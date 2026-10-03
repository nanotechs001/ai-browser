# One shared connection to the browser: the app relays every agent

Date: 2026-10-03.

## Status

Status: the user approved the design in chat and answered its four questions; this spec was written and reviewed by agents without a user review round.

**The user's answer that this spec builds:** to "Should the app hold Brave's connection for its whole run, and should
Claude Code sessions use it?" the user chose **"yes to both" (Recommended)**:
- the app holds Brave's one connection for its whole run;
- Claude Code sessions go through it while the app runs.

The other answers touch this spec only at its edges: the app window draws on Google Chrome (wave 3), agents use the
Brave profile the user is signed in to (wave 4), and AI Browser's own Chrome for agents is dropped (wave 3).

**The brief:** `docs/superpowers/specs/2026-10-03-app-as-an-app-overview.md`, section 2. **The evidence:**
`docs/superpowers/specs/2026-10-03-app-as-an-app-investigation.json`, topic `relay`.

**What was found**, so the reasons below rest on facts:
- **Brave asks once per connection, and remembers nothing.** With the `brave://inspect` switch on, the debugging
  server runs in "approval mode": every websocket to `/devtools/browser/*` gets its own "Allow remote debugging?"
  (Chromium `chrome/browser/devtools/remote_debugging_server.cc:396-414`,
  `content/browser/devtools/devtools_http_handler.cc:858-870`). A headless probe in a throwaway Chrome 154 confirmed
  approval mode: two handshakes both waited on their own decision, and `/devtools/page/*` got 403 at once.
- **Today that means 1 + N + M questions per app run:** the app's `BraveLink` (`app/bravelink.py:45-66`), one per
  agent's engine (`engine.py:192-201`), and one per Claude Code session (the same code). Every engine restart asks
  again (New chat, a crash, Stop), and so does every Brave restart.
- **The automation bar follows the number of open connections.** Chrome looks at the bar again only when a connection
  opens or closes. If the count is above zero then and the user closed the bar, a new bar appears
  (`chrome/browser/devtools/chrome_devtools_manager_delegate.cc:551-564`). Agents connect and disconnect all day, so
  the bar keeps coming back.
- **Which tabs an agent may use is enforced only inside its own process.** All agents share one token
  (`app/server.py:148`), and the app records ownership on the engine's word (`app/server.py:399-420`). Take back
  reaches the engine through a status answer cached for 1 s (`agentlink.py:20`, `:68-81`).
- **Each engine uses a small, flattened-session subset of CDP.** At browser level it sends only
  `Target.setDiscoverTargets`, `createTarget`, `attachToTarget` (always `flatten: true`), `detachFromTarget`,
  `closeTarget`, `activateTarget`, `getTargets`, `getTargetInfo`, and `Browser.cancelDownload`
  (`browser.py:366-368`, `:376-383`, `:423-443`, `:516`, `:538-539`, `:808-812`, `:1027-1028`; `engine.py:489`).
  `Browser.setDownloadBehavior` is sandbox-only (`browser.py:377-379`). Every other call carries the session id of an
  attached tab. So a relay can enforce a short list.
- **Claude Code sessions sometimes land in Chrome.** They pick the first browser whose switch answers, and check again
  on every connect (`chrome.py:55-63`, `engine.py:193`, `:291-292`).

None of the question or bar counts has been counted by hand in the user's Brave 152. That is the hand check at the end
of this wave (Testing).

**Builds on:** everyday-brave (`BraveLink`, `TabWatch`, the Placer, link.json, Hand over and Take back), safe-browsing
(the hold, `bring_to_front`), the Windows spec (`platforms`, token files' permissions), and wave 1 of this project:
- **brain-delegation (wave 1A)** adds agent numbers ("3 · Fix the footer") and a `queued` count. This spec reuses the
  numbered label in AI Home's new list;
- **watcher-safety (wave 1B)** replaces the watcher's deny-list with a fixed list of what the watcher may send, and
  filters AI Home's tab list by profile. This spec's new page message joins the list of messages the watcher may not
  send.

**Build order:** wave 2. This spec (2A) is built beside browser-detection (2B), which touches only the new
`browsers.py` and `platforms.py`. This spec touches neither, and it doesn't touch `chrome.py` (wave 4 changes
`own_browser_dir()`). Wave 3 (the app window) then rewrites `run.py` and `server.py` around the route and tokens added
here, and keeps them as they are. Line numbers below are at HEAD before wave 1; a planner re-reads them after wave 1
merges.

## Goal and success criteria

The app holds the only connection to the user's Brave. Every agent's engine, and every Claude Code session while the
app runs, talks to Brave through it. The relay also decides which tabs each of them may see and drive.

Success means:
1. **One question per app run.** With the switch on, Brave asks "Allow remote debugging?" once when the app connects,
   and once more after each Brave restart. It asks none per agent, per New chat, per crash or Stop of an agent's
   process, or per Claude Code session while the app runs. In tests: a fake debugging port counts exactly one
   handshake while the app's own client, two agents and a session all work.
2. **The bar stays closed.** Once the user closes the "controlled by automated test software" bar, it stays closed
   while the app's one connection lives. Nothing in the code touches it. (From Chromium's source; the hand check
   confirms it.)
3. **Agents see only their own tabs.**
   - An agent's connection sees and drives only tabs it opened, their popups, and tabs the user handed it.
   - A user's tab titled `SECRET-7f3a` appears in no CDP message the relay sends to an agent or a session, and in no
     tool result or task-log line.
   - Attaching to, activating or closing a tab the client may not use is refused, with Chrome's own "not found" words.
4. **Take back cuts at once.** When the user clicks Take back, the agent's session on that tab is detached before the
   server handles its next message. Its next command on that session is refused without reaching Brave. Today this
   can take up to 1 s.
5. **Only a short list of commands gets through.** At browser level only the list in Decision 7 passes. Reading
   cookies, closing or crashing Brave, changing permissions or download settings, overriding the user agent or
   `navigator.webdriver`, and attaching to the browser target are refused, and Brave never sees them.
6. **Locked down.** The relay refuses a handshake that carries any `Origin` header, a `Host` other than
   `127.0.0.1:<app port>`, or no valid token. The token travels only in the `X-AIB-Agent-Token` header.
7. **Claude Code sessions.**
   - While the app runs, a session goes through the relay and uses the app's browser, never Chrome by accident.
   - Without the app, a session connects directly, as today.
   - While the app is up, a session never connects to the app's browser on its own. If the relay fails, or the app
     stops under it, the session reports the error and connects nowhere.
8. **Reconnects follow the user.** The relay opens a new connection to Brave only right after something the user did
   (Decision 10). Everyone waiting shares one attempt. After a Deny nothing asks again by itself.
9. **AI Home lists what is connected.** Every client connected through the app, or holding tabs through it, shows in
   AI Home, with a Disconnect button for agents and sessions.
10. **Honest texts.** The terminal's switch steps, the setup page, AI Home's browser card and the README say "once
    each time AI Browser starts", and explain the standing grant. The everyday-brave spec's Decision 12 carries a
    note that this spec replaces it.
11. **Nothing else changes for agents.** Browser, live view, Website QA and the bot-check hold work through the relay
    unchanged. The engine's browser tests run through the relay as well as directly, except three named tests that
    check the `Browser` alone (Testing).

## What the user sees

### Starting the app

- The terminal and AI Home show the same states as today: switch off, ready, waiting for Allow, connected, not
  allowed, closed (`app/extension/home.js:34-35`).
- Brave asks "Allow remote debugging?" once. The terminal's switch text and AI Home's note say it is the only
  question for this run.
- AI Home's browser card gains a list under its title, **Using your Brave through AI Browser** (with the browser's
  own name, as the card's title has):
  - "AI Browser · the tab list and pictures" (always first while connected, no button);
  - one row per agent with a browser connection: "3 · Fix the footer · 2 tabs", in its colour, with **Disconnect**;
  - one row per Claude Code session: "Claude Code · 1 tab", in orange, with **Disconnect**;
  - under the list, one line: "Anything listed here can use your Brave without a new question until AI Browser quits.
    Disconnect cuts one off; unticking the switch cuts off everything."

### While agents work

- Giving a task, a New chat, an agent's crash and restart: no question.
- The automation bar: if the user closes it, it stays closed. It comes back only when the app or Brave restarts.
- Agents still work in background tabs in their groups, exactly as today.
- An agent never sees the titles or addresses of the user's other tabs, not even in browser events.
- **Take back:** the agent loses the tab at once. Its next tool call starts with "(the user took back tab tN)".
- **Disconnect on an agent's row:** its row then says "cut off from Brave". Its browser tools answer "The user cut this
  agent off from Brave in AI Home: tell the user. The browser stays off for this agent." Close still works as before
  and closes its tabs.

### Claude Code sessions

- **While the app runs:** no question. `sandbox_status` says "browser: your Brave, through AI Browser's connection ·
  only tabs this session opens …". The session's tabs go in the "Claude Code" group, as today. AI Home lists the
  session.
- **Without the app:** as today, one question per session.
- **The app stops or crashes while a session works:** the session's next browser call answers: "AI Browser stopped,
  so this session lost its connection to your Brave. Ask the user to start AI Browser again, or, if they want this
  session to connect to Brave by itself (Brave will ask "Allow remote debugging?"), call sandbox_start(chrome=true)."
  It connects nowhere until then.
- **Disconnect on a session's row:** its browser calls answer "The user disconnected this Claude Code session from
  Brave in AI Home: tell the user." While the app runs, that session can't use Brave again.
- **The app runs but doesn't answer** (its pid is alive, its server isn't): the session's browser calls answer "AI
  Browser didn't answer, so this session can't use your Brave through it now. Ask the user to look at the terminal
  where AI Browser runs." It connects nowhere.
- **`AIB_CHROME_DIR` naming another browser** than the app's (say Chrome while the app uses Brave): the session
  connects to that browser directly, as the user configured, and its status line says "not through AI Browser:
  AIB_CHROME_DIR names your Chrome".

### When Brave restarts, or the user clicks Deny

- **Brave quits or restarts:** AI Home says "closed". Every agent and session loses the browser at once. The first of
  these asks once: Connect, a new task or message, Continue on a bot check, a session's browser call, or the next
  browser step of an agent that was working (once Brave is open again). Everyone waiting shares that one question.
- **The user clicks Deny** (or nobody answers in 60 s): AI Home says "not allowed" with **Try again**. Agents and
  sessions waiting get "Brave said no to AI Browser's connection: ask the user to click Try again in AI Home". Nothing
  asks again by itself. The next Connect, Try again, or agent's turn (a new task, a message, Continue) asks once more.
