"""Workflow, authority, isolation and replay scenarios (P1-21, P3-11..13, T02-T08, R05, R06, R09)."""

from __future__ import annotations

from sqlalchemy import select

from common.db import transaction
from domain import models as m
from tests.offline.harness import Harness


def test_sample_interaction_a108_correction_then_supplier_replacement(h: Harness) -> None:
    # A108: total misread as 1,780; the owner corrects it to 1,180 by typing (no re-extraction).
    h.upload("sharma", "sharma", "F13_blurry_photo")
    summary = h.last("sharma")
    assert "Total: ₹1,780.00  <- uncertain (page 1)" in summary
    h.event("sharma", "sharma", "INV-0001 total=1180.00")
    assert h.case("INV-0001").status == "needs_confirmation"
    assert "INV-0001 r2: please check" in h.said("sharma")[-2]
    assert h.last("sharma") == "INV-0001 corrected (r2); the new summary follows."
    with transaction() as s:
        assert len(list(s.execute(select(m.Job).where(m.Job.type == "extract_document")).scalars())) == 1
    h.event("sharma", "sharma", "ok INV-0001 r2")
    assert h.case("INV-0001").status == "ready_for_ca"

    # Wrong tax type -> CA -> ask supplier -> replacement in the same case -> recheck -> include.
    ref = h.ingest("F08_wrong_tax_type")
    assert h.case(ref).status == "needs_resolution"
    assert h.results(ref)["R-TAX-01"] == "fail"
    rr = h.open_rr(ref)
    assert "R-TAX-01" in h.last("ca") and "tax amount associated with this issue" in h.last("ca")
    h.event("ca", "ca", f"{rr} supplier please reissue with IGST for this interstate supply")
    assert "Draft you can send" in h.last("sharma")
    assert set(h.issues(ref).values()) == {"awaiting_supplier"}

    old_generation = h.case(ref).document_generation
    h.upload("sharma", "sharma", "F16_replacement_for_F08", body=f"corrected bill for {ref}")
    case = h.case(ref)
    assert case.document_generation == old_generation + 1
    assert case.status == "needs_confirmation"
    assert len(h.cases()) == 2  # same case, no new invoice
    assert set(h.issues(ref, current_only=False).values()) == {"superseded"}
    h.event("sharma", "sharma", f"ok {ref}")
    assert h.case(ref).status == "ready_for_ca"

    # The old review request is stale; deciding it fails and changes nothing.
    h.event("ca", "ca", f"{rr} include")
    assert "older version" in h.last("ca") or "earlier version" in h.last("ca")
    new_rr = h.open_rr(ref)
    assert new_rr != rr
    h.event("ca", "ca", f"{new_rr} include")
    assert h.case(ref).status == "approved"


def test_owner_and_strangers_cannot_decide_as_ca(h: Harness) -> None:
    ref = h.ingest("F01_clean_intrastate_5pct")
    rr = h.open_rr(ref)
    # Switch room membership is not authority: an owner posting in the CA room is still refused.
    h.event("ca", "sharma", f"{rr} include")
    assert "not authorized" in h.last("ca").lower() or "only cas" in h.last("ca").lower()
    assert h.case(ref).status == "ready_for_ca"
    with transaction() as s:
        denied = s.execute(select(m.AuditEvent).where(m.AuditEvent.outcome == "denied")).scalars().all()
        assert denied
    # A stranger is unmapped: rejected inbox outcome and denied audit, no state change.
    h.event("ca", "stranger", f"{rr} include")
    with transaction() as s:
        outcomes = [
            e.outcome for e in s.execute(select(m.InboxEvent).order_by(m.InboxEvent.received_at)).scalars()
        ]
    assert outcomes[-1] == "rejected"
    assert h.case(ref).status == "ready_for_ca"


def test_ambiguous_approve_asks_for_clarification(h: Harness) -> None:
    h.ingest("F01_clean_intrastate_5pct")
    h.event("ca", "ca", "include")
    assert h.last("ca").startswith("Which review request?")
    assert h.case("INV-0001").status == "ready_for_ca"


def test_shop_isolation_in_chat(h: Harness) -> None:
    ref = h.ingest("F01_clean_intrastate_5pct")
    h.event("gupta", "gupta", f"why-held {ref}")
    assert "could not find" in h.last("gupta").lower()
    h.event("gupta", "gupta", f"ok {ref}")
    assert "could not find" in h.last("gupta").lower()
    h.event("gupta", "gupta", f"{ref} total=1.00")
    assert h.case(ref).status == "ready_for_ca"
    h.event("gupta", "gupta", "status")
    assert ref not in h.last("gupta")
    assert "No cases for Gupta Hardware" in h.last("gupta")
    # Gupta's owner cannot upload into Sharma's room either.
    h.upload("sharma", "gupta", "F18_gupta_photo_clean")
    assert "only this shop's owner" in h.last("sharma").lower()


def test_replayed_event_creates_one_receipt_and_one_case(h: Harness) -> None:
    msg_id = h.event("sharma", "sharma", files=["F01_clean_intrastate_5pct"])
    h.event("sharma", "sharma", files=["F01_clean_intrastate_5pct"], message_id=msg_id)
    assert h.count(m.Receipt) == 1
    assert h.count(m.Invoice) == 1
    # The same file sent again as a new message is linked to the existing case, not a new one.
    h.upload("sharma", "sharma", "F01_clean_intrastate_5pct")
    assert h.count(m.Invoice) == 1
    assert "same file as INV-0001" in h.last("sharma")


