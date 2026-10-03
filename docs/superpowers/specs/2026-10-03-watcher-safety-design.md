# The watcher may do only what it needs; tab lists keep private titles private

Date: 2026-10-03.

## Status

Status: the user approved the design in chat and answered its four questions; this spec was written and reviewed by agents without a user review round.

- **Part of:** "The app as an app" (docs/superpowers/specs/2026-10-03-app-as-an-app-overview.md). This is wave 1, track
  1B, the safety fixes. It is built in parallel with track 1A, the Brain's delegation to an existing agent.
- **What the user chose that this relies on** (the brief's "The user's answers" and "Defaults we'll take"):
  - agents use the Brave profile "the user is signed in on", with the watcher loaded in that profile. Wave 1 reads
    that profile from the watcher (Decision 7); wave 4 adds the choice in Settings;
  - the default "Always allow stays in the app's Tools", taken for the side chat. This spec applies it to the
    watcher's Brain page too (Decision 3).
- **Evidence:** the investigation's findings (docs/superpowers/specs/2026-10-03-app-as-an-app-investigation.json,
  sections `sidechat` and `browsers`), and the code at HEAD, cited as file:line below.
- **Builds on:** the everyday-brave spec (BraveLink, the tab list, Hand over), the brain spec (the watcher and its
  Brain page), the safe-browsing spec (bot-check notifications).
- **Changes earlier decisions:**
  - the everyday-brave spec says the user's tab titles go to all of AI Browser's own pages
    (2026-10-02-everyday-brave-design.md:777-779) and lists every web tab of Brave. Now the list holds one profile, and
    the watcher's pages get no tab list at all;
  - the safe-browsing spec has the watcher's **Show me** send `watch` with the tab's target
    (2026-10-02-safe-browsing-design.md:739-740, :976-977). Now it sends `check_show` with the agent's id;
  - the watcher's Brain page loses **Always allow** (README.md:276-278 says it has it).
- **Later waves extend this:** wave 5's side chat adds its messages to the two tables defined here. Wave 4 replaces the
  one function that picks the agents' profile.

## Goal and success criteria

The goal is to close the two safety gaps the investigation found, and nothing more:

- **A watcher page can do too much.** The server refuses only a few message types from the watcher's origin
  (server.py:660-673). Everything else is accepted, including `new_task` with `adopt` (server.py:678-696) and the Tools
  writes (server.py:835-856). Measured with a throwaway server
  (`/private/tmp/claude-501/sidepanel-probe/gap/gap_probe.py`):
  - from the watcher's origin, `new_task` with `adopt: "U1"` handed the user's Brave tab U1 to a new agent (owner kind
    "handed");
  - `tool_allow` saved a lasting Always allow;
  - the watcher's Brain page says `hello` like AI Home (watcher/brain.js:36), so it gets the snapshot and every
    broadcast: every Brave tab's target id, title and address (server.py:944-949, :196-199), sessions, thumbnails and
    every agent's conversation.
- **AI Home's tab list leaks titles.**
  - TabWatch keeps only target, url and title for each page (tabs.py:65-70, :80-84). It never looks at the page's
    browser context.
  - BraveLink lists every web page as a "you" row (bravelink.py:122-133).
  - Measured in a throwaway Chrome (probe5.py): pages of a private window are on the browser endpoint, with their own
    context. So AI Home shows titles from private windows and from the user's other profiles.

Success means:

**The watcher may send only its list:**
- one table in server.py names every message type a page may send, and who may send it. A type missing from the table
  is dropped for everyone;
- the watcher's origin may send 22 types, some only with a condition. Every other type from it is dropped without an
  answer;
- `new_task` from the watcher's origin starts no agent, with or without `adopt`, and no tab of the user's becomes
  "handed";
- `tool_allow`, `tool_set` and `tool_forget` from the watcher change nothing. `permission` with `always` from the
  watcher saves nothing and doesn't answer the request;
- one table test covers every message type, for both senders.

**The watcher receives only its list:**
- watcher-origin sockets get 18 message types, some trimmed. They never get `tabs`, `thumb`, `thumbs`, `sessions`,
  `agent_event` or the Tools, workflow and skill messages;
- they never get a tab's target id: agent rows lose their tab fields, `check_request` loses `target`, and the
  notification's **Show me** asks by agent id;
- a test scans everything a watcher socket receives for the test's target ids and finds none.

**Tab lists keep private titles private:**
- AI Home lists the user's tabs from one profile only, the agents' profile (Decision 7);
- a user's tab in another profile or in a private window never gets a row, a title, an address or an id on any of AI
  Browser's pages;
- tabs in other profiles and private windows show only as a number: "4 more tabs in other profiles or private windows:
  not shown here";
- agents' tabs, Claude Code's tabs and tabs handed to an agent stay listed, whichever profile they are in;
- Hand over, `new_task` with `adopt`, and the Train form's page pick accept only a listed tab.

**Nothing else changes:**
- the inbox, drafts, the watch list, notifications, Continue and tab groups work as today;
- no new "Allow remote debugging?" question, no new connection to Brave, and no new extension permission.

## What the user sees

The fixes are mostly invisible. Two places change: AI Home's tab list, and the watcher's Brain page in Brave.

**AI Home's tab list:**
- It lists the web tabs of the Brave profile the watcher is loaded in. Without the watcher, it lists the profile used
  last, with the line: "Showing the Brave profile you used last. With the watcher loaded, this list stays on the
  watcher's profile." The same can show for up to half a minute after Brave connects, until the watcher wakes
  (Decision 7).
- If AI Browser can find neither profile, it lists only the AI's tabs, with the line: "Your tabs aren't listed: AI
  Browser can't tell which Brave profile is yours yet."
- Below the rows, one line counts the rest, for example: "4 more tabs in other profiles or private windows: not shown
  here." There is no line when the count is 0.
- An agent's tabs, Claude Code's tabs and tabs handed to an agent are listed as today, wherever they are.
- With no web page in that profile, the empty text reads "No web pages open in this profile."
- **Hand over** works on the rows shown, as today. Mission Control's "Your tabs" (track 1A) uses the same list.

