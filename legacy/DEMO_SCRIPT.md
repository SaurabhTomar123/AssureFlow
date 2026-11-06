# MunimJi — 3-Minute Demo Video Walkthrough Script

This script outlines the exact sequence for recording the hackathon demo video (Target: under 3 minutes).

---

## Beat 1: The Problem (0:00 - 0:25)
- **Visual:** Show a messy pile of paper receipts, thermal counter slips, and PDF invoices on a phone.
- **Narrator Voiceover:**
  > "Every month across India, millions of small shop owners dump crumpled purchase receipts and PDF invoices on their Chartered Accountants just hours before the GST filing deadline. CAs chase shop owners for missing details, while businesses lose thousands of rupees in unclaimed Input Tax Credit due to format errors and wrong tax types.
  > 
  > Simultaneously, daily store operations—inventory restocks, staff attendance registers, and monthly payroll—remain completely disconnected from these purchase bills.
  > 
  > Introducing MunimJi: where AI reads and advises, code checks, and humans decide."

---

## Beat 2: Private Shop Intake, Extraction & Auto-Restock (0:25 - 0:50)
- **Visual:** Open the private shop group (`shop-sharma-kirana`). Upload `bill_01_clean_kirana_5pct.pdf`.
- **Action:**
  - `bill-reader` agent responds within 2 seconds with a structured breakdown:
    - Supplier: Modern Agro Staples Ltd
    - Invoice: MAS-2026-101
    - Taxable Value: INR 7,400.00
    - Taxes: CGST INR 185.00 | SGST INR 185.00
    - Total: INR 7,770.00
  - Owner types `OK` to confirm.
  - `store-manager` agent immediately chimes in:
    - "Auto-Restock Complete: Inventory balances updated automatically (+1.0 units Modern Agro Staples Ltd Supplies)."
- **Narrator Voiceover:**
  > "Inside their private shop group, the owner simply drops a bill photo or PDF. The Bill Reader agent extracts every line item, taxes, and supplier details in seconds. As soon as the owner confirms with 'OK', the Store Manager agent automatically updates store inventory balances—bridging purchase billing directly into store operations."

---

## Beat 3: Missing GSTIN & Rupee Risk Follow-up (0:50 - 1:10)
- **Visual:** Upload cash vendor bill (`bill_12_missing_gstin.pdf`).
- **Action:**
  - `follow-up` agent triggers an alert in the shop group:
    > "Notice for Bill #LCV-2026-112: Supplier GSTIN missing from invoice. Input Tax Credit at risk: INR 360.00. Please upload a clearer copy or contact vendor."
- **Narrator Voiceover:**
  > "When a bill has a simple issue—like a missing GSTIN or blurry photo—the Follow-up agent alerts the shop owner in plain language and specifies the exact Rupee amount at risk, motivating immediate action."

---

## Beat 4: Serious Defect & CA Office Resolution (1:10 - 1:35)
- **Visual:** Switch view to the central `ca-office` room. Upload interstate bill (`bill_13_wrong_tax_type_interstate_charged_cgst.pdf`) from Gujarat charged with CGST/SGST instead of IGST.
- **Action:**
  - `return-preparer` agent surfaces the defect to the CA:
    > "Compliance Flag: Interstate transaction (Gujarat to Delhi) charged CGST/SGST instead of IGST. Disputed ITC: INR 1,440.00. Options: /approve, /reject, /ask_supplier"
  - CA types `/ask_supplier BILL-013`.
  - System instantly drafts a formal Section 16(2) compliance notice to the supplier.
- **Narrator Voiceover:**
  > "Serious defects never bother the shop owner. They route directly to the CA Office room. With one command, the CA drafts a formal Section 16(2) compliance amendment notice for the supplier."

---

## Beat 5: Duplicate Bill Guard (1:35 - 1:50)
- **Visual:** Upload a duplicate bill already in the system (`bill_16_duplicate_copy.pdf`).
- **Action:**
  - System immediately flags: `DUPLICATE_INVOICE detected: Bill #GPW-2026-999 already filed.`
- **Narrator Voiceover:**
  > "Our deterministic rule engine catches duplicate invoices before filing, protecting businesses from severe GST audit penalties."

---

