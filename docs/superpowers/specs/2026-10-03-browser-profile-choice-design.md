# Choosing where agents browse: browser and profile

Date: 2026-10-03.

## Status

Status: the user approved the design in chat and answered its four questions; this spec was written and reviewed by agents without a user review round.

**The user's choice,** asked which of their two Brave profiles agents should use (question 2 of the brief,
`docs/superpowers/specs/2026-10-03-app-as-an-app-overview.md:284-287`, answered at `:302`): **"the one the user is signed
in on (Recommended), picked in Settings; the watcher is loaded in that profile."** Earlier the same day: "Default in
Settings, switch any time" (`:305`). This is section 4 of the brief (`:109-129`), wave 4 of its build order (`:246-252`).

**Why this project.** Each complaint has a cause in the code:
- **Agent tabs open in whichever profile the user clicked last.** `Browser.open_worker` sends `Target.createTarget`
  with only the placer's parameters (`browser.py:423-434`), and `Placer.create_params` never names a profile
  (`grouping.py:44-50`). Measured in throwaway Chrome 154 and Brave 152, each with two profiles.
- **Grouping then fails without a word** in a profile that has no watcher. A watcher looks tabs up with
  `chrome.tabs.query({})` (`watcher/groups.js:52`), which sees only its own profile's tabs (measured).
- **Claude Code sessions can land in Chrome.** They take the first browser whose switch answers, Brave first, and look
  again on every connect and for every name (`chrome.py:55-63`, `engine.py:193`, `:291-292`). While Brave restarts,
  that is Chrome.
- **AI Home's tab list shows other profiles' and private windows' titles** as "you" rows (`app/tabs.py:65-70`,
  `app/bravelink.py:122-133`). Wave 1B narrows this; this spec finishes it.

**What was measured** (the investigation, `2026-10-03-app-as-an-app-investigation.json`, key `browsers`; probe scripts in
`/private/tmp/claude-501/profile-probe/`, all against throwaway browsers, never the user's):
- **CDP can't open a tab in a chosen profile.** `Target.getBrowserContexts` lists no real profile, only a
  `defaultBrowserContextId`, which is the profile used last. `createTarget` with another real profile's context fails
  with "Failed to find browser context" in Chrome 154 and Brave 152. It has no `windowId` parameter.
- **One connection sees every profile.** One debugging endpoint lists every profile's pages, each with its
  `browserContextId`. So one Allow covers every profile of that browser; another browser needs its own.
- **An extension can place a tab exactly.** `chrome.tabs.create({active: false})` from an extension lands in the
  extension's own profile, whatever profile was used last, and focus doesn't move (probe4.py, Brave 152). Over CDP the
  tab shows its marker address and that profile's context.
- **Which profile holds which watcher is in files.** An extension's service worker is a CDP target with its profile's
  context. Each profile's `Secure Preferences` records the unpacked folders loaded there
  (`extensions.settings.<id>.path`, `disable_reasons`).
- **Profiles are listed in `Local State`** (`profile.info_cache`, ordered by `profile.profiles_order`): name, colour,
  `is_ephemeral`. Its `user_name` and `gaia_name` can hold the signed-in email. It lags a live browser: a new profile
  may appear late.
- **One folder, one id, everywhere.** The same unpacked folder gets the same extension id in two profiles, and even in
  Brave and Chrome (measured, Brave 1.94 and Chrome 154). One folder can't tell profiles apart.
- **Private windows** have their own context. A context-less `createTarget` never went into one (probe5.py).
- **Two-profile tests need a visible browser:** headless Chrome ignored a second `--profile-directory`.

**Builds on** (merged before this wave starts):
- **Wave 1B, watcher safety** (`2026-10-03-watcher-safety-design.md`):
  - `MESSAGE_RULES` and `may_send(role, message)`: what each origin may send; `WATCHER_RECEIVES` and `for_watcher`:
    what a watcher socket gets;
  - `TabWatch` keeps each page's `context`, the service-worker targets (`worker_contexts(extension_id)`) and the
    `default_context`;
  - `BraveLink(folder, watcher_id)`, `agents_context()` and `scope()`, and the `tabs` message's
    `tab_scope {"profile": "watcher" | "last_used" | "none", "elsewhere": n}`. Its Decision 7 hands wave 4 the job of
    making `agents_context()` the chosen profile's, and `watcher_id` a set of ids.
- **Wave 2A, the relay** (`2026-10-03-cdp-relay-design.md`):
  - `app/cdprelay.py`: one `Relay(folder, tokens)` per browser folder, owned by `BraveLink.relay`, with its grants
    (`grants`, `own_targets`, `on_grant`), `may_open`, and `open(why, identity)`, the only thing that ever asks Brave;
  - its route choice for a Claude Code session (its Decision 13), which this spec changes (Decision 15);
  - `Tokens` (`mint`, `check`, `who`): a token per agent and per session; `/agent-hello` answers `{"cdp_token"}`;
  - `TabWatch` as the app's privileged in-process client (`relay.local()`);
  - link.json's `cdp` and `browser_dir`;
  - the rule that the app opens the upstream only right after something the user did. Its out-of-scope list hands
    wave 4 `Relay.assign(target, identity)` and one upstream per browser.
- **Wave 2B, browser detection** (`2026-10-03-browser-detection-design.md`): the pure `browsers.py` and the table in
  `platforms.py`. This spec uses:
  - `platforms.KNOWN_BROWSERS` (`BrowserFacts` rows, with the `agents` flag: offered under "Where agents browse");
  - `browsers.installed()` (`Installed`: `id`, `name`, `agents`, `data_dir`, `inspect_address`), `os_default()`,
    `by_id()`, `data_dir()`, `for_data_dir()` and `all_data_dirs()`;
  - `browsers.profiles(data_dir)` (`Profile`: `folder`, `name`, `color`, `last_used`; never an email, and no "signed
    in" flag);
  - `browsers.watcher_places(data_dir, watchers)` (`WatcherPlace`: `profile`, `extension_id`);
  - `browsers.state(data_dir)` (`not_running`, `switch_off`, `switch_on`);
  - `browsers.detect(watchers)` and `browsers.public(found, connected)`, the fixed shape for pages, with `watcher` and
    `shared_watcher` per profile.
- **Wave 3, the app window** (`2026-10-03-app-window-design.md`):
  - the pages served from `app/ui/`, and the Settings window (`/settings`, `ui/settings.html`, `ui/settings.js`) with
    one section, **App window**. It says "Wave 4 adds 'Where agents browse' to the same page";
  - `src/ai_browser/settings.py`: `read_settings(home)` and `write_setting(home, key, value)` for `<home>/settings.json`,
    written so that wave 4 imports them;
  - `extension_id_for` moved to `src/ai_browser/extension_id.py`, and `AppServer.allow_watcher(origin)`;
  - the watcher's `ai` keyword (`ai_keyword`), and `open_url`, which opens websites in the agents' browser;
  - the end of AI Browser's own Chrome and of the engine's `app` mode: `browser.kind` is always "brave".
- **The everyday-Brave spec:** markers, groups, hand-over, `BraveLink`.

**Comes after it:** wave 5, the side chat (`2026-10-03-side-chat-design.md`), runs one chat per profile's watcher. It
calls these by name, and this spec keeps the names:
- `place_of(origin)`: a watcher copy's browser and profile;
- `AgentManager.create(..., place=…)` and `Agent.place`;
- `Watchers` and `WatcherConn`, one `GroupKeeper` per copy's connection, and `Watchers.connections()`;
- `InstanceLink` (one per browser) with `targets_showing(url)` and `context_of(target)`, and
  `InstanceLinks.link_for(place)`;
- the tab ids in `open_tab`'s answers.

Wave 5 keeps this spec's rule for where tasks go: a task started from any chat uses the current place, and **Start
here** takes the handed tab's place (Decision 3), which wave 5 allows only in the current place (its Decision 13).

**Supersedes:**
- **everyday-brave `:806-807`** ("its tabs open in Brave's default profile"): wrong. They open in the profile used last.
  This spec pins them with the watcher.
- **everyday-brave `:964` and `:969`** (no switch in AI Home; choosing a profile out of scope): both are now in scope.
- **everyday-brave Decision 13, step 2** (`:470-473`, "the first candidate whose switch is on"): removed (Decision 15).
- **The docstring at `grouping.py:8-9`** ("they open in the browser's default profile"): corrected.
- **Wave 1B's `tab_scope.profile` value `"watcher"`:** replaced by `"chosen"` (Decision 10).
- **Wave 2A, Decision 13, step 2** ("`AIB_CHROME_DIR` names another folder: connect directly"): a session now goes
  through the relay to its own place's browser whenever the app can hold that browser. It connects directly only when
  the app can't (Decision 15).
- **Wave 2A's browser name from link.json's `browser_dir`:** a session names the browser of its own place.

Line numbers are at HEAD (commit 946d5f0). Waves 1-3 move some of them; the names stay.

## Goal and success criteria

The user picks, once, the browser and the profile where agents browse. From then on every new agent's tabs open in that
profile, grouped and in the background, whichever profile the user happens to be in. Changing the choice affects new
work only.

Success means:
1. **Settings shows the choices.** Settings → **Where agents browse** shows:
   - a card for each installed browser, found by its installed app, never by a leftover data folder;
   - each card's state: switch on, switch off, not running, connected (or asking, not allowed, closed);
   - under the chosen browser, its profiles with name and colour, never an email;
   - for each profile, whether its watcher is there.
2. **Detection never asks.** Building that page reads files and makes TCP checks only. A test server sees no HTTP
   request and no WebSocket handshake.
3. **The choice is saved and kept.**
   - Saving writes `<home>/settings.json`.
   - An agent created afterwards gets the new place. One already running keeps its own until it closes.
   - A Claude Code session keeps the place it found at its first browser call until its process ends.
4. **Tabs land in the chosen profile.** With the app running and the watcher connected in the chosen profile:
   - every tab an agent opens itself is opened by that watcher;
   - it lands in that profile, even when the user last clicked in another one;
   - it sits in the agent's group, in the background;
   - the user's focused tab doesn't change;
   - no agent sends `Target.createTarget` in this case.
5. **The fallback is honest.** Without the app, or without the watcher in that profile, the tab opens in the profile
   used last. The tool result says so, once, and the session's status line says why. The user's own pages (AI Home,
   Settings) name the profile; what reaches Claude never does.
6. **One watcher copy per profile.**
   - **Set it up** on a profile makes that profile's own watcher folder and shows it in Finder or File Explorer.
   - After one **Load unpacked** in that profile, the row says "✓ watcher".
   - A copy loaded in two profiles is never used to place tabs, and the row says how to fix it.
7. **The AI Home chip.**
   - The browser card's header reads like "Brave · Personal ▾".
   - Picking another profile of the same browser is instant and opens no connection.
   - Picking another browser whose switch is on connects to it once, right after the click. That browser asks "Allow
     remote debugging?" once.
8. **The tab list.**
   - It lists the chosen profile's tabs, plus the agents' own tabs anywhere.
   - Everything else is one number, as wave 1B words it: "4 more tabs in other profiles or private windows: not shown
     here."
   - A private window's tab is never listed.
9. **Restart in.** An agent whose place differs from the current choice offers **Restart in Chrome · Work**. One click
   stops it (its tabs stay open) and starts a new agent with the same words in the current place.
10. **One relay connection per browser.**
    - At start the app connects to the chosen browser only.
    - After a switch to another browser, the old browser's connection stays while one of its agents or sessions lives.
      It closes after the last one ends.
    - The app never connects to a browser nobody picked.
11. **No more browser hopping.** Which browser a session uses no longer depends on whose switch answers.
12. **Names stay on this computer.** Profile names, colours and emails never appear in a tool result, an agent's
    prompt, the Brain's state, the terminal's output, or anything sent to Claude. Emails are never read into the app
    at all.

## What the user sees

### Settings → Where agents browse

The second section of the Settings window (wave 3), under **App window**. It has three parts.

**1. A row of browser cards.** One per installed browser:
- **On each card:**
  - its name (Brave, Chrome, Chrome Beta…) with a plain generic glyph;
  - a state chip: **switch on**, **switch off**, **not running** or **connected**, and while the app connects,
    **waiting for Allow**, **not allowed** or **closed**;
  - its number of profiles;
  - the number of agents at work there, when any.
- **A detected browser agents can't use yet** (Edge, Arc and Vivaldi: wave 2B lists them with `agents` false) shows
  greyed with "not supported yet". It can't be picked.
- **A card whose switch is off** opens to show that browser's three steps. They use its own inspect address
  (`brave://inspect/#remote-debugging`, `chrome://inspect/#remote-debugging`). Under them come the warning sentences
  setup already has (`app/setup.html`, `#switch`; `ui/setup.html` after wave 3), with the browser's name.

**2. Under the selected browser, its profiles.** Read from that browser's `Local State`. Each row shows:
- a colour dot and the profile's name, and "used last" on the profile Brave used last (never an email; wave 2B reads
  no account field);
- the watcher's state there:
  - **✓ watcher**;
  - **Needs the watcher (once) · Set it up**;
  - **Watcher loaded, not connected: open a Brave window in this profile**;
  - **This watcher folder is loaded in two profiles: remove it from one in brave://extensions**;
- how many agents are at work there;
- a **Use this profile** choice. The current one is marked. When the user never picked one, the mark reads "chosen
  for you".

**3. Under the list, in plain words** (with the selected browser's name in place of Brave):
- "Switching profile in Brave needs no new Allow."
- "Switching to another browser: it asks "Allow remote debugging?" once, right after you switch. Agents already at work
  stay where they are."
- "While agents work in two browsers, each shows its own "controlled by automated test software" bar."
- "AI Browser only reads files and checks a port to show this page. It connects only when AI Browser starts, when you
  click Connect, give an agent a task or switch browser, and when you ask Claude Code to browse."
- "Names and colours come from Brave's own files on this computer. AI Browser never shows or sends the email you are
  signed in with, and never sends profile names to Claude."

Picking a profile or a browser saves at once. There is no separate Save button. A browser whose switch is off, or
that isn't running, can be picked too: it is saved, nothing connects, and its card shows the steps.

### The first run

Nothing is saved until the user picks. Until then the app chooses for them:
- **the browser:** the computer's default browser if it is installed and agents can use it (Brave on this Mac), else
  the first installed one they can use, Brave before Chrome;
- **the profile:** the one where the watcher is already loaded, else the profile Brave used last.

AI Home's chip shows that place with "(chosen for you)". The browser card adds: "Pick the profile you're signed in on in
Settings." This matches the user's answer: the profile they're signed in on, picked in Settings.

### Setting up the watcher in another profile

**Set it up** on a profile row:
1. The app makes that profile's own copy of the watcher, a folder such as `~/.ai-browser/app/watchers/brave-profile-1`,
   and shows it in Finder (File Explorer on Windows).
2. The row shows the steps:
   1. "In Brave, switch to the **Work** profile (click your profile picture at the top right)."
   2. "Open brave://extensions and turn on **Developer mode**."
   3. "Drag the folder onto that page (or **Load unpacked** and pick it)."
   4. The folder's path, in a box the user can copy.
3. Once Brave records the copy and its worker connects, the row turns to **✓ watcher**. The app reads Brave's files
   again when the copy connects, and a few times in the next 15 s if Brave hasn't written them yet (Decision 8). The
   page doesn't poll.

The app never opens Brave, never switches the user's profile, and never loads an extension itself.

### The chip in AI Home

The browser card's title becomes a chip: **Brave · Personal ▾**, with the profile's colour dot. Its menu:
- **New agents browse in:** the profiles of the current browser.
  - One click switches. It is instant and asks nothing.
  - A profile without its watcher reads "needs the watcher". Clicking it opens the Settings window at that profile
    (`/settings#where`) instead of switching.
- **The other installed browsers**, each with its state:
  - switch on: "Chrome · it will ask Allow once". Clicking switches to its profile with the watcher, else its profile
    used last.
  - switch off or not running: "Chrome · Show me how". Clicking opens Settings at that card.
- **Settings…**

After a switch, one line shows under the card until the user dismisses it: "New agents use Chrome · Work. 2 running
agents stay in Brave · Personal."

The browser card's other lines stay as they are today (`app/extension/home.js:218-252`, moved to `ui/home.js` by wave
3). One line changes. When the watcher isn't connected in the chosen profile, the card says "Agents' tabs open in
whichever Brave profile you used last: the watcher isn't in Personal yet. **Set it up**." In place of today's "tab groups
off" text, it gives the reason for the chosen profile.

### An agent at work

1. The user gives a task. The agent's place is fixed now: the current browser and profile.
2. When the agent first opens a page, the watcher in that profile opens a blank tab:
   - in the background;
   - in the window where that agent's group already is, else in that profile's most recent normal window;
   - grouped at once under the agent's name and colour.
3. The engine attaches to that tab and loads the page. The user keeps working, in any profile; nothing comes to the
   front.
4. **If that profile has no window open,** the watcher opens a new window for it, behind the user's windows (Decision
   5). The agent's result says "a new Brave window was opened for its tab".

