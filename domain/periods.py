"""Period assignment, the UNASSIGNED queue and readiness (spec section 6)."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from common.errors import Forbidden, ValidationFailed
from domain.models import Invoice, Issue, RequestContext
from domain.scope import is_assigned_ca, is_owner_of
from domain.services.base import UNASSIGNED, bump_period, case_event

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def parse_period(value: str) -> str:
    if not PERIOD_RE.match(value):
        raise ValidationFailed("Periods look like 2026-11.")
    return value


def period_end(period: str) -> datetime:
    year, month = (int(p) for p in period.split("-"))
    last = calendar.monthrange(year, month)[1]
    return datetime(year, month, last, 23, 59, 59, tzinfo=UTC)


@dataclass
class Readiness:
    period: str
    included: list[Invoice] = field(default_factory=list)
    excluded: list[Invoice] = field(default_factory=list)
    held: list[Invoice] = field(default_factory=list)
    unassigned: list[Invoice] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.held and not self.unassigned


def readiness(s: Session, shop_id: object, period: str) -> Readiness:
    result = Readiness(period)
    for case in s.execute(
        select(Invoice).where(Invoice.shop_id == shop_id, Invoice.period == period).order_by(Invoice.case_ref)
    ).scalars():
        if case.status == "approved":
            result.included.append(case)
        elif case.status == "excluded":
            result.excluded.append(case)
        else:
            result.held.append(case)
    for case in s.execute(
        select(Invoice)
        .where(
            Invoice.shop_id == shop_id,
            Invoice.period.is_(None),
            Invoice.status != "excluded",
            Invoice.created_at <= period_end(period),
        )
        .order_by(Invoice.case_ref)
    ).scalars():
        result.unassigned.append(case)
    return result


def why_held(s: Session, case: Invoice) -> str:
    if case.status == "approved":
        return f"{case.case_ref} is included (approved)."
    if case.status == "excluded":
        return f"{case.case_ref} is excluded."
    issues = list(
        s.execute(
            select(Issue).where(
                Issue.invoice_id == case.id,
                Issue.revision_id == case.current_revision_id,
                Issue.status.in_(("open", "awaiting_owner", "awaiting_supplier", "awaiting_ca")),
            )
        ).scalars()
    )
    state = case.status.replace("_", " ")
    if not issues:
        waiting = {
            "received": "waiting to be read",
            "processing": "being read",
            "extraction_failed": "could not be read; send a clearer copy",
            "needs_confirmation": "waiting for the owner to confirm the details",
            "checking": "checks are running",
            "ready_for_ca": "waiting for the CA's decision",
        }.get(case.status, state)
        return f"{case.case_ref}: {waiting}."
    parts = [f"{i.rule_id} ({i.status.replace('_', ' ')}): {i.next_action}" for i in issues]
    return f"{case.case_ref} is {state}. " + " ".join(parts)


def assign_period(s: Session, ctx: RequestContext, case: Invoice, period: str) -> None:
    period = parse_period(period)
    if is_assigned_ca(s, ctx.verified_user_id, case.shop_id):
        basis = "ca_assigned"
    elif is_owner_of(s, ctx.verified_user_id, case.shop_id):
        basis = "owner_assigned"
    else:
        raise Forbidden("Not authorized for this shop.")
    bump_period(s, case.shop_id, case.period or UNASSIGNED)
    case.period, case.period_basis = period, basis
    case_event(
        s,
        case,
        "period_assigned",
        ctx.request_id,
        {"period": period, "basis": basis},
        context_id=ctx.context_id,
    )
