import re
from typing import Dict, Any, List
from datetime import datetime
from sqlalchemy.orm import Session
from src.db.models import Bill, GSTR2BInwardRecord, BankTransaction, ComplianceIssueModel, Shop
from src.gsp.reconciler import normalize_doc_number


def run_three_way_reconciliation(shop_id: str, db: Session) -> Dict[str, Any]:
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise ValueError(f"Shop {shop_id} not found")

    bills = db.query(Bill).filter(Bill.shop_id == shop_id).all()
    portal_records = db.query(GSTR2BInwardRecord).filter(GSTR2BInwardRecord.shop_id == shop_id).all()
    bank_txns = (
        db.query(BankTransaction)
        .filter(BankTransaction.shop_id == shop_id, BankTransaction.txn_type == "DEBIT")
        .all()
    )

    portal_by_bill_id = {}
    for prec in portal_records:
        if prec.matched_bill_id:
            portal_by_bill_id[prec.matched_bill_id] = prec

    bank_by_bill_id = {}
    for txn in bank_txns:
        candidate_bills = []
        for bill in bills:
            norm_num = normalize_doc_number(bill.bill_number or "")
            if norm_num and norm_num in normalize_doc_number(txn.narration):
                candidate_bills.append(bill)
            elif bill.total_amount and abs(txn.amount - bill.total_amount) <= 1.0:
                supplier_words = (bill.supplier_name or "").upper().split()
                if any(w in txn.narration.upper() for w in supplier_words if len(w) > 3):
                    candidate_bills.append(bill)

        matched_bill = None
        if candidate_bills:
            portal_candidates = [b for b in candidate_bills if b.id in portal_by_bill_id]
            matched_bill = portal_candidates[0] if portal_candidates else candidate_bills[0]

        if matched_bill:
            txn.matched_bill_id = matched_bill.id
            txn.recon_status = "RECONCILED"
            bank_by_bill_id[matched_bill.id] = txn

    three_way_matched = []
    unpaid_verified = []
    payment_without_gstr2b = []
    unmatched_bills = []

    total_settled_amount = 0.0
    at_risk_disbursed_itc = 0.0

    for bill in bills:
        has_portal_match = (
            bill.id in portal_by_bill_id
            and portal_by_bill_id[bill.id].match_status == "MATCHED"
        )
        has_bank_payment = bill.id in bank_by_bill_id
        tax_total = (bill.cgst_amount or 0.0) + (bill.sgst_amount or 0.0) + (bill.igst_amount or 0.0)

        bill_info = {
            "bill_id": bill.id,
            "bill_number": bill.bill_number,
            "supplier_name": bill.supplier_name,
            "supplier_gstin": bill.supplier_gstin,
            "total_amount": bill.total_amount,
            "tax_amount": tax_total,
            "has_portal_match": has_portal_match,
            "has_bank_payment": has_bank_payment,
        }

        if has_portal_match and has_bank_payment:
            bill_info["status"] = "THREE_WAY_MATCHED"
            bill_info["details"] = "Bill recorded, GSTR-2B confirmed, and bank payment settled."
            three_way_matched.append(bill_info)
            total_settled_amount += bill.total_amount or 0.0

        elif has_portal_match and not has_bank_payment:
            bill_info["status"] = "UNPAID_PURCHASE_VERIFIED"
            bill_info["details"] = "Verified in GSTR-2B, awaiting bank settlement (Safe Accounts Payable)."
            unpaid_verified.append(bill_info)

        elif not has_portal_match and has_bank_payment:
            bill_info["status"] = "PAYMENT_WITHOUT_GSTR2B"
            bill_info["details"] = "Payment disbursed to supplier, but invoice NOT reflected in GSTR-2B. High risk."
            payment_without_gstr2b.append(bill_info)
            at_risk_disbursed_itc += tax_total

            existing_issue = (
                db.query(ComplianceIssueModel)
                .filter(
                    ComplianceIssueModel.bill_id == bill.id,
                    ComplianceIssueModel.issue_type == "PAID_BUT_UNFILED_GSTR2B",
                )
                .first()
            )
            if not existing_issue:
                issue = ComplianceIssueModel(
                    bill_id=bill.id,
                    shop_id=shop_id,
                    issue_type="PAID_BUT_UNFILED_GSTR2B",
                    severity="CRITICAL",
                    rupee_value_at_risk=tax_total,
                    explanation=(
                        f"Bill {bill.bill_number} (INR {bill.total_amount:,.2f}) has been paid via bank, "
                        f"but supplier {bill.supplier_name} has not filed it in GSTR-1. Claimed ITC is blocked."
                    ),
                    suggested_action="Immediately demand GSTR-1 amendment or initiate recovery notice under Rule 37A.",
                )
                db.add(issue)

        else:
            bill_info["status"] = "UNMATCHED_BILL"
            bill_info["details"] = "Pending verification in GSTR-2B portal and pending payment."
            unmatched_bills.append(bill_info)

    unreconciled_debits = [t for t in bank_txns if t.recon_status != "RECONCILED"]

    db.commit()

    return {
        "shop_id": shop_id,
        "shop_name": shop.name,
        "summary": {
            "total_bills_evaluated": len(bills),
            "three_way_matched_count": len(three_way_matched),
            "unpaid_verified_count": len(unpaid_verified),
            "payment_without_gstr2b_count": len(payment_without_gstr2b),
            "unmatched_bills_count": len(unmatched_bills),
            "unreconciled_bank_debits_count": len(unreconciled_debits),
            "total_settled_amount": round(total_settled_amount, 2),
            "at_risk_disbursed_itc": round(at_risk_disbursed_itc, 2),
        },
        "three_way_matched": three_way_matched,
        "unpaid_verified": unpaid_verified,
        "payment_without_gstr2b": payment_without_gstr2b,
        "unmatched_bills": unmatched_bills,
        "unreconciled_debits": [
            {
                "txn_id": t.id,
                "amount": t.amount,
                "narration": t.narration,
                "txn_date": t.txn_date,
                "mode": t.mode,
            }
            for t in unreconciled_debits
        ],
        "reconciliation_timestamp": datetime.utcnow().isoformat(),
    }
