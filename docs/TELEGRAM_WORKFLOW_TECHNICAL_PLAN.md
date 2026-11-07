# Assure Flow: Telegram workflow technical plan

Date: 6 November 2026
Implements: [TELEGRAM_WORKFLOW_IMPROVEMENT_SPEC.md](TELEGRAM_WORKFLOW_IMPROVEMENT_SPEC.md)
Evidence: [telegram-manual-2026-11-06.md](release/telegram-manual-2026-11-06.md)
Baseline: commit `7cd5076` on `feature/purchase-assurance`, the commit under test. Switch `switch-core:0.31.0`.
Status: P0 code fixes implemented and offline-tested, not yet committed or verified live (section 12). Everything else is planned, not built.

## Decisions (6 November 2026)

| Question | Decision |
|---|---|
| Purchase assurance in the submission? | **Yes, as an optional feature behind its flag.** The main demonstration stays on the verified journey: invoice upload → correction → CA review → supplier replacement → reconciliation → monthly pack. Describe it honestly: automated coverage exists, the full Telegram workflow still needs independent staff accounts, and it isn't presented as verified end to end. The release-branch decision remains open. |
| Scope | The tighter priority order in section 12. The setup wizard, general LLM layer, dynamic agent creation and broad bridge buttons are deferred. `rebind-room` stays in the cut while the bridge membership fix is deferred. |
| Estimates | Planning assumptions only. Reserve time for verification before spending the whole budget on implementation. |
| Live reruns | Targeted regressions after P0, then a short owner and CA journey after the message work. Earlier tests aren't repeated for every wording change. |
| Process attribution | An attributed addendum in the test report, keeping the original account. T-23 still needs a controlled rerun. |

## 1. Summary

**Three of the six observed failures are small fixes in our own code.** FIX-01 and FIX-02 are gaps in the transition table and the override handler. FIX-04 can be avoided by sending one file per outbox row.

**FIX-03 and half of FIX-05 are limits of the Switch Telegram bridge.** They need a reproducible patch to Switch or a documented workaround.

**FIX-06 has an identified cause, and it is not an unknown launcher.** The processes the report could not attribute were started by a Claude Code session working in the same repository during the test (section 3, FIX-06). The requirement stands, because nothing stopped two sessions from running competing processes. T-22's early attempts and T-23 were affected, and T-23 should be rerun.

**Buttons are the largest unknown.** Switch 0.31.0 can draw Telegram buttons, but only on session approval cards. `POST /message` has no way to attach them. P1 therefore ships reply-based actions first, and buttons follow a time-boxed spike (section 6).

**Only part of this fits before the deadline.** About 26 hours remained when this was written (submissions close 7 November, 11:59 PM IST). Section 12 sets the cut: the small P0 fixes and the plain-English rewrite of whole message families. Onboarding, the LLM layer and agent provisioning wait for the next release.

### How claims are labelled

| Label | Meaning |
|---|---|
| **Code** | Read in this repository at `7cd5076` |
| **Switch** | Read in the running `switch-core:0.31.0` container, under `/app/switch_core/` |
| **Report** | Stated in the live test report; not independently reproduced |
| **Unknown** | Not established; needs the named spike |

## 2. Principles carried into every change

- Every transition stays in `domain/states.py`, and every send stays in the outbox.
- A button press, a reply word and a typed command all run the same domain function, with the same authorization and version checks.
- The member check is never loosened to get a test passing.
- Existing commands keep working, and their tests stay.
- Tests run on the dedicated test database. Never run `seed.loader` or `scripts.demo_offline` without a `.env`, because the settings then default to the live demo database.
- Leave the deleted `seed/fixtures/F09_total_mismatch.pdf` alone. `test_override_only_for_overridable_rules` ingests F09, so confirm how the suite gets that file before running it, and run in a separate worktree if the suite would regenerate it.

## 3. P0: root causes and fixes

### FIX-01: reopening an approved case

**Root cause (Code).** `domain/states.py:60` defines only `(EXCLUDED, "ca_reopen")`, so `st.target` raises `InvalidTransition`. The manual guide promises more than the table allows, and `ca_actions.reopen` has only ever been tested from `excluded`.

**Change.**

