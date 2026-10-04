# The app as an app window

Date: 2026-10-03.

## Status

Status: the user approved the design in chat and answered its four questions; this spec was written and reviewed by agents without a user review round.

**The user's choices**, from chat (the brief's "The user's answers"):
- "App window, no browser look".
- **The browser that draws the window, on the Mac:** Google Chrome (Recommended), changeable in Settings.
- **AI Browser's own Chrome for agents:** "drop it" (Recommended). Agents use the chosen browser, or the Docker
  sandbox.
- **The defaults the brief listed, taken as they are:**
  - closing the app window stops the app and its agents, as today;
  - the window starts with the autoplay flag, in AI Browser's own window profile only;
  - the "ai" keyword moves to Brave, through the watcher.

**This is wave 3 of five.** The brief is `2026-10-03-app-as-an-app-overview.md` (section 3). The investigators'
findings are in `2026-10-03-app-as-an-app-investigation.json` (the `appwindow` key). "Finding 6" is the sixth entry of
that key's `findings`, counted from 1, as the browser-detection spec counts them. A1, B4 and so on are the probe runs
those findings name. The waves:
- **wave 1:** brain-delegation and watcher-safety, in parallel;
- **wave 2:** cdp-relay and browser-detection, in parallel;
- **wave 3:** this spec, alone, because it rewrites `app/run.py` and `app/server.py`;
- **wave 4:** browser-profile-choice;
- **wave 5:** side-chat.

**Builds on the merged waves 1 and 2:**
- **brain-delegation (1A):** its page changes (agent numbers, "Your tabs", `agentLabel` in `chat.js`) are in the files
  this spec moves, and `Agent.number` names the agent in the keyword's notification (Decision 11).
- **watcher-safety (1B):** `_role(ws)`, the `MESSAGE_RULES` table with `may_send`, and `WATCHER_RECEIVES` with
  `for_watcher`. This spec maps the window's sockets to the role `"app"`, and adds rows to both tables.
- **cdp-relay (2A):** the `/cdp` route, per-agent tokens, and BraveLink and TabWatch moved onto the relay. This spec
  puts `/cdp` behind the same Host check as every other route. The relay itself doesn't change. Its brave-mode-only
  parts (the route, `AIB_APP_CDP`) now always apply, because brave mode is the only mode left (Decision 12).
- **browser-detection (2B):** `browsers.installed()` (each `Installed` has `id`, `name`, `window`, `binary` and, on
  macOS, `bundle`), `browsers.os_default()`, `browsers.for_data_dir()`, `browsers.running()` and
  `browsers.all_data_dirs()`. This spec uses them to find the browser that draws the window, and the agents' browser
  for links.

**Line numbers** (`file.py:12`) are from HEAD `946d5f0`, before waves 1 and 2. Those waves move some of them, so the
plan finds each place again by its name.

## Amendment (2026-10-04): one window, its pages in a tab menu

**What the user asked,** after using the merged wave: "also for the UI i do not want a popup new window switching
control center, AI home etc. Just implement like a tab menu that I can switch in the tab i toggle , add that in
pipeline change". They then picked "Yes, build it next (Recommended)" for the design below. Built on branch
`tab-menu` from `607396d`; its ledger is `.superpowers/sdd/tab-menu/progress.md`.

**What the user sees now:**
- **A row of tabs under the title bar:** AI Home · Mission Control · Settings. A click shows that page in the same
  window, and the active tab is marked. The window still has no browser tabs and no address bar.
- **The title follows the tab** and keeps AI Home's count: "Mission Control · AI Browser", "(2) Mission Control · AI
  Browser" while two agents work.
- **Each page stays alive.** It loads the first time its tab is picked, and is then only hidden. Nothing resets: a
  half-typed message, the scroll, Mission Control's room.
