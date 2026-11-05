"""Durable inbox writes for the Switch adapter (spec section 2, durable inbox).

Every event from the agent's rooms is written to inbox_events, with its process_inbox_event job and the
adapter cursor, in one transaction. Only after commit does the cursor reported to Switch advance.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from adapters.switch_client import event_key, payload_hash
from common.db import transaction
from domain.models import AdapterState, InboxEvent, utcnow
from workers.queue import enqueue

ADAPTER_KEY = "switch"


def record_event(data: dict[str, Any], sequence: int, connection_id: str, bridge_id: str = "switch") -> bool:
    """Insert the event (idempotent on (bridge_id, event_id)). Returns True when it was new."""
    payload = data.get("payload") or {}
    kind = str(data.get("type") or "message")
    with transaction() as s:
        event_id = event_key(data)
        correlation_id = uuid.uuid4().hex
        inserted = s.execute(
            insert(InboxEvent)
            .values(
                id=uuid.uuid4(),
                bridge_id=bridge_id,
                event_id=event_id,
                switch_room_id=str(data.get("room_id") or ""),
                sender_ref=str(
                    payload.get("sender") or payload.get("user_id") or payload.get("member") or ""
                ),
                addressed_agent="assure-flow" if payload.get("addressed") else None,
                kind=kind,
                thread_id=payload.get("thread_id"),
                body=str(payload.get("body") or "")
                if kind == "message"
                else str(payload.get("command") or ""),
                attachments=list(payload.get("attachments") or []),
                payload_hash=payload_hash(data),
                sequence=sequence or None,
                correlation_id=correlation_id,
            )
            .on_conflict_do_nothing(index_elements=["bridge_id", "event_id"])
            .returning(InboxEvent.id)
        ).scalar_one_or_none()
        if inserted is not None:
            enqueue(
                s,
                type="process_inbox_event",
                lane="fast",
                payload={"inbox_event_id": str(inserted)},
                dedupe_key=f"inbox:{inserted}",
                correlation_id=correlation_id,
            )
        if sequence:
            save_cursor(s, connection_id, sequence)
        return inserted is not None


def save_cursor(s: Any, connection_id: str, sequence: int, generation: int | None = None) -> None:
    s.execute(
        insert(AdapterState)
        .values(
            key=ADAPTER_KEY,
            connection_id=connection_id,
            cursor=sequence,
            generation=generation,
            updated_at=utcnow(),
        )
        .on_conflict_do_update(
            index_elements=["key"],
            set_={"cursor": sequence, "updated_at": utcnow()},
            where=AdapterState.cursor < sequence,
        )
    )


def load_cursor() -> tuple[int, int | None]:
    with transaction() as s:
        row = s.execute(select(AdapterState).where(AdapterState.key == ADAPTER_KEY)).scalar_one_or_none()
        return (row.cursor, row.generation) if row else (0, None)


def save_generation(connection_id: str, generation: int | None) -> None:
    with transaction() as s:
        s.execute(
            insert(AdapterState)
            .values(
                key=ADAPTER_KEY,
                connection_id=connection_id,
                cursor=0,
                generation=generation,
                updated_at=utcnow(),
            )
            .on_conflict_do_update(
                index_elements=["key"], set_={"generation": generation, "updated_at": utcnow()}
            )
        )
