from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.db.session import SessionLocal
from src.db.models import Shop, Bill, ComplianceIssueModel

client = TestClient(app)
BASE_DIR = Path(__file__).resolve().parent.parent
PDF_DIR = BASE_DIR / "synthetic_data" / "bills_pdf"


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_list_shops():
    response = client.get("/api/shops")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(s["id"] == "shop-sharma-kirana" for s in data)


def test_upload_bill_endpoint_clean():
    clean_shop_gstin = "07TESTS1234T1Z3"
    shop_res = client.post(
        "/api/shops",
        json={"name": "Test Upload Shop", "gstin": clean_shop_gstin},
    )
    if shop_res.status_code == 201:
        shop_id = shop_res.json()["id"]
    else:
        shop_id = client.get("/api/shops").json()[-1]["id"]

    pdf_path = PDF_DIR / "bill_01_clean_kirana_5pct.pdf"
    assert pdf_path.exists()

    with open(pdf_path, "rb") as f:
        response = client.post(
            "/api/bills/upload",
            data={"shop_id": shop_id},
            files={"file": (f"test_upload_clean_{shop_id}.pdf", f, "application/pdf")},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["bill_number"] == "MAS-2026-101"
    assert data["status"] == "clean"
    assert data["taxable_amount"] == 7400.0


def test_upload_duplicate_bill_caught():
    pdf_path = PDF_DIR / "bill_01_clean_kirana_5pct.pdf"
    assert pdf_path.exists()

    with open(pdf_path, "rb") as f:
        response = client.post(
            "/api/bills/upload",
            data={"shop_id": "shop-sharma-kirana"},
            files={"file": ("test_duplicate_bill.pdf", f, "application/pdf")},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "flagged_issue"
    issue_types = [i["issue_type"] for i in data["issues"]]
    assert "DUPLICATE_INVOICE" in issue_types


def test_confirm_bill_endpoint():
    response = client.get("/api/bills?shop_id=shop-sharma-kirana")
    assert response.status_code == 200
    bills = response.json()
    assert len(bills) > 0
    bill_id = bills[0]["id"]

    confirm_res = client.post(
        f"/api/bills/{bill_id}/confirm",
        json={"confirmed": True, "corrected_total": 7770.0},
    )
    assert confirm_res.status_code == 200
    assert confirm_res.json()["is_confirmed_by_owner"] is True


def test_issues_and_ca_decision_endpoint():
    response = client.get("/api/issues?severity=serious")
    assert response.status_code == 200
    issues = response.json()
    assert len(issues) > 0
    issue = issues[0]
    issue_id = issue["id"]

    decision_res = client.post(
        f"/api/issues/{issue_id}/decision",
        json={"action": "approve", "note": "Verified with CA offline"},
    )
    assert decision_res.status_code == 200
    updated_issue = decision_res.json()
    assert updated_issue["ca_action"] == "approve"


def test_shop_summary_and_export():
    summary_res = client.get("/api/summary/shop-sharma-kirana")
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert summary["shop_id"] == "shop-sharma-kirana"
    assert summary["total_bills"] > 0
    assert summary["eligible_itc"]["total"] >= 0.0

    export_res = client.get("/api/summary/shop-sharma-kirana/export")
    assert export_res.status_code == 200
    export_data = export_res.json()
    assert "summary" in export_data
    assert "bills" in export_data
