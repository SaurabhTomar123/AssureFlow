# Live run: purchase assurance (2026-11-06)

Switch server 0.31.0 (standalone stack, bundled Mattermost). Feature flag `PURCHASE_ASSURANCE_ENABLED=true`,
branch `feature/purchase-assurance`. Synthetic Mattermost users: `sharma` (owner), `suresh` (storekeeper,
delivery room only), `anil` (purchasing staff, shop room), `mehta` (CA / purchase reviewer). Every event reached
Assure Flow through the agent WebSocket without an @mention; the agent created `af-delivery-sharma` itself.
Transcripts are read back from Mattermost. The delivery room never shows a price.

Persisted outcome (PostgreSQL): `PR-0001` ready_for_payment, 4200.00 INR, due 2026-11-20, content hash
`933eed99cf16...`; `TK-0001` verified_complete; `INV-0001` approved at document generation 2; purchase pack
artifacts `assure-flow_sharma_PO-101_PR-0001.json` and `.xlsx`. Nothing is marked paid.

The driver script stopped twice on its own message matching (it read older room history); each time the run
was resumed from the same database state with no reset. The system's replies were unaffected.

## #af-shop-sharma

```
sharma: ok PO-101 r1
assure-flow: PO-101 r1 confirmed: 10 carton Sunflower oil 1L x 12 from ABC Traders.
sharma:  [1 file(s)]
assure-flow: Received R-0001 (F22_abc_invoice_10_cartons.pdf). Saving the original now.
assure-flow: R-0001 saved as INV-0001 (1 page). Reading it now.
assure-flow: INV-0001 r1: please check these details.
• Type: tax_invoice
• Supplier: ABC Traders
• Supplier GSTIN: 07ABCTR1234F1ZS
• Billed to GSTIN: 07SHARM9999K1ZU
• Invoice no.: ABC/2026/0101
• Date: 2026-11-05
• Place of supply: 07
• Taxable: ₹5,000.00
• CGST: ₹125.00
• SGST: ₹125.00
• IGST: ₹0.00
• Total: ₹5,250.00
Reply `ok INV-0001 r1` to confirm, or correct a value like `INV-0001 total=1180.00`.
sharma: ok INV-0002 r1
assure-flow: I could not find that in this room's scope. No case INV-0002 in this room.
sharma: ok INV-0001 r1
assure-flow: INV-0001 r1 confirmed. Running the GST checks.
assure-flow: INV-0001 looks like PO-101 from ABC Traders.
• invoice line 1 “Sunflower oil 1L x 12” → L1 Sunflower oil 1L x 12 (ordered 10 carton @ ₹500.00)
Linking also confirms the invoice is billed in the order's units.
Reply `link INV-0001 PO-101` to confirm, or name lines: `link INV-0001 PO-101 1=L1`.
sharma: link INV-0001 PO-101
assure-flow: INV-0001 linked to PO-101 (line 1 → L1). Checking it against the delivery.
assure-flow: PO-101 / INV-0001: waiting for evidence before purchase review.
• The invoice has not been included by the reviewer yet (invoice review comes first).
• No confirmed delivery report for this order yet.
assure-flow: Suresh Kumar confirmed delivery DR-0001 v1 for PO-101:
• L1 Sunflower oil 1L x 12: 8 carton
assure-flow: PO-101 / INV-0001: payment readiness is on hold.
• Sunflower oil 1L x 12: billed 10 carton but 8 confirmed received (difference 2).
It clears with a corrected invoice or more delivery evidence. Assign someone: `task INV-0001 anil tomorrow get a corrected invoice`.
assure-flow: PO-101 / INV-0001: payment readiness is on hold.
• Sunflower oil 1L x 12: billed 10 carton but 8 confirmed received (difference 2).
It clears with a corrected invoice or more delivery evidence. Assign someone: `task INV-0001 anil tomorrow get a corrected invoice`.
sharma: task INV-0001 anil tomorrow get a corrected invoice for 8 cartons
assure-flow: TK-0001 for Anil Verma: get a corrected invoice for 8 cartons. PO-101 / INV-0001, due 2026-11-07.
Reply `TK-0001 ack`, then `TK-0001 done <what you did>` when you have it. Finishing the task does not clear the hold; the corrected invoice or delivery evidence does.
assure-flow: TK-0001 assigned to Anil Verma, due 2026-11-07.
anil: TK-0001 ack
assure-flow: TK-0001 acknowledged.
anil: TK-0001 done ABC Traders is sending a revised bill for 8 cartons
assure-flow: TK-0001: thanks, noted (ABC Traders is sending a revised bill for 8 cartons). INV-0001 stays on hold until the corrected invoice or delivery evidence arrives and the checks pass.
sharma: TK-0001 verify
assure-flow: I could not use that input. TK-0001 cannot be verified yet: the purchase checks have not passed on the current evidence. A finished task alone never clears a mismatch.
sharma: corrected bill for INV-0001 [1 file(s)]
assure-flow: Received R-0002 (F23_abc_corrected_8_cartons.pdf). Saving the original now.
assure-flow: Your confirmation of INV-0001 r1 no longer applies because a replacement document arrived. Please check the new summary. (supersedes confirmed:01a1b018-528e-7490-a839-1e09ff744710)
assure-flow: Replacement document attached to INV-0001 (version 2). Earlier checks and approvals for this case no longer apply. Reading it now.
assure-flow: PO-101 / INV-0001: waiting for evidence before purchase review.
• The current invoice revision is not confirmed yet.
assure-flow: INV-0001 r2: please check these details.
• Type: tax_invoice
• Supplier: ABC Traders
• Supplier GSTIN: 07ABCTR1234F1ZS
• Billed to GSTIN: 07SHARM9999K1ZU
• Invoice no.: ABC/2026/0101
• Date: 2026-11-07
• Place of supply: 07
• Taxable: ₹4,000.00
• CGST: ₹100.00
• SGST: ₹100.00
• IGST: ₹0.00
• Total: ₹4,200.00
Reply `ok INV-0001 r2` to confirm, or correct a value like `INV-0001 total=1180.00`.
sharma: ok INV-0001 r2
assure-flow: INV-0001 r2 confirmed. Running the GST checks.
assure-flow: PO-101 / INV-0001: waiting for evidence before purchase review.
• The invoice has not been included by the reviewer yet (invoice review comes first).
• Less was billed than ordered. The owner must accept the partial delivery for this review.
If the rest is not coming with this invoice, reply `accept-partial PO-101`.
assure-flow: PO-101 / INV-0001: waiting for evidence before purchase review.
• The invoice has not been included by the reviewer yet (invoice review comes first).
• Less was billed than ordered. The owner must accept the partial delivery for this review.
If the rest is not coming with this invoice, reply `accept-partial PO-101`.
assure-flow: PO-101 / INV-0001: waiting for evidence before purchase review.
• Less was billed than ordered. The owner must accept the partial delivery for this review.
If the rest is not coming with this invoice, reply `accept-partial PO-101`.
sharma: accept-partial PO-101
assure-flow: Partial delivery of PO-101 accepted for this review. Still outstanding on PO-101: 2 carton Sunflower oil 1L x 12.
assure-flow: PO-101 / INV-0001: the purchase checks now pass. TK-0001 is still open; when you are satisfied, reply `TK-0001 verify` (or `cancel <reason>`).
sharma: TK-0001 verify
assure-flow: TK-0001 verified complete.
assure-flow: PO-101 / INV-0001: purchase checks passed. PR-0001 is with the reviewer.
sharma: authorize PR-0001 933eed99cf16 due 2026-11-20
assure-flow: I could not use that input. PR-0001 has not been reviewed yet.
assure-flow: PR-0001 (PO-101 / INV-0001, ₹4,200.00) was reviewed by CA Priya Mehta. Your sign-off is pending. Reply `authorize PR-0001 933eed99cf16 due YYYY-MM-DD` with the supplier's due date, or `due unknown`. This is payment preparation; no payment is made.
sharma: authorize PR-0001 933eed99cf16 due 2026-11-20
assure-flow: PR-0001 is ready for payment: ₹4,200.00, due 2026-11-20. Nothing has been paid; this records that the purchase was reviewed. Still outstanding on PO-101: 2 carton Sunflower oil 1L x 12. The purchase pack follows.
assure-flow: PR-0001 purchase pack (hash 933eed99cf16): Excel + JSON attached. Ready for payment; no payment has been made. [2 file(s)]
sharma: purchase PO-101
assure-flow: PO-101 / INV-0001: ready for payment.
Sunflower oil 1L x 12: ordered 10, received 8, billed 8 carton (outstanding 2).
PR-0001: ready for payment, ₹4,200.00, due 2026-11-20. No payment has been made.
```

