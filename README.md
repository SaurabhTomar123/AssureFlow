# MunimJi (AssureFlow) — Autonomous Multi-Agent GST, Store Operations & Commercial Bookkeeping Platform

> **Track:** Autonomous Multi-Agent Enterprise Workflows & Compliance  
> **Core Operating Principle:** AI reads and advises, code checks, human decides.  
> **Synthetic Data Notice:** All invoices, merchant entities, taxpayer profiles, employee rosters, and GSTIN identifiers in this project are 100% synthetic.

---

## 1. Executive Summary & Problem Context

In India, over 63 million Micro, Small, and Medium Enterprises (MSMEs) face severe operational and compliance bottlenecks approaching the monthly Goods and Services Tax (GST) filing deadline (GSTR-3B / GSTR-1). Retailers, distributors, and shopkeepers accumulate crumpled physical paper receipts, thermal counter slips, and digital PDF invoices throughout the month. At month-end, these are dumped onto their Chartered Accountants (CAs).

Simultaneously, retail shop owners struggle with daily store management and multi-party reconciliation:
1. **Input Tax Credit (ITC) Leakage:** Invalid or mismatched GSTINs prevent merchants from claiming legal tax credits under Section 16(2) of the CGST Act.
2. **Tax Classification Errors:** Inadvertently charging Intrastate taxes (CGST + SGST) on Interstate shipments, or charging Integrated GST (IGST) within the same state, resulting in rejected returns.
3. **Supplier Default Risk (Section 16(2)(aa) & Rule 37A):** Physical bills paid to vendors are disallowed if the supplier fails to upload the invoice in GSTR-1, causing surprise ITC reversals and mandatory 18% Section 50 interest penalties.
4. **Three-Way Cash Disconnect:** Accounting books, government GSTR-2B portal feeds, and bank account debit statements operate in silos, making vendor payment verification and tax audit preparation an excruciating manual task.
5. **Absence of Real-Time Bookkeeping:** Small proprietors lack continuous bookkeeping, missing out on statutory tax deductions (Section 32 depreciation, Section 44AD presumptive taxation, and Section 80C/80D personal deductions).
6. **Disconnected Inventory & Procurement:** Invoices are filed for taxes but never linked to inventory stock balances, leading to stockouts and manual reorder sheets.
7. **Manual Staff Attendance & Payroll Calculation:** Store managers track staff attendance on paper registers, leading to wage calculation disputes and opaque shift handovers.
8. **Lack of Enterprise Multi-Tenancy & RBAC:** Multi-store owners and CA practices need robust multi-tenancy with JWT authentication and strict access boundaries between store staff, managers, and accountants.

**MunimJi** solves this by establishing an autonomous, multi-agent enterprise workflow orchestrated via **Switch** and **Meta WhatsApp Cloud API**, backed by deterministic verification engines, an automated Store Manager subsystem, live GSTR-2B two-way reconciliation, Account Aggregator three-way bank matching, and a full Junior CA bookkeeping suite.

---

## 2. Multi-Room Isolation & System Architecture

MunimJi decouples shop-level intake, store operations, bank reconciliations, and CA-level tax oversight through strict multi-room and multi-tenant isolation:

