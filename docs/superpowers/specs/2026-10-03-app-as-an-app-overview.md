# The app as an app: design brief

The next project has five parts. One is the Brain fix you asked about. The other four are the pieces you already approved, plus the work that makes Brave stop asking over and over.

## The problems

Each complaint has a cause we can point to in the code.

- **You asked the Brain to use an existing agent, and it started a new one.**
  - The Brain can propose only four things: nothing, start a new agent, draft a reply, or open a view (`src/ai_browser/brain/talk.py:19`). It has no "send to an agent" action. So "give this to the footer agent" can only become a Start card. Confirming that card always creates a new agent (`brain/service.py:631-633`, `:650-653`).
  - What the Brain says out loud is Claude's own free text, and nothing checks it against the card. It can say "Sure, I'll pass that on" while the card starts a new agent. A plain "okay" or "sure" then runs the card (`talk.py:31-32`, `service.py:628`).
  - The new agent works in your Brave and may use only tabs it opens or tabs you hand it (`app/bridge.py:37`, `browser.py:41-42`). So it asked you for a tab.
  - You couldn't command it back by talking. When Claude tries any "send" action, the Brain answers "That's a click for you in AI Browser" (`talk.py:28`, `:159-160`). Messaging an agent already works by click, in its drawer in Mission Control (`mission.js:246-255`, `app/agents.py:158-169`). The Brain just never uses it.
- **"Allow remote debugging?" keeps popping up.**
  - Brave asks once for every new connection and remembers nothing between them (Chromium `chrome/browser/devtools/remote_debugging_server.cc:396-414`, `content/browser/devtools/devtools_http_handler.cc:858-870`).
  - These open connections today: the app itself (`app/bravelink.py:45-66`), each agent's engine (`engine.py:182-198`), and each Claude Code session.
  - So you get 1 question, plus 1 per agent, plus 1 per session. You get another whenever an engine restarts (New chat, a crash, Stop) and whenever Brave restarts.
- **The "controlled by automated test software" bar comes back after you close it.** Brave checks the bar again only when a connection opens or closes. If any connection is still open at that moment, it shows a new bar (`chrome_devtools_manager_delegate.cc:551-564`). Agents connect and disconnect all day, so the bar keeps returning.
- **Several profiles, and sometimes Chrome.**
  - Agent tabs open in whichever Brave profile you clicked last, not in a fixed one. This was measured in throwaway Brave and Chrome. The code never names a profile (`browser.py:427-434`, `grouping.py:44-50`).
  - Claude Code sessions pick the first browser whose switch answers, Brave first. They check again on every connect (`chrome.py:55-63`, `engine.py:193`), so they can land in Chrome.
  - `ai-browser app` itself always starts a Google Chrome window (`appbrowser.py:108-116`, `app/run.py:200-201`).
- **The app is a browser, not an app.** `ai-browser app` starts a separate Chrome with a debugging port. You load its extension by hand, and AI Home, Mission Control and the side panel are pages inside that extension (`appbrowser.py:1-11`, `app/run.py:55-63`).

We also found two privacy and safety gaps along the way:

- **A Brave watcher page can do too much.** It can start an agent in one of your own tabs and save "Always allow" for a tool. The server blocks only a few message types from the watcher. Both were measured with a throwaway server (`app/server.py:644-696`).
- **AI Home's tab list leaks titles.** It shows titles from private windows and from your other profiles as "you" rows (`app/tabs.py:65-69`, `app/bravelink.py:122-133`).

## What we'll build

### 1. The Brain sends work to an existing agent

This is the fix for today's complaint. The rule that nothing runs without your Send or yes stays exactly as it is.

- **A new card: "Send to 1 · Fix the footer: <your words>".**
  - It runs only on Send or a plain yes.
  - It uses the existing `agents.send`.
  - It never falls back to starting a new agent.
