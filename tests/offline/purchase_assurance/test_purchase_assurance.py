"""U2 purchase assurance: UAT01-06, UAT08, UAT11, UAT12 against persisted records (docs/purchase-assurance-update.md).

A conversational success message is never the assertion; every check reads the database.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from sqlalchemy import select

from adapters.excel import read_cells
from adapters.storage import LocalStorage
from common.db import transaction
from common.settings import get_settings
from domain import models as m
from tests.offline.harness import Harness


@pytest.fixture()
def pa(h: Harness, monkeypatch: pytest.MonkeyPatch) -> Iterator[Harness]:
    monkeypatch.setattr(get_settings(), "PURCHASE_ASSURANCE_ENABLED", True)
    yield h


def link_state() -> str:
    with transaction() as s:
        return s.execute(select(m.PurchaseLink.purchase_state)).scalar_one()


def readiness_rows() -> list[m.PaymentReadiness]:
    with transaction() as s:
        return list(s.execute(select(m.PaymentReadiness).order_by(m.PaymentReadiness.created_at)).scalars())


def latest_run() -> m.PurchaseMatchRun:
    with transaction() as s:
        return s.execute(
            select(m.PurchaseMatchRun).order_by(m.PurchaseMatchRun.created_at.desc()).limit(1)
        ).scalar_one()


def ordered_and_invoiced(h: Harness, delivered: str = "8") -> None:
    """Order confirmed, invoice for 10 included by the CA, linked, delivery confirmed."""
    h.event("sharma", "sharma", "ok PO-101 r1")
    h.upload("sharma", "sharma", "F22_abc_invoice_10_cartons")
    h.event("sharma", "sharma", "ok INV-0001 r1")
    h.event("sharma", "sharma", "link INV-0001 PO-101")
    h.event("delivery", "suresh", f"PO-101 L1={delivered}")
    h.event("delivery", "suresh", "ok DR-0001 v1")
    h.event("ca", "ca", f"{h.open_rr('INV-0001')} include")


def test_full_purchase_story(pa: Harness) -> None:
    h = pa
    # 1 Order: the owner confirms; receivers are asked for counts without prices.
    h.event("sharma", "sharma", "ok PO-101 r1")
    assert "PO-101 r1 confirmed" in h.last("sharma")
    assert "please count what arrived" in h.last("delivery")
    # 2 Invoice: the v1.4 flow runs, then a link is proposed and confirmed.
    h.upload("sharma", "sharma", "F22_abc_invoice_10_cartons")
    h.event("sharma", "sharma", "ok INV-0001 r1")
    assert any("INV-0001 looks like PO-101" in x for x in h.said("sharma"))
    h.event("sharma", "sharma", "link INV-0001 PO-101")
    assert link_state() == "awaiting_evidence"
    # 3 Delivery: Suresh reports and confirms 8.
    h.event("delivery", "suresh", "PO-101 L1=8")
    assert "DR-0001 v1" in h.last("delivery")
    h.event("delivery", "suresh", "ok DR-0001 v1")
    assert "confirmed delivery DR-0001 v1" in "\n".join(h.said("sharma"))
    # 4 Hold: once the invoice review includes it, code finds billed 10 > received 8.
    h.event("ca", "ca", f"{h.open_rr('INV-0001')} include")
    assert h.case("INV-0001").status == "approved"
    run = latest_run()
    assert run.status == "hold"
    assert any(f["rule"] == "M03" and f.get("difference") == "2" for f in run.findings)
    assert link_state() == "needs_resolution"
    assert "payment readiness is on hold" in h.last("sharma")
    # 5 Assign: owner assigns Anil; the task view goes to a room Anil may already see.
    h.event("sharma", "sharma", "task INV-0001 anil tomorrow get a corrected invoice for 8 cartons")
    assert "TK-0001 assigned to Anil Verma" in h.said("sharma")[-1] or "TK-0001 assigned" in "\n".join(h.said("sharma"))
    h.event("sharma", "anil", "TK-0001 ack")
    h.event("sharma", "anil", "TK-0001 done supplier is sending a revised bill")
    # Merely completing a task does not clear the hold (U2 gate).
    assert latest_run().status == "hold" and link_state() == "needs_resolution"
    h.event("sharma", "sharma", "TK-0001 verify")
    assert "cannot be verified yet" in h.last("sharma")
    # 6 Correct: the replacement goes into the same case; v1.4 flow reruns.
    h.upload("sharma", "sharma", "F23_abc_corrected_8_cartons", body="corrected bill for INV-0001")
    assert h.case("INV-0001").document_generation == 2
    h.event("sharma", "sharma", "ok INV-0001 r2")
    h.event("ca", "ca", f"{h.open_rr('INV-0001')} include")
    # 7 Review: billed 8 = received 8 < ordered 10 needs the owner's explicit partial acceptance.
    assert any(f["rule"] == "M05" for f in latest_run().findings)
    h.event("sharma", "sharma", "accept-partial PO-101")
    assert "Still outstanding on PO-101: 2 carton" in h.said("sharma")[-1] or any(
        "Still outstanding on PO-101: 2 carton" in x for x in h.said("sharma")
    )
    assert latest_run().status == "pass"
    assert link_state() == "needs_resolution"  # TK-0001 still open
    h.event("sharma", "sharma", "TK-0001 verify")
    assert link_state() == "ready_for_review"
    (record,) = readiness_rows()
    assert record.status == "awaiting_review" and str(record.amount) == "4200.00"
    review = h.last("ca")
    assert review.startswith("PR-0001") and "no payment is made" in review
    # 8 Ready: reviewer signs the exact hash, then the owner authorizes the same record.
    h.event("ca", "ca", f"review PR-0001 {record.content_hash[:12]}")
    assert readiness_rows()[0].status == "awaiting_owner"
    h.event("sharma", "sharma", f"authorize PR-0001 {record.content_hash[:12]} due 2026-11-20")
    record = readiness_rows()[0]
    assert record.status == "ready_for_payment" and record.due_date == "2026-11-20"
    assert link_state() == "ready_for_payment"
    with transaction() as s:
        arts = {a.kind: a for a in s.execute(select(m.Artifact).where(m.Artifact.readiness_id == record.id)).scalars()}
        assert s.execute(select(m.Invoice.status)).scalar_one() == "approved"  # invoice state untouched (D-27)
    pack = json.loads(LocalStorage().get(arts["json"].storage_key))
    assert pack["format"] == "purchase_assurance.v1"
    assert pack["readiness"]["status"] == "ready_for_payment"
    assert pack["match"]["lines"][0]["outstanding"] == "2"
    assert [t["status"] for t in pack["tasks"]] == ["verified_complete"]
    text = json.dumps(pack).lower()
    assert "paid\"" not in text and "payment was sent" in text  # only the disclaimer mentions payment
    cells = read_cells(LocalStorage().get(arts["xlsx"].storage_key))
    assert {"Summary", "Order", "Delivery", "Purchase checks", "Assigned work"} <= set(cells)
    assert h.switch.uploads and {f.rsplit(".", 1)[1] for f in h.switch.uploads[-1][1]} == {"json", "xlsx"}
    # Receivers never saw a price anywhere in the delivery room (UAT11).
    for message in h.said("delivery"):
        assert "₹" not in message and "500" not in message


def test_receiver_and_assignee_authority(pa: Harness) -> None:
    """UAT05: receivers cannot price or approve; assignees cannot verify; owners cannot fake task work."""
    h = pa
    ordered_and_invoiced(h)
    h.event("sharma", "suresh", "link INV-0001 PO-101")
    assert "not set up to" in h.last("sharma") or "already linked" in h.last("sharma")
    h.event("sharma", "anil", "accept-partial PO-101")
    assert "not set up to accept partial deliveries" in h.last("sharma")
    h.event("sharma", "sharma", "task INV-0001 anil tomorrow get a corrected invoice")
    h.event("sharma", "anil", "TK-0001 verify")
    assert "not set up to verify or cancel tasks" in h.last("sharma")
    h.event("sharma", "sharma", "TK-0001 done I did it myself")
    assert "Only Anil Verma can update TK-0001" in h.last("sharma")
    h.event("delivery", "anil", "PO-101 L1=10")
    assert "not set up to report deliveries" in h.last("delivery")
    h.event("ca", "ca", "review PR-0001 0123456789ab")
    assert "No record PR-0001" in h.last("ca")
    with transaction() as s:
        task = s.execute(select(m.BusinessTask)).scalar_one()
        assert task.status == "open"


def test_delivery_correction_replaces_not_adds(pa: Harness) -> None:
    """UAT06: a corrected report supersedes the earlier confirmed version; replays add nothing."""
    h = pa
    ordered_and_invoiced(h, delivered="8")
    msg_id = h.event("delivery", "suresh", "DR-0001 L1=9", drain_after=True)
    h.event("delivery", "suresh", "DR-0001 L1=9", message_id=msg_id)  # replay of the same event
    h.event("delivery", "suresh", "ok DR-0001 v2")
    with transaction() as s:
        reports = list(s.execute(select(m.DeliveryReport).order_by(m.DeliveryReport.report_version)).scalars())
    assert [(r.report_version, r.status) for r in reports] == [(1, "superseded"), (2, "confirmed")]
    line = latest_run().totals["lines"][0]
    assert line["received"] == "9" and line["billed"] == "10"
    assert any(f["rule"] == "M03" and f.get("difference") == "1" for f in latest_run().findings)


def test_happy_path_full_delivery(pa: Harness) -> None:
    """UAT01: ordered 10, received 10, billed 10 at the agreed price -> reviewed and authorized, never paid."""
    h = pa
    ordered_and_invoiced(h, delivered="10")
    assert latest_run().status == "pass"
    (record,) = readiness_rows()
    h.event("sharma", "sharma", f"authorize PR-0001 {record.content_hash[:12]} due unknown")
    assert "has not been reviewed yet" in h.last("sharma")
    h.event("ca", "ca", f"review PR-0001 {record.content_hash[:12]}")
    h.event("sharma", "sharma", f"authorize PR-0001 {record.content_hash[:12]} due unknown")
    record = readiness_rows()[0]
    assert record.status == "ready_for_payment" and record.due_date is None and record.due_source == "unknown"
    assert str(record.amount) == "5250.00"


def test_stale_review_refused_when_delivery_changes(pa: Harness) -> None:
    """UAT07/UAT08: a change after review withdraws the record; the owner's authorization is refused."""
    h = pa
    ordered_and_invoiced(h, delivered="10")
    (record,) = readiness_rows()
    h.event("ca", "ca", f"review PR-0001 {record.content_hash[:12]}")
    h.event("delivery", "suresh", "DR-0001 L1=9")
    h.event("delivery", "suresh", "ok DR-0001 v2")
    assert readiness_rows()[0].status == "stale"
    assert any("Withdrawn: PR-0001" in x and "confirmed delivery changed" in x for x in h.said("ca"))
    h.event("sharma", "sharma", f"authorize PR-0001 {record.content_hash[:12]} due 2026-11-20")
    assert "no longer applies" in h.last("sharma")
    assert link_state() == "needs_resolution"


