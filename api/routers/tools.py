"""Business-tool routes. Each route is one narrow tool; cross-shop lookups return 404 (no existence leak).

Agents can read and request; they can never confirm, decide or approve (those come only from a human's
own room reply, processed by code).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.storage import LocalStorage
from api.deps import Caller, caller, get_db
from common.errors import Forbidden, NotFound
from domain.models import (
    Artifact,
    CheckResult,
    ExecutionGrant,
    FieldEvidence,
    Handoff,
    Invoice,
    Issue,
    Job,
    Receipt,
    Shop,
    Snapshot,
)
from domain.periods import parse_period, readiness, why_held
from domain.scope import can_read_shop, is_assigned_ca
from domain.services import operations as ops
from domain.services.base import post, room_for_shop
from domain.services.cases import current_revision
from domain.services.checks import latest_run
from domain.services.snapshots import request_snapshot

router = APIRouter()


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SnapshotRequest(Strict):
    """No user, shop or role fields: identity comes only from the request context (422 otherwise)."""


class DecisionRequest(Strict):
    action: str
    reason: str | None = None


def _case(s: Session, c: Caller, ref: str) -> Invoice:
    case = s.execute(
        select(Invoice).where(Invoice.practice_id == c.context.practice_id, Invoice.case_ref == ref.upper())
    ).scalar_one_or_none()
    if (
        case is None
        or case.shop_id not in c.shops
        or not can_read_shop(s, c.context.verified_user_id, case.shop_id)
    ):
        raise NotFound(f"No case {ref}.")
    return case


def _shop(s: Session, c: Caller, code: str) -> Shop:
    shop = s.execute(
        select(Shop).where(Shop.practice_id == c.context.practice_id, Shop.code == code.lower())
    ).scalar_one_or_none()
    if shop is None or shop.id not in c.shops or not can_read_shop(s, c.context.verified_user_id, shop.id):
        raise NotFound(f"No shop {code}.")
    return shop


@router.get("/context")
def get_request_context(c: Caller = Depends(caller)) -> dict[str, Any]:
    c.require_tool("get_request_context")
    return {
        "verified_user_id": str(c.context.verified_user_id),
        "room": c.room.name,
        "purpose": c.room.purpose,
        "shops": [str(x) for x in c.shops],
        "expires_at": c.context.expires_at.isoformat(),
    }


@router.get("/receipts/{ref}")
def get_receipt_status(ref: str, c: Caller = Depends(caller), s: Session = Depends(get_db)) -> dict[str, Any]:
    c.require_tool("get_receipt_status")
    receipt = s.execute(
        select(Receipt).where(Receipt.practice_id == c.context.practice_id, Receipt.public_ref == ref.upper())
    ).scalar_one_or_none()
    if receipt is None or receipt.shop_id not in c.shops:
        raise NotFound(f"No receipt {ref}.")
    return {"receipt": receipt.public_ref, "status": receipt.status, "reason": receipt.reject_reason}


@router.get("/invoices/{ref}")
def get_case(ref: str, c: Caller = Depends(caller), s: Session = Depends(get_db)) -> dict[str, Any]:
    c.require_tool("get_case")
    case = _case(s, c, ref)
    rev = current_revision(s, case)
    evidence = (
        [
            {
                "field": e.field_path,
                "value": e.value_text,
                "page": e.page_no,
                "source": e.source,
                "confidence": str(e.confidence) if e.confidence is not None else None,
            }
            for e in s.execute(select(FieldEvidence).where(FieldEvidence.revision_id == rev.id)).scalars()
        ]
        if rev
        else []
    )
    return {
        "case_ref": case.case_ref,
        "status": case.status,
        "document_generation": case.document_generation,
        "revision": rev.revision_no if rev else None,
        "period": case.period,
        "next_action": why_held(s, case),
        "evidence": evidence,
    }


@router.get("/invoices/{ref}/checks")
def get_check_results(ref: str, c: Caller = Depends(caller), s: Session = Depends(get_db)) -> dict[str, Any]:
    c.require_tool("get_check_results")
    case = _case(s, c, ref)
    rev = current_revision(s, case)
    run = latest_run(s, rev.id) if rev else None
    if run is None:
        return {"case_ref": case.case_ref, "check_run": None, "results": []}
    results = [
        {
            "rule_id": r.rule_id,
            "version": r.rule_version,
            "outcome": r.outcome,
            "severity": r.severity,
            "message": r.message,
            "calculation": r.calculation,
        }
        for r in s.execute(select(CheckResult).where(CheckResult.check_run_id == run.id)).scalars()
    ]
    return {
        "case_ref": case.case_ref,
        "check_run": run.run_seq,
        "results": sorted(results, key=lambda r: r["rule_id"]),
    }


@router.get("/shops/{code}/periods/{period}/readiness")
def get_period_readiness(
    code: str, period: str, c: Caller = Depends(caller), s: Session = Depends(get_db)
) -> dict[str, Any]:
    c.require_tool("get_period_readiness")
    shop = _shop(s, c, code)
    ready = readiness(s, shop.id, parse_period(period))
    return {
        "shop": shop.code,
        "period": period,
        "complete": ready.complete,
        "included": [x.case_ref for x in ready.included],
        "excluded": [x.case_ref for x in ready.excluded],
        "held": [x.case_ref for x in ready.held],
        "unassigned": [x.case_ref for x in ready.unassigned],
    }


@router.post("/shops/{code}/periods/{period}/snapshots", status_code=202)
def post_request_snapshot(
    code: str, period: str, body: SnapshotRequest, c: Caller = Depends(caller), s: Session = Depends(get_db)
) -> dict[str, Any]:
    c.require_tool("request_snapshot")
    shop = _shop(s, c, code)
    request_snapshot(s, c.context, shop, parse_period(period))
    job = s.execute(
        select(Job).where(Job.type == "build_snapshot").order_by(Job.created_at.desc()).limit(1)
    ).scalar_one()
    return {"job_id": str(job.id), "status_url": f"/jobs/{job.id}"}


@router.get("/snapshots/{ref}/manifest")
def get_snapshot_manifest(
    ref: str, c: Caller = Depends(caller), s: Session = Depends(get_db)
) -> dict[str, Any]:
    c.require_tool("get_snapshot_manifest")
    snap = s.execute(
        select(Snapshot).where(
            Snapshot.practice_id == c.context.practice_id, Snapshot.public_ref == ref.upper()
        )
    ).scalar_one_or_none()
    if (
        snap is None
        or snap.shop_id not in c.shops
        or not is_assigned_ca(s, c.context.verified_user_id, snap.shop_id)
    ):
        raise NotFound(f"No snapshot {ref}.")
    return {
        "snapshot": snap.public_ref,
        "status": snap.status,
        "content_hash": snap.content_hash,
        "manifest": snap.manifest,
    }


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(
    artifact_id: uuid.UUID, c: Caller = Depends(caller), s: Session = Depends(get_db)
) -> Response:
    art = s.get(Artifact, artifact_id)
    if (
        art is None
        or art.shop_id not in c.shops
        or not is_assigned_ca(s, c.context.verified_user_id, art.shop_id)
    ):
        raise NotFound("No such artifact.")
    media = (
        "application/json"
        if art.kind == "json"
        else ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    )
    return Response(
        LocalStorage().get(art.storage_key),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{art.filename}"'},
    )


@router.get("/jobs/{job_id}")
def get_job(job_id: uuid.UUID, c: Caller = Depends(caller), s: Session = Depends(get_db)) -> dict[str, Any]:
    job = s.get(Job, job_id)
    grant = s.get(ExecutionGrant, job.grant_id) if job and job.grant_id else None
    if job is None or grant is None or grant.shop_id not in c.shops:
        raise NotFound("No such job.")
    return {"job_id": str(job.id), "type": job.type, "status": job.status, "attempts": job.attempts}


@router.post("/review-requests/{ref}/decisions")
def post_decision(ref: str, body: DecisionRequest, c: Caller = Depends(caller)) -> dict[str, Any]:
    """Agents can never decide or approve. CA decisions arrive only as the CA's own room reply."""
    raise Forbidden("Decisions are recorded only from the assigned CA's own reply in the CA review room.")


