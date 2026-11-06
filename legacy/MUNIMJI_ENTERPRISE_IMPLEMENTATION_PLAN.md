# MunimJi (AssureFlow) Enterprise Production Implementation Plan

> **Document Type:** Production Engineering Blueprint & Implementation Plan  
> **Target:** Step-by-step technical architecture, code modifications, database schema migrations, and deployment specifications to transform MunimJi into an enterprise-grade commercial product.  
> **Notice:** All merchant records, tax IDs, and bank transactions in this document are synthetic.

---

## 1. System Vision & Product Architecture

To evolve from a hackathon prototype into a resilient commercial SaaS, MunimJi introduces six production modules:
1. **Live GSP & GSTR-2B Two-Way Auto-Reconciliation Engine**
2. **Three-Stage Resilient OCR & Multimodal Document Pipeline**
3. **Multi-Tenant JWT Authentication with PostgreSQL Row-Level Security (RLS)**
4. **Account Aggregator & Three-Way Bank Reconciliation Engine**
5. **Meta WhatsApp Business Cloud API Bridge**
6. **Decoupled Asynchronous Job Queue (Celery + Redis)**

```
+---------------------------------------------------------------------------------------------------+
|                                  PRODUCTION SYSTEM ARCHITECTURE                                   |
|                                                                                                   |
|  +--------------------+   +-----------------------+   +-------------------+   +-----------------+ |
|  | WhatsApp Business  |   | React Native Mobile / |   | Web Cockpit       |   | GSP Live GSTN   | |
|  | Cloud API (Meta)   |   | PWA Client            |   | Next.js / Tailwind|   | Gateway (Karza) | |
|  +---------+----------+   +-----------+-----------+   +---------+---------+   +--------+--------+ |
|            |                          |                         |                      |          |
|            +--------------------------+------------+------------+                      |          |
|                                                    |                                   |          |
|                                                    v                                   |          |
|  +---------------------------------------------------------------------------------+   |          |
|  |                       API GATEWAY & AUTHENTICATION (FASTAPI)                    |   |          |
|  |  - JWT Bearer Authentication (OAuth2)             - Redis Rate Limiter (Token)  |   |          |
|  |  - Tenant Organization Middleware Context         - Webhook Signature Verifier  |   |          |
|  +-----------------------------------------+---------------------------------------+   |          |
|                                            |                                           |          |
|                                            v                                           |          |
|  +---------------------------------------------------------------------------------+   |          |
|  |                       ASYNCHRONOUS WORKER BROKER (REDIS + CELERY)               |   |          |
|  |  +--------------------------+  +--------------------------+  +----------------+ |   |          |
|  |  | Task: Multimodal OCR     |  | Task: GSTR-2B Auto-Recon |  | Task: Bank 3-Way| |<--+          |
|  |  | OpenCV + Vision LLM + HITL|  | (Live Portal Matcher)    |  | Reconciliation | |            |
|  |  +--------------------------+  +--------------------------+  +----------------+ |              |
|  +-----------------------------------------+---------------------------------------+              |
|                                            |                                                      |
|                                            v                                                      |
|  +---------------------------------------------------------------------------------+              |
|  |                           PERSISTENCE & SECURITY LAYER                          |              |
|  |  - PostgreSQL with Row-Level Security (RLS)  - AWS S3 Encrypted Vault (SSE-KMS) |              |
|  |  - Redis Cache & Distributed Lock Manager    - Immutable Audit Log Ledger       |              |
|  +---------------------------------------------------------------------------------+              |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Technical Work Breakdown & Implementation Steps

### Phase 1: Multi-Tenant JWT Security & PostgreSQL Row-Level Security (RLS)

#### 1.1 Architectural Design
- Migrate from single-database SQLite to multi-tenant PostgreSQL.
- Add `tenants` and `organizations` tables.
- Every business table (`shops`, `bills`, `inventory_items`, `employees`, `ledger_entries`) gains a `tenant_id` foreign key.
- Enable PostgreSQL Row-Level Security (RLS) policies:
  ```sql
  ALTER TABLE bills ENABLE ROW LEVEL SECURITY;
  CREATE POLICY tenant_isolation_policy ON bills
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
  ```

#### 1.2 Required Models (`src/db/models.py`)
```python
class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(String(36), primary_key=True)
    name = Column(String(120), nullable=False)
    subscription_tier = Column(String(30), default="PRO_STORE")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class OrganizationUser(Base):
    __tablename__ = "organization_users"
    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"))
    email = Column(String(120), unique=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(30), default="OWNER") # OWNER, MANAGER, STAFF, CA
    is_active = Column(Boolean, default=True)
