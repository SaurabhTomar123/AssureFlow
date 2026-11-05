"""Room disclosure rule (spec section 2, G-06).

Anything posted in a room must be information every current member may access at delivery time.
The outbox rechecks the declared audience immediately before each send.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.models import RoomBinding, RoomMember, User
from domain.scope import is_assigned_ca, is_owner_of
from domain.services.base import shops_of_room


def unauthorized_members(s: Session, room: RoomBinding) -> list[uuid.UUID]:
    shops = shops_of_room(s, room.id)
    members = s.execute(
        select(RoomMember.user_id).where(
            RoomMember.room_binding_id == room.id, RoomMember.removed_at.is_(None)
        )
    ).scalars()
    bad: list[uuid.UUID] = []
    for user_id in members:
        user = s.get(User, user_id)
        if user is None:
            bad.append(user_id)
            continue
        if room.purpose == "shop_intake":
            ok = all(is_owner_of(s, user_id, shop) or is_assigned_ca(s, user_id, shop) for shop in shops)
        elif room.purpose in ("ca_review", "practice_home"):
            ok = user.role in ("ca", "practice_staff") and all(
                is_assigned_ca(s, user_id, shop) for shop in shops
            )
        elif room.purpose == "operations":
            ok = user.role == "operator"
        else:
            ok = user.role == "developer"
        if not ok:
            bad.append(user_id)
    return bad


def audience_ok(s: Session, room: RoomBinding) -> bool:
    return room.active and not unauthorized_members(s, room)
