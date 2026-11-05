from typing import Any
from sqlalchemy.orm import Session
from src.accounts.ledger import get_accounts_book
from src.advisory.tax_advisor import (
    analyze_presumptive_tax_44ad,
    calculate_asset_depreciation_section_32,
    generate_proprietor_tax_savings_plan,
    detect_blocked_itc_section_17_5,
)


class JuniorCAAgent:
    def __init__(self, agent_id: str = "junior-ca"):
        self.agent_id = agent_id

    def handle_khata_request(self, shop_id: str, db: Session, language: str = "en") -> str:
        book = get_accounts_book(shop_id, db)
        bd = book["breakdown"]

        if language == "hi":
            return (
                f"Aapka Masik Khata (Monthly Accounts Book):\n"
                f"----------------------------------------\n"
                f"Kul Kharcha / Outflow: INR {book['total_cash_outflow']:,.2f}\n"
                f"GST Tax Bhugtan: INR {book['total_tax_paid']:,.2f}\n\n"
                f"Vargikaran (Expense Breakdown):\n"
                f"- Inventory / Mal Kharid: INR {bd['inventory_purchases']:,.2f}\n"
                f"- Operating Expenses (Dukan Kharch): INR {bd['operating_expenses']:,.2f}\n"
                f"- Capital Assets (Upkaran / Machines): INR {bd['capital_assets']:,.2f}\n"
                f"- Logistics & Transport: INR {bd['logistics_freight']:,.2f}\n"
                f"----------------------------------------\n"
                f"Kul Entries: {book['entry_count']} bills darj hain."
            )

        return (
            f"Monthly Accounts Book (Khata):\n"
            f"----------------------------------------\n"
            f"Total Cash Outflow: INR {book['total_cash_outflow']:,.2f}\n"
            f"Total Tax Paid on Purchases: INR {book['total_tax_paid']:,.2f}\n\n"
            f"Expense Categorization:\n"
            f"- Inventory Purchases: INR {bd['inventory_purchases']:,.2f}\n"
            f"- Operating Expenses: INR {bd['operating_expenses']:,.2f}\n"
            f"- Capital Equipment: INR {bd['capital_assets']:,.2f}\n"
            f"- Logistics & Delivery: INR {bd['logistics_freight']:,.2f}\n"
            f"----------------------------------------\n"
            f"Total Invoices Reconciled: {book['entry_count']}"
        )

    def handle_tax_savings_request(self, shop_id: str, db: Session, language: str = "en") -> str:
        plan = generate_proprietor_tax_savings_plan()
        depreciation = calculate_asset_depreciation_section_32(shop_id, db)

        if language == "hi":
            lines = [
                "Junior CA Tax Savings Salah (Tax Optimization Plan):",
                "----------------------------------------",
                f"Sambhavit Varshik Tax Bachat: ~INR {plan['total_potential_annual_tax_saved'] + depreciation['estimated_income_tax_saved']:,.2f}",
                "",
                "1. Business Asset Depreciation (Section 32):",
                f"   Dukan ke upkaran/electronics par INR {depreciation['total_depreciation_claimable']:,.2f} depreciation claim karein.",
                f"   Isse lagbhag INR {depreciation['estimated_income_tax_saved']:,.2f} ka income tax bachega.",
                "",
                "2. Personal Investments & Deductions:",
            ]
            for it in plan["advice_items"]:
                lines.append(f"- {it['section']}: {it['opportunity']} (Tax bachat: INR {it['annual_tax_saved']:,.2f})")
                lines.append(f"  Salah: {it['tip']}")
            return "\n".join(lines)

        lines = [
            "Junior CA Tax Savings Advisory:",
            "----------------------------------------",
            f"Total Potential Annual Tax Savings: ~INR {plan['total_potential_annual_tax_saved'] + depreciation['estimated_income_tax_saved']:,.2f}",
            "",
            "1. Section 32 Commercial Asset Depreciation:",
            f"   Write off INR {depreciation['total_depreciation_claimable']:,.2f} on business tech/equipment.",
            f"   Estimated Income Tax Saved: INR {depreciation['estimated_income_tax_saved']:,.2f}.",
            "",
            "2. Proprietor Personal Tax Optimizations:",
        ]
        for it in plan["advice_items"]:
            lines.append(f"- {it['section']}: {it['opportunity']} (Save ~INR {it['annual_tax_saved']:,.2f})")
            lines.append(f"  Note: {it['tip']}")
        return "\n".join(lines)

    def handle_presumptive_tax_request(
        self,
        annual_turnover: float,
        digital_pct: float = 80.0,
        actual_margin_pct: float = 12.0,
        language: str = "en",
    ) -> str:
        analysis = analyze_presumptive_tax_44ad(annual_turnover, digital_pct, actual_margin_pct)

        if language == "hi":
            return (
                f"Section 44AD Presumptive Taxation Vishleshan:\n"
                f"----------------------------------------\n"
                f"Varshik Turnover: INR {annual_turnover:,.2f} ({digital_pct:.0f}% Digital / UPI)\n"
                f"Aapka Asli Munafa: INR {analysis['actual_profit']:,.2f} ({actual_margin_pct:.1f}%)\n"
                f"44AD ke antargat Manit Munafa: INR {analysis['deemed_profit_44ad']:,.2f}\n"
                f"Taxable Income mein Kami: INR {analysis['taxable_income_reduction']:,.2f}\n"
                f"Estimated Tax Bachat: ~INR {analysis['estimated_tax_saved_30pct']:,.2f}\n\n"
                f"CA Salah: {analysis['recommendation']}"
            )

        return (
            f"Section 44AD Presumptive Taxation Analysis:\n"
            f"----------------------------------------\n"
            f"Annual Turnover: INR {annual_turnover:,.2f} ({digital_pct:.0f}% Digital / Bank)\n"
            f"Actual Net Profit: INR {analysis['actual_profit']:,.2f} ({actual_margin_pct:.1f}%)\n"
            f"Section 44AD Deemed Profit: INR {analysis['deemed_profit_44ad']:,.2f}\n"
            f"Taxable Income Reduction: INR {analysis['taxable_income_reduction']:,.2f}\n"
            f"Estimated Tax Savings: ~INR {analysis['estimated_tax_saved_30pct']:,.2f}\n\n"
            f"Junior CA Advisory: {analysis['recommendation']}"
        )

