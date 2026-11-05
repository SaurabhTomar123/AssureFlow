# Phase gate status: v1.0.0-hackathon (offline evidence)

Legend: **Done** = implemented and covered by an offline test. **Deferred** = "Deferred — hackathon cut" (spec s.10),
listed in README *Known limitations*. **Live** = executed against a real Switch 0.31.0 server (`docs/release/live-run-2026-11-05.md`).

Evidence: `python -m scripts.acceptance` → `docs/release/acceptance-*.json` (62/62 offline tests passing at the time of writing).

## P0 Foundation and integration
| Item | Status | Evidence |
|---|---|---|
| P0-01..03 skeleton, Docker, Makefile | Done | `pyproject.toml`, `Dockerfile` (3.12-slim, non-root, HEALTHCHECK), `docker-compose.yml`, `Makefile` |
| P0-04 migration | Done | `migrations/versions/p0_foundation.py`; up/down/up verified |
| P0-05/06 scopes, contexts, grants | Done | `domain/scope.py`, `domain/context.py`; R16 test |
| P0-07 seed + reset (demo/test only) | Done | `seed/loader.py` |
| P0-08/09 pinned Switch, all-event delivery | Done + **Live** (unaddressed uploads and replies processed) | `adapters/switch_client.py` |
| P0-10/11 durable inbox, code classification | Done | `adapters/inbox_writer.py`, `domain/services/inbox.py`; R19 offline |
| P0-12/13 rooms.yaml, intake tools | Done | `agents/rooms.yaml` |
| P0-14 queue: leases, fencing, dead-letter | Done | `workers/queue.py`; R12 |
| P0-15 idempotency, correlation, envelope, /healthz /readyz | Done | `api/main.py`; API tests |
| P0-16..18 receipt, fetch_and_store, ordered outbox | Done | handlers; R08 |
| P0-19 health | Done | `scripts/health.py` |
| P0-20 live photo+PDF | Done + **Live** (stored SHA-256 = original for PDF and PNG; two messages per upload) | `docs/release/live-run-2026-11-05.md` |
| P0-21..23 context, fencing, recovery tests | Done | `test_api.py`, `test_reliability.py` |
| P0-24 clean clone health | Partial | `make health` all PASS after bootstrap on this machine; clean-clone rehearsal pending |

## P1 Evidence-backed intake
| Item | Status |
|---|---|
| P1-01/02 slow lane, subprocess pool, model timeout | Done (R10) |
| P1-03/04 ExtractionSchema v1, material fields | Done (`domain/extraction.py`) |
| P1-05 single extraction path | Done (`adapters/llm.py`, worker only) |
| P1-06 per-page quality check | **Deferred** (whole document goes to vision if any page fails) |
| P1-07 fake provider by SHA-256 | Done |
| P1-08..14 stable case, generations, replacement, typed correction, confirm | Done (R13, workflow tests) |
| P1-16/17 summary, one question, thread/case-ID replies | Done |
| P1-18..21 fixture, ordering, CPU-kill, replay tests | Done |

## P2 Rules
P2-01..18 **Done**: `rules/` (domain_goods_v1), arithmetic contract, R-DOC/GSTIN/TAX/AMT/PART/DUP, duplicate keys,
routing, exposure once per component, golden fixtures, hypothesis property tests.

## P3 Resolution and authorized review
| Item | Status |
|---|---|
| P3-01..03 CA room, review requests, handoffs, clarification vs supplier paths | Done |
| P3-04 compensation notices | **Deferred** (backend still rejects every stale action) |
| P3-05 digests/quiet hours | **Deferred**; outbox audience recheck **Done** (R17) |
| P3-07 CA action model | Done for include, exclude, resolve_issue, request_owner_clarification, request_supplier_replacement; override/reopen **Deferred** ("not available in this release") |
| P3-08..14 parser, fresh CA context, version binding, tests | Done |

## P4 Monthly snapshot
| Item | Status |
|---|---|
| P4-01..05 periods, UNASSIGNED, frozen manifest, atomic approval | Done (R14, R15, P4-11); P4-05 compensation notice **Deferred** |
| P4-06 practice home + directory | **Deferred** |
| P4-07/08 formula-safe Excel, reproducible JSON, reauthorized download | Done (P4-13 test) |
| P4-09 tools | Done except `list_directory` (deferred) |

## P5 Recovery and submission
| Item | Status |
|---|---|
| P5-01 chaos (slow lane), P5-02 delivery assertions, P5-03 delayed grants | Done (R10, R08, R16) |
| P5-04 injection, P5-05 isolation matrix, P5-06 per-shop model sessions | Done (`metadata.user_id` per shop) |
| P5-07 operations / synthetic testing rooms | **Deferred** (`make health`, `make acceptance`) |
| P5-08 tool inventory | Done (`agents/rooms.yaml` ↔ `api/routers/tools.py`) |
| P5-09 R01–R19 | Offline rows Done; R19 and R05 (hashes, verified sender, unmapped sender rejected) **Live**; R01, R02, R04 pending |
| P5-10 trace command | **Deferred**; correlation ids in logs |
| P5-11 clean-clone rehearsal, video, tag | **Pending** |
