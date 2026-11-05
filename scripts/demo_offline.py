"""The correction-to-export demo (spec section 13) against an in-memory Switch, printed as room transcripts.

Everything except the chat transport is real: PostgreSQL, the inbox, the worker lanes, extraction (fake
provider replaying recorded fixtures), rules, CA decisions, snapshot approval and the Excel/JSON export.
Run: python -m scripts.demo_offline     (resets the demo database)
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from common.db import transaction
from common.settings import get_settings
from domain import models as m
from tests.offline.harness import ROOMS, Harness

TITLES = {ROOMS["sharma"]: "#af-shop-sharma", ROOMS["gupta"]: "#af-shop-gupta", ROOMS["ca"]: "#af-ca-review"}
WHO = {"sharma": "Ramesh (owner)", "gupta": "Sunita (owner)", "ca": "CA Mehta"}


def main() -> None:
    if get_settings().ENVIRONMENT not in ("demo", "test"):
        sys.exit("demo resets data; run it only with ENVIRONMENT=demo")
    h = Harness.fresh()
    shown = 0

    def say(room: str, who: str, text: str = "", files: list[str] | None = None) -> None:
        nonlocal shown
        attach = f"  [{', '.join(files)}]" if files else ""
        print(f"\n{TITLES[ROOMS[room]]}  {WHO[who]}: {text}{attach}")
        h.event(room, who, text, files=files)
        for room_id, body, _ in h.switch.posts[shown:]:
            print(f"{TITLES[room_id]}  assure-flow: " + body.replace("\n", "\n" + " " * 14))
        shown = len(h.switch.posts)

    def beat(title: str) -> None:
        print("\n" + "=" * 100 + f"\n{title}\n" + "=" * 100)

    beat("1. Owner sends a blurry photo; Assure Flow asks about the uncertain total")
    say("sharma", "sharma", "", ["F13_blurry_photo"])
    beat("2. Owner corrects it by typing (no re-reading) and confirms")
    say("sharma", "sharma", "INV-0001 total=1180.00")
    say("sharma", "sharma", "ok INV-0001 r2")
    beat("3. A bill with the wrong tax type reaches the CA")
    say("sharma", "sharma", "", ["F08_wrong_tax_type"])
    say("sharma", "sharma", "ok INV-0002")
    beat("4. An unauthorized 'approve' is refused; the CA asks the supplier for a corrected bill")
    say("ca", "sharma", "RR-0002 include")
    say("ca", "ca", "RR-0002 supplier please reissue with IGST for this interstate supply")
    beat("5. The corrected bill arrives in the same case; checks rerun; the stale request is refused")
    say("sharma", "sharma", "corrected bill for INV-0002", ["F16_replacement_for_F08"])
    say("sharma", "sharma", "ok INV-0002")
    say("ca", "ca", "RR-0002 include")
    say("ca", "ca", "RR-0003 include")
    say("ca", "ca", "RR-0001 include")
    beat("6. Shop isolation: Gupta's owner cannot see Sharma's case")
    say("gupta", "gupta", "why-held INV-0001")
    beat("7. A third bill stays held; the CA reviews a PARTIAL pack and approves its exact hash")
    say("sharma", "sharma", "", ["F09_total_mismatch"])
    say("sharma", "sharma", "ok INV-0003")
    say("ca", "ca", "snapshot sharma 2026-11")
    with transaction() as s:
        snap = s.execute(select(m.Snapshot).order_by(m.Snapshot.created_at.desc()).limit(1)).scalar_one()
        ref, digest, counts = snap.public_ref, snap.content_hash, snap.manifest["counts"]
    say("ca", "ca", f"approve {ref} {digest[:12]} ack {counts['held']} {counts['unassigned']}")
    print("\nFiles posted to the CA room:", h.switch.uploads[-1][1] if h.switch.uploads else "none")


if __name__ == "__main__":
    main()
