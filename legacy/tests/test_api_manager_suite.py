from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)


def test_dashboard_html_rendering():
    response = client.get("/dashboard?shop_id=shop-sharma-kirana&role=OWNER")
    assert response.status_code == 200
    assert "MunimJi Retail & Compliance Cockpit" in response.text
    assert "Live Role Switcher" in response.text
    assert "Sharma Kirana Store" in response.text


def test_dashboard_metrics_role_filtering():
    res_owner = client.get("/api/dashboard/metrics/shop-sharma-kirana?role=OWNER")
    assert res_owner.status_code == 200
    data_owner = res_owner.json()
    assert "financial_summary" in data_owner
    assert "tax_savings_advice" in data_owner

    res_manager = client.get("/api/dashboard/metrics/shop-sharma-kirana?role=MANAGER")
    assert res_manager.status_code == 200
    data_mgr = res_manager.json()
    assert "tax_savings_advice" not in data_mgr
    assert "inventory_status" in data_mgr
    assert "staff_attendance" in data_mgr

    res_staff = client.get("/api/dashboard/metrics/shop-sharma-kirana?role=STAFF")
    assert res_staff.status_code == 200
    data_staff = res_staff.json()
    assert "financial_summary" not in data_staff
    assert "tax_savings_advice" not in data_staff


def test_users_api_flow():
    post_res = client.post(
        "/api/users",
        json={
            "shop_id": "shop-sharma-kirana",
            "name": "Karan Manager",
            "role": "MANAGER",
            "telegram_user_id": "tg_karan_99",
        },
    )
    assert post_res.status_code == 201
    user = post_res.json()
    assert user["name"] == "Karan Manager"
    assert user["role"] == "MANAGER"

    list_res = client.get("/api/users/shop-sharma-kirana")
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1


def test_inventory_api_flow():
    inv_res = client.get("/api/inventory/shop-sharma-kirana")
    assert inv_res.status_code == 200
    catalog = inv_res.json()
    assert len(catalog) >= 1
    sample_sku = catalog[0]["sku"]

    out_res = client.post(
        "/api/inventory/shop-sharma-kirana/stock-out",
        json={"sku": sample_sku, "quantity": 1.0, "reason": "SALE"},
    )
    assert out_res.status_code == 200
    assert "new_stock" in out_res.json()

    low_res = client.get("/api/inventory/shop-sharma-kirana/low-stock")
    assert low_res.status_code == 200


def test_staff_api_flow():
    create_res = client.post(
        "/api/staff/shop-sharma-kirana",
        json={
            "name": "Deepak Sharma",
            "designation": "Delivery Associate",
            "wage_type": "MONTHLY",
            "base_rate": 16000.0,
        },
    )
    assert create_res.status_code == 201
    emp_id = create_res.json()["id"]

    att_res = client.post(
        "/api/staff/shop-sharma-kirana/attendance",
        json={
            "employee_id": emp_id,
            "date": "2026-11-05",
            "status": "PRESENT",
            "check_in_time": "09:00 AM",
        },
    )
    assert att_res.status_code == 200
    assert att_res.json()["attendance_status"] == "PRESENT"

    payroll_res = client.get("/api/staff/shop-sharma-kirana/payroll?month=11&year=2026")
    assert payroll_res.status_code == 200
    assert len(payroll_res.json()) >= 1

    shift_res = client.get("/api/staff/shop-sharma-kirana/shift-summary?date=2026-11-05")
    assert shift_res.status_code == 200
    assert shift_res.json()["present_count"] >= 1

