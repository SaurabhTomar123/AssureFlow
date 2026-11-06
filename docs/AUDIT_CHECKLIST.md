# Assure Flow audit checklist

Release `v1.0.0-hackathon` · branch `rebuild/assure-flow` · Flip the Switch hackathon, Track 1 (Best Business Workflow)
Submission deadline: **2026-11-07, 11:59 PM IST**

Use this list before submitting, after any merge, and whenever someone asks "does it really do that?".
Every row says how to check it and what you should see. Run the commands from the repository root with the
virtual environment active.

**Status key**
- ✅ checked on 2026-11-06 (result shown)
- ⬜ still to do
- 👤 needs a person (cannot be done in code)
- ⚠️ known gap, written down in the README

---

## A. Hackathon submission

| ID | Check | How to check | Expected | Status |
|---|---|---|---|---|
| A-01 | Judges are sent to the right branch | Repository link in the submission form points at `rebuild/assure-flow` (or `main` once it holds this code) | The link opens this README | ⬜ |
| A-02 | Repository is public | Open the link in a private browser window | Opens with no login | ⬜ |
| A-03 | Demo video recorded and linked | Video shows a real Switch room: upload → correction → CA review → GSTR-2B → approval → Excel/JSON | Under the time limit in the rules; link works when logged out | 👤 |
| A-04 | README explains how Switch is used | README section "How Switch is used" | Says what breaks without Switch | ✅ |
| A-05 | Licence present (if the rules ask for one) | `ls LICENSE*` | A licence file the team has chosen | ⬜ none yet |
| A-06 | Release tag pushed | `git ls-remote --tags origin v1.0.0-hackathon` | One line for the tag | ⬜ local only |
| A-07 | Team members and roles listed on the form | Submission form | Matches the people who built it | 👤 |
| A-08 | Submitted before the deadline | Submission confirmation email | Timestamp before 2026-11-07 23:59 IST | 👤 |

## B. Clean clone and build

| ID | Check | How to check | Expected | Status |
|---|---|---|---|---|
| B-01 | Fresh clone installs | Follow README "Quickstart" in a new folder | No errors | 👤 rehearsal pending |
| B-02 | Dependencies are pinned | `requirements.lock` | Exact `==` versions (includes `anthropic`, `fastapi`, `websockets`) | ✅ |
| B-03 | Database starts | `docker compose up -d db` | PostgreSQL 16 on 127.0.0.1:5433 | ✅ |
| B-04 | Migrations go up, down and up | `alembic upgrade head && alembic downgrade base && alembic upgrade head` | No errors | ✅ |
| B-05 | Docker image builds and runs the right app | `docker compose up -d --build api worker` then `curl localhost:8000/healthz` | 200; image runs `api.main:app` as non-root on Python 3.12 | ✅ Dockerfile and Compose checked; image build to repeat in B-01 |
| B-06 | Offline demo needs no keys or servers | `make demo` | Room transcripts from upload to export | ✅ |

## C. Code quality

| ID | Check | How to check | Expected | Status |
|---|---|---|---|---|
| C-01 | Offline test suite | `make test` | **85 passed** | ✅ 85 passed |
| C-02 | Tests fail if the database is missing | Stop the db, run `make test` | Errors, **not** skips | ✅ |
| C-03 | Lint | `make lint` | `All checks passed!` | ✅ |
| C-04 | Type check (strict) | `make typecheck` | `no issues found in 58 source files` | ✅ |
| C-05 | Acceptance report | `make acceptance` | `docs/release/acceptance-*.json` shows 85/85 | ✅ |
| C-06 | Live tests against Switch | `LIVE=1 python -m pytest tests/live` | 4 passed, 1 skipped (R02 is manual) | ✅ 2026-11-05 |

## D. Use of Switch (judging criterion 1)

