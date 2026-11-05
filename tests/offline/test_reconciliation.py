"""Phase 6 GSTR-2B import and reconciliation (P6-01..05, P6-08)."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from common.db import transaction
from domain import models as m
from rules import reconcile as rc
from rules.types import Tolerances
from tests.offline.harness import Harness

FIX = Path(__file__).resolve().parents[2] / "seed" / "fixtures"
TOL = Tolerances(Decimal("0.01"), Decimal("1.00"))


def _setup(h: Harness) -> None:
    for name in (
        "F01_clean_intrastate_5pct",
        "F04_clean_interstate_18pct",
        "F05_clean_round_off",
        "F10_duplicate_original",
    ):
        h.ingest(name)


def _gstr2b(h: Harness, ext: str = "json", period: str = "2026-11", who: str = "ca") -> None:
    data = (FIX / f"gstr2b_sharma_2026-11.{ext}").read_bytes()
    h.raw_upload("ca", who, data, f"gstr2b.{ext}", body=f"gstr2b sharma {period}")


def _latest_results() -> list[m.ReconciliationResult]:
    with transaction() as s:
        run = s.execute(
            select(m.ReconciliationRun).order_by(m.ReconciliationRun.created_at.desc()).limit(1)
        ).scalar_one()
        return list(
            s.execute(select(m.ReconciliationResult).where(m.ReconciliationResult.run_id == run.id)).scalars()
        )


def test_every_class_and_one_to_one(h: Harness) -> None:
    _setup(h)
    _gstr2b(h)
    results = _latest_results()
    counts = Counter(r.class_ for r in results)
    assert counts == {
        "exact_match": 1,
        "mismatch": 1,
        "purchase_only": 1,
        "statement_only": 1,
        "ambiguous": 3,
    }
    by_case = {r.case_ref: r for r in results if r.case_ref}
    assert by_case["INV-0001"].class_ == "exact_match"
    assert by_case["INV-0002"].class_ == "mismatch" and by_case["INV-0002"].differences["igst"] == "50.00"
    assert by_case["INV-0003"].class_ == "purchase_only"
    lines = [r.statement_line_id for r in results if r.statement_line_id]
    revisions = [r.revision_id for r in results if r.revision_id]
    assert len(lines) == len(set(lines)) == 5 and len(revisions) == len(set(revisions)) == 4
    summary = h.last("ca")
    assert summary.startswith("RC-0001 · GSTR-2B reconciliation")
    assert "INV-0003 is not in GSTR-2B" in summary and "not an ITC eligibility decision" in summary
    assert any("Skipped sections" in x and "cdnr" in x for x in h.said("ca"))


def test_repeated_import_is_idempotent_and_excel_matches_json(h: Harness) -> None:
    _setup(h)
    _gstr2b(h)
    _gstr2b(h)
    assert "already imported as ST-0001" in h.last("ca")
    assert h.count(m.Statement) == 1 and h.count(m.ReconciliationRun) == 1
    json_classes = sorted((r.case_ref or "", r.class_) for r in _latest_results())
    _gstr2b(h, "xlsx")
    assert h.count(m.Statement) == 2
    assert sorted((r.case_ref or "", r.class_) for r in _latest_results()) == json_classes


def test_wrong_period_or_gstin_is_rejected(h: Harness) -> None:
    _gstr2b(h, period="2026-10")
    assert "covers 2026-11, not 2026-10" in h.last("ca")
    data = (
        (FIX / "gstr2b_sharma_2026-11.json").read_text("utf-8").replace("07SHARM9999K1ZU", "27GUPTA8888L1ZA")
    )
    h.raw_upload("ca", "ca", data.encode(), "g.json", body="gstr2b sharma 2026-11")
    assert "is for GSTIN 27GUPTA8888L1ZA" in h.last("ca")
    h.raw_upload("ca", "ca", b"not a statement", "g.txt", body="gstr2b sharma 2026-11")
    assert "not imported" in h.last("ca")
    assert h.count(m.Statement) == 0


def test_only_assigned_ca_can_import(h: Harness) -> None:
    _gstr2b(h, who="sharma")
    assert "not authorized" in h.last("ca").lower()
    assert h.count(m.Statement) == 0


def test_recon_command_reports_latest_run(h: Harness) -> None:
    h.event("ca", "ca", "recon sharma 2026-11")
    assert "No GSTR-2B reconciliation" in h.last("ca")
    _setup(h)
    _gstr2b(h)
    h.event("ca", "ca", "recon sharma 2026-11")
    assert h.last("ca").startswith("RC-0001 (Sharma Kirana Store 2026-11):")


def _side(ref: str, key: str, igst: str = "0", total: str = "100") -> rc.Side:
    zero = Decimal(0)
    return rc.Side(
        ref,
        ref,
        key,
        {"taxable": Decimal(100), "igst": Decimal(igst), "cgst": zero, "sgst": zero, "cess": zero},
        Decimal(total),
    )


def test_matcher_tolerances_and_ambiguity() -> None:
    within = rc.match([_side("P1", "k", "18.00")], [_side("L1", "k", "18.01")], TOL)
    assert within[0].class_ == rc.EXACT
    beyond = rc.match([_side("P1", "k", "18.00")], [_side("L1", "k", "18.02")], TOL)
    assert beyond[0].class_ == rc.MISMATCH
    total_only = rc.match([_side("P1", "k", total="100")], [_side("L1", "k", total="101.50")], TOL)
    assert total_only[0].class_ == rc.MISMATCH and "invoice_value" in total_only[0].differences
    amb = rc.match([_side("P1", "k"), _side("P2", "k")], [_side("L1", "k")], TOL)
    assert [r.class_ for r in amb] == [rc.AMBIGUOUS] * 3
    assert rc.results_hash(amb) == rc.results_hash(
        rc.match([_side("P1", "k"), _side("P2", "k")], [_side("L1", "k")], TOL)
    )
