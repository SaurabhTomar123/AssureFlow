# Telegram workflow guide: setup, live API extraction, and daily use

Prepared from the owner/CA Telegram test journey on 6 November 2026.

This is an operating guide for the implemented command-based workflow. The [improvement specification](TELEGRAM_WORKFLOW_IMPROVEMENT_SPEC.md) and [technical plan](TELEGRAM_WORKFLOW_TECHNICAL_PLAN.md) describe additional changes, including simpler conversations, buttons, onboarding, and LLM orchestration. Those proposals must not be assumed to exist.

## 1. Start here: what is connected?

Three different connections have different jobs:

| Connection | Its job | What it does not do |
|---|---|---|
| Telegram bot -> Switch | Receives group messages/files and sends replies/files through the bridge | Does not read invoice fields by itself |
| Assure Flow adapter/worker -> Switch and database | Saves events, processes jobs, runs the workflow, records decisions and sends results | Does not turn on live model extraction merely because Telegram works |
| Worker -> extraction model API | Reads an uploaded bill and returns structured fields with evidence | Does not replace the owner or CA, grant permissions, create agents, or implement general conversation |

**Configuration observed when writing this guide:** effective provider `fake`, model setting `claude-opus-5-5`, no configured `LLM_API_KEY`. The Gemini SDK was installed, and Gemini provider code was present. This establishes implementation availability, not a working live API connection. Recheck the settings below after configuring the deployment.

The earlier Telegram tests used recorded extractions. They prove workflow behavior, not live extraction accuracy. Do not describe the model API as verified until a real call succeeds and a fresh Telegram upload is processed by the restarted worker.

## 2. Responsibilities

| Person/system | Responsibility |
|---|---|
| Operator | Connect the bot, register the integration once, bind groups and verified people, configure the API, and keep one session in control of the runtime |
| Owner | Upload bills, check extracted details, provide corrections or missing evidence, and send supplier replacements |
| CA | Review issues, record inclusion/exclusion/override decisions, inspect reconciliation and approve the exact monthly pack |
| Application | Store originals, invoke extraction, run deterministic checks, create and route review requests, track revisions, build approved exports and handle supported retries |

The application creates the review requests. The CA makes the decisions. An API key enables document reading; it does not make decisions on people's behalf.

## 3. Existing test setup: reuse it rather than starting again

| Item | Setup used during testing |
|---|---|
| Bot | `<telegram-bot>` |
| Owner account | `@<owner-telegram-name>`, mapped to `owner.sharma`; used in Edge |
| CA account | User identified it as `<ca-telegram-handle>`; Switch retained the participant label `<ca-telegram-name>`, mapped to `ca.mehta`; used in Chrome |
| Owner group | `af-shop-sharma` |
| Active CA group | `af-ca-review-recovery` |
| Practice overview group | `af-practice-home` |
| Previous CA group | `af-ca-review`, preserved as membership-failure evidence |

These are demo-specific identities. Do not copy their mappings into another practice. For a new deployment, enroll and verify its actual people.

The recovery CA group was necessary because the pinned Switch Telegram bridge did not remove a departed owner from its recorded membership. Continue CA actions in the recovery group until that limitation is fixed and verified.

## 4. One-time setup for a new shop or environment

Skip completed steps in the existing demo. Do not reset or reseed the database to configure a model API.

Operator prerequisite: the Assure Flow integration must already be registered in Switch. Reuse `data/switch_credentials.json` in the existing demo. On a new deployment without that registration, configure its registration key privately and run `python -m scripts.admin register-agent` once before inviting `@assure-flow`. Do not register a duplicate integration to solve a model-key problem.

