import pytest
from datetime import date
from fastapi.testclient import TestClient
from src.api.main import app
from src.db.session import SessionLocal
from src.db.models import Shop, Bill, GSTR2BInwardRecord
from src.accounts.double_entry import (
    create_journal_entry,
    record_bill_journal_entry,
    record_bank_disbursement_journal_entry,
    record_shrinkage_journal_entry,
    get_trial_balance,
    get_profit_and_loss,
    get_balance_sheet,
    get_cash_flow_forecast,
    get_vendor_payment_priority_queue,
)

client = TestClient(app)


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_balanced_journal_entry_validation(db_session):
    shop = Shop(name="Journal Test Shop", gstin="27AABCU9603R1Z4", state_code="27")
    db_session.add(shop)
    db_session.commit()

    with pytest.raises(ValueError, match="Unbalanced journal entry"):
        create_journal_entry(
            shop_id=shop.id,
            entry_date=date.today().isoformat(),
            reference_type="MANUAL",
            description="Unbalanced entry test",
            lines_data=[
                {"account_code": "1040", "debit": 500.0, "credit": 0.0},
                {"account_code": "2010", "debit": 0.0, "credit": 400.0},
            ],
            db=db_session,
        )

    entry = create_journal_entry(
        shop_id=shop.id,
        entry_date=date.today().isoformat(),
        reference_type="MANUAL",
        description="Balanced capital injection",
        lines_data=[
            {"account_code": "1020", "debit": 50000.0, "credit": 0.0},
            {"account_code": "3010", "debit": 0.0, "credit": 50000.0},
        ],
        db=db_session,
    )
    assert entry.id is not None
    assert entry.total_debit == 50000.0
    assert entry.total_credit == 50000.0
    assert len(entry.lines) == 2


def test_record_bill_journal_entry(db_session):
    shop = Shop(name="Bill Journal Shop", gstin="27AABCU9603R1Z5", state_code="27")
    db_session.add(shop)
    db_session.commit()

    bill = Bill(
        shop_id=shop.id,
        file_path="/tmp/hul_test.pdf",
        supplier_name="Hindustan Unilever Ltd",
        supplier_gstin="27AAACH1111A1Z1",
        bill_number="HUL-901",
        bill_date=date.today().isoformat(),
        taxable_amount=10000.0,
        cgst_amount=900.0,
        sgst_amount=900.0,
        igst_amount=0.0,
        total_amount=11800.0,
        status="CONFIRMED",
    )
    db_session.add(bill)
    db_session.commit()

    je = record_bill_journal_entry(bill.id, db_session)
    assert je is not None
    assert je.total_debit == 11800.0
    assert je.total_credit == 11800.0
    assert len(je.lines) == 4

    debits = {l.account_code: l.debit for l in je.lines if l.debit > 0}
    assert debits["1040"] == 10000.0
    assert debits["1050"] == 900.0
    assert debits["1051"] == 900.0

    credits = {l.account_code: l.credit for l in je.lines if l.credit > 0}
    assert credits["2010"] == 11800.0

    je_second = record_bill_journal_entry(bill.id, db_session)
    assert je_second.id == je.id


def test_trial_balance_and_financial_statements(db_session):
    shop = Shop(name="Full Financials Shop", gstin="27AABCU9603R1Z6", state_code="27")
    db_session.add(shop)
    db_session.commit()

    create_journal_entry(
        shop_id=shop.id,
        entry_date=date.today().isoformat(),
        reference_type="CAPITAL",
        description="Owner initial equity investment",
        lines_data=[
            {"account_code": "1020", "debit": 100000.0, "credit": 0.0},
            {"account_code": "3010", "debit": 0.0, "credit": 100000.0},
        ],
        db=db_session,
    )

    create_journal_entry(
        shop_id=shop.id,
        entry_date=date.today().isoformat(),
        reference_type="SALES",
        description="Weekly retail store sales",
        lines_data=[
            {"account_code": "1010", "debit": 25000.0, "credit": 0.0},
            {"account_code": "4010", "debit": 0.0, "credit": 25000.0},
        ],
        db=db_session,
    )

    create_journal_entry(
        shop_id=shop.id,
        entry_date=date.today().isoformat(),
        reference_type="EXPENSE",
        description="Store electricity bill payment",
        lines_data=[
            {"account_code": "5020", "debit": 4000.0, "credit": 0.0},
            {"account_code": "1020", "debit": 0.0, "credit": 4000.0},
        ],
        db=db_session,
    )

    tb = get_trial_balance(shop.id, db_session)
    assert tb["is_balanced"] is True
    assert tb["total_debits"] == tb["total_credits"]

    pnl = get_profit_and_loss(shop.id, db_session)
    assert pnl["total_revenue"] == 25000.0
    assert pnl["total_expenses"] == 4000.0
    assert pnl["net_profit"] == 21000.0
    assert pnl["is_profitable"] is True

    bs = get_balance_sheet(shop.id, db_session)
    assert bs["total_assets"] == 121000.0
    assert bs["is_balanced"] is True


