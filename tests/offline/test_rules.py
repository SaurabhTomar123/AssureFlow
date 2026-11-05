"""Golden rule fixtures (P2-16), arithmetic contract (P2-05..07) and property tests (P2-18)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from domain.extraction import ExtractionV1
from domain.services.intake import to_decimal
from rules import registry
from rules.arithmetic import check_tax, check_total, paise
from rules.gstin import check_character, make_gstin, structure_problem
from rules.types import FAIL, PASS, LineInput, RevisionInput, Tolerances

ROOT = Path(__file__).resolve().parents[2] / "seed"
INDEX = json.loads((ROOT / "expected" / "fixtures.json").read_text("utf-8"))
TOL = Tolerances(Decimal("0.01"), Decimal("1.00"))
SHOP_GSTIN = {"sharma": make_gstin("07", "SHARM9999K"), "gupta": make_gstin("27", "GUPTA8888L")}


def rev_from_fixture(name: str, **overrides: object) -> RevisionInput:
    info = INDEX[name]
    ex = ExtractionV1.model_validate(
        json.loads((ROOT / "expected" / "extraction" / f"{info['sha256']}.json").read_text())
    )
    lines = tuple(
        LineInput(
            line_no=ln.line_no,
            description=ln.description.value,
            hsn_sac=ln.hsn_sac.value,
            **{
                f: to_decimal(getattr(ln, f).value)
                for f in (
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
            },
        )
        for ln in ex.lines
    )
    values = dict(
        document_type=ex.document_type.value,
        supplier_name=ex.supplier_name.value,
        supplier_gstin=ex.supplier_gstin.value,
        recipient_gstin=ex.recipient_gstin.value,
        invoice_number=ex.invoice_number.value,
        invoice_date=ex.invoice_date.value,
        place_of_supply=ex.place_of_supply.value,
        currency=ex.currency.value,
        tax_printed_per_line=ex.tax_printed_per_line,
        taxable_total=to_decimal(ex.taxable_total.value),
        cgst_total=to_decimal(ex.cgst_total.value),
        sgst_total=to_decimal(ex.sgst_total.value),
        igst_total=to_decimal(ex.igst_total.value),
        cess_total=to_decimal(ex.cess_total.value),
        round_off=to_decimal(ex.round_off.value),
        invoice_total=to_decimal(ex.invoice_total.value),
        lines=lines,
        shop_gstin=SHOP_GSTIN[info["shop"]],
    )
    values.update(overrides)
    return RevisionInput(**values)  # type: ignore[arg-type]


GOLDEN = [n for n in INDEX if n not in ("F11_duplicate_copy", "F13_blurry_photo")]


@pytest.mark.parametrize("name", GOLDEN)
def test_golden_fixture_outcomes(name: str) -> None:
    results = {r.rule_id: r.outcome for r in registry.run_profile(rev_from_fixture(name), TOL)}
    non_pass = {k: v for k, v in results.items() if v != PASS}
    assert non_pass == INDEX[name]["expected_non_pass"]


def test_duplicate_rules_use_precomputed_context() -> None:
    rev = rev_from_fixture(
        "F11_duplicate_copy", duplicate_owner_ref="INV-0010", similar_case_refs=("INV-0010",)
    )
    results = {r.rule_id: r.outcome for r in registry.run_profile(rev, TOL)}
    assert {k: v for k, v in results.items() if v != PASS} == INDEX["F11_duplicate_copy"]["expected_non_pass"]


def test_blurry_misread_total_fails_until_corrected() -> None:
    misread = rev_from_fixture("F13_blurry_photo")
    assert check_total(misread, TOL).outcome == FAIL
    fixed = rev_from_fixture("F13_blurry_photo", invoice_total=Decimal("1180.00"))
    assert check_total(fixed, TOL).outcome == PASS


def test_total_check_records_calculation_and_tolerance() -> None:
    result = check_total(rev_from_fixture("F09_total_mismatch"), TOL)
    assert result.outcome == FAIL
    assert result.difference == Decimal("100.00")
    assert result.calculation["tolerance"] == "1.00"
    assert result.calculation["computed_total"] == "2832.00"


def test_gstin_wording_is_structural() -> None:
    gstin = make_gstin("07", "MODER1111A")
    assert structure_problem(gstin) is None
    assert (
        structure_problem(gstin[:-1] + ("0" if gstin[-1] != "0" else "1")) == "check character does not match"
    )
    result = registry.BY_ID["R-GSTIN-01"].fn(rev_from_fixture("F01_clean_intrastate_5pct"), TOL)
    assert result.message == "Supplier GSTIN structure passed."
    bad = registry.BY_ID["R-GSTIN-01"].fn(rev_from_fixture("F06_invalid_gstin"), TOL)
    assert "not verified" in bad.message and "registered" not in bad.message


def test_rounding_is_half_up_at_printed_level() -> None:
    assert paise(Decimal("10.005")) == Decimal("10.01")
    assert paise(Decimal("10.004999")) == Decimal("10.00")


def test_separate_tolerances_never_excuse_each_other() -> None:
    base = rev_from_fixture("F01_clean_intrastate_5pct")
    off_by_50p = RevisionInput(**{**base.__dict__, "invoice_total": base.invoice_total + Decimal("0.50")})  # type: ignore[operator]
    assert check_total(off_by_50p, TOL).outcome == PASS  # within INR 1.00
    lines = list(base.lines)
    lines[0] = LineInput(**{**lines[0].__dict__, "cgst_amount": lines[0].cgst_amount + Decimal("0.50")})  # type: ignore[operator]
    tax_off = RevisionInput(**{**base.__dict__, "lines": tuple(lines)})
    assert check_tax(tax_off, TOL).outcome == FAIL  # tax tolerance is 0.01 per line


@given(
    qty=st.decimals(min_value=Decimal("0.0001"), max_value=Decimal("9999"), places=4),
    price=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("99999"), places=2),
    rate=st.sampled_from([Decimal("2.5"), Decimal("6"), Decimal("9"), Decimal("14")]),
)
def test_property_consistent_invoice_passes_and_is_order_invariant(
    qty: Decimal, price: Decimal, rate: Decimal
) -> None:
    taxable = paise(qty * price)
    tax = paise(taxable * rate / 100)
    line = LineInput(1, "x", "1001", qty, price, None, taxable, rate, rate, None, None, tax, tax, None)
    line2 = LineInput(
        2,
        "y",
        "1002",
        Decimal(1),
        Decimal("10.00"),
        None,
        Decimal("10.00"),
        rate,
        rate,
        None,
        None,
        paise(Decimal(10) * rate / 100),
        paise(Decimal(10) * rate / 100),
        None,
    )
    base = rev_from_fixture("F01_clean_intrastate_5pct")
    totals = {
        "taxable_total": taxable + Decimal("10.00"),
        "cgst_total": tax + line2.cgst_amount,  # type: ignore[operator]
        "sgst_total": tax + line2.sgst_amount,  # type: ignore[operator]
        "igst_total": Decimal("0.00"),
        "round_off": None,
    }
    totals["invoice_total"] = totals["taxable_total"] + totals["cgst_total"] + totals["sgst_total"]  # type: ignore[operator]
    a = RevisionInput(**{**base.__dict__, **totals, "lines": (line, line2)})
    b = RevisionInput(**{**base.__dict__, **totals, "lines": (line2, line)})
    ra, rb = registry.run_profile(a, TOL), registry.run_profile(b, TOL)
    for result in ra:
        if result.rule_id.startswith("R-AMT"):
            assert result.outcome == PASS, result.message
        assert all(not isinstance(v, float) for v in result.calculation.values())
    assert [r.outcome for r in ra] == [r.outcome for r in rb]


def test_results_hash_is_deterministic() -> None:
    rev = rev_from_fixture("F03_clean_mixed_rates")
    assert registry.results_hash(registry.run_profile(rev, TOL)) == registry.results_hash(
        registry.run_profile(rev, TOL)
    )


def test_check_character_known_value() -> None:
    assert check_character("07MODER1111A1Z") == make_gstin("07", "MODER1111A")[-1]
