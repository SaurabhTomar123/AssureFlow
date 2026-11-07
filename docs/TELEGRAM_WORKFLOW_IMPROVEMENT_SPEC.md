# Assure Flow: Telegram journey and conversation improvements

Date: 6 November 2026
Audience: Claude or another engineer implementing the next iteration
Status: Proposed product and engineering requirements, informed by live testing

## 1. Purpose and evidence

Improve the complete journey from connecting a shop and its CA to reviewing invoices and approving a monthly pack. The experience must be understandable without a command reference, terminal access, knowledge of internal identifiers, or help from an engineer.

The user found the setup slow, the commands undiscoverable, the review process fragmented across groups, and the bot's language technical and unnatural. These are core product requirements, not optional wording polish.

Read these sources before implementing:

- [Live Telegram test results](release/telegram-manual-2026-11-06.md): evidence, failures, recovery workarounds, and limits.
- [Audit checklist, section M](AUDIT_CHECKLIST.md): current Telegram verification status.
- [Manual test guide](MANUAL_TEST_GUIDE.md): existing behavior and test scenarios; some expectations conflict with implementation.
- [Purchase assurance contract](purchase-assurance-update.md): current release boundaries and deferred onboarding/routing features.
- [Decisions](decisions.md): existing design constraints and rationale.

The live run used recorded fixture extraction (`LLM_PROVIDER=fake`). It did not establish the quality of live model extraction or conversational orchestration. Ninety-four automated tests passed during the run, but that is not evidence that all live Telegram scenarios passed. Additional accounts were unavailable, so cross-shop and full staff purchase workflows remain unverified manually.

This document is a proposed next-iteration specification. It does not claim the features below exist or the observed failures have been fixed.

## 2. Product outcome

An ordinary owner should be able to connect a shop, invite its CA, upload an invoice, correct unclear details, and follow progress through understandable messages and buttons. The CA should receive a focused review queue, make explicit decisions, and approve an exact monthly pack. Routing, identifiers, revisions, hashes, retry handling, and audit records should be managed by the application.

People should supply business facts and exercise their authority. They should not operate the application's internal protocol.

### Target journey

1. An authorized administrator starts setup and enters the shop details.
2. Setup provides owner and CA invitations, explaining each role's access.
3. Each invited person accepts using their own verified Telegram account.
4. The administrator selects the appropriate Telegram groups through guided links or a picker. The application checks permissions, connects the workflow, and saves bindings.
5. The owner uploads a bill. The system acknowledges it, reads it, and asks only for information that needs attention.
6. The owner confirms or corrects details using buttons and ordinary language.
7. Checks run automatically. The system routes exceptions and keeps the owner informed of the next responsible person.
8. The CA reviews evidence and chooses an action. The system routes clarification and supplier requests without copying commands between groups.
9. The CA sees month readiness, reviews a pack, acknowledges unresolved items when applicable, and approves the exact displayed version.
10. The system delivers the exports, reports delivery failures accurately, and offers recovery without rebuilding unrelated work.

## 3. Scope and authority boundaries

### Build now

- Guided setup, enrollment, room binding, and permission preflight.
- Human-centered message templates and role-specific terminology.
- Contextual buttons, menus, conversational correction, and clear next actions.
- A scoped conversational LLM layer over existing business services.
- Focused queues and configurable notifications.
- Fixes for observed workflow, membership, and file-delivery failures.
- Repeatable automated interaction tests and a shorter manual verification guide.

### Preserve

- Exact Decimal arithmetic and deterministic GST/purchase checks.
- Immutable original files, evidence references, revision history, and auditability.
- Server-side user, practice, shop, room, and capability authorization.
- Decisions bound to the current revision/check run; snapshot approvals bound to exact content.
- Revocation, duplicate protection, job idempotence, and recovery guarantees.
- Storekeeper separation from prices and CA-only information.

### Do not introduce implicitly

- An LLM granting itself or a person permissions.
- An LLM recording a CA approval or owner confirmation without the appropriate human action.
- Automatic CA sign-off merely because extraction confidence is high.
- Real payment execution, GST filing, or claims of ITC eligibility.
- A shared owner/CA conversation that exposes confidential CA content.
- Direct Telegram calls inside the business domain that bypass Switch.

If straight-through handling of clean invoices is added later, specify an explicit opt-in policy. Record automatic clearance distinctly from a named CA's decision. Confidence is not proof that the underlying invoice is correct.