```

#### 1.3 Authentication & Context Middleware (`src/auth/jwt_handler.py`)
- Issue signed HS256/RS256 JWT tokens with 24-hour expiry.
- Middleware intercepts requests, verifies the bearer token, and injects `tenant_id` into the database session context.

---

### Phase 2: Live GSP Integration & Two-Way GSTR-2B Auto-Reconciliation

#### 2.1 The Two-Way Reconciliation Problem
Under Section 16(2)(aa) of the CGST Act, a business can claim Input Tax Credit (ITC) only if their supplier has filed their GSTR-1 and the invoice appears in the buyer's live GSTR-2B statement.
In the current prototype, only physical invoice validity is checked. If the supplier fails to report the invoice to the government, the merchant faces tax scrutiny and penalty interest (18% p.a.).

#### 2.2 Live GSP Client Architecture (`src/gsp/client.py`)
```python
class GSPClient:
    def __init__(self, base_url: str, client_id: str, client_secret: str):
        self.base_url = base_url
        self.client_id = client_id
        self.client_secret = client_secret

    def authenticate_merchant(self, gstin: str, username: str, otp: str) -> dict:
        """Exchanges OTP for an active government GSTN auth session token."""
        pass

    def fetch_gstr2b(self, gstin: str, return_period: str) -> dict:
        """Fetches live GSTR-2B B2B invoice tables directly from the GST portal."""
        pass
```

#### 2.3 Automated Two-Way Reconciliation Logic (`src/gsp/reconciler.py`)
```
For each Purchase Bill in local database:
  Match against GSTR-2B B2B records by (supplier_gstin, bill_number):
    1. If Matched and Tax Amounts match within 1.0 INR:
       -> Mark as RECON_MATCHED (ITC Safe to Claim in GSTR-3B)
    2. If Matched but Tax Amount differs:
       -> Mark as RECON_TAX_MISMATCH (Flag difference for supplier credit note)
    3. If Present in Physical Bills but Missing in GSTR-2B:
       -> Mark as SUPPLIER_DEFAULT (Block ITC from current month filing, generate WhatsApp notice)
    4. If Present in GSTR-2B but Missing in Physical Bills:
       -> Mark as UNRECORDED_PURCHASE (Alert owner to locate physical bill)
```

---

### Phase 3: Three-Stage Resilient OCR & Multimodal Vision Pipeline

#### 3.1 Three-Stage Pipeline Architecture (`src/extraction/pipeline.py`)
```
Inbound Document (Image / PDF)
             |
             v
[Stage 1: OpenCV Preprocessing]
  - Auto-rotate EXIF orientation
  - Document boundary detection and 4-point perspective warp
  - Adaptive thresholding (CLAHE) for faded thermal counter slips
             |
             v
[Stage 2: Local OCR Extraction (PaddleOCR)]
  - Extracts text bounding boxes and line tokens in <500ms
  - Heuristic parser runs pattern matching
             |
             v
Did Stage 2 achieve >90% confidence on GSTIN, Invoice #, and Total?
  |-- YES --> Output clean invoice record
  `-- NO  --> [Stage 3: Generative Multimodal Vision (Gemini 2.5 Flash)]
                - Passes raw image bytes to Gemini Vision
                - Resolves handwritten items, regional fonts, and blurred cells
                - If still ambiguous: Routes to Human-in-the-Loop (HITL) Queue
```

---

### Phase 4: Account Aggregator & Three-Way Bank Reconciliation

#### 4.1 Reconciling Bills Against Real Cash Outflows
Currently, the Khata records liability when an invoice is ingested, but cannot confirm if the vendor was paid.
The production system integrates with Indian Account Aggregators (Setu / Sahamati / Banking Webhooks) to track bank balance and UPI/NEFT outflows.

#### 4.2 Three-Way Reconciliation Matrix (`src/accounts/three_way_recon.py`)
```
Purchase Invoice (Bill) <========> Live GSTR-2B Portal <========> Bank Statement Outflow
   (Vendor Liability)                 (Legal ITC Eligibility)          (Actual Payment Record)
```

