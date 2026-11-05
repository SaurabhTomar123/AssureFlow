"""Rule inputs and results. Rules are pure functions: same inputs produce the same result (G-15)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

PASS = "pass"
FAIL = "fail"
NEEDS_EVIDENCE = "needs_evidence"
UNSUPPORTED = "unsupported"

BLOCKING = "blocking"
WARNING = "warning"
INFO = "info"


@dataclass(frozen=True)
class LineInput:
    line_no: int
    description: str | None
    hsn_sac: str | None
    qty: Decimal | None
    unit_price: Decimal | None
    discount: Decimal | None
    taxable_value: Decimal | None
    cgst_rate: Decimal | None
    sgst_rate: Decimal | None
    igst_rate: Decimal | None
    combined_rate: Decimal | None
    cgst_amount: Decimal | None
    sgst_amount: Decimal | None
    igst_amount: Decimal | None


@dataclass(frozen=True)
class RevisionInput:
    document_type: str | None
    supplier_name: str | None
    supplier_gstin: str | None
    recipient_gstin: str | None
    invoice_number: str | None
    invoice_date: str | None
    place_of_supply: str | None
    currency: str | None
    tax_printed_per_line: bool
    taxable_total: Decimal | None
    cgst_total: Decimal | None
    sgst_total: Decimal | None
    igst_total: Decimal | None
    cess_total: Decimal | None
    round_off: Decimal | None
    invoice_total: Decimal | None
    lines: tuple[LineInput, ...]
    shop_gstin: str
    duplicate_owner_ref: str | None = None
    similar_case_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Tolerances:
    tax_line: Decimal
    amount: Decimal


@dataclass
class RuleResult:
    rule_id: str
    version: int
    outcome: str
    severity: str
    category: str
    message: str
    inputs: dict[str, Any] = field(default_factory=dict)
    calculation: dict[str, Any] = field(default_factory=dict)
    difference: Decimal | None = None
    components: tuple[str, ...] = ()
    owner_hint: str | None = None

    @property
    def is_blocking(self) -> bool:
        return self.outcome != PASS and self.severity == BLOCKING


def s(value: Decimal | None) -> str | None:
    return None if value is None else str(value)
