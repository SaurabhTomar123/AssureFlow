import re
from typing import Dict, Any, List
from datetime import datetime
from sqlalchemy.orm import Session
from src.db.models import Bill, GSTR2BInwardRecord, ComplianceIssueModel, Shop
from src.gsp.client import GSPClient


def normalize_doc_number(doc_no: str) -> str:
    if not doc_no:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", doc_no).upper()


def normalize_gstin(gstin: str) -> str:
    if not gstin:
        return ""
    return gstin.strip().upper()


def generate_rule37a_supplier_notice(
    buyer_name: str,
    buyer_gstin: str,
    supplier_name: str,
    supplier_gstin: str,
    invoice_number: str,
    invoice_date: str,
    taxable_value: float,
    tax_amount: float,
    period: str,
) -> str:
    return (
        f"FORMAL NOTICE: NON-REFLECTION OF INVOICE IN GSTR-2B (GST RULE 37A)\n\n"
        f"To: {supplier_name} (GSTIN: {supplier_gstin})\n"
        f"From: {buyer_name} (GSTIN: {buyer_gstin})\n"
        f"Date: {datetime.utcnow().strftime('%d-%b-%Y')}\n"
        f"Return Period: {period}\n\n"
        f"Subject: Notice regarding non-appearance of Invoice #{invoice_number} in GSTR-2B.\n\n"
        f"Dear Accounts Team,\n"
        f"On reviewing our auto-drafted GSTR-2B statement for the period {period}, we observed that "
        f"the following tax invoice issued by your firm has not been reported in your GSTR-1 / IFF:\n\n"
        f"  - Invoice No: {invoice_number}\n"
        f"  - Invoice Date: {invoice_date}\n"
        f"  - Taxable Value: INR {taxable_value:,.2f}\n"
        f"  - GST Amount: INR {tax_amount:,.2f}\n\n"
        f"Pursuant to Section 16(2)(aa) of the CGST Act, 2017, Input Tax Credit (ITC) is strictly inadmissible "
        f"to us unless reported by the supplier in GSTR-1. Furthermore, under Rule 37A, failure to report will "
        f"compel us to reverse ITC along with interest under Section 50.\n\n"
        f"Please file or amend your return immediately to reflect this invoice. Outstanding disbursements "
        f"may be withheld pending verification in our GST portal.\n\n"
        f"Sincerely,\n"
        f"Finance & Compliance Division\n"
        f"{buyer_name}"
    )


def sync_gstr2b_feed(shop_id: str, return_period: str, db: Session) -> int:
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise ValueError(f"Shop with id {shop_id} not found")

    client = GSPClient()
    records = client.fetch_gstr2b_inward(shop.gstin, return_period)

    synced_count = 0
    for item in records:
        existing = (
            db.query(GSTR2BInwardRecord)
            .filter(
                GSTR2BInwardRecord.shop_id == shop.id,
                GSTR2BInwardRecord.supplier_gstin == item["supplier_gstin"],
                GSTR2BInwardRecord.invoice_number == item["invoice_number"],
                GSTR2BInwardRecord.filing_period == item["filing_period"],
            )
            .first()
        )
        if not existing:
            inward = GSTR2BInwardRecord(
                tenant_id=shop.tenant_id,
                shop_id=shop.id,
                supplier_gstin=item["supplier_gstin"],
                supplier_trade_name=item["supplier_trade_name"],
                invoice_number=item["invoice_number"],
                invoice_date=item["invoice_date"],
                invoice_value=item["invoice_value"],
                taxable_value=item["taxable_value"],
                igst=item["igst"],
                cgst=item["cgst"],
                sgst=item["sgst"],
                cess=item["cess"],
                filing_period=item["filing_period"],
                filing_date=item["filing_date"],
                itc_eligibility=item["itc_eligibility"],
                match_status="UNMATCHED",
            )
            db.add(inward)
        else:
            existing.invoice_value = item["invoice_value"]
            existing.taxable_value = item["taxable_value"]
            existing.igst = item["igst"]
            existing.cgst = item["cgst"]
            existing.sgst = item["sgst"]
            existing.cess = item["cess"]
            existing.filing_date = item["filing_date"]
            existing.itc_eligibility = item["itc_eligibility"]
            existing.match_status = "UNMATCHED"
            existing.matched_bill_id = None
        synced_count += 1
    db.commit()
    return synced_count


