from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)


def test_export_default_summary():
    res = client.get("/api/summary/shop-sharma-kirana/export")
    assert res.status_code == 200
    data = res.json()
    assert "summary" in data
    assert "bills" in data
    assert data["summary"]["shop_id"] == "shop-sharma-kirana"


def test_export_gstr3b_format():
    res = client.get("/api/summary/shop-sharma-kirana/export?format=gstr3b")
    assert res.status_code == 200
    data = res.json()
    assert "gstin" in data
    assert "ret_period" in data
    assert "itc_elg" in data
    assert "itc_avl" in data["itc_elg"]
    assert "itc_net" in data["itc_elg"]
    assert data["filing_status"] == "DRAFT_READY"
    assert "attachment; filename=gstr3b_shop-sharma-kirana.json" in res.headers.get("content-disposition", "")