| ID | Check | How to check | Expected | Status |
|---|---|---|---|---|
| D-01 | Switch version pinned | `make health` | `switch version pinned 0.31.0` | ✅ |
| D-02 | Agent receives every room event over WebSocket | Upload a file in a shop room **without** mentioning anyone | `Received R-…` reply | ✅ live |
| D-03 | Agent creates and binds all six rooms itself | `python -m scripts.admin create-rooms …` on an empty server | Six `af-*` rooms appear | ✅ live |
| D-04 | Work moves between rooms | Wrong-tax invoice in a shop room | Review request appears in `af-ca-review`; supplier draft comes back to the shop room | ✅ live |
| D-05 | Files are delivered through Switch | Approve a snapshot | Excel and JSON attached in `af-ca-review` | ✅ live |
| D-06 | Live member check before each message | Add an unexpected user to a shop room, trigger a reply | Message withheld; alert in `af-operations` | ✅ live |
| D-07 | Nothing bypasses Switch | `git grep -nE "telegram\|whatsapp\|slack_sdk" -- api domain workers adapters` | No direct chat-platform calls | ✅ |
| D-09 | Same workflow on a second chat platform (Telegram) | Section M below, using [MANUAL_TEST_GUIDE.md](MANUAL_TEST_GUIDE.md) | All required Telegram tests pass with no code change | ⬜ |
| D-08 | It stops working without Switch | Stop the Switch stack, send a message | No intake, no replies; health shows `switch server` FAIL | ⬜ show in the video |

## E. Security and isolation

| ID | Check | How to check | Expected | Status |
|---|---|---|---|---|
| E-01 | Every business route needs a token and a request context | `python -m scripts.isolation_matrix` | Every route and MCP tool refuses another shop and another practice | ✅ |
| E-02 | Agents cannot decide or approve | `POST /tools/decisions` with a valid token | Always 403 | ✅ |
| E-03 | Shop A never sees shop B | Isolation matrix; `test_api.py` | Refused / not found | ✅ |
| E-04 | Owners never see the CA room | Outbox audience check (`test_reliability.py`, R08) | Message withheld | ✅ |
| E-05 | Background jobs run under narrow grants | R16; scheduled grants allow `notify` only | Revocation cancels the job visibly | ✅ |
| E-06 | CA decisions bound to revision and check run | R04/R19 | A stale decision is refused | ✅ live |
| E-07 | Invoice text cannot give instructions | Prompt-injection fixtures (P5-04) | Text treated as data | ✅ |
| E-08 | No secrets in the repository | `git grep -nIE "sk-ant-\|PRIVATE KEY"`; `git check-ignore data .env` | No matches; both ignored | ✅ |
| E-09 | No hard-coded signing secrets or default passwords in code | Review `common/settings.py` | Secrets only from the environment | ✅ |
| E-10 | `.mcp.json` not committed | `git ls-files .mcp.json` | Empty (D-22) | ✅ |

## F. Money and GST rules

| ID | Check | How to check | Expected | Status |
|---|---|---|---|---|
| F-01 | No floating-point money | `git grep -nE "\bFloat\b" -- domain rules` | No matches; amounts are `Numeric` / `Decimal` | ✅ |
| F-02 | Rounding once, half-up to paise | `rules/arithmetic.py`; golden and hypothesis tests | Tests pass | ✅ |
| F-03 | Separate tolerances | `.env.example` | Tax ₹0.01 per line, total ₹1.00 | ✅ |
| F-04 | GSTIN wording | Shop-room replies | "structure passed", never "registered" or "valid" | ✅ |
| F-05 | Unsupported cases are held, not guessed | Credit note fixture F15; combined-rate fixture F14 | Held with a reason | ✅ |
| F-06 | Overrides only on overridable rules and listed in the export | `RR-… override R-DUP-01 …` | Refused; R-PART-01 / R-DUP-02 allowed and shown in Excel | ✅ |
| F-07 | GSTR-2B match is review support only | README and room text | No ITC eligibility claim | ✅ |
| F-08 | Nothing says "money lost" or "audit protection" | `git grep -niE "money lost\|audit protection\|tax saved" -- . ':!docs/archive'` | Only as "not money lost" or in the forbidden-wording list (`rules/routing.py`) | ✅ |

