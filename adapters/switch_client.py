"""Switch runtime integration (agent protocol, WebSocket events in, HTTP out).

Verified against the Switch docs and core source (docs/decisions.md D-02):
  * WS  GET  /agents/{id}/connection/ws?connection_id=&scope=all&filter=all&start_from=
  * HTTP POST /agents/{id}/message                     {room_id, content}
  * HTTP GET  /agents/{id}/rooms/{room_id}/media?mxc=   attachment bytes
  * HTTP POST /agents/{id}/rooms/{room_id}/media       multipart upload (files, caption)
  * HTTP POST /agents/{id}/ops/{operation}             operations (list_rooms, ...)
The adapter consumes every event in its rooms (filter=all) and writes each to the durable inbox before
its cursor advances. Pings are answered before events are processed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx

from common.errors import LimitExceeded
from common.logging import get_logger
from common.settings import get_settings

log = get_logger("switch")


@dataclass
class SwitchCredentials:
    agent_id: str
    api_key: str
    connection_id: str
    agent_name: str = "assure-flow"

    @classmethod
    def load(cls, path: str | None = None) -> SwitchCredentials:
        data = json.loads(Path(path or get_settings().SWITCH_CREDENTIALS_FILE).read_text("utf-8"))
        return cls(**data)

    def save(self, path: str | None = None) -> None:
        target = Path(path or get_settings().SWITCH_CREDENTIALS_FILE)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.__dict__, indent=2), "utf-8")


class SwitchPort(Protocol):
    def post_message(self, room_id: str, content: str) -> str: ...

    def upload_files(self, room_id: str, files: list[tuple[str, bytes, str]], caption: str) -> str: ...

    def download_media(
        self, room_id: str, mxc: str, max_bytes: int
    ) -> tuple[bytes, str | None, str | None]: ...

    def room_members(self, room_id: str) -> list[str] | None: ...


class SwitchHttp:
    def __init__(self, creds: SwitchCredentials, base_url: str | None = None) -> None:
        settings = get_settings()
        self.creds = creds
        self.base = (base_url or settings.SWITCH_BASE_URL).rstrip("/")
        self.timeout = settings.SWITCH_HTTP_TIMEOUT_SECONDS
        self.fetch_timeout = settings.FETCH_TIMEOUT_SECONDS

    @property
    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.creds.api_key}"}

    def post_message(self, room_id: str, content: str) -> str:
        resp = httpx.post(
            f"{self.base}/agents/{self.creds.agent_id}/message",
            json={"room_id": room_id, "content": content},
            headers=self._auth,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return str(resp.json().get("event_id", ""))

    def upload_files(self, room_id: str, files: list[tuple[str, bytes, str]], caption: str) -> str:
        resp = httpx.post(
            f"{self.base}/agents/{self.creds.agent_id}/rooms/{room_id}/media",
            files=[("files", (name, data, mime)) for name, data, mime in files],
            data={"caption": caption},
            headers=self._auth,
            timeout=self.fetch_timeout,
        )
        resp.raise_for_status()
        return str(resp.json().get("event_id", resp.json().get("event_ids", "")))

    def download_media(self, room_id: str, mxc: str, max_bytes: int) -> tuple[bytes, str | None, str | None]:
        url = f"{self.base}/agents/{self.creds.agent_id}/rooms/{room_id}/media"
        chunks: list[bytes] = []
        size = 0
        with httpx.stream(
            "GET", url, params={"mxc": mxc}, headers=self._auth, timeout=self.fetch_timeout
        ) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise LimitExceeded(f"file is larger than {max_bytes // (1024 * 1024)} MB")
                chunks.append(chunk)
            ctype = resp.headers.get("content-type")
            disposition = resp.headers.get("content-disposition", "")
        filename = disposition.split("filename=")[-1].strip('"') if "filename=" in disposition else None
        return b"".join(chunks), ctype, filename

    def room_members(self, room_id: str) -> list[str] | None:
        """Chat usernames of the people currently in the room (Switch `get_room_detail`)."""
        detail = self.op("get_room_detail", {"room_id": room_id}) or {}
        return [str(name) for name in detail.get("connected_user_names") or []]

    def op(self, operation: str, args: dict[str, Any] | None = None, connected: bool = False) -> Any:
        """Call an operation. Only room-bound operations need the live connection id header."""
        headers = dict(self._auth)
        if connected:
            headers["X-Switch-Connection-Id"] = self.creds.connection_id
        resp = httpx.post(
            f"{self.base}/agents/{self.creds.agent_id}/ops/{operation}",
            json=args or {},
            headers=headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json().get("result")


@dataclass
class FakeSwitch:
    """In-memory Switch used by offline CI (mocked bridge and runtime)."""

    media: dict[str, bytes] = field(default_factory=dict)
    posts: list[tuple[str, str, str]] = field(default_factory=list)
    uploads: list[tuple[str, list[str], str]] = field(default_factory=list)
    fail_next_posts: int = 0
    members: dict[str, list[str]] = field(default_factory=dict)

    def post_message(self, room_id: str, content: str) -> str:
        if self.fail_next_posts:
            self.fail_next_posts -= 1
            raise httpx.ConnectError("bridge offline")
        event_id = f"$evt-{len(self.posts) + 1}"
        self.posts.append((room_id, content, event_id))
        return event_id

    def upload_files(self, room_id: str, files: list[tuple[str, bytes, str]], caption: str) -> str:
        event_id = f"$upl-{len(self.uploads) + 1}"
        self.uploads.append((room_id, [name for name, _, _ in files], caption))
        self.posts.append((room_id, caption, event_id))
        return event_id

    def download_media(self, room_id: str, mxc: str, max_bytes: int) -> tuple[bytes, str | None, str | None]:
        data = self.media[mxc]
        if len(data) > max_bytes:
            raise LimitExceeded(f"file is larger than {max_bytes // (1024 * 1024)} MB")
        return data, None, None

    def room_members(self, room_id: str) -> list[str] | None:
        return self.members.get(room_id)

    def messages_in(self, room_id: str) -> list[str]:
        return [body for room, body, _ in self.posts if room == room_id]


_port: SwitchPort | None = None


def set_switch(port: SwitchPort | None) -> None:
    global _port
    _port = port


def get_switch() -> SwitchPort:
    global _port
    if _port is None:
        _port = SwitchHttp(SwitchCredentials.load())
    return _port


# ----------------------------------------------------------------------------- WebSocket consumer


EVICTION_LIMIT = 3
EVICTION_WINDOW_SECONDS = 60.0


def evictions_exceeded(times: list[float], now: float) -> bool:
    """Record one eviction; True once more than the limit fall inside the window (a competing adapter)."""
    times.append(now)
    times[:] = [t for t in times if now - t <= EVICTION_WINDOW_SECONDS]
    return len(times) > EVICTION_LIMIT


def event_key(data: dict[str, Any]) -> str:
    payload = data.get("payload") or {}
    return str(payload.get("message_id") or f"seq-{data.get('sequence')}")


def payload_hash(data: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


async def run_adapter(creds: SwitchCredentials, store_event: Any, load_cursor: Any, save_state: Any) -> None:
    """Consume room events forever. `store_event(data, sequence)` persists to the inbox (sync, run in a
    thread) and returns only after commit; the persisted cursor is what the pong reports."""
    import websockets

    settings = get_settings()
    ws_base = settings.SWITCH_BASE_URL.replace("http://", "ws://").replace("https://", "wss://").rstrip("/")
    backoff = 1.0
    evictions: list[float] = []
    while True:
        cursor, generation = await asyncio.to_thread(load_cursor)
        params = f"connection_id={creds.connection_id}&scope=all&filter=all&client=assure-flow&client_version=1.0.0"
        if cursor:
            params += f"&start_from={cursor}"
        if generation is not None:
            params += f"&expected_generation={generation}"
        url = f"{ws_base}/agents/{creds.agent_id}/connection/ws?{params}"
        state = {"cursor": cursor}
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        try:
            async with websockets.connect(
                url, additional_headers={"Authorization": f"Bearer {creds.api_key}"}, max_size=2**22
            ) as ws:
                backoff = 1.0

                async def process(
                    queue: asyncio.Queue[dict[str, Any]] = queue, state: dict[str, int] = state
                ) -> None:
                    while True:
                        frame = await queue.get()
                        data = frame.get("data") or {}
                        seq = int(frame.get("id") or data.get("sequence") or 0)
                        await asyncio.to_thread(store_event, data, seq)
                        state["cursor"] = max(state["cursor"], seq)

                worker = asyncio.create_task(process())
                try:
                    async for raw in ws:
                        frame = json.loads(raw)
                        kind = frame.get("type") or frame.get("event")
                        if kind == "ping":
                            await ws.send(json.dumps({"type": "pong", "cursor": state["cursor"]}))
                        elif kind == "connection_state":
                            await asyncio.to_thread(save_state, frame.get("generation"))
                            log.info("switch.connected", rooms=len(frame.get("rooms") or []))
                        elif kind == "gap":
                            log.warning("switch.gap", reason=frame.get("reason"))
                            state["cursor"] = int(frame.get("resumed_at") or state["cursor"])
                        elif kind == "evicted":
                            code = frame.get("code")
                            log.warning("switch.evicted", code=code)
                            if code in ("taken_over", "closed"):
                                return
                            if evictions_exceeded(evictions, asyncio.get_running_loop().time()):
                                log.error("switch.eviction_loop", limit=EVICTION_LIMIT)
                                raise SystemExit(
                                    "Evicted repeatedly: another process is using this agent connection. "
                                    "Check `python -m scripts.health` before starting the adapter again."
                                )
                        elif kind in ("message", "command", "room_join"):
                            await queue.put(frame)
                finally:
                    worker.cancel()
        except (OSError, websockets.WebSocketException) as exc:
            log.warning("switch.disconnected", error=type(exc).__name__)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30.0)


def new_connection_id() -> str:
    return str(uuid.uuid4())
