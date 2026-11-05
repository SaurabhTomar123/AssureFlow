"""structlog JSON logs with a redaction filter (G-13: no invoice text, file bytes, tokens or secrets)."""

from __future__ import annotations

import logging
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

REDACTED_KEYS = {
    "body",
    "content",
    "text",
    "excerpt",
    "api_key",
    "token",
    "authorization",
    "password",
    "bytes",
    "payload",
    "LLM_API_KEY",
}


def redact(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> Mapping[str, Any]:
    for key in list(event_dict):
        if key.lower() in {k.lower() for k in REDACTED_KEYS}:
            event_dict[key] = "[redacted]"
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )


def get_logger(name: str) -> Any:
    return structlog.get_logger(name)
