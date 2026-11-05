import pytest
from datetime import date
from fastapi.testclient import TestClient
from src.api.main import app
from src.db.session import SessionLocal
from src.db.models import Shop, Employee, AttendanceRecord, LeaveBalance, StaffAdvance, PayoutBatch, JournalEntry
from src.staff.service import (
    add_employee,
    mark_smart_attendance,
    crew_checkin,
    regularize_attendance,
    check_shift_understaffing,
    issue_staff_advance,
    get_staff_advances,
    calculate_smart_payroll,
    generate_payout_advice_batch,
    approve_payout_batch,
)

client = TestClient(app)


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_white_collar_attendance_and_late_marks(db_session):
    shop = Shop(name="Smart HR Shop 1", gstin="27AABCU9603R1Z9", state_code="27")
    db_session.add(shop)
    db_session.commit()

    manager = add_employee(
        shop_id=shop.id,
        name="Vikram Cashier",
        designation="Head Cashier",
        wage_type="MONTHLY",
        base_rate=30000.0,
        tier="WHITE_COLLAR",
        shift_start_time="09:30 AM",
        shift_end_time="06:30 PM",
        db=db_session,
    )

    rec_normal = mark_smart_attendance(
        shop_id=shop.id,
        employee_id=manager.id,
        date_str="2026-11-01",
        check_in_time="09:40 AM",
        status="PRESENT",
        db=db_session,
    )
    assert rec_normal.is_late is False

    rec_late = mark_smart_attendance(
        shop_id=shop.id,
        employee_id=manager.id,
        date_str="2026-11-02",
        check_in_time="10:15 AM",
        status="PRESENT",
        db=db_session,
    )
    assert rec_late.is_late is True

    reg_rec = regularize_attendance(
        shop_id=shop.id,
        employee_id=manager.id,
        date_str="2026-11-02",
        check_in_time="09:30 AM",
        check_out_time="06:30 PM",
        reason="Metro signal failure delay",
        db=db_session,
    )
    assert reg_rec.regularized is True
    assert reg_rec.is_late is False

    rec_leave = mark_smart_attendance(
        shop_id=shop.id,
        employee_id=manager.id,
        date_str="2026-11-03",
        status="ON_LEAVE",
        db=db_session,
    )
    assert rec_leave.status == "ON_LEAVE"

    leave_bal = db_session.query(LeaveBalance).filter(LeaveBalance.employee_id == manager.id).first()
    assert leave_bal is not None
    assert leave_bal.casual_leave == 11.0


def test_blue_collar_worked_hours_and_overtime(db_session):
    shop = Shop(name="Smart HR Shop 2", gstin="27AABCU9603R1ZA", state_code="27")
    db_session.add(shop)
    db_session.commit()

    loader = add_employee(
        shop_id=shop.id,
        name="Ramesh Loader",
        designation="Warehouse Loader",
        wage_type="DAILY",
        daily_rate=600.0,
        overtime_hourly_rate=112.5,
        tier="BLUE_COLLAR",
        db=db_session,
    )

    rec_absent = mark_smart_attendance(
        shop_id=shop.id,
        employee_id=loader.id,
        date_str="2026-11-01",
        check_in_time="08:00 AM",
        check_out_time="10:30 AM",
        status="PRESENT",
        db=db_session,
    )
    assert rec_absent.status == "ABSENT"
    assert rec_absent.worked_hours == 2.5

    rec_half = mark_smart_attendance(
        shop_id=shop.id,
        employee_id=loader.id,
        date_str="2026-11-02",
        check_in_time="08:00 AM",
        check_out_time="01:30 PM",
        status="PRESENT",
        db=db_session,
    )
    assert rec_half.status == "HALF_DAY"
    assert rec_half.worked_hours == 5.5

    rec_full = mark_smart_attendance(
        shop_id=shop.id,
        employee_id=loader.id,
        date_str="2026-11-03",
        check_in_time="08:00 AM",
        check_out_time="04:30 PM",
        status="PRESENT",
        db=db_session,
    )
    assert rec_full.status == "PRESENT"
    assert rec_full.overtime_hours == 0.0

    rec_ot = mark_smart_attendance(
        shop_id=shop.id,
        employee_id=loader.id,
        date_str="2026-11-04",
        check_in_time="08:00 AM",
        check_out_time="07:00 PM",
        status="PRESENT",
        db=db_session,
    )
    assert rec_ot.status == "PRESENT"
    assert rec_ot.worked_hours == 11.0
    assert rec_ot.overtime_hours == 3.0


def test_crew_checkin_and_understaffing(db_session):
    shop = Shop(name="Smart HR Shop 3", gstin="27AABCU9603R1ZB", state_code="27")
    db_session.add(shop)
    db_session.commit()

    emp1 = add_employee(shop.id, "Sonu Loader", tier="BLUE_COLLAR", db=db_session)
    emp2 = add_employee(shop.id, "Monu Loader", tier="BLUE_COLLAR", db=db_session)
    emp3 = add_employee(shop.id, "Mukesh Driver", tier="BLUE_COLLAR", db=db_session)

    crew_res = crew_checkin(
        shop_id=shop.id,
        date_str="2026-11-05",
        present_employee_ids=[emp1.id, emp2.name],
        shift_name="MORNING",
        db=db_session,
    )
    assert crew_res["present_count"] == 2
    assert crew_res["absent_count"] == 1
    assert "Mukesh Driver" in crew_res["absent_staff"]

    understaff = check_shift_understaffing(
        shop_id=shop.id,
        date_str="2026-11-05",
        shift_name="MORNING",
        required_minimum=3,
        db=db_session,
    )
    assert understaff["is_understaffed"] is True
    assert "Mukesh Driver" in understaff["missing_staff"]