1. Create/configure the Telegram bot and its token through the supported Telegram setup flow. Store the token only in the connection configuration, never in a document, source file, screenshot, or chat.
2. Configure Group Privacy appropriately before the bot joins the workflow groups. Verify an ordinary file upload arrives without an @mention.
3. In Switch Gateway, connect Telegram using the bot's credentials. Use the deployment's Gateway administrator account, which is separate from a personal Telegram or email account.
4. Have the owner create/select their shop group and the CA create/select a separate private review group. Add the bot to both. Keep the owner out of the CA group.
5. In each group, invite the integration:

   ```text
   /invite_agent @assure-flow
   ```

6. Confirm the integration appears with `!list-agents` where supported.
7. Bind the new groups using the operator tools. For a clean name-based setup, `python -m scripts.admin bind-rooms --prefix "Telegram: "` matches the configured room names. For an existing recovery binding, use the explicit recovery procedure below instead.
8. Have each person send `status` in their own group. The operator inspects `python -m scripts.admin unmapped`, verifies the participant, and binds the actual person and role. The supplied chat name must match Switch's current member representation for this version's audience check. A typed username alone is not proof of identity.
9. Start/verify the adapter and worker. Send owner `status` and `help`, and CA `pending`. Verify the responses appear in the intended groups.

Current setup still needs these operator actions. Guided onboarding and automatic agent provisioning are planned improvements, not an effect of adding an extraction API key.

The operator's identity-binding command template is `python -m scripts.admin bind-user <observed-participant-id> <existing-business-user-handle> <verified-Switch-member-name>`. Replace the placeholders with verified values; the business user and its role/assignment must already exist. Do not infer permissions from the person claiming a username in chat.

### Preserve an explicit recovery binding

The tested CA recovery Switch room ID was `<id>`. Verify it still refers to the intended group and membership before using it. On the code containing the recovery command, the operator can register an audited explicit binding:

```powershell
.\.venv\Scripts\python.exe -m scripts.admin rebind-room af-ca-review <id> "Use the verified Telegram CA recovery group"
```

`af-ca-review` in that command is the logical application room; it may point to the differently named Telegram recovery group. The new `bind-rooms` protection relies on the audited `rebind-room` operation. A historical manual database edit alone does not create that audit marker. Do not run generic rebinding with `--force` unless deliberately replacing the recovery binding.

## 5. Enable live extraction: operator steps

Run commands from the repository root using its virtual environment. First agree which session owns the runtime. Other assistants or terminals must not restart deliberately stopped processes during verification.

### Step A: use the code and dependencies that support the selected provider

Review the current branch and uncommitted changes:

```powershell
git status --short
git log -5 --oneline
```

Use the project's current dependency installation procedure. The new Gemini provider needs `google-genai`; dependency manifests may be under active development. Do not assume an older Docker image contains a new provider merely because the local source does.

### Step B: select a provider and configure its key privately

In the local ignored `.env`, configure all three settings together:

| Setting | Gemini | Anthropic |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `anthropic` |
| `LLM_MODEL` | An available Gemini model ID supported by the provider integration | An available Anthropic model ID supported by the provider integration |
| `LLM_API_KEY` | The key for the selected Gemini account/project | The key for the selected Anthropic account |

Do not leave the old Claude model setting when choosing Gemini. Do not use `fake` if the goal is live extraction. Confirm provider terms and deployment data policy before sending customer documents; the current demo/evaluation uses synthetic documents only, including the free-key Gemini path documented in D-30.

For Gemini, after setting `LLM_PROVIDER=gemini` and the key, list the models available to that account:

```powershell
.\.venv\Scripts\python.exe -m scripts.eval_extraction --list-models
```

Choose a compatible returned model. If the output is `models/gemini-...`, configure the bare `gemini-...` ID: the current Gemini provider validates that the model name starts with `gemini`. A model-list call is not an extraction test, and it does not establish quota or accuracy for document generation.

Shell environment variables can override `.env`. Check effective settings without displaying the key:

```powershell
.\.venv\Scripts\python.exe -c "from common.settings import get_settings; s=get_settings(); print('Provider:',s.LLM_PROVIDER); print('Model:',s.LLM_MODEL); print('Key configured:',bool(s.LLM_API_KEY))"
```

