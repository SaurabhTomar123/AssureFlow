from typing import Any, Optional
from src.gst_engine.validator import validate_bill_compliance


class GSTCheckerAgent:
    def __init__(self, agent_id: str = "gst-checker"):
        self.agent_id = agent_id

    def check_compliance(
        self,
        bill_data: dict[str, Any],
        buyer_gstin: str,
        existing_bills: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        issues = validate_bill_compliance(
            bill_data=bill_data,
            buyer_gstin=buyer_gstin,
            existing_bills=existing_bills,
        )

        simple_issues = [i for i in issues if i.severity == "simple"]
        serious_issues = [i for i in issues if i.severity == "serious"]

        status = "clean"
        if serious_issues:
            status = "requires_ca_review"
        elif simple_issues:
            status = "requires_owner_clarification"

        return {
            "agent_id": self.agent_id,
            "status": status,
            "is_clean": len(issues) == 0,
            "all_issues": [i.to_dict() for i in issues],
            "simple_issues": [i.to_dict() for i in simple_issues],
            "serious_issues": [i.to_dict() for i in serious_issues],
        }

