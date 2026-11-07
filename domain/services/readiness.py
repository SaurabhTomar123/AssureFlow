"""Purchase review and payment readiness (U2 sections 7 and 9).

Three separate facts: the invoice review (v1.4, unchanged), the purchase review by an assigned reviewer, and
the owner's authorization. Both sign-offs bind the exact content hash of a frozen record, and the owner's
authorization rechecks the current inputs in the same transaction. "Ready for payment" never means paid.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from common.errors import MatchStale, NotFound, ValidationFailed
from common.ids import next_ref
from domain.context import issue_grant
from domain.models import (
    BusinessTask,
    DeliveryEvent,
    DeliveryReport,
    ExecutionGrant,
    Invoice,
    InvoiceRevision,
    PaymentReadiness,
    PurchaseLink,
    PurchaseMatchRun,
    PurchaseOrder,
    RequestContext,
    Shop,
    TaskEvent,
    utcnow,
)
from domain.scope import has_capability
from domain.services import purchases as pa
from domain.services.base import audit, case_event, post, room_for_shop
from domain.services.messages import inr
from rules.purchase import digest
from workers.queue import enqueue

ACTIVE = ("awaiting_review", "awaiting_owner", "ready_for_payment")
WORDING = (
    "Payment readiness records that this purchase was reviewed for payment. It does not mean payment was sent, "
    "a debt was settled, or GST input tax credit is eligible."
)
CHANGE_LABELS = {
    "invoice_revision_id": "the invoice changed",
    "document_generation": "a replacement invoice arrived",
    "invoice_status": "the invoice review changed",
    "check_run_id": "the invoice checks were rerun",
    "mapping": "the line mapping changed",
    "link_version": "the purchase link changed",
    "order_revision_id": "the order changed",
    "order_status": "the order changed",
    "delivery_set": "the confirmed delivery changed",
    "partial_accepted": "the partial-delivery acceptance changed",
    "blocking_tasks": "an assigned task changed",
}


def active_record(s: Session, link_id: uuid.UUID) -> PaymentReadiness | None:
    return s.execute(
        select(PaymentReadiness)
        .where(PaymentReadiness.link_id == link_id, PaymentReadiness.status.in_(ACTIVE))
        .order_by(PaymentReadiness.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _rooms(s: Session, shop_id: uuid.UUID) -> list[Any]:
    return [r for r in (room_for_shop(s, shop_id, "ca_review"), room_for_shop(s, shop_id, "shop_intake")) if r]


def _make_stale(s: Session, record: PaymentReadiness, reason: str, correlation_id: str) -> None:
    record.status = "stale"
    record.stale_reason = reason
    case_ref = record.content["invoice"]["case_ref"]
    order_ref = record.content["order"]["ref"]
    extra = " The earlier record and any export stay as history." if record.authorized_at else ""
    for room in _rooms(s, record.shop_id):
        post(
            s,
            room,
            action_id=f"readiness_withdrawn:{record.id}",
            body=f"Withdrawn: {record.public_ref} for {order_ref} / {case_ref} no longer applies because {reason}. "
            f"A fresh review is needed.{extra}",
            correlation_id=correlation_id,
        )


def withdraw_if_changed(
    s: Session, link: PurchaseLink, input_hash: str, vector: dict[str, Any], correlation_id: str
) -> None:
    record = active_record(s, link.id)
    if record is None or record.input_hash == input_hash:
        return
    before = record.content["input_vector"]
    changed = [label for key, label in CHANGE_LABELS.items() if before.get(key) != vector.get(key)]
    _make_stale(s, record, changed[0] if changed else "its inputs changed", correlation_id)


def advance(
    s: Session, link: PurchaseLink, run: PurchaseMatchRun, correlation_id: str, grant: ExecutionGrant
) -> None:
    """A passing match with no open blocker becomes a frozen record awaiting the reviewer."""
    if run.status != "pass":
        return
    case = s.get(Invoice, link.case_id)
    order = s.get(PurchaseOrder, link.order_id)
    assert case is not None and order is not None
    shop_room = room_for_shop(s, link.shop_id, "shop_intake")
    blockers = pa.open_blockers(s, link.id)
    if blockers:
        link.purchase_state = "needs_resolution"
        if shop_room is not None:
            refs = ", ".join(t.task_ref for t in blockers)
            post(
                s,
                shop_room,
                action_id=f"verify_prompt:{link.id}:{run.results_hash}:{refs}",
                body=f"{order.order_ref} / {case.case_ref}: the purchase checks now pass. {refs} is still open; "
                f"when you are satisfied, reply `{blockers[0].task_ref} verify` (or `cancel <reason>`).",
                case_ref=case.case_ref,
                correlation_id=correlation_id,
            )
        return
    existing = active_record(s, link.id)
    if existing is not None and existing.input_hash == run.input_hash:
        link.purchase_state = {"awaiting_review": "ready_for_review"}.get(existing.status, existing.status)
        return
    rev = s.get(InvoiceRevision, case.current_revision_id)
    assert rev is not None and rev.invoice_total is not None
    ref = next_ref(s, link.practice_id, "PR")
    content: dict[str, Any] = {
        "ref": ref,
        "order": {"ref": order.order_ref, "supplier": order.supplier_name, "supplier_gstin": order.supplier_gstin},
        "invoice": {
            "case_ref": case.case_ref,
            "revision": rev.revision_no,
            "document_generation": case.document_generation,
            "invoice_number": rev.invoice_number,
            "invoice_total": str(rev.invoice_total),
        },
        "match": {"run_id": str(run.id), "results_hash": run.results_hash, "lines": run.totals.get("lines", []),
                  "findings": run.findings},
        "input_vector": run.input_vector,
        "amount": str(rev.invoice_total),
        "currency": "INR",
    }
    content_hash = digest(content)
    record = PaymentReadiness(
        practice_id=link.practice_id,
        shop_id=link.shop_id,
        public_ref=ref,
        link_id=link.id,
        match_run_id=run.id,
        input_hash=run.input_hash,
        content=content,
        content_hash=content_hash,
        amount=Decimal(rev.invoice_total),
        currency="INR",
    )
    s.add(record)
    s.flush()
    link.purchase_state = "ready_for_review"
    lines = "\n".join(
        f"• {x['description']}: ordered {x['ordered']}, received {x['received']}, billed {x['billed']} {x['unit']}"
        + (f" ({x['outstanding']} outstanding on the order)" if x["outstanding"] != "0" else "")
        for x in content["match"]["lines"]
    )
    ca_room = room_for_shop(s, link.shop_id, "ca_review")
    if ca_room is not None:
        post(
            s,
            ca_room,
            action_id=f"readiness:{record.id}",
            body=f"{ref} · {order.order_ref} / {case.case_ref} r{rev.revision_no}: purchase review.\n{lines}\n"
            f"Invoice total {inr(rev.invoice_total)}; invoice review: included; delivery confirmed; checks passed.\n"
            f"Hash {content_hash[:12]}. Reply `review {ref} {content_hash[:12]}` to sign off this exact record. "
            "This is payment preparation; no payment is made.",
            correlation_id=correlation_id,
        )
    if shop_room is not None:
        post(
            s,
            shop_room,
            action_id=f"readiness_owner_note:{record.id}",
            body=f"{order.order_ref} / {case.case_ref}: purchase checks passed. {ref} is with the reviewer.",
            case_ref=case.case_ref,
            correlation_id=correlation_id,
        )


def _find(s: Session, ctx: RequestContext, shop_ids: list[uuid.UUID], ref: str) -> PaymentReadiness:
    record = s.execute(
        select(PaymentReadiness)
        .where(PaymentReadiness.practice_id == ctx.practice_id, PaymentReadiness.public_ref == ref.upper())
        .with_for_update()
    ).scalar_one_or_none()
    if record is None or record.shop_id not in shop_ids:
        raise NotFound(f"No record {ref.upper()} in this room.")
    return record


def _refuse_if_stale(record: PaymentReadiness) -> None:
    if record.status == "stale":
        raise MatchStale(
            f"{record.public_ref} no longer applies because {record.stale_reason or 'its inputs changed'}. "
            "A fresh review is needed."
        )


def _check_hash(record: PaymentReadiness, prefix: str) -> None:
    if len(prefix) < 8 or not record.content_hash.startswith(prefix.lower()):
        raise ValidationFailed(f"That hash does not match {record.public_ref}. Use `{record.content_hash[:12]}`.")


def _require_current(s: Session, record: PaymentReadiness, correlation_id: str) -> PurchaseLink:
    link = s.execute(select(PurchaseLink).where(PurchaseLink.id == record.link_id).with_for_update()).scalar_one()
    if record.status == "stale":
        raise MatchStale(f"{record.public_ref} no longer applies ({record.stale_reason}).")
    _, vector, current = pa.current_inputs(s, link)
    if current != record.input_hash:
        before = record.content["input_vector"]
        changed = [label for key, label in CHANGE_LABELS.items() if before.get(key) != vector.get(key)]
        reason = changed[0] if changed else "its inputs changed"
        _make_stale(s, record, reason, correlation_id)
        raise MatchStale(f"{record.public_ref} no longer applies because {reason}. A fresh review is needed.")
    return link


def review(s: Session, ctx: RequestContext, shop_ids: list[uuid.UUID], ref: str, prefix: str) -> str:
    record = _find(s, ctx, shop_ids, ref)
    shop = s.get(Shop, record.shop_id)
    assert shop is not None
    pa.require_enabled(shop)
    pa.require_cap(s, ctx, record.shop_id, "purchase_review", "sign off purchase reviews")
    _refuse_if_stale(record)
    _check_hash(record, prefix)
    if record.status != "awaiting_review":
        raise ValidationFailed(f"{record.public_ref} is {record.status.replace('_', ' ')}.")
    link = _require_current(s, record, ctx.request_id)
    record.status = "awaiting_owner"
    record.reviewed_by, record.reviewed_at, record.review_context_id = ctx.verified_user_id, utcnow(), ctx.context_id
    link.purchase_state = "awaiting_owner"
    audit(
        s,
        action="purchase.reviewed",
        entity="payment_readiness",
        entity_id=str(record.id),
        outcome="ok",
        actor=str(ctx.verified_user_id),
        request_id=ctx.request_id,
        practice_id=record.practice_id,
        shop_id=record.shop_id,
        context_id=ctx.context_id,
        after={"ref": record.public_ref, "content_hash": record.content_hash},
    )
    shop_room = room_for_shop(s, record.shop_id, "shop_intake")
    if shop_room is not None:
        post(
            s,
            shop_room,
            action_id=f"readiness_reviewed:{record.id}",
            body=f"{record.public_ref} ({record.content['order']['ref']} / {record.content['invoice']['case_ref']}, "
            f"{inr(record.amount)}) was reviewed by {pa.display(s, ctx.verified_user_id)}. Your sign-off is pending. "
            f"Reply `authorize {record.public_ref} {record.content_hash[:12]} due YYYY-MM-DD` with the supplier's due "
            "date, or `due unknown`. This is payment preparation; no payment is made.",
            correlation_id=ctx.request_id,
        )
    return f"{record.public_ref} signed off. It now waits for the owner's authorization."


def parse_due(words: list[str]) -> tuple[str | None, str]:
    lowered = [w.lower() for w in words]
    if "due" not in lowered or lowered.index("due") + 1 >= len(words):
        raise ValidationFailed("Add the supplier's due date: `due 2026-11-20`, or `due unknown`.")
    value = words[lowered.index("due") + 1]
    if value.lower() == "unknown":
        return None, "unknown"
    try:
        from datetime import date

        return date.fromisoformat(value).isoformat(), "owner_confirmed_terms"
    except ValueError as exc:
        raise ValidationFailed(f"'{value}' is not a date (use YYYY-MM-DD).") from exc


def authorize(s: Session, ctx: RequestContext, shop_ids: list[uuid.UUID], ref: str, prefix: str, words: list[str]) -> str:
    record = _find(s, ctx, shop_ids, ref)
    shop = s.get(Shop, record.shop_id)
    assert shop is not None
    pa.require_enabled(shop)
    pa.require_cap(s, ctx, record.shop_id, "readiness_authorize", "authorize payment readiness")
    _refuse_if_stale(record)
    _check_hash(record, prefix)
    if record.status == "awaiting_review":
        raise ValidationFailed(f"{record.public_ref} has not been reviewed yet.")
    if record.status != "awaiting_owner":
        raise ValidationFailed(f"{record.public_ref} is {record.status.replace('_', ' ')}.")
    due, source = parse_due(words)
    link = _require_current(s, record, ctx.request_id)
    if record.reviewed_by is None or not has_capability(s, record.reviewed_by, record.shop_id, "purchase_review"):
        raise MatchStale("The reviewer's assignment changed; a fresh review is needed.")
    record.status = "ready_for_payment"
    record.authorized_by, record.authorized_at, record.authorize_context_id = (
        ctx.verified_user_id,
        utcnow(),
        ctx.context_id,
    )
    record.due_date, record.due_source = due, source
    link.purchase_state = "ready_for_payment"
    case = s.get(Invoice, link.case_id)
    assert case is not None
    case_event(s, case, "readiness_authorized", ctx.request_id, {"ref": record.public_ref}, context_id=ctx.context_id)
    audit(
        s,
        action="purchase.readiness_authorized",
        entity="payment_readiness",
        entity_id=str(record.id),
        outcome="ok",
        actor=str(ctx.verified_user_id),
        request_id=ctx.request_id,
        practice_id=record.practice_id,
        shop_id=record.shop_id,
        context_id=ctx.context_id,
        after={"ref": record.public_ref, "content_hash": record.content_hash, "due": due},
    )
    grant = issue_grant(
        s,
        operation="build_purchase_export",
        practice_id=record.practice_id,
        shop_id=record.shop_id,
        case_id=link.case_id,
        context=ctx,
    )
    enqueue(
        s,
        type="build_purchase_export",
        lane="slow",
        payload={"readiness_id": str(record.id)},
        dedupe_key=f"purchase_export:{record.id}",
        correlation_id=ctx.request_id,
        grant_id=grant.grant_id,
    )
    outstanding = [
        f"{x['outstanding']} {x['unit']} {x['description']}" for x in record.content["match"]["lines"] if x["outstanding"] != "0"
    ]
    rest = f" Still outstanding on {record.content['order']['ref']}: {'; '.join(outstanding)}." if outstanding else ""
    return (
        f"{record.public_ref} is ready for payment: {inr(record.amount)}, due {due or 'unknown'}. "
        f"Nothing has been paid; this records that the purchase was reviewed.{rest} The purchase pack follows."
    )


def pack(s: Session, record: PaymentReadiness) -> dict[str, Any]:
    """The frozen purchase pack (purchase_assurance.v1), built only from records up to the authorization."""
    link = s.get(PurchaseLink, record.link_id)
    assert link is not None and record.authorized_at is not None
    order = s.get(PurchaseOrder, link.order_id)
    assert order is not None
    cutoff = record.authorized_at
    run = s.get(PurchaseMatchRun, record.match_run_id)
    assert run is not None
    order_rev_id = record.content["input_vector"]["order_revision_id"]
    from domain.models import PurchaseOrderRevision

    order_rev = s.get(PurchaseOrderRevision, uuid.UUID(order_rev_id))
    assert order_rev is not None
    deliveries = []
    wanted = {entry.split(":")[0] + ":" + entry.split(":")[1] for entry in record.content["input_vector"]["delivery_set"]}
    for report in s.execute(
        select(DeliveryReport).where(DeliveryReport.order_id == order.id).order_by(DeliveryReport.report_ref, DeliveryReport.report_version)
    ).scalars():
        if f"{report.report_ref}:v{report.report_version}" not in wanted:
            continue
        event = s.execute(
            select(DeliveryEvent).where(DeliveryEvent.report_id == report.id, DeliveryEvent.action == "confirmed")
        ).scalar_one_or_none()
        deliveries.append(
            {
                "ref": report.report_ref,
                "version": report.report_version,
                "lines": report.lines,
                "confirmed_by": pa.display(s, event.actor_user_id if event else None),
                "confirmed_at": event.created_at.isoformat() if event else None,
                "content_hash": report.content_hash,
            }
        )
    tasks = []
    for task in s.execute(
        select(BusinessTask).where(BusinessTask.link_id == link.id, BusinessTask.created_at <= cutoff).order_by(BusinessTask.task_ref)
    ).scalars():
        events = list(
            s.execute(
                select(TaskEvent)
                .where(TaskEvent.task_id == task.id, TaskEvent.created_at <= cutoff)
                .order_by(TaskEvent.created_at)
            ).scalars()
        )
        history = [
            f"{e.action} -> {e.to_status} by {pa.display(s, e.actor_user_id)}" + (f": {e.note}" if e.note else "")
            for e in events
        ]
        tasks.append(
            {
                "ref": task.task_ref,
                "assignee": pa.display(s, task.assignee_user_id),
                "due": task.due_at,
                "status": events[-1].to_status if events else task.status,
                "reason": task.reason,
                "history": history,
            }
        )
    return {
        "format": "purchase_assurance.v1",
        "wording": WORDING,
        "readiness": {
            "ref": record.public_ref,
            "status": "ready_for_payment",
            "amount": str(record.amount),
            "currency": record.currency,
            "due_date": record.due_date,
            "due_source": record.due_source,
            "content_hash": record.content_hash,
            "reviewed_by": pa.display(s, record.reviewed_by),
            "reviewed_at": record.reviewed_at.isoformat() if record.reviewed_at else None,
            "authorized_by": pa.display(s, record.authorized_by),
            "authorized_at": cutoff.isoformat(),
        },
        "order": {
            "ref": order.order_ref,
            "revision": order_rev.revision_no,
            "supplier": order.supplier_name,
            "supplier_gstin": order.supplier_gstin,
            "lines": order_rev.lines,
        },
        "invoice": record.content["invoice"],
        "deliveries": deliveries,
        "match": {"rule_version": run.rule_version, "results_hash": run.results_hash, "lines": run.totals.get("lines", []),
                  "findings": run.findings, "partial_accepted": run.totals.get("partial_accepted", False)},
        "tasks": tasks,
    }


def pack_json(s: Session, record: PaymentReadiness) -> str:
    return json.dumps(pack(s, record), sort_keys=True, ensure_ascii=False, indent=1)
