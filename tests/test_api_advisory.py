from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)


def test_api_shop_ledger():
    response = client.get("/api/advisory/accounts/shop-sharma-kirana/ledger")
    assert response.status_code == 200
    data = response.json()
    assert data["shop_id"] == "shop-sharma-kirana"
    assert data["total_cash_outflow"] > 0
    assert "breakdown" in data
    assert data["breakdown"]["inventory_purchases"] > 0


def test_api_shop_tax_savings():
    response = client.get("/api/advisory/tax-savings/shop-sharma-kirana?annual_income=1200000")
    assert response.status_code == 200
    data = response.json()
    assert data["shop_id"] == "shop-sharma-kirana"
    assert data["total_combined_tax_savings"] > 0
    assert "section_32_asset_depreciation" in data
    assert "personal_tax_optimization" in data


def test_api_presumptive_tax_analysis():
    response = client.get("/api/advisory/presumptive-tax?turnover=7500000&digital_pct=80&actual_margin_pct=14")
    assert response.status_code == 200
    data = response.json()
    assert data["annual_turnover"] == 7500000.0
    assert data["is_eligible"] is True
    assert data["estimated_tax_saved_30pct"] > 0


def test_api_blocked_itc():
    response = client.get("/api/advisory/blocked-itc/shop-sharma-kirana")
    assert response.status_code == 200
    data = response.json()
    assert data["shop_id"] == "shop-sharma-kirana"
    assert "blocked_itc_items" in data
