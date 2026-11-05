import pytest
from src.db.session import SessionLocal
from src.staff.service import (
    add_employee,
    list_employees,
    mark_attendance,
    calculate_monthly_payroll,
    get_daily_shift_summary,
)


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_add_and_list_employees(db_session):
    emp = add_employee(
        shop_id="shop-sharma-kirana",
        name="Vikram Singh",
        designation="Head Cashier",
        wage_type="MONTHLY",
        base_rate=20000.0,
        db=db_session,
    )
    assert emp.id is not None
    assert emp.name == "Vikram Singh"

    all_emp = list_employees("shop-sharma-kirana", db_session)
    assert len(all_emp) >= 1
    assert any(e.name == "Vikram Singh" for e in all_emp)


def test_mark_attendance_and_payroll(db_session):
    emp = add_employee(
        shop_id="shop-sharma-kirana",
        name="Sunil Helper",
        designation="Store Helper",
        wage_type="MONTHLY",
        base_rate=15000.0,
        db=db_session,
    )

    for day in range(1, 26):
        date_str = f"2026-11-{day:02d}"
        status = "PRESENT" if day <= 22 else "HALF_DAY"
        ot = 2.0 if day == 5 else 0.0
        mark_attendance(
            shop_id="shop-sharma-kirana",
            employee_id=emp.id,
            date=date_str,
            status=status,
            overtime_hours=ot,
            db=db_session,
        )

    payroll = calculate_monthly_payroll(
        shop_id="shop-sharma-kirana",
        month=11,
        year=2026,
        db=db_session,
    )
    assert len(payroll) >= 1

    sunil_pay = next(p for p in payroll if p["employee_id"] == emp.id)
    assert sunil_pay["days_present"] == 22.0
    assert sunil_pay["days_half_day"] == 3.0
    assert sunil_pay["overtime_hours"] == 2.0
    assert sunil_pay["net_payable"] > 0.0


def test_daily_shift_summary(db_session):
    summary = get_daily_shift_summary(
        shop_id="shop-sharma-kirana",
        date="2026-11-05",
        db=db_session,
    )
    assert summary["shop_id"] == "shop-sharma-kirana"
    assert "present_count" in summary
    assert "urgent_reorder_count" in summary
    assert "urgent_reorder_items" in summary
