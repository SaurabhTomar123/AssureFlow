"""Test harness: injects room events through the real adapter inbox path and drains the worker."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select

from adapters.inbox_writer import record_event
from adapters.llm import set_provider
from adapters.switch_client import FakeSwitch, set_switch
from common.db import transaction
from domain import models as m
from seed.loader import seed, truncate_all
from workers.runner import drain

FIXTURES = Path(__file__).resolve().parents[2] / "seed" / "fixtures"
INDEX = json.loads((FIXTURES.parent / "expected" / "fixtures.json").read_text("utf-8"))
ROOMS = {
    "sharma": "unbound:af-shop-sharma",
    "gupta": "unbound:af-shop-gupta",
    "ca": "unbound:af-ca-review",
    "home": "unbound:af-practice-home",
    "ops": "unbound:af-operations",
    "testing": "unbound:af-synthetic-testing",
}
SENDERS = {
    "sharma": "@switch-user-sharma:test",
    "gupta": "@switch-user-gupta:test",
    "ca": "@switch-user-mehta:test",
    "ops": "@switch-user-rao:test",
    "dev": "@switch-user-iyer:test",
    "stranger": "@switch-user-stranger:test",
}
HANDLES = {
    "sharma": "owner.sharma",
    "gupta": "owner.gupta",
    "ca": "ca.mehta",
    "ops": "ops.rao",
    "dev": "dev.iyer",
}


class Harness:
    def __init__(self) -> None:
        self.switch = FakeSwitch()
        self.seq = 0
        set_switch(self.switch)
        set_provider(None)

    @classmethod
    def fresh(cls) -> Harness:
        with transaction() as s:
            truncate_all(s)
            data = seed(s)
            for key, handle in HANDLES.items():
                user = data["users"][handle]
                s.add(
                    m.ChatIdentity(
                        practice_id=user.practice_id,
                        platform="switch",
                        platform_user_id=SENDERS[key],
                        chat_username=key,
                        user_id=user.id,
                    )
                )
        return cls()

    def close(self) -> None:
        set_switch(None)

    # -- events -------------------------------------------------------------------------------

    def event(
        self,
        room: str,
        who: str,
        body: str = "",
        files: list[str] | None = None,
        thread_id: str | None = None,
        message_id: str | None = None,
        addressed: bool = False,
        drain_after: bool = True,
    ) -> str:
        self.seq += 1
        attachments = []
        for name in files or []:
            info = INDEX[name]
            mxc = f"mxc://test/{name}/{self.seq}"
            self.switch.media[mxc] = (FIXTURES / info["file"]).read_bytes()
            attachments.append({"filename": info["file"], "mimetype": "application/octet-stream", "mxc": mxc})
        msg_id = message_id or f"$m{self.seq}-{uuid.uuid4().hex[:6]}"
        record_event(
            {
                "type": "message",
                "room_id": ROOMS[room],
                "payload": {
                    "addressed": addressed,
                    "sender": SENDERS[who],
                    "message_id": msg_id,
                    "body": body,
                    "thread_id": thread_id,
                    "attachments": attachments,
                },
                "sequence": self.seq,
            },
            self.seq,
            "test-connection",
        )
        if drain_after:
            drain()
        return msg_id

    def upload(self, room: str, who: str, fixture: str, body: str = "") -> str:
        return self.event(room, who, body, files=[fixture])

    def raw_upload(self, room: str, who: str, data: bytes, filename: str, body: str = "") -> str:
        self.seq += 1
        mxc = f"mxc://test/raw/{self.seq}"
        self.switch.media[mxc] = data
        record_event(
            {
                "type": "message",
                "room_id": ROOMS[room],
                "payload": {
                    "sender": SENDERS[who],
                    "message_id": f"$raw{self.seq}",
                    "body": body,
                    "attachments": [{"filename": filename, "mxc": mxc}],
                },
            },
            self.seq,
            "test-connection",
        )
        drain()
        return mxc

    # -- reads --------------------------------------------------------------------------------

    def said(self, room: str) -> list[str]:
        return self.switch.messages_in(ROOMS[room])

    def last(self, room: str) -> str:
        msgs = self.said(room)
        return msgs[-1] if msgs else ""

    def case(self, ref: str) -> m.Invoice:
        with transaction() as s:
            return s.execute(select(m.Invoice).where(m.Invoice.case_ref == ref)).scalar_one()

    def cases(self) -> list[m.Invoice]:
        with transaction() as s:
            return list(s.execute(select(m.Invoice).order_by(m.Invoice.case_ref)).scalars())

    def latest_case(self) -> m.Invoice:
        return self.cases()[-1]

    def open_rr(self, case_ref: str) -> str:
        with transaction() as s:
            case = s.execute(select(m.Invoice).where(m.Invoice.case_ref == case_ref)).scalar_one()
            rr = s.execute(
                select(m.ReviewRequest).where(
                    m.ReviewRequest.invoice_id == case.id, m.ReviewRequest.status == "open"
                )
            ).scalar_one()
            return rr.public_ref

    def issues(self, case_ref: str, current_only: bool = True) -> dict[str, str]:
        with transaction() as s:
            case = s.execute(select(m.Invoice).where(m.Invoice.case_ref == case_ref)).scalar_one()
            q = select(m.Issue).where(m.Issue.invoice_id == case.id)
            if current_only:
                q = q.where(m.Issue.revision_id == case.current_revision_id)
            return {i.rule_id: i.status for i in s.execute(q).scalars()}

    def results(self, case_ref: str) -> dict[str, str]:
        """Outcomes of the latest check run of the current revision."""
        with transaction() as s:
            case = s.execute(select(m.Invoice).where(m.Invoice.case_ref == case_ref)).scalar_one()
            run = s.execute(
                select(m.CheckRun)
                .where(m.CheckRun.revision_id == case.current_revision_id)
                .order_by(m.CheckRun.run_seq.desc())
                .limit(1)
            ).scalar_one()
            return {
                r.rule_id: r.outcome
                for r in s.execute(
                    select(m.CheckResult).where(m.CheckResult.check_run_id == run.id)
                ).scalars()
            }

    def count(self, model: Any) -> int:
        with transaction() as s:
            return len(list(s.execute(select(model)).scalars()))

    def ingest(self, fixture: str, shop: str = "sharma") -> str:
        """Upload and confirm a fixture; returns its case ref."""
        self.upload(shop, shop, fixture)
        case = self.latest_case()
        self.event(shop, shop, f"ok {case.case_ref}")
        return case.case_ref
