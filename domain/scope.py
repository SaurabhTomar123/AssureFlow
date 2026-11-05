"""Authorization reads only memberships and assignments, never room membership (spec section 6)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.models import CaAssignment, ShopMembership, User, utcnow


def is_owner_of(s: Session, user_id: uuid.UUID, shop_id: uuid.UUID) -> bool:
    row = s.execute(
        select(ShopMembership).where(
            ShopMembership.user_id == user_id,
            ShopMembership.shop_id == shop_id,
            ShopMembership.revoked_at.is_(None),
        )
    ).scalar_one_or_none()
    return row is not None


def is_assigned_ca(s: Session, user_id: uuid.UUID, shop_id: uuid.UUID, at: datetime | None = None) -> bool:
    now = at or utcnow()
    rows = s.execute(
        select(CaAssignment).where(CaAssignment.ca_user_id == user_id, CaAssignment.shop_id == shop_id)
    ).scalars()
    return any(r.effective_from <= now and (r.effective_to is None or r.effective_to > now) for r in rows)


def can_read_shop(s: Session, user_id: uuid.UUID, shop_id: uuid.UUID) -> bool:
    return is_owner_of(s, user_id, shop_id) or is_assigned_ca(s, user_id, shop_id)


def user_role(s: Session, user_id: uuid.UUID) -> str:
    return s.get(User, user_id).role  # type: ignore[union-attr]