- **The user unticks the switch:** Brave closes the connection. Everything is cut off, as today.

### The texts

The switch steps in the terminal (`app/run.py:76-84`), the setup page (`app/setup.html:74-90`), AI Home's browser
card (`app/extension/home.js:240-251`) and the README (`README.md:434-444`) change to the words in Messages /
interfaces, **Texts**.

## Decisions (with reasons)

### 1. The app holds the only connection, for its whole run

- **What:** the relay opens one websocket to Brave (the upstream). It keeps it open until the app quits, Brave quits,
  or the user unticks the switch.
- **Why:**
  - the user chose it;
  - Brave asks per connection (Status), so one connection means one question;
  - the bar only comes back when a connection opens or closes, so one long-lived connection keeps a closed bar closed;
  - identity and tab rules can only be enforced by the one holder of the approved connection.
- **Rejected:**
  - **dropping the connection after some idle minutes:** the user chose against it; it brings back one question and
    the bar each time;
  - **one connection per process (today):** 1 + N + M questions, and the bar keeps returning;
  - **a standalone `ai-browser relay` helper** for sessions without the app: a later step (Out of scope).

### 2. The relay is a route on the app's own server

- **What:** `WebSocketRoute("/cdp")` on the existing `AppServer` (`app/server.py:202-210`), so the address is
  `ws://127.0.0.1:<app port>/cdp`. It exists only in brave mode. In `--browser app` mode the route answers 404 and
  nothing changes (wave 3 retires that mode).
- **Why:** the app already listens on 127.0.0.1 only, holds the tokens and knows the agents. One process and one port
  keep "who is the app" simple.
- **The code:** a new module, `src/ai_browser/app/cdprelay.py`. It is one `Relay` per browser folder, so wave 4 can
  hold one per browser.

### 3. Clients speak plain CDP; the relay remaps ids and routes flattened sessions

- **What:** a client sends and receives ordinary CDP JSON. `Browser`, `LiveView`, Website QA and `TabWatch` need no
  protocol changes.
- **Ids:** the relay keeps one upstream id counter. For each forwarded command it records
  `pending[upstream id] = (client, the client's id, method, params)`. The answer goes back to that client only, with
  its own id, after the post-processing below.
- **Flattened sessions:**
  - `Target.attachToTarget` without `flatten: true` is refused;
  - the `sessionId` in the attach answer binds that session to the client;
  - in flatten mode Chrome sends `Target.attachedToTarget`, and possibly the session's first events, before that
    answer. Events for a session not bound yet wait in a buffer (`BIND_WAIT` = 2 s, at most `BIND_BUFFER` = 256 per
    session). The answer releases them to the client in order, then the answer itself. Unclaimed events are dropped
    after `BIND_WAIT`;
  - `Target.detachedFromTarget` goes to the session's client, then the binding is dropped;
  - `Target.attachedToTarget` and `Target.detachedFromTarget` arrive on the browser session with no top-level
    `sessionId`. The relay routes both by the session id in their `params`;
  - events carrying a top-level `sessionId` go to that session's client only. A `sessionId` inside `params` of any
    other message is page data to the relay (the live view's `Page.screencastFrameAck` carries one, `live.py:179`).
- **Discovery is per client:** the relay turns discovery on upstream once, when it connects (as `app/tabs.py:35` does
  today). A client's `Target.setDiscoverTargets {discover: true}` never reaches Brave. It sets a flag, the relay sends
  that client a `Target.targetCreated` for each target it may see, then answers `{}`. `{discover: false}` clears the
  flag.
- **Browser-level target events** (`targetCreated`, `targetInfoChanged`, `targetDestroyed`, `targetCrashed`) update
  the relay's cache. They go only to clients with discovery on, and only for targets that client may see (Decision 5).
- **A tab the client just created:** Chrome may announce it before the `createTarget` answer, when the relay doesn't
  yet know its owner. So, right before that answer, the relay sends the creator a `Target.targetCreated` from its
  cache, if the creator has discovery on. The relay remembers which `targetCreated` each client got, so none arrives
  twice.
- **Other browser-level events** go to the app's own client only. `Inspector.detached` goes to everyone.
- **Why:** this is what the engines already speak, and flatten mode keeps one socket per client.

### 4. Who a client is comes from its token

- **Agents:** a token per agent, minted when the agent is created (`AgentManager.create`, `app/agents.py:141-147`). It
  replaces the shared agent token (`app/server.py:148`) everywhere: `/cdp` and the HTTP routes (`/agent-events`,
  `/agent-claim`, `/agent-status`). So agent a1 can no longer post reports or claims as a2.
- **Claude Code sessions:** link.json's session token still buys `/agent-hello`, as today. `/agent-hello` now answers
  with a token for this session id, used only for `/cdp`. The session's HTTP reports keep using the session token.
- **The app itself:** an in-process client with no token (Decision 9).
- **How it travels:** in the `X-AIB-Agent-Token` handshake header, the header the engines already send on HTTP
  (`agentlink.py:48-49`). A token in the address is ignored, and the handshake is refused.
- **Lifetime:** tokens live in memory, new every app run. On disk they sit only in the 0600 files that carry them today:
  each agent's `mcp.json` (`app/bridge.py:304-305`) and link.json (`app/run.py:110-116`).
- **Identity, not connection:** the relay keys everything by identity (`a3`, `cc-<task id>`). An agent's engine that
  reconnects with the same token keeps its tabs: after New chat, a crash, or a dropped socket. A session's engine says
  bye before it reconnects, so its stale tabs are closed, as its own reconnect path closes them today (Decision 11).
- **Why:** the brief's "each agent gets its own token". A shared token can't tell agents apart, so it can't enforce
  whose tab is whose.

### 5. The relay decides which tabs a client may use

- **What a client may see and use** (its "visible" targets):
  - **own:** pages it created through the relay;
  - **popup:** a page whose `openerId` is one of its own pages, or a handed page it has a live session on;
  - **handed:** for an agent, the pages in `agent.adopted` right now. The relay reads it live from `AgentManager` on
    every check, never from a cache. Only Hand over or a task started in a tab puts a page there (both are clicks).
- **Popups become own when used:** a popup is visible to the opener's owner and may be attached. It counts as the
  client's own (owner chip, closed with the agent) only once that client attaches to it. A popup the engine never takes
  on stays the user's. This matches the engine, which takes on only popups its own steps opened (`browser.py:484-497`).
- **Everything else is hidden:** the user's tabs, other agents' tabs, private windows, other profiles, extension
  workers (including the watcher's). For a hidden target, the relay answers as Chrome does for a missing one.
- **The app's truth:** the relay's table decides ownership.
  - The server sets an AI Home owner chip when the relay records a grant (`Relay.on_grant`). It no longer waits for
    the engine's report.
  - An engine's tab report (`tab_opened`, `working_tab`, `check`) or claim about a target the relay doesn't grant to
    that agent or session (own, or handed) is dropped. This replaces `_hands_a_tab` (`app/server.py:363-371`) with a
    stronger check.
  - A report that passes keeps its kind, but its `adopted` flag comes from the relay (true only for a handed tab),
    never from the engine. So no report can add a tab to `agent.adopted` (`AgentManager.tab_event`,
    `app/agents.py:260-262`), and none can put a handed tab in `agent.tabs`, which closing the agent closes.
  - In `--browser app` mode there is no relay, and today's rules stay.
- **Closing an agent** closes its own tabs from the relay's table as well as from its reports (`AgentManager.close`,
  `app/agents.py:191-209`). A tab the engine opened but never reported is no longer left behind.
- **Why:** the brief's "an agent sees and drives only the tabs it opened, their popups, and tabs you handed it". The
  holder of the approved connection is the only place this can be enforced.
- **Rejected: trusting the engine's own check** (`browser.py:568-577`). It stays, but any process with a token could
  skip it.

### 6. Take back cuts at once

- **What:** the server's `take_back` (`app/server.py:513-516`) calls `Relay.cut(agent id, target)`. For every session
  that agent has on that target, the relay:
  1. marks the session cut, so any command on it is refused at once with "Session with given id not found.";
  2. fails that session's pending commands with the same error;
  3. sends `Target.detachFromTarget` upstream itself;
  4. forwards Chrome's `Target.detachedFromTarget` to the agent, then drops the binding.
  `agent.adopted` no longer lists the tab, so a new attach is refused too.
- **In the engine:** `Browser` listens for `Target.detachedFromTarget`. When it is for a handed tab's session, the tab
  is marked `detached`. The next call's `let_go_of_taken_back()` (`browser.py:588-605`) lets go of it with "(the user
  took back tab tN)", without waiting for the 1 s status cache. The engine's `_taken_back()` (`engine.py:271-280`)
  also counts a `detached` held tab as taken back, so a bot-check hold on it ends in the same call. If the user closed
  the tab instead, `Target.targetDestroyed` follows and the closed-tab note stays as today.
- **Why:** the brief asks for it. Today an agent can keep working in a taken-back tab for up to 1 s.
- **Not done:** a synthetic `Target.targetDestroyed` for the taken-back tab. The tab isn't gone, and the engine would
  report it as closed.

### 7. Only listed commands pass

- **Browser level** (no `sessionId`): an allowlist. For agents and sessions:

  | Command | Rule |
  |---|---|
  | `Target.setDiscoverTargets` | handled by the relay (Decision 3), never forwarded |
  | `Target.createTarget` | allowed; checks below |
  | `Target.attachToTarget` | visible targets only; `flatten: true` required |
  | `Target.detachFromTarget` | the client's own sessions only, by `sessionId` |
  | `Target.closeTarget` | own targets only; a handed tab can be let go of, never closed |
  | `Target.activateTarget` | own or handed targets |
  | `Target.getTargets` | forwarded; the answer is filtered to visible targets |
  | `Target.getTargetInfo` | visible targets only; a `targetId` is required |
  | `Browser.getVersion` | allowed |
  | `Browser.cancelDownload` | only a `guid` the relay saw in `Page.downloadWillBegin` on that client's own sessions |
  | `Browser.getWindowForTarget` | own or handed targets (the app: any) |

  Everything else at browser level is refused, among them `Browser.close`, `Browser.crash`,
  `Browser.setDownloadBehavior`, `Browser.grantPermissions`, `Browser.setPermission`, `Browser.resetPermissions`,
  `Target.attachToBrowserTarget`, `Target.setAutoAttach`, `Target.autoAttachRelated`, `Target.sendMessageToTarget`,
  `Target.exposeDevToolsProtocol`, `Target.createBrowserContext`, `Target.disposeBrowserContext`,
  `Target.getBrowserContexts`, and every `Storage.*`, `SystemInfo.*`, `Tethering.*`, `Extensions.*` and `PWA.*`.
