from typing import Any


class ReturnPreparerAgent:
    def __init__(self, agent_id: str = "return-preparer"):
        self.agent_id = agent_id

    def format_ca_alert(
        self,
        shop_name: str,
        bill_data: dict[str, Any],
        issue_data: dict[str, Any],
    ) -> dict[str, Any]:
        bill_no = bill_data.get("bill_number", "Unknown")
        supplier = bill_data.get("supplier_name", "Unknown Supplier")
        supplier_gstin = bill_data.get("supplier_gstin", "N/A")
        total = bill_data.get("total_amount", 0.0)
        rupee_at_risk = float(issue_data.get("rupee_value_at_risk", 0.0))
        issue_type = issue_data.get("issue_type", "DEFECT")
        explanation = issue_data.get("explanation", "")

        message = (
            f"CA Action Required: Compliance Flag\n"
            f"Shop: {shop_name}\n"
            f"Invoice: #{bill_no} | Date: {bill_data.get('bill_date', 'N/A')}\n"
            f"Supplier: {supplier} (GSTIN: {supplier_gstin})\n"
            f"Invoice Value: INR {total:.2f}\n"
            f"Flagged Issue [{issue_type}]: {explanation}\n"
            f"ITC Disputed: INR {rupee_at_risk:.2f}\n\n"
            f"Options:\n"
            f"1. /approve {bill_data.get('id', '')} - Accept risk and retain in filing pool\n"
            f"2. /reject {bill_data.get('id', '')} - Disallow ITC from GSTR-3B\n"
            f"3. /ask_supplier {bill_data.get('id', '')} - Generate notice to supplier"
        )

        inquiry_draft = (
            f"Subject: Formal Discrepancy Notice for Invoice #{bill_no}\n\n"
            f"Dear Accounts Team at {supplier},\n\n"
            f"During GST compliance audit for {shop_name}, an issue was identified on invoice #{bill_no} "
            f"dated {bill_data.get('bill_date', 'N/A')} for INR {total:.2f}.\n\n"
            f"Issue: {explanation}\n"
            f"Under Section 16(2) of the CGST Act, Input Tax Credit cannot be claimed with this mismatch.\n"
            f"Please issue an amended tax invoice or credit note immediately.\n\n"
            f"Sincerely,\n"
            f"Tax & Compliance Office, on behalf of {shop_name}"
        )

        return {
            "agent_id": self.agent_id,
            "ca_message": message,
            "inquiry_draft": inquiry_draft,
        }

    def format_month_end_summary(self, summary_data: dict[str, Any]) -> str:
        shop_name = summary_data.get("shop_name", "Shop")
        shop_gstin = summary_data.get("shop_gstin", "")
        clean_count = summary_data.get("clean_bills", 0)
        open_issues = summary_data.get("open_issues_count", 0)
        itc = summary_data.get("eligible_itc", {})
        itc_at_risk = summary_data.get("itc_at_risk", 0.0)

        return (
            f"Month-End GSTR Compliance Report\n"
            f"Entity: {shop_name} ({shop_gstin})\n"
            f"----------------------------------------\n"
            f"Clean Invoices Ready for Filing: {clean_count}\n"
            f"Unresolved Compliance Issues: {open_issues} (ITC at Risk: INR {itc_at_risk:.2f})\n\n"
            f"Eligible Input Tax Credit (ITC) Summary:\n"
            f"- CGST: INR {itc.get('cgst', 0.0):.2f}\n"
            f"- SGST: INR {itc.get('sgst', 0.0):.2f}\n"
            f"- IGST: INR {itc.get('igst', 0.0):.2f}\n"
            f"- Total Eligible ITC: INR {itc.get('total', 0.0):.2f}\n"
            f"----------------------------------------\n"
            f"Status: Ready for CA review and filing export."
        )

