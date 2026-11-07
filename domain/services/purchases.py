"""Purchase assurance (U2): orders, delivery reports, invoice-to-order links and three-way matching.

Code computes every comparison (rules/purchase.py). People confirm orders, deliveries, links and partial
deliveries; reviewers and owners sign exact records (domain/services/readiness.py). Purchase state lives on
`purchase_links`, never in `invoices.status` (D-27). Delivery-room messages never carry prices.
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from common.errors import Forbidden, NotAvailable, NotFound, OrderAlreadyLinked, ValidationFailed
from common.ids import next_ref
from common.settings import get_settings
from domain.context import issue_grant
from domain.models import (
    BusinessTask,
    CheckRun,
    DeliveryEvent,
    DeliveryReport,
    ExecutionGrant,
    InboxEvent,
    Invoice,
    InvoiceRevision,
    LineItem,
    PaymentReadiness,
    PurchaseLink,
    PurchaseMatchRun,
    PurchaseOrder,
    PurchaseOrderRevision,
    RequestContext,
    Shop,
    ShopCapability,
    User,
    utcnow,
)
from domain.scope import has_capability
from domain.services.base import audit, case_event, post, room_for_shop
from domain.services.messages import inr
from rules.purchase import RULE_VERSION, InvoiceLine, MatchInput, MatchResult, OrderLine, digest, evaluate
from workers.queue import enqueue

PO_RE = re.compile(r"\bPO-\d+\b", re.I)
DR_RE = re.compile(r"\bDR-\d{4,}\b", re.I)
OPEN_TASK = ("open", "acknowledged", "evidence_submitted")


# ------------------------------------------------------------------------------------- access


def enabled(shop: Shop) -> bool:
    return bool(get_settings().PURCHASE_ASSURANCE_ENABLED and shop.purchase_assurance)


def require_enabled(shop: Shop) -> None:
    if not enabled(shop):
        raise NotAvailable(f"Purchase assurance is not enabled for {shop.name}.")


def require_cap(s: Session, ctx: RequestContext, shop_id: uuid.UUID, capability: str, what: str) -> None:
    if not has_capability(s, ctx.verified_user_id, shop_id, capability):
        raise Forbidden(f"You are not set up to {what} for this shop.")


def display(s: Session, user_id: uuid.UUID | None) -> str:
    user = s.get(User, user_id) if user_id else None
    return user.display_name.split(" (")[0] if user else "someone"


def holders(s: Session, shop_id: uuid.UUID, capability: str) -> list[User]:
    ids = s.execute(
        select(ShopCapability.user_id).where(
            ShopCapability.shop_id == shop_id,
            ShopCapability.capability == capability,
            ShopCapability.revoked_at.is_(None),
        )
    ).scalars()
    users = [s.get(User, i) for i in ids]
    return sorted((u for u in users if u is not None), key=lambda u: u.handle)


def short_handle(user: User) -> str:
    return user.handle.split(".", 1)[-1]


def qty(value: Decimal | str) -> str:
    d = Decimal(str(value))
    return format(d.normalize(), "f") if d == d.to_integral() else format(d, "f")


# ------------------------------------------------------------------------------------- orders


def find_order(s: Session, practice_id: uuid.UUID, shop_ids: list[uuid.UUID], ref: str) -> PurchaseOrder:
    order = s.execute(
        select(PurchaseOrder).where(PurchaseOrder.practice_id == practice_id, PurchaseOrder.order_ref == ref.upper())
    ).scalar_one_or_none()
    if order is None or order.shop_id not in shop_ids:
        raise NotFound(f"No order {ref.upper()} in this room.")
    return order


def order_revision(s: Session, order: PurchaseOrder) -> PurchaseOrderRevision:
    rev = s.get(PurchaseOrderRevision, order.current_revision_id)
    assert rev is not None
    return rev


def order_lines(rev: PurchaseOrderRevision) -> list[OrderLine]:
    return [
        OrderLine(
            line_id=str(line["line_id"]),
            description=str(line["description"]),
            ordered_qty=Decimal(str(line["ordered_qty"])),
            unit=str(line["unit"]),
            unit_price=Decimal(str(line["unit_price"])),
            tax_basis=str(line.get("tax_basis", "exclusive")),
        )
        for line in rev.lines
    ]


def orders_text(s: Session, shop: Shop, with_prices: bool) -> str:
    orders = list(
        s.execute(
            select(PurchaseOrder).where(PurchaseOrder.shop_id == shop.id).order_by(PurchaseOrder.order_ref)
        ).scalars()
    )
    if not orders:
        return f"No purchase orders for {shop.name}."
    out = []
    for order in orders:
        rev = order_revision(s, order)
        lines = []
        for line in order_lines(rev):
            price = f" @ {inr(line.unit_price)}/{line.unit}" if with_prices else ""
            lines.append(f"{line.line_id} {line.description}: {qty(line.ordered_qty)} {line.unit}{price}")
        out.append(f"• {order.order_ref} r{rev.revision_no} ({order.status}) · {order.supplier_name} · " + "; ".join(lines))
    return "Purchase orders:\n" + "\n".join(out)


def confirm_order(s: Session, ctx: RequestContext, order: PurchaseOrder, revision_no: int | None) -> str:
    shop = s.get(Shop, order.shop_id)
    assert shop is not None
    require_enabled(shop)
    require_cap(s, ctx, order.shop_id, "order_confirm", "confirm orders")
    rev = order_revision(s, order)
    if revision_no is not None and revision_no != rev.revision_no:
        raise ValidationFailed(f"{order.order_ref} is at r{rev.revision_no}; reply `ok {order.order_ref} r{rev.revision_no}`.")
    if rev.status == "confirmed":
        return f"{order.order_ref} r{rev.revision_no} is already confirmed."
    rev.status, rev.confirmed_by, rev.confirmed_at = "confirmed", ctx.verified_user_id, utcnow()
    order.status, order.version = "confirmed", order.version + 1
    audit(
        s,
        action="purchase.order_confirmed",
        entity="purchase_order",
        entity_id=str(order.id),
        outcome="ok",
        actor=str(ctx.verified_user_id),
        request_id=ctx.request_id,
        practice_id=order.practice_id,
        shop_id=order.shop_id,
        context_id=ctx.context_id,
        after={"order_ref": order.order_ref, "revision": rev.revision_no},
    )
    ask_for_delivery(s, order, rev, ctx.request_id)
    link = active_link_for_order(s, order.id)
    if link is not None:
        schedule_match(s, link, ctx.request_id, context=ctx)
    lines = "; ".join(f"{qty(line.ordered_qty)} {line.unit} {line.description}" for line in order_lines(rev))
    return f"{order.order_ref} r{rev.revision_no} confirmed: {lines} from {order.supplier_name}."


def ask_for_delivery(s: Session, order: PurchaseOrder, rev: PurchaseOrderRevision, correlation_id: str) -> None:
    """Delivery question for receivers: item names and quantities only, never prices (U2 section 9)."""
    room = room_for_shop(s, order.shop_id, "delivery")
    if room is None:
        return
    first = order_lines(rev)[0]
    items = "\n".join(f"• {line.line_id} {line.description}: {qty(line.ordered_qty)} {line.unit} ordered" for line in order_lines(rev))
    post(
        s,
        room,
        action_id=f"delivery_request:{order.id}:{rev.revision_no}",
        body=(
            f"{order.order_ref} from {order.supplier_name}: please count what arrived.\n{items}\n"
            f"Reply with the count, e.g. `{order.order_ref} {first.line_id}=8`."
        ),
        correlation_id=correlation_id,
    )


# ------------------------------------------------------------------------------------- deliveries


def parse_quantities(text: str) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for key, raw in re.findall(r"\b(L\d+)\s*=\s*(-?[0-9][0-9.,]*)", text, re.I):
        try:
            value = Decimal(raw.replace(",", ""))
        except InvalidOperation as exc:
            raise ValidationFailed(f"'{raw}' is not a quantity.") from exc
        if value.as_tuple().exponent < -3:  # type: ignore[operator]
            raise ValidationFailed(f"{key.upper()}={raw}: at most 3 decimal places.")
        out[key.upper()] = value
    return out


def _report_lines_text(order: PurchaseOrder, rev: PurchaseOrderRevision, lines: list[dict[str, Any]]) -> str:
    by_id = {line.line_id: line for line in order_lines(rev)}
    return "\n".join(
        f"• {item['line_id']} {by_id[item['line_id']].description}: {qty(item['received_qty'])} {item['unit']}"
        for item in lines
    )


def submit_delivery(
    s: Session, ctx: RequestContext, event: InboxEvent, order: PurchaseOrder, report_ref: str | None, text: str
) -> str:
    shop = s.get(Shop, order.shop_id)
    assert shop is not None
    require_enabled(shop)
    require_cap(s, ctx, order.shop_id, "delivery_confirm", "report deliveries")
    if order.status != "confirmed":
        raise ValidationFailed(f"{order.order_ref} is not confirmed yet; the owner confirms it first.")
    rev = order_revision(s, order)
    counts = parse_quantities(text)
    if not counts:
        raise ValidationFailed(f"Give counts per line, e.g. `{order.order_ref} L1=8`.")
    known = {line.line_id: line for line in order_lines(rev)}
    unknown = sorted(set(counts) - set(known))
    if unknown:
        raise ValidationFailed(f"{order.order_ref} has no line {', '.join(unknown)}. Lines: {', '.join(sorted(known))}.")
    if any(v < 0 for v in counts.values()):
        raise ValidationFailed("Counts cannot be negative.")
    lines = [
        {"line_id": line_id, "received_qty": str(counts[line_id]), "unit": known[line_id].unit}
        for line_id in sorted(counts)
    ]
    if report_ref is None:
        pending = s.execute(
            select(DeliveryReport)
            .where(
                DeliveryReport.order_id == order.id,
                DeliveryReport.status == "submitted",
                DeliveryReport.submitted_by == ctx.verified_user_id,
            )
            .order_by(DeliveryReport.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        report_ref = pending.report_ref if pending else next_ref(s, order.practice_id, "DR")
    latest = s.execute(
        select(DeliveryReport)
        .where(DeliveryReport.order_id == order.id, DeliveryReport.report_ref == report_ref.upper())
        .order_by(DeliveryReport.report_version.desc())
        .limit(1)
    ).scalar_one_or_none()
    version = (latest.report_version + 1) if latest else 1
    for old in s.execute(
        select(DeliveryReport).where(
            DeliveryReport.order_id == order.id,
            DeliveryReport.report_ref == report_ref.upper(),
            DeliveryReport.status == "submitted",
        )
    ).scalars():
        old.status = "superseded"
        s.add(DeliveryEvent(practice_id=old.practice_id, shop_id=old.shop_id, report_id=old.id, action="superseded",
                            actor_user_id=ctx.verified_user_id, context_id=ctx.context_id, reason="new version submitted"))
    report = DeliveryReport(
        practice_id=order.practice_id,
        shop_id=order.shop_id,
        order_id=order.id,
        report_ref=report_ref.upper(),
        report_version=version,
        status="submitted",
        lines=lines,
        content_hash=digest({"order": str(order.id), "ref": report_ref.upper(), "v": version, "lines": lines}),
        submitted_by=ctx.verified_user_id,
        source_event_id=event.id,
    )
    s.add(report)
    s.flush()
    s.add(DeliveryEvent(practice_id=report.practice_id, shop_id=report.shop_id, report_id=report.id, action="submitted",
                        actor_user_id=ctx.verified_user_id, context_id=ctx.context_id))
    return (
        f"{report.report_ref} v{version} for {order.order_ref}:\n{_report_lines_text(order, rev, lines)}\n"
        f"Reply `ok {report.report_ref} v{version}` to confirm, or send corrected counts."
    )


def report_by_ref(s: Session, practice_id: uuid.UUID, shop_ids: list[uuid.UUID], ref: str) -> DeliveryReport:
    report = s.execute(
        select(DeliveryReport)
        .where(DeliveryReport.practice_id == practice_id, DeliveryReport.report_ref == ref.upper())
        .order_by(DeliveryReport.report_version.desc())
        .limit(1)
    ).scalar_one_or_none()
    if report is None or report.shop_id not in shop_ids:
        raise NotFound(f"No delivery report {ref.upper()} in this room.")
    return report


def confirm_delivery(s: Session, ctx: RequestContext, shop_ids: list[uuid.UUID], report_ref: str, version: int | None) -> str:
    report = s.execute(
        select(DeliveryReport)
        .where(DeliveryReport.practice_id == ctx.practice_id, DeliveryReport.report_ref == report_ref.upper())
        .order_by(DeliveryReport.report_version.desc())
        .limit(1)
        .with_for_update()
    ).scalar_one_or_none()
    if report is None or report.shop_id not in shop_ids:
        raise NotFound(f"No delivery report {report_ref.upper()} in this room.")
    order = s.get(PurchaseOrder, report.order_id)
    assert order is not None
    shop = s.get(Shop, order.shop_id)
    assert shop is not None
    require_enabled(shop)
    require_cap(s, ctx, order.shop_id, "delivery_confirm", "confirm deliveries")
    if version is not None and version != report.report_version:
        raise ValidationFailed(f"The latest is {report.report_ref} v{report.report_version}; confirm that one.")
    if report.status == "confirmed":
        return f"{report.report_ref} v{report.report_version} is already confirmed."
    if report.status != "submitted":
        raise ValidationFailed(f"{report.report_ref} v{report.report_version} is {report.status}.")
    for old in s.execute(
        select(DeliveryReport).where(
            DeliveryReport.order_id == order.id,
            DeliveryReport.report_ref == report.report_ref,
            DeliveryReport.status == "confirmed",
        )
    ).scalars():
        old.status = "superseded"
        s.add(DeliveryEvent(practice_id=old.practice_id, shop_id=old.shop_id, report_id=old.id, action="superseded",
                            actor_user_id=ctx.verified_user_id, context_id=ctx.context_id,
                            reason=f"replaced by v{report.report_version}"))
    report.status = "confirmed"
    s.add(DeliveryEvent(practice_id=report.practice_id, shop_id=report.shop_id, report_id=report.id, action="confirmed",
                        actor_user_id=ctx.verified_user_id, context_id=ctx.context_id))
    audit(
        s,
        action="purchase.delivery_confirmed",
        entity="delivery_report",
        entity_id=str(report.id),
        outcome="ok",
        actor=str(ctx.verified_user_id),
        request_id=ctx.request_id,
        practice_id=report.practice_id,
        shop_id=report.shop_id,
        context_id=ctx.context_id,
        after={"report": report.report_ref, "version": report.report_version, "lines": report.lines},
    )
    rev = order_revision(s, order)
    summary = _report_lines_text(order, rev, report.lines)
    owner_room = room_for_shop(s, order.shop_id, "shop_intake")
    if owner_room is not None:
        post(
            s,
            owner_room,
            action_id=f"delivery_confirmed:{report.id}",
            body=f"{display(s, ctx.verified_user_id)} confirmed delivery {report.report_ref} v{report.report_version} "
            f"for {order.order_ref}:\n{summary}",
            correlation_id=ctx.request_id,
        )
    link = active_link_for_order(s, order.id)
    if link is not None:
        schedule_match(s, link, ctx.request_id, context=ctx)
    return f"Thanks. {report.report_ref} v{report.report_version} confirmed for {order.order_ref}."


def received(s: Session, order_id: uuid.UUID) -> tuple[dict[str, tuple[Decimal, str]], list[str]]:
    """Sum of current confirmed report versions only (M03, M08)."""
    totals: dict[str, tuple[Decimal, str]] = {}
    refs: list[str] = []
    for report in s.execute(
        select(DeliveryReport)
        .where(DeliveryReport.order_id == order_id, DeliveryReport.status == "confirmed")
        .order_by(DeliveryReport.report_ref)
    ).scalars():
        refs.append(f"{report.report_ref}:v{report.report_version}:{report.content_hash[:16]}")
        for item in report.lines:
            have, unit = totals.get(item["line_id"], (Decimal(0), item["unit"]))
            totals[item["line_id"]] = (have + Decimal(item["received_qty"]), unit if unit == item["unit"] else "mixed")
    return totals, refs


# ------------------------------------------------------------------------------------- links


def active_link_for_order(s: Session, order_id: uuid.UUID) -> PurchaseLink | None:
    return s.execute(
        select(PurchaseLink).where(PurchaseLink.order_id == order_id, PurchaseLink.status == "active")
    ).scalar_one_or_none()


def active_link_for_case(s: Session, case_id: uuid.UUID) -> PurchaseLink | None:
    return s.execute(
        select(PurchaseLink).where(PurchaseLink.case_id == case_id, PurchaseLink.status == "active")
    ).scalar_one_or_none()


def _confirmed_revision(s: Session, case: Invoice) -> InvoiceRevision | None:
    rev = s.get(InvoiceRevision, case.current_revision_id) if case.current_revision_id else None
    return rev if rev is not None and rev.status == "confirmed" else None


def _invoice_lines(s: Session, rev: InvoiceRevision) -> list[LineItem]:
    return list(s.execute(select(LineItem).where(LineItem.revision_id == rev.id).order_by(LineItem.line_no)).scalars())


def proposed_mapping(s: Session, rev: InvoiceRevision, order: PurchaseOrder) -> dict[str, str]:
    """A proposal only: exact description match first, then by position. People confirm it (M02)."""
    lines = order_lines(order_revision(s, order))
    by_desc = {line.description.strip().lower(): line.line_id for line in lines}
    mapping: dict[str, str] = {}
    for i, item in enumerate(_invoice_lines(s, rev)):
        target = by_desc.get((item.description or "").strip().lower())
        if target is None and i < len(lines):
            target = lines[i].line_id
        if target is not None:
            mapping[str(item.line_no)] = target
    return mapping


def propose_link(s: Session, case: Invoice, correlation_id: str) -> None:
    """After the owner confirms an invoice: suggest the unique open order from the same supplier."""
    shop = s.get(Shop, case.shop_id)
    assert shop is not None
    if not enabled(shop) or active_link_for_case(s, case.id) is not None:
        return
    rev = _confirmed_revision(s, case)
    if rev is None or not rev.supplier_gstin:
        return
    candidates = [
        o
        for o in s.execute(
            select(PurchaseOrder).where(
                PurchaseOrder.shop_id == case.shop_id,
                PurchaseOrder.supplier_gstin == rev.supplier_gstin.upper(),
                PurchaseOrder.status != "cancelled",
            )
        ).scalars()
        if active_link_for_order(s, o.id) is None
    ]
    room = room_for_shop(s, case.shop_id, "shop_intake")
    if room is None or len(candidates) != 1:
        return
    order = candidates[0]
    order_rev = order_revision(s, order)
    by_id = {line.line_id: line for line in order_lines(order_rev)}
    items = {str(i.line_no): i for i in _invoice_lines(s, rev)}
    mapping = proposed_mapping(s, rev, order)
    shown = "\n".join(
        f"• invoice line {no} “{items[no].description}” → {lid} {by_id[lid].description} "
        f"(ordered {qty(by_id[lid].ordered_qty)} {by_id[lid].unit} @ {inr(by_id[lid].unit_price)})"
        for no, lid in sorted(mapping.items())
    )
    note = "" if order.status == "confirmed" else f" ({order.order_ref} is still a draft: confirm it with `ok {order.order_ref}`.)"
    post(
        s,
        room,
        action_id=f"link_proposal:{case.id}:{rev.id}",
        body=(
            f"{case.case_ref} looks like {order.order_ref} from {order.supplier_name}.{note}\n{shown}\n"
            "Linking also confirms the invoice is billed in the order's units.\n"
            f"Reply `link {case.case_ref} {order.order_ref}` to confirm, or name lines: "
            f"`link {case.case_ref} {order.order_ref} 1=L1`."
        ),
        case_ref=case.case_ref,
        correlation_id=correlation_id,
    )


def confirm_link(s: Session, ctx: RequestContext, case: Invoice, order: PurchaseOrder, text: str) -> str:
    shop = s.get(Shop, case.shop_id)
    assert shop is not None
    require_enabled(shop)
    require_cap(s, ctx, case.shop_id, "order_confirm", "link invoices to orders")
    if order.shop_id != case.shop_id:
        raise NotFound(f"No order {order.order_ref} for this shop.")
    rev = _confirmed_revision(s, case)
    if rev is None:
        raise ValidationFailed(f"Confirm {case.case_ref} first (`ok {case.case_ref}`), then link it.")
    if order.status != "confirmed":
        raise ValidationFailed(f"Confirm {order.order_ref} first (`ok {order.order_ref}`).")
    existing = active_link_for_case(s, case.id)
    if existing is not None:
        linked = s.get(PurchaseOrder, existing.order_id)
        raise OrderAlreadyLinked(f"{case.case_ref} is already linked to {linked.order_ref if linked else 'an order'}.")
    other = active_link_for_order(s, order.id)
    if other is not None:
        linked_case = s.get(Invoice, other.case_id)
        raise OrderAlreadyLinked(
            f"{order.order_ref} is already linked to {linked_case.case_ref if linked_case else 'another invoice'}; "
            "a second invoice per order is not supported in this release."
        )
    explicit = {no: lid.upper() for no, lid in re.findall(r"\b(\d+)\s*=\s*(L\d+)\b", text, re.I)}
    mapping = explicit or proposed_mapping(s, rev, order)
    known = {line.line_id for line in order_lines(order_revision(s, order))}
    if not mapping or not set(mapping.values()) <= known:
        raise ValidationFailed(f"Name the lines, e.g. `link {case.case_ref} {order.order_ref} 1=L1`.")
    link = PurchaseLink(
        practice_id=case.practice_id,
        shop_id=case.shop_id,
        case_id=case.id,
        order_id=order.id,
        mapping=mapping,
        confirmed_by=ctx.verified_user_id,
    )
    s.add(link)
    s.flush()
    case_event(s, case, "purchase_linked", ctx.request_id, {"order_ref": order.order_ref, "mapping": mapping},
               context_id=ctx.context_id)
    audit(
        s,
        action="purchase.linked",
        entity="purchase_link",
        entity_id=str(link.id),
        outcome="ok",
        actor=str(ctx.verified_user_id),
        request_id=ctx.request_id,
        practice_id=case.practice_id,
        shop_id=case.shop_id,
        context_id=ctx.context_id,
        after={"case": case.case_ref, "order": order.order_ref, "mapping": mapping},
    )
    schedule_match(s, link, ctx.request_id, context=ctx)
    pairs = ", ".join(f"line {no} → {lid}" for no, lid in sorted(mapping.items()))
    return f"{case.case_ref} linked to {order.order_ref} ({pairs}). Checking it against the delivery."


def accept_partial(s: Session, ctx: RequestContext, order: PurchaseOrder) -> str:
    shop = s.get(Shop, order.shop_id)
    assert shop is not None
    require_enabled(shop)
    require_cap(s, ctx, order.shop_id, "order_confirm", "accept partial deliveries")
    link = active_link_for_order(s, order.id)
    if link is None:
        raise ValidationFailed(f"{order.order_ref} is not linked to an invoice yet.")
    if link.partial_accepted_at is not None:
        return f"The partial delivery of {order.order_ref} is already accepted."
    link.partial_accepted_at, link.partial_accepted_by = utcnow(), ctx.verified_user_id
    link.link_version += 1
    audit(
        s,
        action="purchase.partial_accepted",
        entity="purchase_link",
        entity_id=str(link.id),
        outcome="ok",
        actor=str(ctx.verified_user_id),
        request_id=ctx.request_id,
        practice_id=link.practice_id,
        shop_id=link.shop_id,
        context_id=ctx.context_id,
    )
    schedule_match(s, link, ctx.request_id, context=ctx)
    totals, _ = received(s, order.id)
    outstanding = [
        f"{qty(line.ordered_qty - totals.get(line.line_id, (Decimal(0), line.unit))[0])} {line.unit} {line.description}"
        for line in order_lines(order_revision(s, order))
        if line.ordered_qty > totals.get(line.line_id, (Decimal(0), line.unit))[0]
    ]
    rest = f" Still outstanding on {order.order_ref}: {'; '.join(outstanding)}." if outstanding else ""
    return f"Partial delivery of {order.order_ref} accepted for this review.{rest}"


# ------------------------------------------------------------------------------------- matching


def open_blockers(s: Session, link_id: uuid.UUID) -> list[BusinessTask]:
    return list(
        s.execute(
            select(BusinessTask)
            .where(BusinessTask.link_id == link_id, BusinessTask.blocker.is_(True), BusinessTask.status.in_(OPEN_TASK))
            .order_by(BusinessTask.task_ref)
        ).scalars()
    )


def current_inputs(s: Session, link: PurchaseLink) -> tuple[MatchInput, dict[str, Any], str]:
    """The binding vector (U2 section 7) and the matcher input, read from authoritative rows."""
    case = s.get(Invoice, link.case_id)
    order = s.get(PurchaseOrder, link.order_id)
    assert case is not None and order is not None
    order_rev = order_revision(s, order)
    rev = _confirmed_revision(s, case)
    check_run = (
        s.execute(
            select(CheckRun.id).where(CheckRun.revision_id == rev.id).order_by(CheckRun.run_seq.desc()).limit(1)
        ).scalar_one_or_none()
        if rev
        else None
    )
    totals, delivery_set = received(s, order.id)
    lines = _invoice_lines(s, rev) if rev else []
    vector = {
        "case_id": str(case.id),
        "invoice_revision_id": str(rev.id) if rev else None,
        "document_generation": case.document_generation,
        "invoice_status": case.status,
        "check_run_id": str(check_run) if check_run else None,
        "link_id": str(link.id),
        "link_version": link.link_version,
        "mapping": dict(sorted(link.mapping.items())),
        "order_revision_id": str(order_rev.id),
        "order_status": order_rev.status,
        "delivery_set": delivery_set,
        "partial_accepted": link.partial_accepted_at is not None,
        "blocking_tasks": [f"{t.task_ref}:{t.status}" for t in open_blockers(s, link.id)],
        "rule_version": RULE_VERSION,
    }
    match_input = MatchInput(
        order_supplier_gstin=order.supplier_gstin,
        order_currency=order_rev.currency,
        order_lines=order_lines(order_rev),
        invoice_supplier_gstin=rev.supplier_gstin if rev else None,
        invoice_currency=rev.currency if rev else None,
        invoice_lines=[InvoiceLine(i.line_no, i.description, i.qty, i.unit_price) for i in lines],
        invoice_case_status=case.status,
        mapping=dict(link.mapping),
        received=totals,
        has_confirmed_delivery=bool(delivery_set),
        partial_accepted=link.partial_accepted_at is not None,
        invoice_confirmed=rev is not None,
        order_confirmed=order_rev.status == "confirmed",
    )
    return match_input, vector, digest(vector)


def schedule_match(
    s: Session,
    link: PurchaseLink,
    correlation_id: str,
    *,
    context: RequestContext | None = None,
    grant: ExecutionGrant | None = None,
) -> None:
    """Queue re-evaluation for the current input vector (deduplicated per vector)."""
    s.flush()
    _, _, input_hash = current_inputs(s, link)
    new_grant = issue_grant(
        s,
        operation="run_purchase_match",
        practice_id=link.practice_id,
        shop_id=link.shop_id,
        case_id=link.case_id,
        context=context,
        parent=grant,
    )
    enqueue(
        s,
        type="run_purchase_match",
        lane="fast",
        payload={"link_id": str(link.id)},
        dedupe_key=f"pmatch:{link.id}:{input_hash}",
        correlation_id=correlation_id,
        grant_id=new_grant.grant_id,
    )


def on_case_change(
    s: Session,
    case: Invoice,
    correlation_id: str,
    context: RequestContext | None,
    grant: ExecutionGrant | None,
) -> None:
    """Every invoice status change re-evaluates a linked purchase; it never changes the invoice (D-27)."""
    link = active_link_for_case(s, case.id)
    if link is None or (context is None and grant is None):
        return
    shop = s.get(Shop, case.shop_id)
    if shop is None or not enabled(shop):
        return
    schedule_match(s, link, correlation_id, context=context, grant=grant)


def latest_run(s: Session, link_id: uuid.UUID) -> PurchaseMatchRun | None:
    return s.execute(
        select(PurchaseMatchRun)
        .where(PurchaseMatchRun.link_id == link_id)
        .order_by(PurchaseMatchRun.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def run_match(s: Session, link: PurchaseLink, correlation_id: str, grant: ExecutionGrant) -> PurchaseMatchRun:
    """Fenced commit of one match for the vector read inside this transaction."""
    from domain.services import readiness

    match_input, vector, input_hash = current_inputs(s, link)
    previous = latest_run(s, link.id)
    result: MatchResult = evaluate(match_input)
    s.execute(
        insert(PurchaseMatchRun)
        .values(
            id=uuid.uuid4(),
            practice_id=link.practice_id,
            shop_id=link.shop_id,
            link_id=link.id,
            input_vector=vector,
            input_hash=input_hash,
            rule_version=RULE_VERSION,
            status=result.status,
            findings=result.findings,
            totals=result.totals,
            results_hash=result.results_hash,
        )
        .on_conflict_do_nothing(index_elements=["link_id", "input_hash", "rule_version"])
    )
    run = s.execute(
        select(PurchaseMatchRun).where(
            PurchaseMatchRun.link_id == link.id,
            PurchaseMatchRun.input_hash == input_hash,
            PurchaseMatchRun.rule_version == RULE_VERSION,
        )
    ).scalar_one()
    readiness.withdraw_if_changed(s, link, input_hash, vector, correlation_id)
    if previous is not None and previous.id == run.id:
        return run
    _announce(s, link, run, correlation_id)
    readiness.advance(s, link, run, correlation_id, grant)
    return run


def _announce(s: Session, link: PurchaseLink, run: PurchaseMatchRun, correlation_id: str) -> None:
    case = s.get(Invoice, link.case_id)
    order = s.get(PurchaseOrder, link.order_id)
    room = room_for_shop(s, link.shop_id, "shop_intake")
    assert case is not None and order is not None
    if room is None:
        return
    head = f"{order.order_ref} / {case.case_ref}"
    rules = {f["rule"] for f in run.findings}
    if run.status == "hold":
        link.purchase_state = "needs_resolution"
        reasons = "\n".join(f"• {f['message']}" for f in run.findings if f["severity"] == "hold")
        body = f"{head}: payment readiness is on hold.\n{reasons}"
        if not open_blockers(s, link.id):
            staff = holders(s, link.shop_id, "task_work")
            who = short_handle(staff[0]) if staff else "<name>"
            body += (
                "\nIt clears with a corrected invoice or more delivery evidence. Assign someone: "
                f"`task {case.case_ref} {who} tomorrow get a corrected invoice`."
            )
    elif run.status == "needs_evidence":
        link.purchase_state = "awaiting_evidence"
        waiting = [f["message"] for f in run.findings]
        body = f"{head}: waiting for evidence before purchase review.\n" + "\n".join(f"• {w}" for w in waiting)
        if "M05" in rules:
            body += f"\nIf the rest is not coming with this invoice, reply `accept-partial {order.order_ref}`."
        own_prompts = {"M06"} | ({"M07"} if all("not confirmed yet" in f["message"] for f in run.findings if f["rule"] == "M07") else set())
        if rules <= own_prompts:
            return  # waiting only for the owner's confirmation or the reviewer's include: each has its own prompt
    else:
        return  # pass: readiness.advance announces the next step
    # Keyed by what the owner reads: a change that leaves the message unchanged says nothing new.
    post(
        s,
        room,
        action_id=f"pmatch:{link.id}:{digest(body)[:24]}",
        body=body,
        case_ref=case.case_ref,
        correlation_id=correlation_id,
    )


# ------------------------------------------------------------------------------------- answers


def status_text(s: Session, shop: Shop, ref: str) -> str:
    """"What needs my attention?" for one order or invoice, from recorded facts only."""
    require_enabled(shop)
    if ref.upper().startswith("PO-"):
        order = find_order(s, shop.practice_id, [shop.id], ref)
        link = active_link_for_order(s, order.id)
        if link is None:
            totals, refs = received(s, order.id)
            got = ", ".join(f"{k} {qty(v[0])} {v[1]}" for k, v in sorted(totals.items())) or "nothing confirmed yet"
            return f"{order.order_ref} ({order.status}): not linked to an invoice yet. Received: {got}."
    else:
        case = s.execute(
            select(Invoice).where(Invoice.shop_id == shop.id, Invoice.case_ref == ref.upper())
        ).scalar_one_or_none()
        if case is None:
            raise NotFound(f"No case {ref.upper()} in this room.")
        link = active_link_for_case(s, case.id)
        if link is None:
            return f"{case.case_ref} is not linked to an order, so it is unassessed for payment readiness."
        linked_order = s.get(PurchaseOrder, link.order_id)
        assert linked_order is not None
        order = linked_order
    case = s.get(Invoice, link.case_id)
    assert case is not None
    run = latest_run(s, link.id)
    parts = [f"{order.order_ref} / {case.case_ref}: {link.purchase_state.replace('_', ' ')}."]
    if run is not None:
        for line in run.totals.get("lines", []):
            parts.append(
                f"{line['description']}: ordered {line['ordered']}, received {line['received']}, billed {line['billed']} "
                f"{line['unit']} (outstanding {line['outstanding']})."
            )
        parts += [f["message"] for f in run.findings]
    for task in open_blockers(s, link.id):
        parts.append(f"{task.task_ref}: {display(s, task.assignee_user_id)} is responsible, due {task.due_at} ({task.status.replace('_', ' ')}).")
    record = s.execute(
        select(PaymentReadiness)
        .where(PaymentReadiness.link_id == link.id, PaymentReadiness.status != "stale")
        .order_by(PaymentReadiness.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if record is not None:
        if record.status == "ready_for_payment":
            parts.append(f"{record.public_ref}: ready for payment, {inr(record.amount)}, due {record.due_date or 'unknown'}. No payment has been made.")
        elif record.status == "awaiting_owner":
            parts.append(f"{record.public_ref}: reviewed; your sign-off is pending. This is payment preparation; no payment has been made.")
        else:
            parts.append(f"{record.public_ref}: waiting for the reviewer.")
    return "\n".join(parts)
