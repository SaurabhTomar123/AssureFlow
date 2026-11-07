# Telegram manual testing — 2026-11-06

> Real Telegram account names, chat ids and internal ids are replaced with placeholders in this published copy. No results were changed.

Tester: Codex, with user assistance for account and bot setup.
Commit under test: `7cd5076401ca1abdf92d9fb923e77ded331a4dd1`.
Status: **Available-account workflow exercised through export and recovery. Failures and unavailable multi-account tests remain; this is not a full pass. See current coverage below.**

## Findings requiring follow-up

1. Approved-case `reopen` is refused despite the manual guide's example. Excluded-case reopening works.
2. The documented allowed R-DUP-02 override is refused in `ready_for_ca`; no override record is saved, so its export coverage is blocked.
3. After Telegram removal, Switch still reports the owner as a CA-room member and withholds new replies. Recovery required a fresh CA group; the member check was not weakened.
4. User could not see the original grouped Excel/JSON export despite bridge delivery metadata. Separate sends through Switch were confirmed visible. Album visibility remains unresolved.

No application-code fixes were made during this testing run. Existing deleted fixture `F09_total_mismatch.pdf` was left untouched. Final runtime check: Switch reachable, worker/adapter operating, no active jobs, owner identity restored, four historical withheld messages preserved as isolation evidence. CA workflow is bound to `af-ca-review-recovery`; generic room rebinding would select the old CA room, so consult the explicit recovery binding below.

## Verified prerequisites

- Local PostgreSQL, Switch 0.31.0, and Gateway containers are running.
- `python -m scripts.health`: 12 PASS. These describe the existing deployment; they do not prove Telegram connectivity or a running adapter.
- `python -m pytest tests/offline`: 94 passed, 1 warning, 259.97 seconds.
- `python -m ruff check .`: all checks passed.
- `python -m mypy`: no issues in 63 source files.
- API/MCP isolation checks: 2 passed, 6 deselected, 12.08 seconds. Initial standalone attempts encountered Windows temporary-directory access/setup errors; rerunning with a fresh workspace-local `--basetemp` succeeded.
- Telegram Web is signed in through Edge. Verified official @BotFather chat opened.

## Pending setup and limits

- User created `<telegram-bot>` and proceeded through Telegram connection setup. Group Privacy setting has not yet been independently verified.
- Second Telegram account for the CA role is not yet available. Separate accounts are required for role and isolation tests.
- Update: user reports a separate CA account as `<ca-telegram-handle>` and created `Telegram: af-ca-review`; bound that room to `<id>`. Its initial `status` arrived but was rejected as `unbound_room` before binding. Live room membership and sender instead identify `<ca-telegram-name>`; CA identity binding awaits confirmation of that discrepancy.
- CA binding update: after user reaffirmed `<ca-telegram-handle>` and sent a fresh requested `status`, inbox `sw_6b14ce5af196aeeb8918020c18510060` arrived through the same participant (`<ca-telegram-name>`), rejected only as `unmapped_sender`. Switch source shows Telegram fallback names include numeric user ids and client addresses retain their original localpart. Bound that observed participant to `ca.mehta`, using current live membership name `<ca-telegram-name>` for the audience check. A fresh CA command must verify authorized processing; the Telegram username/display-name discrepancy remains documented.
- CA authorized round trip **PASS**: `pending` inbox `sw_5576c66d9823bd643ce0cc8048a50e21` processed. Reply `sw_3047ac7be6074fbf98b8c5d2647a6201` delivered to the Telegram CA room, listing open review requests RR-0003 through RR-0008. No outbox error. Ready for T-09 fresh Telegram-to-Telegram handoff.
- Agent `list_rooms` now includes `Telegram: af-shop-sharma` (`<id>`). Bound `af-shop-sharma` to that room using `bind-rooms --prefix "Telegram: "`. Other Telegram groups are still missing; existing bindings for those rooms remain in place.
- Worker and adapter Python processes are present. Owner's first `status` reached the inbox and appeared in `scripts.admin unmapped`, verifying incoming Telegram transport. Bound the observed participant `<telegram-participant-id>` to `owner.sharma` with the exact live-member username `<owner-telegram-name>`. Health after binding: 12 PASS, 8 identities, no queued jobs or withheld/dead messages. A fresh `status` and `help` are required to finish T-01; the pre-binding message was intentionally ignored.
- Extraction provider is `fake`; purchase assurance is enabled. This run uses synthetic fixture extractions and does not validate live model extraction.
- Existing demo data and room bindings have not been reset or changed.

## Manual workflow coverage

