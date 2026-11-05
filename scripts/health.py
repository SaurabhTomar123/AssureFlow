"""Operator health report (P0-19): DB, environment, bindings, identities, inbox lag, queue depth, failed jobs.

Run: python -m scripts.health    (IDs and metadata only; never invoice content)
"""

from __future__ import annotations

from pathlib import Path

import httpx
from sqlalchemy import func, select, text

from common.db import transaction
from common.settings import get_settings
from domain import models as m


def main() -> None:
    settings = get_settings()
    checks: list[tuple[str, bool, str]] = []
    try:
        with transaction() as s:
            s.execute(text("SELECT 1"))
            env = s.execute(select(m.EnvironmentRow.name)).scalar_one_or_none()
            checks.append(("database", True, "reachable"))
            checks.append(
                ("environment", env == settings.ENVIRONMENT, f"db={env} config={settings.ENVIRONMENT}")
            )
            unbound = (
                s.execute(select(m.RoomBinding.name).where(m.RoomBinding.switch_room_id.like("unbound:%")))
                .scalars()
                .all()
            )
            checks.append(
                (
                    "room bindings",
                    not unbound,
                    "all bound" if not unbound else f"unbound: {', '.join(unbound)}",
                )
            )
            identities = s.execute(select(func.count()).select_from(m.ChatIdentity)).scalar_one()
            checks.append(("identities", identities > 0, f"{identities} verified chat identities"))
            pending = s.execute(
                select(func.count()).select_from(m.InboxEvent).where(m.InboxEvent.outcome == "pending")
            ).scalar_one()
            checks.append(("inbox lag", pending < 50, f"{pending} unprocessed events"))
            depth = dict(
                s.execute(
                    select(m.Job.lane, func.count())
                    .where(m.Job.status.in_(("queued", "leased")))
                    .group_by(m.Job.lane)
                ).all()
            )
            checks.append(
                ("queue depth", True, ", ".join(f"{k}={v}" for k, v in sorted(depth.items())) or "empty")
            )
            dead = s.execute(select(m.Job.id, m.Job.type).where(m.Job.status == "dead")).all()
            checks.append(
                ("failed jobs", not dead, ", ".join(f"{t}:{str(i)[:8]}" for i, t in dead[:5]) or "none")
            )
            withheld = s.execute(
                select(func.count()).select_from(m.Outbox).where(m.Outbox.status.in_(("withheld", "dead")))
            ).scalar_one()
            checks.append(("outbox", withheld == 0, f"{withheld} withheld/dead messages"))
    except Exception as exc:  # noqa: BLE001 - the report shows failures instead of raising
        checks.append(("database", False, type(exc).__name__))
    creds = Path(settings.SWITCH_CREDENTIALS_FILE)
    checks.append(("switch credentials", creds.exists(), str(creds)))
    try:
        ok = httpx.get(
            f"{settings.SWITCH_BASE_URL}/health", timeout=settings.SWITCH_HTTP_TIMEOUT_SECONDS
        ).status_code
        checks.append(("switch server", ok == 200, f"{settings.SWITCH_BASE_URL} -> {ok}"))
    except httpx.HTTPError as exc:
        checks.append(("switch server", False, type(exc).__name__))
    checks.append(
        (
            "switch version pinned",
            bool(settings.SWITCH_SERVER_VERSION),
            settings.SWITCH_SERVER_VERSION or "unset",
        )
    )
    checks.append(("extraction provider", True, f"{settings.LLM_PROVIDER} / {settings.LLM_MODEL}"))
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name:22} {detail}")


if __name__ == "__main__":
    main()
