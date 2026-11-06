from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from src.db.models import (
    Employee,
    AttendanceRecord,
    PayrollRecord,
    StockMovement,
    LeaveBalance,
    StaffAdvance,
    PayoutBatch,
)
from src.inventory.service import get_low_stock_report
from src.accounts.double_entry import create_journal_entry


def add_employee(
    shop_id: str,
    name: str,
    designation: str = "Store Associate",
    wage_type: str = "MONTHLY",
    base_rate: float = 18000.0,
    joining_date: str = "2026-01-01",
    tier: str = "WHITE_COLLAR",
    daily_rate: float = 600.0,
    overtime_hourly_rate: float = 112.5,
    shift_start_time: str = "09:30",
    shift_end_time: str = "18:30",
    epf_eligible: bool = False,
    esic_eligible: bool = False,
    pan: Optional[str] = None,
    bank_account_number: Optional[str] = None,
    ifsc_code: Optional[str] = None,
    upi_id: Optional[str] = None,
    db: Session = None,
) -> Employee:
    norm_wage = wage_type.strip().upper()
    if norm_wage not in ["MONTHLY", "DAILY"]:
        norm_wage = "MONTHLY"

    norm_tier = tier.strip().upper()
    if norm_tier not in ["WHITE_COLLAR", "BLUE_COLLAR"]:
        norm_tier = "WHITE_COLLAR" if norm_wage == "MONTHLY" else "BLUE_COLLAR"

    emp = Employee(
        shop_id=shop_id,
        name=name.strip(),
        designation=designation.strip(),
        wage_type=norm_wage,
        base_rate=base_rate,
        joining_date=joining_date,
        tier=norm_tier,
        daily_rate=daily_rate,
        overtime_hourly_rate=overtime_hourly_rate,
        shift_start_time=shift_start_time,
        shift_end_time=shift_end_time,
        epf_eligible=epf_eligible,
        esic_eligible=esic_eligible,
        pan=pan,
        bank_account_number=bank_account_number,
        ifsc_code=ifsc_code,
        upi_id=upi_id,
        is_active=True,
    )
    db.add(emp)
    db.flush()

    leave_bal = LeaveBalance(
        employee_id=emp.id,
        casual_leave=12.0,
        sick_leave=6.0,
        paid_leave=15.0,
        year=date.today().year,
    )
    db.add(leave_bal)

    db.commit()
    db.refresh(emp)
    return emp
    db.refresh(emp)
    return emp


def list_employees(shop_id: str, db: Session) -> List[Employee]:
    return db.query(Employee).filter(Employee.shop_id == shop_id, Employee.is_active == True).all()


def mark_attendance(
    shop_id: str,
    employee_id: str,
    date: str,
    status: str = "PRESENT",
    check_in_time: Optional[str] = "09:30 AM",
    check_out_time: Optional[str] = "08:30 PM",
    overtime_hours: float = 0.0,
    notes: Optional[str] = None,
    db: Session = None,
) -> AttendanceRecord:
    norm_status = status.strip().upper()
    if norm_status not in ["PRESENT", "ABSENT", "HALF_DAY", "ON_LEAVE"]:
        norm_status = "PRESENT"

    record = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.employee_id == employee_id, AttendanceRecord.date == date)
        .first()
    )

    if record:
        record.status = norm_status
        record.check_in_time = check_in_time
        record.check_out_time = check_out_time
        record.overtime_hours = overtime_hours
        record.notes = notes
    else:
        record = AttendanceRecord(
            shop_id=shop_id,
            employee_id=employee_id,
            date=date,
            status=norm_status,
            check_in_time=check_in_time,
            check_out_time=check_out_time,
            overtime_hours=overtime_hours,
            notes=notes,
        )
        db.add(record)

    db.commit()
    db.refresh(record)
    return record


