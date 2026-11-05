# MunimJi — Multi-Agent GST Compliance Workflow

> **Flip the Switch Hackathon** | **Track 1: Best Business Workflow**  
> **Core Principle:** AI reads, code checks, human decides.  
> **Notice:** All bills, shops, and GST numbers in this repository are 100% synthetic.

---

## 1. Problem Statement
Every month before the GST filing deadline (GSTR-3B / GSTR-1), small Indian shop owners (MSMEs) dump crumpled paper bills, thermal receipts, and digital PDF invoices onto their Chartered Accountants (CAs). 

This manual scramble causes:
- Massive last-minute compliance stress and communication breakdowns.
- Loss of Input Tax Credit (ITC) due to mismatched or invalid GSTINs.
- Interstate vs Intrastate tax errors (charging CGST/SGST instead of IGST, or vice versa).
- Duplicate invoices claimed across multiple months triggering GST audit penalties.

MunimJi transforms this chaotic end-of-month scramble into an automated, continuous, and private workflow powered by **Switch** and deterministic rule engines.

---

## 2. Architecture & Room Isolation

MunimJi decouples shop-level intake from CA-level oversight through strict multi-room isolation:

```
+-----------------------------------------------------------------------------------+
|                                 SWITCH PLATFORM                                   |
|                                                                                   |
|  +-------------------------+                       +---------------------------+  |
|  |  Shop Room 1 (Private)  |                       |   CA Office Room (Shared) |  |
|  |  - Shop Owner Sharma    |                       |   - Chartered Accountant  |  |
|  |  - Bill Reader Agent    |                       |   - GST Checker Agent     |  |
|  |  - Follow-up Agent      |                       |   - Return Preparer Agent |  |
|  +------------+------------+                       +-------------+-------------+  |
+---------------|--------------------------------------------------|----------------+
                |                                                  |
                v                                                  v
+-----------------------------------------------------------------------------------+
|                        FASTAPI CORE APPLICATION ENGINE                            |
|                                                                                   |
|  +---------------------------+   +-----------------------+   +-----------------+  |
|  |  Document Intake Service  |   | Rule-Based GST Engine |   | Issue Routing & |  |
|  |  (PyMuPDF / OCR / Vision) |-->| - Check-Digit Verify  |-->| Decision Engine |  |
|  |                           |   | - State / Tax Match   |   | - Simple vs     |  |
|  |                           |   | - Math Cross-Check    |   |   Serious Issue |  |
|  |                           |   | - Duplicate Guard     |   +--------+--------+  |
|  +---------------------------+   +-----------------------+            |           |
+-----------------------------------------------------------------------|-----------+
                                                                        v
+-----------------------------------------------------------------------------------+
|                        PERSISTENCE & RECONCILIATION LAYER                         |
|                                                                                   |
|  [ shops ] <---- [ bills ] <---- [ bill_items ] <---- [ compliance_issues ]       |
+-----------------------------------------------------------------------------------+
```

### Privacy & Room Isolation
- **Private Shop Rooms (`shop-sharma-kirana`, `shop-gupta-electronics`)**: One room per shop owner. Shop A never sees Shop B's bills or communications.
- **Shared CA Room (`ca-office`)**: Central office where the CA sees serious compliance issues aggregated across all client shops and makes final decisions.

---

## 3. How Switch is Used

Switch serves as the orchestration backbone that makes multi-agent, cross-boundary collaboration possible:

### Agents & Roles
1. **`bill-reader`**: Stationed inside private shop rooms. Listens for uploaded invoices (PDFs or photos), extracts structured invoice fields (supplier, GSTIN, invoice number, line items, taxes), and posts a structured breakdown asking the owner for confirmation (`OK` or corrections). Supports English and Hindi/Hinglish.
2. **`gst-checker`**: Deterministic audit engine. Validates ISO/IEC 7064 Mod-36 check digits, validates place of supply (CGST/SGST vs IGST), checks line-item math totals within 1.0 INR tolerance, and catches duplicates.
3. **`follow-up`**: Stationed inside private shop rooms. Handles simple defects (blurry photos, missing supplier GSTIN). Calculates and explicitly communicates the exact **Rupee amount at risk** in lost Input Tax Credit to encourage prompt owner action.
4. **`junior-ca`**: Stationed inside private shop rooms. Manages the merchant's digital Accounts Book (`/khata`), categorizing expenses into inventory, opex, capital assets, and logistics. Proactively advises on **Section 32** asset depreciation write-offs, **Section 44AD** Presumptive Taxation savings, and proprietor personal tax optimization (**80C**, **80D**, and **NPS 80CCD**).
5. **`return-preparer`**: Stationed in the CA office room. Aggregates serious issues across all shops, presents single-click CA actions (`/approve`, `/reject`, `/ask_supplier`), automatically drafts Section 16(2) compliance notices to suppliers, and compiles month-end GSTR reconciliation summaries.

### Why MunimJi Requires Switch
Without Switch, this workflow collapses:
- Without multi-room isolation, multiple competing shop owners would share a single channel or require bespoke bot instances for every client.
- Without cross-room agent routing, serious compliance flags cannot be automatically triaged from private shop rooms into the CA's central office room while preserving privacy.

The declarative room and agent structure is defined in `switch.template.yaml`.

---

## 4. One-Command Setup

### Option A: Local Python Environment (Zero Setup)
```cmd
# 1. Clone repository
git clone https://github.com/sandbox-quantum/MunimJi.git
cd MunimJi

# 2. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Generate synthetic dataset and seed database
python scripts/generate_synthetic_bills.py
python scripts/seed_database.py

# 5. Run full automated end-to-end demo (All 9 beats)
python scripts/test_e2e_flow.py

# 6. Run complete test suite (54 tests)
pytest

# 7. Start live Telegram bot (Optional)
python src/switch_bridge/telegram_bot.py
```

### Option B: Docker Compose (PostgreSQL + FastAPI)
```cmd
docker-compose up --build
```

---

## 5. Judging Self-Check

| Criterion | Question Judges Ask | How MunimJi Answers It |
| :--- | :--- | :--- |
| **Use of Switch** | *Would it stop working without Switch?* | Yes. Private Telegram/Mattermost rooms per shop, a shared CA room, and agents carrying issues between them with strict access boundaries. |
| **Technical Execution** | *Can someone clone and run it?* | Yes. `switch.template.yaml`, automated synthetic data generator, database seeder, 36 automated unit/integration tests, and a one-command dry run script. |
| **Creativity & Impact** | *Fresh idea, real problem?* | Solves the high-friction monthly GST bill chaos for millions of Indian small businesses and their accounting professionals. |
| **Presentation** | *Do the video and README show Switch clearly?* | Follows one invoice from photo upload to CA resolution, with clear architecture diagrams and demo beats. |

---

## 6. Philosophy: "AI Prepares, CA Files"
MunimJi never submits filings directly to the GST Network portal. The AI agents and deterministic engines extract, validate, and organize the ledger; the licensed Chartered Accountant reviews the final summary and files the official return.

