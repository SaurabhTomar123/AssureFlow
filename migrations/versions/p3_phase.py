"""P3 Resolution and authorized review.

Revision ID: p3
Revises: p2
"""

from migrations.phase import create_phase, drop_phase

revision = "p3"
down_revision = "p2"


def upgrade() -> None:
    create_phase("P3", append_only=("decisions",))


def downgrade() -> None:
    drop_phase("P3")
