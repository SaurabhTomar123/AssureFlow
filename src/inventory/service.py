import re
from datetime import datetime
from typing import Any, List, Optional
from sqlalchemy.orm import Session
from src.db.models import InventoryItem, StockMovement, Bill, BillItem


def generate_sku_from_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").upper()
    parts = [p for p in cleaned.split("-") if p][:4]
    return f"SKU-{'-'.join(parts)}"


def ensure_inventory_item(
    shop_id: str,
    name: str,
    cost_price: float = 0.0,
    hsn_code: Optional[str] = None,
    category: str = "Grocery",
    unit: str = "units",
    reorder_level: float = 10.0,
    db: Session = None,
) -> InventoryItem:
    sku = generate_sku_from_name(name)

    existing = (
        db.query(InventoryItem)
        .filter(InventoryItem.shop_id == shop_id, InventoryItem.sku == sku)
        .first()
    )
    if existing:
        return existing

    item = InventoryItem(
        shop_id=shop_id,
        sku=sku,
        name=name.strip(),
        category=category,
        unit=unit,
        current_stock=0.0,
        reorder_level=reorder_level,
        cost_price=cost_price,
        selling_price=round(cost_price * 1.20, 2) if cost_price > 0 else 0.0,
        hsn_code=hsn_code,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def restock_inventory_from_bill(bill_id: str, db: Session) -> List[dict[str, Any]]:
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill:
        return []

    restock_log = []

    if not bill.items:
        item_name = f"{bill.supplier_name} Supplies" if bill.supplier_name else "General Store Goods"
        inv_item = ensure_inventory_item(
            shop_id=bill.shop_id,
            name=item_name,
            cost_price=bill.taxable_amount or 100.0,
            hsn_code=None,
            db=db,
        )
        old_qty = inv_item.current_stock
        add_qty = 1.0
        inv_item.current_stock += add_qty
        inv_item.last_restocked_at = datetime.utcnow()

        movement = StockMovement(
            item_id=inv_item.id,
            shop_id=bill.shop_id,
            movement_type="IN_PURCHASE",
            quantity=add_qty,
            reference_bill_id=bill.id,
            notes=f"Auto-restocked from Invoice #{bill.bill_number} ({bill.supplier_name})",
        )
        db.add(movement)
        restock_log.append({
            "sku": inv_item.sku,
            "name": inv_item.name,
            "old_stock": old_qty,
            "added_quantity": add_qty,
            "new_stock": inv_item.current_stock,
            "unit": inv_item.unit,
        })
        db.commit()
        return restock_log

    for bill_item in bill.items:
        inv_item = ensure_inventory_item(
            shop_id=bill.shop_id,
            name=bill_item.description,
            cost_price=bill_item.rate,
            hsn_code=bill_item.hsn_code,
            db=db,
        )

        old_qty = inv_item.current_stock
        add_qty = bill_item.quantity
        inv_item.current_stock += add_qty
        inv_item.last_restocked_at = datetime.utcnow()

        movement = StockMovement(
            item_id=inv_item.id,
            shop_id=bill.shop_id,
            movement_type="IN_PURCHASE",
            quantity=add_qty,
            reference_bill_id=bill.id,
            notes=f"Auto-restocked from Invoice #{bill.bill_number} ({bill.supplier_name})",
        )
        db.add(movement)

        restock_log.append({
            "sku": inv_item.sku,
            "name": inv_item.name,
            "old_stock": old_qty,
            "added_quantity": add_qty,
            "new_stock": inv_item.current_stock,
            "unit": inv_item.unit,
        })

    db.commit()
    return restock_log


def record_stock_out(
    shop_id: str,
    sku: str,
    quantity: float,
    reason: str = "SALE",
    db: Session = None,
) -> Optional[dict[str, Any]]:
    item = (
        db.query(InventoryItem)
        .filter(InventoryItem.shop_id == shop_id, InventoryItem.sku == sku)
        .first()
    )
    if not item:
        return None

    movement_type = "OUT_SALE" if reason.upper() == "SALE" else "ADJUSTMENT_DAMAGE"
    item.current_stock = max(item.current_stock - quantity, 0.0)

    movement = StockMovement(
        item_id=item.id,
        shop_id=shop_id,
        movement_type=movement_type,
        quantity=quantity,
        notes=f"Stock out: {reason}",
    )
    db.add(movement)
    db.commit()

    return {
        "sku": item.sku,
        "name": item.name,
        "new_stock": item.current_stock,
        "status": "LOW_STOCK" if item.current_stock <= item.reorder_level else "IN_STOCK",
    }


def get_inventory_catalog(shop_id: str, db: Session) -> List[dict[str, Any]]:
    items = db.query(InventoryItem).filter(InventoryItem.shop_id == shop_id).all()
    results = []

    for it in items:
        status = "IN_STOCK"
        if it.current_stock <= 0.0:
            status = "OUT_OF_STOCK"
        elif it.current_stock <= it.reorder_level:
            status = "LOW_STOCK"

        results.append({
            "id": it.id,
            "sku": it.sku,
            "name": it.name,
            "category": it.category,
            "unit": it.unit,
            "current_stock": it.current_stock,
            "reorder_level": it.reorder_level,
            "cost_price": it.cost_price,
            "selling_price": it.selling_price,
            "status": status,
        })

    return results


def get_low_stock_report(shop_id: str, db: Session) -> List[dict[str, Any]]:
    items = (
        db.query(InventoryItem)
        .filter(InventoryItem.shop_id == shop_id, InventoryItem.current_stock <= InventoryItem.reorder_level)
        .all()
    )
    reports = []
    for it in items:
        suggested_qty = max((it.reorder_level * 2) - it.current_stock, 10.0)
        reports.append({
            "sku": it.sku,
            "name": it.name,
            "current_stock": it.current_stock,
            "reorder_level": it.reorder_level,
            "suggested_reorder_qty": round(suggested_qty, 1),
            "unit": it.unit,
            "estimated_cost": round(suggested_qty * it.cost_price, 2),
        })
    return reports