**The watcher's Brain page in Brave:**
- A tool request's card offers **Allow once** and **Deny**.
- Under the buttons it says: "Always allow is in AI Home's Tools." (AI Home keeps its name and its Tools section in
  wave 3's app window, so the words last. Wave 5's side chat shows the same line.)
- AI Home, Mission Control and the chat panel keep all three buttons.

**Brave's notifications:**
- No visible change. **Show me** still brings the agent's tab to the front, and **Continue** still tells the agent to
  carry on.

**Nothing to do:**
- The watcher reloads itself when its files change (worker.js:86-92).
- Brave asks nothing new, and no setting changes.

## Decisions (with reasons)

1. **One table of who may send what, checked before anything else.**
   - `MESSAGE_RULES` in server.py lists every message type a page may send. For each type it says whether AI Browser's
     own pages may send it, and whether the watcher may.
   - `_handle` asks `may_send(role, message)` first, and drops the message when the answer is no. The four separate
     origin tests go (server.py:663, :666, :669, :672).
   - Why a table: today's list of refusals grew by hand, and the two measured gaps were types nobody thought to refuse.
     With a table, a type nobody classified does nothing, for anyone, so its own feature test fails at once. A row
     added to the table fails the table test until the test's copy says the same, so each new row is a decision
     written down twice.
   - A message whose `type` is missing or isn't a string is refused too. Today such a type reaches `kind in {...}`
     and raises `TypeError` for a list.
   - Why by role, not by origin string: wave 3 replaces the extension's origin with the app window's cookie. The roles
     ("app" and "watcher") stay, and only `_role(ws)` changes.
   - Why per origin, not per page: all watcher pages share one origin, and the `view` in `hello` is the page's own
     claim. The server cannot tell the worker from the Brain page, so every watcher page gets the same rights.
   - The one finer check that exists stays: watcher reports (`items` … `tab_grouped`) count only from the socket that
     said `hello` as the watcher (server.py:644-646).

2. **The watcher's list is what the watcher sends today, and no more.**
   - The 22 types come from the code:
     - the worker: its `hello` (link.js:36), its seven reports, `draft` from a notification, `permission` with Deny,
       `check_continue`, and **Show me** (worker.js:30, :80, :146, :238-241, :293-297, :316-330, :367-403);
     - the Brain page and the shared inbox code: `hello`, `brain`, `draft`, `approve`, `done`, `tell`, `hand`,
       `workflow_run` with an item, `watch_set`, `watch_remove`, `pause`, `style` and `permission`
       (watcher/brain.js:83-193, extension/brainui.js:85-116, :256, extension/permission.js:36-45).
   - `new_task` is refused from the watcher, with or without `adopt`. Nothing in the watcher sends it today. Wave 5 adds
     what the side chat needs, through this table.
   - `workflow_run` is allowed only with an `item`: that is the inbox's "Run <workflow>" on a message. A bare run, with
     any text, stays in AI Home.
     - Today a `workflow_run` with an item falls through to a bare run when the server has no Brain
       (server.py:877-880). It now does nothing then, so an item can never stand in for a bare run.
   - `check_continue` is allowed and `check_skip` is not, as today: Skip closes a tab (server.py:660-664).
   - `send`, `stop`, `close`, `model`, `watch`, `events`, `skills`, `thumbs`, the Tools, workflow and skill messages,
     hearing and the talk with the Brain are refused. After this change the watcher never sends them: today's only one,
     **Show me**'s `watch`, becomes `check_show` (Decision 6).

3. **No lasting "Always allow" from Brave.**
   - `permission` from the watcher counts only with `answer` "once" or "deny". `tools`, `tool_set`, `tool_allow` and
     `tool_forget` are for AI Browser's own pages only.
   - The watcher's Brain page shows **Allow once** and **Deny**, and the line "Always allow is in AI Home's Tools."
   - Why: `permission` with "always" calls `tools.allow_always` (agents.py:238-247). That is the same lasting power as
     `tool_allow`. Closing one and not the other would leave the gap open.
   - It also matches the default the user accepted for the side chat: "Always allow stays in the app's Tools".

4. **A refused message is dropped, with no answer.**
   - This is what the server already does with a refused `check_skip`, `hand_tab` or `brain_ask` (server.py:660-673).
   - With no answer, a page cannot map the table by trying types.
   - After this change nothing in the watcher sends a refused type. A watcher with older files reloads itself when it
     connects (worker.js:86-92, at most once a minute). Until then, an old **Always allow** button or an old **Show
     me** is dropped like any refused message: it changes nothing.

5. **What the watcher receives is a fixed list too, applied where every message leaves.**
   - `WATCHER_RECEIVES` holds 18 types. `for_watcher(message)` returns the message, a trimmed copy, or nothing.
   - It runs in `_write` (server.py:586-589). Every message to a socket passes there: direct answers, `_send_all`
     broadcasts (server.py:605-607) and `_to_watcher` (server.py:609-616). So a path added later is covered too.
   - Agent rows keep only `id`, `name`, `color`, `state` and `permission`. That is what the Brain page reads
     (watcher/brain.js:13-33, :116-134). The snapshot keeps only its agents.
   - Why: the Brain page gets every broadcast today. That includes `tabs` (every target, title and address),
     `sessions`, `thumb` pictures and every agent's `agent_event`.

6. **No target ids at all; Show me asks by agent.**
   - The notification's **Show me** sends `check_show {id}`. The server brings forward the tab where that agent's bot
     check waits.
   - `check_request` reaches the watcher without `target`. The notification no longer stores one.
   - Why: the rule is "no tab ids to watcher pages". The server already holds the check's tab (agents.py:313-322). One
     plain rule is easy to test: no target id in anything the watcher receives. The investigation allowed agent and
     handed tab ids, but nothing in the watcher needs them in wave 1.
   - Brave's own tab ids in `group_tab`, `tab_grouped` and `ungroup_tabs` stay. They are the watcher's own numbers: it
     sees every tab of its profile through its `tabs` permission.
   - AI Browser's own check cards keep sending `watch` with the target (extension/check.js:33).

