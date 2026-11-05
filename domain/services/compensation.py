"""Compensation notices (spec section 2, saga): when an earlier confirmation, review request, decision or
pack no longer applies, post a superseding notice naming the original action id and the reason. Nothing in
the room is edited or deleted. One notice per original action (outbox dedupe on the action id)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.models import Decision, Invoice, InvoiceRevision, ReviewRequest, Snapshot
from domain.services.base import post, room_for_shop

REASONS = {
    "document_replaced": "a replacement document arrived",
    "revision_replaced": "the details were corrected",
    "case_excluded": "the invoice was excluded",
    "period_changed": "an invoice in the month changed",
    "rebuilt": "a newer pack was built",
    "approved_newer": "a newer pack was approved",
    "stale": "the month changed before approval",
}


def _reason(code: str) -> str:
    return REASONS.get(code, code.replace("_", " "))


def review_requests_withdrawn(s: Session, case: Invoice, reason: str, correlation_id: str) -> None:
    room = room_for_shop(s, case.shop_id, "ca_review")
    if room is None:
        return
    for rr in s.execute(
        select(ReviewRequest).where(ReviewRequest.invoice_id == case.id, ReviewRequest.status == "open")
    ).scalars():
        original = f"review:{rr.id}"
        post(
            s,
            room,
            action_id=f"withdrawn:{original}",
            supersedes=original,
            body=f"Withdrawn: {rr.public_ref} for {case.case_ref} no longer applies because {_reason(reason)}. "
            f"Do not decide it; a new review request follows. (supersedes {original})",
            case_ref=case.case_ref,
            correlation_id=correlation_id,
        )


def decision_invalidated(
    s: Session, case: Invoice, decision: Decision, reason: str, correlation_id: str
) -> None:
    room = room_for_shop(s, case.shop_id, "ca_review")
    rr = s.get(ReviewRequest, decision.review_request_id)
    if room is None or rr is None:
        return
    original = f"decision:{decision.id}"
    post(
        s,
        room,
        action_id=f"invalidated:{original}",
        supersedes=original,
        body=f"No longer applies: {rr.public_ref} '{decision.action.replace('_', ' ')}' on {case.case_ref} "
        f"because {_reason(reason)}. The case needs a new decision. (supersedes {original})",
        case_ref=case.case_ref,
        correlation_id=correlation_id,
    )


def confirmation_invalidated(
    s: Session, case: Invoice, rev: InvoiceRevision, reason: str, correlation_id: str
) -> None:
    room = room_for_shop(s, case.shop_id, "shop_intake")
    if room is None:
        return
    original = f"confirmed:{rev.id}"
    post(
        s,
        room,
        action_id=f"unconfirmed:{original}",
        supersedes=original,
        body=f"Your confirmation of {case.case_ref} r{rev.revision_no} no longer applies because {_reason(reason)}. "
        "Please check the new summary. (supersedes " + original + ")",
        case_ref=case.case_ref,
        correlation_id=correlation_id,
    )


def snapshot_superseded(s: Session, snap: Snapshot, reason: str, correlation_id: str) -> None:
    room = room_for_shop(s, snap.shop_id, "ca_review")
    if room is None:
        return
    original = f"snapshot:{snap.id}"
    post(
        s,
        room,
        action_id=f"pack_superseded:{snap.id}:{reason}",
        supersedes=original,
        body=f"{snap.public_ref} (hash {snap.content_hash[:12]}, {snap.period}) is superseded because "
        f"{_reason(reason)}. It stays reproducible for audit; do not file from it. (supersedes {original})",
        correlation_id=correlation_id,
    )


def packs_outdated(s: Session, shop_id: object, period: str, correlation_id: str) -> None:
    """An approved pack whose month changed afterwards is labelled, once, so nobody files from it."""
    for snap in s.execute(
        select(Snapshot).where(
            Snapshot.shop_id == shop_id,
            Snapshot.period == period,
            Snapshot.status.in_(("approved", "exported")),
        )
    ).scalars():
        snapshot_superseded(s, snap, "period_changed", correlation_id)
