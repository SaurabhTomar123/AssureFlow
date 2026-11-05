"""Assure Flow domain API. Run: uvicorn api.main:app"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
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