```
+-----------------------------------------------------------------------------------------------+
|                       MULTI-CHANNEL COLLABORATION & INTAKE PLATFORM                           |
|                                                                                               |
|  +-------------------------------+                               +-------------------------+  |
|  |    Shop Room 1 (Private)      |                               | CA Office Room (Shared) |  |
|  |    - Shop Owner Sharma        |                               | - Chartered Accountant  |  |
|  |    - Store Manager Ramesh     |                               | - GST Checker Agent     |  |
|  |    - Bill Reader Agent        |                               | - Return Preparer Agent |  |
|  |    - Store Manager Agent      |                               +------------+------------+  |
|  |    - Follow-up Agent          |                                            |               |
|  |    - Junior CA Agent          |                                            |               |
|  +---------------+---------------+                                            |               |
|                  |                                                            |               |
|  +---------------+---------------+   +------------------------------------+   |               |
|  |    Shop Room 2 (Private)      |   | Meta WhatsApp Cloud API Gateway    |   |               |
|  |    - Shop Owner Gupta         |   | - Photo Receipts & Documents       |   |               |
|  |    - Bill Reader Agent        |   | - Interactive Quick-Reply Buttons  |   |               |
|  |    - Store Manager Agent      |   | - Natural Language Queries         |   |               |
|  +---------------+---------------+   +-----------------+------------------+   |               |
+------------------|-------------------------------------|----------------------|---------------+
                   |                                     |                      |
                   v                                     v                      v
+-----------------------------------------------------------------------------------------------+
|                                FASTAPI ENTERPRISE CORE ENGINE                                 |
|                                                                                               |
|  +---------------------------+   +-----------------------+   +-----------------------------+  |
|  | Multi-Tenancy & Security  |   | Rule-Based GST Engine |   | Issue Routing & Decision    |  |
|  | - JWT Bearer Tokens       |-->| - Mod-36 Check-Digit  |-->| - Simple vs Serious Flags   |  |
|  | - Tenant & User Isolation |   | - Place of Supply     |   | - ITC Rupee Value at Risk   |  |
|  | - RBAC Guard & Checkers   |   | - Duplicate Guard     |   +--------------+--------------+  |
|  +---------------------------+   +-----------------------+                  |                 |
|                                                                             |                 |
|  +---------------------------+   +-----------------------+   +--------------v--------------+  |
|  | Store Operations Engine   |   | Junior CA Tax Advisor |   | GSP & Bank Reconciliation   |  |
|  | - Auto-Restock from Bill  |   | - Section 44AD Presump|   | - 2-Way GSTR-2B Auto-Recon  |  |
|  | - Low Stock Reorder Sheet |   | - Section 32 Deprec.  |   | - Rule 37A Supplier Notices |  |
|  | - Shift Briefing & Roster |   | - 80C / 80D / 80CCD   |   | - 3-Way Bank Outflow Match  |  |
|  | - Attendance & Payroll    |   | - 17(5) Blocked ITC   |   | - Account Aggregator Feeds  |  |
|  +---------------------------+   +-----------------------+   +-----------------------------+  |
+-----------------------------------------------------------------------------|-----------------+
                                                                              v
+-----------------------------------------------------------------------------------------------+
|                              PERSISTENCE & RECONCILIATION LAYER                               |
|                                                                                               |
|  [ tenants ] <---> [ organization_users ] <---> [ audit_logs ]                                |
|      |                                                                                        |
|      +-----------> [ shops ] <---- [ bills ] <---- [ bill_items ] <---- [ compliance_issues ]  |
|                        |               |                                                      |
|                        |               +-----------> [ stock_movements ] <--- [ items ]       |
|                        |                                                                      |
|                        +-----------> [ employees ] <---- [ attendance ] <---- [ payroll ]     |
|                        |                                                                      |
|                        +-----------> [ gstr2b_inward_records ] (Portal Feeds & Statuses)       |
|                        |                                                                      |
|                        +-----------> [ bank_transactions ] (UPI / NEFT / RTGS Debits)         |
|                        |                                                                      |
|                        +-----------> [ ledger_entries ] (Expense Categorization & Cashflows)   |
+-----------------------------------------------------------------------------------------------+
```

### Access Control & Privacy Guarantees
- **Private Shop Rooms (`shop-sharma-kirana`, `shop-gupta-electronics`)**: Every shop operates in a distinct chat room. Competitors never observe each other's purchase volumes, supplier identities, inventory counts, or financial margins.
- **Shared CA Office Room (`ca-office`)**: Serves as the central practice management cockpit for the Chartered Accountant. Aggregates only serious compliance flags and high-level return preparation metrics across all managed client shops.
- **Enterprise Multi-Tenancy**: Organization users are authenticated via JWT Bearer tokens with strict tenant scoping (`tenant_id`). User actions and audits are tracked in `audit_logs`.
- **Role-Based Filtering (RBAC)**: The `/dashboard` interactive visual cockpit automatically filters data based on the user's role profile (`TENANT_ADMIN`, `STORE_MANAGER`, `JUNIOR_CA`, `SENIOR_CA`, `STORE_STAFF`). Staff never see sensitive profit margins or personal tax advice.

---

## 3. Autonomous Agents & Specialized Roles

### 1. `bill-reader` (Stationed in Shop Rooms & WhatsApp Bridge)
- **Role:** Document intake and multimodal visual extraction.
- **Behavior:** Automatically acknowledges uploaded invoices (PDFs or camera images), extracts structured fields (supplier name, GSTIN, invoice number, invoice date, line items, taxable values, CGST, SGST, IGST, total amount), and posts a structured preview requesting merchant confirmation (`OK` or textual corrections). Supports English and Hindi/Hinglish.

