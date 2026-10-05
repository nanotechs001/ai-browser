# Report: AI Browser as an app of its own (native app, part a: the Electron shell)

Date: 2026-10-05. Branch `native-a`, cut from `main` at b9d4a81 (after the tab menu and AI accounts merged), merged
into `main` as bfe61a0.

## What the user asked

- **The request:** "then in app I want it built in, no need to install the extensions it is such a hassle find a way
  to build it natively we can switch to standalone app if necessary".
- **Their answers:** "Keep Brave, app does it all (Recommended)", "Floating window beside Brave (Recommended)" and
  "Electron (Recommended)".
- **On the design:** "all good". **On the plan:** "Yes, build it next (Recommended)".
- **Scope** (`docs/superpowers/specs/2026-10-04-native-app-design.md`, part a): the setup download, the app itself
  (its name, icon, Dock and menu-bar icon, the main window with the tab menu, closing versus Quit), the locked-down
  windows, the shortcut, notifications, and Chrome's app mode as the fallback. Part b (the extension's jobs) and part
  c (the floating chat) come next.

## What changes for you

- **Setting it up, once:** `uv run ai-browser doctor --setup` shows what it would download: Electron 44.5.1, its size
  (130 MB on a Mac, 158 MB on Windows) and its address on GitHub. Nothing is downloaded until you type `y`.
  - The zip is checked against Electron's `SHASUMS256.txt`. A cut download, a mismatch or Ctrl-C keeps nothing, and
    Settings and AI Home say what went wrong.
  - It builds "AI Browser.app" in `~/.ai-browser/desktop/` (an "AI Browser" folder on Windows), signed on your Mac,
    ad hoc. Its Node fuses are turned off. Running it needs no Node.js.
- **`uv run ai-browser app`** starts the engine as before, then the app: its own Dock icon, a menu-bar icon (Open AI
  Browser, Show chat, which is greyed until part c, and Quit) and the tab menu in its window.
  - **Closing the window hides it.** Agents keep working, and the shortcut, the Dock or the menu-bar icon bring it
    back.
  - **Quit** (the menu-bar icon or ⌘Q) stops the app and every agent, as Ctrl-C does. The app quits if the engine
    goes away.
  - Until it is set up, with `--window`, or when the app can't start, a browser window opens as before, and the
    reason is kept for Settings.
  - After a `git pull` that changes the app's own files, it is rebuilt before it starts, with no download.
- **The shortcut:** ⌥Space (Alt+Space on Windows) shows and hides the window. Settings → **AI Browser app** offers
  ⌥⇧Space, ⌃⇧Space and Off. A shortcut another app holds is said there, and the one before stays. Until it has been
  pressed once, Settings asks you to press it.
- **Notifications** in fixed words, never a message's or a page's text: "An agent is waiting for you", "A bot check
  on example.com", "The Brain has 2 new notes". A click opens AI Home at the agent's row, or brings the agent's tab
  forward in Brave. While the app runs, Brave's watcher doesn't show them too.
- **Locked down:** only AI Browser's own pages load, and a website link opens in Brave. Pages get the microphone and
  the clipboard's Copy, nothing else. The app has no debugging port and no DevTools, and refuses a debugging switch.
- **AI Home** offers the setup while the app isn't set up (**Not now** hides it). The microphone's steps name "AI
  Browser" inside the app.

## How it was built and checked

