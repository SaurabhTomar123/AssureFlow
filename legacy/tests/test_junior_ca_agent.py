import pytest
from src.db.session import SessionLocal
from src.agents.junior_ca import JuniorCAAgent


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_junior_ca_khata_flow(db_session):
    agent = JuniorCAAgent()
    en_msg = agent.handle_khata_request("shop-sharma-kirana", db_session, language="en")
    assert "Monthly Accounts Book" in en_msg
    assert "Total Cash Outflow" in en_msg
    assert "Inventory Purchases" in en_msg

    hi_msg = agent.handle_khata_request("shop-sharma-kirana", db_session, language="hi")
    assert "Aapka Masik Khata" in hi_msg
    assert "Mal Kharid" in hi_msg


def test_junior_ca_tax_savings_flow(db_session):
    agent = JuniorCAAgent()
    en_msg = agent.handle_tax_savings_request("shop-sharma-kirana", db_session, language="en")
    assert "Section 32 Commercial Asset Depreciation" in en_msg
    assert "Section 80C" in en_msg
    assert "Section 80D" in en_msg
    assert "Section 80CCD(1B)" in en_msg


def test_junior_ca_presumptive_tax_flow():
    agent = JuniorCAAgent()
    msg = agent.handle_presumptive_tax_request(
        annual_turnover=6000000.0,
        digital_pct=85.0,
        actual_margin_pct=16.0,
        language="en",
    )
    assert "Section 44AD Presumptive Taxation Analysis" in msg
    assert "Section 44AD Deemed Profit" in msg
    assert "Estimated Tax Savings" in msg

