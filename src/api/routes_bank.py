from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.db.models import Shop, BankTransaction
from src.accounts.bank_client import AccountAggregatorClient, ingest_bank_transactions
from src.accounts.three_way_recon import run_three_way_reconciliation

router = APIRouter(prefix="/api/bank", tags=["Account Aggregator & Bank 3-Way Reconciliation"])


class IngestStatementRequest(BaseModel):
    shop_id: str
    account_number: Optional[str] = "HDFC0001928374"
    transactions: Optional[List[Dict[str, Any]]] = None


class ReconcileThreeWayRequest(BaseModel):
    shop_id: str


@router.post("/ingest-statement")
def ingest_statement(req: IngestStatementRequest, db: Session = Depends(get_db)):
    shop = db.query(Shop).filter(Shop.id == req.shop_id).first()
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Shop {req.shop_id} not found")

    if req.transactions:
        txns = req.transactions
    else:
        client = AccountAggregatorClient(shop.gstin)
        txns = client.fetch_recent_transactions(req.account_number)

    count = ingest_bank_transactions(req.shop_id, txns, db)
    return {
        "status": "success",
        "shop_id": req.shop_id,
        "account_number": req.account_number,
        "ingested_count": count,
    }


@router.post("/three-way-reconcile")
def execute_three_way_reconciliation(req: ReconcileThreeWayRequest, db: Session = Depends(get_db)):
    try:
        report = run_three_way_reconciliation(req.shop_id, db)
        return report
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/recon-status/{shop_id}")
def get_bank_recon_status(shop_id: str, db: Session = Depends(get_db)):
    txns = db.query(BankTransaction).filter(BankTransaction.shop_id == shop_id).all()
    if not txns:
        return {
            "shop_id": shop_id,
            "total_transactions": 0,
            "reconciled_count": 0,
            "unreconciled_count": 0,
            "message": "No bank transactions recorded. Ingest statement or connect Account Aggregator.",
        }

    reconciled = sum(1 for t in txns if t.recon_status == "RECONCILED")
    unreconciled = len(txns) - reconciled

    return {
        "shop_id": shop_id,
        "total_transactions": len(txns),
        "reconciled_count": reconciled,
        "unreconciled_count": unreconciled,
    }