### 2. `gst-checker` (Deterministic Rule Auditor)
- **Role:** Regulatory math and legal format auditor.
- **Behavior:** Evaluates every confirmed invoice against strict Indian statutory standards:
  - Validates GSTIN check-digit using ISO/IEC 7064 Mod-36 algorithm.
  - Verifies Place of Supply (Intrastate requires equal 50/50 CGST+SGST with zero IGST; Interstate requires IGST only with zero CGST/SGST).
  - Cross-checks arithmetic totals within 1.0 INR round-off tolerance.
  - Detects duplicate invoices against existing historical ledgers.
  - Triages findings into `simple` issues (handled locally in the shop room) and `serious` issues (routed to the CA office).

### 3. `follow-up` (Stationed in Shop Rooms & WhatsApp Bridge)
- **Role:** Merchant communication and ITC risk alerter.
- **Behavior:** Handles simple defects (blurry captures, missing supplier GSTIN). Translates regulatory errors into actionable business terms, explicitly calculating the **exact Rupee amount of Input Tax Credit at risk**. Sends automated countdown reminders approaching tax filing deadlines.

### 4. `store-manager` (Stationed in Shop Rooms)
- **Role:** Inventory replenishment, staff attendance, shift briefings, and payroll.
- **Behavior:**
  - **Auto-Restock:** When a purchase bill is confirmed with `OK` (or via WhatsApp quick reply), automatically creates or increments inventory balances and records `IN_PURCHASE` stock movements.
  - **Stock Health Overview (`/stock`):** Reports total catalog SKUs, healthy stock levels, low-stock alerts, and out-of-stock items.
  - **Replenishment Reorder Sheet (`/reorder`):** Generates an itemized procurement sheet with suggested order quantities and estimated wholesale purchase costs.
  - **Daily Shift Briefing (`/shift_summary` or `/attendance`):** Morning operational briefing showing staff on duty, absent staff, incoming purchase deliveries, and low stock warnings.
  - **Staff Check-in (`/checkin [name] [status]`):** Logs daily attendance (Present, Absent, Half-Day, Leave) with check-in timestamps.
  - **Monthly Payroll (`/payroll [YYYY-MM]`):** Computes monthly pro-rata wage disbursements based on actual present days and monthly base salaries.

### 5. `junior-ca` (Stationed in Shop Rooms)
- **Role:** Real-time bookkeeping and proactive tax optimization.
- **Behavior:**
  - Maintains the merchant's digital **Accounts Book (`/khata`)**, categorizing expenses into inventory purchases, operating expenses, capital assets, and logistics.
  - Analyzes eligibility for **Section 44AD Presumptive Taxation** (deemed taxable profit of 6% for digital receipts / 8% for cash receipts), quantifying tax savings and statutory audit exemptions.
  - Calculates **Section 32 Asset Depreciation** write-offs (40% for technology assets, 15% for commercial machinery).
  - Identifies **Section 17(5) Blocked ITC** on food, catering, and personal expenses before GSTR-3B submission.
  - Formulates personal tax optimization roadmaps (**Section 80C**, **80D**, and **NPS 80CCD(1B)**).

### 6. `return-preparer` (Stationed in CA Office Room)
- **Role:** Practice management coordinator and GSTR aggregator.
- **Behavior:** Presents serious compliance defects to the CA with single-click decisions (`/approve`, `/reject`, `/ask_supplier`). Automatically generates legally grounded Section 16(2) compliance notices for non-compliant suppliers. Generates monthly GSTR reconciliation summaries with eligible ITC breakdowns and downloadable JSON audit files.

---

## 4. Live GSP Two-Way & Account Aggregator Three-Way Match Engines

