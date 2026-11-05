"""API authorization, isolation matrix, idempotency and error envelope (G-04, G-07, R05, R09, T05, T06)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from api.main import app
from common.db import transaction
from domain import models as m
from domain.models import utcnow
from tests.offline.harness import Harness

TOKENS = {
    "tok-sharma": {"agent": "assure-flow", "rooms": ["af-shop-sharma"]},
    "tok-ca": {"agent": "assure-flow", "rooms": ["af-ca-review"]},
    "tok-gupta": {"agent": "assure-flow", "rooms": ["af-shop-gupta"]},
    "tok-other": {"agent": "assure-flow", "rooms": ["zz-shop-other"]},
}


@pytest.fixture()
def client(tmp_path: Path, h: Harness) -> TestClient:
    path = tmp_path / "tokens.json"
    path.write_text(json.dumps(TOKENS))
    os.environ["BUSINESS_MCP_TOKENS_FILE"] = str(path)
    from common.settings import get_settings

    get_settings.cache_clear()
    return TestClient(app)


def ctx_for(room: str, handle: str) -> str:
    with transaction() as s:
        rb = s.execute(select(m.RoomBinding).where(m.RoomBinding.name == room)).scalar_one()
        user = s.execute(select(m.User).where(m.User.handle == handle)).scalar_one()
        ev = s.execute(select(m.InboxEvent).limit(1)).scalar_one()
        ctx = m.RequestContext(
            environment="test",
            practice_id=rb.practice_id,
            room_binding_id=rb.id,
            source_event_id=ev.id,
            verified_user_id=user.id,
            request_id=uuid.uuid4().hex,
            expires_at=utcnow() + timedelta(minutes=5),
        )
        s.add(ctx)
        s.flush()
        return str(ctx.context_id)


def H(token: str, ctx: str, key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}", "X-Request-Context": ctx}
    if key:
        headers["Idempotency-Key"] = key
    return headers


SHARMA_MARKERS = ("INV-0001", "Sharma", "R-0001", "SN-0001", "RR-0001")
ROOM_SCOPED = ("/status", "/directory", "/handoffs/pending", "/ops/health", "/ops/failed-jobs", "/context")


def other_practice_context() -> str:
    """A second practice with its own shop, owner and room: nothing of practice one may be reachable."""
    from rules.gstin import make_gstin

    with transaction() as s:
        practice = m.Practice(name="Other practice (synthetic)")
        s.add(practice)
        s.flush()
        shop = m.Shop(
            practice_id=practice.id,
            code="other",
            name="Other Store",
            state_code="07",
            gstin=make_gstin("07", "OTHER5555Q"),
        )
        user = m.User(practice_id=practice.id, handle="owner.other", display_name="Other", role="owner")
        s.add_all([shop, user])
        s.flush()
        s.add(m.ShopMembership(user_id=user.id, shop_id=shop.id))
        tools = sorted({r for r in TOOL_NAMES})
        room = m.RoomBinding(
            environment="test",
            practice_id=practice.id,
            name="zz-shop-other",
            switch_room_id="unbound:zz-shop-other",
            purpose="shop_intake",
            config_version="1",
            agent_roles_and_tools={"assure-flow": {"tools": tools}},
        )
        s.add(room)
        s.flush()
        s.add(m.RoomBindingShop(room_binding_id=room.id, shop_id=shop.id))
        s.flush()
    return ctx_for("zz-shop-other", "owner.other")


TOOL_NAMES = (
    "get_request_context",
    "get_receipt_status",
    "get_case",
    "get_status",
    "get_check_results",
    "explain_issue",
    "request_clarification",
    "draft_supplier_request",
    "list_pending_handoffs",
    "get_period_readiness",
    "request_snapshot",
    "get_snapshot_manifest",
    "list_directory",
    "get_health",
    "list_failed_jobs",
    "describe_job",
)


def test_isolation_matrix_every_route_other_shop_and_other_practice(h: Harness, client: TestClient) -> None:
    ref = h.ingest("F01_clean_intrastate_5pct")
    h.ingest("F08_wrong_tax_type")
    h.event("ca", "ca", f"{h.open_rr(ref)} include")
    h.event("ca", "ca", "snapshot sharma 2026-11")
    with transaction() as s:
        art = s.execute(select(m.Artifact)).scalars().first()
        job = s.execute(select(m.Job).where(m.Job.type == "fetch_and_store")).scalars().first()
    sharma = ctx_for("af-shop-sharma", "owner.sharma")
    assert client.get(f"/invoices/{ref}", headers=H("tok-sharma", sharma)).json()["status"] == "approved"
    fill = {
        "{ref}": ref,
        "{rule_id}": "R-TAX-01",
        "{code}": "sharma",
        "{period}": "2026-11",
        "{artifact_id}": str(art.id if art else uuid.uuid4()),
        "{job_id}": str(job.id if job else uuid.uuid4()),
        "{prefix}": str(job.id)[:8] if job else "deadbeef",
    }
    special = {
        "/receipts/{ref}": "/receipts/R-0001",
        "/snapshots/{ref}/manifest": "/snapshots/SN-0001/manifest",
        "/review-requests/{ref}/decisions": "/review-requests/RR-0001/decisions",
    }
    bodies = {"decisions": {"action": "include"}, "clarifications": {"question": "x?"}}
    contexts = {
        "other shop": ("tok-gupta", ctx_for("af-shop-gupta", "owner.gupta")),
        "other practice": ("tok-other", other_practice_context()),
    }
    checked = 0
    for label, (token, ctx) in contexts.items():
        for template, methods in app.openapi()["paths"].items():
            if template in ("/healthz", "/readyz"):
                continue
            url = special.get(template, template)
            for key, value in fill.items():
                url = url.replace(key, value)
            for method in methods:
                if method == "get":
                    resp = client.get(url, headers=H(token, ctx))
                else:
                    body = next((b for k, b in bodies.items() if k in url), {})
                    resp = client.post(url, json=body, headers=H(token, ctx, key=uuid.uuid4().hex))
                checked += 1
                if template in ROOM_SCOPED and resp.status_code == 200:
                    leaked = [mk for mk in SHARMA_MARKERS if mk in resp.text]
                    assert not leaked, (label, template, leaked)
                else:
                    assert resp.status_code in (403, 404), (label, template, method, resp.status_code)
                    assert "error" in resp.json()
    routes = sum(len(ms) for tpl, ms in app.openapi()["paths"].items() if tpl not in ("/healthz", "/readyz"))
    assert checked == routes * len(contexts) and routes >= 19
    # The shop room's agent token cannot be replayed with a CA-room context.
    ca = ctx_for("af-ca-review", "ca.mehta")
    assert client.get(f"/invoices/{ref}", headers=H("tok-sharma", ca)).status_code == 403


def test_agents_never_decide_and_identity_args_are_rejected(h: Harness, client: TestClient) -> None:
    ref = h.ingest("F01_clean_intrastate_5pct")
    ca = ctx_for("af-ca-review", "ca.mehta")
    resp = client.post(
        f"/review-requests/{h.open_rr(ref)}/decisions",
        json={"action": "include"},
        headers=H("tok-ca", ca, key="k1"),
    )
    assert resp.status_code == 403
    assert h.case(ref).status == "ready_for_ca"
    forged = client.post(
        "/shops/sharma/periods/2026-11/snapshots",
        json={"user_id": "ca.mehta"},
        headers=H("tok-ca", ca, key="k2"),
    )
    assert forged.status_code == 422 and forged.json()["error"]["code"] == "VALIDATION_ERROR"


def test_idempotency_and_missing_key(h: Harness, client: TestClient) -> None:
    h.ingest("F01_clean_intrastate_5pct")
    ca = ctx_for("af-ca-review", "ca.mehta")
    url = "/shops/sharma/periods/2026-11/snapshots"
    assert client.post(url, json={}, headers=H("tok-ca", ca)).status_code == 422
    first = client.post(url, json={}, headers=H("tok-ca", ca, key="same"))
    again = client.post(url, json={}, headers=H("tok-ca", ca, key="same"))
    assert first.status_code == again.status_code == 202 and first.json() == again.json()
    with transaction() as s:
        assert len(list(s.execute(select(m.Job).where(m.Job.type == "build_snapshot")).scalars())) == 1
    conflict = client.post(
        "/shops/gupta/periods/2026-11/snapshots", json={}, headers=H("tok-ca", ca, key="same")
    )
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_expired_context_and_unknown_token(h: Harness, client: TestClient) -> None:
    ref = h.ingest("F01_clean_intrastate_5pct")
    ctx = ctx_for("af-shop-sharma", "owner.sharma")
    with transaction() as s:
        s.execute(update(m.RequestContext).values(expires_at=utcnow() - timedelta(seconds=1)))
    assert client.get(f"/invoices/{ref}", headers=H("tok-sharma", ctx)).status_code == 401
    assert client.get(f"/invoices/{ref}", headers=H("nope", ctx)).status_code == 401


def test_health_endpoints(h: Harness, client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json()["status"] == "ready"
