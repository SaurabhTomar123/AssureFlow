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


def test_scoped_reads_and_cross_shop_isolation_matrix(h: Harness, client: TestClient) -> None:
    ref = h.ingest("F01_clean_intrastate_5pct")
    h.event("ca", "ca", f"{h.open_rr(ref)} include")
    h.event("ca", "ca", "snapshot sharma 2026-11")
    with transaction() as s:
        art = s.execute(select(m.Artifact)).scalars().first()
        job = s.execute(select(m.Job).where(m.Job.type == "fetch_and_store")).scalar_one()
    sharma = ctx_for("af-shop-sharma", "owner.sharma")
    assert client.get(f"/invoices/{ref}", headers=H("tok-sharma", sharma)).json()["status"] == "approved"

    gupta = ctx_for("af-shop-gupta", "owner.gupta")
    targets = {
        "/invoices/{ref}": f"/invoices/{ref}",
        "/invoices/{ref}/checks": f"/invoices/{ref}/checks",
        "/receipts/{ref}": "/receipts/R-0001",
        "/shops/{code}/periods/{period}/readiness": "/shops/sharma/periods/2026-11/readiness",
        "/snapshots/{ref}/manifest": "/snapshots/SN-0001/manifest",
        "/artifacts/{artifact_id}/download": f"/artifacts/{art.id if art else uuid.uuid4()}/download",
        "/jobs/{job_id}": f"/jobs/{job.id}",
    }
    paths = app.openapi()["paths"]
    for template, methods in paths.items():
        if template in ("/healthz", "/readyz", "/context"):
            continue
        for method in methods:
            if method == "get":
                url = targets[template]
                resp = client.get(url, headers=H("tok-gupta", gupta))
            else:
                url = (
                    template.replace("{code}", "sharma")
                    .replace("{period}", "2026-11")
                    .replace("{ref}", "RR-0001")
                )
                resp = client.post(
                    url,
                    json={"action": "include"} if "decisions" in url else {},
                    headers=H("tok-gupta", gupta, key=uuid.uuid4().hex),
                )
            assert resp.status_code in (403, 404), (template, method, resp.status_code)
            assert "error" in resp.json()
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
