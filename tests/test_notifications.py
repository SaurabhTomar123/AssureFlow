import pytest
from src.db.session import SessionLocal
from src.notifications.alert_engine import (
    check_gst_deadline_alerts,
    check_low_stock_alerts,
    get_proactive_store_alerts,
)
from src.switch_bridge.webhook_handler import SwitchWebhookRouter


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_gst_deadline_alerts(db_session):
    alerts = check_gst_deadline_alerts("shop-sharma-kirana", db_session)
    assert isinstance(alerts, list)
    if alerts:
        a = alerts[0]
        assert "days_until_deadline" in a
        assert "itc_at_risk" in a
        assert a["type"] == "GST_DEADLINE_APPROACHING"


def test_low_stock_alerts(db_session):
    alerts = check_low_stock_alerts("shop-sharma-kirana", db_session)
    assert isinstance(alerts, list)
    if alerts:
        a = alerts[0]
        assert a["type"] == "INVENTORY_LOW_STOCK"
        assert "suggested_order" in a


def test_get_proactive_store_alerts(db_session):
    summary = get_proactive_store_alerts("shop-sharma-kirana", db_session)
    assert summary["shop_id"] == "shop-sharma-kirana"
    assert "total_active_alerts" in summary
    assert "status" in summary


def test_switch_alerts_command():
    router = SwitchWebhookRouter()
    events = router.handle_message(
        room_name="shop-sharma-kirana",
        user_name="Harsh Owner",
        text="/alerts",
    )
    assert len(events) == 1
    assert events[0]["sender"] == "follow-up"
    assert "Proactive Store & Compliance Alerts" in events[0]["text"]

