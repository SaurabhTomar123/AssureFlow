import json
import os
import sys
from pathlib import Path
from PIL import Image, ImageFilter
import pymupdf

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from src.gst_engine.checksum import generate_valid_gstin, calculate_gstin_check_digit

BASE_DIR = Path(__file__).resolve().parent.parent
SYNTHETIC_DIR = BASE_DIR / "synthetic_data"
PDF_DIR = SYNTHETIC_DIR / "bills_pdf"
IMG_DIR = SYNTHETIC_DIR / "bills_img"

PDF_DIR.mkdir(parents=True, exist_ok=True)
IMG_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_BUYER_GSTIN = generate_valid_gstin("07", "SHARM9999K", "1")
DEFAULT_BUYER_NAME = "Sharma Kirana Store"
DEFAULT_BUYER_ADDRESS = "Shop 12, Chandni Chowk, New Delhi, Delhi - 110006"


def build_pdf_invoice(
    file_path: Path,
    supplier_name: str,
    supplier_gstin: str,
    supplier_address: str,
    buyer_name: str,
    buyer_gstin: str,
    buyer_address: str,
    invoice_number: str,
    invoice_date: str,
    items: list[dict],
    taxable_amount: float,
    cgst: float,
    sgst: float,
    igst: float,
    total_amount: float,
    multipage: bool = False,
):
    doc = SimpleDocTemplate(
        str(file_path),
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Heading1"],
        fontSize=16,
        leading=20,
        alignment=1,
        textColor=colors.HexColor("#1A365D"),
    )

    body_style = ParagraphStyle(
        "InvoiceBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
    )

    bold_body = ParagraphStyle(
        "InvoiceBold",
        parent=body_style,
        fontName="Helvetica-Bold",
    )

    story = []

    story.append(Paragraph("TAX INVOICE", title_style))
    story.append(Spacer(1, 12))

    header_data = [
        [
            Paragraph(f"<b>Supplier:</b><br/>{supplier_name}<br/>{supplier_address}<br/><b>GSTIN:</b> {supplier_gstin}", body_style),
            Paragraph(f"<b>Invoice No:</b> {invoice_number}<br/><b>Date:</b> {invoice_date}<br/><b>State Code:</b> {supplier_gstin[:2] if supplier_gstin else 'N/A'}", body_style),
        ],
        [
            Paragraph(f"<b>Billed To (Buyer):</b><br/>{buyer_name}<br/>{buyer_address}<br/><b>GSTIN:</b> {buyer_gstin}", body_style),
            Paragraph(f"<b>Place of Supply:</b> {'Delhi (07)' if buyer_gstin.startswith('07') else 'Other'}<br/><b>Reverse Charge:</b> No", body_style),
        ],
    ]

    header_table = Table(header_data, colWidths=[270, 250])
    header_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 14))

    table_data = [
        ["#", "Item Description", "HSN", "Qty", "Rate", "Taxable Value", "Tax %", "Amount"]
    ]

    for idx, it in enumerate(items, 1):
        table_data.append([
            str(idx),
            it["description"],
            it.get("hsn", "1905"),
            f"{it['qty']:.1f}",
            f"{it['rate']:.2f}",
            f"{it['taxable_value']:.2f}",
            f"{it['tax_rate']:.1f}%",
            f"{it['total']:.2f}",
        ])

    items_table = Table(table_data, colWidths=[25, 185, 45, 40, 50, 65, 45, 65])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 12))

    if multipage:
        story.append(PageBreak())
        story.append(Paragraph("TAX INVOICE (Page 2 - Summary & Declarations)", title_style))
        story.append(Spacer(1, 16))

    summary_data = [
        ["Taxable Amount:", f"INR {taxable_amount:.2f}"],
        ["CGST Amount:", f"INR {cgst:.2f}"],
        ["SGST Amount:", f"INR {sgst:.2f}"],
        ["IGST Amount:", f"INR {igst:.2f}"],
        ["Total Invoice Value:", f"INR {total_amount:.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[150, 120])
    summary_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -2), "Helvetica"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEBELOW", (0, -1), (-1, -1), 1, colors.HexColor("#1A365D")),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#1A365D")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F8FAFC")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    wrapper = Table([["", summary_table]], colWidths=[250, 270])
    wrapper.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(wrapper)

    story.append(Spacer(1, 20))
    terms = (
        "Declaration: We declare that this invoice shows the actual price of the goods "
        "described and that all particulars are true and correct."
    )
    story.append(Paragraph(terms, body_style))

    doc.build(story)


def convert_pdf_to_image(pdf_path: Path, output_path: Path, blur: bool = False):
    pdf = pymupdf.open(str(pdf_path))
    page = pdf[0]
    pix = page.get_pixmap(dpi=150)
    img_data = pix.tobytes("png")
    pdf.close()

    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(radius=6.0))
    image.save(str(output_path), "PNG")