7. **The agents' profile, for wave 1.**
   - The rule:
     - the Brave profile the watcher runs in, when it runs in exactly one;
     - otherwise the profile Brave used last (Chromium's default browser context);
     - otherwise none, and then no tab of the user's is listed.
   - How the watcher's profile is found:
     - the watcher's worker is a `service_worker` target, `chrome-extension://<watcher id>/worker.js`. Its
       `browserContextId` is its profile's context (measured, probe4.py);
     - BraveLink reads it from the target list its one connection already has. It never attaches to anything;
     - it remembers the context for the life of that connection, because a sleeping worker drops out of the list;
     - the watcher id is the one the app computes from the folder (run.py:206).
   - Right after Brave connects, the watcher's worker may still be asleep. Until it is first seen, the list follows the
     fallback. The worker wakes within half a minute on its own (its `reconnect` alarm, worker.js:410), connects to
     the app and shows in the target list. The list then switches to its profile.
   - Why the watcher's profile: the user chose to let the Brain into that profile. It doesn't move when focus moves.
     Wave 4 pins agents' tabs there. The overview's build order says the same: "titles only for the watcher's profile".
   - Why the fallback: without the watcher, agents' tabs open in the profile used last (measured, the investigation's
     `browsers` findings). So that is where agents work, and the brief's part 4 says "AI Home lists only the agents'
     profile". A user with one profile sees the list as today.
   - The same watcher folder loaded in two profiles gives two contexts under one id. The app can't tell which one
     groups the tabs, so it uses the fallback. Wave 4 gives each profile its own copy.
   - Wave 4 replaces `BraveLink.agents_context()` with the profile picked in Settings.

8. **Private windows are never listed; the count covers them without naming them.**
   - The watcher's manifest has no `incognito` key, so the watcher runs in "spanning" mode. Its worker lives in the
     regular profile, never in a private window's context (watcher/manifest.json:1-13).
   - The default context is never a private window's. Measured twice:
     - probe5.py (headful): a context-less `Target.createTarget` never went into a private window, even when the
       private window was opened last. A context-less `createTarget` uses that default (chromium
       target_handler.cc:110-121, as cited in the investigation);
     - for this spec, a throwaway headless Chrome 154 started with `--incognito` and a local test page: the page's
       only window was private, with its own context. Yet `defaultBrowserContextId` was the regular profile's
       context, and a context-less `createTarget` landed there. So headless Chrome honours `--incognito`, and test
       15 needs no visible window.
   - The count line covers other profiles and private windows together, and says so. CDP can't tell them apart:
     `TargetInfo` has no private flag, and `Target.getBrowserContexts` lists neither (probe5.py).
   - The count is a number on AI Browser's own page. It carries no title, address or id.
   - A throwaway-Chrome test pins the Chromium behaviour this rests on (Testing, test 15).

9. **The AI's tabs stay listed wherever they are.**
   - Rows owned by an agent or a Claude Code session, and tabs handed to an agent, are listed in any profile.
   - Why: the user must see, Watch and Take back what the AI holds. In wave 1, agents' tabs can still land in another
     profile than the watcher's.
   - A row marked "Brain" is the user's own tab (bravelink.py:151-156). It follows the profile rule.

10. **Only a listed tab can be handed over or read.**
    - `_handable` already reads `tabs()` (server.py:499-504). So `hand_tab` and `new_task` with `adopt` accept only a
      listed tab, with no new code.
    - `page_text(target, picked=True)` (the Train form) reads any target today (bravelink.py:178-182). It now reads only
      a listed one.
    - Why: a tab the user can't see in AI Browser can't be given to an agent, and its text can't go to Claude.

11. **Context ids stay inside BraveLink.**
    - Rows sent to pages keep `target`, `url`, `title` and `owner`, as today.
    - The count and the profile's source go out as one small `tab_scope` object.

12. **Two steps, so this track never edits a file track 1A edits.**
    - **Step 1, now:**
      - code: server.py, tabs.py, bravelink.py, run.py (one line), extension/permission.js, watcher/brain.js,
        watcher/notify.js;
      - tests: tests/fake_brave.py, the new tests/test_watcher_rules.py, and changes in tests/test_app_server.py,
        tests/test_bravelink.py, tests/test_tabwatch.py, tests/test_watcher.py and tests/test_ai_home_phase2.py.
    - **Step 2, after 1A has merged:** extension/tablist.js, extension/home.js, README.md and tests/test_home.py. Track
      1A changes tablist.js, home.js and tests/test_home.py (2026-10-03-brain-delegation-design.md, "Files, and the
      other wave-1 track"). Step 2 still lands in wave 1, before wave 2 starts and before wave 3 moves the pages.
    - 1A's own server.py change, and its tests in tests/test_app_server.py, land after step 1. Each message type 1A
      adds needs a row in `MESSAGE_RULES`, or it does nothing. 1A adds `tell_confirm` and `tell_dismiss`
      (2026-10-03-brain-delegation-design.md, "`app/server.py` (after 1B)"): both are app-only rows, so the table
      test's copy grows to 56 types. 1A's `from_watcher` flag for `tell` reads `self._role(ws) == "watcher"`.
    - A type the watcher's Brain page must send to keep the inbox working may allow the watcher only if it can't give
      an agent a tab of the user's, save a lasting allow, connect to Brave, talk or listen, skip a check or close a tab.

13. **The same on Windows.**
    - Nothing here depends on the OS. Browser contexts, service-worker targets and private windows are Chromium's own,
      and Brave on Windows reports them the same way through the same one connection.
    - The watcher's id is computed from its folder as today (run.py:206). The junction case is already tested
      (tests/test_app_server.py:1139-1163).
    - Tests that use the DevTools pipe fixtures are skipped on Windows, as today (tests/conftest.py:26-36): tests 9, 10,
      19, 20 and 23 below. The others run there, test 15 whenever Chrome is installed.

## Messages / interfaces

### server.py: the table of what pages may send

The constants at server.py:50-61 stay as names. A new table sits beside them:

```python
@dataclass(frozen=True)
class Rule:
    app: bool = True                                # AI Browser's own pages
    watcher: bool | Callable[[dict], bool] = False  # Brave's watcher: no, yes, or yes when the check passes

MESSAGE_RULES: dict[str, Rule] = {...}              # every type a page may send (the table below)

def may_send(role: str, message: dict) -> bool:
    """role is "app" or "watcher". An unknown type, a message without one, or a type that isn't a string is never
    allowed."""
```

These are the rules. "yes" means allowed, "no" means dropped.

| Type | App pages | Watcher | Watcher condition |
|---|---|---|---|
| `hello` | yes | yes | |
| `items`, `replied`, `thread`, `filled`, `reader_status`, `watcher_caps`, `tab_grouped` | no | yes | only from the socket that said `hello` as the watcher (server.py:644-646, kept) |
| `brain`, `draft`, `approve`, `hand`, `done`, `tell`, `watch_set`, `watch_remove`, `pause`, `style` | yes | yes | |
| `workflow_run` | yes | only with an item | `item` is a non-empty string |
| `workflows`, `workflow_save`, `workflow_delete` | yes | no | |
| `permission` | yes | only once or deny | `answer` is "once" or "deny" |
| `tools`, `tool_set`, `tool_allow`, `tool_forget` | yes | no | |
| `skills`, `skill_draft`, `skill_save` | yes | no | |
| `hearing`, `hearing_download`, `hearing_cancel`, `listen_start`, `listen_chunk`, `listen_end`, `listen_cancel` | yes | no | |
| `brain_ask`, `brain_confirm`, `brain_dismiss` | yes | no | |
| `check_continue` | yes | yes | |
| `check_skip` | yes | no | |
| `check_show` (new) | yes | yes | |
| `brave_connect`, `hand_tab`, `take_back` | yes | no | |
| `new_task` | yes | no | with or without `adopt` |
| `send`, `stop`, `close`, `model` | yes | no | |
| `watch`, `events`, `thumbs` | yes | no | |

That is 54 types: 22 allowed for the watcher, 47 for the app's pages (all but the watcher's seven reports).

