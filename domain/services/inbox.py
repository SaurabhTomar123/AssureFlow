"""process_inbox_event: classify every room event in code and record its outcome (spec section 7).

Upload in a shop intake room -> receipt. Reply to a known Assure Flow message, or text naming a case /
RR-id / SN-id -> confirmation, correction or CA action. Anything else -> ignored, with an outcome.
No agent mention is needed for any workflow event.
"""

from __future__ import annotations

import re
import shlex
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from common.errors import DomainError, Forbidden, NotFound, ValidationFailed
from common.settings import get_settings
from domain import ca_actions
from domain.context import create_context
from domain.models import (
    ChatIdentity,
    InboxEvent,
    Invoice,
    Outbox,
    RequestContext,
    ReviewRequest,
    RoomBinding,
    Shop,
    User,
    utcnow,
)
from domain.periods import assign_period, parse_period, readiness, why_held
from domain.scope import is_assigned_ca, is_owner_of
from domain.services import intake
from domain.services import messages as msg
from domain.services.base import audit, post, shops_of_room
from domain.services.snapshots import approve_snapshot, request_snapshot

CASE_RE = re.compile(r"\bINV-\d{4,}\b", re.I)
RR_RE = re.compile(r"\bRR-\d{4,}\b", re.I)
SN_RE = re.compile(r"\bSN-\d{4,}\b", re.I)
REV_RE = re.compile(r"\br(\d+)\b", re.I)
COMMAND_WORDS = {
    "ok",
    "confirm",
    "status",
    "pending",
    "why-held",
    "why",
    "help",
    "approve",
    "snapshot",
    "readiness",
    "assign",
    "include",
    "exclude",
}

CA_VERBS = {
    "include": "include",
    "exclude": "exclude",
    "resolve": "resolve_issue",
    "clarify": "request_owner_clarification",
    "supplier": "request_supplier_replacement",
    "override": "include_with_override",
    "reopen": "reopen",
}


@dataclass
class Outcome:
    outcome: str
    reason: str | None = None


def looks_like_command(text: str) -> bool:
    words = text.strip().lower().split()
    return bool(words) and (words[0] in COMMAND_WORDS or bool(CASE_RE.search(text) or RR_RE.search(text)))


def process(s: Session, event: InboxEvent) -> Outcome:
    settings = get_settings()
    room = s.execute(
        select(RoomBinding).where(
            RoomBinding.environment == settings.ENVIRONMENT,
            RoomBinding.switch_room_id == event.switch_room_id,
            RoomBinding.active.is_(True),
        )
    ).scalar_one_or_none()
    if room is None:
        _deny(s, event, None, "unbound_room")
        return Outcome("rejected", "unbound_room")
    event.room_binding_id = room.id
    own = s.execute(select(Outbox.id).where(Outbox.delivered_event_id == event.event_id).limit(1)).first()
    if own is not None or event.sender_ref in (room.permitted_agent_senders or []):
        return Outcome("ignored", "agent_message")
    identity = s.execute(
        select(ChatIdentity).where(
            ChatIdentity.platform == "switch",
            ChatIdentity.platform_user_id == event.sender_ref,
            ChatIdentity.revoked_at.is_(None),
        )
    ).scalar_one_or_none()
    if identity is None or identity.practice_id != room.practice_id:
        if event.attachments or looks_like_command(event.body):
            _deny(s, event, room, "unmapped_sender")
            return Outcome("rejected", "unmapped_sender")
        return Outcome("ignored", "chatter")
    user = s.get(User, identity.user_id)
    assert user is not None
    shops = shops_of_room(s, room.id)
    ctx = create_context(
        s,
        practice_id=room.practice_id,
        shop_id=shops[0] if len(shops) == 1 else None,
        room_binding_id=room.id,
        source_event_id=event.id,
        user_id=user.id,
        request_id=event.correlation_id,
        addressed_agent=event.addressed_agent,
    )
    replies: list[str] = []
    handled = False
    try:
        with s.begin_nested():
            if room.purpose == "shop_intake":
                handled = _shop_room(s, ctx, event, room, shops, replies)
            elif room.purpose == "ca_review":
                handled = _ca_room(s, ctx, event, room, shops, replies)
    except DomainError as err:
        if isinstance(err, Forbidden):
            _deny(s, event, room, err.code, user_id=user.id, context_id=ctx.context_id)
        replies = [msg.error_reply(err)]
        handled = True
    for i, body in enumerate(replies):
        post(s, room, action_id=f"reply:{event.id}:{i}", body=body, correlation_id=event.correlation_id)
    if not handled:
        if event.addressed_agent:
            post(
                s,
                room,
                action_id=f"reply:{event.id}:help",
                body=msg.help_shop() if room.purpose == "shop_intake" else msg.help_ca(),
                correlation_id=event.correlation_id,
            )
            return Outcome("processed", "help")
        return Outcome("ignored", "not_a_workflow_event")
    return Outcome("processed")


