"""GSTR-2B two-way matching (spec section 11, Phase 6). Code matches; agents explain.

Pure function. Key = (supplier GSTIN, document type, financial year, normalized number). One-to-one by
construction: each statement line and each purchase revision lands in exactly one result. Several
candidates on either side of a key -> ambiguous, resolved only by the CA. Components are compared within
the arithmetic-contract tolerances. A match supports review; it is not an ITC eligibility decision.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal

from rules.types import Tolerances

MATCHER_VERSION = "gstr2b_match_v1"
EXACT, MISMATCH, PURCHASE_ONLY, STATEMENT_ONLY, AMBIGUOUS = (
    "exact_match",
    "mismatch",
    "purchase_only",
    "statement_only",
    "ambiguous",
)
COMPONENTS = ("taxable", "igst", "cgst", "sgst", "cess")


@dataclass(frozen=True)
class Side:
    ref: str  # case ref for purchases, "L<n>" for statement lines
    id: str
    key: str
    amounts: dict[str, Decimal]
    total: Decimal


@dataclass
class Result:
    class_: str
    key: str
    purchase: Side | None = None
    line: Side | None = None
    differences: dict[str, str] = field(default_factory=dict)


def match(purchases: list[Side], lines: list[Side], tol: Tolerances) -> list[Result]:
    by_key_p: dict[str, list[Side]] = {}
    by_key_l: dict[str, list[Side]] = {}
    for p in purchases:
        by_key_p.setdefault(p.key, []).append(p)
    for ln in lines:
        by_key_l.setdefault(ln.key, []).append(ln)
    results: list[Result] = []
    for key in sorted(set(by_key_p) | set(by_key_l)):
        ps, ls = by_key_p.get(key, []), by_key_l.get(key, [])
        if len(ps) > 1 or len(ls) > 1:
            results += [Result(AMBIGUOUS, key, purchase=p) for p in ps]
            results += [Result(AMBIGUOUS, key, line=ln) for ln in ls]
        elif ps and ls:
            p, ln = ps[0], ls[0]
            diffs = {}
            for comp in COMPONENTS:
                diff = abs(p.amounts[comp] - ln.amounts[comp])
                if diff > tol.tax_line:
                    diffs[comp] = str(p.amounts[comp] - ln.amounts[comp])
            if abs(p.total - ln.total) > tol.amount:
                diffs["invoice_value"] = str(p.total - ln.total)
            results.append(Result(MISMATCH if diffs else EXACT, key, purchase=p, line=ln, differences=diffs))
        elif ps:
            results.append(Result(PURCHASE_ONLY, key, purchase=ps[0]))
        else:
            results.append(Result(STATEMENT_ONLY, key, line=ls[0]))
    return results


def results_hash(results: list[Result]) -> str:
    rows = [
        [
            r.class_,
            r.key,
            r.purchase.ref if r.purchase else None,
            r.line.ref if r.line else None,
            r.differences,
        ]
        for r in results
    ]
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