T-01 **PASS**: user screenshot shows correct Sharma status and shop help replies. Inbox events `sw_c2cdde7a87b142c175917497a619d5ed` (status) and `sw_ca8ceaa2699d9ff3b2a90c84deee8658` (help) are processed. Outbox events `sw_75a0c08b76824027956c390c19debbc5` and `sw_33ebe34792634ca6a2e9e4671b674464` are delivered. Existing demo data explains the status counts (1 approved, 1 awaiting confirmation); this was not an empty-database run.

T-02 **PASS with guide wording deviation**: F01 PDF uploaded without a mention. Inbox `sw_1f37c9e7acab54f982b0c14cf4f5b046` processed; receipt `R-0004` saved as `INV-0003`, revision 1, one page. Receipt, saved notice, and summary all delivered (`sw_47723300659343818f469e9d83754174`, `sw_0e58be08f0234036885b83e6893b2daf`, `sw_3ea562fda64b41d7814c4538df75f97c`). Summary: taxable INR 7,400, CGST 185, SGST 185, total 7,770. Owner confirmation inbox `sw_522e30eedc71c44e8126ef086fad221c` processed, confirmation reply `sw_a946fa09232246d19666fbb878da3297` delivered. Revision 1 confirmed; check run 1 is `clean`, all 10 rule results pass, invoice state `ready_for_ca`. Wording deviation: the owner gets "Running the GST checks"; "All required checks passed" is delivered to the existing non-Telegram CA room as `RR-0003`, not back to the owner. Telegram CA handoff remains untested until that room is created and bound.

T-03 **PASS**: source PDF, document database SHA-256, and stored file bytes all hash to `04e3e98c7f4be5dcce145e02c761efa5e44f12a1a09084234c3b9357ce4cf7d2`. MIME `application/pdf`, size 2,684 bytes, one page.

T-04 **PASS**: F13 upload inbox `sw_6bf008ea1ac0d11d1d785bbd0e72453d` processed. Saved as `INV-0004 r1` (`R-0005`). Delivered summary `sw_164bd9338d5f49d2a08193a3b4edb6ff` marks total INR 1,780 as uncertain on page 1 and asks exactly "is the total correct?". Original PNG preserved: 62,197 bytes, source/database/stored hash `d4bbfc03a2dd7f9e57edc60c31d7d929056d952b6c61f141e598ded49de90d27`. Correction inbox `sw_7fbe4abe99f73731abaaf69e0e2137c4` processed: r1 superseded; r2 source `human`, total INR 1,180, same document id and document generation 1. Corrected summary delivered as `sw_8b63d77ec358426582e7665f4d1e0af3`. Confirmation inbox `sw_14baf06ad4e07ec5027fbe50366d7a0f` processed; reply delivered as `sw_2b3bfb85802d4790ab5e70482fef7d1f`. r2 confirmed, all 10 checks pass, invoice `ready_for_ca`.

T-05 **PASS, with UX observation**: F07 inbox `sw_5345e1d6dc88355ecee9cad84dabf91e` processed; receipt `R-0006`, case `INV-0005 r1`. Summary `sw_7e8f1de9f9cd426dbaf7058be0da3aaf` delivered, explicitly identifies missing Supplier GSTIN, with no guessed value. Source/database/stored SHA-256 matches `2e7ab2e78985087f497a3a86362e8aaa77ca1f87f91a75b030e7bc32372d2d24`. Hold confirmation `sw_376f8ea0e67298fff668ce64550152f2` and why-held `sw_299c84ffcbf14d96d2a8aa252ef7460b` processed. Revision confirmed with supplier GSTIN still NULL; invoice `needs_resolution`, check run `blocking`. R-GSTIN-01 and R-TAX-01 report `needs_evidence`; remaining eight rules pass. Confirmation, owner evidence request, and why-held explanation delivered (`sw_868dfd99d354408d91d4ac235b0a4223`, `sw_1f2b8ad9f0ca48ecaf08c93f2e3fdceb`, `sw_7c4c6f5c67e245b493a53ef581c3db05`). UX observation: the evidence request correctly names missing GSTIN but gives generic correction example `pos=07`, which does not supply that GSTIN.

