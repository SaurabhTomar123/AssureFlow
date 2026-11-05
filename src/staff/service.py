from datetime import datetime
from typing import Any, List, Optional
from sqlalchemy.orm import Session
from src.db.models import Employee, AttendanceRecord, PayrollRecord, StockMovement
from src.inventory.service import get_low_stock_report


def add_employee(
    shop_id: str,
    name: str,
    designation: str = "Store Associate",
    wage_type: str = "MONTHLY",
    base_rate: float = 18000.0,
    joining_date: str = "2026-01-01",
    db: Session = None,
) -> Employee:
    norm_wage = wage_type.strip().upper()
    if norm_wage not in ["MONTHLY", "DAILY"]:
        norm_wage = "MONTHLY"

    emp = Employee(
        shop_id=shop_id,
        name=name.strip(),
        designation=designation.strip(),
        wage_type=norm_wage,
        base_rate=base_rate,
        joining_date=joining_date,
        is_active=True,
    )
    db.add(emp)
    db.commit()
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