## 4. Workstream A: fix observed behavior first

| ID | Observation | Required change | Acceptance evidence |
|---|---|---|---|
| FIX-01 | Reopening an approved invoice was refused; excluded-case reopening worked. | Support the proposed approved/excluded reopening behavior consistently across state policy, action handler, approval validity, and month versions. Reconcile the contract and guide. Preserve the old decision as history. | Reopen an approved case; checks rerun once, prior approval is no longer current, affected packs become stale as appropriate, and a new review is actionable. |
| FIX-02 | Allowed R-DUP-02 override was refused in `ready_for_ca`. | Support an explicit, permitted warning override from the relevant reviewable states. Inspect the handler as well as the transition table: it currently selects blocking issues, while the tested R-DUP-02 warning was nonblocking. Persist the named warning, reason, actor, revision, and check run. | R-DUP-02 override succeeds and appears in the export. R-DUP-01, R-TAX-01 and arithmetic rules remain non-overridable. Unknown or unrelated rule names cannot create a misleading success. |
| FIX-03 | After the owner was removed from the CA group, Switch still reported the owner as a member and withheld replies. | Correct membership-change ingestion and stale membership reconciliation at the Switch integration boundary. Cover removals, leaves, rejoins, username changes, and group migrations. | Removing the unexpected member allows a new authorized reply. Previously withheld messages remain withheld. No recovery group or manual database edit is needed. |
| FIX-04 | The grouped Excel/JSON export was reported delivered but the user saw no files. Individual sends through Switch were visible. | Trace the normal grouped path and make the default export path reliable. Prefer individually tracked files unless group delivery has been verified. Provide retry per artifact with deduplication. | A fresh normal approval delivers both usable files without engineer intervention. Each artifact has delivery metadata; partial failures are visible and recoverable. |
| FIX-05 | Telegram attachment downloads intermittently failed during DNS/network errors. | Add bounded retries/backoff at the appropriate bridge layer and a useful user-facing failure/retry path. Preserve idempotence across repeated updates and retransmissions. | A transient failure recovers; an exhausted failure clearly says the file was not received. No empty invoice or duplicate case is created. |
| FIX-06 | Runtime processes were relaunched by an unknown exited launcher, disrupting controlled restart tests. | Establish one documented runtime owner/supervisor, prevent duplicate adapter ownership, and expose launch/restart/connection history. Investigate rather than assume the original launch source. | Start/stop/status commands identify the active service and owner; controlled recovery tests cannot silently be invalidated by a competing process. |

Do not resolve FIX-02 by broadly allowing overrides or treating all failed checks as nonblocking. Do not resolve FIX-03 by disabling member checks or adding every unexpected member to a trusted list. The root cause of FIX-04 is not established; do not label the original album visibly delivered solely from an HTTP success or a platform message ID.

## 5. Workstream B: guided onboarding

### SETUP-01: one guided starting point

Provide an administrator setup flow with a resumable checklist:

- Shop details and supported invoice scope.
- Owner invitation and verified acceptance.
- CA invitation, assignment, and verified acceptance.
- Group selection and workflow attachment.
- Permission and connectivity checks.
- A sample-file round trip, clearly labeled as a test.

Show completed steps and the one next action. Explain failures in the setup interface; do not leave an apparently successful setup that silently ignores messages.

### SETUP-02: select groups instead of matching names

Use Telegram's supported add-to-group deep links or chat selection interface. Associate a short-lived, signed, single-use setup token with the intended practice, shop, role, and setup session. Validate the person completing the operation and their authority before binding.

Store stable platform/Switch room identifiers as the binding. Group titles are display labels. Do not require exact `af-*` names in customer-facing setup. Detect group migrations and provide an explicit binding-repair path.

Retain `scripts.admin` for operations and troubleshooting. Ordinary onboarding must not require `bind-user`, `bind-rooms`, participant IDs, or edits to YAML.

### SETUP-03: invitations and identities

- Bind a verified Telegram numeric user ID/provider identity to the business user through Switch's identity representation. Never use a typed username or display name as the sole proof of identity.
- Usernames and display names may change; treat them as presentation attributes.
- An authorized administrator confirms owner/CA assignments. An LLM may propose a role but cannot grant it.
- Invitations expire, are single-use, and cannot be repurposed for another shop or role.
- Explain each role's access before acceptance, including that storekeepers do not see prices.
- Check duplicate enrollment and conflicting assignments without silently merging people.

