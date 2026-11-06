import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.db.session import SessionLocal
from src.db.init_db import reset_db
from src.db.models import (
    Tenant,
    OrganizationUser,
    Shop,
    Bill,
    BillItem,
    ComplianceIssueModel,
    UserProfile,
    InventoryItem,
    Employee,
    AttendanceRecord,
)
from src.auth.jwt_handler import get_password_hash
from src.gst_engine.checksum import generate_valid_gstin
from src.gst_engine.validator import validate_bill_compliance
from src.inventory.service import restock_inventory_from_bill


def seed_database():
    reset_db()
    db = SessionLocal()

    try:
        tenant = Tenant(
            id="tenant-sharma-group",
            name="Sharma Commercial Enterprise",
            pan="SHARM9999K",
            gstin=generate_valid_gstin("07", "SHARM9999K", "1"),
            tier="ENTERPRISE",
        )
        db.add(tenant)
        db.flush()

        admin_user = OrganizationUser(
            id="user-admin-sharma",
            tenant_id=tenant.id,
            email="admin@munimji.ai",
            hashed_password=get_password_hash("MunimJi@2026"),
            full_name="Rajesh Sharma",
            role="TENANT_ADMIN",
        )
        db.add(admin_user)

        shop1_gstin = generate_valid_gstin("07", "SHARM9999K", "1")
        shop2_gstin = generate_valid_gstin("07", "GUPTA8888E", "1")

        shop1 = Shop(
            id="shop-sharma-kirana",
            tenant_id=tenant.id,
            name="Sharma Kirana Store",
            gstin=shop1_gstin,
            state_code="07",
            telegram_chat_id="-1001234567891",
        )
        shop2 = Shop(
            id="shop-gupta-electronics",
            tenant_id=tenant.id,
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

        # Seed User Profiles
        owner = UserProfile(
            shop_id=shop1.id,
            name="Harsh Gupta",
            role="OWNER",
            telegram_user_id="tg_owner_harsh",
            phone="9811122233",
        )
        manager = UserProfile(
            shop_id=shop1.id,
            name="Ramesh Store Manager",
            role="MANAGER",
            telegram_user_id="tg_manager_ramesh",
            phone="9822233344",
        )
        staff = UserProfile(
            shop_id=shop1.id,
            name="Vikram Cashier",
            role="STAFF",
            telegram_user_id="tg_staff_vikram",
            phone="9833344455",
        )
        ca_profile = UserProfile(
            shop_id=shop1.id,
            name="CA Sanjay Verma",
            role="CA",
            telegram_user_id="tg_ca_sanjay",
            phone="9844455566",
        )
        db.add_all([owner, manager, staff, ca_profile])

        # Seed Employees and initial Attendance
        emp1 = Employee(
            shop_id=shop1.id,
            name="Ramesh Store Manager",
            designation="Store Manager",
            wage_type="MONTHLY",
            base_rate=30000.0,
        )
        emp2 = Employee(
            shop_id=shop1.id,
            name="Vikram Cashier",
            designation="Head Cashier",
            wage_type="MONTHLY",
            base_rate=20000.0,
        )
        emp3 = Employee(
            shop_id=shop1.id,
            name="Sunil Helper",
            designation="Floor Helper",
            wage_type="MONTHLY",
            base_rate=15000.0,
        )
        db.add_all([emp1, emp2, emp3])
        db.commit()

        for emp in [emp1, emp2, emp3]:
            for day in range(1, 6):
                att = AttendanceRecord(
                    shop_id=shop1.id,
                    employee_id=emp.id,
                    date=f"2026-11-{day:02d}",
                    status="PRESENT",
                    check_in_time="09:15 AM",
                    check_out_time="08:30 PM",
                )
                db.add(att)

        # Auto-restock inventory from first 5 clean bills
        clean_bills = db.query(Bill).filter(Bill.shop_id == shop1.id, Bill.status == "clean").all()
        for b in clean_bills[:5]:
            restock_inventory_from_bill(b.id, db)

        db.commit()
        print(f"Seeded 2 shops, {len(records)} bills, 4 user profiles, 3 employees, and inventory.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()

