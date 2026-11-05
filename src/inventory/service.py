import re
from datetime import datetime, date, timedelta
from typing import Any, List, Optional
from sqlalchemy.orm import Session
from src.db.models import InventoryItem, StockMovement, Bill, BillItem, ItemBatch, StockAdjustment


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
        min_cost_seen=cost_price,
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


def create_or_update_batch(
    shop_id: str,
    sku: str,
    batch_number: str,
    quantity: float,
    expiry_date: str,
    cost_price: float = 0.0,
    manufacture_date: Optional[str] = None,
    db: Session = None,
) -> Optional[ItemBatch]:
    item = (
        db.query(InventoryItem)
        .filter(InventoryItem.shop_id == shop_id, InventoryItem.sku == sku)
        .first()
    )
    if not item:
        return None

    batch = (
        db.query(ItemBatch)
        .filter(ItemBatch.item_id == item.id, ItemBatch.batch_number == batch_number)
        .first()
    )

    if batch:
        batch.quantity += quantity
        batch.expiry_date = expiry_date
        if cost_price > 0:
            batch.cost_price = cost_price
        batch.is_active = True
    else:
        batch = ItemBatch(
            item_id=item.id,
            shop_id=shop_id,
            batch_number=batch_number,
            quantity=quantity,
            cost_price=cost_price or item.cost_price,
            manufacture_date=manufacture_date,
            expiry_date=expiry_date,
            is_active=True,
        )
        db.add(batch)

    if not item.expiry_date or expiry_date < item.expiry_date:
        item.expiry_date = expiry_date
    if not item.batch_number:
        item.batch_number = batch_number

    db.commit()
    db.refresh(batch)
    return batch


def get_fefo_expiry_report(shop_id: str, db: Session) -> dict[str, Any]:
    batches = (
        db.query(ItemBatch)
        .filter(ItemBatch.shop_id == shop_id, ItemBatch.is_active == True, ItemBatch.quantity > 0)
        .order_by(ItemBatch.expiry_date.asc())
        .all()
    )

    today = date.today()
    batch_reports = []
    expired_count = 0
    critical_count = 0
    warning_count = 0
    healthy_count = 0
    total_value_at_risk = 0.0

    for b in batches:
        try:
            exp_d = datetime.strptime(b.expiry_date[:10], "%Y-%m-%d").date()
            days_remaining = (exp_d - today).days
        except Exception:
            days_remaining = 90

        value = round(b.quantity * b.cost_price, 2)

        if days_remaining < 0:
            status = "EXPIRED"
            action = "RETURN_TO_VENDOR"
            advisory = f"Expired {abs(days_remaining)} days ago. Generate RTV Debit Note immediately."
            expired_count += 1
            total_value_at_risk += value
        elif days_remaining <= 15:
            status = "CRITICAL"
            action = "FLASH_DISCOUNT"
            advisory = f"Expires in {days_remaining} days. Apply markdown or bundle promotion."
            critical_count += 1
            total_value_at_risk += value
        elif days_remaining <= 45:
            status = "WARNING"
            action = "FRONT_SHELF_DISPLAY"
            advisory = f"Expires in {days_remaining} days. Move to front-of-shelf display."
            warning_count += 1
        else:
            status = "HEALTHY"
            action = "STANDARD_ROTATION"
            advisory = f"Healthy shelf life remaining ({days_remaining} days)."
            healthy_count += 1

        batch_reports.append({
            "batch_id": b.id,
            "sku": b.item.sku if b.item else "UNKNOWN",
            "item_name": b.item.name if b.item else "Unknown Item",
            "batch_number": b.batch_number,
            "quantity": b.quantity,
            "unit": b.item.unit if b.item else "units",
            "cost_price": b.cost_price,
            "expiry_date": b.expiry_date,
            "days_remaining": days_remaining,
            "status": status,
            "action": action,
            "advisory": advisory,
            "value_at_risk": value,
        })

    return {
        "shop_id": shop_id,
        "as_of_date": today.isoformat(),
        "total_batches": len(batches),
        "expired_batches": expired_count,
        "critical_batches": critical_count,
        "warning_batches": warning_count,
        "healthy_batches": healthy_count,
        "total_value_at_risk": round(total_value_at_risk, 2),
        "batches": batch_reports,
    }