def test_invalid_files_create_no_case(h: Harness) -> None:
    h.raw_upload("sharma", "sharma", b"hello, I am not an invoice", "notes.txt")
    assert "not accepted" in h.last("sharma")
    h.raw_upload("sharma", "sharma", b"%PDF-1.4 broken", "broken.pdf")
    assert "not accepted" in h.last("sharma")
    assert h.count(m.Invoice) == 0
    with transaction() as s:
        assert {r.status for r in s.execute(select(m.Receipt)).scalars()} == {"rejected_file"}


def test_exact_duplicate_blocks_second_case(h: Harness) -> None:
    first = h.ingest("F10_duplicate_original")
    second = h.ingest("F11_duplicate_copy")
    assert h.case(first).status == "ready_for_ca"
    assert h.case(second).status == "needs_resolution"
    results = h.results(second)
    assert results["R-DUP-01"] == "fail" and results["R-DUP-02"] == "fail"
    rr = h.open_rr(second)
    h.event("ca", "ca", f"{rr} exclude duplicate of {first}")
    assert h.case(second).status == "excluded"


def test_corrected_invoice_is_not_a_duplicate_of_its_older_revision(h: Harness) -> None:
    ref = h.ingest("F01_clean_intrastate_5pct")
    h.event("sharma", "sharma", f'{ref} supplier="Modern Agro Staples Private Ltd"')
    h.event("sharma", "sharma", f"ok {ref}")
    assert h.results(ref)["R-DUP-01"] == "pass"
    assert h.case(ref).status == "ready_for_ca"


def test_stale_confirmation_is_rejected(h: Harness) -> None:
    h.upload("sharma", "sharma", "F01_clean_intrastate_5pct")
    h.event("sharma", "sharma", "INV-0001 date=2026-11-02")
    h.event("sharma", "sharma", "ok INV-0001 r1")
    assert "older version" in h.last("sharma")
    assert h.case("INV-0001").status == "needs_confirmation"


def test_owner_gap_routes_to_owner_and_ca_issue_to_ca(h: Harness) -> None:
    h.upload("sharma", "sharma", "F07_missing_gstin")
    ref = h.latest_case().case_ref
    h.event("sharma", "sharma", f"ok {ref}")
    assert "or reply `ok INV-0001 hold`" in h.last("sharma")
    h.event("sharma", "sharma", f"ok {ref} hold")
    assert "needs one thing from you" in h.last("sharma")
    assert h.issues(ref)["R-GSTIN-01"] == "awaiting_owner"
    h.event("sharma", "sharma", f"{ref} gstin={_gstin('07', 'ROYAL2222B')}")
    h.event("sharma", "sharma", f"ok {ref}")
    assert h.case(ref).status == "ready_for_ca"


def test_resolvable_issue_and_non_resolvable_issue(h: Harness) -> None:
    hsn = h.ingest("F20_gupta_missing_hsn", shop="gupta")
    rr = h.open_rr(hsn)
    h.event("ca", "ca", f"{rr} resolve R-PART-01 HSN 7318 confirmed on page 1 of the delivery note")
    assert h.case(hsn).status == "ready_for_ca"
    h.event("ca", "ca", f"{h.open_rr(hsn)} include")
    assert h.case(hsn).status == "approved"

    bad = h.ingest("F09_total_mismatch")
    rr = h.open_rr(bad)
    h.event("ca", "ca", f"{rr} resolve R-AMT-03 looks fine to me")
    assert "cannot be resolved" in h.last("ca")
    assert h.case(bad).status == "needs_resolution"


def test_unsupported_document_is_held_for_ca(h: Harness) -> None:
    ref = h.ingest("F15_credit_note")
    assert h.case(ref).status == "needs_resolution"
    assert h.results(ref)["R-DOC-01"] == "unsupported"


def test_handoff_is_data_only_and_deduplicated(h: Harness) -> None:
    ref = h.ingest("F08_wrong_tax_type")
    with transaction() as s:
        handoffs = list(s.execute(select(m.Handoff)).scalars())
    assert len(handoffs) == 1
    assert handoffs[0].responsible_role == "ca" and handoffs[0].hop_count == 1
    assert ref and handoffs[0].next_action.startswith("Decide RR-")


def test_prompt_injection_in_invoice_text_changes_nothing(h: Harness) -> None:
    """Our own room messages echo back (they contain RR ids); they are ignored, never executed."""
    ref = h.ingest("F01_clean_intrastate_5pct")
    with transaction() as s:
        review = s.execute(select(m.Outbox).where(m.Outbox.action_id.like("review:%"))).scalar_one()
        echo_id, body = review.delivered_event_id, review.body
    h.event("ca", "ca", body, message_id=echo_id)
    assert h.case(ref).status == "ready_for_ca"
    with transaction() as s:
        echo = s.execute(select(m.InboxEvent).where(m.InboxEvent.event_id == echo_id)).scalar_one()
    assert (echo.outcome, echo.outcome_reason) == ("ignored", "agent_message")


def _gstin(state: str, pan: str) -> str:
    from rules.gstin import make_gstin

    return make_gstin(state, pan)
