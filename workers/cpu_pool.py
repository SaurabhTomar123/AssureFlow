"""CPU-bound work in a subprocess with a hard timeout (spec section 2, blocking work).

The task runs in its own process; when CPU_TASK_TIMEOUT_SECONDS passes, the process is terminated and
the slot is released. No CPU work runs on a lane thread or in the API process.
"""

from __future__ import annotations

import multiprocessing as mp
from collections.abc import Callable
from multiprocessing.connection import Connection
from typing import Any

from common.settings import get_settings


class CpuTaskTimeout(Exception):
    pass


class CpuTaskFailed(Exception):
    pass


def _child(conn: Connection, fn: Callable[..., Any], args: tuple[Any, ...]) -> None:
    try:
        conn.send(("ok", fn(*args)))
    except Exception as exc:  # noqa: BLE001 - reported to the parent, which raises CpuTaskFailed
        conn.send(("error", f"{type(exc).__name__}: {exc}"))
    finally:
        conn.close()


def run_cpu(fn: Callable[..., Any], *args: Any, timeout: float | None = None) -> Any:
    """Run a top-level, picklable function in a fresh process. Kill it on timeout."""
    limit = timeout if timeout is not None else get_settings().CPU_TASK_TIMEOUT_SECONDS
    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child, args=(child, fn, args), daemon=True)
    proc.start()
    child.close()
    try:
        if not parent.poll(limit):
            raise CpuTaskTimeout(f"{getattr(fn, '__name__', 'task')} exceeded {limit}s")
        status, value = parent.recv()
    except EOFError as exc:
        raise CpuTaskFailed("subprocess exited without a result") from exc
    finally:
        if proc.is_alive():
            proc.terminate()
        proc.join(5)
        if proc.is_alive():
            proc.kill()
        parent.close()
    if status == "error":
        raise CpuTaskFailed(value)
    return value