### Step C: verify a real API call before relying on Telegram

This command makes a real external model request and may consume quota or incur charges. It uses synthetic fixtures and does not touch the database:

```powershell
.\.venv\Scripts\python.exe -m scripts.eval_extraction --limit 1 --out data/extraction-api-smoke.json
```

Then evaluate more fixtures if the smoke test succeeds:

```powershell
.\.venv\Scripts\python.exe -m scripts.eval_extraction --limit 5 --delay 5 --out data/extraction-api-evaluation.json
```

Inspect failed documents and field mismatches, not just the exit code. A model response can succeed while the accuracy check fails. The evaluator compares supported header fields to recorded references; it does not establish line-item accuracy, confidence calibration, multi-page splitting accuracy, or real-world GST correctness. Verify the fixture inventory too: this evaluator skips missing fixture files, so a missing F09 must not be mistaken for coverage of that case.

Do not claim live API extraction is working based only on an installed SDK, a configured key, a model list, or `scripts.health`. The health script prints the configured provider; it does not make a live extraction call.

### Step D: restart the worker on the intended configuration

The worker caches settings and its extraction provider. Editing `.env` does not change an already running worker.

1. Have the single runtime owner stop the old worker through the terminal/supervisor that started it. Use the same procedure for the adapter if deploying new adapter code or changing its settings.
2. Start exactly one worker on the selected code/configuration:

   ```powershell
   .\.venv\Scripts\python.exe -m workers.runner
   ```

3. If the adapter was stopped or updated, start it in a separate terminal:

   ```powershell
   .\.venv\Scripts\python.exe -m adapters.run
   ```

4. Check health:

   ```powershell
   .\.venv\Scripts\python.exe -m scripts.health
   ```

On the code containing runtime locks, an attempted second process should exit and name the lock holder. Old running code may not hold the new lock; stop those old processes before starting new ones. A lock holder does not itself prove the adapter is connected or the model API is available. After a database outage, verify runtime ownership and restart in a controlled way; the documented lock-loss limitation remains relevant.

For Docker deployments, rebuild/recreate the affected app services using that deployment's Compose configuration and confirm they receive the intended settings. Do not start host workers alongside container workers using the same database. Keep the Switch container's networking and the app's Switch address appropriate to that deployment.

### Step E: prove Telegram is using the live provider

1. Choose a synthetic bill not already stored for this shop. Uploading an identical old file tests duplicate detection, not a fresh extraction call.
2. Upload it as a document in the owner group with no caption or @mention.
3. Verify the receipt, extracted summary, and matching original-file hash.
4. Operator: check the new extraction `usage_records` row for the expected provider/model and time. Distinguish it from `fake` / `fixture-replay`. Those usage records are shop/time-scoped rather than a direct invoice-ID trace, so use a single controlled upload and correlate the receipt/job timing; do not attribute an unrelated row to this bill.
5. Owner: compare the extracted fields with the original bill before confirming.

Do not reset an existing demo to create a fresh upload. Use an authorized fresh synthetic case or a separate test environment.

Once this succeeds, future eligible uploads invoke live extraction automatically. You do not need a separate "run AI" command for each bill.

## 6. Daily workflow: owner and CA

Use the reference numbers and revisions shown by the bot. The examples below use placeholders because earlier test IDs already exist. Replace `<case>`, `<revision>`, `<request>`, `<snapshot>`, and `<hash>` with the actual values; do not paste the angle-bracket placeholders literally.

### A. Owner uploads and checks a bill

**Owner, in the shop group:** attach the PDF or clear image as a file. No command or @mention is needed for ordinary intake.

**Automatic:** Telegram/Switch relays the file; the adapter saves the event; the worker preserves the original and asks the configured provider to read it; a summary appears.

**Owner:** check supplier, GSTINs, invoice number/date, tax components, and total against the original. Confirm the displayed revision:

```text
ok <case> r<revision>
```

