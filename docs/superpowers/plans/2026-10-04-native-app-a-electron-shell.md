# AI Browser's Own App (Part A, the Electron Shell) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `uv run ai-browser app` opens AI Browser as an Electron app of its own: its name and icon, a Dock icon and a
menu-bar icon, a locked-down window with the tab menu, the ⌥Space shortcut and native notifications. Closing the
window hides it, and Quit stops everything. `ai-browser doctor --setup` sets the app up once, after the user's yes.
Until then the Chrome app window opens as today.

**Architecture:**
- **Setup (`src/ai_browser/desktop/`, Python):**
  - `release.py` pins Electron 44.5.1: each zip's name, size and SHA-256;
  - `download.py` fetches the zip and checks it against the release's `SHASUMS256.txt`;
  - `unpack.py` unpacks it with its links and executable bits;
  - `fuses.py` turns off Electron's Node fuses;
  - `assemble.py` builds "AI Browser.app" (Info.plist, an icon from `sips`, signed ad hoc with `codesign`) or
    Windows' "AI Browser" folder, in `<home>/desktop/`;
  - `setup.py` runs all of it for `doctor --setup`, after a typed yes.
- **The app (`src/ai_browser/desktop/electron/`, plain CommonJS, no npm packages):**
  - `main.js`: the window registry, the locked-down window, the menu-bar (tray) icon, the global shortcut, the
    notifications, closing and Quit;
  - `preload.js`: the bridge to pages (named actions only; none yet);
  - `policy.js` and `line.js`: the app's rules and its line, as pure functions the tests run under Node.js.
- **The link (`desktop/launch.py`):** `DesktopWindow` has `AppWindow`'s surface plus one private line, JSON both ways.
  On Windows the line is the app's stdin and stdout. On macOS LaunchServices starts the app (`open -n -W -a`), so its
  microphone and Brave permissions are its own, and the line is a socket in a folder only the user can open. The
  one-time code always travels on the line.