### Two-Way GSTR-2B Auto-Reconciliation
*   **The Problem:** Under Section 16(2)(aa) of the CGST Act, a buyer is legally barred from claiming Input Tax Credit unless the supplier files GSTR-1 and the invoice appears in the buyer's auto-drafted GSTR-2B. Under GST Rule 37A, failure to reconcile causes mandatory ITC reversal with 18% interest.
*   **The Solution:**
    *   `GSPClient` syncs live portal inward returns.
    *   The matching engine compares physical purchase bills in books against portal records.
    *   Classifications:
        *   `RECON_MATCHED`: Taxable values and tax claims match within tolerance (+/- Rs 2).
        *   `RECON_TAX_MISMATCH`: Supplier filed return with lower tax than billed; flags tax difference at risk.
        *   `SUPPLIER_DEFAULT`: Physical invoice exists in books, but supplier never filed in GSTR-1.
        *   `UNRECORDED_PURCHASE`: Invoice filed by supplier in portal, but shop staff forgot to enter the bill in MunimJi (unclaimed ITC opportunity).
    *   **Rule 37A Demand Notices:** Automatically drafts formal legal notices to defaulting vendors demanding return amendment before payment release.

### Three-Way Bank Reconciliation Engine
*   **The Problem:** Vendor disbursements made via UPI, NEFT, or RTGS are frequently untracked against whether the vendor filed their taxes. Paying an unfiled vendor leaves the buyer with unclaimable tax losses.
*   **The Solution:**
    *   Connects to Account Aggregator (AA) feeds and bank statement records via `AccountAggregatorClient`.
    *   Cross-reconciles: `Physical Bill` <-> `GSTR-2B Filing` <-> `Bank Payment Outflow`.
    *   Classifications:
        *   `THREE_WAY_MATCHED`: Billed in books, verified in GSTR-2B, and settled via bank. (Audit-proof).
        *   `UNPAID_PURCHASE_VERIFIED`: Confirmed in GSTR-2B, awaiting bank disbursement. (Safe Accounts Payable).
        *   `PAYMENT_WITHOUT_GSTR2B`: Payment disbursed to supplier, but vendor failed to file return. Generates critical CA alert and halts future disbursements.

---

## 5. Meta WhatsApp Business Cloud API Gateway

Shop owners and floor managers can operate MunimJi directly from WhatsApp:
*   **Webhook Handshake:** Secure verification endpoint (`hub.mode == subscribe`, `hub.verify_token`).
*   **Cryptographic Security:** HMAC-SHA256 signature verification via `X-Hub-Signature-256` using the WhatsApp App Secret.
*   **Interactive Action Buttons:** Quick-reply buttons allowing owners to approve or reject bills on the move (`[Approve Bill]` triggers auto-restock).
*   **Multimedia Receipt Ingestion:** Direct camera snapshots and PDF invoices sent via WhatsApp are automatically ingested, parsed, checked for compliance, and restocked.
*   **Conversational Assistant:** Freeform text messages route directly to Junior CA or Store Manager agents.

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
- **Intrastate Supply (`supplier_state == buyer_state`):**
  - Requires Central GST (CGST) and State GST (SGST) in exactly equal amounts.
  - Integrated GST (IGST) must be 0.00 INR. If IGST > 0, flagged as `WRONG_TAX_TYPE`.
- **Interstate Supply (`supplier_state != buyer_state`):**
  - Requires Integrated GST (IGST) only.
  - CGST and SGST must be 0.00 INR. If CGST > 0 or SGST > 0, flagged as `WRONG_TAX_TYPE`.

### 3. Arithmetic Totals Cross-Check
- `sum(line_items.taxable_value) == taxable_amount` (tolerance: +/- 1.00 INR).
- `taxable_amount + cgst + sgst + igst == total_amount` (tolerance: +/- 1.00 INR).

### 4. Duplicate Invoice Guard
- Verifies that `(supplier_gstin, bill_number)` has not previously been recorded for the shop entity.

---

## 7. Repository File Structure & Architecture Map

