"""D-31: owner and CA in one shop group, with the private CA room kept for packs and the multi-shop view."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import select

from common.db import transaction
from domain import models as m
from scripts import admin
from tests.offline.harness import Harness


@pytest.fixture()
def shared(h: Harness) -> Iterator[Harness]:
    admin.shared_review("sharma", "on")
    yield h


def _wrong_tax(h: Harness) -> str:
    return h.ingest("F08_wrong_tax_type")


def _statuses(h: Harness, ref: str) -> str:
    return h.case(ref).status


# ------------------------------------------------------------------------ review happens in the group


def test_review_request_appears_in_the_group_with_a_labelled_suggestion(shared: Harness) -> None:
    ref = _wrong_tax(shared)
    rr = shared.open_rr(ref)
    review = next(x for x in shared.said("sharma") if x.startswith(rr))
    assert "R-TAX-01" in review
    assert "Suggestion from the checks, not a decision: request a corrected invoice" in review
    assert "Priya, your decision." in review


def test_a_clean_bill_goes_to_the_ca_with_no_forwarding(shared: Harness) -> None:
    ref = shared.ingest("F01_clean_intrastate_5pct")
    assert _statuses(shared, ref) == "ready_for_ca"
    rr = shared.open_rr(ref)
    assert any(x.startswith(rr) and "include it" in x for x in shared.said("sharma"))


def test_private_room_gets_a_pointer_without_the_details(shared: Harness) -> None:
    ref = _wrong_tax(shared)
    rr = shared.open_rr(ref)
    note = next(x for x in shared.said("ca") if rr in x)
    assert "posted in the shop's group" in note
    assert "R-TAX-01" not in note


def test_ca_decides_in_the_group_and_can_still_decide_in_private(shared: Harness) -> None:
    first = shared.ingest("F01_clean_intrastate_5pct")
    shared.event("sharma", "ca", f"{shared.open_rr(first)} include")
    assert _statuses(shared, first) == "approved"
    second = shared.ingest("F02_clean_scan_12pct")
    shared.event("ca", "ca", f"{shared.open_rr(second)} include")
    assert _statuses(shared, second) == "approved"


def test_full_correction_story_in_one_group(shared: Harness) -> None:
    ref = _wrong_tax(shared)
    rr = shared.open_rr(ref)
    shared.event("sharma", "ca", f"{rr} supplier please reissue with IGST")
    assert any("Dear Pune Electricals" in x for x in shared.said("sharma"))
    shared.event("sharma", "sharma", f"corrected bill for {ref}", files=["F16_replacement_for_F08"])
    shared.event("sharma", "sharma", f"ok {ref} r2")
    assert _statuses(shared, ref) == "ready_for_ca"
    shared.event("sharma", "ca", f"{rr} include")
    assert "older version" in shared.last("sharma")
    assert _statuses(shared, ref) == "ready_for_ca"
    shared.event("sharma", "ca", f"{shared.open_rr(ref)} include")
    assert _statuses(shared, ref) == "approved"


def test_withdrawal_notice_appears_where_the_review_was(shared: Harness) -> None:
    ref = _wrong_tax(shared)
    rr = shared.open_rr(ref)
    shared.upload("sharma", "sharma", "F16_replacement_for_F08", f"corrected bill for {ref}")
    assert any("Withdrawn" in x and rr in x for x in shared.said("sharma"))


def test_threaded_reply_to_the_review_request_decides_it(shared: Harness) -> None:
    ref = shared.ingest("F01_clean_intrastate_5pct")
    with transaction() as s:
        row = s.execute(select(m.Outbox).where(m.Outbox.action_id.like("review:%"))).scalar_one()
        event_id = row.delivered_event_id
    shared.event("sharma", "ca", "include", thread_id=event_id)
    assert _statuses(shared, ref) == "approved"


# -------------------------------------------------------------------------------------- authority


def test_owner_cannot_decide_in_the_group(shared: Harness) -> None:
    ref = shared.ingest("F01_clean_intrastate_5pct")
    shared.event("sharma", "sharma", f"{shared.open_rr(ref)} include")
    assert _statuses(shared, ref) == "ready_for_ca"
    assert "Only the CA" in shared.last("sharma")


def test_owner_cannot_reopen_in_the_group(shared: Harness) -> None:
    ref = shared.ingest("F01_clean_intrastate_5pct")
    shared.event("sharma", "ca", f"{shared.open_rr(ref)} include")
    shared.event("sharma", "sharma", f"reopen {ref} please")
    assert _statuses(shared, ref) == "approved"


def test_ca_cannot_confirm_or_correct_bill_details(shared: Harness) -> None:
    shared.upload("sharma", "sharma", "F01_clean_intrastate_5pct")
    ref = shared.latest_case().case_ref
    shared.event("sharma", "ca", f"ok {ref} r1")
    assert _statuses(shared, ref) == "needs_confirmation"
    shared.event("sharma", "ca", f"{ref} total=1.00")
    with transaction() as s:
        case = s.execute(select(m.Invoice).where(m.Invoice.case_ref == ref)).scalar_one()
        rev = s.get(m.InvoiceRevision, case.current_revision_id)
        assert rev is not None and rev.revision_no == 1


def test_ca_cannot_decide_another_shops_request_from_this_group(shared: Harness) -> None:
    ref = shared.ingest("F19_gupta_interstate", shop="gupta")
    rr = shared.open_rr(ref)
    before = _statuses(shared, ref)
    shared.event("sharma", "ca", f"{rr} include")
    assert _statuses(shared, ref) == before
    assert "Gupta" not in shared.last("sharma")
    shared.event("sharma", "ca", f"reopen {ref} no")
    assert _statuses(shared, ref) == before


def test_stranger_is_still_refused(shared: Harness) -> None:
    ref = shared.ingest("F01_clean_intrastate_5pct")
    shared.event("sharma", "stranger", f"{shared.open_rr(ref)} include")
    assert _statuses(shared, ref) == "ready_for_ca"


# ------------------------------------------------------------------------------- conversation is safe


@pytest.mark.parametrize(
    "chat",
    [
        "yes",
        "ok",
        "yes, please call him",
        "ok thanks",
        "why is this so late?",
        "status of the delivery?",
        "help me understand this",
        "should we exclude this one?",
        "please include the transport charge",
        "supplier said tomorrow",
        "total=500 sounds wrong",
    ],
)
def test_ordinary_conversation_does_nothing(shared: Harness, chat: str) -> None:
    ref = shared.ingest("F01_clean_intrastate_5pct")
    shared.upload("sharma", "sharma", "F02_clean_scan_12pct")
    awaiting = shared.latest_case().case_ref
    before = len(shared.said("sharma"))
    shared.event("sharma", "sharma", chat)
    shared.event("sharma", "ca", chat)
    assert len(shared.said("sharma")) == before, "the agent stays quiet during conversation"
    assert _statuses(shared, awaiting) == "needs_confirmation"
    assert _statuses(shared, ref) == "ready_for_ca"


@pytest.mark.parametrize("chat", ["{ref} looks wrong to me", "ok {ref} looks odd", "RR-0001 seems fine, should we include?"])
def test_mentioning_a_reference_in_conversation_does_nothing(shared: Harness, chat: str) -> None:
    ref = shared.ingest("F01_clean_intrastate_5pct")
    shared.upload("sharma", "sharma", "F02_clean_scan_12pct")
    awaiting = shared.latest_case().case_ref
    shared.event("sharma", "sharma", chat.format(ref=awaiting))
    shared.event("sharma", "ca", chat.format(ref=awaiting))
    assert _statuses(shared, awaiting) == "needs_confirmation"
    assert _statuses(shared, ref) == "ready_for_ca"


def test_results_can_be_brought_up_in_the_group(shared: Harness) -> None:
    ref = _wrong_tax(shared)
    shared.event("sharma", "ca", f"why is {ref} on hold?")
    assert ref in shared.last("sharma")
    shared.event("sharma", "sharma", "status")
    assert "Sharma" in shared.last("sharma") or ref in shared.last("sharma")


# ---------------------------------------------------------------------- what stays where, and the default


def test_monthly_pack_stays_in_the_private_room(shared: Harness) -> None:
    ref = shared.ingest("F01_clean_intrastate_5pct")
    shared.event("sharma", "ca", f"{shared.open_rr(ref)} include")
    shared.event("sharma", "ca", "snapshot sharma 2026-11")
    with transaction() as s:
        assert not s.execute(select(m.Snapshot)).first(), "a pack can't be built from the shared group"
    shared.event("ca", "ca", "snapshot sharma 2026-11")
    with transaction() as s:
        digest = s.execute(select(m.Snapshot)).scalar_one().content_hash
    assert any(x.startswith("SN-0001") for x in shared.said("ca"))
    assert not any(x.startswith("SN-0001") for x in shared.said("sharma"))
    shared.event("sharma", "ca", f"approve SN-0001 {digest[:12]}")
    with transaction() as s:
        assert s.execute(select(m.Snapshot)).scalar_one().status == "awaiting_ca"
    shared.event("ca", "ca", f"approve SN-0001 {digest[:12]}")
    assert shared.switch.uploads and all(room == "unbound:af-ca-review" for room, _, _ in shared.switch.uploads)


def test_two_room_shops_are_unchanged(h: Harness) -> None:
    ref = _wrong_tax(h)
    rr = h.open_rr(ref)
    assert not any(x.startswith(rr) for x in h.said("sharma"))
    assert any(x.startswith(rr) and "Suggestion" not in x for x in h.said("ca"))
    h.event("sharma", "ca", f"{rr} supplier reissue")
    assert not any("Dear Pune" in x for x in h.said("sharma"))


def test_other_shops_are_unaffected_by_one_shop_opting_in(shared: Harness) -> None:
    ref = shared.ingest("F19_gupta_interstate", shop="gupta")
    rr = shared.open_rr(ref)
    assert not any(rr in x for x in shared.said("gupta"))
    assert not any(rr in x for x in shared.said("sharma"))
    assert any(x.startswith(rr) for x in shared.said("ca"))


def test_switching_is_audited_and_refuses_unknown_shops(h: Harness) -> None:
    admin.shared_review("sharma", "on")
    with transaction() as s:
        assert s.execute(select(m.AuditEvent).where(m.AuditEvent.action == "shop.shared_review")).scalar_one()
    with pytest.raises(SystemExit, match="No shop"):
        admin.shared_review("nobody", "on")