1. Add `(APPROVED, "ca_reopen"): NEEDS_RESOLUTION`.
2. In `ca_actions.reopen`, when the case was approved, invalidate its current decisions **before** writing the reopen decision. `Exec._invalidate_decisions` invalidates every decision on the case that isn't already invalidated, so calling it afterwards would also invalidate the reopen record.
3. Keep the rest of the flow: rerun checks, then open a new review request.

**Already handled, needs a test only (Code).**

- `case_event` bumps the period version, so an approved pack is marked outdated and a draft pack goes stale.
- `purchases.on_case_change` runs inside `_transition`.
- `_claim_duplicate_key` uses `on_conflict_do_nothing`, so it's safe when the key is still held.

**Tests.** Reopen an approved case and assert all of the following:

- The prior decision is in `decision_invalidations` and still present in `decisions`.
- Exactly one new check run exists.
- A new review request is open.
- An unapproved draft pack refuses approval.
- An approved pack gets one superseded notice.
- A stale `RR` is refused.
- A second `reopen` is refused cleanly.

### FIX-02: permitted warning override

**Root cause (Code), two defects.**

1. `domain/states.py:49` allows `ca_include_with_override` only from `NEEDS_RESOLUTION`. R-DUP-02 has `WARNING` severity (`rules/checks.py:147`), so a case whose only failure is R-DUP-02 sits in `ready_for_ca`.
2. `ca_actions.perform` looks only at **blocking** issues (lines 180–196). It would do nothing for a warning, even with the transition added. It also never checks that a named rule exists. `RR-1 override R-PART-01,R-FAKE-99 reason` succeeds today, and the reply repeats the made-up rule.

The review message has a related gap: `open_review_request` lists only blocking overridable rules (`domain/services/checks.py:296–299`), so the CA is never offered the R-DUP-02 override.

**Change.** Rewrite the override branch in this order:

1. Parse the named rules. Reject an empty list.
2. Every named rule must match an **open issue on this revision**, otherwise `ValidationFailed`. No success reply may mention a rule that had no issue.
3. Every named rule must have `overridable=True`, otherwise `Forbidden`.
4. Every open **blocking** issue must be named, otherwise `ValidationFailed`.
5. Add `(READY_FOR_CA, "ca_include_with_override"): APPROVED`, then record one `Decision` per named issue and mark it `resolved` / `override`.

List overridable warnings in the review message too.

**Tests.**

- R-DUP-02 override from `ready_for_ca` succeeds. Use F10 and F11 with `number=SDF-5521`, as in the live run.
- The rule, reason, actor, revision and check run appear in the decision and in both exports.
- R-DUP-01, R-TAX-01 and R-AMT-03 are refused from both states.
- An unknown rule and an unrelated rule are refused, with no decision written.
- Keep the existing R-PART-01 test.

**Also fix.** The `ca_actions.py` docstring still says override and reopen are not available.

### FIX-03: stale room membership

