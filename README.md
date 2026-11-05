# MunimJi (AssureFlow) — Autonomous Multi-Agent GST, Store Operations & Bookkeeping Platform

> **Flip the Switch Hackathon** | **Track 1: Best Business Workflow**  
> **Core Operating Principle:** AI reads and advises, code checks, human decides.  
> **Synthetic Data Notice:** All invoices, merchant entities, taxpayer profiles, employee rosters, and GSTIN identifiers in this project are 100% synthetic.

---

## 1. Executive Summary & Problem Context

In India, over 63 million Micro, Small, and Medium Enterprises (MSMEs) face severe operational and compliance bottlenecks approaching the monthly Goods and Services Tax (GST) filing deadline (GSTR-3B / GSTR-1). Retailers, distributors, and shopkeepers accumulate crumpled physical paper receipts, thermal counter slips, and digital PDF invoices throughout the month. At month-end, these are dumped onto their Chartered Accountants (CAs).

Simultaneously, retail shop owners struggle with daily store management:
1. **Input Tax Credit (ITC) Leakage:** Invalid or mismatched GSTINs prevent merchants from claiming legal tax credits under Section 16(2) of the CGST Act.
2. **Tax Classification Errors:** Inadvertently charging Intrastate taxes (CGST + SGST) on Interstate shipments, or charging Integrated GST (IGST) within the same state, resulting in rejected returns.
3. **Audit Exposure via Duplicate Claims:** Submitting the same invoice across multiple periods triggers automated tax department penalty notices.
4. **Absence of Real-Time Bookkeeping:** Small proprietors lack continuous bookkeeping, missing out on statutory tax deductions (Section 32 depreciation, Section 44AD presumptive taxation, and Section 80C/80D personal deductions).
5. **Disconnected Inventory & Procurement:** Invoices are filed for taxes but never linked to inventory stock balances, leading to stockouts and manual reorder sheets.
6. **Manual Staff Attendance & Payroll Calculation:** Store managers track staff attendance on paper registers, leading to wage calculation disputes and opaque shift handovers.
7. **Lack of Role-Based Privacy (RBAC):** Shop owners need their managers and billing staff to handle daily tasks without exposing sensitive proprietor profit margins, CA communications, or personal tax savings.

**MunimJi** solves this by establishing an autonomous, multi-room agent workflow orchestrated via **Switch** and backed by deterministic verification engines, an automated Store Manager subsystem, and a full Junior CA bookkeeping suite.

---

## 2. Multi-Room Isolation & System Architecture

MunimJi decouples shop-level intake, store operations, and CA-level tax oversight through strict multi-room isolation:

```
+-----------------------------------------------------------------------------------------------+
|                                  SWITCH COLLABORATION PLATFORM                                |
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
|  +---------------+---------------+                                            |               |
|  |    Shop Room 2 (Private)      |                                            |               |
|  |    - Shop Owner Gupta         |                                            |               |
|  |    - Bill Reader Agent        |                                            |               |
|  |    - Store Manager Agent      |                                            |               |
|  +---------------+---------------+                                            |               |
+------------------|------------------------------------------------------------|---------------+
                   |                                                            |
                   v                                                            v
+-----------------------------------------------------------------------------------------------+
|                                FASTAPI CORE APPLICATION ENGINE                                |
|                                                                                               |
|  +---------------------------+   +-----------------------+   +-----------------------------+  |
|  |  Document Intake Service  |   | Rule-Based GST Engine |   | Issue Routing & Decision    |  |
|  |  (PyMuPDF / OCR / Blur)   |-->| - Mod-36 Check-Digit  |-->| - Simple vs Serious Flags   |  |
|  |                           |   | - Place of Supply     |   | - ITC Rupee Value at Risk   |  |
|  |                           |   | - Duplicate Guard     |   +--------------+--------------+  |
|  +---------------------------+   +-----------------------+                  |                 |
|                                                                             |                 |
|  +---------------------------+   +-----------------------+   +--------------v--------------+  |
|  |  Store Operations Engine  |   | Junior CA Tax Advisor |   | Role-Based Access Control   |  |
|  |  - Auto-Restock from Bill |   | - Section 44AD Presump|   | - OWNER, MANAGER, STAFF, CA |  |
|  |  - Low Stock Reorder List |   | - Section 32 Deprec.  |   | - Permission Boundary Filter|  |
|  |  - Shift Briefing & Roster|   | - 80C / 80D / 80CCD   |   | - Interactive Cockpit View  |  |
|  |  - Attendance & Payroll   |   | - 17(5) Blocked ITC   |   |   at /dashboard             |  |
|  +---------------------------+   +-----------------------+   +-----------------------------+  |
+-----------------------------------------------------------------------------|-----------------+
                                                                              v
+-----------------------------------------------------------------------------------------------+
|                              PERSISTENCE & RECONCILIATION LAYER                               |
|                                                                                               |
|  [ shops ] <---- [ bills ] <---- [ bill_items ] <---- [ compliance_issues ]                   |
|      |               |                                                                        |
|      |               +-----------> [ stock_movements ] <---- [ inventory_items ]              |
|      |                                                                                        |
|      +-----------> [ employees ] <---- [ attendance_records ] <---- [ payroll_records ]       |
|      |                                                                                        |
|      +-----------> [ user_profiles ] (RBAC Credentials & Permissions)                         |
|      |                                                                                        |
|      +-----------> [ ledger_entries ] (Expense Categorization & Cashflows)                    |
+-----------------------------------------------------------------------------------------------+
```

