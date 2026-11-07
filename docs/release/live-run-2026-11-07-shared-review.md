# Live run: shared review, client room and P0 fixes on Mattermost (7 November 2026)

**What ran:** `python -m tests.live.shared_story`, on the code in commit `223a2c3`, Switch 0.31.0 with the bundled Mattermost, against a separate seeded database. Recorded extractions (`LLM_PROVIDER=fake`), purchase assurance off, shared review on for `sharma`.

**Independent accounts:** `sharma` (owner), `mehta` (CA), `iyer` (client), `gupta` (another shop's owner), `rao` (operator). All are synthetic Mattermost users.

**Scope:** this is Mattermost evidence. It doesn't replace the Telegram cases, which remain as recorded in [telegram-manual-2026-11-06.md](telegram-manual-2026-11-06.md). An LLM agent wasn't part of this run, and the suggestion line comes from code.

## Story: 33/33 checks passed

| Area | Check |
|---|---|
| Owner alone | Upload is read and summarized |
| | Confirmed bill reaches the shared group with a labelled suggestion |
| | Private room gets a pointer without details |
| Client | Bill appears in the group with who sent it |
| | Summary goes to the owner |
| | Client gets a received note |
| | Bill reaches the CA after the owner confirms |
| | Client never sees case details |
| | Client commands get no reply |
| Conversation | Ordinary conversation gets no agent reply |
| | A bare `ok` doesn't confirm a bill |
| Authority | CA can't confirm bill details |
| | Owner can't decide |
| | Stale decision is refused |
| Correction | Code catches the wrong tax, in the group, with a suggestion |
| | Results can be brought up in the group |
| | CA decides in the group; supplier draft appears |
| | Corrected bill gets a new review |
| | CA includes the corrected bill in the group |
| Private room | CA can also decide from the private room |
| Isolation | Another shop's owner can't reach this shop's bill |
| | Nothing from this shop reaches the other shop's room |
| Monthly pack | A pack can't be built from the shared group |
| | Pack is built in the private room |
| | Two messages, one file each |
| | Pack stays out of the shared group |
| | `resend` delivers the stored Excel file |
| Reopen | Approved case can be reopened |
| | Approved pack is labelled superseded |
| Override | Review offers the R-DUP-02 override |
| | Permitted override is recorded |
| | A decided request refuses another override |
| Operations | Operator gets a reply to `health` |

The operator check only confirms that a reply arrived; it doesn't check the report's content. The story confirms the override's reply but doesn't open the next export: the export content is covered by offline tests. The Excel and JSON files were counted, not opened by a person.

## Controlled adapter restart (T-23, on Mattermost): passed

One session owned the runtime throughout.

| Step | Result |
|---|---|
| Owner sends `status` | One reply, delivered |
| Start a second adapter | Refused, exit code 1: "An Assure Flow adapter is already running: af-adapter … pid 13212" |
| Stop the adapter; owner sends `status` | Not received while down |
| Start the adapter | That message arrived at 08:26:10 UTC with one reply, delivered |
| Owner sends `status` again | One reply, delivered |
| Inbox after the run | 38 events, 38 distinct event ids: nothing replayed |

## Not covered

- Telegram delivery of any of this, including whether two files are visible to a person on Telegram.
- Live Gemini reading in this flow.
- An LLM agent in a room.
- Purchase assurance (P-01–P-08). Its last live run was at `7cd5076`, also on Mattermost.
- Removing a member from a Telegram group, which still needs the Switch patch.
