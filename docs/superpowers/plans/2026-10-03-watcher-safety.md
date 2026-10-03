# Watcher Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Brave's watcher may send only the 22 message types it needs and receives only 18 (trimmed, never a tab's
target id), and AI Home lists the user's tabs from one Brave profile only, counting other profiles and private windows
without naming them.

**Architecture:**
- **What pages may send:** one table, `MESSAGE_RULES` in `app/server.py`, says for every message type whether AI
  Browser's own pages ("app") and Brave's watcher ("watcher") may send it. `_handle` asks `may_send(role, message)`
  first and drops a refused message with no answer. The four origin tests inside `_handle` go.
- **What the watcher receives:** `for_watcher(message)` returns the message, a trimmed copy, or nothing. It runs in
  `_write`, which every message to a socket passes through. Agent rows keep five fields; `check_request` loses
  `target`; Show me asks by agent id (`check_show`).
- **One profile in the tab list:** `TabWatch` keeps each page's `browserContextId`, the service workers, and the
  default context, on the connection it already has. `BraveLink` picks the agents' profile (the watcher's, else the
  one Brave used last, else none), lists the user's web tabs of that profile and the AI's tabs anywhere, and counts the
  rest. The server sends that count as `tab_scope`; AI Home shows it as one muted line.
- **No lasting Always allow from Brave:** the watcher's Brain page draws the tool card with Allow once and Deny only,
  and the table refuses `permission` with "always" and the Tools writes from the watcher.

**Tech Stack:**
- Python 3.12: asyncio, Starlette and uvicorn, websockets, the app's own CDP client (`ai_browser.cdp.CDP`);
- MV3 extensions in plain JS (ES modules): the watcher (`app/watcher/`) and AI Browser's own pages
  (`app/extension/`);
- pytest with the fake `claude`, `FakeBrave` and `FakePort` (`tests/fake_brave.py`), the `watcher` and `home`
  fixtures (a throwaway headless Chrome over the DevTools pipe), and throwaway Chromes started by `chrome.launch`.

**Spec:** `docs/superpowers/specs/2026-10-03-watcher-safety-design.md`

**Build order and branch:**
- **Before this plan.** The cdp-relay spec (one shared connection) is built first and is on `main` before this branch
  starts. Create the branch `watcher-safety` from that `main`.
- **Wave A** (this plan): brain-delegation, watcher-safety and browser-detection, built at the same time on their own
  branches. Wave B (app-window) starts only once all three are on `main`.
- **Part 1 (Tasks 1-9)** is the spec's step 1. It touches no file brain-delegation touches except `app/server.py` and
  `tests/test_app_server.py`, where each side adds its own lines. browser-detection touches only `browsers.py` and
  `platforms.py`: no shared file.
- **Part 2 (Tasks 10-12)** is the spec's step 2. It starts only once brain-delegation is on `main`: merge `main` into
  this branch first. It lands before Wave B starts.
- **Whichever of Part 1 and brain-delegation reaches `main` first, `tell_confirm` and `tell_dismiss` must be rows of
  `MESSAGE_RULES` the moment both are there**, or AI Home's Start, Send and Cancel on an inbox card are dropped:
  - **Part 1 first:** brain-delegation adds its two rows to `MESSAGE_RULES` (as `APP_ONLY`), and to `SENDS` in
    `tests/test_watcher_rules.py` (Task 10, Step 1), when it merges (its spec's "`app/server.py` (after 1B)"). Its
    `from_watcher` reads `self._role(ws) == "watcher"`. Task 10 then finds the rows in place;
  - **brain-delegation first:** before Part 1 merges, `git merge main` into this branch, and do Task 10 right then
    (it needs only `app/server.py` and `tests/test_watcher_rules.py`). Then merge Part 1. Part 2 starts with Task 11.
  - Note in the ledger which way it went.

**Line numbers in the specs are at HEAD `946d5f0`.** The relay and the parallel tracks move them. Find every place by
the text this plan quotes, never by line. When the merged code names a piece differently from a spec, the code's name
wins and the behaviour is what matters (the brain-delegation spec's "Coordination across the seven specs").

**The relay's names this plan relies on** (from `docs/superpowers/specs/2026-10-03-cdp-relay-design.md`; read the
merged code before each task that touches it):
- `app/server.py`:
  - `BRAVE_MESSAGES` holds `"browser_disconnect"` beside `brave_connect`, `hand_tab` and `take_back`. The relay keeps
    it from the watcher with today's origin test in `_handle` (`elif kind in BRAVE_MESSAGES:` then
    `if self._origin_of.get(ws) not in self._watcher_origins:`). Task 1 gives it an app-only row; Task 2 removes the
    origin test;
  - the server sends `browser_clients {"clients": [...]}` to pages and puts `browser_clients` in the snapshot. It is
    never on `WATCHER_RECEIVES` (Task 4). Built before this plan, the relay keeps it from watcher sockets with a check
    of its own on today's structures (in `_send_all`, `_snapshot` or the `hello` branch). Task 4 removes that check,
    so `_write` is the one place that decides what a watcher socket gets;
  - `server.token_for(agent_id)` replaces `server.agent_token` (each agent has its own token);
  - `connect_brave(why, identity="")`;
- `tests/fake_brave.py`:
  - `FakePort` lives here now (moved from `tests/test_bravelink.py`, which imports it), with `sessions` still counting
    handshakes and `attached` recording `Target.attachToTarget` targets;
  - `FakeBrave.connect(why="connect", identity="")` records its calls in `connects` (a count today; the relay may
    keep a list of `(why, identity)`, so this plan's tests read it only as `not brave.connects`);
    `FakeBrave.relay` is a `FakeRelay` whose `async disconnect(identity)` AI Home's Disconnect calls;
- `app/bravelink.py`: `BraveLink(folder, allow_wait=ALLOW_WAIT, every=SWITCH_EVERY, tokens=None)` holds
  `self.relay`. Its `TabWatch` runs over `self.relay.local()`, is kept in `self._watch`, is made anew on each connect
  and is dropped when the connection is lost;
- `app/tabs.py`: `TabWatch(ws_url, extension_id, open_timeout=10, cdp=None)`;
- `app/cdprelay.py`: `APP_COMMANDS = {"Target.getBrowserContexts"}`. The app's own client sees every target, service
  workers included, with their `browserContextId` (relay Decision 9). The relay's drift test
  `test_every_method_the_engine_sends_passes_the_policy` (`tests/test_cdprelay.py`) reads `app/tabs.py`;
- `app/run.py`: `brave = BraveLink(own, tokens=server.tokens)`;
- the relay's test `test_browser_disconnect_only_from_our_pages` (`tests/test_app_server.py`) keeps passing through
  this plan's table.

**brain-delegation's names Task 10 and Part 2 rely on** (Wave A, beside this plan; read the merged code before Task
10): the page messages `tell_confirm` and `tell_dismiss` (app-only), `tell(..., from_watcher=...)` and the flag
`_handle` passes to `_brain_command`, the agent rows' `number` (never sent to the watcher in this wave:
`WATCHER_AGENT_FIELDS` stays five fields until the side chat), and its changes to `tablist.js` (`chipText`,
"Give to <n> · <name>", `mountYourTabs`) and `home.js`.

## Global Constraints

Copied from the spec and the user's safety rules. Every task's requirements include these.

**The browser's own signs stay:** "Brave's "Allow remote debugging?" question and its automation bar are never
clicked, answered, hidden or suppressed. This spec opens no connection. The new reads (`Target.getBrowserContexts`,
service-worker targets) use BraveLink's one existing connection." Success also means "no new "Allow remote
debugging?" question, no new connection to Brave, and no new extension permission."

**No spoofing, no bot-check bypass, no typed passwords:** "Nothing here touches a page."

**Page and message text is data:**
- "Tab titles stay text. The new count line is set with `textContent`, as the rows are."
- "A message from the watcher is checked against the table before anything reads its fields."
- "The watcher's Brain page renders the trimmed agent rows as it does today, as text."

**Nothing leaves the machine without a knowing choice:** "Everything stays on 127.0.0.1." "Context ids never leave
BraveLink." "Titles from other profiles and private windows no longer reach even AI Browser's own pages." "Rows sent
to pages keep `target`, `url`, `title` and `owner`, as today. The count and the profile's source go out as one small
`tab_scope` object."

**Downloads need the user's OK:** unchanged.

**Hand-over and take-back are clicks only:** "the watcher may not send `hand_tab`, `take_back` or `new_task` with
`adopt`; Hand over works only on a listed tab; the Brain and voice can't do either (unchanged)."

**The Brain only proposes:** "the watcher may not talk to the Brain (`brain_ask`, `brain_confirm`, `brain_dismiss`
are app-only), and `tell` keeps track 1A's card rule."

**The watcher gains nothing:** "no new permission and no `debugger`. Its one new message, `check_show`, replaces
today's `watch`: it can bring forward only the tab where an agent's bot check waits, never a tab it names." No
`incognito` key in its manifest.

**The tables:**
- "A type missing from the table is dropped for everyone." "A message whose `type` is missing or isn't a string is
  refused too."
