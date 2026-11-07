# Assure Flow

### Your shop's GST review, caught in the chat where the bill arrived. Not at month end, when it's hardest to fix.

A shop owner sends a bill to a group chat. AI reads it, the owner confirms the details, and code checks the tax. Their Chartered Accountant reviews it, asks the supplier for a correction with one message, and approves a month-end pack that can't quietly change afterwards.

No new app to install. The team keeps talking where it already talks, and the bot tells people what to reply when it needs something.

> **Flip the Switch hackathon · Track 1: Best Business Workflow** · Built on Switch 0.31.0
>
> **AI reads and explains. Code validates and calculates. People confirm and decide.**
>
> All shops, people, GSTINs and invoices in this repository are synthetic.

## The problem nobody has time for

Every month, a small Indian shop collects bills as paper, photos and PDFs, then hands the pile to its CA close to filing time. That's when the trouble surfaces:

- A supplier in another state charged CGST and SGST when they should have charged IGST.
- A GSTIN is wrong. A total doesn't add up. The same bill arrived twice.
- The supplier now has to reissue an invoice from weeks ago, and the CA chases them over WhatsApp.
- Nobody can say which version of a bill was reviewed, or who approved what.

The shop owner isn't a tax expert. The CA can't recheck every line of every client's bills by hand. Both are working from a chat thread that was never built to be a record.

## What changes

| | Today | With Assure Flow |
|---|---|---|
| **Finding a mistake** | Near filing time, by hand | When the owner confirms the bill, by fixed rules |
| **Fixing it** | Phone calls and forwarded photos | The CA asks in one message; the owner gets a draft ready to send to the supplier |
| **Knowing the current version** | "Is this the latest one?" | One case with every version kept. Approving an old version is refused |
| **Bills from clients** | Lost in someone's chat | A drop-off room; they get "received", and the owner gets the details |
| **Month end** | A spreadsheet someone edited | An exact pack approved by its hash. If a bill changes, the pack is marked superseded |
| **Reconciliation** | Manual comparison with GSTR-2B | Bills matched against the statement, with differences listed |

## See it in 30 seconds

Shortened from a live test run, with a bill that looked fine to the owner:

```
Owner's group
  Ramesh       [sends the bill from Pune Electricals]
  assure-flow  INV-0003: Total ₹8,732.00. Please check these details.
  Ramesh       ok INV-0003 r1

  assure-flow  RR-0003 · R-TAX-01: Interstate supply (27 to 07) must use IGST only,
               but CGST 666.00 / SGST 666.00 are printed.
               Suggestion from the checks, not a decision: request a corrected invoice
               from the supplier. Priya, your decision.

  Priya (CA)   RR-0003 supplier please reissue with IGST for this interstate supply
  assure-flow  Draft you can send: "Dear Pune Electricals LLP, please issue a corrected tax invoice..."

  Ramesh       corrected bill for INV-0003  [sends the new PDF]
  Ramesh       ok INV-0003 r2

  Priya (CA)   RR-0003 include       (trying the old version on purpose)
  assure-flow  That refers to an older version. Nothing was changed.
```

₹1,332 of tax charged under the wrong heads, caught and corrected before anyone filed anything.

## Who it works for

- **An owner on their own.** Send a bill, check the summary, confirm. That's all they have to do. No @mention and no app.
- **An owner and a CA together.** Work in one shared group and talk it through, or keep separate rooms. It's a per-shop choice.
- **A CA with many clients.** A private room keeps every shop's queue, monthly packs and approvals together.
- **Suppliers and clients.** A drop-off room where they send a bill and only ever see "received".

And in every case, **authority doesn't depend on the room**. Only the owner confirms the details. Only the assigned CA can include or exclude a bill. Agents can explain and draft, but they're never given a tool to approve. People can chat freely, too: "yes, please call him" can't confirm a bill by accident.

## Why you can trust it

| Risk | What stops it |
|---|---|
| An AI invents a number | It only reads. Fixed rules do every calculation, in exact decimals, and the owner confirms the reading |
| Someone approves an outdated bill | Every decision is tied to one version; a stale one is refused |
| A pack changes after sign-off | Approval is bound to the pack's hash, and any later change marks it superseded |
| One shop sees another's bills | Rooms are scoped per shop, and the audience is rechecked before every message |
| A message goes to the wrong audience | Sent only if everyone known in the room is allowed to see it; otherwise withheld and flagged to operations |
| A crash loses work | Durable inbox and outbox; messages are processed once after a restart |

