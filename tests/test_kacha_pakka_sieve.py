import pytest
from src.db.session import SessionLocal
from src.db.models import Shop, Bill, BillItem, InventoryItem, LedgerEntry
from src.extraction.document_classifier import classify_document_type, triage_kacha_pakka


def test_classify_pakka_tax_invoice():
    raw_text = (
        "TAX INVOICE\n"
        "Modern Agro Staples Ltd\n"
        "GSTIN: 07MODER1111A1Z1\n"
        "Invoice No: MAS-2026-101\n"
        "Taxable Value: 7400.00\n"
        "CGST (2.5%): 185.00\n"
        "SGST (2.5%): 185.00\n"
        "Total: 7770.00\n"
    )
    extracted = {
        "supplier_name": "Modern Agro Staples Ltd",
        "supplier_gstin": "07MODER1111A1Z1",
        "cgst": 185.0,
        "sgst": 185.0,
        "total_amount": 7770.0,
    }
    result = classify_document_type(raw_text, extracted)
    assert result == "PAKKA_TAX_INVOICE"


def test_classify_kacha_estimate_slip():
    raw_text = (
        "KACHA ESTIMATE SLIP\n"
        "Ramu Mandi Dalal\n"
        "Rate slip only - no tax\n"
        "Atta 10 bori: 3500\n"
        "Chawal 5 bori: 2500\n"
        "Total: 6000\n"
    )
    extracted = {
        "supplier_name": "Ramu Mandi Dalal",
        "supplier_gstin": None,
        "cgst": 0.0,
        "sgst": 0.0,
        "total_amount": 6000.0,
    }
    result = classify_document_type(raw_text, extracted)
    assert result == "KACHA_ESTIMATE_SLIP"


def test_triage_kacha_slip_execution():
    db = SessionLocal()
    try:
        shop = db.query(Shop).filter(Shop.id == "shop-sharma-kirana").first()
        assert shop is not None

        bill = Bill(
            shop_id=shop.id,
            file_path="synthetic_data/kacha_slip_sample.pdf",
            supplier_name="Ramu Mandi Dalal",
            supplier_gstin=None,
            bill_number="EST-9988",
            bill_date="2026-11-04",
            taxable_amount=6000.0,
            cgst_amount=0.0,
            sgst_amount=0.0,
            total_amount=6000.0,
            status="pending_review",
        )
        db.add(bill)
        db.flush()

        item = BillItem(
            bill_id=bill.id,
            description="Desi Chana 50kg Bori",
            quantity=5.0,
            rate=1200.0,
            taxable_value=6000.0,
            total=6000.0,
        )
        db.add(item)
        db.commit()

        raw_text = "ESTIMATE MEMORANDUM - Ramu Mandi Dalal - Desi Chana 5 bori Total 6000"
        extracted = {
            "supplier_name": "Ramu Mandi Dalal",
            "supplier_gstin": None,
            "invoice_date": "2026-11-04",
            "total_amount": 6000.0,
        }

        res = triage_kacha_pakka(bill.id, raw_text, extracted, shop.id, db)

        assert res["document_category"] == "KACHA_ESTIMATE_SLIP"
        assert res["is_gst_eligible"] is False
        assert res["quarantined_from_gst_returns"] is True
        assert res["inventory_restocked"] is True
        assert "Section 122 penalty" in res["advisory_message"]

        db.refresh(bill)
        assert bill.status == "quarantined_internal_only"
        assert bill.document_category == "KACHA_ESTIMATE_SLIP"

        # Verify ledger entry
        ledger = (
            db.query(LedgerEntry)
            .filter(LedgerEntry.bill_id == bill.id, LedgerEntry.category == "KACHA_INVENTORY_PURCHASE")
            .first()
        )
        assert ledger is not None
        assert ledger.total_outflow == 6000.0

        # Verify stock updated
        inv = db.query(InventoryItem).filter(InventoryItem.name.like("%Desi Chana%")).first()
        assert inv is not None
        assert inv.current_stock >= 5.0

    finally:
        db.close()
