# MunimJi (AssureFlow) — Autonomous Multi-Agent GST, Store Operations & Commercial Bookkeeping Platform

> **Hackathon:** WeMakeDevs & DevTools Academy — Flip the Switch Hackathon  
> **Primary Track:** Track 1 — Best Business Workflow ($2,000 USD)  
> **Sponsored Voice Track:** Code with Wispr Voice Track ($500 USD)  
> **Core Operating Principle:** AI reads and advises, code checks, human decides.  
> **Synthetic Data Notice:** All invoices, merchant entities, taxpayer profiles, employee rosters, and GSTIN identifiers in this project are 100% synthetic.

---

## 1. Executive Summary & Problem Context

In India, over 63 million Micro, Small, and Medium Enterprises (MSMEs) face severe operational and compliance bottlenecks approaching the monthly Goods and Services Tax (GST) filing deadline (GSTR-3B / GSTR-1). Retailers, distributors, and shopkeepers accumulate crumpled physical paper receipts, thermal counter slips, informal estimate slips, and digital PDF invoices throughout the month. At month-end, these are dumped onto their Chartered Accountants (CAs).

Simultaneously, retail shop owners struggle with daily store management, multi-party dispute resolution, and fragmented reconciliation:
1. **Input Tax Credit (ITC) Leakage:** Invalid or mismatched GSTINs prevent merchants from claiming legal tax credits under Section 16(2) of the CGST Act.
2. **"Kacha vs Pakka" Informal Paper Slips:** Counter estimate chits mixed into formal tax invoices cause immediate GST audit scrutiny and penalties under Section 122 if filed, but throwing them away causes inventory loss and untracked cash outlays.
3. **Supplier Default & Disconnected Vendor Disputes (Rule 37A):** Physical bills paid to vendors are disallowed if the supplier fails to upload the invoice in GSTR-1, causing surprise ITC reversals and mandatory 18% Section 50 interest penalties with zero streamlined channel to dispute it.
4. **Three-Way Cash Disconnect:** Accounting books, government GSTR-2B portal feeds, and bank account debit statements operate in silos, making vendor payment verification and tax audit preparation an excruciating manual task.
5. **Absence of Real-Time Bookkeeping:** Small proprietors lack continuous bookkeeping, missing out on statutory tax deductions (Section 32 depreciation, Section 44AD presumptive taxation, and Section 80C/80D personal deductions).
6. **Perishable Goods & Inventory Expiry (FEFO):** FMCG retailers lose substantial margins to expired stock discovered too late on shelves without contractual return-to-vendor (RTV) debit claims.
7. **Inventory Shrinkage & Unbalanced Stock:** Thefts, breakage, and unrecorded counter samples create massive discrepancies between recorded ledgers and physical stock.
8. **Dual-Tier Workforce Disconnect:** Store owners manage both salaried white-collar staff (managers, cashiers) and blue-collar daily-wage workers (loaders, drivers) on manual paper registers with frequent cash advances ("udhari") and arbitrary overtime calculations.
9. **Hands-Busy Floor Environment:** Shopkeepers rarely have time to type commands into desktops while unloading crates or serving counter customers.
10. **Lack of Enterprise Multi-Tenancy & RBAC:** Multi-store owners and CA practices need robust multi-tenancy with JWT authentication and strict access boundaries between store staff, managers, and accountants.

**MunimJi** solves this by establishing an autonomous, multi-agent enterprise workflow orchestrated across isolated rooms via **Switch** and **Meta WhatsApp Cloud API**, backed by deterministic verification engines, a "Kacha-Pakka" document classifier, an automated Vendor Dispute Concierge, a DGGI Audit Radar, Wispr Voice Ingestion, a Smart Inventory Engine, an Autonomous Double-Entry General Ledger, a 30-Day Predictive Cash Flow Runway, and a Dual-Tier Smart Attendance and HR Disbursement System.

---

## 2. Breakthrough Hackathon Innovations

### 1. "Kacha-Pakka" Smart Document Sieve (`src/extraction/document_classifier.py`)
- **The Problem:** Indian retail counters routinely receive two types of paper documents: formal GST Tax Invoices ("Pakka Bill") and informal handwritten estimate slips ("Kacha Parchi"). Mixing them into the CA filing queue triggers severe penalties under Section 122 of the CGST Act. However, discarding them destroys real operational inventory records and unrecorded cash outlays.
- **The Autonomous Solution:** MunimJi automatically classifies uploaded documents into `PAKKA_TAX_INVOICE` or `KACHA_ESTIMATE_SLIP`.
  - **Pakka Bills** enter the standard GST verification pipeline, claim ITC, and schedule for GSTR-3B.
  - **Kacha Slips** are strictly quarantined from the tax return queue (preventing audit scrutiny) while automatically updating inventory stock balances via `store-manager` and recording non-GST expense outlays in the merchant's digital `/khata`.

### 2. Autonomous Vendor Dispute Concierge (`src/concierge/vendor_dispute.py`)
- **The Problem:** When reconciliation detects an invoice missing in the government GSTR-2B portal, traditional software leaves it as an error flag. The buyer must manually call the supplier or forfeit their Input Tax Credit.
- **The Autonomous Solution:** MunimJi automatically triggers a tokenized, secure vendor dispute portal.
  - Generates dispute tracking links dispatched directly to the defaulting vendor.
  - Provides frictionless vendor resolution actions via WhatsApp or Web (`AMEND_GSTR1` or `ISSUE_CREDIT_NOTE`).
  - Upon vendor resolution, automatically broadcasts multi-room confirmation notifications to both the merchant's room (`shop-sharma-kirana`) and the CA practice cockpit (`ca-office`), unlocking withheld payments.

### 3. Proactive GST Audit Radar & Supplier Risk Scorecard (`src/advisory/audit_radar.py`)
- **The Problem:** MSMEs only discover tax compliance risks when they receive an official show-cause notice from the Directorate General of GST Intelligence (DGGI).
- **The Autonomous Solution:** Computes proactive, real-time risk telemetry:
  - **DGGI Audit Risk Index (0 to 100):** Evaluates ratio of unverified ITC, missing GSTR-2B filings, and unfiled vendor exposure.
  - **Supplier Compliance Scorecard:** Assigns compliance badges to vendors (`A+ Safe Partner`, `B Watchlist`, `C Chronic Defaulter`) with specific payment withholding recommendations.
  - **MSME Credit Solvency Score (300 to 900):** Synthesizes verified turnover, reconciled bank debits, and prompt filings to assess Mudra and MSME working capital loan readiness.

