from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from src.db.session import get_db
from src.db.models import Shop, Bill, ComplianceIssueModel

router = APIRouter(prefix="/api/summary", tags=["Summary"])


class TaxBreakdown(BaseModel):
    cgst: float
    sgst: float
    igst: float
    total: float


class ShopSummaryResponse(BaseModel):
    shop_id: str
    shop_name: str
    shop_gstin: str
    total_bills: int
    clean_bills: int
    flagged_bills: int
    ca_approved_bills: int
    ca_rejected_bills: int
    eligible_itc: TaxBreakdown
    itc_at_risk: float
    open_issues_count: int


@router.get("/{shop_id}", response_model=ShopSummaryResponse)
def get_shop_summary(shop_id: str, db: Session = Depends(get_db)):
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    bills = db.query(Bill).filter(Bill.shop_id == shop_id).all()
    issues = db.query(ComplianceIssueModel).filter(ComplianceIssueModel.shop_id == shop_id).all()

    total_bills = len(bills)
    clean_bills = sum(1 for b in bills if b.status == "clean")
    ca_approved = sum(1 for b in bills if b.status == "ca_approved")
    ca_rejected = sum(1 for b in bills if b.status == "ca_rejected")
    flagged_bills = sum(1 for b in bills if b.status == "flagged_issue")

    eligible_bills = [b for b in bills if b.status in ["clean", "ca_approved"]]
    eligible_cgst = sum(b.cgst_amount for b in eligible_bills)
    eligible_sgst = sum(b.sgst_amount for b in eligible_bills)
    eligible_igst = sum(b.igst_amount for b in eligible_bills)
    eligible_total = eligible_cgst + eligible_sgst + eligible_igst

    open_issues = [i for i in issues if i.ca_action == "pending"]
    itc_at_risk = sum(i.rupee_value_at_risk for i in open_issues)

    return ShopSummaryResponse(
        shop_id=shop.id,
        shop_name=shop.name,
        shop_gstin=shop.gstin,
        total_bills=total_bills,
        clean_bills=clean_bills,
        flagged_bills=flagged_bills,
        ca_approved_bills=ca_approved,
        ca_rejected_bills=ca_rejected,
        eligible_itc=TaxBreakdown(
            cgst=round(eligible_cgst, 2),
            sgst=round(eligible_sgst, 2),
            igst=round(eligible_igst, 2),
            total=round(eligible_total, 2),
        ),
        itc_at_risk=round(itc_at_risk, 2),
        open_issues_count=len(open_issues),
    )


@router.get("/{shop_id}/export")
def export_shop_summary(shop_id: str, db: Session = Depends(get_db)):
    summary = get_shop_summary(shop_id, db)
    bills = db.query(Bill).filter(Bill.shop_id == shop_id).all()

    export_payload = {
        "summary": summary.model_dump(),
        "bills": [
            {
                "id": b.id,
                "bill_number": b.bill_number,
                "bill_date": b.bill_date,
                "supplier_name": b.supplier_name,
                "supplier_gstin": b.supplier_gstin,
                "taxable_amount": b.taxable_amount,
                "cgst_amount": b.cgst_amount,
                "sgst_amount": b.sgst_amount,
                "igst_amount": b.igst_amount,
                "total_amount": b.total_amount,
                "status": b.status,
            }
            for b in bills
        ],
    }

    return JSONResponse(
        content=export_payload,
        headers={"Content-Disposition": f"attachment; filename=munimji_gstr_summary_{shop_id}.json"},
    )