- **Test-first, 12 tasks, one commit each:**
  1. 3d7e69f: the pinned Electron 44.5.1 (each zip's name, size and SHA-256) and where the app lives;
  2. a2d785b: the download, checked against `SHASUMS256.txt`, or nothing kept;
  3. 3edd4fc: unpacking with its links, and the Node fuses turned off;
  4. 3fe60fa: the app's rules (`policy.js`) and its line (`line.js`), tested under Node.js;
  5. 9f4ffc9: the Electron app: a locked-down window, the menu-bar icon, the shortcut, notifications;
  6. 445102a: building AI Browser.app (and Windows' folder), signed ad hoc;
  7. 6be0011: `doctor --setup` offers the app and builds it after a typed yes;
  8. 5a473e7: starting it on a private line: stdin on Windows, LaunchServices and a socket on macOS;
  9. 66e4a8a: the engine's side: the shortcut setting, the app's state in Settings, notifications and clicks;
  10. 69489e1: `ai-browser app` opens the app, falls back to a browser window, and ends on Quit;
  11. 9ab657a: the pages: Settings → AI Browser app, AI Home's offer, a click's focus, the microphone's name;
  12. f835e2f: the README.
- **Nothing was downloaded** in the build, and the real `codesign`, `sips` and `open` never ran: tests use a
  miniature Electron zip and stand-in tools. The tests that drive a real Electron run only with `AIB_TEST_ELECTRON`.
- **My own review of the whole branch** (no subagents were allowed): two findings graded Important, both fixed
  test-first:
  - **3d056de:** on a Mac, an error while making the private line (for example "AF_UNIX path too long" under a long
    TMPDIR) crashed `ai-browser app`. Now it falls back to the browser window and keeps the reason. RED→GREEN:
    `test_a_line_that_cant_be_made_is_said_plainly_and_leaves_nothing`;
  - **569ef32:** `app.setToastActivatorCLSID` was called unguarded on Windows. If Electron 44 lacks it, every Windows
    start would end. Now it runs only where it exists. RED→GREEN:
    `test_a_windows_api_this_electron_may_lack_never_stops_the_start`.
- **A fresh review** (Opus, read-only, run by the main session): "Ready to merge". The download, the fuses, the
  lockdown, the debugging guard and the private line are sound, and all five Review Focus items hold. Two of its
  minors were raised to Important by the main session and fixed test-first in one pass:
  - **F1, the start code was made before a rebuild** (0dfed9f). After a pull, the rebuild (a copy, `sips`, the fuses
    and `codesign`) could outlast the code's 60 s, and the window said the start link had expired. Now the address
    is made once the app is up, right before its start. RED→GREEN: `test_the_start_code_is_made_after_a_slow_rebuild`
    (403 before, 303 after);
  - **F2, a "Start AI Browser from a terminal" box blocked later starts** (150ce6d). An app the engine started now
    quits quietly when the engine goes, with no box and no window. A double-click start lets go of the
    single-instance lock before its box. When `open` ends with 0 before the app connects, the saved reason now says it
    closed as it started, not "open ended with 0". main.js's flow now runs under a stand-in Electron
    (`tests/electron_stub.js`). RED→GREEN: `test_without_an_engine_only_a_double_click_hears_how_to_start`,
    `test_a_double_click_start_lets_go_of_the_lock_before_it_says_how`,
    `test_an_engine_gone_before_its_start_quits_quietly`, `test_once_the_start_has_come_there_is_never_a_box` and
    `test_a_copy_that_closes_as_it_starts_falls_back_with_the_plain_reason`.
    `test_the_engine_gone_after_the_start_quits_the_app` guards Review Focus 4 (green before and after).
  - **Its verdicts:** it agreed with every ruling. `UNPACKAGED` is sound: only Electron's default app defines
    `process.defaultApp`, the guard runs before Chromium's DevTools server, and the fuses cover the environment,
    `--inspect*` and SIGUSR1. It accepted the Ctrl-C-during-start ruling with a larger cost (that became F2), and the
    Windows stdin ruling, gated on the Windows hand checks. It agreed with my four deferred minors.
  - **Its other findings** are deferred minors (below), and its rulings are in the list below.
- **Whole suite:**
  - after the self-review fixes: 1758 passed, 18 skipped (21 min 51 s);
  - after the F1 and F2 pass: 1764 passed, 18 skipped, 1 failed (25 min 6 s). The failure,
    `test_the_brain_draws_at_most_30_frames_a_second` (67 frames in its 2 s window, limit 62), is a wall-clock timing
    test in files this branch doesn't touch. It passed 3 of 3 times alone;
  - skipped: 3 real-Electron tests (no `AIB_TEST_ELECTRON`), 7 Windows-only, 6 retired side-panel, 2 opt-in.

## The merge and your setup run

- **Into main:** bfe61a0, pushed by the main session.
- **Your real setup run:** `doctor --setup` downloaded the zip, checked it against `SHASUMS256.txt`, said "all good",
  and built AI Browser.app. The app runs. The main session checked it has no debugging switch and no listening
  ports, and that Brave has one connection.

## Rulings I made

Every decision taken on your behalf, in order, with what it costs if wrong:

- **Setup:** Ruling: the ledger is sdd-workspace's .superpowers/sdd/2026-10-04-native-app-a-electron-shell/progress.md
  (not the plan's …/2026-10-04-native-app-a/), and the branch is native-a (not native-app-a) — the main session named
  both — cost if wrong: a reader looks in the plan's folder; git log holds every commit.
- **Task 5:** Ruling: main.js tells a test's unpackaged Electron apart with `const UNPACKAGED = !app.isPackaged &&
  process.defaultApp === true`, for the debugging-switch guard, --aib-profile and the Start menu entry
  (test_desktop_static follows) — Electron's isPackaged only compares the program's name with "electron", and the Mac
  app keeps Contents/MacOS/Electron, so the plan's guard would never fire on a Mac (a debugging switch would open a
  port; Task 6's real-Electron test would fail there); process.defaultApp is set only by Electron's default app,
  which setup deletes — cost if wrong: if Electron stops setting process.defaultApp, the AIB_TEST_ELECTRON tests fail
  to start, loudly; the product still refuses the switch.
- **Task 10:** Ruling: Step 2's RED was conftest's new `_no_real_desktop` erroring (run has no default_desktop yet),
  not the plan's TypeError/app_text — the plan adds the fixture before that import exists; same missing feature —
  cost if wrong: none.
- **Task 11:** Ruling: settings.js's opening comment keeps AI accounts' words and adds the plan's — the plan's anchor
  line moved with AI accounts, and replacing it alone would cut a sentence — cost if wrong: a comment's wording.
- **Task 12:** Ruling: the whole suite runs once, after the final review (suite.txt), not inside Task 12; task-done
  recorded the README/static/appwindow/portable run — the main session asked for one ~21-minute run at the end — cost
  if wrong: a Task 12 failure surfaces after the review (still before the report).
- **Final:** Ruling: ⌘W in the Mac app may reach the Window menu's Close (which hides) before the tab menu's close-tab
  guard — closing only hides, nothing is lost, and it can't be checked without Electron; it stands, hand-check it —
  cost if wrong: one surprise per ⌘W.
- **Final:** Ruling: Ctrl-C while the app is still starting can leave Electron's "Start AI Browser from a terminal"
  box (the line ends before the start) — a narrow window, harmless — cost if wrong: one stray dialog. (The fresh
  review raised its cost; F2 fixed it.)
- **Final:** Ruling: Windows' line is the app's stdin and stdout (plan decision 3), unverifiable here — it stands;
  Windows' hand checks 2-5 prove it — cost if wrong: every Windows start falls back to the browser window, with the
  reason in Settings.
- **Final:** Ruling: this plan's workspace (the ledger, suite.txt, the review package) is kept, not deleted as
  executing-plans' finish says — the main session runs a fresh reviewer that reads the ledger's rulings — cost if
  wrong: a git-ignored folder stays until the main session removes it.
- **Final (the fresh review's):** Ruling: only a real Electron 44 run can show main.js has no API slips, the handlers
  behave as policy.js says, the tray/shortcut/notifications work on an ad hoc app, codesign/sips/Info.plist give a
  launchable app whose microphone prompt names "AI Browser", the fuse offsets are right in the real binary, and the
  real 130 MB zip unpacks — the user's setup run and hand checks — cost if wrong: the setup run or a hand check fails,
  and the app falls back to the browser window with the reason.
- **Final (the fresh review's):** Ruling: the same-user threat model is out of scope (a program running as the user
  can start the app with its own --aib-line or edit the user-writable bundle and borrow its microphone grant; asar
  integrity and App Management protection aren't used) — stands: such a program already has the user's account —
  cost if wrong: a local program borrows AI Browser's microphone grant.
- **Final (the fresh review's):** Ruling: Web Bluetooth device picking isn't gated by the permission handler (Electron
  picks the first device with no select-bluetooth-device handler) — stands: only AI Browser's own CSP-restricted
  pages load — cost if wrong: theoretical.
- **Final (the fresh review's):** Ruling: on macOS another app's ⌥Space rarely blocks ours, so "taken" is seldom
  detected and Settings relies on "press it once to check" (plan decision 10) — cost if wrong: two apps answer the
  same shortcut until the user picks another.
- **Final (F2):** Ruling: Windows passes no --aib-line, so an app the engine started there whose line ends before its
  start takes the double-click path (the box, with the lock already let go) — telling them apart would need a new
  marker from the engine — cost if wrong: a stray box on Windows in that narrow race, blocking nothing.
- **Final (F2):** Ruling: the box's copy doesn't quit by itself when a real start comes; it lets go of the lock first,
  so it blocks nothing, and stays until OK — it can't hear the new copy (no lock, and a macOS box with no parent window
  runs synchronously) — cost if wrong: a stray box and a second Dock icon until OK.
- **Final (F2):** Ruling: `open` ending with 0 before the app connects now says "AI Browser's app closed as it started:
  another copy of it may still be open, or closing", which also covers an app that dies at once; a non-zero end keeps
  "macOS couldn't open AI Browser's app (open ended with N)" — cost if wrong: after a crash at start, the reason
  suggests another copy first.
- **Final (F2):** Ruling: main.js's no-engine flow is now tested under a stand-in Electron (tests/electron_stub.js);
  test_desktop_static's line-end check anchors `noEngine();` instead of the old inline quit — only a real Electron
  proves the API itself (the reviewer's ruling above) — cost if wrong: none beyond that ruling's.

## Deferred minors

- **From my review (the fresh review agreed they are minor):**
  1. `ai-browser app` started while `doctor --setup` builds the app (the setup holds `<home>/app/lock`) says "AI
     Browser is already running: its window is open", which is the wrong reason;
  2. main.js's `useShortcut` always tells the engine `pressed: false`, even when the same shortcut stays registered
     and was pressed before (unreachable from Settings today: a radio can't be picked twice);
  3. run.py's module docstring still says the app ends when its last window has been closed for a few seconds, which
     is now true of the browser window only;
  4. the menu-bar icon is the 128 px colour icon resized to 18 px, not a template image: it doesn't follow a dark or
     light menu bar, and it is blurry on Retina (no @2x).
- **From the fresh review:**
  1. unpack.py: a chain of links (`y → w/../../x`, then `w → .`) gets past the link check and leaves a link pointing
     outside the folder. Not exploitable (the zip must match the pinned digest first), but the docstring's promise
     doesn't hold. Re-check every link once the whole zip is unpacked;
  2. `doctor --setup` asks "Download it now?" before checking that AI Browser isn't running. Nothing is downloaded,
     but the check should come first;
  3. run.py's `_first_window` ignores `window.ended`, so an app that crashes or quits before its page connects waits
     60 s and then says "page never connected";
  4. no recovery when the window's page crashes (no `render-process-gone` handler, no reload): the window stays blank
     until Quit, which stops every agent. Reload on `render-process-gone`.
- **From the last suite:** `test_the_brain_draws_at_most_30_frames_a_second` counts frames over a 2 s sleep plus two
  DevTools round trips, so a loaded full run can count more than 62 (seen once: 67). It predates this branch.

## What only you can do

1. **On the Mac** (the setup is done, and the app runs):
   - **the look:** "AI Browser" in the Dock and in the menu bar; the menu-bar icon offers Open AI Browser, Show chat
     (greyed) and Quit;
   - **closing versus Quit:** the red button hides the window, and agents keep working. Open AI Browser or the Dock
     icon brings it back. Quit from the menu-bar icon ends the terminal's `ai-browser app`; start again, then ⌘Q: the
     same; start again, then Ctrl-C in the terminal: the app goes too;
   - **⌥Space** from another app shows AI Browser, and again hides it. Settings → AI Browser app then says "⌥Space
     shows and hides AI Browser". If Raycast or Alfred holds it, pick ⌥⇧Space;
   - **⌘W** on a closable tab: does it close the tab, or hide the window? (Either loses nothing.)
   - **the microphone:** hold Space to talk in Mission Control. macOS asks for "AI Browser" (not Terminal). Quit and
     start again: it doesn't ask again;
   - **a website link** in an agent's chat opens in Brave, never in the app's window;
   - **notifications:** a tool request shows "An agent is waiting for you", and a click opens AI Home at its row. A
     bot check shows "A bot check on <site>", and a click brings the agent's tab forward in Brave. Allow
     notifications when macOS asks;
   - **a double-click start:** quit, then double-click "AI Browser.app" in Finder. It says "Start AI Browser from a
     terminal". With the box still up, `uv run ai-browser app` must start normally (F2);
   - **no Node behind its back:** `ELECTRON_RUN_AS_NODE=1 ~/.ai-browser/desktop/"AI Browser.app"/Contents/MacOS/Electron
     -e "console.log(1)"` prints no 1. After about 20 seconds it says "Start AI Browser from a terminal": click OK;
   - **an update:** after a pull that changes the app's files, `ai-browser app` says "Updating AI Browser's app…" and
     then opens normally (F1). macOS may ask for the microphone once more.
2. **On Windows:**
   - the setup shows 158 MB and the Start menu line; type `y`, and it builds "AI Browser";
   - the window has a title bar only, and an icon by the clock. Its menu offers Open AI Browser, Show chat (greyed)
     and Quit; a left click opens the window. This also proves the stdin line (the ruling above);
   - the window's × hides it, and the icon stays. Quit ends the terminal's `ai-browser app`;
   - Alt+Space shows and hides AI Browser. With PowerToys Run on Alt+Space, Settings says it's taken;
   - notifications show as toasts, and a click opens the right place;
   - the cost said in the plan: AI Browser.exe keeps Electron's icon in File Explorer. The Start menu has "AI
     Browser"; started from there, it says to start AI Browser from a terminal.
