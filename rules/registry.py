"""Rule profile domestic_goods_v1: ids, versions, effective dates, references, overridable flags."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from rules import arithmetic, checks
from rules.types import RevisionInput, RuleResult, Tolerances

PROFILE = "domestic_goods_v1"


@dataclass(frozen=True)
class RuleDef:
    rule_id: str
    version: int
    category: str
    overridable: bool
    reference: str
    description: str
    fn: Callable[[RevisionInput, Tolerances], RuleResult]
    effective_from: str = "2017-07-01"


RULES: tuple[RuleDef, ...] = (
    RuleDef(
        "R-DOC-01", 1, "document", False, "CGST Rules r.46 (tax invoice)", "Document scope", checks.doc_scope
    ),
    RuleDef(
        "R-GSTIN-01",
        1,
        "gstin",
        False,
        "GSTIN format, ISO/IEC 7064 Mod 36",
        "Supplier GSTIN structure",
        checks.supplier_gstin,
    ),
    RuleDef(
        "R-GSTIN-02", 1, "gstin", False, "CGST Act s.16(2)", "Recipient is this shop", checks.recipient_gstin
    ),
    RuleDef(
        "R-TAX-01", 1, "tax_type", False, "IGST Act s.7, s.8", "Tax type vs place of supply", checks.tax_type
    ),
    RuleDef(
        "R-AMT-01",
        1,
        "arithmetic",
        False,
        "Arithmetic contract",
        "Line taxable values",
        arithmetic.check_line_taxable,
    ),
    RuleDef(
        "R-AMT-02", 1, "arithmetic", False, "Arithmetic contract", "Tax per component", arithmetic.check_tax
    ),
    RuleDef(
        "R-AMT-03", 1, "arithmetic", False, "Arithmetic contract", "Invoice total", arithmetic.check_total
    ),
    RuleDef(
        "R-PART-01", 1, "particulars", True, "CGST Rules r.46", "Required particulars", checks.particulars
    ),
    RuleDef("R-DUP-01", 1, "duplicate", True, "Duplicate key", "Exact duplicate", checks.exact_duplicate),
    RuleDef("R-DUP-02", 1, "duplicate", True, "Similarity", "Suspected duplicate", checks.similar_duplicate),
)

BY_ID = {r.rule_id: r for r in RULES}


def run_profile(rev: RevisionInput, tol: Tolerances) -> list[RuleResult]:
    return [rule.fn(rev, tol) for rule in RULES]


def results_hash(results: list[RuleResult]) -> str:
    canonical = [
        {
            "rule": r.rule_id,
            "v": r.version,
            "outcome": r.outcome,
            "severity": r.severity,
            "calc": r.calculation,
            "diff": None if r.difference is None else str(r.difference),
        }
        for r in sorted(results, key=lambda r: r.rule_id)
    ]
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
