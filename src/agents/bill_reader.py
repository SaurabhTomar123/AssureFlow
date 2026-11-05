from typing import Any
from src.extraction.parser import extract_bill_data


class BillReaderAgent:
    def __init__(self, agent_id: str = "bill-reader"):
        self.agent_id = agent_id

    def process_document(self, file_path: str, language: str = "en") -> dict[str, Any]:
        extracted = extract_bill_data(file_path)

        supplier = extracted.get("supplier_name", "Unknown Supplier")
        bill_num = extracted.get("bill_number", "Unknown")
        total = extracted.get("total_amount", 0.0)
        taxable = extracted.get("taxable_amount", 0.0)
        cgst = extracted.get("cgst_amount", 0.0)
        sgst = extracted.get("sgst_amount", 0.0)
        igst = extracted.get("igst_amount", 0.0)
        gstin = extracted.get("supplier_gstin") or "NOT DETECTED"

        if language == "hi":
            message = (
                f"Bill Prapt Hua: {supplier}\n"
                f"Bill Sankhya: {bill_num}\n"
                f"Supplier GSTIN: {gstin}\n"
                f"Taxable Raashi: INR {taxable:.2f}\n"
                f"Tax: CGST INR {cgst:.2f}, SGST INR {sgst:.2f}, IGST INR {igst:.2f}\n"
                f"Kul Raashi: INR {total:.2f}\n\n"
                f"Kripya jaanch lein aur agar sahi hai toh 'OK' likhein, ya koi badlav ho toh likhkar bhejein."
            )
        else:
            message = (
                f"Bill Received from: {supplier}\n"
                f"Invoice No: {bill_num}\n"
                f"Supplier GSTIN: {gstin}\n"
                f"Taxable Amount: INR {taxable:.2f}\n"
                f"Tax Breakdown: CGST INR {cgst:.2f}, SGST INR {sgst:.2f}, IGST INR {igst:.2f}\n"
                f"Total Amount: INR {total:.2f}\n\n"
                f"Please verify details and reply 'OK' to confirm, or reply with corrections."
            )

        return {
            "agent_id": self.agent_id,
            "status": "extracted",
            "extracted_data": extracted,
            "confirmation_message": message,
        }
