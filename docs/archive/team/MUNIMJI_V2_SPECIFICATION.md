# MunimJi (AssureFlow) v2 — Architectural & Technical Specification

> Comprehensive system documentation designed for automated reasoning, LLM agents, and hackathon technical evaluation.
> All merchant entities, tax IDs, invoices, and employee records in this repository are 100% synthetic.

---

## 1. System Identity & Mission

- **Project Name:** MunimJi (Repository: `AssureFlow`)
- **Hackathon Track:** Flip the Switch Hackathon — Track 1: Best Business Workflow
- **Core Principle:** "AI reads and advises, code checks, human decides."
- **Problem Statement:** Over 63 million Indian MSMEs struggle with monthly GST invoice reconciliation, input tax credit (ITC) leakage, statutory filing deadlines, and daily store operations (inventory tracking, staff attendance, payroll).
- **Solution:** A multi-room, multi-agent platform orchestrated via Switch that integrates:
  1. Multimodal document intake (Gemini Vision + PyMuPDF)
  2. Deterministic Indian GST compliance audit (ISO 7064 Mod-36 check digit, Place of Supply, arithmetic totals, duplicate guard)
  3. Store operations (inventory catalog, automated restock from purchase bills, reorder alerts)
  4. Staff management (attendance marking, shift briefings, pro-rata monthly payroll)
  5. Junior CA advisory (Section 44AD presumptive tax, Section 32 depreciation, Section 80C/80D/80CCD(1B) optimization, Section 17(5) blocked ITC)
  6. Central CA practice management (multi-shop oversight, Section 16(2) supplier dispute notices, GSTR-3B export)
  7. Role-Based Access Control (OWNER, MANAGER, STAFF, CA)
  8. Interactive visual dashboard (`/dashboard`) with Chart.js analytics and live role switching

---

## 2. Complete High-Level Architecture

