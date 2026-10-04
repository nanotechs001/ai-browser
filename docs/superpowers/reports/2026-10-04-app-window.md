# Report: AI Browser opens as an app window, with no browser look (app-window)

Date: 2026-10-04. Branch `app-window`, cut from `main` at d8ee359 (after wave A and allow-once merged), merged into
`main` as 607396d and pushed.

## What the user asked

- **Their design answer:** "App window, no browser look".
- **Their words, the same day:** "Then on the app it is still using the browser UI i want it to make it look like an APP
  not browser that have tabs or i can see the url bar or like that i want it to be an actual app".
- **The choices behind the spec** (`docs/superpowers/specs/2026-10-03-app-window-design.md`, wave B): Google Chrome
  draws the window on the Mac (Microsoft Edge on Windows), changeable in Settings; AI Browser's own Chrome: "drop it";
  closing the window stops the app; the `ai` keyword moves to Brave.

## What changes for you

- **One plain window.** `uv run ai-browser app` opens AI Home in a window with a title bar only: no tabs and no address
  bar. On this Mac Google Chrome draws it, because Brave is your everyday browser, so the Dock shows Chrome while AI
  Browser is open.
- **No question and no bar for the window.** It runs on a profile of its own (`~/.ai-browser/app/window/<browser>/`)
  with no debugging port. Nothing drives it, and no agent browses there. Brave still asks once for the app's own
  connection, as before.
- **Nothing to load by hand.** AI Browser's own Chrome, its extension, the side panel, ⌘⇧Y and the toolbar badge are
  gone. The window's title counts the agents at work: "(2) AI Home".
- **Only the window gets in.** It starts with a one-time code, which the app swaps for a cookie only that window holds.
  The same address typed into Brave shows "AI Browser's pages open only in its own window" (the setup page holds no
  secret, and opens anywhere). Every route checks the Host header, and every answer carries a strict content policy.
- **Settings** (beside Mission Control): which browser draws the window (Auto, Google Chrome, Brave, and Microsoft Edge
  on Windows). A browser that isn't installed is greyed out. A change applies at the next start, and `--window brave`
  picks one for a single run.
- **Remembered by the app, not the browser:** the model you pick and Voice, in every page and across restarts
  (`~/.ai-browser/settings.json`). The port is remembered too, so the microphone grant survives a restart.
- **Links:** a website opens in your Brave, never in the window.
- **The `ai` keyword lives in Brave now.** `ai`, a space and a task in Brave's address bar starts an agent through the
  watcher (version 0.2.0), and Brave says "Started 4 · Fix the footer. See it in AI Browser's window."
- **Closing the window** ends the app about 5 s later, with its agents. Ctrl-C in the terminal closes the window.
- **Since then, popups became tabs.** This wave opened Mission Control, Settings, the setup steps and an agent's live
  view as small windows of their own. The tab menu (merged as 7123816) shows them as tabs in the same window instead.

## How it was built and checked

- **Test-first, 24 tasks, one commit each.** Each test was seen failing for its stated reason, then passing:
  0. 6c90479: the earlier waves' names pinned; extension IDs get a module of their own;
  1. 98c6872: which browser draws the window, and its exact command line;
  2. 48a6fd3: `settings.json`: one reader, one writer and a typed view;
  3. 140096b: the window starts on its own profile, hands off, and closes only what it started;
  4. b38e5a3: the tab list hides AI Browser's own address, not its extension;
  5. 2c1df80: the pages move to `app/ui` (a `git mv`); the watcher shares them from there;
  6. 26057a8: the one-time code, the window's cookie, and the pages over http;
  7. b670058: the setup page holds no secret, shows Brave's steps only, and runs no inline code;
  8. e1d1de4: an exact Host on every route, and a strict content policy and headers on every answer;
  9. f54a685: window sockets need the cookie and our exact Origin and Host; roles are stored when a socket opens;
  10. ec36ba0: the model, Voice and the window's browser are the app's settings; the port is remembered;
  11. 6a35304: a website link opens in your browser, never in the window;
  12. 5b81046: the `ai` keyword moves to Brave's address bar, through the watcher;
  13. ea3d232: the pages run over http with the window's cookie; the model and Voice come from the app;
  14. 9056f07: our pages open as small windows, websites in your browser; a static guard for both;
  15. 2496ee7: the Settings page;
  16. 37189a1: the window's title counts working agents; the keyword's hint names Brave;
  17. 52f3b6d: `ai-browser app` opens its window and ends when the last one closes;
  18. b4e5ca2: the server's AI Browser mode retires: the token is the watcher's only way in;
  19. ed46cb6: the engine's AI Browser mode retires; an agent never opens AI Browser's own pages;
  20. f400e33: one prompt and one browser for every agent; AI Browser mode's lines go;
  21. 91272b2: AI Browser's own Chrome and extension are deleted; the watcher's tests keep the pipe;
  22. 99e4ce8: `doctor --setup` checks the browser that draws the window;
  23. 799b309: the README.
