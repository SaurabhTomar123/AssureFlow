"""Trusted request context for API and tool calls (spec section 7).

Authorization: Bearer <agent token>   -> which agent is calling (agent permission only)
X-Request-Context: <context id>        -> opaque reference to an interactive context created by the adapter
                                         from one verified room event; accepted only if it matches the
                                         agent's allowed rooms and has not expired. Identity is resolved
                                         server side; model arguments never carry identity.
Permission = agent tool allow-list for that room ∩ the human's rights ∩ room scope ∩ environment.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from common.db import session_factory
from common.errors import Forbidden, Unauthenticated
from common.settings import get_settings
from domain.context import require_live_context
from domain.models import RequestContext, RoomBinding
from domain.services.base import shops_of_room


@dataclass
class Caller:
    agent: str
    tools: set[str]
    context: RequestContext
    room: RoomBinding
    shops: list[uuid.UUID]

    def require_tool(self, tool: str) -> None:
        if tool not in self.tools:
            raise Forbidden(f"agent '{self.agent}' is not allowed to call {tool} in {self.room.name}")


def get_db() -> Iterator[Session]:
    session = session_factory()()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def load_tokens() -> dict[str, dict[str, object]]:
    path = Path(get_settings().BUSINESS_MCP_TOKENS_FILE)
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


def caller(
    request: Request,
    authorization: str = Header(default=""),
    x_request_context: str = Header(default=""),
    s: Session = Depends(get_db),
) -> Caller:
    token = authorization.removeprefix("Bearer ").strip()
    agent = load_tokens().get(token) if token else None
    if agent is None:
        raise Unauthenticated("missing or unknown agent token")
    try:
        ctx = s.get(RequestContext, uuid.UUID(x_request_context))
    except ValueError as exc:
        raise Unauthenticated("missing or malformed request context") from exc
    if ctx is None or ctx.environment != get_settings().ENVIRONMENT:
        raise Unauthenticated("unknown request context")
    require_live_context(ctx)
    room = s.get(RoomBinding, ctx.room_binding_id)
    assert room is not None
    if room.name not in agent.get("rooms", []):  # type: ignore[operator]
        raise Forbidden("this agent is not configured for the context's room")
    tools = set((room.agent_roles_and_tools.get(str(agent["agent"])) or {}).get("tools", []))
    request.state.actor_scope = f"{agent['agent']}:{ctx.verified_user_id}"
    return Caller(str(agent["agent"]), tools, ctx, room, shops_of_room(s, room.id))