def calculate_monthly_payroll(
    shop_id: str,
    month: int,
    year: int = 2026,
    db: Session = None,
) -> List[dict[str, Any]]:
    employees = list_employees(shop_id, db)
    payroll_summaries = []

    for emp in employees:
        records = (
            db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.employee_id == emp.id,
                AttendanceRecord.date.like(f"{year}-{month:02d}-%"),
            )
            .all()
        )

        days_present = sum(1.0 for r in records if r.status == "PRESENT")
        days_half_day = sum(1.0 for r in records if r.status == "HALF_DAY")
        days_absent = sum(1.0 for r in records if r.status == "ABSENT")
        days_leave = sum(1.0 for r in records if r.status == "ON_LEAVE")
        total_overtime = sum(r.overtime_hours or 0.0 for r in records)

        effective_days = days_present + (days_half_day * 0.5) + (days_leave * 1.0)
        working_days = 30

        if emp.wage_type == "MONTHLY":
            daily_rate = emp.base_rate / working_days
            earned_basic = daily_rate * effective_days
        else:
            daily_rate = emp.base_rate
            earned_basic = daily_rate * effective_days

        hourly_rate = daily_rate / 8.0
        overtime_pay = total_overtime * hourly_rate * 1.5
        gross_salary = round(earned_basic + overtime_pay, 2)
        net_payable = gross_salary

        payroll_record = (
            db.query(PayrollRecord)
            .filter(
                PayrollRecord.employee_id == emp.id,
                PayrollRecord.month == month,
                PayrollRecord.year == year,
            )
            .first()
        )

        if not payroll_record:
            payroll_record = PayrollRecord(
                shop_id=shop_id,
                employee_id=emp.id,
                month=month,
                year=year,
                working_days_in_month=working_days,
                days_present=days_present,
                days_absent=days_absent,
                gross_salary=gross_salary,
                advances_deducted=0.0,
                net_payable=net_payable,
                is_paid=False,
            )
            db.add(payroll_record)
        else:
            payroll_record.days_present = days_present
            payroll_record.days_absent = days_absent
            payroll_record.gross_salary = gross_salary
            payroll_record.net_payable = net_payable

        payroll_summaries.append({
            "employee_id": emp.id,
            "employee_name": emp.name,
            "designation": emp.designation,
            "wage_type": emp.wage_type,
            "base_rate": emp.base_rate,
            "days_present": days_present,
            "days_absent": days_absent,
            "days_half_day": days_half_day,
            "overtime_hours": total_overtime,
            "gross_salary": gross_salary,
            "net_payable": net_payable,
        })

    db.commit()
    return payroll_summaries


def get_daily_shift_summary(
    shop_id: str,
    date: str,
    db: Session,
) -> dict[str, Any]:
    employees = list_employees(shop_id, db)
    records = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.shop_id == shop_id, AttendanceRecord.date == date)
        .all()
    )

    attendance_map = {r.employee_id: r for r in records}

    present_names = []
    absent_names = []

    for emp in employees:
        rec = attendance_map.get(emp.id)
        if rec and rec.status in ["PRESENT", "HALF_DAY"]:
            present_names.append(f"{emp.name} ({emp.designation})")
        else:
            absent_names.append(f"{emp.name} ({emp.designation})")

    today_stock_in = (
        db.query(StockMovement)
        .filter(
            StockMovement.shop_id == shop_id,
            StockMovement.movement_type == "IN_PURCHASE",
        )
        .count()
    )

    low_stock = get_low_stock_report(shop_id, db)

    return {
        "shop_id": shop_id,
        "date": date,
        "total_staff": len(employees),
        "present_count": len(present_names),
        "absent_count": len(absent_names),
        "present_staff": present_names,
        "absent_staff": absent_names,
        "stock_movements_in_today": today_stock_in,
        "urgent_reorder_count": len(low_stock),
        "urgent_reorder_items": [f"{it['name']} ({it['current_stock']} left)" for it in low_stock[:4]],
    }


