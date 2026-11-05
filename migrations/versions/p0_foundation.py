"""P0 foundation and integration tables.

Revision ID: p0
Revises:
"""

from alembic import op

from migrations.phase import create_phase, drop_phase

revision = "p0"
down_revision = None


def upgrade() -> None:
    op.execute(
        "CREATE OR REPLACE FUNCTION af_forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN RAISE EXCEPTION 'append-only table %', TG_TABLE_NAME; END $$"
    )
    create_phase("P0", append_only=("documents", "audit_events"))


def downgrade() -> None:
    drop_phase("P0")
    op.execute("DROP FUNCTION IF EXISTS af_forbid_mutation()")
