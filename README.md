# Assure Flow

**Monthly GST purchase review for small Indian shops and their Chartered Accountant, run entirely inside Switch rooms.**

> Flip the Switch hackathon · Track 1: Best Business Workflow · Release `v1.0.0-hackathon` · Switch server 0.31.0
>
> AI reads and explains. Code validates and calculates. Authorized people confirm and decide.
>
> All shops, people, GSTINs and invoices in this repository are synthetic.

| | |
|---|---|
| **Offline tests** | 85 passed (real PostgreSQL, recorded extractions, in-memory Switch) |
| **Live tests** | 4 passed, 1 manual, against Switch 0.31.0 + Mattermost |
| **Lint / types** | ruff clean · mypy strict clean (58 files) |
| **Health** | 12/12 PASS on the live stack |
| **Audit** | [docs/AUDIT_CHECKLIST.md](docs/AUDIT_CHECKLIST.md) |

## Contents

1. [For judges: five minutes](#for-judges-five-minutes)
2. [The problem](#the-problem)
3. [How Switch is used](#how-switch-is-used-and-why-it-would-not-work-without-it)
4. [Walkthrough](#walkthrough-what-you-see-in-the-rooms)
5. [Architecture](#architecture)
6. [Quickstart (offline)](#quickstart-offline-no-switch-no-api-key)
7. [Run with Switch (live)](#run-with-switch-live)
8. [Room commands](#room-commands)
9. [GSTR-2B reconciliation](#gstr-2b-reconciliation)
10. [Configuration](#configuration)
11. [Testing and verification](#testing-and-verification)
12. [Troubleshooting](#troubleshooting)
13. [Repository map](#repository-map)
14. [Known limitations](#known-limitations-v100-hackathon)

## For judges: five minutes

1. **See it without installing anything:** read the real Switch room transcripts in
   [docs/release/live-run-2026-11-05.md](docs/release/live-run-2026-11-05.md).
2. **Run the story offline (no keys, no Switch):** follow [Quickstart](#quickstart-offline-no-switch-no-api-key) and run `make demo`.
3. **Check the claims:** `make test` (85 tests) and `make acceptance` (machine-generated report). Every phase item
   is listed with its evidence in [docs/gates/](docs/gates/README.md). Design decisions are in
   [docs/decisions.md](docs/decisions.md).

## The problem

Indian shop owners collect paper bills, photos and PDFs all month and hand them to their CA at filing time.
Errors show up late: a wrong GSTIN, CGST+SGST charged on an interstate supply, totals that don't add up, the
same bill twice. The CA re-checks everything by hand, chases suppliers over WhatsApp, and has no reliable record
of what was reviewed.

Assure Flow turns invoice messages into a **case** with evidence. It runs **deterministic checks**, routes every
problem to the **person who owns it**, reconciles the month against **GSTR-2B**, and ends with a **frozen,
hash-approved review pack** (Excel + JSON) that the CA can trust and reproduce.

## How Switch is used (and why it would not work without it)

Switch is the collaboration layer: every channel is a room, people and the `assure-flow` agent share it, and
work moves between rooms. Assure Flow owns the records, checks, state and approvals. The agent creates and binds
all six rooms itself.

| Room | Who is in it | What happens there |
|---|---|---|
| `af-shop-sharma`, `af-shop-gupta` (one per shop) | that shop's owner | Send bill photos/PDFs (no @mention needed), answer focused questions, correct values, confirm, send supplier replacements, ask `status` / `why-held`, daily digest |
| `af-ca-review` | the assigned CA | Review requests (RR-…) with evidence and rule results; decisions by reply; GSTR-2B reconciliation; monthly pack approval by hash; Excel/JSON delivered as files; escalations |
| `af-practice-home` | CAs and practice staff only | Practice directory and month readiness across the practice's shops |
| `af-operations` | the operator | Health, failed jobs, `retry`, `trace INV-…`; alerts for dead jobs and withheld messages (ids and metadata only) |
| `af-synthetic-testing` | developers (test/demo only) | `acceptance` runs the full offline suite and posts the machine-generated report |

* **Room isolation is the product.** Shop A never sees shop B, and owners never see the CA room. Before every
  message is sent, the outbox rechecks the room's declared audience **and Switch's live member list**. If anyone
  who may not see the message is in the room, it is withheld and operations is alerted.
* **Handoffs between rooms.** A tax problem found in a shop room is handed to the CA room (data only, no
  authority). A CA's "ask the supplier" goes back to the shop room as a ready-to-send draft. The corrected bill
  comes back into the same case, and anything it makes obsolete is withdrawn with a notice naming the original action.
* **Every room event is read by code.** The adapter connects to Switch as an agent over WebSocket and reads all
  events (`filter=all`). An upload or a CA reply works without mentioning anyone.
* **Agents get narrow tools, never authority.** LLM agents (for example Claude Code via Switch Console) reach
  Assure Flow only through the business-tool MCP server. They can read, explain, draft and request; they can
  never confirm, decide or approve.

Without Switch there is no intake, no review, no handoff and no delivery: the rooms *are* the user interface.

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

* **Stable case + revisions.** A case exists from the moment the original is saved (SHA-256, content-addressed,
  never deleted). Typed corrections create a new revision with no re-reading. Replacement documents create a new
  *document generation*; only the newest can become current. A file holding several invoices is split per page.
* **Evidence-backed extraction.** Every field has a page, an excerpt and a confidence. Pages with a good text layer
  are sent as text, weak pages as images, mixed pages as both. Claude (`claude-opus-5-5`) vision with JSON-schema
  output, or recorded extractions offline.
* **Deterministic checks** (`rules/`, profile `domestic_goods_v1`): GSTIN structure and check character ("structure
  passed", never "registered"), recipient GSTIN, tax type vs place of supply (IGST Act s.7/8), line arithmetic,
  per-component tax from printed rates, invoice total, required particulars, duplicates. `Decimal` throughout,
  half-up rounding to paise once at the printed level, separate tax (₹0.01 per line) and total (₹1.00)
  tolerances. Unsupported cases are **held**, never guessed.
* **Authority.** Workflow actions use an *interactive context* from one verified room event. Background jobs run
  under narrow, revocable *execution grants*; scheduled digests can only notify. CA decisions need a fresh context
  from the CA's own reply and are bound to the exact revision and check run. Overrides are limited to overridable
  rules and listed in the export.
* **Consistency.** Lease fencing tokens on every job commit; shop-period versions locked atomically at approval;
  a frozen canonical-JSON manifest whose SHA-256 the CA approves; byte-identical JSON and formula-safe Excel.
* **Delivery.** One business action and one logical outbox record per action; ordered per room; at-least-once
  delivery with stable action ids; audience rechecked before every send.

## Quickstart (offline: no Switch, no API key)

Prerequisites: Docker, Python 3.12+, `make` (or run the commands in the `Makefile` by hand).

```bash
git clone https://github.com/SaurabhTomar123/AssureFlow.git && cd AssureFlow
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.lock && pip install pytest hypothesis ruff mypy mcp
cp .env.example .env
docker compose up -d db                              # PostgreSQL 16 on 127.0.0.1:5433
python -m alembic upgrade head
make demo        # the correction-to-export story, printed as room transcripts
make test        # 85 offline tests
make acceptance  # machine-generated report in docs/release/
uvicorn api.main:app --port 8000   # optional: project landing page at http://localhost:8000/
```

## Run with Switch (live)

1. **Start Switch 0.31.0.** Use Switch Console ("Add a server"), or Switch's standalone stack from the
   `switch-v0.31.0` tag of [sandbox-quantum/switch](https://github.com/sandbox-quantum/switch):
   `docker compose -f deploy/local/standalone-docker-compose.yml --profile collab --profile gateway up -d`
   (includes Mattermost). Set `SWITCH_BASE_URL` and `SWITCH_SERVER_VERSION=0.31.0` in `.env`.
2. **Register the agent** with a registration key from the Gateway (or the deployment's bootstrap key):
   `SWITCH_REGISTRATION_KEY=… python -m scripts.admin register-agent`
3. **Seed and create the rooms.** The agent creates and binds them on the default bridge, mapping each seeded
   person to their chat username:
   `python -m seed.loader`, then
   `python -m scripts.admin create-rooms owner.sharma=<u> owner.gupta=<u> ca.mehta=<u> ops.rao=<u> dev.iyer=<u>`
4. **Start the worker and adapter:** `docker compose --profile switch up -d --build`, or
   `python -m workers.runner` and `python -m adapters.run`. Optional, for LLM agents:
   `uvicorn api.main:app` and `python -m api.mcp.server` (MCP on 127.0.0.1:8765).
5. **Bind people.** Have each person post once, list them with `python -m scripts.admin unmapped`, and bind each:
   `python -m scripts.admin bind-user @switch-…-<u>:<server> owner.sharma <u>`
6. **Check:** `make health` should be all PASS. Send `seed/fixtures/F13_blurry_photo.png` into `af-shop-sharma`.
   Live tests: `LIVE=1 python -m pytest tests/live`.

**Telegram instead of Mattermost:** a Telegram bot cannot create groups, so you create the six groups by hand
(exact titles), add the bot, invite `assure-flow`, and bind with
`python -m scripts.admin bind-rooms --prefix "Telegram: "`. The full step-by-step test, with expected results,
is in [docs/MANUAL_TEST_GUIDE.md](docs/MANUAL_TEST_GUIDE.md).

Real extraction instead of recorded fixtures: set `LLM_PROVIDER=anthropic` and `LLM_API_KEY`.

For development, give your coding agent the Switch documentation (never added to the runtime agents):
`claude mcp add --transport http switch-ai-docs https://docs.switchagents.ai/mcp`

## Room commands

| Room | Commands |
|---|---|
| Shop | send a file · `ok INV-0001 r1` · `ok INV-0001 hold` · `INV-0001 total=1180.00 date=2026-11-03` · send a file with `INV-0001` in the message to replace a document · `status` · `pending` · `why-held INV-0001` · `help` |
| CA review | `RR-0001 include` · `RR-0001 exclude <reason>` · `RR-0001 resolve <RULE-ID> <reason>` · `RR-0001 override <RULE-ID>[,…] <reason>` · `RR-0001 clarify <question>` · `RR-0001 supplier <reason>` · `reopen INV-0001 <reason>` · `readiness sharma 2026-11` · `snapshot sharma 2026-11` · `approve SN-0001 <hash-12> [ack <held> <unassigned>]` · `assign INV-0001 2026-11` · `pending` · `gstr2b sharma 2026-11` (with the file attached) · `recon sharma 2026-11` |
| Practice home | `directory` · `readiness <shop> 2026-11` |
| Operations | `health` · `failed` · `job <id>` · `retry <id>` · `trace INV-0001` |
| Synthetic testing | `acceptance` · `report <run-id>` |

## GSTR-2B reconciliation

The CA attaches the GSTR-2B downloaded from the GST portal to `gstr2b <shop> <period>` in the CA room. It is
stored unchanged (re-uploading the same file changes nothing); a wrong GSTIN or period is refused. Code matches
each confirmed purchase to at most one statement line by supplier GSTIN, document type, financial year and invoice
number, compares every tax component in `Decimal`, and reports **exact match, mismatch, purchase only, statement
only, ambiguous**. A match supports review; it is not an ITC eligibility decision.

## Configuration

Every variable, with its default, is in [.env.example](.env.example). The ones you are most likely to change:

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://af:af@localhost:5433/assureflow` | Authoritative store |
| `ENVIRONMENT` | `demo` | `demo` · `test` · `pilot` · `production`; must match the database. Reset is refused outside `demo`/`test` |
| `SWITCH_BASE_URL` / `SWITCH_SERVER_VERSION` | `http://localhost:8080` / empty | Switch server and its pinned version (`0.31.0`) |
| `LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY` | `fake` / `claude-opus-5-5` / empty | `fake` replays recorded extractions; `anthropic` calls Claude |
| `LIVE_MEMBER_CHECK` | `true` | Check Switch's live room members before each send |
| `SWITCH_TRUSTED_USERNAMES` | empty | Chat usernames allowed in rooms without an identity (e.g. deployment admins) |
| `TAX_LINE_TOLERANCE_INR` / `AMOUNT_TOLERANCE_INR` | `0.01` / `1.00` | Rule tolerances |
| `DIGEST_LOCAL_TIME` / `QUIET_HOURS` | `10:00` / `20:00-09:00` | Daily digest schedule (Asia/Kolkata) |

Secrets come only from the environment. `data/` (credentials, files) and `.env` are git-ignored.

## Testing and verification

| Command | What it proves |
|---|---|
| `make test` | 85 offline tests: rules, workflow, authority, isolation, lease fencing, snapshots, GSTR-2B, MCP |
| `make acceptance` | Same suite, with a JSON report in `docs/release/` |
| `make lint` · `make typecheck` | ruff and strict mypy |
| `make health` | Database, environment, room bindings, identities, queues, outbox, Switch server and version |
| `python -m scripts.isolation_matrix` | Every API route and MCP tool refuses another shop and another practice |
| `python -m scripts.measure` | Acknowledgement and extraction timings, model cost |
| `LIVE=1 python -m pytest tests/live` | R01, R04, R05, R19 against a running Switch + Mattermost |
| [docs/MANUAL_TEST_GUIDE.md](docs/MANUAL_TEST_GUIDE.md) | 25 manual tests of the whole workflow in real Telegram groups |

Tests use their own database (`assureflow_test`) and fail, rather than skip, when it is unreachable.
The full pre-submission list is in [docs/AUDIT_CHECKLIST.md](docs/AUDIT_CHECKLIST.md).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Tests error with a connection failure | Start the database: `docker compose up -d db` (port 5433) |
| `refusing to reset in environment …` | Intended: seeding only runs with `ENVIRONMENT=demo` or `test` |
| Switch stack fails to start: port 5434 in use | Change the Switch Postgres host port (we use 55434) |
| GSTR-2B `.json` never arrives through Mattermost | Switch 0.31.0 bridge bug (D-18); attach the Excel file instead |
| Agent replies nowhere / message withheld | Someone without an identity is in the room. See the alert in `af-operations`; bind them or remove them |
| `make health` shows unbound rooms | Run `python -m scripts.admin create-rooms …` or `bind-rooms` (Telegram: `bind-rooms --prefix "Telegram: "`) |

## Repository map

| Path | Contents |
|---|---|
| `api/` | FastAPI scoped business tools; `api/mcp/` MCP server |
| `domain/` | Models, state table, `CaseWorkflow`, CA actions, periods, services (intake, checks, snapshots, reconciliation, digests, operations, compensation, disclosure) |
| `rules/` | Deterministic checks, rule registry, routing, GSTR-2B matcher |
| `workers/` | Queue, lanes, CPU pool, handlers, outbox |
| `adapters/` | Switch client, inbox writer, storage, PDF, GSTR-2B parsers, Claude extraction, Excel |
| `agents/rooms.yaml` | The six rooms and their tool allow-lists |
| `migrations/` | Alembic, one revision per phase |
| `seed/` | 21 synthetic invoices, GSTR-2B fixtures, recorded extractions, expected outcomes |
| `tests/offline/`, `tests/live/` | Offline suite; live Switch tests |
| `scripts/` | admin, health, measure, isolation matrix, acceptance, demo |
| `legacy/` | Earlier MunimJi prototypes, kept for reference only (see below) |
| `docs/` | [decisions](docs/decisions.md), [phase gates](docs/gates/README.md), [audit checklist](docs/AUDIT_CHECKLIST.md), [manual Telegram test guide](docs/MANUAL_TEST_GUIDE.md), OpenAPI, release reports |

## Earlier prototypes (`legacy/`)

`legacy/` keeps the earlier MunimJi prototypes (inventory with FEFO tracking, attendance and payroll,
double-entry bookkeeping, a WhatsApp webhook, Gemini extraction). They are **not part of this release**: nothing
in Docker, the Makefile or the default `pytest` run uses them, they do not go through Switch, and they have not
been brought up to this release's rules (exact decimals, scoped access, Switch rooms). To run their own tests,
use a throwaway SQLite database, never the Assure Flow `DATABASE_URL`, because their setup drops every table:

```bash
DATABASE_URL=sqlite:///./legacy_test.db python -m pytest legacy/tests -o testpaths=legacy/tests
```

## Known limitations (v1.0.0-hackathon)

* Live test R02 (fresh LLM-agent briefing) is manual: it needs an LLM agent in a room. R01, R04, R05 and R19 are
  automated in `tests/live`.
* Through Mattermost, attach GSTR-2B as Excel: Switch 0.31.0's Mattermost bridge cannot relay `.json` files (D-18).
* Credit/debit-note profiles and eligibility-evidence tracking (P6-06/07) need CA-approved examples and are not built.
* Production phases are not started: P7 security and operations for real clients, P8 controlled pilot (two monthly
  cycles), P9 optional filing. They need sign-off from a practising CA and a named security owner.
* Scope: INR domestic B2B purchase tax invoices only. Assure Flow does **not** file GST returns, verify live GSTIN
  registration, or decide ITC eligibility. Amounts are "tax associated with an issue", never "money lost". The CA
  files separately.
