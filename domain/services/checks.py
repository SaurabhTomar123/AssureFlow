"""Step 5-6: versioned checks on the confirmed revision, issue ownership and CA hand-off."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from common.ids import next_ref
from common.settings import get_settings
from domain.models import (
    CheckResult,
    CheckRun,
    DuplicateKey,
    Handoff,
    Invoice,
    InvoiceRevision,
    Issue,
    LineItem,
    ReviewRequest,
    Shop,
    utcnow,
)
from domain.services import messages as msg
from domain.services.base import post, room_for_shop
from domain.services.cases import current_revision, duplicate_key
from rules import registry, routing
from rules.types import PASS, LineInput, RevisionInput, RuleResult, Tolerances

COMPONENT_FIELDS = {"cgst": "cgst_total", "sgst": "sgst_total", "igst": "igst_total", "cess": "cess_total"}


def build_input(s: Session, case: Invoice, rev: InvoiceRevision) -> RevisionInput:
    shop = s.get(Shop, case.shop_id)
    assert shop is not None
    lines = tuple(
        LineInput(
            line_no=li.line_no,
            description=li.description,
            hsn_sac=li.hsn_sac,
            qty=li.qty,
            unit_price=li.unit_price,
            discount=li.discount,
            taxable_value=li.taxable_value,
            cgst_rate=li.cgst_rate,
            sgst_rate=li.sgst_rate,
            igst_rate=li.igst_rate,
            combined_rate=li.combined_rate,
            cgst_amount=li.cgst_amount,
            sgst_amount=li.sgst_amount,
            igst_amount=li.igst_amount,
        )
        for li in s.execute(
            select(LineItem).where(LineItem.revision_id == rev.id).order_by(LineItem.line_no)
        ).scalars()
    )
    key = duplicate_key(rev)
    owner_ref = None
    if key:
        owner = s.execute(
            select(DuplicateKey).where(DuplicateKey.shop_id == case.shop_id, DuplicateKey.key == key)
        ).scalar_one_or_none()
        if owner is not None and owner.case_id != case.id:
            other = s.get(Invoice, owner.case_id)
            owner_ref = other.case_ref if other else None
    return RevisionInput(
        document_type=rev.document_type,
        supplier_name=rev.supplier_name,
        supplier_gstin=rev.supplier_gstin,
        recipient_gstin=rev.recipient_gstin,
        invoice_number=rev.invoice_number,
        invoice_date=rev.invoice_date,
        place_of_supply=rev.place_of_supply,
        currency=rev.currency,
        tax_printed_per_line=rev.tax_printed_per_line,
        taxable_total=rev.taxable_total,
        cgst_total=rev.cgst_total,
        sgst_total=rev.sgst_total,
        igst_total=rev.igst_total,
        cess_total=rev.cess_total,
        round_off=rev.round_off,
        invoice_total=rev.invoice_total,
        lines=lines,
        shop_gstin=shop.gstin,
        duplicate_owner_ref=owner_ref,
        similar_case_refs=tuple(similar_cases(s, case, rev)),
    )


def similar_cases(s: Session, case: Invoice, rev: InvoiceRevision) -> list[str]:
    """Same supplier and total within 7 days, in another case of this shop that is not excluded."""
    if not (rev.supplier_gstin and rev.invoice_total is not None and rev.invoice_date):
        return []
    try:
        day = date.fromisoformat(rev.invoice_date)
    except ValueError:
        return []
    rows = s.execute(
        select(Invoice.case_ref, InvoiceRevision.invoice_date)
        .join(InvoiceRevision, InvoiceRevision.id == Invoice.current_revision_id)
        .where(
            Invoice.shop_id == case.shop_id,
            Invoice.id != case.id,
            Invoice.status != "excluded",
            InvoiceRevision.supplier_gstin == rev.supplier_gstin,
            InvoiceRevision.invoice_total == rev.invoice_total,
            InvoiceRevision.invoice_number != rev.invoice_number,
        )
    ).all()
    refs = []
    for ref, other_date in rows:
        if not other_date:
            continue
        try:
            if abs(date.fromisoformat(other_date) - day) <= timedelta(days=7):
                refs.append(ref)
        except (TypeError, ValueError):
            continue
    return sorted(refs)


def evaluate(s: Session, case: Invoice, rev: InvoiceRevision) -> tuple[list[RuleResult], str, str]:
    settings = get_settings()
    rev_input = build_input(s, case, rev)
    tol = Tolerances(tax_line=settings.TAX_LINE_TOLERANCE_INR, amount=settings.AMOUNT_TOLERANCE_INR)
    results = registry.run_profile(rev_input, tol)
    inputs_hash = hashlib.sha256(
        json.dumps(rev_input.__dict__, default=str, sort_keys=True).encode()
    ).hexdigest()
    return results, inputs_hash, registry.results_hash(results)


def record_check_run(
    s: Session,
    case: Invoice,
    rev: InvoiceRevision,
    results: list[RuleResult],
    inputs_hash: str,
    results_hash: str,
) -> tuple[CheckRun, bool, bool]:
    """Persist the run and upsert one issue per (revision, rule). Returns (run, blocking, ca_attention)."""
    run_seq = (
        s.execute(
            select(func.coalesce(func.max(CheckRun.run_seq), 0)).where(CheckRun.revision_id == rev.id)
        ).scalar_one()
        + 1
    )
    blocking = any(r.is_blocking for r in results)
    run = CheckRun(
        practice_id=case.practice_id,
        shop_id=case.shop_id,
        invoice_id=case.id,
        revision_id=rev.id,
        run_seq=run_seq,
        profile_version=f"{registry.PROFILE}",
        status="blocking" if blocking else "clean",
        inputs_hash=inputs_hash,
        results_hash=results_hash,
    )
    s.add(run)
    s.flush()
    claimed: set[str] = set()
    ca_attention = False
    for result in results:
        row = CheckResult(
            practice_id=case.practice_id,
            shop_id=case.shop_id,
            check_run_id=run.id,
            rule_id=result.rule_id,
            rule_version=result.version,
            outcome=result.outcome,
            severity=result.severity,
            category=result.category,
            message=result.message,
            inputs=result.inputs,
            calculation=result.calculation,
            difference=result.difference,
        )
        s.add(row)
        s.flush()
        if result.outcome == PASS:
            continue
        role = routing.owner_role(result)
        ca_attention = ca_attention or role == "ca"
        new_components = [c for c in result.components if c not in claimed]
        claimed.update(new_components)
        exposure = sum((getattr(rev, COMPONENT_FIELDS[c]) or Decimal(0) for c in new_components), Decimal(0))
        issue = s.execute(
            select(Issue).where(Issue.revision_id == rev.id, Issue.rule_id == result.rule_id)
        ).scalar_one_or_none()
        if issue is None:
            issue = Issue(
                practice_id=case.practice_id,
                shop_id=case.shop_id,
                invoice_id=case.id,
                revision_id=rev.id,
                rule_id=result.rule_id,
            )
            s.add(issue)
        issue.check_result_id = row.id
        issue.category = result.category
        issue.blocking = result.is_blocking
        issue.status = "awaiting_owner" if role == "owner" else "awaiting_ca"
        issue.owner_role = role
        issue.next_action = routing.NEXT_ACTION[role]
        issue.due_at = utcnow() + timedelta(days=2)
        issue.exposure_key = ",".join(f"{rev.id}:{c}" for c in new_components) or None
        issue.exposure_amount = exposure
        issue.updated_at = utcnow()
    s.flush()
    return run, blocking, ca_attention


def open_issues(s: Session, case: Invoice) -> list[Issue]:
    return list(
        s.execute(
            select(Issue)
            .where(Issue.invoice_id == case.id, Issue.revision_id == case.current_revision_id)
            .where(Issue.status.in_(("open", "awaiting_owner", "awaiting_supplier", "awaiting_ca")))
            .order_by(Issue.rule_id)
        ).scalars()
    )


def issue_message(s: Session, issue: Issue) -> str:
    result = s.get(CheckResult, issue.check_result_id)
    text = result.message if result else issue.rule_id
    amount = (
        f" · tax amount associated with this issue: {msg.inr(issue.exposure_amount)}"
        if issue.exposure_amount
        else ""
    )
    return f"{issue.rule_id}: {text}{amount}"


def route_issues(s: Session, case: Invoice, correlation_id: str) -> None:
    owner_issues = [i for i in open_issues(s, case) if i.owner_role == "owner"]
    room = room_for_shop(s, case.shop_id, "shop_intake")
    if owner_issues and room is not None:
        first = owner_issues[0]
        body = (
            f"{case.case_ref} needs one thing from you: {issue_message(s, first)}\n"
            f"Type the value (e.g. `{case.case_ref} pos=07`) or send a clearer copy with {case.case_ref} in the message."
        )
        post(
            s,
            room,
            action_id=f"owner_issue:{first.id}",
            body=body,
            case_ref=case.case_ref,
            correlation_id=correlation_id,
        )


def latest_run(s: Session, rev_id: object) -> CheckRun | None:
    return s.execute(
        select(CheckRun).where(CheckRun.revision_id == rev_id).order_by(CheckRun.run_seq.desc()).limit(1)
    ).scalar_one_or_none()


def open_review_request(s: Session, case: Invoice, correlation_id: str) -> ReviewRequest | None:
    """A review request bound to (revision, check run) plus a durable, data-only handoff to the CA room."""
    rev = current_revision(s, case)
    if rev is None:
        return None
    run = latest_run(s, rev.id)
    if run is None:
        return None
    existing = s.execute(
        select(ReviewRequest).where(ReviewRequest.check_run_id == run.id, ReviewRequest.status == "open")
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    for old in s.execute(
        select(ReviewRequest).where(ReviewRequest.invoice_id == case.id, ReviewRequest.status == "open")
    ).scalars():
        old.status = "stale"
    rr = ReviewRequest(
        practice_id=case.practice_id,
        shop_id=case.shop_id,
        public_ref=next_ref(s, case.practice_id, "RR"),
        invoice_id=case.id,
        revision_id=rev.id,
        check_run_id=run.id,
        status="open",
    )
    s.add(rr)
    s.flush()
    ca_issues = [i for i in open_issues(s, case) if i.owner_role == "ca"]
    blocking = any(i.blocking for i in open_issues(s, case))
    overridable = sorted(
        i.rule_id
        for i in open_issues(s, case)
        if i.blocking and i.rule_id in registry.BY_ID and registry.BY_ID[i.rule_id].overridable
    )
    shop = s.get(Shop, case.shop_id)
    assert shop is not None
    summary_lines = [issue_message(s, i) for i in ca_issues] or ["All required checks passed."]
    dedupe = hashlib.sha256(f"{case.id}|{rev.id}|review|ca".encode()).hexdigest()
    shop_room = room_for_shop(s, case.shop_id, "shop_intake")
    ca_room = room_for_shop(s, case.shop_id, "ca_review")
    if s.execute(select(Handoff).where(Handoff.dedupe_key == dedupe)).scalar_one_or_none() is None:
        s.add(
            Handoff(
                practice_id=case.practice_id,
                shop_id=case.shop_id,
                case_id=case.id,
                expected_revision_id=rev.id,
                from_role="shop_intake",
                to_role="ca_review",
                from_room=shop_room.id if shop_room else None,
                to_room=ca_room.id if ca_room else None,
                originating_actor=str(rev.confirmed_by) if rev.confirmed_by else None,
                evidence_refs=[f"document:{rev.document_id}"],
                issue_summary="; ".join(summary_lines)[:2000],
                responsible_role="ca",
                next_action=f"Decide {rr.public_ref}",
                hop_count=1,
                dedupe_key=dedupe,
            )
        )
    if ca_room is not None:
        body = "\n".join(
            [
                f"{rr.public_ref} · {case.case_ref} r{rev.revision_no} · {shop.name} ({shop.code})",
                f"{rev.supplier_name or 'Unknown supplier'} · {rev.invoice_number or '?'} · {rev.invoice_date or '?'} · "
                f"total {msg.inr(rev.invoice_total)} · check run {run.run_seq}",
                *[f"• {line}" for line in summary_lines],
                "Reply "
                + (
                    f"`{rr.public_ref} resolve <RULE-ID> <reason>`"
                    + (
                        f", `{rr.public_ref} override {','.join(overridable)} <reason>`"
                        if overridable
                        else ""
                    )
                    if blocking
                    else f"`{rr.public_ref} include`"
                )
                + f", `{rr.public_ref} exclude <reason>`, `{rr.public_ref} clarify <question>` "
                f"or `{rr.public_ref} supplier <reason>`.",
            ]
        )
        post(
            s,
            ca_room,
            action_id=f"review:{rr.id}",
            body=body,
            case_ref=case.case_ref,
            correlation_id=correlation_id,
        )
    return rr
