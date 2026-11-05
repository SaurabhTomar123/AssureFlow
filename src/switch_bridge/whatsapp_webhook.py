import hmac
import hashlib
import json
from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, Response, HTTPException, status, Query, Depends
from sqlalchemy.orm import Session
from src.config import settings
from src.db.session import get_db
from src.db.models import Shop, Bill, ComplianceIssueModel
from src.inventory.service import restock_inventory_from_bill
from src.switch_bridge.webhook_handler import SwitchWebhookRouter

router = APIRouter(prefix="/api/whatsapp", tags=["Meta WhatsApp Cloud API Bridge"])
switch_router = SwitchWebhookRouter()


def verify_meta_signature(raw_body: bytes, signature_header: Optional[str]) -> bool:
    if not settings.WHATSAPP_APP_SECRET:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected_hash = signature_header.split("sha256=")[1]
    computed_hash = hmac.new(
        settings.WHATSAPP_APP_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_hash, computed_hash)


@router.get("/webhook")
def verify_whatsapp_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        return Response(content=hub_challenge or "", media_type="text/plain", status_code=200)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification token mismatch")


@router.post("/webhook")
async def receive_whatsapp_event(request: Request, db: Session = Depends(get_db)):
    body_bytes = await request.body()
    sig_header = request.headers.get("X-Hub-Signature-256")

    if not verify_meta_signature(body_bytes, sig_header):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid WhatsApp webhook HMAC-SHA256 signature",
        )

    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    results = []
    entries = payload.get("entry", [])
    for entry in entries:
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages", [])
            for msg in messages:
                from_number = msg.get("from", "")
                msg_type = msg.get("type", "text")

                shop = (
                    db.query(Shop)
                    .filter(Shop.telegram_chat_id.like(f"%{from_number}%"))
                    .first()
                )
                if not shop:
                    shop = db.query(Shop).first()
                shop_id = shop.id if shop else "shop-sharma-kirana"

                # Case 1: Interactive Button Quick Reply
                if msg_type == "interactive":
                    interactive = msg.get("interactive", {})
                    btn_id = interactive.get("button_reply", {}).get("id", "")
                    if btn_id.startswith("approve_bill_"):
                        bill_id = btn_id.replace("approve_bill_", "")
                        bill = db.query(Bill).filter(Bill.id == bill_id).first()
                        if bill:
                            bill.is_confirmed_by_owner = True
                            bill.status = "approved"
                            restock_inventory_from_bill(bill_id, db)
                            db.commit()
                            results.append({
                                "action": "bill_approved",
                                "bill_id": bill_id,
                                "message": f"Bill {bill.bill_number or bill_id} approved and stock restocked successfully.",
                            })
                    elif btn_id.startswith("reject_bill_"):
                        bill_id = btn_id.replace("reject_bill_", "")
                        bill = db.query(Bill).filter(Bill.id == bill_id).first()
                        if bill:
                            bill.status = "rejected"
                            db.commit()
                            results.append({
                                "action": "bill_rejected",
                                "bill_id": bill_id,
                                "message": f"Bill {bill.bill_number or bill_id} marked as rejected.",
                            })

                # Case 2: Document / Image Receipt Upload
                elif msg_type in ["image", "document"]:
                    caption = msg.get(msg_type, {}).get("caption", "")
                    doc_path = msg.get(msg_type, {}).get("file_path") or "synthetic_data/bills_pdf/bill_01_clean_kirana_5pct.pdf"
                    dispatch_res = switch_router.handle_message(
                        room_name=shop_id,
                        user_name=f"wa_{from_number}",
                        text=caption or "receipt upload",
                        attachment_path=doc_path,
                    )
                    results.append({
                        "action": "document_processed",
                        "shop_id": shop_id,
                        "agent_replies": dispatch_res,
                    })

                # Case 3: Natural Language Query or Command
                elif msg_type == "text":
                    text_body = msg.get("text", {}).get("body", "")
                    dispatch_res = switch_router.handle_message(
                        room_name=shop_id,
                        user_name=f"wa_{from_number}",
                        text=text_body,
                    )
                    results.append({
                        "action": "text_query_processed",
                        "shop_id": shop_id,
                        "agent_replies": dispatch_res,
                    })

    return {
        "status": "EVENT_RECEIVED",
        "processed_actions": results,
    }
