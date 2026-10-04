# Report: the watcher may do only what it needs, and tab lists keep private titles private (watcher-safety)

Date: 2026-10-04. Branch `watcher-safety`, cut from `main` at b8de841 (after the relay merged), merged into `main` as
8006d31.

## What the user asked

- **The design they approved:** wave 1, track 1B of "The app as an app"
  (`docs/superpowers/specs/2026-10-03-watcher-safety-design.md`). It closes the two safety gaps the investigation found:
  - a watcher page in Brave could start an agent in one of your own tabs, and save "Always allow" for a tool;
  - AI Home's tab list showed titles from your private windows and your other Brave profiles.
- **The answers it relies on:** agents use the Brave profile "the user is signed in on", and "Always allow stays in the
  app's Tools".
- **The instruction behind this build:** "continue what you havent able to finish here".

## What changes for you

- **The watcher may send only its list.** One table in the app names every message a page may send, and who may send
  it. The watcher may send 22 kinds. It can no longer start, stop, close or message an agent, save Always allow or
  change the Tools. It still can't hand over a tab, connect to Brave, talk or listen to the Brain, or skip a check.
  Anything else it sends is dropped, with no answer.
- **The watcher receives only its list.** It gets 18 kinds of message, trimmed. It never gets the tab list, sessions,
  pictures, agents' conversations, the Tools, the list of what uses your Brave, or any tab's id.
- **No lasting Always allow from Brave.** The watcher's Brain page offers **Allow once** and **Deny**, with the line
  "Always allow is in AI Home's Tools." AI Home, Mission Control and the chat keep all three buttons.
- **Show me asks by agent.** The bot-check notification's Show me brings forward only the tab where that agent's
  check waits. It can't name a tab.
- **AI Home lists one Brave profile.**
  - It lists the profile the watcher is in. Without the watcher, it lists the profile Brave used last, and says so.
  - Other profiles and private windows show only as a count: "4 more tabs in other profiles or private windows: not
    shown here."
  - If AI Browser can find neither profile, it lists only the AI's tabs, and says so.
  - The AI's tabs (agents', Claude Code's, handed ones) stay listed, wherever they are.
- **Only a listed tab** can be handed over, start a task, or be read by the Train form.
- **Nothing new asks.** No new connection to Brave, no new "Allow remote debugging?", no new extension permission.

## How it was built and checked

- **Test-first, 12 tasks, one commit each,** then one fix pass:
  1. 4fc712f: one table of who may send what (`MESSAGE_RULES`, `may_send`);
  2. 6e7501d: every message is checked against it first, by role;
  3. b1d28ae: Show me asks by agent id (`check_show`), and notes keep no tab id;
  4. 380b807: a watcher socket gets only `WATCHER_RECEIVES`, trimmed;
  5. 42b3c73: the watcher's tool card has Allow once and Deny;
  6. d0c565d: the tab list and the snapshot carry `tab_scope`;
  7. fec81de: the tab watch keeps each page's profile, the service workers and the default profile;
  8. 8ff83d5: AI Home lists one profile and counts the rest;
  9. de3edb5: the app gives BraveLink the watcher's id; a private window is never listed (proved in a real Chrome);
  10. 6b564a6: brain-delegation's `tell_confirm` and `tell_dismiss` are app-only rows;
  11. d1d2808: AI Home's lines for the profile and the count;
  12. fd42cfb: the README.
- **Mutation checks:** with the watcher filter turned off, the target-id test fails. With the server's connected-only
  scope check removed, AI Home's test catches the flash of "Your tabs aren't listed…".
- **My own review of the whole branch** (no subagents were allowed in that run): no critical or important findings,
  four minors (below).
