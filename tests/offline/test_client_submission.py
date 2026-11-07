"""D-32: a client drops a bill in a submission room, sees only "received", and the owner still confirms it."""

from __future__ import annotations

import re
from collections.abc import Iterator

import pytest
from sqlalchemy import select

from common.db import transaction
from domain import models as m
from scripts import admin
from tests.offline.harness import Harness

FIXTURE = "F01_clean_intrastate_5pct"
CASE_DETAILS = re.compile(r"INV-\d|RR-\d|R-\d{4}|₹|GSTIN|Modern Agro")


@pytest.fixture()
def client(h: Harness) -> Iterator[Harness]:
    admin.shared_review("sharma", "on")
    yield h


def test_client_bill_reaches_the_owner_and_then_the_ca(client: Harness) -> None:
    client.upload("submit", "client", FIXTURE)
    ref = client.latest_case().case_ref
    assert client.case(ref).status == "needs_confirmation"
    group = " ".join(client.said("sharma"))
    assert "Verma Supplies sent" in group
    assert f"{ref} r1: please check these details" in group
    client.event("sharma", "sharma", f"ok {ref} r1")
    assert client.case(ref).status == "ready_for_ca"
    assert any(x.startswith(client.open_rr(ref)) for x in client.said("sharma"))


def test_client_only_ever_sees_received(client: Harness) -> None:
    client.upload("submit", "client", FIXTURE)
    ref = client.latest_case().case_ref
    client.event("sharma", "sharma", f"ok {ref} r1")
    said = client.said("submit")
    assert said == [f"Received {FIXTURE}.pdf. Thank you, it has gone to the shop for review."]
    assert not CASE_DETAILS.search(" ".join(said))


def test_duplicate_tells_the_client_nothing_about_the_case(client: Harness) -> None:
    client.upload("submit", "client", FIXTURE)
    count = len(client.cases())
    client.upload("submit", "client", FIXTURE)
    assert len(client.cases()) == count
    assert "already been received" in client.last("submit")
    assert not CASE_DETAILS.search(" ".join(client.said("submit")))


def test_bill_the_owner_already_sent_is_not_revealed(client: Harness) -> None:
    client.upload("sharma", "sharma", FIXTURE)
    client.upload("submit", "client", FIXTURE)
    assert not CASE_DETAILS.search(" ".join(client.said("submit")))


@pytest.mark.parametrize("text", ["status", "pending", "orders", "ok INV-0001 r1", "INV-0001 total=1.00", "why-held INV-0001"])
def test_client_commands_do_nothing_and_reply_nothing(client: Harness, text: str) -> None:
    client.upload("submit", "client", FIXTURE)
    before = list(client.said("submit"))
    client.event("submit", "client", text)
    assert client.said("submit") == before
    assert client.latest_case().status == "needs_confirmation"


def test_client_cannot_confirm_in_the_shop_group_or_upload_there(client: Harness) -> None:
    client.upload("submit", "client", FIXTURE)
    ref = client.latest_case().case_ref
    client.event("sharma", "client", f"ok {ref} r1")
    assert client.case(ref).status == "needs_confirmation"
    count = len(client.cases())
    client.upload("sharma", "client", "F02_clean_scan_12pct")
    assert len(client.cases()) == count


def test_client_cannot_replace_a_case_by_naming_it(client: Harness) -> None:
    client.upload("submit", "client", FIXTURE)
    ref = client.latest_case().case_ref
    generation = client.case(ref).document_generation
    client.upload("submit", "client", "F02_clean_scan_12pct", f"corrected bill for {ref}")
    assert client.case(ref).document_generation == generation
    assert len(client.cases()) == 2


def test_stranger_and_people_without_the_capability_are_refused(client: Harness) -> None:
    client.upload("submit", "stranger", FIXTURE)
    client.upload("submit", "anil", FIXTURE)
    client.upload("submit", "ca", FIXTURE)
    assert client.cases() == []
    assert not any("Received" in x for x in client.said("submit"))


def test_revoking_the_capability_stops_submission(client: Harness) -> None:
    with transaction() as s:
        s.execute(select(m.ShopCapability).where(m.ShopCapability.capability == "invoice_submit")).scalar_one()
        cap = s.execute(select(m.ShopCapability).where(m.ShopCapability.capability == "invoice_submit")).scalar_one()
        cap.revoked_at = m.utcnow()
    client.upload("submit", "client", FIXTURE)
    assert client.cases() == []


def test_failed_download_tells_the_client(client: Harness) -> None:
    client.event("submit", "client", "_attachment not relayed: bill.pdf — download failed: Timed out_")
    assert "couldn't download bill.pdf" in client.last("submit")
    assert client.cases() == []


def test_works_for_a_two_room_shop_too(h: Harness) -> None:
    h.upload("submit", "client", FIXTURE)
    ref = h.latest_case().case_ref
    h.event("sharma", "sharma", f"ok {ref} r1")
    rr = h.open_rr(ref)
    assert any(x.startswith(rr) for x in h.said("ca"))
    assert not any(x.startswith(rr) for x in h.said("sharma"))


def test_client_room_rejects_an_unauthorized_member(h: Harness) -> None:
    with transaction() as s:
        room = s.execute(select(m.RoomBinding).where(m.RoomBinding.name == "af-submit-sharma")).scalar_one()
        room.switch_room_id = "live-submit"
    h.switch.members["live-submit"] = ["client", "intruder"]
    from tests.offline.harness import ROOMS

    ROOMS["submit"], old = "live-submit", ROOMS["submit"]
    try:
        h.upload("submit", "client", FIXTURE)
        assert h.said("submit") == []
    finally:
        ROOMS["submit"] = old


def test_add_client_is_idempotent_and_works_on_an_existing_database(h: Harness) -> None:
    admin.add_client("sharma", "client.new", "New Supplier")
    admin.add_client("sharma", "client.new", "New Supplier")
    with transaction() as s:
        user = s.execute(select(m.User).where(m.User.handle == "client.new")).scalar_one()
        assert user.role == "client"
        caps = s.execute(select(m.ShopCapability).where(m.ShopCapability.user_id == user.id)).scalars().all()
        assert [c.capability for c in caps] == ["invoice_submit"]
    with pytest.raises(SystemExit, match="already exists with role owner"):
        admin.add_client("sharma", "owner.sharma", "Nope")