- **Outcomes:**
  - Automated detection of outstanding vendor payments (Sundry Creditors ledger).
  - Identification of vendor credit periods (e.g., 30-day or 45-day MSME payment terms under Section 43B(h)).
  - Automated payment receipts and bank ledger synchronization.

---

### Phase 5: Meta WhatsApp Business Cloud API Integration

#### 5.1 Architecture (`src/switch_bridge/whatsapp_webhook.py`)
- WhatsApp is the ubiquitous operational interface for Indian retailers.
- Connect via official Meta Graph API:
  - Inbound webhook handles image media drops directly from shopkeepers' phones.
  - Interactive Action Messages:
    - Button 1: `Verify Bill [OK]`
    - Button 2: `Today's Khata`
    - Button 3: `Low Stock Reorder`
  - Proactive notification dispatch: Automatically pushes GSTR-3B countdown alerts (on the 15th, 18th, and 20th of the month) directly to the proprietor's WhatsApp.

---

### Phase 6: Decoupled Asynchronous Worker Queue (Celery + Redis)

#### 6.1 Worker Configuration (`src/tasks/worker.py`)
- Move intensive operations out of FastAPI's request-response lifecycle:
  - `tasks.process_invoice_upload(bill_id, file_path)`
  - `tasks.run_gstr2b_reconciliation(shop_id, period)`
  - `tasks.send_whatsapp_alert(phone, template, params)`
- Benefits:
  - Instant file intake response (<100ms HTTP 202 Accepted).
  - Resilient retry semantics with exponential backoff for external APIs (GSP and Gemini).
  - Scalable worker horizontal scaling across multiple Docker containers.

---

## 3. Database Schema Migration Plan

