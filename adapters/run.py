"""Switch adapter process: consume every room event over the agent WebSocket into the durable inbox.

Run: python -m adapters.run
"""

from __future__ import annotations

import asyncio
from typing import Any

from adapters.inbox_writer import load_cursor, record_event, save_generation
from adapters.switch_client import SwitchCredentials, run_adapter
from common.logging import configure_logging, get_logger
from common.settings import get_settings

log = get_logger("adapter")


def main() -> None:
    configure_logging()
    settings = get_settings()
    if not settings.SWITCH_SERVER_VERSION:
        raise SystemExit("SWITCH_SERVER_VERSION must be pinned (see docs/decisions.md D-02).")
    creds = SwitchCredentials.load()

    def store(data: dict[str, Any], sequence: int) -> None:
        record_event(data, sequence, creds.connection_id)

    log.info("adapter.starting", agent=creds.agent_name, switch=settings.SWITCH_SERVER_VERSION)
    asyncio.run(run_adapter(creds, store, load_cursor, lambda gen: save_generation(creds.connection_id, gen)))


if __name__ == "__main__":
    main()