### SETUP-04: automatic agent provisioning within granted permissions

An authorized setup service should activate or attach the configured Switch workflow/agents after binding. Detect existing registrations and membership so setup is idempotent. Do not ask every customer to type `/invite_agent` after completing a setup wizard.

The current `assure-flow` integration and its logical room responsibilities are not evidence that separate LLM workers are already deployed. Choose the needed runtime architecture explicitly. Multiple internal specialists do not require multiple visible Telegram bot accounts.

The standard Telegram Bot API does not provide arbitrary group creation. Keep the user-mediated group selection/create step explicit. Do not promise that an LLM can bypass platform permissions.

### SETUP-06: LLM-driven creation of specialist agents

Proposed capability: an authorized orchestrator LLM can propose, create, configure, and coordinate multiple specialist agents through a controlled provisioning service. A user should be able to say, "Set up invoice processing and accountant review for this shop," and receive a clear explanation of the agents and responsibilities being configured.

Creating an agent means provisioning an internal agent identity/configuration and its supported runtime through Switch/deployment APIs. It does not imply creating a new Telegram bot account, Telegram user, or group. One visible Assure Flow bot may present work from several internal specialists.

| Specialist | Responsibility | Permission boundary |
|---|---|---|
| Setup coordinator | Collect setup information, propose roles, request provisioning, track onboarding | Cannot grant business roles or expand its own access |
| Invoice intake agent | Handle uploads, track processing, ask for missing information | Limited to its assigned shop and intake actions |
| Extraction agent | Read documents and return structured fields with evidence and confidence | Document-scoped input; cannot confirm fields or decide GST outcomes |
| Review assistant | Explain deterministic check results, prioritize exceptions, draft clarification and supplier requests | Assigned CA/shop context; cannot sign a CA decision |
| Reconciliation assistant | Explain GSTR-2B match results and help investigate differences | Scoped statements and invoices; matching calculations remain deterministic |
| Purchase coordination agent | Coordinate order, delivery, invoice-link, and correction tasks | Capability-scoped; cannot invent delivery confirmation or authorize payment readiness |
| Monthly pack assistant | Summarize readiness and request pack generation | Cannot approve a pack on the CA's behalf |
| Operations agent | Monitor failures, retries, service ownership, and delivery status | Operational metadata; invoice content only when explicitly authorized and necessary |

Provisioning flow:

1. Interpret the user's requested workflow within the verified administrator's scope.
2. Propose a plan containing agent types, responsibilities, shop scope, tool allowlists, runtime/model settings, and destinations. Reuse existing suitable agents where possible.
3. Validate the plan against administrator-granted provisioning authority, approved templates, deployment capabilities, and resource limits. Require explicit approval for new or broader access; routine creation within an already approved policy can proceed automatically.
4. Create the permitted agent registrations/configurations, start their supported runtimes, and attach them to authorized Switch rooms. Do not report success until each required step is verified.
5. Run permission and connectivity preflight, then show a plain-English setup summary. Record partial failures and offer resumable recovery.
6. Coordinate work using durable, scoped tasks with traceable handoffs and idempotent execution. Suspend or retire agents when their scope is revoked or their work is complete.

Implement provisioning as typed, validated tools rather than arbitrary model-generated shell commands. Use a distinct provisioning identity; ordinary invoice/review agents should not inherit the ability to create agents. Cap agent counts, concurrency, tool calls, and model spend. Agent creation must be idempotent so repeated setup requests do not multiply registrations or consumers.

Choose specialists according to actual workload and isolation needs. Do not deploy every listed agent for every small shop by default. A specialist can be an internal worker or a separately registered agent where that distinction provides useful isolation. The current YAML role declarations alone do not implement this capability; verify the pinned Switch version's registration and runtime lifecycle interfaces before building it.

Acceptance: an authorized administrator can request a workflow in ordinary language; the orchestrator provisions the necessary specialists without terminal commands, verifies their operation, and explains who handles each task. An unauthorized user cannot provision agents. Repeating the request creates no duplicates, and a proposed role/tool/scope expansion cannot bypass approval. Every specialist remains unable to impersonate a human confirmation, CA decision, or owner authorization.

### SETUP-05: preflight and minimal topology

Verify bot visibility/privacy behavior, attachment round trips, participant verification, role assignments, membership monitoring capability, worker/adapter health, and a valid CA destination before marking setup complete.

