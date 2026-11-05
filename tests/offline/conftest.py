"""Offline CI fixtures: real test PostgreSQL, fake model, mocked Switch bridge (spec section 12)."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

TEST_DB = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://af:af@localhost:5433/assureflow_test")
os.environ["DATABASE_URL"] = TEST_DB
os.environ["ENVIRONMENT"] = "test"
os.environ["LLM_PROVIDER"] = "fake"
os.environ["FILE_STORAGE_ROOT"] = tempfile.mkdtemp(prefix="af-files-")
os.environ["CPU_TASK_TIMEOUT_SECONDS"] = "60"

from sqlalchemy import create_engine, text  # noqa: E402

from tests.offline.harness import Harness  # noqa: E402


_DB_AVAILABLE = False


def _ensure_database() -> None:
    global _DB_AVAILABLE
    try:
        base, name = TEST_DB.rsplit("/", 1)
        admin = create_engine(f"{base}/postgres", isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 1})
        with admin.connect() as conn:
            if not conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}).first():
                conn.execute(text(f'CREATE DATABASE "{name}"'))
        admin.dispose()
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        cfg.attributes["url"] = TEST_DB
        command.upgrade(cfg, "head")
        _DB_AVAILABLE = True
    except Exception:
        _DB_AVAILABLE = False


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    _ensure_database()
    yield


@pytest.fixture()
def h() -> Iterator[Harness]:
    if not _DB_AVAILABLE:
        pytest.skip("Test PostgreSQL instance (port 5433) is not reachable")
    harness = Harness.fresh()
    yield harness
    harness.close()