Tabs the agent's pages open stay with their opener, in the same profile (Chromium does this), and join its group as
today.

### Without the watcher in that profile

If the app isn't running, or the chosen profile's watcher isn't connected, or it doesn't answer in time:
- the tab opens as today: in the profile Brave used last, grouped there if that profile has a watcher, else in a window
  of its own;
- the engine reads where the tab landed and says so, once per session, in that call's result (Messages / interfaces,
  Texts);
- its status line says why: "its tabs open in the Brave profile the user used last: the watcher isn't in the chosen
  profile".

AI Home marks such a tab's row "in another profile" when the app can tell: the agent's place has a copy connected, and
the tab's context isn't that copy's (the row's `other_profile` flag, Decision 10).

### The tab list

Wave 1B's list stays; only its profile changes. AI Home's **Tabs** list shows:
- **the chosen profile's tabs:** web pages and the agents' blank tabs, with owner chips as today;
- **the agents', Claude Code's and handed tabs in any other place,** with a small place chip ("Brave · Work");
- **one line for the rest,** in wave 1B's words: "4 more tabs in other profiles or private windows: not shown here."

When the chosen profile's watcher isn't connected, the app can't tell which tabs are that profile's. The list then
falls back as wave 1B's does, to the profile Brave used last, which is where agents' tabs go too (Decision 6). Its line
reads: "Showing the Brave profile you used last: the watcher isn't in Personal yet, so agents' tabs open there too."

Private windows never appear as rows.

### Switching

- **Another profile, same browser:**
  - instant, and no question;
  - the tab list re-filters at once;
  - new agents and new Claude Code sessions use the new profile;
  - running agents keep theirs.
- **Another browser:**
  - the click is the user's action, so the app connects to that browser right away;
  - if its switch is on, it asks "Allow remote debugging?" once;
  - the card shows **waiting for Allow** for up to 60 s, as today (`app/bravelink.py:21`);
  - running agents keep working in the old browser. Its connection, and its automation bar, stay until the last of
    them closes.
- **Where new tasks go:** tasks started from AI Home, Mission Control, the Brain, workflows and the watcher's `ai`
  keyword (from any copy, in any profile) use the current place. The one exception is a task started in a handed tab
  (Decision 3). Wave 5's chat keeps this rule (its Decision 13).

### Restart in

An agent whose place differs from the current one shows, in its AI Home row and in its Mission Control drawer:
- a place chip ("Brave · Personal");
- a button, **Restart in Chrome · Work**, with the line "Stops this agent and starts a new one there with the same
  task. Its tabs here stay open."

One click:
1. stops the old agent: its process and tabs stay, and the user closes it when done with it;
2. starts a new agent with the old one's first words, skills, model and tool list, in the current place;
3. adds a line to the old agent's chat view: "Restarted as 5 · Fix the footer in Chrome · Work." It is a line on the
   user's own pages only. It is never sent to the old agent's Claude, because it names a profile (Decision 16).

Tabs handed to the old agent are not carried over: they belong to the old profile. The new agent's first message has
no handed-tab line either.

### Claude Code sessions

- A session reads the saved choice at its first browser call and keeps it until its process ends. A switch in Settings
  never moves it.
- **`AIB_CHROME_DIR` still wins.** A session whose environment sets it (the repo's `.mcp.json` sets it to Brave's
  folder today) uses that browser whatever Settings says. It follows Settings' profile while Settings names the same
  browser. The README says: remove `AIB_CHROME_DIR` to follow Settings.
- **While the app runs:** it goes through the relay to its place's browser, and its tabs open in that profile through
  the watcher, grouped "Claude Code". That browser may be another one than the current place's (an `AIB_CHROME_DIR`
  naming Chrome, say). The app then connects to it on the session's first command, with that browser's own Allow.
- **When the app can't hold that browser** (an `AIB_CHROME_DIR` that isn't an installed browser offered to agents,
  such as a test's throwaway Chrome): the session connects directly, as wave 2A does for such a folder.
- **Without the app:** it connects to its place's browser directly (one Allow, as today). Its tabs open in the profile
  used last, and its status line says so.
- It never picks a browser because that browser's switch answered.

## Decisions (with reasons)

### 1. A place is one browser instance and one profile folder

- **What:** `Place(browser, user_data_dir, profile)`:
  - `browser` is the id of a `platforms.KNOWN_BROWSERS` row offered to agents ("brave", "chrome", "chrome-beta"…).
    It is `""` only for an `AIB_CHROME_DIR` that no known browser owns (a test's throwaway Chrome). Such a place is
    never saved, never offered, and never held by the app;
  - `user_data_dir` is that browser's folder of profiles on this computer;
  - `profile` is a profile folder name ("Default", "Profile 1"), never a display name.
- **Why:**
  - the folder is what Brave's files and CDP agree on;
  - a display name can change or repeat;
  - one instance means one debugging endpoint, so one relay upstream (Decision 11).

### 2. Saved in `<home>/settings.json`; chosen for the user until they pick

- **The file:**
  - one key, `agents_browser`, read and written through wave 3's `settings.read_settings` and
    `settings.write_setting` (atomic, mode 0600, other keys kept), so one reader and one writer touch the file;
  - only the app writes it; sessions only read it;
  - not through wave 3's `settings_set` message: a place needs detection to check it, and a browser switch connects
    (Decision 12). It has its own message, `place_set`.
- **What counts as a valid saved place:**
  - its browser is installed (`browsers.installed()`) and its row has `agents` true;
  - its `user_data_dir` is that row's `data_dir`, compared by `places.same_folder`: real paths, and case-blind on
    Windows, the rule of `chrome._same_folder` (`chrome.py:133-138`) and of wave 2B's `for_data_dir`;
  - its profile is in `browsers.profiles(data_dir)`, which already drops System, Guest, ephemeral, missing and
    oddly named folders.
  - If `Local State` can't be read, the profile folder must exist and the name must be a plain folder name: no path
    separator, no `..`.

  Anything else is ignored, and the place is chosen for the user.
- **Chosen for the user:** `places.default_place()`, as wave 2B suggests:
  - the browser: the row `browsers.os_default()` names, if installed with `agents` true; else the first installed row
    with `agents` true, in table order (the Brave family first); else Brave's folder, so an error can name it;
  - the profile: the one profile where `browsers.watcher_places` finds the primary copy enabled (not when it is in
    two), else the profile marked `last_used`, else "Default";
  - for Brave's folder when no browser is installed, the profile is "Default", and nothing in that folder is read:
    detection looks at installed apps, never at a leftover data folder (and in tests that folder is the real one).
- **Why no automatic save:** a saved file means the user chose. Until they do, the page says "chosen for you", and the
  default follows the watcher if the user moves it.

### 3. Agents keep their place for life

- **Agents:**
  - `AgentManager.create` copies the current place into the agent (`Agent.place`);
  - it adds `AIB_CHROME_DIR` and a new `AIB_CHROME_PROFILE` to that agent's env, which today is merged once, at
    creation (`app/agents.py:143`);
  - nothing changes them afterwards, through New chat, a crash or a reconnect.
- **The one exception: an agent started in a tab the user handed it** (Hand over → New agent, and wave 5's Start here)
  takes that tab's place, when the app knows which profile the tab is in. Its own tabs then sit beside the handed one,
  with the same logins.
  - The app knows a tab's profile only through a copy connected there (Decision 8). A tab in a profile with no copy
    can't be mapped, so its agent gets the current place.
  - In this wave AI Home lists the chosen profile's tabs, so this is usually the same place. Wave 5 relies on the rule.
- **Claude Code sessions:**
  - `Engine` resolves the place once, at its first `_start_chrome`, and keeps it for the process's life;
  - today it asks `own_browser_dir()` at every connect and again for every name (`engine.py:193`, `:291-292`).
- **Why:** cookies and logins differ per profile and per browser. An agent that moved halfway through a task would act
  under other accounts.

### 4. The watcher in that profile opens the tab (`open_tab`)

- **How:**
  1. The engine asks the app: `POST /agent-open {agent, marker}`. The marker is a fresh `grouping.new_marker()`.
  2. The app finds the watcher connected in that agent's place (Decision 8). It sends
     `open_tab {request, marker, key, title, color}`.
  3. The watcher builds the address itself, `about:blank#aib-<marker>`, and picks a window:
     - the window of the agent's live group (the key's stored group that `live()` still finds,
       `watcher/groups.js:81-89`);
     - else `chrome.windows.getLastFocused({windowTypes: ["normal"]})`, when it isn't private;
     - else the first non-private window of `chrome.windows.getAll({windowTypes: ["normal"]})`;
     - else none (Decision 5).
  4. The watcher calls `chrome.tabs.create({url, active: false, windowId})`, groups the tab in the same step (`put`,
     `watcher/groups.js:91-117`), and answers `opened_tab {request, ok, tab, window, group, new_window}`.
  5. The app looks, through its own privileged view of that browser, for the one target whose URL is that marker
     address. It checks that the target's `browserContextId` is the watcher's own context. It tells the relay the
     target is that agent's (`Relay.assign(target, identity)`, which wave 2A left for this wave). The relay's
     `on_grant` puts AI Home's owner chip, the server remembers the tab id (as `/agent-claim` does,
     `app/server.py:396`), and it answers `{opened: true, target, tab, grouped, new_window}`.
  6. The engine attaches to that target (`Browser._setup_tab`, `browser.py:538-566`) and loads the page as today.