def generate_rtv_debit_note(
    shop_id: str,
    batch_id: str,
    reason: str = "EXPIRED_SHELF_LIFE",
    db: Session = None,
) -> Optional[dict[str, Any]]:
    batch = db.query(ItemBatch).filter(ItemBatch.id == batch_id, ItemBatch.shop_id == shop_id).first()
    if not batch:
        return None

    item = batch.item
    debit_qty = batch.quantity
    taxable_claim = round(debit_qty * batch.cost_price, 2)
    tax_adjustment = round(taxable_claim * 0.18, 2)
    total_debit = round(taxable_claim + tax_adjustment, 2)

    note_number = f"DN-RTV-{datetime.utcnow().strftime('%Y%m%d')}-{batch.batch_number[:6]}"

    batch.is_active = False
    batch.quantity = 0.0

    if item:
        item.current_stock = max(0.0, item.current_stock - debit_qty)
        movement = StockMovement(
            item_id=item.id,
            shop_id=shop_id,
            movement_type="OUT_RTV",
            quantity=debit_qty,
            notes=f"Return to Vendor Debit Note #{note_number} ({reason})",
        )
        db.add(movement)

    db.commit()

    return {
        "debit_note_number": note_number,
        "batch_id": batch.id,
        "batch_number": batch.batch_number,
        "sku": item.sku if item else "UNKNOWN",
        "item_name": item.name if item else "Unknown",
        "returned_quantity": debit_qty,
        "unit": item.unit if item else "units",
        "taxable_claim": taxable_claim,
        "tax_reversal_claim": tax_adjustment,
        "total_debit_claim": total_debit,
        "reason": reason,
        "status": "ISSUED",
        "generated_at": datetime.utcnow().isoformat(),
    }


def get_dynamic_reorder_sheet(
    shop_id: str,
    db: Session,
    lookback_days: int = 30,
    safety_buffer_days: int = 2,
) -> List[dict[str, Any]]:
    items = db.query(InventoryItem).filter(InventoryItem.shop_id == shop_id).all()
    cutoff_date = datetime.utcnow() - timedelta(days=lookback_days)

    recommendations = []

    for it in items:
        sales_movements = (
            db.query(StockMovement)
            .filter(
                StockMovement.item_id == it.id,
                StockMovement.movement_type == "OUT_SALE",
                StockMovement.created_at >= cutoff_date,
            )
            .all()
        )
        total_units_sold = sum(m.quantity for m in sales_movements)

        if total_units_sold > 0:
            adv = round(total_units_sold / lookback_days, 2)
        else:
            adv = 0.5 if it.current_stock <= it.reorder_level else 0.0

        if adv > 0:
            dir_days = round(it.current_stock / adv, 1)
        else:
            dir_days = 999.0

        lead_time = it.lead_time_days or 3
        threshold_days = lead_time + safety_buffer_days

        if dir_days <= threshold_days or it.current_stock <= it.reorder_level:
            suggested_po_qty = max(
                round(adv * 14, 1),
                round((it.reorder_level * 2) - it.current_stock, 1),
                10.0,
            )
            estimated_cost = round(suggested_po_qty * it.cost_price, 2)

            if dir_days <= 2.0:
                urgency = "CRITICAL"
            elif dir_days <= 5.0:
                urgency = "URGENT"
            else:
                urgency = "STANDARD"

            recommendations.append({
                "sku": it.sku,
                "name": it.name,
                "current_stock": it.current_stock,
                "reorder_level": it.reorder_level,
                "average_daily_velocity": adv,
                "days_inventory_remaining": dir_days,
                "lead_time_days": lead_time,
                "urgency": urgency,
                "suggested_po_quantity": suggested_po_qty,
                "unit": it.unit,
                "cost_price": it.cost_price,
                "estimated_order_cost": estimated_cost,
                "preferred_vendor_gstin": it.preferred_vendor_gstin,
            })

    return recommendations


