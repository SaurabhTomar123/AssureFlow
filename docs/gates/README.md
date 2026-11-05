# Phase gates (v1.0.0-hackathon)

Evidence for every checklist item, one file per phase. **Done** = implemented with an offline test.
**Live** = also executed against Switch 0.31.0 + Mattermost (`docs/release/live-run-2026-11-05.md`).
**Human** = needs a person outside the codebase (sign-off, video).

Offline evidence: `make acceptance` → `docs/release/acceptance-*.json` (85/85). Live: `LIVE=1 pytest tests/live` (4 passed).

| Phase | File | Status |
|---|---|---|
| P0 Foundation and integration | [P0.md](P0.md) | Done, Live |
| P1 Evidence-backed intake | [P1.md](P1.md) | Done, Live |
| P2 Rules and exception ownership | [P2.md](P2.md) | Done |
| P3 Resolution and authorized review | [P3.md](P3.md) | Done, Live |
| P4 Monthly snapshot and evidence pack | [P4.md](P4.md) | Done, Live |
| P5 Recovery, reproducibility, submission | [P5.md](P5.md) | Done, Live; video Human |
| P6 Reconciliation (early, post-MVP) | [P6.md](P6.md) | P6-01..05 Done/Live; P6-06/07/09 not started |
| P7–P9 Production | — | Not started (needs CA + security owner sign-off) |