**In `AppServer`:**
- `_role(ws) -> "app" | "watcher"`: "watcher" when `self._origin_of[ws]` is in `self._watcher_origins`, else "app".
  The origin is checked when the socket opens (server.py:553-565), so every open socket has a role.
- `_handle` (server.py:634): its first step is `if not may_send(self._role(ws), message): return`. The origin tests at
  server.py:663, :666, :669 and :672 go. The `hello` branch for the watcher (server.py:636-643) and the reports check
  (server.py:644-646) stay.
- `check_show {id}` (new) joins `CHECK_MESSAGES` (server.py:60). When agent `id` holds a bot check without a `live`
  link, and a tab source is attached, the server calls `self.tabs.watch(agent.check["target"])`. Otherwise it does
  nothing. It never opens a connection: BraveLink's `watch` uses the one it has (bravelink.py:163-166).
- `_workflow_command` (server.py:876-881): a `workflow_run` with an `item` runs only through the Brain. With no Brain
  it does nothing, instead of falling through to a bare run.

### server.py: what the watcher receives

```python
WATCHER_RECEIVES = frozenset({...})                # the 18 types below
WATCHER_AGENT_FIELDS = ("id", "name", "color", "state", "permission")

def for_watcher(message: dict) -> dict | None:
    """What a watcher-origin socket may get: the message, a trimmed copy, or None. It never changes its input,
    because _send_all puts one dict in every queue."""
```

The 18 types:
- **for the worker:** `ping`, `error`, `watcher_hello`, `watch_list`, `notify`, `permission_request`, `check_request`,
  `group_tab`, `ungroup_tabs`, `open_thread`, `fill_reply`;
- **for the Brain page:** `snapshot`, `agent`, `agent_closed`, `brain_snapshot`, `brain_item`, `brain_item_gone`,
  `brain_state`.

Three are trimmed:
- `snapshot` becomes `{"type": "snapshot", "agents": [<trimmed row>, ...]}`, with no `tabs`, `sessions`, `browser`,
  `skills_summary`, `max_working` or `default_model`;
- `agent` becomes `{"type": "agent", "agent": <row with WATCHER_AGENT_FIELDS only>}`. Gone: `tabs`, `adopted`,
  `working_tab`, `check` (it holds the target), `status`, `last_action` and the rest;
- `check_request` loses `target`. It keeps `agent`, `name`, `site`, `what` and `live`.

Everything else is dropped for watcher sockets: `tabs`, `thumb`, `thumbs`, `sessions`, `browser`, `agent_event`,
`agent_events`, `created`, `brain_activity`, `brain_answer`, `hearing_status`, `heard`, `tools_snapshot`,
`workflows_snapshot`, `workflow_saved`, `skills`, `skill_drafted`, `skill_diff`, `skill_saved`, and any type added
later.

**`_write(ws, queue)`** (server.py:586-589) reads the role once when it starts. For a watcher socket it passes each
message through `for_watcher`, and skips it on `None`.

### server.py: the tab list's scope