- **Fixed spoken lines.** The Brain's line for a card comes from the app, not from Claude:
  - for a start card: "I can start a NEW agent with your words";
  - for a send card: "I can send your words to 1 · Fix the footer".
- **Picking the agent.**
  - You can name it by its number ("agent 2"), its colour ("the blue one"), a word from its name, or "it" (the last agent you dealt with).
  - A number or colour you say beats Claude's guess.
  - If it's still unclear, the Brain asks: "Which agent: 1 · Fix the footer, or 3 · Flights to Manila?" It then sends your first words, not "the footer one".
- **Numbers on screen.** Each agent's number shows on its station, in the List, in its drawer, in AI Home and on "Give to" buttons. It is the agent's id number, and it stays the same for the whole run.
- **A "yes" with no open card never becomes a task.**
- **What happens depends on what the agent is doing:**
  - working: your message is queued, and the agent reads it after its current step;
  - waiting on a permission: queued, and it does not answer the permission;
  - waiting at a bot check: refused, and the Brain points you to Continue;
  - closed: "nothing was sent".
- **The message starts with one fixed line:** "The user said this to the Brain, for you:". It uses no brackets, because agents treat a bracketed first line as page data (`bridge.py:40-41`).
- **Handing over a tab stays a click.**
  - When work needs one of your tabs, the Brain tells you how to hand it over.
  - Mission Control's agent drawer gets a "Your tabs" list, with a "Give to this agent" button on each row.
- **Agents in Brave learn the other way in.** Their instructions get one more line: "hand me that tab, or tell me its address and I'll open it in a tab of my own." A tab they open is in your Brave profile, with your logins.
- **The inbox's "Tell the Brain" box gets the same cards.** Today, if the Brain decides on an agent there, it starts one right away with no card (`service.py:579-580`).

### 2. One shared connection to Brave

- **The app holds the only connection to Brave.**
  - Agents' engines talk to Brave through it.
  - While the app runs, Claude Code sessions do too.
  - It is a relay at `ws://127.0.0.1:<app port>/cdp`, in a new file, `app/cdprelay.py`.
- **What you should see.** This comes from Chromium's source and still needs one hand check in your Brave:
  - one "Allow remote debugging?" per app run, and one more after each Brave restart;
  - none per agent and none per New chat.
- **The bar.** Once you close it, it stays closed while that one connection lives. It comes back when the app or Brave restarts. We never touch it.
- **The relay also decides which tabs an agent may use.**
  - Each agent gets its own token. Today all agents share one (`server.py:148`). The token travels in a header, never in the address.
  - An agent sees and drives only the tabs it opened, their popups, and tabs you handed it.
  - Your other tabs' titles and addresses no longer reach agents.
  - Take back cuts the agent off at once. Today it can take up to 1 s.
  - Only a short list of browser-wide commands gets through. It refuses reading all your cookies, closing Brave, changing permissions and changing download settings.
- **Locked down.** It refuses any connection that carries a web page's Origin or a Host other than `127.0.0.1:<port>`.
- **Without the app.** A lone Claude Code session connects directly, as today, with one Allow per session.
- **If the relay fails while the app is up,** the session reports the error. It never quietly connects on its own, because that would make Brave ask out of the blue.
- **Reconnecting** happens only right after something you did: app start, Connect, or an agent's turn.
  - Everyone waiting shares one attempt, so you see one question.
  - If you click Deny, nothing retries by itself.
- **No more surprise Chrome.** Sessions that go through the app always use the app's chosen browser.

### 3. The app window