- **The engine (`settings.py`, `app/server.py`, `app/run.py`):**
  - Settings gets the app's state and a `shortcut` setting, which the app tries before it is saved;
  - notifications go to the app in fixed words (`desktop/notes.py`), and a click opens the right place;
  - `run_app` opens the app when it is set up, else the browser window (wave B's `AppWindow`) with the setup offered;
  - the app's Quit ends the run.
- **Pages:** Settings → **AI Browser app**; AI Home's offer of the setup; AI Home's row in focus after a click;
  `talk.js` names AI Browser in the microphone's steps.

**Tech Stack:**
- Python 3.12: asyncio subprocesses and Unix sockets, zipfile, mmap, plistlib, and urllib with truststore;
  Starlette and uvicorn;
- Electron 44.5.1, plain CommonJS;
- macOS's `codesign`, `sips` and `open`;
- pytest, with fakes: a miniature Electron zip, a fake app, a fake `open`, a fake `codesign` and `sips`;
- Node.js for the app's pure rules, where it is installed;
- a throwaway headless Chrome for the pages;
- a real Electron only when `AIB_TEST_ELECTRON` names one.

**Spec:** `docs/superpowers/specs/2026-10-04-native-app-design.md`. The user approved it ("all good"). This plan is its
part a. Parts b (the extension's jobs) and c (the floating chat) get plans of their own.

**Branch and build order:** create the branch `native-app-a` from `main` once these are merged, in this order:
1. wave B (app-window): merged already;
2. the tab menu (`tab-menu`): the window's page `/app` with app.html, app.js and app.css, nav.js's `openTab`, the
   headers by path, and the close-tab key;
3. AI accounts (`docs/superpowers/plans/2026-10-04-ai-accounts.md`);
4. **this plan**.

**Files the tab menu and AI accounts change too.** Re-read each one at HEAD before the task that touches it. Find
every place by the text a step quotes, never by a line number, and keep what they added:
- `src/ai_browser/app/server.py` (Task 9): AI accounts adds eight app-only messages and the snapshot's `accounts`.
- `src/ai_browser/app/run.py` (Task 10): AI accounts rewires the start of `_run`. This plan changes the window part.
- `src/ai_browser/app/ui/settings.html` and `settings.js` (Task 11): AI accounts adds the **Accounts** section after
  **App window**, and its branches in `handle`; the tab menu adds `guardCloseKey()`.
- `src/ai_browser/app/ui/home.html`, `home.js` and `home.css` (Task 11), `tests/conftest.py` (Tasks 7 and 10),
  `tests/test_app_server.py` and AI accounts' `tests/test_accounts_seams.py` (Task 9), and `README.md` (Task 12).

Task 1's seams test fails first if a name this plan uses is spelled differently, or if the tab menu or AI accounts
isn't in.

**What parts b and c will find** (the seams this plan leaves):
- **The window registry:** `main.js`'s `windows` map, `makeWindow(kind, options)` and `showWindow(kind)`. Part c adds
  the `"chat"` window there.
- **The bridge:** `preload.js`'s `ACTIONS` list and `main.js`'s `ACTIONS` map, both empty here. Part c adds `chat` and
  `thisPage` to both, and to `test_the_bridge_holds_named_actions_only`.
- **The menu-bar icon:** its **Show chat** item is there, disabled. The shortcut calls `toggleMain`; part c points it
  at the chat.
- **The line:** its message types are listed in `desktop/launch.py`'s docstring. `AppServer._notify_desktop` takes a
  new kind of notification through `desktop/notes.py`.
- **Brave's watcher:** part b retires it. Then `_forward`'s and `_to_watcher`'s fallback to Brave's notifications goes.

## Plan decisions

Where the spec leaves a choice, or meets the code, this plan rules:
1. **Notifications come from the engine only,** over the line. The preload has no `notify`: a page's script, even an
   agent's text gone wrong, can't raise a notification with words of its own. The engine writes every title and
   body from fixed words (`desktop/notes.py`), and `main.js` shows them as written. The spec's preload list is an
   upper bound ("a few named actions only").
2. **The shortcut is set through the engine too,** with `settings_set`, which the pages already send. The engine asks
   the app to try the shortcut, and saves it only once the app could take it. The main window's pages sit in the
   tab menu's frames, where a preload doesn't run. So part a's bridge exposes no action: its `ACTIONS` table is the
   seam part c fills.
3. **The line is stdin and stdout on Windows, and a private socket on macOS.** A program the engine starts from a
   terminal would ask for the microphone, and for Brave, as the terminal. So macOS starts the app through
   LaunchServices (`open -n -W -a`), which gives it no pipe.
   - The socket sits in a new folder only this user can open (mode 0700), and its path is the app's one argument.
   - The engine takes the first connection only, then removes the socket.
   - It is as private as a pipe, and the one-time code still never goes on a command line.
4. **Writing to the clipboard is allowed too,** for AI Browser's own pages only. Their Copy buttons call
   `navigator.clipboard.writeText` (the Brain's draft, the watcher's folder, AI accounts' sign-in command, this
   plan's setup command). Electron asks the permission handler for `clipboard-sanitized-write`, so without it they
   would break. Reading the clipboard, and every other permission, stays refused. This departs from the spec's
   words "everything else is denied".
5. **No debugging, even if another program starts the app with a switch.**
   - The packaged app refuses to start with a debugging switch (`--remote-debugging-port` and its kin, `--inspect`,
     `--js-flags`).
   - Setup turns off Electron's fuses for running it as plain Node.js, `NODE_OPTIONS`, and Node's inspector.
   - Tests drive an *unpackaged* Electron (`AIB_TEST_ELECTRON`), which takes the switch on the test's own command
     line.
6. **`sips` makes the icon:** one command, `sips -s format icns <icon.png> --out <AI Browser.icns>`. The cost:
   `icon.png` is 128 px, so the Dock shows it slightly soft on a Retina screen. A larger `icon.png` fixes that later.
7. **Windows has no icon tool, and gets a Start menu entry.**
   - The cost of no icon tool: `AI Browser.exe` keeps Electron's icon in File Explorer, in Task Manager and on a
     pinned taskbar button. The window, the icon by the clock and the notifications show AI Browser's (set at run
     time).
   - Windows shows an app's notifications only when the Start menu has a shortcut to it with the same
     AppUserModelID and toast activator, so `main.js` adds "AI Browser" there. The setup's offer says so before the
     yes.
   - Started from that entry, it says to start AI Browser from a terminal (a double-click start comes later).
8. **Updates.** AI Browser's JavaScript is copied into the bundle, then signed, as the spec asks. When a `git pull`
   changes it, `ai-browser app` builds AI Browser's part again before it starts, with no download, and signs it
   again. macOS may then ask for the microphone once more. A newer pinned Electron is offered by `doctor --setup`
   only.
9. **`--window` asks for a browser window,** for that run. The "window's browser" setting is used by the fallback only,
   and Settings hides it while the app runs (the spec's "retires once Electron is set up").
10. **Three shortcuts and Off:** ⌥Space (the default), ⌥⇧Space and ⌃⇧Space, written Alt+Space, Alt+Shift+Space and
    Ctrl+Shift+Space on Windows.
    - None is a macOS default: ⌃Space and ⌃⌥Space switch input sources there.
    - A key recorder would catch the very shortcut it records.
    - macOS may let two apps hold the same key without telling either. So until the shortcut has been pressed once,
      Settings asks the user to press it once; after that press it says it works.
11. **Which notifications:** a bot check, a tool request (an agent waiting for the user), and the Brain's new notes.
    While the app runs, they replace Brave's watcher notifications, so nothing shows twice. Part b retires the
    watcher.
12. **Setup waits until AI Browser isn't running:** the app's files can't be replaced under it. It checks
    `<home>/app/lock`, which `ai-browser app` holds.
13. **The app ending by itself ends the run,** as Quit does, and the terminal says so.

## Global Constraints

Copied from the spec. Every task's requirements include these.

**The app:**
- "`uv run ai-browser app` starts the engine as today (the server, the one Brave connection, agents, the Brain), then
  the Electron app, named "AI Browser", with its own Dock icon and a menu-bar icon. The menu-bar icon offers **Open
  AI Browser**, **Show chat** and **Quit**." Show chat is part c's: here it is there, and disabled.
- "The main window is the tab menu (AI Home · Mission Control · Settings), with a title bar only. Its pages come from
  `http://127.0.0.1:<port>`, entered with wave B's one-time code and cookie."
- "closing the main window hides it, and the app keeps running in the menu bar, so ⌥Space still works and agents keep
  working"; "**Quit** (the menu-bar icon or ⌘Q) stops the app and its agents"; "this changes today's rule, where
  closing the window stops everything."
- "Before Electron is set up, `ai-browser app` opens the Chrome app window as it does today, and AI Home offers the
  setup. The floating chat, the shortcut, the menu-bar icon and native notifications need Electron."

**Setting it up:**
- "`ai-browser doctor --setup` shows what it will download (the pinned Electron version, its size and its address)
  and asks first";
- "the download is checked against Electron's `SHASUMS256.txt`, and a mismatch keeps nothing";
- "it builds "AI Browser.app" (on Windows, an "AI Browser" folder) in `~/.ai-browser/desktop/`, with AI Browser's
  name and icon. On the Mac the app is signed locally (ad hoc), so macOS remembers its microphone and Brave
  permissions";
- "**running it needs no Node.js.** AI Browser's Electron code is plain JavaScript in the repo, with no npm packages at
  run time";
- "a double-click start (Electron starting the engine itself) comes later."
- **The pin (exact values):** Electron **44.5.1**, the newest stable release on 2026-10-04 (GitHub's releases API; 45
  was still an alpha). The zips, from `https://github.com/electron/electron/releases/download/v44.5.1/`:

  | Zip | Bytes | SHA-256 |
  |---|---|---|
  | `electron-v44.5.1-darwin-arm64.zip` | 130,259,261 | `1d75703019bb16461ae65f3081d7e6f5c0b11e901d0ccb5c343bcf7bcdd6435c` |
  | `electron-v44.5.1-darwin-x64.zip` | 134,208,970 | `e567d13833d0e161d7749727355b98643461df3395b537cfa7bdddf8a8bfedff` |
  | `electron-v44.5.1-win32-x64.zip` | 157,998,329 | `9b382492dcfee91f8f9e92c91f7972550a1b95d2299cac72279dab33a600d7db` |

  These are the only computers: macOS on arm64 and on x64, and Windows on x64.

**Locked down:**
- "`contextIsolation` and `sandbox` are on, `nodeIntegration` is off, and `webSecurity` is on";
- "windows load only `http://127.0.0.1:<port>` pages of AI Browser. Any other navigation is blocked, and no window can
  open another: a website link goes to Brave through the engine's existing `open_url`". The tab menu's own frames
  for an engine's live view (`http://127.0.0.1:8770-8790/live?token=…`) stay allowed, as frames only;
- "the preload exposes a few named actions only" (plan decisions 1 and 2: none in part a);
- "permissions: the microphone is allowed for AI Browser's own origin only, and everything else is denied" (plan
  decision 4: writing to the clipboard too);
- "no debugging port and no DevTools in the product. Tests drive Electron through a test-only switch, and a static
  guard proves the product never passes it."

**The shortcut:** "⌥Space shows or hides it from anywhere. It can be changed in Settings, and a shortcut another app
holds is reported there, never silently failed." In part a it shows and hides the main window.

**Notifications:** "Electron shows native notifications for a bot check, an agent waiting for the user, and the
Brain's notes"; "they say what needs the user ("An agent is waiting for you", "A bot check on example.com"), never
message bodies or page text"; "clicking one opens the right place: AI Home's row, or the agent's tab in Brave."

**Safety:** "Downloads only with the user's OK: Electron's download is checksum-verified, and nothing else is
downloaded." "Notifications carry no message or page text." "No passwords, no API keys, and never `--bare`, as
everywhere."

**Retiring:** "Chrome's app mode (wave B's `AppWindow`, and the "window's browser" setting) retires once Electron is
set up, and stays only as the fallback in Decision 1".

**Coordination rules (earlier waves, still binding):**
- text files name `encoding="utf-8"`;
- new page text never says "this Mac" or "⌘": a page gets the shortcut's label from the engine;
- no macOS path and no `osascript` outside `platforms.py`. The paths inside AI Browser's own bundle (`Contents/…`)
  describe the app this plan builds, not the user's computer, so they live in `desktop/layout.py`;
- every module imports on a Windows-like Python (`tests/test_portable.py`).

**House rules:**
- UI text: plain words, short sentences.
- Run only the tests a step names (`uv run pytest <path>::<test> -q -p no:randomly`). The whole suite runs only in
  Task 12.
- **Tests never touch the user's real `~/.ai-browser`, Brave, Chrome or port 8792.** The user's app may be running.
  Use throwaway homes and profiles only.
- **No test does these:** download Electron, run the real `codesign` or `sips`, register a global shortcut, or add a
  Start menu entry. The one exception is the real-Electron tests. They run only with `AIB_TEST_ELECTRON`, and work in
  throwaway homes.
- **Nobody in this build downloads Electron** or any other binary.
- **Never click, answer or hide** Brave's "Allow remote debugging?" or its automation bar.
- Commit only the task's files.

## Review Focus

The spec's Review Focus items that belong to part a (1, 5, and 4 as far as the shell goes), and two failure modes it
implies. Each has its test in the task that owns the code.
1. **⌥Space already taken by another app** (Raycast, Alfred, a keyboard tool). Settings says so and offers the other
   shortcuts. Trying one that is taken keeps the one before. Nothing crashes, and nothing silently doesn't work: a
   shortcut nobody has pressed yet says "press it once to check". Tests: Task 4
   (`test_a_taken_shortcut_keeps_the_one_before`), Task 9
   (`test_a_taken_shortcut_is_said_and_another_one_is_taken_instead`), Task 11
   (`test_settings_says_the_shortcut_is_taken_and_offers_another`).
2. **The Electron download interrupted, or not matching its checksum.** Nothing is kept, the Chrome app window still
   works, and Settings says what happened. Tests: Task 2 (`test_a_download_cut_halfway_keeps_nothing`,
   `test_a_zip_that_doesnt_match_keeps_nothing`), Task 7
   (`test_a_download_cut_halfway_keeps_nothing_and_settings_will_say_why`), Task 10
   (`test_an_app_that_cant_start_leaves_a_browser_window_and_the_reason`), Task 11
   (`test_settings_and_ai_home_offer_the_app_and_say_what_went_wrong`).
3. **A website link inside an Electron page** (an agent's chat, a draft). It opens in Brave, never inside Electron:
   no frame leaves AI Browser's pages, and no window opens. Tests: Task 4
   (`test_frames_go_only_to_our_pages_and_live_views`), Task 5 (`test_every_window_is_locked_down`, and with a real
   Electron `test_the_real_app_is_locked_down`).
4. **The engine ends without a word** (a crash, a kill, a second Ctrl-C). The app must not stay in the menu bar
   talking to nobody: the line's end quits it. Tests: Task 5 (`test_the_menu_bar_icon_closing_and_quitting`, and with
   a real Electron `test_the_real_app_quits_when_the_engine_goes`).
5. **A `git pull` changes the app's JavaScript after setup.** The old copy in the bundle must not run against a newer
   engine. `ai-browser app` builds AI Browser's part again before it starts, with no download. If that fails, it
   opens a browser window and says why. Tests: Task 6 (`test_a_changed_part_is_noticed_and_built_again`), Task 8
   (`test_a_stale_app_is_built_again_before_it_starts`).

## File map

**New:**
- `src/ai_browser/desktop/__init__.py`: the package's docstring.
- `src/ai_browser/desktop/release.py` (Task 1): `VERSION`, `RELEASE`, `SHASUMS`, `SETUP_COMMAND`, `Asset`, `ASSETS`,
  `arch`, `asset_for`, `offer`.
- `src/ai_browser/desktop/layout.py` (Task 1): `APP_NAME`, `BUNDLE_ID`, `folder`, `app_path`, `executable`,
  `resources`, `framework`, `profile`, `stamp`, `write_stamp`, `installed`, `problem`, `set_problem`.
- `src/ai_browser/desktop/download.py` (Task 2): `SetupError`, `MISMATCH`, `NOT_LISTED`, `CUT`, `NEEDED`, `listed`,
  `download`.
- `src/ai_browser/desktop/unpack.py` (Task 3): `UnpackError`, `unpack`.
- `src/ai_browser/desktop/fuses.py` (Task 3): `SENTINEL`, `OFF`, `FuseError`, `wires`, `lock_down`, `states`.
- `src/ai_browser/desktop/shortcut.py` (Task 4): `SHORTCUTS`, `DEFAULT`, `SHORTCUT_ERROR`, `label`, `state`.
- `src/ai_browser/desktop/electron/policy.js` and `line.js` (Task 4); `main.js`, `preload.js` and `package.json`
  (Task 5).
- `src/ai_browser/desktop/stage.py` (Task 5): `ELECTRON`, `ICON`, `APP_FILES`, `stage_app`, `part_hash`.
- `src/ai_browser/desktop/assemble.py` (Task 6): `PLIST`, `Tools`, `sign_command`, `icon_command`, `layer_hash`,
  `stale`, `build`, `refresh`.
- `src/ai_browser/desktop/setup.py` (Task 7): `FETCH`, `TOOLS`, `STOPPED`, `RUNNING`, `set_up`.
- `src/ai_browser/desktop/launch.py` (Task 8): `DesktopError`, `DesktopWindow`, `mac_command`, `windows_command`,
  `default_desktop`, `START_WAIT`, `ANSWER_WAIT`, `QUIT_WAIT`, `UPDATED`.
- `src/ai_browser/desktop/notes.py` (Task 9): `note_for`.
- **Tests:**
  - helpers: `tests/fake_electron_zip.py` (Tasks 2 and 3), `tests/fake_tools.py` (Task 6), `tests/fake_electron.py`
    and `tests/fake_open.py` (Task 8), `tests/fake_desktop.py` (Task 9);
  - `tests/test_native_a_seams.py`, `test_desktop_release.py` (Task 1); `test_desktop_download.py` (Task 2);
    `test_desktop_unpack.py` (Task 3); `test_desktop_js.py` (Task 4); `test_desktop_static.py` and
    `test_desktop_electron.py` (Task 5, with one test more in Tasks 6, 8 and 12); `test_desktop_assemble.py`
    (Task 6); `test_desktop_setup.py` (Task 7); `test_desktop_launch.py` (Task 8); `test_desktop_server.py` (Task 9);
    `test_desktop_run.py` (Task 10); `test_desktop_pages.py` (Task 11).

**Changed:**
- `src/ai_browser/cli.py` (Tasks 7 and 10), `src/ai_browser/settings.py` (Task 9), `src/ai_browser/app/server.py`
  (Task 9), `src/ai_browser/app/run.py` (Task 10).
- **Pages (Task 11):** `app/ui/settings.html`, `settings.js`, `home.html`, `home.js`, `home.css` and `talk.js`.
- **Docs (Task 12):** `README.md`.
- **Tests:** `tests/conftest.py` (Tasks 7 and 10), `tests/test_settings.py`, `tests/test_app_server.py` and
  `tests/test_accounts_seams.py` (Task 9).

The ledger is `.superpowers/sdd/2026-10-04-native-app-a/progress.md` (git-ignored). Note in it each task's result,
the real-Electron tests' result if they ran, and every hand-check finding.

---

### Task 1: The pinned Electron, where the app lives, and the seams

**Files:**
- Create: `src/ai_browser/desktop/__init__.py`
- Create: `src/ai_browser/desktop/release.py`
- Create: `src/ai_browser/desktop/layout.py`
- Test: `tests/test_native_a_seams.py` (new), `tests/test_desktop_release.py` (new)

**Interfaces:**
- Consumes: wave B, the tab menu and AI accounts, as merged. The seams test pins the names.
- Produces:
  - **`release.py`:**
    - `VERSION = "44.5.1"`, `RELEASE` (the release's download address), `SHASUMS` (its `SHASUMS256.txt`),
      `SETUP_COMMAND = "uv run ai-browser doctor --setup"`;
    - `Asset(system, arch, name, size, sha256, where)`, frozen, with `.url` and `.megabytes` ("130 MB");
    - `ASSETS`: darwin arm64, darwin x64 and win32 x64, in that order;
    - `arch(machine=None) -> str` ("arm64", "x64" or "");
    - `asset_for(system=None, machine=None) -> Asset | None`;
    - `offer(asset, folder, system=None) -> list[str]`: the lines `doctor --setup` shows before it asks.
  - **`layout.py`:**
    - `APP_NAME = "AI Browser"`, `BUNDLE_ID = "io.github.nanotechs001.ai-browser"`;
    - paths: `folder(home)`, `app_path(home, system=None)`, `executable(app, system=None)`,
      `resources(app, system=None)`, `framework(app)` and `profile(home)`, each a `Path`;
    - records: `stamp(home) -> dict | None`, `write_stamp(home, data)`,
      `installed(home, system=None) -> dict | None`, `problem(home) -> str` ("" when there is none) and
      `set_problem(home, text: str | None)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_native_a_seams.py`:

```python
"""AI Browser's own app (part a) builds on wave B (the app window), the tab menu and AI accounts through a few names.
This pins them, so no task starts on a name the merged code spells differently, or before those are merged."""

import importlib.util
import inspect
from pathlib import Path

UI = Path(__file__).parents[1] / "src" / "ai_browser" / "app" / "ui"


def test_the_merged_code_has_the_names_this_plan_uses():
    from ai_browser import cli, platforms, settings, syncdir
    from ai_browser.app import run, server, window
    from ai_browser.config import LIVE_PORTS, home
    from ai_browser.hearing import model

    # wave B: the window, its launcher, and how run_app waits and ends
    assert issubclass(window.WindowError, RuntimeError) and callable(window.default_launcher)
    assert callable(window.choices)
    for name in ("_run", "_until_closed", "_first_window", "_call", "ready_text", "default_launcher"):
        assert callable(getattr(run, name)), name
    assert {"ready", "stop", "out", "browser", "window_browser", "launcher"} <= set(
        inspect.signature(run.run_app).parameters)
    assert run.WINDOW_GRACE and run.WINDOW_START_WAIT and "{name}" in run.NO_WINDOW
    # the server: its settings, the watcher's notifications, a bot check's tab
    assert {"model", "voice", "window_browser"} <= set(server.SETTING_KEYS)
    for name in ("_settings_payload", "_settings_set", "_forward", "_to_watcher", "_show_check", "_send_all", "_job"):
        assert callable(getattr(server.AppServer, name)), name
    assert "focus" not in server.WATCHER_RECEIVES and "settings" not in server.WATCHER_RECEIVES
    assert server.CHECK_SITE.pattern == r"[a-z0-9.-]{1,253}"
    assert {"window_browser", "model", "voice"} <= set(settings.DEFAULTS)
    assert callable(settings.read_settings) and callable(settings.write_setting)
    assert callable(cli._doctor_setup) and callable(cli.main)
    assert callable(model.tls_context) and callable(model.urlopen_fetch)
    for name in ("shortcut", "lock_file", "replace", "rmtree", "unlink"):
        assert callable(getattr(platforms, name)), name
    assert callable(syncdir.write_atomic) and callable(home) and LIVE_PORTS == range(8770, 8791)
    # the tab menu: the window's own page (/app) shows ours in frames; a page asks it for a tab
    assert server.SHELL == "/app" and callable(server._page_headers)
    for name in ("app.html", "app.js", "nav.js", "talk.js", "settings.html", "settings.js", "home.html", "home.js",
                 "home.css"):
        assert (UI / name).is_file(), name
    assert "export function openTab(" in (UI / "nav.js").read_text(encoding="utf-8")
    assert "export function browserName(" in (UI / "talk.js").read_text(encoding="utf-8")
    page = (UI / "settings.html").read_text(encoding="utf-8")
    assert 'id="window-section"' in page
    # AI accounts, built before this plan: its Settings section and its module
    assert 'id="accounts-section"' in page and importlib.util.find_spec("ai_browser.accounts") is not None


def test_the_tests_have_the_helpers_this_plan_uses():
    import conftest
    import fake_brave
    import fake_window
    import test_app_run
    import test_app_server
    import test_cli
    import test_home
    import test_tab_menu
    import ui_socket

    for module, names in (
            (conftest, ("fake_python", "symlink_or_skip", "file_mode", "_no_real_window", "_never_the_users_app_port")),
            (test_home, ("stack", "home", "until", "page_js", "open_page")),
            (test_tab_menu, ("connected", "frame", "tab", "active_is")),
            (test_app_run, ("servers", "quiet")), (test_app_server, ("started", "recv", "until")),
            (test_cli, ("_setup_env", "_browser_port_stand_in")), (fake_brave, ("add_agent",)),
            (fake_window, ("SocketWindow",)), (ui_socket, ("ui_socket",))):
        for name in names:
            assert callable(getattr(module, name)), (module.__name__, name)
    assert conftest.USERS_APP_PORT == 8792  # the tab menu's: no test's server takes it (Task 7 guards the doctor too)
```

Create `tests/test_desktop_release.py`:

```python
"""The one Electron release AI Browser's own app is built on (desktop/release.py), and where the app lives
(desktop/layout.py): pure facts, no network, no download."""

from conftest import file_mode


def test_the_pin_is_electron_44_5_1_with_its_listed_sizes_and_checksums():
    from ai_browser.desktop import release

    assert release.VERSION == "44.5.1"
    assert release.SHASUMS == "https://github.com/electron/electron/releases/download/v44.5.1/SHASUMS256.txt"
    assert release.SETUP_COMMAND == "uv run ai-browser doctor --setup"
    assert [(asset.system, asset.arch, asset.name, asset.size, asset.sha256) for asset in release.ASSETS] == [
        ("darwin", "arm64", "electron-v44.5.1-darwin-arm64.zip", 130_259_261,
         "1d75703019bb16461ae65f3081d7e6f5c0b11e901d0ccb5c343bcf7bcdd6435c"),
        ("darwin", "x64", "electron-v44.5.1-darwin-x64.zip", 134_208_970,
         "e567d13833d0e161d7749727355b98643461df3395b537cfa7bdddf8a8bfedff"),
        ("win32", "x64", "electron-v44.5.1-win32-x64.zip", 157_998_329,
         "9b382492dcfee91f8f9e92c91f7972550a1b95d2299cac72279dab33a600d7db")]
    assert release.ASSETS[0].url == ("https://github.com/electron/electron/releases/download/v44.5.1/"
                                     "electron-v44.5.1-darwin-arm64.zip")
    assert [asset.megabytes for asset in release.ASSETS] == ["130 MB", "134 MB", "158 MB"]


def test_each_computer_gets_its_own_zip_or_none():
    from ai_browser.desktop.release import ASSETS, arch, asset_for

    assert asset_for("darwin", "arm64") is ASSETS[0]
    assert asset_for("darwin", "x86_64") is ASSETS[1]
    assert asset_for("win32", "AMD64") is ASSETS[2]
    assert asset_for("win32", "ARM64") is None  # Windows on Arm: a browser window
    assert asset_for("linux", "x86_64") is None
    assert asset_for("darwin", "ppc") is None and arch("ppc") == ""


def test_the_offer_shows_the_version_size_and_address_first(tmp_path):
    from ai_browser.desktop.release import ASSETS, offer

    assert offer(ASSETS[0], tmp_path / "desktop", "darwin") == [
        "AI Browser can run as its own app: its own Dock icon, a menu-bar icon, the ⌥Space shortcut and "
        "notifications.",
        "It is built from Electron 44.5.1 for a Mac with Apple silicon: 130 MB, from",
        "  https://github.com/electron/electron/releases/download/v44.5.1/electron-v44.5.1-darwin-arm64.zip",
        "The download is checked against Electron's SHASUMS256.txt. If anything doesn't match, nothing is kept.",
        f"The app is built in {tmp_path / 'desktop'}. Nothing else is downloaded."]
    windows = offer(ASSETS[2], tmp_path / "desktop", "win32")
    assert windows[0] == ("AI Browser can run as its own app: a taskbar icon, an icon by the clock, the Alt+Space "
                          "shortcut and notifications.")
    assert windows[1] == "It is built from Electron 44.5.1 for Windows (x64): 158 MB, from"
    assert windows[-1] == "It also adds AI Browser to the Start menu, so Windows can show its notifications."
    assert "⌥" not in " ".join(windows)


def test_the_app_lives_in_the_homes_desktop_folder(tmp_path):
    from ai_browser.desktop import layout

    home = tmp_path / "home"
    mac, windows = layout.app_path(home, "darwin"), layout.app_path(home, "win32")
    assert mac == home / "desktop" / "AI Browser.app" and windows == home / "desktop" / "AI Browser"
    assert layout.executable(mac, "darwin") == mac / "Contents" / "MacOS" / "Electron"
    assert layout.executable(windows, "win32") == windows / "AI Browser.exe"
    assert layout.resources(mac, "darwin") == mac / "Contents" / "Resources"
    assert layout.resources(windows, "win32") == windows / "resources"
    assert layout.framework(mac) == (mac / "Contents" / "Frameworks" / "Electron Framework.framework"
                                     / "Electron Framework")
    assert layout.profile(home) == home / "desktop" / "profile"
    assert (layout.APP_NAME, layout.BUNDLE_ID) == ("AI Browser", "io.github.nanotechs001.ai-browser")


def test_installed_means_built_here_for_this_system(tmp_path):
    from ai_browser.desktop import layout

    home = tmp_path / "home"
    assert layout.installed(home, "darwin") is None and layout.stamp(home) is None
    stamp = {"electron": "44.5.1", "system": "darwin", "arch": "arm64", "layer": "x"}
    layout.write_stamp(home, stamp)
    assert layout.installed(home, "darwin") is None  # the record alone: no program
    program = layout.executable(layout.app_path(home, "darwin"), "darwin")
    program.parent.mkdir(parents=True)
    program.write_bytes(b"")
    assert layout.installed(home, "darwin") == stamp and layout.installed(home, "win32") is None
    assert file_mode(home / "desktop" / "app.json") in (0o600, None)
    (home / "desktop" / "app.json").write_text("{broken", encoding="utf-8")
    assert layout.installed(home, "darwin") is None and layout.stamp(home) is None  # never raises


def test_the_last_problem_is_kept_for_settings_and_then_forgotten(tmp_path):
    from ai_browser.desktop import layout

    home = tmp_path / "home"
    assert layout.problem(home) == ""
    layout.set_problem(home, "The download stopped before the end: nothing was kept")
    assert layout.problem(home) == "The download stopped before the end: nothing was kept"
    assert file_mode(home / "desktop" / "problem.json") in (0o600, None)
    layout.set_problem(home, None)
    assert layout.problem(home) == "" and not (home / "desktop" / "problem.json").exists()
    layout.set_problem(home, None)  # nothing to forget: fine
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_native_a_seams.py tests/test_desktop_release.py -q -p no:randomly`

Expected:
- the release tests FAIL with `ModuleNotFoundError: No module named 'ai_browser.desktop'`;
- the seams tests PASS. If one fails, stop: a name differs, or the tab menu or AI accounts isn't merged yet. Say so
  in the ledger, and don't go on.

- [ ] **Step 3: Write the package, the pin and the layout**

Create `src/ai_browser/desktop/__init__.py`:

```python
"""AI Browser's own app: Electron (a Chromium with a window, a menu-bar icon, a global shortcut and native
notifications of its own) over the Python engine. `ai-browser doctor --setup` downloads one pinned Electron after the
user's yes, checks it and builds the app in <home>/desktop/ (setup.py). `ai-browser app` then starts it (launch.py),
or a browser window (app/window.py) while it isn't set up. The app's own JavaScript is in desktop/electron/."""
```

Create `src/ai_browser/desktop/release.py`:

```python
"""The one Electron release AI Browser's own app is built on, pinned: its version, and for each computer the zip's
name, size and SHA-256 as the release lists them (GitHub's releases API, 2026-10-04). Setup downloads only these
files, from this release, and checks them against its SHASUMS256.txt. Nothing here touches the network."""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from pathlib import Path

VERSION = "44.5.1"  # the newest stable Electron on 2026-10-04 (45 was still an alpha)
RELEASE = f"https://github.com/electron/electron/releases/download/v{VERSION}"
SHASUMS = f"{RELEASE}/SHASUMS256.txt"
SETUP_COMMAND = "uv run ai-browser doctor --setup"


@dataclass(frozen=True)
class Asset:
    system: str  # sys.platform's value: "darwin" or "win32"
    arch: str  # "arm64" or "x64"
    name: str
    size: int  # bytes
    sha256: str
    where: str  # the computer, in plain words

    @property
    def url(self) -> str:
        return f"{RELEASE}/{self.name}"

    @property
    def megabytes(self) -> str:
        return f"{round(self.size / 1_000_000)} MB"


ASSETS = (
    Asset("darwin", "arm64", f"electron-v{VERSION}-darwin-arm64.zip", 130_259_261,
          "1d75703019bb16461ae65f3081d7e6f5c0b11e901d0ccb5c343bcf7bcdd6435c", "a Mac with Apple silicon"),
    Asset("darwin", "x64", f"electron-v{VERSION}-darwin-x64.zip", 134_208_970,
          "e567d13833d0e161d7749727355b98643461df3395b537cfa7bdddf8a8bfedff", "an Intel Mac"),
    Asset("win32", "x64", f"electron-v{VERSION}-win32-x64.zip", 157_998_329,
          "9b382492dcfee91f8f9e92c91f7972550a1b95d2299cac72279dab33a600d7db", "Windows (x64)"),
)
_ARCHES = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64", "amd64": "x64", "x64": "x64"}


def arch(machine: str | None = None) -> str:
    """platform.machine() in Electron's words ("arm64", "x64"), or "" for anything else."""
    return _ARCHES.get((platform.machine() if machine is None else machine).lower(), "")


def asset_for(system: str | None = None, machine: str | None = None) -> Asset | None:
    """The zip for this computer; None where AI Browser's own app doesn't run (Linux, Windows on Arm)."""
    system, found = system or sys.platform, arch(machine)
    return next((asset for asset in ASSETS if asset.system == system and asset.arch == found), None)


def offer(asset: Asset, folder: Path, system: str | None = None) -> list[str]:
    """What `doctor --setup` shows before it asks: what the app adds, what is downloaded (the version, the size, the
    address), how it is checked, and where the app goes."""
    if (system or sys.platform) == "darwin":
        adds = "its own Dock icon, a menu-bar icon, the ⌥Space shortcut and notifications"
    else:
        adds = "a taskbar icon, an icon by the clock, the Alt+Space shortcut and notifications"
    lines = [f"AI Browser can run as its own app: {adds}.",
             f"It is built from Electron {VERSION} for {asset.where}: {asset.megabytes}, from",
             f"  {asset.url}",
             "The download is checked against Electron's SHASUMS256.txt. If anything doesn't match, nothing is kept.",
             f"The app is built in {folder}. Nothing else is downloaded."]
    if (system or sys.platform) == "win32":
        lines.append("It also adds AI Browser to the Start menu, so Windows can show its notifications.")
    return lines
```

Create `src/ai_browser/desktop/layout.py`:

```python
"""Where AI Browser's own app lives: <home>/desktop/ holds the app ("AI Browser.app" on macOS, an "AI Browser" folder
on Windows), its Electron profile, app.json and problem.json.
- app.json says what was built: the Electron version, the system, and a hash of AI Browser's own part, so a change
  to the JavaScript is noticed (assemble.py).
- problem.json says why the last setup or start didn't work, for Settings.
The paths inside the bundle describe AI Browser's own app, never the user's computer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .. import platforms
from ..syncdir import write_atomic

APP_NAME = "AI Browser"
BUNDLE_ID = "io.github.nanotechs001.ai-browser"  # also Windows' AppUserModelID (main.js's APP_ID)


def _system(system: str | None) -> str:
    return system or sys.platform


def folder(home) -> Path:
    return Path(home) / "desktop"


def app_path(home, system: str | None = None) -> Path:
    return folder(home) / (f"{APP_NAME}.app" if _system(system) == "darwin" else APP_NAME)


def executable(app: Path, system: str | None = None) -> Path:
    """The program inside an app built here (`app`: its bundle, or its folder on Windows)."""
    if _system(system) == "darwin":
        return Path(app) / "Contents" / "MacOS" / "Electron"
    return Path(app) / f"{APP_NAME}.exe"


def resources(app: Path, system: str | None = None) -> Path:
    return Path(app) / "Contents" / "Resources" if _system(system) == "darwin" else Path(app) / "resources"


def framework(app: Path) -> Path:
    """macOS: the Electron Framework binary, which holds the fuses."""
    return Path(app) / "Contents" / "Frameworks" / "Electron Framework.framework" / "Electron Framework"


def profile(home) -> Path:
    return folder(home) / "profile"  # main.js finds the same folder from where its program is


def _read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def stamp(home) -> dict | None:
    """app.json: what was built here, or None (missing, unreadable or broken: it never raises)."""
    return _read(folder(home) / "app.json")


def write_stamp(home, data: dict) -> None:
    write_atomic(folder(home) / "app.json", (json.dumps(data, indent=1) + "\n").encode("utf-8"), 0o600)


def installed(home, system: str | None = None) -> dict | None:
    """The stamp of an app built here for this system, if its program is there too; else None."""
    system, found = _system(system), stamp(home)
    if found is None or found.get("system") != system:
        return None
    return found if executable(app_path(home, system), system).is_file() else None


def problem(home) -> str:
    """Why the last setup or start didn't work, in plain words; "" when nothing went wrong."""
    found = _read(folder(home) / "problem.json")
    text = found.get("text") if found is not None else None
    return text if isinstance(text, str) else ""


def set_problem(home, text: str | None) -> None:
    """Keep why the last setup or start didn't work, for Settings; None forgets it."""
    path = folder(home) / "problem.json"
    if text:
        write_atomic(path, (json.dumps({"text": text[:300]}) + "\n").encode("utf-8"), 0o600)
    else:
        platforms.unlink(path, missing_ok=True)
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_native_a_seams.py tests/test_desktop_release.py tests/test_portable.py -q -p no:randomly`

Expected: PASS (`test_portable.py` checks that the new modules import on a Windows-like Python, and that every text
read names its encoding).

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/desktop/__init__.py src/ai_browser/desktop/release.py src/ai_browser/desktop/layout.py tests/test_native_a_seams.py tests/test_desktop_release.py
git commit -m "feat(desktop): the pinned Electron 44.5.1 and where AI Browser's own app lives"
```

### Task 2: Electron's zip, downloaded and checked against SHASUMS256.txt

**Files:**
- Create: `src/ai_browser/desktop/download.py`
- Create: `tests/fake_electron_zip.py` (the release from memory; Task 3 adds the zips)
- Test: `tests/test_desktop_download.py` (new)

**Interfaces:**
- Consumes: Task 1's `Asset` and `SHASUMS`; `hearing/model.py`'s `urlopen_fetch` (truststore, certificates always
  checked); `platforms.replace` and `platforms.unlink`.
- Produces:
  - `SetupError(Exception)`: a setup step that failed, in plain words. Tasks 6 to 8 raise it too.
  - `MISMATCH`, `NOT_LISTED`, `CUT` (the exact texts below), and `NEEDED = 1_000_000_000` (bytes of free disk).
  - `listed(text, name) -> str | None`: the SHA-256 that `SHASUMS256.txt` lists for `name`.
  - `download(asset, folder, fetch=urlopen_fetch, progress=lambda done: None) -> Path`: the checked zip at
    `<folder>/<asset.name>`. `fetch(url)` returns an object with `read(size)` that is a context manager, as
    `urllib.request.urlopen` does.
  - `tests/fake_electron_zip.py`: `checksum(data) -> str`, and `ReleaseFetch(asset, data)` with `.urls` and the
    knobs `.listed`, `.fail`, `.cut_at`, `.short`, `.corrupt` and `.extra`.

- [ ] **Step 1: Write the failing tests**

Create `tests/fake_electron_zip.py`:

```python
"""Electron's release in miniature, for setup's tests: its SHASUMS256.txt and a zip served from memory
(ReleaseFetch). From Task 3 it also has zips with Electron's own layout: a Mac's Electron.app with its framework's
links and fuses, or Windows' electron.exe, a few bytes per file. No test downloads Electron."""

from __future__ import annotations

import hashlib
import io


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Cut(io.BytesIO):
    """A zip's bytes. With `at`, the connection drops once that many have been read (ConnectionResetError)."""

    def __init__(self, data: bytes, at: int | None = None):
        super().__init__(data)
        self.at = at

    def read(self, size: int = -1) -> bytes:
        if self.at is not None:
            if self.tell() >= self.at:
                raise ConnectionResetError(54, "Connection reset by peer")
            size = self.at - self.tell() if size < 0 else min(size, self.at - self.tell())
        return super().read(size)


class ReleaseFetch:
    """GitHub's release, from memory, by the last part of the address: SHASUMS256.txt (listing `asset`'s checksum, or
    `listed`) and the zip. It records every address asked for. It can fail (`fail`), drop the connection mid-zip
    (`cut_at`), end the zip early with no error (`short`), change a byte (`corrupt`) or add bytes (`extra`)."""

    def __init__(self, asset, data: bytes):
        self.asset, self.data = asset, data
        self.urls: list[str] = []
        self.listed = asset.sha256
        self.fail: Exception | None = None
        self.cut_at: int | None = None
        self.short = False
        self.corrupt = False
        self.extra = b""

    def __call__(self, url: str) -> io.BytesIO:
        self.urls.append(url)
        if self.fail is not None:
            raise self.fail
        if url.rsplit("/", 1)[1] == "SHASUMS256.txt":
            lines = f"{'0' * 64} *electron-v44.5.1-linux-x64.zip\n{self.listed} *{self.asset.name}\n"
            return io.BytesIO(lines.encode("utf-8"))
        data = self.data[:-1000] if self.short else self.data
        if self.corrupt:
            data = bytes([data[0] ^ 1]) + data[1:]
        return Cut(data + self.extra, self.cut_at)
```

Create `tests/test_desktop_download.py`:

```python
"""Electron's zip (desktop/download.py): fetched from the pinned release only, and checked twice. The release's
SHASUMS256.txt must list the pinned checksum, and the zip must have the pinned size and that checksum. It is written
as a .part file and keeps its name only once checked. A cut, a mismatch, an error or Ctrl-C keeps nothing. The
release is served from memory (tests/fake_electron_zip.py)."""

import inspect
import socket
import ssl
import urllib.error
from types import SimpleNamespace

import pytest

from fake_electron_zip import ReleaseFetch, checksum

DATA = bytes(range(256)) * 9000  # 2,304,000 bytes: two pieces of 1 MiB and a short one


def release(tmp_path):
    from ai_browser.desktop.release import Asset

    asset = Asset("darwin", "arm64", "electron-test.zip", len(DATA), checksum(DATA), "a test Mac")
    return asset, ReleaseFetch(asset, DATA), tmp_path / "download"


def test_a_checked_zip_keeps_its_name_and_nothing_else_is_left(tmp_path):
    from ai_browser.desktop.download import download
    from ai_browser.desktop.release import SHASUMS

    asset, fetch, folder = release(tmp_path)
    seen = []
    path = download(asset, folder, fetch, seen.append)
    assert path == folder / "electron-test.zip" and path.read_bytes() == DATA
    assert sorted(item.name for item in folder.iterdir()) == ["electron-test.zip"]  # no .part left
    assert fetch.urls == [SHASUMS, asset.url]  # the checksums first, then the zip
    assert seen == sorted(seen) and seen[-1] == len(DATA)


def test_a_download_cut_halfway_keeps_nothing(tmp_path):  # Review Focus 2
    from ai_browser.desktop.download import CUT, SetupError, download

    asset, fetch, folder = release(tmp_path)
    fetch.cut_at = len(DATA) // 2
    with pytest.raises(SetupError) as error:
        download(asset, folder, fetch)
    assert str(error.value) == CUT == "The download stopped before the end: nothing was kept"
    assert list(folder.iterdir()) == []
    fetch.cut_at, fetch.short = None, True  # the connection ends early, with no error
    with pytest.raises(SetupError, match="^The download stopped before the end"):
        download(asset, folder, fetch)
    assert list(folder.iterdir()) == []


def test_a_zip_that_doesnt_match_keeps_nothing(tmp_path):  # Review Focus 2
    from ai_browser.desktop.download import MISMATCH, NOT_LISTED, SetupError, download

    asset, fetch, folder = release(tmp_path)
    fetch.corrupt = True  # one changed byte: the same size, another checksum
    with pytest.raises(SetupError) as error:
        download(asset, folder, fetch)
    assert str(error.value) == MISMATCH == "The download didn't match Electron's checksum: nothing was kept"
    fetch.corrupt, fetch.extra = False, b"!"  # one byte too many
    with pytest.raises(SetupError, match="didn't match"):
        download(asset, folder, fetch)
    assert list(folder.iterdir()) == []
    fetch.extra, fetch.listed = b"", "f" * 64  # the release lists another checksum: the zip is never fetched
    fetch.urls.clear()
    with pytest.raises(SetupError) as error:
        download(asset, folder, fetch)
    assert str(error.value) == NOT_LISTED == ("Electron's SHASUMS256.txt doesn't list the expected checksum: nothing "
                                              "was downloaded")
    assert len(fetch.urls) == 1 and list(folder.iterdir()) == []


def test_ctrl_c_keeps_nothing(tmp_path):
    from ai_browser.desktop.download import download

    asset, fetch, folder = release(tmp_path)

    def stop(done):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        download(asset, folder, fetch, stop)
    assert list(folder.iterdir()) == []


def test_network_problems_are_plain_words(tmp_path):
    from ai_browser.desktop.download import SetupError, download

    asset, fetch, folder = release(tmp_path)
    for fail, said in (
            (urllib.error.URLError(socket.gaierror(8, "nodename nor servname provided")), "^No internet connection$"),
            (urllib.error.HTTPError("https://github.com/x", 404, "Not Found", {}, None),
             "^The download failed: GitHub answered 404$"),
            (urllib.error.URLError(ssl.SSLCertVerificationError("certificate verify failed")), "couldn't be checked"),
            (TimeoutError("timed out"), "^The download stopped: the connection timed out$")):
        fetch.fail = fail
        with pytest.raises(SetupError, match=said):
            download(asset, folder, fetch)
    assert list(folder.iterdir()) == []


def test_low_disk_fails_before_anything_is_fetched(tmp_path, monkeypatch):
    import ai_browser.desktop.download as module

    asset, fetch, folder = release(tmp_path)
    monkeypatch.setattr(module.shutil, "disk_usage", lambda path: SimpleNamespace(free=1_000))
    with pytest.raises(module.SetupError, match="^Not enough free disk space: 1 GB is needed$"):
        module.download(asset, folder, fetch)
    assert fetch.urls == []


def test_the_checksum_list_is_read_as_sha256sum_writes_it():
    from ai_browser.desktop.download import listed

    text = f"{'a' * 64} *electron-v44.5.1-darwin-arm64.zip\n{'b' * 64}  electron-v44.5.1-win32-x64.zip\nnot a line\n"
    assert listed(text, "electron-v44.5.1-darwin-arm64.zip") == "a" * 64
    assert listed(text, "electron-v44.5.1-win32-x64.zip") == "b" * 64
    assert listed(text, "electron-v44.5.1-darwin-x64.zip") is None and listed("", "x") is None


def test_the_network_is_the_checked_one():
    from ai_browser.desktop.download import download
    from ai_browser.hearing.model import urlopen_fetch

    assert inspect.signature(download).parameters["fetch"].default is urlopen_fetch  # certificates always checked
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_desktop_download.py -q -p no:randomly`

Expected: FAIL with `ModuleNotFoundError: No module named 'ai_browser.desktop.download'`.

- [ ] **Step 3: Write the download**

Create `src/ai_browser/desktop/download.py`:

```python
"""Electron's zip, fetched only after the user's yes (setup.py asks), and checked twice. The release's own
SHASUMS256.txt must list the pinned SHA-256 for it, and the zip must have the pinned size and that SHA-256. It is
written as <name>.part beside where it goes, and keeps its name only once checked. A mismatch, an error, a connection
that drops, or Ctrl-C keeps nothing."""

from __future__ import annotations

import contextlib
import hashlib
import http.client
import re
import shutil
import ssl
import urllib.error
from collections.abc import Callable
from pathlib import Path

from .. import platforms
from ..hearing.model import urlopen_fetch  # the same checked connection as the voice model's (truststore)
from .release import SHASUMS, Asset

PIECE = 1 << 20  # bytes read at a time
SUMS_LIMIT = 64_000  # bytes of SHASUMS256.txt read at most (6,740 for 44.5.1)
NEEDED = 1_000_000_000  # free disk space for the zip, Electron unpacked, and the app built from it
MISMATCH = "The download didn't match Electron's checksum: nothing was kept"
NOT_LISTED = "Electron's SHASUMS256.txt doesn't list the expected checksum: nothing was downloaded"
CUT = "The download stopped before the end: nothing was kept"
_LINE = re.compile(r"^([0-9a-f]{64}) [ *](.+)$")


class SetupError(Exception):
    """A setup step that failed, in plain words for the terminal and for Settings."""


def listed(text: str, name: str) -> str | None:
    """The SHA-256 SHASUMS256.txt lists for `name` (a "<hex> *<name>" or "<hex>  <name>" line), or None."""
    for line in text.splitlines():
        found = _LINE.match(line.strip())
        if found is not None and found.group(2) == name:
            return found.group(1)
    return None


def _plain(exc: BaseException) -> str | None:
    """A network or disk failure in plain words; None for anything else."""
    if isinstance(exc, urllib.error.HTTPError):
        return f"The download failed: GitHub answered {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        if isinstance(exc.reason, ssl.SSLError):
            return "The download failed: the connection to GitHub couldn't be checked"
        if isinstance(exc.reason, TimeoutError):
            return "The download stopped: the connection timed out"
        return "No internet connection"
    if isinstance(exc, TimeoutError):
        return "The download stopped: the connection timed out"
    if isinstance(exc, (ConnectionError, http.client.IncompleteRead)):
        return CUT
    if isinstance(exc, OSError):
        return f"The download failed: {exc.strerror or type(exc).__name__}"
    return None


def _small(fetch: Callable, url: str, limit: int) -> bytes:
    """A small file (SHASUMS256.txt), at most `limit` bytes."""
    try:
        with fetch(url) as answer:
            data = answer.read(limit + 1)
    except Exception as exc:
        said = _plain(exc)
        if said is None:
            raise
        raise SetupError(said) from None
    if len(data) > limit:
        raise SetupError(NOT_LISTED)
    return data


def _zip(asset: Asset, part: Path, fetch: Callable, progress: Callable[[int], None]) -> None:
    digest, size = hashlib.sha256(), 0
    try:
        with fetch(asset.url) as answer, open(part, "wb") as out:
            while piece := answer.read(PIECE):
                size += len(piece)
                if size > asset.size:
                    raise SetupError(MISMATCH)
                digest.update(piece)
                out.write(piece)
                progress(size)
    except SetupError:
        raise
    except Exception as exc:
        said = _plain(exc)
        if said is None:
            raise
        raise SetupError(said) from None
    if size < asset.size:
        raise SetupError(CUT)
    if digest.hexdigest() != asset.sha256:
        raise SetupError(MISMATCH)


def download(asset: Asset, folder: Path, fetch: Callable = urlopen_fetch,
             progress: Callable[[int], None] = lambda done: None) -> Path:
    """The checked zip at <folder>/<asset.name>. SetupError when anything fails: nothing is kept then, nor on Ctrl-C
    (KeyboardInterrupt goes on up). `progress` gets the bytes so far."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(folder).free < NEEDED:
        raise SetupError(f"Not enough free disk space: {NEEDED // 1_000_000_000} GB is needed")
    if listed(_small(fetch, SHASUMS, SUMS_LIMIT).decode("utf-8", "replace"), asset.name) != asset.sha256:
        raise SetupError(NOT_LISTED)
    final, part = folder / asset.name, folder / f"{asset.name}.part"
    for leftover in (final, part):
        platforms.unlink(leftover, missing_ok=True)
    try:
        _zip(asset, part, fetch, progress)
        platforms.replace(part, final)
    except BaseException:
        with contextlib.suppress(OSError):
            platforms.unlink(part, missing_ok=True)
        raise
    return final
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_desktop_download.py tests/test_portable.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/desktop/download.py tests/fake_electron_zip.py tests/test_desktop_download.py
git commit -m "feat(desktop): Electron's zip, downloaded and checked against SHASUMS256.txt, or nothing kept"
```

### Task 3: Unpacking Electron with its links, and turning its Node fuses off

**Files:**
- Create: `src/ai_browser/desktop/unpack.py`
- Create: `src/ai_browser/desktop/fuses.py`
- Modify: `tests/fake_electron_zip.py` (Electron's two layouts, in miniature)
- Test: `tests/test_desktop_unpack.py` (new)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - **`unpack.py`:** `UnpackError(Exception)` and `unpack(archive: Path, dest: Path) -> None`. `dest` must not exist yet
    (`FileExistsError`). Files keep their executable bits, links stay links, and nothing lands outside `dest`.
  - **`fuses.py`:**
    - `SENTINEL`, `OFF = (0, 2, 3)` (runAsNode, nodeOptions, nodeCliInspect) and `FuseError(Exception)`;
    - `wires(data) -> list[int]`, for bytes or an mmap;
    - `lock_down(binary: Path) -> None`: in place, every wire checked before any byte changes;
    - `states(binary: Path) -> list[str]`: each wire as text, such as "000000011".
  - **`tests/fake_electron_zip.py`:** `SENTINEL`, `WIRE` (Electron 44's fuses as shipped, "101100011"), `FRAMEWORK`,
    `PLIST`, `add_file(archive, name, data, mode=0o644)`, `add_link(archive, name, target)`,
    `mac_zip(wire=WIRE) -> bytes` and `windows_zip(wire=WIRE) -> bytes`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/fake_electron_zip.py`, after its imports (add `import stat` and `import zipfile` to them):

```python
SENTINEL = b"dL7pKGdnNz796PbbjQWNKmHXBZaB9tsX"  # Electron's fuse wire starts after it (desktop/fuses.py)
WIRE = SENTINEL + bytes([1, 9]) + b"101100011"  # Electron 44's fuses as it ships them: runAsNode, nodeOptions and
#                                                 nodeCliInspect on
FRAMEWORK = "Electron.app/Contents/Frameworks/Electron Framework.framework"
PLIST = (b'<?xml version="1.0" encoding="UTF-8"?>\n'
         b'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
         b'<plist version="1.0"><dict>'
         b"<key>CFBundleExecutable</key><string>Electron</string>"
         b"<key>CFBundleIconFile</key><string>electron.icns</string>"
         b"<key>CFBundleIconName</key><string>AppIcon</string>"  # an asset catalog's icon, which macOS prefers
         b"<key>CFBundleIdentifier</key><string>com.github.Electron</string>"
         b"<key>CFBundleName</key><string>Electron</string>"
         b"<key>CFBundleShortVersionString</key><string>44.5.1</string>"
         b"</dict></plist>\n")
WHEN = (2026, 10, 4, 0, 0, 0)


def add_file(archive: zipfile.ZipFile, name: str, data: bytes, mode: int = 0o644) -> None:
    info = zipfile.ZipInfo(name, WHEN)
    info.external_attr = (stat.S_IFREG | mode) << 16
    archive.writestr(info, data, zipfile.ZIP_DEFLATED)


def add_link(archive: zipfile.ZipFile, name: str, target: str) -> None:
    """A symbolic link, stored as zip stores one: its mode says link, and its content is the target."""
    info = zipfile.ZipInfo(name, WHEN)
    info.external_attr = (stat.S_IFLNK | 0o755) << 16
    archive.writestr(info, target.encode("utf-8"))


def mac_zip(wire: bytes = WIRE) -> bytes:
    """Electron's darwin zip, in miniature. Electron.app has its program, its Info.plist, its default app and its
    icon. Its framework's binary holds the fuses and is reached through links, as in the real one."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        add_file(archive, "Electron.app/Contents/Info.plist", PLIST)
        add_file(archive, "Electron.app/Contents/MacOS/Electron", b"\xcf\xfa\xed\xfe the program", 0o755)
        add_file(archive, "Electron.app/Contents/Resources/default_app.asar", b"Electron's own app")
        add_file(archive, "Electron.app/Contents/Resources/electron.icns", b"Electron's icon")
        add_file(archive, f"{FRAMEWORK}/Versions/A/Electron Framework", b"\x00framework\x00" + wire + b"\x00rest",
                 0o755)
        add_file(archive, f"{FRAMEWORK}/Versions/A/Resources/Info.plist", PLIST)
        add_link(archive, f"{FRAMEWORK}/Versions/Current", "A")
        add_link(archive, f"{FRAMEWORK}/Electron Framework", "Versions/Current/Electron Framework")
        add_link(archive, f"{FRAMEWORK}/Resources", "Versions/Current/Resources")
        add_file(archive, "LICENSE", b"MIT")
        add_file(archive, "version", b"44.5.1")
    return buffer.getvalue()


def windows_zip(wire: bytes = WIRE) -> bytes:
    """Electron's win32-x64 zip, in miniature: electron.exe holds the fuses."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        add_file(archive, "electron.exe", b"MZ the program\x00" + wire + b"\x00rest")
        add_file(archive, "resources/default_app.asar", b"Electron's own app")
        add_file(archive, "ffmpeg.dll", b"MZ a library")
        add_file(archive, "LICENSE", b"MIT")
        add_file(archive, "version", b"44.5.1")
    return buffer.getvalue()
```

Create `tests/test_desktop_unpack.py`:

```python
"""Electron's zip unpacked with its links and executable bits (desktop/unpack.py), and its Node fuses turned off
(desktop/fuses.py), on miniature zips with Electron's own layout (tests/fake_electron_zip.py)."""

import io
import os
import stat
import zipfile

import pytest

from fake_electron_zip import FRAMEWORK, WIRE, add_file, add_link, mac_zip, windows_zip


def zipped(tmp_path, data: bytes, name: str = "electron.zip"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


@pytest.mark.posix_only  # links, and executable bits
def test_links_and_executable_bits_come_out_as_they_went_in(tmp_path):
    from ai_browser.desktop.unpack import unpack

    unpack(zipped(tmp_path, mac_zip()), tmp_path / "out")
    app, framework = tmp_path / "out" / "Electron.app", tmp_path / "out" / FRAMEWORK
    assert os.readlink(framework / "Versions" / "Current") == "A"
    assert os.readlink(framework / "Electron Framework") == "Versions/Current/Electron Framework"
    assert (framework / "Electron Framework").read_bytes().startswith(b"\x00framework\x00")  # through the links
    assert os.access(app / "Contents" / "MacOS" / "Electron", os.X_OK)
    assert not os.access(app / "Contents" / "Info.plist", os.X_OK)


def test_the_windows_zip_comes_out_as_files(tmp_path):
    from ai_browser.desktop.unpack import unpack

    unpack(zipped(tmp_path, windows_zip()), tmp_path / "out")
    assert (tmp_path / "out" / "electron.exe").read_bytes().count(WIRE) == 1
    assert (tmp_path / "out" / "resources" / "default_app.asar").is_file()


@pytest.mark.posix_only
def test_nothing_lands_outside_the_folder(tmp_path):
    from ai_browser.desktop.unpack import UnpackError, unpack

    for name, kind, entry, value in (("dots", "file", "../outside.txt", b"x"),
                                     ("link-out", "link", "evil", "../.."),
                                     ("absolute-link", "link", "evil", "/etc")):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            (add_file if kind == "file" else add_link)(archive, entry, value)
        with pytest.raises(UnpackError):
            unpack(zipped(tmp_path, buffer.getvalue(), f"{name}.zip"), tmp_path / name)
    assert not (tmp_path / "outside.txt").exists()


def test_a_broken_zip_and_a_folder_already_there_are_refused(tmp_path):
    from ai_browser.desktop.unpack import UnpackError, unpack

    with pytest.raises(UnpackError, match="^Electron's zip can't be read$"):
        unpack(zipped(tmp_path, b"not a zip"), tmp_path / "out")
    with pytest.raises(FileExistsError):
        unpack(zipped(tmp_path, windows_zip(), "again.zip"), tmp_path / "out")  # "out" is there from the first try


def test_the_node_fuses_go_off_and_the_rest_stay(tmp_path):
    from ai_browser.desktop import fuses

    binary = tmp_path / "Electron Framework"
    binary.write_bytes(b"\x00head\x00" + WIRE + b"\x00tail")
    binary.chmod(0o755)
    assert fuses.states(binary) == ["101100011"]  # as Electron ships it
    fuses.lock_down(binary)
    assert fuses.states(binary) == ["000000011"]  # runAsNode, nodeOptions and nodeCliInspect off
    fuses.lock_down(binary)  # again: nothing changes
    assert fuses.states(binary) == ["000000011"]
    data = binary.read_bytes()
    assert data.startswith(b"\x00head\x00") and data.endswith(b"\x00tail")
    if os.name != "nt":
        assert stat.S_IMODE(binary.stat().st_mode) == 0o755


def test_a_removed_fuse_stays_removed_and_two_wires_both_go_off(tmp_path):
    from ai_browser.desktop import fuses

    binary = tmp_path / "universal"
    removed = WIRE[:-9] + b"r01100011"  # runAsNode removed from this build
    binary.write_bytes(WIRE + b"\x00between\x00" + removed)
    fuses.lock_down(binary)
    assert fuses.states(binary) == ["000000011", "r00000011"]


def test_fuses_that_cant_be_read_stop_everything_and_change_nothing(tmp_path):
    from ai_browser.desktop import fuses

    sentinel = fuses.SENTINEL
    for data, said in ((b"no fuses here", "no fuses"),
                       (sentinel + bytes([2, 9]) + b"101100011", "doesn't know"),  # a newer wire version
                       (sentinel + bytes([1, 3]) + b"101", "doesn't know"),  # too short for nodeCliInspect
                       (sentinel + bytes([1, 9]) + b"10110x011", "doesn't know"),  # not a fuse state
                       (sentinel + bytes([1, 9]) + b"1011", "doesn't know"),  # cut off
                       (b"", "no fuses")):  # an empty file
        binary = tmp_path / "binary"
        binary.write_bytes(data)
        with pytest.raises(fuses.FuseError, match=said):
            fuses.lock_down(binary)
        assert binary.read_bytes() == data
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_desktop_unpack.py -q -p no:randomly`

Expected: FAIL with `ModuleNotFoundError: No module named 'ai_browser.desktop.unpack'` (and `...fuses`).

- [ ] **Step 3: Write the unpacking and the fuses**

Create `src/ai_browser/desktop/unpack.py`:

```python
"""Electron's zip, unpacked into a new folder: every file with its executable bits, and every symbolic link as a link.
A Mac app's frameworks are built of links, and Python's zipfile alone would write each one as a small text file. An
entry that would land outside the folder, or a link that points outside it, stops everything. The zip was checked
against Electron's checksums first, so that never happens with Electron's own."""

from __future__ import annotations

import os
import shutil
import stat
import zipfile
from pathlib import Path

PIECE = 1 << 20
LIMIT = 2_000_000_000  # bytes unpacked at most (Electron 44 unpacks to about 400 MB)


class UnpackError(Exception):
    """The zip can't be unpacked safely; the message says why, in plain words."""


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def unpack(archive: Path, dest: Path) -> None:
    """Every entry of `archive` under `dest`, which must not exist yet (FileExistsError). UnpackError when it can't
    be done safely. What was written stays in `dest`, for the caller to remove."""
    dest = Path(dest)
    dest.mkdir(parents=True)
    root = os.path.realpath(dest)
    try:
        with zipfile.ZipFile(archive) as zipped:
            entries = zipped.infolist()
            if sum(entry.file_size for entry in entries) > LIMIT:
                raise UnpackError("Electron's zip is larger than expected")
            for entry in entries:
                _one(zipped, entry, root)
    except zipfile.BadZipFile:
        raise UnpackError("Electron's zip can't be read") from None


def _one(zipped: zipfile.ZipFile, entry: zipfile.ZipInfo, root: str) -> None:
    place = os.path.join(root, *entry.filename.split("/"))
    if not _inside(os.path.realpath(place), root):  # realpath follows the links unpacked so far
        raise UnpackError(f"Electron's zip has an entry outside its folder: {entry.filename}")
    if entry.is_dir():
        os.makedirs(place, exist_ok=True)
        return
    os.makedirs(os.path.dirname(place), exist_ok=True)
    mode = entry.external_attr >> 16
    if stat.S_ISLNK(mode):
        target = zipped.read(entry).decode("utf-8")
        if os.path.isabs(target) or not _inside(os.path.realpath(os.path.join(os.path.dirname(place), target)), root):
            raise UnpackError(f"Electron's zip has a link outside its folder: {entry.filename}")
        os.symlink(target, place)
        return
    with zipped.open(entry) as source, open(place, "wb") as out:
        shutil.copyfileobj(source, out, PIECE)
    if mode & 0o111:
        os.chmod(place, (mode & 0o777) | 0o200)  # a program stays one (and its owner may replace it)
```

Create `src/ai_browser/desktop/fuses.py`:

```python
"""Electron's fuses, set in AI Browser's own copy before it is signed. Fuses are switches built into the Electron
binary that no command line and no environment variable can turn back on. AI Browser turns off the three that would
let another program borrow the app, with the microphone and Brave permissions macOS gives it: running it as plain
Node.js, NODE_OPTIONS, and Node's inspector switches. The wire sits right after a fixed sentinel:
| sentinel | version (1) | length | one byte per fuse: "0" off, "1" on, "r" removed |
On macOS it is in the Electron Framework binary, on Windows in the program itself (layout.py)."""

from __future__ import annotations

import mmap
from pathlib import Path

SENTINEL = b"dL7pKGdnNz796PbbjQWNKmHXBZaB9tsX"
WIRE_VERSION = 1
RUN_AS_NODE, NODE_OPTIONS, NODE_CLI_INSPECT = 0, 2, 3  # Electron's fuse order (its docs: tutorial/fuses)
OFF = (RUN_AS_NODE, NODE_OPTIONS, NODE_CLI_INSPECT)
STATES = frozenset(b"01r")
NONE_FOUND = "This Electron build has no fuses: nothing was kept"
UNKNOWN = "This Electron build has fuses AI Browser doesn't know: nothing was kept"


class FuseError(Exception):
    """The binary's fuses can't be found or read, so the app isn't built (plain words)."""


def wires(data) -> list[int]:
    """Where each fuse wire starts (one per architecture in the binary), each one checked. FuseError when there is
    none, or one can't be read. `data` is bytes or an mmap."""
    found, start = [], 0
    while (at := data.find(SENTINEL, start)) != -1:
        head = at + len(SENTINEL)
        if head + 2 > len(data) or data[head] != WIRE_VERSION:
            raise FuseError(UNKNOWN)
        length, wire = data[head + 1], head + 2
        if length <= max(OFF) or wire + length > len(data) \
                or any(byte not in STATES for byte in data[wire:wire + length]):
            raise FuseError(UNKNOWN)
        found.append(wire)
        start = wire + length
    if not found:
        raise FuseError(NONE_FOUND)
    return found


def lock_down(binary: Path) -> None:
    """Turn the OFF fuses off in `binary`, in place: its other bytes and its file mode stay. Every wire is checked
    before any byte changes."""
    if Path(binary).stat().st_size == 0:
        raise FuseError(NONE_FOUND)
    with open(binary, "r+b") as handle, mmap.mmap(handle.fileno(), 0) as data:
        for wire in wires(data):
            for fuse in OFF:
                if data[wire + fuse] == ord("1"):
                    data[wire + fuse] = ord("0")
        data.flush()


def states(binary: Path) -> list[str]:
    """Each wire's fuses as text ("000000011"), for the tests."""
    if Path(binary).stat().st_size == 0:
        raise FuseError(NONE_FOUND)
    with open(binary, "rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
        return [data[wire:wire + data[wire - 1]].decode("ascii") for wire in wires(data)]
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_desktop_unpack.py tests/test_desktop_download.py tests/test_portable.py -q -p no:randomly`

Expected: PASS. On Windows the `posix_only` tests show as skipped.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/desktop/unpack.py src/ai_browser/desktop/fuses.py tests/fake_electron_zip.py tests/test_desktop_unpack.py
git commit -m "feat(desktop): Electron unpacked with its links, and its Node fuses turned off"
```

### Task 4: The app's rules and its line, as plain JavaScript tested under Node

**Files:**
- Create: `src/ai_browser/desktop/shortcut.py`
- Create: `src/ai_browser/desktop/electron/policy.js`
- Create: `src/ai_browser/desktop/electron/line.js`
- Test: `tests/test_desktop_js.py` (new)

**Interfaces:**
- Consumes: `config.LIVE_PORTS` (`range(8770, 8791)`).
- Produces:
  - **`desktop/shortcut.py`:**
    - `SHORTCUTS = ("Alt+Space", "Alt+Shift+Space", "Control+Shift+Space")`, `DEFAULT = "Alt+Space"` and
      `SHORTCUT_ERROR`;
    - `label(value, system=None) -> str`: "⌥⇧Space" on a Mac, "Alt+Shift+Space" elsewhere, "Off" for `None`;
    - `state(value, said: dict, running: bool) -> str`: one of "off", "taken", "ready", "works" or "unknown".
  - **`policy.js`** (CommonJS; `main.js` requires it in Task 5):
    - constants `LIVE_PORTS`, `SHORTCUTS` and `DEBUG_SWITCHES`;
    - `originOf(url)`, `startOrigin(open)` and `isLiveView(url)`;
    - `mayNavigate(url, own, isMainFrame)`;
    - `mayRequest(permission, details, own)` and `mayCheck(permission, requestingOrigin, details, own)`;
    - `shortcutOk(value)`, and `moveShortcut(keys, current, next, onPress) -> {registered, ok, why}`;
    - `notice(message) -> {id, title, body} | null`.
  - **`line.js`** (CommonJS): `LIMIT`, `parse(line)`, `splitter(onMessage) -> (chunk) => void`, `encode(message)` and
    `lineOption(argv) -> path | null`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_desktop_js.py`:

```python
"""AI Browser's own app's rules (desktop/electron/policy.js) and its line (line.js), run under Node.js: plain
functions with no Electron in them. Skipped where Node.js isn't installed, since the app itself never needs it. The
shortcuts' Python side (desktop/shortcut.py) needs no Node."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ELECTRON_DIR = Path(__file__).parents[1] / "src" / "ai_browser" / "desktop" / "electron"
NODE = shutil.which("node")
NEEDS_NODE = pytest.mark.skipif(NODE is None, reason="Node.js isn't installed (AI Browser's app never needs it)")
OWN = "http://127.0.0.1:8793"  # an app's own origin (a string only: no server listens)


def run_js(body: str):
    """`body` (JavaScript ending in a return) run with policy.js as `policy` and line.js as `line`; its value."""
    script = (f"const policy = require({json.dumps(str(ELECTRON_DIR / 'policy.js'))});\n"
              f"const line = require({json.dumps(str(ELECTRON_DIR / 'line.js'))});\n"
              f"const value = (() => {{ {body} }})();\n"
              "process.stdout.write(JSON.stringify(value === undefined ? null : value));")
    done = subprocess.run([NODE, "-e", script], capture_output=True, timeout=60)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    return json.loads(done.stdout.decode("utf-8"))


@NEEDS_NODE
def test_frames_go_only_to_our_pages_and_live_views():  # Review Focus 3
    cases = [  # (address, main frame, allowed)
        (f"{OWN}/app", True, True), (f"{OWN}/home", False, True), (f"{OWN}/open?code=x", True, True),
        ("https://example.com/", True, False), ("https://example.com/", False, False),
        ("http://127.0.0.1:8770/live?token=abc_DEF-1", False, True),
        ("http://127.0.0.1:8770/live?token=abc", True, False),  # a live view in a frame only, never the window
        ("http://127.0.0.1:8790/live?token=abc", False, True), ("http://127.0.0.1:8791/live?token=abc", False, False),
        ("http://127.0.0.1:8770/elsewhere", False, False), ("http://localhost:8793/app", True, False),
        ("http://127.0.0.1:8794/app", True, False), ("file:///etc/passwd", True, False),
        ("data:text/html,hi", False, False), ("javascript:alert(1)", True, False)]
    got = run_js("return " + json.dumps([[url, main] for url, main, _ in cases])
                 + f".map(([url, main]) => policy.mayNavigate(url, {json.dumps(OWN)}, main));")
    assert got == [allowed for _, _, allowed in cases]
    assert run_js(f"return [policy.mayNavigate('{OWN}/app', null, true), policy.mayNavigate('{OWN}/app', '', true),"
                  f" policy.mayNavigate('{OWN}/app', {json.dumps(OWN)}, undefined)];") == [False, False, True]


@NEEDS_NODE
def test_only_the_microphone_and_copying_are_allowed_and_only_for_our_pages():
    own = json.dumps(OWN)
    got = run_js(f"""
      const page = {{ requestingUrl: {json.dumps(OWN + '/mission')}, isMainFrame: false }};
      const live = {{ requestingUrl: 'http://127.0.0.1:8770/live?token=x', isMainFrame: false }};
      const others = ['notifications', 'geolocation', 'display-capture', 'openExternal', 'hid', 'fullscreen',
                      'clipboard-read', 'unknown'];
      return [
        policy.mayRequest('media', {{ ...page, mediaTypes: ['audio'] }}, {own}),
        policy.mayRequest('media', {{ ...page, mediaTypes: ['audio', 'video'] }}, {own}),
        policy.mayRequest('media', {{ ...page, mediaTypes: ['video'] }}, {own}),
        policy.mayRequest('media', {{ ...page, mediaTypes: [] }}, {own}),
        policy.mayRequest('media', {{ ...live, mediaTypes: ['audio'] }}, {own}),
        policy.mayRequest('media', {{ ...page, mediaTypes: ['audio'] }}, null),
        policy.mayRequest('clipboard-sanitized-write', page, {own}),
        policy.mayRequest('clipboard-sanitized-write', live, {own}),
        ...others.map((name) => policy.mayRequest(name, page, {own})),
        policy.mayCheck('media', {own}, {{ mediaType: 'audio' }}, {own}),
        policy.mayCheck('media', {own}, {{ mediaType: 'video' }}, {own}),
        policy.mayCheck('media', 'http://127.0.0.1:8770', {{ mediaType: 'audio' }}, {own}),
        policy.mayCheck('clipboard-sanitized-write', {own}, {{}}, {own}),
        ...others.map((name) => policy.mayCheck(name, {own}, {{}}, {own})),
      ];""")
    assert got == [True, False, False, False, False, False, True, False, *[False] * 8,
                   True, False, False, True, *[False] * 8]


@NEEDS_NODE
def test_the_start_address_must_be_the_engines_own():
    got = run_js("""return ['http://127.0.0.1:8793/open?code=abc', 'https://127.0.0.1:8793/open?code=abc',
      'http://localhost:8793/open?code=abc', 'http://127.0.0.1/open?code=abc', 'http://127.0.0.1:8793/home',
      'http://me:pw@127.0.0.1:8793/open?code=abc', 'not an address', null].map((open) => policy.startOrigin(open));""")
    assert got == [OWN, None, None, None, None, None, None, None]


@NEEDS_NODE
def test_a_taken_shortcut_keeps_the_one_before():  # Review Focus 1
    got = run_js("""
      const others = new Set(['Alt+Shift+Space']); // another app holds this one
      const mine = [];
      const keys = {
        register(accelerator) { if (others.has(accelerator)) return false; mine.push(accelerator); return true; },
        unregister(accelerator) { mine.splice(mine.indexOf(accelerator), 1); },
      };
      const press = () => {};
      const first = policy.moveShortcut(keys, null, 'Alt+Space', press);
      const taken = policy.moveShortcut(keys, first.registered, 'Alt+Shift+Space', press);
      const other = policy.moveShortcut(keys, taken.registered, 'Control+Shift+Space', press);
      const off = policy.moveShortcut(keys, other.registered, null, press);
      const unknown = policy.moveShortcut(keys, off.registered, 'A', press);
      const broken = policy.moveShortcut({ register() { throw new Error('no'); }, unregister() {} }, null,
                                         'Alt+Space', press);
      return [first, taken, other, off, unknown, broken, mine];""")
    assert got == [{"registered": "Alt+Space", "ok": True, "why": ""},
                   {"registered": "Alt+Space", "ok": False, "why": "taken"},  # the one before is back
                   {"registered": "Control+Shift+Space", "ok": True, "why": ""},
                   {"registered": None, "ok": True, "why": ""},
                   {"registered": None, "ok": False, "why": "unknown"},  # only the offered ones: never a bare key
                   {"registered": None, "ok": False, "why": "taken"},
                   []]


@NEEDS_NODE
def test_a_notification_is_only_what_the_engine_wrote():
    got = run_js("""return [
      policy.notice({ id: 'n1', title: 'An agent is waiting for you',
                      body: 'It asks to use a tool. Answer in AI Home.' }),
      policy.notice({ id: 'n2', title: 'A\\u0007 bot check\\non x', body: 'b'.repeat(500) }),
      policy.notice({ id: 'x1', title: 'no', body: '' }),
      policy.notice({ id: 'n3', title: '', body: 'only a body' }),
      policy.notice({ id: 'n4', title: 42 }),
      policy.notice(null),
    ];""")
    assert got[0] == {"id": "n1", "title": "An agent is waiting for you",
                      "body": "It asks to use a tool. Answer in AI Home."}
    assert got[1]["title"] == "A  bot check on x" and len(got[1]["body"]) == 240
    assert got[2:] == [None, None, None, None]


@NEEDS_NODE
def test_the_line_reads_whole_json_objects_and_drops_the_rest():
    got = run_js("""
      const seen = [];
      const feed = line.splitter((message) => seen.push(message));
      feed('{"type":"start","open":"x"}\\n{"type":"no');
      feed('tify","id":"n1"}\\n');
      feed('not json\\n[1,2]\\n{"no":"type"}\\n\\n');
      feed('{"type":"long","text":"' + 'x'.repeat(70000) + '"}\\n{"type":"after"}\\n');
      feed('{"type":"growing","text":"' + 'y'.repeat(70000));
      feed('"}\\n{"type":"next"}\\n');
      return [seen, line.encode({ type: 'hello', pid: 7 }), line.lineOption(['electron', '--aib-line=/t/line']),
              line.lineOption(['electron']), line.lineOption(['--aib-line=']), line.LIMIT];""")
    assert got[0] == [{"type": "start", "open": "x"}, {"type": "notify", "id": "n1"}, {"type": "after"},
                      {"type": "next"}]
    assert got[1:] == ['{"type":"hello","pid":7}\n', "/t/line", None, None, 65536]


@NEEDS_NODE
def test_the_app_and_the_engine_agree_on_the_shortcuts_and_the_live_views():
    from ai_browser.config import LIVE_PORTS
    from ai_browser.desktop.shortcut import SHORTCUTS

    assert run_js("return [policy.SHORTCUTS, policy.LIVE_PORTS];") == [list(SHORTCUTS),
                                                                      [LIVE_PORTS.start, LIVE_PORTS.stop - 1]]


def test_shortcuts_are_written_the_way_each_keyboard_says_them():
    from ai_browser.desktop.shortcut import DEFAULT, SHORTCUT_ERROR, SHORTCUTS, label, state

    assert SHORTCUTS == ("Alt+Space", "Alt+Shift+Space", "Control+Shift+Space") and DEFAULT == "Alt+Space"
    assert SHORTCUT_ERROR == "The shortcut must be one of the offered ones, or Off"
    assert [label(one, "darwin") for one in SHORTCUTS] == ["⌥Space", "⌥⇧Space", "⌃⇧Space"]
    assert [label(one, "win32") for one in SHORTCUTS] == ["Alt+Space", "Alt+Shift+Space", "Ctrl+Shift+Space"]
    assert label(None, "darwin") == label(None, "win32") == "Off"
    said = {"value": "Alt+Space", "ok": False, "why": "taken", "pressed": False}
    assert state("Alt+Space", said, True) == "taken"
    assert state("Alt+Space", {**said, "ok": True}, True) == "ready"
    assert state("Alt+Space", {**said, "ok": True, "pressed": True}, True) == "works"
    assert state("Alt+Space", said, False) == "unknown"  # the app isn't running: nobody holds it
    assert state("Alt+Space", {**said, "value": "Alt+Shift+Space"}, True) == "unknown"  # it said about another one
    assert state("Alt+Space", {}, True) == "unknown"  # it hasn't said yet
    assert state(None, said, True) == "off"
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_desktop_js.py -q -p no:randomly`

Expected: FAIL. Node can't find `policy.js` (`Cannot find module`), and `ModuleNotFoundError: No module named
'ai_browser.desktop.shortcut'`. Without Node.js, only the last test runs, and it fails the same way.

- [ ] **Step 3: Write the shortcuts, the rules and the line**

Create `src/ai_browser/desktop/shortcut.py`:

```python
"""The global shortcuts AI Browser's own app offers (Settings → AI Browser app), and how each is written: ⌥Space on a
Mac, Alt+Space elsewhere. policy.js lists the same values, in the same order (a test checks). None of them is a macOS
default: ⌃Space and ⌃⌥Space switch input sources there."""

from __future__ import annotations

import sys

SHORTCUTS = ("Alt+Space", "Alt+Shift+Space", "Control+Shift+Space")  # Electron accelerators
DEFAULT = "Alt+Space"
SHORTCUT_ERROR = "The shortcut must be one of the offered ones, or Off"
_MAC = {"Control": "⌃", "Alt": "⌥", "Shift": "⇧"}
_OTHER = {"Control": "Ctrl"}


def label(value: str | None, system: str | None = None) -> str:
    """How Settings writes a shortcut: "⌥⇧Space" on a Mac, "Alt+Shift+Space" elsewhere, "Off" for none."""
    if value is None:
        return "Off"
    keys = value.split("+")
    if (system or sys.platform) == "darwin":
        return "".join(_MAC.get(key, key) for key in keys)
    return "+".join(_OTHER.get(key, key) for key in keys)


def state(value: str | None, said: dict, running: bool) -> str:
    """What Settings says about the saved shortcut, from what the app said (`said`):
    - "off": no shortcut;
    - "taken": another app holds it;
    - "ready": the app holds it, and it hasn't been pressed yet;
    - "works": it was pressed;
    - "unknown": the app isn't running, or hasn't said yet."""
    if value is None:
        return "off"
    if not running or said.get("value") != value or said.get("ok") is None:
        return "unknown"
    if said.get("ok") is False:
        return "taken"
    return "works" if said.get("pressed") else "ready"
```

Create `src/ai_browser/desktop/electron/policy.js`:

```js
// What AI Browser's own app allows, as small functions main.js calls (and the tests run under Node.js): where a frame
// may go, which permission a page may have, which global shortcuts there are and how one is moved, what a
// notification may say, and which switches the packaged app refuses. Nothing here touches Electron, the network or
// the disk.
"use strict";

const LIVE_PORTS = [8770, 8790]; // an engine's live view binds one of these (config.LIVE_PORTS)
const LIVE = /^http:\/\/127\.0\.0\.1:(\d{4})\/live\?token=[A-Za-z0-9_-]{1,64}$/;
const SHORTCUTS = ["Alt+Space", "Alt+Shift+Space", "Control+Shift+Space"]; // desktop/shortcut.py's, in its order
const DEBUG_SWITCHES = ["remote-debugging-port", "remote-debugging-pipe", "remote-debugging-address",
  "remote-allow-origins", "inspect", "inspect-brk", "inspect-port", "js-flags", "auto-open-devtools-for-tabs"];
const NOTE_ID = /^n\d{1,9}$/;
const TITLE_LIMIT = 120;
const BODY_LIMIT = 240;
const CONTROL = /[\u0000-\u001f\u007f]/g;

function originOf(url) { // an http(s) address's origin, or null
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.origin : null;
  } catch {
    return null;
  }
}

// The app's own origin, from the start address the engine sent: http://127.0.0.1:<port>/open?code=…, nothing else.
function startOrigin(open) {
  let url;
  try {
    url = new URL(open);
  } catch {
    return null;
  }
  const ours = url.protocol === "http:" && url.hostname === "127.0.0.1" && url.port !== "" && url.pathname === "/open"
    && url.username === "" && url.password === "";
  return ours ? url.origin : null;
}

function isLiveView(url) { // an engine's live view (the tab menu shows one in a frame), on its own ports only
  const found = typeof url === "string" ? LIVE.exec(url) : null;
  return found !== null && Number(found[1]) >= LIVE_PORTS[0] && Number(found[1]) <= LIVE_PORTS[1];
}

// A frame may load AI Browser's own pages only; a frame inside our page (never the window itself) may also show an
// engine's live view. Anything else stays where it was: a website link goes to the user's own browser through the
// engine (open_url), never into this window. Before the engine's start (no `own`), nothing loads.
function mayNavigate(url, own, isMainFrame) {
  if (typeof own !== "string" || !own) return false;
  if (originOf(url) === own) return true;
  return isMainFrame === false && isLiveView(url);
}

// A permission request (setPermissionRequestHandler): the microphone alone (talking to the Brain), and writing to the
// clipboard (the Copy buttons), for AI Browser's own pages only. Everything else is refused, for everyone.
function mayRequest(permission, details, own) {
  if (!own || originOf(details?.requestingUrl) !== own) return false;
  if (permission === "media") {
    const types = Array.isArray(details?.mediaTypes) ? details.mediaTypes : [];
    return types.length > 0 && types.every((type) => type === "audio");
  }
  return permission === "clipboard-sanitized-write";
}

// The quiet check before a request (setPermissionCheckHandler, navigator.permissions.query): the same answers.
function mayCheck(permission, requestingOrigin, details, own) {
  if (!own || originOf(requestingOrigin) !== own) return false;
  if (permission === "media") return details?.mediaType === "audio";
  return permission === "clipboard-sanitized-write";
}

function shortcutOk(value) {
  return value === null || SHORTCUTS.includes(value);
}

function tryRegister(keys, accelerator, onPress) {
  try {
    return keys.register(accelerator, onPress) === true;
  } catch {
    return false;
  }
}

// Moving the global shortcut from `current` to `next`. When another app holds `next`, the one before comes back, so
// nothing is lost by trying. `keys` is Electron's globalShortcut (or a test's stand-in). `registered` is what the app
// holds afterwards.
function moveShortcut(keys, current, next, onPress) {
  if (!shortcutOk(next)) return { registered: current, ok: false, why: "unknown" };
  if (current) keys.unregister(current);
  if (next === null) return { registered: null, ok: true, why: "" };
  if (tryRegister(keys, next, onPress)) return { registered: next, ok: true, why: "" };
  const back = current && tryRegister(keys, current, onPress) ? current : null;
  return { registered: back, ok: false, why: "taken" };
}

// A notification exactly as the engine wrote it: its id, a title and a body, as plain text, cut to length. Nothing
// else reaches the screen. null when it isn't one.
function notice(message) {
  if (!message || typeof message.id !== "string" || !NOTE_ID.test(message.id)) return null;
  const text = (value, limit) => (typeof value === "string" ? value : "").replace(CONTROL, " ").trim().slice(0, limit);
  const title = text(message.title, TITLE_LIMIT);
  return title ? { id: message.id, title, body: text(message.body, BODY_LIMIT) } : null;
}

module.exports = {
  DEBUG_SWITCHES, LIVE_PORTS, SHORTCUTS, isLiveView, mayCheck, mayNavigate, mayRequest, moveShortcut, notice,
  originOf, shortcutOk, startOrigin,
};
```

Create `src/ai_browser/desktop/electron/line.js`:

```js
// The engine's private line to the app: one JSON object per line, each way. When the engine starts the program itself
// (Windows, and the tests' Electron) it is the app's stdin and stdout. When macOS starts the app through
// LaunchServices, it is a socket in a folder only this user can open: --aib-line=<path>. The start address, with its
// one-time code, comes this way, never on a command line.
"use strict";

const LIMIT = 64 * 1024; // characters in one line; a longer one is dropped

function parse(line) { // an object with a string "type", or null
  if (!line.trim() || line.length > LIMIT) return null;
  try {
    const message = JSON.parse(line);
    return message && typeof message === "object" && !Array.isArray(message) && typeof message.type === "string"
      ? message : null;
  } catch {
    return null;
  }
}

// Text as it comes (any chunks) to whole messages. A line that grows past LIMIT before its end is dropped whole.
function splitter(onMessage) {
  let buffer = "";
  let dropping = false;
  return (chunk) => {
    buffer += chunk;
    let end;
    while ((end = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, end);
      buffer = buffer.slice(end + 1);
      if (dropping) {
        dropping = false;
        continue;
      }
      const message = parse(line);
      if (message) onMessage(message);
    }
    if (buffer.length > LIMIT) {
      buffer = "";
      dropping = true;
    }
  };
}

function encode(message) {
  return `${JSON.stringify(message)}\n`;
}

function lineOption(argv) { // macOS: the socket's path; null: stdin and stdout
  const found = (argv || []).find((arg) => typeof arg === "string" && arg.startsWith("--aib-line="));
  return found ? found.slice("--aib-line=".length) || null : null;
}

module.exports = { LIMIT, encode, lineOption, parse, splitter };
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_desktop_js.py tests/test_portable.py -q -p no:randomly`

Expected: PASS. Without Node.js, the Node tests show as skipped with their reason.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/desktop/shortcut.py src/ai_browser/desktop/electron/policy.js src/ai_browser/desktop/electron/line.js tests/test_desktop_js.py
git commit -m "feat(desktop): the app's rules and its line as plain JavaScript, tested under Node"
```

### Task 5: The Electron app: a locked-down window, the menu-bar icon, the shortcut and notifications

**Files:**
- Create: `src/ai_browser/desktop/electron/main.js`
- Create: `src/ai_browser/desktop/electron/preload.js`
- Create: `src/ai_browser/desktop/electron/package.json`
- Create: `src/ai_browser/desktop/stage.py`
- Test: `tests/test_desktop_static.py` (new), `tests/test_desktop_electron.py` (new)

**Interfaces:**
- Consumes: Task 4's `policy.js` and `line.js`; `app/ui/icon.png`.
- Produces:
  - **`stage.py`:** `ELECTRON` (the `desktop/electron/` folder), `ICON` (`app/ui/icon.png`),
    `APP_FILES = ("package.json", "main.js", "preload.js", "policy.js", "line.js")`, `stage_app(dest)` (`dest` then
    holds exactly those files and `icon.png`) and `part_hash(extra: bytes = b"") -> str`.
  - **The app's command line:** the program, plus `--aib-line=<path>` on macOS. A test's unpackaged Electron gets
    `<app folder> --aib-profile=<folder>` (and the test's own `--remote-debugging-port`).
  - **The line, the engine to the app:**
    - `start {open, shortcut}`, which must come first;
    - `shortcut {value, request}`, `notify {id, title, body}`, `show` and `quit`.
  - **The line, the app to the engine:**
    - `hello {pid}`;
    - `shortcut {value, ok, why, pressed, request?}`, where `pressed: true` comes once, at its first press;
    - `clicked {id}`, and `quit` (the user's Quit).
  - **The seams for part c:** `main.js`'s `windows`, `makeWindow(kind, options)` and `showWindow(kind)`;
    `preload.js`'s `ACTIONS` list and `main.js`'s `ACTIONS` map, both empty.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_desktop_static.py`:

```python
"""AI Browser's own app, read as files. There is no debugging and no DevTools anywhere in it, every window is locked
down, the bridge holds named actions only, and there is no npm package. A real Electron drives it in
test_desktop_electron.py, when there is one."""

import json
import re
from pathlib import Path

ELECTRON_DIR = Path(__file__).parents[1] / "src" / "ai_browser" / "desktop" / "electron"
SRC = Path(__file__).parents[1] / "src" / "ai_browser"
APP_FILES = ("package.json", "main.js", "preload.js", "policy.js", "line.js")
REFUSED_LIST = re.compile(r"const DEBUG_SWITCHES = \[([^\]]*)\];")
NEVER = ("openDevTools", "remote-debugging", "appendSwitch", "--inspect", "devTools: true", ".debugger",
         "nodeIntegration: true", "contextIsolation: false", "sandbox: false", "webSecurity: false",
         "allowRunningInsecureContent: true", "webviewTag: true", "nodeIntegrationInSubFrames: true", "openExternal",
         "ELECTRON_RUN_AS_NODE", "enableBlinkFeatures", "experimentalFeatures", "console.", "remote-allow-origins",
         "inspect-brk", "js-flags")


def text(name: str) -> str:
    return (ELECTRON_DIR / name).read_text(encoding="utf-8")


def test_the_app_never_turns_debugging_on():
    assert sorted(path.name for path in ELECTRON_DIR.iterdir() if not path.name.startswith(".")) == sorted(APP_FILES)
    for name in APP_FILES:
        source = REFUSED_LIST.sub("", text(name))  # policy.js names the debugging switches only to refuse them
        for word in NEVER:
            assert word not in source, (name, word)
    refused = set(re.findall(r'"([a-z-]+)"', REFUSED_LIST.search(text("policy.js")).group(1)))
    assert {"remote-debugging-port", "remote-debugging-pipe", "inspect", "inspect-brk", "js-flags"} <= refused
    assert re.search(r"if \(app\.isPackaged && policy\.DEBUG_SWITCHES\.some\(\(name\) => "
                     r"app\.commandLine\.hasSwitch\(name\)\)\) \{\n  app\.exit\(1\);[^\n]*\n\} else \{\n  main\(\);\n"
                     r"\}\n$", text("main.js"))  # the packaged app's very first step


def test_every_window_is_locked_down():
    main = text("main.js")
    web = re.search(r"const WEB = Object\.freeze\(\{(.*?)\n\}\);", main, re.S).group(1)
    for setting in ("contextIsolation: true", "sandbox: true", "nodeIntegration: false",
                    "nodeIntegrationInWorker: false", "nodeIntegrationInSubFrames: false", "webSecurity: true",
                    "allowRunningInsecureContent: false", "webviewTag: false", "devTools: false",
                    "navigateOnDragDrop: false"):
        assert setting in web, setting
    assert main.count("new BrowserWindow(") == 1 and "webPreferences: { ...WEB }" in main  # every one: makeWindow
    for needed in ('contents.setWindowOpenHandler(() => ({ action: "deny" }))',
                   '["will-navigate", "will-frame-navigate", "will-redirect"]',
                   "policy.mayNavigate(details.url, own, details.isMainFrame)", "setPermissionRequestHandler",
                   "policy.mayRequest(permission, details, own)", "setPermissionCheckHandler",
                   "setDevicePermissionHandler(() => false)", '"will-download"', '"will-attach-webview"',
                   "requestSingleInstanceLock()", 'app.on("web-contents-created"', "policy.startOrigin(message.open)"):
        assert needed in main, needed


def test_the_bridge_holds_named_actions_only():
    preload, main = text("preload.js"), text("main.js")
    assert preload.count("exposeInMainWorld(") == 1
    assert 'contextBridge.exposeInMainWorld("aib", Object.freeze(bridge));' in preload
    assert "const ACTIONS = [];" in preload and "const ACTIONS = new Map();" in main  # part c adds chat, thisPage
    assert "ipcRenderer.invoke(`aib:${name}`, ...args)" in preload
    assert re.findall(r'require\("([^"]+)"\)', preload) == ["electron"]  # a sandboxed preload: the bridge alone
    assert "frame !== event.sender.mainFrame || policy.originOf(frame.url) !== own" in main


def test_no_npm_package_at_run_time():
    package = json.loads(text("package.json"))
    assert package["main"] == "main.js" and package["productName"] == "AI Browser" and package["private"] is True
    assert not {"dependencies", "devDependencies", "optionalDependencies", "scripts"} & set(package)
    for name in ("main.js", "preload.js", "policy.js", "line.js"):
        modules = set(re.findall(r'require\("([^"]+)"\)', text(name)))
        assert modules <= {"electron", "node:fs", "node:net", "node:path", "./policy.js", "./line.js"}, (name, modules)


def test_the_menu_bar_icon_closing_and_quitting():  # Review Focus 4
    main = text("main.js")
    for item in ('label: "Open AI Browser"', 'label: "Show chat", enabled: false', 'label: "Quit"'):
        assert item in main, item
    assert 'win.on("close", (event) => {' in main and "win.hide();" in main  # closing hides it
    assert 'send({ type: "quit" })' in main  # Quit tells the engine
    assert re.search(r"\}, \(\) => \{\n    clearTimeout\(waiting\);\n    if \(started\) \{\n      engineQuit = true;\n"
                     r"      app\.quit\(\);", main)  # the line's end (the engine gone) quits the app
    assert main.count("new Notification(") == 1 and "policy.notice(message)" in main  # the engine's words only
    assert "if (!app.isPackaged) return;" in main  # a test's Electron never adds a Start menu entry


def test_staging_copies_exactly_the_apps_files(tmp_path):
    from ai_browser.desktop.stage import APP_FILES as STAGED
    from ai_browser.desktop.stage import ELECTRON, ICON, part_hash, stage_app

    assert STAGED == APP_FILES and ELECTRON == ELECTRON_DIR and ICON == SRC / "app" / "ui" / "icon.png"
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "old.js").write_text("// from before", encoding="utf-8")
    stage_app(tmp_path / "app")
    assert sorted(path.name for path in (tmp_path / "app").iterdir()) == sorted([*APP_FILES, "icon.png"])
    assert (tmp_path / "app" / "icon.png").read_bytes() == ICON.read_bytes()
    assert part_hash() == part_hash() and part_hash(b"x") != part_hash()
```

Create `tests/test_desktop_electron.py`:

```python
"""AI Browser's own app on a real Electron, only when AIB_TEST_ELECTRON names an Electron 44 program (an Electron.app's
Contents/MacOS/Electron, or electron.exe); skipped otherwise. Nobody downloads Electron for these: the user may point
them at one they have. The test starts that Electron itself, unpackaged, on a throwaway profile. Chromium's
--remote-debugging-port goes on the TEST's command line, to look inside. The packaged app refuses that switch (Task 6
checks it). A window shows for a moment. No test here registers a global shortcut, and none touches the user's own AI
Browser, Brave or Chrome."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ELECTRON = os.environ.get("AIB_TEST_ELECTRON", "")
REAL = pytest.mark.skipif(not ELECTRON or not Path(ELECTRON).is_file(),
                          reason="set AIB_TEST_ELECTRON to an Electron 44 program to drive the real app")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def browser_ws(port: int, seconds: float = 30) -> str:
    """The DevTools address of the test's Electron (its --remote-debugging-port), once it answers."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(int(seconds * 10)):
        try:
            with opener.open(f"http://127.0.0.1:{port}/json/version", timeout=1) as answer:
                return json.loads(answer.read().decode("utf-8"))["webSocketDebuggerUrl"]
        except OSError:
            time.sleep(0.1)
    raise AssertionError("the test's Electron never opened its debugging port")


async def page_at(cdp, url: str, seconds: float = 30) -> str:
    for _ in range(int(seconds * 10)):
        infos = (await cdp.send("Target.getTargets"))["targetInfos"]
        found = [info["targetId"] for info in infos if info["type"] == "page" and info["url"] == url]
        if found:
            return found[0]
        await asyncio.sleep(0.1)
    raise AssertionError(f"no page at {url}")


async def started_app(tmp_path, server, url):
    """The test's Electron on the staged app, its start message sent and its hello read: (process, port)."""
    from ai_browser.desktop.stage import stage_app

    stage_app(tmp_path / "app")
    port = free_port()
    process = subprocess.Popen([ELECTRON, str(tmp_path / "app"), f"--aib-profile={tmp_path / 'profile'}",
                                f"--remote-debugging-port={port}"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)
    start = {"type": "start", "open": f"{url}/open?code={server.new_launch_code()}", "shortcut": None}
    process.stdin.write((json.dumps(start) + "\n").encode("utf-8"))
    process.stdin.flush()
    hello = json.loads(await asyncio.wait_for(asyncio.to_thread(process.stdout.readline), 60))
    assert hello == {"type": "hello", "pid": process.pid}
    return process, port


@REAL
async def test_the_real_app_is_locked_down(fake_claude, tmp_path):  # Review Focus 3
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer
    from ai_browser.cdp import CDP
    from test_home import page_js, until
    from test_tab_menu import connected, frame

    runner, _, _ = fake_claude
    server = AppServer(tmp_path / "home", AgentManager(tmp_path / "home", claude=runner))
    url = await server.start()  # never 8792 (conftest)
    process, cdp = None, None
    try:
        process, port = await started_app(tmp_path, server, url)
        cdp = await CDP.connect(await asyncio.to_thread(browser_ws, port))
        js = await page_js(cdp, await page_at(cdp, url + "/app"))
        assert await until(js, connected("/home"), seconds=30)  # the tab menu, and AI Home's line to the engine
        assert await js("typeof require === 'undefined' && typeof process === 'undefined'")  # no Node.js in pages
        assert await js("JSON.stringify(Object.keys(window.aib))") == "[]"  # the bridge: no action in part a
        assert await js(f"typeof {frame('/home')}.aib") == "undefined"  # framed pages get no bridge at all
        assert await js("window.open('https://example.com/') === null")  # no window opens another
        await js("location.href = 'https://example.com/'; true")  # a website, in the window itself: refused
        await js(f"{frame('/home')}.location.href = 'https://example.com/'; true")  # and in a frame
        await asyncio.sleep(1.5)
        assert await js("location.href") == url + "/app"
        assert await js(f"{frame('/home')}.location.pathname") == "/home"
        ask = "navigator.permissions.query({name: '%s'}).then((answer) => answer.state)"
        assert await js(f"{frame('/home')}.{ask % 'microphone'}") == "granted"  # talking to the Brain
        assert await js(f"{frame('/home')}.{ask % 'camera'}") == "denied"
        assert await js(f"{frame('/home')}.{ask % 'geolocation'}") == "denied"
        process.stdin.write(b'{"type": "quit"}\n')  # the engine stops
        process.stdin.flush()
        assert await asyncio.to_thread(process.wait, 30) == 0
    finally:
        if cdp is not None:
            await cdp.close()
        if process is not None and process.poll() is None:
            process.kill()
        await server.stop()


@REAL
async def test_the_real_app_quits_when_the_engine_goes(fake_claude, tmp_path):  # Review Focus 4
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer

    runner, _, _ = fake_claude
    server = AppServer(tmp_path / "home", AgentManager(tmp_path / "home", claude=runner))
    url = await server.start()
    process = None
    try:
        process, _ = await started_app(tmp_path, server, url)
        process.stdin.close()  # the engine is gone, without a word: its line ends
        assert await asyncio.to_thread(process.wait, 30) == 0  # the app doesn't stay behind in the menu bar
    finally:
        if process is not None and process.poll() is None:
            process.kill()
        await server.stop()
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_desktop_static.py tests/test_desktop_electron.py -q -p no:randomly`

Expected:
- the static tests FAIL: the folder holds only `policy.js` and `line.js`, `main.js` is missing
  (`FileNotFoundError`), and there is `No module named 'ai_browser.desktop.stage'`;
- the real-Electron tests are SKIPPED (no `AIB_TEST_ELECTRON`).

- [ ] **Step 3: Write the app**

Create `src/ai_browser/desktop/electron/package.json`:

```json
{
  "name": "ai-browser-app",
  "productName": "AI Browser",
  "version": "0.1.0",
  "private": true,
  "description": "AI Browser's own app: its window, its menu-bar icon, its shortcut and its notifications. No npm package.",
  "main": "main.js"
}
```

Create `src/ai_browser/desktop/electron/preload.js`:

```js
// The bridge between AI Browser's pages and its app: named actions only, each answered by main.js's ACTIONS, for AI
// Browser's own top-level pages (anything else gets null). contextIsolation keeps this file's world apart from the
// page's, and the sandbox gives it no Node.js. Part a has no action for pages: the shortcut and notifications go
// through the engine, which the pages already talk to. The floating chat adds its own (part c), here and in main.js.
"use strict";

const { contextBridge, ipcRenderer } = require("electron");

const ACTIONS = []; // the names main.js's ACTIONS answers, in the same order
const bridge = {};
for (const name of ACTIONS) bridge[name] = (...args) => ipcRenderer.invoke(`aib:${name}`, ...args);
contextBridge.exposeInMainWorld("aib", Object.freeze(bridge));
```

Create `src/ai_browser/desktop/electron/main.js`:

```js
// AI Browser's own app (Electron). `ai-browser app` starts it (desktop/launch.py) and talks to it over one private
// line (line.js): the start address, with its one-time code, comes that way, never on a command line.
// - It shows the tab menu at http://127.0.0.1:<port>/app in a window locked down as policy.js says.
// - It keeps an icon in the menu bar (by the clock on Windows), and holds the shortcut picked in Settings (in part a
//   it shows and hides the window).
// - It shows the notifications the engine writes, word for word.
// Closing the window hides it. Quit ends the app and tells the engine, which stops too. When the engine goes, the app
// quits. The packaged app never runs with a debugging port or an inspector, and its pages never get DevTools.
"use strict";

const { app, BrowserWindow, Menu, Notification, Tray, dialog, globalShortcut, ipcMain, nativeImage, session, shell } =
  require("electron");
const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");
const policy = require("./policy.js");
const { encode, lineOption, splitter } = require("./line.js");

const APP_ID = "io.github.nanotechs001.ai-browser"; // desktop/layout.py's BUNDLE_ID, and Windows' AppUserModelID
const TOAST_CLSID = "{52E8D68C-5CAC-4680-848A-E80657E0B4D5}"; // Windows: the Start menu entry's toast activator
const PROFILE = "--aib-profile="; // an unpackaged Electron only (the tests'): its throwaway profile
const ICON = path.join(__dirname, "icon.png");
const START_WAIT = 20000; // ms for the engine's start message
const NOTES_KEPT = 20; // notifications whose click still reaches the engine
const WEB = Object.freeze({ // every window's webPreferences (makeWindow)
  contextIsolation: true,
  sandbox: true,
  nodeIntegration: false,
  nodeIntegrationInWorker: false,
  nodeIntegrationInSubFrames: false,
  webSecurity: true,
  allowRunningInsecureContent: false,
  webviewTag: false,
  devTools: false,
  spellcheck: false,
  navigateOnDragDrop: false,
  safeDialogs: true,
  autoplayPolicy: "no-user-gesture-required", // Mission Control speaks without a click first
  preload: path.join(__dirname, "preload.js"),
});
const ACTIONS = new Map(); // name -> handler: what a page may ask the app for (preload.js lists the same names)

const windows = new Map(); // "main" (the floating chat adds "chat")
const notes = new Map(); // id -> Notification, kept so a click still reaches us
let own = null; // the app's own origin, http://127.0.0.1:<port>, once the engine has started it
let send = () => false; // a message to the engine
let starting = false;
let started = false;
let quitting = false;
let engineQuit = false; // the engine asked for the quit, or went away: there is no one to tell
let shortcut = null; // the accelerator registered now
let pressed = false; // it fired since it was registered
let tray = null;

function profileFolder() { // <home>/desktop/profile, beside the app (a test's unpackaged Electron: its own)
  const given = process.argv.find((arg) => arg.startsWith(PROFILE));
  if (given && !app.isPackaged) return given.slice(PROFILE.length);
  const up = process.platform === "darwin" ? ["..", "..", "..", ".."] : ["..", ".."]; // out of the .app, or the folder
  return path.join(path.resolve(process.execPath, ...up), "profile");
}

function openLine(onMessage, onEnd) {
  const feed = splitter(onMessage);
  let ended = false;
  const end = () => {
    if (!ended) {
      ended = true;
      onEnd();
    }
  };
  const where = lineOption(process.argv);
  if (where) { // macOS: the socket the engine named
    const socket = net.createConnection({ path: where });
    socket.setEncoding("utf8");
    socket.on("data", feed);
    socket.on("close", end);
    socket.on("error", () => {}); // "close" follows
    send = (message) => !socket.destroyed && socket.write(encode(message));
    return;
  }
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", feed);
  process.stdin.on("end", end);
  process.stdin.on("error", end);
  process.stdout.on("error", () => {});
  send = (message) => {
    try {
      return process.stdout.write(encode(message));
    } catch {
      return false;
    }
  };
}

function noEngine() { // started by a double-click (Finder, the Start menu), with no `ai-browser app` behind it
  if (started) return;
  starting = true; // a start message coming now is too late
  app.whenReady().then(async () => {
    await dialog.showMessageBox({ type: "info", message: "Start AI Browser from a terminal",
                                  detail: "Run: uv run ai-browser app", buttons: ["OK"] });
    app.exit(0);
  });
}

function makeWindow(kind, options) { // every window: locked down the same way, kept by its kind
  const win = new BrowserWindow({ ...options, show: false, webPreferences: { ...WEB } });
  windows.set(kind, win);
  win.on("closed", () => windows.delete(kind));
  return win;
}

function showWindow(kind) {
  const win = windows.get(kind);
  if (!win) return;
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
  if (process.platform === "darwin") app.focus({ steal: true });
}

function toggleMain() { // the shortcut: AI Browser's window comes forward, or hides when it is in front
  if (!pressed) {
    pressed = true; // it works: Settings says so
    send({ type: "shortcut", value: shortcut, ok: true, why: "", pressed: true });
  }
  const win = windows.get("main");
  if (win && win.isVisible() && win.isFocused()) win.hide();
  else showWindow("main");
}

function useShortcut(value, request) { // move the global shortcut, and tell the engine how it went
  const result = policy.moveShortcut(globalShortcut, shortcut, value, toggleMain);
  if (result.registered !== shortcut) pressed = false;
  shortcut = result.registered;
  send({ type: "shortcut", value: value ?? null, ok: result.ok, why: result.why, pressed: false,
         ...(request ? { request } : {}) });
}

function lockContents(contents) { // every page, frame and window: AI Browser's own pages only
  contents.setWindowOpenHandler(() => ({ action: "deny" })); // no window opens another; a website goes to Brave
  contents.on("will-attach-webview", (event) => event.preventDefault());
  for (const name of ["will-navigate", "will-frame-navigate", "will-redirect"]) {
    contents.on(name, (details) => {
      if (!policy.mayNavigate(details.url, own, details.isMainFrame)) details.preventDefault();
    });
  }
}

function lockSession(ses) { // the microphone and copying, for AI Browser's own pages; nothing else, for anyone
  ses.setPermissionRequestHandler((contents, permission, callback, details) => {
    callback(policy.mayRequest(permission, details, own));
  });
  ses.setPermissionCheckHandler((contents, permission, requestingOrigin, details) =>
    policy.mayCheck(permission, requestingOrigin, details, own));
  ses.setDevicePermissionHandler(() => false);
  ses.on("will-download", (event) => event.preventDefault()); // nothing downloads here
}

function makeMenu() { // a Mac's menu bar: hiding, copy and paste, the window, Quit; Windows: a title bar only
  if (process.platform !== "darwin") {
    Menu.setApplicationMenu(null);
    return;
  }
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { label: "AI Browser", submenu: [{ role: "hide" }, { role: "hideOthers" }, { role: "unhide" },
                                     { type: "separator" }, { role: "quit" }] },
    { role: "editMenu" },
    { label: "Window", submenu: [{ role: "minimize" }, { role: "zoom" }, { type: "separator" }, { role: "close" }] },
  ]));
}

function makeTray() { // the menu-bar icon (by the clock on Windows)
  const size = process.platform === "darwin" ? 18 : 16;
  tray = new Tray(nativeImage.createFromPath(ICON).resize({ width: size, height: size }));
  tray.setToolTip("AI Browser");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Open AI Browser", click: () => showWindow("main") },
    { label: "Show chat", enabled: false }, // the floating chat: part c
    { type: "separator" },
    { label: "Quit", click: () => app.quit() },
  ]));
  if (process.platform === "win32") tray.on("click", () => showWindow("main"));
}