- The `tabs` broadcast gains `tab_scope` when the tab source has `scope()` (BraveLink does; AI Browser's own TabWatch
  doesn't):
  `{"type": "tabs", "tabs": [...], "tab_scope": {"profile": "watcher" | "last_used" | "none", "elsewhere": 4}}`.
  It is built in `attach_tabs` (server.py:196-199) and in `attach_brave` (server.py:483).
- The snapshot (server.py:944-949) gains the same `tab_scope`, or `null` in AI Browser mode.
- Watcher sockets get neither: `tabs` is dropped, and their snapshot is trimmed.

### tabs.py: TabWatch

- Each page record gains `context`, the page's `browserContextId` (tabs.py:65-70 and :80-84).
- `tabs()` (tabs.py:55-59) still returns rows with exactly `target`, `url` and `title`. AI Browser mode is unchanged.
- **New `pages()`:** the same rows plus `context`, for BraveLink.
- **Service workers:** `service_worker` targets are kept too, as `{target: {"url", "context"}}`, from
  `Target.targetCreated`, `Target.targetDestroyed` and the `Target.getTargets` refresh (tabs.py:76-87).
  `Target.setDiscoverTargets` and `Target.getTargets` already report them: their default filter leaves out only
  `browser` and `tab` targets.
  - They are kept apart from the pages. `tabs()`, `pages()` and `has_pages()` never count a worker, so AI Browser's
    window check (run.py:254) still ends the app when its last page closes.
  - New `worker_contexts(extension_id) -> set[str]`: the contexts of workers whose url starts with
    `chrome-extension://<extension_id>/`. An empty id matches nothing.
- **New `default_context: str | None`:** `defaultBrowserContextId` from `Target.getBrowserContexts`. It is read at
  start and in each refresh round (every 1.5 s). A failed read keeps the last value.
- `on_change` also fires when a worker comes or goes, or the default context changes.
- All of these are browser-level reads on the connection TabWatch already has. None attaches to a tab.

### bravelink.py: BraveLink

- **`BraveLink(folder, watcher_id: str = "", allow_wait=..., every=...)`**: the watcher's extension id. Empty means no
  watcher, so the fallback.
- **`_watcher_contexts: set[str]`**: every context the watcher's worker has been seen in on this connection. It is
  emptied when `connect()` makes a new TabWatch (bravelink.py:55).
- **New `agents_context() -> tuple[str | None, str]`**: `(context, source)`, where source is "watcher", "last_used" or
  "none" (Decision 7).
- **`tabs()`** (bravelink.py:122-133) lists:
  - a page whose owner is an agent, a session or "handed", when it is a web page, or one of the AI's own blank tabs
    (as today), in any context;
  - a web page with no owner, or marked "brain", only when its `context` is the agents' context.

  Rows are `{target, url, title, owner}`, with no `context`.
- **New `scope() -> {"profile": source, "elsewhere": n}`**: `n` counts the web pages (http and https) that `tabs()`
  leaves out, which are those with no owner or marked "brain" outside the agents' context. That covers other
  profiles and private windows (Decision 8).
- **`_changed()`** (bravelink.py:116-120) calls back only when the rows or the scope differ from the last pair sent,
  so a worker waking or sleeping doesn't resend the list. `connect()` and a lost connection forget that pair, so they
  always call back.
- **`page_text(target, picked=True)`** (bravelink.py:178-182) reads only a target that `tabs()` lists. It returns ""
  otherwise, before anything attaches.
- `mark_brain` (bravelink.py:151-156) keeps its code. It already searches `tabs()`, which now holds only the agents'
  profile.

### run.py

- run.py:211 becomes `brave = BraveLink(own, watcher_id=extension_id_for(watcher))`. That is the same id the app
  allows as the watcher's origin (run.py:206).

### The watcher's files and the shared card

- **extension/permission.js:** `permissionCard(request, send, agentName = "", { always = true } = {})`. With
  `always: false` there is no Always allow button. Instead there is a muted line, set with `textContent`: "Always allow
  is in AI Home's Tools." AI Home, Mission Control and the panel call it as today (home.js:132, mission.js:289,
  panel.js:87). The file's header comment (permission.js:1-2) says the watcher's card has no Always allow.
- **watcher/brain.js:21-22** passes `{ always: false }`.
- **watcher/notify.js:**
  - `checkNotification` (notify.js:32-40) keeps `{ check: { agent, live } }` in its note, with no `target`;
  - `checkAction` (notify.js:44-49): Continue sends `check_continue` as today; a valid `live` link opens as today;
    otherwise **Show me** sends `{ type: "check_show", id: check.agent }`.
- worker.js doesn't change: `doCheck` sends whatever `checkAction` returns (worker.js:293-297).
- These files are in the watcher's folder (brain/watcher.py:20 shares permission.js). So the watcher's build changes,
  and the watcher reloads itself when it next connects.

### Step 2 (after track 1A merges): AI Home's line and the README

- **extension/tablist.js**, `render(tabs, { brave, ownerOf, scope })` (tablist.js:82-118): after the rows, up to two
  muted lines, each set with `textContent`. They are updated in place on each render, and removed when not needed:
  - `p.scope-source`, for the profile's source:
    - `scope.profile === "last_used"`: "Showing the Brave profile you used last. With the watcher loaded, this list
      stays on the watcher's profile.";
    - `scope.profile === "none"`: "Your tabs aren't listed: AI Browser can't tell which Brave profile is yours yet.";
  - `p.elsewhere`, for the count, when `scope.elsewhere > 0`: "<n> more tabs in other profiles or private windows:
    not shown here." ("1 more tab" for one);
  - with `scope` set and no rows, the empty text (tablist.js:115-117, today "No web pages open in your browser.")
    reads "No web pages open in this profile."
- **extension/home.js:** keeps `tabScope` from `snapshot.tab_scope` (home.js:388) and from each `tabs` message
  (home.js:424-427), and passes it to `tabList.render` (home.js:196-197).
- **README.md:**
  - :183 becomes "**Tabs:** the web tabs of the Brave profile the watcher is in (without the watcher, the profile you
    used last), each marked with whose it is: an agent's, Claude Code's, the Brain's, or yours. Other profiles and
    private windows are only counted, never listed." Its three sub-bullets (:184-186) stay;
  - :276-278: AI Home's agent row, Mission Control and the chat beside its tab offer **Allow once**, **Always allow**
    and **Deny**. The watcher's Brain page in Brave offers **Allow once** and **Deny**, because Always allow is kept
    for AI Home's Tools;
  - :453-455: "AI Home shows them" becomes "AI Home shows the ones in the agents' profile (other profiles and private
    windows only as a count)".

### For the later waves

- **Wave 2 (the relay):** BraveLink's connection becomes the relay's upstream. It must keep `Target.getBrowserContexts`
  and service-worker discovery for the app's own use. The per-agent allowlist doesn't apply to them. run.py keeps
  passing `watcher_id` beside the relay's new `tokens` (cdp-relay, its `app/run.py` interface).
- **Wave 3 (the app window):** `_role(ws)` maps the window's cookie session to "app". `_write`'s filter and the table
  stay as they are.
