import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.db.session import SessionLocal
from src.db.models import Shop, Bill, GSTR2BInwardRecord, ComplianceIssueModel
from src.gsp.client import GSPClient
from src.gsp.reconciler import (
    normalize_doc_number,
    normalize_gstin,
    generate_rule37a_supplier_notice,
    sync_gstr2b_feed,
    reconcile_shop_purchases,
)

client = TestClient(app)


def test_normalization_helpers():
    assert normalize_doc_number("inv / 2026 - 001 ") == "INV2026001"
    assert normalize_gstin("  07aaaaa0000a1z5  ") == "07AAAAA0000A1Z5"


def test_gsp_client_sandbox_feed():
    gsp = GSPClient()
    records = gsp.fetch_gstr2b_inward("07SHARM9999K1Z4", "112026")
    assert len(records) >= 3
    assert records[0]["supplier_gstin"] == "07MODER1111A1Z1"
    assert records[0]["invoice_number"] == "MAS-2026-101"


def test_rule37a_notice_generation():
    notice = generate_rule37a_supplier_notice(
        buyer_name="Sharma Kirana Store",
        buyer_gstin="07SHARM9999K1Z4",
        supplier_name="Modern Agro Staples Ltd",
        supplier_gstin="07MODER1111A1Z1",
        invoice_number="MAS-2026-101",
        invoice_date="2026-11-01",
        taxable_value=7400.0,
        tax_amount=370.0,
        period="112026",
    )
    assert "FORMAL NOTICE" in notice
    assert "RULE 37A" in notice
    assert "MAS-2026-101" in notice
    assert "Section 16(2)(aa)" in notice


def test_two_way_reconciliation_workflow():
    db = SessionLocal()
    try:
        shop = db.query(Shop).filter(Shop.id == "shop-sharma-kirana").first()
        assert shop is not None

        # Step 1: Sync GSTR-2B portal records
        synced = sync_gstr2b_feed(shop.id, "112026", db)
        assert synced >= 3

        # Step 2: Run reconciliation
        report = reconcile_shop_purchases(shop.id, "112026", db)
        assert report["matched_count"] >= 1
        assert report["tax_mismatch_count"] >= 1
        assert report["supplier_default_count"] >= 1
        assert report["unrecorded_purchase_count"] >= 1
        assert report["itc_at_risk"] > 0
    finally:
        db.close()


def test_gsp_api_endpoints():
    shop_id = "shop-sharma-kirana"

    # API Sync
    sync_resp = client.post("/api/gsp/sync-gstr2b", json={"shop_id": shop_id, "return_period": "112026"})
    assert sync_resp.status_code == 200
    assert sync_resp.json()["status"] == "success"

    # API Reconcile
    recon_resp = client.post("/api/gsp/reconcile", json={"shop_id": shop_id, "return_period": "112026"})
    assert recon_resp.status_code == 200
    report = recon_resp.json()
    assert report["matched_count"] >= 1
    assert "itc_at_risk" in report

    # API Summary
    sum_resp = client.get(f"/api/gsp/reconciliation-summary/{shop_id}?return_period=112026")
    assert sum_resp.status_code == 200
    summary = sum_resp.json()
    assert summary["shop_id"] == shop_id

    # API Supplier Notices
    notice_resp = client.get(f"/api/gsp/supplier-notices/{shop_id}")
    assert notice_resp.status_code == 200
    notices = notice_resp.json()
    assert len(notices) >= 1
    assert any("FORMAL NOTICE" in (n.get("supplier_notice_draft") or "") for n in notices)