- **`Target.createTarget` checks:**
  - the `url` must be `about:blank` (with or without the `#aib-<marker>` fragment), `http`, `https` or `data:`. It
    must not be the app's own origin, `http://127.0.0.1:<app port>/`, so an agent can't open `/setup` in Brave;
  - the app's origin is matched the way Chrome reads an address, not as text. Every loopback spelling of the host on
    the app's port is refused: `localhost` and `*.localhost`, any address in 127.0.0.0/8 written as Chrome accepts it
    (`127.1`, `2130706433`, `0x7f.0.0.1`, `0177.0.0.1`), `0.0.0.0`, `[::1]` and `[::ffff:127.0.0.1]`. Other local
    ports stay open: the tests' pages are served on `localhost` (`testpages.serve_host`);
  - the relay forces `background: true`, so no agent tab takes the user's focus. It allows `newWindow` (the fallback
    window, everyday-brave Decision 9);
  - `hidden: true`, `focus: true`, `forTab` and `enableBeginFrameControl` are refused. The AI's tabs stay in plain
    sight;
  - a `browserContextId` is allowed only when it equals the context of one of the client's own targets. So a client
    can never open a tab in a private window or another profile it learned of. No client needs it today: wave 4
    places tabs through the watcher and never sends one (browser-profile-choice, Decision 6).
- **Session level** (a `sessionId` the client owns): a domain and method allowlist.
  - **Whole domains**, because they act only inside that page: `Runtime`, `DOM`, `Input`, `IO`, `Log`.
  - **Listed methods only**, for domains that can reach past the page:
    - `Page`: `enable`, `setLifecycleEventsEnabled`, `addScriptToEvaluateOnNewDocument`, `getFrameTree`, `navigate`,
      `getNavigationHistory`, `navigateToHistoryEntry`, `reload`, `createIsolatedWorld`, `getLayoutMetrics`,
      `captureScreenshot`, `handleJavaScriptDialog`, `startScreencast`, `stopScreencast`, `screencastFrameAck`;
    - `Network`: `enable`, `loadNetworkResource`;
    - `Emulation`: `setFocusEmulationEnabled`, `setDeviceMetricsOverride`, `clearDeviceMetricsOverride`.
  - `Page.navigate` and `Network.loadNetworkResource` (Website QA's link checks, `qa/checker.py:85-87`) take the same
    address check as `createTarget`. It backs up `url_problem` (`browser.py:121-146`).
  - This is a backstop, not a wall: script in a page (`Runtime.evaluate`) can still go wherever a page may go. The
    app's own pages get their cookie and Host checks in wave 3. Until then `/setup` shows a key that only opens a
    file manager window (`app/server.py:263-271`).
  - Everything else is refused. That includes:
    - every cookie call (`Network.getCookies`, `getAllCookies`, `setCookie(s)`, `deleteCookies`,
      `clearBrowserCookies`);
    - `Network.clearBrowserCache`, `Network.setExtraHTTPHeaders`;
    - every user-agent, locale, timezone or automation override (`Network.setUserAgentOverride`,
      `Emulation.setUserAgentOverride`, `Emulation.setAutomationOverride`, `Emulation.setLocaleOverride`,
      `Emulation.setTimezoneOverride`);
    - `Page.setDownloadBehavior`;
    - every `Target.*`, `Browser.*`, `Storage.*`, `Fetch.*`, `Autofill.*`, `WebAuthn.*` and `FedCm.*`.
- **The app's own client** passes the same lists plus `Target.getBrowserContexts`, a read that wave 1B's profile
  filter needs. It sees and may attach to every target (Decision 9).
- **The answers:**
  - a refused command: CDP error `-32601`, "<method> isn't allowed through AI Browser's connection";
  - a hidden or unknown target: `-32602`, "No target with given id found";
  - a session the client doesn't own: `-32001`, "Session with given id not found.";
  - a handed tab in `closeTarget`: `-32000`, "a tab the user handed over can be let go of, never closed".
  Hidden and missing look the same, so a client can't probe for the user's tabs.
- **Why:** the brief's short list. Today any engine could read every cookie of the user's profile, or close Brave.
  The session-level list also makes the relay refuse spoofing, which this project never does.
- **The cost: the list can fall behind the code.** A new CDP call in `browser.py`, `live.py` or `qa/` fails through
  the relay until it is added here. A test reads every method the engine sends from the source and fails if the
  policy refuses one (Testing, test 18). Its one named exception is `Browser.setDownloadBehavior`, which the engine
  sends only in the Docker sandbox (`browser.py:377-379`), never through the relay. The engine's browser tests also
  run through the relay.

### 8. The handshake is locked down

- **Checks, before anything else**, in this order:
  1. **`Origin`:** any `Origin` header, even `null`, is refused. Web pages always send one; our clients never do
     (the `websockets` client sends none unless asked).
  2. **`Host`:** it must be exactly `127.0.0.1:<app port>`. That blocks DNS rebinding.
  3. **Token:** `X-AIB-Agent-Token` must belong to a known identity (`hmac.compare_digest`).
- **Refusals are HTTP answers before the upgrade** (Starlette's `WebSocket.send_denial_response`, which needs the
  server's `websocket.http.response` extension; uvicorn's `websockets-sansio` implementation offers it), so the client
  can read why:
  - **403 "refused":** a failed check above. It never says which one;
  - **410:** the user disconnected this client in AI Home (Decision 14), or its agent has closed;
  - **409:** no browser connection, and this client may not open one now (Decision 10). The body says why.
- **After the upgrade, close codes:** 4400 a message that isn't CDP, 4401 the user disconnected it, 4408 too slow
  (Decision 12), 4410 the browser connection is gone, 1001 the app is quitting (`server.stop()` closes the relay's
  client sockets with it once the agents have ended, before uvicorn stops).
- **The server is pinned to `ws="websockets-sansio"`** in `AppServer.start`'s `uvicorn.Config`
  (`app/server.py:219-220`), and `pyproject.toml`'s floor rises from `uvicorn>=0.30` to `uvicorn>=0.38` (`uv.lock`
  follows). Why: Decision 10 holds a handshake for up to 60 s. uvicorn's older `websockets` implementation runs the
  handshake under the `websockets` library's `open_timeout`, 10 s by default (`websockets/legacy/server.py`), and
  uvicorn passes none. The sans-I/O one has no handshake timeout. Checked in uv's cache: 0.38.0 and 0.40.0 ship
  `websockets_sansio_impl.py`, but their `auto` still picks the older one; the locked 0.54.0's `auto` picks the
  sans-I/O one. So the pin changes nothing at run time today, and it keeps an older install from cutting the hold at
  10 s.
- **Why:** the brief's "refuses any connection that carries a web page's Origin or a Host other than
  `127.0.0.1:<port>`". A browser page can't set a custom header on a websocket, so it can't present a token either.

### 9. The app's own client is in-process and privileged

- **What:** `Relay.local()` returns a `LocalClient` with the same methods as `cdp.CDP` (`send`, `on`, `off`,
  `wait_for`, `closed`, `close`). `TabWatch` runs over it instead of a websocket of its own. So `BraveLink` never opens
  a second connection.
- **Its rights:**
  - it sees every target, for the tab list. That includes service workers, from which wave 1B learns the watcher's
    profile, and it may read `Target.getBrowserContexts` for the default context (wave 1B, its "For the later waves");
  - it may attach to any target. `BraveLink` still pictures and reads only readable tabs (`app/bravelink.py:22`,
    `:160-182`), and the page the user picked in the Train form;
  - it may activate any target (Watch is the user's click). It may close a target that an agent or session owns in
    the relay's table (closing an agent, Skip this site), never one nobody owns and never a handed one;
  - wave 5 uses its `Browser.getWindowForTarget` to match the side chat's tab.
- **Why:** the app's code is the trusted part; it already makes these choices today.
- **Two sessions on one tab** (an agent's, and the app's for a thumbnail) are separate upstream sessions. That works,
  and a test covers it.

### 10. When the relay may ask Brave

- **The states** move from `BraveLink` into the relay, with the same names: `off`, `ready`, `asking`, `connected`,
  `refused`, `lost`. AI Home's card is unchanged. While not connected, the relay looks at the switch every 2 s with a
  TCP check only (`chrome.switch_on`), which never asks anything, as `BraveLink` does today (`app/bravelink.py:90-99`).
- **Who may open the upstream, and from which state.** `Relay.open(why, identity)`:

  | Asked by | connected | asking | ready | lost | refused | off |
  |---|---|---|---|---|---|---|
  | `start`: the app starts (`app/run.py:230-234`) | n/a | n/a | opens | n/a | n/a | stays off |
  | `connect`: Connect or Try again in AI Home | nothing | joins | opens | opens | opens | stays off |
  | `turn`: an agent's turn starts (`app/server.py:174`) | nothing | joins | opens | opens | opens | stays off |
  | `client`: an agent's engine connects during its turn | accepted | waits | opens | opens | 409 | 409 |
  | `client`: an agent's engine connects outside a turn | accepted | waits | 409 | 409 | 409 | 409 |
  | `client`: a Claude Code session connects | accepted | waits | opens | opens | 409 | 409 |

  - "Accepted" opens nothing: the upstream is already there. "Waits" holds the handshake on the attempt under way,
    then accepts or refuses it with that attempt's outcome. "Opens" is the one place a question can start.
  - A turn starts only from something the user did: a task, a message, a hand-over note, Continue, or a workflow the
    user scheduled (the everyday-brave exception). That is today's rule (`app/server.py:485-488`).
  - A working agent whose browser went away (Brave quit, restarted or was switched off) may open from `lost` at its
    next browser step. That step belongs to the turn the user started; today each engine does the same on its own
    (`engine.py:383-391`). The texts say so (What the user sees).
  - A session's call follows the user's request in Claude Code, so it may ask from `ready` or `lost`, as a lone
    session's direct connection would.
  - "During its turn" is `AgentManager.working(agent id)`.
  - A cut-off identity (Decision 14) opens nothing: its turn doesn't call `open`, and its handshake gets 410 first.
- **One shared attempt:** `open()` is single-flight. A second caller while `asking` waits on the same attempt. A
  client's handshake is held, not yet accepted, for up to `ALLOW_WAIT` (60 s), and then accepted or refused. So
  everyone waiting sees one question. The pinned `websockets-sansio` server has no handshake timeout (Decision 8), so
  holding it is safe. The engine's connect waits `RELAY_WAIT` = 65 s, so the relay's answer comes first.
- **Deny is never retried:** `refused` stays until Connect, Try again, or a new turn. A client's own connect never
  asks again after a Deny. It gets 409: "Brave said no to AI Browser's connection: ask the user to click Try again in
  AI Home".
- **Why:** the brief's "reconnecting happens only right after something you did … if you click Deny, nothing retries
  by itself". This is the same consent timing as `app/bravelink.py:1-8`.

### 11. When something drops

- **A client goes away** (its socket closes): the upstream stays. The relay detaches every session that client had,
  which ends its focus emulation, scripts and Network buffers on those tabs. Its pending answers are dropped. Its tabs
  stay open: the identity may come back, and its tabs stay its own.
- **The upstream drops** (Brave quit or restarted, or the switch went off):
  1. every pending command fails with `-32000` "browser connection lost";
  2. each client gets a `Target.detachedFromTarget` for each of its sessions;
  3. every client socket closes with 4410;
  4. the state becomes `lost`. Grants by identity stay. Targets that don't come back in the next discovery are
     pruned.
  The engines then take their existing reconnect path (`engine.py:383-391`), which now reconnects to the relay. They
  never connect to Brave themselves.
- **An agent closes:** the server calls `Relay.forget(agent id)`. Its sockets close, its token is revoked, and its
  grants go once `AgentManager.close` has closed its tabs.
- **A session ends:** `/agent-bye` runs `relay.forget(id, close_tabs=True)`: the relay closes the session's own tabs
  that are still open, then forgets it. After a clean end there are none left, because the engine closed them. The
  close matters on the engine's reconnect path: `_teardown` says bye (`engine.py:360-364`) before `_start_chrome`
  says hello again, so the stale tabs the engine then tries to close (`engine.py:385-390`) are no longer its own, and
  the relay has already closed them. When the 30 s sweep finds a session's process gone (`app/server.py:461-469`), it
  does the same. Through the relay a session's engine skips `_register`/`_close_orphans` (`engine.py:236-238`, and
  the `_register` after each tool, `:414`), as app agents already do, because the app cleans up.
