from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from src.db.session import get_db
from src.inventory.service import (
    get_inventory_catalog,
    get_low_stock_report,
    record_stock_out,
)

router = APIRouter(prefix="/api/inventory", tags=["Inventory Management"])


class StockOutRequest(BaseModel):
    sku: str
    quantity: float
    reason: str = "SALE"


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
