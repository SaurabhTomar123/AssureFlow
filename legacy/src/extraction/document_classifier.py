import re
from typing import Dict, Any
from sqlalchemy.orm import Session
from src.db.models import Bill, LedgerEntry, Shop
from src.inventory.service import restock_inventory_from_bill

GSTIN_REGEX = re.compile(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}\b")

KACHA_INDICATORS = [
    "estimate",
    "kachha",
    "kacha",
    "rough",
    "quotation",
    "order slip",
    "counter slip",
    "memorandum",
    "challan only",
    "not for tax",
    "non gst",
    "delivery note",
]

PAKKA_INDICATORS = [
    "tax invoice",
    "gst invoice",
    "bill of supply",
    "original for recipient",
    "duplicate for transporter",
]


def classify_document_type(raw_text: str, extracted_data: Dict[str, Any]) -> str:
    text_lower = (raw_text or "").lower()
    supplier_gstin = extracted_data.get("supplier_gstin") or ""

    has_gstin = bool(GSTIN_REGEX.search(supplier_gstin) or GSTIN_REGEX.search(raw_text or ""))
    has_kacha_keyword = any(k in text_lower for k in KACHA_INDICATORS)
    has_pakka_keyword = any(k in text_lower for k in PAKKA_INDICATORS)

    cgst = extracted_data.get("cgst", 0.0) or 0.0
    sgst = extracted_data.get("sgst", 0.0) or 0.0
    igst = extracted_data.get("igst", 0.0) or 0.0
    has_tax_breakdown = (cgst + sgst + igst) > 0.0

    if has_kacha_keyword and not has_gstin:
        return "KACHA_ESTIMATE_SLIP"

    if not has_gstin and not has_pakka_keyword and not has_tax_breakdown:
        return "KACHA_ESTIMATE_SLIP"

    return "PAKKA_TAX_INVOICE"


def triage_kacha_pakka(
    bill_id: str,
    raw_text: str,
    extracted_data: Dict[str, Any],
    shop_id: str,
    db: Session,
) -> Dict[str, Any]:
    doc_type = classify_document_type(raw_text, extracted_data)

    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if bill:
        bill.document_category = doc_type

    if doc_type == "KACHA_ESTIMATE_SLIP":
        if bill:
            bill.status = "quarantined_internal_only"
            bill.is_confirmed_by_owner = True

        restocked_items = restock_inventory_from_bill(bill_id, db)

        total_amount = float(extracted_data.get("total_amount", 0.0) or 0.0)
        supplier_name = extracted_data.get("supplier_name") or "Local Counter Vendor"
        bill_date = extracted_data.get("invoice_date") or "2026-11-01"

        ledger = LedgerEntry(
            shop_id=shop_id,
            bill_id=bill_id,
            category="KACHA_INVENTORY_PURCHASE",
            description=f"Internal procurement via informal counter slip from {supplier_name}",
            amount=total_amount,
            tax_amount=0.0,
            total_outflow=total_amount,
            entry_date=bill_date,
        )
        db.add(ledger)
        db.commit()

        return {
            "bill_id": bill_id,
            "document_category": "KACHA_ESTIMATE_SLIP",
            "is_gst_eligible": False,
            "quarantined_from_gst_returns": True,
            "inventory_restocked": True,
            "restocked_items_count": len(restocked_items),
            "accounts_ledger_updated": True,
            "advisory_message": (
                "Informal counter chit processed for store inventory and cash khata. "
                "Quarantined from CA return queue to prevent Section 122 penalty notices."
            ),
        }

    db.commit()
    return {
        "bill_id": bill_id,
        "document_category": "PAKKA_TAX_INVOICE",
        "is_gst_eligible": True,
        "quarantined_from_gst_returns": False,
        "inventory_restocked": False,
        "accounts_ledger_updated": False,
        "advisory_message": "Formal tax invoice confirmed. Proceeding to deterministic GST compliance audit.",
    }

