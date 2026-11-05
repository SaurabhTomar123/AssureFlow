"""Latency and cost report (P5-10, spec section 13). Measured from the database; nothing is estimated
except token cost, which is labelled as an estimate.

Run: python -m scripts.measure
"""

from __future__ import annotations

import statistics
from decimal import Decimal

from sqlalchemy import func, select

from common.db import transaction
from common.settings import get_settings
from domain import models as m


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def main() -> None:
    settings = get_settings()
    with transaction() as s:
        ack: list[float] = []
        extraction: list[float] = []
        for receipt in s.execute(select(m.Receipt)).scalars():
            event = s.get(m.InboxEvent, receipt.inbox_event_id)
            row = s.execute(
                select(m.Outbox).where(m.Outbox.action_id == f"received:{receipt.id}")
            ).scalar_one_or_none()
            if event and row and row.delivered_at:
                ack.append((row.delivered_at - event.received_at).total_seconds())
            doc = s.execute(
                select(m.Document).where(m.Document.receipt_id == receipt.id).limit(1)
            ).scalar_one_or_none()
            if event and doc and doc.invoice_id:
                rev = s.execute(
                    select(m.InvoiceRevision)
                    .where(
                        m.InvoiceRevision.invoice_id == doc.invoice_id, m.InvoiceRevision.source != "human"
                    )
                    .order_by(m.InvoiceRevision.revision_no)
                    .limit(1)
                ).scalar_one_or_none()
                if rev:
                    summary = s.execute(
                        select(m.Outbox).where(m.Outbox.action_id == f"summary:{rev.id}")
                    ).scalar_one_or_none()
                    if summary and summary.delivered_at:
                        extraction.append((summary.delivered_at - event.received_at).total_seconds())
        tokens_in, tokens_out = s.execute(
            select(
                func.coalesce(func.sum(m.UsageRecord.input_tokens), 0),
                func.coalesce(func.sum(m.UsageRecord.output_tokens), 0),
            )
        ).one()
        providers = dict(
            s.execute(select(m.UsageRecord.provider, func.count()).group_by(m.UsageRecord.provider)).all()
        )
        cases = s.execute(select(func.count()).select_from(m.Invoice)).scalar_one()
        completed = s.execute(
            select(func.count()).select_from(m.Invoice).where(m.Invoice.status.in_(("approved", "excluded")))
        ).scalar_one()
        corrections = s.execute(
            select(func.count()).select_from(m.InvoiceRevision).where(m.InvoiceRevision.source == "human")
        ).scalar_one()
    usd = (
        Decimal(tokens_in) * settings.COST_USD_PER_MTOK_INPUT
        + Decimal(tokens_out) * settings.COST_USD_PER_MTOK_OUTPUT
    ) / Decimal(1_000_000)
    inr = usd * settings.USD_INR
    print("Assure Flow measurements (this database)")
    print(
        f"  receipt acknowledgment: n={len(ack)} median={statistics.median(ack) if ack else 0:.2f}s "
        f"p95={pct(ack, 0.95):.2f}s target={settings.ACK_TARGET_SECONDS}s"
    )
    print(
        f"  receipt -> summary:     n={len(extraction)} median={statistics.median(extraction) if extraction else 0:.2f}s "
        f"p95={pct(extraction, 0.95):.2f}s target={settings.EXTRACTION_TARGET_SECONDS}s"
    )
    print(f"  cases {cases}, completed (included or excluded) {completed}, typed corrections {corrections}")
    print(f"  extraction calls by provider: {providers or 'none'}")
    print(
        f"  model tokens in/out: {tokens_in}/{tokens_out}; estimated cost ₹{inr:.2f} (token-based estimate; "
        f"₹{(inr / completed if completed else Decimal(0)):.2f} per completed case)"
    )


if __name__ == "__main__":
    main()
