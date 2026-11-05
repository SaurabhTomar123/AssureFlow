"""Operations, practice home and synthetic testing rooms (P4-06, P5-07, P5-09, P5-10).

Operations answers carry IDs and metadata only: never invoice text, attachments or secrets. Infrastructure
access does not imply authority over invoices; an operator can retry a dead job, nothing else.
"""

from __future__ import annotations

import uuid

from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session
from sqlalchemy.types import String

from common.errors import Forbidden, NotAvailable, NotFound, ValidationFailed
from common.settings import get_settings
from domain.context import issue_grant
from domain.models import (
    CaseEvent,
    ExecutionGrant,
    InboxEvent,
    Invoice,
    Job,
    Outbox,
    RequestContext,
    ReviewRequest,
    RoomBinding,
    RoomBindingShop,
    Shop,
    TestRun,
    User,
    utcnow,
)
from domain.periods import readiness
from domain.scope import is_assigned_ca
from domain.services.base import audit, post
from workers.queue import enqueue

OPS_ROOM_PURPOSE = "operations"


def _role(s: Session, ctx: RequestContext) -> str:
    user = s.get(User, ctx.verified_user_id)
    return user.role if user else ""


def require_role(s: Session, ctx: RequestContext, *roles: str) -> None:
    if _role(s, ctx) not in roles:
        raise Forbidden(f"Only a {' or '.join(roles)} can do that here.")


# ------------------------------------------------------------------------------- operations


def health_text(s: Session) -> str:
    depth = dict(
        s.execute(
            select(Job.lane, func.count()).where(Job.status.in_(("queued", "leased"))).group_by(Job.lane)
        ).all()
    )
    dead = s.execute(select(func.count()).select_from(Job).where(Job.status == "dead")).scalar_one()
    pending_inbox = s.execute(
        select(func.count()).select_from(InboxEvent).where(InboxEvent.outcome == "pending")
    ).scalar_one()
    withheld = s.execute(
        select(func.count()).select_from(Outbox).where(Outbox.status.in_(("withheld", "dead")))
    ).scalar_one()
    oldest = s.execute(select(func.min(Job.created_at)).where(Job.status == "queued")).scalar_one()
    age = f"{int((utcnow() - oldest).total_seconds())}s" if oldest else "none"
    lanes = ", ".join(f"{k}={v}" for k, v in sorted(depth.items())) or "empty"
    return (
        f"Health: queue {lanes} (oldest queued {age}) · dead jobs {dead} · unprocessed inbox {pending_inbox} · "
        f"withheld/dead messages {withheld}"
    )


def _job(s: Session, prefix: str) -> Job:
    jobs = list(
        s.execute(select(Job).where(cast(Job.id, String).like(f"{prefix.lower()}%")).limit(2)).scalars()
    )
    if len(jobs) != 1:
        raise NotFound(f"No unique job starting with {prefix}.")
    return jobs[0]


def failed_jobs_text(s: Session) -> str:
    rows = list(
        s.execute(
            select(Job).where(Job.status.in_(("dead", "cancelled"))).order_by(Job.created_at.desc()).limit(10)
        ).scalars()
    )
    if not rows:
        return "No failed or cancelled jobs."
    return "Failed jobs:\n" + "\n".join(
        f"• {str(j.id)[:8]} {j.type} {j.status} attempts={j.attempts} error={(j.last_error or '')[:60].split(':')[0]}"
        for j in rows
    )


def describe_job(s: Session, prefix: str) -> str:
    j = _job(s, prefix)
    grant = s.get(ExecutionGrant, j.grant_id) if j.grant_id else None
    return (
        f"Job {j.id}: {j.type} lane={j.lane} status={j.status} attempts={j.attempts} "
        f"lease_generation={j.lease_generation} correlation={j.correlation_id} "
        f"grant={grant.operation if grant else 'none'}{' (revoked)' if grant and grant.revoked_at else ''} "
        f"error_type={(j.last_error or 'none').split(':')[0]}"
    )


def retry_job(s: Session, ctx: RequestContext, prefix: str) -> str:
    require_role(s, ctx, "operator")
    j = _job(s, prefix)
    if j.status != "dead":
        raise ValidationFailed(f"Job {str(j.id)[:8]} is {j.status}; only dead jobs can be retried.")
    grant = s.get(ExecutionGrant, j.grant_id) if j.grant_id else None
    if grant is not None and (grant.revoked_at is not None or grant.expires_at <= utcnow()):
        raise Forbidden(
            "Its execution grant is revoked or expired; the original requester must start it again."
        )
    j.status, j.attempts, j.run_after, j.last_error = "queued", 0, utcnow(), None
    audit(
        s,
        action="job.retry",
        entity="job",
        entity_id=str(j.id),
        outcome="permitted",
        actor=str(ctx.verified_user_id),
        request_id=ctx.request_id,
        context_id=ctx.context_id,
    )
    return f"Job {str(j.id)[:8]} ({j.type}) queued again."