def test_cash_flow_forecast_and_vendor_priority(db_session):
    shop = Shop(name="Treasury Shop", gstin="27AABCU9603R1Z7", state_code="27")
    db_session.add(shop)
    db_session.commit()

    bill_matched = Bill(
        shop_id=shop.id,
        file_path="/tmp/rel_test.pdf",
        supplier_name="Reliable Distributor",
        supplier_gstin="27AABCR1234F1Z1",
        bill_number="REL-101",
        bill_date=date.today().isoformat(),
        taxable_amount=20000.0,
        cgst_amount=1800.0,
        sgst_amount=1800.0,
        igst_amount=0.0,
        total_amount=23600.0,
        status="CONFIRMED",
    )
    bill_unfiled = Bill(
        shop_id=shop.id,
        file_path="/tmp/def_test.pdf",
        supplier_name="Defaulting Wholesaler",
        supplier_gstin="27AABCD9999K1Z9",
        bill_number="DEF-202",
        bill_date=date.today().isoformat(),
        taxable_amount=15000.0,
        cgst_amount=1350.0,
        sgst_amount=1350.0,
        igst_amount=0.0,
        total_amount=17700.0,
        status="CONFIRMED",
    )
    db_session.add_all([bill_matched, bill_unfiled])
    db_session.commit()

    gstr_record = GSTR2BInwardRecord(
        shop_id=shop.id,
        invoice_number="REL-101",
        invoice_date=date.today().isoformat(),
        filing_period="2026-11",
        supplier_gstin="27AABCR1234F1Z1",
        supplier_trade_name="Reliable Distributor",
        taxable_value=20000.0,
        cgst=1800.0,
        sgst=1800.0,
        igst=0.0,
        match_status="MATCHED",
        itc_eligibility="ELIGIBLE",
    )
    db_session.add(gstr_record)
    db_session.commit()

    forecast = get_cash_flow_forecast(shop.id, db_session)
    assert forecast["liquid_cash_balance"] > 0
    assert forecast["total_projected_outflows_30d"] > 0
    assert "safety_index" in forecast

    queue = get_vendor_payment_priority_queue(shop.id, db_session)
    assert len(queue) >= 2
    top_bill = queue[0]
    assert top_bill["bill_number"] == "REL-101"
    assert top_bill["recommended_action"] == "PAY_IMMEDIATELY"

    bottom_bill = queue[1]
    assert bottom_bill["bill_number"] == "DEF-202"
    assert bottom_bill["recommended_action"] == "HOLD_PAYMENT_DEFAULT"


def test_double_entry_api_endpoints(db_session):
    shop = Shop(name="API Financials Shop", gstin="27AABCU9603R1Z8", state_code="27")
    db_session.add(shop)
    db_session.commit()

    bill = Bill(
        shop_id=shop.id,
        file_path="/tmp/brit_test.pdf",
        supplier_name="Britannia Industries",
        supplier_gstin="27AAACB2222C1Z2",
        bill_number="BRIT-555",
        bill_date=date.today().isoformat(),
        taxable_amount=5000.0,
        cgst_amount=250.0,
        sgst_amount=250.0,
        igst_amount=0.0,
        total_amount=5500.0,
        status="CONFIRMED",
    )
    db_session.add(bill)
    db_session.commit()

    resp_sync = client.post(f"/api/advisory/double-entry/{shop.id}/sync-bills")
    assert resp_sync.status_code == 200
    assert resp_sync.json()["synced_count"] >= 1

    resp_tb = client.get(f"/api/advisory/double-entry/{shop.id}/trial-balance")
    assert resp_tb.status_code == 200
    assert resp_tb.json()["is_balanced"] is True

    resp_pnl = client.get(f"/api/advisory/double-entry/{shop.id}/profit-loss")
    assert resp_pnl.status_code == 200

    resp_bs = client.get(f"/api/advisory/double-entry/{shop.id}/balance-sheet")
    assert resp_bs.status_code == 200
    assert resp_bs.json()["is_balanced"] is True

    resp_cf = client.get(f"/api/advisory/treasury/{shop.id}/cash-flow-forecast")
    assert resp_cf.status_code == 200
    assert "safety_index" in resp_cf.json()

    resp_queue = client.get(f"/api/advisory/treasury/{shop.id}/vendor-payment-priority")
    assert resp_queue.status_code == 200
    assert len(resp_queue.json()) >= 1