@router.get("/status")
def get_status(c: Caller = Depends(caller), s: Session = Depends(get_db)) -> dict[str, Any]:
    """Status of the shop this room covers (shop intake rooms only)."""
    c.require_tool("get_status")
    if len(c.shops) != 1 or not can_read_shop(s, c.context.verified_user_id, c.shops[0]):
        raise NotFound("This room does not cover exactly one shop.")
    cases = list(
        s.execute(select(Invoice).where(Invoice.shop_id == c.shops[0]).order_by(Invoice.case_ref)).scalars()
    )
    return {
        "cases": [{"case_ref": x.case_ref, "status": x.status, "why": why_held(s, x)} for x in cases],
    }


@router.get("/invoices/{ref}/issues/{rule_id}")
def explain_issue(
    ref: str, rule_id: str, c: Caller = Depends(caller), s: Session = Depends(get_db)
) -> dict[str, Any]:
    c.require_tool("explain_issue")
    case = _case(s, c, ref)
    issue = s.execute(
        select(Issue).where(Issue.revision_id == case.current_revision_id, Issue.rule_id == rule_id.upper())
    ).scalar_one_or_none()
    if issue is None:
        raise NotFound(f"No issue {rule_id} on {ref}.")
    result = s.get(CheckResult, issue.check_result_id)
    return {
        "rule_id": issue.rule_id,
        "status": issue.status,
        "owner": issue.owner_role,
        "next_action": issue.next_action,
        "message": result.message if result else None,
        "calculation": result.calculation if result else {},
        "tax_amount_associated": str(issue.exposure_amount) if issue.exposure_amount is not None else None,
        "wording": "Tax amount associated with this issue; not money lost and not an eligibility decision.",
    }


