"""Live story on Mattermost with independent accounts: shared group, private CA room, client room, isolation.

Needs the stack running against a freshly seeded database, with shared review on for `sharma`, and these accounts:
sharma (owner), mehta (CA), iyer (client.verma), gupta (other shop's owner), rao (operator).

Run: python -m tests.live.shared_story [--out report.md]
"""

from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from tests.live.mm import MM, channel, login, post

SHOP, CA, SUBMIT, OTHER, OPS = "af-shop-sharma", "af-ca-review", "af-submit-sharma", "af-shop-gupta", "af-operations"
DIR = Path("seed/fixtures")
DETAILS = re.compile(r"INV-\d|RR-\d|R-\d{4}|₹|GSTIN")


@dataclass
class Run:
    results: list[tuple[str, bool, str]] = field(default_factory=list)

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.results.append((name, ok, detail[:300]))
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail[:160]}]" if not ok else ""), flush=True)
        return ok


def messages(user: str, room: str) -> list[tuple[int, str, str, int]]:
    """(time, author, text, file count), oldest first."""
    h = login(user)
    ch = channel(h, room)
    data = httpx.get(f"{MM}/channels/{ch['id']}/posts", headers=h, params={"per_page": 100}).json()
    names: dict[str, str] = {}
    rows = []
    for pid in reversed(data["order"]):
        p = data["posts"][pid]
        uid = p["user_id"]
        if uid not in names:
            names[uid] = httpx.get(f"{MM}/users/{uid}", headers=h).json().get("username", uid)
        rows.append((p["create_at"], names[uid], p["message"], len(p.get("file_ids") or [])))
    return rows


def mark(user: str, room: str) -> int:
    rows = messages(user, room)
    return rows[-1][0] if rows else 0


