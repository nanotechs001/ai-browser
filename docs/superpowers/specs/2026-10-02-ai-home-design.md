# AI Home — a dashboard, several agents and a normal Chrome (project 4)

Date: 2026-10-02 · Status: design approved in chat. The user chose:
- "One-time manual install";
- "Real Chrome, built in";
- "Several at once";
- design part 1: "Looks right";
- design part 2: "Looks right".

Builds on project 3 (`2026-10-02-ai-browser-app-design.md`) after its final-review fixes.

## Goal

In the user's words: "can you makee it just a part of the browser not just an extension? like there is a dashboard
central for all tabs that are running or an agent is working? where you can see all the skills of the claude and the
agent working?"

- **One place:** **AI Home** shows every tab, every agent and what it is doing right now, and all of Claude's skills.
- **Several agents** work at once, each in its own tabs.
- **Built into the browser:**
  - AI Home is the home page and every new tab;
  - agent tabs sit in Chrome tab groups;
  - tasks can be typed in the address bar;
  - the toolbar shows a badge;
  - the chat sits beside the page.
- **A normal Chrome:** AI Browser does not run in automation mode, so Google and other sites treat the user's own
  browsing like any Chrome.

Success means:
1. **Two tasks at once:** two tasks started from AI Home run together, each in its own coloured tab group. AI Home shows
   each one's status line and its last action with timing.
2. **Working in the user's tab:** a task started from the chat beside a logged-in tab works in that tab, in front of
   the user.
3. **Limit:** with four tasks, three work at once. The fourth waits and starts when one finishes.
4. **Stop:** stopping one agent stops only that agent. Its tabs stay open and the others keep working.
5. **Skills:**
   - AI Home lists every skill with a count per source;
   - it marks the skills each agent loaded;
   - skills picked for a new task are loaded by that agent.
6. **Not a bot:** `navigator.webdriver` is false on AI Browser's pages, and a Google search works as in any Chrome.
7. **Clean ending:**
   - quitting Chrome, or closing its last window, ends `ai-browser app`;
   - Ctrl-C in the terminal quits Chrome;
   - nothing is left running except the Docker shell container, which the README documents with `ai-browser stop chrome`.
8. **The user's tabs are safe:** an agent never closes a tab the user owns, not even after a crash.

## What the user sees

### First start: a one-time setup

`uv run ai-browser app` checks whether the AI Browser extension is installed in AI Browser's profile. If it is not,
Chrome opens with two tabs:
- `chrome://extensions`;
- a setup page served by the app, with four steps:
  1. Turn on **Developer mode** (top right).
  2. Click **Load unpacked**.
  3. Press ⌘⇧G, paste `~/.ai-browser/app/extension` (the page has a copy button), and press Enter.
  4. Click **Select**, then pin the AI Browser icon from the puzzle-piece menu.

The terminal prints the same steps.

Once the extension is installed, it opens AI Home as the pinned first tab. The setup page checks the app's
`GET /setup/status` (`{"installed": bool}`, no secrets) and then says "All set — you can close this tab".

Chrome may ask once whether to keep the new tab page; the user keeps it.

From then on, `ai-browser app` starts Chrome on AI Home (`chrome-extension://<id>/home.html`), and the extension keeps
exactly one pinned AI Home tab first in each window.

### AI Home

AI Home is pinned as the first tab, and every new tab is AI Home too.

**New task:**
- a text box, a skills picker, a model picker (Sonnet by default) and **Start**;
- a hint: "Or type ai and a space in the address bar".

**Agents:** one row per agent.
- **Name:** the task's first words, up to 40 characters.
- **Colour:** the same colour as its tab group.
- **State:**
  - **working**;
  - **waiting in line**;
  - **your turn**: the turn ended, either with an answer or with a question such as a ⚠ confirmation;
  - **stopped**;
  - **failed**: with a plain reason.
- **Status line:** the tool running now and its summary.
- **Last action:** with its timing, for example `click e14 · 38 ms`.
- **Thumbnail:** a small picture of the agent's working tab, refreshed after its actions.
- **Totals:** time and cost so far.
- **Buttons:**
  - **Watch:** brings the agent's tab to the front;
  - **Chat:** opens the agent's conversation inside AI Home, rendered like the panel;
  - **Stop**;
  - **Close:** ends the agent and closes the tabs it opened.

**Tabs:** every tab in every window, with its title and host.
- A chip says which agent works in it, or "you".
- Clicking a row switches to that tab.