def parse_time_to_hours(time_str: Optional[str]) -> Optional[float]:
    if not time_str:
        return None
    cleaned = time_str.strip().upper()
    is_pm = "PM" in cleaned
    is_am = "AM" in cleaned
    cleaned = cleaned.replace("AM", "").replace("PM", "").strip()

    try:
        parts = cleaned.split(":")
        hours = float(parts[0])
        mins = float(parts[1]) if len(parts) > 1 else 0.0
        if is_pm and hours < 12.0:
            hours += 12.0
        elif is_am and hours == 12.0:
            hours = 0.0
        return hours + (mins / 60.0)
    except Exception:
        return None


def mark_smart_attendance(
    shop_id: str,
    employee_id: str,
    date_str: str,
    check_in_time: Optional[str] = None,
    check_out_time: Optional[str] = None,
    status: str = "PRESENT",
    shift_name: str = "MORNING",
    notes: Optional[str] = None,
    db: Session = None,
) -> AttendanceRecord:
    emp = db.query(Employee).filter(Employee.id == employee_id, Employee.shop_id == shop_id).first()
    if not emp:
        raise ValueError(f"Employee {employee_id} not found in shop {shop_id}")

    norm_status = status.strip().upper()
    worked_hours = 8.0
    overtime_hours = 0.0
    is_late = False

    t_in = parse_time_to_hours(check_in_time)
    t_out = parse_time_to_hours(check_out_time)

    if emp.tier == "WHITE_COLLAR":
        shift_start = parse_time_to_hours(emp.shift_start_time or "09:30") or 9.5
        if t_in is not None:
            grace_period = 0.25
            if t_in > (shift_start + grace_period):
                is_late = True

        if norm_status == "ON_LEAVE":
            leave_bal = (
                db.query(LeaveBalance)
                .filter(LeaveBalance.employee_id == emp.id)
                .first()
            )
            if leave_bal and leave_bal.casual_leave >= 1.0:
                leave_bal.casual_leave -= 1.0
            elif leave_bal and leave_bal.paid_leave >= 1.0:
                leave_bal.paid_leave -= 1.0
            else:
                norm_status = "LOSS_OF_PAY"
    else:
        if t_in is not None and t_out is not None:
            raw_worked = max(0.0, t_out - t_in)
            worked_hours = round(raw_worked, 1)

            if worked_hours < 4.0:
                norm_status = "ABSENT"
                overtime_hours = 0.0
            elif worked_hours < 7.0:
                norm_status = "HALF_DAY"
                overtime_hours = 0.0
            elif worked_hours <= 9.0:
                norm_status = "PRESENT"
                overtime_hours = 0.0
            else:
                norm_status = "PRESENT"
                overtime_hours = round(worked_hours - 8.0, 1)

    record = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.employee_id == employee_id, AttendanceRecord.date == date_str)
        .first()
    )

    if record:
        record.status = norm_status
        record.check_in_time = check_in_time or record.check_in_time
        record.check_out_time = check_out_time or record.check_out_time
        record.worked_hours = worked_hours
        record.overtime_hours = overtime_hours
        record.is_late = is_late
        record.shift_name = shift_name
        record.notes = notes or record.notes
    else:
        record = AttendanceRecord(
            shop_id=shop_id,
            employee_id=employee_id,
            date=date_str,
            status=norm_status,
            check_in_time=check_in_time,
            check_out_time=check_out_time,
            worked_hours=worked_hours,
            overtime_hours=overtime_hours,
            is_late=is_late,
            shift_name=shift_name,
            notes=notes,
        )
        db.add(record)

    db.commit()
    db.refresh(record)
    return record