// Windows shows an app's notifications only when the Start menu has a shortcut to it with the same AppUserModelID and
// toast activator (setup's offer says so). Started from that entry, the app says to start AI Browser from a terminal.
function startMenuEntry() {
  if (!app.isPackaged) return;
  app.setAppUserModelId(APP_ID);
  app.setToastActivatorCLSID(TOAST_CLSID);
  const link = path.join(app.getPath("appData"), "Microsoft", "Windows", "Start Menu", "Programs", "AI Browser.lnk");
  const want = { target: process.execPath, appUserModelId: APP_ID, toastActivatorClsid: TOAST_CLSID,
                 description: "AI Browser" };
  let have = null;
  try {
    have = shell.readShortcutLink(link);
  } catch {
    have = null;
  }
  if (have && have.target === want.target && have.appUserModelId === APP_ID) return;
  try {
    shell.writeShortcutLink(link, have ? "replace" : "create", want);
  } catch {
    // without it Windows may not show the notifications; everything else works
  }
}

function notify(message) { // the engine's words, as written (policy.notice keeps text only, cut to length)
  const text = policy.notice(message);
  if (!text || !Notification.isSupported()) return;
  const note = new Notification({ title: text.title, body: text.body,
                                  ...(process.platform === "win32" ? { icon: ICON } : {}) });
  note.on("click", () => {
    notes.delete(text.id);
    send({ type: "clicked", id: text.id });
  });
  note.on("close", () => notes.delete(text.id));
  notes.set(text.id, note);
  while (notes.size > NOTES_KEPT) notes.delete(notes.keys().next().value);
  note.show();
}

