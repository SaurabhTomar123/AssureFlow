import hmac
import hashlib
import json
from fastapi.testclient import TestClient
from src.api.main import app
from src.config import settings
from src.db.session import SessionLocal
from src.db.models import Bill, InventoryItem
from src.switch_bridge.whatsapp_webhook import verify_meta_signature

client = TestClient(app)


def test_whatsapp_webhook_verification_success():
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": settings.WHATSAPP_VERIFY_TOKEN,
        "hub.challenge": "1155992288",
    }
    response = client.get("/api/whatsapp/webhook", params=params)
    assert response.status_code == 200
    assert response.text == "1155992288"


def test_whatsapp_webhook_verification_forbidden():
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "wrong_token",
        "hub.challenge": "1155992288",
    }
    response = client.get("/api/whatsapp/webhook", params=params)
    assert response.status_code == 403


def test_meta_signature_verification():
    raw_payload = b'{"test": "payload"}'
    secret = "test_meta_secret_key"
    settings.WHATSAPP_APP_SECRET = secret

    computed = hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()
    valid_header = f"sha256={computed}"

    assert verify_meta_signature(raw_payload, valid_header) is True
    assert verify_meta_signature(raw_payload, "sha256=invalidhash") is False
    assert verify_meta_signature(raw_payload, None) is False

    # Reset
    settings.WHATSAPP_APP_SECRET = None
    assert verify_meta_signature(raw_payload, None) is True


def test_whatsapp_interactive_button_approval():
    db = SessionLocal()
    try:
        bill = db.query(Bill).filter(Bill.id == "BILL-001").first()
        assert bill is not None
        bill.is_confirmed_by_owner = False
        bill.status = "pending_review"
        db.commit()

        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "919876543210",
                                        "type": "interactive",
                                        "interactive": {
                                            "button_reply": {
                                                "id": "approve_bill_BILL-001",
                                                "title": "Approve Bill",
                                            }
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        resp = client.post("/api/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "EVENT_RECEIVED"
        assert len(data["processed_actions"]) >= 1
        assert data["processed_actions"][0]["action"] == "bill_approved"

        # Verify bill updated in DB
        db.refresh(bill)
        assert bill.is_confirmed_by_owner is True
        assert bill.status == "approved"
    finally:
        db.close()


def test_whatsapp_text_natural_language_query():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "919876543210",
                                    "type": "text",
                                    "text": {"body": "stock check aashirvaad"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    resp = client.post("/api/whatsapp/webhook", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "EVENT_RECEIVED"
    actions = data["processed_actions"]
    assert len(actions) >= 1
    assert actions[0]["action"] == "text_query_processed"
    assert len(actions[0]["agent_replies"]) >= 1
    assert "stock" in actions[0]["agent_replies"][0]["text"].lower()
