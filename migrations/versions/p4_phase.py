"""P4 Monthly snapshot and evidence pack.

Revision ID: p4
Revises: p3
"""

from migrations.phase import create_phase, drop_phase

revision = "p4"
down_revision = "p3"


def upgrade() -> None:
    create_phase("P4")


def downgrade() -> None:
    drop_phase("P4")