function answerActions() { // each named action, for AI Browser's own top-level pages only
  for (const [name, handler] of ACTIONS) {
    ipcMain.handle(`aib:${name}`, (event, ...args) => {
      const frame = event.senderFrame;
      if (!frame || frame !== event.sender.mainFrame || policy.originOf(frame.url) !== own) return null;
      return handler(...args);
    });
  }
}

function begin(message) { // the engine's start: the window on its start address, the menu-bar icon, the shortcut
  own = policy.startOrigin(message.open);
  if (!own) {
    engineQuit = true;
    app.exit(1); // not the engine's own address: nothing loads
    return;
  }
  started = true;
  if (process.platform === "win32") startMenuEntry();
  makeTray();
  const win = makeWindow("main", { width: 1440, height: 960, minWidth: 720, minHeight: 480, title: "AI Browser",
                                   backgroundColor: "#faf9f5", icon: ICON });
  win.on("close", (event) => { // closing hides it: the app keeps running, and so do the agents
    if (!quitting) {
      event.preventDefault();
      win.hide();
    }
  });
  win.once("ready-to-show", () => showWindow("main"));
  win.loadURL(message.open).catch(() => {}); // a page that can't load: the engine says so (it waits for the page)
  send({ type: "hello", pid: process.pid });
  useShortcut(policy.shortcutOk(message.shortcut) ? message.shortcut : null, null);
}

function onEngine(message) {
  if (message.type === "notify") notify(message);
  else if (message.type === "show") showWindow("main");
  else if (message.type === "shortcut" && "value" in message) {
    useShortcut(message.value, typeof message.request === "string" ? message.request.slice(0, 40) : null);
  } else if (message.type === "quit") {
    engineQuit = true;
    app.quit();
  }
}

function main() {
  const profile = profileFolder();
  fs.mkdirSync(profile, { recursive: true });
  app.setPath("userData", profile);
  if (!app.requestSingleInstanceLock()) {
    app.exit(0); // one app per profile: the running one comes forward instead (second-instance)
    return;
  }
  app.on("second-instance", () => showWindow("main"));
  app.on("activate", () => showWindow("main")); // a click on the Dock icon
  app.on("before-quit", () => {
    quitting = true;
    if (!engineQuit) send({ type: "quit" });
  });
  app.on("will-quit", () => globalShortcut.unregisterAll());
  app.on("window-all-closed", () => {}); // only Quit ends the app
  app.on("web-contents-created", (event, contents) => lockContents(contents));
  const waiting = setTimeout(noEngine, START_WAIT);
  openLine((message) => {
    if (message.type === "start" && !starting) {
      starting = true;
      clearTimeout(waiting);
      app.whenReady().then(() => begin(message)).catch(() => app.exit(1)); // a broken start: the engine hears it
    } else if (started) {
      onEngine(message);
    }
  }, () => {
    clearTimeout(waiting);
    if (started) {
      engineQuit = true;
      app.quit();
    } else {
      noEngine();
    }
  });
  app.whenReady().then(() => {
    lockSession(session.defaultSession);
    makeMenu();
    answerActions();
  });
}

if (app.isPackaged && policy.DEBUG_SWITCHES.some((name) => app.commandLine.hasSwitch(name))) {
  app.exit(1); // the packaged app never runs with a debugging port or an inspector
} else {
  main();
}
```

Create `src/ai_browser/desktop/stage.py`:

```python
"""AI Browser's part of its own app: the JavaScript in desktop/electron/ and the icon, as they go into the app's
resources/app folder, and a hash of them, so a changed file is noticed (assemble.py adds the rest of what setup
changes to the hash)."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from .. import platforms

ELECTRON = Path(__file__).with_name("electron")
ICON = Path(__file__).parents[1] / "app" / "ui" / "icon.png"
APP_FILES = ("package.json", "main.js", "preload.js", "policy.js", "line.js")


def stage_app(dest: Path) -> None:
    """`dest` holds exactly the app's files and icon.png (whatever was there before goes)."""
    dest = Path(dest)
    if dest.exists():
        platforms.rmtree(dest)
    dest.mkdir(parents=True)
    for name in APP_FILES:
        shutil.copyfile(ELECTRON / name, dest / name)
    shutil.copyfile(ICON, dest / "icon.png")


def part_hash(extra: bytes = b"") -> str:
    """A SHA-256 over every file stage_app copies, and `extra`."""
    digest = hashlib.sha256()
    for name, path in [*((name, ELECTRON / name) for name in APP_FILES), ("icon.png", ICON)]:
        data = path.read_bytes()
        digest.update(f"{name}\0{len(data)}\0".encode("utf-8") + data)
    digest.update(extra)
    return digest.hexdigest()
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_desktop_static.py tests/test_desktop_electron.py tests/test_desktop_js.py tests/test_portable.py -q -p no:randomly`

Expected:
- the static, JS and portable tests PASS;
- the real-Electron tests are SKIPPED. With `AIB_TEST_ELECTRON` naming an Electron 44.5.1 program the user already
  has, they PASS, and a window shows for a moment. Nobody downloads one for this.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/desktop/electron/main.js src/ai_browser/desktop/electron/preload.js src/ai_browser/desktop/electron/package.json src/ai_browser/desktop/stage.py tests/test_desktop_static.py tests/test_desktop_electron.py
git commit -m "feat(desktop): the Electron app: a locked-down window, a menu-bar icon, the shortcut and notifications"
```

### Task 6: Building AI Browser.app (and Windows' AI Browser folder) from Electron, signed ad hoc

**Files:**
- Create: `src/ai_browser/desktop/assemble.py`
- Create: `tests/fake_tools.py`
- Test: `tests/test_desktop_assemble.py` (new)
- Modify: `tests/test_desktop_electron.py` (one test at the end)

**Interfaces:**
- Consumes:
  - Task 1's `layout` and `VERSION`; Task 2's `SetupError`;
  - Task 3's `fuses.lock_down` and `FuseError`;
  - Task 5's `stage_app`, `part_hash` and `ICON`;
  - `platforms.replace` and `platforms.rmtree`.
- Produces:
  - `PLIST`: the Info.plist values set on macOS;
  - `Tools(codesign=("codesign",), sips=("sips",))`, frozen: the commands, as argv prefixes;
  - `sign_command(tools, app) -> list[str]` and `icon_command(tools, png, icns) -> list[str]`;
  - `layer_hash(system) -> str` and `stale(home, system=None) -> bool`;
  - `build(electron, home, system=None, tools=Tools(), arch="", move=False) -> Path`. `electron` is the folder
    Electron's zip unpacks to. It returns the app's path, or raises `SetupError` and keeps nothing new.
  - `refresh(home, system=None, tools=Tools()) -> Path`: AI Browser's part again, with no download.
  - The work folder is `<home>/desktop/.build/`; the app is put in place only when complete.
  - The stamp is `{"electron", "system", "arch", "layer", "built"}`.
  - **`tests/fake_tools.py`:** `fake_tools(tmp_path, monkeypatch) -> (Tools, log path)` and
    `tool_runs(log) -> list[list[str]]`. Set `FAKE_TOOLS_FAIL=<tool>` and that tool fails.

- [ ] **Step 1: Write the failing tests**

Create `tests/fake_tools.py`:

```python
"""Stand-ins for macOS's codesign and sips, for setup's tests. Each run is logged with its exact argv (the tool's
name first) to FAKE_TOOLS_LOG. sips writes its --out file as sips would (here a copy of the PNG). FAKE_TOOLS_FAIL
names a tool that fails, as the real one would, with a line on stderr."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    name, args = argv[0], argv[1:]
    with open(os.environ["FAKE_TOOLS_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps([name, *args]) + "\n")
    if os.environ.get("FAKE_TOOLS_FAIL") == name:
        sys.stderr.write(f"{name}: fake failure\n")
        return 1
    if name == "sips":  # sips -s format icns <png> --out <icns>
        shutil.copyfile(args[3], args[args.index("--out") + 1])
    return 0


def fake_tools(tmp_path, monkeypatch):
    """(Tools that run this file instead of codesign and sips, the log they write)."""
    from ai_browser.desktop.assemble import Tools
    from conftest import fake_python

    log = tmp_path / "tools.log"
    monkeypatch.setenv("FAKE_TOOLS_LOG", str(log))
    me = str(Path(__file__).resolve())
    return Tools(codesign=(fake_python(), me, "codesign"), sips=(fake_python(), me, "sips")), log


def tool_runs(log: Path) -> list[list[str]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Create `tests/test_desktop_assemble.py`:

```python
"""Building AI Browser's own app from Electron's zip (desktop/assemble.py). The zips are miniatures with Electron's
layout (tests/fake_electron_zip.py), and codesign and sips are stand-ins (tests/fake_tools.py) whose exact command
lines are checked. Nothing is downloaded, and no real tool runs."""

import os
import plistlib

import pytest

from conftest import file_mode
from fake_electron_zip import mac_zip, windows_zip
from fake_tools import fake_tools, tool_runs


def unpacked(tmp_path, data: bytes):
    from ai_browser.desktop.unpack import unpack

    archive = tmp_path / "electron.zip"
    archive.write_bytes(data)
    unpack(archive, tmp_path / "electron")
    return tmp_path / "electron"


@pytest.mark.posix_only  # the Mac's zip holds symbolic links
def test_the_mac_app_gets_its_name_icon_javascript_fuses_and_signature(tmp_path, monkeypatch):
    from ai_browser.desktop import assemble, fuses, layout
    from ai_browser.desktop.release import VERSION
    from ai_browser.desktop.stage import APP_FILES, ELECTRON, ICON

    tools, log = fake_tools(tmp_path, monkeypatch)
    home = tmp_path / "home"
    app = assemble.build(unpacked(tmp_path, mac_zip()), home, "darwin", tools, arch="arm64", move=True)
    assert app == home / "desktop" / "AI Browser.app"
    with open(app / "Contents" / "Info.plist", "rb") as handle:
        info = plistlib.load(handle)
    assert {key: info[key] for key in assemble.PLIST} == assemble.PLIST
    assert (info["CFBundleName"], info["CFBundleDisplayName"]) == ("AI Browser", "AI Browser")
    assert info["CFBundleIdentifier"] == "io.github.nanotechs001.ai-browser"
    assert info["CFBundleExecutable"] == "Electron"  # Electron's own keys stay,
    assert "CFBundleIconName" not in info  # but not its asset catalog's icon, which macOS would show instead of ours
    resources = app / "Contents" / "Resources"
    assert sorted(path.name for path in (resources / "app").iterdir()) == sorted([*APP_FILES, "icon.png"])
    assert all((resources / "app" / name).read_bytes() == (ELECTRON / name).read_bytes() for name in APP_FILES)
    assert (resources / "AI Browser.icns").read_bytes() == ICON.read_bytes()  # the fake sips copies; sips converts
    assert not (resources / "default_app.asar").exists()  # Electron's own app can't run in AI Browser's place
    assert fuses.states(layout.framework(app)) == ["000000011"]  # runAsNode, nodeOptions, nodeCliInspect off
    current = app / "Contents" / "Frameworks" / "Electron Framework.framework" / "Versions" / "Current"
    assert current.is_symlink() and os.readlink(current) == "A"
    assert os.access(layout.executable(app, "darwin"), os.X_OK)
    building = home / "desktop" / ".build" / "AI Browser.app"
    assert tool_runs(log) == [
        ["sips", "-s", "format", "icns", str(ICON), "--out",
         str(building / "Contents" / "Resources" / "AI Browser.icns")],
        ["codesign", "--force", "--deep", "--sign", "-", str(building)]]  # signed last, once everything is in
    stamp = layout.stamp(home)
    assert {key: stamp[key] for key in ("electron", "system", "arch", "layer")} == {
        "electron": VERSION, "system": "darwin", "arch": "arm64", "layer": assemble.layer_hash("darwin")}
    assert file_mode(home / "desktop" / "app.json") in (0o600, None)
    assert sorted(path.name for path in (home / "desktop").iterdir()) == ["AI Browser.app", "app.json"]
    assert not (tmp_path / "electron" / "Electron.app").exists()  # moved, not copied


