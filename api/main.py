"""Assure Flow domain API. Run: uvicorn api.main:app"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from api.routers.tools import router as tools_router
from common.db import transaction
from common.errors import DomainError, IdempotencyConflict, ValidationFailed
from common.logging import configure_logging
from common.settings import get_settings
from domain.models import EnvironmentRow, IdempotencyKey

configure_logging()
app = FastAPI(title="Assure Flow", version="1.0.0")


def _cid(request: Request) -> str:
    return getattr(request.state, "correlation_id", "") or uuid.uuid4().hex


@app.exception_handler(DomainError)
async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(exc.envelope(_cid(request)), status_code=exc.status)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    err = ValidationFailed("Invalid request.", {"errors": json.loads(json.dumps(exc.errors(), default=str))})
    return JSONResponse(err.envelope(_cid(request)), status_code=422)


@app.middleware("http")
async def correlation_and_idempotency(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request.state.correlation_id = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex
    if request.method != "POST":
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = request.state.correlation_id
        return response
    key = request.headers.get("Idempotency-Key")
    if not key:
        err = ValidationFailed("Every POST needs an Idempotency-Key header.")
        return JSONResponse(err.envelope(request.state.correlation_id), status_code=422)
    body = await request.body()
    scope = f"{request.headers.get('Authorization', '')[-12:]}:{request.headers.get('X-Request-Context', '')}"
    request_hash = hashlib.sha256(request.url.path.encode() + b"\n" + body).hexdigest()
    with transaction() as s:
        stored = s.execute(
            select(IdempotencyKey).where(IdempotencyKey.key == key, IdempotencyKey.actor_scope == scope)
        ).scalar_one_or_none()
        if stored is not None:
            if stored.request_hash != request_hash:
                conflict = IdempotencyConflict("This Idempotency-Key was used with a different request.")
                return JSONResponse(conflict.envelope(request.state.correlation_id), status_code=409)
            return JSONResponse(stored.response, status_code=stored.status_code)
    response = await call_next(request)
    payload = b"".join([chunk async for chunk in response.body_iterator])  # type: ignore[attr-defined]
    if response.status_code < 500:
        with transaction() as s:
            s.execute(
                insert(IdempotencyKey)
                .values(
                    key=key,
                    actor_scope=scope,
                    request_hash=request_hash,
                    response=json.loads(payload or b"null"),
                    status_code=response.status_code,
                )
                .on_conflict_do_nothing()
            )
    headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
    headers["X-Correlation-ID"] = request.state.correlation_id
    return Response(
        payload, status_code=response.status_code, headers=headers, media_type=response.media_type
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MunimJi (AssureFlow) &mdash; System Operations Cockpit</title>
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #38bdf8;
      --success: #4ade80;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.6;
      padding: 2rem 1rem;
    }
    .container { max-width: 1000px; margin: 0 auto; }
    header { margin-bottom: 2rem; border-bottom: 1px solid var(--border); padding-bottom: 1.5rem; }
    h1 { font-size: 2rem; font-weight: 700; color: #fff; margin-bottom: 0.5rem; }
    .badge {
      display: inline-block;
      background: rgba(56, 189, 248, 0.15);
      color: var(--accent);
      border: 1px solid var(--accent);
      border-radius: 4px;
      padding: 0.2rem 0.6rem;
      font-size: 0.85rem;
      font-weight: 600;
      margin-right: 0.5rem;
    }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.5rem; margin-bottom: 2rem; }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1.25rem;
    }
    .card h2 { font-size: 1.2rem; margin-bottom: 0.75rem; color: var(--accent); }
    .card p { color: var(--text-muted); font-size: 0.95rem; margin-bottom: 0.75rem; }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.85rem;
      color: var(--success);
      font-weight: 600;
    }
    .status-dot { width: 8px; height: 8px; background: var(--success); border-radius: 50%; }
    table { width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: 0.9rem; }
    th, td { text-align: left; padding: 0.75rem; border-bottom: 1px solid var(--border); }
    th { color: var(--text-muted); font-weight: 600; }
    code { background: #0f172a; padding: 0.2rem 0.4rem; border-radius: 4px; font-family: monospace; font-size: 0.85rem; color: #38bdf8; }
    pre { background: #090d16; padding: 1rem; border-radius: 6px; overflow-x: auto; font-family: monospace; font-size: 0.85rem; margin-top: 0.5rem; border: 1px solid var(--border); }
    .notice {
      background: rgba(56, 189, 248, 0.08);
      border-left: 4px solid var(--accent);
      padding: 1rem;
      border-radius: 4px;
      margin-bottom: 2rem;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div style="margin-bottom: 0.75rem;">
        <span class="badge">Flip the Switch Hackathon</span>
        <span class="badge">Track 1: Best Business Workflow</span>
        <span class="badge">Release v1.0.0</span>
      </div>
      <h1>MunimJi (AssureFlow) Operations Cockpit</h1>
      <p style="color: var(--text-muted);">Evidence-backed monthly GST purchase review run entirely inside Switch rooms.</p>
    </header>

    <div class="notice">
      <strong>Architecture Note:</strong> AssureFlow&apos;s core product interface operates <strong>100% inside Switch collaboration rooms</strong> (Mattermost, Telegram, Slack). Shopkeepers and CAs interact directly via natural chat and file attachments. This web cockpit provides telemetry, health status, and developer guidance.
    </div>

    <div class="grid">
      <div class="card">
        <h2>System Status</h2>
        <p><span class="status-pill"><span class="status-dot"></span> Domain API Online</span></p>
        <p><strong>Health Endpoints:</strong> <a href="/healthz" style="color: var(--accent);">/healthz</a>, <a href="/readyz" style="color: var(--accent);">/readyz</a></p>
        <p><strong>Database:</strong> PostgreSQL 16 (Phases P0&ndash;P6)</p>
        <p><strong>Rules Profile:</strong> <code>domestic_goods_v1</code> (10 statutory Decimal rules)</p>
        <p><strong>Switch Protocol:</strong> WebSocket Agent Protocol <code>0.31.0</code></p>
      </div>

      <div class="card">
        <h2>Quick Evaluation Commands</h2>
        <p>Run the 12-beat end-to-end room story offline with recorded fixtures (zero keys or servers needed):</p>
        <pre>python -m scripts.demo_offline</pre>
        <p style="margin-top: 0.75rem;">Run the automated regression test suite:</p>
        <pre>pytest</pre>
      </div>
    </div>

    <div class="card" style="margin-bottom: 2rem;">
      <h2>Active Switch Room Topology</h2>
      <table>
        <thead>
          <tr>
            <th>Room</th>
            <th>Participants</th>
            <th>Operational Scope</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><code>#af-shop-sharma</code></td>
            <td>Ramesh (Shop Owner), assure-flow</td>
            <td>Bill photo/PDF intake, typed corrections, owner confirmation (<code>ok INV-0001 r1</code>)</td>
          </tr>
          <tr>
            <td><code>#af-shop-gupta</code></td>
            <td>Sunita (Shop Owner), assure-flow</td>
            <td>Independent merchant intake; verified room isolation blocks cross-shop access</td>
          </tr>
          <tr>
            <td><code>#af-ca-review</code></td>
            <td>CA Mehta, assure-flow</td>
            <td>Review requests (<code>RR-XXXX</code>), GSTR-2B reconciliation, hash-approved frozen review pack export</td>
          </tr>
          <tr>
            <td><code>#af-practice-home</code></td>
            <td>CA Practice Staff</td>
            <td>Client directory and multi-shop month readiness oversight</td>
          </tr>
          <tr>
            <td><code>#af-operations</code></td>
            <td>System Operator</td>
            <td>Worker lane health, job retry commands, dead-letter and isolation alerts</td>
          </tr>
          <tr>
            <td><code>#af-synthetic-testing</code></td>
            <td>Developers</td>
            <td>Automated offline acceptance runner (<code>acceptance</code>)</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h2>Exploratory Prototypes Catalog (legacy/)</h2>
      <p>Auxiliary prototypes covering store inventory (FEFO tracking), blue/white-collar attendance, and double-entry bookkeeping are preserved in <code>legacy/</code>. They are decoupled from the core Switch 0.31.0 GST review engine to guarantee strict statutory mathematical precision (<code>Decimal</code> and integer paise) across tax filings.</p>
    </div>
  </div>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/switch-simulator", response_class=HTMLResponse)
def cockpit_dashboard() -> HTMLResponse:
    return HTMLResponse(content=DASHBOARD_HTML, status_code=200)


@app.get("/readyz")
def readyz() -> JSONResponse:
    settings = get_settings()
    try:
        with transaction() as s:
            s.execute(text("SELECT 1"))
            env = s.execute(select(EnvironmentRow.name)).scalar_one_or_none()
    except Exception as exc:  # noqa: BLE001 - readiness reports, never raises
        return JSONResponse({"status": "down", "reason": type(exc).__name__}, status_code=503)
    if env != settings.ENVIRONMENT:
        return JSONResponse({"status": "down", "reason": f"database environment is {env}"}, status_code=503)
    return JSONResponse({"status": "ready", "environment": env})


app.include_router(tools_router)
