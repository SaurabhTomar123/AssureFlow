"""ExtractionSchema v1 (P1-03) and the material field list (P1-04).

Every field is {value | null, page, excerpt, confidence}. Numbers are strings exactly as printed, so
Decimal parsing keeps printed precision (arithmetic contract).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FieldValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str | None
    page: int | None
    excerpt: str | None
    confidence: float


class LineV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line_no: int
    description: FieldValue
    hsn_sac: FieldValue
    qty: FieldValue
    unit_price: FieldValue
    discount: FieldValue
    taxable_value: FieldValue
    cgst_rate: FieldValue
    sgst_rate: FieldValue
    igst_rate: FieldValue
    combined_rate: FieldValue
    cgst_amount: FieldValue
    sgst_amount: FieldValue
    igst_amount: FieldValue


class ExtractionV1(BaseModel):
    """What the model must return for one purchase document."""

    model_config = ConfigDict(extra="forbid")
    document_type: FieldValue
    supplier_name: FieldValue
    supplier_gstin: FieldValue
    recipient_gstin: FieldValue
    invoice_number: FieldValue
    invoice_date: FieldValue
    place_of_supply: FieldValue
    currency: FieldValue
    taxable_total: FieldValue
    cgst_total: FieldValue
    sgst_total: FieldValue
    igst_total: FieldValue
    cess_total: FieldValue
    round_off: FieldValue
    invoice_total: FieldValue
    tax_printed_per_line: bool
    multiple_invoices: bool
    lines: list[LineV1]


SCHEMA_VERSION = "extraction.v1"

HEADER_FIELDS = (
    "document_type",
    "supplier_name",
    "supplier_gstin",
    "recipient_gstin",
    "invoice_number",
    "invoice_date",
    "place_of_supply",
    "currency",
    "taxable_total",
    "cgst_total",
    "sgst_total",
    "igst_total",
    "cess_total",
    "round_off",
    "invoice_total",
)

MATERIAL_FIELDS = (
    "document_type",
    "supplier_name",
    "supplier_gstin",
    "recipient_gstin",
    "invoice_number",
    "invoice_date",
    "place_of_supply",
    "taxable_total",
    "invoice_total",
)

LOW_CONFIDENCE = 0.8

MONEY_FIELDS = (
    "taxable_total",
    "cgst_total",
    "sgst_total",
    "igst_total",
    "cess_total",
    "round_off",
    "invoice_total",
)

LINE_FIELDS = (
    "description",
    "hsn_sac",
    "qty",
    "unit_price",
    "discount",
    "taxable_value",
    "cgst_rate",
    "sgst_rate",
    "igst_rate",
    "combined_rate",
    "cgst_amount",
    "sgst_amount",
    "igst_amount",
)

# Owner-facing correction keywords -> revision field.
CORRECTABLE = {
    "supplier": "supplier_name",
    "supplier_name": "supplier_name",
    "gstin": "supplier_gstin",
    "supplier_gstin": "supplier_gstin",
    "recipient_gstin": "recipient_gstin",
    "number": "invoice_number",
    "invoice_number": "invoice_number",
    "date": "invoice_date",
    "invoice_date": "invoice_date",
    "pos": "place_of_supply",
    "place_of_supply": "place_of_supply",
    "taxable": "taxable_total",
    "taxable_total": "taxable_total",
    "cgst": "cgst_total",
    "sgst": "sgst_total",
    "igst": "igst_total",
    "cess": "cess_total",
    "round_off": "round_off",
    "total": "invoice_total",
    "invoice_total": "invoice_total",
    "type": "document_type",
    "document_type": "document_type",
}
