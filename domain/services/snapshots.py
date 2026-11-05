"""Monthly snapshot contract: frozen, complete manifest; canonical JSON; atomic hash approval."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from common.errors import Forbidden, NotFound, ValidationFailed
from common.ids import next_ref
from domain.context import issue_grant, require_live_context
from domain.extraction import HEADER_FIELDS, LINE_FIELDS
from domain.models import (
    CheckResult,
    Decision,
    DecisionInvalidation,
    Document,
    FieldEvidence,
    Invoice,
    InvoiceRevision,
    Issue,
    LineItem,
    RequestContext,
    Shop,
    Snapshot,
    utcnow,
)
from domain.periods import Readiness, readiness, why_held
from domain.scope import is_assigned_ca
from domain.services import compensation
from domain.services import messages as msg
from domain.services.base import UNASSIGNED, period_version, post, room_for_shop
from domain.services.cases import duplicate_key
from domain.services.checks import latest_run
from rules.registry import PROFILE
from workers.queue import enqueue

ITC_WORDING = (
    "Tax on reviewed purchases. Potential ITC pending GSTR-2B reconciliation and eligibility review. "
    "This is a review pack, not a GST return; the CA files separately."
)


class DuplicateInManifest(ValidationFailed):
    pass


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_dec).encode(
        "utf-8"
    )


def _dec(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"not serializable: {type(value).__name__}")


def _d(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _included_entry(s: Session, case: Invoice) -> dict[str, Any]:
    rev = s.get(InvoiceRevision, case.current_revision_id)
    assert rev is not None
    run = latest_run(s, rev.id)
    assert run is not None
    doc = s.get(Document, rev.document_id)
    lines = [
        {
            "line_no": li.line_no,
            **{
                f: (_d(getattr(li, f)) if f not in ("description", "hsn_sac") else getattr(li, f))
                for f in LINE_FIELDS
            },
        }
        for li in s.execute(select(LineItem).where(LineItem.revision_id == rev.id)).scalars()
    ]
    results = [
        {
            "rule_id": r.rule_id,
            "version": r.rule_version,
            "outcome": r.outcome,
            "severity": r.severity,
            "message": r.message,
            "calculation": r.calculation,
            "difference": _d(r.difference),
        }
        for r in s.execute(select(CheckResult).where(CheckResult.check_run_id == run.id)).scalars()
    ]
    invalidated = set(s.execute(select(DecisionInvalidation.decision_id)).scalars())
    decisions = [
        {"id": str(d.id), "seq": i, "action": d.action, "reason": d.reason, "actor": str(d.actor_user_id)}
        for i, d in enumerate(
            s.execute(
                select(Decision).where(Decision.revision_id == rev.id).order_by(Decision.created_at)
            ).scalars()
        )
        if d.id not in invalidated
    ]
    overrides = [
        {"rule_id": i.rule_id, "disposition": i.disposition}
        for i in s.execute(
            select(Issue).where(Issue.revision_id == rev.id, Issue.status == "resolved")
        ).scalars()
    ]
    evidence = [
        {
            "field": e.field_path,
            "page": e.page_no,
            "source": e.source,
            "excerpt_sha256": hashlib.sha256((e.excerpt or "").encode()).hexdigest() if e.excerpt else None,
        }
        for e in s.execute(select(FieldEvidence).where(FieldEvidence.revision_id == rev.id)).scalars()
    ]
    header = {
        f: (_d(getattr(rev, f)) if isinstance(getattr(rev, f), Decimal) else getattr(rev, f))
        for f in HEADER_FIELDS
    }
    return {
        "case_ref": case.case_ref,
        "revision": {
            "revision_no": rev.revision_no,
            "source": rev.source,
            **header,
            "lines": sorted(lines, key=lambda x: x["line_no"]),
        },
        "check_run": {
            "run_seq": run.run_seq,
            "profile": run.profile_version,
            "results_hash": run.results_hash,
            "results": sorted(results, key=lambda x: x["rule_id"]),
        },
        "decisions": decisions,
        "overrides": sorted(overrides, key=lambda x: x["rule_id"]),
        "evidence": {
            "document_sha256": doc.sha256 if doc else None,
            "fields": sorted(evidence, key=lambda x: x["field"]),
        },
        "duplicate_key": duplicate_key(rev),
    }


def _excluded_reason(s: Session, case: Invoice) -> str | None:
    d = s.execute(
        select(Decision)
        .where(Decision.invoice_id == case.id, Decision.action == "exclude")
        .order_by(Decision.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return d.reason if d else None


def build_manifest(s: Session, shop: Shop, ready: Readiness) -> tuple[dict[str, Any], dict[str, int]]:
    included = [_included_entry(s, c) for c in ready.included]
    keys = [e["duplicate_key"] for e in included if e["duplicate_key"]]
    if len(keys) != len(set(keys)):
        raise DuplicateInManifest(
            "Two included cases share a duplicate key; exclude one or resolve the issue first."
        )
    totals = {name: Decimal("0.00") for name in ("taxable", "cgst", "sgst", "igst", "cess", "total")}
    for entry in included:
        rev = entry["revision"]
        for name, field in (
            ("taxable", "taxable_total"),
            ("cgst", "cgst_total"),
            ("sgst", "sgst_total"),
            ("igst", "igst_total"),
            ("cess", "cess_total"),
            ("total", "invoice_total"),
        ):
            totals[name] += Decimal(rev[field] or "0")
    cutoff = {
        c.case_ref: c.event_seq for c in (*ready.included, *ready.excluded, *ready.held, *ready.unassigned)
    }
    manifest = {
        "schema": "assure-flow.snapshot.v1",
        "shop": {"code": shop.code, "name": shop.name, "gstin": shop.gstin},
        "period": ready.period,
        "rule_profiles": [PROFILE],
        "included": sorted(included, key=lambda x: x["case_ref"]),
        "excluded": [{"case_ref": c.case_ref, "reason": _excluded_reason(s, c)} for c in ready.excluded],
        "held": [{"case_ref": c.case_ref, "status": c.status, "why": why_held(s, c)} for c in ready.held],
        "unassigned": [{"case_ref": c.case_ref, "status": c.status} for c in ready.unassigned],
        "totals": {k: str(v) for k, v in totals.items()},
        "counts": {
            "included": len(ready.included),
            "excluded": len(ready.excluded),
            "held": len(ready.held),
            "unassigned": len(ready.unassigned),
        },
        "partial": not ready.complete,
        "itc_wording": ITC_WORDING,
    }
    return manifest, cutoff


def build_snapshot(s: Session, shop: Shop, period: str, correlation_id: str) -> Snapshot:
    """Build the frozen manifest at the current shop-period versions (fast-lane job body)."""
    p_version = period_version(s, shop.id, period)
    u_version = period_version(s, shop.id, UNASSIGNED)
    ready = readiness(s, shop.id, period)
    manifest, cutoff = build_manifest(s, shop, ready)
    payload = canonical(manifest)
    version = (
        s.execute(
            select(func.coalesce(func.max(Snapshot.version), 0)).where(
                Snapshot.shop_id == shop.id, Snapshot.period == period
            )
        ).scalar_one()
        + 1
    )
    for old in s.execute(
        select(Snapshot).where(
            Snapshot.shop_id == shop.id, Snapshot.period == period, Snapshot.status == "awaiting_ca"
        )
    ).scalars():
        old.status = "superseded"
        compensation.snapshot_superseded(s, old, "rebuilt", correlation_id)
    snap = Snapshot(
        practice_id=shop.practice_id,
        shop_id=shop.id,
        public_ref=next_ref(s, shop.practice_id, "SN"),
        period=period,
        version=version,
        status="awaiting_ca",
        period_version=p_version,
        unassigned_version=u_version,
        manifest=manifest,
        manifest_bytes=payload.decode("utf-8"),
        content_hash=hashlib.sha256(payload).hexdigest(),
        history_cutoff=cutoff,
        partial=manifest["partial"],
    )
    s.add(snap)
    s.flush()
    room = room_for_shop(s, shop.id, "ca_review")
    if room is not None:
        t = manifest["totals"]
        counts = manifest["counts"]
        lines = [
            f"{snap.public_ref} · {shop.name} · {period} · v{version} · hash {snap.content_hash[:12]}",
            f"Included {counts['included']} · excluded {counts['excluded']} · held {counts['held']} · "
            f"unassigned {counts['unassigned']}",
            f"Taxable {msg.inr(Decimal(t['taxable']))} · CGST {msg.inr(Decimal(t['cgst']))} · "
            f"SGST {msg.inr(Decimal(t['sgst']))} · IGST {msg.inr(Decimal(t['igst']))} · "
            f"Total {msg.inr(Decimal(t['total']))}",
        ]
        for item in manifest["held"][:5]:
            lines.append(f"• held: {item['why']}")
        for item in manifest["unassigned"][:5]:
            lines.append(f"• unassigned: {item['case_ref']} ({item['status'].replace('_', ' ')})")
        if snap.partial:
            lines.append(
                f"PARTIAL. To approve anyway: `approve {snap.public_ref} {snap.content_hash[:12]} "
                f"ack {counts['held']} {counts['unassigned']}`"
            )
        else:
            lines.append(f"To approve: `approve {snap.public_ref} {snap.content_hash[:12]}`")
        lines.append(ITC_WORDING)
        post(s, room, action_id=f"snapshot:{snap.id}", body="\n".join(lines), correlation_id=correlation_id)
    return snap


def request_snapshot(s: Session, ctx: RequestContext, shop: Shop, period: str) -> None:
    require_live_context(ctx)
    if not is_assigned_ca(s, ctx.verified_user_id, shop.id):
        raise Forbidden("Only the assigned CA can request a monthly pack.")
    grant = issue_grant(
        s, operation="build_snapshot", practice_id=shop.practice_id, shop_id=shop.id, context=ctx
    )
    enqueue(
        s,
        type="build_snapshot",
        lane="fast",
        payload={"shop_id": str(shop.id), "period": period},
        dedupe_key=f"snapshot:{shop.id}:{period}:{ctx.request_id}",
        correlation_id=ctx.request_id,
        grant_id=grant.grant_id,
    )


@dataclass
class ApprovalOutcome:
    approved: bool
    reply: str


def approve_snapshot(
    s: Session, ctx: RequestContext, ref: str, hash_prefix: str, ack: tuple[int, int] | None
) -> ApprovalOutcome:
    """One transaction: lock the period and UNASSIGNED version rows, require them unchanged (R14, R15)."""
    require_live_context(ctx)
    snap = s.execute(
        select(Snapshot)
        .where(Snapshot.practice_id == ctx.practice_id, Snapshot.public_ref == ref)
        .with_for_update()
    ).scalar_one_or_none()
    if snap is None:
        raise NotFound(f"No snapshot {ref}.")
    if not is_assigned_ca(s, ctx.verified_user_id, snap.shop_id):
        raise Forbidden("Only the assigned CA can approve this pack.")
    if snap.status != "awaiting_ca":
        raise ValidationFailed(f"{ref} is {snap.status}; approve the latest pack instead.")
    if len(hash_prefix) < 12 or not snap.content_hash.startswith(hash_prefix.lower()):
        raise ValidationFailed(
            f"The hash does not match {ref}. Approval must name the exact pack you reviewed."
        )
    p_now = period_version(s, snap.shop_id, snap.period, lock=True)
    u_now = period_version(s, snap.shop_id, UNASSIGNED, lock=True)
    if (p_now, u_now) != (snap.period_version, snap.unassigned_version):
        snap.status = "stale"
        compensation.snapshot_superseded(s, snap, "stale", ctx.request_id)
        shop = s.get(Shop, snap.shop_id)
        assert shop is not None
        grant = issue_grant(
            s, operation="build_snapshot", practice_id=shop.practice_id, shop_id=shop.id, context=ctx
        )
        enqueue(
            s,
            type="build_snapshot",
            lane="fast",
            payload={"shop_id": str(shop.id), "period": snap.period},
            dedupe_key=f"snapshot:{shop.id}:{snap.period}:rebuild:{snap.id}",
            correlation_id=ctx.request_id,
            grant_id=grant.grant_id,
        )
        return ApprovalOutcome(
            False,
            f"SNAPSHOT_STALE: the month changed after {ref} was built, so nothing was approved. "
            "A rebuilt pack follows.",
        )
    counts = snap.manifest["counts"]
    if snap.partial:
        if ack != (counts["held"], counts["unassigned"]):
            raise ValidationFailed(
                f"{ref} is PARTIAL. Acknowledge exactly {counts['held']} held and {counts['unassigned']} unassigned: "
                f"`approve {ref} {snap.content_hash[:12]} ack {counts['held']} {counts['unassigned']}`."
            )
        snap.acknowledged_held_ids = [h["case_ref"] for h in snap.manifest["held"]]
        snap.acknowledged_unassigned_ids = [u["case_ref"] for u in snap.manifest["unassigned"]]
    for old in s.execute(
        select(Snapshot).where(
            Snapshot.shop_id == snap.shop_id,
            Snapshot.period == snap.period,
            Snapshot.status.in_(("approved", "exported")),
            Snapshot.id != snap.id,
        )
    ).scalars():
        old.status, old.superseded_by = "superseded", snap.id
        compensation.snapshot_superseded(s, old, "approved_newer", ctx.request_id)
    snap.status = "approved"
    snap.approved_by = ctx.verified_user_id
    snap.approved_at = utcnow()
    grant = issue_grant(
        s,
        operation="build_export",
        practice_id=snap.practice_id,
        shop_id=snap.shop_id,
        snapshot_id=snap.id,
        context=ctx,
    )
    enqueue(
        s,
        type="build_export",
        lane="slow",
        payload={"snapshot_id": str(snap.id)},
        dedupe_key=f"export:{snap.id}",
        correlation_id=ctx.request_id,
        grant_id=grant.grant_id,
    )
    label = "PARTIAL pack" if snap.partial else "Pack"
    return ApprovalOutcome(
        True, f"{label} {ref} approved (hash {snap.content_hash[:12]}). Excel and JSON exports follow."
    )
