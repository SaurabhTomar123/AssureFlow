"""Measure a live extraction provider against the recorded fixtures. Makes real API calls; never touches the database.

Run: python -m scripts.eval_extraction [--limit 5] [--delay 5] [--min-accuracy 0.9] [--out report.json]
     python -m scripts.eval_extraction --list-models

Compares the fields people confirm. Recorded values are the reference; passing says nothing about real-world bills.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import sys
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from adapters import pdf
from adapters.llm import FIXTURE_DIR, ProviderError, ProviderPermanentError, get_provider
from common.settings import get_settings
from domain.extraction import ExtractionV1

FIXTURES = FIXTURE_DIR.parent.parent / "fixtures"
INDEX = FIXTURE_DIR.parent / "fixtures.json"
COMPARED = (
    "document_type",
    "supplier_name",
    "supplier_gstin",
    "recipient_gstin",
    "invoice_number",
    "invoice_date",
    "place_of_supply",
    "taxable_total",
    "cgst_total",
    "sgst_total",
    "igst_total",
    "invoice_total",
)


@dataclass
class Score:
    compared: int = 0
    matched: int = 0
    errors: list[str] = field(default_factory=list)
    mismatches: list[dict[str, Any]] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.matched / self.compared if self.compared else 0.0


def same(expected: str | None, actual: str | None) -> bool:
    """Amounts compare exactly by value; text ignores case and surrounding space."""
    if expected is None or actual is None:
        return expected is None and actual is None
    try:
        return Decimal(expected.replace(",", "")) == Decimal(actual.replace(",", ""))
    except InvalidOperation:
        return expected.strip().casefold() == actual.strip().casefold()


def compare(name: str, expected: ExtractionV1, actual: ExtractionV1, score: Score) -> None:
    for attr in COMPARED:
        want, got = getattr(expected, attr).value, getattr(actual, attr).value
        score.compared += 1
        if same(want, got):
            score.matched += 1
        else:
            score.mismatches.append({"fixture": name, "field": attr, "expected": want, "actual": got})


def cases() -> list[tuple[str, bytes, str, ExtractionV1]]:
    """Whole-file fixtures that have a recorded extraction. Per-page split fixtures are left out."""
    found = []
    for name, info in json.loads(INDEX.read_text("utf-8")).items():
        path = FIXTURES / info["file"]
        if not path.exists():
            continue
        data = path.read_bytes()
        recorded = FIXTURE_DIR / f"{hashlib.sha256(data).hexdigest()}.json"
        if recorded.exists():
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            found.append((name, data, mime, ExtractionV1.model_validate_json(recorded.read_text("utf-8"))))
    return found


def list_models() -> None:
    settings = get_settings()
    if settings.LLM_PROVIDER != "gemini":
        raise SystemExit("--list-models needs LLM_PROVIDER=gemini")
    from google import genai

    client = genai.Client(api_key=settings.LLM_API_KEY)  # held here: the pager needs it open while iterating
    for model in client.models.list():
        if "generateContent" in (model.supported_actions or []):
            print(model.name)


def run(limit: int, delay: float) -> Score:
    provider = get_provider()
    score = Score()
    selected = cases()[:limit]
    for i, (name, data, mime, expected) in enumerate(selected):
        if i:
            time.sleep(delay)
        prepared = pdf.prepare_for_extraction(data, mime, None, None)
        try:
            outcome = provider.extract(prepared, hashlib.sha256(data).hexdigest(), "eval")
        except (ProviderError, ProviderPermanentError) as exc:
            score.errors.append(f"{name}: {exc}")
            print(f"ERROR {name}: {exc}")
            continue
        before = score.matched
        compare(name, expected, outcome.result, score)
        print(f"{name}: {score.matched - before}/{len(COMPARED)} fields, {outcome.duration_ms} ms")
    return score


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--delay", type=float, default=5.0, help="seconds between calls, for free-tier rate limits")
    parser.add_argument("--min-accuracy", type=float, default=0.9)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--list-models", action="store_true")
    args = parser.parse_args(argv)
    if args.list_models:
        list_models()
        return 0
    settings = get_settings()
    if settings.LLM_PROVIDER == "fake":
        raise SystemExit("LLM_PROVIDER is fake, which only replays the reference. Set a live provider and key.")
    score = run(args.limit, args.delay)
    for miss in score.mismatches:
        print(f"MISMATCH {miss['fixture']} {miss['field']}: expected {miss['expected']!r}, got {miss['actual']!r}")
    print(f"{settings.LLM_PROVIDER}/{settings.LLM_MODEL}: {score.matched}/{score.compared} fields "
          f"({score.accuracy:.1%}), {len(score.errors)} failed documents")
    if args.out:
        args.out.write_text(
            json.dumps(
                {
                    "provider": settings.LLM_PROVIDER,
                    "model": settings.LLM_MODEL,
                    "compared": score.compared,
                    "matched": score.matched,
                    "errors": score.errors,
                    "mismatches": score.mismatches,
                },
                indent=2,
            ),
            "utf-8",
        )
    return 0 if score.accuracy >= args.min_accuracy and not score.errors else 1


if __name__ == "__main__":
    sys.exit(main())
