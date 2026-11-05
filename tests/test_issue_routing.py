from src.agents.bill_reader import BillReaderAgent
from src.agents.gst_checker import GSTCheckerAgent
from src.agents.follow_up import FollowUpAgent
from src.agents.return_preparer import ReturnPreparerAgent
from src.gst_engine.checksum import generate_valid_gstin


def test_bill_reader_agent_flow():
    reader = BillReaderAgent()
    doc_result = reader.process_document("synthetic_data/bills_pdf/bill_01_clean_kirana_5pct.pdf", language="en")
    assert doc_result["status"] == "extracted"
    assert "Modern Agro Staples" in doc_result["confirmation_message"]
    assert "Tax Breakdown" in doc_result["confirmation_message"]

    doc_result_hi = reader.process_document("synthetic_data/bills_pdf/bill_01_clean_kirana_5pct.pdf", language="hi")
    assert "Bill Prapt Hua" in doc_result_hi["confirmation_message"]


def test_gst_checker_routing():
    checker = GSTCheckerAgent()
    buyer = generate_valid_gstin("07", "BUYER1111A")
    supplier_intrastate = generate_valid_gstin("07", "SUPPL2222B")
    supplier_interstate = generate_valid_gstin("27", "SUPPL3333C")

    clean_bill = {
        "supplier_name": "ABC Goods",
        "supplier_gstin": supplier_intrastate,
        "bill_number": "B-101",
        "bill_date": "2026-11-01",
        "taxable_amount": 1000.0,
        "cgst_amount": 90.0,
        "sgst_amount": 90.0,
        "igst_amount": 0.0,
        "total_amount": 1180.0,
    }
    res_clean = checker.check_compliance(clean_bill, buyer_gstin=buyer)
    assert res_clean["status"] == "clean"
    assert res_clean["is_clean"] is True

    blurry_bill = dict(clean_bill)
    blurry_bill["is_blurry"] = True
    res_simple = checker.check_compliance(blurry_bill, buyer_gstin=buyer)
    assert res_simple["status"] == "requires_owner_clarification"
    assert len(res_simple["simple_issues"]) >= 1

    wrong_tax_bill = dict(clean_bill)
    wrong_tax_bill["supplier_gstin"] = supplier_interstate
    res_serious = checker.check_compliance(wrong_tax_bill, buyer_gstin=buyer)
    assert res_serious["status"] == "requires_ca_review"
    assert len(res_serious["serious_issues"]) >= 1


def test_follow_up_agent_alerts():
    follow_up = FollowUpAgent()
    alert_en = follow_up.generate_owner_alert(
        bill_data={"bill_number": "INV-555", "supplier_name": "XYZ Corp"},
        issue_data={"rupee_value_at_risk": 180.0, "explanation": "Supplier GSTIN missing"},
        language="en",
    )
    assert "INV-555" in alert_en
    assert "INR 180.00" in alert_en
    assert "Input Tax Credit at risk" in alert_en

    reminder = follow_up.generate_deadline_reminder(
        shop_name="Sharma Kirana",
        days_remaining=3,
        bills_submitted=45,
        last_month_bills=60,
    )
    assert "3 days remaining" in reminder


def test_return_preparer_ca_alert_and_summary():
    preparer = ReturnPreparerAgent()
    alert = preparer.format_ca_alert(
        shop_name="Sharma Kirana",
        bill_data={
            "id": "b-999",
            "bill_number": "INV-777",
            "bill_date": "2026-11-03",
            "supplier_name": "State Ceramic",
            "supplier_gstin": "24AAAAA0000A1Z5",
            "total_amount": 11800.0,
        },
        issue_data={
            "issue_type": "WRONG_TAX_TYPE",
            "explanation": "Interstate supply charged CGST/SGST instead of IGST",
            "rupee_value_at_risk": 1800.0,
        },
    )
    assert "CA Action Required" in alert["ca_message"]
    assert "/approve" in alert["ca_message"]
    assert "/reject" in alert["ca_message"]
    assert "/ask_supplier" in alert["ca_message"]
    assert "Section 16(2)" in alert["inquiry_draft"]

    summary_msg = preparer.format_month_end_summary({
        "shop_name": "Sharma Kirana",
        "shop_gstin": "07AAAAA0000A1Z5",
        "clean_bills": 14,
        "open_issues_count": 2,
        "itc_at_risk": 2160.0,
        "eligible_itc": {"cgst": 5000.0, "sgst": 5000.0, "igst": 3000.0, "total": 13000.0},
    })
    assert "Clean Invoices Ready for Filing: 14" in summary_msg
    assert "Total Eligible ITC: INR 13000.00" in summary_msg
