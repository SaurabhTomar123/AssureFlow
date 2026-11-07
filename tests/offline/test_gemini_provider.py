"""GeminiProvider without network: request shape, schema acceptance, error mapping, and the evaluation scoring."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google.genai import errors

from adapters import llm
from common.settings import get_settings
from domain.extraction import ExtractionV1
from scripts import eval_extraction as ev

PREPARED = {"pages": [{"page": 1, "text": "INVOICE", "image": b"\x89PNG"}]}


def _recorded() -> ExtractionV1:
    name, data, mime, expected = ev.cases()[0]
    assert name and data and mime
    return expected


class _Models:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _provider(result: Any) -> tuple[llm.GeminiProvider, _Models]:
    provider = llm.GeminiProvider.__new__(llm.GeminiProvider)
    models = _Models(result)
    provider.model = "gemini-test"
    provider.client = SimpleNamespace(models=models)  # type: ignore[assignment]
    return provider, models


def _response(parsed: Any = None, text: str | None = None) -> Any:
    usage = SimpleNamespace(prompt_token_count=11, candidates_token_count=7)
    return SimpleNamespace(parsed=parsed, text=text, usage_metadata=usage)


def test_request_carries_prompt_schema_and_both_page_forms() -> None:
    expected = _recorded()
    provider, models = _provider(_response(parsed=expected))
    outcome = provider.extract(PREPARED, "sha", "shop")
    assert outcome.result == expected
    assert (outcome.provider, outcome.input_tokens, outcome.output_tokens) == ("gemini", 11, 7)
    call = models.calls[0]
    assert call["model"] == "gemini-test"
    config = call["config"]
    assert config.system_instruction == llm.SYSTEM_PROMPT
    # response_schema is rejected by the live API (400, additional_properties): this exact form is required.
    assert config.response_schema is None
    assert config.response_json_schema == ExtractionV1.model_json_schema()
    assert config.response_mime_type == "application/json"
    assert config.temperature == 0
    assert any(p.inline_data and p.inline_data.mime_type == "image/png" for p in call["contents"])
    assert any(p.text and "INVOICE" in p.text for p in call["contents"])


def test_falls_back_to_validating_the_text() -> None:
    expected = _recorded()
    provider, _ = _provider(_response(text=expected.model_dump_json()))
    assert provider.extract(PREPARED, "sha", "shop").result == expected


@pytest.mark.parametrize("text", [None, "", "not json", json.dumps({"document_type": "x"})])
def test_unusable_output_is_permanent(text: str | None) -> None:
    provider, _ = _provider(_response(text=text))
    with pytest.raises(llm.ProviderPermanentError):
        provider.extract(PREPARED, "sha", "shop")


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (errors.ClientError(429, {"error": {"message": "rate"}}), llm.ProviderError),
        (errors.ServerError(503, {"error": {"message": "busy"}}), llm.ProviderError),
        (errors.ClientError(400, {"error": {"message": "bad"}}), llm.ProviderPermanentError),
        (errors.ClientError(403, {"error": {"message": "key"}}), llm.ProviderPermanentError),
        (httpx.ConnectError("offline"), llm.ProviderError),
        (TimeoutError(), llm.ProviderError),
    ],
)
def test_errors_map_to_retryable_or_permanent(error: Exception, kind: type[Exception]) -> None:
    provider, _ = _provider(error)
    with pytest.raises(kind):
        provider.extract(PREPARED, "sha", "shop")


@pytest.mark.parametrize(
    ("key", "model", "message"),
    [("", "gemini-test", "needs LLM_API_KEY"), ("k", "claude-opus-5-5", "must name a Gemini model")],
)
def test_misconfiguration_fails_clearly(monkeypatch: pytest.MonkeyPatch, key: str, model: str, message: str) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "LLM_API_KEY", key)
    monkeypatch.setattr(settings, "LLM_MODEL", model)
    with pytest.raises(llm.ProviderPermanentError, match=message):
        llm.GeminiProvider()


def test_provider_is_selected_by_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "LLM_API_KEY", "k")
    monkeypatch.setattr(settings, "LLM_MODEL", "gemini-test")
    llm.set_provider(None)
    try:
        assert isinstance(llm.get_provider(), llm.GeminiProvider)
    finally:
        llm.set_provider(None)


def test_evaluation_compares_amounts_by_value_and_reports_misses() -> None:
    assert ev.same("1180.00", "1,180")
    assert ev.same("ABC Traders ", "abc traders")
    assert not ev.same("1180.00", "1180.01")
    assert not ev.same(None, "1180")
    assert ev.same(None, None)
    expected = _recorded()
    changed = expected.model_copy(deep=True)
    changed.invoice_total.value = "1.00"
    score = ev.Score()
    ev.compare("F", expected, changed, score)
    assert score.compared == len(ev.COMPARED)
    assert score.matched == score.compared - 1
    assert score.mismatches[0]["field"] == "invoice_total"


def test_evaluation_refuses_the_fake_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "LLM_PROVIDER", "fake")
    with pytest.raises(SystemExit, match="only replays"):
        ev.main([])


def test_evaluation_runs_end_to_end_against_a_stub(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    class Replay:
        def extract(self, prepared: dict[str, Any], sha256: str, shop_key: str) -> llm.ExtractionOutcome:
            return llm.FakeProvider().extract({}, sha256, shop_key)

    monkeypatch.setattr(get_settings(), "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(ev, "get_provider", Replay)
    out = tmp_path / "report.json"
    assert ev.main(["--limit", "2", "--delay", "0", "--out", str(out)]) == 0
    report = json.loads(out.read_text("utf-8"))
    assert report["matched"] == report["compared"] == 2 * len(ev.COMPARED)
