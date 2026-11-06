# Assure Flow

**Evidence-backed monthly GST purchase review for small shops and their CA, run entirely inside Switch rooms.**

> Flip the Switch hackathon · Track 1: Best Business Workflow · Release `v1.0.0-hackathon`
> AI reads and explains. Code validates and calculates. Authorized people confirm and decide.
> All shops, people, GSTINs and invoices in this repository are synthetic.

## The problem

Indian shop owners collect paper bills, photos and PDFs all month and hand them to their Chartered Accountant
at filing time. Errors surface late: a wrong GSTIN, CGST+SGST charged on an interstate supply, totals that
don't add up, the same bill twice. The CA re-checks everything by hand, chases suppliers over WhatsApp, and
has no reliable record of what was reviewed.

Assure Flow turns invoice messages into a **case** with evidence, runs **deterministic checks**, routes every
exception to the **person who owns it**, reconciles the month against **GSTR-2B**, and ends with a **frozen,
hash-approved review pack** (Excel + JSON) that the CA can trust and reproduce.

## How Switch is used (and why it would not work without it)

Switch is the collaboration layer: every channel is a room, people and the `assure-flow` agent share it, and
work moves between rooms. Assure Flow owns the records, checks, state and approvals.

| Room | Who is in it | What happens there |
|---|---|---|
| `af-shop-sharma`, `af-shop-gupta` (one per shop) | that shop's owner | Send bill photos/PDFs (no @mention needed), answer focused questions, correct values, confirm, send supplier replacements, ask `status` / `why-held`, daily digest |
| `af-ca-review` | the assigned CA | Review requests (RR-…) with evidence and rule results; decisions by reply; GSTR-2B reconciliation; monthly pack approval by hash; Excel/JSON delivered as files; escalations |
| `af-practice-home` | CAs and practice staff only | Practice directory and month readiness across the practice's shops |
| `af-operations` | the operator | Health, failed jobs, `retry`, `trace INV-…`; alerts for dead jobs and withheld messages (ids and metadata only) |
| `af-synthetic-testing` | developers (test/demo only) | `acceptance` runs the full offline suite and posts the machine-generated report |

* **Room isolation is the product.** Shop A never sees shop B, and owners never see the CA room. Before every
  delivery the outbox rechecks the room's declared audience **and Switch's live member list**; if anyone who may
  not see the message is in the room, it is withheld and operations is alerted.
* **Handoffs between rooms.** A tax exception found in a shop room is handed off (data only, no authority) to the
  CA room. A CA's "ask the supplier" goes back to the shop room as a ready-to-send draft. The corrected bill
  comes back into the same case, and anything it invalidates is withdrawn with a notice naming the original action.
* **Every room event is consumed by code.** The adapter connects to Switch as an agent over the WebSocket protocol
  and reads all events (`filter=all`). An upload or a CA reply works without mentioning anyone.
* **Agents get narrow tools, never authority.** LLM agents (e.g. Claude Code via Switch Console) reach Assure Flow
  only through the business-tool MCP server: they can read, explain, draft and request, never confirm, decide or approve.

## Walkthrough (what you see in the rooms)

```
#af-shop-sharma  Ramesh: [photo of bill A108]
#af-shop-sharma  assure-flow: Received R-0001 … saved as INV-0001 … Total: ₹1,780.00 <- uncertain (page 1)
#af-shop-sharma  Ramesh: INV-0001 total=1180.00          (typed correction, no re-reading)
#af-shop-sharma  Ramesh: ok INV-0001 r2
#af-ca-review    assure-flow: RR-0002 · INV-0002 · R-TAX-01: Interstate supply (27 to 07) must use IGST only …
#af-ca-review    CA Mehta: RR-0002 supplier please reissue with IGST
#af-shop-sharma  assure-flow: INV-0002 is waiting for a corrected invoice … Draft you can send: …
#af-shop-sharma  Ramesh: corrected bill for INV-0002 [PDF]   -> same case, version 2, checks rerun
#af-ca-review    assure-flow: Withdrawn: RR-0002 for INV-0002 no longer applies because a replacement document arrived.
#af-ca-review    CA Mehta: RR-0003 include
#af-ca-review    CA Mehta: gstr2b sharma 2026-11 [GSTR-2B.xlsx]
#af-ca-review    assure-flow: RC-0001 · exact match 1 · purchase only 2 · statement only 2 · ambiguous 2 …
#af-ca-review    CA Mehta: snapshot sharma 2026-11
#af-ca-review    assure-flow: SN-0001 · hash 539837db061e · Included 2 · …
#af-ca-review    CA Mehta: approve SN-0001 539837db061e
#af-ca-review    assure-flow: SN-0001 export: Excel + JSON attached.
```