Start customer setup with an owner workspace and a private CA review workspace. Make the practice overview optional or a view in the CA experience. Delivery workspaces are introduced only when staff functionality is enabled. Operations and synthetic testing are deployment concerns, not mandatory customer onboarding steps.

Telegram membership updates and `getChatMember` have permission limitations. Verify the bot's required rights and update subscriptions. Do not equate "accounts that have posted" with a complete current member list. If a required audience check cannot be established, explain the setup limitation and fail closed for sensitive output.

Acceptance: a new shop can complete setup without a terminal, internal identifiers, exact group titles, or a command manual. Test interrupted setup, expired invitations, renamed groups, and unauthorized enrollment.

## 6. Workstream C: human-centered language and interaction

### LANG-01: voice

Use simple, standard English that sounds like a competent bookkeeping assistant: calm, direct, respectful, and specific. Prefer short active sentences and familiar words. Explain what happened, what needs attention, and the next useful action.

Natural language must not conceal that this is an automated service or invent human review. Avoid theatrical friendliness, repeated greetings, excessive emojis, canned apologies, and claims such as "I checked this personally" when code or a model performed the check.

Use first-person phrasing where it reads naturally, but name the responsible person when waiting on someone else: "Your accountant is reviewing this bill." Do not suggest that the owner should act when the next step belongs to the CA.

### LANG-02: information hierarchy

Each primary message should contain:

1. A plain-language outcome or status.
2. The relevant supplier, invoice/date, or month so the person recognizes the work.
3. One clear next step or a small set of mutually understandable choices.
4. An optional Details action for evidence, tax components, history, and technical references.

Keep identifiers available for support and cross-reference, but secondary. Do not require the user to copy an identifier to act on the message. Put rule codes, state names, correlation IDs, hashes, and execution diagnostics in technical details or operations views.

Do not hide material tax facts to make messages shorter. The CA needs the actual discrepancy and supporting evidence; the owner needs understandable action and enough invoice detail to verify it.

### LANG-03: terminology map

| Internal term | Owner-facing wording | CA-facing wording |
|---|---|---|
| `needs_confirmation` | Please check the bill details | Waiting for the owner's confirmation |
| `needs_resolution` | This bill needs attention | Review needed, followed by the specific issue |
| `ready_for_ca` | Waiting for your accountant's review | Ready for your review |
| `approved` | Included in this month's review pack | Included in the monthly pack |
| `excluded` | Left out of this month's pack, with the reason | Excluded, with the recorded reason |
| `needs_evidence` | We need more information | Evidence needed, with the exact missing fact |
| `stale revision` | This bill has been updated | A newer version needs your review |
| `snapshot` | Monthly review pack | Monthly review pack |
| `partial` | Some bills still need attention | Incomplete pack, with held/unassigned counts |
| `outbox withheld` | Use a private authorized destination for recovery instructions | Delivery paused because the group includes someone without access |

Use "accountant" or "CA" consistently with the person's configured role and local product terminology. Never translate `approved` into "paid", "GST filed", or "ITC eligible".

### LANG-04: before/after copy examples

These examples describe required behavior and tone. Populate messages from actual case data; example amounts are not hard-coded production defaults.