def test_one_invoice_per_order_and_wrong_supplier(pa: Harness) -> None:
    """UAT04/M08: a second invoice case cannot take the same order; a different supplier holds (M01)."""
    h = pa
    h.event("sharma", "sharma", "ok PO-101 r1")
    first = h.ingest("F01_clean_intrastate_5pct")
    h.event("sharma", "sharma", f"link {first} PO-101")
    second = h.ingest("F22_abc_invoice_10_cartons")
    h.event("sharma", "sharma", f"link {second} PO-101")
    assert "already linked" in h.last("sharma")
    with transaction() as s:
        assert len(list(s.execute(select(m.PurchaseLink)).scalars())) == 1
    assert any(f["rule"] == "M01" for f in latest_run().findings)


def test_flag_off_keeps_v14(h: Harness) -> None:
    """UAT12: with the flag off nothing is proposed or matched, and purchase commands explain the limit."""
    h.upload("sharma", "sharma", "F22_abc_invoice_10_cartons")
    h.event("sharma", "sharma", "ok INV-0001 r1")
    assert not any("looks like PO-101" in x for x in h.said("sharma"))
    h.event("sharma", "sharma", "ok PO-101 r1")
    assert "not enabled" in h.last("sharma")
    assert h.count(m.PurchaseLink) == 0 and h.count(m.PurchaseMatchRun) == 0
    assert h.case("INV-0001").status == "ready_for_ca"