**Automatic:** deterministic checks run. The API extracts what is printed; it does not replace those calculations or human confirmation. A clean bill proceeds to CA review; it is not automatically described as paid or GST-filed.

### B. Correct an unclear field

For a wrong total:

```text
<case> total=1180.00
```

**Automatic:** the application creates a new human-corrected revision and sends its summary, without rerunning extraction merely to change that value.

Confirm the new displayed revision. If material information is unavailable, use the supported hold form instead:

```text
ok <case> hold
```

Then ask:

```text
why-held <case>
```

**Automatic:** missing evidence remains missing and relevant checks stay held. Do not invent a GSTIN or accept the model's guess to remove a hold.

### C. CA reviews the automatically created request

**CA, in the active CA group:** use `pending` to list requests. Review the supplied evidence, then choose the appropriate supported action:

| Intention | Command |
|---|---|
| Include an eligible reviewed bill in the monthly pack | `<request> include` |
| Exclude it with a reason | `<request> exclude duplicate invoice` |
| Ask the owner a question | `<request> clarify which branch received the goods?` |
| Request a supplier replacement | `<request> supplier please reissue with IGST` |
| Override a permitted possible-duplicate warning with a recorded reason | `<request> override R-DUP-02 confirmed separate deliveries` |
| Reopen an approved/excluded case for another review on updated code | `reopen <case> recheck after supplier call` |

**Automatic:** the system checks CA authority and the current request/revision, records valid decisions, routes owner/supplier requests, and updates month readiness. Exact duplicates, tax-type errors, and arithmetic errors cannot be waived using an override command.

Reopen and warning-override fixes were implemented and offline-tested after the original failed live run. Reverify them on the deployed code; do not treat the original failed commands as successful live evidence for the new implementation.

The current clarification flow can deliver a free-text question, but a complete conversational answer-tracking feature is still planned. Do not assume arbitrary natural-language answers update the case unless the implemented flow acknowledges them.

### D. Owner sends a supplier replacement

**Owner, in the shop group:** upload the corrected file with this caption:

```text
corrected bill for <case>
```

**Automatic:** the same case receives a new document version/revision; outdated confirmations/decisions are invalidated and appropriate notices are routed. The owner then confirms the new summary. Checks rerun and a current CA request is generated.

An old request is not reusable: a decision on it must be refused. Use the newer request.

### E. CA uploads GSTR-2B

**CA, in the CA group:** attach the supported Excel or JSON statement with this caption:

```text
gstr2b sharma 2026-11
```

Use the actual shop code and period for other shops/months.

**Automatic:** the application stores the statement and reconciles it against the purchases using deterministic matching. It reports exact matches, mismatches, purchase-only, statement-only, and ambiguous items. An identical re-upload is idempotent. This is an uploaded-statement workflow, not an automatic GST-portal download.

Review the differences. Matching supports review; it does not establish ITC eligibility. `recon sharma 2026-11` shows the latest stored report; do not assume it requests a new model call or reruns matching.

### F. CA builds and approves a monthly pack

Send separately:

```text
readiness sharma 2026-11
```

```text
snapshot sharma 2026-11
```

**Automatic:** the system freezes the reviewed manifest, shows counts/totals and a content hash, and provides the exact approval command.

**CA:** review the actual pack and unresolved items. Use the command shown by the bot:

```text
approve <snapshot> <hash>
```

For an incomplete pack, explicitly acknowledge its exact held and unassigned counts:

```text
approve <snapshot> <hash> ack <held-count> <unassigned-count>
```

**Automatic:** the system revalidates versions/hash and authority, then generates the Excel and JSON artifacts. On the newer export code, each file has its own message. Approval does not file GST returns or execute payment.

Confirm both files are actually visible and usable. If necessary, the CA can request the same stored files on code supporting resend:

```text
resend <snapshot>
```

```text
resend <snapshot> excel
```

```text
resend <snapshot> json
```