### Access Control & Privacy Guarantees
- **Private Shop Rooms (`shop-sharma-kirana`, `shop-gupta-electronics`)**: Every shop operates in a distinct chat room. Competitors never observe each other's purchase volumes, supplier identities, inventory counts, or financial margins.
- **Shared CA Office Room (`ca-office`)**: Serves as the central practice management cockpit for the Chartered Accountant. Aggregates only serious compliance flags and high-level return preparation metrics across all managed client shops.
- **Role-Based Filtering**: The `/dashboard` interactive visual cockpit automatically filters data based on the user's role profile (`OWNER`, `MANAGER`, `STAFF`, `CA`). Staff never see sensitive profit margins or personal tax advice.

---

## 3. Autonomous Agents & Specialized Roles

### 1. `bill-reader` (Stationed in Shop Rooms)
- **Role:** Document intake and visual extraction.
- **Behavior:** Automatically acknowledges uploaded invoices (PDFs or camera images), extracts structured fields (supplier name, GSTIN, invoice number, invoice date, line items, taxable values, CGST, SGST, IGST, total amount), and posts a structured preview requesting merchant confirmation (`OK` or textual corrections). Supports English and Hindi/Hinglish.

### 2. `gst-checker` (Deterministic Rule Auditor)
- **Role:** Regulatory math and legal format auditor.
- **Behavior:** Evaluates every confirmed invoice against strict Indian statutory standards:
  - Validates GSTIN check-digit using ISO/IEC 7064 Mod-36 algorithm.
  - Verifies Place of Supply (Intrastate requires equal 50/50 CGST+SGST with zero IGST; Interstate requires IGST only with zero CGST/SGST).
  - Cross-checks arithmetic totals within 1.0 INR round-off tolerance.
  - Detects duplicate invoices against existing historical ledgers.
  - Triages findings into `simple` issues (handled locally in the shop room) and `serious` issues (routed to the CA office).

### 3. `follow-up` (Stationed in Shop Rooms)
- **Role:** Merchant communication and ITC risk alerter.
- **Behavior:** Handles simple defects (blurry captures, missing supplier GSTIN). Translates regulatory errors into actionable business terms, explicitly calculating the **exact Rupee amount of Input Tax Credit at risk**. Sends automated countdown reminders approaching tax filing deadlines.

### 4. `store-manager` (Stationed in Shop Rooms)
- **Role:** Inventory replenishment, staff attendance, shift briefings, and payroll.
- **Behavior:**
  - **Auto-Restock:** When a purchase bill is confirmed with `OK`, automatically creates or increments inventory balances and records `IN_PURCHASE` stock movements.
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

## 4. Role-Based Access Control (RBAC) & User Profiles

