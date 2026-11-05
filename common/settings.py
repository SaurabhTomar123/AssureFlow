"""Configuration contract (spec section 2). Every value has the specification default."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://af:af@localhost:5433/assureflow"
    FILE_STORAGE_ROOT: str = "./data/files"
    ENVIRONMENT: Literal["demo", "test", "pilot", "production"] = "demo"

    SWITCH_BASE_URL: str = "http://localhost:8080"
    SWITCH_SERVER_VERSION: str = ""
    SWITCH_CONSOLE_VERSION: str = ""
    SWITCH_CREDENTIALS_FILE: str = "./data/switch_credentials.json"
    ROOM_BINDINGS_FILE: str = "./agents/rooms.yaml"
    ROOM_CONFIG_VERSION: str = "1"
    BUSINESS_MCP_BIND: str = "127.0.0.1:8000"
    BUSINESS_MCP_TOKENS_FILE: str = "./data/business_tokens.json"

    REQUEST_CONTEXT_TTL_SECONDS: int = 900
    EXECUTION_GRANT_TTL_HOURS: int = 72

    LLM_PROVIDER: Literal["anthropic", "fake"] = "fake"
    LLM_MODEL: str = "claude-opus-5-5"
    LLM_API_KEY: str = ""

    HANDOFF_HOP_LIMIT: int = 3
    MAX_UPLOAD_MB: int = 20
    MAX_PAGES: int = 20
    TAX_LINE_TOLERANCE_INR: Decimal = Decimal("0.01")
    AMOUNT_TOLERANCE_INR: Decimal = Decimal("1.00")

    JOB_MAX_ATTEMPTS: int = 3
    JOB_LEASE_SECONDS: int = 120
    JOB_HEARTBEAT_SECONDS: int = 30
    JOB_BACKOFF_SECONDS: Annotated[list[int], NoDecode] = Field(default_factory=lambda: [30, 120, 600])
    WORKER_FAST_SLOTS: int = 4
    WORKER_IO_SLOTS: int = 2
    WORKER_SLOW_SLOTS: int = 2
    JOB_MAX_DURATION_SECONDS: int = 300
    OUTBOX_MAX_ATTEMPTS: int = 20
    MODEL_TIMEOUT_SECONDS: int = 60
    SWITCH_HTTP_TIMEOUT_SECONDS: int = 10
    FETCH_TIMEOUT_SECONDS: int = 30
    CPU_TASK_TIMEOUT_SECONDS: int = 90

    DEFAULT_TZ: str = "Asia/Kolkata"
    ACK_TARGET_SECONDS: int = 5
    EXTRACTION_TARGET_SECONDS: int = 90

    @field_validator("JOB_BACKOFF_SECONDS", mode="before")
    @classmethod
    def _split_backoff(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part) for part in value.replace(" ", "").split(",") if part]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