| Situation | Current or observed wording | Proposed message/action |
|---|---|---|
| Upload acknowledgment | "Received R-0004 ... Saving the original now." | "I've received your bill. I'll read the details now." Show supplier/reference once known. |
| Confirmation request | "INV-0003 r1 ... Reply ok INV-0003 r1" | "Please check this bill from Modern Agro Staples: total ₹7,770." Actions: Confirm details; Correct a detail; View full bill details. |
| Unclear total | "Total ... uncertain ... Question: is the total correct?" | "I couldn't read the total clearly. Is it ₹1,780, or a different amount?" Allow a typed amount. Do not invent alternatives from confidence alone. |
| Missing GSTIN | "Supplier GSTIN: not readable ... is the supplier gstin correct?" | "The supplier's GSTIN is missing from this bill. Please enter it, upload a clearer bill, or leave this on hold." |
| Irrelevant correction hint | Missing GSTIN followed by `pos=07` | Ask specifically for the GSTIN. The helper must match the missing field. |
| Typed correction | "corrected (r2)" | "Updated the total to ₹1,180. Please check the revised details." Actions: Confirm updated details; Make another correction. |
| Exact duplicate | "R-0009 is the same file as INV-0006" | "You've already sent this bill. I haven't added it again." Action: Open existing bill. |
| Two invoices | "split ... page 1 ... page 2" | "This PDF contains two bills. I've separated them so you can check each one." Show two identifiable cards. |
| Tax-type issue | "R-TAX-01 ... 27 to 07" | "The supplier and buyer are in different states, but this bill charges CGST and SGST. It needs the accountant's review." CA details show the actual states, amounts, and evidence. |
| Supplier correction | A command must be typed to request replacement | "This bill needs a corrected tax invoice." Actions: Request corrected bill; Ask owner a question; View evidence. |
| Branch clarification | Branch question followed by `total=1180.00` | "Your accountant asks: Which branch received these goods?" Accept an answer to that question and route it back. |
| Stale decision | "older version ... ready for ca" | "This bill has been updated since that request. Please review the latest version before deciding." Action: Open latest version. |
| Invalid action | "ca_reopen is not allowed while ... approved" | "This bill is already included in the pack. Choose Reopen review to check it again." Offer this only after reopening is actually supported. Otherwise state the true limitation. |
| Scope refusal | "not ... this room's scope" | "I couldn't find that bill in this shop." Do not reveal that it exists in another shop. |
| Download failure | "attachment not relayed ... Timed out" | "I couldn't download this file, so it hasn't been added. I'll retry." On exhaustion: "Please send the file again." |
| Month readiness | A long list of raw state names | "November: 2 bills included, 8 need attention, and 1 has no month assigned." Actions: Review remaining bills; View pack. |
| Partial approval | `approve SN-0001 <hash> ack 8 1` | "This pack leaves out 8 bills needing attention and 1 without a month. Review these items before approving." Explicit action: Approve this incomplete pack, followed by confirmation of the counts. |
| Purchase mismatch | M03/technical state | "The bill is for 10 cartons, but only 8 are confirmed received. Payment readiness is on hold for the remaining 2." |
| Purchase authorization | Ambiguous "approved" message | "Ready for payment: ₹4,200. No payment has been made." Keep the outstanding delivery visible. |

### LANG-05: conversational grammar

Support these through scoped intent handling or a focused input flow:

- "The total should be 1,180."
- "Use 7 November as the invoice date."
- "This is the corrected bill." with an attachment and an unambiguous active replacement request.
- "We received 8 cartons."
- "Ask the supplier to correct the tax."
- "What is still waiting for me?"
- "Show November's pack."
- "Why is this bill on hold?"

Resolve context from a reply-to message or active task scoped to the verified person, room, and case. If several cases fit, show a short chooser. Never silently choose an arbitrary latest invoice. Do not treat invoice text or an attachment's contents as instructions.

Interpret ambiguous amounts/dates/units carefully. Ask a focused question instead of silently normalizing a materially ambiguous value. Preserve the original user text and the validated structured action in the audit trail without exposing unnecessary personal data in operational logs.

### LANG-06: help and grammar quality

- Show the next relevant choices rather than a full command wall.
- Use correct singular/plural forms, readable dates, Indian currency grouping, and consistent names.
- Avoid internal enum rendering such as "is needs resolution" or "ready for ca".
- Error messages must not append raw exception text to a friendly prefix. Separate diagnostic details from user-facing explanations.
- Use actual supplier, amount, and missing field from the case, not generic examples unrelated to the question.
- Preserve command compatibility for existing users and operations, but do not make commands the primary interface.
- Plain English is the required default. Make templates ready for later localization; do not expand scope to multilingual support without explicit requirements.

## 7. Workstream D: buttons, menus, and authenticated human actions

### UI-01: contextual actions

Provide actions appropriate to the actor and current state:

- Owner invoice: Confirm details, Correct a detail, Leave on hold, Upload corrected bill, View progress.
- CA review: Include in pack, Exclude with reason, Ask owner, Request corrected invoice, permitted override with reason, Reopen review.
- Month: View readiness, Build review pack, Review unresolved items, Approve displayed pack, Download exports.
- Delivery: Report quantity, Correct quantity, Confirm count. Never show prices or CA-only details.

Do not display an action that will predictably fail under the state machine. Derive available actions from the same server-side policy that validates execution.

### UI-02: callback integrity

Add or extend a transport-neutral interaction path through Switch; first verify the pinned Switch version's supported callback/interaction interfaces. Do not assume existing business code handles Telegram callbacks.

Use opaque action references or signed, bounded payloads. Bind an action to its intended practice/shop/case, current revision or snapshot hash, allowed actor/capability, destination, expiration, and unique action ID. Do not put secrets or the full business record in button payloads.