```
+---------------------------------------------------------------------------------------------------+
|                                   SWITCH COLLABORATION PLATFORM                                   |
|                                                                                                   |
|  +------------------------------------+                             +--------------------------+  |
|  |     Shop Room 1 (Private)          |                             | CA Office Room (Shared)  |  |
|  |     - Shop Owner Sharma            |                             | - Chartered Accountant   |  |
|  |     - Store Manager Ramesh         |                             | - GST Checker Agent      |  |
|  |     - Bill Reader Agent            |                             | - Return Preparer Agent  |  |
|  |     - Store Manager Agent          |                             +-------------+------------+  |
|  |     - Follow-up Agent              |                                           |               |
|  |     - Junior CA Agent              |                                           |               |
|  +-----------------+------------------+                                           |               |
|                    |                                                              |               |
|  +-----------------+------------------+                                           |               |
|  |     Shop Room 2 (Private)          |                                           |               |
|  |     - Shop Owner Gupta             |                                           |               |
|  |     - Bill Reader Agent            |                                           |               |
|  |     - Store Manager Agent          |                                           |               |
|  +-----------------+------------------+                                           |               |
+--------------------|--------------------------------------------------------------|---------------+
                     |                                                              |
                     v                                                              v
+---------------------------------------------------------------------------------------------------+
|                                  FASTAPI CORE APPLICATION ENGINE                                  |
|                                                                                                   |
|  +-----------------------------+   +-------------------------+   +-----------------------------+  |
|  | Document Intake Pipeline    |   | Rule-Based GST Engine   |   | Issue Routing & Decisions   |  |
|  | - Gemini 2.5 Flash Vision   |-->| - Mod-36 Check-Digit    |-->| - Simple vs Serious Flags   |  |
|  | - Native PyMuPDF Text Extr. |   | - Place of Supply Rules |   | - Disputed ITC Rupee Risk   |  |
|  | - Table Line-Item Extractor |   | - Duplicate Invoice Det.|   +--------------+--------------+  |
|  +-----------------------------+   +-------------------------+                  |                 |
|                                                                                 |                 |
|  +-----------------------------+   +-------------------------+   +--------------v--------------+  |
|  | Store Operations Subsystem  |   | Junior CA Tax Advisory  |   | Role-Based Access Control   |  |
|  | - Invoice Auto-Restock      |   | - Section 44AD Engine   |   | - OWNER, MANAGER, STAFF, CA |  |
|  | - Low Stock Reorder Sheet   |   | - Section 32 Deprec.    |   | - Data Boundary Filtering   |  |
|  | - Shift Briefing & Roster   |   | - Section 17(5) Blocked |   | - Interactive Cockpit View  |  |
|  | - Attendance & Payroll Math |   | - Personal 80C/80D Plan |   |   at /dashboard             |  |
|  +-----------------------------+   +-------------------------+   +-----------------------------+  |
|                                                                                 |                 |
|  +-----------------------------+   +-------------------------+                  |                 |
|  | Proactive Alert Engine      |   | Natural Language Router |                  |                 |
|  | - 20th Deadline Countdown   |   | - Freeform Hindi/English|<-----------------+                 |
|  | - Depleted Stock Alerter    |   | - Intent Classification |                                    |
|  +-----------------------------+   +-------------------------+                                    |
+---------------------------------------------------------------------------------|-----------------+
                                                                                  v
+---------------------------------------------------------------------------------------------------+
|                                PERSISTENCE & DATA MODEL LAYER                                     |
|                                                                                                   |
|  [ shops ] <----+---- [ bills ] <----+---- [ bill_items ]                                         |
|                 |                    +---- [ compliance_issues ]                                  |
|                 |                    `----> [ stock_movements ] <----+---- [ inventory_items ]    |
|                 |                                                                                 |
|                 +----+---- [ employees ] <----+---- [ attendance_records ]                        |
|                 |                             `---- [ payroll_records ]                           |
|                 +----+---- [ user_profiles ] (RBAC Credentials & Access Matrix)                   |
|                 `----+---- [ ledger_entries ] (Expense Categorization & Khata Cashflows)          |
+---------------------------------------------------------------------------------------------------+
```

---

## 3. Subsystem Breakdown & Module Reference

### 3.1 AI Integration & Multimodal Vision (`src/ai/`)
- **`src/ai/gemini_client.py`:**
  - `get_gemini_api_key()`: Reads API key from environment or settings.
  - `is_gemini_available()`: Returns boolean status of AI availability.
  - `generate_conversational_advice(prompt, system_instruction, language)`: Generates natural language advisory using Gemini 2.5 Flash with graceful fallback to deterministic string templates if the API key is not present.
  - `extract_bill_with_gemini_vision(file_path)`: Uses multimodal vision to extract structured JSON (supplier details, invoice number, amounts, line items) directly from PDF or image files.

### 3.2 Document Intake & Extraction (`src/extraction/`)
- **`src/extraction/pdf_extractor.py`:**
  - `extract_text_from_pdf(pdf_path)`: Uses PyMuPDF to extract text streams from digital invoices.
  - `is_scanned_pdf(pdf_path)`: Detects image-only documents.
- **`src/extraction/parser.py`:**
  - `parse_items_from_lines(lines)`: Scans extracted text lines for table headers (`Item Description`, `HSN`, `Qty`, `Rate`, `Taxable Value`, `Tax %`, `Amount`), parses line-by-line item blocks, and outputs structured `items` lists.
  - `parse_bill_text(text)`: Regex and heuristic parser extracting supplier name, GSTIN, invoice number, date, tax breakdown, and item table.
  - `extract_bill_data(file_path)`: Master intake pipeline that prioritizes Gemini Vision multimodal extraction and falls back to PyMuPDF parsing and ground-truth validation.
  - `check_image_blur(image_path)`: PIL variance-based blur detector for photo quality screening.

### 3.3 Deterministic GST Rules Engine (`src/gst_engine/`)
- **`src/gst_engine/checksum.py`:**
  - `validate_gstin_checksum(gstin)`: Validates 15-character GSTIN check-digit using ISO/IEC 7064 Mod-36 algorithm.
  - `calculate_gstin_check_digit(gstin14)`: Generates valid 15th check character.
  - `generate_valid_gstin(state_code, pan, entity_number)`: Generates valid test GSTINs.
- **`src/gst_engine/rules.py`:**
  - `validate_gstin_format(gstin)`: Format regex verification.
  - `validate_place_of_supply(supplier_gstin, buyer_gstin, cgst, sgst, igst)`:
    - Intrastate (same state): Requires `cgst == sgst` and `igst == 0.0`.
    - Interstate (different states): Requires `igst > 0.0` and `cgst == 0.0` and `sgst == 0.0`.
  - `validate_math_totals(taxable, cgst, sgst, igst, total)`: Round-off cross-check within +/- 1.0 INR.
  - `detect_duplicate_invoice(shop_id, supplier_gstin, bill_number, existing_bills)`: Duplicate detection.
- **`src/gst_engine/validator.py`:**
  - `validate_bill_compliance(bill_data, buyer_gstin, existing_bills)`: Triages issues into `simple` (handled in shop room) and `serious` (routed to CA room), computing exact rupee values of Input Tax Credit at risk.

### 3.4 Store Operations Subsystem (`src/inventory/` & `src/staff/`)
- **`src/inventory/service.py`:**
  - `ensure_inventory_item(shop_id, name, cost_price, hsn_code, db)`: Auto-provisions SKU if not existing.
  - `restock_inventory_from_bill(bill_id, db)`: Auto-increments item quantities and records `IN_PURCHASE` stock movements when invoices are confirmed. Falls back gracefully to supplier-level stock tracking if line items are absent.
  - `record_stock_out(shop_id, sku, quantity, reason, db)`: Decrements stock for sales or damage.
  - `get_inventory_catalog(shop_id, db)`: Returns SKU balances, values, and health statuses (`IN_STOCK`, `LOW_STOCK`, `OUT_OF_STOCK`).
  - `get_low_stock_report(shop_id, db)`: Compiles procurement replenishment list with suggested order quantities and estimated wholesale purchase costs.
- **`src/staff/service.py`:**
  - `add_employee(shop_id, name, designation, phone, monthly_salary, shift, db)`: Registers store staff.
  - `mark_attendance(shop_id, employee_id, date, status, check_in_time, check_out_time, db)`: Records attendance (`PRESENT`, `ABSENT`, `HALF_DAY`, `LEAVE`).
  - `calculate_monthly_payroll(shop_id, month, year, db)`: Calculates pro-rata net wage disbursal based on actual attendance days.
  - `get_daily_shift_summary(shop_id, date, db)`: Compiles daily morning briefing (present staff, absent staff, stock receipts, low stock alerts).

### 3.5 Role-Based Access Control (`src/users/`)
- **`src/users/rbac.py`:**
  - `ROLE_PERMISSIONS`: Permission matrix defining capabilities for `OWNER`, `MANAGER`, `STAFF`, and `CA`.
  - `has_permission(role, permission)`: Authorization checker.
  - `filter_dashboard_data_for_role(role, data)`: Filters sensitive financial summaries, tax savings advice, or floor operations depending on the viewer role.
- **`src/users/service.py`:**
  - User registration, authentication, and role profile retrieval.

### 3.6 Bookkeeping & Junior CA Advisory (`src/accounts/` & `src/advisory/`)
- **`src/accounts/ledger.py`:**
  - `categorize_expense(description)`: Automatically maps line items to `INVENTORY_PURCHASE`, `OPERATING_EXPENSE`, `CAPITAL_ASSET`, or `LOGISTICS_FREIGHT`.
  - `get_accounts_book(shop_id, db)`: Compiles monthly Khata ledger with category breakdowns and cashflow totals.
- **`src/advisory/tax_advisor.py`:**
  - `analyze_presumptive_tax_44ad(annual_turnover, digital_pct, actual_margin_pct)`: Computes deemed profit under Section 44AD (6% digital / 8% cash turnover) and calculates income tax savings and audit exemptions.
  - `calculate_asset_depreciation_section_32(shop_id, db)`: Computes depreciation write-offs (40% for technology assets, 15% for commercial machinery).
  - `generate_proprietor_tax_savings_plan()`: Generates structured tax-saving recommendations for Section 80C, Section 80D (health insurance), and Section 80CCD(1B) (National Pension System).
  - `detect_blocked_itc_section_17_5(items)`: Identifies blocked ITC on food, catering, motor vehicles, and personal consumption.

### 3.7 Proactive Notification Subsystem (`src/notifications/`)
- **`src/notifications/alert_engine.py`:**
  - `check_gst_deadline_alerts(shop_id, db)`: Computes days remaining until the 20th of the month GSTR-3B deadline and quantifies disputed ITC at risk.
  - `check_low_stock_alerts(shop_id, db)`: Detects items reaching or dropping below reorder thresholds.
  - `get_proactive_store_alerts(shop_id, db)`: Aggregated alert telemetry payload.

### 3.8 Visual Cockpit Dashboard (`src/dashboard/`)
- **`src/dashboard/router.py`:**
  - `GET /dashboard`: Responsive Tailwind CSS cockpit featuring live role switcher, 4 primary KPI cards, inventory catalog table, staff roster board, Junior CA tax savings card, and embedded Chart.js visualizations (expense breakdown doughnut chart and ITC health bar chart).
  - `GET /api/dashboard/metrics/{shop_id}`: Role-filtered JSON telemetry.

### 3.9 Autonomous Agent Layer (`src/agents/`)
- **`BillReaderAgent` (`src/agents/bill_reader.py`):** Ingests invoices, extracts fields, and outputs bilingual confirmation previews.
- **`GSTCheckerAgent` (`src/agents/gst_checker.py`):** Runs deterministic compliance audit rules.
- **`FollowUpAgent` (`src/agents/follow_up.py`):** Generates merchant alerts for simple defects with explicit rupee amounts at risk.
- **`StoreManagerAgent` (`src/agents/store_manager.py`):** Handles operational commands (`/stock`, `/reorder`, `/attendance`, `/checkin`, `/payroll`, `/shift_summary`) and announces invoice auto-restocks.
- **`JuniorCAAgent` (`src/agents/junior_ca.py`):** Bookkeeping and tax advisor handling `/khata`, `/tax_savings`, `/presumptive`, and open tax questions with Gemini AI insights.
- **`ReturnPreparerAgent` (`src/agents/return_preparer.py`):** CA cockpit agent formatting serious compliance flags, Section 16(2) supplier dispute notices, and month-end GSTR reconciliation summaries.

### 3.10 Switch Platform Bridge & Routing (`src/switch_bridge/`)
- **`src/switch_bridge/webhook_handler.py`:**
  - Central command router orchestrating agents across private shop rooms and the CA office room.
  - Natural Language Router: Automatically classifies conversational Hindi and English queries without requiring exact slash command syntax.
  - Auto-Restock Trigger: Confirms purchase bills and triggers inventory replenishment.
- **`src/switch_bridge/telegram_bot.py`:**
  - Long-polling daemon supporting Telegram document and photo drops.
- **`switch.template.yaml`:**
  - Declarative topology specifying 6 agents, 3 isolated rooms, tool capabilities, and event triggers (`bill_received`, `bill_confirmed`, `compliance_defect_serious`, `daily_shift_start`).

---

## 4. Complete REST API Specification

| Method | Endpoint | Description | Query / Body Payload |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Service health status | None |
| `GET` | `/dashboard` | Interactive visual cockpit | `shop_id`, `role` (OWNER, MANAGER, STAFF, CA) |
| `GET` | `/api/dashboard/metrics/{shop_id}` | Role-filtered cockpit metrics | `role` |
| `GET` | `/api/shops` | List registered merchant entities | None |
| `POST` | `/api/shops` | Register a new merchant entity | `{ "name": str, "gstin": str, "telegram_chat_id": Optional[str] }` |
| `POST` | `/api/bills/upload` | Ingest bill photo/PDF, audit compliance | Multipart Form: `shop_id`, `file` |
| `GET` | `/api/bills` | List bills with filters | `shop_id`, `status` |
| `GET` | `/api/bills/{bill_id}` | Retrieve bill details & flags | Path: `bill_id` |
| `POST` | `/api/bills/{bill_id}/confirm` | Confirm extracted bill details | `{ "confirmed": bool, "corrected_total": Optional[float] }` |
| `GET` | `/api/issues` | Query compliance defect flags | `shop_id`, `severity`, `ca_action` |
| `POST` | `/api/issues/{issue_id}/decision` | Record CA review decision | `{ "action": "approve" \| "reject" \| "ask_supplier", "note": Optional[str] }` |
| `GET` | `/api/summary/{shop_id}` | Month-end GSTR reconciliation | Path: `shop_id` |
| `GET` | `/api/summary/{shop_id}/export` | Export GSTR reconciliation JSON | `format`: `summary` (default) or `gstr3b` (official portal schema) |
| `GET` | `/api/notifications/alerts/{shop_id}` | Proactive filing countdown and stock alerts | Path: `shop_id` |
| `GET` | `/api/advisory/accounts/{shop_id}/ledger` | Accounts Book (Khata) & expense breakdown | Path: `shop_id` |
| `GET` | `/api/advisory/tax-savings/{shop_id}` | Section 32 & 80C/80D tax plan | Path: `shop_id`, `annual_income` |
| `GET` | `/api/advisory/presumptive-tax` | Section 44AD feasibility analysis | `turnover`, `digital_pct`, `actual_margin_pct` |
| `GET` | `/api/advisory/blocked-itc/{shop_id}` | Ineligible Section 17(5) items | Path: `shop_id` |
| `GET` | `/api/inventory/{shop_id}` | Complete store inventory catalog | Path: `shop_id` |
| `GET` | `/api/inventory/{shop_id}/reorder-sheet` | Urgent stock replenishment sheet | Path: `shop_id` |
| `POST` | `/api/inventory/{shop_id}/stock-out` | Record stock depletion/sale | `{ "sku": str, "quantity": float, "reason": str }` |
| `GET` | `/api/staff/{shop_id}/employees` | Staff roster with salaries & shifts | Path: `shop_id` |
| `POST` | `/api/staff/{shop_id}/attendance` | Log daily employee attendance | `{ "employee_id": str, "date": str, "status": str }` |
| `GET` | `/api/staff/{shop_id}/shift-summary` | Morning shift briefing & alerts | `date` |
| `GET` | `/api/staff/{shop_id}/payroll` | Monthly payroll calculation sheet | `month`, `year` |
| `GET` | `/api/users/profile/{user_id}` | User profile and RBAC permissions | Path: `user_id` |

---

## 5. Automated Verification & Testing Suite

The repository contains 87 automated unit and integration tests across 23 modules:

| Test Module | Coverage Area | Status |
| :--- | :--- | :--- |
| `tests/test_ai_gemini.py` | Gemini client initialization, fallback behavior | 2 passed |
| `tests/test_natural_language_queries.py` | Freeform Hindi/English query intent routing | 4 passed |
| `tests/test_notifications.py` | 20th deadline countdown, stock alerts, `/alerts` | 4 passed |
| `tests/test_gstr3b_export.py` | Government GSTR-3B schema export structure | 2 passed |
| `tests/test_rbac_profiles.py` | Role-Based Access Control and data filtering | 4 passed |
| `tests/test_inventory_management.py` | Invoice auto-restock, stock-out, reorders | 3 passed |
| `tests/test_staff_attendance.py` | Employee roster, daily check-in, payroll math | 3 passed |
| `tests/test_store_manager_agent.py` | Store Manager agent formatting and dialogues | 4 passed |
| `tests/test_api_manager_suite.py` | REST endpoints for users, inventory, staff | 5 passed |
| `tests/test_switch_bridge.py` | Switch router, multi-room routing, auto-restock | 5 passed |
| `tests/test_accounts_ledger.py` | Khata ledger and expense categorization | 2 passed |
| `tests/test_tax_advisory.py` | Section 44AD, Section 32, 80C/80D advisory | 4 passed |
| `tests/test_junior_ca_agent.py` | Junior CA agent conversational outputs | 3 passed |
| `tests/test_extraction.py` | PyMuPDF text extraction, line-item parser | 4 passed |
| `tests/test_gst_checksum.py` | ISO/IEC 7064 Mod-36 check-digit verification | 4 passed |
| `tests/test_gst_rules.py` | Place of supply, math checks, state codes | 6 passed |
| `tests/test_issue_routing.py` | Simple vs serious defect issue triaging | 4 passed |
| `tests/test_api_bills.py` | Bill upload, confirmation, duplicate guard | 7 passed |
| `tests/test_api_advisory.py` | Advisory REST API endpoints | 4 passed |
| `tests/test_db_models.py` | Relational persistence schema validation | 3 passed |
| `tests/test_dataset.py` | Synthetic dataset file verification | 2 passed |
| `tests/test_telegram_bot.py` | Telegram bot command handling and runners | 5 passed |
| `tests/test_env.py` | Core dependencies importability | 3 passed |
| **Total** | **Full automated regression suite** | **87 passed (100%)** |

---

## 6. Execution & Quick Start Instructions

```cmd
# 1. Clone the repository
git clone https://github.com/SaurabhTomar123/AssureFlow.git
cd AssureFlow

# 2. Activate virtual environment
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Generate synthetic invoices and seed database
python scripts/generate_synthetic_bills.py
python scripts/seed_database.py

# 5. Run full 12-beat automated demonstration
python scripts/test_e2e_flow.py

# 6. Run complete test suite (87 automated tests)
pytest

# 7. Start API server and open interactive visual cockpit
uvicorn src.api.main:app --reload --port 8000
# Navigate to: http://localhost:8000/dashboard
```

