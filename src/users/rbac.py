from typing import Any
from fastapi import HTTPException

ROLE_PERMISSIONS = {
    "OWNER": {
        "VIEW_FINANCIALS",
        "VIEW_TAX_SAVINGS",
        "VIEW_CA_PORTAL",
        "VIEW_INVENTORY",
        "MANAGE_INVENTORY",
        "VIEW_STAFF_ATTENDANCE",
        "MARK_ATTENDANCE",
        "MANAGE_PAYROLL",
        "UPLOAD_BILLS",
        "MANAGE_USERS",
    },
    "MANAGER": {
        "VIEW_INVENTORY",
        "MANAGE_INVENTORY",
        "VIEW_STAFF_ATTENDANCE",
        "MARK_ATTENDANCE",
        "MANAGE_PAYROLL",
        "UPLOAD_BILLS",
        "VIEW_SHIFT_SUMMARY",
    },
    "STAFF": {
        "MARK_ATTENDANCE",
        "VIEW_INVENTORY",
        "UPLOAD_BILLS",
    },
    "CA": {
        "VIEW_CA_PORTAL",
        "MANAGE_CA_ACTIONS",
        "VIEW_FINANCIALS",
    },
}


def has_permission(role: str, permission: str) -> bool:
    normalized_role = role.strip().upper()
    allowed_perms = ROLE_PERMISSIONS.get(normalized_role, set())
    return permission in allowed_perms


def validate_access(role: str, permission: str):
    if not has_permission(role, permission):
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: Role '{role}' lacks '{permission}' authorization.",
        )


def filter_dashboard_data_for_role(role: str, data: dict[str, Any]) -> dict[str, Any]:
    norm_role = role.strip().upper()
    filtered = dict(data)

    if norm_role == "STAFF":
        filtered.pop("financial_summary", None)
        filtered.pop("tax_savings_advice", None)
        filtered.pop("ca_compliance", None)
        filtered.pop("payroll_summary", None)
        filtered["accessible_features"] = ["Self Attendance Check-in", "Stock Level View", "Invoice Upload"]

    elif norm_role == "MANAGER":
        filtered.pop("tax_savings_advice", None)
        filtered.pop("ca_compliance", None)
        filtered["accessible_features"] = [
            "Inventory Restock & Reorders",
            "Staff Attendance Board",
            "Monthly Wage Calculation",
            "Daily Shift Briefing",
            "Invoice Upload & Receipt",
        ]

    elif norm_role == "CA":
        filtered.pop("staff_attendance", None)
        filtered.pop("inventory_status", None)
        filtered["accessible_features"] = ["GSTR Filing Reconciliation", "Section 16(2) Notices", "Audit Flags"]

    elif norm_role == "OWNER":
        filtered["accessible_features"] = ["Full Enterprise Governance"]

    return filtered