### 4. Smart Autonomous Inventory Engine (`src/inventory/service.py`)
- **FEFO (First-Expired, First-Out) & Batch Tracking:** Tracks batch numbers and expiry dates on every bill. Categorizes batches into `EXPIRED`, `CRITICAL` (<15 days), `WARNING` (15-45 days), and `HEALTHY`.
- **Return-to-Vendor (RTV) Debit Notes:** Automatically issues formal debit notes (`DN-RTV`) for expired goods, claiming tax reversals (18% GST) and supplier refunds while auto-deducting stock.
- **Dynamic Run-Rate Reordering:** Computes rolling Average Daily Velocity (ADV) and Days of Inventory Remaining (DIR). Generates pre-calculated Economic Order Quantity (EOQ) Purchase Order (PO) drafts.
- **Physical Shrinkage & Leakage Audit:** Command `/audit_stock` compares physical counts against expected book stock (`Initial + Purchases - Billed Sales`), triaging discrepancies into `NORMAL_VARIANCE`, `SHRINKAGE_WARNING`, or `SEVERE_LEAKAGE`.
- **Supplier Price Intelligence:** Analyzes historical purchase prices across vendors, alerting when another distributor previously offered identical SKUs at a lower price.

### 5. Autonomous Double-Entry Ledger & Cash Flow Forecast (`src/accounts/double_entry.py`)
- **Standard Chart of Accounts (COA):** Assets (`1000`), Liabilities (`2000`), Equity (`3000`), Revenue (`4000`), Expenses (`5000`).
- **Autonomous Balanced Journal Entries:** Automatically posts balanced debits and credits upon bill confirmation, bank disbursement, stock shrinkage, and payroll.
- **Real-Time Financial Statements:** Generates balanced Trial Balance, monthly Profit & Loss (P&L), and Balance Sheet.
- **30-Day Predictive Cash Flow Runway:** Combines liquid cash, accounts payable due dates, salary obligations, fixed overheads, and net GST cash liability on the 20th against projected daily sales velocity to assign a Liquidity Safety Index (`SAFE`, `TIGHT`, `CRITICAL_DEFICIT`).
- **GSTR-Optimized Vendor Payment Priority Queue:** Ranks unpaid bills by GSTR-2B match status, DGGI supplier scorecard, cash discounts, and aging. Recommends which suppliers to pay first to unlock maximum ITC while withholding payment from defaulting vendors.

### 6. Smart Attendance & Dual-Tier HR Disbursement System (`src/staff/service.py`)
- **Tier Modeling (White-Collar vs. Blue-Collar):**
  - **White-Collar (Managers, Cashiers, Accountants):** Shift window with 15-minute grace period, automated late-mark penalty engine (**3 late marks = 0.5-day salary deduction**), leave balances (Casual Leave `CL`, Sick Leave `SL`, Paid Leave `PL`), and regularization workflows.
  - **Blue-Collar (Loaders, Drivers, Floor Stockers):** Voice punch-in/out, worked-hour thresholding (`<4h` Absent, `4-7h` Half-Day, `7-9h` Full-Day, `>9h` Overtime), dynamic overtime calculation at **1.5x standard hourly rate**, and 1-click crew check-ins.
- **Shift Understaffing Warning:** Automated alerts when critical floor personnel (loaders, delivery drivers) fail to punch in within 30 minutes of shift start.
- **"Udhari" Cash Advances Ledger:** Tracks mid-month cash advances given to floor workers (`/advance [name] [amount]` or voice), automatically scheduling and deducting recoveries from payroll.
- **Bulk Payout Advice Generator:** Prepares structured bulk payout batch files (standard Indian banking CSV/JSON for NEFT/RTGS/UPI batching) with dual-authorization approval (`Accountant Agent drafts -> Shop Owner approves -> Double-entry journal JE recorded`).

### 7. Wispr Flow Voice Ingestion Subsystem (`src/voice/voice_transcriber.py`)
- **The Problem:** Kirana owners and warehouse staff have dirty or busy hands while unloading trucks or attending counter patrons. Typing commands into a chat UI creates friction.
- **The Autonomous Solution:** Targets the **Code with Wispr Voice Track**.
  - Ingests natural spoken Hinglish and English voice notes (e.g., *"12 bori Aashirvaad Atta delivery aayi"*, *"Poori loading team present hai siwaye Mukesh ke, aur Chandan ko 1500 advance diya"*).
  - Automatically parses voice transcriptions into structured operational actions: inventory restock, crew attendance check-ins, udhari advances, or tax/khata queries with zero manual typing.

### 8. 3-Room Switch War-Room Simulator & 15-Beat Interactive CLI Runner
- **Live Web Simulator (`/switch-simulator`):** An interactive 3-column split view displaying isolated Switch rooms (`shop-sharma-kirana`, `ca-office`, `vendor-dispute-desk`) running multi-agent handoffs in real-time.
- **1-Click Terminal Demo Runner (`scripts/demo_switch_live.py`):** High-speed colorized terminal playback running all 15 beats, demonstrating instant message propagation, automated disputes, voice ingestion, FEFO expiry, double-entry journaling, and bulk payout approvals.

---

## 3. Multi-Room Isolation & System Architecture

MunimJi decouples shop-level intake, store operations, external vendor disputes, and CA-level regulatory oversight through strict room and tenant isolation:

