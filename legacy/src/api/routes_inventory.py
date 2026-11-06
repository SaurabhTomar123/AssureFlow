from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from src.db.session import get_db
from src.inventory.service import (
    get_inventory_catalog,
    get_low_stock_report,
    record_stock_out,
    create_or_update_batch,
    get_fefo_expiry_report,
    generate_rtv_debit_note,
    get_dynamic_reorder_sheet,
    audit_physical_stock,
    check_supplier_price_opportunity,
)

router = APIRouter(prefix="/api/inventory", tags=["Inventory Management"])


class StockOutRequest(BaseModel):
    sku: str
    quantity: float
    reason: str = "SALE"


class CreateBatchRequest(BaseModel):
    sku: str
    batch_number: str
    quantity: float
    expiry_date: str
    cost_price: Optional[float] = 0.0
    manufacture_date: Optional[str] = None


class RTVDebitNoteRequest(BaseModel):
    batch_id: str
    reason: str = "EXPIRED_SHELF_LIFE"


class AuditStockRequest(BaseModel):
    sku: str
    physical_count: float
    audited_by: Optional[str] = "Store Manager"
    reason: Optional[str] = "AUDIT_DISCREPANCY"


@router.get("/{shop_id}")
def list_inventory(shop_id: str, db: Session = Depends(get_db)):
    return get_inventory_catalog(shop_id, db)


@router.get("/{shop_id}/low-stock")
def list_low_stock(shop_id: str, db: Session = Depends(get_db)):
    return get_low_stock_report(shop_id, db)


@router.post("/{shop_id}/stock-out")
def post_stock_out(shop_id: str, payload: StockOutRequest, db: Session = Depends(get_db)):
    res = record_stock_out(
        shop_id=shop_id,
        sku=payload.sku,
        quantity=payload.quantity,
        reason=payload.reason,
        db=db,
    )
    if not res:
        raise HTTPException(status_code=404, detail="SKU not found in store inventory")
    return res


@router.post("/{shop_id}/batch")
def post_create_batch(shop_id: str, payload: CreateBatchRequest, db: Session = Depends(get_db)):
    batch = create_or_update_batch(
        shop_id=shop_id,
        sku=payload.sku,
        batch_number=payload.batch_number,
        quantity=payload.quantity,
        expiry_date=payload.expiry_date,
        cost_price=payload.cost_price or 0.0,
        manufacture_date=payload.manufacture_date,
        db=db,
    )
    if not batch:
        raise HTTPException(status_code=404, detail="Item SKU not found for batch creation")
    return {
        "status": "SUCCESS",
        "batch_id": batch.id,
        "batch_number": batch.batch_number,
        "quantity": batch.quantity,
        "expiry_date": batch.expiry_date,
    }


@router.get("/{shop_id}/fefo-report")
def get_fefo_report(shop_id: str, db: Session = Depends(get_db)):
    return get_fefo_expiry_report(shop_id=shop_id, db=db)


@router.post("/{shop_id}/rtv-debit-note")
def post_rtv_debit_note(shop_id: str, payload: RTVDebitNoteRequest, db: Session = Depends(get_db)):
    res = generate_rtv_debit_note(
        shop_id=shop_id,
        batch_id=payload.batch_id,
        reason=payload.reason,
        db=db,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Batch not found for RTV Debit Note")
    return res


@router.get("/{shop_id}/dynamic-reorder")
def get_dynamic_reorder(
    shop_id: str,
    lookback_days: int = Query(default=30, ge=1, le=90),
    safety_buffer_days: int = Query(default=2, ge=0, le=14),
    db: Session = Depends(get_db),
):
    return get_dynamic_reorder_sheet(
        shop_id=shop_id,
        db=db,
        lookback_days=lookback_days,
        safety_buffer_days=safety_buffer_days,
    )


@router.post("/{shop_id}/audit-stock")
def post_audit_stock(shop_id: str, payload: AuditStockRequest, db: Session = Depends(get_db)):
    res = audit_physical_stock(
        shop_id=shop_id,
        sku=payload.sku,
        physical_count=payload.physical_count,
        audited_by=payload.audited_by or "Store Manager",
        reason=payload.reason or "AUDIT_DISCREPANCY",
        db=db,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Item SKU not found for stock audit")
    return res


@router.get("/{shop_id}/price-opportunity")
def get_price_opportunity(
    shop_id: str,
    sku: str = Query(...),
    latest_cost: float = Query(...),
    supplier_name: str = Query(default="Vendor"),
    db: Session = Depends(get_db),
):
    return check_supplier_price_opportunity(
        shop_id=shop_id,
        sku=sku,
        latest_cost=latest_cost,
        supplier_name=supplier_name,
        db=db,
    )

