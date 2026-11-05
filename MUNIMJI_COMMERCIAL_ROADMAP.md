# MunimJi — Commercial Production Roadmap (Demo to Enterprise Product)

> **Document Type:** Production Engineering & Commercialization Strategy  
> **Target:** Transforming MunimJi (AssureFlow) from a hackathon prototype into an enterprise-grade SaaS accounting, compliance, and store operations platform for Indian MSMEs and Chartered Accountants.

---

## 1. Executive Gap Analysis: Demo vs Commercial Product

| Architectural Layer | Current Prototype State | Commercial Production Requirement |
| :--- | :--- | :--- |
| **GST Data Source** | Synthetic invoices & manual uploads | Direct Government GSTN Portal integration via GST Suvidha Provider (GSP) API |
| **Reconciliation** | Inward purchase invoice math check | 2-Way & 3-Way Auto-Reconciliation (Purchase Register vs GSTR-2B vs Bank Feed) |
| **Authentication & RBAC** | Soft role query parameter (`?role=OWNER`) | Multi-tenant JWT auth, OAuth2, session expiry, role claims, and encrypted merchant vaults |
| **Document Pipeline** | PyMuPDF + Gemini Vision | Multi-engine OCR fallback pipeline (Tesseract/PaddleOCR + Vision LLM + Human-in-the-Loop) |
| **Messaging & Channels** | Telegram bot & simulated Switch webhook | Official WhatsApp Business API (Meta BSP) + Web Dashboard + SMS notification gateway |
| **Storage & Architecture** | SQLite & synchronous FastAPI requests | PostgreSQL (RDS), Redis task queues (Celery/RQ), S3 encrypted object store for bills |
| **Audit & Security** | Database state updates only | Immutable audit trail, DPDP Act 2023 compliance, Section 65B Indian Evidence Act certificates |

---

## 2. Six Pillars for Commercial Production Readiness

```
+---------------------------------------------------------------------------------------------------+
|                            ENTERPRISE PRODUCTION PLATFORM TOPOLOGY                                |
|                                                                                                   |
|  +-------------------+   +----------------------+   +-------------------+   +------------------+  |
|  | Official WhatsApp |   | Web Cockpit / Mobile |   | Telegram Business |   | GSP Government   |  |
|  | Cloud API (Meta)  |   | (PWA / React Native) |   | Long-Polling Bot  |   | Live GSTN Feeds  |  |
|  +---------+---------+   +----------+-----------+   +---------+---------+   +--------+---------+  |
|            |                        |                         |                      |            |
|            +------------------------+------------+------------+                      |            |
|                                                  |                                   |            |
|                                                  v                                   |            |
|  +-------------------------------------------------------------------------------+   |            |
|  |                     API GATEWAY & MULTI-TENANT AUTH (FASTAPI)                 |   |            |
|  |  - JWT Bearer Authentication                  - Rate Limiting (Redis)         |   |            |
|  |  - Tenant / Organization Isolation Context    - Webhook Signature Verifier    |   |            |
|  +---------------------------------------+---------------------------------------+   |            |
|                                          |                                           |            |
|                                          v                                           |            |
|  +-------------------------------------------------------------------------------+   |            |
|  |                     ASYNCHRONOUS WORKER CLUSTER (CELERY + REDIS)              |   |            |
|  |  +-------------------------+  +-------------------------+  +----------------+ |   |            |
|  |  | OCR & Multimodal Vision |  | GSTR-2B Recon Worker    |  | Auto-Restock   | |<--+            |
|  |  | (Vision LLM + Fallback) |  | (Match Live GST Portal) |  | Event Handler  | |                |
|  |  +-------------------------+  +-------------------------+  +----------------+ |                |
|  +---------------------------------------+---------------------------------------+                |
|                                          |                                                        |
|                                          v                                                        |
|  +-------------------------------------------------------------------------------+                |
|  |                        PERSISTENCE & SECURITY LAYER                           |                |
|  |  - PostgreSQL (Row-Level Security)   - AWS S3 / Cloud Storage (Encrypted)     |                |
|  |  - Redis Cache & Task Broker         - Immutable Audit Ledger (DPDP Compliant)|                |
|  +-------------------------------------------------------------------------------+                |
+---------------------------------------------------------------------------------------------------+
```

---

## 3. Detailed Architectural Enhancements

### Pillar 1: Direct GSTN Integration via GSP (GST Suvidha Provider)
*Current Limitation:* Users must manually upload invoice photos. The system cannot verify if the supplier actually filed the invoice with the government.

- **Integrate Licensed GSP APIs (e.g., Masters India, Cleartax, Karza):**
  - Connect with government GSTN servers using merchant API credentials / OTP authentication.
  - Automatically fetch live **GSTR-2B** (electronic input tax credit statement generated on the 14th of every month).
- **Automated 2-Way Match Engine:**
  - Compare uploaded physical purchase bills against live GSTR-2B data.
  - Classify invoices into:
    - *Full Match:* ITC safe to claim in GSTR-3B.
    - *Supplier Default:* Invoice physically present with shop, but supplier failed to upload GSTR-1 (ITC blocked under Section 16(2)(aa)).
    - *Amount Mismatch:* Supplier reported lower taxable value on portal.
  - Automatically generate WhatsApp notices for suppliers who haven't uploaded invoices before the 11th of the month.

---

### Pillar 2: Production Document Processing & OCR Fallback Pipeline
*Current Limitation:* Relies on PyMuPDF text stream and single-call Gemini Vision. Camera photos without ground-truth fallback can fail on poor lighting or crumpling.