def test_the_windows_app_is_a_folder_with_ai_browser_exe(tmp_path, monkeypatch):
    from ai_browser.desktop import assemble, fuses, layout
    from ai_browser.desktop.stage import APP_FILES

    tools, log = fake_tools(tmp_path, monkeypatch)
    home = tmp_path / "home"
    app = assemble.build(unpacked(tmp_path, windows_zip()), home, "win32", tools, arch="x64", move=True)
    assert app == home / "desktop" / "AI Browser"
    assert (app / "AI Browser.exe").is_file() and not (app / "electron.exe").exists()
    assert sorted(path.name for path in (app / "resources" / "app").iterdir()) == sorted([*APP_FILES, "icon.png"])
    assert not (app / "resources" / "default_app.asar").exists()
    assert fuses.states(app / "AI Browser.exe") == ["000000011"]
    assert tool_runs(log) == []  # no icon tool and no signing: the .exe keeps Electron's icon in File Explorer
    assert layout.installed(home, "win32")["system"] == "win32"


@pytest.mark.posix_only
def test_a_failed_signature_keeps_the_app_that_was_there(tmp_path, monkeypatch):
    from ai_browser.desktop import assemble
    from ai_browser.desktop.download import SetupError

    tools, _ = fake_tools(tmp_path, monkeypatch)
    home = tmp_path / "home"
    before = home / "desktop" / "AI Browser.app"
    before.mkdir(parents=True)
    (before / "marker").write_text("the app from before", encoding="utf-8")
    monkeypatch.setenv("FAKE_TOOLS_FAIL", "codesign")
    with pytest.raises(SetupError) as error:
        assemble.build(unpacked(tmp_path, mac_zip()), home, "darwin", tools, move=True)
    assert str(error.value) == "macOS couldn't sign AI Browser's app: codesign: fake failure"
    assert (before / "marker").read_text(encoding="utf-8") == "the app from before"
    assert sorted(path.name for path in (home / "desktop").iterdir()) == ["AI Browser.app"]  # no .build, no stamp


def test_an_electron_without_fuses_is_refused_and_nothing_is_kept(tmp_path, monkeypatch):
    from ai_browser.desktop import assemble
    from ai_browser.desktop.download import SetupError

    tools, _ = fake_tools(tmp_path, monkeypatch)
    with pytest.raises(SetupError, match="^This Electron build has no fuses: nothing was kept$"):
        assemble.build(unpacked(tmp_path, windows_zip(wire=b"")), tmp_path / "home", "win32", tools, move=True)
    assert sorted(path.name for path in (tmp_path / "home" / "desktop").iterdir()) == []


def test_a_changed_part_is_noticed_and_built_again(tmp_path, monkeypatch):  # Review Focus 5
    from ai_browser.desktop import assemble, fuses, layout
    from ai_browser.desktop.stage import ELECTRON

    tools, _ = fake_tools(tmp_path, monkeypatch)
    home = tmp_path / "home"
    app = assemble.build(unpacked(tmp_path, windows_zip()), home, "win32", tools, move=True)
    assert not assemble.stale(home, "win32")
    (app / "resources" / "app" / "main.js").write_text("// an older main.js", encoding="utf-8")
    monkeypatch.setattr(assemble, "layer_hash", lambda system: "a newer part")  # a pull changed AI Browser's part
    assert assemble.stale(home, "win32")
    assert assemble.refresh(home, "win32", tools) == app
    assert layout.stamp(home)["layer"] == "a newer part" and not assemble.stale(home, "win32")
    assert (app / "resources" / "app" / "main.js").read_bytes() == (ELECTRON / "main.js").read_bytes()
    assert fuses.states(app / "AI Browser.exe") == ["000000011"]  # still off: setting them again changes nothing
    assert sorted(path.name for path in (home / "desktop").iterdir()) == ["AI Browser", "app.json"]


def test_the_part_hash_follows_every_file_the_app_gets(tmp_path, monkeypatch):
    from ai_browser.desktop import assemble, stage

    copy = tmp_path / "electron"
    copy.mkdir()
    for name in stage.APP_FILES:
        (copy / name).write_bytes((stage.ELECTRON / name).read_bytes())
    monkeypatch.setattr(stage, "ELECTRON", copy)
    first = assemble.layer_hash("darwin")
    (copy / "preload.js").write_bytes(b"// changed")
    assert assemble.layer_hash("darwin") != first
    assert assemble.layer_hash("darwin") != assemble.layer_hash("win32")  # the Info.plist part is the Mac's own


def test_the_commands_are_exactly_these(tmp_path):
    from ai_browser.desktop.assemble import Tools, icon_command, sign_command

    app = tmp_path / "AI Browser.app"
    assert sign_command(Tools(), app) == ["codesign", "--force", "--deep", "--sign", "-", str(app)]
    assert icon_command(Tools(), tmp_path / "icon.png", tmp_path / "AI Browser.icns") == [
        "sips", "-s", "format", "icns", str(tmp_path / "icon.png"), "--out", str(tmp_path / "AI Browser.icns")]