- **Wave 4 (profiles):** `BraveLink.agents_context()` returns the context of the chosen profile, found through that
  profile's watcher copy. `watcher_id` becomes a set of ids. `tab_scope.profile`'s `"watcher"` becomes `"chosen"`,
  and the tests here that expect `"watcher"` (12-14 and 20) follow (browser-profile-choice, Decision 10).
- **Wave 5 (the side chat):** it adds rows to `MESSAGE_RULES`, for example `new_task` without `adopt`, `send`,
  `events`, `start_here`, `hand_here` and `take_back_here`. It adds types to `WATCHER_RECEIVES`, for example
  `agent_event`, `agent_events`, `created`, `tab_owners` and `hand_result`, and fields to `WATCHER_AGENT_FIELDS`. Each
  addition updates the two table tests. Its chat uses this spec's card line, "Always allow is in AI Home's Tools.",
  unchanged.
- **The running counts** of both tables, wave by wave, are in the brain-delegation spec's "Coordination across the
  seven specs".

## Safety

The binding rules, and how this spec keeps each one:

- **Brave's "Allow remote debugging?" question and its automation bar are never clicked, answered, hidden or
  suppressed.** This spec opens no connection. The new reads (`Target.getBrowserContexts`, service-worker targets) use
  BraveLink's one existing connection, which opens only right after something the user did (bravelink.py:45-66,
  server.py:485-488).
- **No spoofing, no bot-check bypass, no typed passwords.** Nothing here touches a page.
- **Page and message text is data.**
  - Tab titles stay text. The new count line is set with `textContent`, as the rows are (tablist.js:17-19).
  - A message from the watcher is checked against the table before anything reads its fields.
  - The watcher's Brain page renders the trimmed agent rows as it does today, as text.
- **Nothing leaves the machine without a knowing choice.**
  - Everything stays on 127.0.0.1.
  - Context ids never leave BraveLink.
  - Titles from other profiles and private windows no longer reach even AI Browser's own pages.
- **Downloads need the user's OK:** unchanged.
- **Hand-over and take-back are clicks only:**
  - the watcher may not send `hand_tab`, `take_back` or `new_task` with `adopt`;
  - Hand over works only on a listed tab;
  - the Brain and voice can't do either (unchanged).
- **The Brain only proposes:** the watcher may not talk to the Brain (`brain_ask`, `brain_confirm`, `brain_dismiss`
  are app-only), and `tell` keeps track 1A's card rule.
- **The watcher gains nothing:** no new permission and no `debugger`. Its one new message, `check_show`, replaces
  today's `watch`: it can bring forward only the tab where an agent's bot check waits, never a tab it names. It loses
  `new_task`, Always allow, the Tools writes, stop, close, send, events, `watch` and the tab list.

## Testing

Tests 1-10, 12-17, 19-20 and 22-23 fail before the change and pass after it. Tests 11, 18 and 21 are guards: they pass
before and must keep passing. Tests never reach the user's real Brave or Chrome (the
autouse fixture in tests/conftest.py:53-60). Throwaway Chromes are started with their own temporary profiles. Run the
touched files, not the whole suite. On Windows, tests 9, 10, 19, 20 and 23 are skipped with the other pipe-fixture
tests (Decision 13).

**New file tests/test_watcher_rules.py** (helpers from tests/test_app_server.py and tests/fake_brave.py):

1. `test_the_message_table_covers_every_type_for_both_roles` (pure, parametrized):
   - the test holds its own copy of the table above. It asserts that `set(MESSAGE_RULES)` equals it, 54 types. A row
     added to `MESSAGE_RULES` fails here until the copy has it too;
   - for every type and both roles, `may_send(role, {"type": type, ...})` matches the copy;
   - conditional rows: `workflow_run` with `item: "i1"` (watcher yes), with no item or `""` (no); `permission` with
     "once" and "deny" (yes), "always" or no answer (no); `new_task` with and without `adopt` (watcher no, app yes);
   - an unknown type, a message with no type, and a type that is a list or a number are refused for both roles, with
     no exception.
   - Before: `MESSAGE_RULES` and `may_send` don't exist.
2. `test_what_the_watcher_receives_is_a_fixed_list` (pure):
   - for each type the server sends (the 18 above plus every dropped type named above), `for_watcher` keeps exactly
     `WATCHER_RECEIVES`;
   - a snapshot comes out as only `type` and trimmed agents;
   - an agent row comes out with only `WATCHER_AGENT_FIELDS`;
   - `check_request` comes out with no `target`;
   - the input dict is unchanged afterwards;
   - every type that `_to_watcher` is called with (`watcher_hello`, `watch_list`, `notify`, `open_thread`,
     `fill_reply`, `group_tab`, `ungroup_tabs`, `permission_request`, `check_request`) is kept.
   - Before: `for_watcher` doesn't exist.
3. `test_the_watcher_cannot_start_an_agent_in_a_users_tab` (socket; FakeBrave with U1):
   - from the watcher's origin, `new_task` with `adopt: "U1"`, then without `adopt`: no agent, no `created`, and U1
     has no owner;
   - from AI Home's origin, the same `new_task` with `adopt` starts an agent with U1 handed (control).
   - Before: measured, agent a1 starts and U1 becomes "handed".
4. `test_the_watcher_cannot_save_always_allow` (socket; an `AppServer` with `tools=`, and an agent waiting for a tool,
   made with `manager()` and `asking()` from tests/test_tools.py:16-19, :51-60, as test_tools.py:199-234 does):
   - from the watcher's origin, `tool_allow` for that tool, then `permission` with "always": `tools.always()` stays
     empty and the agent still waits;
   - then `permission` with "once" from the watcher: the agent goes on, and `tools.always()` is still empty.
   - Before: both writes save the tool in tools.json.
