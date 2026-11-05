import pytest
from fastapi import HTTPException
from src.db.session import SessionLocal
from src.users.rbac import has_permission, validate_access, filter_dashboard_data_for_role
from src.users.service import create_user_profile, get_user_by_telegram_id, list_shop_users


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_rbac_permissions():
    assert has_permission("OWNER", "VIEW_FINANCIALS") is True
    assert has_permission("OWNER", "VIEW_TAX_SAVINGS") is True

    assert has_permission("MANAGER", "MANAGE_INVENTORY") is True
    assert has_permission("MANAGER", "MANAGE_PAYROLL") is True
    assert has_permission("MANAGER", "VIEW_TAX_SAVINGS") is False

    assert has_permission("STAFF", "MARK_ATTENDANCE") is True
    assert has_permission("STAFF", "MANAGE_PAYROLL") is False

    assert has_permission("CA", "VIEW_CA_PORTAL") is True
    assert has_permission("CA", "MANAGE_INVENTORY") is False


def test_validate_access_exception():
    with pytest.raises(HTTPException) as excinfo:
        validate_access("STAFF", "MANAGE_PAYROLL")
    assert excinfo.value.status_code == 403


def test_filter_dashboard_data_for_role():
    full_data = {
        "financial_summary": {"profit": 50000},
        "tax_savings_advice": {"section_80c": 150000},
        "inventory_status": {"low_stock_items": 3},
        "staff_attendance": {"present_today": 4},
        "ca_compliance": {"clean_bills": 12},
    }

    staff_view = filter_dashboard_data_for_role("STAFF", full_data)
    assert "tax_savings_advice" not in staff_view
    assert "financial_summary" not in staff_view
    assert "inventory_status" in staff_view

    manager_view = filter_dashboard_data_for_role("MANAGER", full_data)
    assert "tax_savings_advice" not in manager_view
    assert "inventory_status" in manager_view
    assert "staff_attendance" in manager_view

    owner_view = filter_dashboard_data_for_role("OWNER", full_data)
    assert "tax_savings_advice" in owner_view
    assert "financial_summary" in owner_view


def test_create_and_query_user_profile(db_session):
    profile = create_user_profile(
        shop_id="shop-sharma-kirana",
        name="Ramesh Manager",
        role="MANAGER",
        telegram_user_id="tg_ramesh_123",
        phone="9876543210",
        db=db_session,
    )
    assert profile.id is not None
    assert profile.role == "MANAGER"

    found = get_user_by_telegram_id("shop-sharma-kirana", "tg_ramesh_123", db_session)
    assert found is not None
    assert found.name == "Ramesh Manager"

    users = list_shop_users("shop-sharma-kirana", db_session)
    assert len(users) >= 1

