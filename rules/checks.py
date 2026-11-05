"""Document scope, GSTIN, tax type, particulars and duplicate rules (profile domestic_goods_v1)."""

from __future__ import annotations

from rules.gstin import structure_problem
from rules.types import (
    BLOCKING,
    FAIL,
    NEEDS_EVIDENCE,
    PASS,
    UNSUPPORTED,
    WARNING,
    RevisionInput,
    RuleResult,
    Tolerances,
)

ZERO_TEXT = "0"


def doc_scope(rev: RevisionInput, _: Tolerances) -> RuleResult:
    """R-DOC-01: only tax invoices are in scope; other documents are held, never treated as invalid."""
    rule = RuleResult("R-DOC-01", 1, PASS, BLOCKING, "document", "Document is a tax invoice.")
    rule.inputs = {"document_type": rev.document_type}
    if rev.document_type is None:
        rule.outcome, rule.message, rule.owner_hint = (
            NEEDS_EVIDENCE,
            "Document type could not be read.",
            "owner",
        )
    elif rev.document_type != "tax_invoice":
        rule.outcome = UNSUPPORTED
        rule.message = (
            f"A {rev.document_type.replace('_', ' ')} is outside the supported profile; held for CA review."
        )
    return rule


def supplier_gstin(rev: RevisionInput, _: Tolerances) -> RuleResult:
    """R-GSTIN-01: format and check character. Says 'structure passed', never 'registered'."""
    rule = RuleResult("R-GSTIN-01", 1, PASS, BLOCKING, "gstin", "Supplier GSTIN structure passed.")
    rule.inputs = {"supplier_gstin": rev.supplier_gstin}
    problem = structure_problem(rev.supplier_gstin)
    if problem == "missing":
        rule.outcome, rule.owner_hint = NEEDS_EVIDENCE, "owner"
        rule.message = "Supplier GSTIN is not printed or not readable."
        rule.components = ("cgst", "sgst", "igst")
    elif problem:
        rule.outcome = FAIL
        rule.message = f"Supplier GSTIN structure failed: {problem}. Live registration is not verified."
        rule.components = ("cgst", "sgst", "igst")
    return rule


def recipient_gstin(rev: RevisionInput, _: Tolerances) -> RuleResult:
    """R-GSTIN-02: the recipient GSTIN equals the configured shop GSTIN."""
    rule = RuleResult("R-GSTIN-02", 1, PASS, BLOCKING, "gstin", "Recipient GSTIN is this shop.")
    rule.inputs = {"recipient_gstin": rev.recipient_gstin, "shop_gstin": rev.shop_gstin}
    if not rev.recipient_gstin:
        rule.outcome, rule.owner_hint = NEEDS_EVIDENCE, "owner"
        rule.message = "Recipient (buyer) GSTIN is not printed or not readable."
    elif rev.recipient_gstin.strip().upper() != rev.shop_gstin:
        rule.outcome = FAIL
        rule.message = f"Invoice is billed to {rev.recipient_gstin}, not this shop ({rev.shop_gstin})."
        rule.components = ("cgst", "sgst", "igst")
    return rule


def tax_type(rev: RevisionInput, _: Tolerances) -> RuleResult:
    """R-TAX-01: supplier state vs place of supply decides CGST+SGST/UTGST or IGST (IGST Act s.7/8)."""
    rule = RuleResult("R-TAX-01", 1, PASS, BLOCKING, "tax_type", "Tax type matches the place of supply.")
    supplier_state = rev.supplier_gstin[:2] if rev.supplier_gstin and len(rev.supplier_gstin) >= 2 else None
    rule.inputs = {"supplier_state": supplier_state, "place_of_supply": rev.place_of_supply}
    if not supplier_state or not rev.place_of_supply:
        rule.outcome = NEEDS_EVIDENCE
        rule.message = "Supplier state or place of supply is missing, so the tax type cannot be decided."
        rule.owner_hint = "owner"
        return rule
    cgst, sgst, igst = (str(v or ZERO_TEXT) for v in (rev.cgst_total, rev.sgst_total, rev.igst_total))
    from decimal import Decimal

    c, sg, ig = Decimal(cgst), Decimal(sgst), Decimal(igst)
    intrastate = supplier_state == rev.place_of_supply
    rule.calculation = {
        "supply": "intrastate" if intrastate else "interstate",
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
    }
    if intrastate:
        if ig != 0:
            rule.outcome = FAIL
            rule.message = (
                f"Same-state supply ({supplier_state}) must not charge IGST, but IGST {ig} is printed."
            )
            rule.components = ("igst",)
        elif c != sg:
            rule.outcome = FAIL
            rule.message = f"Same-state supply needs equal CGST and SGST; printed CGST {c}, SGST {sg}."
            rule.components = ("cgst", "sgst")
    elif c != 0 or sg != 0:
        rule.outcome = FAIL
        rule.message = (
            f"Interstate supply ({supplier_state} to {rev.place_of_supply}) must use IGST only, "
            f"but CGST {c} / SGST {sg} are printed."
        )
        rule.components = ("cgst", "sgst")
    return rule


def particulars(rev: RevisionInput, _: Tolerances) -> RuleResult:
    """R-PART-01: required particulars of the supported profile (a narrow field check, not legal compliance)."""
    rule = RuleResult("R-PART-01", 1, PASS, BLOCKING, "particulars", "Required particulars are present.")
    missing = [
        name
        for name, value in (
            ("supplier name", rev.supplier_name),
            ("invoice number", rev.invoice_number),
            ("invoice date", rev.invoice_date),
        )
        if not value
    ]
    missing += [f"line {ln.line_no} description" for ln in rev.lines if not ln.description]
    missing += [f"line {ln.line_no} HSN/SAC" for ln in rev.lines if not ln.hsn_sac]
    rule.inputs = {"missing": missing}
    if missing:
        rule.outcome = FAIL
        rule.message = "Missing particulars: " + ", ".join(missing[:5]) + "."
    return rule


def exact_duplicate(rev: RevisionInput, _: Tolerances) -> RuleResult:
    """R-DUP-01: the duplicate key (supplier GSTIN, type, FY, number) is owned by another case."""
    rule = RuleResult("R-DUP-01", 1, PASS, BLOCKING, "duplicate", "No other case has this invoice number.")
    if rev.duplicate_owner_ref:
        rule.outcome = FAIL
        rule.message = (
            f"Same supplier, document type, financial year and number as {rev.duplicate_owner_ref}."
        )
        rule.inputs = {"duplicate_of": rev.duplicate_owner_ref}
        rule.components = ("cgst", "sgst", "igst")
    return rule


def similar_duplicate(rev: RevisionInput, _: Tolerances) -> RuleResult:
    """R-DUP-02: same supplier and amount within a week: a warning for the CA, never an exclusion."""
    rule = RuleResult("R-DUP-02", 1, PASS, WARNING, "duplicate", "No similar invoice from this supplier.")
    if rev.similar_case_refs:
        rule.outcome = FAIL
        rule.message = (
            "Possible duplicate of " + ", ".join(rev.similar_case_refs) + " (same supplier and amount)."
        )
        rule.inputs = {"similar": list(rev.similar_case_refs)}
    return rule
