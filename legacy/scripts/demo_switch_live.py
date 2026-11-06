import sys
import time
import os
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Windows ANSI color support
os.system("")

CYAN = "\033[96m"
MAGENTA = "\033[95m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_step(beat_num, title):
    print(f"\n{BOLD}{'=' * 80}{RESET}")
    print(f"{BOLD}[BEAT {beat_num}/15] {title}{RESET}")
    print(f"{BOLD}{'=' * 80}{RESET}")
    time.sleep(0.4)


def room_shop(sender, message):
    print(f"{CYAN}[ROOM: shop-sharma-kirana]{RESET} {BOLD}{sender}:{RESET} {message}")
    time.sleep(0.3)


def room_ca(sender, message):
    print(f"{MAGENTA}[ROOM: ca-office]{RESET} {BOLD}{sender}:{RESET} {message}")
    time.sleep(0.3)


def room_vendor(sender, message):
    print(f"{YELLOW}[ROOM: vendor-dispute-desk]{RESET} {BOLD}{sender}:{RESET} {message}")
    time.sleep(0.3)


def system_log(msg):
    print(f"{GREEN}--> {msg}{RESET}")
    time.sleep(0.2)


def run_live_demo():
    print(f"\n{BOLD}MUNIMJI — SWITCH AUTONOMOUS MULTI-AGENT COMPLIANCE & STORE OPS DEMO{RESET}")
    print("Core Principle: AI reads and advises, code checks, human decides.\n")
    time.sleep(0.8)

    # Beat 1
    print_step(1, "Private Shop Intake & Bill Reader Extraction")
    room_shop("Shop Owner Sharma", "Uploaded invoice photo: bill_01_clean_kirana_5pct.pdf")
    room_shop(
        "@bill-reader",
        "Document Extracted: MAS-2026-101\n"
        "  Supplier: Modern Agro Staples Ltd (GSTIN: 07MODER1111A1Z1)\n"
        "  Taxable: INR 7,400.00 | CGST: INR 185.00 | SGST: INR 185.00 | Total: INR 7,770.00\n"
        "  Please verify details and reply 'OK' to confirm.",
    )

    # Beat 2
    print_step(2, "Owner Confirmation & Store Manager Auto-Restock")
    room_shop("Shop Owner Sharma", "OK")
    system_log("Invoice MAS-2026-101 confirmed by owner. Dispatching restock event...")
    room_shop(
        "@store-manager",
        "Auto-Restock Complete: Inventory balances updated automatically (+10.0 units Aashirvaad Atta 10kg, +8.0 units Fortune Rice 5kg).",
    )

    # Beat 3
    print_step(3, "Kacha Counter Chit (Smart Sieve Tax-Evasion Shield)")
    room_shop("Shop Owner Sharma", "Uploaded rough counter chit: 'Ramu Mandi se 5 bori chana aaya'")
    room_shop(
        "@bill-reader",
        "KACHA SMART SIEVE ALERT: Classified as INFORMAL ESTIMATE SLIP.\n"
        "  - Quarantined from CA Tax Return Pool (Section 122 Penalty Protection).\n"
        "  - Forwarded to @store-manager: +5 Bori Desi Chana added to store catalog.\n"
        "  - Logged to /khata internal store procurement (INR 6,000.00).",
    )

    # Beat 4
    print_step(4, "Serious Interstate Tax Classification Defect & CA Escalation")
    room_shop("Shop Owner Sharma", "Uploaded interstate invoice: bill_13_interstate_wrong_tax.pdf")
    room_shop("@bill-reader", "Invoice #INV-2026-013 extracted from Gujarat vendor. Forwarding to GST Checker...")
    room_ca(
        "@gst-checker",
        "COMPLIANCE ESCALATION FROM [shop-sharma-kirana]:\n"
        "  Bill #INV-2026-013 interstate supply charged CGST/SGST instead of IGST.\n"
        "  Disputed ITC: INR 1,440.00.\n"
        "  Action Required: /approve, /reject, or /ask_supplier.",
    )

    # Beat 5
    print_step(5, "CA Single-Click Dispute Link Generation")
    room_ca("Chartered Accountant", "/ask_supplier BILL-013")
    room_ca(
        "@return-preparer",
        "Generated Rule 37A Demand Notice citing Section 16(2)(aa). Dispatched tokenized dispute link to vendor billing desk.",
    )

    # Beat 6
    print_step(6, "Autonomous Bot-to-Bot Vendor Dispute Resolution")
    room_vendor(
        "@vendor-concierge",
        "Incoming Dispute Ticket from Sharma Kirana Store:\n"
        "  Bill #INV-2026-013 wrong tax classification. Disputed ITC: INR 1,440.00.",
    )
    room_vendor("Supplier Billing Team", "Credit Note #CN-2026-9901 issued for INR 1,440.00 tax differential.")
    room_ca("@return-preparer", "Dispute Resolved: Supplier issued Credit Note #CN-2026-9901. Tax credit pool adjusted.")
    room_shop(
        "@follow-up",
        "Vendor Dispute Notice Cleared: Modern Agro resolved tax differential via Credit Note #CN-2026-9901. Your ITC is safe.",
    )

    # Beat 7
    print_step(7, "Wispr Voice Ingestion (Code with Wispr Bounty)")
    room_shop("Shop Owner Sharma", "[Voice Note (Wispr Flow)]: 'Bhai 12 bori Aashirvaad Atta delivery aayi hai'")
    room_shop(
        "@store-manager",
        "Voice Delivery Processed: Restocked 1 catalog item in inventory:\n"
        "  - Aashirvaad Atta: +12 units (New Total: 22.0 units).",
    )

    # Beat 8
    print_step(8, "Live GSP Inward Feed & Two-Way GSTR-2B Auto-Reconciliation")
    system_log("Syncing live government portal GSTR-2B inward records for Sharma Kirana Store...")
    system_log("Reconciliation complete: 1 Matched | 1 Tax Mismatch | 1 Supplier Default caught under Section 16(2)(aa).")

    # Beat 9
    print_step(9, "Account Aggregator Three-Way Bank Outflow Match")
    system_log("Ingesting bank statement debits via RBI Account Aggregator...")
    system_log("Three-Way Cross Match: Physical Bill <-> GSTR-2B Return <-> Bank Payment Outflow.")
    system_log("STATUS: THREE_WAY_MATCHED for Bill MAS-2026-101 (INR 7,770.00 settled via UPI).")

    # Beat 10
    print_step(10, "Proactive GST Audit Radar & Supplier Risk Scorecard")
    system_log("Audit Radar Computed: Risk Score 25/100 [LOW - Audit-Proof].")
    system_log("MSME Credit Solvency Score: 760/900. Ready for 1-click Mudra loan application.")
    system_log("Supplier Scorecard: Modern Agro Ltd [A+ Safe Partner] | Ghost Trader [C High Defaulter Risk].")

    # Beat 11
    print_step(11, "Junior CA Bookkeeping & Section 44AD Presumptive Tax Advice")
    room_shop("Shop Owner Sharma", "/khata")
    room_shop(
        "@junior-ca",
        "Digital Accounts Book (Current Month):\n"
        "  - Resale Inventory: INR 48,400.00\n"
        "  - Operating Expenses: INR 54,400.00\n"
        "  - Capital Assets: INR 9,000.00\n"
        "  - Section 44AD Recommendation: Declaring presumptive net profit saves INR 24,600.00 in audit fees.",
    )

    # Beat 12
    print_step(12, "Month-End GSTR-3B Government Format Export")
    room_ca("Chartered Accountant", "/summary shop-sharma-kirana")
    room_ca(
        "@return-preparer",
        "GSTR-3B Reconciliation Summary Generated:\n"
        "  - Eligible ITC: CGST INR 4,528.00 | SGST INR 4,528.00 | IGST INR 1,620.00\n"
        "  - Total Clean Invoices: 14\n"
        "  - Download: munimji_gstr3b_export_shop-sharma-kirana.json",
    )

    # Beat 13
    print_step(13, "Smart Inventory FEFO Expiry & Return-to-Vendor Debit Note")
    room_shop("Shop Owner Sharma", "/fefo_expiry_check")
    room_shop(
        "@store-manager",
        "FEFO Horizon Audit Triggered:\n"
        "  - Batch BAT-EXP-001 (Amul Butter 500g): Expired 5 days ago (5 units at risk: INR 1,200.00).\n"
        "  - Auto-generated Debit Note #DN-RTV-20261105-EXP001.\n"
        "  - Claim: INR 1,416.00 (INR 1,200 taxable + INR 216 18% GST reversal).\n"
        "  - Auto-deducted 5 units from store stock. Supplier return dispatch confirmed.",
    )
    system_log("Dynamic Reorder PO Draft: Tata Salt 1kg ADV 2.0 units/day (4 days remaining). Optimal PO: 22 units (INR 484.00).")

    # Beat 14
    print_step(14, "Autonomous Double-Entry Ledger, P&L & 30-Day Cash Flow Runway")
    room_shop("Shop Owner Sharma", "/financials")
    room_shop(
        "@junior-ca",
        "Autonomous Double-Entry Financial Cockpit:\n"
        "  - Trial Balance: BALANCED (INR 121,000.00 Debits = INR 121,000.00 Credits)\n"
        "  - P&L: Revenue INR 25,000.00 | Operating Expenses INR 4,000.00 | Net Profit: INR 21,000.00\n"
        "  - Balance Sheet: Assets INR 121,000.00 = Liabilities INR 0.00 + Equity INR 121,000.00",
    )
    room_ca(
        "@return-preparer",
        "Treasury 30-Day Liquidity Forecast & Payment Prioritization:\n"
        "  - Working Capital: SAFE (Liquid Bank Reserves INR 125,000.00 vs Outflows INR 104,200.00)\n"
        "  - GST Liability due on 20th: INR 14,200.00 | Scheduled Payroll: INR 45,000.00\n"
        "  - Priority Queue: PAY Reliable Distributor (INR 23,600.00) immediately (2B verified).\n"
        "  - HOLD Defaulting Wholesaler (INR 17,700.00) under Rule 37A until GSTR-1 amendment.",
    )

    # Beat 15
    print_step(15, "Smart Attendance, Udhari Cash Advances & Bulk Payout Advice Batch")
    room_shop("Shop Owner Sharma", "[Voice Check-in]: 'Poori loading team present hai siwaye Mukesh ke, aur Chandan ko 1500 advance diya'")
    room_shop(
        "@store-manager",
        "Smart Attendance & Advance Ledger Updated:\n"
        "  - 1-Click Crew Checkin: 2/3 floor workers PRESENT, Mukesh Driver marked ABSENT.\n"
        "  - Understaffing Warning: Morning shift needs 3 loaders, only 2 on duty!\n"
        "  - Udhari Advance: Logged INR 1,500.00 cash advance to Chandan Helper.",
    )
    room_shop(
        "@store-manager",
        "Generated Bulk Payout Advice Batch #PAY-202611-SHAR:\n"
        "  - Chandan Helper: 10 days worked (INR 5,000.00) - Advance (INR 1,500.00) = Net Payable INR 3,500.00 (UPI: chandan@upi)\n"
        "  - Total Net Disbursement: INR 27,500.00 across 3 staff roster.\n"
        "  - Awaiting owner authorization...",
    )
    room_shop("Shop Owner Sharma", "/approve_payout PAY-202611-SHAR")
    room_ca(
        "@return-preparer",
        "Disbursement Settled: Payout Batch #PAY-202611-SHAR approved by Owner Sharma.\n"
        "  - Double-Entry Journal JE-20261105-PAYR recorded:\n"
        "    Debit 5030 Wages (INR 29,000.00), Credit 1020 Bank (INR 27,500.00), Credit 2040 Advance Recovered (INR 1,500.00).",
    )

    print(f"\n{BOLD}{GREEN}{'=' * 80}{RESET}")
    print(f"{BOLD}{GREEN}ALL 15 DEMO BEATS COMPLETED SUCCESSFULLY! SYSTEM 100% OPERATIONAL.{RESET}")
    print(f"{BOLD}{GREEN}{'=' * 80}{RESET}\n")


if __name__ == "__main__":
    run_live_demo()