def audit_physical_stock(
    shop_id: str,
    sku: str,
    physical_count: float,
    audited_by: str = "Store Manager",
    reason: str = "AUDIT_DISCREPANCY",
    db: Session = None,
) -> Optional[dict[str, Any]]:
    item = (
        db.query(InventoryItem)
        .filter(InventoryItem.shop_id == shop_id, InventoryItem.sku == sku)
        .first()
    )
    if not item:
        return None

    expected_stock = item.current_stock
    discrepancy = round(physical_count - expected_stock, 2)
    discrepancy_pct = round(abs(discrepancy) / max(expected_stock, 1.0) * 100, 2)
    discrepancy_val = round(abs(discrepancy) * item.cost_price, 2)

    item.current_stock = physical_count

    if discrepancy != 0:
        movement = StockMovement(
            item_id=item.id,
            shop_id=shop_id,
            movement_type="SHRINKAGE_ADJUSTMENT",
            quantity=abs(discrepancy),
            notes=f"Stock audit adjustment by {audited_by}: Expected {expected_stock}, Counted {physical_count} ({reason})",
        )
        db.add(movement)

    adjustment = StockAdjustment(
        item_id=item.id,
        shop_id=shop_id,
        expected_stock=expected_stock,
        physical_count=physical_count,
        discrepancy=discrepancy,
        discrepancy_pct=discrepancy_pct,
        discrepancy_value=discrepancy_val,
        reason=reason,
        audited_by=audited_by,
    )
    db.add(adjustment)
    db.commit()
    db.refresh(adjustment)

    if discrepancy == 0:
        audit_status = "AUDIT_MATCHED"
    elif discrepancy_pct <= 2.0:
        audit_status = "NORMAL_VARIANCE"
    elif discrepancy_pct <= 10.0:
        audit_status = "SHRINKAGE_WARNING"
    else:
        audit_status = "SEVERE_LEAKAGE"

    return {
        "audit_id": adjustment.id,
        "sku": item.sku,
        "name": item.name,
        "expected_stock": expected_stock,
        "physical_count": physical_count,
        "discrepancy": discrepancy,
        "discrepancy_pct": discrepancy_pct,
        "discrepancy_value": discrepancy_val,
        "audit_status": audit_status,
        "audited_by": audited_by,
        "reason": reason,
        "adjusted_stock": item.current_stock,
    }


def check_supplier_price_opportunity(
    shop_id: str,
    sku: str,
    latest_cost: float,
    supplier_name: str,
    db: Session,
) -> dict[str, Any]:
    item = (
        db.query(InventoryItem)
        .filter(InventoryItem.shop_id == shop_id, InventoryItem.sku == sku)
        .first()
    )
    if not item:
        return {"opportunity_detected": False}

    if item.min_cost_seen <= 0.0 or latest_cost < item.min_cost_seen:
        item.min_cost_seen = latest_cost
        db.commit()
        return {
            "opportunity_detected": False,
            "min_cost_seen": latest_cost,
            "status": "NEW_LOWEST_RATE_RECORDED",
        }

    if latest_cost > item.min_cost_seen:
        unit_diff = round(latest_cost - item.min_cost_seen, 2)
        pct_diff = round((unit_diff / latest_cost) * 100, 1)
        return {
            "opportunity_detected": True,
            "sku": item.sku,
            "name": item.name,
            "latest_cost": latest_cost,
            "min_cost_seen": item.min_cost_seen,
            "potential_unit_savings": unit_diff,
            "percentage_savings": pct_diff,
            "supplier_name": supplier_name,
            "recommendation": f"Current supplier {supplier_name} charges Rs {latest_cost}, but previous baseline purchase was Rs {item.min_cost_seen} (save Rs {unit_diff}/unit, {pct_diff}%).",
        }

    return {"opportunity_detected": False, "min_cost_seen": item.min_cost_seen}