Resend checks stored artifact hashes and does not rebuild a different pack. Local missing-file error handling and runtime lock-loss behavior were flagged during review; consult the technical plan for their current disposition before claiming every failure path is handled.

## 7. Quick reference

| Where | Useful commands |
|---|---|
| Owner shop | `help`, `status`, `pending`, `why-held <case>` |
| Active CA group | `help`, `pending`, current review decisions, `readiness`, `snapshot`, `approve`, supported `resend` |
| Practice home | `directory`, `readiness sharma 2026-11` |
| Operator terminal | `python -m scripts.health`, `python -m scripts.admin unmapped`, verified binding/recovery commands |

Commands remain the current interface. Buttons, broad natural-language interpretation, and dynamic specialist-agent creation need the planned implementation. Connecting Gemini or Anthropic for extraction does not enable them by itself.

## 8. Short live verification after enabling the API or deploying fixes

Use synthetic documents and two independent owner/CA accounts. Record the code revision, provider/model, configuration check, request/case IDs, timings, and message/file evidence. Never record the key.

1. Verify one owner and one CA command in their separate groups.
2. Make one real extraction request outside Telegram and inspect its output.
3. Upload an unused synthetic bill through Telegram and establish that the worker used the live provider.
4. Correct one field and confirm the new revision.
5. Route a tax issue to the CA, request a supplier correction, replace the original, and confirm it stays in the same case.
6. Verify stale decisions and prohibited overrides are refused; verify the newly fixed reopen and permitted override behavior separately.
7. Import a statement and verify duplicate-upload behavior.
8. Approve a reviewed pack and visually verify both normal export messages; test `resend` without rebuilding artifacts.
9. With one session controlling the stack, perform the controlled adapter restart test. Do not count a test as valid if another session restarts competing processes.

The full [manual test guide](MANUAL_TEST_GUIDE.md) contains recovery and isolation tests. The [original results](release/telegram-manual-2026-11-06.md) document what actually passed and failed at the time. Do not carry those results forward as verification of newer code without rerunning the relevant scenarios.

## 9. Troubleshooting

| Symptom | Check / next step |
|---|---|
| Only known fixture files work | Check effective `LLM_PROVIDER`; `fake` is fixture replay, not live extraction. |
| Gemini rejects configuration | Set a supported bare Gemini model ID and its key; do not leave a Claude model name. |
| Key is configured but calls fail | Inspect provider/model availability, credentials, quota and connectivity. A key-presence check is not a successful request. |
| API works in a terminal but the bot still behaves like fixture replay | Restart the worker that processes Telegram jobs; check for an old host/container worker and cached settings. |
| Upload gets no summary | Check that the file reached Switch, the room/person is bound, the worker is running, and extraction did not fail. Inspect the specific receipt/job rather than repeatedly re-uploading. |
| File download timed out | The bill may not have been added. Let supported retries run; if asked, resend it. Earlier testing encountered Telegram DNS failures. |
| Two sessions evict one another | Stop competing instances through their owner and establish one adapter/runtime controller. |
| Replies stay withheld after a member was removed | Known Switch membership limitation; use verified fresh-group recovery and audited `rebind-room`. Do not disable audience checks. |
| No file visible after approval | Distinguish artifact generation, Switch acceptance and recipient visibility. Check the CA group, then use supported per-file resend. |
| Old withheld messages affect health | Preserve them as test evidence; inspect their age/status. Do not delete them just to make the report green. |
| An old command references a different revision or snapshot | Open the current summary/request and use its exact values; never copy earlier test references blindly. |

## 10. What a connected API automates today

After setup and a verified worker restart, uploading a bill automatically invokes the selected live extraction provider, produces structured fields, and continues the existing workflow. Confirmed details trigger deterministic checks; issues create review requests; valid human decisions update the case; approved packs generate exports.

The owner still confirms facts, the CA still decides and approves, and an operator still configures the current deployment. Fully guided setup, command-free conversations, buttons, and one-command multi-agent orchestration remain separate planned features.