On every click, recheck identity, role, room audience, current object version, and action availability. Handle double clicks, replay, revocation, and expired buttons idempotently. Show a clear result and replace obsolete action buttons when practical.

A verified human click may invoke the same domain action as a verified human room command. It must not be treated as an agent-token permission to decide. Existing MCP/agent decision restrictions remain intact.

### UI-03: command discovery

Register the commands actually supported by the integration, with role/chat-scoped descriptions. Coordinate ownership with Switch because one Telegram bot may serve multiple logical agents. Verify routing for slash commands; simply registering `/status` will not help if the parser expects only `status`.

The command menu is a discoverability aid, never an authorization boundary. Dynamic invoice-specific actions belong on buttons, not in a static list of commands. Maintain an action/command catalog so parsing, help, menus, and documentation do not drift apart.

## 8. Workstream E: scoped conversational LLM assistance

### Architecture

Verified Switch event -> identity/room context -> deterministic command or button handling -> optional conversational interpretation -> validated typed intent -> existing scoped domain service -> audit/outbox -> role-appropriate response.

Keep arithmetic, rule outcomes, state transitions, authorization, and canonical amounts deterministic. Use an LLM for interpretation, explanation, document extraction, draft generation, and choosing relevant permitted tools. Validate structured output before execution.

Use deterministic templates for transactional confirmations and refusals. Optional LLM explanations must be grounded in tool results and must not change the canonical outcome, amount, missing evidence, or responsible person. A model outage should leave menus, buttons, commands, and queued processing usable.

### LLM-01: intent handling

Define a small typed intent schema with explicit action, target/context reference, supported field values, and clarification requirements. Derive identity, shop, and role from trusted context, not model-supplied fields. Allowlist tools and validate every field using the existing domain types.

The model may propose an action that needs a human decision; render the relevant confirmation card instead of recording authorization on the model's behalf. A CA's explicit action must still reference the exact reviewable object.

### LLM-02: orchestration and limits

- A configured orchestrator may activate specialists through granted Switch/deployment tools; it cannot create credentials or widen permissions by itself.
- Specialists receive only the context and evidence needed for their role.
- Cross-room routing is selected by validated business bindings, not arbitrary destinations returned by the model.
- State what is waiting on the owner, CA, supplier, or storekeeper. Do not repeatedly ask the wrong person.
- Use bounded tool calls, timeouts, retries, and durable tasks rather than an unconstrained model loop.
- Add live-model evaluation after deterministic interaction work. Recorded fixtures cannot establish natural-language understanding or extraction accuracy.

## 9. Workstream F: review queues and reliable coordination

### REVIEW-01: actionable queues

Give each user a queue of work requiring their action. Group CA work by issue/urgency and shop; include supplier, amount, reason, evidence, and permitted next steps. Separate clean bills awaiting review from blocking exceptions and informational warnings.

Reduce unnecessary acknowledgments and duplicate notifications. Preserve timely upload receipt and clear processing progress, but avoid exposing every internal job/revision event as a separate chat message. Use an updatable case card when supported, retaining immutable history in the backend.

### REVIEW-02: clarification as a durable business object

Record who asked, what fact is requested, which case/version it concerns, intended respondent, status, and the answer. Route a natural-language answer back to the CA. A non-numeric question such as branch identity must not be forced into a numeric invoice correction command.

If an answer changes a material invoice field, create the appropriate revision and invalidate dependent decisions. If it is supplementary evidence, preserve it as evidence without pretending the printed invoice was edited.

### REVIEW-03: month-end

Show included, excluded, held, and unassigned items with understandable explanations. Bind the approval interaction to the frozen manifest/hash internally. Make incomplete-pack acknowledgment explicit and specific; never hide unresolved items behind a generic Approve button.

Invalidate stale approval controls if relevant data changes. Provide per-file downloads/retries for the exact approved artifacts. Do not rebuild a different pack silently while presenting it as the one previously approved.

## 10. Workstream G: observability and recovery

Expose distinct states for file receipt, durable storage, processing, export generation, submission to Switch, and platform acceptance/failure. Platform acceptance does not prove that the recipient saw or opened a file. Record user acknowledgment separately when the product needs it.

Retries must preserve the case/receipt/action relationship and must not duplicate invoices, decisions, or visible messages unnecessarily. Keep partial export delivery explicit so a successful JSON send does not hide an Excel failure.

