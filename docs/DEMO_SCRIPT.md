# Assure Flow: 3-minute demo script

**The one idea to land:** the Telegram groups are the product. An owner can work alone, an owner and a CA can work together, and Switch connects the people and the agents. Code does the checking, and people make the decisions.

| Role | Who | Screen |
|---|---|---|
| **A: Ramesh, shop owner** | You | Left half: Telegram group `af-shop-sharma` |
| **B: Priya, the CA** | Your teammate | Right half: Telegram group `af-ca-review-recovery` |

Keep both groups visible the whole time, so viewers see a message leave one room and arrive in the other. Spoken lines are in quote blocks.

## Run sheet

| Time | Beat | What it proves |
|---|---|---|
| 0:00 | 1. The problem | Why this exists |
| 0:15 | 2. Two rooms, one agent | Switch is the interface |
| 0:30 | 3. Owner working alone | One person can use it |
| 0:55 | 4. The code catches a tax error | Checks are code; rooms stay private |
| 1:25 | 5. Calling another agent | Agents help but can't decide |
| 1:45 | 6. CA asks for a correction | Two people working across rooms |
| 2:05 | 7. Corrected bill replaces the old one | Stale decisions are refused |
| 2:25 | 8. Monthly pack approved | The real outcome: files |
| 2:45 | 9. Switch off | It can't work without Switch |

---

## The script

### 1. The problem (0:00–0:15)

**Screen:** title card, "Assure Flow: GST bill review inside your team chat", small caption "Synthetic demo data". Then both empty groups.

> **A:** "I run a small shop. Every month, I send my accountant a pile of bills over chat. Mistakes get found late, and nobody knows which version is the right one."

### 2. Two rooms, one agent (0:15–0:30)

**Screen:** show the two groups, then the agent joining the shop group.

**A types:** `/invite_agent @assure-flow`

> **B:** "So we work where we already talk. Ramesh has his shop group. I have a private review group. Assure Flow sits in both through Switch. He can't see my room."

### 3. Owner working alone (0:30–0:55)

**A sends:** `F01_clean_intrastate_5pct.pdf`, **as a file**. No mention and no command.

**Screen:** `Received R-0001…`, then the bill summary. Add a caption, "Sped up", over the wait, then zoom in on the supplier and `Total: ₹7,770.00`.

**A types:** `ok INV-0001 r1`

**Screen:** `INV-0001 r1 confirmed. Running the GST checks.` Then **B's room** receives `RR-0001 · All required checks passed`.

> **A:** "On my own, I just send the bill. The AI reads it, and I confirm the details myself. That's all I have to do. If this bill is clean, it goes straight to my accountant's queue."

### 4. The code catches a tax error (0:55–1:25)

**A sends:** `F08_wrong_tax_type.pdf`, then types `ok INV-0002 r1`.

**Screen:** zoom in on **B's room**:

```
RR-0002 · INV-0002 r1 · Sharma Kirana Store
Pune Electricals LLP · total ₹8,732.00
• R-TAX-01: Interstate supply (27 to 07) must use IGST only,
  but CGST 666.00 / SGST 666.00 are printed.
```

> **A:** "This one looked fine to me. I confirmed what's printed on it."
>
> **B:** "But the supplier is in another state, and they charged the wrong tax. No AI guessed that: fixed rules calculated it, and only I got the details, in my own room."

### 5. Calling another agent (1:25–1:45)

> **Rehearse this beat. It's the only one nobody has tested live.** If it doesn't work reliably, use the fallback below.

**B types:** `@<your-llm-agent> why is INV-0002 on hold?`

**Screen:** the agent explains the rule in plain words.

**B types:** `@<your-llm-agent> approve it for me`

**Screen:** the agent says it can't: it has no tool for approving.

> **B:** "I can call other agents into the room. This one reads the case and explains it. But I asked it to approve, and it can't. Agents can explain and draft. Only a person can decide."

**Fallback if it isn't reliable (same time):** show your agents in the Switch Console and say:

> **B:** "Switch lets us bring other agents into a room to read, explain and draft. But they're never given a tool to approve. Only a person can decide."

### 6. CA asks for a correction (1:45–2:05)

**B types:** `RR-0002 supplier please reissue with IGST for this interstate supply`

**Screen:** **A's room** receives the note that the bill is waiting for the supplier, with a draft:

```
Dear Pune Electricals LLP,
Please issue a corrected tax invoice for PEL/26/0461...
```

> **B:** "I decide the supplier has to fix it, and I never leave my room."
>
> **A:** "And I get a message that's ready to send. I don't see Priya's review notes, just what I need to do."

### 7. Corrected bill replaces the old one (2:05–2:25)

**A sends:** `F16_replacement_for_F08.pdf`, **as a file**, with the message `corrected bill for INV-0002`. Then types `ok INV-0002 r2`.