**Root cause (Switch; the owner's removal itself is Report).**

- `telegram/adapter.py:130`: `_ALLOWED_UPDATES` is `message, channel_post, my_chat_member, callback_query`. It omits `chat_member`.
- The adapter handles `new_chat_members` (line 2639), and no `left_chat_member` handling appears in the Telegram adapter. Nothing removes a person from the room's clients when they leave.
- `agent_core.py:4061–4076`: `connected_user_names` is the room's stored clients matched to known bridge users. It isn't a current Telegram member list.
- `room_store.remove_client` exists (`db/stores/room_store.py:542`), so the bridge only needs to call it.

**Two further weaknesses in our check (Code, `disclosure.unauthorized_live`).**

- It matches on `chat_username`, which is a display attribute. A renamed person is withheld, which at least fails safe. A person who takes an authorized person's display name would pass the check.
- The lookup has no practice filter and uses `scalar_one_or_none`. Two identities with the same name raise `MultipleResultsFound` inside the outbox dispatch. `chat_username` has no uniqueness constraint.

**The member list has a blind spot.** A person who joined before the bot and has never posted may not be listed at all. Treat the check as "no known unauthorized member", and say so in setup (spec SETUP-05).

**Change.**

| Step | Where | What |
|---|---|---|
| 1 | Repo: `deploy/switch/` | Build `switch-core:0.31.0-af1` from a digest-pinned upstream image plus a tracked patch, with a provenance note. First check whether a newer Switch release already fixes this. |
| 2 | Patch | Handle `left_chat_member` → new `on_user_left` → `remove_client`. Add `chat_member` to allowed updates where the bot has admin rights. A rejoin goes through the existing join path. |
| 3 | Patch | Return stable external ids from `get_room_detail` beside the names. |
| 4 | `disclosure.py` | Match live members by platform id once ids are available. **Built now:** a name that matches no one, several people or another practice fails closed, with no crash. |
| 5 | `scripts/admin.py` | **Built now:** an audited `rebind-room <name> <switch-room-id> <reason>` as the documented recovery. It keeps the old room and its evidence. |

`bind-rooms` no longer replaces a room moved with `rebind-room` unless given `--force`, which closes the trap the report warned about.

**A name is not an identity.** A practice-scoped username match still doesn't establish who someone is, so name matching isn't equivalent to stable-id verification. Until Switch returns ids, a pass means only "no known unauthorized member":

- Ambiguous or unverifiable names fail closed in every room with a required audience check.
- Actions stay safe regardless, because commands are authorized from the sender's stable id.
- What remains exposed is a silent reader: someone who never posts, or who holds an authorized person's display name, might receive a room's messages. This goes in the known limitations and is only fully closed by steps 2 and 3.

**Tests.** Extend `FakeSwitch` with member changes. Unexpected member joins: replies withheld. Member leaves: fresh replies delivered. Earlier rows stay `withheld`. Name changes: identity still matches by id. Duplicate names: fail closed, with no crash. Live AC-09 needs the patched image and a real removal.

**Fallback if the patch doesn't land.** The workaround from the test run stays: a fresh CA group plus `rebind-room`. Record this as a known limitation.

### FIX-04: grouped export not visible

**What is established (Switch, Code, Report).**

- Our handlers post one row with two artifacts (`workers/handlers/__init__.py:322`, `workers/handlers/purchase_match.py:100`).
- `upload_files` sends them as repeated `files` parts, and the bridge uses `send_media_group` (`adapter.py:1256`).
- The bridge records only the first message reference. Our client stores only the first `event_id`, though Switch also returns an `attachments` list.
- Single sends go through `send_attachment`. The same files sent that way were confirmed visible (Report).

**Cause of the invisible album: Unknown.** Don't claim one. The test showed a mapped Telegram message 156 and a user who saw nothing.

**A second truthfulness gap (Switch).** On a `TelegramError`, `send_attachment` falls back to a text notice and still returns a reference. So our outbox `delivered` means "Switch accepted it", not "the file reached Telegram".

**Change.**

1. Post one outbox row per artifact: `export:{snapshot_id}:{artifact_id}`, each with its own caption. Apply it to both handlers.
2. Keep ordering through the existing per-room sequence. A dead row doesn't block later rows, because `_heads` selects pending rows only.
3. `outbox.py` sets `dead` without telling anyone. Add an ops alert, and tell an authorized room which file failed.
4. Add `resend SN-0001 [excel|json]` for the CA. It re-posts the stored bytes with a new action id and refuses if the SHA-256 no longer matches the artifact record. It never rebuilds the pack.
5. Treat `delivered` as "submitted to Switch" in docs and wording. Only a person can confirm a file was seen. Never say "delivered to you".

**Tests.** Two artifacts create two rows. One failing send leaves one `dead`, one delivered, and an alert. `resend` produces identical bytes and no new artifact. Live: confirm two visible files after a fresh, normal approval. If possible, also run one deliberate album send to learn whether the album fault reproduces.

### FIX-05: attachment download failures

**Root cause (Switch).** `adapter.py:3134–3141` calls `get_file` and `download_as_bytearray` once, with no retry. A failure becomes the text `_attachment not relayed: <file> — download failed: <reason>_` in the message body (`collaboration_core.py:1063`). The report recorded such an event as ignored (Report): the inbox sees no attachment and no command (`inbox.py`, `not_a_workflow_event`), so the owner gets no reply from Assure Flow.

**Change.**

| Layer | Change | Depends on |
|---|---|---|
| Our inbox | Recognize the note from a verified sender in a room that accepts files. Reply: "I couldn't download `<file>`, so it hasn't been added. Please send it again." Action id `reply:{event_id}:relay-failed`, so a redelivered event can't reply twice. | Nothing |
| Bridge patch | Retry 3 times with 1s, 3s and 9s backoff, on `NetworkError` and `TimedOut` only | The FIX-03 patch image |

Someone could type that text by hand. The only effect is a harmless prompt to resend, and it creates no case. Don't strip the failure reason from the audit record, but don't show it to the owner either.

**Tests.** The note produces one reply, no receipt, no document and no invoice. A replayed event produces no second reply. A retry test belongs to the patch.

### FIX-06: runtime ownership

**Cause of the unattributed processes.** The test report describes workers and adapters started by an unknown launcher. The evidence matches a Claude Code session working in this repository at the same time:

| Report | Other session's record |
|---|---|
| Worker launcher created 19:57:49 IST | Worker restarted; `worker.started` logged 14:27:51 UTC (19:57:51 IST) |
| Worker launcher PID 19348, started 20:02:02 IST | `Start-Process` returned PID 19348, start time 20:02:02 |
| Replacement adapter 12700 repeatedly `switch.evicted` | Multiple adapters overlapped and evicted each other |
| Adapter launcher 54968, created 20:27:34 IST; "our original replacement is no longer listed" | That session stopped every adapter and worker, including 12700 and 33016, then started 54968 and a new worker |

That session most likely read the tester's deliberate stops as crashes and restarted the processes (the exit notices carry no timestamps). The two sessions were unaware of each other. The evidence and links are in the [test report's addendum](release/telegram-manual-2026-11-06.md#addendum-6-november-2026-added-after-the-run-source-of-the-unattributed-processes). Consequences:

- The T-22 first attempt was inconclusive because of this interference. The second attempt also had a separate download timeout.
- T-23's controlled restart can't be counted. **Rerun T-23** with one session in control.
- T-22's final upload recovery and T-24 weren't affected, as far as the timeline shows.

**Why it could happen at all (Code).** Nothing stops a second adapter. All copies share `connection_id` from the credentials file, so they displace each other. `run_adapter` only exits on `taken_over` or `closed`, and these evictions arrived with `code: null`, so each copy reconnected and kept the cycle going. `scripts/health.py` doesn't check that an adapter or worker is running, as the report also notes.

**Change.**

1. **One adapter per environment.** Hold a Postgres session advisory lock for the life of the process. A second adapter exits at once and names the holder.
2. **Instance registry.** New table `runtime_instances`: role, host, pid, git sha, started_by, started_at, heartbeat_at, stopped_at. Workers register too. Several workers remain safe because of leases, but each one is visible.
3. **`scripts/runtime.py`** with `start`, `stop`, `restart` and `status` for local use, and Compose for deployments. Both pass through the same lock. Stop by registered instance, not by matching command lines.
4. **Eviction guard.** More than 3 evictions in 60 seconds logs an error and exits.
5. **Health report.** Add adapter connected, worker heartbeat, and last inbound event age. Split withheld rows into historical and new, so preserved evidence doesn't fail health forever. Add an acknowledged marker; never delete rows.
6. **Working rule.** Add to the README and test guide: one session owns the runtime during a live test, and a stopped process isn't restarted without checking who stopped it.

**Tests.** A second adapter refuses to start. `status` lists the active instance. A killed adapter's lock releases when its database session ends. Heartbeat expiry shows as stale.

## 4. Switch 0.31.0 capabilities

Everything in P1–P3 depends on this table.

| Capability | State | Source |
|---|---|---|
| Plain messages and file uploads from the agent | Available. `SendMessageRequest` has `room_id`, `content`, `metadata`, and no controls. | `agent/api/schemas.py:99` |
| Inline buttons on Telegram | Only on `RequestCard` and turn status | `telegram/adapter.py:1569–1632` |
| Agent-opened approval or question cards | `POST {session}/approvals` with title, detail, options. Answers from `GET /approvals/outcomes`. | `agent/api/activity_routes.py` |
| Who may press a card, and whether the outcome names them | **Unknown** | Spike S1 |
| Bot pressers identified by Telegram, not by the payload | Yes, from `from_user` | `telegram/adapter.py:2445` |
| Add-to-group link | `?startgroup=<payload>` | `telegram/adapter.py:949–985`, `install.py` |
| Group migration handling | Room is re-pointed when a handler is installed | `telegram/adapter.py:2780–2830` |
| Bot command menu | Published by Switch from its own command list. No role-scoped list for an agent. | `telegram/commands.py` |
| Member leaves | Not handled | FIX-03 |
| Download retry | None | FIX-05 |
| Reply threading | `thread_id` on events. `POST /message` takes no thread id (D-06), though `/media` does. | `decisions.md`, `handlers.py:510` |

### Spikes (time-boxed; each ends in a written note in `docs/decisions.md`)

| ID | Question | Time box |
|---|---|---|
| S1 | Can an always-on agent with no model session open an approval card? Who may answer it? Does the outcome return a verified presser id? What are the title and detail limits? | 4 hours |
| S2 | Can an agent join a room automatically after the bot joins, without `/invite_agent`? Which operations does it need, and does it need more than the current non-admin registration (D-15)? | 2 hours |
| S3 | Is a newer Switch release available that fixes members, retries or message controls? Would upgrading cost less than patching? | 1 hour |
| S4 | Do `?start=` payloads and private chats reach the agent as events? | 1 hour |

## 5. P1: language and action model

### 5.1 One action catalog

Add `domain/actions.py` as the single source of what each person can do next.

```python
@dataclass(frozen=True)
class Action:
    key: str                # "confirm_details"
    label: str              # "Confirm details"
    roles: frozenset[str]   # who may see it
    reply_words: tuple[str, ...]
    command: str            # compatibility form: "ok {case} r{rev}"

def available_actions(s, case, viewer) -> list[Action]: ...
```

`available_actions` gets its answer from `st.TRANSITIONS` plus the same issue checks that execution uses, so a message only offers actions that are valid **when it is written**. Help text, reply parsing, future buttons and the docs table all read from this catalog. A test walks every state and role and asserts that each offered action passes `st.target` and its authorization check at that moment.

**An offered action can stop being valid later.** A correction, a replacement, another person's decision or a revocation can all happen after the message is posted. So the catalog doesn't guarantee execution:

- Execution always revalidates state, version and authority, as it does today, and never trusts that the action was offered.
- When an action has gone stale, the reply explains what changed and offers the current next step, for example "This bill was updated after that message. Please check the latest version." It never shows a raw transition error.
- Tests cover each change between offer and use: a newer revision, a decided review, a rebuilt or stale pack, and a revoked person.

### 5.2 Structured messages

Add `domain/services/copy/`, with a small renderer:

```python
@dataclass
class Card:
    status: str                # "Please check this bill from Modern Agro Staples: total ₹7,770."
    actions: list[Action]
    details: list[str]         # references, tax components, rule codes
```

Default Telegram rendering is the status, the choices, and a short details line. The full details stay available through a `details` reply. Case references stay visible but secondary.

**Inventory first.** User-visible strings are spread across `messages.py`, `ca_actions.py`, `periods.py`, `checks.py`, `reconciliation.py`, `snapshots.py`, `purchases.py`, `readiness.py`, `business_tasks.py`, `compensation.py`, `operations.py` and `inbox.py`. Start by listing every `post(...)` and `replies.append(...)` in a table: role, trigger, current text, new text.

### 5.3 Priority message fixes

These come from the spec's LANG-04 table and the report's observations.

| Fix | Current cause (Code) |
|---|---|
| Correction prompt names the actual missing field | `messages.summary` always ends with `total=1180.00`; the report saw `pos=07` on a missing GSTIN |
| Clarification accepts a free-text answer | `ca_actions.py:277` always says `total=1180.00` (see REVIEW-02) |
| No raw state names | `case.status.replace('_', ' ')` in `ca_actions.py:94`, and the readiness replies |
| No raw transition text | `states.target` puts `'ca_reopen'` in its message, and `error_reply` appends it. Map codes to a sentence and send details to the audit record. |
| Scope refusal doesn't hint at other shops | `ERROR_TEXT["NOT_FOUND"]` |
| Partial pack states its counts in words | `approve … ack 8 1` becomes a two-step confirmation (section 5.4) |
| Purchase hold in plain words | `purchases._announce` |

Keep these unchanged: Decimal amounts, the material tax facts in CA messages, and the statement that ready for payment doesn't mean paid.

### 5.4 Reply-based actions, with no bridge changes

Replying to a bot message already gives us `thread_id`, and `_thread_case_ref` and `_thread_rr_ref` already resolve it (D-06). Extend that:

| Person replies to | With | Runs |
|---|---|---|
| A bill summary | `confirm`, `yes`, `looks right` | `ok INV-x rN` for the revision **that message showed** |
| A bill summary | `the total is 1,180` or `total 1180` | Typed correction |
| A review request | `include`, `exclude <reason>`, `ask <question>` | Existing CA action |
| A pack | `approve` | Step 1: shows the counts. Step 2: `approve these 2 bills, leaving 8 + 1 out` is matched exactly, and the hash is taken from the message being replied to. |

Rules:

- Bind to the revision or hash of the **message replied to**, never the latest one. An older message gets the "this bill has been updated" reply.
- A message with no reply context and more than one open case gets a short chooser. Never choose silently.
- Telegram group privacy limits which messages a bot sees. Group Privacy must be off, as setup already requires.

A small deterministic grammar handles these forms. Amounts with commas parse exactly to `Decimal`. An ambiguous value such as `1.180` or `12/11` gets a question, not a guess.

**Check on replies.** The existing thread lookups read `delivered_event_id`. Live-test that a Telegram reply arrives with `thread_id` set to the bot message's event id. If it doesn't, this section needs the bridge's reference mapping first, and it would become the first P1 task.

## 6. Buttons (UI-01, UI-02)

| Option | Works when | Cost | Risk |
|---|---|---|---|
| **A. Switch approval cards** | S1 shows a sessionless agent can open them and outcomes carry a verified presser id | Low | Built for agent sessions, so polling and limits may not suit case cards |
| **B. Bridge patch**: `controls` on `/message`, presses forwarded as a WebSocket `interaction` event | Always, on the patched image | Medium | Larger patch to carry; needs the same on Mattermost for parity |
| **C. Reply-based only** | Now | Done in P1 | Less discoverable than a button |

**Recommendation.** Ship C in P1. Choose A or B after S1. The domain side is the same for both:

```text
action_tokens
  id (opaque, in the button payload)    practice_id, shop_id, room_binding_id
  action_key                            object_type, object_id
  revision_id or content_hash           allowed_user_id or allowed_role
  expires_at                            used_at, used_by, result
```

Pressing a button writes to the durable inbox like any message, with `kind="interaction"`, and runs through `inbox.process`. On every press:

1. Resolve identity from the bridge-reported presser id, never from the payload.
2. Recheck the role, room audience, object version and `available_actions`.
3. Mark the token used in the same transaction as the domain action. A second press returns the first result.
4. Expired, stale and unauthorized presses get a clear reply and no mutation. Unauthorized replies reveal nothing about other shops.

A press calls the same domain function as a verified human command. It doesn't go through agent tokens, and the MCP and API restriction on agent decisions (`POST /review-requests/{id}/decisions` returns 403 for every agent) stays.

**Command menu (UI-03).** Switch owns the menu, so role-specific entries need the patch. Until then, plain `status`, `pending` and `help` stay available. Also test how a `/status` event reaches us: `inbox_writer` takes the body from `payload.command`, so arguments may be lost.

## 7. P2: guided onboarding (next release)

**Target.** Setup with no terminal, no YAML, no participant ids and no exact group names.

**Administrator surface.** A small server-rendered wizard in `api/routers/setup.py`, protected by an admin credential. It shows a resumable checklist and the one next action.

**New tables.**

```text
setup_sessions   id, practice_id, shop_id, step, status, created_by, timestamps
invitations      id, token_hash, setup_session_id, shop_id, role, expires_at,
                 consumed_at, consumed_by_platform_id
```

**Flow that needs no bridge changes.**

1. The wizard creates single-use, short-lived codes tied to one shop and role, storing only the hash.
2. The administrator adds the bot through the `?startgroup` link.
3. In the group, an authorized person sends `connect ABC123`. The application binds `RoomBinding.switch_room_id` to that room, with the title kept as a display label.
4. Each invited person sends `join XYZ789` from their own account. `sender_ref` from Switch is the verified id, and this creates `ChatIdentity`. A typed username is never proof.
5. An administrator confirms the owner and CA assignments in the wizard. Conflicts and duplicate enrollment are shown, never merged silently.

If S4 shows `?start=` reaches the agent, private-chat enrollment replaces codes posted in groups, which is better because the code stays out of the group.

**Preflight**, all required before setup shows complete:

- The bot sees an ordinary message (Group Privacy check).
- A file round trip, labelled as a test.
- The worker and adapter are up (FIX-06).
- A CA destination is bound and the audience is clean.

State the member-list blind spot in plain words, and fail closed for sensitive output when an audience can't be established.

**Minimal topology.** One owner room plus one private CA room. Delivery appears only with purchase assurance. `agents/rooms.yaml` stays for operations and demos.

`/invite_agent` can only be removed if S2 finds a supported way to attach the agent.

## 8. P3: scoped conversational layer (next release)

```text
verified event → identity and room context → deterministic grammar (5.4)
   → no match, flag on: model returns a typed intent
   → validate → available_actions check → existing domain service → outbox
```

- **New modules:** `domain/intents.py` (Pydantic schema, one allowed intent list per room purpose) and `adapters/intent_llm.py`. Keep it separate from extraction and behind `INTENT_PROVIDER`.
- **Model input:** the user's text, the case summary for the current context, and the allowed intents. Identity, shop and role come from trusted context and are never read from model output. Invoice text is marked as data.
- **Authority:** the model can only choose a card to show. An approval or confirmation still needs the person's own next action, bound to the exact object.
- **Failure:** on a model outage or low confidence, fall back to the chooser and the deterministic grammar.
- **Audit:** store the original text and the validated intent, without personal data in operational logs.
- **Cost:** this layer needs a paid model key, which the keyless demo doesn't have. Add per-shop limits on calls and spend.

**Evaluation.** A labelled set covering the LANG-05 sentences, ambiguous amounts, other-shop references and prompt injection in invoice text (AC-04, AC-13). Recorded fixtures can't prove language understanding, so this set runs against the live model.

### SETUP-06: multi-agent provisioning (not scheduled)

Don't schedule this until P2 and P3 show a real need. Today `assure-flow` is one deterministic identity (D-09), and the agent roles in `rooms.yaml` are declarations, not running workers. The plan's recommendation is a single orchestrated service with internal modules first. Add separately registered agents only where isolation requires it. Any later build needs its own design covering Switch registration and lifecycle, a separate provisioning credential, typed tools and spend limits.

## 9. P4: queues and durable clarifications (next release)

**REVIEW-01.** `pending` becomes a grouped queue: blocking, warnings, clean. Each line shows supplier, amount and reason. Reduce duplicate notices, keeping receipt and progress. Telegram message edits need bridge support, so they stay out of scope until a patch or S3 provides them.

**REVIEW-02.** New table:

```text
clarifications  id, practice_id, shop_id, invoice_id, revision_id, asked_by,
                question, respondent_role, status, answer_text, answer_event_id,
                answered_by, answered_at, resulting_revision_id
```

A reply to the question closes it and goes back to the CA. Only an explicit field correction creates a revision and invalidates decisions. Otherwise the answer is stored as evidence, and the printed invoice is unchanged. The issue then returns to `awaiting_ca`.

**REVIEW-03.** Pack approval uses the two-step flow in 5.4. A changed month invalidates the prompt, because `approve_snapshot` already rechecks versions.

## 10. Data and dependency changes

| Change | Phase | Migration |
|---|---|---|
| New transitions; override handler | P0 | None |
| One outbox row per artifact | P0 | None |
| `runtime_instances` | P0 | `u3_runtime` |
| Withheld acknowledgement marker on `outbox` | P0 | `u3_runtime` |
| Patched `switch-core:0.31.0-af1` in `deploy/switch/` | P0 (optional in the cut) | Compose image change |
| `action_tokens` | Button phase | New |
| `setup_sessions`, `invitations` | P2 | New |
| `clarifications` | P4 | New |

Each migration needs an up, down, up test on the test database, as with U2.

## 11. Verification map

| AC | Test | Type | Phase |
|---|---|---|---|
| AC-01 | Setup wizard, interrupted setup, expired invitation | Offline + live | P2 |
| AC-02 | Confirm through a reply with no reference typed | Offline + live | P1 |
| AC-03 | Each prompt names the real field | Offline | P1 |
| AC-04 | Correct target, chooser when ambiguous, no other shop | Offline | P1, P3 |
| AC-05 | Old or repeated confirmation | Offline | P1 |
| AC-06 | Revoked person's reply or press | Offline + live | P1, buttons |
| AC-07 | Approved and excluded reopen | Offline + live | P0 |
| AC-08 | R-DUP-02 override into export | Offline + live | P0 |
| AC-09 | Join and leave withholding | Offline + live on patched image | P0 |
| AC-10 | Rename, migration, username change | Offline + live | P0, P2 |
| AC-11 | Normal approval, both files visible | Live, person confirms | P0 |
| AC-12 | Network, model, worker failure | Offline + live | P0, P3 |
| AC-13 | Prompt injection | Live-model evaluation | P3 |
| AC-14 | Queues show the next responsible person | Offline + live | P4 |
| AC-15 | Unfamiliar person completes the journey | Moderated session | P1 onward |
| AC-16 | Scan of rendered messages for enum names, SQL, grant or lease text | Offline | P1 |
| AC-17 | Multi-agent provisioning | Not scheduled | n/a |

**Rerun live after P0:** T-11 (approved reopen, allowed override), T-15 cleanup, T-18 (normal export, seen by a person), T-23 (controlled restart).

**Still needs more accounts, never to be reported as passed from one account:** T-14, T-16, T-20, T-21, P-01–P-08.

Update `docs/AUDIT_CHECKLIST.md` section M and `docs/MANUAL_TEST_GUIDE.md` as each item is verified, including the guide's `Withdrawn` wording, which the report found differs from the actual notice.

## 12. Sequence and hackathon cut

Effort figures are planning assumptions for one engineer, before live rerun time.

| Priority | Item | Estimate | State |
|---|---|---|---|
| 1 | FIX-01 reopen, FIX-02 override | 4 h | Code and offline tests done; live rerun pending |
| 2 | FIX-04 one file per row, dead-row alert, `resend`; FIX-05 inbox reply | 4 h | Code and offline tests done; live rerun pending |
| 3 | FIX-06 lock, eviction guard, health checks; FIX-03 name hardening, `rebind-room` | 4 h | Code and offline tests done; controlled restart pending |
| — | **Checkpoint: targeted live regressions** (below) | 2 h | Next; needs one runtime owner and your Telegram accounts |
| 4 | Plain English for complete, frequently used message families, on the action catalog | 6 h | Not started |
| 5 | Basic reply-based confirmation and correction, **only if Telegram reply mapping is verified first** | 4 h | Not started |
| — | **Final short owner and CA journey** | 1 h | After priority 4–5 |

Not in the cut: FIX-06 registry and `scripts/runtime.py`, the Switch patch image for FIX-03 and FIX-05 (stated as known limitations), the full message inventory, spikes other than the reply-mapping check, buttons, P2, P3 and P4.

### Verification sequence

1. Establish one session as the runtime owner. Restart the adapter and worker on the new code, so both take their locks. No other session touches the stack during live tests.
2. Run the automated P0 suite.
3. Rerun live: approved reopening, permitted override, normal export delivery with a person confirming both files, and a controlled adapter restart (T-23).
4. Rerun membership removal only if its bridge fix is included. It isn't in this cut.
5. Implement the message improvements.
6. Finish with a short owner and CA usability run: correction, clarification, supplier replacement and approval. Earlier tests aren't repeated for wording changes.

**Hold back time for verification.** The deadline also has to fit the demo video and the clean-clone rehearsal. If time gets short, drop reply-based actions first, then whole lower-priority message families. Don't leave a family half-rewritten.

**Release.** Purchase assurance ships behind its flag, default off, and the README must say what's verified about it. `feature/purchase-assurance` still isn't merged into `main`; that decision remains open. The report's live evidence applies to `7cd5076`, so the fixes should be reviewable commits on top of it.

Each increment reports: user-visible behaviour, modules changed, tests run, remaining limits, and any migration or Switch dependency change.

## 13. Risks and open questions

| Risk or question | Effect | Handling |
|---|---|---|
| Telegram replies may not carry a usable `thread_id` | Reply-based actions need bridge work | Test first in P1 |
| Approval cards may not fit a sessionless agent | Option B needed | S1 |
| Carrying a Switch patch | Upgrades need rebasing | Small patch, provenance note, S3 first, offer upstream |
| Member list stays incomplete even after the patch | A silent member may be missed | Stated in setup; declared `room_members` check stays |
| FIX-04 cause remains unknown | The same fault could affect other album sends | No album sends in our path; rerun with a person watching |
| Running out of time | Half-finished language pass reads inconsistently | Finish whole message families, in priority order |
| Concurrent sessions on one live stack | Test results get invalidated again | Lock, health checks and the one-owner rule |
| Display names aren't identity | A silent reader could receive a room's messages | Fail closed on ambiguity, state the limit, close it with the patch |
| The advisory lock ends if its database connection drops | A second copy could then start | Accepted for this release; restart after any database outage |

**Still open:** whether and when `feature/purchase-assurance` merges into `main` for the submission.
