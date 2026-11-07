"""Assigned purchase work (U2 sections 3 and 7).

Tasks: open -> acknowledged -> evidence_submitted -> verified_complete; the owner can cancel with a reason.
Assignment never grants access: a task view is posted only in a room every member may already see. Marking a
task done triggers re-evaluation; it never clears a mismatch by itself.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from common.errors import Forbidden, NotFound, ValidationFailed
from common.ids import next_ref
from domain.models import (
    BusinessTask,
    Invoice,
    PurchaseLink,
    PurchaseOrder,
    RequestContext,
    Shop,
    TaskEvent,
    User,
    utcnow,
)
from domain.scope import has_capability
from domain.services import purchases as pa
from domain.services.base import audit, post, room_for_shop
from domain.services.disclosure import _authorized

TRANSITIONS = {
    "ack": ({"open"}, "acknowledged"),
    "done": ({"open", "acknowledged"}, "evidence_submitted"),
    "verify": ({"open", "acknowledged", "evidence_submitted"}, "verified_complete"),
    "cancel": ({"open", "acknowledged", "evidence_submitted"}, "cancelled"),
}


def parse_due(word: str, tz: str = "Asia/Kolkata") -> str:
    from datetime import datetime

    today = datetime.now(ZoneInfo(tz)).date()
    lowered = word.lower()
    if lowered == "today":
        return today.isoformat()
    if lowered == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    try:
        return date.fromisoformat(word).isoformat()
    except ValueError as exc:
        raise ValidationFailed(f"'{word}' is not a due date (use today, tomorrow or YYYY-MM-DD).") from exc


def _assignee(s: Session, shop: Shop, name: str) -> User:
    candidates = [u for u in pa.holders(s, shop.id, "task_work") if name.lower() in (u.handle.lower(), pa.short_handle(u).lower())]
    if not candidates:
        staff = ", ".join(pa.short_handle(u) for u in pa.holders(s, shop.id, "task_work")) or "nobody yet"
        raise ValidationFailed(f"'{name}' is not set up to take purchase tasks for {shop.name}. Verified staff: {staff}.")
    return candidates[0]


def _event(s: Session, task: BusinessTask, action: str, old: str | None, ctx: RequestContext, note: str | None) -> None:
    s.add(
        TaskEvent(
            practice_id=task.practice_id,
            shop_id=task.shop_id,
            task_id=task.id,
            action=action,
            from_status=old,
            to_status=task.status,
            actor_user_id=ctx.verified_user_id,
            context_id=ctx.context_id,
            note=note,
        )
    )
    audit(
        s,
        action=f"task.{action}",
        entity="business_task",
        entity_id=str(task.id),
        outcome="ok",
        actor=str(ctx.verified_user_id),
        request_id=ctx.request_id,
        practice_id=task.practice_id,
        shop_id=task.shop_id,
        context_id=ctx.context_id,
        after={"task": task.task_ref, "status": task.status, "note": note},
    )


def assign(s: Session, ctx: RequestContext, case: Invoice, words: list[str]) -> str:
    """`task INV-0001 <who> <due> <what to do>`; the owner's own reply is the assignment (suggest-and-confirm)."""
    shop = s.get(Shop, case.shop_id)
    assert shop is not None
    pa.require_enabled(shop)
    pa.require_cap(s, ctx, case.shop_id, "task_assign", "assign purchase tasks")
    if len(words) < 5:
        raise ValidationFailed(f"Use `task {case.case_ref} <who> <due> <what to do>`, e.g. `task {case.case_ref} anil tomorrow get a corrected invoice`.")
    link = pa.active_link_for_case(s, case.id)
    if link is None:
        raise ValidationFailed(f"{case.case_ref} is not linked to an order; link it first.")
    assignee = _assignee(s, shop, words[2])
    due = parse_due(words[3], shop.timezone)
    reason = " ".join(words[4:])
    run = pa.latest_run(s, link.id)
    task = BusinessTask(
        practice_id=case.practice_id,
        shop_id=case.shop_id,
        task_ref=next_ref(s, case.practice_id, "TK"),
        link_id=link.id,
        case_id=case.id,
        category="supplier_correction",
        reason=reason,
        assignee_user_id=assignee.id,
        assigned_by=ctx.verified_user_id,
        due_at=due,
        status="open",
        blocker=True,
        expected_input_hash=run.input_hash if run else None,
    )
    s.add(task)
    s.flush()
    _event(s, task, "assigned", None, ctx, reason)
    order = s.get(PurchaseOrder, link.order_id)
    assert order is not None
    room = room_for_shop(s, case.shop_id, "shop_intake")
    blocked = room is None or not _authorized(s, room, assignee, [case.shop_id])
    if not blocked and room is not None:
        post(
            s,
            room,
            action_id=f"task:{task.id}",
            body=(
                f"{task.task_ref} for {pa.display(s, assignee.id)}: {reason}. {order.order_ref} / {case.case_ref}, "
                f"due {due}.\nReply `{task.task_ref} ack`, then `{task.task_ref} done <what you did>` when you have it. "
                "Finishing the task does not clear the hold; the corrected invoice or delivery evidence does."
            ),
            case_ref=case.case_ref,
            correlation_id=ctx.request_id,
        )
    pa.schedule_match(s, link, ctx.request_id, context=ctx)
    if blocked:
        return (
            f"{task.task_ref} recorded for {pa.display(s, assignee.id)}, but the handoff is blocked: there is no room "
            "they may see where it can be posted. Ask the operator to set one up; no access was widened."
        )
    return f"{task.task_ref} assigned to {pa.display(s, assignee.id)}, due {due}."


