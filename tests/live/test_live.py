"""Live integration tests (spec section 12, live mode): actual Switch (pinned 0.31.0), the Mattermost bridge,
the running adapter and worker, and the demo database. Assertions run against code, storage and the database;
an agent saying "passed" is never evidence.

Run (with the stack, adapter and worker running): LIVE=1 python -m pytest tests/live -q
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from sqlalchemy import select

from common.db import transaction
from domain import models as m
from tests.live import mm

pytestmark = pytest.mark.skipif(
    os.environ.get("LIVE") != "1", reason="live mode: set LIVE=1 with Switch running"
)
ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "seed" / "fixtures"


def wait_for(fn: Any, timeout: float = 60.0, every: float = 1.0) -> Any:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = fn()
        if value:
            return value
        time.sleep(every)
    raise AssertionError("timed out waiting for the live system")


def _latest_case_with_sha(sha: str) -> m.Invoice | None:
    with transaction() as s:
        doc = s.execute(
            select(m.Document).where(m.Document.sha256 == sha).order_by(m.Document.created_at.desc()).limit(1)
        ).scalar_one_or_none()
        return s.get(m.Invoice, doc.invoice_id) if doc and doc.invoice_id else None


def test_r19_r05_unaddressed_upload_is_processed_and_hash_matches() -> None:
    """R19: a normal upload with no mention is processed by code. R05: stored bytes equal the original."""
    path = FIX / "F12_multipage.pdf"
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    with transaction() as s:
        before = s.execute(
            select(m.Receipt).order_by(m.Receipt.created_at.desc()).limit(1)
        ).scalar_one_or_none()
    mm.post("sharma", "af-shop-sharma", "", file=str(path))

    def new_receipt() -> m.Receipt | None:
        with transaction() as s:
            r = s.execute(
                select(m.Receipt).order_by(m.Receipt.created_at.desc()).limit(1)
            ).scalar_one_or_none()
            return r if r and (before is None or r.id != before.id) and r.status != "accepted" else None

    receipt = wait_for(new_receipt)
    assert receipt.status in ("preserved", "duplicate")
    with transaction() as s:
        event = s.get(m.InboxEvent, receipt.inbox_event_id)
        assert event is not None and event.addressed_agent is None and event.outcome == "processed"
        doc = s.execute(select(m.Document).where(m.Document.sha256 == sha)).scalars().first()
        assert doc is not None
    from adapters.storage import LocalStorage

    assert hashlib.sha256(LocalStorage().get(doc.storage_key)).hexdigest() == sha
    lines = wait_for(lambda: [x for x in mm.read("af-shop-sharma", 6) if receipt.public_ref in x])
    assert any(x.startswith("assure-flow: Received") for x in lines)


def test_r05_unmapped_sender_is_rejected_with_denied_audit() -> None:
    """A person with no bound identity cannot start work: rejected inbox outcome and denied audit."""
    users = json.loads(Path("data/mattermost_test_users.json").read_text("utf-8"))
    if "outsider" not in users:
        pytest.skip("create a synthetic 'outsider' user to run this check")
    mm.post("outsider", "af-shop-sharma", "status")

    def rejected() -> bool:
        with transaction() as s:
            ev = s.execute(
                select(m.InboxEvent)
                .where(m.InboxEvent.sender_ref.like("%-outsider:%"))
                .order_by(m.InboxEvent.received_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            return bool(ev and ev.outcome == "rejected")

    assert wait_for(rejected)


def test_r04_r19_ca_reply_without_mention_and_unauthorized_sender_has_no_effect() -> None:
    """R19: a CA reply naming an RR id is processed without a mention. R04: an owner (not an allowed CA)
    sending the same command in a room they cannot act in causes no state change."""
    with transaction() as s:
        rr = (
            s.execute(
                select(m.ReviewRequest)
                .where(m.ReviewRequest.status == "open")
                .order_by(m.ReviewRequest.created_at)
            )
            .scalars()
            .first()
        )
        if rr is None:
            pytest.skip("no open review request in the live database")
        case_id, ref = rr.invoice_id, rr.public_ref
        before = s.get(m.Invoice, case_id).status  # type: ignore[union-attr]
    mm.post("rao", "af-operations", f"{ref} include")  # an operator has no invoice authority
    time.sleep(4)
    with transaction() as s:
        assert s.get(m.Invoice, case_id).status == before  # type: ignore[union-attr]
    mm.post("mehta", "af-ca-review", f"{ref} clarify please confirm the supplier GSTIN on the bill")

    def decided() -> bool:
        with transaction() as s:
            return s.get(m.ReviewRequest, rr.id).status == "decided"  # type: ignore[union-attr]

    assert wait_for(decided)


def test_r01_documentation_mcp_is_development_only() -> None:
    """R01: developers add the Switch docs MCP (documented command); runtime agents' tool lists never contain it."""
    readme = (ROOT / "README.md").read_text("utf-8")
    assert "claude mcp add --transport http switch-ai-docs https://docs.switchagents.ai/mcp" in readme
    index = httpx.get("https://docs.switchagents.ai/llms.txt", timeout=20)
    assert index.status_code == 200 and "agent-protocol" in index.text
    rooms = yaml.safe_load((ROOT / "agents" / "rooms.yaml").read_text("utf-8"))["rooms"]
    runtime_tools = {t for r in rooms for a in (r.get("agents") or {}).values() for t in a.get("tools", [])}
    assert not any("doc" in t.lower() and "switch" in t.lower() for t in runtime_tools)
    import asyncio

    from api.mcp.server import mcp

    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert "search" not in names and not any("switch" in n for n in names)


def test_live_disclosure_matches_switch_members() -> None:
    """D-16: every bound room's live Switch members are exactly people authorized for it."""
    from adapters.switch_client import SwitchCredentials, SwitchHttp
    from domain.services.disclosure import unauthorized_live

    http = SwitchHttp(SwitchCredentials.load())
    with transaction() as s:
        rooms = list(
            s.execute(select(m.RoomBinding).where(~m.RoomBinding.switch_room_id.like("unbound:%"))).scalars()
        )
        for room in rooms:
            live = http.room_members(room.switch_room_id) or []
            assert not unauthorized_live(s, room, live), (room.name, live)
