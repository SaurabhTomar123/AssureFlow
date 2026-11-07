"""Idempotent reset and seed (P0-07). Refuses to run outside demo/test."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import text
from sqlalchemy.orm import Session

from common.db import Base, transaction
from common.settings import get_settings
from domain import models as m
from rules.gstin import make_gstin
from rules.registry import PROFILE, RULES

ROOT = Path(__file__).resolve().parent.parent


def truncate_all(s: Session) -> None:
    names = ", ".join(t.name for t in Base.metadata.sorted_tables)
    s.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


def seed(s: Session, rooms_file: Path | None = None) -> dict[str, Any]:
    settings = get_settings()
    data = yaml.safe_load((ROOT / "seed" / "practice.yaml").read_text("utf-8"))
    rooms = yaml.safe_load((rooms_file or ROOT / settings.ROOM_BINDINGS_FILE).read_text("utf-8"))
    s.add(m.EnvironmentRow(name=settings.ENVIRONMENT))
    practice = m.Practice(name=data["practice"])
    s.add(practice)
    s.flush()
    shops: dict[str, m.Shop] = {}
    for sh in data["shops"]:
        shop = m.Shop(
            practice_id=practice.id,
            code=sh["code"],
            name=sh["name"],
            state_code=sh["state_code"],
            gstin=make_gstin(sh["state_code"], sh["pan"]),
            purchase_assurance=bool(sh.get("purchase_assurance", False)),
            shared_review=bool(sh.get("shared_review", False)),
        )
        s.add(shop)
        shops[sh["code"]] = shop
    s.flush()
    users: dict[str, m.User] = {}
    for u in data["users"]:
        user = m.User(practice_id=practice.id, handle=u["handle"], display_name=u["name"], role=u["role"])
        s.add(user)
        s.flush()
        users[u["handle"]] = user
        for code in u.get("shops", []):
            s.add(m.ShopMembership(user_id=user.id, shop_id=shops[code].id, role="owner"))
        for code in u.get("assigned", []):
            s.add(m.CaAssignment(ca_user_id=user.id, shop_id=shops[code].id))
        for code, caps in (u.get("capabilities") or {}).items():
            for cap in caps:
                s.add(
                    m.ShopCapability(
                        practice_id=practice.id, shop_id=shops[code].id, user_id=user.id, capability=cap
                    )
                )
    for room in rooms["rooms"]:
        if not room.get("provision"):
            continue
        binding = m.RoomBinding(
            environment=settings.ENVIRONMENT,
            practice_id=practice.id,
            name=room["name"],
            switch_room_id=f"unbound:{room['name']}",
            purpose=room["purpose"],
            human_roles=sorted({users[h].role for h in room["members"]}),
            permitted_agent_senders=[],
            agent_roles_and_tools=room.get("agents", {}),
            config_version=str(rooms["config_version"]),
        )
        s.add(binding)
        s.flush()
        for code in room["shops"]:
            s.add(m.RoomBindingShop(room_binding_id=binding.id, shop_id=shops[code].id))
        for handle in room["members"]:
            s.add(m.RoomMember(room_binding_id=binding.id, user_id=users[handle].id))
    seed_orders(s, practice, shops)
    for rule in RULES:
        s.add(
            m.RuleDefinition(
                rule_id=rule.rule_id,
                version=rule.version,
                profile=PROFILE,
                effective_from=rule.effective_from,
                category=rule.category,
                overridable=rule.overridable,
                reference=rule.reference,
                description=rule.description,
            )
        )
    s.flush()
    return {"practice": practice, "shops": shops, "users": users}


def seed_orders(s: Session, practice: m.Practice, shops: dict[str, m.Shop]) -> None:
    """Structured seeded purchase orders, created as drafts for the owner to confirm in chat (D-29)."""
    path = ROOT / "seed" / "purchase_orders.yaml"
    if not path.exists():
        return
    for order in yaml.safe_load(path.read_text("utf-8"))["orders"]:
        shop = shops[order["shop"]]
        po = m.PurchaseOrder(
            practice_id=practice.id,
            shop_id=shop.id,
            order_ref=order["order_ref"],
            supplier_name=order["supplier_name"],
            supplier_gstin=make_gstin(order["supplier_state"], order["supplier_pan"]),
            status="draft",
        )
        s.add(po)
        s.flush()
        rev = m.PurchaseOrderRevision(
            practice_id=practice.id,
            shop_id=shop.id,
            order_id=po.id,
            revision_no=1,
            status="draft",
            expected_delivery_date=order.get("expected_delivery_date"),
            currency="INR",
            lines=[{k: str(v) for k, v in line.items()} for line in order["lines"]],
        )
        s.add(rev)
        s.flush()
        po.current_revision_id = rev.id


def reset_and_seed(url: str | None = None) -> None:
    settings = get_settings()
    if settings.ENVIRONMENT not in ("demo", "test"):
        raise SystemExit(f"refusing to reset in environment '{settings.ENVIRONMENT}'")
    with transaction(url) as s:
        truncate_all(s)
        seed(s)


if __name__ == "__main__":
    reset_and_seed()
    print("seeded: 1 practice, 2 shops, 8 users, 8 room bindings, 1 draft purchase order")