- **Two regressions, caught and fixed in later commits** (each seen failing first):
  - Task 17 dropped `AIB_APP_BROWSER=app` from the test fixture, which broke test_chrome's guard; Task 19 fixed it;
  - Task 12's keyword reply used `int(id[1:])`, which brain-delegation's guard forbids; Task 20 uses `agent_number`.
- **My own review of the whole branch** (no subagents allowed): nothing critical or important, six minors.
- **A fresh review** (Opus, run by the main session): "Ready to merge", with four minors, so there was no fix pass.
  - It agreed with every ruling, and partly with three:
    - review 13a (`openWindow` re-navigating a window that shows another of our pages) gave my minor 3;
    - "browsers.py only through window.pick" was too narrow: `_agents_browser` and `AppWindow` call it too;
    - the no-bench ruling.
  - It agreed that my six minors are minor.
  - It declined to judge: the spec's hand checks; closing by socket count when a renderer crashes or Memory Saver
    discards a hidden window; macOS link routing when the window's browser is your default browser; ⌘N, ⌘T and the menu
    bar; the accepted risks (the code on the command line, a local program forging the Origin); the keyword's doubled
    spaces and its first seconds; the CLI's exit code 130.
- **Whole suite** (the skips: 6 Windows-only tests, 7 side-panel tests kept for the side chat, and 2 that need an
  environment variable):
  - main before the branch (d8ee359): 1519 passed, 9 skipped;
  - after the build (799b309): 1561 passed, 15 skipped, none failed. test_approval_mode, with a throwaway Chrome and a
    throwaway Brave, still counts one question for the app, two agents and a session. The bench wasn't run (the Task 23
    ruling).

## The merge

- **Into main:** 607396d, pushed.
- **Since then:** the tab menu (7123816) turned the popups into tabs in one window (the spec's amendment of 2026-10-04).

## Rulings I made

Every decision taken on your behalf, in order, with what it costs if wrong:

- **Pre-flight:** Ruling: review 1 — the RETIRED_BROWSER test uses startswith (the engine appends its ⏱ line) — cost if
  wrong: none.
- **Pre-flight:** Ruling: review 2 — test_portable's pinned PIPE_FIXTURES shrinks with conftest, ending at {"watcher"} —
  cost if wrong: none.
- **Pre-flight:** Ruling: review 3 — Task 17 deletes test_cli's stale test_app_takes_the_browser_choice — cost if wrong:
  none.
- **Pre-flight:** Ruling: review 4 — test_mission's two endswith("/mission.html") become "/mission" in Task 13 — cost if
  wrong: none.
- **Pre-flight:** Ruling: review 5 — the _watcher_origins readers guard follows Tasks 9 and 18 (_socket_kind, then
  allow_watcher) — cost if wrong: none.
- **Pre-flight:** Ruling: review 6 — the relay's self.port = 0 becomes None; port and headers are set right after bind,
  relay.port after start — cost if wrong: none.
- **Pre-flight:** Ruling: review 7 — the wiring test keeps two agents' distinct tokens, the exact link.json and the
  Disconnect line — cost if wrong: none.
- **Pre-flight:** Ruling: review 8 — BraveLink's TabWatch("", "", cdp=…) becomes TabWatch("",
  hidden_origin=self.app_origin, cdp=…) — cost if wrong: none.
- **Pre-flight:** Ruling: review 9 — Task 8 drops the relay-Host note and test_cdprelay.py (that test runs on
  serve_relay) — cost if wrong: none.