```
+---------------------------------------------------------------------------------------------------+
|                           SWITCH MULTI-ROOM COLLABORATION TOPOLOGY                                |
|                                                                                                   |
|  +-------------------------------+   +-----------------------------+   +-----------------------+  |
|  |     Shop Room (Private)       |   | Vendor Dispute Desk (Shared)|   | CA Office Room(Shared)|  |
|  | - Shop Owner Sharma           |   | - External Defaulting Vendor|   | - Chartered Accountant|  |
|  | - Store Manager Ramesh        |   | - Dispute Concierge Agent   |   | - GST Checker Agent   |  |
|  | - Bill Reader Agent           |   |                             |   | - Return Preparer     |  |
|  | - Store Manager Agent         |   | Broadcast Resolution Events |   | - Audit Radar Telemetry| |
|  | - Junior CA Bookkeeper        |<------------------------------->|   | - Double-Entry Auditor|  |
|  | - Wispr Voice Intake          |   | Tokenized Dispute Link      |   +-----------+-----------+  |
|  +---------------+---------------+   +-----------------------------+               |              |
|                  |                                                                 |              |
|                  +-----------------------------------+-----------------------------+              |
|                                                      |                                            |
+------------------------------------------------------|--------------------------------------------+
                                                       v
+---------------------------------------------------------------------------------------------------+
|                                  FASTAPI ENTERPRISE CORE ENGINE                                   |
|                                                                                                   |
|  +---------------------------+   +---------------------------+   +-----------------------------+  |
|  | Multi-Tenancy & Security  |   | "Kacha-Pakka" Sieve       |   | Rule-Based GST Engine       |  |
|  | - JWT Bearer Tokens       |-->| - Pakka Tax Invoice       |-->| - Mod-36 Check-Digit        |  |
|  | - Tenant & User Scoping   |   | - Kacha Estimate Slip     |   | - Place of Supply           |  |
|  | - RBAC Guard & Checkers   |   | - Audit Quarantine        |   | - Duplicate Guard           |  |
|  +---------------------------+   +---------------------------+   +--------------+--------------+  |
|                                                                                 |                 |
|  +---------------------------+   +---------------------------+   +--------------v--------------+  |
|  | Store Operations & Voice  |   | Junior CA & Audit Radar   |   | GSP & Bank Reconciliation   |  |
|  | - Wispr Flow Audio Notes  |   | - Section 44AD Presumptive|   | - 2-Way GSTR-2B Auto-Recon  |  |
|  | - FEFO Expiry & RTV Notes |   | - Double-Entry Ledger     |   | - Rule 37A Supplier Notices |  |
|  | - Dynamic Run-Rate POs    |   | - 30-Day Cash Runway      |   | - 3-Way Bank Outflow Match  |  |
|  | - Shrinkage & Leakage     |   | - Vendor Priority Queue   |   | - Dispute Concierge Webhook |  |
|  | - Smart Dual-Tier HR      |   | - P&L & Balance Sheet     |   | - Account Aggregator Feeds  |  |
|  | - Bulk Payout Advice Batch|   | - DGGI Audit Risk Index   |   +-----------------------------+  |
|  +---------------------------+   +---------------------------+                                    |
+---------------------------------------------------------------------------------|-----------------+
                                                                                  v
+---------------------------------------------------------------------------------------------------+
|                                PERSISTENCE & AUDIT LEDGER LAYER                                   |
|                                                                                                   |
|  [ tenants ] <---> [ organization_users ] <---> [ audit_logs ]                                    |
|      |                                                                                            |
|      +-----------> [ shops ] <---- [ bills ] <---- [ bill_items ] <---- [ compliance_issues ]     |
|                        |               |                                                          |
|                        |               +-----------> [ item_batches ] <--- [ items ]              |
|                        |               |                                                          |
|                        |               +-----------> [ stock_movements ] <--- [ stock_adjustments ]|
|                        |                                                                          |
|                        +-----------> [ employees ] <---- [ attendance ] <---- [ payroll ]         |
|                        |               |                                                          |
|                        |               +-----------> [ leave_balances ] <--- [ staff_advances ]   |
|                        |               |                                                          |
|                        |               +-----------> [ payout_batches ]                           |
|                        |                                                                          |
|                        +-----------> [ journal_entries ] <--- [ journal_entry_lines ]             |
|                        |                                                                          |
|                        +-----------> [ gstr2b_inward_records ] (Portal Feeds & Statuses)           |
|                        |                                                                          |
|                        +-----------> [ bank_transactions ] (UPI / NEFT / RTGS Debits)             |
|                        |                                                                          |
|                        +-----------> [ ledger_entries ] (Expense Categorization & Cashflows)       |
+---------------------------------------------------------------------------------------------------+
```

---

## 4. Autonomous Agents & Specialized Roles

### 1. `bill-reader` (Stationed in Shop Rooms & WhatsApp Bridge)
- **Role:** Multimodal intake, document classification, and visual extraction.
- **Behavior:** Automatically classifies incoming files into `PAKKA_TAX_INVOICE` or `KACHA_ESTIMATE_SLIP`. Extracts supplier name, GSTIN, invoice number, date, line items, taxable values, CGST, SGST, IGST, and total amounts. Requests merchant confirmation with structured previews.

### 2. `gst-checker` (Deterministic Rule Auditor)
- **Role:** Regulatory math and legal format auditor.
- **Behavior:** Evaluates every confirmed invoice against Indian statutory standards:
  - Validates GSTIN check-digit using ISO/IEC 7064 Mod-36 algorithm.
  - Verifies Place of Supply (Intrastate requires equal 50/50 CGST+SGST with zero IGST; Interstate requires IGST only with zero CGST/SGST).
  - Cross-checks arithmetic totals within 1.0 INR round-off tolerance.
  - Detects duplicate invoices against historical ledgers.
  - Triages findings into `simple` issues (handled locally in the shop room) and `serious` issues (routed to the CA office).

### 3. `follow-up` (Stationed in Shop Rooms & WhatsApp Bridge)
- **Role:** Merchant communication and ITC risk alerter.
- **Behavior:** Handles simple defects (blurry captures, missing supplier GSTIN). Translates regulatory errors into actionable business terms, explicitly calculating the **exact Rupee amount of Input Tax Credit at risk**. Sends automated countdown reminders approaching tax filing deadlines.

### 4. `store-manager` (Stationed in Shop Rooms)
- **Role:** Inventory replenishment, FEFO tracking, staff attendance, shift briefings, and payroll.
- **Behavior:**
  - **FEFO Expiry Audits:** Alerts on expiring batches; auto-generates Return-to-Vendor Debit Notes (`DN-RTV`).
  - **Dynamic Run-Rate POs:** Calculates rolling ADV and generates replenishment PO drafts based on EOQ.
  - **Shrinkage Audits:** Compares physical counts against expected stock, triaging discrepancies over 2%.
  - **Smart Attendance:** Tracks white-collar late marks (3 lates = 0.5-day cut), blue-collar worked hours, and 1.5x overtime.
  - **Udhari & Cash Advances:** Manages floor worker advances and recovers them from wages.
  - **Bulk Payout Advice Batches:** Generates structured bank/UPI payout batches for owner approval.

### 5. `junior-ca` (Stationed in Shop Rooms)
- **Role:** Double-entry bookkeeping and proactive tax optimization.
- **Behavior:**
  - Posts balanced double-entry journal entries (`Debit Inventory/Expense, Credit Accounts Payable/Bank`).
  - Generates balanced Trial Balance, Profit & Loss (P&L), and Balance Sheet.
  - Evaluates 30-day cash flow runway and provides Liquidity Safety Index.
  - Ranks unpaid invoices in the GSTR-Optimized Payment Priority Queue.
  - Analyzes eligibility for **Section 44AD Presumptive Taxation** and Section 32 Depreciation.

### 6. `return-preparer` (Stationed in CA Office Room)
- **Role:** Practice management coordinator and GSTR aggregator.
- **Behavior:** Presents serious compliance defects to the CA with single-click decisions (`/approve`, `/reject`, `/ask_supplier`). Automatically generates legally grounded Section 16(2) compliance notices for non-compliant suppliers. Generates monthly GSTR reconciliation summaries with eligible ITC breakdowns and downloadable JSON audit files.