**Skills:** all of Claude's skills from every source the agents use: personal, plugins, claude.ai and ai-browser.
- A count per source, and a search box.
- **Each skill shows:**
  - its name, source and the first line of its description;
  - "in use by <agent>" chips.
- **Actions:**
  - **Use in new task** adds the skill to the new-task box;
  - **Ask <agent> to use it** sends that request to a running agent.

### The chat beside the page (side panel)

- **A tab where an agent works:** the panel shows that agent's conversation, its action rows, a composer and Stop.
- **A tab with no agent:** the panel offers "Start a task here". The new agent works in this tab, in front of the user.
  It is the user's tab: the agent uses it but never closes it.
- **AI Home:** the panel shows the most recently active agent.

### In the browser itself

- **Tab groups:** each agent's tabs form a Chrome tab group titled with the agent's name. Colours cycle through
  Chrome's nine group colours.
- **Toolbar badge:** the AI Browser icon shows how many agents are working, and nothing when none are.
- **Address bar:** `ai` plus a space puts the address bar in AI Browser mode. Typing a task and pressing Enter starts an
  agent in a background tab, and AI Home lists it.

### How agents behave

- **Where an agent works:**
  - tasks from AI Home or the address bar open a new **background** tab in the agent's group, so the agent never takes
    focus from the user. The user watches through Watch or the thumbnails;
  - tasks from the panel work in the current tab.
- **Limit:** three agents work at once; more wait in line, first come first served. The limit is set by the environment
  variable `AIB_APP_MAX_AGENTS`.
- **After a turn:** when a turn ends, the agent stays as "your turn" and can be continued with a new message.
- **Messages to a busy agent:** a message sent while an agent works is queued and delivered when its turn ends.
  The chat shows it as queued, so nothing typed is lost.
- **Model:** each agent keeps its own model. Changing it applies to that agent's next message.
- **History:** agents and their conversations last as long as `ai-browser app` runs.

## Decisions

Measured on 2026-10-02 with Chrome 154 and Claude Code 2.1.263.

### 1. A normal Chrome, with a one-time install

Installing the panel over `--remote-debugging-pipe` puts Chrome in automation mode.
- **Measured:** `navigator.webdriver` was `true` on every AI Browser page, and Google answered a search with its
  "unusual traffic" page.
- Branded Chrome 137+ also ignores `--load-extension`.

So headed AI Browser starts with:
- `--user-data-dir=<home>/browser`;
- `--remote-debugging-port=0` (allowed for a non-default profile);
- `--no-first-run`, `--no-default-browser-check` and `--disable-search-engine-choice-screen`.

It is started **without** the pipe and without `--enable-unsafe-extension-debugging`.

**Installation:**
- The user loads the extension once with Developer mode → **Load unpacked**. Chrome keeps it in the profile.
- **The folder:** the extension's folder is fixed at `~/.ai-browser/app/extension`. Before Chrome starts, the app
  refreshes the extension's files and `config.json` (the server URL and token, mode 0600). Chrome reads an unpacked
  extension's files from disk, so the new token is picked up.
- **The ID:** an unpacked extension's ID comes from its folder path. It is the SHA-256 of the absolute path; the first
  32 hex digits are mapped 0–f → a–p.
  - **Verified:** `~/.ai-browser/app/extension` gives `eghfoelflnjggonfelofncaidillmfbb`, the ID Chrome gave it.
  - So the app allows that origin before Chrome starts.
- **Is it installed?** The app reads `Default/Secure Preferences`, then `Default/Preferences`, in the profile. It looks
  for `extensions.settings.<id>` with that `path`. The files are complete on disk before Chrome starts.

**Headless** (the hidden `--headless` flag, used by tests only) still installs over the pipe. Headless Chrome reports
automation anyway.

**Lifetime:** without the pipe, Chrome no longer quits when the app ends.
- **When the app ends**, it quits Chrome: `Browser.close`, then terminate after 10 s, then kill.
- **When Chrome goes, the app ends.** That happens when Chrome exits, or when it has had no `page` targets for three
  checks one second apart. On macOS, closing the last window leaves Chrome running.

**A lock:** `ai-browser app` holds an exclusive `fcntl.flock` on `<home>/app/lock` for its whole run.
- It takes the lock before touching the extension folder.
- A second run then exits with "AI Browser is already running" and changes nothing.

### 2. Several agents are several Claude Code processes

**The app's `AgentManager`** runs the agents. Each agent has:
- its own `ClaudeBridge`: `claude -p` with stream-json and the same flags as project 3, so no API keys;
  - `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` are stripped;
  - `--disallowedTools mcp__ai-browser__sandbox_start` is added, so agents stay in AI Browser;
