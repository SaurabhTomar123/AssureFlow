import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.db.session import SessionLocal
from src.db.models import Shop, InventoryItem, Employee, AttendanceRecord
from src.voice.voice_transcriber import route_voice_intent, transcribe_audio_note

client = TestClient(app)


def test_voice_stock_delivery_intake():
    db = SessionLocal()
    try:
        shop = db.query(Shop).filter(Shop.id == "shop-sharma-kirana").first()
        assert shop is not None

        voice_text = "Bhai 12 bori Aashirvaad Atta delivery aayi hai"
        result = route_voice_intent(voice_text, shop.id, db)

        assert result["intent"] == "STOCK_DELIVERY"
        assert len(result["processed_items"]) >= 1
        assert "Aashirvaad Atta" in result["processed_items"][0]["name"]
        assert result["processed_items"][0]["quantity"] == 12.0

        # Check DB
        item = db.query(InventoryItem).filter(InventoryItem.name == "Aashirvaad Atta").first()
        assert item is not None
        assert item.current_stock >= 12.0
    finally:
        db.close()


def test_voice_staff_attendance():
    db = SessionLocal()
    try:
        shop = db.query(Shop).filter(Shop.id == "shop-sharma-kirana").first()
        assert shop is not None

        # Seed employee Ramesh if not exists
        emp = db.query(Employee).filter(Employee.shop_id == shop.id, Employee.name.like("%Ramesh%")).first()
        if not emp:
            emp = Employee(
                shop_id=shop.id,
                name="Ramesh Kumar",
                designation="Store Assistant",
                wage_type="MONTHLY",
                base_rate=14000.0,
            )
            db.add(emp)
            db.commit()

        voice_text = "Bhaiya aaj Ramesh duty pe hai, present mark kar do"
        result = route_voice_intent(voice_text, shop.id, db)

        assert result["intent"] == "STAFF_ATTENDANCE"
        assert len(result["attendance_records"]) >= 1
        assert any(r["employee_name"] == emp.name and r["status"] == "PRESENT" for r in result["attendance_records"])
    finally:
        db.close()


def test_voice_khata_query():
    db = SessionLocal()
    try:
        shop = db.query(Shop).filter(Shop.id == "shop-sharma-kirana").first()
        assert shop is not None

        voice_text = "Mera is mahine ka khata aur hisaab dikhao"
        result = route_voice_intent(voice_text, shop.id, db)

        assert result["intent"] == "GENERAL_QUERY"
        assert "khata" in result["reply_message"].lower() or "accounts" in result["reply_message"].lower() or "sharma" in result["reply_message"].lower()
    finally:
        db.close()


def test_voice_api_process_text_endpoint():
    shop_id = "shop-sharma-kirana"
    payload = {
        "shop_id": shop_id,
        "transcript": "Bhai 5 packet MDH Mirch delivery aayi hai",
    }
    response = client.post("/api/voice/process-text", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "STOCK_DELIVERY"
    assert len(data["processed_items"]) >= 1
