"""Interactive contexts and execution grants (spec section 7, authority).

An interactive context comes from exactly one verified room event and expires quickly; it authorizes
synchronous actions and grant issuance only. An execution grant is the durable, narrow authority of
one job: one operation on one target.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from common.errors import Unauthenticated
from common.settings import get_settings
from domain.models import (
    ExecutionGrant,
    Job,
    RequestContext,
    utcnow,
)


class GrantInvalid(Exception):
    """The job's grant is revoked, expired or does not cover this write (job is cancelled)."""


def create_context(
    s: Session,
    *,
    practice_id: uuid.UUID,
    shop_id: uuid.UUID | None,
    room_binding_id: uuid.UUID,
    source_event_id: uuid.UUID,
    user_id: uuid.UUID,
    request_id: str,
    addressed_agent: str | None = None,
) -> RequestContext:
    settings = get_settings()
    ctx = RequestContext(
        environment=settings.ENVIRONMENT,
        practice_id=practice_id,
        shop_id=shop_id,
        room_binding_id=room_binding_id,
        source_event_id=source_event_id,
        verified_user_id=user_id,
        addressed_agent_id=addressed_agent,
        request_id=request_id,
        expires_at=utcnow() + timedelta(seconds=settings.REQUEST_CONTEXT_TTL_SECONDS),
    )
    s.add(ctx)
    s.flush()
    return ctx


def require_live_context(ctx: RequestContext) -> None:
    if ctx.expires_at <= utcnow():
        raise Unauthenticated("The request context has expired; send the command again.")


def issue_grant(
    s: Session,
    *,
    operation: str,
    practice_id: uuid.UUID,
    shop_id: uuid.UUID,
    case_id: uuid.UUID | None = None,
    generation: int | None = None,
    snapshot_id: uuid.UUID | None = None,
    receipt_id: uuid.UUID | None = None,
    context: RequestContext | None = None,
    parent: ExecutionGrant | None = None,
) -> ExecutionGrant:
    """Grants are issued from a live interactive context, or chained from the job grant that produced them."""
    settings = get_settings()
    event_id: uuid.UUID | None
    context_id: uuid.UUID | None
    user_id: uuid.UUID | None
    if context is not None:
        require_live_context(context)
        event_id, context_id, user_id = context.source_event_id, context.context_id, context.verified_user_id
    elif parent is not None:
        event_id, context_id, user_id = (
            parent.initiating_event_id,
            parent.initiating_context_id,
            parent.initiating_user_id,
        )
    else:
        raise Unauthenticated("A grant needs an interactive context or a parent grant.")
    grant = ExecutionGrant(
        environment=settings.ENVIRONMENT,
        practice_id=practice_id,
        shop_id=shop_id,
        operation=operation,
        target_case_id=case_id,
        target_generation=generation,
        target_snapshot_id=snapshot_id,
        target_receipt_id=receipt_id,
        initiating_event_id=event_id,
        initiating_context_id=context_id,
        initiating_user_id=user_id,
        expires_at=utcnow() + timedelta(hours=settings.EXECUTION_GRANT_TTL_HOURS),
    )
    s.add(grant)
    s.flush()
    return grant


def check_grant(
    s: Session,
    grant_id: uuid.UUID | None,
    operation: str,
    *,
    case_id: uuid.UUID | None = None,
    generation: int | None = None,
    snapshot_id: uuid.UUID | None = None,
) -> ExecutionGrant:
    if grant_id is None:
        raise GrantInvalid("job has no execution grant")
    grant = s.get(ExecutionGrant, grant_id)
    if grant is None:
        raise GrantInvalid("unknown grant")
    if grant.revoked_at is not None:
        raise GrantInvalid(f"grant revoked: {grant.revoke_reason}")
    if grant.expires_at <= utcnow():
        raise GrantInvalid("grant expired")
    if grant.operation != operation:
        raise GrantInvalid(f"grant covers {grant.operation}, not {operation}")
    if case_id is not None and grant.target_case_id not in (None, case_id):
        raise GrantInvalid("grant targets another case")
    if generation is not None and grant.target_generation not in (None, generation):
        raise GrantInvalid("grant targets another document generation")
    if snapshot_id is not None and grant.target_snapshot_id != snapshot_id:
        raise GrantInvalid("grant targets another snapshot")
    return grant


def revoke_grants(
    s: Session,
    reason: str,
    *,
    case_id: uuid.UUID | None = None,
    below_generation: int | None = None,
    user_id: uuid.UUID | None = None,
    shop_id: uuid.UUID | None = None,
) -> int:
    """Revoke matching live grants and cancel their queued jobs (non-retryable, visible)."""
    query = select(ExecutionGrant).where(ExecutionGrant.revoked_at.is_(None))
    if case_id is not None:
        query = query.where(ExecutionGrant.target_case_id == case_id)
    if below_generation is not None:
        query = query.where(ExecutionGrant.target_generation < below_generation)
    if user_id is not None:
        query = query.where(ExecutionGrant.initiating_user_id == user_id)
    if shop_id is not None:
        query = query.where(ExecutionGrant.shop_id == shop_id)
    grants = list(s.execute(query).scalars())
    now = utcnow()
    for grant in grants:
        grant.revoked_at = now
        grant.revoke_reason = reason
    if grants:
        s.execute(
            update(Job)
            .where(Job.grant_id.in_([g.grant_id for g in grants]), Job.status == "queued")
            .values(status="cancelled", last_error=f"grant revoked: {reason}", finished_at=now)
        )
    return len(grants)
