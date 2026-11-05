import pytest
from src.db.session import SessionLocal
from src.advisory.tax_advisor import (
    analyze_presumptive_tax_44ad,
    calculate_asset_depreciation_section_32,
    detect_blocked_itc_section_17_5,
    generate_proprietor_tax_savings_plan,
)


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_analyze_presumptive_tax_44ad_eligible_and_beneficial():
    res = analyze_presumptive_tax_44ad(
        annual_turnover=5000000.0,
        digital_turnover_pct=80.0,
        actual_profit_margin_pct=15.0,
    )
    assert res["is_eligible"] is True
    assert res["actual_profit"] == 750000.0
    assert res["deemed_profit_44ad"] < res["actual_profit"]
    assert res["taxable_income_reduction"] > 0
    assert res["estimated_tax_saved_30pct"] > 0
    assert "Opt for Section 44AD" in res["recommendation"]


def test_analyze_presumptive_tax_44ad_ineligible():
    res = analyze_presumptive_tax_44ad(annual_turnover=35000000.0)
    assert res["is_eligible"] is False
    assert "exceeds statutory threshold" in res["recommendation"]


def test_calculate_asset_depreciation(db_session):
    res = calculate_asset_depreciation_section_32("shop-sharma-kirana", db_session)
    assert res["shop_id"] == "shop-sharma-kirana"
    assert res["capital_asset_count"] >= 1
    assert res["total_depreciation_claimable"] > 0.0
    assert res["estimated_income_tax_saved"] > 0.0
    assert "Section 32" in res["advisory"]


def test_proprietor_tax_savings_plan():
    plan = generate_proprietor_tax_savings_plan(
        estimated_annual_income=1000000.0,
        current_80c_investment=50000.0,
        current_health_insurance=0.0,
        has_parents_insurance=False,
        current_nps_80ccd=0.0,
    )
    assert plan["total_potential_annual_tax_saved"] > 0
    sections = [item["section"] for item in plan["advice_items"]]
    assert "Section 80C" in sections
    assert "Section 80D" in sections
    assert "Section 80CCD(1B)" in sections
