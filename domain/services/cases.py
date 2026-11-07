"""Execute CaseWorkflow commands inside the caller's transaction."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from common.ids import next_ref
from domain import states as st
from domain.context import issue_grant, revoke_grants
from domain.models import (
    Decision,
    DecisionInvalidation,
    DuplicateKey,
    ExecutionGrant,
    FieldEvidence,
    Invoice,
    InvoiceRevision,
    Issue,
    RequestContext,
    ReviewRequest,
    Shop,
    utcnow,
)
from domain.services import compensation
from domain.services import messages as msg
from domain.services.base import UNASSIGNED, bump_period, case_event, post, room_for_shop
from domain.workflow import CaseWorkflow, Command, Event
from workers.queue import enqueue


@dataclass
class Exec:
    """Everything a command may need; authority is either an interactive context or a job grant."""

    s: Session
    case: Invoice
    correlation_id: str
    context: RequestContext | None = None
    grant: ExecutionGrant | None = None
    notes: dict[str, str] = field(default_factory=dict)

    def run(self, event: Event) -> list[Command]:
        commands = CaseWorkflow.next(self.case.status, event)
        for command in commands:
            getattr(self, f"_{command.name}")(command)
        return commands

    # -- commands ------------------------------------------------------------------------------

    def _transition(self, c: Command) -> None:
        old, new = st.transition(self.case, c.args["command"])
        case_event(
            self.s,
            self.case,
            f"status:{new}",
            self.correlation_id,
            {"from": old, "to": new, "command": c.args["command"]},
            context_id=self.context.context_id if self.context else None,
            grant_id=self.grant.grant_id if self.grant else None,
        )
        from domain.services import purchases

        purchases.on_case_change(self.s, self.case, self.correlation_id, self.context, self.grant)

    def _supersede_current_revision(self, c: Command) -> None:
        rev = current_revision(self.s, self.case)
        if rev is not None and rev.status == "confirmed":
            compensation.confirmation_invalidated(
                self.s, self.case, rev, c.args["reason"], self.correlation_id
            )
        if rev is not None and rev.status != "superseded":
            rev.status = "superseded"
            rev.superseded_at = utcnow()
        self._supersede_open_issues(c)
        self._invalidate_decisions(c)
        release_duplicate_key(self.s, self.case)

    def _supersede_open_issues(self, c: Command) -> None:
        compensation.review_requests_withdrawn(self.s, self.case, c.args["reason"], self.correlation_id)
        self.s.execute(
            update(Issue)
            .where(
                Issue.invoice_id == self.case.id, Issue.status.notin_(("resolved", "excluded", "superseded"))
            )
            .values(status="superseded", close_reason=c.args["reason"], updated_at=utcnow())
        )
        self.s.execute(
            update(ReviewRequest)
            .where(ReviewRequest.invoice_id == self.case.id, ReviewRequest.status == "open")
            .values(status="stale")
        )

    def _invalidate_decisions(self, c: Command) -> None:
        decided = list(self.s.execute(select(Decision).where(Decision.invoice_id == self.case.id)).scalars())
        already = set(self.s.execute(select(DecisionInvalidation.decision_id)).scalars())
        for decision in decided:
            if decision.id not in already:
                self.s.add(DecisionInvalidation(decision_id=decision.id, reason=c.args["reason"]))
                compensation.decision_invalidated(
                    self.s, self.case, decision, c.args["reason"], self.correlation_id
                )

    def _enqueue_extraction(self, _: Command) -> None:
        grant = issue_grant(
            self.s,
            operation="extract_generation",
            practice_id=self.case.practice_id,
            shop_id=self.case.shop_id,
            case_id=self.case.id,
            generation=self.case.document_generation,
            context=self.context,
            parent=self.grant,
        )
        enqueue(
            self.s,
            type="extract_document",
            lane="slow",
            payload={"case_id": str(self.case.id), "generation": self.case.document_generation},
            dedupe_key=f"extract:{self.case.id}:{self.case.document_generation}",
            correlation_id=self.correlation_id,
            grant_id=grant.grant_id,
        )

    def _claim_duplicate_key(self, _: Command) -> None:
        rev = current_revision(self.s, self.case)
        assert rev is not None
        key = duplicate_key(rev)
        if key is None:
            return
        self.s.execute(
            insert(DuplicateKey)
            .values(
                id=uuid.uuid4(),
                practice_id=self.case.practice_id,
                shop_id=self.case.shop_id,
                key=key,
                case_id=self.case.id,
            )
            .on_conflict_do_nothing(index_elements=["shop_id", "key"])
        )

    def _assign_period(self, _: Command) -> None:
        rev = current_revision(self.s, self.case)
        if rev is None or not rev.invoice_date or self.case.period_basis in ("owner_assigned", "ca_assigned"):
            return
        new_period = rev.invoice_date[:7]
        if new_period != self.case.period:
            bump_period(self.s, self.case.shop_id, self.case.period or UNASSIGNED)
            self.case.period = new_period
            self.case.period_basis = "invoice_date"
            bump_period(self.s, self.case.shop_id, new_period)

    def _enqueue_checks(self, _: Command) -> None:
        rev = current_revision(self.s, self.case)
        assert rev is not None
        grant = issue_grant(
            self.s,
            operation="run_checks",
            practice_id=self.case.practice_id,
            shop_id=self.case.shop_id,
            case_id=self.case.id,
            context=self.context,
            parent=self.grant,
        )
        enqueue(
            self.s,
            type="run_checks",
            lane="fast",
            payload={"case_id": str(self.case.id), "revision_id": str(rev.id)},
            dedupe_key=f"checks:{rev.id}",
            correlation_id=self.correlation_id,
            grant_id=grant.grant_id,
        )

    def _notify_owner(self, c: Command) -> None:
        room = room_for_shop(self.s, self.case.shop_id, "shop_intake")
        if room is None:
            return
        template = c.args["template"]
        rev = current_revision(self.s, self.case)
        if template == "summary":
            assert rev is not None
            evidence = list(
                self.s.execute(select(FieldEvidence).where(FieldEvidence.revision_id == rev.id)).scalars()
            )
            body = msg.summary(self.case, rev, evidence)
            action = f"summary:{rev.id}"
        elif template == "preserved":
            body = msg.preserved(self.case.case_ref, self.notes["receipt_ref"], int(self.notes["pages"]))
            action = f"preserved:{self.case.id}"
        elif template == "replacement_received":
            body = msg.replacement_received(self.case.case_ref, self.case.document_generation)
            action = f"replacement:{self.case.id}:{self.case.document_generation}"
        elif template == "confirmed":
            assert rev is not None
            body = msg.confirmed(self.case.case_ref, rev.revision_no)
            action = f"confirmed:{rev.id}"
        elif template == "extraction_failed":
            body = msg.extraction_failed(self.case.case_ref)
            action = f"extraction_failed:{self.case.id}:{self.case.document_generation}"
        else:
            raise ValueError(f"unknown template {template}")
        post(
            self.s,
            room,
            action_id=action,
            body=body,
            case_ref=self.case.case_ref,
            correlation_id=self.correlation_id,
        )

    def _route_issues(self, _: Command) -> None:
        from domain.services.checks import route_issues

        route_issues(self.s, self.case, self.correlation_id)

    def _open_review_request(self, _: Command) -> None:
        from domain.services.checks import open_review_request

        open_review_request(self.s, self.case, self.correlation_id)


# ----------------------------------------------------------------------------------- helpers


def current_revision(s: Session, case: Invoice) -> InvoiceRevision | None:
    return s.get(InvoiceRevision, case.current_revision_id) if case.current_revision_id else None


def new_case(s: Session, shop: Shop, correlation_id: str) -> Invoice:
    case = Invoice(
        practice_id=shop.practice_id,
        shop_id=shop.id,
        case_ref=next_ref(s, shop.practice_id, "INV"),
        status=st.RECEIVED,
        document_generation=1,
    )
    s.add(case)
    s.flush()
    case_event(s, case, "case_created", correlation_id, {"status": st.RECEIVED})
    return case


def financial_year(invoice_date: str) -> str:
    d = date.fromisoformat(invoice_date)
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def normalize_number(number: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", number.upper())


def duplicate_key(rev: InvoiceRevision) -> str | None:
    if not (rev.supplier_gstin and rev.invoice_number and rev.invoice_date):
        return None
    try:
        fy = financial_year(rev.invoice_date)
    except ValueError:
        return None
    return "|".join(
        [rev.supplier_gstin.upper(), rev.document_type or "unknown", fy, normalize_number(rev.invoice_number)]
    )


def release_duplicate_key(s: Session, case: Invoice) -> None:
    s.execute(delete(DuplicateKey).where(DuplicateKey.case_id == case.id))


def revoke_older_generations(s: Session, case: Invoice) -> None:
    revoke_grants(s, "document_replaced", case_id=case.id, below_generation=case.document_generation)
