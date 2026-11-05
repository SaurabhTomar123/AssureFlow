from typing import Any, Optional
from sqlalchemy.orm import Session
from src.accounts.ledger import get_accounts_book
from src.db.models import Shop, Bill

BLOCKED_ITC_KEYWORDS = [
    "food", "beverage", "catering", "restaurant", "lunch", "dinner",
    "club", "fitness", "gym", "motor vehicle", "car repair", "personal care"
]


def analyze_presumptive_tax_44ad(
    annual_turnover: float,
    digital_turnover_pct: float = 70.0,
    actual_profit_margin_pct: float = 12.0,
) -> dict[str, Any]:
    if annual_turnover <= 0:
        return {"error": "Turnover must be greater than zero"}

    is_eligible = annual_turnover <= 20000000.0 or (digital_turnover_pct >= 95.0 and annual_turnover <= 30000000.0)

    digital_turnover = annual_turnover * (digital_turnover_pct / 100.0)
    cash_turnover = annual_turnover - digital_turnover

    deemed_digital_profit = digital_turnover * 0.06
    deemed_cash_profit = cash_turnover * 0.08
    total_deemed_profit = deemed_digital_profit + deemed_cash_profit
    effective_deemed_rate = (total_deemed_profit / annual_turnover) * 100.0

    actual_profit = annual_turnover * (actual_profit_margin_pct / 100.0)
    taxable_difference = actual_profit - total_deemed_profit

    if is_eligible and taxable_difference > 0:
        estimated_tax_savings = taxable_difference * 0.30
        recommendation = (
            f"Strong Recommendation: Opt for Section 44AD Presumptive Taxation. "
            f"Your actual estimated profit is INR {actual_profit:,.2f} ({actual_profit_margin_pct:.1f}%), "
            f"but under 44AD your deemed taxable profit is only INR {total_deemed_profit:,.2f} "
            f"({effective_deemed_rate:.1f}%). "
            f"You legally reduce taxable income by INR {taxable_difference:,.2f}, saving ~INR {estimated_tax_savings:,.2f} "
            f"in income tax, and you are exempt from mandatory Section 44AB tax audit."
        )
    elif is_eligible:
        recommendation = (
            f"Maintain Regular Books: Your estimated profit margin ({actual_profit_margin_pct:.1f}%) "
            f"is below the 44AD deemed rate ({effective_deemed_rate:.1f}%). "
            f"Maintaining audited regular books of account will result in lower income tax."
        )
    else:
        recommendation = (
            f"Ineligible for 44AD: Annual turnover of INR {annual_turnover:,.2f} exceeds statutory threshold."
        )

    return {
        "annual_turnover": annual_turnover,
        "is_eligible": is_eligible,
        "digital_turnover_pct": digital_turnover_pct,
        "actual_profit": round(actual_profit, 2),
        "deemed_profit_44ad": round(total_deemed_profit, 2),
        "taxable_income_reduction": max(round(taxable_difference, 2), 0.0),
        "estimated_tax_saved_30pct": max(round(taxable_difference * 0.30, 2), 0.0),
        "recommendation": recommendation,
    }


def detect_blocked_itc_section_17_5(shop_id: str, db: Session) -> list[dict[str, Any]]:
    bills = db.query(Bill).filter(Bill.shop_id == shop_id).all()
    blocked_flags = []

    for bill in bills:
        for item in bill.items:
            desc_lower = item.description.lower()
            for kw in BLOCKED_ITC_KEYWORDS:
                if kw in desc_lower:
                    tax_at_stake = (item.cgst or 0.0) + (item.sgst or 0.0) + (item.igst or 0.0)
                    blocked_flags.append({
                        "bill_id": bill.id,
                        "bill_number": bill.bill_number,
                        "supplier_name": bill.supplier_name,
                        "item_description": item.description,
                        "keyword_matched": kw,
                        "blocked_itc_amount": round(tax_at_stake, 2),
                        "legal_clause": "Section 17(5)(b)(i) of CGST Act",
                        "advisory": (
                            f"ITC of INR {tax_at_stake:.2f} on '{item.description}' is blocked under Section 17(5). "
                            f"Exclude this item from GSTR-3B Table 4(A) to avoid automatic scrutiny notices."
                        ),
                    })
                    break

    return blocked_flags


