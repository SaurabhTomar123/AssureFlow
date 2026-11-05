import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.db.session import SessionLocal
from src.db.init_db import reset_db
from src.db.models import Shop, Bill, BillItem, ComplianceIssueModel
from src.gst_engine.checksum import generate_valid_gstin
from src.gst_engine.validator import validate_bill_compliance


def seed_database():
    reset_db()
    db = SessionLocal()

    try:
        shop1_gstin = generate_valid_gstin("07", "SHARM9999K", "1")
        shop2_gstin = generate_valid_gstin("07", "GUPTA8888E", "1")

        shop1 = Shop(
            id="shop-sharma-kirana",
            name="Sharma Kirana Store",
            gstin=shop1_gstin,
            state_code="07",
            telegram_chat_id="-1001234567891",
        )
        shop2 = Shop(
            id="shop-gupta-electronics",
            name="Gupta Electronics",
            gstin=shop2_gstin,
            state_code="07",
            telegram_chat_id="-1001234567892",
        )
        db.add_all([shop1, shop2])
        db.commit()

        gt_path = BASE_DIR / "synthetic_data" / "ground_truth.json"
        if not gt_path.exists():
            print("ground_truth.json not found, skipping bill seeding")
            return

        with open(gt_path, "r", encoding="utf-8") as f:
            records = json.load(f)

        existing_history = []

        for record in records:
            bill = Bill(
                id=record["id"],
                shop_id=shop1.id,
                file_path=record["pdf_path"],
                file_type="pdf",
                supplier_name=record["supplier_name"],
                supplier_gstin=record["supplier_gstin"],
                supplier_state_code=record["supplier_gstin"][:2] if record["supplier_gstin"] else None,
                bill_number=record["invoice_number"],
                bill_date=record["invoice_date"],
                taxable_amount=record["taxable_amount"],
                cgst_amount=record["cgst"],
                sgst_amount=record["sgst"],
                igst_amount=record["igst"],
                total_amount=record["total_amount"],
                is_confirmed_by_owner=True,
                status="clean" if record["expected_status"] == "clean" else "flagged_issue",
            )
            db.add(bill)

            for item_data in record.get("items", []):
                item = BillItem(
                    bill_id=bill.id,
                    description=item_data["description"],
                    hsn_code=item_data.get("hsn", "1905"),
                    quantity=item_data.get("qty", 1.0),
                    rate=item_data.get("rate", 0.0),
                    tax_rate_percent=item_data.get("tax_rate", 0.0),
                    taxable_value=item_data.get("taxable_value", 0.0),
                    cgst=record["cgst"] / max(len(record.get("items", [])), 1),
                    sgst=record["sgst"] / max(len(record.get("items", [])), 1),
                    igst=record["igst"] / max(len(record.get("items", [])), 1),
                    total=item_data.get("total", 0.0),
                )
                db.add(item)

            is_blurry = "blurry" in record["filename"]
            bill_check_data = {
                "id": record["id"],
                "supplier_name": record["supplier_name"],
                "supplier_gstin": record["supplier_gstin"],
                "bill_number": record["invoice_number"],
                "bill_date": record["invoice_date"],
                "taxable_amount": record["taxable_amount"],
                "cgst_amount": record["cgst"],
                "sgst_amount": record["sgst"],
                "igst_amount": record["igst"],
                "total_amount": record["total_amount"],
                "items": record["items"],
                "is_blurry": is_blurry,
            }

            issues = validate_bill_compliance(
                bill_data=bill_check_data,
                buyer_gstin=shop1.gstin,
                existing_bills=existing_history,
            )

            for issue in issues:
                draft = None
                if issue.issue_type == "WRONG_TAX_TYPE":
                    draft = (
                        f"Subject: Amendment Request for Invoice #{bill.bill_number}\n\n"
                        f"Dear {bill.supplier_name},\n\n"
                        f"We received Invoice #{bill.bill_number} dated {bill.bill_date} "
                        f"for INR {bill.total_amount:.2f}. You charged CGST/SGST instead of IGST "
                        f"for an interstate supply between {bill.supplier_state_code} and 07 (Delhi).\n"
                        f"Please issue a revised invoice with IGST to avoid Input Tax Credit blockage."
                    )
                issue_model = ComplianceIssueModel(
                    bill_id=bill.id,
                    shop_id=shop1.id,
                    issue_type=issue.issue_type,
                    severity=issue.severity,
                    rupee_value_at_risk=issue.rupee_value_at_risk,
                    explanation=issue.explanation,
                    suggested_action=issue.suggested_action,
                    supplier_inquiry_draft=draft,
                )
                db.add(issue_model)

            existing_history.append({
                "id": record["id"],
                "supplier_gstin": record["supplier_gstin"],
                "bill_number": record["invoice_number"],
            })

        db.commit()
        print(f"Seeded 2 shops and {len(records)} bills with compliance audit trails.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
