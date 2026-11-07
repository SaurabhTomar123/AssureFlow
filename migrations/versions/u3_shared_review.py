"""Shared review and client submission rooms (D-31, D-32).

Revision ID: u3
Revises: u2
"""

from alembic import op

revision = "u3"
down_revision = "u2"

ROLES = "'owner','ca','practice_staff','operator','developer','staff'"
PURPOSES = "'practice_home','shop_intake','ca_review','operations','synthetic_testing','delivery'"
CAPABILITIES = (
    "'order_confirm','delivery_confirm','task_assign','task_work','invoice_view',"
    "'purchase_review','readiness_authorize'"
)


def _check(table: str, name: str, column: str, values: str) -> None:
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({column} IN ({values}))")


def upgrade() -> None:
    op.execute("ALTER TABLE shops ADD COLUMN IF NOT EXISTS shared_review boolean NOT NULL DEFAULT false")
    _check("users", "users_role_check", "role", ROLES + ",'client'")
    _check("room_bindings", "room_bindings_purpose_check", "purpose", PURPOSES + ",'submission'")
    _check("shop_capabilities", "shop_capabilities_capability_check", "capability", CAPABILITIES + ",'invoice_submit'")


def downgrade() -> None:
    op.execute("DELETE FROM shop_capabilities WHERE capability = 'invoice_submit'")
    op.execute(
        "DELETE FROM room_members WHERE room_binding_id IN (SELECT id FROM room_bindings WHERE purpose = 'submission')"
    )
    op.execute(
        "DELETE FROM room_binding_shops WHERE room_binding_id IN "
        "(SELECT id FROM room_bindings WHERE purpose = 'submission')"
    )
    op.execute("DELETE FROM room_bindings WHERE purpose = 'submission'")
    _check("shop_capabilities", "shop_capabilities_capability_check", "capability", CAPABILITIES)
    _check("room_bindings", "room_bindings_purpose_check", "purpose", PURPOSES)
    op.execute("UPDATE users SET role = 'staff' WHERE role = 'client'")
    _check("users", "users_role_check", "role", ROLES)
    op.execute("ALTER TABLE shops DROP COLUMN IF EXISTS shared_review")