```
AssureFlow/
|-- .env.example                       # Template for environment configuration
|-- .gitignore                          # Git isolation definitions
|-- Dockerfile                          # Production container image definition
|-- docker-compose.yml                  # PostgreSQL and API service orchestrator
|-- requirements.txt                    # Python dependency manifest
|-- switch.template.yaml                # Declarative Switch agent and room topology
|-- DEMO_SCRIPT.md                      # Complete 12-beat video recording script
|-- MUNIMJI_COMMERCIAL_ROADMAP.md       # Product roadmap & monetization strategy
|-- MUNIMJI_ENTERPRISE_IMPLEMENTATION_PLAN.md # Enterprise architectural specification
|-- README.md                           # Comprehensive architectural documentation
|
|-- scripts/
|   |-- generate_synthetic_bills.py     # Generates 18 realistic PDF & PNG invoices
|   |-- seed_database.py                # Initializes tenants, shops, users, staff, and invoices
|   `-- test_e2e_flow.py                # Automated dry run executing all 12 demo beats
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
|   |-- accounts/                       # Bookkeeping & Bank 3-Way Reconciliation
|   |   |-- __init__.py
|   |   |-- ledger.py                   # Automated expense categorizer and cashflow tracker
|   |   |-- bank_client.py              # Account Aggregator (AA) & bank statement ingestion
|   |   `-- three_way_recon.py          # Three-way cross-reconciliation (Bill <-> 2B <-> Bank)
|   |
|   |-- ai/                             # Gemini AI Integration & Multimodal Vision
|   |   |-- __init__.py
|   |   `-- gemini_client.py            # Multimodal bill extractor & conversational advisor
|   |
|   |-- notifications/                  # Proactive Alerts & Deadline Subsystem
|   |   |-- __init__.py
|   |   `-- alert_engine.py             # GST 20th countdown & low stock alerts
|   |
|   |-- advisory/                       # Junior CA Tax Advisory Engine
|   |   |-- __init__.py
|   |   `-- tax_advisor.py              # Section 44AD, Section 32, Section 17(5), 80C/80D
|   |
|   |-- inventory/                      # Store Inventory & Auto-Restock Subsystem
|   |   |-- __init__.py
|   |   `-- service.py                  # Catalog tracking, stock-in/out, reorder sheet
|   |
|   |-- staff/                          # Store Staff Attendance & Payroll Subsystem
|   |   |-- __init__.py
|   |   `-- service.py                  # Employee roster, check-in, shift summary, payroll
|   |
|   |-- users/                          # User Profiles & RBAC Engine
|   |   |-- __init__.py
|   |   |-- rbac.py                     # Permission boundaries and role data filtering
|   |   `-- service.py                  # User profile authentication and management
|   |
|   |-- dashboard/                      # Visual Dashboard Cockpit
|   |   |-- __init__.py
|   |   `-- router.py                   # Interactive HTML cockpit & telemetry router
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
|   |   |-- routes_gsp.py               # GSTR-2B feed sync, 2-way match, supplier notices
|   |   |-- routes_bank.py              # Bank statement ingestion, 3-way match, status
|   |   |-- routes_shops.py             # Shop registration and profile management
|   |   |-- routes_bills.py             # Multipart upload, audit, and confirmation
|   |   |-- routes_issues.py            # Compliance issue triaging and CA actions
|   |   |-- routes_summary.py           # GSTR reconciliation summaries & GSTR-3B JSON exports
|   |   |-- routes_advisory.py          # Accounts ledger and tax savings endpoints
|   |   |-- routes_inventory.py         # Inventory catalog and stock movement routes
|   |   |-- routes_staff.py             # Employee roster, attendance and payroll routes
|   |   |-- routes_notifications.py     # Proactive deadline and stock alerts endpoints
|   |   `-- routes_users.py             # User profile and role lookup routes
|   |
|   |-- db/                             # Persistence Layer
|   |   |-- __init__.py
|   |   |-- session.py                  # SQLAlchemy session lifecycle management
|   |   |-- init_db.py                  # Schema creation and migration utilities
|   |   `-- models.py                   # Relational models (Tenant, Shop, Bill, Bank, GSTR2B, etc.)
|   |
|   |-- extraction/                     # Document Intake Pipeline
|   |   |-- __init__.py
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
`-- tests/                              # Comprehensive Automated Test Suite (108 Tests)
    |-- __init__.py
    |-- conftest.py                     # Database initialization test fixtures
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
| **Auth & Multi-Tenancy** | `POST` | `/api/auth/register` | Register new tenant organization and admin | `{ "tenant_name": str, "admin_email": str, "admin_password": str, "admin_full_name": str }` |
| | `POST` | `/api/auth/login` | Authenticate user and issue JWT bearer token | `{ "email": str, "password": str }` |
| | `GET` | `/api/auth/me` | Fetch authenticated user profile & tenant info | Header: `Authorization: Bearer <token>` |
| **GSP & 2-Way Recon** | `POST` | `/api/gsp/sync-gstr2b` | Ingest inward GSTR-2B portal records | `{ "shop_id": str, "return_period": str }` |
| | `POST` | `/api/gsp/reconcile` | Run two-way match (Physical vs Portal) | `{ "shop_id": str, "return_period": str }` |
| | `GET` | `/api/gsp/reconciliation-summary/{shop_id}` | Quantitative GSTR-2B reconciliation report | Path: `shop_id`, Query: `return_period` |
| | `GET` | `/api/gsp/supplier-notices/{shop_id}` | Fetch generated Rule 37A supplier recovery notices | Path: `shop_id` |
| **Bank & 3-Way Recon** | `POST` | `/api/bank/ingest-statement` | Ingest bank statement / Account Aggregator feed | `{ "shop_id": str, "transactions": Optional[list] }` |
| | `POST` | `/api/bank/three-way-reconcile` | Run three-way match (Bill <-> 2B <-> Bank) | `{ "shop_id": str }` |
| | `GET` | `/api/bank/recon-status/{shop_id}` | Summary of settled vs unreconciled debits | Path: `shop_id` |
| **WhatsApp Cloud API** | `GET` | `/api/whatsapp/webhook` | Meta Cloud API webhook verification handshake | Query: `hub.mode`, `hub.verify_token`, `hub.challenge` |
| | `POST` | `/api/whatsapp/webhook` | Process WhatsApp receipts, buttons, and queries | Header: `X-Hub-Signature-256`, Payload: Meta JSON |
| **Cockpit & Dashboard** | `GET` | `/health` | Service health status | None |
| | `GET` | `/dashboard` | Interactive HTML visual cockpit | Query: `shop_id`, `role` |
| | `GET` | `/api/dashboard/metrics/{shop_id}` | Role-filtered cockpit telemetry | Path: `shop_id`, Query: `role` |
| **Shop Management** | `GET` | `/api/shops` | List registered merchant entities | None |
| | `POST` | `/api/shops` | Register a new merchant entity | `{ "name": str, "gstin": str, "telegram_chat_id": Optional[str] }` |
| **Bill Processing** | `POST` | `/api/bills/upload` | Ingest bill photo/PDF, run checks | Form: `shop_id`, `file` (Multipart) |
| | `GET` | `/api/bills` | List bills with filters | Query: `shop_id`, `status` |
| | `GET` | `/api/bills/{bill_id}` | Retrieve bill details & issues | Path: `bill_id` |
| | `POST` | `/api/bills/{bill_id}/confirm` | Confirm or correct extracted details | `{ "confirmed": bool, "corrected_total": Optional[float] }` |
| **Compliance & CA** | `GET` | `/api/issues` | Query compliance defects | Query: `shop_id`, `severity`, `ca_action` |
| | `POST` | `/api/issues/{issue_id}/decision` | Record CA review decision | `{ "action": "approve" \| "reject" \| "ask_supplier", "note": Optional[str] }` |
| | `GET` | `/api/summary/{shop_id}` | Month-end GSTR reconciliation | Path: `shop_id` |
| | `GET` | `/api/summary/{shop_id}/export` | Export GSTR JSON (Query: `format=gstr3b` or `summary`) | Path: `shop_id`, Query: `format` |
| | `GET` | `/api/notifications/alerts/{shop_id}` | Proactive filing deadline and low stock alerts | Path: `shop_id` |
| **Tax Advisory** | `GET` | `/api/advisory/accounts/{shop_id}/ledger` | Accounts Book (Khata) & breakdown | Path: `shop_id` |
| | `GET` | `/api/advisory/tax-savings/{shop_id}` | Section 32 & 80C/80D tax plan | Path: `shop_id`, Query: `annual_income` |
| | `GET` | `/api/advisory/presumptive-tax` | Section 44AD feasibility analysis | Query: `turnover`, `digital_pct`, `actual_margin_pct` |
| | `GET` | `/api/advisory/blocked-itc/{shop_id}` | Ineligible Section 17(5) items | Path: `shop_id` |
| **Store Operations** | `GET` | `/api/inventory/{shop_id}` | Complete inventory catalog | Path: `shop_id` |
| | `GET` | `/api/inventory/{shop_id}/reorder-sheet` | Urgent stock replenishment sheet | Path: `shop_id` |
| | `POST` | `/api/inventory/{shop_id}/stock-out` | Record item sale or stock out | `{ "sku": str, "quantity": float, "reason": str }` |
| | `GET` | `/api/staff/{shop_id}/employees` | Staff roster with designations & wage | Path: `shop_id` |
| | `POST` | `/api/staff/{shop_id}/attendance` | Log daily employee attendance | `{ "employee_id": str, "date": str, "status": str }` |
| | `GET` | `/api/staff/{shop_id}/shift-summary` | Morning shift briefing & alerts | Path: `shop_id`, Query: `date` |
| | `GET` | `/api/staff/{shop_id}/payroll` | Monthly payroll calculation sheet | Path: `shop_id`, Query: `month`, `year` |
| | `GET` | `/api/users/profile/{user_id}` | User profile and RBAC permissions | Path: `user_id` |

---

## 9. Chat Commands & Room Interaction Guide

### In Private Shop Rooms (`shop-sharma-kirana` or WhatsApp)
- **Upload File:** Drop any bill photo or PDF. `bill-reader` extracts data and replies with a structured confirmation prompt.
- **`OK`**: Confirms the latest extracted invoice details into the filing queue **AND automatically triggers auto-restock** via `store-manager`.
- **`/stock`**: `store-manager` displays real-time inventory health (total SKUs, low-stock warnings, depleted items).
- **`/reorder`**: `store-manager` generates an automated procurement reorder sheet with suggested quantities and estimated costs.
- **`/attendance`**: `store-manager` displays today's staff roster, attendance summary, and shift briefing.
- **`/checkin [name] [status]`**: `store-manager` logs employee check-in (Present, Absent, Half-Day, Leave).
- **`/payroll [YYYY-MM]`**: `store-manager` calculates monthly staff payroll wage disbursal based on actual attendance days.
- **`/shift_summary`**: `store-manager` outputs the morning operational briefing and procurement alerts.
- **`/khata` or `/accounts`**: `junior-ca` displays the current month's Accounts Book (Mal Kharid, Operating Expenses, Capital Assets, Total Outflow).
- **`/tax_savings`**: `junior-ca` suggests Section 32 asset depreciation and proprietor personal tax deductions (80C, 80D, NPS).
- **`/presumptive [turnover] [digital_pct]`**: `junior-ca` computes Section 44AD deemed profit and estimated tax savings.
- **`/alerts`**: `follow-up` reports pending GST filing deadlines (countdown to the 20th), disputed ITC at risk, and depleted stock warnings.
- **Natural Language ("Ask MunimJi"):** Send conversational questions in Hindi or English (e.g., *"Aaj ka stock kaisa hai"*, *"Tax kaise bacha sakte hain"*, *"Mera khata dikhao"*, *"Staff ki attendance"*). The system classifies intent and returns structured operational or tax insights.
- **`/status`**: `follow-up` returns clean vs pending bill totals.

### In CA Office Room (`ca-office`)
- **`/dashboard`**: `return-preparer` lists high-level compliance status across all client shops.
- **`/summary [shop_id]`**: `return-preparer` generates complete month-end GSTR report with eligible ITC breakdown.
- **`/approve [bill_id]`**: Overrides compliance defect, retaining invoice in the filing pool.
- **`/reject [bill_id]`**: Disallows invoice, excluding it from GSTR-3B tax credit pool.
- **`/ask_supplier [bill_id]`**: Drafts a formal Section 16(2) compliance amendment notice for the supplier.

---

## 10. One-Command Setup & Execution

### Option A: Local Python Environment (Recommended for Demo & Evaluation)

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

# 5. Run full automated end-to-end demo dry run (All 12 beats)
python scripts/test_e2e_flow.py

# 6. Run complete test suite (108 automated unit and integration tests)
pytest

# 7. Launch FastAPI server and view interactive Visual Cockpit
uvicorn src.api.main:app --reload --port 8000
# Open in browser: http://localhost:8000/dashboard
```

### Option B: Live Telegram Bot Deployment
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

### Option C: Live Meta WhatsApp Cloud API Setup
1. In Meta for Developers console, configure a WhatsApp Business Cloud App.
2. Set Webhook URL to: `https://your-public-domain.com/api/whatsapp/webhook`.
3. Set Verify Token to: `munimji_meta_verify_token_2026` (or configure via `WHATSAPP_VERIFY_TOKEN`).
4. Subscribe to the `messages` event field.

### Option D: Docker Compose (PostgreSQL + FastAPI)
```cmd
docker-compose up --build
```

---

## 11. Regulatory Philosophy: "AI Prepares, CA Files"

MunimJi never submits filings directly to the GST Network portal. The AI agents and deterministic engines extract, validate, and organize the ledger; the licensed Chartered Accountant reviews the final summary and files the official return.
