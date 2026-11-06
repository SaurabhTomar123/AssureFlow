import pytest
from src.db.session import SessionLocal
from src.accounts.ledger import classify_expense, get_accounts_book


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_classify_expense():
    assert classify_expense("Syska LED Bulb", "Apex Electronic") == "INVENTORY_PURCHASE"
    assert classify_expense("Commercial Kitchen Blender", "Maharashtra Goods") == "CAPITAL_ASSET"
    assert classify_expense("Shipping Cartons 12x10x8", "Craft Corrugated") == "OPERATING_EXPENSE"
    assert classify_expense("Tempo delivery charges", "Delhi Transport") == "LOGISTICS_FREIGHT"


def test_get_accounts_book_seeded_shop(db_session):
    book = get_accounts_book("shop-sharma-kirana", db_session)

    assert book["shop_id"] == "shop-sharma-kirana"
    assert book["entry_count"] >= 18
    assert book["total_cash_outflow"] > 0.0

    breakdown = book["breakdown"]
    assert breakdown["inventory_purchases"] > 0.0
    assert breakdown["capital_assets"] > 0.0
    assert breakdown["operating_expenses"] > 0.0

    assert len(book["entries"]) == book["entry_count"]

