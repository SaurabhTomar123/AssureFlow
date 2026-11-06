"""CA action model (spec section 4).

Actor: the assigned CA, identified by a fresh interactive context from that CA's own reply. Every action
is bound to the review request's revision and check run, writes one decision row and one case event, and
increments the shop-period version. Hackathon cut: include_with_override and reopen are not available.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from common.errors import Forbidden, NotFound, StaleRevision, ValidationFailed
from domain import states as st
from domain.context import require_live_context, revoke_grants
from domain.models import (
    CheckResult,
    Decision,
    Invoice,
    Issue,
    RequestContext,
    ReviewRequest,
    utcnow,
)
from domain.scope import is_assigned_ca
from domain.services import messages as msg
from domain.services.base import audit, case_event, post, room_for_shop
from domain.services.cases import Exec, current_revision, release_duplicate_key
from domain.services.checks import (
    evaluate,
    latest_run,
    open_issues,
    open_review_request,
    record_check_run,
    route_issues,
)
from domain.workflow import Command, Event
from rules import registry, routing

ACTIONS = (
    "include",
    "exclude",
    "resolve_issue",
    "request_owner_clarification",
    "request_supplier_replacement",
    "include_with_override",
)


@dataclass
class ActionResult:
    reply: str
    case_ref: str


def _bind(s: Session, ctx: RequestContext, rr_ref: str) -> tuple[ReviewRequest, Invoice]:
    require_live_context(ctx)
    rr = s.execute(
        select(ReviewRequest).where(
            ReviewRequest.practice_id == ctx.practice_id, ReviewRequest.public_ref == rr_ref
        )
    ).scalar_one_or_none()
    if rr is None:
        raise NotFound(f"No review request {rr_ref}.")
    if not is_assigned_ca(s, ctx.verified_user_id, rr.shop_id):
        audit(
            s,
            action="ca_action.denied",
            entity="review_request",
            entity_id=rr_ref,
            outcome="denied",
            actor=str(ctx.verified_user_id),
            request_id=ctx.request_id,
            practice_id=rr.practice_id,
            shop_id=rr.shop_id,
            context_id=ctx.context_id,
        )
        raise Forbidden("Only the CA assigned to this shop can decide its review requests.")
    case = s.execute(select(Invoice).where(Invoice.id == rr.invoice_id).with_for_update()).scalar_one()
    rev = current_revision(s, case)
    run = latest_run(s, rev.id) if rev else None
    if (
        rr.status != "open"
        or rev is None
        or rev.id != rr.revision_id
        or run is None
        or run.id != rr.check_run_id
    ):
        current = f"r{rev.revision_no}" if rev else "unread"
        raise StaleRevision(
            f"{rr_ref} was raised for an earlier version of {case.case_ref}; it is now {current} "
            f"({case.status.replace('_', ' ')}). Decide the newer review request instead.",
            {"review_request": rr_ref, "current_revision": current, "status": case.status},
        )
    return rr, case


def _decide(
    s: Session,
    ctx: RequestContext,
    rr: ReviewRequest,
    case: Invoice,
    action: str,
    reason: str | None,
    issue: Issue | None = None,
) -> None:
    s.add(
        Decision(
            practice_id=case.practice_id,
            shop_id=case.shop_id,
            review_request_id=rr.id,
            invoice_id=case.id,
            revision_id=rr.revision_id,
            check_run_id=rr.check_run_id,
            actor_user_id=ctx.verified_user_id,
            request_context_id=ctx.context_id,
            action=action,
            reason=reason,
            target_issue_id=issue.id if issue else None,
            request_id=ctx.request_id,
        )
    )
    audit(
        s,
        action=f"ca_action.{action}",
        entity="invoice",
        entity_id=case.case_ref,
        outcome="permitted",
        actor=str(ctx.verified_user_id),
        request_id=ctx.request_id,
        practice_id=case.practice_id,
        shop_id=case.shop_id,
        context_id=ctx.context_id,
    )


def _transition(
    s: Session, ctx: RequestContext, case: Invoice, command: str, payload: dict[str, str]
) -> None:
    old, new = st.transition(case, command)
    case_event(
        s,
        case,
        f"status:{new}",
        ctx.request_id,
        {"from": old, "to": new, **payload},
        context_id=ctx.context_id,
    )
    from domain.services import purchases

    purchases.on_case_change(s, case, ctx.request_id, ctx, None)


def perform(
    s: Session, ctx: RequestContext, rr_ref: str, action: str, arg: str | None, reason: str | None
) -> ActionResult:
    if action == "reopen":
        raise ValidationFailed("Reopen names the case, not a review request: `reopen INV-0001 <reason>`.")
    if action not in ACTIONS:
        raise ValidationFailed(f"Unknown action '{action}'.")
    rr, case = _bind(s, ctx, rr_ref)
    if action == "include":
        blocking = [i for i in open_issues(s, case) if i.blocking]
        if blocking:
            raise ValidationFailed(
                f"{case.case_ref} still has blocking issues: {', '.join(i.rule_id for i in blocking)}. "
                "Resolve, exclude or request a correction first."
            )
        st.target(case.status, "ca_include")
        _decide(s, ctx, rr, case, "include", reason)
        rr.status = "decided"
        _transition(s, ctx, case, "ca_include", {"review_request": rr.public_ref})
        reply = f"{case.case_ref} included. It will count in the monthly pack."
    elif action == "include_with_override":
        if not arg or not reason:
            raise ValidationFailed("Use `RR-0001 override <RULE-ID>[,<RULE-ID>] <reason>`.")
        named = {r.strip().upper() for r in arg.split(",") if r.strip()}
        blocking = [i for i in open_issues(s, case) if i.blocking]
        uncovered = sorted(i.rule_id for i in blocking if i.rule_id.upper() not in named)
        if uncovered:
            raise ValidationFailed(
                f"Name every blocking issue to override; still open: {', '.join(uncovered)}."
            )
        for issue in blocking:
            rule = registry.BY_ID.get(issue.rule_id)
            if rule is None or not rule.overridable:
                raise Forbidden(
                    f"{issue.rule_id} ({issue.category}) is never overridable: arithmetic, GSTIN structure, "
                    "exact duplicates and unsupported documents need a correction or an exclusion."
                )
        st.target(case.status, "ca_include_with_override")
        for issue in blocking:
            _decide(s, ctx, rr, case, "include_with_override", reason, issue)
            issue.status, issue.disposition, issue.updated_at = "resolved", "override", utcnow()
        rr.status = "decided"
        _transition(
            s, ctx, case, "ca_include_with_override", {"review_request": rr.public_ref, "override": arg}
        )
        reply = (
            f"{case.case_ref} included with an override of {', '.join(sorted(named))} ({reason}). "
            "The override is listed in the export."
        )
    elif action == "exclude":
        if not reason:
            raise ValidationFailed("Exclude needs a reason, e.g. `RR-0001 exclude duplicate of INV-0002`.")
        st.target(case.status, "ca_exclude")
        _decide(s, ctx, rr, case, "exclude", reason)
        rr.status = "decided"
        for issue in open_issues(s, case):
            issue.status, issue.updated_at = "excluded", utcnow()
        release_duplicate_key(s, case)
        revoke_grants(s, "case_excluded", case_id=case.id)
        _transition(s, ctx, case, "ca_exclude", {"review_request": rr.public_ref, "reason": reason})
        reply = f"{case.case_ref} excluded ({reason}). It stays in the exclusion register, never in totals."
    elif action == "resolve_issue":
        if not arg or not reason:
            raise ValidationFailed("Use `RR-0001 resolve <RULE-ID> <reason>`.")
        target_issue = next((i for i in open_issues(s, case) if i.rule_id.upper() == arg.upper()), None)
        if target_issue is None:
            raise NotFound(f"No open issue {arg} on {case.case_ref}.")
        result = s.get(CheckResult, target_issue.check_result_id)
        has_evidence = "evidence" in reason.lower() or "page" in reason.lower()
        if not routing.can_resolve(target_issue.category, result.outcome if result else "", has_evidence):
            raise Forbidden(
                f"{target_issue.rule_id} ({target_issue.category}) cannot be resolved by a disposition in this release; "
                "exclude the invoice or request a corrected one."
            )
        st.target(case.status, "ca_resolve_issue")
        _decide(s, ctx, rr, case, "resolve_issue", reason, target_issue)
        target_issue.status, target_issue.disposition, target_issue.updated_at = (
            "resolved",
            "resolved_with_evidence",
            utcnow(),
        )
        case_event(
            s,
            case,
            "issue_resolved",
            ctx.request_id,
            {"rule": target_issue.rule_id},
            context_id=ctx.context_id,
        )
        rr.status = "decided"
        remaining = [i for i in open_issues(s, case) if i.blocking]
        if not remaining:
            Exec(s, case, ctx.request_id, context=ctx).run(
                Event("issue_resolved", all_blocking_resolved=True)
            )
            reply = f"{target_issue.rule_id} on {case.case_ref} resolved. A new review request follows for inclusion."
        else:
            open_review_request(s, case, ctx.request_id)
            reply = f"{target_issue.rule_id} resolved; {len(remaining)} blocking issue(s) remain on {case.case_ref}."
    elif action == "request_owner_clarification":
        if not reason:
            raise ValidationFailed("Use `RR-0001 clarify <question for the owner>`.")
        st.target(case.status, "ca_request_owner_clarification")
        _decide(s, ctx, rr, case, "request_owner_clarification", reason)
        rr.status = "decided"
        for issue in open_issues(s, case):
            if issue.owner_role == "ca":
                issue.status, issue.next_action = (
                    "awaiting_owner",
                    "Owner: answer the CA's question with a typed correction.",
                )
        if case.status == st.READY_FOR_CA:
            _transition(s, ctx, case, "ca_request_owner_clarification", {"review_request": rr.public_ref})
        else:
            case_event(s, case, "clarification_requested", ctx.request_id, {}, context_id=ctx.context_id)
        room = room_for_shop(s, case.shop_id, "shop_intake")
        if room is not None:
            post(
                s,
                room,
                action_id=f"clarify:{rr.id}",
                body=f"Your CA asks about {case.case_ref}: {reason}\nAnswer with a correction like `{case.case_ref} total=1180.00`.",
                case_ref=case.case_ref,
                correlation_id=ctx.request_id,
            )
        reply = f"Question sent to the owner of {case.case_ref}."
    else:  # request_supplier_replacement
        if not reason:
            raise ValidationFailed("Use `RR-0001 supplier <what the supplier must correct>`.")
        st.target(case.status, "ca_request_supplier_replacement")
        _decide(s, ctx, rr, case, "request_supplier_replacement", reason)
        rr.status = "decided"
        for issue in open_issues(s, case):
            if issue.owner_role == "ca":
                issue.status = "awaiting_supplier"
                issue.next_action = "Owner: send the supplier's corrected invoice with the case number."
        if case.status == st.READY_FOR_CA:
            _transition(s, ctx, case, "ca_request_supplier_replacement", {"review_request": rr.public_ref})
        else:
            case_event(
                s, case, "supplier_replacement_requested", ctx.request_id, {}, context_id=ctx.context_id
            )
        rev = current_revision(s, case)
        room = room_for_shop(s, case.shop_id, "shop_intake")
        if room is not None and rev is not None:
            draft = (
                f"Dear {rev.supplier_name or 'Supplier'},\nPlease issue a corrected tax invoice for "
                f"{rev.invoice_number or 'the invoice'} dated {rev.invoice_date or '?'}: {reason}.\n"
                "We need it to complete our GST purchase review (CGST Act s.16(2)). Thank you."
            )
            post(
                s,
                room,
                action_id=f"supplier:{rr.id}",
                body=(
                    f"{case.case_ref} is waiting for a corrected invoice from the supplier. Draft you can send:\n"
                    f"---\n{draft}\n---\nWhen it arrives, send it here with {case.case_ref} in the message."
                ),
                case_ref=case.case_ref,
                correlation_id=ctx.request_id,
            )
        reply = f"{case.case_ref} is now waiting for the supplier. The owner has a draft request to send."
    return ActionResult(reply=f"{rr.public_ref}: {reply}", case_ref=case.case_ref)


def reopen(s: Session, ctx: RequestContext, case_ref: str, reason: str | None) -> ActionResult:
    """excluded -> needs_resolution; the issues are re-raised by a new check run (CA action model)."""
    require_live_context(ctx)
    if not reason:
        raise ValidationFailed("Reopen needs a reason: `reopen INV-0001 <reason>`.")
    case = s.execute(
        select(Invoice)
        .where(Invoice.practice_id == ctx.practice_id, Invoice.case_ref == case_ref.upper())
        .with_for_update()
    ).scalar_one_or_none()
    if case is None:
        raise NotFound(f"No case {case_ref}.")
    if not is_assigned_ca(s, ctx.verified_user_id, case.shop_id):
        raise Forbidden("Only the CA assigned to this shop can reopen its cases.")
    st.target(case.status, "ca_reopen")
    rr = s.execute(
        select(ReviewRequest)
        .where(ReviewRequest.invoice_id == case.id)
        .order_by(ReviewRequest.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    rev = current_revision(s, case)
    if rr is None or rev is None or rev.status != "confirmed":
        raise ValidationFailed(
            f"{case.case_ref} has no confirmed revision to reopen; ask the owner to confirm it."
        )
    _decide(s, ctx, rr, case, "reopen", reason)
    _transition(s, ctx, case, "ca_reopen", {"reason": reason})
    Exec(s, case, ctx.request_id, context=ctx)._claim_duplicate_key(Command("claim_duplicate_key"))
    results, inputs_hash, results_hash = evaluate(s, case, rev)
    _, blocking, _ = record_check_run(s, case, rev, results, inputs_hash, results_hash)
    if blocking:
        route_issues(s, case, ctx.request_id)
        open_review_request(s, case, ctx.request_id)
        state = "needs resolution"
    else:
        _transition(s, ctx, case, "issues_resolved", {"reason": "reopened, checks clean"})
        open_review_request(s, case, ctx.request_id)
        state = "ready for CA"
    return ActionResult(
        reply=f"{case.case_ref} reopened ({reason}); checks re-ran, now {state}.", case_ref=case.case_ref
    )


def ambiguous_reply() -> str:
    return "Which review request? Reply to its message or name it, e.g. `RR-0004 include`. " + msg.help_ca()