Provide an operations view of connectivity, polling conflicts, adapter ownership, DNS/download errors, queue health, withheld messages, and failed artifacts. Show customer-facing recovery instructions only to an appropriate authorized destination. Do not send sensitive diagnostics into a room whose audience check failed.

Historical intentionally withheld messages must be distinguishable from a current outage. Do not delete audit evidence merely to make health checks green.

## 11. Implementation map

Recheck current code before editing; this is a starting map, not an exhaustive list.

| Area | Existing entry points |
|---|---|
| Message language, labels, help, error rendering | `domain/services/messages.py`; also direct messages in `domain/ca_actions.py`, `domain/periods.py`, `domain/services/checks.py`, `domain/services/reconciliation.py`, `domain/services/snapshots.py`, `domain/services/purchases.py`, `domain/services/readiness.py`, and `domain/services/business_tasks.py` |
| Parsing, routing, verified human command execution | `domain/services/inbox.py`, `domain/context.py`, `domain/scope.py` |
| Workflow policies and CA decisions | `domain/states.py`, `domain/workflow.py`, `domain/ca_actions.py`, `rules/registry.py` |
| Setup, identities, room bindings | `scripts/admin.py`, `agents/rooms.yaml`, `seed/practice.yaml`, `domain/models.py` |
| Switch events, interactions and media | `adapters/switch_client.py`, `adapters/inbox_writer.py`, `adapters/run.py`, `workers/outbox.py`; upstream Switch Telegram bridge where required |
| Queues, retries, supervision | `workers/runner.py`, `workers/queue.py`, `docker-compose.yml`, `scripts/health.py` |
| Extraction and conversational model separation | `adapters/llm.py`, `domain/extraction.py`, new scoped intent/orchestration modules as needed |
| Agent-facing authority boundary | `api/mcp/server.py`, `api/routers/tools.py`, `api/deps.py` |
| Regression coverage | `tests/offline/`, `tests/live/`, `docs/MANUAL_TEST_GUIDE.md` |

Do not patch a temporary external Switch checkout as the only implementation of a fix. If the pinned bridge needs changes, maintain a reproducible dependency patch/version/build procedure and document its provenance.

## 12. Verification and acceptance criteria

| ID | Scenario | Required outcome |
|---|---|---|
| AC-01 | New administrator sets up a shop | Completes enrollment and group selection without terminal commands, internal IDs, or exact group names. |
| AC-02 | Owner sees a new bill summary | Can identify the bill and confirm/correct/hold without learning command syntax. |
| AC-03 | Missing GSTIN, unclear total, branch question | Each prompt asks the right question and accepts the appropriate answer; no irrelevant generic examples. |
| AC-04 | Owner says "the total is 1,180" while replying to a bill | Correct target and revision; ambiguous context triggers a chooser; no cross-shop interpretation. |
| AC-05 | User clicks an old/double-clicked confirmation | No stale mutation or duplicate action; understandable explanation and latest-version action. |
| AC-06 | Unauthorized or revoked person clicks a valid-looking button | Server refuses without disclosing another shop's data. |
| AC-07 | Approved/excluded case reopened | Intended contract enforced, checks rerun once, prior decisions remain historical, dependent packs handled correctly. |
| AC-08 | Permitted duplicate-warning override | Persists the correct issue-specific audit record and reason, and exports it. Non-overridable checks remain blocked. |
| AC-09 | Unexpected member joins, then leaves | Sensitive replies withheld while unauthorized member is present; fresh authorized replies resume after verified removal; old withheld replies stay withheld. |
| AC-10 | Group renamed/migrated, username changed | Identity and scope remain correct or explicit revalidation is requested; no stale bindings silently redirect content. |
| AC-11 | Normal pack approval | Wrong/stale content refused; exact approval works; unresolved items explicitly acknowledged; both files delivered through the normal path. |
| AC-12 | Network/model/worker failure | Accurate status, bounded recovery, durable resumption, no invented success, no duplicate business action. |
| AC-13 | Natural-language or document prompt injection | Cannot select unauthorized tools, grant access, alter rule results, or impersonate a human decision. |
| AC-14 | Owner and CA queues | Each person sees their own actionable tasks and understands who acts next, without copying commands between groups. |
| AC-15 | Language comprehension review | A person unfamiliar with the command guide can complete setup, correction, clarification, supplier replacement, and pack approval, explaining the next action in their own words. |
| AC-16 | Operational versus customer language | No raw state-transition exceptions, enum names, SQL errors, or grant/lease diagnostics in ordinary customer messages. Necessary business tax terms remain available and explained. |
| AC-17 | LLM-driven multi-agent setup | Authorized workflow request provisions only permitted specialists, verifies registrations/runtimes/bindings, reuses existing agents, enforces resource limits, and refuses unauthorized access expansion. Partial failure is recoverable without duplicates. |