5. `test_the_watcher_origin_may_send_nothing_else` (socket sweep, built like
   test_the_watcher_can_neither_talk_nor_listen, tests/test_app_server.py:1053):
   - set-up: one server with the Brain, a ToolsConfig, a WorkflowStore with one workflow and its runner, a SkillWriter,
     hearing, and FakeBrave with U1 (state "ready"). Agent a1 has its own tab T1, holds a bot check on it, and has U2
     handed. So every sample below would do something from AI Home;
   - a watcher-origin socket says `hello` with view "brain", then sends one real-looking sample of every type the table
     refuses for the watcher: `close`, `stop`, `send` and `model` for a1, `watch` U1, `events` a1, `thumbs`, `skills`,
     `tools` with `refresh: true`, `tool_set`, `tool_forget`, `workflows`, `workflow_save`, `workflow_delete`,
     `workflow_run` without an item, `skill_draft`, `skill_save`, the hearing messages, `brain_ask`, `check_skip` for
     a1, `brave_connect`, `hand_tab` U1, `take_back` U2 and `new_task`;
   - afterwards:
     - agent a1 is open and unchanged: its model, its state, its check, `adopted == ["U2"]`, nothing queued;
     - the fake claude's log shows no new call: no message, no probe, no skill draft, no talk;
     - no other agent exists, `brave.connects == 0`, `brave.watched == []` and nothing was closed;
     - tools.json, the workflows folder and the skills folder are unchanged;
   - the socket received none of: `created`, `agent_events`, `thumbs`, `skills`, `tools_snapshot`,
     `workflows_snapshot`, `workflow_saved`, `skill_drafted`, `skill_saved`, `hearing_status`, `heard`, `brain_answer`.
     (Test 1 pins the read-only requests, `events`, `skills`, `thumbs`, `tools` and `workflows`: their only effect is
     an answer, which `for_watcher` would drop anyway.);
   - the same `close` from AI Home's origin then closes a1 (control: the samples are real);
   - a second server with workflows and no Brain: `workflow_run` with an `item`, from AI Home's origin, starts nothing.
   - Before: `close`, `stop`, `send`, `model`, `tools` with refresh, `tool_set`, `tool_forget`, `workflow_save`,
     `workflow_delete`, the bare `workflow_run`, `skill_draft`, `skill_save`, `watch` and `new_task` take effect from
     the watcher (`check_skip`, the Brave messages, hearing and the talk were refused already), and the no-Brain
     `workflow_run` starts the workflow.
6. `test_watcher_sockets_get_no_target_ids` (socket):
   - set-up: FakeBrave with pages `U1-7f3a` and `U2-7f3a`; agent a1 with tab `T1-7f3a`, handed `U2-7f3a`, a bot check
     on `T1-7f3a` and a waiting tool request; a session `cc-x` with tab `S1-7f3a`;
   - sockets: a watcher worker (`hello` view "watcher"), a watcher Brain page (`hello` view "brain") and AI Home;
   - trigger `brave.changed()`, the agent's changes, the check, a sessions change and a `thumb` broadcast, then collect
     for 1 s;
   - no text "-7f3a" appears in anything either watcher socket received, and their types are a subset of
     `WATCHER_RECEIVES`;
   - the Brain page still got a1's row with `permission`, so its card works. The worker got `check_request` and
     `permission_request`;
   - AI Home got `tabs` with `U1-7f3a` (control).
   - Before: the snapshot's `tabs`, the agent rows, `sessions` and `check_request.target` all carry them.
7. `test_show_me_from_the_watcher_brings_the_checks_tab_forward` (socket; FakeBrave):
   - `check_show {id: "a1"}` from the watcher, with a1 held at a check on T1: `brave.watched == ["T1"]`;
   - `check_show` for an agent with no check, or with a `live` link: nothing;
   - `watch {target: "U1"}` from the watcher: nothing.
   - Before: `check_show` is unknown, and `watch` from the watcher brings U1 forward.

**Changed tests:**

8. tests/test_app_server.py:449, `test_check_reports_are_checked_then_reach_pages_and_the_watcher`: the watcher's
   `check_request` has no `target`. An AI Home socket in the same test still gets it with `"target": "T1"`.
9. tests/test_watcher.py:380, `test_a_bot_check_gets_one_notification_with_show_me_and_continue`:
   - the note stored for the `check_request` (sent with `"target": "T1"`, :381-382) has `check.agent == "a1"` and no
     `target` key (:383-385 asks for `target === 'T1'` today);
   - `checkNotification({..., target: 'T1', live: null})` (:392-393) returns a note with no `target`, even though its
     input has one. This pins notify.js itself: after the change the server's filter alone would already keep `target`
     out of the stored note;
   - `checkAction(note, 0)` returns `{"send": {"type": "check_show", "id": "a1"}}` (:399);
   - the valid live link still opens (:400-403);
   - the forged live link (:404-408) still gives `live == ""`, and its Show me now returns
     `{"send": {"type": "check_show", "id": "a1"}}`, not `watch`.
10. tests/test_ai_home_phase2.py:148, `test_the_watcher_shows_a_permission_request`:
    - the watcher's card has `.allow-once` and `.deny` and no `.allow-always`, and its text includes "Always allow is in
      AI Home's Tools.";
    - Deny works as today;
    - in the same page, `import('./permission.js')` (as tests/test_watcher.py:364 imports notify.js) then
      `permissionCard({...}, () => true)` with no options still has `.allow-always`, as AI Home's card does.
11. tests/test_app_server.py:737, `test_the_watcher_may_not_hand_tabs_or_connect`: unchanged, and still passing, now
    through the table.

**BraveLink with a fake Brave** (tests/test_bravelink.py). `FakePort` (tests/test_bravelink.py:16-68) gains:
- a `context` on each page, "C0" unless the test gives one, sent as `browserContextId` in `targetCreated` and
  `getTargets`;
- a list of service workers (`{target, url, context}`), reported the same way with type `service_worker`;
- an answer to `Target.getBrowserContexts`: `{"browserContextIds": [], "defaultBrowserContextId": "C0"}` unless
  `set_default(context)` changes it. `set_default(None)` makes it answer an error;
- `destroy(target)`, which sends `Target.targetDestroyed`.

With "C0" everywhere by default, the existing FakePort tests keep their meaning: their pages are in the profile used
last, so they are listed as today. That includes test_the_brain_is_marked_only_when_one_tab_matches
(tests/test_bravelink.py:162), which needs no change.

