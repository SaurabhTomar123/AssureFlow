"""Ordered outbox delivery per room (spec section 2).

The next row of a destination is sent only after the previous one is delivered, withheld or dead.
The audience is rechecked immediately before each send (G-06). Transport is at-least-once and every
retry carries the same action id. No transaction or row lock is held during the network call (G-11).
"""

from __future__ import annotations

import uuid

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from adapters.storage import LocalStorage
from adapters.switch_client import get_switch
from common.db import transaction
from common.logging import get_logger
from common.settings import get_settings
from domain.models import Artifact, Outbox, RoomBinding, Snapshot, utcnow
from domain.services.base import audit, post
from domain.services.disclosure import audience_ok, unauthorized_live, unauthorized_members
from domain.services.operations import ops_alert

log = get_logger("outbox")


def _heads(s: Session) -> list[Outbox]:
    first = (
        select(Outbox.destination, func.min(Outbox.seq).label("seq"))
        .where(Outbox.status == "pending")
        .group_by(Outbox.destination)
        .subquery()
    )
    return list(
        s.execute(
            select(Outbox).join(
                first, (Outbox.destination == first.c.destination) & (Outbox.seq == first.c.seq)
            )
        ).scalars()
    )


def _report_dead(s: Session, row: Outbox) -> None:
    """A message that can never be sent must be visible; a file gets a recovery note in its own room."""
    room = s.get(RoomBinding, row.room_binding_id)
    assert room is not None
    log.error("outbox.dead", room=room.name, action_id=row.action_id, error=row.last_error)
    if room.purpose != "operations":
        ops_alert(
            s,
            room.practice_id,
            f"dead:{row.id}",
            f"message {row.action_id.split(':')[0]} to {room.name} could not be sent: {row.last_error}.",
            row.correlation_id,
        )
    if row.kind != "files":
        return
    artifacts = [s.get(Artifact, uuid.UUID(a)) for a in row.attachments]
    names = ", ".join(a.filename for a in artifacts if a is not None)
    snapshot_ids = {a.snapshot_id for a in artifacts if a is not None and a.snapshot_id is not None}
    snapshot = s.get(Snapshot, next(iter(snapshot_ids))) if snapshot_ids else None
    recovery = f" Reply `resend {snapshot.public_ref}` to try again." if snapshot is not None else ""
    post(
        s,
        room,
        action_id=f"failed:{row.id}",
        body=f"I couldn't send {names}. The stored file is unchanged.{recovery}",
        correlation_id=row.correlation_id,
    )


def dispatch_once() -> int:
    """Send the head row of every destination once. Returns the number of rows delivered."""
    settings = get_settings()
    delivered = 0
    with transaction() as s:
        heads = [(row.id, row.room_binding_id) for row in _heads(s)]
    for row_id, room_id in heads:
        with transaction() as s:
            row = s.get(Outbox, row_id)
            room = s.get(RoomBinding, room_id)
            assert row is not None and room is not None
            if row.status != "pending":
                continue
            if row.audience_check == "required" and not audience_ok(s, room):
                row.status = "withheld"
                row.last_error = "audience check failed"
                audit(
                    s,
                    action="outbox.withheld",
                    entity="outbox",
                    entity_id=row.action_id,
                    outcome="withheld",
                    actor="outbox",
                    request_id=row.correlation_id,
                    practice_id=room.practice_id,
                    after={
                        "room": room.name,
                        "unauthorized_members": [str(u) for u in unauthorized_members(s, room)],
                    },
                )
                log.warning("outbox.withheld", room=room.name, action_id=row.action_id)
                if room.purpose != "operations":
                    ops_alert(
                        s,
                        room.practice_id,
                        f"withheld:{row.id}",
                        f"message {row.action_id.split(':')[0]} to {room.name} withheld: room audience failed the "
                        "disclosure check. Fix membership or assignments, then resend.",
                        row.correlation_id,
                    )
                continue
            kind, body, destination, audience = row.kind, row.body, row.destination, row.audience_check
            files: list[tuple[str, bytes, str]] = []
            if kind == "files":
                storage = LocalStorage()
                for artifact_id in row.attachments:
                    art = s.get(Artifact, uuid.UUID(artifact_id))
                    assert art is not None
                    mime = (
                        "application/json"
                        if art.kind == "json"
                        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    files.append((art.filename, storage.get(art.storage_key), mime))
        if settings.LIVE_MEMBER_CHECK and audience == "required" and not destination.startswith("unbound:"):
            try:
                live = get_switch().room_members(destination)
            except (httpx.HTTPError, OSError):
                continue
            if live is not None:
                with transaction() as s:
                    room = s.get(RoomBinding, room_id)
                    assert room is not None
                    bad = unauthorized_live(s, room, live)
                    if bad:
                        row = s.get(Outbox, row_id)
                        assert row is not None
                        row.status, row.last_error = "withheld", "live member check failed"
                        audit(
                            s,
                            action="outbox.withheld",
                            entity="outbox",
                            entity_id=row.action_id,
                            outcome="withheld",
                            actor="outbox",
                            request_id=row.correlation_id,
                            practice_id=room.practice_id,
                            after={"room": room.name, "live_members": bad},
                        )
                        if room.purpose != "operations":
                            ops_alert(
                                s,
                                room.practice_id,
                                f"withheld-live:{row.id}",
                                f"message to {room.name} withheld: unexpected live member(s) "
                                f"{', '.join(bad)}.",
                                row.correlation_id,
                            )
                        continue
        try:
            port = get_switch()
            event_id = (
                port.upload_files(destination, files, body)
                if kind == "files"
                else port.post_message(destination, body)
            )
        except (httpx.HTTPError, OSError) as exc:
            with transaction() as s:
                row = s.get(Outbox, row_id)
                assert row is not None
                row.transport_attempts += 1
                row.last_error = type(exc).__name__
                if row.transport_attempts >= settings.OUTBOX_MAX_ATTEMPTS:
                    row.status = "dead"
                    _report_dead(s, row)
            continue
        with transaction() as s:
            row = s.get(Outbox, row_id)
            assert row is not None
            row.transport_attempts += 1
            row.status = "delivered"
            row.delivered_event_id = event_id
            row.delivered_at = utcnow()
            delivered += 1
    return delivered
