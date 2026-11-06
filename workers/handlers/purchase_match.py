"""U2 job handlers: run_purchase_match (fast lane) and build_purchase_export (slow lane).

Same shape as the v1.4 handlers: the match is read and committed in one fenced transaction; the export renders
Excel in the CPU subprocess pool outside any transaction, then commits artifacts and the room message.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from adapters.excel import build_purchase_workbook
from adapters.storage import LocalStorage
from common.db import transaction
from domain.context import check_grant
from domain.models import Artifact, PaymentReadiness, PurchaseLink, PurchaseOrder, Shop
from domain.services import purchases, readiness
from domain.services.base import post, room_for_shop
from workers.cpu_pool import CpuTaskFailed, CpuTaskTimeout, run_cpu
from workers.queue import LeasedJob, fence_and_complete


class Retryable(Exception):
    pass


def run_purchase_match(job: LeasedJob) -> None:
    with transaction() as s:
        fence_and_complete(s, job)
        link = s.execute(
            select(PurchaseLink).where(PurchaseLink.id == uuid.UUID(job.payload["link_id"])).with_for_update()
        ).scalar_one()
        grant = check_grant(s, job.grant_id, "run_purchase_match", case_id=link.case_id)
        if link.status != "active":
            return
        purchases.run_match(s, link, job.correlation_id, grant)


def build_purchase_export(job: LeasedJob) -> None:
    readiness_id = uuid.UUID(job.payload["readiness_id"])
    with transaction() as s:
        record = s.get(PaymentReadiness, readiness_id)
        assert record is not None
        link = s.get(PurchaseLink, record.link_id)
        assert link is not None
        check_grant(s, job.grant_id, "build_purchase_export", case_id=link.case_id)
        if record.authorized_at is None:
            return
        data = readiness.pack_json(s, record)
        shop = s.get(Shop, record.shop_id)
        order = s.get(PurchaseOrder, link.order_id)
        assert shop is not None and order is not None
        stem = f"assure-flow_{shop.code}_{order.order_ref}_{record.public_ref}"
        shop_id = record.shop_id
    try:
        xlsx = run_cpu(build_purchase_workbook, data)
    except (CpuTaskTimeout, CpuTaskFailed) as exc:
        raise Retryable(str(exc)) from exc
    storage = LocalStorage()
    files = {"json": (f"{stem}.json", data.encode("utf-8")), "xlsx": (f"{stem}.xlsx", xlsx)}
    stored = {kind: storage.put_artifact(shop_id, blob) for kind, (_, blob) in files.items()}
    with transaction() as s:
        fence_and_complete(s, job)
        record = s.execute(select(PaymentReadiness).where(PaymentReadiness.id == readiness_id)).scalar_one()
        for kind, (filename, _) in files.items():
            sha, key = stored[kind]
            s.execute(
                insert(Artifact)
                .values(
                    id=uuid.uuid4(),
                    practice_id=record.practice_id,
                    shop_id=record.shop_id,
                    snapshot_id=None,
                    readiness_id=record.id,
                    kind=kind,
                    filename=filename,
                    sha256=sha,
                    storage_key=key,
                )
                .on_conflict_do_nothing(index_elements=["readiness_id", "kind"])
            )
        s.flush()
        artifact_ids = [
            str(a.id)
            for a in s.execute(
                select(Artifact).where(Artifact.readiness_id == record.id).order_by(Artifact.kind)
            ).scalars()
        ]
        for purpose in ("shop_intake", "ca_review"):
            room = room_for_shop(s, record.shop_id, purpose)
            if room is not None:
                post(
                    s,
                    room,
                    action_id=f"purchase_export:{record.id}",
                    body=f"{record.public_ref} purchase pack (hash {record.content_hash[:12]}): Excel + JSON attached. "
                    "Ready for payment; no payment has been made.",
                    kind="files",
                    attachments=artifact_ids,
                    correlation_id=job.correlation_id,
                )