- "A refused message is dropped, with no answer."
- After this plan's Part 1 (with the relay's `browser_disconnect`): 55 types, 22 for the watcher, 48 for the app's
  pages. After Task 10 (brain-delegation's two rows): 57 types, 22 and 50.
- `WATCHER_RECEIVES` holds 18 types. `WATCHER_AGENT_FIELDS = ("id", "name", "color", "state", "permission")`.

**Texts, word for word:**
- "Always allow is in AI Home's Tools."
- "<n> more tabs in other profiles or private windows: not shown here." ("1 more tab" for one)
- "Showing the Brave profile you used last. With the watcher loaded, this list stays on the watcher's profile."
- "Your tabs aren't listed: AI Browser can't tell which Brave profile is yours yet."
- "No web pages open in this profile."

**Tests:** "Tests never reach the user's real Brave or Chrome (the autouse fixture in tests/conftest.py). Throwaway
Chromes are started with their own temporary profiles. Run the touched files, not the whole suite." On Windows the
tests on the `watcher`, `home` and `app_browser` fixtures skip with the other pipe-fixture tests (Decision 13).

**Coordination rules:** text files name `encoding="utf-8"`; no new text says "this Mac" or "⌘"; no browser folder or
install path is written outside `chrome.py`.

**House rules:**
- Run tests one file or test at a time: `uv run pytest <path>::<test> -q -p no:randomly`.
- The whole suite runs only in the last task.
- Never connect to the user's own Brave or Chrome, and never touch a running `ai-browser app`.

## Review Focus

These are the five failures most likely to hit a user that the spec implies but none of its tests cover. Each one
has a test in the task that owns the code.
1. **Brave isn't connected (off, waiting for Allow, refused, lost), or has just connected again.** AI Home's tab list
   must not say "Your tabs aren't listed: AI Browser can't tell which Brave profile is yours yet." or show a count
   while the browser card says Brave isn't connected. While not connected, `BraveLink.scope()` answers
   `{"profile": "none", "elsewhere": 0}`, and that stale scope must not show either in the moment after Brave connects
   again, before the new connection's first list. Scope lines show only while connected and only from a list sent
   since the browser's state last changed; until then the empty text stays "No web pages open in your browser."
   Test: Task 11.
2. **A malformed `type` (a list, a number, `null`, an object, missing, 10,000 characters).** It is dropped with no
   answer, and the same socket keeps working. Today a list `type` raises `TypeError` in `_handle` and kills that
   page's socket. Test: Task 2.
3. **The watcher's worker waking and sleeping over and over** (an MV3 worker sleeps after about 30 s idle). The tab
   list and its scope aren't resent when nothing changed, so AI Home doesn't redraw for nothing. Test: Task 8.
4. **Take back, or an agent closing, on a tab in another profile.** The row leaves the list and the count line counts
   it; no title or address of it stays on screen. Test: Task 8.
5. **Show me when no tab source is attached** (the app started without a browser link). Nothing happens, nothing
   breaks, and the same watcher socket keeps working. Test: Task 3.

## File map

**New:**
- `tests/test_watcher_rules.py`: the two table tests, the watcher's socket tests, and the README test.

**Changed:**
- **App (Python):**
  - `src/ai_browser/app/server.py`: `Rule`, `MESSAGE_RULES`, `may_send`, `WATCHER_RECEIVES`, `WATCHER_AGENT_FIELDS`,
    `for_watcher`, `_role`, `_handle`, `_write`, `check_show` and `_show_check`, `_workflow_command`, `tab_scope`;
  - `src/ai_browser/app/tabs.py`: contexts, `pages()`, service workers, `worker_contexts`, `default_context`;
  - `src/ai_browser/app/bravelink.py`: `watcher_id`, `agents_context()`, the one-profile `tabs()`, `scope()`,
    `_changed()` only on change, `page_text` of listed tabs only;
  - `src/ai_browser/app/run.py`: one line (`watcher_id=`);
- **Pages:**
  - `src/ai_browser/app/extension/permission.js`: `{ always = true }`;
  - `src/ai_browser/app/watcher/brain.js`: one call, `{ always: false }`;
  - `src/ai_browser/app/watcher/notify.js`: no target in the note; Show me sends `check_show`;
  - `src/ai_browser/app/extension/tablist.js` and `home.js` (Part 2): the scope lines;
- **Docs:** `README.md` (Part 2): three places;
- **Tests:** `tests/fake_brave.py`, `tests/test_app_server.py`, `tests/test_bravelink.py`, `tests/test_tabwatch.py`,
  `tests/test_watcher.py`, `tests/test_ai_home_phase2.py`, `tests/test_app_run.py`, `tests/test_home.py` (Part 2).

**Not touched:** `app/cdprelay.py`, `chrome.py`, `browsers.py`, `platforms.py`, `app/watcher/worker.js` and
`app/watcher/manifest.json` (Decision 6: worker.js sends whatever `checkAction` returns).

The ledger is `.superpowers/sdd/2026-10-03-watcher-safety/progress.md` (git-ignored). Note in it each task's result,
and the merge of `main` before Part 2.

---

## Part 1: the spec's step 1 (beside brain-delegation and browser-detection)

### Task 1: One table of who may send what

**Files:**
- Modify: `src/ai_browser/app/server.py` (beside the constants `WATCHER_MESSAGES` … `BRAVE_MESSAGES`)
- Test: `tests/test_watcher_rules.py` (new)

**Interfaces:**
- Consumes: the relay's `"browser_disconnect"` page message (in `BRAVE_MESSAGES`).
- Produces:
  - `Rule(app: bool = True, watcher: bool | Callable[[dict], bool] = False)`, a frozen dataclass;
  - `MESSAGE_RULES: dict[str, Rule]`, 55 rows;
  - `may_send(role: str, message: dict) -> bool`: `role` is `"app"` or `"watcher"`; an unknown role, an unknown type,
    a missing type or a type that isn't a string gives `False`, never an exception;
  - in `tests/test_watcher_rules.py`: `SENDS` (the test's copy of the table, `{type: (app, watcher)}`),
    `ONLY_WITH_ITEM`, `ONCE_OR_DENY`. Tasks 10 and later waves add rows to it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_watcher_rules.py`:

```python
"""What a page may send and what a watcher socket may get: the server's two tables, each written down twice (in
app/server.py and here), and Brave's watcher held to them over real sockets."""

import pytest

ONLY_WITH_ITEM, ONCE_OR_DENY = "only with an item", "only once or deny"

# The table of watcher-safety's spec ("the table of what pages may send"), plus cdp-relay's row: (app, watcher).
# A row added to MESSAGE_RULES fails here until this copy says the same.
SENDS = {
    "hello": (True, True),
    **{kind: (False, True) for kind in ("items", "replied", "thread", "filled", "reader_status", "watcher_caps",
                                        "tab_grouped")},
    **{kind: (True, True) for kind in ("brain", "draft", "approve", "hand", "done", "tell", "watch_set",
                                       "watch_remove", "pause", "style")},
    "workflow_run": (True, ONLY_WITH_ITEM),
    **{kind: (True, False) for kind in ("workflows", "workflow_save", "workflow_delete")},
    "permission": (True, ONCE_OR_DENY),
    **{kind: (True, False) for kind in ("tools", "tool_set", "tool_allow", "tool_forget")},
    **{kind: (True, False) for kind in ("skills", "skill_draft", "skill_save")},
    **{kind: (True, False) for kind in ("hearing", "hearing_download", "hearing_cancel", "listen_start",
                                        "listen_chunk", "listen_end", "listen_cancel")},
    **{kind: (True, False) for kind in ("brain_ask", "brain_confirm", "brain_dismiss")},
    "check_continue": (True, True),
    "check_skip": (True, False),
    "check_show": (True, True),
    **{kind: (True, False) for kind in ("brave_connect", "hand_tab", "take_back")},
    "browser_disconnect": (True, False),  # cdp-relay: Disconnect in AI Home's list of connected clients
    "new_task": (True, False),  # with or without adopt
    **{kind: (True, False) for kind in ("send", "stop", "close", "model")},
    **{kind: (True, False) for kind in ("watch", "events", "thumbs")},
}


def test_the_message_table_has_exactly_the_written_down_types():
    from ai_browser.app.server import MESSAGE_RULES

    assert set(MESSAGE_RULES) == set(SENDS)
    assert len(SENDS) == 55
    assert sum(1 for app, _ in SENDS.values() if app) == 48
    assert sum(1 for _, watcher in SENDS.values() if watcher) == 22  # the two conditional rows count as allowed


@pytest.mark.parametrize("kind", sorted(SENDS))
def test_the_message_table_covers_every_type_for_both_roles(kind):
    from ai_browser.app.server import may_send

    app, watcher = SENDS[kind]
    sample = {"type": kind, "id": "a1"}
    assert may_send("app", sample) is app
    if watcher == ONLY_WITH_ITEM:  # the inbox's Run <workflow> on a message; a bare run stays in AI Home
        assert may_send("watcher", {**sample, "item": "i1"}) is True
        for bad in ({}, {"item": ""}, {"item": 3}, {"item": ["i1"]}, {"item": None}):
            assert may_send("watcher", {**sample, **bad}) is False, bad
    elif watcher == ONCE_OR_DENY:  # a lasting Always allow stays in AI Home's Tools
        for answer in ("once", "deny"):
            assert may_send("watcher", {**sample, "answer": answer}) is True
        for bad in ({"answer": "always"}, {}, {"answer": "ONCE"}, {"answer": ["once"]}, {"answer": None}):
            assert may_send("watcher", {**sample, **bad}) is False, bad
    else:
        assert may_send("watcher", sample) is watcher
    if kind == "new_task":  # with or without adopt: never from the watcher
        assert may_send("watcher", {**sample, "adopt": "U1"}) is False
        assert may_send("app", {**sample, "adopt": "U1"}) is True


@pytest.mark.parametrize("message", [{"type": "nonsense"}, {}, {"id": "a1"}, {"type": ["hello"]}, {"type": 7},
                                     {"type": None}, {"type": {"hello": 1}}, {"type": "HELLO"}, {"type": " hello"},
                                     {"type": "x" * 10_000}])
def test_an_unknown_or_malformed_type_is_refused_for_both_roles(message):
    from ai_browser.app.server import may_send

    assert may_send("app", message) is False
    assert may_send("watcher", message) is False


def test_only_the_two_roles_exist():
    from ai_browser.app.server import may_send

    assert may_send("stranger", {"type": "hello"}) is False and may_send("", {"type": "hello"}) is False
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_watcher_rules.py -q -p no:randomly`

Expected: FAIL. Every test errors with `ImportError: cannot import name 'MESSAGE_RULES' from 'ai_browser.app.server'`
(or `may_send`).

- [ ] **Step 3: Write the table**

In `src/ai_browser/app/server.py`, add `from dataclasses import dataclass` to the standard-library imports, on its own
line right after `from collections.abc import Callable` (the file lists `import …` lines first, then `from … import`
lines, each group in alphabetical order). Then, right after the line that starts `BRAVE_MESSAGES = {"brave_connect",
"hand_tab", "take_back"` (the relay added `"browser_disconnect"` to it), add:

```python


@dataclass(frozen=True)
class Rule:
    """Who may send one message type: AI Browser's own pages ("app"), and Brave's watcher ("watcher"), which may send
    it never, always, or when the check on the message passes."""
    app: bool = True
    watcher: bool | Callable[[dict], bool] = False


def _has_item(message: dict) -> bool:
    """The inbox's "Run <workflow>" on a message: never a bare run, which stays in AI Home."""
    return isinstance(message.get("item"), str) and message["item"] != ""


def _once_or_deny(message: dict) -> bool:
    """A tool request allowed once, or denied: a lasting Always allow stays in AI Home's Tools."""
    return message.get("answer") in ("once", "deny")


APP_ONLY, BOTH, WATCHER_ONLY = Rule(), Rule(watcher=True), Rule(app=False, watcher=True)

# Every message type a page may send, and who may send it (watcher-safety Decision 1). A type missing here is dropped
# for everyone, with no answer. tests/test_watcher_rules.py holds a copy: a row added here fails there until the copy
# says the same. A row may allow the watcher only if it can't give an agent a tab of the user's, save a lasting allow,
# connect to Brave, talk or listen, skip a check or close a tab.
MESSAGE_RULES: dict[str, Rule] = {
    "hello": BOTH,
    # the watcher's reports: they count only from the socket that said hello as the watcher (_handle)
    "items": WATCHER_ONLY, "replied": WATCHER_ONLY, "thread": WATCHER_ONLY, "filled": WATCHER_ONLY,
    "reader_status": WATCHER_ONLY, "watcher_caps": WATCHER_ONLY, "tab_grouped": WATCHER_ONLY,
    # the Brain's inbox, in AI Home and on the watcher's Brain page
    "brain": BOTH, "draft": BOTH, "approve": BOTH, "hand": BOTH, "done": BOTH, "tell": BOTH, "watch_set": BOTH,
    "watch_remove": BOTH, "pause": BOTH, "style": BOTH,
    "workflow_run": Rule(watcher=_has_item),
    "workflows": APP_ONLY, "workflow_save": APP_ONLY, "workflow_delete": APP_ONLY,
    "permission": Rule(watcher=_once_or_deny),
    "tools": APP_ONLY, "tool_set": APP_ONLY, "tool_allow": APP_ONLY, "tool_forget": APP_ONLY,
    "skills": APP_ONLY, "skill_draft": APP_ONLY, "skill_save": APP_ONLY,
    "hearing": APP_ONLY, "hearing_download": APP_ONLY, "hearing_cancel": APP_ONLY, "listen_start": APP_ONLY,
    "listen_chunk": APP_ONLY, "listen_end": APP_ONLY, "listen_cancel": APP_ONLY,
    "brain_ask": APP_ONLY, "brain_confirm": APP_ONLY, "brain_dismiss": APP_ONLY,
    "check_continue": BOTH, "check_skip": APP_ONLY, "check_show": BOTH,  # Skip closes a tab: never the watcher's
    "brave_connect": APP_ONLY, "hand_tab": APP_ONLY, "take_back": APP_ONLY,
    "browser_disconnect": APP_ONLY,  # cdp-relay: Disconnect in AI Home's list of connected clients
    "new_task": APP_ONLY,  # with or without adopt
    "send": APP_ONLY, "stop": APP_ONLY, "close": APP_ONLY, "model": APP_ONLY,
    "watch": APP_ONLY, "events": APP_ONLY, "thumbs": APP_ONLY,
}


def may_send(role: str, message: dict) -> bool:
    """Whether a page of this role ("app" or "watcher") may send this message. An unknown type, a message without
    one, or a type that isn't a string is never allowed, for anyone."""
    kind = message.get("type")
    rule = MESSAGE_RULES.get(kind) if isinstance(kind, str) else None
    if rule is None:
        return False
    if role == "app":
        return rule.app
    if role == "watcher":
        return bool(rule.watcher(message)) if callable(rule.watcher) else rule.watcher is True
    return False
```

`Callable` is already imported (`from collections.abc import Callable`). Nothing calls `may_send` yet: Task 2 does.

- [ ] **Step 4: Run it to see it pass**

Run: `uv run pytest tests/test_watcher_rules.py -q -p no:randomly`

Expected: PASS, 67 tests: the count test, 55 cases of the table test, 10 malformed messages, and the roles test.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/server.py tests/test_watcher_rules.py
git commit -m "feat: one table of which page may send which message (MESSAGE_RULES, may_send)"
```

### Task 2: `_handle` asks the table first; the watcher does nothing else

**Files:**
- Modify: `src/ai_browser/app/server.py` (`_handle`, a new `_role`, `_workflow_command`)
- Test: `tests/test_watcher_rules.py`

**Interfaces:**
- Consumes: Task 1's `may_send`; the relay's `browser_disconnect` handling inside `_brave_command` (unchanged).
- Produces:
  - `AppServer._role(self, ws: WebSocket) -> str`: `"watcher"` when the socket's origin is one of
    `self._watcher_origins`, else `"app"`;
  - `_handle`'s first step is `if not may_send(self._role(ws), message): return`. After this task the only uses of
    `_watcher_origins` are `__init__`, `allow_origin`, `_mismatch`, `_socket` and `_role`, plus the relay's check that
    keeps `browser_clients` from watcher sockets, if it reads `_watcher_origins` (Task 4 removes it);
  - `workflow_run` with an `item` runs only through the Brain; with no Brain it does nothing.
- Test helpers this task's tests import from `tests/test_app_server.py`: `ORIGIN`, `WATCHER`, `CHECK_REPORT`,
  `started`, `with_brain`, `socket_url`, `recv`, `until`, `quiet`, `wait_for`.

- [ ] **Step 1: Write the failing tests**

At the top of `tests/test_watcher_rules.py`, replace the import block (`import pytest`) with:

```python
import asyncio
import inspect
import json

import pytest
from websockets.asyncio.client import connect

from fake_brave import FakeBrave, add_agent
from test_app_server import (CHECK_REPORT, ORIGIN, WATCHER, quiet, recv, socket_url, started, until, wait_for,
                             with_brain)
from test_bridge import EVENTS
```

Then add at the end of the file:

```python
SKILL = "---\nname: cookie-reader\ndescription: Reads every cookie of the user's\n---\n# Cookies\n\n1. Read them.\n"


def files(folder):
    """Every file under `folder` with its text: to show nothing was written."""
    if not folder.exists():
        return {}
    return {str(path.relative_to(folder)): path.read_text(encoding="utf-8")
            for path in sorted(folder.rglob("*")) if path.is_file()}


def log_text(log):
    return log.read_text(encoding="utf-8") if log.exists() else ""


async def test_the_watcher_cannot_start_an_agent_in_a_users_tab(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    server.allow_origin(WATCHER, watcher=True)
    brave = FakeBrave([{"target": "U1", "url": "https://shop.example/", "title": "Shop"}])
    server.attach_brave(brave)
    try:
        async with connect(socket_url(server, url), origin=WATCHER) as watcher:
            await watcher.send(json.dumps({"type": "hello", "view": "brain"}))
            await until(watcher, lambda m: m["type"] == "snapshot")
            await watcher.send(json.dumps({"type": "new_task", "text": "look", "adopt": "U1", "request": "r1"}))
            await watcher.send(json.dumps({"type": "new_task", "text": "look", "request": "r2"}))
            seen = await quiet(watcher, 1.0)
        assert not any(m["type"] in ("created", "error") for m in seen)  # dropped, with no answer
        assert server.agents.agents == {} and "U1" not in brave.owners
        async with connect(socket_url(server, url), origin=ORIGIN) as page:  # AI Home may (the samples are real)
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            await recv(page)
            await page.send(json.dumps({"type": "new_task", "text": "look", "adopt": "U1", "request": "r3"}))
            await until(page, lambda m: m["type"] == "created")
        assert server.agents.agents["a1"].adopted == ["U1"] and brave.owners["U1"]["kind"] == "handed"
    finally:
        await server.stop()


async def test_the_watcher_cannot_save_always_allow(fake_claude, tmp_path):
    from ai_browser.app.server import AppServer
    from test_tools import answers, asking, manager

    agents, tools, log = manager(fake_claude, tmp_path, asking())
    tools.set_enabled("clickup", True)
    server = AppServer(tmp_path / "home", agents, tools=tools)
    url = await server.start()
    server.allow_origin(ORIGIN)
    server.allow_origin(WATCHER, watcher=True)
    try:
        agent = await agents.create("make a ClickUp task")
        await wait_for(lambda: agent.permission is not None)
        request = agent.permission["request"]
        async with connect(socket_url(server, url), origin=WATCHER) as watcher:
            await watcher.send(json.dumps({"type": "hello", "view": "brain"}))
            await until(watcher, lambda m: m["type"] == "snapshot")
            await watcher.send(json.dumps({"type": "tool_allow", "tool": "mcp__clickup__create_task"}))
            for answer in ({"answer": "always"}, {}):
                await watcher.send(json.dumps({"type": "permission", "agent": agent.id, "request": request,
                                               **answer}))
            await asyncio.sleep(0.5)
            assert tools.always() == set()
            assert agent.permission is not None and agent.permission["request"] == request  # still waiting
            await watcher.send(json.dumps({"type": "permission", "agent": agent.id, "request": request,
                                           "answer": "once"}))
            await wait_for(lambda: agent.permission is None)  # Allow once from Brave still answers
        await wait_for(lambda: bool(answers(log)))
        assert answers(log)[0]["behavior"] == "allow" and tools.always() == set()
        assert "mcp__clickup__create_task" not in tools.path.read_text(encoding="utf-8")
    finally:
        await server.stop()


async def test_the_watcher_origin_may_send_nothing_else(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer
    from ai_browser.brain.service import BrainService
    from ai_browser.brain.skillwriter import SkillWriter
    from ai_browser.brain.store import BrainStore
    from ai_browser.brain.tools import ToolsConfig
    from ai_browser.brain.workflows import WorkflowRunner, WorkflowStore
    from ai_browser.hearing.service import HearingService
    from fake_engine import FakeEngine, tiny_store
    from test_hearing import chunks, tone
    from test_tools import user_config

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    home = tmp_path / "home"
    agents = AgentManager(home, claude=runner)
    tools = ToolsConfig(home, claude_home=user_config(tmp_path))
    tools.allow_always("mcp__clickup__get_task")  # so a tool_forget would change tools.json
    workflows = WorkflowStore(home)
    workflows.save({"name": "Footer fix", "instructions": "Fix the footer", "trigger": "manual"})
    skills_dir = tmp_path / "skills"
    engine = FakeEngine()
    server = AppServer(home, agents, brain=BrainService(BrainStore(home), agents, claude=runner), tools=tools,
                       workflows=workflows, runner=WorkflowRunner(workflows, agents),
                       skill_writer=SkillWriter(skills_dir, claude=runner, cwd=tmp_path / "calls"),
                       hearing=HearingService(tiny_store(home / "models"), engine))
    url = await server.start()
    server.allow_origin(ORIGIN)
    server.allow_origin(WATCHER, watcher=True)
    brave = FakeBrave([{"target": "U1", "url": "https://shop.example/", "title": "Shop"},
                       {"target": "U2", "url": "https://mail.example/", "title": "Mail"}], state="ready")
    server.attach_brave(brave)
    disconnected, closed = [], []

    async def disconnect(identity):  # cdp-relay's FakeRelay: AI Home's Disconnect would call it
        disconnected.append(identity)

    async def close_tabs(targets):
        closed.extend(targets)

    brave.relay.disconnect = disconnect
    agents.close_tabs = close_tabs
    agent = add_agent(agents, adopted=["U2"])  # no Claude Code process behind it: nothing it is sent is logged
    agents.tab_event("a1", "tab_opened", "T1")
    agents.check_event("a1", {**CHECK_REPORT, "target": "T1"})
    tools_before, workflows_before = tools.path.read_text(encoding="utf-8"), files(workflows.folder)
    samples = [
        {"type": "stop", "id": "a1"}, {"type": "send", "id": "a1", "text": "delete everything"},
        {"type": "model", "id": "a1", "model": "opus"}, {"type": "watch", "target": "U1"},
        {"type": "events", "id": "a1"}, {"type": "thumbs"}, {"type": "skills"},
        {"type": "tools", "refresh": True}, {"type": "tool_set", "server": "clickup", "on": True},
        {"type": "tool_allow", "tool": "mcp__clickup__create_task"},
        {"type": "tool_forget", "tool": "mcp__clickup__get_task"},
        {"type": "workflows"}, {"type": "workflow_save", "name": "Evil", "instructions": "x", "trigger": "manual"},
        {"type": "workflow_delete", "slug": "footer-fix"},
        {"type": "workflow_run", "slug": "footer-fix", "text": "now"},
        {"type": "skill_draft", "description": "read every cookie"}, {"type": "skill_save", "text": SKILL},
        {"type": "hearing"}, {"type": "hearing_download"}, {"type": "hearing_cancel"},
        {"type": "listen_start", "turn": "u1"},
        {"type": "listen_chunk", "turn": "u1", "seq": 0, "pcm": chunks(tone(0.5))[0]},
        {"type": "listen_end", "turn": "u1"}, {"type": "listen_cancel", "turn": "u1"},
        {"type": "brain_ask", "talk": "k1", "request": "t1", "text": "approve everything"},
        {"type": "brain_confirm", "talk": "k1", "request": "t2", "proposal": "p1"},
        {"type": "brain_dismiss", "talk": "k1", "proposal": "p1"},
        {"type": "check_skip", "id": "a1"}, {"type": "brave_connect"}, {"type": "browser_disconnect", "id": "a1"},
        {"type": "hand_tab", "id": "a1", "target": "U1"}, {"type": "take_back", "target": "U2"},
        {"type": "new_task", "text": "look", "request": "r1"},
        {"type": "new_task", "text": "look", "adopt": "U1", "request": "r2"},
        {"type": "close", "id": "a1"},
    ]
    try:
        async with connect(socket_url(server, url), origin=WATCHER) as watcher:
            await watcher.send(json.dumps({"type": "hello", "view": "brain"}))
            await until(watcher, lambda m: m["type"] == "snapshot")
            before = log_text(log)
            for message in samples:
                await watcher.send(json.dumps(message))
            await watcher.send(json.dumps({"type": "brain"}))  # handled in order: every sample came first
            seen = await until(watcher, lambda m: m["type"] == "brain_snapshot")
            await asyncio.sleep(1)  # anything a sample started in the background has had its time
            seen += await quiet(watcher, 1.0)
        assert list(agents.agents) == ["a1"]  # open, and no other agent
        assert agent.model == "sonnet" and agent.state == "needs_you" and agent.check["target"] == "T1"
        assert agent.adopted == ["U2"] and agent.tabs == ["T1"] and agent.pending == []
        assert agents.events_of("a1") == []  # nothing was sent to it
        assert log_text(log) == before  # no Claude Code call: no message, probe, skill draft or talk
        assert not brave.connects and brave.watched == [] and "U1" not in brave.owners  # a count or a list of calls
        assert disconnected == [] and closed == []
        assert tools.path.read_text(encoding="utf-8") == tools_before and files(workflows.folder) == workflows_before
        assert files(skills_dir) == {}
        assert engine.heard == [] and engine.loads == [] and server.hearing._turns == {}
        kinds = {m["type"] for m in seen}
        assert not kinds & {"created", "error", "agent_events", "thumbs", "skills", "tools_snapshot",
                            "workflows_snapshot", "workflow_saved", "skill_drafted", "skill_saved", "hearing_status",
                            "heard", "brain_answer"}
        async with connect(socket_url(server, url), origin=ORIGIN) as page:  # the same close from AI Home works
            await page.send(json.dumps({"type": "close", "id": "a1"}))
            await wait_for(lambda: "a1" not in agents.agents)
    finally:
        await server.stop()
    home2 = tmp_path / "home2"  # workflows and no Brain: a Run on an inbox item can't become a bare run
    agents2 = AgentManager(home2, claude=runner)
    store2 = WorkflowStore(home2)
    store2.save({"name": "Footer fix", "instructions": "Fix the footer", "trigger": "manual"})
    bare = AppServer(home2, agents2, workflows=store2, runner=WorkflowRunner(store2, agents2))
    url2 = await bare.start()
    bare.allow_origin(ORIGIN)
    try:
        async with connect(socket_url(bare, url2), origin=ORIGIN) as page:
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            await recv(page)
            await page.send(json.dumps({"type": "workflow_run", "slug": "footer-fix", "item": "gmail:t1",
                                        "request": "r9"}))
            await page.send(json.dumps({"type": "workflows"}))
            seen = await until(page, lambda m: m["type"] == "workflows_snapshot")
        assert agents2.agents == {} and not any(m["type"] == "created" for m in seen)
    finally:
        await bare.stop()


async def test_a_malformed_type_is_dropped_and_the_socket_goes_on(fake_claude, tmp_path):  # Review Focus 2
    server, url, _ = await with_brain(fake_claude, tmp_path, [{"result": "[]"}])
    add_agent(server.agents)
    bad = [{"type": ["events"]}, {"type": 7}, {"type": None}, {"type": {"events": 1}}, {"id": "a1"},
           {"type": "x" * 10_000}]
    try:
        for origin, view, ask, answer in ((ORIGIN, "home", {"type": "events", "id": "a1"}, "agent_events"),
                                          (WATCHER, "brain", {"type": "brain"}, "brain_snapshot")):
            async with connect(socket_url(server, url), origin=origin) as ws:
                await ws.send(json.dumps({"type": "hello", "view": view}))
                await until(ws, lambda m: m["type"] == "snapshot")
                for message in bad:
                    await ws.send(json.dumps(message))
                await ws.send(json.dumps(ask))
                seen = await until(ws, lambda m, answer=answer: m["type"] == answer)
                assert not any(m["type"] == "error" for m in seen), origin
    finally:
        await server.stop()


def test_rights_go_by_role_through_the_table():
    from ai_browser.app.server import AppServer

    for method in (AppServer._handle, AppServer._brain_command):  # no origin test of its own any more
        assert "_watcher_origins" not in inspect.getsource(method), method.__name__
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_watcher_rules.py -q -p no:randomly`

Expected: Task 1's tests PASS; the five new ones FAIL:
- `test_the_watcher_cannot_start_an_agent_in_a_users_tab`: agent a1 starts and U1 becomes "handed";
- `test_the_watcher_cannot_save_always_allow`: `tools.always()` holds `mcp__clickup__create_task`;
- `test_the_watcher_origin_may_send_nothing_else`: a1 is closed (and the other samples took effect);
- `test_a_malformed_type_is_dropped_and_the_socket_goes_on`: `{"type": ["events"]}` raises `TypeError` in
  `_handle`, the socket closes, and `until` raises `ConnectionClosed`;
- `test_rights_go_by_role_through_the_table`: `_handle` still reads `_watcher_origins`.

- [ ] **Step 3: Ask the table first, by role**

In `src/ai_browser/app/server.py`:

1. Add, right before `async def _handle(`:

```python
    def _role(self, ws: WebSocket) -> str:
        """ "watcher" for a socket from Brave's watcher's origin, else "app" (AI Browser's own pages). The origin was
        checked when the socket opened, so every open socket has a role. (The app window, Wave B, maps its cookie to
        "app" here; the table and the filter stay.)"""
        return "watcher" if self._origin_of.get(ws) in self._watcher_origins else "app"
```

2. In `_handle`, replace its first line, `kind, agent_id, agents = message.get("type"), str(message.get("id", "")),
   self.agents`, and the condition of the first branch (`if kind == "hello" and message.get("view") == "watcher" and
   self.brain is not None \` / `and self._origin_of.get(ws) in self._watcher_origins:`) with:

```python
        if not may_send(self._role(ws), message):  # MESSAGE_RULES, before anything reads the message's fields
            return  # dropped, with no answer: a page can't map the table by trying types
        kind, agent_id, agents = message["type"], str(message.get("id", "")), self.agents
        if kind == "hello" and message.get("view") == "watcher" and self.brain is not None \
                and self._role(ws) == "watcher":
```

   The branch's body (`self._watcher = (ws, queue)` …) and the reports branch (`elif kind in WATCHER_MESSAGES:` with
   its `self._watcher[0] is ws` check) stay as they are.

3. Replace the `CHECK_MESSAGES` branch:

```python
        elif kind in CHECK_MESSAGES:  # only a click in one of our pages (or the watcher's Continue) answers a check
            if kind == "check_continue":
                await agents.continue_check(agent_id)
            elif self._origin_of.get(ws) not in self._watcher_origins:
                await agents.skip_check(agent_id)
```

   with:

```python
        elif kind in CHECK_MESSAGES:  # a bot check's buttons; MESSAGE_RULES lets the watcher Continue, never Skip
            if kind == "check_continue":
                await agents.continue_check(agent_id)
            elif kind == "check_skip":
                await agents.skip_check(agent_id)
```

4. In the `BRAVE_MESSAGES`, `HEARING_MESSAGES` and `TALK_MESSAGES` branches, delete the line
   `if self._origin_of.get(ws) not in self._watcher_origins:` (with its comment) and dedent the call under it, so they
   read:

```python
        elif kind in BRAVE_MESSAGES:  # AI Browser's own pages only (MESSAGE_RULES)
            await self._brave_command(queue, kind, message)
        elif kind in HEARING_MESSAGES:  # only AI Browser's own pages talk or listen (MESSAGE_RULES)
            self._hearing_command(ws, queue, kind, message)
        elif kind in TALK_MESSAGES:
            self._talk_command(queue, kind, message)
```

   Keep each call's arguments as the merged code has them (the relay may pass more to `_brave_command`); only the
   `if` lines go.

5. In `_workflow_command`, replace the `workflow_run` branch's `if`/`else`:

```python
            elif kind == "workflow_run" and isinstance(message.get("slug"), str):
                if isinstance(message.get("item"), str) and self.brain is not None:
                    agent_id = await self.brain.run_workflow(message["item"], message["slug"])
                else:
                    agent_id = await self.runner.run(message["slug"], text=_text(message.get("text")) or None)
```

   with:

```python
            elif kind == "workflow_run" and isinstance(message.get("slug"), str):
                if isinstance(message.get("item"), str):  # the inbox's Run on a message: only through the Brain,
                    if self.brain is None:                # never a bare run in its place
                        return
                    agent_id = await self.brain.run_workflow(message["item"], message["slug"])
                else:
                    agent_id = await self.runner.run(message["slug"], text=_text(message.get("text")) or None)
```

6. Run `grep -n "_watcher_origins" src/ai_browser/app/server.py`. The only lines left are in `__init__`,
   `allow_origin`, `_mismatch`, `_socket` and `_role`, and possibly the relay's `browser_clients` check (outside
   `_handle` and `_brain_command`), which stays until Task 4. Any other use that refuses a message type is an origin
   test this task replaces: delete it, and check the table's row for that type says the same.

- [ ] **Step 4: Run them, and the files around them**

Run: `uv run pytest tests/test_watcher_rules.py tests/test_app_server.py tests/test_tools.py tests/test_workflows.py -q -p no:randomly`

Expected: PASS. That includes these, now through the table:
- `test_the_watcher_may_not_hand_tabs_or_connect` (the spec's test 11, unchanged);
- `test_check_buttons_come_from_our_pages_and_the_watcher_only_continues`;
- `test_the_watcher_can_neither_talk_nor_listen`;
- `test_only_the_watcher_may_report_items`;
- the relay's `test_browser_disconnect_only_from_our_pages`.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/server.py tests/test_watcher_rules.py
git commit -m "feat: every page message is checked against MESSAGE_RULES first; the watcher may send only its list"
```

### Task 3: Show me asks by agent id (`check_show`)

**Files:**
- Modify: `src/ai_browser/app/server.py` (`CHECK_MESSAGES`, the `CHECK_MESSAGES` branch of `_handle`, a new
  `_show_check`)
- Modify: `src/ai_browser/app/watcher/notify.js` (`checkNotification`, `checkAction`)
- Test: `tests/test_watcher_rules.py`, `tests/test_watcher.py`
  (`test_a_bot_check_gets_one_notification_with_show_me_and_continue`)

**Interfaces:**
- Consumes: Task 1's row `"check_show": BOTH`; Task 2's `CHECK_MESSAGES` branch.
- Produces:
  - page message `check_show {"id": "<agent id>"}`;
  - `async AppServer._show_check(self, agent_id: str) -> None`: when that agent holds a bot check without a `live`
    link, and a tab source is attached, `await self.tabs.watch(agent.check["target"])`; otherwise nothing;
  - `checkNotification(request)` returns `note: { check: { agent, live } }` (no `target`);
  - `checkAction(note, 0)` returns `{ send: { type: "check_show", id: check.agent } }` when there is no live link.
- AI Browser's own check cards keep sending `watch` with the target (`app/extension/check.js`): unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_watcher_rules.py`:

```python
async def test_show_me_from_the_watcher_brings_the_checks_tab_forward(fake_claude, tmp_path):
    server, url, _ = await with_brain(fake_claude, tmp_path, [{"result": "[]"}])
    brave = FakeBrave([{"target": "U1", "url": "https://shop.example/", "title": "Shop"}])
    server.attach_brave(brave)
    agents = server.agents
    for agent_id, live in (("a1", None), ("a3", "http://127.0.0.1:8770/live?token=abc")):
        add_agent(agents, agent_id)
        agents.tab_event(agent_id, "tab_opened", f"T{agent_id[1:]}")
        agents.check_event(agent_id, {**CHECK_REPORT, "target": f"T{agent_id[1:]}", "live": live})
    add_agent(agents, "a2", "Other", "green")  # no bot check
    try:
        async with connect(socket_url(server, url), origin=WATCHER) as watcher:
            await watcher.send(json.dumps({"type": "hello", "view": "watcher"}))
            await until(watcher, lambda m: m["type"] == "watch_list")
            for message in ({"type": "check_show", "id": "a2"},  # no check: nothing
                            {"type": "check_show", "id": "a3"},  # shown in the live view: nothing here
                            {"type": "check_show", "id": "nobody"},
                            {"type": "watch", "target": "U1"},  # a tab the watcher names: never
                            {"type": "check_show", "id": "a1"}):
                await watcher.send(json.dumps(message))
            await watcher.send(json.dumps({"type": "brain"}))  # handled in order: every message above came first
            await until(watcher, lambda m: m["type"] == "brain_snapshot")
        assert brave.watched == ["T1"] and agents.agents["a1"].check is not None  # Show me answers nothing
        async with connect(socket_url(server, url), origin=ORIGIN) as page:  # AI Home's own Watch still names a tab
            await page.send(json.dumps({"type": "watch", "target": "U1"}))
            await wait_for(lambda: brave.watched == ["T1", "U1"])
    finally:
        await server.stop()


async def test_show_me_with_no_tab_source_does_nothing(fake_claude, tmp_path):  # Review Focus 5
    server, url, _ = await with_brain(fake_claude, tmp_path, [{"result": "[]"}])  # no browser link attached
    agents = server.agents
    add_agent(agents)
    agents.tab_event("a1", "tab_opened", "T1")
    agents.check_event("a1", {**CHECK_REPORT, "target": "T1"})
    try:
        async with connect(socket_url(server, url), origin=WATCHER) as watcher:
            await watcher.send(json.dumps({"type": "hello", "view": "watcher"}))
            await until(watcher, lambda m: m["type"] == "watch_list")
            await watcher.send(json.dumps({"type": "check_show", "id": "a1"}))
            await watcher.send(json.dumps({"type": "check_continue", "id": "a1"}))  # the socket goes on
            await wait_for(lambda: agents.agents["a1"].check is None)
    finally:
        await server.stop()
```

In `tests/test_watcher.py`, replace the whole of `test_a_bot_check_gets_one_notification_with_show_me_and_continue`
with:

```python
@CHROME
async def test_a_bot_check_gets_one_notification_with_show_me_and_continue(watcher):
    watcher.brain.send_watcher({"type": "check_request", "agent": "a1", "name": "Flights to Manila",
                                "site": "www.google.com", "what": "a check", "target": "T1", "live": None})
    noted = ("chrome.storage.session.get('notes').then(({notes = {}}) => Object.values(notes).some("
             "note => note.check && note.check.agent === 'a1' && !('target' in note.check)))")
    assert await until(watcher.worker_js, noted)  # no tab id is kept: Show me asks by the agent's id
    assert await until(watcher.worker_js, "chrome.notifications.getAll().then(all => Object.keys(all).length === 1)")
    _, js = await open_page(watcher.cdp, f"chrome-extension://{watcher.app.extension_id}/brain.html")

    async def notify(code):
        return await js(f"import('./notify.js').then((m) => {code})")

    made = await notify("m.checkNotification({agent: 'a1', name: 'Flights to Manila', site: 'www.google.com', "
                        "target: 'T1', live: null})")
    assert made["options"]["title"] == "Flights to Manila: a bot check on www.google.com"
    assert made["options"]["message"] == "Solve it in the tab, then press Continue."
    assert [button["title"] for button in made["options"]["buttons"]] == ["Show me", "Continue"]
    assert made["note"] == {"check": {"agent": "a1", "live": ""}}  # its input had a target: the note has none
    note = json.dumps(made["note"])
    assert await notify(f"m.checkAction({note}, 1)") == {"send": {"type": "check_continue", "id": "a1"}}
    assert await notify(f"m.checkAction({note}, 0)") == {"send": {"type": "check_show", "id": "a1"}}
    live = await notify("m.checkNotification({agent: 'a1', target: 'Q1', "
                        "live: 'http://127.0.0.1:8770/live?token=abc'})")
    assert await notify(f"m.checkAction({json.dumps(live['note'])}, 0)") == \
        {"open": "http://127.0.0.1:8770/live?token=abc"}
    forged = await notify("m.checkNotification({agent: 'a1', target: 'Q1', "
                          "live: 'http://127.0.0.1:80@evil.example/live?token=x'})")  # Review Focus 2 (safe-browsing)
    assert forged["note"]["check"]["live"] == ""
    assert await notify(f"m.checkAction({json.dumps(forged['note'])}, 0)") == \
        {"send": {"type": "check_show", "id": "a1"}}
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_watcher_rules.py::test_show_me_from_the_watcher_brings_the_checks_tab_forward tests/test_watcher_rules.py::test_show_me_with_no_tab_source_does_nothing tests/test_watcher.py::test_a_bot_check_gets_one_notification_with_show_me_and_continue -q -p no:randomly`

Expected:
- `test_show_me_from_the_watcher_brings_the_checks_tab_forward` FAILS: `brave.watched == []` (`check_show` has a row
  but no branch in `_handle` yet);
- `test_show_me_with_no_tab_source_does_nothing` PASSES already: it is a guard for Review Focus 5 and must keep
  passing;
- the notification test FAILS: the stored note still has `target`, and Show me returns `watch`.

- [ ] **Step 3: Show me by agent**

In `src/ai_browser/app/server.py`:

1. Replace `CHECK_MESSAGES = {"check_continue", "check_skip"}  # a bot check's buttons; the watcher may Continue,
   never Skip` with:

```python
CHECK_MESSAGES = {"check_continue", "check_skip", "check_show"}  # a bot check's buttons (who may: MESSAGE_RULES)
```

2. In `_handle`'s `CHECK_MESSAGES` branch (Task 2's form), add a third arm after the `check_skip` one:

```python
            elif kind == "check_show":
                await self._show_check(agent_id)
```

3. Add, right after `_handle`:

```python
    async def _show_check(self, agent_id: str) -> None:
        """Show me, from Brave's notification: bring forward the tab where this agent's bot check waits. The app holds
        that tab, so no page names one. A check shown in the live view (QA's sandbox) has no tab here, and without a
        tab source nothing happens. It uses the link's one connection and never opens one."""
        agent = self.agents.agents.get(agent_id)
        check = agent.check if agent is not None else None
        if check is None or check.get("live") or not check.get("target") or self.tabs is None:
            return
        await self.tabs.watch(check["target"])
```

In `src/ai_browser/app/watcher/notify.js`, replace everything from the comment `// An agent stopped at a bot check:
the notification says who and where` to the end of the file with:

```js
// An agent stopped at a bot check: the notification says who and where (plain text), and its buttons can only bring
// that agent's checked tab forward (or open the live view that shows it) and tell the agent to carry on. Nothing here
// closes a tab, and the note keeps no tab id: the app knows which tab the agent's check is in.
export function checkNotification(request) {
  const live = LIVE.test(String(request.live || "")) ? String(request.live) : "";
  return {
    options: { title: `${request.name || "An agent"}: a bot check on ${request.site || "a site"}`.slice(0, 120),
               message: "Solve it in the tab, then press Continue.",
               buttons: [{ title: "Show me" }, { title: "Continue" }] },
    note: { check: { agent: String(request.agent || ""), live } },
  };
}

// What a click on the notification does: Continue (button 1) tells the agent; Show me (button 0, or the notification
// itself) opens the live view when there is one, else asks the app, by the agent's id, to bring its tab forward.
export function checkAction(note, index) {
  const check = note.check || {};
  if (index === 1) return { send: { type: "check_continue", id: check.agent } };
  if (check.live) return { open: check.live };
  return { send: { type: "check_show", id: check.agent } };
}
```

`worker.js` doesn't change: `doCheck` sends whatever `checkAction` returns. The watcher's build changes, so it reloads
itself when it next connects.

- [ ] **Step 4: Run them, and the watcher's files**

Run: `uv run pytest tests/test_watcher_rules.py tests/test_watcher.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/server.py src/ai_browser/app/watcher/notify.js tests/test_watcher_rules.py tests/test_watcher.py
git commit -m "feat: the watcher's Show me asks by agent id (check_show); its notes keep no tab id"
```

### Task 4: What a watcher socket receives is a fixed list

**Files:**
- Modify: `src/ai_browser/app/server.py` (new `WATCHER_RECEIVES`, `WATCHER_AGENT_FIELDS`, `for_watcher`; `_write`;
  the relay's `browser_clients` check by origin goes)
- Test: `tests/test_watcher_rules.py`; `tests/test_app_server.py`
  (`test_check_reports_are_checked_then_reach_pages_and_the_watcher`)

**Interfaces:**
- Consumes: Task 2's `AppServer._role`; the relay's `browser_clients` message (dropped here), and the relay's own
  check that keeps it from watcher sockets (removed here).
- Produces:
  - `WATCHER_RECEIVES: frozenset[str]` (18 types) and `WATCHER_AGENT_FIELDS = ("id", "name", "color", "state",
    "permission")`;
  - `for_watcher(message: dict) -> dict | None`: the message, a trimmed copy (`snapshot`, `agent`,
    `check_request`), or `None`. It never changes its input;
  - `_write` filters every message to a watcher-origin socket through `for_watcher`. The side chat (Wave D) adds
    types and fields here, and updates `RECEIVES` in the test.

- [ ] **Step 1: Write the failing tests**

Add `import os` to the imports of `tests/test_watcher_rules.py`, then add:

```python
RECEIVES = {"ping", "error", "watcher_hello", "watch_list", "notify", "permission_request", "check_request",
            "group_tab", "ungroup_tabs", "open_thread", "fill_reply",  # the worker's
            "snapshot", "agent", "agent_closed", "brain_snapshot", "brain_item", "brain_item_gone",
            "brain_state"}  # the Brain page's
NEVER = {"tabs", "thumb", "thumbs", "sessions", "browser", "agent_event", "agent_events", "created", "brain_activity",
         "brain_answer", "hearing_status", "heard", "tools_snapshot", "workflows_snapshot", "workflow_saved", "skills",
         "skill_drafted", "skill_diff", "skill_saved",
         "browser_clients",  # cdp-relay's list of connected clients
         "a_type_added_later"}
AGENT_ROW = {"id": "a1", "name": "Fix the footer", "color": "blue", "model": "sonnet", "state": "needs_you",
             "status": "", "last_action": "", "tabs": ["T1"], "adopted": ["U2"], "working_tab": "T1",
             "loaded_skills": [], "seconds": 0, "cost": 0, "created": 1.0,
             "permission": {"request": "r1", "server": "clickup", "tool": "mcp__clickup__create_task", "input": {}},
             "check": {"target": "T1", "live": None}}


def test_what_the_watcher_receives_is_a_fixed_list():
    from ai_browser.app.server import WATCHER_AGENT_FIELDS, WATCHER_RECEIVES, for_watcher

    assert WATCHER_RECEIVES == RECEIVES and len(RECEIVES) == 18
    assert WATCHER_AGENT_FIELDS == ("id", "name", "color", "state", "permission")
    for kind in RECEIVES | NEVER:
        assert (for_watcher({"type": kind}) is not None) is (kind in RECEIVES), kind
    row = {key: AGENT_ROW[key] for key in WATCHER_AGENT_FIELDS}
    snapshot = {"type": "snapshot", "agents": [AGENT_ROW], "tabs": [{"target": "U1"}], "sessions": [],
                "browser": {"kind": "brave"}, "skills_summary": {}, "max_working": 3, "default_model": "sonnet",
                "browser_clients": [], "tab_scope": {"profile": "watcher", "elsewhere": 1}}
    agent = {"type": "agent", "agent": AGENT_ROW}
    check = {"type": "check_request", "agent": "a1", "name": "Fix the footer", "site": "www.google.com",
             "what": "a check", "target": "T1", "live": None}
    before = json.dumps([snapshot, agent, check])
    assert for_watcher(snapshot) == {"type": "snapshot", "agents": [row]}
    assert for_watcher(agent) == {"type": "agent", "agent": row}
    assert for_watcher(check) == {key: value for key, value in check.items() if key != "target"}
    assert json.dumps([snapshot, agent, check]) == before  # _send_all puts one dict in every queue
    for kind in ("watcher_hello", "watch_list", "notify", "open_thread", "fill_reply", "group_tab", "ungroup_tabs",
                 "permission_request", "check_request"):  # everything _to_watcher sends
        assert for_watcher({"type": kind}) is not None, kind
    assert for_watcher({"type": ["agent"]}) is None and for_watcher({}) is None
    assert for_watcher({"type": "snapshot"}) == {"type": "snapshot", "agents": []}


async def test_watcher_sockets_get_no_target_ids(fake_claude, tmp_path):
    from ai_browser.app.server import WATCHER_RECEIVES

    server, url, _ = await with_brain(fake_claude, tmp_path, [{"result": "[]"}])
    brave = FakeBrave([{"target": "U1-7f3a", "url": "https://shop.example/", "title": "Shop"},
                       {"target": "U2-7f3a", "url": "https://mail.example/", "title": "Mail"}])
    server.attach_brave(brave)
    agents = server.agents
    agent = add_agent(agents, adopted=["U2-7f3a"])
    agents.tab_event("a1", "working_tab", "T1-7f3a")
    server.sessions["cc-x"] = {"id": "cc-x", "name": "Claude Code", "color": "orange", "tabs": ["S1-7f3a"],
                               "pid": os.getpid()}
    try:
        async with (connect(socket_url(server, url), origin=WATCHER) as worker,
                    connect(socket_url(server, url), origin=WATCHER) as page,
                    connect(socket_url(server, url), origin=ORIGIN) as home):
            await worker.send(json.dumps({"type": "hello", "view": "watcher"}))
            got = {"worker": await until(worker, lambda m: m["type"] == "watch_list")}
            await page.send(json.dumps({"type": "hello", "view": "brain"}))
            got["page"] = await until(page, lambda m: m["type"] == "snapshot")
            await home.send(json.dumps({"type": "hello", "view": "home"}))
            got["home"] = await until(home, lambda m: m["type"] == "snapshot")
            agents.check_event("a1", {**CHECK_REPORT, "target": "T1-7f3a"})
            agent.permission = {"request": "r1", "server": "clickup", "tool": "mcp__clickup__create_task",
                                "input": {"name": "Fix footer"}}
            agents._changed(agent)
            agents._broadcast({"type": "permission_request", "agent": "a1", **agent.permission})
            brave.changed()
            server._sessions_changed()
            server._send_all({"type": "thumb", "id": "a1", "jpeg": "eHh4"})
            for name, ws in (("worker", worker), ("page", page), ("home", home)):
                got[name] += await quiet(ws, 1.0)
        for name in ("worker", "page"):
            assert "-7f3a" not in json.dumps(got[name]), name
            assert {m["type"] for m in got[name]} <= WATCHER_RECEIVES, name
        rows = [m["agent"] for m in got["page"] if m["type"] == "agent" and m["agent"].get("id") == "a1"]
        assert rows and rows[-1]["permission"]["request"] == "r1"  # the Brain page's card still works
        assert {"check_request", "permission_request"} <= {m["type"] for m in got["worker"]}
        assert any(m["type"] == "tabs" and any(tab["target"] == "U1-7f3a" for tab in m["tabs"])
                   for m in got["home"])  # AI Home still gets the list
    finally:
        await server.stop()


def test_only_the_role_reads_the_watchers_origins():
    from ai_browser.app.server import AppServer

    readers = sorted(name for name, member in vars(AppServer).items()
                     if inspect.isfunction(member) and "_watcher_origins" in inspect.getsource(member))
    assert readers == ["__init__", "_mismatch", "_role", "_socket", "allow_origin"]  # the rest asks _role
```

In `tests/test_app_server.py`, replace the whole of `test_check_reports_are_checked_then_reach_pages_and_the_watcher`
with the version below. Its `headers` line uses the relay's `server.token_for(agent.id)`; if the merged test builds
the headers another way, keep the merged line.

```python
async def test_check_reports_are_checked_then_reach_pages_and_the_watcher(fake_claude, tmp_path):
    from ai_browser.checks import KINDS

    server, url, _ = await with_brain(fake_claude, tmp_path, EVENTS)
    try:
        agent = await server.agents.create("Flights to Manila")
        good = {**CHECK_REPORT, "agent": agent.id}
        headers = {"X-AIB-Agent-Token": server.token_for(agent.id)}
        async with (connect(socket_url(server, url), origin=WATCHER) as watcher,
                    connect(socket_url(server, url), origin=ORIGIN) as page):
            await watcher.send(json.dumps({"type": "hello", "view": "watcher"}))
            await until(watcher, lambda message: message["type"] == "watch_list")
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            await until(page, lambda message: message["type"] == "snapshot")
            async with httpx.AsyncClient() as client:
                for bad in ({**good, "check": "dragon"}, {**good, "site": "www.google.com <b>"}, {**good, "site": "a b"},
                            {**good, "site": "www.google.com\n"}, {**good, "live": "http://evil.example/live?token=x"},
                            {**good, "live": "http://127.0.0.1:80@evil.example/live?token=x"}):  # Review Focus 2
                    response = await client.post(url + "/agent-events", json=bad, headers=headers)
                    assert response.status_code == 204 and agent.check is None, bad
                await client.post(url + "/agent-events", json=good, headers=headers)
                request = (await until(watcher, lambda message: message["type"] == "check_request"))[-1]
                assert request == {"type": "check_request", "agent": agent.id, "name": "Flights to Manila",
                                   "site": "www.google.com", "what": KINDS["google"], "live": None}  # no tab id
                shown = (await until(page, lambda message: message["type"] == "check_request"))[-1]
                assert shown["target"] == "T1"  # AI Home's own check card still has it (its Watch sends it)
                assert agent.state == "needs_you" and agent.check["check"] == "google"
                cleared = {"agent": agent.id, "kind": "check_cleared", "target": "T1", "adopted": False,
                           "how": "solved"}
                await client.post(url + "/agent-events", json=cleared, headers=headers)
                assert agent.check is None
    finally:
        await server.stop()
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_watcher_rules.py::test_what_the_watcher_receives_is_a_fixed_list tests/test_watcher_rules.py::test_watcher_sockets_get_no_target_ids tests/test_watcher_rules.py::test_only_the_role_reads_the_watchers_origins tests/test_app_server.py::test_check_reports_are_checked_then_reach_pages_and_the_watcher -q -p no:randomly`

Expected: FAIL. The first two with `ImportError` (`for_watcher`, `WATCHER_RECEIVES`): the second test imports the
list before it opens a socket, and once the import works it would still fail because the Brain page's snapshot carries
`tabs`, `sessions` and the agent rows' tab fields (and it gets `tabs`, `sessions` and `thumb`).
`test_only_the_role_reads_the_watchers_origins` fails with the relay's `browser_clients` check in its list (for
example `"_send_all"` or `"_snapshot"`); if the relay keeps watcher sockets from `browser_clients` without reading
`_watcher_origins`, it passes already, as a guard, and Step 3's grep for `browser_clients` finds that other check. The
last fails because the watcher's `check_request` still has `"target": "T1"`.

- [ ] **Step 3: Filter where every message leaves**

In `src/ai_browser/app/server.py`, add after `may_send` (Task 1):

```python
# What a socket from Brave's watcher's origin may get (watcher-safety Decision 5): never a tab list, a session, a
# picture, an agent's conversation or the Tools, workflow and skill messages, and never a tab's target id.
WATCHER_RECEIVES = frozenset({
    "ping", "error", "watcher_hello", "watch_list", "notify", "permission_request", "check_request", "group_tab",
    "ungroup_tabs", "open_thread", "fill_reply",  # for the worker
    "snapshot", "agent", "agent_closed", "brain_snapshot", "brain_item", "brain_item_gone", "brain_state",  # Brain page
})
WATCHER_AGENT_FIELDS = ("id", "name", "color", "state", "permission")  # what the Brain page reads of an agent


def _watcher_row(agent) -> dict:
    return {key: agent[key] for key in WATCHER_AGENT_FIELDS if key in agent} if isinstance(agent, dict) else {}


def for_watcher(message: dict) -> dict | None:
    """What a watcher-origin socket may get: the message, a trimmed copy, or None. It never changes its input,
    because _send_all puts one dict in every queue."""
    kind = message.get("type")
    if not isinstance(kind, str) or kind not in WATCHER_RECEIVES:
        return None  # a type added later is dropped too, until it is written down here
    if kind == "snapshot":
        agents = message.get("agents")
        return {"type": "snapshot", "agents": [_watcher_row(agent) for agent in agents]
                if isinstance(agents, list) else []}
    if kind == "agent":
        return {"type": "agent", "agent": _watcher_row(message.get("agent"))}
    if kind == "check_request":
        return {key: value for key, value in message.items() if key != "target"}  # Show me asks by agent id
    return message
```

Replace `_write`:

```python
    async def _write(self, ws: WebSocket, queue: asyncio.Queue) -> None:
        with contextlib.suppress(Exception):
            while True:
                await ws.send_json(await queue.get())
```

with:

```python
    async def _write(self, ws: WebSocket, queue: asyncio.Queue) -> None:
        """Every message to a socket passes here (answers, _send_all, _to_watcher), so a path added later is covered:
        a watcher-origin socket gets only for_watcher's part of each."""
        watcher = self._role(ws) == "watcher"  # read once: the socket's origin is set before this task starts
        with contextlib.suppress(Exception):
            while True:
                message = await queue.get()
                if watcher:
                    message = for_watcher(message)
                    if message is None:
                        continue
                await ws.send_json(message)
```

`_socket` sets `self._origin_of[ws] = origin` before it creates the writer task: check that the merged `_socket`
still does, in that order.

Then remove the relay's own check that keeps `browser_clients` from watcher sockets: `for_watcher` now drops
`browser_clients` and trims it out of the snapshot for every watcher socket. Find it with
`grep -n "browser_clients\|_watcher_origins" src/ai_browser/app/server.py`: a condition in `_send_all`, `_snapshot`
or the `hello` branch that skips or strips `browser_clients` by origin. Delete only that condition, and leave
`browser_clients` itself in the snapshot and in the broadcast to every socket (AI Home draws its list from them). If
the relay made it part of a helper, such as a snapshot built per socket, make that helper send the same to every
socket. Afterwards `grep -n "_watcher_origins" src/ai_browser/app/server.py` shows only `__init__`, `allow_origin`,
`_mismatch`, `_socket` and `_role`, which `test_only_the_role_reads_the_watchers_origins` pins. Step 4 runs the
relay's `test_browser_disconnect_only_from_our_pages`, which still checks that a watcher socket never receives
`browser_clients`.

- [ ] **Step 4: Run them, and the watcher's suites**

Run: `uv run pytest tests/test_watcher_rules.py tests/test_app_server.py tests/test_watcher.py tests/test_watcher_groups.py tests/test_ai_home_phase2.py::test_the_watcher_shows_a_permission_request -q -p no:randomly`

Expected: PASS. The watcher's notifications, inbox, grouping and permission card work on the trimmed messages, and
the relay's `test_browser_disconnect_only_from_our_pages` passes through `for_watcher` alone.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/server.py tests/test_watcher_rules.py tests/test_app_server.py
git commit -m "feat: a watcher socket gets only WATCHER_RECEIVES, trimmed, and never a tab's target id"
```

### Task 5: No lasting Always allow from Brave

**Files:**
- Modify: `src/ai_browser/app/extension/permission.js` (the whole file, below)
- Modify: `src/ai_browser/app/watcher/brain.js` (the `permissionCard(` call in `renderPermissions`)
- Test: `tests/test_ai_home_phase2.py` (`test_the_watcher_shows_a_permission_request`)

**Interfaces:**
- Consumes: Task 1's row `"permission": Rule(watcher=_once_or_deny)` (the server side of the same rule).
- Produces: `permissionCard(request, send, agentName = "", { always = true } = {})`. With `always: false`: no
  `.allow-always` button, and a muted `p.always-elsewhere` line, set with `textContent`: "Always allow is in AI Home's
  Tools." AI Home, Mission Control and the panel call it as today. The side chat (Wave D) passes `{ always: false }`
  too.

- [ ] **Step 1: Write the failing test**

In `tests/test_ai_home_phase2.py`, replace the whole of `test_the_watcher_shows_a_permission_request` with:

```python
@CHROME
async def test_the_watcher_shows_a_permission_request(watcher, tmp_path):
    from ai_browser.brain.tools import ToolsConfig

    tools = ToolsConfig(watcher.home, claude_home=user_config(tmp_path))
    tools.set_enabled("clickup", True)
    watcher.server.agents.tools = tools
    watcher.script.write_text(json.dumps(asking()), encoding="utf-8")
    _, js = await open_page(watcher.cdp, f"chrome-extension://{watcher.app.extension_id}/brain.html")
    await watcher.server.agents.create("make a ClickUp task")
    assert await until(watcher.worker_js, "chrome.notifications.getAll().then(all => Object.keys(all).length === 1)")
    card = "document.querySelector('#permissions .permission')"
    assert await until(js, f"{card} !== null")
    assert "create_task" in await js(f"{card}.textContent")
    assert await js(f"['.allow-once', '.deny', '.allow-always'].map((s) => {card}.querySelector(s) !== null)") == \
        [True, True, False]  # no lasting allow from Brave
    assert "Always allow is in AI Home's Tools." in await js(f"{card}.textContent")
    full = ("import('./permission.js').then(({permissionCard}) => permissionCard({request: 'r9', agent: 'a9', "
            "server: 'x', tool: 'mcp__x__y', input: {}}, () => true).querySelector('.allow-always') !== null)")
    assert await js(full) is True  # AI Home's card, with no options, keeps all three buttons
    await js(f"{card}.querySelector('.deny').click(); true")
    assert [answer["behavior"] for answer in await answered(watcher.log)] == ["deny"]
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_ai_home_phase2.py::test_the_watcher_shows_a_permission_request -q -p no:randomly`

Expected: FAIL: the buttons check gives `[True, True, True]`.

- [ ] **Step 3: The card's option, and the watcher's call**

Replace `src/ai_browser/app/extension/permission.js` with:

```js
// A tool request waiting for the user: which agent, the server, the tool and its exact input, shown as text. Allow
// once, Always allow (remembered in AI Home's Tools) or Deny: only these clicks answer it, never anything a page says.
// The watcher's Brain page in Brave passes { always: false }: its card has Allow once and Deny only, and a line saying
// where Always allow is (a lasting allow is given in AI Browser's own pages only).
"use strict";

const LIMIT = 4000; // characters of the input shown before "Show all"
const ELSEWHERE = "Always allow is in AI Home's Tools.";

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function permissionCard(request, send, agentName = "", { always = true } = {}) {
  const card = el("div", "permission card");
  card.dataset.request = request.request;
  const tool = String(request.tool || "");
  const short = tool.split("__").slice(2).join("__") || tool;
  card.append(el("div", "permission-head", `${agentName || "An agent"} wants to use a tool`));
  const line = el("div", "permission-tool");
  line.append(el("span", "chip", request.server || "tool"), el("strong", "", short));
  card.append(line);
  const input = JSON.stringify(request.input ?? {}, null, 2);
  const shown = el("pre", "permission-input", input.length > LIMIT ? `${input.slice(0, LIMIT)}…` : input);
  card.append(shown);
  if (input.length > LIMIT) {
    const more = el("button", "ghost more", "Show all");
    more.addEventListener("click", () => {
      shown.textContent = input;
      more.remove();
    });
    card.append(more);
  }
  const buttons = el("div", "row permission-buttons");
  const done = el("span", "muted");
  const choices = [["allow-once primary", "Allow once", "once"],
                   ...(always ? [["allow-always", "Always allow", "always"]] : []),
                   ["deny", "Deny", "deny"]];
  for (const [className, label, answer] of choices) {
    const choice = el("button", className, label);
    choice.addEventListener("click", () => {
      if (!send({ type: "permission", agent: request.agent, request: request.request, answer })) return;
      for (const other of buttons.querySelectorAll("button")) other.disabled = true;
      done.textContent = answer === "deny" ? "Denied" : "Allowed";
    });
    buttons.append(choice);
  }
  buttons.append(done);
  card.append(buttons);
  if (!always) card.append(el("p", "muted always-elsewhere", ELSEWHERE));
  return card;
}
```

In `src/ai_browser/app/watcher/brain.js`, in `renderPermissions`, replace:

```js
      const card = permissionCard({ ...agent.permission, agent: agent.id }, (message) => link.send(message),
                                  agent.name);
```

with:

```js
      const card = permissionCard({ ...agent.permission, agent: agent.id }, (message) => link.send(message),
                                  agent.name, { always: false }); // Always allow stays in AI Home's Tools
```

- [ ] **Step 4: Run it, and the other cards' tests**

Run: `uv run pytest tests/test_ai_home_phase2.py tests/test_panel.py tests/test_mission.py -q -p no:randomly`

Expected: PASS. AI Home's, the panel's and Mission Control's cards keep **Always allow**.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/extension/permission.js src/ai_browser/app/watcher/brain.js tests/test_ai_home_phase2.py
git commit -m "feat: the watcher's tool card offers Allow once and Deny; Always allow stays in AI Home's Tools"
```

### Task 6: The tab list carries its scope (`tab_scope`)

**Files:**
- Modify: `src/ai_browser/app/server.py` (`attach_tabs`, `attach_brave`, `_snapshot`; new `_tab_scope`,
  `_tabs_message`)
- Modify: `tests/fake_brave.py` (`FakeBrave.scope`, `FakeBrave.set_scope`)
- Test: `tests/test_app_server.py`

**Interfaces:**
- Consumes: Task 4's filter (watcher sockets get no `tabs` and a trimmed snapshot).
- Produces:
  - `AppServer._tab_scope(self) -> dict | None`: the tab source's `scope()` when it has one (BraveLink, FakeBrave),
    else `None` (AI Browser's own `TabWatch`, which must never gain a `scope` attribute);
  - `AppServer._tabs_message(self, listing: list[dict]) -> dict`: `{"type": "tabs", "tabs": listing}` plus
    `"tab_scope"` when there is one;
  - the snapshot gains `"tab_scope"` (`null` in AI Browser mode);
  - `FakeBrave.scope() -> dict` (by default `{"profile": "watcher", "elsewhere": 0}`) and
    `FakeBrave.set_scope(profile: str, elsewhere: int)`, which calls `changed()`. Task 11 uses both.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_app_server.py` (after `test_the_watcher_may_not_hand_tabs_or_connect`):

```python
async def test_the_tab_list_carries_its_scope(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    server.allow_origin(WATCHER, watcher=True)
    brave = FakeBrave([{"target": "U1", "url": "https://shop.example/", "title": "Shop"}])
    brave.set_scope("watcher", 2)
    server.attach_brave(brave)
    try:
        async with (connect(socket_url(server, url), origin=ORIGIN) as page,
                    connect(socket_url(server, url), origin=WATCHER) as watcher):
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            await watcher.send(json.dumps({"type": "hello", "view": "brain"}))
            assert (await recv(page))["tab_scope"] == {"profile": "watcher", "elsewhere": 2}
            trimmed = await recv(watcher)
            assert trimmed["type"] == "snapshot" and "tab_scope" not in trimmed and "tabs" not in trimmed
            brave.set_scope("last_used", 3)
            message = (await until(page, lambda m: m["type"] == "tabs"))[-1]
            assert message["tab_scope"] == {"profile": "last_used", "elsewhere": 3}
            assert [tab["target"] for tab in message["tabs"]] == ["U1"]
            assert not [m for m in await quiet(watcher, 1.0) if m["type"] == "tabs" or "tab_scope" in m]
    finally:
        await server.stop()
    plain, plain_url = await started(fake_claude, tmp_path / "plain", EVENTS, tabs=StubTabs())
    try:
        async with connect(socket_url(plain, plain_url), origin=ORIGIN) as page:
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            assert (await recv(page))["tab_scope"] is None  # AI Browser's own TabWatch lists every tab
    finally:
        await plain.stop()
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_app_server.py::test_the_tab_list_carries_its_scope -q -p no:randomly`

Expected: FAIL with `AttributeError: 'FakeBrave' object has no attribute 'set_scope'`.

- [ ] **Step 3: Send the scope with the list**

In `tests/fake_brave.py`, add to `class FakeBrave` (after `def tabs(self):`'s method):

```python
    tab_scope = {"profile": "watcher", "elsewhere": 0}  # what BraveLink.scope() answers (watcher-safety)

    def scope(self):
        return dict(self.tab_scope)

    def set_scope(self, profile, elsewhere):
        self.tab_scope = {"profile": profile, "elsewhere": elsewhere}
        self.changed()
```

In `src/ai_browser/app/server.py`:

1. Replace `attach_tabs`:

```python
    def attach_tabs(self, tabs) -> None:
        """The TabWatch, once AI Browser is open: the tab list, Watch and thumbnails."""
        self.tabs = tabs
        tabs.on_change(lambda listing: self._send_all({"type": "tabs", "tabs": listing}))
```

   with:

```python
    def attach_tabs(self, tabs) -> None:
        """The tab source (AI Browser's TabWatch, or BraveLink in brave mode): the tab list, Watch and thumbnails."""
        self.tabs = tabs
        tabs.on_change(lambda listing: self._send_all(self._tabs_message(listing)))

    def _tab_scope(self) -> dict | None:
        """BraveLink's {"profile", "elsewhere"}: which profile the list shows, and how many of the user's tabs it
        leaves out (a number only). None for AI Browser's own TabWatch, which lists every tab."""
        scope = getattr(self.tabs, "scope", None)
        return scope() if callable(scope) else None

    def _tabs_message(self, listing: list[dict]) -> dict:
        scope = self._tab_scope()
        return {"type": "tabs", "tabs": listing, **({"tab_scope": scope} if scope is not None else {})}
```

2. In `attach_brave`, replace `self._send_all({"type": "tabs", "tabs": brave.tabs()})` with
   `self._send_all(self._tabs_message(brave.tabs()))` (keep its comment).

3. In `_snapshot`, add `"tab_scope": self._tab_scope(),` after the `"tabs": ...` entry.

- [ ] **Step 4: Run it, and the server's file**

Run: `uv run pytest tests/test_app_server.py tests/test_watcher_rules.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/server.py tests/fake_brave.py tests/test_app_server.py
git commit -m "feat: the tab list and the snapshot carry tab_scope (which profile, how many left out)"
```

### Task 7: TabWatch sees contexts, service workers and the default context

**Files:**
- Modify: `src/ai_browser/app/tabs.py` (the docstring, `__init__`, `start`, `tabs`, a new `pages`, `has_pages`'s
  docstring, `_on_target`, `_on_destroyed`, `_refresh`, a new `worker_contexts`, `_read_default`)
- Modify: `tests/fake_brave.py` (`FakePort`: contexts, workers, `Target.getBrowserContexts`, `set_default`,
  `destroy`, `add_worker`)
- Test: `tests/test_tabwatch.py`

**Interfaces:**
- Consumes: the relay's `TabWatch(..., cdp=None)` and its `APP_COMMANDS = {"Target.getBrowserContexts"}`; the relay's
  `FakePort` in `tests/fake_brave.py`.
- Produces:
  - `TabWatch.pages() -> list[dict]`: rows `{"target", "url", "title", "context"}` (context: the page's
    `browserContextId`, `""` if none was reported), with the same pages as `tabs()`;
  - `TabWatch.tabs()` rows keep exactly `target`, `url` and `title`; `has_pages()` never counts a worker;
  - `TabWatch.worker_contexts(extension_id: str) -> set[str]`: the contexts of service workers whose url starts with
    `chrome-extension://<extension_id>/`; an empty id matches nothing;
  - `TabWatch.default_context: str | None`: `defaultBrowserContextId`, read at start and in each refresh round; a
    failed read keeps the last value;
  - `on_change` also fires when a worker comes or goes, or the default context changes;
  - `FakePort(folder, answer="accept", pages=(), workers=(), default="C0")` (keep any parameter the relay added): a
    page's `"context"` (default `"C0"`) goes out as `browserContextId`; `workers` are
    `{"target", "url", "context"}` reported as `service_worker` targets; `set_default(context | None)`;
    `async destroy(target)`; `async add_worker(worker)`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_tabwatch.py`:

```python
async def test_contexts_workers_and_the_default_on_a_fake_port(tmp_path):
    from ai_browser.app.tabs import TabWatch
    from ai_browser.chrome import find_ws_url
    from fake_brave import FakePort

    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    page = {"target": "U1", "url": "https://mail.example/", "title": "Mail", "context": "W"}
    worker = {"target": "SW1", "url": "chrome-extension://abc/worker.js", "context": "W"}
    port = FakePort(folder, pages=[page], workers=[worker], default="P")
    await port.start()
    watch = TabWatch(find_ws_url(folder), "")
    changes = []
    watch.on_change(changes.append)
    await watch.start()
    try:
        assert await until(lambda: watch.pages() == [page])
        assert watch.tabs() == [{"target": "U1", "url": "https://mail.example/", "title": "Mail"}]
        assert watch.worker_contexts("abc") == {"W"}
        assert watch.worker_contexts("") == set() and watch.worker_contexts("other") == set()
        assert watch.default_context == "P"
        port.set_default("C2")  # the user used another profile last
        assert await until(lambda: watch.default_context == "C2")
        port.set_default(None)  # a failed read keeps the last value
        await asyncio.sleep(2)
        assert watch.default_context == "C2"
        await port.destroy("U1")
        assert await until(lambda: watch.pages() == [])
        assert watch.tabs() == [] and not watch.has_pages()  # a worker is never a page
        assert watch.worker_contexts("abc") == {"W"}
        await port.destroy("SW1")  # the worker sleeps
        assert await until(lambda: watch.worker_contexts("abc") == set())
        seen = len(changes)
        await port.add_worker(worker)  # it wakes
        assert await until(lambda: watch.worker_contexts("abc") == {"W"})
        assert await until(lambda: len(changes) > seen)  # on_change fires for workers too
    finally:
        await watch.close()
        await port.stop()


@CHROME
async def test_pages_carry_their_context_and_workers_are_seen(app_browser):
    from ai_browser.app.tabs import TabWatch
    from ai_browser.cdp import CDP

    app, base = app_browser
    watch = TabWatch(app.ws_url, app.extension_id)
    await watch.start()
    cdp = await CDP.connect(app.ws_url)
    try:
        page = (await cdp.send("Target.createTarget", {"url": base + "privacy.html"}))["targetId"]
        assert await until(lambda: any(row["target"] == page for row in watch.pages()))
        assert await until(lambda: bool(watch.worker_contexts(app.extension_id)), 10)
        contexts = {row["context"] for row in watch.pages()}
        assert len(contexts) == 1 and "" not in contexts  # one profile, one context
        assert watch.default_context in contexts
        assert watch.worker_contexts(app.extension_id) == contexts
        assert all(set(tab) == {"target", "url", "title"} for tab in watch.tabs())
    finally:
        await cdp.close()
        await watch.close()
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_tabwatch.py -q -p no:randomly`

Expected: the two new tests FAIL: the first with `TypeError: FakePort.__init__() got an unexpected keyword argument
'workers'`, the second with `AttributeError: 'TabWatch' object has no attribute 'pages'`. The three existing tests
PASS.

- [ ] **Step 3: Contexts, workers and the default context**

**`tests/fake_brave.py`, `FakePort`** (the relay's version; keep everything it has):
1. Add `import contextlib` to the imports if it isn't there.
2. Its `__init__` gains the keyword parameters `workers=()` and `default="C0"` after `pages=()`, and sets:

```python
        self.workers = [dict(worker) for worker in workers]  # {"target", "url", "context"}: service workers
        self.default = default  # Target.getBrowserContexts' defaultBrowserContextId; None makes it fail
        self._live = set()  # the open sockets, for destroy and add_worker
```

3. In `infos()`, give each page's dict `"browserContextId": page.get("context", "C0")`, and return the workers after
   the pages. Today's `infos()` then reads (keep any field the relay added to a page's dict):

```python
    def infos(self):
        pages = [{"targetId": page["target"], "type": "page", "url": page["url"], "title": page["title"],
                  "browserContextId": page.get("context", "C0")} for page in self.pages]
        return pages + [self._worker_info(worker) for worker in self.workers]
```

4. In `_handler`, add `self._live.add(ws)` before its `async for raw in ws:` loop, and wrap the loop in
   `try:` … `finally: self._live.discard(ws)`. (If the relay's `FakePort` already keeps its open sockets and has a
   method that sends an event to them, which it needs to emit `targetCreated` with an `openerId` on request, use that
   in `_tell_all` below and skip `_live`.) Right after the line that records the method (today
   `self.methods.append(method)`; the relay records it with its `sessionId`), add:

```python
            if method == "Target.getBrowserContexts" and self.default is None:  # a failed read
                await ws.send(json.dumps({"id": message["id"], "error": {"code": -32000, "message": "Not available"}}))
                continue
```

   and in its chain of answers (the `if method == "Target.getTargets":` … `elif` branches) add the branch below. If
   the relay's `FakePort` already answers `Target.getBrowserContexts` (its test that the app's own client may read
   it), replace that branch with this one rather than adding a second:

```python
            elif method == "Target.getBrowserContexts":
                result = {"browserContextIds": [], "defaultBrowserContextId": self.default}
```

5. Add these methods to `FakePort`:

```python
    # ---- watcher-safety: profiles, private windows and the watcher's worker --------------------------------------

    def set_default(self, context):
        """The context Brave would name as its default (the profile used last); None makes the read fail."""
        self.default = context

    @staticmethod
    def _worker_info(worker):
        return {"targetId": worker["target"], "type": "service_worker", "url": worker["url"], "title": "",
                "browserContextId": worker["context"]}

    async def _tell_all(self, method, params):
        for ws in list(self._live):
            with contextlib.suppress(Exception):
                await ws.send(json.dumps({"method": method, "params": params}))

    async def destroy(self, target):
        """A page closes, or a service worker goes to sleep: Target.targetDestroyed."""
        self.pages = [page for page in self.pages if page["target"] != target]
        self.workers = [worker for worker in self.workers if worker["target"] != target]
        await self._tell_all("Target.targetDestroyed", {"targetId": target})

    async def add_worker(self, worker):
        """A service worker starts (the watcher's worker wakes up): Target.targetCreated."""
        self.workers.append(dict(worker))
        await self._tell_all("Target.targetCreated", {"targetInfo": self._worker_info(worker)})
```

**`src/ai_browser/app/tabs.py`:**
1. The module docstring gains one sentence at its end: "It also knows each page's browser context (its profile, or a
   private window), the service workers, and the context the browser used last, for BraveLink's one-profile list;
   all of it from the target list, never by attaching."
2. In `__init__`, replace the `self._pages` line with:

```python
        self._pages: dict[str, dict] = {}  # target id -> {"target", "url", "title", "context"}, in the order they came
        self._workers: dict[str, dict] = {}  # service-worker target id -> {"url", "context"}: never pages
        self.default_context: str | None = None  # defaultBrowserContextId: the profile the browser used last
```

3. In `start()`, right after `await self._cdp.send("Target.setDiscoverTargets", {"discover": True})  # also announces
   the open ones`, add:

```python
        await self._read_default()  # the profile used last (BraveLink's fallback); a failed read leaves None
```

4. Add these module-level helpers after `REFRESH = 1.5 ...`:

```python
def _page(info: dict) -> dict:
    return {"target": info["targetId"], "url": info.get("url", ""), "title": info.get("title", ""),
            "context": info.get("browserContextId", "")}


def _worker(info: dict) -> dict:
    return {"url": info.get("url", ""), "context": info.get("browserContextId", "")}
```

5. Replace `tabs()`, `has_pages()`, `_on_target`, `_on_destroyed` and `_refresh` with:

```python
    def tabs(self) -> list[dict]:
        """The user's and the agents' tabs; AI Browser's own pages (AI Home, the panel) are left out. Each row has
        exactly target, url and title."""
        return [{key: page[key] for key in ("target", "url", "title")} for page in self.pages()]

    def pages(self) -> list[dict]:
        """The same pages as tabs(), each with its browser context (for BraveLink, which never sends it on)."""
        own = f"chrome-extension://{self.extension_id}/"
        return [dict(page) for page in self._pages.values()
                if not page["url"].startswith(own) and not page["url"].startswith("chrome://newtab")]

    def worker_contexts(self, extension_id: str) -> set[str]:
        """The contexts of that extension's running service workers (a sleeping worker isn't listed)."""
        if not extension_id:
            return set()
        prefix = f"chrome-extension://{extension_id}/"
        return {worker["context"] for worker in self._workers.values()
                if worker["url"].startswith(prefix) and worker["context"]}

    def has_pages(self) -> bool:
        """Whether AI Browser still shows anything at all (a tab, AI Home, the side panel). A worker isn't a page."""
        return bool(self._pages)

    def _on_target(self, params: dict, session: str | None) -> None:
        info = params.get("targetInfo", {})
        if info.get("type") == "page":
            self._pages[info["targetId"]] = _page(info)
            self._changed()
        elif info.get("type") == "service_worker" and self._workers.get(info["targetId"]) != _worker(info):
            self._workers[info["targetId"]] = _worker(info)
            self._changed()

    def _on_destroyed(self, params: dict, session: str | None) -> None:
        target = params.get("targetId")
        page = self._pages.pop(target, None)
        worker = self._workers.pop(target, None)
        if page is not None or worker is not None:
            self._changed()

    async def _read_default(self) -> bool:
        """Read defaultBrowserContextId; True when it changed. A failed read keeps the last value."""
        try:
            answer = await self._cdp.send("Target.getBrowserContexts", timeout=5)
        except CDPError:
            return False
        context = answer.get("defaultBrowserContextId") or None
        if context == self.default_context:
            return False
        self.default_context = context
        return True

    async def _refresh(self) -> None:
        while not self._cdp.closed:
            await asyncio.sleep(REFRESH)
            changed = await self._read_default()
            try:
                infos = (await self._cdp.send("Target.getTargets", timeout=5))["targetInfos"]
            except CDPError:
                if changed:
                    self._changed()
                continue
            pages = {info["targetId"]: _page(info) for info in infos if info.get("type") == "page"}
            workers = {info["targetId"]: _worker(info) for info in infos if info.get("type") == "service_worker"}
            if pages != self._pages:
                self._pages = {**{key: pages[key] for key in self._pages if key in pages}, **pages}  # keep the order
                changed = True
            if workers != self._workers:
                self._workers = workers
                changed = True
            if changed:
                self._changed()
```

- [ ] **Step 4: Run them, the relay's drift test, and BraveLink's file**

Run: `uv run pytest tests/test_tabwatch.py tests/test_bravelink.py tests/test_appmode.py -q -p no:randomly`

Expected: PASS. AI Browser mode is unchanged: its rows still have exactly `target`, `url` and `title`.

Run: `uv run pytest tests/test_cdprelay.py -q -p no:randomly -k every_method`

Expected: PASS: `Target.getBrowserContexts` from `app/tabs.py` passes the relay's policy for the app's own client
(`APP_COMMANDS`).

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/tabs.py tests/fake_brave.py tests/test_tabwatch.py
git commit -m "feat: TabWatch keeps each page's context, the service workers and the default context"
```

### Task 8: BraveLink lists one profile, and counts the rest

**Files:**
- Modify: `src/ai_browser/app/bravelink.py` (the docstring, `__init__`, `_changed`, `tabs`, `mark_brain`'s neighbours,
  `page_text`; new `agents_context`, `_shown`, `scope`)
- Test: `tests/test_bravelink.py`

**Interfaces:**
- Consumes: Task 7's `TabWatch.pages()`, `worker_contexts(id)` and `default_context`; the relay's
  `BraveLink(folder, allow_wait, every, tokens=None)` and `self._watch`.
- Produces:
  - `BraveLink(folder, watcher_id: str = "", allow_wait=ALLOW_WAIT, every=SWITCH_EVERY, tokens=None)`;
  - `BraveLink.agents_context() -> tuple[str | None, str]`: `(context, source)`, source `"watcher"`, `"last_used"`
    or `"none"` (Decision 7). browser-profile-choice (Wave C) replaces it with the profile picked in Settings;
  - `BraveLink.tabs()`: rows `{target, url, title, owner}` (never `context`): the AI's tabs (owner `agent`,
    `session` or `handed`) in any profile when they are web pages, the AI's own blank tabs (`agent` or `session`), and
    the user's web pages (no owner, or `brain`) in the agents' context only;
  - `BraveLink.scope() -> {"profile": source, "elsewhere": n}`: `n` counts the user's web pages that `tabs()` leaves
    out;
  - on_change callbacks fire only when `(connection, rows, scope)` differs from the last one sent;
  - `page_text(target, picked=True)` reads only a listed target.

- [ ] **Step 1: Write the failing tests**

In `tests/test_bravelink.py`, add after `AGENT = {...}`:

```python
HANDED = {"kind": "handed", "id": "a1", "name": "Fix the footer", "color": "blue"}
WATCHER_ID = "abcdefghijklmnopabcdefghijklmnop"  # the watcher's extension id (run.py computes it from its folder)
WORKER = {"target": "SW1", "url": f"chrome-extension://{WATCHER_ID}/worker.js", "context": "W"}
PROFILES = [  # W: the watcher's profile; P: another profile, the one used last; X: a private window
    {"target": "U1", "url": "https://mail.example/", "title": "SECRET-W", "context": "W"},
    {"target": "U2", "url": "https://bank.example/", "title": "SECRET-P", "context": "P"},
    {"target": "U3", "url": "https://private.example/", "title": "SECRET-X", "context": "X"},
    {"target": "A1", "url": "https://shop.example/", "title": "Agent page", "context": "P"},
    {"target": "H1", "url": "https://docs.example/", "title": "Handed page", "context": "W"},
]


def targets(link):
    return sorted(tab["target"] for tab in link.tabs())


async def connected(folder, watcher_id=WATCHER_ID):
    from ai_browser.app.bravelink import BraveLink

    link = BraveLink(folder, watcher_id=watcher_id, every=0.1)
    await link.start()
    await link.connect()
    assert link.state == "connected"
    return link
```

In `test_the_users_tabs_are_listed_but_never_attached`, after
`assert await until(lambda: len(link.tabs()) == 2)  # web pages only: ...`, add:

```python
        assert all("context" not in tab for tab in link.tabs())  # context ids never leave BraveLink
```

Add at the end of `tests/test_bravelink.py` (before the `@CHROME` test if you like; order doesn't matter):

```python
async def test_only_the_agents_profile_is_listed_and_the_rest_is_counted(tmp_path):
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=PROFILES, workers=[WORKER], default="P")
    await port.start()
    link = await connected(folder)
    try:
        link.set_owner("A1", AGENT)
        link.set_owner("H1", HANDED)
        assert await until(lambda: link.scope()["profile"] == "watcher")
        assert targets(link) == ["A1", "H1", "U1"]  # the watcher's profile, and the AI's tabs wherever they are
        listed = json.dumps(link.tabs())
        assert "context" not in listed and "SECRET-P" not in listed and "SECRET-X" not in listed
        assert link.scope() == {"profile": "watcher", "elsewhere": 2}  # U2 (another profile), U3 (a private window)
        assert link.agents_context() == ("W", "watcher")
        assert port.sessions == 1  # no new connection to Brave
    finally:
        await link.close()
        await port.stop()


async def test_without_the_watcher_the_profile_used_last_is_listed(tmp_path):
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=PROFILES, default="P")
    await port.start()
    link = await connected(folder)
    try:
        assert await until(lambda: targets(link) == ["A1", "U2"])
        assert link.scope() == {"profile": "last_used", "elsewhere": 3}
        port.set_default("W")  # the user used the other profile last
        assert await until(lambda: targets(link) == ["H1", "U1"])
        assert link.scope() == {"profile": "last_used", "elsewhere": 3}
        await port.add_worker(WORKER)
        assert await until(lambda: link.scope()["profile"] == "watcher")
        await port.add_worker({**WORKER, "target": "SW2", "context": "X"})  # one watcher folder in two profiles
        assert await until(lambda: link.scope()["profile"] == "last_used")  # which one groups? the fallback
    finally:
        await link.close()
        await port.stop()


async def test_the_watchers_profile_outlives_its_sleeping_worker_but_not_the_connection(tmp_path):
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=PROFILES, workers=[WORKER], default="P")
    await port.start()
    link = await connected(folder)
    try:
        assert await until(lambda: link.scope()["profile"] == "watcher")
        await port.destroy("SW1")  # the worker sleeps
        await asyncio.sleep(2)  # past a refresh round
        assert link.agents_context() == ("W", "watcher") and targets(link) == ["H1", "U1"]
        await port.stop()  # Brave quits
        assert await until(lambda: link.state == "lost")
        port = FakePort(folder, pages=PROFILES, default="P")  # Brave again: the worker hasn't woken yet
        await port.start()
        await link.connect()
        assert link.state == "connected"
        assert await until(lambda: link.scope()["profile"] == "last_used")
        assert await until(lambda: targets(link) == ["A1", "U2"])
        await port.add_worker(WORKER)  # it wakes within half a minute (its reconnect alarm)
        assert await until(lambda: link.scope()["profile"] == "watcher")
    finally:
        await link.close()
        await port.stop()


async def test_with_no_profile_known_no_tab_of_the_users_is_listed(tmp_path):
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=PROFILES, default=None)  # Target.getBrowserContexts answers an error
    await port.start()
    link = await connected(folder)
    try:
        link.set_owner("A1", AGENT)
        assert await until(lambda: targets(link) == ["A1"])  # only the AI's
        assert link.scope() == {"profile": "none", "elsewhere": 4}
    finally:
        await link.close()
        await port.stop()


async def test_a_hidden_tab_cannot_be_read_or_marked(tmp_path):
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=PROFILES, default="W")
    await port.start()
    link = await connected(folder, watcher_id="")
    try:
        assert await until(lambda: targets(link) == ["H1", "U1"])
        assert await link.page_text("U2", picked=True) == ""  # another profile: not listed, never read
        assert "U2" not in port.attached
        link.mark_brain("https://bank.example/")  # nothing in the list shows it: nothing is marked
        assert await link.page_text("U1", picked=True) == "page text"  # a listed tab still can be (control)
        assert "U1" in port.attached
        port.set_default("P")
        assert await until(lambda: "U2" in targets(link))
        assert next(tab for tab in link.tabs() if tab["target"] == "U2")["owner"] == {"kind": "you"}
    finally:
        await link.close()
        await port.stop()


async def test_a_waking_and_sleeping_worker_doesnt_resend_the_list(tmp_path):  # Review Focus 3
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=PROFILES, workers=[WORKER], default="P")
    await port.start()
    link = await connected(folder)
    changes = []
    link.on_change(changes.append)
    try:
        assert await until(lambda: link.scope()["profile"] == "watcher")
        await asyncio.sleep(2)  # settled, past a refresh round
        settled = len(changes)
        for _ in range(3):
            await port.destroy("SW1")
            await asyncio.sleep(0.3)
            await port.add_worker(WORKER)
            await asyncio.sleep(0.3)
        await asyncio.sleep(2)
        assert len(changes) == settled  # neither the rows nor the scope changed
    finally:
        await link.close()
        await port.stop()


async def test_a_tab_let_go_in_another_profile_leaves_the_list_for_the_count(tmp_path):  # Review Focus 4
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=PROFILES, default="P")  # no watcher: the profile used last, P
    await port.start()
    link = await connected(folder, watcher_id="")
    try:
        assert await until(lambda: link.scope() == {"profile": "last_used", "elsewhere": 3})
        link.set_owner("H1", HANDED)  # handed to a1, in profile W
        link.set_owner("U1", AGENT)
        assert targets(link) == ["A1", "H1", "U1", "U2"] and link.scope()["elsewhere"] == 1
        link.forget("H1")  # Take back
        assert "H1" not in targets(link) and link.scope()["elsewhere"] == 2
        link.release("a1")  # the agent closed
        assert targets(link) == ["A1", "U2"] and link.scope()["elsewhere"] == 3
        assert "SECRET-W" not in json.dumps(link.tabs())
    finally:
        await link.close()
        await port.stop()
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_bravelink.py -q -p no:randomly`

Expected: the new tests FAIL with `TypeError: BraveLink.__init__() got an unexpected keyword argument 'watcher_id'`
(and, once that is fixed, because U2 and U3 are listed as "you" with their titles). The existing tests PASS: their
pages are in "C0", the profile used last.

- [ ] **Step 3: One profile, and the count**

In `src/ai_browser/app/bravelink.py`:

1. Add a paragraph at the end of the module docstring:

```
AI Home lists the user's web tabs of one profile only, the agents' (the one the watcher runs in, else the one Brave
used last): other profiles and private windows are only counted. The AI's tabs are listed wherever they are. Context
ids never leave this class.
```

2. After `YOU = {"kind": "you"}`, add:

```python
USERS = ("you", "brain")  # the user's own tabs (a Brain row is theirs): listed only in the agents' profile
WEB = ("http://", "https://")
```

3. In `__init__`, add `watcher_id: str = ""` as the second parameter (after `folder`; keep every parameter the relay
   added, such as `tokens`), and add to its body:

```python
        self.watcher_id = watcher_id  # the watcher's extension id; "" = no watcher, so the profile used last
        self._watcher_contexts: set[str] = set()  # every context its worker was seen in, on this connection
        self._seen_on: TabWatch | None = None  # the connection those were seen on: a new one starts again
        self._last = None  # (connection, rows, scope) last sent to the on_change callbacks
```

   Check with `grep -rn "BraveLink(" src tests` that no caller passes `allow_wait` by position.

4. Replace `_changed` and `tabs` with:

```python
    def _changed(self) -> None:
        """Call back only when the rows or the scope changed (a worker waking or sleeping changes neither), or the
        connection did: connecting and losing it always call back."""
        tabs, scope = self.tabs(), self.scope()
        sent = (self._watch, tabs, scope)
        if sent == self._last:
            return
        self._last = sent
        for callback in list(self._changes):
            with contextlib.suppress(Exception):
                callback(tabs)

    def agents_context(self) -> tuple[str | None, str]:
        """(context, source) of the profile whose tabs AI Home lists: the one the watcher runs in ("watcher"), else
        the one Brave used last ("last_used"), else none ("none"). A sleeping worker drops out of Brave's target list,
        so a context it was seen in counts for the rest of this connection."""
        watch = self._watch
        if watch is not self._seen_on:  # a new connection (or none): what the last one saw is forgotten
            self._seen_on, self._watcher_contexts = watch, set()
        if watch is None:
            return None, "none"
        if self.watcher_id:
            self._watcher_contexts |= watch.worker_contexts(self.watcher_id)
        if len(self._watcher_contexts) == 1:  # in two profiles the app can't tell which one groups: the fallback
            return next(iter(self._watcher_contexts)), "watcher"
        if watch.default_context:
            return watch.default_context, "last_used"
        return None, "none"

    def _shown(self, page: dict, context: str | None) -> bool:
        owner = self._owners.get(page["target"], YOU)
        web = page["url"].startswith(WEB)
        if owner["kind"] in READABLE:  # the AI's tabs, wherever they are: the user must see, Watch and Take back them
            return web or (owner["kind"] in ("agent", "session") and page["url"].startswith("about:blank"))
        return web and context is not None and page["context"] == context

    def tabs(self) -> list[dict]:
        """The rows AI Home may show: the user's web pages (http and https) in the agents' profile, and the AI's tabs
        anywhere (its own blank tabs too), each with its owner. No row carries its context."""
        if self._watch is None:
            return []
        context, _ = self.agents_context()
        return [{"target": page["target"], "url": page["url"], "title": page["title"],
                 "owner": dict(self._owners.get(page["target"], YOU))}
                for page in self._watch.pages() if self._shown(page, context)]

    def scope(self) -> dict:
        """Which profile tabs() shows, and how many of the user's web pages it leaves out (other profiles and private
        windows, which CDP can't tell apart): a number, never a title, an address or an id."""
        context, source = self.agents_context()
        pages = self._watch.pages() if self._watch is not None else []
        elsewhere = sum(1 for page in pages if page["url"].startswith(WEB)
                        and self._owners.get(page["target"], YOU)["kind"] in USERS and not self._shown(page, context))
        return {"profile": source, "elsewhere": elsewhere}
```

   Do not reset `_watcher_contexts` or `_last` in `connect()`: both follow the `TabWatch` object, and the relay's
   `connect()` makes a new one for each connection.

5. Replace `page_text` with:

```python
    async def page_text(self, target: str, picked: bool = False) -> str:
        """A tab's text for a skill draft: the AI's tabs, or the page the user picked in the Train form, which must be
        a listed tab (never one in another profile or a private window). Nothing attaches otherwise."""
        if self._watch is None:
            return ""
        if not (self._readable(target) or (picked and any(tab["target"] == target for tab in self.tabs()))):
            return ""
        return await self._watch.page_text(target)
```

`mark_brain` keeps its code: it searches `tabs()`, which now holds only the agents' profile. `_handable` in the server
reads `tabs()` too, so Hand over and `new_task` with `adopt` accept only a listed tab with no new code.

- [ ] **Step 4: Run them, and the server's brave tests**

Run: `uv run pytest tests/test_bravelink.py tests/test_tabwatch.py tests/test_app_server.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/bravelink.py tests/test_bravelink.py
git commit -m "feat: AI Home lists the user's tabs of the agents' profile only, and counts the rest"
```

### Task 9: Proven in a real Chrome, and wired in run.py

**Files:**
- Modify: `src/ai_browser/app/run.py` (the line `brave = BraveLink(own, ...)`)
- Modify: `tests/test_watcher.py` (the `watcher` fixture's BraveLink, from cdp-relay)
- Test: `tests/test_bravelink.py`, `tests/test_watcher.py`, `tests/test_app_run.py`

**Interfaces:**
- Consumes: Task 8's `BraveLink(..., watcher_id=...)`, `agents_context()`, `scope()`; `appbrowser.extension_id_for`;
  `chrome.launch(folder, headless=True, extra_args=...)` (it appends `about:blank` after `extra_args`).
- Produces: in brave mode, `BraveLink(own, watcher_id=extension_id_for(watcher), tokens=server.tokens)`: the same id
  the app allows as the watcher's origin. browser-profile-choice (Wave C) turns it into a set of ids.

- [ ] **Step 1: Write the tests**

Add to `tests/test_bravelink.py`:

```python
@CHROME
async def test_a_private_window_is_never_listed_in_a_throwaway_chrome(tmp_path):
    from ai_browser import testpages
    from ai_browser.app.bravelink import BraveLink
    from ai_browser.app.tabs import TabWatch
    from ai_browser.cdp import CDP
    from ai_browser.chrome import find_ws_url, launch

    base, _, stop_pages = testpages.serve_host()
    folder = tmp_path / "private-profile"
    process = launch(folder, headless=True, extra_args=("--incognito", base + "privacy.html"))  # its window: private
    link = BraveLink(folder, every=0.1)  # no watcher: the profile used last
    try:
        ws_url = find_ws_url(folder, timeout=20)
        watch = TabWatch(ws_url, "")
        await watch.start()
        cdp = await CDP.connect(ws_url)
        try:
            assert await until(lambda: any(row["url"] == base + "privacy.html" for row in watch.pages()), 10)
            private = next(row for row in watch.pages() if row["url"] == base + "privacy.html")
            regular = (await cdp.send("Target.createTarget", {"url": base + "form.html"}))["targetId"]  # no context
            assert await until(lambda: any(row["target"] == regular for row in watch.pages()), 10)
            context = next(row["context"] for row in watch.pages() if row["target"] == regular)
            assert private["context"] and context and private["context"] != context
            assert await until(lambda: watch.default_context == context)  # never the private window's
            await link.start()
            await link.connect()
            assert link.state == "connected"
            assert await until(lambda: [tab["target"] for tab in link.tabs()] == [regular], 10)
            assert link.scope() == {"profile": "last_used", "elsewhere": 1}
            listed = json.dumps(link.tabs())
            assert private["target"] not in listed and "Privacy" not in listed
        finally:
            await cdp.close()
            await watch.close()
    finally:
        await link.close()
        process.terminate()
        process.wait(timeout=15)
        stop_pages()
```

Add to `tests/test_watcher.py` (it imports `json` already; add `from pathlib import Path` to its imports if it isn't
there):

```python
@CHROME
async def test_the_watchers_profile_is_found_from_its_worker(watcher, tmp_path):
    from ai_browser.app.bravelink import BraveLink

    link = BraveLink(tmp_path / "profile", watcher_id=watcher.app.extension_id, every=0.1)  # the fixture's Chrome
    await link.start()
    try:
        await link.connect()
        assert link.state == "connected"
        assert await watcher.until(lambda: link.agents_context()[1] == "watcher")
        target = (await watcher.cdp.send("Target.createTarget", {"url": watcher.base + "privacy.html"}))["targetId"]
        assert await watcher.until(lambda: any(tab["target"] == target for tab in link.tabs()))
        assert link.scope()["profile"] == "watcher"
    finally:
        await link.close()


def test_the_watcher_never_runs_in_private_windows():
    manifest = json.loads((Path(__file__).parents[1] / "src" / "ai_browser" / "app" / "watcher" / "manifest.json")
                          .read_text(encoding="utf-8"))
    assert manifest.get("incognito", "spanning") == "spanning"  # its worker lives in the regular profile
    assert "debugger" not in manifest["permissions"]
```

Add to `tests/test_app_run.py`:

```python
@pytest.mark.posix_only
@CHROME
async def test_brave_mode_gives_the_link_the_watchers_id(fake_claude, tmp_path, monkeypatch):
    from ai_browser.app import run
    from ai_browser.appbrowser import extension_id_for

    runner, _, _ = fake_claude
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    folder.mkdir(parents=True)  # Brave is installed; its switch is off
    monkeypatch.setenv("AIB_CHROME_DIR", str(folder))
    home, made = tmp_path / "home", []
    real = run.BraveLink

    def recording(*args, **kwargs):
        link = real(*args, **kwargs)
        made.append(link)
        return link

    monkeypatch.setattr(run, "BraveLink", recording)

    async def ready(url, app):
        app.process.kill()

    code = await asyncio.wait_for(run.run_app(home, headless=True, claude=runner, ready=ready, out=lambda line: None,
                                              browser="brave"), 60)
    assert code == 0 and len(made) == 1
    assert made[0].watcher_id == extension_id_for(home / "app" / "watcher") != ""  # the id the app allows
```

- [ ] **Step 2: Run them**

Run: `uv run pytest tests/test_app_run.py::test_brave_mode_gives_the_link_the_watchers_id tests/test_bravelink.py::test_a_private_window_is_never_listed_in_a_throwaway_chrome tests/test_watcher.py::test_the_watchers_profile_is_found_from_its_worker tests/test_watcher.py::test_the_watcher_never_runs_in_private_windows -q -p no:randomly`

Expected:
- `test_brave_mode_gives_the_link_the_watchers_id` FAILS: `made[0].watcher_id == ""` (run.py doesn't pass it);
- `test_a_private_window_is_never_listed_in_a_throwaway_chrome` and `test_the_watchers_profile_is_found_from_its_worker`
  PASS already: they prove Tasks 7 and 8 in a real Chrome, through the relay's connection. If either fails:
  - print `link._watch.pages()`, `link._watch.worker_contexts(<the id>)` and `link._watch.default_context` in the
    failing test to see which read is missing;
  - a page without its context, or a wrong default, is this plan's code (`app/tabs.py`): fix it test-first in Task 7's
    `tests/test_tabwatch.py`, then go on;
  - no service worker at all, or `Target.getBrowserContexts` refused, while Task 8's FakePort tests pass through the
    same relay, is the relay's local client (relay Decision 9 says it sees every target, service workers included,
    with their `browserContextId`, and may read `Target.getBrowserContexts`). `app/cdprelay.py` is not this plan's
    file: stop, write what you found in the ledger, and report it, so it is fixed on `main`, test-first in
    `tests/test_cdprelay.py`, before this branch goes on;
- `test_the_watcher_never_runs_in_private_windows` PASSES: it is a guard.

- [ ] **Step 3: Pass the watcher's id**

In `src/ai_browser/app/run.py`, replace the line that starts `brave = BraveLink(own` (the relay's
`brave = BraveLink(own, tokens=server.tokens)`) with:

```python
            brave = BraveLink(own, watcher_id=extension_id_for(watcher), tokens=server.tokens)  # the watcher's profile
```

`extension_id_for(watcher)` is the same id the app allows as the watcher's origin a few lines above
(`server.allow_origin(f"chrome-extension://{extension_id_for(watcher)}", watcher=True)`).

In `tests/test_watcher.py`, the `watcher` fixture builds a connected BraveLink on the fixture's profile (cdp-relay's
"The watcher fixture"). Give that `BraveLink(...)` call `watcher_id=app.extension_id` too, as run.py now does.

- [ ] **Step 4: Run them, and the watcher's grouping tests**

Run: `uv run pytest tests/test_app_run.py tests/test_bravelink.py tests/test_watcher.py tests/test_watcher_groups.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/run.py tests/test_app_run.py tests/test_bravelink.py tests/test_watcher.py
git commit -m "feat: the app tells BraveLink the watcher's id; a private window is never listed (real Chrome)"
```

---

## Part 2: the spec's step 2 (once brain-delegation is on `main`)

Before Task 10: `git fetch` if needed, then `git merge main` into `watcher-safety`. Resolve conflicts in
`app/server.py` and `tests/test_app_server.py` by keeping both sides' additions: brain-delegation's `tell_confirm`,
`tell_dismiss` and `tell` arguments, and this branch's table, filter and `_role`. Where brain-delegation refuses its
messages from the watcher by origin (built beside Part 1, it may use today's `self._origin_of.get(ws) …
self._watcher_origins` test), keep its handling and drop the origin test: Task 10 puts the same rule in the table.
Note the merge in the ledger.

When brain-delegation reached `main` before Part 1 (the build order above), this merge and Task 10 happen before
Part 1 merges; Part 2 then starts at Task 11, after merging `main` again.

### Task 10: brain-delegation's two messages in the table

**Files:**
- Modify: `src/ai_browser/app/server.py` (`MESSAGE_RULES`; the `from_watcher` flag `_handle` passes for `tell`)
- Test: `tests/test_watcher_rules.py` (`SENDS` and the counts)

**Interfaces:**
- Consumes: brain-delegation's `tell_confirm {id, proposal, task?}` and `tell_dismiss {id, proposal}` (in
  `BRAIN_MESSAGES`, handled in `_brain_command`), and its `from_watcher` flag for `tell`.
- Produces: `MESSAGE_RULES` with 57 rows (22 for the watcher, 50 for the app); `tell`'s `from_watcher` is
  `self._role(ws) == "watcher"`.

- [ ] **Step 1: Write the failing test**

In `tests/test_watcher_rules.py` (when brain-delegation's merge already wrote these into `SENDS` and the counts, as the
build order asks, check they read as below and go on to Step 2):
1. Change the comment above `SENDS` to "The table of watcher-safety's spec, plus cdp-relay's and brain-delegation's
   rows: (app, watcher)."
2. Add to `SENDS`, after the `"brain_ask"` … row:

```python
    "tell_confirm": (True, False), "tell_dismiss": (True, False),  # brain-delegation: Start/Send and Cancel on a card
```

3. In `test_the_message_table_has_exactly_the_written_down_types`, change `55` to `57` and `48` to `50`.

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_watcher_rules.py -q -p no:randomly`

Expected: `test_the_message_table_has_exactly_the_written_down_types` FAILS (`MESSAGE_RULES` lacks the two rows), and
so do the two new parametrized cases: `may_send("app", {"type": "tell_confirm"})` is `False`. If brain-delegation
refused its messages from the watcher with an origin test of its own, `test_rights_go_by_role_through_the_table` and
`test_only_the_role_reads_the_watchers_origins` fail too, naming the method that holds it. If brain-delegation's
merge already added the rows (Part 1 reached `main` first), these PASS: note that in the ledger and do only Step 3's
points 2 and 3.

- [ ] **Step 3: The rows, and the flag by role**

In `src/ai_browser/app/server.py`:
1. In `MESSAGE_RULES`, after the `"brain_ask": APP_ONLY, ...` row, add:

```python
    "tell_confirm": APP_ONLY, "tell_dismiss": APP_ONLY,  # brain-delegation: a card runs only from our own pages
```

2. Find where `_handle` computes the `from_watcher` flag it passes towards `brain.tell` (brain-delegation's spec:
   "`_brain_command` gets that flag as a parameter from `_handle`, which has the socket"). Make that expression
   `self._role(ws) == "watcher"`. If brain-delegation added a helper of its own for the same test, delete it and use
   `_role`.
3. Delete any origin test brain-delegation added for `tell_confirm` or `tell_dismiss`: the table drops them from the
   watcher. `uv run pytest tests/test_watcher_rules.py::test_rights_go_by_role_through_the_table tests/test_watcher_rules.py::test_only_the_role_reads_the_watchers_origins -q -p no:randomly`
   must pass: nothing but `_role` (and the four places that set up origins) reads `_watcher_origins`.

- [ ] **Step 4: Run them, and brain-delegation's server and service tests**

Run: `uv run pytest tests/test_watcher_rules.py tests/test_app_server.py tests/test_brain_service.py -q -p no:randomly`

Expected: PASS, including brain-delegation's test that the watcher's `tell_confirm`, `tell_dismiss` and a typed yes
run no card, and that AI Home's `tell_confirm` starts exactly one agent.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/server.py tests/test_watcher_rules.py
git commit -m "feat: brain-delegation's tell_confirm and tell_dismiss are app-only rows in MESSAGE_RULES"
```

### Task 11: AI Home's tab list says what it doesn't show

**Files:**
- Modify: `src/ai_browser/app/extension/tablist.js` (`render`, a new `scopeTexts`)
- Modify: `src/ai_browser/app/extension/home.js` (`tabScope`; the `snapshot`, `tabs` and `browser` cases;
  `renderTabs`)
- Test: `tests/test_home.py`

**Interfaces:**
- Consumes: Task 6's `tab_scope` in the snapshot and in each `tabs` message; Task 6's `FakeBrave.set_scope`;
  brain-delegation's `tablist.js` and `home.js` as merged.
- Produces:
  - `scopeTexts(scope) -> { source: string, elsewhere: string }` (exported from `tablist.js`; `""` for no line);
  - `render(tabs, { brave, ownerOf, scope })`: after the rows, up to two muted lines, `p.scope-source` and
    `p.elsewhere`, set with `textContent`, updated in place and removed when not needed; with `scope` set and no rows,
    the empty text reads "No web pages open in this profile.";
  - `home.js` passes `scope` only while Brave is connected, and forgets it when Brave's state changes, until the next
    list (Review Focus 1).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_home.py`, after `test_the_tab_list_marks_owners_and_hands_tabs_over`:

```python
LAST_USED = ("Showing the Brave profile you used last. With the watcher loaded, this list stays on the watcher's "
             "profile.")
NO_PROFILE = "Your tabs aren't listed: AI Browser can't tell which Brave profile is yours yet."


@CHROME
async def test_the_tab_list_counts_what_it_doesnt_show(home):
    from fake_brave import FakeBrave

    js, _, stack = home
    brave = FakeBrave([{"target": "U1", "url": "https://mail.example/", "title": "Mail"}])
    brave.set_scope("watcher", 3)
    stack["server"].attach_brave(brave)
    source = "document.querySelector('#tabs p.scope-source')?.textContent ?? null"
    count = "document.querySelector('#tabs p.elsewhere')?.textContent ?? null"
    empty = "document.querySelector('#tabs .empty')?.textContent ?? null"

    async def shows(expression, text):
        return await until(js, f"({expression}) === {json.dumps(text)}")

    assert await shows(count, "3 more tabs in other profiles or private windows: not shown here.")
    assert await js(source) is None
    brave.set_scope("watcher", 1)
    assert await shows(count, "1 more tab in other profiles or private windows: not shown here.")
    brave.set_scope("last_used", 0)
    assert await shows(source, LAST_USED)
    assert await js(count) is None  # no line when the count is 0
    brave.set_scope("none", 2)
    assert await shows(source, NO_PROFILE)
    assert await shows(count, "2 more tabs in other profiles or private windows: not shown here.")
    brave.set_scope("watcher", 0)
    assert await shows(source, None)
    assert await js(count) is None
    brave.pages = []
    brave.changed()
    assert await shows(empty, "No web pages open in this profile.")
    brave.set_scope("none", 4)  # Review Focus 1: while Brave isn't connected, the list claims nothing about profiles
    brave.set_state("ready")
    assert await shows(empty, "No web pages open in your browser.")
    assert await js(source) is None and await js(count) is None
    brave.set_state("connected")  # connected again: the scope sent before is stale until the new connection's list
    assert await until(js, "document.getElementById('browser-card').dataset.state === 'connected'")
    assert await js(source) is None and await js(count) is None
    assert await js(empty) == "No web pages open in your browser."
    brave.changed()  # the new connection's first list brings its own scope
    assert await shows(source, NO_PROFILE)
    assert await shows(count, "4 more tabs in other profiles or private windows: not shown here.")
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_home.py::test_the_tab_list_counts_what_it_doesnt_show -q -p no:randomly`

Expected: FAIL: `p.elsewhere` never appears (`until` gives `False`).

- [ ] **Step 3: The two lines**

In `src/ai_browser/app/extension/tablist.js`:
1. Add after `chipText` (keep brain-delegation's version of `chipText` as it is):

```js
// The tab list's scope in brave mode (the server's tab_scope): which profile the rows come from, and how many of the
// user's tabs it leaves out. Only a number reaches this page: never a title, an address or an id of those tabs.
const SCOPE_SOURCE = {
  last_used: "Showing the Brave profile you used last. With the watcher loaded, this list stays on the watcher's "
    + "profile.",
  none: "Your tabs aren't listed: AI Browser can't tell which Brave profile is yours yet.",
};

export function scopeTexts(scope) {
  if (!scope) return { source: "", elsewhere: "" };
  const count = Number(scope.elsewhere) || 0;
  return {
    source: SCOPE_SOURCE[scope.profile] || "",
    elsewhere: count > 0
      ? `${count} more ${count === 1 ? "tab" : "tabs"} in other profiles or private windows: not shown here.` : "",
  };
}
```

2. In `mountTabList`, add before `function render(`:

```js
  function line(className, text) { // a muted line after the rows, updated in place, gone when not needed
    let node = root.querySelector(`:scope > p.${className}`);
    if (!text) {
      node?.remove();
      return;
    }
    if (!node) node = el("p", `${className} muted`);
    setText(node, text);
    root.append(node); // after the rows and the empty text, in the order of the calls
  }
```

3. `render`'s options gain `scope = null`: `function render(tabs, { brave, ownerOf })` becomes
   `function render(tabs, { brave, ownerOf, scope = null })` (if brain-delegation added options to it, keep them and
   add `scope = null`).
4. Replace its empty-text block:

```js
    if (!tabs.length) {
      root.append(el("p", "empty", brave ? "No web pages open in your browser." : "No tabs open besides AI Home."));
    }
```

   with:

```js
    if (!tabs.length) {
      root.append(el("p", "empty", !brave ? "No tabs open besides AI Home."
        : scope ? "No web pages open in this profile." : "No web pages open in your browser."));
    }
    const texts = scopeTexts(brave ? scope : null);
    line("scope-source", texts.source);
    line("elsewhere", texts.elsewhere);
```

In `src/ai_browser/app/extension/home.js`:
1. After `let tabs = [];`, add `let tabScope = null; // brave mode: {profile, elsewhere} from the app, never a title`.
2. In the `case "snapshot":` block, after `tabs = message.tabs || [];`, add `tabScope = message.tab_scope || null;`.
3. In the `case "tabs":` block, after `tabs = message.tabs || [];`, add `tabScope = message.tab_scope || null;`.
4. In `renderTabs`, add to the options passed to `tabList.render(tabs, {`:

```js
    scope: browser?.kind === "brave" && browser.state === "connected" ? tabScope : null, // only while connected
```

5. In the `case "browser":` block, before its line `browser = { kind: message.kind, name: message.name, state:
   message.state, groups: message.groups };`, add:

```js
      // A new state forgets the scope: while not connected the app sends {profile: "none"}, which must not show in
      // the moment after Brave connects again. The new connection's first list brings its own.
      if (message.state !== browser?.state) tabScope = null;
```

The `case "browser":` block already calls `renderTabs()`, so the lines follow Brave's state. The server sends the
`browser` message for a new state before the list of the new connection (BraveLink sets its state, then starts its
tab watch and calls back with the list), so the list's scope is the one that stays.

- [ ] **Step 4: Run it, and AI Home's file**

Run: `uv run pytest tests/test_home.py -q -p no:randomly`

Expected: PASS, including `test_the_tab_list_marks_owners_and_hands_tabs_over` and brain-delegation's tests.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/extension/tablist.js src/ai_browser/app/extension/home.js tests/test_home.py
git commit -m "feat: AI Home's tab list names its profile and counts other profiles and private windows"
```

### Task 12: The README; the whole suite and the bench

**Files:**
- Modify: `README.md` (three places, found by their text)
- Test: `tests/test_watcher_rules.py`

**Interfaces:**
- Consumes: the README as merged (the relay's switch section and brain-delegation's lines stay as they are).
- Produces: the README says what AI Home lists, where Always allow is, and what AI Home shows of the user's other
  tabs.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_watcher_rules.py` (add `from pathlib import Path` to its imports):

```python
def test_the_readme_says_what_ai_home_lists_and_where_always_allow_is():
    text = " ".join((Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8").split())
    assert ("**Tabs:** the web tabs of the Brave profile the watcher is in (without the watcher, the profile you used "
            "last), each marked with whose it is") in text
    assert "Other profiles and private windows are only counted, never listed." in text
    assert ("The watcher's Brain page in Brave shows them with **Allow once** and **Deny** only, because Always "
            "allow is kept for AI Home's Tools.") in text
    assert "and the watcher's Brain page all show the tool" not in text
    assert ("AI Home shows the ones in the agents' profile (other profiles and private windows only as a count)"
            in text)
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_watcher_rules.py::test_the_readme_says_what_ai_home_lists_and_where_always_allow_is -q -p no:randomly`

Expected: FAIL: the README still says "**Tabs:** your Brave's web tabs".

- [ ] **Step 3: Write the README**

1. In the "AI Browser" section, replace the line
   `- **Tabs:** your Brave's web tabs, each marked with whose it is: an agent's, Claude Code's, the Brain's, or yours.`
   with the two lines below. Its three sub-bullets (A click…, **Hand over**…, **Take back**…) stay.

```markdown
- **Tabs:** the web tabs of the Brave profile the watcher is in (without the watcher, the profile you used last),
  each marked with whose it is: an agent's, Claude Code's, the Brain's, or yours. Other profiles and private windows
  are only counted, never listed.
```

2. Under **Asking first:**, replace:

```markdown
- AI Home's agent row, the chat beside its tab, and the watcher's Brain page all show the tool and its exact input,
  with **Allow once**, **Always allow** and **Deny**. Brave also shows a notification (Review / Deny).
```

   with:

```markdown
- AI Home's agent row, Mission Control and the chat beside its tab show the tool and its exact input, with **Allow
  once**, **Always allow** and **Deny**. The watcher's Brain page in Brave shows them with **Allow once** and **Deny**
  only, because Always allow is kept for AI Home's Tools. Brave also shows a notification (Review / Deny).
```

3. Under "What happens in your Brave", in the bullet that starts `- **Your other tabs:** never read, listed to an
   agent or touched.`, replace `AI Home shows them, and **Hand over** gives one to` with
   `AI Home shows the ones in the agents' profile (other profiles and private windows only as a count), and **Hand
   over** gives one to`, and rewrap the bullet at 120 columns.

- [ ] **Step 4: Run the docs test, then the whole suite and the bench**

Run: `uv run pytest tests/test_watcher_rules.py -q -p no:randomly`

Expected: PASS.

Run: `uv run pytest -q -p no:randomly`

Expected: PASS. Docker tests skip when Docker or the image is missing; the Chrome tests need Google Chrome. Write the
tail of the output to the ledger. If anything fails, fix it test-first in the task that owns the code, then run the
whole suite again.

Run: `uv run ai-browser bench`

Expected: every row PASS. This plan doesn't touch the engine's reading or acting; write the table to the ledger. The
bench needs Docker and the sandbox image: if Docker isn't running, say so in the ledger and the report, and don't count
it as a failure of this plan.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_watcher_rules.py
git commit -m "docs: AI Home lists one Brave profile; the watcher's tool card has no Always allow"
```

Then:
1. **The final review.** A fresh reviewer checks the branch against the Global Constraints and the Review Focus, and
   checks the two tables against the spec's ("the table of what pages may send", "what the watcher receives") with
   the relay's and brain-delegation's rows. One fix pass follows, test-first; minor findings go to the ledger.
2. **A check by the user, in their own Brave, only when they say so** (no agent connects to the user's Brave):
   1. With the watcher loaded and a second Brave profile and a private window open, each with a web tab: AI Home's
      Tabs list shows only the watcher's profile's tabs, and one line counts the others.
   2. Give an agent a task that needs a tool: the watcher's Brain page card offers **Allow once** and **Deny**, with
      "Always allow is in AI Home's Tools."; AI Home's card still has all three.
   3. On a local bot-check page, the Brave notification's **Show me** brings the agent's tab forward, and **Continue**
      lets it carry on.
3. **Restart the user's `ai-browser app`** so the new pages load, only when the user says so. The watcher reloads
   itself when its files change.
