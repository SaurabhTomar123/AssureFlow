from typing import Any


class FollowUpAgent:
    def __init__(self, agent_id: str = "follow-up"):
        self.agent_id = agent_id

    def generate_owner_alert(
        self,
        bill_data: dict[str, Any],
        issue_data: dict[str, Any],
        language: str = "en",
    ) -> str:
        bill_no = bill_data.get("bill_number", "Unknown")
        supplier = bill_data.get("supplier_name", "Supplier")
        rupee_at_risk = float(issue_data.get("rupee_value_at_risk", 0.0))
        explanation = issue_data.get("explanation", "Discrepancy detected.")

        if language == "hi":
            return (
                f"Dhyan Dein (Shop Owner Alert):\n"
                f"Bill #{bill_no} ({supplier}) mein samasya aayi hai: {explanation}\n"
                f"Isme aapka INR {rupee_at_risk:.2f} ka GST Input Credit khatre mein hai.\n"
                f"Kripya bill ka saaf photo dobara bhejein ya supplier se sampark karein."
            )

        return (
            f"Notice for Bill #{bill_no} ({supplier}):\n"
            f"Issue: {explanation}\n"
            f"Input Tax Credit at risk: INR {rupee_at_risk:.2f}\n"
            f"Action: Please upload a clearer copy or verify details with supplier."
        )

    def generate_deadline_reminder(
        self,
        shop_name: str,
        days_remaining: int,
        bills_submitted: int,
        last_month_bills: int,
        language: str = "en",
    ) -> str:
        if language == "hi":
            return (
                f"Namaste {shop_name}!\n"
                f"GST filing deadline mein sirf {days_remaining} din bache hain.\n"
                f"Pichle mahine aapne {last_month_bills} bills bheje the, is baar abhi tak {bills_submitted} bills aaye hain.\n"
                f"Kripya bache hue purchase bills jald se jald yahan bhej dein."
            )

        return (
            f"Reminder for {shop_name}:\n"
            f"{days_remaining} days remaining until GST filing deadline.\n"
            f"Bills submitted this month: {bills_submitted} (compared to ~{last_month_bills} last month).\n"
            f"Please drop your remaining purchase invoices into this group today."
        )
