from pathlib import Path
from src.switch_bridge.webhook_handler import SwitchWebhookRouter
from src.db.session import SessionLocal
from src.db.models import Bill

BASE_DIR = Path(__file__).resolve().parent.parent
PDF_DIR = BASE_DIR / "synthetic_data" / "bills_pdf"


def test_switch_shop_intake():
    router = SwitchWebhookRouter()
    pdf_path = str(PDF_DIR / "bill_01_clean_kirana_5pct.pdf")

    events = router.handle_message(
        room_name="shop-sharma-kirana",
        user_name="Harsh",
        text="Aap yeh bill check kar lo",
        attachment_path=pdf_path,
    )
    assert len(events) >= 1
    assert any(e["room"] == "shop-sharma-kirana" and "Bill Prapt Hua" in e["text"] for e in events)


def test_switch_serious_issue_routed_to_ca_room():
    router = SwitchWebhookRouter()
    pdf_path = str(PDF_DIR / "bill_13_wrong_tax_type_interstate_charged_cgst.pdf")

    events = router.handle_message(
        room_name="shop-sharma-kirana",
        user_name="Harsh",
        text="New tile invoice received",
        attachment_path=pdf_path,
    )
    ca_events = [e for e in events if e["room"] == "ca-office"]
    assert len(ca_events) >= 1
    assert "CA Action Required" in ca_events[0]["text"]
    assert "WRONG_TAX_TYPE" in ca_events[0]["text"]


def test_switch_ca_commands():
    router = SwitchWebhookRouter()
    db = SessionLocal()
    bill = db.query(Bill).filter(Bill.shop_id == "shop-sharma-kirana").first()
    bill_id = bill.id
    db.close()

    events_dash = router.handle_message(
        room_name="ca-office",
        user_name="CA Harsh",
        text="/dashboard",
    )
    assert len(events_dash) == 1
    assert "Monthly Multi-Shop CA Dashboard:" in events_dash[0]["text"]

    events_summary = router.handle_message(
        room_name="ca-office",
        user_name="CA Harsh",
        text="/summary shop-sharma-kirana",
    )
    assert len(events_summary) == 1
    assert "Month-End GSTR Compliance Report" in events_summary[0]["text"]

    events_ask = router.handle_message(
        room_name="ca-office",
        user_name="CA Harsh",
        text=f"/ask_supplier {bill_id}",
    )
    assert len(events_ask) == 1
    assert "Supplier Inquiry Notice Drafted" in events_ask[0]["text"]
