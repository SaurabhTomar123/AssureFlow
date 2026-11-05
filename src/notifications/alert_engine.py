from datetime import date
from typing import Any, List
from sqlalchemy.orm import Session
from src.db.models import Shop, Bill, ComplianceIssueModel
from src.inventory.service import get_low_stock_report


def check_gst_deadline_alerts(shop_id: str, db: Session) -> List[dict[str, Any]]:
    today = date.today()
    filing_deadline_day = 20
    days_left = filing_deadline_day - today.day

    issues = db.query(ComplianceIssueModel).filter(
        ComplianceIssueModel.shop_id == shop_id,
        ComplianceIssueModel.ca_action == "pending",
    ).all()

    total_risk = sum(i.rupee_value_at_risk for i in issues)
    alerts = []

    if days_left >= 0 and len(issues) > 0:
        urgency = "HIGH" if days_left <= 5 else "MEDIUM"
        alerts.append({
            "type": "GST_DEADLINE_APPROACHING",
            "urgency": urgency,
            "days_until_deadline": days_left,
            "deadline_date": f"{today.year}-{today.month:02d}-20",
            "open_issues_count": len(issues),
            "itc_at_risk": round(total_risk, 2),
            "title": f"GSTR-3B Filing Deadline in {days_left} Days",
            "message": (
                f"Statutory filing deadline is on the 20th ({days_left} days remaining). "
                f"You have {len(issues)} open compliance flags putting INR {total_risk:,.2f} ITC at risk. "
                "Resolve or approve them now to ensure timely credit claim."
            ),
        })

    return alerts


def check_low_stock_alerts(shop_id: str, db: Session) -> List[dict[str, Any]]:
    low_items = get_low_stock_report(shop_id, db)
    if not low_items:
        return []

    alerts = []
    for it in low_items:
        alerts.append({
            "type": "INVENTORY_LOW_STOCK",
            "urgency": "HIGH" if it["current_stock"] == 0 else "MEDIUM",
            "sku": it["sku"],
            "name": it["name"],
            "current_stock": it["current_stock"],
            "unit": it["unit"],
            "reorder_level": it["reorder_level"],
            "suggested_order": it["suggested_reorder_qty"],
            "estimated_cost": it["estimated_cost"],
            "title": f"Low Stock Warning: {it['name']}",
            "message": (
                f"{it['name']} has reached {it['current_stock']} {it['unit']} "
                f"(Threshold: {it['reorder_level']}). Suggested reorder: {it['suggested_reorder_qty']} {it['unit']} (~INR {it['estimated_cost']:,.2f})."
            ),
        })
    return alerts


def get_proactive_store_alerts(shop_id: str, db: Session) -> dict[str, Any]:
    gst_alerts = check_gst_deadline_alerts(shop_id, db)
    stock_alerts = check_low_stock_alerts(shop_id, db)

    total_alerts = len(gst_alerts) + len(stock_alerts)
    high_urgency = sum(1 for a in gst_alerts + stock_alerts if a.get("urgency") == "HIGH")

    return {
        "shop_id": shop_id,
        "total_active_alerts": total_alerts,
        "high_urgency_count": high_urgency,
        "gst_deadline_alerts": gst_alerts,
        "inventory_alerts": stock_alerts,
        "status": "ATTENTION_REQUIRED" if total_alerts > 0 else "ALL_SYSTEMS_OPTIMAL",
    }
