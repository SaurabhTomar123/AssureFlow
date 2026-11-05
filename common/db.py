"""SQLAlchemy engine and session factory (PostgreSQL 16, psycopg 3)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from common.settings import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache(maxsize=4)
def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or get_settings().DATABASE_URL, pool_pre_ping=True, future=True)


def session_factory(url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(url), expire_on_commit=False, future=True)


@contextmanager
def transaction(url: str | None = None) -> Iterator[Session]:
    """One unit of work: commits on success, rolls back on any exception."""
    session = session_factory(url)()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
