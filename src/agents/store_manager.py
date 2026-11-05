from typing import Any, List
from sqlalchemy.orm import Session
from src.inventory.service import get_inventory_catalog, get_low_stock_report
from src.staff.service import (
    get_daily_shift_summary,
    calculate_monthly_payroll,
    list_employees,
    mark_attendance,
)


class StoreManagerAgent:
    def __init__(self, agent_id: str = "store-manager"):
        self.agent_id = agent_id

    def format_stock_overview(self, shop_id: str, db: Session, language: str = "en") -> str:
        catalog = get_inventory_catalog(shop_id, db)
        total_items = len(catalog)
        low_stock = sum(1 for it in catalog if it["status"] == "LOW_STOCK")
        out_of_stock = sum(1 for it in catalog if it["status"] == "OUT_OF_STOCK")
        healthy = total_items - low_stock - out_of_stock

        if language == "hi":
            lines = [
                "Store Manager Stock Report (Inventory Overview):",
                "----------------------------------------",
                f"Kul SKUs / Items: {total_items}",
                f"Pura Stock Upalabdha (Healthy): {healthy}",
                f"Kam Stock (Low Stock Alert): {low_stock}",
                f"Khatam Stock (Out of Stock): {out_of_stock}",
                "----------------------------------------",
            ]
            if low_stock > 0:
                lines.append("Turant reorder karne ke liye '/reorder' likhein.")
            return "\n".join(lines)

        lines = [
            "Store Operations — Inventory Health Report:",
            "----------------------------------------",
            f"Total Catalog SKUs: {total_items}",
            f"Healthy Stock Level: {healthy}",
            f"Low Stock Warnings: {low_stock}",
            f"Out of Stock: {out_of_stock}",
            "----------------------------------------",
        ]
        if low_stock > 0:
            lines.append("Type '/reorder' to generate an automated replenishment sheet.")
        return "\n".join(lines)

    def format_reorder_alert(self, shop_id: str, db: Session, language: str = "en") -> str:
        low_items = get_low_stock_report(shop_id, db)

        if not low_items:
            if language == "hi":
                return "Sabhi items ka stock purn hai. Koi reorder avashyak nahi hai."
            return "All inventory levels are optimal. No reorders required currently."

        total_est_cost = sum(it["estimated_cost"] for it in low_items)

        if language == "hi":
            lines = [
                "Zaroori Reorder Suchi (Replenishment Order Sheet):",
                "----------------------------------------",
                f"Kam stock wale items: {len(low_items)} | Anumanit Kharcha: INR {total_est_cost:,.2f}",
                "",
            ]
            for it in low_items:
                lines.append(
                    f"- {it['name']}: Bacha hai {it['current_stock']} {it['unit']} "
                    f"(Order karein: {it['suggested_reorder_qty']} {it['unit']} | ~INR {it['estimated_cost']:,.2f})"
                )
            lines.append("----------------------------------------")
            lines.append("Supplier ko order bhejne ke liye CA/Owner se approve karwayein.")
            return "\n".join(lines)

        lines = [
            "Urgent Restock & Procurement Sheet:",
            "----------------------------------------",
            f"SKUs Requiring Restock: {len(low_items)} | Total Estimated Cost: INR {total_est_cost:,.2f}",
            "",
        ]
        for it in low_items:
            lines.append(
                f"- {it['name']}: {it['current_stock']} {it['unit']} remaining "
                f"(Suggested order: {it['suggested_reorder_qty']} {it['unit']} | Cost: INR {it['estimated_cost']:,.2f})"
            )
        lines.append("----------------------------------------")
        lines.append("Ready for manager issuance or supplier purchase order.")
        return "\n".join(lines)

    def format_shift_summary(self, shop_id: str, date: str, db: Session, language: str = "en") -> str:
        summary = get_daily_shift_summary(shop_id, date, db)

        if language == "hi":
            lines = [
                f"Dukan Shift Report — Tarikh: {date}",
                "----------------------------------------",
                f"Karmchari Hazri (Staff Present): {summary['present_count']} / {summary['total_staff']}",
            ]
            if summary["present_staff"]:
                lines.append(f"Karyarat: {', '.join(summary['present_staff'])}")
            if summary["absent_staff"]:
                lines.append(f"Anupasthit (Absent): {', '.join(summary['absent_staff'])}")

            lines.append(f"Aaj Mall Prapt Hua (Bills Ingested): {summary['stock_movements_in_today']}")
            lines.append(f"Kam Stock Items: {summary['urgent_reorder_count']}")
            if summary["urgent_reorder_items"]:
                lines.append(f"Alert: {', '.join(summary['urgent_reorder_items'])}")
            lines.append("----------------------------------------")
            return "\n".join(lines)

        lines = [
            f"Daily Shift Briefing — Date: {date}",
            "----------------------------------------",
            f"Staff On Duty: {summary['present_count']} / {summary['total_staff']}",
        ]
        if summary["present_staff"]:
            lines.append(f"Present: {', '.join(summary['present_staff'])}")
        if summary["absent_staff"]:
            lines.append(f"Absent / On-Leave: {', '.join(summary['absent_staff'])}")

        lines.append(f"Purchase Stock Receipts Today: {summary['stock_movements_in_today']}")
        lines.append(f"Low Stock Items Requiring Restock: {summary['urgent_reorder_count']}")
        if summary["urgent_reorder_items"]:
            lines.append(f"Attention Needed: {', '.join(summary['urgent_reorder_items'])}")
        lines.append("----------------------------------------")
        return "\n".join(lines)

    def format_payroll_report(self, shop_id: str, month: int, year: int, db: Session, language: str = "en") -> str:
        payroll = calculate_monthly_payroll(shop_id, month, year, db)
        total_payroll = sum(p["net_payable"] for p in payroll)

        if language == "hi":
            lines = [
                f"Masik Vetan Register (Payroll Slip) — Mahina: {month}/{year}",
                "----------------------------------------",
                f"Kul Karmchari: {len(payroll)} | Kul Vetan Rashi: INR {total_payroll:,.2f}",
                "",
            ]
            for p in payroll:
                lines.append(
                    f"- {p['employee_name']} ({p['designation']}): {p['days_present']} din upasthit | "
                    f"Net Vetan: INR {p['net_payable']:,.2f}"
                )
            lines.append("----------------------------------------")
            return "\n".join(lines)

        lines = [
            f"Monthly Payroll Sheet — Period: {month:02d}/{year}",
            "----------------------------------------",
            f"Total Staff: {len(payroll)} | Total Wage Outflow: INR {total_payroll:,.2f}",
            "",
        ]
        for p in payroll:
            lines.append(
                f"- {p['employee_name']} ({p['designation']}): {p['days_present']} days present | "
                f"Net Payable: INR {p['net_payable']:,.2f}"
            )
        lines.append("----------------------------------------")
        return "\n".join(lines)

    def handle_checkin_command(
        self,
        shop_id: str,
        staff_name: str,
        date_str: str,
        time_str: str = "09:30 AM",
        db: Session = None,
        language: str = "en",
    ) -> str:
        employees = list_employees(shop_id, db)
        matched = None
        for emp in employees:
            if staff_name.lower() in emp.name.lower():
                matched = emp
                break

        if not matched:
            matched = list_employees(shop_id, db)[0] if employees else None

        if not matched:
            return "No registered employee profile found for check-in."

        rec = mark_attendance(
            shop_id=shop_id,
            employee_id=matched.id,
            date=date_str,
            status="PRESENT",
            check_in_time=time_str,
            db=db,
        )

        if language == "hi":
            return f"Hazri Darj: {matched.name} ({matched.designation}) ne {time_str} par check-in kiya."
        return f"Attendance Logged: {matched.name} ({matched.designation}) checked in at {time_str}."

    def format_auto_restock_announcement(
        self,
        restocked_items: List[dict[str, Any]],
        invoice_number: str,
        supplier_name: str,
        language: str = "en",
    ) -> str:
        if not restocked_items:
            return ""

        item_summaries = [f"{it['name']} (+{it['added_quantity']} {it['unit']} -> Now {it['new_stock']})" for it in restocked_items]

        if language == "hi":
            return (
                f"Auto-Restock Alert (Invoice #{invoice_number} from {supplier_name}):\n"
                f"Naya stock inventory mein jod diya gaya hai:\n"
                f"- " + "\n- ".join(item_summaries)
            )

        return (
            f"Auto-Restock Complete (Invoice #{invoice_number} from {supplier_name}):\n"
            f"Inventory balances updated automatically:\n"
            f"- " + "\n- ".join(item_summaries)
        )