def generate_all_bills():
    specs = [
        {
            "id": "BILL-001",
            "filename": "bill_01_clean_kirana_5pct.pdf",
            "supplier_name": "Modern Agro Staples Ltd",
            "supplier_state": "07",
            "supplier_pan": "MODER1111A",
            "invoice_number": "MAS-2026-101",
            "invoice_date": "2026-11-01",
            "items": [
                {"description": "Aashirvaad Atta 10kg", "hsn": "1101", "qty": 10, "rate": 380.0, "taxable_value": 3800.0, "tax_rate": 5.0, "total": 3990.0},
                {"description": "Fortune Basmati Rice 5kg", "hsn": "1006", "qty": 8, "rate": 450.0, "taxable_value": 3600.0, "tax_rate": 5.0, "total": 3780.0},
            ],
            "taxable_amount": 7400.0,
            "cgst": 185.0,
            "sgst": 185.0,
            "igst": 0.0,
            "total_amount": 7770.0,
            "expected_status": "clean",
            "expected_issues": [],
        },
        {
            "id": "BILL-002",
            "filename": "bill_02_clean_spices_12pct.pdf",
            "supplier_name": "Royal Spices & Condiments",
            "supplier_state": "07",
            "supplier_pan": "ROYAL2222B",
            "invoice_number": "RSC-2026-202",
            "invoice_date": "2026-11-02",
            "items": [
                {"description": "MDH Deggi Mirch 500g", "hsn": "0904", "qty": 20, "rate": 180.0, "taxable_value": 3600.0, "tax_rate": 12.0, "total": 4032.0},
                {"description": "Everest Garam Masala 200g", "hsn": "0910", "qty": 25, "rate": 96.0, "taxable_value": 2400.0, "tax_rate": 12.0, "total": 2688.0},
            ],
            "taxable_amount": 6000.0,
            "cgst": 360.0,
            "sgst": 360.0,
            "igst": 0.0,
            "total_amount": 6720.0,
            "expected_status": "clean",
            "expected_issues": [],
        },
        {
            "id": "BILL-003",
            "filename": "bill_03_clean_electronics_18pct.pdf",
            "supplier_name": "Apex Electronic Hub",
            "supplier_state": "07",
            "supplier_pan": "APELE3333C",
            "invoice_number": "AEH-2026-303",
            "invoice_date": "2026-11-02",
            "items": [
                {"description": "Syska LED Bulb 12W Pack", "hsn": "8539", "qty": 40, "rate": 120.0, "taxable_value": 4800.0, "tax_rate": 18.0, "total": 5664.0},
                {"description": "Anchor Extension Cord 4-Way", "hsn": "8536", "qty": 10, "rate": 320.0, "taxable_value": 3200.0, "tax_rate": 18.0, "total": 3776.0},
            ],
            "taxable_amount": 8000.0,
            "cgst": 720.0,
            "sgst": 720.0,
            "igst": 0.0,
            "total_amount": 9440.0,
            "expected_status": "clean",
            "expected_issues": [],
        },
        {
            "id": "BILL-004",
            "filename": "bill_04_clean_beverages_28pct.pdf",
            "supplier_name": "Delhi Cold Beverages Dist",
            "supplier_state": "07",
            "supplier_pan": "DELBE4444D",
            "invoice_number": "DCB-2026-404",
            "invoice_date": "2026-11-03",
            "items": [
                {"description": "Aerated Soft Drinks 2L Crates", "hsn": "2202", "qty": 15, "rate": 600.0, "taxable_value": 9000.0, "tax_rate": 28.0, "total": 11520.0},
            ],
            "taxable_amount": 9000.0,
            "cgst": 1260.0,
            "sgst": 1260.0,
            "igst": 0.0,
            "total_amount": 11520.0,
            "expected_status": "clean",
            "expected_issues": [],
        },
        {
            "id": "BILL-005",
            "filename": "bill_05_clean_interstate_18pct.pdf",
            "supplier_name": "Maharashtra Goods Syndicate",
            "supplier_state": "27",
            "supplier_pan": "MAHGS5555E",
            "invoice_number": "MGS-2026-505",
            "invoice_date": "2026-11-03",
            "items": [
                {"description": "Commercial Kitchen Blender", "hsn": "8509", "qty": 2, "rate": 4500.0, "taxable_value": 9000.0, "tax_rate": 18.0, "total": 10620.0},
            ],
            "taxable_amount": 9000.0,
            "cgst": 0.0,
            "sgst": 0.0,
            "igst": 1620.0,
            "total_amount": 10620.0,
            "expected_status": "clean",
            "expected_issues": [],
        },
        {
            "id": "BILL-006",
            "filename": "bill_06_clean_hardware_18pct.pdf",
            "supplier_name": "Metro Hardware Depot",
            "supplier_state": "07",
            "supplier_pan": "METHW6666F",
            "invoice_number": "MHD-2026-606",
            "invoice_date": "2026-11-03",
            "items": [
                {"description": "Heavy Duty Padlocks 65mm", "hsn": "8301", "qty": 12, "rate": 250.0, "taxable_value": 3000.0, "tax_rate": 18.0, "total": 3540.0},
            ],
            "taxable_amount": 3000.0,
            "cgst": 270.0,
            "sgst": 270.0,
            "igst": 0.0,
            "total_amount": 3540.0,
            "expected_status": "clean",
            "expected_issues": [],
        },
        {
            "id": "BILL-007",
            "filename": "bill_07_clean_packaging_12pct.pdf",
            "supplier_name": "Craft Corrugated Boxes Ltd",
            "supplier_state": "07",
            "supplier_pan": "CRAFT7777G",
            "invoice_number": "CCB-2026-707",
            "invoice_date": "2026-11-04",
            "items": [
                {"description": "Shipping Cartons 12x10x8", "hsn": "4819", "qty": 100, "rate": 25.0, "taxable_value": 2500.0, "tax_rate": 12.0, "total": 2800.0},
            ],
            "taxable_amount": 2500.0,
            "cgst": 150.0,
            "sgst": 150.0,
            "igst": 0.0,
            "total_amount": 2800.0,
            "expected_status": "clean",
            "expected_issues": [],
        },
        {
            "id": "BILL-008",
            "filename": "bill_08_clean_stationery_12pct.pdf",
            "supplier_name": "National Office Supplies",
            "supplier_state": "07",
            "supplier_pan": "NATOF8888H",
            "invoice_number": "NOS-2026-808",
            "invoice_date": "2026-11-04",
            "items": [
                {"description": "A4 Copier Paper 75GSM Ream", "hsn": "4802", "qty": 10, "rate": 280.0, "taxable_value": 2800.0, "tax_rate": 12.0, "total": 3136.0},
            ],
            "taxable_amount": 2800.0,
            "cgst": 168.0,
            "sgst": 168.0,
            "igst": 0.0,
            "total_amount": 3136.0,
            "expected_status": "clean",
            "expected_issues": [],
        },
        {
            "id": "BILL-009",
            "filename": "bill_09_clean_dairy_5pct.pdf",
            "supplier_name": "Verma Dairy Products",
            "supplier_state": "07",
            "supplier_pan": "VERMA9999I",
            "invoice_number": "VDP-2026-909",
            "invoice_date": "2026-11-04",
            "items": [
                {"description": "Pure Ghee 1L Tins", "hsn": "0405", "qty": 10, "rate": 550.0, "taxable_value": 5500.0, "tax_rate": 5.0, "total": 5775.0},
            ],
            "taxable_amount": 5500.0,
            "cgst": 137.50,
            "sgst": 137.50,
            "igst": 0.0,
            "total_amount": 5775.0,
            "expected_status": "clean",
            "expected_issues": [],
        },
        {
            "id": "BILL-010",
            "filename": "bill_10_clean_medicines_12pct.pdf",
            "supplier_name": "Careway Pharma Agency",
            "supplier_state": "07",
            "supplier_pan": "CAREP1010J",
            "invoice_number": "CPA-2026-010",
            "invoice_date": "2026-11-04",
            "items": [
                {"description": "Multivitamin Syrups 200ml", "hsn": "3004", "qty": 50, "rate": 90.0, "taxable_value": 4500.0, "tax_rate": 12.0, "total": 5040.0},
            ],
            "taxable_amount": 4500.0,
            "cgst": 270.0,
            "sgst": 270.0,
            "igst": 0.0,
            "total_amount": 5040.0,
            "expected_status": "clean",
            "expected_issues": [],
        },
        {
            "id": "BILL-011",
            "filename": "bill_11_invalid_gstin_checksum.pdf",
            "supplier_name": "Shady Wholesalers Co",
            "supplier_state": "07",
            "supplier_pan": "SHADY1111K",
            "corrupt_checksum": True,
            "invoice_number": "SWC-2026-111",
            "invoice_date": "2026-11-04",
            "items": [
                {"description": "Commercial Kitchen Towels", "hsn": "6307", "qty": 20, "rate": 150.0, "taxable_value": 3000.0, "tax_rate": 12.0, "total": 3360.0},
            ],
            "taxable_amount": 3000.0,
            "cgst": 180.0,
            "sgst": 180.0,
            "igst": 0.0,
            "total_amount": 3360.0,
            "expected_status": "flagged_issue",
            "expected_issues": ["INVALID_GSTIN_CHECKSUM"],
        },
        {
            "id": "BILL-012",
            "filename": "bill_12_missing_gstin.pdf",
            "supplier_name": "Local Cash Vendor",
            "omit_gstin": True,
            "invoice_number": "LCV-2026-112",
            "invoice_date": "2026-11-04",
            "items": [
                {"description": "Handmade Packaging Bags", "hsn": "4202", "qty": 50, "rate": 40.0, "taxable_value": 2000.0, "tax_rate": 18.0, "total": 2360.0},
            ],
            "taxable_amount": 2000.0,
            "cgst": 180.0,
            "sgst": 180.0,
            "igst": 0.0,
            "total_amount": 2360.0,
            "expected_status": "flagged_issue",
            "expected_issues": ["MISSING_MANDATORY_FIELD"],
        },
        {
            "id": "BILL-013",
            "filename": "bill_13_wrong_tax_type_interstate_charged_cgst.pdf",
            "supplier_name": "Gujarat Ceramic Tiles",
            "supplier_state": "24",
            "supplier_pan": "GUJCT1313L",
            "invoice_number": "GCT-2026-113",
            "invoice_date": "2026-11-04",
            "items": [
                {"description": "Vitrified Floor Tiles Box", "hsn": "6907", "qty": 20, "rate": 400.0, "taxable_value": 8000.0, "tax_rate": 18.0, "total": 9440.0},
            ],
            "taxable_amount": 8000.0,
            "cgst": 720.0,
            "sgst": 720.0,
            "igst": 0.0,
            "total_amount": 9440.0,
            "expected_status": "flagged_issue",
            "expected_issues": ["WRONG_TAX_TYPE"],
        },
        {
            "id": "BILL-014",
            "filename": "bill_14_math_mismatch_wrong_total.pdf",
            "supplier_name": "Delhi Electrical Accessories",
            "supplier_state": "07",
            "supplier_pan": "DELEA1414M",
            "invoice_number": "DEA-2026-114",
            "invoice_date": "2026-11-04",
            "items": [
                {"description": "Copper Wires 2.5sqmm Coil", "hsn": "8544", "qty": 4, "rate": 1250.0, "taxable_value": 5000.0, "tax_rate": 18.0, "total": 5900.0},
            ],
            "taxable_amount": 5000.0,
            "cgst": 450.0,
            "sgst": 450.0,
            "igst": 0.0,
            "total_amount": 6800.0,
            "expected_status": "flagged_issue",
            "expected_issues": ["TAX_CALCULATION_MISMATCH"],
        },
        {
            "id": "BILL-015",
            "filename": "bill_15_duplicate_original.pdf",
            "supplier_name": "Gupta Packaging Works",
            "supplier_state": "07",
            "supplier_pan": "GUPTA1515N",
            "invoice_number": "GPW-2026-999",
            "invoice_date": "2026-11-04",
            "items": [
                {"description": "Bubble Wrap Roll 100m", "hsn": "3923", "qty": 5, "rate": 600.0, "taxable_value": 3000.0, "tax_rate": 18.0, "total": 3540.0},
            ],
            "taxable_amount": 3000.0,
            "cgst": 270.0,
            "sgst": 270.0,
            "igst": 0.0,
            "total_amount": 3540.0,
            "expected_status": "clean",
            "expected_issues": [],
        },
        {
            "id": "BILL-016",
            "filename": "bill_16_duplicate_copy.pdf",
            "supplier_name": "Gupta Packaging Works",
            "supplier_state": "07",
            "supplier_pan": "GUPTA1515N",
            "invoice_number": "GPW-2026-999",
            "invoice_date": "2026-11-04",
            "items": [
                {"description": "Bubble Wrap Roll 100m", "hsn": "3923", "qty": 5, "rate": 600.0, "taxable_value": 3000.0, "tax_rate": 18.0, "total": 3540.0},
            ],
            "taxable_amount": 3000.0,
            "cgst": 270.0,
            "sgst": 270.0,
            "igst": 0.0,
            "total_amount": 3540.0,
            "expected_status": "flagged_issue",
            "expected_issues": ["DUPLICATE_INVOICE"],
        },
        {
            "id": "BILL-017",
            "filename": "bill_17_multipage_clean.pdf",
            "supplier_name": "Mega Wholesale Depot",
            "supplier_state": "07",
            "supplier_pan": "MEGAW1717O",
            "invoice_number": "MWD-2026-117",
            "invoice_date": "2026-11-05",
            "multipage": True,
            "items": [
                {"description": "Refined Sunflower Oil 15L Tin", "hsn": "1512", "qty": 5, "rate": 1800.0, "taxable_value": 9000.0, "tax_rate": 5.0, "total": 9450.0},
                {"description": "Premium Basmati Rice 25kg Bag", "hsn": "1006", "qty": 4, "rate": 2200.0, "taxable_value": 8800.0, "tax_rate": 5.0, "total": 9240.0},
                {"description": "Tata Salt 1kg Pack Carton", "hsn": "2501", "qty": 10, "rate": 450.0, "taxable_value": 4500.0, "tax_rate": 5.0, "total": 4725.0},
            ],
            "taxable_amount": 22300.0,
            "cgst": 557.50,
            "sgst": 557.50,
            "igst": 0.0,
            "total_amount": 23415.0,
            "expected_status": "clean",
            "expected_issues": [],
        },
        {
            "id": "BILL-018",
            "filename": "bill_18_blurry_receipt.png",
            "is_image_only": True,
            "supplier_name": "Sharma Tea Stall Supplies",
            "supplier_state": "07",
            "supplier_pan": "SHARM1818P",
            "invoice_number": "STS-2026-118",
            "invoice_date": "2026-11-05",
            "items": [
                {"description": "Wagh Bakri Tea Leaves 1kg", "hsn": "0902", "qty": 4, "rate": 450.0, "taxable_value": 1800.0, "tax_rate": 5.0, "total": 1890.0},
            ],
            "taxable_amount": 1800.0,
            "cgst": 45.0,
            "sgst": 45.0,
            "igst": 0.0,
            "total_amount": 1890.0,
            "expected_status": "flagged_issue",
            "expected_issues": ["BLURRY_IMAGE"],
        },
    ]

    ground_truth = []

    for spec in specs:
        if spec.get("omit_gstin"):
            supplier_gstin = ""
        else:
            state = spec.get("supplier_state", "07")
            pan = spec.get("supplier_pan", "AAAAA0000A")
            base = f"{state}{pan}1Z"
            valid_check = calculate_gstin_check_digit(base)
            if spec.get("corrupt_checksum"):
                corrupt_digit = "0" if valid_check != "0" else "1"
                supplier_gstin = f"{base}{corrupt_digit}"
            else:
                supplier_gstin = f"{base}{valid_check}"

        spec_record = dict(spec)
        spec_record["supplier_gstin"] = supplier_gstin
        spec_record["buyer_gstin"] = DEFAULT_BUYER_GSTIN
        spec_record["buyer_name"] = DEFAULT_BUYER_NAME

        pdf_path = PDF_DIR / spec["filename"].replace(".png", ".pdf")
        img_path = IMG_DIR / spec["filename"].replace(".pdf", ".png")

        build_pdf_invoice(
            file_path=pdf_path,
            supplier_name=spec["supplier_name"],
            supplier_gstin=supplier_gstin,
            supplier_address=f"Industrial Area, State Code: {supplier_gstin[:2] if supplier_gstin else '07'}",
            buyer_name=DEFAULT_BUYER_NAME,
            buyer_gstin=DEFAULT_BUYER_GSTIN,
            buyer_address=DEFAULT_BUYER_ADDRESS,
            invoice_number=spec["invoice_number"],
            invoice_date=spec["invoice_date"],
            items=spec["items"],
            taxable_amount=spec["taxable_amount"],
            cgst=spec["cgst"],
            sgst=spec["sgst"],
            igst=spec["igst"],
            total_amount=spec["total_amount"],
            multipage=spec.get("multipage", False),
        )

        is_blur = spec.get("is_image_only", False) and "blurry" in spec["filename"]
        convert_pdf_to_image(pdf_path, img_path, blur=is_blur)

        spec_record["pdf_path"] = str(pdf_path.relative_to(BASE_DIR))
        spec_record["img_path"] = str(img_path.relative_to(BASE_DIR))
        ground_truth.append(spec_record)

    gt_file = SYNTHETIC_DIR / "ground_truth.json"
    with open(gt_file, "w", encoding="utf-8") as f:
        json.dump(ground_truth, f, indent=2)

    print(f"Generated {len(ground_truth)} synthetic bills in {SYNTHETIC_DIR}")


if __name__ == "__main__":
    generate_all_bills()
