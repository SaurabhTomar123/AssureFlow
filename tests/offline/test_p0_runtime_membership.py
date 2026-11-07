"""Live Telegram regressions T-15 and T-23: one runtime owner, name-based member checks, rebind-room."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from adapters.switch_client import evictions_exceeded
from common import runtime
from common.db import transaction
from domain import models as m
from domain.services.disclosure import unauthorized_live
from scripts import admin
from tests.offline.conftest import TEST_DB
from tests.offline.harness import ROOMS, Harness


def test_recovery_after_membership_change_keeps_old_replies_withheld(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    room = "!ca-room:test"  # the live check skips rooms that are still unbound
    monkeypatch.setitem(ROOMS, "ca", room)
    with transaction() as s:
        _ca_binding(s).switch_room_id = room
    h.switch.members[room] = ["ca", "sharma"]
    h.event("ca", "ca", "pending")
    with transaction() as s:
        withheld = s.execute(select(m.Outbox).where(m.Outbox.status == "withheld")).scalars().all()
        assert withheld
        kept = [row.id for row in withheld]
    h.switch.members[room] = ["ca"]
    h.event("ca", "ca", "pending")
    assert "review" in h.last("ca").lower()
    with transaction() as s:
        assert all(s.get(m.Outbox, i).status == "withheld" for i in kept)  # type: ignore[union-attr]


def _ca_binding(s: object) -> m.RoomBinding:
    return s.execute(select(m.RoomBinding).where(m.RoomBinding.name == "af-ca-review")).scalar_one()  # type: ignore[attr-defined]


def test_ambiguous_display_name_fails_closed_without_crashing(h: Harness) -> None:
    with transaction() as s:
        owner = s.execute(select(m.User).where(m.User.handle == "owner.sharma")).scalar_one()
        s.add(
            m.ChatIdentity(
                practice_id=owner.practice_id,
                platform="switch",
                platform_user_id="@someone-else:test",
                chat_username="ca",
                user_id=owner.id,
            )
        )
    with transaction() as s:
        assert unauthorized_live(s, _ca_binding(s), ["ca"]) == ["ca"]


def test_unknown_display_name_fails_closed(h: Harness) -> None:
    with transaction() as s:
        assert unauthorized_live(s, _ca_binding(s), ["ca", "nobody"]) == ["nobody"]


def test_name_bound_in_another_practice_fails_closed(h: Harness) -> None:
    with transaction() as s:
        other = m.Practice(name="Other practice")
        s.add(other)
        s.flush()
        identity = s.execute(select(m.ChatIdentity).where(m.ChatIdentity.chat_username == "ca")).scalar_one()
        identity.practice_id = other.id
    with transaction() as s:
        assert unauthorized_live(s, _ca_binding(s), ["ca"]) == ["ca"]





def test_second_copy_refuses_and_names_the_holder() -> None:
    first = runtime.hold("adapter", TEST_DB)
    try:
        with pytest.raises(runtime.AlreadyRunning, match="af-adapter"):
            runtime.hold("adapter", TEST_DB)
        assert "af-adapter" in (runtime.holder(first, "adapter") or "")
        worker = runtime.hold("worker", TEST_DB)  # another role is independent
        worker.close()
    finally:
        runtime.release("adapter")
    released = runtime.hold("adapter", TEST_DB)
    runtime.release("adapter")
    assert released.closed


def test_eviction_guard_trips_only_on_a_burst() -> None:
    times: list[float] = []
    assert [evictions_exceeded(times, t) for t in (0, 10, 20)] == [False, False, False]
    assert evictions_exceeded(times, 30) is True
    assert evictions_exceeded([], 500) is False
    spaced: list[float] = []
    assert not any(evictions_exceeded(spaced, t * 100.0) for t in range(10))



class _Http:
    def __init__(self, rooms: list[str], members: list[str]) -> None:
        self.rooms, self.members = rooms, members

    def op(self, operation: str, args: dict[str, str] | None = None) -> list[dict[str, str]]:
        return [{"room_id": r, "name": f"Telegram: {r}"} for r in self.rooms]

    def room_members(self, room_id: str) -> list[str]:
        return self.members


def test_rebind_room_moves_the_binding_and_is_audited(h: Harness, capsys: pytest.CaptureFixture[str]) -> None:
    admin.rebind_room("af-ca-review", "!new", "stale membership", _Http(["!new"], ["ca", "sharma"]))  # type: ignore[arg-type]
    assert "withheld until these members leave: sharma" in capsys.readouterr().out
    with transaction() as s:
        assert _ca_binding(s).switch_room_id == "!new"
        event = s.execute(select(m.AuditEvent).where(m.AuditEvent.action == "room.rebound")).scalar_one()
        assert event.entity_id == "af-ca-review"
        assert admin._was_rebound(s, "af-ca-review")
        assert not admin._was_rebound(s, "af-shop-sharma")


def test_rebind_room_refuses_a_room_the_agent_is_not_in_or_one_already_bound(h: Harness) -> None:
    with pytest.raises(SystemExit, match="not in Switch room"):
        admin.rebind_room("af-ca-review", "!missing", "x", _Http([], []))  # type: ignore[arg-type]
    admin.rebind_room("af-shop-sharma", "!taken", "x", _Http(["!taken"], ["sharma"]))  # type: ignore[arg-type]
    with pytest.raises(SystemExit, match="already bound to af-shop-sharma"):
        admin.rebind_room("af-ca-review", "!taken", "x", _Http(["!taken"], []))  # type: ignore[arg-type]