def test_staff_advances_and_smart_payroll(db_session):
    shop = Shop(name="Smart HR Shop 4", gstin="27AABCU9603R1ZC", state_code="27")
    db_session.add(shop)
    db_session.commit()

    worker = add_employee(
        shop_id=shop.id,
        name="Chandan Helper",
        tier="BLUE_COLLAR",
        daily_rate=500.0,
        overtime_hourly_rate=95.0,
        upi_id="chandan@upi",
        db=db_session,
    )

    adv = issue_staff_advance(
        shop_id=shop.id,
        employee_id=worker.id,
        amount=1500.0,
        notes="Emergency medical advance",
        db=db_session,
    )
    assert adv.id is not None
    assert adv.amount == 1500.0

    active_advs = get_staff_advances(shop.id, db=db_session)
    assert len(active_advs) == 1
    assert active_advs[0]["remaining_balance"] == 1500.0

    for day in range(1, 11):
        mark_smart_attendance(
            shop_id=shop.id,
            employee_id=worker.id,
            date_str=f"2026-11-{day:02d}",
            check_in_time="08:00 AM",
            check_out_time="04:30 PM",
            status="PRESENT",
            db=db_session,
        )

    payroll = calculate_smart_payroll(shop_id=shop.id, month=11, year=2026, db=db_session)
    assert len(payroll) == 1
    p_worker = payroll[0]
    assert p_worker["days_present"] == 10.0
    assert p_worker["gross_salary"] == 5000.0
    assert p_worker["advance_deduction"] == 1500.0
    assert p_worker["net_payable"] == 3500.0


def test_payout_advice_batch_and_approval_workflow(db_session):
    shop = Shop(name="Smart HR Shop 5", gstin="27AABCU9603R1ZD", state_code="27")
    db_session.add(shop)
    db_session.commit()

    staff1 = add_employee(
        shop_id=shop.id,
        name="Anil Supervisor",
        tier="WHITE_COLLAR",
        base_rate=24000.0,
        bank_account_number="9876543210",
        ifsc_code="HDFC0001234",
        db=db_session,
    )

    mark_smart_attendance(
        shop_id=shop.id,
        employee_id=staff1.id,
        date_str="2026-11-01",
        check_in_time="09:30 AM",
        status="PRESENT",
        db=db_session,
    )

    batch_draft = generate_payout_advice_batch(shop_id=shop.id, month=11, year=2026, db=db_session)
    assert batch_draft["status"] == "DRAFT"
    assert batch_draft["total_gross_wages"] == 24000.0
    batch_id = batch_draft["batch_id"]

    approve_res = approve_payout_batch(batch_id=batch_id, approved_by="Proprietor Sharma", db=db_session)
    assert approve_res["status"] == "APPROVED"
    assert approve_res["journal_entry_recorded"] is True

    je = (
        db_session.query(JournalEntry)
        .filter(JournalEntry.shop_id == shop.id, JournalEntry.reference_type == "PAYROLL_BATCH")
        .first()
    )
    assert je is not None
    assert je.total_debit == 24000.0
    assert je.total_credit == 24000.0


def test_smart_attendance_api_endpoints(db_session):
    shop = Shop(name="API HR Shop", gstin="27AABCU9603R1ZE", state_code="27")
    db_session.add(shop)
    db_session.commit()

    emp = add_employee(shop.id, "Deepak Cashier", tier="WHITE_COLLAR", base_rate=20000.0, db=db_session)

    resp_att = client.post(
        f"/api/staff/{shop.id}/smart-attendance",
        json={
            "employee_id": emp.id,
            "date": "2026-11-05",
            "check_in_time": "10:30 AM",
            "status": "PRESENT",
            "shift_name": "MORNING",
        },
    )
    assert resp_att.status_code == 200
    assert resp_att.json()["is_late"] is True

    resp_reg = client.post(
        f"/api/staff/{shop.id}/regularize",
        json={
            "employee_id": emp.id,
            "date": "2026-11-05",
            "check_in_time": "09:30 AM",
            "check_out_time": "06:30 PM",
            "reason": "Traffic jam on Western Express Highway",
        },
    )
    assert resp_reg.status_code == 200
    assert resp_reg.json()["regularized"] is True

    resp_under = client.get(
        f"/api/staff/{shop.id}/shift-understaffing",
        params={"date": "2026-11-05", "shift_name": "MORNING", "required_minimum": 2},
    )
    assert resp_under.status_code == 200

    resp_adv = client.post(
        f"/api/staff/{shop.id}/advances",
        json={"employee_id": emp.id, "amount": 1000.0, "notes": "Festival advance"},
    )
    assert resp_adv.status_code == 200

    resp_adv_list = client.get(f"/api/staff/{shop.id}/advances")
    assert resp_adv_list.status_code == 200
    assert len(resp_adv_list.json()) >= 1

    resp_payroll = client.get(f"/api/staff/{shop.id}/smart-payroll", params={"month": 11, "year": 2026})
    assert resp_payroll.status_code == 200

    resp_batch = client.post(
        f"/api/staff/{shop.id}/payout-batch",
        json={"month": 11, "year": 2026},
    )
    assert resp_batch.status_code == 200
    batch_id = resp_batch.json()["batch_id"]

    resp_approve = client.post(
        f"/api/staff/payout-batch/{batch_id}/approve",
        json={"approved_by": "Owner Sharma"},
    )
    assert resp_approve.status_code == 200
    assert resp_approve.json()["status"] == "APPROVED"
