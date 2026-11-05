import hmac
import hashlib
import json
import base64
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from src.config import settings
from src.db.models import Bill, ComplianceIssueModel, Shop


def generate_dispute_token(issue_id: str, bill_id: str, shop_id: str) -> str:
    data = f"{issue_id}:{bill_id}:{shop_id}:{settings.JWT_SECRET_KEY}"
    sig = hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]
    raw = f"{issue_id}|{bill_id}|{shop_id}|{sig}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")


def decode_dispute_token(token: str) -> Optional[Dict[str, str]]:
    try:
        decoded = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        issue_id, bill_id, shop_id, sig = decoded.split("|")
        expected_data = f"{issue_id}:{bill_id}:{shop_id}:{settings.JWT_SECRET_KEY}"
        expected_sig = hashlib.sha256(expected_data.encode("utf-8")).hexdigest()[:16]
        if hmac.compare_digest(sig, expected_sig):
            return {"issue_id": issue_id, "bill_id": bill_id, "shop_id": shop_id}
        return None
    except Exception:
        return None


class VendorDisputeConcierge:
    def create_dispute_ticket(
        self,
        issue_id: str,
        bill_id: str,
        shop_id: str,
        db: Session,
    ) -> Dict[str, Any]:
        shop = db.query(Shop).filter(Shop.id == shop_id).first()
        bill = db.query(Bill).filter(Bill.id == bill_id).first()
        issue = db.query(ComplianceIssueModel).filter(ComplianceIssueModel.id == issue_id).first()

        if not shop or not bill or not issue:
            raise ValueError("Invalid shop, bill, or issue identifier")

        token = generate_dispute_token(issue_id, bill_id, shop_id)
        dispute_url = f"https://munimji.ai/vendor-dispute?token={token}"

        supplier_name = bill.supplier_name or "Vendor"
        tax_at_risk = issue.rupee_value_at_risk or 0.0

        vendor_whatsapp_message = (
            f"Dear Accounts Team at {supplier_name},\n"
            f"MunimJi Compliance Bot for {shop.name} has detected a GST filing discrepancy on "
            f"Invoice #{bill.bill_number or 'UNKNOWN'} (Disputed ITC: INR {tax_at_risk:,.2f}).\n\n"
            f"To prevent payment hold under Section 16(2)(aa) & Rule 37A, please select your resolution here:\n"
            f"{dispute_url}\n\n"
            f"Resolution Options:\n"
            f"1. Commit GSTR-1 Amendment in next filing.\n"
            f"2. Issue GST Credit Note.\n"
            f"3. Provide Amended Invoice Copy."
        )

        return {
            "issue_id": issue_id,
            "bill_id": bill_id,
            "shop_id": shop_id,
            "token": token,
            "dispute_url": dispute_url,
            "vendor_whatsapp_message": vendor_whatsapp_message,
        }

    def process_vendor_resolution(
        self,
        token: str,
        resolution_type: str,
        notes: str,
        credit_note_ref: Optional[str],
        db: Session,
    ) -> Dict[str, Any]:
        info = decode_dispute_token(token)
        if not info:
            raise ValueError("Invalid or tampered dispute token")

        issue = db.query(ComplianceIssueModel).filter(ComplianceIssueModel.id == info["issue_id"]).first()
        bill = db.query(Bill).filter(Bill.id == info["bill_id"]).first()
        shop = db.query(Shop).filter(Shop.id == info["shop_id"]).first()

        if not issue or not bill or not shop:
            raise ValueError("Dispute records not found")

        issue.ca_action = "resolved_by_vendor"
        issue.resolved_at = datetime.utcnow()
        db.commit()

        supplier_name = bill.supplier_name or "Supplier"
        itc_val = issue.rupee_value_at_risk or 0.0

        shop_room_msg = (
            f"Vendor Dispute Resolved: Supplier {supplier_name} responded to Invoice #{bill.bill_number}.\n"
            f"Resolution: {resolution_type}.\n"
            f"Reference: {credit_note_ref or notes or 'Acknowledged'}.\n"
            f"Input Tax Credit of INR {itc_val:,.2f} secured for your store."
        )

        ca_room_msg = (
            f"Compliance Notice Cleared: [shop-{shop.id}] Bill #{bill.bill_number} resolved with {supplier_name}.\n"
            f"Action: {resolution_type} recorded. Invoice eligible for GSTR-3B tax credit pool."
        )

        return {
            "status": "success",
            "issue_id": issue.id,
            "bill_id": bill.id,
            "resolution_type": resolution_type,
            "credit_note_ref": credit_note_ref,
            "multi_room_broadcast": {
                "shop_room": shop.id,
                "shop_room_message": shop_room_msg,
                "ca_room": "ca-office",
                "ca_room_message": ca_room_msg,
            },
        }