```sql
-- Migration 002_production_enterprise_schema.sql

-- 1. Tenant & Organization Hierarchy
CREATE TABLE tenants (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    subscription_plan VARCHAR(30) DEFAULT 'PRO_STORE',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE organization_users (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) REFERENCES tenants(id) ON DELETE CASCADE,
    email VARCHAR(120) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(30) NOT NULL DEFAULT 'OWNER',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. GSTR-2B Government Records Table
CREATE TABLE gstr2b_inward_records (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) REFERENCES tenants(id) ON DELETE CASCADE,
    shop_id VARCHAR(36) REFERENCES shops(id) ON DELETE CASCADE,
    supplier_gstin VARCHAR(15) NOT NULL,
    supplier_name VARCHAR(150),
    invoice_number VARCHAR(50) NOT NULL,
    invoice_date DATE NOT NULL,
    invoice_type VARCHAR(20) DEFAULT 'B2B',
    taxable_value NUMERIC(12, 2) NOT NULL,
    cgst NUMERIC(12, 2) DEFAULT 0.00,
    sgst NUMERIC(12, 2) DEFAULT 0.00,
    igst NUMERIC(12, 2) DEFAULT 0.00,
    filing_period VARCHAR(10) NOT NULL, -- e.g., '112026'
    is_itc_available BOOLEAN DEFAULT TRUE,
    itc_disallow_reason VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Two-Way Reconciliation Log Table
CREATE TABLE recon_matches (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) REFERENCES tenants(id) ON DELETE CASCADE,
    shop_id VARCHAR(36) REFERENCES shops(id) ON DELETE CASCADE,
    bill_id VARCHAR(36) REFERENCES bills(id) ON DELETE CASCADE,
    gstr2b_record_id VARCHAR(36) REFERENCES gstr2b_inward_records(id) ON DELETE SET NULL,
    match_status VARCHAR(40) NOT NULL, -- 'EXACT_MATCH', 'AMOUNT_MISMATCH', 'SUPPLIER_DEFAULT', 'MISSING_INVOICE'
    discrepancy_amount NUMERIC(12, 2) DEFAULT 0.00,
    action_taken VARCHAR(40) DEFAULT 'PENDING',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Bank Account & Transaction Ledger
CREATE TABLE bank_transactions (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) REFERENCES tenants(id) ON DELETE CASCADE,
    shop_id VARCHAR(36) REFERENCES shops(id) ON DELETE CASCADE,
    bank_account_number VARCHAR(30) NOT NULL,
    transaction_date DATE NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    transaction_type VARCHAR(10) NOT NULL, -- 'DEBIT' or 'CREDIT'
    payment_mode VARCHAR(20) NOT NULL, -- 'UPI', 'NEFT', 'RTGS', 'CHEQUE', 'CASH'
    reference_number VARCHAR(100),
    narration TEXT,
    matched_bill_id VARCHAR(36) REFERENCES bills(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. Immutable Audit Trail Ledger (Compliance & Forensic Evidence)
CREATE TABLE compliance_audit_log (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) REFERENCES tenants(id) ON DELETE CASCADE,
    user_id VARCHAR(36),
    action VARCHAR(50) NOT NULL, -- 'BILL_CONFIRMED', 'CA_APPROVED', 'RECON_OVERRIDE', 'STOCK_ADJUST'
    target_entity VARCHAR(50) NOT NULL,
    target_id VARCHAR(36) NOT NULL,
    previous_state JSONB,
    new_state JSONB,
    ip_address VARCHAR(45),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

---

## 4. Implementation Subtasks & Verification Gates

```
+---------------------------------------------------------------------------------------------------+
|                            SUBTASK EXECUTION & VERIFICATION ROADMAP                               |
|                                                                                                   |
|  [Subtask 1: Security & Multi-Tenancy] -----------------------------------------------------> [V1]|
|  - PostgreSQL Migration + RLS Policies                                                            |
|  - JWT Bearer Authentication & User Registration                                                  |
|  - Gate V1: test_multitenant_rls_isolation.py (Pass)                                              |
|                                                                                                   |
|  [Subtask 2: Three-Stage Resilient OCR Pipeline] ------------------------------------------> [V2]|
|  - OpenCV Preprocessor (Deskew, CLAHE)                                                            |
|  - PaddleOCR + Gemini 2.5 Flash Fallback Integration                                              |
|  - Gate V2: test_resilient_ocr_pipeline.py (Pass)                                                 |
|                                                                                                   |
|  [Subtask 3: GSP Live GSTR-2B Auto-Reconciler] ---------------------------------------------> [V3]|
|  - GSP Client Interface & GSTR-2B Data Ingestion                                                  |
|  - Two-Way Match Engine (Physical vs Portal)                                                      |
|  - Gate V3: test_two_way_gstr2b_reconciliation.py (Pass)                                          |
|                                                                                                   |
|  [Subtask 4: Bank Feeds & Three-Way Match Engine] -------------------------------------------> [V4]|
|  - Bank Transaction Statement Ingestion                                                           |
|  - Three-Way Match: Bill <-> Portal <-> Payment Outflow                                           |
|  - Gate V4: test_three_way_bank_reconciliation.py (Pass)                                          |
|                                                                                                   |
|  [Subtask 5: Meta WhatsApp Business API Cloud Gateway] -------------------------------------> [V5]|
|  - Inbound WhatsApp Webhook Handler with Signature Verification                                   |
|  - Interactive Action Templates & Deadline Push Notifier                                          |
|  - Gate V5: test_whatsapp_cloud_webhook.py (Pass)                                                 |
|                                                                                                   |
|  [Subtask 6: Asynchronous Task Workers & S3 Vault] -----------------------------------------> [V6]|
|  - Celery Worker Cluster with Redis Broker                                                        |
|  - AWS S3 Encrypted Storage Driver with Pre-Signed URLs                                           |
|  - Gate V6: test_celery_async_tasks.py (Pass)                                                     |
+---------------------------------------------------------------------------------------------------+
```

---

## 5. Production Operational Readiness & Governance

1. **Security & Cryptography:**
   - Database credentials stored via AWS Secrets Manager or HashiCorp Vault.
   - Merchant GSTN credentials encrypted with AES-256-GCM.
2. **High Availability & Fault Tolerance:**
   - Multi-AZ PostgreSQL deployment with read-replicas for CA practice analytical reporting.
   - Redis cluster configured with persistence (AOF + RDB).
3. **Observability & Telemetry:**
   - Structured JSON logging with OpenTelemetry tracing across API Gateway and Celery workers.
   - Prometheus metrics endpoint (`/metrics`) tracking ingestion latency, OCR confidence distribution, and reconciliation success rates.
4. **Legal Compliance:**
   - Strict adherence to Rule 36(4) and Section 16(2) of the CGST Act.
   - Audit trail formatted for Section 65B Indian Evidence Act admissibility in tax dispute hearings.

