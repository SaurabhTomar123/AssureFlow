import pytest
from datetime import datetime, date, timedelta
from fastapi.testclient import TestClient
from src.api.main import app
from src.db.session import SessionLocal
from src.db.models import Shop, InventoryItem, StockMovement, ItemBatch, StockAdjustment
from src.inventory.service import (
    ensure_inventory_item,
    create_or_update_batch,
    get_fefo_expiry_report,
    generate_rtv_debit_note,
    get_dynamic_reorder_sheet,
    audit_physical_stock,
    check_supplier_price_opportunity,
)

client = TestClient(app)


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_fefo_expiry_and_rtv_debit_note(db_session):
    shop = Shop(name="Smart Kirana", gstin="27AABCU9603R1ZM", state_code="27")
    db_session.add(shop)
    db_session.commit()

    item = ensure_inventory_item(
        shop_id=shop.id,
        name="Amul Butter 500g",
        cost_price=240.0,
        category="Dairy",
        db=db_session,
    )
    item.current_stock = 30.0
    db_session.commit()

    today = date.today()
    past_date = (today - timedelta(days=5)).isoformat()
    critical_date = (today + timedelta(days=10)).isoformat()
    warning_date = (today + timedelta(days=25)).isoformat()
    healthy_date = (today + timedelta(days=90)).isoformat()

    b_expired = create_or_update_batch(
        shop_id=shop.id,
        sku=item.sku,
        batch_number="BAT-EXP-001",
        quantity=5.0,
        expiry_date=past_date,
        cost_price=240.0,
        db=db_session,
    )
    b_critical = create_or_update_batch(
        shop_id=shop.id,
        sku=item.sku,
        batch_number="BAT-CRIT-002",
        quantity=10.0,
        expiry_date=critical_date,
        cost_price=240.0,
        db=db_session,
    )
    b_warning = create_or_update_batch(
        shop_id=shop.id,
        sku=item.sku,
        batch_number="BAT-WARN-003",
        quantity=5.0,
        expiry_date=warning_date,
        cost_price=240.0,
        db=db_session,
    )
    b_healthy = create_or_update_batch(
        shop_id=shop.id,
        sku=item.sku,
        batch_number="BAT-HLTH-004",
        quantity=10.0,
        expiry_date=healthy_date,
        cost_price=240.0,
        db=db_session,
    )

    report = get_fefo_expiry_report(shop_id=shop.id, db=db_session)
    assert report["total_batches"] == 4
    assert report["expired_batches"] == 1
    assert report["critical_batches"] == 1
    assert report["warning_batches"] == 1
    assert report["healthy_batches"] == 1
    assert report["total_value_at_risk"] == round(5.0 * 240.0 + 10.0 * 240.0, 2)

    debit_note = generate_rtv_debit_note(
        shop_id=shop.id,
        batch_id=b_expired.id,
        reason="EXPIRED_SHELF_LIFE",
        db=db_session,
    )
    assert debit_note is not None
    assert debit_note["status"] == "ISSUED"
    assert debit_note["returned_quantity"] == 5.0
    assert debit_note["taxable_claim"] == 1200.0
    assert debit_note["total_debit_claim"] == round(1200.0 * 1.18, 2)
    assert item.current_stock == 25.0


def test_dynamic_run_rate_reordering(db_session):
    shop = Shop(name="Sharma Dynamic Store", gstin="07AABCS1429B1ZB", state_code="07")
    db_session.add(shop)
    db_session.commit()

    item = ensure_inventory_item(
        shop_id=shop.id,
        name="Tata Salt 1kg",
        cost_price=22.0,
        category="Grocery",
        reorder_level=15.0,
        db=db_session,
    )
    item.current_stock = 8.0
    item.lead_time_days = 3
    db_session.commit()

    movement = StockMovement(
        item_id=item.id,
        shop_id=shop.id,
        movement_type="OUT_SALE",
        quantity=60.0,
        notes="30-day cumulative retail sales",
        created_at=datetime.utcnow() - timedelta(days=10),
    )
    db_session.add(movement)
    db_session.commit()

    reorder_sheet = get_dynamic_reorder_sheet(shop_id=shop.id, db=db_session)
    assert len(reorder_sheet) >= 1
    target = next((r for r in reorder_sheet if r["sku"] == item.sku), None)
    assert target is not None
    assert target["average_daily_velocity"] == 2.0
    assert target["days_inventory_remaining"] == 4.0
    assert target["urgency"] == "URGENT"
    assert target["suggested_po_quantity"] >= 22.0


