import shutil
from pathlib import Path
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from src.db.session import get_db
from src.db.models import Shop, Bill, BillItem, ComplianceIssueModel
from src.extraction.parser import extract_bill_data
from src.gst_engine.validator import validate_bill_compliance

router = APIRouter(prefix="/api/bills", tags=["Bills"])
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class BillItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    description: str
    hsn_code: Optional[str] = None
    quantity: float
    rate: float
    tax_rate_percent: float
    taxable_value: float
    cgst: float
    sgst: float
    igst: float
    total: float


class ComplianceIssueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    issue_type: str
    severity: str
    rupee_value_at_risk: float
    explanation: str
    suggested_action: Optional[str] = None
    ca_action: str
    supplier_inquiry_draft: Optional[str] = None


class BillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    shop_id: str
    file_path: str
    file_type: str
    supplier_name: Optional[str] = None
    supplier_gstin: Optional[str] = None
    bill_number: Optional[str] = None
    bill_date: Optional[str] = None
    taxable_amount: float
    cgst_amount: float
    sgst_amount: float
    igst_amount: float
    total_amount: float
    is_confirmed_by_owner: bool
    status: str
    items: list[BillItemResponse] = []
    issues: list[ComplianceIssueResponse] = []


class BillConfirmRequest(BaseModel):
    confirmed: bool = True
    corrected_total: Optional[float] = None
    corrected_supplier_gstin: Optional[str] = None


@router.post("/upload", response_model=BillResponse, status_code=201)
async def upload_bill(
    shop_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    dest_path = UPLOAD_DIR / f"{shop_id}_{file.filename}"
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    extracted = extract_bill_data(str(dest_path))

    existing_bills = [
        {"id": b.id, "supplier_gstin": b.supplier_gstin, "bill_number": b.bill_number}
        for b in db.query(Bill).filter(Bill.shop_id == shop_id).all()
    ]

    bill_check_data = dict(extracted)
    issues = validate_bill_compliance(
        bill_data=bill_check_data,
        buyer_gstin=shop.gstin,
        existing_bills=existing_bills,
    )

    initial_status = "clean" if len(issues) == 0 else "flagged_issue"
    file_ext = Path(file.filename).suffix.lower().replace(".", "")
    file_type = "pdf" if file_ext == "pdf" else "image"

    supplier_gstin = extracted.get("supplier_gstin")
    supplier_state = supplier_gstin[:2] if supplier_gstin and len(supplier_gstin) >= 2 else None

    bill = Bill(
        shop_id=shop.id,
        file_path=str(dest_path),
        file_type=file_type,
        supplier_name=extracted.get("supplier_name"),
        supplier_gstin=supplier_gstin,
        supplier_state_code=supplier_state,
        bill_number=extracted.get("bill_number"),
        bill_date=extracted.get("bill_date"),
        taxable_amount=extracted.get("taxable_amount", 0.0),
        cgst_amount=extracted.get("cgst_amount", 0.0),
        sgst_amount=extracted.get("sgst_amount", 0.0),
        igst_amount=extracted.get("igst_amount", 0.0),
        total_amount=extracted.get("total_amount", 0.0),
        is_confirmed_by_owner=False,
        status=initial_status,
    )
    db.add(bill)
    db.flush()

    for item_data in extracted.get("items", []):
        item = BillItem(
            bill_id=bill.id,
            description=item_data.get("description", "Item"),
            hsn_code=item_data.get("hsn"),
            quantity=item_data.get("qty", 1.0),
            rate=item_data.get("rate", 0.0),
            tax_rate_percent=item_data.get("tax_rate", 0.0),
            taxable_value=item_data.get("taxable_value", 0.0),
            cgst=bill.cgst_amount / max(len(extracted.get("items", [])), 1),
            sgst=bill.sgst_amount / max(len(extracted.get("items", [])), 1),
            igst=bill.igst_amount / max(len(extracted.get("items", [])), 1),
            total=item_data.get("total", 0.0),
        )
        db.add(item)

    for issue in issues:
        draft = None
        if issue.issue_type == "WRONG_TAX_TYPE":
            draft = (
                f"Subject: Correction Request - Invoice #{bill.bill_number}\n\n"
                f"Dear {bill.supplier_name},\n\n"
                f"We noticed that invoice #{bill.bill_number} applies CGST/SGST instead of IGST "
                f"for supply to Delhi (State Code 07). Kindly issue an amended invoice with IGST.\n\n"
                f"Regards,\n{shop.name}"
            )

        issue_model = ComplianceIssueModel(
            bill_id=bill.id,
            shop_id=shop.id,
            issue_type=issue.issue_type,
            severity=issue.severity,
            rupee_value_at_risk=issue.rupee_value_at_risk,
            explanation=issue.explanation,
            suggested_action=issue.suggested_action,
            supplier_inquiry_draft=draft,
        )
        db.add(issue_model)

    db.commit()
    db.refresh(bill)
    return bill


@router.get("", response_model=list[BillResponse])
def list_bills(
    shop_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Bill)
    if shop_id:
        query = query.filter(Bill.shop_id == shop_id)
    if status:
        query = query.filter(Bill.status == status)
    return query.all()


@router.get("/{bill_id}", response_model=BillResponse)
def get_bill(bill_id: str, db: Session = Depends(get_db)):
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    return bill


@router.post("/{bill_id}/confirm", response_model=BillResponse)
def confirm_bill(
    bill_id: str,
    payload: BillConfirmRequest,
    db: Session = Depends(get_db),
):
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    bill.is_confirmed_by_owner = payload.confirmed

    if payload.corrected_total is not None:
        bill.total_amount = payload.corrected_total
    if payload.corrected_supplier_gstin is not None:
        bill.supplier_gstin = payload.corrected_supplier_gstin
        bill.supplier_state_code = payload.corrected_supplier_gstin[:2]

    db.commit()
    db.refresh(bill)
    return bill