def calculate_asset_depreciation_section_32(shop_id: str, db: Session) -> dict[str, Any]:
    accounts_book = get_accounts_book(shop_id, db)
    capital_entries = [e for e in accounts_book["entries"] if e["category"] == "CAPITAL_ASSET"]

    total_tech_assets = 0.0
    total_general_assets = 0.0

    tech_keywords = ["computer", "laptop", "printer", "software", "smartphone", "mobile"]

    for entry in capital_entries:
        desc_lower = entry["description"].lower()
        if any(kw in desc_lower for kw in tech_keywords):
            total_tech_assets += entry["net_amount"]
        else:
            total_general_assets += entry["net_amount"]

    tech_depreciation_40 = total_tech_assets * 0.40
    general_depreciation_15 = total_general_assets * 0.15
    total_depreciation = tech_depreciation_40 + general_depreciation_15
    tax_savings_estimate = total_depreciation * 0.30

    return {
        "shop_id": shop_id,
        "capital_asset_count": len(capital_entries),
        "tech_assets_total": round(total_tech_assets, 2),
        "tech_depreciation_40pct": round(tech_depreciation_40, 2),
        "general_assets_total": round(total_general_assets, 2),
        "general_depreciation_15pct": round(general_depreciation_15, 2),
        "total_depreciation_claimable": round(total_depreciation, 2),
        "estimated_income_tax_saved": round(tax_savings_estimate, 2),
        "advisory": (
            f"Under Section 32 of the Income Tax Act, you can write off INR {total_depreciation:,.2f} "
            f"as depreciation on business equipment, reducing personal income tax liability by ~INR {tax_savings_estimate:,.2f}."
        ),
    }


def generate_proprietor_tax_savings_plan(
    estimated_annual_income: float = 900000.0,
    current_80c_investment: float = 50000.0,
    current_health_insurance: float = 0.0,
    has_parents_insurance: bool = False,
    current_nps_80ccd: float = 0.0,
) -> dict[str, Any]:
    advice_items = []
    total_potential_savings = 0.0

    unclaimed_80c = max(150000.0 - current_80c_investment, 0.0)
    if unclaimed_80c > 0:
        tax_saved = unclaimed_80c * 0.20
        total_potential_savings += tax_saved
        advice_items.append({
            "section": "Section 80C",
            "opportunity": f"Invest additional INR {unclaimed_80c:,.0f} in PPF, ELSS, or Tax-Saver FD",
            "max_limit": 150000.0,
            "annual_tax_saved": round(tax_saved, 2),
            "tip": "PPF offers 7.1% tax-free interest; ELSS provides equity wealth compounding with a 3-year lock-in.",
        })

    unclaimed_80d_self = max(25000.0 - current_health_insurance, 0.0)
    parents_benefit = 50000.0 if not has_parents_insurance else 0.0
    total_80d_gap = unclaimed_80d_self + parents_benefit

    if total_80d_gap > 0:
        tax_saved = total_80d_gap * 0.20
        total_potential_savings += tax_saved
        advice_items.append({
            "section": "Section 80D",
            "opportunity": f"Secure medical insurance up to INR {total_80d_gap:,.0f} for family and senior parents",
            "max_limit": 75000.0,
            "annual_tax_saved": round(tax_saved, 2),
            "tip": "Medical emergencies deplete working capital. Premium payments provide direct deductions under 80D.",
        })

    unclaimed_nps = max(50000.0 - current_nps_80ccd, 0.0)
    if unclaimed_nps > 0:
        tax_saved = unclaimed_nps * 0.20
        total_potential_savings += tax_saved
        advice_items.append({
            "section": "Section 80CCD(1B)",
            "opportunity": f"Deposit INR {unclaimed_nps:,.0f} in National Pension System (NPS)",
            "max_limit": 50000.0,
            "annual_tax_saved": round(tax_saved, 2),
            "tip": "This INR 50,000 deduction is strictly over and above the Section 80C INR 1.5 Lakh ceiling.",
        })

    return {
        "estimated_annual_income": estimated_annual_income,
        "total_potential_annual_tax_saved": round(total_potential_savings, 2),
        "advice_items": advice_items,
    }
