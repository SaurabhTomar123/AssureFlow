import pytest
from src.gst_engine.checksum import generate_valid_gstin
from src.gst_engine.rules import (
    validate_gstin_format,
    validate_tax_type,
    validate_math_totals,
    check_duplicate_bill,
)
from src.gst_engine.validator import validate_bill_compliance


def test_gstin_format_validation():
    valid, err = validate_gstin_format("07ABCDE1234F1Z5")
    assert valid is True
    assert err == ""

    invalid_state, err = validate_gstin_format("99ABCDE1234F1Z5")
    assert invalid_state is False
    assert "not a recognized Indian state" in err

    invalid_chars, err = validate_gstin_format("07abcde1234f1z5")
    valid_up, _ = validate_gstin_format("07abcde1234f1z5".upper())
    assert valid_up is True


def test_tax_type_intrastate():
    delhi_seller = generate_valid_gstin("07", "SELLA1111A")
    delhi_buyer = generate_valid_gstin("07", "BUYER2222B")

    valid, err = validate_tax_type(
        supplier_gstin=delhi_seller,
        buyer_gstin=delhi_buyer,
        cgst=90.0,
        sgst=90.0,
        igst=0.0,
    )
    assert valid is True
    assert err == ""

    invalid_igst, err = validate_tax_type(
        supplier_gstin=delhi_seller,
        buyer_gstin=delhi_buyer,
        cgst=0.0,
        sgst=0.0,
        igst=180.0,
    )
    assert invalid_igst is False
    assert "cannot have IGST" in err


def test_tax_type_interstate():
    delhi_seller = generate_valid_gstin("07", "SELLA1111A")
    mumbai_buyer = generate_valid_gstin("27", "BUYER2222B")

    valid, err = validate_tax_type(
        supplier_gstin=delhi_seller,
        buyer_gstin=mumbai_buyer,
        cgst=0.0,
        sgst=0.0,
        igst=180.0,
    )
    assert valid is True

    invalid_cgst, err = validate_tax_type(
        supplier_gstin=delhi_seller,
        buyer_gstin=mumbai_buyer,
        cgst=90.0,
        sgst=90.0,
        igst=0.0,
    )
    assert invalid_cgst is False
    assert "must charge IGST only" in err


def test_math_totals_validation():
    items = [
        {"taxable_value": 500.0},
        {"taxable_value": 500.0},
    ]
    valid, err = validate_math_totals(
        taxable_amount=1000.0,
        cgst=90.0,
        sgst=90.0,
        igst=0.0,
        total_amount=1180.0,
        items=items,
    )
    assert valid is True

    valid_tol, _ = validate_math_totals(
        taxable_amount=1000.0,
        cgst=90.0,
        sgst=90.0,
        igst=0.0,
        total_amount=1180.40,
        items=items,
    )
    assert valid_tol is True

    invalid_math, err = validate_math_totals(
        taxable_amount=1000.0,
        cgst=90.0,
        sgst=90.0,
        igst=0.0,
        total_amount=1250.0,
        items=items,
    )
    assert invalid_math is False
    assert "Tax and taxable total mismatch" in err


def test_duplicate_bill_detection():
    existing = [
        {"id": "bill-1", "supplier_gstin": "07AAAAA0000A1Z5", "bill_number": "INV-101"},
        {"id": "bill-2", "supplier_gstin": "27BBBBB0000B1Z5", "bill_number": "INV-202"},
    ]
    is_dup, dup_id = check_duplicate_bill(
        supplier_gstin="07AAAAA0000A1Z5",
        bill_number="INV-101",
        existing_bills=existing,
    )
    assert is_dup is True
    assert dup_id == "bill-1"

    is_not_dup, _ = check_duplicate_bill(
        supplier_gstin="07AAAAA0000A1Z5",
        bill_number="INV-999",
        existing_bills=existing,
    )
    assert is_not_dup is False


def test_validator_coordinator():
    buyer = generate_valid_gstin("07", "BUYER1234A")
    supplier = generate_valid_gstin("07", "SUPPL1234B")

    clean_bill = {
        "supplier_name": "Delhi Traders",
        "supplier_gstin": supplier,
        "bill_number": "INV-500",
        "bill_date": "2026-11-01",
        "taxable_amount": 1000.0,
        "cgst_amount": 90.0,
        "sgst_amount": 90.0,
        "igst_amount": 0.0,
        "total_amount": 1180.0,
        "items": [{"taxable_value": 1000.0}],
    }

    issues = validate_bill_compliance(clean_bill, buyer_gstin=buyer)
    assert len(issues) == 0

    blurry_bill = dict(clean_bill)
    blurry_bill["is_blurry"] = True
    issues = validate_bill_compliance(blurry_bill, buyer_gstin=buyer)
    assert len(issues) == 1
    assert issues[0].issue_type == "BLURRY_IMAGE"
    assert issues[0].severity == "simple"

    interstate_err_bill = dict(clean_bill)
    interstate_err_bill["supplier_gstin"] = generate_valid_gstin("27", "MUMBA1234M")
    issues = validate_bill_compliance(interstate_err_bill, buyer_gstin=buyer)
    assert any(i.issue_type == "WRONG_TAX_TYPE" and i.severity == "serious" for i in issues)

