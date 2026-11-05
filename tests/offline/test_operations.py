"""Deferred-item completion: compensation notices, override/reopen, multi-invoice split, per-page modes,
digests and escalation, practice home, operations and synthetic testing rooms, live member check."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update

from adapters.pdf import prepare_for_extraction
from common.db import transaction
from domain import models as m
from domain.services.base import post
from domain.services.digests import in_quiet_hours, schedule_due
from domain.services.operations import format_report
from tests.offline.harness import FIXTURES, INDEX, Harness
from workers.outbox import dispatch_once
from workers.runner import drain


def _ist(day: int, hh: int, mm: int = 5) -> datetime:
    # 10:05 IST == 04:35 UTC
    from zoneinfo import ZoneInfo

    return datetime(2026, 11, day, hh, mm, tzinfo=ZoneInfo("Asia/Kolkata")).astimezone(UTC)


# ------------------------------------------------------------------- compensation notices (P3-04, P4-05)


def test_replacement_withdraws_open_review_request_with_notice(h: Harness) -> None:
    ref = h.ingest("F08_wrong_tax_type")
    rr = h.open_rr(ref)
    h.upload("sharma", "sharma", "F16_replacement_for_F08", body=f"{ref} corrected")
    withdrawn = [x for x in h.said("ca") if x.startswith("Withdrawn:")]
    assert withdrawn and rr in withdrawn[0] and "a replacement document arrived" in withdrawn[0]
    with transaction() as s:
        row = s.execute(select(m.Outbox).where(m.Outbox.action_id.like("withdrawn:%"))).scalar_one()
        assert row.supersedes_action_id and row.supersedes_action_id.startswith("review:")
    assert any("Your confirmation of" in x for x in h.said("sharma"))


def test_correction_after_approval_invalidates_decision_with_notice(h: Harness) -> None:
    ref = h.ingest("F01_clean_intrastate_5pct")
    h.event("ca", "ca", f"{h.open_rr(ref)} include")
    h.event("sharma", "sharma", f"{ref} date=2026-11-02")
    assert h.case(ref).status == "needs_confirmation"
    assert any(x.startswith("No longer applies: RR-0001 'include'") for x in h.said("ca"))


def test_pack_superseded_and_outdated_notices(h: Harness) -> None:
    ref = h.ingest("F01_clean_intrastate_5pct")
    h.event("ca", "ca", f"{h.open_rr(ref)} include")
    h.event("ca", "ca", "snapshot sharma 2026-11")
    h.event("ca", "ca", "snapshot sharma 2026-11")
    assert any("SN-0001" in x and "a newer pack was built" in x for x in h.said("ca"))
    with transaction() as s:
        snap = s.execute(select(m.Snapshot).where(m.Snapshot.public_ref == "SN-0002")).scalar_one()
        digest = snap.content_hash
    h.event("ca", "ca", f"approve SN-0002 {digest[:12]}")
    h.event("sharma", "sharma", f"{ref} date=2026-11-03")
    assert any("SN-0002" in x and "an invoice in the month changed" in x for x in h.said("ca"))


# --------------------------------------------------------------------------------- override / reopen


def test_override_only_for_overridable_rules(h: Harness) -> None:
    hsn = h.ingest("F20_gupta_missing_hsn", shop="gupta")
    h.event("ca", "ca", f"{h.open_rr(hsn)} override R-PART-01 HSN confirmed on the delivery challan")
    assert h.case(hsn).status == "approved"
    with transaction() as s:
        issue = s.execute(select(m.Issue).where(m.Issue.rule_id == "R-PART-01")).scalar_one()
        assert (issue.status, issue.disposition) == ("resolved", "override")
    bad = h.ingest("F09_total_mismatch")
    h.event("ca", "ca", f"{h.open_rr(bad)} override R-AMT-03 looks fine")
    assert "never overridable" in h.last("ca")
    assert h.case(bad).status == "needs_resolution"


def test_reopen_reruns_checks(h: Harness) -> None:
    ref = h.ingest("F01_clean_intrastate_5pct")
    h.event("ca", "ca", f"{h.open_rr(ref)} exclude thought it was personal")
    assert h.case(ref).status == "excluded"
    h.event("ca", "ca", f"reopen {ref} it is a shop purchase after all")
    assert h.case(ref).status == "ready_for_ca"
    assert "reopened" in h.said("ca")[-2] or "reopened" in h.last("ca")
    h.event("ca", "ca", f"{h.open_rr(ref)} include")
    assert h.case(ref).status == "approved"


# ------------------------------------------------------------------------ multi-invoice + per-page


def test_two_invoices_in_one_file_are_split_per_page(h: Harness) -> None:
    h.upload("sharma", "sharma", "F21_two_invoices")
    cases = h.cases()
    assert len(cases) == 2
    parent, child = cases
    assert child.split_from_invoice_id == parent.id
    assert {c.status for c in cases} == {"needs_confirmation"}
    assert any("holds 2 invoices, so it was split" in x for x in h.said("sharma"))
    with transaction() as s:
        revs = {c.case_ref: s.get(m.InvoiceRevision, c.current_revision_id) for c in h.cases()}
    assert {r.invoice_number for r in revs.values() if r} == {"RSC-2026-260", "DPC-801"}
    for c in cases:
        h.event("sharma", "sharma", f"ok {c.case_ref}")
    assert {c.status for c in h.cases()} == {"ready_for_ca"}


def test_per_page_text_vision_modes() -> None:
    def modes(name: str, mime: str) -> tuple[str, list[tuple[bool, bool]]]:
        r = prepare_for_extraction((FIXTURES / INDEX[name]["file"]).read_bytes(), mime)
        return r["mode"], [(bool(p["text"]), bool(p["image"])) for p in r["pages"]]

    assert modes("F01_clean_intrastate_5pct", "application/pdf") == ("text", [(True, False)])
    assert modes("F02_clean_scan_12pct", "application/pdf") == ("mixed", [(True, True)])
    assert modes("F12_multipage", "application/pdf") == ("text", [(True, False), (True, False)])
    assert modes("F18_gupta_photo_clean", "image/png") == ("vision", [(False, True)])
    one = prepare_for_extraction((FIXTURES / "F21_two_invoices.pdf").read_bytes(), "application/pdf", 2, 2)
    assert [p["page"] for p in one["pages"]] == [2]


# ------------------------------------------------------------------------------- digests (P3-05)


def test_digest_schedule_quiet_hours_stop_rules_and_escalation(h: Harness) -> None:
    h.upload("sharma", "sharma", "F01_clean_intrastate_5pct")  # owner must confirm INV-0001
    assert in_quiet_hours(datetime(2026, 11, 5, 21, 0)) and not in_quiet_hours(datetime(2026, 11, 5, 10, 0))
    with transaction() as s:
        assert schedule_due(s, _ist(10, 8)) == 0  # before 10:00 local
        assert schedule_due(s, _ist(10, 21)) == 0  # quiet hours
    for day in (10, 11, 12):
        with transaction() as s:
            assert schedule_due(s, _ist(day, 10)) >= 1
            assert schedule_due(s, _ist(day, 10, 30)) == 0  # idempotent per day
        drain()
    digests = [x for x in h.said("sharma") if x.startswith("Daily digest")]
    assert len(digests) == 3 and "INV-0001: confirm the details" in digests[0]
    escalations = [x for x in h.said("ca") if x.startswith("Escalation:")]
    assert len(escalations) == 1 and "INV-0001" in escalations[0]
    h.event("sharma", "sharma", "ok INV-0001")
    with transaction() as s:
        schedule_due(s, _ist(13, 10))
    drain()
    assert not any(x.startswith("Daily digest 2026-11-13") for x in h.said("sharma"))  # stop rule
    assert any(x.startswith("Daily digest 2026-11-13") and "RR-0001" in x for x in h.said("ca"))


# ------------------------------------------------------------------ practice home, ops, testing rooms


def test_practice_home_directory_and_owner_refused(h: Harness) -> None:
    h.ingest("F01_clean_intrastate_5pct")
    h.event("home", "ca", "directory")
    text = h.last("home")
    assert (
        text.startswith("Practice directory:") and "sharma: Sharma Kirana Store" in text and "gupta" in text
    )
    h.event("home", "sharma", "directory")
    assert "only a ca or practice_staff" in h.last("home").lower()


def test_operations_room_health_alert_retry_and_trace(h: Harness) -> None:
    h.raw_upload("sharma", "sharma", b"\x89PNG\r\n\x1a\n" + b"0" * 64, "broken.png")
    h.event("ops", "ops", "health")
    assert h.last("ops").startswith("Health: queue")
    ref = h.ingest("F01_clean_intrastate_5pct")
    h.event("ops", "ops", f"trace {ref}")
    trace = h.last("ops")
    assert (
        trace.startswith(f"Trace {ref}")
        and "extract_document succeeded" in trace
        and "Modern Agro" not in trace
    )
    with transaction() as s:
        job = s.execute(select(m.Job).where(m.Job.type == "run_checks")).scalars().first()
        s.execute(update(m.Job).where(m.Job.id == job.id).values(status="dead", last_error="Boom: x"))
        prefix = str(job.id)[:8]
    h.event("ops", "ops", "failed")
    assert prefix in h.last("ops")
    h.event("ops", "sharma", f"retry {prefix}")
    assert "only a operator" in h.last("ops").lower()
    h.event("ops", "ops", f"retry {prefix}")
    assert "queued again" in h.last("ops")


def test_dead_job_raises_ops_alert(h: Harness) -> None:
    from adapters import llm

    class Down:
        def extract(self, *_: object) -> llm.ExtractionOutcome:
            raise llm.ProviderPermanentError("provider rejected")

    llm.set_provider(Down())
    h.upload("sharma", "sharma", "F01_clean_intrastate_5pct")
    assert h.latest_case().status == "extraction_failed"
    alerts = [x for x in h.said("ops") if x.startswith("ALERT job")]
    assert alerts and "extract_document" in alerts[0] and "Modern Agro" not in alerts[0]


def test_synthetic_testing_room(h: Harness) -> None:
    h.event("testing", "dev", "report nope")
    assert "No test run nope" in h.last("testing")
    h.event("testing", "sharma", "acceptance")
    assert "only a developer" in h.last("testing").lower()
    with transaction() as s:
        from domain.services.operations import request_acceptance

        assert s.execute(select(m.Job).where(m.Job.type == "run_acceptance")).first() is None
    run = m.TestRun(
        run_id="abc",
        environment="test",
        mode="offline",
        switch_versions="0.31.0",
        app_commit="c0ffee",
        fixture_version="f1",
        assertions={"tests": 3, "passed": 2, "failed": 1},
        failures=["t::x"],
        artifact_refs=["docs/release/junit-abc.xml"],
        report_hash="0" * 64,
    )
    text = format_report(run)
    assert "Acceptance abc" in text and "2 passed, 1 failed" in text and "t::x" in text
    assert callable(request_acceptance)


def test_acceptance_command_queues_a_run_under_a_grant(h: Harness) -> None:
    from tests.offline import harness as hz

    hz.drain = lambda: None  # do not execute the nested suite inside the suite
    try:
        h.event("testing", "dev", "acceptance")
    finally:
        hz.drain = drain
    drain_fast_only()
    with transaction() as s:
        job = s.execute(select(m.Job).where(m.Job.type == "run_acceptance")).scalar_one()
        grant = s.get(m.ExecutionGrant, job.grant_id)
        assert job.status == "queued" and grant is not None and grant.operation == "run_acceptance"


def drain_fast_only() -> None:
    from workers.queue import lease_one
    from workers.runner import run_job

    while (job := lease_one("fast", "t")) is not None:
        run_job(job)
    dispatch_once()


# ------------------------------------------------------------------------- live member check (D-16)


def test_live_member_check_withholds_for_unknown_member(h: Harness) -> None:
    with transaction() as s:
        room = s.execute(select(m.RoomBinding).where(m.RoomBinding.name == "af-ca-review")).scalar_one()
        room.switch_room_id = "live-ca"
        post(s, room, action_id="probe:1", body="hello CA", correlation_id="t")
    h.switch.members["live-ca"] = ["ca", "intruder"]
    dispatch_once()
    dispatch_once()  # the alert is queued during the first pass
    with transaction() as s:
        row = s.execute(select(m.Outbox).where(m.Outbox.action_id == "probe:1")).scalar_one()
        assert (row.status, row.last_error) == ("withheld", "live member check failed")
    assert any("unexpected live member(s) intruder" in x for x in h.said("ops"))
    with transaction() as s:
        room = s.execute(select(m.RoomBinding).where(m.RoomBinding.name == "af-ca-review")).scalar_one()
        post(s, room, action_id="probe:2", body="hello again", correlation_id="t")
    h.switch.members["live-ca"] = ["ca"]
    dispatch_once()
    with transaction() as s:
        row = s.execute(select(m.Outbox).where(m.Outbox.action_id == "probe:2")).scalar_one()
        assert row.status == "delivered"
