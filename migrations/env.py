from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

from common.db import Base
from common.settings import get_settings
from domain import models  # noqa: F401  (registers tables)

target_metadata = Base.metadata


def run_migrations_online() -> None:
    url = context.config.attributes.get("url") or get_settings().DATABASE_URL
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations_online()
