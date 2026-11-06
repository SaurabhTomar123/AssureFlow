from typing import List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from src.db.models import BankTransaction, Shop


class AccountAggregatorClient:
    def __init__(self, shop_gstin: str):
        self.shop_gstin = shop_gstin

    def fetch_recent_transactions(self, account_number: str = "HDFC0001928374") -> List[Dict[str, Any]]:
        # In production, connects to RBI-regulated Account Aggregator (AA) Consent Flow (e.g. Setu / OneMoney)
        # Returns standard financial data interchange format
        return [
            {
                "account_number": account_number,
                "txn_date": "2026-11-03",
                "narration": "UPI/202611030192/MODERN AGRO STAPLES/MAS-2026-101",
                "txn_type": "DEBIT",
                "amount": 7770.0,
                "mode": "UPI",
                "reference_no": "UPI-REF-MAS-101",
            },
            {
                "account_number": account_number,
                "txn_date": "2026-11-04",
                "narration": "NEFT/N104260012/ROYAL SPICES/RSC-2026-202",
                "txn_type": "DEBIT",
                "amount": 6720.0,
                "mode": "NEFT",
                "reference_no": "NEFT-REF-RSC-202",
            },
            {
                "account_number": account_number,
                "txn_date": "2026-11-06",
                "narration": "RTGS/R992019/DELHI COLD BEVERAGES/DCB-2026-404",
                "txn_type": "DEBIT",
                "amount": 11520.0,
                "mode": "RTGS",
                "reference_no": "RTGS-REF-992019",
            },
            {
                "account_number": account_number,
                "txn_date": "2026-11-10",
                "narration": "POS SETTLEMENT PAYTM QR MERCHANT CREDIT",
                "txn_type": "CREDIT",
                "amount": 42000.0,
                "mode": "UPI",
                "reference_no": "POS-PAYTM-44829",
            },
            {
                "account_number": account_number,
                "txn_date": "2026-11-12",
                "narration": "ATM CASH WITHDRAWAL LAJPAT NAGAR BRANCH",
                "txn_type": "DEBIT",
                "amount": 5000.0,
                "mode": "CASH",
                "reference_no": "ATM-TXN-11203",
            },
        ]


def ingest_bank_transactions(shop_id: str, transactions: List[Dict[str, Any]], db: Session) -> int:
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise ValueError(f"Shop {shop_id} not found")

    ingested = 0
    for txn in transactions:
        existing = (
            db.query(BankTransaction)
            .filter(
                BankTransaction.shop_id == shop_id,
                BankTransaction.reference_no == txn.get("reference_no"),
            )
            .first()
        )
        if not existing and txn.get("reference_no"):
            record = BankTransaction(
                tenant_id=shop.tenant_id,
                shop_id=shop.id,
                account_number=txn["account_number"],
                txn_date=txn["txn_date"],
                narration=txn["narration"],
                txn_type=txn["txn_type"],
                amount=float(txn["amount"]),
                mode=txn.get("mode", "UPI"),
                reference_no=txn.get("reference_no"),
                recon_status="UNRECONCILED",
            )
            db.add(record)
            ingested += 1
        elif existing:
            existing.amount = float(txn["amount"])
            existing.narration = txn["narration"]
            existing.recon_status = "UNRECONCILED"
            existing.matched_bill_id = None
            ingested += 1
    db.commit()
    return ingested
