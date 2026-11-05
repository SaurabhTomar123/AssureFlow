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