- **Pre-flight:** Ruling: review 10 — setup.html's #switch section is copied from HEAD exactly — cost if wrong: none.
- **Pre-flight:** Ruling: review 11 — HEAD's write_link (optional cdp/browser_dir) is kept — cost if wrong: none.
- **Pre-flight:** Ruling: review 12 — home.html and mission.html link icon.png — cost if wrong: one more request per
  page.
- **Pre-flight:** Ruling: review 13a — openWindow also re-navigates a named window showing another page of ours (spec:
  only about:blank) — cost if wrong: a reload of that window.
- **Pre-flight:** Ruling: review 13b — the real-window test passes the URL once and asserts window_count == 1 (seen) —
  cost if wrong: none.
- **Pre-flight:** Ruling: review 14 — two of Task 14's static guards pass before Step 3; its RED is the other five —
  cost if wrong: none.
- **Pre-flight:** Ruling: review 15 — Task 23 also renames README's "the extension's config.json" to the watcher's —
  cost if wrong: none.
- **Pre-flight:** Ruling: _role fails closed: no stored role reads "none" (may_send refuses it) and _write trims every
  non-"app" socket to the watcher's part; a new test pins it — cost if wrong: none.
- **Pre-flight:** Ruling: run.py keeps LEFT_ASKING; its test now ends the app the window's way (the window's socket
  closes) and keeps its assertions — cost if wrong: none.
- **Pre-flight:** Ruling: test_approval_mode runs after Tasks 8 and 17 and in the final suite — cost if wrong: none.
- **Pre-flight:** Ruling: Tasks 5, 13, 14, 21 grep every test for the old page addresses and fix them there — cost if
  wrong: none.
- **Pre-flight:** Ruling: browsers.py is used only through window.pick, unchanged — cost if wrong: none.
- **Task 0:** Ruling: test_appbrowser's three other extension-ID imports also move to ai_browser.extension_id — cost if
  wrong: none.
- **Task 4:** Ruling: wave A's context test moves to the throwaway pages fixture without its two
  worker_contexts(extension) lines (spec) — cost if wrong: none.
- **Task 6:** Ruling: attach_brave sets relay.port = self.port or 0 (the server's port is None before start; the relay's
  stays an int) — cost if wrong: none.
- **Task 7:** Ruling: setup.css keeps the old <style> rules without their page indent — cost if wrong: none.
- **Task 7:** Ruling: test_the_watcher_feeds_the_brain_and_pages_see_it expects /setup/status == {"watcher": True}
  ("installed" goes) — cost if wrong: none.
- **Task 12:** Ruling: the keyword's watcher test polls notifications.getAll() (the note is written before the
  notification; one read came too early) — cost if wrong: none.
- **Task 13:** Ruling: wave A's late-page test opens stack["url"] + "/home" (no extension any more) — cost if wrong:
  none.
- **Task 13:** Ruling: two brain-delegation talk tests drop server.tabs._callbacks.clear() (the stack has no AI Browser
  TabWatch) — cost if wrong: none.
- **Task 14:** Ruling: nav.js's comment names _blank unquoted (the plan's own guard caught the quoted one) — cost if
  wrong: none.
- **Task 17:** Ruling: test_app_run keeps the watcher's-id and hashed-path tests on SocketWindow — cost if wrong: none.
- **Task 17:** Ruling: three AI Browser-Chrome tests go (profile in use, stale install record, extension folder named) —
  cost if wrong: none.
- **Task 18:** Ruling: three sockets move by hand beyond the plan's regex — cost if wrong: none.
- **Task 19:** Ruling: the two tests moved from test_appmode were green before Step 3 (existing behaviour, moved) — cost
  if wrong: none.
- **Task 19:** Ruling: test_chrome's guard asserted AIB_APP_BROWSER == "app" (Task 17 broke it, seen RED); it now
  expects it absent, and conftest deletes it — cost if wrong: none.
