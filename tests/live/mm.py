"""Live-integration driver: act as a synthetic Mattermost user (the bridged chat app) and read channels.

Usage: python -m tests.live.mm <user> <room-name> [text] [--file PATH]
       python -m tests.live.mm read <room-name> [N]
Credentials for the synthetic users are in data/mattermost_test_users.json (never committed).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

MM = "http://localhost:8065/api/v4"
USERS = json.loads(Path("data/mattermost_test_users.json").read_text("utf-8"))


def login(user: str) -> dict[str, str]:
    r = httpx.post(f"{MM}/users/login", json={"login_id": user, "password": USERS[user]["password"]})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.headers['Token']}"}


def channel(headers: dict[str, str], name: str) -> dict[str, Any]:
    team = httpx.get(f"{MM}/teams/name/switch", headers=headers).json()
    for ch in httpx.get(f"{MM}/users/me/teams/{team['id']}/channels", headers=headers).json():
        if name in (ch["display_name"], ch["name"]) or ch["display_name"].endswith(name):
            return dict(ch)
    raise SystemExit(f"{name}: not a member, or channel not found")


def post(user: str, room: str, text: str = "", file: str | None = None) -> str:
    h = login(user)
    ch = channel(h, room)
    file_ids: list[str] = []
    if file:
        data = Path(file).read_bytes()
        mime = "application/pdf" if file.endswith(".pdf") else "image/png"
        r = httpx.post(
            f"{MM}/files",
            headers=h,
            data={"channel_id": ch["id"]},
            files={"files": (Path(file).name, data, mime)},
        )
        r.raise_for_status()
        file_ids = [f["id"] for f in r.json()["file_infos"]]
    r = httpx.post(
        f"{MM}/posts", headers=h, json={"channel_id": ch["id"], "message": text, "file_ids": file_ids}
    )
    r.raise_for_status()
    return str(r.json()["id"])


def read(room: str, n: int = 12, as_user: str = "mehta") -> list[str]:
    h = login(
        as_user
        if room == "af-ca-review"
        else {"af-shop-sharma": "sharma", "af-shop-gupta": "gupta"}.get(room, as_user)
    )
    ch = channel(h, room)
    data = httpx.get(f"{MM}/channels/{ch['id']}/posts", headers=h, params={"per_page": n}).json()
    users: dict[str, str] = {}
    lines = []
    for pid in reversed(data["order"]):
        p = data["posts"][pid]
        uid = p["user_id"]
        if uid not in users:
            users[uid] = httpx.get(f"{MM}/users/{uid}", headers=h).json().get("username", uid)
        files = f" [{len(p.get('file_ids') or [])} file(s)]" if p.get("file_ids") else ""
        lines.append(f"{users[uid]}: {p['message']}{files}")
    return lines


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "read":
        for line in read(args[1], int(args[2]) if len(args) > 2 else 12):
            print(line)
    else:
        f = None
        if "--file" in args:
            i = args.index("--file")
            f = args[i + 1]
            args = args[:i] + args[i + 2 :]
        print(post(args[0], args[1], " ".join(args[2:]), file=f))
        time.sleep(0.2)