def trace_case(s: Session, case_ref: str) -> str:
    case = s.execute(select(Invoice).where(Invoice.case_ref == case_ref.upper())).scalar_one_or_none()
    if case is None:
        raise NotFound(f"No case {case_ref}.")
    lines = [f"Trace {case.case_ref}: status={case.status} generation={case.document_generation}"]
    for ev in s.execute(
        select(CaseEvent).where(CaseEvent.case_id == case.id).order_by(CaseEvent.seq)
    ).scalars():
        lines.append(f"  #{ev.seq} {ev.at:%H:%M:%S} {ev.type} corr={ev.correlation_id[:8]}")
    for j in s.execute(
        select(Job).where(Job.payload["case_id"].astext == str(case.id)).order_by(Job.created_at)
    ).scalars():
        took = (
            f"{(j.finished_at - j.started_at).total_seconds():.1f}s"
            if j.finished_at and j.started_at
            else "-"
        )
        lines.append(f"  job {str(j.id)[:8]} {j.type} {j.status} attempts={j.attempts} took={took}")
    for o in s.execute(
        select(Outbox).where(Outbox.case_ref == case.case_ref).order_by(Outbox.created_at)
    ).scalars():
        lines.append(f"  msg {o.action_id.split(':')[0]} seq={o.seq} {o.status}")
    return "\n".join(lines[:60])


def ops_alert(s: Session, practice_id: uuid.UUID | None, key: str, text: str, correlation_id: str) -> None:
    """Post a metadata-only alert to the operations room, if one is bound."""
    query = select(RoomBinding).where(
        RoomBinding.purpose == OPS_ROOM_PURPOSE,
        RoomBinding.active.is_(True),
        RoomBinding.environment == get_settings().ENVIRONMENT,
    )
    if practice_id is not None:
        query = query.where(RoomBinding.practice_id == practice_id)
    for room in s.execute(query).scalars():
        post(s, room, action_id=f"alert:{key}", body=f"ALERT {text}", correlation_id=correlation_id)


# ------------------------------------------------------------------------------- practice home


def directory_text(s: Session, ctx: RequestContext, room: RoomBinding) -> str:
    """Only what every member of this room may see: the room's shops (all members are assigned CAs)."""
    require_role(s, ctx, "ca", "practice_staff")
    shop_ids = [
        r
        for r in s.execute(
            select(RoomBindingShop.shop_id).where(RoomBindingShop.room_binding_id == room.id)
        ).scalars()
    ]
    lines = ["Practice directory:"]
    for shop in s.execute(select(Shop).where(Shop.id.in_(shop_ids)).order_by(Shop.code)).scalars():
        if not is_assigned_ca(s, ctx.verified_user_id, shop.id):
            continue
        rooms = [
            r.name
            for r in s.execute(
                select(RoomBinding)
                .join(RoomBindingShop, RoomBindingShop.room_binding_id == RoomBinding.id)
                .where(RoomBindingShop.shop_id == shop.id, RoomBinding.active.is_(True))
                .order_by(RoomBinding.name)
            ).scalars()
        ]
        open_rr = s.execute(
            select(func.count())
            .select_from(ReviewRequest)
            .where(ReviewRequest.shop_id == shop.id, ReviewRequest.status == "open")
        ).scalar_one()
        month = utcnow().strftime("%Y-%m")
        ready = readiness(s, shop.id, month)
        lines.append(
            f"• {shop.code}: {shop.name} · rooms {', '.join(rooms)} · open review requests {open_rr} · "
            f"{month}: held {len(ready.held)}, unassigned {len(ready.unassigned)}"
        )
    return "\n".join(lines)


# ------------------------------------------------------------------------------- synthetic testing


def testing_enabled() -> bool:
    return get_settings().ENVIRONMENT in ("test", "demo")


def request_acceptance(s: Session, ctx: RequestContext, room: RoomBinding) -> str:
    require_role(s, ctx, "developer")
    if not testing_enabled():
        raise NotAvailable("Acceptance runs exist only in the test and demo environments.")
    shop_id = s.execute(select(Shop.id).where(Shop.practice_id == room.practice_id).limit(1)).scalar_one()
    grant = issue_grant(
        s, operation="run_acceptance", practice_id=room.practice_id, shop_id=shop_id, context=ctx
    )
    enqueue(
        s,
        type="run_acceptance",
        lane="slow",
        payload={"room_id": room.switch_room_id, "user_id": str(ctx.verified_user_id)},
        dedupe_key=f"acceptance:{ctx.request_id}",
        correlation_id=ctx.request_id,
        grant_id=grant.grant_id,
    )
    return "Acceptance run started (offline suite: real PostgreSQL, fake model, mocked bridge). The report follows."


def report_text(s: Session, run_id: str) -> str:
    run = s.get(TestRun, run_id)
    if run is None:
        raise NotFound(f"No test run {run_id}.")
    return format_report(run)


def format_report(run: TestRun) -> str:
    a = run.assertions
    head = (
        f"Acceptance {run.run_id} · {run.mode} · env {run.environment} · Switch {run.switch_versions} · "
        f"commit {run.app_commit[:10]} · fixtures {run.fixture_version}\n"
        f"Assertions: {a.get('tests')} run, {a.get('passed')} passed, {a.get('failed')} failed · "
        f"report sha256 {run.report_hash[:16]}"
    )
    fails = "\n".join(f"• {f}" for f in run.failures[:10])
    return head + (f"\nFailures:\n{fails}" if fails else "") + "\nArtifacts: " + ", ".join(run.artifact_refs)


def reset_allowed() -> None:
    if get_settings().ENVIRONMENT != "test":
        raise NotAvailable("reset_fixtures runs only in the test environment.")