## #af-delivery-sharma

```
assure-flow: PO-101 from ABC Traders: please count what arrived.
• L1 Sunflower oil 1L x 12: 10 carton ordered
Reply with the count, e.g. `PO-101 L1=8`.
suresh: PO-101 L1=8
assure-flow: DR-0001 v1 for PO-101:
• L1 Sunflower oil 1L x 12: 8 carton
Reply `ok DR-0001 v1` to confirm, or send corrected counts.
suresh: ok DR-0001 v1
assure-flow: Thanks. DR-0001 v1 confirmed for PO-101.
```

## #af-ca-review

```
assure-flow: RR-0001 · INV-0001 r1 · Sharma Kirana Store (sharma)
ABC Traders · ABC/2026/0101 · 2026-11-05 · total ₹5,250.00 · check run 1
• All required checks passed.
Reply `RR-0001 include`, `RR-0001 exclude <reason>`, `RR-0001 clarify <question>` or `RR-0001 supplier <reason>`.
mehta: RR-0001 include
assure-flow: RR-0001: INV-0001 included. It will count in the monthly pack.
assure-flow: No longer applies: RR-0001 'include' on INV-0001 because a replacement document arrived. The case needs a new decision. (supersedes decision:01a1b01e-bb3c-7d89-ad21-fee9835b268f)
assure-flow: RR-0002 · INV-0001 r2 · Sharma Kirana Store (sharma)
ABC Traders · ABC/2026/0101 · 2026-11-07 · total ₹4,200.00 · check run 1
• All required checks passed.
Reply `RR-0002 include`, `RR-0002 exclude <reason>`, `RR-0002 clarify <question>` or `RR-0002 supplier <reason>`.
mehta: RR-0002 include
assure-flow: RR-0002: INV-0001 included. It will count in the monthly pack.
assure-flow: PR-0001 · PO-101 / INV-0001 r2: purchase review.
• Sunflower oil 1L x 12: ordered 10, received 8, billed 8 carton (2 outstanding on the order)
Invoice total ₹4,200.00; invoice review: included; delivery confirmed; checks passed.
Hash 933eed99cf16. Reply `review PR-0001 933eed99cf16` to sign off this exact record. This is payment preparation; no payment is made.
mehta: review PR-0001 933eed99cf16
assure-flow: PR-0001 signed off. It now waits for the owner's authorization.
assure-flow: PR-0001 purchase pack (hash 933eed99cf16): Excel + JSON attached. Ready for payment; no payment has been made. [2 file(s)]
```
