import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.db.session import SessionLocal
from src.db.models import Shop, Bill, ComplianceIssueModel
from src.concierge.vendor_dispute import (
    generate_dispute_token,
    decode_dispute_token,
    VendorDisputeConcierge,
)

client = TestClient(app)
concierge = VendorDisputeConcierge()


def test_token_generation_and_tampering():
    token = generate_dispute_token("issue-123", "bill-456", "shop-789")
    decoded = decode_dispute_token(token)
    assert decoded is not None
    assert decoded["issue_id"] == "issue-123"
    assert decoded["bill_id"] == "bill-456"
    assert decoded["shop_id"] == "shop-789"

    # Tampered token
    tampered = token[:-4] + "XXXX"
    assert decode_dispute_token(tampered) is None


def test_vendor_dispute_workflow():
    db = SessionLocal()
    try:
        shop = db.query(Shop).filter(Shop.id == "shop-sharma-kirana").first()
        assert shop is not None

        bill = db.query(Bill).filter(Bill.shop_id == shop.id).first()
        assert bill is not None

        issue = ComplianceIssueModel(
            bill_id=bill.id,
            shop_id=shop.id,
            issue_type="WRONG_TAX_TYPE",
            severity="serious",
            rupee_value_at_risk=1440.0,
            explanation="Interstate supply charged CGST/SGST instead of IGST.",
            suggested_action="Contact supplier for credit note or amendment.",
        )
        db.add(issue)
        db.commit()

        # Step 1: Create dispute ticket
        ticket = concierge.create_dispute_ticket(
            issue_id=issue.id,
            bill_id=bill.id,
            shop_id=shop.id,
            db=db,
        )
        assert ticket["issue_id"] == issue.id
        assert "dispute_url" in ticket
        assert "vendor_whatsapp_message" in ticket
        assert "Disputed ITC: INR 1,440.00" in ticket["vendor_whatsapp_message"]

        # Step 2: Vendor processes resolution
        token = ticket["token"]
        res = concierge.process_vendor_resolution(
            token=token,
            resolution_type="GSTR1_AMENDMENT_COMMITTED",
            notes="Will file in November GSTR-1 return",
            credit_note_ref=None,
            db=db,
        )
        assert res["status"] == "success"
        broadcast = res["multi_room_broadcast"]
        assert broadcast["shop_room"] == shop.id
        assert "Vendor Dispute Resolved" in broadcast["shop_room_message"]
        assert broadcast["ca_room"] == "ca-office"
        assert "Compliance Notice Cleared" in broadcast["ca_room_message"]

        db.refresh(issue)
        assert issue.ca_action == "resolved_by_vendor"
        assert issue.resolved_at is not None

    finally:
        db.close()


def test_concierge_api_endpoints():
    db = SessionLocal()
    try:
        shop = db.query(Shop).filter(Shop.id == "shop-sharma-kirana").first()
        bill = db.query(Bill).filter(Bill.shop_id == shop.id).first()
        issue = (
            db.query(ComplianceIssueModel)
            .filter(ComplianceIssueModel.shop_id == shop.id)
            .first()
        )
        assert issue is not None

        # API Create
        create_resp = client.post(
            "/api/concierge/dispute/create",
            json={"shop_id": shop.id, "bill_id": bill.id, "issue_id": issue.id},
        )
        assert create_resp.status_code == 200
        token = create_resp.json()["token"]

        # API Resolve
        resolve_resp = client.post(
            "/api/concierge/dispute/resolve",
            json={
                "token": token,
                "resolution_type": "CREDIT_NOTE_ISSUED",
                "notes": "Credit note issued for tax differential",
                "credit_note_ref": "CN-2026-9901",
            },
        )
        assert resolve_resp.status_code == 200
        data = resolve_resp.json()
        assert data["status"] == "success"
        assert data["resolution_type"] == "CREDIT_NOTE_ISSUED"
    finally:
        db.close()

