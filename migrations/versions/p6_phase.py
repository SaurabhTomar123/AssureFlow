"""P6 GSTR-2B import and reconciliation.

Revision ID: p6
Revises: p4
"""

from alembic import op

from migrations.phase import create_phase, drop_phase

revision = "p6"
down_revision = "p4"

OLD_OPS = "'preserve_document','extract_generation','run_checks','notify','build_snapshot','build_export'"
NEW_OPS = OLD_OPS + ",'import_statement','reconcile'"


def _ops(values: str) -> None:
    op.execute("ALTER TABLE execution_grants DROP CONSTRAINT IF EXISTS execution_grants_operation_check")
    op.execute(
        f"ALTER TABLE execution_grants ADD CONSTRAINT execution_grants_operation_check CHECK (operation IN ({values}))"
    )


def upgrade() -> None:
    _ops(NEW_OPS)
    create_phase("P6", append_only=("statements", "statement_lines", "reconciliation_results"))


def downgrade() -> None:
    drop_phase("P6")
    _ops(OLD_OPS)