T-06 **PARTIAL — semantic duplicate passed; exact-file re-upload pending**: F10 inbox `sw_6a67c0fe40ac696904400e4f99eb948f` processed as `INV-0006 r1`, supplier Shree Dairy Foods, invoice SDF-5520, total INR 5,936. Confirmation `sw_bbbf7b316fc1036f586bfc4765ccf6b2` processed: revision confirmed, clean check run, `ready_for_ca`. F11 upload `sw_a1061915af870dfc7decf9a76aeae839` and confirmation `sw_d92adac56ad6d3f811d6d63b977c40ad` processed as `INV-0007 r1`: confirmed, blocking check run, `needs_resolution`. Both R-DUP-01 and R-DUP-02 fail against INV-0006, including normalization of SDF/5520 versus SDF-5520. Review request `RR-0006` delivered to the existing non-Telegram CA room; Telegram CA delivery is not yet tested. Both uploaded files match their originals. Each currently has exactly one stored document. Next: upload F10 again and verify an existing-case response without another invoice.

T-06 exact-file re-upload **PASS**: inbox `sw_9ff8f5f17534ff9ac1f391f7cece2ba6` processed. Delivered reply `sw_81048732ec4341108a83ac8f25e67e59`: "R-0009 is the same file as INV-0006, which is already saved. No new case was created." Database retains exactly one F10 document; latest invoice remains INV-0007. Together with the semantic duplicate checks above, T-06 business behavior passes; CA transport was the existing non-Telegram room.

T-07 **PASS**: upload inbox `sw_9ab9dd5b6816ce9ba635b78e04c6d92c` processed as receipt `R-0010`. Exactly two cases created: `INV-0008` page 1 (Royal Spices, RSC-2026-260, total INR 1,764) and `INV-0009` page 2 (Delhi Packaging, DPC-801, total INR 3,024). Both revision 1, `needs_confirmation`. Separate page ranges 1–1 and 2–2 reference the preserved original PDF, whose stored hash matches the source. Split notice `sw_cd784198be97414597ad518d179375cd` and both summaries (`sw_01c19aaa916248bab7298bb750a140f2`, `sw_9971c021e62b4b288c65f634d5f09632`) delivered.

T-08 **PASS for current dataset**: split-case confirmations `sw_f01acc70ac00c9304e3fd1e6c6e60228` and `sw_b105716e824d07c11871fbd7de683731` processed; INV-0008 and INV-0009 revision 1 confirmed and `ready_for_ca`. `status` (`sw_67c1fd81ad1f30425138f0587e742088`) and `pending` (`sw_812e66b3977e44a9cf9f8029374b26f0`) processed. Delivered status reports 1 approved, 1 needing confirmation, 2 needing resolution, 5 ready for CA. Pending excludes the approved invoice and reports only open cases; with purchase assurance enabled it also delivers "No open purchase tasks." All listed invoice references belong to Sharma. `why-held INV-0005` was verified in T-05. Live cross-shop negative coverage remains T-14, pending another account.

T-09 **PASS**: initial F08 upload in the CA room was ignored with `not_a_workflow_event` and created no invoice. Subsequent owner upload in `af-shop-sharma` and `ok INV-0010 r1` both processed. INV-0010 revision 1 confirmed; check run 1 blocking, R-TAX-01 fails because interstate supply 27 to 07 prints CGST/SGST INR 666 each instead of IGST. Review `RR-0009` delivered to Telegram CA room `<id>` as `sw_e505e72b0b824f658b6ee8221b164673`; no transport error. Owner confirmation delivered as `sw_e147e2543443424c837675b56a844f05`. Review-request details were routed to CA, not posted in the owner room.

T-10 **PARTIAL — replacement and invalidation passed, new confirmation/checks pending**: CA command `RR-0009 supplier please reissue with IGST` processed as inbox `sw_15deb3fdbeb2705fa032bb297108826d`. Supplier correction draft delivered to Telegram owner room as `sw_c8926fd7693a48e49642093469bd7335`. F16 replacement caption inbox `sw_5c8a89570f0bf09c3ef815c78f75d69e` processed: same INV-0010, document generation 2, r1 superseded, r2 source `replacement`, draft. Source and stored replacement bytes match. r2 shows CGST/SGST zero and IGST INR 1,332. Owner gets replacement notice `sw_5b14e080148d44bb84a5bb1599c4e60f`, confirmation invalidation `sw_af06aa57288a4b33b0c8d0c15e9cb68a`, and summary `sw_cab95f66bc42494c8ba89926a4f1bc26`. CA gets `sw_32e2890357e14c7f9f49271165d1d1fe`: "No longer applies: RR-0009 'request supplier replacement' ... because a replacement document arrived. The case needs a new decision." Notice wording differs from the guide's literal "Withdrawn", while conveying invalidation. Next: confirm r2 and test a stale RR-0009 decision.