- **The app quits:** `run.py` ends the agents (`server.stop()`) before it closes the relay (`brave.close()`), the
  reverse of today's order (`app/run.py:264-266`). So no agent sees its browser vanish while it still runs. Inside
  `server.stop()`, after `agents.close_all()`, the relay's client sockets close with 1001 before uvicorn stops. The
  agents' tabs and groups stay in Brave, as today.
- **After an app restart,** a session's earlier tabs belong to nobody in the new run. Its engine's attempt to close
  them is refused, and they stay open in Brave as plain tabs, like the tabs a quitting app leaves.

### 12. A slow client is cut, never the browser link

- **What:** each client has a bounded outbound queue (`QUEUE_BYTES` = 64 MiB, `QUEUE_MESSAGES` = 10,000). The upstream
  reader only ever puts messages on queues; it never waits on a client. A client whose queue overflows (screenshots,
  screencast frames) is closed with 4408, and its sessions are detached.
- **Inbound limits:** uvicorn's default 16 MiB per message from a client. The upstream socket has no size limit
  (`max_size=None`, as `cdp.py:37`), because a full-page screenshot can be large.
- **Why:** one socket now carries everyone, so one stalled reader must not freeze every agent.

### 13. Claude Code sessions: through the app while it runs, never a silent fallback

- **The engine's choice of route**, in `_start_chrome("chrome")` (`engine.py:182-240`):
  1. **An app agent** (`AIB_APP_AGENT` set): `AIB_APP_CDP` with its own `AIB_APP_AGENT_TOKEN`. Always the relay; never
     direct. In `--browser app` mode nothing changes.
  2. **A session** with a running app (`AgentLink.discover` finds link.json with a live pid, a valid `cdp` and a
     `browser_dir`):
     - if `AIB_CHROME_DIR` is unset, or names the app's `browser_dir` (compared with `chrome._same_folder`,
       `chrome.py:133-138`: resolved, and without regard to case on Windows): say hello, take the `cdp_token`, connect
       to the relay;
     - if `AIB_CHROME_DIR` names another folder: connect to that browser directly, as the user configured. The status
       line says "not through AI Browser: AIB_CHROME_DIR names your {name}", with that folder's browser name.
  3. **A session with no app:**
     - if this session went through the relay before and the user hasn't since chosen otherwise: refuse with the
       "AI Browser stopped …" text (What the user sees);
     - else connect directly, as today.
  4. `sandbox_start(chrome=true)` is the user's explicit choice. It allows step 3's direct connection, but only when no
     app is running. While the app runs, a session never connects directly to the app's browser, even after a
     Disconnect; only step 2's `AIB_CHROME_DIR` case goes direct, to another browser.
- **Errors while the app is up** become a `ChromeError`, and none is ever followed by a direct attempt:
  - a 403, 409 or 410 from `/cdp`: the relay's text (Messages / interfaces);
  - `/agent-hello` answering 410 (a session the user disconnected): `CUT_OFF_SESSION`;
  - no answer to the hello, or a refused connection to `/cdp`: `APP_GONE` when link.json's pid has ended meanwhile,
    else `APP_SILENT`.
- **`ai-browser doctor --own`** (`cli.py:244-275`) is a session too. While the app runs it checks the relay path,
  says hello, and shows in AI Home's list until it ends. Without the app it connects directly, as today.
- **The browser's name:** a relay session takes it from link.json's `browser_dir`, not from `own_browser_dir()`, which
  could answer "Chrome" while Brave restarts (`engine.py:291-292`). That ends "sometimes Chrome".
- **A session already connected directly when the app starts** keeps that connection. It goes through the relay the
  next time it connects.
- **Why:** the user chose "yes to both", and the brief says the session reports the error and never quietly connects
  on its own, because that would make Brave ask out of the blue.

### 14. AI Home lists what is connected, with Disconnect

- **The list:** `Relay.clients()` gives one row per identity with an open socket or own tabs:
  `{"id", "kind": "app" | "agent" | "session", "number", "name", "color", "tabs": <own tab count>, "connected": bool,
  "cut_off": bool}`. `number` is the agent's id number from wave 1A (`int(id[1:])`), and `null` for the app and
  sessions; the page draws an agent's row with 1A's `agentLabel`. The server broadcasts it as `browser_clients` and
  puts it in the snapshot.
- **Disconnect** (agents and sessions; the app's row has none) sends `browser_disconnect {"id"}`. The relay:
  - adds the identity to its cut-off set for the rest of the run. `forget` never clears that set;
  - closes its sockets with 4401;
  - detaches its sessions;
  - refuses its next handshake with 410. For a session, `/agent-hello` with that id also answers 410, with no token.
  Its own tabs stay open. Closing the agent closes them; a session's are closed when it ends (Decision 11).
- **Only AI Browser's own pages send it.** It gets a row in wave 1B's `MESSAGE_RULES`, allowed for the "app" role
  only. `browser_clients` stays out of wave 1B's `WATCHER_RECEIVES`, so watcher sockets never get the list.
- **Honest about its limits:** Disconnect stops that client. It is no wall against a program that can read AI
  Browser's files: such a program could join again under a new name, and the list would show it. Unticking the switch
  stops everything.
- **Why:** the brief's mitigation for the standing grant: "AI Home lists who is connected, with a Disconnect button".

### 15. New consent texts; everyday-brave Decision 12 is replaced

- **What:** every place that tells the user to expect a question per agent changes to the words in Texts, with three
  points:
  - Brave asks once each time AI Browser starts, and again after Brave restarts;
  - when to click Allow: right after starting AI Browser, clicking Connect, giving an agent a task, asking Claude Code
    to browse, or opening Brave again while an agent was working (Decision 10). A question at any other time isn't AI
    Browser's;
  - the standing grant: a program that can read AI Browser's files can use Brave through it without a new question,
    and AI Home lists what is connected.
- **The bar text** says the bar stays closed once the user closes it, until AI Browser or Brave restarts, and that AI
  Browser never hides or closes it.
- **The everyday-brave spec** (`docs/superpowers/specs/2026-10-02-everyday-brave-design.md`) gets notes, and nothing
  else in it is rewritten:
  - at Decision 12 (`:445-461`);
  - at success criterion 2 (`:66-70`);
  - at the Out of scope line "A relay through the app's one connection" (`:965-966`).
- **Why:** the old text tells the user to expect many questions. With the relay, that could lead them to Deny the one
  question that matters, or to trust a question that comes from somewhere else.

### 16. What the relay can't change

- **Other tools still ask.** chrome-devtools-mcp or Playwright in a Claude Code session open their own connections.
  Those ask again and bring the bar back. The texts say a question at another time isn't AI Browser's.
- **Profiles:** `createTarget` without a context still lands in the profile the user used last. The relay records
  each own target's `browserContextId` but pins nothing. Wave 4 places tabs through the watcher.
- **The bar after restarts:** a new connection after an app or Brave restart brings a new bar. That is Brave telling
  the truth.

## Messages / interfaces

### New module: `src/ai_browser/app/cdprelay.py`

- **Constants:**
  - `ALLOW_WAIT = 60` and `SWITCH_EVERY = 2.0`, moved from `app/bravelink.py:20-21` (`bravelink` re-exports them);
  - `BIND_WAIT = 2.0`, `BIND_BUFFER = 256`;
  - `QUEUE_BYTES = 64 * 1024 * 1024`, `QUEUE_MESSAGES = 10_000`;
  - `TOKEN_HEADER = "x-aib-agent-token"`, `APP = "app"`;
  - close codes `NOT_CDP = 4400`, `CUT_OFF = 4401`, `TOO_SLOW = 4408`, `GONE = 4410`;
  - `BROWSER_COMMANDS`, `SESSION_DOMAINS`, `SESSION_METHODS`: the tables of Decision 7;
  - `APP_COMMANDS = {"Target.getBrowserContexts"}`: the app's client's one extra read.
- **Policy, as pure functions** (unit-tested, used by the drift test):
  - `allowed(method: str, level: str, app: bool = False) -> bool`, where `level` is `"browser"` or `"session"`, and
    `app` adds `APP_COMMANDS`;
  - `address_problem(url: str, app_port: int) -> str | None`: Decision 7's scheme list and app-origin check, with the
    host read as Chrome reads it (`ipaddress` after Chrome's IPv4 forms: one to four parts, each decimal, octal or
    hex).
- **`class Tokens`** (owned by `AppServer`, also used without a relay):
  - `mint(identity) -> str` (`secrets.token_urlsafe(24)`; minting again for the same identity returns the same token);
  - `check(identity, given) -> bool` (`hmac.compare_digest`);
  - `who(given) -> str | None`: the identity a `/cdp` token belongs to;
  - `revoke(identity)`.
- **`class Relay(folder: Path, tokens: Tokens, allow_wait=ALLOW_WAIT, every=SWITCH_EVERY)`:**
  - `state`, `name` (`browser_name(folder)`), `port` (set by the server once it listens);
  - `upstream_opens: int`: handshakes started to the browser. Tests count questions with it;
  - hooks set by the server:
    - `handed: Callable[[str], set[str]]`: an agent's handed targets, read live;
    - `may_open: Callable[[str], bool]`: an agent is in a turn, or the identity is a session;
  - `async start()`: the switch look, every `every` seconds, TCP only;
  - `async open(why: str, identity: str = "") -> bool`: Decision 10's table; single-flight; nothing for a cut-off
    identity;
  - `async close_clients(code: int = 1001)`: closes every client socket, and keeps the upstream;
  - `async close()`: the client sockets, then the upstream;
  - `async serve(ws: WebSocket)`: the `/cdp` route (Decision 8), then the client's read and write loops;
  - `local() -> LocalClient`: the app's own client (Decision 9);
  - `grants(identity, target) -> bool`: own, including attached popups;
  - `visible(identity, target) -> bool`;
  - `own_targets(identity) -> list[str]`;
  - `async cut(identity, target)`: Take back (Decision 6);
  - `async disconnect(identity)`: AI Home's Disconnect;
  - `async forget(identity, close_tabs: bool = False)`;
  - `clients() -> list[dict]`;
  - `on_state(cb(state))`, `on_change(cb())`, `on_grant(cb(identity, target))`.
- **Inside:**
  - `Upstream`: one `websockets` client connection to `find_ws_url(folder)` (`max_size=None`, `ping_interval=None`,
    `open_timeout=allow_wait`, `proxy=None`), a reader task and a send lock;
  - `Client`: identity, socket, outbound queue and byte count, discovery flag, bound session ids, seen download guids;
  - `targets`: `{target id: {type, url, title, openerId, browserContextId}}` from discovery and every `getTargets`
    answer that passes;
  - `grants`: `{target id: (identity, "own" | "popup")}`;
  - `sessions`: `{session id: (client, target id, cut: bool)}`;
  - `pending`: `{upstream id: (client | None, client id, method, params)}`. `None` marks the relay's own commands:
    discovery, cut, detaching for a client that left;
  - `cut_off: set[str]`;
  - `log`: refusals with the method and the identity only, never params or page text.

### Engine side

- **`cdp.py`:** `CDP.connect(ws_url, open_timeout=10, headers: dict[str, str] | None = None)` passes
  `additional_headers=headers` and `proxy=None` to `websockets` (`cdp.py:35-38`). No `Origin` is sent.
  - `proxy=None` because `websockets` 15 and later use the system's proxy by default (`proxy=True`,
    `websockets/asyncio/client.py`), and Python's `proxy_bypass` doesn't always exempt `127.0.0.1`: with
    `HTTP_PROXY` set and no `NO_PROXY`, or with a Windows proxy whose `<local>` rule matches only dotless names. A
    token in a header must never pass through a proxy. Every address `CDP.connect` is given is on this computer, so
    the change is right for the direct and sandbox connections too. `agentlink` already does the same for HTTP
    (`agentlink.py:19`).