12. `test_only_the_agents_profile_is_listed_and_the_rest_is_counted`:
    - pages: U1 "SECRET-W" in context W; U2 "SECRET-P" in P (another profile); U3 "SECRET-X" in X (a private window);
      A1 in P, owned by agent a1; H1 in W, handed to a1;
    - the watcher's worker is in W, and the default context is P;
    - `tabs()` lists U1, A1 and H1 only, and no row has a `context` key;
    - no title "SECRET-P" or "SECRET-X" appears in any row;
    - `scope() == {"profile": "watcher", "elsewhere": 2}`.
    - Before: U2 and U3 are listed as "you", with their titles.
13. `test_without_the_watcher_the_profile_used_last_is_listed`:
    - with no watcher worker, the scope is "last_used" and P's tabs are listed;
    - after `set_default("W")`, W's tabs are listed and the count follows;
    - a watcher worker in two contexts also gives "last_used".
14. `test_the_watchers_profile_outlives_its_sleeping_worker_but_not_the_connection`:
    - after `destroy(worker)`, the scope stays "watcher";
    - after Brave restarts (`port.stop()`, a new port, `connect()`), it is "last_used" until the worker shows again;
    - workers are never pages: with the worker and no page, the TabWatch's `tabs()` and `pages()` are empty and
      `has_pages()` is False.
15. `test_a_private_window_is_never_listed_in_a_throwaway_chrome` (`@CHROME`):
    - a throwaway headless Chrome from `chrome.launch(folder, headless=True, extra_args=("--incognito", base +
      "privacy.html"))` (chrome.py:164-178), with `base` from `testpages.serve_host()`, shows the test page in a
      private window, in a context of its own. (In the measurement an `about:blank#…` start page showed there as
      `chrome://newtab/`, which is no web page, so the test uses a real one.);
    - a context-less `Target.createTarget` gives a regular page;
    - a BraveLink with no watcher id lists the regular page only, with `scope()["elsewhere"] == 1`, and no row has the
      private page's target or its title;
    - TabWatch's `default_context` is the regular page's context, not the private page's.
    - Headless Chrome 154 was measured doing all of this for this spec (Decision 8).
16. `test_with_no_profile_known_no_tab_of_the_users_is_listed`: `Target.getBrowserContexts` answers an error and no
    worker is seen. The scope is "none", only the AI's rows are listed, and every user web page is counted.
17. `test_a_hidden_tab_cannot_be_read_or_marked` (test 12's pages): `page_text("U2", picked=True) == ""` and U2 is
    never attached; `mark_brain(<U2's url>)` marks nothing. `page_text("U1", picked=True)` still reads U1 (control).
    - Before: U2's text is read (bravelink.py:180 lets any picked target through).
18. The existing `test_the_users_tabs_are_listed_but_never_attached` (tests/test_bravelink.py:126) keeps its pages,
    now in "C0", the profile used last. It passes as before, plus an assertion that rows have no `context`.

**TabWatch and the watcher in a throwaway Chrome:**

19. tests/test_tabwatch.py, `test_pages_carry_their_context_and_workers_are_seen` (the `app_browser` fixture,
    tests/test_tabwatch.py:13-24):
    - every page in `pages()` carries the same non-empty context, and `default_context` equals it;
    - `worker_contexts(app.extension_id)` is that one context;
    - `tabs()` rows have exactly `target`, `url` and `title`.
20. tests/test_watcher.py, `test_the_watchers_profile_is_found_from_its_worker` (the `watcher` fixture,
    tests/test_watcher.py:56-97): a BraveLink on the fixture's Chrome, with the fixture's extension id as `watcher_id`,
    reports `agents_context()` with source "watcher". A context-less `createTarget` page is listed in it.
21. tests/test_watcher.py, `test_the_watcher_never_runs_in_private_windows` (pure): watcher/manifest.json has no
    `incognito` key, or it is "spanning".

**Server and AI Home:**

22. tests/test_app_server.py, `test_the_tab_list_carries_its_scope`:
    - FakeBrave (tests/fake_brave.py gains `scope()`, by default `{"profile": "watcher", "elsewhere": 0}`) set to
      `{"profile": "watcher", "elsewhere": 2}`;
    - AI Home's snapshot has that `tab_scope`, and so does the `tabs` message after `brave.changed()`;
    - a watcher-origin socket gets neither;
    - a server in AI Browser mode (StubTabs, tests/test_app_server.py:165, which has no `scope()`) sends
      `"tab_scope": null` in its snapshot.
23. Step 2: tests/test_home.py, `test_the_tab_list_counts_what_it_doesnt_show` (next to
    test_the_tab_list_marks_owners_and_hands_tabs_over, tests/test_home.py:253):
    - with `elsewhere: 3`, `p.elsewhere` reads "3 more tabs in other profiles or private windows: not shown here.",
      and with `elsewhere: 1` it reads "1 more tab in other profiles or private windows: not shown here.";
    - with "last_used", the "Showing the Brave profile you used last…" line shows;
    - with "none", the "Your tabs aren't listed…" line shows;
    - with `elsewhere: 0` and "watcher", there is no line;
    - with no rows, the empty text reads "No web pages open in this profile."

## Out of scope

- **The side chat's messages** (wave 5): `new_task` without `adopt`, `send`, `events`, `start_here`, `hand_here`,
  `take_back_here`, `tab_owners`, `hand_result`, and the panel's agent fields. Wave 5 adds them to the tables here.
- **Choosing the agents' profile** in Settings, per-profile watcher copies, and opening agents' tabs through the
  watcher (wave 4). Wave 4 replaces `agents_context()`.
- **The relay** (wave 2). Until then each agent's engine still gets other tabs' `Target` events, as today. They never
  reach a tool result, the task log or a prompt (everyday-brave spec).
- **Telling private windows apart from other profiles** in the count. CDP gives no way to (Decision 8).
- **AI Browser's own Chrome's tab list** (AI Browser mode): unchanged. That Chrome goes away in wave 3.
- **Proving which watcher page sent a message:** not possible with one shared origin. Rights stay per origin.
- **The watcher's promise text:** unchanged here. Wave 5 rewrites it.
- **A Chrome copy of the watcher.**
