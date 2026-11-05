# MunimJi — 3-Minute Demo Video Walkthrough Script

This script outlines the exact sequence for recording the hackathon demo video (Target: under 3 minutes).

---

## Beat 1: The Problem (0:00 - 0:30)
- **Visual:** Show a messy folder/pile of paper receipts, blurry photos, and PDF invoices on a phone.
- **Narrator Voiceover:**
  > "Every month across India, millions of small shop owners dump crumpled purchase receipts and PDF invoices on their Chartered Accountants just hours before the GST filing deadline. CAs are forced to chase shop owners for missing details, while businesses lose thousands of rupees in unclaimed Input Tax Credit due to format errors and wrong tax types.
  > 
  > Introducing MunimJi: where AI reads, code checks, and humans decide."

---

## Beat 2: Private Shop Intake & Instant Extraction (0:30 - 0:55)
- **Visual:** Open the private shop group (`shop-sharma-kirana`). Upload `bill_01_clean_kirana_5pct.pdf`.
- **Action:**
  - `bill-reader` agent responds within 2 seconds with a structured breakdown:
    - Supplier: Modern Agro Staples Ltd
    - Invoice: MAS-2026-101
    - Taxable Value: INR 7,400.00
    - Taxes: CGST INR 185.00 | SGST INR 185.00
    - Total: INR 7,770.00
  - Owner types `OK` to confirm.
- **Narrator Voiceover:**
  > "Inside their private shop group, the owner simply drops a bill photo or PDF. The Bill Reader agent extracts every line item, taxes, and supplier details in seconds. The owner confirms with a single reply."

---

## Beat 3: Missing GSTIN & Rupee Risk Follow-up (0:55 - 1:20)
- **Visual:** Upload cash vendor bill (`bill_12_missing_gstin.pdf`).
- **Action:**
  - `follow-up` agent triggers an alert in the shop group:
    > "Notice for Bill #LCV-2026-112: Supplier GSTIN missing from invoice. Input Tax Credit at risk: INR 360.00. Please upload a clearer copy or contact vendor."
- **Narrator Voiceover:**
  > "When a bill has a simple issue—like a missing GSTIN or blurry photo—the Follow-up agent alerts the shop owner in plain language and specifies the exact Rupee amount at risk, motivating immediate action."

---

## Beat 4: Serious Defect & CA Office Resolution (1:20 - 1:55)
- **Visual:** Switch view to the central `ca-office` room. Upload interstate bill (`bill_13_wrong_tax_type_interstate_charged_cgst.pdf`) from Gujarat charged with CGST/SGST instead of IGST.
- **Action:**
  - `return-preparer` agent surfaces the defect to the CA:
    > "Compliance Flag: Interstate transaction (Gujarat to Delhi) charged CGST/SGST instead of IGST. Disputed ITC: INR 1,440.00. Options: /approve, /reject, /ask_supplier"
  - CA types `/ask_supplier BILL-013`.
  - System instantly drafts a formal Section 16(2) compliance notice to the supplier.
- **Narrator Voiceover:**
  > "Serious defects never bother the shop owner. They route directly to the CA Office room. With one command, the CA drafts a formal Section 16(2) compliance amendment notice for the supplier."

---

## Beat 5: Duplicate Bill Guard (1:55 - 2:15)
- **Visual:** Upload a duplicate bill already in the system (`bill_16_duplicate_copy.pdf`).
- **Action:**
  - System immediately flags: `DUPLICATE_INVOICE detected: Bill #GPW-2026-999 already filed.`
- **Narrator Voiceover:**
  > "Our deterministic rule engine catches duplicate invoices before filing, protecting businesses from severe GST audit penalties."

---

## Beat 6: Month-End Summary & Export (2:15 - 2:40)
- **Visual:** Inside `ca-office`, CA types `/summary shop-sharma-kirana`.
- **Action:**
  - `return-preparer` outputs the month-end GSTR report:
    - Clean Invoices: 13
    - Open Issues: 8 (ITC at Risk: INR 4,610.00)
    - Eligible ITC Breakdown: CGST INR 4,528.00 | SGST INR 4,528.00 | IGST INR 1,620.00
    - Total Eligible ITC: INR 10,676.00
  - Show download of `munimji_gstr_summary_shop-sharma-kirana.json`.
- **Narrator Voiceover:**
  > "At month-end, one command generates the entire GSTR reconciliation report, detailing every rupee of eligible Input Tax Credit broken down by tax bracket, ready for final CA review."

---

## Beat 7: Junior CA Accounts Book & Khata Ledger (2:25 - 2:40)
- **Visual:** Back in `shop-sharma-kirana`, owner types `/khata`.
- **Action:**
  - `junior-ca` agent immediately returns the shop's accounts book:
    - Total Cash Outflow: INR 1,24,246.00
    - Inventory Mal Kharid: INR 48,400.00
    - Operating Expenses: INR 51,400.00
    - Capital Equipment: INR 9,000.00
- **Narrator Voiceover:**
  > "MunimJi is also your merchant's daily bookkeeper. Typing /khata categorizes purchases into resale inventory, shop operating expenses, and capital equipment in seconds."

---

## Beat 8: Junior CA Tax Savings & 44AD Optimization (2:40 - 2:55)
- **Visual:** Owner types `/tax_savings` and `/presumptive 6000000 85`.
- **Action:**
  - `junior-ca` suggests:
    - Write off INR 1,350 depreciation on shop equipment under Section 32.
    - Personal tax deductions under Section 80C, 80D (health insurance), and NPS 80CCD(1B).
    - Recommends Section 44AD Presumptive Taxation (saving ~INR 1,02,600 on 85% digital turnover with exemption from Section 44AB audits).
- **Narrator Voiceover:**
  > "Like a true Junior CA, MunimJi actively suggests tax deductions—from Section 32 asset depreciation to Section 44AD presumptive tax savings—putting money back in small business pockets."

---

## Beat 9: Architecture & Conclusion (2:55 - 3:00)
- **Visual:** Display architecture slide highlighting Switch rooms, agent isolation, and core rule.
- **Narrator Voiceover:**
  > "MunimJi is powered by Switch: private rooms per shop ensure complete confidentiality, while shared rooms give CAs cross-client superpowers. AI reads and advises, code checks, human decides. Thank you!"