### 7. Autonomous Vendor Concierge (Stationed in Vendor Dispute Desk)
- **Role:** Supplier dispute mediation and resolution tracking.
- **Behavior:** Issues tokenized dispute URLs, processes supplier remediation (GSTR-1 amendment or Credit Note issuance), and dispatches automated resolution broadcasts to both the merchant room and CA office.

---

## 5. Live GSP Two-Way & Account Aggregator Three-Way Match Engines

### Two-Way GSTR-2B Auto-Reconciliation
- **The Problem:** Under Section 16(2)(aa) of the CGST Act, a buyer is legally barred from claiming Input Tax Credit unless the supplier files GSTR-1 and the invoice appears in the buyer's auto-drafted GSTR-2B. Under GST Rule 37A, failure to reconcile causes mandatory ITC reversal with 18% interest.
- **The Solution:**
  - `GSPClient` syncs live portal inward returns.
  - The matching engine compares physical purchase bills in books against portal records.
  - Classifications: `RECON_MATCHED`, `RECON_TAX_MISMATCH`, `SUPPLIER_DEFAULT`, `UNRECORDED_PURCHASE`.
  - **Rule 37A Demand Notices:** Automatically drafts formal legal notices to defaulting vendors demanding return amendment before payment release.

### Three-Way Bank Reconciliation Engine
- **The Problem:** Vendor disbursements made via UPI, NEFT, or RTGS are frequently untracked against whether the vendor filed their taxes. Paying an unfiled vendor leaves the buyer with unclaimable tax losses.
- **The Solution:**
  - Connects to Account Aggregator (AA) feeds and bank statement records via `AccountAggregatorClient`.
  - Cross-reconciles: `Physical Bill` <-> `GSTR-2B Filing` <-> `Bank Payment Outflow`.
  - Classifications: `THREE_WAY_MATCHED`, `UNPAID_PURCHASE_VERIFIED`, `PAYMENT_WITHOUT_GSTR2B`.

---

## 6. Deterministic Rule Specification

To eliminate generative hallucinations in regulatory calculations, all tax compliance checks operate exclusively via deterministic Python code:

### 1. Indian GSTIN ISO/IEC 7064 Mod-36 Check-Digit Algorithm
A valid Indian GSTIN consists of 15 alphanumeric characters:
- Digits 1-2: State Code (`01` through `38`).
- Digits 3-12: 10-character Permanent Account Number (PAN) of the entity.
- Digit 13: Entity number of the PAN holder.
- Digit 14: Default character `Z`.
- Digit 15: Check digit computed via weighted alternating factors (1 and 2) over the Base-36 alphabet (`0-9`, `A-Z`).

### 2. Place of Supply Rules (Section 7, 8, 10 of IGST Act)
- **Intrastate Supply (`supplier_state == buyer_state`):** Requires equal 50/50 CGST+SGST with zero IGST.
- **Interstate Supply (`supplier_state != buyer_state`):** Requires IGST only with zero CGST/SGST.

### 3. Arithmetic Totals Cross-Check
- `sum(line_items.taxable_value) == taxable_amount` (tolerance: +/- 1.00 INR).
- `taxable_amount + cgst + sgst + igst == total_amount` (tolerance: +/- 1.00 INR).

### 4. Duplicate Invoice Guard
- Verifies that `(supplier_gstin, bill_number)` has not previously been recorded for the shop entity.

### 5. Double-Entry Balanced Ledger Engine
- Every transaction enforces exact mathematical parity: `abs(sum(debits) - sum(credits)) <= 0.01`.
- Standard Chart of Accounts (COA) ranges:
  - Assets: `1000 - 1999` (e.g., `1010 Cash`, `1020 Operating Bank Account`, `1030 Input Tax Credit Receivable`, `1040 Inventory`)
  - Liabilities: `2000 - 2999` (e.g., `2010 Accounts Payable`, `2020 GST Output Liability Payable`, `2030 Salary Payable`, `2040 Staff Advance Recovered`)
  - Equity: `3000 - 3999` (e.g., `3010 Owner Equity / Capital`, `3020 Retained Earnings`)
  - Revenue: `4000 - 4999` (e.g., `4010 Counter Sales Revenue`)
  - Expenses: `5000 - 5999` (e.g., `5010 Cost of Goods Sold`, `5020 Shop Rent`, `5030 Wages & Salaries`, `5040 Inventory Shrinkage Loss`)

### 6. FEFO Shelf-Life Horizon & RTV Debit Note Calculations
- Evaluates days to expiry: `days_remaining = (batch.expiry_date - today).days`.
  - `days_remaining < 0`: Status `EXPIRED` (immediate shelf pull).
  - `0 <= days_remaining <= 15`: Status `CRITICAL` (promotional clearance or urgent RTV).
  - `15 < days_remaining <= 45`: Status `WARNING` (prioritize in dispatch).
  - `days_remaining > 45`: Status `HEALTHY`.
- Return-to-Vendor Debit Note formula:
  - `Taxable Return Value = batch.quantity * unit_cost_price`
  - `Reversed GST (18%) = Taxable Return Value * 0.18`
  - `Total Debit Claim = Taxable Return Value + Reversed GST`
  - Auto-deducts returned batch units from book inventory immediately upon generation.

### 7. Dynamic Run-Rate Reordering Formulas
- `Average Daily Velocity (ADV) = sum(sales_quantities_over_lookback) / lookback_days`
- `Days Inventory Remaining (DIR) = current_stock / ADV`
- `Economic Order Quantity (EOQ) = sqrt((2 * annual_demand * order_cost) / holding_cost_per_unit)`
- Generates proactive PO drafts when `DIR < lead_time_days + safety_buffer_days`.

### 8. Physical Stock Shrinkage Sieve
- Discrepancy calculation: `discrepancy = physical_count - book_stock`.
- Triaging thresholds:
  - `discrepancy == 0`: `EXACT_MATCH`.
  - `abs(discrepancy) / book_stock <= 0.02`: `NORMAL_VARIANCE` (minor handling loss).
  - `0.02 < abs(discrepancy) / book_stock <= 0.08`: `SHRINKAGE_WARNING` (counter alert).
  - `abs(discrepancy) / book_stock > 0.08`: `SEVERE_LEAKAGE` (triggers mandatory supervisor investigation and posts loss to Account `5040 Inventory Shrinkage Loss`).

### 9. Dual-Tier Smart Attendance & Statutory Payroll Formulas
- **White-Collar Tier:**
  - Standard shift with 15-minute grace period (`check_in <= shift_start + 15m`).
  - Late-mark penalty rule: `penalty_days = floor(total_late_marks / 3) * 0.5`.
  - Leave balance debit waterfall: `Casual Leave (CL) -> Sick Leave (SL) -> Paid Leave (PL) -> Loss of Pay (LOP)`.