- **Closable tabs** at the end of the row, each with a ×: the setup steps (the Brain's **Set it up**, and **Show me
  how** for Brave's switch, which opens the same tab at its other section), and an agent's live view (**Show me** on a
  bot check in QA's sandbox). A second Show me for the same agent goes to its open tab.
- **No popups.** A link or button between our pages switches tabs. A website still opens in the user's browser
  (`open_url`).

**What changed, decision by decision:**
- **Decision 5:** a valid code (and a reload with the cookie, and `/`) redirects to `/app`, the tab menu, not `/home`.
  `GET /app` serves `ui/app.html` with the cookie, like every page.
- **Decision 6:** the headers depend on the path, and nothing else changes.
  - **`/app`** adds `frame-src 'self' http://127.0.0.1:8770 … http://127.0.0.1:8790` (each of `LIVE_PORTS`, where
    every engine's live view binds; a CSP can't name a port range) and keeps `frame-ancestors 'none'`.
  - **`/home`, `/mission`, `/settings` and `/setup`** have `frame-ancestors 'self'`: only the tab menu may frame them.
  - **Every other answer** keeps the strict headers as they were, a refused Host too.
- **Decision 7:** popups for our pages become tabs.
  - `nav.js` keeps `guardLinks`, and `openWindow`, `focusHome` and `WINDOWS` become `openTab(path)` and
    `openLive(url, agent, label)`. A page asks with `window.parent.postMessage({type: "tab", path} or {type: "live",
    url, agent, label}, location.origin)`.
  - The tab menu (`ui/app.js`) takes a message only if `event.origin` is its own and `event.source` is one of its own
    pages' frames, and only for `/home`, `/mission`, `/settings`, `/setup#…` or a live view's address (the
    `CHECK_LIVE` pattern, with an agent id).
  - `check.js` imports nothing still: `checkCard` takes `openLive` from its caller, as `brainui.js` takes `openSetup`.
  - **The live view opens as a tab.** It is our own `live.py` on 127.0.0.1, it sends no framing header, and neither
    server logs requests. Its frame is `sandbox="allow-scripts"`, so it can't navigate the window, open a window or
    reach our pages, and Chrome runs it in a process of its own. Its address never becomes a top-level history entry,
    as the old popup's did.
  - The table of windows (`aib-home`, `aib-mission`, `aib-settings`, `aib-setup`, `aib-live`) goes. No script in
    `ui/` opens a window any more; the only `"_blank"` left is still `brainui.js`'s anchor in Brave.
  - A page opened by itself (tests, by hand) still works. There, `openTab` moves the page to the asked one, and
    `openLive` does nothing.
- **Decision 8:** the window's sockets are its tabs' pages. AI Home's is there from the start, and Mission Control's
  and Settings' join when first picked. Switching tabs never ends the app, and neither does closing a closable tab:
  the setup steps have no socket, and a live view's socket goes to the live view, not the app. Closing the window ends
  it as before. "A Mission Control or Settings window still open keeps the app running" no longer arises.
- **Hiding a tab:** `visibility: hidden` plus `content-visibility: hidden` on the box around its frame, never
  `display: none`, which loses the page's scroll. A hidden page draws nothing until it is shown again.
- **Testing:** `tests/test_tab_menu.py` (the real headless browser) replaces the popup tests: state kept across a
  switch, the active tab marked, the title, setup and the live view as closable tabs (a second Show me goes to the
  first), a link to `/settings` inside a page, a website link sending `open_url`, closing a live view's tab ending its
  socket while the app runs on, and the messages the tab menu refuses. `test_app_run.py` checks that switching and
  closing tabs never end the app and closing the window does. `test_ui_static.py` forbids `window.open`, popup
  features and link targets in `ui/`.

**Unchanged:** the plain window (no browser tabs, no address bar, no debugging port or flag), the window's command
line, closing the window to stop the app, the cookie and the one-time code, Brave's `ai` keyword, and the rest of
this wave.

## Goal and success criteria

AI Browser's pages (AI Home, Mission Control, the Brain's views and the new Settings page) become one plain app
window. The app server serves them over http. An installed browser shows them in Chrome's `--app` mode, on a profile of
the app's own, with no debugging port. AI Browser's own Chrome, its extension and the engine's app mode retire.

Success means:
1. **One plain window.** `uv run ai-browser app` opens one window with a title bar only: no tabs and no address bar.
   Its pages report `display-mode: standalone`. Nothing is loaded by hand.
2. **No debugging, no bar.**
   - The window never causes an "Allow remote debugging?" question or an automation bar.
   - `navigator.webdriver` is false in it.
   - Its profile never holds a `DevToolsActivePort`.
   - Its command line has no debugging or automation flag.
3. **Pages from the app server.**
   - AI Home, Mission Control and Settings work over `http://127.0.0.1:<port>`.
   - Mission Control, Settings, the setup page and the live view open as small app-style windows.
   - No code path opens a tabbed browser window.
4. **Only the window gets in.**
   - A page needs the window's session cookie. That cookie is set only by swapping a one-time code.
   - A page opened any other way (typed into Brave, opened by an agent) gets a plain 403 page and no socket. The
     setup page is the one page that opens anywhere, and it holds no secret.
5. **Hardened.**
   - Every route, HTTP and WebSocket, checks the Host header.
   - Every response carries a strict Content-Security-Policy.
   - `/setup` holds no secret, and showing the watcher's folder needs the window's cookie.
6. **Closing.**
   - Closing the last AI Browser window ends the app. About 5 s later it ends its agents, its server and the browser
     process it started.
   - Ctrl-C closes the window.
7. **Settings on the server.**
   - The model, Voice and the window's browser are saved in `<home>/settings.json`.
   - The port is remembered, so the microphone grant survives a restart.
8. **Voice.** In Google Chrome, Mission Control speaks updates without a click first.
9. **The keyword.** "ai", a space and a task in Brave's address bar starts an agent, through the watcher.
10. **Retired.**
    - AI Browser's Chrome, its extension, its side panel and the engine's app mode are gone.
    - `--browser app`, `AIB_APP_BROWSER=app` and `AIB_BROWSER=app` each give one plain message, never a guess.
11. **Windows.** Microsoft Edge draws the window by default.
12. **Tests.**
    - The UI tests run on a rebuilt fixture with no extension.
    - Each test listed under Testing fails before this wave where it says so, and passes after.

## What the user sees

### Starting

- **`uv run ai-browser app`** opens a window titled **AI Home**:
  - a title bar only, with no tabs and no address bar;
  - on this Mac it is drawn by Google Chrome (Settings' **Auto** picks Chrome because Brave is the everyday browser);
  - the Dock shows Google Chrome's icon while AI Browser is open. If the user's own Chrome is open too, the Dock shows
    two Chrome icons.
- **No question, no bar** for the window itself. Brave still asks once for the app's own connection (wave 2's
  relay), as before.
- **The first start** needs no extension. These one-time steps are about Brave only:
  - the terminal prints the watcher's steps, as today (`run.py:66-72`);
  - Finder shows the watcher folder once, as today;
  - in the window, AI Home's browser card and the Brain's "Set it up" link lead to the setup page.

  The setup page no longer opens by itself, because a page can't open a window without a click.
- **The terminal says:**
  ```
  AI Browser is open in its own window: AI Home shows every agent, tab and skill.
  With the watcher in Brave, type ai and a space in Brave's address bar to start a task from there.
  Close the window, or press Ctrl-C here, to stop.
  ```

### Inside the window

*Amended 2026-10-04 ([one window, its pages in a tab menu](#amendment-2026-10-04-one-window-its-pages-in-a-tab-menu)):
Mission Control, Settings, the setup steps and the live view are tabs of this one window, not windows of their own.*

- **AI Home** looks as today, with these changes:
  - its header gains a **Settings** button beside **Mission Control**;
  - the hint under the task box reads "Or type ai and a space in Brave's address bar";
  - the empty agent list reads "No agents yet. Start a task above." The words "or open the chat beside any page" go
    until wave 5 brings that chat back in Brave;
  - the title shows how many agents are working: "(2) AI Home". It replaces the old toolbar badge.
- **Mission Control** opens in a second, smaller window (1280 × 860).
  - A second click brings that window to the front. It never opens two.
  - Its **AI Home** button brings the main window to the front.
- **Settings** opens in a small window (720 × 760). It has one section in this wave, **App window**:
  - "Which browser draws AI Browser's window": **Auto (Google Chrome)**, **Google Chrome**, **Brave**, and
    **Microsoft Edge** on Windows only;
  - a browser that isn't installed is greyed out, with "not installed";
  - "This window: Google Chrome. A change applies the next time AI Browser starts."

  Wave 4 adds "Where agents browse" to the same page.
- **The model and Voice are remembered by the app**, not the browser:
  - a model picked in AI Home shows in Mission Control too;
  - both survive a restart.

  The choices saved in the old extension are not carried over. The user picks them once more.
- **Talking:**
  - the first time the user talks, the window asks for the microphone (and macOS asks once for Google Chrome);
  - after a restart it doesn't ask again, because the window comes back on the same address.
- **Voice** speaks updates right after start, with no click first. That was measured in Google Chrome. In Brave or Edge
  it may still need one click on the page, as today.
- **Links:**
  - the setup steps and an agent's live view open as small windows;
  - a website opens in the user's Brave (the agents' browser), never in the app window.

### Elsewhere

- **The "ai" keyword lives in Brave now.**
  - The watcher reloads itself with the new build, as today, and gains the keyword.
  - Typing `ai`, a space and a task in Brave's address bar starts an agent, or a workflow whose name the text starts
    with.
  - Brave shows a notification: "Started 4 · Fix the footer. See it in AI Browser's window."
  - With the app not running, the notification says "AI Browser isn't running: start it with `uv run ai-browser app`".
- **An AI Browser address typed into Brave**, such as `http://127.0.0.1:8792/home`, shows: "AI Browser's pages open
  only in its own window. Start it with `uv run ai-browser app`."
  - The setup page is the one exception. It opens anywhere (the watcher's "Set it up" link opens it in Brave).
  - There, "Show the folder" gets a 403 from the server and says "This button works in AI Browser's own window". The
    folder's path is still shown to copy.

### Closing

*Amended 2026-10-04 ([one window, its pages in a tab menu](#amendment-2026-10-04-one-window-its-pages-in-a-tab-menu)):
the window's tabs are its pages, so only closing the window ends the app.*

- **Closing the window** ends the app, as today: the agents end, and the terminal returns.
  - If Mission Control's or Settings' window is still open, the app keeps running until the last AI Browser window
    closes.
  - **⌘Q** in the window does the same.
  - **Ctrl-C** in the terminal closes the window.

### What goes away

- **AI Browser's own Chrome** and its extension: the user loads nothing by hand any more.
- **The chat beside the page** (AI Browser's side panel). It comes back inside Brave's watcher in wave 5 (the
  side-chat spec). Until then, each agent's chat is in AI Home's drawer and in Mission Control.
- **⌘⇧Y** and the toolbar badge.
- **The old profile, `~/.ai-browser/browser/`,** is no longer used. It may hold logins the user made in AI Browser's
  old Chrome. The app never deletes it; the README says it can be deleted by hand.

### On Windows

- **Microsoft Edge draws the window by default** (Auto). The taskbar shows Edge's icon.
- **Closing, and Ctrl-C,** close the window the way its × does, so Edge doesn't offer "Restore pages?" at the next
  start (Decision 15).
- Everything else is the same, with Ctrl in place of ⌘, File Explorer in place of Finder, and the taskbar in place of
  the Dock.

## Decisions (with reasons)

### 1. One app window, drawn in `--app` mode, with no debugging port

- **What:** the window is an installed Chromium browser started with `--app=<url>`, on a profile of the app's own,
  with no debugging port or pipe.
- **Why:**
  - **The window is plain.** Measured in a throwaway Chrome 154 (finding 6): one window, a title bar only,
    `display-mode: standalone`, 32 px above the page, against 87 px in a normal window.
  - **It isn't automated.** `navigator.webdriver` is false and no `DevToolsActivePort` is written (finding 6). Brave
    152 behaves the same (finding 8).
  - **A port would bring the bar back.** The same window with `--remote-debugging-port` alone reports
    `navigator.webdriver` true, and gains a 56 px bar (finding 7). So the window never gets one: no
    `--remote-debugging-port`, no `--remote-debugging-pipe`, no `--enable-automation`, no `--load-extension`.
  - **Nothing drives it.** Agents never browse there. The app never connects to it; it only starts the process and
    later ends it.
- **Rejected: keeping AI Browser's Chrome** (`appbrowser.py:1-11`, started with `--remote-debugging-port=0` at
  `appbrowser.py:108-116`). It is automated by that flag, Google refuses sign-in there, and it needs the extension
  loaded by hand.

### 2. Which browser draws the window

- **A Settings choice:** `window_browser`, one of `auto`, `chrome`, `brave` and `edge`. It is saved in
  `<home>/settings.json` (Decision 9).
- **What each system offers:**
  - macOS and Linux: Auto, Chrome and Brave;
  - Windows: Auto, Edge, Chrome and Brave.
- **The order Auto tries:**
  - macOS and Linux: Chrome, then Brave;
  - Windows: Edge, then Chrome, then Brave.
- **On macOS, the everyday browser is skipped.** Auto skips the OS's default browser (`browsers.os_default()`) when
  another candidate is installed:
  - on this Mac the default is Brave, so Auto picks Chrome, which is the user's choice;
  - this keeps the app window and the everyday browser in different apps. macOS hands a link clicked in another app
    to a running copy of the default browser's app, which could be the window's copy (the brief's risk, not
    measured).
  - **Not on Windows or Linux.** There a link from another app starts the browser on its default profile folder, and
    Chromium passes it to the process of that folder, never to one started with another `--user-data-dir`. So Auto
    on Windows is always Edge first, which matches the brief ("Edge on Windows"). Not measured; a laptop check.
- **A choice that can't be used:** an explicit choice that isn't installed, or Edge on a Mac, falls back to Auto. A
  one-line note goes to the terminal and to the Settings page: "Brave isn't installed: the window uses Google Chrome.
  Change it in Settings."
  - This is the app's own window, not the agents' browser, so the "never switch browsers" rule doesn't apply.
  - The fallback keeps the user able to reach Settings.
- **No browser at all:** the app exits 1 with "AI Browser needs Google Chrome, Brave or Microsoft Edge to draw its
  window: install one, then start again."
- **For one run only:** `ai-browser app --window auto|chrome|brave|edge` overrides the setting for that run and saves
  nothing.
- **Finding the program:**
  - the candidates are wave 2B's `browsers.installed()` rows with `window` true (Brave, Chrome and Edge), and each
    row's `binary` is the program started. 2B already knows Edge's Windows places and its App Paths key;
  - Chrome keeps `AIB_CHROME_BINARY` first (`chrome.py:87-93`), for tests and CI. When it names a file, it is
    Chrome's program and Chrome counts as installed, whatever `installed()` says;
  - on Linux, where `installed()` returns `[]`, Chrome and Brave come from `chrome.chrome_binary()` and
    `chrome.brave_binary()` (`chrome.py:87-98`), as today.
- **A profile per browser:** `<home>/app/window/chrome`, `…/brave` and `…/edge`.
  - Two Chromium brands, or versions, must not share a profile folder.
  - The microphone grant lives in that profile. So switching the window's browser asks for the mic once more; the
    Settings page says so.
  - The launcher refuses a profile folder that is, or is inside, any browser's real data folder
    (`browsers.all_data_dirs()`), as `chrome.launch` already refuses the user's own (`chrome.py:170-171`).
- **A change applies at the next start.** Swapping the browser under a running window is out of scope.

### 3. The window's command line

- **New module `src/ai_browser/app/window.py`.** It replaces `launch_app_browser` (`appbrowser.py:274-317`, called at
  `run.py:201`).
- **`window_args(binary, profile, url)` returns exactly:**
  ```
  <binary> --user-data-dir=<profile> --app=<url> --no-first-run --no-default-browser-check
           --disable-search-engine-choice-screen --window-size=1440,960 --autoplay-policy=no-user-gesture-required
  ```
  - A test pins this list.
  - `AppWindow` takes an `extra_args` tuple for one test only (`--headless=new`). The product never passes it.
- **The autoplay flag.**
  - Without a click, `speechSynthesis.speak()` fails with `not-allowed` in Chrome and Brave app windows (finding 10).
  - With the flag, it speaks in Chrome (run A3). Brave and Edge with the flag weren't measured; `voice.js`'s click
    fallback covers them.
  - The flag applies only to the browser process started on AI Browser's own window profile. It changes nothing about
    what sites see, and no site is loaded there.
  - `voice.js`'s click fallback (`voice.js:81-85`) stays, for those browsers and for any window whose browser
    doesn't honour the flag.
- **Started with a plain `subprocess.Popen`,** with stdout and stderr to devnull, on every system. No extra descriptors
  are needed, so `posix_spawn` and the pipe (`appbrowser.py:119-263`) go.
- **The URL** is `http://127.0.0.1:<port>/open?code=<one-time code>` (Decision 5).
- **Hand-off.** A browser may already be running on that profile, left from a crashed run.
  - `launch()` asks first: `browsers.running(profile)` (wave 2B) reads the profile's own lock (`SingletonLock` on
    macOS and Linux, `lockfile` on Windows) and never opens a connection.
  - When it is True, the launch is a hand-off. The new process passes its command line to that browser (Chromium's
    process singleton) and exits; that browser opens the new window, which works. Nothing relies on the new
    process's exit code.
  - The app can't end that browser at the end. `close()` ends nothing and returns a note: "AI Browser's window was
    opened by a browser already running on its profile: quit it yourself (⌘Q)", or "(close its windows)" on Windows
    and Linux.
  - When `running()` is False or None, the launch is the app's own, and `close()` ends it (Decision 8).
  - The app never kills a process it didn't start.

### 4. The pages move to `app/ui/` and are served by the app server

- **The move:** `src/ai_browser/app/extension/` becomes `src/ai_browser/app/ui/`.
  - **What moves with the files, as merged:** wave 1A's numbers, Your tabs, send and inbox cards (`chat.js`,
    `scene.js`, `mission.js`, `tablist.js`, `home.js`, `talk.js`, `brainui.js`, `voice.js` and their CSS), wave 1B's
    `permission.js` option and tab-list lines, and wave 2A's connected-clients list and texts (`home.js`,
    `home.html`). This wave's own edits go on top of them. The move is a `git mv`, so their history follows.
  - **Deleted:** `manifest.json` and `worker.js`.
  - **Staying behind in `app/extension/`:** only `panel.html`, `panel.js` and `panel.css`. They are not served or
    shipped to any browser. They are the source the side-chat spec (wave 5) ports into the watcher, and it deletes them
    then ("retiring `extension/panel.*`" in the brief).
  - **Moved too:** `app/setup.html` becomes `ui/setup.html`. Its inline `<style>` (`setup.html:7-38`) moves to
    `ui/setup.css`, and its inline `<script>` (`setup.html:92-142`) to `ui/setup.js`, because the CSP forbids inline
    code.
  - **New files:** `ui/settings.html`, `ui/settings.js`, `ui/nav.js`, and `ui/icon.png` (a copy of the watcher's
    icon, for the title bar and taskbar).
- **The watcher's shared files** come from `app/ui/`: `brain/watcher.py:19` `SHARED_SOURCE = APP / "ui"`. Its list
  (`watcher.py:20`) keeps `link.js`, `brainui.js`, `brainui.css` and `permission.js`.
- **Routes**, all on the existing Starlette app (`server.py:202-210`):
  - `GET /` gives 303 to `/home`;
  - `GET /open?code=…` is the swap (Decision 5);
  - `GET /home`, `/mission` and `/settings` give `home.html`, `mission.html` and `settings.html`;
  - `GET /setup` gives the setup page;
  - `GET /<file>` serves a `.js`, `.css` or `.png` file that is in `app/ui/`;
    - the list of names is read once at start;
    - no other path is served, and `..` or `/` inside a name gives 404;
  - the existing `/health`, `/setup/status`, `/setup/reveal`, `/agent-*` and `/ws`, and wave 2's `/cdp`, stay.
- **Which routes need the window's cookie:**
  - all pages and files need it, except `/setup`, `setup.css`, `setup.js` and `icon.png`;
  - without it, the answer is 403 with a plain page and no script: "AI Browser's pages open only in its own window.
    Start it with `uv run ai-browser app`."
  - **Why:** the HTML holds no secret, but a page without the socket is useless, and a clear message beats a page that
    never connects.
- **Relative addresses keep working.** Pages are served at `/home` and `/mission`, so `home.css` and `./link.js`
  resolve to `/home.css` and `/link.js`.
- **Content types:** `text/html; charset=utf-8`, `text/javascript; charset=utf-8`, `text/css; charset=utf-8` and
  `image/png`.

### 5. A one-time code, swapped for an HttpOnly cookie

- **At each start, the server makes `ui_secret`** (`secrets.token_urlsafe(32)`).
- **Before each launch, `new_launch_code()` makes a code:**
  - `secrets.token_urlsafe(32)`;
  - single use, valid for 60 s (`CODE_TTL`);
  - kept in a dict of code to expiry; expired codes are dropped whenever a new one is made.
- **`GET /open?code=…`** compares the code with each pending one using `hmac.compare_digest`, then removes it.
  - **A valid code:** 303 to `/home`, with
    `Set-Cookie: aib_ui_<port>=<ui_secret>; HttpOnly; SameSite=Strict; Path=/`.
  - **No `Max-Age`:** the cookie lives for the browser session only.
  - **No `Secure`:** it adds nothing for a host-only `127.0.0.1` cookie, and Edge's handling of it over http is
    unmeasured. (Chrome and Brave accepted it, finding 13.)
  - **The redirect drops the code** from the window's address and history. `Referrer-Policy: no-referrer` keeps it out
    of any `Referer`.
  - **A used, expired or unknown code:** 303 to `/home` if the request already carries a valid cookie (a reload), or
    else 403 with "This start link was used already or has expired. Start AI Browser again."
- **Why a cookie:**
  - the page's script can't read it (HttpOnly);
  - it never sits in a lasting address;
  - only the window's own profile ever holds it. Agents drive Brave or the sandbox, which never get it.

  This is the pattern Jupyter uses.
- **Why the port is in the cookie's name:** cookies for `127.0.0.1` reach every port (finding 13). The window never
  loads another local page (Decision 7), and the name keeps two app servers apart.
- **A socket on `/ws` from a page is accepted only when all of these hold:**
  - Origin is exactly `http://127.0.0.1:<port>`;
  - Host is exactly `127.0.0.1:<port>`;
  - the cookie `aib_ui_<port>` equals `ui_secret` (`hmac.compare_digest`).

  Otherwise the socket closes with 4403, after `accept`, as today (`server.py:551-562`). A page from another local
  port shares the site, so SameSite alone wouldn't stop it; the exact Origin does.
- **The watcher's path stays as it is:** `?token=` plus a watcher origin.
  - `allow_origin(origin, watcher=False)` (`server.py:178-183`) loses its non-watcher use and becomes
    `allow_watcher(origin)`.
  - The token path refuses any origin that isn't a watcher's.
- **Two roles of socket.** Wave 1B's `_role(ws)` reads `"app"` or `"watcher"` from the origin
  (`server.py:139`, `_origin_of`). It now reads a role stored when the socket is accepted:
  - `"app"` for a window socket (cookie, Origin and Host);
  - `"watcher"` for a watcher socket (token and a watcher origin).

  1B's `MESSAGE_RULES` and `_write`'s `for_watcher` filter stay as they are, with this spec's rows added.
  - `extension_seen` (`server.py:156, 563-564`) goes.
  - `origin_mismatch` stays for the watcher only. Its line becomes "A watcher connected as <origin>, but the app
    expected <ids>: please report this".
- **A refused window page stops trying.** On close code 4403, `link.js` reports the state `refused` and doesn't retry.
  - The status dot's title says "This window wasn't opened by this run of ai-browser app: close it".
  - This covers a window left from an earlier run, whose cookie holds the old secret.
- **The code is on the browser's command line,** where other local programs can read it. It is good for one use,
  within 60 s. If another program used it first, the window's own swap would fail with the 403 above, which the user
  sees. A program that can do that runs as the user and can already read the app's token files (the brief's risk "One
  Allow covers more").

### 6. A Host check and a strict CSP on every route; `/setup` holds no secret

- **One pure-ASGI middleware, `_Guard`, in `server.py`,** wraps the whole Starlette app, for HTTP and WebSocket
  alike.
- **The Host check:**
  - the Host header must be exactly `127.0.0.1:<port>`, known once the port is bound;
  - otherwise HTTP gets 403, and a WebSocket is closed before accept, which the client sees as an HTTP 403;
  - `localhost:<port>` is refused too. Every real client of the app uses `127.0.0.1` (`run.py:110-116`;
    `prepare_watcher`'s config.json).
  - **Why:** it blocks DNS rebinding. Starlette's `TrustedHostMiddleware` ignores the port, so it isn't used.
- **Headers on every HTTP response:**
  - `Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:;
    connect-src ws://127.0.0.1:<port>/ws http://127.0.0.1:<port>/setup/; base-uri 'none'; form-action 'none';
    frame-ancestors 'none'`;
  - `X-Content-Type-Options: nosniff`;
  - `Referrer-Policy: no-referrer`;
  - `Cache-Control: no-store`;
  - `Cross-Origin-Resource-Policy: same-origin`.
- **Why these CSP sources:**
  - thumbnails are `data:` JPEGs;
  - the mic worklet and dynamic imports count as scripts;
  - WebGL and the inline SVG of the chibi workers need nothing.
  - `connect-src` names the two paths pages use. A page script can't reach `/cdp` or `/agent-*`, even if `'self'`
    would allow a same-origin socket.
  - It replaces MV3's default extension CSP. The pages already set text with `textContent` only, have no inline
    scripts or styles, and use no `innerHTML` (checked).
- **`/setup` holds no secret.**
  - Today the page embeds the setup key in `data-key` (`setup.html:48, 66`), and has no Host check
    (`server.py:202-211, 263-264`).
  - `setup_key` (`server.py:159`) and the `X-AIB-Setup` header (`server.py:267`) go.
  - `POST /setup/reveal` now needs the window's cookie, and an Origin of exactly `http://127.0.0.1:<port>`.
  - It always shows the watcher's folder: the extension's folder is gone, so the `which` parameter goes too.
- **`/setup` keeps only Brave's steps:** `#brave` (the watcher) and `#switch` (the remote-debugging switch). The
  AI Browser extension section (`setup.html:42-58`) goes.
- **`GET /setup/status`** returns `{"watcher": bool}`, plus `"mismatch"` for a watcher mismatch. `"installed"`
  goes.

### 7. Links and windows: popups for our pages, the user's browser for websites

*Amended 2026-10-04 ([one window, its pages in a tab menu](#amendment-2026-10-04-one-window-its-pages-in-a-tab-menu)):
our pages are tabs, never popups; `openTab` and `openLive` replace `openWindow` and `focusHome`, and the table of
windows goes.*

- **A plain new-tab link brings the browser look back.** `window.open(url, "_blank")` from an app window opens a
  normal tabbed window (finding 11, runs B2 and B3). With `popup,width,height` features it opens an app-style window
  (B4). So the window's code never uses `_blank`.
- **New module `ui/nav.js`,** imported by `home.js`, `mission.js` and `settings.js` only:
  - `openWindow(path, name, width, height)`:
    - it calls `window.open("", name, "popup,width=…,height=…")`;
    - if the window it gets back still shows `about:blank`, it calls `location.replace(path)` on it;
    - then it calls `focus()`;
    - so a second click brings the open window forward instead of opening another. The features are ignored when a
      window of that name exists.
  - `focusHome()`: `openWindow("/home", "aib-home", 1440, 960)`. The main window names itself `aib-home` when it loads
    (`home.js`).
  - `guardLinks(link)`: one click listener (capture phase) on the document, also for `auxclick` and clicks with
    modifier keys, for every `<a href>`. Each of the three pages calls it once, at load:
    - a page of ours (`/home`, `/mission`, `/settings`, `/setup…`) goes through `openWindow`, with the name and size
      from the table below;
    - an `http` or `https` address elsewhere sends `open_url`;
    - anything else is dropped;
    - the default action is always prevented.
- **The files shared with the watcher import nothing new.** `brainui.js`, `link.js` and `permission.js` are copied
  into Brave's watcher (`brain/watcher.py:20`), and wave 5 adds `chat.js` and `check.js`. The watcher's folder has no
  `nav.js`, so none of them imports it:
  - `openLive(url)` lives in `check.js`, its only user: `window.open(url, "aib-live",
    "popup,noopener,width=1280,height=860")`. The live view is the engine's own `127.0.0.1:877x` page, already checked
    against `CHECK_LIVE` (`server.py:63`). `noopener` keeps that page from reaching back into ours;
  - `brainui.js` gets its setup link from its caller (below).
- **The windows of our own:**

  | name | page | size |
  |---|---|---|
  | `aib-home` | `/home` | 1440 × 960 |
  | `aib-mission` | `/mission` | 1280 × 860 |
  | `aib-settings` | `/settings` | 720 × 760 |
  | `aib-setup` | `/setup#brave` or `/setup#switch` | 760 × 900 |
  | `aib-live` | an engine's live view | 1280 × 860 |

  All of them are opened from a click, so the popup blocker never stops them.
- **Each `chrome.*` use in the pages, replaced:**
  - **`link.js:19, 27`:** see Decision 13.
  - **`home.js:258-259`** (the browser card's "Show me how"): `openWindow("/setup#switch", "aib-setup", …)`.
  - **`brainui.js:41, 191-193`** (the watcher's "Set it up"): `mountBrain(root, link, {…, openSetup = null})` gains
    one option, beside wave 1A's `cards` option, which stays as 1A left it.
    - AI Home and Mission Control pass `openSetup: () => openWindow("/setup#brave", "aib-setup", 760, 900)`, and the
      link calls it;
    - without it (the watcher's `brain.html` in Brave), `brainui.js` reads config.json and makes today's anchor to the
      server's `/setup#brave`, with `target = "_blank"`: in Brave a new tab is right. It is the one `"_blank"` left in
      `app/ui/`.
  - **`home.js:507-516`** (`openMission`): `openWindow("/mission", "aib-mission", 1280, 860)`.
  - **`mission.html:20`** (the `home.html` link): a button that calls `focusHome()`.
  - **`check.js:32`** (`window.open(live, "_blank", "noopener")`): `openLive(live)`, in `check.js` itself.
  - **`mic.js:13`:** `new URL("./mic-worklet.js", import.meta.url)`. Measured working over http (A4).
  - **`home.js:528, 549` and `mission.js:502, 504, 513, 515`** (`chrome.storage.local`): server settings
    (Decision 9).
  - **`home.js:557-565`** (pin AI Home): deleted.
  - **`talk.js:247`:** only its comment changes.
- **Websites go to the user's browser.** The new `open_url {url}` message:
  - **Accepted:** only from a window socket; only an address that starts with `http://` or `https://`, has a host,
    no user name or password, no whitespace or control character, and at most 2,000 characters. Because it starts
    with `http`, no program can read it as a command-line switch.
  - **Opened:** with the new `platforms.open_url(url, browser=None) -> bool`, in the agents' browser. In wave 3 that
    is the `browsers.installed()` row whose id `browsers.for_data_dir(own_browser_dir())` names, or None; wave 4 uses
    the saved choice:
    - macOS: `open -a <that browser's bundle> <url>` (2B's `Installed.bundle`), or `open <url>` when it isn't
      known;
    - Windows: `[<its exe>, <url>]`, or `os.startfile(url)`;
    - Linux: `xdg-open <url>`.
  - It runs in a thread (`asyncio.to_thread`). `False` (nothing could open it) answers `error {"text": "Couldn't open
    that address in your browser"}`.
  - **Why the OS and not the debugging connection:** opening a link is the user's own click, like a link in Mail. It
    lands in the profile they used last, needs no Allow, and works with the switch off.
  - Today no page shows a link to a website. `open_url` is where `guardLinks` sends one, so the window never navigates
    away from its own origin.
- **The risk that stays:** the user can still press ⌘N or ⌘T in the window. That opens a normal window on the app's
  profile, by hand. Nothing in the code does it.

### 8. Closing the window ends the app, detected through its sockets

*Amended 2026-10-04 ([one window, its pages in a tab menu](#amendment-2026-10-04-one-window-its-pages-in-a-tab-menu)):
the window's sockets are its tabs' pages; switching or closing a tab never ends the app.*

- **Process exit is no signal.** On macOS the browser keeps running after its last window closes (finding 12, run
  A2). The old check counted AI Browser's tabs through `TabWatch` (`run.py:217-221, 247-256`), which needs the
  debugging port the window no longer has.
- **The server counts window sockets:**
  - a window socket joins the set `_windows` when it is accepted, and leaves it in `_unsubscribe`, which may run twice
    for one socket (`stop()` and the socket's own `finally`);
  - `window_count` is `len(_windows)`, so it can't go below 0 or count a socket twice;
  - `window_seen` turns true at the first one.

  Every page of ours with a socket counts: AI Home, Mission Control and Settings. The setup page opens no socket; it
  is always a popup next to a window that has one.
- **`run.py`'s loop**, every 0.25 s:
  - **before the first window socket:** wait up to `WINDOW_START_WAIT` = 60 s. If none comes, print "AI Browser's
    window didn't open: <browser> started, but the page never connected. Try again, or pick another browser with
    `ai-browser app --window brave`", and return 1.
  - **after it:** when `window_count` has been 0 for `WINDOW_GRACE` = 5 s in a row, the app ends.
    - A reload, or a move between pages, reconnects within milliseconds.
    - 5 s, longer than the investigation's 3 s, leaves room for a slow machine or a socket dropped on wake from sleep.
    - On macOS, `time.monotonic` doesn't advance during sleep, so a long sleep can't use up the grace.
  - **`stop` set** (tests), or Ctrl-C: the app ends.
- **Ending, in this order:**
  1. the window is closed first, so it disappears at once. `AppWindow.close()` asks the process it started to quit
     (SIGTERM on macOS and Linux, `taskkill /PID <pid>` without `/F` on Windows, Decision 15), waits 10 s, and then
     kills it. That is safe, because the profile is the app's own. After a hand-off it ends nothing (Decision 3);
  2. the link file (`<home>/app/link.json`) goes;
  3. the server stops, and with it every agent's Claude Code process (`server.py:237`);
  4. BraveLink, and with it wave 2's relay, closes last. This keeps wave 2's order (its Decision 11): no agent sees
     its browser vanish while it still runs.
- **A second `ai-browser app`** is refused by the existing lock (`run.py:130-134`), as today. Only the message
  changes: "AI Browser is already running: its window is open (look for it in the Dock)", with "the taskbar" on
  Windows and Linux. Bringing the window to the front is out of scope.
- **On Windows,** closing the window usually ends the process too. The socket rule covers that case and Edge's
  background mode alike.

### 9. Settings move to the server; the port is remembered

- **New module `src/ai_browser/settings.py`,** for the file `<home>/settings.json`. Wave 4 adds `agents_browser` to
  the same file.
  - `read_settings(home) -> dict` gives the raw object: `{}` for a missing, unreadable or non-object file. It never
    raises.
  - `write_setting(home, key, value) -> None` reads, sets one key and writes atomically, keeping every other key.
  - These are the names and rules wave 4's spec lists under `places.py`. This wave lands first, so wave 4's
    `places.py` imports these two from `settings.py` (both names then work) and doesn't write a second reader. One
    reader and one writer touch the file.
  - `Settings(home)` is this wave's typed view on top of them.
  - `get() -> dict` returns the defaults `{"window_browser": "auto", "model": None, "voice": False}` merged with the
    file.
    - A missing, broken or half-written file gives the defaults.
    - A wrong value for one key falls back to that key's default.
  - `set(key, value) -> dict` checks the value, and raises `ValueError` with a plain message:
    - `window_browser`: one of this system's choices (Decision 2);
    - `model`: `opus`, `sonnet`, `haiku` or `None`;
    - `voice`: a bool.
  - **Writing:** atomic, with `syncdir.write_atomic(..., 0o600)`. Keys it doesn't know are kept, so a newer file
    survives an older build.
- **The model:**
  - `model` is `None` until the user picks one. Pages use `settings.model ?? default_model`, where `default_model` is
    `ai-browser app --model`, as today.
  - This replaces `storedModel` (`home.js:27, 393, 552`; `mission.js:25, 390, 518`).
- **Voice:** Mission Control turns Voice on at load when `settings.voice` is true (today `mission.js:504`).
- **The server's side:**
  - `AppServer(settings=…)` defaults to `Settings(home)`;
  - `settings_set` calls `Settings.set` and then sends `settings` to every socket (wave 1B's filter keeps it from the
    watcher);
  - `AppServer.window_info` holds the `window` part of that message: `{"using", "name", "note", "choices"}`. `run_app`
    sets it once, from the launched window and `window.choices()` (Interfaces). Detection runs once, at start, not on
    every `hello`. Without `run_app` (tests), it is `{"using": None, "name": "", "note": "", "choices": []}` unless
    the test sets it.
- **Why the server:**
  - the origin includes the port, so browser storage would reset whenever the port changed (finding 14);
  - wave 5's side chat in Brave has another origin. It never gets the `settings` message (that stays off
    `WATCHER_RECEIVES`); the server gives it the saved model in its own `panel_place` message (the side-chat spec).
- **The remembered port:**
  - `AppServer(port_file=…)`: `run.py` passes `<home>/app/port`, and tests that build a server leave it out.
  - `start()` tries the saved port first, then `APP_PORTS` in order (`server.py:44, 215-230`).
  - The file is written only when it is missing or unreadable, or names a port outside `APP_PORTS`.
  - A start that finds the saved port busy uses another and leaves the file alone. It prints: "Port 8792 is busy: AI
    Browser uses 8794 this time, and may ask for the microphone again."
  - **Why keep the first port:** the microphone grant belongs to that origin. A busy port is usually a one-off, and
    the next start goes back to the granted origin.

### 10. Microphone, voice and 3D in the window

- **The microphone:**
  - `127.0.0.1` is a secure context, and the window shows the site's microphone prompt (finding 9);
  - `talk.js`'s explain card and its Continue (`talk.js:193-226`) still fit, with their wording;
  - the grant is remembered per origin in the window's profile, which Decision 9's fixed port keeps stable;
  - macOS asks once per browser app. Its wording is already in `micProblem` (`talk.js:165`);
  - `micProblem`'s site-settings line (`talk.js:179-180`) says "allow AI Browser". The browser lists the site as its
    address, so it now says "allow `<location.host>`" (for example 127.0.0.1:8792).
- **The AudioWorklet** loads by a relative URL over http (A4). The `AudioContext` opens on the user's press, as today
  (`mic.js`), so the autoplay policy doesn't touch it.
- **WebGL 1 and 2** run on the GPU in Chrome and Brave app windows (ANGLE Metal on this Mac, C1). `blob.js` and
  `scene.js` don't change.
- **The browser's name** in the voice texts: `talk.js:21-24` `browserName` adds "Microsoft Edge" when the brands list
  it. Brave and Google Chrome are as today.

### 11. The "ai" keyword moves to the watcher

- **Why:** an app window has no address bar. Brave is where the user types addresses.
- **The watcher's `manifest.json`** gains `"omnibox": {"keyword": "ai"}`, and its version becomes `0.2.0`.
  - No new permission is needed.
  - The watcher reloads itself when the build changes (`watcher/worker.js:87-91`), and `chrome.runtime.reload()`
    reads the manifest again.
- **The watcher's `worker.js`:**
  - `chrome.omnibox.setDefaultSuggestion({description: "Start an AI Browser agent: %s"})`;
  - `onInputEntered` calls `startKeywordTask(text)`, which is also set on `globalThis` for the tests, as
    `startTask` is today (`extension/worker.js:151-167`);
  - it sends `ai_keyword {text, request}`. If `link.send` returns false (the app isn't connected), it shows the "isn't
    running" notification instead, and queues nothing. It never waits for the link, as today's `startTask` does
    (`link.whenOpen()`);
  - on `keyword_started {request, id, number, name}` it shows the notification "Started <number> · <name>. See it in
    AI Browser's window". `number` is wave 1A's `Agent.number` (`a4` is 4);
  - on an `error` with that request, it shows the error's text.
  - Notifications are set through the API, as text.
  - Only the omnibox handler sends `ai_keyword`. The worker's listeners for its readers' reports never do.
- **The server:**
  - it accepts `ai_keyword` only from the watcher;
  - the text is trimmed to 2,000 characters, and an empty text does nothing;
  - the server matches workflow names itself: the longest workflow name the text starts with, then a space or nothing
    more. This is the rule of `extension/worker.js:139-148`, moved to Python as `_keyword_workflow(text)`;
  - it runs that workflow with the rest of the text (`runner.run(slug, text=…)`), or creates an agent with the text,
    `settings.model` (else `default_model`) and no skills;
  - it answers `keyword_started` with that agent's id, number and name, or `error` with the reason;
  - it never takes `adopt` or `tab`. **Typing never hands over a tab.**
  - The keyword is the user's own Enter, like Start in AI Home. It doesn't go through the Brain.
- **Why a message of its own,** not `new_task` and `workflows` from the watcher:
  - the watcher never needs the workflow list;
  - wave 1B's list stays tight: the watcher may start a task only through this narrow message.

### 12. AI Browser's Chrome, its extension and the engine's app mode retire

The user said "drop it". The app's agents browse in the user's browser. They can't call `sandbox_start`, as today
(`bridge.py:310`). The Docker sandbox stays where it already is: Website QA (`qa`) crawls in its own sandbox, and a
Claude Code session can still call `sandbox_start()`.

- **Deleted: `src/ai_browser/appbrowser.py`.**
  - `extension_path` and `extension_id_for` (`appbrowser.py:68-85`), which the watcher still needs, move unchanged to
    a new `src/ai_browser/extension_id.py`. The importers change: `server.py:29`, `run.py:18-19`, and the tests.
  - The pipe launcher (`_Pipe`, `_Process`, `_spawn_posix`, `Extensions.loadUnpacked`) moves to a test helper,
    `tests/pipe_chrome.py`, as `launch_with_extension(profile, folder) -> PipeChrome(ws_url, extension_id, close())`.
    The watcher's tests still load the watcher into a throwaway headless Chrome. The product never uses it.
- **`app/run.py`:**
  - These go: `setup_text`, `_setup_pages`, `_connected`, `_open`, `EXTENSION_WAIT`, `WINDOW_CHECKS`, the `TabWatch`
    on AI Browser and the windowless loop (`run.py:37, 39, 55-63, 141-161, 217-229, 247-256`).
  - The watcher's folder is revealed once, `if not brain.store.watcher_prompted` (today also `installed`,
    `run.py:237`), and nothing is opened for it (today `_open(…, setup#brave)`, `run.py:240`).
  - `ready_text` is rewritten (What the user sees).
  - `brave_text` (`run.py:66-72`) gains a fourth step: "Type ai and a space in Brave's address bar to start a task".
  - The Brave setup always runs (today only `if where == "brave"`, `run.py:209-216`): the app always attaches
    BraveLink, and `brave_env(own)` always goes into `agents.env`.
- **`--browser`:**
  - `BROWSERS` (`run.py:75`) becomes `("brave",)`;
  - `app` (from `--browser` or `AIB_APP_BROWSER`) exits 1 with `RETIRED_APP`: "AI Browser's own Chrome is gone: agents
    browse in your browser (Brave or Chrome). Drop --browser app (and AIB_APP_BROWSER).";
  - with no choice, `app_browser()` is always `"brave"`, folder or not (today `"app"` when no browser folder exists,
    `run.py:99`);
  - `cli.py:41-42` keeps `--browser brave` only, and its help says so. The `app` command's help (`cli.py:38`, "a
    Chrome of its own with a Claude chat side panel") and `--model`'s ("changed in the panel", `:40`) are reworded for
    the window.
- **The hidden `--headless` flag** (`cli.py:43`) and `run_app`'s `headless` and `pipe_install` parameters go. Tests
  pass a launcher instead (Decision 16).
- **`agents.env`** (`run.py:207-208`):
  - loses `AIB_APP_PROFILE` and `AIB_APP_EXTENSION`;
  - gains `AIB_APP_ORIGIN=http://127.0.0.1:<port>`;
  - keeps `AIB_APP_EVENTS` and wave 2's `AIB_APP_CDP`. It holds no token since wave 2: each agent's own token is put
    in its env by `AgentManager.create`.
- **`app/bridge.py`:**
  - the default `AIB_BROWSER` (`bridge.py:297`) becomes `"chrome"`;
  - `PANEL_PROMPT` (`bridge.py:27-35`) is deleted, and the prompt is always `BRAVE_PROMPT` (`bridge.py:324`).
- **`engine.py`:**
  - `BROWSER_KINDS` (`engine.py:36-37`) loses `"app"`;
  - `AIB_BROWSER=app` answers every browser tool with "AIB_BROWSER=app is retired: AI Browser's own Chrome is gone.
    Use own (your browser) or sandbox." It is checked before `BAD_BROWSER`, which becomes "AIB_BROWSER must be own,
    chrome, brave or sandbox";
  - the app branches go: `engine.py:18, 35, 109, 186-190, 196, 211-215, 282-283, 311, 519, 544-545, 572, 768`;
  - it makes each `Browser` with `app_origin=os.environ.get("AIB_APP_ORIGIN", "")`.
- **`browser.py`:**
  - mode `"app"`, `hidden_extension` and `front` go: `browser.py:134-139, 150-163, 391, 407, 432, 474, 611, 876,
    1048-1060, 1286`;
  - `Browser(…, app_origin="")` keeps it, and `open` (`browser.py:410`) passes it on;
  - `url_problem(url, mode, app_origin="")` refuses, in every mode, an address whose scheme, host and port (from
    `urlsplit`, so case doesn't matter) equal the app's origin: "AI Browser's own pages open only in its window".
  - **Why:** an agent in Brave has no cookie, so the page would be useless anyway. This keeps the UI's origin, and
    `/setup`, out of agents' reach. Wave 2's relay already refuses the app's origin in `Target.createTarget` and
    `Page.navigate` (cdp-relay Decision 7), which also covers Claude Code sessions, whose env has no
    `AIB_APP_ORIGIN`.
- **`src/ai_browser/server.py`, the MCP server's instructions:** the last two lines (`server.py:33-34`, "In AI Browser
  (AIB_BROWSER=app)…") go.
- **`app/tabs.py`:**
  - `TabWatch(ws_url, extension_id)` (`tabs.py:20, 55-59`) becomes `TabWatch(ws_url, hidden_origin="", …)`.
    When it is set, `tabs()` and wave 1B's `pages()` leave out pages whose address starts with `hidden_origin` + "/"
    (in place of `chrome-extension://<id>/`);
  - `BraveLink(folder, …, app_origin="")` passes its `app_origin` to the `TabWatch` it makes, so a 403 page the user
    opened in Brave isn't listed as one of their tabs;
  - `has_pages` (`tabs.py:61-63`) goes;
  - `chrome://newtab` stays left out.
- **`app/server.py`'s AI Browser mode answers go,** because the app always attaches BraveLink now:
  - `_browser_info()` (`server.py:490-494`) loses its `"app"` answer. With no BraveLink attached (tests that build a
    server alone), it answers `{"kind": "brave", "name": "Brave", "state": "off", "groups":
    self.groups.available()}`;
  - `new_task` with `adopt` (`server.py:685-690`) is refused whenever `_handable` finds no such tab, BraveLink or
    not. Today it passes an unchecked `adopt` through when no BraveLink is attached.
- **Wave 1A's AI Browser mode branch goes:** `AgentManager.in_users_browser` is always true in the app now, so
  `HAND_OVER_APP_SAY` and its branch in the Brain (brain-delegation Decision 10) go with their test, and
  `in_users_browser` with them.
- **The pages:**
  - the `kind: "app"` branch of the browser card (`home.js:222-229`) and the "No tabs open besides AI Home" text
    (`tablist.js:116`) go;
  - `browser.kind` is always `"brave"`;
  - the empty agent list (`home.html:50`, `home.js:181`) drops "or open the chat beside any page" (What the user
    sees).
- **Docstrings** that describe AI Browser's Chrome are rewritten: `app/__init__.py:1`, `app/run.py:1-5`,
  `app/tabs.py:1-2` and `app/server.py:1-5`.
- **Left on disk, untouched:** `~/.ai-browser/browser/` (AI Browser's old Chrome profile, which may hold the user's
  logins) and `~/.ai-browser/app/extension/` (its old `config.json` holds a token, rotated and dead). The app never
  deletes user data. The README says both can be deleted by hand.
- **`doctor --setup`** (`cli.py:129`):
  - the required `Chrome` line becomes a required `window` line: "✓ window      Google Chrome (Auto) <path>". It
    comes from `window.pick`, which reads files only;
  - Chrome and Brave become information lines;
  - it fails only when no browser can draw the window: "✗ window      AI Browser needs Google Chrome, Brave or
    Microsoft Edge to draw its window: install one, or set AIB_CHROME_BINARY to the full path of chrome".

### 13. `link.js` keeps the watcher's path

- **One file, two ways in.** `connect({view, onMessage, onState})` picks its way by `location.protocol`:
  - **`chrome-extension:`** (Brave's watcher and its Brain page): config.json and `?token=`, exactly as today
    (`link.js:15-32`);
  - **`http:`** (AI Browser's window): `new WebSocket(\`ws://${location.host}/ws\`)`, with no token. The cookie goes
    with it.
- **On close code 4403,** an http page reports `refused` and stops retrying (Decision 5).
- **`targetOfTab` and `tabOfTarget`** (`link.js:70-84`, `chrome.debugger.getTargets`) go. Their callers were
  `extension/worker.js` (deleted) and `panel.js` (not served; wave 5 needs no debugger, per everyday-brave
  Decision 5).
- **`brainui.js`** keeps both ways to the setup page (Decision 7): `openSetup` from its caller, or config.json in the
  watcher.
- **A static test** keeps `chrome.` out of every `ui/` file except `link.js` and `brainui.js`.

### 14. The badge becomes the title

- **The window title** is "(n) AI Home" while n agents are working, and "AI Home" when none are.
- **`navigator.setAppBadge(n)`** is called too, inside try/catch. Whether the Dock shows it for a window that isn't
  an installed app was not checked.
- **The watcher's own badge and notifications** for permission and check requests, in Brave, stay
  (`server.py:625-627`).

### 15. Windows: Edge

- **Auto on Windows tries Edge, Chrome, Brave,** in that order, with no skip (Decision 2). Edge comes with Windows 10
  and 11. Where it was removed (the EEA allows that on Windows 11), Auto takes Chrome or Brave.
- **The same command line.** `--disable-search-engine-choice-screen` is Chrome's; Edge ignores it.
- **Closing it cleanly.** `TerminateProcess` (Popen's `terminate()` on Windows) counts as a crash, and Edge would then
  offer "Restore pages?" in the window at the next start. So `close()` first runs `taskkill /PID <pid>` without
  `/F`, which asks the process to close its windows, as a click on × does. After 10 s it calls `kill()`. Its
  renderers end with the browser process.
- **Not verified, because there is no Edge on this Mac:**
  - Edge's first run on a fresh `--user-data-dir`, with `--no-first-run`;
  - its `--app` window;
  - its startup boost, and its "keep running in the background" setting on a fresh profile;
  - that `taskkill` without `/F` closes it with no "Restore pages?" afterwards;
  - that a link clicked in another app opens in the everyday browser, never in the window (Decision 2).

  These are hand checks on the laptop.

### 16. The tests are rebuilt around a window with no extension

- **The `stack` fixture** (`tests/test_home.py:47-93):
  - it starts a throwaway headless Chrome with `chrome.launch(…, headless=True)`. That throwaway keeps its debugging
    port, because tests drive the page through it; only the product's window never has one;
  - it takes the cookie the real way: it opens `f"{url}/open?code={server.new_launch_code()}"` and waits for `/home`;
  - it attaches `FakeBrave([])` by default (agents browse in the user's browser);
  - it sets `server.window_info` to Chrome in use, with Chrome and Brave installed, so the Settings page has two
    choices to click whatever this machine has;
  - a test that needs real tabs (thumbnails, Watch) attaches a `TabWatch(ws_url, hidden_origin=url)` on the same
    throwaway with `server.attach_tabs`.
- **The `home` fixture** returns `(js, stack)`. `worker_js` goes, and each `js, _, stack = home` becomes
  `js, stack = home`.
- **Clicks that open a window** go through a new helper, `click_as_user(js_session, selector)`: `Runtime.evaluate`
  with `userGesture: true`. A script's `.click()` carries no user gesture, and the popup blocker would stop
  `window.open`.
- **Opening pages:**
  - `chrome-extension://{id}/home.html` becomes `{url}/home`, and `mission.html` becomes `{url}/mission`, in
    test_home, `test_mission.open_mission` and `open_with`, test_ai_home_phase2, test_brain_ui, test_check_card,
    test_talk and test_mission_visuals;
  - `import(chrome.runtime.getURL('x.js'))` becomes `import('/x.js')` (test_mission_visuals.py:20, 399, 602;
    test_talk.py:37, 182, 194, 553).
- **`tests/ui_socket.py` (new):** `ui_socket(server, url)` opens `/ws` with Origin `url` and the header
  `Cookie: aib_ui_<port>=<server.ui_secret>`. It replaces every `origin=ORIGIN` connection plus the token in
  test_app_server, and the `chrome-extension://good` ones in test_tools, test_skillwriter and test_workflows
  (`server.allow_origin("chrome-extension://good")` goes there). The watcher's path (`WATCHER` origin plus token)
  stays, with `allow_watcher`.
- **`conftest.py`:**
  - `PIPE_FIXTURES` (`conftest.py:26`) becomes `{"watcher"}`. The UI tests no longer need the pipe, so they can run on
    Windows;
  - `_never_the_users_browsers` drops `AIB_APP_BROWSER=app` (`conftest.py:59`), which would now be refused. The app
    in tests runs in brave mode, with `AIB_CHROME_DIR` at the empty `no-chrome-here` folder, so BraveLink stays `off`
    and never connects;
  - the same fixture now keeps detection off this machine's files, because the app calls `browsers.installed()` and
    `os_default()` from this wave on (`window.pick`, `doctor --setup`): `platforms.app_folders` gives empty temporary
    folders, `platforms.windows_browser_commands` gives `[]`, `platforms.windows_https_progid` gives None, and
    `platforms.launch_services_file` names a missing temporary file. These are the parts of wave 2B's
    `tests/test_browsers.py` fixture that wave 4's spec planned to move here; wave 3 moves them, and wave 4 keeps
    them. The one test that runs `doctor --setup` in a subprocess (`test_cli.py:192`) can't take the fixture: there
    `pick` reads the installed apps' `Info.plist` files and the LaunchServices file, and connects to nothing;
  - a new autouse fixture `_no_real_window` replaces `run.default_launcher` with one that raises
    `WindowError("tests never open AI Browser's real window: pass launcher=")`.
- **`tests/fake_window.py` (new):** `FakeWindow(cdp)` has `id` "chrome", `name` "Google Chrome" and `note` "". Its
  `launch(url)` opens the URL in a test's throwaway Chrome with `Target.createTarget`. Its `close()` closes the
  targets it opened, records `closed` and returns "".
- **Deleted:**
  - `test_appbrowser.py`. Its extension-ID tests move to `tests/test_extension_id.py`. Its docs test is rewritten in
    test_appwindow (below), and its Windows `Popen` test is replaced by test_appwindow's launch tests;
  - `test_appmode.py`:
    - **moved to `tests/test_engine.py` as they are:** `test_the_engine_needs_no_development_packages` (`:360`);
    - **moved onto `chrome_engine` (the throwaway stands in for the user's browser), as plain sessions without the
      app's reports:** `test_the_agent_carries_on_when_the_user_closes_its_tab` (`:310`) and
      `test_a_tab_the_user_opens_from_an_agents_tab_stays_theirs` (`:334`), each without its AI Browser-only lines
      (the page in front, `as_agent`). Neither behaviour has a user's-browser test yet;
    - **deleted with the mode,** because they test AI Browser's `u1` adoption, its page in front or its own profile,
      or a user's-browser test already covers them: the other twelve. Those counterparts are a handed tab used,
      taken back and left open (`test_watcher_groups.py:236`), agents' tabs grouped without taking the focus
      (`:71`), the engine holding at a bot check and handing it over (`test_checks_browser.py:191`), an app agent's
      check reaching AI Home (`test_engine.py:433`), QA holding at a check (`test_checks_browser.py:385`) and
      downloads asking first in the user's browser (`test_chrome.py:730`);
  - test_home's extension tests: the keyword (`test_home.py:149-157`, which moves to test_watcher), grouping
    (`:160-172`), the new tab page (`:194-198`), the pinned AI Home and AI Browser's grouping in brave mode
    (`:219-242`) and app mode (`:329-332`);
  - test_workflows' keyword test (`test_workflows.py:259-271`). The server's `_keyword_workflow` test in
    test_app_server replaces it.
- **Rewritten:**
  - `test_pages_reconnect_after_the_app_restarts` (`test_home.py:175-191`): after the server stops and a new one
    starts on the same home, the old page reports `refused` and stops, because its cookie holds the old secret;
  - `test_rows_are_updated_in_place_so_clicks_land` (`test_home.py:201-216`): its tab comes from a `FakeBrave` page;
  - `test_the_app_picks_brave_when_its_folder_exists` (`test_app_run.py:299-313`): no folder gives "brave" too, and
    `"app"` gives `RETIRED_APP`;
  - `test_aib_browser_picks_the_browser` (`test_engine.py:249-254`): its `("app", "app")` row goes; the retired
    message is tested on its own (Engine and browser, below);
  - `test_chrome.py:727`: the loop over Browser modes is `("sandbox",)`;
  - `test_server.py:153`: it asserts the AIB_BROWSER=app lines are gone;
  - the doctor tests (`test_cli.py:140-190`): the third line is the `window` line, and "✗ Chrome" becomes
    "✗ window";
  - `test_talk.py:21`'s `EXTENSION` (the "no cloud speech" scan) reads `app/ui`.
- **Kept, but skipped:** `test_panel.py`, with `pytestmark = pytest.mark.skip(reason="AI Browser's side panel retired
  in wave 3; the side-chat spec (wave 5) ports these tests to the watcher")`. A mark, not `pytest.skip(…,
  allow_module_level=True)`, so `from test_panel import panel` still imports. The two tests elsewhere that use its
  `panel` fixture get the same mark and stay where they are for wave 5: `test_the_panel_shows_the_same_card`
  (`test_ai_home_phase2.py:58`) and `test_the_panel_shows_the_same_card_for_the_users_own_tab`
  (`test_check_card.py:104`, which side-chat Decision 16 moves).
- **`test_tabwatch.py`'s `app_browser` fixture** becomes `throwaway_chrome`, and its "leaves out our pages" check
  uses `hidden_origin`. Wave 1B's `test_pages_carry_their_context_and_workers_are_seen` keeps its page and
  `default_context` checks there. Its `worker_contexts(app.extension_id)` line goes, because the throwaway loads no
  extension; wave 1B's `test_the_watchers_profile_is_found_from_its_worker`, on the `watcher` fixture, still covers
  a worker's context.
- **`test_portable.py:186`** looks in `app/ui` and `app/watcher`, not `app/extension` and `app/setup.html`.
- **`tests/test_sandbox.py:30`** is unchanged: the sandbox profile name "app" stays reserved, so no old folder is
  mistaken for a sandbox.

### 17. What this spec replaces in earlier specs

- **everyday-brave:**
  - Decision 3, "AI Browser's window stays, as the control room" (`2026-10-02-everyday-brave-design.md:294-306`): the
    control room is now this app window;
  - Decision 2's app mode (`:264-292`): retired;
  - the "pages" interface (`:687-699`): the `worker` view and `browser.kind: "app"` go.
- **ai-browser-app and ai-home:**
  - the extension, the side panel and its ⌘⇧Y (`2026-10-02-ai-browser-app-design.md:19, 37-42`);
  - AI Home as the pinned first tab and the new tab page (`2026-10-02-ai-home-design.md:21, 62-78, 337-340`).
- **voice-input Decision 1** (`2026-10-02-voice-input-design.md:228-236`): capture moves from an extension page in a
  tab to Mission Control's window. The grant now belongs to `http://127.0.0.1:<port>`.
- **mission-control** (`2026-10-02-mission-control-design.md:172`): Voice is remembered by the app's settings, not
  `chrome.storage.local`.
- **windows-and-repo:**
  - Decision 3, "Launching AI Browser on Windows" (`2026-10-02-windows-and-repo-design.md:275-296`), and the README's
    Windows step 5 (Load unpacked): replaced by Decisions 2, 3 and 15;
  - its Decision 4 (extension IDs) still applies to the watcher.
- **This project's own specs:**
  - brain-delegation Decision 10: its AI Browser mode branch (`HAND_OVER_APP_SAY`, `in_users_browser`) goes
    (Decision 12);
  - cdp-relay: its `--browser app` exceptions (no relay there, the route answering 404) no longer arise;
  - browser-detection: moving its test fixture's detection parts into `tests/conftest.py`, which it gave to wave 4,
    happens in this wave (Decision 16);
  - browser-profile-choice (wave 4): `read_settings` and `write_setting` already exist, in `settings.py`, and its
    `places.py` imports them (Decision 9). The conftest fixture's detection parts are already in place.

## Messages / interfaces

**New modules:**
- **`src/ai_browser/app/window.py`:**
  - `WINDOW_CHOICES = ("auto", "chrome", "brave", "edge")`, and `offered(system=None) -> tuple[str, ...]`;
  - `@dataclass WindowBrowser(id: str, name: str, binary: str)`. The names are "Google Chrome", "Brave" and
    "Microsoft Edge";
  - `@dataclass WindowPick(browser: WindowBrowser, note: str)`;
  - `pick(setting, system=None, installed=None, os_default=None) -> WindowPick | None`. It is pure when both are
    given: `installed` maps an id to a program path, and `os_default` is an id or None. `installed=None` means it
    asks `browsers.installed()` (plus `AIB_CHROME_BINARY`, and on Linux the `chrome.py` finders), and
    `os_default=None` means it asks `browsers.os_default()` on macOS only;
  - `choices(system=None, installed=None, os_default=None) -> list[dict]`: `[{"id", "name", "installed"}]` for each
    of `offered(system)`, with Auto named after its pick ("Auto (Google Chrome)");
  - `window_profile(home, browser_id) -> Path`, which is `<home>/app/window/<id>`;
  - `window_args(binary, profile, url) -> list[str]`;
  - `class WindowError(RuntimeError)`;
  - `class AppWindow`:
    - `__init__(home, browser: WindowBrowser, note: str = "", extra_args=())`;
    - `id`, `name` and `note` (the pick's fallback note, "" when none);
    - `launch(url) -> None`, which raises `WindowError("AI Browser's window could not start: …")`. It asks
      `browsers.running(profile)` first (the hand-off, Decision 3);
    - `close() -> str`, which returns "" or the hand-off note. On Windows it runs `taskkill /PID <pid>` before
      `kill()` (Decision 15);
  - `default_launcher(home) -> Callable[[str], AppWindow]`. It takes the `window_browser` setting and picks, or
    raises `WindowError`.
- **`src/ai_browser/settings.py`:** `read_settings(home) -> dict`, `write_setting(home, key, value) -> None`,
  `DEFAULTS`, and `class Settings(home)` with `.path`, `.get() -> dict` and `.set(key, value) -> dict`.
- **`src/ai_browser/extension_id.py`:** `extension_path(folder, system=None)` and `extension_id_for(folder,
  system=None)`. They are moved, not changed.

**Changed:**
- **`AppServer`:**
  - `__init__(…, settings: Settings | None = None, port_file: Path | None = None)`;
  - `new_launch_code() -> str`;
  - `ui_secret`, `window_count` (`len(_windows)`) and `window_seen`;
  - `window_info: dict` (Decision 9);
  - `allow_watcher(origin)` in place of `allow_origin`;
  - `setup_key`, `extension_seen` and `_extension_folder` go.
- **`AppServer.start()`** binds the saved port first, then sets the Host the guard expects and the CSP.
- **`run_app(home, model="sonnet", claude=None, ready=None, stop=None, out=print, browser=None, window_browser=None,
  launcher=None) -> int`:**
  - `launcher` takes the window's setting and returns an object with `id`, `name`, `note`, `launch(url)` and
    `close() -> str`. `None` means `default_launcher(home)`;
  - `run_app` prints the note when there is one, sets `server.window_info`, and prints `close()`'s note at the end;
  - `ready(url, window)` is called once the first window socket is in.
- **`cli.py`:** `run_app(home(), args.model, browser=args.browser, window_browser=args.window)` (today
  `cli.py:76`).
- **`TabWatch(ws_url, hidden_origin="", open_timeout=10, cdp=None)`** (`cdp` is wave 2A's; `extension_id` goes)
  and **`BraveLink(folder, …, app_origin="")`**.
- **`browser.url_problem(url, mode, app_origin="")`** and **`Browser(…, app_origin="")`**.
- **`platforms.open_url(url, browser=None, system=None) -> bool`**, plus `open_url_command(url, browser=None,
  system=None)`, which is pure and tested for each OS. `browser` is an `Installed` row, or None for the OS default.
- **`brain/watcher.py`:** `SHARED_SOURCE = APP / "ui"`.

**HTTP** (every route goes through `_Guard`: an exact Host, and the headers of Decision 6):
- `GET /` gives 303 to `/home`.
- `GET /open?code=` gives 303 to `/home` with `Set-Cookie: aib_ui_<port>=…; HttpOnly; SameSite=Strict; Path=/`. A bad
  code gives 403, or 303 to `/home` when the cookie is already valid.
- `GET /home`, `/mission` and `/settings` give the page with a valid cookie, or else 403 with the plain page.
- `GET /<file>` serves files from `app/ui/` (`.js`, `.css`, `.png`). They need the cookie, except `setup.js`,
  `setup.css` and `icon.png`.
- `GET /setup` gives the setup page, with no secret in it.
- `GET /setup/status` gives `{"watcher": bool, "mismatch"?: str}`.
- `POST /setup/reveal` needs the cookie and an exact Origin. It gives 204 when shown, 501 when nothing could show it,
  and 403 otherwise.
- `/health`, `/agent-*` and `/cdp` are unchanged, behind the Host check.

**WebSocket `/ws`:**
- **Window sockets** need an exact Origin, an exact Host and the cookie. **Watcher sockets** need the token and a
  watcher origin. Anything else is closed with 4403.
- **Pages → server (window sockets only):**
  - `settings_set {"key": "model" | "voice" | "window_browser", "value": …, "request"?}`. A bad value gets
    `error {"text", "request"}`;
  - `open_url {"url"}`. A refused address gets `error {"text": "Only web addresses open from here"}`, and one
    nothing could open gets `error {"text": "Couldn't open that address in your browser"}`.
- **Server → pages (window sockets only):**
  - `settings {"model": str | null, "voice": bool, "window_browser": str, "window": {"using": "chrome", "name":
    "Google Chrome", "note": str, "choices": [{"id": "auto", "name": "Auto (Google Chrome)", "installed": true},
    …]}}`;
  - the same object as `snapshot.settings`.
- **Watcher → server:** `ai_keyword {"text", "request"}`.
- **Server → watcher:** `keyword_started {"request", "id", "number", "name"}`, or `error {"request", "text"}`.
- **The `hello` views** become `home`, `mission` and `settings` (window), and `watcher` and `brain` (watcher). The
  `worker` and `panel` views go.
- **`browser`** keeps its shape, but `kind` is always `"brave"`.
- **Wave 1B's tables gain these rows:**
  - `MESSAGE_RULES`: `ai_keyword` (app no, watcher yes); `settings_set` and `open_url` (app yes, watcher no). The
    table test's copy grows by these three, after waves 1A and 2A's rows;
  - `WATCHER_RECEIVES`: `keyword_started`. `settings` is sent to app sockets only, and isn't on the list.

**Command line:**
- `ai-browser app [--model …] [--browser brave] [--window auto|chrome|brave|edge]`. `--window` applies to that run
  only.
- `--browser app` exits 1 with `RETIRED_APP`.
- `--headless` goes.
- `doctor --setup` has the `window` line.

**Environment:**
- **New:** `AIB_APP_ORIGIN`, set by the app for its agents.
- **Retired:** `AIB_APP_PROFILE` and `AIB_APP_EXTENSION`.
- **Refused with a message:** `AIB_APP_BROWSER=app` and `AIB_BROWSER=app`.
- **Unchanged:** `AIB_CHROME_BINARY`, which is used when the window's browser is Chrome.

**Files:**
- **New:** `<home>/settings.json` (0600), `<home>/app/port`, and `<home>/app/window/<browser>/` (the window's
  profile).
- **No longer written:** `<home>/app/extension/` and `<home>/browser/`.

**Docs:** the README is rewritten where it describes AI Browser's Chrome:
- the intro line (`README.md:20`);
- the Windows step 5 (`:62-68`), including its Google sign-in note, which was about AI Browser's Chrome;
- "Which browser" (`:124-125`);
- the whole "AI Browser" section (`:145-212`): the window, Settings, closing, and the old folders that can be deleted.
  Its "Debugging port" line (`:211-212`) goes;
- "Mission Control" (its own window);
- "Talking to the Brain" (the mic is asked for once in the window, and kept across restarts);
- "Commands" (`:545`);
- "Safety notes" (`:554`) gains one line: AI Browser's window has no debugging port, and no agent browses there.

## Safety

The binding rules, one by one:

- **Brave's "Allow remote debugging?" prompt and its automation bar are never auto-clicked, answered, suppressed or
  hidden.**
  - The window has no debugging port, so it never causes either.
  - Its command line has no flag that touches them: no `--enable-automation`, no `--silent-debugger-extension-api`,
    no `--disable-infobars`.
  - A test pins the exact list.
  - The app's one connection to Brave (wave 2) is unchanged.
- **No spoofing or disguise; no bypassing or solving bot checks.**
  - `--app` is Chrome's own feature for a plain window.
  - `navigator.webdriver` is false there because nothing automates the window, not because anything hides it.
  - No agent ever browses in it. Agents can't even open its address (`url_problem`).
  - The autoplay flag only lets AI Browser's own pages speak, in AI Browser's own profile.
  - No user agent, screen or timing change anywhere.
- **No passwords are typed.** The window's pages have no sign-in, and the app never signs its profile in to the
  browser. Agents are not there.
- **Page and message text is data.**
  - The keyword's text is what the user typed in Brave's address bar. Only the watcher's omnibox handler sends it.
  - `open_url` takes only an `http`/`https` address, only from a window socket. The pages send it only from a link
    click (`guardLinks`), and the address can't be read as a command-line switch.
  - Agent names and page titles in notifications are set through APIs, as text.
- **`textContent` only.**
  - The new pages (Settings, setup.js, nav.js) set text with `textContent`.
  - The CSP forbids inline script and style.
  - A static test forbids `.innerHTML`, `.outerHTML`, `insertAdjacentHTML` and `document.write` in `ui/`'s scripts,
    and inline `<script>` and `<style>`, `style=` and `on…=` attributes in its pages.
- **Nothing leaves the machine without a knowing choice.**
  - Settings, the port, the cookie and the code stay on this computer.
  - A clicked link opens in the user's own browser, on this computer.
  - The window's pages are all local. The browser's own background traffic (updates, Safe Browsing) is the browser's,
    as in any window of it, and the user chose that browser.
- **Downloads need the user's OK.** The window's pages download nothing. Agents' download rules (everyday-brave
  Decision 15) are unchanged.
- **Hand-over and take-back are clicks only, never voice or the Brain.**
  - Unchanged in AI Home.
  - The keyword never hands over a tab: the server ignores `adopt` and `tab` on `ai_keyword`.
- **The Brain only proposes; nothing runs without Start, Send or a plain yes.** Unchanged: this wave moves the pages
  and changes nothing about what runs. The keyword doesn't go through the Brain: it is the user's own Enter, like
  Start in AI Home, as it was in AI Browser's address bar.
- **Agents use only tabs they open or tabs the user hands them.** With AI Browser mode gone, `new_task` with `adopt`
  is checked against BraveLink's list in every case (Decision 12).
- **Who can reach the UI:**
  - **only the window,** through a single-use, 60 s code swapped for an HttpOnly, SameSite=Strict cookie named for
    the port;
  - **every socket** also needs the exact Origin and Host;
  - **a page in Brave, or opened by an agent,** gets 403 and no socket;
  - **DNS rebinding** is blocked by the Host check on every route;
  - **`/setup`** holds no secret;
  - **showing a folder** needs the cookie and the exact Origin;
  - **CSP `connect-src`** keeps a page's script off `/cdp` and `/agent-*`.
- **Cookies on 127.0.0.1 are shared across ports** (finding 13).
  - The window loads only our pages and the engine's own live view. `guardLinks` sends every other address to the
    user's browser.
  - The live view's server is our own (`live.py`) and ignores cookies.
  - A local dev server the user is testing must never be opened in the window: QA and agents use Brave or the
    sandbox.
- **Only our own process is ended.** `close()` ends the process the app started on its own profile. It never kills a
  process it found: after a hand-off it ends nothing.
- **The user's data is not deleted.** The old `~/.ai-browser/browser/` profile stays until the user deletes it.

## Testing

No test opens a visible window, connects to the user's Brave or Chrome, or touches the running app. Throwaway
headless Chromes only. "Fails today" marks a test that fails at HEAD and passes after this wave.

**`tests/test_appwindow.py` (new):**
- **`pick` for each system:**
  - this Mac's case (Chrome and Brave installed, Brave the default) gives Chrome;
  - with Chrome the default, it gives Brave;
  - with only Brave, Brave;
  - on win32 with all three and Chrome the default, Edge;
  - on win32 with all three and Edge the default, Edge: no skip there;
  - on linux with Chrome and Brave, Chrome;
  - an explicit `brave` with Brave missing gives Chrome, with the note;
  - `edge` on darwin gives Auto's pick, with a note;
  - `AIB_CHROME_BINARY` at a temporary file, with nothing installed, gives Chrome at that path;
  - nothing installed gives None.
- **`choices`** on darwin with Chrome and Brave installed and Brave the default: Auto is "Auto (Google Chrome)",
  and each row's `installed` is right. On win32 it lists Edge too.
- **`window_args`:**
  - it equals the list in Decision 3;
  - it has no argument starting with `--remote-debugging`, `--enable-automation`, `--load-extension`, `--headless`,
    `--user-agent` or `--disable-infobars`.
- **`window_profile`** is under `<home>/app/window/`. `AppWindow` refuses a profile inside any of
  `browsers.all_data_dirs()` (patched to a temp folder).
- **The launch, with a recorder in place of `subprocess.Popen`:**
  - the recorded argv equals `window_args(...)`;
  - an `OSError` gives `WindowError("AI Browser's window could not start: …")`;
  - `close()` calls `terminate`, then `kill` after the wait, on a fake process that ignores `terminate`;
  - with the system patched to win32, `close()` first runs `["taskkill", "/PID", "<pid>"]` (recorded, no `/F`), then
    `kill` after the wait;
  - with `browsers.running` patched to True, `launch` still starts the process, and `close()` calls neither
    `terminate` nor `kill` and returns the hand-off note;
  - with it False, and a process that has already exited (Ctrl-C reached it too), `close()` returns "" and kills
    nothing.
- **The real launcher, headless** (CHROME):
  - `AppWindow(home, chrome, extra_args=("--headless=new", url))` launches against a live `AppServer`. The URL comes
    a second time as a plain argument, because headless Chrome's handling of `--app=` wasn't measured. The code is
    single-use, so whichever page loads second gets the 403 page and no socket;
  - within 20 s, `server.window_count == 1`;
  - the profile has no `DevToolsActivePort`;
  - after `close()`, the process has exited.
- **The docs:** `window.py`'s docstring says the window has no debugging port and that no agent browses there.
  `appbrowser.__doc__` is gone. This replaces `test_appbrowser.py:169-185`, whose checks of the other docs (the
  ai-home spec's correction, its plan, the own-chrome-mode sentence) move with it unchanged.

**`tests/test_settings.py` (new):**
- `read_settings` gives `{}` for a missing file, a broken file and a JSON list, and never raises;
- `write_setting` keeps a key it didn't set (`agents_browser`, as wave 4 writes it);
- a missing file gives the defaults;
- a broken file gives the defaults and is not overwritten until the next `set`;
- a bad `model` in the file falls back for that key only;
- `set` refuses `window_browser="edge"` on darwin, `model="gpt"` and `voice="yes"`;
- an unknown key in the file survives a `set`;
- the file mode is 0600 (`file_mode`).

**`tests/test_app_server.py` (additions; `ui_socket` replaces the `ORIGIN` pattern):**
- **Host:**
  - `GET /setup` with `Host: rebind.example:<port>` gives 403 (**fails today**: 200);
  - `GET http://localhost:<port>/health` gives 403;
  - a `/ws` handshake to `ws://localhost:<port>/ws` gets HTTP 403;
  - `/agent-events` with the right token but a wrong Host gives 403.
- **Headers:**
  - `GET /home` (with the cookie), `/setup` and `/home.js` each carry the exact CSP, `nosniff`, `no-referrer`,
    `no-store` and `Cross-Origin-Resource-Policy: same-origin` (**fails today**: no CSP).
- **`/setup` holds no secret:**
  - the HTML has no `data-key` and no value of any of the server's secrets (`token`, `session_token`, `ui_secret`,
    the agents' tokens) (**fails today**: it holds `setup_key`);
  - `POST /setup/reveal` with no cookie gives 403 (**fails today**: with the `X-AIB-Setup` key, 204 and no cookie
    needed);
  - with the cookie but `Origin: http://127.0.0.1:<other port>`, 403;
  - with both right, 204, and the reveal stub got the watcher's folder.
- **The code:**
  - `new_launch_code()` then `GET /open?code=…` gives 303 to `/home` and a `Set-Cookie` with `aib_ui_<port>`,
    `HttpOnly`, `SameSite=Strict` and `Path=/`, and no `Max-Age`;
  - the same code again gives 403;
  - a code older than `CODE_TTL` (clock patched) gives 403;
  - a wrong code gives 403, or 303 when the request carries the valid cookie.
- **Pages:**
  - `/home`, `/mission`, `/settings` and `/link.js` without the cookie give 403 with the plain text (**fails today**:
    404);
  - with it, 200;
  - `/setup.js` and `/icon.png` give 200 without it;
  - `/%2e%2e%2fserver.py`, `/server.py`, `/home.html`, `/setup.html`, `/panel.js` and `/manifest.json` give 404, with
    the cookie too.
- **Sockets:**
  - the right cookie, Origin and Host get the snapshot, with `settings` in it;
  - a missing cookie, a wrong cookie, `Origin: http://127.0.0.1:<other port>`, no Origin, or the token with an http
    Origin each get 4403;
  - the watcher's token and origin still connect as the watcher;
  - the token from any origin that isn't a watcher's gets 4403, and `allow_origin` no longer exists.
- **Window count:** two window sockets give `window_count == 2`; after both close, 0; `window_seen` stays true.
- **The role decides:** a window socket's `_role` is `"app"`. `listen_start`, `brain_ask`, `hand_tab`, `settings_set`
  and `open_url` from the watcher do nothing; from a window socket they work as before.
- **Settings:**
  - `settings_set model=opus` is saved, and every window socket gets `settings`;
  - a bad value gets `error`, and the file is unchanged.
- **`open_url`:**
  - `https://example.com` calls the patched `platforms.open_url` once;
  - `javascript:alert(1)`, `file:///etc/hosts`, `https://u:p@example.com`, `http:///x` (no host),
    `https://example.com/a b` and a 3,000-character address each get `error`, and nothing is called;
  - when the patched `platforms.open_url` returns False, the page gets "Couldn't open that address in your browser".
- **`ai_keyword`, from the watcher socket:**
  - "check the shop" creates an agent with that text, the saved model and no skills, and answers `keyword_started`
    with its id, number and name;
  - with a workflow "qa site", the text "qa site example.com" runs that workflow with the text "example.com";
  - `adopt` and `tab` in the message are ignored, and no tab is handed;
  - from a window socket, nothing happens;
  - wave 1B's two table tests gain the new rows (`ai_keyword`, `settings_set`, `open_url`, `keyword_started`).
- **AI Browser mode's answers are gone:**
  - with no BraveLink attached, `new_task` with `adopt: "T1"` gets the hand-over error and starts no agent
    (**fails today**: it starts one, with T1 adopted);
  - with no BraveLink attached, the snapshot's `browser` has `kind` "brave" and `state` "off" (**fails today**:
    `kind` "app").
- **The port:**
  - with `port_file` naming a free port in range, the server binds it;
  - with that port held by a test socket, it binds another, the file is unchanged, and the note is printed;
  - a file naming 80 is rewritten with the port used.
- **The watcher mismatch** is still reported, worded for the watcher only (replaces `test_app_server.py:1166-1200`).

**`tests/test_app_run.py` (rewritten with `FakeWindow`):**
- **It opens the window:** `run_app(..., launcher=…)` launches with `f"{url}/open?code=…"`. Once the page is
  connected, `ready` is called. `/health` answers. `<home>/app/extension` is not written.
- **It ends when the window closes:** the test closes the page target. `run_app` returns 0 within
  `WINDOW_GRACE + 2` s (grace patched to 1 s), `FakeWindow.closed` is true, and the port is free again.
- **A reload doesn't end it:** `location.reload()` in the page, wait twice the grace, still running.
- **A popup keeps it alive:** the page opens `/mission` with `openWindow` (as a user gesture); closing the main page
  leaves the app running; closing `/mission` ends it.
- **A window that never connects:** a launcher that opens nothing makes `run_app` return 1 with "didn't open"
  (`WINDOW_START_WAIT` patched to 1 s).
- **No window browser:** a launcher raising `WindowError` makes `run_app` return 1 with its message.
- **The notes:** a launcher whose window has a `note` gets it printed at start; one whose `close()` returns the
  hand-off note gets that printed at the end.
- **The retired choice:**
  - `browser="app"`, or `AIB_APP_BROWSER=app`, with a `FakeWindow` launcher, returns 1 with `RETIRED_APP` and
    launches nothing (**fails today**: `run_app` takes no `launcher`, and it accepts `"app"`);
  - `agents.env` has `AIB_APP_ORIGIN` and no `AIB_APP_PROFILE` or `AIB_APP_EXTENSION`.
- **The ending order:** with `stop` set, the recorded order is `FakeWindow.close`, the link file gone,
  `server.stop`, then BraveLink's `close` (Decision 8).
- **A second run** is refused with "already running", and the first one's files are unchanged (as
  `test_app_run.py:82-101`).
- **First start:** the watcher's steps are printed once, the reveal stub is called once with the watcher folder, and
  nothing else is revealed.
- **The terminal texts:** `ready_text` and `brave_text` for darwin and win32 have no "⌘⇧Y" and no "extension"; win32
  says Ctrl.

**`tests/test_home.py` and the UI tests (on the rebuilt `stack`):**
- AI Home connects over http, and its status dot is `connected`.
- **Mission Control:** clicking it (`click_as_user`) opens one target at `/mission`; a second click opens none (the
  target count stays 1); `window.name` there is `aib-mission`.
- **Settings:** clicking it opens `/settings`; picking `brave` sends `settings_set`, and the file says `brave`.
- **Set it up:** with the watcher not connected, the inbox's "Set it up" link (`click_as_user`) opens one target at
  `/setup#brave`, whose `window.name` is `aib-setup`.
- **The model:**
  - picking `opus` in AI Home shows `opus` in an open Mission Control without a reload, and after reloading AI Home;
  - **fails today**: Mission Control reads the model from `chrome.storage.local` once, at load
    (`mission.js:515-518`), so an open Mission Control keeps the old one.
- **The title** is "(1) AI Home" while a fake agent works, and "AI Home" after.
- **Links:**
  - an injected `<a href="https://example.com">` click sends `open_url` (the patched `platforms.open_url` records it)
    and leaves `location.href` unchanged;
  - an injected `<a href="/mission" target="_blank">` click (`click_as_user`) opens exactly one new target, at
    `/mission`, and its `window.name` is `aib-mission`. A `_blank` open would have an empty name.
- **The CSP:** an injected `<script>` with text doesn't run, and a `securitypolicyviolation` event fires;
  `fetch('/agent-status')` from the page is blocked.
- **Without the cookie:** a page opened in a new browser context (`Target.createBrowserContext`) at `{url}/home`
  shows "open only in its own window", and opens no socket (`window_count` unchanged).
- **The tab list, the browser card, Hand over and Take back** work as today on `FakeBrave`
  (`test_home.py:252-327`, kept).
- **test_mission and test_talk:**
  - the mic tests pass on `/mission` with the worklet loaded through `import.meta.url`;
  - **fails today**: `mic.js:13` calls `chrome.runtime.getURL`, which an http page lacks.
- **`browserName`** gives "Microsoft Edge" for brands that list it.

**`tests/test_watcher.py` (additions):**
- `manifest.json` has `omnibox.keyword == "ai"`;
- `startKeywordTask("check the shop")` from the worker makes the server create that agent, and a notification appears
  (`chrome.notifications.getAll`) whose message starts "Started 1 · check the shop". The old `test_home.py:150`
  moves here;
- with the app stopped, `startKeywordTask` shows the "isn't running" notification and the server sees nothing;
- the shared files in the watcher's folder are byte-equal to `app/ui/`'s (`link.js`, `brainui.js`, `brainui.css`,
  `permission.js`);
- the existing watcher tests pass with the pipe launcher from `tests/pipe_chrome.py`.

**Engine and browser:**
- `url_problem("http://127.0.0.1:8792/home", "chrome", app_origin="http://127.0.0.1:8792")` refuses (**fails
  today**: it allows it). Another port is allowed.
- With `AIB_BROWSER=app`, `open` answers the retired message, and nothing starts (**fails today**: it answers "AI
  Browser isn't open: start it with `uv run ai-browser app`").
- The engine makes its `Browser` with `AIB_APP_ORIGIN`, so `open http://127.0.0.1:<app port>/setup` is refused
  through the engine too.
- test_bridge: the default `AIB_BROWSER` in `mcp.json` is `chrome`, the prompt is `BRAVE_PROMPT`, and `PANEL_PROMPT`
  no longer exists.

**`tests/test_ui_static.py` (new):**
- it first asserts that `app/ui/` holds `home.html`, `mission.html`, `settings.html`, `setup.html` and `nav.js`, so
  it can't pass on a missing folder (**fails today**: there is no `app/ui/`);
- no `.js` there matches `\.innerHTML|\.outerHTML|insertAdjacentHTML|document\.write`. A comment that names
  innerHTML without the dot, as `chibi.js:4` does, is fine;
- `"_blank"` appears only in `brainui.js` (the watcher's anchor), and `chrome.` only in `link.js` and `brainui.js`;
- `nav.js` is imported by no file that `brain/watcher.py`'s `WATCHER_SHARED` lists;
- no `.html` there has an inline `<script>` (one without `src`), a `<style>`, a `style=` attribute or an attribute
  matching `\son[a-z]+\s*=` (so `aria-controls=` doesn't count);
- moving today's files in as they are would fail it: `setup.html` (its inline script and style) and `check.js`
  (`_blank`).

**`tests/test_platforms.py` (additions):** `open_url_command` for darwin (with and without the browser's bundle),
win32 and linux.

**`tests/test_cli.py` (additions):**
- `app --help` lists `--window`, and `--browser` offers `brave` only;
- `doctor --setup`, with `AIB_CHROME_BINARY` at a temp file, prints "✓ window      Google Chrome (Auto) <that
  path>" as its third line;
- with `AIB_CHROME_BINARY` at a missing file and nothing installed (the conftest fixture), it prints "✗ window" and
  fails.

**`tests/test_portable.py`:** the page guard reads `app/ui`. It passes for the new files.

**By hand, on the Mac, after this wave** (the main session asks the user):
1. `uv run ai-browser app`:
   - one window with a title bar only;
   - no "Allow remote debugging?" for the window and no automation bar;
   - the Dock shows Google Chrome.
2. Mission Control and Settings open as small windows. A second click brings them forward.
3. The first talk in Mission Control's window shows Chrome's microphone prompt (and macOS's once). After a restart,
   no prompt.
4. With Voice on, Mission Control speaks an update right after start, with no click.
5. Closing the window ends the app within about 5 s, and no Chrome is left in the Dock.
6. In Brave, `ai check the shop` starts an agent, and the notification appears.
7. Typing `http://127.0.0.1:<port>/home` in Brave shows the "open only in its own window" page.
8. Ctrl-C in the terminal closes the window, and the next start shows no "Restore pages?".

**On the Windows laptop:**
- Edge draws the window on its first run with a fresh profile, with no welcome page;
- closing it ends the app;
- Ctrl-C in the terminal closes it, and the next start shows no "Restore pages?";
- a link clicked in another app (Mail, Teams) opens in the everyday browser, not in the window.

## Out of scope

- **A double-click Mac app** with its own Dock icon and menu bar name: an installed web app (a manifest and Chrome's
  app shim) or a native shell. Until then, the Dock shows the browser that draws the window.
- **Bringing the open window to the front** when `ai-browser app` runs a second time.
- **Applying a new window browser at once**, without a restart.
- **Keeping the app running** after its last window closes, with a way to reopen it.
- **A ⌘K command bar** in the window.
- **A separate, opt-in agent browser** to replace AI Browser's Chrome: the user said "drop it".
- **Where agents browse, and in which profile** (Settings' second section, the AI Home chip): wave 4.
- **The chat beside the page:** wave 5 brings it into Brave's watcher.
- **Edge as the window's browser on macOS,** and Firefox or Safari anywhere.
- **Migrating the model and Voice** saved in the old extension's storage.
- **Deleting the old `~/.ai-browser/browser/` profile** or `~/.ai-browser/app/extension/`: the user's choice, by
  hand.
- **Linux desktop polish** beyond the same command line.
