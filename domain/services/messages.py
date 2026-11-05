"""Room message templates. Plain, specific English; one actionable question at a time."""

from __future__ import annotations

from decimal import Decimal

from common.errors import DomainError
from domain.extraction import LOW_CONFIDENCE, MATERIAL_FIELDS
from domain.models import FieldEvidence, Invoice, InvoiceRevision

LABELS = {
    "document_type": "Type",
    "supplier_name": "Supplier",
    "supplier_gstin": "Supplier GSTIN",
    "recipient_gstin": "Billed to GSTIN",
    "invoice_number": "Invoice no.",
    "invoice_date": "Date",
    "place_of_supply": "Place of supply",
    "taxable_total": "Taxable",
    "cgst_total": "CGST",
    "sgst_total": "SGST",
    "igst_total": "IGST",
    "invoice_total": "Total",
}

ERROR_TEXT = {
    "FORBIDDEN": "You are not authorized for that action here.",
    "NOT_FOUND": "I could not find that in this room's scope.",
    "STALE_REVISION": "That refers to an older version. Nothing was changed.",
    "INVALID_TRANSITION": "That action is not allowed in the case's current state.",
    "SNAPSHOT_STALE": "The month changed after this pack was built. Nothing was approved.",
    "VALIDATION_ERROR": "I could not use that input.",
    "UNAUTHENTICATED": "That request expired. Please send it again.",
    "NOT_AVAILABLE_IN_THIS_RELEASE": "That action is not available in this release.",
}


def inr(value: Decimal | None) -> str:
    if value is None:
        return "?"
    sign = "-" if value < 0 else ""
    whole, _, frac = f"{abs(value):.2f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return f"{sign}₹{whole}.{frac}"


def error_reply(err: DomainError) -> str:
    base = ERROR_TEXT.get(err.code, "That did not work.")
    return f"{base} {err.message}".strip()


def received(receipt_ref: str, filename: str) -> str:
    return f"Received {receipt_ref} ({filename}). Saving the original now."


def preserved(case_ref: str, receipt_ref: str, pages: int) -> str:
    return f"{receipt_ref} saved as {case_ref} ({pages} page{'s' if pages != 1 else ''}). Reading it now."


def replacement_received(case_ref: str, generation: int) -> str:
    return (
        f"Replacement document attached to {case_ref} (version {generation}). Earlier checks and approvals "
        "for this case no longer apply. Reading it now."
    )


def rejected(receipt_ref: str, reason: str) -> str:
    return f"{receipt_ref} was not accepted: {reason}. Please send a PDF, JPG or PNG under the limits."


def duplicate_file(receipt_ref: str, case_ref: str) -> str:
    return f"{receipt_ref} is the same file as {case_ref}, which is already saved. No new case was created."


def extraction_failed(case_ref: str) -> str:
    return (
        f"I could not read {case_ref}. Please send a clearer photo or the PDF, replying with {case_ref} "
        "in the message so it attaches to the same case."
    )


def summary(case: Invoice, rev: InvoiceRevision, evidence: list[FieldEvidence]) -> str:
    uncertain = {
        e.field_path: e.page_no
        for e in evidence
        if e.source != "human"
        and (e.value_text is None or (e.confidence is not None and e.confidence < LOW_CONFIDENCE))
    }
    lines = [f"{case.case_ref} r{rev.revision_no}: please check these details."]
    for field, label in LABELS.items():
        value = getattr(rev, field)
        shown = inr(value) if isinstance(value, Decimal) else (value or "not readable")
        flag = ""
        if field in uncertain:
            page = uncertain[field]
            flag = f"  <- uncertain{f' (page {page})' if page else ''}"
        lines.append(f"• {label}: {shown}{flag}")
    if rev.multiple_invoices:
        lines.append(
            "This file seems to hold more than one invoice. Please send one invoice per file; "
            "I will hold this one until then."
        )
    missing = [LABELS.get(f, f) for f in MATERIAL_FIELDS if getattr(rev, f) in (None, "")]
    question = next((f for f in LABELS if f in uncertain), None)
    if missing:
        lines.append(f"Missing: {', '.join(missing)}.")
    if question:
        lines.append(f"Question: is the {LABELS[question].lower()} correct?")
    lines.append(
        f"Reply `ok {case.case_ref} r{rev.revision_no}` to confirm, or correct a value like "
        f"`{case.case_ref} total=1180.00`."
    )
    return "\n".join(lines)


def confirmed(case_ref: str, rev_no: int) -> str:
    return f"{case_ref} r{rev_no} confirmed. Running the GST checks."


def help_shop() -> str:
    return (
        "Send a bill photo or PDF here. Then:\n"
        "• `ok INV-0001 r1` confirms the details\n"
        "• `INV-0001 total=1180.00 date=2026-11-03` corrects values (no re-reading)\n"
        "• send a new file with `INV-0001` in the message to replace a document\n"
        "• `status`, `pending`, `why-held INV-0001`"
    )


def help_ca() -> str:
    return (
        "Review requests: `RR-0001 include`, `RR-0001 exclude <reason>`, `RR-0001 resolve <RULE-ID> <reason>`, "
        "`RR-0001 clarify <question>`, `RR-0001 supplier <reason>`.\n"
        "Month: `readiness <shop> 2026-11`, `snapshot <shop> 2026-11`, "
        "`approve SN-0001 <hash-12> [ack <held> <unassigned>]`, `assign INV-0001 2026-11`, `pending`.\n"
        "GSTR-2B: attach the portal JSON/Excel to `gstr2b <shop> 2026-11`; `recon <shop> 2026-11` shows the result."
    )
