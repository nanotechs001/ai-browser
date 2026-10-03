# The App Window Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `uv run ai-browser app` opens AI Home, Mission Control and Settings in one plain app window (an installed
browser in `--app` mode, on a profile of the app's own, with no debugging port), served over http by the app server
behind a one-time code, an HttpOnly cookie, an exact Host check and a strict CSP. AI Browser's own Chrome, its
extension and the engine's app mode retire.

**Architecture:**
- **The window (`src/ai_browser/app/window.py`, new):**
  - picks the browser that draws it (the `window_browser` setting, `--window` for one run, Auto);
  - builds its exact command line (`--app=<url>`, its own profile, the autoplay flag, no debugging flag);
  - starts it with `subprocess.Popen`, and at the end closes only the process it started.
- **Settings (`src/ai_browser/settings.py`, new):** `<home>/settings.json`, one reader and one writer, plus a typed
  view (the window's browser, the model, Voice).
- **The app server (`app/server.py`):**
  - `_Guard`: an exact Host on every route, and strict headers on every HTTP answer;
  - `/open?code=` swaps a 60 s one-time code for the cookie `aib_ui_<port>`;
  - the pages and files of `app/ui/`, a setup page with no secret;
  - window sockets (cookie, Origin and Host) next to the watcher's (token and origin), each with a stored role;
  - `window_count`, `settings_set`, `open_url`, `ai_keyword` and the remembered port.
- **The pages (`app/extension/` becomes `app/ui/`, a `git mv`):**
  - `link.js` has two ways in: the window over http, and the watcher's extension path;
  - `nav.js` opens our pages as popup windows and sends websites to the user's browser;
  - a Settings page;
  - the model and Voice come from the server.
- **`app/run.py`:** launches the window through a launcher, waits for its first socket, and ends 5 s after the last
  window socket closes. It always attaches BraveLink and the relay.
- **The watcher:** gains the `ai` omnibox keyword.
- **Retired:** `appbrowser.py`; the extension's manifest and worker; `AIB_BROWSER=app` and `--browser app`;
  `PANEL_PROMPT`; the MCP server's app-mode lines; `HAND_OVER_APP_SAY`.

**Tech Stack:**
- Python 3.12, Starlette 1.x and uvicorn (`ws="websockets-sansio"`, pinned by the relay);
- the `websockets` 17 client, and `httpx` in tests;
- plain-JS ES modules;
- pytest with:
  - a throwaway headless Google Chrome (`chrome.launch`) for the UI tests;
  - `tests/pipe_chrome.py` for the watcher's tests;
  - the fake `claude`.

**Spec:** `docs/superpowers/specs/2026-10-03-app-window-design.md`. The brief is
`docs/superpowers/specs/2026-10-03-app-as-an-app-overview.md` (section 3), and the probe findings are in
`docs/superpowers/specs/2026-10-03-app-as-an-app-investigation.json` (key `appwindow`).

**Branch and build order:** this is **wave B**. The user asked to fix the repeated Allow prompts first, so the order
is:
1. the cdp-relay;
2. wave A, in parallel: brain-delegation, watcher-safety and browser-detection;
3. **this plan**;
4. wave C: browser-profile-choice;
5. wave D: side-chat.

Create the branch `app-window` from `main` once the relay and all of wave A are merged. Nothing else runs at the same
time, because this plan rewrites `app/run.py` and `app/server.py`.

**Find every place by its text, never by a line number.** The spec's line numbers are at HEAD `946d5f0`, before the
relay and wave A, and those waves move them. Each step quotes the text it changes. When the merged code spells a name
differently from the names below, the merged name wins, and the behaviour is what matters. Task 0 pins the names first.

**The earlier waves' names this plan relies on** (Task 0 checks they exist):
- **cdp-relay** (`docs/superpowers/specs/2026-10-03-cdp-relay-design.md`):
  - `app/cdprelay.py`: `Relay` (with `serve`, `local()` and `clients()`) and `Tokens` (`mint`);
  - `AppServer.tokens`, `AppServer.token_for(agent_id)` and `connect_brave(why, identity="")`;
  - the `/cdp` WebSocketRoute and `uvicorn.Config(..., ws="websockets-sansio")`;
  - `BraveLink(folder, watcher_id="", allow_wait, every, tokens=None)` and its `relay`;
  - `TabWatch(ws_url, extension_id, open_timeout=10, cdp=None)`;
  - `write_link(home, url, token, cdp, browser_dir)` and the `AIB_APP_CDP` env;
  - the new `SWITCH` text and setup-page texts;
  - `FakePort`, `FakeBrave` and `FakeRelay` in `tests/fake_brave.py`;
  - `browser_disconnect` and `browser_clients`.

  The relay was built before wave A, on `BRAVE_MESSAGES` and `int(id[1:])`. Wave A then moved its rows into the
  tables below, and its client list onto `Agent.number`.
- **watcher-safety** (`2026-10-03-watcher-safety-design.md`):
  - `Rule(app=True, watcher=False)`, `MESSAGE_RULES` and `may_send(role, message)`;
  - `WATCHER_RECEIVES`, `WATCHER_AGENT_FIELDS` and `for_watcher(message)`;
  - `AppServer._role(ws)`;
  - `_write`, which reads the role once;
  - the two table tests in `tests/test_watcher_rules.py`;
  - `TabWatch.pages()`, `worker_contexts()` and `default_context`;
  - `BraveLink.agents_context()` and `scope()`;
  - `check_show`.
- **brain-delegation** (`2026-10-03-brain-delegation-design.md`):
  - `Agent.number` (a property, `int(id[1:])`) and `Agent.queued`;
  - `AgentManager.in_users_browser` and `HAND_OVER_APP_SAY` (Task 20 deletes both);
  - `agentLabel(agent)` in `chat.js`;
  - `mountBrain(root, link, {compact, openAgent, cards})`;
  - `tell_confirm` and `tell_dismiss`.
- **browser-detection** (`2026-10-03-browser-detection-design.md`):
  - `browsers.installed(system=None, env=None, folders=None, commands=None)`;
  - `Installed`, with `facts`, `binary` and `bundle`, plus `id`, `name` and `window`;
  - `browsers.os_default(system=None, env=None)`, `browsers.for_data_dir(folder)` and
    `browsers.running(data_dir, system=None)`;
  - `browsers.all_data_dirs(system=None, env=None)`;
  - `platforms.app_folders`, `windows_browser_commands`, `windows_https_progid` and `launch_services_file`.

## Global Constraints

Copied from the spec. Every task's requirements include these.

**The binding safety rules** (this project, all waves):
- Never auto-click, answer, suppress or hide the browser's "Allow remote debugging?" prompt or its automation bar. The
  window's command line has no `--remote-debugging-port`, `--remote-debugging-pipe`, `--enable-automation`,
  `--load-extension`, `--silent-debugger-extension-api` or `--disable-infobars`, and a test pins the exact list.
- No spoofing and no disguise. No bypassing bot checks. "`navigator.webdriver` is false there because nothing automates
  the window, not because anything hides it." "No user agent, screen or timing change anywhere."
- No passwords: "The window's pages have no sign-in, and the app never signs its profile in to the browser."
- Page text is data. The keyword's text is "what the user typed in Brave's address bar. Only the watcher's omnibox
  handler sends it."
- `textContent` only. "A static test forbids `.innerHTML`, `.outerHTML`, `insertAdjacentHTML` and `document.write` in
  `ui/`'s scripts, and inline `<script>` and `<style>`, `style=` and `on…=` attributes in its pages."
- Hand-over and take-back are clicks only: "the server ignores `adopt` and `tab` on `ai_keyword`."
- The Brain only proposes. "The keyword doesn't go through the Brain: it is the user's own Enter, like Start in AI
  Home."
- Downloads need the user's OK: "The window's pages download nothing. Agents' download rules … are unchanged."

**The window:**
- The command line, exactly:
  `<binary> --user-data-dir=<profile> --app=<url> --no-first-run --no-default-browser-check
  --disable-search-engine-choice-screen --window-size=1440,960 --autoplay-policy=no-user-gesture-required`.
- The profile is `<home>/app/window/<browser id>`. The launcher refuses a profile that is, or is inside, any of
  `browsers.all_data_dirs()`.
- `WINDOW_CHOICES = ("auto", "chrome", "brave", "edge")`.
- What each system offers: macOS and Linux get Auto, Chrome and Brave; Windows gets Auto, Edge, Chrome and Brave.
- Auto's order: Chrome, then Brave (Windows: Edge, Chrome, Brave). On macOS only, it skips the OS default browser when
  another candidate is installed.
- Names: "Google Chrome", "Brave", "Microsoft Edge".
- Closing:
  - macOS and Linux: SIGTERM;
  - Windows: `taskkill /PID <pid>` without `/F`;
  - then wait 10 s, then kill;
  - after a hand-off, nothing.
- The app never kills a process it didn't start.

**The server:**
- `ui_secret` and every code are `secrets.token_urlsafe(32)`. A code is single use, valid for 60 s (`CODE_TTL`), and
  compared with `hmac.compare_digest`.
- The cookie: `Set-Cookie: aib_ui_<port>=<ui_secret>; HttpOnly; SameSite=Strict; Path=/`, with no `Max-Age` and no
  `Secure`.
- Host must be exactly `127.0.0.1:<port>`. `localhost:<port>` is refused. HTTP gets 403. A WebSocket is closed before
  accept, which the client sees as HTTP 403.
- Headers on every HTTP response:
  - `Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:;
    connect-src ws://127.0.0.1:<port>/ws http://127.0.0.1:<port>/setup/; base-uri 'none'; form-action 'none';
    frame-ancestors 'none'`;
  - `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` and
    `Cross-Origin-Resource-Policy: same-origin`.
- A window socket needs Origin exactly `http://127.0.0.1:<port>`, Host exactly `127.0.0.1:<port>`, and the cookie.
  Anything else is closed with 4403 after accept.
- The pages need the cookie, except `/setup`, `setup.css`, `setup.js` and `icon.png`. Without it: 403 and "AI
  Browser's pages open only in its own window. Start it with `uv run ai-browser app`."
- `open_url` accepts only:
  - an address starting `http://` or `https://`, with a host;
  - no user name or password;
  - no whitespace or control character;
  - at most 2,000 characters.
- `ai_keyword` text is trimmed to 2,000 characters.
- Window timing: `WINDOW_START_WAIT = 60` s, `WINDOW_GRACE = 5` s, and a look every 0.25 s.
- The ending order:
  1. the window;
  2. the link file;
  3. `server.stop()`;
  4. BraveLink (and with it the relay).

**Windows of our own:**

| name | page | size |
|---|---|---|
| `aib-home` | `/home` | 1440 × 960 |
| `aib-mission` | `/mission` | 1280 × 860 |
| `aib-settings` | `/settings` | 720 × 760 |
| `aib-setup` | `/setup#brave` or `/setup#switch` | 760 × 900 |
| `aib-live` | an engine's live view | 1280 × 860 |

No code path uses `"_blank"`, except `brainui.js`'s anchor in the watcher.

**Settings:**
- `DEFAULTS = {"window_browser": "auto", "model": None, "voice": False}`.
- Writes are atomic, mode 0600, and keep every other key.
- `model` is one of `opus`, `sonnet`, `haiku` or None. `voice` is a bool.

**Coordination rules (earlier waves, still binding):**
- Text files name `encoding="utf-8"`.
- No new text in pages says "this Mac" or "⌘". Python texts use `platforms.shortcut`.
- No macOS path (`/Applications/`, `Application Support`, `"open", "-R"`) is written outside `platforms.py`.
- Process checks use the existing helpers.

**House rules:**
- Run tests one file or test at a time: `uv run pytest <path>::<test> -q -p no:randomly`.
- The whole suite runs only in the last task.
- Never connect to the user's own Brave or Chrome. Never touch a running `ai-browser app`.
- No test opens a visible window. Throwaway headless Chromes only.
- Do not commit anything outside the task's files.

## Review Focus

These are the five failures most likely to hit a user that the spec implies but none of its tests cover. Each one has
a test in the task that owns the code.
1. **Ctrl-C (or `stop`) while the window is still opening.** The user expects Ctrl-C to always close the window. The
   app must close it, return 0, and print no "didn't open" line. Test: Task 17
   (`test_stop_before_the_window_connects_still_closes_it`).
2. **A `settings.json` from another computer or a newer build.** Take `"window_browser": "edge"` read on a Mac. That
   key falls back to Auto. The other keys are kept, and the file is not rewritten until a `set`, which keeps "edge"
   for the Windows laptop that wrote it. Test: Task 2 (`test_a_file_from_another_computer_falls_back_key_by_key`).
3. **Saving a setting fails** (a read-only home, a full disk, a folder where the file should be). The page gets
   "Couldn't save that setting: …", the socket stays open, and the value stays as it was. Test: Task 10
   (`test_a_setting_that_cant_be_saved_is_said_and_changes_nothing`).
4. **The keyword in other letter case, with extra spaces, or very long.** `ai QA Site   example.com` runs the
   "qa site" workflow with "example.com". 3,000 characters are trimmed to 2,000 and still start one agent. Test:
   Task 12 (`test_the_keyword_ignores_case_spaces_and_trims_long_text`).
5. **On Windows, `taskkill` missing or failing.** `close()` still kills the process after the wait and never raises.
   Test: Task 3 (`test_a_failing_taskkill_still_ends_the_window`).

## File map

**New:**
- `src/ai_browser/extension_id.py`: `extension_path` and `extension_id_for`, moved unchanged from `appbrowser.py`.
- `src/ai_browser/app/window.py`: `WINDOW_CHOICES`, `offered`, `WindowBrowser`, `WindowPick`, `pick`, `choices`,
  `window_profile`, `window_args`, `WindowError`, `AppWindow` and `default_launcher`.
- `src/ai_browser/settings.py`: `read_settings`, `write_setting`, `DEFAULTS` and `Settings`.
- `src/ai_browser/app/ui/` (moved from `app/extension/`, plus):
  - `nav.js`, `settings.html`, `settings.js` and `icon.png` (a copy of the watcher's);
  - `setup.html`, moved from `app/setup.html`, with its style in `setup.css` and its script in `setup.js`.
- **Tests:**
  - `tests/test_wave_b_seams.py`, `tests/test_extension_id.py`, `tests/test_appwindow.py`, `tests/test_settings.py`
    and `tests/test_ui_static.py`;
  - helpers: `tests/ui_socket.py`, `tests/fake_window.py` and `tests/pipe_chrome.py`.

**Changed:**
- **App:**
  - `app/server.py`: the guard, routes, code and cookie, roles, settings, `open_url`, the keyword, the port, and AI
    Browser mode gone;
  - `app/run.py`: rewritten around the window;
  - `app/tabs.py`: `hidden_origin`;
  - `app/bravelink.py`: `app_origin`;
  - `app/bridge.py`: `PANEL_PROMPT` gone, `AIB_BROWSER` defaults to `chrome`;
  - `app/agents.py`: `in_users_browser` gone;
  - `app/__init__.py`: its docstring.
- **Pages:**
  - `app/ui/link.js`, `home.js`, `home.html`, `home.css`, `mission.js`, `mission.html`, `brainui.js`,
    `brainui.css`, `check.js`, `mic.js`, `talk.js` and `tablist.js`;
  - `app/watcher/manifest.json` and `worker.js` (the keyword).
- **Engine:**
  - `engine.py` and `browser.py` (app mode gone, `app_origin`);
  - `qa/run.py` (`url_problem` with the app's origin);
  - `server.py` (the MCP instructions);
  - `platforms.py` (`open_url`, `open_url_command`);
  - `cli.py` (`--window`, `--browser brave`, the doctor's `window` line);
  - `brain/watcher.py` (`SHARED_SOURCE`);
  - `brain/talk.py` and `brain/service.py` (`HAND_OVER_APP_SAY` gone).
- **Docs:** `README.md`.
- **Tests:**
  - `tests/conftest.py`, `test_app_server.py`, `test_app_run.py` (rewritten), `test_home.py` (the stack rebuilt),
    `test_mission.py`, `test_talk.py`, `test_mission_visuals.py`;
  - `test_ai_home_phase2.py`, `test_brain_ui.py`, `test_check_card.py`, `test_panel.py` (skipped);
  - `test_watcher.py`, `test_watcher_rules.py`, `test_tabwatch.py`, `test_bravelink.py`, `test_engine.py`,
    `test_chrome.py`, `test_server.py`;
  - `test_bridge.py`, `test_brain_talk.py`, `test_cli.py`, `test_platforms.py`, `test_portable.py`, `test_tools.py`,
    `test_skillwriter.py`, `test_workflows.py`.

**Deleted:**
- `src/ai_browser/appbrowser.py`;
- `src/ai_browser/app/extension/manifest.json` and `worker.js` (`app/extension/` keeps only `panel.*`, for wave D);
- `tests/test_appbrowser.py` and `tests/test_appmode.py` (three of its tests move).

The ledger is `.superpowers/sdd/2026-10-03-app-window/progress.md` (git-ignored). Note in it each task's result and
any by-hand finding.

---

### Task 0: The earlier waves' names, pinned; `extension_id.py` split out of `appbrowser.py`

This task changes no behaviour. It checks that the relay and wave A left the names this plan builds on. It also moves
the two extension-ID functions that the watcher still needs out of `appbrowser.py`, which Task 21 deletes.

**Files:**
- Create: `src/ai_browser/extension_id.py`
- Modify: `src/ai_browser/appbrowser.py` (delete `extension_path` and `extension_id_for`; import them)
- Modify: `src/ai_browser/app/server.py` (the line `from ..appbrowser import extension_path`)
- Modify: `src/ai_browser/app/run.py` (the `from ..appbrowser import (...)` block)
- Modify: `tests/test_appbrowser.py` (the moved tests go), `tests/test_app_run.py`, `tests/test_app_server.py`
  (imports only)
- Test: `tests/test_wave_b_seams.py` (new), `tests/test_extension_id.py` (new)

**Interfaces:**
- Consumes the names listed in the header under "The earlier waves' names this plan relies on".
- Produces:
  - `ai_browser.extension_id.extension_path(folder, system=None) -> str`;
  - `ai_browser.extension_id.extension_id_for(folder, system=None) -> str`.

  Both are moved byte for byte. Every later task imports them from `ai_browser.extension_id`.

- [ ] **Step 1: Write the failing tests**

`tests/test_wave_b_seams.py`:

```python
"""The app window (wave B) builds on the cdp-relay and wave A (watcher-safety, brain-delegation, browser-detection)
through a few names. This pins them, so no task starts on a name the merged code spells differently."""

import inspect


def test_the_relay_and_wave_a_have_the_names_this_plan_uses():
    from ai_browser import browsers
    from ai_browser.app import server
    from ai_browser.app.agents import Agent
    from ai_browser.app.bravelink import BraveLink
    from ai_browser.app.cdprelay import Relay, Tokens
    from ai_browser.app.tabs import TabWatch

    # watcher-safety: what a page may send, by role, and what a watcher socket may get
    assert callable(server.may_send) and callable(server.for_watcher) and callable(server.AppServer._role)
    assert {"hello", "new_task", "hand_tab", "brave_connect", "check_show", "browser_disconnect",
            "tell_confirm"} <= set(server.MESSAGE_RULES)
    assert {"snapshot", "error", "check_request"} <= set(server.WATCHER_RECEIVES)
    assert "browser_clients" not in server.WATCHER_RECEIVES and "tabs" not in server.WATCHER_RECEIVES
    # the relay: one connection to the browser, a token per agent, BraveLink and TabWatch on it
    assert {"tokens", "watcher_id"} <= set(inspect.signature(BraveLink).parameters)
    assert "cdp" in inspect.signature(TabWatch).parameters
    assert callable(Tokens.mint) and callable(Relay.serve) and callable(server.AppServer.token_for)
    assert list(inspect.signature(server.AppServer.connect_brave).parameters)[:2] == ["self", "why"]
    # brain-delegation: an agent's number is its id's number
    assert isinstance(inspect.getattr_static(Agent, "number"), property)
    # browser-detection
    for name in ("installed", "os_default", "for_data_dir", "running", "all_data_dirs"):
        assert callable(getattr(browsers, name)), name
    assert {"facts", "binary", "bundle"} <= set(browsers.Installed.__dataclass_fields__)
```

`tests/test_extension_id.py`. These are the extension-ID tests from `tests/test_appbrowser.py`, moved unchanged
except for the import path:

```python
"""The ID Chrome and Brave give an unpacked extension (Brave's watcher), and the folder path it is hashed from."""

import pytest

EXT = "C:\\Users\\me\\.ai-browser\\app\\extension"
WATCH = "C:\\Users\\me\\.ai-browser\\app\\watcher"
JOSE = "C:\\Users\\José & Ana\\.ai-browser\\app\\extension"
DEV = "C:\\dev\\aib-home\\app\\extension"


@pytest.mark.parametrize("folder, shown, expected", [
    (EXT, EXT, "jjdpkibincdinfnjejbcmmghdbgfjpph"),
    ("c:\\Users\\me\\.ai-browser\\app\\extension", EXT, "jjdpkibincdinfnjejbcmmghdbgfjpph"),  # a lower-case drive
    (WATCH, WATCH, "ncapijkcfmdajdlhdhbgnnmkgejiggeg"),
    ("C:/Users/me/.ai-browser/app/extension", EXT, "jjdpkibincdinfnjejbcmmghdbgfjpph"),  # forward slashes
    ("C:\\Users\\me\\.ai-browser\\app\\extension\\", EXT, "jjdpkibincdinfnjejbcmmghdbgfjpph"),  # a trailing separator
    ("c:/dev/aib-home/app/extension/", DEV, "nhhpnkhncgedihejcoolkhbhmnklfgik"),  # all three at once
    (DEV, DEV, "nhhpnkhncgedihejcoolkhbhmnklfgik"),
    (JOSE, JOSE, "lfcipbofoccnodmlbinbgmflefkkgomp"),  # UTF-16LE of the exact path, not UTF-8
])
def test_windows_extension_ids_follow_chromium(folder, shown, expected):
    from ai_browser.extension_id import extension_id_for, extension_path

    assert extension_id_for(folder, system="win32") == expected
    assert extension_path(folder, system="win32") == shown  # one string: hashed, shown, pasted


def test_the_old_utf8_hash_was_wrong_on_windows():
    from ai_browser.extension_id import extension_id_for

    assert extension_id_for(EXT, system="win32") != "mkeihmjkgdgccikkejdhgpoikkjpilll"  # the old UTF-8 code's ID


def test_the_posix_id_is_unchanged(tmp_path):
    import hashlib
    import os

    from ai_browser.extension_id import extension_id_for, extension_path

    folder = tmp_path / "ext"
    folder.mkdir()
    digest = hashlib.sha256(os.path.realpath(folder).encode("utf-8")).hexdigest()[:32]
    assert extension_id_for(folder, system="darwin") == "".join(chr(ord("a") + int(c, 16)) for c in digest)
    assert extension_path(folder, system="darwin") == os.path.realpath(folder)
```

In `tests/test_appbrowser.py`, delete what moved:
- the constants `EXT`, `WATCH`, `JOSE` and `DEV`;
- `test_windows_extension_ids_follow_chromium` with its `parametrize`;
- `test_the_old_utf8_hash_was_wrong_on_windows`;
- `test_the_posix_id_is_unchanged`.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_wave_b_seams.py tests/test_extension_id.py -q -p no:randomly`

Expected:
- `test_extension_id.py` FAILS with `ModuleNotFoundError: No module named 'ai_browser.extension_id'`.
- `test_the_relay_and_wave_a_have_the_names_this_plan_uses` already PASSES if the relay and wave A are merged.
  If it fails, a name was spelled differently there. Find the merged name, write it in the ledger, and use it in every
  task below that says the old one. Then make this test assert the merged name.

- [ ] **Step 3: Move the two functions**

Create `src/ai_browser/extension_id.py`. Copy `extension_path` and `extension_id_for` from
`src/ai_browser/appbrowser.py` byte for byte, with only the imports they need:

```python
"""The ID Chrome and Brave give an unpacked extension, and the folder path it is computed from. Brave's watcher is
loaded once from a fixed folder (<home>/app/watcher), so the app knows its ID, and allows its origin, before it ever
connects."""

from __future__ import annotations

import hashlib
import ntpath
import os
import sys
from pathlib import Path


def extension_path(folder: Path | str, system: str | None = None) -> str:
    """The folder's path as Chrome sees it: the string that is hashed into the ID, and the one the user sees, pastes
    and gets revealed. Windows: the absolute path as written (Chrome resolves neither junctions nor OneDrive's
    redirection), with the drive letter upper-cased as Chromium's MaybeNormalizePath does. Elsewhere: the real
    path."""
    if (system or sys.platform) == "win32":
        path = ntpath.abspath(str(folder))
        return path[0].upper() + path[1:] if path[1:2] == ":" else path
    return os.path.realpath(folder)


def extension_id_for(folder: Path | str, system: str | None = None) -> str:
    """The ID Chrome gives an unpacked extension: SHA-256 of its folder's path, 0-f mapped to a-p. Windows hashes the
    path as UTF-16LE (Chromium's id_util.cc, GenerateIdForPath); extension_path already upper-cased its drive."""
    path = extension_path(folder, system)
    data = path.encode("utf-16-le" if (system or sys.platform) == "win32" else "utf-8")
    digest = hashlib.sha256(data).hexdigest()[:32]
    return "".join(chr(ord("a") + int(char, 16)) for char in digest)
```

In `src/ai_browser/appbrowser.py`:
- delete the two `def`s;
- delete `import hashlib`, which is no longer used;
- add `from .extension_id import extension_id_for, extension_path` under `from . import platforms`.
  `extension_installed` and `launch_app_browser` keep calling them.

In `src/ai_browser/app/server.py`, replace `from ..appbrowser import extension_path` with
`from ..extension_id import extension_path`.

In `src/ai_browser/app/run.py`, the import block becomes these two imports, one from each module:

```python
from ..appbrowser import AppBrowserError, app_profile, extension_installed, launch_app_browser, prepare_extension
from ..extension_id import extension_id_for, extension_path
```

In the tests, every import of `extension_id_for` or `extension_path` from `ai_browser.appbrowser` now comes from
`ai_browser.extension_id`. Find them with `grep -n "appbrowser import" tests/*.py`. Today they are in
`test_app_run.py` and `test_app_server.py`. Split a mixed line, for example:

```python
from ai_browser.appbrowser import prepare_extension
from ai_browser.extension_id import extension_id_for
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_wave_b_seams.py tests/test_extension_id.py tests/test_appbrowser.py -q -p no:randomly`

Expected: PASS.

Run: `uv run pytest tests/test_app_server.py -q -p no:randomly -k "setup or watcher or junction or mismatch"`

Expected: PASS. Only imports changed.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/extension_id.py src/ai_browser/appbrowser.py src/ai_browser/app/server.py \
  src/ai_browser/app/run.py tests/test_wave_b_seams.py tests/test_extension_id.py tests/test_appbrowser.py \
  tests/test_app_run.py tests/test_app_server.py
git commit -m "refactor: pin the relay's and wave A's names; extension IDs get a module of their own"
```

### Task 1: Which browser draws the window, and its exact command line

**Files:**
- Create: `src/ai_browser/app/window.py` (part 1: the pick and the command line)
- Modify: `tests/conftest.py` (the autouse fixture `_never_the_users_browsers`)
- Test: `tests/test_appwindow.py` (new)

**Interfaces:**
- Consumes (browser-detection, as merged):
  - `browsers.installed(system=…)`, whose rows give `.id`, `.window` and `.binary`;
  - `browsers.os_default(system=…)`;
  - `chrome.chrome_binary()` and `chrome.brave_binary()` (Linux only);
  - `platforms.app_folders`, `windows_browser_commands`, `windows_https_progid` and `launch_services_file` (the test
    fixture replaces them).
- Produces (`ai_browser.app.window`):
  - `WINDOW_CHOICES = ("auto", "chrome", "brave", "edge")` and `NAMES = {"chrome": "Google Chrome", "brave": "Brave",
    "edge": "Microsoft Edge"}`;
  - `offered(system=None) -> tuple[str, ...]`: `("auto", "chrome", "brave")`, or `("auto", "edge", "chrome",
    "brave")` on `win32`;
  - `@dataclass(frozen=True) WindowBrowser(id: str, name: str, binary: str)`;
  - `@dataclass(frozen=True) WindowPick(browser: WindowBrowser, note: str)`;
  - `pick(setting, system=None, installed=None, os_default=None) -> WindowPick | None`:
    - `installed` maps an id to a program path. With `installed` given, `os_default` is taken as given (None means
      no default), so the call is pure;
    - with `installed=None`, it asks the computer, and `os_default=None` asks it too (macOS only);
  - `choices(system=None, installed=None, os_default=None) -> list[dict]`: one `{"id", "name", "installed"}` per
    offered choice, with Auto named after its pick;
  - `window_profile(home, browser_id) -> Path`: `<home>/app/window/<id>`;
  - `window_args(binary, profile, url) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_appwindow.py`:

```python
"""AI Browser's window (app/window.py): which browser draws it, its exact command line, starting it and ending only
what it started. No test opens a visible window: the launch tests record Popen, and the one real launch (Task 13) is
headless."""

import subprocess
import sys

import pytest

from ai_browser.app import window

MAC_BOTH = {"chrome": "/x/Google Chrome", "brave": "/x/Brave Browser"}
ALL_THREE = {"edge": "C:\\Edge\\msedge.exe", "chrome": "C:\\Chrome\\chrome.exe", "brave": "C:\\Brave\\brave.exe"}


def picked(setting, system, installed, default=None):
    found = window.pick(setting, system=system, installed=installed, os_default=default)
    return None if found is None else (found.browser.id, found.browser.binary, found.note)


def test_auto_skips_the_everyday_browser_on_macos():
    assert picked("auto", "darwin", MAC_BOTH, "brave") == ("chrome", "/x/Google Chrome", "")  # this Mac's case
    assert picked("auto", "darwin", MAC_BOTH, "chrome")[0] == "brave"
    assert picked("auto", "darwin", {"brave": "/x/Brave Browser"}, "brave")[0] == "brave"  # nothing else to use
    assert picked("auto", "darwin", MAC_BOTH, None)[0] == "chrome"


def test_auto_on_windows_is_edge_first_with_no_skip():
    assert picked("auto", "win32", ALL_THREE, "chrome")[0] == "edge"
    assert picked("auto", "win32", ALL_THREE, "edge")[0] == "edge"  # no skip there
    assert picked("auto", "win32", {"chrome": "C:\\Chrome\\chrome.exe", "brave": "C:\\Brave\\brave.exe"})[0] == "chrome"


def test_auto_on_linux_is_chrome_then_brave():
    assert picked("auto", "linux", {"chrome": "/usr/bin/google-chrome", "brave": "/usr/bin/brave"})[0] == "chrome"
    assert picked("auto", "linux", {"brave": "/usr/bin/brave"})[0] == "brave"


def test_a_choice_that_cant_be_used_falls_back_to_auto_with_a_note():
    assert picked("brave", "darwin", {"chrome": "/x/Google Chrome"}) == (
        "chrome", "/x/Google Chrome", "Brave isn't installed: the window uses Google Chrome. Change it in Settings.")
    found = picked("edge", "darwin", MAC_BOTH, "brave")
    assert found[0] == "chrome" and found[2] == ("Microsoft Edge draws the window only on Windows: the window uses "
                                                 "Google Chrome. Change it in Settings.")
    assert picked("brave", "darwin", MAC_BOTH, "brave") == ("brave", "/x/Brave Browser", "")  # the user's choice wins
    assert picked("chrome", "win32", ALL_THREE)[0] == "chrome"
    assert picked("nonsense", "darwin", MAC_BOTH, "brave")[0] == "chrome"  # an unknown setting is Auto
    assert picked("auto", "darwin", {}) is None and picked("chrome", "win32", {}) is None


def test_offered_choices_per_system():
    assert window.offered("darwin") == ("auto", "chrome", "brave") == window.offered("linux")
    assert window.offered("win32") == ("auto", "edge", "chrome", "brave")
    assert set(window.offered("win32")) == set(window.WINDOW_CHOICES)


def test_choices_name_auto_after_its_pick():
    assert window.choices(system="darwin", installed={"chrome": "/x/c"}, os_default="brave") == [
        {"id": "auto", "name": "Auto (Google Chrome)", "installed": True},
        {"id": "chrome", "name": "Google Chrome", "installed": True},
        {"id": "brave", "name": "Brave", "installed": False}]
    rows = window.choices(system="win32", installed=ALL_THREE)
    assert [(row["id"], row["name"]) for row in rows] == [("auto", "Auto (Microsoft Edge)"), ("edge", "Microsoft Edge"),
                                                          ("chrome", "Google Chrome"), ("brave", "Brave")]
    assert window.choices(system="darwin", installed={})[0] == {"id": "auto", "name": "Auto", "installed": False}


def test_the_command_line_is_exactly_this(tmp_path):
    profile = tmp_path / "home" / "app" / "window" / "chrome"
    url = "http://127.0.0.1:8792/open?code=abc"
    args = window.window_args("/x/Google Chrome", profile, url)
    assert args == ["/x/Google Chrome", f"--user-data-dir={profile}", f"--app={url}", "--no-first-run",
                    "--no-default-browser-check", "--disable-search-engine-choice-screen", "--window-size=1440,960",
                    "--autoplay-policy=no-user-gesture-required"]
    banned = ("--remote-debugging", "--enable-automation", "--load-extension", "--headless", "--user-agent",
              "--disable-infobars", "--silent-debugger-extension-api")
    assert not [arg for arg in args if arg.startswith(banned)]
    assert window.window_profile(tmp_path / "home", "brave") == tmp_path / "home" / "app" / "window" / "brave"


def test_detection_never_reads_this_computers_apps(monkeypatch):
    from ai_browser import browsers

    monkeypatch.delenv("AIB_CHROME_BINARY", raising=False)
    for system in (None, "darwin", "win32"):
        assert browsers.installed(system=system) == [], system
    assert browsers.os_default() is None and browsers.os_default(system="darwin") is None


def test_aib_chrome_binary_is_chromes_program(tmp_path, monkeypatch):
    program = tmp_path / "chrome-bin"
    program.write_bytes(b"")
    monkeypatch.setenv("AIB_CHROME_BINARY", str(program))
    found = window.pick("auto")  # nothing is installed: the conftest fixture keeps detection off this computer
    assert (found.browser.id, found.browser.name, found.browser.binary) == ("chrome", "Google Chrome", str(program))
    monkeypatch.setenv("AIB_CHROME_BINARY", str(tmp_path / "missing"))
    if sys.platform in ("darwin", "win32"):  # on Linux the PATH finders still look
        assert window.pick("auto") is None
```

The imports `subprocess` and `pytest` are used by Task 3's tests in the same file.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_appwindow.py -q -p no:randomly`

Expected: every test FAILS at collection with `ModuleNotFoundError: No module named 'ai_browser.app.window'`. Once
the module exists, `test_detection_never_reads_this_computers_apps` still fails on this Mac (`installed()` lists Brave
and Chrome) until the conftest change below.

- [ ] **Step 3: Write `window.py` (the pick and the command line) and keep detection off this computer in tests**

`src/ai_browser/app/window.py`:

```python
"""AI Browser's own window: AI Home, Mission Control and Settings, drawn by an installed browser in Chrome's --app
mode (a title bar only: no tabs, no address bar), on a profile of the app's own.

The window has no debugging port: no --remote-debugging-port, no --remote-debugging-pipe, no --enable-automation and
no --load-extension. Nothing drives it, so it never brings "Allow remote debugging?" or the automation bar, and
navigator.webdriver is false there because nothing automates it, not because anything hides it. No agent browses in
it: agents use the user's browser, or the Docker sandbox. The app only starts the browser process on its own profile,
and ends that process when the app ends; it never connects to it.

Which browser draws it is a setting: Auto, Google Chrome, Brave, or Microsoft Edge on Windows. Auto tries Chrome, then
Brave (on Windows: Edge, Chrome, Brave). On macOS it skips the everyday browser when another is installed, so a link
clicked in another app never lands in this window's app."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .. import browsers

WINDOW_CHOICES = ("auto", "chrome", "brave", "edge")
NAMES = {"chrome": "Google Chrome", "brave": "Brave", "edge": "Microsoft Edge"}


def _system(system: str | None) -> str:
    return system or sys.platform


def offered(system: str | None = None) -> tuple[str, ...]:
    """The choices Settings shows on this system: Edge only on Windows."""
    return ("auto", "edge", "chrome", "brave") if _system(system) == "win32" else ("auto", "chrome", "brave")


def _order(system: str) -> tuple[str, ...]:
    return ("edge", "chrome", "brave") if system == "win32" else ("chrome", "brave")


@dataclass(frozen=True)
class WindowBrowser:
    id: str
    name: str
    binary: str


@dataclass(frozen=True)
class WindowPick:
    browser: WindowBrowser
    note: str  # why a choice that can't be used fell back to Auto, or ""


def _installed(system: str) -> dict[str, str]:
    """The browsers here that can draw the window: id -> program. Reads files only, never connects."""
    found: dict[str, str] = {}
    for row in browsers.installed(system=system):
        if row.window and row.id in NAMES and row.id in offered(system):
            found.setdefault(row.id, str(row.binary))
    if system not in ("darwin", "win32"):  # Linux: detection lists nothing there; today's finders do
        from ..chrome import brave_binary, chrome_binary

        for browser_id, finder in (("chrome", chrome_binary), ("brave", brave_binary)):
            program = finder()
            if program and Path(program).is_file():
                found.setdefault(browser_id, program)
    configured = os.environ.get("AIB_CHROME_BINARY")
    if configured and Path(configured).is_file():  # tests and CI: Chrome's program, whatever detection says
        found["chrome"] = configured
    return found


def _os_default(system: str) -> str | None:
    return browsers.os_default(system=system) if system == "darwin" else None


def pick(setting: str, system: str | None = None, installed: dict | None = None,
         os_default: str | None = None) -> WindowPick | None:
    """The browser that draws the window for `setting`, or None when no browser here can. A choice that can't be used
    falls back to Auto, with a note for the terminal and the Settings page."""
    system = _system(system)
    if installed is None:
        found = _installed(system)
        default = os_default if os_default is not None else _os_default(system)
    else:
        found, default = {key: str(value) for key, value in installed.items()}, os_default
    usable = [choice for choice in _order(system) if choice in found and choice in offered(system)]
    if not usable:
        return None
    auto = usable[0]
    if system == "darwin" and len(usable) > 1:  # not the everyday browser, when there is another
        auto = next(choice for choice in usable if choice != default)
    if setting in usable:
        return WindowPick(WindowBrowser(setting, NAMES[setting], found[setting]), "")
    note = ""
    if setting in NAMES:
        why = "isn't installed" if setting in offered(system) else "draws the window only on Windows"
        note = f"{NAMES[setting]} {why}: the window uses {NAMES[auto]}. Change it in Settings."
    return WindowPick(WindowBrowser(auto, NAMES[auto], found[auto]), note)


def choices(system: str | None = None, installed: dict | None = None, os_default: str | None = None) -> list[dict]:
    """What Settings lists: each offered choice, whether it is installed, and Auto named after its pick."""
    system = _system(system)
    if installed is None:
        found = _installed(system)
        default = os_default if os_default is not None else _os_default(system)
    else:
        found, default = dict(installed), os_default
    auto = pick("auto", system, found, default)
    rows = []
    for choice in offered(system):
        if choice == "auto":
            rows.append({"id": "auto", "name": f"Auto ({auto.browser.name})" if auto else "Auto",
                         "installed": auto is not None})
        else:
            rows.append({"id": choice, "name": NAMES[choice], "installed": choice in found})
    return rows


def window_profile(home, browser_id: str) -> Path:
    """The window's own profile, one per browser: two Chromium brands must never share a profile folder."""
    return Path(home) / "app" / "window" / browser_id


def window_args(binary, profile, url: str) -> list[str]:
    """The window's whole command line. The autoplay flag lets Mission Control speak without a click first; it applies
    only to this browser process, on AI Browser's own profile, where no site is ever loaded."""
    return [str(binary), f"--user-data-dir={profile}", f"--app={url}", "--no-first-run", "--no-default-browser-check",
            "--disable-search-engine-choice-screen", "--window-size=1440,960",
            "--autoplay-policy=no-user-gesture-required"]
```

In `tests/conftest.py`, extend `_never_the_users_browsers`. These are the parts of browser-detection's test fixture
that keep detection off this computer, now that the app calls `installed()` and `os_default()`. Add these lines at
the end of the fixture's body:

```python
    from ai_browser import browsers, platforms

    nothing = tmp_path_factory.getbasetemp() / "no-apps-here"
    nothing.mkdir(exist_ok=True)
    fakes = {"app_folders": lambda system=None, env=None: [nothing],
             "windows_browser_commands": lambda: [],
             "windows_https_progid": lambda: None,
             "launch_services_file": lambda: nothing / "no-launch-services.plist"}
    for module in (platforms, browsers):  # browsers.py may hold its own reference to one of them
        for name, fake in fakes.items():
            if hasattr(module, name):
                monkeypatch.setattr(module, name, fake)
```

Then add one sentence to its docstring: "Detection (`browsers.installed()`, `os_default()`) sees no app folder, no
registry and no LaunchServices file of this computer."

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_appwindow.py -q -p no:randomly`

Expected: PASS.

Run: `uv run pytest tests/test_browsers.py -q -p no:randomly`

Expected: PASS. Its own fixture still sets its own folders on top of these.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/window.py tests/test_appwindow.py tests/conftest.py
git commit -m "feat(window): which browser draws AI Browser's window, and its exact command line"
```

### Task 2: `settings.py`: the settings file and its typed view

**Files:**
- Create: `src/ai_browser/settings.py`
- Test: `tests/test_settings.py` (new)

**Interfaces:**
- Consumes: `window.offered(system)` (Task 1) and `syncdir.write_atomic(path, data, mode)`.
- Produces (`ai_browser.settings`):
  - `FILE = "settings.json"`, `MODELS = ("opus", "sonnet", "haiku")` and
    `DEFAULTS = {"window_browser": "auto", "model": None, "voice": False}`;
  - `read_settings(home) -> dict`: the raw object, `{}` for a missing, unreadable or non-object file. It never raises.
    Wave C's `places.py` imports it;
  - `write_setting(home, key, value) -> None`: it reads, sets one key, and writes atomically with mode 0600, keeping
    every other key. Wave C imports it too;
  - `class Settings(home, system=None)`:
    - `.path`;
    - `.get() -> dict`: `DEFAULTS` merged with the file, a key at a time; a bad value gives that key's default;
    - `.set(key, value) -> dict`: checks, writes, and returns `get()`. It raises `ValueError` with a plain message.

- [ ] **Step 1: Write the failing tests**

`tests/test_settings.py`:

```python
"""<home>/settings.json: one reader and one writer, and the typed view on top (the window's browser, the model,
Voice). Nothing here ever raises on a bad file."""

import json

import pytest

from conftest import file_mode


def test_read_settings_never_raises(tmp_path):
    from ai_browser.settings import read_settings

    path = tmp_path / "settings.json"
    assert read_settings(tmp_path) == {}  # missing
    path.write_text("{not json", encoding="utf-8")
    assert read_settings(tmp_path) == {}
    path.write_text("[1, 2]", encoding="utf-8")  # JSON, but not an object
    assert read_settings(tmp_path) == {}
    path.unlink()
    path.mkdir()  # a folder where the file should be
    assert read_settings(tmp_path) == {}


def test_write_setting_keeps_the_other_keys(tmp_path):
    from ai_browser.settings import read_settings, write_setting

    place = {"id": "brave", "user_data_dir": "/x/Brave-Browser", "profile": "Default"}
    write_setting(tmp_path, "agents_browser", place)  # as wave C writes it
    write_setting(tmp_path, "model", "opus")
    assert read_settings(tmp_path) == {"agents_browser": place, "model": "opus"}
    assert file_mode(tmp_path / "settings.json") in (0o600, None)


def test_the_defaults_and_a_bad_value_for_one_key(tmp_path):
    from ai_browser.settings import DEFAULTS, Settings

    settings = Settings(tmp_path, system="darwin")
    assert settings.path == tmp_path / "settings.json"
    assert settings.get() == DEFAULTS == {"window_browser": "auto", "model": None, "voice": False}
    (tmp_path / "settings.json").write_text(json.dumps({"model": "gpt", "voice": True, "window_browser": "brave"}),
                                            encoding="utf-8")
    assert settings.get() == {"window_browser": "brave", "model": None, "voice": True}  # only the model falls back


def test_a_broken_file_gives_the_defaults_and_stays_until_the_next_set(tmp_path):
    from ai_browser.settings import DEFAULTS, Settings

    path = tmp_path / "settings.json"
    path.write_text('{"model": "opus",', encoding="utf-8")  # half-written
    settings = Settings(tmp_path, system="darwin")
    assert settings.get() == DEFAULTS
    assert path.read_text(encoding="utf-8") == '{"model": "opus",'  # reading never rewrites it
    assert settings.set("model", "haiku")["model"] == "haiku"
    assert json.loads(path.read_text(encoding="utf-8")) == {"model": "haiku"}


def test_set_checks_each_value(tmp_path):
    from ai_browser.settings import Settings

    mac = Settings(tmp_path, system="darwin")
    for key, value in (("window_browser", "edge"), ("window_browser", 3), ("model", "gpt"), ("voice", "yes"),
                       ("colour", "red")):
        with pytest.raises(ValueError):
            mac.set(key, value)
    assert not (tmp_path / "settings.json").exists()  # nothing written for a refused value
    assert Settings(tmp_path, system="win32").set("window_browser", "edge")["window_browser"] == "edge"
    assert mac.set("model", None)["model"] is None and mac.set("voice", True)["voice"] is True


def test_an_unknown_key_survives_a_set(tmp_path):
    from ai_browser.settings import Settings, read_settings

    (tmp_path / "settings.json").write_text(json.dumps({"from_a_newer_build": [1, 2]}), encoding="utf-8")
    Settings(tmp_path, system="darwin").set("voice", True)
    assert read_settings(tmp_path) == {"from_a_newer_build": [1, 2], "voice": True}
    assert file_mode(tmp_path / "settings.json") in (0o600, None)


def test_a_file_from_another_computer_falls_back_key_by_key(tmp_path):  # Review Focus 2
    from ai_browser.settings import Settings, read_settings

    (tmp_path / "settings.json").write_text(json.dumps({"window_browser": "edge", "model": "opus",
                                                        "agents_browser": {"id": "brave"}}), encoding="utf-8")
    mac = Settings(tmp_path, system="darwin")
    assert mac.get() == {"window_browser": "auto", "model": "opus", "voice": False}  # Edge draws it on Windows only
    mac.set("voice", True)
    assert read_settings(tmp_path)["window_browser"] == "edge"  # kept for the Windows computer that wrote it
    assert Settings(tmp_path, system="win32").get()["window_browser"] == "edge"
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_settings.py -q -p no:randomly`

Expected: FAIL with `ModuleNotFoundError: No module named 'ai_browser.settings'`.

- [ ] **Step 3: Write `settings.py`**

```python
"""The app's own settings: <home>/settings.json, one small JSON object the app reads and writes for the user.

One reader and one writer touch the file: read_settings and write_setting (wave C's places.py uses them too). A
missing, unreadable, broken or half-written file reads as {} and never raises, so the app always starts. A write is
atomic, mode 0600, and keeps every key it doesn't set, so a file written by a newer build survives an older one.
Settings(home) is the typed view on top: the window's browser, the model and Voice, each value checked."""

from __future__ import annotations

import json
from pathlib import Path

from .app.window import NAMES, offered
from .syncdir import write_atomic

FILE = "settings.json"
MODELS = ("opus", "sonnet", "haiku")
DEFAULTS = {"window_browser": "auto", "model": None, "voice": False}


def _path(home) -> Path:
    return Path(home) / FILE


def read_settings(home) -> dict:
    """The file's object, or {} when it is missing, unreadable or not a JSON object."""
    try:
        data = json.loads(_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_setting(home, key: str, value) -> None:
    """Set one key, keeping every other."""
    data = read_settings(home)
    data[key] = value
    write_atomic(_path(home), (json.dumps(data, indent=1, ensure_ascii=False) + "\n").encode("utf-8"), 0o600)


def _either(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} or {names[-1]}"


class Settings:
    """The typed view: get() never raises, and set() checks the value before anything is written."""

    def __init__(self, home, system: str | None = None):
        self.home = Path(home)
        self.path = _path(home)
        self.system = system

    def _check(self, key: str, value) -> None:
        if key == "window_browser":
            choices = offered(self.system)
            if not isinstance(value, str) or value not in choices:
                names = [NAMES.get(choice, "Auto") for choice in choices]
                raise ValueError(f"The window's browser must be {_either(names)}")
        elif key == "model":
            if value is not None and value not in MODELS:
                raise ValueError("The model must be Opus, Sonnet or Haiku")
        elif key == "voice":
            if not isinstance(value, bool):
                raise ValueError("Voice is on or off")
        else:
            raise ValueError(f"There is no setting {key!r}")

    def get(self) -> dict:
        stored, result = read_settings(self.home), dict(DEFAULTS)
        for key in DEFAULTS:
            if key in stored:
                try:
                    self._check(key, stored[key])
                except ValueError:
                    continue  # this key falls back; the others stand
                result[key] = stored[key]
        return result

    def set(self, key: str, value) -> dict:
        self._check(key, value)
        write_setting(self.home, key, value)
        return self.get()
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_settings.py tests/test_appwindow.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/settings.py tests/test_settings.py
git commit -m "feat(settings): <home>/settings.json with one reader, one writer and a typed view"
```

### Task 3: `AppWindow`: start the window, hand off, close only what it started

**Files:**
- Modify: `src/ai_browser/app/window.py` (part 2)
- Test: `tests/test_appwindow.py`

**Interfaces:**
- Consumes:
  - `window_args`, `window_profile`, `pick` and `WindowBrowser` (Task 1);
  - `browsers.running(data_dir, system=None) -> bool | None` and `browsers.all_data_dirs(system=None, env=None)`;
  - `platforms.shortcut(mac, other, system)`.
- Produces (`ai_browser.app.window`):
  - `QUIT_WAIT = 10` (seconds);
  - `NO_BROWSER = "AI Browser needs Google Chrome, Brave or Microsoft Edge to draw its window: install one, then
    start again."`;
  - `HANDED_OFF = "AI Browser's window was opened by a browser already running on its profile: quit it yourself
    ({how})"`;
  - `class WindowError(RuntimeError)`;
  - `class AppWindow(home, browser, note="", extra_args=(), system=None)`:
    - `.id`, `.name`, `.note`, `.browser`, `.profile`, `.process` and `.handed_off`;
    - `.launch(url) -> None`, which raises `WindowError("AI Browser's window could not start: …")`;
    - `.close() -> str`, which returns "" or the hand-off note.

    `system` is a seam for the Windows tests, beyond the spec's signature.
  - `default_launcher(home) -> Callable[[str], AppWindow]`: it takes the `window_browser` setting and returns an
    `AppWindow`, or raises `WindowError(NO_BROWSER)`. `run_app` (Task 17) calls it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_appwindow.py`:

```python
CHROME_ROW = window.WindowBrowser("chrome", "Google Chrome", "/x/Google Chrome")
START = "http://127.0.0.1:8792/open?code=abc"


class FakeProcess:
    """A browser process that ignores terminate (as a hung one would), or one that has already exited."""

    def __init__(self, exited=False):
        self.pid = 4242
        self.calls = []
        self.returncode = 0 if exited else None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.calls.append("terminate")

    def kill(self):
        self.calls.append("kill")
        self.returncode = -9

    def wait(self, timeout=None):
        self.calls.append("wait")
        if self.returncode is None:
            raise subprocess.TimeoutExpired("browser", timeout)
        return self.returncode


@pytest.fixture
def recorded(monkeypatch):
    """Popen and subprocess.run recorded, nothing started; no browser runs on any profile."""
    seen = {"popen": [], "run": [], "process": FakeProcess()}

    def popen(args, **options):
        seen["popen"].append((list(args), options))
        return seen["process"]

    def run(args, **options):
        seen["run"].append(list(args))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(window.subprocess, "Popen", popen)
    monkeypatch.setattr(window.subprocess, "run", run)
    monkeypatch.setattr(window, "QUIT_WAIT", 0.01)
    monkeypatch.setattr(window.browsers, "running", lambda profile, system=None: False)
    return seen


def test_launch_starts_exactly_the_window_command(tmp_path, recorded):
    app = window.AppWindow(tmp_path / "home", CHROME_ROW)
    app.launch(START)
    [(args, options)] = recorded["popen"]
    profile = tmp_path / "home" / "app" / "window" / "chrome"
    assert args == window.window_args("/x/Google Chrome", profile, START)
    assert options["stdout"] == options["stderr"] == subprocess.DEVNULL and profile.is_dir()
    assert (app.id, app.name, app.note, app.handed_off) == ("chrome", "Google Chrome", "", False)


def test_a_browser_that_cannot_start_is_said_plainly(tmp_path, monkeypatch, recorded):
    def broken(args, **options):
        raise OSError("No such file or directory")

    monkeypatch.setattr(window.subprocess, "Popen", broken)
    with pytest.raises(window.WindowError, match="^AI Browser's window could not start: No such file or directory"):
        window.AppWindow(tmp_path / "home", CHROME_ROW).launch(START)


def test_close_asks_then_kills_what_it_started(tmp_path, recorded):
    app = window.AppWindow(tmp_path / "home", CHROME_ROW, system="darwin")
    app.launch(START)
    assert app.close() == ""
    assert recorded["process"].calls == ["terminate", "wait", "kill", "wait"] and recorded["run"] == []


def test_on_windows_close_is_a_click_on_its_x_first(tmp_path, recorded):
    edge = window.WindowBrowser("edge", "Microsoft Edge", "C:\\Edge\\msedge.exe")
    app = window.AppWindow(tmp_path / "home", edge, system="win32")
    app.launch(START)
    assert app.close() == ""
    assert recorded["run"] == [["taskkill", "/PID", "4242"]]  # no /F: Edge closes as if its × was clicked
    assert recorded["process"].calls == ["wait", "kill", "wait"]  # never terminate(): Windows counts that a crash


def test_a_failing_taskkill_still_ends_the_window(tmp_path, monkeypatch, recorded):  # Review Focus 5
    def missing(args, **options):
        raise FileNotFoundError(2, "The system cannot find the file specified", "taskkill")

    monkeypatch.setattr(window.subprocess, "run", missing)
    app = window.AppWindow(tmp_path / "home", CHROME_ROW, system="win32")
    app.launch(START)
    assert app.close() == "" and recorded["process"].calls == ["wait", "kill", "wait"]


def test_a_hand_off_ends_nothing(tmp_path, monkeypatch, recorded):
    monkeypatch.setattr(window.browsers, "running", lambda profile, system=None: True)  # left from a crashed run
    app = window.AppWindow(tmp_path / "home", CHROME_ROW, system="darwin")
    app.launch(START)
    assert len(recorded["popen"]) == 1  # still started: it hands its command line to the running browser
    assert app.handed_off and app.close() == ("AI Browser's window was opened by a browser already running on its "
                                              "profile: quit it yourself (⌘Q)")
    assert recorded["process"].calls == []
    other = window.AppWindow(tmp_path / "home", CHROME_ROW, system="win32")
    other.launch(START)
    assert other.close().endswith("quit it yourself (close its windows)") and recorded["run"] == []


def test_a_window_that_already_ended_is_left_alone(tmp_path, recorded):
    recorded["process"] = FakeProcess(exited=True)  # Ctrl-C reached the browser too
    app = window.AppWindow(tmp_path / "home", CHROME_ROW, system="darwin")
    app.launch(START)
    assert app.close() == "" and recorded["process"].calls == []


def test_the_profile_is_never_a_real_browsers_folder(tmp_path, monkeypatch, recorded):
    data = tmp_path / "Google" / "Chrome"
    data.mkdir(parents=True)
    monkeypatch.setattr(window.browsers, "all_data_dirs", lambda system=None, env=None: [data])
    with pytest.raises(window.WindowError, match="a browser's own data folder"):
        window.AppWindow(data / "inside", CHROME_ROW, system="darwin").launch(START)  # <data>/inside/app/window/…
    inside = window.AppWindow(tmp_path / "home", CHROME_ROW, system="darwin")
    monkeypatch.setattr(window.browsers, "all_data_dirs", lambda system=None, env=None: [inside.profile])
    with pytest.raises(window.WindowError, match="a browser's own data folder"):
        inside.launch(START)  # the profile is itself a real one
    assert recorded["popen"] == []


def test_the_default_launcher_picks_or_says_why(tmp_path, monkeypatch):
    monkeypatch.delenv("AIB_CHROME_BINARY", raising=False)
    if sys.platform in ("darwin", "win32"):  # on Linux the PATH finders may still find a browser
        with pytest.raises(window.WindowError, match="^AI Browser needs Google Chrome, Brave or Microsoft Edge"):
            window.default_launcher(tmp_path)("auto")  # nothing installed: the conftest fixture
    program = tmp_path / "chrome-bin"
    program.write_bytes(b"")
    monkeypatch.setenv("AIB_CHROME_BINARY", str(program))
    app = window.default_launcher(tmp_path)("brave")
    assert (app.id, app.browser.binary, app.profile) == ("chrome", str(program),
                                                         tmp_path / "app" / "window" / "chrome")
    if sys.platform in ("darwin", "win32"):
        assert app.note == "Brave isn't installed: the window uses Google Chrome. Change it in Settings."
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_appwindow.py -q -p no:randomly`

Expected: the new tests FAIL with `AttributeError: module 'ai_browser.app.window' has no attribute 'subprocess'` (in
the fixture) or `… has no attribute 'AppWindow'`. Task 1's tests still PASS.

- [ ] **Step 3: Write `AppWindow` and `default_launcher`**

In `src/ai_browser/app/window.py`, add these imports to the existing ones:

```python
import contextlib
import ntpath
import subprocess
from collections.abc import Callable

from .. import browsers, platforms
```

(`from .. import browsers` becomes `from .. import browsers, platforms`.) Append:

```python
QUIT_WAIT = 10  # seconds the window's browser gets to quit before it is killed
NO_BROWSER = ("AI Browser needs Google Chrome, Brave or Microsoft Edge to draw its window: install one, then start "
              "again.")
HANDED_OFF = "AI Browser's window was opened by a browser already running on its profile: quit it yourself ({how})"


class WindowError(RuntimeError):
    """AI Browser's window can't start; the message says why, in plain words."""


def _inside(path, folder, system: str) -> bool:
    """Whether `path` is `folder` or inside it: resolved, and on Windows without regard to case."""
    left, right = os.path.realpath(path), os.path.realpath(folder)
    if system == "win32":
        left, right = ntpath.normcase(left), ntpath.normcase(right)
    return left == right or left.startswith(right.rstrip("/\\") + os.sep)


class AppWindow:
    """This run's window: started on <home>/app/window/<browser>, ended at the app's end. It ends only the process it
    started, and nothing after a hand-off (a browser already running on its profile took the launch)."""

    def __init__(self, home, browser: WindowBrowser, note: str = "", extra_args=(), system: str | None = None):
        self.browser = browser
        self.id, self.name, self.note = browser.id, browser.name, note
        self.profile = window_profile(home, browser.id)
        self.extra_args = tuple(extra_args)  # one test only: ("--headless=new", url); the product never passes any
        self.system = _system(system)
        self.process = None
        self.handed_off = False

    def launch(self, url: str) -> None:
        if any(_inside(self.profile, folder, self.system) for folder in browsers.all_data_dirs(system=self.system)):
            raise WindowError(f"AI Browser's window could not start: {self.profile} is in a browser's own data folder")
        self.profile.mkdir(parents=True, exist_ok=True)
        # Left from a crashed run: the new process hands its command line to that browser and exits, and that browser
        # opens the window. It reads the profile's own lock only, and never connects.
        self.handed_off = browsers.running(self.profile, system=self.system) is True
        try:
            self.process = subprocess.Popen([*window_args(self.browser.binary, self.profile, url), *self.extra_args],
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            raise WindowError(f"AI Browser's window could not start: {exc.strerror or exc}") from None

    def close(self) -> str:
        """Quit the browser this run started: asked first (SIGTERM; on Windows taskkill without /F, as a click on its
        × does, so Edge offers no "Restore pages?" next time), killed after QUIT_WAIT. After a hand-off it ends nothing
        and returns what the user should do."""
        if self.handed_off:
            return HANDED_OFF.format(how=platforms.shortcut("⌘Q", "close its windows", self.system))
        process = self.process
        if process is None or process.poll() is not None:
            return ""
        if self.system == "win32":
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                subprocess.run(["taskkill", "/PID", str(process.pid)], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=QUIT_WAIT)
        else:
            process.terminate()
        try:
            process.wait(timeout=QUIT_WAIT)
        except subprocess.TimeoutExpired:
            process.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=QUIT_WAIT)
        return ""


def default_launcher(home) -> Callable[[str], AppWindow]:
    """run_app's launcher: the window_browser setting in, this run's AppWindow out (or WindowError)."""
    def launcher(setting: str) -> AppWindow:
        found = pick(setting)
        if found is None:
            raise WindowError(NO_BROWSER)
        return AppWindow(home, found.browser, found.note)
    return launcher
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_appwindow.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/window.py tests/test_appwindow.py
git commit -m "feat(window): start the window on its own profile, hand off, and close only what it started"
```

### Task 4: `TabWatch` hides the app's own origin; `BraveLink` passes it on

**Files:**
- Modify: `src/ai_browser/app/tabs.py` (`TabWatch.__init__`, `tabs()`, wave A's `pages()`, the docstring)
- Modify: `src/ai_browser/app/bravelink.py` (`BraveLink.__init__` and the `TabWatch(` call it makes)
- Modify: `src/ai_browser/app/run.py` and `tests/test_home.py`: the two `TabWatch(app.ws_url, app.extension_id)`
  calls, which last until Tasks 13 and 17 replace them
- Modify: `tests/test_tabwatch.py` (rewritten on `throwaway_chrome`), `tests/conftest.py` (`PIPE_FIXTURES`)
- Test: `tests/test_tabwatch.py`, `tests/test_bravelink.py`

**Interfaces:**
- Consumes: the relay's `TabWatch(ws_url, extension_id, open_timeout=10, cdp=None)`, and wave A's `pages()` and
  `BraveLink(folder, watcher_id="", allow_wait, every, tokens=None)`.
- Produces:
  - `TabWatch(ws_url, hidden_origin="", open_timeout=10, cdp=None)`;
  - `TabWatch.hidden_origin`;
  - `tabs()` and `pages()` leave out every page whose address starts with `hidden_origin + "/"`, and
    `chrome://newtab`;
  - `has_pages()` stays until Task 17;
  - `BraveLink(..., app_origin="")` and `BraveLink.app_origin`. The `TabWatch` it makes gets
    `hidden_origin=app_origin`.

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_tabwatch.py` whole. It no longer needs AI Browser's Chrome or `test_appmode`'s helpers:

```python
"""TabWatch, the app's view of a browser's tabs: the tab list (without AI Browser's own pages), Watch, closing an
agent's tabs, thumbnails, and a tab's text for a skill draft. A throwaway headless Chrome stands in for the browser."""

import asyncio

import pytest

from ai_browser.chrome import chrome_binary

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


@pytest.fixture
async def pages(throwaway_chrome):
    """(the throwaway Chrome's websocket, the test pages' base, another local origin standing in for the app's)."""
    from ai_browser import testpages
    from ai_browser.chrome import find_ws_url

    base, other, stop = testpages.serve_host()
    yield find_ws_url(throwaway_chrome, timeout=20), base, other.rstrip("/")
    stop()


async def until(check, seconds=5):
    for _ in range(int(seconds * 10)):
        if check():
            return True
        await asyncio.sleep(0.1)
    return False


def test_the_rows_leave_out_the_apps_origin_and_new_tab_pages():
    from ai_browser.app.tabs import TabWatch

    watch = TabWatch("ws://127.0.0.1:1/unused", hidden_origin="http://127.0.0.1:8792")
    for target, url in (("U1", "https://mail.example/"), ("W1", "http://127.0.0.1:8792/home"),
                        ("W2", "http://127.0.0.1:8792/open?code=x"), ("N1", "chrome://newtab/"),
                        ("P1", "http://127.0.0.1:87921/x"), ("O1", "http://127.0.0.1:8793/home")):
        watch._pages[target] = {"target": target, "url": url, "title": target}
    assert [tab["target"] for tab in watch.tabs()] == ["U1", "P1", "O1"]  # another port is another origin
    assert watch.hidden_origin == "http://127.0.0.1:8792"
    assert [tab["target"] for tab in TabWatch("ws://127.0.0.1:1/unused").tabs()] == []


@CHROME
async def test_the_tab_list_follows_chrome_and_leaves_out_the_apps_pages(pages):
    from ai_browser.app.tabs import TabWatch
    from ai_browser.cdp import CDP

    ws_url, base, app_origin = pages
    watch = TabWatch(ws_url, hidden_origin=app_origin)
    changes = []
    watch.on_change(changes.append)
    await watch.start()
    cdp = await CDP.connect(ws_url)
    try:
        page = (await cdp.send("Target.createTarget", {"url": base + "privacy.html"}))["targetId"]
        ours = (await cdp.send("Target.createTarget", {"url": app_origin + "/form.html"}))["targetId"]
        assert await until(lambda: any(t["target"] == page and t["title"] == "Privacy" for t in watch.tabs()))
        await asyncio.sleep(0.5)
        assert changes and not any(tab["target"] == ours for tab in watch.tabs())  # a 403 page in Brave isn't a tab
        shot = await watch.thumbnail(page)
        assert shot and shot[:2] == b"\xff\xd8" and len(shot) < 80_000  # a small JPEG
        await watch.close_targets([page, "no-such-target"])
        assert await until(lambda: not any(tab["target"] == page for tab in watch.tabs()))
    finally:
        await cdp.close()
        await watch.close()


@CHROME
async def test_watch_asks_chrome_to_bring_the_tab_forward(pages, monkeypatch):
    from ai_browser.app.tabs import TabWatch
    from ai_browser.cdp import CDP

    ws_url, base, _ = pages
    watch = TabWatch(ws_url)
    await watch.start()
    cdp = await CDP.connect(ws_url)
    sent, original = [], CDP.send

    async def spy(self, method, params=None, *args, **kwargs):
        sent.append((method, params))
        return await original(self, method, params, *args, **kwargs)

    try:
        first = (await cdp.send("Target.createTarget", {"url": base + "privacy.html"}))["targetId"]
        monkeypatch.setattr(CDP, "send", spy)
        await watch.watch(first)
        assert ("Target.activateTarget", {"targetId": first}) in sent
    finally:
        monkeypatch.undo()
        await cdp.close()
        await watch.close()


@CHROME
async def test_the_text_of_a_tab_for_a_skill_draft(pages):
    from ai_browser.app.tabs import TabWatch
    from ai_browser.cdp import CDP

    ws_url, base, _ = pages
    watch = TabWatch(ws_url)
    await watch.start()
    cdp = await CDP.connect(ws_url)
    try:
        page = (await cdp.send("Target.createTarget", {"url": base + "brain/orders.html"}))["targetId"]
        for _ in range(50):
            text = await watch.page_text(page)
            if "#1001" in text:
                break
            await asyncio.sleep(0.1)
        assert "Orders" in text and "#1001" in text
        assert await watch.page_text("no-such-target") == ""
    finally:
        await cdp.close()
        await watch.close()
```

If wave A added tests to `tests/test_tabwatch.py` (watcher-safety's
`test_pages_carry_their_context_and_workers_are_seen`), keep them below these. Move them from the old `app_browser`
fixture onto `pages`, as the spec says: "its `worker_contexts(app.extension_id)` line goes, because the throwaway loads
no extension". The `watcher` fixture's test of a worker's context still covers that.

Add to `tests/test_bravelink.py`:

```python
async def test_brave_link_leaves_out_the_apps_own_pages(tmp_path, monkeypatch):
    from ai_browser.app import bravelink
    from ai_browser.app.tabs import TabWatch
    from fake_brave import FakePort

    made = []

    class Recording(TabWatch):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            made.append(self)

    monkeypatch.setattr(bravelink, "TabWatch", Recording)
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder)
    await port.start()
    link = bravelink.BraveLink(folder, allow_wait=2, every=0.1, app_origin="http://127.0.0.1:8792")
    await link.start()
    try:
        await link.connect()
        assert link.app_origin == "http://127.0.0.1:8792"
        assert made and made[-1].hidden_origin == "http://127.0.0.1:8792"  # a 403 page the user opened in Brave
    finally:
        await link.close()
        await port.stop()
```

(`FakePort` moved into `tests/fake_brave.py` with the relay. If the merged one is still in `test_bravelink.py`, use
that one.)

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_tabwatch.py tests/test_bravelink.py::test_brave_link_leaves_out_the_apps_own_pages -q -p no:randomly`

Expected: FAIL with `TypeError: TabWatch.__init__() got an unexpected keyword argument 'hidden_origin'` and
`BraveLink.__init__() got an unexpected keyword argument 'app_origin'`.

- [ ] **Step 3: Hide an origin instead of an extension**

In `src/ai_browser/app/tabs.py`:
- The docstring becomes:

  ```python
  """The app's view of a browser's tabs (BraveLink's, over the relay's one connection): every tab, Watch (bring a tab to
  the front), closing an agent's tabs when the user closes the agent, a tab's text for a skill draft, and small
  thumbnails of the tabs agents work in. AI Browser's own pages (its origin, http://127.0.0.1:<port>) are never listed:
  only its window shows them, and a copy the user opened in Brave is a 403 page, not one of their tabs."""
  ```

- In `TabWatch.__init__`, the parameter `extension_id: str` becomes `hidden_origin: str = ""`, and
  `self.extension_id = extension_id` becomes `self.hidden_origin = hidden_origin.rstrip("/")`. Keep the relay's
  `open_timeout` and `cdp` parameters as they are.
- Add this method right after `__init__`:

  ```python
      def _hidden(self, url: str) -> bool:
          """AI Browser's own pages (the app's origin) and the new tab page are never anybody's tab."""
          return url.startswith("chrome://newtab") or (bool(self.hidden_origin)
                                                       and url.startswith(self.hidden_origin + "/"))
  ```

- In `tabs()`, replace the lines

  ```python
          own = f"chrome-extension://{self.extension_id}/"
          return [dict(page) for page in self._pages.values()
                  if not page["url"].startswith(own) and not page["url"].startswith("chrome://newtab")]
  ```

  with the same filter on `not self._hidden(page["url"])`. Keep the row shape wave A gave it (exactly `target`,
  `url` and `title`). For example:

  ```python
          return [{key: page[key] for key in ("target", "url", "title")} for page in self._pages.values()
                  if not self._hidden(page["url"])]
  ```

- In wave A's `pages()`, use the same `if not self._hidden(page["url"])` in place of its extension test.
- Its docstring line for `tabs()` becomes `"""The user's and the agents' tabs; AI Browser's own pages (the app's origin)
  are left out."""`.

In `src/ai_browser/app/bravelink.py`:
- `BraveLink.__init__` gains a last keyword, `app_origin: str = ""`, and the line `self.app_origin = app_origin`.
- Find the `TabWatch(` call BraveLink makes when it connects (since the relay, over `self.relay.local()`). Pass
  `hidden_origin=self.app_origin` by keyword, and drop the positional extension id it passes today (`""`). For
  example, `TabWatch("", "", open_timeout=self.allow_wait, cdp=self.relay.local())` becomes
  `TabWatch("", hidden_origin=self.app_origin, open_timeout=self.allow_wait, cdp=self.relay.local())`.

Until Tasks 13 and 17 replace them, AI Browser's own `TabWatch` must still hide its extension pages. In
`src/ai_browser/app/run.py` and in the `stack` fixture of `tests/test_home.py`, replace
`TabWatch(app.ws_url, app.extension_id)` with:

```python
TabWatch(app.ws_url, f"chrome-extension://{app.extension_id}")
```

In `tests/conftest.py`, `PIPE_FIXTURES` loses `"app_browser"`. The fixture is gone.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_tabwatch.py tests/test_bravelink.py -q -p no:randomly`

Expected: PASS.

Run: `uv run pytest tests/test_home.py -q -p no:randomly`

Expected: PASS, unchanged. AI Browser's own pages are still left out of its list.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/tabs.py src/ai_browser/app/bravelink.py src/ai_browser/app/run.py tests/test_home.py \
  tests/test_tabwatch.py tests/test_bravelink.py tests/conftest.py
git commit -m "feat(tabs): the tab list hides AI Browser's own origin, not its extension"
```

### Task 5: The pages move to `app/ui/`

**Files:**
- Move (`git mv`): every file of `src/ai_browser/app/extension/` into `src/ai_browser/app/ui/`, except `panel.html`,
  `panel.js`, `panel.css`, `manifest.json` and `worker.js`
- Modify: `src/ai_browser/appbrowser.py` (`prepare_extension` copies `app/ui/` plus `app/extension/`, until Task 21)
- Modify: `src/ai_browser/brain/watcher.py` (`SHARED_SOURCE`)
- Modify: `tests/test_talk.py` (`EXTENSION`), `tests/test_portable.py` (the page guard's folders)
- Test: `tests/test_ui_static.py` (new)

**Interfaces:**
- Produces:
  - `src/ai_browser/app/ui/`, holding AI Home's, Mission Control's and the shared pages and scripts, with their git
    history;
  - `brain.watcher.SHARED_SOURCE == APP / "ui"`;
  - `appbrowser.UI_SOURCE`, so that until Task 21 AI Browser's old extension folder is still `app/ui/` plus
    `app/extension/`.

  Wave A's page changes move as they are: the numbers, Your tabs, the cards, the clients list and the scope lines.

- [ ] **Step 1: Write the failing test**

`tests/test_ui_static.py`:

```python
"""AI Browser's pages, read as files: where they live, and (from Task 14) what they never do."""

from pathlib import Path

APP = Path(__file__).parents[1] / "src" / "ai_browser" / "app"
UI = APP / "ui"


def test_the_pages_live_in_app_ui_and_the_watcher_shares_them():
    from ai_browser.brain.watcher import SHARED_SOURCE, WATCHER_SHARED

    for name in ("home.html", "mission.html", "home.js", "mission.js", "link.js", "brainui.js", "brainui.css",
                 "check.js", "mic.js", "mic-worklet.js", "talk.js", "tablist.js", "chat.js", "permission.js"):
        assert (UI / name).is_file(), name
    assert sorted(path.name for path in (APP / "extension").iterdir() if not path.name.startswith(".")) == [
        "manifest.json", "panel.css", "panel.html", "panel.js", "worker.js"]
    assert SHARED_SOURCE == UI and all((UI / name).is_file() for name in WATCHER_SHARED)


def test_the_watchers_shared_files_are_byte_equal_to_app_uis(tmp_path):
    from ai_browser.brain.watcher import WATCHER_SHARED, prepare_watcher

    folder, _ = prepare_watcher(tmp_path, "http://127.0.0.1:8792", "token")
    for name in WATCHER_SHARED:
        assert (folder / name).read_bytes() == (UI / name).read_bytes(), name
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_ui_static.py -q -p no:randomly`

Expected: FAIL, because `app/ui/home.html` doesn't exist.

- [ ] **Step 3: Move the files**

```bash
mkdir -p src/ai_browser/app/ui
for path in src/ai_browser/app/extension/*; do
  case "$(basename "$path")" in
    panel.html|panel.js|panel.css|manifest.json|worker.js) ;;
    *) git mv "$path" src/ai_browser/app/ui/ ;;
  esac
done
```

In `src/ai_browser/brain/watcher.py`:
- `SHARED_SOURCE = APP / "extension"` becomes `SHARED_SOURCE = APP / "ui"`;
- the comment on `WATCHER_SHARED` becomes `# shared with AI Browser's window pages (app/ui)`.

In `src/ai_browser/appbrowser.py` (deleted in Task 21), the old extension folder still needs every file. Replace
`EXTENSION_SOURCE = …` and the `files = {…}` comprehension in `prepare_extension` with:

```python
UI_SOURCE = Path(__file__).with_name("app") / "ui"  # AI Home, Mission Control and the scripts they share
EXTENSION_SOURCE = Path(__file__).with_name("app") / "extension"  # the manifest, the worker and the side panel


def _files(source: Path) -> dict[str, bytes]:
    return {path.relative_to(source).as_posix(): path.read_bytes() for path in sorted(source.rglob("*"))
            if path.is_file() and not path.name.startswith(".") and "__pycache__" not in path.parts}
```

and in `prepare_extension`:

```python
    files = {**_files(UI_SOURCE), **_files(EXTENSION_SOURCE)}
```

In `tests/test_talk.py`, `EXTENSION = ROOT / "src" / "ai_browser" / "app" / "extension"` becomes
`EXTENSION = ROOT / "src" / "ai_browser" / "app" / "ui"`.

In `tests/test_portable.py::test_no_mac_words_where_windows_shows_them`, the `pages` list becomes:

```python
    pages = [*(SRC / "app" / "ui").rglob("*"), *(SRC / "app" / "watcher").rglob("*"), SRC / "app" / "setup.html"]
```

(Task 7 moves `setup.html` into `ui/` and drops the last item.)

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_ui_static.py tests/test_portable.py tests/test_appbrowser.py tests/test_talk.py::test_no_cloud_speech_anywhere_in_the_extension -q -p no:randomly`

Expected: PASS.

Run: `uv run pytest tests/test_home.py tests/test_watcher.py -q -p no:randomly`

Expected: PASS. AI Browser's extension folder still holds every page and the side panel, and the watcher's copies are
the same bytes.

- [ ] **Step 5: Commit**

```bash
git add -A src/ai_browser/app/ui src/ai_browser/app/extension src/ai_browser/appbrowser.py \
  src/ai_browser/brain/watcher.py tests/test_ui_static.py tests/test_talk.py tests/test_portable.py
git commit -m "refactor(ui): AI Browser's pages move to app/ui (git mv); the watcher shares them from there"
```

### Task 6: The one-time code, the window's cookie, and the page and file routes

**Files:**
- Modify: `src/ai_browser/app/server.py` (constants, `AppServer.__init__`, `start()`, new handlers)
- Create: `src/ai_browser/app/ui/icon.png` (a copy of `src/ai_browser/app/watcher/icon.png`)
- Create: `tests/ui_socket.py` (the cookie helper; Task 9 adds the socket)
- Test: `tests/test_app_server.py`

**Interfaces:**
- Consumes: `app/ui/` (Task 5).
- Produces (`ai_browser.app.server`):
  - `UI`, `PAGES`, `FILE_TYPES`, `OPEN_ANYWHERE`, `CODE_TTL = 60`, `NOT_HERE`, `USED_CODE` and `_clock()`;
  - on `AppServer`:
    - `ui_secret` (str) and `port` (int, or None before `start()`);
    - `origin` (`"http://127.0.0.1:<port>"`), `host_header` (`"127.0.0.1:<port>"`) and `cookie_name`
      (`"aib_ui_<port>"`);
    - `new_launch_code() -> str`;
    - `_cookie_ok(connection) -> bool`, for a `Request` or a `WebSocket`;
  - routes:
    - `GET /`: 303 to `/home`;
    - `GET /open?code=`: the swap;
    - `GET /home`, `/mission` and `/settings`: the page with the cookie, else 403;
    - `GET /{name}`: a `.js`, `.css` or `.png` file of `app/ui/`, which needs the cookie except for
      `OPEN_ANYWHERE`.
- Produces (`tests/ui_socket.py`): `ui_cookie(server) -> dict`, the `Cookie` header AI Browser's window sends.

- [ ] **Step 1: Write the failing tests**

`tests/ui_socket.py`:

```python
"""AI Browser's window, as the app server sees it, for tests that need it without a browser: the window's cookie
(aib_ui_<port>, set by swapping a one-time code), and from Task 9 a socket with that cookie and our exact Origin."""


def ui_cookie(server) -> dict:
    """The Cookie header AI Browser's window sends on every request (httpx takes it as a header)."""
    return {"Cookie": f"aib_ui_{server.port}={server.ui_secret}"}
```

Add to the imports of `tests/test_app_server.py`: `from ui_socket import ui_cookie`. Then append:

```python
async def fetch(method, url, **options):
    """One request from a fresh client: no cookie jar carries the window's cookie from one request to the next."""
    async with httpx.AsyncClient() as client:
        return await client.request(method, url, **options)


NOT_HERE = "AI Browser's pages open only in its own window. Start it with `uv run ai-browser app`."


async def test_the_one_time_code_becomes_the_windows_cookie(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        code = server.new_launch_code()
        answer = await fetch("GET", f"{url}/open", params={"code": code})
        assert answer.status_code == 303 and answer.headers["location"] == "/home"
        cookie = answer.headers["set-cookie"]
        assert cookie.startswith(f"aib_ui_{server.port}={server.ui_secret};")
        assert {"httponly", "samesite=strict", "path=/"} <= {part.strip().lower() for part in cookie.split(";")[1:]}
        assert "max-age" not in cookie.lower() and "expires" not in cookie.lower() and "secure" not in cookie.lower()
        again = await fetch("GET", f"{url}/open", params={"code": code})  # single use
        assert again.status_code == 403 and "This start link was used already or has expired." in again.text
        assert (await fetch("GET", f"{url}/open", params={"code": "nope"})).status_code == 403
        assert (await fetch("GET", f"{url}/open")).status_code == 403
        reload = await fetch("GET", f"{url}/open", params={"code": code}, headers=ui_cookie(server))
        assert reload.status_code == 303 and reload.headers["location"] == "/home"  # a reload of the window
        root = await fetch("GET", f"{url}/")
        assert root.status_code == 303 and root.headers["location"] == "/home"
        assert server.origin == url and server.host_header == url.removeprefix("http://")
        assert server.cookie_name == f"aib_ui_{server.port}" and len(server.ui_secret) >= 43
    finally:
        await server.stop()


async def test_a_start_code_lasts_a_minute(fake_claude, tmp_path, monkeypatch):
    from ai_browser.app import server as module

    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        clock = [1000.0]
        monkeypatch.setattr(module, "_clock", lambda: clock[0])
        code = server.new_launch_code()
        clock[0] += module.CODE_TTL + 1
        assert (await fetch("GET", f"{url}/open", params={"code": code})).status_code == 403
        old = server.new_launch_code()
        clock[0] += module.CODE_TTL + 1
        fresh = server.new_launch_code()  # expired codes are dropped whenever a new one is made
        assert old not in server._codes and fresh in server._codes
    finally:
        await server.stop()


async def test_pages_need_the_windows_cookie(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        for path in ("/home", "/mission", "/settings", "/link.js", "/home.js", "/home.css"):
            answer = await fetch("GET", url + path)
            assert answer.status_code == 403, path
            assert NOT_HERE in answer.text and "<script" not in answer.text, path
        home = await fetch("GET", url + "/home", headers=ui_cookie(server))
        assert home.status_code == 200 and home.headers["content-type"] == "text/html; charset=utf-8"
        assert '<script type="module" src="home.js"></script>' in home.text
        assert (await fetch("GET", url + "/mission", headers=ui_cookie(server))).status_code == 200
        script = await fetch("GET", url + "/link.js", headers=ui_cookie(server))
        assert script.status_code == 200 and script.headers["content-type"] == "text/javascript; charset=utf-8"
        style = await fetch("GET", url + "/home.css", headers=ui_cookie(server))
        assert style.headers["content-type"] == "text/css; charset=utf-8"
        icon = await fetch("GET", url + "/icon.png")  # no cookie: the setup page opens anywhere and shows it
        assert icon.status_code == 200 and icon.headers["content-type"] == "image/png"
        assert icon.content[:4] == b"\x89PNG"
        for path in ("/%2e%2e%2fserver.py", "/..%2Fserver.py", "/server.py", "/home.html", "/setup.html",
                     "/panel.js", "/manifest.json", "/worker.js", "/ui/home.js", "/config.json"):
            assert (await fetch("GET", url + path, headers=ui_cookie(server))).status_code == 404, path
    finally:
        await server.stop()
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_app_server.py -q -p no:randomly -k "one_time_code or start_code or need_the_windows_cookie"`

Expected: FAIL with `AttributeError: 'AppServer' object has no attribute 'new_launch_code'`.

- [ ] **Step 3: The code, the cookie and the routes**

```bash
cp src/ai_browser/app/watcher/icon.png src/ai_browser/app/ui/icon.png
```

In `src/ai_browser/app/server.py`:

1. Imports: `from starlette.responses import HTMLResponse, JSONResponse, Response` becomes
   `from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response`.
   (`PlainTextResponse` is used from Task 8 on.)
2. Under the line `SETUP_PAGE = Path(__file__).with_name("setup.html")`, add:

   ```python
   UI = Path(__file__).with_name("ui")  # AI Browser's pages, served to its window only
   PAGES = {"/home": "home.html", "/mission": "mission.html", "/settings": "settings.html"}
   FILE_TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".png": "image/png"}
   OPEN_ANYWHERE = {"setup.js", "setup.css", "icon.png"}  # the setup page's own files: it opens in Brave too
   CODE_TTL = 60  # seconds a one-time start code is good for
   NOT_HERE = "AI Browser's pages open only in its own window. Start it with `uv run ai-browser app`."
   USED_CODE = "This start link was used already or has expired. Start AI Browser again."
   ```

3. Above `class AppServer`, add:

   ```python
   def _clock() -> float:
       return time.monotonic()  # its own function, so a test moves the start codes' clock and nothing else


   def _refused_page(text: str) -> HTMLResponse:
       """A plain 403 page: one line of text, no script."""
       return HTMLResponse('<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><title>AI Browser</title>'
                           f"</head><body><p>{html.escape(text, quote=False)}</p></body></html>\n", status_code=403)
   ```

4. In `AppServer.__init__`, after `self.url: str | None = None`, add:

   ```python
           self.port: int | None = None  # the bound port, once start() has one
           self.ui_secret = secrets.token_urlsafe(32)  # the window's session cookie: set only by swapping a start code
           self._codes: dict[str, float] = {}  # one-time start codes -> when they expire (_clock)
           self._files = {path.name for path in UI.iterdir() if path.is_file() and path.suffix in FILE_TYPES}
   ```

5. Add these members to `AppServer`, right after `allow_origin`:

   ```python
       @property
       def origin(self) -> str:
           """AI Browser's pages' own origin: the only Origin a window socket may carry."""
           return f"http://{self.host}:{self.port}"

       @property
       def host_header(self) -> str:
           return f"{self.host}:{self.port}"

       @property
       def cookie_name(self) -> str:
           return f"aib_ui_{self.port}"  # cookies on 127.0.0.1 reach every port: the name keeps two apps apart

       def new_launch_code(self) -> str:
           """A start code for the window's address: single use, CODE_TTL seconds. Expired ones are dropped here."""
           now = _clock()
           self._codes = {code: until for code, until in self._codes.items() if until > now}
           code = secrets.token_urlsafe(32)
           self._codes[code] = now + CODE_TTL
           return code

       def _take_code(self, given: str) -> bool:
           now = _clock()
           for code, until in list(self._codes.items()):
               if hmac.compare_digest(code.encode(), given.encode()):
                   del self._codes[code]  # used: never again, valid or not
                   return until > now
           return False

       def _cookie_ok(self, connection) -> bool:
           """The window's cookie on a request or a socket (Starlette gives both .cookies)."""
           given = connection.cookies.get(self.cookie_name, "")
           return bool(given) and hmac.compare_digest(given.encode(), self.ui_secret.encode())
   ```

6. In `start()`, the `Starlette(routes=[...])` list gets the new routes. Write the list as below, keeping the relay's
   `/cdp` route exactly as merged (its handler name may differ). The `Route("/{name}", …)` entry comes after every
   other HTTP route, because Starlette matches in order:

   ```python
           app = Starlette(routes=[Route("/", self._root), Route("/open", self._open),
                                   Route("/home", self._page), Route("/mission", self._page),
                                   Route("/settings", self._page),
                                   Route("/health", self._health), Route("/setup", self._setup),
                                   Route("/setup/status", self._setup_status),
                                   Route("/setup/reveal", self._setup_reveal, methods=["POST"]),
                                   Route("/agent-events", self._agent_events, methods=["POST"]),
                                   Route("/agent-claim", self._agent_claim, methods=["POST"]),
                                   Route("/agent-status", self._agent_status),
                                   Route("/agent-hello", self._agent_hello, methods=["POST"]),
                                   Route("/agent-bye", self._agent_bye, methods=["POST"]),
                                   Route("/{name}", self._file),
                                   WebSocketRoute("/ws", self._socket), WebSocketRoute("/cdp", self._cdp)])
   ```

   In the port loop, right after `if sock is None: continue`, add `self.port = port`. After the loop, before the
   `raise RuntimeError(...)`, add `self.port = None`.
7. Add the handlers next to `_health`:

   ```python
       async def _root(self, request: Request) -> Response:
           return RedirectResponse("/home", status_code=303)

       async def _open(self, request: Request) -> Response:
           """The window's start address: a valid code becomes the cookie, and the redirect drops the code from the
           window's address and history. A used or unknown code is a 403, unless the cookie is already there (a
           reload)."""
           if self._take_code(request.query_params.get("code", "")):
               response = RedirectResponse("/home", status_code=303)
               response.set_cookie(self.cookie_name, self.ui_secret, httponly=True, samesite="strict", path="/")
               return response
           if self._cookie_ok(request):
               return RedirectResponse("/home", status_code=303)
           return _refused_page(USED_CODE)

       async def _page(self, request: Request) -> Response:
           if not self._cookie_ok(request):
               return _refused_page(NOT_HERE)
           path = UI / PAGES[request.url.path]
           if not path.is_file():
               return Response(status_code=404)
           return HTMLResponse(path.read_text(encoding="utf-8"))

       async def _file(self, request: Request) -> Response:
           """A script, style or picture of app/ui: only names read at start, so no other path is ever served."""
           name = request.path_params["name"]
           if name not in self._files:
               return Response(status_code=404)
           if name not in OPEN_ANYWHERE and not self._cookie_ok(request):
               return _refused_page(NOT_HERE)
           return Response((UI / name).read_bytes(), media_type=FILE_TYPES[Path(name).suffix])
   ```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_app_server.py -q -p no:randomly -k "one_time_code or start_code or need_the_windows_cookie or setup or health"`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/server.py src/ai_browser/app/ui/icon.png tests/ui_socket.py tests/test_app_server.py
git commit -m "feat(server): the window's one-time code and cookie, and AI Browser's pages over http"
```

### Task 7: The setup page: Brave's steps only, no secret, no inline code

**Files:**
- Move (`git mv`): `src/ai_browser/app/setup.html` to `src/ai_browser/app/ui/setup.html`
- Create: `src/ai_browser/app/ui/setup.css`, `src/ai_browser/app/ui/setup.js`
- Modify: `src/ai_browser/app/server.py` (`SETUP_PAGE`, `setup_page`, `_setup`, `_setup_reveal`, `_setup_status`;
  `setup_key` and `_extension_folder` go)
- Modify: `tests/test_app_server.py`, `tests/test_app_run.py` (two `installed` asserts), `tests/test_portable.py`
- Test: `tests/test_app_server.py`

**Interfaces:**
- Consumes: `_cookie_ok`, `origin` and the file route (Task 6); the relay's setup-page texts.
- Produces:
  - `setup_page(watcher: str, system=None) -> str` (no extension folder, no key);
  - `POST /setup/reveal`, which needs the cookie and `Origin == server.origin`. It answers 204, 501 or 403, and
    always shows the watcher's folder;
  - `GET /setup/status`, which answers `{"watcher": bool}`, plus `"mismatch"` when one was seen;
  - `AppServer.setup_key` and `AppServer._extension_folder` no longer exist. `extension_seen` stays until Task 18.

- [ ] **Step 1: Write the failing tests**

In `tests/test_app_server.py`, replace these tests:
- `test_setup_page_and_status`;
- `test_the_setup_page_can_show_the_folder_in_finder`;
- `test_the_setup_page_covers_chromes_questions` (deleted, with no replacement: the page has no Chrome step any more);
- `test_the_setup_page_has_the_brave_steps`;
- `test_the_setup_page_shows_the_path_the_id_is_hashed_from`;
- `test_a_home_through_a_junction_keeps_the_path_chrome_sees`;
- `test_the_setup_page_shows_the_mismatch_as_text`;
- `test_the_setup_page_is_worded_for_each_computer`;
- `test_the_reveal_says_when_no_folder_window_opened`.

Replace them with:

```python
async def test_the_setup_page_holds_no_secret_and_says_the_watchers_state(fake_claude, tmp_path):
    from fake_brave import add_agent

    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        add_agent(server.agents)
        page = (await fetch("GET", url + "/setup")).text  # opens anywhere: no cookie needed
        assert "data-key" not in page and "X-AIB-Setup" not in page
        for secret in (server.token, server.session_token, server.ui_secret, server.token_for("a1")):
            assert secret not in page
        assert "brave://extensions" in page and str(tmp_path / "home" / "app" / "watcher") in page
        assert "chrome://extensions" not in page and 'id="reveal"' not in page  # AI Browser's extension is gone
        assert '<link rel="stylesheet" href="setup.css">' in page and '<script src="setup.js"></script>' in page
        assert (await fetch("GET", url + "/setup/status")).json() == {"watcher": False}
        assert (await fetch("GET", url + "/setup.js")).status_code == 200  # its own files open anywhere too
        assert (await fetch("GET", url + "/setup.css")).status_code == 200
    finally:
        await server.stop()


async def test_showing_the_folder_needs_the_window(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    shown = []
    server.reveal = lambda path: shown.append(path) or True
    try:
        assert (await fetch("POST", url + "/setup/reveal")).status_code == 403  # a page in Brave: no cookie
        other = {**ui_cookie(server), "Origin": f"http://127.0.0.1:{server.port + 1}"}
        assert (await fetch("POST", url + "/setup/reveal", headers=other)).status_code == 403
        bare = {"Origin": server.origin}
        assert (await fetch("POST", url + "/setup/reveal", headers=bare)).status_code == 403
        assert shown == []
        right = {**ui_cookie(server), "Origin": server.origin}
        assert (await fetch("POST", url + "/setup/reveal", headers=right)).status_code == 204
        assert shown == [os.path.realpath(tmp_path / "home" / "app" / "watcher")]
        server.reveal = lambda path: False  # no file manager could start
        assert (await fetch("POST", url + "/setup/reveal", headers=right)).status_code == 501
    finally:
        await server.stop()


async def test_the_setup_page_shows_the_path_the_id_is_hashed_from(fake_claude, tmp_path):
    import html

    from conftest import symlink_or_skip

    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer
    from ai_browser.extension_id import extension_id_for, extension_path

    real = tmp_path / "real"
    real.mkdir()
    symlink_or_skip(real, tmp_path / "link")
    home = tmp_path / "link" / "home"  # a home reached through a link
    server = AppServer(home, AgentManager(home))
    revealed = []
    server.reveal = lambda path: revealed.append(path) or True
    url = await server.start()
    try:
        page = (await fetch("GET", url + "/setup")).text
        await fetch("POST", url + "/setup/reveal", headers={**ui_cookie(server), "Origin": server.origin})
        shown = extension_path(home / "app" / "watcher")
        assert html.escape(shown) in page and revealed == [shown]
        assert extension_id_for(home / "app" / "watcher") == extension_id_for(shown)
        if os.name != "nt":  # on POSIX, the real path (Brave resolves the link too)
            assert shown == os.path.realpath(home / "app" / "watcher")
    finally:
        await server.stop()


@pytest.mark.windows_only
async def test_a_home_through_a_junction_keeps_the_path_brave_sees(tmp_path):
    import _winapi
    import html

    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer
    from ai_browser.extension_id import extension_path

    real = tmp_path / "real-home"
    real.mkdir()
    link = tmp_path / "home-link"
    _winapi.CreateJunction(str(real), str(link))
    folder = link / "app" / "watcher"
    folder.mkdir(parents=True)
    assert extension_path(folder) == str(folder)  # not the resolved path
    server = AppServer(link, AgentManager(link))
    assert server._watcher_folder() == str(folder)
    url = await server.start()
    try:
        assert html.escape(str(folder)) in (await fetch("GET", url + "/setup")).text
    finally:
        await server.stop()


def test_the_setup_page_sets_its_lines_as_text():
    from ai_browser.app.server import SETUP_PAGE, UI

    script = (UI / "setup.js").read_text(encoding="utf-8")
    assert SETUP_PAGE == UI / "setup.html" and 'id="mismatch"' in SETUP_PAGE.read_text(encoding="utf-8")
    assert "mismatch.textContent" in script and "innerHTML" not in script
    assert "This button works in AI Browser's own window" in script


def test_the_setup_page_is_worded_for_each_computer():
    from ai_browser.app.server import setup_page

    windows = setup_page("C:\\Users\\José & Ana\\.ai-browser\\app\\watcher", system="win32")
    assert "File Explorer" in windows and 'data-manager="File Explorer"' in windows
    assert "click the address bar at the top of the folder window, paste the path and press Enter" in windows
    assert "⌘" not in windows and "Finder" not in windows and "{{" not in windows
    assert "C:\\Users\\José &amp; Ana\\.ai-browser\\app\\watcher" in windows  # whole, accents kept, escaped
    mac = setup_page("/Users/me/.ai-browser/app/watcher", system="darwin")
    assert "Finder" in mac and "press ⌘⇧G, paste the path and press Enter" in mac and "<kbd>" not in mac
```

Every other test that calls `setup_page(` passes the watcher folder and `system=` only. For example, the relay's
switch test calls `setup_page("/x", "/w", "k", system=system)`, which becomes `setup_page("/w", system=system)`. Find
them with `grep -n "setup_page(" tests/*.py`.

In `tests/test_app_run.py`, the setup status loses `installed`:
- in `test_first_start_opens_the_setup_steps`, the assertion on `seen["status"]` becomes
  `assert seen["status"] == {"watcher": False}`;
- in `test_first_start_also_sets_up_the_watcher`, the `for _ in range(50): … if seen["status"]["installed"]: break`
  loop becomes a single `seen["status"] = (await client.get(url + "/setup/status")).json()`, and its assertion
  becomes `assert seen["status"] == {"watcher": False}`.

Task 17 rewrites the whole file anyway.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_app_server.py -q -p no:randomly -k "setup or folder or junction"`

Expected: FAIL. Today the page holds `data-key`, shows the extension's folder, has no `setup.js`, and
`setup_page` takes four arguments.

- [ ] **Step 3: Brave's steps only, with the script and style in files**

```bash
git mv src/ai_browser/app/setup.html src/ai_browser/app/ui/setup.html
```

Create `src/ai_browser/app/ui/setup.css` with the contents of the `<style>` element of `setup.html`, moved verbatim
(the lines between `<style>` and `</style>`, without the tags). Then append one rule:

```css
#copy { margin-left: 4px; }
```

Replace `src/ai_browser/app/ui/setup.html` whole with the page below. Its `#switch` section holds the relay's words
(its "Texts" section, setup page). If the merged section differs from these words, keep the merged words: the relay
owns them.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Set up AI Browser</title>
<link rel="icon" href="icon.png">
<link rel="stylesheet" href="setup.css">
</head>
<body>
<main>
  <h1>Set up AI Browser</h1>
  <p class="lead">Two one-time steps, both in Brave, your everyday browser. AI Browser's own window needs nothing.</p>
  <p id="mismatch" class="alt" hidden></p>

  <h2 id="brave">The Brain's watcher, in Brave</h2>
  <p class="lead">Once: the Brain watches the sites you pick (Gmail, Slack, Asana…) in Brave, through a small
    extension. It reads new messages and never sends anything.</p>
  <ol>
    <li>In Brave, open <strong>brave://extensions</strong> and turn on <strong>Developer mode</strong>.</li>
    <li>Drag the <strong>watcher</strong> folder onto that page.
      <div class="path"><button id="reveal-watcher" type="button" data-manager="{{FILE_MANAGER}}">Show the folder in {{FILE_MANAGER}}</button></div>
      <p class="alt">Or click <strong>Load unpacked</strong>, {{GOTO}}, then <strong>Select</strong>. The folder:</p>
      <div class="path"><code id="watcher-folder">{{WATCHER}}</code><button id="copy" type="button">Copy</button></div>
    </li>
    <li>Click the watcher's icon to open the Brain, and switch on the sites to watch.</li>
    <li>Type <strong>ai</strong> and a space in Brave's address bar to start a task from there.</li>
  </ol>
  <p id="watcher-status">Waiting for the watcher…</p>

  <h2 id="switch">Let agents use your Brave</h2>
  <p class="lead">Agents browse in Brave, your everyday browser, where you are already signed in: in background tabs of
    their own, grouped and named after their task. Brave's own remote-debugging switch lets them in. You turn it on
    yourself, and Brave asks before it lets a connection in.</p>
  <ol>
    <li>In Brave, open <strong>brave://inspect/#remote-debugging</strong>.</li>
    <li>Tick <strong>Allow remote debugging for this browser instance</strong>.</li>
    <li>When Brave asks <strong>Allow remote debugging?</strong>, click <strong>Allow</strong>. AI Browser holds one
      connection for all its agents and Claude Code sessions, so Brave asks once each time AI Browser starts, and again
      after Brave restarts.</li>
  </ol>
  <p class="warning"><strong>While this switch is on, any program on {{THIS_COMPUTER}} can reach your Brave, not only AI
    Browser.</strong> That includes the sites you are signed in to. While AI Browser is connected, a program that can
    read AI Browser's files can also use your Brave through it without a new question. AI Home lists everything
    connected, with Disconnect.</p>
  <p class="warning">Turn it off when agents aren't working: untick the same box.</p>
  <p class="warning">Only click Allow right after you started AI Browser, clicked Connect, gave an agent a task, asked
    Claude Code to browse, or opened Brave again while an agent was working. If Brave asks at any other time, it isn't
    AI Browser: click Deny, unless you just started another browser tool yourself.</p>
  <p class="warning">While AI Browser is connected, Brave shows a bar saying it is being controlled by automated test
    software. That is Brave telling you the truth; AI Browser never hides or closes it. If you close it yourself, it
    comes back only when AI Browser or Brave restarts.</p>
</main>
<script src="setup.js"></script>
</body>
</html>
```

Create `src/ai_browser/app/ui/setup.js`:

```js
// The setup page's script. The page holds no secret: it is the one page of AI Browser's that opens anywhere (the
// watcher's "Set it up" link opens it in Brave). Copy, Show the folder, and the watcher's status, all set as text.
// Show the folder works only in AI Browser's own window, whose cookie the server checks.
"use strict";

const watcherStatus = document.getElementById("watcher-status");
const mismatch = document.getElementById("mismatch");

document.getElementById("copy").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  try {
    await navigator.clipboard.writeText(document.getElementById("watcher-folder").textContent);
    button.textContent = "Copied";
  } catch {
    button.textContent = "Select and copy it";
  }
});

document.getElementById("reveal-watcher").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const manager = button.dataset.manager; // the file manager's name, from the server
  try {
    const answer = await fetch("/setup/reveal", { method: "POST" });
    button.textContent = answer.status === 204 ? `Shown in ${manager}`
      : answer.status === 403 ? "This button works in AI Browser's own window" : `Couldn't open ${manager}`;
  } catch {
    button.textContent = "Can't reach ai-browser app";
  }
});

async function check() {
  try {
    const answer = await (await fetch("/setup/status", { cache: "no-store" })).json();
    if (answer.mismatch) {
      mismatch.textContent = `A watcher connected as ${answer.mismatch}, which this app didn't expect, so it was `
        + "refused: please report this.";
      mismatch.hidden = false;
    }
    if (answer.watcher) {
      watcherStatus.textContent = "The watcher is connected: the Brain is on.";
      watcherStatus.className = "done";
      return;
    }
  } catch {
    watcherStatus.textContent = "Can't reach ai-browser app: is it still running?";
  }
  setTimeout(check, 1000);
}
check();
```

In `src/ai_browser/app/server.py`:

1. `SETUP_PAGE = Path(__file__).with_name("setup.html")` becomes `SETUP_PAGE = UI / "setup.html"`. Move that line
   below the `UI = …` line.
2. Replace `setup_page` with:

   ```python
   def setup_page(watcher: str, system: str | None = None) -> str:
       """The one-time setup page (Brave's two steps), worded for the computer it runs on; every value is escaped. It
       holds no secret: it is the one page of ours that opens anywhere."""
       values = {"{{FILE_MANAGER}}": platforms.file_manager(system),
                 "{{GOTO}}": platforms.shortcut(GOTO_MAC, GOTO_OTHER, system),
                 "{{THIS_COMPUTER}}": platforms.this_computer(system), "{{WATCHER}}": watcher}
       page = SETUP_PAGE.read_text(encoding="utf-8")
       for placeholder, value in values.items():
           page = page.replace(placeholder, html.escape(value))
       return page
   ```

3. In `__init__`, delete the `self.setup_key = …` line.
4. Delete the method `_extension_folder`.
5. Replace `_setup`, `_setup_reveal` and `_setup_status` with:

   ```python
       async def _setup(self, request: Request) -> HTMLResponse:
           return HTMLResponse(setup_page(self._watcher_folder()))

       async def _setup_reveal(self, request: Request) -> Response:
           """Show the watcher's folder: only from AI Browser's own window (its cookie and our exact Origin), so no
           other page, in Brave or anywhere, can open a folder window."""
           if not (self._cookie_ok(request) and request.headers.get("origin") == self.origin):
               return Response(status_code=403)
           shown = self.reveal(self._watcher_folder())
           return Response(status_code=204 if shown else 501)  # 501: nothing could show it (no file manager)

       async def _setup_status(self, request: Request) -> JSONResponse:
           answer = {"watcher": self.brain is not None and self.brain.store.watcher_seen}
           if self.origin_mismatch:
               answer["mismatch"] = self.origin_mismatch
           return JSONResponse(answer)
   ```

In `tests/test_portable.py::test_no_mac_words_where_windows_shows_them`, drop `SRC / "app" / "setup.html"` from
`pages`. It is in `app/ui` now.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_app_server.py tests/test_portable.py -q -p no:randomly -k "setup or folder or junction or mac_words"`

Expected: PASS.

Run: `uv run pytest tests/test_app_run.py -q -p no:randomly -k "first_start"`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A src/ai_browser/app/setup.html src/ai_browser/app/ui/setup.html src/ai_browser/app/ui/setup.css \
  src/ai_browser/app/ui/setup.js src/ai_browser/app/server.py tests/test_app_server.py tests/test_app_run.py \
  tests/test_portable.py
git commit -m "feat(setup): the setup page holds no secret, shows Brave's steps only, and runs no inline code"
```

### Task 8: A Host check and strict headers on every route (`_Guard`)

**Files:**
- Modify: `src/ai_browser/app/server.py` (`_strict_headers`, `_Guard`; `start()` wraps the app and sets the headers)
- Test: `tests/test_app_server.py`

**Interfaces:**
- Consumes: `AppServer.port`, `host` and `host_header` (Task 6).
- Produces:
  - `_strict_headers(host, port) -> list[tuple[bytes, bytes]]`;
  - `class _Guard(app, server)`, a pure ASGI wrapper around the whole Starlette app;
  - `AppServer.strict_headers`, set in `start()` once the port is bound.

  Every route, HTTP and WebSocket (including the relay's `/cdp`), now refuses any Host other than
  `127.0.0.1:<port>`.

- [ ] **Step 1: Write the failing tests**

Add to the imports of `tests/test_app_server.py`: `from websockets.exceptions import InvalidStatus` (beside
`ConnectionClosed`). Append:

```python
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src "
       "ws://127.0.0.1:{port}/ws http://127.0.0.1:{port}/setup/; base-uri 'none'; form-action 'none'; "
       "frame-ancestors 'none'")


async def test_every_route_checks_the_host(fake_claude, tmp_path):
    from fake_brave import add_agent

    server, url = await started(fake_claude, tmp_path, EVENTS)
    port = server.port
    try:
        add_agent(server.agents)
        assert (await fetch("GET", url + "/setup", headers={"Host": f"rebind.example:{port}"})).status_code == 403
        assert (await fetch("GET", url + "/health", headers={"Host": f"localhost:{port}"})).status_code == 403
        report = {"agent": "a1", "kind": "tab_opened", "target": "T", "adopted": False}
        wrong = {"X-AIB-Agent-Token": server.token_for("a1"), "Host": f"evil.example:{port}"}
        assert (await fetch("POST", url + "/agent-events", json=report, headers=wrong)).status_code == 403
        with pytest.raises(InvalidStatus) as refused:  # the WebSocket is refused before accept: an HTTP 403
            async with connect(f"ws://localhost:{port}/ws?token={server.token}", host="127.0.0.1", port=port,
                               origin=ORIGIN, proxy=None):
                pass
        assert refused.value.response.status_code == 403
        assert (await fetch("GET", url + "/health")).status_code == 200  # 127.0.0.1:<port> itself
    finally:
        await server.stop()


async def test_every_answer_carries_the_strict_headers(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        for path, headers in (("/home", ui_cookie(server)), ("/home", {}), ("/setup", {}),
                              ("/home.js", ui_cookie(server)), ("/health", {}), ("/nothing-here.js", {}),
                              ("/setup", {"Host": f"rebind.example:{server.port}"})):
            answer = await fetch("GET", url + path, headers=headers)
            assert answer.headers["content-security-policy"] == CSP.format(port=server.port), path
            assert answer.headers["x-content-type-options"] == "nosniff", path
            assert answer.headers["referrer-policy"] == "no-referrer", path
            assert answer.headers["cache-control"] == "no-store", path
            assert answer.headers["cross-origin-resource-policy"] == "same-origin", path
    finally:
        await server.stop()
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_app_server.py -q -p no:randomly -k "checks_the_host or strict_headers"`

Expected: FAIL. `/setup` with `Host: rebind.example` answers 200 today, and no answer carries a CSP.

- [ ] **Step 3: The guard**

In `src/ai_browser/app/server.py`, add above `class AppServer`:

```python
def _strict_headers(host: str, port: int) -> list[tuple[bytes, bytes]]:
    """On every HTTP answer: scripts and styles from our own files only, sockets only to /ws, fetches only to /setup/
    (so a page's script can never reach /cdp or /agent-*), no sniffing, no referrer, nothing cached."""
    origin = f"{host}:{port}"
    csp = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
           f"connect-src ws://{origin}/ws http://{origin}/setup/; base-uri 'none'; form-action 'none'; "
           "frame-ancestors 'none'")
    return [(b"content-security-policy", csp.encode()), (b"x-content-type-options", b"nosniff"),
            (b"referrer-policy", b"no-referrer"), (b"cache-control", b"no-store"),
            (b"cross-origin-resource-policy", b"same-origin")]


class _Guard:
    """The whole app, HTTP and WebSocket alike, behind one check: the Host header must be exactly 127.0.0.1:<port>,
    which blocks DNS rebinding (Starlette's TrustedHostMiddleware ignores the port, so it isn't used). Every HTTP
    answer, a refusal too, carries the strict headers."""

    def __init__(self, app, server: AppServer):
        self.app, self.server = app, server

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        strict = self.server.strict_headers
        names = {name for name, _ in strict}

        async def send_strict(message):
            if message["type"] == "http.response.start":
                kept = [(name, value) for name, value in message.get("headers", []) if name.lower() not in names]
                message = {**message, "headers": kept + strict}
            await send(message)

        host = next((value.decode("latin-1") for key, value in scope["headers"] if key == b"host"), "")
        if self.server.port is None or host != self.server.host_header:
            if scope["type"] == "websocket":
                await receive()  # websocket.connect
                await send({"type": "websocket.close", "code": 1008})  # before accept: the client reads HTTP 403
            else:
                await PlainTextResponse("refused", status_code=403)(scope, receive, send_strict)
            return
        await self.app(scope, receive, send_strict if scope["type"] == "http" else send)
```

In `AppServer.__init__`, after `self.port: int | None = None`, add
`self.strict_headers: list[tuple[bytes, bytes]] = []`.

In `start()`:
- the line `app = Starlette(routes=[…])` becomes `app = _Guard(Starlette(routes=[…]), self)`, with the same routes;
- in the port loop, right after `self.port = port`, add `self.strict_headers = _strict_headers(self.host, port)`.

Keep the relay's `ws="websockets-sansio"` in the `uvicorn.Config(...)` call as merged.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_app_server.py -q -p no:randomly`

Expected: PASS: every test of the file, because every client in it already uses `127.0.0.1:<port>`.

Run: `uv run pytest tests/test_cdprelay.py tests/test_bravelink.py tests/test_grouping.py -q -p no:randomly`

Expected: PASS. The relay's own Host refusal (its test 19) is now answered by the guard first, with the same 403.
The guard's WebSocket refusal has an empty body. If that relay test reads the body for its two Host cases, keep
only their status check, and note it in the ledger.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/server.py tests/test_app_server.py tests/test_cdprelay.py
git commit -m "feat(server): an exact Host on every route, and a strict CSP and headers on every answer"
```

### Task 9: Window sockets: cookie, Origin and Host; roles; the window count

The window's sockets are added beside today's. AI Browser's extension keeps its token path (as role "app") until
Task 18 retires it, so nothing in between breaks.

**Files:**
- Modify: `src/ai_browser/app/server.py` (`_socket`'s acceptance, `_socket_kind`, `_role`, `_unsubscribe`,
  `allow_watcher`, `window_count`, `window_seen`)
- Modify: `tests/ui_socket.py` (`ui_socket`)
- Test: `tests/test_app_server.py`

**Interfaces:**
- Consumes: watcher-safety's `_role(ws)`, and `_write`, which reads the role once, when the socket's writer starts;
  `_cookie_ok`, `origin` and `host_header` (Task 6).
- Produces:
  - `AppServer._roles: dict[WebSocket, str]`, holding `"app"` or `"watcher"` and stored when the socket is accepted.
    `_role(ws)` reads it, and a socket with no role reads as `"watcher"`, the least rights;
  - `AppServer._windows: set[WebSocket]`, `window_count` (a property, `len(_windows)`) and `window_seen` (bool);
  - `AppServer.allow_watcher(origin)`: the watcher's origin. Until Task 18, it does what
    `allow_origin(origin, watcher=True)` does;
  - `_socket_kind(ws) -> "window" | "watcher" | "extension" | None`. `"extension"` lasts until Task 18;
  - (tests) `ui_socket(server, url, cookie=True, origin="", secret=None)`: a `websockets` connect. `origin=""` means
    the page's own origin (`url`), and `None` sends no Origin.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui_socket.py`:

```python
from websockets.asyncio.client import connect


def ui_socket(server, url, cookie=True, origin="", secret=None):
    """A socket on /ws as AI Browser's window opens it: the cookie, our exact Origin (origin="" means url's own; None
    sends none), and the Host websockets takes from the address. Use it as `async with ui_socket(...) as ws`."""
    headers = {"Cookie": f"aib_ui_{server.port}={secret or server.ui_secret}"} if cookie else {}
    return connect(url.replace("http://", "ws://", 1) + "/ws", origin=url if origin == "" else origin,
                   additional_headers=headers, proxy=None)
```

Change the import line in `tests/test_app_server.py` to `from ui_socket import ui_cookie, ui_socket`. Append:

```python
async def refused_socket(opening) -> int:
    """The close code of a socket the server refuses (after accept, so the page can read it)."""
    async with opening as ws:
        with pytest.raises(ConnectionClosed) as closed:
            await recv(ws)
    return closed.value.rcvd.code


async def test_only_the_windows_cookie_origin_and_host_open_a_window_socket(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        async with ui_socket(server, url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "home"}))
            assert (await recv(ws))["type"] == "snapshot"
        other = f"http://127.0.0.1:{server.port + 1}"
        for opening in (ui_socket(server, url, cookie=False), ui_socket(server, url, secret="an-old-secret"),
                        ui_socket(server, url, origin=other), ui_socket(server, url, origin=None),
                        connect(socket_url(server, url), origin=url, proxy=None)):  # the token, from an http page
            assert await refused_socket(opening) == 4403
        server.allow_watcher(WATCHER)
        async with connect(socket_url(server, url), origin=WATCHER, proxy=None) as ws:  # the watcher's path stays
            await ws.send(json.dumps({"type": "hello", "view": "brain"}))
            assert (await recv(ws))["type"] == "snapshot"
        assert await refused_socket(connect(socket_url(server, url), origin="https://evil.example", proxy=None)) == 4403
    finally:
        await server.stop()


async def test_the_window_count_follows_the_window_sockets(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        assert (server.window_count, server.window_seen) == (0, False)
        async with ui_socket(server, url) as one, ui_socket(server, url) as two:
            for ws in (one, two):
                await ws.send(json.dumps({"type": "hello", "view": "home"}))
                await recv(ws)
            assert server.window_count == 2 and server.window_seen
            server.allow_watcher(WATCHER)
            async with connect(socket_url(server, url), origin=WATCHER, proxy=None) as watcher:
                await watcher.send(json.dumps({"type": "hello", "view": "brain"}))
                await recv(watcher)
                assert server.window_count == 2  # the watcher is no window of ours
        for _ in range(50):
            if server.window_count == 0:
                break
            await asyncio.sleep(0.05)
        assert server.window_count == 0 and server.window_seen
    finally:
        await server.stop()


async def test_a_window_socket_has_the_app_role(fake_claude, tmp_path):
    from fake_brave import FakeBrave, add_agent

    server, url = await started(fake_claude, tmp_path, EVENTS)
    brave = FakeBrave([{"target": "U1", "url": "https://mail.example/", "title": "Mail"}])
    server.attach_brave(brave)
    agent = add_agent(server.agents)
    server.allow_watcher(WATCHER)
    try:
        async with connect(socket_url(server, url), origin=WATCHER, proxy=None) as watcher:
            await watcher.send(json.dumps({"type": "hello", "view": "brain"}))
            await recv(watcher)
            await watcher.send(json.dumps({"type": "hand_tab", "id": agent.id, "target": "U1"}))
            await watcher.send(json.dumps({"type": "brain_ask", "talk": "t1", "request": "r", "text": "hi"}))
            await asyncio.sleep(0.5)
            assert agent.adopted == []  # refused for the watcher, with no answer
        async with ui_socket(server, url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "home"}))
            await recv(ws)
            assert set(server._roles.values()) == {"app"}
            await ws.send(json.dumps({"type": "brain_ask", "talk": "t1", "request": "r", "text": "hi"}))
            answer = (await until(ws, lambda message: message["type"] == "brain_answer"))[-1]
            assert answer["error"] == "The Brain isn't running"  # it reached the talk: a window may ask
            await ws.send(json.dumps({"type": "hand_tab", "id": agent.id, "target": "U1"}))
            for _ in range(50):
                if agent.adopted:
                    break
                await asyncio.sleep(0.05)
            assert agent.adopted == ["U1"]
    finally:
        await server.stop()
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_app_server.py -q -p no:randomly -k "window_socket or window_count or app_role"`

Expected: FAIL. `ui_socket` is refused with 4403 (no token), and `allow_watcher` and `window_count` don't exist.

- [ ] **Step 3: Window sockets beside the watcher's**

In `src/ai_browser/app/server.py`, `AppServer.__init__`, after `self._origin_of: dict[WebSocket, str] = {}`, add:

```python
        self._roles: dict[WebSocket, str] = {}  # "app" or "watcher", stored when a socket is accepted
        self._windows: set[WebSocket] = set()  # AI Browser's window's sockets: AI Home, Mission Control, Settings
        self.window_seen = False  # the window's first socket has come in
```

Add, next to `allow_origin`:

```python
    def allow_watcher(self, origin: str) -> None:
        """Brave's watcher's origin (chrome-extension://<id>): it connects with the token from there, as role
        "watcher"."""
        self.allow_origin(origin, watcher=True)

    @property
    def window_count(self) -> int:
        return len(self._windows)  # a set: never below 0, never a socket twice

    def _socket_kind(self, ws: WebSocket) -> str | None:
        """Who opens this socket: AI Browser's window (its cookie, our exact Origin and Host), Brave's watcher (the
        token and a watcher origin), or, until AI Browser's own extension retires, that extension (the token and its
        origin). None: refused."""
        origin = ws.headers.get("origin")
        if origin == self.origin and ws.headers.get("host") == self.host_header and self._cookie_ok(ws):
            return "window"
        if not hmac.compare_digest(ws.query_params.get("token", "").encode(), self.token.encode()):
            return None
        if origin in self._watcher_origins:
            return "watcher"
        if origin in self._origins:
            return "extension"
        # Only once the app has allowed its computed IDs: during start-up the extension can connect before allow_*
        # runs, and that is no mismatch.
        if self._origins and isinstance(origin, str) and origin.startswith("chrome-extension://"):
            self._mismatch(origin)
        return None
```

In `_socket`, replace everything between `await ws.accept()` and `queue: asyncio.Queue = asyncio.Queue()` with the
lines below. Today that is the token and origin check, the `extension_seen` line and `self._origin_of[ws] = origin`;
watcher-safety may have reworded them, so replace whatever is there:

```python
        kind = self._socket_kind(ws)
        if kind is None:
            await ws.close(code=REFUSED)
            return
        self._roles[ws] = "watcher" if kind == "watcher" else "app"
        self._origin_of[ws] = ws.headers.get("origin", "")
        if kind == "window":
            self._windows.add(ws)
            self.window_seen = True
        elif kind == "extension":
            self.extension_seen = True  # AI Browser's own extension, until it retires
```

Replace the body of watcher-safety's `_role(self, ws)` with:

```python
        return self._roles.get(ws, "watcher")  # a socket with no role gets the least rights
```

In `_unsubscribe(self, ws)`, after `self._origin_of.pop(ws, None)`, add:

```python
        self._roles.pop(ws, None)
        self._windows.discard(ws)
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_app_server.py tests/test_watcher_rules.py -q -p no:randomly`

Expected: PASS. Watcher-safety's table tests are unchanged: the roles are the same two.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/server.py tests/ui_socket.py tests/test_app_server.py
git commit -m "feat(server): window sockets need the cookie, our exact Origin and Host; roles stored at accept"
```

### Task 10: Settings on the server; the remembered port

**Files:**
- Modify: `src/ai_browser/app/server.py` (`__init__` gains `settings`, `port_file`, `window_info`; `settings_set`; the
  `settings` message and `snapshot.settings`; `MESSAGE_RULES`; the port loop in `start()`)
- Modify: `tests/test_watcher_rules.py` (`SENDS` gains `settings_set`; `NEVER` gains `settings`)
- Test: `tests/test_app_server.py`

**Interfaces:**
- Consumes:
  - `Settings(home)` with `get()` and `set(key, value)` (Task 2);
  - watcher-safety's `Rule`, `MESSAGE_RULES` and `for_watcher`, which drops anything not in `WATCHER_RECEIVES`;
  - `syncdir.write_atomic`.
- Produces:
  - `AppServer(…, settings: Settings | None = None, port_file: Path | None = None)`, with `self.settings` and
    `self.port_file`;
  - `AppServer.window_info: dict`, which defaults to `{"using": None, "name": "", "note": "", "choices": []}`.
    `run_app` sets it (Task 17);
  - `AppServer._settings_payload() -> dict`: `{"model", "voice", "window_browser", "window"}`;
  - the message `settings {**payload}`, sent to every socket after a change (the filter keeps it from the watcher);
    the snapshot's `settings` holds the same payload;
  - `settings_set {"key", "value", "request"?}`. Only `MESSAGE_RULES["settings_set"] = Rule(app=True,
    watcher=False)` lets it through. A bad value gets `error {"text", "request"}`, and a write that fails gets
    `error {"text": "Couldn't save that setting: …"}`;
  - `SETTING_KEYS = ("model", "voice", "window_browser")`;
  - `_saved_port()` and `_remember_port(saved, port)`: `start()` tries the saved port first, then `APP_PORTS`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app_server.py`:

```python
async def test_settings_are_saved_by_the_app_and_reach_every_window(fake_claude, tmp_path):
    from ai_browser.settings import read_settings

    server, url = await started(fake_claude, tmp_path, EVENTS)
    server.window_info = {"using": "chrome", "name": "Google Chrome", "note": "",
                          "choices": [{"id": "auto", "name": "Auto (Google Chrome)", "installed": True}]}
    server.allow_watcher(WATCHER)
    try:
        async with ui_socket(server, url) as one, ui_socket(server, url) as two, \
                connect(socket_url(server, url), origin=WATCHER, proxy=None) as watcher:
            for ws, view in ((one, "home"), (two, "mission"), (watcher, "brain")):
                await ws.send(json.dumps({"type": "hello", "view": view}))
            snapshot = await recv(one)
            assert snapshot["settings"] == {"model": None, "voice": False, "window_browser": "auto",
                                            "window": server.window_info}
            await recv(two)
            assert "settings" not in await recv(watcher)  # the watcher's snapshot is trimmed to its agents
            await one.send(json.dumps({"type": "settings_set", "key": "model", "value": "opus", "request": "s1"}))
            for ws in (one, two):
                seen = (await until(ws, lambda message: message["type"] == "settings"))[-1]
                assert seen["model"] == "opus" and seen["window"]["name"] == "Google Chrome"
            assert read_settings(tmp_path / "home")["model"] == "opus"
            await watcher.send(json.dumps({"type": "settings_set", "key": "model", "value": "haiku"}))
            await one.send(json.dumps({"type": "settings_set", "key": "voice", "value": "loud", "request": "s2"}))
            error = (await until(one, lambda message: message["type"] == "error"))[-1]
            assert error == {"type": "error", "text": "Voice is on or off", "request": "s2"}
            await one.send(json.dumps({"type": "settings_set", "key": "colour", "value": "red", "request": "s3"}))
            assert (await until(one, lambda message: message["type"] == "error"))[-1]["request"] == "s3"
            await asyncio.sleep(0.3)
            assert read_settings(tmp_path / "home") == {"model": "opus"}  # the watcher's and the bad ones changed nothing
            with pytest.raises(TimeoutError):
                while True:  # the watcher never gets a settings message
                    if json.loads(await asyncio.wait_for(watcher.recv(), 0.5))["type"] == "settings":
                        raise AssertionError("the watcher got settings")
    finally:
        await server.stop()


async def test_a_setting_that_cant_be_saved_is_said_and_changes_nothing(fake_claude, tmp_path):  # Review Focus 3
    server, url = await started(fake_claude, tmp_path, EVENTS)
    (tmp_path / "home" / "settings.json").mkdir(parents=True)  # a folder where the file should be
    try:
        async with ui_socket(server, url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "home"}))
            await recv(ws)
            await ws.send(json.dumps({"type": "settings_set", "key": "model", "value": "opus", "request": "s1"}))
            error = (await until(ws, lambda message: message["type"] == "error"))[-1]
            assert error["text"].startswith("Couldn't save that setting: ") and error["request"] == "s1"
            await ws.send(json.dumps({"type": "events", "id": "a9"}))  # the socket is still open and answering
            assert (await until(ws, lambda message: message["type"] == "agent_events"))[-1]["events"] == []
        assert server.settings.get()["model"] is None
    finally:
        await server.stop()


def free_run(count=3):
    """`count` consecutive free ports, well away from the running app's 8792-8811."""
    from ai_browser.live import _bind

    for start in range(18700, 18900, count):
        sockets = [_bind("127.0.0.1", port) for port in range(start, start + count)]
        for sock in sockets:
            if sock is not None:
                sock.close()
        if all(sockets):
            return range(start, start + count)
    pytest.skip("no free ports")


async def test_the_port_is_remembered_so_the_microphone_grant_survives(fake_claude, tmp_path):
    import socket as sockets

    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer

    runner, _, _ = fake_claude
    home, ports = tmp_path / "home", free_run()
    port_file = home / "app" / "port"
    port_file.parent.mkdir(parents=True)
    port_file.write_text(f"{ports[1]}\n", encoding="utf-8")  # a free port in range: it is used
    server = AppServer(home, AgentManager(home, claude=runner), ports=ports, port_file=port_file)
    assert await server.start() == f"http://127.0.0.1:{ports[1]}"
    await server.stop()
    holder = sockets.socket()
    holder.bind(("127.0.0.1", ports[1]))
    holder.listen()  # another program has it now
    lines = []
    server = AppServer(home, AgentManager(home, claude=runner), ports=ports, port_file=port_file)
    server.out = lines.append
    try:
        url = await server.start()
        assert url != f"http://127.0.0.1:{ports[1]}" and port_file.read_text(encoding="utf-8") == f"{ports[1]}\n"
        assert lines == [f"Port {ports[1]} is busy: AI Browser uses {server.port} this time, and may ask for the "
                         "microphone again."]
    finally:
        await server.stop()
        holder.close()
    for wrong in ("80\n", "not a port\n"):  # outside the range, or unreadable: rewritten with the port used
        port_file.write_text(wrong, encoding="utf-8")
        server = AppServer(home, AgentManager(home, claude=runner), ports=ports, port_file=port_file)
        await server.start()
        assert port_file.read_text(encoding="utf-8") == f"{server.port}\n"
        await server.stop()
    port_file.unlink()
    server = AppServer(home, AgentManager(home, claude=runner), ports=ports, port_file=port_file)
    await server.start()  # missing: written
    assert port_file.read_text(encoding="utf-8") == f"{server.port}\n"
    await server.stop()
```

In `tests/test_watcher_rules.py` (watcher-safety's two table tests):
- add `"settings_set": (True, False),  # app-window: the model, Voice and the window's browser` to the copy
  `SENDS`;
- in `test_the_message_table_has_exactly_the_written_down_types`, `len(SENDS)` and the app count each grow by
  one: after brain-delegation's two rows, 57 becomes 58 and 50 becomes 51. If the merged numbers differ, add one
  to what is there;
- add `"settings"` to `NEVER`: the settings message never reaches a watcher socket.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_app_server.py tests/test_watcher_rules.py -q -p no:randomly -k "settings or port or message_table"`

Expected: FAIL. `AppServer` takes no `port_file`, the snapshot has no `settings`, and the table test's copy names a
type `MESSAGE_RULES` lacks.

- [ ] **Step 3: Settings and the port, on the server**

In `src/ai_browser/app/server.py`:

1. Imports: add `from ..settings import Settings` and `from ..syncdir import write_atomic`.
2. Under `CODE_TTL = …`, add `SETTING_KEYS = ("model", "voice", "window_browser")`.
3. In `MESSAGE_RULES`, add the row:

   ```python
       "settings_set": Rule(app=True, watcher=False),  # the window's Settings, AI Home's and Mission Control's picks
   ```

4. In `AppServer.__init__`'s signature, add two last keywords: `settings: Settings | None = None` and
   `port_file: Path | None = None`. In its body, add:

   ```python
           self.settings = settings if settings is not None else Settings(self.home)  # <home>/settings.json
           self.port_file = Path(port_file) if port_file is not None else None  # run_app: <home>/app/port
           self.window_info: dict = {"using": None, "name": "", "note": "", "choices": []}  # run_app sets it once
   ```

5. Add the methods:

   ```python
       def _settings_payload(self) -> dict:
           return {**self.settings.get(), "window": dict(self.window_info)}

       def _settings_set(self, queue: asyncio.Queue, message: dict) -> None:
           request = message.get("request") if isinstance(message.get("request"), (str, int)) else None
           key = message.get("key")
           if key not in SETTING_KEYS:
               queue.put_nowait({"type": "error", "text": "There is no such setting", "request": request})
               return
           try:
               self.settings.set(key, message.get("value"))
           except ValueError as exc:
               queue.put_nowait({"type": "error", "text": str(exc), "request": request})
               return
           except OSError as exc:  # a read-only home, a full disk: nothing changed
               queue.put_nowait({"type": "error", "text": f"Couldn't save that setting: {exc.strerror or exc}",
                                 "request": request})
               return
           self._send_all({"type": "settings", **self._settings_payload()})  # the watcher's filter keeps it out

       def _saved_port(self) -> int | None:
           """The port this home used before (the microphone grant belongs to that address), if it is one of ours."""
           if self.port_file is None:
               return None
           try:
               port = int(self.port_file.read_text(encoding="utf-8").strip())
           except (OSError, ValueError):
               return None
           return port if port in self.ports else None

       def _remember_port(self, saved: int | None, port: int) -> None:
           if self.port_file is None:
               return
           if saved is None:  # missing, unreadable, or not one of ours: this port from now on
               with contextlib.suppress(OSError):
                   write_atomic(self.port_file, f"{port}\n".encode("utf-8"))
           elif saved != port:  # busy this once: the file stays, so the next start goes back to the granted address
               self.out(f"Port {saved} is busy: AI Browser uses {port} this time, and may ask for the microphone "
                        "again.")
   ```

6. In `_handle`, add a branch right before `elif kind == "new_task":`:

   ```python
           elif kind == "settings_set":
               self._settings_set(queue, message)
   ```

7. In `_snapshot()`, add `"settings": self._settings_payload(),` to the dict.
8. In `start()`, the port loop now begins with the saved port. Replace `for port in self.ports:` with:

   ```python
           saved = self._saved_port()
           for port in ([saved] if saved is not None else []) + [port for port in self.ports if port != saved]:
   ```

   Right after `self.url = f"http://{self.host}:{port}"`, add `self._remember_port(saved, port)`.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_app_server.py tests/test_watcher_rules.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/server.py tests/test_app_server.py tests/test_watcher_rules.py
git commit -m "feat(server): the model, Voice and the window's browser are the app's settings; the port is remembered"
```

### Task 11: Websites open in the user's browser (`platforms.open_url`, the `open_url` message)

**Files:**
- Modify: `src/ai_browser/platforms.py` (`open_url_command`, `open_url`)
- Modify: `src/ai_browser/app/server.py` (`_web_address`, `open_url`, `MESSAGE_RULES`, `_agents_browser`)
- Modify: `tests/test_watcher_rules.py` (`SENDS` gains `open_url`)
- Test: `tests/test_platforms.py`, `tests/test_app_server.py`

**Interfaces:**
- Consumes: browser-detection's `Installed` (`.bundle`, `.binary`, `.id`), `browsers.installed()`,
  `browsers.for_data_dir(folder)`, and `chrome.own_browser_dir()`.
- Produces:
  - `platforms.open_url_command(url, browser=None, system=None) -> list[str] | None`, which is pure:
    - macOS: `["open", "-a", <bundle>, url]`, or `["open", url]`;
    - Windows: `[<binary>, url]`, or None, which means `os.startfile`;
    - Linux: `["xdg-open", url]`, or None;
  - `platforms.open_url(url, browser=None, system=None) -> bool`: True when a program started;
  - `server._web_address(value) -> str | None`;
  - `MESSAGE_RULES["open_url"] = Rule(app=True, watcher=False)`;
  - the message `open_url {"url"}`. A refused address gets `error {"text": "Only web addresses open from here"}`, and
    a `False` from `platforms.open_url` gets `error {"text": "Couldn't open that address in your browser"}`.

  Wave C swaps `_agents_browser()` for the saved place's row.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_platforms.py`:

```python
def test_open_url_commands_for_each_system(monkeypatch):
    from types import SimpleNamespace

    url = "https://example.com/a?b=1"
    brave = SimpleNamespace(bundle=Path("/x/Brave Browser.app"), binary=Path("C:/Brave/brave.exe"))
    assert platforms.open_url_command(url, brave, "darwin") == ["open", "-a", str(Path("/x/Brave Browser.app")), url]
    assert platforms.open_url_command(url, None, "darwin") == ["open", url]
    assert platforms.open_url_command(url, brave, "win32") == [str(Path("C:/Brave/brave.exe")), url]
    assert platforms.open_url_command(url, None, "win32") is None  # os.startfile: the default browser
    monkeypatch.setattr(platforms.shutil, "which", lambda name: "/usr/bin/xdg-open" if name == "xdg-open" else None)
    assert platforms.open_url_command(url, brave, "linux") == ["xdg-open", url]
    monkeypatch.setattr(platforms.shutil, "which", lambda name: None)
    assert platforms.open_url_command(url, None, "linux") is None


def test_open_url_says_whether_a_program_started(monkeypatch):
    started = []
    monkeypatch.setattr(platforms.subprocess, "Popen", lambda command, **options: started.append(command) or object())
    assert platforms.open_url("https://example.com", system="darwin") is True
    assert started == [["open", "https://example.com"]]

    def cannot(command, **options):
        raise OSError("no such program")

    monkeypatch.setattr(platforms.subprocess, "Popen", cannot)
    assert platforms.open_url("https://example.com", system="darwin") is False
    monkeypatch.setattr(platforms.shutil, "which", lambda name: None)
    assert platforms.open_url("https://example.com", system="linux") is False  # nothing could open it
```

Append to `tests/test_app_server.py`:

```python
async def test_websites_open_in_the_users_browser(fake_claude, tmp_path, monkeypatch):
    from ai_browser import platforms

    opened, answer = [], [True]
    monkeypatch.setattr(platforms, "open_url", lambda url, browser=None, system=None: opened.append(url) or answer[0])
    server, url = await started(fake_claude, tmp_path, EVENTS)
    server.allow_watcher(WATCHER)
    try:
        async with ui_socket(server, url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "home"}))
            await recv(ws)
            await ws.send(json.dumps({"type": "open_url", "url": "https://example.com/pricing?a=1"}))
            for _ in range(50):
                if opened:
                    break
                await asyncio.sleep(0.05)
            assert opened == ["https://example.com/pricing?a=1"]
            for bad in ("javascript:alert(1)", "file:///etc/hosts", "https://u:p@example.com", "http:///x",
                        "https://example.com/a b", "https://example.com/\nx", "https://" + "a" * 3000 + ".com",
                        "HTTPS://example.com", "--app=https://example.com", 42, None):
                await ws.send(json.dumps({"type": "open_url", "url": bad}))
                error = (await until(ws, lambda message: message["type"] == "error"))[-1]
                assert error["text"] == "Only web addresses open from here", bad
            answer[0] = False  # nothing on this computer could open it
            await ws.send(json.dumps({"type": "open_url", "url": "https://example.com"}))
            error = (await until(ws, lambda message: message["type"] == "error"))[-1]
            assert error["text"] == "Couldn't open that address in your browser"
        async with connect(socket_url(server, url), origin=WATCHER, proxy=None) as watcher:
            await watcher.send(json.dumps({"type": "hello", "view": "brain"}))
            await recv(watcher)
            await watcher.send(json.dumps({"type": "open_url", "url": "https://example.com/from-the-watcher"}))
            await asyncio.sleep(0.5)
        assert opened == ["https://example.com/pricing?a=1", "https://example.com"]  # never from the watcher
    finally:
        await server.stop()
```

In `tests/test_watcher_rules.py`, add `"open_url": (True, False),  # app-window: a website link in our pages` to
`SENDS`. In `test_the_message_table_has_exactly_the_written_down_types`, `len(SENDS)` becomes 59 and the app count
52 (one more each than Task 10 left).

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_platforms.py tests/test_app_server.py tests/test_watcher_rules.py -q -p no:randomly -k "open_url or message_table"`

Expected: FAIL with `AttributeError: module 'ai_browser.platforms' has no attribute 'open_url_command'`. The server
drops `open_url`, which no table row allows.

- [ ] **Step 3: Open a website the way a link in Mail does**

In `src/ai_browser/platforms.py`, after `reveal`, add:

```python
def open_url_command(url: str, browser=None, system: str | None = None) -> list[str] | None:
    """The command that opens a web address in the user's browser: `browser` (a browsers.Installed row) when it is
    known, else the system's default. None: no command (on Windows, os.startfile does it). The address always starts
    with http:// or https://, so no program reads it as a switch."""
    system = _system(system)
    if system == "darwin":
        bundle = getattr(browser, "bundle", None)
        return ["open", "-a", str(bundle), url] if bundle else ["open", url]
    if system == "win32":
        binary = getattr(browser, "binary", None)
        return [str(binary), url] if binary else None
    return ["xdg-open", url] if shutil.which("xdg-open") else None


def open_url(url: str, browser=None, system: str | None = None) -> bool:
    """Open a web address in the user's browser, as a link clicked in Mail would: in the profile they used last, with
    no Allow question. True when something started."""
    command = open_url_command(url, browser, system)
    if command is None:
        start = getattr(os, "startfile", None)  # Windows only
        if _system(system) != "win32" or start is None:
            return False
        try:
            start(url)
        except OSError:
            return False
        return True
    try:
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    return True
```

In `src/ai_browser/app/server.py`:

1. Imports: add `from urllib.parse import urlsplit`, `from .. import browsers` (beside `from .. import platforms`, as
   `from .. import browsers, platforms`) and `from ..chrome import own_browser_dir`.
2. Under `SETTING_KEYS`, add `URL_LIMIT = 2000`, and above `class AppServer`:

   ```python
   def _web_address(value) -> str | None:
       """A link's address, if the user's browser may open it: http or https with a host, no user name or password, no
       whitespace or control character, at most URL_LIMIT characters."""
       if not isinstance(value, str) or not value.startswith(("http://", "https://")) or len(value) > URL_LIMIT:
           return None
       if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value):
           return None
       try:
           parts = urlsplit(value)
           parts.port  # noqa: B018  (a bad port raises here)
       except ValueError:
           return None
       if not parts.hostname or parts.username is not None or parts.password is not None:
           return None
       return value
   ```

3. In `MESSAGE_RULES`, add `"open_url": Rule(app=True, watcher=False),  # a website link in one of our pages`.
4. Add the methods:

   ```python
       def _agents_browser(self):
           """The agents' browser, as an installed row (it opens a website the user clicked), or None for the system's
           default. Wave C uses the saved place instead."""
           facts = browsers.for_data_dir(own_browser_dir())
           if facts is None:
               return None
           return next((row for row in browsers.installed() if row.id == facts.id), None)

       async def _open_url(self, queue: asyncio.Queue, message: dict) -> None:
           url = _web_address(message.get("url"))
           if url is None:
               queue.put_nowait({"type": "error", "text": "Only web addresses open from here"})
               return
           browser = await asyncio.to_thread(self._agents_browser)
           if not await asyncio.to_thread(platforms.open_url, url, browser):
               queue.put_nowait({"type": "error", "text": "Couldn't open that address in your browser"})
   ```

5. In `_handle`, before `elif kind == "new_task":`, add:

   ```python
           elif kind == "open_url":
               self._job(self._open_url(queue, message))
   ```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_platforms.py tests/test_app_server.py tests/test_watcher_rules.py tests/test_portable.py -q -p no:randomly`

Expected: PASS. `test_no_macos_paths_outside_platforms` still passes: `"open", "-a"` is in `platforms.py` only.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/platforms.py src/ai_browser/app/server.py tests/test_platforms.py tests/test_app_server.py \
  tests/test_watcher_rules.py
git commit -m "feat(server): a website link in AI Browser's window opens in the user's browser, never in the window"
```

### Task 12: The `ai` keyword moves to the watcher

**Files:**
- Modify: `src/ai_browser/app/server.py` (`ai_keyword`, `_keyword_workflow`, `keyword_started`, `MESSAGE_RULES`,
  `WATCHER_RECEIVES`)
- Modify: `src/ai_browser/app/watcher/manifest.json`, `src/ai_browser/app/watcher/worker.js`
- Modify: `tests/test_watcher_rules.py` (`SENDS` and `RECEIVES`), `tests/test_workflows.py` (its address-bar test
  goes)
- Test: `tests/test_app_server.py`, `tests/test_watcher.py`

**Interfaces:**
- Consumes:
  - brain-delegation's `Agent.number`;
  - `WorkflowRunner.run(slug, text=None) -> agent id`, `WorkflowStore.all()` (each workflow's `.name` and `.slug`)
    and `AgentManager.create(text, skills, model)`;
  - `Settings.get()["model"]` (Task 10).
- Produces:
  - `MESSAGE_RULES["ai_keyword"] = Rule(app=False, watcher=True)`;
  - `"keyword_started"` in `WATCHER_RECEIVES`;
  - `KEYWORD_LIMIT = 2000`;
  - `AppServer._keyword_workflow(text) -> tuple[str, str] | None`, giving `(slug, the rest of the text)`;
  - the message `ai_keyword {"text", "request"}`, answered with `keyword_started {"request", "id", "number", "name"}`
    or `error {"request", "text"}`. Any `adopt` or `tab` on it is ignored;
  - the watcher's `globalThis.startKeywordTask(text) -> bool`, its omnibox `ai`, and its notifications. Each
    notification keeps a note `{keyword: {message}}` in `chrome.storage.session`'s `notes`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app_server.py`:

```python
async def watcher_hello(server, url):
    """Brave's watcher on the app's socket (its token and origin), after its hello."""
    server.allow_watcher(WATCHER)
    ws = await connect(socket_url(server, url), origin=WATCHER, proxy=None)
    await ws.send(json.dumps({"type": "hello", "view": "watcher"}))
    return ws


async def keyword_server(fake_claude, tmp_path, names):
    """(server, agents, slugs, ran): a server with workflows `names`, whose runner records (slug, text) and makes an
    agent with no process behind it (ids from a9 down, so they never meet AgentManager's own a1, a2…)."""
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer
    from ai_browser.brain.workflows import WorkflowRunner, WorkflowStore

    runner_bin, _, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    home = tmp_path / "home"
    agents = AgentManager(home, claude=runner_bin)
    store = WorkflowStore(home)
    for name in names:
        store.save({"name": name, "instructions": f"Run {name}", "trigger": "manual"})
    slugs = {workflow.name: workflow.slug for workflow in store.all()}
    runner = WorkflowRunner(store, agents)
    ran = []

    async def run(slug, text=None, page=None):
        ran.append((slug, text))
        return add_agent(agents, f"a{10 - len(ran)}", name=f"Run {slug}").id

    runner.run = run
    server = AppServer(home, agents, workflows=store, runner=runner)
    await server.start()
    return server, agents, slugs, ran


async def test_the_keyword_starts_an_agent_from_the_watcher_only(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    server.settings.set("model", "opus")
    try:
        ws = await watcher_hello(server, url)
        await ws.send(json.dumps({"type": "ai_keyword", "text": "  check the shop  ", "request": "k1",
                                  "adopt": "U1", "tab": {"url": "https://mail.example/", "title": "Mail"}}))
        answer = (await until(ws, lambda message: message["type"] == "keyword_started"))[-1]
        assert answer == {"type": "keyword_started", "request": "k1", "id": "a1", "number": 1,
                          "name": "check the shop"}
        agent = server.agents.agents["a1"]
        assert agent.model == "opus" and agent.adopted == [] and agent.working_tab is None  # typing hands no tab
        await ws.send(json.dumps({"type": "ai_keyword", "text": "   ", "request": "k2"}))
        await asyncio.sleep(0.3)
        assert list(server.agents.agents) == ["a1"]  # an empty text does nothing
        await ws.close()
        async with ui_socket(server, url) as page:  # AI Home never sends it: its own Start does that
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            await recv(page)
            await page.send(json.dumps({"type": "ai_keyword", "text": "from a page", "request": "k3"}))
            await asyncio.sleep(0.3)
        assert list(server.agents.agents) == ["a1"]
    finally:
        await server.stop()


async def test_the_keyword_runs_a_workflow_by_its_name(fake_claude, tmp_path):
    server, agents, slugs, ran = await keyword_server(fake_claude, tmp_path, ("qa", "qa site"))
    try:
        assert server._keyword_workflow("qa site example.com") == (slugs["qa site"], "example.com")  # longest wins
        assert server._keyword_workflow("QA SITE") == (slugs["qa site"], "")
        assert server._keyword_workflow("qasite") is None and server._keyword_workflow("check qa") is None
        ws = await watcher_hello(server, server.url)
        await ws.send(json.dumps({"type": "ai_keyword", "text": "qa site example.com", "request": "k1"}))
        answer = (await until(ws, lambda message: message["type"] == "keyword_started"))[-1]
        assert ran == [(slugs["qa site"], "example.com")]
        assert (answer["id"], answer["number"], answer["name"]) == ("a9", 9, "Run " + slugs["qa site"])
        await ws.send(json.dumps({"type": "ai_keyword", "text": "qa", "request": "k2"}))
        await until(ws, lambda message: message["type"] == "keyword_started")
        assert ran[1] == (slugs["qa"], None)  # nothing after the name: the workflow alone
        await ws.close()
    finally:
        await server.stop()


async def test_the_keyword_ignores_case_spaces_and_trims_long_text(fake_claude, tmp_path):  # Review Focus 4
    server, agents, slugs, ran = await keyword_server(fake_claude, tmp_path, ("qa site",))
    try:
        ws = await watcher_hello(server, server.url)
        await ws.send(json.dumps({"type": "ai_keyword", "text": "QA Site   example.com ", "request": "k1"}))
        await until(ws, lambda message: message["type"] == "keyword_started")
        assert ran == [(slugs["qa site"], "example.com")]
        await ws.send(json.dumps({"type": "ai_keyword", "text": "x" * 3000, "request": "k2"}))
        answer = (await until(ws, lambda message: message["type"] == "keyword_started"))[-1]
        agent = agents.agents[answer["id"]]
        for _ in range(100):  # the agent's turn starts with the user's words
            if any(event.get("type") == "user" for event in agent.events):
                break
            await asyncio.sleep(0.05)
        assert [event["text"] for event in agent.events if event.get("type") == "user"] == ["x" * 2000]
        assert len(ran) == 1  # one agent, no workflow
        await ws.close()
    finally:
        await server.stop()
```

Append to `tests/test_watcher.py`:

```python
def test_the_watcher_has_the_ai_keyword():
    from ai_browser.brain.watcher import WATCHER_SOURCE

    manifest = json.loads((WATCHER_SOURCE / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["omnibox"] == {"keyword": "ai"} and manifest["version"] == "0.2.0"
    assert "debugger" not in manifest["permissions"] and "incognito" not in manifest


NOTES = ("chrome.storage.session.get('notes').then(({notes = {}}) => Object.values(notes)"
         ".filter((note) => note.keyword).map((note) => note.keyword.message))")


@CHROME
async def test_the_keyword_starts_an_agent_and_says_so(watcher):
    await watcher.worker_js("startKeywordTask('check the shop')")
    assert await watcher.until(lambda: [agent.name for agent in watcher.server.agents.agents.values()]
                               == ["check the shop"])
    assert await until(watcher.worker_js, f"{NOTES}.then((messages) => messages.some((message) => "
                                          "message.startsWith('Started 1 · check the shop')))")
    assert await watcher.worker_js("chrome.notifications.getAll().then((all) => Object.keys(all).length)") >= 1


@CHROME
async def test_with_the_app_stopped_the_keyword_says_so_and_sends_nothing(watcher):
    await watcher.server.stop()
    assert await until(watcher.worker_js, "chrome.action.getBadgeText({}).then((text) => text === 'off')", 15)
    assert await watcher.worker_js("startKeywordTask('check the shop')") is False
    assert await until(watcher.worker_js, f"{NOTES}.then((messages) => messages.includes("
                                          "\"AI Browser isn't running: start it with `uv run ai-browser app`\"))")
    assert watcher.server.agents.agents == {}
```

In `tests/test_workflows.py`, delete `test_ai_and_a_workflow_name_in_the_address_bar`. The server's
`_keyword_workflow` tests above replace it, and AI Browser's own worker, which it drove, retires.

In `tests/test_watcher_rules.py`:
- add `"ai_keyword": (False, True),  # app-window: Brave's address bar, through the watcher's omnibox` to
  `SENDS`. In `test_the_message_table_has_exactly_the_written_down_types`, `len(SENDS)` becomes 60 and the
  watcher's count 23 (the app's stays 52);
- add `"keyword_started"` to `RECEIVES`. In `test_what_the_watcher_receives_is_a_fixed_list`,
  `len(RECEIVES) == 18` becomes `== 19`.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_app_server.py tests/test_watcher.py tests/test_watcher_rules.py -q -p no:randomly -k "keyword or message_table or receives"`

Expected: FAIL. The server drops `ai_keyword`, `_keyword_workflow` doesn't exist, the watcher's manifest has no
omnibox, and `startKeywordTask` is undefined.

- [ ] **Step 3: The keyword, in the watcher and the server**

In `src/ai_browser/app/server.py`:

1. Under `URL_LIMIT`, add `KEYWORD_LIMIT = 2000  # characters of what the user typed after "ai" in Brave's address
   bar`.
2. In `MESSAGE_RULES`, add `"ai_keyword": Rule(app=False, watcher=True),  # Brave's address bar: only the watcher's
   omnibox handler`.
3. In `WATCHER_RECEIVES`, add `"keyword_started"`.
4. Add the methods:

   ```python
       def _keyword_workflow(self, text: str) -> tuple[str, str] | None:
           """The workflow a keyword's text starts with: the longest name it starts with, then a space or nothing more,
           without regard to case. (slug, the rest of the text), or None."""
           if self.workflows is None:
               return None
           lower, found = text.lower(), None
           for workflow in self.workflows.all():
               name = workflow.name.lower()
               if (lower == name or lower.startswith(f"{name} ")) and (found is None or len(name) > len(found[0])):
                   found = (name, workflow.slug)
           return None if found is None else (found[1], text[len(found[0]):].strip())

       async def _keyword(self, queue: asyncio.Queue, message: dict) -> None:
           """"ai", a space and a task in Brave's address bar: the user's own Enter, like Start in AI Home. It never
           goes through the Brain, and it never hands over a tab: adopt and tab are ignored here."""
           request = message.get("request") if isinstance(message.get("request"), (str, int)) else None
           text = message.get("text").strip()[:KEYWORD_LIMIT].strip() if isinstance(message.get("text"), str) else ""
           if not text:
               return
           try:
               found = self._keyword_workflow(text)
               if found is not None and self.runner is not None:
                   agent_id = await self.runner.run(found[0], text=found[1] or None)
               else:
                   model = self.settings.get()["model"] or self.default_model
                   agent_id = (await self.agents.create(text, [], model)).id
           except ValueError as exc:
               queue.put_nowait({"type": "error", "request": request, "text": str(exc)})
               return
           agent = self.agents.agents.get(agent_id)
           queue.put_nowait({"type": "keyword_started", "request": request, "id": agent_id,
                             "number": agent.number if agent is not None else int(agent_id[1:]),
                             "name": agent.name if agent is not None else ""})
   ```

5. In `_handle`, before `elif kind == "new_task":`, add:

   ```python
           elif kind == "ai_keyword":
               await self._keyword(queue, message)
   ```

In `src/ai_browser/app/watcher/manifest.json`:
- `"version": "0.1.0"` becomes `"version": "0.2.0"`;
- after the `"description"` line, add `"omnibox": {"keyword": "ai"},`. No new permission is needed.

In `src/ai_browser/app/watcher/worker.js`:

1. In `handle(message)`, add this branch before `else if (message.type === "fill_reply")`:

   ```js
     else if (message.type === "keyword_started" || (message.type === "error" && keywordRequests.has(message.request))) {
       await keywordAnswered(message);
     }
   ```

2. In `chrome.notifications.onClicked.addListener`, right after `chrome.notifications.clear(id);`, add
   `if (note.keyword) return; // a keyword's notice: clicking it only dismisses it`.
3. After the line `chrome.action.onClicked.addListener(() => { openBrain().catch(() => {}); });`, add:

   ```js
   // ---- the "ai" keyword: Brave's address bar starts an agent in AI Browser ---------------------------------------
   // Only this handler sends ai_keyword, with what the user typed after "ai" and a space. It never hands over a tab
   // (the app ignores any), never waits for the line, and with the app off it says so and queues nothing.

   const NOT_RUNNING = "AI Browser isn't running: start it with `uv run ai-browser app`";
   const keywordRequests = new Set();

   async function keywordNotice(message) { // set through the API, as text
     const text = String(message).slice(0, 300);
     const id = `k${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
     await keepNote(id, { keyword: { message: text } });
     await chrome.notifications.create(id, { type: "basic", iconUrl: "icon.png", priority: 1, title: "AI Browser",
                                             message: text });
   }

   function startKeywordTask(text) {
     const task = String(text || "").trim().slice(0, 2000);
     if (!task) return false;
     const request = `kw-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
     if (!link.send({ type: "ai_keyword", text: task, request })) {
       keywordNotice(NOT_RUNNING).catch(() => {});
       return false;
     }
     keywordRequests.add(request);
     return true;
   }
   globalThis.startKeywordTask = startKeywordTask; // for the tests, as AI Browser's old worker had startTask

   async function keywordAnswered(message) {
     if (!keywordRequests.delete(message.request)) return;
     if (message.type === "keyword_started") {
       await keywordNotice(`Started ${message.number} · ${message.name}. See it in AI Browser's window.`);
     } else if (message.text) {
       await keywordNotice(message.text);
     }
   }

   chrome.omnibox.setDefaultSuggestion({ description: "Start an AI Browser agent: %s" });
   chrome.omnibox.onInputEntered.addListener((text) => { startKeywordTask(text); });
   ```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_app_server.py tests/test_watcher.py tests/test_watcher_rules.py tests/test_workflows.py -q -p no:randomly`

Expected: PASS. The watcher reloads itself with the new build, as before.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/server.py src/ai_browser/app/watcher/manifest.json src/ai_browser/app/watcher/worker.js \
  tests/test_app_server.py tests/test_watcher.py tests/test_watcher_rules.py tests/test_workflows.py
git commit -m "feat(watcher): the ai keyword moves to Brave's address bar, through the watcher"
```

### Task 13: AI Browser's pages over http: `link.js`'s second way in, settings from the server, the rebuilt `stack`

From this task on, the UI tests open the pages the way the window does, in a throwaway headless Chrome with no
extension. The pages lose every `chrome.*` call they need at load. AI Browser's old extension (which `run.py` still
launches until Task 17) keeps working, because `link.js` keeps the extension path.

**Files:**
- Modify: `src/ai_browser/app/ui/link.js` (two ways in; `refused`)
- Modify: `src/ai_browser/app/ui/brainui.js` (`openSetup`; config.json only on an extension page)
- Modify: `src/ai_browser/app/ui/mic.js`
- Modify: `src/ai_browser/app/ui/home.js` and `src/ai_browser/app/ui/mission.js` (the model and Voice from the app's
  settings; the `refused` state; the pin code goes)
- Modify: `src/ai_browser/app/ui/talk.js` (one comment)
- Modify:
  - `tests/test_home.py`: `stack`, `home`, `open_page`, `page_js`, and the tests below;
  - `tests/test_mission.py`, `tests/test_talk.py`, `tests/test_mission_visuals.py`, `tests/test_ai_home_phase2.py`,
    `tests/test_brain_ui.py` and `tests/test_check_card.py` (mechanical);
  - `tests/test_panel.py` (skipped);
  - `tests/conftest.py` (`PIPE_FIXTURES`).
- Test: `tests/test_home.py`, `tests/test_mission.py`, `tests/test_appwindow.py` (the real window, headless)

**Interfaces:**
- Consumes:
  - `AppWindow(…, extra_args=…)` (Task 3);
  - `/open` and the cookie (Task 6), the guard and CSP (Task 8), window sockets (Task 9);
  - `snapshot.settings`, the `settings` message and `settings_set` (Task 10);
  - `server.window_info` (Task 10);
  - the relay's `FakeBrave` (with its `FakeRelay`).
- Produces:
  - `link.js`: `connect({view, onMessage, onState})`. On an `http:` page it opens `ws://<location.host>/ws`; on close
    code 4403 it reports `"refused"` and stops retrying. On a `chrome-extension:` page, config.json and `?token=`,
    as before. `targetOfTab` and `tabOfTarget` stay until Task 21;
  - `brainui.js`: `mountBrain(root, link, {compact, openAgent, cards, openSetup = null})`;
  - the pages' status titles: `refused` reads "This window wasn't opened by this run of ai-browser app: close it";
  - tests (`tests/test_home.py`):
    - `WINDOW_INFO`;
    - `stack`, a dict with `server`, `cdp`, `url`, `ws_url`, `home`, `log`, `runner`, `script`, `brain`,
      `workflows`, `tools`, `hearing`, `engine`, `user`, `brave`, `home_js` and `home_target`;
    - `home`, returning `(js, stack)`;
    - `open_page(cdp, url)`, whose `js` now carries `.cdp` and `.session`;
    - `page_js(cdp, target) -> js`.

- [ ] **Step 1: Rebuild the fixture and write the failing tests**

In `tests/test_home.py`, replace the module docstring, `open_page`, `stack` and `home` with the code below. Add
`page_js` after `open_page`. The `HOSTILE`, `evaluate`, `until`, `post_tab`, `CHIP` and `in_row` helpers stay as
merged.

```python
"""AI Home and its window: the pages over http, opened the way AI Browser's window opens them (a one-time code swapped
for the window's cookie) in a throwaway headless Chrome, talking to a real app server (agents run the fake claude)."""
```

```python
async def open_page(cdp, url, background=False):
    """(target, js) for a new tab showing `url`, once it has left about:blank. js.cdp and js.session drive it."""
    params = {"url": url, **({"background": True} if background else {})}
    target = (await cdp.send("Target.createTarget", params))["targetId"]
    session = (await cdp.send("Target.attachToTarget", {"targetId": target, "flatten": True}))["sessionId"]

    async def js(expression):
        return await evaluate(cdp, session, expression)

    js.cdp, js.session = cdp, session
    await until(js, "location.protocol !== 'about:' && document.readyState === 'complete'")
    return target, js


async def page_js(cdp, target):
    """js(expression) in a page that is already open (a window one of ours opened)."""
    session = (await cdp.send("Target.attachToTarget", {"targetId": target, "flatten": True}))["sessionId"]

    async def js(expression):
        return await evaluate(cdp, session, expression)

    js.cdp, js.session = cdp, session
    return js


WINDOW_INFO = {"using": "chrome", "name": "Google Chrome", "note": "",
               "choices": [{"id": "auto", "name": "Auto (Google Chrome)", "installed": True},
                           {"id": "chrome", "name": "Google Chrome", "installed": True},
                           {"id": "brave", "name": "Brave", "installed": True}]}


@pytest.fixture
async def stack(fake_claude, tmp_path):
    """A real app server (agents on the fake claude) and its pages in a throwaway headless Chrome, opened the way AI
    Browser's window opens them: a one-time code swapped for the window's cookie. The throwaway keeps its debugging
    port because the tests drive the pages through it; the product's window never has one. Agents browse in the
    user's browser, here a FakeBrave with no tabs (a test that needs tabs attaches its own)."""
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer
    from ai_browser.brain.service import BrainService
    from ai_browser.brain.skillwriter import SkillWriter
    from ai_browser.brain.store import BrainStore
    from ai_browser.brain.tools import ToolsConfig
    from ai_browser.brain.workflows import WorkflowRunner, WorkflowStore
    from ai_browser.cdp import CDP
    from ai_browser.chrome import find_ws_url, launch
    from ai_browser.hearing.service import HearingService
    from fake_brave import FakeBrave
    from fake_engine import FakeEngine, tiny_store

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    home = tmp_path / "home"
    agents = AgentManager(home, claude=runner)
    brain = BrainService(BrainStore(home), agents, claude=runner)
    engine = FakeEngine(answers=["what is fix the footer doing"])
    hearing = HearingService(tiny_store(home / "models"), engine)  # talking is ready: the tiny model is in place
    workflows = WorkflowStore(home)
    tools = ToolsConfig(home, claude_home=tmp_path / "user")  # the tests that use it write a configuration there
    skills = SkillWriter(tmp_path / "user" / ".claude" / "skills", claude=runner, cwd=tmp_path / "calls")
    server = AppServer(home, agents, brain=brain, workflows=workflows, runner=WorkflowRunner(workflows, agents),
                       tools=tools, skill_writer=skills, hearing=hearing)
    url = await server.start()
    server.window_info = WINDOW_INFO  # Chrome draws it; Chrome and Brave installed, whatever this computer has
    brave = FakeBrave([])
    server.attach_brave(brave)
    agents.close_tabs = brave.close_targets
    profile = tmp_path / "profile"
    process = launch(profile, headless=True)
    ws_url = find_ws_url(profile, timeout=20)
    cdp = await CDP.connect(ws_url)
    target, js = await open_page(cdp, f"{url}/open?code={server.new_launch_code()}")  # the cookie, the real way
    assert await until(js, "location.pathname === '/home'")
    state = {"server": server, "cdp": cdp, "url": url, "ws_url": ws_url, "home": home, "log": log, "runner": runner,
             "script": script, "brain": brain, "workflows": workflows, "tools": tools, "hearing": hearing,
             "engine": engine, "user": tmp_path / "user", "brave": brave, "home_js": js, "home_target": target}
    yield state
    await cdp.close()
    await state["server"].stop()
    process.terminate()
    process.wait(timeout=15)


@pytest.fixture
async def home(stack):
    """(js in AI Home, the page the window opened; stack)."""
    js = stack["home_js"]
    assert await until(js, "document.getElementById('status').dataset.state === 'connected'")
    return js, stack
```

In `tests/test_home.py`, delete these tests. They tested AI Browser's own extension: its worker, its tab groups, its
new tab page, its pinned tab, or AI Browser mode.
- `test_the_address_bar_keyword_starts_a_task` (the watcher's keyword is tested in `test_watcher.py`, Task 12);
- `test_agent_tabs_are_grouped_once`;
- `test_ai_home_is_the_new_tab_page`;
- `test_ai_home_is_one_pinned_tab_in_front_after_a_start`;
- `test_ai_browser_groups_nothing_when_agents_browse_in_brave`;
- `test_ai_browser_mode_says_so`.

Replace `test_pages_reconnect_after_the_app_restarts`, `test_rows_are_updated_in_place_so_clicks_land` and
`test_ai_home_shows_agents_tabs_and_skills_as_text` with the versions below. Then add the other tests:

```python
@CHROME
async def test_ai_home_shows_agents_tabs_and_skills_as_text(home):
    from fake_brave import FakeBrave

    js, stack = home
    await stack["server"].agents.create(HOSTILE)
    assert await until(js, "document.querySelectorAll('#agents .agent').length === 1")
    assert "<img" in await js("document.querySelector('#agents .agent .name').textContent")
    assert await js("document.querySelectorAll('#agents img:not(.thumb)').length") == 0
    assert await js("document.title") != "pwned"
    assert await until(js, "/\\d/.test(document.querySelector('#skills .count').textContent)")
    stack["server"].attach_brave(FakeBrave([{"target": "S1", "url": "https://shop.example/", "title": "Shop page"}]))
    assert await until(js, "document.getElementById('tabs').textContent.includes('Shop page')")


@CHROME
async def test_ai_home_connects_over_http_with_the_windows_cookie(home):
    js, stack = home
    assert await js("location.origin") == stack["url"] and stack["server"].window_count >= 1
    assert await js("document.cookie") == ""  # HttpOnly: the page's own script can't read the window's cookie


@CHROME
async def test_an_old_window_is_refused_after_the_app_restarts(home):
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer

    js, stack = home
    port = stack["server"].port
    await stack["server"].stop()
    assert await until(js, "document.getElementById('status').dataset.state !== 'connected'")
    server = AppServer(stack["home"], AgentManager(stack["home"], claude=stack["runner"]), ports=range(port, port + 1))
    stack["server"] = server
    try:
        await server.start()  # the same address, a new run: the window's cookie holds the old secret
    except RuntimeError:
        pytest.skip("this system still holds the old address")
    assert await until(js, "document.getElementById('status').dataset.state === 'refused'", 15)
    assert await js("document.getElementById('status').title") == (
        "This window wasn't opened by this run of ai-browser app: close it")
    await asyncio.sleep(2)
    assert await js("document.getElementById('status').dataset.state") == "refused"  # it stopped trying
    assert server.window_count == 0


@CHROME
async def test_rows_are_updated_in_place_so_clicks_land(home):
    from fake_brave import FakeBrave

    js, stack = home
    server = stack["server"]
    stack["script"].write_text(json.dumps([EVENTS[0], {"sleep": 4}, *EVENTS[1:]]),
                               encoding="utf-8")  # it keeps working a while
    server.attach_brave(FakeBrave([{"target": "P1", "url": "https://some.example/", "title": "Some page"}]))
    agent = await server.agents.create("keep working")
    row = f"#agents .agent[data-id='{agent.id}']"
    assert await until(js, f"!!document.querySelector(\"{row} .stop\") && "
                           "document.getElementById('tabs').textContent.includes('Some page')")
    await js(f"window.held = [document.querySelector(\"{row} .stop\"), document.querySelector('#tabs .tab')]; true")
    for step in range(3):  # each change of the agent redraws its row: in place
        agent.status = f"step {step}"
        server.agents._changed(agent)
        await asyncio.sleep(0.1)
    await asyncio.sleep(0.5)
    assert await js(f"document.querySelector(\"{row} .status\").textContent") == "step 2"
    assert await js("window.held.every(node => node.isConnected)")  # the same elements: a click can't be lost


@CHROME
async def test_the_pages_csp_blocks_injected_script_and_the_other_routes(home):
    js, _ = home
    await js("window.violations = 0;"
             "document.addEventListener('securitypolicyviolation', () => { window.violations += 1; });"
             "const script = document.createElement('script'); script.textContent = 'window.pwned = true';"
             "document.body.append(script); true")
    assert await until(js, "window.violations >= 1")
    assert await js("window.pwned === undefined")
    assert await js("fetch('/agent-status').then(() => 'reached', () => 'blocked')") == "blocked"


@CHROME
async def test_a_page_opened_any_other_way_gets_no_socket(home):
    js, stack = home
    cdp, server = stack["cdp"], stack["server"]
    before = server.window_count
    context = (await cdp.send("Target.createBrowserContext"))["browserContextId"]  # no cookie there, as in Brave
    try:
        target = (await cdp.send("Target.createTarget", {"url": stack["url"] + "/home",
                                                         "browserContextId": context}))["targetId"]
        other = await page_js(cdp, target)
        assert await until(other, "document.body !== null && "
                                  "document.body.textContent.includes('open only in its own window')")
        await asyncio.sleep(1)
        assert server.window_count == before and await other("document.scripts.length") == 0
    finally:
        await cdp.send("Target.disposeBrowserContext", {"browserContextId": context})
```

In `tests/test_mission.py`:
- `open_mission` opens `stack["url"] + "/mission"`;
- delete `test_ai_home_opens_mission_control_once`. It drove `chrome.tabs`, and Task 14 writes its window version;
- append:

```python
@CHROME
async def test_the_model_is_the_apps_choice_in_every_window(home):
    from ai_browser.settings import read_settings

    js, stack = home
    mission = await open_mission(stack)
    assert await mission("document.getElementById('task-model').value") == "sonnet"  # ai-browser app --model
    await js("const picker = document.getElementById('task-model'); picker.value = 'opus';"
             "picker.dispatchEvent(new Event('change')); true")
    assert await until(mission, "document.getElementById('task-model').value === 'opus'")  # no reload needed
    assert read_settings(stack["home"])["model"] == "opus"
    await js("location.reload(); true")
    await asyncio.sleep(0.5)
    assert await until(js, "document.getElementById('status')?.dataset.state === 'connected' && "
                           "document.getElementById('task-model').value === 'opus'")


@CHROME
async def test_voice_comes_back_on_from_the_apps_settings(stack):
    from ai_browser.settings import read_settings

    js = await open_with(stack, LOCAL_VOICE)
    await voice_on(js)
    for _ in range(50):
        if read_settings(stack["home"]).get("voice") is True:
            break
        await asyncio.sleep(0.1)
    assert read_settings(stack["home"])["voice"] is True
    later = await open_with(stack, LOCAL_VOICE)  # Mission Control opened again: Voice is on at load
    assert await until(later, "document.getElementById('voice').checked === true")
```

The other UI test files need mechanical edits: the `home` fixture's new shape, the pages' http addresses, and
modules imported by address. Run:

```bash
uv run python - <<'PY'
import re
from pathlib import Path

for name in ("test_home.py", "test_mission.py", "test_talk.py", "test_mission_visuals.py", "test_ai_home_phase2.py",
             "test_brain_ui.py", "test_check_card.py"):
    path = Path("tests") / name
    text = path.read_text(encoding="utf-8")
    new = text.replace("js, _, stack = home", "js, stack = home").replace("_, _, stack = home", "_, stack = home")
    new = new.replace("f\"chrome-extension://{stack['app'].extension_id}/mission.html\"", "stack[\"url\"] + \"/mission\"")
    new = re.sub(r"""import\(chrome\.runtime\.getURL\((["'])([\w-]+\.js)\1\)\)""", r"import(\1/\2\1)", new)
    if new != text:
        path.write_text(new, encoding="utf-8")
        print(path)
PY
grep -n "chrome-extension://{stack\|stack\[.app.\]\|worker_js\|getURL" tests/test_home.py tests/test_mission.py \
  tests/test_talk.py tests/test_mission_visuals.py tests/test_ai_home_phase2.py tests/test_brain_ui.py \
  tests/test_check_card.py
```

Expected from the grep: only the watcher's lines remain, which use `watcher.app.extension_id` and `watcher.worker_js`.
Those are the `watcher` fixture's, unchanged.

AI Browser's side panel is not served any more. Wave D ports its tests to the watcher. Skip them, without deleting
them:
- at the top of `tests/test_panel.py`, under its imports, add:

  ```python
  pytestmark = pytest.mark.skip(reason="AI Browser's side panel retired in wave B (the app window); the side-chat "
                                       "plan (wave D) ports these tests to the watcher")
  ```

- above `test_the_panel_shows_the_same_card` in `tests/test_ai_home_phase2.py`, and above
  `test_the_panel_shows_the_same_card_for_the_users_own_tab` in `tests/test_check_card.py`, add:

  ```python
  @pytest.mark.skip(reason="AI Browser's side panel retired in wave B; the side-chat plan (wave D) moves this test")
  ```

In `tests/conftest.py`, `PIPE_FIXTURES` loses `"stack"`. The UI tests run on Windows now.

Append to `tests/test_appwindow.py`. Add `from ai_browser.chrome import chrome_binary` to its imports, and
`CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")` below them:

```python
@CHROME
async def test_the_real_window_connects_with_no_debugging_port_and_ends(fake_claude, tmp_path):
    import asyncio

    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer

    runner, _, _ = fake_claude
    home = tmp_path / "home"
    server = AppServer(home, AgentManager(home, claude=runner))
    url = await server.start()
    app = None
    try:
        start = f"{url}/open?code={server.new_launch_code()}"
        # The address comes twice, because headless Chrome's handling of --app= wasn't measured. The code is single
        # use: a second page either finds the cookie the first one got (a reload, as for the window) or gets the 403
        # page and no socket.
        app = window.AppWindow(home, window.WindowBrowser("chrome", "Google Chrome", chrome_binary()),
                               extra_args=("--headless=new", start))
        app.launch(start)
        for _ in range(200):
            if server.window_count >= 1:
                break
            await asyncio.sleep(0.1)
        assert 1 <= server.window_count <= 2  # AI Home's page, over http, with the window's cookie
        assert not (app.profile / "DevToolsActivePort").exists()  # no debugging port: nothing can drive it
        assert await asyncio.to_thread(app.close) == ""
        assert app.process.poll() is not None
    finally:
        if app is not None and app.process is not None and app.process.poll() is None:
            app.process.kill()
        await server.stop()
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_home.py tests/test_mission.py tests/test_appwindow.py -q -p no:randomly -k "over_http or old_window or csp or any_other_way or model_is or voice_comes or tabs_and_skills or in_place or real_window"`

Expected: FAIL, most of them as errors in the `home` fixture. On an http page, `link.js` reads config.json through
`chrome.runtime`, which an http page lacks, so no page ever connects: AI Home's status never reaches `connected`,
and the real window's page never counts as a window. (Past that, `brainui.js` would stop at
`chrome.runtime.getURL` and Mission Control at `chrome.storage`; Step 3 fixes all three.)

- [ ] **Step 3: The pages run over http**

Replace `src/ai_browser/app/ui/link.js` whole:

```js
// The line to `ai-browser app`, two ways in. AI Browser's window (an http page the app serves) opens /ws on its own
// address: the window's cookie goes with it, and a page that this run of the app didn't open is refused (close code
// 4403), so it stops trying. Brave's watcher (a chrome-extension page) reads config.json (the server's address and
// token) again before every attempt, so a restarted app, on a new port with a new token, is found again. Pings from the
// server keep the watcher's service worker, and its socket, alive. Also, until AI Browser's old extension retires:
// Chrome tab ids <-> DevTools target ids.
"use strict";

const REFUSED = 4403; // the server's close code for a socket it won't take

async function address() {
  if (location.protocol === "http:") return `ws://${location.host}/ws`; // the window: its cookie goes along
  const config = await (await fetch(chrome.runtime.getURL("config.json"), { cache: "no-store" })).json();
  return `${config.server.replace(/^http/, "ws")}/ws?token=${encodeURIComponent(config.token)}`;
}

export function connect({ view, onMessage = () => {}, onState = () => {} }) {
  let socket = null;
  let retries = 0;
  let refused = false;
  const waiters = [];

  function retry() {
    if (!refused) setTimeout(open, Math.min(5000, 250 * 2 ** retries++));
  }

  async function open() {
    onState("connecting");
    let ws;
    try {
      ws = new WebSocket(await address());
    } catch {
      onState("disconnected");
      retry();
      return;
    }
    ws.onopen = () => {
      retries = 0;
      socket = ws;
      ws.send(JSON.stringify({ type: "hello", view }));
      onState("connected");
      for (const resolve of waiters.splice(0)) resolve();
    };
    ws.onmessage = (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      if (message && message.type !== "ping") onMessage(message);
    };
    ws.onclose = (event) => {
      if (socket === ws) socket = null;
      if (event.code === REFUSED && location.protocol === "http:") { // not this run's window: retrying can't help
        refused = true;
        onState("refused");
        return;
      }
      onState("disconnected");
      retry();
    };
  }

  open();
  return {
    send(message) {
      if (!socket || socket.readyState !== WebSocket.OPEN) return false;
      socket.send(JSON.stringify(message));
      return true;
    },
    whenOpen() {
      if (socket && socket.readyState === WebSocket.OPEN) return Promise.resolve();
      return new Promise((resolve) => waiters.push(resolve));
    },
  };
}

async function targets() {
  try {
    return await chrome.debugger.getTargets(); // only lists them: nothing is attached
  } catch {
    return [];
  }
}

export async function targetOfTab(tabId) {
  return (await targets()).find((target) => target.tabId === tabId)?.id ?? null;
}

export async function tabOfTarget(target) {
  return (await targets()).find((info) => info.id === target)?.tabId ?? null;
}
```

In `src/ai_browser/app/ui/brainui.js`:

1. `mountBrain`'s options gain `openSetup = null`. Today the destructuring reads
   `{ compact = false, openAgent = null, cards = "view" } = {}`; it becomes
   `{ compact = false, openAgent = null, cards = "view", openSetup = null } = {}`.
2. The `fetch(chrome.runtime.getURL("config.json"), …)` statement runs only on the watcher's extension page.
   Wrap it as:

   ```js
     if (!openSetup && location.protocol === "chrome-extension:") { // the watcher's Brain page: the server's address
       fetch(chrome.runtime.getURL("config.json"), { cache: "no-store" }).then((answer) => answer.json()).then((config) => {
         setupUrl = `${config.server}/setup#brave`;
         renderHead();
       }).catch(() => {});
     }
   ```

3. In `renderHead`, the `if (!watcherOn) {…}` block becomes:

   ```js
       if (!watcherOn) {
         watcher.append("The watcher isn't connected in Brave");
         if (openSetup) { // AI Browser's window: the setup steps in a small window of their own
           const setup = el("button", "brain-setup link", "Set it up");
           setup.type = "button";
           setup.addEventListener("click", () => openSetup());
           watcher.append(" · ", setup);
         } else if (setupUrl) { // the watcher's Brain page, in Brave: a new tab there is right
           const setup = el("a", "brain-setup", "Set it up");
           setup.href = setupUrl;
           setup.target = "_blank";
           watcher.append(" · ", setup);
         }
       }
   ```

In `src/ai_browser/app/ui/mic.js`, the line
`await context.audioWorklet.addModule(chrome.runtime.getURL("mic-worklet.js"));` becomes:

```js
    await context.audioWorklet.addModule(new URL("./mic-worklet.js", import.meta.url).href);
```

In `src/ai_browser/app/ui/home.js`:

1. Replace the line `let storedModel = false; // the user picked a model here before: it wins over the app's default`
   with:

   ```js
   let defaultModel = "sonnet"; // ai-browser app --model, until the user picks one (the app remembers the pick)
   ```

2. Replace `setStatus` with:

   ```js
   function setStatus(state) {
     $("status").dataset.state = state;
     $("status").title = { connected: "Connected to ai-browser app", connecting: "Connecting…",
                           refused: "This window wasn't opened by this run of ai-browser app: close it" }[state]
       || "Not connected: is `ai-browser app` running?";
   }
   ```

3. Add, after `setStatus`:

   ```js
   function applySettings(settings) { // the model picked last, here or in Mission Control: the app keeps it
     if (!settings) return;
     const model = settings.model ?? defaultModel;
     if ([...$("task-model").options].some((option) => option.value === model)) $("task-model").value = model;
   }
   ```

4. In `handle`'s `case "snapshot":`, replace
   `if (!storedModel && message.default_model) $("task-model").value = message.default_model;` with:

   ```js
         defaultModel = message.default_model || defaultModel;
         applySettings(message.settings);
   ```

5. In `handle`'s `switch`, add a case right before `case "agent":`:

   ```js
       case "settings":
         applySettings(message);
         break;
   ```

6. Replace

   ```js
   $("task-model").addEventListener("change", () => {
     chrome.storage.local.set({ model: $("task-model").value }).catch(() => {});
   });
   ```

   with:

   ```js
   $("task-model").addEventListener("change", () => {
     link.send({ type: "settings_set", key: "model", value: $("task-model").value });
   });
   ```

7. Delete the whole `(async () => { … })();` block at the end of the file. It read `chrome.storage` and pinned AI
   Home's tab.

In `src/ai_browser/app/ui/mission.js`:

1. Replace `let storedModel = false;` with
   `let defaultModel = "sonnet"; // ai-browser app --model, until the user picks one (the app remembers the pick)`.
2. Replace `setStatus` with the same `refused` title as AI Home's. Keep its first line, `talk?.connection(state);`:

   ```js
   function setStatus(state) {
     talk?.connection(state); // a lost line ends a turn, or a question, at once
     $("status").dataset.state = state;
     $("status").title = { connected: "Connected to ai-browser app", connecting: "Connecting…",
                           refused: "This window wasn't opened by this run of ai-browser app: close it" }[state]
       || "Not connected: is `ai-browser app` running?";
   }
   ```

3. Add, after `setStatus`:

   ```js
   function applySettings(settings) { // the model picked last, here or in AI Home: the app keeps it
     if (!settings) return;
     const model = settings.model ?? defaultModel;
     if ([...$("task-model").options].some((option) => option.value === model)) $("task-model").value = model;
   }
   ```

4. In `handle`'s `case "snapshot":`, replace
   `if (!storedModel && message.default_model) $("task-model").value = message.default_model;` with:

   ```js
         defaultModel = message.default_model || defaultModel;
         applySettings(message.settings);
         if (message.settings?.voice && !$("voice").checked) setVoice(true); // Voice was on: it comes back on
   ```

5. In `handle`'s `switch`, add before `case "agent":`:

   ```js
       case "settings":
         applySettings(message);
         break;
   ```

6. Replace the Voice listener and the line after it:

   ```js
   $("voice").addEventListener("change", async () => {
     const result = await setVoice($("voice").checked);
     chrome.storage.local.set({ voice: result.on }).catch(() => {});
   });
   chrome.storage.local.get("voice").then(({ voice: on }) => { if (on) setVoice(true); }).catch(() => {});
   ```

   with:

   ```js
   $("voice").addEventListener("change", async () => {
     const result = await setVoice($("voice").checked);
     link.send({ type: "settings_set", key: "voice", value: result.on }); // remembered by the app, not the browser
   });
   ```

7. Replace the model listener and the `chrome.storage.local.get("model").then(…)` block after it with:

   ```js
   $("task-model").addEventListener("change", () => {
     link.send({ type: "settings_set", key: "model", value: $("task-model").value });
   });
   ```

In `src/ai_browser/app/ui/talk.js`, the comment
`// the model last picked (the task bar's, from chrome.storage.local)` becomes
`// the model last picked (the task bar's, from the app's settings)`.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_home.py tests/test_mission.py tests/test_appwindow.py -q -p no:randomly`

Expected: PASS. The real window's test shows the whole chain: the window's exact command line (plus
`--headless=new`), the code, the cookie, and the page's socket.

Run, one file at a time:
- `uv run pytest tests/test_talk.py -q -p no:randomly`
- `uv run pytest tests/test_mission_visuals.py -q -p no:randomly`
- `uv run pytest tests/test_ai_home_phase2.py tests/test_brain_ui.py tests/test_check_card.py tests/test_panel.py -q -p no:randomly`

Expected: PASS, with `test_panel.py` and the two panel tests skipped. The mic tests now load the worklet by
`import.meta.url` over http.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/ui/link.js src/ai_browser/app/ui/brainui.js src/ai_browser/app/ui/mic.js \
  src/ai_browser/app/ui/home.js src/ai_browser/app/ui/mission.js src/ai_browser/app/ui/talk.js tests/test_home.py \
  tests/test_mission.py tests/test_talk.py tests/test_mission_visuals.py tests/test_ai_home_phase2.py \
  tests/test_brain_ui.py tests/test_check_card.py tests/test_panel.py tests/conftest.py tests/test_appwindow.py
git commit -m "feat(ui): AI Browser's pages run over http with the window's cookie; the model and Voice are the app's"
```

### Task 14: Windows of our own: `nav.js`, popups for our pages, links to the user's browser, the static guard

**Files:**
- Create: `src/ai_browser/app/ui/nav.js`
- Modify: `src/ai_browser/app/ui/home.js` (the window's name, `guardLinks`, Mission Control, the switch's steps, the
  inbox's Set it up)
- Modify: `src/ai_browser/app/ui/mission.js` (`guardLinks`, the AI Home button, the inbox's Set it up)
- Modify: `src/ai_browser/app/ui/mission.html` (the AI Home link becomes a button)
- Modify: `src/ai_browser/app/ui/check.js` (`openLive`)
- Modify: `src/ai_browser/app/ui/brainui.css` (the Set it up button)
- Modify: `tests/test_home.py` (helpers), `tests/test_mission.py`, `tests/test_ui_static.py`
- Test: `tests/test_home.py`, `tests/test_mission.py`, `tests/test_ui_static.py`

**Interfaces:**
- Consumes: `open_url` (Task 11), and `brainui.js`'s `openSetup` option (Task 13).
- Produces (`ui/nav.js`, imported by `home.js`, `mission.js` and, from Task 15, `settings.js`; never by a file the
  watcher shares):
  - `WINDOWS = {"/home": ["aib-home", 1440, 960], "/mission": ["aib-mission", 1280, 860], "/settings":
    ["aib-settings", 720, 760], "/setup": ["aib-setup", 760, 900]}`;
  - `openWindow(path, name, width, height) -> Window | null`;
  - `focusHome()`;
  - `guardLinks(link)`.
- Produces (`ui/check.js`): `openLive(url)`, private to the file.
- Produces (tests): `click_as_user(js, selector)`, `page_targets(cdp, ending) -> list[str]` and
  `wait_targets(cdp, ending, count=1, seconds=10) -> list[str]`, in `tests/test_home.py`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_home.py`, after `page_js`:

```python
async def click_as_user(js, selector):
    """A click the browser counts as the user's own (Runtime.evaluate with userGesture): window.open needs one."""
    result = await js.cdp.send("Runtime.evaluate", {
        "expression": f"document.querySelector({json.dumps(selector)}).click(); true", "userGesture": True,
        "returnByValue": True}, session_id=js.session)
    return result.get("result", {}).get("value")


async def page_targets(cdp, ending) -> list[str]:
    """The page targets whose address ends with `ending` ("/mission", "/setup#brave")."""
    infos = (await cdp.send("Target.getTargets"))["targetInfos"]
    return [info["targetId"] for info in infos if info["type"] == "page" and info["url"].endswith(ending)]


async def wait_targets(cdp, ending, count=1, seconds=10) -> list[str]:
    for _ in range(int(seconds * 10)):
        found = await page_targets(cdp, ending)
        if len(found) >= count:
            return found
        await asyncio.sleep(0.1)
    return await page_targets(cdp, ending)
```

Append to `tests/test_home.py`:

```python
@CHROME
async def test_the_setup_steps_open_in_a_small_window(home):
    js, stack = home
    cdp = stack["cdp"]
    assert await until(js, "document.querySelector('#brain .brain-setup') !== null")  # the watcher isn't connected
    await click_as_user(js, "#brain .brain-setup")
    [setup] = await wait_targets(cdp, "/setup#brave")
    assert await (await page_js(cdp, setup))("window.name") == "aib-setup"
    stack["brave"].set_state("off")
    assert await until(js, "document.getElementById('browser-action').textContent === 'Show me how'")
    await click_as_user(js, "#browser-action")
    assert await wait_targets(cdp, "/setup#switch") == [setup]  # the same small window, now on the switch's steps


@CHROME
async def test_links_go_to_the_users_browser_or_a_window_of_ours(home, monkeypatch):
    from ai_browser import platforms

    js, stack = home
    opened = []
    monkeypatch.setattr(platforms, "open_url", lambda url, browser=None, system=None: opened.append(url) or True)
    before = await js("location.href")
    await js("const site = document.createElement('a'); site.id = 'site'; site.href = 'https://example.com/pricing';"
             "site.textContent = 'pricing'; document.body.append(site);"
             "const ours = document.createElement('a'); ours.id = 'ours'; ours.href = '/mission';"
             "ours.target = '_blank'; ours.textContent = 'Mission Control'; document.body.append(ours); true")
    await js("document.getElementById('site').click(); true")
    for _ in range(50):
        if opened:
            break
        await asyncio.sleep(0.1)
    assert opened == ["https://example.com/pricing"] and await js("location.href") == before  # never in the window
    await click_as_user(js, "#ours")
    [mission] = await wait_targets(stack["cdp"], "/mission")
    await asyncio.sleep(0.5)
    assert await page_targets(stack["cdp"], "/mission") == [mission]
    assert await (await page_js(stack["cdp"], mission))("window.name") == "aib-mission"  # a _blank open has no name
```

Append to `tests/test_mission.py`, which also imports the new helpers: change its
`from test_home import …` line to

```python
from test_home import (HOSTILE, click_as_user, evaluate, home, open_page, page_js, page_targets, stack,  # noqa: F401
                       until, wait_targets)
```

and add:

```python
@CHROME
async def test_mission_control_opens_once_in_a_window_of_its_own(home):
    js, stack = home
    cdp = stack["cdp"]
    assert await js("window.name") == "aib-home"
    await click_as_user(js, "#mission")
    [mission] = await wait_targets(cdp, "/mission")
    await click_as_user(js, "#mission")  # open already: brought to the front, never a second one
    await asyncio.sleep(1)
    assert await page_targets(cdp, "/mission") == [mission]
    there = await page_js(cdp, mission)
    assert await until(there, "document.getElementById('status')?.dataset.state === 'connected'")
    assert await there("window.name") == "aib-mission"
    await click_as_user(there, "#home-link")  # AI Home's button: the main window comes forward, never a new one
    await asyncio.sleep(1)
    assert len(await page_targets(cdp, "/home")) == 1
```

Append to `tests/test_ui_static.py`:

```python
import re

INLINE_SCRIPT = re.compile(r"<script(?![^>]*\ssrc=)[^>]*>", re.IGNORECASE)


def test_the_window_pages_are_all_there():
    for name in ("home.html", "mission.html", "setup.html", "nav.js"):
        assert (UI / name).is_file(), name


def test_no_script_writes_html_and_no_page_runs_inline_code():
    scripts, pages = sorted(UI.glob("*.js")), sorted(UI.glob("*.html"))
    assert scripts and pages
    for path in scripts:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\.innerHTML|\.outerHTML|insertAdjacentHTML|document\.write", text), path.name
    for path in pages:
        text = path.read_text(encoding="utf-8")
        assert not INLINE_SCRIPT.search(text), path.name
        assert not re.search(r"<style|\sstyle\s*=", text, re.IGNORECASE), path.name
        assert not re.search(r"\son[a-z]+\s*=", text), path.name


def test_only_the_watchers_shared_files_reach_the_extension_apis():
    for path in sorted(UI.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        if path.name != "brainui.js":  # the watcher's own "Set it up" anchor: a new tab in Brave is right
            assert '"_blank"' not in text and "'_blank'" not in text, path.name
        if path.name not in ("link.js", "brainui.js"):
            assert "chrome." not in text, path.name


def test_nav_js_stays_out_of_the_watcher():
    from ai_browser.brain.watcher import WATCHER_SHARED

    assert "nav.js" not in WATCHER_SHARED
    for name in WATCHER_SHARED:
        assert "nav.js" not in (UI / name).read_text(encoding="utf-8"), name
```

(`import re` goes at the top of the file with the other import.)

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_ui_static.py tests/test_home.py tests/test_mission.py -q -p no:randomly -k "pages_are_all_there or inline_code or extension_apis or nav_js or small_window or links_go or opens_once"`

Expected: FAIL:
- `nav.js` doesn't exist;
- `check.js` holds `"_blank"`;
- `home.js` still calls `chrome.tabs`, so Mission Control and the setup steps open nothing on an http page, and
  AI Home's `window.name` is `""`.

- [ ] **Step 3: Windows of our own**

Create `src/ai_browser/app/ui/nav.js`:

```js
// Windows of our own. AI Browser's pages open as small app-style windows, never as tabs: a "_blank" open from an app
// window brings back a normal tabbed window, so this file never uses one. A link to a website goes to the user's own
// browser through the app (open_url), so the window never leaves its own pages. Only AI Home, Mission Control and
// Settings import this file; the files Brave's watcher shares never do.
"use strict";

export const WINDOWS = {
  "/home": ["aib-home", 1440, 960],
  "/mission": ["aib-mission", 1280, 860],
  "/settings": ["aib-settings", 720, 760],
  "/setup": ["aib-setup", 760, 900],
};

// A window of ours by name: opened on the first click, brought forward on the next (the size counts only when it is
// new). It loads `path` when it is new, or when it shows another page of ours than the one asked for.
export function openWindow(path, name, width, height) {
  const opened = window.open("", name, `popup,width=${width},height=${height}`);
  if (!opened) return null; // the popup blocker: only a click opens a window
  try {
    const showing = opened.location.href === "about:blank" ? null : opened.location.pathname + opened.location.hash;
    if (showing !== path) opened.location.replace(path);
  } catch {
    // not a page of ours: leave it as it is
  }
  opened.focus();
  return opened;
}

export function focusHome() {
  return openWindow("/home", ...WINDOWS["/home"]);
}

function ourPage(url) { // "/home", "/mission", "/settings" or "/setup", or null
  if (url.origin !== location.origin) return null;
  return Object.keys(WINDOWS).find((path) => url.pathname === path) || null;
}

// Every link click on the page (any button, any modifier): a page of ours opens in its own window, a website in the
// user's browser, and anything else is dropped. The click itself never navigates.
export function guardLinks(link) {
  const follow = (event) => {
    const anchor = event.target instanceof Element ? event.target.closest("a[href]") : null;
    if (!anchor) return;
    event.preventDefault();
    let url;
    try {
      url = new URL(anchor.getAttribute("href"), location.href);
    } catch {
      return;
    }
    const page = ourPage(url);
    if (page) openWindow(url.pathname + url.search + url.hash, ...WINDOWS[page]);
    else if ((url.protocol === "http:" || url.protocol === "https:") && url.origin !== location.origin) {
      link.send({ type: "open_url", url: url.href });
    }
  };
  for (const type of ["click", "auxclick"]) document.addEventListener(type, follow, true);
}
```

In `src/ai_browser/app/ui/home.js`:

1. Add to the imports: `import { guardLinks, openWindow, WINDOWS } from "./nav.js";`.
2. Right after the imports, add:

   ```js
   window.name = "aib-home"; // Mission Control's AI Home button finds this window by its name
   ```

3. Right after the line `const link = connect({ view: "home", onMessage: handle, onState: setStatus });`, add
   `guardLinks(link);`.
4. In the `mountBrain($("brain"), link, {…})` call, add `openSetup: () => openWindow("/setup#brave",
   ...WINDOWS["/setup"])` to its options object, beside wave A's `cards`.
5. Replace `browserAction` with:

   ```js
   function browserAction() {
     if (!browser || browser.kind !== "brave") return;
     if (browser.state === "off") { // the setup page's steps, with their warning, in a small window
       openWindow("/setup#switch", ...WINDOWS["/setup"]);
       return;
     }
     link.send({ type: "brave_connect" });
   }
   ```

6. Delete `let openingMission = null; …` and the function `openMission`. Replace the `$("mission")` listener with:

   ```js
   $("mission").addEventListener("click", () => openWindow("/mission", ...WINDOWS["/mission"]));
   ```

In `src/ai_browser/app/ui/mission.js`:

1. Add to the imports: `import { focusHome, guardLinks, openWindow, WINDOWS } from "./nav.js";`.
2. Right after `const link = connect({ view: "mission", onMessage: handle, onState: setStatus });`, add
   `guardLinks(link);`.
3. In `openBrain`, the `mountBrain(root, link, {…})` call's options gain `openSetup: () => openWindow("/setup#brave",
   ...WINDOWS["/setup"])`.
4. After `$("drawer-close").addEventListener("click", closeDrawer);`, add:

   ```js
   $("home-link").addEventListener("click", () => focusHome());
   ```

In `src/ai_browser/app/ui/mission.html`, replace
`<a id="home-link" class="button ghost" href="home.html">AI Home</a>` with:

```html
    <button id="home-link" class="ghost" type="button" title="Bring AI Home's window to the front">AI Home</button>
```

In `src/ai_browser/app/ui/check.js`:

1. After the `LIVE` constant, add:

   ```js
   function openLive(url) { // an engine's live view, in a small window; noopener: it can't reach back into our pages
     window.open(url, "aib-live", "popup,noopener,width=1280,height=860");
   }
   ```

2. Replace `if (live) window.open(live, "_blank", "noopener");` with `if (live) openLive(live);`.

In `src/ai_browser/app/ui/brainui.css`, append:

```css
.brain-setup.link { border: none; background: none; padding: 0; color: inherit; text-decoration: underline;
                    font: inherit; cursor: pointer; }
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_ui_static.py tests/test_home.py tests/test_mission.py tests/test_check_card.py -q -p no:randomly`

Expected: PASS. The live view's Show me still calls `window.open` with the live address first, as
`test_skip_is_offered_only_for_the_agents_own_tab` checks.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/ui/nav.js src/ai_browser/app/ui/home.js src/ai_browser/app/ui/mission.js \
  src/ai_browser/app/ui/mission.html src/ai_browser/app/ui/check.js src/ai_browser/app/ui/brainui.css \
  tests/test_home.py tests/test_mission.py tests/test_ui_static.py
git commit -m "feat(ui): our pages open as small app windows, websites in the user's browser; a static guard for both"
```

### Task 15: The Settings page

**Files:**
- Create: `src/ai_browser/app/ui/settings.html`, `src/ai_browser/app/ui/settings.js`
- Modify: `src/ai_browser/app/ui/home.html` (the header's Settings button), `src/ai_browser/app/ui/home.js` (its
  listener), `src/ai_browser/app/ui/home.css` (the page's few rules)
- Modify: `tests/test_ui_static.py` (`settings.html` joins the list)
- Test: `tests/test_home.py`, `tests/test_ui_static.py`

**Interfaces:**
- Consumes: `snapshot.settings`, `settings`, `settings_set` and `server.window_info` (Task 10); `openWindow`,
  `focusHome` and `guardLinks` (Task 14).
- Produces:
  - the Settings window (`aib-settings`, 720 × 760). It has one section in this wave, App window: a radio per
    choice, disabled with "· not installed" when the browser is missing, the line "This window: <name>. A change
    applies the next time AI Browser starts.", and the pick's note. Wave C adds "Where agents browse" below it;
  - AI Home's `#settings` button.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_home.py`:

```python
@CHROME
async def test_settings_opens_as_a_small_window_and_saves_the_choice(home):
    from ai_browser.settings import read_settings

    js, stack = home
    await click_as_user(js, "#settings")
    [target] = await wait_targets(stack["cdp"], "/settings")
    settings = await page_js(stack["cdp"], target)
    assert await until(settings, "document.querySelectorAll('#window-choices input').length === 3")
    assert await settings("window.name") == "aib-settings"
    labels = "[...document.querySelectorAll('#window-choices label')].map((label) => label.textContent)"
    assert await settings(labels) == ["Auto (Google Chrome)", "Google Chrome", "Brave"]
    assert await settings("document.querySelector('#window-choices input[value=auto]').checked") is True
    assert await settings("document.getElementById('window-using').textContent") == (
        "This window: Google Chrome. A change applies the next time AI Browser starts.")
    await settings("document.querySelector('#window-choices input[value=brave]').click(); true")
    for _ in range(50):
        if read_settings(stack["home"]).get("window_browser") == "brave":
            break
        await asyncio.sleep(0.1)
    assert read_settings(stack["home"])["window_browser"] == "brave"
    assert await until(settings, "document.querySelector('#window-choices input[value=brave]').checked")


@CHROME
async def test_a_browser_that_isnt_installed_is_greyed_out(home):
    js, stack = home
    stack["server"].window_info = {
        "using": "chrome", "name": "Google Chrome",
        "note": "Brave isn't installed: the window uses Google Chrome. Change it in Settings.",
        "choices": [{"id": "auto", "name": "Auto (Google Chrome)", "installed": True},
                    {"id": "chrome", "name": "Google Chrome", "installed": True},
                    {"id": "brave", "name": "Brave", "installed": False}]}
    await click_as_user(js, "#settings")
    [target] = await wait_targets(stack["cdp"], "/settings")
    settings = await page_js(stack["cdp"], target)
    assert await until(settings, "document.querySelectorAll('#window-choices input').length === 3")
    assert await settings("document.querySelector('#window-choices input[value=brave]').disabled") is True
    assert await settings("document.querySelectorAll('#window-choices label')[2].textContent") == (
        "Brave · not installed")
    assert (await settings("document.getElementById('window-note').textContent")).startswith("Brave isn't installed")
```

In `tests/test_ui_static.py::test_the_window_pages_are_all_there`, the tuple becomes
`("home.html", "mission.html", "settings.html", "setup.html", "nav.js")`.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_home.py tests/test_ui_static.py -q -p no:randomly -k "settings or greyed or all_there"`

Expected: FAIL. AI Home has no `#settings` button, and `settings.html` doesn't exist.

- [ ] **Step 3: The Settings page**

Create `src/ai_browser/app/ui/settings.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Settings</title>
<link rel="icon" href="icon.png">
<link rel="stylesheet" href="home.css">
</head>
<body>
<header class="top">
  <div class="brand"><span id="status" class="dot" data-state="connecting" title="Connecting…"></span>
    <h1>Settings</h1></div>
  <button id="home-link" class="ghost" type="button" title="Bring AI Home's window to the front">AI Home</button>
</header>
<main class="settings">
  <section id="window-section" class="card" aria-labelledby="window-title">
    <h2 id="window-title">App window</h2>
    <p>Which browser draws AI Browser's window</p>
    <div id="window-choices" class="choices" role="radiogroup" aria-labelledby="window-title"></div>
    <p id="window-using" class="muted"></p>
    <p id="window-note" class="muted" hidden></p>
    <p class="muted">The microphone is allowed per browser: after a switch, the window asks for it once more.</p>
    <p id="window-error" class="muted" role="status"></p>
  </section>
</main>
<script type="module" src="settings.js"></script>
</body>
</html>
```

Create `src/ai_browser/app/ui/settings.js`:

```js
// Settings, in a small window of its own: which browser draws AI Browser's window (wave C adds where agents browse).
// The choices come from the app; a change is saved there, and applies the next time AI Browser starts. Every name is
// set as text.
import { connect } from "./link.js";
import { focusHome, guardLinks } from "./nav.js";

const $ = (id) => document.getElementById(id);
let current = null; // the app's settings: {model, voice, window_browser, window: {using, name, note, choices}}

function setStatus(state) {
  $("status").dataset.state = state;
  $("status").title = { connected: "Connected to ai-browser app", connecting: "Connecting…",
                        refused: "This window wasn't opened by this run of ai-browser app: close it" }[state]
    || "Not connected: is `ai-browser app` running?";
}

function renderWindow() {
  if (!current) return;
  const info = current.window || {};
  const choices = info.choices || [];
  const box = $("window-choices");
  if (box.dataset.choices !== JSON.stringify(choices)) { // rebuilt only when the choices change
    box.textContent = "";
    for (const choice of choices) {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "radio";
      input.name = "window_browser";
      input.value = choice.id;
      input.disabled = !choice.installed;
      input.addEventListener("change", () => {
        if (input.checked) link.send({ type: "settings_set", key: "window_browser", value: choice.id, request: "window" });
      });
      label.append(input, document.createTextNode(`${choice.name}${choice.installed ? "" : " · not installed"}`));
      box.append(label);
    }
    box.dataset.choices = JSON.stringify(choices);
  }
  for (const input of box.querySelectorAll("input")) input.checked = input.value === current.window_browser;
  $("window-using").textContent = info.name
    ? `This window: ${info.name}. A change applies the next time AI Browser starts.` : "";
  $("window-note").textContent = info.note || "";
  $("window-note").hidden = !info.note;
}

function handle(message) {
  if (message.type === "snapshot") {
    current = message.settings || null;
    renderWindow();
  } else if (message.type === "settings") {
    current = message;
    $("window-error").textContent = "";
    renderWindow();
  } else if (message.type === "error" && message.request === "window") {
    $("window-error").textContent = message.text || "";
    renderWindow(); // the saved choice stays checked
  }
}

const link = connect({ view: "settings", onMessage: handle, onState: setStatus });
guardLinks(link);
$("home-link").addEventListener("click", () => focusHome());
```

In `src/ai_browser/app/ui/home.html`, replace the Mission Control button

```html
  <button id="mission" class="ghost" title="Your agents at work in a 3D room, and the Brain that talks back">Mission
    Control</button>
```

with the two buttons in one row:

```html
  <div class="header-buttons">
    <button id="settings" class="ghost" type="button" title="Which browser draws this window">Settings</button>
    <button id="mission" class="ghost" title="Your agents at work in a 3D room, and the Brain that talks back">Mission
      Control</button>
  </div>
```

In `src/ai_browser/app/ui/home.js`, after the `$("mission")` listener, add:

```js
$("settings").addEventListener("click", () => openWindow("/settings", ...WINDOWS["/settings"]));
```

Append to `src/ai_browser/app/ui/home.css`:

```css
.header-buttons { display: flex; gap: 4px; }
.settings { max-width: 720px; }
.settings .choices { display: flex; flex-direction: column; gap: 6px; margin: 8px 0; }
.settings .choices label { display: flex; align-items: center; gap: 8px; }
.settings .choices label:has(input:disabled) { color: var(--muted); }
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_home.py tests/test_ui_static.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/ui/settings.html src/ai_browser/app/ui/settings.js src/ai_browser/app/ui/home.html \
  src/ai_browser/app/ui/home.js src/ai_browser/app/ui/home.css tests/test_home.py tests/test_ui_static.py
git commit -m "feat(ui): a Settings window: which browser draws AI Browser's window"
```

### Task 16: AI Home's words and title in the window; the microphone's and the browser's names

**Files:**
- Modify: `src/ai_browser/app/ui/home.html` (the hint, the empty list), `src/ai_browser/app/ui/home.js`
  (`renderCounts`, the empty list)
- Modify: `src/ai_browser/app/ui/talk.js` (`browserName`, `micProblem`)
- Modify: `tests/test_talk.py` (the blocked-microphone sentence)
- Test: `tests/test_home.py`, `tests/test_talk.py`

**Interfaces:**
- Produces:
  - the window's title is "(n) AI Home" while n agents work, and "AI Home" otherwise; `navigator.setAppBadge(n)` and
    `clearAppBadge()` are called inside try/catch;
  - `browserName(nav)` answers "Microsoft Edge", "Brave" or "Google Chrome";
  - the blocked-microphone line names `location.host`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_home.py`:

```python
@CHROME
async def test_ai_homes_words_for_the_window(home):
    js, _ = home
    assert await js("document.querySelector('.new-task .grow').textContent") == (
        "Or type ai and a space in Brave's address bar")
    assert await until(js, "document.querySelector('#agents .empty')?.textContent === "
                           "'No agents yet. Start a task above.'")


@CHROME
async def test_the_title_counts_the_working_agents(home):
    js, stack = home
    stack["script"].write_text(json.dumps([EVENTS[0], {"sleep": 30}]), encoding="utf-8")  # it stays at work
    agent = await stack["server"].agents.create("keep working")
    assert await until(js, "document.title === '(1) AI Home'")
    await stack["server"].agents.stop(agent.id)
    assert await until(js, "document.title === 'AI Home'")
```

In `tests/test_talk.py::test_microphone_problems_become_plain_words`, the `blocked` sentence becomes:

```python
    blocked = ("The microphone is blocked for AI Browser. Open Google Chrome's Settings → Privacy and security → Site "
               f"settings → Microphone, and allow {stack['url'].removeprefix('http://')}.")
```

and append to `tests/test_talk.py`:

```python
@CHROME
async def test_the_browser_is_named_from_its_brands(stack):
    js = await open_with(stack)
    names = await js("import('/talk.js').then(({ browserName }) => [[{brand: 'Microsoft Edge'}, {brand: 'Chromium'}],"
                     " [{brand: 'Brave'}], [{brand: 'Google Chrome'}], []]"
                     ".map((brands) => browserName({ userAgentData: { brands } })))")
    assert names == ["Microsoft Edge", "Brave", "Google Chrome", "Google Chrome"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_home.py tests/test_talk.py -q -p no:randomly -k "words_for_the_window or title_counts or microphone_problems or named_from_its_brands"`

Expected: FAIL:
- the hint still says "in the address bar";
- the empty list mentions the chat beside the page;
- the title never counts;
- the blocked line says "allow AI Browser";
- Edge is named "Google Chrome".

- [ ] **Step 3: The window's words**

In `src/ai_browser/app/ui/home.html`:
- `<span class="muted grow">Or type <kbd>ai</kbd> and a space in the address bar</span>` becomes
  `<span class="muted grow">Or type <kbd>ai</kbd> and a space in Brave's address bar</span>`;
- the agents list's placeholder becomes
  `<div id="agents" class="list"><p class="empty">No agents yet. Start a task above.</p></div>`.

In `src/ai_browser/app/ui/home.js`:
- in `renderAgents`, `"No agents yet. Start a task above, or open the chat beside any page."` becomes
  `"No agents yet. Start a task above."`;
- at the end of `renderCounts`, add:

  ```js
    document.title = working ? `(${working}) AI Home` : "AI Home"; // the window's title: there is no toolbar badge
    try {
      if (working) navigator.setAppBadge?.(working)?.catch(() => {});
      else navigator.clearAppBadge?.()?.catch(() => {});
    } catch {
      // not an installed app: the title says it
    }
  ```

In `src/ai_browser/app/ui/talk.js`:
- `browserName` becomes:

  ```js
  export function browserName(nav = navigator) { // the browser this page runs in, for the steps it names
    const brands = (nav.userAgentData?.brands || []).map((entry) => String(entry?.brand || ""));
    if (brands.some((brand) => /brave/i.test(brand))) return "Brave";
    if (brands.some((brand) => /edge/i.test(brand))) return "Microsoft Edge";
    return "Google Chrome";
  }
  ```

- in `micProblem`, the blocked line becomes:

  ```js
        return `The microphone is blocked for AI Browser. Open ${name}'s Settings → Privacy and security → Site `
          + `settings → Microphone, and allow ${location.host}.`; // the browser lists the site by its address
  ```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_home.py tests/test_talk.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/ui/home.html src/ai_browser/app/ui/home.js src/ai_browser/app/ui/talk.js \
  tests/test_home.py tests/test_talk.py
git commit -m "feat(ui): the window's title counts working agents; the keyword's hint names Brave"
```

### Task 17: `ai-browser app` opens the window (`run.py`, `cli.py`, the test windows)

**Files:**
- Modify: `src/ai_browser/app/run.py` (rewritten: the window, its loop, the ending order, the retired choice)
- Modify: `src/ai_browser/app/tabs.py` (`has_pages` goes: its last caller was `run.py`)
- Modify: `src/ai_browser/cli.py` (the `app` command: `--window`, `--browser brave`, no `--headless`)
- Modify: `tests/conftest.py` (`_never_the_users_browsers` drops `AIB_APP_BROWSER`; new `_no_real_window`)
- Create: `tests/fake_window.py`
- Modify: `tests/test_app_run.py` (rewritten), `tests/test_cli.py`
- Test: `tests/test_app_run.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes:
  - `default_launcher`, `WindowError`, `choices` and `WINDOW_CHOICES` (Tasks 1 and 3);
  - `AppServer(…, port_file=…)`, `settings`, `window_info`, `new_launch_code`, `window_seen`, `window_count` and
    `allow_watcher` (Tasks 6, 9 and 10);
  - `BraveLink(…, tokens=…, app_origin=…)` (relay and Task 4);
  - the relay's `write_link(home, url, token, cdp, browser_dir)`, `SWITCH` and `connect_brave("start")`.
- Produces (`ai_browser.app.run`):
  - `run_app(home, model="sonnet", claude=None, ready=None, stop=None, out=print, browser=None,
    window_browser=None, launcher=None) -> int`. `launcher(setting)` returns an object with `id`, `name`, `note`,
    `launch(url)` and `close() -> str`, each sync or async. `ready(url, window)` is called once the first window
    socket is in;
  - `WINDOW_START_WAIT = 60`, `WINDOW_GRACE = 5` and `POLL = 0.25`;
  - `NO_WINDOW` and `RETIRED_APP`;
  - `BROWSERS = ("brave",)`;
  - `app_browser(choice=None) -> "brave"`, which raises `ValueError(RETIRED_APP)` for `app`;
  - `ready_text(system=None)` and `brave_text(folder, system=None)`, which gains step 4;
  - `default_launcher`, a module global, so the test fixture replaces it.
- Produces (tests):
  - `tests/fake_window.py`:
    - `FakeWindow(cdp, note="", close_note="")`, with `.urls`, `.targets`, `.closed`, `.on_close` and
      `page(index=0) -> js`;
    - `SocketWindow(servers, note="", close_note="")`, with `.urls` and `.closed`;
  - conftest's autouse `_no_real_window`.

- [ ] **Step 1: Write the failing tests**

Create `tests/fake_window.py`:

```python
"""Stand-ins for AI Browser's window in run_app's tests: AppWindow's surface (id, name, note, launch(url) and
close() -> str). FakeWindow opens the start address in a test's throwaway headless Chrome, the way the real window
opens it. SocketWindow opens no browser at all, only a socket with the window's cookie, as AI Home's page would."""

from __future__ import annotations

import contextlib
import json

from ai_browser.cdp import CDPError
from ui_socket import ui_socket


class FakeWindow:
    id, name = "chrome", "Google Chrome"

    def __init__(self, cdp, note: str = "", close_note: str = ""):
        self.cdp, self.note, self.close_note = cdp, note, close_note
        self.urls: list[str] = []
        self.targets: list[str] = []
        self.closed = False
        self.on_close = None  # a test's recorder, called first

    async def launch(self, url: str) -> None:
        self.urls.append(url)
        self.targets.append((await self.cdp.send("Target.createTarget", {"url": url}))["targetId"])

    async def close(self) -> str:
        if self.on_close is not None:
            self.on_close()
        for target in self.targets:
            with contextlib.suppress(CDPError):
                await self.cdp.send("Target.closeTarget", {"targetId": target})
        self.closed = True
        return self.close_note

    async def page(self, index: int = 0):
        """js(expression) in the window's page (its index-th launch), with .cdp and .session for click_as_user."""
        session = (await self.cdp.send("Target.attachToTarget", {"targetId": self.targets[index],
                                                                  "flatten": True}))["sessionId"]

        async def js(expression):
            result = await self.cdp.send("Runtime.evaluate", {"expression": expression, "returnByValue": True,
                                                              "awaitPromise": True}, session_id=session)
            return result.get("result", {}).get("value")

        js.cdp, js.session = self.cdp, session
        return js


class SocketWindow:
    id, name = "chrome", "Google Chrome"

    def __init__(self, servers: list, note: str = "", close_note: str = ""):
        self.servers, self.note, self.close_note = servers, note, close_note  # servers: the `servers` fixture's list
        self.ws = None
        self.urls: list[str] = []
        self.closed = False

    async def launch(self, url: str) -> None:
        self.urls.append(url)
        server = self.servers[-1]
        self.ws = await ui_socket(server, server.url)
        await self.ws.send(json.dumps({"type": "hello", "view": "home"}))

    async def close(self) -> str:
        self.closed = True
        if self.ws is not None:
            await self.ws.close()
        return self.close_note
```

Replace `tests/test_app_run.py` whole with the file below. It also carries the relay's run tests, rewritten on the new
windows:
- its wiring test becomes `test_brave_the_relay_and_the_windows_origin_are_wired`;
- its switch-text test is kept as `test_the_switch_text_says_once_per_run`;
- its ending-order test becomes `test_the_window_closes_first_and_the_relay_last`.

If the merged file has another test that this file lacks, move it over the same way: `launcher=` with a
`SocketWindow`, no `headless`, and `ui_socket` for any socket.

```python
"""`ai-browser app`: the server, the watcher's folder, BraveLink and AI Browser's window together. FakeWindow stands in
for the window (its start address opens in a throwaway headless Chrome, as the real window opens it: the one-time
code, then the cookie); SocketWindow opens no browser, only a socket with the window's cookie. The app ends once the
last window's socket has been gone WINDOW_GRACE seconds, or when `stop` is set."""

import asyncio
import json
import os
import socket
import time
from pathlib import Path

import httpx
import pytest

from ai_browser.chrome import chrome_binary
from conftest import file_mode
from fake_window import FakeWindow, SocketWindow
from test_home import click_as_user, page_js, until, wait_targets
from ui_socket import ui_socket

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


def quiet(*args):
    pass


def port_free(url) -> bool:
    with socket.socket() as probe:  # closed connections may linger in TIME_WAIT
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", int(url.rsplit(":", 1)[1])))
        except OSError:
            return False
    return True


@pytest.fixture
async def window(throwaway_chrome):
    """A FakeWindow on a throwaway headless Chrome."""
    from ai_browser.cdp import CDP
    from ai_browser.chrome import find_ws_url

    cdp = await CDP.connect(find_ws_url(throwaway_chrome, timeout=20))
    yield FakeWindow(cdp)
    await cdp.close()


@pytest.fixture
def servers(monkeypatch):
    """Every AppServer run_app makes, for the tests that look inside it."""
    from ai_browser.app import run
    from ai_browser.app.server import AppServer

    made = []

    class Recording(AppServer):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            made.append(self)

    monkeypatch.setattr(run, "AppServer", Recording)
    return made


@CHROME
async def test_it_opens_the_window_and_ends_when_the_window_closes(fake_claude, tmp_path, window, monkeypatch,
                                                                   servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    monkeypatch.setattr(run, "WINDOW_GRACE", 1)
    seen, asked = {}, []

    async def ready(url, opened):
        seen["url"], seen["opened"] = url, opened
        async with httpx.AsyncClient() as client:
            seen["health"] = (await client.get(url + "/health")).json()
        page = await window.page()
        seen["home"] = await until(page, "location.pathname === '/home' && "
                                         "document.getElementById('status').dataset.state === 'connected'")
        await window.cdp.send("Target.closeTarget", {"targetId": window.targets[0]})  # the user closes the window
        seen["closed_at"] = time.monotonic()

    def launcher(setting):
        asked.append(setting)
        return window

    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, ready=ready, out=quiet,
                                              launcher=launcher), 60)
    assert code == 0 and seen["health"] == {"ok": True} and seen["home"] and seen["opened"] is window
    assert time.monotonic() - seen["closed_at"] < run.WINDOW_GRACE + 2
    assert asked == ["auto"] and window.urls[0].startswith(seen["url"] + "/open?code=") and window.closed
    assert servers[0].window_seen and not (tmp_path / "home" / "app" / "extension").exists()
    assert port_free(seen["url"])


@CHROME
async def test_a_reload_doesnt_end_it(fake_claude, tmp_path, window, monkeypatch, servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    monkeypatch.setattr(run, "WINDOW_GRACE", 1)
    stop, seen, jobs = asyncio.Event(), {}, []

    async def check(page):
        await page("location.reload(); true")
        await asyncio.sleep(2.5)  # more than twice the grace
        seen["running"], seen["windows"] = not running.done(), servers[0].window_count
        stop.set()

    async def ready(url, opened):
        page = await window.page()
        assert await until(page, "document.getElementById('status').dataset.state === 'connected'")
        jobs.append(asyncio.create_task(check(page)))

    running = asyncio.create_task(run.run_app(tmp_path / "home", claude=runner, ready=ready, stop=stop, out=quiet,
                                              launcher=lambda setting: window))
    assert await asyncio.wait_for(running, 60) == 0 and seen["running"] and seen["windows"] == 1


@CHROME
async def test_a_popup_keeps_it_alive(fake_claude, tmp_path, window, monkeypatch, servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    monkeypatch.setattr(run, "WINDOW_GRACE", 1)
    seen, jobs = {}, []

    async def check(page):
        await click_as_user(page, "#mission")  # Mission Control opens in a window of its own
        [mission] = await wait_targets(window.cdp, "/mission")
        assert await until(await page_js(window.cdp, mission),
                           "document.getElementById('status')?.dataset.state === 'connected'")
        await window.cdp.send("Target.closeTarget", {"targetId": window.targets[0]})  # the main window closes
        await asyncio.sleep(2.5)
        seen["alive"] = not running.done()
        await window.cdp.send("Target.closeTarget", {"targetId": mission})  # then the last one
        seen["closed_at"] = time.monotonic()

    async def ready(url, opened):
        page = await window.page()
        assert await until(page, "document.getElementById('status').dataset.state === 'connected'")
        jobs.append(asyncio.create_task(check(page)))

    running = asyncio.create_task(run.run_app(tmp_path / "home", claude=runner, ready=ready, out=quiet,
                                              launcher=lambda setting: window))
    assert await asyncio.wait_for(running, 60) == 0 and seen["alive"]
    assert time.monotonic() - seen["closed_at"] < run.WINDOW_GRACE + 2


class Nothing:
    """A window whose page never connects (its browser started, and nothing else happened)."""
    id, name, note = "chrome", "Google Chrome", ""

    def __init__(self):
        self.launched, self.closed = [], False

    def launch(self, url):
        self.launched.append(url)

    def close(self):
        self.closed = True
        return ""


async def test_a_window_that_never_connects_ends_the_start(fake_claude, tmp_path, monkeypatch):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    monkeypatch.setattr(run, "WINDOW_START_WAIT", 1)
    nothing, lines = Nothing(), []
    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, out=lines.append,
                                              launcher=lambda setting: nothing), 30)
    assert code == 1 and nothing.launched and nothing.closed
    assert ("AI Browser's window didn't open: Google Chrome started, but the page never connected. Try again, or pick "
            "another browser with `ai-browser app --window brave`") in lines


async def test_stop_before_the_window_connects_still_closes_it(fake_claude, tmp_path):  # Review Focus 1
    from ai_browser.app import run

    runner, _, _ = fake_claude
    nothing, lines, stop = Nothing(), [], asyncio.Event()
    asyncio.get_running_loop().call_later(1, stop.set)  # Ctrl-C while the window is still opening
    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, stop=stop, out=lines.append,
                                              launcher=lambda setting: nothing), 30)
    assert code == 0 and nothing.launched and nothing.closed
    assert not any("didn't open" in line for line in lines)


async def test_no_browser_for_the_window_is_said_plainly(fake_claude, tmp_path):
    from ai_browser.app import run
    from ai_browser.app.window import NO_BROWSER, WindowError

    runner, _, _ = fake_claude
    lines = []

    def launcher(setting):
        raise WindowError(NO_BROWSER)

    assert await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, out=lines.append,
                                              launcher=launcher), 30) == 1
    assert f"error: {NO_BROWSER}" in lines and not (tmp_path / "home" / "app" / "link.json").exists()


async def test_the_setting_picks_the_window_and_window_overrides_it_once(fake_claude, tmp_path):
    from ai_browser.app import run
    from ai_browser.app.window import WindowError
    from ai_browser.settings import Settings, read_settings

    runner, _, _ = fake_claude
    home, asked = tmp_path / "home", []
    Settings(home).set("window_browser", "brave")

    def launcher(setting):
        asked.append(setting)
        raise WindowError("no window in this test")

    assert await run.run_app(home, claude=runner, out=quiet, launcher=launcher) == 1
    assert await run.run_app(home, claude=runner, out=quiet, launcher=launcher, window_browser="chrome") == 1
    assert asked == ["brave", "chrome"] and read_settings(home)["window_browser"] == "brave"  # --window saves nothing
    lines = []
    assert await run.run_app(home, out=lines.append, window_browser="firefox", launcher=launcher) == 1
    assert lines == ["error: --window must be auto, chrome, brave or edge, not 'firefox'"]


async def test_the_window_notes_are_printed(fake_claude, tmp_path, servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    note = "Brave isn't installed: the window uses Google Chrome. Change it in Settings."
    handed = "AI Browser's window was opened by a browser already running on its profile: quit it yourself (⌘Q)"
    window, lines, stop = SocketWindow(servers, note=note, close_note=handed), [], asyncio.Event()
    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, ready=lambda url, opened: stop.set(),
                                              stop=stop, out=lines.append, launcher=lambda setting: window), 60)
    assert code == 0 and note in lines and lines[-1] == handed and window.closed
    assert servers[0].window_info["using"] == "chrome" and servers[0].window_info["note"] == note


async def test_the_retired_ai_browser_choice_is_refused(tmp_path, monkeypatch):
    from ai_browser.app.run import RETIRED_APP, run_app

    launched = []
    for browser, env in (("app", None), (" APP ", None), (None, "app")):
        if env:
            monkeypatch.setenv("AIB_APP_BROWSER", env)
        lines = []
        assert await run_app(tmp_path / "home", browser=browser, out=lines.append, launcher=launched.append) == 1
        assert lines == [f"error: {RETIRED_APP}"]
    assert launched == [] and RETIRED_APP == (
        "AI Browser's own Chrome is gone: agents browse in your browser (Brave or Chrome). Drop --browser app (and "
        "AIB_APP_BROWSER).")


def test_agents_always_browse_in_the_users_browser(tmp_path, monkeypatch):
    from ai_browser.app.run import RETIRED_APP, app_browser, brave_env

    monkeypatch.delenv("AIB_APP_BROWSER", raising=False)
    monkeypatch.setenv("AIB_CHROME_DIR", str(tmp_path / "missing"))
    assert app_browser() == "brave"  # no browser folder: still the user's browser, never AI Browser's own
    assert app_browser(" Brave ") == "brave"
    with pytest.raises(ValueError) as refused:
        app_browser("app")
    assert str(refused.value) == RETIRED_APP
    with pytest.raises(ValueError, match="--browser must be brave, not 'firefox'"):
        app_browser("firefox")
    assert brave_env(tmp_path) == {"AIB_BROWSER": "chrome", "AIB_CHROME_DIR": str(tmp_path)}


async def test_a_bad_browser_choice_is_refused(tmp_path):
    from ai_browser.app.run import run_app

    lines = []
    assert await run_app(tmp_path / "home", browser="firefox", out=lines.append) == 1
    assert lines == ["error: --browser must be brave, not 'firefox'"]


async def test_brave_the_relay_and_the_windows_origin_are_wired(fake_claude, tmp_path, monkeypatch, servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    folder.mkdir(parents=True)  # Brave is installed; its switch is off
    monkeypatch.setenv("AIB_CHROME_DIR", str(folder))
    home, lines, seen, stop = tmp_path / "home", [], {}, asyncio.Event()

    async def ready(url, opened):
        link = home / "app" / "link.json"
        seen["mode"], seen["link"], seen["url"] = file_mode(link), json.loads(link.read_text(encoding="utf-8")), url
        seen["env"] = dict(servers[0].agents.env)
        async with ui_socket(servers[0], url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "home"}))
            seen["browser"] = json.loads(await asyncio.wait_for(ws.recv(), 10))["browser"]
            await ws.send(json.dumps({"type": "new_task", "text": "look around", "request": "r"}))
            while json.loads(await asyncio.wait_for(ws.recv(), 10))["type"] != "created":
                pass
        mcp = home / "app" / "agents" / "a1" / "mcp.json"
        for _ in range(100):
            if mcp.exists():
                break
            await asyncio.sleep(0.1)
        seen["agent_env"] = json.loads(mcp.read_text(encoding="utf-8"))["mcpServers"]["ai-browser"]["env"]
        stop.set()

    code = await asyncio.wait_for(run.run_app(home, claude=runner, ready=ready, stop=stop, out=lines.append,
                                              launcher=lambda setting: SocketWindow(servers)), 60)
    url = seen["url"]
    cdp = url.replace("http://", "ws://", 1) + "/cdp"
    assert code == 0 and seen["mode"] in (0o600, None)
    assert seen["link"]["events"] == url + "/agent-events" and seen["link"]["pid"] == os.getpid()
    assert seen["link"]["cdp"] == cdp and seen["link"]["browser_dir"] == str(folder)
    assert seen["browser"] == {"kind": "brave", "name": "Brave", "state": "off", "groups": "no_watcher"}
    env = seen["env"]
    assert (env["AIB_APP_ORIGIN"], env["AIB_APP_CDP"], env["AIB_BROWSER"], env["AIB_CHROME_DIR"]) == (
        url, cdp, "chrome", str(folder))
    assert not {"AIB_APP_PROFILE", "AIB_APP_EXTENSION", "AIB_APP_AGENT_TOKEN"} & set(env)  # each agent has its own
    assert seen["agent_env"]["AIB_APP_ORIGIN"] == url and seen["agent_env"]["AIB_APP_AGENT_TOKEN"]
    printed = "\n".join(lines)
    assert "brave://inspect/#remote-debugging" in printed and "asks once each time AI Browser starts" in printed
    assert not (home / "app" / "link.json").exists()  # removed at exit


def test_the_switch_text_says_once_per_run():
    from ai_browser.app.run import SWITCH

    text = " ".join(SWITCH.split())
    assert "asks once each time AI Browser starts" in text and "it isn't AI Browser" in text
    assert "each agent first uses the browser" not in text


async def test_the_window_closes_first_and_the_relay_last(fake_claude, tmp_path, monkeypatch, servers):
    from ai_browser.app import run
    from ai_browser.app.bravelink import BraveLink
    from ai_browser.app.server import AppServer

    runner, _, _ = fake_claude
    order, stop = [], asyncio.Event()
    window = SocketWindow(servers)
    real_close, real_unlink = window.close, run.platforms.unlink

    async def close():
        order.append("window")
        return await real_close()

    def unlink(path, missing_ok=False):
        if Path(path).name == "link.json":
            order.append("link")
        return real_unlink(path, missing_ok=missing_ok)

    async def server_stop(self, original=AppServer.stop):
        order.append("server")
        await original(self)

    async def brave_close(self, original=BraveLink.close):
        order.append("brave")
        await original(self)

    window.close = close
    monkeypatch.setattr(run.platforms, "unlink", unlink)
    monkeypatch.setattr(AppServer, "stop", server_stop)
    monkeypatch.setattr(BraveLink, "close", brave_close)
    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, ready=lambda url, opened: stop.set(),
                                              stop=stop, out=quiet, launcher=lambda setting: window), 60)
    assert code == 0 and order == ["window", "link", "server", "brave"]  # no agent sees its browser vanish first


async def test_a_second_run_changes_nothing_for_the_running_one(fake_claude, tmp_path, servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    home, seen, stop = tmp_path / "home", {}, asyncio.Event()

    def files():
        return {name: (home / "app" / name).read_bytes() for name in ("link.json", "port")} | {
            "watcher": (home / "app" / "watcher" / "config.json").read_bytes()}

    async def ready(url, opened):
        before, lines = files(), []
        seen["code"] = await run.run_app(home, claude=runner, out=lines.append,
                                         launcher=lambda setting: pytest.fail("a second window"))
        seen["lines"], seen["unchanged"] = lines, files() == before
        stop.set()

    code = await asyncio.wait_for(run.run_app(home, claude=runner, ready=ready, stop=stop, out=quiet,
                                              launcher=lambda setting: SocketWindow(servers)), 60)
    assert code == 0 and seen["code"] == 1 and seen["unchanged"]
    assert any(line.startswith("error: AI Browser is already running: its window is open (look for it in")
               for line in seen["lines"])


async def test_first_start_shows_the_watchers_steps_once(fake_claude, tmp_path, monkeypatch, servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    shown, lines, home = [], [], tmp_path / "home"
    monkeypatch.setattr(run, "reveal", shown.append)
    for _ in range(2):
        stop = asyncio.Event()
        code = await asyncio.wait_for(run.run_app(home, claude=runner, ready=lambda url, opened: stop.set(),
                                                  stop=stop, out=lines.append,
                                                  launcher=lambda setting: SocketWindow(servers)), 60)
        assert code == 0
    watcher = os.path.realpath(home / "app" / "watcher")
    printed = "\n".join(lines)
    assert shown == [watcher]  # the folder window once; the printed steps until the watcher is set up
    assert printed.count("brave://extensions") == 2 and "Type ai and a space in Brave's address bar" in printed


async def test_the_brain_survives_a_restart(fake_claude, tmp_path, servers):
    from ai_browser.app import run
    from ai_browser.brain.store import BrainStore, Item

    runner, _, _ = fake_claude
    home, seen, stop = tmp_path / "home", {}, asyncio.Event()
    BrainStore(home).put(Item(id="gmail:t1", site="gmail", raw_id="t1", sender="Maria", subject="Launch",
                              kind="needs_reply", summary="Move the launch?"))

    async def ready(url, opened):
        async with ui_socket(servers[0], url) as ws:
            await ws.send(json.dumps({"type": "brain"}))
            while "snapshot" not in seen:
                message = json.loads(await asyncio.wait_for(ws.recv(), 10))
                if message["type"] == "brain_snapshot":
                    seen["snapshot"] = message
        stop.set()

    code = await asyncio.wait_for(run.run_app(home, claude=runner, ready=ready, stop=stop, out=quiet,
                                              launcher=lambda setting: SocketWindow(servers)), 60)
    assert code == 0 and [item["id"] for item in seen["snapshot"]["items"]] == ["gmail:t1"]


async def test_scheduled_workflows_tick_while_the_app_runs(fake_claude, tmp_path, monkeypatch, servers):
    from ai_browser.app import run
    from ai_browser.brain import workflows as workflow_module
    from ai_browser.brain.workflows import WorkflowStore
    from test_bridge import EVENTS

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    home, seen, stop = tmp_path / "home", {}, asyncio.Event()
    WorkflowStore(home).save({"name": "Hourly check", "instructions": "Check the sites and tell me what changed",
                              "trigger": "schedule", "schedule": "every 15m"})
    clock = [1_000_000.0]
    monkeypatch.setattr(workflow_module, "_now", lambda: clock[0])
    monkeypatch.setattr(run, "TICK", 0.1)

    def users():
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if '"type": "user"' in line]

    async def ready(url, opened):
        await asyncio.sleep(0.5)  # the first tick starts the schedule's clock: nothing missed is caught up
        assert users() == []
        clock[0] += 16 * 60
        for _ in range(100):
            if users():
                break
            await asyncio.sleep(0.1)
        seen["users"] = users()
        stop.set()

    code = await asyncio.wait_for(run.run_app(home, claude=runner, ready=ready, stop=stop, out=quiet,
                                              launcher=lambda setting: SocketWindow(servers)), 60)
    assert code == 0 and seen["users"][0]["message"]["content"].startswith("Check the sites and tell me what changed")


async def test_the_app_can_hear_with_its_models_folder(fake_claude, tmp_path, servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    seen, stop = {}, asyncio.Event()

    async def ready(url, opened):
        async with ui_socket(servers[0], url) as ws:
            await ws.send(json.dumps({"type": "hearing"}))
            while (message := json.loads(await asyncio.wait_for(ws.recv(), 10)))["type"] != "hearing_status":
                pass
            seen["status"] = message
        stop.set()

    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, ready=ready, stop=stop, out=quiet,
                                              launcher=lambda setting: SocketWindow(servers)), 60)
    status = seen["status"]
    assert code == 0 and status["folder"] == str(tmp_path / "home" / "models" / "faster-whisper-base.en")
    assert status["size_bytes"] == 147_769_510 and status["model"] == "Whisper base.en"
    assert status["state"] in ("no_engine", "no_model")  # never ready by itself: the model comes only on Download


def test_the_terminal_texts_name_no_extension_and_no_panel():
    from ai_browser.app.run import brave_text, ready_text

    expected = ("AI Browser is open in its own window: AI Home shows every agent, tab and skill.\n"
                "With the watcher in Brave, type ai and a space in Brave's address bar to start a task from there.\n"
                "Close the window, or press Ctrl-C here, to stop.")
    assert ready_text("darwin") == ready_text("win32") == expected
    for system, folder in (("darwin", "/x/watcher"), ("win32", "C:\\Users\\me\\.ai-browser\\app\\watcher")):
        for text in (ready_text(system), brave_text(folder, system)):
            assert "⌘⇧Y" not in text and "Ctrl+Shift+Y" not in text and "chrome://extensions" not in text
            assert "Pin the AI Browser icon" not in text
        assert "4. Type ai and a space in Brave's address bar to start a task" in brave_text(folder, system)
    windows = brave_text("C:\\Users\\me\\.ai-browser\\app\\watcher", "win32")
    assert "address bar at the top of the folder window" in windows and "⌘" not in windows
    assert "⌘⇧G" in brave_text("/x/watcher", "darwin")
```

Append to `tests/test_cli.py`:

```python
def test_app_help_offers_the_window_and_brave_only(capsys):
    with pytest.raises(SystemExit) as exited:
        main(["app", "--help"])
    assert exited.value.code == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "--window {auto,chrome,brave,edge}" in out and "--browser {brave}" in out
    assert "--headless" not in out and "side panel" not in out


def test_app_hands_its_choices_to_run_app(monkeypatch):
    import ai_browser.app.run as run

    seen = {}

    async def fake_run_app(home, model="sonnet", **options):
        seen.update(model=model, **options)
        return 0

    monkeypatch.setattr(run, "run_app", fake_run_app)
    assert main(["app", "--model", "haiku", "--window", "brave", "--browser", "brave"]) == 0
    assert seen == {"model": "haiku", "browser": "brave", "window_browser": "brave"}
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_app_run.py tests/test_cli.py -q -p no:randomly -k "not doctor"`

Expected: FAIL. `run_app` takes no `launcher` or `window_browser`, it still launches AI Browser's Chrome, `app` is
still an accepted browser, and `cli.py` has no `--window`.

- [ ] **Step 3: Rewrite `run.py` around the window**

Replace `src/ai_browser/app/run.py` whole with the file below. Two parts of it are the relay's: `SWITCH` and
`write_link`, copied from the relay spec. Keep the merged code's exact words for both. Everything that mentioned AI
Browser's Chrome is gone:
- `setup_text`, `_setup_pages`, `_connected`, `_open`, `EXTENSION_WAIT` and `WINDOW_CHECKS`;
- the `TabWatch` on AI Browser, and the windowless loop.

```python
"""`ai-browser app`: the agents, the app server and AI Browser's window together, until the user is done.

AI Browser's window is an installed browser in --app mode on a profile of the app's own, with no debugging port
(app/window.py). It opens on a one-time code the server swaps for the window's cookie. The app ends when the last of
its windows has been closed for a few seconds (on macOS the browser keeps running with no window, so the windows'
sockets tell), or on Ctrl-C, which closes the window too. Agents browse in the user's own browser through the app's
one connection (the relay); the first start shows the watcher's steps, once."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import os
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from .. import platforms
from ..brain.service import BrainService
from ..brain.skillwriter import SkillWriter
from ..brain.store import BrainStore
from ..brain.tools import ToolsConfig
from ..brain.watcher import prepare_watcher
from ..brain.workflows import WorkflowRunner, WorkflowStore
from ..chrome import inspect_address, own_browser_dir
from ..extension_id import extension_id_for, extension_path
from ..hearing.engine import WhisperEngine
from ..hearing.model import ModelStore
from ..hearing.service import HearingService
from ..syncdir import write_atomic
from .agents import AgentManager
from .bravelink import BraveLink
from .server import AppServer, reveal_folder
from .window import WINDOW_CHOICES, WindowError, choices, default_launcher

TICK = 30  # seconds between two looks at the scheduled workflows
WINDOW_START_WAIT = 60  # seconds for the window's page to connect once its browser has started
WINDOW_GRACE = 5  # seconds with no AI Browser window before the app ends: a reload or a page change is back sooner
POLL = 0.25  # seconds between two looks at the windows' sockets (time.monotonic stands still while the Mac sleeps)
NO_WINDOW = ("AI Browser's window didn't open: {name} started, but the page never connected. Try again, or pick "
             "another browser with `ai-browser app --window brave`")
RETIRED_APP = ("AI Browser's own Chrome is gone: agents browse in your browser (Brave or Chrome). Drop --browser app "
               "(and AIB_APP_BROWSER).")


def _goto(folder: str, system: str | None) -> str:
    return platforms.shortcut(f"press ⌘⇧G, paste {folder} and press Enter",
                              f"click the address bar at the top of the folder window, paste {folder} and press Enter",
                              system)


def ready_text(system: str | None = None) -> str:
    return ("AI Browser is open in its own window: AI Home shows every agent, tab and skill.\n"
            "With the watcher in Brave, type ai and a space in Brave's address bar to start a task from there.\n"
            "Close the window, or press Ctrl-C here, to stop.")


def brave_text(folder: str, system: str | None = None) -> str:
    return f"""The Brain watches your messages (Gmail, Slack, Asana…) in Brave, through a small extension. Once:
  1. In Brave, open brave://extensions and turn on Developer mode (top right).
  2. Drag the "watcher" folder onto that page.
     (Or click Load unpacked, {_goto(folder, system)}.)
  3. Click the watcher's icon to open the Brain, and switch on the sites to watch.
  4. Type ai and a space in Brave's address bar to start a task.
It reads new messages in tabs you have open and never sends anything."""


BROWSERS = ("brave",)
SWITCH = """Agents browse in your {name}, but its remote-debugging switch is off, so nothing reaches it yet. Once:
  1. In {name}, open {inspect}.
  2. Tick "Allow remote debugging for this browser instance".
  3. When {name} asks "Allow remote debugging?", click Allow. AI Browser holds one connection for all its agents
     and Claude Code sessions, so {name} asks once each time AI Browser starts, and again after {name} restarts.
While this switch is on, any program on this computer can reach your {name}, not only AI Browser. That includes the
sites you are signed in to. While AI Browser is connected, a program that can read AI Browser's files can also use
your {name} through it without a new question; AI Home lists everything connected, with Disconnect. Turn the switch
off when agents aren't working: untick the same box. Only click Allow right after you started AI Browser, clicked
Connect, gave an agent a task, asked Claude Code to browse, or opened {name} again while an agent was working. If
{name} asks at any other time, it isn't AI Browser: click Deny, unless you just started another browser tool
yourself.
Once the switch is on, AI Home's browser card has a Connect button."""
reveal = reveal_folder  # a file manager window with the watcher's folder selected (tests replace it)


def _max_agents() -> int:
    try:
        return min(10, max(1, int(os.environ.get("AIB_APP_MAX_AGENTS", "3"))))
    except ValueError:
        return 3


def app_browser(choice: str | None = None) -> str:
    """Where agents browse: always the user's own browser. AI Browser's own Chrome is gone, so "app" (from --browser
    or $AIB_APP_BROWSER) is refused with a plain message, and anything else that names no browser too: never a
    guess."""
    value = (choice or os.environ.get("AIB_APP_BROWSER") or "").strip().lower()
    if value == "app":
        raise ValueError(RETIRED_APP)
    if value and value not in BROWSERS:
        raise ValueError(f"--browser must be brave, not {value!r}")
    return "brave"


def brave_env(folder: Path) -> dict[str, str]:
    """Every agent's engine drives the user's own browser."""
    return {"AIB_BROWSER": "chrome", "AIB_CHROME_DIR": str(folder)}


def write_link(home: Path, url: str, token: str, cdp: str, browser_dir: Path) -> Path:
    """<home>/app/link.json (mode 0600): how Claude Code sessions find this app, its relay and its browser."""
    path = Path(home) / "app" / "link.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps({"events": f"{url}/agent-events", "session_token": token, "pid": os.getpid(), "cdp": cdp,
                       "browser_dir": str(browser_dir)}).encode("utf-8")
    write_atomic(path, data, 0o600)  # holds the session token
    return path


async def run_app(home: Path, model: str = "sonnet", claude: str | Sequence[str] | None = None,
                  ready: Callable | None = None, stop: asyncio.Event | None = None,
                  out: Callable[[str], None] = print, browser: str | None = None, window_browser: str | None = None,
                  launcher: Callable | None = None) -> int:
    """0 once AI Browser's window is closed (or `stop` is set); 1 with a message when it can't start. `launcher` takes
    the window's setting and returns the window (default_launcher; tests pass their own)."""
    home = Path(home)
    try:
        app_browser(browser)
        if window_browser is not None and window_browser not in WINDOW_CHOICES:
            raise ValueError(f"--window must be auto, chrome, brave or edge, not {window_browser!r}")
    except ValueError as exc:
        out(f"error: {exc}")
        return 1
    lock = _lock(home)  # before anything is touched: a second run must not disturb the first one's files
    if lock is None:
        out("error: AI Browser is already running: its window is open (look for it in "
            f"{platforms.shortcut('the Dock', 'the taskbar')})")
        return 1
    try:
        return await _run(home, model, claude, ready, stop or asyncio.Event(), out, window_browser, launcher)
    finally:
        lock.close()


async def _tick(runner: WorkflowRunner) -> None:
    while True:
        await asyncio.sleep(TICK)
        with contextlib.suppress(Exception):  # one workflow that can't start must not stop the others' schedules
            await runner.tick()


def _lock(home: Path):
    """An exclusive lock on <home>/app/lock held for the whole run, or None if another run holds it."""
    folder = home / "app"
    folder.mkdir(parents=True, exist_ok=True)
    return platforms.lock_file(folder / "lock")


async def _call(method, *args):
    """A window's launch or close: a coroutine is awaited (the tests' windows); a plain call runs in a thread, because
    closing waits up to 10 s for the browser to quit."""
    if inspect.iscoroutinefunction(method):
        return await method(*args)
    return await asyncio.to_thread(method, *args)


async def _first_window(server: AppServer, stop: asyncio.Event) -> bool:
    """True once the window's first socket is in; False after WINDOW_START_WAIT, or when `stop` is set first."""
    deadline = time.monotonic() + WINDOW_START_WAIT
    while not server.window_seen:
        if stop.is_set() or time.monotonic() >= deadline:
            return False
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), POLL)
    return True


async def _until_closed(server: AppServer, stop: asyncio.Event) -> None:
    """Until `stop`, or until no window socket has been open for WINDOW_GRACE seconds in a row."""
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


async def _run(home: Path, model: str, claude: str | Sequence[str] | None, ready: Callable | None,
               stop: asyncio.Event, out: Callable[[str], None], window_browser: str | None,
               launcher: Callable | None) -> int:
    agents = AgentManager(home, claude=claude, max_working=_max_agents())
    brain = BrainService(BrainStore(home), agents, claude=claude, agent_model=model)
    workflows = WorkflowStore(home)
    runner = WorkflowRunner(workflows, agents)
    skills = SkillWriter(Path.home() / ".claude" / "skills", claude=claude, cwd=home / "brain" / "calls")
    hearing = HearingService(ModelStore(home / "models"), WhisperEngine())  # talking; the model only on Download
    server = AppServer(home, agents, default_model=model, brain=brain, tools=ToolsConfig(home), workflows=workflows,
                       runner=runner, skill_writer=skills, hearing=hearing, port_file=home / "app" / "port")
    server.out = out
    window = ticker = brave = link_file = None
    try:
        try:
            url = await server.start()
        except RuntimeError as exc:
            out(f"error: {exc}")
            return 1
        watcher, server.watcher_build = prepare_watcher(home, url, server.token)  # Brave's watcher, updated
        server.watcher_folder = extension_path(watcher)
        watcher_id = extension_id_for(watcher)
        server.allow_watcher(f"chrome-extension://{watcher_id}")
        own = own_browser_dir()  # the user's own browser (Brave first): where agents browse
        cdp = url.replace("http://", "ws://", 1) + "/cdp"
        brave = BraveLink(own, watcher_id=watcher_id, tokens=server.tokens, app_origin=url)
        agents.env.update({"AIB_APP_EVENTS": f"{url}/agent-events", "AIB_APP_CDP": cdp, "AIB_APP_ORIGIN": url,
                           **brave_env(own)})
        server.attach_brave(brave)
        agents.close_tabs = brave.close_targets
        link_file = write_link(home, url, server.session_token, cdp, own)
        await brave.start()  # looks at the switch; it never connects by itself
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
        if not brain.store.watcher_seen:  # the Brain's watcher isn't in Brave yet: its steps, until it is
            out(brave_text(server.watcher_folder))
            if not brain.store.watcher_prompted:  # one folder window, once
                brain.store.set_watcher_prompted()
                reveal(server.watcher_folder)
        if brave.state == "off":
            out(SWITCH.format(name=brave.name, inspect=inspect_address(brave.folder)))
        else:
            server.connect_brave("start")  # once, as the app starts: Brave asks "Allow remote debugging?"
        ticker = asyncio.create_task(_tick(runner))  # scheduled workflows run while the app does
        if ready is not None:
            result = ready(url, window)
            if inspect.isawaitable(result):
                await result
        await _until_closed(server, stop)
        return 0
    finally:
        if ticker is not None:
            ticker.cancel()
        if window is not None:  # first, so the window goes at once (after a hand-off it ends nothing, and says so)
            with contextlib.suppress(Exception):
                note = await _call(window.close)
                if note:
                    out(note)
        if link_file is not None:
            with contextlib.suppress(OSError):
                platforms.unlink(link_file, missing_ok=True)
        await server.stop()  # every agent's Claude Code process ends, and the relay's clients with them
        if brave is not None:
            await brave.close()  # the one connection to Brave closes last; the agents' tabs and groups stay there
```

In `src/ai_browser/app/tabs.py`, delete `has_pages`. Nothing in the product calls it any more. If a test still
calls it (`grep -rn has_pages tests/`; watcher-safety's tab-list test may), drop that one assertion.

In `src/ai_browser/cli.py`:
1. Replace the four `app` lines (the parser, `--model`, `--browser` and `--headless`) with:

   ```python
       app = commands.add_parser("app", help="open AI Browser in its own window: AI Home, Mission Control and the Brain")
       app.add_argument("--model", choices=["sonnet", "opus", "haiku"], default="sonnet",
                        help="Claude model for new agents until you pick one in AI Home (default: sonnet)")
       app.add_argument("--browser", default=None, metavar="{brave}",
                        help="where agents browse: your Brave (the only choice: AI Browser's own Chrome is gone)")
       app.add_argument("--window", choices=["auto", "chrome", "brave", "edge"], default=None,
                        help="which browser draws AI Browser's window, for this run only (default: the Settings "
                             "choice)")
   ```

   `--browser` takes any value, so `--browser app` reaches `run_app` and gets its plain message there, instead of
   argparse's.
2. Replace `return asyncio.run(run_app(home(), args.model, args.headless, browser=args.browser))` with:

   ```python
               return asyncio.run(run_app(home(), args.model, browser=args.browser, window_browser=args.window))
   ```

In `tests/conftest.py`:
- in `_never_the_users_browsers`, delete `monkeypatch.setenv("AIB_APP_BROWSER", "app")`. In its docstring,
  "every test runs with the sandbox and the app with AI Browser" becomes "every test runs with the sandbox, and
  `ai-browser app` with BraveLink off (no browser folder)";
- add the fixture:

  ```python
  @pytest.fixture(autouse=True)
  def _no_real_window(monkeypatch):
      """No test opens AI Browser's real window: run_app's tests pass a launcher (tests/fake_window.py)."""
      import ai_browser.app.run as run
      from ai_browser.app.window import WindowError

      def launcher(home):
          def refuse(setting):
              raise WindowError("tests never open AI Browser's real window: pass launcher=")
          return refuse

      monkeypatch.setattr(run, "default_launcher", launcher)
  ```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_app_run.py -q -p no:randomly`

Expected: PASS.

Run: `uv run pytest tests/test_cli.py tests/test_tabwatch.py tests/test_app_server.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/run.py src/ai_browser/app/tabs.py src/ai_browser/cli.py tests/conftest.py \
  tests/fake_window.py tests/test_app_run.py tests/test_cli.py tests/test_tabwatch.py
git commit -m "feat(app): ai-browser app opens its own window and ends when the last one closes"
```

### Task 18: The server's AI Browser mode retires (the token path is the watcher's only)

**Files:**
- Modify: `src/ai_browser/app/server.py`:
  - `allow_origin` and `_origins` go; `allow_watcher` stands alone;
  - `_socket_kind` loses `"extension"`; `extension_seen` goes;
  - `_mismatch` is worded for the watcher; `_browser_info`; `new_task` with `adopt`; the module docstring.
- Modify: `src/ai_browser/app/ui/home.js` (the browser card's AI Browser branch), `src/ai_browser/app/ui/tablist.js`
  (the "besides AI Home" text)
- Modify: `tests/test_app_server.py`, `tests/test_watcher_rules.py`, `tests/test_tools.py`,
  `tests/test_skillwriter.py`, `tests/test_workflows.py`, `tests/test_watcher.py` and any other test that calls
  `allow_origin` (a mechanical move to `ui_socket` and `allow_watcher`), `tests/test_ui_static.py`
- Test: `tests/test_app_server.py`, `tests/test_ui_static.py`

**Interfaces:**
- Consumes: `ui_socket` (Task 9), `refused_socket` and `fetch` (`tests/test_app_server.py`, Tasks 6 and 9).
- Produces:
  - a socket opens only two ways: the window's (cookie, Origin, Host), or the watcher's (token and an origin passed
    to `allow_watcher`);
  - `AppServer.allow_origin` and `extension_seen` no longer exist;
  - the mismatch line reads "A watcher connected as <origin>, but the app expected <ids>: please report this";
  - with no BraveLink, `_browser_info()` is `{"kind": "brave", "name": "Brave", "state": "off", "groups":
    self.groups.available()}`;
  - `new_task` with an `adopt` that `_handable` doesn't find is refused, BraveLink or not.

- [ ] **Step 1: Write the failing tests, and move every test socket onto the window's path**

Move the tests' sockets first. Every `connect(socket_url(server, url), origin=ORIGIN)` becomes
`ui_socket(server, url)`. The `chrome-extension://good` sockets in other files become `ui_socket` too.
`allow_origin(X, watcher=True)` becomes `allow_watcher(X)`, and a plain `allow_origin(ORIGIN)` line goes. Run:

```bash
uv run python - <<'PY'
import re
from pathlib import Path


def add_import(text: str) -> str:
    if "from ui_socket import" in text:
        return text if re.search(r"from ui_socket import .*\bui_socket\b", text) else text.replace(
            "from ui_socket import ", "from ui_socket import ui_socket, ", 1)
    lines = text.split("\n")
    anchor = next((i for i, line in enumerate(lines) if line.startswith(("from conftest", "from fake_", "from test_"))),
                  None)
    if anchor is None:
        anchor = next(i for i, line in enumerate(lines) if line.startswith("import pytest")) + 1
    lines.insert(anchor, "from ui_socket import ui_socket")
    return "\n".join(lines)


for path in sorted(Path("tests").glob("*.py")):
    text = path.read_text(encoding="utf-8")
    new = re.sub(r"connect\(socket_url\((\w+), (\w+)\), origin=ORIGIN\)", r"ui_socket(\1, \2)", text)
    new = re.sub(r'connect\((\w+)\.replace\("http", "ws"\) \+ "/ws\?token=" \+ (\w+)\.token,\s*'
                 r'origin="chrome-extension://good"\)', r"ui_socket(\2, \1)", new)
    new = re.sub(r"\n[ \t]*[\w\[\]\"']+\.allow_origin\((?:ORIGIN|\"chrome-extension://good\")\)", "", new)
    new = re.sub(r"\.allow_origin\(([^()]+?), watcher=True\)", r".allow_watcher(\1)", new)
    if new != text:
        if "ui_socket(" in new:
            new = add_import(new)
        path.write_text(new, encoding="utf-8")
        print(path)
PY
grep -n "origin=ORIGIN\|allow_origin(\|chrome-extension://good" tests/*.py
```

Expected from the grep: only lines whose socket is meant to be refused, with an `origin=` variable. For example,
`test_strangers_are_refused` loops over `("wrong", ORIGIN)`: AI Browser's extension origin is now refused even with the
right token, which that test still expects. Fix any other line by hand, by the same rule.

In `tests/test_app_server.py`, replace `test_a_wrong_extension_id_is_reported_not_allowed` with:

```python
async def test_a_wrong_watcher_id_is_reported_not_allowed(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer

    runner, _, _ = fake_claude
    server = AppServer(tmp_path / "home", AgentManager(tmp_path / "home", claude=runner))
    url = await server.start()
    lines = []
    server.out = lines.append
    try:
        # The app is still starting: it hasn't allowed the watcher's computed ID yet, and the watcher (which already
        # has this run's token) may connect first. Refused as always, but that is no mismatch.
        early = connect(socket_url(server, url), origin="chrome-extension://early", proxy=None)
        assert await refused_socket(early) == 4403 and server.origin_mismatch is None and lines == []
        server.allow_watcher(WATCHER)
        assert "mismatch" not in (await fetch("GET", url + "/setup/status")).json()
        wrong = connect(socket_url(server, url, "wrong"), origin="chrome-extension://other", proxy=None)
        assert await refused_socket(wrong) == 4403
        assert server.origin_mismatch is None and lines == []  # a wrong token sets nothing
        for _ in range(2):  # the right token from an origin the app didn't compute: said once
            unexpected = connect(socket_url(server, url), origin="chrome-extension://unexpected", proxy=None)
            assert await refused_socket(unexpected) == 4403  # still refused, never allowed on its own
        assert server.origin_mismatch == "chrome-extension://unexpected"
        assert lines == ["A watcher connected as chrome-extension://unexpected, but the app expected "
                         "chrome-extension://watcher: please report this"]
        assert (await fetch("GET", url + "/setup/status")).json()["mismatch"] == "chrome-extension://unexpected"
    finally:
        await server.stop()


async def test_ai_browsers_extension_path_is_gone(fake_claude, tmp_path):
    from ai_browser.app.server import AppServer

    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        assert not hasattr(AppServer, "allow_origin") and not hasattr(server, "extension_seen")
        for origin in ("chrome-extension://good", url, "https://evil.example"):  # the token alone opens nothing
            assert await refused_socket(connect(socket_url(server, url), origin=origin, proxy=None)) == 4403
    finally:
        await server.stop()


async def test_without_brave_nothing_is_handed_and_the_card_says_off(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        async with ui_socket(server, url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "home"}))
            snapshot = await recv(ws)
            assert snapshot["browser"] == {"kind": "brave", "name": "Brave", "state": "off", "groups": "no_watcher"}
            await ws.send(json.dumps({"type": "new_task", "text": "reply to it", "adopt": "T1", "request": "r1"}))
            error = (await until(ws, lambda message: message["type"] == "error"))[-1]
            assert error["request"] == "r1" and error["text"].startswith("That tab can't be handed over")
        assert server.agents.agents == {}  # no agent, and T1 adopted by nobody
    finally:
        await server.stop()
```

Append to `tests/test_ui_static.py`:

```python
def test_ai_browser_mode_is_gone_from_the_pages():
    assert "Agents browse in AI Browser" not in (UI / "home.js").read_text(encoding="utf-8")
    assert "No tabs open besides AI Home" not in (UI / "tablist.js").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_app_server.py tests/test_ui_static.py -q -p no:randomly -k "watcher_id or extension_path_is_gone or without_brave or mode_is_gone"`

Expected: FAIL:
- the mismatch line still names AI Browser;
- `allow_origin` exists;
- the snapshot's `browser` is `{"kind": "app", …}`;
- `new_task` with `adopt` and no BraveLink starts an agent;
- the pages still hold AI Browser mode's texts.

- [ ] **Step 3: One way in for each of the two roles**

In `src/ai_browser/app/server.py`:

1. Replace the module docstring with:

   ```python
   """The AI Browser app server: AI Home's, Mission Control's and Settings' only way to the agents, and Brave's
   watcher's.

   It listens on 127.0.0.1 only, and every route checks the Host header. AI Browser's pages are served here to its own
   window, which swaps a one-time code for an HttpOnly cookie; a window socket needs that cookie and our exact Origin
   and Host. Brave's watcher connects with its token from its own extension origin. The agents' engines report their
   tabs to /agent-events with tokens of their own, and reach the browser through /cdp. Everything that happens to an
   agent is broadcast to every socket (the watcher gets a trimmed copy); an agent's conversation is sent on request
   (`events`), so a page opened later can draw it whole."""
   ```

2. In `__init__`, delete `self._origins: set[str] = set()` and `self.extension_seen = False …`. Also make the
   comment on `self.token` read `# Brave's watcher (in its config.json)`.
3. Replace `allow_origin` and `allow_watcher` with:

   ```python
       def allow_watcher(self, origin: str) -> None:
           """Brave's watcher's origin (chrome-extension://<id>): the only origin that may connect with the token."""
           self._watcher_origins.add(origin)
   ```

4. Replace `_mismatch` with:

   ```python
       def _mismatch(self, origin: str) -> None:
           """Only a watcher holding our config.json has the token: from an origin we didn't compute, it means an
           extension ID is computed wrong on this computer. The socket is still refused; this says so, once."""
           if origin == self.origin_mismatch:
               return
           self.origin_mismatch = origin
           expected = ", ".join(sorted(self._watcher_origins)) or "?"
           self.out(f"A watcher connected as {origin}, but the app expected {expected}: please report this")
   ```

5. In `_socket_kind`, replace everything after `if origin in self._watcher_origins: return "watcher"` with:

   ```python
           if self._watcher_origins and isinstance(origin, str) and origin.startswith("chrome-extension://"):
               self._mismatch(origin)  # only once the app has allowed its computed ID: before that, no mismatch
           return None
   ```

   Its docstring loses "or, until AI Browser's own extension retires, that extension (the token and its origin)".
6. In `_socket`, delete the two lines `elif kind == "extension":` and `self.extension_seen = True  # …`.
7. Replace `_browser_info` with:

   ```python
       def _browser_info(self) -> dict:
           if self.brave is None:  # no BraveLink attached (a server built alone, in tests): agents can't browse yet
               return {"kind": "brave", "name": "Brave", "state": "off", "groups": self.groups.available()}
           return {"kind": "brave", "name": self.brave.name, "state": self.brave.state,
                   "groups": self.groups.available()}
   ```

   If wave A or the relay added keys to the BraveLink answer, keep them in the second `return`.
8. In the `new_task` branch of `_handle`, replace the two lines

   ```python
               handed = self._handable(adopt) if adopt and self.brave is not None else None
               if adopt and self.brave is not None and handed is None:  # in brave mode: only a tab Brave lists
   ```

   with:

   ```python
               handed = self._handable(adopt) if adopt else None
               if adopt and handed is None:  # only a tab the user's browser lists: never an unchecked target
   ```

   Keep whatever wave A put between these lines and the error it sends.

In `src/ai_browser/app/ui/home.js`, in `renderBrowser`:
- delete the block that begins `if (browser.kind !== "brave") {`, which sets "Agents browse in AI Browser";
- `card.dataset.state = browser.kind === "brave" ? browser.state : "app";` becomes
  `card.dataset.state = browser.state;`.

In `src/ai_browser/app/ui/tablist.js`, the empty-list text loses its AI Browser branch. Find the string
`"No tabs open besides AI Home."`. Today the line is

```js
    root.append(el("p", "empty", brave ? "No web pages open in your browser." : "No tabs open besides AI Home."));
```

and it becomes the brave text alone. Keep the words wave A wrote, for example "No web pages open in this profile."
when a scope is set:

```js
    root.append(el("p", "empty", "No web pages open in your browser."));
```

- [ ] **Step 4: Run them to see them pass**

Run, one file at a time:
- `uv run pytest tests/test_app_server.py -q -p no:randomly`
- `uv run pytest tests/test_watcher_rules.py tests/test_tools.py tests/test_skillwriter.py tests/test_workflows.py -q -p no:randomly`
- `uv run pytest tests/test_watcher.py tests/test_watcher_groups.py -q -p no:randomly`
- `uv run pytest tests/test_home.py tests/test_ui_static.py tests/test_app_run.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -u src/ai_browser/app/server.py src/ai_browser/app/ui/home.js src/ai_browser/app/ui/tablist.js tests/
git commit -m "feat(server): AI Browser's extension path retires; the token is the watcher's only way in"
```

### Task 19: The engine's app mode retires (`AIB_BROWSER=app`, the app's origin in `url_problem`)

**Files:**
- Modify: `src/ai_browser/browser.py` (`url_problem`, `Browser.__init__`, app mode's branches, `NO_TAB`, `_others`)
- Modify: `src/ai_browser/engine.py` (`BROWSER_KINDS`, `BAD_BROWSER`, `RETIRED_BROWSER`, `RECONNECTED`, the app
  branches, `app_origin`)
- Modify: `src/ai_browser/qa/run.py` (`url_problem` with the browser's `app_origin`)
- Delete: `tests/test_appmode.py` (three of its tests move)
- Modify: `tests/test_engine.py`, `tests/test_chrome.py`, `tests/conftest.py` (`PIPE_FIXTURES`)
- Test: `tests/test_engine.py`, `tests/test_chrome.py`

**Interfaces:**
- Consumes: the relay's `engine.py` and `browser.py` (the route, `detached`). Every edit below is found by its text.
- Produces:
  - `url_problem(url, mode, app_origin="")` refuses, in every mode, an address with the app's scheme, host and port:
    "AI Browser's own pages open only in its window";
  - `Browser(cdp, work, cfg, mode="sandbox", placer=None, keep_tabs=False, handed=None, key_prefix="t",
    app_origin="")`, plus the relay's parameters. `hidden_extension` and `front` are gone;
  - `Browser.app_origin`;
  - `engine.BROWSER_KINDS` without `"app"`;
  - `BAD_BROWSER = "AIB_BROWSER must be own, chrome, brave or sandbox"`;
  - `RETIRED_BROWSER = "AIB_BROWSER=app is retired: AI Browser's own Chrome is gone. Use own (your browser) or
    sandbox."`;
  - every `Browser` the engine makes gets `app_origin=os.environ.get("AIB_APP_ORIGIN", "")`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine.py`:

```python
def test_the_apps_own_pages_never_open_in_an_agents_browser():
    from ai_browser.browser import url_problem

    app = "http://127.0.0.1:8792"
    for mode in ("chrome", "sandbox"):
        for url in ("http://127.0.0.1:8792/home", "http://127.0.0.1:8792/setup#switch", "HTTP://127.0.0.1:8792/x"):
            assert url_problem(url, mode, app_origin=app) == "AI Browser's own pages open only in its window", url
    assert url_problem("http://127.0.0.1:8793/home", "chrome", app_origin=app) is None  # another port
    assert url_problem("http://127.0.0.1:8792/home", "chrome") is None  # no app running
    assert url_problem("chrome-extension://abc/options.html", "chrome")  # extension pages: never, as before


async def test_the_retired_ai_browser_mode_is_said_plainly(monkeypatch, tmp_path):
    from ai_browser.engine import RETIRED_BROWSER

    monkeypatch.setenv("AIB_BROWSER", "app")

    async def nothing(*args, **kwargs):
        raise AssertionError("started a browser")

    monkeypatch.setattr(Engine, "_start", nothing)
    monkeypatch.setattr(Engine, "_start_chrome", nothing)
    result = await Engine(home=tmp_path, catalog=Catalog([], set())).open("https://example.com")
    assert result.text == f"error: {RETIRED_BROWSER}"
    assert RETIRED_BROWSER == ("AIB_BROWSER=app is retired: AI Browser's own Chrome is gone. Use own (your browser) "
                               "or sandbox.")


def test_the_engine_needs_no_development_packages():  # moved from test_appmode.py
    import subprocess
    import sys

    code = "import sys; sys.modules['httpx'] = None; import ai_browser.engine, ai_browser.server"  # httpx is dev-only
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60, encoding="utf-8")
    assert result.returncode == 0, result.stderr[-500:]
```

In `tests/test_engine.py`:
- `test_aib_browser_picks_the_browser`'s parametrize list loses `("app", "app")`;
- in `test_an_unknown_aib_browser_is_refused_never_guessed`,
  `"error: AIB_BROWSER must be own, chrome, brave, sandbox or app"` becomes
  `"error: AIB_BROWSER must be own, chrome, brave or sandbox"`.

Append to `tests/test_chrome.py`. These are the two `test_appmode.py` tests that have no user's-browser twin yet,
moved onto `chrome_engine` as plain sessions, without the app's reports:

```python
@CHROME
async def test_the_session_carries_on_when_the_user_closes_its_tab(chrome_engine):  # moved from test_appmode.py
    from ai_browser.cdp import CDP
    from ai_browser.chrome import find_ws_url

    engine, base, folder = chrome_engine
    await engine.sandbox_start(chrome=True)
    user = await CDP.connect(find_ws_url(folder, timeout=20))  # stands in for the user's own clicks
    try:
        await engine.open(base + "form.html")
        old = engine.browser.current.target
        await user.send("Target.closeTarget", {"targetId": old})  # the user closes the session's tab
        await asyncio.sleep(0.3)
        assert "new tab" in (await engine.observe()).text
        assert engine.browser.current.target != old
    finally:
        await user.close()


@CHROME
async def test_a_tab_the_user_opens_from_a_sessions_tab_stays_theirs(chrome_engine):  # moved from test_appmode.py
    from ai_browser.cdp import CDP
    from ai_browser.chrome import find_ws_url
    from ai_browser.steps import parse_step

    engine, base, folder = chrome_engine
    await engine.sandbox_start(chrome=True)
    user = await CDP.connect(find_ws_url(folder, timeout=20))
    try:
        await engine.open(base + "popup.html")  # the session's own (background) tab
        own = engine.browser.current.target
        session = (await user.send("Target.attachToTarget", {"targetId": own, "flatten": True}))["sessionId"]
        await user.send("Runtime.evaluate", {"expression": f"window.open('{base}form.html', '_blank'); 1",
                                             "userGesture": True}, session_id=session)
        await asyncio.sleep(1)
        users = [t["targetId"] for t in (await user.send("Target.getTargets"))["targetInfos"]
                 if t["url"].endswith("form.html")]
        assert users and not {tab.target for tab in engine.browser.owned.values()} & set(users)
        reply = await engine.browser.act([parse_step("scroll down")])
        assert "opened new tab" not in reply and engine.browser.current.target == own  # no jump into the user's tab
    finally:
        await user.close()


@CHROME
async def test_the_apps_pages_are_refused_through_the_engine(chrome_engine, monkeypatch):
    engine, _, _ = chrome_engine
    monkeypatch.setenv("AIB_APP_ORIGIN", "http://127.0.0.1:8799")  # as ai-browser app sets it for its agents
    await engine.sandbox_start(chrome=True)
    assert engine.browser.app_origin == "http://127.0.0.1:8799"
    result = await engine.open("http://127.0.0.1:8799/setup")
    assert result.text.startswith("error") and "AI Browser's own pages open only in its window" in result.text
```

In `tests/test_chrome.py`, in the test whose loop reads `for mode in ("sandbox", "app"):  # unchanged there`, the
tuple becomes `("sandbox",)`.

Delete `tests/test_appmode.py`. Every other test in it is retired with the mode, or already has a twin in the user's
browser (the spec's Decision 16 lists them). In `tests/conftest.py`, `PIPE_FIXTURES` loses `"app_engine"`.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_engine.py tests/test_chrome.py -q -p no:randomly -k "own_pages or retired or development_packages or picks_the_browser or never_guessed or carries_on or stays_theirs or refused_through or risky"`

Expected: FAIL:
- `url_problem` takes no `app_origin`;
- `AIB_BROWSER=app` still answers "AI Browser isn't open: start it with `uv run ai-browser app`";
- `RETIRED_BROWSER` doesn't exist;
- `Browser` has no `app_origin`.

- [ ] **Step 3: Remove app mode; refuse the app's origin**

In `src/ai_browser/browser.py`:

1. Delete `NO_TAB = (…)`, the app-mode message about `tabs switch uN`. Keep `NO_TAB_CHROME`.
2. Replace `url_problem` with:

   ```python
   def _same_origin(parts, origin: str) -> bool:
       try:
           own = urlsplit(origin)
           return (parts.scheme.lower(), parts.hostname or "", parts.port) == (own.scheme.lower(), own.hostname or "",
                                                                               own.port)
       except ValueError:
           return False


   def url_problem(url: str, mode: str, app_origin: str = "") -> str | None:
       """Why a URL may not be opened, or None. Never AI Browser's own pages (the app's origin): they open only in its
       window, and an agent has no cookie for them anyway. The user's own browser runs on this computer, so it opens
       web pages only; the sandbox may also open the files it shares with the shell under file:///work/ (never its own
       profile)."""
       try:
           parts = urlsplit(url.strip())
       except ValueError as exc:
           return f"not a valid address ({exc})"
       if app_origin and _same_origin(parts, app_origin):
           return "AI Browser's own pages open only in its window"
       scheme = parts.scheme.lower()
       if scheme in {"http", "https", "data"} or (scheme == "about" and parts.path == "blank"):
           return None
       if not scheme:
           return "use a full address such as https://example.com"
       if mode == "chrome":
           return ("only web pages (http, https, data:, about:blank) open in your own Chrome: local files and chrome:// "
                   f"pages would reach {platforms.this_computer()} and Chrome's settings (use read_file for work files)")
       path = posixpath.normpath(unquote(parts.path).replace("\\", "/"))
       if scheme == "file" and parts.netloc in {"", "localhost"} and (path == "/work" or path.startswith("/work/")):
           return None
       return "only web pages and files under file:///work/ can be opened in the sandbox"
   ```

3. In `Browser.__init__`'s signature, delete `hidden_extension: str = ""` and `front: bool = True`, and add a last
   keyword `app_origin: str = ""`. In its body:
   - the mode comment becomes `# "sandbox" (Docker Chromium) or "chrome" (the user's own browser: change nothing,
     only our background tabs)`;
   - delete the `self.hidden_extension = …` line and the three `self.front` lines with their comment;
   - delete `self._others: dict[str, str] = {}` and its comment;
   - add `self.app_origin = app_origin  # AI Browser's own origin: never opened here (url_problem)`.
4. `_check_url`: `problem = url_problem(url, self.mode)` becomes
   `problem = url_problem(url, self.mode, self.app_origin)`.
5. `close()`: `if tab.adopted or self.mode == "app" or self.keep_tabs:` becomes `if tab.adopted or self.keep_tabs:`.
6. `_no_tab()`: `return NO_TAB if self.mode == "app" else NO_TAB_CHROME if self.mode == "chrome" else "no open tab"`
   becomes `return NO_TAB_CHROME if self.mode == "chrome" else "no open tab"`.
7. `_new_tab`: `tab = await self.open_worker(background=self.mode == "chrome" or not self.front)` becomes
   `tab = await self.open_worker(background=self.mode == "chrome")`.
8. `open_worker`: `if self.mode in ("chrome", "app") if background is None else background:` becomes
   `if self.mode == "chrome" if background is None else background:`.
9. `ensure_tab`: `self.mode in ("app", "chrome")` becomes `self.mode == "chrome"`, and the comment's "and in AI
   Browser " goes.
10. `_switch`: delete the `if self.mode == "app" and self.front:` block and its two lines.
11. `_emulate`: `self.mode in ("chrome", "app")` becomes `self.mode == "chrome"`.
12. In the tab listing, delete the whole `if self.mode == "app":` block. That is the one that offers the user's tabs
    as `u1…`, ending with its `lines.append(… "(not opened by this session)")`.
13. In the `tabs switch` handling:
    - delete `if action == "switch" and tab in self._others:` with its next line;
    - in the error that lists the keys, `[*self.owned, *self._others, *self._handed_keys]` becomes
      `[*self.owned, *self._handed_keys]`.
14. `_upload_path`: `self.mode in ("chrome", "app")` becomes `self.mode == "chrome"`.

In `src/ai_browser/qa/run.py`, `problem = url_problem(url, browser.mode)` becomes
`problem = url_problem(url, browser.mode, getattr(browser, "app_origin", ""))`.

In `src/ai_browser/engine.py`:

1. Delete `from .appbrowser import app_profile`.
2. `RECONNECTED` keeps only its `"chrome"` entry.
3. Replace the `BROWSER_KINDS` and `BAD_BROWSER` lines with:

   ```python
   BROWSER_KINDS = {"": "chrome", "own": "chrome", "chrome": "chrome", "brave": "chrome",
                    "sandbox": "sandbox"}  # AIB_BROWSER -> the browser: "chrome" is the user's own (Brave or Chrome)
   BAD_BROWSER = "AIB_BROWSER must be own, chrome, brave or sandbox"
   RETIRED_BROWSER = ("AIB_BROWSER=app is retired: AI Browser's own Chrome is gone. Use own (your browser) or "
                      "sandbox.")
   ```

4. `browser_kind`'s docstring becomes `"""The browser AIB_BROWSER names ("chrome": the user's own; "sandbox"), or None
   for anything else."""`.
5. In `Engine.__init__`, delete `self.default_app = …`. The `_wanted` comment becomes
   `# (profile, fresh, sandbox|chrome) from sandbox_start`.
6. `_default_kind` becomes:

   ```python
       def _default_kind(self) -> str:
           """The browser this session uses until sandbox_start picks another: never a guess."""
           if os.environ.get("AIB_BROWSER", "").strip().lower() == "app":
               raise ValueError(RETIRED_BROWSER)
           if self._kind is None:
               raise ValueError(BAD_BROWSER)
           return self._kind
   ```

7. Delete `_app_profile`.
8. In `_start_chrome` (as the relay left it):
   - delete the `if mode == "app":` branch that finds `self._app_profile()`, and keep its `else` body at the outer
     level;
   - `name = self._browser_name() if mode == "chrome" else "Chrome"` becomes `name = self._browser_name()`, if that
     line is still there;
   - delete the `if mode == "app":` branch that makes `Browser(…, mode="app", hidden_extension=…, front=…)`, and keep
     the user's-browser `Browser(…)` call alone;
   - that `Browser(…)` call gains `app_origin=os.environ.get("AIB_APP_ORIGIN", "")`;
   - the docstring loses ", or in app mode to AI Browser, the agent's own Chrome started by `ai-browser app`".
9. The two other `Browser(` calls each gain `app_origin=os.environ.get("AIB_APP_ORIGIN", "")`: the sandbox's
   `Browser(cdp, work, self.cfg)`, and QA's `Browser(cdp, self._qa_work(), self.cfg, key_prefix="q")`.
10. `_register`: `self.browser.mode == "app" or \` goes from its condition.
11. `_status_text`: delete the `if info.chrome and info.profile == "app":` block.
12. `sandbox_start`: delete the comment `# In AI Browser (AIB_BROWSER=app) a plain sandbox_start() keeps using it.`,
    and the two-line `kind = …` becomes `kind = "chrome" if chrome else "sandbox"`.
13. `sandbox_stop`: `where = "AI Browser" if self.info.profile == "app" else f"your {self._browser_name()}"` becomes
    `where = f"your {self._browser_name()}"`.
14. `_end_qa_hold`: the condition's last line
    `not (self.info is not None and self.info.chrome and self.info.profile == "app"):` goes. The line above it then
    ends with `not self.cdp.closed:`.

Check with `grep -n '"app"\|default_app\|hidden_extension\|self.front\|_others\|NO_TAB\b' src/ai_browser/engine.py src/ai_browser/browser.py`.
Nothing should remain except the word "app" in unrelated text (`AIB_APP_*`, "the app").

- [ ] **Step 4: Run them to see them pass**

Run, one file at a time:
- `uv run pytest tests/test_engine.py -q -p no:randomly`
- `uv run pytest tests/test_chrome.py -q -p no:randomly`
- `uv run pytest tests/test_checks_browser.py tests/test_browser_misc.py tests/test_qa_browser.py -q -p no:randomly`

Expected: PASS. Docker tests skip without Docker.

- [ ] **Step 5: Commit**

```bash
git rm tests/test_appmode.py
git add src/ai_browser/browser.py src/ai_browser/engine.py src/ai_browser/qa/run.py tests/test_engine.py \
  tests/test_chrome.py tests/conftest.py
git commit -m "feat(engine): AI Browser mode retires; an agent never opens AI Browser's own pages"
```

### Task 20: Agents' instructions and the Brain: `PANEL_PROMPT`, the MCP app lines and `HAND_OVER_APP_SAY` go

**Files:**
- Modify: `src/ai_browser/app/bridge.py` (`PANEL_PROMPT` goes; `AIB_BROWSER` defaults to `chrome`;
  `BRAVE_PROMPT` always)
- Modify: `src/ai_browser/server.py` (the MCP instructions' last two lines)
- Modify: `src/ai_browser/brain/talk.py` and `src/ai_browser/brain/service.py` (`HAND_OVER_APP_SAY` and its branch),
  `src/ai_browser/app/agents.py` (`in_users_browser`)
- Modify: `tests/test_bridge.py`, `tests/test_server.py`, `tests/test_brain_talk.py`
- Test: `tests/test_bridge.py`, `tests/test_server.py`, `tests/test_brain_talk.py`

**Interfaces:**
- Consumes: brain-delegation's `HAND_OVER_SAY`, `HAND_OVER_ANY_SAY` and `HAND_OVER_APP_SAY`, its branch on
  `in_users_browser`, and its test `test_hand_over_is_a_pointer_never_a_hand`, whose `Recorder` has
  `in_users_browser = True`.
- Produces:
  - `bridge.PANEL_PROMPT`, `brain.talk.HAND_OVER_APP_SAY` and `AgentManager.in_users_browser` no longer exist;
  - every agent's `mcp.json` env defaults to `AIB_BROWSER=chrome` (`agents.env` still sets it), and its system prompt
    is `BRAVE_PROMPT`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_bridge.py`:
- `test_the_open_tab_reaches_claude_as_labelled_page_data` imports `BRAVE_PROMPT` in place of `PANEL_PROMPT`, and
  its last check becomes `assert "never the user's words" in BRAVE_PROMPT`;
- replace `test_the_panel_prompt_hands_bot_checks_to_the_user` with:

  ```python
  def test_ai_browsers_panel_prompt_is_gone():
      import ai_browser.app.bridge as bridge

      assert not hasattr(bridge, "PANEL_PROMPT")
      assert ("If a result says ⛔ bot check, stop and tell the user in one line: the tab is in front for them, and AI "
              "Home shows Continue. Don't reload, retry or open the site another way.") in " ".join(
                  bridge.BRAVE_PROMPT.split())
  ```

- in `test_agents_in_brave_get_the_brave_prompt`:
  - the import becomes `from ai_browser.app.bridge import BRAVE_PROMPT, ClaudeBridge`;
  - the end, from `log.write_text("", encoding="utf-8")`, becomes:

    ```python
        log.write_text("", encoding="utf-8")
        plain = ClaudeBridge(tmp_path / "home", claude=runner, agent_id="a2")  # no env: the user's browser all the same
        [event async for event in plain.send("two")]
        argv = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
        assert argv[argv.index("--append-system-prompt") + 1] == BRAVE_PROMPT
        config = json.loads(Path(argv[argv.index("--mcp-config") + 1]).read_text(encoding="utf-8"))
        assert config["mcpServers"]["ai-browser"]["env"]["AIB_BROWSER"] == "chrome"
        await plain.close()
    ```

    (`from pathlib import Path` joins the file's imports if it isn't there.)

In `tests/test_server.py`, in the instructions test, replace the assertion that holds
`"In AI Browser (AIB_BROWSER=app) the browser is already open beside the chat: …"` with:

```python
    assert "AIB_BROWSER=app" not in text and "tabs switch u1" not in text and "In AI Browser" not in text
    assert text.endswith("one request at a time, and stop at a 429 or 403.")
```

In `tests/test_brain_talk.py`:
- in `test_hand_over_is_a_pointer_never_a_hand`, delete the part that sets `in_users_browser = False` and expects
  `HAND_OVER_APP_SAY`;
- in `Recorder`, delete the class attribute `in_users_browser = True`;
- append:

  ```python
  def test_ai_browser_modes_hand_over_line_is_gone():
      import ai_browser.brain.talk as talk
      from ai_browser.app.agents import AgentManager

      assert not hasattr(talk, "HAND_OVER_APP_SAY") and not hasattr(AgentManager, "in_users_browser")
  ```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_bridge.py tests/test_server.py tests/test_brain_talk.py -q -p no:randomly`

Expected: FAIL:
- `PANEL_PROMPT` exists;
- a bridge with no env still gets `AIB_BROWSER=app`;
- the MCP instructions still hold the AI Browser lines;
- `HAND_OVER_APP_SAY` exists.

- [ ] **Step 3: Delete them**

In `src/ai_browser/app/bridge.py`:
- delete `PANEL_PROMPT = """…"""` whole;
- in `_mcp_config`, `"AIB_BROWSER": "app"` becomes `"AIB_BROWSER": "chrome"`;
- in `_command`, `BRAVE_PROMPT if self.env.get("AIB_BROWSER") == "chrome" else PANEL_PROMPT` becomes
  `BRAVE_PROMPT`;
- the module docstring's first line becomes
  `"""Bridge AI Browser's agents to Claude Code on this computer.`.

In `src/ai_browser/server.py`, delete the last two lines of `INSTRUCTIONS`:

```
In AI Browser (AIB_BROWSER=app) the browser is already open beside the chat: don't call sandbox_start; tabs list shows
the user's tabs there too (tabs switch u1 to work in one).
```

The string then ends `…one request at a time, and stop at a 429 or 403."""`.

In `src/ai_browser/brain/talk.py` (or `service.py`, wherever brain-delegation put the branch):
- delete `HAND_OVER_APP_SAY`;
- in the branch that answers `open` with `target: "tabs"`, keep only the user's-browser path: `HAND_OVER_SAY` with
  `open: {"agent": id, "tabs": True}`, or `HAND_OVER_ANY_SAY` with no agent. That path also sets `tab_hint`. Find the
  branch with `grep -n "in_users_browser\|HAND_OVER_APP_SAY" src/ai_browser/brain/*.py`, and delete its `else`
  (or `if not …`) arm.

In `src/ai_browser/app/agents.py`, delete the `in_users_browser` property.

Check with `grep -rn "PANEL_PROMPT\|HAND_OVER_APP_SAY\|in_users_browser" src/ tests/`. Nothing remains outside the
new "is gone" tests.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_bridge.py tests/test_server.py tests/test_brain_talk.py tests/test_brain_service.py tests/test_agents.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/bridge.py src/ai_browser/server.py src/ai_browser/brain/talk.py \
  src/ai_browser/brain/service.py src/ai_browser/app/agents.py tests/test_bridge.py tests/test_server.py \
  tests/test_brain_talk.py
git commit -m "feat(agents): one prompt and one browser for every agent; AI Browser mode's lines go"
```

### Task 21: AI Browser's Chrome and extension are deleted; the watcher's tests load it with `tests/pipe_chrome.py`

**Files:**
- Delete: `src/ai_browser/appbrowser.py`, `src/ai_browser/app/extension/manifest.json`,
  `src/ai_browser/app/extension/worker.js` and `tests/test_appbrowser.py`
- Create: `tests/pipe_chrome.py` (the pipe launcher, moved from `appbrowser.py`, for the watcher's tests only)
- Modify: `tests/test_watcher.py` (the `watcher` fixture's launch), `tests/conftest.py` (`PIPE_FIXTURES`)
- Modify: `src/ai_browser/app/ui/link.js` (the debugger helpers go), `src/ai_browser/app/__init__.py` (docstring)
- Modify: `tests/test_app_server.py` (`test_prepare_watcher_updates_its_folder_in_place`), `tests/test_ui_static.py`
- Test: `tests/test_appwindow.py`, `tests/test_ui_static.py`, `tests/test_watcher.py`

**Interfaces:**
- Consumes: the `watcher` fixture as the relay and wave A left it (a BraveLink attached and connected on its
  throwaway profile).
- Produces:
  - `tests/pipe_chrome.py`: `launch_with_extension(profile, folder) -> PipeChrome`. A `PipeChrome` has `ws_url`,
    `extension_id`, `profile`, `process` and `close()`;
  - `tests/pipe_chrome.py`'s `_Pipe` and `_spawn_posix(binary, args, pipe=True) -> (process, pipe)`, moved
    from `appbrowser.py` with their names (wave C's watcher-copy tests import `_spawn_posix`);
  - `PipeError(RuntimeError)`;
  - `PIPE_FIXTURES = {"watcher"}`;
  - `app/extension/` holds only `panel.html`, `panel.js` and `panel.css`, which wave D ports into the watcher and
    deletes.

- [ ] **Step 1: Write the failing tests, and move the watcher fixture onto the test helper**

Append to `tests/test_appwindow.py`:

```python
CORRECTED = ("**Corrected 2026-10-02 (safe-browsing spec):** measured, `navigator.webdriver` is true in headed AI "
             "Browser because of `--remote-debugging-port`; sites can see it is automated and Google refuses sign-in "
             "there. Hiding that was never a goal.")


def test_the_docs_say_the_window_is_never_automated():
    import importlib.util

    from ai_browser.config import project_root

    doc = " ".join(window.__doc__.split())
    assert "The window has no debugging port" in doc and "No agent browses in it" in doc
    assert importlib.util.find_spec("ai_browser.appbrowser") is None  # AI Browser's own Chrome is gone

    def flat(name):
        path = project_root() / "docs" / "superpowers" / name
        return " ".join(path.read_text(encoding="utf-8").split())

    assert flat("specs/2026-10-02-ai-home-design.md").count(CORRECTED) == 3
    assert flat("plans/2026-10-02-ai-home.md").count(CORRECTED) == 1
    assert ("the user's own browser is chosen before a task, for their logins; it is never a way around a block. A "
            "bot check is handed to the user in every mode.") in flat("specs/2026-10-02-own-chrome-mode-design.md")
```

In `tests/test_ui_static.py::test_the_pages_live_in_app_ui_and_the_watcher_shares_them`, the expected listing of
`app/extension` becomes `["panel.css", "panel.html", "panel.js"]`. Append:

```python
def test_link_js_lists_no_debugger_targets():
    assert "chrome.debugger" not in (UI / "link.js").read_text(encoding="utf-8")  # the watcher has no debugger
```

In `tests/test_watcher.py`'s `watcher` fixture, replace `from ai_browser.appbrowser import launch_app_browser` with
`from pipe_chrome import launch_with_extension`, and `app = launch_app_browser(tmp_path / "profile", folder,
headless=True)` with `app = launch_with_extension(tmp_path / "profile", folder)`. The rest of the fixture stays as
merged: it reads `app.ws_url` and `app.extension_id`, and calls `app.close()`.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_appwindow.py tests/test_ui_static.py tests/test_watcher.py -q -p no:randomly`

Expected: FAIL:
- `ai_browser.appbrowser` still exists;
- `app/extension` still holds `manifest.json` and `worker.js`;
- `link.js` still lists debugger targets;
- the watcher tests stop at `ModuleNotFoundError: No module named 'pipe_chrome'`.

- [ ] **Step 3: Delete, and keep the pipe for the tests only**

Create `tests/pipe_chrome.py`. These are `appbrowser.py`'s `_Pipe`, `_Process` and `_spawn_posix`, moved with their
names, plus the launcher the watcher's tests use:

```python
"""A throwaway headless Chrome with an unpacked extension loaded over the DevTools pipe, for the watcher's tests only.
Branded Chrome ignores --load-extension, so the tests install the watcher for one run with Extensions.loadUnpacked;
Chrome quits when the pipe closes. The product never does this: the user loads Brave's watcher once, by hand. POSIX
only (file descriptors 3 and 4): tests/conftest.py skips the `watcher` fixture on Windows."""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from ai_browser.chrome import ChromeError, chrome_binary, find_ws_url

START_TIMEOUT = 20  # seconds for Chrome to start and open its debugging port


class PipeError(RuntimeError):
    """The throwaway Chrome could not start, or didn't answer over its pipe."""


class _Pipe:
    """Chrome DevTools over --remote-debugging-pipe: NUL-separated JSON."""

    def __init__(self, to_chrome: int, from_chrome: int):
        self._out, self._in = to_chrome, from_chrome
        self._buffer = b""
        self._id = 0

    def call(self, method: str, params: dict, timeout: float = START_TIMEOUT) -> dict:
        import select  # POSIX only, like the pipe itself

        self._id += 1
        os.write(self._out, json.dumps({"id": self._id, "method": method, "params": params}).encode() + b"\0")
        deadline = time.monotonic() + timeout
        while True:
            while b"\0" not in self._buffer:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PipeError(f"Chrome did not answer {method} within {timeout:g} s")
                if not select.select([self._in], [], [], remaining)[0]:
                    continue
                chunk = os.read(self._in, 65536)
                if not chunk:
                    raise PipeError("Chrome closed its DevTools pipe")
                self._buffer += chunk
            raw, self._buffer = self._buffer.split(b"\0", 1)
            message = json.loads(raw)
            if message.get("id") != self._id:
                continue  # an event
            if "error" in message:
                raise PipeError(f"{method}: {message['error'].get('message', message['error'])}")
            return message.get("result", {})

    def drain(self) -> None:
        """Keep reading (and dropping) whatever Chrome sends, so its writes can never block."""
        def run() -> None:
            with contextlib.suppress(OSError):
                while os.read(self._in, 65536):
                    pass
        threading.Thread(target=run, name="aib-pipe-drain", daemon=True).start()

    def close(self) -> None:
        for fd in (self._out, self._in):
            with contextlib.suppress(OSError):
                os.close(fd)


@dataclass
class _Process:
    """Chrome, started with posix_spawn: Popen can't move descriptors onto 3 and 4 without preexec_fn."""

    pid: int
    returncode: int | None = None

    def poll(self) -> int | None:
        if self.returncode is None:
            try:
                pid, status = os.waitpid(self.pid, os.WNOHANG)
            except ChildProcessError:  # reaped elsewhere: it has exited, the code is lost
                self.returncode = -1
            else:
                if pid:
                    self.returncode = os.waitstatus_to_exitcode(status)
        return self.returncode

    def wait(self, timeout: float) -> int:
        deadline = time.monotonic() + timeout
        while self.poll() is None:
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired("Google Chrome", timeout)
            time.sleep(0.05)
        return self.returncode

    def _signal(self, number: int) -> None:
        if self.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.kill(self.pid, number)

    def terminate(self) -> None:
        self._signal(signal.SIGTERM)

    def kill(self) -> None:
        self._signal(signal.SIGKILL)


@dataclass
class PipeChrome:
    process: _Process
    ws_url: str
    extension_id: str
    profile: Path
    _pipe: _Pipe = field(repr=False)

    def close(self) -> None:
        """Chrome quits when its pipe closes; it is stopped if it hasn't after 10 s."""
        self._pipe.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)


def _spawn_posix(binary: str, args: list[str], pipe: bool = True) -> tuple[_Process, _Pipe | None]:
    """posix_spawn. With the pipe, Chrome reads commands on fd 3 and writes answers on fd 4."""
    import fcntl  # POSIX only

    actions = [(os.POSIX_SPAWN_OPEN, 1, os.devnull, os.O_WRONLY, 0), (os.POSIX_SPAWN_OPEN, 2, os.devnull, os.O_WRONLY, 0)]
    ours: list[int] = []  # our ends of the pipe
    theirs: list[int] = []  # Chrome's ends, closed here once it has started
    if pipe:
        to_read, to_write = os.pipe()  # Chrome reads commands on fd 3...
        from_read, from_write = os.pipe()  # ...and writes answers on fd 4
        # Chrome's ends go above 9 first, so moving one onto 3 or 4 in the child can never overwrite the other.
        theirs = [fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 10) for fd in (to_read, from_write)]
        for fd in (to_read, from_write):
            os.close(fd)
        actions = [(os.POSIX_SPAWN_DUP2, theirs[0], 3), (os.POSIX_SPAWN_DUP2, theirs[1], 4), *actions]
        ours = [to_write, from_read]
    try:
        process = _Process(os.posix_spawn(binary, args, os.environ, file_actions=actions,
                                          setsigdef=(signal.SIGPIPE, signal.SIGXFSZ)))
    except OSError as exc:
        for fd in ours:
            os.close(fd)
        raise PipeError(f"the throwaway Chrome could not start: {exc}") from None
    finally:
        for fd in theirs:
            os.close(fd)
    return process, (_Pipe(*ours) if pipe else None)


def launch_with_extension(profile, folder) -> PipeChrome:
    """A headless throwaway Chrome on `profile` with the unpacked extension in `folder` loaded for this run."""
    binary = chrome_binary()
    if binary is None:
        raise PipeError("Google Chrome is not installed")
    profile = Path(profile)
    profile.mkdir(parents=True, exist_ok=True)
    args = [binary, f"--user-data-dir={profile}", "--remote-debugging-port=0", "--no-first-run",
            "--no-default-browser-check", "--disable-search-engine-choice-screen", "--window-size=1440,960",
            "--remote-debugging-pipe", "--enable-unsafe-extension-debugging", "--headless=new"]
    process, pipe = _spawn_posix(binary, args, True)
    try:
        extension_id = pipe.call("Extensions.loadUnpacked", {"path": str(folder)})["id"]
        ws_url = find_ws_url(profile, START_TIMEOUT)
    except (PipeError, ChromeError, OSError, KeyError) as exc:
        pipe.close()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.terminate()
            process.wait(timeout=10)
        raise PipeError(f"the throwaway Chrome could not start: {exc}") from None
    pipe.drain()
    return PipeChrome(process, ws_url, extension_id, profile, pipe)
```

Then:

```bash
git rm src/ai_browser/appbrowser.py src/ai_browser/app/extension/manifest.json src/ai_browser/app/extension/worker.js \
  tests/test_appbrowser.py
```

In `tests/conftest.py`:
- `PIPE_FIXTURES` becomes `{"watcher"}  # it loads Brave's watcher into a throwaway Chrome over the DevTools pipe`;
- in `platform_skip`'s docstring, "installs the extension over the DevTools pipe" becomes "loads the watcher over the
  DevTools pipe".

In `src/ai_browser/app/ui/link.js`:
- delete `targets()`, `targetOfTab` and `tabOfTarget`;
- delete the header's last sentence, "Also, until AI Browser's old extension retires: Chrome tab ids <-> DevTools
  target ids."

(`app/extension/panel.js` still imports them. It is neither served nor shipped, and wave D rewrites it.)

`src/ai_browser/app/__init__.py` becomes:

```python
"""AI Browser app: its own window (AI Home, Mission Control and the Brain), the agents, and the app server between."""
```

In `tests/test_app_server.py::test_prepare_watcher_updates_its_folder_in_place`:
- delete the import `from ai_browser.appbrowser import prepare_extension` (Task 0 split it from
  `from ai_browser.extension_id import extension_id_for`, which stays);
- `assert extension_id_for(folder) != extension_id_for(prepare_extension(tmp_path, "http://127.0.0.1:1", "t"))`
  becomes `assert extension_id_for(folder) != extension_id_for(tmp_path / "app" / "extension")  # another folder,
  another ID`.

Check with `grep -rn "appbrowser\|launch_app_browser\|prepare_extension\|app_profile" src/ tests/`. Nothing remains
but the `find_spec` line above.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_appwindow.py tests/test_ui_static.py tests/test_app_server.py -q -p no:randomly`

Expected: PASS.

Run: `uv run pytest tests/test_watcher.py tests/test_watcher_groups.py tests/test_brain_ui.py tests/test_ai_home_phase2.py -q -p no:randomly`

Expected: PASS. The watcher loads over the pipe from `tests/pipe_chrome.py` exactly as before.

- [ ] **Step 5: Commit**

```bash
git add tests/pipe_chrome.py tests/test_watcher.py tests/conftest.py src/ai_browser/app/ui/link.js \
  src/ai_browser/app/__init__.py tests/test_app_server.py tests/test_ui_static.py tests/test_appwindow.py
git commit -m "refactor: AI Browser's own Chrome and extension are deleted; the watcher's tests keep the pipe"
```

### Task 22: `doctor --setup` checks the window's browser

**Files:**
- Modify: `src/ai_browser/cli.py` (`_doctor_setup`)
- Modify: `tests/test_cli.py` (the setup doctor's tests)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `window.pick(setting)`, which reads files only (Task 1), and `Settings(home).get()` (Task 2).
- Produces:
  - `doctor --setup`'s third line, which is required: `✓ window      <name> (Auto) <program>` (or `(Settings)` when
    the user picked one), or `✗ window      AI Browser needs Google Chrome, Brave or Microsoft Edge to draw its
    window: install one, or set AIB_CHROME_BINARY to the full path of chrome`;
  - the Chrome and Brave lines below it, now information only.

- [ ] **Step 1: Write the failing tests**

In `tests/test_cli.py::test_doctor_setup_checks_without_docker_or_a_browser_connection`, the line assertions become:

```python
    lines = out.splitlines()
    assert lines[0].startswith("✓ Python      3.")
    assert lines[1] == f"✓ Claude Code {tmp_path / 'claude-bin'}"
    assert lines[2] == f"✓ window      Google Chrome (Auto) {tmp_path / 'chrome-bin'}"
    assert lines[3] == f"✓ Chrome      {tmp_path / 'chrome-bin'}"  # information now: agents may browse in it
    assert lines[4].startswith(("✓ Brave", "- Brave"))  # information only
    assert lines[5].startswith("✓ everyday") and "remote debugging is on" in lines[5]
    assert lines[6] == "✓ ports       app 8792-8811 and live view 8770-8790 have free ports"
    assert lines[7] == "- Docker      not checked here: run `uv run ai-browser doctor`"
    assert lines[-1] == "all good"
```

Rename `test_doctor_setup_fails_without_claude_code_or_chrome` to
`test_doctor_setup_fails_without_claude_code_or_a_window_browser`. Its middle assertion becomes:

```python
    assert "✗ Claude Code" in out and "✗ window" in out and "AIB_CHROME_BINARY" in out
    assert "AI Browser needs Google Chrome, Brave or Microsoft Edge to draw its window" in out
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_cli.py -q -p no:randomly -k "doctor_setup"`

Expected: FAIL. The third line is still `✓ Chrome …`.

- [ ] **Step 3: The `window` line**

In `src/ai_browser/cli.py::_doctor_setup`:
- the docstring's second sentence becomes "Python, Claude Code, a browser that can draw AI Browser's window and a
  config.json that is there must pass; the rest is information.";
- replace the block from `chrome = chrome_binary()` through the `report("✗", "Chrome", …)` call with:

  ```python
      from .app.window import pick
      from .settings import Settings

      setting = Settings(home()).get()["window_browser"]
      found = pick(setting)  # reads installed apps' files only: no browser starts, nothing connects
      if found is None:
          report("✗", "window", "AI Browser needs Google Chrome, Brave or Microsoft Edge to draw its window: install "
                                "one, or set AIB_CHROME_BINARY to the full path of chrome", True)
      else:
          report("✓", "window", f"{found.browser.name} ({'Auto' if setting == 'auto' else 'Settings'}) "
                                f"{found.browser.binary}", True)
          if found.note:
              report("-", "window", found.note)
      chrome = chrome_binary()
      if chrome and Path(chrome).is_file():
          report("✓", "Chrome", chrome)
      else:
          report("-", "Chrome", "not installed (optional: agents can browse in it)")
  ```

The Brave line after it stays as it is.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_cli.py -q -p no:randomly`

Expected: PASS. `test_doctor_setup_prints_its_marks_on_any_console` runs `doctor --setup` in a subprocess, without
the conftest fixture. There `pick` reads the installed apps' `Info.plist` files and the LaunchServices file, and
connects to nothing. `AIB_CHROME_BINARY` points at the test's file, so it still passes.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/cli.py tests/test_cli.py
git commit -m "feat(doctor): doctor --setup checks the browser that draws AI Browser's window"
```

### Task 23: The README; the whole suite and the bench

**Files:**
- Modify: `README.md`. Find each part by its heading or quoted text:
  - the intro's "Three parts" list;
  - `## Windows`, step 5;
  - `## Which browser`;
  - `## AI Browser (a browser with AI Home and Claude agents)`, the whole section;
  - `## Mission Control (your agents at work, in 3D)`;
  - `## Talking to the Brain (push-to-talk, speech to text on this computer)`;
  - `## Commands`;
  - `## Safety notes`.
- Test: `tests/test_appwindow.py`

**Interfaces:**
- Consumes: the README as the relay and wave A left it. Their lines stay word for word:
  - wave A's AI Home **Tabs** bullet and its three sub-bullets;
  - the relay's Allow lines in "Use your everyday Brave";
  - wave A's Brain and Mission Control lines.
- Produces: the docs say what this plan built.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_appwindow.py`:

```python
def test_the_readme_describes_the_window():
    from ai_browser.config import project_root

    text = " ".join((project_root() / "README.md").read_text(encoding="utf-8").split())
    assert "uv run ai-browser app [--window auto|chrome|brave|edge]" in text
    assert "AI Browser's window has no debugging port, and no agent browses there." in text
    assert "~/.ai-browser/browser/" in text and "delete them by hand" in text
    section = text.split("## AI Browser (its own window", 1)[1].split("## The Brain", 1)[0]
    for gone in ("Load unpacked", "chrome://extensions", "⌘⇧Y", "Debugging port:", "toolbar badge",
                 "pinned first tab", "Keep it"):
        assert gone not in section, gone
    for kept in ("Settings", "Mission Control", "open only in its own window", "Ctrl-C"):
        assert kept in section, kept
    assert "--browser app" not in text and "AIB_APP_BROWSER=app" not in text
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_appwindow.py::test_the_readme_describes_the_window -q -p no:randomly`

Expected: FAIL. The README still describes AI Browser's Chrome and `--browser app`.

- [ ] **Step 3: Write the docs**

In `README.md`:

1. **Intro.** In the "Three parts" list, `- **the AI Browser app** (a Chrome with a Claude side panel).` becomes
   `- **the AI Browser app** (its own window: AI Home, Mission Control and the Brain).`
2. **`## Windows`, step 5.** Replace the step-5 item, from `5. **AI Browser:**` through its "Google sign-in"
   sub-bullet, with:

   ```markdown
   5. **AI Browser:** `uv run ai-browser app`. It opens in a window of its own, drawn by Microsoft Edge (or the
      browser you pick in AI Browser's Settings), with nothing to load by hand. Close the window, or press Ctrl-C in
      the terminal, to stop it.
   ```

   Step 6 (Brave) stays as merged.
3. **`## Which browser`.** Delete the bullet that begins `- **AI Browser:** \`ai-browser app --browser app\``,
   together with its second line.
4. **`## AI Browser …`.** Replace the whole section, from its heading up to `## The Brain`, with the text below.
   The **Your browser** and **Tabs** bullets below hold the relay's and wave A's words, as their specs give them. If
   the merged README words those two bullets differently, keep the merged words.

   ````markdown
   ## AI Browser (its own window: AI Home, Mission Control and the Brain)

   ```bash
   uv run ai-browser app            # add --model haiku for the fastest replies, or opus for the most capable
   ```

   AI Browser opens in a window of its own: a title bar only, with no tabs and no address bar. An installed browser
   draws it in its app mode, on a profile of AI Browser's own (`~/.ai-browser/app/window/<browser>/`), with no
   debugging port. Nothing drives that window, so it never asks "Allow remote debugging?" and shows no automation bar,
   and no agent browses there. Agents browse in your everyday Brave ([Which browser](#which-browser)), where you are
   signed in yourself: chosen before the task, for your logins, and nothing switches browsers on its own after a
   block. When a site answers with a bot check, the agent stops and hands it to you ([Bot checks](#bot-checks)).

   **Which browser draws the window:** Settings → App window offers **Auto**, **Google Chrome**, **Brave**, and
   **Microsoft Edge** on Windows. Auto picks Google Chrome on a Mac whose everyday browser is Brave, so a link clicked
   in another app never lands in AI Browser's window, and Microsoft Edge on Windows. The Dock (the taskbar on Windows)
   shows that browser's icon while AI Browser is open. A change applies at the next start;
   `uv run ai-browser app --window brave` picks one for a single run.

   **First start (once):** there is nothing to load in the window. The terminal shows the watcher's steps for Brave,
   and Finder (File Explorer on Windows) shows the watcher's folder. AI Home's browser card and the Brain's **Set it
   up** open the same steps in a small window.

   **AI Home** is the window's first page.
   - **Start a task:** pick skills and a model if you like. In Brave you can also type `ai`, a space and the task in
     the address bar: the watcher passes it on, and Brave says "Started 4 · Fix the footer".
   - **Agents:**
     - Up to 3 work at once (`AIB_APP_MAX_AGENTS`); the rest wait in line.
     - Each row shows what the agent is doing now, its last action with timing, a small picture of its tab, and its
       time and cost.
     - Each row has **Watch**, **Chat**, **Stop** and **Close**.
     - The window's title counts the agents at work: "(2) AI Home".
   - **Your browser:** a card at the top says whether your Brave is connected. When Brave's switch is off, it shows
     the steps; when Brave asks "Allow remote debugging?", it says so. It also lists everything connected
     through AI Browser, with Disconnect.
   - **Tabs:** the web tabs of the Brave profile the watcher is in (without the watcher, the profile you used last),
     each marked with whose it is: an agent's, Claude Code's, the Brain's, or yours. Other profiles and private windows
     are only counted, never listed.
     - A click brings a tab to the front.
     - **Hand over** gives one of your tabs to a new or running agent (it reads that tab and acts in it).
     - **Take back** ends that.
   - **Skills:**
     - every one of Claude's skills (personal, plugins, claude.ai, ai-browser), and which ones each agent loaded;
     - add one to a new task, or ask a running agent to use it.
   - **Settings** (beside **Mission Control**): which browser draws the window. The model you pick and Voice are
     remembered by AI Browser itself, in every window and across restarts.

   **Windows and links:** Mission Control, Settings, the setup steps and an agent's live view open as small windows of
   their own; a second click brings the open one forward. A link to a website opens in your Brave, never in AI
   Browser's window. Each agent's tabs sit in a coloured tab group in your Brave, named after its task. The Brain's
   watcher makes the groups. Without the watcher, each tab the AI opens gets a window of its own.

   How it works:
   - **Claude:** each agent is Claude Code on this computer (`claude -p`), signed in with your Claude account, with no
     API keys. Its only tools are ai-browser's. Shell commands and skill scripts run in the Docker sandbox.
   - **Background agents:** tasks from AI Home, Mission Control or Brave's address bar work in background tabs. They
     never take your focus, and they stay at full speed. **Watch** brings one to the front.
   - **Stop and Close:** **Stop** interrupts an agent and keeps its tabs. **Close** ends it and closes the tabs it
     opened; your own tabs stay open.
   - **Logins:** log in yourself, in that tab in Brave. Claude never types passwords, and risky buttons (⚠) need your
     yes in that agent's chat.
   - **Downloads** go to your Downloads folder, and only after your OK.
   - **Only the window gets in:** AI Browser's window starts with a one-time code that the app swaps for a cookie
     only that window holds. The same address typed into Brave shows "AI Browser's pages open only in its own window".
   - **Closing:** close the window (⌘Q on a Mac), or press Ctrl-C in the terminal: the agents end with it. A Mission
     Control or Settings window still open keeps AI Browser running until the last of its windows closes. The Docker
     shell container keeps running for the next start; stop it with `uv run ai-browser stop chrome`.
   - **The microphone** is asked for once, in the window, and kept across restarts: AI Browser comes back on the same
     address.
   - **Old folders:** `~/.ai-browser/browser/` (AI Browser's old Chrome profile, which may hold logins you made there)
     and `~/.ai-browser/app/extension/` (its old extension) are no longer used. AI Browser never deletes them; delete
     them by hand if you like.
   ````

5. **`## Mission Control`.** Its first line,
   `**Mission Control**, in AI Home's header, opens a dark control room:`, becomes
   `**Mission Control**, in AI Home's header, opens a dark control room in a window of its own (a second click brings
   it forward):`. In its **Voice** bullet, "It is off by default and remembered." becomes "It is off by default, and AI
   Browser remembers it."
6. **`## Talking to the Brain`, setup step 3.** "AI Browser then asks to use the microphone: choose **Allow while
   visiting the site**, not **Allow this time**. macOS may also ask once whether Google Chrome may use the
   microphone." becomes:

   ```markdown
     3. AI Browser's window then asks to use the microphone: choose **Allow while visiting the site**, not **Allow
        this time**. It asks once: AI Browser comes back on the same address after a restart. macOS may also ask once
        whether the browser that draws the window (Google Chrome on a Mac) may use the microphone.
   ```

7. **`## Commands`.** The first two lines become:

   ```bash
   uv run ai-browser app [--window auto|chrome|brave|edge]  # AI Browser's window; agents browse in your Brave
   uv run ai-browser doctor [--own]             # health check (the sandbox, or your own Brave or Chrome)
   ```

   and the `doctor --setup` line's comment becomes
   `# quick check, no Docker: Python, Claude Code, the window's browser, Brave, ports, config`.
8. **`## Safety notes`.** Add a first bullet:

   ```markdown
   - AI Browser's window has no debugging port, and no agent browses there. Its pages need a cookie only that window
     holds, every request must name `127.0.0.1:<port>` exactly, and a strict content policy runs no script but the
     pages' own.
   ```

Check with `grep -n -- "--browser app\|AIB_APP_BROWSER\|⌘⇧Y\|side panel\|chrome://extensions" README.md`. What may
remain is only in sections other waves own, never about AI Browser's Chrome. The side chat is wave D's.

- [ ] **Step 4: Run the docs test, then the whole suite and the bench**

Run: `uv run pytest tests/test_appwindow.py -q -p no:randomly`

Expected: PASS.

Run: `uv run pytest -q -p no:randomly`

Expected: PASS.
- Docker tests skip when Docker or the image is missing.
- The Chrome tests need Google Chrome.
- `test_panel.py` and the two panel tests are skipped, for wave D.

Write the tail of the output to the ledger. If anything fails, fix it test-first in the task that owns the code, then
run the whole suite again.

Run: `uv run ai-browser bench`

Expected: every row PASS. Its budgets cover the sandbox's reading and acting, which this plan doesn't touch. Write the
table to the ledger.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_appwindow.py
git commit -m "docs: AI Browser is its own window; the old Chrome and extension are gone"
```

Then:
1. **The final review.** A fresh reviewer checks the branch against the Global Constraints and the Review Focus. One
   fix pass follows, test-first; minor findings go to the ledger.
2. **The hand check, by the user, on the Mac** (the spec's list). The main session asks the user. No agent opens the
   window or touches the user's Brave.
   1. `uv run ai-browser app`:
      - one window with a title bar only;
      - no "Allow remote debugging?" for the window and no automation bar;
      - the Dock shows Google Chrome.
   2. Mission Control and Settings open as small windows, and a second click brings them forward.
   3. The first talk in Mission Control's window shows Chrome's microphone prompt (and macOS's once). After a
      restart, no prompt.
   4. With Voice on, Mission Control speaks an update right after start, with no click.
   5. Closing the window ends the app within about 5 s, and no Chrome is left in the Dock.
   6. In Brave, `ai check the shop` starts an agent, and the notification appears.
   7. Typing `http://127.0.0.1:<port>/home` in Brave shows the "open only in its own window" page.
   8. Ctrl-C in the terminal closes the window, and the next start shows no "Restore pages?".
3. **On the Windows laptop:**
   - Edge draws the window on its first run with a fresh profile, with no welcome page;
   - closing it ends the app;
   - Ctrl-C in the terminal closes it, and the next start shows no "Restore pages?";
   - a link clicked in another app (Mail, Teams) opens in the everyday browser, not in the window.
