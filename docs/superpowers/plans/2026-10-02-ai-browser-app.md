# AI Browser App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `ai-browser app` opens **AI Browser**: a dedicated Google Chrome with a Claude chat side panel. Local Claude
Code is the brain (no API keys), and the ai-browser engine does the clicking, jev-ultrafast style.

**Architecture:**
- **Launcher:** starts Chrome with a debugging port, which the engine uses, and a pipe, which installs the side-panel
  extension.
- **Local server:** a token-guarded local WebSocket server connects the panel to a `claude -p` stream-json bridge. Its
  MCP server is ai-browser in a new **app** browser mode that drives that Chrome.

**Tech stack:**
- Python 3.12: asyncio, Starlette/uvicorn (already used by the live view), the existing CDP client, `websockets`.
- An MV3 Chrome extension (plain HTML/CSS/JS).
- Claude Code CLI 2.1.263 (`claude -p`).
- pytest with a throwaway headless Chrome and a fake `claude` script.

**Spec:** `docs/superpowers/specs/2026-10-02-ai-browser-app-design.md`

## Global Constraints

- **No API keys:** the bridge never passes `--bare` (it skips the keychain login) and never sets `ANTHROPIC_API_KEY`.
- **Claude's tools are limited:**
  - always `--tools "" --strict-mcp-config --allowedTools "mcp__ai-browser__*" --permission-mode dontAsk
    --setting-sources local`;
  - the panel's Claude gets only ai-browser tools.
- **The panel shows model text as text,** never as HTML (`textContent` only).
- **Server:**
  - binds `127.0.0.1` only;
  - checks the token in constant time;
  - accepts only our extension's origin.
- **Engine app mode:**
  - foreground tabs, real window size, downloads to the work folder;
  - `chrome-extension://` allowed, `file://` and `chrome://` blocked;
  - adopted tabs are never closed by the session.
- **The engine never touches:** our own extension's pages (side panel) and extension service workers.
- **No git** in this repo. Wherever a step says "commit", append a line to the ledger
  `.superpowers/sdd/2026-10-02-ai-browser-app/progress.md` instead.

## Review Focus

1. **Claude Code missing, not signed in, or the process dies mid-answer:** the panel shows a plain error, and the next
   message starts a new process with `--resume`. Test: a fake `claude` that exits early (Task 3).
2. **The panel reconnects while Claude is working** (panel closed and reopened): the server must not start a second
   Claude process, and the new socket gets the rest of the stream. Test: Task 4.
3. **A web page tries to drive the local server** (CSRF/WebSocket from a site): wrong origin or no token is refused.
   Test: Task 4.
4. **Planted HTML or script in Claude's reply,** from a prompt-injected page: rendered as text. Test: Task 5.
5. **The user closes the AI Browser window** while `ai-browser app` runs: the command ends cleanly and nothing is left
   running. Test: Task 6.

---

### Task 0: Finish the Website QA plan (its Tasks 7 and 8)

Follow `docs/superpowers/plans/2026-10-02-website-qa.md` Tasks 7–8 exactly (`Engine.qa`, MCP tool `qa`, sandbox test,
`skills/website-qa/SKILL.md`, README, real-world check, final review), with its own ledger. Done when the QA ledger
says "Website QA plan: COMPLETE."

### Task 1: AI Browser launcher

**Files:**
- Create: `src/ai_browser/appbrowser.py`
- Create: `src/ai_browser/app/__init__.py`
- Create: `src/ai_browser/app/extension/` (`manifest.json`, `worker.js`, `panel.html`, `panel.css`, `panel.js`). These
  are minimal placeholders; Task 5 fills them in.
- Test: `tests/test_appbrowser.py`

**Interfaces (produced):**
- `AppBrowserError(RuntimeError)`
- `prepare_extension(home: Path, server_url: str, token: str) -> Path`
  - copies `app/extension/` to `home/"app"/"extension"`;
  - writes `config.json` as `{"server": server_url, "token": token}`;
  - returns the folder.