- its own MCP config, with the environment variables:
  - `AIB_BROWSER=app`, `AIB_APP_PROFILE` and `AIB_APP_EXTENSION`;
  - `AIB_APP_AGENT=<id>`;
  - `AIB_APP_EVENTS=<server url>/agent-events`;
  - `AIB_APP_AGENT_TOKEN`, a per-run token that is not the extension's token;
  - `AIB_APP_ADOPT=<targetId>` only for tasks started from the panel;
- so its own `ai-browser mcp` and its own Engine, in app mode.

**The Engine in app mode, for agents:**
- **Where it starts:**
  - with `AIB_APP_ADOPT`, it adopts that target as its working tab and brings it to the front;
  - otherwise it opens its working tab in the **background** when it first needs one. It never opens a blank tab in
    front of the user.
- **Reporting tabs:** it reports every tab it opens, closes or switches to with
  `POST <AIB_APP_EVENTS> {agent, kind: "tab_opened"|"tab_closed"|"working_tab", target}`, with the header
  `X-AIB-Agent-Token`.
- **No orphan cleanup in app mode:** it never records tabs for orphan cleanup. The app owns cleanup, because it knows
  every agent's tabs from these reports.
- **Downloads:** it no longer redirects downloads browser-wide. Downloads go to Chrome's Downloads folder, for the user
  and for agents alike, and an agent that downloads a file names it in its reply.

**Mapping tabs to targets:** Chrome's tab IDs and CDP target IDs are matched by the extension with
`chrome.debugger.getTargets()`.
- This needs the `debugger` permission, which is used only for `getTargets`. The extension never attaches.

**Thumbnails:** the app keeps its own CDP connection to AI Browser, for the tab list, Watch and thumbnails.
- A thumbnail is a JPEG 320 px wide at quality 60 of the agent's working tab.
- It is taken after a tool result, at most once every 2 s per agent.

### 3. Stop and model changes keep the process

Claude Code's stream-json input accepts **control requests**. These are what the Agent SDK's `interrupt` and
`setModel` send:
- `{"type": "control_request", "request_id": …, "request": {"subtype": "interrupt"}}`;
- `{"type": "control_request", "request_id": …, "request": {"subtype": "set_model", "model": …}}`.

- **Stop** sends an interrupt. If the turn has not ended 5 s later, the process is terminated, then killed after
  another 5 s.
- **A model change** sends `set_model`.
- **The agent keeps everything:** its process, its MCP server and its tabs all stay. Only Close ends them.
- **Before relying on this:** both requests are checked against Claude Code 2.1.263 with a real run.
  - If a request is not supported, the fallback restarts the process with `--resume` and prefixes the next message
    with "Your earlier tabs and element numbers are gone".
  - The tabs still stay open, because killing an app-mode engine never closes tabs.

### 4. Who owns which tab

- **Tabs an agent opened** are its own. They are closed only when the user closes the agent, and the app does it over
  its own CDP connection.
