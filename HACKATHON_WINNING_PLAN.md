# MunimJi — Hackathon Innovation Plan: Breakthrough Unique Ideas

> **Hackathon:** [WeMakeDevs & DevTools Academy "Flip the Switch"](https://www.wemakedevs.org/hackathons/switch)  
> **Prize Goals:** Track 1: Best Business Workflow ($2,000) + Code with Wispr ($500) + Best Content (#HowISwitch)  
> **Guiding Theme:** "Bridging the gap for solo AI agents by turning them into collaborative team members on team platforms (Slack, Teams, Discord, Telegram, Mattermost) via **Switch**."

---

## 1. The Innovation Gap: Why Standard Demos Don't Win

Most hackathon projects build predictable workflows: *"User sends a message -> Agent calls an API -> Agent replies."*

To win **Track 1 ($2,000)** and outshine hundreds of global submissions, MunimJi must demonstrate **uniquely Indian, real-world retail authenticity combined with advanced multi-agent coordination** that would be impossible without Switch's multi-room architecture.

---

## 2. Five Breakthrough Unique Ideas

```
+---------------------------------------------------------------------------------------------------+
|                                  THE 5 UNIQUE INNOVATION PILLARS                                  |
|                                                                                                   |
|  [1. "Kacha-Pakka" Smart Sieve]           [2. Autonomous Vendor Dispute Concierge]                |
|  - Distinguishes informal counter chits   - Bot-to-Bot WhatsApp/Switch communication              |
|    from statutory tax invoices            - Auto-resolves mismatched GST returns with suppliers   |
|  - Restocks stock & khata without risk    - Zero phone tag between CA, merchant, and vendor      |
|                                                                                                   |
|  [3. GST Audit Radar & Supplier Scoring]  [4. Working Capital & Dynamic Discount Engine]          |
|  - DGGI tax notice prediction meter       - Early payment discount tracker (e.g. 2% in 7 days)    |
|  - Flags suppliers with filing delays     - 1-Click Mudra/MSME loan health certificate            |
|                                                                                                   |
|  [5. Interactive 3-Room Switch War-Room Live Simulator]                                           |
|  - Side-by-side interactive visual cockpit: [Shop Room] <-> [CA Office] <-> [Vendor Desk]        |
|  - Real-time agent event handoffs, voice notes, and live resolution animation                     |
+---------------------------------------------------------------------------------------------------+
```

---

### Unique Idea 1: The "Kacha-Pakka" Smart Sieve (Tax-Evasion Shield)
*   **The Reality of Indian Retail:**
    Every kirana shopkeeper receives two kinds of documents:
    1. **Pakka Bill (Formal Tax Invoice):** Contains supplier GSTIN, tax breakup, and invoice number. Eligible for government ITC.
    2. **Kacha Bill (Informal estimate / rough counter chit / diary note):** Handwritten slips without GST details or bill numbers. Ineligible for GST claims, but **essential for actual inventory stock-in and daily cashflow tracking**.
*   **The Technical Innovation:**
    *   `bill-reader` uses multimodal vision to classify whether a document is a `FORMAL_TAX_INVOICE` or an `INFORMAL_COUNTER_CHIT`.
    *   **The Sieve Logic:**
        *   If **Kacha Bill**: It routes to `store-manager` (to restock catalog items) and `junior-ca` (to log internal cash expenses in `/khata`), but **strictly isolates and blocks it from the CA tax return queue**.
        *   Alerts the shop owner: *"Handwritten slip recorded in your shop stock and internal khata, but excluded from GST return to protect you from Section 122 penalty notices."*
    *   **Why Judges Will Love It:** It demonstrates authentic domain empathy that generic foreign accounting tools completely fail to grasp.

---

### Unique Idea 2: Autonomous Vendor Dispute Concierge (Bot-to-Bot Resolution)
*   **The Real-World Friction:**
    When GSTR-2B two-way reconciliation flags that a supplier defaulted on filing (or filed the wrong tax amount), the typical workflow breaks down: the CA tells the merchant, the merchant calls the supplier's accountant, the supplier argues, and weeks pass while ITC expires.
*   **The Technical Innovation:**
    *   Introducing the **`vendor-concierge`** agent.
    *   When a `SUPPLIER_DEFAULT` or `TAX_MISMATCH` is flagged, MunimJi generates an **interactive, tokenized WhatsApp Bot link** sent to the supplier's billing department.
    *   The vendor's accountant clicks the link and chats with `vendor-concierge`:
        *   Vendor: *"Sorry, this invoice was filed under our Haryana GSTIN instead of Delhi."*
        *   `vendor-concierge` captures the amended return reference, updates the internal ledger, and broadcasts a resolution event to both the CA Office and the Shop Room:
            *"Dispute resolved with Agrawal Mills. Amendment scheduled in next GSTR-1 return. Unblocked ITC: INR 1,250.00."*
    *   **Why Judges Will Love It:** Showcases true autonomous multi-party agent negotiation across isolated rooms.

---

### Unique Idea 3: Proactive GST Audit Radar & Supplier Risk Scoring
*   **The Technical Innovation:**
    *   An automated audit risk engine (`audit_radar.py`) that scores a merchant's compliance health from **0 (Audit Proof) to 100 (High Risk of Tax Notice)**.
    *   **Algorithmic Risk Metrics:**
        1. *Supplier Defaulter Ratio:* Percentage of vendors who delay or fail GSTR-1 filings.
        2. *Turnover Inconsistency:* Ratio of bank credits to declared turnover under Section 44AD (flags risk of undeclared cash sales).
        3. *Section 17(5) Blocked ITC Claims:* Detects attempts to claim input tax credit on personal food, motor vehicles, or gift items.
    *   **Supplier Compliance Scorecard:** Assigns a creditworthiness badge to vendors (`A+ Safe`, `B Risk of Delay`, `C Chronic Defaulter`), helping merchants choose reliable suppliers who don't endanger their tax credits.

---

### Unique Idea 4: Working Capital & Dynamic Discounting Engine
*   **The Technical Innovation:**
    *   Large FMCG distributors offer small retail shops **Dynamic Discounting** (e.g. *"2% cash discount if invoice is paid within 7 days"*).
    *   Because MunimJi reconciles the purchase invoice date with real-time bank account balances via Account Aggregator:
        *   `store-manager` alerts the owner: *"Distributor Modern Agro offers a 2% discount (Save INR 1,050.00) if paid by Friday. Current bank balance is INR 42,000.00. Click [Pay Now via UPI] to claim discount."*
    *   Generates a 1-click **Verified MSME Credit Health Certificate** (audited turnover, verified GSTR-2B matches, bank cashflows) that proprietors can share with banks for instant Mudra/MSME working capital credit lines.

---

### Unique Idea 5: Interactive 3-Room Switch War-Room Live Simulator
*   **The Visual Hackathon Demo Showstopper:**
    *   A web-based interactive split-screen cockpit accessible at `/switch-simulator` rendering 3 distinct isolated rooms side-by-side:
        1. **Room 1: `Shop Room (Sharma Kirana)`** (Owner Sharma, `@bill-reader`, `@store-manager`, `@junior-ca`).
        2. **Room 2: `CA Practice Cockpit`** (Chartered Accountant, `@gst-checker`, `@return-preparer`).
        3. **Room 3: `Supplier Dispute Desk`** (Vendor Accountant, `@vendor-concierge`).
    *   **Interactive Simulation Console:**
        *   Single-click demo buttons:
            *   `[Drop Clean Bill]` -> Watch Bill Reader extract, Store Manager restock.
            *   `[Drop Kacha Counter Chit]` -> Watch smart sieve triage to internal khata while shielding CA room.
            *   `[Drop Supplier Defect Bill]` -> Watch GST Checker escalate to CA room, CA trigger dispute, and Vendor Concierge resolve it.
            *   `[Voice Input (Hinglish)]` -> Speak or play sample audio note, watch voice intent route to stock and attendance.
    *   **Why Judges Will Love It:** Judges can experience the entire multi-room Switch orchestration visually in 30 seconds without running any terminal commands or configuring chat bots.

---

## 3. Hackathon Implementation Architecture

```
+---------------------------------------------------------------------------------------------------+
|                                 NEW MODULE IMPLEMENTATION STRUCTURE                               |
|                                                                                                   |
|  src/                                                                                             |
|  |-- extraction/                                                                                  |
|  |   `-- document_classifier.py    # Kacha vs Pakka Smart Sieve classifier                        |
|  |                                                                                                |
|  |-- concierge/                                                                                   |
|  |   |-- __init__.py                                                                              |
|  |   `-- vendor_dispute.py         # Autonomous vendor bot-to-bot dispute resolution             |
|  |                                                                                                |
|  |-- advisory/                                                                                    |
|  |   `-- audit_radar.py            # DGGI Tax notice predictor & supplier risk scorecard          |
|  |                                                                                                |
|  |-- voice/                                                                                       |
|  |   |-- __init__.py                                                                              |
|  |   `-- voice_transcriber.py      # Audio note ingestion & Kirana voice intent router (Wispr)   |
|  |                                                                                                |
|  `-- dashboard/                                                                                   |
|      `-- simulator_router.py       # Live 3-Room Switch War-Room interactive web UI               |
|                                                                                                   |
|  scripts/                                                                                         |
|  `-- demo_switch_live.py           # 1-Click ANSI color-coded multi-room terminal demo runner     |
|                                                                                                   |
|  tests/                                                                                           |
|  |-- test_kacha_pakka_sieve.py     # Sieve verification tests                                     |
|  |-- test_vendor_concierge.py      # Dispute resolution tests                                     |
|  `-- test_audit_radar.py           # Risk scoring tests                                           |
+---------------------------------------------------------------------------------------------------+
```

---

## 4. Sequential Execution Subtasks

1. **Subtask 1: The "Kacha-Pakka" Smart Sieve**
   * Classify formal tax invoices vs informal handwritten slips.
   * Route informal slips to inventory and internal khata while barring from CA filing pool.
   * Write tests in `tests/test_kacha_pakka_sieve.py`.

2. **Subtask 2: Autonomous Vendor Dispute Concierge & Rule 37A Bot**
   * Create `src/concierge/vendor_dispute.py`.
   * Simulate vendor WhatsApp negotiation link and resolution broadcast.
   * Write tests in `tests/test_vendor_concierge.py`.

3. **Subtask 3: Proactive GST Audit Radar & Supplier Risk Scorecard**
   * Create `src/advisory/audit_radar.py`.
   * Implement risk metrics (0-100 meter, vendor reliability score).
   * Write tests in `tests/test_audit_radar.py`.

4. **Subtask 4: Wispr Voice Ingestion Module**
   * Create `src/voice/voice_transcriber.py`.
   * Ingest Kirana audio notes in Hindi/English, parsing stock deliveries and staff attendance.
   * Write tests in `tests/test_voice_workflow.py`.

5. **Subtask 5: Interactive 3-Room Switch War-Room Web Simulator & 1-Click Terminal Demo**
   * Build `/switch-simulator` visual UI in `src/dashboard/`.
   * Create `scripts/demo_switch_live.py` with ANSI multi-room playback.
   * Verify all tests pass, update documentation, and push to GitHub.
