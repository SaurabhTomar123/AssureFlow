"""Daily digests, quiet hours, stop rules and escalation (P3-05).

One combined digest per room per local day at DIGEST_LOCAL_TIME (shop time zone), never in QUIET_HOURS.
Items are recomputed from current state every time, so resolved, excluded or superseded work stops
appearing by itself. An owner item still pending after DIGEST_ESCALATE_AFTER consecutive digests is
escalated once to the CA review room. Runs under a scheduled `notify` grant: read and send only.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from common.settings import get_settings
from domain.context import issue_grant
from domain.models import (
    DigestRun,
    Invoice,
    Issue,
    Job,
    ReviewRequest,
    RoomBinding,
    Shop,
    utcnow,
)
from domain.services.base import post, room_for_shop, shops_of_room
from workers.queue import enqueue

OWNER_STATES = ("needs_confirmation", "extraction_failed")


def _hm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def in_quiet_hours(local: datetime, quiet: str | None = None) -> bool:
    start_s, end_s = (quiet or get_settings().QUIET_HOURS).split("-")
    start, end, now = _hm(start_s), _hm(end_s), local.time()
    return (now >= start or now < end) if start > end else (start <= now < end)


def owner_items(s: Session, shop_id: uuid.UUID) -> dict[str, str]:
    items: dict[str, str] = {}
    for case in s.execute(
        select(Invoice)
        .where(Invoice.shop_id == shop_id, Invoice.status.in_(OWNER_STATES))
        .order_by(Invoice.case_ref)
    ).scalars():
        items[case.case_ref] = (
            "confirm the details" if case.status == "needs_confirmation" else "send a clearer copy"
        )
    for issue, ref in s.execute(
        select(Issue, Invoice.case_ref)
        .join(Invoice, Invoice.id == Issue.invoice_id)
        .where(
            Issue.shop_id == shop_id,
            Issue.revision_id == Invoice.current_revision_id,
            Issue.status.in_(("awaiting_owner", "awaiting_supplier")),
        )
    ).all():
        items.setdefault(
            ref,
            "send the supplier's corrected bill"
            if issue.status == "awaiting_supplier"
            else "answer the question",
        )
    return items


def ca_items(s: Session, shop_ids: list[uuid.UUID]) -> dict[str, str]:
    items: dict[str, str] = {}
    for rr, ref in s.execute(
        select(ReviewRequest, Invoice.case_ref)
        .join(Invoice, Invoice.id == ReviewRequest.invoice_id)
        .where(ReviewRequest.shop_id.in_(shop_ids), ReviewRequest.status == "open")
        .order_by(ReviewRequest.public_ref)
    ).all():
        items[rr.public_ref] = f"decide {ref}"
    return items


def schedule_due(s: Session, now_utc: datetime | None = None) -> int:
    """Enqueue today's digest for every room whose local digest time has passed. Idempotent per day."""
    settings = get_settings()
    now = now_utc or utcnow()
    queued = 0
    for room in s.execute(
        select(RoomBinding).where(
            RoomBinding.active.is_(True),
            RoomBinding.purpose.in_(("shop_intake", "ca_review")),
            RoomBinding.environment == settings.ENVIRONMENT,
        )
    ).scalars():
        shops = shops_of_room(s, room.id)
        if not shops:
            continue
        shop = s.get(Shop, shops[0])
        assert shop is not None
        local = now.astimezone(ZoneInfo(shop.timezone or settings.DEFAULT_TZ))
        if local.time() < _hm(settings.DIGEST_LOCAL_TIME) or in_quiet_hours(local):
            continue
        day = local.date().isoformat()
        key = f"digest:{room.id}:{day}"
        if s.execute(select(Job.id).where(Job.dedupe_key == key)).first() is not None:
            continue
        grant = issue_grant(
            s, operation="notify", practice_id=shop.practice_id, shop_id=shop.id, scheduled=True
        )
        if enqueue(
            s,
            type="daily_digest",
            lane="fast",
            payload={"room_binding_id": str(room.id), "local_date": day},
            dedupe_key=key,
            correlation_id=f"digest-{day}",
            grant_id=grant.grant_id,
        ):
            queued += 1
    return queued


def run_digest(s: Session, room_id: uuid.UUID, day: str, correlation_id: str) -> None:
    settings = get_settings()
    room = s.get(RoomBinding, room_id)
    if (
        room is None
        or s.execute(
            select(DigestRun).where(DigestRun.room_binding_id == room_id, DigestRun.local_date == day)
        ).scalar_one_or_none()
    ):
        return
    shops = shops_of_room(s, room.id)
    items = owner_items(s, shops[0]) if room.purpose == "shop_intake" else ca_items(s, shops)
    previous = list(
        s.execute(
            select(DigestRun)
            .where(DigestRun.room_binding_id == room_id, DigestRun.local_date < day)
            .order_by(DigestRun.local_date.desc())
            .limit(settings.DIGEST_ESCALATE_AFTER)
        ).scalars()
    )
    escalate: list[str] = []
    if room.purpose == "shop_intake" and len(previous) >= settings.DIGEST_ESCALATE_AFTER:
        already = {ref for run in previous for ref in run.escalated}
        escalate = [ref for ref in items if all(ref in run.items for run in previous) and ref not in already]
    s.add(DigestRun(room_binding_id=room_id, local_date=day, items=sorted(items), escalated=escalate))
    if items:
        who = "Pending for you" if room.purpose == "shop_intake" else "Open review requests"
        body = f"Daily digest {day}. {who}:\n" + "\n".join(f"• {ref}: {what}" for ref, what in items.items())
        post(s, room, action_id=f"digest:{room.id}:{day}", body=body, correlation_id=correlation_id)
    if escalate:
        ca_room = room_for_shop(s, shops[0], "ca_review")
        shop = s.get(Shop, shops[0])
        if ca_room is not None and shop is not None:
            post(
                s,
                ca_room,
                action_id=f"escalation:{room.id}:{day}",
                body=f"Escalation: {shop.name} has not answered {', '.join(escalate)} after "
                f"{settings.DIGEST_ESCALATE_AFTER} daily digests.",
                correlation_id=correlation_id,
            )