It doesn't file GST, pay anyone or decide what credit you can claim. It gets the review right and leaves a record, and the CA stays in charge.

## What's actually been proven

| Evidence | Result |
|---|---|
| **Offline tests** | 189 passed, on real PostgreSQL |
| **Live on Mattermost, five separate accounts** | 33/33 checks: [full results](docs/release/live-run-2026-11-07-shared-review.md) |
| **Controlled restart** | Second copy refused; a message sent during downtime answered once; nothing replayed |
| **Live on Telegram** | The main owner and CA journey run by hand: [test report, including what failed](docs/release/telegram-manual-2026-11-06.md). The fixes for those failures are proven on Mattermost, and their Telegram rerun is pending |
| **Live bill reading with Gemini** | 4 clean synthetic bills matched on all 48 fields; a small sample, not an accuracy claim |
| **Lint and types** | ruff clean, mypy strict clean |

Everything still limited is listed under [Known limitations](#known-limitations-v100-hackathon). The full audit is in [docs/AUDIT_CHECKLIST.md](docs/AUDIT_CHECKLIST.md).

## Contents

1. [For judges: five minutes](#for-judges-five-minutes)
2. [How Switch is used](#how-switch-is-used-and-why-it-would-not-work-without-it)
3. [Walkthrough](#walkthrough-what-you-see-in-the-rooms)
4. [Architecture](#architecture)
5. [Quickstart (offline)](#quickstart-offline-no-switch-no-api-key)
6. [Run with Switch (live)](#run-with-switch-live)
7. [Room commands](#room-commands)
8. [GSTR-2B reconciliation](#gstr-2b-reconciliation)
9. [Shared review group and client invoices](#shared-review-group-optional-per-shop)
10. [Purchase assurance (U2)](#purchase-assurance-update-u2-behind-a-flag)
11. [Configuration](#configuration)
12. [Testing and verification](#testing-and-verification)
13. [Troubleshooting](#troubleshooting)
14. [Repository map](#repository-map)
15. [Known limitations](#known-limitations-v100-hackathon)

## For judges: five minutes

1. **See the live results without installing anything:** the [33-check Mattermost run](docs/release/live-run-2026-11-07-shared-review.md) and the [room transcripts](docs/release/live-run-2026-11-05.md).
2. **Run the story offline, with no keys and no Switch:** follow the [Quickstart](#quickstart-offline-no-switch-no-api-key) and run `make demo`.
3. **Check the claims:** `make test` (189 tests) and `make acceptance`, which writes a machine-generated report. Every phase item is listed with its evidence in [docs/gates/](docs/gates/README.md), and design decisions are in [docs/decisions.md](docs/decisions.md).

## How Switch is used (and why it would not work without it)

Switch is the collaboration layer: every channel is a room, people and the `assure-flow` agent share it, and
work moves between rooms. Assure Flow owns the records, checks, state and approvals. The agent creates and binds
its rooms itself.

| Room | Who is in it | What happens there |
|---|---|---|
| `af-shop-sharma`, `af-shop-gupta` (one per shop) | that shop's owner | Send bill photos/PDFs (no @mention needed), answer focused questions, correct values, confirm, send supplier replacements, ask `status` / `why-held`, daily digest |
| `af-ca-review` | the assigned CA | Review requests (RR-…) with evidence and rule results; decisions by reply; GSTR-2B reconciliation; monthly pack approval by hash; Excel/JSON delivered as files; escalations |
| `af-practice-home` | CAs and practice staff only | Practice directory and month readiness across the practice's shops |
| `af-operations` | the operator | Health, failed jobs, `retry`, `trace INV-…`; alerts for dead jobs and withheld messages (ids and metadata only) |
| `af-synthetic-testing` | developers (test/demo only) | `acceptance` runs the full offline suite and posts the machine-generated report |
| `af-submit-sharma` (one per shop, optional) | clients and suppliers | Drop off a bill and see only "received": no reference numbers, amounts or commands |
| `af-delivery-sharma` (purchase assurance) | the storekeeper | Counts what arrived against the order: item names and quantities only, **never prices** |

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
#af-ca-review    assure-flow: SN-0001 export, JSON file … · SN-0001 export, Excel file …
```

## Architecture

```
 Switch rooms (Mattermost / Telegram)                             Assure Flow (Docker Compose)
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
make test        # 189 offline tests
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
| CA review | `RR-0001 include` · `RR-0001 exclude <reason>` · `RR-0001 resolve <RULE-ID> <reason>` · `RR-0001 override <RULE-ID>[,…] <reason>` · `RR-0001 clarify <question>` · `RR-0001 supplier <reason>` · `reopen INV-0001 <reason>` · `readiness sharma 2026-11` · `snapshot sharma 2026-11` · `approve SN-0001 <hash-12> [ack <held> <unassigned>]` · `resend SN-0001 [excel|json]` · `assign INV-0001 2026-11` · `pending` · `gstr2b sharma 2026-11` (with the file attached) · `recon sharma 2026-11` |
| Practice home | `directory` · `readiness <shop> 2026-11` |
| Operations | `health` · `failed` · `job <id>` · `retry <id>` · `trace INV-0001` |
| Synthetic testing | `acceptance` · `report <run-id>` |
| Shop, purchases (flag on) | `orders` · `ok PO-101` · `link INV-0001 PO-101 [1=L1]` · `accept-partial PO-101` · `task INV-0001 <who> <due> <what>` · `TK-0001 ack\|done <note>\|verify\|cancel <reason>` · `tasks` · `purchase PO-101` · `authorize PR-0001 <hash-12> due YYYY-MM-DD` |
| Delivery (flag on) | `orders` · `PO-101 L1=8` · `ok DR-0001 v1` · `DR-0001 L1=9` (corrects, never adds) |
| CA review, purchases (flag on) | `review PR-0001 <hash-12>` |

## GSTR-2B reconciliation

The CA attaches the GSTR-2B downloaded from the GST portal to `gstr2b <shop> <period>` in the CA room. It is
stored unchanged (re-uploading the same file changes nothing); a wrong GSTIN or period is refused. Code matches
each confirmed purchase to at most one statement line by supplier GSTIN, document type, financial year and invoice
number, compares every tax component in `Decimal`, and reports **exact match, mismatch, purchase only, statement
only, ambiguous**. A match supports review; it is not an ITC eligibility decision.

## Shared review group (optional, per shop)

By default the owner and CA have separate rooms. A shop can instead share one group with its CA:
`python -m scripts.admin shared-review sharma on`, then add the CA to the shop's chat group.

* The owner uploads and confirms bills, and review requests and CA decisions all happen in that group.
* Only the CA can include or exclude; only the owner can confirm. Agents can do neither.
* People can talk freely: only strictly formed commands act, so "yes, call him" can't confirm a bill.
* Each review request carries a suggestion worked out from the checks, labelled as not a decision.
* The CA's private room remains for monthly packs, approvals and the view across shops.

The owner sees the CA's review details in this mode, so use it only where that's acceptable (D-31).

**Client invoices.** A client sends bills in the shop's submission room (`af-submit-sharma`) and only ever sees "received".
The bill appears in the shop group with who sent it, the owner confirms the details, and it reaches the CA with no forwarding
(D-32). To add one to an existing database: `python -m scripts.admin add-client sharma client.verma "Verma Supplies"`.

## Purchase assurance (Update U2, behind a flag)

Invoice review answers "is this bill correct?". Purchase assurance adds "did we get what we were billed for?",
comparing **what was ordered, what the storekeeper confirms arrived and what the supplier billed**, then
producing a reviewed **payment-readiness** record. It is off by default (`PURCHASE_ASSURANCE_ENABLED=false`,
plus per-shop opt-in) and leaves every v1.4 behaviour unchanged when off.

```
#af-shop-sharma      Ramesh: ok PO-101 r1                       (owner confirms the order: 10 cartons)
#af-delivery-sharma  Suresh: PO-101 L1=8 · ok DR-0001 v1        (storekeeper counts; this room never shows prices)
#af-shop-sharma      assure-flow: PO-101 / INV-0001: payment readiness is on hold.
                     • billed 10 carton but 8 confirmed received (difference 2)
#af-shop-sharma      Ramesh: task INV-0001 anil tomorrow get a corrected invoice for 8 cartons
#af-shop-sharma      Anil: TK-0001 done …    -> stays on hold: finishing a task never clears a mismatch
#af-shop-sharma      Ramesh: corrected bill for INV-0001 [PDF] · ok INV-0001 r2 · accept-partial PO-101 · TK-0001 verify
#af-ca-review        CA Mehta: review PR-0001 933eed99cf16       (signs the exact record)
#af-shop-sharma      Ramesh: authorize PR-0001 933eed99cf16 due 2026-11-20
#af-shop-sharma      assure-flow: PR-0001 is ready for payment: ₹4,200.00 … Nothing has been paid.
                     Still outstanding on PO-101: 2 carton … [purchase pack: Excel + JSON]
```

Code does every comparison (`rules/purchase.py`, rules M01–M08: supplier, line mapping, exact quantities and
units, exact price, partial delivery, invoice review first, missing evidence, one invoice per order). People
confirm the order, the delivery count, the link and any partial delivery; the reviewer and then the owner sign the
same content hash, and the owner's authorization rechecks every input in the same transaction. Any later change
withdraws the record with a notice. Ready for payment never means paid. Full transcript:
[docs/release/live-run-2026-11-06-purchase.md](docs/release/live-run-2026-11-06-purchase.md); contract and scope:
[docs/purchase-assurance-update.md](docs/purchase-assurance-update.md); evidence: [docs/gates/U2.md](docs/gates/U2.md).

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
| `LLM_PROVIDER` | `fake` | `fake` replays recorded extractions (no key); `anthropic` or `gemini` read new bills live and need `LLM_MODEL` and `LLM_API_KEY`. Measure accuracy with `make eval-extraction` first. A free Gemini key is for synthetic documents only (D-30) |
| `PURCHASE_ASSURANCE_ENABLED` | `false` | Purchase assurance (U2); shops also opt in (`seed/practice.yaml`) |
| `TAX_LINE_TOLERANCE_INR` / `AMOUNT_TOLERANCE_INR` | `0.01` / `1.00` | Rule tolerances |
| `DIGEST_LOCAL_TIME` / `QUIET_HOURS` | `10:00` / `20:00-09:00` | Daily digest schedule (Asia/Kolkata) |

Secrets come only from the environment. `data/` (credentials, files) and `.env` are git-ignored.

## Testing and verification

| Command | What it proves |
|---|---|
| `make test` | 189 offline tests: rules, workflow, authority, isolation, lease fencing, snapshots, GSTR-2B, MCP, purchase assurance |
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
| Agent replies nowhere / message withheld | Someone without an identity is in the room. See the alert in `af-operations`; bind them or remove them. On Telegram, a removal isn't noticed: create a fresh group and run `python -m scripts.admin rebind-room <name> <switch-room-id> <reason>` |
| Adapter or worker exits saying one is already running | Another copy holds the lock, and the message names it. Stop that copy first |
| `make health` shows unbound rooms | Run `python -m scripts.admin create-rooms …` or `bind-rooms` (Telegram: `bind-rooms --prefix "Telegram: "`) |

## Repository map

| Path | Contents |
|---|---|
| `api/` | FastAPI scoped business tools; `api/mcp/` MCP server |
| `domain/` | Models, state table, `CaseWorkflow`, CA actions, periods, services (intake, checks, snapshots, reconciliation, digests, operations, compensation, disclosure) |
| `rules/` | Deterministic checks, rule registry, routing, GSTR-2B matcher, purchase matcher (M01–M08) |
| `workers/` | Queue, lanes, CPU pool, handlers, outbox |
| `adapters/` | Switch client, inbox writer, storage, PDF, GSTR-2B parsers, Claude extraction, Excel |
| `agents/rooms.yaml` | The six rooms and their tool allow-lists |
| `migrations/` | Alembic, one revision per phase |
| `seed/` | 23 synthetic invoices, GSTR-2B fixtures, seeded purchase order, recorded extractions, expected outcomes |
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
* Purchase assurance (U2) is the hackathon slice: seeded orders confirmed in chat (no order creation in chat or order OCR), one invoice per order, one unit per order line (the owner confirms the unit when linking, D-26), no price-change revisions, no reminders for tasks, no monthly-pack section yet (UAT10). Guided setup, permission preflight and routing policies (U2 §14–17) are not built. The CA is the purchase reviewer (D-24).
* Telegram member check: Switch 0.31.0 reports display names and doesn't notice when someone leaves a Telegram group. An ambiguous or unknown name withholds the message, but a pass means only "no known unauthorized member", not a verified audience. After a removal, replies stay withheld; the recovery is a fresh group plus `python -m scripts.admin rebind-room`.
* Purchase assurance is optional and off by default. Automated tests and a Mattermost live run cover it. Its full Telegram workflow still needs independent staff accounts for manual verification, so it isn't presented as verified end to end on Telegram.
* Scope: INR domestic B2B purchase tax invoices only. Assure Flow does **not** file GST returns, verify live GSTIN
  registration, or decide ITC eligibility. Amounts are "tax associated with an issue", never "money lost". The CA
  files separately.