def crew_checkin(
    shop_id: str,
    date_str: str,
    present_employee_ids: List[str],
    shift_name: str = "MORNING",
    db: Session = None,
) -> Dict[str, Any]:
    blue_collar_staff = (
        db.query(Employee)
        .filter(Employee.shop_id == shop_id, Employee.is_active == True, Employee.tier == "BLUE_COLLAR")
        .all()
    )

    checked_in = []
    absent = []

    for emp in blue_collar_staff:
        if emp.id in present_employee_ids or emp.name in present_employee_ids:
            rec = mark_smart_attendance(
                shop_id=shop_id,
                employee_id=emp.id,
                date_str=date_str,
                check_in_time="08:00 AM",
                status="PRESENT",
                shift_name=shift_name,
                notes="1-Click Crew Checkin",
                db=db,
            )
            checked_in.append(emp.name)
        else:
            rec = mark_smart_attendance(
                shop_id=shop_id,
                employee_id=emp.id,
                date_str=date_str,
                status="ABSENT",
                shift_name=shift_name,
                notes="Marked absent in crew checkin",
                db=db,
            )
            absent.append(emp.name)

    return {
        "shop_id": shop_id,
        "date": date_str,
        "shift_name": shift_name,
        "crew_size": len(blue_collar_staff),
        "present_count": len(checked_in),
        "absent_count": len(absent),
        "checked_in_staff": checked_in,
        "absent_staff": absent,
    }


def regularize_attendance(
    shop_id: str,
    employee_id: str,
    date_str: str,
    check_in_time: str,
    check_out_time: str,
    reason: str,
    db: Session,
) -> Optional[AttendanceRecord]:
    record = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.employee_id == employee_id, AttendanceRecord.date == date_str)
        .first()
    )
    if not record:
        record = AttendanceRecord(
            shop_id=shop_id,
            employee_id=employee_id,
            date=date_str,
            status="PRESENT",
        )
        db.add(record)

    record.check_in_time = check_in_time
    record.check_out_time = check_out_time
    record.status = "PRESENT"
    record.is_late = False
    record.regularized = True
    record.regularization_notes = reason
    db.commit()
    db.refresh(record)
    return record


def check_shift_understaffing(
    shop_id: str,
    date_str: str,
    shift_name: str = "MORNING",
    required_minimum: int = 2,
    db: Session = None,
) -> Dict[str, Any]:
    records = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.shop_id == shop_id,
            AttendanceRecord.date == date_str,
            AttendanceRecord.shift_name == shift_name,
            AttendanceRecord.status.in_(["PRESENT", "HALF_DAY"]),
        )
        .all()
    )
    present_count = len(records)
    is_understaffed = present_count < required_minimum

    all_staff = (
        db.query(Employee)
        .filter(Employee.shop_id == shop_id, Employee.is_active == True)
        .all()
    )
    present_ids = {r.employee_id for r in records}
    missing_staff = [e.name for e in all_staff if e.id not in present_ids]

    return {
        "shop_id": shop_id,
        "date": date_str,
        "shift_name": shift_name,
        "present_count": present_count,
        "required_minimum": required_minimum,
        "is_understaffed": is_understaffed,
        "missing_staff": missing_staff,
        "alert_message": f"Understaffing warning: Only {present_count} staff on duty for {shift_name} shift (minimum {required_minimum} required)." if is_understaffed else "Shift fully staffed.",
    }


def issue_staff_advance(
    shop_id: str,
    employee_id: str,
    amount: float,
    notes: Optional[str] = "Mid-month cash advance",
    db: Session = None,
) -> StaffAdvance:
    emp = db.query(Employee).filter(Employee.id == employee_id, Employee.shop_id == shop_id).first()
    if not emp:
        raise ValueError(f"Employee {employee_id} not found in shop {shop_id}")

    advance = StaffAdvance(
        shop_id=shop_id,
        employee_id=employee_id,
        amount=round(amount, 2),
        date_given=date.today().isoformat(),
        repaid_amount=0.0,
        status="ACTIVE",
        notes=notes,
    )
    db.add(advance)
    db.commit()
    db.refresh(advance)
    return advance