The full live transcripts (Switch 0.31.0 + Mattermost) are in `docs/release/live-run-2026-11-05.md`.
Run the story yourself without keys or servers: `make demo`.

## Architecture

```
 Switch rooms (Mattermost / Telegram / Slack…)                     Assure Flow (Docker Compose)
 ┌──────────────────────┐   WebSocket events (all)   ┌──────────────────────────────────────────────┐
 │ shop · CA · practice │ ─────────────────────────▶ │ adapter → inbox_events (durable, cursor)      │
 │ ops · testing rooms  │ ◀───────────────────────── │ worker: fast | io | slow lanes + outbox       │
 └──────────────────────┘   HTTP: message / media    │   + digest scheduler + subprocess CPU pool    │
          ▲                                          │ domain: CaseWorkflow (pure process manager),  │
          │ LLM agents (optional)                    │   state table, CA action model, Decimal rules,│
          └──── MCP (api/mcp/server.py) ───────────▶ │   GSTR-2B matcher, periods + frozen manifest  │
                                                     │ API: scoped business tools (token + context)  │
                                                     │ PostgreSQL 16 (authoritative) · file store    │
                                                     └──────────────────────────────────────────────┘
```

**What makes it trustworthy**

* **Stable case + revisions.** A case exists from the moment the original is preserved (SHA-256, content-addressed,
  never deleted). Typed corrections create a new revision with no re-reading. Replacement documents create a new
  *document generation*; only the newest can become current. A file holding several invoices is split per page.
* **Evidence-backed extraction.** Every field has a page, an excerpt and a confidence. Pages with a good text layer
  go as text, weak pages as images, mixed pages as both. Claude (`claude-opus-5-5`) vision with JSON-schema output,
  or a recorded-fixture provider offline.