- `launch_app_browser(profile: Path, extension_dir: Path, headless: bool = False) -> AppBrowser`. Chrome flags:
  - `--user-data-dir=<profile> --remote-debugging-port=0 --remote-debugging-pipe --enable-unsafe-extension-debugging`;
  - `--no-first-run --no-default-browser-check --disable-search-engine-choice-screen --window-size=1440,960`;
  - `[--headless=new]`.

  Behaviour:
  - It sends `Extensions.loadUnpacked {path}` over the pipe (NUL-separated JSON) and waits for
    `find_ws_url(profile, 20)`.
  - It refuses with `AppBrowserError("AI Browser is already open (profile …): close it or stop the other ai-browser
    app first")` when `profile/DevToolsActivePort` answers, or when Chrome exits at once (the profile is locked).
- `AppBrowser`: `process`, `ws_url`, `extension_id`, `closed` (property), `close()`.
  - `close()` closes the pipe (Chrome then quits); after 10 s it terminates the process.
- `app_profile(home) -> Path`, which returns `home/"browser"`.

- [ ] **Step 1: Write the failing tests**

```python
import json

import pytest

from ai_browser.chrome import chrome_binary

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


def test_prepare_extension_copies_the_panel_with_its_config(tmp_path):
    from ai_browser.appbrowser import prepare_extension

    folder = prepare_extension(tmp_path, "http://127.0.0.1:8792", "secret")
    assert folder == tmp_path / "app" / "extension"
    assert json.loads((folder / "manifest.json").read_text())["side_panel"]["default_path"] == "panel.html"
    assert json.loads((folder / "config.json").read_text()) == {"server": "http://127.0.0.1:8792", "token": "secret"}


@CHROME
async def test_launch_installs_the_panel_and_the_engine_can_connect(tmp_path):
    from ai_browser.appbrowser import AppBrowserError, launch_app_browser, prepare_extension
    from ai_browser.cdp import CDP

    extension = prepare_extension(tmp_path, "http://127.0.0.1:1", "t")
    app = launch_app_browser(tmp_path / "profile", extension, headless=True)
    try:
        assert len(app.extension_id) == 32
        cdp = await CDP.connect(app.ws_url)
        urls = [t["url"] for t in (await cdp.send("Target.getTargets"))["targetInfos"]]
        await cdp.close()
        assert any(url.startswith(f"chrome-extension://{app.extension_id}/") for url in urls)
        with pytest.raises(AppBrowserError, match="already open"):
            launch_app_browser(tmp_path / "profile", extension, headless=True)
    finally:
        app.close()
    assert app.closed
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_appbrowser.py -q`. Expected: FAIL (no module).
- [ ] **Step 3: Implement.**
  - `appbrowser.py` with a tiny blocking pipe client: `_Pipe.call(method, params)`, which writes JSON + `\0` and reads
    until the reply with the same id.
  - Placeholder extension files.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Ledger.** Add "Task 1: complete".

### Task 2: Engine app mode

**Files:**
- Modify: `src/ai_browser/browser.py`
  - `url_problem` gains mode `app`;
  - `Browser(mode="app")` gets foreground tabs, a download folder, the all-tabs list and adoption, and leaves adopted
    tabs open;
  - `Tab.adopted: bool = False`.
- Modify: `src/ai_browser/engine.py`
  - `AIB_BROWSER=app` → `_start_app()`: connect via `find_ws_url(AIB_APP_PROFILE or home/"browser")`, with mode `app`;
  - `sandbox_start()` with default arguments keeps app mode when it's the default;
  - status text "browser: AI Browser (the agent's own Chrome)".
- Modify: `src/ai_browser/server.py`. Add an INSTRUCTIONS line: "In the AI Browser app, don't call sandbox_start; use
  the open tab".
- Test: `tests/test_appmode.py`

**Interfaces:**
- **Consumes:** `launch_app_browser`, `prepare_extension`.
- **Produces:**
  - `url_problem(url, "app")`, which also allows `chrome-extension:`;
  - in app mode, `Browser.tabs("list")` adds lines `  u1  "title"  url  (not opened by this session)`;
  - `Browser.tabs("switch", "u1")` adopts that tab: it becomes owned, gets a new `tN` key and `adopted=True`, and
    becomes current;
  - `Browser.close()` detaches from adopted tabs instead of closing them;
  - the env `AIB_APP_EXTENSION=<id>` hides our own extension's targets from listings.

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from ai_browser.chrome import chrome_binary

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