## Beat 6: Month-End Summary & Export (1:50 - 2:05)
- **Visual:** Inside `ca-office`, CA types `/summary shop-sharma-kirana`.
- **Action:**
  - `return-preparer` outputs the month-end GSTR report:
    - Clean Invoices: 13
    - Open Issues: 7 (ITC at Risk: INR 4,240.00)
    - Eligible ITC Breakdown: CGST INR 4,528.00 | SGST INR 4,528.00 | IGST INR 1,620.00
    - Total Eligible ITC: INR 10,676.00
  - Show download of `munimji_gstr_summary_shop-sharma-kirana.json`.
- **Narrator Voiceover:**
  > "At month-end, one command generates the entire GSTR reconciliation report, detailing every rupee of eligible Input Tax Credit broken down by tax bracket, ready for final CA review."

---

## Beat 7: Multi-Shop Dashboard & Architecture Isolation (2:05 - 2:15)
- **Visual:** CA types `/dashboard`.
- **Action:**
  - `return-preparer` outputs aggregated multi-client status:
    - Sharma Kirana Store: 20 bills | 13 ready | 7 flags
    - Gupta Electronics: 0 bills
- **Narrator Voiceover:**
  > "The CA manages multiple independent retail shops from one workspace without cross-contaminating private shop client data."

---

## Beat 8: Junior CA Accounts Book & Khata Ledger (2:15 - 2:25)
- **Visual:** Back in `shop-sharma-kirana`, owner types `/khata`.
- **Action:**
  - `junior-ca` agent immediately returns the shop's accounts book:
    - Total Cash Outflow: INR 127,786.00
    - Inventory Purchases: INR 48,400.00
    - Operating Expenses: INR 54,400.00
    - Capital Equipment: INR 9,000.00
- **Narrator Voiceover:**
  > "MunimJi is also your merchant's daily bookkeeper. Typing /khata categorizes purchases into resale inventory, shop operating expenses, and capital equipment in seconds."

---

## Beat 9: Junior CA Tax Savings & Section 44AD Advisory (2:25 - 2:35)
- **Visual:** Owner types `/tax_savings` and `/presumptive 6000000 85`.
- **Action:**
  - `junior-ca` suggests:
    - Write off INR 1,350 depreciation on shop equipment under Section 32.
    - Personal tax deductions under Section 80C, 80D (health insurance), and NPS 80CCD(1B).
    - Recommends Section 44AD Presumptive Taxation (saving ~INR 102,600 on 85% digital turnover with exemption from Section 44AB audits).
- **Narrator Voiceover:**
  > "Like a true Junior CA, MunimJi actively suggests tax deductions—from Section 32 asset depreciation to Section 44AD presumptive tax savings—putting money back into small business pockets."

---

## Beat 10: Store Operations — Stock Health & Urgent Reorder Sheet (2:35 - 2:45)
- **Visual:** Store manager types `/stock` and `/reorder`.
- **Action:**
  - `store-manager` displays real-time inventory health (total SKUs, low-stock warnings, depleted items).
  - Automatically generates an itemized procurement replenishment sheet with suggested order quantities and estimated wholesale purchase costs.
- **Narrator Voiceover:**
  > "Store managers command inventory directly in chat. Typing /stock and /reorder generates instant procurement sheets with wholesale price estimates."

---

## Beat 11: Staff Check-in, Shift Briefings & Monthly Payroll (2:45 - 2:55)
- **Visual:** Store manager types `/checkin Ramesh present` and `/attendance` followed by `/payroll 2026-11`.
- **Action:**
  - Attendance logged and morning shift briefing generated with staff on duty, deliveries, and stock warnings.
  - Monthly payroll register computes wage disbursements pro-rated to actual attendance days.
- **Narrator Voiceover:**
  > "Staff check-ins, morning shift handovers, and month-end payroll calculations happen seamlessly inside the room."

---

## Beat 12: Interactive Visual Cockpit & Conclusion (2:55 - 3:00)
- **Visual:** Open browser at `http://localhost:8000/dashboard`. Toggle between `OWNER`, `MANAGER`, `STAFF`, and `CA` roles with live UI reactive metric filtering.
- **Narrator Voiceover:**
  > "MunimJi connects the entire business workflow: from bill photo to inventory restock, payroll, and CA tax filing. Role-based privacy ensures managers and staff see only what they need, while owners and CAs retain total control.
  > 
  > AI reads and advises, code checks, human decides. Thank you!"
