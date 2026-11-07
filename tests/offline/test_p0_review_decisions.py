"""Live Telegram regressions T-11: reopening approved cases and permitted warning overrides."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from common.db import transaction
from domain import models as m
from tests.offline.harness import Harness


def _approved_case(h: Harness) -> str:
    ref = h.ingest("F01_clean_intrastate_5pct")
    h.event("ca", "ca", f"{h.open_rr(ref)} include")
    assert h.case(ref).status == "approved"
    return ref


def _warning_only_case(h: Harness) -> str:
    """As in the live run: a near-duplicate whose number was corrected, leaving only R-DUP-02 failed."""
    h.ingest("F10_duplicate_original")
    ref = h.ingest("F11_duplicate_copy")
    h.event("sharma", "sharma", f"{ref} number=SDF-5521")
    h.event("sharma", "sharma", f"ok {ref} r2")
    assert h.case(ref).status == "ready_for_ca"
    return ref





def test_reopen_approved_case_withdraws_approval_and_keeps_history(h: Harness) -> None:
    ref = _approved_case(h)
    h.event("ca", "ca", f"reopen {ref} recheck after supplier call")
    assert "reopened" in " ".join(h.said("ca")[-4:])
    case = h.case(ref)
    assert case.status == "ready_for_ca"
    with transaction() as s:
        decisions = {
            d.action: d for d in s.execute(select(m.Decision).where(m.Decision.invoice_id == case.id)).scalars()
        }
        invalidated = set(s.execute(select(m.DecisionInvalidation.decision_id)).scalars())
        runs = s.execute(select(m.CheckRun).where(m.CheckRun.revision_id == case.current_revision_id)).scalars().all()
    assert decisions["include"].id in invalidated, "the old approval stays in history, invalidated"
    assert decisions["reopen"].id not in invalidated, "the reopen itself is still valid"
    assert len(runs) == 2, "checks rerun exactly once"
    rr = h.open_rr(ref)
    h.event("ca", "ca", f"{rr} include")
    assert h.case(ref).status == "approved"


def test_reopen_makes_a_draft_pack_stale_and_outdates_an_approved_pack(h: Harness) -> None:
    ref = _approved_case(h)
    h.event("ca", "ca", "snapshot sharma 2026-11")
    with transaction() as s:
        digest = s.execute(select(m.Snapshot)).scalar_one().content_hash
    h.event("ca", "ca", f"reopen {ref} recheck")
    h.event("ca", "ca", f"approve SN-0001 {digest[:12]}")
    with transaction() as s:
        statuses = {x.public_ref: x.status for x in s.execute(select(m.Snapshot)).scalars()}
    assert statuses["SN-0001"] == "stale"


def test_second_reopen_is_refused_cleanly(h: Harness) -> None:
    ref = _approved_case(h)
    h.event("ca", "ca", f"reopen {ref} recheck")
    status = h.case(ref).status
    h.event("ca", "ca", f"reopen {ref} again")
    assert h.case(ref).status == status
    assert "not allowed" in h.last("ca")


def test_owner_cannot_reopen(h: Harness) -> None:
    ref = _approved_case(h)
    h.event("sharma", "sharma", f"reopen {ref} no")
    assert h.case(ref).status == "approved"





def test_warning_override_from_ready_for_ca_is_recorded_and_exported(h: Harness) -> None:
    ref = _warning_only_case(h)
    rr = h.open_rr(ref)
    assert "override R-DUP-02" in next(x for x in reversed(h.said("ca")) if x.startswith(rr))
    h.event("ca", "ca", f"{rr} override R-DUP-02 confirmed separate deliveries")
    case = h.case(ref)
    assert case.status == "approved"
    assert "R-DUP-02" in h.last("ca")
    with transaction() as s:
        issue = s.execute(
            select(m.Issue).where(m.Issue.revision_id == case.current_revision_id, m.Issue.rule_id == "R-DUP-02")
        ).scalar_one()
        assert (issue.status, issue.disposition) == ("resolved", "override")
        decision = s.execute(
            select(m.Decision).where(m.Decision.invoice_id == case.id, m.Decision.action == "include_with_override")
        ).scalar_one()
        assert decision.target_issue_id == issue.id
        assert decision.reason == "confirmed separate deliveries"
        assert decision.revision_id == case.current_revision_id
    h.event("ca", "ca", "snapshot sharma 2026-11")
    with transaction() as s:
        snap = s.execute(select(m.Snapshot).order_by(m.Snapshot.version.desc())).scalars().first()
        assert snap is not None
        included = {e["case_ref"]: e for e in snap.manifest["included"]}
    assert {"rule_id": "R-DUP-02", "disposition": "override"} in included[ref]["overrides"]


def test_override_refuses_unknown_and_unrelated_rules_without_a_decision(h: Harness) -> None:
    ref = _warning_only_case(h)
    rr = h.open_rr(ref)
    for bad in ("R-FAKE-99", "R-PART-01", "R-DUP-02,R-FAKE-99"):
        h.event("ca", "ca", f"{rr} override {bad} because")
        assert "no open issue" in h.last("ca")
        assert h.case(ref).status == "ready_for_ca"
    with transaction() as s:
        assert not s.execute(select(m.Decision).where(m.Decision.action == "include_with_override")).first()


@pytest.mark.parametrize(
    ("fixture", "rule"),
    [("F09_total_mismatch", "R-AMT-03"), ("F08_wrong_tax_type", "R-TAX-01")],
)
def test_non_overridable_rules_stay_refused(h: Harness, fixture: str, rule: str) -> None:
    ref = h.ingest(fixture)
    h.event("ca", "ca", f"{h.open_rr(ref)} override {rule} looks fine")
    assert "never overridable" in h.last("ca")
    assert h.case(ref).status == "needs_resolution"


def test_exact_duplicate_stays_refused_even_when_named_with_the_warning(h: Harness) -> None:
    h.ingest("F10_duplicate_original")
    ref = h.ingest("F11_duplicate_copy")
    h.event("ca", "ca", f"{h.open_rr(ref)} override R-DUP-01,R-DUP-02 same goods")
    assert "never overridable" in h.last("ca")
    assert h.case(ref).status == "needs_resolution"


def test_reopen_drops_an_earlier_override_until_the_ca_decides_again(h: Harness) -> None:
    ref = _warning_only_case(h)
    h.event("ca", "ca", f"{h.open_rr(ref)} override R-DUP-02 confirmed separate deliveries")
    h.event("ca", "ca", f"reopen {ref} recheck")
    case = h.case(ref)
    assert case.status == "ready_for_ca"
    with transaction() as s:
        issue = s.execute(
            select(m.Issue).where(m.Issue.revision_id == case.current_revision_id, m.Issue.rule_id == "R-DUP-02")
        ).scalar_one()
        assert issue.status == "awaiting_ca"



def test_manifest_is_json_serialisable_after_override(h: Harness) -> None:
    ref = _warning_only_case(h)
    h.event("ca", "ca", f"{h.open_rr(ref)} override R-DUP-02 separate")
    h.event("ca", "ca", "snapshot sharma 2026-11")
    with transaction() as s:
        snap = s.execute(select(m.Snapshot)).scalars().first()
        assert snap is not None
        assert json.dumps(snap.manifest)
