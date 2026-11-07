"""One runtime owner per database: the adapter and the worker each hold a Postgres advisory lock for life.

A second copy exits at once and names the holder, so a restart can't silently compete with a running process.
The lock lives on a dedicated session and is released when the process or its database connection ends.
"""

from __future__ import annotations

import os
import socket
from typing import Any

from sqlalchemy import Connection, create_engine, text
from sqlalchemy.pool import NullPool

from common.settings import get_settings

NAMESPACE = 7001
ROLES = {"adapter": 1, "worker": 2}

_held: dict[str, Connection] = {}


class AlreadyRunning(RuntimeError):
    pass


HOLDER_SQL = text(
    """
    SELECT a.application_name, a.backend_start
    FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid
    WHERE l.locktype = 'advisory' AND l.granted AND l.classid = :ns AND l.objid = :role AND l.objsubid = 2
      AND l.database = (SELECT oid FROM pg_database WHERE datname = current_database())
    """
)


def holder(conn: Any, role: str) -> str | None:
    """Who holds the role right now: "<application name> since <time>", or None."""
    row = conn.execute(HOLDER_SQL, {"ns": NAMESPACE, "role": ROLES[role]}).first()
    return f"{row[0]} since {row[1]:%Y-%m-%d %H:%M:%S %Z}" if row else None


def hold(role: str, url: str | None = None) -> Connection:
    """Take the role's lock for the life of this process, or raise AlreadyRunning."""
    # NullPool: closing must end the database session, or the lock would outlive it in a connection pool.
    engine = create_engine(url or get_settings().DATABASE_URL, poolclass=NullPool, future=True)
    conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    name = f"af-{role} {socket.gethostname()} pid {os.getpid()}"
    conn.execute(text("SELECT set_config('application_name', :n, false)"), {"n": name})
    got: bool = conn.execute(
        text("SELECT pg_try_advisory_lock(:ns, :role)"), {"ns": NAMESPACE, "role": ROLES[role]}
    ).scalar_one()
    if not got:
        who = holder(conn, role) or "another process"
        conn.close()
        raise AlreadyRunning(f"An Assure Flow {role} is already running: {who}. Stop it first; this copy will exit.")
    _held[role] = conn
    return conn


def release(role: str) -> None:
    conn = _held.pop(role, None)
    if conn is not None:
        conn.close()
