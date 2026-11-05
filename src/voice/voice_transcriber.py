import re
from typing import Dict, Any, List
from datetime import date
from sqlalchemy.orm import Session
from src.db.models import Shop, Employee, InventoryItem, StockMovement
from src.inventory.service import ensure_inventory_item
from src.staff.service import mark_attendance
from src.switch_bridge.webhook_handler import SwitchWebhookRouter

switch_router = SwitchWebhookRouter()


def transcribe_audio_note(audio_bytes: bytes = b"", filename: str = "voice_note.ogg") -> str:
    # In production, invokes Wispr Flow / Gemini Speech-to-Text API
    # Returns transcribed natural language in Hindi or English
    return "Bhai 10 bori Aashirvaad Atta aur 5 packet MDH Mirch delivery aayi hai"


def route_voice_intent(transcript: str, shop_id: str, db: Session) -> Dict[str, Any]:
    text_lower = (transcript or "").lower()
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise ValueError(f"Shop with id {shop_id} not found")

    # Intent 1: Stock delivery intake via voice
    if any(k in text_lower for k in ["delivery aayi", "stock add", "bori", "peti", "dabbe", "packet", "maal aaya"]):
        items_detected = []

        # Regex for quantity + item
        qty_matches = re.findall(r"(\d+)\s*(?:bori|peti|dabbe|packet|units?|kg)?\s*([a-zA-Z\s]{3,25})", transcript, re.IGNORECASE)
        for qty_str, raw_item_name in qty_matches:
            tokens = [w for w in raw_item_name.strip().split() if w.lower() not in ["delivery", "aayi", "hai", "aur", "bori", "peti", "dabbe", "packet"]]
            if not tokens:
                continue
            cleaned_name = " ".join(tokens).title()
            qty = float(qty_str)
            item = ensure_inventory_item(
                shop_id=shop_id,
                name=cleaned_name,
                category="Groceries",
                db=db,
            )
            item.current_stock += qty
            movement = StockMovement(
                item_id=item.id,
                shop_id=shop_id,
                movement_type="IN_VOICE_DELIVERY",
                quantity=qty,
                notes=f"Voice delivery note: '{transcript}'",
            )
            db.add(movement)
            items_detected.append({"name": cleaned_name, "quantity": qty, "current_stock": item.current_stock})

        db.commit()
        return {
            "intent": "STOCK_DELIVERY",
            "transcript": transcript,
            "processed_items": items_detected,
            "agent": "store-manager",
            "reply_message": (
                f"Voice Delivery Processed: Restocked {len(items_detected)} catalog items in inventory.\n"
                + "\n".join([f"- {it['name']}: +{it['quantity']} units (New Total: {it['current_stock']})" for it in items_detected])
            ),
        }

    # Intent 2: Staff attendance via voice
    if any(k in text_lower for k in ["duty", "present", "absent", "chutti", "attendance", "aaj"]):
        employees = db.query(Employee).filter(Employee.shop_id == shop_id).all()
        marked = []
        today_str = date.today().isoformat()

        for emp in employees:
            first_name = emp.name.split()[0].lower()
            if first_name in text_lower:
                status = "ABSENT" if any(w in text_lower for w in ["chutti", "absent", "nahi aaya"]) else "PRESENT"
                record = mark_attendance(
                    shop_id=shop_id,
                    employee_id=emp.id,
                    date=today_str,
                    status=status,
                    db=db,
                )
                marked.append({"employee_name": emp.name, "status": status})

        return {
            "intent": "STAFF_ATTENDANCE",
            "transcript": transcript,
            "attendance_records": marked,
            "agent": "store-manager",
            "reply_message": (
                f"Voice Attendance Logged for {today_str}:\n"
                + "\n".join([f"- {m['employee_name']}: {m['status']}" for m in marked])
            ),
        }

    # Intent 3: General conversational or tax/khata question
    dispatch = switch_router.handle_message(
        room_name=shop_id,
        user_name="voice_merchant",
        text=transcript,
    )
    return {
        "intent": "GENERAL_QUERY",
        "transcript": transcript,
        "agent": "junior-ca",
        "agent_replies": dispatch,
        "reply_message": dispatch[0]["text"] if dispatch else "Voice query processed.",
    }