def test_app_mode_url_rules():
    from ai_browser.browser import url_problem

    assert url_problem("chrome-extension://abc/options.html", "app") is None
    assert url_problem("https://example.com", "app") is None
    assert url_problem("file:///etc/hosts", "app") and url_problem("chrome://settings", "app")


@pytest.fixture
async def app_engine(tmp_path, monkeypatch):
    from ai_browser import testpages
    from ai_browser.appbrowser import launch_app_browser, prepare_extension
    from ai_browser.engine import Engine
    from ai_browser.skills import Catalog

    app = launch_app_browser(tmp_path / "profile", prepare_extension(tmp_path, "http://127.0.0.1:1", "t"),
                             headless=True)
    monkeypatch.setenv("AIB_BROWSER", "app")
    monkeypatch.setenv("AIB_APP_PROFILE", str(tmp_path / "profile"))
    monkeypatch.setenv("AIB_APP_EXTENSION", app.extension_id)
    base, _, stop = testpages.serve_host()
    engine = Engine(home=tmp_path / "home", default_profile="pytest-app", catalog=Catalog([], set()))
    yield engine, base, app
    await engine.close()
    stop()
    app.close()


async def targets_of(app):
    from ai_browser.cdp import CDP

    cdp = await CDP.connect(app.ws_url)
    try:
        return {t["targetId"] for t in (await cdp.send("Target.getTargets"))["targetInfos"]}
    finally:
        await cdp.close()


@CHROME
async def test_app_mode_works_in_the_visible_browser_and_adopts_user_tabs(app_engine):
    engine, base, app = app_engine
    opened = await engine.open(base + "form.html")
    assert 'page  "Form test"' in opened.text
    assert "AI Browser" in (await engine.sandbox_status()).text
    user_tab = (await engine.cdp.send("Target.createTarget", {"url": base + "privacy.html"}))["targetId"]
    listing = (await engine.tabs("list")).text
    assert "u1" in listing and "privacy.html" in listing and app.extension_id not in listing
    assert 'page  "Privacy"' in (await engine.tabs("switch", "u1")).text
    panel = await engine.open(f"chrome-extension://{app.extension_id}/panel.html")
    assert not panel.text.startswith("error")
    assert (await engine.open("file:///etc/hosts")).text.startswith("error")
    await engine.close()
    assert user_tab in await targets_of(app)  # the user's tab stays open