- **`agentlink.py`:**
  - `AgentLink` gains `cdp: str | None` and `browser_dir: Path | None`;
  - `discover()` (`:105-117`) reads link.json's optional `cdp` and `browser_dir`. A `cdp` that fails `_local_cdp` is
    ignored;
  - new `_local_cdp(url) -> bool`, the twin of `_local_events` (`:120-130`): scheme `ws`, host `127.0.0.1` itself (no
    user part), a port, path `/cdp`, no query or fragment;
  - `hello() -> dict | None` (`:83-85`): the app's JSON answer (`{"cdp_token": …}`), `{"cut_off": True}` when it
    answered 410, `{}` when it answered 204, and `None` when it failed. It reads the status itself, because
    `_request` turns every HTTP error into `None` (`:95-99`).
- **`engine.py`:**
  - `RELAY_WAIT = 65`;
  - `APP_GONE`, `APP_SILENT`, `CUT_OFF_AGENT`, `CUT_OFF_SESSION`: the texts in What the user sees;
  - `_route() -> ("relay", url, token, browser_dir) | ("direct", folder)`: Decision 13;
  - `_start_chrome("chrome")` connects with
    `CDP.connect(url, open_timeout=RELAY_WAIT, headers={"X-AIB-Agent-Token": token})`, maps
    `websockets.exceptions.InvalidStatus` (403, 409, 410, with its body) to `ChromeError`, and never tries direct
    after a relay failure;
  - a relay session says hello before it connects (it needs the token), so the later hello (`engine.py:223-226`)
    is skipped for it;
  - `self._via_relay` and `self._direct_ok` (set by `sandbox_start(chrome=true)`) drive step 3 of Decision 13;
  - `_register`/`_close_orphans` are skipped through the relay;
  - `_taken_back()` (`:271-280`) ends a hold on a handed tab that is `detached` (Decision 6);
  - `_browser_name()` uses the link's `browser_dir` through the relay;
  - `_status_text()` (`engine.py:516-532`) says "browser: your Brave, through AI Browser's connection · …", or "… ·
    not through AI Browser: AIB_CHROME_DIR names your {name}".
- **`browser.py`:**
  - `Tab` (`:66-80`) gains `detached: bool = False`;
  - `Browser` listens for `Target.detachedFromTarget`. For a handed tab's session it sets `detached`;
  - `let_go_of_taken_back()` lets go of a tab that is no longer handed or is `detached`.

### App side

- **`app/agents.py`:**
  - `AgentManager.mint_token: Callable[[str], str] | None`: set by the app. `create()` puts the agent's own token in
    its env as `AIB_APP_AGENT_TOKEN` (`:143`);
  - `AgentManager.own_tabs: Callable[[str], list[str]] | None`: set by the app in brave mode. `close()` closes
    `agent.tabs` together with `own_tabs(id)`;
  - `working(agent_id) -> bool`: the agent is in a turn (`agent_id in self._turns`).
- **`app/bravelink.py`:**
  - `BraveLink(folder, watcher_id="", allow_wait=ALLOW_WAIT, every=SWITCH_EVERY, tokens: Tokens | None = None)`
    (wave 1B's signature, plus `tokens`) creates `self.relay = Relay(...)`;
  - `state` and `on_state` read the relay's;
  - `start()` starts the relay's switch look; `_watch_switch` goes;
  - `connect(why="connect", identity="")` calls `relay.open(why, identity)`. On `connected` it starts its `TabWatch`
    over `relay.local()`. On `lost` it drops it;
  - `close()` closes the `TabWatch`, then the relay;
  - the tab list, owners, Watch, thumbnails and page text are unchanged. Its docstring says it now also carries every
    agent and session.
- **`app/tabs.py`:** `TabWatch` gains a keyword `cdp=None`. With `cdp` given, `start()` uses it and connects nothing
  (`:30-36`). Wave 1B's reads (contexts, service workers, the default context) stay as they are. AI Browser's own
  `TabWatch` (`app/run.py:217`) still connects directly to AI Browser's Chrome, which never asks.
- **`app/server.py`:**
  - `self.tokens = Tokens()`. `self.agent_token` goes; `agents.mint_token = self.tokens.mint`;
  - `token_for(agent_id) -> str` (`tokens.mint`), for tests and `run.py`;
  - `start()` (`:219-220`): `uvicorn.Config(..., ws="websockets-sansio")` (Decision 8);
  - `WebSocketRoute("/cdp", self._cdp)`: a 404 denial without a relay, else `self.brave.relay.serve(ws)`;
  - `_token_ok(request, agent)` (`:303-307`): an agent's own token for agent ids, the session token for `cc-` ids.
    `_agent_events` (`:280-284`) drops its "either token" check for that;
  - `/agent-hello` (`:437-448`): with a relay it answers `{"cdp_token": tokens.mint(session id)}`. A cut-off id gets
    410 and is not listed again. Without a relay it answers 204, as today;
  - `/agent-bye` (`:450-459`) and the sweep (`:461-469`): `relay.forget(id, close_tabs=True)` (Decision 11);
  - reports and claims: in brave mode, a `tab_opened`, `working_tab` or `check` report, or a claim, about a target
    the relay doesn't grant to that identity (own, or handed) is dropped (claims answer
    `{"grouped": false, "reason": "not_yours"}`). A kept report's `adopted` is the relay's answer, not the engine's
    (Decision 5). `_hands_a_tab` goes;
  - `attach_brave(brave)` (`:477-483`):
    - sets `relay.port`, `relay.handed` (`set(agent.adopted)`, live) and `relay.may_open`;
    - sets `agents.own_tabs = relay.own_targets`;
    - sets `relay.on_grant` to put the owner chip (`_own`);
    - sets `relay.on_change` to broadcast `browser_clients`;
  - `connect_brave(why, identity="")` (`:485-488`): `"start"`, `"connect"` or `"turn"`. `on_turn` (`:174`) passes
    `"turn"` and the agent's id;
  - `stop()` (`:232-250`): after `agents.close_all()`, `await relay.close_clients(1001)`, then uvicorn stops;
  - `take_back` (`:513-516`): `await relay.cut(had, target)` once `agents.take_back` returns the agent;
  - `_forward` (`:618-627`): on `agent_closed`, `relay.forget(id)` and `tokens.revoke(id)`;
  - `browser_disconnect` gets an app-only row in wave 1B's `MESSAGE_RULES` (today's `BRAVE_MESSAGES`, `:61`), and is
    handled beside `brave_connect`;
  - the snapshot (`:944-949`) gains `browser_clients`;
  - no token ever goes into a broadcast, the snapshot or `sessions`.
- **`app/run.py`:**
  - brave mode: `brave = BraveLink(own, watcher_id=extension_id_for(watcher), tokens=server.tokens)`. It keeps wave
    1B's `watcher_id` (its run.py line), so the tab list keeps the watcher's profile;
  - `agents.env` gains `AIB_APP_CDP = ws://127.0.0.1:<port>/cdp` and loses the shared `AIB_APP_AGENT_TOKEN`
    (`:207-208`). Each agent's own token comes from `create()`;
  - `write_link(home, url, token, cdp, browser_dir)` (`:110-116`);
  - `server.connect_brave("start")` (`:234`);
  - the `finally` block runs `server.stop()` before `brave.close()` (Decision 11);
  - `SWITCH` (`:76-84`): the new text.
- **`app/bridge.py`:** no code change. Each agent's `mcp.json` already carries its env, mode 0600 (`:297-305`); a test
  pins that it holds `AIB_APP_CDP` and that agent's own token.

### link.json and the environment

