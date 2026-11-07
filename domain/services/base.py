"""Shared transactional helpers: audit, outbox, case events, period versions, room lookup.

Everything here writes inside the caller's transaction (G-11: domain change + case event + audit +
outbox/job insert commit together).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from common.settings import get_settings
from domain.models import (
    AuditEvent,
    CaseEvent,
    Invoice,
    Outbox,
    RoomBinding,
    RoomBindingShop,
    Shop,
    ShopPeriodVersion,
    utcnow,
)

UNASSIGNED = "UNASSIGNED"


def audit(
    s: Session,
    *,
    action: str,
    entity: str,
    outcome: str,
    actor: str,
    request_id: str,
    entity_id: str | None = None,
    practice_id: uuid.UUID | None = None,
    shop_id: uuid.UUID | None = None,
    context_id: uuid.UUID | None = None,
    grant_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    s.add(
        AuditEvent(
            environment=get_settings().ENVIRONMENT,
            practice_id=practice_id,
            shop_id=shop_id,
            actor=actor,
            request_context_id=context_id,
            grant_id=grant_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            before=before,
            after=after,
            outcome=outcome,
            request_id=request_id,
        )
    )


def post(
    s: Session,
    room: RoomBinding,
    *,
    action_id: str,
    body: str,
    correlation_id: str,
    case_ref: str | None = None,
    kind: str = "text",
    attachments: list[str] | None = None,
    supersedes: str | None = None,
) -> None:
    """One logical outbox record per (action_id, destination), ordered per destination (G-12)."""
    s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:d))"), {"d": room.switch_room_id})
    next_seq = (
        s.execute(
            select(func.coalesce(func.max(Outbox.seq), 0)).where(Outbox.destination == room.switch_room_id)
        ).scalar_one()
        + 1
    )
    s.execute(
        insert(Outbox)
        .values(
            id=uuid.uuid4(),
            action_id=action_id,
            destination=room.switch_room_id,
            room_binding_id=room.id,
            seq=next_seq,
            body=body,
            case_ref=case_ref,
            kind=kind,
            attachments=attachments or [],
            supersedes_action_id=supersedes,
            correlation_id=correlation_id,
        )
        .on_conflict_do_nothing(index_elements=["action_id", "destination"])
    )


def case_event(
    s: Session,
    case: Invoice,
    type: str,
    correlation_id: str,
    payload: dict[str, Any] | None = None,
    *,
    context_id: uuid.UUID | None = None,
    grant_id: uuid.UUID | None = None,
) -> None:
    case.event_seq += 1
    case.updated_at = utcnow()
    s.add(
        CaseEvent(
            practice_id=case.practice_id,
            shop_id=case.shop_id,
            case_id=case.id,
            seq=case.event_seq,
            type=type,
            payload=payload or {},
            request_context_id=context_id,
            grant_id=grant_id,
            correlation_id=correlation_id,
        )
    )
    bump_period(s, case.shop_id, case.period or UNASSIGNED)


def bump_period(s: Session, shop_id: uuid.UUID, period: str, correlation_id: str = "") -> None:
    """Consistency token: incremented in every transaction that changes a case in that period.

    An approved pack for that month is labelled superseded (compensation notice, once)."""
    if period != UNASSIGNED:
        from domain.services.compensation import packs_outdated

        packs_outdated(s, shop_id, period, correlation_id or "period-change")
    s.execute(
        insert(ShopPeriodVersion)
        .values(shop_id=shop_id, period=period, version=1, updated_at=utcnow())
        .on_conflict_do_update(
            index_elements=["shop_id", "period"],
            set_={"version": ShopPeriodVersion.version + 1, "updated_at": utcnow()},
        )
    )


def period_version(s: Session, shop_id: uuid.UUID, period: str, lock: bool = False) -> int:
    query = select(ShopPeriodVersion).where(
        ShopPeriodVersion.shop_id == shop_id, ShopPeriodVersion.period == period
    )
    if lock:
        query = query.with_for_update()
    row = s.execute(query).scalar_one_or_none()
    return row.version if row else 0


def room_for_shop(s: Session, shop_id: uuid.UUID, purpose: str) -> RoomBinding | None:
    return s.execute(
        select(RoomBinding)
        .join(RoomBindingShop, RoomBindingShop.room_binding_id == RoomBinding.id)
        .where(
            RoomBindingShop.shop_id == shop_id,
            RoomBinding.purpose == purpose,
            RoomBinding.active.is_(True),
            RoomBinding.environment == get_settings().ENVIRONMENT,
        )
        .order_by(RoomBinding.created_at)
        .limit(1)
    ).scalar_one_or_none()


def review_room(s: Session, shop_id: uuid.UUID) -> RoomBinding | None:
    """Where review requests go: the shop's own group when it opted in to shared review (D-31)."""
    shop = s.get(Shop, shop_id)
    if shop is not None and shop.shared_review:
        room = room_for_shop(s, shop_id, "shop_intake")
        if room is not None:
            return room
    return room_for_shop(s, shop_id, "ca_review")


def shops_of_room(s: Session, room_binding_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        s.execute(
            select(RoomBindingShop.shop_id).where(RoomBindingShop.room_binding_id == room_binding_id)
        ).scalars()
    )
