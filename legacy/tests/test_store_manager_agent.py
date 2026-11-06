import pytest
from src.db.session import SessionLocal
from src.agents.store_manager import StoreManagerAgent
from src.staff.service import add_employee


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_store_manager_stock_overview(db_session):
    agent = StoreManagerAgent()
    overview_en = agent.format_stock_overview("shop-sharma-kirana", db_session, language="en")
    assert "Inventory Health Report" in overview_en
    assert "Total Catalog SKUs" in overview_en

    overview_hi = agent.format_stock_overview("shop-sharma-kirana", db_session, language="hi")
    assert "Store Manager Stock Report" in overview_hi


def test_store_manager_reorder_and_shift(db_session):
    agent = StoreManagerAgent()
    reorder_msg = agent.format_reorder_alert("shop-sharma-kirana", db_session, language="en")
    assert "Restock" in reorder_msg or "optimal" in reorder_msg

    shift_msg = agent.format_shift_summary("shop-sharma-kirana", "2026-11-05", db_session, language="en")
    assert "Daily Shift Briefing" in shift_msg
    assert "Staff On Duty" in shift_msg


def test_store_manager_checkin_and_payroll(db_session):
    agent = StoreManagerAgent()
    add_employee(
        shop_id="shop-sharma-kirana",
        name="Anil Kumar",
        designation="Billing Executive",
        base_rate=22000.0,
        db=db_session,
    )

    checkin_res = agent.handle_checkin_command(
        shop_id="shop-sharma-kirana",
        staff_name="Anil",
        date_str="2026-11-05",
        time_str="09:15 AM",
        db=db_session,
        language="en",
    )
    assert "Attendance Logged" in checkin_res
    assert "Anil" in checkin_res

    payroll_res = agent.format_payroll_report("shop-sharma-kirana", 11, 2026, db_session, language="en")
    assert "Monthly Payroll Sheet" in payroll_res
    assert "Total Staff" in payroll_res


def test_auto_restock_announcement():
    agent = StoreManagerAgent()
    items = [
        {"name": "Aashirvaad Atta 10kg", "added_quantity": 10, "unit": "units", "new_stock": 25},
    ]
    announcement = agent.format_auto_restock_announcement(
        restocked_items=items,
        invoice_number="INV-101",
        supplier_name="Modern Agro",
    )
    assert "Auto-Restock Complete" in announcement
    assert "Aashirvaad Atta" in announcement

