"""Phase 6: GSTR-2B import (P6-01/02) and two-way reconciliation (P6-03..05) driven from the CA room."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from common.errors import Forbidden
from common.ids import next_ref
from common.settings import get_settings
from domain.context import issue_grant, require_live_context
from domain.models import (
    ExecutionGrant,
    InboxEvent,
    Invoice,
    InvoiceRevision,
    ReconciliationResult,
    ReconciliationRun,
    RequestContext,
    RoomBinding,
    Shop,
    Statement,
    StatementLine,
)
from domain.scope import is_assigned_ca
from domain.services import messages as msg
from domain.services.base import post, room_for_shop
from domain.services.cases import financial_year, normalize_number
from rules import reconcile as rc
from rules.types import Tolerances
from workers.queue import enqueue

DOC_TYPES = {"r": "tax_invoice", "regular": "tax_invoice", "": "tax_invoice"}
WORDING = (
    "A match supports review; it is not an ITC eligibility decision. "
    "Tax amounts shown are associated with the difference, not money lost."
)


def doc_type(invoice_type: Any) -> str:
    return DOC_TYPES.get(str(invoice_type or "").strip().lower(), "other")


def match_key(gstin: str, document_type: str, invoice_date: str, number: str) -> str:
    return "|".join([gstin.upper(), document_type, financial_year(invoice_date), normalize_number(number)])


def request_import(
    s: Session, ctx: RequestContext, event: InboxEvent, room: RoomBinding, shop: Shop, period: str
) -> None:
    require_live_context(ctx)
    if not is_assigned_ca(s, ctx.verified_user_id, shop.id):
        raise Forbidden("Only the assigned CA can import a GSTR-2B statement.")
    attachment = event.attachments[0]
    grant = issue_grant(
        s, operation="import_statement", practice_id=shop.practice_id, shop_id=shop.id, context=ctx
    )
    enqueue(
        s,
        type="import_statement",
        lane="io",
        payload={
            "shop_id": str(shop.id),
            "period": period,
            "room_id": room.switch_room_id,
            "mxc": str(attachment.get("mxc") or ""),
            "filename": str(attachment.get("filename") or "gstr2b"),
            "user_id": str(ctx.verified_user_id),
        },
        dedupe_key=f"import:{event.id}",
        correlation_id=event.correlation_id,
        grant_id=grant.grant_id,
    )
    post(
        s,
        room,
        action_id=f"import_ack:{event.id}",
        body=f"Received the GSTR-2B file for {shop.name} {period}. Importing it now.",
        correlation_id=event.correlation_id,
    )


def record_statement(
    s: Session,
    *,
    shop: Shop,
    period: str,
    parsed: dict[str, Any],
    sha256: str,
    storage_key: str,
    filename: str,
    user_id: uuid.UUID,
    grant: ExecutionGrant,
    correlation_id: str,
) -> str:
    """Validate and store immutably. Returns the reply for the CA room."""
    if parsed.get("error"):
        return f"GSTR-2B file not imported: {parsed['error']}."
    if parsed["gstin"] != shop.gstin:
        return (
            f"GSTR-2B file not imported: it is for GSTIN {parsed['gstin']}, not {shop.name} ({shop.gstin})."
        )
    if parsed["period"] != period:
        return f"GSTR-2B file not imported: it covers {parsed['period']}, not {period}."
    existing = s.execute(
        select(Statement).where(
            Statement.shop_id == shop.id,
            Statement.kind == "gstr2b",
            Statement.period == period,
            Statement.sha256 == sha256,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return f"This file is already imported as {existing.public_ref}; nothing changed."
    statement = Statement(
        practice_id=shop.practice_id,
        shop_id=shop.id,
        public_ref=next_ref(s, shop.practice_id, "ST"),
        kind="gstr2b",
        period=period,
        parser_version=parsed["parser"],
        sha256=sha256,
        storage_key=storage_key,
        filename=filename[:255],
        line_count=len(parsed["lines"]),
        skipped=parsed.get("skipped") or {},
        imported_by=user_id,
    )
    s.add(statement)
    s.flush()
    for i, line in enumerate(parsed["lines"], 1):
        dtype = doc_type(line["invoice_type"])
        s.add(
            StatementLine(
                practice_id=shop.practice_id,
                shop_id=shop.id,
                statement_id=statement.id,
                line_no=i,
                supplier_gstin=line["supplier_gstin"],
                supplier_name=(str(line["supplier_name"])[:255] if line.get("supplier_name") else None),
                document_type=dtype,
                invoice_number=line["invoice_number"][:64],
                number_norm=normalize_number(line["invoice_number"])[:64],
                invoice_date=line["invoice_date"],
                financial_year=financial_year(line["invoice_date"]),
                invoice_value=Decimal(line["invoice_value"]),
                taxable=Decimal(line["taxable"]),
                igst=Decimal(line["igst"]),
                cgst=Decimal(line["cgst"]),
                sgst=Decimal(line["sgst"]),
                cess=Decimal(line["cess"]),
                itc_available=(str(line["itc_available"])[:8] if line.get("itc_available") else None),
            )
        )
    s.flush()
    child = issue_grant(s, operation="reconcile", practice_id=shop.practice_id, shop_id=shop.id, parent=grant)
    enqueue(
        s,
        type="reconcile",
        lane="fast",
        payload={"statement_id": str(statement.id)},
        dedupe_key=f"reconcile:{statement.id}:1",
        correlation_id=correlation_id,
        grant_id=child.grant_id,
    )
    skipped = statement.skipped
    extra = f" Skipped sections (not in the supported profile): {skipped}." if skipped else ""
    return f"Imported {statement.public_ref}: {statement.line_count} B2B invoices for {period}.{extra} Reconciling now."


def purchases_for(s: Session, shop_id: uuid.UUID, period: str) -> list[rc.Side]:
    rows = s.execute(
        select(Invoice, InvoiceRevision)
        .join(InvoiceRevision, InvoiceRevision.id == Invoice.current_revision_id)
        .where(
            Invoice.shop_id == shop_id,
            Invoice.period == period,
            Invoice.status != "excluded",
            InvoiceRevision.status == "confirmed",
        )
    ).all()
    sides = []
    for case, rev in rows:
        if not (rev.supplier_gstin and rev.invoice_number and rev.invoice_date):
            continue
        zero = Decimal("0.00")
        sides.append(
            rc.Side(
                ref=case.case_ref,
                id=str(rev.id),
                key=match_key(
                    rev.supplier_gstin,
                    rev.document_type or "tax_invoice",
                    rev.invoice_date,
                    rev.invoice_number,
                ),
                amounts={
                    "taxable": rev.taxable_total or zero,
                    "igst": rev.igst_total or zero,
                    "cgst": rev.cgst_total or zero,
                    "sgst": rev.sgst_total or zero,
                    "cess": rev.cess_total or zero,
                },
                total=rev.invoice_total or zero,
            )
        )
    return sides


def reconcile(s: Session, statement: Statement, correlation_id: str) -> ReconciliationRun:
    settings = get_settings()
    lines = list(
        s.execute(
            select(StatementLine)
            .where(StatementLine.statement_id == statement.id)
            .order_by(StatementLine.line_no)
        ).scalars()
    )
    line_sides = [
        rc.Side(
            ref=f"L{ln.line_no}",
            id=str(ln.id),
            key=match_key(ln.supplier_gstin, ln.document_type, ln.invoice_date, ln.invoice_number),
            amounts={
                "taxable": ln.taxable,
                "igst": ln.igst,
                "cgst": ln.cgst,
                "sgst": ln.sgst,
                "cess": ln.cess,
            },
            total=ln.invoice_value,
        )
        for ln in lines
    ]
    tol = Tolerances(settings.TAX_LINE_TOLERANCE_INR, settings.AMOUNT_TOLERANCE_INR)
    results = rc.match(purchases_for(s, statement.shop_id, statement.period), line_sides, tol)
    run_seq = (
        s.execute(
            select(func.coalesce(func.max(ReconciliationRun.run_seq), 0)).where(
                ReconciliationRun.statement_id == statement.id
            )
        ).scalar_one()
        + 1
    )
    counts: dict[str, int] = {}
    for r in results:
        counts[r.class_] = counts.get(r.class_, 0) + 1
    run = ReconciliationRun(
        practice_id=statement.practice_id,
        shop_id=statement.shop_id,
        public_ref=next_ref(s, statement.practice_id, "RC"),
        statement_id=statement.id,
        period=statement.period,
        run_seq=run_seq,
        matcher_version=rc.MATCHER_VERSION,
        summary={"counts": counts},
        results_hash=rc.results_hash(results),
    )
    s.add(run)
    s.flush()
    for r in results:
        s.add(
            ReconciliationResult(
                practice_id=statement.practice_id,
                shop_id=statement.shop_id,
                run_id=run.id,
                class_=r.class_,
                statement_line_id=uuid.UUID(r.line.id) if r.line else None,
                revision_id=uuid.UUID(r.purchase.id) if r.purchase else None,
                case_ref=r.purchase.ref if r.purchase else None,
                key=r.key[:160],
                differences=r.differences,
            )
        )
    s.flush()
    room = room_for_shop(s, statement.shop_id, "ca_review")
    shop = s.get(Shop, statement.shop_id)
    if room is not None and shop is not None:
        post(
            s,
            room,
            action_id=f"recon:{run.id}",
            body=summary_text(shop, run, results, lines),
            correlation_id=correlation_id,
        )
    return run


def summary_text(
    shop: Shop, run: ReconciliationRun, results: list[rc.Result], lines: list[StatementLine]
) -> str:
    by_line = {f"L{ln.line_no}": ln for ln in lines}
    counts = run.summary["counts"]
    out = [
        f"{run.public_ref} · GSTR-2B reconciliation · {shop.name} · {run.period}",
        " · ".join(
            f"{k.replace('_', ' ')} {counts.get(k, 0)}"
            for k in (rc.EXACT, rc.MISMATCH, rc.PURCHASE_ONLY, rc.STATEMENT_ONLY, rc.AMBIGUOUS)
        ),
    ]
    for r in results:
        if r.class_ == rc.EXACT:
            continue
        if r.class_ == rc.MISMATCH and r.purchase:
            diffs = ", ".join(f"{k} {v}" for k, v in sorted(r.differences.items()))
            out.append(f"• mismatch {r.purchase.ref} vs 2B line {r.line.ref if r.line else '?'}: {diffs}")
        elif r.class_ == rc.PURCHASE_ONLY and r.purchase:
            tax = sum((r.purchase.amounts[c] for c in ("igst", "cgst", "sgst", "cess")), Decimal(0))
            out.append(
                f"• {r.purchase.ref} is not in GSTR-2B for {run.period} (tax associated {msg.inr(tax)}). "
                "Ask the supplier to report it in their GSTR-1."
            )
        elif r.class_ == rc.STATEMENT_ONLY and r.line:
            ln = by_line[r.line.ref]
            out.append(
                f"• 2B line {r.line.ref} {ln.supplier_gstin} {ln.invoice_number} {msg.inr(ln.invoice_value)} "
                "has no purchase bill here. Ask the owner whether the bill exists."
            )
        elif r.class_ == rc.AMBIGUOUS:
            side = r.purchase.ref if r.purchase else f"2B line {r.line.ref if r.line else '?'}"
            out.append(f"• ambiguous: {side} shares a match key with another item; the CA decides.")
    out.append(WORDING)
    return "\n".join(out)


def latest_summary(s: Session, shop: Shop, period: str) -> str:
    run = s.execute(
        select(ReconciliationRun)
        .where(ReconciliationRun.shop_id == shop.id, ReconciliationRun.period == period)
        .order_by(ReconciliationRun.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if run is None:
        return f"No GSTR-2B reconciliation for {shop.name} {period} yet. Send the file with `gstr2b {shop.code} {period}`."
    counts = run.summary["counts"]
    return f"{run.public_ref} ({shop.name} {period}): " + ", ".join(
        f"{k.replace('_', ' ')} {v}" for k, v in sorted(counts.items())
    )
