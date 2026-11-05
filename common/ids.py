"""UUIDv7 primary keys and per-practice human references (R-, INV-, RR-, SN-) that are never reused."""

from __future__ import annotations

import uuid

import uuid6
from sqlalchemy import text
from sqlalchemy.orm import Session


def new_id() -> uuid.UUID:
    return uuid.UUID(str(uuid6.uuid7()))


def next_ref(session: Session, practice_id: uuid.UUID, prefix: str) -> str:
    """Allocate the next human reference atomically inside the caller's transaction."""
    value: int = session.execute(
        text(
            "INSERT INTO ref_counters (practice_id, prefix, next_value) VALUES (:p, :x, 2) "
            "ON CONFLICT (practice_id, prefix) DO UPDATE SET next_value = ref_counters.next_value + 1 "
            "RETURNING next_value - 1"
        ),
        {"p": practice_id, "x": prefix},
    ).scalar_one()
    return f"{prefix}-{int(value):04d}"
