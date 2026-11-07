"""U2 purchase assurance: capabilities, orders, deliveries, links, match runs, tasks, payment readiness.

Revision ID: u2
Revises: p5
(See docs/purchase-assurance-update.md. Existing tables only gain columns or widen checks.)
"""

from alembic import op

from migrations.phase import create_phase, drop_phase

revision = "u2"
down_revision = "p5"

P5_OPS = (
    "'preserve_document','extract_generation','run_checks','notify','build_snapshot','build_export',"
    "'import_statement','reconcile','run_acceptance'"
)
U2_OPS = P5_OPS + ",'run_purchase_match','build_purchase_export'"
ROLES_V14 = "'owner','ca','practice_staff','operator','developer'"
PURPOSES_V14 = "'practice_home','shop_intake','ca_review','operations','synthetic_testing'"


def _check(table: str, name: str, column: str, values: str) -> None:
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({column} IN ({values}))")


def upgrade() -> None:
    _check("execution_grants", "execution_grants_operation_check", "operation", U2_OPS)
    _check("users", "users_role_check", "role", ROLES_V14 + ",'staff'")
    _check("room_bindings", "room_bindings_purpose_check", "purpose", PURPOSES_V14 + ",'delivery'")
    op.execute("ALTER TABLE shops ADD COLUMN IF NOT EXISTS purchase_assurance boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE artifacts ALTER COLUMN snapshot_id DROP NOT NULL")
    op.execute("ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS readiness_id uuid")
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_artifacts_readiness_kind') "
        "THEN ALTER TABLE artifacts ADD CONSTRAINT uq_artifacts_readiness_kind UNIQUE (readiness_id, kind); "
        "END IF; END $$"
    )
    create_phase("U2", append_only=("delivery_events", "purchase_match_runs", "task_events"))


def downgrade() -> None:
    drop_phase("U2")
    op.execute("DELETE FROM artifacts WHERE readiness_id IS NOT NULL")
    op.execute("ALTER TABLE artifacts DROP CONSTRAINT IF EXISTS uq_artifacts_readiness_kind")
    op.execute("ALTER TABLE artifacts DROP COLUMN IF EXISTS readiness_id")
    op.execute("ALTER TABLE artifacts ALTER COLUMN snapshot_id SET NOT NULL")
    op.execute("ALTER TABLE shops DROP COLUMN IF EXISTS purchase_assurance")
    _check("room_bindings", "room_bindings_purpose_check", "purpose", PURPOSES_V14)
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check")
    op.execute(f"ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ({ROLES_V14})) NOT VALID")
    _check("execution_grants", "execution_grants_operation_check", "operation", P5_OPS)