- **link.json** (`<home>/app/link.json`, 0600, removed at exit), written in brave mode only:
  `{"events": "http://127.0.0.1:<port>/agent-events", "session_token": "…", "pid": <app pid>,
  "cdp": "ws://127.0.0.1:<port>/cdp", "browser_dir": "<the app's browser folder>"}`.
- **Each agent's env:**
  - `AIB_APP_AGENT`;
  - `AIB_APP_EVENTS` (as today);
  - `AIB_APP_AGENT_TOKEN`: now this agent's own;
  - `AIB_APP_CDP` (new; brave mode only);
  - `AIB_BROWSER=chrome`, `AIB_CHROME_DIR` (`app/run.py:105-107`, as today).

### HTTP (engines → app; 127.0.0.1 only)

| Route | Change |
|---|---|
| `POST /agent-events`, `POST /agent-claim`, `GET /agent-status` | an agent id needs that agent's own token; reports and claims about targets the relay doesn't grant are dropped (brave mode) |
| `POST /agent-hello` (session token) | answers `{"cdp_token": "…"}` with a relay; 410 for a cut-off session id; 204 without a relay |
| `POST /agent-bye` (session token) | also closes the session's remaining own tabs and forgets it in the relay |

### WebSocket `/cdp` (engines and sessions → app)

- **Handshake:** `GET ws://127.0.0.1:<port>/cdp` with `X-AIB-Agent-Token: <token>`, no `Origin`,
  `Host: 127.0.0.1:<port>`.
- **Refused before the upgrade**, with a plain-text body:
  - 403 `refused`;
  - 410 `The user disconnected this client in AI Home.`;
  - 409, worded per state, with `{name}` and `{inspect}` from the relay's folder (`chrome.browser_name`,
    `chrome.inspect_address`):
    - `off`: "{name}'s remote-debugging switch is off: the user turns it on at {inspect}";
    - `refused`: "{name} said no to AI Browser's connection: ask the user to click Try again in AI Home";
    - `ready` or `lost` with no right to open: "AI Browser isn't connected to {name}: ask the user to click Connect in
      AI Home";
    - quitting: "AI Browser is quitting".
- **After the upgrade:** plain CDP both ways. Close codes 4400, 4401, 4408, 4410 and 1001 (Decision 8).

### WebSocket: app ↔ pages

- **server → pages:**
  - `browser_clients {"clients": [{"id", "kind", "number", "name", "color", "tabs", "connected", "cut_off"}]}`, also
    in the snapshot;
  - `browser` (`app/server.py:490-497`): unchanged.
- **pages → server:** `browser_disconnect {"id": "a3" | "cc-…"}`. AI Browser's own pages only, never the watcher.

### Texts

- **`SWITCH`** (`app/run.py:76-84`):

  ```
  Agents browse in your {name}, but its remote-debugging switch is off, so nothing reaches it yet. Once:
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
  Once the switch is on, AI Home's browser card has a Connect button.
  ```

- **The setup page** (`app/setup.html:81-90`):
  - step 3: "When Brave asks **Allow remote debugging?**, click **Allow**. AI Browser holds one connection for all its
    agents and Claude Code sessions, so Brave asks once each time AI Browser starts, and again after Brave restarts.";
  - the warnings keep "any program on {{THIS_COMPUTER}} can reach your Brave" and "Turn it off …". They add: "While AI
    Browser is connected, a program that can read AI Browser's files can also use your Brave through it without a new
    question. AI Home lists everything connected, with Disconnect.";
  - the Allow line: "Only click Allow right after you started AI Browser, clicked Connect, gave an agent a task, asked
    Claude Code to browse, or opened Brave again while an agent was working. If Brave asks at any other time, it isn't
    AI Browser: click Deny, unless you just started another browser tool yourself.";
  - the bar: "While AI Browser is connected, Brave shows a bar saying it is being controlled by automated test
    software. That is Brave telling you the truth; AI Browser never hides or closes it. If you close it yourself, it
    comes back only when AI Browser or Brave restarts."
- **AI Home** (`app/extension/home.js:240-245`):
  - `ready`: `${name} will ask "Allow remote debugging?" once for AI Browser: click Allow`;
  - `asking`: `${name} is asking "Allow remote debugging?": click Allow there (or Deny). Everything waiting for ${name}
    shares this one question.`;
  - the list of Decision 14 under `#browser-card` (`app/extension/home.html:18-24`): a new `<ul id="browser-clients">`
    and its line, rendered with `textContent` only.
- **README** (`README.md:434-444`): step 2 becomes "When Brave asks **Allow remote debugging?**, click **Allow**.
  Brave asks once when `ai-browser app` connects, and again after Brave restarts. While the app runs, agents and Claude
  Code sessions share its one connection; without it, each Claude Code session asks once." The Allow line, the bar
  line and the standing-grant line match the setup page.
- **The everyday-brave spec:**
  - under Decision 12's heading: "**Replaced on 2026-10-03** by the cdp-relay spec
    (`2026-10-03-cdp-relay-design.md`): the app holds the only connection, agents and Claude Code sessions go through
    it while it runs, and Brave asks once per app run.";
  - at success criterion 2: "(Since the cdp-relay spec: once per app run.)";
  - the Out of scope line at `:965-966` ends "(built: the cdp-relay spec)".

### Files

- **New:**
  - `src/ai_browser/app/cdprelay.py`;
  - `tests/test_cdprelay.py`, `tests/test_cdprelay_chrome.py`.
- **Changed:**
  - engine side: `cdp.py`, `agentlink.py`, `engine.py`, `browser.py`;
  - app side: `app/agents.py`, `app/bravelink.py`, `app/tabs.py`, `app/server.py`, `app/run.py`;
  - pages: `app/setup.html`, `app/extension/home.html`, `app/extension/home.js`, `app/extension/home.css`;
  - docs: `README.md`, `docs/superpowers/specs/2026-10-02-everyday-brave-design.md`;
  - packaging: `pyproject.toml` (`uvicorn>=0.38`) and `uv.lock` (its recorded specifier; the CI runs
    `uv sync --locked`, `.github/workflows/tests.yml`);
  - tests: `tests/fake_brave.py`, `tests/conftest.py`, `tests/test_bravelink.py`, `tests/test_app_server.py`,
    `tests/test_app_run.py`, `tests/test_engine.py`, `tests/test_chrome.py`, `tests/test_grouping.py`,
    `tests/test_bridge.py`, `tests/test_watcher.py`, `tests/test_watcher_groups.py`, `tests/test_home.py`.
- **Not touched:** `chrome.py` (wave 4), `browsers.py` and `platforms.py` (2B), the watcher's files (waves 3, 4 and
  5).

## Safety

**The browser's own signs stay:**
- The relay never answers, clicks, suppresses or hides "Allow remote debugging?", and never touches the automation
  bar. CDP offers no command for either, and the relay sends none that could.
- It only makes fewer connections, so Brave asks less often and the bar comes back less often.
- The upstream opens only right after something the user did (Decision 10). A Deny is never retried by itself.
- Unticking the switch still cuts everything off.

**No spoofing, no bypassing:**
- The relay refuses every user-agent, locale, timezone and `navigator.webdriver` override (`Emulation.*` and `Network.*`
  outside the short list; Decision 7). So even a client that tried couldn't disguise the browser.
- It refuses hidden tabs. The AI's tabs stay in plain sight.
- It does nothing about bot checks. The safe-browsing hold and hand-off are unchanged.

**Passwords:** the relay refuses `Autofill.*`, `WebAuthn.*` and `FedCm.*`, and every cookie call. The engine still
never types a password. The user logs in, in that tab, themselves.

**Only the AI's tabs:**
- A client sees and drives only its own tabs, their popups, and tabs the user handed it (Decision 5).
- The user's other tabs' titles and addresses never reach an agent or a session. Hidden and missing targets get the
  same answer.
- Grants for handed tabs come only from `agent.adopted`, which only Hand over and a task started in a tab change. Both
  are clicks in AI Browser's own pages. No CDP command, no report, no claim, nothing the Brain proposes and no spoken
  word can grant a tab.
- Take back cuts at once (Decision 6).

**Page and message text is data:** the relay reads only routing fields (`id`, `method`, `sessionId`, target ids,
`openerId`, `browserContextId`, URLs for the address check, download guids). It never acts on page text and never
logs it.

**Text is text:** AI Home's new list sets every name and count with `textContent`.

**Nothing leaves the machine unless the user chooses:**
- The relay listens on 127.0.0.1 only, on the app's existing port.
- Tokens stay in memory and in the 0600 files that already hold them (on Windows, the per-user folder permissions of
  the Windows spec).
- No token goes in a URL, a broadcast, the snapshot or a log line.
- No CDP connection goes through a proxy (`proxy=None`, Messages / interfaces), so a token in a header never passes a
  proxy the system or the environment names. This matters most on Windows, where a system proxy's `<local>` rule
  doesn't cover `127.0.0.1`.
- The list of connected clients stays in AI Home.

**Downloads need the user's OK:** the relay refuses `Browser.setDownloadBehavior` and `Page.setDownloadBehavior`, so no
client can move or silence the user's downloads. `Browser.cancelDownload` works only for the client's own downloads,
so the engine's cancel of an unconfirmed download (everyday-brave Decision 15) still works.

**The standing grant, said plainly:** one Allow now covers every holder of a relay token until the app quits. Any
program running as the user that can read `mcp.json` or link.json can drive Brave without a new question, though only
in tabs it opens, and without cookie calls. The mitigations:
- tokens change every run;
- the relay enforces tab ownership and the command list;
- a web page can't reach the relay (Origin, Host, header-only token);
- AI Home lists every client, with Disconnect;
- the switch text, the setup page and the README say all this.

**The Brain only proposes:** nothing in this spec lets the Brain, voice or a page open the upstream, grant a tab or
disconnect a client. The relay opens the upstream only for the app's start, a click, an agent's turn or a session's
call. A turn starts only from the user's own act: a task, a message, a click, a Brain card confirmed with Start, Send or
a plain yes, or a workflow the user scheduled.

## Testing

Tests never reach the user's real browsers:
- the autouse fixture `_never_the_users_browsers` (`tests/conftest.py:53-60`) stays;
- the "Brave" is either a fake debugging port, which counts handshakes the way Brave would count questions, or a
  throwaway headless Chrome started with `--remote-debugging-port=0`, which never asks.

Each test below fails before this wave, because the module, route, field or behaviour doesn't exist yet, and passes
after.

**On Windows:**
- the unit and server tests (`tests/test_cdprelay.py`, `tests/test_app_server.py`, `tests/test_app_run.py`,
  `tests/test_engine.py`, `tests/test_grouping.py`, `tests/test_bridge.py`) run there;
