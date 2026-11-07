"""Operator commands. Run: python -m scripts.admin <command>

register-agent        Register the assure-flow integration agent in Switch (needs SWITCH_REGISTRATION_KEY)
create-rooms HANDLE=CHATUSER ...   Agent creates the provisioned rooms in Switch, then binds them
bind-rooms [--prefix P] [--force]   Match Switch rooms the agent belongs to against agents/rooms.yaml by name.
                      Rooms adopted from Telegram are named "<connection>: <group title>"; pass
                      --prefix "Telegram: " to bind those (otherwise a unique ": <name>" suffix matches).
                      A room moved with rebind-room is kept unless --force is given.
rebind-room NAME SWITCH_ROOM_ID REASON...   Move a logical room to another Switch room (recovery, audited).
                      The old room and its messages are left as they are.
unmapped              List senders whose events were rejected (to bind their identities)
bind-user SENDER HANDLE [CHATUSER]   Map a Switch participant id (and chat username) to a seeded user
revoke-user HANDLE    Revoke a user's chat identity and grants (removes their authority)
shared-review SHOP on|off   Let the CA review inside the shop's own group, as well as the private room (D-31)
add-client SHOP HANDLE NAME...   Add a client and the shop's submission room to an existing database (D-32).
                      Then use rebind-room af-submit-<shop> <switch-room-id> <reason> and bind-user.
health                Print the operator health report
"""

from __future__ import annotations

import os
import sys
import uuid

import httpx
import yaml
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from adapters.switch_client import SwitchCredentials, SwitchHttp, new_connection_id
from common.db import transaction
from common.settings import get_settings
from domain import models as m
from domain.context import revoke_grants
from domain.models import utcnow
from domain.services.base import audit
from domain.services.disclosure import unauthorized_live

AGENT_NAME = "assure-flow"