- **Limits:**
  - the app waits at most `OPEN_WAIT` = 2.5 s for steps 2-5;
  - the engine waits at most `ENGINE_OPEN_WAIT` = 3.0 s, then falls back (Decision 6). Its request to the app gets
    that same timeout: today every request to the app stops after 2 s (`agentlink.py:96`), which would cut off the
    app's 2.5 s;
  - an `opened_tab` that comes back after the wait has its tab closed by the app (it is a blank tab nobody uses), so
    no stray blank tab is left. The app finds it with `targets_showing(<that marker address>)` in the watcher's context
    and closes it with `Relay.close_marker` (wave 2A's app client may not close a tab nobody owns, so this is the one
    narrow exception). The marker is secret and used once, so no other tab can match;
  - a target the app assigned after the engine gave up (an answer slower than `ENGINE_OPEN_WAIT`) stays the agent's
    own blank tab, and closes with the agent (wave 2A's `own_targets`);
  - a target in another context than the watcher's is closed (`Relay.close_marker`) and refused as `wrong_profile`. It
    "can't happen", so it is checked.
- **Why:**
  - CDP can't target a profile (measured);
  - an extension's `tabs.create` lands in its own profile without moving focus (measured);
  - the marker is the everyday-Brave mechanism already (Decision 5 there), secret and random, so no page can make the
    app hand some other tab to an agent;
  - the app, not the engine, finds the target, so the engine never needs to see other tabs. The relay keeps hiding the
    user's tabs from agents (wave 2A).
- **The watcher's new power is small:**
  - it opens only `about:blank#aib-<16 hex>`. The app never sends it an address, and a message that carries one is
    refused;
  - it never navigates the tab; the engine loads pages over CDP, through the relay's and `url_problem`'s checks;
  - it never opens a tab in a private window.
- **Rejected:**
  - `createTarget` with the profile's `browserContextId`: fails for any profile but the one used last (measured);
  - focus tricks (activating a window of that profile first): they move the user's focus, and they race the user;
  - `--profile-directory` launches: they start or raise the user's browser;
  - the `debugger` permission in the watcher: everyday-brave Decision 5 still holds.

### 5. A profile with no window: a new window, behind the user's

- **What:** when the watcher's profile has no non-private normal window, it calls
  `chrome.windows.create({url, focused: false, incognito: false, type: "normal"})`. The answer says
  `new_window: true`, and the engine's result says "a new Brave window was opened for its tab".
- **Why:**
  - the alternative is the fallback, which puts the agent in the profile used last, under other logins. That is worse
    than one background window;
  - everyday-brave Decision 9 already opens a window per tab when there are no groups;
  - `focused: false` is the documented way to open an inactive window. Nothing fakes a gesture or moves focus on
    purpose.
- **To check:** whether macOS, or Windows, still brings that window to the front (first task, fact 1). If either does,
  Settings and the card add "A new window for this profile may come to the front."
- **When this happens:** the browser keeps a profile loaded for a while after its last window closes, so its watcher
  can still be connected (first task, fact 4 checks how long).
- **When the profile isn't open at all,** its watcher isn't running, so it isn't connected. That is the fallback
  (Decision 6). The app never launches a profile.

### 6. The fallback: the profile used last, said plainly

- **When:**
  - no app (a lone Claude Code session);
  - the app is running but `/agent-status` says `open: false`;
  - `/agent-open` answers `opened: false`.
- **What:**
  - the engine creates the tab as today (`Placer.create_params`, `grouping.py:44-50`):
    - a marker without `newWindow` when `/agent-status` says `groups`. In this wave that means a copy that can group is
      connected in the profile the browser used last (the link's `default_context`), because a context-less tab
      lands there. A copy in some other profile can't see that tab, and the tab would sit ungrouped in the user's
      window, which is today's silent failure;
    - else `newWindow: true`;
  - the claim goes to the watcher whose context matches the tab's (Decision 9);
  - then the engine reads the tab's context (`Target.getTargetInfo`) and compares it with its place's context (from
    `/agent-status`, when the app knows it) and with this session's earlier tabs;
  - it adds one note to that call's result, the way download notes are added (`_download_notes`,
    `browser.py:370-374`, read into the results at `:761`, `:1096` and `:1107`):
    - only the first time per session;
    - and again if a later tab lands in a different context from the earlier ones.
- **Never:**
  - a retry in another browser or profile;
  - a focus trick;
  - `createTarget` with a `browserContextId`. Wave 2A allows one equal to the context of one of the client's own tabs.
    It works only while that profile is the one used last (measured), and then a tab without one lands there anyway.
    So it adds nothing.

  A future Chromium may let CDP target real profiles. The check after creating stays, so the behaviour stays right
  either way.
- **Why:** the brief's fallback (`overview.md:124`), with the honesty the user asked for: the agent says where the tab
  went.

### 7. One watcher copy per profile, each in its own folder

- **Where:**
  - the primary copy stays at `<home>/app/watcher` (`brain/watcher.py:35`), where the user already loaded it;
  - each other profile's copy goes in `<home>/app/watchers/<slug>`, for example `brave-profile-1`;
  - the slug is the browser id and the profile folder, lower-cased, with anything outside `[a-z0-9]` turned into "-",
    at most 60 characters. It never changes, so the extension id never changes;
  - Chromium's own folder names ("Default", "Profile N") never share a slug. If two listed profiles still would,
    **Set it up** on the second answers `error {"text": "AI Browser can't give this profile a watcher folder of its
    own: please report this"}` and makes nothing.
- **When it is made:**
  - only when the user clicks **Set it up** on a profile that has no copy;
  - at every app start, the primary copy and every folder under `<home>/app/watchers/` are brought up to date
    (`prepare_watcher` with a `folder` argument): files, `build.js`, and `config.json` with this run's address and token;
  - every copy's origin is allowed as a watcher origin (wave 3's `AppServer.allow_watcher(origin)`, which replaced
    `allow_origin`, `app/server.py:178-183`).
- **Why a folder each:**
  - the extension id is a hash of the folder's path (`extension_id_for`, `appbrowser.py:79-85`, moved to
    `extension_id.py` by wave 3). It is the same in every profile, and in Brave and Chrome (measured). One folder can't
    tell profiles apart; a folder per profile can;
  - each copy costs the user one "Load unpacked" in that profile, once. The brief accepted that (`overview.md:125`).
- **Why not inside `<home>/app/watcher`:** `sync_folder` removes every file it doesn't know (`syncdir.py:46-49`), so
  updating the primary copy would delete the others. The primary's folder would also contain them.

### 8. Which profile a watcher is in: its files, then its worker

- **The profile, from the files alone:**
  - for each installed browser offered to agents, `browsers.watcher_places(data_dir, watchers)` reads each profile's
    `Secure Preferences`, then `Preferences`, for every copy's id (`watchers` maps each id to its folder) and counts
    only enabled copies;
  - a copy found in exactly one profile of one browser has that place. Its socket's origin carries that id, so the
    socket comes from there: this is `place_of(origin)`;
  - found in two it is **shared**: never used to place tabs, and its rows say how to fix it. Two profiles of one
    browser are wave 2B's `shared_watcher`. Wave 2B doesn't look across browsers, so `Watchers.refresh` also marks a
    copy enabled in Brave and in Chrome as shared, and the `browsers` view sets `shared_watcher` on both rows;
  - found nowhere yet (Brave writes the file a little after Load unpacked) it is **unknown**.
- **When the files are read:** never on a repeating timer, as wave 2B asks, because the files can be a few MB:
  - when a copy connects; if it is still unknown, again 2 s, 5 s and 15 s later (first task, fact 2, sets these);
  - when a page asks for `browsers`;
  - after `place_set` and `watcher_copy`.
- **The context, from the worker:**
  - wave 1B's `TabWatch.worker_contexts(extension_id)`, on the app's privileged view of the copy's own browser, gives
    the context of the copy's worker, `chrome-extension://<id>/worker.js`. A worker with that id seen in another
    browser's link gives nothing;
  - the watcher keeps a socket open to the app, which keeps its worker alive (the server pings every 20 s,
    `PING_EVERY`, `app/server.py:47`). So while it is connected, its target is there, and the app remembers the
    context for the life of that connection (as wave 1B does);
  - the context needs that browser's link to be connected. Until it is, the copy has a place and no context.
- **What each needs:**
  - a row's ✓ (`live`) needs the place and an open socket;
  - `open_tab`, the tab list's `"chosen"` and the check after opening need the context too. Without it the agent
    falls back (Decision 6);
  - two copies in one profile both work there. The app uses the primary, else the first by slug, and the row says
    "remove the extra copy" (Texts).
- **Never a guess:** a copy in two places, or in none yet, places nothing.
- **Why:** an extension can't learn which profile it is in. The files and the target list are the two facts measured,
  and neither opens a tab.

### 9. The Brain keeps one watcher; every copy places tabs

- **The Brain's role stays with the primary copy:**
  - the watch list, readers, notifications, `open_thread`, `fill_reply`, `permission_request` and `check_request`
    notifications go only to the primary copy's connection;
  - `brain.watcher` and `watcher_seen` follow it alone (`app/server.py:636-643`);
  - a copy never receives `watch_list`, so it registers no readers and the user's mail is read once.
- **The tab role belongs to every copy, the primary included:**
  - `open_tab`, `group_tab` and `ungroup_tabs` go to the copy whose context matches the tab;
  - each copy's connection has its own `GroupKeeper` (`app/groups.py:15-23`), so claims and answers never cross;
  - every copy gets `watcher_hello`, so an older copy reloads itself as the primary does (`watcher/worker.js:86-92`);
  - the browser card's `groups` (`app/server.py:494`) is the current place's copy's `GroupKeeper.available()`, or
    `"no_watcher"` when no copy is connected there.
- **The reports, under wave 1B's rules:** the Brain's reports (`items`, `replied`, `thread`, `filled`,
  `reader_status`) count only from the primary copy's connection. The tab reports (`watcher_caps`, `tab_grouped`,
  `opened_tab`) count from any copy's connection, each into its own `GroupKeeper`.
- **Why:** a single watcher slot where "the latest watcher wins" (`app/server.py:140`, `:638`) would let a copy in
  another profile take the Brain's inbox, or group tabs it can't see. Splitting by role keeps the Brain as it is, and
  sends placement to the one copy that can do it.

### 10. The tab list: wave 1B's, on the chosen profile

- **What changes:** only where `agents_context()` (wave 1B, its Decision 7) looks. In order:
  1. the chosen profile's context, from the copy connected there (Decision 8): `tab_scope.profile` is `"chosen"`;
  2. otherwise the profile Brave used last (`default_context`): `"last_used"`, as in wave 1B;
  3. otherwise none: `"none"`, and no tab of the user's is listed.

  Wave 1B's `"watcher"` (the one watcher's profile) is no longer produced: `"chosen"` takes its place, and the page
  shows no line for it, as it did for `"watcher"`. When the primary copy sits in another profile than the chosen one,
  its profile isn't where agents work, so its tabs aren't listed.
