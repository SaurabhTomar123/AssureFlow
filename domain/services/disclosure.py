"""Room disclosure rule (spec section 2, G-06).

Anything posted in a room must be information every current member may access at delivery time.
The outbox rechecks the declared audience immediately before each send.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from common.settings import get_settings
from domain.models import ChatIdentity, RoomBinding, RoomMember, User
from domain.scope import has_capability, is_assigned_ca, is_owner_of
from domain.services.base import shops_of_room


def _authorized(s: Session, room: RoomBinding, user: User, shops: list[uuid.UUID]) -> bool:
    if room.purpose == "shop_intake":
        return all(
            is_owner_of(s, user.id, shop)
            or is_assigned_ca(s, user.id, shop)
            or has_capability(s, user.id, shop, "invoice_view")
            for shop in shops
        )
    if room.purpose == "delivery":
        # Receivers see item names and quantities only; never invoice prices or tax details (U2 section 3).
        return all(
            is_owner_of(s, user.id, shop) or has_capability(s, user.id, shop, "delivery_confirm") for shop in shops
        )
    if room.purpose == "submission":
        # Only "received" notes are posted here, never case details (D-32).
        return all(
            is_owner_of(s, user.id, shop) or has_capability(s, user.id, shop, "invoice_submit") for shop in shops
        )
    if room.purpose in ("ca_review", "practice_home"):
        return user.role in ("ca", "practice_staff") and all(
            is_assigned_ca(s, user.id, shop) for shop in shops
        )
    if room.purpose == "operations":
        return user.role == "operator"
    return user.role == "developer"


def unauthorized_live(s: Session, room: RoomBinding, usernames: list[str]) -> list[str]:
    """Check Switch's live member list: every person must map to one authorized identity or be trusted.

    Switch 0.31.0 reports display names only, so a pass means "no known unauthorized member", not a verified
    audience. A name is not an identity: one that matches no one, several people or another practice fails closed.
    """
    trusted = set(get_settings().SWITCH_TRUSTED_USERNAMES)
    shops = shops_of_room(s, room.id)
    bad: list[str] = []
    for name in usernames:
        if name in trusted:
            continue
        identities = list(
            s.execute(
                select(ChatIdentity).where(ChatIdentity.chat_username == name, ChatIdentity.revoked_at.is_(None))
            ).scalars()
        )
        user_ids = {i.user_id for i in identities}
        if len(user_ids) != 1 or any(i.practice_id != room.practice_id for i in identities):
            bad.append(name)
            continue
        user = s.get(User, identities[0].user_id)
        if user is None or not _authorized(s, room, user, shops):
            bad.append(name)
    return bad


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
        ok = _authorized(s, room, user, shops)
        if not ok:
            bad.append(user_id)
    return bad


def audience_ok(s: Session, room: RoomBinding) -> bool:
    return room.active and not unauthorized_members(s, room)