T-10 completion **PASS with notice wording deviation above**: confirmation inbox `sw_667bc7cb40c44d5258a86f1b8e485d8c` processed, r2 confirmed, current check run `clean`, R-TAX-01 passes, case `ready_for_ca`. New review `RR-0010` delivered in Telegram CA room as `sw_562a8b3f8a4440daba7b44d94692d809`.

T-12 **PASS**: stale `RR-0009 include` inbox `sw_8bef1d309d1fad696af70b1b83bc5f3d` processed. Refusal `sw_0083360c6afc4626850be56b427a6031` delivered: older version, nothing changed, current r2, decide newer review request. Case remains awaiting CA rather than approved.

T-11 **PARTIAL — include/exclude/clarify passed; override/reopen pending**: CA commands `RR-0010 include`, `RR-0006 exclude duplicate invoice`, and `RR-0004 clarify please confirm which branch received the goods` processed as inbox events `sw_21a4139dd8f94ae95caa0a42394c13c6`, `sw_3ce15d5eaa355596822e98975e2eda87`, and `sw_eaef7d8e82e24b2affc03148a3d1854b`. INV-0010 now approved, INV-0007 excluded, INV-0004 needs_resolution. All three CA replies delivered. Clarification delivered to owner as `sw_e147a1d1962f4df18fd3c033c58aea84`. UX observation: free-text branch question is followed by a generic numeric `total=1180.00` correction example; answering a branch question is not explained.

T-11 reopen **FAIL**: CA sent `reopen INV-0010 recheck after supplier call`; command processed but reply `sw_2acb48ef192c41c3a57c15a4cab36d89` says "'ca_reopen' is not allowed while the case is approved". Case remains approved, contrary to the manual guide's expected recheck behavior. Investigate state transition policy before claiming T-11 complete.

T-11 non-overridable arithmetic setup: F09 uploaded and confirmed as INV-0011 r1; check R-AMT-03 fails because parts total INR 2,832 but invoice states INR 2,932 (difference INR 100). Case `needs_resolution`; RR-0011 delivered to CA as `sw_ae808abeafc74a71851b8c2b70165b6c`. Next: attempt override of R-AMT-03. Local source F09 is currently deleted in the worktree (user change); original fixture hash was obtained from the Git HEAD blob to verify the uploaded document without restoring or overwriting it.

T-11 non-overridable arithmetic **PASS**: `RR-0011 override R-AMT-03 looks fine` processed as `sw_b500544d4f71e5cdd80e193ec13d0ed1`; refusal `sw_4ba9cd5c329746c0baf0982126083654` delivered, explicitly states R-AMT-03 is never overridable. INV-0011 remains `needs_resolution` with its blocking check.

T-11 excluded-case reopening **PASS**: `reopen INV-0007 recheck duplicate after supplier call` processed as `sw_adc697ddbc6bad1e9caa4b7aa2dacdd5`; second check run remains blocking and new review RR-0012 delivered as `sw_be8ae8287d0641fea844f7f94ec6edbb`. Reopen confirmation `sw_33b1ba45498c4678a104d1c10c6b5b81` delivered. Case moves from excluded to `needs_resolution`. Approved-case reopening remains the earlier documented failure. Successful allowed override and the guide's specific R-TAX-01 override refusal have not yet been exercised manually.

T-11 allowed-override setup: owner correction `INV-0007 number=SDF-5521` (`sw_7fb0fbf06e018caeec190176c1b3964c`) and r2 confirmation (`sw_512be7c876aa2ef23b331a1088205b08`) processed. r2 confirmed with distinct invoice number; exact-duplicate failure clears, only R-DUP-02 remains a failed warning. Case `ready_for_ca`, current run labeled `clean` despite this nonblocking warning. New review RR-0013 delivered as `sw_a74fd2c1e7ae421bb16f7f1d6647769b`. Next: attempt explicit R-DUP-02 override and inspect its persisted audit/export evidence.

T-11 allowed R-DUP-02 override **FAIL**: `RR-0013 override R-DUP-02 confirmed separate deliveries` processed as `sw_d3a6e368fa19bd4234b995335d4a5e5b`; reply `sw_8b4f272f0c2c4a18998d4931dfdc8945` refuses `ca_include_with_override` while case is `ready_for_ca`. INV-0007 remains ready_for_ca; its current nonblocking R-DUP-02 issue is `awaiting_ca`, disposition NULL. No override Decision was persisted. Therefore the documented allowed-override path and its downstream export evidence have not passed. This is separate from the correct R-AMT-03 refusal. T-11 overall cannot be marked passed.

