"""Arithmetic contract (spec section 5).

* Decimal end to end, context precision 28, no rounding inside a calculation chain.
* Round to paise with ROUND_HALF_UP once, at the level the document prints the value.
* Tax tolerance per line or rate group: TAX_LINE_TOLERANCE_INR x lines aggregated.
* Total tolerance, separately: AMOUNT_TOLERANCE_INR. Passing one never excuses the other.
* Combined-rate-only, missing rates, conflicting tax, cess, non-INR -> needs_evidence / unsupported.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Context, Decimal, localcontext

from rules.types import (
    BLOCKING,
    FAIL,
    NEEDS_EVIDENCE,
    PASS,
    UNSUPPORTED,
    LineInput,
    RevisionInput,
    RuleResult,
    Tolerances,
    s,
)

PAISE = Decimal("0.01")
HUNDRED = Decimal(100)
ZERO = Decimal(0)
COMPONENTS = ("cgst", "sgst", "igst")
CTX = Context(prec=28)


def paise(value: Decimal) -> Decimal:
    return value.quantize(PAISE, rounding=ROUND_HALF_UP)


def _z(value: Decimal | None) -> Decimal:
    return ZERO if value is None else value


def check_line_taxable(rev: RevisionInput, tol: Tolerances) -> RuleResult:
    """R-AMT-01: line taxable = qty x unit price - discount; lines sum to the taxable total."""
    rule = RuleResult("R-AMT-01", 1, PASS, BLOCKING, "arithmetic", "Line taxable values add up.")
    if not rev.lines:
        rule.outcome, rule.message = (
            NEEDS_EVIDENCE,
            "No line items were read, so line values cannot be checked.",
        )
        rule.owner_hint = "owner"
        return rule
    lines_calc = []
    worst = ZERO
    with localcontext(CTX):
        for line in rev.lines:
            if line.taxable_value is None:
                rule.outcome = NEEDS_EVIDENCE
                rule.message = f"Line {line.line_no} has no printed taxable value."
                rule.owner_hint = "owner"
                return rule
            if line.qty is None or line.unit_price is None:
                lines_calc.append(
                    {"line_no": line.line_no, "printed": s(line.taxable_value), "computed": None}
                )
                continue
            unrounded = line.qty * line.unit_price - _z(line.discount)
            rounded = paise(unrounded)
            diff = abs(rounded - line.taxable_value)
            worst = max(worst, diff)
            lines_calc.append(
                {
                    "line_no": line.line_no,
                    "unrounded": str(unrounded),
                    "rounded": str(rounded),
                    "printed": s(line.taxable_value),
                    "difference": str(diff),
                }
            )
            if diff > tol.tax_line:
                rule.outcome = FAIL
                rule.message = (
                    f"Line {line.line_no}: {line.qty} x {line.unit_price} - {_z(line.discount)} = {rounded}, "
                    f"but the invoice prints {line.taxable_value}."
                )
        printed_sum = sum((line.taxable_value for line in rev.lines if line.taxable_value is not None), ZERO)
        sum_tol = tol.tax_line * len(rev.lines)
    rule.calculation = {"basis": "line", "lines": lines_calc, "lines_sum": str(printed_sum)}
    if rev.taxable_total is None:
        rule.outcome, rule.message, rule.owner_hint = (
            NEEDS_EVIDENCE,
            "Taxable total is not readable.",
            "owner",
        )
        return rule
    total_diff = abs(printed_sum - rev.taxable_total)
    rule.calculation.update(
        {"taxable_total": s(rev.taxable_total), "sum_difference": str(total_diff), "tolerance": str(sum_tol)}
    )
    rule.difference = max(worst, total_diff)
    if total_diff > sum_tol and rule.outcome == PASS:
        rule.outcome = FAIL
        rule.message = (
            f"Line taxable values sum to {printed_sum}, but the taxable total is {rev.taxable_total}."
        )
    return rule


def _rate_problem(line: LineInput) -> str | None:
    has_component_rate = any(r is not None for r in (line.cgst_rate, line.sgst_rate, line.igst_rate))
    if line.combined_rate is not None and not has_component_rate:
        return f"Line {line.line_no} prints only a combined rate ({line.combined_rate}%); the split is not inferred."
    for comp in COMPONENTS:
        amount = getattr(line, f"{comp}_amount")
        rate = getattr(line, f"{comp}_rate")
        if amount not in (None, ZERO) and rate is None:
            return f"Line {line.line_no} prints {comp.upper()} {amount} without its rate."
    return None


def check_tax(rev: RevisionInput, tol: Tolerances) -> RuleResult:
    """R-AMT-02: each component computed from its own printed rate against the applicable base."""
    rule = RuleResult("R-AMT-02", 1, PASS, BLOCKING, "arithmetic", "Tax amounts match the printed rates.")
    if (rev.currency or "INR").upper() != "INR":
        rule.outcome, rule.message = UNSUPPORTED, f"Amounts are in {rev.currency}; only INR is supported."
        return rule
    if _z(rev.cess_total) != ZERO:
        rule.outcome, rule.message = UNSUPPORTED, "Cess is printed; cess calculations are not supported."
        rule.components = ("cess",)
        return rule
    if not rev.lines:
        rule.outcome, rule.message, rule.owner_hint = (
            NEEDS_EVIDENCE,
            "No line items to compute tax from.",
            "owner",
        )
        return rule
    for line in rev.lines:
        problem = _rate_problem(line)
        if problem:
            rule.outcome, rule.message = NEEDS_EVIDENCE, problem
            return rule
    calc: dict[str, object] = {"basis": "line" if rev.tax_printed_per_line else "rate_group"}
    failures: list[str] = []
    worst = ZERO
    with localcontext(CTX):
        if rev.tax_printed_per_line:
            per_line = []
            for line in rev.lines:
                for comp in COMPONENTS:
                    rate = getattr(line, f"{comp}_rate")
                    printed = getattr(line, f"{comp}_amount")
                    if rate is None and printed is None:
                        continue
                    base = _z(line.taxable_value)
                    unrounded = base * _z(rate) / HUNDRED
                    rounded = paise(unrounded)
                    diff = abs(rounded - _z(printed))
                    worst = max(worst, diff)
                    per_line.append(
                        {
                            "line_no": line.line_no,
                            "component": comp,
                            "base": str(base),
                            "rate": s(rate),
                            "unrounded": str(unrounded),
                            "rounded": str(rounded),
                            "printed": s(printed),
                            "difference": str(diff),
                        }
                    )
                    if diff > tol.tax_line:
                        failures.append(
                            f"line {line.line_no} {comp.upper()} should be {rounded}, printed {printed}"
                        )
            calc["lines"] = per_line
            computed_totals = {
                comp: sum((_z(getattr(line, f"{comp}_amount")) for line in rev.lines), ZERO)
                for comp in COMPONENTS
            }
            aggregated = len(rev.lines)
        else:
            groups: dict[tuple[str, str, str], list[LineInput]] = {}
            for line in rev.lines:
                key = (s(line.cgst_rate) or "-", s(line.sgst_rate) or "-", s(line.igst_rate) or "-")
                groups.setdefault(key, []).append(line)
            group_calc = []
            computed_totals = {comp: ZERO for comp in COMPONENTS}
            for key, members in sorted(groups.items()):
                base = sum((_z(m.taxable_value) for m in members), ZERO)
                entry: dict[str, object] = {
                    "rates": list(key),
                    "lines": [m.line_no for m in members],
                    "base": str(base),
                }
                for comp, rate_text in zip(COMPONENTS, key, strict=True):
                    if rate_text == "-":
                        continue
                    unrounded = base * Decimal(rate_text) / HUNDRED
                    rounded = paise(unrounded)
                    computed_totals[comp] += rounded
                    entry[comp] = {"unrounded": str(unrounded), "rounded": str(rounded)}
                group_calc.append(entry)
            calc["groups"] = group_calc
            aggregated = len(rev.lines)
        component_calc = {}
        for comp in COMPONENTS:
            printed_total = getattr(rev, f"{comp}_total")
            computed = computed_totals[comp]
            group_tol = tol.tax_line * aggregated
            diff = abs(computed - _z(printed_total))
            worst = max(worst, diff)
            component_calc[comp] = {
                "computed": str(computed),
                "printed": s(printed_total),
                "difference": str(diff),
                "tolerance": str(group_tol),
            }
            if diff > group_tol:
                failures.append(f"{comp.upper()} total should be {computed}, printed {_z(printed_total)}")
                rule.components = (*rule.components, comp)
        calc["components"] = component_calc
    rule.calculation = calc
    rule.difference = worst
    if failures:
        rule.outcome = FAIL
        rule.message = "Tax does not match the printed rates: " + "; ".join(failures[:3]) + "."
        if not rule.components:
            rule.components = COMPONENTS
    return rule


def check_total(rev: RevisionInput, tol: Tolerances) -> RuleResult:
    """R-AMT-03: taxable + taxes + cess + round-off = printed total, within AMOUNT_TOLERANCE_INR."""
    rule = RuleResult("R-AMT-03", 1, PASS, BLOCKING, "arithmetic", "Invoice total adds up.")
    if rev.taxable_total is None or rev.invoice_total is None:
        rule.outcome, rule.message, rule.owner_hint = (
            NEEDS_EVIDENCE,
            "Taxable total or invoice total is missing.",
            "owner",
        )
        return rule
    with localcontext(CTX):
        computed = (
            rev.taxable_total
            + _z(rev.cgst_total)
            + _z(rev.sgst_total)
            + _z(rev.igst_total)
            + _z(rev.cess_total)
            + _z(rev.round_off)
        )
        diff = abs(computed - rev.invoice_total)
    rule.calculation = {
        "taxable": s(rev.taxable_total),
        "cgst": s(rev.cgst_total),
        "sgst": s(rev.sgst_total),
        "igst": s(rev.igst_total),
        "cess": s(rev.cess_total),
        "round_off": s(rev.round_off),
        "computed_total": str(computed),
        "printed_total": s(rev.invoice_total),
        "difference": str(diff),
        "tolerance": str(tol.amount),
    }
    rule.difference = diff
    if diff > tol.amount:
        rule.outcome = FAIL
        rule.message = (
            f"The parts add up to {computed}, but the invoice total is {rev.invoice_total} (off by {diff})."
        )
        rule.components = COMPONENTS
    return rule