- **Blue-Collar Tier:**
  - Worked-hour rule:
    - `hours < 4.0`: `ABSENT` (0.0 day pay).
    - `4.0 <= hours < 7.0`: `HALF_DAY` (0.5 day pay).
    - `7.0 <= hours <= 9.0`: `FULL_DAY` (1.0 day pay).
    - `hours > 9.0`: `FULL_DAY` + Overtime hours at `1.5 * overtime_hourly_rate`.
- **Statutory Deductions & Advance Recoveries:**
  - `EPF Employee Share (12%)` on Basic Pay (if EPF eligible).
  - `ESIC Employee Share (0.75%)` on Gross Pay (if ESIC eligible).
  - `Udhari Recovery = min(active_advance_balance, net_payable_after_statutory)`.
- **Disbursement Balanced Journal Entry:**
  - `DR 5030 Wages & Salaries` = Gross Wages
  - `CR 1020 Operating Bank Account` = Total Net Payable Disbursed
  - `CR 2040 Staff Advance Recovered` = Total Advances Recovered
  - `CR 2050 Statutory EPF/ESIC Payable` = Total Employee Statutory Withholdings

---

## 7. Repository File Structure & Architecture Map

```
AssureFlow/
|-- .env.example                       # Template for environment configuration
|-- .gitignore                          # Git isolation definitions
|-- Dockerfile                          # Production container image definition
|-- docker-compose.yml                  # PostgreSQL and API service orchestrator
|-- requirements.txt                    # Python dependency manifest
|-- switch.template.yaml                # Declarative Switch agent and 3-room topology
|-- DEMO_SCRIPT.md                      # Complete 15-beat video recording script
|-- MUNIMJI_COMMERCIAL_ROADMAP.md       # Product roadmap & monetization strategy
|-- MUNIMJI_ENTERPRISE_IMPLEMENTATION_PLAN.md # Enterprise architectural specification
|-- README.md                           # Comprehensive architectural documentation
|
|-- scripts/
|   |-- generate_synthetic_bills.py     # Generates 18 realistic PDF & PNG invoices
|   |-- seed_database.py                # Initializes tenants, shops, users, staff, and invoices
|   |-- test_e2e_flow.py                # Automated dry run executing demo beats
|   `-- demo_switch_live.py             # 1-Click interactive terminal war-room runner (15 Beats)
|
|-- synthetic_data/
|   |-- bills_pdf/                      # Generated synthetic PDF tax invoices
|   |-- bills_img/                      # Rendered PNG images and blurry test cases
|   `-- ground_truth.json               # Canonical verification benchmark metadata
|
|-- src/
|   |-- config.py                       # Pydantic BaseSettings configuration loader
|   |
|   |-- auth/                           # Enterprise JWT Authentication & RBAC
|   |   |-- __init__.py
|   |   `-- jwt_handler.py              # Bcrypt hashing, JWT generation, decode & role checkers
|   |
|   |-- gsp/                            # GST Suvidha Provider (GSP) & Portal Feed
|   |   |-- __init__.py
|   |   |-- client.py                   # GSP client interface (Sandbox & Production)
|   |   `-- reconciler.py               # 2-Way GSTR-2B reconciler & Rule 37A notice generator
|   |
|   |-- accounts/                       # Bookkeeping & Double-Entry Accounting
|   |   |-- __init__.py
|   |   |-- double_entry.py             # Double-entry ledger, P&L, balance sheet, cashflow runway
|   |   |-- ledger.py                   # Automated expense categorizer and cashflow tracker
|   |   |-- bank_client.py              # Account Aggregator (AA) & bank statement ingestion
|   |   `-- three_way_recon.py          # Three-way cross-reconciliation (Bill <-> 2B <-> Bank)
|   |
|   |-- concierge/                      # Autonomous Vendor Dispute Concierge
|   |   |-- __init__.py
|   |   `-- vendor_dispute.py           # Tokenized vendor dispute URLs & multi-room resolution
|   |
|   |-- voice/                          # Wispr Flow Voice Ingestion Subsystem
|   |   |-- __init__.py
|   |   `-- voice_transcriber.py        # Spoken Hinglish audio notes parser & dispatcher
|   |
|   |-- ai/                             # Gemini AI Integration & Multimodal Vision
|   |   |-- __init__.py
|   |   `-- gemini_client.py            # Multimodal bill extractor & conversational advisor
|   |
|   |-- notifications/                  # Proactive Alerts & Deadline Subsystem
|   |   |-- __init__.py
|   |   `-- alert_engine.py             # GST 20th countdown & low stock alerts
|   |
|   |-- advisory/                       # Junior CA Tax Advisory & Audit Radar
|   |   |-- __init__.py
|   |   |-- tax_advisor.py              # Section 44AD, Section 32, Section 17(5), 80C/80D
|   |   `-- audit_radar.py              # DGGI Audit Risk Index & Supplier Risk Scorecards
|   |
|   |-- inventory/                      # Store Inventory & Auto-Restock Subsystem
|   |   |-- __init__.py
|   |   `-- service.py                  # FEFO expiry, RTV debit notes, dynamic POs, shrinkage audits
|   |
|   |-- staff/                          # Store Staff Attendance & Payroll Subsystem
|   |   |-- __init__.py
|   |   `-- service.py                  # Dual-tier attendance, late marks, overtime, udhari, payout batches
|   |
|   |-- users/                          # User Profiles & RBAC Engine
|   |   |-- __init__.py
|   |   |-- rbac.py                     # Permission boundaries and role data filtering
|   |   `-- service.py                  # User profile authentication and management
|   |
|   |-- dashboard/                      # Visual Cockpit & 3-Room Switch Simulator
|   |   |-- __init__.py
|   |   `-- router.py                   # Cockpit & `/switch-simulator` 3-column war-room (8 Interactive Beats)
|   |
|   |-- agents/                         # Multi-Agent Conversational Logic
|   |   |-- __init__.py
|   |   |-- bill_reader.py              # Visual extraction and confirmation agent
|   |   |-- gst_checker.py              # Deterministic rule compliance router
|   |   |-- follow_up.py                # Shop owner risk communicator
|   |   |-- store_manager.py            # Inventory, attendance, briefing & payroll agent
|   |   |-- junior_ca.py                # Conversational Junior CA & Bookkeeper
|   |   `-- return_preparer.py          # CA cockpit and GSTR return aggregator
|   |
|   |-- api/                            # FastAPI REST Service Layer
|   |   |-- __init__.py
|   |   |-- main.py                     # Application entry point, CORS & exception handler
|   |   |-- routes_auth.py              # Tenant registration, JWT login, and profile lookup
|   |   |-- routes_concierge.py         # Autonomous vendor dispute & multi-room resolution
|   |   |-- routes_voice.py             # Wispr voice transcription and audio intake
|   |   |-- routes_gsp.py               # GSTR-2B feed sync, 2-way match, supplier notices
|   |   |-- routes_bank.py              # Bank statement ingestion, 3-way match, status
|   |   |-- routes_shops.py             # Shop registration and profile management
|   |   |-- routes_bills.py             # Multipart upload, audit, and confirmation
|   |   |-- routes_issues.py            # Compliance issue triaging and CA actions
|   |   |-- routes_summary.py           # GSTR reconciliation summaries & GSTR-3B JSON exports
|   |   |-- routes_advisory.py          # Double-entry ledger, P&L, balance sheet, cashflow runway
|   |   |-- routes_inventory.py         # FEFO reports, RTV debit notes, dynamic POs, shrinkage audits
|   |   |-- routes_staff.py             # Smart attendance, crew check-in, advances, payout batches
|   |   |-- routes_notifications.py     # Proactive deadline and stock alerts endpoints
|   |   `-- routes_users.py             # User profile and role lookup routes
|   |
|   |-- db/                             # Persistence Layer
|   |   |-- __init__.py
|   |   |-- session.py                  # SQLAlchemy session lifecycle management
|   |   |-- init_db.py                  # Schema creation and migration utilities
|   |   `-- models.py                   # Relational models (Tenant, Shop, Bill, Bank, Journal, Batches, etc.)
|   |
|   |-- extraction/                     # Document Intake Pipeline
|   |   |-- __init__.py
|   |   |-- document_classifier.py      # "Kacha-Pakka" Sieve (Pakka Invoice vs Kacha Slip)
|   |   |-- pdf_extractor.py            # Native PyMuPDF text stream extraction
|   |   `-- parser.py                   # Structured heuristic parser and blur detector
|   |
|   |-- gst_engine/                     # Deterministic Regulatory Core
|   |   |-- __init__.py
|   |   |-- checksum.py                 # ISO/IEC 7064 Mod-36 check-digit logic
|   |   |-- rules.py                    # Place of supply, math checks, and state codes
|   |   `-- validator.py                # Comprehensive compliance audit coordinator
|   |
|   `-- switch_bridge/                  # Platform & Chat Bridge Connectors
|       |-- __init__.py
|       |-- webhook_handler.py          # Multi-room event and command router
|       |-- whatsapp_webhook.py         # Meta WhatsApp Cloud API webhook receiver & buttons
|       `-- telegram_bot.py             # Standalone long-polling Telegram daemon
|
`-- tests/                              # Comprehensive Automated Test Suite (138 Tests Passed across 35 Test Suites)
    |-- __init__.py
    |-- conftest.py                     # Database initialization test fixtures
    |-- test_smart_inventory.py         # FEFO expiry, RTV debit notes, dynamic POs, shrinkage audits (5 tests)
    |-- test_double_entry_accounting.py # Balanced journaling, Trial Balance, P&L, Cashflow runway (5 tests)
    |-- test_smart_attendance_and_hr.py # White/blue collar attendance, late marks, overtime, udhari, payout (6 tests)
    |-- test_api_advisory.py            # Financial statements & treasury API endpoint tests (4 tests)
    |-- test_kacha_pakka_sieve.py       # "Kacha-Pakka" Smart Sieve & quarantine tests
    |-- test_vendor_concierge.py        # Autonomous Vendor Dispute Concierge tests
    |-- test_audit_radar.py             # DGGI Audit Radar & Supplier Scorecard tests
    |-- test_voice_workflow.py          # Wispr Hinglish voice ingestion & dispatch tests
    |-- test_switch_simulator.py        # 3-Room Switch War-Room Simulator & Live Runner tests
    |-- test_enterprise_auth.py         # Tenant registration, JWT, bcrypt, and RBAC tests
    |-- test_two_way_reconciliation.py  # GSP client, GSTR-2B two-way match, Rule 37A notices
    |-- test_three_way_bank_recon.py    # Account Aggregator statement & 3-way match tests
    |-- test_whatsapp_webhook.py        # Meta WhatsApp challenge, HMAC-SHA256, and buttons
    |-- test_ai_gemini.py               # Gemini client and fallback test cases
    |-- test_env.py                     # Environment and dependency verification
    |-- test_gst_checksum.py            # ISO 7064 Mod-36 algorithm test cases
    |-- test_gst_rules.py               # Place of supply and tax split verification
    |-- test_dataset.py                 # Synthetic invoice dataset integrity tests
    |-- test_db_models.py               # Relational persistence and schema tests
    |-- test_extraction.py              # PDF extraction and blur detection tests
    |-- test_api_bills.py               # Bill upload, confirmation, and decision API tests
    |-- test_issue_routing.py           # Agent message and routing tests
    |-- test_switch_bridge.py           # Switch room routing tests
    |-- test_accounts_ledger.py         # Bookkeeping and expense categorization tests
    |-- test_tax_advisory.py            # Section 44AD and depreciation advisory tests
    |-- test_junior_ca_agent.py         # Junior CA agent dialogue tests
    |-- test_rbac_profiles.py           # RBAC permissions and role filtering tests
    |-- test_inventory_management.py    # Auto-restock and low-stock reorder tests
    |-- test_staff_attendance.py        # Staff roster, attendance, and payroll tests
    |-- test_store_manager_agent.py     # Store Manager agent response formatting tests
    |-- test_api_manager_suite.py       # Manager REST API endpoints test suite
    |-- test_natural_language_queries.py# Freeform Hindi & English NL query routing
    |-- test_notifications.py           # Proactive deadline and stock alerts engine tests
    |-- test_gstr3b_export.py           # Official government GSTR-3B schema export tests
    `-- test_telegram_bot.py            # Telegram runner command and mock tests