def find(s: Session, ctx: RequestContext, shop_ids: list[uuid.UUID], ref: str) -> BusinessTask:
    task = s.execute(
        select(BusinessTask)
        .where(BusinessTask.practice_id == ctx.practice_id, BusinessTask.task_ref == ref.upper())
        .with_for_update()
    ).scalar_one_or_none()
    if task is None or task.shop_id not in shop_ids:
        raise NotFound(f"No task {ref.upper()} in this room.")
    return task


def act(s: Session, ctx: RequestContext, shop_ids: list[uuid.UUID], ref: str, action: str, note: str | None) -> str:
    task = find(s, ctx, shop_ids, ref)
    shop = s.get(Shop, task.shop_id)
    assert shop is not None
    pa.require_enabled(shop)
    if action not in TRANSITIONS:
        raise ValidationFailed(f"Use `{task.task_ref} ack`, `done <note>`, `verify` or `cancel <reason>`.")
    allowed, target = TRANSITIONS[action]
    if action in ("ack", "done"):
        if ctx.verified_user_id != task.assignee_user_id or not has_capability(s, ctx.verified_user_id, task.shop_id, "task_work"):
            raise Forbidden(f"Only {pa.display(s, task.assignee_user_id)} can update {task.task_ref}.")
    else:
        pa.require_cap(s, ctx, task.shop_id, "task_assign", "verify or cancel tasks")
        if action == "cancel" and not note:
            raise ValidationFailed(f"Give a reason: `{task.task_ref} cancel <reason>`.")
    if task.status not in allowed:
        raise ValidationFailed(f"{task.task_ref} is {task.status.replace('_', ' ')}.")
    link = s.get(PurchaseLink, task.link_id)
    assert link is not None
    if action == "verify":
        run = pa.latest_run(s, link.id)
        _, _, current = pa.current_inputs(s, link)
        if run is None or run.input_hash != current or run.status == "hold":
            raise ValidationFailed(
                f"{task.task_ref} cannot be verified yet: the purchase checks have not passed on the current "
                "evidence. A finished task alone never clears a mismatch."
            )
    old = task.status
    task.status, task.version, task.updated_at = target, task.version + 1, utcnow()
    _event(s, task, action, old, ctx, note)
    pa.schedule_match(s, link, ctx.request_id, context=ctx)
    case = s.get(Invoice, task.case_id)
    assert case is not None
    if action == "done":
        return (
            f"{task.task_ref}: thanks, noted ({note or 'no note'}). {case.case_ref} stays on hold until the corrected "
            "invoice or delivery evidence arrives and the checks pass."
        )
    return f"{task.task_ref} {target.replace('_', ' ')}."


def list_text(s: Session, ctx: RequestContext, shop: Shop) -> str:
    pa.require_enabled(shop)
    query = select(BusinessTask).where(BusinessTask.shop_id == shop.id, BusinessTask.status.in_(pa.OPEN_TASK))
    if not has_capability(s, ctx.verified_user_id, shop.id, "task_assign"):
        query = query.where(BusinessTask.assignee_user_id == ctx.verified_user_id)
    tasks = list(s.execute(query.order_by(BusinessTask.task_ref)).scalars())
    if not tasks:
        return "No open purchase tasks."
    lines = []
    for task in tasks:
        case = s.get(Invoice, task.case_id)
        lines.append(
            f"• {task.task_ref} · {case.case_ref if case else '?'} · {pa.display(s, task.assignee_user_id)} · due "
            f"{task.due_at} · {task.status.replace('_', ' ')}: {task.reason}"
        )
    return "Open purchase tasks:\n" + "\n".join(lines)
