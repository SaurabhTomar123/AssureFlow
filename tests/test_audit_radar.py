import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.db.session import SessionLocal
from src.db.models import Shop, Bill, ComplianceIssueModel
from src.advisory.audit_radar import compute_shop_audit_risk

client = TestClient(app)


def test_compute_shop_audit_risk():
    db = SessionLocal()
    try:
        shop = db.query(Shop).filter(Shop.id == "shop-sharma-kirana").first()
        assert shop is not None

        radar = compute_shop_audit_risk(shop.id, db)
        assert radar["shop_id"] == shop.id
        assert 0 <= radar["audit_risk_score"] <= 100
        assert radar["risk_level"] in [
            "LOW (Audit-Proof)",
            "MODERATE",
            "ELEVATED",
            "CRITICAL (High Scrutiny Notice Risk)",
        ]
        assert 300 <= radar["credit_solvency_score"] <= 900
        assert len(radar["top_recommendations"]) >= 1

        scorecard = radar["supplier_scorecard"]
        assert len(scorecard) >= 1
        assert any(s["compliance_badge"] in ["A+ Safe Partner", "B Watchlist", "C High Defaulter Risk"] for s in scorecard)
    finally:
        db.close()


def test_audit_radar_api_endpoint():
    shop_id = "shop-sharma-kirana"
    response = client.get(f"/api/advisory/audit-radar/{shop_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["shop_id"] == shop_id
    assert "audit_risk_score" in data
    assert "credit_solvency_score" in data
    assert "supplier_scorecard" in data