T-17 **PARTIAL — Excel import/reconciliation delivered; idempotence and JSON pending**: caption `gstr2b sharma 2026-11` inbox `sw_4fd83975389a0111b7867c7e9a970554` processed. Imported ST-0001 with 5 B2B lines; RC-0001 report delivered as `sw_b1afc64fedb24d59b6125503f3653fcc`. Counts: exact match 1, mismatch 0, purchase only 7, statement only 2, ambiguous 3. These reflect the current nonempty, edited test dataset; mismatch coverage is not demonstrated by this run. Disclaimer correctly distinguishes matching from ITC eligibility and tax-associated amounts from loss. Next: identical Excel re-upload, then JSON transport/import.

T-17 idempotence and JSON **PASS (mismatch class remains unexercised)**: duplicate Excel inbox `sw_03ee35243d67727cce26951cef25c168` processed; reply `sw_fe67051700384873af2c7b9068290c0e` says already imported as ST-0001, nothing changed. Database still contains one Excel statement, five lines, and one reconciliation run RC-0001. JSON inbox `sw_1c228ad049516dc4ceb19d1333704c5a` processed; ST-0002 contains five lines, stored bytes match source, unsupported `cdnr` section is explicitly reported as skipped. RC-0002 counts match RC-0001 exactly; report `sw_2aadecf1111445d89cf138c5464c0587` delivered. Telegram JSON transport works.

T-18 **PARTIAL — readiness/snapshot passed, approval/export pending**: readiness inbox `sw_ba1ede19be9a6a1a53eceec320945595` and snapshot inbox `sw_9ece7d48a93608b0bc95525d9687d249` processed. Snapshot SN-0001 delivered as `sw_ce225ed1a0164ce8ab4dcfb6c0a25a4a`, hash prefix `15b731be2b0c`. Counts: included 2, excluded 0 (duplicate was reopened), held 8, unassigned 1. Totals: taxable INR 11,400, CGST 100, SGST 100, IGST 1,332, total 12,932. Explicit PARTIAL label requires exact `ack 8 1`. Next: wrong-hash refusal while draft, then correct approval and export verification. No override export evidence is expected because allowed override failed earlier.

T-18 approval/export **PASS at backend/transport level; recipient visual confirmation pending**: wrong-hash inbox `sw_d500f0d214f2c5d639027202a501ffc5` processed; hash-specific refusal delivered as `sw_490257b1a94a487fad3cb217af911290`. Correct hash with `ack 8 1` inbox `sw_a748ca5c3fd3c680cfcc71990bff8856` processed; snapshot `exported`, partial true, acknowledged 8 held and 1 unassigned. Approval notice and two-file outbox delivered (`sw_ce2f990778604b298abe5b73145c6b01`, `sw_1b57bcc1e1ad440d81c4ba0785649b0f`). JSON artifact 13,040 bytes matches snapshot manifest exactly; XLSX artifact 10,844 bytes loads successfully, has Summary/Included/Lines/Checks/Decisions/Excluded/Held/Unassigned sheets, exactly two included invoices (INV-0001 and INV-0010), and no formula cells. Both artifact SHA-256 hashes match stored records. Allowed-override export coverage remains blocked by the earlier T-11 failure; no manual recipient confirmation of seeing both attachments has been supplied yet.

T-19 **SETUP COMPLETE — commands pending**: user created Telegram practice home and invited agent. Bound `af-practice-home` to `<id>` with explicit Telegram prefix. Next: CA sends `directory` and `readiness sharma 2026-11` in that group. User's generic "done" did not explicitly confirm both export attachments visually, so that T-18 observation remains pending.

T-18 recipient observation **FAIL / investigating**: user explicitly reports "no file visible". This supersedes the earlier pending visual check; backend generation/HTTP acceptance alone does not establish visible delivery. Switch message/attachment records show both export files and bridge-message mapping of album's first event `sw_1b57bcc1e1ad440d81c4ba0785649b0f` to Telegram chat `<telegram-chat-id>`, message 156. The second grouped event has no independent mapping (bridge album implementation records the first returned message reference). No matching attachment errors found in inspected logs. Retrying the same approved artifacts individually through Switch to distinguish album visibility from basic file delivery; recipient confirmation still required.

T-19 **PASS**: CA's directory and readiness commands both processed in practice home. Directory reply `sw_610a688d750344ec8cea7799519d331a` and aggregate readiness `sw_b937f5207aae47eb9bb3b30b817acbcc` delivered. Directory lists Sharma and Gupta; readiness reports included 2, excluded 0, held 8, unassigned 1, without invoice-line detail.

