# AI Browser app — a browser with a Claude side panel (project 3)

Date: 2026-10-02 · Status: design approved in chat ("Browser + chat side panel but have like JEv ultrafast browse
feature for interacting", then "Yes, use Google Chrome").

## Goal

An app like Claude: chat on one side, a browser on the other.

- **Own browser:** the browser belongs to the agent, has its own profile, and can use and install Chrome extensions.
- **Local Claude:** the brain is Claude Code on this Mac, signed in with the user's Claude account (no API keys).
- **Fast hands:** the ai-browser engine works the jev-ultrafast way, with numbered elements, guarded batched steps and
  screenshots only when needed. It is far faster than Claude in Chrome.

## What the user sees

1. Run `uv run ai-browser app`. **AI Browser** opens: a Google Chrome window with its own profile at
   `~/.ai-browser/browser/` (its own logins and extensions), separate from the user's Brave.
2. Click the AI Browser toolbar icon, or press ⌘⇧Y, to open the chat side panel.
3. Type a task. Claude works in the tab beside the panel. The panel streams Claude's reply and logs each action as it
   runs (`✓ click e12 · 41 ms`). A **Page** view shows the numbered elements of the page Claude last read, like
   jev-ultrafast's inspector.
4. The panel has three controls:
   - **model picker:** Opus (best), Sonnet (balanced), Haiku (fastest);
   - **Stop**;
   - **New chat**.
5. Each message also tells Claude which tab the user is looking at (its URL and title), so "this page" works.
6. **Extensions:** the user installs them from the Chrome Web Store as usual, and Chrome's own "Add extension"
   confirmation is always theirs to click. Claude uses them as they appear in pages, and can open an extension's own
   pages (`chrome-extension://…`) in a tab.

## Decisions (with what was measured on 2026-10-02, Chrome 154, Claude Code 2.1.263)

- **Launching the AI Browser:** Google Chrome with `--user-data-dir=~/.ai-browser/browser`, `--remote-debugging-port=0`
  (the engine connects as usual, with no "Allow" prompt), `--remote-debugging-pipe` and
  `--enable-unsafe-extension-debugging`.
  - Over the pipe, the launcher installs the side panel with `Extensions.loadUnpacked`.
  - Measured: this works, the port endpoint works alongside it, and the extension does *not* survive a restart. So the
    launcher loads it at every start.
  - Branded Chrome 137+ ignores `--load-extension`, which is why the pipe is used.
  - The launcher keeps the pipe open for the browser's life.
  - The side panel is copied to `~/.ai-browser/app/extension/` together with a `config.json` (server URL and token).
    Its ID follows from that fixed path.
- **Engine "app" mode** (`AIB_BROWSER=app`, profile from `AIB_APP_PROFILE`, default `~/.ai-browser/browser`):
  - **connection:** like the user's-own-Chrome mode (reads `DevToolsActivePort`);
  - **tabs:** new tabs open in the **foreground**, and `tabs list` shows every page tab in the AI Browser;
  - **adopting tabs:** `tabs switch` to a tab the user opened adopts it, and it is left open at the end;
  - **pages it may open:** `chrome-extension://` pages are allowed, while `file://` and `chrome://` stay blocked;
  - **downloads:** go to the task's work folder;
  - **size:** the real window size is kept (no viewport override);
  - **live view:** not used, since the browser is visible.
- **Bridge to Claude** (no API keys). One `claude -p` process per chat, run in `~/.ai-browser/app/`, with:
  - `--input-format stream-json --output-format stream-json --verbose --include-partial-messages`;
  - `--tools ""` (no Bash, file or web tools);
  - `--strict-mcp-config --mcp-config <ai-browser, env AIB_BROWSER=app>`;
  - `--allowedTools "mcp__ai-browser__*"`;
  - `--permission-mode dontAsk`;
  - `--setting-sources local` (no user hooks or plugins);
  - `--model <picker>`;
  - `--append-system-prompt <panel instructions>`.

  Changing the model restarts the process with `--resume <session id>`. `--bare` is never used, because it skips the
  keychain, which holds the login.

  Measured: `apiKeySource: none`, all 17 tools are ai-browser's, the MCP server shows `connected`, and the first answer
  took 4.3 s including startup.
- **App server:** Starlette + uvicorn on `127.0.0.1` (first free port from 8792), with a random token.
  - The panel connects to the WebSocket `/ws?token=…`, and only from our extension's origin.
  - It relays panel messages to the bridge and bridge events back to the panel.
- **Side panel (MV3):**
  - permissions `sidePanel`, `tabs` and `storage`;
  - host permission `http://127.0.0.1/*`;
  - `openPanelOnActionClick`;
  - a ⌘⇧Y command for `_execute_action`.

  Model text is shown as text, never as HTML, because pages may have planted words in it.
- **CLI:** `ai-browser app` starts the server, launches the AI Browser, prints how to open the panel, and runs until
  Ctrl-C or until the browser closes.
  - The browser lives as long as the launcher's pipe, so it closes with `ai-browser app`.
  - If the profile is already in use, for example by an AI Browser started in another terminal, the command says so
    and exits.

## Safety

- **Claude's reach:** the panel's Claude has only ai-browser's tools: the browser, the Docker-sandboxed shell and the
  skills. It can't touch the Mac's files or terminal.
- **Risky actions:** ⚠ steps still need the user's yes in the chat.
- **Logins:** the user logs in in the visible window, never Claude.
- **Page text:** treated as data.
- **Server:** a token plus an origin check, so websites can't use it.
- **Debugging port:** like any Chrome started with a debugging port, other programs on this Mac can connect to the
  AI Browser's port. The profile is dedicated, which limits the risk; the README says so.

## Interfaces

- **`ai_browser/appbrowser.py`:**
  - `AppBrowser(process, ws_url, extension_id)`;
  - `launch_app_browser(profile, extension_dir, headless=False) -> AppBrowser` (refuses a profile already in use);
  - `close()`.
- **`Browser(mode="app")` and `url_problem(url, "app")`:** `Browser.tabs("list")` in app mode lists every page tab.
- **`ai_browser/app/bridge.py`:** `ClaudeBridge(claude="claude", home, model)`, with:
  - `async send(text, tab_url, tab_title) -> AsyncIterator[dict]`, which yields panel events;
  - `stop()`, `close()`.
- **Panel events:** `{"type": …}` where the type is one of:
  - `delta {text}`, `message_end`;
  - `tool {name, summary}`, `tool_result {name, lines, is_error}`;
  - `done {seconds, cost}`;
  - `error {text}`, `status {model, connected}`.
- **`ai_browser/app/server.py`:** `AppServer(home, bridge_factory)`, with `start() -> (url, token)` and `stop()`.
- **`ai_browser/app/extension/`:** `manifest.json`, `worker.js`, `panel.html`, `panel.css`, `panel.js`.
- **CLI:** `ai-browser app [--model sonnet]`.

## Testing

- **Launcher:** with a throwaway profile, the extension is loaded, its worker target exists and the engine connects.
  A second launch on the same profile is refused with a clear message, and closing the launcher closes the browser.
- **App mode:**
  - foreground tabs;
  - `tabs list` shows user tabs, and `tabs switch` adopts one;
  - `chrome-extension://` pages open, while `file://` and `chrome://` don't;
  - adopted tabs survive the end of the session.
- **Bridge:** a fake `claude` script that emits recorded stream-json is used for parsing, tool summaries, model
  switches (resume), stop, and a clear error when `claude` is missing.
- **Server:** the token and origin checks, and relaying a conversation (fake `claude`).
- **Panel:**
  - load the extension in a throwaway headless Chrome and open `panel.html` as a tab;
  - the engine types a message;
  - the streamed reply and action lines appear;
  - HTML in replies stays text.
- **End to end:** one real run with Haiku on the planted QA site ("open the QA test site and tell me the title").
- **Also in this project:** finish wiring the Website QA tool (its Tasks 7–8), so "QA this site" works in the panel.