@router.get("/invoices/{ref}/supplier-draft")
def draft_supplier_request(
    ref: str, c: Caller = Depends(caller), s: Session = Depends(get_db)
) -> dict[str, Any]:
    """A draft only: an authorized owner sends it; agents never message suppliers."""
    c.require_tool("draft_supplier_request")
    case = _case(s, c, ref)
    rev = current_revision(s, case)
    if rev is None:
        raise NotFound(f"{ref} has not been read yet.")
    issues = [
        i.rule_id
        for i in s.execute(
            select(Issue).where(
                Issue.revision_id == rev.id, Issue.status.in_(("awaiting_supplier", "awaiting_ca"))
            )
        ).scalars()
    ]
    return {
        "case_ref": case.case_ref,
        "draft": (
            f"Dear {rev.supplier_name or 'Supplier'},\nPlease issue a corrected tax invoice for "
            f"{rev.invoice_number or 'the invoice'} dated {rev.invoice_date or '?'} "
            f"(points: {', '.join(issues) or 'see attached review'}).\nThank you."
        ),
        "send": "owner sends it; not sent automatically",
    }


@router.get("/handoffs/pending")
def list_pending_handoffs(c: Caller = Depends(caller), s: Session = Depends(get_db)) -> dict[str, Any]:
    c.require_tool("list_pending_handoffs")
    rows = s.execute(
        select(Handoff, Invoice.case_ref)
        .join(Invoice, Invoice.id == Handoff.case_id)
        .where(Handoff.shop_id.in_(c.shops), Handoff.status == "pending")
        .order_by(Handoff.created_at)
    ).all()
    return {
        "handoffs": [
            {
                "case_ref": ref,
                "summary": h.issue_summary,
                "next_action": h.next_action,
                "responsible": h.responsible_role,
            }
            for h, ref in rows
            if is_assigned_ca(s, c.context.verified_user_id, h.shop_id)
        ]
    }


@router.get("/directory")
def list_directory(c: Caller = Depends(caller), s: Session = Depends(get_db)) -> dict[str, Any]:
    c.require_tool("list_directory")
    return {"directory": ops.directory_text(s, c.context, c.room)}


@router.get("/ops/health")
def get_health(c: Caller = Depends(caller), s: Session = Depends(get_db)) -> dict[str, Any]:
    c.require_tool("get_health")
    ops.require_role(s, c.context, "operator")
    return {"health": ops.health_text(s)}


@router.get("/ops/failed-jobs")
def list_failed_jobs(c: Caller = Depends(caller), s: Session = Depends(get_db)) -> dict[str, Any]:
    c.require_tool("list_failed_jobs")
    ops.require_role(s, c.context, "operator")
    return {"failed": ops.failed_jobs_text(s)}


@router.get("/ops/jobs/{prefix}")
def describe_job(prefix: str, c: Caller = Depends(caller), s: Session = Depends(get_db)) -> dict[str, Any]:
    c.require_tool("describe_job")
    ops.require_role(s, c.context, "operator")
    return {"job": ops.describe_job(s, prefix)}


class ClarificationRequest(Strict):
    question: str


@router.post("/invoices/{ref}/clarifications", status_code=202)
def request_clarification(
    ref: str, body: ClarificationRequest, c: Caller = Depends(caller), s: Session = Depends(get_db)
) -> dict[str, Any]:
    """Ask the owner one focused question about a case in its shop room. Changes no case state."""
    c.require_tool("request_clarification")
    case = _case(s, c, ref)
    room = room_for_shop(s, case.shop_id, "shop_intake")
    if room is None:
        raise NotFound("No shop room is bound.")
    question = body.question.strip()[:500]
    post(
        s,
        room,
        action_id=f"clarify-agent:{c.context.context_id}:{case.case_ref}",
        body=f"Question about {case.case_ref}: {question}\nReply with a correction like `{case.case_ref} total=1180.00`.",
        case_ref=case.case_ref,
        correlation_id=c.context.request_id,
    )
    return {"status": "posted", "case_ref": case.case_ref}
