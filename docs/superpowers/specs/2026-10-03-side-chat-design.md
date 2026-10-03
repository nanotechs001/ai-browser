# The chat beside your page, in the watcher

Date: 2026-10-03.

## Status

Status: the user approved the design in chat and answered its four questions; this spec was written and reviewed by agents without a user review round.

- **Part of:** "The app as an app" (`2026-10-03-app-as-an-app-overview.md`, section 5). This is wave 5, the last.
- **Evidence:** the investigation's findings (`2026-10-03-app-as-an-app-investigation.json`, section `sidechat`), and
  the code at HEAD, cited as file:line.

**The user's choices**, from chat on 2026-10-03:
- "Side chat into the watcher extension" (brief section 5);
- "App window, no browser look": AI Home, Mission Control and the Brain move into an app window with no tabs (wave 3),
  so the chat beside the page can no longer live in AI Browser's own Chrome;
- agents use the Brave profile picked in Settings, with the watcher loaded there (wave 4);
- the defaults in the brief, which the user accepted: the side chat offers only **Allow once** and **Deny**, and
  **Always allow** stays in the app's Tools.

**Questions the investigation left open, settled by the brief:**
- Enter on one of your own tabs never starts an agent there: you choose **Start here** or **Start in its own tabs**.
- The side chat talks to agents through a **To:** picker. It doesn't talk to the Brain.
- The chat in Chrome comes later (Out of scope).

**One open question the brief doesn't answer, decided here:** handing over a tab of a site the Brain watches (Gmail,
Slack, Asana) gets no extra confirm step. The hand-over is already a separate click that names the site, and it carries
the same line as AI Home's Hand over: "The agent will read this tab and act in it." (The investigation's open question
5.)

**Builds on** the merged earlier waves. This is wave 5, and it goes last because it needs all of them:
- **everyday-brave** (2026-10-02): `BraveLink`, `GroupKeeper`, `hand_tab` and `take_back`, the watcher's tab groups;
- **brain-delegation** (wave 1A, `2026-10-03-brain-delegation-design.md`):
  - `Agent.number` and `Agent.queued` on every agent row;
  - the label helper `agentLabel(agent)` in `chat.js`, which gives "2 · Fix the footer";
  - `AgentManager.send` returning `False` for a closed agent;
  - the Brain's fixed lines `HAND_OVER_SAY` and `HAND_OVER_ANY_SAY`, and the hand-over sentence in `BRAVE_PROMPT`;
- **watcher-safety** (wave 1B, `2026-10-03-watcher-safety-design.md`):
  - `MESSAGE_RULES` and `may_send(role, message)`, checked first in `_handle`, with `_role(ws)` giving "app" or
    "watcher";
  - a refused message is dropped with no answer;
  - `WATCHER_RECEIVES`, `for_watcher(message)` and `WATCHER_AGENT_FIELDS`: what watcher sockets may get, and no target
    id in any of it;
  - `check_show {id}`: the watcher's **Show me**, by agent id;
  - `permissionCard(..., { always: false })`, with the line "Always allow is in AI Home's Tools.";
  - the table tests in `tests/test_watcher_rules.py`;
- **cdp-relay** (wave 2A, `2026-10-03-cdp-relay-design.md`):
  - the app holds the only connection to Brave, and the relay enforces which tabs each agent may use;
  - Take back cuts the agent off at once (`relay.cut`, its Decision 6);
  - reconnecting happens only right after a user action, as one shared attempt (`Relay.open(why)`, its Decision 10).
    A click in the chat uses the `connect` row, as AI Home's Connect does. An agent's turn uses the `turn` row;
  - the consent texts of its Decision 15, which say when to click Allow;
  - the app's own client is in-process and privileged, and may send `Browser.getWindowForTarget` for any target (its
    Decision 9, which names this spec as the user);
- **app-window** (wave 3, `2026-10-03-app-window-design.md`):
  - the pages move to `app/ui/`, and `brain/watcher.py`'s `SHARED_SOURCE` becomes `app/ui/`;
  - only `app/extension/panel.html`, `panel.js` and `panel.css` stay behind, unserved, as the source this spec ports;
  - `link.js` keeps its extension path for the watcher, and loses `targetOfTab` and `tabOfTarget`;
  - `check.js` opens a live view with its own `openLive(url)`. Wave 3 keeps it there, not in `ui/nav.js`, so that no
    file shared with the watcher imports `nav.js` (its Decision 7, and its static test);
  - the `hello` views shrink to `home`, `mission`, `settings`, `watcher` and `brain`. This spec brings back `panel`,
    for the watcher's chat only;
  - the watcher's manifest gains `omnibox` and the version 0.2.0, and the server gains `ai_keyword` and
    `keyword_started`;
  - `setup.html` moves to `app/ui/setup.html`, with `ui/setup.js` and `ui/setup.css`;
  - `tests/test_panel.py` is skipped at module level, kept as the reference for this spec;
  - the model setting lives on the server (`settings.model ?? default_model`);
- **browser-profile-choice** (wave 4, `2026-10-03-browser-profile-choice-design.md`):
  - `Place` (browser and profile), the Settings choice, and `Agent.place`, fixed when the agent starts. Its Decision 3
    lets an agent started in a handed tab take that tab's place, which this spec's Start here relies on;
  - one watcher copy per profile, each with its own folder and origin, and `place_of(origin)`. A copy can also be made
    for a Chrome profile (its Decision 7), and every copy carries the same files, this chat included;
  - `Watchers` and `WatcherConn`, with one `GroupKeeper` per copy's connection, and `Watchers.connections()` for
    `tab_owners`;
  - `InstanceLink` (today's `BraveLink`, one per browser), with `targets_showing(url)` and `context_of(target)`, and
    `InstanceLinks.link_for(place)`;
  - the watcher's `open_tab`.

**Names.** Where the merged code names a piece differently from the specs above, the planner uses the code's name.
What matters is the behaviour.

**What this spec replaces:**
- **everyday-brave Decision 3**, "Rejected for now: moving these pages into the watcher"
  (`2026-10-02-everyday-brave-design.md:305-306`), for the chat panel. **Decision 5** (no `debugger` permission in the
  watcher, `:353-356`) stands, and this spec keeps it.
- **everyday-brave's** "The chat panel in AI Browser shows the agent that was active last" (`:157-158`).
- **The watcher's promise**, "It never sends anything", in five places (Decision 15).

## Goal and success criteria

The chat beside your page moves into the watcher and uses Brave's side panel. There you can:
- talk to an existing agent: pick it in **To:**, type, and press Enter;
- start a new agent, either in your tab or in tabs of its own;
- hand an agent your tab, or take it back, with a click;
- answer an agent's permission or bot-check card.

It adds no `debugger` permission, no host permission and no connection to Brave of its own. Its only line is the app's
127.0.0.1 socket.

Success means:
1. **Opening:**
   - the watcher's toolbar icon, or ⌘⇧Y (Ctrl+Shift+Y on Windows), opens the chat beside the page in that window;
   - each normal window has its own chat;
   - nothing opens the chat for a popup window, and no code path calls `chrome.sidePanel.open` for a window whose type
     isn't `normal`.
2. **The strip:**
   - a line at the top says whose the tab beside the chat is: yours, handed to an agent, an agent's, Claude Code's, or a
     browser page;
   - it follows only that window's active tab, and changes within a second of a tab switch.
3. **Talking to an existing agent:**
   - **To:** lists the open agents, newest first, then **New agent**;
   - with an agent picked, Enter sends `send {id, text}`;
   - no new agent starts, and nothing passes through the Brain.
4. **Starting:**
   - on your own tab with **New agent** picked, Enter starts nothing until you click **Start here · <site>** or
     **Start in its own tabs**;
   - **Start here** hands that tab to the new agent;
   - **Start in its own tabs** hands nothing.
5. **Hand over and Take back:**
   - each is a separate button, and only a trusted click works it;
   - typing never hands a tab over;
   - for Start here and Hand over, the server finds the tab by its address and its window. When two tabs in that window
     show the address, or none does, it refuses and never guesses;
   - for Take back, the server takes back only a tab it recorded as handed, by its tab id. Take back never connects to
     Brave.
6. **Cards:**
   - a permission card offers **Allow once** and **Deny**, and the server drops `always` from the watcher (as
     watcher-safety already does);
   - a bot-check card offers **Show me** and **Continue**, with no **Skip this site**.
7. **No page data:**
   - the chat never sends the tab's address or title to an agent;
   - the server drops `tab` from every `new_task` and `send` that comes from a watcher origin;
   - the tab's address goes to the local server only on a Start here, Hand over or Take back click, so the server can
     find the tab. The server never logs it.
8. **The rules:** the watcher's allowed-message table gains the new messages and conditions. Its table test covers every
   message type for both origins.
9. **The promise:** the new wording is in all five places, and the chat and the Brain page show it once.
10. **Retired:**
    - AI Browser's `panel.*`;
    - `tests/test_panel.py`, with no test file importing it;
    - no `chrome.debugger` anywhere in the watcher's folder (wave 3 removed `link.js`'s helpers; test 21 keeps it so).