def register_agent() -> None:
    settings = get_settings()
    key = os.environ.get("SWITCH_REGISTRATION_KEY", "")
    if not key:
        raise SystemExit("Set SWITCH_REGISTRATION_KEY to a registration API key from the Switch Gateway.")
    body = {
        "name": AGENT_NAME,
        "display_name": "Assure Flow",
        "description": "Evidence-backed GST purchase review: receipts, checks, CA review and monthly packs.",
        "connector_type": "assure-flow",
        "integration_profile": {
            "connection_model": "always_on",
            "message_exchange": True,
            "pre_invocation_mediation": [],
            "post_invocation_mediation": [],
            "event_reporting": [],
        },
    }
    resp = httpx.post(
        f"{settings.SWITCH_BASE_URL}/agents",
        json=body,
        headers={"Authorization": f"Bearer {key}"},
        timeout=settings.SWITCH_HTTP_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = resp.json()
    creds = SwitchCredentials(agent_id=data["id"], api_key=data["api_key"], connection_id=new_connection_id())
    creds.save()
    SwitchHttp(creds).op("update_agent_detail", {"agent_id": creds.agent_id, "addressing": "anyone"})
    print(
        f"registered agent {AGENT_NAME} ({creds.agent_id}); credentials saved to {settings.SWITCH_CREDENTIALS_FILE}"
    )


def _match_room(by_name: dict[str, str], name: str, prefix: str | None) -> tuple[str | None, list[str]]:
    """Find the Switch room for a configured room name. Returns (room id, ambiguous candidates)."""
    if prefix is not None:
        return by_name.get(prefix + name), []
    if name in by_name:
        return by_name[name], []
    suffixed = [n for n in by_name if n.endswith(": " + name)]
    if len(suffixed) == 1:
        return by_name[suffixed[0]], []
    return None, suffixed


def bind_rooms(prefix: str | None = None, force: bool = False) -> None:
    settings = get_settings()
    rooms = SwitchHttp(SwitchCredentials.load()).op("list_rooms") or []
    by_name = {str(r.get("name")): str(r.get("room_id") or r.get("id")) for r in rooms}
    config = yaml.safe_load(open(settings.ROOM_BINDINGS_FILE, encoding="utf-8"))
    with transaction() as s:
        for room in config["rooms"]:
            if not room.get("provision"):
                continue
            binding = s.execute(select(m.RoomBinding).where(m.RoomBinding.name == room["name"])).scalar_one_or_none()
            if binding is None:
                print(f"SKIPPED  {room['name']}: not in this database (see add-client)")
                continue
            if not force and _was_rebound(s, room["name"]):
                print(f"KEPT     {room['name']}: moved with rebind-room; use --force to replace it")
                continue
            switch_id, candidates = _match_room(by_name, room["name"], prefix)
            if switch_id is None:
                if candidates:
                    print(f"AMBIGUOUS {room['name']}: {', '.join(candidates)}; rerun with --prefix")
                else:
                    print(f"MISSING  {room['name']}: create it in Switch and invite @{AGENT_NAME}")
                continue
            binding.switch_room_id = switch_id
            print(f"BOUND    {room['name']} -> {switch_id}")


def _was_rebound(s: Session, name: str) -> bool:
    return (
        s.execute(
            select(m.AuditEvent.id).where(m.AuditEvent.action == "room.rebound", m.AuditEvent.entity_id == name).limit(1)
        ).first()
        is not None
    )


def rebind_room(name: str, switch_id: str, reason: str, http: SwitchHttp | None = None) -> None:
    """Point a logical room at another Switch room. Withheld messages stay withheld in the old room."""
    settings = get_settings()
    http = http or SwitchHttp(SwitchCredentials.load())
    rooms = {str(r.get("room_id") or r.get("id")) for r in http.op("list_rooms") or []}
    if switch_id not in rooms:
        raise SystemExit(f"The agent is not in Switch room {switch_id}. Invite it first.")
    members = http.room_members(switch_id) or []
    with transaction() as s:
        binding = s.execute(
            select(m.RoomBinding).where(m.RoomBinding.name == name, m.RoomBinding.environment == settings.ENVIRONMENT)
        ).scalar_one_or_none()
        if binding is None:
            raise SystemExit(f"No room binding named {name}.")
        taken = s.execute(
            select(m.RoomBinding.name).where(
                m.RoomBinding.switch_room_id == switch_id,
                m.RoomBinding.environment == settings.ENVIRONMENT,
                m.RoomBinding.id != binding.id,
            )
        ).scalar_one_or_none()
        if taken is not None:
            raise SystemExit(f"Switch room {switch_id} is already bound to {taken}.")
        old = binding.switch_room_id
        binding.switch_room_id = switch_id
        unexpected = unauthorized_live(s, binding, members)
        audit(
            s,
            action="room.rebound",
            entity="room_binding",
            entity_id=name,
            outcome="permitted",
            actor="operator",
            request_id=uuid.uuid4().hex,
            practice_id=binding.practice_id,
            before={"switch_room_id": old},
            after={"switch_room_id": switch_id, "reason": reason, "members": members},
        )
    print(f"REBOUND  {name}: {old} -> {switch_id}")
    if unexpected:
        print(f"WARNING  replies will be withheld until these members leave: {', '.join(unexpected)}")


def create_rooms(mapping: dict[str, str]) -> None:
    settings = get_settings()
    http = SwitchHttp(SwitchCredentials.load())
    existing = {str(r.get("name")) for r in http.op("list_rooms") or []}
    config = yaml.safe_load(open(settings.ROOM_BINDINGS_FILE, encoding="utf-8"))
    for room in config["rooms"]:
        if not room.get("provision") or room["name"] in existing:
            continue
        users = [mapping[h] for h in room["members"] if h in mapping]
        http.op(
            "create_room",
            {
                "name": room["name"],
                "description": f"Assure Flow {room['purpose'].replace('_', ' ')} room (synthetic demo data)",
                "agent_names": [AGENT_NAME],
                "user_names": users,
            },
        )
        print(f"CREATED  {room['name']} with {', '.join(users) or 'no users'}")
    bind_rooms()


def unmapped() -> None:
    with transaction() as s:
        rows = s.execute(
            select(m.InboxEvent.sender_ref, m.InboxEvent.switch_room_id)
            .where(
                m.InboxEvent.outcome.in_(("rejected", "ignored")),
                m.InboxEvent.outcome_reason.in_(("unmapped_sender", "chatter")),
            )
            .distinct()
        ).all()
        mapped = set(s.execute(select(m.ChatIdentity.platform_user_id)).scalars())
    for sender, room in rows:
        if sender not in mapped:
            print(f"{sender}\t(in {room})")


def bind_user(sender: str, handle: str, username: str | None = None) -> None:
    with transaction() as s:
        user = s.execute(select(m.User).where(m.User.handle == handle)).scalar_one()
        s.add(
            m.ChatIdentity(
                practice_id=user.practice_id,
                platform="switch",
                platform_user_id=sender,
                chat_username=username,
                user_id=user.id,
            )
        )
    print(f"bound {sender} -> {handle}")


def revoke_user(handle: str) -> None:
    with transaction() as s:
        user = s.execute(select(m.User).where(m.User.handle == handle)).scalar_one()
        s.execute(update(m.ChatIdentity).where(m.ChatIdentity.user_id == user.id).values(revoked_at=utcnow()))
        count = revoke_grants(s, "identity_revoked", user_id=user.id)
    print(f"revoked {handle}; {count} grant(s) revoked")


def add_client(code: str, handle: str, name: str) -> None:
    """Idempotent: one client user with invoice_submit, and the shop's submission room, unbound until rebound."""
    settings = get_settings()
    with transaction() as s:
        shop = s.execute(select(m.Shop).where(m.Shop.code == code)).scalar_one_or_none()
        if shop is None:
            raise SystemExit(f"No shop {code}.")
        user = s.execute(select(m.User).where(m.User.handle == handle)).scalar_one_or_none()
        if user is None:
            user = m.User(practice_id=shop.practice_id, handle=handle, display_name=name, role="client")
            s.add(user)
            s.flush()
        if user.role != "client":
            raise SystemExit(f"{handle} already exists with role {user.role}.")
        if not s.execute(
            select(m.ShopCapability).where(
                m.ShopCapability.user_id == user.id,
                m.ShopCapability.shop_id == shop.id,
                m.ShopCapability.capability == "invoice_submit",
            )
        ).first():
            s.add(
                m.ShopCapability(
                    practice_id=shop.practice_id, shop_id=shop.id, user_id=user.id, capability="invoice_submit"
                )
            )
        room_name = f"af-submit-{code}"
        binding = s.execute(
            select(m.RoomBinding).where(m.RoomBinding.name == room_name, m.RoomBinding.environment == settings.ENVIRONMENT)
        ).scalar_one_or_none()
        if binding is None:
            binding = m.RoomBinding(
                environment=settings.ENVIRONMENT,
                practice_id=shop.practice_id,
                name=room_name,
                switch_room_id=f"unbound:{room_name}",
                purpose="submission",
                human_roles=["client"],
                permitted_agent_senders=[],
                agent_roles_and_tools={},
                config_version="1",
            )
            s.add(binding)
            s.flush()
            s.add(m.RoomBindingShop(room_binding_id=binding.id, shop_id=shop.id))
        if not s.execute(
            select(m.RoomMember).where(m.RoomMember.room_binding_id == binding.id, m.RoomMember.user_id == user.id)
        ).first():
            s.add(m.RoomMember(room_binding_id=binding.id, user_id=user.id))
        audit(
            s,
            action="client.added",
            entity="user",
            entity_id=handle,
            outcome="permitted",
            actor="operator",
            request_id=uuid.uuid4().hex,
            practice_id=shop.practice_id,
            shop_id=shop.id,
            after={"room": room_name},
        )
    print(f"{handle} can send bills to {room_name}. Bind the room with rebind-room and the person with bind-user.")


def shared_review(code: str, state: str) -> None:
    """Turn shared review on for a shop. The CA must also be a member of the shop's chat group."""
    with transaction() as s:
        shop = s.execute(select(m.Shop).where(m.Shop.code == code)).scalar_one_or_none()
        if shop is None:
            raise SystemExit(f"No shop {code}.")
        shop.shared_review = state == "on"
        audit(
            s,
            action="shop.shared_review",
            entity="shop",
            entity_id=code,
            outcome="permitted",
            actor="operator",
            request_id=uuid.uuid4().hex,
            practice_id=shop.practice_id,
            shop_id=shop.id,
            after={"shared_review": shop.shared_review},
        )
    print(f"{code}: shared review {state}. Owner and CA can now work in the shop group.")


def main(argv: list[str]) -> None:
    if not argv:
        print(__doc__)
        return
    cmd, args = argv[0], argv[1:]
    if cmd == "register-agent":
        register_agent()
    elif cmd == "create-rooms":
        create_rooms(dict(a.split("=", 1) for a in args))
    elif cmd == "bind-rooms":
        force = "--force" in args
        rest = [a for a in args if a != "--force"]
        if rest and (len(rest) != 2 or rest[0] != "--prefix"):
            print(__doc__)
            sys.exit(2)
        bind_rooms(rest[1] if rest else None, force)
    elif cmd == "rebind-room" and len(args) >= 3:
        rebind_room(args[0], args[1], " ".join(args[2:]))
    elif cmd == "add-client" and len(args) >= 3:
        add_client(args[0], args[1], " ".join(args[2:]))
    elif cmd == "shared-review" and len(args) == 2 and args[1] in ("on", "off"):
        shared_review(args[0], args[1])
    elif cmd == "unmapped":
        unmapped()
    elif cmd == "bind-user" and len(args) in (2, 3):
        bind_user(*args)
    elif cmd == "revoke-user" and len(args) == 1:
        revoke_user(args[0])
    elif cmd == "health":
        from scripts.health import main as health

        health()
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv[1:])
