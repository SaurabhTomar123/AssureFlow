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
exception to the **person who owns it**, and ends the month with a **frozen, hash-approved review pack**
(Excel + JSON) that the CA can trust and reproduce.

## How Switch is used (and why it would not work without it)

Switch is the collaboration layer: every channel is a room, people and the `assure-flow` agent share it, and
work moves between rooms. Assure Flow owns the records, checks, state and approvals.

| Room | Who is in it | What happens there |
|---|---|---|
| `af-shop-sharma`, `af-shop-gupta` (one per shop) | that shop's owner + `assure-flow` | Send bill photos/PDFs (no @mention needed), answer focused questions, correct values, confirm, send supplier replacements, ask `status` / `why-held` |
| `af-ca-review` | the assigned CA + `assure-flow` | Review requests (RR-…) with evidence and rule results; decisions by reply; monthly pack approval by hash; Excel/JSON delivered as files |

* **Room isolation is the product.** Shop A never sees shop B, and owners never see the CA room. Every message
  passes a disclosure check right before delivery: if someone who shouldn't see it is in the room, it is
  withheld.
* **Handoffs between rooms.** A tax exception found in a shop room is handed off (data only, no authority) to the
  CA room. A CA's "ask the supplier" goes back to the shop room as a ready-to-send draft. The corrected bill
  comes back into the same case.
* **Every room event is consumed by code.** The adapter connects to Switch as an agent over the WebSocket protocol
  and reads all events (`filter=all`). An upload or a CA reply works without mentioning anyone.

## Walkthrough (what you see in the rooms)

```
#af-shop-sharma  Ramesh: [photo of bill A108]
#af-shop-sharma  assure-flow: Received R-0001 … saved as INV-0001 … Total: ₹1,780.00 <- uncertain (page 1)
#af-shop-sharma  Ramesh: INV-0001 total=1180.00          (typed correction, no re-reading)
#af-shop-sharma  Ramesh: ok INV-0001 r2
#af-ca-review    assure-flow: RR-0001 · INV-0001 r2 · All required checks passed. Reply `RR-0001 include` …
#af-ca-review    assure-flow: RR-0002 · INV-0002 · R-TAX-01: Interstate supply (27 to 07) must use IGST only …
#af-ca-review    Ramesh: RR-0002 include      -> "You are not authorized for that action here."
#af-ca-review    CA Mehta: RR-0002 supplier please reissue with IGST
#af-shop-sharma  assure-flow: INV-0002 is waiting for a corrected invoice … Draft you can send: …
#af-shop-sharma  Ramesh: corrected bill for INV-0002 [PDF]   -> same case, version 2, checks rerun
#af-ca-review    CA Mehta: RR-0002 include   -> "That refers to an older version. Nothing was changed."
#af-ca-review    CA Mehta: RR-0003 include
#af-ca-review    CA Mehta: snapshot sharma 2026-11
#af-ca-review    assure-flow: SN-0001 · hash 21b70bbe1c63 · Included 2 · held 1 · PARTIAL …
#af-ca-review    CA Mehta: approve SN-0001 21b70bbe1c63 ack 1 0
#af-ca-review    assure-flow: PARTIAL SN-0001 export: Excel + JSON attached.
```

Run it yourself without any keys or servers: `make demo` (prints every room transcript).

## Architecture

```
 Switch rooms (Mattermost / Telegram / Slack…)                     Assure Flow (Docker Compose)
 ┌──────────────────────┐   WebSocket events (all)   ┌─────────────────────────────────────────────┐
 │ shop rooms · CA room │ ─────────────────────────▶ │ adapter → inbox_events (durable, cursor)     │
 │  people + assure-flow│ ◀───────────────────────── │ worker: fast | io | slow lanes + outbox      │
 └──────────────────────┘   HTTP: message / media    │   process_inbox_event → receipt → fetch_and_ │
                                                     │   store → extract_document → run_checks →    │
                                                     │   review request → build_snapshot → export   │
                                                     │ domain: CaseWorkflow (pure process manager), │
                                                     │   state table, CA action model, rules (Decimal)│
                                                     │ API: scoped business tools (token + context) │
                                                     │ PostgreSQL 16 (authoritative) · file store   │
                                                     └─────────────────────────────────────────────┘
```

**What makes it trustworthy**

* **Stable case + revisions.** A case exists from the moment the original is preserved (SHA-256,
  content-addressed, never deleted). Typed corrections create a new revision with no re-reading. Replacement
  documents create a new *document generation*, and only the newest generation can become current.
* **Deterministic checks** (`rules/`, profile `domestic_goods_v1`): GSTIN structure and check character
  ("structure passed", never "registered"), recipient GSTIN, tax type vs place of supply (IGST Act s.7/8), line
  arithmetic, per-component tax from printed rates, invoice total, required particulars, duplicates.
  `Decimal` throughout, half-up rounding to paise once at the printed level, separate tax (₹0.01/line) and
  total (₹1.00) tolerances. Unsupported cases (credit notes, combined-rate-only, cess, non-INR) are **held**,
  never guessed.
* **Authority.** Every workflow action uses an *interactive context* created from one verified room event, and
  every background job runs under a narrow *execution grant* (one operation, one target, revocable). CA
  decisions need a fresh context from the CA's own reply and are bound to the exact revision and check run.
  Agents can never confirm, decide or approve.