- so do the throwaway-Chrome tests in `tests/test_cdprelay_chrome.py` and the `["direct", "relay"]` fixtures, whenever
  Chrome is installed: their Chrome is started with `--remote-debugging-port=0`, not over the DevTools pipe;
- tests on the `watcher` or `home` fixtures (test 45, and tests 46-47 until wave 3 rebuilds `stack`) skip there, with
  the other pipe-fixture tests (`tests/conftest.py:26-35`);
- test 32's proxy case is the one that matters most there (`cdp.py`'s `proxy=None`, Messages / interfaces). File-mode
  checks (tests 29 and 39) assert only where modes apply, as `file_mode` does today.

### Helpers

- **`tests/fake_brave.py`:**
  - gains `FakePort`, moved from `tests/test_bravelink.py:16-68`, with `sessions` still counting handshakes;
  - `FakeBrave.connect(why="connect", identity="")` records each call's `why` and identity;
  - it now also answers `Target.createTarget`, flattened `Target.attachToTarget` (it sends `Target.attachedToTarget`
    and one session event before the answer), `detachFromTarget` (with `Target.detachedFromTarget`), `closeTarget`,
    `getTargets` and `getTargetInfo`, and emits `targetCreated` with an `openerId` on request;
  - it records every method it receives, with its `sessionId`.
- **`FakeRelay`**, in `tests/fake_brave.py`, for `FakeBrave`: `grants`, `own_targets`, `cut`, `forget`, `disconnect`
  and `clients`, all recorded. A test calls `own(identity, target)` to declare a grant.
- **`relay_client(server_or_relay, token, origin=None, host=None)`:** opens `/cdp` with `websockets`. A raw-socket
  variant sends a handshake with any `Host`.

### Unit: `tests/test_cdprelay.py` (a `FakePort`, an in-test Starlette app or `AppServer` with a relay)

1. `test_one_upstream_for_the_app_two_agents_and_a_session`: the app's local client, agents a1 and a2, and session
   `cc-x` all send commands. `port.sessions == 1` and `relay.upstream_opens == 1`.
2. `test_ids_are_remapped_per_client`: a1 and a2 both send id 1 at once. Each gets its own answer, and the upstream saw
   two different ids.
3. `test_attach_events_before_the_answer_reach_only_the_attacher`: the fake sends `attachedToTarget` and a session
   event before the attach answer. a1 receives both, then the answer. a2 receives nothing.
4. `test_two_clients_on_one_tab_get_two_sessions`: the app and a1 attach to a1's tab. Each gets only its own
   session's events.
5. `test_the_users_tabs_are_invisible_to_agents`:
   - the fake lists a user page titled `SECRET-7f3a`;
   - a1's `getTargets` answer, its discovery events and every frame it receives never contain it;
   - a1's `attachToTarget`, `activateTarget` and `getTargetInfo` on it answer `-32602` "No target with given id found",
     and the fake never received them;
   - the app's local client sees it, and its `Target.getBrowserContexts` passes; a1's is refused.
6. `test_a_handed_tab_is_visible_and_take_back_cuts_at_once`:
   - a1 attaches to a target listed in `handed("a1")`;
   - `cut("a1", target)`, then `handed` drops it;
   - a1's next command on that session answers `-32001` without reaching the fake;
   - the fake got `Target.detachFromTarget`, and a1 got `Target.detachedFromTarget`;
   - a new attach is refused.
7. `test_refused_commands_never_reach_the_browser`, parametrized, at the right level:
   - browser level: `Browser.close`, `Browser.crash`, `Browser.setDownloadBehavior`, `Browser.grantPermissions`,
     `Browser.setPermission`, `Storage.getCookies`, `Target.setAutoAttach`, `Target.attachToBrowserTarget`,
     `Target.createBrowserContext`, `Target.exposeDevToolsProtocol`, `SystemInfo.getInfo`;
   - session level: `Network.getAllCookies`, `Network.getCookies`, `Network.setUserAgentOverride`,
     `Emulation.setUserAgentOverride`, `Emulation.setAutomationOverride`, `Page.setDownloadBehavior`,
     `Fetch.enable`, `Autofill.trigger`;
   - each answers `-32601`, and the fake's record lacks it.
8. `test_create_target_forces_background_and_checks_the_address`:
   - refused: `file:///etc/passwd`, `chrome://settings`, `brave://settings`, `javascript:alert(1)`,
     `http://127.0.0.1:<app port>/setup`, the same page as `http://localhost:<app port>/`,
     `http://2130706433:<app port>/`, `http://0x7f.1:<app port>/`, `http://[::1]:<app port>/` and
     `http://app.localhost:<app port>/`, `hidden: true`, and a `browserContextId` not among a1's own;
   - allowed: `about:blank#aib-0123456789abcdef`, `https://example.com` and `http://localhost:<another port>/`,
     forwarded with `background: true` even when the client sent `false`;
   - `Page.navigate` to `file:///etc/passwd`, and `Network.loadNetworkResource` of `http://127.0.0.1:<app port>/setup`,
     on an own session are refused.
9. `test_close_target_only_own`: a1 closes its own tab. Closing a handed tab answers "can be let go of, never closed".
   Closing a2's tab answers "No target …".
10. `test_cancel_download_only_for_seen_guids`: after the fake sends `Page.downloadWillBegin` with guid `G1` on a1's
    session, a1's `Browser.cancelDownload {guid: G1}` passes. `G2`, and `G1` from a2, are refused.
11. `test_popups_are_visible_and_become_own_when_attached`: `targetCreated` with `openerId` = a1's tab is sent to a1,
    not to a2. `grants("a1", popup)` is false until a1 attaches, then true. `on_grant` fires once.
12. `test_discovery_is_per_client`: a1's `setDiscoverTargets` never reaches the fake (it was sent once, at connect).
    a1 gets `targetCreated` for its own tab only, then `{}`.
13. `test_a_client_that_leaves_has_its_sessions_detached`: a1's socket closes. The fake gets `detachFromTarget` for
    a1's session, the upstream stays open, and a1 reconnecting with the same token still drives its own tab.
14. `test_an_upstream_drop_fails_pending_and_closes_clients`: the fake closes with a command pending. The command fails
    with "browser connection lost", clients get `detachedFromTarget`, then close code 4410, and the state is `lost`.
15. `test_a_slow_client_is_cut_not_the_upstream`: a client stops reading while the fake floods 70 MB of events for its
    session. That client closes with 4408, and a1 keeps getting answers in under a second.
16. `test_one_shared_attempt_and_deny_is_not_retried`:
    - with `FakePort(answer="silent")`, three clients connect while `asking`. One handshake reaches the fake. On
      release, all three are accepted;
    - with `answer="refuse"`: the state is `refused`, and all three get 409 with the "Try again" text;
    - a fourth client connect gets 409 and `port.sessions` stays 1;
    - `open("connect")` makes `port.sessions == 2`;
    - the `AppServer`'s uvicorn config names `ws="websockets-sansio"`, the implementation that lets a handshake wait
      past 10 s (Decision 8).
17. `test_open_follows_the_table`: every row and column of Decision 10's table, with `may_open` stubbed. No `open`
    happens from `off` (`find_ws_url` fails), no `client` open happens from `refused`, and a cut-off identity's
    `open("turn", "a1")` starts nothing.
18. `test_every_method_the_engine_sends_passes_the_policy`: reads `browser.py`, `live.py`, `engine.py`, `checks.py`,
    `grouping.py`, `qa/*.py` and `app/tabs.py`, and collects every `"Domain.method"` passed to `send(`, `_call(` or
    `_send(`. Each passes `allowed()` at its level (browser level for `Target.*` and `Browser.*`, else session):
    `app/tabs.py`'s with `app=True`, the engine's without. The one exception is `Browser.setDownloadBehavior`
    (`browser.py:377-379`, sandbox mode only), named in the test with that reason. This is the drift guard.
19. `test_handshake_refusals`:
    - each answers 403 and opens no client: an `Origin: https://evil.example` header, an `Origin: null` header,
      `Host: localhost:<port>`, `Host: attacker.example:<port>` (raw socket), no token, a wrong token, and a right
      token only in `?token=`;
    - a cut-off identity gets 410.
20. `test_the_relay_logs_no_page_text`: with `caplog`, a refused `Runtime.evaluate` carrying `SECRET-7f3a` and a page
    titled `SECRET-7f3a` leave no log line containing it.

### Server: `tests/test_app_server.py`

21. `test_each_agent_has_its_own_token`:
    - two agents get different env tokens;
    - a1's token posts `/agent-events` and `/agent-claim` for a1, and gets 403 for a2;
    - `server.token` and the session token get 403 for agent ids. (Replaces `test_agent_events_need_the_agent_token`
      at `:94-107`, which uses `server.agent_token`.)
22. `test_hello_returns_a_cdp_token_only_with_a_relay`: in brave mode `/agent-hello` answers `{"cdp_token"}`, the same
    one twice. After `browser_disconnect` it answers 410, and the session isn't listed again. In app mode it answers
    204.
23. `test_no_token_reaches_a_page`: the JSON of the snapshot, `sessions`, `browser_clients` and every broadcast
    during a hello, a report and a Disconnect contains no agent, session or relay token.
24. `test_a_report_about_a_tab_the_relay_doesnt_grant_is_dropped`: with `FakeRelay` granting nothing, a1's
    `tab_opened` report sets no owner chip and adds nothing to `agent.tabs`. With the grant, it does. A report saying
    `"adopted": true` about an own tab adds nothing to `agent.adopted`, and one saying `"adopted": false` about a
    handed tab adds nothing to `agent.tabs`. (Replaces the late-report test at `:822`, which tests `_hands_a_tab`.)
25. `test_take_back_cuts_in_the_relay`: `take_back` from AI Home's origin calls `relay.cut("a1", target)` before the
    server reads the next message.