T-18 individual retry **PASS, original album visibility unresolved**: same approved artifacts resent individually through Switch (no bypass of the chat bridge). JSON event `sw_31fab37599b240c2b5cc74e7c889abe7` maps to Telegram `<telegram-chat-id>:168`; XLSX event `sw_e554978d65d447cdaa15f261ae226122` maps to `<telegram-chat-id>:169`. User explicitly confirms both files visible. Basic file delivery works; original grouped export visibility is not established and automatic grouped delivery cannot yet be claimed fully passed.

T-15 **PARTIAL — withholding/alert passed, cleanup recovery pending**: live CA-room members are `<ca-telegram-name>` and `<owner-telegram-name>`. Owner `status` inbox `sw_b76b4ac1fccc328a52ddaaab917b40a5` processed into an authorization refusal (not business data); CA `pending` inbox `sw_213b8637875e98a659ffe291990c9c28` processed into a queue reply. Both outbound messages are `withheld`, reason `live member check failed`, with no delivered event id (outbox ids `<id>` and `<id>`). Operations alerts delivered as `sw_9fba681aae5342ee886041406689b17e` and `sw_bed189618971460ca421e0a71d6d0785`, identifying only room and unexpected member, no invoice content. Next: remove owner, send a fresh CA pending command, verify fresh reply delivered while previous messages remain withheld.

T-15 cleanup recovery **FAIL**: user reports removing owner and sending fresh pending. Fresh pending inboxes `sw_ace571e2f4c1c62934398d19c26eca03` and `sw_ccd3599593cdc04ff4fb111ed595934d` processed, but Switch continues reporting both CA and <owner-telegram-name> as members. New replies remain withheld (ids `<id>`, `<id>`). Older withheld messages stay withheld as required. Source inspection: get_room_detail derives names from persisted Switch room client membership, and inspected Telegram handler handles new_chat_members and the bot's own membership but has no left_chat_member handling. This supports a stale-membership bridge limitation; actual Telegram member removal is user-reported, not independently inspected. Do not weaken the member check to recover. Next: use a fresh CA test group and explicitly bind it, preserving the old room/evidence.

CA recovery setup: user created `Telegram: af-ca-review-recovery` and invited agent. Live membership verified as only `<ca-telegram-name>`. Explicitly rebound existing logical `af-ca-review` binding from old room `<id>` to recovery room `<id>`. Old room and withheld messages preserved. During this run, avoid generic `bind-rooms --prefix "Telegram: "`, which would restore the old exact-name match. Fresh CA command in recovery room is pending.

CA recovery-room round trip **PASS**: `pending` inbox `sw_b416d652726f71318527a834f6c4a45e` processed; queue reply `sw_592e96dd0bd24547a0135da449b92b01` delivered in recovery group. This workaround restores CA messaging but does not fix stale membership of the old room.

T-22 **IN PROGRESS**: no queued/leased jobs before test. Verified worker launcher PID 21944 and child PID 12044, adapter launcher PID 56704 and child PID 56808. Stopping only worker processes whose exact command is this workspace's `.venv/Scripts/python.exe -m workers.runner`; adapter remains running. Next: owner uploads F02; verify durable intake without processing, then restart worker and verify one summary.

T-22 first attempt **INCONCLUSIVE**: by the time user uploaded F02, a different worker launcher PID 33568 / child PID 28868 was already running (created 2026-11-06 19:57:49 IST). F02 arrived 19:58:53 IST and processed immediately, so durable waiting while worker-down was not demonstrated. INV-0012 was created once, its summary delivered once (`sw_3b747b98227346c883b3726b7769e8ee`), and owner subsequently confirmed it. CA review RR-0014 delivered. Do not count this as successful queued-upload recovery. Retrying with unused F03 after a verified stop.

T-22 second attempt **BLOCKED BY TEST CONDITIONS / upload timeout**: F03 resulted in inbox `sw_b86089dbfaf2074e644e962121673342`, body "attachment not relayed: F03_clean_mixed_rates.pdf — download failed: Timed out", outcome ignored. No F03 document or extraction job exists. Separately another worker launcher PID 19348 / child PID 54044 started at 20:02:02 IST, after the verified stop; launcher parent PID 25356 is no longer available. Thus this attempt also does not establish worker-down queue recovery. Asked user whether another terminal/assistant/script starts workers. No changes made to live-member checks, and current workers left running while coordinating the retry.