11. **Brave's question:**
    - from the chat, Brave's "Allow remote debugging?" appears only when the app isn't connected, and only right after
      the user's own click or Enter: a Start here or Hand over click, or a Tell or Start that begins an agent's turn
      (wave 2A's `turn` rule, as for a task or message from AI Home);
    - opening the chat, switching tabs and Take back never make Brave ask;
    - the texts that say when to click Allow name the chat's Start here and Hand over;
    - nothing answers, hides or closes that question, or the automation bar.

## What the user sees

### Once: pin the icon

Brave has no sidebar entry for extension panels (brave/brave-browser#31334), so the chat opens from the watcher's
toolbar icon or the shortcut. The setup page's watcher step 3 (setup.html:70 today, `app/ui/setup.html` after wave 3)
becomes:

> Pin the watcher's icon: click the puzzle piece in Brave's toolbar, then the pin next to AI Browser Watcher. Click the
> icon, or press ⌘⇧Y, to open the chat beside your page. Its **Inbox** button opens the Brain, where you switch on the
> sites to watch.

The terminal's watcher steps and the README say the same.

**The shortcut's name follows the system** everywhere it is written: ⌘⇧Y on a Mac, Ctrl+Shift+Y on Windows and Linux.
The setup page and the terminal pick it with `platforms.shortcut` (as `run.py:49` does today; the setup page through
a `{{SHORTCUT}}` placeholder). The README and AI Home
write "⌘⇧Y, or Ctrl+Shift+Y on Windows".

The watcher updates itself (worker.js:86-92). Its one new permission, `sidePanel`, shows no warning. That is why the
chat and the Brain page both show the new promise once (Decision 15).

### Opening the chat

- **The icon or ⌘⇧Y** opens the chat beside the page in that window. Pressing it again closes the chat.
- **One chat per window.** Each normal window gets its own chat, and each one follows its own window.
- **Popup windows**, such as a site's sign-in popup, get no chat. Nothing happens there.
- **From the Brain page:** a **Chat** button in its header opens the chat beside that window.
- **Notifications** work as today. **Review** on a permission notification still opens the Brain page.

### The layout, top to bottom

1. **The header:** a connection dot, "AI Browser", the model menu (Sonnet, Opus, Haiku), and **Inbox**, which opens the
   Brain page.
2. **The strip:** whose tab this is, plus **Take back** when the tab is handed to an agent.
3. **The first-run line.** It shows once, until **Got it**:

   > This chat never presses Send for you. An agent works in one of your tabs only after you click Start here or Hand
   > over, and it asks you before any ⚠ step like Send, Buy or Delete.
4. **The conversation** of the agent picked in **To:**. With **New agent** picked, a short note shows instead. The old
   panel's Page view (`panel.html:33-36`, the page Claude read last) isn't ported.
5. **The waiting line**, when another agent needs you: "3 · Flights to Manila is waiting for you", or "3 · Flights to
   Manila and 1 more are waiting for you". Its **Show** button switches **To:** to that agent. It never answers
   anything.
6. **Cards** for the picked agent: a bot check, then a permission.
7. **The composer:**
   - **To:** the open agents, newest first, each as "2 · Fix the footer · working", then **New agent**;
   - the text box;
   - a hint line;
   - the buttons for the current mode (below).

The layout works from 320 px, the side panel's narrowest width: the buttons wrap onto a second row when they need to.
Brave's own sidebar may show beside the chat (brave/brave-browser#51271); that is Brave's.

### The strip

The strip shows the site's host, never the page title:

| The tab beside the chat | The strip |
|---|---|
| a web page nobody else uses | This tab: mail.google.com · yours |
| a thread the Brain opened | This tab: mail.google.com · yours |
| handed to an agent | This tab: mail.google.com · handed to 2 · Fix the footer **[Take back]** |
| an agent's own tab | This tab: shop.example · 2 · Fix the footer's tab |
| a Claude Code session's tab | This tab: shop.example · Claude Code's tab |
| not http or https (brave://, the new tab page, a file) | This tab: a browser page |

A second, muted line appears when agents can't use this tab. `<browser>`, `<inspect>` and `<place>` come from
`panel_place`: the agents' browser's name, its switch page (wave 4's `browsers` row, for example
brave://inspect/#remote-debugging) and the agents' place ("Brave · Personal").
- **The switch is off:** "Agents can't use your tabs until `<browser>`'s switch is on (`<inspect>`)."
- **The app has no browser link** (`no_link`): "AI Browser isn't linked to a browser yet, so agents can't use your
  tabs." Since wave 3 the app's agents always browse in the user's browser, never in the Docker sandbox (app-window,
  Decision 12), so this shows only for a server started without a link, as in tests.
- **Agents browse in another browser:** "Agents work in `<browser>`: change it in AI Browser's Settings to work in this
  tab."
- **This watcher copy isn't matched to one profile yet:** "This copy of the watcher isn't matched to one profile yet:
  see Where agents browse in AI Browser's Settings." (wave 4's "unknown" and "shared" copies)
- **The chat is in another profile than the one agents use:** "Agents work in `<place>`: switch to this profile in AI
  Home to work in its tabs."

### Talking to an agent

- **Pick it** in **To:**, type, and press Enter (or click **Tell**). The words go to that agent, as Mission Control's
  drawer composer does (mission.js:246-255).
- **A busy agent** reads your words after its current step. The chat shows them as queued (chat.js:48-49).
- **An agent waiting at a bot check** can be told things too. "skip it" is how you skip a site from here (check.js:27).
- **Shift+Enter** starts a new line.
- **Which agent To: starts on:**
  - when you switch to a tab that an agent owns or was handed, **To:** switches to that agent;
  - on any other tab, **To:** keeps your last choice, so a tab switch never drops the conversation you are in;
  - when the picked agent closes, **To:** falls back to **New agent**, and the chat says "2 · Fix the footer has
    closed".
- **Stop** (the picked agent, while it works or waits) works as today. There is no **Close**: ending an agent stays in
  the app window.

### Starting an agent

The buttons depend on the tab and on **To:**:

| **To:** | The tab beside the chat | Buttons | What Enter does |
|---|---|---|---|
| an agent | yours | **Tell**, **Hand over to 2 · Fix the footer** | Tell |
| an agent | anything else | **Tell** | Tell |
| New agent | yours | **Start here · mail.google.com**, **Start in its own tabs** | nothing (see the hint) |
| New agent | anything else | **Start** | Start, in its own tabs |

When the chat's hands are off (the strip's muted line), your own tab counts as "anything else": Start here and Hand
over don't show.

- **The hint while Enter waits:** "Choose where it works: Start here · mail.google.com, or Start in its own tabs."
- **Under the hand-over buttons:** "The agent will read this tab and act in it." This is the same line as AI Home's
  Hand over.
- **An empty text box:** **Start here**, **Start in its own tabs** and **Start** are greyed out until you type the
  task. **Hand over** needs no text.
- **Focus stays in the text box.** No code moves focus to **Start here**, **Hand over** or **Take back**, so an Enter
  meant for the text box can never press one of them.
- **After a start:**
  - **To:** switches to the new agent;
  - its first message shows in the conversation;
  - with **Start here**, the tab joins its group, as with AI Home's Hand over.
- **The button words:**
  - the composer says **Tell** and **Start**, never **Send** (Decision 14);
  - the model menu sets the new agent's model, or changes the picked agent's model.

### Handing a tab over, and taking it back

- **Hand over to <n · name>** hands the tab beside the chat to the agent picked in **To:**. The agent gets the usual
  note (agents.py:24), and the strip says "handed to 2 · Fix the footer".
- **Take back** on the strip ends the hand-over. The tab leaves the agent's group, and the agent is cut off at once
  (cdp-relay). It shows whenever the strip says "handed", in any profile, because taking a tab back only removes power.
  It never connects to Brave, so it never makes Brave ask.
- **Typing never hands a tab.** Only these buttons do, and only with a real click.
- **When the server can't find the tab**, the hint line says why, and nothing is handed (`<browser>` and `<inspect>` as
  in the strip):
  - "Two tabs in this window show this page. Close one, or hand it over from AI Home's tab list." (`ambiguous`)
  - "The page changed. Click again." (`changed`)
  - "That tab isn't yours to hand over: an agent or Claude Code works in it." (`not_yours`)
  - "That agent has closed: nothing was handed." (`closed`)
  - "`<browser>`'s switch is off: turn it on at `<inspect>`, then click again." (`off`)
  - "`<browser>` didn't allow the connection, so nothing was handed. Click again to be asked again." (`refused`)
  - "That tab isn't handed to an agent." (`not_handed`, Take back on a tab that isn't handed)
  - "That tab can't be handed over." (`bad_tab`, a tab the chat couldn't describe)
  - "Write what the agent should do." (`no_text`)
  - "2 · Fix the footer started in another browser or profile, so it can't use this tab." (`other_place`: an agent
    that started before a switch)
  - When the app has no browser link, agents browse in another browser or another profile, or the chat has no
    profile: the strip's muted line, above.
- **When the app isn't connected to the agents' browser** (after Brave restarted, say), a Start here or Hand over click
  connects it. Brave then asks "Allow remote debugging?", and the hint says: '`<browser>` is asking "Allow remote
  debugging?" because you just clicked. Allow lets AI Browser's agents use `<browser>` until AI Browser or
  `<browser>` restarts; Deny stops here.' Nothing answers that question for you.

### Cards

- **A permission request** from the picked agent:
  - the tool and its exact input, with **Allow once** and **Deny**;
  - one muted line under them: "Always allow is in AI Home's Tools." (watcher-safety's line)
- **A bot check** of the picked agent:
  - who stopped, on which site, and what kind of check, with **Show me** and **Continue**;
  - the line "To skip it, tell the agent: skip it" (check.js:27). The card has no **Skip this site** button;
  - **Show me** brings the agent's tab to the front.
- **Another agent needs you:** the waiting line's **Show** switches **To:** to it. The chat never answers a card by
  itself.

### When something is off

- **The app isn't running:**
  - the dot is grey and the composer is greyed out;
  - the chat says "AI Browser isn't running: start `ai-browser app`";
  - it connects again by itself when the app is back (link.js).
- **The switch is off, or the app has no browser link:** the strip's second line says so. Talking and cards still
  work. Start here and Hand over don't show, and **Start** starts the agent in its own tabs.

### Other profiles

- Each profile you load the watcher in has its own chat, through its own watcher copy (wave 4).
- Start here and Hand over work in the profile agents use (Settings, or AI Home's switcher). In another profile the
  chat talks to agents and answers cards, and the strip's muted line says where agents work (Decision 13).
- Switching the agents' profile in AI Home is instant and asks no Allow, so working in another profile's tabs is one
  click away.

### The Brain page

- **The header** gains **Chat**, which opens the chat beside this window (Decision 2).
- **Permission cards** show **Allow once** and **Deny** only, plus the Tools line, as watcher-safety made them.
- **The promise** shows once, in the same words as the chat's first-run line.
- **The watch list's heading** (brain.html:26) says "(only tabs you have open; it reads and drafts, and you press
  Send)".

## Decisions (with reasons)

### 1. The chat lives in the watcher's side panel, one per window

- **What:**
  - the manifest's `side_panel.default_path` is `panel.html`, a global, window-wide panel;
  - the code never sets a panel path for a single tab;
  - each normal window's open panel is its own page, and it follows its own window.
- **Why:**
  - the user chose it;
  - the app window has no tabs to sit beside (wave 3);
  - a window-wide panel keeps the conversation when you switch tabs.
- **Measured** (investigation): a throwaway Brave 1.94.121 has every `chrome.sidePanel` method. A window-wide panel
  opened by a click stayed open, and `onOpened` and `onClosed` fired with the window id.
- **Rejected:**
  - **per-tab panels:** each tab switch would reload the conversation, and open panels would multiply;
  - **keeping the chat in AI Browser's window:** that window no longer has tabs.

### 2. Only the browser opens it, and never for a popup window

- **What:**
  - **the opening:**
    - the worker calls `chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })` at its top level;
    - the manifest maps `_execute_action` to ⌘⇧Y (Mac) and Ctrl+Shift+Y (others), as extension/manifest.json:13-18
      does today;
    - so the browser itself opens the panel, in the window where the icon was clicked;
  - **the popup guard** (`sidepanel.js`, run by the worker): `guardTab(tab)` calls
    `chrome.sidePanel.setOptions({ tabId, enabled: false })` for every tab whose window type isn't `normal`. It runs:
    - on `tabs.onCreated`;
    - on `tabs.onAttached`;
    - at worker start, for every open window (`windows.getAll({ populate: true, windowTypes: ["normal", "popup",
      "panel", "app", "devtools"] })`);
  - **the one place the code opens the chat:** `openChatFor(win)`, used only by the Brain page's **Chat** button:
    - the Brain page reads its own window with `chrome.windows.get` when it loads, and again when its tab moves to
      another window (`tabs.onAttached`). It keeps `{ id, type }`;
    - on the click, `openChatFor` calls `chrome.sidePanel.open({ windowId: win.id })` only when `win.type` is
      `normal`;
    - nothing is awaited before the call, so the click's gesture holds;
  - **gone:** `chrome.action.onClicked` → `openBrain()` (worker.js:340). The Brain page moves behind the chat's
    **Inbox** button.
- **Why:**
  - Brave crashes when an extension opens a side panel for a tab in a popup window (brave/brave-browser#59256, open).
    Popup windows show no toolbar icon. The guard covers the shortcut too: with the panel off for that tab, the browser
    has no panel to show there;
  - the brief says to pin the icon, because Brave has no sidebar entry (brave/brave-browser#31334).
- **Not measured, and the fallback:** whether the icon click opens the panel in Brave 1.94 with
  `openPanelOnActionClick` (the user's hand check 1). If it doesn't:
  - the icon goes back to opening the Brain page, as today;
  - the Brain page's **Chat** button opens the panel;
  - the shortcut is dropped.

  The fallback never calls `sidePanel.open` from an icon click. A window-type check there would need an `await`, which
  can lose the click's gesture in the worker.
- **A known limit:** a tab moved out of a popup window into a normal window keeps its panel switched off. Setting it on
  again would make it a per-tab panel. It is rare, and that tab simply has no chat.

### 3. The chat follows its own window's active tab

- **What:**
  - `chrome.windows.getCurrent()` gives the chat its window id once. Measured: it works in a side panel;
  - it reads the active tab with `chrome.tabs.query({ active: true, windowId })`;
  - it re-reads on these events:
    - `tabs.onActivated`, for this window only;
    - `tabs.onUpdated` for that tab, when its address or loading status changes;
    - `tabs.onAttached`, `tabs.onDetached` and `tabs.onRemoved`, when they touch this window.
  - it keeps the tab's id, window and address. It never uses the title.
- **Why:**
  - today's panel follows `lastFocusedWindow` (panel.js:102), so with two windows it shows the wrong tab;
  - the chat already knows the tab's id, window and address through the watcher's existing `tabs` permission;
  - it never knows target ids.

### 4. The strip comes from a local map, and the server's check decides

- **What:**
  - the server sends each chat `tab_owners`, a map from the browser's tab id to its owner;
  - the map lists only agents' tabs, handed tabs and Claude Code's tabs. A Brain tab is the user's own, so it isn't
    listed;
  - it is built from the targets the browser link lists now whose owner is one of those, in the chat's own profile
    (`context_of(target)` is the context of the chat's place), each with the tab id the server recorded for it. A
    target with no recorded tab id is left out;
  - a tab missing from the map shows as "yours";
  - the server records tab ids:
    - from the watcher copies' grouping answers (`GroupKeeper.remember`, groups.py:74-75; one `GroupKeeper` per copy
      in wave 4);
    - from wave 4's `open_tab` answers;
    - from the chat's own successful matches (Decision 8);
  - when the map is wrong, the server's check refuses the click, records the tab id, and sends a new map. So the strip
    corrects itself.
- **Why:**
  - the chat can draw the strip without sending the tab's address anywhere when you switch tabs;
  - the map holds only tab ids this copy can already see through `chrome.tabs`, never target ids (watcher-safety
    Decision 6). A copy can't see another profile's tabs, so it never gets their ids;
  - building it from the targets listed now drops a record whose tab is gone. After Brave restarts, tab ids start
    again, so an old record must never label a new tab;
  - every action is checked again on the server (`_handable`, server.py:499-504), so a stale map never hands a tab
    over.

### 5. To: picks the agent; the Brain isn't in the side chat

- **What:**
  - **To:** lists the open agents, newest first, each as "<n> · <name> · <state>" (`agentLabel` from `chat.js`, then
    the state word), then **New agent**;
  - Claude Code sessions aren't listed, because they can't be messaged;
  - the conversation shown is the picked agent's (`events {id}`);
  - the default rule is `defaultTo` in `sidechat.js`:
    - the tab's owner, when the tab changed to one an agent owns or was handed;
    - otherwise the current choice;
    - **New agent** when the choice closed.
- **Why:**
  - this is the second fix for the delegation complaint: picking the agent is a click, not the Brain's guess;
  - the watcher may not talk with the Brain (`brain_ask`, `brain_confirm` and `brain_dismiss` are refused from its
    origin);
  - a side panel can't show the mic prompt (voice spec, Out of scope).
- **State words:**
  - `working` → "working";
  - `waiting` → "in line";
  - `your_turn` → "your turn";
  - `needs_you` → "needs you";
  - `stopped` → "stopped";
  - `failed` → "failed".

### 6. Starting in your tab is a hand-over, so Enter waits for a click

- **What:**
  - on a tab that is yours, with **New agent** picked and the chat's hands on (Decision 13), the mode is `choose`;
  - in that mode Enter only shows the hint, and the two buttons decide:
    - **Start here** sends `start_here`;
    - **Start in its own tabs** sends `new_task` with no `adopt` and no `tab`;
  - with **New agent** on any other tab, the mode is `start`: one **Start** button, and Enter starts the agent in its
    own tabs, because there is nothing to hand over.
- **Why:**
  - starting in your tab gives an agent your logged-in page, which is a hand-over, and every hand-over is a click;
  - the investigation's first open question is settled in the brief this way.

### 7. Typing never hands a tab over; Hand over and Take back are their own clicks

- **What:**
  - **Start here**, **Hand over to …** and **Take back** work only when `event.isTrusted` is true;
  - Enter is checked the same way;
  - no code focuses these three buttons, so Enter in the text box never reaches them;
  - each button is disabled while its request is open, until `hand_result` comes or 65 s pass (Brave's 60 s question,
    plus a margin);
  - the server ignores a second message with the same `request` from the same socket, so a double click starts one
    agent;
  - **Take back** needs no address match: the server takes back the target it recorded for that tab id, in the chat's
    browser, when an agent holds it as handed (`agent.adopted`). Otherwise the answer is `not_handed`. It never
    connects to the browser (Decision 12).
- **Why:**
  - the rule "hand over and take back are clicks only" covers the chat too;
  - `isTrusted` is false for an `element.click()` from script, so only the user's own click passes;
  - Take back only removes power from an agent, and the strip shows it only for a tab the server recorded as handed.
    A forged tab id could at most take back another handed tab of the same browser.

### 8. No `debugger`: the server matches the tab by its address and window

- **What:**
  - the chat sends a tab descriptor, `{id, window, url}`, and never a target;
  - for Start here and Hand over, the server resolves it in `app/tabmatch.py`:
    1. it validates the descriptor: `id` and `window` are non-negative integers (a JSON `true` is not an integer), and
       `url` is a string that starts `http://` or `https://`, at most 2,000 characters. Anything else is `bad_tab`;
    2. it takes the candidates: the targets whose `url` equals the descriptor's exactly (`InstanceLink.targets_showing`,
       wave 4), and whose context is the chat's own profile (`context_of`). More than 20 candidates count as
       `ambiguous` at once, with no window lookups;
    3. it keeps those whose `InstanceLink.window_of(target)` equals `window`. It **always** checks the window, even for
       a single candidate. A single candidate in another window means your tab no longer shows that address, so it is
       `changed`. A lookup that fails counts as another window;
    4. exactly one left means found. Two or more means `ambiguous`, even when the server has recorded a target for this
       tab id: the brief says it refuses, never guesses. None means `changed`;
  - on `changed`, the server reads the list fresh once (`InstanceLink.refresh()`) and tries again before it refuses;
  - on success it records the tab id and target in the `GroupKeeper` of the chat's own copy (the `WatcherConn` with
    the chat's origin, wave 4), then checks whose the tab is again;
  - the descriptor's address is used for the match only. The server never logs it, and the agent gets the address
    from the server's own list (Decision 9).
- **Why:**
  - Decision 5 of everyday-brave stands: `debugger` would let the watcher drive any tab;
  - measured: CDP's `Browser.getWindowForTarget` returns the same window id as `chrome.tabs` does, and it is a
    browser-level call that never attaches to your tab (bravelink.py:1-8 still holds);
  - the codebase already refuses to guess when a match isn't unique (watcher/groups.js:70-79, "never a guess" at
    :74);
  - checking the window even for one candidate is stricter than the investigation's step 3. It costs one call, and it
    removes a race.
- **The cost:**
  - the same address twice in one window is refused;
  - a single-page app that changes its address between your click and the check (a Gmail `#` link, say) is refused
    once and needs a second click;
  - the tab's group is found by address, as `_hand` does today (`find: {url}`, server.py:528). With the same address
    open in another window of the profile, the watcher answers `ambiguous` and the handed tab stays ungrouped, as any
    grouping failure does (everyday-brave Decision 5). The strip still says "handed", because the match recorded the
    tab id.

### 9. The chat sends no page data to agents

- **What:**
  - the chat's `send` and `new_task` carry no `tab`;
  - the server sets `tab` to `{}` for both when they come from a watcher origin, whatever the message says;
  - for **Start here** the server builds the page line itself, from its own list, labelled "handed": the "Tab the user
    handed you" line of `page_line` (bridge.py:66-75), as Hand over does today (agents.py:285-286).
- **Why:**
  - today's panel sends the tab's address and title with every message in app mode (panel.js:159);
  - next to your mail, that would send what you are reading to an agent you only meant to talk to;
  - a tab reaches an agent only through a hand-over.

### 10. Cards: Allow once and Deny; Show me and Continue

- **What:**
  - **permission cards:** the chat calls `permissionCard(…, { always: false })`, the option watcher-safety added. The
    card has **Allow once** and **Deny**, and the line "Always allow is in AI Home's Tools.";
  - the server already drops `permission` with `answer: "always"` from the watcher, with no answer (watcher-safety
    Decisions 3 and 4). This spec changes nothing there;
  - **check.js:** `checkCard(agent, send, { skip = true, show = null } = {})`:
    - when `skip` is false, the card has no **Skip this site** (check.js:46), and it always shows the "To skip it, tell
      the agent: skip it" line (check.js:27);
    - when `show` is given, **Show me** calls it for a check without a `live` link, in place of today's `watch` with
      the target (check.js:31-34). A valid `live` link still opens the live view, with wave 3's `openLive`;
  - **the chat's Show me** sends `check_show {id}`, watcher-safety's message: the server brings forward the tab where
    that agent's check waits. The chat never needs the tab's target;
  - **Continue** sends `check_continue`, as today.
- **Why:**
  - the user accepted "Allow once and Deny only" in the brief's defaults;
  - the watcher may Continue but never Skip (server.py:60);
  - a typed message to an agent at a bot check stays allowed, because "skip it" is the documented way to skip from
    here. This differs on purpose from the Brain's send card, which refuses at a bot check (brain-delegation, its
    `CHECK_SAY`): a card built from speech could carry words the user didn't mean.

### 11. The watcher's tables grow

- **What the watcher may send.** The earlier waves leave `MESSAGE_RULES` with 65 types, 24 of them allowed for the
  watcher and 56 for the app's pages:
  - watcher-safety: 54 types (22 watcher, 47 app);
  - brain-delegation: `tell_confirm` and `tell_dismiss`, app only;
  - cdp-relay: `browser_disconnect`, app only;
  - app-window: `ai_keyword` (watcher only), `settings_set` and `open_url` (app only);
  - browser-profile-choice: `opened_tab` (watcher only), `browsers`, `place_set`, `watcher_copy` and `restart_in`
    (app only).

  This spec adds three types and allows five more for the watcher. The table then has 68 types: 32 for the watcher and
  56 for the app's pages. If the merged table counts differently, the test's copy follows the merged code plus these
  rows.

  | Type | App pages | Watcher | Watcher condition |
  |---|---|---|---|
  | `start_here` **(new)** | no | yes | `tab_desc(message["tab"])` is a valid descriptor, and `request` matches `_TALK_ID` (server.py:59: 1 to 40 of `[A-Za-z0-9-]`) |
  | `hand_here` **(new)** | no | yes | the same |
  | `take_back_here` **(new)** | no | yes | the same |
  | `new_task` | yes | yes, was no | no `adopt`, or an empty one. The server drops `tab` |
  | `send` | yes | yes, was no | the server drops `tab` |
  | `stop`, `model`, `events` | yes | yes, was no | |

  Everything else in watcher-safety's table stays as it is. In particular these stay "no" for the watcher:
  - `close` and `check_skip`;
  - `watch` and `thumbs`;
  - `hand_tab`, `take_back` and `brave_connect`;
  - `permission` with "always";
  - the Tools, workflow and skill messages;
  - the hearing messages, and the talk with the Brain.

  The new types are "no" for the app's pages, because AI Home names tabs by target (`hand_tab`, `new_task` with
  `adopt`). One way per origin means one path to check.

  `may_send` checks only the message. So whether the chat's hands work in that place (`panel_place.hands`, Decision 13)
  is checked in `_here`, which answers with `hand_result`. That answer is not a table refusal: the message was allowed,
  and the action was refused.
- **What watcher sockets receive.** `WATCHER_RECEIVES` has 20 types after the earlier waves (watcher-safety's 18,
  app-window's `keyword_started` and browser-profile-choice's `open_tab`). It gains seven, which makes 27:
  - `agent_event`, `agent_events` and `created`: the chat's conversation, and the answer to a start;
  - `panel_place`, `tab_owners`, `hand_wait` and `hand_result`: new.

  Among watcher sockets, `agent_event`, `panel_place`, `tab_owners`, `hand_wait` and `hand_result` go only to chat
  sockets (sockets that said `hello` with `view: "panel"`). So the Brain page and the worker still get no conversation
  broadcasts, as watcher-safety Decision 5 made it.

  Trimmed for watcher sockets:
  - `WATCHER_AGENT_FIELDS` gains `number`, `queued`, `model` and `check`. `for_watcher` copies `check` without its
    `target`, as it does for `check_request` (watcher-safety Decision 6);
  - `agent_event` and `agent_events` lose each event's `page` field (chat.js:74): the chat has no Page view;
  - the snapshot for watcher sockets stays as it is: only trimmed agents. The chat gets the app's default model from
    `panel_place`.
- **Why:**
  - the server can't tell which watcher page sent a message, because they all share one origin, so rights are per
    origin (watcher-safety Decision 1);
  - the new messages carry a descriptor, which the server checks. They never carry a raw target;
  - nothing the watcher receives carries a target id. `tab_owners` carries the browser's own tab ids, which the copy
    can already see through `chrome.tabs` (watcher-safety Decision 6 allows those);
  - watcher-safety Decision 12 allowed the watcher only types that can't give an agent one of the user's tabs or
    connect to Brave. This spec's types do both, on purpose, because the brief's side chat starts agents and hands them
    tabs:
    - `start_here` and `hand_here` hand a tab and may connect, each only from a trusted click, through the server's
      own match and owner check;
    - `send` and `new_task` start an agent's turn, and a turn may connect under wave 2A's `turn` rule, as the same
      messages from AI Home do;
    - the rest of watcher-safety's limits stay: no lasting allow, no talk or listening, no Skip, no closing a tab.

### 12. Brave is asked only after your click

- **What:**
  - `start_here` and `hand_here` call `_ready_for_hands`, on the link of the agents' place (Decision 13 makes it the
    chat's place too):
    - `connected`: it goes on;
    - `ready`, `refused` or `lost`: it starts the same attempt as AI Home's Connect, wave 2A's `open("connect")`
      (today's `connect_brave()`, server.py:485-488, which wave 4 routes through `InstanceLinks.connect(place,
      "connect")`), and awaits it. Today's `connect_brave` only schedules the attempt (`_job`); this path needs one
      it can await;
    - `asking`, from this attempt or one already open: it sends `hand_wait {request, why: "allow"}` once, and awaits
      the same shared attempt. The relay holds it for at most `ALLOW_WAIT` (60 s);
    - after the attempt: `connected` goes on, `refused` ends with `refused`, and `off` ends with `off`;
    - `off` from the start: `off`, with no attempt;
  - `take_back_here` never connects (Decision 7);
  - opening the chat, switching tabs, `hello`, `events` and `tab_owners` never connect;
  - `send` and `new_task` from the chat start an agent's turn, and a turn may connect under wave 2A's `turn` rule,
    exactly as a message or a task from AI Home does.
- **The texts that say when to click Allow** (wave 2A's Decision 15: `SWITCH` in `run.py`, the setup page's Allow
  line and the README's, as wave 4 left them) add the chat, and keep every moment the earlier waves named. They
  become: "Only click Allow right after you started AI Browser, clicked Connect, gave an agent a task, switched to
  {name} in AI Browser's Settings, clicked Start here or Hand over in the chat beside your page, asked Claude Code to
  browse, or opened {name} again while an agent was working." The sentence after it stays wave 2A's: "If {name} asks
  at any other time, it isn't AI Browser: click Deny, unless you just started another browser tool yourself."
- **Why:**
  - the consent rule from everyday-brave and the relay: a connection only right after something the user did;
  - a Deny is final until the next click: nothing retries by itself;
  - without the new words, the user would be told that a question right after Hand over "isn't AI Browser", and might
    Deny the one that is.

### 13. Hands work only in the profile agents use

- **What:**
  - each watcher copy has a place, from wave 4: its browser and its profile (`place_of(origin)`);
  - the chat's hands (Start here and Hand over) are on only when the chat's place is the agents' place, the Settings
    choice. Take back works in any chat (Decision 7);
  - `hand_here` also needs the agent's own place (`agent.place`: the same browser and profile folder) to be the chat's.
    An agent started before a profile switch keeps its old place (wave 4), so it gets `other_place`;
  - **Start here** creates the agent with the tab's place (wave 4 Decision 3's exception). Under this decision that is
    always the agents' place;
  - **Start** and **Start in its own tabs** work from any chat. The new agent gets the Settings place, as every new
    agent does;
  - `panel_place.hands` is false, with its `why`, in five cases:
    - `"no_link"`: the server has no browser link for the agents' place. Wave 3 retired every agent mode but the
      user's browser, and wave 4's `InstanceLinks` always holds the current place's link, so this arises only for a
      server built without one, as in tests;
    - `"other_browser"`: the chat's browser isn't the agents' browser;
    - `"other_profile"`: the chat's profile isn't the agents' profile;
    - `"unknown_profile"`: the chat's origin maps to no place (wave 4's "unknown" or "shared" copy);
    - `"off"`: the agents' browser's switch is off.
- **How this meets wave 4:**
  - the same rule for where tasks go: wave 4's "Where new tasks go" (in its Switching section) says a task from any
    chat uses the current place, and Start here takes the handed tab's place;
  - one difference, on purpose: wave 4 Decision 14 lets AI Home give a tab to an agent in another profile of the same
    browser, with a label ("(in Work)"). The chat refuses that (`other_place`): it has no room for the label, and the
    agent would then work under two profiles' logins. AI Home's Give to still can.
- **Why:**
  - watcher-safety lists, and lets you hand over, only tabs of the agents' profile (its Decisions 7 and 10). The chat
    keeps the same rule, so `_handable` needs no exception;
  - a tab from profile "Work" has Work's logins. An agent placed in "Personal" would open its other tabs with other
    logins;
  - switching the agents' profile is one click in AI Home and asks no Allow (wave 4, measured: one Allow covers every
    profile of one Brave).
- **Rejected: placing agents in the chat's own profile.** It would need a second way to choose an agent's place, and
  an exception in `_handable` for tabs that AI Home doesn't list.

### 14. The buttons say Tell and Start, never Send

- **What:** the composer's buttons are **Tell**, **Start**, **Start here · <host>**, **Start in its own tabs**,
  **Hand over to <n · name>** and **Stop**.
- **Why:** the chat sits beside Gmail and Slack. A **Send** button there could be taken for the site's Send. And "the
  watcher never presses Send" should stay plainly true on screen.

### 15. The promise, reworded in five places, and shown once

The core sentence: "It never presses Send for you. An agent works in one of your tabs only after you click Start here
or Hand over."

| Place | New text |
|---|---|
| `watcher/manifest.json:5` (`description`, at most 132 characters) | "Your agents' chat and the Brain's inbox, beside your tabs. It never presses Send; agents use your tabs only when you hand them over." |
| `watcher/brain.html:26` | "(only tabs you have open; it reads and drafts, and you press Send)" |
| `watcher/worker.js:1-4` (header comment) | "…It never presses Send. It holds the chat beside the page (Brave's side panel); an agent gets one of the user's tabs only from the user's click in that chat (Start here, Hand over) or in AI Browser's window." |
| `app/setup.html:61-62` (`app/ui/setup.html` after wave 3) | "Also one time: the watcher puts AI Browser's chat beside your pages in Brave, and the Brain watches the sites you pick (Gmail, Slack, Asana…) there. It reads new messages and drafts replies you approve. It never presses Send for you. An agent works in one of your tabs only after you click Start here or Hand over, and it asks you before any ⚠ step like Send, Buy or Delete." |
| `README.md:217` and `:243` | :217 gains the core sentence and "The watcher also holds the chat beside your page (see below)." :243 becomes "**You press Send**: the watcher never presses it for you." |

- **Shown once:**
  - the chat and the Brain page show the first-run line until **Got it**;
  - one flag in `chrome.storage.local` (`promise2Seen`), shared by both;
  - if the flag can't be read, the line shows. It is only a convenience.
- **The other texts that change:**
  - setup step 3 (setup.html:70);
  - the README's watcher steps (:224, :226);
  - the README's permission line (:276-278, which watcher-safety already changed so the Brain page offers **Allow once**
    and **Deny**): the side chat in Brave offers the same two;
  - AI Home's empty agent list (home.html:50 and home.js:181 today, in `app/ui/` after wave 3). Wave 3 dropped its
    words "or open the chat beside any page" until this wave; they come back as "No agents yet. Start a task above,
    or open the chat beside any page in Brave: the watcher's icon, or ⌘⇧Y (Ctrl+Shift+Y on Windows).";
  - the terminal's ready text (run.py:49-51 today), which wave 3 rewrote without a shortcut. It gains one line: "In
    Brave, the watcher's icon or <shortcut> opens the chat beside your page.", with `<shortcut>` from
    `platforms.shortcut`. Wave 3's terminal-text test then expects that shortcut (⌘⇧Y on darwin, Ctrl+Shift+Y on
    win32) on that line only, and still no "extension";
  - the terminal's watcher steps (run.py:71-72 today), which end in "never sends anything" and take the core sentence
    instead;
  - the Allow line in `SWITCH`, the setup page and the README (Decision 12).
- **Why:**
  - the watcher itself still never sends;
  - agents started from it can act in a tab you handed over, through the ⚠ step, once you agree;
  - users who loaded it under the old promise get the new powers on a silent reload, so they see the new wording once.

### 16. AI Browser's side panel retires

- **Deleted:**
  - `app/extension/panel.html`, `panel.js` and `panel.css`, the files wave 3 left unserved for this port, and the
    `app/extension/` folder once it is empty;
  - `tests/test_panel.py`, which wave 3 skipped, once its tests live in `tests/test_sidechat.py`;
  - `targetOfTab` and `tabOfTarget` (link.js:70-84) and AI Browser's `manifest.json` (with `side_panel`, `sidePanel`,
    `debugger` and the command, extension/manifest.json:6,9,13-18) are already gone in wave 3. Test 21 checks that no
    `chrome.debugger` is left in the watcher.
- **Moved:**
  - `test_the_panel_shows_the_same_card_for_the_users_own_tab` (tests/test_check_card.py:104) and
    `test_the_panel_shows_the_same_card` (tests/test_ai_home_phase2.py:58) move into `tests/test_sidechat.py` (test 34);
  - both files drop `from test_panel import panel` (test_check_card.py:12, test_ai_home_phase2.py:12). Without that,
    deleting `test_panel.py` breaks their collection. While wave 3's module-level skip is in place, that import skips
    every test in both files.
- **Why:** with wave 3 there is no AI Browser window with tabs to sit beside, and the watcher's chat covers the panel's
  job without `debugger`.

### 17. The Brain points to the side chat

- **What:**
  - brain-delegation's `HAND_OVER_SAY` (`brain/talk.py`) becomes: "Only you can give {label} one of your tabs: open
    the chat beside that tab with the watcher's icon and press Hand over to {label}, or use Your tabs → Give to this
    agent. Or tell it the page's address, and it opens it in a tab of its own, with your logins.";
  - `HAND_OVER_ANY_SAY` (`brain/talk.py`) becomes: "Only you can give an agent one of your tabs: open the chat beside
    that tab with the watcher's icon, pick the agent in To: and press Hand over. Or tell it the page's address.";
  - the hand-over sentence that brain-delegation Decision 11 adds to `BRAVE_PROMPT` (`app/bridge.py`; wave 4's
    `browser_prompt(name)`) becomes: "If the task needs a page the user has open, ask in one line: hand me that tab
    (Hand over in the chat beside it, or Give to this agent in Mission Control), or tell me its address and I'll open
    it in a tab of my own.";
  - there is no `HAND_OVER_APP_SAY` to change: wave 3 deleted it with AI Browser mode (app-window, Decision 12).
- **Why:**
  - the chat is now the shortest way to hand a tab over. The Brain still only points: it never hands anything over;
  - the lines name no browser and no shortcut. The Brain's lines are spoken when Voice is on, where "⌘⇧Y" reads
    badly, and wave 4 may place agents in Chrome.

## Messages / interfaces

### Files

- **New:**
  - `src/ai_browser/app/watcher/panel.html`, `panel.css`, `panel.js`: the chat;
  - `src/ai_browser/app/watcher/sidechat.js`: pure functions for the strip, the mode, the default **To:**, the waiting
    line and labels;
  - `src/ai_browser/app/watcher/sidepanel.js`: the worker's panel set-up, the popup guard and `openChatFor`;
  - `src/ai_browser/app/watcher/brainpage.js`: `openBrain(itemId)`, moved from worker.js:304-314 so the worker and
    the chat share it;
  - `src/ai_browser/app/tabmatch.py`: `TabDesc`, `tab_desc`, `resolve_tab`;
  - `tests/test_sidechat.py`, `tests/test_tabmatch.py`.
- **Changed:**
  - watcher: `manifest.json`, `worker.js`, `brain.html`, `brain.js`, `brain.css`;
  - shared: `check.js` (`skip` and `show`);
  - `brain/watcher.py:20`: `WATCHER_SHARED` gains `chat.js` and `check.js`. Neither imports another module (at HEAD
    both import nothing; wave 1A adds only exports to `chat.js`, and wave 3 puts `openLive` inside `check.js`), so the
    chat's module graph loads with these two. `nav.js` stays out of the watcher. Its source folder is `app/ui/` after
    wave 3;
  - `app/server.py`, `app/bravelink.py` (wave 4's `InstanceLink`), `app/groups.py`;
  - `brain/talk.py` (`HAND_OVER_SAY`, `HAND_OVER_ANY_SAY`) and `app/bridge.py` (the `BRAVE_PROMPT` sentence):
    Decision 17;
  - `app/ui/setup.html` (the promise, step 3, the Allow line) and `setup_page` (server.py:79-89), which gains a
    `{{SHORTCUT}}` placeholder from `platforms.shortcut`; `app/run.py` (`SWITCH`'s Allow line,
    and the watcher steps if wave 3 left them), `README.md`, and the app's home texts (Decisions 12 and 15);
  - tests: `test_watcher_rules.py`, `test_app_server.py`, `test_bravelink.py`, `test_check_card.py`,
    `test_ai_home_phase2.py`, `test_brain_talk.py`, `test_bridge.py`, `test_cdprelay.py` (its drift test reads
    `app/bravelink.py` too), `fake_brave.py`.
- **Deleted:** Decision 16's list.

### The watcher's manifest

The whole file after this wave. `host_permissions` and `optional_host_permissions` are today's
(watcher/manifest.json:7-9), and `omnibox` is wave 3's:

```json
{
  "manifest_version": 3,
  "name": "AI Browser Watcher",
  "version": "0.3.0",
  "description": "Your agents' chat and the Brain's inbox, beside your tabs. It never presses Send; agents use your tabs only when you hand them over.",
  "permissions": ["scripting", "storage", "notifications", "tabs", "alarms", "tabGroups", "sidePanel"],
  "host_permissions": ["https://mail.google.com/*", "https://app.slack.com/*", "https://app.asana.com/*",
                       "http://127.0.0.1/*", "http://localhost/*"],
  "optional_host_permissions": ["https://*/*", "http://*/*"],
  "background": {"service_worker": "worker.js", "type": "module"},
  "side_panel": {"default_path": "panel.html"},
  "action": {"default_title": "AI Browser: chat beside this page", "default_icon": {"128": "icon.png"}},
  "commands": {"_execute_action": {"suggested_key": {"default": "Ctrl+Shift+Y", "mac": "Command+Shift+Y"},
                                   "description": "Open the AI Browser chat beside this page"}},
  "omnibox": {"keyword": "ai"},
  "icons": {"128": "icon.png"}
}
```

The description is exactly 132 characters, the limit in Chrome's manifest docs.

The manifest must not contain:
- `debugger`;
- `externally_connectable`;
- `web_accessible_resources`;
- `incognito` other than "spanning" (watcher-safety test 21);
- a `content_security_policy` key (the MV3 default applies).

### Watcher JS modules

- **`sidechat.js`** is pure: no `chrome.*`, no DOM.
  - It uses `agentLabel(agent)` from `chat.js` (brain-delegation), which gives "2 · Fix the footer".
  - `hostOf(url) -> string`: `new URL(url).host`, or `""` when the address won't parse.
  - `isWebPage(url) -> boolean`: http or https.
  - `stripFor({ tab, owner, place }) -> { state, text, note, takeBack }`:
    - `state` is one of `yours`, `handed`, `agent`, `session`, `browser_page` or `no_tab`;
    - `text` is the strip's line;
    - `note` is the muted second line, from `place.why`;
    - `takeBack` is true exactly when `state` is `handed`.
  - `modeFor({ to, strip, place }) -> "tell" | "choose" | "start" | "off"`:
    - `"off"` only while the chat isn't connected;
    - `"choose"` only when `to` is `new`, the strip says `yours` and `place.hands` is true;
    - with `place.hands` false, **New agent** on your tab is `"start"` (in its own tabs).
  - `handButton({ to, strip, place, agent }) -> { show, label, disabledWhy }`.
  - `defaultTo({ current, owner, agents, tabChanged }) -> id | "new"`.
  - `waitingLine(agents, shownId) -> { text, id } | null`.
  - `stateWord(state) -> string`.
- **`panel.js`:**
  - **its socket:** `connect({ view: "panel", … })` from `link.js`. It registers no `chrome.runtime.onMessage`,
    `onConnect` or `onMessageExternal` listener;
  - **its state:**
    - `windowId`, set once;
    - `tab`, the active tab: `{id, windowId, url}` (never its title);
    - `agents`, keyed by id;
    - `owners`, from `tab_owners`;
    - `place`, from `panel_place`;
    - `to`, an agent id or `"new"`;
    - `pending`, the open request ids;
    - `defaultModel`;
  - **rendering:** everything is set with `textContent` (chat.js:5-22 does the same). `<option>` labels too;
  - **the click guards:** `startHere`, `startOwn`, `handOver`, `takeBack`, `tell`. Each returns at once unless
    `event.isTrusted`;
  - **the model:**
    - the menu's choice is kept in `chrome.storage.local` (`model`), as panel.js:191 does today. It is a convenience;
    - without it, `panel_place.model` is used: the server's `settings.model ?? default_model` (wave 3). The watcher's
      snapshot carries no `default_model` (watcher-safety Decision 5).
- **`sidepanel.js`:**
  - `setUpSidePanel(api = chrome)` is called once at the worker's top level. It sets the panel behaviour, registers the
    guard's listeners at once, and guards the open windows;
  - `async guardTab(tab, api = chrome)`;
  - `async windowOf(tabId, api = chrome) -> { id, type } | null`, for the Brain page;
  - `openChatFor(win, api = chrome) -> boolean`: synchronous, with no `await` before `api.sidePanel.open`. It returns
    false, and opens nothing, unless `win.type === "normal"`.

  The `api` parameter lets tests pass a fake.
- **`worker.js`:**
  - imports `setUpSidePanel` and `openBrain`;
  - drops worker.js:340 and its own `openBrain`;
  - keeps what waves 3 and 4 added: the `ai` keyword's handlers and `startKeywordTask` (app-window Decision 11), and
    the `open_tab` branch in `handle` with `open: true` in `watcher_caps` (browser-profile-choice, "WebSocket: app ↔
    watcher");
  - never gets `tab_owners`, `panel_place`, `hand_wait` or `hand_result`: they go to chat sockets only (Decision 11).
- **`brain.js` and `brain.html`:**
  - **Chat**, a `#open-chat` button:
    - at load, `chrome.tabs.getCurrent()`, then `windowOf(tab.id)`, kept as `win`;
    - `win` is read again on `tabs.onAttached` for that tab;
    - the click calls `openChatFor(win)`;
  - the first-run line.

  Its permission cards already pass `{ always: false }` (watcher-safety, watcher/brain.js:21-22).

### Shared modules

- **`permission.js`:** unchanged here. Watcher-safety added `{ always = true }`, and the chat passes
  `{ always: false }`. AI Home and Mission Control in the app window keep **Always allow**.
- **`check.js`:** `checkCard(agent, send, { skip = true, show = null } = {})`. Its `openLive` is its own (wave 3), so it
  still imports nothing, and wave 3's static test (no `WATCHER_SHARED` file imports `nav.js`) keeps passing.
- **`chat.js`:** unchanged here (brain-delegation added `agentLabel`). It is now shipped to the watcher too. The chat
  calls `createChat` with no `onPage`.
- **`link.js`:** unchanged here. Wave 3 adds the http path and removes the debugger helpers.

### Chat → server (WebSocket, the watcher's origin and token)

| type | fields | notes |
|---|---|---|
| `hello` | `view: "panel"` | answered with `snapshot`, `panel_place` and `tab_owners`. Wave 3 dropped the `panel` view; it comes back for watcher sockets only |
| `events` | `id` | the picked agent's conversation |
| `new_task` | `text`, `model`, `request` | no `adopt`, no `tab` |
| `start_here` | `request`, `text`, `model`, `tab: {id, window, url}` | a trusted click; an empty `text` gets `no_text` |
| `send` | `id`, `text` | no `tab` |
| `hand_here` | `request`, `id`, `tab: {id, window, url}` | a trusted click |
| `take_back_here` | `request`, `tab: {id, window, url}` | a trusted click |
| `stop` | `id` | |
| `model` | `id`, `model` | |
| `permission` | `agent`, `request`, `answer: "once" \| "deny"` | |
| `check_continue` | `id` | |
| `check_show` | `id` | watcher-safety's **Show me**, by agent id |

- **`request`:** 1 to 40 characters of `[A-Za-z0-9-]`, unique per click. The server ignores a repeated `request` on
  the same socket.
- **`text`:** at most `TEXT_LIMIT` (20,000) characters, as today (`_text`).

### Server → chat

| type | fields | when |
|---|---|---|
| `snapshot` | as `for_watcher` trims it: only the agents, each with `WATCHER_AGENT_FIELDS` | after `hello` |
| `agent` | trimmed the same way; `check` without `target` | broadcast |
| `agent_closed`, `agent_event`, `agent_events`, `created`, `error` | as today | broadcasts and replies |
| `panel_place` | `{"hands": bool, "why": "" \| "off" \| "no_link" \| "other_browser" \| "other_profile" \| "unknown_profile", "browser": "Brave", "inspect": "brave://inspect/#remote-debugging", "place": "Brave · Personal", "model": "sonnet"}`, where `browser`, `inspect` and `place` describe where agents work (wave 4's `describe(place)` and `browsers` row) | after `hello`, and when the agents' link's state, the Settings choice or a watcher copy's place (wave 4's `Watchers.refresh`) changes |
| `tab_owners` | `{"owners": {"<tab id>": {"kind": "agent" \| "handed" \| "session", "id", "name", "color"}}}` | after `hello`, and at most every 100 ms after an owner or a recorded tab id changes |
| `hand_wait` | `{"request", "why": "allow"}` | once, while the browser's question is open after a Start here or Hand over click |
| `hand_result` | `{"request", "ok": true, "id"?}` or `{"request", "ok": false, "reason"}` | the answer to `start_here`, `hand_here` and `take_back_here`; `id` is the agent's |

- **`hand_result` reasons:** `bad_tab`, `no_text`, `ambiguous`, `changed`, `not_yours`, `not_handed`, `closed`,
  `other_place`, `off`, `refused`, `no_link`, `other_browser`, `other_profile` and `unknown_profile`. The chat maps
  each one to the fixed sentences in What the user sees. A `start_here` that worked also gets `created {id, request}`,
  as `new_task` does.
- **`tab_owners` is per chat:** each chat socket gets only the tabs of its own profile (Decision 4). It never holds a
  "you" or Brain tab, and never a target id. A session's `id` is its `cc-` id.

### Server (Python)

- **`app/tabmatch.py`:**
  - `@dataclass(frozen=True) class TabDesc: id: int; window: int; url: str`;
  - `tab_desc(value) -> TabDesc | None`: the checks in Decision 8, step 1;
  - `async resolve_tab(desc, candidates, window_of) -> tuple[str | None, str]`:
    - `candidates` are the target ids that show `desc.url` exactly in the chat's profile (`targets_showing`, filtered
      by `context_of`);
    - `window_of` is an async callable, target → `int | None`;
    - it returns `(target, "")`, `(None, "ambiguous")` or `(None, "changed")`, by Decision 8, steps 2-4;
  - `MAX_CANDIDATES = 20`.
- **`InstanceLink`** (wave 4's name for `BraveLink`):
  - `async window_of(target) -> int | None`: `Browser.getWindowForTarget` on the app's own privileged client. It never
    attaches, and it returns `None` on any error;
  - `async refresh() -> None`: one fresh `Target.getTargets`.
  - Wave 2A's drift test (its test 18, which reads `app/tabs.py` with `app=True`) also reads `app/bravelink.py` from
    this wave, because these two send CDP from there. Both methods pass the app client's list (cdp-relay, Decisions 7
    and 9).
- **`GroupKeeper`:**
  - `target_of(tab) -> str | None`, the reverse of `tab_of` (groups.py:77-78);
  - `known() -> dict[str, int]`.
- **`AppServer`:**
  - `HERE_MESSAGES = {"start_here", "hand_here", "take_back_here"}`: their `MESSAGE_RULES` rows allow them only from
    the watcher (Decision 11);
  - `self._panels: dict[WebSocket, asyncio.Queue]`: chat sockets, filled by `hello` with `view: "panel"` from a
    watcher-role socket, and emptied in `_unsubscribe`. `_write` uses it for the chat-only types (Decision 11);
  - `self._here_seen: dict[WebSocket, set[str]]`: request ids already handled, at most 200 per socket, dropped in
    `_unsubscribe`;
  - `_panel_place(ws) -> dict` and `_send_panel_places()`: from `place_of(origin)`, the current place and the link's
    state;
  - `_copy_of(ws) -> WatcherConn | None`: the connected copy with the chat's origin, whose `GroupKeeper` learns the
    chat's matches. With none connected, a match is used but not remembered;
  - `async _ready_for_hands(queue, request, link) -> str`: `""` once connected, else a reason (Decision 12);
  - `async _resolve_here(link, place, desc) -> tuple[str | None, str]`: the candidates, then `resolve_tab`, with one
    `refresh()` and a retry on `changed`, then `GroupKeeper.remember`;
  - `async _here(ws, queue, kind, message)` (the table already checked the descriptor and `request`):
    - **first, for all three:** a `request` already seen on this socket does nothing;
    - **`take_back_here`:**
      - the target recorded for `tab.id` in the chat's browser (every copy's `GroupKeeper` there), held as handed by an
        agent (`agent.adopted`), else `not_handed`;
      - then exactly what `_brave_command`'s `take_back` does (server.py:513-516, with wave 2's `relay.cut`), so the
        agent loses the tab at once. No `_ready_for_hands`: it never connects;
    - **then, for `start_here` and `hand_here`:**
      - `start_here` with an empty `_text(text)`: `no_text`;
      - `_panel_place(ws)["hands"]` false: `hand_result` with its `why`;
      - `_ready_for_hands`, then `_resolve_here`. Either one's reason ends it with `hand_result`;
    - **`start_here`:**
      - `_handable(target)` (server.py:499-504), else `not_yours`;
      - then `_start_in(...)`;
    - **`hand_here`:**
      - the agent exists, else `closed`;
      - its place is the chat's, else `other_place`;
      - then `_hand(id, target)` (server.py:518-529), which checks `_handable` again, and `not_yours` if it refuses;
  - `async _start_in(target, info, text, model, request, queue)`:
    - this is today's `new_task` with `adopt` (server.py:678-696), moved into one method so that AI Home's `new_task`
      and `start_here` share it;
    - the agent's first message carries `{url, title, label: "handed"}` from the server's own list. AI Home's
      **Hand over → New agent** sends no `tab` today (home.js:471-472), so its agents gain the same labelled line;
  - `_tab_owners(ws) -> dict` and `_tab_owners_soon()`:
    - for one chat: the targets its browser's link lists now, owned by an agent, a session or a hand-over, in the
      chat's profile, each with the tab id recorded in that browser's copies' `GroupKeeper`s
      (`Watchers.connections()`, `known()`). Decision 4;
    - scheduled from the link's `on_change` and from `remember`;
  - `send` to an agent that has closed answers `error {"text": "That agent has closed: nothing was sent"}`, using the
    `False` that brain-delegation's `AgentManager.send` returns. Today it is silent (server.py:697-700).

## Safety

**Brave's own signs stay:**
- nothing answers, auto-clicks, hides or closes "Allow remote debugging?" or the "controlled by automated test
  software" bar;
- the chat only says why Brave is asking, right after the user's click;
- no connection opens because the chat opened or a tab changed (Decision 12).

**No new powers in the watcher but `sidePanel`:**
- no `debugger`, no new host permission, no `externally_connectable`, no `web_accessible_resources`;
- the chat reads only the active tab's id, window and address, through the existing `tabs` permission, and runs no
  script in any page;
- the matching is the server's, and it never attaches to the user's tab (Decision 8).

**Every hand-over is a click:**
- Start here, Hand over and Take back are trusted clicks, each with its own message;
- typing never hands a tab, and no code moves focus onto these buttons, so an Enter for the text box can't press one;
- the server checks again who owns the tab, and refuses an ambiguous or changed match;
- Take back only removes a hand-over the server recorded, and never connects;
- the Brain and the voice have no path to `start_here`, `hand_here` or `take_back_here`: the watcher's origin can't
  talk to the Brain, and the Brain's talk proposes only cards (brain-delegation). The Brain only points to the chat
  (Decision 17).

**The Brain only proposes:** nothing in this spec changes how its cards run. They run only on Start, Send or a plain
yes.

**Nothing a page says reaches the chat:**
- the chat registers no runtime message listener, so content scripts (the Gmail, Slack and Asana readers) can't reach
  it;
- the MV3 default content policy stays.

**Text is text:**
- agent names, conversation lines, hosts, card fields and `<option>` labels are set with `textContent`;
- the strip shows the host, never the page title;
- the chat sends no page data to agents, and the server drops it from watcher messages (Decision 9). A handed tab
  reaches the agent as a labelled line of page data (`page_line`).

**Permissions and bot checks:**
- Allow once and Deny only, and the server drops `always` from the watcher (watcher-safety);
- Show me and Continue only;
- the agent never touches a bot check, and nothing solves or skips one by itself.

**Never spoofed:** nothing here changes what sites see. There are no user-agent or `navigator.webdriver` changes, and
no way around bot checks.

**Passwords:** an agent never types a password. On a handed tab that needs a login, it asks the user to log in in that
tab.

**Downloads need the user's OK:** unchanged. In the user's Brave a download is a ⚠ step, and one that starts outside a
confirmed step is cancelled (everyday-brave Decision 15). The chat adds no path around it.

**Nothing leaves the machine without a knowing choice:**
- the chat talks only to 127.0.0.1;
- the tab's address goes to the local server only on a hand click, and the server never logs it;
- a tab reaches an agent, and so Claude, only after Start here or Hand over, as with AI Home's Hand over today;
- the agents' place label in `panel_place` (a profile's name, which may be a person's name) goes only to the chat on
  this computer, never to an agent or the Brain (wave 4 Decision 16).

**Brave's question, explained, never answered:** the texts that say when to click Allow name the chat's Start here and
Hand over (Decision 12), so the user isn't told to Deny a question their own click caused.

**Popup windows:** the panel is switched off for their tabs, and the code opens it only for a `normal` window
(Decision 2).

**More power next to your mail.** The watcher now sits beside Gmail and Slack, and it can start agents in your tabs.
The guards:
- the fixed allowed list;
- the server's own matching and owner check;
- a trusted click for each hand-over;
- no listener in the chat;
- `textContent` everywhere.

## Testing

Tests never reach the user's real browsers:
- the "Brave" is a throwaway Google Chrome with the watcher loaded (the `watcher` fixture, tests/test_watcher.py:56-97,
  as wave 3 leaves it);
- `BraveLink` (wave 4's `InstanceLink`) points at that Chrome's own folder, as tests/test_bravelink.py:183-190 does;
- conftest's `AIB_BROWSER=sandbox` default stays;
- only the touched test files run, never the whole suite.

**On Windows:** the unit tests run. The throwaway-browser tests skip there, as every test on the `watcher` fixture
does (`PIPE_FIXTURES` and `platform_skip`, tests/conftest.py:26-35). The shortcut texts are checked as text (test 25).

Every test below fails before this change and passes after it.

### First task: four facts, in a throwaway browser

Each fact is measured in a throwaway browser with its own `--user-data-dir`, never the user's:
1. **The guard:** in headless Chrome, after `sidePanel.setOptions({ tabId, enabled: false })` on a popup window's tab,
   `sidePanel.getOptions({ tabId })` reads `enabled: false`. If headless lacks the API, test 36 below runs in a visible
   throwaway Chrome.
2. **The Chat button:** in a visible throwaway Brave 1.94, a CDP mouse click on the Brain page's **Chat** button opens
   the panel. `openChatFor` awaits nothing before `open`, so the click's gesture should hold. `sidePanel.onOpened`
   fires, or `panel.html` shows up as a target. If it doesn't open, the button goes, and the pin step stays.
3. **The panel's window:** in that open panel, `chrome.windows.getCurrent()` gives the window id of the tab beside it.
4. **Real input in a background tab:** in the headless test Chrome, a CDP `Input.dispatchMouseEvent` click and an
   `Input.dispatchKeyEvent` Enter reach a page in a background tab, with `event.isTrusted` true. test_talk's helpers
   bring their page to the front first (`front`, tests/test_talk.py:153-157), which the `side` fixture can't do: the
   chat's own tab would become the active tab it describes. If input doesn't arrive, the `side` fixture opens the chat
   as a real side panel instead, through the Brain page's **Chat** button (fact 2, in a visible throwaway Chrome), and
   drives the panel's own target.

### Unit tests, no browser

`tests/test_tabmatch.py` (new):
1. `test_one_tab_with_the_address_in_that_window_is_found`.
2. `test_the_same_address_only_in_another_window_is_changed`: one candidate, in window 8, for a descriptor in window 7,
   gives `changed`.
3. `test_two_tabs_in_one_window_are_ambiguous`: two candidates, both in window 7.
4. `test_more_than_twenty_candidates_are_ambiguous_without_lookups`: 21 candidates give `ambiguous`, and the fake
   `window_of` is never called.
5. `test_bad_descriptors_are_refused`: these give `None`:
   - `id` as the string `"41"`, and `id: true`;
   - `window: -1`, and a missing `window`;
   - `javascript:` and `chrome://` addresses, and a `url` that isn't a string;
   - an address of 2,001 characters.
6. `test_a_window_lookup_that_fails_counts_as_no_match`: `window_of` gives `None` for the only candidate, so the answer
   is `changed`; with two candidates in window 7 and one failed lookup, the other is found.

`tests/fake_brave.py` gains:
- `windows: dict[str, int]`, `async window_of(target)` (`None` for a target it doesn't know) and `async refresh()`,
  which counts its calls in `refreshes`;
- `targets_showing(url)` and `context_of(target)`, from the pages, which take an optional `context` ("P" by default);
- `FakeBrave(..., ask=True)`: `connect()` counts, sets `asking`, waits until the test calls `answer("allow")` or
  `answer("deny")`, then sets `connected` or `refused`. Without `ask`, `connect()` counts and returns, as today
  (tests/fake_brave.py:54-55).

`tests/test_app_server.py` (new tests; the worker's socket comes from `watcher_socket`, :519, and a chat socket is a
watcher-origin socket that says `hello` with `view: "panel"`). "What Claude got" is read with `sent_to_claude`, as
`test_hand_tab_and_take_back` does (:713-716):

7. `test_start_here_from_the_chat_hands_the_matching_tab`:
   - pages U1 and U2 show the same address, in windows 7 and 8;
   - `start_here` with tab `{id: 41, window: 7, url}` gives `created` and `hand_result ok`;
   - `a1.adopted == ["U1"]`, U1's owner kind is `handed`, and the chat copy's `GroupKeeper.tab_of("U1") == 41`;
   - the first message Claude got starts with "[Tab the user handed you, as reported by the page", with FakeBrave's
     title and address for U1.
8. `test_start_here_refuses_ambiguous_and_changed_pages`:
   - both tabs in window 7 give `ambiguous`, also after `remember("U1", 41)`;
   - no tab with that address gives `changed`, after exactly one `refresh()`;
   - no agent starts in either case.
9. `test_start_here_never_takes_an_agents_or_a_sessions_tab`: gives `not_yours`, starts no agent, and a later
   `tab_owners` lists tab 41.
10. `test_hand_here_and_take_back_here_from_the_chat`:
    - `hand_here` adds U1 to a1, and the note Claude got starts with the "Tab the user handed you" line, then
      `HANDED_NOTE`;
    - `take_back_here` with tab 41 removes it and sends `ungroup_tabs` with `[41]`, with FakeBrave at `state="ready"`
      and `connects == 0`;
    - `take_back_here` on a1's own tab (recorded as 56) gives `not_handed`, and so does a tab id never recorded.
11. `test_hand_here_to_a_closed_agent_hands_nothing`: gives `closed`.
12. `test_only_a_click_connects_brave` (`FakeBrave(state="ready", ask=True)`):
    - a chat's `hello` and `events`, and a `tab_owners` push, leave `connects == 0`;
    - `start_here` gives `connects == 1` and one `hand_wait {request}` while the state is `asking`. After
      `answer("allow")` it gives `hand_result ok`;
    - a `hand_here` sent while `asking` adds no connect, and finishes after the same answer;
    - after a Deny (`answer("deny")`), the answer is `refused`, and nothing connects again until the next click;
    - with `state="off"`, `start_here` gives `off`, and `connects == 0`.

    (`send` and `new_task` from the chat start a turn, which may connect: wave 2A's `turn` rule, tested there.)
13. `test_the_watchers_new_task_and_send_carry_no_page_data`:
    - from the watcher origin, `new_task` and `send` with `tab: {url: "https://mail.example/inbox", title: "SECRET"}`:
      nothing Claude got contains "SECRET" or "as reported by the page";
    - from the app's origin, the same `send` gives a page line (control).
14. `test_the_chats_agent_rows_carry_the_check_without_its_target`:
    - a1 held at a bot check on `T1-7f3a` reaches a chat socket with `check.site`, `check.what`, `number`, `queued` and
      `model`;
    - an `agent_event` whose event has a `page` reaches the chat without `page`;
    - the text "-7f3a" appears nowhere in what the chat socket received.
15. `test_stop_model_and_events_from_the_chat`: `stop`, `model` and `events` for a1 from the watcher's origin take
    effect, and `close` for a1 still does nothing.
16. `test_tab_owners_go_to_chats_only_and_name_only_known_ai_tabs`:
    - after `remember("T1", 55)` and an owner a1 on T1, the chat socket gets `{"55": {"kind": "agent", "id": "a1", …}}`;
    - a "you" tab and a Brain tab are never in the map;
    - a target in another context, with a recorded tab id and an agent owner, isn't in the map;
    - when T1 leaves FakeBrave's list (Brave restarted), 55 leaves the map;
    - the app-origin socket, the worker's socket and the Brain page's socket get no `tab_owners`, and the Brain page's
      socket gets no `agent_event`.
17. `test_panel_place_says_when_hands_work`: these give `hands: false` with their `why`:
    - no browser link (`no_link`);
    - switch `off`;
    - an origin with no place (`unknown_profile`);
    - a chat in profile "Work" while agents use "Personal" (`other_profile`).

    A connected link with an origin in the agents' profile gives `hands: true`. A `hand_here` to an agent whose place
    is another profile gives `other_place`.
18. `test_a_double_click_starts_one_agent`: two `start_here` with the same `request` start one agent, and `start_here`
    with an empty `text` gives `no_text` and starts none.
19. `test_send_to_a_closed_agent_says_nothing_was_sent`.
20. **Watcher-safety's tests in `tests/test_watcher_rules.py`, updated:**
    - `test_the_message_table_covers_every_type_for_both_roles`: the test's own copy gets Decision 11's rows, which
      makes 68 types. `start_here`, `hand_here` and `take_back_here` are "no" for the app's pages. `new_task` with
      `adopt` is still "no" for the watcher, and without it "yes". A descriptor that `tab_desc` rejects, or a
      `request` of 41 characters, makes the three new types "no";
    - `test_what_the_watcher_receives_is_a_fixed_list`: the 27 types. An agent row keeps `WATCHER_AGENT_FIELDS` with
      `number`, `queued`, `model` and `check`, and `check` has no `target`;
    - `test_the_watcher_origin_may_send_nothing_else`: `send`, `stop`, `model`, `events` and `new_task` without
      `adopt` leave its sweep, because they are now allowed. `close`, `watch`, `check_skip`, `hand_tab`, `take_back`,
      `brave_connect` and the rest stay in it, with the same "nothing happened" checks;
    - `test_watcher_sockets_get_no_target_ids`: add a chat socket (`hello` with `view: "panel"`), an `agent_event` and a
      `tab_owners` update. Still no "-7f3a" in anything a watcher socket received.
21. **`test_prepare_watcher_updates_its_folder_in_place`** (tests/test_app_server.py:341), extended:
    - the folder has `panel.html`, `panel.js`, `panel.css`, `sidechat.js`, `sidepanel.js`, `brainpage.js`, `chat.js`,
      `check.js`, `permission.js` and `link.js`, and no `nav.js`;
    - no file in it contains `chrome.debugger`.

`tests/test_bravelink.py`:

22. `test_window_of_asks_the_browser_and_attaches_nothing`:
    - against the fake CDP server, it sends `Browser.getWindowForTarget` and no `Target.attachToTarget`;
    - an error gives `None`;
    - wave 2A's drift test (`tests/test_cdprelay.py`, its test 18) now also reads `app/bravelink.py`, with `app=True`,
      and passes.
23. `test_refresh_reads_the_list_once`: one `Target.getTargets`, and a page added on the fake server shows in
    `targets_showing` right after.

`tests/test_sidechat.py`, the file checks (no browser):

24. `test_the_manifest_has_the_side_panel_and_no_debugger`:
    - `sidePanel` is in the permissions, and `side_panel.default_path` is `panel.html`;
    - `_execute_action` maps ⌘⇧Y and Ctrl+Shift+Y;
    - there is no `debugger`, `externally_connectable` or `web_accessible_resources`;
    - the description is at most 132 characters, and `omnibox.keyword` is still "ai".
25. `test_the_promise_is_new_everywhere`:
    - the core sentence ("An agent works in one of your tabs only after you click Start here or Hand over") is in
      `setup.html`, `README.md`, `panel.html` and `brain.html`;
    - "never presses Send" is in the manifest's description and in worker.js's header;
    - no watcher file, `setup.html`, `README.md` or run.py's setup text says "never sends anything". The Brain's own
      docstring (brain/service.py:5) is not a watcher promise and stays;
    - the Allow line names "Start here or Hand over" in `SWITCH`, the setup page and the README;
    - `setup_page(..., system="windows")` names Ctrl+Shift+Y and no ⌘⇧Y, and `system="darwin"` names ⌘⇧Y.
26. `test_the_chat_listens_to_no_page_and_parses_no_html`:
    - no `.js` file in the prepared watcher folder contains `innerHTML`, `outerHTML` or `insertAdjacentHTML`;
    - `panel.js` and every module it imports (`sidechat.js`, `brainpage.js`, `chat.js`, `check.js`, `permission.js`,
      `link.js`) contain none of `runtime.onMessage`, `runtime.onConnect`, `onMessageExternal` or
      `onConnectExternal`.
27. `test_sidepanel_open_is_called_only_behind_the_window_check`:
    - `sidePanel.open` appears only in `sidepanel.js`, and only inside `openChatFor`;
    - `worker.js` has no `action.onClicked` listener.

`tests/test_brain_talk.py` and `tests/test_bridge.py`: brain-delegation's tests of `HAND_OVER_SAY`,
`HAND_OVER_ANY_SAY` and `BRAVE_PROMPT` assert the new wording of Decision 17:
- the hand-over line names "the chat beside that tab" and "Hand over to 1 · Fix the footer", and has no "⌘";
- `BRAVE_PROMPT` names "the chat beside it" and still contains "tell me its address".

### In a throwaway Chrome, with the watcher loaded

`tests/test_sidechat.py`. The fixture `side` is the `watcher` fixture plus:
- a `BraveLink` on its folder, attached with `server.attach_brave`;
- the watcher's origin given the agents' place;
- the chat opened as `chrome-extension://<id>/panel.html` in a background tab of the user's window, as
  tests/test_panel.py:15-28 did for the old panel (or as a real side panel, if the first task's fact 4 says so);
- user pages served by `testpages.serve_host()`, so they are http;
- a recorder wrapped round `server._handle` that keeps every message type.

Clicks and keys go through CDP `Input.dispatchMouseEvent` and `Input.dispatchKeyEvent`, so they are trusted.

28. `test_the_chat_follows_only_its_own_window`:
    - switching tabs in a second window leaves the strip as it was;
    - switching tabs in the chat's window changes it within a second.
29. `test_the_strip_says_whose_tab_it_is`:
    - a user tab says "· yours";
    - after a `hand_here` it says "· handed to 1 · Fix the footer" and shows **Take back**;
    - an agent's tab (in `tab_owners`) says "1 · Fix the footer's tab";
    - `about:blank` says "a browser page".
30. `test_enter_waits_on_your_tab_until_you_choose`:
    - **New agent**, type, Enter: no `new_task` or `start_here` is recorded, and the hint names both choices;
    - a click on **Start here** starts a1 with `adopted == [the user's tab's target]`;
    - **New agent** again, then **Start in its own tabs**, starts a2 with `adopted == []`, and no page line in what
      Claude got for it.
31. `test_tell_an_existing_agent_never_hands_the_tab`: with **To:** a1, Enter records `send` only, a1's `adopted` is
    unchanged, and no page line is in what Claude got for that message.
32. `test_hand_over_needs_a_real_click`:
    - `document.getElementById("hand").click()` from page script records nothing;
    - a CDP click hands the tab over;
    - a script click on **Take back** does nothing, and a CDP click takes the tab back;
    - after typing in the text box, `document.activeElement` is still the text box.
33. `test_the_same_page_twice_in_the_window_is_refused`: two tabs show `form.html`, and **Start here** gives the
    "Two tabs in this window" hint and starts no agent.
34. `test_cards_in_the_chat` (moved from test_check_card.py:104 and test_ai_home_phase2.py:58, and extended):
    - the permission card's buttons are exactly `["Allow once", "Deny"]`, and watcher-safety's line "Always allow is in
      AI Home's Tools." is there. **Deny** answers the request with deny;
    - the check card's buttons are `["Show me", "Continue"]`, with no `.skip-site`;
    - **Continue** clears the check;
    - **Show me** records `check_show {id: "a1"}`, and never `watch`.
35. `test_hostile_text_stays_text`: `HOSTILE` (test_home.py:16) as an agent name, as conversation text and in a page
    address's path adds no `img` element, the title stays the same, and the strip shows only the host.
36. `test_popup_windows_get_no_panel`:
    - `chrome.windows.create({ type: "popup", url })` leaves its tab with `getOptions` `enabled: false`;
    - a normal window's tab is enabled;
    - `openChatFor({ id: popupId, type: "popup" }, fake)` returns false, and the fake records no `open`;
    - `openChatFor({ id: normalId, type: "normal" }, fake)` records one;
    - `windowOf` on the popup's tab gives `type: "popup"`.
37. `test_the_brain_page_has_chat_and_shows_the_promise_once`:
    - the Brain page's header has **Chat**;
    - the first-run line shows on the Brain page, and is gone after **Got it** and a reload, there and in the chat.
38. `test_the_strip_mode_and_to_rules` (`import('./sidechat.js')` in the chat's page, as tests/test_watcher.py:364
    imports `notify.js`):
    - `modeFor` gives the four rows of the table in Starting an agent, `"start"` for **New agent** on your tab with
      `place.hands` false, and `"off"` while not connected;
    - `stripFor` gives `takeBack` true for a handed tab, also with `place.hands` false, and false for every other
      state;
    - `defaultTo` follows a tab change to an agent's or a handed tab, keeps the choice on any other tab, and gives
      `"new"` when the choice closed;
    - `waitingLine` gives "3 · Flights to Manila is waiting for you", "… and 1 more are waiting for you", and `null`
      when only the shown agent waits.

### By hand, the user, in their own Brave, after wave 5

1. Pin the watcher's icon and click it: the chat opens beside the page. ⌘⇧Y closes it and opens it again.
2. In a second window, open its chat: each chat follows its own window's tab.
3. On Gmail, with **New agent**, type and press Enter: nothing starts until you choose.
4. Hand a tab to an agent from the chat: the strip says handed. Then **Take back**.
5. A permission request shows **Allow once** and **Deny** only.
6. After Brave restarts, click **Hand over** in the chat: Brave asks "Allow remote debugging?" right after the click,
   and the hint says why. Click Allow, and the tab is handed.

Nobody tries a popup window by hand: the guard is tested in a throwaway browser (test 36).

## Out of scope

- **The chat in Chrome, as a supported setup** (the brief's "Later: a Chrome copy of the watcher"). Wave 4 already
  gives a copy its own folder and id per browser and profile, finds its place from the profile's files, and keeps the
  Brain's inbox and notifications on the primary copy (its Decisions 7-9). A copy loaded in a Chrome profile carries
  this chat too, and the server treats it like any other copy: its hands work only where agents work (Decision 13).
  Not done here: a setup-page step for Chrome, Chrome wording in the setup texts, and a hand check in Chrome.
- **Talking to the Brain in the side chat,** typed or spoken, and the mic in the side panel.
- **Always allow in Brave.** It stays in AI Home's Tools.
- **Closing an agent from the side chat.** It stays in the app window.
- **Per-tab panels,** and a Brave sidebar entry for the chat (brave/brave-browser#31334).
- **Opening the chat from a notification click.** Whether that counts as a gesture is not measured, so **Review**
  keeps opening the Brain page.
- **Opening the chat by itself** when an agent needs you.
- **Thumbnails** in the side chat, and the old panel's Page view.
- **Handing a tab, from the chat, to an agent placed in another profile** (Decision 13). AI Home's Give to still can.
- **An extra confirm step** for handing over a tab of a site the Brain watches.
- **Moving an agent to another profile** (brief). "Restart in <browser · profile>" is wave 4's.
- **The `debugger` permission in the watcher:** never (everyday-brave Decision 5).
- **Firefox and Safari.**