def reconcile_shop_purchases(shop_id: str, return_period: str, db: Session) -> Dict[str, Any]:
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise ValueError(f"Shop with id {shop_id} not found")

    bills = db.query(Bill).filter(Bill.shop_id == shop_id).all()
    portal_records = (
        db.query(GSTR2BInwardRecord)
        .filter(
            GSTR2BInwardRecord.shop_id == shop_id,
            GSTR2BInwardRecord.filing_period == return_period,
        )
        .all()
    )

    portal_map = {}
    for prec in portal_records:
        norm_key = (normalize_gstin(prec.supplier_gstin), normalize_doc_number(prec.invoice_number))
        portal_map[norm_key] = prec

    matched_count = 0
    mismatch_count = 0
    default_count = 0
    itc_at_risk = 0.0
    matched_itc = 0.0

    for bill in bills:
        bill_gstin = normalize_gstin(bill.supplier_gstin or "")
        bill_num = normalize_doc_number(bill.bill_number or "")
        key = (bill_gstin, bill_num)

        bill_tax = round((bill.cgst_amount or 0.0) + (bill.sgst_amount or 0.0) + (bill.igst_amount or 0.0), 2)

        if key in portal_map:
            prec = portal_map[key]
            if prec.match_status == "MATCHED":
                continue
            prec_tax = round((prec.cgst or 0.0) + (prec.sgst or 0.0) + (prec.igst or 0.0), 2)
            tax_diff = abs(bill_tax - prec_tax)

            if tax_diff <= 2.0:
                prec.match_status = "MATCHED"
                prec.matched_bill_id = bill.id
                matched_count += 1
                matched_itc += bill_tax
            else:
                prec.match_status = "MISMATCH"
                prec.matched_bill_id = bill.id
                mismatch_count += 1
                itc_at_risk += tax_diff

                existing_issue = (
                    db.query(ComplianceIssueModel)
                    .filter(
                        ComplianceIssueModel.bill_id == bill.id,
                        ComplianceIssueModel.issue_type == "GSTR2B_TAX_MISMATCH",
                    )
                    .first()
                )
                if not existing_issue:
                    notice = generate_rule37a_supplier_notice(
                        buyer_name=shop.name,
                        buyer_gstin=shop.gstin,
                        supplier_name=prec.supplier_trade_name or prec.supplier_gstin,
                        supplier_gstin=prec.supplier_gstin,
                        invoice_number=prec.invoice_number,
                        invoice_date=prec.invoice_date,
                        taxable_value=prec.taxable_value,
                        tax_amount=prec_tax,
                        period=return_period,
                    )
                    issue = ComplianceIssueModel(
                        bill_id=bill.id,
                        shop_id=shop.id,
                        issue_type="GSTR2B_TAX_MISMATCH",
                        severity="HIGH",
                        rupee_value_at_risk=tax_diff,
                        explanation=f"Bill {bill.bill_number} tax (INR {bill_tax}) differs from supplier filed tax (INR {prec_tax}) in GSTR-2B.",
                        suggested_action="Draft notice to supplier to amend in next GSTR-1 return under Rule 37A.",
                        supplier_inquiry_draft=notice,
                    )
                    db.add(issue)
        else:
            default_count += 1
            itc_at_risk += bill_tax

            existing_issue = (
                db.query(ComplianceIssueModel)
                .filter(
                    ComplianceIssueModel.bill_id == bill.id,
                    ComplianceIssueModel.issue_type == "SUPPLIER_DEFAULT_UNFILED",
                )
                .first()
            )
            if not existing_issue and bill_tax > 0:
                notice = generate_rule37a_supplier_notice(
                    buyer_name=shop.name,
                    buyer_gstin=shop.gstin,
                    supplier_name=bill.supplier_name or bill_gstin,
                    supplier_gstin=bill_gstin,
                    invoice_number=bill.bill_number or "UNKNOWN",
                    invoice_date=bill.bill_date or datetime.utcnow().strftime("%Y-%m-%d"),
                    taxable_value=bill.taxable_amount or 0.0,
                    tax_amount=bill_tax,
                    period=return_period,
                )
                issue = ComplianceIssueModel(
                    bill_id=bill.id,
                    shop_id=shop.id,
                    issue_type="SUPPLIER_DEFAULT_UNFILED",
                    severity="CRITICAL",
                    rupee_value_at_risk=bill_tax,
                    explanation=f"Supplier {bill.supplier_name or bill_gstin} failed to report bill {bill.bill_number} in GSTR-1. ITC of INR {bill_tax:,.2f} is blocked under Section 16(2)(aa).",
                    suggested_action="Hold supplier payment until invoice reflects in GSTR-2B; issue Rule 37A warning.",
                    supplier_inquiry_draft=notice,
                )
                db.add(issue)

    unrecorded_purchases = [p for p in portal_records if p.match_status == "UNMATCHED"]
    unrecorded_itc = sum((p.cgst or 0.0) + (p.sgst or 0.0) + (p.igst or 0.0) for p in unrecorded_purchases)

    db.commit()

    return {
        "shop_id": shop_id,
        "return_period": return_period,
        "total_books_bills": len(bills),
        "total_portal_invoices": len(portal_records),
        "matched_count": matched_count,
        "tax_mismatch_count": mismatch_count,
        "supplier_default_count": default_count,
        "unrecorded_purchase_count": len(unrecorded_purchases),
        "matched_itc": round(matched_itc, 2),
        "itc_at_risk": round(itc_at_risk, 2),
        "unrecorded_potential_itc": round(unrecorded_itc, 2),
        "reconciliation_timestamp": datetime.utcnow().isoformat(),
    }