## G. Data safety

| ID | Check | How to check | Expected | Status |
|---|---|---|---|---|
| G-01 | All data is synthetic | `seed/practice.yaml`, `seed/fixtures/` | Made-up shops, people and GSTINs | ✅ |
| G-02 | Reset cannot wipe a real database | `ENVIRONMENT=pilot python -m seed.loader` | `refusing to reset in environment 'pilot'` | ✅ |
| G-03 | Database environment must match config | `make health` | `environment db=demo config=demo` | ✅ |
| G-04 | Originals are never changed or deleted | Append-only trigger `af_forbid_mutation`; SHA-256 equals the uploaded file | Update/delete on protected tables fails | ✅ |
| G-05 | Tests use their own database | `tests/offline/conftest.py` | Points at `assureflow_test`, never the demo DB | ✅ |

## H. Reliability

| ID | Check | How to check | Expected | Status |
|---|---|---|---|---|
| H-01 | Stale workers cannot commit (lease fencing) | R12 | Old lease rejected | ✅ |
| H-02 | Killing extraction mid-run recovers | R10 | Job retried, case continues | ✅ |
| H-03 | Restart keeps state | Restart worker and adapter | Cursor resumes, no duplicate replies | ✅ live |
| H-04 | Duplicate jobs not reported as new | `workers/queue.py` uses `RETURNING` | Duplicate enqueue returns False | ✅ |
| H-05 | Worker loops survive errors | `workers/runner.py` | Loop logs, waits 5 s, continues | ✅ |
| H-06 | Dead jobs alert operations | Force a job to fail past max attempts | Alert in `af-operations` | ✅ |
| H-07 | Health is all green | `make health` | 12 PASS | ✅ 12 PASS |

## I. Documentation matches the code

| ID | Check | How to check | Expected | Status |
|---|---|---|---|---|
| I-01 | Test count in README equals the real count | `make test` vs README | Both 85 | ✅ |
| I-02 | Room list in README equals `agents/rooms.yaml` | Compare | Six rooms | ✅ |
| I-03 | Tool list equals the room allow-lists | `test_tool_inventory_matches_room_allow_lists` | Passes | ✅ |
| I-04 | Every phase item has evidence | `docs/gates/P0.md` … `P6.md` | Each row names a file or test | ✅ |
| I-05 | Decisions recorded | `docs/decisions.md` | D-01 … D-23 | ✅ |
| I-06 | Limitations stated honestly | README "Known limitations" | R02 manual, JSON relay bug, P6-06/07 and P7–P9 not started | ✅ |
| I-07 | No claim the code does not support | Read README top to bottom against the demo | Nothing promised that the demo cannot show | ✅ |

## J. Demo rehearsal (do this before recording)

| ID | Check | Expected | Status |
|---|---|---|---|
| J-01 | Switch stack up, `make health` all PASS | 12 PASS | ✅ |
| J-02 | Fresh database: `alembic downgrade base && alembic upgrade head && python -m seed.loader` | Empty case list | ⬜ |
| J-03 | Shop room: blurry photo F13 → correction → `ok INV-… r2` | Confirmed, checks run | ⬜ |
| J-04 | Shop room: F08 wrong tax type → CA `supplier` → F16 replacement | Same case, version 2, review request withdrawn with a notice | ⬜ |
| J-05 | CA room: `gstr2b sharma 2026-11` with the Excel file | RC-… with all five classes | ⬜ |
| J-06 | CA room: `snapshot` → `approve SN-… <hash>` | Excel + JSON attached | ⬜ |
| J-07 | Operations room: `trace INV-0001` | Full event history | ⬜ |
| J-08 | Isolation shown on camera | Gupta's room shows none of Sharma's invoices | ⬜ |

## K. Branch hygiene