```

Add to the end of `tests/test_desktop_electron.py`:

```python
@REAL
def test_the_assembled_app_refuses_a_debugging_port(tmp_path):
    from ai_browser.desktop import assemble, fuses, layout

    binary = Path(ELECTRON)
    root = binary.parents[3] if sys.platform == "darwin" else binary.parent  # the folder Electron's zip unpacks to
    home = tmp_path / "home"
    app = assemble.build(root, home, sys.platform)  # a copy, in a throwaway home; the real codesign and sips on a Mac
    started = subprocess.run([str(layout.executable(app, sys.platform)), f"--remote-debugging-port={free_port()}"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             timeout=30)
    assert started.returncode == 1  # it ended by itself, before any window: the packaged app opens no such port
    holder = layout.framework(app) if sys.platform == "darwin" else layout.executable(app, sys.platform)
    for wire in fuses.states(holder):
        assert wire[0] == wire[2] == wire[3] == "0"
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_desktop_assemble.py tests/test_desktop_electron.py -q -p no:randomly`

Expected: FAIL with `ModuleNotFoundError: No module named 'ai_browser.desktop.assemble'` (in `fake_tools`). The
real-Electron tests are skipped.

- [ ] **Step 3: Write the build**

Create `src/ai_browser/desktop/assemble.py`:

```python
"""AI Browser's own app, built in <home>/desktop/ from Electron as it was unpacked (layout.py says where).
- macOS: Electron.app becomes "AI Browser.app".
  - Its Info.plist gets AI Browser's name, bundle id and microphone text, and its icon (an .icns that sips makes from
    app/ui/icon.png). Electron's CFBundleIconName goes, or macOS would show Electron's icon from its asset catalog.
  - AI Browser's JavaScript goes in Contents/Resources/app/, and Electron's default app goes.
  - The fuses that would run it as Node.js or with an inspector are turned off (fuses.py).
  - Then it is signed on this computer, ad hoc (codesign --force --deep --sign -). macOS then keeps one identity for
    it, and remembers its microphone and Brave permissions.
- Windows: an "AI Browser" folder. electron.exe is renamed "AI Browser.exe", AI Browser's JavaScript goes in
  resources\\app\\, the default app goes, and the same fuses are turned off. There is no icon tool there, so
  AI Browser.exe keeps Electron's icon in File Explorer and in Task Manager. The window, the icon by the clock and the
  notifications show AI Browser's own (main.js sets them).
Everything is built in <home>/desktop/.build/ and moved into place only when complete. On any failure the app that
was there stays as it was, and the half-built one goes."""

from __future__ import annotations

import contextlib
import json
import plistlib
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .. import platforms
from . import fuses, layout
from .download import SetupError
from .release import VERSION
from .stage import ICON, part_hash, stage_app

PLIST = {"CFBundleName": layout.APP_NAME, "CFBundleDisplayName": layout.APP_NAME,
         "CFBundleIdentifier": layout.BUNDLE_ID, "CFBundleIconFile": "AI Browser.icns",
         "NSMicrophoneUsageDescription": "AI Browser listens only while you hold the talk button in Mission Control."}
TOOL_WAIT = 300  # seconds codesign or sips may take


@dataclass(frozen=True)
class Tools:
    """The macOS commands setup runs, as argv prefixes (tests pass stand-ins): codesign signs the app, sips makes its
    icon."""
    codesign: tuple[str, ...] = ("codesign",)
    sips: tuple[str, ...] = ("sips",)


def sign_command(tools: Tools, app: Path) -> list[str]:
    return [*tools.codesign, "--force", "--deep", "--sign", "-", str(app)]


def icon_command(tools: Tools, png: Path, icns: Path) -> list[str]:
    return [*tools.sips, "-s", "format", "icns", str(png), "--out", str(icns)]


def layer_hash(system: str) -> str:
    """AI Browser's part of the app, as this checkout would build it for `system`."""
    extra = json.dumps({"plist": PLIST if system == "darwin" else {}, "fuses": list(fuses.OFF)}, sort_keys=True)
    return part_hash(extra.encode("utf-8"))


def stale(home, system: str | None = None) -> bool:
    """An app is built here, but from another AI Browser part: a pull changed the JavaScript, the icon or the plist."""
    system = system or sys.platform
    found = layout.installed(home, system)
    return found is not None and found.get("layer") != layer_hash(system)


def _run(command: list[str], what: str) -> None:
    try:
        done = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=TOOL_WAIT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SetupError(f"{what}: {exc}") from None
    if done.returncode != 0:
        lines = done.stderr.decode("utf-8", "replace").strip().splitlines()
        raise SetupError(f"{what}: {lines[-1] if lines else f'it ended with {done.returncode}'}")


def _layer(app: Path, system: str, tools: Tools) -> None:
    """AI Browser's part, on a copy of Electron in .build: its JavaScript, its name and icon, Electron's default app
    gone, the fuses off; on macOS, signed last."""
    resources = layout.resources(app, system)
    stage_app(resources / "app")
    platforms.unlink(resources / "default_app.asar", missing_ok=True)
    if system == "darwin":
        plist = app / "Contents" / "Info.plist"
        with open(plist, "rb") as handle:
            info = plistlib.load(handle)
        info.update(PLIST)
        info.pop("CFBundleIconName", None)  # else macOS shows the asset catalog's icon (Electron's), not ours
        with open(plist, "wb") as handle:
            plistlib.dump(info, handle)
        _run(icon_command(tools, ICON, resources / PLIST["CFBundleIconFile"]), "macOS couldn't make AI Browser's icon")
        fuses.lock_down(layout.framework(app))
        _run(sign_command(tools, app), "macOS couldn't sign AI Browser's app")
    else:
        fuses.lock_down(layout.executable(app, system))


@contextlib.contextmanager
def _building(home):
    """<home>/desktop/.build, new (a stopped build's leftovers go first), and gone afterwards whatever happens.
    Failures come out as SetupError."""
    work = layout.folder(home) / ".build"
    if work.exists():
        platforms.rmtree(work)
    work.mkdir(parents=True)
    try:
        yield work
    except SetupError:
        raise
    except fuses.FuseError as exc:
        raise SetupError(str(exc)) from None
    except (OSError, ValueError) as exc:  # a copy or a rename; a broken Info.plist
        raise SetupError(f"AI Browser's app couldn't be built: {exc}") from None
    finally:
        with contextlib.suppress(OSError):
            platforms.rmtree(work)


def _into_place(built: Path, home, system: str, stamp: dict) -> Path:
    """The built app takes the place of the one there (if any), only now that it is complete."""
    final = layout.app_path(home, system)
    old = final.with_name(f".old-{final.name}")
    if old.exists():
        platforms.rmtree(old)
    if final.exists():
        platforms.replace(final, old)
    platforms.replace(built, final)
    layout.write_stamp(home, stamp)
    if old.exists():
        with contextlib.suppress(OSError):
            platforms.rmtree(old)
    return final


def build(electron: Path, home, system: str | None = None, tools: Tools = Tools(), arch: str = "",
          move: bool = False) -> Path:
    """The app, from Electron unpacked at `electron` (the zip's top folder): its path. `move` takes that folder's
    files (setup's own unpacking) instead of copying them. SetupError when it can't; nothing new is kept then."""
    system = system or sys.platform
    with _building(home) as work:
        built = work / layout.app_path(home, system).name
        source = Path(electron) / "Electron.app" if system == "darwin" else Path(electron)
        if not source.is_dir():
            raise SetupError("Electron's zip doesn't hold the app: nothing was kept")
        if move:
            platforms.replace(source, built)
        else:
            shutil.copytree(source, built, symlinks=True)
        if system != "darwin":
            platforms.replace(built / "electron.exe", layout.executable(built, system))
        _layer(built, system, tools)
        return _into_place(built, home, system, {"electron": VERSION, "system": system, "arch": arch,
                                                 "layer": layer_hash(system),
                                                 "built": time.strftime("%Y-%m-%dT%H:%M:%S")})


def refresh(home, system: str | None = None, tools: Tools = Tools()) -> Path:
    """AI Browser's part again, on the app that is there (a pull changed it), with no download: its path."""
    system = system or sys.platform
    found = layout.installed(home, system)
    if found is None:
        raise SetupError("AI Browser's app isn't set up")
    with _building(home) as work:
        built = work / layout.app_path(home, system).name
        shutil.copytree(layout.app_path(home, system), built, symlinks=True)
        _layer(built, system, tools)
        return _into_place(built, home, system, {**found, "layer": layer_hash(system),
                                                 "built": time.strftime("%Y-%m-%dT%H:%M:%S")})
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_desktop_assemble.py tests/test_desktop_electron.py tests/test_portable.py -q -p no:randomly`

Expected:
- PASS, with the `posix_only` tests skipped on Windows;
- the real-Electron tests skipped without `AIB_TEST_ELECTRON`. With it they pass, on a copy in a throwaway home, and
  on a Mac the real `codesign` and `sips` run on that copy only.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/desktop/assemble.py tests/fake_tools.py tests/test_desktop_assemble.py tests/test_desktop_electron.py
git commit -m "feat(desktop): AI Browser.app (and Windows' AI Browser folder) built from Electron, signed ad hoc"
```

### Task 7: `doctor --setup` offers the app, and builds it after a typed yes

**Files:**
- Create: `src/ai_browser/desktop/setup.py`
- Modify: `src/ai_browser/cli.py` (`_doctor_setup`, and three new functions after it)
- Modify: `tests/conftest.py` (one autouse fixture after the tab menu's `_never_the_users_app_port`)
- Test: `tests/test_desktop_setup.py` (new)

**Interfaces:**
- Consumes:
  - Task 1's `asset_for`, `offer`, `SETUP_COMMAND`, `VERSION` and `layout`;
  - Task 2's `download` and `SetupError`; Task 3's `unpack` and `UnpackError`; Task 6's `build` and `Tools`;
  - `platforms.lock_file` (`ai-browser app` holds `<home>/app/lock` while it runs);
  - `cli._doctor_setup`'s `report(mark, label, detail, required=False)`.
- Produces:
  - **`setup.py`:**
    - `FETCH` (the network) and `TOOLS` (codesign and sips): module globals, which tests replace;
    - `STOPPED` and `RUNNING`;
    - `set_up(home, asset, out=print, system=None) -> Path`: the app's path, or `SetupError`. Any failure keeps the
      reason (`layout.set_problem`); a success forgets the last one.
  - **`cli.py`:**
    - `_interactive() -> bool`: a terminal both ways, so someone can see the question and answer it;
    - `_ask(question) -> str`;
    - `_desktop_check(report)`. `doctor --setup` prints one `app` line, after the `Docker` line. When someone can
      answer, the offer, the question and the setup follow.
  - **`tests/conftest.py`'s `_no_setup_outside_the_test` (autouse):**
    - `AIB_HOME` is a throwaway, unless a test sets its own;
    - `setup.FETCH` fails the test if it is ever called;
    - `cli._interactive()` is False;
    - `live._bind` never binds 8792 (the doctor's look at the free ports). The tab menu's
      `_never_the_users_app_port` does the same for the app server; `USERS_APP_PORT` is its constant.

- [ ] **Step 1: Write the failing tests**

In `tests/conftest.py`, add after the tab menu's `_never_the_users_app_port` fixture (it defines `USERS_APP_PORT`):

```python
@pytest.fixture(autouse=True)
def _no_setup_outside_the_test(monkeypatch, tmp_path_factory):
    """No test reads or writes the user's own ~/.ai-browser (AIB_HOME is a throwaway unless a test sets its own), no
    test downloads Electron, and no doctor --setup waits for a typed answer or binds 8792 to see if it is free. The
    setup's tests pass a fake release and say whether someone can answer."""
    import ai_browser.cli as cli
    from ai_browser import live
    from ai_browser.desktop import setup

    def refuse(url):
        raise AssertionError(f"tests never download Electron ({url})")

    bind = live._bind
    monkeypatch.setenv("AIB_HOME", str(tmp_path_factory.mktemp("aib-home")))
    monkeypatch.setattr(setup, "FETCH", refuse)
    monkeypatch.setattr(cli, "_interactive", lambda: False)
    monkeypatch.setattr(live, "_bind", lambda host, port: None if port == USERS_APP_PORT else bind(host, port))
```

Create `tests/test_desktop_setup.py`:

```python
"""`ai-browser doctor --setup` offers AI Browser's own app (desktop/setup.py, cli.py). It builds the app only after a
typed yes. Before it asks, it shows the pinned Electron's version, size and address. The download is checked against
SHASUMS256.txt. When the download is cut, doesn't match or is stopped, nothing is kept, and the reason is kept for
Settings. Every release here is a miniature (tests/fake_electron_zip.py), and codesign and sips are stand-ins."""

import sys
from pathlib import Path

import pytest

from fake_electron_zip import ReleaseFetch, checksum, mac_zip, windows_zip
from fake_tools import fake_tools, tool_runs
from test_cli import _browser_port_stand_in, _setup_env

ZIPS = {"darwin": mac_zip, "win32": windows_zip}
APP_SYSTEMS = pytest.mark.skipif(sys.platform not in ZIPS, reason="AI Browser's own app is for macOS and Windows")


@pytest.fixture
def doctor(tmp_path, monkeypatch):
    """doctor --setup's world: a throwaway home, a fake Claude Code and browser (test_cli's), a miniature Electron
    release for this computer, stand-in tools, and someone at the terminal who answers from `answers`."""
    from ai_browser import cli
    from ai_browser.desktop import release, setup

    server, _ = _browser_port_stand_in()
    env = _setup_env(tmp_path, monkeypatch, server.getsockname()[1])
    data = ZIPS[sys.platform]()
    asset = release.Asset(sys.platform, "arm64" if sys.platform == "darwin" else "x64", "electron-test.zip",
                          len(data), checksum(data), "a test computer")
    fetch = ReleaseFetch(asset, data)
    tools, log = fake_tools(tmp_path, monkeypatch)
    answers = ["y"]
    monkeypatch.setattr(release, "asset_for", lambda system=None, machine=None: asset)
    monkeypatch.setattr(setup, "FETCH", fetch)
    monkeypatch.setattr(setup, "TOOLS", tools)
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    monkeypatch.setattr(cli, "_ask", lambda question: answers.pop(0))
    yield {"home": Path(env["AIB_HOME"]), "asset": asset, "fetch": fetch, "log": log, "answers": answers}
    server.close()


def listing(home: Path) -> list[str]:
    folder = home / "desktop"
    return sorted(path.name for path in folder.iterdir()) if folder.exists() else []


@APP_SYSTEMS
def test_the_offer_says_what_and_where_and_a_yes_builds_the_app(doctor, capsys):
    from ai_browser.cli import main
    from ai_browser.desktop import layout
    from ai_browser.desktop.release import SHASUMS, VERSION

    asset, home = doctor["asset"], doctor["home"]
    assert main(["doctor", "--setup"]) == 0
    out = capsys.readouterr().out
    assert "- app         AI Browser's own app isn't set up: AI Browser opens in a browser window" in out
    assert f"It is built from Electron {VERSION} for a test computer: {asset.megabytes}, from" in out
    assert f"\n  {asset.url}\n" in out and "checked against Electron's SHASUMS256.txt" in out
    assert f"The app is built in {home / 'desktop'}." in out
    assert "✓ app         AI Browser's own app is ready: start it with `uv run ai-browser app`" in out
    assert out.splitlines()[-1] == "all good"
    assert doctor["fetch"].urls == [SHASUMS, asset.url]  # the checksums first, then the zip
    assert layout.installed(home) is not None and layout.problem(home) == ""
    assert listing(home) == sorted([layout.app_path(home).name, "app.json"])  # no zip, no unpacked Electron
    if sys.platform == "darwin":
        assert [run[0] for run in tool_runs(doctor["log"])] == ["sips", "codesign"]


@APP_SYSTEMS
def test_a_download_cut_halfway_keeps_nothing_and_settings_will_say_why(doctor, capsys):  # Review Focus 2
    from ai_browser.cli import main
    from ai_browser.desktop import layout
    from ai_browser.desktop.download import CUT

    doctor["fetch"].cut_at = doctor["asset"].size // 2
    assert main(["doctor", "--setup"]) == 1
    out = capsys.readouterr().out
    assert f"✗ app         {CUT}" in out and out.splitlines()[-1] == "some checks failed"
    assert layout.problem(doctor["home"]) == CUT
    assert listing(doctor["home"]) == ["problem.json"]  # no zip, no part, no app


@APP_SYSTEMS
def test_a_zip_or_a_list_that_doesnt_match_keeps_nothing(doctor, capsys):  # Review Focus 2
    from ai_browser.cli import main
    from ai_browser.desktop.download import MISMATCH, NOT_LISTED
    from ai_browser.desktop.release import SHASUMS

    doctor["fetch"].corrupt = True
    assert main(["doctor", "--setup"]) == 1
    assert f"✗ app         {MISMATCH}" in capsys.readouterr().out
    assert listing(doctor["home"]) == ["problem.json"]
    doctor["fetch"].corrupt, doctor["fetch"].listed = False, "f" * 64
    doctor["answers"][:] = ["y"]
    doctor["fetch"].urls.clear()
    assert main(["doctor", "--setup"]) == 1
    out = capsys.readouterr().out
    assert f"- app         the last setup didn't finish: {MISMATCH}" in out  # what went wrong before, said first
    assert f"✗ app         {NOT_LISTED}" in out and doctor["fetch"].urls == [SHASUMS]  # the zip: never fetched


@APP_SYSTEMS
def test_only_a_yes_downloads(doctor, capsys):
    from ai_browser.cli import main

    for answer in ("n", "", "yes please"):
        doctor["answers"][:] = [answer]
        assert main(["doctor", "--setup"]) == 0
        assert "Skipped: nothing was downloaded." in capsys.readouterr().out
    assert doctor["fetch"].urls == [] and listing(doctor["home"]) == []


@APP_SYSTEMS
def test_ctrl_c_during_the_download_keeps_nothing(doctor, monkeypatch, capsys):
    from ai_browser.cli import main
    from ai_browser.desktop import layout, setup

    def stopping(asset, out):
        def progress(done):
            raise KeyboardInterrupt
        return progress

    monkeypatch.setattr(setup, "_progress", stopping)
    assert main(["doctor", "--setup"]) == 130
    assert layout.problem(doctor["home"]) == setup.STOPPED == ("The setup was stopped before the end: nothing was "
                                                               "kept")
    assert listing(doctor["home"]) == ["problem.json"]


@APP_SYSTEMS
def test_the_setup_waits_until_ai_browser_is_not_running(doctor, capsys):
    from ai_browser import platforms
    from ai_browser.cli import main

    (doctor["home"] / "app").mkdir(parents=True)
    lock = platforms.lock_file(doctor["home"] / "app" / "lock")  # a running `ai-browser app` holds it
    try:
        assert main(["doctor", "--setup"]) == 1
    finally:
        lock.close()
    assert "✗ app         AI Browser is running: quit it, then run the setup again" in capsys.readouterr().out
    assert doctor["fetch"].urls == []


@APP_SYSTEMS
def test_once_set_up_it_says_so_and_asks_nothing(doctor, capsys):
    from ai_browser.cli import main
    from ai_browser.desktop import layout
    from ai_browser.desktop.release import VERSION

    assert main(["doctor", "--setup"]) == 0
    capsys.readouterr()
    assert main(["doctor", "--setup"]) == 0  # `answers` is empty now: a question would fail the test
    out = capsys.readouterr().out
    assert f"✓ app         AI Browser's own app (Electron {VERSION}): {layout.app_path(doctor['home'])}" in out


@APP_SYSTEMS
def test_with_no_one_to_answer_it_says_how_and_downloads_nothing(doctor, monkeypatch, capsys):
    from ai_browser import cli

    monkeypatch.setattr(cli, "_interactive", lambda: False)
    assert cli.main(["doctor", "--setup"]) == 0
    line = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("- app"))
    assert line == ("- app         AI Browser's own app isn't set up: AI Browser opens in a browser window. To set it "
                    "up, run `uv run ai-browser doctor --setup` in a terminal (it asks first)")
    assert doctor["fetch"].urls == []


def test_where_the_app_doesnt_run_the_doctor_says_so(tmp_path, monkeypatch, capsys):
    from ai_browser.cli import main
    from ai_browser.desktop import release

    server, _ = _browser_port_stand_in()
    try:
        _setup_env(tmp_path, monkeypatch, server.getsockname()[1])
        monkeypatch.setattr(release, "asset_for", lambda system=None, machine=None: None)
        assert main(["doctor", "--setup"]) == 0
    finally:
        server.close()
    assert ("- app         AI Browser's own app runs on macOS and on Windows (x64): here it opens in a browser "
            "window") in capsys.readouterr().out


def test_no_test_downloads_electron_or_waits_for_an_answer(tmp_path):
    from ai_browser import cli
    from ai_browser.config import home
    from ai_browser.desktop import setup

    with pytest.raises(AssertionError, match="tests never download Electron"):
        setup.FETCH("https://github.com/electron/electron/releases/download/v44.5.1/SHASUMS256.txt")
    assert cli._interactive() is False and home() != Path.home() / ".ai-browser"
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_desktop_setup.py -q -p no:randomly`

Expected: every test errors at setup with `ModuleNotFoundError: No module named 'ai_browser.desktop.setup'`, which
comes from the conftest fixture.

- [ ] **Step 3: Write the setup, and the doctor's offer**

Create `src/ai_browser/desktop/setup.py`:

```python
"""Setting up AI Browser's own app, for `ai-browser doctor --setup` (cli.py). After the user's typed yes, the pinned
Electron is downloaded and checked (download.py), unpacked (unpack.py) and built into the app (assemble.py), all in
<home>/desktop/. Whatever fails, and on Ctrl-C, nothing is kept but a note of why (layout.set_problem), which
Settings shows; the browser window works as before. It runs only while AI Browser itself isn't running."""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Callable
from pathlib import Path

from .. import platforms
from ..hearing.model import urlopen_fetch
from . import layout
from .assemble import Tools, build
from .download import SetupError, download
from .release import Asset
from .unpack import UnpackError, unpack

FETCH = urlopen_fetch  # the network (conftest replaces it: no test downloads Electron)
TOOLS = Tools()  # codesign and sips (the tests pass stand-ins)
STOPPED = "The setup was stopped before the end: nothing was kept"
RUNNING = "AI Browser is running: quit it, then run the setup again"


def _progress(asset: Asset, out: Callable[[str], None]) -> Callable[[int], None]:
    """A line about every tenth of the download."""
    step, shown = max(1, asset.size // 10), [0]

    def progress(done: int) -> None:
        if done - shown[0] >= step or done == asset.size:
            shown[0] = done
            out(f"Downloaded {round(done / 1_000_000)} of {asset.megabytes}")

    return progress


def _clear(work: Path) -> None:
    if work.exists():
        with contextlib.suppress(OSError):
            platforms.rmtree(work)


def set_up(home, asset: Asset, out: Callable[[str], None] = print, system: str | None = None) -> Path:
    """The app, downloaded, checked and built: its path. SetupError when anything fails, with the reason kept for
    Settings. On Ctrl-C the reason is kept too, and KeyboardInterrupt goes on up. Nothing else is kept either way."""
    system = system or sys.platform
    (Path(home) / "app").mkdir(parents=True, exist_ok=True)
    lock = platforms.lock_file(Path(home) / "app" / "lock")  # `ai-browser app` holds it while it runs
    if lock is None:
        raise SetupError(RUNNING)
    work = layout.folder(home) / ".download"
    try:
        _clear(work)
        zipped = download(asset, work, FETCH, _progress(asset, out))
        out("It matches Electron's SHASUMS256.txt. Building AI Browser's app…")
        unpack(zipped, work / "electron")
        platforms.unlink(zipped)
        app = build(work / "electron", home, system, TOOLS, arch=asset.arch, move=True)
    except (UnpackError, OSError) as exc:
        reason = str(exc) if isinstance(exc, UnpackError) else f"Electron couldn't be unpacked: {exc.strerror or exc}"
        layout.set_problem(home, reason)
        raise SetupError(reason) from None
    except SetupError as exc:
        layout.set_problem(home, str(exc))
        raise
    except BaseException:
        layout.set_problem(home, STOPPED)
        raise
    finally:
        _clear(work)
        lock.close()
    layout.set_problem(home, None)
    return app
```

In `src/ai_browser/cli.py`:
1. In `_doctor_setup`, replace the line `report("-", "Docker", "not checked here: run `uv run ai-browser doctor`")`
   with:

```python
    report("-", "Docker", "not checked here: run `uv run ai-browser doctor`")
    _desktop_check(report)
```

2. Add after `_doctor_setup`:

```python
def _interactive() -> bool:
    """Whether someone can see a question here and answer it: a terminal both ways, not a pipe or a file."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def _ask(question: str) -> str:
    try:
        return input(question)
    except EOFError:
        return ""


def _desktop_check(report) -> None:
    """AI Browser's own app: set up, or not. While it isn't, or uses an older Electron, and someone can answer: the
    offer (the version, the size, the address), the question, and after a typed yes, the setup. Nothing is
    downloaded without that yes."""
    from .desktop import layout
    from .desktop.download import SetupError
    from .desktop.release import SETUP_COMMAND, VERSION, asset_for, offer
    from .desktop.setup import set_up

    root = home()
    asset, built = asset_for(), layout.installed(root)
    if asset is None:
        report("-", "app", "AI Browser's own app runs on macOS and on Windows (x64): here it opens in a browser window")
        return
    if built is not None and built.get("electron") == VERSION:
        report("✓", "app", f"AI Browser's own app (Electron {VERSION}): {layout.app_path(root)}")
        return
    problem = layout.problem(root)
    if problem:
        report("-", "app", f"the last setup didn't finish: {problem}")
    now = (f"AI Browser's own app uses Electron {built.get('electron')}, and {VERSION} is out" if built is not None
           else "AI Browser's own app isn't set up: AI Browser opens in a browser window")
    if not _interactive():
        report("-", "app", f"{now}. To set it up, run `{SETUP_COMMAND}` in a terminal (it asks first)")
        return
    report("-", "app", now)
    print("\n".join(offer(asset, layout.folder(root))))
    if _ask("Download it now? Type y and press Enter: ").strip().lower() not in ("y", "yes"):
        print("Skipped: nothing was downloaded.")
        return
    try:
        set_up(root, asset)
    except SetupError as exc:
        report("✗", "app", str(exc), True)
        return
    report("✓", "app", "AI Browser's own app is ready: start it with `uv run ai-browser app`")
```

- [ ] **Step 4: Run them, and the doctor's other tests, to see them pass**

Run: `uv run pytest tests/test_desktop_setup.py tests/test_cli.py -q -p no:randomly`

Expected: PASS. The doctor's other tests still find their lines: the new `app` line comes after `Docker`, and
"all good" stays last.

Run: `uv run pytest tests/test_config.py tests/test_app_run.py -q -p no:randomly`

Expected: PASS (a throwaway `AIB_HOME` changes nothing for the tests that set their own).

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/desktop/setup.py src/ai_browser/cli.py tests/conftest.py tests/test_desktop_setup.py
git commit -m "feat(doctor): doctor --setup offers AI Browser's own app and builds it after a typed yes"
```

### Task 8: Starting the app on a private line: stdin on Windows, LaunchServices and a socket on macOS

**Files:**
- Create: `src/ai_browser/desktop/launch.py`
- Create: `tests/fake_electron.py`, `tests/fake_open.py`
- Test: `tests/test_desktop_launch.py` (new)
- Modify: `tests/test_desktop_static.py` (one test at the end)

**Interfaces:**
- Consumes:
  - `app/window.py`'s `WindowError`;
  - Task 1's `layout`; Task 6's `stale`, `refresh` and `SetupError`;
  - Task 5's line, as `main.js` speaks it (its message types are listed in Task 5's Interfaces).
- Produces:
  - `DesktopError(WindowError)`: the app can't start (plain words, with no full stop).
  - `mac_command(app, line, opener=("open",)) -> list[str]`, `windows_command(program) -> list[str]`.
  - `START_WAIT = 20.0`, `ANSWER_WAIT = 5.0`, `QUIT_WAIT = 10.0`, and `UPDATED` (the note after a rebuild).
  - `DesktopWindow(home, shortcut=None, system=None, program=None, opener=("open",))`. It has `AppWindow`'s surface:
    - `id = "desktop"`, `name = "AI Browser"` and `note`;
    - `async launch(url)`: it builds AI Browser's part again first if it is stale, then starts the app, sends
      `start`, and waits for `hello`;
    - `async close() -> ""`.
  - And the line:
    - `send(message) -> bool` and `async try_shortcut(value) -> {value, ok, why, pressed}`;
    - `.shortcut`: the latest `{value, ok, why, pressed}` the app said;
    - `.on_message`, which gets `{"type": "shortcut", ...}` said unasked and `{"type": "clicked", "id"}`;
    - `.ended` (an `asyncio.Event`, set once the app has quit or gone), `.quit_by_user` (its own Quit), `.pid` and
      `.running`.
  - `default_desktop(home, shortcut=None) -> DesktopWindow | None`: the app, once it is built here.
  - **Tests:** `tests/fake_electron.py` (a fake app speaking the line, run by `FAKE_ELECTRON_PLAN`) and
    `tests/fake_open.py` (a fake `open`).

- [ ] **Step 1: Write the failing tests**

Create `tests/fake_electron.py`:

```python
"""A stand-in for AI Browser's own app (desktop/electron/main.js), for the launcher's tests. It speaks the same line:
JSON lines on its stdin and stdout, or on the socket --aib-line=<path> names. It answers start with hello (its pid),
answers a shortcut as its plan says, and quits on the engine's quit or when the line ends. FAKE_ELECTRON_LOG gets its
argv and every message it reads. FAKE_ELECTRON_PLAN (JSON) says what else it does:
- "hello": false: it never says hello;
- "start_status": {...}: right after hello, the state of the shortcut it was started with;
- "shortcuts": {value: {"ok", "why"}}: its answer to a shortcut request (any other value: ok);
- "click": true: it clicks each notification it gets;
- "quit_after": seconds: the user's Quit, that long after the start."""

from __future__ import annotations

import json
import os
import socket
import sys
import threading


def main(argv: list[str]) -> int:
    plan = json.loads(os.environ.get("FAKE_ELECTRON_PLAN") or "{}")
    lock = threading.Lock()
    log = open(os.environ["FAKE_ELECTRON_LOG"], "a", encoding="utf-8")  # noqa: SIM115 (open until the end)

    def note(entry: dict) -> None:
        with lock:
            log.write(json.dumps(entry) + "\n")
            log.flush()

    note({"argv": argv})
    path = next((arg.split("=", 1)[1] for arg in argv if arg.startswith("--aib-line=")), None)
    if path:
        line = socket.socket(socket.AF_UNIX)
        line.connect(path)
        reader, writer = line.makefile("rb"), line.makefile("wb")
    else:
        reader, writer = sys.stdin.buffer, sys.stdout.buffer

    def say(message: dict) -> None:
        with lock:
            writer.write((json.dumps(message) + "\n").encode("utf-8"))
            writer.flush()

    def quit_later(seconds: float) -> None:
        def now() -> None:
            say({"type": "quit"})
            os._exit(0)

        threading.Timer(seconds, now).start()

    for raw in reader:
        message = json.loads(raw.decode("utf-8"))
        note({"got": message})
        kind = message.get("type")
        if kind == "start":
            if plan.get("hello", True):
                say({"type": "hello", "pid": os.getpid()})
            if "start_status" in plan:
                say({"type": "shortcut", "value": message.get("shortcut"), "pressed": False, **plan["start_status"]})
            if "quit_after" in plan:
                quit_later(plan["quit_after"])
        elif kind == "shortcut":
            answer = plan.get("shortcuts", {}).get(str(message.get("value")), {"ok": True, "why": ""})
            say({"type": "shortcut", "value": message.get("value"), "request": message.get("request"),
                 "pressed": False, **answer})
        elif kind == "notify" and plan.get("click"):
            say({"type": "clicked", "id": message["id"]})
        elif kind == "quit":
            break
    log.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Create `tests/fake_open.py`:

```python
"""A stand-in for macOS's `open`, for the launcher's tests. It takes the arguments LaunchServices would get
(-n -W -a <app> --args …), and logs them, with the mode of the line's folder, to FAKE_OPEN_LOG. Then it runs the fake
app (fake_electron.py) with the --args, and waits for it, as `open -W` does."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import fake_electron


def main(argv: list[str]) -> int:
    folder = next((Path(arg.split("=", 1)[1]).parent for arg in argv if arg.startswith("--aib-line=")), None)
    mode = stat.S_IMODE(os.stat(folder).st_mode) if folder is not None and folder.exists() else None
    with open(os.environ["FAKE_OPEN_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps({"argv": argv, "folder_mode": mode}) + "\n")
    if argv[:3] != ["-n", "-W", "-a"] or len(argv) < 5 or argv[4] != "--args" or not Path(argv[3]).is_dir():
        return 1
    return fake_electron.main(argv[5:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Create `tests/test_desktop_launch.py`:

```python
"""Starting AI Browser's own app and its private line (desktop/launch.py). The app is a fake
(tests/fake_electron.py), and on macOS so is `open` (tests/fake_open.py), whose arguments are checked as
LaunchServices would get them. The one-time code goes over the line, never on a command line."""

import asyncio
import json
import sys
from pathlib import Path

import pytest

from conftest import fake_python

TESTS = Path(__file__).parent
URL = "http://127.0.0.1:8793/open?code=the-one-time-code"


def entries(log: Path) -> list[dict]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []


def plan(tmp_path, monkeypatch, **steps) -> Path:
    log = tmp_path / "app.log"
    monkeypatch.setenv("FAKE_ELECTRON_LOG", str(log))
    monkeypatch.setenv("FAKE_ELECTRON_PLAN", json.dumps(steps))
    return log


def windows_app(tmp_path, monkeypatch, **steps):
    """(the app as Windows starts it: its own program, the line on its stdin and stdout; the fake's log)."""
    from ai_browser.desktop.launch import DesktopWindow

    log = plan(tmp_path, monkeypatch, **steps)
    app = DesktopWindow(tmp_path / "home", "Alt+Space", system="win32",
                        program=[fake_python(), str(TESTS / "fake_electron.py")])
    return app, log


async def test_on_windows_the_line_is_the_apps_stdin_and_the_code_stays_off_every_command_line(tmp_path,
                                                                                                 monkeypatch):
    app, log = windows_app(tmp_path, monkeypatch, shortcuts={"Alt+Shift+Space": {"ok": False, "why": "taken"}})
    await app.launch(URL)
    try:
        assert app.pid is not None and app.running and not app.ended.is_set()
        assert await app.try_shortcut("Alt+Shift+Space") == {"value": "Alt+Shift+Space", "ok": False, "why": "taken",
                                                             "pressed": False}
        assert await app.try_shortcut(None) == {"value": None, "ok": True, "why": "", "pressed": False}
        assert app.shortcut["value"] is None  # what the app holds now: no shortcut
        assert app.send({"type": "notify", "id": "n1", "title": "An agent is waiting for you", "body": "…"})
    finally:
        assert await app.close() == ""
    assert app.ended.is_set() and not app.quit_by_user and not app.running
    seen = entries(log)
    assert seen[0] == {"argv": []}  # its command line: the program alone
    got = [entry["got"] for entry in seen[1:]]
    assert got[0] == {"type": "start", "open": URL, "shortcut": "Alt+Space"}  # the code: over the line only
    assert [message["type"] for message in got] == ["start", "shortcut", "shortcut", "notify", "quit"]


@pytest.mark.posix_only  # macOS's line is a socket in a folder; Windows' is stdin
async def test_on_macos_launchservices_starts_it_and_the_line_is_a_private_socket(tmp_path, monkeypatch):
    from ai_browser.desktop import layout
    from ai_browser.desktop.launch import DesktopWindow

    log = plan(tmp_path, monkeypatch)
    opened = tmp_path / "open.log"
    monkeypatch.setenv("FAKE_OPEN_LOG", str(opened))
    home = tmp_path / "home"
    bundle = layout.app_path(home, "darwin")
    bundle.mkdir(parents=True)  # the built app
    app = DesktopWindow(home, None, system="darwin", opener=[fake_python(), str(TESTS / "fake_open.py")])
    await app.launch(URL)
    try:
        [entry] = entries(opened)
        line = entry["argv"][-1].removeprefix("--aib-line=")
        assert entry["argv"] == ["-n", "-W", "-a", str(bundle), "--args", f"--aib-line={line}"]
        assert entry["folder_mode"] == 0o700  # only this user can open the line's folder
        assert not Path(line).exists() and not Path(line).parent.exists()  # taken once, then gone
        assert entries(log)[1]["got"] == {"type": "start", "open": URL, "shortcut": None}
    finally:
        await app.close()
    assert app.ended.is_set() and not app.running


async def test_the_apps_quit_ends_the_run_as_the_users(tmp_path, monkeypatch):
    app, _ = windows_app(tmp_path, monkeypatch, quit_after=0.3)
    await app.launch(URL)
    await asyncio.wait_for(app.ended.wait(), 10)
    assert app.quit_by_user
    assert await app.close() == ""


async def test_what_the_app_says_unasked_reaches_the_engine(tmp_path, monkeypatch):
    app, _ = windows_app(tmp_path, monkeypatch, start_status={"ok": False, "why": "taken"}, click=True)
    heard = []
    app.on_message = heard.append
    await app.launch(URL)
    try:
        app.send({"type": "notify", "id": "n7", "title": "A bot check on example.com", "body": "…"})
        for _ in range(100):
            if len(heard) >= 2:
                break
            await asyncio.sleep(0.05)
    finally:
        await app.close()
    assert heard == [{"type": "shortcut", "value": "Alt+Space", "ok": False, "why": "taken", "pressed": False},
                     {"type": "clicked", "id": "n7"}]
    assert app.shortcut == {"value": "Alt+Space", "ok": False, "why": "taken", "pressed": False}


async def test_an_app_that_never_says_hello_is_ended_and_said_plainly(tmp_path, monkeypatch):
    from ai_browser.desktop import launch

    monkeypatch.setattr(launch, "START_WAIT", 1.0)
    app, _ = windows_app(tmp_path, monkeypatch, hello=False)
    with pytest.raises(launch.DesktopError) as error:
        await app.launch(URL)
    assert str(error.value) == "AI Browser's app didn't answer as it started"
    assert app.ended.is_set() and not app.running  # nothing is left running


async def test_a_program_that_isnt_there_is_said_plainly(tmp_path):
    from ai_browser.desktop.launch import DesktopError, DesktopWindow

    app = DesktopWindow(tmp_path / "home", None, system="win32", program=[str(tmp_path / "missing.exe")])
    with pytest.raises(DesktopError, match="^AI Browser's app could not start: "):
        await app.launch(URL)
    assert app.ended.is_set()


async def test_a_stale_app_is_built_again_before_it_starts(tmp_path, monkeypatch):  # Review Focus 5
    from ai_browser.desktop import launch

    built = []
    monkeypatch.setattr(launch, "stale", lambda home, system=None: True)
    monkeypatch.setattr(launch, "refresh", lambda home, system=None: built.append((home, system)))
    app, _ = windows_app(tmp_path, monkeypatch)
    await app.launch(URL)
    await app.close()
    assert built == [(tmp_path / "home", "win32")] and app.note == ""  # the microphone's note is the Mac's

    def failing(home, system=None):
        raise launch.SetupError("macOS couldn't sign AI Browser's app: test")

    monkeypatch.setattr(launch, "refresh", failing)
    again, _ = windows_app(tmp_path, monkeypatch)
    with pytest.raises(launch.DesktopError) as error:
        await again.launch(URL)
    assert str(error.value) == "AI Browser's app couldn't be updated: macOS couldn't sign AI Browser's app: test"
    assert not again.running  # never started: run_app opens a browser window instead


def test_the_app_is_used_only_once_it_is_built_here(tmp_path):
    from ai_browser.desktop import layout
    from ai_browser.desktop.launch import DesktopWindow, default_desktop

    home = tmp_path / "home"
    assert default_desktop(home, "Alt+Space") is None
    program = layout.executable(layout.app_path(home))
    program.parent.mkdir(parents=True)
    program.write_bytes(b"")
    layout.write_stamp(home, {"electron": "44.5.1", "system": sys.platform, "arch": "", "layer": "x"})
    found = default_desktop(home, "Alt+Shift+Space")
    assert isinstance(found, DesktopWindow) and found.start_shortcut == "Alt+Shift+Space"
    assert (found.id, found.name, found.note) == ("desktop", "AI Browser", "")
```

Add to the end of `tests/test_desktop_static.py`:

```python
def test_the_product_never_passes_a_debugging_switch():
    from ai_browser.desktop import launch

    mac = launch.mac_command(Path("/x/AI Browser.app"), Path("/t/aib-1/line"))
    windows = launch.windows_command(Path("/x/AI Browser/AI Browser.exe"))
    assert mac == ["open", "-n", "-W", "-a", str(Path("/x/AI Browser.app")), "--args",
                   f"--aib-line={Path('/t/aib-1/line')}"]
    assert windows == [str(Path("/x/AI Browser/AI Browser.exe"))]
    banned = ("--remote-debugging", "--inspect", "--remote-allow-origins", "--js-flags", "--enable-logging",
              "--auto-open-devtools", "--user-data-dir", "--load-extension")
    assert not [arg for arg in mac + windows if arg.startswith(banned)]
    for path in sorted((SRC / "desktop").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for word in ("remote-debugging", "--inspect", "ELECTRON_RUN_AS_NODE", "openDevTools"):
            assert word not in source, (path.name, word)
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_desktop_launch.py tests/test_desktop_static.py -q -p no:randomly`

Expected: FAIL with `ModuleNotFoundError: No module named 'ai_browser.desktop.launch'`.

- [ ] **Step 3: Write the launcher**

Create `src/ai_browser/desktop/launch.py`:

```python
"""AI Browser's own app for one run of `ai-browser app` (app/run.py): started, linked by one private line, and ended.

The line carries JSON, one object per line, both ways (desktop/electron/line.js is the other end):
- the engine sends start (the start address with its one-time code, and the shortcut from Settings), shortcut (try
  this one), notify, show and quit;
- the app sends hello (its pid), shortcut (whether it holds one, and its first press), clicked (a notification) and
  quit (the user's Quit).

How it starts:
- Windows: its own program, AI Browser.exe, with the line on its stdin and stdout.
- macOS: through LaunchServices (`open -n -W -a`), so macOS treats it as an app of its own: its Dock icon, and the
  microphone and Brave permissions it asks for are its own (a program started from a terminal would ask as the
  terminal). LaunchServices gives it no pipe. So the line is a socket in a new folder only this user can open. Its
  path is the app's one argument, only the first connection is taken, and the socket goes at once.

The start code never goes on a command line, and nothing here passes a debugging switch."""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import os
import signal
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from ..app.window import WindowError
from . import layout
from .assemble import SetupError, refresh, stale

START_WAIT = 20.0  # seconds for the app to start and say hello
ANSWER_WAIT = 5.0  # seconds for its answer about a shortcut
QUIT_WAIT = 10.0  # seconds it gets to quit before it is ended
LINE_LIMIT = 64 * 1024  # bytes in one line
UPDATED = "AI Browser's app was updated for this version: macOS may ask for the microphone once more."


class DesktopError(WindowError):
    """AI Browser's own app can't start; app/run.py opens a browser window instead (plain words, no full stop)."""


def mac_command(app: Path, line: Path, opener: Sequence[str] = ("open",)) -> list[str]:
    return [*opener, "-n", "-W", "-a", str(app), "--args", f"--aib-line={line}"]


def windows_command(program: Path) -> list[str]:
    return [str(program)]


def _parse(raw: bytes) -> dict | None:
    try:
        message = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return message if isinstance(message, dict) and isinstance(message.get("type"), str) else None


class DesktopWindow:
    """This run's own app: AppWindow's surface (id, name, note, launch(url), close() -> str), plus the line."""

    id, name = "desktop", "AI Browser"

    def __init__(self, home, shortcut: str | None = None, system: str | None = None,
                 program: Sequence[str] | None = None, opener: Sequence[str] = ("open",)):
        self.home, self.system = Path(home), system or sys.platform
        self.app = layout.app_path(self.home, self.system)
        self.program = list(program) if program else windows_command(layout.executable(self.app, self.system))
        self.opener = tuple(opener)
        self.start_shortcut = shortcut
        self.note = ""
        self.shortcut: dict = {"value": shortcut, "ok": None, "why": "", "pressed": False}
        self.on_message: Callable[[dict], None] | None = None
        self.ended = asyncio.Event()
        self.quit_by_user = False
        self.pid: int | None = None
        self._process = None
        self._writer = None
        self._tasks: list[asyncio.Task] = []
        self._hello: asyncio.Future | None = None
        self._waiters: dict[str, asyncio.Future] = {}
        self._requests = itertools.count(1)

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def launch(self, url: str) -> None:
        """Start the app on `url` (the /open address with its one-time code), and wait for its hello. A stale app is
        built again first. DesktopError when it can't start: nothing is left running then."""
        if stale(self.home, self.system):
            try:
                await asyncio.to_thread(refresh, self.home, self.system)
            except SetupError as exc:
                raise DesktopError(f"AI Browser's app couldn't be updated: {exc}") from None
            self.note = UPDATED if self.system == "darwin" else ""
        self._hello = asyncio.get_running_loop().create_future()
        try:
            await (self._start_mac() if self.system == "darwin" else self._start_direct())
            self.send({"type": "start", "open": url, "shortcut": self.start_shortcut})
            hello = await asyncio.wait_for(self._hello, START_WAIT)
        except TimeoutError:
            await self._end_now()
            raise DesktopError("AI Browser's app didn't answer as it started") from None
        except DesktopError:
            await self._end_now()
            raise
        pid = hello.get("pid")
        self.pid = pid if isinstance(pid, int) and not isinstance(pid, bool) and pid > 1 else None

    async def _start_direct(self) -> None:
        try:
            self._process = await asyncio.create_subprocess_exec(
                *self.program, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, limit=LINE_LIMIT)
        except OSError as exc:
            raise DesktopError(f"AI Browser's app could not start: {exc.strerror or exc}") from None
        self._listen(self._process.stdout, self._process.stdin)

    async def _start_mac(self) -> None:
        if not self.app.is_dir():
            raise DesktopError(f"AI Browser's app isn't at {self.app}")
        folder = Path(tempfile.mkdtemp(prefix="aib-"))  # mode 0700: only this user can open what's in it
        line = folder / "line"
        joined = asyncio.get_running_loop().create_future()

        def accept(reader, writer) -> None:
            if joined.done():
                writer.close()  # the first connection only: the app's
            else:
                joined.set_result((reader, writer))

        server = await asyncio.start_unix_server(accept, path=str(line), limit=LINE_LIMIT)
        try:
            os.chmod(line, 0o600)
            try:
                self._process = await asyncio.create_subprocess_exec(
                    *mac_command(self.app, line, self.opener), stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            except OSError as exc:
                raise DesktopError(f"macOS couldn't open AI Browser's app: {exc.strerror or exc}") from None
            exited = asyncio.ensure_future(self._process.wait())
            try:
                await asyncio.wait({joined, exited}, timeout=START_WAIT, return_when=asyncio.FIRST_COMPLETED)
            finally:
                exited.cancel()
            if not joined.done():
                if self._process.returncode is not None:
                    raise DesktopError(f"macOS couldn't open AI Browser's app (open ended with "
                                       f"{self._process.returncode})")
                raise DesktopError("AI Browser's app didn't answer as it started")
        finally:
            server.close()
            with contextlib.suppress(OSError):
                line.unlink()
            with contextlib.suppress(OSError):
                folder.rmdir()
        reader, writer = joined.result()
        self._listen(reader, writer)

    def _listen(self, reader, writer) -> None:
        self._writer = writer
        self._tasks += [asyncio.create_task(self._read(reader)), asyncio.create_task(self._exited())]

    async def _read(self, reader) -> None:
        try:
            while True:
                try:
                    raw = await reader.readline()
                except ValueError:  # a line longer than LINE_LIMIT: dropped
                    continue
                except (ConnectionError, OSError):
                    break
                if not raw:
                    break
                message = _parse(raw)
                if message is not None:
                    self._dispatch(message)
        finally:
            self._gone()

    async def _exited(self) -> None:
        with contextlib.suppress(Exception):
            await self._process.wait()
        self._gone()

    def _dispatch(self, message: dict) -> None:
        kind = message["type"]
        if kind == "hello":
            if self._hello is not None and not self._hello.done():
                self._hello.set_result(message)
        elif kind == "quit":
            self.quit_by_user = True
            self._gone()
        elif kind == "shortcut":
            status = {"value": message.get("value") if isinstance(message.get("value"), str) else None,
                      "ok": message.get("ok") is True, "why": str(message.get("why") or "")[:40],
                      "pressed": message.get("pressed") is True}
            request = message.get("request") if isinstance(message.get("request"), str) else None
            if status["ok"] or request is None:
                self.shortcut = status  # what the app holds now: a refused try leaves the one before held
            waiter = self._waiters.pop(request, None) if request is not None else None
            if waiter is not None:
                if not waiter.done():
                    waiter.set_result(status)
            elif self.on_message is not None:
                self.on_message({"type": "shortcut", **status})
        elif kind == "clicked" and isinstance(message.get("id"), str) and self.on_message is not None:
            self.on_message({"type": "clicked", "id": message["id"][:20]})

    def _gone(self) -> None:
        """The app has quit, or its line or its process ended: everything waiting for it hears so."""
        if self.ended.is_set():
            return
        self.ended.set()
        if self._hello is not None and not self._hello.done():
            self._hello.set_exception(DesktopError("AI Browser's app closed as it started"))
            self._hello.exception()  # read once here: a hello nobody waits for any more leaves no warning
        for waiter in self._waiters.values():
            if not waiter.done():
                waiter.set_result({"value": None, "ok": False, "why": "gone", "pressed": False})
        self._waiters.clear()

    def send(self, message: dict) -> bool:
        """A message to the app; False when it can't get one (not started, or gone)."""
        if self._writer is None or self.ended.is_set():
            return False
        try:
            self._writer.write((json.dumps(message) + "\n").encode("utf-8"))
        except (OSError, RuntimeError):
            return False
        return True

    async def try_shortcut(self, value: str | None) -> dict:
        """Ask the app to hold `value` instead (None: no shortcut). Its answer: {value, ok, why, pressed}. When it can't
        take it, the one before stays held."""
        request = f"s{next(self._requests)}"
        waiter = asyncio.get_running_loop().create_future()
        self._waiters[request] = waiter
        if not self.send({"type": "shortcut", "value": value, "request": request}):
            self._waiters.pop(request, None)
            return {"value": value, "ok": False, "why": "gone", "pressed": False}
        try:
            return await asyncio.wait_for(waiter, ANSWER_WAIT)
        except TimeoutError:
            self._waiters.pop(request, None)
            return {"value": value, "ok": False, "why": "no answer", "pressed": False}

    def _kill(self) -> None:
        if self.system == "darwin" and self.pid is not None:
            with contextlib.suppress(OSError):
                os.kill(self.pid, signal.SIGKILL)  # the app itself: `open` only waits for it
        with contextlib.suppress(ProcessLookupError, OSError):
            self._process.kill()

    async def _end_now(self) -> None:
        """A start that failed: nothing may stay running."""
        if self._writer is not None:
            with contextlib.suppress(Exception):
                self._writer.close()  # the line ends: the app quits on that
        if self.running:
            self._kill()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._process.wait(), QUIT_WAIT)
        for task in self._tasks:
            task.cancel()
        self._gone()

    async def close(self) -> str:
        """Quit the app (the engine is stopping): asked over the line, then the line ends, and after QUIT_WAIT it is
        ended. "" (AppWindow's surface: there is never a note)."""
        if self._process is None:
            self._gone()
            return ""
        if self.running:
            self.send({"type": "quit"})
            if self._writer is not None:
                with contextlib.suppress(Exception):
                    self._writer.close()  # the line's end: the app quits on that too
            try:
                await asyncio.wait_for(self._process.wait(), QUIT_WAIT)
            except TimeoutError:
                self._kill()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._process.wait(), QUIT_WAIT)
        for task in self._tasks:
            task.cancel()
        self._gone()
        return ""


def default_desktop(home, shortcut: str | None = None) -> DesktopWindow | None:
    """This run's own app, if it is built here for this computer. None: a browser window draws AI Browser
    (app/window.py)."""
    if layout.installed(home) is None:
        return None
    return DesktopWindow(home, shortcut)
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_desktop_launch.py tests/test_desktop_static.py tests/test_portable.py -q -p no:randomly`

Expected: PASS. On Windows the macOS line's test shows as skipped.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/desktop/launch.py tests/fake_electron.py tests/fake_open.py tests/test_desktop_launch.py tests/test_desktop_static.py
git commit -m "feat(desktop): the app starts on a private line: stdin on Windows, LaunchServices and a socket on macOS"
```

### Task 9: The engine's side: the shortcut setting, the app's state in Settings, native notifications and clicks

**Files:**
- Create: `src/ai_browser/desktop/notes.py`
- Modify: `src/ai_browser/settings.py` (the `shortcut` setting)
- Modify: `src/ai_browser/app/server.py` (imports, constants, `__init__`, `_settings_payload`, `_settings_set`,
  eight new methods, `_to_watcher`, `_forward`)
- Create: `tests/fake_desktop.py`
- Test: `tests/test_desktop_server.py` (new)
- Modify: `tests/test_settings.py`, `tests/test_app_server.py`, `tests/test_accounts_seams.py` (the defaults and the
  payload grow by one key each)

**Interfaces:**
- Consumes:
  - Task 4's `SHORTCUTS`, `DEFAULT`, `SHORTCUT_ERROR`, `label` and `state`; Task 1's `layout`, `asset_for`,
    `SETUP_COMMAND` and `VERSION`;
  - Task 8's `DesktopWindow` surface: `send`, `try_shortcut`, `.shortcut`, `.on_message` and `.ended`;
  - the server's `_job`, `_send_all`, `_show_check`, `_to_watcher` and `_forward`.
- Produces:
  - **`settings.py`:** `DEFAULTS["shortcut"] = "Alt+Space"`, and `Settings.set("shortcut", value)` takes a value
    from `SHORTCUTS`, or `None` (off).
  - **`notes.py`:** `note_for(message) -> {"kind", "agent", "title", "body"} | None`, for `check_request`,
    `permission_request` and the Brain's `notify`.
  - **`AppServer`:**
    - `desktop` (the app while it runs, else `None`), `attach_desktop(desktop)` and `detach_desktop()`;
    - `_desktop_payload() -> dict`, sent as the settings payload's `"desktop"`:
      `{running, supported, set_up, version, platform ("mac" | "windows" | "other"), command, problem,
      shortcut: {value, label, state}, shortcuts: [{value, label}]}`;
    - `_from_desktop(message)`, `_shortcut_set(queue, value, request)`, `_notify_desktop(message) -> bool`,
      `_clicked(note_id)` and `_check_target(agent_id)`.
  - **A new server-to-page message:** `{"type": "focus", "agent": "a3"}` or `{"type": "focus", "brain": true}`. It is
    for AI Browser's own pages only: it isn't in `WATCHER_RECEIVES`.
  - **`tests/fake_desktop.py`:** `FakeDesktop(answers=None, launch_error=None, servers=None, note="")`, with `.sent`,
    `.tried`, `.launched`, `.closed`, `says(message)` and `quits(by_user=True)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/fake_desktop.py`:

```python
"""AI Browser's own app, faked, for the engine's tests (app/server.py, app/run.py and the pages). It has
DesktopWindow's surface (desktop/launch.py), with no process behind it. It records what the engine sends and
answers a shortcut as told. says() sends what the real app sends unasked, and quits() is its Quit. With `servers`
(test_app_run's fixture), its launch opens a socket with the window's cookie, as the app's page would."""

from __future__ import annotations

import asyncio
import json

from ui_socket import ui_socket


class FakeDesktop:
    id, name = "desktop", "AI Browser"

    def __init__(self, answers=None, launch_error=None, servers=None, note: str = ""):
        self.answers = dict(answers or {})  # a shortcut's value -> {"ok", "why"}; any other: ok
        self.launch_error = launch_error
        self.servers = servers
        self.note = note
        self.sent: list[dict] = []
        self.tried: list = []
        self.launched: list[str] = []
        self.shortcut = {"value": None, "ok": None, "why": "", "pressed": False}
        self.on_message = None
        self.ended = asyncio.Event()
        self.quit_by_user = False
        self.closed = False
        self.ws = None

    async def launch(self, url: str) -> None:
        self.launched.append(url)
        if self.launch_error is not None:
            raise self.launch_error
        if self.servers:
            server = self.servers[-1]
            self.ws = await ui_socket(server, server.url)
            await self.ws.send(json.dumps({"type": "hello", "view": "home"}))

    async def close(self) -> str:
        self.closed = True
        if self.ws is not None:
            await self.ws.close()
        self.ended.set()
        return ""

    def send(self, message: dict) -> bool:
        self.sent.append(message)
        return not self.ended.is_set()

    async def try_shortcut(self, value):
        self.tried.append(value)
        answer = {"value": value, "pressed": False, **self.answers.get(value, {"ok": True, "why": ""})}
        if answer["ok"]:
            self.shortcut = answer
        return answer

    def says(self, message: dict) -> None:
        """What the real app sends unasked: a shortcut's state as it starts or is pressed, or a click."""
        if message.get("type") == "shortcut":
            self.shortcut = {key: message.get(key) for key in ("value", "ok", "why", "pressed")}
        self.on_message(message)

    def quits(self, by_user: bool = True) -> None:
        self.quit_by_user = by_user
        self.ended.set()
```

Create `tests/test_desktop_server.py`:

```python
"""The engine's side of AI Browser's own app (app/server.py): the app's state in Settings; a shortcut the app tries
before it is saved; native notifications in fixed words, in place of Brave's; and their clicks. The app is a fake
(tests/fake_desktop.py), and the pages are sockets."""

import asyncio
import json
import sys

from fake_brave import add_agent
from fake_brave import until as settled
from fake_desktop import FakeDesktop
from test_app_server import recv, started, until
from test_bridge import EVENTS
from ui_socket import ui_socket

HOSTILE = 'Re: <img src=x onerror=alert(1)> wire $5,000 now'


def last_settings(seen: list[dict]) -> dict:
    return [message for message in seen if message["type"] == "settings"][-1]


def notes_of(app: FakeDesktop) -> list[dict]:
    return [message for message in app.sent if message["type"] == "notify"]


async def test_settings_say_whether_the_app_is_set_up_and_running(fake_claude, tmp_path):
    from ai_browser.desktop import layout
    from ai_browser.desktop.release import SETUP_COMMAND, VERSION, asset_for
    from ai_browser.desktop.shortcut import SHORTCUTS, label

    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        assert server._settings_payload()["desktop"] == {
            "running": False, "supported": asset_for() is not None, "set_up": False, "version": VERSION,
            "platform": {"darwin": "mac", "win32": "windows"}.get(sys.platform, "other"), "command": SETUP_COMMAND,
            "problem": "", "shortcut": {"value": "Alt+Space", "label": label("Alt+Space"), "state": "unknown"},
            "shortcuts": [{"value": one, "label": label(one)} for one in SHORTCUTS]}
        layout.set_problem(server.home, "The download stopped before the end: nothing was kept")
        server.attach_desktop(FakeDesktop())
        payload = server._settings_payload()["desktop"]
        assert payload["running"] and payload["problem"] == "The download stopped before the end: nothing was kept"
    finally:
        await server.stop()


async def test_a_taken_shortcut_is_said_and_another_one_is_taken_instead(fake_claude, tmp_path):  # Review Focus 1
    from ai_browser.desktop.shortcut import label
    from ai_browser.settings import read_settings

    server, url = await started(fake_claude, tmp_path, EVENTS)
    lines = []
    server.out = lines.append
    app = FakeDesktop(answers={"Control+Shift+Space": {"ok": False, "why": "taken"}})
    server.attach_desktop(app)
    try:
        async with ui_socket(server, url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "settings"}))
            await recv(ws)
            app.says({"type": "shortcut", "value": "Alt+Space", "ok": False, "why": "taken", "pressed": False})
            shown = last_settings(await until(ws, lambda message: message["type"] == "settings"))
            assert shown["desktop"]["shortcut"] == {"value": "Alt+Space", "label": label("Alt+Space"),
                                                    "state": "taken"}
            assert lines == [f"{label('Alt+Space')} is used by another app, so it does nothing in AI Browser: pick "
                             "another in Settings"]
            await ws.send(json.dumps({"type": "settings_set", "key": "shortcut", "value": "Alt+Shift+Space",
                                      "request": "shortcut"}))
            shown = last_settings(await until(ws, lambda message: message["type"] == "settings"))
            assert shown["shortcut"] == "Alt+Shift+Space" and shown["desktop"]["shortcut"]["state"] == "ready"
            await ws.send(json.dumps({"type": "settings_set", "key": "shortcut", "value": "Control+Shift+Space",
                                      "request": "shortcut"}))
            error = (await until(ws, lambda message: message["type"] == "error"))[-1]
            assert error == {"type": "error", "request": "shortcut",
                             "text": f"{label('Control+Shift+Space')} is used by another app. Pick another one."}
            await ws.send(json.dumps({"type": "settings_set", "key": "shortcut", "value": "F5", "request": "shortcut"}))
            error = (await until(ws, lambda message: message["type"] == "error"))[-1]
            assert error["text"] == "The shortcut must be one of the offered ones, or Off"
        assert read_settings(server.home)["shortcut"] == "Alt+Shift+Space"  # the one the app could take
        assert app.tried == ["Alt+Shift+Space", "Control+Shift+Space"]  # F5 never reached the app
        assert app.shortcut["value"] == "Alt+Shift+Space"
    finally:
        await server.stop()


async def test_without_the_app_a_picked_shortcut_waits_for_its_next_start(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        async with ui_socket(server, url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "settings"}))
            await recv(ws)
            await ws.send(json.dumps({"type": "settings_set", "key": "shortcut", "value": None, "request": "shortcut"}))
            shown = last_settings(await until(ws, lambda message: message["type"] == "settings"))
        assert shown["shortcut"] is None and shown["desktop"]["shortcut"]["state"] == "off"
    finally:
        await server.stop()


async def test_the_app_notifies_in_fixed_words_and_brave_doesnt_too(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    app = FakeDesktop()
    server.attach_desktop(app)
    watcher = asyncio.Queue()
    server._watcher = (object(), watcher)  # Brave's watcher, connected
    try:
        add_agent(server.agents, "a1")
        server.agents.check_event("a1", {"check": "captcha", "site": "shop.example.com", "target": "T1"})
        server.agents._broadcast({"type": "permission_request", "agent": "a1", "request": "r1", "server": "gmail",
                                  "tool": "mcp__gmail__send", "input": {"body": HOSTILE}})
        assert await settled(lambda: len(notes_of(app)) == 2)
        assert server._to_watcher({"type": "notify", "count": 2,
                                   "items": [{"sender": "Maria Lopez", "subject": HOSTILE}]}) is True
        assert [(note["id"], note["title"], note["body"]) for note in notes_of(app)] == [
            ("n1", "A bot check on shop.example.com", "An agent waits for you to solve it."),
            ("n2", "An agent is waiting for you", "It asks to use a tool. Answer in AI Home."),
            ("n3", "The Brain has 2 new notes", "Open AI Home to see what needs you.")]
        sent = json.dumps(app.sent)
        assert "Maria" not in sent and "5,000" not in sent and "gmail" not in sent  # no message, no page, no tool
        assert watcher.empty()  # Brave's watcher shows none of them while the app runs
        server.detach_desktop()
        server.agents.check_event("a1", {"check": "captcha", "site": "other.example.com", "target": "T2"})
        assert (await asyncio.wait_for(watcher.get(), 10))["type"] == "check_request"  # without the app: Brave's
    finally:
        await server.stop()


async def test_a_click_opens_the_right_place(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    app = FakeDesktop()
    server.attach_desktop(app)
    watched = []

    class Tabs:  # the user's Brave, with no tab listed: Watch brings a tab forward
        def tabs(self):
            return []

        async def watch(self, target):
            watched.append(target)

    server.tabs = Tabs()
    try:
        add_agent(server.agents, "a1")
        add_agent(server.agents, "a2")
        async with ui_socket(server, url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "home"}))
            await recv(ws)
            server.agents.check_event("a1", {"check": "captcha", "site": "shop.example.com", "target": "T1"})
            server.agents._broadcast({"type": "permission_request", "agent": "a2", "request": "r1", "server": "s",
                                      "tool": "t", "input": {}})
            assert await settled(lambda: len(notes_of(app)) == 2)
            app.says({"type": "clicked", "id": "n1"})  # the bot check: the agent's tab, in Brave
            app.says({"type": "clicked", "id": "n2"})  # the tool request: AI Home, at that agent's row
            assert (await until(ws, lambda message: message["type"] == "focus"))[-1] == {"type": "focus",
                                                                                         "agent": "a2"}
            assert watched == ["T1"] and app.sent.count({"type": "show"}) == 1
            server._to_watcher({"type": "notify", "count": 1, "items": []})
            app.says({"type": "clicked", "id": "n3"})  # the Brain's note: AI Home's Brain
            assert (await until(ws, lambda message: message["type"] == "focus"))[-1] == {"type": "focus",
                                                                                         "brain": True}
            app.says({"type": "clicked", "id": "n1"})  # the same click again: nothing
            app.says({"type": "clicked", "id": "n99"})  # one the engine never sent: nothing
            await asyncio.sleep(0.3)
            assert watched == ["T1"] and app.sent.count({"type": "show"}) == 2
    finally:
        await server.stop()


def test_the_words_never_carry_a_message_or_a_page():
    from ai_browser.desktop.notes import note_for

    assert note_for({"type": "check_request", "agent": "a3", "site": "Shop.Example.com/<b>"}) == {
        "kind": "check", "agent": "a3", "title": "A bot check", "body": "An agent waits for you to solve it."}
    assert note_for({"type": "permission_request", "agent": "nope", "input": {"text": HOSTILE}})["agent"] == ""
    assert note_for({"type": "notify", "count": True})["title"] == "The Brain has a new note"
    assert note_for({"type": "notify", "count": 5000})["title"] == "The Brain has a new note"
    assert note_for({"type": "agent"}) is None and note_for({}) is None


def test_the_watcher_never_gets_a_focus():
    from ai_browser.app.server import WATCHER_RECEIVES, for_watcher

    assert for_watcher({"type": "focus", "agent": "a1"}) is None and "focus" not in WATCHER_RECEIVES
```

In `tests/test_settings.py`:
1. In `test_the_defaults_and_a_bad_value_for_one_key`, the dict `{"window_browser": "auto", "model": None,
   "voice": False}` becomes `{"window_browser": "auto", "model": None, "voice": False, "shortcut": "Alt+Space"}`, and
   `{"window_browser": "brave", "model": None, "voice": True}` becomes
   `{"window_browser": "brave", "model": None, "voice": True, "shortcut": "Alt+Space"}`.
2. In `test_set_checks_each_value`, the tuple of refused pairs gets `("shortcut", "F5"), ("shortcut",
   ["Alt+Space"])` at its end, and these lines go after the test's last line:

```python
    assert mac.set("shortcut", None)["shortcut"] is None
    assert mac.set("shortcut", "Control+Shift+Space")["shortcut"] == "Control+Shift+Space"
```

3. In `test_a_file_from_another_computer_falls_back_key_by_key`, `{"window_browser": "auto", "model": "opus",
   "voice": False}` becomes `{"window_browser": "auto", "model": "opus", "voice": False, "shortcut": "Alt+Space"}`.
4. Add at the end:

```python
def test_the_apps_shortcut_is_one_of_the_offered_ones_or_off(tmp_path):
    from ai_browser.settings import Settings

    (tmp_path / "settings.json").write_text(json.dumps({"shortcut": "F5"}), encoding="utf-8")
    assert Settings(tmp_path, system="darwin").get()["shortcut"] == "Alt+Space"  # not offered: the default
    (tmp_path / "settings.json").write_text(json.dumps({"shortcut": None}), encoding="utf-8")
    assert Settings(tmp_path, system="darwin").get()["shortcut"] is None  # Off stays off
```

In `tests/test_app_server.py`'s `test_settings_are_saved_by_the_app_and_reach_every_window`, the assertion

```python
            assert snapshot["settings"] == {"model": None, "voice": False, "window_browser": "auto",
                                            "window": server.window_info}
```

becomes

```python
            assert snapshot["settings"] == {"model": None, "voice": False, "window_browser": "auto",
                                            "shortcut": "Alt+Space", "window": server.window_info,
                                            "desktop": server._desktop_payload()}
```

In `tests/test_accounts_seams.py` (AI accounts' seams test), the line
`assert set(settings.DEFAULTS) == {"window_browser", "model", "voice"}` becomes
`assert {"window_browser", "model", "voice"} <= set(settings.DEFAULTS)  # native-app part a adds "shortcut"`.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_desktop_server.py tests/test_settings.py -q -p no:randomly`

Expected: FAIL:
- `AttributeError: 'AppServer' object has no attribute '_desktop_payload'` (and `attach_desktop`);
- `ModuleNotFoundError: No module named 'ai_browser.desktop.notes'`;
- the settings tests fail on the missing `shortcut` key.

- [ ] **Step 3: Write the setting, the words, and the server's side**

In `src/ai_browser/settings.py`:
1. Add `from .desktop.shortcut import DEFAULT as DEFAULT_SHORTCUT` and
   `from .desktop.shortcut import SHORTCUT_ERROR, SHORTCUTS` after `from .app.window import NAMES, offered`.
2. `DEFAULTS = {"window_browser": "auto", "model": None, "voice": False}` becomes
   `DEFAULTS = {"window_browser": "auto", "model": None, "voice": False, "shortcut": DEFAULT_SHORTCUT}`.
3. In `Settings._check`, add before its final `else:`:

```python
        elif key == "shortcut":
            if value is not None and value not in SHORTCUTS:
                raise ValueError(SHORTCUT_ERROR)
```

4. In the module docstring, "the window's browser, the model and Voice" becomes "the window's browser, the model,
   Voice and the app's shortcut".

Create `src/ai_browser/desktop/notes.py`:

```python
"""What AI Browser's own app says in a notification: only what needs the user, in fixed words. Never a message's
text, a page's text, a tool's input or a sender's name. A bot check names its site, a plain host name from AI
Browser's own check report. The Brain's notes are counted."""

from __future__ import annotations

import re

SITE = re.compile(r"[a-z0-9.-]{1,253}")  # the server's CHECK_SITE
AGENT = re.compile(r"a[0-9]{1,9}")


def note_for(message: dict) -> dict | None:
    """{"kind", "agent", "title", "body"} for an event that needs the user (a bot check, a tool request, the Brain's
    new notes); None for anything else."""
    kind = message.get("type")
    agent = message.get("agent")
    agent = agent if isinstance(agent, str) and AGENT.fullmatch(agent) else ""
    if kind == "check_request":
        site = message.get("site")
        where = f" on {site}" if isinstance(site, str) and SITE.fullmatch(site) else ""
        return {"kind": "check", "agent": agent, "title": f"A bot check{where}",
                "body": "An agent waits for you to solve it."}
    if kind == "permission_request":
        return {"kind": "permission", "agent": agent, "title": "An agent is waiting for you",
                "body": "It asks to use a tool. Answer in AI Home."}
    if kind == "notify":
        count = message.get("count")
        count = count if isinstance(count, int) and not isinstance(count, bool) and 0 < count < 1000 else 1
        title = "The Brain has a new note" if count == 1 else f"The Brain has {count} new notes"
        return {"kind": "brain", "agent": "", "title": title, "body": "Open AI Home to see what needs you."}
    return None
```

In `src/ai_browser/app/server.py`:
1. Add `import sys` to the standard imports (after `import secrets`). Add after the `from ..config import …` line:

```python
from ..desktop import layout
from ..desktop.notes import note_for
from ..desktop.release import SETUP_COMMAND, asset_for
from ..desktop.release import VERSION as ELECTRON_VERSION
from ..desktop.shortcut import SHORTCUT_ERROR, SHORTCUTS
from ..desktop.shortcut import label as shortcut_label
from ..desktop.shortcut import state as shortcut_state
```

2. `SETTING_KEYS = ("model", "voice", "window_browser")` becomes
   `SETTING_KEYS = ("model", "voice", "window_browser", "shortcut")`, and after it add:

```python
NOTES_KEPT = 50  # the app's notifications whose click is still answered
PLATFORM_WORDS = {"darwin": "mac", "win32": "windows"}  # the pages say "the menu bar" or "by the clock"
APP_SILENT = "AI Browser's app didn't answer: try again"
```

3. In `AppServer.__init__`, after the line that sets `self.window_info`, add:

```python
        self.desktop = None  # AI Browser's own app while it runs (run_app attaches it): the shortcut, notifications
        self._notes: dict[str, dict] = {}  # the app's notifications: id -> {"kind", "agent"}, for their clicks
        self._note_seq = 0
```

4. In `_settings_payload`, `return {**self.settings.get(), "window": dict(self.window_info)}` becomes
   `return {**self.settings.get(), "window": dict(self.window_info), "desktop": self._desktop_payload()}`.
5. In `_settings_set`, right after the `if key not in SETTING_KEYS:` block (it ends with `return`), add:

```python
        if key == "shortcut" and self.desktop is not None:  # the app tries it first: only one it could take is saved
            self._job(self._shortcut_set(queue, message.get("value"), request))
            return
```

6. Add after `_settings_set`:

```python
    def attach_desktop(self, desktop) -> None:
        """AI Browser's own app (desktop/launch.py), for this run: its shortcut, its notifications and their clicks."""
        self.desktop = desktop
        desktop.on_message = self._from_desktop

    def detach_desktop(self) -> None:
        if self.desktop is not None:
            self.desktop.on_message = None
        self.desktop = None

    def _desktop_payload(self) -> dict:
        """Settings' and AI Home's view of AI Browser's own app: whether it is set up and running, what went wrong
        last, and the shortcut with the app's word on it."""
        value = self.settings.get()["shortcut"]
        said = self.desktop.shortcut if self.desktop is not None else {}
        return {"running": self.desktop is not None, "supported": asset_for() is not None,
                "set_up": layout.installed(self.home) is not None, "version": ELECTRON_VERSION,
                "platform": PLATFORM_WORDS.get(sys.platform, "other"), "command": SETUP_COMMAND,
                "problem": layout.problem(self.home),
                "shortcut": {"value": value, "label": shortcut_label(value),
                             "state": shortcut_state(value, said, self.desktop is not None)},
                "shortcuts": [{"value": one, "label": shortcut_label(one)} for one in SHORTCUTS]}

    async def _shortcut_set(self, queue: asyncio.Queue, value, request) -> None:
        """A shortcut picked in Settings while the app runs. The app tries it first, and only a shortcut it could take
        is saved. When another app holds it, the one before stays, and Settings says so."""
        if value is not None and value not in SHORTCUTS:
            queue.put_nowait({"type": "error", "text": SHORTCUT_ERROR, "request": request})
            return
        answer = await self.desktop.try_shortcut(value)
        if not answer.get("ok"):
            text = (f"{shortcut_label(value)} is used by another app. Pick another one." if answer.get("why") == "taken"
                    else APP_SILENT)
            queue.put_nowait({"type": "error", "text": text, "request": request})  # its page checks the saved one
            return
        try:
            self.settings.set("shortcut", value)
        except (ValueError, OSError) as exc:
            queue.put_nowait({"type": "error", "request": request,
                              "text": f"Couldn't save that setting: {getattr(exc, 'strerror', None) or exc}"})
            return
        self._send_all({"type": "settings", **self._settings_payload()})

    def _from_desktop(self, message: dict) -> None:
        """What the app says unasked: the shortcut it holds (or can't, or its first press), and a click on one of its
        notifications."""
        kind = message.get("type")
        if kind == "shortcut":
            if message.get("ok") is False and isinstance(message.get("value"), str):
                self.out(f"{shortcut_label(message['value'])} is used by another app, so it does nothing in AI "
                         "Browser: pick another in Settings")
            self._send_all({"type": "settings", **self._settings_payload()})
        elif kind == "clicked" and isinstance(message.get("id"), str):
            self._job(self._clicked(message["id"]))

    def _notify_desktop(self, message: dict) -> bool:
        """A notification from AI Browser's own app, in place of Brave's, in fixed words (desktop/notes.py). False when
        the app isn't running: Brave's watcher shows it then."""
        desktop = self.desktop
        note = note_for(message) if desktop is not None and not desktop.ended.is_set() else None
        if note is None:
            return False
        self._note_seq += 1
        note_id = f"n{self._note_seq}"
        self._notes[note_id] = {"kind": note["kind"], "agent": note["agent"]}
        while len(self._notes) > NOTES_KEPT:
            self._notes.pop(next(iter(self._notes)))
        return desktop.send({"type": "notify", "id": note_id, "title": note["title"], "body": note["body"]})

    async def _clicked(self, note_id: str) -> None:
        """A click on one of the app's notifications. A bot check brings the agent's tab forward, in Brave. Anything
        else brings the app's window forward, on AI Home, at that agent's row (or the Brain)."""
        note = self._notes.pop(note_id, None)
        if note is None or self.desktop is None:
            return
        if note["kind"] == "check" and self._check_target(note["agent"]) is not None:
            await self._show_check(note["agent"])
            return
        self.desktop.send({"type": "show"})
        self._send_all({"type": "focus", **({"agent": note["agent"]} if note["agent"] else {"brain": True})})

    def _check_target(self, agent_id: str) -> str | None:
        """The tab in Brave where this agent's bot check waits, if there is one (a live view's has none)."""
        agent = self.agents.agents.get(agent_id)
        check = agent.check if agent is not None else None
        if check is None or check.get("live") or not check.get("target") or self.tabs is None:
            return None
        return check["target"]
```

7. In `_to_watcher`, add as its first lines, right after its docstring:

```python
        if message.get("type") == "notify" and self._notify_desktop(message):
            return True  # the Brain's new notes: AI Browser's own app says so, and Brave's watcher doesn't too
```

8. In `_forward`, replace

```python
            if message.get("type") in ("permission_request", "check_request"):
                self._to_watcher(message)  # a Brave notification too
```

with

```python
            if message.get("type") in ("permission_request", "check_request") and not self._notify_desktop(message):
                self._to_watcher(message)  # Brave's notification, while AI Browser's own app isn't running
```

- [ ] **Step 4: Run them, and the server's and settings' other tests, to see them pass**

Run: `uv run pytest tests/test_desktop_server.py tests/test_settings.py tests/test_app_server.py tests/test_accounts_seams.py tests/test_watcher_rules.py tests/test_portable.py -q -p no:randomly`

Expected: PASS. If one of AI accounts' server tests pins the settings payload exactly, add `"shortcut": "Alt+Space"`
and `"desktop": server._desktop_payload()` to it, as in `test_app_server.py`.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/desktop/notes.py src/ai_browser/settings.py src/ai_browser/app/server.py tests/fake_desktop.py tests/test_desktop_server.py tests/test_settings.py tests/test_app_server.py tests/test_accounts_seams.py
git commit -m "feat(server): the app's state in Settings, its shortcut tried before it is saved, and native notifications"
```

### Task 10: `ai-browser app` opens the app, falls back to a browser window, and ends on Quit

**Files:**
- Modify: `src/ai_browser/app/run.py` (imports, three texts, `app_text`, `setup_hint`, `_open_app`, `run_app`, `_run`,
  `_until_closed`)
- Modify: `src/ai_browser/cli.py` (`--window`'s help)
- Modify: `tests/conftest.py` (one autouse fixture after `_no_real_window`)
- Test: `tests/test_desktop_run.py` (new)

**Interfaces:**
- Consumes:
  - Task 8's `default_desktop(home, shortcut)` and the `DesktopWindow` surface (`launch`, `close`, `note`, `ended`,
    `quit_by_user`);
  - Task 6's `stale`; Task 1's `layout`, `asset_for` and `SETUP_COMMAND`;
  - Task 9's `server.attach_desktop` and `detach_desktop`, and the `shortcut` setting;
  - wave B's `_call`, `_first_window`, `ready_text`, `NO_WINDOW`, `default_launcher` and `choices`.
- Produces:
  - `run_app(..., launcher=None, desktop=None)`. `desktop` is a factory `(home, shortcut) -> window | None`; the
    default is `default_desktop`, and tests pass their own.
  - `_open_app(home, server, url, desktop, window_browser, out)`: the launched app, or `None`.
  - `_until_closed(server, stop, window=None)`. A window with an `ended` event ends the run when that is set;
    anything else ends it on wave B's socket rule.
  - The texts: `app_text(system=None)`, `setup_hint(home, system=None, machine=None)`, `APP_ENDED`, `NO_APP_PAGE` and
    `UPDATING`.
  - **`conftest.py`'s `_no_real_desktop` (autouse):** `run.default_desktop` returns `None`, so no test starts the
    real app.

- [ ] **Step 1: Write the failing tests**

In `tests/conftest.py`, add after the `_no_real_window` fixture:

```python
@pytest.fixture(autouse=True)
def _no_real_desktop(monkeypatch):
    """No test starts AI Browser's own app: run_app's tests pass desktop= (tests/fake_desktop.py)."""
    import ai_browser.app.run as run

    monkeypatch.setattr(run, "default_desktop", lambda home, shortcut=None: None)
```

Create `tests/test_desktop_run.py`:

```python
"""`ai-browser app` with AI Browser's own app (app/run.py).
- It opens the app when the app is set up.
- It opens a browser window when the app isn't set up, with --window, or when the app can't start. In that last
  case it says why, and keeps the reason for Settings.
- Quit in the app ends everything, and so does Ctrl-C.
The app is a fake (tests/fake_desktop.py), and so is the browser window (tests/fake_window.py)."""

import asyncio

from fake_desktop import FakeDesktop
from fake_window import SocketWindow
from test_app_run import quiet, servers  # noqa: F401  (a fixture)


async def test_the_app_opens_and_its_quit_ends_everything(fake_claude, tmp_path, servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    app, lines, asked, given = FakeDesktop(servers=servers), [], [], []

    async def ready(url, opened):
        assert opened is app and servers[0].desktop is app
        app.quits()  # Quit, from the menu-bar icon

    def desktop(home, shortcut):
        given.append(shortcut)
        return app

    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, ready=ready, out=lines.append,
                                              launcher=asked.append, desktop=desktop), 60)
    assert code == 0 and asked == [] and app.closed  # no browser window, and the app was told to go
    assert given == ["Alt+Space"]  # the shortcut from Settings, for the app to hold as it starts
    assert app.launched[0].startswith(servers[0].url + "/open?code=")
    assert run.app_text() in lines and run.APP_ENDED not in lines
    assert servers[0].window_info["using"] == "desktop"


async def test_ctrl_c_quits_the_app(fake_claude, tmp_path, servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    app, stop = FakeDesktop(servers=servers), asyncio.Event()
    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, ready=lambda url, opened: stop.set(),
                                              stop=stop, out=quiet, desktop=lambda home, shortcut: app), 60)
    assert code == 0 and app.closed and not app.quit_by_user


async def test_the_app_ending_by_itself_ends_the_run_and_says_so(fake_claude, tmp_path, servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    app, lines = FakeDesktop(servers=servers), []
    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, out=lines.append,
                                              ready=lambda url, opened: app.quits(by_user=False),
                                              desktop=lambda home, shortcut: app), 60)
    assert code == 0 and run.APP_ENDED in lines


async def test_before_the_app_is_set_up_a_browser_window_opens_and_offers_it(fake_claude, tmp_path, servers,
                                                                              monkeypatch):
    from ai_browser.app import run
    from ai_browser.desktop.release import ASSETS, SETUP_COMMAND

    runner, _, _ = fake_claude
    monkeypatch.setattr(run, "asset_for", lambda system=None, machine=None: ASSETS[0])  # a computer the app runs on
    window, lines, stop = SocketWindow(servers), [], asyncio.Event()
    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, ready=lambda url, opened: stop.set(),
                                              stop=stop, out=lines.append, launcher=lambda setting: window), 60)
    assert code == 0 and window.closed and servers[0].desktop is None  # default_desktop: none (conftest)
    printed = "\n".join(lines)
    assert run.ready_text() in printed and f"run `{SETUP_COMMAND}` once" in printed


async def test_an_app_that_cant_start_leaves_a_browser_window_and_the_reason(fake_claude, tmp_path,
                                                                             servers):  # Review Focus 2
    from ai_browser.app import run
    from ai_browser.desktop import layout
    from ai_browser.desktop.launch import DesktopError

    runner, _, _ = fake_claude
    home, window, lines, stop = tmp_path / "home", SocketWindow(servers), [], asyncio.Event()
    broken = FakeDesktop(launch_error=DesktopError("AI Browser's app could not start: test"))
    code = await asyncio.wait_for(run.run_app(home, claude=runner, ready=lambda url, opened: stop.set(), stop=stop,
                                              out=lines.append, launcher=lambda setting: window,
                                              desktop=lambda home, shortcut: broken), 60)
    assert code == 0 and window.urls and servers[0].desktop is None
    assert "AI Browser's app could not start: test. AI Browser opens in a browser window this time." in lines
    assert layout.problem(home) == "AI Browser's app could not start: test"  # Settings shows it
    stop = asyncio.Event()
    good = FakeDesktop(servers=servers)
    assert await asyncio.wait_for(run.run_app(home, claude=runner, ready=lambda url, opened: stop.set(), stop=stop,
                                              out=quiet, desktop=lambda home, shortcut: good), 60) == 0
    assert layout.problem(home) == ""  # the next good start forgets it


async def test_window_asks_for_a_browser_window_for_this_run(fake_claude, tmp_path, servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    asked, window, stop = [], SocketWindow(servers), asyncio.Event()

    def desktop(home, shortcut):
        asked.append(home)
        return FakeDesktop(servers=servers)

    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, ready=lambda url, opened: stop.set(),
                                              stop=stop, out=quiet, window_browser="chrome",
                                              launcher=lambda setting: window, desktop=desktop), 60)
    assert code == 0 and asked == [] and window.urls


def test_the_app_texts_say_how_to_stop_on_each_computer(tmp_path):
    from ai_browser.app.run import app_text, setup_hint

    mac, windows = app_text("darwin"), app_text("win32")
    assert mac == ("AI Browser is open as its own app: AI Home shows every agent, tab and skill.\n"
                   "Closing its window keeps it running in the menu bar. To stop it, press ⌘Q or choose Quit from its "
                   "menu-bar icon, or press Ctrl-C here.")
    assert "by the clock" in windows and "⌘" not in windows and "Ctrl-C here" in windows
    assert setup_hint(tmp_path, "linux", "x86_64") == ""  # where the app doesn't run, nothing is offered
    assert setup_hint(tmp_path, "darwin", "arm64") == ("\nAI Browser can run as its own app, with a shortcut and "
                                                       "notifications: run `uv run ai-browser doctor --setup` once.")
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_desktop_run.py -q -p no:randomly`

Expected: FAIL. `run_app()` has no `desktop` parameter (`TypeError: run_app() got an unexpected keyword argument
'desktop'`), and there is no `app_text`.

- [ ] **Step 3: Open the app first, and end on its Quit**

In `src/ai_browser/app/run.py`:
1. Add to the imports:

```python
from ..desktop import layout
from ..desktop.assemble import stale
from ..desktop.launch import default_desktop
from ..desktop.release import SETUP_COMMAND, asset_for
```

2. Add after `RETIRED_APP = (…)`:

```python
APP_ENDED = "AI Browser's app closed by itself, so AI Browser stops too."
NO_APP_PAGE = ("AI Browser's app started, but its page never connected. Try again, or use a browser window: "
               "`uv run ai-browser app --window chrome`")
UPDATING = "Updating AI Browser's app for this version (nothing is downloaded)…"
```

3. Add after `ready_text`:

```python
def app_text(system: str | None = None) -> str:
    """What the terminal says once AI Browser's own app is open."""
    where = platforms.shortcut("in the menu bar", "by the clock", system)
    stop = platforms.shortcut("press ⌘Q or choose Quit from its menu-bar icon", "choose Quit from its icon there",
                              system)
    return ("AI Browser is open as its own app: AI Home shows every agent, tab and skill.\n"
            f"Closing its window keeps it running {where}. To stop it, {stop}, or press Ctrl-C here.")


def setup_hint(home, system: str | None = None, machine: str | None = None) -> str:
    """The browser window's extra line, on a computer AI Browser's own app runs on, while it isn't set up."""
    if asset_for(system, machine) is None or layout.installed(home, system) is not None:
        return ""
    return f"\nAI Browser can run as its own app, with a shortcut and notifications: run `{SETUP_COMMAND}` once."
```

4. `run_app`'s signature gets `desktop: Callable | None = None` after `launcher: Callable | None = None`. Its
   docstring's last sentence becomes: "`launcher` takes the window's setting and returns the browser window
   (default_launcher); `desktop` takes the home and the shortcut and returns AI Browser's own app, or None while it
   isn't set up (default_desktop). Tests pass their own." The call
   `return await _run(home, model, claude, ready, stop or asyncio.Event(), out, window_browser, launcher)` becomes
   `return await _run(home, model, claude, ready, stop or asyncio.Event(), out, window_browser, launcher, desktop)`.
5. `_until_closed` becomes:

```python
async def _until_closed(server: AppServer, stop: asyncio.Event, window=None) -> None:
    """Until `stop`. AI Browser's own app: until it has quit or gone (closing its window only hides it). A browser
    window: until no window socket has been open for WINDOW_GRACE seconds in a row."""
    ended = getattr(window, "ended", None)
    if isinstance(ended, asyncio.Event):
        waiting = [asyncio.ensure_future(stop.wait()), asyncio.ensure_future(ended.wait())]
        try:
            await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in waiting:
                task.cancel()
        return
    empty_since: float | None = None
    while not stop.is_set():
        if server.window_count:
            empty_since = None
        elif empty_since is None:
            empty_since = time.monotonic()
        elif time.monotonic() - empty_since >= WINDOW_GRACE:
            return
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), POLL)
```

6. Add before `_run`:

```python
async def _open_app(home: Path, server: AppServer, url: str, desktop: Callable | None, window_browser: str | None,
                    out: Callable[[str], None]):
    """AI Browser's own app, started and linked; or None, and this run uses a browser window. That happens when the
    app isn't set up, when --window asked for one, or when the app couldn't start: then why is said, and kept for
    Settings."""
    if window_browser is not None:
        return None
    app = (desktop or default_desktop)(home, server.settings.get()["shortcut"])
    if app is None:
        return None
    if stale(home):
        out(UPDATING)
    server.attach_desktop(app)
    try:
        await _call(app.launch, f"{url}/open?code={server.new_launch_code()}")
    except WindowError as exc:
        server.detach_desktop()
        layout.set_problem(home, str(exc))
        out(f"{exc}. AI Browser opens in a browser window this time.")
        return None
    layout.set_problem(home, None)
    if app.note:
        out(app.note)
    return app
```

7. `_run`'s signature gets `desktop: Callable | None` after `launcher: Callable | None`. In `_run`, replace this block
   (from `try:` after `await brave.start()` to `out(ready_text())`):

```python
        try:
            window = (launcher or default_launcher(home))(window_browser or server.settings.get()["window_browser"])
        except WindowError as exc:
            out(f"error: {exc}")
            return 1
        if window.note:
            out(window.note)
        server.window_info = {"using": window.id, "name": window.name, "note": window.note,
                              "choices": await asyncio.to_thread(choices)}  # detection once, at start
        try:
            await _call(window.launch, f"{url}/open?code={server.new_launch_code()}")
        except WindowError as exc:
            out(f"error: {exc}")
            return 1
        if not await _first_window(server, stop):
            if stop.is_set():
                return 0
            out(NO_WINDOW.format(name=window.name))
            return 1
        out(ready_text())
```

with:

```python
        window = await _open_app(home, server, url, desktop, window_browser, out)  # AI Browser's own app, if set up
        if window is not None:
            server.window_info = {"using": window.id, "name": window.name, "note": "",
                                  "choices": await asyncio.to_thread(choices)}
        else:  # a browser window, as before the app
            try:
                window = (launcher or default_launcher(home))(window_browser or server.settings.get()["window_browser"])
            except WindowError as exc:
                out(f"error: {exc}")
                return 1
            if window.note:
                out(window.note)
            server.window_info = {"using": window.id, "name": window.name, "note": window.note,
                                  "choices": await asyncio.to_thread(choices)}  # detection once, at start
            try:
                await _call(window.launch, f"{url}/open?code={server.new_launch_code()}")
            except WindowError as exc:
                out(f"error: {exc}")
                return 1
        if not await _first_window(server, stop):
            if stop.is_set():
                return 0
            out(NO_APP_PAGE if server.desktop is not None else NO_WINDOW.format(name=window.name))
            return 1
        out(app_text() if server.desktop is not None else ready_text() + setup_hint(home))
```

8. In `_run`, `await _until_closed(server, stop)` becomes:

```python
        await _until_closed(server, stop, window)
        if server.desktop is not None and window.ended.is_set() and not window.quit_by_user and not stop.is_set():
            out(APP_ENDED)
```

9. The module docstring's second sentence becomes: "AI Browser's own app (desktop/) opens when it is set up: closing
   its window hides it, and its Quit ends the run. Until it is set up (and with --window), a browser window draws AI
   Browser instead: an installed browser in --app mode on a profile of the app's own, with no debugging port
   (app/window.py)." Keep the rest of the docstring.

In `src/ai_browser/cli.py`, the `--window` argument's `help=` becomes
`"a browser window for this run, drawn by this browser (default: AI Browser's own app once it is set up, else the "
"Settings choice)"`.

- [ ] **Step 4: Run them, and run_app's other tests, to see them pass**

Run: `uv run pytest tests/test_desktop_run.py tests/test_app_run.py tests/test_cli.py tests/test_portable.py -q -p no:randomly`

Expected: PASS. The existing `run_app` tests still open their browser window: `default_desktop` gives `None` under
conftest.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/run.py src/ai_browser/cli.py tests/conftest.py tests/test_desktop_run.py
git commit -m "feat(app): ai-browser app opens AI Browser's own app, falls back to a browser window, and ends on Quit"
```

### Task 11: The pages: Settings → AI Browser app, AI Home's offer, a click's focus, the microphone's name

**Files:**
- Modify: `src/ai_browser/app/ui/settings.html` (a section before **App window**), `settings.js`
- Modify: `src/ai_browser/app/ui/home.html` (a card after the browser card), `home.js`, `home.css`
- Modify: `src/ai_browser/app/ui/talk.js` (`browserName`)
- Test: `tests/test_desktop_pages.py` (new)

**Interfaces:**
- Consumes:
  - Task 9's settings payload `desktop` (`{running, supported, set_up, version, platform, command, problem,
    shortcut: {value, label, state}, shortcuts}`);
  - its `settings_set` for `shortcut` (an `error` with `request: "shortcut"` when the app can't take it);
  - its `focus` message; nav.js's `openTab`; the `stack` and `home` fixtures; `tests/fake_desktop.py`.
- Produces:
  - **Settings' ids:** `app-section`, `app-state`, `app-shortcut`, `shortcut-choices` (radio inputs, one per
    shortcut and Off: `value=""` for Off), `shortcut-note`, `app-setup`, `app-adds`, `app-command`, `app-copy`,
    `app-copied` and `app-problem`.
  - **AI Home's ids:** `app-card`, `app-card-adds`, `app-card-command`, `app-card-copy`, `app-card-copied`,
    `app-card-problem` and `app-card-close`. A row in focus gets the class `focus` for 2 seconds.
  - **`talk.js`:** `browserName(nav)` gives "AI Browser" inside AI Browser's own app (its user agent says
    `Electron/`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_desktop_pages.py`:

```python
"""AI Browser's own app on AI Browser's pages, in a throwaway headless Chrome against a real app server (the `stack`
fixture):
- Settings → AI Browser app: the app's state, the shortcut, the setup command, and what went wrong;
- AI Home's offer of the setup;
- a notification's click landing on AI Home's row;
- the microphone's steps naming AI Browser.
The app is a fake (tests/fake_desktop.py). Every text is set as text."""

import asyncio
import json

import pytest

from ai_browser.chrome import chrome_binary
from fake_brave import add_agent
from fake_desktop import FakeDesktop
from test_home import home, open_page, stack, until  # noqa: F401  (fixtures)

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
PROBLEM = "The download stopped before the end: nothing was kept"


def tell_pages(stack) -> None:
    server = stack["server"]
    server._send_all({"type": "settings", **server._settings_payload()})


async def open_settings(stack):
    _, js = await open_page(stack["cdp"], stack["url"] + "/settings")  # the stack's browser has the window's cookie
    assert await until(js, "document.getElementById('status').dataset.state === 'connected'")
    return js


@CHROME
async def test_settings_says_the_shortcut_is_taken_and_offers_another(stack):  # Review Focus 1
    from ai_browser.desktop.shortcut import SHORTCUTS, label
    from ai_browser.settings import read_settings

    app = FakeDesktop()
    stack["server"].attach_desktop(app)
    settings = await open_settings(stack)
    app.says({"type": "shortcut", "value": "Alt+Space", "ok": False, "why": "taken", "pressed": False})
    taken = f"{label('Alt+Space')} is used by another app, so it does nothing here. Pick another shortcut."
    assert await until(settings, f"document.getElementById('shortcut-note').textContent === {json.dumps(taken)}")
    assert await settings("document.getElementById('app-state').textContent") == "AI Browser runs as its own app."
    assert await settings("document.getElementById('window-section').hidden") is True  # the window's browser: unused
    assert await settings("[...document.querySelectorAll('#shortcut-choices label')].map((one) => one.textContent)"
                          ) == [label(one) for one in SHORTCUTS] + ["Off"]
    await settings("document.querySelector('#shortcut-choices input[value=\"Alt+Shift+Space\"]').click(); true")
    ready = (f"{label('Alt+Shift+Space')} shows and hides AI Browser. Press it once to check: if another app answers "
             "instead, pick another shortcut.")
    assert await until(settings, f"document.getElementById('shortcut-note').textContent === {json.dumps(ready)}")
    assert read_settings(stack["home"])["shortcut"] == "Alt+Shift+Space"
    assert await settings("document.querySelector('#shortcut-choices input:checked').value") == "Alt+Shift+Space"


@CHROME
async def test_a_shortcut_the_app_cant_take_leaves_the_one_before_checked(stack):
    from ai_browser.desktop.shortcut import label

    stack["server"].attach_desktop(FakeDesktop(answers={"Control+Shift+Space": {"ok": False, "why": "taken"}}))
    settings = await open_settings(stack)
    await settings("document.querySelector('#shortcut-choices input[value=\"Control+Shift+Space\"]').click(); true")
    said = f"{label('Control+Shift+Space')} is used by another app. Pick another one."
    assert await until(settings, f"document.getElementById('shortcut-note').textContent === {json.dumps(said)}")
    assert await settings("document.querySelector('#shortcut-choices input:checked').value") == "Alt+Space"


@CHROME
async def test_settings_and_ai_home_offer_the_app_and_say_what_went_wrong(home, monkeypatch):  # Review Focus 2
    from ai_browser.app import server as server_module
    from ai_browser.desktop import layout
    from ai_browser.desktop.release import ASSETS, SETUP_COMMAND

    js, stack = home
    monkeypatch.setattr(server_module, "asset_for", lambda system=None, machine=None: ASSETS[0])  # the app runs here
    layout.set_problem(stack["home"], PROBLEM)
    tell_pages(stack)
    said = f"The last try didn't work: {PROBLEM}"
    assert await until(js, "!document.getElementById('app-card').hidden")
    assert await js("document.getElementById('app-card-command').textContent") == SETUP_COMMAND
    assert await js("document.getElementById('app-card-problem').textContent") == said
    settings = await open_settings(stack)
    assert await until(settings, "!document.getElementById('app-setup').hidden")
    assert await settings("document.getElementById('app-command').textContent") == SETUP_COMMAND
    assert await settings("document.getElementById('app-problem').textContent") == said
    assert await settings("document.getElementById('app-state').textContent") == ("AI Browser runs in a browser "
                                                                                 "window now.")
    assert await settings("document.getElementById('window-section').hidden") is False  # a browser window is in use
    await js("document.getElementById('app-card-close').click(); true")  # Not now
    assert await until(js, "document.getElementById('app-card').hidden")


@CHROME
async def test_ai_home_offers_nothing_while_the_app_runs(home, monkeypatch):
    from ai_browser.app import server as server_module
    from ai_browser.desktop.release import ASSETS

    js, stack = home
    monkeypatch.setattr(server_module, "asset_for", lambda system=None, machine=None: ASSETS[0])
    stack["server"].attach_desktop(FakeDesktop())
    tell_pages(stack)
    await asyncio.sleep(0.5)
    assert await js("document.getElementById('app-card').hidden") is True


@CHROME
async def test_a_notifications_click_lands_on_the_agents_row_or_the_brain(home):
    js, stack = home
    server = stack["server"]
    add_agent(server.agents, "a1")
    server._send_all({"type": "agent", "agent": server.agents.agents["a1"].public()})
    row = "document.querySelector('#agents .agent[data-id=\"a1\"]')"
    assert await until(js, f"{row} !== null")
    server._send_all({"type": "focus", "agent": "a1"})
    assert await until(js, f"{row}.classList.contains('focus')")
    server._send_all({"type": "focus", "brain": True})
    assert await until(js, "document.getElementById('brain').classList.contains('focus')")
    assert await js("location.pathname") == "/home"  # AI Home by itself (here): no tab menu to ask, it stays put


@CHROME
async def test_the_microphones_steps_name_ai_browser_in_its_own_app(home):
    js, _ = home
    name = await js("import('/talk.js').then(({ browserName }) => browserName({ userAgent: 'Mozilla/5.0 "
                    "(Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) ai-browser-app/0.1.0 "
                    "Chrome/150.0.0.0 Electron/44.5.1 Safari/537.36', userAgentData: { brands: [{ brand: 'Chromium' "
                    "}] } }))")
    assert name == "AI Browser"
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_desktop_pages.py -q -p no:randomly`

Expected: FAIL. There is no `#shortcut-note`, `#app-card` or `#app-state`, the row never gets `focus`, and
`browserName` says "Google Chrome".

- [ ] **Step 3: Write the section, the card, the focus and the name**

In `src/ai_browser/app/ui/settings.html`, add this section first inside `<main class="settings">`, before
`<section id="window-section"`:

```html
  <section id="app-section" class="card" aria-labelledby="app-title">
    <h2 id="app-title">AI Browser app</h2>
    <p id="app-state"></p>
    <div id="app-shortcut" hidden>
      <p>The shortcut shows and hides AI Browser from any app.</p>
      <div id="shortcut-choices" class="choices" role="radiogroup" aria-label="Shortcut"></div>
      <p id="shortcut-note" class="muted" role="status"></p>
    </div>
    <div id="app-setup" hidden>
      <p id="app-adds"></p>
      <p>To set it up, run this in a terminal. It shows what it downloads, and asks first.</p>
      <p><code id="app-command" class="app-command"></code>
        <button id="app-copy" class="ghost" type="button">Copy</button>
        <span id="app-copied" class="muted" role="status"></span></p>
    </div>
    <p id="app-problem" class="muted" hidden></p>
  </section>
```

In `src/ai_browser/app/ui/settings.js`:
1. Its first comment line becomes "// Settings, in its tab of AI Browser's window: AI Browser's own app (its state,
   its shortcut, its setup),". Keep the comment's other lines.
2. Add before `function handle(`:

```js
const SHORTCUT_NOTES = { // what Settings says about the saved shortcut, by its state (the app's word on it)
  ready: (label) => `${label} shows and hides AI Browser. Press it once to check: if another app answers instead, `
    + "pick another shortcut.",
  works: (label) => `${label} shows and hides AI Browser.`,
  taken: (label) => `${label} is used by another app, so it does nothing here. Pick another shortcut.`,
  off: () => "No shortcut.",
  unknown: () => "",
};

function appState(app) {
  if (app.running) return "AI Browser runs as its own app.";
  if (app.set_up) return "AI Browser's own app is set up, but this run uses a browser window.";
  if (app.supported) return "AI Browser runs in a browser window now.";
  return "AI Browser's own app runs on macOS and on Windows (x64).";
}

function renderShortcut(app) { // the offered shortcuts and Off, the saved one checked
  const options = [...(app.shortcuts || []), { value: null, label: "Off" }];
  const box = $("shortcut-choices");
  if (box.dataset.options !== JSON.stringify(options)) { // rebuilt only when the choices change
    box.textContent = "";
    for (const option of options) {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "radio";
      input.name = "shortcut";
      input.value = option.value ?? "";
      input.addEventListener("change", () => {
        if (!input.checked) return;
        link.send({ type: "settings_set", key: "shortcut", value: option.value, request: "shortcut" });
      });
      label.append(input, document.createTextNode(option.label));
      box.append(label);
    }
    box.dataset.options = JSON.stringify(options);
  }
  const saved = app.shortcut?.value ?? "";
  for (const input of box.querySelectorAll("input")) input.checked = input.value === saved;
  const note = SHORTCUT_NOTES[app.shortcut?.state] || SHORTCUT_NOTES.unknown;
  $("shortcut-note").textContent = note(app.shortcut?.label || "");
}

function renderApp() { // AI Browser's own app: running, set up, or offered (its setup command and the last problem)
  const app = current?.desktop;
  if (!app) return;
  $("window-section").hidden = Boolean(app.running); // the window's browser matters only without the app
  $("app-state").textContent = appState(app);
  $("app-shortcut").hidden = !app.running;
  if (app.running) renderShortcut(app);
  $("app-setup").hidden = Boolean(app.running || app.set_up || !app.supported);
  $("app-adds").textContent = `Its own app adds ${app.platform === "mac" ? "a menu-bar icon" : "an icon by the clock"}`
    + ", a shortcut and notifications.";
  $("app-command").textContent = app.command || "";
  $("app-problem").textContent = app.problem ? `The last try didn't work: ${app.problem}` : "";
  $("app-problem").hidden = !app.problem;
}
```

3. In `handle`, call `renderApp();` right after `renderWindow();` in the `snapshot` branch and in the `settings`
   branch. Then add these three lines right before the line
   `} else if (message.type === "error" && message.request === "window") {`:

```js
  } else if (message.type === "error" && message.request === "shortcut") {
    renderApp(); // the saved one is checked again
    $("shortcut-note").textContent = message.text || "";
```

4. Add after the line `guardLinks(link);`:

```js
$("app-copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("app-command").textContent);
    $("app-copied").textContent = "Copied.";
  } catch {
    $("app-copied").textContent = "Copy didn't work: select the command and copy it yourself.";
  }
});
```

In `src/ai_browser/app/ui/home.html`, add right after the `browser-card` section (before `<main>`):

```html
<section id="app-card" class="card app-card" aria-label="AI Browser's own app" hidden>
  <div class="line"><strong>Get AI Browser's own app</strong>
    <button id="app-card-close" class="ghost" type="button">Not now</button></div>
  <p id="app-card-adds" class="muted"></p>
  <p class="muted">To set it up, run this in a terminal. It shows what it downloads, and asks first.</p>
  <p><code id="app-card-command" class="app-command"></code>
    <button id="app-card-copy" class="ghost" type="button">Copy</button>
    <span id="app-card-copied" class="muted" role="status"></span></p>
  <p id="app-card-problem" class="muted" hidden></p>