* **Consistency.** Lease fencing tokens on every job commit; shop-period versions locked atomically at approval
  (a bill arriving mid-approval makes the pack `SNAPSHOT_STALE`); a frozen, canonical-JSON manifest whose
  SHA-256 the CA approves; exports render only from that manifest (byte-identical JSON, formula-safe Excel).
* **Delivery.** One business action and one logical outbox record per action; ordered per room; at-least-once
  transport with stable action ids; the audience is rechecked before every send.

## Quickstart (offline: no Switch, no API key)

Prerequisites: Docker, Python 3.12+.

```bash
git clone https://github.com/SaurabhTomar123/AssureFlow.git && cd AssureFlow
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.lock && pip install pytest hypothesis ruff mypy
cp .env.example .env
docker compose up -d db                              # PostgreSQL 16 on 127.0.0.1:5433
python -m alembic upgrade head
make demo        # the full correction-to-export story, printed as room transcripts
make test        # 62 offline tests: rules, workflow, authority, isolation, fencing, snapshots, export
make acceptance  # machine-generated report in docs/release/
```

## Run with Switch (live)

1. Start a Switch server, pinned to **0.31.0**. Either use Switch Console (desktop app, "Add a server") or
   Switch's standalone stack from the `switch-v0.31.0` tag of
   [sandbox-quantum/switch](https://github.com/sandbox-quantum/switch):
   `docker compose -f deploy/local/standalone-docker-compose.yml --profile collab --profile gateway up -d`
   (bundles Mattermost). Set `SWITCH_BASE_URL` and `SWITCH_SERVER_VERSION=0.31.0` in `.env`.
2. In the Switch Gateway, create a **registration** API key. Then run
   `SWITCH_REGISTRATION_KEY=… python -m scripts.admin register-agent`. This registers the `assure-flow`
   agent and saves its credentials to `data/`.
3. Let the agent create and bind the rooms through Switch (on the default bridge, e.g. Mattermost), mapping each
   seeded person to their chat username: `python -m scripts.admin create-rooms owner.sharma=<user>
   owner.gupta=<user> ca.mehta=<user>`. (Or create them yourself, invite `assure-flow`, and run `bind-rooms`.)
4. Start the stack: `docker compose --profile switch up -d --build` (api, worker, adapter).
5. Have each person send one message, then map identities. `python -m scripts.admin unmapped` lists the
   unmapped senders; bind each one with `python -m scripts.admin bind-user @switch-user-…:server owner.sharma`.
6. `make health` should be all PASS. Send `seed/fixtures/F13_blurry_photo.png` into `af-shop-sharma`.

To use real extraction instead of recorded fixtures, set `LLM_PROVIDER=anthropic` and `LLM_API_KEY`
(model `claude-opus-5-5`, vision + JSON-schema output).

## Room commands

**Shop room:** send a file · `ok INV-0001 r1` · `ok INV-0001 hold` · `INV-0001 total=1180.00 date=2026-11-03` ·
send a file with `INV-0001` in the message to replace a document · `status` · `pending` · `why-held INV-0001` · `help`

**CA room:** `RR-0001 include` · `RR-0001 exclude <reason>` · `RR-0001 resolve <RULE-ID> <reason>` ·
`RR-0001 clarify <question>` · `RR-0001 supplier <reason>` · `readiness sharma 2026-11` ·
`snapshot sharma 2026-11` · `approve SN-0001 <hash-12> [ack <held> <unassigned>]` · `assign INV-0001 2026-11` · `pending`

## Repository map

`api/` FastAPI and scoped business tools · `domain/` models, state table, `CaseWorkflow`, CA actions, periods,
services · `rules/` deterministic checks · `workers/` queue, lanes, CPU pool, handlers, outbox · `adapters/` Switch
client, inbox writer, storage, PDF, Claude extraction, Excel · `agents/rooms.yaml` · `migrations/` one revision per phase
· `seed/` 20 synthetic fixtures + recorded extractions + expected outcomes · `tests/offline/` ·
`docs/` decisions, gate status, OpenAPI, release reports

## Known limitations (v1.0.0-hackathon)

Deferred by the spec's hackathon cut. Each one replies "not available in this release" or is absent; none is
implied to work.

* No practice-home room or directory; no operations or synthetic-testing rooms (`make health` and
  `make acceptance` instead).
* No daily digests, quiet hours or escalation; pending work is shown on request.
* No compensation notices. The backend still rejects every stale decision, confirmation and approval, so room
  history can be outdated but never acted on.
* CA `override` and `reopen` are not available. Multi-invoice files are held, with the owner asked to send one
  per file. Per-page text/vision merging is replaced by whole-document vision when any page is weak.
* No `trace <case>` command; correlation ids are in the logs.
* The business tools are an authenticated HTTP API. The MCP wrapper is deferred (docs/decisions.md D-07).
* The full workflow has been run live against Switch 0.31.0 + Mattermost (`docs/release/live-run-2026-11-05.md`);
  automated live tests R01, R02 and R04 have not been run.
* On Switch's standalone stack, the deployment's admin accounts are members of every room. Assure Flow's
  disclosure check uses the declared audience in `agents/rooms.yaml`, not Switch's live member list.
* Scope: INR domestic B2B purchase tax invoices only. Assure Flow does **not** file GST returns, verify live GSTIN
  registration, or decide ITC eligibility. Amounts are "tax associated with an issue", never "money lost". The
  CA files separately.
