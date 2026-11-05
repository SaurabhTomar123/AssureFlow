"""Operator commands. Run: python -m scripts.admin <command>

register-agent        Register the assure-flow integration agent in Switch (needs SWITCH_REGISTRATION_KEY)
bind-rooms            Match Switch rooms the agent belongs to against agents/rooms.yaml by name
unmapped              List senders whose events were rejected (to bind their identities)
bind-user SENDER HANDLE   Map a Switch participant id to a seeded user (verified identity)
revoke-user HANDLE    Revoke a user's chat identity and grants (removes their authority)
health                Print the operator health report
"""

from __future__ import annotations

import os
import sys

import httpx
import yaml
from sqlalchemy import select, update

from adapters.switch_client import SwitchCredentials, SwitchHttp, new_connection_id
from common.db import transaction
from common.settings import get_settings
from domain import models as m
from domain.context import revoke_grants
from domain.models import utcnow

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


def bind_rooms() -> None:
    settings = get_settings()
    rooms = SwitchHttp(SwitchCredentials.load()).op("list_rooms") or []
    by_name = {str(r.get("name")): str(r.get("room_id") or r.get("id")) for r in rooms}
    config = yaml.safe_load(open(settings.ROOM_BINDINGS_FILE, encoding="utf-8"))
    with transaction() as s:
        for room in config["rooms"]:
            if not room.get("provision"):
                continue
            binding = s.execute(select(m.RoomBinding).where(m.RoomBinding.name == room["name"])).scalar_one()
            switch_id = by_name.get(room["name"])
            if switch_id is None:
                print(f"MISSING  {room['name']}: create it in Switch and invite @{AGENT_NAME}")
                continue
            binding.switch_room_id = switch_id
            print(f"BOUND    {room['name']} -> {switch_id}")


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


def bind_user(sender: str, handle: str) -> None:
    with transaction() as s:
        user = s.execute(select(m.User).where(m.User.handle == handle)).scalar_one()
        s.add(
            m.ChatIdentity(
                practice_id=user.practice_id, platform="switch", platform_user_id=sender, user_id=user.id
            )
        )
    print(f"bound {sender} -> {handle}")


def revoke_user(handle: str) -> None:
    with transaction() as s:
        user = s.execute(select(m.User).where(m.User.handle == handle)).scalar_one()
        s.execute(update(m.ChatIdentity).where(m.ChatIdentity.user_id == user.id).values(revoked_at=utcnow()))
        count = revoke_grants(s, "identity_revoked", user_id=user.id)
    print(f"revoked {handle}; {count} grant(s) revoked")


def main(argv: list[str]) -> None:
    if not argv:
        print(__doc__)
        return
    cmd, args = argv[0], argv[1:]
    if cmd == "register-agent":
        register_agent()
    elif cmd == "bind-rooms":
        bind_rooms()
    elif cmd == "unmapped":
        unmapped()
    elif cmd == "bind-user" and len(args) == 2:
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
