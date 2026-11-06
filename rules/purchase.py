"""Deterministic three-way purchase matching (U2 section 6, rule version purchase_v1).

A pure function of confirmed inputs: the confirmed order revision, the current confirmed invoice revision,
the confirmed line mapping and the current confirmed delivery-report versions. Nothing here reads the
database or a model; a match is a fact computed by code, never inferred from text (M07).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

RULE_VERSION = "purchase_v1"


@dataclass(frozen=True)
class OrderLine:
    line_id: str
    description: str
    ordered_qty: Decimal
    unit: str
    unit_price: Decimal
    tax_basis: str = "exclusive"


@dataclass(frozen=True)
class InvoiceLine:
    line_no: int
    description: str | None
    qty: Decimal | None
    unit_price: Decimal | None


@dataclass
class MatchInput:
    order_supplier_gstin: str
    order_currency: str
    order_lines: list[OrderLine]
    invoice_supplier_gstin: str | None
    invoice_currency: str | None
    invoice_lines: list[InvoiceLine]
    invoice_case_status: str
    mapping: dict[str, str]  # invoice line_no (str) -> order line_id
    received: dict[str, tuple[Decimal, str]] = field(default_factory=dict)  # line_id -> (qty, unit)
    has_confirmed_delivery: bool = False
    partial_accepted: bool = False
    invoice_confirmed: bool = True
    order_confirmed: bool = True


@dataclass
class MatchResult:
    status: str  # pass | hold | needs_evidence
    findings: list[dict[str, Any]]
    totals: dict[str, Any]

    @property
    def results_hash(self) -> str:
        return digest({"status": self.status, "findings": self.findings, "totals": self.totals})


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _q(value: Decimal) -> str:
    return format(value.normalize(), "f") if value == value.to_integral() else format(value, "f")


def evaluate(m: MatchInput) -> MatchResult:
    findings: list[dict[str, Any]] = []

    def add(rule: str, severity: str, message: str, **values: Any) -> None:
        findings.append({"rule": rule, "severity": severity, "message": message, **values})

    # M07: nothing is compared until the order and the current invoice revision are confirmed by people.
    if not m.order_confirmed or not m.invoice_confirmed:
        what = "order" if not m.order_confirmed else "current invoice revision"
        add("M07", "needs_evidence", f"The {what} is not confirmed yet.")
        return MatchResult("needs_evidence", findings, {"lines": [], "rule_version": RULE_VERSION})

    # M01 identity and scope
    if not m.invoice_supplier_gstin:
        add("M01", "needs_evidence", "The invoice has no supplier GSTIN, so the supplier cannot be matched.")
    elif m.invoice_supplier_gstin.upper() != m.order_supplier_gstin.upper():
        add(
            "M01",
            "hold",
            "The invoice is from a different supplier than the order.",
            order_supplier=m.order_supplier_gstin,
            invoice_supplier=m.invoice_supplier_gstin,
        )
    if (m.invoice_currency or "INR") != "INR" or m.order_currency != "INR":
        add("M01", "hold", "Only INR purchases are supported in this release.")

    # M06 baseline invoice review
    if m.invoice_case_status != "approved":
        add(
            "M06",
            "needs_evidence",
            "The invoice has not been included by the reviewer yet (invoice review comes first).",
            invoice_status=m.invoice_case_status,
        )

    # M07 missing evidence
    if not m.mapping:
        add("M07", "needs_evidence", "No confirmed line mapping between the invoice and the order.")
    if not m.has_confirmed_delivery:
        add("M07", "needs_evidence", "No confirmed delivery report for this order yet.")

    by_id = {line.line_id: line for line in m.order_lines}
    billed: dict[str, Decimal] = {}
    # M02 line mapping
    for inv in m.invoice_lines:
        target = m.mapping.get(str(inv.line_no))
        if target is None or target not in by_id:
            add("M02", "hold", f"Invoice line {inv.line_no} is not mapped to an order line.", invoice_line=inv.line_no)
            continue
        if target in billed:
            add("M02", "hold", f"Two invoice lines map to order line {target}.", order_line=target)
            continue
        if inv.qty is None or inv.unit_price is None:
            add("M07", "needs_evidence", f"Invoice line {inv.line_no} has no quantity or unit price.")
            continue
        billed[target] = inv.qty
        order = by_id[target]
        # M04 price and basis (tax-exclusive on both sides; exact)
        if inv.unit_price != order.unit_price:
            add(
                "M04",
                "hold",
                f"{order.description}: billed at {_q(inv.unit_price)} per {order.unit}, "
                f"ordered at {_q(order.unit_price)}.",
                order_line=target,
                billed_price=_q(inv.unit_price),
                ordered_price=_q(order.unit_price),
            )

    totals_lines = []
    needs_partial = False
    for order in m.order_lines:
        got = m.received.get(order.line_id)
        received = got[0] if got else Decimal(0)
        if got and got[1] != order.unit:
            add(
                "M03",
                "hold",
                f"{order.description}: delivery was counted in {got[1]}, the order is in {order.unit}.",
                order_line=order.line_id,
            )
        qty = billed.get(order.line_id, Decimal(0))
        # M03 quantities (exact, no tolerance)
        if qty < 0 or received < 0:
            add("M03", "hold", f"{order.description}: negative quantity.", order_line=order.line_id)
        if received > order.ordered_qty:
            add(
                "M03",
                "hold",
                f"{order.description}: received {_q(received)} {order.unit}, more than the "
                f"{_q(order.ordered_qty)} ordered.",
                order_line=order.line_id,
                received=_q(received),
                ordered=_q(order.ordered_qty),
            )
        if qty > order.ordered_qty:
            add(
                "M03",
                "hold",
                f"{order.description}: billed {_q(qty)} {order.unit}, more than the {_q(order.ordered_qty)} ordered.",
                order_line=order.line_id,
                billed=_q(qty),
                ordered=_q(order.ordered_qty),
            )
        if m.has_confirmed_delivery and qty > received:
            add(
                "M03",
                "hold",
                f"{order.description}: billed {_q(qty)} {order.unit} but {_q(received)} confirmed received "
                f"(difference {_q(qty - received)}).",
                order_line=order.line_id,
                billed=_q(qty),
                received=_q(received),
                difference=_q(qty - received),
            )
        # M05 partial delivery
        if qty < order.ordered_qty:
            needs_partial = True
        totals_lines.append(
            {
                "line_id": order.line_id,
                "description": order.description,
                "unit": order.unit,
                "ordered": _q(order.ordered_qty),
                "received": _q(received),
                "billed": _q(qty),
                "outstanding": _q(max(order.ordered_qty - received, Decimal(0))),
            }
        )
    if needs_partial and not m.partial_accepted and m.has_confirmed_delivery:
        add(
            "M05",
            "needs_evidence",
            "Less was billed than ordered. The owner must accept the partial delivery for this review.",
        )

    severities = {f["severity"] for f in findings}
    status = "hold" if "hold" in severities else "needs_evidence" if severities else "pass"
    return MatchResult(
        status=status,
        findings=findings,
        totals={"lines": totals_lines, "partial_accepted": m.partial_accepted, "rule_version": RULE_VERSION},
    )