def wait(user: str, room: str, pattern: str, since: int, timeout: float = 60) -> str | None:
    """The first agent message after `since` matching the pattern."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for at, author, text, _ in messages(user, room):
            if at > since and author not in (user,) and re.search(pattern, text, re.S):
                return text
        time.sleep(1.5)
    return None


def quiet(user: str, room: str, since: int, seconds: float = 8) -> list[str]:
    """Agent messages that appeared after `since` within the window (expected to be none)."""
    time.sleep(seconds)
    return [t for at, a, t, _ in messages(user, room) if at > since and a == "assure-flow"]


def say(user: str, room: str, text: str = "", file: str | None = None) -> int:
    before = mark(user, room)
    post(user, room, text, file=str(DIR / file) if file else None)
    return before


def add_member(actor: str, room: str, username: str) -> None:
    h = login(actor)
    ch = channel(h, room)
    uid = httpx.get(f"{MM}/users/username/{username}", headers=h).json()["id"]
    httpx.post(f"{MM}/channels/{ch['id']}/members", headers=h, json={"user_id": uid}).raise_for_status()


def rr_of(text: str | None) -> str:
    match = re.search(r"RR-\d{4,}", text or "")
    return match.group(0) if match else ""


def story(run: Run) -> None:
    add_member("sharma", SHOP, "mehta")
    time.sleep(3)

    # Owner working alone: a clean bill reaches the CA with no forwarding.
    since = say("sharma", SHOP, file="F01_clean_intrastate_5pct.pdf")
    run.check("owner upload is read and summarized", bool(wait("sharma", SHOP, r"INV-0001 r1: please check", since)))
    since = say("sharma", SHOP, "ok INV-0001 r1")
    review = wait("sharma", SHOP, r"RR-\d+ · INV-0001 r1.*Suggestion from the checks, not a decision: include it", since)
    run.check("confirmed bill reaches the shared group with a labelled suggestion", bool(review), review or "")
    first_rr = rr_of(review)
    run.check(
        "private room gets a pointer without details",
        bool(wait("mehta", CA, rf"{first_rr}.*posted in the shop's group", since)),
    )

    # Client: only ever sees "received"; owner still confirms.
    since = say("iyer", SUBMIT, file="F02_clean_scan_12pct.pdf")
    run.check("client bill appears in the group with who sent it", bool(wait("sharma", SHOP, r"Verma Supplies sent", since)))
    run.check("client bill summary goes to the owner", bool(wait("sharma", SHOP, r"INV-0002 r1: please check", since)))
    run.check("client gets a received note", bool(wait("iyer", SUBMIT, r"Received F02", since)))
    since = say("sharma", SHOP, "ok INV-0002 r1")
    run.check("client bill reaches the CA after the owner confirms", bool(wait("sharma", SHOP, r"RR-\d+ · INV-0002", since)))
    client_view = [t for _, a, t, _ in messages("iyer", SUBMIT) if a == "assure-flow"]
    run.check("client never sees case details", not any(DETAILS.search(t) for t in client_view), str(client_view))
    since = say("iyer", SUBMIT, "status")
    run.check("client commands get no reply", not quiet("iyer", SUBMIT, since))

    # Owner and CA talk in one room; conversation never acts.
    since = say("sharma", SHOP, file="F08_wrong_tax_type.pdf")
    wait("sharma", SHOP, r"INV-0003 r1: please check", since)
    since = say("mehta", SHOP, "Ramesh, did this one arrive? yes or no is fine")
    say("sharma", SHOP, "yes, please call him")
    run.check("conversation gets no agent reply", not quiet("sharma", SHOP, since))
    since = say("sharma", SHOP, "ok")
    run.check("a bare ok does not confirm a bill", not quiet("sharma", SHOP, since))

    since = say("mehta", SHOP, "ok INV-0003 r1")
    refusal = wait("mehta", SHOP, r"owner|authorized", since, 30)
    run.check("CA cannot confirm bill details", bool(refusal), refusal or "")

    since = say("sharma", SHOP, "ok INV-0003 r1")
    review = wait("sharma", SHOP, r"RR-\d+ · INV-0003 r1.*R-TAX-01.*request a corrected invoice.*Priya, your decision", since)
    run.check("code catches the wrong tax, in the group, with a suggestion", bool(review), review or "")
    tax_rr = rr_of(review)

    since = say("sharma", SHOP, f"{tax_rr} include")
    run.check("owner cannot decide", bool(wait("sharma", SHOP, r"Only the CA", since, 30)))

    since = say("mehta", SHOP, "why-held INV-0003")
    run.check("results can be brought up in the group", bool(wait("mehta", SHOP, r"INV-0003", since, 30)))

    since = say("mehta", SHOP, f"{tax_rr} supplier please reissue with IGST for this interstate supply")
    run.check("CA decides in the group; supplier draft appears", bool(wait("sharma", SHOP, r"Dear Pune Electricals", since)))

    since = say("sharma", SHOP, "corrected bill for INV-0003", file="F16_replacement_for_F08.pdf")
    wait("sharma", SHOP, r"INV-0003 r2: please check", since)
    since = say("sharma", SHOP, "ok INV-0003 r2")
    review = wait("sharma", SHOP, r"RR-\d+ · INV-0003 r2", since)
    run.check("corrected bill gets a new review", bool(review), review or "")
    new_rr = rr_of(review)

    since = say("mehta", SHOP, f"{tax_rr} include")
    run.check("stale decision is refused", bool(wait("mehta", SHOP, r"older version", since, 30)))
    since = say("mehta", SHOP, f"{new_rr} include")
    run.check("CA includes the corrected bill in the group", bool(wait("mehta", SHOP, r"INV-0003 included", since, 30)))

    # The private room still works for decisions.
    since = say("mehta", CA, f"{first_rr} include")
    run.check("CA can also decide from the private room", bool(wait("mehta", CA, r"INV-0001 included", since, 30)))
    since = say("mehta", SHOP, "RR-0002 include")
    wait("mehta", SHOP, r"INV-0002 included", since, 30)

    # Another shop's owner sees nothing of this.
    since = say("gupta", OTHER, "ok INV-0001")
    reply = wait("gupta", OTHER, r"could not find", since, 30)
    run.check("another shop's owner can't reach this shop's bill", bool(reply), reply or "")
    other_view = " ".join(t for _, _, t, _ in messages("gupta", OTHER))
    run.check("nothing from Sharma's shop reaches Gupta's room", "Modern Agro" not in other_view and "Pune" not in other_view)

    # Monthly pack: private room only, one message per file, resend.
    since = say("mehta", SHOP, "snapshot sharma 2026-11")
    run.check("a pack can't be built from the shared group", not quiet("mehta", SHOP, since))
    since = say("mehta", CA, "snapshot sharma 2026-11")
    pack = wait("mehta", CA, r"SN-0001 .*hash", since)
    run.check("pack is built in the private room", bool(pack), pack or "")
    digest = re.search(r"hash ([0-9a-f]{12})", pack or "")
    assert digest, "no pack hash"
    since = say("mehta", CA, f"approve SN-0001 {digest.group(1)}")
    wait("mehta", CA, r"Excel file", since)
    wait("mehta", CA, r"JSON file", since)
    files = [(t, n) for at, a, t, n in messages("mehta", CA) if at > since and n]
    run.check("two messages, one file each", len(files) == 2 and all(n == 1 for _, n in files), str(files))
    run.check("pack stays out of the shared group", not any("SN-0001" in t for _, _, t, _ in messages("sharma", SHOP)))
    since = say("mehta", CA, "resend SN-0001 excel")
    wait("mehta", CA, r"export resent", since)
    files = [n for at, a, t, n in messages("mehta", CA) if at > since and n]
    run.check("resend delivers the stored Excel file", files == [1], str(files))

    # Reopening an approved case; the pack is labelled.
    since = say("mehta", SHOP, "reopen INV-0001 recheck after supplier call")
    run.check("approved case can be reopened", bool(wait("mehta", SHOP, r"INV-0001 reopened", since, 30)))
    run.check("the approved pack is labelled superseded", bool(wait("mehta", CA, r"SN-0001.*superseded", since, 30)))

    # Permitted warning override, with evidence in the next pack.
    since = say("sharma", SHOP, file="F10_duplicate_original.pdf")
    case = wait("sharma", SHOP, r"INV-\d+ r1: please check", since)
    original = re.search(r"INV-\d+", case or "")
    assert original
    since = say("sharma", SHOP, f"ok {original.group(0)} r1")
    wait("sharma", SHOP, rf"RR-\d+ · {original.group(0)}", since)
    since = say("sharma", SHOP, file="F11_duplicate_copy.pdf")
    case = wait("sharma", SHOP, r"INV-\d+ r1: please check", since)
    copy = re.search(r"INV-\d+", case or "")
    assert copy
    since = say("sharma", SHOP, f"{copy.group(0)} number=SDF-5521")
    wait("sharma", SHOP, rf"{copy.group(0)} r2: please check", since)
    since = say("sharma", SHOP, f"ok {copy.group(0)} r2")
    review = wait("sharma", SHOP, rf"RR-\d+ · {copy.group(0)} r2.*override R-DUP-02", since)
    run.check("review offers the R-DUP-02 override", bool(review), review or "")
    since = say("mehta", SHOP, f"{rr_of(review)} override R-DUP-02 confirmed separate deliveries")
    run.check("permitted override is recorded", bool(wait("mehta", SHOP, r"included with an override of R-DUP-02", since, 30)))
    since = say("mehta", SHOP, f"{rr_of(review)} override R-FAKE-99 nope")
    run.check("a decided request refuses another override", bool(wait("mehta", SHOP, r"older version|earlier version", since, 30)))

    # Operations room.
    since = say("rao", OPS, "health")
    run.check("operator gets a health report", bool(wait("rao", OPS, r".+", since, 30)))


def main() -> int:
    run = Run()
    try:
        story(run)
    except Exception as exc:  # noqa: BLE001 - report how far the story got
        run.check("story completed", False, f"{type(exc).__name__}: {exc}")
    passed = sum(1 for _, ok, _ in run.results if ok)
    print(f"\n{passed}/{len(run.results)} checks passed")
    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])
        rows = "\n".join(f"| {'PASS' if ok else 'FAIL'} | {name} |" for name, ok, _ in run.results)
        out.write_text(f"| Result | Check |\n|---|---|\n{rows}\n\n{passed}/{len(run.results)} checks passed\n", "utf-8")
    return 0 if passed == len(run.results) else 1


if __name__ == "__main__":
    sys.exit(main())