```

---

## 8. Complete REST API Specification

| Category | Method | Endpoint | Description | Key Parameters / Payload |
| :--- | :--- | :--- | :--- | :--- |
| **Switch & War-Room** | `GET` | `/switch-simulator` | Interactive 3-Room Switch War-Room Simulator | None |
| **Smart Inventory** | `POST` | `/api/inventory/{shop_id}/batch` | Create or update item batch | `{ "sku": str, "batch_number": str, "quantity": float, "expiry_date": str }` |
| | `GET` | `/api/inventory/{shop_id}/fefo-report` | FEFO horizon report & RTV alerts | Path: `shop_id` |
| | `POST` | `/api/inventory/{shop_id}/rtv-debit-note` | Issue Return-to-Vendor Debit Note | `{ "batch_id": str, "reason": str }` |
| | `GET` | `/api/inventory/{shop_id}/dynamic-reorder` | Dynamic run-rate replenishment POs | Path: `shop_id`, Query: `lookback_days` |
| | `POST` | `/api/inventory/{shop_id}/audit-stock` | Physical stock audit & shrinkage check | `{ "sku": str, "physical_count": float, "reason": str }` |
| | `GET` | `/api/inventory/{shop_id}/price-opportunity` | Supplier purchase price variance | Path: `shop_id`, Query: `sku`, `latest_cost` |
| **Smart Accounting** | `POST` | `/api/advisory/double-entry/{shop_id}/sync-bills` | Auto-post purchase bills to journal | Path: `shop_id` |
| | `GET` | `/api/advisory/double-entry/{shop_id}/trial-balance` | Balanced Trial Balance | Path: `shop_id` |
| | `GET` | `/api/advisory/double-entry/{shop_id}/profit-loss` | Monthly Trading & P&L Statement | Path: `shop_id` |
| | `GET` | `/api/advisory/double-entry/{shop_id}/balance-sheet` | Full Balance Sheet (Assets = Liab + Eq) | Path: `shop_id` |
| | `GET` | `/api/advisory/treasury/{shop_id}/cash-flow-forecast` | 30-Day Cash Runway & Safety Index | Path: `shop_id` |
| | `GET` | `/api/advisory/treasury/{shop_id}/vendor-payment-priority` | GSTR-Optimized Payment Priority Queue | Path: `shop_id` |
| **Smart HR & Payroll** | `POST` | `/api/staff/{shop_id}/smart-attendance` | Smart check-in/out, late marks & OT | `{ "employee_id": str, "date": str, "check_in_time": str, "check_out_time": str }` |
| | `POST` | `/api/staff/{shop_id}/crew-checkin` | 1-Click Blue-Collar Crew Check-in | `{ "date": str, "present_employee_ids": list[str] }` |
| | `POST` | `/api/staff/{shop_id}/regularize` | Regularize missed punch-out | `{ "employee_id": str, "date": str, "reason": str }` |
| | `GET` | `/api/staff/{shop_id}/shift-understaffing` | Shift understaffing alert check | Path: `shop_id`, Query: `date`, `shift_name` |
| | `POST` | `/api/staff/{shop_id}/advances` | Issue cash advance / udhari | `{ "employee_id": str, "amount": float, "notes": str }` |
| | `GET` | `/api/staff/{shop_id}/advances` | List active cash advances | Path: `shop_id` |
| | `GET` | `/api/staff/{shop_id}/smart-payroll` | Dual-Tier Smart Payroll Breakdown | Path: `shop_id`, Query: `month`, `year` |
| | `POST` | `/api/staff/{shop_id}/payout-batch` | Generate bulk bank payout batch | `{ "month": int, "year": int }` |
| | `POST` | `/api/staff/payout-batch/{batch_id}/approve` | Approve payout batch & post journal | `{ "approved_by": str }` |
| **Dispute Concierge** | `GET` | `/api/concierge/disputes/{shop_id}` | Fetch active supplier dispute records | Path: `shop_id` |
| | `POST` | `/api/concierge/create-dispute` | Generate tokenized supplier dispute link | `{ "issue_id": str, "supplier_gstin": str, "amount_at_risk": float }` |
| | `POST` | `/api/concierge/resolve` | Resolve dispute & broadcast to rooms | `{ "token": str, "action": "AMEND_GSTR1" \| "ISSUE_CREDIT_NOTE" }` |
| **Wispr Voice Intake** | `POST` | `/api/voice/process-text` | Ingest voice transcription text | `{ "shop_id": str, "transcription": str }` |
| | `POST` | `/api/voice/upload-audio` | Ingest raw voice audio file | Form: `shop_id`, `file` (Multipart audio) |
| **Audit Radar** | `GET` | `/api/advisory/audit-radar/{shop_id}` | DGGI Audit Risk Index & Supplier Scorecard | Path: `shop_id` |
| **Auth & Multi-Tenancy** | `POST` | `/api/auth/register` | Register new tenant organization and admin | `{ "tenant_name": str, "admin_email": str, "admin_password": str }` |
| | `POST` | `/api/auth/login` | Authenticate user and issue JWT bearer token | `{ "email": str, "password": str }` |
| | `GET` | `/api/auth/me` | Fetch authenticated user profile & tenant info | Header: `Authorization: Bearer <token>` |
| **GSP & 2-Way Recon** | `POST` | `/api/gsp/sync-gstr2b` | Ingest inward GSTR-2B portal records | `{ "shop_id": str, "return_period": str }` |
| | `POST` | `/api/gsp/reconcile` | Run two-way match (Physical vs Portal) | `{ "shop_id": str, "return_period": str }` |
| | `GET` | `/api/gsp/reconciliation-summary/{shop_id}` | Quantitative GSTR-2B reconciliation report | Path: `shop_id`, Query: `return_period` |
| | `GET` | `/api/gsp/supplier-notices/{shop_id}` | Fetch generated Rule 37A supplier notices | Path: `shop_id` |
| **Bank & 3-Way Recon** | `POST` | `/api/bank/ingest-statement` | Ingest bank statement / AA feed | `{ "shop_id": str, "transactions": Optional[list] }` |
| | `POST` | `/api/bank/three-way-reconcile` | Run three-way match (Bill <-> 2B <-> Bank) | `{ "shop_id": str }` |
| | `GET` | `/api/bank/recon-status/{shop_id}` | Summary of settled vs unreconciled debits | Path: `shop_id` |
| **WhatsApp Cloud API** | `GET` | `/api/whatsapp/webhook` | Meta Cloud API webhook verification handshake | Query: `hub.mode`, `hub.verify_token`, `hub.challenge` |
| | `POST` | `/api/whatsapp/webhook` | Process WhatsApp receipts, buttons, queries | Header: `X-Hub-Signature-256`, Payload: Meta JSON |
| **Cockpit & Dashboard** | `GET` | `/health` | Service health status | None |
| | `GET` | `/dashboard` | Interactive HTML visual cockpit | Query: `shop_id`, `role` |
| | `GET` | `/api/dashboard/metrics/{shop_id}` | Role-filtered cockpit telemetry | Path: `shop_id`, Query: `role` |
| **Bill Processing** | `POST` | `/api/bills/upload` | Ingest bill photo/PDF, run checks | Form: `shop_id`, `file` (Multipart) |
| | `POST` | `/api/bills/{bill_id}/confirm` | Confirm or correct extracted details | `{ "confirmed": bool, "corrected_total": Optional[float] }` |
| **Compliance & CA** | `GET` | `/api/issues` | Query compliance defects | Query: `shop_id`, `severity`, `ca_action` |
| | `POST` | `/api/issues/{issue_id}/decision` | Record CA review decision | `{ "action": "approve" \| "reject" \| "ask_supplier" }` |
| | `GET` | `/api/summary/{shop_id}/export` | Export GSTR JSON (`format=gstr3b` or `summary`) | Path: `shop_id`, Query: `format` |

---

## 9. Chat Commands & Room Interaction Guide

### In Private Shop Rooms (`shop-sharma-kirana` or WhatsApp)
- **Upload File:** Drop any bill photo, PDF, or kacha estimate slip. `bill-reader` classifies the document, extracts data, and displays confirmation previews.
- **`OK`**: Confirms invoice details into the filing queue **AND automatically triggers auto-restock** via `store-manager`.
- **`/fefo_expiry_check`**: `store-manager` displays FEFO batch shelf life, flags expiring items, and issues Return-to-Vendor Debit Notes (`DN-RTV`).
- **`/audit_stock [sku] [count]`**: `store-manager` audits physical counts against book inventory, triaging shrinkage discrepancies.
- **`/financials`**: `junior-ca` outputs the balanced Trial Balance, P&L Net Profit, and Balance Sheet.
- **`/runway`**: `junior-ca` reports the 30-day Cash Flow Runway and Liquidity Safety Index.
- **`/stock`**: `store-manager` displays real-time inventory health (total SKUs, low-stock warnings, depleted items).
- **`/reorder`**: `store-manager` generates an automated procurement reorder sheet with suggested quantities and estimated costs.
- **`/attendance`**: `store-manager` displays today's staff roster, attendance summary, and shift briefing.
- **`/checkin [name] [status]`**: `store-manager` logs employee check-in (Present, Absent, Half-Day, Leave).
- **`/crew_checkin`**: 1-click roster check-in for the entire blue-collar floor team.
- **`/advance [name] [amount]`**: Logs an udhari cash advance to an employee ledger.
- **`/payroll [YYYY-MM]`**: `store-manager` calculates monthly staff payroll wage disbursal based on actual attendance days.
- **`/shift_summary`**: `store-manager` outputs the morning operational briefing and procurement alerts.
- **`/khata` or `/accounts`**: `junior-ca` displays the current month's Accounts Book (Mal Kharid, Operating Expenses, Capital Assets, Total Outflow).
- **`/tax_savings`**: `junior-ca` suggests Section 32 asset depreciation and proprietor personal tax deductions (80C, 80D, NPS).
- **`/presumptive [turnover] [digital_pct]`**: `junior-ca` computes Section 44AD deemed profit and estimated tax savings.
- **`/alerts`**: `follow-up` reports pending GST filing deadlines (countdown to the 20th), disputed ITC at risk, and depleted stock warnings.
- **Wispr Voice Notes:** Send conversational Hinglish or English audio notes (e.g., *"12 bori Aashirvaad Atta delivery aayi"*, *"Poori loading team present hai siwaye Mukesh ke, aur Chandan ko 1500 advance diya"*). The voice transcriber dispatches stock updates, attendance, or advances immediately.

### In CA Office Room (`ca-office`)
- **`/dashboard`**: `return-preparer` lists high-level compliance status across all client shops.
- **`/summary [shop_id]`**: `return-preparer` generates complete month-end GSTR report with eligible ITC breakdown.
- **`/approve [bill_id]`**: Overrides compliance defect, retaining invoice in the filing pool.
- **`/reject [bill_id]`**: Disallows invoice, excluding it from GSTR-3B tax credit pool.
- **`/ask_supplier [bill_id]`**: Generates Section 16(2) compliance notice and opens a dispute in the Vendor Dispute Desk.
- **`/priority_queue`**: Lists suppliers ranked by GSTR-2B compliance status for payment authorization.

### In Vendor Dispute Desk (`vendor-dispute-desk`)
- **Interactive Dispute Resolution:** Defaulting suppliers receive tokenized links and resolve compliance discrepancies with single clicks:
  - `AMEND_GSTR1`: Vendor commits to amending the outward filing in the next GSTR-1 cycle.
  - `ISSUE_CREDIT_NOTE`: Vendor issues a formal GST Credit Note for the disputed tax difference.
- **Multi-Room Broadcast:** Upon resolution, automated notifications alert both the merchant room and the CA office.

---

## 10. One-Command Setup & Execution

### Option A: Local Python Environment (Recommended for Evaluation)

```cmd
# 1. Clone repository
git clone https://github.com/SaurabhTomar123/AssureFlow.git
cd AssureFlow

