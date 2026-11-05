"""Job handlers. Shape (G-18): (1) load inputs; (2) external calls and CPU work outside any transaction;
(3) one fenced transaction: lease check, compare-and-set on state and generation, domain writes, case
event, outbox rows, job succeeded. A rerun finds the state already advanced and completes as a no-op.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import httpx
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from adapters import pdf
from adapters.excel import build_workbook
from adapters.llm import ProviderError, ProviderPermanentError, get_provider
from adapters.storage import LocalStorage
from adapters.switch_client import get_switch
from common.db import transaction
from common.errors import DomainError, LeaseLost, LimitExceeded
from common.logging import get_logger
from common.settings import get_settings
from domain import states as st
from domain.context import GrantInvalid, check_grant
from domain.models import (
    Artifact,
    ExecutionGrant,
    InboxEvent,
    Invoice,
    InvoiceRevision,
    Job,
    Receipt,
    RoomBinding,
    Shop,
    Snapshot,
    UsageRecord,
)
from domain.services import inbox as inbox_service
from domain.services import intake
from domain.services.base import audit, post, room_for_shop
from domain.services.cases import Exec
from domain.services.checks import evaluate, record_check_run
from domain.services.snapshots import DuplicateInManifest, build_snapshot
from domain.workflow import Event
from workers.cpu_pool import CpuTaskFailed, CpuTaskTimeout, run_cpu
from workers.queue import LeasedJob, fence_and_complete

log = get_logger("worker")


class Retryable(Exception):
    pass


class Permanent(Exception):
    pass


def hold_lease(s: Session, job: LeasedJob) -> None:
    """Lock our job row without completing it (for intermediate fenced writes)."""
    row = s.execute(
        text(
            "SELECT id FROM jobs WHERE id = :id AND lease_generation = :g AND lease_owner = :o "
            "AND status = 'leased' FOR UPDATE"
        ),
        {"id": job.id, "g": job.lease_generation, "o": job.lease_owner},
    ).first()
    if row is None:
        raise LeaseLost(f"job {job.id} lease generation {job.lease_generation} is no longer ours")


# ------------------------------------------------------------------------------------- inbox


def process_inbox_event(job: LeasedJob) -> None:
    with transaction() as s:
        fence_and_complete(s, job)
        event = s.execute(
            select(InboxEvent)
            .where(InboxEvent.id == uuid.UUID(job.payload["inbox_event_id"]))
            .with_for_update()
        ).scalar_one()
        if event.outcome != "pending":
            return
        inbox_service.mark(event, inbox_service.process(s, event))


# ------------------------------------------------------------------------------ fetch_and_store


def fetch_and_store(job: LeasedJob) -> None:
    settings = get_settings()
    receipt_id = uuid.UUID(job.payload["receipt_id"])
    with transaction() as s:
        receipt = s.get(Receipt, receipt_id)
        assert receipt is not None
        if receipt.status != "accepted":
            fence_and_complete(s, job)
            return
        check_grant(s, job.grant_id, "preserve_document")
        media_ref = receipt.media_ref
        shop_id = receipt.shop_id
    room_id = job.payload["room_id"]
    reason: str | None = None
    data = b""
    try:
        data, _, _ = get_switch().download_media(room_id, media_ref, settings.MAX_UPLOAD_MB * 1024 * 1024)
    except LimitExceeded as exc:
        reason = exc.message
    except (httpx.HTTPError, OSError) as exc:
        raise Retryable(f"download failed: {type(exc).__name__}") from exc
    mime = pdf.sniff_mime(data) if reason is None else None
    pages = 0
    if reason is None and mime is None:
        reason = "the file type is not a PDF, JPG or PNG"
    if reason is None and mime is not None:
        info = run_cpu(pdf.inspect_document, data, mime)
        if "error" in info:
            reason = info["error"]
        else:
            pages = int(info["pages"])
            if pages > settings.MAX_PAGES:
                reason = f"it has {pages} pages; the limit is {settings.MAX_PAGES}"
    storage_key = sha = ""
    if reason is None:
        sha, storage_key = LocalStorage().put(shop_id, data)
    with transaction() as s:
        fence_and_complete(s, job)
        receipt = s.execute(select(Receipt).where(Receipt.id == receipt_id).with_for_update()).scalar_one()
        if receipt.status != "accepted":
            return
        grant = check_grant(s, job.grant_id, "preserve_document")
        room = s.execute(select(RoomBinding).where(RoomBinding.switch_room_id == room_id)).scalar_one()
        if reason is not None:
            intake.reject_receipt(s, receipt, room, reason)
            return
        assert mime is not None
        intake.record_preserved(
            s,
            receipt=receipt,
            room=room,
            grant=grant,
            sha256=sha,
            mime=mime,
            size=len(data),
            pages=pages,
            storage_key=storage_key,
        )


# ----------------------------------------------------------------------------- extract_document


def extract_document(job: LeasedJob) -> None:
    case_id = uuid.UUID(job.payload["case_id"])
    generation = int(job.payload["generation"])
    with transaction() as s:
        hold_lease(s, job)
        case = s.execute(select(Invoice).where(Invoice.id == case_id).with_for_update()).scalar_one()
        if case.document_generation != generation:
            fence_and_complete(s, job)
            return
        check_grant(s, job.grant_id, "extract_generation", case_id=case.id, generation=generation)
        grant = s.get(ExecutionGrant, job.grant_id)
        Exec(s, case, job.correlation_id, grant=grant).run(Event("extraction_leased"))
        document = intake.current_document(s, case)
        assert document is not None
        storage_key, mime, sha = document.storage_key, document.mime, document.sha256
        shop_key = f"shop-{case.shop_id}"
    data = LocalStorage().get(storage_key)
    try:
        prepared = run_cpu(pdf.prepare_for_extraction, data, mime)
    except (CpuTaskTimeout, CpuTaskFailed) as exc:
        raise Retryable(str(exc)) from exc
    try:
        outcome = get_provider().extract(prepared, sha, shop_key)
    except ProviderError as exc:
        raise Retryable(str(exc)) from exc
    except ProviderPermanentError as exc:
        raise Permanent(str(exc)) from exc
    with transaction() as s:
        fence_and_complete(s, job)
        case = s.execute(select(Invoice).where(Invoice.id == case_id).with_for_update()).scalar_one()
        usage = UsageRecord(
            practice_id=case.practice_id,
            shop_id=case.shop_id,
            stage="extraction",
            provider=outcome.provider,
            model=outcome.model,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            duration_ms=outcome.duration_ms,
        )
        if case.document_generation != generation or case.status != st.PROCESSING:
            usage.outcome = "discarded_stale_generation"
            s.add(usage)
            return
        grant = check_grant(s, job.grant_id, "extract_generation", case_id=case.id, generation=generation)
        s.add(usage)
        document = intake.current_document(s, case)
        assert document is not None
        intake.persist_extraction(
            s,
            case=case,
            document=document,
            result=outcome.result,
            grant=grant,
            correlation_id=job.correlation_id,
        )


# ---------------------------------------------------------------------------------- run_checks


def run_checks(job: LeasedJob) -> None:
    case_id = uuid.UUID(job.payload["case_id"])
    revision_id = uuid.UUID(job.payload["revision_id"])
    with transaction() as s:
        fence_and_complete(s, job)
        case = s.execute(select(Invoice).where(Invoice.id == case_id).with_for_update()).scalar_one()
        if case.current_revision_id != revision_id or case.status != st.CHECKING:
            return
        grant = check_grant(s, job.grant_id, "run_checks", case_id=case.id)
        rev = s.get(InvoiceRevision, revision_id)
        assert rev is not None
        results, inputs_hash, results_hash = evaluate(s, case, rev)
        _, blocking, ca_attention = record_check_run(s, case, rev, results, inputs_hash, results_hash)
        Exec(s, case, job.correlation_id, grant=grant).run(
            Event("checks_completed", blocking=blocking, ca_attention=ca_attention)
        )


# ------------------------------------------------------------------------------ snapshot/export


def build_snapshot_job(job: LeasedJob) -> None:
    with transaction() as s:
        fence_and_complete(s, job)
        check_grant(s, job.grant_id, "build_snapshot")
        shop = s.get(Shop, uuid.UUID(job.payload["shop_id"]))
        assert shop is not None
        try:
            with s.begin_nested():
                build_snapshot(s, shop, job.payload["period"], job.correlation_id)
        except DuplicateInManifest as exc:
            room = room_for_shop(s, shop.id, "ca_review")
            if room is not None:
                post(
                    s,
                    room,
                    action_id=f"snapshot_refused:{job.id}",
                    body=exc.message,
                    correlation_id=job.correlation_id,
                )


def build_export(job: LeasedJob) -> None:
    snapshot_id = uuid.UUID(job.payload["snapshot_id"])
    with transaction() as s:
        snap = s.get(Snapshot, snapshot_id)
        assert snap is not None
        check_grant(s, job.grant_id, "build_export", snapshot_id=snap.id)
        if snap.status not in ("approved", "exported"):
            raise Permanent(f"snapshot is {snap.status}")
        manifest_bytes = snap.manifest_bytes
        shop_id, ref, period = snap.shop_id, snap.public_ref, snap.period
        shop = s.get(Shop, shop_id)
        assert shop is not None
        code = shop.code
    try:
        xlsx = run_cpu(build_workbook, manifest_bytes)
    except (CpuTaskTimeout, CpuTaskFailed) as exc:
        raise Retryable(str(exc)) from exc
    storage = LocalStorage()
    files = {
        "json": (f"assure-flow_{code}_{period}_{ref}.json", manifest_bytes.encode("utf-8")),
        "xlsx": (f"assure-flow_{code}_{period}_{ref}.xlsx", xlsx),
    }
    stored = {kind: storage.put_artifact(shop_id, data) for kind, (_, data) in files.items()}
    with transaction() as s:
        fence_and_complete(s, job)
        snap = s.execute(select(Snapshot).where(Snapshot.id == snapshot_id).with_for_update()).scalar_one()
        for kind, (filename, _) in files.items():
            sha, key = stored[kind]
            s.execute(
                insert(Artifact)
                .values(
                    id=uuid.uuid4(),
                    practice_id=snap.practice_id,
                    shop_id=snap.shop_id,
                    snapshot_id=snap.id,
                    kind=kind,
                    filename=filename,
                    sha256=sha,
                    storage_key=key,
                )
                .on_conflict_do_nothing(index_elements=["snapshot_id", "kind"])
            )
        if snap.status == "approved":
            snap.status = "exported"
        s.flush()
        artifact_ids = [
            str(a.id)
            for a in s.execute(
                select(Artifact).where(Artifact.snapshot_id == snap.id).order_by(Artifact.kind)
            ).scalars()
        ]
        room = room_for_shop(s, snap.shop_id, "ca_review")
        if room is not None:
            label = "PARTIAL " if snap.partial else ""
            post(
                s,
                room,
                action_id=f"export:{snap.id}",
                body=f"{label}{ref} export (hash {snap.content_hash[:12]}): Excel + JSON attached.",
                kind="files",
                attachments=artifact_ids,
                correlation_id=job.correlation_id,
            )


HANDLERS: dict[str, Callable[[LeasedJob], None]] = {
    "process_inbox_event": process_inbox_event,
    "fetch_and_store": fetch_and_store,
    "extract_document": extract_document,
    "run_checks": run_checks,
    "build_snapshot": build_snapshot_job,
    "build_export": build_export,
}


def registered_types() -> set[str]:
    return set(HANDLERS)


def on_dead(s: Session, job: Job) -> None:
    """Visible failure when retries are exhausted: tell the right room, never fail silently."""
    payload: dict[str, Any] = job.payload
    if job.type == "extract_document":
        case = s.get(Invoice, uuid.UUID(payload["case_id"]))
        if (
            case is not None
            and case.document_generation == int(payload["generation"])
            and case.status
            in (
                st.RECEIVED,
                st.PROCESSING,
            )
        ):
            Exec(s, case, job.correlation_id).run(Event("extraction_exhausted"))
    elif job.type == "fetch_and_store":
        receipt = s.get(Receipt, uuid.UUID(payload["receipt_id"]))
        room = s.execute(
            select(RoomBinding).where(RoomBinding.switch_room_id == payload["room_id"])
        ).scalar_one_or_none()
        if receipt is not None and receipt.status == "accepted" and room is not None:
            intake.reject_receipt(s, receipt, room, "the file could not be downloaded")
    audit(
        s,
        action="job.dead",
        entity="job",
        entity_id=str(job.id),
        outcome="failed",
        actor="worker",
        request_id=job.correlation_id,
        after={"type": job.type, "error": (job.last_error or "")[:200]},
    )
    log.error("job.dead", job_id=str(job.id), type=job.type)


def classify(exc: BaseException) -> tuple[bool, bool]:
    """(retryable, cancel) for a handler exception."""
    if isinstance(exc, GrantInvalid):
        return False, True
    if isinstance(exc, Permanent | DomainError):
        return False, False
    return True, False