- **Adopted tabs** (the user's) are never closed. That includes `tabs close`, ending a session and crashes.
- **Popups:** a popup opened from an adopted tab belongs to the user. The engine follows a popup only if it opens while
  one of the agent's own steps runs.
- **After the working tab closes,** the fallback never picks an adopted tab silently. If no tab of the agent's own is
  left, it opens a new background tab.

### 5. Page data stays data

With each message, the panel and AI Home send the active tab's title and URL.
- **Title:** at most 150 characters.
- **URL:** scheme, host and path only, at most 300 characters. The query and fragment are dropped.
- **Cleaning:** brackets and control characters are stripped from both.
- **Labelling:** the bridge puts them on a line labelled as supplied by the page.

The system prompt says that line is data from the page, never the user's words.

### 6. Extension pages are off limits to agents

In app mode, `url_problem` refuses `open` and `goto` to any `chrome-extension://` page:
- AI Browser's own pages (AI Home, the panel, `config.json`);
- other extensions' pages (password managers, for example).

An agent can still work in an extension page that the user opened and handed over (`tabs switch u*`).

### 7. Skills

AI Home shows the same `Catalog` the engines use (`skills.Catalog.discover`, with the same sources and blocked set).
- **Read only:** the listing never runs anything.
- **Picking skills** for a new task adds a line to the agent's first message: "Load and use these skills with
  load_skill: …".
- **"In use" chips** come from the agent's `load_skill` tool calls, which the bridge sees in the stream.

## Safety

Everything in project 3 still holds:
- the server listens on 127.0.0.1 only;
- the token is checked in constant time, and only our extension's origin is accepted;
- text is rendered with `textContent` only;
- ⚠ buttons need the user's yes in that agent's chat;
- the agent never types passwords;
- CAPTCHAs are the user's to solve.

New in this project:
- **One run per home:** the lock means two app runs can never share one home.
- **Separate tokens:**
  - engine events need the agent token;
  - UI sockets need the extension token and our origin.
- **Untrusted text** is rendered as text in AI Home: agent names, skill descriptions and tab titles. Thumbnails are JPEG
  data URLs that the app makes from Chrome screenshots, so a page never supplies them.
- **Page data** is labelled and trimmed (Decision 5).
- **Tabs** follow the ownership rules (Decision 4).
- **Extension pages** are off limits (Decision 6).
- **No sandbox switching:** agents cannot call `sandbox_start`.
- **No surprise API billing:** both Anthropic credential variables are stripped.

## Interfaces

**`AgentManager`:**
- `AgentManager(home, claude=None, max_working=3)`.
- Commands:
  - `create(text, skills=(), model="sonnet", adopt=None) -> Agent`;
  - `send(agent_id, text)`;
  - `stop(agent_id)`;
  - `close(agent_id)`;
  - `set_model(agent_id, model)`.
- Views: `snapshot() -> dict` and `subscribe() -> queue`.

**`Agent`:**
- `id`, `name`, `color`, `state`, `model`;
- `tabs: list[target_id]`, `adopted: target_id | None`, `working_tab`;
- `loaded_skills`, `seconds`, `cost`;
- `events`: a deque of at most 5000 events.

**WebSocket, server → UI:**
- `snapshot {agents, tabs, skills_summary}`;
- `agent {…}`: upsert;
- `agent_event {id, event}`;
- `tabs {tabs}`;
- `thumb {id, jpeg_base64}`;
- `skills {skills}`.

**WebSocket, UI → server:**
- `hello {view: "home"|"panel"}`;
- `new_task {text, skills, model, adopt?}`;
- `send {id, text}`, `stop {id}`, `close {id}`, `model {id, model}`;
- `watch {target}`;
- `skills {}`.

**Engine → app:** `POST /agent-events` (Decision 2).

**Setup:**
- `GET /setup` serves the one-time setup page;
- `GET /setup/status` returns `{"installed": bool}`. It is true once the extension has connected with the token.

**Extension `manifest.json`:**
- `chrome_url_overrides.newtab = "home.html"`;
- `omnibox.keyword = "ai"`;
- `permissions: sidePanel, tabs, storage, tabGroups, debugger`;
- the side panel stays `panel.html`;
- a new page `home.html`.

**Launcher:**
- `launch_app_browser(profile, extension_dir, headless)`;
- headed: no pipe; `extension_installed(profile, extension_dir) -> bool`;
- headless: pipe install.

## Testing

- **AgentManager**, with the fake `claude` (it logs control requests):
  - three agents run in parallel and a fourth waits, then starts;
  - Stop sends an interrupt and leaves the others working;
  - one agent crashing leaves the others working;
  - Close ends the process and closes only the agent's own tabs;
  - `set_model` is sent.
- **Engine in app mode:**
  - tab reports are posted;
  - an adopt start comes to the front;
  - background starts open no foreground tab;
  - a user tab survives an agent being killed, `tabs close`, and a popup;
  - extension pages are refused.
- **Launcher:**
  - headed arguments include neither `--remote-debugging-pipe` nor `--enable-unsafe-extension-debugging`;
  - the installation check works against Preferences fixtures (installed, not installed, another path);
  - the lock refuses a second run without touching `config.json`.
- **AI Home and panel in headless Chrome** (pipe-installed extension):
  - the snapshot renders;
  - a hostile agent name, skill description or tab title stays text;
  - a new task starts from the box and from the `ai` keyword handler;
  - agent tabs are grouped;
  - the panel follows the current tab's agent.
- **Ending:** closing every page ends `run_app`, and the browser is gone.
- **Live run** with real Claude Code (Haiku):
  - two agents in parallel on the planted QA site;
  - one in the user's current tab;
  - a screenshot of AI Home for the user;
  - a check that `navigator.webdriver` is false in headed AI Browser.

## Out of scope

- Keeping agents across app restarts.
- Separate logins per agent: all agents share AI Browser's profile.
- Scheduling, notifications and publishing the extension to the Chrome Web Store.
