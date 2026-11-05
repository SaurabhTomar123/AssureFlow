"""End-to-end offline scenarios (R07 correction to export, R19 unaddressed workflow events, T01-T09)."""

from __future__ import annotations

import json

from sqlalchemy import select

from adapters.excel import read_cells
from adapters.storage import LocalStorage
from common.db import transaction
from domain import models as m
from tests.offline.harness import Harness


def test_clean_invoice_from_upload_to_export(h: Harness) -> None:
    # R19: an upload without any agent mention is processed by code.
    h.upload("sharma", "sharma", "F01_clean_intrastate_5pct")
    said = h.said("sharma")
    assert said[0].startswith("Received R-0001")
    assert "saved as INV-0001" in said[1]
    assert "INV-0001 r1: please check" in said[2]
    assert h.case("INV-0001").status == "needs_confirmation"

    h.event("sharma", "sharma", "ok INV-0001 r1")
    assert h.case("INV-0001").status == "ready_for_ca"
    assert set(h.results("INV-0001").values()) == {"pass"}
    review = h.last("ca")
    assert review.startswith("RR-0001 · INV-0001 r1")

    # R19: a CA reply naming the RR-id, no mention, is processed.
    h.event("ca", "ca", "RR-0001 include")
    assert h.case("INV-0001").status == "approved"

    h.event("ca", "ca", "snapshot sharma 2026-11")
    pack = h.last("ca")
    assert pack.startswith("SN-0001")
    with transaction() as s:
        snap = s.execute(select(m.Snapshot)).scalar_one()
        digest = snap.content_hash
        assert snap.partial is False
        assert snap.manifest["totals"]["total"] == "7770.00"
    h.event("ca", "ca", f"approve SN-0001 {digest[:12]}")
    assert "approved" in h.said("ca")[-2]
    assert h.switch.uploads and {f.rsplit(".", 1)[1] for f in h.switch.uploads[-1][1]} == {"json", "xlsx"}
    with transaction() as s:
        snap = s.execute(select(m.Snapshot)).scalar_one()
        assert snap.status == "exported"
        arts = {a.kind: a for a in s.execute(select(m.Artifact)).scalars()}
    data = LocalStorage().get(arts["json"].storage_key)
    assert json.loads(data)["totals"]["total"] == "7770.00"
    cells = read_cells(LocalStorage().get(arts["xlsx"].storage_key))
    assert cells["Summary"][3] == ["Status", "COMPLETE"]