- **Three-Stage Resilient Intake Pipeline:**
  1. **Image Preprocessing Stage:** Automatic deskewing, shadow removal, contrast adaptive thresholding (CLAHE), and edge detection using OpenCV.
  2. **Fast Local OCR / Layout Analysis:** Primary local extraction via Tesseract / PaddleOCR / DocumentAI to extract bounding boxes without cloud API latency.
  3. **Generative Multimodal Parsing (Gemini 2.5 Flash):** Handles thermal slips, handwritten bills, regional font variations, and non-standard tabular formats.
- **Human-in-the-Loop (HITL) Queue:**
  - If confidence score on supplier GSTIN or total amount is below 90%, flag for 1-click verification in the `/dashboard` verification drawer before posting to Khata.

---

### Pillar 3: Real Authentication, Multi-Tenancy & Data Security
*Current Limitation:* Role switching happens via URL query parameters (`?role=OWNER`). Endpoints have no bearer tokens.

- **Multi-Tenant JWT Architecture:**
  - Support Organization / Branch hierarchy (e.g., Sharma Retail Pvt Ltd -> Chandni Chowk Branch, Karol Bagh Branch).
  - Issue cryptographically signed JWT access tokens containing `tenant_id`, `shop_id`, and `role_claims`.
- **Database Row-Level Security (RLS):**
  - PostgreSQL row-level security policies enforcing tenant isolation directly at the database engine level.
- **Secure File Storage:**
  - Store uploaded invoices in private, encrypted S3 buckets with time-limited pre-signed URLs rather than local disk `/uploads`.
- **Digital Personal Data Protection (DPDP) Act Compliance:**
  - Anonymize customer phone numbers on customer-facing bills.
  - Implement export and right-to-be-forgotten endpoints for staff records.

---

### Pillar 4: Bank Feed Integration & 3-Way Reconciliation
*Current Limitation:* Bookkeeping tracks bills, but doesn't reconcile whether the bill was paid via UPI, NEFT, cash, or credit.

- **Account Aggregator (AA) & Bank Statement Integration:**
  - Connect with Indian Account Aggregator framework (e.g., Setu, Sahamati) to pull read-only merchant bank statements.
- **3-Way Reconciliation Engine:**
  - Reconcile `Purchase Invoice` <-> `GSTR-2B Return` <-> `Bank Outflow (UPI / NetBanking)`.
  - Automatically match vendor payments to outstanding bills, generating aging balance sheets (Sundry Creditors ledger).

---

### Pillar 5: WhatsApp Business Cloud API Gateway
*Current Limitation:* Telegram bot is convenient for developers, but Indian retail shop owners operate almost exclusively on WhatsApp.

- **Meta WhatsApp Cloud API Integration:**
  - Direct webhook routing for inbound bill photos sent to a registered business WhatsApp number.
  - Interactive WhatsApp Quick-Reply buttons: `[Confirm Bill]`, `[View Khata]`, `[Low Stock Reorder]`.
  - Automated interactive reminders approaching the 20th GSTR-3B deadline sent straight to the owner's WhatsApp.

---

### Pillar 6: High-Availability Asynchronous Architecture
*Current Limitation:* FastAPI handles bill uploads, PDF parsing, and rule validation in the synchronous request cycle. Under multi-user load, this will block the server.

- **Decoupled Job Queue Architecture:**
  - FastAPI receives the upload -> generates a `bill_id` -> returns HTTP 202 Accepted in under 100ms.
  - Pushes extraction job to Redis queue.
  - Celery / RQ worker pool processes OCR, Gemini Vision, and GST validation asynchronously.
  - Pushes completion notification to user via WebSocket / WhatsApp webhook.

---

## 4. Phase-by-Phase Commercial Rollout Plan

```
Phase 1: Security & Auth Foundation (Weeks 1-2)
- Multi-tenant PostgreSQL migration + JWT Bearer Auth
- S3 encrypted object storage for bill uploads
- Global error logging with Sentry / structured JSON logger

Phase 2: WhatsApp Channel & Asynchronous Queue (Weeks 3-4)
- Meta WhatsApp Business API webhook integration
- Redis + Celery worker cluster for document processing
- Interactive WhatsApp reply buttons for shop owners

Phase 3: GSP Live GSTN & 2-Way Reconciliation (Weeks 5-7)
- Integration with licensed GST Suvidha Provider (GSP) API
- GSTR-2B auto-fetch and automated 2-way matching engine
- Section 16(2)(aa) supplier default alert generator

Phase 4: Bank Feeds & Financial Ledger (Weeks 8-9)
- Account Aggregator / ICICI / HDFC corporate banking webhook integration
- 3-Way purchase-to-payment reconciliation
- Creditor aging analysis and automated payment reminders

Phase 5: CA Practice Portal & Multi-Shop Scale (Weeks 10-12)
- Dedicated multi-client CA portal with bulk filing preparation
- Section 65B electronic audit trail certificate generator
- Android / iOS PWA application release
```

---

## 5. Commercial Impact & Monetization Model

1. **Target Market:** 63M+ Indian MSMEs (kirana shops, electronics retail, distributors, pharmacy chains) and 350,000+ practicing Chartered Accountants.
2. **SaaS Subscription Tiers:**
   - **Shop Tier (INR 499/mo):** WhatsApp bill drop, auto-inventory restock, staff attendance, basic Khata.
   - **Pro Store Tier (INR 1,299/mo):** Multi-counter billing, payroll calculator, Section 44AD optimization, reorder procurement sheets.
   - **CA Practice Partner Tier (INR 4,999/mo):** Unlimited client shops, GSTR-2B automated 2-way recon, bulk filing exports, supplier discrepancy notice drafts.
3. **Enterprise Defense:** The unique combination of Switch multi-room privacy isolation with deterministic tax verification ensures data confidentiality between rival shops while giving CAs centralized practice oversight.

