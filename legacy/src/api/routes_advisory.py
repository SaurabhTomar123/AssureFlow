from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.db.models import Shop
from src.accounts.ledger import get_accounts_book
from src.advisory.tax_advisor import (
    analyze_presumptive_tax_44ad,
    calculate_asset_depreciation_section_32,
    generate_proprietor_tax_savings_plan,
    detect_blocked_itc_section_17_5,
)
from src.advisory.audit_radar import compute_shop_audit_risk
from src.accounts.double_entry import (
    record_bill_journal_entry,
    get_trial_balance,
    get_profit_and_loss,
    get_balance_sheet,
    get_cash_flow_forecast,
    get_vendor_payment_priority_queue,
)
from src.db.models import Bill

router = APIRouter(prefix="/api/advisory", tags=["Junior CA & Accounts"])


@router.get("/accounts/{shop_id}/ledger")
def get_shop_ledger(shop_id: str, db: Session = Depends(get_db)):
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return get_accounts_book(shop_id, db)


@router.get("/tax-savings/{shop_id}")
def get_shop_tax_savings(
    shop_id: str,
    annual_income: float = Query(900000.0, description="Estimated annual income of proprietor"),
    db: Session = Depends(get_db),
):
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    depreciation = calculate_asset_depreciation_section_32(shop_id, db)
    personal_plan = generate_proprietor_tax_savings_plan(estimated_annual_income=annual_income)

    total_combined_savings = (
        personal_plan["total_potential_annual_tax_saved"]
        + depreciation["estimated_income_tax_saved"]
    )

    return {
        "shop_id": shop_id,
        "shop_name": shop.name,
        "total_combined_tax_savings": round(total_combined_savings, 2),
        "section_32_asset_depreciation": depreciation,
        "personal_tax_optimization": personal_plan,
    }


@router.get("/presumptive-tax")
def get_presumptive_tax_analysis(
    turnover: float = Query(..., description="Annual turnover in INR"),
    digital_pct: float = Query(70.0, description="Percentage of turnover received via digital modes"),
    actual_margin_pct: float = Query(12.0, description="Estimated actual net profit margin percentage"),
):
    return analyze_presumptive_tax_44ad(
        annual_turnover=turnover,
        digital_turnover_pct=digital_pct,
        actual_profit_margin_pct=actual_margin_pct,
    )


@router.get("/blocked-itc/{shop_id}")
def get_blocked_itc_warnings(shop_id: str, db: Session = Depends(get_db)):
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return {
        "shop_id": shop_id,
        "blocked_itc_items": detect_blocked_itc_section_17_5(shop_id, db),
    }


@router.get("/audit-radar/{shop_id}")
def get_shop_audit_radar(shop_id: str, db: Session = Depends(get_db)):
    try:
        radar_report = compute_shop_audit_risk(shop_id, db)
        return radar_report
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/double-entry/{shop_id}/sync-bills")
def post_sync_bills_to_journal(shop_id: str, db: Session = Depends(get_db)):
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    bills = db.query(Bill).filter(Bill.shop_id == shop_id, Bill.status != "REJECTED").all()
    created = []
    for b in bills:
        entry = record_bill_journal_entry(b.id, db)
        if entry:
            created.append(entry.entry_number)
    return {"shop_id": shop_id, "synced_count": len(created), "entries": created}


@router.get("/double-entry/{shop_id}/trial-balance")
def get_shop_trial_balance(shop_id: str, db: Session = Depends(get_db)):
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return get_trial_balance(shop_id, db)


@router.get("/double-entry/{shop_id}/profit-loss")
def get_shop_profit_loss(shop_id: str, db: Session = Depends(get_db)):
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return get_profit_and_loss(shop_id, db)


@router.get("/double-entry/{shop_id}/balance-sheet")
def get_shop_balance_sheet(shop_id: str, db: Session = Depends(get_db)):
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return get_balance_sheet(shop_id, db)


@router.get("/treasury/{shop_id}/cash-flow-forecast")
def get_shop_cash_flow_forecast(shop_id: str, db: Session = Depends(get_db)):
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return get_cash_flow_forecast(shop_id, db)


@router.get("/treasury/{shop_id}/vendor-payment-priority")
def get_shop_vendor_payment_priority(shop_id: str, db: Session = Depends(get_db)):
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return get_vendor_payment_priority_queue(shop_id, db)