# 2. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Generate synthetic dataset (18 bills) and seed database (tenants, shops, users, staff, inventory)
python scripts/generate_synthetic_bills.py
python scripts/seed_database.py

# 5. Run full automated end-to-end demo dry run
python scripts/test_e2e_flow.py

# 6. Run complete test suite (138 automated unit and integration tests across 34 test suites)
pytest

# 7. Run 1-Click Interactive Terminal War-Room Playback (All 15 beats with colorized agent handoffs)
python scripts/demo_switch_live.py

# 8. Launch FastAPI server and view interactive Visual Cockpit and 3-Room Switch Simulator
uvicorn src.api.main:app --reload --port 8000
# Open in browser: http://localhost:8000/switch-simulator
# Open Cockpit:   http://localhost:8000/dashboard
```

### Option B: Interactive 3-Room Switch War-Room Simulator
1. Start the server: `uvicorn src.api.main:app --reload --port 8000`
2. Open `http://localhost:8000/switch-simulator` in any browser.
3. Observe the 3-column split view (`shop-sharma-kirana`, `ca-office`, `vendor-dispute-desk`).
4. Click the interactive simulation beats (Beats 1 through 8) to see real-time cross-room messaging, dispute resolution, voice notes, FEFO expiry debit notes, double-entry financial statements, and crew payout approvals.

### Option C: Live Telegram Bot Deployment
To connect live Telegram groups for smartphone photo drops:
1. Message `@BotFather` on Telegram to generate a Bot Token.
2. Add your token to `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=your_token_here
   ```
3. Run the long-polling runner:
   ```cmd
   python src/switch_bridge/telegram_bot.py
   ```

### Option D: Live Meta WhatsApp Cloud API Setup
1. In Meta for Developers console, configure a WhatsApp Business Cloud App.
2. Set Webhook URL to: `https://your-public-domain.com/api/whatsapp/webhook`.
3. Set Verify Token to: `munimji_meta_verify_token_2026` (or configure via `WHATSAPP_VERIFY_TOKEN`).
4. Subscribe to the `messages` event field.

### Option E: Docker Compose (PostgreSQL + FastAPI)
```cmd
docker-compose up --build
```

---

## 11. Regulatory Philosophy: "AI Prepares, CA Files"

MunimJi never submits filings directly to the GST Network portal. The AI agents and deterministic engines extract, validate, and organize the ledger; the licensed Chartered Accountant reviews the final summary and files the official return.
