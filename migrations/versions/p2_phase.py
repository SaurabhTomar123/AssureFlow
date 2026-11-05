"""P2 Versioned rules and exception ownership.

Revision ID: p2
Revises: p1
"""

from migrations.phase import create_phase, drop_phase

revision = "p2"
down_revision = "p1"


def upgrade() -> None:
    create_phase("P2", append_only=("check_results",))


def downgrade() -> None:
    drop_phase("P2")