**Screen:** **B's room** receives the withdrawal notice, then `RR-0003 · All required checks passed`.

**B types the old request on purpose:** `RR-0002 include`

**Screen:** zoom in:

```
That refers to an older version. Nothing was changed.
Decide the newer review request instead.
```

> **B:** "It's the same case, with the history kept. And watch: I try to approve the old version, and it refuses. Nobody can sign off on a bill that has changed."

### 8. Monthly pack approved (2:25–2:45)

**B types, one at a time (speed up as needed):**

1. `RR-0003 include`
2. `RR-0001 include`
3. `snapshot sharma 2026-11`
4. `approve SN-0001 <hash from the message>`

**Screen:** `Included 2 · Total ₹16,502.00`, then **two messages, one file each**. Open the Excel file for one second.

> **B:** "At month end, I review one exact pack and approve it by its hash. If anything changes, that approval stops working. I get Excel and JSON, ready for my own filing work."

### 9. Switch off (2:45–3:00)

**Screen:** terminal: `docker stop switch-af-switch-1`. **A sends** `status`. No reply. Hold for two seconds.

> **A:** "And it really runs on Switch. Turn Switch off, and there's no intake, no review, no delivery. The rooms are the app."

**End card:** "Assure Flow. Built on Switch. Code checks. People decide." Plus the repository link and small print: "Synthetic data. A review pack, not a GST return."

---

## Before recording

### Use a separate database

The story needs fresh numbers, starting at `INV-0001`, and files already uploaded to a shop get refused as duplicates. A separate database gives you that **and keeps yesterday's test evidence**. Don't run `seed.loader` against the current database.

Stop the adapter and worker first, then run:

```powershell
docker exec af-dev-db createdb -U af assureflow_video
```

In `.env`, make these changes, keeping a note of the old values:

```
DATABASE_URL=postgresql+psycopg://af:af@localhost:5433/assureflow_video
PURCHASE_ASSURANCE_ENABLED=false
```

Then:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m seed.loader
.\.venv\Scripts\python.exe -m scripts.admin bind-rooms --prefix "Telegram: "
.\.venv\Scripts\python.exe -m scripts.admin rebind-room af-ca-review <switch-room-id-of-your-clean-CA-group> "clean CA group for the video"
```

The rebind is needed because `bind-rooms` picks the old CA group, which still lists the owner as a member.

Start the adapter and worker. Each person sends `status` in their own group, then run:

```powershell
.\.venv\Scripts\python.exe -m scripts.admin unmapped
.\.venv\Scripts\python.exe -m scripts.admin bind-user "<owner id from unmapped>" owner.sharma "<owner name Switch shows>"
.\.venv\Scripts\python.exe -m scripts.admin bind-user "<CA id from unmapped>" ca.mehta "<CA name Switch shows>"
```

The last argument must be the name Switch shows for that person. Send `status` again from each account: both should now get a reply.

To go back afterwards, restore the old `DATABASE_URL` and flag value in `.env`, then restart the adapter and worker.

### Rehearse once, start to finish

- **Gemini readings:** only four clean bills (F01, F02, F03, F05) have been measured live, so F08 and F16 are untested with Gemini. Check that the summaries show the numbers above.
- **If Gemini misreads a bill or is too slow:** set `LLM_PROVIDER=fake` and restart the worker. These are then recorded readings, so change the caption in beat 3 to "Recorded reading" and say "It reads the bill" instead of "The AI reads it".
- **Reference numbers:** if your rehearsal used up `INV-0001`, recreate the video database first.
- **Beat 5:** invite your other agent to the CA group and try both prompts. Replace `<your-llm-agent>` with its name.
- **Beat 9:** run this last. Afterwards, run `docker start switch-af-switch-1`.

### On-screen wording

The bot's messages are still the current technical wording, such as `RR-0002` and `INV-0002 r1`. The plain-English rewrite isn't finished. Re-record beats 3–8 if those messages change before you submit.

## Stay accurate

| Don't say | Why | Say instead |
|---|---|---|
| "It files GST" or "it's paid" | It produces a review pack only | "Ready for my own filing work" |
| "Multiple AI agents run the workflow" | `assure-flow` is code; other agents only read, explain and draft | "I can call other agents to explain and draft" |
| "Fully tested on Telegram" | Some cases need more accounts | Say nothing about test coverage |
| "It reads any bill accurately" | Only 4 clean synthetic bills have been read live with a successful comparison | "It reads the bill, and I confirm it" |
| Purchase assurance as a finished feature | Its full Telegram flow isn't verified | Leave it out, or on the end card: "Optional purchase matching behind a flag" |

Keep the "Sped up" caption anywhere you cut waiting time.
