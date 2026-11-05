"""Reliability, consistency and security tests (R08, R10, R12-R18, P1-19, P1-20, P4-10..13, G-08, G-10, G-13)."""

from __future__ import annotations

import io
import threading
import time
from datetime import timedelta
from typing import Any

import pytest
from PIL import Image
from sqlalchemy import select, text, update

from adapters import llm
from adapters.excel import build_workbook, read_cells
from adapters.pdf import burn_cpu
from adapters.storage import LocalStorage
from common.db import transaction
from common.errors import InvalidTransition, LeaseLost
from common.logging import redact
from domain import models as m
from domain import states as st
from domain.context import revoke_grants
from domain.models import utcnow
from tests.offline.harness import Harness
from workers.cpu_pool import CpuTaskTimeout, run_cpu
from workers.handlers import process_inbox_event
from workers.outbox import dispatch_once
from workers.queue import lease_one
from workers.runner import drain, run_job


def _approve_latest(h: Harness, ack: str = "") -> str:
    with transaction() as s:
        snap = s.execute(select(m.Snapshot).order_by(m.Snapshot.created_at.desc()).limit(1)).scalar_one()
        ref, digest = snap.public_ref, snap.content_hash
    h.event("ca", "ca", f"approve {ref} {digest[:12]} {ack}".strip())
    return ref


def test_r13_replacements_finishing_in_reverse_order(h: Harness) -> None:
    ref = h.ingest("F08_wrong_tax_type")
    real = llm.FakeProvider()
    injected = {"done": False}

    class Racing:
        def extract(self, prepared: dict[str, Any], sha256: str, shop_key: str) -> llm.ExtractionOutcome:
            if not injected["done"]:
                injected["done"] = True
                # While generation 2 is still extracting, a newer replacement arrives and finishes first.
                h.upload("sharma", "sharma", "F16_replacement_for_F08", body=f"{ref} again")
            return real.extract(prepared, sha256, shop_key)

    llm.set_provider(Racing())
    h.upload("sharma", "sharma", "F01_clean_intrastate_5pct", body=f"{ref} replacement")
    case = h.case(ref)
    assert case.document_generation == 3
    with transaction() as s:
        rev = s.get(m.InvoiceRevision, case.current_revision_id)
        assert rev is not None and rev.document_generation == 3
        discarded = s.execute(
            select(m.UsageRecord).where(m.UsageRecord.outcome == "discarded_stale_generation")
        ).all()
        cancelled = s.execute(
            select(m.Job).where(m.Job.type == "extract_document", m.Job.status == "cancelled")
        ).all()
    assert discarded or cancelled
    assert case.status == "needs_confirmation"


def test_r12_lease_fencing(h: Harness) -> None:
    h.event("sharma", "sharma", "status", drain_after=False)
    job_a = lease_one("fast", "worker-A")
    assert job_a is not None
    with transaction() as s:
        s.execute(
            update(m.Job).where(m.Job.id == job_a.id).values(lease_expires_at=utcnow() - timedelta(seconds=1))
        )
    job_b = lease_one("fast", "worker-B")
    assert job_b is not None and job_b.id == job_a.id and job_b.lease_generation == job_a.lease_generation + 1
    assert run_job(job_b) == "succeeded"
    with pytest.raises(LeaseLost):
        process_inbox_event(job_a)
    with transaction() as s:
        replies = s.execute(select(m.Outbox).where(m.Outbox.action_id.like("reply:%"))).all()
    assert len(replies) == 1


def test_r14_receipt_during_approval_makes_snapshot_stale(h: Harness) -> None:
    ref = h.ingest("F01_clean_intrastate_5pct")
    h.event("ca", "ca", f"{h.open_rr(ref)} include")
    h.event("ca", "ca", "snapshot sharma 2026-11")
    first = h.last("ca").split(" ")[0]
    h.upload("sharma", "sharma", "F04_clean_interstate_18pct")
    with transaction() as s:
        snap = s.execute(select(m.Snapshot).where(m.Snapshot.public_ref == first)).scalar_one()
        digest = snap.content_hash
    h.event("ca", "ca", f"approve {first} {digest[:12]}")
    msgs = h.said("ca")
    assert any("SNAPSHOT_STALE" in x for x in msgs[-3:])
    with transaction() as s:
        snaps = list(s.execute(select(m.Snapshot).order_by(m.Snapshot.version)).scalars())
    assert [x.status for x in snaps] == ["stale", "awaiting_ca"]
    assert snaps[1].manifest["unassigned"] == [{"case_ref": "INV-0002", "status": "needs_confirmation"}]


