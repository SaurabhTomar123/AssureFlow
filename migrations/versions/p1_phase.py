"""P1 Evidence-backed intake and revisioning.

Revision ID: p1
Revises: p0
"""

from migrations.phase import create_phase, drop_phase

revision = "p1"
down_revision = "p0"


def upgrade() -> None:
    create_phase("P1", append_only=("field_evidence", "case_events",))


def downgrade() -> None:
    drop_phase("P1")