def test_inventory_shrinkage_audit(db_session):
    shop = Shop(name="Audit Grocery", gstin="27AABCU9603R1Z1", state_code="27")
    db_session.add(shop)
    db_session.commit()

    item = ensure_inventory_item(
        shop_id=shop.id,
        name="Basmati Rice 5kg",
        cost_price=450.0,
        db=db_session,
    )
    item.current_stock = 50.0
    db_session.commit()

    audit_res = audit_physical_stock(
        shop_id=shop.id,
        sku=item.sku,
        physical_count=47.0,
        audited_by="Ramesh Manager",
        reason="COUNTER_SHORTAGE",
        db=db_session,
    )
    assert audit_res is not None
    assert audit_res["discrepancy"] == -3.0
    assert audit_res["discrepancy_pct"] == 6.0
    assert audit_res["discrepancy_value"] == 1350.0
    assert audit_res["audit_status"] == "SHRINKAGE_WARNING"
    assert audit_res["adjusted_stock"] == 47.0

    severe_res = audit_physical_stock(
        shop_id=shop.id,
        sku=item.sku,
        physical_count=35.0,
        audited_by="Surprise Audit CA",
        reason="DAMAGED_AND_THEFT",
        db=db_session,
    )
    assert severe_res["audit_status"] == "SEVERE_LEAKAGE"


def test_supplier_price_opportunity(db_session):
    shop = Shop(name="Bargain Mart", gstin="27AABCU9603R1Z2", state_code="27")
    db_session.add(shop)
    db_session.commit()

    item = ensure_inventory_item(
        shop_id=shop.id,
        name="Fortune Sunflower Oil 1L",
        cost_price=130.0,
        db=db_session,
    )
    item.min_cost_seen = 130.0
    db_session.commit()

    res_same = check_supplier_price_opportunity(
        shop_id=shop.id,
        sku=item.sku,
        latest_cost=130.0,
        supplier_name="Distributor A",
        db=db_session,
    )
    assert res_same["opportunity_detected"] is False

    res_expensive = check_supplier_price_opportunity(
        shop_id=shop.id,
        sku=item.sku,
        latest_cost=150.0,
        supplier_name="Distributor B",
        db=db_session,
    )
    assert res_expensive["opportunity_detected"] is True
    assert res_expensive["potential_unit_savings"] == 20.0
    assert res_expensive["percentage_savings"] == 13.3


def test_smart_inventory_api_endpoints(db_session):
    shop = Shop(name="API Smart Kirana", gstin="27AABCU9603R1Z3", state_code="27")
    db_session.add(shop)
    db_session.commit()

    item = ensure_inventory_item(
        shop_id=shop.id,
        name="Parle-G Gold 1kg",
        cost_price=110.0,
        db=db_session,
    )
    item.current_stock = 20.0
    db_session.commit()

    today_str = date.today().isoformat()
    resp_batch = client.post(
        f"/api/inventory/{shop.id}/batch",
        json={
            "sku": item.sku,
            "batch_number": "BAT-PG-01",
            "quantity": 10.0,
            "expiry_date": today_str,
            "cost_price": 110.0,
        },
    )
    assert resp_batch.status_code == 200
    batch_data = resp_batch.json()
    batch_id = batch_data["batch_id"]

    resp_fefo = client.get(f"/api/inventory/{shop.id}/fefo-report")
    assert resp_fefo.status_code == 200
    assert resp_fefo.json()["total_batches"] >= 1

    resp_reorder = client.get(f"/api/inventory/{shop.id}/dynamic-reorder")
    assert resp_reorder.status_code == 200

    resp_audit = client.post(
        f"/api/inventory/{shop.id}/audit-stock",
        json={"sku": item.sku, "physical_count": 18.0, "reason": "EXPIRY_SPOILAGE"},
    )
    assert resp_audit.status_code == 200
    assert resp_audit.json()["discrepancy"] == -2.0

    resp_opp = client.get(
        f"/api/inventory/{shop.id}/price-opportunity",
        params={"sku": item.sku, "latest_cost": 135.0, "supplier_name": "New Wholesaler"},
    )
    assert resp_opp.status_code == 200
    assert resp_opp.json()["opportunity_detected"] is True

    resp_rtv = client.post(
        f"/api/inventory/{shop.id}/rtv-debit-note",
        json={"batch_id": batch_id, "reason": "SPOILED_PACKET"},
    )
    assert resp_rtv.status_code == 200
    assert resp_rtv.json()["status"] == "ISSUED"
