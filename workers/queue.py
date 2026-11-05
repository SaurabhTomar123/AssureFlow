"""PostgreSQL job queue: SKIP LOCKED leasing, fencing tokens, bounded retries, dead-letter (spec section 2)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import CursorResult, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from common.db import transaction
from common.errors import LeaseLost
from common.settings import get_settings
from domain.models import Job, utcnow

LANES = ("fast", "io", "slow")


@dataclass(frozen=True)
class LeasedJob:
    id: uuid.UUID
    type: str
    lane: str
    payload: dict[str, Any]
    grant_id: uuid.UUID | None
    lease_generation: int
    lease_owner: str
    attempts: int
    correlation_id: str


def enqueue(
    s: Session,
    *,
    type: str,
    lane: str,
    payload: dict[str, Any],
    dedupe_key: str,
    correlation_id: str,
    grant_id: uuid.UUID | None = None,
    delay_seconds: int = 0,
) -> bool:
    """Insert a job in the caller's transaction. A repeated dedupe key is a no-op (returns False)."""
    from workers.handlers import registered_types

    if type not in registered_types():
        raise RuntimeError(f"no handler registered for job type {type}")
    inserted = s.execute(
        insert(Job)
        .values(
            id=uuid.uuid4(),
            type=type,
            lane=lane,
            payload=payload,
            dedupe_key=dedupe_key,
            correlation_id=correlation_id,
            grant_id=grant_id,
            run_after=utcnow() + timedelta(seconds=delay_seconds),
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
        .returning(Job.id)
    ).scalar_one_or_none()
    return inserted is not None


def lease_one(lane: str, owner: str, url: str | None = None) -> LeasedJob | None:
    """Lease the next runnable job in a lane; an expired lease is recovered with a new generation."""
    settings = get_settings()
    now = utcnow()
    with transaction(url) as s:
        job = s.execute(
            select(Job)
            .where(
                Job.lane == lane,
                (
                    ((Job.status == "queued") & (Job.run_after <= now))
                    | ((Job.status == "leased") & (Job.lease_expires_at < now))
                ),
            )
            .order_by(Job.run_after, Job.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).scalar_one_or_none()
        if job is None:
            return None
        if job.attempts >= settings.JOB_MAX_ATTEMPTS:
            job.status = "dead"
            job.last_error = (job.last_error or "") + " | lease expired after final attempt"
            job.finished_at = now
            _on_dead(s, job)
            return None
        job.status = "leased"
        job.lease_generation += 1
        job.lease_owner = owner
        job.lease_expires_at = now + timedelta(seconds=settings.JOB_LEASE_SECONDS)
        job.attempts += 1
        job.started_at = now
        return LeasedJob(
            id=job.id,
            type=job.type,
            lane=job.lane,
            payload=dict(job.payload),
            grant_id=job.grant_id,
            lease_generation=job.lease_generation,
            lease_owner=owner,
            attempts=job.attempts,
            correlation_id=job.correlation_id,
        )


def heartbeat(job: LeasedJob, url: str | None = None) -> bool:
    settings = get_settings()
    with transaction(url) as s:
        result: CursorResult[Any] = s.execute(  # type: ignore[assignment]
            text(
                "UPDATE jobs SET lease_expires_at = now() + make_interval(secs => :secs) "
                "WHERE id = :id AND lease_generation = :g AND lease_owner = :o AND status = 'leased'"
            ),
            {
                "secs": settings.JOB_LEASE_SECONDS,
                "id": job.id,
                "g": job.lease_generation,
                "o": job.lease_owner,
            },
        )
        return bool(result.rowcount)


def fence_and_complete(s: Session, job: LeasedJob) -> None:
    """First statement of a handler's committing transaction: lock our job row and mark it succeeded.

    Zero rows means another worker owns the job now; the whole transaction rolls back (G-09).
    """
    result: CursorResult[Any] = s.execute(  # type: ignore[assignment]
        text(
            "UPDATE jobs SET status = 'succeeded', finished_at = now(), lease_expires_at = NULL "
            "WHERE id = :id AND lease_generation = :g AND lease_owner = :o AND status = 'leased'"
        ),
        {"id": job.id, "g": job.lease_generation, "o": job.lease_owner},
    )
    if result.rowcount != 1:
        raise LeaseLost(f"job {job.id} lease generation {job.lease_generation} is no longer ours")


def fail(job: LeasedJob, error: str, *, retryable: bool, cancel: bool = False, url: str | None = None) -> str:
    """Record a failure under the fence. Returns the resulting job status."""
    settings = get_settings()
    with transaction(url) as s:
        row = s.execute(
            select(Job)
            .where(
                Job.id == job.id,
                Job.lease_generation == job.lease_generation,
                Job.lease_owner == job.lease_owner,
                Job.status == "leased",
            )
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            return "lease_lost"
        row.last_error = error[:500]
        row.lease_expires_at = None
        if cancel:
            row.status = "cancelled"
            row.finished_at = utcnow()
        elif retryable and row.attempts < settings.JOB_MAX_ATTEMPTS:
            backoff = settings.JOB_BACKOFF_SECONDS
            delay = backoff[min(row.attempts - 1, len(backoff) - 1)]
            row.status = "queued"
            row.run_after = utcnow() + timedelta(seconds=delay)
        else:
            row.status = "dead"
            row.finished_at = utcnow()
            _on_dead(s, row)
        return row.status


def _on_dead(s: Session, job: Job) -> None:
    from workers.handlers import on_dead

    on_dead(s, job)