def get_staff_advances(shop_id: str, employee_id: Optional[str] = None, db: Session = None) -> List[Dict[str, Any]]:
    query = db.query(StaffAdvance).filter(StaffAdvance.shop_id == shop_id, StaffAdvance.status == "ACTIVE")
    if employee_id:
        query = query.filter(StaffAdvance.employee_id == employee_id)
    advances = query.all()

    results = []
    for adv in advances:
        results.append({
            "advance_id": adv.id,
            "employee_id": adv.employee_id,
            "employee_name": adv.employee.name if adv.employee else "Unknown",
            "amount": adv.amount,
            "date_given": adv.date_given,
            "repaid_amount": adv.repaid_amount,
            "remaining_balance": round(adv.amount - adv.repaid_amount, 2),
            "notes": adv.notes,
        })
    return results


def calculate_smart_payroll(
    shop_id: str,
    month: int,
    year: int = 2026,
    db: Session = None,
) -> List[Dict[str, Any]]:
    employees = list_employees(shop_id, db)
    payroll_items = []

    for emp in employees:
        records = (
            db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.employee_id == emp.id,
                AttendanceRecord.date.like(f"{year}-{month:02d}-%"),
            )
            .all()
        )

        days_present = sum(1.0 for r in records if r.status == "PRESENT")
        days_half_day = sum(1.0 for r in records if r.status == "HALF_DAY")
        days_absent = sum(1.0 for r in records if r.status == "ABSENT")
        days_lop = sum(1.0 for r in records if r.status == "LOSS_OF_PAY")
        late_marks = sum(1 for r in records if r.is_late and not r.regularized)
        total_overtime = sum(r.overtime_hours or 0.0 for r in records)

        active_advances = (
            db.query(StaffAdvance)
            .filter(StaffAdvance.employee_id == emp.id, StaffAdvance.status == "ACTIVE")
            .all()
        )
        total_advance_pending = sum(a.amount - a.repaid_amount for a in active_advances)

        if emp.tier == "WHITE_COLLAR":
            working_days = 30
            daily_rate = emp.base_rate / working_days

            late_cuts = (late_marks // 3) * 0.5 * daily_rate
            lop_cuts = days_lop * daily_rate
            absent_cuts = days_absent * daily_rate

            gross_salary = emp.base_rate
            epf_deduction = round(emp.base_rate * 0.12, 2) if emp.epf_eligible else 0.0
            esic_deduction = round(emp.base_rate * 0.0075, 2) if emp.esic_eligible else 0.0

            advance_deduction = min(total_advance_pending, round(emp.base_rate * 0.25, 2))

            total_deductions = round(late_cuts + lop_cuts + absent_cuts + epf_deduction + esic_deduction + advance_deduction, 2)
            net_payable = round(max(0.0, gross_salary - total_deductions), 2)
        else:
            daily_rate = emp.daily_rate or (emp.base_rate / 30.0)
            earned_days = days_present + (days_half_day * 0.5)
            basic_pay = round(earned_days * daily_rate, 2)

            ot_rate = emp.overtime_hourly_rate or (daily_rate / 8.0 * 1.5)
            overtime_pay = round(total_overtime * ot_rate, 2)
            gross_salary = round(basic_pay + overtime_pay, 2)

            epf_deduction = 0.0
            esic_deduction = round(gross_salary * 0.0075, 2) if emp.esic_eligible else 0.0
            advance_deduction = min(total_advance_pending, round(gross_salary * 0.40, 2))

            total_deductions = round(esic_deduction + advance_deduction, 2)
            net_payable = round(max(0.0, gross_salary - total_deductions), 2)

        payroll_items.append({
            "employee_id": emp.id,
            "employee_name": emp.name,
            "designation": emp.designation,
            "tier": emp.tier,
            "days_present": days_present,
            "days_half_day": days_half_day,
            "days_absent": days_absent,
            "late_marks": late_marks,
            "overtime_hours": total_overtime,
            "gross_salary": gross_salary,
            "epf_deduction": epf_deduction,
            "esic_deduction": esic_deduction,
            "advance_deduction": advance_deduction,
            "total_deductions": total_deductions,
            "net_payable": net_payable,
            "bank_account_number": emp.bank_account_number,
            "ifsc_code": emp.ifsc_code,
            "upi_id": emp.upi_id,
        })

    return payroll_items


def generate_payout_advice_batch(
    shop_id: str,
    month: int,
    year: int = 2026,
    db: Session = None,
) -> Dict[str, Any]:
    payroll_items = calculate_smart_payroll(shop_id, month, year, db)
    period_str = f"{year}-{month:02d}"

    total_gross = round(sum(p["gross_salary"] for p in payroll_items), 2)
    total_deductions = round(sum(p["total_deductions"] for p in payroll_items), 2)
    total_net = round(sum(p["net_payable"] for p in payroll_items), 2)

    batch_number = f"BATCH-PAY-{year}{month:02d}-{shop_id[:6].upper()}"

    batch = (
        db.query(PayoutBatch)
        .filter(PayoutBatch.shop_id == shop_id, PayoutBatch.period == period_str, PayoutBatch.batch_type == "STAFF_PAYROLL")
        .first()
    )

    if not batch:
        batch = PayoutBatch(
            shop_id=shop_id,
            batch_number=batch_number,
            period=period_str,
            batch_type="STAFF_PAYROLL",
            total_gross=total_gross,
            total_deductions=total_deductions,
            total_net_payable=total_net,
            employee_count=len(payroll_items),
            status="DRAFT",
        )
        db.add(batch)
    else:
        batch.total_gross = total_gross
        batch.total_deductions = total_deductions
        batch.total_net_payable = total_net
        batch.employee_count = len(payroll_items)

    db.commit()
    db.refresh(batch)

    return {
        "batch_id": batch.id,
        "batch_number": batch.batch_number,
        "period": period_str,
        "status": batch.status,
        "employee_count": len(payroll_items),
        "total_gross_wages": total_gross,
        "total_deductions": total_deductions,
        "total_net_disbursement": total_net,
        "disbursement_advice": payroll_items,
    }


def approve_payout_batch(
    batch_id: str,
    approved_by: str = "Store Owner",
    db: Session = None,
) -> Dict[str, Any]:
    batch = db.query(PayoutBatch).filter(PayoutBatch.id == batch_id).first()
    if not batch:
        raise ValueError(f"Payout Batch {batch_id} not found")

    batch.status = "APPROVED"
    batch.approved_by = approved_by
    batch.approved_at = datetime.utcnow()

    lines = [
        {"account_code": "5030", "debit": batch.total_gross, "credit": 0.0, "notes": f"Staff wages for period {batch.period}"},
        {"account_code": "1020", "debit": 0.0, "credit": batch.total_net_payable, "notes": f"Net salary disbursement via Bank ({batch.batch_number})"},
    ]

    if batch.total_deductions > 0:
        lines.append({
            "account_code": "2040",
            "debit": 0.0,
            "credit": batch.total_deductions,
            "notes": f"Staff advances & statutory withholdings ({batch.batch_number})",
        })

    create_journal_entry(
        shop_id=batch.shop_id,
        entry_date=date.today().isoformat(),
        reference_type="PAYROLL_BATCH",
        reference_id=batch.id,
        description=f"Payroll disbursement batch {batch.batch_number} approved by {approved_by}",
        lines_data=lines,
        db=db,
    )

    db.commit()
    db.refresh(batch)

    return {
        "batch_id": batch.id,
        "batch_number": batch.batch_number,
        "status": "APPROVED",
        "approved_by": approved_by,
        "total_disbursed": batch.total_net_payable,
        "journal_entry_recorded": True,
    }

