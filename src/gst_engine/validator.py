from typing import Any, Optional
from src.gst_engine.checksum import validate_gstin_checksum
from src.gst_engine.rules import (
    validate_gstin_format,
    validate_tax_type,
    validate_math_totals,
    check_duplicate_bill,
)


class ComplianceIssue:
    def __init__(
        self,
        issue_type: str,
        severity: str,
        rupee_value_at_risk: float,
        explanation: str,
        suggested_action: str,
    ):
        self.issue_type = issue_type
        self.severity = severity
        self.rupee_value_at_risk = round(rupee_value_at_risk, 2)
        self.explanation = explanation
        self.suggested_action = suggested_action

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_type": self.issue_type,
            "severity": self.severity,
            "rupee_value_at_risk": self.rupee_value_at_risk,
            "explanation": self.explanation,
            "suggested_action": self.suggested_action,
        }


def validate_bill_compliance(
    bill_data: dict[str, Any],
    buyer_gstin: str,
    existing_bills: Optional[list[dict[str, Any]]] = None,
) -> list[ComplianceIssue]:
    issues: list[ComplianceIssue] = []

    supplier_name = bill_data.get("supplier_name")
    supplier_gstin = bill_data.get("supplier_gstin")
    bill_number = bill_data.get("bill_number")
    bill_date = bill_data.get("bill_date")
    taxable_amount = float(bill_data.get("taxable_amount") or 0.0)
    cgst = float(bill_data.get("cgst_amount") or 0.0)
    sgst = float(bill_data.get("sgst_amount") or 0.0)
    igst = float(bill_data.get("igst_amount") or 0.0)
    total_amount = float(bill_data.get("total_amount") or 0.0)
    items = bill_data.get("items") or []

    total_tax_at_risk = cgst + sgst + igst
    if total_tax_at_risk <= 0.0 and total_amount > 0.0:
        total_tax_at_risk = round(total_amount * 0.18, 2)

    if bill_data.get("is_blurry", False):
        issues.append(
            ComplianceIssue(
                issue_type="BLURRY_IMAGE",
                severity="simple",
                rupee_value_at_risk=total_tax_at_risk,
                explanation="Bill photo is blurry or unreadable.",
                suggested_action="Ask shop owner to retake a clear photo.",
            )
        )

    missing_fields = []
    if not supplier_name:
        missing_fields.append("supplier name")
    if not bill_number:
        missing_fields.append("bill number")
    if not bill_date:
        missing_fields.append("bill date")

    if missing_fields:
        issues.append(
            ComplianceIssue(
                issue_type="MISSING_MANDATORY_FIELD",
                severity="simple",
                rupee_value_at_risk=total_tax_at_risk,
                explanation=f"Missing essential fields: {', '.join(missing_fields)}.",
                suggested_action="Request owner confirmation or update.",
            )
        )

    if not supplier_gstin:
        issues.append(
            ComplianceIssue(
                issue_type="MISSING_MANDATORY_FIELD",
                severity="simple",
                rupee_value_at_risk=total_tax_at_risk,
                explanation="Supplier GSTIN is missing from invoice.",
                suggested_action="Ask owner to provide supplier GSTIN or check bill header.",
            )
        )
    else:
        is_format_valid, format_err = validate_gstin_format(supplier_gstin)
        if not is_format_valid:
            issues.append(
                ComplianceIssue(
                    issue_type="INVALID_GSTIN_FORMAT",
                    severity="serious",
                    rupee_value_at_risk=total_tax_at_risk,
                    explanation=f"Supplier GSTIN format error: {format_err}",
                    suggested_action="Review bill image and verify GST number with supplier.",
                )
            )
        else:
            is_checksum_valid = validate_gstin_checksum(supplier_gstin)
            if not is_checksum_valid:
                issues.append(
                    ComplianceIssue(
                        issue_type="INVALID_GSTIN_CHECKSUM",
                        severity="serious",
                        rupee_value_at_risk=total_tax_at_risk,
                        explanation="Supplier GSTIN check digit failed ISO 7064 verification.",
                        suggested_action="CA review required: verify with supplier or GST portal.",
                    )
                )

        if is_format_valid and buyer_gstin:
            is_tax_valid, tax_err = validate_tax_type(
                supplier_gstin=supplier_gstin,
                buyer_gstin=buyer_gstin,
                cgst=cgst,
                sgst=sgst,
                igst=igst,
            )
            if not is_tax_valid:
                issues.append(
                    ComplianceIssue(
                        issue_type="WRONG_TAX_TYPE",
                        severity="serious",
                        rupee_value_at_risk=total_tax_at_risk,
                        explanation=tax_err,
                        suggested_action="CA inquiry required: request amended invoice with correct tax type.",
                    )
                )

    is_math_valid, math_err = validate_math_totals(
        taxable_amount=taxable_amount,
        cgst=cgst,
        sgst=sgst,
        igst=igst,
        total_amount=total_amount,
        items=items,
    )
    if not is_math_valid:
        issues.append(
            ComplianceIssue(
                issue_type="TAX_CALCULATION_MISMATCH",
                severity="serious",
                rupee_value_at_risk=total_tax_at_risk,
                explanation=math_err,
                suggested_action="CA review required: calculation discrepancy requires credit note or correction.",
            )
        )

    if existing_bills and supplier_gstin and bill_number:
        is_dup, dup_id = check_duplicate_bill(
            supplier_gstin=supplier_gstin,
            bill_number=bill_number,
            existing_bills=existing_bills,
            current_bill_id=bill_data.get("id"),
        )
        if is_dup:
            issues.append(
                ComplianceIssue(
                    issue_type="DUPLICATE_INVOICE",
                    severity="serious",
                    rupee_value_at_risk=total_tax_at_risk,
                    explanation=f"Duplicate invoice detected: Bill #{bill_number} from same supplier already exists (ID: {dup_id}).",
                    suggested_action="Reject bill to prevent duplicate Input Tax Credit claim.",
                )
            )

    return issues