</section>
```

In `src/ai_browser/app/ui/home.js`:
1. Add after `function applySettings(…) { … }`:

```js
let appCardClosed = false; // Not now: hidden until this page loads again

function renderAppCard(app) { // the offer of AI Browser's own app, while it isn't set up (a browser window draws us)
  const show = Boolean(app && !app.running && !app.set_up && app.supported && !appCardClosed);
  $("app-card").hidden = !show;
  if (!show) return;
  $("app-card-adds").textContent = `It adds ${app.platform === "mac" ? "a menu-bar icon" : "an icon by the clock"}, `
    + "a shortcut and notifications.";
  $("app-card-command").textContent = app.command || "";
  $("app-card-problem").textContent = app.problem ? `The last try didn't work: ${app.problem}` : "";
  $("app-card-problem").hidden = !app.problem;
}

function focusOn(message) { // a notification's click: AI Home's tab, and the agent's row (or the Brain) in view
  if (window.parent !== window) openTab("/home"); // inside the tab menu: show AI Home's tab
  const target = message.brain ? $("brain") : rows.get(String(message.agent || ""));
  if (!target) return;
  target.scrollIntoView({ block: "center" });
  target.classList.add("focus");
  setTimeout(() => target.classList.remove("focus"), 2000);
}
```

2. In `applySettings`, add as its last line: `renderAppCard(settings.desktop);`.
3. In `handle`'s `switch`, add before `case "error":`:

```js
    case "focus":
      focusOn(message);
      break;