def _deny(
    s: Session,
    event: InboxEvent,
    room: RoomBinding | None,
    reason: str,
    user_id: uuid.UUID | None = None,
    context_id: uuid.UUID | None = None,
) -> None:
    audit(
        s,
        action="inbox.denied",
        entity="inbox_event",
        entity_id=str(event.id),
        outcome="denied",
        actor=str(user_id) if user_id else event.sender_ref,
        request_id=event.correlation_id,
        practice_id=room.practice_id if room else None,
        context_id=context_id,
        after={"reason": reason},
    )


def _thread_case_ref(s: Session, event: InboxEvent) -> str | None:
    if not event.thread_id:
        return None
    row = s.execute(
        select(Outbox.case_ref).where(Outbox.delivered_event_id == event.thread_id).limit(1)
    ).first()
    return row[0] if row and row[0] else None


def _thread_rr_ref(s: Session, event: InboxEvent) -> str | None:
    if not event.thread_id:
        return None
    row = s.execute(
        select(Outbox.action_id).where(Outbox.delivered_event_id == event.thread_id).limit(1)
    ).first()
    if row and row[0].startswith("review:"):
        rr = s.get(ReviewRequest, uuid.UUID(row[0].split(":", 1)[1]))
        return rr.public_ref if rr else None
    return None


def _find_case(s: Session, practice_id: uuid.UUID, shop_ids: list[uuid.UUID], ref: str) -> Invoice:
    case = s.execute(
        select(Invoice).where(Invoice.practice_id == practice_id, Invoice.case_ref == ref.upper())
    ).scalar_one_or_none()
    if case is None or case.shop_id not in shop_ids:
        raise NotFound(f"No case {ref.upper()} in this room.")
    return case


def _shop_room(
    s: Session,
    ctx: RequestContext,
    event: InboxEvent,
    room: RoomBinding,
    shops: list[uuid.UUID],
    replies: list[str],
) -> bool:
    shop = s.get(Shop, shops[0])
    assert shop is not None
    text = event.body.strip()
    named = CASE_RE.search(text)
    case_ref = named.group(0).upper() if named else _thread_case_ref(s, event)
    if event.attachments:
        replaces = _find_case(s, room.practice_id, shops, case_ref) if case_ref else None
        for index, attachment in enumerate(event.attachments):
            intake.accept_upload(
                s,
                ctx=ctx,
                event=event,
                room=room,
                shop=shop,
                attachment=attachment,
                index=index,
                replaces=replaces,
            )
        return True
    if not text:
        return False
    words = text.split()
    verb = words[0].lower().rstrip(":")
    if verb == "help":
        replies.append(msg.help_shop())
        return True
    if verb in ("status", "pending"):
        if not (
            is_owner_of(s, ctx.verified_user_id, shop.id) or is_assigned_ca(s, ctx.verified_user_id, shop.id)
        ):
            raise Forbidden("Not authorized for this shop.")
        replies.append(_shop_status(s, shop, pending_only=verb == "pending"))
        return True
    if verb in ("why-held", "why"):
        if not case_ref:
            raise ValidationFailed("Which case? e.g. `why-held INV-0001`.")
        replies.append(why_held(s, _find_case(s, room.practice_id, shops, case_ref)))
        return True
    if verb in ("ok", "confirm", "yes"):
        if not case_ref:
            case_ref = _single_awaiting(s, shop)
        case = _find_case(s, room.practice_id, shops, case_ref)
        rev_match = REV_RE.search(text.replace(case_ref, ""))
        hold = "hold" in (w.lower() for w in words)
        intake.confirm(s, ctx, case, int(rev_match.group(1)) if rev_match else None, hold=hold)
        return True
    if verb == "assign" and case_ref and len(words) >= 3:
        assign_period(s, ctx, _find_case(s, room.practice_id, shops, case_ref), words[-1])
        replies.append(f"{case_ref} assigned to {words[-1]}.")
        return True
    if "=" in text and case_ref:
        case = _find_case(s, room.practice_id, shops, case_ref)
        changes: dict[str, str] = {}
        expected: int | None = None
        try:
            tokens = shlex.split(text)
        except ValueError as exc:
            raise ValidationFailed("Unbalanced quotes in the correction.") from exc
        for token in tokens:
            if "=" in token:
                key, _, value = token.partition("=")
                changes[key.strip()] = value.strip()
            elif re.fullmatch(r"r\d+", token, re.I):
                expected = int(token[1:])
        rev = intake.correct(s, ctx, case, expected, changes)
        replies.append(f"{case.case_ref} corrected (r{rev.revision_no}); the new summary follows.")
        return True
    return False


def _single_awaiting(s: Session, shop: Shop) -> str:
    waiting = list(
        s.execute(
            select(Invoice.case_ref).where(Invoice.shop_id == shop.id, Invoice.status == "needs_confirmation")
        ).scalars()
    )
    if len(waiting) == 1:
        return waiting[0]
    if not waiting:
        raise ValidationFailed("Nothing is waiting for confirmation in this shop.")
    raise ValidationFailed(f"Which one? {', '.join(sorted(waiting))} are waiting. Reply `ok INV-....`.")