- **A fresh review** (Opus, read-only, run by the main session): "With fixes (small)", nothing critical or important as
  graded. The main session re-graded two findings by their effect, and both were fixed test-first in one pass:
  - **R1, on every connect:** right after Allow, while the tab list was still starting, a page that loaded got "profile:
    none". AI Home showed "Your tabs aren't listed…" and "No web pages open in this profile." Now nothing is claimed
    or sent until the first list (2387d22). RED→GREEN: `test_while_brave_connects_the_tab_list_claims_no_profile` (the
    snapshot had `{"profile": "none", "elsewhere": 0}`) and `test_while_brave_connects_ai_home_claims_no_profile` (AI
    Home showed the line). The "send nothing" half was seen RED on its own.
  - **R2, a flaky merge-gate test:** a tab source replaced by brave mode kept sending its list, with Brave's scope.
    AI Home's scope test failed about 4 runs in 13. Now a replaced source is ignored (a03d6e7). RED→GREEN:
    `test_a_replaced_tab_source_is_no_longer_heard`. AI Home's tests after the branch's Chrome tests: 10 of 10 runs
    passed.
  - The reviewer agreed with my rulings 1-5 and 7-14, and partly with 6 (Part 2, built before 1A merged): checking
    against 1A's code would have caught Mission Control's "Your tabs". It agreed with deferred minors 3 and 4, and
    partly with 2, which became R1.
- **Whole suite** (the 9 skips are Windows-only tests):
  - main before the branch: 1239 passed, 9 skipped;
  - after the build: 1334 passed, 9 skipped;
  - after the fix pass: 1337 passed, 9 skipped;
  - main with wave A merged: 1511 passed, 9 skipped.

## The merge

- **Into main:** 8006d31.
- **The reconciliation with brain-delegation (977518c):**
  - `TELL_CARD_MESSAGES` went: the table decides;
  - the Brain's `from_watcher` now comes from `_role(ws)`. This branch's two guard tests were red on the merged tree and
    green after;
  - Mission Control's "Your tabs" now shows the same lines (7ff4f5d, `test_your_tabs_say_what_the_list_leaves_out`
    RED→GREEN).

## Rulings I made

Every decision taken on your behalf, in order, with what it costs if wrong:

- **Pre-flight:** Ruling: no relay check keeps browser_clients from the watcher at HEAD (_watcher_origins is read only
  in __init__, allow_origin, _mismatch, _socket, _handle); the Brain page's plain hello joins _sockets and gets
  browser_clients in its snapshot and every _clients_changed() broadcast. Task 4's for_watcher IS the fix; Task 4 Step 3
  deletes nothing; test_only_the_role_reads_the_watchers_origins already passes in Task 4 (kept as a guard);
  test_watcher_sockets_get_no_target_ids sets brave.relay.rows to one agent row and calls server._clients_changed(),
  asserting the worker and the Brain page get no browser_clients message and the Brain page's snapshot has no
  browser_clients key, while home gets both. browser_disconnect is an app-only row of MESSAGE_RULES; browser_clients is
  not in WATCHER_RECEIVES — from the main session's check against the merged relay — cost if wrong: none (a guard that
  passes early instead of a red test).
- **Pre-flight:** Ruling: Task 7's FakePort edits follow the relay's FakePort: FakePort(..., workers=(), default="C1");
  info() kept (context "C1"); infos() = pages' info() + workers' _worker_info(); the getBrowserContexts branch lives in
  _reply (an error when self.default is None, else {"browserContextIds": ["C2"], "defaultBrowserContextId":
  self.default}); no `continue` insertion in _handler; _tell_all is built on emit() (no _live); Task 8 Step 2's "C0"
  reads "C1"; Task 7 Step 4 runs tests/test_cdprelay.py tests/test_bravelink.py tests/test_engine.py — the plan's "C0"
  would break the relay's tests (they assert "C1") — cost if wrong: none.
- **Pre-flight:** Ruling: on "lost", BraveLink's _drop_watch sends the empty list before the server's browser message,
  so Task 6's _tab_scope() returns None unless getattr(self.tabs, "state", "connected") == "connected" (tested in Task
  6), and Task 11 gains a step copying the relay's order (brave.state = "lost"; brave.changed();
  brave.set_state("lost")) that shows no source line — otherwise AI Home flashes "Your tabs aren't listed…" when Brave
  is lost — cost if wrong: the snapshot's tab_scope is null while Brave isn't connected (the page shows no scope lines
  then anyway, Review Focus 1).
