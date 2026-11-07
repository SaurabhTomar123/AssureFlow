# Purchase assurance (Update U2): change contract

Source: *Assure Flow Purchase Assurance Technical Update U2*, 6 November 2026, an addendum to specification v1.4.
This file is the scoped contract for what this release builds, what it defers, and how each
requirement is checked. v1.4 remains authoritative for everything not listed here.

**Release scope:** the "smallest useful hackathon slice" (U2 §10), behind the feature flag
`PURCHASE_ASSURANCE_ENABLED` (default `false`) and per-shop opt-in (`shops.purchase_assurance`).
With the flag off, every v1.4 behaviour, test and export is unchanged.

## The story this release supports

```
seeded draft order PO-101 (10 cartons, ABC Traders)
 → owner confirms the order                     ok PO-101 r1                     (shop room)
 → delivery question in the delivery room (no prices)
 → owner uploads the invoice (10 cartons); v1.4 extraction, confirmation, checks, CA review
 → owner confirms the proposed link             link INV-0001 PO-101             (shop room)
 → storekeeper reports and confirms 8 received  PO-101 L1=8 · ok DR-0001 v1     (delivery room)
 → code: billed 10 > received 8 → held, with the exact difference
 → owner assigns the correction                 task INV-0001 anil tomorrow get a corrected invoice
 → assignee acknowledges / reports              TK-0001 ack · TK-0001 done …
 → corrected invoice (8 cartons) uploaded to the same case; v1.4 flow reruns; CA includes it
 → owner accepts the partial delivery           accept-partial PO-101            (2 cartons stay outstanding)
 → owner verifies the task                      TK-0001 verify                   (refused while the mismatch remains)
 → purchase review request PR-0001 in the CA room with its hash
 → reviewer signs the exact record              review PR-0001 <hash12>          (CA room)
 → owner authorizes the exact record            authorize PR-0001 <hash12> due 2026-11-20
 → frozen purchase pack (JSON + Excel) posted; status "ready for payment", never "paid"
```

## Decisions (also in `docs/decisions.md`)

| ID | Decision | Why |
|---|---|---|
| D-24 | Reviewer = the existing assigned CA plus a `purchase_review` capability. `ca_assignments` is **not** migrated to `reviewer_assignments` and "CA review" is **not** renamed in this release. | The migration touches every v1.4 room, parser guard and test for no visible gain in the slice; historical CA decisions stay untouched. Planned for the next release. |
| D-25 | Capabilities live in `shop_capabilities(user, shop, capability)`: `order_confirm`, `delivery_confirm`, `task_assign`, `task_work`, `invoice_view`, `purchase_review`, `readiness_authorize`. Staff are users with role `staff` and no shop membership. | Staff must never become "owners" through `shop_memberships`; titles grant nothing. |
| D-26 | The extraction schema v1 has no unit per invoice line. The unit is confirmed by the owner when linking (the link message states the order unit); M03 compares order and delivery units exactly and treats the confirmed link as the invoice unit. | Adding units to the extraction schema would re-key every recorded fixture a day before release. Planned as ExtractionSchema v2. |
| D-27 | Purchase state lives on `purchase_links.purchase_state`, never in `invoices.status`. The invoice workflow is unchanged; every invoice status change schedules purchase re-evaluation. | U2 §4 "service boundaries". |
| D-28 | Reviewer and owner decisions are stored on the immutable `payment_readiness` record (actor, time, context, hash) plus audit events, not in the v1.4 `decisions` table. | The v1.4 decision envelope is keyed to review requests; a typed `decision_scope` extension is planned. |
| D-29 | Orders are seeded (`seed/purchase_orders.yaml`) and confirmed in chat. Order creation in chat, order OCR and price changes (new order revision) are deferred. | U2 §10 "structured seeded order entry first". |

## Records (migration `u2`)

`shop_capabilities`, `purchase_orders`, `purchase_order_revisions` (lines JSON with stable `line_id`),
`delivery_reports` (lines JSON, `report_version`, supersede chain), `delivery_events` (append-only),
`purchase_links` (one active link per case and per order: partial unique indexes), `purchase_match_runs`
(append-only, unique per link + input hash + rule version), `business_tasks`, `task_events` (append-only),
`payment_readiness`. `artifacts` gains an optional `readiness_id` for purchase packs. Users gain role `staff`,
rooms gain purpose `delivery`, grants gain `run_purchase_match` and `build_purchase_export`.

## Matching rules (`rules/purchase.py`, version `purchase_v1`)

| Rule | Implemented as |
|---|---|
| M01 identity and scope | supplier GSTIN of the order equals the invoice's; currency INR; same shop |
| M02 line mapping | every invoice line maps to exactly one order line, by the confirmed link mapping only |
| M03 units and quantities | exact Decimal; sums only current confirmed delivery-report versions; received > ordered, billed > ordered, billed > received → hold with the difference; negative → hold |
| M04 price | printed unit price equals the order unit price exactly (tax-exclusive basis on both) |
| M05 partial delivery | billed < ordered allowed only when billed = received and the owner accepted the partial delivery; outstanding shown separately |
| M06 baseline | the invoice case must be `approved` (current CA include); otherwise "waiting for invoice review" |
| M07 missing evidence | no confirmed delivery / no mapping → `needs_evidence`; never inferred from an invoice or a task message |
| M08 duplicate consumption | second active link to the same order refused (unique index); a superseded report never adds to the total |

## Not in this release (stated in README)

Guided setup, permission preflight and routing policies (U2 §14–17); standing auto-assignment; order creation
in chat, order OCR, price-change revisions; multiple invoices per order, unit conversion, returns; reminders for
tasks; reviewer `hold`/`exclude` on purchases; task reassignment; Slack and Teams verification; payment
execution, inventory, payroll, collections.

## Checklist U0–U4

Status on 2026-11-06: U0–U4 done and verified live; per-item evidence and the partly-covered UAT rows are in
[docs/gates/U2.md](gates/U2.md).

| Phase | Item | Test |
|---|---|---|
| U0 | capabilities, staff role, delivery room, receiver sees no prices | `test_receiver_never_sees_prices` |
| U1 | orders + confirmation, delivery reports/events, link + mapping | `test_delivery_correction_replaces_not_adds`, `test_link_rules` |
| U2 | matching rules, match job, task assignment, task done does not clear the hold | `test_short_delivery_holds_and_task_does_not_clear` |
| U3 | review + owner authorization bound to hash, stale checks, partial acceptance, frozen export | `test_full_purchase_story`, `test_stale_review_refused` |
| U4 | flag off preserves v1.4, baseline suite green, live run | `test_flag_off_keeps_v14`, `make test`, live run |