26. `test_browser_disconnect_only_from_our_pages`: from the watcher's origin it does nothing, and a watcher socket
    never receives `browser_clients` (new rows in wave 1B's two table tests). From AI Home it calls
    `relay.disconnect` and broadcasts `browser_clients`.
27. `test_closing_an_agent_closes_the_tabs_the_relay_says_it_owns`: a tab granted in `FakeRelay` but never reported
    is in `FakeBrave.closed` after `close`.
28. `test_a_sessions_tabs_are_closed_by_bye_and_by_the_sweep`: `/agent-bye` runs `relay.forget` with
    `close_tabs=True`; so does the sweep, set to 0.1 s, for a dead pid.

### App run: `tests/test_app_run.py`

29. `test_brave_mode_wires_the_relay`:
    - `agents.env` has `AIB_APP_CDP == ws://127.0.0.1:<port>/cdp` and no `AIB_APP_AGENT_TOKEN`;
    - each created agent's env has its own token;
    - link.json has `cdp` and `browser_dir`, mode 0600 (`file_mode`, `tests/conftest.py:47-50`).
30. `test_the_switch_text_says_once_per_run`: `SWITCH` contains "asks once each time AI Browser starts" and "it isn't
    AI Browser", and no longer contains "each agent first uses the browser".
31. `test_agents_end_before_the_relay_closes`: a stub order recorder shows `server.stop` before `brave.close`.

### Engine: `tests/test_engine.py`, `tests/test_grouping.py`, `tests/test_bridge.py`, `tests/test_cdprelay.py`

32. `test_cdp_connect_sends_the_header_and_no_origin_and_uses_no_proxy` (`test_cdprelay.py`, because `test_cdp.py`
    needs Docker): against a tiny `websockets` server recording request headers. It runs with `HTTP_PROXY` and
    `HTTPS_PROXY` set to `http://127.0.0.1:9` (nothing listens there) and `NO_PROXY`/`no_proxy` removed. Before,
    `websockets` sends the handshake to that proxy and the connect fails; after, it reaches the server.
33. `test_an_app_agent_always_uses_the_relay`: with `AIB_APP_AGENT` and `AIB_APP_CDP` set, the engine connects to
    `AIB_APP_CDP` with its token. `find_ws_url` and a direct connect are patched to fail the test. A 409 from the relay
    becomes the relay's text, and nothing else is tried.
34. `test_a_session_goes_through_a_running_app`: with a live link.json, the session says hello, connects with the
    `cdp_token`, and its status says "through AI Browser's connection". `_close_orphans` isn't called.
35. `test_a_session_never_falls_back_while_the_app_is_up`: the relay answers 409; then the hello gets no answer
    (`APP_SILENT`); then the hello answers 410 (`CUT_OFF_SESSION`). Each becomes its error text. A direct connect is
    patched to fail the test.
36. `test_a_session_whose_app_stopped_asks_first`:
    - after a relay connection, link.json goes away and the socket closes;
    - the next `open` answers `APP_GONE` and connects nowhere;
    - after `sandbox_start(chrome=true)` it connects directly to the throwaway folder.
37. `test_aib_chrome_dir_naming_another_browser_goes_direct`: link.json's `browser_dir` differs from `AIB_CHROME_DIR`.
    The engine connects directly, and the status names it.
38. `test_discover_reads_a_local_cdp_only` (`test_grouping.py`): it rejects `ws://127.0.0.1:80@evil/cdp`,
    `wss://127.0.0.1:1/cdp`, `ws://localhost:1/cdp`, `ws://127.0.0.1:1/other` and `ws://127.0.0.1:1/cdp?x=1`.
39. `test_an_agents_mcp_json_holds_its_own_token_and_the_relay` (`test_bridge.py`): mode 0600 where modes apply.

### Through the relay, in a throwaway Chrome: `tests/test_cdprelay_chrome.py`, and fixtures

- **`own_browser`** (`tests/test_chrome.py:319-342`) and **`chrome_browser`** (`tests/conftest.py:86-104`) are
  parametrized `["direct", "relay"]` for `test_chrome.py`, `test_checks_browser.py` and `test_isolation.py`:
  - in `relay` mode a `Relay` sits on the throwaway Chrome, served by an `AppServer` in brave mode, and the `Browser`
    connects with a minted token;
  - the test's own CDP connection stays direct, so a test can still point downloads at a temp folder
    (`tests/test_chrome.py:737-738`), a command the relay refuses;
  - so the own-mode browser tests, the download guard included (`tests/test_chrome.py:732-757`), also run through
    the relay. `test_qa_browser.py` stays direct, except test 44.
  - three tests stay direct only, with a `direct_only` mark the fixtures read, because they test the `Browser` on
    its own and lean on one shared connection:
    - `test_chrome_mode_leaves_the_users_tabs_alone` (`tests/test_chrome.py:185-195`) reads the user's tabs through
      the `Browser`'s own connection, which the relay rightly hides. Test 5 and test 40 cover the relay's side;
    - `test_a_handed_tab_is_listed_taken_on_and_given_back` (`:624-669`) and
      `test_a_tab_the_agent_opens_from_a_handed_tab_is_its_own_and_take_back_ends_the_handed_one` (`:674`) hand tabs
      through a test callable the relay can't see, and the first spies on the test's own connection
      (`:648-655`). Test 6 and test 41 cover handing over and Take back through the relay.
- **The `watcher` fixture** (`tests/test_watcher.py:56-95`) attaches a `BraveLink` on its throwaway profile and
  connects it, so the relay is `connected` before any engine connects (Decision 10: accepted outside a turn too).
  `agent_engine` (`tests/test_watcher_groups.py:57-64`) sets `AIB_APP_CDP` and `server.token_for(agent)` in place of
  `server.agent_token`. So the grouping tests run through the relay.

40. `test_two_engines_one_upstream_and_only_their_own_tabs`:
    - two engines as a1 and a2 open pages;
    - `relay.upstream_opens == 1`;
    - each engine's `tabs list` shows only its own tab;
    - a user tab titled `SECRET-7f3a` appears in no tool result, no task-log line and no frame in a CDP spy on either
      engine.
41. `test_take_back_through_the_relay`:
    - `agentlink.HANDED_TTL` is patched to 60 s, so the engine's status cache still says "handed" after Take back.
      Only the relay's cut can tell the engine;
    - hand a user tab to a1; `tabs switch h1` and `observe` work;
    - `take_back`; a1's next `observe` starts "(the user took back tab t…)";
    - the tab is still open.
42. `test_a_new_engine_or_a_dropped_socket_keeps_one_upstream`:
    - **New chat:** a1's engine closes, and a new engine with the same token connects. `relay.upstream_opens` is
      still 1. a1's earlier tab is still a1's in `relay.own_targets("a1")`, so closing a1 closes it;
    - **A dropped socket:** the relay closes a1's socket (as it does for 4408). a1's next call takes the reconnect
      path (`engine.py:383-391`), says "(reconnected to your …)", and its stale tab is closed through the relay
      (`:388-390`). `relay.upstream_opens` is still 1.
43. `test_live_view_and_thumbnails_through_the_relay`: the live view streams frames of a1's tab, and the app's
    thumbnail of the same tab is a JPEG at the same time.
44. `test_website_qa_through_the_relay`: one `run_qa` on the `qa/` test site with a relayed `Browser` finds the same
    issues as the direct run. Its link checks (`Network.loadNetworkResource`, `IO.read`) and its download cancels pass
    the relay.
45. `test_a_popup_from_a_step_joins_the_agent_through_the_relay`: in the grouping test, the popup becomes a1's own in
    the relay and gets the owner chip "Fix the footer".

### AI Home: `tests/test_home.py` (the `home` fixture, built on `stack`)

46. `test_ai_home_lists_connected_clients_with_disconnect`:
    - a `browser_clients` message draws "AI Browser" with no button, "3 · Fix the footer · 2 tabs" and "Claude Code ·
      1 tab";
    - Disconnect sends `browser_disconnect`;
    - a hostile name stays text.
47. `test_the_browser_card_says_one_question`: the `ready` and `asking` notes have the new words.

### Texts

48. `test_setup_page_says_once_per_run` (`test_app_server.py`): `/setup` contains "asks once each time AI Browser
    starts", the standing-grant sentence and the bar sentence. It no longer contains "again when each agent first uses
    the browser".

### Hand check, by the user, in their own Brave, after this wave

Nobody has counted these in a real Brave yet. They rest on Chromium's source and a headless probe. The user checks:
1. With the switch ticked, start `ai-browser app`. Brave asks once: click Allow.
2. Give two tasks. Count: Brave asks no more. AI Home lists AI Browser and the two agents.
3. Close the "controlled by automated test software" bar. Start a third task, and press New chat on one agent. The bar
   stays closed and nothing asks.
4. With the app running, ask a Claude Code session to open a page. Nothing asks; its tab joins the "Claude Code"
   group; AI Home lists it.
5. Hand a tab to an agent, then take it back. The agent's next step says it lost the tab.
6. Disconnect the session in AI Home. Its next browser call says so, and Brave doesn't ask.
7. Quit Brave and start it again. AI Home says closed. Give an agent a message: Brave asks once, click Allow, and the
   agent carries on.
8. Restart Brave once more, click Connect in AI Home, and click Deny. Nothing asks again until Try again or a new
   task.
9. Quit the app. The Claude Code session's next browser call says AI Browser stopped, and Brave doesn't ask.

On the Windows laptop, if Brave or Chrome is installed there with its switch on, the user repeats steps 1, 2, 4 and
9 in that browser. This checks the relay and the session's route on Windows, including a system proxy.

The user notes how many times Brave asked in steps 1-4 and whether the bar came back in step 3. If either differs
from this spec, the texts are corrected before wave 3 starts. If the bar or the question count turns out to be
per-tab, a follow-up spec says so plainly; nothing tries to hide either.

**Not tested as a goal:** `navigator.webdriver`, or whether a site shows a challenge.

## Out of scope

- **A standalone `ai-browser relay`** that holds Brave's connection for bare Claude Code sessions without the app, and
  closes it after about 10 idle minutes. A later step.
- **Dropping the connection when idle:** the user chose to hold it for the whole run.
- **Pinning tabs to a profile:** wave 4. The relay records each own tab's `browserContextId`. Wave 4 adds
  `Relay.assign(target, identity)` for tabs the watcher opens in the chosen profile.
- **One connection per browser** when the user switches browsers: wave 4. The `Relay` is per folder, so wave 4 can
  hold one upstream per browser and bind each client to its own.
- **The app window, its cookie and Host checks on every route:** wave 3. This spec adds the Host check to `/cdp` only.
- **Relaying other tools** (chrome-devtools-mcp, Playwright). They keep their own connections, and the texts say so.
- **Relaying AI Browser's own Chrome** (`--browser app`): it never asks, and wave 3 retires it.
- **Iframe and worker sessions** (`Target.setAutoAttach`): refused until the engine needs them. A child session event,
  should one ever come, goes to its parent's client.
- **Checking upload paths in the relay** (`DOM.setFileInputFiles`): the engine already uploads only copies from the
  work folder (`browser.py:1283-1293`).
- **A wall against programs running as the user:** the relay narrows what a token can do and AI Home shows who holds
  one. A program that can read the user's files can still join, as it can today.
- **Remembering Allow across connections, or touching the bar:** never. Chromium closed the request to persist
  approval as not planned (ChromeDevTools/chrome-devtools-mcp#825), and this project never answers the prompt or hides
  the bar.