- **Pre-flight:** Ruling: Task 9's test_the_watchers_profile_is_found_from_its_worker asserts on watcher.brave (the
  fixture's connected BraveLink, now given watcher_id=app.extension_id in Step 1) instead of building a second BraveLink
  (a second relay and upstream) on the fixture's Chrome — cost if wrong: none.
- **Pre-flight:** Ruling: the plan's tell_confirm/tell_dismiss rows (Task 10) are followed; the main session reconciles
  1A and 1B at merge — cost if wrong: two table rows that no handler serves, if 1A had named its messages differently
  (Task 10's ruling)
- **Part 2:** Ruling: Tasks 10-12 are done on this branch without merging main — brain-delegation isn't on main and the
  brief forbids merging; the main session said it reconciles 1A and 1B at merge, and asked for a Task 11 step — cost if
  wrong: merge conflicts in tablist.js, home.js, tests/test_home.py and README.md for the main session (each side adds
  lines).
- **Task 1:** Ruling: the Rule/MESSAGE_RULES/may_send block sits after the constants block (after YOU), not between
  BRAVE_MESSAGES and CHECK_SITE — keeps the constants together and the table beside them; same module, same names — cost
  if wrong: none.
- **Task 2:** Ruling: test_the_watcher_cannot_save_always_allow's last check reads json.loads(tools.json)["always"] ==
  [] instead of "mcp__clickup__create_task" not in tools.json's text — tools.json legitimately lists that tool under
  "known" (the tools Claude Code reported at the agent's start), so the plan's text check failed for a reason unrelated
  to the safety property; the test still saw RED first on tools.always() holding the tool — cost if wrong: none.
- **Task 9:** Ruling: test_a_private_window_is_never_listed_in_a_throwaway_chrome launches with
  extra_args=("--incognito",) and points the private window's start page at privacy.html over the test's own CDP
  connection, instead of passing the page's address in extra_args — headless Chrome exits at once (code 13, "Multiple
  targets are not supported in headless mode") when given two start addresses, and launch() appends about:blank after
  extra_args; probed in headless Chrome: the start page is about:blank in a context of its own, defaultBrowserContextId
  is the regular profile's, and a context-less createTarget lands there (the spec's Decision 8 facts hold) — cost if
  wrong: none (the test still proves a private page is never listed and is counted).
- **Task 10:** Ruling: Steps 3.2 and 3.3 have nothing to act on here — brain-delegation isn't merged into this branch
  (Part 2 ruling), so there is no from_watcher flag for tell and no origin test of its own; the rows wait for its
  handlers, and the main session sets from_watcher to self._role(ws) == "watcher" and drops any origin test of 1A's at
  merge (until then a tell_confirm/tell_dismiss from AI Home reaches no branch in _handle and does nothing, as before) —
  cost if wrong: if 1A names the messages differently, two dead rows and the table test's copy to rename.
- **Task 12:** Ruling: the bench (uv run ai-browser bench) is not run on this branch — the brief asked for the whole
  suite only; the bench is CPU-heavy Chromium-in-Docker timing work that would load a machine where two other builders
  run timing-sensitive suites (one Chrome-launch flake already seen at load ~10), and this branch changes no engine code
  (only app/server.py, app/tabs.py, app/bravelink.py, app/run.py and page scripts), which is what the bench measures —
  cost if wrong: a bench regression from this branch would show only in the main session's run after merge.
- **Final:** Ruling: rights stay per origin, so the watcher's worker may send the Brain page's types and the Brain page
  the worker's (the reports still count only from the socket that said hello as the watcher) — stands: the spec's
  Decision 1 (one shared origin; the view in hello is the page's own claim) — cost if wrong: none beyond the 22 listed
  types.
- **Final:** Ruling: the final review is a self-review — this run's brief forbids dispatching subagents — cost if wrong:
  the branch gets no fresh-context review before merge; the main session decides whether to run one.
- **Final:** Ruling: superpowers:finishing-a-development-branch is not used and the plan's workspace is kept — the brief
  forbids merging and pushing (the main session merges) and puts suite.txt in the workspace — cost if wrong: a
  git-ignored folder to delete by hand.
- **Final:** Ruling: a malformed field in an allowed type can still close that page's socket — stands: it predates this
  branch, only pages that passed the origin check can send, and the page reconnects — cost if wrong: one page's socket
  closes until it reconnects.
- **Final:** Ruling: group_tab sends a handed tab's URL to the watcher, which with watchers in two profiles may be the
  other one — stands: multi-profile watchers are wave C's (browser-profile-choice) — cost if wrong: one URL reaches the
  watcher of another profile of the same user.
- **Final:** Ruling: the watcher's profile is remembered for the whole connection, even after its windows close —
  stands: spec Decision 7 — cost if wrong: a stale profile until the next connect.
- **Final:** Ruling: the 1A reconciliation (from_watcher = self._role(ws) == "watcher", drop TELL_CARD_MESSAGES) and
  1A's Mission Control "Your tabs" reading tab_scope are done by the main session at merge, test-first — cost if wrong:
  none (the guard tests flag a leftover).

## Deferred minors

- **Minor 1:** AI Browser mode — TabWatch's on_change now also fires when any service worker (a website's too) starts or
  stops, and AI Browser's TabWatch has no dedup, so the server resends an unchanged tab list (AI Home re-renders in
  place; nothing visible); fix later: TabWatch._tell compares the rows it last sent, or only BraveLink listens to
  workers. (re-worded by the fresh review: see the last one)