```

- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Read `engine._start_chrome` and `Browser.tabs` first, and reuse them; don't duplicate.
- [ ] **Step 4: Run** this file plus `tests/test_chrome.py`. Expected: PASS.
- [ ] **Step 5: Ledger.** Add "Task 2: complete".

### Task 3: Claude Code bridge

**Files:**
- Create: `src/ai_browser/app/bridge.py`
- Create: `tests/fake_claude.py`, a script that records argv and stdin lines to `$FAKE_CLAUDE_LOG` and answers every
  user message from `$FAKE_CLAUDE_SCRIPT`.
  - Script entries are events.
  - `{"exit": n}` exits with that code.
  - `{"sleep": s}` pauses.
- Modify: `tests/conftest.py`. Add the fixture `fake_claude(tmp_path, monkeypatch) -> (runner, log, script)` so that
  Tasks 3–6 share it.
- Test: `tests/test_bridge.py`

**Interfaces (produced):**
- `PANEL_PROMPT` (the system prompt appended for the panel).
- `ClaudeBridge(home: Path, model: str = "sonnet", claude: str | None = None, env: dict[str, str] | None = None)`:
  - `model`, settable (it restarts with `--resume` on the next send);
  - `session_id: str | None`;
  - `busy: bool`;
  - `async send(text, tab_url="", tab_title="") -> AsyncIterator[dict]`;
  - `async stop()`, `async close()`, `reset()` (new chat: forgets the session).
- **Event translation (Claude Code stream-json → panel):**
  - `stream_event` `content_block_delta`/`text_delta` → `{"type": "delta", "text"}`;
  - each `assistant` message → `{"type": "tool", "name": short name, "summary"}` per `tool_use` block, then
    `{"type": "message_end"}`;
  - `user` `tool_result` → `{"type": "tool_result", "name", "lines": first 12 lines, "page": full text up to 6000
    chars (for open/observe/act/tabs), "is_error"}`;
  - `result` → `{"type": "done", "seconds", "cost"}`, or `{"type": "error", "text"}` when `is_error`;
  - `system/init` → `session_id`, plus `{"type": "status", "model", "connected": <ai-browser mcp status>}`;
  - a process that ends without a `result` → `{"type": "error", "text": "Claude Code stopped unexpectedly (exit N):
    <stderr tail>"}`.
- **Command:** `[claude, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
  "--include-partial-messages", "--model", model, "--tools", "", "--strict-mcp-config", "--mcp-config",
  <home/app/mcp.json>, "--allowedTools", "mcp__ai-browser__*", "--permission-mode", "dontAsk", "--setting-sources",
  "local", "--append-system-prompt", PANEL_PROMPT, ("--resume", session_id)?]`, with cwd `home/"app"/"chat"`.
- **`mcp.json`:** `{"mcpServers": {"ai-browser": {"command": sys.executable, "args": ["-m", "ai_browser.cli", "mcp"],
  "env": {"AIB_HOME": str(home), "AIB_BROWSER": "app", ...env}}}}`.
- **Tool summaries:**
  - `act` → the steps joined by " · ";
  - `open` → url;
  - `screenshot` → size;
  - otherwise the first 80 characters of the JSON input.
- **The user message** is prefixed with `[The user is looking at: <title> — <url>]` when a tab is known.

- [ ] **Step 1: Write the failing tests**

```python
import json

EVENTS = [
    {"type": "system", "subtype": "init", "session_id": "s-1", "model": "claude-sonnet-5-5",
     "mcp_servers": [{"name": "ai-browser", "status": "connected"}]},
    {"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Open"}}},
    {"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "ing"}}},
    {"type": "assistant", "message": {"content": [{"type": "text", "text": "Opening"},
     {"type": "tool_use", "id": "u1", "name": "mcp__ai-browser__act", "input": {"steps": ["click e5", "type e7 \"hi\""]}}]}},
    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "u1",
     "content": [{"type": "text", "text": "✓ click e5 41 ms\n✓ type e7 \"hi\" 12 ms\npage  \"Form\""}]}]}},
    {"type": "result", "subtype": "success", "is_error": False, "duration_ms": 2500, "total_cost_usd": 0.01,
     "session_id": "s-1", "result": "Done"},
]


async def test_bridge_streams_text_tools_and_results(fake_claude, tmp_path):
    from ai_browser.app.bridge import ClaudeBridge

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS))
    bridge = ClaudeBridge(tmp_path / "home", claude=str(runner))
    events = [event async for event in bridge.send("click it", "https://s.com/", "Shop")]
    kinds = [event["type"] for event in events]
    assert kinds == ["status", "delta", "delta", "tool", "message_end", "tool_result", "done"]
    assert events[3] == {"type": "tool", "name": "act", "summary": 'click e5 · type e7 "hi"'}
    assert events[5]["lines"][0] == "✓ click e5 41 ms" and not events[5]["is_error"]
    assert bridge.session_id == "s-1"
    argv = json.loads(log.read_text().splitlines()[0])
    for flag in ("--tools", "--strict-mcp-config", "--permission-mode", "--setting-sources"):
        assert flag in argv
    assert argv[argv.index("--allowedTools") + 1] == "mcp__ai-browser__*" and "--bare" not in argv
    sent = json.loads(log.read_text().splitlines()[1])
    assert sent["message"]["content"].startswith("[The user is looking at: Shop — https://s.com/]")
    await bridge.close()


async def test_model_change_resumes_the_session(fake_claude, tmp_path):
    from ai_browser.app.bridge import ClaudeBridge

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS))
    bridge = ClaudeBridge(tmp_path / "home", claude=str(runner))
    [event async for event in bridge.send("one")]
    bridge.model = "haiku"
    [event async for event in bridge.send("two")]
    argvs = [json.loads(line) for line in log.read_text().splitlines() if line.startswith("[")]
    assert argvs[-1][argvs[-1].index("--model") + 1] == "haiku"
    assert argvs[-1][argvs[-1].index("--resume") + 1] == "s-1"
    await bridge.close()


async def test_missing_claude_and_early_exit_are_plain_errors(fake_claude, tmp_path):
    from ai_browser.app.bridge import ClaudeBridge

    runner, _, script = fake_claude
    missing = ClaudeBridge(tmp_path / "home", claude=str(tmp_path / "nope"))
    [event] = [event async for event in missing.send("hi")]
    assert event["type"] == "error" and "Claude Code" in event["text"]
    script.write_text(json.dumps(EVENTS[:2] + [{"exit": 3}]))
    dying = ClaudeBridge(tmp_path / "home", claude=str(runner))
    events = [event async for event in dying.send("hi")]
    assert events[-1]["type"] == "error" and "stopped" in events[-1]["text"]
    await dying.close()
```

- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** `bridge.py`, `tests/fake_claude.py` and the conftest fixture.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Ledger.** Add "Task 3: complete".

### Task 4: App server

**Files:**
- Create: `src/ai_browser/app/server.py`
- Test: `tests/test_app_server.py`

**Interfaces (produced):**
- `AppServer(home: Path, bridge: ClaudeBridge, ports: range = range(8792, 8812))`:
  - `async start() -> str`, which returns the URL;
  - `token`;
  - `allow_origin(origin)`;
  - `async stop()`.
- WebSocket `/ws?token=…`.
  - **Client messages:**
    - `{"type": "send", "text", "tab": {"url", "title"}, "model"}`;
    - `{"type": "stop"}`;
    - `{"type": "new"}`, which resets the session;
    - `{"type": "hello"}`, which replays the current turn's events.
  - **Server messages:** the bridge events, plus `{"type": "busy"}` when a send arrives during a turn.
  - **Rules:**
    - one Claude turn at a time, owned by the server, not the socket;
    - events are kept for the current turn and replayed on `hello`;
    - a bad token or origin: accept, then close with code 4403.
- `GET /health` → `{"ok": true}`.

- [ ] **Step 1: Write the failing tests** (fake `claude` from conftest; `websockets.asyncio.client.connect`)

```python
import json

import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from test_bridge import EVENTS


async def test_server_rejects_strangers_and_relays_a_turn(fake_claude, tmp_path):
    from ai_browser.app.bridge import ClaudeBridge
    from ai_browser.app.server import AppServer

    runner, _, script = fake_claude
    script.write_text(json.dumps(EVENTS))
    server = AppServer(tmp_path / "home", ClaudeBridge(tmp_path / "home", claude=str(runner)))
    url = await server.start()
    server.allow_origin("chrome-extension://good")
    ws_url = url.replace("http", "ws") + "/ws?token="
    try:
        for token, origin in ((server.token, "https://evil.example"), ("wrong", "chrome-extension://good")):
            async with connect(ws_url + token, origin=origin) as ws:
                with pytest.raises(ConnectionClosed) as closed:
                    await ws.recv()
                assert closed.value.rcvd.code == 4403
        async with connect(ws_url + server.token, origin="chrome-extension://good") as ws:
            await ws.send(json.dumps({"type": "send", "text": "hi", "tab": {}, "model": "sonnet"}))
            kinds = []
            while not kinds or kinds[-1] not in ("done", "error"):
                kinds.append(json.loads(await ws.recv())["type"])
        assert kinds[0] == "status" and kinds[-1] == "done" and "tool_result" in kinds
    finally:
        await server.stop()
```

  Also add `test_reconnecting_panel_gets_the_rest_of_the_turn`. It uses a script with `{"sleep": 1}` before `result`:
  socket A sends and closes after the first delta; socket B sends `hello` and must receive `done`. The fake log must
  show one Claude process.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Use the same free-port bind as `live.py` (`_bind`), with uvicorn.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Ledger.** Add "Task 4: complete".

### Task 5: Side panel

**Files:**
- Modify: `src/ai_browser/app/extension/manifest.json`, `worker.js`, `panel.html`, `panel.css`, `panel.js`.
- Test: `tests/test_panel.py`

**Interfaces:**
- **Consumes:** the server protocol (Task 4) and `config.json` (Task 1).
- **Produces:** the panel UI, with these element ids:
  - `#messages`, `#input`, `#send`, `#stop`, `#new`, `#model`, `#page-toggle`, `#page`, `#status`.
- **Rendering:**
  - user bubbles;
  - assistant text streamed into the current bubble;
  - action lines (`.action`, from tool + tool_result lines, ✓ green and ✗ red);
  - the Page view shows the last `page` text.
- **Behaviour:**
  - it reconnects with backoff;
  - the model choice is stored in `chrome.storage.local`;
  - Enter sends, and Shift+Enter makes a newline;
  - every message includes the active tab (`chrome.tabs.query({active: true, lastFocusedWindow: true})`), skipping
    `chrome://` and our own pages.

- [ ] **Step 1: Write the failing test.**
  - Launch the AI Browser (headless) with the extension and an `AppServer` using the fake `claude`. Make the fake
    reply delta contain `<img src=x onerror="document.title='pwned'">`.
  - Open `chrome-extension://<id>/panel.html` in a tab, with an engine `Browser` in app mode connected to
    `app.ws_url`.
  - Use `act` to type "hi" into `#input` and click Send.
  - Then wait for the text "click e5". Assert that the bubble shows the literal `<img`, that there is no `img` element
    in `#messages`, and that `document.title` isn't `pwned`.
- [ ] **Step 2: Run.** Expected: FAIL (the placeholder panel has no UI).
- [ ] **Step 3: Implement the extension:**
  - **`manifest.json`:**
    - `side_panel`;
    - permissions `["sidePanel", "tabs", "storage"]`;
    - `host_permissions` `["http://127.0.0.1/*"]`;
    - `action.default_title` "AI Browser";
    - commands: `_execute_action` with suggested key `Command+Shift+Y` / `Ctrl+Shift+Y`.
  - **`worker.js`:** `setPanelBehavior`.
  - **`panel.*`:** a clean light/dark UI that follows `prefers-color-scheme`.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Ledger.** Add "Task 5: complete".

### Task 6: `ai-browser app` command, docs, live run, final review

**Files:**
- Create: `src/ai_browser/app/run.py`, with `async run_app(home, model="sonnet", headless=False, claude=None,
  ready=None, stop: asyncio.Event | None = None) -> int`.
- Modify: `src/ai_browser/cli.py` (`app` subcommand: `--model {opus,sonnet,haiku}`, `--headless`), `README.md`
- Test: `tests/test_app_run.py`

**Interfaces:**
- `run_app` does the following, in order:
  1. Prepare a token and the extension.
  2. Start the server.
  3. Launch the AI Browser.
  4. Allow the extension origin and give the bridge env `AIB_APP_PROFILE` and `AIB_APP_EXTENSION`.
  5. Call `ready(server_url, app)` when given.
  6. Print: "AI Browser is open. Click its toolbar icon (pin it from the puzzle menu) or press ⌘⇧Y to chat."
  7. Wait until the stop event fires or the browser exits.
  8. Close the bridge, the server and the browser.

  It returns 0, or 1 with a clear message on launch errors (already open, Chrome missing).

- [ ] **Step 1: Write the failing tests.**
  - `run_app(headless=True, claude=fake)` with a `ready` callback: inside it, check the server's `/health`, the browser
    targets, and `config.json`, then kill the browser process. `run_app` must return 0 within 10 s, with the server
    port free again.
  - A second test: a profile already in use → returns 1 with "already open".
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** `run.py` and the CLI subcommand. Add a README section "AI Browser app": what it is, how to
  start it, the panel, extensions, safety, limits.
- [ ] **Step 4: Run** these, then the whole suite. Expected: PASS.
- [ ] **Step 5: Live run with real Claude (Haiku).**
  - Start `run_app(headless=False)` in a scratch driver on the planted QA site.
  - Open the panel page in a tab and send "Open <base>qa/index.html and tell me the page title".
  - Confirm the reply says "QA test home" and that action lines appear.
  - Record the timings in the ledger, and take one screenshot of the panel for the user.
- [ ] **Step 6: Final review.**
  - A fresh reviewer (opus) reviews the app files against this plan's Global Constraints and Review Focus.
  - Fix Critical and Important findings test-first, and record Minor ones in the ledger.
  - Run the full suite and bench, then record "AI Browser app plan: COMPLETE."