def test_r15_held_invoice_change_invalidates_draft(h: Harness) -> None:
    good = h.ingest("F01_clean_intrastate_5pct")
    h.event("ca", "ca", f"{h.open_rr(good)} include")
    held = h.ingest("F09_total_mismatch")
    h.event("ca", "ca", "snapshot sharma 2026-11")
    with transaction() as s:
        snap = s.execute(select(m.Snapshot)).scalar_one()
        assert snap.partial and snap.manifest["counts"]["held"] == 1
    h.event("ca", "ca", f"{h.open_rr(held)} exclude printed total is wrong")
    _approve_latest(h, ack="ack 1 0")
    assert any("SNAPSHOT_STALE" in x for x in h.said("ca")[-3:])


def _unknown_png() -> bytes:
    img = Image.new("RGB", (40, 40), (200, 10, 10))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def test_p4_11_failed_extraction_is_unassigned_and_blocks_complete_pack(h: Harness) -> None:
    ok = h.ingest("F01_clean_intrastate_5pct")
    h.event("ca", "ca", f"{h.open_rr(ok)} include")
    h.raw_upload("sharma", "sharma", _unknown_png(), "photo.png")
    failed = h.latest_case()
    assert failed.status == "extraction_failed"
    assert "could not read" in h.last("sharma")
    h.event("ca", "ca", "snapshot sharma 2026-11")
    with transaction() as s:
        snap = s.execute(select(m.Snapshot)).scalar_one()
        assert snap.partial is True
        assert snap.manifest["unassigned"][0]["case_ref"] == failed.case_ref
        digest = snap.content_hash
    h.event("ca", "ca", f"approve SN-0001 {digest[:12]}")
    assert "PARTIAL" in h.last("ca") and "ack 0 1" in h.last("ca")
    h.event("ca", "ca", f"approve SN-0001 {digest[:12]} ack 0 1")
    with transaction() as s:
        snap = s.execute(select(m.Snapshot)).scalar_one()
        assert snap.status == "exported" and snap.acknowledged_unassigned_ids == [failed.case_ref]
        art = s.execute(select(m.Artifact).where(m.Artifact.kind == "xlsx")).scalar_one()
    cells = read_cells(LocalStorage().get(art.storage_key))
    assert ["Status", "PARTIAL"] in cells["Summary"]


def test_p4_12_13_totals_reconcile_formula_safe_and_reproducible(h: Harness) -> None:
    a = h.ingest("F01_clean_intrastate_5pct")
    h.upload("sharma", "sharma", "F04_clean_interstate_18pct")
    b = h.latest_case().case_ref
    h.event("sharma", "sharma", f'{b} supplier="=HYPERLINK(""http://evil"",""x"")"')
    h.event("sharma", "sharma", f"ok {b}")
    excluded = h.ingest("F05_clean_round_off")
    h.event("ca", "ca", f"{h.open_rr(a)} include")
    h.event("ca", "ca", f"{h.open_rr(b)} include")
    h.event("ca", "ca", f"{h.open_rr(excluded)} exclude personal purchase")
    h.event("ca", "ca", "snapshot sharma 2026-11")
    _approve_latest(h)
    with transaction() as s:
        snap = s.execute(select(m.Snapshot)).scalar_one()
        arts = {x.kind: x for x in s.execute(select(m.Artifact)).scalars()}
        revs = [s.get(m.InvoiceRevision, h.case(r).current_revision_id) for r in (a, b)]
    expected_total = sum(r.invoice_total for r in revs if r)  # type: ignore[misc]
    assert snap.manifest["totals"]["total"] == str(expected_total)
    assert [e["case_ref"] for e in snap.manifest["excluded"]] == [excluded]
    xlsx = LocalStorage().get(arts["xlsx"].storage_key)
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(xlsx))
    cell = wb["Included"]["C3"]
    assert cell.value.startswith("=HYPERLINK") and cell.data_type == "s"
    # Later events never change an approved pack: re-export is identical.
    h.ingest("F12_multipage")
    assert LocalStorage().get(arts["json"].storage_key) == snap.manifest_bytes.encode("utf-8")
    assert read_cells(build_workbook(snap.manifest_bytes)) == read_cells(xlsx)


