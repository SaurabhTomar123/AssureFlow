import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.db.session import SessionLocal
from src.db.models import Shop, Bill, GSTR2BInwardRecord, BankTransaction, ComplianceIssueModel
from src.accounts.bank_client import AccountAggregatorClient, ingest_bank_transactions
from src.accounts.three_way_recon import run_three_way_reconciliation
from src.gsp.reconciler import sync_gstr2b_feed, reconcile_shop_purchases

client = TestClient(app)


def test_bank_client_fetch_and_ingest():
    db = SessionLocal()
    try:
        shop = db.query(Shop).filter(Shop.id == "shop-sharma-kirana").first()
        assert shop is not None

        aa_client = AccountAggregatorClient(shop.gstin)
        txns = aa_client.fetch_recent_transactions("HDFC99887766")
        assert len(txns) >= 4

        count = ingest_bank_transactions(shop.id, txns, db)
        assert count >= 4

        saved = (
            db.query(BankTransaction)
            .filter(BankTransaction.shop_id == shop.id, BankTransaction.account_number == "HDFC99887766")
            .all()
        )
        assert len(saved) >= 4
    finally:
        db.close()


def test_three_way_reconciliation_logic():
    db = SessionLocal()
    try:
        shop = db.query(Shop).filter(Shop.id == "shop-sharma-kirana").first()
        assert shop is not None

        # Ensure GSTR-2B feed synced and 2-way reconciled first
        sync_gstr2b_feed(shop.id, "112026", db)
        reconcile_shop_purchases(shop.id, "112026", db)

        # Ingest bank transactions
        aa_client = AccountAggregatorClient(shop.gstin)
        txns = aa_client.fetch_recent_transactions("HDFC0001928374")
        ingest_bank_transactions(shop.id, txns, db)

        report = run_three_way_reconciliation(shop.id, db)
        assert report["shop_id"] == shop.id
        summary = report["summary"]

        assert summary["three_way_matched_count"] >= 1
        assert summary["total_settled_amount"] > 0
        assert "at_risk_disbursed_itc" in summary
        assert len(report["three_way_matched"]) >= 1

        # Check for paid without GSTR2B (Delhi Cold Beverages / DCB-2026-404)
        paid_unfiled = report["payment_without_gstr2b"]
        assert any(b["bill_number"] == "DCB-2026-404" for b in paid_unfiled)

        # Check critical compliance issue created
        issue = (
            db.query(ComplianceIssueModel)
            .filter(
                ComplianceIssueModel.shop_id == shop.id,
                ComplianceIssueModel.issue_type == "PAID_BUT_UNFILED_GSTR2B",
            )
            .first()
        )
        assert issue is not None
        assert issue.severity == "CRITICAL"
        assert issue.rupee_value_at_risk > 0

    finally:
        db.close()


def test_bank_api_endpoints():
    shop_id = "shop-sharma-kirana"

    # Ingest Statement API
    resp = client.post("/api/bank/ingest-statement", json={"shop_id": shop_id, "account_number": "ICICI123456"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    # Three-Way Reconcile API
    recon_resp = client.post("/api/bank/three-way-reconcile", json={"shop_id": shop_id})
    assert recon_resp.status_code == 200
    report = recon_resp.json()
    assert report["shop_id"] == shop_id
    assert "summary" in report
    assert "three_way_matched" in report

    # Status API
    status_resp = client.get(f"/api/bank/recon-status/{shop_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["shop_id"] == shop_id
    assert status_data["total_transactions"] >= 1
