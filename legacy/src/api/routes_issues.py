from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from src.db.session import get_db
from src.db.models import ComplianceIssueModel, Bill

router = APIRouter(prefix="/api/issues", tags=["Compliance Issues"])


class IssueActionRequest(BaseModel):
    action: str
    note: Optional[str] = None


class ComplianceIssueDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    bill_id: str
    shop_id: str
    issue_type: str
    severity: str
    rupee_value_at_risk: float
    explanation: str
    suggested_action: Optional[str] = None
    ca_action: str
    supplier_inquiry_draft: Optional[str] = None
    created_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


@router.get("", response_model=list[ComplianceIssueDetail])
def list_issues(
    shop_id: Optional[str] = None,
    severity: Optional[str] = None,
    ca_action: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(ComplianceIssueModel)
    if shop_id:
        query = query.filter(ComplianceIssueModel.shop_id == shop_id)
    if severity:
        query = query.filter(ComplianceIssueModel.severity == severity)
    if ca_action:
        query = query.filter(ComplianceIssueModel.ca_action == ca_action)
    return query.all()


@router.get("/{issue_id}", response_model=ComplianceIssueDetail)
def get_issue(issue_id: str, db: Session = Depends(get_db)):
    issue = db.query(ComplianceIssueModel).filter(ComplianceIssueModel.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    return issue


@router.post("/{issue_id}/decision", response_model=ComplianceIssueDetail)
def record_ca_decision(
    issue_id: str,
    payload: IssueActionRequest,
    db: Session = Depends(get_db),
):
    action = payload.action.lower().strip()
    if action not in ["approve", "reject", "ask_supplier"]:
        raise HTTPException(status_code=400, detail="Action must be 'approve', 'reject', or 'ask_supplier'")

    issue = db.query(ComplianceIssueModel).filter(ComplianceIssueModel.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    issue.ca_action = action
    issue.resolved_at = datetime.now(timezone.utc)

    bill = db.query(Bill).filter(Bill.id == issue.bill_id).first()
    if bill:
        if action == "approve":
            bill.status = "ca_approved"
        elif action == "reject":
            bill.status = "ca_rejected"

    db.commit()
    db.refresh(issue)
    return issue