Test real state transitions and security boundaries rather than only snapshotting exact prose. Use focused copy/render checks for key messages plus behavior tests for context, actor, version, replay, retries, and audit persistence. Do not weaken assertions just to accept a changed result.

Retain old command compatibility tests. Add callback and plain-language equivalents using the same domain semantics. Run live extraction/conversation evaluations with synthetic documents before claiming model quality. Mark tests requiring independent roles as not run when accounts are unavailable; do not reuse one live account across incompatible roles to manufacture a pass.

## 13. Delivery sequence

| Milestone | Deliverable | Exit criterion |
|---|---|---|
| P0 | FIX-01 through FIX-06 investigation/fixes, supported-action policy, truthful delivery status | Focused regressions pass; original failing live cases rerun; unresolved upstream limitations explicitly retained. |
| P1 | Plain-English templates, relevant prompts, contextual actions, role-specific help/menu | Owner and CA can complete core invoice/review actions without a command reference. |
| P2 | Guided onboarding, verified invitations, stable binding, permission preflight | New shop setup has no terminal/YAML steps and handles interrupted enrollment safely. |
| P3 | Scoped conversational intents and optional LLM explanations | Natural-language workflows pass ambiguity, adversarial, scope, and failure evaluations; deterministic fallback remains usable. |
| P4 | Focused queues, durable clarifications, month-end interaction and reliability polish | End-to-end usability and real Telegram delivery verified across independent roles. |

Track measured onboarding duration, role-assignment steps, commands manually typed, actions requiring group switching, clarification completion, duplicate submissions, and file-retry success. Establish a baseline first; do not claim a percentage reduction without measurements.

## 14. Claude handoff instructions

Use this document as the implementation brief. First inspect the repository's instructions, current code, and linked test evidence. Identify changes since the tested commit before relying on old line numbers or state assumptions.

Start with P0 and the action-policy consistency needed for P1. Implement in reviewable increments with clear acceptance evidence. Preserve command compatibility and existing authorization boundaries. For each increment, report the user-visible behavior, affected modules, tests run, remaining limitations, and any migration or upstream dependency change.

Do not silently implement every milestone as one broad rewrite. Do not reset the working demo database, delete recorded evidence, replace real identities, commit credentials, publish changes, or alter production roles as part of routine verification. Use the dedicated test database and synthetic fixtures. Preserve unrelated user edits, including the currently deleted F09 fixture unless explicitly addressed.

For language work, inventory messages across the whole domain; editing only `messages.py` is insufficient. Introduce structured message/action models where they help keep rendering, available actions, and business outcomes consistent. Keep internal audit detail while presenting human-readable outcomes.

For every human decision, prove the authenticated actor and exact current object before recording it. An LLM's proposed intent is not proof of authorization. A button callback is not valid merely because its payload contains an allowed action name.

Suggested initial request to Claude:

> Read `docs/TELEGRAM_WORKFLOW_IMPROVEMENT_SPEC.md` and the linked Telegram test report. Inspect the current implementation, identify the root causes of the P0 failures, and implement focused fixes with regression coverage. Then implement the P1 plain-English conversation and contextual-action experience while preserving existing commands and human decision authority. Keep onboarding and LLM work scoped to their later milestones unless required dependencies are identified. Report verified behavior and outstanding gaps without marking unrun live tests passed.

## 15. Platform references

Check compatibility with the pinned Switch version before using newer platform capabilities:

- [Telegram bot features: deep links, group selection, keyboards and menus](https://core.telegram.org/bots/features).
- [Telegram command scopes](https://core.telegram.org/bots/api#botcommandscope).
- [Telegram users and numeric IDs](https://core.telegram.org/bots/api#user).
- [Telegram update subscriptions and membership events](https://core.telegram.org/bots/api#update).
- [Telegram membership lookup and administrator limitation](https://core.telegram.org/bots/api#getchatmember).

Telegram capabilities do not imply the current Switch adapter exposes them. Specify required bridge/API changes and test the actual configured transport.
