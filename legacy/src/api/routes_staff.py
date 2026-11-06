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


class SmartAttendanceRequest(BaseModel):
    employee_id: str
    date: str
    check_in_time: Optional[str] = None
    check_out_time: Optional[str] = None
    status: str = "PRESENT"
    shift_name: str = "MORNING"
    notes: Optional[str] = None


class CrewCheckinRequest(BaseModel):
    date: str
    present_employee_ids: list[str]
    shift_name: str = "MORNING"


class RegularizeRequest(BaseModel):
    employee_id: str
    date: str
    check_in_time: str
    check_out_time: str
    reason: str


class StaffAdvanceRequest(BaseModel):
    employee_id: str
    amount: float
    notes: Optional[str] = "Mid-month cash advance"


class PayoutBatchRequest(BaseModel):
    month: int
    year: int = 2026


class PayoutBatchApproveRequest(BaseModel):
    approved_by: str = "Store Owner"


@router.post("/{shop_id}/smart-attendance")
def post_smart_attendance(shop_id: str, payload: SmartAttendanceRequest, db: Session = Depends(get_db)):
    try:
        rec = mark_smart_attendance(
            shop_id=shop_id,
            employee_id=payload.employee_id,
            date_str=payload.date,
            check_in_time=payload.check_in_time,
            check_out_time=payload.check_out_time,
            status=payload.status,
            shift_name=payload.shift_name,
            notes=payload.notes,
            db=db,
        )
        return {
            "status": "success",
            "employee_id": rec.employee_id,
            "date": rec.date,
            "attendance_status": rec.status,
            "worked_hours": rec.worked_hours,
            "overtime_hours": rec.overtime_hours,
            "is_late": rec.is_late,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{shop_id}/crew-checkin")
def post_crew_checkin(shop_id: str, payload: CrewCheckinRequest, db: Session = Depends(get_db)):
    return crew_checkin(
        shop_id=shop_id,
        date_str=payload.date,
        present_employee_ids=payload.present_employee_ids,
        shift_name=payload.shift_name,
        db=db,
    )


@router.post("/{shop_id}/regularize")
def post_regularize(shop_id: str, payload: RegularizeRequest, db: Session = Depends(get_db)):
    rec = regularize_attendance(
        shop_id=shop_id,
        employee_id=payload.employee_id,
        date_str=payload.date,
        check_in_time=payload.check_in_time,
        check_out_time=payload.check_out_time,
        reason=payload.reason,
        db=db,
    )
    return {
        "status": "success",
        "employee_id": rec.employee_id,
        "date": rec.date,
        "regularized": rec.regularized,
    }


@router.get("/{shop_id}/shift-understaffing")
def get_shift_understaffing(
    shop_id: str,
    date: str = Query(...),
    shift_name: str = Query("MORNING"),
    required_minimum: int = Query(2),
    db: Session = Depends(get_db),
):
    return check_shift_understaffing(
        shop_id=shop_id,
        date_str=date,
        shift_name=shift_name,
        required_minimum=required_minimum,
        db=db,
    )


@router.post("/{shop_id}/advances")
def post_staff_advance(shop_id: str, payload: StaffAdvanceRequest, db: Session = Depends(get_db)):
    try:
        adv = issue_staff_advance(
            shop_id=shop_id,
            employee_id=payload.employee_id,
            amount=payload.amount,
            notes=payload.notes,
            db=db,
        )
        return {
            "status": "success",
            "advance_id": adv.id,
            "employee_id": adv.employee_id,
            "amount": adv.amount,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{shop_id}/advances")
def list_staff_advances(
    shop_id: str,
    employee_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    return get_staff_advances(shop_id=shop_id, employee_id=employee_id, db=db)


@router.get("/{shop_id}/smart-payroll")
def get_smart_payroll(
    shop_id: str,
    month: int = Query(11, ge=1, le=12),
    year: int = Query(2026),
    db: Session = Depends(get_db),
):
    return calculate_smart_payroll(shop_id=shop_id, month=month, year=year, db=db)


@router.post("/{shop_id}/payout-batch")
def post_generate_payout_batch(
    shop_id: str,
    payload: PayoutBatchRequest,
    db: Session = Depends(get_db),
):
    return generate_payout_advice_batch(
        shop_id=shop_id,
        month=payload.month,
        year=payload.year,
        db=db,
    )


@router.post("/payout-batch/{batch_id}/approve")
def post_approve_payout_batch(
    batch_id: str,
    payload: PayoutBatchApproveRequest,
    db: Session = Depends(get_db),
):
    try:
        return approve_payout_batch(
            batch_id=batch_id,
            approved_by=payload.approved_by,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