- **One plain window.**
  - AI Home, Mission Control and the Brain are served by the app's own server.
  - They show in an app window: a title bar only, with no tabs and no address bar (Chrome's `--app` mode).
  - The window has its own profile and no debugging port. That means no Allow question and no bar for the window itself. Measured: `navigator.webdriver` was false in both Chrome and Brave.
  - Adding a debugging port would bring the bar back (measured), so the window never gets one.
- **No more loading AI Browser's extension by hand.** Only Brave's watcher stays an extension.
- **Opening the window.**
  - The start address carries a one-time code.
  - The server swaps that code for a session cookie the page can't read, and then the code is removed from the address.
  - A page opened any other way gets no live connection. That includes one typed into Brave or opened by an agent.
- **Hardening.** Every route checks the Host, and every page has a strict content policy. This matters because `/setup` shows the setup key today and has no Host check (`server.py:202-211`, `:263-264`).
- **Links.**
  - AI Browser's own extra windows (Mission Control, the live view) open as small app-style windows.
  - Real websites open in your browser, never in the app window.
  - A plain "new tab" link would bring back a normal tabbed window (measured), so the code never uses one.
- **Closing.** Closing the window ends the app, as today. The app notices through the window's connection, because on macOS the browser keeps running with no window (measured).
- **Settings.** Your model and voice choices move to the server. The app remembers its port, so the microphone permission survives a restart.
- **Mic, voice, 3D.** The mic works, because 127.0.0.1 counts as secure. WebGL works. Spoken updates need a click first, unless the window starts with the autoplay flag (see the defaults below).
- **The "ai" keyword.** The window has no address bar, so the "ai" address-bar keyword moves to the watcher in Brave.
- **Your choice of browser.** The browser that draws the window is a Settings choice: Auto, Chrome, Brave, or Edge on Windows. You can switch any time.
- **Later: a double-click Mac app.** Until then, the Dock shows the icon of whichever browser draws the window.

### 4. Browser and profile choice

- **Settings → "Where agents browse".**
  - It shows a card for each installed browser, with its state: switch on, switch off, not running, or connected.
  - Detection looks at installed apps, not data folders. This Mac has leftover Arc, Edge, Vivaldi and Opera folders, but only Brave and Chrome are installed.
  - Under the chosen browser you see its profiles, read from Brave's Local State file: name and colour, never your email.
- **Detection never asks Allow.** It only reads files and checks a local port. It never connects.
- **The saved choice.**
  - The browser and profile are saved in `<home>/settings.json`.
  - Each agent gets them when it starts and keeps them for life.
  - A switch affects only new work.
- **Putting a tab in your chosen profile.**
  - Browser automation can't target a profile (see "Findings that change earlier decisions").
  - So the engine asks the app, and the watcher in that profile opens the tab in the background and groups it.
  - Measured: the tab lands in the watcher's profile whatever profile you used last, and focus doesn't move.
- **The fallback.** Without the watcher in that profile, or without the app, the tab opens in the profile you used last. The agent then says where it went.
- **One watcher per profile.** Each profile you want agents in needs its own watcher copy, in its own folder. That means one "Load unpacked" per profile, once.
- **The tab list.** AI Home lists only the agents' profile, plus a line like "4 tabs in other profiles". Private windows are never listed.
- **A quick switcher in AI Home,** for example "Brave · Personal ▾".
  - Switching profile is instant and needs no Allow.
  - Switching browser asks Allow once in the new browser.

### 5. The side chat in the watcher

- **The chat beside your page moves into Brave.** It lives in the watcher and uses Brave's side panel, which works in Brave 1.94 (measured).
  - It opens from the watcher's toolbar icon or with Cmd/Ctrl+Shift+Y.
  - Pin the icon: Brave has no sidebar entry for extension panels (brave/brave-browser#31334).
- **One panel per window.** It follows that window's active tab.
- **Layout, top to bottom:**
  - a strip saying whose tab this is: "This tab: mail.google.com · yours", "· handed to Blue", or "· Blue's tab";
  - the conversation;
  - a box with a "To:" picker listing your existing agents (newest first) and "New agent".
- **A second fix for the delegation complaint.** Pick the agent in To:, type, and press Enter. The Brain doesn't have to guess.
- **Starting in your tab is a hand-over, so it takes a click.**
  - On your own tab with "New agent" picked, Enter waits until you choose "Start here · <site>" or "Start in its own tabs".
  - With an existing agent picked, a separate button hands the tab over.
  - Typing never hands over a tab.
- **No `debugger` permission** (the earlier spec's Decision 5 still holds). The server matches your tab by its address and window. If two tabs in that window show the same address, it refuses instead of guessing.
- **Cards in the chat.**
  - Permission cards offer Allow once and Deny. Always allow stays in the app's Tools.
  - Bot-check cards offer Show me and Continue, with no Skip.
- **Tighter rules for the watcher.**
  - The server switches to a fixed list of what the watcher may send, which closes the gap above.
  - Watcher pages stop receiving the id of every tab.
- **New promise text.** The watcher still never presses Send. An agent works in one of your tabs only after you click Start here or Hand over.
- **Later: a Chrome copy of the watcher.** Loaded from the same folder, Chrome gets the same extension id as Brave (measured), so a Chrome copy needs its own folder.

## What we will NOT do

- **We will never auto-click, answer, suppress or hide Brave's or Chrome's "Allow remote debugging?" prompt.**
- **We will never hide or close the "controlled by automated test software" bar.** You may close it yourself. With fewer connections it simply comes back less often.
- We will never spoof or disguise the browser, bypass or solve bot checks, or type passwords.
- The Brain will never hand over or take back a tab, answer a permission or bot check, or approve or send anything.
- There is no "move this agent to another profile", because cookies and logins differ per profile. Instead, after your click, we offer "Restart in <browser · profile>".
- We will never connect to a browser you didn't pick.

## What stays the same

- The Brain only proposes. Nothing runs without your Start or Send, or a plain yes.
- Agents use only tabs they open or tabs you hand them. Hand over and Take back are clicks.
- ⚠ steps (Send, Buy, Delete) still need your OK. At a bot check, the agent stops and tells you.
- Brave's switch and its Allow question stay. Unticking the switch still cuts everything off.
- The watcher reads and drafts, and you press Send.
- Page text is data. Pages set text with `textContent` only.
- The Docker sandbox doesn't change.

## Findings that change earlier decisions

These findings overturn or change things we decided before:

- **Agent tabs don't open "in Brave's default profile".** The everyday-brave spec says they do (`docs/superpowers/specs/2026-10-02-everyday-brave-design.md:806-807`), and it lists profile choice as out of scope (`:969`). In fact they open in whichever profile you clicked last.
  - Browser automation can't target a specific profile. It fails with "Failed to find browser context" in Chrome 154 and Brave 152, and it has no window option.
  - So "switch any time" works for the browser. A profile works only if the watcher is loaded in it.
- **Decision 12 (`:445-461`) and the switch text (`app/run.py:76-84`) both change.** Today they tell you to expect a question per agent. With the relay it's one per app run. Both texts must change, or you may click Deny on the one question that matters.
- **Decision 3 (`:305-306`, "don't move the pages into the watcher") is replaced** by the side chat you approved. Decision 5 (no `debugger` permission in the watcher) stays.
- **The watcher's "never sends anything" promise needs new words.** The watcher itself still never presses Send. Agents started from it can act in a tab you handed over, through the ⚠ step.
- **AI Browser's own Chrome goes away.** Today agents use it by default (`bridge.py:297`, `AIB_BROWSER=app`). The app window must have no debugging port, so agents can no longer browse there (see question 4).
- **"Tell the Brain" changes.** In the inbox it starts an agent at once by design (`docs/superpowers/specs/2026-10-02-brain-design.md:354`). It becomes a card.
- **Voice can now talk to one agent.** The voice spec left "talking to one agent" for later (`2026-10-02-voice-input-design.md:926-927`). It is in scope now, with the same confirm rule.

## The risks

Each part brings its own risks:

- **One Allow covers more.**
  - For the whole app run, any program running as you that can read AI Browser's token files can use Brave without a new question. Those files are readable only by you.
  - Mitigations: tokens change every run; the relay enforces which tabs each client may use; AI Home lists who is connected, with a Disconnect button.
- **The app becomes a single point of failure.** If the app crashes, every agent loses the browser at once. Engines must reconnect cleanly, and sessions must never quietly connect on their own.
- **Other tools still ask.** Other browser tools in a Claude Code session (chrome-devtools-mcp, Playwright) still open their own connections. Those ask again and bring the bar back.
- **The relay can fall behind the code.** A new browser command used by the engine fails through the relay until we add it to its allowed list. Tests must run through the relay.
- **Not yet counted by hand.** The "one Allow" and "the bar stays closed" claims come from Chromium's source and a headless probe. Nobody has counted them in your real Brave 152 yet. That's a hand check after wave 2.
- **App window: the Dock and the menu bar show the host browser.** You'll see Chrome or Brave, not "AI Browser", until the app is packaged.
- **App window: macOS asks for the mic once.** It asks once for whichever browser draws the window.
- **App window: shared local cookies.** Cookies on 127.0.0.1 reach every port (measured), so the app window must never load other local pages.
- **Profiles: we read Chromium's files.** Local State and Secure Preferences are internal Chromium files, not an API. Every read must fail safely.
- **Profiles: emails stay local.** Local State holds your account email, which must never leave your computer.
- **Profiles: one more step each.** Each profile you want agents in needs its own watcher copy.
- **Side chat: a Brave crash.** Brave crashes when an extension opens a side panel for a popup window (brave/brave-browser#59256, still open). We open the panel only for normal windows.
- **Side chat: more power next to your mail.** The watcher runs beside Gmail and Slack, and it gains the power to start agents in your tabs. Mitigations: the fixed list of allowed messages, a click for every hand-over, and no message listener in the panel.
- **Brain: a misheard transcript.** It could now reach an agent that has tools. The card shows the exact words, you can edit them, and nothing goes without Send or yes.
- **Brain: steering through page text.** Page text in an agent's status could nudge which agent Claude picks. A number or colour you say wins, and the card names the agent before you confirm.
- **Brain: colours repeat after 7 agents.** So "the blue one" asks back instead of guessing.

## The build order

The waves are ordered so that two pieces of work never edit the same file at once.

- **Wave 1: the fixes you're waiting for (about 3-4 days, two tracks in parallel)**
  - **1A, Brain delegation:**
    - `brain/talk.py`, `brain/service.py`;
    - one sentence in `app/bridge.py`;
    - a "queued" count in `app/agents.py`;
    - numbers and "Your tabs" in `mission.js`, `scene.js`, `tablist.js`;
    - tests in `test_brain_talk.py`, `test_talk.py`, `test_bridge.py`.

    It lands before wave 3 moves these pages. If it needs a `server.py` change, that lands after 1B.
  - **1B, safety fixes:**
    - the watcher's list of allowed messages in `server.py`, with one table test covering every message type;
    - no tab ids sent to the watcher;
    - in `app/tabs.py` and `bravelink.py`: titles only for the watcher's profile, a count for the rest.
- **Wave 2: one shared connection (about 4-5 days)**
  - **2A, the relay:**
    - the new `app/cdprelay.py`;
    - `bravelink.py`, `tabs.py`, `cdp.py`, `engine.py`, `agentlink.py`;
    - the `/cdp` route and per-agent tokens in `server.py`;
    - environment wiring in `run.py` and `bridge.py`;
    - the new switch text and spec Decision 12.
  - **2B, in parallel, browser detection:** a new, pure `browsers.py`, plus `platforms.py`, tested with sample files. It touches nothing 2A touches.
  - **Then your hand check:**
    - start two agents and count one Allow;
    - close the bar, start another agent, and the bar stays closed.
- **Wave 3: the app window (about 5-7 days, alone, because it rewrites `run.py` and `server.py`)**
  - the new `app/window.py`;
  - in `server.py`: the page routes, Host check, content policy, one-time code and cookie;
  - pages move to `app/ui/`, and `link.js` keeps the watcher's path;
  - AI Browser's Chrome and extension retire;
  - the test fixture is rebuilt.
- **Wave 4: browser and profile choice (about 3-4 days, my estimate)**
  - in `chrome.py`: the saved setting, used in place of "first switch on";
  - the agent's profile passed in through `run.py`;
  - in `grouping.py` and `engine.py`: tabs opened by the watcher;
  - `open_tab` in `watcher/worker.js`;
  - one connection per browser;
  - the Settings page and the AI Home chip.
- **Wave 5: the side chat (about 4-5 days)**
  - `watcher/manifest.json`, `panel.*`, `worker.js`;
  - shared `chat.js` and `check.js` via `brain/watcher.py:20`;
  - Start here, Hand here and Take back in `server.py`;
  - the promise text in five places;
  - retiring `extension/panel.*`;
  - the Chrome copy comes later.

The side chat goes last because it needs the watcher rules from wave 1, the relay's tab rules from wave 2 and the per-profile watchers from wave 4.

## Defaults we'll take unless you say otherwise

- Agent numbers stay fixed for the run. They don't renumber when an agent closes.
- Closing the app window stops the app and its agents, as today.
- The app window starts with the autoplay flag, so Mission Control can speak without a click. The flag applies only to AI Browser's own window profile.
- The "ai" keyword moves to Brave, through the watcher.
- The side chat offers only Allow once and Deny. Always allow stays in the app's Tools.
- The voice can't stop or close agents.

One note on testing: a throwaway Chrome used in testing may have made macOS show "Google Chrome would like to access the microphone". Clicking "Don't Allow" is fine.

## Questions for you

1. **Which browser should draw the app window on your Mac?** This is only the app's own window. Agents still use Brave.
   - **Recommended: Google Chrome.**
     - It's kept apart from your Brave, so links you click in other apps never land in it.
     - The cost: the Dock shows a Chrome icon while AI Browser is open.
   - **Brave, with its own profile.**
     - You'd see a second Brave icon.
     - Links from other apps might open in the app window. We didn't test this, to stay away from your real Brave.
   - You can change it in Settings any time.
2. **Which of your two Brave profiles (Default, Profile 1) should agents use?**
   - **Recommended:** the one where you're signed in to the sites agents need. You'd load the watcher there once.
   - Load the watcher in both, and switch with the chip in AI Home.
   - No pinning: tabs follow the profile you used last, as today.
3. **Should the app hold Brave's connection for its whole run, and should Claude Code sessions use it?**
   - **Recommended: yes to both.**
     - You get one Allow per run, and the bar stays closed once you close it.
     - Sessions always use your chosen browser, never Chrome by accident.
     - The cost: any program running as you that can read AI Browser's token files can use Brave without a new question.
   - **Drop the connection after some idle minutes.** You'd get one more Allow next time, and the bar may come back.
   - **Let sessions keep connecting on their own.** That means one Allow per session, and they may still pick Chrome.
4. **The app window has no debugging port, so agents can no longer browse in AI Browser's own Chrome. What should replace it?**
   - **Recommended: drop it.** Agents use your chosen browser or the Docker sandbox.
   - **Keep an opt-in "separate agent browser".** It shows the automation bar, and Google refuses sign-in there.

## The user's answers (2026-10-03)

- **App window on the Mac:** Google Chrome (Recommended), changeable in Settings.
- **Brave profile for agents:** the one the user is signed in on (Recommended), picked in Settings; the watcher is loaded in that profile.
- **Connection:** yes to both (Recommended): the app holds Brave's connection for its whole run, and Claude Code sessions go through it.
- **AI Browser's own Chrome for agents:** drop it (Recommended): agents use the chosen browser, or the Docker sandbox.
- Earlier the same day: "App window, no browser look", "Default in Settings, switch any time", "Side chat into the watcher extension".
- The process: as for the previous project, the user approved the design in chat; specs and plans are written and reviewed by agents, then built in waves without a user review round.
