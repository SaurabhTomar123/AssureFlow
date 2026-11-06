from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.db.models import Shop, GSTR2BInwardRecord, ComplianceIssueModel
from src.gsp.reconciler import sync_gstr2b_feed, reconcile_shop_purchases

router = APIRouter(prefix="/api/gsp", tags=["GSP & GSTR-2B Reconciliation"])


class SyncGSTR2BRequest(BaseModel):
    shop_id: str
    return_period: str = "042026"


class ReconcileRequest(BaseModel):
    shop_id: str
    return_period: str = "042026"


class SupplierNoticeResponse(BaseModel):
    issue_id: str
    bill_id: str
    issue_type: str
    severity: str
    rupee_value_at_risk: float
    explanation: str
    supplier_notice_draft: Optional[str]


@router.post("/sync-gstr2b")
def sync_gstr2b(req: SyncGSTR2BRequest, db: Session = Depends(get_db)):
    shop = db.query(Shop).filter(Shop.id == req.shop_id).first()
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shop {req.shop_id} not found",
        )
    synced_count = sync_gstr2b_feed(req.shop_id, req.return_period, db)
    return {
        "status": "success",
        "shop_id": req.shop_id,
        "return_period": req.return_period,
        "synced_records": synced_count,
    }


@router.post("/reconcile")
def run_two_way_reconciliation(req: ReconcileRequest, db: Session = Depends(get_db)):
    try:
        report = reconcile_shop_purchases(req.shop_id, req.return_period, db)
        return report
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/reconciliation-summary/{shop_id}")
def get_reconciliation_summary(shop_id: str, return_period: str = "042026", db: Session = Depends(get_db)):
    portal_records = (
        db.query(GSTR2BInwardRecord)
        .filter(
            GSTR2BInwardRecord.shop_id == shop_id,
            GSTR2BInwardRecord.filing_period == return_period,
        )
        .all()
    )
    if not portal_records:
        sync_gstr2b_feed(shop_id, return_period, db)
        return reconcile_shop_purchases(shop_id, return_period, db)

    matched = sum(1 for r in portal_records if r.match_status == "MATCHED")
    mismatch = sum(1 for r in portal_records if r.match_status == "MISMATCH")
    unmatched = sum(1 for r in portal_records if r.match_status == "UNMATCHED")

    return {
        "shop_id": shop_id,
        "return_period": return_period,
        "total_portal_invoices": len(portal_records),
        "matched_count": matched,
        "tax_mismatch_count": mismatch,
        "unrecorded_purchase_count": unmatched,
    }


@router.get("/supplier-notices/{shop_id}", response_model=List[SupplierNoticeResponse])
def get_supplier_notices(shop_id: str, db: Session = Depends(get_db)):
    issues = (
        db.query(ComplianceIssueModel)
        .filter(
            ComplianceIssueModel.shop_id == shop_id,
            ComplianceIssueModel.issue_type.in_(["GSTR2B_TAX_MISMATCH", "SUPPLIER_DEFAULT_UNFILED"]),
        )
        .all()
    )

    return [
        SupplierNoticeResponse(
            issue_id=issue.id,
            bill_id=issue.bill_id,
            issue_type=issue.issue_type,
            severity=issue.severity,
            rupee_value_at_risk=issue.rupee_value_at_risk or 0.0,
            explanation=issue.explanation,
            supplier_notice_draft=issue.supplier_inquiry_draft,
        )
        for issue in issues
    ]