Worker launcher investigation: no restart loop found in repository sources and no matching Python/PowerShell/cmd scheduled task referencing Assure Flow or workers.runner. Current worker's parent PID 25356 had exited; no matching available Windows process-creation audit event, so launch origin remains unknown. Two matching Python PIDs are venv launcher plus child, not two independent workers. New launch command wraps executable in quotes, so subsequent exact matching normalizes quotes and whitespace while restricting to this workspace's Python and module. Stopped that pair and observed for 10 seconds to check for immediate respawn.

T-22 queued-confirmation variant **PASS; original extraction-during-downtime scenario still incomplete**: F03 eventually arrived successfully as INV-0013 before the worker stop. With zero matching workers, owner confirmation inbox `sw_b5dfd697bfd34fd54df92ba2edf3f644` was observed `pending`, its process_inbox_event job `queued`, invoice needs_confirmation and r1 draft. Restarted worker launcher PID 33016. Same inbox event processed at 14:55:50 UTC, r1 confirmed, invoice ready_for_ca, exactly one check run and exactly one confirmation reply (`sw_b746230acf1d40f1892f38e93e66c667`), new RR-0015 delivered (`sw_80c3d240e0124451b711bb75f08e6725`), no active jobs remaining. This demonstrates durable event recovery without duplicate confirmation, but does not replace the guide's pending invoice-extraction test.

T-23 **IN PROGRESS / runtime interference observed**: restarted original adapter PIDs 56704/56808, new launcher 12700 connected at 14:57:01 UTC. It then logged repeated `switch.evicted`/reconnect events. Later process inventory shows a different launcher 54968/child 56376 created at 20:27:34/35 IST, and our original replacement is no longer listed. Origin of external relaunch is unknown. No pending inbox/jobs at checkpoint. Fresh owner status required to verify current service and no duplicate response; controlled single-process restart attribution is limited by relaunch interference.

T-23 fresh-message checkpoint **PASS with controlled-restart limitation above**: owner status inbox `sw_783250dc7fd963a221e1826daa2a8232` processed; exactly one outbox row shares its correlation id, delivered as `sw_b8287a82e4d74c3f886639dc18530a24`. No active jobs. Current adapter functions after observed restart/relaunch; historical replay has not been exhaustively counted.

T-24 **PARTIAL — outage verified, fresh post-restart message pending**: deliberately stopped only `switch-af-switch-1`. Health reported `switch server FAIL ConnectError`; user sent owner status while down. Before restart, latest owner inbox remained `sw_783250dc7fd963a221e1826daa2a8232` (pre-outage), demonstrating no new intake via a bypass. Container inspection confirmed `exited`, then restarted Switch. Health returned HTTP 200. At immediate post-start checkpoint no downtime message/reply had arrived yet; record any later catch-up behavior separately. Four withheld outbox messages remain expected isolation-test evidence.

T-24 recovery **PASS**: Switch and Telegram bridge reconnected. Two earlier status events caught up at 15:02:51 UTC (`sw_046984315b8191e626f1295486a7b769`, `sw_831c598a65baed6a6c86ed51688b4f2c`), each with exactly one correlated delivered response. Fresh post-restart status `sw_82f3a02c7cca5ca69e3f40530a7b6a74` processed at 15:04:36 UTC with exactly one reply `sw_29ee0959da9d4fdeb541002634bbafd4`. This shows no bypass while Switch was down and catch-up after it returns; delayed messages can be answered after restart.

T-25 **PASS, access restored**: temporarily revoked only <owner-telegram-name>'s Telegram ChatIdentity (`<id>`) and revoked 50 user execution grants. Owner status inbox `sw_6b6bf1bf86107e3bc1e760d43ff6110d` rejected as `unmapped_sender`; zero correlated outbox rows, hence no data reply. Restored that identity's revoked_at to NULL after verification. Previously revoked grants stay revoked; subsequent authorized commands obtain fresh contexts/grants. Fresh post-restoration command still required to verify full round trip.

Post-restoration owner access **PASS**: status `sw_daadc0fc2acfd160e9adf70b64f52f9e` processed, reply `sw_3cc8cc25da384fea801c98ef2db3a6f8` delivered. User confirms no additional Telegram accounts are available. Cross-shop live T-14, distinct stranger-account T-16, operator/developer T-20/T-21, and full multi-person purchase P-01–P-08 cannot be completed in this live run. Existing automated coverage must not be represented as those manual passes.

T-22 original invoice-upload recovery **PASS**: F04 inbox `sw_b5f3ed2cf5403110e9a79060c7aa74f2` observed pending with PDF attachment (2,674 bytes), one queued process_inbox_event job (`<id>`), zero F04 documents, and zero matching worker processes. Restarted worker launcher PID 1752. Inbox processed; exactly one F04 document and INV-0014 (`needs_confirmation`) created; stored hash matches original. Saved notice `sw_92461b192d3c4c0da4ab0baab5e44d05` and exactly one summary `sw_c203fe4eeeac462a92b96be3527f0294` delivered; no active jobs afterward. Guide wording qualification: while worker is stopped, the durable inbox holds the event; a business receipt/summary is not dispatched until worker resumes.

