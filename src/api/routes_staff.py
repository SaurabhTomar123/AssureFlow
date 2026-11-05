from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from src.db.session import get_db
from src.staff.service import (
    add_employee,
    list_employees,
    mark_attendance,
    calculate_monthly_payroll,
    get_daily_shift_summary,
)

router = APIRouter(prefix="/api/staff", tags=["Staff & Attendance Management"])


class EmployeeCreate(BaseModel):
    name: str
    designation: str = "Store Associate"
    wage_type: str = "MONTHLY"
    base_rate: float = 18000.0


class EmployeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    shop_id: str
    name: str
    designation: str
    wage_type: str
    base_rate: float
    is_active: bool


class AttendanceRequest(BaseModel):
    employee_id: str
    date: str
    status: str = "PRESENT"
    check_in_time: Optional[str] = "09:30 AM"
    check_out_time: Optional[str] = "08:30 PM"
    overtime_hours: float = 0.0
    notes: Optional[str] = None


@router.post("/{shop_id}", response_model=EmployeeResponse, status_code=201)
def create_staff(shop_id: str, payload: EmployeeCreate, db: Session = Depends(get_db)):
    return add_employee(
        shop_id=shop_id,
        name=payload.name,
        designation=payload.designation,
        wage_type=payload.wage_type,
        base_rate=payload.base_rate,
        db=db,
    )


@router.get("/{shop_id}", response_model=list[EmployeeResponse])
def get_staff(shop_id: str, db: Session = Depends(get_db)):
    return list_employees(shop_id, db)


@router.post("/{shop_id}/attendance")
def post_attendance(shop_id: str, payload: AttendanceRequest, db: Session = Depends(get_db)):
    rec = mark_attendance(
        shop_id=shop_id,
        employee_id=payload.employee_id,
        date=payload.date,
        status=payload.status,
        check_in_time=payload.check_in_time,
        check_out_time=payload.check_out_time,
        overtime_hours=payload.overtime_hours,
        notes=payload.notes,
        db=db,
    )
    return {
        "status": "success",
        "employee_id": rec.employee_id,
        "date": rec.date,
        "attendance_status": rec.status,
    }


@router.get("/{shop_id}/payroll")
def get_payroll(
    shop_id: str,
    month: int = Query(11, ge=1, le=12),
    year: int = Query(2026),
    db: Session = Depends(get_db),
):
    return calculate_monthly_payroll(shop_id=shop_id, month=month, year=year, db=db)


@router.get("/{shop_id}/shift-summary")
def get_shift_summary(
    shop_id: str,
    date: str = Query("2026-11-05"),
    db: Session = Depends(get_db),
):
    return get_daily_shift_summary(shop_id=shop_id, date=date, db=db)

