# Manual test guide: the full workflow in real Telegram

This guide connects Assure Flow to **real Telegram groups** through Switch 0.31.0 and walks through every
part of the workflow by hand: shop intake, corrections, CA review, supplier replacement, GSTR-2B, monthly
approval, isolation, operations and recovery.

It takes about **90 minutes** the first time (30 minutes of setup, 60 minutes of tests).
Record each result in the [results sheet](#results-sheet) at the end and copy the summary into
[AUDIT_CHECKLIST.md](AUDIT_CHECKLIST.md) section M.

All invoices are synthetic, from `seed/fixtures/`. Never send real invoices.

---

## How it fits together

```
 Your phone / Telegram Desktop                Your laptop
 ┌──────────────────────────┐   polling   ┌─────────────────────────┐   WebSocket   ┌──────────────────────┐
 │ Telegram groups          │ ◀─────────▶ │ Switch 0.31.0 (Docker)  │ ◀───────────▶ │ Assure Flow          │
 │ af-shop-sharma, …        │  (outbound) │ Telegram connection     │  + HTTP       │ adapter + worker + DB │
 └──────────────────────────┘             └─────────────────────────┘               └──────────────────────┘
```

Switch opens the connection to Telegram from your laptop, so **nothing needs a public address**.

### Three Telegram rules that change how you set up

1. **A bot cannot create Telegram groups.** On Mattermost the agent creates its own rooms
   (`create-rooms`). On Telegram **you** create each group, add the bot, and Assure Flow then binds to it.
2. **Group Privacy must be off before the bot joins any group.** Otherwise the bot only sees messages that
   tag it, and a plain photo upload never arrives.
3. **Every person needs a Telegram `@username`.** Switch identifies people by username. An account with only
   a phone number cannot be bound.

---

## 1. What you need

### Telegram accounts

Each account maps to exactly one person in the seeded practice. One account cannot play two roles, because
the room-isolation checks would then (correctly) block messages.

| Account | Plays | Seeded handle | Needed for | Required? |
|---|---|---|---|---|
| A | Ramesh, owner of Sharma Kirana Store | `owner.sharma` | Shop room tests | **Yes** |
| B | CA Mehta | `ca.mehta` | CA review, practice home, GSTR-2B, approval | **Yes** |
| C | Owner of Gupta store | `owner.gupta` | Isolation between shops (T-14) | Recommended |
| D | Rao, operator | `ops.rao` | Operations room (T-19) | Optional |
| E | Iyer, developer | `dev.iyer` | Synthetic testing room (T-20) | Optional |
| F | Suresh, storekeeper | `staff.suresh` | Delivery room, purchase tests (P-xx) | For purchase tests |
| G | Anil, purchasing staff | `staff.anil` | Assigned task in the shop room (P-04) | For purchase tests |

Without C, D or E, skip the tests marked for them and use `make health` in the terminal instead of the
operations room. A second account can be a second phone number, or a teammate's account.

Tip: use **Telegram Desktop** on the laptop for account A, so you can send files straight from
`seed/fixtures/`, and the phone for account B.

### On the laptop

- The repository on branch `main`, the virtual environment, and `.env` (see the README Quickstart).
- Docker running.
- The Switch 0.31.0 standalone stack. The Gateway admin page is at http://localhost:3000.
- The Switch admin login you created when you first started the stack.

---

## 2. Start everything and reset to a clean state

Run all commands from the repository root with the virtual environment active.

```bash
docker compose up -d db                       # Assure Flow database on 127.0.0.1:5433
# Switch stack (from your Switch checkout, tag switch-v0.31.0):
docker compose -f deploy/local/standalone-docker-compose.yml --profile collab --profile gateway up -d
```

Reset Assure Flow to empty seeded data. This **deletes all cases** in the demo database; it refuses to run
unless `ENVIRONMENT=demo` or `test`.

```bash
python -m alembic downgrade base && python -m alembic upgrade head
python -m seed.loader
```

Register the agent, but only if `data/switch_credentials.json` does not exist yet:

```bash
SWITCH_REGISTRATION_KEY=<key from the Gateway> python -m scripts.admin register-agent
```

Do **not** start the worker and adapter yet.

---

## 3. Create the Telegram bot

1. In Telegram, open **@BotFather** and send `/newbot`.
2. Name it, for example `Assure Flow Test`, with a username ending in `bot`, for example `af_test_yourname_bot`.
3. **Save the token now.** BotFather shows it only once. Never paste it into a chat or into the repository.
4. Turn Group Privacy off. In BotFather send `/mybots`, choose the bot, then **Bot Settings** →
   **Group Privacy** → **Turn off**.
5. Give each environment its own bot. If two Switch servers poll the same token, they steal each other's messages.

---

## 4. Connect Telegram to Switch

1. Open the Gateway at http://localhost:3000 and sign in as the Switch admin.
2. Go to **Messaging Apps** → **Register messaging app** → **Telegram**. (Switch Console also works:
   server **Home** → **Messaging apps** → **Connect**.)
3. Fill in the form:
   - **Name:** `Telegram`. Rooms will be named `Telegram: <group title>`. If you pick another name, use it
     in step 6.
   - **Bot Token:** from BotFather.
   - **Bot Username:** the bot's username.
4. Select **Connect**. A bad token is reported right away.
5. Check the connection is listed with no error next to it.

---

## 5. Create the Telegram groups

Create these groups in Telegram. **The titles must match exactly**, because Assure Flow binds rooms by name.

| Group title | Members (besides the bot) | Created by |
|---|---|---|
| `af-shop-sharma` | A only | A |
| `af-shop-gupta` | C only | C (skip if you have no account C) |
| `af-ca-review` | B only | B |
| `af-practice-home` | B only | B |
| `af-operations` | D only | D (optional) |
| `af-synthetic-testing` | E only | E (optional) |
| `af-delivery-sharma` | F only | F (purchase tests only) |

For the purchase tests, also add account G to `af-shop-sharma`. Anil may see invoices (capability `invoice_view`); Suresh must **not** be in the shop room.

For each group:

1. Create the group with its member, then **Add Members** → search for your bot → add it. It needs no admin rights.
2. Make sure the bot posts **no** "can only see messages that tag it" warning. If it does, see
   [Troubleshooting](#troubleshooting).
3. Invite the Assure Flow agent by sending in the group:
   ```
   /invite_agent @assure-flow
   ```
4. Check with `!list-agents`. It should list `assure-flow`.

Do not put an owner in `af-ca-review` or `af-practice-home`, and do not put two shops' owners in one group.
Test T-15 does that on purpose, later.

---

## 6. Bind the rooms

```bash
python -m scripts.admin bind-rooms --prefix "Telegram: "
```

Expected output: one `BOUND` line per group you created, for example `BOUND af-shop-sharma -> 7c1e…`.
`MISSING` means the title is wrong or the bot was not added. Groups you chose not to create (gupta,
operations, testing) will show `MISSING`; that is fine.

Now start Assure Flow (two terminals, or `docker compose --profile switch up -d --build`):

```bash
python -m workers.runner
python -m adapters.run
```

---

## 7. Bind the people

Assure Flow only acts for people it knows. Until someone is bound, their messages are ignored.

1. Each person sends `status` in their own group (A in `af-shop-sharma`, B in `af-ca-review`, and so on).
   There will be no reply yet. This is expected.
2. List the unknown senders:
   ```bash
   python -m scripts.admin unmapped
   ```
   Each line shows a Switch participant id and the room it came from.
3. Bind each one to its seeded person, with their Telegram username (without `@`) as the third argument:
   ```bash
   python -m scripts.admin bind-user <participant id> owner.sharma <telegram username of A>
   python -m scripts.admin bind-user <participant id> ca.mehta     <telegram username of B>
   # C → owner.gupta, D → ops.rao, E → dev.iyer
   ```
   The username is what Switch reports as a room member. It must be right, or the member check in T-15 will
   block every message in that room.
4. Run `make health`. Everything should say PASS. With some groups skipped, `room bindings` lists the
   unbound ones; that is expected.
5. Optional: link your own account in Switch Console (server **Home** → the Telegram connection →
   **Link my account…** → **This is me**). Assure Flow does not need this; Switch uses it for owner-only agents.

---

## 8. Test cases

Send files as **files, not photos**. In Telegram choose "File" in the attach menu (Desktop: untick
"Compress images"). A compressed photo is a different file, so test T-03 would fail.

Each test lists who acts, where, what to send, and what you should see. Invoice and request numbers
(`INV-0001`, `RR-0002`) depend on order; use the numbers the bot actually gives you.

### Shop intake

**T-01 Bot answers in the shop room** · A in `af-shop-sharma`
Send `status`.
Expected: "No cases for Sharma Kirana Store …". Then send `help`; you get the list of shop commands.

**T-02 Clean invoice, no mention needed** · A
Send `F01_clean_intrastate_5pct.pdf` as a file, with no text and no @mention.
Expected, within about a minute:
1. `Received R-0001 … Saving the original now.`
2. `R-0001 saved as INV-0001 (1 page). Reading it now.`
3. A summary with supplier, GSTINs, taxable value, CGST, SGST, IGST and total, ending with
   `Reply ok INV-0001 r1 to confirm …`.

Reply `ok INV-0001 r1`. Expected: `confirmed. Running the GST checks.` and then no problems found.
A 👀 reaction and a "⚙️ Working on it…" message from Switch while it works are normal.

**T-03 Stored file is identical to what you sent** · laptop
```bash
sha256sum seed/fixtures/F01_clean_intrastate_5pct.pdf
docker exec af-dev-db psql -U af -d assureflow -c "select sha256, mime, size_bytes from documents order by created_at desc limit 3"
```
Expected: the newest row's `sha256` equals the file's hash.

**T-04 Unclear photo, typed correction** · A
Send `F13_blurry_photo.png` as a file.
Expected: a summary with one field marked `<- uncertain (page 1)` and one focused question.
Send a correction, for example `INV-0002 total=1180.00`. Expected: a new revision `r2` with the new value
(no re-reading). Then `ok INV-0002 r2`. Expected: confirmed.

**T-05 Confirm while holding a missing field** · A
Send `F07_missing_gstin.pdf` (the supplier GSTIN is not printed). The summary asks for the missing value.
Reply `ok INV-000X hold`.
Expected: confirmed with the field held, and the GSTIN checks show "needs evidence" instead of guessing.
`why-held INV-000X` explains why.

**T-06 Duplicate bill** · A
Send `F10_duplicate_original.pdf`, confirm it, then send `F11_duplicate_copy.pdf` and confirm that too.
Expected: the second one (same invoice number, different file) fails R-DUP-01/R-DUP-02 and goes to the CA,
never silently counted twice.
Then send `F10_duplicate_original.pdf` again, the exact same file.
Expected: "already received" pointing at the existing case, with no new case.

**T-07 Two invoices in one file** · A
Send `F21_two_invoices.pdf`.
Expected: split into two cases, one per page, each with its own summary.

**T-08 Status commands** · A
Send `status`, `pending` and `why-held INV-000X`.
Expected: short, correct answers that only mention Sharma's invoices.

### CA review and handoffs

**T-09 Tax problem goes to the CA room** · A, then B
A sends `F08_wrong_tax_type.pdf` and confirms it.
Expected in `af-ca-review` (B sees it, A does not):
`RR-000X · INV-000Y · R-TAX-01: Interstate supply (27 to 07) must use IGST only …`, with the evidence.

**T-10 CA asks for a corrected invoice; it comes back into the same case** · B, then A
1. B replies in `af-ca-review`: `RR-000X supplier please reissue with IGST`
2. Expected in `af-shop-sharma`: "INV-000Y is waiting for a corrected invoice …" with a ready-to-send supplier draft.
3. A sends `F16_replacement_for_F08.pdf` with the message `corrected bill for INV-000Y`.
4. Expected: the same case gets version 2 and the checks run again.
5. Expected in `af-ca-review`: `Withdrawn: RR-000X for INV-000Y no longer applies because a replacement document arrived.`

**T-11 CA decisions** · B
Try each one on an open review request (create more by sending `F09_total_mismatch.pdf`,
`F06_invalid_gstin.pdf` or `F17_wrong_recipient.pdf` as A):

| Send | Expected |
|---|---|
| `RR-000X include` | Included; request closed |
| `RR-000X exclude not a business purchase` | Excluded with the reason |
| `RR-000X clarify which branch received the goods?` | Question appears in the shop room |
| `RR-000X override R-DUP-02 confirmed separate deliveries` | Allowed (overridable rule); listed in the export later |
| `RR-000X override R-TAX-01 looks fine` | **Refused**: that rule cannot be overridden |
| `reopen INV-0001 recheck after supplier call` | Checks re-run on INV-0001 |

**T-12 A stale decision is refused** · B
Reply to an old review request after its invoice has a new revision (for example the RR withdrawn in T-10).
Expected: a refusal explaining that the request no longer applies.

### Isolation

**T-13 Owners never see CA content** · A
Look at `af-shop-sharma` after T-09 to T-11.
Expected: no review-request text, no CA decisions, only messages meant for the owner.

**T-14 Shop A never sees shop B** · C in `af-shop-gupta` (needs account C)
1. C sends `status`. Expected: only Gupta's cases (none at first).
2. C sends `ok INV-0001 r1` (an invoice number that belongs to Sharma).
   Expected: "I could not find that in this room's scope …".
3. C sends `F18_gupta_photo_clean.png`. Expected: a Gupta case, never visible in `af-shop-sharma`.

**T-15 Wrong person in a room → message withheld** · A and B
1. B adds account A to `af-ca-review`. A sends any message there (Switch only knows about members who have posted).
2. In `af-ca-review`, B sends `pending`.
3. Expected: **no reply in `af-ca-review`**. The message is withheld, and `af-operations` (or
   `make health` → `outbox`) shows an alert with ids only, no invoice content.
4. Remove A from `af-ca-review`. Withheld messages stay withheld; send `pending` again to get a fresh reply.

Telegram limit: Switch only reports members it has seen post, so a member who never speaks is not caught by
this check. The declared-audience check in Assure Flow still applies.

**T-16 Stranger is ignored** · any account not bound (or a bound one in a group it does not belong to)
Send `status` in a group. Expected: no reply with any data. The sender shows up in `scripts.admin unmapped`.

### Month end

**T-17 GSTR-2B reconciliation** · B in `af-ca-review`
Send `seed/fixtures/gstr2b_sharma_2026-11.xlsx` as a file with the message `gstr2b sharma 2026-11`.
Expected: `RC-000X · exact match … · mismatch … · purchase only … · statement only … · ambiguous …`.
Send the same file again. Expected: nothing changes (the upload is idempotent).
Then try `gstr2b_sharma_2026-11.json`. Telegram relays documents byte-for-byte, so it may work here even though
Mattermost cannot relay `.json` (D-18). **Record the result** either way.

**T-18 Snapshot and approval with files delivered in Telegram** · B
1. `readiness sharma 2026-11`. Expected: counts of included, held and unassigned invoices.
2. `snapshot sharma 2026-11`. Expected: `SN-000X · hash <12 chars> · Included …`.
3. `approve SN-000X <the 12-character hash>` (add `ack <held> <unassigned>` if it asks).
4. Expected: `SN-000X export: Excel + JSON attached.` and **two files arrive in the Telegram group**.
5. Open the Excel file. It should show the included invoices, issues and overrides from T-11. Cells must not
   run formulas.
6. `approve SN-000X 000000000000` (wrong hash). Expected: refused.

**T-19 Practice home** · B in `af-practice-home`
Send `directory`, then `readiness sharma 2026-11`.
Expected: the practice's shops and month readiness. No invoice details from the CA room.

### Operations and testing (optional accounts)

**T-20 Operations room** · D in `af-operations`
Send `health`, `failed` and `trace INV-0001`.
Expected: the health report, failed jobs (probably none), and the full event history for INV-0001.
Alerts from T-15 appear here.

**T-21 Synthetic testing room** · E in `af-synthetic-testing`
Send `acceptance`. Expected: a few minutes later, a report with 85/85 passed.

### Recovery

**T-22 Worker stopped, then started** · laptop + A
Stop `workers.runner`. A sends `F02_clean_scan_12pct.pdf`. Only the receipt is saved and no summary
arrives. Start the worker again.
Expected: processing continues and the summary arrives **once**.

**T-23 Adapter restarted** · laptop + A
Restart `adapters.run`, then A sends `status`.
Expected: one reply, and no old messages replayed.

**T-24 Without Switch, nothing works** · laptop + A
Stop the Switch container (`docker stop switch-af-switch-1`). A sends `status`.
Expected: no reply, and `make health` shows `switch server` FAIL.
Start it again (`docker start switch-af-switch-1`) and record whether the waiting message is delivered.
Telegram keeps undelivered updates for up to 24 hours.

**T-25 Revoking a person** · laptop + C
`python -m scripts.admin revoke-user owner.gupta`, then C sends `status`.
Expected: no reply. Rebind C with `bind-user` to undo.

### Purchase assurance (optional; needs accounts F and G)

Turn it on first: set `PURCHASE_ASSURANCE_ENABLED=true` in `.env`, then restart the worker and adapter. Bind F to
`staff.suresh` and G to `staff.anil` (section 7). The seeded order is **PO-101**: 10 cartons of "Sunflower oil 1L x 12"
from ABC Traders at ₹500.00 per carton.

**P-01 Order confirmed; storekeeper asked without prices** · A in `af-shop-sharma`
Send `ok PO-101 r1`. Expected: "PO-101 r1 confirmed". In `af-delivery-sharma`: "please count what arrived" with
**no ₹ amount or price**.

**P-02 Invoice linked to the order** · A
Send `F22_abc_invoice_10_cartons.pdf` as a file, then `ok INV-000X r1`.
Expected: "INV-000X looks like PO-101 …". Reply `link INV-000X PO-101`. Expected: "linked to PO-101".

**P-03 Storekeeper counts 8; code holds the purchase** · F in `af-delivery-sharma`, then B
F sends `PO-101 L1=8`, then `ok DR-0001 v1`. B includes the invoice's review request in `af-ca-review`.
Expected in the shop room: "payment readiness is on hold … billed 10 carton but 8 confirmed received (difference 2)".

**P-04 Assigned work; finishing it does not clear the hold** · A, G
A sends `task INV-000X anil tomorrow get a corrected invoice for 8 cartons`. G sends `TK-0001 ack`, then
`TK-0001 done supplier is sending a revised bill`. A sends `TK-0001 verify`.
Expected: verify is **refused**: "cannot be verified yet … A finished task alone never clears a mismatch."

**P-05 Corrected invoice; partial delivery accepted** · A, B
A sends `F23_abc_corrected_8_cartons.pdf` with the message `corrected bill for INV-000X`, then `ok INV-000X r2`.
B includes the new review request. A sends `accept-partial PO-101`, then `TK-0001 verify`.
Expected: "Still outstanding on PO-101: 2 carton …"; then `PR-0001` appears in `af-ca-review` with a hash.

**P-06 Reviewer, then owner, sign the same record** · A, B
A first tries `authorize PR-0001 <hash> due 2026-11-20`. Expected: refused, "has not been reviewed yet".
B sends `review PR-0001 <hash>`. A sends `authorize PR-0001 <hash> due 2026-11-20`.
Expected: "PR-0001 is ready for payment: ₹4,200.00 … Nothing has been paid", then an Excel + JSON purchase pack in
the shop room and the CA room.

**P-07 Storekeeper privacy and authority** · F, G
Read every message in `af-delivery-sharma`: no ₹, no unit price. F sends `link INV-000X PO-101` in any room it can
reach, and G sends `accept-partial PO-101`. Expected: both refused ("not set up to …").

**P-08 A change after review withdraws the record** (run on a fresh database with delivery 10)
After B's `review`, F sends `DR-0001 L1=9` and `ok DR-0001 v2`.
Expected: "Withdrawn: PR-0001 … because the confirmed delivery changed"; A's `authorize` is refused.

---

## Results sheet

Copy this table into your notes or the pull request, and fill it in as you go.

| Test | Pass / Fail / Skipped | Notes (message ids, timings, screenshots) |
|---|---|---|
| T-01 Bot answers | | |
| T-02 Clean invoice, no mention | | |
| T-03 Hash matches | | |
| T-04 Unclear photo, correction | | |
| T-05 Hold | | |
| T-06 Duplicate | | |
| T-07 Split file | | |
| T-08 Status commands | | |
| T-09 Handoff to CA | | |
| T-10 Supplier replacement and withdrawal | | |
| T-11 CA decisions | | |
| T-12 Stale decision refused | | |
| T-13 Owner never sees CA content | | |
| T-14 Shop isolation | | |
| T-15 Wrong member → withheld | | |
| T-16 Stranger ignored | | |
| T-17 GSTR-2B (Excel / JSON) | | |
| T-18 Snapshot, approval, files | | |
| T-19 Practice home | | |
| T-20 Operations room | | |
| T-21 Testing room | | |
| T-22 Worker restart | | |
| T-23 Adapter restart | | |
| T-24 Switch down | | |
| T-25 Revoke | | |
| P-01 Order confirmed, no prices to storekeeper | | |
| P-02 Invoice linked | | |
| P-03 Count 8 → hold | | |
| P-04 Task done does not clear hold | | |
| P-05 Corrected invoice, partial accepted | | |
| P-06 Review then authorize, pack delivered | | |
| P-07 Storekeeper privacy and authority | | |
| P-08 Change after review withdraws | | |

Tester: ______  Date: ______  Commit: `git rev-parse --short HEAD` ______  Switch version: 0.31.0

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Bot posts "can only see messages that tag it" | Group Privacy was on when it joined. Turn it off in BotFather, then remove the bot from the group and add it back, or make the bot a group admin. |
| Messages arrive only sometimes | Another Switch server is polling the same bot token. Stop it, or make a second bot. The Switch logs show a "polling conflict". |
| `bind-rooms` says `MISSING` | The group title is not exactly right, the bot is not in the group, or the connection is not named `Telegram` (use `--prefix "<your name>: "`). |
| `bind-rooms` says `AMBIGUOUS` | The same title exists on two connections (for example Mattermost and Telegram). Pass `--prefix`. |
| No reply at all to a bound person | Check the worker and adapter are running, and that `assure-flow` is invited (`!list-agents`). Then check `make health`. |
| Every reply in one room is withheld | Someone in that room is not bound, or was bound with the wrong Telegram username. Check the alert in `af-operations` (or the outbox line in `make health`) and fix with `bind-user` / `revoke-user`. |
| Room stopped working after adding members | Telegram turned the group into a supergroup with a new id. Switch follows it and says so in the chat. If Assure Flow stops replying, run `bind-rooms --prefix "Telegram: "` again. |
| Hash in T-03 does not match | The file was sent as a compressed photo. Send it as a file. |
| Long message split in two | Telegram limit of 4096 characters. Expected. |
| Person missing from `unmapped` | They have no Telegram username, or they have not posted in a group the bot can see. |

## Cleaning up

1. Remove the bot from the groups (or delete the groups).
2. In the Gateway, remove the Telegram connection. **Disconnecting deletes those Switch rooms and their history**;
   the Telegram groups stay.
3. In BotFather, `/revoke` the token if it was ever shown on screen during a recording.
4. To go back to the Mattermost rooms, run `python -m scripts.admin bind-rooms` (exact names win over Telegram ones).