- **Minor 2:** first connect only — if an agent's tab grant reaches BraveLink before its tab watch has started (_watch
  None, nothing sent yet), _changed() sends an empty list with scope {"profile": "none"} while the state is already
  "connected", so AI Home can show "Your tabs aren't listed…" and "No web pages open in this profile." for the
  milliseconds until the watch's first list; fix later: _changed() doesn't call back while the relay is connected and
  the watch is still starting. (re-graded as R1 and fixed, see above)
- **Minor 3:** tablist.js's header comment still says "every web tab of the user's Brave" (now one profile's); left
  unchanged so 1A's edits to that file merge with fewer conflict lines; fix at merge.
- **Minor 4:** TabWatch reads Target.getBrowserContexts every refresh round (1.5 s) in AI Browser mode too, where
  nothing reads default_context: one extra browser-level call per round; fix later: read it only when asked for
  (BraveLink passes a flag).
- **Minor 5:** home.js:210-212 — after a profile switch, `handing` keeps a stale "Starts in your tab: <title>", and
  Start then fails with "it is closed, or an agent works in it"; fix later: clear it when its target leaves `tabs`.
- **Minor 6:** no test covers a "Brain" row in another profile (a mutation of _shown survived); fix later: a FakePort
  test with a brain-marked tab outside the agents' context.
- **Minor 7:** _role answers "app" for anything not from the watcher's origin; it should fail closed once wave B maps a
  cookie to "app" — for wave B's pre-flight.
- **Minor 8:** (my minor 1, re-worded by the reviewer) AI Browser mode resends an unchanged tab list whenever any
  service worker starts or stops, and each resend redraws the tab list and rebuilds the Train form's page picker
  ("nothing visible" was optimistic); wave B retires that mode.

## Your hand check (in your own Brave, after you restart the app)

Nobody has checked these in a real Brave yet:

1. With the watcher loaded, open a web tab in a second Brave profile and one in a private window. AI Home's Tabs list
   shows only the watcher's profile, and one line counts the other two.
2. Give an agent a task that needs a tool. The watcher's Brain page offers **Allow once** and **Deny**, with "Always
   allow is in AI Home's Tools." AI Home's card still has all three.
3. On a bot-check page, the notification's **Show me** brings the agent's tab forward, and **Continue** lets it carry
   on.
4. Quit Brave and start it again, then click Allow. AI Home never shows "Your tabs aren't listed…" while it connects.
5. Brave asks "Allow remote debugging?" no more often than before: this branch opens no connection of its own.
