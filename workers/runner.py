"""Worker process: three lanes with separate slots (bulkhead) plus the ordered outbox dispatcher.

Run: python -m workers.runner
"""

from __future__ import annotations

import os
import socket
import threading
import time

from common.logging import configure_logging, get_logger
from common.settings import get_settings
from workers.handlers import HANDLERS, classify
from workers.outbox import dispatch_once
from workers.queue import LeasedJob, fail, heartbeat, lease_one

log = get_logger("runner")
IDLE_SLEEP = 0.5
DIGEST_CHECK_SECONDS = 60
ERROR_BACKOFF_SECONDS = 5


def run_job(job: LeasedJob) -> str:
    """Execute one leased job with heartbeats; returns the final status label."""
    settings = get_settings()
    stop = threading.Event()
    started = time.monotonic()

    def beat() -> None:
        while not stop.wait(settings.JOB_HEARTBEAT_SECONDS):
            if time.monotonic() - started > settings.JOB_MAX_DURATION_SECONDS:
                log.warning("job.max_duration", job_id=str(job.id))
                return  # stop renewing: the lease lapses and fencing blocks any late commit
            if not heartbeat(job):
                return

    beater = threading.Thread(target=beat, daemon=True)
    beater.start()
    try:
        HANDLERS[job.type](job)
        return "succeeded"
    except Exception as exc:  # noqa: BLE001 - every failure is classified and recorded under the fence
        retryable, cancel = classify(exc)
        status = fail(job, f"{type(exc).__name__}: {exc}", retryable=retryable, cancel=cancel)
        log.warning("job.failed", job_id=str(job.id), type=job.type, status=status, error=type(exc).__name__)
        return status
    finally:
        stop.set()


def lane_loop(lane: str, slot: int, stop: threading.Event) -> None:
    owner = f"{socket.gethostname()}:{os.getpid()}:{lane}:{slot}"
    while not stop.is_set():
        try:
            job = lease_one(lane, owner)
        except Exception as exc:  # noqa: BLE001 - a lane must survive database hiccups; it retries
            log.error("lane.lease_failed", lane=lane, error=type(exc).__name__)
            stop.wait(ERROR_BACKOFF_SECONDS)
            continue
        if job is None:
            stop.wait(IDLE_SLEEP)
            continue
        run_job(job)


def digest_loop(stop: threading.Event) -> None:
    """Every minute, enqueue today's digests that are due (idempotent per room per day)."""
    from common.db import transaction
    from domain.services.digests import schedule_due

    while not stop.is_set():
        try:
            with transaction() as s:
                schedule_due(s)
        except Exception as exc:  # noqa: BLE001 - scheduling retries next minute
            log.error("digest.schedule_failed", error=type(exc).__name__)
        stop.wait(DIGEST_CHECK_SECONDS)


def outbox_loop(stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            sent = dispatch_once()
        except Exception as exc:  # noqa: BLE001 - delivery retries; the loop must not die
            log.error("outbox.dispatch_failed", error=type(exc).__name__)
            stop.wait(ERROR_BACKOFF_SECONDS)
            continue
        if sent == 0:
            stop.wait(IDLE_SLEEP)


def drain(max_rounds: int = 50) -> None:
    """Run every runnable job and outbox row until idle (offline tests and the fixture demo)."""
    for _ in range(max_rounds):
        progressed = False
        for lane in ("fast", "io", "slow"):
            while (job := lease_one(lane, "drain")) is not None:
                run_job(job)
                progressed = True
        if dispatch_once():
            progressed = True
        if not progressed:
            return


def main() -> None:
    settings = get_settings()
    configure_logging()
    stop = threading.Event()
    threads = [
        threading.Thread(target=outbox_loop, args=(stop,), daemon=True),
        threading.Thread(target=digest_loop, args=(stop,), daemon=True),
    ]
    for lane, slots in (
        ("fast", settings.WORKER_FAST_SLOTS),
        ("io", settings.WORKER_IO_SLOTS),
        ("slow", settings.WORKER_SLOW_SLOTS),
    ):
        threads += [
            threading.Thread(target=lane_loop, args=(lane, i, stop), daemon=True) for i in range(slots)
        ]
    for t in threads:
        t.start()
    log.info(
        "worker.started",
        lanes={
            "fast": settings.WORKER_FAST_SLOTS,
            "io": settings.WORKER_IO_SLOTS,
            "slow": settings.WORKER_SLOW_SLOTS,
        },
    )
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop.set()


if __name__ == "__main__":
    main()
