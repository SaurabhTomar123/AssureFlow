"""P5 operations: test_runs, digest_runs, live member usernames, page-range documents.

Revision ID: p5
Revises: p6
(Phase 5 tables were added after the early Phase 6 port, so this revision follows p6.)
"""

from alembic import op

from migrations.phase import create_phase, drop_phase

revision = "p5"
down_revision = "p6"

BASE = "'preserve_document','extract_generation','run_checks','notify','build_snapshot','build_export'"
P6 = BASE + ",'import_statement','reconcile'"
P5 = P6 + ",'run_acceptance'"


def _ops(values: str) -> None:
    op.execute("ALTER TABLE execution_grants DROP CONSTRAINT IF EXISTS execution_grants_operation_check")
    op.execute(
        "ALTER TABLE execution_grants ADD CONSTRAINT execution_grants_operation_check "
        f"CHECK (operation IN ({values}))"
    )


def upgrade() -> None:
    _ops(P5)
    op.execute("ALTER TABLE chat_identities ADD COLUMN IF NOT EXISTS chat_username varchar(120)")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS page_from integer")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS page_to integer")
    create_phase("P5", append_only=("test_runs",))


def downgrade() -> None:
    drop_phase("P5")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS page_to")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS page_from")
    op.execute("ALTER TABLE chat_identities DROP COLUMN IF EXISTS chat_username")
    _ops(P6)