- **Task 19:** Ruling: stale AI Browser-mode comments in engine.py/browser.py reworded — cost if wrong: none.
- **Task 20:** Ruling: _in_users_browser goes entirely (cards' tab_hint always computed); brain-delegation's AI
  Browser-mode test lines go — cost if wrong: none.
- **Task 20:** Ruling: Task 12's keyword reply used int(agent_id[1:]), which brain-delegation's guard forbids (RED since
  Task 12); it now uses agent_number — cost if wrong: none.
- **Task 22:** Ruling: the doctor's subprocess test sets HOME to a temp folder, so detection never reads the user's
  LaunchServices file — cost if wrong: none.
- **Task 23:** Ruling: the README keeps the merged "Your browser" bullet, and its "What sites can see" table loses the
  AI Browser row (that Chrome is gone) — cost if wrong: none.
- **Task 23:** Ruling: no bench (forbidden here); the whole suite runs once after the final review, as ordered — cost if
  wrong: a sandbox speed regression goes unmeasured.
- **Final:** Ruling: the window's look, Dock icon, mic prompt, click-free Voice and Edge are the spec's hand checks,
  untestable here — cost if wrong: a regression shows only by hand.
- **Final:** Ruling: the workspace is kept for your fresh reviewer — cost if wrong: a git-ignored folder to delete after
  merge.

## Deferred minors

- **Mine**, from my own review:
  - browser.url_problem's app-origin test doesn't canonicalize hosts as the relay does (backslashes, 127.1); the relay's
    check and the cookie still hold.
  - _keyword_workflow cuts the user's text by the lowercased name's length (a name whose lower() changes length would
    cut wrong).
  - openWindow compares pathname+hash, so a path with a query re-navigates a window already showing it.
  - stale comments: agents.py's env comment names AIB_APP_PROFILE; home.js renderTabs' "AI Browser mode" owner fallback;
    bridge.py's "panel events".
  - README's Tools and Bot checks sections still mention the chat beside the tab (wave D's side chat).
  - engine._start_chrome keeps a redundant `route = None` before route = self._route().
- **The fresh review's:**
  1. Ctrl-C during the window's launch call (a 5 to 30 ms gap) can leave the window running: `close()` sees
     `process=None` while `launch()` is still in its thread. Fix later: wait for the shielded launch before `close()`.
  2. A second "Show me" opened a second live-view window. The tab menu has since fixed this: one live tab per agent.
  3. Stale wording: server.py:1123-1125 (the `_role` docstring), :541 and :551; qa/page.py:73-76; agents.py:160 and
     :171; README.md:424 ("in the chat panel").
  4. On Windows a hung `taskkill` delays the kill to about 20 s, with no error.

## Until the side chat returns

- **What went with this wave:** AI Browser's chat beside the page (its side panel, and ⌘⇧Y).
- **Where it comes back:** as the native app's floating chat (`docs/superpowers/specs/2026-10-04-native-app-design.md`,
  part c): a small window that stays on top beside Brave, ⌥Space from anywhere, the Brain's talk, New task, messages to
  an open agent, and "This page".
- **Meanwhile:**
  - each agent's chat is in AI Home's drawer and in Mission Control;
  - tasks start from AI Home, from Mission Control, or with `ai` and a space in Brave's address bar. The native app's
    New task later replaces the keyword, and the watcher retires;
  - the 7 side-panel tests are skipped, not deleted;
  - the README's Tools and Bot checks sections still mention the chat beside the tab (a deferred minor).

## Your hand check

On the Mac, after you restart the app. Nobody has done these yet:

1. `uv run ai-browser app`: one window with a title bar only; no "Allow remote debugging?" for the window and no
   automation bar; the Dock shows Google Chrome.
2. Mission Control and Settings open as tabs in the same window (the spec's small windows, since the tab menu).
3. The first talk in Mission Control shows Chrome's microphone prompt (and macOS's, once). After a restart, no prompt.
4. With Voice on, Mission Control speaks an update right after start, with no click.
5. Closing the window ends the app within about 5 s, and no Chrome is left in the Dock.
6. In Brave, `ai check the shop` starts an agent, and the notification appears.
7. Typing `http://127.0.0.1:<port>/home` in Brave shows the "open only in its own window" page.
8. Ctrl-C in the terminal closes the window, and the next start shows no "Restore pages?".

On the Windows laptop:

- Edge draws the window on its first run with a fresh profile, with no welcome page;
- closing it ends the app;
- Ctrl-C in the terminal closes it, and the next start shows no "Restore pages?";
- a link clicked in another app (Mail, Teams) opens in the everyday browser, not in the window.
