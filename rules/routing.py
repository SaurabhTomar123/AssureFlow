"""Deterministic issue routing: simple extraction gaps go to the owner; tax, document, duplicate and
interpretation exceptions go to the assigned CA (spec section 3, step 6)."""

from __future__ import annotations

from rules.types import NEEDS_EVIDENCE, RuleResult

FORBIDDEN_WORDING = ("money lost", "credit recovered", "registered", "itc guaranteed", "eligible itc")

NEXT_ACTION = {
    "owner": "Owner: send a clearer copy or type the correct value.",
    "ca": "CA: review and record a decision on the review request.",
}

# Categories the CA may dispose of with resolve_issue. Arithmetic, GSTIN structure and unsupported
# outcomes are never overridable in the MVP.
RESOLVABLE_CATEGORIES = {"particulars", "duplicate"}


def owner_role(result: RuleResult) -> str:
    if result.owner_hint == "owner" and result.outcome == NEEDS_EVIDENCE:
        return "owner"
    return "ca"


def can_resolve(category: str, outcome: str, has_evidence: bool) -> bool:
    if category in RESOLVABLE_CATEGORIES:
        return True
    return outcome == NEEDS_EVIDENCE and has_evidence and category not in {"arithmetic", "gstin"}
