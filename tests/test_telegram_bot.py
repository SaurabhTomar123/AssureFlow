from pathlib import Path
from src.switch_bridge.telegram_bot import TelegramBotRunner

BASE_DIR = Path(__file__).resolve().parent.parent
PDF_DIR = BASE_DIR / "synthetic_data" / "bills_pdf"


def test_telegram_bot_unconfigured():
    bot = TelegramBotRunner(token=None)
    assert bot.is_configured() is False
    assert bot.send_message(123456, "Hello Test") is True


def test_telegram_bot_resolve_room():
    bot = TelegramBotRunner(token="mock_token_123456789")
    room_shop = bot.resolve_room(chat_id="-1001234567891", chat_title="Sharma Kirana")
    assert room_shop == "shop-sharma-kirana"

    room_ca = bot.resolve_room(chat_id="9999", chat_title="CA Central Office")
    assert room_ca == "ca-office"


def test_telegram_bot_process_start_command():
    bot = TelegramBotRunner(token=None)
    update = {
        "update_id": 101,
        "message": {
            "chat": {"id": 123456, "title": "Sharma Kirana"},
            "from": {"first_name": "Harsh"},
            "text": "/start",
        },
    }
    events = bot.process_update(update)
    assert len(events) == 1
    assert "MunimJi" in events[0]["text"]
    assert "/khata" in events[0]["text"]


def test_telegram_bot_process_khata_command():
    bot = TelegramBotRunner(token=None)
    update = {
        "update_id": 102,
        "message": {
            "chat": {"id": -1001234567891, "title": "Sharma Kirana"},
            "from": {"first_name": "Harsh"},
            "text": "/khata",
        },
    }
    events = bot.process_update(update)
    assert len(events) >= 1
    assert any("Monthly Accounts Book" in e["text"] for e in events)


def test_telegram_bot_process_tax_savings_command():
    bot = TelegramBotRunner(token=None)
    update = {
        "update_id": 103,
        "message": {
            "chat": {"id": -1001234567891, "title": "Sharma Kirana"},
            "from": {"first_name": "Harsh"},
            "text": "/tax_savings",
        },
    }
    events = bot.process_update(update)
    assert len(events) >= 1
    assert any("Section 32" in e["text"] for e in events)


def test_telegram_bot_process_voice_message():
    bot = TelegramBotRunner(token=None)
    update = {
        "update_id": 104,
        "message": {
            "chat": {"id": -1001234567891, "title": "Sharma Kirana"},
            "from": {"first_name": "Harsh"},
            "voice": {"file_id": "mock_voice_file_123", "mime_type": "audio/ogg"},
            "caption": "Bhai 10 bori Aashirvaad Atta delivery aayi hai",
        },
    }
    events = bot.process_update(update)
    assert len(events) >= 1
    assert events[0]["sender"] == "store-manager"
    assert "Voice Delivery Processed" in events[0]["text"]


def test_telegram_bot_process_voice_advance():
    bot = TelegramBotRunner(token=None)
    update = {
        "update_id": 105,
        "message": {
            "chat": {"id": -1001234567891, "title": "Sharma Kirana"},
            "from": {"first_name": "Harsh"},
            "voice": {"file_id": "mock_voice_advance_456", "mime_type": "audio/ogg"},
            "caption": "Chandan ko 1500 advance diya",
        },
    }
    events = bot.process_update(update)
    assert len(events) >= 1
    assert events[0]["sender"] == "store-manager"
    assert "Udhari Advance Logged" in events[0]["text"]


def test_telegram_bot_process_financials_and_runway():
    bot = TelegramBotRunner(token=None)
    
    # Financials
    update_fin = {
        "update_id": 106,
        "message": {
            "chat": {"id": -1001234567891, "title": "Sharma Kirana"},
            "from": {"first_name": "Harsh"},
            "text": "/financials",
        },
    }
    ev_fin = bot.process_update(update_fin)
    assert len(ev_fin) >= 1
    assert any("Trial Balance" in e["text"] for e in ev_fin)

    # Runway
    update_run = {
        "update_id": 107,
        "message": {
            "chat": {"id": -1001234567891, "title": "Sharma Kirana"},
            "from": {"first_name": "Harsh"},
            "text": "/runway",
        },
    }
    ev_run = bot.process_update(update_run)
    assert len(ev_run) >= 1
    assert any("Liquidity Status" in e["text"] for e in ev_run)


def test_telegram_bot_process_fefo_and_operations():
    bot = TelegramBotRunner(token=None)

    # FEFO check
    update_fefo = {
        "update_id": 108,
        "message": {
            "chat": {"id": -1001234567891, "title": "Sharma Kirana"},
            "from": {"first_name": "Harsh"},
            "text": "/fefo_expiry_check",
        },
    }
    ev_fefo = bot.process_update(update_fefo)
    assert len(ev_fefo) >= 1
    assert any("FEFO Shelf-Life Horizon Report" in e["text"] for e in ev_fefo)

    # Crew checkin
    update_crew = {
        "update_id": 109,
        "message": {
            "chat": {"id": -1001234567891, "title": "Sharma Kirana"},
            "from": {"first_name": "Harsh"},
            "text": "/crew_checkin",
        },
    }
    ev_crew = bot.process_update(update_crew)
    assert len(ev_crew) >= 1
    assert any("1-Click Crew Checkin Complete" in e["text"] for e in ev_crew)


def test_telegram_bot_process_ca_priority_queue():
    bot = TelegramBotRunner(token=None)
    update_pq = {
        "update_id": 110,
        "message": {
            "chat": {"id": 9999, "title": "CA Central Office"},
            "from": {"first_name": "Mehta"},
            "text": "/priority_queue",
        },
    }
    ev_pq = bot.process_update(update_pq)
    assert len(ev_pq) >= 1
    assert any("Vendor Payment Priority Queue" in e["text"] for e in ev_pq)

