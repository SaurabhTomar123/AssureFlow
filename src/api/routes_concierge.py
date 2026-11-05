from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.concierge.vendor_dispute import VendorDisputeConcierge

router = APIRouter(prefix="/api/concierge", tags=["Autonomous Vendor Dispute Concierge"])
concierge = VendorDisputeConcierge()


class CreateDisputeTicketRequest(BaseModel):
    shop_id: str
    bill_id: str
    issue_id: str


class VendorResolutionRequest(BaseModel):
    token: str
    resolution_type: str  # e.g. "GSTR1_AMENDMENT_COMMITTED", "CREDIT_NOTE_ISSUED"
    notes: Optional[str] = "Committed in next filing"
    credit_note_ref: Optional[str] = None


@router.post("/dispute/create")
def create_dispute_ticket(req: CreateDisputeTicketRequest, db: Session = Depends(get_db)):
    try:
        ticket = concierge.create_dispute_ticket(
            issue_id=req.issue_id,
            bill_id=req.bill_id,
            shop_id=req.shop_id,
            db=db,
        )
        return ticket
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/dispute/resolve")
def resolve_dispute(req: VendorResolutionRequest, db: Session = Depends(get_db)):
    try:
        res = concierge.process_vendor_resolution(
            token=req.token,
            resolution_type=req.resolution_type,
            notes=req.notes or "",
            credit_note_ref=req.credit_note_ref,
            db=db,
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
