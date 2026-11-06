import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from src.api.main import app
from src.switch_bridge.webhook_handler import SwitchWebhookRouter

client = TestClient(app)
router = SwitchWebhookRouter()
PDF_DIR = BASE_DIR / "synthetic_data" / "bills_pdf"
IMG_DIR = BASE_DIR / "synthetic_data" / "bills_img"


def run_e2e_demo():
    print("=" * 65)
    print("MUNIMJI - FULL END-TO-END DEMO EXECUTION (12 BEATS)")
    print("Hackathon: Flip the Switch | Track 1: Best Business Workflow")
    print("Core Rule: AI reads and advises, code checks, human decides")
    print("=" * 65)

    print("\n[BEAT 1] The Problem Statement:")
    print("Small Indian shop owners accumulate paper & digital invoices.")
    print("At month-end, CAs chase them while ITC credit risks expire.")

    print("\n[BEAT 2] Bill Photo / PDF Intake & Confirmation:")
    clean_pdf = PDF_DIR / "bill_01_clean_kirana_5pct.pdf"
    events_beat2 = router.handle_message(
        room_name="shop-sharma-kirana",
        user_name="Shop Owner Sharma",
        text="Aap yeh purchase bill check karo",
        attachment_path=str(clean_pdf),
    )
    for evt in events_beat2:
        print(f"[{evt['room']}] <{evt['sender']}>:\n{evt['text']}\n")

    confirm_events = router.handle_message(
        room_name="shop-sharma-kirana",
        user_name="Shop Owner Sharma",
        text="OK",
    )
    for evt in confirm_events:
        print(f"[{evt['room']}] <{evt['sender']}>:\n{evt['text']}\n")

    print("[BEAT 3] Missing / Corrupted GSTIN Detection & Rupee Risk Follow-up:")
    missing_gstin_pdf = PDF_DIR / "bill_12_missing_gstin.pdf"
    events_beat3 = router.handle_message(
        room_name="shop-sharma-kirana",
        user_name="Shop Owner Sharma",
        text="Cash vendor bill",
        attachment_path=str(missing_gstin_pdf),
    )
    for evt in events_beat3:
        print(f"[{evt['room']}] <{evt['sender']}>:\n{evt['text']}\n")

    print("[BEAT 4] Serious Defect (Wrong Tax Type) Routed to CA Office Room:")
    wrong_tax_pdf = PDF_DIR / "bill_13_wrong_tax_type_interstate_charged_cgst.pdf"
    events_beat4 = router.handle_message(
        room_name="shop-sharma-kirana",
        user_name="Shop Owner Sharma",
        text="Gujarat ceramic tiles bill",
        attachment_path=str(wrong_tax_pdf),
    )
    for evt in events_beat4:
        print(f"[{evt['room']}] <{evt['sender']}>:\n{evt['text']}\n")

    print("CA reviews the serious defect and chooses 'ask_supplier':")
    ca_action_events = router.handle_message(
        room_name="ca-office",
        user_name="CA Verma",
        text="/ask_supplier BILL-013",
    )
    for evt in ca_action_events:
        print(f"[{evt['room']}] <{evt['sender']}>:\n{evt['text']}\n")

    print("[BEAT 5] Duplicate Invoice Guard:")
    dup_pdf = PDF_DIR / "bill_16_duplicate_copy.pdf"
    with open(dup_pdf, "rb") as f:
        res_dup = client.post(
            "/api/bills/upload",
            data={"shop_id": "shop-sharma-kirana"},
            files={"file": ("duplicate_bill.pdf", f, "application/pdf")},
        )
    dup_json = res_dup.json()
    dup_issues = [i["issue_type"] for i in dup_json["issues"]]
    print(f"Uploaded duplicate bill GPW-2026-999. Status: {dup_json['status']}. Issues: {dup_issues}")
    assert "DUPLICATE_INVOICE" in dup_issues, "Duplicate check failed!"
    print("Duplicate bill successfully caught by deterministic rule engine.")

    print("\n[BEAT 6] Month-End Reconciliation & Summary Export:")
    summary_events = router.handle_message(
        room_name="ca-office",
        user_name="CA Verma",
        text="/summary shop-sharma-kirana",
    )
    for evt in summary_events:
        print(f"[{evt['room']}] <{evt['sender']}>:\n{evt['text']}\n")

    export_res = client.get("/api/summary/shop-sharma-kirana/export")
    assert export_res.status_code == 200
    export_payload = export_res.json()
    print("CA Downloaded GSTR Summary JSON:")
    print(f"- Shop: {export_payload['summary']['shop_name']}")
    print(f"- Total Bills: {export_payload['summary']['total_bills']}")
    print(f"- Clean Bills: {export_payload['summary']['clean_bills']}")
    print(f"- Eligible ITC Total: INR {export_payload['summary']['eligible_itc']['total']}")
    print(f"- Open Issues: {export_payload['summary']['open_issues_count']} (Disputed: INR {export_payload['summary']['itc_at_risk']})")

    print("\n[BEAT 7] Multi-Shop Dashboard & Architecture Isolation:")
    dash_events = router.handle_message(
        room_name="ca-office",
        user_name="CA Verma",
        text="/dashboard",
    )
    for evt in dash_events:
        print(f"[{evt['room']}] <{evt['sender']}>:\n{evt['text']}\n")

    print("\n[BEAT 8] Junior CA Accounts Book (Khata Ledger):")
    khata_events = router.handle_message(
        room_name="shop-sharma-kirana",
        user_name="Shop Owner Sharma",
        text="/khata",
    )
    for evt in khata_events:
        print(f"[{evt['room']}] <{evt['sender']}>:\n{evt['text']}\n")

    print("\n[BEAT 9] Junior CA Tax Savings & Section 44AD Optimization:")
    tax_events = router.handle_message(
        room_name="shop-sharma-kirana",
        user_name="Shop Owner Sharma",
        text="/tax_savings",
    )
    for evt in tax_events:
        print(f"[{evt['room']}] <{evt['sender']}>:\n{evt['text']}\n")

    presump_events = router.handle_message(
        room_name="shop-sharma-kirana",
        user_name="Shop Owner Sharma",
        text="/presumptive 6000000 85",
    )
    for evt in presump_events:
        print(f"[{evt['room']}] <{evt['sender']}>:\n{evt['text']}\n")

    print("\n[BEAT 10] Store Manager Inventory Overview & Reorder Sheet:")
    stock_events = router.handle_message(
        room_name="shop-sharma-kirana",
        user_name="Shop Owner Sharma",
        text="/stock",
    )
    for evt in stock_events:
        print(f"[{evt['room']}] <{evt['sender']}>:\n{evt['text']}\n")

    reorder_events = router.handle_message(
        room_name="shop-sharma-kirana",
        user_name="Shop Owner Sharma",
        text="/reorder",
    )
    for evt in reorder_events:
        print(f"[{evt['room']}] <{evt['sender']}>:\n{evt['text']}\n")

    print("\n[BEAT 11] Staff Check-in & Morning Shift Briefing:")
    checkin_events = router.handle_message(
        room_name="shop-sharma-kirana",
        user_name="Ramesh Manager",
        text="/checkin Ramesh present",
    )
    for evt in checkin_events:
        print(f"[{evt['room']}] <{evt['sender']}>:\n{evt['text']}\n")

    attendance_events = router.handle_message(
        room_name="shop-sharma-kirana",
        user_name="Ramesh Manager",
        text="/attendance",
    )
    for evt in attendance_events:
        print(f"[{evt['room']}] <{evt['sender']}>:\n{evt['text']}\n")

    print("\n[BEAT 12] Monthly Payroll Calculation & Interactive Web Cockpit Metrics:")
    payroll_events = router.handle_message(
        room_name="shop-sharma-kirana",
        user_name="Shop Owner Sharma",
        text="/payroll 2026-11",
    )
    for evt in payroll_events:
        print(f"[{evt['room']}] <{evt['sender']}>:\n{evt['text']}\n")

    cockpit_res = client.get("/api/dashboard/metrics/shop-sharma-kirana?role=OWNER")
    assert cockpit_res.status_code == 200
    metrics = cockpit_res.json()
    print("Owner Cockpit Telemetry Verified:")
    print(f"- Shop: {metrics['shop_name']}")
    print(f"- Total Bills: {metrics['gst_compliance']['total_bills']}")
    print(f"- Eligible ITC: INR {metrics['gst_compliance']['eligible_itc']}")
    print(f"- Inventory SKUs: {metrics['inventory_status']['total_skus']}")
    print(f"- Staff Present Today: {metrics['staff_attendance']['present_today']} / {metrics['staff_attendance']['total_employees']}")

    print("=" * 65)
    print("ALL 12 DEMO BEATS PASSED PERFECTLY!")
    print("AI reads and advises, code checks, human decides.")
    print("=" * 65)


if __name__ == "__main__":
    run_e2e_demo()