MunimJi implements strict role-based access control to ensure privacy and organizational hierarchy across 4 user profiles:

| Role Profile | Key Permissions | Accessible Data | Restricted Views |
| :--- | :--- | :--- | :--- |
| **`OWNER`** | Full System Access | Complete Financials, GST Filings, Junior CA Tax Advice, Inventory, Staff Attendance, Payroll | None |
| **`MANAGER`** | Store Operations | Inventory Catalog, Stock In/Out, Reorder Sheets, Staff Attendance, Shift Briefings, Payroll | Sensitive Financials, Section 44AD Tax Optimization, CA Room Escalations |
| **`STAFF`** | Floor Operations | Daily Check-in, Inventory Stock Lookups, Bill Submissions | Financial Summaries, Wage Disbursals, Tax Strategies, CA Approvals |
| **`CA`** | Practice Compliance | Multi-Shop GST Audit, Serious Compliance Flags, Eligible ITC Ledgers, GSTR Summary Exports | Internal Staff Attendance, Shop Floor Operations |

---

## 5. Deterministic Rule Specification

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

## 6. Repository File Structure & Architecture Map

```
AssureFlow/
|-- .env.example                       # Template for environment configuration
|-- .gitignore                          # Git isolation definitions
|-- Dockerfile                          # Production container image definition
|-- docker-compose.yml                  # PostgreSQL and API service orchestrator
|-- requirements.txt                    # Python dependency manifest
|-- switch.template.yaml                # Declarative Switch agent and room topology
|-- DEMO_SCRIPT.md                      # Complete 12-beat video recording script
|-- README.md                           # Comprehensive architectural documentation
|
|-- scripts/
|   |-- generate_synthetic_bills.py     # Generates 18 realistic PDF & PNG invoices
|   |-- seed_database.py                # Initializes shops, profiles, staff, and invoices
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
|   |-- ai/                             # Gemini AI Integration & Multimodal Vision
|   |   |-- __init__.py
|   |   `-- gemini_client.py            # Multimodal bill extractor & conversational advisor
|   |
|   |-- notifications/                  # Proactive Alerts & Deadline Subsystem
|   |   |-- __init__.py
|   |   `-- alert_engine.py             # GST 20th countdown & low stock alerts
|   |
|   |-- accounts/                       # Bookkeeping & Khata Ledger Engine
|   |   |-- __init__.py
|   |   `-- ledger.py                   # Automated expense categorizer and cashflow tracker
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
|   |   `-- models.py                   # Relational models (Shop, Bill, Items, Issues, Staff, Stock)
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
|       `-- telegram_bot.py             # Standalone long-polling Telegram daemon
|
`-- tests/                              # Comprehensive Automated Test Suite (87 Tests)
    |-- __init__.py
    |-- conftest.py                     # Database initialization test fixtures
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

## 7. Complete REST API Specification

| Method | Endpoint | Description | Key Parameters / Payload |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Service health status | None |
| `GET` | `/dashboard` | Interactive HTML visual cockpit | Query: `shop_id`, `role` |
| `GET` | `/api/dashboard/metrics/{shop_id}` | Role-filtered cockpit telemetry | Path: `shop_id`, Query: `role` |
| `GET` | `/api/shops` | List registered merchant entities | None |
| `POST` | `/api/shops` | Register a new merchant entity | `{ "name": str, "gstin": str, "telegram_chat_id": Optional[str] }` |
| `POST` | `/api/bills/upload` | Ingest bill photo/PDF, run checks | Form: `shop_id`, `file` (Multipart) |
| `GET` | `/api/bills` | List bills with filters | Query: `shop_id`, `status` |
| `GET` | `/api/bills/{bill_id}` | Retrieve bill details & issues | Path: `bill_id` |
| `POST` | `/api/bills/{bill_id}/confirm` | Confirm or correct extracted details | `{ "confirmed": bool, "corrected_total": Optional[float] }` |
| `GET` | `/api/issues` | Query compliance defects | Query: `shop_id`, `severity`, `ca_action` |
| `POST` | `/api/issues/{issue_id}/decision` | Record CA review decision | `{ "action": "approve" \| "reject" \| "ask_supplier", "note": Optional[str] }` |
| `GET` | `/api/summary/{shop_id}` | Month-end GSTR reconciliation | Path: `shop_id` |
| `GET` | `/api/summary/{shop_id}/export` | Export GSTR JSON (Query: `format=gstr3b` or `summary`) | Path: `shop_id`, Query: `format` |
| `GET` | `/api/notifications/alerts/{shop_id}` | Proactive filing deadline and low stock alerts | Path: `shop_id` |
| `GET` | `/api/advisory/accounts/{shop_id}/ledger` | Accounts Book (Khata) & breakdown | Path: `shop_id` |
| `GET` | `/api/advisory/tax-savings/{shop_id}` | Section 32 & 80C/80D tax plan | Path: `shop_id`, Query: `annual_income` |
| `GET` | `/api/advisory/presumptive-tax` | Section 44AD feasibility analysis | Query: `turnover`, `digital_pct`, `actual_margin_pct` |
| `GET` | `/api/advisory/blocked-itc/{shop_id}` | Ineligible Section 17(5) items | Path: `shop_id` |
| `GET` | `/api/inventory/{shop_id}` | Complete inventory catalog | Path: `shop_id` |
| `GET` | `/api/inventory/{shop_id}/reorder-sheet` | Urgent stock replenishment sheet | Path: `shop_id` |
| `POST` | `/api/inventory/{shop_id}/stock-out` | Record item sale or stock out | `{ "sku": str, "quantity": float, "reason": str }` |
| `GET` | `/api/staff/{shop_id}/employees` | Staff roster with designations & wage | Path: `shop_id` |
| `POST` | `/api/staff/{shop_id}/attendance` | Log daily employee attendance | `{ "employee_id": str, "date": str, "status": str }` |
| `GET` | `/api/staff/{shop_id}/shift-summary` | Morning shift briefing & alerts | Path: `shop_id`, Query: `date` |
| `GET` | `/api/staff/{shop_id}/payroll` | Monthly payroll calculation sheet | Path: `shop_id`, Query: `month`, `year` |
| `GET` | `/api/users/profile/{user_id}` | User profile and RBAC permissions | Path: `user_id` |

---

## 8. Chat Commands & Room Interaction Guide

### In Private Shop Rooms (`shop-sharma-kirana`)
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

## 9. One-Command Setup & Execution

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

# 4. Generate synthetic dataset (18 bills) and seed database (shops, users, staff, inventory)
python scripts/generate_synthetic_bills.py
python scripts/seed_database.py

# 5. Run full automated end-to-end demo dry run (All 12 beats)
python scripts/test_e2e_flow.py

# 6. Run complete test suite (87 automated tests)
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

### Option C: Docker Compose (PostgreSQL + FastAPI)
```cmd
docker-compose up --build
```

---

## 10. Hackathon Judging Self-Check

| Criterion | Question Judges Ask | How MunimJi Answers It |
| :--- | :--- | :--- |
| **Use of Switch** | *Would it stop working without Switch?* | Yes. Private Telegram/Mattermost rooms per shop, a shared CA room, and agents carrying issues, restocks, and alerts between them with strict access boundaries. |
| **Technical Execution** | *Can someone clone and run it?* | Yes. `switch.template.yaml`, automated synthetic data generator, database seeder, 75 automated unit/integration tests, and a one-command 12-beat dry run script. |
| **Creativity & Impact** | *Fresh idea, real problem?* | Solves both the high-friction monthly GST compliance chaos and daily store operations (inventory, attendance, payroll) for millions of Indian small businesses. |
| **Presentation** | *Do the video, cockpit, and README show Switch clearly?* | Follows one invoice from photo upload to auto-restock and CA resolution, with clear architecture diagrams, interactive visual cockpit, and demo beats. |

---

## 11. Regulatory Philosophy: "AI Prepares, CA Files"

MunimJi never submits filings directly to the GST Network portal. The AI agents and deterministic engines extract, validate, and organize the ledger; the licensed Chartered Accountant reviews the final summary and files the official return.
