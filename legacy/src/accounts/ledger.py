from typing import Any
from sqlalchemy.orm import Session
from src.db.models import Bill, LedgerEntry

CAPITAL_KEYWORDS = [
    "computer", "laptop", "printer", "smartphone", "mobile", "blender",
    "mixer", "refrigerator", "freezer", "air conditioner", "ac unit",
    "machinery", "furniture", "desk", "inverter", "battery", "display rack"
]

OPEX_KEYWORDS = [
    "carton", "cartons", "stationery", "paper", "pen", "packaging", "box", "bubble wrap",
    "tape", "cleaning", "mop", "sanitizer", "tea", "refreshment",
    "electricity", "utility", "maintenance", "repair", "towel"
]

LOGISTICS_KEYWORDS = [
    "freight", "transport", "delivery", "courier", "shipping",
    "tempo", "cartage", "carriage"
]


def classify_expense(description: str, supplier_name: str = "") -> str:
    desc_lower = (description + " " + supplier_name).lower()

    for kw in CAPITAL_KEYWORDS:
        if kw in desc_lower:
            return "CAPITAL_ASSET"

    for kw in OPEX_KEYWORDS:
        if kw in desc_lower:
            return "OPERATING_EXPENSE"

    for kw in LOGISTICS_KEYWORDS:
        if kw in desc_lower:
            return "LOGISTICS_FREIGHT"

    return "INVENTORY_PURCHASE"


def sync_bills_to_ledger(shop_id: str, db: Session) -> list[LedgerEntry]:
    bills = db.query(Bill).filter(Bill.shop_id == shop_id).all()
    created_entries = []

    existing_ledger_bill_ids = {
        entry.bill_id for entry in db.query(LedgerEntry).filter(LedgerEntry.shop_id == shop_id).all()
        if entry.bill_id
    }

    for bill in bills:
        if bill.id in existing_ledger_bill_ids:
            continue

        desc = bill.supplier_name or "Purchase"
        if bill.items:
            desc = ", ".join(item.description for item in bill.items[:3])

        category = classify_expense(desc, bill.supplier_name or "")

        total_tax = (bill.cgst_amount or 0.0) + (bill.sgst_amount or 0.0) + (bill.igst_amount or 0.0)
        entry = LedgerEntry(
            shop_id=shop_id,
            bill_id=bill.id,
            category=category,
            description=f"{bill.supplier_name} - {desc}",
            amount=bill.taxable_amount,
            tax_amount=total_tax,
            total_outflow=bill.total_amount,
            entry_date=bill.bill_date or "2026-11-01",
        )
        db.add(entry)
        created_entries.append(entry)

    if created_entries:
        db.commit()

    return created_entries


def get_accounts_book(shop_id: str, db: Session) -> dict[str, Any]:
    sync_bills_to_ledger(shop_id, db)
    entries = db.query(LedgerEntry).filter(LedgerEntry.shop_id == shop_id).all()

    total_inventory = 0.0
    total_opex = 0.0
    total_capital = 0.0
    total_logistics = 0.0
    total_tax_paid = 0.0
    total_outflow = 0.0

    categorized_records = []
    for e in entries:
        total_outflow += e.total_outflow
        total_tax_paid += e.tax_amount

        if e.category == "INVENTORY_PURCHASE":
            total_inventory += e.amount
        elif e.category == "OPERATING_EXPENSE":
            total_opex += e.amount
        elif e.category == "CAPITAL_ASSET":
            total_capital += e.amount
        elif e.category == "LOGISTICS_FREIGHT":
            total_logistics += e.amount

        categorized_records.append({
            "id": e.id,
            "date": e.entry_date,
            "category": e.category,
            "description": e.description,
            "net_amount": e.amount,
            "tax_amount": e.tax_amount,
            "total_outflow": e.total_outflow,
        })

    return {
        "shop_id": shop_id,
        "entry_count": len(entries),
        "total_cash_outflow": round(total_outflow, 2),
        "total_tax_paid": round(total_tax_paid, 2),
        "breakdown": {
            "inventory_purchases": round(total_inventory, 2),
            "operating_expenses": round(total_opex, 2),
            "capital_assets": round(total_capital, 2),
            "logistics_freight": round(total_logistics, 2),
        },
        "entries": categorized_records,
    }
