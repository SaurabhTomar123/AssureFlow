import pytest
from src.db.session import SessionLocal
from src.db.models import Shop, Bill, BillItem, ComplianceIssueModel


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_shops_seeded(db_session):
    shops = db_session.query(Shop).all()
    assert len(shops) >= 2
    shop_ids = [s.id for s in shops]
    assert "shop-sharma-kirana" in shop_ids
    assert "shop-gupta-electronics" in shop_ids


def test_bills_and_relationships(db_session):
    shop = db_session.query(Shop).filter(Shop.id == "shop-sharma-kirana").first()
    assert shop is not None
    assert len(shop.bills) >= 18

    clean_bill = db_session.query(Bill).filter(Bill.id == "BILL-001").first()
    assert clean_bill is not None
    assert clean_bill.status == "clean"
    assert len(clean_bill.items) == 2
    assert len(clean_bill.issues) == 0

    wrong_tax_bill = db_session.query(Bill).filter(Bill.id == "BILL-013").first()
    assert wrong_tax_bill is not None
    assert len(wrong_tax_bill.issues) >= 1
    issue = wrong_tax_bill.issues[0]
    assert issue.issue_type == "WRONG_TAX_TYPE"
    assert issue.severity == "serious"
    assert issue.supplier_inquiry_draft is not None


def test_issues_filtering(db_session):
    serious_issues = (
        db_session.query(ComplianceIssueModel)
        .filter(ComplianceIssueModel.severity == "serious")
        .all()
    )
    simple_issues = (
        db_session.query(ComplianceIssueModel)
        .filter(ComplianceIssueModel.severity == "simple")
        .all()
    )

    assert len(serious_issues) > 0
    assert len(simple_issues) > 0
    serious_types = {i.issue_type for i in serious_issues}
    assert "WRONG_TAX_TYPE" in serious_types
    assert "INVALID_GSTIN_CHECKSUM" in serious_types
