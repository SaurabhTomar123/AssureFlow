"""Generate the 20 synthetic fixtures (100% synthetic identities), their recorded extractions for the
fake provider (keyed by SHA-256) and the expected rule outcomes, recorded before tests run.

Run: python -m seed.make_fixtures
Output is deterministic (reportlab invariant mode), so SHA-256 keys are stable.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from reportlab import rl_config

rl_config.invariant = 1

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import getSampleStyleSheet  # noqa: E402
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402

from rules.gstin import make_gstin  # noqa: E402

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
EXTRACTION = ROOT / "expected" / "extraction"
P = Decimal("0.01")

SHARMA = make_gstin("07", "SHARM9999K")
GUPTA = make_gstin("27", "GUPTA8888L")
SUPPLIERS = {
    "agro": ("Modern Agro Staples Pvt Ltd", make_gstin("07", "MODER1111A")),
    "spice": ("Royal Spices and Condiments", make_gstin("07", "ROYAL2222B")),
    "elec": ("Pune Electricals LLP", make_gstin("27", "PUNEE3333C")),
    "pack": ("Delhi Packaging Co", make_gstin("07", "DELHI4444D")),
    "dairy": ("Shree Dairy Foods", make_gstin("07", "SHREE5555E")),
    "mumbai": ("Mumbai Hardware Mart", make_gstin("27", "MUMBA6666F")),
    "noida": ("Noida Stationers", make_gstin("09", "NOIDA7777G")),
}


def q(value: Decimal) -> Decimal:
    return value.quantize(P, rounding=ROUND_HALF_UP)


@dataclass
class Line:
    desc: str
    hsn: str | None
    qty: Decimal
    price: Decimal
    cgst: Decimal | None = None
    sgst: Decimal | None = None
    igst: Decimal | None = None

    @property
    def taxable(self) -> Decimal:
        return q(self.qty * self.price)

    def amount(self, comp: str) -> Decimal | None:
        rate = getattr(self, comp)
        return None if rate is None else q(self.taxable * rate / 100)


@dataclass
class Fixture:
    name: str
    shop: str
    supplier: str
    number: str
    date: str
    pos: str
    lines: list[Line]
    kind: str = "pdf"  # pdf | scan | png | blurry
    title: str = "TAX INVOICE"
    recipient: str | None = None
    supplier_gstin: str | None = "default"
    per_line: bool = True
    combined_only: bool = False
    round_off: Decimal = Decimal("0.00")
    total_override: Decimal | None = None
    pages: int = 1
    misread: dict[str, Any] = field(default_factory=dict)
    expected: dict[str, str] = field(default_factory=dict)
    note: str = ""

    @property
    def gstin(self) -> str | None:
        return SUPPLIERS[self.supplier][1] if self.supplier_gstin == "default" else self.supplier_gstin

    @property
    def buyer(self) -> str:
        return self.recipient or (SHARMA if self.shop == "sharma" else GUPTA)

    def totals(self) -> dict[str, Decimal]:
        taxable = sum((ln.taxable for ln in self.lines), Decimal(0))
        comps: dict[str, Decimal] = {}
        for comp in ("cgst", "sgst", "igst"):
            if self.per_line:
                comps[comp] = sum((ln.amount(comp) or Decimal(0) for ln in self.lines), Decimal(0))
            else:
                groups: dict[tuple[Any, ...], Decimal] = {}
                for ln in self.lines:
                    key = (ln.cgst, ln.sgst, ln.igst)
                    groups[key] = groups.get(key, Decimal(0)) + ln.taxable
                comps[comp] = sum(
                    (
                        q(base * (dict(zip(("cgst", "sgst", "igst"), key, strict=True))[comp] or 0) / 100)
                        for key, base in groups.items()
                    ),
                    Decimal(0),
                )
        total = taxable + comps["cgst"] + comps["sgst"] + comps["igst"] + self.round_off
        return {"taxable": taxable, **comps, "total": self.total_override or total}


def L(
    desc: str, hsn: str | None, qty: str, price: str, *, cs: str | None = None, ig: str | None = None
) -> Line:
    half = Decimal(cs) if cs else None
    return Line(desc, hsn, Decimal(qty), Decimal(price), half, half, Decimal(ig) if ig else None)


FIXTURE_LIST: list[Fixture] = [
    Fixture(
        "F01_clean_intrastate_5pct",
        "sharma",
        "agro",
        "MAS-2026-101",
        "2026-11-01",
        "07",
        [
            L("Wheat atta 10kg", "1101", "10", "380.00", cs="2.5"),
            L("Basmati rice 5kg", "1006", "8", "450.00", cs="2.5"),
        ],
        note="clean, text PDF",
    ),
    Fixture(
        "F02_clean_scan_12pct",
        "sharma",
        "spice",
        "RSC-2026-202",
        "2026-11-02",
        "07",
        [
            L("Red chilli powder 500g", "0904", "20", "145.00", cs="6"),
            L("Turmeric 500g", "0910", "15", "98.50", cs="6"),
        ],
        kind="scan",
        note="scanned PDF with a small digital header: vision fallback",
    ),
    Fixture(
        "F03_clean_mixed_rates",
        "sharma",
        "pack",
        "DPC-778",
        "2026-11-03",
        "07",
        [
            L("Carton boxes", "4819", "100", "12.40", cs="6"),
            L("Packing tape", "3919", "40", "35.00", cs="9"),
            L("Paper bags", "4819", "200", "3.15", cs="6"),
        ],
        per_line=False,
        note="tax printed per rate group",
    ),
    Fixture(
        "F04_clean_interstate_18pct",
        "sharma",
        "elec",
        "PEL/26/0457",
        "2026-11-04",
        "07",
        [
            L("LED bulb 9W", "8539", "50", "89.00", ig="18"),
            L("Extension board", "8536", "10", "315.00", ig="18"),
        ],
        note="interstate, IGST only",
    ),
    Fixture(
        "F05_clean_round_off",
        "sharma",
        "dairy",
        "SDF-5511",
        "2026-11-05",
        "07",
        [L("Ghee 1L", "0405", "6", "612.35", cs="6"), L("Paneer 1kg", "0406", "4", "355.20", cs="2.5")],
        round_off=Decimal("0.35"),
        note="explicit round-off",
    ),
    Fixture(
        "F06_invalid_gstin",
        "sharma",
        "agro",
        "MAS-2026-130",
        "2026-11-06",
        "07",
        [L("Sugar 5kg", "1701", "12", "230.00", cs="2.5")],
        supplier_gstin="07MODER1111A1Z9",
        expected={"R-GSTIN-01": "fail"},
        note="check character wrong",
    ),
    Fixture(
        "F07_missing_gstin",
        "sharma",
        "spice",
        "RSC-2026-219",
        "2026-11-07",
        "07",
        [L("Cumin 250g", "0909", "30", "88.00", cs="2.5")],
        supplier_gstin=None,
        expected={"R-GSTIN-01": "needs_evidence", "R-TAX-01": "needs_evidence"},
        note="supplier GSTIN not printed",
    ),
    Fixture(
        "F08_wrong_tax_type",
        "sharma",
        "elec",
        "PEL/26/0461",
        "2026-11-08",
        "07",
        [L("Ceiling fan", "8414", "4", "1850.00", cs="9")],
        expected={"R-TAX-01": "fail"},
        note="interstate supply charged CGST+SGST",
    ),
    Fixture(
        "F09_total_mismatch",
        "sharma",
        "pack",
        "DPC-781",
        "2026-11-09",
        "07",
        [L("Plastic crates", "3923", "10", "240.00", cs="9")],
        total_override=Decimal("2932.00"),
        expected={"R-AMT-03": "fail"},
        note="printed total wrong by 100",
    ),
    Fixture(
        "F10_duplicate_original",
        "sharma",
        "dairy",
        "SDF-5520",
        "2026-11-10",
        "07",
        [L("Butter 500g", "0405", "20", "265.00", cs="6")],
        note="clean original",
    ),
    Fixture(
        "F11_duplicate_copy",
        "sharma",
        "dairy",
        "SDF/5520",
        "2026-11-10",
        "07",
        [L("Butter 500g", "0405", "20", "265.00", cs="6")],
        title="TAX INVOICE (COPY)",
        expected={"R-DUP-01": "fail", "R-DUP-02": "fail"},
        note="same invoice number, different file",
    ),
    Fixture(
        "F12_multipage",
        "sharma",
        "agro",
        "MAS-2026-150",
        "2026-11-12",
        "07",
        [L(f"Pulses lot {i}", "0713", "5", f"{100 + i * 7}.00", cs="2.5") for i in range(1, 13)],
        pages=2,
        note="two pages",
    ),
    Fixture(
        "F13_blurry_photo",
        "sharma",
        "agro",
        "A108",
        "2026-11-13",
        "07",
        [L("Mustard oil 1L", "1514", "8", "125.00", cs="9")],
        kind="blurry",
        misread={"invoice_total": ("1780.00", 0.55)},
        note="blurry photo; total misread 1780 vs printed 1180, owner corrects",
    ),
    Fixture(
        "F14_combined_rate_only",
        "sharma",
        "spice",
        "RSC-2026-240",
        "2026-11-14",
        "07",
        [L("Garam masala", "0910", "25", "64.00", cs="2.5")],
        combined_only=True,
        expected={"R-AMT-02": "needs_evidence", "R-AMT-03": "fail"},
        note="only GST 5% printed; component split not inferred",
    ),
    Fixture(
        "F15_credit_note",
        "sharma",
        "agro",
        "MAS-CN-12",
        "2026-11-15",
        "07",
        [L("Return: wheat atta 10kg", "1101", "1", "380.00", cs="2.5")],
        title="CREDIT NOTE",
        expected={"R-DOC-01": "unsupported"},
        note="credit note held",
    ),
    Fixture(
        "F16_replacement_for_F08",
        "sharma",
        "elec",
        "PEL/26/0461",
        "2026-11-08",
        "07",
        [L("Ceiling fan", "8414", "4", "1850.00", ig="18")],
        title="TAX INVOICE (REVISED)",
        note="supplier's corrected invoice, IGST",
    ),
    Fixture(
        "F17_wrong_recipient",
        "sharma",
        "pack",
        "DPC-790",
        "2026-11-17",
        "07",
        [L("Shrink wrap", "3920", "5", "410.00", cs="9")],
        recipient=make_gstin("07", "OTHER1234Z"),
        expected={"R-GSTIN-02": "fail"},
        note="billed to another business",
    ),
    Fixture(
        "F18_gupta_photo_clean",
        "gupta",
        "mumbai",
        "MHM-2211",
        "2026-11-03",
        "27",
        [
            L("Hammer drill", "8467", "2", "3250.00", cs="9"),
            L("Drill bits set", "8207", "5", "420.00", cs="9"),
        ],
        kind="png",
        note="clear phone photo",
    ),
    Fixture(
        "F19_gupta_interstate",
        "gupta",
        "noida",
        "NS-9087",
        "2026-11-04",
        "27",
        [L("A4 paper ream", "4802", "40", "245.00", ig="12")],
        note="interstate to Maharashtra",
    ),
    Fixture(
        "F20_gupta_missing_hsn",
        "gupta",
        "mumbai",
        "MHM-2240",
        "2026-11-06",
        "27",
        [L("Assorted fasteners", None, "1", "1500.00", cs="9")],
        expected={"R-PART-01": "fail"},
        note="HSN not printed (resolvable by CA)",
    ),
]


def _pdf(fx: Fixture) -> bytes:
    styles = getSampleStyleSheet()
    body = styles["Normal"]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=30,
        rightMargin=30,
        topMargin=30,
        bottomMargin=30,
        title=fx.number,
        author="synthetic",
        creator="assure-flow fixtures",
    )
    name, _ = SUPPLIERS[fx.supplier]
    t = fx.totals()
    story: list[Any] = [Paragraph(f"<b>{fx.title}</b>", styles["Title"]), Spacer(1, 6)]
    head = [
        [
            Paragraph(f"<b>Supplier:</b> {name}<br/><b>GSTIN:</b> {fx.gstin or ''}", body),
            Paragraph(f"<b>Invoice No:</b> {fx.number}<br/><b>Date:</b> {fx.date}", body),
        ],
        [
            Paragraph(f"<b>Billed to GSTIN:</b> {fx.buyer}", body),
            Paragraph(f"<b>Place of Supply:</b> {fx.pos}", body),
        ],
    ]
    ht = Table(head, colWidths=[270, 255])
    ht.setStyle(
        TableStyle(
            [("BOX", (0, 0), (-1, -1), 0.8, colors.grey), ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.grey)]
        )
    )
    story += [ht, Spacer(1, 10)]
    if fx.combined_only:
        cols = ["#", "Description", "HSN", "Qty", "Rate", "Taxable", "GST %"]
    elif fx.per_line:
        cols = [
            "#",
            "Description",
            "HSN",
            "Qty",
            "Rate",
            "Taxable",
            "CGST%",
            "CGST",
            "SGST%",
            "SGST",
            "IGST%",
            "IGST",
        ]
    else:
        cols = ["#", "Description", "HSN", "Qty", "Rate", "Taxable", "CGST%", "SGST%", "IGST%"]
    rows: list[list[str]] = [cols]
    per_page = 8
    for i, ln in enumerate(fx.lines, 1):
        base = [str(i), ln.desc, ln.hsn or "", f"{ln.qty}", f"{ln.price}", f"{ln.taxable}"]
        if fx.combined_only:
            base.append(f"{(ln.cgst or 0) * 2 + (ln.igst or 0)}")
        elif fx.per_line:
            for comp in ("cgst", "sgst", "igst"):
                rate = getattr(ln, comp)
                base += [
                    f"{rate}" if rate is not None else "",
                    f"{ln.amount(comp)}" if rate is not None else "",
                ]
        else:
            base += [
                f"{getattr(ln, c)}" if getattr(ln, c) is not None else "" for c in ("cgst", "sgst", "igst")
            ]
        rows.append(base)
    chunks = [rows[0:1] + rows[1 + k : 1 + k + per_page] for k in range(0, len(rows) - 1, per_page)]
    for idx, chunk in enumerate(chunks):
        table = Table(chunk, repeatRows=1)
        table.setStyle(
            TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7), ("GRID", (0, 0), (-1, -1), 0.3, colors.grey)])
        )
        story.append(table)
        if idx < len(chunks) - 1:
            story.append(PageBreak())
    totals = [["Taxable value", f"{t['taxable']}"]]
    if fx.combined_only:
        totals.append(["GST", f"{t['cgst'] + t['sgst'] + t['igst']}"])
    else:
        totals += [["CGST", f"{t['cgst']}"], ["SGST", f"{t['sgst']}"], ["IGST", f"{t['igst']}"]]
    if fx.round_off:
        totals.append(["Round off", f"{fx.round_off}"])
    totals.append(["GRAND TOTAL (INR)", f"{t['total']}"])
    tt = Table(totals, colWidths=[150, 100], hAlign="RIGHT")
    tt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
    story += [
        Spacer(1, 10),
        tt,
        Spacer(1, 8),
        Paragraph("Synthetic document for testing. Not a real invoice.", body),
    ]
    doc.build(story)
    return buf.getvalue()


def _raster(pdf_bytes: bytes, blur: float = 0.0) -> bytes:
    import pymupdf
    from PIL import Image, ImageFilter

    page = pymupdf.open(stream=pdf_bytes, filetype="pdf")[0]
    img = Image.open(io.BytesIO(page.get_pixmap(dpi=110).tobytes("png"))).convert("RGB")
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _scan_pdf(pdf_bytes: bytes) -> bytes:
    import pymupdf

    png = _raster(pdf_bytes)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=png)
    page.insert_text((30, 20), "Scanned with ShopCam", fontsize=7)
    return doc.tobytes(garbage=3, deflate=True, no_new_id=True)


def _fv(value: Any, page: int = 1, conf: float = 0.97, excerpt: str | None = None) -> dict[str, Any]:
    text = None if value is None else str(value)
    return {
        "value": text,
        "page": page if text is not None else None,
        "excerpt": excerpt if excerpt is not None else text,
        "confidence": conf if text is not None else 0.2,
    }


def extraction(fx: Fixture) -> dict[str, Any]:
    t = fx.totals()
    name, _ = SUPPLIERS[fx.supplier]
    last = fx.pages
    doc_type = "credit_note" if "CREDIT" in fx.title else "tax_invoice"
    data = {
        "document_type": _fv(doc_type, excerpt=fx.title),
        "supplier_name": _fv(name),
        "supplier_gstin": _fv(fx.gstin),
        "recipient_gstin": _fv(fx.buyer),
        "invoice_number": _fv(fx.number),
        "invoice_date": _fv(fx.date),
        "place_of_supply": _fv(fx.pos),
        "currency": _fv("INR", page=last),
        "taxable_total": _fv(t["taxable"], page=last),
        "cgst_total": _fv(None if fx.combined_only else t["cgst"], page=last),
        "sgst_total": _fv(None if fx.combined_only else t["sgst"], page=last),
        "igst_total": _fv(None if fx.combined_only else t["igst"], page=last),
        "cess_total": _fv(None),
        "round_off": _fv(fx.round_off if fx.round_off else None, page=last),
        "invoice_total": _fv(t["total"], page=last),
        "tax_printed_per_line": fx.per_line and not fx.combined_only,
        "multiple_invoices": False,
        "lines": [],
    }
    for i, ln in enumerate(fx.lines, 1):
        page = 1 + (i - 1) // 8
        line: dict[str, Any] = {
            "line_no": i,
            "description": _fv(ln.desc, page),
            "hsn_sac": _fv(ln.hsn, page),
            "qty": _fv(ln.qty, page),
            "unit_price": _fv(ln.price, page),
            "discount": _fv(None),
            "taxable_value": _fv(ln.taxable, page),
            "combined_rate": _fv((ln.cgst or 0) * 2 + (ln.igst or 0) if fx.combined_only else None, page),
        }
        for comp in ("cgst", "sgst", "igst"):
            rate = None if fx.combined_only else getattr(ln, comp)
            line[f"{comp}_rate"] = _fv(rate, page)
            line[f"{comp}_amount"] = _fv(ln.amount(comp) if rate is not None and fx.per_line else None, page)
        data["lines"].append(line)
    for key, (value, conf) in fx.misread.items():
        data[key] = _fv(value, last, conf)
    return data


def build() -> dict[str, Any]:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    EXTRACTION.mkdir(parents=True, exist_ok=True)
    index: dict[str, Any] = {}
    import hashlib

    for fx in FIXTURE_LIST:
        pdf_bytes = _pdf(fx)
        if fx.kind == "pdf":
            data, ext = pdf_bytes, "pdf"
        elif fx.kind == "scan":
            data, ext = _scan_pdf(pdf_bytes), "pdf"
        elif fx.kind == "blurry":
            data, ext = _raster(pdf_bytes, blur=1.6), "png"
        else:
            data, ext = _raster(pdf_bytes), "png"
        path = FIXTURES / f"{fx.name}.{ext}"
        path.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        (EXTRACTION / f"{sha}.json").write_text(json.dumps(extraction(fx), indent=1, sort_keys=True), "utf-8")
        t = fx.totals()
        index[fx.name] = {
            "file": path.name,
            "sha256": sha,
            "shop": fx.shop,
            "kind": fx.kind,
            "note": fx.note,
            "expected_non_pass": fx.expected,
            "totals": {k: str(v) for k, v in t.items()},
        }
    (ROOT / "expected" / "fixtures.json").write_text(json.dumps(index, indent=1, sort_keys=True), "utf-8")
    return index


if __name__ == "__main__":
    result = build()
    print(f"wrote {len(result)} fixtures")