- **What stays as wave 1B built it:**
  - the agents', sessions' and handed tabs are listed in any context;
  - every other web page is one number, `tab_scope.elsewhere`, worded "other profiles or private windows";
  - context ids stay inside the link: rows carry no context.
- **What this adds:**
  - rows owned outside the current place carry a `place` label ("Brave · Work"). It comes from the owner's place,
    never from the page;
  - a row owned by an agent or session carries `other_profile: true` when its place's copy is connected and the tab's
    context isn't that copy's (a fallback tab). It is a flag, not a context id.
- **Why:**
  - the chosen profile is where agents now work, so its tabs are the ones the user may hand over;
  - when the watcher isn't there, agents' tabs fall back to the profile used last (Decision 6), so that is the right
    list to show, as wave 1B reasoned;
  - wave 1B's count wording is honest about private windows. CDP can't tell a private window from another profile,
    so a "profiles only" count would need a guess.

### 11. One relay connection per browser in use

- **`InstanceLinks`:**
  - holds one `InstanceLink` per browser folder in use (the `BraveLink` of waves 1B-3, renamed);
  - each `InstanceLink` owns one `Relay`, so one upstream (wave 2A);
  - each has its own states, `off · ready · asking · connected · refused · lost` (`app/bravelink.py:30`).
- **When each connects:** only right after something the user did, as wave 2A says:
  - at start, only the current place's browser, once (as `app/run.py:233-234` does today);
  - on **Connect** or **Try again**;
  - on a switch to another browser (the click);
  - on an agent's turn, its own place's browser (`agents.on_turn`, `app/server.py:174`, now place-aware);
  - on a session's first command after the user gave it a task (wave 2A's relay table: a session's `/cdp` handshake
    opens its link).

  Everyone waiting on one browser shares one attempt.
- **When a link is made:** at start for the current place; on a switch to another browser; when an agent is created
  in a place whose browser has no link yet (a handed tab's place, Decision 3); and when `/agent-hello` records a
  session's place in such a browser (`InstanceLinks.ensure`). Making a link connects nothing: its relay only looks at
  the switch, by TCP.
- **When each closes:** a browser that isn't the current place closes its upstream, and its link goes, when its last
  agent closes or its last session ends. `InstanceLinks.prune` runs on `agent_closed`, on a session's bye or sweep
  (`app/server.py:450-469`), and after `set_current`.
- **Never:**
  - a connection to a browser that is neither the current place nor the place of a live agent or session;
  - a retry by itself after Deny.
- **Routing:**
  - the server's `/cdp` route binds each client, at its handshake, to the relay of its place's link: an agent's from
    `Agent.place`, a session's from its hello;
  - a client never chooses its upstream;
  - ownership tables are per upstream.
- **Why:** one debugging connection covers every profile of a browser instance, but not another browser (measured).
  This keeps the brief's "one Allow per app run" per browser, and lets running agents finish where they started.

### 12. Switching: a profile is instant, a browser asks once

- **A profile:**
  - the same `InstanceLink` and upstream;
  - no connection, no question;
  - `agents.place` changes, the tab list re-filters, and `browser` and `browsers` are broadcast.
- **A browser:**
  - `InstanceLinks.set_current` makes or reuses that browser's link and connects it now, when its switch is on (the
    link is `ready`, `lost` or `refused`). With the switch off, or the browser not running, nothing connects and the
    card shows the steps;
  - link.json's `browser_dir` (wave 2A) is written again;
  - the old link stays while it is in use (Decision 11).
- **The notice:** "New agents use Chrome · Work. 2 running agents stay in Brave · Personal." The count covers agents
  whose place differs from the new one.
- **Why:** it is exactly what the user approved ("Switching profile is instant and needs no Allow. Switching browser
  asks Allow once in the new browser", `overview.md:127-129`).

### 13. No moving agents: **Restart in**

- **What:**
  - `restart_in {id}` from the app window stops the agent (`AgentManager.stop`, `app/agents.py:171-189`: a waiting
    permission becomes a no, its tabs stay);
  - it creates a new agent with the same first words, skills, model and tool list, in the current place, with no
    `adopt` and no tab line;
  - `Agent` keeps its first words, skills and tool list for this (`task`, `skills`, `servers`; never sent to pages or
    the Brain);
  - the "Restarted as …" line is an event in the old agent's chat view only, never a message to its Claude.
- **Shown only when** the agent's place differs from the current one, and the agent hasn't closed.
- **Why Stop and not Close:** Close would close the old agent's tabs, which may hold what the user wanted to see.
  Leaving it running would do the task twice, in two accounts.
- **Why one click is enough:** the click is the user's, on a button that names the place. The Brain, voice and the
  watcher can't send `restart_in`.
- **Not carried over:** handed tabs (another profile's).

### 14. Hand over stays within one browser

- **Give to <agent>** (`app/extension/tablist.js:54-61`, `ui/tablist.js` after wave 3) lists only agents whose place
  is in the tab's browser.
- Agents in another profile of that browser get a label: "Give to 1 · Fix the footer (in Work)" (the number is wave
  1A's). The handed tab then works under that tab's profile's logins, as it does today.
- The server checks the same rule in `_hand` (`app/server.py:518-529`) and in `new_task` with `adopt` (`:685-695`).
- Mission Control's **Your tabs** (wave 1A, in the agent's drawer) follows it too. For an agent whose place is in
  another browser than the current place's, it shows no rows and one line: "This agent works in Chrome: your tabs here
  are Brave's." For an agent in another profile of the same browser, each **Give to this agent** carries the same "(in
  Work)" label.
- **Why:** an agent's relay client is bound to one browser's upstream (Decision 11). A tab of another browser isn't
  reachable through it.

### 15. `own_browser_dir()` stops following the switch

- **The new order:**
  1. `AIB_CHROME_DIR` (with `AIB_CHROME_PROFILE`, if set);
  2. the saved place;
  3. the place chosen for the user (Decision 2).
- **What goes:** "the first candidate whose switch is on" (`chrome.py:62`).
- `own_browser_dir()` becomes `places.resolve(config.home())[0].user_data_dir`.
- **Naming the browser:** `browser_name` and `inspect_address` come from `browsers.for_data_dir(folder)`'s row, as
  wave 2B suggests. A folder no row owns keeps today's rule (`chrome.py:69-76`): a path with "BraveSoftware" is Brave,
  anything else Chrome. So a test's throwaway folder still says "Chrome", and the hint tests keep passing.
- **The import direction:** `chrome.py` imports `places`; `places.py` imports `browsers`, `platforms`, `settings` and
  `extension_id` (wave 3), never `chrome.py`. That keeps wave 2B's rule against a cycle (its Decision 13).
- **`AIB_CHROME_DIR` stays first.** It is an explicit setting, and the tests rely on it (`tests/conftest.py:60`). The
  repo's `.mcp.json` sets it to Brave's folder today, so the user's sessions follow Settings' profile but not a
  switch to Chrome. The README's own-browser section says so, and says to remove it to follow Settings.
- **A session's route** (wave 2A's Decision 13, changed): with the app running, the session says hello with its place.
  - The app answers with the same place when it can hold that browser: an installed browser offered to agents, and a
    plain profile folder name. The session then goes through the relay, to that browser's link, whether or not it is
    the current place.
  - The app answers `"place": null` for a folder no installed browser offered to agents owns. The session then
    connects directly, as wave 2A's step 2 does, with wave 2A's "not through AI Browser" status line.
  - The session never takes a place from the app: its place is fixed (Decision 3).
- **Why:** following the switch is how sessions land in Chrome while Brave restarts. The place is now a choice. When
  that browser isn't reachable, the error says so and names it, as today (`chrome.py:141-161`).

### 16. Names and colours stay on this computer

- **Emails:** `browsers.profiles` reads no account field, and a name that holds `@` becomes the folder name (wave 2B,
  its Decision 5). So no email reaches the app.
- **Names and colours** go only to the app window's own pages (Settings, AI Home, Mission Control).
- **They never go to:**
  - an engine's tool results or status line ("the chosen profile", "the profile the user used last", never a name or
    a folder);
  - an agent's prompt;
  - the Brain's state (`brain/talk.py:92-102` picks fields one by one and `place` isn't one);
  - the relay's clients;
  - the terminal. Claude Code often runs `ai-browser app` and `doctor` for the user and reads what they print. So
    they name the browser and the profile folder ("Brave · profile folder Profile 1"), never the display name.
