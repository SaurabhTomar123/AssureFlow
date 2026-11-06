from typing import Dict, Any, List
from sqlalchemy.orm import Session
from src.db.models import Bill, ComplianceIssueModel, GSTR2BInwardRecord, BankTransaction, Shop


def compute_shop_audit_risk(shop_id: str, db: Session) -> Dict[str, Any]:
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise ValueError(f"Shop with id {shop_id} not found")

    bills = db.query(Bill).filter(Bill.shop_id == shop_id).all()
    issues = db.query(ComplianceIssueModel).filter(ComplianceIssueModel.shop_id == shop_id).all()
    portal_records = db.query(GSTR2BInwardRecord).filter(GSTR2BInwardRecord.shop_id == shop_id).all()
    bank_txns = db.query(BankTransaction).filter(BankTransaction.shop_id == shop_id).all()

    open_issues = [i for i in issues if i.ca_action != "resolved_by_vendor"]
    serious_issues = [i for i in open_issues if i.severity == "serious"]
    critical_issues = [i for i in open_issues if i.severity == "CRITICAL"]

    default_records = [p for p in portal_records if p.match_status in ["MISMATCH", "UNMATCHED"]]
    unreconciled_debits = [b for b in bank_txns if b.txn_type == "DEBIT" and b.recon_status != "RECONCILED"]

    # Calculate audit risk score (0 to 100)
    risk_score = 10
    risk_score += len(critical_issues) * 20
    risk_score += len(serious_issues) * 12
    risk_score += len(open_issues) * 4
    risk_score += len(default_records) * 5
    risk_score += min(len(unreconciled_debits) * 3, 15)

    risk_score = min(max(risk_score, 5), 100)

    if risk_score <= 25:
        risk_level = "LOW (Audit-Proof)"
    elif risk_score <= 50:
        risk_level = "MODERATE"
    elif risk_score <= 75:
        risk_level = "ELEVATED"
    else:
        risk_level = "CRITICAL (High Scrutiny Notice Risk)"

    # Supplier risk scorecard
    supplier_map: Dict[str, Dict[str, Any]] = {}
    for b in bills:
        gstin = b.supplier_gstin or "UNREGISTERED"
        if gstin not in supplier_map:
            supplier_map[gstin] = {
                "supplier_name": b.supplier_name or "Unknown Supplier",
                "supplier_gstin": gstin,
                "total_invoices": 0,
                "defaulted_invoices": 0,
                "total_spend": 0.0,
            }
        supplier_map[gstin]["total_invoices"] += 1
        supplier_map[gstin]["total_spend"] += (b.total_amount or 0.0)

    for i in issues:
        bill = db.query(Bill).filter(Bill.id == i.bill_id).first()
        if bill and bill.supplier_gstin in supplier_map:
            supplier_map[bill.supplier_gstin]["defaulted_invoices"] += 1

    supplier_scorecard = []
    for gstin, data in supplier_map.items():
        defaults = data["defaulted_invoices"]
        total = data["total_invoices"]
        if defaults == 0:
            badge = "A+ Safe Partner"
            rating = 5
        elif defaults / max(total, 1) < 0.3:
            badge = "B Watchlist"
            rating = 3
        else:
            badge = "C High Defaulter Risk"
            rating = 1

        supplier_scorecard.append({
            "supplier_name": data["supplier_name"],
            "supplier_gstin": data["supplier_gstin"],
            "total_invoices": total,
            "defaulted_invoices": defaults,
            "total_spend": round(data["total_spend"], 2),
            "compliance_badge": badge,
            "rating": rating,
        })

    # Recommended mitigation actions
    recommendations = []
    if critical_issues:
        recommendations.append("Execute Rule 37A demand notices for unfiled supplier invoices before payment release.")
    if serious_issues:
        recommendations.append("Correct wrong Place of Supply tax classifications before GSTR-3B return submission.")
    if len(unreconciled_debits) > 2:
        recommendations.append("Reconcile pending bank disbursements to ensure matching invoice entries in books.")
    if not recommendations:
        recommendations.append("All ledgers clean and reconciled. System is ready for safe GSTR-3B monthly filing.")

    # Verifiable MSME credit solvency metric (300 to 900 scale)
    credit_solvency_score = max(300, min(900, int(880 - (risk_score * 4.8))))

    return {
        "shop_id": shop_id,
        "shop_name": shop.name,
        "audit_risk_score": risk_score,
        "risk_level": risk_level,
        "credit_solvency_score": credit_solvency_score,
        "open_issues_count": len(open_issues),
        "critical_issues_count": len(critical_issues),
        "unreconciled_bank_debits": len(unreconciled_debits),
        "top_recommendations": recommendations,
        "supplier_scorecard": supplier_scorecard,
    }

