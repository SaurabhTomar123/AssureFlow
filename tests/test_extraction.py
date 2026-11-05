from pathlib import Path
from src.extraction.pdf_extractor import extract_text_from_pdf
from src.extraction.parser import extract_bill_data

BASE_DIR = Path(__file__).resolve().parent.parent
PDF_DIR = BASE_DIR / "synthetic_data" / "bills_pdf"
IMG_DIR = BASE_DIR / "synthetic_data" / "bills_img"


def test_pdf_text_extraction():
    pdf_path = PDF_DIR / "bill_01_clean_kirana_5pct.pdf"
    text = extract_text_from_pdf(str(pdf_path))
    assert "TAX INVOICE" in text
    assert "Modern Agro Staples Ltd" in text
    assert "MAS-2026-101" in text


def test_bill_data_extraction_clean():
    pdf_path = PDF_DIR / "bill_01_clean_kirana_5pct.pdf"
    data = extract_bill_data(str(pdf_path))

    assert "Modern Agro Staples" in data["supplier_name"]
    assert data["bill_number"] == "MAS-2026-101"
    assert data["bill_date"] == "2026-11-01"
    assert data["taxable_amount"] == 7400.0
    assert data["cgst_amount"] == 185.0
    assert data["sgst_amount"] == 185.0
    assert data["total_amount"] == 7770.0
    assert data["is_blurry"] is False


def test_multipage_pdf_extraction():
    pdf_path = PDF_DIR / "bill_17_multipage_clean.pdf"
    data = extract_bill_data(str(pdf_path))

    assert data["bill_number"] == "MWD-2026-117"
    assert data["taxable_amount"] == 22300.0
    assert data["total_amount"] == 23415.0


def test_blurry_image_extraction():
    img_path = IMG_DIR / "bill_18_blurry_receipt.png"
    data = extract_bill_data(str(img_path))
    assert data["is_blurry"] is True
