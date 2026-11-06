import pytest
from src.db.session import SessionLocal
from src.db.models import Bill, InventoryItem, StockMovement
from src.inventory.service import (
    ensure_inventory_item,
    restock_inventory_from_bill,
    record_stock_out,
    get_inventory_catalog,
    get_low_stock_report,
)


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_ensure_inventory_item(db_session):
    item = ensure_inventory_item(
        shop_id="shop-sharma-kirana",
        name="Tata Salt 1kg Pack",
        cost_price=22.0,
        category="Grocery",
        unit="packets",
        reorder_level=15.0,
        db=db_session,
    )
    assert item.sku.startswith("SKU-TATA-SALT")
    assert item.reorder_level == 15.0
    assert item.cost_price == 22.0


def test_restock_from_bill(db_session):
    bill = db_session.query(Bill).filter(Bill.id == "BILL-001").first()
    assert bill is not None
    assert len(bill.items) == 2

    restock_log = restock_inventory_from_bill(bill.id, db_session)
    assert len(restock_log) == 2

    first_entry = restock_log[0]
    assert first_entry["added_quantity"] > 0
    assert first_entry["new_stock"] >= first_entry["added_quantity"]

    movements = (
        db_session.query(StockMovement)
        .filter(StockMovement.reference_bill_id == bill.id)
        .all()
    )
    assert len(movements) >= 2
    assert all(m.movement_type == "IN_PURCHASE" for m in movements)


def test_record_stock_out_and_low_stock(db_session):
    item = ensure_inventory_item(
        shop_id="shop-sharma-kirana",
        name="Fortune Sunflower Oil 1L",
        cost_price=120.0,
        reorder_level=20.0,
        db=db_session,
    )
    item.current_stock = 25.0
    db_session.commit()

    res = record_stock_out(
        shop_id="shop-sharma-kirana",
        sku=item.sku,
        quantity=10.0,
        reason="SALE",
        db=db_session,
    )
    assert res["new_stock"] == 15.0
    assert res["status"] == "LOW_STOCK"

    low_items = get_low_stock_report("shop-sharma-kirana", db_session)
    low_skus = [it["sku"] for it in low_items]
    assert item.sku in low_skus
