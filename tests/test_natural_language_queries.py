from src.switch_bridge.webhook_handler import SwitchWebhookRouter


def test_nl_query_stock_intent():
    router = SwitchWebhookRouter()
    events = router.handle_message(
        room_name="shop-sharma-kirana",
        user_name="Shopkeeper",
        text="Aaj ka stock kaisa hai aur kitna maal bacha hai?",
    )
    assert len(events) == 1
    assert events[0]["sender"] == "store-manager"
    assert "Stock" in events[0]["text"] or "Inventory" in events[0]["text"]


def test_nl_query_reorder_intent():
    router = SwitchWebhookRouter()
    events = router.handle_message(
        room_name="shop-sharma-kirana",
        user_name="Shopkeeper",
        text="Kaun sa maal khatam ho gaya hai, order list dikhao",
    )
    assert len(events) == 1
    assert events[0]["sender"] == "store-manager"
    assert "Reorder" in events[0]["text"] or "Procurement" in events[0]["text"] or "stock purn" in events[0]["text"]


def test_nl_query_khata_intent():
    router = SwitchWebhookRouter()
    events = router.handle_message(
        room_name="shop-sharma-kirana",
        user_name="Shopkeeper",
        text="Mera hisaab aur khata dikhao",
    )
    assert len(events) == 1
    assert events[0]["sender"] == "junior-ca"
    assert "Khata" in events[0]["text"] or "Accounts" in events[0]["text"]


def test_nl_query_tax_savings_intent():
    router = SwitchWebhookRouter()
    events = router.handle_message(
        room_name="shop-sharma-kirana",
        user_name="Shopkeeper",
        text="Dukan ka tax kaise bacha sakte hain?",
    )
    assert len(events) == 1
    assert events[0]["sender"] == "junior-ca"
    assert "Section 32" in events[0]["text"] or "Tax" in events[0]["text"]