```

4. Add next to the other button listeners at the end:

```js
$("app-card-close").addEventListener("click", () => {
  appCardClosed = true;
  $("app-card").hidden = true;
});
$("app-card-copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("app-card-command").textContent);
    $("app-card-copied").textContent = "Copied.";
  } catch {
    $("app-card-copied").textContent = "Copy didn't work: select the command and copy it yourself.";
  }
});
```

Add to the end of `src/ai_browser/app/ui/home.css` (Settings uses it too):

```css
.app-card { max-width: 1180px; margin: 12px auto 0; }
.app-card .line { display: flex; align-items: center; gap: 10px; justify-content: space-between; }
.app-command { display: inline-block; font: 12px/1.45 ui-monospace, Menlo, monospace; background: var(--soft);
               border-radius: 8px; padding: 4px 8px; user-select: all; }
.agent.focus, #brain.focus { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 12px; }
```

In `src/ai_browser/app/ui/talk.js`, `browserName` gets this first line in its body:

```js
  if (/\bElectron\//.test(String(nav.userAgent || ""))) return "AI Browser"; // AI Browser's own app (Electron)
```

- [ ] **Step 4: Run them, and the pages' other tests, to see them pass**

Run: `uv run pytest tests/test_desktop_pages.py tests/test_ui_static.py tests/test_portable.py -q -p no:randomly`

Expected: PASS. The static tests find no `innerHTML`, no inline script, and no "⌘" or "this Mac" in the pages.

Run: `uv run pytest tests/test_home.py tests/test_talk.py tests/test_tab_menu.py -q -p no:randomly`

Expected: PASS.

Run: `uv run pytest tests/test_accounts_pages.py -q -p no:randomly`

Expected: PASS (AI accounts' Settings section is unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/ui/settings.html src/ai_browser/app/ui/settings.js src/ai_browser/app/ui/home.html src/ai_browser/app/ui/home.js src/ai_browser/app/ui/home.css src/ai_browser/app/ui/talk.js tests/test_desktop_pages.py
git commit -m "feat(ui): Settings → AI Browser app, AI Home's offer, and a notification's click on AI Home's row"
```

### Task 12: The README, the whole suite, and the hand checks on the Mac and on Windows

**Files:**
- Modify: `README.md` (a new section, the Commands block, a Safety note, a Development note)
- Modify: `tests/test_desktop_static.py` (one test at the end)

**Interfaces:**
- Consumes: everything above.
- Produces: the README's **AI Browser's own app** section, and the user's hand checks, recorded in the ledger.

- [ ] **Step 1: Write the failing test**

Add to the end of `tests/test_desktop_static.py`:

```python
def test_the_readme_explains_the_app():
    text = " ".join((SRC.parents[1] / "README.md").read_text(encoding="utf-8").split())
    for needed in ("### AI Browser's own app (a menu-bar icon, a shortcut and notifications)",
                   "uv run ai-browser doctor --setup", "Electron 44.5.1", "Nothing is downloaded until you type `y`",
                   "`SHASUMS256.txt`", "nothing is kept", "~/.ai-browser/desktop/", "signed on your Mac, ad hoc",
                   "Running it needs no Node.js", "**Closing the window hides it.**", "**Quit**",
                   "Settings → AI Browser app", "Press it once", "\"An agent is waiting for you\"",
                   "Never a message's text or a page's", "the Start menu", "keeps Electron's icon in File Explorer",
                   "AIB_TEST_ELECTRON", "It has no debugging port and no DevTools"):
        assert needed in text, needed
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_desktop_static.py::test_the_readme_explains_the_app -q -p no:randomly`

Expected: FAIL on the first phrase (`### AI Browser's own app …`).

- [ ] **Step 3: Write the README**

In `README.md`:
1. Add this section right before the line `## The Brain (watches your messages, tells you what needs you)`:

```markdown
### AI Browser's own app (a menu-bar icon, a shortcut and notifications)

AI Browser can run as an app of its own, built on Electron, instead of in a browser window. It has its own Dock
icon (a taskbar icon on Windows) and an icon in the menu bar (by the clock on Windows). It also adds a shortcut that
shows and hides it from any app, and native notifications. The engine stays the same: `uv run ai-browser app` starts
it, then the app.

**Setting it up (once):** run `uv run ai-browser doctor --setup` in a terminal.
- It shows what it would download: Electron 44.5.1 for your computer, its size (about 130 MB on a Mac, 158 MB on
  Windows) and its address on GitHub. Nothing is downloaded until you type `y`.
- The download is checked against Electron's `SHASUMS256.txt` from the same release. If it doesn't match, or it
  stops halfway, nothing is kept, the browser window still works, and Settings says what happened.
- The app is built in `~/.ai-browser/desktop/`: "AI Browser.app" on a Mac, signed on your Mac, ad hoc, so macOS
  remembers its microphone permission; an "AI Browser" folder on Windows. Running it needs no Node.js and no npm.
- On Windows it also adds AI Browser to the Start menu: Windows shows an app's notifications only then. AI Browser.exe
  keeps Electron's icon in File Explorer. Its window, its icon by the clock and its notifications show AI Browser's.
- When an update of AI Browser changes the app's own files, `ai-browser app` builds the app again before it starts,
  with no download. macOS may then ask for the microphone once more.

**Using it:**
- **Closing the window hides it.** The app keeps running in the menu bar (by the clock on Windows), agents keep
  working, and the shortcut brings it back.
- **Quit** stops the app and every agent, as Ctrl-C in the terminal does. Quit is in the menu-bar icon's menu, or
  press ⌘Q on a Mac.
- **The shortcut** is ⌥Space (Alt+Space on Windows). Settings → AI Browser app offers two others, and Off. If another
  app already uses it, Settings says so: pick another one. Press it once after a change, to check it.
- **Notifications** say only what needs you: "An agent is waiting for you", "A bot check on example.com", "The Brain
  has 2 new notes". Never a message's text or a page's. A click opens AI Home at that agent's row, or brings the
  agent's tab forward in Brave.
- The menu-bar icon offers **Open AI Browser**, **Show chat** (the floating chat, coming next) and **Quit**.
- Until it is set up, or with `--window`, AI Browser opens in a browser window as before, and AI Home offers the
  setup.
- Started by a double-click (Finder, or the Start menu), it asks you to start AI Browser from a terminal. A
  double-click start comes later.

**Locked down:** its pages are AI Browser's own (`http://127.0.0.1:<port>`) and nothing else. A website link opens in
Brave, and no page opens a window. Pages may use the microphone, and write to the clipboard on a Copy button; nothing
else. It has no debugging port and no DevTools, and it refuses to start with a debugging switch.
```

2. In the Commands block:
   - the line starting `uv run ai-browser app [--window auto|chrome|brave|edge]` keeps its command, and its comment
     becomes `# AI Browser's own app, or a browser window; agents browse in your Brave`;
   - the line starting `uv run ai-browser doctor --setup` keeps its command, and its comment becomes
     `# quick check, no Docker; offers AI Browser's own app (asks first)`.
3. In "Safety notes", after the bullet that starts "AI Browser's window has no debugging port", add:
   "- AI Browser's own app has no debugging port and no DevTools, and refuses to start with a debugging switch. Its
   fuses keep any other program from running it as Node.js or with an inspector. Its pages are AI Browser's own
   only. They may use the microphone, and write to the clipboard on a Copy button."
4. In "Development", after the `uv run pytest` block, add: "Tests that drive a real Electron run only when
   `AIB_TEST_ELECTRON` names an Electron 44 program you already have (an Electron.app's `Contents/MacOS/Electron`, or
   `electron.exe`). They start it unpackaged, in throwaway folders, and a window shows for a moment. The tests of the
   app's rules run under Node.js when it is installed. The app itself never needs Node.js."

- [ ] **Step 4: Run it, then the whole suite**

Run: `uv run pytest tests/test_desktop_static.py tests/test_appwindow.py tests/test_portable.py -q -p no:randomly`

Expected: PASS. `test_the_readme_describes_the_window` still finds its words, and none it must not.

Run: `uv run pytest -q -p no:randomly`

Expected: every test passes. These show as skipped:
- the Docker tests, without the sandbox image;
- the real-Electron tests, without `AIB_TEST_ELECTRON`;
- the Node tests, without Node.js;
- the Windows-only tests, on a Mac.
Note the totals in the ledger.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_desktop_static.py
git commit -m "docs: AI Browser's own app in the README: setting it up, closing versus Quit, the shortcut, notifications"
```

- [ ] **Step 6: The user's hand checks (the main session, with the user)**

Never on a running `ai-browser app` the user didn't start for this. Never click, answer or hide Brave's "Allow remote
debugging?" or its automation bar: the user answers Brave's questions. Record each step's result in the ledger.

**On the Mac:**
1. **The setup:** the user runs `uv run ai-browser doctor --setup`.
   - The offer shows Electron 44.5.1, 130 MB and the address on GitHub.
   - The user types `y`. It downloads and checks, then builds "✓ app … ready".
   - `~/.ai-browser/desktop/` holds "AI Browser.app" and `app.json`.
2. **The app's look:** the user runs `uv run ai-browser app`.
   - "AI Browser" opens with its own Dock icon and the tab menu (AI Home · Mission Control · Settings).
   - The menu bar shows "AI Browser". The menu-bar icon offers Open AI Browser, Show chat (greyed) and Quit.
3. **Closing versus Quit:**
   - The red button hides the window. The Dock and the menu bar keep the app, and agents keep working.
   - Open AI Browser (or the Dock icon) brings it back.
   - Quit, from the menu-bar icon, ends the terminal's `ai-browser app` and every agent. Start again, then ⌘Q: the
     same.
   - Start again, then Ctrl-C in the terminal: the app goes too.
4. **⌥Space:** from another app, ⌥Space shows AI Browser, and again hides it. Settings → AI Browser app then says
   "⌥Space shows and hides AI Browser". If Raycast or Alfred holds ⌥Space, Settings says so; pick ⌥⇧Space, and it
   works.
5. **The microphone:** in Mission Control, hold Space to talk.
   - macOS asks whether "AI Browser" (not Terminal) may use the microphone. Allow.
   - Quit and start again: it doesn't ask again.
6. **A website link** in an agent's chat opens in Brave, never in the app's window.
7. **Notifications:**
   - An agent that asks for a tool shows "An agent is waiting for you". A click opens AI Home at its row.
   - A bot check shows "A bot check on <site>". A click brings the agent's tab forward in Brave.
   - The first one makes macOS ask whether AI Browser may send notifications. Allow.
8. **A double-click start:** quit, then double-click "AI Browser.app" in Finder. It says "Start AI Browser from a
   terminal".
9. **No Node behind its back:** in a terminal, run
   `ELECTRON_RUN_AS_NODE=1 ~/.ai-browser/desktop/"AI Browser.app"/Contents/MacOS/Electron -e "console.log(1)"`.
   - It doesn't print 1: the fuse is off, so it starts as the app instead.
   - With no engine behind it, it says "Start AI Browser from a terminal" after about 20 seconds. Click OK.

**On Windows:**
1. **The setup:** `uv run ai-browser doctor --setup` shows 158 MB and the Start menu line. Type `y`, and it builds
   "AI Browser".
2. **The app:** `uv run ai-browser app` opens the window with a title bar only, and an icon by the clock. The icon's
   menu offers Open AI Browser, Show chat (greyed) and Quit; a left click opens the window.
3. **Closing versus Quit:**
   - The window's × hides it, and the icon by the clock stays.
   - Quit ends the terminal's `ai-browser app`.
4. **Alt+Space** shows and hides AI Browser from another app. With PowerToys Run on Alt+Space, Settings says it's
   taken.
5. **Notifications** show as Windows toasts, and a click opens the right place.
6. **The cost said in the plan:** AI Browser.exe keeps Electron's icon in File Explorer. The Start menu has "AI
   Browser", and started from there it says to start AI Browser from a terminal.

If a check fails, note it in the ledger, with what the user saw, before anything is changed.
