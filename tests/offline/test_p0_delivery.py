"""Live Telegram regressions T-18 and T-22: per-file export delivery, resend and download failures."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from adapters.storage import LocalStorage
from common.db import transaction
from common.settings import get_settings
from domain import models as m
from tests.offline.harness import Harness
from workers.outbox import dispatch_once

NOTE = "_attachment not relayed: F03.pdf — download failed: Timed out_"


def _approved_case(h: Harness) -> str:
    ref = h.ingest("F01_clean_intrastate_5pct")
    h.event("ca", "ca", f"{h.open_rr(ref)} include")
    assert h.case(ref).status == "approved"
    return ref





def _exported_pack(h: Harness) -> tuple[str, list[tuple[str, list[str], str]]]:
    _approved_case(h)
    h.event("ca", "ca", "snapshot sharma 2026-11")
    with transaction() as s:
        digest = s.execute(select(m.Snapshot)).scalar_one().content_hash
    h.event("ca", "ca", f"approve SN-0001 {digest[:12]}")
    return digest, list(h.switch.uploads)


def test_each_export_file_is_its_own_tracked_message(h: Harness) -> None:
    _, uploads = _exported_pack(h)
    assert sorted(f.rsplit(".", 1)[1] for _, files, _ in uploads for f in files) == ["json", "xlsx"]
    assert all(len(files) == 1 for _, files, _ in uploads)
    with transaction() as s:
        rows = s.execute(select(m.Outbox).where(m.Outbox.kind == "files")).scalars().all()
    assert len(rows) == 2
    assert all(row.status == "delivered" and row.delivered_event_id for row in rows)
    assert len({row.action_id for row in rows}) == 2


def test_a_failed_file_is_reported_and_does_not_hide_the_other(h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    _approved_case(h)
    h.event("ca", "ca", "snapshot sharma 2026-11")
    with transaction() as s:
        digest = s.execute(select(m.Snapshot)).scalar_one().content_hash
    real = h.switch.upload_files

    def flaky(room: str, files: list[tuple[str, bytes, str]], caption: str) -> str:
        if files[0][0].endswith(".xlsx"):
            raise httpx.ConnectError("bridge offline")
        return real(room, files, caption)

    monkeypatch.setattr(h.switch, "upload_files", flaky)
    h.event("ca", "ca", f"approve SN-0001 {digest[:12]}")
    for _ in range(get_settings().OUTBOX_MAX_ATTEMPTS + 2):
        dispatch_once()
    with transaction() as s:
        rows = {r.attachments[0]: r for r in s.execute(select(m.Outbox).where(m.Outbox.kind == "files")).scalars()}
        arts = {a.kind: str(a.id) for a in s.execute(select(m.Artifact)).scalars()}
        assert rows[arts["xlsx"]].status == "dead"
        assert rows[arts["json"]].status == "delivered"
    assert any("couldn't send" in x and "resend SN-0001" in x for x in h.said("ca"))
    monkeypatch.setattr(h.switch, "upload_files", real)
    before = len(h.switch.uploads)
    h.event("ca", "ca", "resend SN-0001 excel")
    assert [f.rsplit(".", 1)[1] for _, files, _ in h.switch.uploads[before:] for f in files] == ["xlsx"]


def test_resend_uses_the_stored_bytes_and_builds_nothing(h: Harness) -> None:
    _exported_pack(h)
    with transaction() as s:
        art_count = len(s.execute(select(m.Artifact)).scalars().all())
        snap_count = len(s.execute(select(m.Snapshot)).scalars().all())
    before = len(h.switch.uploads)
    h.event("ca", "ca", "resend SN-0001")
    assert len(h.switch.uploads) == before + 2
    with transaction() as s:
        assert len(s.execute(select(m.Artifact)).scalars().all()) == art_count
        assert len(s.execute(select(m.Snapshot)).scalars().all()) == snap_count


def test_resend_refuses_a_file_that_no_longer_matches(h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    _exported_pack(h)
    before = len(h.switch.uploads)
    monkeypatch.setattr(LocalStorage, "get", lambda self, key: b"tampered")
    h.event("ca", "ca", "resend SN-0001")
    assert "no longer matches" in h.last("ca")
    assert len(h.switch.uploads) == before


def test_only_the_assigned_ca_can_resend(h: Harness) -> None:
    _exported_pack(h)
    before = len(h.switch.uploads)
    h.event("sharma", "sharma", "resend SN-0001")
    assert len(h.switch.uploads) == before





def test_download_failure_tells_the_sender_and_creates_nothing(h: Harness) -> None:
    h.event("sharma", "sharma", NOTE)
    assert "couldn't download F03.pdf" in h.last("sharma")
    assert "Timed out" not in h.last("sharma")
    with transaction() as s:
        assert not s.execute(select(m.Invoice)).first()
        assert not s.execute(select(m.Document)).first()


def test_replayed_failure_note_replies_once(h: Harness) -> None:
    h.event("sharma", "sharma", NOTE, message_id="$same")
    count = len(h.said("sharma"))
    h.event("sharma", "sharma", NOTE, message_id="$same")
    assert len(h.said("sharma")) == count


def test_partial_failure_still_processes_the_file_that_arrived(h: Harness) -> None:
    h.event("sharma", "sharma", f"two bills\n{NOTE}", files=["F01_clean_intrastate_5pct"])
    said = " ".join(h.said("sharma"))
    assert "couldn't download F03.pdf" in said
    assert len(h.cases()) == 1


def test_unknown_sender_gets_no_relay_reply(h: Harness) -> None:
    h.event("sharma", "stranger", NOTE)
    assert not h.said("sharma")