* **Deterministic checks** (`rules/`, profile `domestic_goods_v1`): GSTIN structure and check character ("structure
  passed", never "registered"), recipient GSTIN, tax type vs place of supply (IGST Act s.7/8), line arithmetic,
  per-component tax from printed rates, invoice total, required particulars, duplicates. `Decimal` throughout,
  half-up rounding to paise once at the printed level, separate tax (₹0.01/line) and total (₹1.00) tolerances.
  Unsupported cases are **held**, never guessed.
* **Authority.** Workflow actions use an *interactive context* from one verified room event; background jobs run
  under narrow, revocable *execution grants*; scheduled digests can only notify. CA decisions need a fresh context
  from the CA's own reply and are bound to the exact revision and check run. Overrides are limited to overridable
  rules and listed in the export.
* **Consistency.** Lease fencing tokens on every job commit; shop-period versions locked atomically at approval;
  a frozen, canonical-JSON manifest whose SHA-256 the CA approves; byte-identical JSON and formula-safe Excel.
* **Delivery.** One business action and one logical outbox record per action; ordered per room; at-least-once
  transport with stable action ids; audience rechecked before every send.

## Quickstart (offline: no Switch, no API key)

Prerequisites: Docker, Python 3.12+.

```bash
git clone https://github.com/SaurabhTomar123/AssureFlow.git && cd AssureFlow && git checkout rebuild/assure-flow
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.lock && pip install pytest hypothesis ruff mypy mcp
cp .env.example .env
docker compose up -d db                              # PostgreSQL 16 on 127.0.0.1:5433
python -m alembic upgrade head
make demo        # the correction-to-export story, printed as room transcripts
make test        # 85 offline tests: rules, workflow, authority, isolation, fencing, snapshots, GSTR-2B, MCP
make acceptance  # machine-generated report in docs/release/
```

## Run with Switch (live)

1. Start a Switch server pinned to **0.31.0**: Switch Console ("Add a server"), or Switch's standalone stack from
   the `switch-v0.31.0` tag of [sandbox-quantum/switch](https://github.com/sandbox-quantum/switch)
   (`docker compose -f deploy/local/standalone-docker-compose.yml --profile collab --profile gateway up -d`,
   bundled Mattermost). Set `SWITCH_BASE_URL` and `SWITCH_SERVER_VERSION=0.31.0` in `.env`.
2. Register the agent with a registration key from the Gateway (or the deployment's bootstrap key):
   `SWITCH_REGISTRATION_KEY=… python -m scripts.admin register-agent`.
3. Seed and let the agent create and bind the rooms on the default bridge, mapping each seeded person to their
   chat username: `python -m seed.loader` then
   `python -m scripts.admin create-rooms owner.sharma=<u> owner.gupta=<u> ca.mehta=<u> ops.rao=<u> dev.iyer=<u>`.
4. Start the worker and adapter (`docker compose --profile switch up -d --build`, or `python -m workers.runner` and
   `python -m adapters.run`). Optional for LLM agents: `python -m api.mcp.server` (MCP on 127.0.0.1:8765) with
   `uvicorn api.main:app`.
5. Have each person post once, list them with `python -m scripts.admin unmapped`, and bind each one:
   `python -m scripts.admin bind-user @switch-…-<u>:<server> owner.sharma <u>`.
6. `make health` should be all PASS. Send `seed/fixtures/F13_blurry_photo.png` into `af-shop-sharma`.
   Live tests: `LIVE=1 python -m pytest tests/live`.

Real extraction instead of recorded fixtures: `LLM_PROVIDER=anthropic` and `LLM_API_KEY`.
For development, give your coding agent the Switch documentation (never added to runtime agents):
`claude mcp add --transport http switch-ai-docs https://docs.switchagents.ai/mcp`

## Room commands

**Shop room:** send a file · `ok INV-0001 r1` · `ok INV-0001 hold` · `INV-0001 total=1180.00 date=2026-11-03` ·
send a file with `INV-0001` in the message to replace a document · `status` · `pending` · `why-held INV-0001` · `help`

**CA room:** `RR-0001 include` · `RR-0001 exclude <reason>` · `RR-0001 resolve <RULE-ID> <reason>` ·
`RR-0001 override <RULE-ID>[,…] <reason>` · `RR-0001 clarify <question>` · `RR-0001 supplier <reason>` ·
`reopen INV-0001 <reason>` · `readiness sharma 2026-11` · `snapshot sharma 2026-11` ·
`approve SN-0001 <hash-12> [ack <held> <unassigned>]` · `assign INV-0001 2026-11` · `pending` ·
attach GSTR-2B Excel/JSON to `gstr2b sharma 2026-11` · `recon sharma 2026-11`

**Practice home:** `directory` · `readiness <shop> 2026-11`
**Operations:** `health` · `failed` · `job <id>` · `retry <id>` · `trace INV-0001`
**Synthetic testing:** `acceptance` · `report <run-id>`

## GSTR-2B reconciliation (Phase 6, early)

The CA attaches the GSTR-2B downloaded from the portal to `gstr2b <shop> <period>` in the CA room. It is stored
immutably (re-uploading the same file changes nothing); a wrong GSTIN or period is refused. Code matches each
confirmed purchase to at most one statement line by supplier GSTIN, document type, financial year and invoice
number, compares every tax component in `Decimal`, and reports **exact match, mismatch, purchase only,
statement only, ambiguous**. A match supports review; it is not an ITC eligibility decision.

## Repository map

`api/` FastAPI scoped business tools and `api/mcp/` MCP server · `domain/` models, state table, `CaseWorkflow`, CA
actions, periods, services (intake, checks, snapshots, reconciliation, digests, operations, compensation,
disclosure) · `rules/` deterministic checks and GSTR-2B matcher · `workers/` queue, lanes, CPU pool, handlers,
outbox · `adapters/` Switch client, inbox writer, storage, PDF, GSTR-2B parsers, Claude extraction, Excel ·
`agents/rooms.yaml` · `migrations/` · `seed/` 21 synthetic documents + GSTR-2B fixtures + recorded extractions +
expected outcomes · `tests/offline/`, `tests/live/` · `scripts/` admin, health, measure, isolation matrix,
acceptance, demo · `docs/` decisions, gate files, OpenAPI, release reports

## Known limitations (v1.0.0-hackathon)

* Live test R02 (fresh LLM-agent briefing) is manual: it needs an LLM agent in a room. R01, R04, R05 and R19 are
  automated in `tests/live` and run against Switch 0.31.0.
* Through Mattermost, attach GSTR-2B as Excel: Switch 0.31.0's Mattermost bridge cannot relay `.json` files
  (`docs/decisions.md` D-18).
* Credit/debit-note profiles and eligibility-evidence tracking (P6-06/07) need CA-approved examples and are not built.
* Production phases are not started: P7 real-client security and operations, P8 controlled pilot (two monthly
  cycles), P9 optional filing. They need sign-off from a practising CA and a named security owner.
* Scope: INR domestic B2B purchase tax invoices only. Assure Flow does **not** file GST returns, verify live GSTIN
  registration, or decide ITC eligibility. Amounts are "tax associated with an issue", never "money lost". The CA
  files separately.

## Additional Exploratory Prototypes (`legacy/`)

Exploratory prototypes covering store inventory (FEFO tracking), blue/white-collar attendance, and double-entry bookkeeping are cataloged in `legacy/`. They are decoupled from the core Switch 0.31.0 GST review engine and test suite to preserve architectural integrity and strict mathematical precision (`Decimal` and integer `paise`) across production filings.

