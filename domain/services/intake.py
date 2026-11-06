"""Steps 1-4: receive, preserve, extract, confirm, plus typed corrections and replacements."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from common.errors import Forbidden, NotFound, StaleRevision, ValidationFailed
from common.ids import next_ref
from domain import states as st
from domain.context import issue_grant
from domain.extraction import (
    CORRECTABLE,
    HEADER_FIELDS,
    LINE_FIELDS,
    MATERIAL_FIELDS,
    MONEY_FIELDS,
    ExtractionV1,
)
from domain.models import (
    Document,
    DuplicateLink,
    ExecutionGrant,
    FieldEvidence,
    InboxEvent,
    Invoice,
    InvoiceRevision,
    LineItem,
    Receipt,
    RequestContext,
    RoomBinding,
    Shop,
    utcnow,
)
from domain.scope import is_owner_of
from domain.services import messages as msg
from domain.services.base import audit, case_event, post, room_for_shop
from domain.services.cases import (
    Exec,
    current_revision,
    new_case,
    release_duplicate_key,
    revoke_older_generations,
)
from domain.workflow import Command, Event
from workers.queue import enqueue

LINE_DECIMALS = {
    "qty",
    "unit_price",
    "discount",
    "taxable_value",
    "cgst_rate",
    "sgst_rate",
    "igst_rate",
    "combined_rate",
    "cgst_amount",
    "sgst_amount",
    "igst_amount",
}


def to_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    cleaned = value.replace(",", "").replace("₹", "").replace("INR", "").replace("Rs.", "").strip()
    if cleaned in ("", "-"):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


# ------------------------------------------------------------------------------- step 1 receive


def accept_upload(
    s: Session,
    *,
    ctx: RequestContext,
    event: InboxEvent,
    room: RoomBinding,
    shop: Shop,
    attachment: dict[str, Any],
    index: int,
    replaces: Invoice | None,
) -> Receipt:
    """Receipt + preserve_document grant + fetch_and_store job + 'received' outbox row, one transaction."""
    if not is_owner_of(s, ctx.verified_user_id, shop.id):
        raise Forbidden("Only this shop's owner can send bills here.")
    receipt = Receipt(
        public_ref=next_ref(s, shop.practice_id, "R"),
        practice_id=shop.practice_id,
        shop_id=shop.id,
        inbox_event_id=event.id,
        attachment_index=index,
        filename=str(attachment.get("filename") or "attachment")[:255],
        declared_mime=attachment.get("mimetype"),
        media_ref=str(attachment.get("mxc") or ""),
        replaces_invoice_id=replaces.id if replaces else None,
        correlation_id=event.correlation_id,
    )
    s.add(receipt)
    s.flush()
    grant = issue_grant(
        s,
        operation="preserve_document",
        practice_id=shop.practice_id,
        shop_id=shop.id,
        receipt_id=receipt.id,
        case_id=replaces.id if replaces else None,
        context=ctx,
    )
    enqueue(
        s,
        type="fetch_and_store",
        lane="io",
        payload={"receipt_id": str(receipt.id), "room_id": room.switch_room_id},
        dedupe_key=f"fetch:{receipt.id}",
        correlation_id=event.correlation_id,
        grant_id=grant.grant_id,
    )
    post(
        s,
        room,
        action_id=f"received:{receipt.id}",
        body=msg.received(receipt.public_ref, receipt.filename),
        correlation_id=event.correlation_id,
        case_ref=replaces.case_ref if replaces else None,
    )
    return receipt


# ------------------------------------------------------------------------------ step 2 preserve


def reject_receipt(s: Session, receipt: Receipt, room: RoomBinding, reason: str) -> None:
    receipt.status = "rejected_file"
    receipt.reject_reason = reason[:255]
    post(
        s,
        room,
        action_id=f"rejected:{receipt.id}",
        body=msg.rejected(receipt.public_ref, reason),
        correlation_id=receipt.correlation_id,
    )
    audit(
        s,
        action="receipt.rejected",
        entity="receipt",
        entity_id=receipt.public_ref,
        outcome="rejected",
        actor="worker",
        request_id=receipt.correlation_id,
        practice_id=receipt.practice_id,
        shop_id=receipt.shop_id,
    )


def record_preserved(
    s: Session,
    *,
    receipt: Receipt,
    room: RoomBinding,
    grant: ExecutionGrant,
    sha256: str,
    mime: str,
    size: int,
    pages: int,
    storage_key: str,
) -> Invoice | None:
    """File is already on disk. Create the document and the stable case (or attach a replacement)."""
    shop = s.get(Shop, receipt.shop_id)
    assert shop is not None
    if receipt.replaces_invoice_id is None:
        existing = s.execute(
            select(Document).where(Document.shop_id == shop.id, Document.sha256 == sha256).limit(1)
        ).scalar_one_or_none()
        if existing is not None and existing.invoice_id is not None:
            original = s.get(Invoice, existing.invoice_id)
            assert original is not None
            receipt.status = "duplicate"
            s.add(
                DuplicateLink(
                    practice_id=shop.practice_id,
                    shop_id=shop.id,
                    kind="exact_file",
                    invoice_a=original.id,
                    receipt_b=receipt.id,
                )
            )
            post(
                s,
                room,
                action_id=f"duplicate_file:{receipt.id}",
                body=msg.duplicate_file(receipt.public_ref, original.case_ref),
                case_ref=original.case_ref,
                correlation_id=receipt.correlation_id,
            )
            return None
        case = new_case(s, shop, receipt.correlation_id)
        event = Event("document_preserved")
    else:
        replaced = s.get(Invoice, receipt.replaces_invoice_id)
        if replaced is None:
            raise NotFound("case to replace no longer exists")
        case = replaced
        case.document_generation += 1
        revoke_older_generations(s, case)
        event = Event("replacement_preserved")
    receipt.status = "preserved"
    s.add(
        Document(
            practice_id=shop.practice_id,
            shop_id=shop.id,
            receipt_id=receipt.id,
            invoice_id=case.id,
            document_generation=case.document_generation,
            sha256=sha256,
            mime=mime,
            size_bytes=size,
            page_count=pages,
            storage_key=storage_key,
        )
    )
    s.flush()
    executor = Exec(s, case, receipt.correlation_id, grant=grant)
    executor.notes = {"receipt_ref": receipt.public_ref, "pages": str(pages)}
    executor.run(event)
    return case


# ------------------------------------------------------------------------------- step 3 extract


def current_document(s: Session, case: Invoice) -> Document | None:
    return s.execute(
        select(Document).where(
            Document.invoice_id == case.id, Document.document_generation == case.document_generation
        )
    ).scalar_one_or_none()


def persist_extraction(
    s: Session,
    *,
    case: Invoice,
    document: Document,
    result: ExtractionV1,
    grant: ExecutionGrant,
    correlation_id: str,
) -> InvoiceRevision | None:
    """Draft revision, line items and per-field evidence; case -> needs_confirmation.

    A multi-page file that holds several invoices is split instead (returns None)."""
    if result.multiple_invoices and document.page_count > 1 and document.page_from is None:
        split_document(s, case=case, document=document, grant=grant, correlation_id=correlation_id)
        return None
    previous = current_revision(s, case)
    revision_no = (
        s.execute(
            select(func.coalesce(func.max(InvoiceRevision.revision_no), 0)).where(
                InvoiceRevision.invoice_id == case.id
            )
        ).scalar_one()
        + 1
    )
    header: dict[str, Any] = {}
    for name in HEADER_FIELDS:
        raw = getattr(result, name).value
        header[name] = to_decimal(raw) if name in MONEY_FIELDS else (raw.strip() if raw else None)
    if header.get("supplier_gstin"):
        header["supplier_gstin"] = str(header["supplier_gstin"]).replace(" ", "").upper()
    if header.get("recipient_gstin"):
        header["recipient_gstin"] = str(header["recipient_gstin"]).replace(" ", "").upper()
    if header.get("place_of_supply"):
        header["place_of_supply"] = str(header["place_of_supply"])[:2].zfill(2)
    if header.get("currency"):
        header["currency"] = str(header["currency"])[:3].upper()
    rev = InvoiceRevision(
        practice_id=case.practice_id,
        shop_id=case.shop_id,
        invoice_id=case.id,
        revision_no=revision_no,
        status="draft",
        parent_revision_id=previous.id if previous else None,
        document_id=document.id,
        document_generation=document.document_generation,
        source="replacement" if document.document_generation > 1 else "extraction",
        tax_printed_per_line=result.tax_printed_per_line,
        multiple_invoices=result.multiple_invoices,
        **header,
    )
    s.add(rev)
    s.flush()
    for name in HEADER_FIELDS:
        fv = getattr(result, name)
        s.add(
            FieldEvidence(
                practice_id=case.practice_id,
                shop_id=case.shop_id,
                revision_id=rev.id,
                field_path=name,
                value_text=fv.value,
                page_no=fv.page,
                excerpt=(fv.excerpt or "")[:500] or None,
                confidence=Decimal(str(round(fv.confidence, 3))),
                source="vision" if document.mime != "application/pdf" else "text",
            )
        )
    for line in result.lines:
        values: dict[str, Any] = {}
        for name in LINE_FIELDS:
            raw = getattr(line, name).value
            values[name] = to_decimal(raw) if name in LINE_DECIMALS else (raw.strip() if raw else None)
        s.add(
            LineItem(
                practice_id=case.practice_id,
                shop_id=case.shop_id,
                revision_id=rev.id,
                line_no=line.line_no,
                **values,
            )
        )
    if previous is not None and previous.status != "superseded":
        previous.status = "superseded"
    case.current_revision_id = rev.id
    Exec(s, case, correlation_id, grant=grant).run(Event("extraction_persisted"))
    return rev


def split_document(
    s: Session, *, case: Invoice, document: Document, grant: ExecutionGrant, correlation_id: str
) -> list[Invoice]:
    """One invoice per page: this case keeps page 1 (a new document generation, re-read); every other page
    becomes its own case linked by split_from_invoice_id. Originals are untouched; documents are new rows."""
    shop = s.get(Shop, case.shop_id)
    assert shop is not None
    receipt = s.get(Receipt, document.receipt_id)
    assert receipt is not None

    def page_doc(target: Invoice, page: int) -> None:
        s.add(
            Document(
                practice_id=shop.practice_id,
                shop_id=shop.id,
                receipt_id=document.receipt_id,
                invoice_id=target.id,
                document_generation=target.document_generation,
                sha256=document.sha256,
                mime=document.mime,
                size_bytes=document.size_bytes,
                page_count=1,
                storage_key=document.storage_key,
                page_from=page,
                page_to=page,
            )
        )
        s.flush()

    case.document_generation += 1
    revoke_older_generations(s, case)
    page_doc(case, 1)
    case_event(s, case, "document_split", correlation_id, {"pages": document.page_count, "keeps_page": 1})
    Exec(s, case, correlation_id, grant=grant)._enqueue_extraction(Command("enqueue_extraction"))
    children: list[Invoice] = []
    for page in range(2, document.page_count + 1):
        child = new_case(s, shop, correlation_id)
        child.split_from_invoice_id = case.id
        page_doc(child, page)
        executor = Exec(s, child, correlation_id, grant=grant)
        executor.notes = {"receipt_ref": receipt.public_ref, "pages": "1"}
        executor.run(Event("document_preserved"))
        children.append(child)
    room = room_for_shop(s, case.shop_id, "shop_intake")
    if room is not None:
        parts = [f"{case.case_ref} (page 1)"] + [
            f"{c.case_ref} (page {i})" for i, c in enumerate(children, 2)
        ]
        post(
            s,
            room,
            action_id=f"split:{case.id}:{case.document_generation}",
            body=f"{receipt.public_ref} holds {document.page_count} invoices, so it was split: {', '.join(parts)}. "
            "Each one gets its own summary to confirm.",
            case_ref=case.case_ref,
            correlation_id=correlation_id,
        )
    return children


# ------------------------------------------------------------------------------- step 4 confirm


def _require_owner(s: Session, ctx: RequestContext, case: Invoice) -> None:
    if not is_owner_of(s, ctx.verified_user_id, case.shop_id):
        raise Forbidden("Only this shop's owner can confirm or correct its bills.")


def _check_revision(case: Invoice, rev: InvoiceRevision | None, expected_no: int | None) -> InvoiceRevision:
    if rev is None:
        raise ValidationFailed(f"{case.case_ref} has not been read yet; wait for the summary.")
    if expected_no is not None and expected_no != rev.revision_no:
        raise StaleRevision(
            f"{case.case_ref} is now at r{rev.revision_no}, not r{expected_no}.",
            {"current_revision": rev.revision_no, "expected_revision": expected_no},
        )
    return rev


def confirm(
    s: Session, ctx: RequestContext, case: Invoice, expected_no: int | None, hold: bool = False
) -> InvoiceRevision:
    """Every material field needs a value or an explicit hold (`ok INV-0001 hold`)."""
    _require_owner(s, ctx, case)
    rev = _check_revision(case, current_revision(s, case), expected_no)
    missing = [f for f in MATERIAL_FIELDS if getattr(rev, f) in (None, "")]
    if missing and not hold:
        raise ValidationFailed(
            f"{case.case_ref} still has no value for: {', '.join(msg.LABELS.get(f, f) for f in missing)}. "
            f"Type it, e.g. `{case.case_ref} {missing[0]}=...`, or reply `ok {case.case_ref} hold` to send it "
            "for review with that field held."
        )
    if rev.multiple_invoices:
        raise ValidationFailed("This file holds more than one invoice; please send one invoice per file.")
    executor = Exec(s, case, ctx.request_id, context=ctx)
    st.target(case.status, "confirm")
    rev.status = "confirmed"
    rev.confirmed_by = ctx.verified_user_id
    rev.confirmed_at = utcnow()
    executor.run(Event("owner_confirmed"))
    from domain.services import purchases

    purchases.propose_link(s, case, ctx.request_id)
    return rev


def correct(
    s: Session, ctx: RequestContext, case: Invoice, expected_no: int | None, changes: dict[str, str]
) -> InvoiceRevision:
    """Typed correction: a new draft revision (source=human), no re-extraction."""
    _require_owner(s, ctx, case)
    base = _check_revision(case, current_revision(s, case), expected_no)
    if not changes:
        raise ValidationFailed("No field=value pairs found.")
    updates: dict[str, Any] = {}
    for key, raw in changes.items():
        field = CORRECTABLE.get(key.lower())
        if field is None:
            raise ValidationFailed(
                f"Unknown field '{key}'. Use one of: {', '.join(sorted(set(CORRECTABLE)))}."
            )
        if field in MONEY_FIELDS:
            value = to_decimal(raw)
            if value is None:
                raise ValidationFailed(f"'{raw}' is not an amount.")
            updates[field] = value.quantize(Decimal("0.01"))
        elif field == "invoice_date":
            try:
                updates[field] = date.fromisoformat(raw).isoformat()
            except ValueError as exc:
                raise ValidationFailed("Dates must look like 2026-11-03.") from exc
        elif field in ("supplier_gstin", "recipient_gstin"):
            updates[field] = raw.replace(" ", "").upper()
        elif field == "place_of_supply":
            updates[field] = raw.strip()[:2].zfill(2)
        else:
            updates[field] = raw.strip()
    revision_no = (
        s.execute(
            select(func.max(InvoiceRevision.revision_no)).where(InvoiceRevision.invoice_id == case.id)
        ).scalar_one()
        + 1
    )
    copy_fields = {c: getattr(base, c) for c in (*HEADER_FIELDS, "tax_printed_per_line")}
    copy_fields.update(updates)
    rev = InvoiceRevision(
        practice_id=case.practice_id,
        shop_id=case.shop_id,
        invoice_id=case.id,
        revision_no=revision_no,
        status="draft",
        parent_revision_id=base.id,
        document_id=base.document_id,
        document_generation=base.document_generation,
        source="human",
        multiple_invoices=False,
        **copy_fields,
    )
    s.add(rev)
    s.flush()
    for line in s.execute(select(LineItem).where(LineItem.revision_id == base.id)).scalars():
        s.add(
            LineItem(
                practice_id=line.practice_id,
                shop_id=line.shop_id,
                revision_id=rev.id,
                line_no=line.line_no,
                **{name: getattr(line, name) for name in LINE_FIELDS},
            )
        )
    for ev in s.execute(select(FieldEvidence).where(FieldEvidence.revision_id == base.id)).scalars():
        if ev.field_path in updates:
            continue
        s.add(
            FieldEvidence(
                practice_id=ev.practice_id,
                shop_id=ev.shop_id,
                revision_id=rev.id,
                field_path=ev.field_path,
                value_text=ev.value_text,
                page_no=ev.page_no,
                excerpt=ev.excerpt,
                confidence=ev.confidence,
                source=ev.source,
                actor_id=ev.actor_id,
            )
        )
    for field, value in updates.items():
        s.add(
            FieldEvidence(
                practice_id=case.practice_id,
                shop_id=case.shop_id,
                revision_id=rev.id,
                field_path=field,
                value_text=str(value),
                source="human",
                actor_id=ctx.verified_user_id,
                confidence=Decimal("1"),
            )
        )
    base.status = "superseded"
    base.superseded_at = utcnow()
    release_duplicate_key(s, case)
    case.current_revision_id = rev.id
    case_event(
        s, case, "typed_correction", ctx.request_id, {"fields": sorted(updates)}, context_id=ctx.context_id
    )
    Exec(s, case, ctx.request_id, context=ctx).run(Event("typed_correction"))
    return rev