def _shop_status(s: Session, shop: Shop, pending_only: bool) -> str:
    cases = list(
        s.execute(select(Invoice).where(Invoice.shop_id == shop.id).order_by(Invoice.case_ref)).scalars()
    )
    if pending_only:
        cases = [c for c in cases if c.status not in ("approved", "excluded")]
    if not cases:
        return f"No {'pending ' if pending_only else ''}cases for {shop.name} (all periods searched)."
    counts: dict[str, int] = {}
    for case in cases:
        counts[case.status] = counts.get(case.status, 0) + 1
    head = f"{shop.name}: " + ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in sorted(counts.items()))
    detail = [why_held(s, c) for c in cases if c.status not in ("approved", "excluded")][:8]
    return "\n".join([head, *[f"• {d}" for d in detail]])


def _ca_shop(s: Session, practice_id: uuid.UUID, shops: list[uuid.UUID], code: str) -> Shop:
    shop = s.execute(
        select(Shop).where(Shop.practice_id == practice_id, Shop.code == code.lower())
    ).scalar_one_or_none()
    if shop is None or shop.id not in shops:
        raise NotFound(f"No shop '{code}' in this review room.")
    return shop


def _ca_room(
    s: Session,
    ctx: RequestContext,
    event: InboxEvent,
    room: RoomBinding,
    shops: list[uuid.UUID],
    replies: list[str],
) -> bool:
    text = event.body.strip()
    if not text:
        return False
    words = text.split()
    verb = words[0].lower()
    if not all(is_assigned_ca(s, ctx.verified_user_id, shop) for shop in shops):
        if looks_like_command(text):
            raise Forbidden("Only CAs assigned to every shop in this room can act here.")
        return False
    if verb == "help":
        replies.append(msg.help_ca())
        return True
    rr = RR_RE.search(text)
    rr_ref = rr.group(0).upper() if rr else _thread_rr_ref(s, event)
    action_word = next((w.lower() for w in words if w.lower() in CA_VERBS), None)
    if action_word and verb != "approve":
        if not rr_ref:
            replies.append(ca_actions.ambiguous_reply())
            return True
        rest = re.sub(
            r"^[^a-zA-Z0-9]*", "", text[text.lower().index(action_word) + len(action_word) :]
        ).strip()
        arg = None
        if action_word == "resolve":
            parts = rest.split(maxsplit=1)
            arg, rest = (parts[0], parts[1] if len(parts) > 1 else "") if parts else (None, "")
        result = ca_actions.perform(s, ctx, rr_ref, CA_VERBS[action_word], arg, rest or None)
        replies.append(result.reply)
        return True
    if verb == "pending":
        open_rr = list(
            s.execute(
                select(ReviewRequest)
                .where(ReviewRequest.shop_id.in_(shops), ReviewRequest.status == "open")
                .order_by(ReviewRequest.public_ref)
            ).scalars()
        )
        if not open_rr:
            replies.append("No open review requests in this room's shops.")
        else:
            lines = []
            for r in open_rr:
                case = s.get(Invoice, r.invoice_id)
                lines.append(f"• {r.public_ref} · {case.case_ref if case else '?'}")
            replies.append("Open review requests:\n" + "\n".join(lines))
        return True
    if verb in ("readiness", "snapshot") and len(words) >= 3:
        shop = _ca_shop(s, room.practice_id, shops, words[1])
        period = parse_period(words[2])
        if verb == "snapshot":
            request_snapshot(s, ctx, shop, period)
            replies.append(f"Building the {period} pack for {shop.name}.")
        else:
            ready = readiness(s, shop.id, period)
            replies.append(
                f"{shop.name} {period}: included {len(ready.included)}, excluded {len(ready.excluded)}, "
                f"held {len(ready.held)}, unassigned {len(ready.unassigned)}"
                + ("" if ready.complete else " (not complete)")
                + "".join(f"\n• {why_held(s, c)}" for c in [*ready.held, *ready.unassigned][:8])
            )
        return True
    if verb == "approve":
        sn = SN_RE.search(text)
        if not sn or len(words) < 3:
            replies.append("Approve a pack by naming it and its hash: `approve SN-0001 <first 12 of hash>`.")
            return True
        ack = None
        if "ack" in [w.lower() for w in words]:
            idx = [w.lower() for w in words].index("ack")
            try:
                ack = (int(words[idx + 1]), int(words[idx + 2]))
            except (IndexError, ValueError) as exc:
                raise ValidationFailed("Use `ack <held> <unassigned>`.") from exc
        outcome = approve_snapshot(s, ctx, sn.group(0).upper(), words[2], ack)
        replies.append(outcome.reply)
        return True
    if verb == "assign":
        case_ref = CASE_RE.search(text)
        if not case_ref or len(words) < 3:
            raise ValidationFailed("Use `assign INV-0001 2026-11`.")
        assign_period(s, ctx, _find_case(s, room.practice_id, shops, case_ref.group(0)), words[-1])
        replies.append(f"{case_ref.group(0).upper()} assigned to {words[-1]}.")
        return True
    return False


def mark(event: InboxEvent, outcome: Outcome) -> None:
    event.outcome = outcome.outcome
    event.outcome_reason = outcome.reason
    event.processed_at = utcnow()