def test_r16_delayed_job_runs_under_grant_and_revocation_cancels(h: Harness) -> None:
    h.event("sharma", "sharma", files=["F01_clean_intrastate_5pct"], drain_after=False)
    job = lease_one("fast", "w")
    assert job is not None
    run_job(job)  # inbox processed: receipt + grant + fetch job queued
    with transaction() as s:
        s.execute(update(m.RequestContext).values(expires_at=utcnow() - timedelta(seconds=1)))
    drain()
    assert h.case("INV-0001").status == "needs_confirmation"

    h.event("sharma", "sharma", files=["F04_clean_interstate_18pct"], drain_after=False)
    job = lease_one("fast", "w")
    assert job is not None
    run_job(job)
    with transaction() as s:
        owner = s.execute(select(m.User).where(m.User.handle == "owner.sharma")).scalar_one()
        s.execute(
            update(m.ShopMembership).where(m.ShopMembership.user_id == owner.id).values(revoked_at=utcnow())
        )
        revoke_grants(s, "membership_removed", user_id=owner.id)
    drain()
    with transaction() as s:
        fetches = list(
            s.execute(
                select(m.Job).where(m.Job.type == "fetch_and_store").order_by(m.Job.created_at)
            ).scalars()
        )
    assert fetches[-1].status == "cancelled" and "grant revoked" in (fetches[-1].last_error or "")
    assert h.count(m.Invoice) == 1


def test_r17_assignment_revoked_before_delivery_withholds(h: Harness) -> None:
    h.upload("sharma", "sharma", "F01_clean_intrastate_5pct")
    h.event("sharma", "sharma", "ok INV-0001", drain_after=False)
    with transaction() as s:
        s.execute(text("UPDATE ca_assignments SET effective_to = now() - interval '1 second'"))
    drain()
    with transaction() as s:
        review = s.execute(select(m.Outbox).where(m.Outbox.action_id.like("review:%"))).scalar_one()
        alert = (
            s.execute(select(m.AuditEvent).where(m.AuditEvent.action == "outbox.withheld")).scalars().all()
        )
    assert review.status == "withheld" and alert
    assert not any(x.startswith("RR-0001") for x in h.said("ca"))


def test_r08_business_action_outbox_record_and_transport_are_separate(h: Harness) -> None:
    h.switch.fail_next_posts = 2
    msg_id = h.event("sharma", "sharma", "status", drain_after=False)
    drain()
    while dispatch_once() == 0 and h.switch.fail_next_posts:
        pass
    dispatch_once()
    with transaction() as s:
        rows = list(s.execute(select(m.Outbox)).scalars())
    assert len(rows) == 1 and rows[0].status == "delivered" and rows[0].transport_attempts == 3
    h.event("sharma", "sharma", "status", message_id=msg_id)
    assert h.count(m.Outbox) == 1
    assert len(h.said("sharma")) == 1


def test_r18_no_file_deletion_and_identical_content_reused(h: Harness) -> None:
    storage = LocalStorage()
    assert not any(hasattr(storage, name) for name in ("delete", "remove", "unlink"))
    sha1, key1 = storage.put("shop", b"same bytes")
    sha2, key2 = storage.put("shop", b"same bytes")
    assert (sha1, key1) == (sha2, key2) and storage.get(key1) == b"same bytes"


def test_r10_cpu_blocking_task_is_killed_and_ack_path_stays_fast(h: Harness) -> None:
    errors: list[BaseException] = []

    def blocker() -> None:
        try:
            run_cpu(burn_cpu, 30, timeout=3)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t = threading.Thread(target=blocker)
    t.start()
    started = time.monotonic()
    h.event("sharma", "sharma", "status")
    assert time.monotonic() - started < 5
    t.join(20)
    assert errors and isinstance(errors[0], CpuTaskTimeout)


def test_transition_table_is_total() -> None:
    commands = {c for _, c in st.TRANSITIONS}
    for state in st.ALL_STATES:
        for command in commands:
            if (state, command) in st.TRANSITIONS:
                assert st.target(state, command) == st.TRANSITIONS[(state, command)]
            else:
                with pytest.raises(InvalidTransition):
                    st.target(state, command)
    assert ("excluded", "replacement_accepted") not in st.TRANSITIONS


def test_append_only_tables_reject_updates(h: Harness) -> None:
    h.ingest("F01_clean_intrastate_5pct")
    with pytest.raises(Exception, match="append-only"), transaction() as s:
        s.execute(text("UPDATE case_events SET type = 'x'"))
    with pytest.raises(Exception, match="append-only"), transaction() as s:
        s.execute(text("DELETE FROM field_evidence"))


def test_log_redaction() -> None:
    out = redact(None, "info", {"event": "x", "body": "GSTIN 07ABC", "api_key": "sk-1", "shop_id": "s"})
    assert out["body"] == "[redacted]" and out["api_key"] == "[redacted]" and out["shop_id"] == "s"
