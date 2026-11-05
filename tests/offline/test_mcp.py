"""Business-tool MCP server (D-07, P5-08 tool inventory, P5-05 isolation through MCP)."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from mcp.shared.memory import create_connected_server_and_client_session

from api.main import app
from api.mcp import server
from tests.offline.harness import Harness
from tests.offline.test_api import TOKENS, ctx_for

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def mcp_client(tmp_path: Path, h: Harness) -> TestClient:
    path = tmp_path / "tokens.json"
    path.write_text(json.dumps(TOKENS))
    os.environ["BUSINESS_MCP_TOKENS_FILE"] = str(path)
    from common.settings import get_settings

    get_settings.cache_clear()
    client = TestClient(app)
    server.set_api_client(client)
    yield client
    server.set_api_client(None)
    server.set_header_source(None)


def call(tool: str, args: dict[str, Any], token: str, ctx: str) -> Any:
    server.set_header_source(lambda _: {"authorization": f"Bearer {token}", "x-request-context": ctx})

    async def run() -> Any:
        async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
            result = await session.call_tool(tool, args)
            return json.loads(result.content[0].text) if result.content else None

    return asyncio.run(run())


def list_tools() -> list[Any]:
    async def run() -> list[Any]:
        async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
            return list((await session.list_tools()).tools)

    return asyncio.run(run())


def test_tool_inventory_matches_room_allow_lists_and_has_no_identity_args() -> None:
    tools = list_tools()
    names = {t.name for t in tools}
    rooms = yaml.safe_load((ROOT / "agents" / "rooms.yaml").read_text("utf-8"))["rooms"]
    allowed = {tool for r in rooms if r.get("provision") for tool in r["agents"]["assure-flow"]["tools"]}
    test_only = {"run_acceptance_suite", "reset_fixtures", "get_test_report"}  # room commands, not MCP tools
    assert allowed - test_only == names
    for tool in tools:
        props = set((tool.inputSchema or {}).get("properties", {}))
        assert not props & {"user", "user_id", "shop", "shop_id", "role", "actor"} or tool.name in (
            "get_period_readiness",
            "request_snapshot",
        )


def test_scoped_reads_through_mcp(h: Harness, mcp_client: TestClient) -> None:
    ref = h.ingest("F08_wrong_tax_type")
    sharma = ctx_for("af-shop-sharma", "owner.sharma")
    case = call("get_case", {"case_ref": ref}, "tok-sharma", sharma)
    assert case["case_ref"] == ref and case["status"] == "needs_resolution"
    explained = call("explain_issue", {"case_ref": ref, "rule_id": "R-TAX-01"}, "tok-sharma", sharma)
    assert explained["owner"] == "ca" and "not money lost" in explained["wording"]
    draft = call("draft_supplier_request", {"case_ref": ref}, "tok-sharma", sharma)
    assert "not sent automatically" in draft["send"]
    asked = call(
        "request_clarification",
        {"case_ref": ref, "question": "Is the supplier in Pune?"},
        "tok-sharma",
        sharma,
    )
    assert asked["status"] == "posted"
    from workers.runner import drain

    drain()
    assert any("Question about INV-0001" in x for x in h.said("sharma"))
    ca = ctx_for("af-ca-review", "ca.mehta")
    assert call("list_pending_handoffs", {}, "tok-ca", ca)["handoffs"][0]["case_ref"] == ref
    assert "error" in call("get_case", {"case_ref": ref}, "tok-sharma", ca)  # token/room mismatch


def test_mcp_isolation_every_tool_other_shop(h: Harness, mcp_client: TestClient) -> None:
    ref = h.ingest("F01_clean_intrastate_5pct")
    gupta = ctx_for("af-shop-gupta", "owner.gupta")
    args = {
        "get_receipt_status": {"receipt_ref": "R-0001"},
        "get_case": {"case_ref": ref},
        "get_check_results": {"case_ref": ref},
        "explain_issue": {"case_ref": ref, "rule_id": "R-TAX-01"},
        "request_clarification": {"case_ref": ref, "question": "?"},
        "draft_supplier_request": {"case_ref": ref},
        "get_period_readiness": {"shop": "sharma", "period": "2026-11"},
        "request_snapshot": {"shop": "sharma", "period": "2026-11"},
        "get_snapshot_manifest": {"snapshot_ref": "SN-0001"},
        "describe_job": {"job_id_prefix": "0"},
    }
    for tool in list_tools():
        out = call(tool.name, args.get(tool.name, {}), "tok-gupta", gupta)
        if tool.name in args:  # targets one of Sharma's objects: must be refused
            assert isinstance(out, dict) and "error" in out, (tool.name, out)
        else:  # room-scoped: may answer for Gupta's room, never with Sharma's data
            text = json.dumps(out)
            assert "INV-0001" not in text and "Sharma" not in text, (tool.name, text)