- **The watcher** gets no place in this wave (`WATCHER_AGENT_FIELDS` doesn't gain it). Wave 5's chat shows its own
  profile's name on the user's own page, which stays on this computer.
- **Why:** a profile's name is often a person's name ("Alex"), typed by the user or taken by the browser from the
  account. Sending it to Claude would be a choice the user never made. The agent can say everything useful without
  it.

## Messages / interfaces

### New files

- `src/ai_browser/places.py`: the place, the settings file, resolving. No app imports, because the engine of a lone
  Claude Code session uses it. It imports `browsers`, `platforms`, `settings` and `extension_id`, never `chrome`
  (Decision 15).
- `src/ai_browser/app/links.py`: `InstanceLinks`.
- `src/ai_browser/app/watchers.py`: `WatcherCopies` (folders) and `Watchers` (live connections).
- `src/ai_browser/app/where.py`: the Settings view (the `browsers` message), `place_set` checks, and labels.
- `src/ai_browser/app/ui/places.js`: the Settings section and the AI Home chip menu, shared.
- Tests: `tests/test_places.py`, `tests/test_watcher_copies.py`, `tests/test_links.py`, `tests/test_where.py`.

### Engine side (Python)

- **`places.py`:**
  - `@dataclass(frozen=True) class Place: browser: str; user_data_dir: str; profile: str`, with `instance` (the
    folder, normalized as `same_folder` compares it: one per browser instance) and `key` (`instance` and `profile`);
  - `same_folder(a, b, system=None) -> bool`: real paths, and on Windows case-blind (`ntpath.normcase`), the rule of
    `chrome._same_folder` (`chrome.py:133-138`), written here so that `places` never imports `chrome`;
  - `KEY = "agents_browser"`; the file is read and written with wave 3's `settings.read_settings` and
    `settings.write_setting`;
  - `save_place(home, place) -> None`: `write_setting(home, KEY, {"id", "user_data_dir", "profile"})`;
  - `saved_place(home) -> Place | None`: valid only as Decision 2 says;
  - `default_place(home) -> Place` (Decision 2). The primary copy's id is `extension_id_for(<home>/app/watcher)`;
  - `resolve(home, env=os.environ) -> tuple[Place, bool]`: the place, and whether it was chosen for the user. With
    `AIB_CHROME_DIR` set:
    - the folder is that, and the browser is `browsers.for_data_dir(folder)`'s id, else `""`;
    - the profile is `AIB_CHROME_PROFILE` when it is a plain folder name, else the saved profile when the saved folder
      is the same, else "Default".

    So tests, which set `AIB_CHROME_DIR` (`tests/conftest.py:60`), never read a real choice.
  - `place_env(place) -> dict`: `{"AIB_BROWSER": "chrome", "AIB_CHROME_DIR": ..., "AIB_CHROME_PROFILE": ...}`;
  - `place_from_env(env) -> Place | None`;
  - `plain_profile(name) -> bool`: wave 2B's plain-name rule (`browsers.profiles`, its Decision 5), for a profile name
    that comes from the environment or the file.
- **`chrome.py`:** `own_browser_dir()`, `browser_name()` and `inspect_address()` per Decision 15;
  `default_chrome_dir` stays its other name. The `launch()` guard (`chrome.py:170`) refuses every folder in
  `browsers.all_data_dirs()`, as wave 2B suggests, and still every folder in `own_browser_dirs()`.
- **`grouping.py`:**
  - the docstring's last sentence (`:8-9`) becomes "CDP can't choose a profile: with the app and the profile's watcher,
    the watcher opens the tab (open_tab); otherwise it opens in the profile the user used last, and the result says
    so.";
  - `ENGINE_OPEN_WAIT = 3.0`;
  - `@dataclass class Placement: target: str | None = None; params: dict | None = None; marker: str | None = None;
    why: str = ""`;
  - `Placer.open() -> Placement`:
    - with a link whose status says `open`: `link.open_tab(new_marker())` within `ENGINE_OPEN_WAIT`;
    - `opened: true` gives `Placement(target=...)`;
    - anything else gives today's `create_params()` with `why` set to the app's reason (or `"no_app"`, `"no_watcher"`);
  - `Placer.note_for(landed: str | None, why: str, key: str) -> str`: the fallback note (Texts), once per session and
    again when a tab lands in a different context from the earlier ones; `""` otherwise;
  - `placed()` and `popup()` as today.
- **`agentlink.py`:**
  - `_request(method, path, body, timeout=2)` (`agentlink.py:90-103`): its fixed 2 s becomes a parameter, with that
    default;
  - new `async open_tab(marker, timeout) -> dict` (`POST /agent-open`, with the `timeout` the `Placer` passes,
    `ENGINE_OPEN_WAIT`; `{"opened": False, "reason": "no_app"}` when the app doesn't answer). `agentlink` can't import
    `grouping`, which imports it;
  - `status()` adds `"open": bool` and `"context": str | None`, cached for `GROUPS_TTL` like `groups`
    (`agentlink.py:68-81`);
  - `hello(place)` sends `{"agent", "pid", "place": {"browser", "profile"}}`. Wave 2A's answer,
    `{"cdp_token": …}`, gains `"place"`: the same place, or null (Decision 15).
- **`browser.py`, `open_worker`** (`:423-443`):
  - `placement = await self.placer.open()`;
  - with `placement.target`, it skips `Target.createTarget` and goes straight to `_setup_tab`;
  - otherwise it creates the tab as today, calls `placed()`, reads the tab's `browserContextId` with
    `Target.getTargetInfo` (allowed through the relay for the client's own tab), and appends `placer.note_for(...)` to a
    new `_place_notes` list;
  - `_download_notes()` (`:370-374`) also returns and clears `_place_notes`, so the notes reach `observe`'s and
    `act`'s results where download notes do (`:761`, `:1096`, `:1107`). `open` returns `observe()` (`:763-768`);
  - a tab the watcher opened in a new window adds the note "(a new Brave window was opened for tab tN: the chosen
    profile had none open)", with the browser's name.
- **`engine.py`:**
  - `self._place: Place | None`, set once by `_start_chrome` from `places.resolve(self.home)`; `place_env` values in an
    agent's env win inside `resolve`;
  - `find_ws_url` (`:193`, a direct session) and `_browser_name()` (`:291-292`) use it, in place of wave 2A's
    link.json `browser_dir`;
  - wave 2A's `_route()` takes the place: the session's `hello(place)` sends it, an answer with the same place gives
    the relay, and `"place": null` gives a direct connection (Decision 15). The session never takes another place;
  - `_placement()` (`:260-269`) gains the texts below;
  - `RECONNECTED` and the errors keep naming the browser only.
- **`app/bridge.py`:** `BRAVE_PROMPT` (`:36-46`) keeps its name, which waves 1A and 5 use, and becomes a template.
  `browser_prompt(name)` fills it, and `bridge.py:324` passes `browser_prompt(...)`:
  - "You work in the user's everyday {name}, in the profile the user chose, in background tabs…", and `{name}` in
    place of every other "Brave" in it;
  - `{name}` is `chrome.browser_name(Path(env["AIB_CHROME_DIR"]))` (Decision 15), so a throwaway folder gives
    "Chrome";
  - the rest is word for word, including wave 1A's added sentence;
  - no profile name.

### App side (Python)

- **`app/bravelink.py`:** `class InstanceLink(folder, watcher_ids: set[str], tokens, app_origin)`: the `BraveLink` of
  waves 1B, 2A and 3, with its `watcher_id` made a set, as wave 1B's "For the later waves" asks. `BraveLink` stays as
  another name for the tests. It adds:
  - `name` from `chrome.browser_name(folder)` (Decision 15);
  - `chosen: str | None`, the profile folder whose tabs are listed, set by `InstanceLinks`;
  - `chosen_context: str | None`, the context of the copy connected in `chosen`, set by `Watchers`;
  - `agents_context()`: `(chosen_context, "chosen")` when it is known, else wave 1B's `"last_used"` and `"none"`
    (Decision 10). Wave 1B's `"watcher"` goes;
  - `worker_contexts(extension_id)` and `default_context`, passed through from wave 1B's `TabWatch`;
  - `context_of(target) -> str | None` and `targets_showing(url) -> list[str]`, from `TabWatch.pages()`. Neither
    attaches to anything.
- **`app/tabs.py`:** no change. Wave 1B's `pages()`, `worker_contexts()` and `default_context` are enough.
- **`app/links.py`, `class InstanceLinks(make_link)`:**
  - `current: Place`;
  - `set_current(place) -> bool` (True when the browser changed);
  - `link_for(place) -> InstanceLink | None`;
  - `ensure(place) -> InstanceLink`: makes or reuses that browser's link, and connects nothing (Decision 11);
  - `async connect(place, why="connect", identity="") -> None` (single-flight per link; refuses a browser nobody
    uses, Decision 11). It passes `why` and `identity` to that link's `relay.open(why, identity)`, so wave 2A's table
    of who may open from which state still decides: `"start"` at app start, `"connect"` for Connect, Try again and a
    browser switch click, `"turn"` with the agent's id for an agent's turn;
  - `in_use(instance) -> bool` and `async prune(live: set[str])`;
  - `context_of(place) -> str | None`;
  - `tabs() -> tuple[list[dict], dict]`: the current link's rows and `scope()` (wave 1B), plus the rows other links
    hold for agents, sessions and hand-overs, each with its `place` label;
  - `watch`, `close_targets`, `thumbnail`, `page_text`, each routed to the link that lists the target;
  - `on_change`, `on_state`.
- **`app/watchers.py`:**
  - `class WatcherCopies(home)`:
    - `primary`, `folder_for(browser, profile) -> Path`, `existing() -> list[Path]`;
    - `prepare_all(url, token) -> dict[str, Path]` (id → folder);
    - `make(browser, profile, url, token) -> Path`;
    - `ids() -> set[str]`;
  - `@dataclass class WatcherConn`: `ws`, `queue`, `origin`, `extension_id`, `copy` ("primary" or the slug),
    `groups: GroupKeeper`, `place: Place | None` (from the files), `context: str | None` (from the worker), `status`
    ("on", "unknown", "shared");
  - `class Watchers(copies, links)`:
    - `connected(ws, queue, origin) -> WatcherConn`, `gone(ws)`;
    - `brain() -> WatcherConn | None`;
    - `place_of(origin) -> Place | None`: the name wave 5 calls;
    - `for_place(place)`, `for_context(instance, context)`;
    - `can_group(instance)`: a copy that can group is connected in the link's `default_context` (Decision 6);
    - `status_for(place) -> "on" | "missing" | "asleep" | "shared" | "unknown"`: `on`, a copy placed there by the
      files has an open socket; `asleep`, the files place one there and none is connected; `shared`, a copy there is
      also in another place; `unknown`, a copy is connected that no file places yet; `missing`, none of these;
    - `async refresh()`: `browsers.watcher_places` for every installed browser offered to agents, through
      `asyncio.to_thread`, at the times Decision 8 lists, never on a repeating timer. It marks a copy found in two
      browsers as shared;
    - `connections()` (wave 5 pushes `tab_owners` per browser through it).
- **`app/groups.py`:** one `GroupKeeper` per `WatcherConn`. It gains:
  - `OPEN_WAIT = 2.5` (seconds for the watcher's answer and the target together);
  - `caps["open"]`;
  - `async open(marker, key, title, color) -> dict`: one `open_tab` with a request id and a future, answered by
    `opened_tab` or `OPEN_WAIT`;
  - `opened(message)`;
  - `late: Callable[[str], None]`: called with the marker of an answer that came after its wait.
- **`app/where.py`:**
  - `async browsers_view(links, watchers, agents, current, automatic, fresh: bool) -> dict` (the `browsers` message):
    - `browsers.public(browsers.detect(watchers), connected=<ids of connected links>)`, wave 2B's fixed shape;
    - plus, per browser, `at_work` (live agents placed there), and per profile, `at_work` and `live` (a copy is
      connected and placed there);
    - `shared_watcher` also set on both rows of a copy enabled in two browsers (Decision 8);
    - with `fresh` false it reuses the last `detect()` and refreshes only the states and the counts. Files are read
      again only when a page asks, after `place_set` or `watcher_copy`, and when a copy connects;
  - `check_place_set(message) -> Place | str`: the place, or the error text. It takes ids only and finds the folder in
    `browsers.installed()`;
  - `describe(place) -> {"label": "Brave · Personal", "color": "#3f51b5"}`, for the app's own pages only.
- **`app/agents.py`:**
  - `Agent` gains:
    - `place: dict`, public, as `{"browser", "profile", "label", "color"}`;
    - `task`, `skills` and `servers`, not public;
  - `AgentManager` gains:
    - `place: Place | None`;
    - `describe: Callable[[Place], dict] | None`;
    - `create(..., place=None)`: an explicit place wins, for an agent started in a handed tab (Decision 3);
    - `async restart(agent_id) -> Agent` (Decision 13).
- **`app/cdprelay.py`:**
  - one `Relay` per `InstanceLink`, as wave 2A already builds it (one per folder), all sharing the server's `Tokens`;
  - new `Relay.assign(target, identity) -> bool`: records a target the client didn't create as its own, if the relay
    lists it, and fires `on_grant`. False when the relay doesn't list the target (Decision 4). When that client has
    discovery on, it also sends it the target's `Target.targetCreated` from the cache, once, as wave 2A's Decision 3
    does for a tab the client created. So the engine's later `targetInfoChanged` and `targetDestroyed` for it follow a
    `targetCreated`, as for any tab of its own;
  - new `Relay.close_marker(target, marker) -> bool`: the app's client closes a target the relay lists at
    `about:blank#aib-<marker>`, for a marker the app sent in an `open_tab` this run, whoever owns it. This is how a late
    `open_tab` tab and a `wrong_profile` one are closed (Decision 4). Wave 2A's Decision 9 rule, that the app's client
    never closes a tab nobody owns, stays for every other tab.
- **`app/server.py`:**
  - `self.watchers` and `self.links` replace the one `_watcher` slot (`:140`) and `self.brave` (`:151`);
  - the `/cdp` route (wave 2A) first refuses an `Origin` or a wrong `Host` as wave 2A's Decision 8 does, in that order,
    then finds the client's identity with `tokens.who`, then that identity's place (an agent's `place`, a session's
    from its hello), and hands the socket to that place's link's `relay.serve(ws)`, which checks everything again. An
    identity with no place gets wave 2A's 409 text. Every live agent's and session's place has a link
    (`InstanceLinks.ensure`, Decision 11);
  - `_to_watcher` (`:609-616`) goes to `watchers.brain()` only;
  - `_group` (`:393-397`) picks the `WatcherConn` by the target's context;
  - the `tab_of` map becomes target → (connection, tab id);
  - `_agent_status` (`:422-435`): `groups` is `watchers.can_group(<the identity's browser>)` (Decision 6); `open` is
    true when the copy in the identity's place is `on`, said `open: true` in its caps, and has a context; `context` is
    that context, or null;
  - `_browser_info()` (`:490-494`) adds `place` and `watcher`, and takes `groups` from the current place's copy
    (Decision 9);
  - `connect_brave(why, identity)` (`:485-488`, wave 2A's signature) becomes `links.connect(links.current, why,
    identity)`, and `on_turn` (`:174`) connects the agent's own place with `"turn"` and the agent's id;
  - `take_back` (`:513-516`) runs wave 2A's `relay.cut` on the relay of the agent's own place's link, the only relay
    that agent's sessions are on;
  - `browser_clients` (wave 2A) lists the clients of every open link's relay. Each row gains `"browser"`, that link's
    browser name, and the page shows it when more than one link is open. `browser_disconnect {id}` goes to the relay
    that holds that identity;
  - `_hand` and `new_task`'s `adopt` follow Decision 14;
  - `place_of(origin)` passes through to `Watchers.place_of`, for wave 5;
  - new: the `/agent-open` route, the page messages below and `opened_tab` from the watcher;
  - **wave 1B's tables:**
    - `MESSAGE_RULES` gains five rows: `opened_tab` (watcher yes, from a socket that said `hello` as a watcher; app
      no), and `browsers`, `place_set`, `watcher_copy` and `restart_in` (app yes, watcher no). The table tests' copies
      grow by five;
    - the reports' condition narrows by role (Decision 9): `items`, `replied`, `thread`, `filled` and
      `reader_status` count only from the primary copy's worker socket; `watcher_caps`, `tab_grouped` and `opened_tab`
      from any copy's worker socket;
    - `WATCHER_RECEIVES` gains `open_tab`. The new page messages `browsers`, `place_changed` and `watcher_copy` stay
      off it, so watcher sockets never get them, as wave 1B drops every type not on its list;
    - `WATCHER_AGENT_FIELDS` doesn't gain `place`, so a watcher never receives an agent's place.
- **`brain/watcher.py`:** `prepare_watcher(home, url, token, folder=None)`. Without `folder` it is today's primary copy
  (`:33-44`). Each copy gets the same files, including wave 3's shared files from `app/ui/`.
- **`app/run.py`:**
  - at start: `place, automatic = places.resolve(home)`, `links.set_current(place)`, `agents.place = place`,
    `copies.prepare_all(url, token)` with every origin allowed as a watcher;
  - one line printed, with the folder and never the display name (Decision 16): "Agents browse in Brave · profile
    folder Profile 1 (change it in AI Browser's Settings)";
  - `brave_env` (`:105-107`) becomes `place_env`, which `AgentManager.create` adds to each agent's env. `agents.env`
    no longer carries `AIB_CHROME_DIR` (`:212`). `SWITCH` (`:76-84`, already reworded by wave 2A) names the current
    browser. Its Allow line, and the setup page's and the README's, add the browser switch, because that click now
    asks: "Only click Allow right after you started AI Browser, clicked Connect, gave an agent a task, switched to
    {name} in AI Browser's Settings, asked Claude Code to browse, or opened {name} again while an agent was working."
    Wave 5 adds the side chat's clicks to the same line;
  - link.json (wave 2A's `write_link`) is written again, with the new `browser_dir`, when the current browser
    changes;
  - wave 3's `open_url` gets the current place's `Installed` row;
  - `--browser` and `AIB_APP_BROWSER` keep whatever wave 3 left them.
- **`cli.py`, `doctor`** (`:171-178`): the "everyday" line names the place: "Brave · profile folder Default (chosen in
  Settings)" or "(chosen for you)".

### HTTP (engines → app; 127.0.0.1 only)

| Route | Body | Answer |
|---|---|---|
| `POST /agent-open` (new) | `{agent, marker}` | `{"opened": true, "target": "…", "tab": 412, "grouped": true, "new_window": false}` or `{"opened": false, "reason": "no_watcher" \| "asleep" \| "shared" \| "unknown" \| "not_connected" \| "timeout" \| "not_found" \| "wrong_profile" \| "refused"}` |
| `GET /agent-status` (as today) | | `groups` as Decision 6 says; adds `"open": bool, "context": str \| null` |
| `POST /agent-hello` (as today) | adds `"place": {"browser", "profile"}` | adds `"place"`: the same place, or null (Decision 15) |

All of these keep today's rules (`X-AIB-Agent-Token`, the session token only for `cc-` ids, 403 and 404). For
`/agent-open`:
- **400** for a marker that isn't 16 hex characters, or one already used in this run;
- every `"opened": false` answer is a 200, so the engine reads its reason;
- **the reasons:**
  - `no_watcher`, `asleep`, `shared`, `unknown`: `status_for` of the identity's place (`missing` is `no_watcher`);
    nothing is sent to any watcher;
  - `not_connected`: the identity's browser link isn't connected, so the context can't be checked. It comes at once;
  - `refused`: the watcher answered `ok: false`;
  - `timeout`: no `opened_tab` within `OPEN_WAIT`;
  - `not_found`: the watcher opened the tab, but no target shows the marker address within `OPEN_WAIT`;
  - `wrong_profile`: the target's context isn't the watcher's (Decision 4). The tab is closed.

`/agent-hello` accepts a session's place when its browser is an installed browser offered to agents and its profile
is a plain folder name. It records it (making that browser's link with `InstanceLinks.ensure`), answers with the same
place and mints the `cdp_token`. A session id that any link's relay has cut off (wave 2A's Disconnect) still gets 410
and no token, whichever place it names. Otherwise it records the session with no place, answers `"place": null` and
mints no `cdp_token`: that session connects directly (Decision 15).

### WebSocket: app ↔ watcher

- **App → watcher, new:**
  - `open_tab {"request": "o7", "marker": "<16 hex>", "key": "a3", "title": "Fix the footer", "color": "blue"}`;
  - it goes only to the connection of the agent's place.
- **Watcher → app, new:**
  - `opened_tab {"request": "o7", "ok": true, "tab": 412, "window": 77, "group": 9 | null, "new_window": false}`;
  - or `{"request": "o7", "ok": false, "reason": "invalid" | "failed"}`;
  - it gets a `MESSAGE_RULES` row (above), and `open_tab` joins `WATCHER_RECEIVES`.
- **Changed:** `watcher_caps {"groups": bool, "open": true}`. A watcher without `open` is treated as unable to open
  tabs. Watchers reload themselves when their files change (`watcher/worker.js:86-92`), so this lasts at most a minute.
- **The watcher checks `open_tab`** with `validOpen`, next to `valid` (`watcher/groups.js:25-32`):
  - `key` matches `KEY`, `color` is one of the nine, `title` is a string of at most 40 characters, `marker` matches
    `MARKER`;
  - any `url` field means refusal;
  - it never opens anything but `about:blank#aib-<marker>`.
- **In `watcher/groups.js`:** `export function openTab(message)`, queued on `grouping` like `groupTab` (`:143-147`).
  It never picks a window whose `incognito` is true.
- **In `watcher/worker.js`:** `handle` (`:67-84`) adds
  `else if (message.type === "open_tab") link.send({ type: "opened_tab", ...(await openTab(message)) });`, and
  `watcher_caps` (`:30`) adds `open: true`.
- **Copies:** they run the same files. A copy gets `watcher_hello` and the tab messages, never the Brain's.

### WebSocket: app ↔ pages (the app window's origin only)

- **Server → pages:**
  - `browser`: today's fields (`app/server.py:490-494`) plus:
    - `"place": {"browser", "profile", "label", "color", "automatic"}`;
    - `"watcher": "on" | "missing" | "asleep" | "shared" | "unknown"` for that place;
  - `browsers`, wave 2B's `public()` shape plus this spec's fields (`current`, `automatic`, `at_work`, `live`):

    ```json
    {"type": "browsers", "current": {"browser": "brave", "profile": "Default"}, "automatic": false,
     "browsers": [
       {"id": "brave", "name": "Brave", "agents": true, "default": true, "state": "connected", "at_work": 2,
        "profiles": [{"folder": "Default", "name": "Personal", "color": "#3f51b5", "last_used": false,
                      "watcher": true, "shared_watcher": false, "live": true, "at_work": 2},
                     {"folder": "Profile 1", "name": "Work", "color": "#1b5e20", "last_used": true,
                      "watcher": false, "shared_watcher": false, "live": false, "at_work": 0}]},
       {"id": "chrome", "name": "Chrome", "agents": true, "default": false, "state": "not_running", "at_work": 0,
        "profiles": [{"folder": "Default", "name": "Your Chrome", "color": null, "last_used": true,
                      "watcher": false, "shared_watcher": false, "live": false, "at_work": 0}]},
       {"id": "edge", "name": "Edge", "agents": false, "default": false, "state": null, "at_work": 0,
        "profiles": []}]}
    ```

    - `state` is `"connected"` for a browser whose link is connected (wave 2B's `connected` argument). While the link
      is asking, refused or lost, the server puts that state in its place. Otherwise it is wave 2B's `switch_on`,
      `switch_off` or `not_running`;
    - the page derives each profile's watcher line: `shared_watcher` gives the "two profiles" line; `watcher` and
      `live` give ✓; `watcher` alone gives "loaded, not connected"; neither gives "Needs the watcher";
    - no folder paths, no emails, no watcher ids;
  - `place_changed {"label": "Chrome · Work", "elsewhere": 2, "elsewhere_labels": ["Brave · Personal"]}`;
  - `watcher_copy {"browser", "profile", "folder", "extensions": "brave://extensions"}` (`chrome://extensions` for the
    Chrome family), the answer to the request below. Its `folder` is shown as text, for Load unpacked;
  - `tabs`: wave 1B's message. `tab_scope.profile` is `"chosen"` in place of `"watcher"`, rows owned outside the
    current place carry `"place": {"label", "color"}`, and a fallback tab's row carries `"other_profile": true`
    (Decision 10);
  - `agent` rows: `"place"` (above).
- **Pages → server** (refused from the watcher's origin: none is on its allowed list):
  - `browsers {}`: answered with `browsers`, from a fresh read of the files;
  - `place_set {"browser": "brave", "profile": "Profile 1"}`: checked by `check_place_set`. A wrong one gets
    `error {"text": "That profile isn't in Brave any more"}` and changes nothing;
  - `watcher_copy {"browser", "profile"}`: makes or refreshes that profile's copy, allows its origin, and shows the
    folder;
  - `restart_in {"id": "a2"}`: refused when the agent's place is already the current one.

### Files on disk

- `<home>/settings.json` (0600): `{"agents_browser": {"id": "brave", "user_data_dir": "/Users/alex/Library/Application
  Support/BraveSoftware/Brave-Browser", "profile": "Default"}}`, plus any keys wave 3 keeps there.
- `<home>/app/watchers/<slug>/`: a full watcher copy, with its own `config.json` (0600) and `build.js`.

### Texts

These go to Claude (tool results and status lines). They name the browser (here Brave; the place's browser name in
general), never a profile. Each status line keeps wave 2A's start ("browser: your Brave, through AI Browser's
connection" or "… not through AI Browser") and adds one part:
- **Placed by the watcher:** "· in the profile the user chose, where its watcher opens this session's tabs · only tabs
  this session opens, and tabs the user hands it · tab group 'Fix the footer'".
- **Fallback:** "· its tabs open in the Brave profile the user used last: " and the reason:
  - `no_app`: "ai-browser app isn't running";
  - `no_watcher`, `unknown`: "the watcher isn't in the chosen profile";
  - `asleep`: "the watcher in the chosen profile isn't connected";
  - `shared`: "the chosen profile's watcher folder is loaded in two profiles";
  - `not_connected`, `timeout`, `not_found`, `refused`, `wrong_profile`: "the watcher in the chosen profile didn't
    answer".
- **The first fallback tab:** "(tab t2 opened in the Brave profile the user used last: AI Browser can't pick the profile
  without the watcher there. Tell the user once; AI Home → Settings shows how to set it up.)"
- **A tab in another context than the earlier ones:** "(tab t3 opened in a different Brave profile from this session's
  earlier tabs: Brave puts new tabs in the profile used last)".
- **A new window:** "(a new Brave window was opened for tab t1: the chosen profile had none open)".

These stay on the user's own pages (names allowed):
- **The card's watcher lines:**
  - `missing`: "Agents' tabs open in whichever Brave profile you used last: the watcher isn't in Personal yet. Set it
    up.";
  - `asleep`: "The watcher in Personal isn't connected: open a Brave window in Personal.";
  - `shared`: "The watcher folder for Personal is loaded in two profiles: remove it from one in brave://extensions.";
  - two copies in one profile: "Two AI Browser watchers are loaded in Personal: remove the extra one in
    brave://extensions.".
- **The notice and Restart in:** as in What the user sees.
- **The terminal** (`ai-browser app`, `doctor`): the browser and the profile folder only (Decision 16).

## Safety

**The browser's own signs stay:**
- nothing auto-clicks, answers, suppresses or hides "Allow remote debugging?" or the automation bar, in any browser;
- a switch to another browser asks once, right after the user's click;
- with two browsers connected, each shows its own bar, and Settings says so.

**Connections only after the user acts:**
- detection reads files and makes TCP checks only (wave 2B; Success 2 tests it);
- the app connects to a browser only at start (the current place), on Connect or Try again, on a switch click, on an
  agent's turn (its own place's browser), or on a session's first command after its task (its own place's browser);
- it never connects to a browser that is neither the current place nor the place of a live agent or session. A
  session's place is the user's own setting: Settings, or the `AIB_CHROME_DIR` they configured;
- after Deny nothing retries by itself.

**No spoofing, no tricks:**
- `open_tab` uses `chrome.tabs.create({active: false})` and, for a profile with no window,
  `chrome.windows.create({focused: false})`, both documented;
- no focus tricks, no faked gestures, no `--profile-directory` launch, no `debugger` permission;
- nothing changes how any browser presents itself.

**The watcher's new power is one blank tab:**
- `open_tab` opens only `about:blank#aib-<16 hex>`, built by the watcher;
- a message with an address, a bad marker, colour or title is refused;
- the watcher never navigates or reads that tab. The engine loads pages over CDP, through the relay's scheme list and
  `url_problem`;
- it never uses a private window;
- it acts only on messages over its own origin and token, as today.

**Only the AI's tabs:**
- the app, not the engine, finds the new tab by its secret marker and checks its profile before `Relay.assign` gives it
  to that agent alone;
- a marker is used once;
- agents still never see the user's tabs (wave 2A).

**Hand-over and take-back stay clicks:**
- **Give to** lists only agents in the tab's browser;
- the Brain, voice and the watcher can't send `place_set`, `watcher_copy` or `restart_in`;
- the Brain only proposes Start and Send cards, as before;
- **Restart in** is a click on a button that names the place.

**Pages never choose a folder:** `place_set` and `watcher_copy` carry a browser id and a profile folder. The server
finds the browser's folder in `browsers.installed()` and checks the profile against its `Local State`. A path from a
page is never used. The app window's own profile (wave 3) and the retired `<home>/browser` aren't in
`browsers.installed()`, so they can never be a place.

**Text is text:**
- profile names, colours, labels, folder paths and counts are set with `textContent`;
- a hostile profile name stays text (tested);
- page and message text stays data, never instructions;
- an agent's group title is still its AI Home name.

**Nothing leaves the machine without a knowing choice:**
- emails are never read into the app;
- profile names and colours reach only the app's own pages. The terminal shows folder names only, because Claude Code
  may read it (Decision 16);
- an engine learns its place's context id from `/agent-status`, an opaque id that never goes into a tool result;
- `settings.json` and the copies' `config.json` are 0600 and local.

**Private windows** are never opened into or listed (Decisions 4, 5 and 10). They show only inside wave 1B's honest
number, "other profiles or private windows".

**Unchanged:**
- passwords are never typed: the agent asks the user to log in in that tab;
- downloads still need the user's OK (⚠ and the cancel net, everyday-brave Decision 15), now through the upstream of
  the agent's own browser;
- bot checks are handed to the user.

**Chromium's files are internals:** every read of `Local State`, `Secure Preferences` or `Preferences` fails safe: no
profiles, or "unknown", never a crash and never a guess.

## Testing

Tests never reach the user's real browsers:
- the autouse fixture (`tests/conftest.py:53-60`) also sets `AIB_CHROME_PROFILE=Default`. Its `AIB_CHROME_DIR` keeps
  `places.resolve` away from any real `settings.json` (Decision 15);
- now that the app calls `browsers.detect()`, the same fixture takes over (unless wave 3 already did) the parts of
  wave 2B's test fixture that keep detection off the real files, as that spec asks: `platforms.app_folders` gives
  empty temporary folders, `platforms.windows_browser_commands` gives `[]`, `platforms.windows_https_progid` gives
  None, and `platforms.launch_services_file` names a missing temporary file. It doesn't move `HOME`, which other tests
  rely on. With no installed browser, nothing reads a profile folder: the fallback to Brave's folder reads nothing
  (Decision 2);
- **a test that makes a browser "installed"** (sample `Info.plist` files in the temporary app folders) also moves
  `HOME`, `USERPROFILE` and `LOCALAPPDATA` to its `tmp_path`, as wave 2B's own fixture does. Otherwise that browser's
  data folder would be the user's real one, and a session could find its real `DevToolsActivePort`;
- `test_tests_never_reach_the_real_browsers` (`tests/test_chrome.py:24-27`) also asserts that `places.resolve()` gives
  the throwaway folder, and that `browsers.installed()` is `[]`;
- browsers in tests are throwaway Chromes started with `--remote-debugging-port`, which never ask Allow;
- the watcher fixture is the one wave 3 rebuilt on `tests/pipe_chrome.py`, and fakes are wave 2A's `FakeBrave` and
  `FakeRelay` (`tests/fake_brave.py`), which gain `assign` and a second link.

Every test below fails before this wave (on the merged waves 1-3), because the module, route, message or behaviour
doesn't exist yet or is the opposite, and passes after it. The tests that check something is absent (no place in the
Brain's state, none to the watcher) build their agents with `AgentManager.create(..., place=…)`, so they fail first
too.

**Where they run:** the unit tests run on macOS and, in the manual Windows workflow (`.github/workflows/tests.yml`),
on Windows, with `system="win32"` cases for paths and slugs. The watcher-fixture tests use the DevTools pipe, so they
are POSIX-only (`conftest.py`'s `PIPE_FIXTURES`). The headful tests run only with `AIB_HEADFUL=1`. Windows placement is
checked by hand on the laptop (below).

### First task: five facts, measured in throwaway browsers

Each becomes a test or a note in the code:
1. **A new window, unfocused** (visible throwaway Chrome, two profiles): does `chrome.windows.create({focused: false})`
   from the watcher in a profile with no window come to the front on macOS? Does it take focus from the user's window
   in the other profile? The same on the Windows laptop. (Decision 5's line in Settings depends on it.)
2. **How soon Brave records Load unpacked:** how long after it does `Secure Preferences` hold
   `extensions.settings.<id>`? (It sets the re-reads at 2 s, 5 s and 15 s after a copy connects.)
3. **Private windows and the watcher:** with the watcher allowed in private windows, does `windows.getLastFocused` return
   a private window? (The filter stays either way.)
4. **The worker's target:** is the watcher's `service_worker` target listed, with its context, the whole time its socket
   to the app is open? And after the profile's last window closes, how long does its copy stay connected? (Decision 5
   applies only while it is.)
5. **Two copies, two contexts:** with copies loaded in Default and Profile 2, do their workers show two different
   contexts, each equal to the context of a tab that copy opened?

### Unit tests, no browser

1. **`tests/test_places.py`** (new; with wave 2B's sample files in `tests/samples/browsers/`, temporary app folders,
   and `HOME`, `USERPROFILE` and `LOCALAPPDATA` in `tmp_path`):
   - `test_the_saved_choice_wins_over_a_switch_that_is_on`: a Chrome folder with a live `DevToolsActivePort`, and a
     saved Brave place, resolve to Brave;
   - `test_resolve_order`:
     - `AIB_CHROME_DIR` (+ `AIB_CHROME_PROFILE`), then the saved place, then the OS default, then the first installed
       browser offered to agents, then Brave's folder;
     - `automatic` is true only for the last three;
     - an `AIB_CHROME_DIR` no known browser owns gives the browser `""`; a bad `AIB_CHROME_PROFILE` (`../x`) gives
       "Default";
   - `test_the_fallback_to_braves_folder_reads_nothing`: with nothing installed and a `Local State` in Brave's
     (temporary) folder, the profile is "Default" and a spy on `open` and `platforms.open_shared` sees no read there;
   - `test_a_saved_browser_that_is_gone_is_ignored` (uninstalled, folder moved, profile deleted);
   - `test_saving_keeps_other_keys_and_is_private`: `{"window_browser": "chrome"}` survives; mode 0600 (`file_mode`,
     None on Windows);
   - `test_a_broken_settings_file_never_crashes`: empty, half-written, a list, wrong types;
   - `test_the_profile_chosen_for_you_is_the_watchers_then_last_used`: `brave-local-state.json` and
     `secure-preferences-watcher.json`, then the watcher removed;
   - `test_profile_names_are_plain_folder_names`: `../x`, `a/b`, `C:x` and `..` are refused;
   - `test_place_env_round_trip`.
2. **`tests/test_chrome.py`:**
   - `test_own_browser_dir_order` (`:52-73`) is rewritten, with `HOME`, `USERPROFILE` and `LOCALAPPDATA` in
     `tmp_path`. Its "a switch that is on wins" becomes "a switch that is on never decides";
   - `test_every_hint_names_the_browser` keeps its `BraveSoftware` folder under `tmp_path`, which no row owns, so it
     still says "Brave" (Decision 15's fallback). It adds a Chrome Beta folder at wave 2B's data folder under a moved
     `HOME`: "Chrome Beta" and `chrome://inspect/#remote-debugging`;
   - `test_launch_refuses_every_real_browser_folder` (`:92-99`) also tries every folder in `browsers.all_data_dirs()`.
3. **`tests/test_watcher_copies.py`** (new):
   - `test_a_copy_per_profile_has_its_own_folder_and_id`: stable slugs; `extension_id_for` differs from the primary's;
     the folder is outside `<home>/app/watcher`;
   - `test_updating_the_primary_never_deletes_a_copy`;
   - `test_every_copy_is_brought_up_to_date_at_start`: `build.js` and `config.json` in each, 0600;
   - `test_a_watcher_is_placed_by_its_profiles_files`: id in Profile 1 gives that place; in two profiles, or in Brave
     and Chrome, shared (and the view sets `shared_watcher` on both rows); nowhere, unknown;
   - `test_the_files_are_read_again_only_on_events`: a copy that connects while unknown is read again at 2 s, 5 s and
     15 s (a fake clock), then not until a page asks;
   - `test_place_of_gives_a_copys_browser_and_profile` (the name wave 5 calls), with the browser's link not connected;
   - `test_a_copys_context_comes_from_its_worker_in_its_own_browser`: a fake Brave link listing the worker target gives
     the context; the same id's worker in a fake Chrome link gives none;
   - `test_status_for_each_state`: `on`, `asleep`, `shared`, `unknown` and `missing`, as `Watchers.status_for` defines
     them;
   - `test_slugs_are_stable_and_never_shared` (`system="win32"` too): `brave` and "Profile 1" give `brave-profile-1`;
     two folder names with one slug make the second **Set it up** an error, and no folder.
4. **`tests/test_links.py`** (new; fake links record `connect` and `close`):
   - `test_only_the_current_browser_connects_at_start`;
   - `test_a_profile_switch_connects_nothing`;
   - `test_a_browser_switch_connects_the_new_browser_once`: two callers, one connect;
   - `test_the_old_browser_stays_while_its_agents_live_then_closes`: `prune` after the last `agent_closed`, and after a
     session's bye;
   - `test_a_browser_nobody_uses_is_never_connected`;
   - `test_a_switch_to_a_browser_whose_switch_is_off_connects_nothing`;
   - `test_ensure_makes_a_link_and_connects_nothing`;
   - `test_the_tab_list_follows_the_chosen_profile`:
     - pages in C1 (the chosen profile's copy's worker) and C2 (the default context), plus an agent's tab in C2;
     - rows are C1's and the agent's, the agent's row with a place label and no context;
     - the agent placed in C1's profile has `other_profile: true` on its C2 tab;
     - `tab_scope` is `{"profile": "chosen", "elsewhere": <C2's user pages>}`;
   - `test_without_the_chosen_profiles_copy_the_list_falls_back_to_the_profile_used_last`: `tab_scope.profile` is
     `"last_used"`, as in wave 1B;
   - `test_a_profile_switch_re_filters_the_list_at_once`.
5. **`tests/test_groups.py`:**
   - `test_open_tab_is_answered_by_its_own_request` (two out of order);
   - `test_a_late_open_answer_closes_its_tab` (the `late` callback gets the marker);
   - `test_caps_say_whether_a_watcher_can_open_tabs`.
6. **`tests/test_grouping.py`:**
   - `test_with_the_profiles_watcher_the_app_opens_the_tab`: `status` says `open`; `Placer.open()` returns the target
     and no parameters;
   - `test_when_the_watcher_cant_the_tab_falls_back_with_the_reason`: marker parameters when groups are on, else
     `newWindow`; `why` set;
   - `test_open_waits_at_most_engine_open_wait`;
   - `test_open_tab_is_heard_after_two_seconds`: a fake app (as at `tests/test_grouping.py:79`) that answers
     `/agent-open` after 2.4 s is heard; today's 2 s request timeout would drop it;
   - `test_the_fallback_note_is_said_once_and_names_no_profile`: the same context twice gives one note, a new context
     another; no profile name or folder in either.
7. **`tests/test_app_server.py`** (fake watcher sockets with two copies' origins, E1 in Default and E2 in Profile 1;
   fake links; `FakeRelay` recording `assign`):
   - `test_agent_open_goes_to_the_watcher_of_the_agents_profile`:
     - an agent in Profile 1 gets `open_tab` on E2 only;
     - the marker target in E2's context is returned, `assign(target, "a1")` is recorded, and AI Home's owner chip
       follows;
   - `test_agent_open_without_that_profiles_watcher_says_no_watcher`: only E1 connected; nothing is sent to E1;
   - `test_a_tab_in_the_wrong_profile_is_closed_and_refused`;
   - `test_agent_open_tokens_and_markers`: 403, the session token for `a1`, a bad marker, a reused marker, and
     `not_connected` at once when the agent's browser isn't connected;
   - `test_the_brains_messages_go_to_the_primary_watcher_only`: `notify`, `open_thread`, `fill_reply`, `watch_list`,
     `permission_request`;
   - `test_place_set_changes_new_agents_only`:
     - `a1` is created, then `place_set` Profile 1, then `a2`;
     - `a1` keeps Default; `a2` gets Profile 1 and `AIB_CHROME_PROFILE`;
     - `browser`, `browsers` and `place_changed` (elsewhere 1) are broadcast;
   - `test_place_set_takes_ids_never_paths`: a `user_data_dir` in the message is ignored; an unknown browser or profile
     gets the error, no change and no write;
   - `test_place_set_watcher_copy_and_restart_in_are_refused_from_the_watchers_origin`, through wave 1B's table test,
     whose copy gains the five new rows;
   - `test_the_watcher_never_receives_an_agents_place` (`for_watcher` trims it);
   - `test_brain_reports_count_only_from_the_primary_copy`: `items` from a copy's socket is dropped; `tab_grouped` and
     `opened_tab` from it reach that copy's `GroupKeeper`;
   - `test_a_browser_switch_connects_once_and_a_profile_switch_never`;
   - `test_restart_in_stops_and_starts_the_same_words_in_the_current_place`:
     - the old agent is stopped, not closed, and its tabs aren't closed;
     - the new one has the same text, skills, model and servers;
     - it is refused when the places are equal;
   - `test_hand_over_stays_within_one_browser`: a Brave tab to an agent in Chrome is refused; to an agent in another
     Brave profile it is allowed;
   - `test_agent_hello_records_and_answers_the_sessions_place`:
     - a Brave place is echoed with a `cdp_token`;
     - a Chrome place while the current place is Brave is echoed too, and makes Chrome's link without connecting it;
     - a place with the browser `""` gets `"place": null` and no `cdp_token`;
   - `test_agent_status_says_whether_the_profiles_watcher_can_open_tabs`;
   - `test_agent_status_groups_only_when_the_profile_used_last_has_a_copy`: E1's context is the default context:
     `groups` true; the default context changes to one with no copy: `groups` false, though E1 is still connected;
   - `test_take_back_cuts_on_the_agents_own_relay`: with Brave current and a2 placed in Chrome (two fake links, each
     with a `FakeRelay`), Take back of a tab handed to a2 calls `cut` on Chrome's relay only;
   - `test_browser_clients_list_every_link`: with two links, `browser_clients` rows carry `browser`, and
     `browser_disconnect` for a2 reaches only the relay that holds a2;
   - `test_connect_keeps_wave_2a_why`: app start passes `"start"`, Connect `"connect"`, a browser switch `"connect"`,
     and an agent's turn `"turn"` with its id, to the fake link's `relay.open`.
8. **`tests/test_agents.py`:**
   - `test_an_agent_keeps_the_place_it_was_created_with` (env and `place`, after `agents.place` changes);
   - `test_an_agent_started_in_a_handed_tab_takes_that_tabs_place`;
   - `test_restart_keeps_the_words_skills_model_and_servers`.
9. **`tests/test_engine.py`:**
   - `test_a_session_resolves_its_place_once` (`AIB_CHROME_DIR` unset; two browsers "installed" from wave 2B's sample
     plists; `HOME`, `USERPROFILE` and `LOCALAPPDATA` in `tmp_path`): `settings.json` changes after the first connect
     (a fake CDP); the same engine keeps its browser, and a new engine takes the new one;
   - `test_a_session_the_app_cant_hold_connects_directly`: a fake app answers `/agent-hello` with `"place": null`; the
     engine connects to its `AIB_CHROME_DIR` directly, with wave 2A's "not through AI Browser" line, and never to the
     relay;
   - `test_no_tool_result_carries_a_profile_name_or_email`:
     - fixture `Local State` with the name `SECRET-NAME-9` and `user_name` `secret@example.com`;
     - status lines, notes and errors are scanned.
10. **`tests/test_app_run.py` and `tests/test_cli.py`:** `test_the_terminal_names_the_profile_folder_never_its_name`:
    with that same `Local State`, `run_app`'s `out` lines and `doctor`'s "everyday" line hold "profile folder Default"
    and never `SECRET-NAME-9`. Also `test_the_allow_line_names_a_browser_switch` (`tests/test_app_run.py`, beside wave
    2A's `test_the_switch_text_says_once_per_run`): `SWITCH`, `/setup` and the README's Allow line each contain
    "switched to" and still "it isn't AI Browser".
11. **`tests/test_bridge.py`:** `test_the_agents_prompt_names_its_browser_and_no_profile`: a Brave folder gives "Brave",
    a Chrome Beta folder gives "Chrome Beta", a throwaway folder gives "Chrome", and no profile name appears. The
    existing check that the prompt is `BRAVE_PROMPT` (`tests/test_bridge.py:252`) becomes `browser_prompt("Brave")`.
12. **`tests/test_brain_talk.py`:** `test_the_brains_state_never_carries_an_agents_place`: an agent made with
    `create(..., place=…)` and the label "SECRET-NAME-9"; no part of the Brain's state holds it.
13. **`tests/test_cdprelay.py`** (wave 2A's file, with its `FakePort`):
    - `test_assign_grants_a_listed_target_and_announces_it_once`: an unlisted target gives False; a listed one gives
      True, fires `on_grant` once, and a1 (discovery on) gets one `Target.targetCreated` for it, and later its
      `targetDestroyed`;
    - `test_close_marker_closes_only_an_open_tab_marker`: the app's client closes, through `close_marker`, an unowned
      target at a marker the app sent this run; a user's unowned tab, or a marker never sent, is refused, and the fake
      never gets that `Target.closeTarget`.
14. **`tests/test_where.py`** (new):
    - `test_building_the_settings_view_never_opens_a_debugging_session`:
      - a fake installed Brave (sample plist, moved `HOME`) whose data folder has a `SingletonLock` naming this test's
        own pid, so `state()` does make its TCP check, and a `DevToolsActivePort` naming a listening socket that
        records connects and bytes;
      - `browsers_view()` makes at least one TCP connect, and the socket receives zero bytes;
    - `test_the_view_has_no_paths_no_emails_and_no_watcher_ids`;
    - `test_browsers_agents_cant_use_are_listed_without_profiles`;
    - `test_a_kept_view_refreshes_states_without_reading_files` (`fresh=False`; a spy on `browsers.detect`).

### With a throwaway browser (one profile, headless; the watcher fixture as rebuilt in wave 3)

1. **`tests/test_watcher_groups.py`:**
   - `test_open_tab_makes_a_background_tab_at_the_marker_in_the_group`:
     - through `/agent-open` for `a1`;
     - read through the watcher's worker: the tab's URL is the marker address, its group has the agent's title and
       colour;
     - the active tab is unchanged; `new_window` is false;
   - `test_open_tab_opens_nothing_but_the_marker`:
     - a bad marker, a 41-character title, colour "black", or an extra `url: "https://example.com"` each give
       `ok: false`;
     - the number of tabs is unchanged, and no tab ever shows example.com;
   - `test_an_agent_engine_uses_the_watcher_and_creates_no_target`:
     - an engine in own mode as `a1`, through the relay;
     - the test wraps the relay's upstream send and records each forwarded method with its identity (wave 2A's `log`
       holds refusals only); no `Target.createTarget` from `a1` is recorded;
     - `open(url)` loads the page, and `tabs list` shows `t1`;
   - `test_without_the_profiles_watcher_the_engine_falls_back_and_says_so`:
     - the agent's place names a profile with no watcher;
     - `Target.createTarget` is used, and the result has the fallback note once.
2. **`tests/test_bravelink.py`:** `test_two_watcher_ids_and_the_chosen_context`: with `watcher_ids` holding two ids,
   each worker's context is found; `agents_context()` gives `("…", "chosen")` once `chosen_context` is set, and wave
   1B's `"last_used"` before. Wave 1B's tests that expect `"watcher"` (its tests 12-14 and 20) set `chosen_context` to
   the worker's context, as `Watchers` does, and expect `"chosen"`.
3. **AI Home and Settings** (`tests/test_home.py` stack as rebuilt in wave 3):
   - `test_the_chip_shows_the_place_and_switches_profiles`:
     - "Brave · Personal" is shown;
     - a profile in the menu sends `place_set`;
     - a "needs the watcher" profile opens Settings and sends nothing;
   - `test_a_hostile_profile_name_stays_text` (`<img src=x onerror=…>` in a name and a label);
   - `test_settings_lists_browsers_profiles_and_watcher_states`: cards of browsers agents can't use are greyed, each
     watcher line follows `watcher`, `shared_watcher` and `live`, and **Set it up** sends `watcher_copy`;
   - `test_restart_in_shows_only_for_agents_elsewhere`, and sends `restart_in`;
   - `test_the_tab_list_says_it_shows_the_chosen_profile` (and wave 1B's count line, unchanged);
   - `test_give_to_lists_only_agents_in_the_same_browser`;
   - `test_your_tabs_follow_the_agents_browser` (Mission Control's drawer, wave 1A's Your tabs): an agent placed in
     Chrome while Brave is current shows no rows and the "This agent works in Chrome" line; an agent in Brave's other
     profile shows the rows with "(in Work)".

### Visible browser, two profiles (`@pytest.mark.headful`)

A new marker in `pyproject.toml` (`:40-44`): "headful: opens visible throwaway browser windows; runs only with
AIB_HEADFUL=1". These tests are skipped otherwise. They use a throwaway Chrome with Default and Profile 2, and a watcher
copy loaded in Profile 2 as probe4.py did:
- `test_tabs_land_in_the_watchers_profile_whatever_was_used_last`:
  - a Default tab is made active first;
  - the agent's tab's `browserContextId` is the Profile 2 worker's context;
  - the focused tab is unchanged;
- `test_the_fallback_lands_in_the_profile_used_last_and_says_so`;
- `test_a_profile_with_no_window_gets_one_behind`: Profile 2's last window closes while its copy stays connected
  (first-task fact 4); the agent's tab opens in a new Profile 2 window, at the marker, grouped, with `new_window` true
  and the note. A Default page's `document.hasFocus()`, read over CDP, is true before and after. If fact 1 found that
  this OS brings the window forward, that one assertion is skipped there with the fact's note;
- `test_a_private_window_is_never_listed_or_used`: an `--incognito` window holds a tab titled `SECRET-7f3a`. It is in
  no `tabs` row and in no `open_tab` window choice; it adds one to `tab_scope.elsewhere`.

### Manual check, by the user, in their own Brave (after this wave)

1. Open Settings → Where agents browse. Brave and Chrome show, with no Arc, Edge, Vivaldi or Opera card. Brave's
   profiles show with names and colours and no email.
2. Pick the profile you're signed in on. If it says "Needs the watcher", click **Set it up** and load the folder there
   once.
3. Click in a window of your other profile, then give an agent a task. Its tab appears in the chosen profile, in its
   group, and your window keeps the focus.
4. In the chip, switch to the other profile: no Allow appears. Switch back.
5. AI Home's tab list shows only the chosen profile's tabs, and one line counting the rest. Open a private window: no
   row appears for it.
6. Optional: switch to Chrome with its switch on. Chrome asks Allow once. The running Brave agent keeps working, and
   offers **Restart in Chrome · …**.
7. If the repo's `.mcp.json` still sets `AIB_CHROME_DIR`, Claude Code sessions stay in that browser whatever Settings
   says (Decision 15). Remove it to let them follow Settings.

### Manual check, on the Windows laptop (after this wave)

Added to the windows-and-repo spec's laptop list:
1. Settings → Where agents browse lists the installed browsers from the registry, with Brave's profiles.
2. **Set it up** on a second profile opens File Explorer at its folder. After Load unpacked there, the row shows
   ✓ watcher, which confirms the Windows extension id of a copy.
3. Steps 3 and 4 of the Mac check: the tab lands in the chosen profile, and a new window for a profile with no window
   stays behind (first-task fact 1).

## Out of scope

- **Moving a running agent** to another profile or browser: only **Restart in** (cookies and logins differ).
- **Opening or launching a browser or a profile** for the user, or loading an extension for them.
- **Edge, Arc and Vivaldi** as places, until their switch is verified (wave 2B lists them with `agents` false). Opera
  isn't listed at all.
- **A Brain inbox per profile:** the readers stay in the primary copy's profile.
- **A place per task** ("start this one in Work"): the place is a Settings choice. Restart in covers the rest.
- **The Chrome copy of the side chat:** wave 5 and later.
- **Private windows for agents.**
- **Firefox and Safari.**
- **Telling Claude which profile it is in:** by design (Decision 16).
- **A profile picker for the app window's own browser:** wave 3's Settings, a separate choice.