Current coverage (details and qualifications above):

| Cases | Coverage | Current status |
|---|---|---|
| T-01–T-10 | Owner workflow and CA handoff/replacement | Passed business checks; note wording and earlier non-Telegram CA routing qualifications |
| T-11 | CA decisions | Partial: include/exclude/clarify and excluded reopen passed; approved reopen and allowed override failed |
| T-12 | Stale decision refusal | Passed |
| T-13 | Owner never sees CA content | Routing observed during handoff; full standalone review pending |
| T-14 | Cross-shop live isolation | Unavailable: no third account |
| T-15 | Wrong member and cleanup | Withholding passed; cleanup failed due stale membership; fresh-room workaround passed |
| T-16 | Stranger ignored | Standalone stranger account unavailable; revoked-owner rejection and wrong-role denial verified separately |
| T-17 | GSTR-2B Excel/JSON/idempotence | Passed for current dataset; mismatch classification not exercised |
| T-18 | Snapshot, hash approval and files | Generation/hash refusal passed; individual delivery retries visible; original album visibility unresolved; override export blocked |
| T-19 | Practice home | Passed |
| T-20–T-21 | Operations and synthetic testing rooms | Unavailable: no separate operator/developer accounts |
| T-22 | Worker recovery | Passed queued-confirmation and original invoice-upload recovery; one summary after restart |
| T-23 | Adapter recovery | Fresh command delivered once; controlled restart/no replay evidence limited by external relaunch |
| T-24–T-25 | Switch outage and revocation | Passed; owner restored |
| P-01–P-08 | Full purchase workflow | Unavailable: additional independent staff accounts required |

Automated results above are supporting evidence only, not substitutes for the outstanding manual Telegram cases.

## Addendum, 6 November 2026 (added after the run): source of the unattributed processes

Added by: Claude (Opus 5.5), the Claude Code session involved. The account above is left as written. It was accurate when recorded, because the launcher was unknown to the tester at the time.

**Finding.** Another Claude Code session, working in this repository during the test, started the worker and adapter processes that T-22 and T-23 could not attribute. That session also stopped some of the tester's processes.

| Test report | That session's records |
|---|---|
| Worker launcher 33568 created 19:57:49 IST | Worker restarted in the background; `worker.started` logged 14:27:51 UTC, which is 19:57:51 IST (`data/logs/worker.log`, line 232) |
| Worker launcher 19348 started 20:02:02 IST | `Start-Process` returned PID 19348 with start time 20:02:02 (session transcript) |
| Adapter 12700 repeatedly logged `switch.evicted` | That session started a second adapter at about 14:57:07 UTC, connected at 14:57:09.54 (transcript). The tester's first eviction is at 14:57:09.51 (`data/logs/adapter-recovery.err.log`) |
| Adapter launcher 54968 created 20:27:34 IST; adapter 12700 no longer listed | That session stopped every adapter and worker, including 12700 and worker 33016, then started 54968 and a new worker (transcript; process list) |

**Records.**

- Session transcript, local to this machine and not in the repository: `C:\Users\Saurabh\.claude\projects\c--Users-Saurabh-Desktop-assureflow\<id>.jsonl`
- Logs, gitignored: `data/logs/worker.log`, `data/logs/adapter-recovery.err.log`
- That session's first detached logs were overwritten when it restarted at 14:57:36 UTC, so for those lines the transcript is the only record.

**Inference, not observed directly.** That session received exit notices for its background processes and read them as crashes. They were probably the tester's deliberate stops, but the notices carry no timestamps, so this can't be confirmed. The session's own explanation at the time, that its shells were closing, was wrong. So was its count of "three adapters and two workers": each process appears as a launcher and a child, so there were two adapters and one worker.

**Effect on results.**

- **T-23 stays unverified as a controlled restart.** This addendum does not change its status. It needs a rerun with one session owning the runtime.
- T-22's first attempt remains inconclusive, now with a known reason. Its second attempt also had a separate download timeout, which this finding does not explain.
- T-22's queued-confirmation and final upload recovery ran with zero matching workers confirmed before each restart, and they completed before or after the interference. Their results stand.
- The eviction loop was caused by two adapters sharing one connection, not by a Switch or Telegram fault.