| ID | Check | How to check | Expected | Status |
|---|---|---|---|---|
| K-01 | Submission branch is clean and pushed | `git status -sb` | `## rebuild/assure-flow...origin/rebuild/assure-flow`, nothing to commit | ✅ |
| K-02 | `main` is not linked to judges until fixed | See the review of `origin/main` (ab38963) | Docker serves the old `src/` app; tests clash on the `shops` table; most routes unauthenticated; hard-coded JWT secret; float money | ⚠️ |
| K-03 | Teammate features ported properly (optional) | Each port uses Switch rooms, `Decimal`, scoped tools and tests | Done the same way as the GSTR-2B port | ⬜ |

## L. Not in this release (stated in the README)

| Item | Why |
|---|---|
| Live test R02 (fresh LLM-agent briefing) | Needs an LLM agent in a room; checked by hand |
| GSTR-2B as `.json` through Mattermost | Switch 0.31.0 bridge bug (D-18); Excel works |
| P6-06 credit/debit-note profiles, P6-07 eligibility evidence | Need examples approved by a CA |
| P7 security and operations, P8 pilot, P9 filing | Need a practising CA and a named security owner |

## M. Real Telegram end-to-end (manual)

Run by a person with at least two Telegram accounts (owner and CA), following
[MANUAL_TEST_GUIDE.md](MANUAL_TEST_GUIDE.md). The test ids refer to that guide.

| ID | Check | Guide | Expected | Status |
|---|---|---|---|---|
| M-01 | Bot created, Group Privacy off, Telegram connected to Switch with no error | §3–4 | Connection listed under Messaging Apps | ⬜ |
| M-02 | Groups created with exact titles, bot added, `assure-flow` invited | §5 | `!list-agents` shows `assure-flow`; no privacy warning | ⬜ |
| M-03 | Rooms bound | §6 `bind-rooms --prefix "Telegram: "` | `BOUND` for each created group | ⬜ |
| M-04 | People bound with their Telegram usernames; `make health` PASS | §7 | No unmapped senders left | ⬜ |
| M-05 | Upload without a mention; summary; confirm | T-01, T-02 | Summary, then confirmed | ⬜ |
| M-06 | Stored SHA-256 equals the sent file | T-03 | Hashes equal | ⬜ |
| M-07 | Correction, hold, duplicate, split | T-04 – T-08 | As described in the guide | ⬜ |
| M-08 | Handoff to CA, supplier replacement, withdrawal notice | T-09, T-10 | Same case, version 2; RR withdrawn | ⬜ |
| M-09 | CA decisions, including a refused override and a refused stale decision | T-11, T-12 | Allowed and refused exactly as listed | ⬜ |
| M-10 | Isolation: owner never sees the CA room, shop A never sees shop B | T-13, T-14 | No leaks | ⬜ |
| M-11 | Wrong person in a room → message withheld and alert raised | T-15 | No reply in the room; alert with ids only | ⬜ |
| M-12 | Unbound stranger ignored | T-16 | No data in any reply | ⬜ |
| M-13 | GSTR-2B Excel reconciled; JSON result recorded | T-17 | RC summary; JSON outcome written in notes | ⬜ |
| M-14 | Snapshot approved by hash; Excel + JSON arrive in Telegram; wrong hash refused | T-18 | Two files in the group | ⬜ |
| M-15 | Practice home and operations rooms | T-19, T-20 | Correct answers; alerts visible in operations | ⬜ |
| M-16 | Worker restart, adapter restart, Switch down, revoke | T-22 – T-25 | Processed once; no replays; nothing without Switch; revoked user ignored | ⬜ |
| M-17 | Results sheet filled in, with tester, date and commit | Results sheet | Attached to the release notes | 👤 |

Telegram differences to note in the results: the bot cannot create groups (rooms are created by hand and
bound by name); agents appear as name-prefixed messages from one bot; Switch reports only members who have
posted, so the live member check cannot see silent members (the declared-audience check still applies).

---

### Sign-off

| Role | Name | Date | Notes |
|---|---|---|---|
| Builder | | | |
| Reviewer (second person ran sections B, C, J) | | | |
