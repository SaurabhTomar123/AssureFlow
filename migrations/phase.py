"""Shared helpers: each revision creates exactly its phase's tables (capability matrix)."""

from __future__ import annotations

from alembic import op

from domain.models import Base, tables_for_phase


def create_phase(phase: str, append_only: tuple[str, ...] = ()) -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind, tables=tables_for_phase(phase))
    for table in append_only:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION af_forbid_mutation()"
        )


def drop_phase(phase: str) -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind, tables=list(reversed(tables_for_phase(phase))))
