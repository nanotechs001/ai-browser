# Browser and Profile Choice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The user picks, once, the browser and the profile where agents browse. From then on every new agent's tabs
are opened by the watcher copy in that profile, grouped and in the background, whichever profile the user last clicked
in; without that copy, the tab opens in the profile used last and the agent says so.

**Architecture:**
- **Engine (Python, one per agent or Claude Code session):**
  - `places.py` (new) resolves a `Place` (browser id, its folder of profiles, a profile folder) once per process:
    `AIB_CHROME_DIR` (+ `AIB_CHROME_PROFILE`), else `<home>/settings.json`'s `agents_browser`, else the place chosen
    for the user. `chrome.own_browser_dir()` follows it and no longer follows "whose switch answers";
  - `grouping.Placer.open()` asks the app (`POST /agent-open`) for a tab the watcher opened; with `opened: true` the
    `Browser` attaches to that target and sends no `Target.createTarget`. Otherwise it creates the tab as today, reads
    where it landed (`Target.getTargetInfo`) and adds one note to the result;
  - a session says hello with its place; the app answers with the same place (the relay) or `null` (direct).
- **App (Python):**
  - `app/links.py` (new): `InstanceLinks`, one `InstanceLink` (today's `BraveLink`, renamed) per browser in use, each
    with its own relay upstream; it connects only after something the user did, and closes a browser nobody uses;
  - `app/watchers.py` (new): `WatcherCopies` (one watcher folder per profile, at `<home>/app/watchers/<slug>`) and
    `Watchers` (the live copy connections, each with its own `GroupKeeper`, placed by their profiles' files and their
    workers' contexts);
  - `app/where.py` (new): the Settings view (`browsers`), `place_set`'s checks, and the labels for the app's own pages;
  - `app/groups.py`: `GroupKeeper.open()` sends `open_tab` and waits for `opened_tab`;
  - `app/cdprelay.py`: `Relay.assign` (a tab the watcher opened becomes that agent's own) and `Relay.close_marker`;
  - `app/server.py`: `/agent-open`; `/agent-status` says whether the place's copy can open tabs; `/agent-hello`
    records a session's place; `/cdp` binds each client to its place's relay; the Brain's messages go to the primary
    copy only; `browsers`, `place_set`, `watcher_copy` and `restart_in` from the app's own pages;
  - `app/agents.py`: each agent keeps the place it was created with; **Restart in**.
- **Watcher (MV3, in the user's browser):** `groups.js` gains `validOpen` and `openTab`
  (`chrome.tabs.create({active: false})`, or `chrome.windows.create({focused: false})` for a profile with no window);
  `worker.js` answers `open_tab` and says `open: true` in `watcher_caps`.
- **Pages (`app/ui/`):** `places.js` (new) draws Settings → **Where agents browse** and AI Home's chip; AI Home and
  Mission Control show a place chip and **Restart in**; the tab list labels rows owned elsewhere and lists Give to per
  browser.

**Tech Stack:** Python 3.12 (asyncio, Starlette and uvicorn, websockets, `urllib` for the engine-to-app calls); MV3
extension and page scripts in plain JS (ES modules); pytest with throwaway headless Chromes, the `watcher` fixture,
wave 2A's `FakePort`/`FakeRelay`, `FakeBrave`, the fake `claude`, and visible two-profile throwaway Chromes for the
`headful` tests (run only with `AIB_HEADFUL=1`).

**Spec:** `docs/superpowers/specs/2026-10-03-browser-profile-choice-design.md`

**Branch and order:** wave C. Create the branch `browser-profile-choice` from `main` once these have merged, in this
order (the user's new build order, which replaces the spec's "wave 4 after waves 1-3"):
1. the cdp-relay (`2026-10-03-cdp-relay-design.md`), built first. It used today's structures where its spec expected
   wave 1: `BRAVE_MESSAGES` and the watcher-origin check, and `int(id[1:])` for agent numbers;
2. wave A, in parallel: brain-delegation, watcher-safety (which folded the relay's message rows into its
   `MESSAGE_RULES` table) and browser-detection (brain-delegation's `Agent.number` is what the relay's client list
   now uses);
3. wave B: app-window.

Wave D (side-chat) builds on this branch and calls its names (`place_of`, `Watchers.connections()`, `WatcherConn`,
`InstanceLink.targets_showing`/`context_of`, `InstanceLinks.link_for`, `Agent.place`, the tab ids in `open_tab`'s
answers). Keep them as named here.

**Line numbers** in the spec are at HEAD `946d5f0`; every earlier wave moved them. Every edit below is anchored by the
text or the name it changes, never by a line number. Read the merged code before each task that touches it.

## Seams: the earlier waves' names this plan relies on

The rule of the seven specs' coordination section applies: when the merged code spells one of these differently, the
merged code's name wins, and the behaviour is what the tests check. Each task's **Interfaces** block repeats the ones
it uses.

- **cdp-relay (merged first):**
  - `app/cdprelay.py`: `Relay(folder, tokens, allow_wait, every)` with `state`, `name`, `port`, `upstream_opens`,
    `open(why, identity)`, `serve(ws)`, `local()`, `grants(identity, target)`, `visible(identity, target)`,
    `own_targets(identity)`, `cut(identity, target)`, `disconnect(identity)`, `forget(identity, close_tabs=False)`,
    `clients()`, `on_state`, `on_change`, `on_grant`, the hooks `handed` and `may_open`; inside, the target cache
    (`targets`), the grant table, the clients (each with a discovery flag and the record of which
    `Target.targetCreated` it got), the cut-off set, and the relay's own upstream commands (pending `None`);
    `Tokens` (`mint`, `check`, `who`, `revoke`), `TOKEN_HEADER`;
  - `BraveLink(folder, ..., tokens=None)` with `self.relay`, `connect(why="connect", identity="")`, `start()`,
    `close()`; `TabWatch(..., cdp=None)`;
  - `AppServer.tokens`, `token_for(agent_id)`, `connect_brave(why, identity="")`, the `/cdp` route, the relay wiring
    in `attach_brave`, `browser_clients` and `browser_disconnect`, `/agent-hello` answering `{"cdp_token"}` (410 for a
    cut-off session); `AgentManager.mint_token`, `own_tabs`, `working(agent_id)`;
  - engine: `_route()`, `RELAY_WAIT`, `APP_GONE`, `APP_SILENT`, `CUT_OFF_SESSION`, the status line's start ("browser:
    your Brave, through AI Browser's connection" / "… not through AI Browser: …"), `AgentLink.cdp`,
    `AgentLink.browser_dir`, `hello()` returning `dict | None`, `CDP.connect(url, open_timeout, headers)`;
  - `write_link(home, url, token, cdp, browser_dir)`; tests: `FakePort` and `FakeRelay` in `tests/fake_brave.py`,
    `relay_client(...)` in `tests/test_cdprelay.py`.
- **brain-delegation (wave A):** `Agent.number` (`int(id[1:])`), `agentLabel(agent)` and `el` in `ui/chat.js`,
  `mountYourTabs(root, { send, agentId })` in `ui/tablist.js` with `render(tabs, { brave, connected, name })`,
  Mission Control's drawer with **Your tabs**.
- **watcher-safety (wave A):** `Rule`, `MESSAGE_RULES`, `may_send(role, message)`, `WATCHER_RECEIVES`,
  `WATCHER_AGENT_FIELDS`, `for_watcher(message)`, `_role(ws)`, `check_show`; `TabWatch.pages()` (rows with
  `context`), `worker_contexts(extension_id)`, `default_context`; `BraveLink(folder, watcher_id="", ...)`,
  `agents_context()`, `scope()`, `_changed()` (calls back only when the rows or the scope change), its remembered
  worker contexts; the `tabs` message's `tab_scope`; `FakePort`'s page `context`, service workers, `set_default`,
  `destroy`; `FakeBrave.scope()`; `tests/test_watcher_rules.py` and its two copies of the tables; `tablist.js`'s
  `render(tabs, { brave, ownerOf, scope })` with `p.scope-source` and `p.elsewhere`.
- **browser-detection (wave A):** `platforms.KNOWN_BROWSERS` (`BrowserFacts`: `id`, `name`, `agents`, `inspect`, …),
  `platforms.user_data_dir`, `platforms.open_shared`; `browsers.Installed` (`facts`, `binary`, `bundle`, `version`,
  `data_dir`; `id`, `name`, `agents`, `inspect_address`), `browsers.Profile`, `browsers.WatcherPlace`,
  `browsers.installed()`, `os_default()`, `by_id()`, `data_dir()`, `for_data_dir()`, `all_data_dirs()`,
  `plain_folder()`, `profiles()`, `watcher_places()`, `state()`, `detect(watchers)`, `public(found, connected)`.
- **app-window (wave B):** `app/ui/` (pages served by the app server; `nav.js`'s `openWindow(path, name, width,
  height)`), `ui/settings.html` and `ui/settings.js` (one section, **App window**), `ui/setup.html`;
  `src/ai_browser/settings.py` (`read_settings(home)`, `write_setting(home, key, value)`);
  `src/ai_browser/extension_id.py` (`extension_path`, `extension_id_for`); `AppServer.allow_watcher(origin)`,
  `window_info`, `settings_set`, `open_url` with `platforms.open_url(url, browser=None)`; `run_app(home, model,
  claude, ready, stop, out, browser, window_browser, launcher)`; `brain/watcher.py`'s `SHARED_SOURCE = APP / "ui"`;
  `BraveLink(..., app_origin="")`; `browser.kind` is always `"brave"`; tests: `tests/ui_socket.py`
  (`ui_socket(server, url)`), `tests/pipe_chrome.py` (the pipe launcher moved from `appbrowser.py`, with `_Pipe` and
  `_spawn_posix`), `tests/fake_window.py` (`FakeWindow(cdp)`), the rebuilt `stack` and `home` fixtures (`js, stack =
  home`) and `click_as_user(js_session, selector)`, the conftest fixture parts that keep detection off this machine's
  files.

## Plan decisions (where the spec leaves a choice, or this plan adds a small piece)

1. **`/agent-status` also answers `"why"`** (`""`, `no_watcher`, `asleep`, `shared`, `unknown`, `not_connected`,
   `refused`) when `open` is false. Without it the status line couldn't give the spec's `asleep` and `shared` reasons
   before a tab is opened (the spec's Texts list them).
2. **`Placement.new_window`** carries the watcher's `new_window`, for the note.
3. **`Agent.where: Place | None`** (never public) beside the public `Agent.place` dict: routing needs the folder, and
   the folder never goes to a page.
4. **`app/where.py` is a class `Where(copies)`** whose methods carry the spec's names (`browsers_view`,
   `check_place_set`, `describe`); it keeps the last `detect()` and a names cache, so the browser card never reads
   `Local State` per broadcast. Wave D calls `server.where.describe(place)`.
5. **Test seams:** `Watchers.find_places` (a callable, default: the browsers' files) and
   `AppServer.allow_watcher(origin, copy="primary")`.
6. **Small helpers** the spec implies: `InstanceLink.lists(target)`, `InstanceLinks.located(target)`,
   `InstanceLinks.at(instance)`, `Relay.note_marker(marker)` (the markers `close_marker` accepts),
   `GroupKeeper.can_open()`.
7. **`doctor`'s everyday line** says "(set by AIB_CHROME_DIR)" when the environment chose the place.
8. **A `note` chat event** draws "Restarted as …" in the old agent's chat view (`chat.js`), recorded with
   `AgentManager._record`, never queued for Claude.
9. **The browser card** gets one more line for a copy that just connected and isn't placed yet ("Checking which Brave
   profile the watcher is in…"), and the `browser` message carries `extra_watcher` for the spec's "Two AI Browser
   watchers" line.
10. **A `""` place** (an `AIB_CHROME_DIR` no known browser owns) is held by the app only as its own current place,
    from its own environment (tests' throwaway Chrome); never from a session's hello or a page.

## Global Constraints

Copied from the spec and the user's rules. Every task's requirements include these.

**The browser's own signs stay:**
- "nothing auto-clicks, answers, suppresses or hides "Allow remote debugging?" or the automation bar, in any
  browser";
- "a switch to another browser asks once, right after the user's click";
- "with two browsers connected, each shows its own bar, and Settings says so."

**Connections only after the user acts:** "the app connects to a browser only at start (the current place), on
Connect or Try again, on a switch click, on an agent's turn (its own place's browser), or on a session's first
command after its task (its own place's browser)"; "it never connects to a browser that is neither the current place
nor the place of a live agent or session"; "after Deny nothing retries by itself"; "detection reads files and makes TCP
checks only".

**No spoofing, no tricks:** "`open_tab` uses `chrome.tabs.create({active: false})` and, for a profile with no window,
`chrome.windows.create({focused: false})`, both documented"; "no focus tricks, no faked gestures, no
`--profile-directory` launch, no `debugger` permission"; "nothing changes how any browser presents itself." No bot
check is bypassed or solved: they stay handed to the user.

**The watcher's new power is one blank tab:** "`open_tab` opens only `about:blank#aib-<16 hex>`, built by the
watcher"; "a message with an address, a bad marker, colour or title is refused"; "the watcher never navigates or
reads that tab"; "it never uses a private window"; "it acts only on messages over its own origin and token".

**Only the AI's tabs:** "the app, not the engine, finds the new tab by its secret marker and checks its profile before
`Relay.assign` gives it to that agent alone"; "a marker is used once"; agents still never see the user's tabs.

**Hand-over and take-back are clicks only:** "**Give to** lists only agents in the tab's browser"; "the Brain, voice and
the watcher can't send `place_set`, `watcher_copy` or `restart_in`"; "the Brain only proposes Start and Send cards";
"**Restart in** is a click on a button that names the place."

**Pages never choose a folder:** "`place_set` and `watcher_copy` carry a browser id and a profile folder. The server
finds the browser's folder in `browsers.installed()` and checks the profile against its `Local State`. A path from a
page is never used."

**Text is text:** "profile names, colours, labels, folder paths and counts are set with `textContent`"; "a hostile
profile name stays text (tested)"; "page and message text stays data, never instructions".

**Names stay on this computer (Decision 16):**
- "Profile names, colours and emails never appear in a tool result, an agent's prompt, the Brain's state, the
  terminal's output, or anything sent to Claude. Emails are never read into the app at all."
- tool results and status lines say "the chosen profile" or "the profile the user used last", never a name or a
  folder;
- the terminal (`ai-browser app`, `doctor`) names the browser and the profile folder ("Brave · profile folder
  Profile 1"), never the display name;
- `WATCHER_AGENT_FIELDS` doesn't gain `place`.

**No passwords:** "passwords are never typed: the agent asks the user to log in in that tab." **Downloads** still need
the user's OK (⚠ and the cancel net), now through the upstream of the agent's own browser.

**Private windows** "are never opened into or listed"; they show only inside wave 1B's number, "other profiles or
private windows".

**Chromium's files are internals:** "every read of `Local State`, `Secure Preferences` or `Preferences` fails safe: no
profiles, or "unknown", never a crash and never a guess."

**Exact values:** `OPEN_WAIT = 2.5`; `ENGINE_OPEN_WAIT = 3.0`; the files are read again 2 s, 5 s and 15 s after a copy
connects while it is unknown; the settings key is `agents_browser`; `settings.json` and every copy's `config.json` are
0600; a copy's folder is `<home>/app/watchers/<slug>`, the slug being the browser id and the profile folder,
lower-cased, anything outside `[a-z0-9]` turned into "-", at most 60 characters; the primary copy stays at
`<home>/app/watcher`; `open_tab`'s `title` is a string of at most 40 characters and its `color` one of the nine.

**Coordination rules:** text files name `encoding="utf-8"`; a process check uses `platforms.pid_alive` through the
engine's `_alive`; new text says "this computer", never "this Mac"; no browser folder or install path is spelled
outside `platforms.py` (folders come from `platforms`/`browsers`).

**House rules:**
- Run tests one file or test at a time: `uv run pytest <path>::<test> -q -p no:randomly`.
- The whole suite runs only in the last task.
- Never connect to the user's own Brave or Chrome, and never touch a running `ai-browser app`. The `headful` tests
  open visible **throwaway** Chromes: only the main session runs them, with `AIB_HEADFUL=1`, after the user says yes.

## Review Focus

The five failures most likely to hit a user that the spec implies but none of its tests cover. Each has a test in the
task that owns the code.
1. **Two agents open tabs at the same moment in one profile.** Their `open_tab` answers come back out of order. Each
   agent must get the target at its own marker, assigned to it and nobody else. Test: Task 19.
2. **The watcher reloads itself (a new build) while an `open_tab` waits.** The wait must end at once with
   `no_watcher`, so the engine falls back in milliseconds, not after 2.5 s. Test: Task 10.
3. **The user switches to another browser while the old one still shows "Allow remote debugging?", and no agent works
   there.** The old attempt is dropped with its link; it must never turn into a connection later. Test: Task 13.
4. **The user closes the watcher's new tab before the engine attaches.** The call fails with a plain sentence, and no
   second tab is created in another profile. Test: Task 6.
5. **A copy's folder the user deleted, or a stray file or oddly named folder under `<home>/app/watchers/`.** Start-up
   carries on; a stray never gets an origin; a deleted copy's profile simply reads "Needs the watcher". Test: Task 11.

## File map

**New:**
- `src/ai_browser/places.py`: `Place`, the settings key, `resolve`, `place_env`.
- `src/ai_browser/app/links.py`: `InstanceLinks`.
- `src/ai_browser/app/watchers.py`: `slug`, `WatcherCopies`, `WatcherConn`, `Watchers`.
- `src/ai_browser/app/where.py`: `Where` (the `browsers` view, `check_place_set`, `describe`).
- `src/ai_browser/app/ui/places.js`: Settings' section and AI Home's chip.
- **Tests:** `tests/test_places.py`, `tests/test_watcher_copies.py`, `tests/test_links.py`, `tests/test_where.py`,
  `tests/test_profile_facts.py` (headful), `tests/test_profiles_headful.py` (headful); helpers
  `tests/places_rig.py`, `tests/profile_rig.py`, `tests/fake_cdp.py`, `tests/two_profiles.py`.

**Changed:**
- **Engine:** `chrome.py`, `agentlink.py`, `grouping.py`, `browser.py`, `engine.py`, `cli.py` (`doctor`).
- **App:** `app/bravelink.py` (`InstanceLink`), `app/groups.py`, `app/cdprelay.py`, `app/agents.py`,
  `app/bridge.py`, `app/server.py`, `app/run.py`, `brain/watcher.py`.
- **Watcher:** `app/watcher/groups.js`, `app/watcher/worker.js`.
- **Pages:** `app/ui/settings.html`, `settings.js`, `home.html`,
  `home.js`, `home.css`, `tablist.js`, `mission.js`, `mission.css`, `chat.js`, `setup.html`.
- **Docs and config:** `README.md`, `pyproject.toml` (the `headful` marker).
- **Tests:** `tests/conftest.py`, `tests/fake_brave.py`, `tests/test_chrome.py`, `tests/test_grouping.py`,
  `tests/test_groups.py`, `tests/test_engine.py`, `tests/test_bridge.py`, `tests/test_cdprelay.py`,
  `tests/test_bravelink.py`, `tests/test_agents.py`, `tests/test_brain_talk.py`, `tests/test_app_server.py`,
  `tests/test_watcher_rules.py`, `tests/test_watcher.py` (the fixture), `tests/test_watcher_groups.py`,
  `tests/test_app_run.py`, `tests/test_cli.py`, `tests/test_home.py`, `tests/test_mission.py`.

The ledger is `.superpowers/sdd/2026-10-03-browser-profile-choice/progress.md` (git-ignored). Note in it each task's
result, the five facts of Task 1, and any by-hand finding.

---

### Task 1: The `headful` marker, a two-profile throwaway Chrome, and the five facts

The spec's first task: five facts, measured in visible throwaway browsers, each becoming a test or a note in the code.
A subagent can't open visible windows on the user's screen: it writes the tests, sees them skip, and the main session
runs them once with the user's OK.

**Files:**
- Modify: `pyproject.toml` (`[tool.pytest.ini_options]` `markers`)
- Modify: `tests/conftest.py` (`headful_skip`, used in `pytest_collection_modifyitems`)
- Create: `tests/two_profiles.py`
- Test: `tests/test_profile_facts.py` (new)

**Interfaces:**
- Consumes: wave B's `tests/pipe_chrome.py` (`_spawn_posix(binary, args, pipe) -> (process, pipe)`, the pipe's
  `call(method, params)` and `close()`); `tests/test_home.py`'s `evaluate(cdp, session, expression)` and `until`;
  `tests/test_watcher.py`'s `start_server(home, agents, brain)`; wave B's `AppServer.allow_watcher(origin)`.
- Produces:
  - `conftest.HEADFUL_ONLY` and `conftest.headful_skip(item, env) -> str | None`;
  - the `headful` marker: such tests skip unless `AIB_HEADFUL=1`;
  - `tests/two_profiles.py`: `MARKER`, `probe_extension(folder) -> Path`, `TwoProfiles` (`folder`, `ws_url`,
    `load(extension) -> str`, `open_profile(profile)`, `close()`), `launch_two_profiles(folder, first="Profile 2")`,
    `page_contexts(cdp) -> dict[str, tuple[str, str]]`, `worker(cdp, extension_id) -> (session, context)`,
    `page_outside(cdp, context) -> str`, `in_worker(cdp, session, expression)`;
  - in the ledger: facts 1-5, which Tasks 14, 15 and 26 read (`REREAD_AFTER`, `where.WINDOW_FRONT_NOTE`).

- [ ] **Step 1: Write the failing tests**

`tests/test_profile_facts.py`:

```python
"""Five facts about watcher copies in two profiles, measured in a visible throwaway Chrome (the spec's "First task").
The facts run only with AIB_HEADFUL=1 (the main session, with the user's OK); the first two tests are plain: they pin
the rule that keeps visible windows out of ordinary runs."""

import asyncio
import json
import time

import pytest

from ai_browser.cdp import CDP
from ai_browser.chrome import chrome_binary

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


def test_headful_tests_run_only_when_asked():
    from types import SimpleNamespace

    from conftest import HEADFUL_ONLY, headful_skip

    marked, plain = SimpleNamespace(keywords={"headful": True}), SimpleNamespace(keywords={})
    assert headful_skip(marked, {}) == HEADFUL_ONLY
    assert headful_skip(marked, {"AIB_HEADFUL": "0"}) == HEADFUL_ONLY
    assert headful_skip(marked, {"AIB_HEADFUL": "1"}) is None
    assert headful_skip(plain, {}) is None


def test_the_headful_marker_is_registered(pytestconfig):
    assert any(line.startswith("headful:") for line in pytestconfig.getini("markers"))


def _recorded(prefs, extension_id) -> bool:
    try:
        return extension_id in json.loads(prefs.read_text(encoding="utf-8"))["extensions"]["settings"]
    except (OSError, ValueError, KeyError, TypeError):
        return False


@pytest.mark.headful
@pytest.mark.posix_only
@CHROME
async def test_fact_1_a_window_for_a_profile_with_none_opens_behind(tmp_path):
    from test_home import evaluate
    from two_profiles import MARKER, launch_two_profiles, page_contexts, page_outside, probe_extension, worker

    two = launch_two_profiles(tmp_path / "browser")
    cdp = None
    try:
        probe = two.load(probe_extension(tmp_path / "probe-p2"))  # into Profile 2, the only profile open
        cdp = await CDP.connect(two.ws_url)
        session, p2 = await worker(cdp, probe)
        two.open_profile("Default")  # the user's window, in the other profile, in front
        user = await page_outside(cdp, p2)
        user_session = (await cdp.send("Target.attachToTarget", {"targetId": user, "flatten": True}))["sessionId"]
        for target, (_, context) in (await page_contexts(cdp)).items():
            if context == p2:
                await cdp.send("Target.closeTarget", {"targetId": target})  # Profile 2 has no window now
        await cdp.send("Target.activateTarget", {"targetId": user})
        await asyncio.sleep(1.5)
        before = await evaluate(cdp, user_session, "document.hasFocus()")
        made = await evaluate(cdp, session, f"chrome.windows.create({{url: {json.dumps(MARKER)}, focused: false, "
                                            "incognito: false, type: 'normal'}).then(w => w.id)")
        await asyncio.sleep(1.5)
        after = await evaluate(cdp, user_session, "document.hasFocus()")
        marked = [context for url, context in (await page_contexts(cdp)).values() if url == MARKER]
        print(f"\nFACT 1: the Default page had the focus before: {before}; after the new Profile 2 window: {after}. "
              "Watch the screen too: did that window come to the front?")
        assert isinstance(made, int) and marked == [p2]
    finally:
        if cdp is not None:
            await cdp.close()
        two.close()


@pytest.mark.headful
@pytest.mark.posix_only
@CHROME
async def test_fact_2_how_soon_a_loaded_copy_is_recorded(tmp_path):
    from two_profiles import launch_two_profiles, probe_extension

    two = launch_two_profiles(tmp_path / "browser")
    try:
        started = time.monotonic()
        probe = two.load(probe_extension(tmp_path / "probe"))
        prefs, seconds = two.folder / "Profile 2" / "Secure Preferences", None
        while time.monotonic() - started < 30:
            if _recorded(prefs, probe):
                seconds = round(time.monotonic() - started, 1)
                break
            await asyncio.sleep(0.25)
        print(f"\nFACT 2: Secure Preferences recorded the loaded folder after {seconds} s (None: not within 30 s)")
        assert seconds is None or seconds > 0
    finally:
        two.close()


@pytest.mark.headful
@pytest.mark.posix_only
@CHROME
async def test_fact_3_last_focused_and_private_windows(tmp_path):
    from test_home import evaluate
    from two_profiles import launch_two_profiles, probe_extension, worker

    two = launch_two_profiles(tmp_path / "browser")
    cdp = None
    try:
        probe = two.load(probe_extension(tmp_path / "probe"))
        cdp = await CDP.connect(two.ws_url)
        session, _ = await worker(cdp, probe)
        made = await evaluate(cdp, session, "chrome.windows.create({incognito: true, url: 'about:blank'})"
                                            ".then(w => 'window ' + w.id).catch(e => 'refused: ' + e.message)")
        await asyncio.sleep(1)
        last = await evaluate(cdp, session, "chrome.windows.getLastFocused({windowTypes: ['normal']})"
                                            ".then(w => ({id: w.id, incognito: w.incognito}))"
                                            ".catch(e => 'none: ' + e.message)")
        print(f"\nFACT 3: a private window: {made}; getLastFocused gives {last} (the filter stays either way)")
        assert made is not None and last is not None
    finally:
        if cdp is not None:
            await cdp.close()
        two.close()


@pytest.mark.headful
@pytest.mark.posix_only
@CHROME
async def test_fact_4_the_worker_while_its_socket_is_open(tmp_path, fake_claude):
    from ai_browser.app.agents import AgentManager
    from ai_browser.brain.service import BrainService
    from ai_browser.brain.store import BrainStore
    from test_watcher import start_server
    from two_profiles import launch_two_profiles, page_contexts, page_outside

    runner, _, script = fake_claude
    script.write_text(json.dumps([{"result": "[]"}]), encoding="utf-8")
    home = tmp_path / "home"
    agents = AgentManager(home, claude=runner)
    brain = BrainService(BrainStore(home), agents, claude=runner)
    server, folder = await start_server(home, agents, brain)
    two = launch_two_profiles(tmp_path / "browser")
    cdp = None
    try:
        watcher_id = two.load(folder)  # the real watcher, in Profile 2, talking to a real app server
        server.allow_watcher(f"chrome-extension://{watcher_id}")
        for _ in range(200):
            if brain.watcher:
                break
            await asyncio.sleep(0.1)
        assert brain.watcher, "the watcher never connected"
        cdp = await CDP.connect(two.ws_url)
        missing = 0
        for _ in range(45):  # past the 30 s an idle worker would get
            infos = (await cdp.send("Target.getTargets"))["targetInfos"]
            listed = [info for info in infos if info["type"] == "service_worker"
                      and info["url"].startswith(f"chrome-extension://{watcher_id}/")]
            missing += not listed
            p2 = listed[0]["browserContextId"] if listed else None
            await asyncio.sleep(1)
        print(f"\nFACT 4a: the worker's target was missing {missing} times in 45 s while its socket was open")
        two.open_profile("Default")
        await page_outside(cdp, p2)
        for target, (_, context) in (await page_contexts(cdp)).items():
            if context == p2:
                await cdp.send("Target.closeTarget", {"targetId": target})
        started = time.monotonic()
        while brain.watcher and time.monotonic() - started < 180:
            await asyncio.sleep(1)
        print(f"FACT 4b: the copy stayed connected {time.monotonic() - started:.0f} s after its profile's last window "
              "closed (180: still connected)")
        assert missing == 0
    finally:
        if cdp is not None:
            await cdp.close()
        two.close()
        await server.stop()


@pytest.mark.headful
@pytest.mark.posix_only
@CHROME
async def test_fact_5_two_copies_two_contexts(tmp_path):
    from test_home import evaluate
    from two_profiles import launch_two_profiles, page_contexts, page_outside, probe_extension, worker

    two = launch_two_profiles(tmp_path / "browser")
    cdp = None
    try:
        in_p2 = two.load(probe_extension(tmp_path / "probe-p2"))
        cdp = await CDP.connect(two.ws_url)
        _, p2 = await worker(cdp, in_p2)
        two.open_profile("Default")
        await page_outside(cdp, p2)
        in_default = two.load(probe_extension(tmp_path / "probe-default"))  # the profile used last is Default now
        found = {}
        for name, extension_id in (("p2", in_p2), ("default", in_default)):
            session, context = await worker(cdp, extension_id)
            marker = f"about:blank#aib-{'a' * 15}{'1' if name == 'p2' else '2'}"
            await evaluate(cdp, session, f"chrome.tabs.create({{url: {json.dumps(marker)}, active: false}})"
                                         ".then(() => true)")
            await asyncio.sleep(1)
            tab = [ctx for url, ctx in (await page_contexts(cdp)).values() if url == marker]
            found[name] = (context, tab)
        print(f"\nFACT 5: worker and tab contexts per copy: {found}")
        assert found["p2"][0] != found["default"][0]
        assert all(tab == [context] for context, tab in found.values())
    finally:
        if cdp is not None:
            await cdp.close()
        two.close()
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_profile_facts.py -q -p no:randomly`

Expected: FAIL. `test_headful_tests_run_only_when_asked` fails with `ImportError: cannot import name 'HEADFUL_ONLY'
from 'conftest'`, and `test_the_headful_marker_is_registered` fails its assertion. The five facts don't skip yet
(pytest warns about the unknown `headful` mark) and fail with `ModuleNotFoundError: No module named 'two_profiles'`.

- [ ] **Step 3: Add the marker, the skip rule and the helper**

In `pyproject.toml`, add one line to `markers`, after the `windows_only` line:

```toml
  "headful: opens visible throwaway browser windows; runs only with AIB_HEADFUL=1",
```

In `tests/conftest.py`, after `platform_skip`:

```python
HEADFUL_ONLY = "headful: opens visible throwaway browser windows; runs only with AIB_HEADFUL=1"


def headful_skip(item, env) -> str | None:
    """Why a headful test can't run now: it opens visible windows, so only a run that asks for them (AIB_HEADFUL=1, the
    main session with the user's OK) gets them. Their browsers are throwaway Chromes, never the user's."""
    if "headful" in item.keywords and env.get("AIB_HEADFUL") != "1":
        return HEADFUL_ONLY
    return None
```

and in `pytest_collection_modifyitems` replace `reason = platform_skip(item, windows)` with:

```python
        reason = platform_skip(item, windows) or headful_skip(item, os.environ)
```

Create `tests/two_profiles.py`:

```python
"""A visible throwaway Google Chrome with two profiles, for the headful tests (AIB_HEADFUL=1 only).

Its own temporary --user-data-dir: never one of the user's browsers. Folders are loaded over the DevTools pipe as
probe4.py loaded its extension: the browser starts in one profile with the pipe; a second start of the same
--user-data-dir with --profile-directory opens the other profile in the running browser (Chromium hands the start
over); Extensions.loadUnpacked then loads a folder into the profile used last (fact 5 checks this)."""

from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ai_browser.chrome import chrome_binary, find_ws_url
from pipe_chrome import _spawn_posix  # wave B moved the pipe launcher here from appbrowser.py
from test_home import evaluate

ARGS = ("--no-first-run", "--no-default-browser-check", "--disable-search-engine-choice-screen",
        "--window-size=900,700")
MARKER = "about:blank#aib-0123456789abcdef"


def probe_extension(folder: Path) -> Path:
    """A tiny MV3 extension (the tabs permission only) whose worker a test drives over CDP: a stand-in for a copy."""
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {"manifest_version": 3, "name": "probe", "version": "1", "permissions": ["tabs"],
                "background": {"service_worker": "worker.js"}}
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (folder / "worker.js").write_text("chrome.runtime.onInstalled.addListener(() => {});\n", encoding="utf-8")
    return folder


@dataclass
class TwoProfiles:
    folder: Path
    ws_url: str
    process: object
    pipe: object

    def load(self, extension: Path) -> str:
        """Load an extension folder into the profile used last; its id."""
        return self.pipe.call("Extensions.loadUnpacked", {"path": str(extension)})["id"]

    def open_profile(self, profile: str) -> None:
        """A second start: the running browser opens a window of `profile`, which becomes the profile used last."""
        subprocess.run([chrome_binary(), f"--user-data-dir={self.folder}", f"--profile-directory={profile}", *ARGS,
                        "about:blank"], timeout=30, check=False, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)

    def close(self) -> None:
        self.pipe.close()  # Chrome quits when its pipe closes
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=15)


def launch_two_profiles(folder: Path, first: str = "Profile 2") -> TwoProfiles:
    binary = chrome_binary()
    folder.mkdir(parents=True, exist_ok=True)
    args = [binary, f"--user-data-dir={folder}", f"--profile-directory={first}", *ARGS, "--remote-debugging-port=0",
            "--remote-debugging-pipe", "--enable-unsafe-extension-debugging", "about:blank"]
    process, pipe = _spawn_posix(binary, args, True)
    return TwoProfiles(folder, find_ws_url(folder, timeout=20), process, pipe)


async def page_contexts(cdp) -> dict[str, tuple[str, str]]:
    """Every page target: (url, browserContextId)."""
    infos = (await cdp.send("Target.getTargets"))["targetInfos"]
    return {info["targetId"]: (info.get("url", ""), info.get("browserContextId", "")) for info in infos
            if info["type"] == "page"}


async def worker(cdp, extension_id: str, seconds: float = 15) -> tuple[str, str]:
    """(session, context) of an extension's service worker, attached (an attached worker stays awake)."""
    for _ in range(int(seconds * 10)):
        infos = (await cdp.send("Target.getTargets"))["targetInfos"]
        found = [info for info in infos if info["type"] == "service_worker"
                 and info["url"].startswith(f"chrome-extension://{extension_id}/")]
        if found:
            session = (await cdp.send("Target.attachToTarget", {"targetId": found[0]["targetId"],
                                                                "flatten": True}))["sessionId"]
            return session, found[0]["browserContextId"]
        await asyncio.sleep(0.1)
    raise AssertionError(f"no worker for {extension_id}")


async def page_outside(cdp, context: str | None, seconds: float = 15) -> str:
    """A page target in another context than `context`: the other profile's window, once it opened."""
    for _ in range(int(seconds * 10)):
        for target, (_, found) in (await page_contexts(cdp)).items():
            if found and found != context:
                return target
        await asyncio.sleep(0.1)
    raise AssertionError("the other profile's window never opened")


async def in_worker(cdp, session: str, expression: str):
    return await evaluate(cdp, session, expression)
```

If the merged `tests/pipe_chrome.py` spells `_spawn_posix` differently, import its name: it is the function that
starts Chrome with descriptors 3 and 4 for the pipe and returns the process and the pipe.

- [ ] **Step 4: Run them; then the main session measures the five facts**

Run: `uv run pytest tests/test_profile_facts.py -q -p no:randomly`

Expected: the two plain tests PASS; the five facts are SKIPPED with "headful: opens visible throwaway browser windows;
runs only with AIB_HEADFUL=1".

Then the main session (never a subagent) asks the user: "May I open a few visible throwaway Chrome windows for about
four minutes to measure how a second profile behaves? They use their own temporary profiles, never your Brave or
Chrome." Only after a yes:

Run: `AIB_HEADFUL=1 uv run pytest tests/test_profile_facts.py -q -s -p no:randomly`

Write the five `FACT` lines to the ledger, and these decisions:
1. **Fact 1:** if the Default page lost the focus, or the user saw the new window come to the front, Task 15 sets
   `where.WINDOW_FRONT_NOTE = "A new window for this profile may come to the front."` (Settings and the card show it).
   Otherwise it stays `""`. On the Windows laptop this is re-checked in the final manual check.
2. **Fact 2:** if the file recorded the folder later than 15 s, Task 14 sets `REREAD_AFTER`'s last value to that
   time rounded up to whole seconds. If it never recorded it within 30 s (a pipe load may differ from **Load
   unpacked**), keep `(2.0, 5.0, 15.0)`; the user's own Load unpacked is checked in the manual check (the row turns
   ✓ watcher).
3. **Fact 3:** noted only. `openTab` filters private windows either way.
4. **Fact 4:** if the worker's target went missing while its socket was open, stop and tell the user: Decision 8's
   context needs revisiting. Write fact 4b's seconds into the docstring of `Watchers` (Task 14): "after its profile's
   last window closes, a copy stayed connected about N s (measured)".
5. **Fact 5:** if the two copies show one context, `TwoProfiles.load` loads into the first profile, not the one used
   last: note it, and Task 26's headful tests load the Default copy before opening Profile 2 instead.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/conftest.py tests/two_profiles.py tests/test_profile_facts.py
git commit -m "test: a headful marker, a two-profile throwaway Chrome, and the five profile facts"
```

### Task 2: `places.py`: the place, saved in Settings, chosen for the user until they pick

**Files:**
- Create: `src/ai_browser/places.py`
- Create: `tests/places_rig.py`
- Modify: `tests/conftest.py` (`_never_the_users_browsers` also sets `AIB_CHROME_PROFILE`)
- Modify: `tests/test_chrome.py` (`test_tests_never_reach_the_real_browsers`)
- Test: `tests/test_places.py` (new)

**Interfaces:**
- Consumes: wave B's `settings.read_settings(home) -> dict` and `settings.write_setting(home, key, value)` (imported
  inside the functions that use them, so `chrome` → `places` → `settings` can never close an import cycle through
  wave B's window module), and `extension_id.extension_id_for(folder)`; wave A's `browsers.installed()`, `os_default()`, `by_id()`, `data_dir()`,
  `for_data_dir()`, `plain_folder()`, `profiles()`, `watcher_places(data_dir, watchers)`, `Installed(facts, binary,
  bundle, version, data_dir)`, and `platforms.user_data_dir("brave")`.
- Produces (`src/ai_browser/places.py`):
  - `KEY = "agents_browser"`, `DEFAULT_PROFILE = "Default"`;
  - `normalize(folder, system=None) -> str`, `same_folder(a, b, system=None) -> bool`;
  - `@dataclass(frozen=True) class Place(browser: str, user_data_dir: str, profile: str)` with `instance -> str`,
    `key -> tuple[str, str]` and `public() -> {"browser", "profile"}`;
  - `plain_profile(name) -> bool`, `profile_ok(data_dir, profile) -> bool`;
  - `save_place(home, place) -> None` (`ValueError` for a place whose browser is `""`);
  - `saved_place(home, installed=None) -> Place | None`;
  - `primary_watcher(home) -> tuple[str, Path]` (the primary copy's id and folder);
  - `default_place(home, installed=None) -> Place`;
  - `place_from_env(env, home=None) -> Place | None`;
  - `resolve(home, env=None, installed=None) -> tuple[Place, bool]` (the place, and whether it was chosen for the
    user);
  - `place_env(place) -> dict[str, str]`;
  - `tests/places_rig.py`: `LOCAL_STATE`, `move_home(monkeypatch, tmp_path) -> Path`,
    `install(monkeypatch, tmp_path, *ids, default=None, local_state=None) -> dict[str, Path]` (browser id → its data
    folder), `load_watcher(data_dir, profile, extension_id, folder, enabled=True)`,
    `unload_watcher(data_dir, profile, extension_id)`, `write_local_state(data_dir, state)`.

- [ ] **Step 1: Write the failing tests**

`tests/places_rig.py`:

```python
"""Installed browsers, faked for wave C's tests: HOME, USERPROFILE and LOCALAPPDATA moved into tmp_path,
browsers.installed() and os_default() patched, each browser's data folder at wave A's own place for it, with a
Local State and its profile folders. Never the user's files, and the same on macOS and Windows."""

from __future__ import annotations

import json
from pathlib import Path

LOCAL_STATE = {"profile": {
    "info_cache": {"Default": {"name": "Personal", "profile_highlight_color": -12627531,
                               "user_name": "alex@example.com", "gaia_name": "Alex Example"},
                   "Profile 1": {"name": "Work", "default_avatar_fill_color": -14983648},
                   "Profile 2": {"name": "Side"}},
    "profiles_order": ["Default", "Profile 1", "Profile 2"],
    "last_used": "Profile 1"}}


def move_home(monkeypatch, tmp_path) -> Path:
    home = tmp_path / "user-home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("LOCALAPPDATA", str(home / "AppData" / "Local"))
    return home


def write_local_state(data_dir, state) -> None:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "Local State").write_text(json.dumps(state), encoding="utf-8")
    for folder in state.get("profile", {}).get("info_cache", {}):
        (data_dir / folder).mkdir(exist_ok=True)


def install(monkeypatch, tmp_path, *ids, default=None, local_state=None) -> dict[str, Path]:
    """Make browsers "installed": their data folders under the moved home, browsers.installed() listing them in table
    order, and os_default() naming `default`. Returns browser id -> data folder."""
    from ai_browser import browsers, platforms

    move_home(monkeypatch, tmp_path)
    rows, folders = [], {}
    order = [facts.id for facts in platforms.KNOWN_BROWSERS]  # installed() lists rows in table order
    for browser_id in sorted(ids, key=order.index):
        facts = browsers.by_id(browser_id)
        data = browsers.data_dir(facts)
        write_local_state(data, LOCAL_STATE if local_state is None else local_state)
        binary = tmp_path / "bin" / browser_id
        binary.parent.mkdir(exist_ok=True)
        binary.write_bytes(b"")
        rows.append(browsers.Installed(facts=facts, binary=binary, bundle=None, version=None, data_dir=data))
        folders[browser_id] = data
    monkeypatch.setattr(browsers, "installed", lambda *args, **kwargs: list(rows))
    monkeypatch.setattr(browsers, "os_default", lambda *args, **kwargs: default)
    return folders


def load_watcher(data_dir, profile, extension_id, folder, enabled=True) -> None:
    """That profile's Secure Preferences records the unpacked folder, as the browser does after Load unpacked."""
    path = Path(data_dir) / profile / "Secure Preferences"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    settings = data.setdefault("extensions", {}).setdefault("settings", {})
    settings[extension_id] = {"path": str(folder), "location": 4, "disable_reasons": [] if enabled else [1]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def unload_watcher(data_dir, profile, extension_id) -> None:
    path = Path(data_dir) / profile / "Secure Preferences"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["extensions"]["settings"].pop(extension_id, None)
    path.write_text(json.dumps(data), encoding="utf-8")
```

`tests/test_places.py`:

```python
"""Where agents browse (places.py): one browser instance and one profile folder, saved in <home>/settings.json and
chosen for the user until they pick. Browsers are "installed" by places_rig: HOME in tmp_path, never the user's."""

import io
import json
import socket

import pytest

from conftest import file_mode
from places_rig import install, load_watcher, move_home, unload_watcher, write_local_state


def place(browser, folder, profile="Default"):
    from ai_browser.places import Place

    return Place(browser, str(folder), profile)


@pytest.fixture
def unset(monkeypatch):
    """No AIB_CHROME_DIR or AIB_CHROME_PROFILE: the saved place and the default decide (conftest sets both)."""
    monkeypatch.delenv("AIB_CHROME_DIR")
    monkeypatch.delenv("AIB_CHROME_PROFILE")


def test_the_saved_choice_wins_over_a_switch_that_is_on(monkeypatch, tmp_path, unset):
    from ai_browser.chrome import switch_on
    from ai_browser.places import resolve, save_place

    folders = install(monkeypatch, tmp_path, "brave", "chrome", default="chrome")
    home = tmp_path / "home"
    save_place(home, place("brave", folders["brave"], "Profile 1"))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        (folders["chrome"] / "DevToolsActivePort").write_text(f"{listener.getsockname()[1]}\n/devtools/browser/x\n",
                                                             encoding="utf-8")
        assert switch_on(folders["chrome"]) and not switch_on(folders["brave"])
        assert resolve(home) == (place("brave", folders["brave"], "Profile 1"), False)


def test_resolve_order(monkeypatch, tmp_path):
    from ai_browser import browsers, platforms
    from ai_browser.places import resolve, save_place

    folders = install(monkeypatch, tmp_path, "brave", "chrome", default="chrome")
    home, throwaway = tmp_path / "home", tmp_path / "throwaway"
    env = {"AIB_CHROME_DIR": str(throwaway), "AIB_CHROME_PROFILE": "Profile 3"}
    assert resolve(home, env) == (place("", throwaway, "Profile 3"), False)  # no known browser owns it
    assert resolve(home, {**env, "AIB_CHROME_PROFILE": "../x"})[0].profile == "Default"
    assert resolve(home, {"AIB_CHROME_DIR": str(folders["chrome"])}) == (place("chrome", folders["chrome"]), False)
    save_place(home, place("brave", folders["brave"], "Profile 1"))
    assert resolve(home, {"AIB_CHROME_DIR": str(folders["brave"])})[0].profile == "Profile 1"  # the saved profile
    assert resolve(home, {}) == (place("brave", folders["brave"], "Profile 1"), False)  # then the saved place
    (home / "settings.json").unlink()
    assert resolve(home, {}) == (place("chrome", folders["chrome"], "Profile 1"), True)  # the OS default, used last
    monkeypatch.setattr(browsers, "os_default", lambda *args, **kwargs: "edge")  # agents can't use it
    assert resolve(home, {}) == (place("brave", folders["brave"], "Profile 1"), True)  # the first one offered
    monkeypatch.setattr(browsers, "installed", lambda *args, **kwargs: [])
    assert resolve(home, {}) == (place("brave", platforms.user_data_dir("brave")), True)  # an error can name it


def test_the_fallback_to_braves_folder_reads_nothing(monkeypatch, tmp_path):
    import builtins

    from ai_browser import browsers, platforms
    from ai_browser.places import resolve

    move_home(monkeypatch, tmp_path)
    brave = platforms.user_data_dir("brave")
    write_local_state(brave, {"profile": {"info_cache": {"Profile 9": {"name": "Leftover"}}, "last_used": "Profile 9"}})
    monkeypatch.setattr(browsers, "installed", lambda *args, **kwargs: [])
    opened = []
    real_open, real_shared = builtins.open, platforms.open_shared

    def spy_open(path, *args, **kwargs):
        opened.append(str(path))
        return real_open(path, *args, **kwargs)

    def spy_shared(path):
        opened.append(str(path))
        return real_shared(path)

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(io, "open", spy_open)
    monkeypatch.setattr(platforms, "open_shared", spy_shared)
    found, automatic = resolve(tmp_path / "home", {})
    assert (found.profile, automatic) == ("Default", True)
    assert not [path for path in opened if path.startswith(str(brave))]  # a leftover folder is never read


def test_a_saved_browser_that_is_gone_is_ignored(monkeypatch, tmp_path):
    from ai_browser import browsers
    from ai_browser.places import resolve, save_place

    folders = install(monkeypatch, tmp_path, "brave", "chrome", default="brave")
    home = tmp_path / "home"
    rows = browsers.installed()
    save_place(home, place("chrome", folders["chrome"], "Profile 2"))
    assert resolve(home, {})[0] == place("chrome", folders["chrome"], "Profile 2")
    monkeypatch.setattr(browsers, "installed", lambda *args, **kwargs: [row for row in rows if row.id == "brave"])
    assert resolve(home, {})[1] is True  # Chrome was uninstalled
    monkeypatch.setattr(browsers, "installed", lambda *args, **kwargs: list(rows))
    save_place(home, place("chrome", tmp_path / "moved", "Profile 2"))
    assert resolve(home, {})[1] is True  # not that browser's folder any more
    save_place(home, place("chrome", folders["chrome"], "Profile 2"))
    state = json.loads((folders["chrome"] / "Local State").read_text(encoding="utf-8"))
    del state["profile"]["info_cache"]["Profile 2"]
    write_local_state(folders["chrome"], state)
    assert resolve(home, {})[1] is True  # the profile was deleted


def test_saving_keeps_other_keys_and_is_private(tmp_path):
    from ai_browser.places import KEY, save_place
    from ai_browser.settings import read_settings, write_setting

    home = tmp_path / "home"
    write_setting(home, "window_browser", "chrome")
    save_place(home, place("brave", tmp_path / "b", "Profile 1"))
    data = read_settings(home)
    assert data["window_browser"] == "chrome"
    assert data[KEY] == {"id": "brave", "user_data_dir": str(tmp_path / "b"), "profile": "Profile 1"}
    assert file_mode(home / "settings.json") in (None, 0o600)
    with pytest.raises(ValueError):
        save_place(home, place("", tmp_path / "throwaway"))  # a test's throwaway Chrome is never saved


@pytest.mark.parametrize("text", ["", '{"agents_browser": {"id": "brave"', "[]", '{"agents_browser": ["brave"]}',
                                  '{"agents_browser": {"id": 1, "user_data_dir": null, "profile": []}}',
                                  '{"agents_browser": {"id": "brave", "user_data_dir": "", "profile": "Default"}}'])
def test_a_broken_settings_file_never_crashes(monkeypatch, tmp_path, text):
    from ai_browser.places import resolve

    install(monkeypatch, tmp_path, "brave", default="brave")
    home = tmp_path / "home"
    home.mkdir()
    (home / "settings.json").write_text(text, encoding="utf-8")
    assert resolve(home, {})[1] is True


def test_the_profile_chosen_for_you_is_the_watchers_then_last_used(monkeypatch, tmp_path):
    from ai_browser.places import primary_watcher, resolve

    folders = install(monkeypatch, tmp_path, "brave", default="brave")
    home = tmp_path / "home"
    extension_id, primary = primary_watcher(home)
    primary.mkdir(parents=True)
    load_watcher(folders["brave"], "Default", extension_id, primary)
    assert resolve(home, {}) == (place("brave", folders["brave"], "Default"), True)  # where the watcher is
    load_watcher(folders["brave"], "Profile 2", extension_id, primary)
    assert resolve(home, {})[0].profile == "Profile 1"  # loaded in two profiles: it places nothing; used last
    unload_watcher(folders["brave"], "Profile 2", extension_id)
    load_watcher(folders["brave"], "Default", extension_id, primary, enabled=False)
    assert resolve(home, {})[0].profile == "Profile 1"  # switched off: the profile used last


@pytest.mark.parametrize("name", ["../x", "a/b", "a\\b", "C:x", "..", ".", "", 3, None])
def test_profile_names_are_plain_folder_names(name, tmp_path):
    from ai_browser.places import place_from_env, plain_profile

    assert not plain_profile(name)
    env = {"AIB_CHROME_DIR": str(tmp_path / "t")}
    if isinstance(name, str):
        env["AIB_CHROME_PROFILE"] = name
    assert place_from_env(env).profile == "Default"
    assert plain_profile("Default") and plain_profile("Profile 12")


def test_place_env_round_trip(monkeypatch, tmp_path):
    from ai_browser.places import place_env, place_from_env

    folders = install(monkeypatch, tmp_path, "brave", default="brave")
    chosen = place("brave", folders["brave"], "Profile 1")
    env = place_env(chosen)
    assert env == {"AIB_BROWSER": "chrome", "AIB_CHROME_DIR": str(folders["brave"]), "AIB_CHROME_PROFILE": "Profile 1"}
    assert place_from_env(env) == chosen
    assert place_from_env({}) is None


def test_two_spellings_of_one_folder_are_one_instance(tmp_path):
    from ai_browser.places import same_folder

    assert same_folder(r"C:\Users\Alex\AppData\Local\X", r"c:\users\alex\appdata\local\x", system="win32")
    assert place("brave", tmp_path / "b").instance == place("brave", tmp_path / "b" / ".." / "b").instance
    assert place("brave", tmp_path / "b").key != place("brave", tmp_path / "b", "Profile 1").key
```

In `tests/test_chrome.py`, `test_tests_never_reach_the_real_browsers` gains, at its end:

```python
    from ai_browser import browsers, config, places

    assert os.environ["AIB_CHROME_PROFILE"] == "Default"
    assert places.resolve(config.home())[0].user_data_dir == os.environ["AIB_CHROME_DIR"]
    assert browsers.installed() == []  # wave B's conftest parts keep detection off this machine's apps
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_places.py tests/test_chrome.py::test_tests_never_reach_the_real_browsers -q -p no:randomly`

Expected: FAIL. `tests/test_places.py` errors with `ModuleNotFoundError: No module named 'ai_browser.places'`; the
`test_chrome.py` test fails with `KeyError: 'AIB_CHROME_PROFILE'`.

- [ ] **Step 3: Write `places.py` and the conftest line**

In `tests/conftest.py`, `_never_the_users_browsers` gains, right after its `AIB_CHROME_DIR` line:

```python
    monkeypatch.setenv("AIB_CHROME_PROFILE", "Default")  # with AIB_CHROME_DIR, places.resolve never reads a choice
```

Create `src/ai_browser/places.py`:

```python
"""Where agents browse: a Place is one browser instance (its folder of profiles) and one profile folder in it, saved in
<home>/settings.json under "agents_browser", and chosen for the user until they pick (browser-profile-choice Decisions
1, 2 and 15).

No app imports: the engine of a lone Claude Code session resolves its place here too. This module imports browsers,
platforms, settings and extension_id, never chrome (chrome imports it). Every read of a browser's files goes through
browsers.py, which fails safe and reads no account field; nothing here connects to a browser."""

from __future__ import annotations

import ntpath
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from . import browsers, platforms
from .extension_id import extension_id_for

KEY = "agents_browser"
DEFAULT_PROFILE = "Default"


def normalize(folder, system: str | None = None) -> str:
    """A folder as two places compare it: its real path, and on Windows without regard to case."""
    path = os.path.realpath(str(folder))
    return ntpath.normcase(path) if (system or sys.platform) == "win32" else path


def same_folder(a, b, system: str | None = None) -> bool:
    """chrome._same_folder's rule, written here so that places never imports chrome."""
    return normalize(a, system) == normalize(b, system)


@dataclass(frozen=True)
class Place:
    browser: str  # a platforms.KNOWN_BROWSERS id offered to agents; "" for an AIB_CHROME_DIR no known browser owns
    user_data_dir: str  # that browser's folder of profiles on this computer
    profile: str  # a profile folder name ("Default", "Profile 1"), never a display name

    @property
    def instance(self) -> str:
        """One per browser instance: one debugging endpoint, so one relay upstream (Decision 11)."""
        return normalize(self.user_data_dir)

    @property
    def key(self) -> tuple[str, str]:
        return self.instance, self.profile

    def public(self) -> dict:
        """What an engine tells the app: ids only, never a folder path or a display name."""
        return {"browser": self.browser, "profile": self.profile}


def plain_profile(name) -> bool:
    """A profile folder name from the environment, the file or a page, by wave A's plain-name rule."""
    return isinstance(name, str) and browsers.plain_folder(name)


def profile_ok(data_dir, profile) -> bool:
    """Whether `profile` is one of that browser's profiles now: listed in its Local State; or, when Local State can't
    be read, a plain folder name whose folder exists."""
    if not plain_profile(profile):
        return False
    listed = browsers.profiles(data_dir)
    if listed:
        return any(found.folder == profile for found in listed)
    return (Path(data_dir) / profile).is_dir()


def _offered(installed) -> list:
    rows = browsers.installed() if installed is None else installed
    return [row for row in rows if row.agents]


def save_place(home, place: Place) -> None:
    """The user's choice (atomic, 0600, every other key kept: settings.write_setting). Only the app saves it."""
    from .settings import write_setting  # here, not at the top: chrome imports this module, and settings may import
    # the window's module, which imports chrome

    if not place.browser:
        raise ValueError("a place that no installed browser owns is never saved")
    write_setting(home, KEY, {"id": place.browser, "user_data_dir": place.user_data_dir, "profile": place.profile})


def _raw_saved(home) -> tuple[str, str, str] | None:
    from .settings import read_settings  # (see save_place)

    raw = read_settings(home).get(KEY)
    if not isinstance(raw, dict):
        return None
    values = raw.get("id"), raw.get("user_data_dir"), raw.get("profile")
    return values if all(isinstance(value, str) and value for value in values) else None


def saved_place(home, installed=None) -> Place | None:
    """The saved place when it is still valid (Decision 2): its browser is installed and offered to agents, its folder
    is that browser's own, and its profile is one the browser has now. Anything else is ignored."""
    raw = _raw_saved(home)
    if raw is None:
        return None
    browser, folder, profile = raw
    row = next((row for row in _offered(installed) if row.id == browser), None)
    if row is None or not same_folder(folder, row.data_dir) or not profile_ok(row.data_dir, profile):
        return None
    return Place(browser, str(row.data_dir), profile)


def primary_watcher(home) -> tuple[str, Path]:
    """The primary watcher copy, where the user loaded it first: its extension id and folder."""
    folder = Path(home) / "app" / "watcher"
    return extension_id_for(folder), folder


def default_place(home, installed=None) -> Place:
    """The place chosen for the user until they pick (Decision 2): the system's default browser when agents can use
    it, else the first installed one offered to agents (the Brave family first); in it, the profile where the primary
    watcher copy is enabled (in exactly one), else the profile used last. With nothing installed, Brave's folder, so an
    error can name it: nothing in it is read (a leftover data folder proves nothing)."""
    rows = _offered(installed)
    if not rows:
        return Place("brave", str(platforms.user_data_dir("brave")), DEFAULT_PROFILE)
    wanted = browsers.os_default()
    row = next((row for row in rows if row.id == wanted), rows[0])
    extension_id, folder = primary_watcher(home)
    holding = [found.profile for found in browsers.watcher_places(row.data_dir, {extension_id: folder})]
    if len(holding) == 1:
        return Place(row.id, str(row.data_dir), holding[0])
    last = next((found.folder for found in browsers.profiles(row.data_dir) if found.last_used), None)
    return Place(row.id, str(row.data_dir), last or DEFAULT_PROFILE)


def place_from_env(env: Mapping[str, str], home=None) -> Place | None:
    """AIB_CHROME_DIR's place (Decision 15, step 1), or None when it isn't set. The profile is AIB_CHROME_PROFILE when
    it is a plain folder name, else the saved profile when the saved folder is the same one, else "Default"."""
    configured = (env.get("AIB_CHROME_DIR") or "").strip()
    if not configured:
        return None
    folder = str(Path(configured).expanduser())
    facts = browsers.for_data_dir(folder)
    wanted = (env.get("AIB_CHROME_PROFILE") or "").strip()
    profile = wanted if plain_profile(wanted) else DEFAULT_PROFILE
    if not plain_profile(wanted) and home is not None:
        raw = _raw_saved(home)
        if raw is not None and same_folder(raw[1], folder) and plain_profile(raw[2]):
            profile = raw[2]
    return Place(facts.id if facts is not None else "", folder, profile)


def resolve(home, env: Mapping[str, str] | None = None, installed=None) -> tuple[Place, bool]:
    """(the place, chosen for the user?): AIB_CHROME_DIR (with AIB_CHROME_PROFILE), else the saved place, else the place
    chosen for the user. A browser whose switch happens to be on never decides (Decision 15)."""
    configured = place_from_env(os.environ if env is None else env, home)
    if configured is not None:
        return configured, False
    saved = saved_place(home, installed)
    if saved is not None:
        return saved, False
    return default_place(home, installed), True


def place_env(place: Place) -> dict[str, str]:
    """An agent's environment (Decision 3): its engine drives this browser, in this profile, for the agent's life."""
    return {"AIB_BROWSER": "chrome", "AIB_CHROME_DIR": place.user_data_dir, "AIB_CHROME_PROFILE": place.profile}
```

If wave A's `browsers.Installed` is built with other field names, change only `places_rig.install`'s constructor call
to match; `places.py` reads `row.id`, `row.agents` and `row.data_dir`, which wave A's spec names as properties.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_places.py tests/test_chrome.py::test_tests_never_reach_the_real_browsers -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/places.py tests/places_rig.py tests/test_places.py tests/conftest.py tests/test_chrome.py
git commit -m "feat: places.py, where agents browse: saved in Settings, chosen for the user until they pick"
```

### Task 3: `chrome.py` follows the place; names come from the table

**Files:**
- Modify: `src/ai_browser/chrome.py` (`own_browser_dir`, `browser_name`, `inspect_address`, `launch`; new
  `place_label`)
- Test: `tests/test_chrome.py` (`test_own_browser_dir_order` rewritten, `test_every_hint_names_the_browser` and
  `test_launch_refuses_every_real_browser_folder` extended, `test_place_label_names_the_folder_never_the_name`)

**Interfaces:**
- Consumes: Task 2's `places.resolve(home)`, `Place`; `config.home()`; wave A's `browsers.for_data_dir(folder)`,
  `browsers.all_data_dirs()`, `BrowserFacts.name` and `BrowserFacts.inspect` (the scheme).
- Produces:
  - `own_browser_dir() -> Path`: `Path(places.resolve(config.home())[0].user_data_dir)`;
  - `browser_name(folder) -> str` and `inspect_address(folder) -> str`: the table's row for a known folder, else
    today's rule ("BraveSoftware" in the path is Brave, anything else Chrome);
  - `place_label(place) -> str`: `"Brave · profile folder Profile 1"`, for the terminal;
  - `launch()` refuses every folder in `browsers.all_data_dirs()` too.

- [ ] **Step 1: Write the failing tests**

In `tests/test_chrome.py`, replace `test_own_browser_dir_order` with:

```python
def test_own_browser_dir_order(monkeypatch, tmp_path):
    from ai_browser import chrome
    from ai_browser.places import Place, save_place
    from places_rig import install

    folders = install(monkeypatch, tmp_path, "brave", "chrome", default="brave")
    monkeypatch.setenv("AIB_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AIB_CHROME_DIR")
    monkeypatch.delenv("AIB_CHROME_PROFILE")
    assert chrome.own_browser_dir() == folders["brave"]  # chosen for the user: the system's default browser
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        (folders["chrome"] / "DevToolsActivePort").write_text(f"{listener.getsockname()[1]}\n/devtools/browser/x\n",
                                                             encoding="utf-8")
        assert chrome.switch_on(folders["chrome"]) and not chrome.switch_on(folders["brave"])
        assert chrome.own_browser_dir() == folders["brave"]  # a switch that is on never decides
        save_place(tmp_path / "home", Place("chrome", str(folders["chrome"]), "Default"))
        assert chrome.own_browser_dir() == folders["chrome"]  # the place saved in Settings
    monkeypatch.setenv("AIB_CHROME_DIR", str(tmp_path / "set"))
    assert chrome.own_browser_dir() == tmp_path / "set"  # the setting wins over everything
    assert chrome.default_chrome_dir is chrome.own_browser_dir
```

`test_every_hint_names_the_browser` takes `monkeypatch` too, and gains at its end:

```python
    from ai_browser import browsers
    from places_rig import move_home

    move_home(monkeypatch, tmp_path)  # wave A's data folder for Chrome Beta, under a home of this test's own
    beta = browsers.data_dir(browsers.by_id("chrome-beta"))
    beta.mkdir(parents=True)
    assert (browser_name(beta), inspect_address(beta)) == ("Chrome Beta", "chrome://inspect/#remote-debugging")
    assert (browser_name(brave), inspect_address(brave)) == ("Brave", "brave://inspect/#remote-debugging")  # no row
```

`test_launch_refuses_every_real_browser_folder` gains a second loop:

```python
    from ai_browser import browsers

    for folder in browsers.all_data_dirs():  # every known browser's folder, installed or not
        with pytest.raises(ChromeError, match="refusing to launch a browser on the user's own profile folder"):
            chrome.launch(folder)
```

and a new test:

```python
def test_place_label_names_the_folder_never_the_name(tmp_path):
    from ai_browser.chrome import place_label
    from ai_browser.places import Place

    brave = tmp_path / "BraveSoftware" / "Brave-Browser"
    assert place_label(Place("brave", str(brave), "Profile 1")) == "Brave · profile folder Profile 1"
    assert place_label(Place("", str(tmp_path / "t"), "Default")) == "Chrome · profile folder Default"
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_chrome.py -k "own_browser_dir_order or every_hint or launch_refuses or place_label" -q -p no:randomly`

Expected: FAIL. `test_own_browser_dir_order` fails at "a switch that is on never decides" (today's rule returns
Chrome's folder); the hint test fails with `('Chrome', 'chrome://…')` for Chrome Beta; the launch test fails for
`all_data_dirs()`'s Edge, Arc or Vivaldi folder; `place_label` doesn't exist.

- [ ] **Step 3: Point `chrome.py` at the place and the table**

In `src/ai_browser/chrome.py`, the imports become:

```python
from . import browsers, config, places, platforms
```

Replace `own_browser_dir`, `browser_name` and `inspect_address` with:

```python
def own_browser_dir() -> Path:
    """The folder of the browser where agents browse (browser-profile-choice Decision 15): $AIB_CHROME_DIR; else the
    place saved in AI Browser's Settings; else the place chosen for the user. A switch that is on never decides."""
    return Path(places.resolve(config.home())[0].user_data_dir)


default_chrome_dir = own_browser_dir  # its earlier name


def browser_name(folder: Path) -> str:
    """The browser's own name from wave A's table ("Brave", "Chrome", "Chrome Beta"…). A folder no row owns keeps the
    earlier rule: a path with "BraveSoftware" is Brave, anything else Chrome (a test's throwaway folder says Chrome)."""
    facts = browsers.for_data_dir(folder)
    if facts is not None:
        return facts.name
    return "Brave" if "bravesoftware" in Path(folder).as_posix().lower() else "Chrome"


def inspect_address(folder: Path) -> str:
    """Where the user turns the remote-debugging switch on."""
    facts = browsers.for_data_dir(folder)
    scheme = facts.inspect if facts is not None else ("brave" if browser_name(folder) == "Brave" else "chrome")
    return f"{scheme}://inspect/#remote-debugging"


def place_label(place) -> str:
    """A place as the terminal names it: the browser and the profile folder, never the profile's display name (Claude
    Code often reads what `ai-browser app` and `doctor` print; Decision 16)."""
    return f"{browser_name(Path(place.user_data_dir))} · profile folder {place.profile}"
```

In `launch()`, replace the guard's line:

```python
    real = [*own_browser_dirs(), *browsers.all_data_dirs()]  # never a real browser folder, installed or not
    if any(_same_folder(folder, candidate) for candidate in real):
```

- [ ] **Step 4: Run them, and the rest of the file's quick tests**

Run: `uv run pytest tests/test_chrome.py -k "own_browser_dir_order or every_hint or launch_refuses or place_label or never_reach or folders or port_file or missing" -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/chrome.py tests/test_chrome.py
git commit -m "feat: the agents' browser folder follows the saved place, and every hint names the browser from the table"
```

### Task 4: `agentlink.py`: a request that may wait longer, `open_tab`, what the status says, a hello with the place

**Files:**
- Modify: `src/ai_browser/agentlink.py` (`_request`, `status`, `hello`; new `open_tab`, `NO_OPEN`, `WHY`)
- Test: `tests/test_grouping.py` (the `App` stand-in gains `delay`; new tests; two equality asserts updated)

**Interfaces:**
- Consumes: wave 2A's `hello()` (it reads the answer's status itself: a JSON answer, `{"cut_off": True}` on 410, `{}`
  on 204, `None` on failure); Task 2's `Place.public()`.
- Produces:
  - `AgentLink._request(method, path, body, timeout=2)`;
  - `async AgentLink.open_tab(marker: str, timeout: float) -> dict`: the app's answer to `POST /agent-open`
    `{"agent", "marker"}`, or `NO_OPEN = {"opened": False, "reason": "no_app"}`;
  - `AgentLink.status(max_age)` returns `{"groups": bool, "handed": list, "open": bool, "context": str | None,
    "why": str}`; `why` is `""` when `open`, one of `WHY` otherwise, `"no_watcher"` from an app that doesn't say, and
    `"no_app"` before any answer;
  - `AgentLink.hello(place=None)`: the body gains `"place": place.public()`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_grouping.py`, the `App` stand-in takes a delay (a slow app):

```python
class App:
    """A small stand-in for the app's routes: it records each request and answers from `answers` (path -> JSON),
    after `delay` seconds."""

    def __init__(self, answers=None, delay=0.0):
        self.requests, self.answers, self.delay = [], answers or {}, delay
```

and its `_answer` sleeps first, as its first line:

```python
            def _answer(self):
                time.sleep(app.delay)
```

Add:

```python
async def test_open_tab_is_heard_after_two_seconds():
    from ai_browser.agentlink import AgentLink

    opened = {"opened": True, "target": "T9", "tab": 412, "grouped": True, "new_window": False}
    app = App({"/agent-open": opened}, delay=2.4)
    try:
        link = AgentLink(app.url + "/agent-events", "tok", "a3")
        assert await link.open_tab("0123456789abcdef", 3.0) == opened  # today's 2 s request timeout would drop it
        assert app.requests[-1][:3] == ("POST", "/agent-open", {"agent": "a3", "marker": "0123456789abcdef"})
        assert await link.open_tab("fedcba9876543210", 1.0) == {"opened": False, "reason": "no_app"}  # too slow
    finally:
        app.stop()


async def test_status_says_whether_the_place_can_open_tabs():
    from ai_browser.agentlink import AgentLink

    app = App({"/agent-status": {"groups": True, "handed": [], "open": True, "context": "C1", "why": ""}})
    try:
        link = AgentLink(app.url + "/agent-events", "tok", "a3")
        assert await link.status() == {"groups": True, "handed": [], "open": True, "context": "C1", "why": ""}
        app.answers["/agent-status"] = {"groups": False, "handed": [], "open": False, "context": None, "why": "asleep"}
        await asyncio.sleep(1.1)
        assert await link.status() == {"groups": False, "handed": [], "open": False, "context": None, "why": "asleep"}
        app.answers["/agent-status"] = {"groups": True, "handed": [], "why": "<script>"}  # older, or strange
        await asyncio.sleep(1.1)
        status = await link.status()
        assert (status["open"], status["context"], status["why"]) == (False, None, "no_watcher")
    finally:
        app.stop()


async def test_hello_names_the_sessions_place():
    from ai_browser.agentlink import AgentLink
    from ai_browser.places import Place

    answer = {"cdp_token": "c", "place": {"browser": "brave", "profile": "Profile 1"}}
    app = App({"/agent-hello": answer})
    try:
        link = AgentLink(app.url + "/agent-events", "sess", "cc-t1")
        assert await link.hello(Place("brave", "/x/Brave-Browser", "Profile 1")) == answer
        body = app.requests[-1][2]
        assert body == {"agent": "cc-t1", "pid": os.getpid(), "place": {"browser": "brave", "profile": "Profile 1"}}
        assert "/x/" not in json.dumps(body)  # ids only: no folder goes to the app
        await link.hello()
        assert "place" not in app.requests[-1][2]
    finally:
        app.stop()
```

In `test_a_claim_with_no_app_says_so`, the last assertion becomes:

```python
    assert await link.status() == {"groups": False, "handed": [], "open": False, "context": None, "why": "no_app"}
```

and in `test_status_is_cached` the first assertion becomes:

```python
        assert await link.status() == await link.status() == {"groups": True, "handed": handed, "open": False,
                                                                "context": None, "why": "no_watcher"}
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_grouping.py -q -p no:randomly`

Expected: FAIL. `open_tab` doesn't exist; `status()` has no `open`; `hello()` takes no place.

- [ ] **Step 3: Write the changes**

In `src/ai_browser/agentlink.py`, beside `NO_APP`:

```python
NO_OPEN = {"opened": False, "reason": "no_app"}
WHY = {"no_watcher", "asleep", "shared", "unknown", "not_connected", "refused"}  # why the app can't open a tab
```

`_request` takes the timeout as a parameter (its docstring says "`timeout` s at most"):

```python
    def _request(self, method: str, path: str, body: dict | None, timeout: float = 2) -> dict | None:
        """One request to the app (`timeout` s at most): its JSON answer, {} for an empty one, None when it failed."""
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "Content-Type": "application/json", "X-AIB-Agent-Token": self.token})
        try:
            with _DIRECT.open(request, timeout=timeout) as response:
                raw = response.read()
        except (OSError, ValueError):  # refused, timed out, or an HTTP error (403, 404)
            return None
        try:
            return json.loads(raw) if raw else {}
        except ValueError:
            return None
```

After `claim`:

```python
    async def open_tab(self, marker: str, timeout: float) -> dict:
        """Ask the app for a blank tab the watcher in our place opens at about:blank#aib-<marker> (POST /agent-open,
        browser-profile-choice Decision 4): its answer, or NO_OPEN. `timeout` is the Placer's ENGINE_OPEN_WAIT: the
        app itself may take OPEN_WAIT (2.5 s), longer than every other request's 2 s."""
        answer = await asyncio.to_thread(self._request, "POST", "/agent-open", {"agent": self.agent, "marker": marker},
                                         timeout)
        return answer if isinstance(answer, dict) and isinstance(answer.get("opened"), bool) else dict(NO_OPEN)
```

In `status`, the answer's reading becomes:

```python
        if isinstance(answer, dict) and "handed" in answer:
            handed = [item for item in answer.get("handed") or []
                      if isinstance(item, dict) and isinstance(item.get("target"), str)]
            opens = answer.get("open") is True
            context = answer.get("context") if isinstance(answer.get("context"), str) else None
            why = "" if opens else answer.get("why") if answer.get("why") in WHY else "no_watcher"
            self._status = {"groups": answer.get("groups") is True, "handed": handed, "open": opens,
                            "context": context, "why": why}
        elif self._status is None:
            self._status = {"groups": False, "handed": [], "open": False, "context": None, "why": "no_app"}
```

and its docstring names the new fields: `{"groups", "handed", "open": the watcher in our place can open our tabs,
"context": that profile's browser context (opaque, never in a tool result), "why": why not}`.

In wave 2A's `hello()`, add the parameter `place=None` and build its body like this; the request and the reading of
the answer's status stay exactly as wave 2A wrote them:

```python
        body = {"agent": self.agent, "pid": os.getpid()}
        if place is not None:  # this session's own place (browser-profile-choice Decision 15): ids only
            body["place"] = place.public()
```

and add to its docstring: "With `place`, the app answers with the same place when it can hold that browser, or
"place": null."

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_grouping.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/agentlink.py tests/test_grouping.py
git commit -m "feat: an engine can ask the app for a tab the watcher opens, and says hello with its place"
```

### Task 5: `grouping.py`: the watcher opens the tab, else the fallback with its reason and one note

**Files:**
- Modify: `src/ai_browser/grouping.py` (docstring; `ENGINE_OPEN_WAIT`, `REASONS`, the texts, `Placement`,
  `Placer.open`, `Placer.note_for`, `Placer(name=, place=)`)
- Test: `tests/test_grouping.py`

**Interfaces:**
- Consumes: Task 4's `AgentLink.open_tab(marker, timeout)` and `status()` with `open`, `context`, `why`;
  `hello(place)`.
- Produces:
  - `ENGINE_OPEN_WAIT = 3.0`; `REASONS` (every reason `/agent-open` may give, plus `no_app`);
  - `why_words(why) -> str`: the status line's reason (Texts);
  - `FIRST_NOTE`, `MOVED_NOTE`, `NEW_WINDOW_NOTE` (format fields `key` and `name`);
  - `@dataclass class Placement(target=None, params=None, marker=None, why="", new_window=False)`;
  - `Placer(link, rediscover=None, name="Brave", place=None)`: `name` is the browser's name for the notes, `place`
    goes into a rediscovered hello;
  - `async Placer.open() -> Placement`;
  - `Placer.note_for(landed: str | None, why: str, key: str) -> str`;
  - `create_params()`, `placed()` and `popup()` as today.

- [ ] **Step 1: Write the failing tests**

In `tests/test_grouping.py`, `FakeLink` learns the new status fields and `open_tab`:

```python
class FakeLink:
    def __init__(self, groups=True, claim_wait=0.0, opens=False, open_answer=None, open_wait=0.0, context=None,
                 why="no_watcher"):
        self.groups, self.claim_wait, self.claims, self.reports, self.hellos = groups, claim_wait, [], [], 0
        self.opens, self.open_answer, self.open_wait, self.context, self.why = opens, open_answer, open_wait, context, why
        self.opened = []
        self.url, self.token, self.agent = "http://127.0.0.1:1/agent-events", "t", "a1"

    async def status(self, max_age=1.0):
        return {"groups": self.groups, "handed": [], "open": self.opens, "context": self.context,
                "why": "" if self.opens else self.why}

    async def open_tab(self, marker, timeout):
        self.opened.append((marker, timeout))
        await asyncio.sleep(self.open_wait)
        return self.open_answer or {"opened": False, "reason": "timeout"}

    async def claim(self, target, marker=None, opener=None, url=""):
        self.claims.append((target, marker))
        await asyncio.sleep(self.claim_wait)
        return {"grouped": True, "tab": 1}

    async def hello(self, place=None):
        self.hellos += 1

    def report(self, kind, target, adopted=False, **extra):
        self.reports.append((kind, target, adopted, extra))
```

Add:

```python
async def test_with_the_profiles_watcher_the_app_opens_the_tab():
    from ai_browser.grouping import ENGINE_OPEN_WAIT, MARKER, Placer

    answer = {"opened": True, "target": "T7", "tab": 5, "grouped": True, "new_window": True}
    link = FakeLink(opens=True, open_answer=answer)
    placement = await Placer(link).open()
    assert (placement.target, placement.params, placement.marker, placement.why) == ("T7", None, None, "")
    assert placement.new_window is True
    [(marker, timeout)] = link.opened
    assert MARKER.match(marker) and timeout == ENGINE_OPEN_WAIT


async def test_when_the_watcher_cant_the_tab_falls_back_with_the_reason():
    from ai_browser.grouping import MARKER_PREFIX, Placer

    timed_out = await Placer(FakeLink(opens=True)).open()  # the app said open, the watcher didn't answer
    assert timed_out.target is None and timed_out.why == "timeout"
    assert timed_out.params == {"url": MARKER_PREFIX + timed_out.marker, "background": True}  # groups: a marker
    asleep = await Placer(FakeLink(groups=False, why="asleep")).open()
    assert asleep.params == {"url": "about:blank", "newWindow": True, "background": True} and asleep.marker is None
    assert asleep.why == "asleep"
    assert (await Placer(None).open()).why == "no_app"
    strange = await Placer(FakeLink(opens=True, open_answer={"opened": False, "reason": "<b>"})).open()
    assert strange.why == "timeout"  # a reason the engine doesn't know is never passed on


async def test_open_waits_at_most_engine_open_wait():
    from ai_browser.grouping import ENGINE_OPEN_WAIT, Placer

    started = time.monotonic()
    placement = await Placer(FakeLink(opens=True, open_wait=10)).open()
    assert time.monotonic() - started < ENGINE_OPEN_WAIT + 0.5 and placement.why == "timeout"


async def test_the_fallback_note_is_said_once_and_names_no_profile():
    from ai_browser.grouping import Placer

    placer = Placer(FakeLink(), name="Brave")
    first = placer.note_for("C2", "no_watcher", "t2")
    assert first == ("(tab t2 opened in the Brave profile the user used last: AI Browser can't pick the profile "
                     "without the watcher there. Tell the user once; AI Home → Settings shows how to set it up.)")
    assert placer.note_for("C2", "no_watcher", "t3") == ""
    moved = placer.note_for("C3", "timeout", "t4")
    assert moved == ("(tab t4 opened in a different Brave profile from this session's earlier tabs: Brave puts new "
                     "tabs in the profile used last)")
    assert placer.note_for("C3", "no_watcher", "t5") == "" and placer.note_for("C2", "no_watcher", "t6") == ""
    for note in (first, moved):
        assert "Profile 1" not in note and "Personal" not in note and "Default" not in note
    chosen = Placer(FakeLink(context="C9"), name="Chrome")
    await chosen.open()  # the app knows the chosen profile's context: a tab that landed there needs no note
    assert chosen.note_for("C9", "no_watcher", "t1") == ""
    assert Placer(FakeLink(), name="Brave").note_for("C2", "", "t1") == ""  # placed by the watcher: nothing to say


def test_the_docstring_says_where_tabs_open():
    from ai_browser import grouping

    text = " ".join(grouping.__doc__.split())
    assert "CDP can't choose a profile" in text and "the watcher opens the tab (open_tab)" in text
    assert "default profile" not in text
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_grouping.py -q -p no:randomly`

Expected: FAIL with `ImportError: cannot import name 'ENGINE_OPEN_WAIT'` (and `Placer` has no `open`).

- [ ] **Step 3: Write the placement**

In `src/ai_browser/grouping.py`, the docstring's last sentence ("Tabs never carry a browserContextId, so they open
in the browser's default profile, never in a private window.") becomes:

```
CDP can't choose a profile: with the app and the profile's watcher, the watcher opens the tab (open_tab); otherwise it
opens in the profile the user used last, and the result says so. A tab never carries a browserContextId, and never
opens in a private window.
```

and its first paragraph gains, at its start: "With the app and the watcher in this session's place, the app has that
watcher open a blank tab at a secret marker and gives it to us (Placer.open); otherwise:".

Add after `REREAD_EVERY`:

```python
ENGINE_OPEN_WAIT = 3.0  # seconds the engine waits for the watcher's tab; the app itself waits OPEN_WAIT (2.5 s)
REASONS = {"no_app", "no_watcher", "asleep", "shared", "unknown", "not_connected", "timeout", "not_found",
           "wrong_profile", "refused"}
WHY = {  # the status line's reason (the spec's Texts): "the chosen profile", never its name or folder
    "no_app": "ai-browser app isn't running",
    "no_watcher": "the watcher isn't in the chosen profile",
    "unknown": "the watcher isn't in the chosen profile",
    "asleep": "the watcher in the chosen profile isn't connected",
    "shared": "the chosen profile's watcher folder is loaded in two profiles",
}
DIDNT_ANSWER = "the watcher in the chosen profile didn't answer"  # not_connected, timeout, not_found, refused, …
FIRST_NOTE = ("(tab {key} opened in the {name} profile the user used last: AI Browser can't pick the profile without "
              "the watcher there. Tell the user once; AI Home → Settings shows how to set it up.)")
MOVED_NOTE = ("(tab {key} opened in a different {name} profile from this session's earlier tabs: {name} puts new tabs "
              "in the profile used last)")
NEW_WINDOW_NOTE = "(a new {name} window was opened for tab {key}: the chosen profile had none open)"


def why_words(why: str) -> str:
    return WHY.get(why, DIDNT_ANSWER)


@dataclass
class Placement:
    """Where a new tab of ours comes from: the watcher already opened it (`target`, and `new_window` when it needed a
    window of its own), or the engine creates it with `params` and claims it with `marker`; `why` says why the watcher
    didn't ("" when it did)."""

    target: str | None = None
    params: dict | None = None
    marker: str | None = None
    why: str = ""
    new_window: bool = False
```

(import `dataclass` from `dataclasses`). `Placer`'s constructor and the two new methods:

```python
    def __init__(self, link: AgentLink | None, rediscover: Callable[[], AgentLink | None] | None = None,
                 name: str = "Brave", place=None):
        self.link = link
        self.rediscover = rediscover  # a Claude Code session reads link.json again (the app started or restarted)
        self.name = name  # the browser's name, for the notes (never a profile's)
        self.place = place  # this session's place (places.Place), sent in a rediscovered hello
        self._read_at = time.monotonic()
        self._chosen: str | None = None  # the chosen profile's context, when the app knows it (opaque)
        self._landed: set[str] = set()  # contexts this session's fallback tabs landed in
        self._noted = False

    async def open(self) -> Placement:
        """Where the next tab comes from (browser-profile-choice Decisions 4 and 6): with a link whose status says
        `open`, the watcher in our place opens it (within ENGINE_OPEN_WAIT); anything else is today's create_params(),
        with the reason."""
        await self._refresh()
        link = self.link
        if link is None:
            params, marker = await self.create_params()
            return Placement(params=params, marker=marker, why="no_app")
        status = await link.status(GROUPS_TTL)
        self._chosen = status.get("context")
        why = status.get("why") or "no_watcher"
        if status.get("open"):
            try:
                answer = await asyncio.wait_for(link.open_tab(new_marker(), ENGINE_OPEN_WAIT), ENGINE_OPEN_WAIT)
            except Exception:  # TimeoutError, or the app went away
                answer = {"opened": False, "reason": "timeout"}
            if answer.get("opened") is True and isinstance(answer.get("target"), str):
                return Placement(target=answer["target"], new_window=answer.get("new_window") is True)
            why = answer.get("reason") if answer.get("reason") in REASONS else "timeout"
        params, marker = await self.create_params()
        return Placement(params=params, marker=marker, why=why)

    def note_for(self, landed: str | None, why: str, key: str) -> str:
        """The note for a tab created here (Decision 6), from the context it landed in: the first time per session,
        and again when a tab lands in another context than the earlier ones; "" otherwise, and "" when the tab landed
        in the chosen profile after all. It names the browser, never a profile."""
        if not why or (landed is not None and landed == self._chosen):
            if landed is not None:
                self._landed.add(landed)
            return ""
        earlier = set(self._landed)
        if landed is not None:
            self._landed.add(landed)
        if not self._noted:
            self._noted = True
            return FIRST_NOTE.format(key=key, name=self.name)
        if landed is not None and earlier and landed not in earlier:
            return MOVED_NOTE.format(key=key, name=self.name)
        return ""
```

In `_refresh`, the rediscovered link's hello carries the place: `await found.hello(self.place)`.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_grouping.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/grouping.py tests/test_grouping.py
git commit -m "feat: a new tab comes from the watcher in the agent's profile, else falls back with its reason"
```

### Task 6: `browser.py`: attach to the watcher's tab, or create it and say where it landed

**Files:**
- Modify: `src/ai_browser/browser.py` (`open_worker`, `_download_notes`, `_place_notes`, new `_context_of`)
- Create: `tests/fake_cdp.py`
- Test: `tests/test_grouping.py`

**Interfaces:**
- Consumes: Task 5's `Placement`, `Placer.open()`, `Placer.note_for()`, `Placer.name`, `NEW_WINDOW_NOTE`.
- Produces:
  - `Browser._place_notes: list[str]`; `_download_notes()` returns the place notes first, then the stopped downloads,
    and clears both, so the notes reach `observe`'s and `act`'s results where download notes do;
  - `open_worker()` sends no `Target.createTarget` when the placement has a `target`; a target that is gone before
    it attaches raises `BrowserError("the new tab was closed before it could be used: try again")`;
  - `async Browser._context_of(target) -> str | None` (`Target.getTargetInfo`'s `browserContextId`);
  - `tests/fake_cdp.py`: `FakeCDP(contexts=None, missing=())` with `sent`, `methods()`, `on`, `off`, `send`,
    `close`, `closed`.

- [ ] **Step 1: Write the failing tests**

Create `tests/fake_cdp.py`:

```python
"""A CDP connection stand-in for engine and Browser tests that need no browser: it records what is sent and answers
the few methods a Browser sends to open, attach to and read a tab."""

from __future__ import annotations

import contextlib

from ai_browser.cdp import CDPError


class FakeCDP:
    def __init__(self, contexts=None, missing=()):
        self.sent: list[tuple[str, dict, str | None]] = []
        self.contexts = dict(contexts or {})  # target -> browserContextId ("C0" when not given)
        self.missing = set(missing)  # targets gone before anything attaches to them
        self.closed = False
        self.handlers: dict[str, list] = {}
        self._made = 0

    def on(self, method, handler):
        self.handlers.setdefault(method, []).append(handler)

    def off(self, method, handler):
        with contextlib.suppress(ValueError):
            self.handlers.get(method, []).remove(handler)

    def methods(self) -> list[str]:
        return [method for method, _, _ in self.sent]

    async def send(self, method, params=None, session_id=None, timeout=30):
        params = dict(params or {})
        self.sent.append((method, params, session_id))
        if method == "Target.createTarget":
            self._made += 1
            return {"targetId": f"N{self._made}"}
        if method == "Target.attachToTarget":
            if params.get("targetId") in self.missing:
                raise CDPError("No target with given id found", code=-32602, method=method)
            return {"sessionId": f"S-{params.get('targetId')}"}
        if method == "Page.getFrameTree":
            return {"frameTree": {"frame": {"id": "F1"}}}
        if method == "Target.getTargetInfo":
            target = params.get("targetId")
            return {"targetInfo": {"targetId": target, "type": "page", "url": "about:blank",
                                   "browserContextId": self.contexts.get(target, "C0")}}
        if method == "Target.getTargets":
            return {"targetInfos": []}
        return {}

    async def close(self):
        self.closed = True
```

In `tests/test_grouping.py` add:

```python
class FakePlacer:
    """The Browser's view of a Placer: a fixed placement, the real note rule, and a record of claims."""

    name = "Brave"

    def __init__(self, placement):
        from ai_browser.grouping import Placer

        self.placement, self.placed_calls = placement, []
        self._rule = Placer(None, name="Brave")

    async def open(self):
        return self.placement

    async def placed(self, target, marker):
        self.placed_calls.append((target, marker))

    def note_for(self, landed, why, key):
        return self._rule.note_for(landed, why, key)

    def popup(self, *args, **kwargs):
        pass


def chrome_browser_on(cdp, tmp_path, placement):
    from ai_browser.browser import Browser
    from ai_browser.config import Config
    from ai_browser.workfs import WorkDir

    return Browser(cdp, WorkDir(tmp_path / "work", "t"), Config(), mode="chrome", placer=FakePlacer(placement))


async def test_a_tab_the_watcher_opened_is_attached_and_none_is_created(tmp_path):
    from ai_browser.grouping import Placement
    from fake_cdp import FakeCDP

    cdp = FakeCDP()
    browser = chrome_browser_on(cdp, tmp_path, Placement(target="T7"))
    tab = await browser.open_worker()
    assert tab.target == "T7" and "Target.createTarget" not in cdp.methods()
    assert "Target.attachToTarget" in cdp.methods() and browser._download_notes() == []


async def test_a_new_window_for_the_profile_is_said_once(tmp_path):
    from ai_browser.grouping import Placement
    from fake_cdp import FakeCDP

    browser = chrome_browser_on(FakeCDP(), tmp_path, Placement(target="T7", new_window=True))
    tab = await browser.open_worker()
    assert browser._download_notes() == [f"(a new Brave window was opened for tab {tab.key}: the chosen profile had "
                                         "none open)"]
    assert browser._download_notes() == []


async def test_a_fallback_tab_reads_where_it_landed_and_says_so_once(tmp_path):
    from ai_browser.grouping import Placement
    from fake_cdp import FakeCDP

    cdp = FakeCDP(contexts={"N2": "C7"})  # the second tab lands in another profile (the user clicked there meanwhile)
    params = {"url": "about:blank", "newWindow": True, "background": True}
    browser = chrome_browser_on(cdp, tmp_path, Placement(params=params, why="no_watcher"))
    first = await browser.open_worker()
    notes = browser._download_notes()
    assert notes == [f"(tab {first.key} opened in the Brave profile the user used last: AI Browser can't pick the "
                     "profile without the watcher there. Tell the user once; AI Home → Settings shows how to set it "
                     "up.)"]
    second = await browser.open_worker()
    assert browser._download_notes() == [f"(tab {second.key} opened in a different Brave profile from this session's "
                                         "earlier tabs: Brave puts new tabs in the profile used last)"]
    assert cdp.methods().count("Target.createTarget") == 2 and cdp.methods().count("Target.getTargetInfo") == 2
    assert browser.placer.placed_calls == [("N1", None), ("N2", None)]


async def test_a_watchers_tab_closed_before_attach_fails_plainly_and_opens_nothing_else(tmp_path):  # Review Focus 4
    import pytest

    from ai_browser.browser import BrowserError
    from ai_browser.grouping import Placement
    from fake_cdp import FakeCDP

    cdp = FakeCDP(missing={"T7"})
    browser = chrome_browser_on(cdp, tmp_path, Placement(target="T7"))
    with pytest.raises(BrowserError, match="^the new tab was closed before it could be used: try again$"):
        await browser.open_worker()
    assert "Target.createTarget" not in cdp.methods()  # never a second tab, in whatever profile was used last
    assert browser.owned == {}
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_grouping.py -q -p no:randomly`

Expected: FAIL. `open_worker` calls `self.placer.create_params()`, which `FakePlacer` doesn't have
(`AttributeError`).

- [ ] **Step 3: Write `open_worker`'s two ways**

In `src/ai_browser/browser.py`, import `NEW_WINDOW_NOTE` (`from .grouping import NEW_WINDOW_NOTE`; grouping imports
only agentlink, so there is no cycle). In `__init__`, beside `self._stopped`:

```python
        self._place_notes: list[str] = []  # where a new tab went, when that isn't where the user chose (one note each)
```

Replace `_download_notes` with:

```python
    def _download_notes(self) -> list[str]:
        """The notes for the next result: where new tabs went (browser-profile-choice Decision 6), then the downloads
        that were stopped."""
        notes = self._place_notes + [f"⛔ a download of {name} was stopped: ask the user, then repeat with "
                                     "confirmed=true" for name in self._stopped]
        self._place_notes = []
        self._stopped.clear()
        return notes
```

Replace `open_worker` (the method whose docstring starts "A new tab of ours (closed with the session)"), keeping
wave B's single mode test for `background`:

```python
    async def open_worker(self, background: bool | None = None) -> Tab:
        """A new tab of ours (closed with the session) that does not become the working tab: Website QA uses these.
        In the user's own browser the placer decides: the watcher in the chosen profile opened it (nothing is created
        here), or it is created here, lands in the profile the browser used last, and the result says so once
        (browser-profile-choice Decisions 4 and 6). It waits for its group before anything loads in it."""
        placement = await self.placer.open() if self.placer is not None else None
        if placement is not None and placement.target is not None:
            try:
                tab = await self._setup_tab(placement.target)
            except CDPError:  # the user closed it at once: say so; never open another one somewhere else
                with contextlib.suppress(CDPError):
                    await self.cdp.send("Target.closeTarget", {"targetId": placement.target})
                raise BrowserError("the new tab was closed before it could be used: try again") from None
            if placement.new_window:
                self._place_notes.append(NEW_WINDOW_NOTE.format(name=self.placer.name, key=tab.key))
            return tab
        if placement is not None:
            params, marker = placement.params, placement.marker
        else:
            params, marker = {"url": "about:blank"}, None
            if self.mode == "chrome" if background is None else background:
                params["background"] = True  # don't steal the user's focus
        target = (await self.cdp.send("Target.createTarget", params))["targetId"]
        try:
            tab = await self._setup_tab(target)
        except BaseException:  # never leave a blank tab in the user's browser
            with contextlib.suppress(CDPError):
                await self.cdp.send("Target.closeTarget", {"targetId": target})
            raise
        if placement is not None:
            await self.placer.placed(target, marker)
            note = self.placer.note_for(await self._context_of(target), placement.why, tab.key)
            if note:
                self._place_notes.append(note)
        return tab

    async def _context_of(self, target: str) -> str | None:
        """Which browser context (profile, or private window) a tab of ours landed in: opaque, never shown."""
        with contextlib.suppress(CDPError, KeyError, TypeError):
            info = (await self.cdp.send("Target.getTargetInfo", {"targetId": target}))["targetInfo"]
            return info.get("browserContextId")
        return None
```

If wave B left `self.mode in ("chrome", "app")` in the `background` test, it is `self.mode == "chrome"` now (app mode
is gone); keep whatever wave B left.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_grouping.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/browser.py tests/fake_cdp.py tests/test_grouping.py
git commit -m "feat: an agent attaches to the tab its profile's watcher opened, or says where a tab it made landed"
```

### Task 7: The engine: one place per process, a route from it, and honest words

**Files:**
- Modify: `src/ai_browser/engine.py` (`Engine.__init__`, `_own_place`, `_start_chrome`, wave 2A's `_route`,
  `_browser_name`, `_placement`, `_status_text`; constants `ONLY_TABS`, `CHOSEN_LINE`, `FALLBACK_LINE`)
- Modify: `tests/test_chrome.py` (the old placement words, and the hello body, in its session tests)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: Task 2's `places.resolve(home)`, `Place`; Task 3's `browser_name`; Task 4's `hello(place)` and
  `status()`; Task 5's `Placer(link, rediscover, name, place)`, `why_words`; wave 2A's `_route()`,
  `AgentLink.discover`, `AgentLink.cdp`, `APP_GONE`, `APP_SILENT`, `CUT_OFF_SESSION`, the status line's start.
- Produces:
  - `Engine._place: Place | None`, set once by `_own_place()` at the first browser call and kept for the process's
    life (an agent's own `AIB_CHROME_DIR`/`AIB_CHROME_PROFILE` win inside `resolve`);
  - a direct connection goes to `find_ws_url(Path(place.user_data_dir), 2)`; `_browser_name()` names the place's
    browser;
  - `_route()`, for a session with a running app: `hello(place)`; an answer echoing the place gives the relay, and
    `"place": null` (or any other place) gives a direct connection, with wave 2A's "not through AI Browser" line;
  - `_placement()` returns the status line's whole part after wave 2A's start (`ONLY_TABS` included).

- [ ] **Step 1: Write the failing tests**

In `tests/test_engine.py` add:

```python
async def test_a_session_resolves_its_place_once(monkeypatch, tmp_path):
    from ai_browser import engine as engine_module
    from ai_browser.places import Place, save_place
    from fake_cdp import FakeCDP
    from places_rig import install

    folders = install(monkeypatch, tmp_path, "brave", "chrome", default="brave")
    for name in ("AIB_CHROME_DIR", "AIB_CHROME_PROFILE", "AIB_BROWSER"):
        monkeypatch.delenv(name)
    home = tmp_path / "home"
    save_place(home, Place("brave", str(folders["brave"]), "Default"))
    asked, made = [], []

    def ws_url(folder, timeout=0):
        asked.append(Path(folder))
        return "ws://127.0.0.1:9/devtools/browser/x"

    async def connect(url, open_timeout=10, headers=None):
        made.append(FakeCDP())
        return made[-1]

    monkeypatch.setattr(engine_module, "find_ws_url", ws_url)
    monkeypatch.setattr(engine_module.CDP, "connect", connect)
    engine = Engine(home=home, catalog=Catalog([], set()))
    fresh = None
    try:
        await engine.sandbox_start(chrome=True)
        save_place(home, Place("chrome", str(folders["chrome"]), "Default"))  # the user switches in Settings
        made[-1].closed = True  # the connection drops: the next start reconnects
        await engine.sandbox_start(chrome=True)
        assert asked == [folders["brave"], folders["brave"]]  # this session keeps its place
        fresh = Engine(home=home, catalog=Catalog([], set()))
        await fresh.sandbox_start(chrome=True)
        assert asked[-1] == folders["chrome"]  # a new session takes the new choice
    finally:
        await engine.close()
        if fresh is not None:
            await fresh.close()


async def test_a_session_the_app_cant_hold_connects_directly(monkeypatch, tmp_path):
    from ai_browser import engine as engine_module
    from fake_cdp import FakeCDP
    from test_grouping import App

    throwaway = tmp_path / "throwaway"
    throwaway.mkdir()
    monkeypatch.setenv("AIB_CHROME_DIR", str(throwaway))
    monkeypatch.delenv("AIB_BROWSER")
    app = App({"/agent-hello": {"place": None}})
    home = tmp_path / "home"
    (home / "app").mkdir(parents=True)
    port = app.url.rsplit(":", 1)[1]
    (home / "app" / "link.json").write_text(json.dumps({
        "events": app.url + "/agent-events", "session_token": "s", "pid": os.getpid(),
        "cdp": f"ws://127.0.0.1:{port}/cdp", "browser_dir": str(tmp_path / "brave")}), encoding="utf-8")
    connects = []

    async def connect(url, open_timeout=10, headers=None):
        connects.append((url, headers))
        return FakeCDP()

    monkeypatch.setattr(engine_module, "find_ws_url",
                        lambda folder, timeout=0: f"ws://127.0.0.1:9/devtools/browser/{Path(folder).name}")
    monkeypatch.setattr(engine_module.CDP, "connect", connect)
    engine = Engine(home=home, catalog=Catalog([], set()))
    try:
        text = (await engine.sandbox_start(chrome=True)).text
        assert connects == [("ws://127.0.0.1:9/devtools/browser/throwaway", None)]  # direct, never the relay
        hello = next(body for _, path, body, _ in app.requests if path == "/agent-hello")
        assert hello["place"] == {"browser": "", "profile": "Default"}
        assert "not through AI Browser" in text
    finally:
        await engine.close()
        app.stop()


async def test_no_tool_result_carries_a_profile_name_or_email(monkeypatch, tmp_path):
    from ai_browser import engine as engine_module
    from fake_cdp import FakeCDP
    from places_rig import write_local_state

    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    write_local_state(folder, {"profile": {"info_cache": {"Profile 7": {"name": "SECRET-NAME-9",
                                                                        "user_name": "secret@example.com",
                                                                        "gaia_name": "secret@example.com"}},
                                           "last_used": "Profile 7"}})
    monkeypatch.setenv("AIB_CHROME_DIR", str(folder))
    monkeypatch.setenv("AIB_CHROME_PROFILE", "Profile 7")
    monkeypatch.delenv("AIB_BROWSER")
    engine = Engine(home=tmp_path / "home", catalog=Catalog([], set()))
    try:
        texts = [(await engine.open("https://example.com")).text]  # the switch is off: the error names the browser
        monkeypatch.setattr(engine_module, "find_ws_url", lambda folder, timeout=0: "ws://127.0.0.1:9/x")

        async def connect(url, open_timeout=10, headers=None):
            return FakeCDP()

        monkeypatch.setattr(engine_module.CDP, "connect", connect)
        texts.append((await engine.sandbox_start(chrome=True)).text)  # the status line: no app here
        await engine.browser.open_worker()
        texts += engine.browser._download_notes()  # the fallback note
        for text in texts:
            assert "SECRET-NAME-9" not in text and "secret@example.com" not in text and "Profile 7" not in text, text
        assert any("the Brave profile the user used last" in text for text in texts[1:])  # what it says instead
    finally:
        await engine.close()


async def test_the_status_line_says_where_tabs_open(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from ai_browser.grouping import Placer
    from ai_browser.sandbox import SandboxInfo
    from ai_browser.workfs import WorkDir
    from test_grouping import FakeLink

    monkeypatch.setenv("AIB_CHROME_DIR", str(tmp_path / "BraveSoftware" / "Brave-Browser"))
    engine = Engine(home=tmp_path / "home", catalog=Catalog([], set()))
    engine.info = SandboxInfo("aib-chrome", "chrome", "", tmp_path / "w", False, False, chrome=True)
    engine.work = WorkDir(tmp_path / "w", engine.task_id)
    engine.browser = SimpleNamespace(mode="chrome")
    engine._placer = Placer(FakeLink(opens=True), name="Brave")
    placed = engine._status_text(await engine._placement())
    assert ("in the profile the user chose, where its watcher opens this session's tabs · only tabs this session "
            "opens, and tabs the user hands it · a tab group named after this task") in placed
    engine._placer = Placer(FakeLink(why="asleep"), name="Brave")
    assert ("only tabs this session opens, and tabs the user hands it · its tabs open in the Brave profile the user "
            "used last: the watcher in the chosen profile isn't connected") in engine._status_text(
                await engine._placement())
    engine._placer = Placer(None, name="Brave")
    assert "its tabs open in the Brave profile the user used last: ai-browser app isn't running" in \
        engine._status_text(await engine._placement())
```

(`Path`, `json` and `os` are imported at the top of `tests/test_engine.py`; add any that are missing.)

In `tests/test_chrome.py`, the session tests that pin today's placement words follow the new ones:
- `test_sandbox_start_chrome_opens_no_tab`: its expected line becomes `"only tabs this session opens, and tabs the
  user hands it · its tabs open in the Chrome profile the user used last: ai-browser app isn't running"`;
- `test_a_session_joins_the_running_app_and_says_goodbye` (as wave 2A left it): the expected `/agent-hello` body gains
  `"place": {"browser": "", "profile": "Default"}`; where it expects `"tab group 'Claude Code'"` from an app stand-in
  whose `/agent-status` has no `open`, it expects `"its tabs open in the Chrome profile the user used last: the
  watcher isn't in the chosen profile"` instead.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_engine.py -k "resolves_its_place or cant_hold or profile_name_or_email or says_where_tabs_open" -q -p no:randomly`

Expected: FAIL. The first test sees `asked[-1] == brave` for the fresh engine (today's code never reads
`settings.json`); the second finds no `place` in the hello; the third finds no "the Brave profile the user used
last"; the fourth sees today's "its tabs open in their own window" words.

- [ ] **Step 3: Give the engine its place**

In `src/ai_browser/engine.py`, import `places` (`from . import config, places, platforms`) and the grouping words
(`from .grouping import Placer, why_words`). Beside `BAD_BROWSER`:

```python
ONLY_TABS = "only tabs this session opens, and tabs the user hands it"
CHOSEN_LINE = "in the profile the user chose, where its watcher opens this session's tabs"
FALLBACK_LINE = "its tabs open in the {name} profile the user used last: "
```

In `Engine.__init__`, beside `self._placer`:

```python
        self._place = None  # this session's place (places.Place), fixed at its first browser call (Decision 3)
```

New method, and `_browser_name` follows it:

```python
    def _own_place(self):
        """This session's place: resolved once, at its first browser call, and kept for the process's life. An
        agent's env carries its own (place_env), which wins inside resolve; a switch in Settings never moves it."""
        if self._place is None:
            self._place = places.resolve(self.home)[0]
        return self._place

    def _browser_name(self) -> str:
        return browser_name(Path(self._own_place().user_data_dir))
```

In `_start_chrome` (and in wave 2A's `_route()` for its direct case), every `own_browser_dir()` becomes
`Path(self._own_place().user_data_dir)`, so a direct connection reads:

```python
                ws_url = await asyncio.to_thread(find_ws_url, Path(self._own_place().user_data_dir), 2)
```

and the Placer is made with the name and the place:

```python
            self._placer = Placer(self._link if agent else rediscover(), rediscover=rediscover,
                                  name=self._browser_name(), place=self._own_place())
```

In wave 2A's `_route()`, replace its step 2 (a session with a running app, which compares `AIB_CHROME_DIR` with
link.json's `browser_dir`) with the hello that carries the place. Keep wave 2A's step 1 (an app agent: always the
relay), its step 3 (no app) and its error texts as they are; the session's step 2 becomes:

```python
        place = self._own_place()
        link = AgentLink.discover(self.home, self.task_id)
        if link is not None and link.cdp:  # a running app: it says whether it can hold this session's browser
            answer = await link.hello(place)
            if answer is None:  # wave 2A: no answer to the hello
                raise ChromeError(APP_GONE if AgentLink.discover(self.home, self.task_id) is None else APP_SILENT)
            if answer.get("cut_off"):
                raise ChromeError(CUT_OFF_SESSION)
            if answer.get("place") == place.public() and isinstance(answer.get("cdp_token"), str):
                return "relay", link.cdp, answer["cdp_token"], Path(place.user_data_dir)
            self._not_through = True  # wave 2A's "not through AI Browser" status line
            return "direct", Path(place.user_data_dir)
```

`self._not_through` is the name this plan gives the flag wave 2A's status line reads for its "not through AI Browser:
AIB_CHROME_DIR names your {name}" case; use wave 2A's own flag. A relay session's browser name now comes from its
place, not link.json's `browser_dir` (the spec's "a session names the browser of its own place").

Replace `_placement` with:

```python
    async def _placement(self) -> str:
        """The status line's part after wave 2A's start: where this session's tabs open (the spec's Texts). It names the
        browser, never a profile."""
        if self._placer is None or self.browser is None or self.browser.mode != "chrome":
            return ""
        link, name = self._placer.link, self._browser_name()
        group = "tab group 'Claude Code'" if link is None or link.agent.startswith("cc-") else \
            "a tab group named after this task"
        if link is None:
            return f"{ONLY_TABS} · {FALLBACK_LINE.format(name=name)}{why_words('no_app')}"
        status = await link.status(GROUPS_TTL)
        if status.get("open"):
            return f"{CHOSEN_LINE} · {ONLY_TABS} · {group}"
        return f"{ONLY_TABS} · {FALLBACK_LINE.format(name=name)}{why_words(status.get('why') or 'no_watcher')}"
```

In `_status_text`'s chrome branch, keep wave 2A's start of the line (`browser: your {name}, through AI Browser's
connection`, or its "not through AI Browser" form) and put the placement after it, in place of the fixed "only tabs
…" words:

```python
            tail = placement or ONLY_TABS
            return (f"{start} · {tail}\n"  # `start` is wave 2A's start of the line, unchanged
                    f"work folder {self.work.sandbox_task} (on {platforms.this_computer()}: {self.work.host_task}; "
                    "shell and skill scripts run in a Docker sandbox)\n"
                    f"live view: {live}{unused}")
```

`RECONNECTED` and the errors keep naming the browser only.

- [ ] **Step 4: Run them, and the engine's other quick tests**

Run: `uv run pytest tests/test_engine.py -q -p no:randomly -m "not docker"`

Then: `uv run pytest tests/test_chrome.py -k "sandbox_start_chrome_opens_no_tab or joins_the_running_app" -q -p no:randomly`

Expected: PASS (the Chrome ones skip without Google Chrome).

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/engine.py tests/test_engine.py tests/test_chrome.py
git commit -m "feat: a session keeps its place for its life, goes through the relay only to it, and says where tabs open"
```

### Task 8: The agents' prompt names their browser, never a profile

**Files:**
- Modify: `src/ai_browser/app/bridge.py` (`BRAVE_PROMPT` becomes a template; new `browser_prompt`, `_browser_name`)
- Test: `tests/test_bridge.py`

**Interfaces:**
- Consumes: Task 3's `chrome.browser_name(folder)`, `chrome.own_browser_dir()`; wave A's hand-over sentence in
  `BRAVE_PROMPT` (kept word for word).
- Produces: `BRAVE_PROMPT` with `{name}` in place of every "Brave"; `browser_prompt(name: str) -> str`;
  `ClaudeBridge` passes `browser_prompt(<its AIB_CHROME_DIR's browser name>)`.

- [ ] **Step 1: Write the failing test**

In `tests/test_bridge.py` add:

```python
async def test_the_agents_prompt_names_its_browser_and_no_profile(fake_claude, tmp_path, monkeypatch):
    from ai_browser import browsers
    from ai_browser.app.bridge import BRAVE_PROMPT, ClaudeBridge, browser_prompt
    from places_rig import move_home

    move_home(monkeypatch, tmp_path)
    beta = browsers.data_dir(browsers.by_id("chrome-beta"))
    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    for folder, name in ((tmp_path / "BraveSoftware" / "Brave-Browser", "Brave"), (beta, "Chrome Beta"),
                         (tmp_path / "throwaway", "Chrome")):
        log.write_text("", encoding="utf-8")
        bridge = ClaudeBridge(tmp_path / "home", claude=runner, agent_id="a1",
                              env={"AIB_BROWSER": "chrome", "AIB_CHROME_DIR": str(folder),
                                   "AIB_CHROME_PROFILE": "Profile 7"})
        [event async for event in bridge.send("one")]
        argv = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
        prompt = argv[argv.index("--append-system-prompt") + 1]
        assert prompt == browser_prompt(name)
        assert f"You work in the user's everyday {name}, in the profile the user chose, in background" in " ".join(
            prompt.split())
        assert "Profile 7" not in prompt and (name == "Brave" or "Brave" not in prompt)
        await bridge.close()
    assert browser_prompt("Brave") == BRAVE_PROMPT.replace("{name}", "Brave")
```

In `test_agents_in_brave_get_the_brave_prompt`, give the bridge `"AIB_CHROME_DIR": str(tmp_path / "BraveSoftware" /
"Brave-Browser")` in its `env`, import `browser_prompt`, and compare the prompt with `browser_prompt("Brave")` instead
of `BRAVE_PROMPT`. Its word checks run on `" ".join(browser_prompt("Brave").split()).lower()`.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_bridge.py -k "prompt" -q -p no:randomly`

Expected: FAIL with `ImportError: cannot import name 'browser_prompt'`.

- [ ] **Step 3: Make the prompt a template**

In `src/ai_browser/app/bridge.py`:
- In `BRAVE_PROMPT`, change "You work in the user's everyday Brave, in background tabs:" to "You work in the user's
  everyday {name}, in the profile the user chose, in background tabs:" (re-wrap the string's lines as needed), and
  every other "Brave" in it to "{name}" (today one more: "your browser is the user's Brave"; wave A's sentence and
  wave B's edits may add others). The rest stays word for word, including wave A's hand-over sentence.
- Add, after `BRAVE_PROMPT`:

```python
def browser_prompt(name: str) -> str:
    """BRAVE_PROMPT for the agent's own browser ("Brave", "Chrome Beta"…). It names the browser, never a profile: a
    profile's name is often a person's (browser-profile-choice Decision 16)."""
    return BRAVE_PROMPT.replace("{name}", name)
```

- In `ClaudeBridge`, add:

```python
    def _browser_name(self) -> str:
        """The browser this agent's engine drives: its AIB_CHROME_DIR (place_env), named from wave A's table."""
        folder = self.env.get("AIB_CHROME_DIR")
        return browser_name(Path(folder)) if folder else browser_name(own_browser_dir())
```

  with `from ..chrome import browser_name, own_browser_dir`, and in `_command` pass
  `browser_prompt(self._browser_name())` where wave B left `BRAVE_PROMPT`.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_bridge.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/bridge.py tests/test_bridge.py
git commit -m "feat: an agent's prompt names its own browser and the profile the user chose, never the profile's name"
```

### Task 9: The relay: `assign` a tab the watcher opened, and close only an `open_tab` marker

**Files:**
- Modify: `src/ai_browser/app/cdprelay.py` (`Relay.__init__`, new `assign`, `note_marker`, `close_marker`)
- Modify: `tests/fake_brave.py` (`FakePort` records the targets it closed)
- Test: `tests/test_cdprelay.py`

**Interfaces:**
- Consumes (wave 2A, inside `Relay`): the target cache (`self.targets`: target → `{type, url, title, openerId,
  browserContextId}`), the grant table (target → `(identity, "own" | "popup")`), the clients of an identity with their
  discovery flag and the set of targets each was told about, the hook that fires `on_grant`, the queue a message is put
  on for a client, and the way the relay sends a command of its own upstream (pending `None`). This plan calls them
  `self.targets`, `self._grants`, `self._clients_of(identity)`, `client.discovery`, `client.announced`,
  `self._fire_grant(identity, target)`, `self._queue_to(client, message)` and `await self._own_command(method,
  params)`: use wave 2A's own spellings. Tests: wave 2A's `FakePort` (with wave A's `destroy(target)`) and
  `relay_client(relay, token)`.
- Produces:
  - `Relay.assign(target: str, identity: str) -> bool`;
  - `Relay.note_marker(marker: str) -> None`;
  - `async Relay.close_marker(target: str, marker: str) -> bool`;
  - `FakePort.closed_targets: list[str]`.

- [ ] **Step 1: Write the failing tests**

In `tests/fake_brave.py`, `FakePort.__init__` gains `self.closed_targets = []`, and its handler records each
`Target.closeTarget`'s `targetId` there (beside whatever wave 2A's handler already does for it):

```python
            elif method == "Target.closeTarget":
                self.closed_targets.append(message["params"]["targetId"])
```

In `tests/test_cdprelay.py` add:

```python
async def relay_on(tmp_path, pages):
    """A relay connected to a FakePort that lists `pages`: (relay, port, tokens)."""
    from ai_browser.app.cdprelay import Relay, Tokens
    from fake_brave import FakePort

    folder = tmp_path / "brave"
    port = FakePort(folder, pages=pages)
    await port.start()
    tokens = Tokens()
    relay = Relay(folder, tokens, every=0.1)
    await relay.start()
    assert await relay.open("start")
    return relay, port, tokens


async def next_message(ws, predicate, seconds=5):
    async def read():
        while True:
            message = json.loads(await ws.recv())
            if predicate(message):
                return message
    return await asyncio.wait_for(read(), seconds)


async def test_assign_grants_a_listed_target_and_announces_it_once(tmp_path):
    marker = "about:blank#aib-0123456789abcdef"
    relay, port, tokens = await relay_on(tmp_path, [{"target": "B1", "url": marker, "title": ""}])
    granted = []
    relay.on_grant(lambda identity, target: granted.append((identity, target)))
    try:
        async with relay_client(relay, tokens.mint("a1")) as a1:
            await a1.send(json.dumps({"id": 1, "method": "Target.setDiscoverTargets", "params": {"discover": True}}))
            await next_message(a1, lambda message: message.get("id") == 1)
            assert relay.assign("NOT-LISTED", "a1") is False and granted == []
            assert relay.assign("B1", "a1") is True
            assert granted == [("a1", "B1")] and relay.grants("a1", "B1") and relay.own_targets("a1") == ["B1"]
            created = await next_message(a1, lambda message: message.get("method") == "Target.targetCreated")
            assert created["params"]["targetInfo"]["targetId"] == "B1"
            assert relay.assign("B1", "a1") is True and granted == [("a1", "B1")]  # once
            await port.destroy("B1")
            gone = await next_message(a1, lambda message: message.get("method") == "Target.targetDestroyed")
            assert gone["params"]["targetId"] == "B1"  # its later events follow the targetCreated it got
    finally:
        await relay.close()
        await port.stop()


async def test_close_marker_closes_only_an_open_tab_marker(tmp_path):
    marker = "0123456789abcdef"
    relay, port, tokens = await relay_on(tmp_path, [
        {"target": "B1", "url": f"about:blank#aib-{marker}", "title": ""},
        {"target": "U1", "url": "https://mail.example/", "title": "SECRET-7f3a"},
        {"target": "B2", "url": "about:blank#aib-fedcba9876543210", "title": ""}])
    try:
        assert await relay.close_marker("B1", marker) is False  # a marker the app never sent
        relay.note_marker(marker)
        assert await relay.close_marker("U1", marker) is False  # a user's tab
        assert await relay.close_marker("B2", marker) is False  # another marker's tab
        assert await relay.close_marker("B1", marker) is True
        for _ in range(50):
            if port.closed_targets:
                break
            await asyncio.sleep(0.05)
        assert port.closed_targets == ["B1"]  # Brave never got a close for U1 or B2
    finally:
        await relay.close()
        await port.stop()
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_cdprelay.py -k "assign or close_marker" -q -p no:randomly`

Expected: FAIL with `AttributeError: 'Relay' object has no attribute 'assign'`.

- [ ] **Step 3: Write the three methods**

In `Relay.__init__`:

```python
        self._sent_markers: set[str] = set()  # markers the app sent in an open_tab this run (close_marker)
```

Add to `Relay`:

```python
    def assign(self, target: str, identity: str) -> bool:
        """A tab the watcher opened for `identity` (browser-profile-choice Decision 4) becomes its own: its engine may
        attach to it, and closing the agent closes it. False when the relay doesn't list the target. A client of that
        identity with discovery on is told of it once, as for a tab it created (wave 2A's Decision 3), so the engine's
        later targetInfoChanged and targetDestroyed for it follow a targetCreated."""
        info = self.targets.get(target)
        if info is None:
            return False
        if self._grants.get(target) != (identity, "own"):
            self._grants[target] = (identity, "own")
            self._fire_grant(identity, target)
        for client in self._clients_of(identity):
            if client.discovery and target not in client.announced:
                client.announced.add(target)
                self._queue_to(client, {"method": "Target.targetCreated",
                                        "params": {"targetInfo": {**info, "targetId": target}}})
        return True

    def note_marker(self, marker: str) -> None:
        """The app sent this marker in an open_tab: a tab at it may be closed by close_marker, whoever owns it."""
        self._sent_markers.add(marker)

    async def close_marker(self, target: str, marker: str) -> bool:
        """The app's client closes a blank open_tab tab nobody uses: one whose answer came after its wait, or one that
        opened in the wrong profile (Decision 4). Only a target the relay lists at about:blank#aib-<marker>, for a
        marker the app sent this run. Wave 2A's rule stays for every other tab: the app never closes a tab nobody owns."""
        info = self.targets.get(target)
        if marker not in self._sent_markers or info is None or info.get("url") != f"about:blank#aib-{marker}":
            return False
        await self._own_command("Target.closeTarget", {"targetId": target})
        self._grants.pop(target, None)
        return True
```

If wave 2A keeps a target's `targetId` inside its cached info already, `{**info, "targetId": target}` leaves it as it
is.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_cdprelay.py -q -p no:randomly`

Expected: PASS, wave 2A's tests included (the drift test is unchanged: no new CDP method is sent).

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/cdprelay.py tests/fake_brave.py tests/test_cdprelay.py
git commit -m "feat: the relay gives a tab the watcher opened to its agent alone, and closes only a stray open_tab blank tab"
```

### Task 10: `GroupKeeper.open`: one `open_tab`, answered by its own `opened_tab`, never a hang

**Files:**
- Modify: `src/ai_browser/app/groups.py`
- Test: `tests/test_groups.py`

**Interfaces:**
- Consumes: today's `GroupKeeper(send_to_watcher, on_change)`, `watcher_changed`, `caps_from`.
- Produces:
  - `OPEN_WAIT = 2.5`;
  - `caps` gains `"open": bool`; `can_open() -> bool`;
  - `async open(marker, key, title, color, wait=OPEN_WAIT) -> dict`: `{"ok": True, "tab": int, "window": int | None,
    "group": int | None, "new_window": bool}` or `{"ok": False, "reason": "no_watcher" | "refused" | "timeout"}`;
  - `opened(message)`: the copy's `opened_tab`;
  - `late: Callable[[str], None] | None`: called with the marker of an `ok` answer that came after its wait.

- [ ] **Step 1: Write the failing tests**

In `tests/test_groups.py` add (`keeper_on()` there today sends `watcher_caps` without `open`):

```python
def opener_on():
    from ai_browser.app.groups import GroupKeeper

    sent = []
    keeper = GroupKeeper(lambda message: sent.append(message) or True)
    keeper.watcher_changed(True)
    keeper.caps_from({"type": "watcher_caps", "groups": True, "open": True})
    return keeper, sent


async def test_open_tab_is_answered_by_its_own_request():
    keeper, sent = opener_on()
    first = asyncio.ensure_future(keeper.open("a" * 16, "a1", "Fix the footer", "blue"))
    second = asyncio.ensure_future(keeper.open("b" * 16, "a2", "Check prices", "green"))
    await asyncio.sleep(0.05)
    assert [(m["type"], m["request"], m["marker"], m["key"], m["title"], m["color"]) for m in sent] == [
        ("open_tab", "o1", "a" * 16, "a1", "Fix the footer", "blue"),
        ("open_tab", "o2", "b" * 16, "a2", "Check prices", "green")]
    assert all("url" not in message for message in sent)  # the watcher builds the address itself
    keeper.opened({"type": "opened_tab", "request": "o2", "ok": True, "tab": 22, "window": 3, "group": 9,
                   "new_window": True})
    keeper.opened({"type": "opened_tab", "request": "o1", "ok": False, "reason": "invalid"})
    assert await second == {"ok": True, "tab": 22, "window": 3, "group": 9, "new_window": True}
    assert await first == {"ok": False, "reason": "refused"}


async def test_a_late_open_answer_closes_its_tab():
    keeper, _ = opener_on()
    late = []
    keeper.late = late.append
    assert await keeper.open("c" * 16, "a1", "Fix", "blue", wait=0.2) == {"ok": False, "reason": "timeout"}
    keeper.opened({"type": "opened_tab", "request": "o1", "ok": True, "tab": 5, "window": 1, "group": None,
                   "new_window": False})
    assert late == ["c" * 16]
    keeper.opened({"type": "opened_tab", "request": "o1", "ok": True, "tab": 5})  # never twice
    keeper.opened({"type": "opened_tab", "request": "o9", "ok": True, "tab": 6})  # nobody asked
    assert late == ["c" * 16]


async def test_caps_say_whether_a_watcher_can_open_tabs():
    from ai_browser.app.groups import GroupKeeper

    sent = []
    keeper = GroupKeeper(lambda message: sent.append(message) or True)
    keeper.watcher_changed(True)
    keeper.caps_from({"groups": True})  # a watcher from before this wave
    assert keeper.available() == "on" and not keeper.can_open()
    assert await keeper.open("d" * 16, "a1", "Fix", "blue") == {"ok": False, "reason": "refused"} and sent == []
    keeper.caps_from({"groups": True, "open": True})
    assert keeper.can_open()
    keeper.watcher_changed(False)
    assert not keeper.can_open()
    assert await keeper.open("d" * 16, "a1", "Fix", "blue") == {"ok": False, "reason": "no_watcher"}


async def test_the_watcher_leaving_ends_a_waiting_open_at_once():  # Review Focus 2
    keeper, _ = opener_on()
    waiting = asyncio.ensure_future(keeper.open("e" * 16, "a1", "Fix", "blue"))
    await asyncio.sleep(0.05)
    started = time.monotonic()
    keeper.watcher_changed(False)  # the watcher reloads itself with a new build
    assert await waiting == {"ok": False, "reason": "no_watcher"} and time.monotonic() - started < 0.3
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_groups.py -q -p no:randomly`

Expected: FAIL with `AttributeError: 'GroupKeeper' object has no attribute 'open'`.

- [ ] **Step 3: Write `open`**

In `src/ai_browser/app/groups.py`, the module docstring gains: "Each watcher copy's connection has its own keeper
(browser-profile-choice Decision 9). The app may also ask a copy to open a blank tab at a secret marker (`open_tab` /
`opened_tab`), for an agent in that copy's profile." Then:

```python
OPEN_WAIT = 2.5  # seconds for the copy's opened_tab and the target together (the engine waits ENGINE_OPEN_WAIT, 3 s)
```

In `__init__`:

```python
        self._opening: dict[str, tuple[asyncio.Future, str]] = {}  # open_tab request -> (its answer, its marker)
        self._late: dict[str, str] = {}  # requests whose wait ended -> their markers
        self.late: Callable[[str], None] | None = None  # set by the app: close the blank tab of a late answer
```

`watcher_changed` ends a waiting open too:

```python
    def watcher_changed(self, connected: bool) -> None:
        """The watcher said hello (True) or went away (False): a claim or an open still waiting ends at once."""
        self.connected, self.caps = connected, None
        if not connected:
            for future in self._waiting.values():
                if not future.done():
                    future.set_result({"grouped": False, "reason": "no_watcher"})
            for future, _ in self._opening.values():
                if not future.done():
                    future.set_result({"ok": False, "reason": "no_watcher"})
        self._changed()

    def caps_from(self, message: dict) -> None:
        self.caps = {"groups": message.get("groups") is True, "open": message.get("open") is True}
        self._changed()

    def can_open(self) -> bool:
        """A copy from before this wave never says `open`: it can't open tabs (it reloads itself within a minute)."""
        return self.connected and self.caps is not None and self.caps["open"]

    async def open(self, marker: str, key: str, title: str, color: str, wait: float = OPEN_WAIT) -> dict:
        """Ask this copy to open a blank background tab at about:blank#aib-<marker> in the agent's group (it builds the
        address itself; no address is ever sent). Its answer, or why not."""
        if not self.connected:
            return {"ok": False, "reason": "no_watcher"}
        if not self.can_open():
            return {"ok": False, "reason": "refused"}
        self._seq += 1
        request = f"o{self._seq}"
        future = asyncio.get_running_loop().create_future()
        self._opening[request] = (future, marker)
        try:
            if not self.send({"type": "open_tab", "request": request, "marker": marker, "key": key, "title": title,
                              "color": color}):
                return {"ok": False, "reason": "no_watcher"}
            return await asyncio.wait_for(asyncio.shield(future), wait)
        except TimeoutError:
            self._late[request] = marker
            return {"ok": False, "reason": "timeout"}
        finally:
            self._opening.pop(request, None)

    def opened(self, message: dict) -> None:
        """The copy's opened_tab: the answer to its own request; an `ok` answer after its wait goes to `late`."""
        request = str(message.get("request", ""))
        entry = self._opening.get(request)
        if entry is None:
            marker = self._late.pop(request, None)
            if marker is not None and message.get("ok") is True and self.late is not None:
                self.late(marker)
            return
        future, _ = entry
        if future.done():
            return
        tab = message.get("tab")
        if message.get("ok") is True and isinstance(tab, int):
            window, group = message.get("window"), message.get("group")
            future.set_result({"ok": True, "tab": tab, "window": window if isinstance(window, int) else None,
                               "group": group if isinstance(group, int) else None,
                               "new_window": message.get("new_window") is True})
        else:
            future.set_result({"ok": False, "reason": "refused"})
```

(import `Callable` is already there.)

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_groups.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/groups.py tests/test_groups.py
git commit -m "feat: a watcher copy can be asked to open one blank tab at a marker, answered by its own request"
```

### Task 11: Watcher copies: one folder per profile, all brought up to date at start

**Files:**
- Modify: `src/ai_browser/brain/watcher.py` (`prepare_watcher(..., folder=None)`)
- Create: `src/ai_browser/app/watchers.py` (`slug`, `NO_SLUG`, `WatcherCopies`; Task 14 adds the live connections)
- Test: `tests/test_watcher_copies.py` (new)

**Interfaces:**
- Consumes: wave B's `extension_id.extension_id_for(folder, system=None)`; today's `sync_folder`, `write_atomic`.
- Produces:
  - `prepare_watcher(home, server_url, token, folder=None) -> tuple[Path, str]`;
  - `app/watchers.py`: `COPIES = "watchers"`, `SLUG` (a compiled `^[a-z0-9-]{1,60}$`), `NO_SLUG`,
    `slug(browser, profile) -> str`;
  - `class WatcherCopies(home)`: `primary: Path`, `root: Path`, `build: str`, `folder_for(browser, profile) -> Path`,
    `existing() -> list[Path]`, `prepare_all(url, token) -> dict[str, Path]` (id → folder, primary first),
    `make(browser, profile, url, token, profiles=()) -> Path` (raises `ValueError(NO_SLUG)`),
    `folders() -> dict[str, Path]`, `ids() -> set[str]`, `name_of(extension_id) -> str | None` (`"primary"` or the
    slug).

- [ ] **Step 1: Write the failing tests**

`tests/test_watcher_copies.py`:

```python
"""One watcher copy per profile (browser-profile-choice Decisions 7 and 8): its own folder, so its own extension id,
brought up to date at every start; placed by its profile's files and its worker's context."""

import json
import shutil

import pytest

from conftest import file_mode


def test_a_copy_per_profile_has_its_own_folder_and_id(tmp_path):
    from ai_browser.app.watchers import WatcherCopies
    from ai_browser.extension_id import extension_id_for

    copies = WatcherCopies(tmp_path / "home")
    folder = copies.folder_for("brave", "Profile 1")
    assert folder == tmp_path / "home" / "app" / "watchers" / "brave-profile-1"
    assert copies.folder_for("brave", "Profile 1") == folder  # stable: the id never changes
    assert extension_id_for(folder) != extension_id_for(copies.primary)
    assert copies.primary == tmp_path / "home" / "app" / "watcher" and copies.primary not in folder.parents


def test_updating_the_primary_never_deletes_a_copy(tmp_path):
    from ai_browser.app.watchers import WatcherCopies

    copies = WatcherCopies(tmp_path / "home")
    copies.prepare_all("http://127.0.0.1:8792", "tok")
    made = copies.make("brave", "Profile 1", "http://127.0.0.1:8792", "tok", ["Default", "Profile 1"])
    copies.prepare_all("http://127.0.0.1:8793", "tok2")  # the next start updates the primary in place
    assert (made / "manifest.json").is_file() and (made / "worker.js").is_file()
    assert json.loads((made / "config.json").read_text(encoding="utf-8"))["server"] == "http://127.0.0.1:8793"


def test_every_copy_is_brought_up_to_date_at_start(tmp_path):
    from ai_browser.app.watchers import WatcherCopies
    from ai_browser.extension_id import extension_id_for

    home = tmp_path / "home"
    copies = WatcherCopies(home)
    for name in ("brave-profile-1", "chrome-default"):
        (home / "app" / "watchers" / name).mkdir(parents=True)
    found = copies.prepare_all("http://127.0.0.1:8792", "tok")
    assert list(found.values())[0] == copies.primary
    assert set(found) == {extension_id_for(folder) for folder in found.values()} == copies.ids()
    for folder in found.values():
        assert (folder / "build.js").read_text(encoding="utf-8") == f'export const BUILD = "{copies.build}";\n'
        config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
        assert config == {"server": "http://127.0.0.1:8792", "token": "tok"}
        assert file_mode(folder / "config.json") in (None, 0o600)
    names = {copies.name_of(extension_id) for extension_id in found}
    assert names == {"primary", "brave-profile-1", "chrome-default"} and copies.name_of("nope") is None


@pytest.mark.parametrize("system", [None, "win32"])
def test_slugs_are_stable_and_never_shared(tmp_path, system):
    from ai_browser.app.watchers import NO_SLUG, WatcherCopies, slug
    from ai_browser.extension_id import extension_id_for

    assert slug("brave", "Profile 1") == "brave-profile-1" and slug("chrome-beta", "Default") == "chrome-beta-default"
    assert slug("brave", "Ünïcode/../x") == "brave--n-code----x" and len(slug("brave", "p" * 99)) == 60
    copies = WatcherCopies(tmp_path / "home")
    one = copies.folder_for("brave", "Profile 1")
    assert extension_id_for(one, system=system) != extension_id_for(copies.primary, system=system)
    listed = ["Default", "Profile 1", "profile-1"]  # two folder names, one slug
    copies.make("brave", "Profile 1", "http://127.0.0.1:8792", "tok", listed)
    with pytest.raises(ValueError, match=f"^{NO_SLUG}$"):
        copies.make("brave", "profile-1", "http://127.0.0.1:8792", "tok", listed)
    assert [folder.name for folder in copies.existing()] == ["brave-profile-1"]  # the second made nothing


def test_a_stray_or_deleted_copy_never_stops_the_start(tmp_path):  # Review Focus 5
    from ai_browser.app.watchers import WatcherCopies

    home = tmp_path / "home"
    root = home / "app" / "watchers"
    (root / "Junk Folder").mkdir(parents=True)  # not a slug: never a copy, never an origin
    (root / "notes.txt").write_text("mine", encoding="utf-8")
    (root / "brave-profile-2").mkdir()
    copies = WatcherCopies(home)
    copies.prepare_all("http://127.0.0.1:8792", "tok")
    assert [folder.name for folder in copies.existing()] == ["brave-profile-2"]
    assert (root / "notes.txt").read_text(encoding="utf-8") == "mine" and not (root / "Junk Folder" / "build.js").exists()
    shutil.rmtree(root / "brave-profile-2")  # the user deleted a copy
    assert len(copies.prepare_all("http://127.0.0.1:8792", "tok")) == 1  # the primary alone, and no error
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_watcher_copies.py -q -p no:randomly`

Expected: FAIL with `ModuleNotFoundError: No module named 'ai_browser.app.watchers'`.

- [ ] **Step 3: Write the copies**

In `src/ai_browser/brain/watcher.py`, the docstring gains: "Each other profile has its own copy, in its own folder
(browser-profile-choice Decision 7): `prepare_watcher(..., folder=)` makes or updates it with the same files, so the
same build." and `prepare_watcher` becomes:

```python
def prepare_watcher(home: Path, server_url: str, token: str, folder: Path | None = None) -> tuple[Path, str]:
    """A watcher folder, current, with this run's address and token; returns (folder, build). Without `folder` it is the
    primary copy at <home>/app/watcher; with it, one profile's own copy."""
    folder = Path(folder) if folder is not None else Path(home) / "app" / "watcher"
    files = _sources()
    digest = hashlib.sha256()
    for name, data in files.items():
        digest.update(name.encode("utf-8") + b"\0" + data + b"\0")
    build = digest.hexdigest()[:12]
    files["build.js"] = f'export const BUILD = "{build}";\n'.encode("utf-8")
    sync_folder(folder, files, keep={"config.json"})
    write_atomic(folder / "config.json", json.dumps({"server": server_url, "token": token}).encode("utf-8"), 0o600)
    return folder, build
```

(`_sources()` reads wave B's `SHARED_SOURCE`, unchanged.)

Create `src/ai_browser/app/watchers.py`:

```python
"""The watcher's copies and their live connections (browser-profile-choice Decisions 7, 8 and 9).

An extension can't tell which profile it runs in, and one folder has one id everywhere (in two profiles, even in
Brave and Chrome), so each profile agents use gets its own copy: the primary at <home>/app/watcher, where the user
loaded it first, and each other one at <home>/app/watchers/<slug>. A copy is placed by its profile's files and its
worker's browser context, never by a guess."""

from __future__ import annotations

import re
from pathlib import Path

from ..brain.watcher import prepare_watcher
from ..extension_id import extension_id_for

COPIES = "watchers"
SLUG = re.compile(r"^[a-z0-9-]{1,60}$")
NO_SLUG = "AI Browser can't give this profile a watcher folder of its own: please report this"


def slug(browser: str, profile: str) -> str:
    """A copy's folder name: the browser id and the profile folder, lower-cased, anything outside [a-z0-9] turned into
    "-", at most 60 characters. It never changes, so the copy's extension id never changes."""
    return re.sub(r"[^a-z0-9]", "-", f"{browser}-{profile}".lower())[:60]


class WatcherCopies:
    """The copies' folders. Updating the primary never touches a copy: they are outside its folder, which sync_folder
    keeps to its own files."""

    def __init__(self, home: Path):
        self.home = Path(home)
        self.primary = self.home / "app" / "watcher"
        self.root = self.home / "app" / COPIES
        self.build = ""

    def folder_for(self, browser: str, profile: str) -> Path:
        return self.root / slug(browser, profile)

    def existing(self) -> list[Path]:
        """The copies on disk: folders under <home>/app/watchers named like a slug. Anything else there is left
        alone, and gets no origin."""
        try:
            entries = sorted(self.root.iterdir())
        except OSError:
            return []
        return [entry for entry in entries if entry.is_dir() and SLUG.fullmatch(entry.name)]

    def prepare_all(self, url: str, token: str) -> dict[str, Path]:
        """At every start: the primary and every copy brought up to date (files, build.js, config.json with this run's
        address and token). Returns extension id -> folder, the primary first."""
        folder, self.build = prepare_watcher(self.home, url, token)
        found = {extension_id_for(folder): folder}
        for copy in self.existing():
            prepare_watcher(self.home, url, token, folder=copy)
            found[extension_id_for(copy)] = copy
        return found

    def make(self, browser: str, profile: str, url: str, token: str, profiles=()) -> Path:
        """Set it up: that profile's own copy, made or brought up to date. `profiles` are the browser's profile
        folders in its own order: when two would share one slug, only the first gets it, and the second makes
        nothing (ValueError)."""
        mine = slug(browser, profile)
        first = next((name for name in profiles if slug(browser, name) == mine), profile)
        if first != profile:
            raise ValueError(NO_SLUG)
        folder = self.folder_for(browser, profile)
        prepare_watcher(self.home, url, token, folder=folder)
        return folder

    def folders(self) -> dict[str, Path]:
        """Extension id -> folder, for every copy (the mapping wave A's watcher_places and detect take)."""
        return {extension_id_for(folder): folder for folder in [self.primary, *self.existing()]}

    def ids(self) -> set[str]:
        return set(self.folders())

    def name_of(self, extension_id: str) -> str | None:
        """"primary", or a copy's slug, for one of our ids; None for any other."""
        folder = self.folders().get(extension_id)
        if folder is None:
            return None
        return "primary" if folder == self.primary else folder.name
```

- [ ] **Step 4: Run them, and the watcher's own build test**

Run: `uv run pytest tests/test_watcher_copies.py -q -p no:randomly`

Then: `uv run pytest tests/test_watcher.py -k "build or shared_files or byte" -q -p no:randomly`

Expected: PASS (the second run's Chrome tests skip without Google Chrome).

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/brain/watcher.py src/ai_browser/app/watchers.py tests/test_watcher_copies.py
git commit -m "feat: a watcher copy per profile, in its own folder, all brought up to date at start"
```

### Task 12: `InstanceLink`: `BraveLink` renamed, its watcher ids a set, its tab list on the chosen profile

**Files:**
- Modify: `src/ai_browser/app/bravelink.py`
- Modify: `tests/test_bravelink.py` (two new tests; wave 1B's tests that expect `"watcher"` follow `"chosen"`)

**Interfaces:**
- Consumes (the merged `BraveLink`): wave 1B's `watcher_id`, its remembered worker contexts (`_watcher_contexts`),
  `agents_context()`, `scope()`, `tabs()`, `_changed()`, its `TabWatch` (`self._watch`, with `pages()`,
  `worker_contexts(id)`, `default_context`); wave 2A's `relay`, `start()`, `connect(why, identity)`, `close()`;
  wave B's `app_origin`; wave A's `FakePort` with page contexts, service workers, `set_default`, `destroy`.
- Produces (`src/ai_browser/app/bravelink.py`):
  - `class InstanceLink(folder, watcher_ids=(), allow_wait=ALLOW_WAIT, every=SWITCH_EVERY, tokens=None,
    app_origin="", watcher_id="")`; `BraveLink = InstanceLink`;
  - `watcher_ids: set[str]`;
  - `chosen: str | None` (the profile folder whose tabs are listed; set by `InstanceLinks`) and
    `chosen_context: str | None` (that profile's copy's context; set by `Watchers`), both properties whose setter
    re-filters the list at once; setting another `chosen` clears `chosen_context`;
  - `agents_context() -> (chosen_context, "chosen")`, else wave 1B's `"last_used"` and `"none"`;
  - `worker_contexts(extension_id) -> set[str]` (remembered for the connection's life), `default_context`;
  - `context_of(target) -> str | None`, `targets_showing(url) -> list[str]`, `lists(target) -> bool`, from
    `TabWatch.pages()`; none of them attaches to anything.

- [ ] **Step 1: Write the failing tests**

In `tests/test_bravelink.py` (its `FakePort` is wave 2A's, in `tests/fake_brave.py`, with wave 1B's contexts and
service workers; if the merged `FakePort` takes its workers another way than `workers=[…]`, use that way):

```python
async def test_two_watcher_ids_and_the_chosen_context(tmp_path):
    from ai_browser.app.bravelink import BraveLink, InstanceLink
    from fake_brave import FakePort

    assert BraveLink is InstanceLink
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=[{"target": "U1", "url": "https://mail.example/", "title": "Mail", "context": "C1"},
                                   {"target": "U2", "url": "https://bank.example/", "title": "SECRET-P",
                                    "context": "C2"}],
                    workers=[{"target": "W1", "url": "chrome-extension://e1/worker.js", "context": "C1"},
                             {"target": "W2", "url": "chrome-extension://e2/worker.js", "context": "C2"}])
    port.set_default("C2")
    await port.start()
    link = InstanceLink(folder, watcher_ids={"e1", "e2"}, every=0.1)
    await link.start()
    await link.connect()
    try:
        assert await until(lambda: link.worker_contexts("e1") == {"C1"} and link.worker_contexts("e2") == {"C2"})
        assert link.default_context == "C2" and link.worker_contexts("e3") == set()
        assert link.agents_context() == ("C2", "last_used") and link.scope()["profile"] == "last_used"
        link.chosen = "Default"
        link.chosen_context = "C1"  # as Watchers does once the Default copy's worker is seen
        assert link.agents_context() == ("C1", "chosen")
        assert [tab["target"] for tab in link.tabs()] == ["U1"] and link.scope() == {"profile": "chosen",
                                                                                    "elsewhere": 1}
        link.chosen = "Profile 1"  # another profile of the same browser: its context isn't known yet
        assert link.chosen_context is None and link.agents_context() == ("C2", "last_used")
        await port.destroy("W1")  # a sleeping worker drops out of the list...
        await asyncio.sleep(0.3)
        assert link.worker_contexts("e1") == {"C1"}  # ...and is remembered for the connection's life
    finally:
        await link.close()
        await port.stop()


async def test_context_of_and_targets_showing_read_the_list_and_attach_nothing(tmp_path):
    from ai_browser.app.bravelink import InstanceLink
    from fake_brave import FakePort

    marker = "about:blank#aib-0123456789abcdef"
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=[{"target": "B1", "url": marker, "title": "", "context": "C1"},
                                   {"target": "U1", "url": "https://mail.example/", "title": "Mail", "context": "C2"}])
    await port.start()
    link = InstanceLink(folder, every=0.1)
    await link.start()
    await link.connect()
    try:
        assert await until(lambda: link.lists("B1") and link.lists("U1"))
        assert link.context_of("B1") == "C1" and link.context_of("nope") is None and not link.lists("nope")
        assert link.targets_showing(marker) == ["B1"] and link.targets_showing("about:blank") == []
        assert port.attached == []  # reads of the list only
    finally:
        await link.close()
        await port.stop()
```

Wave 1B's tests that expect `"watcher"` follow this wave (its tests 12, 13, 14 and 20, by name in
`tests/test_bravelink.py` and `tests/test_watcher.py`):
- `test_only_the_agents_profile_is_listed_and_the_rest_is_counted`: after the watcher's worker shows in W, set
  `link.chosen = "Default"` and `link.chosen_context = "W"` (as `Watchers` does); expect
  `scope() == {"profile": "chosen", "elsewhere": 2}`;
- `test_without_the_watcher_the_profile_used_last_is_listed`: unchanged in what it expects ("last_used"); its "a
  watcher worker in two contexts" case leaves `chosen_context` unset, and so still gives "last_used";
- `test_the_watchers_profile_outlives_its_sleeping_worker_but_not_the_connection`: with `chosen_context = "W"` set,
  `destroy(worker)` keeps "chosen"; after Brave restarts (`port.stop()`, a new port, `connect()`), `chosen_context` is
  `None` again and the scope is "last_used" until it is set again;
- `test_the_watchers_profile_is_found_from_its_worker` (`tests/test_watcher.py`): the link (made with the fixture's id
  in `watcher_ids`) reports `worker_contexts(<id>)` as one context; with `chosen_context` set to it,
  `agents_context()[1] == "chosen"`.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_bravelink.py -q -p no:randomly`

Expected: FAIL. `InstanceLink` doesn't exist; the updated wave 1B tests expect "chosen", which nothing produces.

- [ ] **Step 3: Rename the link and give it the chosen profile**

In `src/ai_browser/app/bravelink.py`:
- The class `BraveLink` becomes `InstanceLink`, and after it: `BraveLink = InstanceLink  # its earlier name (tests)`.
  Its docstring begins: "One browser instance agents use (browser-profile-choice Decision 11): its relay upstream
  (wave 2A), the tab list on the chosen profile, Watch, thumbnails of the AI's tabs, closing an agent's tabs."
- `__init__` takes `watcher_ids=()` in place of wave 1B's `watcher_id: str = ""`, and keeps `watcher_id` as a last
  keyword so wave 1B's tests still build it. Its new fields:

```python
        self.watcher_ids: set[str] = set(watcher_ids) | ({watcher_id} if watcher_id else set())
        self._seen: dict[str, set[str]] = {}  # extension id -> worker contexts seen on this connection
        self._chosen: str | None = None
        self._chosen_context: str | None = None
        # wave 1B's `_seen_on` (the TabWatch those contexts were seen on) and `_last` stay as wave 1B made them
```

- Wave 1B's `_watcher_contexts` goes. Wave 1B forgets it when the connection changes (its `_seen_on`, the `TabWatch`
  those contexts were seen on); keep that rule with one helper, called first in `agents_context()`,
  `worker_contexts()` and `_changed()`:

```python
    def _fresh(self) -> None:
        """A new connection (or none): what the last one saw is forgotten (a context id belongs to one browser run),
        and every copy's worker seen now is remembered."""
        if self._watch is not self._seen_on:
            self._seen_on, self._seen, self._chosen_context = self._watch, {}, None
        if self._watch is not None:
            for extension_id in self.watcher_ids:
                self._seen.setdefault(extension_id, set()).update(self._watch.worker_contexts(extension_id))
```

- Replace `agents_context()` and add the new members:

```python
    def agents_context(self) -> tuple[str | None, str]:
        """(context, source) of the profile whose tabs are listed (Decision 10): the chosen profile's, from the copy
        connected there ("chosen"); else the profile the browser used last ("last_used"), where agents' tabs fall
        back to; else none, and no tab of the user's is listed. Context ids never leave this link."""
        self._fresh()
        if self._chosen_context is not None:
            return self._chosen_context, "chosen"
        default = self.default_context
        if default is not None:
            return default, "last_used"
        return None, "none"

    @property
    def chosen(self) -> str | None:
        return self._chosen

    @chosen.setter
    def chosen(self, profile: str | None) -> None:
        if profile != self._chosen:
            self._chosen = profile
            self._chosen_context = None  # it was the other profile's
            self._changed()

    @property
    def chosen_context(self) -> str | None:
        return self._chosen_context

    @chosen_context.setter
    def chosen_context(self, context: str | None) -> None:
        self._fresh()  # first, so a connection that just changed doesn't wipe the value set now
        if context != self._chosen_context:
            self._chosen_context = context
            self._changed()  # the list re-filters at once

    @property
    def default_context(self) -> str | None:
        return self._watch.default_context if self._watch is not None else None

    def worker_contexts(self, extension_id: str) -> set[str]:
        """The contexts a watcher copy's worker was seen in on this connection: a sleeping worker drops out of the
        target list, so they are remembered until the connection ends."""
        self._fresh()
        if self._watch is None or not extension_id:
            return set()
        seen = self._seen.setdefault(extension_id, set())
        seen.update(self._watch.worker_contexts(extension_id))
        return set(seen)

    def _pages(self) -> list[dict]:
        return self._watch.pages() if self._watch is not None else []

    def lists(self, target: str) -> bool:
        return any(page["target"] == target for page in self._pages())

    def context_of(self, target: str) -> str | None:
        """Which browser context (profile, or private window) a page is in: from the list, attaching to nothing."""
        return next((page.get("context") for page in self._pages() if page["target"] == target), None)

    def targets_showing(self, url: str) -> list[str]:
        """The pages whose address is exactly `url` (an open_tab marker, wave D's side chat)."""
        return [page["target"] for page in self._pages() if page["url"] == url]
```

  If wave 1B already made `default_context` a property here, keep one of the two.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_bravelink.py -q -p no:randomly`

Then: `uv run pytest tests/test_watcher.py -k "profile_is_found_from_its_worker" -q -p no:randomly`

Expected: PASS (the second skips without Google Chrome).

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/bravelink.py tests/test_bravelink.py tests/test_watcher.py
git commit -m "feat: InstanceLink, one browser's link: its copies' worker contexts and the chosen profile's tab list"
```

### Task 13: `InstanceLinks`: one link per browser in use, connected only after the user acts

**Files:**
- Create: `src/ai_browser/app/links.py`
- Modify: `tests/fake_brave.py` (`FakeBrave` as a link: folder, contexts, start, close, a gated connect)
- Test: `tests/test_links.py` (new)

**Interfaces:**
- Consumes: Task 12's `InstanceLink` (`state`, `name`, `relay`, `start()`, `connect(why, identity)`, `close()`,
  `tabs()`, `scope()`, `chosen`, `chosen_context`, `context_of`, `lists`, `targets_showing`, `set_owner`, `forget`,
  `release`, `mark_brain`, `watch`, `close_targets`, `thumbnail`, `page_text`, `on_change`, `on_state`); Task 2's
  `Place`.
- Produces (`src/ai_browser/app/links.py`):
  - `CONNECTABLE = {"ready", "lost", "refused", "asking"}`;
  - `class InstanceLinks(make_link: Callable[[Place], InstanceLink])` with `current: Place | None`;
  - `set_current(place) -> bool` (True when the browser changed); `link_for(place)`, `at(instance)`,
    `all() -> list[tuple[Place, InstanceLink]]`, `ensure(place)` (makes and starts a link, connects nothing),
    `async started(place)` (waits for that link's first look at its switch);
  - `async connect(place, why="connect", identity="")` (single-flight per link; nothing for a browser nobody uses,
    for `off` or `connected`);
  - `in_use(instance) -> bool`, `async prune(live: set[str])`, `async close()`;
  - `context_of(place) -> str | None`, `located(target) -> tuple[str, str] | None` (instance, context);
  - `tabs() -> tuple[list[dict], dict]` (rows and `tab_scope`): rows owned outside the current place carry
    `"place": {"label", "color"}`; an agent's or a session's row carries `"other_profile": True` when its place's copy
    is connected and the tab's context isn't that copy's;
  - routed to the link that lists the target: `watch`, `close_targets`, `thumbnail`, `page_text`, `set_owner`;
    `forget` and `release` on every link; `mark_brain` on the current one;
  - `on_change(cb())`, `on_state(cb(place, state))`, `on_link(cb(place, link))`;
  - hooks the app sets: `users() -> set[str]`, `owner_place(owner) -> Place | None`, `describe(place) -> dict`,
    `place_context(place) -> str | None`.

- [ ] **Step 1: Write the failing tests**

In `tests/fake_brave.py`, `FakeBrave` becomes a link `InstanceLinks` can hold. Keep everything waves 1B and 2A gave it
(its `relay`, its records of connects, `scope()`), and add:

```python
    def __init__(self, pages=(), state="connected", folder=None, default_context="C0"):
        # (wave 2A's and 1B's fields stay; these are wave C's)
        self.folder = Path(folder) if folder is not None else Path("fake-brave")
        self.workers: dict[str, set[str]] = {}  # extension id -> its worker's contexts
        self.default_context = default_context
        self.watcher_ids: set[str] = set()
        self.chosen = self.chosen_context = None
        self.asked: list[tuple[str, str]] = []  # every connect's (why, identity)
        self.gate: asyncio.Event | None = None  # set: connect stays "asking" until it is set
        self.started = self.closes = 0
        self.tab_scope = {"profile": "chosen", "elsewhere": 0}

    async def start(self):
        self.started += 1

    async def connect(self, why="connect", identity=""):
        self.asked.append((why, identity))
        self.connects += 1  # wave 2A's own record stays beside this
        if self.gate is not None:
            self.state = "asking"
            await self.gate.wait()
            self.state = "connected"
        else:
            await asyncio.sleep(0.02)

    async def close(self):
        self.closes += 1
        self.state = "off"

    def scope(self):
        return dict(self.tab_scope)

    def worker_contexts(self, extension_id):
        return set(self.workers.get(extension_id, set()))

    def lists(self, target):
        return any(page["target"] == target for page in self.pages)

    def context_of(self, target):
        return next((page.get("context", "C0") for page in self.pages if page["target"] == target), None)

    def targets_showing(self, url):
        return [page["target"] for page in self.pages if page["url"] == url]

    def add_page(self, target, url, context="C0", title=""):
        self.pages.append({"target": target, "url": url, "title": title, "context": context})
        self.changed()
```

Wave 1B's `FakeBrave.scope()` reports a scope a test can set; this plan's tests set it as `tab_scope` (if wave 1B
named that attribute otherwise, keep one name and use it in this plan's tests), and its default becomes
`{"profile": "chosen", "elsewhere": 0}`, since `"watcher"` is no longer produced. `tabs()` returns rows without
`context` (as the real link does):

```python
    def tabs(self):
        return [{**{key: page[key] for key in ("target", "url", "title")},
                 "owner": dict(self.owners.get(page["target"], {"kind": "you"}))} for page in self.pages]
```

(`asyncio` and `Path` are imported at the top of `tests/fake_brave.py`.) `FakeRelay.__init__` gains, beside wave
2A's records:

```python
        self.lists = lambda target: True  # set by FakeBrave: whether its link lists a target
        self.assigned, self.markers, self.closed_markers, self.served = [], set(), [], []
```

and `FakeRelay` gains these methods:

```python
    def assign(self, target, identity):
        if not self.lists(target):
            return False
        self.assigned.append((target, identity))
        self.own(identity, target)  # wave 2A's way for a test to declare a grant
        return True

    def note_marker(self, marker):
        self.markers.add(marker)

    async def close_marker(self, target, marker):
        if marker not in self.markers or not self.lists(target):
            return False
        self.closed_markers.append((target, marker))
        return True

    async def serve(self, ws):
        self.served.append(ws.headers.get("x-aib-agent-token"))
        await ws.accept()
        await ws.close()
```

and `FakeBrave.__init__` sets `self.relay.lists = self.lists` on its relay.

`tests/test_links.py`:

```python
"""One link per browser in use (browser-profile-choice Decision 11): the current place's browser, and any other one a
live agent or session works in. Fake links record their connects and closes; the tab-list tests use a real
InstanceLink on a fake debugging port."""

import asyncio
from pathlib import Path

from fake_brave import FakeBrave


def spots(tmp_path):
    from ai_browser.places import Place

    brave, chrome = tmp_path / "BraveSoftware" / "Brave-Browser", tmp_path / "Google" / "Chrome"
    return (Place("brave", str(brave), "Default"), Place("brave", str(brave), "Profile 1"),
            Place("chrome", str(chrome), "Default"))


def fake_links(state="ready"):
    from ai_browser.app.links import InstanceLinks

    made = {}

    def make(place):
        made[place.instance] = FakeBrave([], state=state, folder=Path(place.user_data_dir))
        return made[place.instance]

    return InstanceLinks(make), made


async def test_only_the_current_browser_connects_at_start(tmp_path):
    personal, _, chrome = spots(tmp_path)
    links, made = fake_links()
    assert links.set_current(personal) is True
    await links.connect(personal, "start")
    await asyncio.sleep(0)
    assert list(made) == [personal.instance] and made[personal.instance].asked == [("start", "")]
    assert made[personal.instance].started == 1 and links.link_for(chrome) is None


async def test_a_profile_switch_connects_nothing(tmp_path):
    personal, work, _ = spots(tmp_path)
    links, made = fake_links()
    links.set_current(personal)
    await links.connect(personal, "start")
    link = links.link_for(personal)
    assert links.set_current(work) is False and links.link_for(work) is link
    assert link.chosen == "Profile 1" and link.asked == [("start", "")]


async def test_a_browser_switch_connects_the_new_browser_once(tmp_path):
    personal, _, chrome = spots(tmp_path)
    links, made = fake_links()
    links.set_current(personal)
    assert links.set_current(chrome) is True
    await asyncio.gather(links.connect(chrome, "connect"), links.connect(chrome, "connect"))  # two callers
    assert made[chrome.instance].asked == [("connect", "")]  # one attempt: one question


async def test_the_old_browser_stays_while_its_agents_live_then_closes(tmp_path):
    personal, _, chrome = spots(tmp_path)
    links, made = fake_links()
    users = {personal.instance}
    links.users = lambda: set(users)
    links.set_current(personal)
    links.set_current(chrome)
    await links.prune({personal.instance})  # an agent still works in Brave
    assert links.link_for(personal) is not None and made[personal.instance].closes == 0
    users.clear()
    await links.prune(set())  # its last agent closed (or its last session said bye)
    assert links.link_for(personal) is None and made[personal.instance].closes == 1
    assert links.link_for(chrome) is not None  # the current place's browser always stays


async def test_a_browser_nobody_uses_is_never_connected(tmp_path):
    personal, _, chrome = spots(tmp_path)
    links, made = fake_links()
    links.set_current(personal)
    links.ensure(chrome)  # a link exists (say, a session's hello named Chrome), but nobody is placed there now
    await links.connect(chrome, "turn", "a1")
    assert made[chrome.instance].asked == []


async def test_a_switch_to_a_browser_whose_switch_is_off_connects_nothing(tmp_path):
    personal, _, chrome = spots(tmp_path)
    links, made = fake_links(state="off")
    links.set_current(chrome)
    await links.connect(chrome, "connect")
    assert made[chrome.instance].asked == []  # the card shows the steps instead


async def test_ensure_makes_a_link_and_connects_nothing(tmp_path):
    personal, _, chrome = spots(tmp_path)
    links, made = fake_links()
    made_links = []
    links.on_link(lambda place, link: made_links.append(place.browser))
    links.set_current(personal)
    link = links.ensure(chrome)
    await asyncio.sleep(0)
    assert links.ensure(chrome) is link and made_links == ["brave", "chrome"]
    assert link.started == 1 and link.asked == []


async def test_switching_away_from_a_browser_that_is_asking_drops_its_attempt(tmp_path):  # Review Focus 3
    personal, _, chrome = spots(tmp_path)
    links, made = fake_links()
    links.set_current(personal)
    old = made[personal.instance]
    old.gate = asyncio.Event()
    attempt = asyncio.ensure_future(links.connect(personal, "start"))
    await asyncio.sleep(0.05)
    assert old.state == "asking"
    links.set_current(chrome)
    await links.prune(set())  # no agent works in Brave
    await asyncio.wait_for(attempt, 1)  # the caller isn't left waiting
    old.gate.set()  # the user clicks Allow in Brave afterwards
    await asyncio.sleep(0.05)
    assert old.closes == 1 and old.state != "connected" and links.link_for(personal) is None


async def tab_list_on(tmp_path, pages):
    from ai_browser.app.bravelink import InstanceLink
    from ai_browser.app.links import InstanceLinks
    from fake_brave import FakePort

    personal, work, _ = spots(tmp_path)
    port = FakePort(Path(personal.user_data_dir), pages=pages)
    port.set_default("C2")
    await port.start()
    links = InstanceLinks(lambda place: InstanceLink(Path(place.user_data_dir), every=0.1))
    links.set_current(personal)
    link = links.link_for(personal)
    await link.start()
    await links.connect(personal, "start")
    return links, link, port


PAGES = [{"target": "U1", "url": "https://mail.example/", "title": "Mail", "context": "C1"},
         {"target": "U2", "url": "https://bank.example/", "title": "SECRET-P", "context": "C2"},
         {"target": "A1", "url": "https://shop.example/", "title": "Shop", "context": "C2"}]


async def test_the_tab_list_follows_the_chosen_profile(tmp_path):
    personal, work, _ = spots(tmp_path)
    links, link, port = await tab_list_on(tmp_path, PAGES)
    placed = {"a1": personal}
    links.owner_place = lambda owner: placed.get(owner.get("id"))
    links.describe = lambda place: {"label": f"Brave · {place.profile}", "color": "#3f51b5"}
    links.place_context = lambda place: "C1" if place == personal else None
    try:
        for _ in range(50):
            if link.lists("A1"):
                break
            await asyncio.sleep(0.05)
        link.chosen_context = "C1"  # as Watchers does once the Default copy's worker is seen
        link.set_owner("A1", {"kind": "agent", "id": "a1", "name": "Fix the footer", "color": "blue"})
        rows, scope = links.tabs()
        assert [row["target"] for row in rows] == ["U1", "A1"] and scope == {"profile": "chosen", "elsewhere": 1}
        agent = rows[1]
        assert "context" not in agent and agent["other_profile"] is True  # its place's copy is in C1, its tab in C2
        assert "place" not in agent  # its place is the current one
        placed["a1"] = work  # an agent placed in Profile 1 of the same browser: outside the current place
        rows, _ = links.tabs()
        assert rows[1]["place"] == {"label": "Brave · Profile 1", "color": "#3f51b5"}
        assert "other_profile" not in rows[1]  # no copy is connected in its place: nothing to compare with
        assert "SECRET-P" not in str(rows)
    finally:
        await links.close()
        await port.stop()


async def test_without_the_chosen_profiles_copy_the_list_falls_back_to_the_profile_used_last(tmp_path):
    links, link, port = await tab_list_on(tmp_path, PAGES)
    try:
        for _ in range(50):
            if link.lists("A1"):
                break
            await asyncio.sleep(0.05)
        rows, scope = links.tabs()
        assert scope["profile"] == "last_used" and [row["target"] for row in rows] == ["U2", "A1"]
    finally:
        await links.close()
        await port.stop()


async def test_a_profile_switch_re_filters_the_list_at_once(tmp_path):
    personal, work, _ = spots(tmp_path)
    links, link, port = await tab_list_on(tmp_path, PAGES)
    changes = []
    links.on_change(lambda: changes.append(1))
    try:
        for _ in range(50):
            if link.lists("A1"):
                break
            await asyncio.sleep(0.05)
        link.chosen_context = "C1"
        before = len(changes)
        links.set_current(work)  # Profile 1: its copy's context isn't known yet
        assert len(changes) > before and links.tabs()[1]["profile"] == "last_used"
        link.chosen_context = "C2"  # Watchers finds Profile 1's copy in C2
        assert [row["target"] for row in links.tabs()[0]] == ["U2", "A1"] and links.tabs()[1]["profile"] == "chosen"
    finally:
        await links.close()
        await port.stop()
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_links.py -q -p no:randomly`

Expected: FAIL with `ModuleNotFoundError: No module named 'ai_browser.app.links'`.

- [ ] **Step 3: Write `links.py`**

Create `src/ai_browser/app/links.py`:

```python
"""Every browser agents use, one InstanceLink each (browser-profile-choice Decision 11).

One debugging connection covers every profile of one browser instance, never another browser, so the app holds one
link (one relay upstream) per browser in use: the current place's, and the browser of any live agent or Claude Code
session placed elsewhere. A link connects only right after something the user did, and wave 2A's table decides from
`why` whether a question may start; a browser nobody uses is never connected, and its link closes once its last agent
or session ends. Everyone waiting on one browser shares one attempt."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable

from ..places import Place

CONNECTABLE = {"ready", "lost", "refused", "asking"}  # "off" waits for the switch; "connected" has nothing to do
OWNED = ("agent", "session", "handed")


class InstanceLinks:
    def __init__(self, make_link: Callable[[Place], object]):
        self.make_link = make_link
        self.current: Place | None = None
        self._links: dict[str, object] = {}  # instance -> its link
        self._places: dict[str, Place] = {}  # instance -> the place it was made for (its browser id)
        self._attempts: dict[str, asyncio.Future] = {}
        self._starts: dict[str, asyncio.Task] = {}  # instance -> its link's start (the first look at the switch)
        self._changes: list[Callable[[], None]] = []
        self._states: list[Callable[[Place, str], None]] = []
        self._made: list[Callable[[Place, object], None]] = []
        # set by the app server
        self.users: Callable[[], set[str]] = lambda: set()  # instances a live agent or session is placed in
        self.owner_place: Callable[[dict], Place | None] = lambda owner: None
        self.describe: Callable[[Place], dict] = lambda place: {"label": place.browser, "color": None}
        self.place_context: Callable[[Place], str | None] = lambda place: None

    # ---- the links ----------------------------------------------------------------------------------------------

    def on_change(self, callback: Callable[[], None]) -> None:
        self._changes.append(callback)

    def on_state(self, callback: Callable[[Place, str], None]) -> None:
        self._states.append(callback)

    def on_link(self, callback: Callable[[Place, object], None]) -> None:
        """callback(place, link) for each link as it is made (the app wires its relay)."""
        self._made.append(callback)

    def all(self) -> list[tuple[Place, object]]:
        return [(self._places[instance], link) for instance, link in self._links.items()]

    def at(self, instance: str):
        return self._links.get(instance)

    def link_for(self, place: Place | None):
        return None if place is None else self._links.get(place.instance)

    def set_current(self, place: Place) -> bool:
        """The Settings choice (or the app's start): True when it is another browser. Another profile of the same
        browser is the same link and the same upstream: nothing connects, nothing asks (Decision 12)."""
        before = self.current
        self.current = place
        link = self.ensure(place)
        for other in self._links.values():
            other.chosen = place.profile if other is link else None
        self._changed()
        return before is None or before.instance != place.instance

    def ensure(self, place: Place):
        """That browser's link, made if needed. Making a link connects nothing: its relay only looks at the switch,
        by TCP."""
        link = self._links.get(place.instance)
        if link is not None:
            return link
        link = self.make_link(place)
        self._links[place.instance], self._places[place.instance] = link, place
        link.on_change(lambda *_: self._changed())
        link.on_state(lambda state, place=place: self._state(place, state))
        for callback in list(self._made):
            callback(place, link)
        with contextlib.suppress(RuntimeError):  # no running loop: the caller starts the link itself
            self._starts[place.instance] = asyncio.get_running_loop().create_task(link.start())
        return link

    async def started(self, place: Place) -> None:
        """Wait for that link's first look at its switch (run.py prints the switch's steps when it is off)."""
        task = self._starts.get(place.instance)
        if task is not None:
            await asyncio.wait({task})

    def in_use(self, instance: str) -> bool:
        return (self.current is not None and instance == self.current.instance) or instance in self.users()

    async def connect(self, place: Place, why: str = "connect", identity: str = "") -> None:
        """Connect that browser now, only right after something the user did: "start", "connect" (Connect, Try again,
        a switch to another browser), or "turn" with the agent's id. One attempt per link, shared; nothing for a
        browser nobody uses, a switch that is off, or a link already connected."""
        link = self._links.get(place.instance)
        if link is None or not self.in_use(place.instance) or link.state not in CONNECTABLE:
            return
        attempt = self._attempts.get(place.instance)
        if attempt is None or attempt.done():
            attempt = asyncio.ensure_future(link.connect(why, identity))
            attempt.add_done_callback(lambda done: done.cancelled() or done.exception())
            self._attempts[place.instance] = attempt
        await asyncio.wait({attempt})

    async def prune(self, live: set[str]) -> None:
        """Close every browser that isn't the current place's and that no live agent or session uses (`live`: their
        instances). An attempt still waiting for Allow there is dropped with its link: it never connects later."""
        for instance in list(self._links):
            if (self.current is not None and instance == self.current.instance) or instance in live:
                continue
            link = self._links.pop(instance)
            self._places.pop(instance, None)
            self._starts.pop(instance, None)
            attempt = self._attempts.pop(instance, None)
            if attempt is not None and not attempt.done():
                attempt.cancel()
            with contextlib.suppress(Exception):
                await link.close()
            self._changed()

    async def close(self) -> None:
        for instance in list(self._links):
            attempt = self._attempts.pop(instance, None)
            if attempt is not None and not attempt.done():
                attempt.cancel()
            with contextlib.suppress(Exception):
                await self._links.pop(instance).close()

    def context_of(self, place: Place) -> str | None:
        """The context of `place`'s profile, known only through a copy connected there (Decision 8)."""
        return self.place_context(place)

    def located(self, target: str) -> tuple[str, str] | None:
        """(instance, context) of the link that lists `target`, or None."""
        for instance, link in self._links.items():
            context = link.context_of(target)
            if context is not None:
                return instance, context
        return None

    def _state(self, place: Place, state: str) -> None:
        for callback in list(self._states):
            with contextlib.suppress(Exception):
                callback(place, state)

    def _changed(self) -> None:
        for callback in list(self._changes):
            with contextlib.suppress(Exception):
                callback()

    # ---- the tab list (Decision 10) -----------------------------------------------------------------------------

    def tabs(self) -> tuple[list[dict], dict]:
        """The current link's rows and its scope (wave 1B's, on the chosen profile), plus the rows other links hold
        for agents, sessions and hand-overs. A row owned outside the current place carries its owner's place label,
        never one from the page; context ids never leave the links."""
        current = self.current
        rows, scope = [], {"profile": "none", "elsewhere": 0}
        for instance, link in self._links.items():
            here = current is not None and instance == current.instance
            if here:
                scope = link.scope()
            for row in link.tabs():
                owner = row.get("owner") or {}
                kind = owner.get("kind", "you")
                if here or kind in OWNED:  # another browser's own tabs are never listed
                    rows.append(self._labelled(link, row, kind, owner))
        return rows, scope

    def _labelled(self, link, row: dict, kind: str, owner: dict) -> dict:
        row = dict(row)
        place = self.owner_place(owner) if kind in OWNED else None
        if place is not None and (self.current is None or place.key != self.current.key):
            label = self.describe(place)
            row["place"] = {"label": label.get("label", ""), "color": label.get("color")}
        if kind in ("agent", "session") and place is not None:
            copy = self.place_context(place)
            landed = link.context_of(row["target"])
            if copy is not None and landed is not None and landed != copy:
                row["other_profile"] = True  # a fallback tab: it landed in the profile used last
        return row

    # ---- actions, routed to the link that lists the target ---------------------------------------------------------

    def _holding(self, target: str):
        return next((link for link in self._links.values() if link.lists(target)), None) or \
            self.link_for(self.current)

    async def watch(self, target: str) -> None:
        link = self._holding(target)
        if link is not None:
            await link.watch(target)

    async def close_targets(self, targets: list[str]) -> None:
        grouped: dict[int, tuple[object, list[str]]] = {}
        for target in targets:
            link = self._holding(target)
            if link is not None:
                grouped.setdefault(id(link), (link, []))[1].append(target)
        for link, chosen in grouped.values():
            await link.close_targets(chosen)

    async def thumbnail(self, target: str) -> bytes | None:
        link = self._holding(target)
        return await link.thumbnail(target) if link is not None else None

    async def page_text(self, target: str, picked: bool = False) -> str:
        link = self._holding(target)
        return await link.page_text(target, picked=picked) if link is not None else ""

    def set_owner(self, target: str, owner: dict) -> None:
        link = self._holding(target)
        if link is not None:
            link.set_owner(target, owner)

    def forget(self, target: str) -> None:
        for link in self._links.values():
            link.forget(target)

    def release(self, owner_id: str) -> None:
        for link in self._links.values():
            link.release(owner_id)

    def mark_brain(self, url: str) -> None:
        link = self.link_for(self.current)
        if link is not None:
            link.mark_brain(url)
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_links.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/links.py tests/fake_brave.py tests/test_links.py
git commit -m "feat: InstanceLinks, one connection per browser in use, only after the user acts, closed when unused"
```

### Task 14: `Watchers`: the copies' live connections, placed by their files and their workers

**Files:**
- Modify: `src/ai_browser/app/watchers.py` (add `REREAD_AFTER`, `WatcherConn`, `Watchers`)
- Test: `tests/test_watcher_copies.py`

**Interfaces:**
- Consumes: Task 10's `GroupKeeper` (`available()`, `can_open()`, `tab_of(target)`); Task 11's `WatcherCopies`
  (`folders()`, `name_of(id)`); Task 13's `InstanceLinks` (`current`, `all()`, `at(instance)`, `link_for(place)`) and
  the links' `worker_contexts(id)`, `default_context`, `watcher_ids`, `chosen_context`; wave A's
  `browsers.installed()` and `watcher_places(data_dir, watchers)`; Task 2's `Place`.
- Produces (`src/ai_browser/app/watchers.py`):
  - `REREAD_AFTER = (2.0, 5.0, 15.0)` (Task 1, fact 2, may change the last value);
  - `@dataclass class WatcherConn(ws, queue, origin, extension_id, copy, groups, place=None, context=None,
    status="unknown")`;
  - `class Watchers(copies, links=None, find_places=None, on_groups=None)` with `sleep` (the re-reads' clock) and:
    `allow(origin, copy="primary")`, `allowed(origin) -> bool`, `ids() -> set[str]`,
    `connected(ws, queue, origin) -> WatcherConn`, `gone(ws) -> WatcherConn | None`, `conn_of(ws)`,
    `connections() -> list[WatcherConn]`, `brain() -> WatcherConn | None` (the primary's latest connection),
    `place_of(origin) -> Place | None` (the name wave D calls), `context(conn) -> str | None`,
    `for_place(place) -> WatcherConn | None` (the primary first, then by slug), `extra_at(place) -> bool`,
    `placed_copy(place) -> str | None`, `for_context(instance, context) -> WatcherConn | None`,
    `place_context(place) -> str | None`, `can_group(instance) -> bool`,
    `status_for(place) -> "on" | "asleep" | "shared" | "unknown" | "missing"`,
    `tab_of(target) -> tuple[WatcherConn, int] | None`, `async refresh()`, `async arrived(conn)`, `sync()`,
    `on_change(cb)`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_watcher_copies.py` add:

```python
import asyncio
from pathlib import Path

from fake_brave import FakeBrave
from test_links import spots

E1, E2, E3 = "chrome-extension://e1", "chrome-extension://e2", "chrome-extension://e3"


def watchers_on(tmp_path, places=None):
    """Watchers over fake links (Brave at tmp/BraveSoftware…, Chrome at tmp/Google/Chrome), with `places` standing in
    for the browsers' files: extension id -> the places they list it enabled in."""
    from ai_browser.app.links import InstanceLinks
    from ai_browser.app.watchers import WatcherCopies, Watchers

    personal, work, chrome = spots(tmp_path)
    made = {}

    def make(place):
        made[place.browser] = FakeBrave([], folder=Path(place.user_data_dir),
                                        default_context="C1" if place.browser == "brave" else "K1")
        return made[place.browser]

    links = InstanceLinks(make)
    links.set_current(personal)
    links.ensure(chrome)
    found = {} if places is None else places
    watchers = Watchers(WatcherCopies(tmp_path / "home"), links, find_places=lambda: dict(found))
    for origin, copy in ((E1, "primary"), (E2, "brave-profile-1"), (E3, "chrome-default")):
        watchers.allow(origin, copy)
    return watchers, made, (personal, work, chrome)


def on(watchers, origin):
    conn = watchers.connected(object(), asyncio.Queue(), origin)
    conn.groups.watcher_changed(True)
    conn.groups.caps_from({"groups": True, "open": True})
    return conn


async def test_a_watcher_is_placed_by_its_profiles_files(monkeypatch, tmp_path):
    from ai_browser.app.watchers import WatcherCopies, Watchers
    from ai_browser.extension_id import extension_id_for
    from ai_browser.places import Place
    from places_rig import install, load_watcher, unload_watcher

    folders = install(monkeypatch, tmp_path, "brave", "chrome", default="brave")
    copies = WatcherCopies(tmp_path / "home")
    copies.prepare_all("http://127.0.0.1:8792", "tok")
    copy = copies.make("brave", "Profile 1", "http://127.0.0.1:8792", "tok", ["Default", "Profile 1"])
    primary, work = extension_id_for(copies.primary), extension_id_for(copy)
    watchers = Watchers(copies)
    load_watcher(folders["brave"], "Profile 1", work, copy)
    await watchers.refresh()
    brave_work = Place("brave", str(folders["brave"]), "Profile 1")
    assert watchers.place_of(f"chrome-extension://{work}") == brave_work
    assert watchers.status_for(brave_work) == "asleep"  # placed, not connected
    assert watchers.place_of(f"chrome-extension://{primary}") is None  # nowhere yet: unknown, never a guess
    load_watcher(folders["brave"], "Default", primary, copies.primary)
    load_watcher(folders["brave"], "Profile 2", primary, copies.primary)  # the primary in two profiles
    await watchers.refresh()
    assert watchers.place_of(f"chrome-extension://{primary}") is None
    assert watchers.status_for(Place("brave", str(folders["brave"]), "Default")) == "shared"
    unload_watcher(folders["brave"], "Profile 2", primary)
    load_watcher(folders["chrome"], "Default", primary, copies.primary)  # in Brave and in Chrome: shared too
    await watchers.refresh()
    assert watchers.place_of(f"chrome-extension://{primary}") is None
    assert watchers.status_for(Place("chrome", str(folders["chrome"]), "Default")) == "shared"


async def test_the_files_are_read_again_only_on_events(tmp_path):
    from ai_browser.app.watchers import REREAD_AFTER

    watchers, _, (_, work, _) = watchers_on(tmp_path)
    reads, slept = [], []
    watchers.find_places = lambda: reads.append(1) or {}

    async def clock(seconds):
        slept.append(seconds)

    watchers.sleep = clock
    conn = watchers.connected(object(), asyncio.Queue(), E2)
    await watchers.arrived(conn)  # when it connects, then 2 s, 5 s and 15 s later while it is still unknown
    steps = [REREAD_AFTER[0], REREAD_AFTER[1] - REREAD_AFTER[0], REREAD_AFTER[2] - REREAD_AFTER[1]]
    assert REREAD_AFTER[:2] == (2.0, 5.0) and len(reads) == 4 and slept == steps
    await asyncio.sleep(0.05)
    assert len(reads) == 4  # never on a timer
    await watchers.refresh()  # a page asked
    assert len(reads) == 5
    answers = iter([{}, {"e2": [work]}])
    reads.clear()
    slept.clear()
    watchers.find_places = lambda: reads.append(1) or next(answers, {"e2": [work]})
    other = watchers.connected(object(), asyncio.Queue(), E2)
    await watchers.arrived(other)
    assert len(reads) == 2 and slept == [REREAD_AFTER[0]] and other.status == "on"  # placed: no more reads


async def test_place_of_gives_a_copys_browser_and_profile(tmp_path):
    watchers, made, (personal, work, _) = watchers_on(tmp_path)
    watchers.find_places = lambda: {"e2": [work]}
    made["brave"].state = "ready"  # the browser's link isn't connected: no worker is seen
    conn = on(watchers, E2)
    await watchers.refresh()
    assert watchers.place_of(E2) == work and conn.place == work and watchers.place_of(E1) is None
    assert watchers.context(conn) is None and watchers.status_for(work) == "on"


async def test_a_copys_context_comes_from_its_worker_in_its_own_browser(tmp_path):
    watchers, made, (_, work, chrome) = watchers_on(tmp_path, {"e2": [], "e3": []})
    watchers.find_places = lambda: {"e2": [work], "e3": [chrome]}
    made["brave"].workers = {"e2": {"C2"}, "e3": {"C3"}}  # e3's worker shows in Brave's list: not its browser
    two, three = on(watchers, E2), on(watchers, E3)
    await watchers.refresh()
    assert watchers.context(two) == "C2" and watchers.context(three) is None
    assert watchers.for_context(work.instance, "C2") is two and watchers.place_context(work) == "C2"


async def test_status_for_each_state(tmp_path):
    from ai_browser.places import Place

    watchers, made, (personal, work, chrome) = watchers_on(tmp_path)
    side = Place("brave", personal.user_data_dir, "Profile 2")
    watchers.find_places = lambda: {"e1": [personal], "e2": [work, side], "e3": [chrome]}
    await watchers.refresh()
    on(watchers, E1)
    assert watchers.status_for(personal) == "on"
    assert watchers.status_for(chrome) == "asleep"  # the files place e3 there; its socket isn't open
    assert watchers.status_for(work) == "shared" and watchers.status_for(side) == "shared"
    other = Place("brave", personal.user_data_dir, "Profile 3")
    assert watchers.status_for(other) == "missing"
    watchers.find_places = lambda: {"e1": [personal]}
    watchers.allow("chrome-extension://e4", "brave-profile-3")
    watchers.connected(object(), asyncio.Queue(), "chrome-extension://e4")  # no file places it yet
    await watchers.refresh()
    assert watchers.status_for(other) == "unknown"


async def test_two_copies_in_one_profile_use_the_primary(tmp_path):
    watchers, made, (personal, _, _) = watchers_on(tmp_path)
    watchers.find_places = lambda: {"e1": [personal], "e2": [personal]}
    await watchers.refresh()
    copy = on(watchers, E2)
    assert watchers.for_place(personal) is copy and watchers.extra_at(personal)
    primary = on(watchers, E1)
    assert watchers.for_place(personal) is primary and watchers.placed_copy(personal) == "primary"


async def test_can_group_only_in_the_profile_used_last(tmp_path):
    watchers, made, (personal, work, _) = watchers_on(tmp_path)
    watchers.find_places = lambda: {"e1": [personal]}
    made["brave"].workers = {"e1": {"C1"}}
    await watchers.refresh()
    on(watchers, E1)
    assert watchers.can_group(personal.instance)  # the copy's context is the browser's default context
    made["brave"].default_context = "C2"  # the user clicked into a profile with no copy
    assert not watchers.can_group(personal.instance)


async def test_the_brain_is_the_primarys_latest_connection(tmp_path):
    watchers, _, _ = watchers_on(tmp_path)
    first, copy, second = on(watchers, E1), on(watchers, E2), on(watchers, E1)
    assert watchers.brain() is second
    watchers.gone(second.ws)
    assert watchers.brain() is first and watchers.connections() == [first, copy]
    watchers.gone(first.ws)
    assert watchers.brain() is None  # a copy never takes the Brain's role


async def test_sync_tells_the_current_link_its_chosen_context(tmp_path):
    watchers, made, (personal, work, _) = watchers_on(tmp_path)
    watchers.find_places = lambda: {"e1": [personal], "e2": [work]}
    made["brave"].workers = {"e1": {"C1"}, "e2": {"C2"}}
    await watchers.refresh()
    on(watchers, E1)
    assert made["brave"].chosen_context == "C1"
    watchers.links.set_current(work)
    watchers.sync()
    assert made["brave"].chosen_context is None  # Profile 1's copy isn't connected
    second = on(watchers, E2)
    assert made["brave"].chosen_context == "C2"
    watchers.gone(second.ws)
    assert made["brave"].chosen_context is None and made["chrome"].chosen_context is None
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_watcher_copies.py -q -p no:randomly`

Expected: FAIL with `ImportError: cannot import name 'Watchers'` (Task 11's tests still pass).

- [ ] **Step 3: Write `Watchers`**

In `src/ai_browser/app/watchers.py`, add the imports (`asyncio`, `contextlib`, `dataclass`, `Callable`,
`from .. import browsers`, `from ..places import Place`, `from .groups import GroupKeeper`) and, after
`WatcherCopies`:

```python
REREAD_AFTER = (2.0, 5.0, 15.0)  # seconds after a copy connects, while no file places it yet (Task 1, fact 2)


def _id(origin: str) -> str:
    return origin.removeprefix("chrome-extension://")


@dataclass
class WatcherConn:
    """One live watcher socket, a copy's worker: its own GroupKeeper, its place from the files, its context from its
    worker. Never sent to a page."""

    ws: object
    queue: asyncio.Queue
    origin: str
    extension_id: str
    copy: str  # "primary" or the copy's slug
    groups: GroupKeeper
    place: Place | None = None
    context: str | None = None
    status: str = "unknown"  # "on" (the files place it), "unknown" (no file yet), "shared" (in two places)


class Watchers:
    """The copies' live connections (Decisions 8 and 9). The Brain keeps one watcher, the primary copy's latest
    connection; every copy places tabs in its own profile, each through its own GroupKeeper. A copy's profile comes from
    its profile's files, its context from its worker, in its own browser's link: never a guess. The files are read only
    on events (a copy connects, a page asks, place_set, watcher_copy), never on a timer: they can be a few MB. After its
    profile's last window closes, a copy stayed connected about N s (Task 1, fact 4b: write the measured number)."""

    def __init__(self, copies: WatcherCopies, links=None, find_places=None, on_groups=None):
        self.copies, self.links = copies, links
        self.find_places: Callable[[], dict[str, list[Place]]] = find_places or self._from_files
        self.on_groups = on_groups  # a keeper's change: the browser card shows whether groups are on
        self.sleep = asyncio.sleep  # the re-reads' clock (tests replace it)
        self._conns: list[WatcherConn] = []
        self._copy_of: dict[str, str] = {}  # allowed origin -> "primary" or the copy's slug
        self._places: dict[str, list[Place]] = {}  # extension id -> the places its files list it enabled in
        self._changes: list[Callable[[], None]] = []

    # ---- origins and sockets ---------------------------------------------------------------------------------------

    def allow(self, origin: str, copy: str = "primary") -> None:
        """A watcher origin (chrome-extension://<id>) and which copy it is. Every link learns the id, so it remembers
        that copy's worker contexts."""
        self._copy_of[origin] = copy
        if self.links is not None:
            for _, link in self.links.all():
                link.watcher_ids.add(_id(origin))

    def allowed(self, origin: str) -> bool:
        return origin in self._copy_of

    def ids(self) -> set[str]:
        return {_id(origin) for origin in self._copy_of}

    def connected(self, ws, queue: asyncio.Queue, origin: str) -> WatcherConn:
        """A copy's worker said hello. It gets its own GroupKeeper; its place is whatever the files said last."""
        def send(message: dict) -> bool:
            queue.put_nowait(message)
            return True

        extension_id = _id(origin)
        conn = WatcherConn(ws, queue, origin, extension_id, self._copy_of.get(origin, "primary"),
                           GroupKeeper(send, on_change=self.on_groups))
        conn.place, conn.status = self.place_of(origin), self._status_of(extension_id)
        self._conns.append(conn)
        self.sync()
        return conn

    def gone(self, ws) -> WatcherConn | None:
        conn = self.conn_of(ws)
        if conn is not None:
            self._conns.remove(conn)
            self.sync()
        return conn

    def conn_of(self, ws) -> WatcherConn | None:
        return next((conn for conn in self._conns if conn.ws is ws), None)

    def connections(self) -> list[WatcherConn]:
        return list(self._conns)

    def brain(self) -> WatcherConn | None:
        """The Brain's watcher: the primary copy's latest connection (a reloaded watcher connects again)."""
        return next((conn for conn in reversed(self._conns) if conn.copy == "primary"), None)

    # ---- places and contexts ---------------------------------------------------------------------------------------

    def place_of(self, origin: str) -> Place | None:
        """A copy's browser and profile, from its profile's files: only when they list it in exactly one place."""
        found = self._places.get(_id(origin), [])
        return found[0] if len(found) == 1 else None

    def _status_of(self, extension_id: str) -> str:
        found = self._places.get(extension_id, [])
        return "on" if len(found) == 1 else "shared" if found else "unknown"

    def _placed_at(self, place: Place) -> list[str]:
        return [extension_id for extension_id, found in self._places.items()
                if len(found) == 1 and found[0].key == place.key]

    def _live_at(self, place: Place) -> list[WatcherConn]:
        placed = set(self._placed_at(place))
        latest: dict[str, WatcherConn] = {}
        for conn in self._conns:
            if conn.extension_id in placed:
                latest[conn.extension_id] = conn
        return sorted(latest.values(), key=lambda conn: (conn.copy != "primary", conn.copy))

    def for_place(self, place: Place | None) -> WatcherConn | None:
        """The copy connected in `place`: the primary, else the first by slug."""
        live = self._live_at(place) if place is not None else []
        return live[0] if live else None

    def extra_at(self, place: Place) -> bool:
        """Two copies are loaded in one profile: the row says "remove the extra one"."""
        return len(self._placed_at(place)) > 1

    def _name_of(self, extension_id: str) -> str:
        """"primary" or a copy's slug: from its allowed origin, else from the folders."""
        return self._copy_of.get(f"chrome-extension://{extension_id}") or self.copies.name_of(extension_id) or ""

    def placed_copy(self, place: Place) -> str | None:
        """Which copy the files place in `place` ("primary" first), for Set it up."""
        names = sorted((self._name_of(extension_id) for extension_id in self._placed_at(place)),
                       key=lambda name: (name != "primary", name))
        return names[0] if names else None

    def context(self, conn: WatcherConn) -> str | None:
        """The copy's context: its worker's, seen in its own browser's link, remembered for the socket's life."""
        if conn.context is None and conn.place is not None and self.links is not None:
            link = self.links.link_for(conn.place)
            found = link.worker_contexts(conn.extension_id) if link is not None else set()
            if len(found) == 1:
                conn.context = next(iter(found))
        return conn.context

    def place_context(self, place: Place) -> str | None:
        conn = self.for_place(place)
        return self.context(conn) if conn is not None else None

    def for_context(self, instance: str, context: str | None) -> WatcherConn | None:
        """The copy whose profile holds a tab of that context, in that browser: the only copy that can see it."""
        if context is None:
            return None
        found = [conn for conn in self._conns
                 if conn.place is not None and conn.place.instance == instance and self.context(conn) == context]
        found.sort(key=lambda conn: (conn.copy != "primary", conn.copy))
        return found[0] if found else None

    def can_group(self, instance: str) -> bool:
        """Decision 6: a context-less tab lands in the profile the browser used last, so the engine asks for a group
        only when a copy that can group is connected there."""
        link = self.links.at(instance) if self.links is not None else None
        conn = self.for_context(instance, getattr(link, "default_context", None))
        return conn is not None and conn.groups.available() == "on"

    def status_for(self, place: Place | None) -> str:
        """"on": a copy the files place there has an open socket; "asleep": the files place one there, none is
        connected; "shared": a copy there is also in another place; "unknown": a copy is connected that no file places
        yet; "missing": none of these."""
        if place is None:
            return "missing"
        placed = self._placed_at(place)
        if any(conn.extension_id in placed for conn in self._conns):
            return "on"
        if placed:
            return "asleep"
        if any(len(found) > 1 and any(where.key == place.key for where in found) for found in self._places.values()):
            return "shared"
        if any(conn.status == "unknown" for conn in self._conns):
            return "unknown"
        return "missing"

    def tab_of(self, target: str) -> tuple[WatcherConn, int] | None:
        """The copy that knows a target's tab id (it opened or grouped it), and that id."""
        for conn in reversed(self._conns):
            tab = conn.groups.tab_of(target)
            if tab is not None:
                return conn, tab
        return None

    # ---- reading the files ---------------------------------------------------------------------------------------

    def _from_files(self) -> dict[str, list[Place]]:
        folders = self.copies.folders()
        found: dict[str, list[Place]] = {}
        for row in browsers.installed():
            if row.agents:
                for where in browsers.watcher_places(row.data_dir, folders):
                    found.setdefault(where.extension_id, []).append(Place(row.id, str(row.data_dir), where.profile))
        return found

    async def refresh(self) -> None:
        """Read every installed browser's files again (in a thread) and place each connected copy. A copy found in two
        profiles, or in two browsers, is shared: it places nothing."""
        found = await asyncio.to_thread(self.find_places)
        self._places = {extension_id: list(places) for extension_id, places in found.items()}
        for conn in self._conns:
            place = self.place_of(conn.origin)
            if place != conn.place:
                conn.place, conn.context = place, None
            conn.status = self._status_of(conn.extension_id)
        self.sync()
        for callback in list(self._changes):
            with contextlib.suppress(Exception):
                callback()

    async def arrived(self, conn: WatcherConn) -> None:
        """A copy connected: the files now, and again at REREAD_AFTER while no file places it (the browser writes
        Secure Preferences a little after Load unpacked)."""
        await self.refresh()
        waited = 0.0
        for at in REREAD_AFTER:
            if conn.status != "unknown" or conn not in self._conns:
                return
            await self.sleep(at - waited)
            waited = at
            await self.refresh()

    def sync(self) -> None:
        """Tell each link which context its chosen profile has (the tab list's "chosen", Decision 10): the current
        place's copy's, else none."""
        if self.links is None:
            return
        current = self.links.current
        for place, link in self.links.all():
            here = current is not None and place.instance == current.instance
            link.chosen_context = self.place_context(current) if here else None

    def on_change(self, callback: Callable[[], None]) -> None:
        self._changes.append(callback)
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_watcher_copies.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/watchers.py tests/test_watcher_copies.py
git commit -m "feat: Watchers, every copy's connection placed by its profile's files and its worker, never a guess"
```

### Task 15: `where.py`: the Settings view from files and TCP checks only; ids in, labels out

**Files:**
- Create: `src/ai_browser/app/where.py`
- Test: `tests/test_where.py` (new)

**Interfaces:**
- Consumes: wave A's `browsers.detect(watchers)`, `public(found, connected)`, `state(data_dir)`, `installed()`,
  `profiles(data_dir)`, `by_id(id)`, `Found` (`browser`, `state`, `profiles`, `watchers`, `default`), `Installed`
  (`id`, `name`, `agents`, `data_dir`, `inspect_address`), `BrowserFacts.inspect`; Task 2's `Place`, `profile_ok`;
  Task 3's `browser_name`; Task 11's `WatcherCopies.folders()`; Task 13's `InstanceLinks.all()`; Task 14's
  `Watchers.status_for(place)`; `AgentManager.agents` (each agent's `where`, Task 16; read with `getattr`).
- Produces (`src/ai_browser/app/where.py`):
  - `WINDOW_FRONT_NOTE` (`""`, or Task 1 fact 1's sentence), `NOT_OFFERED`, `GONE`;
  - `class Where(copies)` with `kept` (the last `detect()`), and:
    - `async browsers_view(links, watchers, agents, current, automatic, fresh) -> dict`: the `browsers` message,
      wave A's `public()` shape plus `current`, `automatic`, `new_window_note`, per browser `at_work`, `inspect` and
      `extensions`, per profile `at_work` and `live`; a link that is asking, refused or lost puts its state in place
      of the detected one;
    - `check_place_set(message) -> Place | str` (ids only; the error text otherwise);
    - `describe(place) -> {"label": "Brave · Personal", "color": "#3f51b5" | None}`, for the app's own pages only;
    - `extensions_page(browser_id) -> str` (`brave://extensions`, `chrome://extensions`, …);
    - `forget_names()`.

- [ ] **Step 1: Write the failing tests**

`tests/test_where.py`:

```python
"""Settings → Where agents browse (app/where.py): built from files and TCP checks only, never a debugging session;
pages send ids, never paths; names and colours go only to AI Browser's own pages."""

import asyncio
import json
import os
import socket
import time
from pathlib import Path

import pytest

from conftest import symlink_or_skip
from fake_brave import FakeBrave, add_agent
from places_rig import install, load_watcher


def running(data_dir):
    """The browser's own lock names this test's process, so wave A's state() treats it as running."""
    if os.name == "nt":
        (Path(data_dir) / "lockfile").write_bytes(b"")
    else:
        symlink_or_skip(f"{socket.gethostname()}-{os.getpid()}", Path(data_dir) / "SingletonLock")


def setting(monkeypatch, tmp_path, ids=("brave", "chrome"), link_state="ready"):
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.links import InstanceLinks
    from ai_browser.app.watchers import WatcherCopies, Watchers
    from ai_browser.app.where import Where
    from ai_browser.places import Place

    folders = install(monkeypatch, tmp_path, *ids, default="brave")
    current = Place("brave", str(folders["brave"]), "Default")
    links = InstanceLinks(lambda place: FakeBrave([], state=link_state, folder=Path(place.user_data_dir)))
    links.set_current(current)
    copies = WatcherCopies(tmp_path / "home")
    copies.prepare_all("http://127.0.0.1:8792", "tok")
    watchers = Watchers(copies, links, find_places=lambda: {})
    return Where(copies), links, watchers, AgentManager(tmp_path / "home"), current, folders


async def test_building_the_settings_view_never_opens_a_debugging_session(monkeypatch, tmp_path):
    from test_cli import _browser_port_stand_in

    where, links, watchers, agents, current, folders = setting(monkeypatch, tmp_path, ids=("brave",))
    running(folders["brave"])
    server, seen = _browser_port_stand_in()
    try:
        (folders["brave"] / "DevToolsActivePort").write_text(f"{server.getsockname()[1]}\n/devtools/browser/x\n",
                                                             encoding="utf-8")
        view = await where.browsers_view(links, watchers, agents, current, False, fresh=True)
        for _ in range(20):
            if seen["connections"]:
                break
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.5)
        assert view["browsers"][0]["state"] == "switch_on"
        assert seen["connections"] >= 1 and seen["bytes"] == b""  # a TCP check: no HTTP request, no handshake
    finally:
        server.close()


async def test_the_view_has_no_paths_no_emails_and_no_watcher_ids(monkeypatch, tmp_path):
    from ai_browser.app import where as where_module
    from ai_browser.places import Place

    where, links, watchers, agents, current, folders = setting(monkeypatch, tmp_path)
    primary_id = next(iter(where.copies.folders()))
    load_watcher(folders["brave"], "Default", primary_id, where.copies.primary)
    agent = add_agent(agents, "a1")
    agent.where = Place("brave", str(folders["brave"]), "Profile 1")
    view = await where.browsers_view(links, watchers, agents, current, True, fresh=True)
    text = json.dumps(view)
    for secret in (str(tmp_path), "alex@example.com", "Alex Example", primary_id):
        assert secret not in text
    assert (view["type"], view["current"], view["automatic"]) == ("browsers", {"browser": "brave",
                                                                              "profile": "Default"}, True)
    brave = view["browsers"][0]
    assert (brave["id"], brave["name"], brave["agents"], brave["at_work"]) == ("brave", "Brave", True, 1)
    assert (brave["inspect"], brave["extensions"]) == ("brave://inspect/#remote-debugging", "brave://extensions")
    rows = {profile["folder"]: profile for profile in brave["profiles"]}
    assert (rows["Default"]["name"], rows["Default"]["color"], rows["Default"]["watcher"]) == ("Personal", "#3f51b5",
                                                                                               True)
    assert (rows["Profile 1"]["name"], rows["Profile 1"]["at_work"], rows["Profile 1"]["last_used"]) == ("Work", 1,
                                                                                                        True)
    assert rows["Default"]["live"] is False and view["new_window_note"] == where_module.WINDOW_FRONT_NOTE


async def test_browsers_agents_cant_use_are_listed_without_profiles(monkeypatch, tmp_path):
    where, links, watchers, agents, current, _ = setting(monkeypatch, tmp_path, ids=("brave", "edge"))
    view = await where.browsers_view(links, watchers, agents, current, False, fresh=True)
    edge = next(row for row in view["browsers"] if row["id"] == "edge")
    assert (edge["agents"], edge["profiles"], edge["state"], edge["at_work"]) == (False, [], None, 0)


async def test_a_kept_view_refreshes_states_without_reading_files(monkeypatch, tmp_path):
    from ai_browser import browsers

    where, links, watchers, agents, current, folders = setting(monkeypatch, tmp_path, ids=("brave",))
    running(folders["brave"])
    detected = []
    real = browsers.detect
    monkeypatch.setattr(browsers, "detect", lambda *args, **kwargs: detected.append(1) or real(*args, **kwargs))
    first = await where.browsers_view(links, watchers, agents, current, False, fresh=True)
    assert first["browsers"][0]["state"] == "switch_off" and detected == [1]
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        (folders["brave"] / "DevToolsActivePort").write_text(f"{listener.getsockname()[1]}\n/devtools/browser/x\n",
                                                             encoding="utf-8")
        kept = await where.browsers_view(links, watchers, agents, current, False, fresh=False)
        assert kept["browsers"][0]["state"] == "switch_on" and detected == [1]  # states fresh, files not read
    links.link_for(current).state = "asking"
    asking = await where.browsers_view(links, watchers, agents, current, False, fresh=False)
    assert asking["browsers"][0]["state"] == "asking"  # the app's own link says it is waiting for Allow


async def test_a_copy_in_two_browsers_is_shared_on_both_rows(monkeypatch, tmp_path):
    where, links, watchers, agents, current, folders = setting(monkeypatch, tmp_path)
    primary_id = next(iter(where.copies.folders()))
    load_watcher(folders["brave"], "Default", primary_id, where.copies.primary)
    load_watcher(folders["chrome"], "Default", primary_id, where.copies.primary)
    view = await where.browsers_view(links, watchers, agents, current, False, fresh=True)
    for row in view["browsers"]:
        default = next(profile for profile in row["profiles"] if profile["folder"] == "Default")
        assert default["shared_watcher"] is True, row["id"]


def test_check_place_set_takes_ids_only(monkeypatch, tmp_path):
    from ai_browser.app.where import GONE, NOT_OFFERED
    from ai_browser.places import Place

    where, _, _, _, _, folders = setting(monkeypatch, tmp_path, ids=("brave", "edge"))
    elsewhere = str(tmp_path / "elsewhere")
    assert where.check_place_set({"browser": "brave", "profile": "Profile 1", "user_data_dir": elsewhere}) == \
        Place("brave", str(folders["brave"]), "Profile 1")  # a path from a page is never used
    assert where.check_place_set({"browser": "firefox", "profile": "Default"}) == NOT_OFFERED
    assert where.check_place_set({"browser": "edge", "profile": "Default"}) == NOT_OFFERED  # not offered to agents
    for profile in ("Profile 9", "../x", None):
        assert where.check_place_set({"browser": "brave", "profile": profile}) == GONE.format(name="Brave")
    assert GONE.format(name="Brave") == "That profile isn't in Brave any more"


def test_describe_names_the_profile_for_our_pages_only(monkeypatch, tmp_path):
    from ai_browser.places import Place

    where, _, _, _, _, folders = setting(monkeypatch, tmp_path)
    assert where.describe(Place("brave", str(folders["brave"]), "Default")) == {"label": "Brave · Personal",
                                                                                 "color": "#3f51b5"}
    assert where.describe(Place("chrome", str(folders["chrome"]), "Profile 2")) == {"label": "Chrome · Side",
                                                                                    "color": None}
    assert where.describe(Place("brave", str(folders["brave"]), "Profile 8"))["label"] == "Brave · Profile 8"
    assert where.describe(Place("", str(tmp_path / "throwaway"), "Default"))["label"] == "Chrome · Default"
    assert where.extensions_page("brave") == "brave://extensions" and where.extensions_page("chrome-beta") == \
        "chrome://extensions"
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_where.py -q -p no:randomly`

Expected: FAIL with `ModuleNotFoundError: No module named 'ai_browser.app.where'`.

- [ ] **Step 3: Write `where.py`**

Create `src/ai_browser/app/where.py` (set `WINDOW_FRONT_NOTE` from the ledger's fact 1):

```python
"""Settings → Where agents browse (browser-profile-choice): the `browsers` view, place_set's checks, and the labels
("Brave · Personal") for AI Browser's own pages.

Building the view reads files and makes TCP checks only (wave A's browsers.detect): no HTTP request and no debugging
session, so no browser ever asks. Names and colours come from each browser's own Local State on this computer and go
to the app window's pages only, never to Claude or the terminal. Pages send ids (a browser id, a profile folder), never
a path: the folder is always found in browsers.installed()."""

from __future__ import annotations

import asyncio
import dataclasses
import re
from pathlib import Path

from .. import browsers
from ..chrome import browser_name
from ..places import Place, profile_ok

WINDOW_FRONT_NOTE = ""  # Task 1, fact 1: "A new window for this profile may come to the front." when it does
NOT_OFFERED = "AI Browser can't use that browser for agents: pick another one in Settings"
GONE = "That profile isn't in {name} any more"
LINK_STATES = {"asking", "refused", "lost"}  # the app's own link's states, shown in place of the detected one
_COLOR = re.compile(r"^#[0-9a-f]{6}$")


class Where:
    def __init__(self, copies):
        self.copies = copies
        self.kept: list | None = None  # the last browsers.detect()
        self._names: dict[str, dict[str, tuple[str, str | None]]] = {}  # instance -> folder -> (name, colour)

    async def browsers_view(self, links, watchers, agents, current: Place, automatic: bool, fresh: bool) -> dict:
        """The `browsers` message. With `fresh`, the files are read again (a page asked, place_set, watcher_copy);
        without it, the last detection is kept and only the states (two small files and a TCP check per browser) and
        the counts are new."""
        if fresh or self.kept is None:
            self.kept = await asyncio.to_thread(browsers.detect, self.copies.folders())
            self._names.clear()
        else:
            self.kept = await asyncio.to_thread(self._restated, self.kept)
        for found in self.kept:
            if found.browser.agents:
                self._names[Place(found.browser.id, str(found.browser.data_dir), "").instance] = {
                    profile.folder: (profile.name, profile.color) for profile in found.profiles}
        states = {place.browser: link.state for place, link in links.all()}
        connected = [browser for browser, state in states.items() if state == "connected"]
        rows = browsers.public(self.kept, connected=connected)
        kept = {found.browser.id: found for found in self.kept}
        placed = [where for where in (getattr(agent, "where", None) for agent in agents.agents.values()) if where]
        for row in rows:
            found = kept[row["id"]]
            if row["agents"] and states.get(row["id"]) in LINK_STATES:
                row["state"] = states[row["id"]]
            row["inspect"] = found.browser.inspect_address if row["agents"] else None
            row["extensions"] = self.extensions_page(row["id"])
            row["at_work"] = sum(where.browser == row["id"] for where in placed)
            for profile in row["profiles"]:
                place = Place(row["id"], str(found.browser.data_dir), profile["folder"])
                profile["at_work"] = sum(where.key == place.key for where in placed)
                profile["live"] = watchers.status_for(place) == "on"
        return {"type": "browsers", "current": current.public(), "automatic": automatic, "browsers": rows,
                "new_window_note": WINDOW_FRONT_NOTE}

    @staticmethod
    def _restated(kept: list) -> list:
        return [dataclasses.replace(found, state=browsers.state(found.browser.data_dir))
                if found.state is not None else found for found in kept]

    def check_place_set(self, message: dict) -> Place | str:
        """place_set and watcher_copy: a browser id and a profile folder, checked against the installed browsers and
        that browser's Local State. Any path in the message is ignored. The place, or the error's text."""
        browser, profile = message.get("browser"), message.get("profile")
        row = next((row for row in browsers.installed() if row.id == browser), None) if isinstance(browser, str) \
            else None
        if row is None or not row.agents:
            return NOT_OFFERED
        if not profile_ok(row.data_dir, profile):
            return GONE.format(name=row.name)
        return Place(row.id, str(row.data_dir), profile)

    def describe(self, place: Place) -> dict:
        """{"label": "Brave · Personal", "color": "#3f51b5"}: for the app window's own pages only (Decision 16)."""
        names = self._names.get(place.instance)
        if names is None:
            names = {found.folder: (found.name, found.color) for found in browsers.profiles(place.user_data_dir)}
            self._names[place.instance] = names
        name, color = names.get(place.profile, (place.profile, None))
        facts = browsers.by_id(place.browser) if place.browser else None
        browser = facts.name if facts is not None else browser_name(Path(place.user_data_dir))
        return {"label": f"{browser} · {name}",
                "color": color if isinstance(color, str) and _COLOR.fullmatch(color) else None}

    @staticmethod
    def extensions_page(browser_id: str) -> str:
        facts = browsers.by_id(browser_id)
        return f"{facts.inspect if facts is not None else 'chrome'}://extensions"

    def forget_names(self) -> None:
        self._names.clear()
```

If wave A's `public()` doesn't keep `found`'s order or ids, the code above maps rows by `row["id"]` already. If its
`Found` isn't a dataclass, rebuild it with its own constructor in `_restated`.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_where.py -q -p no:randomly`

Expected: PASS (the lock tests skip on a Windows machine without symbolic links only where `symlink_or_skip` says).

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/where.py tests/test_where.py
git commit -m "feat: the Settings view of browsers and profiles, from files and TCP checks only, with ids in and labels out"
```

### Task 16: Agents keep their place; **Restart in**

**Files:**
- Modify: `src/ai_browser/app/agents.py` (`Agent`, `AgentManager.create`, new `AgentManager.restart`, `RESTARTED`)
- Modify: `src/ai_browser/app/ui/chat.js` (a `note` event is drawn as a muted line)
- Test: `tests/test_agents.py`, `tests/test_brain_talk.py`

**Interfaces:**
- Consumes: Task 2's `Place`, `place_env`; wave A's `Agent.number`; wave 2A's per-agent token in `create()`;
  `AgentManager.stop`, `_record`, `_changed`.
- Produces:
  - `Agent.place: dict | None` (public: `{"browser", "profile", "label", "color"}`), `Agent.where: Place | None`,
    `Agent.task: str`, `Agent.skills: list[str]`, `Agent.servers: list[str] | None` (the last four never public);
  - `AgentManager.place: Place | None` (the current place, set by the app), `AgentManager.describe:
    Callable[[Place], dict] | None`;
  - `create(text, skills=(), model="sonnet", adopt=None, tab=None, servers=None, place=None) -> Agent`: an explicit
    place wins (a handed tab's place); else the current one; its env gains `place_env(place)`;
  - `RESTARTED = "Restarted as {number} · {name} in {place}."`; `async restart(agent_id) -> Agent | None`;
  - `chat.js`'s `append` draws `{"type": "note", "text"}` as `div.meta`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_agents.py` add:

```python
async def test_an_agent_keeps_the_place_it_was_created_with(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager
    from ai_browser.places import Place

    runner, _, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    personal, work = Place("brave", str(tmp_path / "b"), "Default"), Place("brave", str(tmp_path / "b"), "Profile 1")
    manager = AgentManager(tmp_path / "home", claude=runner)
    manager.place = personal
    manager.describe = lambda place: {"label": f"Brave · {place.profile}", "color": "#3f51b5"}
    try:
        first = await manager.create("one")
        manager.place = work  # the user switched profile in Settings
        second = await manager.create("two")
        assert (first.where, second.where) == (personal, work)
        assert first.bridge.env["AIB_CHROME_PROFILE"] == "Default" and second.bridge.env["AIB_CHROME_PROFILE"] == \
            "Profile 1"
        assert first.bridge.env["AIB_CHROME_DIR"] == str(tmp_path / "b") and first.bridge.env["AIB_BROWSER"] == "chrome"
        row = first.public()
        assert row["place"] == {"browser": "brave", "profile": "Default", "label": "Brave · Default",
                                "color": "#3f51b5"}
        assert not {"where", "task", "skills", "servers"} & set(row)
    finally:
        await manager.close_all()


async def test_an_agent_started_in_a_handed_tab_takes_that_tabs_place(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager
    from ai_browser.places import Place

    runner, _, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    manager = AgentManager(tmp_path / "home", claude=runner)
    manager.place = Place("brave", str(tmp_path / "b"), "Default")
    try:
        agent = await manager.create("reply to it", adopt="U1", place=Place("brave", str(tmp_path / "b"), "Profile 1"))
        assert agent.where.profile == "Profile 1" and agent.bridge.env["AIB_CHROME_PROFILE"] == "Profile 1"
    finally:
        await manager.close_all()


async def test_restart_keeps_the_words_skills_model_and_servers(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager
    from ai_browser.places import Place

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    brave, chrome = Place("brave", str(tmp_path / "b"), "Default"), Place("chrome", str(tmp_path / "c"), "Profile 1")
    manager = AgentManager(tmp_path / "home", claude=runner)
    manager.place = brave
    manager.describe = lambda place: {"label": "Chrome · Work" if place == chrome else "Brave · Personal",
                                      "color": None}
    try:
        old = await manager.create("Fix the footer", ["web-qa"], "opus", servers=["clickup"])
        assert await settle(manager, lambda agents: state(agents, old.id) == "your_turn")
        manager.place = chrome
        new = await manager.restart(old.id)
        assert (new.task, new.skills, new.model, new.servers) == ("Fix the footer", ["web-qa"], "opus", ["clickup"])
        assert new.where == chrome and old.where == brave and old.id in manager.agents  # stopped, never closed
        assert new.adopted == [] and "AIB_APP_ADOPT" not in new.bridge.env
        note = {"type": "note", "text": f"Restarted as {new.number} · {new.name} in Chrome · Work."}
        assert note in manager.events_of(old.id)
        await asyncio.sleep(0.5)
        assert not any("Restarted as" in json.dumps(line) for line in sent_to_claude(log))  # never to its Claude
    finally:
        await manager.close_all()
```

In `tests/test_brain_talk.py` add:

```python
async def test_the_brains_state_never_carries_an_agents_place(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager
    from ai_browser.brain.talk import state_data
    from ai_browser.places import Place

    runner, _, script = fake_claude
    script.write_text(json.dumps([{"result": "fine"}]), encoding="utf-8")
    manager = AgentManager(tmp_path / "home", claude=runner)
    manager.describe = lambda place: {"label": "Brave · SECRET-NAME-9", "color": "#123456"}
    try:
        await manager.create("check the shop", place=Place("brave", str(tmp_path / "b"), "Profile 7"))
        data = state_data(manager.snapshot()["agents"], [], 0, "")
        text = json.dumps(data)
        assert "SECRET-NAME-9" not in text and "Profile 7" not in text and str(tmp_path) not in text
    finally:
        await manager.close_all()
```

(`json` is imported in both files; `settle`, `state` and `sent_to_claude` are `tests/test_agents.py`'s own helpers.)

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_agents.py -k "place or restart" tests/test_brain_talk.py::test_the_brains_state_never_carries_an_agents_place -q -p no:randomly`

Expected: FAIL with `TypeError: AgentManager.create() got an unexpected keyword argument 'place'` (and no `restart`).

- [ ] **Step 3: Give each agent its place, and Restart in**

In `src/ai_browser/app/agents.py`, import `from ..places import Place, place_env` and add:

```python
RESTARTED = "Restarted as {number} · {name} in {place}."  # a line in the old agent's chat view, never to its Claude
```

`Agent` gains, after `check`:

```python
    place: dict | None = None  # where it browses, for the app's own pages: {"browser", "profile", "label", "color"}
    where: Place | None = field(default=None, repr=False)  # the same place, with its folder: never public
    task: str = field(default="", repr=False)  # its first words, skills and tool list, for Restart in (never public)
    skills: list = field(default_factory=list, repr=False)
    servers: list | None = field(default=None, repr=False)
```

and `"place"` joins `Agent.PUBLIC` (after wave A's `"number"` and `"queued"`). `AgentManager.__init__` gains:

```python
        self.place: Place | None = None  # where new agents browse (Settings, set by the app)
        self.describe: Callable[[Place], dict] | None = None  # the label and colour, for the app's own pages
```

`create` takes `place=None`; at its start, after `agent_id`, the place goes into the env, which is merged once, at
creation (keep wave 2A's own-token line and the adopt line as they are):

```python
        where = place or self.place  # an explicit place wins: an agent started in a tab the user handed it
        env = {**self.env, **(place_env(where) if where is not None else {}), "AIB_APP_AGENT": agent_id,
               **({"AIB_APP_ADOPT": adopt} if adopt else {})}
```

and, after the `Agent(...)` is built:

```python
        agent.where, agent.place = where, self._public_place(where)
        agent.task, agent.skills, agent.servers = text, list(skills), list(servers) if servers is not None else None
```

New methods:

```python
    def _public_place(self, where: Place | None) -> dict | None:
        if where is None:
            return None
        label = self.describe(where) if self.describe is not None else {"label": where.browser, "color": None}
        return {"browser": where.browser, "profile": where.profile, "label": label.get("label", ""),
                "color": label.get("color")}

    async def restart(self, agent_id: str) -> Agent | None:
        """Restart in (browser-profile-choice Decision 13): the old agent stops (its process and its tabs stay; a
        waiting permission becomes a no), and a new one starts with its first words, skills, model and tool list in
        the current place, with no handed tab. The old agent's chat view gets one line naming the new place: a line on
        the user's own pages only, never sent to its Claude, because it names a profile (Decision 16)."""
        old = self.agents.get(agent_id)
        if old is None or self.place is None:
            return None
        await self.stop(agent_id)
        new = await self.create(old.task, old.skills, old.model, servers=old.servers)
        label = new.place["label"] if new.place else ""
        self._record(old, {"type": "note", "text": RESTARTED.format(number=new.number, name=new.name, place=label)})
        return new
```

In `src/ai_browser/app/ui/chat.js`, `append` gains a case beside `done`:

```js
      case "note": // a line from AI Browser itself (Restart in): set as text
        bubble = null;
        add(el("div", "meta", event.text || ""));
        break;
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_agents.py tests/test_brain_talk.py::test_the_brains_state_never_carries_an_agents_place -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/agents.py src/ai_browser/app/ui/chat.js tests/test_agents.py tests/test_brain_talk.py
git commit -m "feat: an agent keeps the place it was created with, and Restart in starts the same words in the new one"
```

### Task 17: The server holds one link per browser: relays, connects, Take back, clients and `/cdp` by place

**Files:**
- Modify: `src/ai_browser/app/server.py`
- Create: `tests/profile_rig.py`
- Test: `tests/test_app_server.py`

**Interfaces:**
- Consumes: Task 13's `InstanceLinks`; Task 12's `InstanceLink`; Task 14's `Watchers` (`allow`, `status_for`,
  `for_place`, `extra_at`, `sync`, `place_context`); Task 15's `Where` (`describe`); Task 11's `WatcherCopies`; Task
  16's `Agent.where`, `AgentManager.place`, `AgentManager.describe`; wave 2A's relay hooks set in `attach_brave`
  (`port`, `handed`, `may_open`, `on_grant`, `on_change`), `agents.own_tabs`, `tokens`, `connect_brave(why,
  identity)`, `_cdp`, `take_back`'s `relay.cut`, `browser_clients`/`browser_disconnect`, `/agent-bye` and the sweep's
  `relay.forget(id, close_tabs=True)`, `_forward`'s `relay.forget(id)`; wave 1B's `tab_scope` in `tabs` and the
  snapshot; wave B's `allow_watcher(origin)`, `ui_socket`.
- Produces (in `AppServer`):
  - `self.copies: WatcherCopies`, `self.links: InstanceLinks | None`, `self.watchers: Watchers`, `self.where: Where`,
    `self.place_automatic: bool`, `self.on_browser_changed: Callable[[Place], None] | None`;
  - `brave` becomes a read-only property: the current place's link (for code that wants the current browser);
  - `allow_watcher(origin, copy="primary")`;
  - `attach_links(links, place, automatic=False)`; `attach_brave(link, place=None)` builds a one-link
    `InstanceLinks` around `link` (tests, and a server built without `run.py`);
  - `_place_of_identity(identity) -> Place | None` (an agent's `where`, else the current place; a session's
    recorded place), `_relay_of(identity)`, `_instances_in_use() -> set[str]`, `async _prune()`;
  - `connect_brave(why="connect", identity="")` connects the current place's browser; an agent's turn connects its
    own place's browser with `"turn"` and its id;
  - `take_back` cuts on the agent's own relay; `browser_clients` rows carry `"browser"`; `browser_disconnect` reaches
    the relay that holds the identity; `/cdp` hands a client to its place's relay;
  - `browser` gains `place` (`{"browser", "profile", "label", "color", "automatic"}`), `watcher` (`status_for` of the
    current place) and `extra_watcher`; `groups` is the current place's copy's;
  - `tests/profile_rig.py`: `E1`, `E2`, `places_for(tmp_path)`, `rig(fake_claude, tmp_path, brain=False,
    current="personal", state="connected", events=None, spots=None) -> (server, url, spots, made)`,
    `copy_socket(server, url,
    origin, link=None, context=None, opens=True, answer=True)` (async context manager yielding `(ws, seen)`),
    `settled(predicate, seconds=5)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/profile_rig.py`:

```python
"""Wave C's app-server rig: an AppServer with fake links (FakeBrave, each with a FakeRelay) for the places a test
names, and fake watcher sockets with their own origins that answer open_tab as a copy in that profile would."""

from __future__ import annotations

import asyncio
import contextlib
import json
from contextlib import asynccontextmanager
from pathlib import Path

from websockets.asyncio.client import connect

from fake_brave import FakeBrave

E1, E2 = "chrome-extension://e1", "chrome-extension://e2"  # the primary copy (Brave · Default); Profile 1's copy


def places_for(tmp_path) -> dict:
    from ai_browser.places import Place

    brave, chrome = tmp_path / "BraveSoftware" / "Brave-Browser", tmp_path / "Google" / "Chrome"
    return {"personal": Place("brave", str(brave), "Default"), "work": Place("brave", str(brave), "Profile 1"),
            "chrome": Place("chrome", str(chrome), "Default")}


async def rig(fake_claude, tmp_path, brain=False, current="personal", state="connected", events=None, spots=None):
    """(server, url, spots, made). `made` maps "brave" and "chrome" to their fake links as they are made. The primary
    copy (E1) is placed in Brave's Default, its worker in C1; Profile 1's copy (E2) in Profile 1, its worker in C2;
    Brave's profile used last (its default context) is C1. `spots` replaces places_for's three places (a test whose
    browsers are "installed" passes their real data folders)."""
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.links import InstanceLinks
    from ai_browser.app.server import AppServer
    from ai_browser.brain.service import BrainService
    from ai_browser.brain.store import BrainStore
    from test_bridge import EVENTS

    runner, _, script = fake_claude
    script.write_text(json.dumps(events or EVENTS), encoding="utf-8")
    home = tmp_path / "home"
    agents = AgentManager(home, claude=runner)
    service = BrainService(BrainStore(home), agents, claude=runner, batch_wait=0.1) if brain else None
    server = AppServer(home, agents, brain=service)
    url = await server.start()
    spots = spots or places_for(tmp_path)
    made = {}

    def make(place):
        link = FakeBrave([], state=state, folder=Path(place.user_data_dir),
                         default_context="C1" if place.browser == "brave" else "K1")
        link.name = "Brave" if place.browser == "brave" else "Chrome"
        link.workers = {"e1": {"C1"}, "e2": {"C2"}} if place.browser == "brave" else {}
        made[place.browser] = link
        return link

    server.attach_links(InstanceLinks(make), spots[current])
    server.allow_watcher(E1)
    server.allow_watcher(E2, copy="brave-profile-1")
    server.watchers.find_places = lambda: {"e1": [spots["personal"]], "e2": [spots["work"]]}
    return server, url, spots, made


@asynccontextmanager
async def copy_socket(server, url, origin, link=None, context=None, opens=True, answer=True):
    """A watcher copy's worker: hello as the watcher, its caps (groups; `open` when `opens`), and, with `link` and
    `answer`, an answer to each open_tab: the marker page added to that fake link in `context`, then opened_tab.
    Yields (ws, seen): every message the server sent it."""
    from test_app_server import socket_url

    async with connect(socket_url(server, url), origin=origin) as ws:
        await ws.send(json.dumps({"type": "hello", "view": "watcher"}))
        await ws.send(json.dumps({"type": "watcher_caps", "groups": True, "open": opens}))
        seen: list[dict] = []
        reader = asyncio.ensure_future(_read(ws, seen, link, context, answer))
        try:
            yield ws, seen
        finally:
            reader.cancel()


async def _read(ws, seen, link, context, answer):
    tab = 400
    with contextlib.suppress(Exception):
        async for raw in ws:
            message = json.loads(raw)
            seen.append(message)
            if message.get("type") == "open_tab" and link is not None and answer:
                tab += 1
                link.add_page(f"T-{message['marker'][:6]}", f"about:blank#aib-{message['marker']}", context)
                await ws.send(json.dumps({"type": "opened_tab", "request": message["request"], "ok": True, "tab": tab,
                                          "window": 7, "group": 9, "new_window": False}))


async def settled(predicate, seconds=5):
    for _ in range(int(seconds * 20)):
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return predicate()
```

In `tests/test_app_server.py` add (`ui_socket` is wave B's helper; `recv`, `until`, `add_agent` are this file's):

```python
async def test_connect_starts_and_turns_with_wave_2a_why(fake_claude, tmp_path):
    from profile_rig import rig, settled
    from ui_socket import ui_socket

    server, url, spots, made = await rig(fake_claude, tmp_path, state="ready")
    try:
        server.connect_brave("start")
        assert await settled(lambda: made["brave"].asked == [("start", "")])
        async with ui_socket(server, url) as page:
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            await recv(page)
            await page.send(json.dumps({"type": "brave_connect"}))
            assert await settled(lambda: made["brave"].asked[-1] == ("connect", ""))
        agent = await server.agents.create("one", place=spots["chrome"])  # its own place: Chrome
        assert await settled(lambda: "chrome" in made and made["chrome"].asked == [("turn", agent.id)])
        assert ("turn", agent.id) not in made["brave"].asked
    finally:
        await server.stop()


async def test_take_back_cuts_on_the_agents_own_relay(fake_claude, tmp_path):
    from profile_rig import rig, settled
    from ui_socket import ui_socket

    server, url, spots, made = await rig(fake_claude, tmp_path)
    server.links.ensure(spots["chrome"])
    cuts = []
    for name, link in made.items():
        async def cut(identity, target, name=name):
            cuts.append((name, identity, target))
        link.relay.cut = cut
    add_agent(server.agents, "a1").where = spots["personal"]
    add_agent(server.agents, "a2", "Check prices", "green", adopted=["U9"]).where = spots["chrome"]
    try:
        async with ui_socket(server, url) as page:
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            await recv(page)
            await page.send(json.dumps({"type": "take_back", "target": "U9"}))
            assert await settled(lambda: cuts == [("chrome", "a2", "U9")])  # only the relay a2's sessions are on
    finally:
        await server.stop()


async def test_browser_clients_list_every_link(fake_claude, tmp_path):
    from profile_rig import rig, settled
    from ui_socket import ui_socket

    server, url, spots, made = await rig(fake_claude, tmp_path)
    server.links.ensure(spots["chrome"])
    gone = []
    for name, link in made.items():
        rows = [{"id": "a1" if name == "brave" else "a2", "kind": "agent", "number": 1 if name == "brave" else 2,
                 "name": "x", "color": "blue", "tabs": 1, "connected": True, "cut_off": False}]
        link.relay.clients = lambda rows=rows: [dict(row) for row in rows]

        async def disconnect(identity, name=name):
            gone.append((name, identity))
        link.relay.disconnect = disconnect
    add_agent(server.agents, "a2", "Check prices", "green").where = spots["chrome"]
    try:
        async with ui_socket(server, url) as page:
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            snapshot = await recv(page)
            assert sorted((row["id"], row["browser"]) for row in snapshot["browser_clients"]) == [
                ("a1", "Brave"), ("a2", "Chrome")]
            await page.send(json.dumps({"type": "browser_disconnect", "id": "a2"}))
            assert await settled(lambda: gone == [("chrome", "a2")])
    finally:
        await server.stop()


async def test_the_browser_card_names_the_place_and_its_watcher(fake_claude, tmp_path):
    from profile_rig import rig
    from ui_socket import ui_socket

    server, url, spots, made = await rig(fake_claude, tmp_path)
    await server.watchers.refresh()
    try:
        async with ui_socket(server, url) as page:
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            browser = (await recv(page))["browser"]
            assert browser["place"] == {"browser": "brave", "profile": "Default", "label": "Brave · Default",
                                        "color": None, "automatic": False}
            assert (browser["watcher"], browser["groups"], browser["extra_watcher"]) == ("asleep", "no_watcher",
                                                                                       False)
            assert str(tmp_path) not in json.dumps(browser)  # no folder reaches a page
    finally:
        await server.stop()


async def test_an_agent_closing_prunes_its_old_browser(fake_claude, tmp_path):
    from profile_rig import rig, settled

    server, url, spots, made = await rig(fake_claude, tmp_path)
    try:
        agent = await server.agents.create("one", place=spots["chrome"])
        assert await settled(lambda: "chrome" in made)
        await server.agents.close(agent.id)
        assert await settled(lambda: made["chrome"].closes == 1)  # its last agent closed
        assert server.links.link_for(spots["chrome"]) is None and made["brave"].closes == 0
    finally:
        await server.stop()


async def test_cdp_goes_to_the_relay_of_the_clients_place(fake_claude, tmp_path):
    from websockets.exceptions import InvalidStatus

    from profile_rig import rig, settled

    server, url, spots, made = await rig(fake_claude, tmp_path)
    server.links.ensure(spots["chrome"])
    add_agent(server.agents, "a1").where = spots["personal"]
    add_agent(server.agents, "a2", "Check prices", "green").where = spots["chrome"]
    cdp = url.replace("http", "ws") + "/cdp"
    try:
        for agent, browser in (("a2", "chrome"), ("a1", "brave")):
            token = server.tokens.mint(agent)
            async with connect(cdp, additional_headers={"X-AIB-Agent-Token": token}) as ws:
                with pytest.raises(ConnectionClosed):
                    await ws.recv()
            assert await settled(lambda: made[browser].relay.served[-1:] == [token])
        assert made["brave"].relay.served == [server.tokens.mint("a1")]  # a2 never reached Brave's relay
        for headers, origin in (({"X-AIB-Agent-Token": "nobody"}, None),
                                ({"X-AIB-Agent-Token": server.tokens.mint("a1")}, "https://evil.example")):
            with pytest.raises(InvalidStatus) as refused:
                async with connect(cdp, additional_headers=headers, origin=origin):
                    pass
            assert refused.value.response.status_code == 403
    finally:
        await server.stop()
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_app_server.py -k "wave_2a_why or own_relay or every_link or names_the_place or prunes_its_old_browser or relay_of_the_clients_place" -q -p no:randomly`

Expected: FAIL with `AttributeError: 'AppServer' object has no attribute 'attach_links'`.

- [ ] **Step 3: One link per browser in the server**

In `src/ai_browser/app/server.py`, import `browsers`, `places` (`Place`), `InstanceLink`, `InstanceLinks`,
`WatcherCopies`, `Watchers`, `Where`, and `PlainTextResponse`.

**`__init__`.** In place of `self.brave = None` and the single `self.groups = GroupKeeper(...)`:

```python
        self.copies = WatcherCopies(self.home)  # the watcher's copies, one per profile (Decision 7)
        self.links: InstanceLinks | None = None  # one link per browser in use (attach_links): Decision 11
        self.watchers = Watchers(self.copies, on_groups=self._browser_changed)  # every copy's live connection
        self.where = Where(self.copies)  # Settings' view, place_set's checks, the labels for our pages
        self.place_automatic = False  # the current place was chosen for the user, not saved by them
        self.on_browser_changed: Callable[[Place], None] | None = None  # run.py writes link.json again
        self._no_groups = GroupKeeper(lambda message: False)  # what `groups` gives when no copy is connected
```

and `agents.on_turn = self._on_turn` in place of wave 2A's `lambda agent: self.connect_brave("turn", agent.id)`.

**The current link, for code that wants the current browser:**

```python
    @property
    def brave(self):
        """The current place's link (wave 2A's and 1B's code reads `self.brave`); None before attach_links."""
        return self.links.link_for(self.links.current) if self.links is not None else None

    @property
    def groups(self) -> GroupKeeper:
        """The tab groups of the current place's copy, else of the Brain's copy (a server with no link, as in wave
        2A's tests), else a keeper with no watcher."""
        current = self.links.current if self.links is not None else None
        conn = self.watchers.for_place(current) or self.watchers.brain()
        return conn.groups if conn is not None else self._no_groups
```

**`allow_watcher`** (wave B's) takes the copy's name and tells `Watchers`:

```python
    def allow_watcher(self, origin: str, copy: str = "primary") -> None:
        """A watcher copy's origin (chrome-extension://<id>) and which copy it is: "primary" or its slug."""
        # wave B's lines that record the origin as a watcher origin stay here
        self.watchers.allow(origin, copy)
```

**`attach_links` and `attach_brave`.** Move wave 2A's relay wiring out of `attach_brave` into `_wire_relay(self,
link)`, unchanged, except two lines: `on_grant` sets the owner on that same link
(`link.relay.on_grant(lambda identity, target, link=link: self._own_on(link, target, self._owner_of(identity)))`), and
`agents.own_tabs` is set once in `attach_links` (below). Then:

```python
    def attach_links(self, links: InstanceLinks, place: Place, automatic: bool = False) -> None:
        """The browsers agents use, one InstanceLink each, and the current place: the tab list, Watch, thumbnails, the
        browser card and every relay come from here (browser-profile-choice Decision 11)."""
        self.links, self.tabs = links, links
        self.watchers.links = links
        self.place_automatic = automatic
        links.users = self._instances_in_use
        links.owner_place = self._owner_place
        links.describe = self.where.describe
        links.place_context = self.watchers.place_context
        links.on_link(lambda place, link: self._wire_relay(link))
        links.on_change(self._tabs_changed)
        links.on_state(lambda place, state: (self.watchers.sync(), self._browser_changed()))
        self.agents.place, self.agents.describe = place, self.where.describe
        self.agents.close_tabs = links.close_targets
        self.agents.own_tabs = lambda agent_id: [target for _, link in links.all()
                                                 for target in link.relay.own_targets(agent_id)]
        links.set_current(place)
        self.watchers.sync()
        self._browser_changed()
        self._tabs_changed()

    def attach_brave(self, link, place: Place | None = None) -> None:
        """One link (tests, and a server built without run.py): the current place is `place`, or that link's own
        folder in its Default profile. Another browser gets a real InstanceLink, which connects nothing by itself."""
        folder = Path(getattr(link, "folder", self.home / "brave"))
        facts = browsers.for_data_dir(folder)
        place = place or Place(facts.id if facts is not None else "", str(folder), "Default")
        given = {place.instance: link}

        def make(wanted: Place):
            return given.pop(wanted.instance, None) or InstanceLink(
                Path(wanted.user_data_dir), watcher_ids=self.copies.ids() | self.watchers.ids(), tokens=self.tokens,
                app_origin=self.url or "")

        self.attach_links(InstanceLinks(make), place)
```

**Who is where:**

```python
    def _place_of_identity(self, identity: str) -> Place | None:
        """An agent's place (an agent made without one, in tests, is in the current place); a session's, from its
        hello (None: the app can't hold its browser)."""
        if SESSION_ID.match(identity):
            session = self.sessions.get(identity)
            return session.get("where") if session else None
        agent = self.agents.agents.get(identity)
        if agent is None:
            return None
        return agent.where or (self.links.current if self.links is not None else None)

    def _owner_place(self, owner: dict) -> Place | None:
        identity = owner.get("id")
        return self._place_of_identity(identity) if isinstance(identity, str) else None

    def _relay_of(self, identity: str):
        """The relay of the identity's place's link: the only one its connections are on."""
        if self.links is None:
            return None
        link = self.links.link_for(self._place_of_identity(identity)) or self.links.link_for(self.links.current)
        return link.relay if link is not None else None

    def _instances_in_use(self) -> set[str]:
        placed = [agent.where for agent in self.agents.agents.values() if agent.where is not None]
        placed += [session["where"] for session in self.sessions.values() if session.get("where") is not None]
        return {place.instance for place in placed}

    async def _prune(self) -> None:
        """A browser that isn't the current place's closes once its last agent or session has ended (Decision 11)."""
        if self.links is not None:
            await self.links.prune(self._instances_in_use())

    def _own_on(self, link, target: str, owner: dict | None) -> None:
        if owner is not None:
            link.set_owner(target, owner)
```

`_own(target, owner)` (wave 2A's, which reads `self.brave`) routes through the links: `self.links.set_owner(target,
owner)` and `self.links.forget(target)` (nothing when `self.links` is None).

**Connecting:**

```python
    def connect_brave(self, why: str = "connect", identity: str = "") -> None:
        """Connect the current place's browser now: "start", or "connect" (Connect, Try again, a switch to another
        browser). Only right after something the user did; wave 2A's table decides whether a question may start."""
        if self.links is not None and self.links.current is not None:
            self._job(self.links.connect(self.links.current, why, identity))

    def _on_turn(self, agent) -> None:
        """An agent's turn (right after the user's task, message or Continue): its own place's browser."""
        if self.links is None:
            return
        place = agent.where or self.links.current
        self.links.ensure(place)  # an agent in a browser with no link yet (a handed tab's place)
        self._job(self.links.connect(place, "turn", agent.id))
```

**Take back, clients and Disconnect.** In `_brave_command`'s `take_back` branch, wave 2A's `await
self.brave.relay.cut(had, target)` becomes:

```python
                relay = self._relay_of(had)
                if relay is not None:
                    await relay.cut(had, message["target"])  # the relay of the agent's own place
```

Wave 2A's `browser_clients` list (its broadcast, and the snapshot's `browser_clients`) comes from every link's relay:

```python
    def _clients(self) -> list[dict]:
        """Wave 2A's connected clients, from every link's relay; each row names its browser."""
        if self.links is None:
            return []
        return [{**row, "browser": link.name} for _, link in self.links.all() for row in link.relay.clients()]
```

and its `browser_disconnect` goes to the relay that lists the identity, else the identity's own:

```python
            holding = next((link.relay for _, link in self.links.all()
                            if any(row.get("id") == identity for row in link.relay.clients())), None)
            relay = holding or self._relay_of(identity)
            if relay is not None:
                await relay.disconnect(identity)
```

**Ends.** In `_forward`'s `agent_closed` branch, wave 2A's `relay.forget(id)` runs on every link's relay, then the
links are pruned:

```python
                if self.links is not None:
                    for _, link in self.links.all():
                        await link.relay.forget(str(message.get("id")))
                    self._job(self._prune())
```

In `/agent-bye` and the sweep, take `relay = self._relay_of(session_id)` before the session is popped, run wave 2A's
`relay.forget(session_id, close_tabs=True)` on it, and `await self._prune()` after.

**Grants.** Wherever wave 2A asks the relay whether it grants a target to an identity (the reports' and claims'
check, and the `adopted` flag it takes from the relay), ask that identity's own relay, `self._relay_of(identity)`, in
place of `self.brave.relay`: an agent placed in another browser has its tabs there.

**The `/cdp` route:**

```python
    async def _cdp(self, ws: WebSocket) -> None:
        """Wave 2A's /cdp, one relay per browser (Decision 11): refuse an Origin or a wrong Host as wave 2A's Decision 8
        does, in that order; find the client by its token, then its place; hand the socket to that place's link's
        relay, which checks everything again. A client never chooses its upstream."""
        expected = self.url.split("://", 1)[1] if self.url else ""
        if "origin" in ws.headers or ws.headers.get("host") != expected:
            await ws.send_denial_response(PlainTextResponse("refused", status_code=403))
            return
        identity = self.tokens.who(ws.headers.get(TOKEN_HEADER, ""))
        if identity is None:
            await ws.send_denial_response(PlainTextResponse("refused", status_code=403))
            return
        link = self.links.link_for(self._place_of_identity(identity)) if self.links is not None else None
        if link is None:
            name = self.brave.name if self.brave is not None else "your browser"
            await ws.send_denial_response(PlainTextResponse(
                f"AI Browser isn't connected to {name}: ask the user to click Connect in AI Home", status_code=409))
            return
        await link.relay.serve(ws)
```

(`TOKEN_HEADER` from wave 2A's `cdprelay`.)

**The tab list and the card.** Replace the places that read `self.tabs.tabs()` and wave 1B's `scope()` (the `tabs`
broadcast, the snapshot's `tabs` and `tab_scope`, `_handable`, `_agent_status`'s handed lookup) with:

```python
    def _tab_rows(self) -> list[dict]:
        return self.links.tabs()[0] if self.links is not None else []

    def _tabs_changed(self) -> None:
        if self.links is not None:
            rows, scope = self.links.tabs()
            self._send_all({"type": "tabs", "tabs": rows, "tab_scope": scope})
```

and the snapshot's `tab_scope` is `self.links.tabs()[1]` (None without links). `_browser_info` becomes:

```python
    def _browser_info(self) -> dict:
        """The browser card (wave B's shape; `kind` is always "brave"), with the current place and its watcher."""
        if self.links is None or self.links.current is None:
            return {"kind": "brave", "name": "Brave", "state": "off", "groups": self.groups.available(),
                    "place": None, "watcher": "missing", "extra_watcher": False}
        place, link = self.links.current, self.brave
        conn = self.watchers.for_place(place)
        return {"kind": "brave", "name": link.name, "state": link.state,
                "groups": conn.groups.available() if conn is not None else "no_watcher",
                "place": {**place.public(), **self.where.describe(place), "automatic": self.place_automatic},
                "watcher": self.watchers.status_for(place), "extra_watcher": self.watchers.extra_at(place)}
```

Earlier tests that compare a whole `browser` message with `==` (in `tests/test_app_server.py` and
`tests/test_app_run.py`, for example the one expecting `{"kind": "brave", "name": "Brave", "state": "off", "groups":
"no_watcher"}`) compare those four keys only: `{key: browser[key] for key in ("kind", "name", "state", "groups")}`.

- [ ] **Step 4: Run them, and the server's earlier tests**

Run: `uv run pytest tests/test_app_server.py -q -p no:randomly`

Expected: PASS. Wave 2A's and 1B's server tests attach a `FakeBrave` with `attach_brave(brave)`, which now builds a
one-link `InstanceLinks`; they pass unchanged. A test that set `server.brave = …` by hand uses `attach_brave(…)`
instead.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/server.py tests/profile_rig.py tests/test_app_server.py
git commit -m "feat: the app server holds one link per browser in use: relays, connects, Take back and /cdp by place"
```

### Task 18: The server's watcher copies by role: the Brain keeps the primary, every copy places tabs

**Files:**
- Modify: `src/ai_browser/app/server.py` (the watcher's `hello`, the reports, `_from_watcher`, `_to_watcher`,
  `_unsubscribe`, `_group`, `_group_opened`, `_agent_claim`, `_ungroup`, `place_of`; `MESSAGE_RULES`,
  `WATCHER_MESSAGES`, `TAB_REPORTS`, `WATCHER_RECEIVES`)
- Modify: `tests/test_watcher_rules.py` (the two copies of the tables), `tests/test_watcher.py` (the `watcher`
  fixture places its copy)
- Test: `tests/test_app_server.py`

**Interfaces:**
- Consumes: Task 14's `Watchers` (`connected`, `gone`, `conn_of`, `brain`, `arrived`, `for_context`, `tab_of`,
  `place_of`); Task 13's `InstanceLinks.located(target)`, `mark_brain(url)`; Task 17's rig; wave 1B's `Rule`,
  `MESSAGE_RULES`, `WATCHER_RECEIVES`, `_role(ws)`; wave B's role stored at accept.
- Produces:
  - the `MESSAGE_RULES` row `"opened_tab": Rule(app=False, watcher=True)` (counted only from a socket that said hello as
    a watcher, like the seven reports); `WATCHER_RECEIVES` gains `"open_tab"` (Task 20 adds the four page rows);
  - `TAB_REPORTS = {"watcher_caps", "tab_grouped", "opened_tab"}` (any copy); the Brain's reports (`items`,
    `replied`, `thread`, `filled`, `reader_status`) count only from `watchers.brain()`;
  - `_to_watcher(message)` sends only to `watchers.brain()`; every copy gets `watcher_hello`;
  - `async _copy_for(target) -> WatcherConn | None`, `async _group_with(conn, key, title, color, target, find)`;
  - `AppServer.place_of(origin) -> Place | None` (wave D calls it).

- [ ] **Step 1: Write the failing tests**

In `tests/test_app_server.py` add:

```python
async def test_the_brains_messages_go_to_the_primary_watcher_only(fake_claude, tmp_path):
    from profile_rig import E1, E2, copy_socket, rig, settled

    server, url, spots, made = await rig(fake_claude, tmp_path, brain=True, events=[{"result": "[]"}])
    add_agent(server.agents, "a1")
    try:
        async with copy_socket(server, url, E1) as (_, primary), copy_socket(server, url, E2) as (_, copy):
            assert await settled(lambda: len(server.watchers.connections()) == 2 and server.brain.watcher)
            for message in ({"type": "notify", "count": 1},
                            {"type": "open_thread", "request": "r1", "url": "https://mail.google.com/x"},
                            {"type": "fill_reply", "request": "r2", "text": "hi"}):
                assert server._to_watcher(message)
            server.agents._broadcast({"type": "permission_request", "agent": "a1", "request": "p1", "server": "x",
                                      "tool": "mcp__x__y", "input": {}})
            brain_types = {"watch_list", "notify", "open_thread", "fill_reply", "permission_request"}
            assert await settled(lambda: brain_types <= {message["type"] for message in primary})
            await asyncio.sleep(0.3)
            assert {message["type"] for message in copy} <= {"watcher_hello", "ping"}  # nothing of the Brain's
            assert [message["type"] for message in copy].count("watcher_hello") == 1
    finally:
        await server.stop()


async def test_brain_reports_count_only_from_the_primary_copy(fake_claude, tmp_path):
    from profile_rig import E1, E2, copy_socket, rig, settled

    server, url, spots, made = await rig(fake_claude, tmp_path, brain=True, events=[{"result": "[]"}])
    server.brain.set_watch({"site": "gmail", "enabled": True, "url_match": "https://mail.google.com/*"})
    items = {"type": "items", "site": "gmail", "items": [
        {"id": "t1", "from": "Maria", "subject": "Launch", "snippet": "Monday?", "url": "https://x/1", "time": "1"}]}
    try:
        async with copy_socket(server, url, E2, link=made["brave"], context="C2") as (copy_ws, _):
            assert await settled(lambda: len(server.watchers.connections()) == 1)
            await copy_ws.send(json.dumps(items))
            await asyncio.sleep(0.5)
            await server.brain.settle()
            assert server.brain.snapshot()["items"] == [] and oneshots(fake_claude[1]) == []  # the Brain's inbox
            conn = server.watchers.connections()[0]
            assert await conn.groups.open("a" * 16, "a1", "Fix", "blue") == {  # its tab reports reach its keeper
                "ok": True, "tab": 401, "window": 7, "group": 9, "new_window": False}
            async with copy_socket(server, url, E1) as (primary_ws, _):
                assert await settled(lambda: server.watchers.brain() is not None)
                await primary_ws.send(json.dumps(items))
                assert await settled(lambda: oneshots(fake_claude[1]) != [], 10)  # the primary feeds the Brain
    finally:
        await server.stop()


async def test_a_claim_goes_to_the_copy_whose_profile_holds_the_tab(fake_claude, tmp_path):
    from profile_rig import E1, E2, copy_socket, rig, settled

    server, url, spots, made = await rig(fake_claude, tmp_path)
    made["brave"].add_page("T1", "about:blank#aib-0123456789abcdef", context="C2")  # it landed in Profile 1
    add_agent(server.agents, "a1").where = spots["work"]
    made["brave"].relay.own("a1", "T1")  # wave 2A: the relay granted the tab the engine created
    try:
        async with copy_socket(server, url, E1) as (_, primary), copy_socket(server, url, E2) as (copy_ws, copy):
            assert await settled(lambda: len(server.watchers.connections()) == 2
                                 and all(conn.place for conn in server.watchers.connections()))
            async with httpx.AsyncClient() as client:
                claim = asyncio.ensure_future(client.post(url + "/agent-claim", headers={
                    "X-AIB-Agent-Token": server.token_for("a1")}, json={"agent": "a1", "target": "T1",
                                                                         "marker": "0123456789abcdef"}))
                assert await settled(lambda: any(message["type"] == "group_tab" for message in copy))
                ask = next(message for message in copy if message["type"] == "group_tab")
                await copy_ws.send(json.dumps({"type": "tab_grouped", "request": ask["request"], "ok": True,
                                               "tab": 412, "window": 1, "group": 9}))
                assert (await claim).json() == {"grouped": True, "tab": 412}
            assert not any(message["type"] == "group_tab" for message in primary)  # it can't see Profile 1's tabs
            conn, tab = server.watchers.tab_of("T1")
            assert (conn.copy, tab) == ("brave-profile-1", 412)
    finally:
        await server.stop()


async def test_place_of_names_a_copys_place(fake_claude, tmp_path):
    from profile_rig import E2, rig

    server, url, spots, made = await rig(fake_claude, tmp_path)
    try:
        await server.watchers.refresh()
        assert server.place_of(E2) == spots["work"] and server.place_of("chrome-extension://nobody") is None
    finally:
        await server.stop()
```

In `tests/test_watcher_rules.py`, the test's copy of `MESSAGE_RULES` gains the row `opened_tab` (app no; watcher yes,
from a socket that said hello as a watcher, as the seven reports), and its copy of `WATCHER_RECEIVES` gains
`open_tab`. With waves A and B merged the copies held 60 types (23 the watcher may send, 52 the app's pages) and 19
received types; now 61, 24, 52 and 20 (Task 20 brings them to the spec's 65, 24, 56 and 20).

In `tests/test_watcher.py`, the `watcher` fixture (as wave B rebuilt it, with wave 2A's connected `BraveLink`) places
its copy in the throwaway Chrome's one profile, before anything says hello:

```python
    from ai_browser.places import Place

    place = Place("", str(profile_folder), "Default")  # the fixture's throwaway Chrome (no known browser owns it)
    server.attach_brave(brave, place=place)  # in place of attach_brave(brave)
    server.watchers.find_places = lambda: {extension_id: [place]}  # its Secure Preferences, as Brave would write them
```

where `profile_folder` and `extension_id` are the fixture's own throwaway profile folder and its watcher's id. Call
`attach_brave` before `allow_watcher`, so the link learns the id.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_app_server.py -k "primary_watcher_only or primary_copy or copy_whose_profile or place_of_names" tests/test_watcher_rules.py -q -p no:randomly`

Expected: FAIL. The copy gets `watch_list` (the latest watcher wins today); a copy's `items` reach the Brain; the
claim goes to the latest watcher; `place_of` doesn't exist; the table tests miss the `opened_tab` row.

- [ ] **Step 3: Split the watcher's roles**

In `src/ai_browser/app/server.py`:

```python
TAB_REPORTS = {"watcher_caps", "tab_grouped", "opened_tab"}  # from any copy, each into its own GroupKeeper
```

`WATCHER_MESSAGES` gains `"opened_tab"`; `MESSAGE_RULES` gains its row, and `WATCHER_RECEIVES` gains `"open_tab"`
(with a comment: "browser-profile-choice: a copy opens a blank tab at a marker").

The watcher's `hello` branch of `_handle` (today's "the latest watcher wins") becomes:

```python
        if kind == "hello" and message.get("view") == "watcher" and self._role(ws) == "watcher":
            conn = self.watchers.connected(ws, queue, ws.headers.get("origin", ""))
            conn.groups.watcher_changed(True)
            queue.put_nowait({"type": "watcher_hello", "build": self.watcher_build})  # every copy reloads when old
            if conn is self.watchers.brain() and self.brain is not None:  # the Brain's watcher: the primary only
                queue.put_nowait(self.brain.watch_message())
                self.brain.store.set_watcher_seen()
                self.brain.watcher = True
            self._job(self.watchers.arrived(conn))  # its files now; again at 2, 5 and 15 s while it is unknown
            self._browser_changed()
```

The reports' branch:

```python
        elif kind in WATCHER_MESSAGES:
            conn = self.watchers.conn_of(ws)  # only a socket that said hello as a watcher
            if conn is not None and (kind in TAB_REPORTS or (self.brain is not None
                                                             and conn is self.watchers.brain())):
                await self._from_watcher(conn, kind, message)
```

`_from_watcher` takes the connection:

```python
    async def _from_watcher(self, conn, kind: str, message: dict) -> None:
        if kind == "watcher_caps":
            conn.groups.caps_from(message)
            return
        if kind == "tab_grouped":
            conn.groups.answered(message)
            return
        if kind == "opened_tab":
            conn.groups.opened(message)
            return
        # The Brain's report branches (items, replied, thread, filled, reader_status) stay below exactly as they are,
        # with one change in `thread`: `self.brave.mark_brain(url)` becomes `self.links.mark_brain(url)`, guarded by
        # `self.links is not None`.
```

`_to_watcher` sends to the Brain's copy only:

```python
    def _to_watcher(self, message: dict) -> bool:
        """A message for the Brain's watcher, the primary copy (Decision 9); False when it isn't connected."""
        if message.get("type") == "open_thread" and isinstance(message.get("url"), str):
            self._thread_urls[str(message.get("request", ""))] = message["url"]
        conn = self.watchers.brain()
        if conn is None:
            return False
        conn.queue.put_nowait(message)
        return True
```

In `_unsubscribe`, the block that cleared the one `_watcher` slot becomes:

```python
        conn = self.watchers.gone(ws)
        if conn is not None:
            conn.groups.watcher_changed(False)  # a claim or an open still waiting ends at once
            if self.brain is not None and conn.copy == "primary":
                self.brain.watcher = self.watchers.brain() is not None
            self._browser_changed()
```

The `_watcher` attribute goes. Grouping goes to the copy whose profile holds the tab:

```python
    async def _copy_for(self, target: str):
        """The connected copy whose context is the tab's: the only copy that can see it (Decision 9). The app's list
        may learn of a brand-new tab a moment after the engine made it. A server with no link (wave 2A's tests) keeps
        one watcher for everything."""
        if self.links is None:
            return self.watchers.brain()
        for _ in range(10):
            found = self.links.located(target)
            if found is not None:
                return self.watchers.for_context(*found)
            await asyncio.sleep(0.05)
        return None

    async def _group(self, key: str, title: str, color: str, target: str, find: dict) -> dict:
        conn = await self._copy_for(target)
        if conn is None:
            return {"grouped": False, "reason": "no_watcher"}
        return await self._group_with(conn, key, title, color, target, find)

    async def _group_with(self, conn, key: str, title: str, color: str, target: str, find: dict) -> dict:
        answer = await conn.groups.group(key, title, color, find)
        if answer.get("grouped") and isinstance(answer.get("tab"), int):
            conn.groups.remember(target, answer["tab"])
        return answer
```

Where `_group_opened` and `_agent_claim`'s opener case read `self.groups.tab_of(opener)`, they read
`self.watchers.tab_of(opener)` (a `(conn, tab)` pair, or None for "not_found") and group through that same
connection with `_group_with(conn, …, {"opener_tab": tab, "url": url})`. `_ungroup`:

```python
    def _ungroup(self, targets: list[str]) -> None:
        """Out of their group (a handed tab taken back, or let go when its agent closes): the copy that grouped each
        takes it out."""
        for target in targets:
            found = self.watchers.tab_of(target)
            if found is not None:
                conn, tab = found
                conn.groups.ungroup([tab])
            self._own(target, None)
```

and for wave D:

```python
    def place_of(self, origin: str) -> Place | None:
        """A watcher copy's browser and profile (wave D's side chat names its place by it)."""
        return self.watchers.place_of(origin)
```

- [ ] **Step 4: Run them, and the watcher's own suites**

Run: `uv run pytest tests/test_app_server.py tests/test_watcher_rules.py -q -p no:randomly`

Then: `uv run pytest tests/test_watcher.py tests/test_watcher_groups.py -q -p no:randomly`

Expected: PASS (the second run skips without Google Chrome, and on Windows).

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/server.py tests/test_app_server.py tests/test_watcher_rules.py tests/test_watcher.py
git commit -m "feat: the Brain keeps the primary watcher, and every copy groups the tabs of its own profile"
```

### Task 19: The engine routes: `/agent-open`, what `/agent-status` says, a session's place in `/agent-hello`

**Files:**
- Modify: `src/ai_browser/app/server.py` (new route `/agent-open`, `_open_tab`, `_marker_target`, `_close_late`,
  `_late_open`, `OPEN_REASONS`; `_agent_status`; wave 2A's `_agent_hello`, `_session_list`; the watcher's hello sets
  `late`)
- Test: `tests/test_app_server.py`

**Interfaces:**
- Consumes: Task 10's `GroupKeeper.open(marker, key, title, color, wait)`, `can_open()`, `late`; Task 9's (and the
  fake's) `relay.note_marker`, `assign`, `close_marker`; Task 12's `targets_showing`, `context_of`; Task 14's
  `status_for`, `for_place`, `context`, `can_group`; Task 17's `_place_of_identity`, `_own_on`, rig; wave 2A's
  `_engine_body`, `_token_ok`, `_owner_of`, `_record_tab`, `tokens`, the relays' cut-off sets; `grouping.MARKER`,
  `marker_url`; wave A's `browsers.installed()`; Task 2's `plain_profile`, `Place`.
- Produces:
  - `POST /agent-open {agent, marker}` → `{"opened": true, "target", "tab", "grouped", "new_window"}` or
    `{"opened": false, "reason": "no_watcher" | "asleep" | "shared" | "unknown" | "not_connected" | "timeout" |
    "not_found" | "wrong_profile" | "refused"}` (always 200); 400 for a marker that isn't 16 hex or was used this run;
    403 and 404 as the other routes;
  - `GET /agent-status` adds `"open"`, `"context"` and `"why"` (plan decision 1); `groups` is
    `watchers.can_group(<the identity's browser>)` (Decision 6);
  - `/agent-hello` takes `"place": {"browser", "profile"}`: an installed browser offered to agents and a plain profile
    folder name are recorded (making that browser's link, connecting nothing), echoed, with a `cdp_token`; anything
    else is recorded with no place and answered `{"place": null}` with no token; a cut-off session still gets 410;
  - `self.sessions[id]["where"]` (never broadcast: `_session_list` keeps `id`, `name`, `color`, `tabs`, `pid`).

- [ ] **Step 1: Write the failing tests**

In `tests/test_app_server.py` add:

```python
def agent_token(server, agent_id):
    return {"X-AIB-Agent-Token": server.token_for(agent_id)}


async def open_for(url, server, agent_id, marker):
    async with httpx.AsyncClient() as client:
        return await client.post(url + "/agent-open", headers=agent_token(server, agent_id),
                                 json={"agent": agent_id, "marker": marker}, timeout=10)


async def two_copies_placed(server):
    from profile_rig import settled

    assert await settled(lambda: len(server.watchers.connections()) == 2
                         and all(conn.place and conn.groups.can_open() for conn in server.watchers.connections()))


async def test_agent_open_goes_to_the_watcher_of_the_agents_profile(fake_claude, tmp_path):
    from profile_rig import E1, E2, copy_socket, rig

    server, url, spots, made = await rig(fake_claude, tmp_path)
    add_agent(server.agents, "a1").where = spots["work"]
    try:
        async with copy_socket(server, url, E1, link=made["brave"], context="C1") as (_, primary), \
                copy_socket(server, url, E2, link=made["brave"], context="C2") as (_, copy):
            await two_copies_placed(server)
            answer = (await open_for(url, server, "a1", "0123456789abcdef")).json()
            assert answer == {"opened": True, "target": "T-012345", "tab": 401, "grouped": True, "new_window": False}
            assert not [message for message in primary if message["type"] == "open_tab"]
            [ask] = [message for message in copy if message["type"] == "open_tab"]
            assert {key: ask[key] for key in ("marker", "key", "title", "color")} == {
                "marker": "0123456789abcdef", "key": "a1", "title": "Fix the footer", "color": "blue"}
            assert "url" not in ask  # the watcher builds the address itself
            assert made["brave"].relay.assigned == [("T-012345", "a1")]
            assert "0123456789abcdef" in made["brave"].relay.markers
            assert server.agents.agents["a1"].tabs == ["T-012345"] and made["brave"].owners["T-012345"]["id"] == "a1"
            conn, tab = server.watchers.tab_of("T-012345")
            assert (conn.copy, tab) == ("brave-profile-1", 401)
    finally:
        await server.stop()


async def test_agent_open_without_that_profiles_watcher_says_why(fake_claude, tmp_path):
    from profile_rig import E1, copy_socket, rig, settled

    server, url, spots, made = await rig(fake_claude, tmp_path)
    add_agent(server.agents, "a1").where = spots["work"]
    try:
        async with copy_socket(server, url, E1, link=made["brave"], context="C1") as (_, primary):
            assert await settled(lambda: server.watchers.brain() is not None and server.watchers.brain().place)
            assert (await open_for(url, server, "a1", "0123456789abcdef")).json() == {
                "opened": False, "reason": "asleep"}  # the files place E2 in Profile 1; it isn't connected
            server.watchers.find_places = lambda: {"e1": [spots["personal"]]}
            await server.watchers.refresh()
            assert (await open_for(url, server, "a1", "1123456789abcdef")).json() == {
                "opened": False, "reason": "no_watcher"}
            assert not [message for message in primary if message["type"] == "open_tab"]  # never sent to E1
    finally:
        await server.stop()


async def test_a_tab_in_the_wrong_profile_is_closed_and_refused(fake_claude, tmp_path):
    from profile_rig import E2, copy_socket, rig, settled

    server, url, spots, made = await rig(fake_claude, tmp_path)
    add_agent(server.agents, "a1").where = spots["work"]
    try:
        async with copy_socket(server, url, E2, link=made["brave"], context="C1"):  # "can't happen": it is checked
            assert await settled(lambda: server.watchers.connections() and server.watchers.connections()[0].place)
            answer = (await open_for(url, server, "a1", "0123456789abcdef")).json()
            assert answer == {"opened": False, "reason": "wrong_profile"}
            assert made["brave"].relay.closed_markers == [("T-012345", "0123456789abcdef")]
            assert made["brave"].relay.assigned == [] and server.agents.agents["a1"].tabs == []
    finally:
        await server.stop()


async def test_agent_open_tokens_and_markers(fake_claude, tmp_path):
    from profile_rig import E2, copy_socket, rig, settled

    server, url, spots, made = await rig(fake_claude, tmp_path)
    add_agent(server.agents, "a1").where = spots["work"]
    try:
        async with copy_socket(server, url, E2, link=made["brave"], context="C2"):
            assert await settled(lambda: server.watchers.connections() and server.watchers.connections()[0].place)
            async with httpx.AsyncClient() as client:
                body = {"agent": "a1", "marker": "0123456789abcdef"}
                assert (await client.post(url + "/agent-open", json=body)).status_code == 403
                session = {"X-AIB-Agent-Token": server.session_token}
                assert (await client.post(url + "/agent-open", json=body, headers=session)).status_code == 403
                nobody = {"agent": "a9", "marker": "0123456789abcdef"}
                assert (await client.post(url + "/agent-open", json=nobody,
                                          headers=agent_token(server, "a9"))).status_code == 404
            assert (await open_for(url, server, "a1", "not-hex-at-all!!")).status_code == 400
            assert (await open_for(url, server, "a1", "0123456789abcdef")).json()["opened"] is True
            assert (await open_for(url, server, "a1", "0123456789abcdef")).status_code == 400  # used once
            made["brave"].state = "ready"  # the agent's browser isn't connected: its context can't be checked
            began = time.monotonic()
            assert (await open_for(url, server, "a1", "2123456789abcdef")).json() == {
                "opened": False, "reason": "not_connected"}
            assert time.monotonic() - began < 0.5  # at once
    finally:
        await server.stop()


async def test_two_agents_open_tabs_at_once_in_one_profile(fake_claude, tmp_path):  # Review Focus 1
    from profile_rig import E2, rig, settled

    server, url, spots, made = await rig(fake_claude, tmp_path)
    add_agent(server.agents, "a1").where = spots["work"]
    add_agent(server.agents, "a2", "Check prices", "green").where = spots["work"]
    try:
        async with connect(socket_url(server, url), origin=E2) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "watcher"}))
            await ws.send(json.dumps({"type": "watcher_caps", "groups": True, "open": True}))
            assert await settled(lambda: server.watchers.connections()
                                 and server.watchers.connections()[0].place
                                 and server.watchers.connections()[0].groups.can_open())
            first = asyncio.ensure_future(open_for(url, server, "a1", "a" * 16))
            second = asyncio.ensure_future(open_for(url, server, "a2", "b" * 16))
            asks = []
            while len(asks) < 2:
                message = json.loads(await asyncio.wait_for(ws.recv(), 5))
                if message["type"] == "open_tab":
                    asks.append(message)
            for tab, ask in enumerate(reversed(asks), 500):  # answered out of order
                made["brave"].add_page(f"T-{ask['marker'][:6]}", f"about:blank#aib-{ask['marker']}", "C2")
                await ws.send(json.dumps({"type": "opened_tab", "request": ask["request"], "ok": True, "tab": tab,
                                          "window": 7, "group": 9, "new_window": False}))
            one, two = (await first).json(), (await second).json()
        assert (one["target"], two["target"]) == ("T-aaaaaa", "T-bbbbbb")
        assert sorted(made["brave"].relay.assigned) == [("T-aaaaaa", "a1"), ("T-bbbbbb", "a2")]
    finally:
        await server.stop()


async def test_a_late_open_tab_is_closed_by_its_marker(fake_claude, tmp_path, monkeypatch):
    from ai_browser.app import server as server_module
    from profile_rig import E2, copy_socket, rig, settled

    monkeypatch.setattr(server_module, "OPEN_WAIT", 0.3)
    server, url, spots, made = await rig(fake_claude, tmp_path)
    add_agent(server.agents, "a1").where = spots["work"]
    marker = "0123456789abcdef"
    try:
        async with copy_socket(server, url, E2, answer=False) as (ws, seen):
            assert await settled(lambda: server.watchers.connections() and server.watchers.connections()[0].place)
            assert (await open_for(url, server, "a1", marker)).json() == {"opened": False, "reason": "timeout"}
            ask = next(message for message in seen if message["type"] == "open_tab")
            made["brave"].add_page("T-late", f"about:blank#aib-{marker}", "C2")
            await ws.send(json.dumps({"type": "opened_tab", "request": ask["request"], "ok": True, "tab": 9,
                                      "window": 7, "group": None, "new_window": False}))
            assert await settled(lambda: made["brave"].relay.closed_markers == [("T-late", marker)])
            assert made["brave"].relay.assigned == []  # no stray blank tab is left, and nobody gets it
    finally:
        await server.stop()


async def test_agent_status_says_whether_the_profiles_watcher_can_open_tabs(fake_claude, tmp_path):
    from profile_rig import E2, copy_socket, rig, settled

    server, url, spots, made = await rig(fake_claude, tmp_path)
    add_agent(server.agents, "a1").where = spots["work"]

    async def status():
        async with httpx.AsyncClient() as client:
            answer = (await client.get(url + "/agent-status?agent=a1", headers=agent_token(server, "a1"))).json()
        return {key: answer[key] for key in ("open", "context", "why")}

    try:
        await server.watchers.refresh()
        assert await status() == {"open": False, "context": None, "why": "asleep"}
        async with copy_socket(server, url, E2) as (ws, _):
            assert await settled(lambda: server.watchers.connections() and server.watchers.connections()[0].place
                                 and server.watchers.connections()[0].groups.can_open())
            assert await status() == {"open": True, "context": "C2", "why": ""}
            await ws.send(json.dumps({"type": "watcher_caps", "groups": True, "open": False}))  # an older copy
            assert await settled(lambda: not server.watchers.connections()[0].groups.can_open())
            assert await status() == {"open": False, "context": "C2", "why": "refused"}
            made["brave"].state = "ready"
            assert (await status())["why"] == "not_connected"
    finally:
        await server.stop()


async def test_agent_status_groups_only_when_the_profile_used_last_has_a_copy(fake_claude, tmp_path):
    from profile_rig import E1, copy_socket, rig, settled

    server, url, spots, made = await rig(fake_claude, tmp_path)
    add_agent(server.agents, "a1").where = spots["work"]  # its own place has no copy: Decision 6's fallback

    async def groups():
        async with httpx.AsyncClient() as client:
            return (await client.get(url + "/agent-status?agent=a1", headers=agent_token(server, "a1"))).json()["groups"]

    try:
        async with copy_socket(server, url, E1):
            assert await settled(lambda: server.watchers.brain() is not None and server.watchers.brain().place)
            assert await groups() is True  # E1's context C1 is the profile used last: a context-less tab lands there
            made["brave"].default_context = "C9"  # the user clicked into a profile with no copy
            assert await groups() is False  # though E1 is still connected
    finally:
        await server.stop()


async def test_agent_hello_records_and_answers_the_sessions_place(fake_claude, tmp_path, monkeypatch):
    from ai_browser.places import Place
    from places_rig import install
    from profile_rig import rig, settled

    folders = install(monkeypatch, tmp_path, "brave", "chrome", default="brave")
    spots = {"personal": Place("brave", str(folders["brave"]), "Default"),
             "work": Place("brave", str(folders["brave"]), "Profile 1"),
             "chrome": Place("chrome", str(folders["chrome"]), "Default")}
    server, url, _, made = await rig(fake_claude, tmp_path, spots=spots)
    session = {"X-AIB-Agent-Token": server.session_token}

    async def hello(agent, place):
        async with httpx.AsyncClient() as client:
            return await client.post(url + "/agent-hello", headers=session,
                                     json={"agent": agent, "pid": os.getpid(), "place": place})

    try:
        brave = (await hello("cc-one", {"browser": "brave", "profile": "Profile 1"})).json()
        assert brave["place"] == {"browser": "brave", "profile": "Profile 1"} and isinstance(brave["cdp_token"], str)
        chrome = (await hello("cc-two", {"browser": "chrome", "profile": "Default"})).json()
        assert chrome["place"] == {"browser": "chrome", "profile": "Default"} and chrome["cdp_token"]
        assert "chrome" in made and made["chrome"].asked == []  # Chrome's link is made, and connects nothing
        for place in ({"browser": "", "profile": "Default"}, {"browser": "brave", "profile": "../x"},
                      {"browser": "edge", "profile": "Default"}, None):
            answer = (await hello("cc-three", place)).json()
            assert answer == {"place": None}  # it connects directly; no token
        assert server.sessions["cc-two"]["where"] == spots["chrome"]
        assert all("where" not in row for row in server._session_list())
        made["brave"].relay.cut_off = {"cc-gone"}  # wave 2A: the user disconnected that session in AI Home
        assert (await hello("cc-gone", {"browser": "brave", "profile": "Default"})).status_code == 410
        async with httpx.AsyncClient() as client:
            await client.post(url + "/agent-bye", headers=session, json={"agent": "cc-two"})
        assert await settled(lambda: made["chrome"].closes == 1)  # Chrome's last session ended: its link goes
    finally:
        await server.stop()
```

(`os`, `time` and `socket_url` are this file's own imports and helpers.) The earlier test that compares a whole
`/agent-status` answer (`test_agent_status_lists_only_that_agents_handed_tabs`) expects three more keys: `"open":
False, "context": None, "why": "no_watcher"`.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_app_server.py -k "agent_open or open_tabs_at_once or late_open or agent_status or agent_hello" -q -p no:randomly`

Expected: FAIL. `/agent-open` answers 404 (no route); `/agent-status` has no `open`; `/agent-hello` answers without
`place`.

- [ ] **Step 3: Write the routes**

In `src/ai_browser/app/server.py`, import `OPEN_WAIT` from `.groups` and `marker_url` from `..grouping`, and add:

```python
OPEN_REASONS = {"missing": "no_watcher", "asleep": "asleep", "shared": "shared", "unknown": "unknown"}
```

`AppServer.__init__` gains `self._markers: set[str] = set()  # /agent-open markers used this run`. The route list
gains `Route("/agent-open", self._agent_open, methods=["POST"])`. In the watcher's `hello` branch (Task 18), after
`conn = self.watchers.connected(...)`:

```python
            conn.groups.late = lambda marker, conn=conn: self._job(self._late_open(conn, marker))
```

The route and its work:

```python
    async def _agent_open(self, request: Request) -> Response:
        """POST /agent-open {agent, marker} (browser-profile-choice Decision 4). Every "opened": false is a 200, so the
        engine reads its reason; a bad or reused marker is a 400."""
        body, refused = await self._engine_body(request)
        if refused is not None:
            return refused
        identity, marker = body["agent"], body.get("marker")
        owner = self._owner_of(identity)
        if owner is None:
            return Response(status_code=404)
        if not isinstance(marker, str) or not MARKER.match(marker) or marker in self._markers:
            return Response(status_code=400)
        self._markers.add(marker)
        return JSONResponse(await self._open_tab(identity, owner, marker))

    async def _open_tab(self, identity: str, owner: dict, marker: str) -> dict:
        """The copy in the identity's place opens a blank background tab at the marker; the app finds that one target
        in its own list, checks its profile, and gives it to that agent or session alone (Relay.assign)."""
        place = self._place_of_identity(identity)
        status = self.watchers.status_for(place)
        if status != "on":
            return {"opened": False, "reason": OPEN_REASONS.get(status, "no_watcher")}  # nothing is sent
        conn = self.watchers.for_place(place)
        link = self.links.link_for(place)
        context = self.watchers.context(conn)
        if link is None or link.state != "connected" or context is None:
            return {"opened": False, "reason": "not_connected"}
        deadline = asyncio.get_running_loop().time() + OPEN_WAIT
        link.relay.note_marker(marker)
        answer = await conn.groups.open(marker, identity, owner["name"], owner["color"], wait=OPEN_WAIT)
        if not answer.get("ok"):
            return {"opened": False, "reason": answer.get("reason", "refused")}
        target = await self._marker_target(link, marker, deadline)
        if target is None:
            self._job(self._close_late(link, marker, OPEN_WAIT))  # it may show up a moment later: never left behind
            return {"opened": False, "reason": "not_found"}
        if link.context_of(target) != context:
            await link.relay.close_marker(target, marker)
            return {"opened": False, "reason": "wrong_profile"}
        if not link.relay.assign(target, identity):
            return {"opened": False, "reason": "not_found"}
        conn.groups.remember(target, answer["tab"])
        self._own_on(link, target, owner)
        self._record_tab(identity, target)
        return {"opened": True, "target": target, "tab": answer["tab"], "grouped": answer.get("group") is not None,
                "new_window": answer.get("new_window") is True}

    async def _marker_target(self, link, marker: str, deadline: float) -> str | None:
        """The one target the app's own list shows at the marker's address, by the deadline."""
        url = marker_url(marker)
        while True:
            found = link.targets_showing(url)
            if len(found) == 1:
                return found[0]
            if asyncio.get_running_loop().time() >= deadline:
                return None
            await asyncio.sleep(0.05)

    async def _close_late(self, link, marker: str, wait: float) -> None:
        """A blank open_tab tab nobody will use (its answer came late, or its target showed late): closed by its
        marker, which was secret and used once, so no other tab can match."""
        deadline = asyncio.get_running_loop().time() + wait
        while asyncio.get_running_loop().time() < deadline:
            for target in link.targets_showing(marker_url(marker)):
                await link.relay.close_marker(target, marker)
                return
            await asyncio.sleep(0.1)

    async def _late_open(self, conn, marker: str) -> None:
        link = self.links.link_for(conn.place) if self.links is not None else None
        if link is not None:
            await self._close_late(link, marker, OPEN_WAIT)
```

`_agent_status` keeps its token and owner checks and its handed list (read from `self._tab_rows()`), and answers:

```python
        place = self._place_of_identity(agent_id)
        conn = self.watchers.for_place(place)
        status = self.watchers.status_for(place)
        context = self.watchers.context(conn) if conn is not None else None
        link = self.links.link_for(place) if self.links is not None and place is not None else None
        connected = link is not None and link.state == "connected"
        opens = status == "on" and connected and context is not None and conn.groups.can_open()
        why = "" if opens else OPEN_REASONS.get(status) or ("refused" if connected and context else "not_connected")
        groups = self.watchers.can_group(place.instance) if self.links is not None and place is not None else \
            self.links is None and self.groups.available() == "on"  # a server with no link: its one watcher
        return JSONResponse({"groups": groups, "handed": handed, "open": opens, "context": context, "why": why})
```

`_agent_hello` (wave 2A's) keeps its token check and its 410 for a cut-off id, and records the place:

```python
    def _session_place(self, value) -> Place | None:
        """A session's own place, when the app can hold that browser: an installed browser offered to agents, and a
        plain profile folder name. Ids only; the folder comes from browsers.installed()."""
        if not isinstance(value, dict) or not plain_profile(value.get("profile")):
            return None
        row = next((row for row in browsers.installed() if row.id == value.get("browser") and row.agents), None)
        return Place(row.id, str(row.data_dir), value["profile"]) if row is not None else None

    def _cut_off(self, identity: str) -> bool:
        return self.links is not None and any(identity in getattr(link.relay, "cut_off", ())
                                              for _, link in self.links.all())
```

and its body, after wave 2A's checks:

```python
        where = await asyncio.to_thread(self._session_place, body.get("place"))
        known = self.sessions.get(session_id)
        self.sessions[session_id] = {"id": session_id, "name": "Claude Code", "color": "orange",
                                     "tabs": known["tabs"] if known else [], "pid": pid, "where": where}
        self._sessions_changed()
        if where is None:  # a folder no installed browser offered to agents owns: it connects directly
            return JSONResponse({"place": None})
        self.links.ensure(where)  # its browser's link; it connects on the session's first command
        return JSONResponse({"cdp_token": self.tokens.mint(session_id), "place": where.public()})
```

with wave 2A's cut-off check written as `if self._cut_off(session_id): return Response(status_code=410)`. Finally:

```python
    def _session_list(self) -> list[dict]:
        """Sessions as pages see them: never their place's folder."""
        return [{key: (list(session[key]) if key == "tabs" else session[key])
                 for key in ("id", "name", "color", "tabs", "pid")} for session in self.sessions.values()]
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_app_server.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/server.py tests/test_app_server.py
git commit -m "feat: /agent-open has the agent's profile's watcher open its tab, and sessions say hello with their place"
```

### Task 20: The pages' messages: `browsers`, `place_set`, `watcher_copy`, `restart_in`; Hand over in one browser

**Files:**
- Modify: `src/ai_browser/app/server.py` (`PLACE_MESSAGES`, `_place_command`, `_set_place`, `_watcher_copy`,
  `_copy_folder`, `_restart_in`, `_browsers_view`, `_broadcast_browsers`, `_tab_place`; `_hand`; `new_task`'s
  `adopt`; wave B's `_agents_browser`; the four `MESSAGE_RULES` rows)
- Modify: `tests/test_watcher_rules.py` (the four rows in its copy)
- Test: `tests/test_app_server.py`

**Interfaces:**
- Consumes: Task 15's `Where.browsers_view`, `check_place_set`, `describe`, `extensions_page`; Task 2's
  `places.save_place`; Task 11's `WatcherCopies.make`, `primary`; Task 14's `Watchers.placed_copy`, `refresh`,
  `sync`, `for_context`; Task 13's `set_current`, `located`, `connect`; Task 16's `AgentManager.restart`,
  `create(..., place=)`; Task 17's `_prune`, `on_browser_changed`; wave B's `extension_path`, `extension_id_for`,
  `server.reveal`, `platforms.open_url(url, browser=)`.
- Produces:
  - `MESSAGE_RULES` rows `"browsers"`, `"place_set"`, `"watcher_copy"`, `"restart_in"`: `Rule(app=True,
    watcher=False)`; `PLACE_MESSAGES` with the same four;
  - pages → server: `browsers {}` (answered with a fresh view), `place_set {"browser", "profile"}`, `watcher_copy
    {"browser", "profile"}`, `restart_in {"id"}`;
  - server → pages: `browsers` (Task 15's shape), `place_changed {"label", "elsewhere", "elsewhere_labels"}`,
    `watcher_copy {"browser", "profile", "folder", "extensions"}`, and `error {"text"}`;
  - `_set_place(place)` saves, switches, connects a new browser once, re-filters, broadcasts and prunes;
  - Hand over and `new_task`'s `adopt` follow Decision 14; a task started in a handed tab takes that tab's place
    (`_tab_place(target) -> Place | None`);
  - wave B's `_agents_browser()` returns the current place's `Installed` row (its `_open_url` opens websites
    there).

- [ ] **Step 1: Write the failing tests**

In `tests/test_app_server.py` add:

```python
def installed_spots(monkeypatch, tmp_path):
    from ai_browser.places import Place
    from places_rig import install

    folders = install(monkeypatch, tmp_path, "brave", "chrome", default="brave")
    return folders, {"personal": Place("brave", str(folders["brave"]), "Default"),
                     "work": Place("brave", str(folders["brave"]), "Profile 1"),
                     "chrome": Place("chrome", str(folders["chrome"]), "Default")}


async def test_place_set_changes_new_agents_only(fake_claude, tmp_path, monkeypatch):
    from ai_browser.settings import read_settings
    from profile_rig import rig
    from ui_socket import ui_socket

    folders, spots = installed_spots(monkeypatch, tmp_path)
    server, url, _, made = await rig(fake_claude, tmp_path, spots=spots)
    try:
        first = await server.agents.create("one")
        async with ui_socket(server, url) as page:
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            await recv(page)
            await page.send(json.dumps({"type": "place_set", "browser": "brave", "profile": "Profile 1"}))
            seen = await until(page, lambda message: message["type"] == "browsers")
            changed = next(message for message in seen if message["type"] == "place_changed")
            assert changed == {"type": "place_changed", "label": "Brave · Work", "elsewhere": 1,
                               "elsewhere_labels": ["Brave · Personal"]}
            assert next(message for message in seen if message["type"] == "browser")["place"]["label"] == "Brave · Work"
            assert seen[-1]["current"] == {"browser": "brave", "profile": "Profile 1"}
        second = await server.agents.create("two")
        assert (first.where, second.where) == (spots["personal"], spots["work"])
        assert (first.bridge.env["AIB_CHROME_PROFILE"], second.bridge.env["AIB_CHROME_PROFILE"]) == ("Default",
                                                                                                    "Profile 1")
        assert read_settings(tmp_path / "home")["agents_browser"] == {
            "id": "brave", "user_data_dir": str(folders["brave"]), "profile": "Profile 1"}
        assert server.place_automatic is False
    finally:
        await server.stop()


async def test_place_set_takes_ids_never_paths(fake_claude, tmp_path, monkeypatch):
    from profile_rig import rig
    from ui_socket import ui_socket

    folders, spots = installed_spots(monkeypatch, tmp_path)
    server, url, _, made = await rig(fake_claude, tmp_path, spots=spots)
    try:
        async with ui_socket(server, url) as page:
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            await recv(page)
            await page.send(json.dumps({"type": "place_set", "browser": "brave", "profile": "Profile 1",
                                        "user_data_dir": str(tmp_path / "elsewhere")}))
            await until(page, lambda message: message["type"] == "browsers")
            assert server.links.current == spots["work"]  # the folder came from browsers.installed()
            for wrong, text in (({"browser": "firefox", "profile": "Default"},
                                 "AI Browser can't use that browser for agents: pick another one in Settings"),
                                ({"browser": "brave", "profile": "Profile 9"}, "That profile isn't in Brave any more")):
                await page.send(json.dumps({"type": "place_set", **wrong}))
                assert (await until(page, lambda message: message["type"] == "error"))[-1]["text"] == text
            assert server.links.current == spots["work"]  # nothing changed
    finally:
        await server.stop()


async def test_a_browser_switch_connects_once_and_a_profile_switch_never(fake_claude, tmp_path, monkeypatch):
    from profile_rig import rig, settled
    from ui_socket import ui_socket

    folders, spots = installed_spots(monkeypatch, tmp_path)
    server, url, _, made = await rig(fake_claude, tmp_path, spots=spots, state="ready")
    changed = []
    server.on_browser_changed = changed.append
    try:
        async with ui_socket(server, url) as page:
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            await recv(page)
            await page.send(json.dumps({"type": "place_set", "browser": "brave", "profile": "Profile 1"}))
            await until(page, lambda message: message["type"] == "browsers")
            assert made["brave"].asked == [] and changed == []  # a profile: no connection, no question
            await page.send(json.dumps({"type": "place_set", "browser": "chrome", "profile": "Default"}))
            await until(page, lambda message: message["type"] == "browsers")
            assert await settled(lambda: made["chrome"].asked == [("connect", "")])  # once, right after the click
            assert changed == [spots["chrome"]]  # link.json names the new browser
            assert await settled(lambda: made["brave"].closes == 1)  # nobody works in Brave: its link goes
    finally:
        await server.stop()


async def test_watcher_copy_makes_the_profiles_folder_and_allows_its_origin(fake_claude, tmp_path, monkeypatch):
    from ai_browser.extension_id import extension_id_for, extension_path
    from profile_rig import rig
    from ui_socket import ui_socket

    folders, spots = installed_spots(monkeypatch, tmp_path)
    server, url, _, made = await rig(fake_claude, tmp_path, spots=spots)
    shown = []
    server.reveal = lambda path: shown.append(path) or True
    try:
        async with ui_socket(server, url) as page:
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            await recv(page)
            await page.send(json.dumps({"type": "watcher_copy", "browser": "brave", "profile": "Profile 2"}))
            answer = (await until(page, lambda message: message["type"] == "watcher_copy"))[-1]
            folder = tmp_path / "home" / "app" / "watchers" / "brave-profile-2"
            assert answer == {"type": "watcher_copy", "browser": "brave", "profile": "Profile 2",
                              "folder": extension_path(folder), "extensions": "brave://extensions"}
            assert shown == [extension_path(folder)] and (folder / "config.json").is_file()
            assert server.watchers.allowed(f"chrome-extension://{extension_id_for(folder)}")
            await page.send(json.dumps({"type": "watcher_copy", "browser": "brave", "profile": "Profile 9"}))
            assert (await until(page, lambda message: message["type"] == "error"))[-1]["text"] == \
                "That profile isn't in Brave any more"
    finally:
        await server.stop()


async def test_place_set_watcher_copy_and_restart_in_are_refused_from_the_watchers_origin(fake_claude, tmp_path,
                                                                                            monkeypatch):
    from profile_rig import E1, copy_socket, rig

    folders, spots = installed_spots(monkeypatch, tmp_path)
    server, url, _, made = await rig(fake_claude, tmp_path, spots=spots)
    add_agent(server.agents, "a1").where = spots["chrome"]
    try:
        async with copy_socket(server, url, E1) as (ws, seen):
            for message in ({"type": "place_set", "browser": "chrome", "profile": "Default"},
                            {"type": "watcher_copy", "browser": "brave", "profile": "Profile 2"},
                            {"type": "restart_in", "id": "a1"}, {"type": "browsers"}):
                await ws.send(json.dumps(message))
            await asyncio.sleep(0.5)
        assert server.links.current == spots["personal"] and not (tmp_path / "home" / "settings.json").exists()
        assert not (tmp_path / "home" / "app" / "watchers").exists() and list(server.agents.agents) == ["a1"]
        assert not {"browsers", "watcher_copy", "place_changed"} & {message["type"] for message in seen}
    finally:
        await server.stop()


async def test_the_watcher_never_receives_an_agents_place(fake_claude, tmp_path):
    from profile_rig import E1, copy_socket, rig, settled

    server, url, spots, made = await rig(fake_claude, tmp_path)
    try:
        async with copy_socket(server, url, E1) as (_, seen):
            await server.agents.create("one")  # its row carries `place` for AI Browser's own pages
            assert await settled(lambda: any(message["type"] == "agent" for message in seen))
            rows = [message["agent"] for message in seen if message["type"] == "agent"]
            assert all("place" not in row for row in rows) and str(tmp_path) not in json.dumps(seen)
    finally:
        await server.stop()


async def test_restart_in_stops_and_starts_the_same_words_in_the_current_place(fake_claude, tmp_path):
    from profile_rig import rig, settled
    from ui_socket import ui_socket

    server, url, spots, made = await rig(fake_claude, tmp_path)
    try:
        old = await server.agents.create("Fix the footer", ["web-qa"], "opus")
        assert await settled(lambda: old.state == "your_turn")
        server.agents.tab_event(old.id, "tab_opened", "T1")
        async with ui_socket(server, url) as page:
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            await recv(page)
            await page.send(json.dumps({"type": "restart_in", "id": old.id}))
            assert (await until(page, lambda message: message["type"] == "error"))[-1]["text"] == \
                "That agent already works where new agents browse"
            server.links.set_current(spots["chrome"])  # as place_set does
            server.agents.place = spots["chrome"]
            await page.send(json.dumps({"type": "restart_in", "id": old.id}))
            assert await settled(lambda: len(server.agents.agents) == 2)
        new = next(agent for agent in server.agents.agents.values() if agent is not old)
        assert (new.task, new.skills, new.model, new.servers) == (old.task, old.skills, old.model, old.servers)
        assert new.where == spots["chrome"] and old.id in server.agents.agents  # stopped, not closed
        assert made["brave"].closed == [] and old.tabs == ["T1"]  # its tabs stay open
    finally:
        await server.stop()


async def test_hand_over_stays_within_one_browser(fake_claude, tmp_path):
    from profile_rig import E2, copy_socket, rig, settled
    from ui_socket import ui_socket

    server, url, spots, made = await rig(fake_claude, tmp_path)
    made["brave"].add_page("U1", "https://shop.example/", context="C2", title="Shop")
    made["brave"].add_page("U2", "https://mail.example/", context="C2", title="Mail")
    add_agent(server.agents, "a2", "Check prices", "green").where = spots["chrome"]
    add_agent(server.agents, "a3", "Work task", "cyan").where = spots["work"]
    try:
        async with copy_socket(server, url, E2, link=made["brave"], context="C2"), ui_socket(server, url) as page:
            assert await settled(lambda: server.watchers.connections() and server.watchers.connections()[0].place)
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            await recv(page)
            await page.send(json.dumps({"type": "hand_tab", "id": "a2", "target": "U1"}))
            error = (await until(page, lambda message: message["type"] == "error"))[-1]["text"]
            assert error == "Check prices works in another browser: it can only take tabs from there"
            assert "U1" not in server.agents.agents["a2"].adopted
            await page.send(json.dumps({"type": "hand_tab", "id": "a3", "target": "U1"}))  # Brave, another profile
            assert await settled(lambda: "U1" in server.agents.agents["a3"].adopted)
            await page.send(json.dumps({"type": "new_task", "text": "reply to it", "adopt": "U2", "request": "r1"}))
            created = (await until(page, lambda message: message["type"] == "created"))[-1]
            assert server.agents.agents[created["id"]].where == spots["work"]  # the handed tab's profile (Decision 3)
    finally:
        await server.stop()


async def test_websites_open_in_the_current_places_browser(fake_claude, tmp_path, monkeypatch):
    from ai_browser import platforms
    from profile_rig import rig, settled
    from ui_socket import ui_socket

    folders, spots = installed_spots(monkeypatch, tmp_path)
    server, url, _, made = await rig(fake_claude, tmp_path, spots=spots, current="chrome")
    opened = []
    monkeypatch.setattr(platforms, "open_url", lambda address, browser=None, system=None: opened.append(
        (address, browser.id if browser is not None else None)) or True)
    try:
        async with ui_socket(server, url) as page:
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            await recv(page)
            await page.send(json.dumps({"type": "open_url", "url": "https://example.com"}))
            assert await settled(lambda: opened == [("https://example.com", "chrome")])
    finally:
        await server.stop()
```

In `tests/test_watcher_rules.py`, the test's copy gains the four rows `browsers`, `place_set`, `watcher_copy` and
`restart_in` (app yes, watcher no): 65 types, 24 for the watcher, 56 for the app's pages, and 20 received.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_app_server.py -k "place_set or watcher_copy or restart_in or hand_over_stays or never_receives_an_agents_place or current_places_browser" tests/test_watcher_rules.py -q -p no:randomly`

Expected: FAIL. `place_set`, `watcher_copy`, `restart_in` and `browsers` do nothing (no row, no handler); Hand over
gives a Chrome agent a Brave tab; `open_url` opens in the browser `own_browser_dir()` named. The two guards
(`…refused_from_the_watchers_origin` and `…never_receives_an_agents_place`) PASS already: wave 1B drops a type with
no row for everyone and trims agent rows to `WATCHER_AGENT_FIELDS`. They pin that neither changes.

- [ ] **Step 3: Write the page messages**

In `src/ai_browser/app/server.py`, import `save_place` from `..places` and `extension_id_for`, `extension_path` from
`..extension_id`; add the four rows to `MESSAGE_RULES` and:

```python
PLACE_MESSAGES = {"browsers", "place_set", "watcher_copy", "restart_in"}  # AI Browser's own pages only (the table)
```

In `_handle`, beside wave 2A's Brave messages:

```python
        elif kind in PLACE_MESSAGES:
            await self._place_command(queue, kind, message)
```

and the work:

```python
    async def _place_command(self, queue: asyncio.Queue, kind: str, message: dict) -> None:
        if self.links is None:
            return
        if kind == "browsers":  # a page asked: the files are read again (Decision 8)
            await self.watchers.refresh()
            queue.put_nowait(await self._browsers_view(fresh=True))
            return
        if kind == "place_set":
            place = await asyncio.to_thread(self.where.check_place_set, message)
            error = place if isinstance(place, str) else await self._set_place(place)
        elif kind == "watcher_copy":
            error = await self._watcher_copy(queue, message)
        else:
            error = await self._restart_in(str(message.get("id", "")))
        if error:
            queue.put_nowait({"type": "error", "text": error})

    async def _browsers_view(self, fresh: bool) -> dict:
        return await self.where.browsers_view(self.links, self.watchers, self.agents, self.links.current,
                                              self.place_automatic, fresh)

    async def _broadcast_browsers(self) -> None:
        """A state or a copy changed: pages that asked for the view get it again, from the kept detection."""
        if self.links is not None and self.where.kept is not None:
            self._send_all(await self._browsers_view(fresh=False))

    async def _set_place(self, place: Place) -> str:
        """The user picked where new agents browse (Decision 12): saved; another profile is instant and asks
        nothing; another browser connects once, right after the click. Running agents keep their place."""
        await asyncio.to_thread(save_place, self.home, place)
        changed = self.links.set_current(place)
        self.agents.place, self.place_automatic = place, False
        self.watchers.sync()
        if changed:
            if self.on_browser_changed is not None:
                self.on_browser_changed(place)
            self._job(self.links.connect(place, "connect"))
        elsewhere = [agent for agent in self.agents.agents.values()
                     if agent.where is not None and agent.where.key != place.key]
        self._send_all({"type": "place_changed", "label": self.where.describe(place)["label"],
                        "elsewhere": len(elsewhere),
                        "elsewhere_labels": sorted({agent.place["label"] for agent in elsewhere if agent.place})})
        self._browser_changed()
        self._tabs_changed()
        await self.watchers.refresh()  # the files are read again after place_set
        self._send_all(await self._browsers_view(fresh=True))
        await self._prune()
        return ""

    async def _watcher_copy(self, queue: asyncio.Queue, message: dict) -> str:
        """Set it up: that profile's own watcher folder, shown in the file manager, its origin allowed."""
        place = await asyncio.to_thread(self.where.check_place_set, message)
        if isinstance(place, str):
            return place
        try:
            folder = await asyncio.to_thread(self._copy_folder, place)
        except ValueError as exc:  # NO_SLUG
            return str(exc)
        shown = extension_path(folder)
        await asyncio.to_thread(self.reveal, shown)
        queue.put_nowait({"type": "watcher_copy", "browser": place.browser, "profile": place.profile, "folder": shown,
                          "extensions": self.where.extensions_page(place.browser)})
        self._job(self.watchers.refresh())
        return ""

    def _copy_folder(self, place: Place) -> Path:
        """The primary copy when the files place it in that profile; else that profile's own copy, made or brought up
        to date now, with its origin allowed (Decision 7)."""
        if self.watchers.placed_copy(place) == "primary":
            return self.copies.primary
        profiles = [found.folder for found in browsers.profiles(place.user_data_dir)]
        folder = self.copies.make(place.browser, place.profile, self.url, self.token, profiles)
        self.allow_watcher(f"chrome-extension://{extension_id_for(folder)}", copy=folder.name)
        return folder

    async def _restart_in(self, agent_id: str) -> str:
        """Restart in (Decision 13): a click on a button that names the place; never from the Brain, voice or the
        watcher (the table)."""
        agent = self.agents.agents.get(agent_id)
        if agent is None:
            return "That agent has closed"
        if agent.where is None or agent.where.key == self.links.current.key:
            return "That agent already works where new agents browse"
        await self.agents.restart(agent_id)
        return ""

    def _tab_place(self, target: str) -> Place | None:
        """Decision 3: the profile a tab of the current browser is in, when a copy connected there says so."""
        found = self.links.located(target) if self.links is not None else None
        conn = self.watchers.for_context(*found) if found is not None else None
        return conn.place if conn is not None else None

    def _agents_browser(self):
        """The current place's installed browser, where wave B's open_url opens a website the user clicked; None for
        the system's default. (This replaces wave B's body, which asked own_browser_dir().)"""
        current = self.links.current if self.links is not None else None
        return next((row for row in browsers.installed() if current is not None and row.id == current.browser), None)
```

`links.on_state` (Task 17) and `watchers.on_change` also schedule `self._job(self._broadcast_browsers())`; register
`self.watchers.on_change(lambda: self._job(self._broadcast_browsers()))` in `__init__`.

**Hand over in one browser.** In `_hand`, after the agent is found:

```python
        if agent.where is not None and self.links is not None and agent.where.instance != self.links.current.instance:
            return f"{agent.name} works in another browser: it can only take tabs from there"
```

In `new_task`, the agent is created with the handed tab's place: `agents.create(text, skills, model, adopt,
_tab(...), place=self._tab_place(adopt) if adopt else None)` (keep wave B's other arguments as they are). The tab is
one of the current browser's (only those are handable), so the browser always matches.

**Websites.** Wave B's `_open_url` asks `self._agents_browser()` for the row; its new body above uses the saved
place.

In `tests/test_watcher_rules.py`, add the four rows to the copy.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_app_server.py tests/test_watcher_rules.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/server.py tests/test_app_server.py tests/test_watcher_rules.py
git commit -m "feat: Settings sets the place, sets up a profile's watcher, and Restart in; Hand over stays in one browser"
```

### Task 21: `ai-browser app` and `doctor` start on the place, and print folders, never names

**Files:**
- Modify: `src/ai_browser/app/run.py` (start-up, `SWITCH`, the ending), `src/ai_browser/cli.py` (`doctor`'s
  "everyday" line), `src/ai_browser/app/ui/setup.html` and `README.md` (the Allow line only)
- Test: `tests/test_app_run.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 2's `places.resolve(home)`; Task 3's `place_label`, `inspect_address`; Task 11's
  `WatcherCopies.prepare_all`, `build`, `name_of`, `primary`; Task 13's `InstanceLinks`, `started`, `close`; Task 12's
  `InstanceLink`; Task 17's `attach_links`, `allow_watcher(origin, copy)`, `on_browser_changed`, `connect_brave`,
  `brave`; wave 2A's `write_link(home, url, token, cdp, browser_dir)`, `SWITCH`; wave B's `run_app(...,
  launcher=)`, `FakeWindow`, the window-socket loop and the ending order.
- Produces:
  - at start: `place, automatic = places.resolve(home)`; every copy prepared and allowed; one `InstanceLinks` whose
    links are `InstanceLink`s; `server.attach_links(links, place, automatic)`; one line "Agents browse in Brave ·
    profile folder Profile 1 (change it in AI Browser's Settings)";
  - `agents.env` no longer carries `AIB_CHROME_DIR` (each agent's own place is in its env, Task 16);
  - link.json is written again, with the new `browser_dir`, when the current browser changes;
  - `doctor --setup`'s line: "everyday    Brave · profile folder Default (chosen in Settings): remote debugging is
    on", "(chosen for you)" or "(set by AIB_CHROME_DIR)";
  - the Allow line (in `SWITCH`, the setup page and the README) names the browser switch: "…, gave an agent a task,
    switched to {name} in AI Browser's Settings, asked Claude Code to browse, …".

- [ ] **Step 1: Write the failing tests**

In `tests/test_app_run.py` add (wave B's `FakeWindow` stands for the app window on the throwaway Chrome):

```python
@CHROME
async def test_the_app_starts_on_its_place_and_prints_only_the_folder(fake_claude, throwaway_chrome, tmp_path,
                                                                     monkeypatch):
    from ai_browser.app import run
    from ai_browser.cdp import CDP
    from ai_browser.chrome import find_ws_url
    from ai_browser.extension_id import extension_id_for
    from fake_window import FakeWindow
    from places_rig import write_local_state

    runner, _, _ = fake_claude
    everyday = tmp_path / "everyday"
    write_local_state(everyday, {"profile": {"info_cache": {"Default": {"name": "SECRET-NAME-9",
                                                                        "user_name": "secret@example.com"}},
                                             "last_used": "Default"}})
    monkeypatch.setenv("AIB_CHROME_DIR", str(everyday))
    home = tmp_path / "home"
    copy = home / "app" / "watchers" / "brave-profile-1"
    copy.mkdir(parents=True)
    made, lines, seen = [], [], {}

    class Recorded(run.AppServer):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            made.append(self)

    monkeypatch.setattr(run, "AppServer", Recorded)
    cdp = await CDP.connect(find_ws_url(throwaway_chrome, timeout=20))
    stop = asyncio.Event()

    async def ready(url, window):
        server = made[0]
        seen["current"] = server.links.current
        seen["allowed"] = server.watchers.allowed(f"chrome-extension://{extension_id_for(copy)}")
        seen["env"] = dict(server.agents.env)
        agent = await server.agents.create("look around")
        seen["agent_env"] = dict(agent.bridge.env)
        seen["link"] = json.loads((home / "app" / "link.json").read_text(encoding="utf-8"))
        stop.set()

    try:
        code = await asyncio.wait_for(run.run_app(home, claude=runner, ready=ready, stop=stop, out=lines.append,
                                                  launcher=lambda setting: FakeWindow(cdp)), 60)
    finally:
        await cdp.close()
    printed = "\n".join(lines)
    assert code == 0, printed
    assert (seen["current"].user_data_dir, seen["current"].profile) == (str(everyday), "Default")
    assert seen["allowed"] and (copy / "config.json").is_file()  # every copy brought up to date, its origin allowed
    assert "AIB_CHROME_DIR" not in seen["env"]
    assert (seen["agent_env"]["AIB_CHROME_DIR"], seen["agent_env"]["AIB_CHROME_PROFILE"]) == (str(everyday), "Default")
    assert seen["link"]["browser_dir"] == str(everyday)
    assert "Agents browse in Chrome · profile folder Default (change it in AI Browser's Settings)" in printed
    assert "SECRET-NAME-9" not in printed and "secret@example.com" not in printed


def test_the_allow_line_names_a_browser_switch():
    from ai_browser.app.run import SWITCH
    from ai_browser.config import project_root

    texts = [SWITCH.format(name="Brave", inspect="brave://inspect/#remote-debugging"),
             (project_root() / "src" / "ai_browser" / "app" / "ui" / "setup.html").read_text(encoding="utf-8"),
             (project_root() / "README.md").read_text(encoding="utf-8")]
    for text in texts:
        words = " ".join(text.split())
        assert "gave an agent a task, switched to Brave in AI Browser's Settings, asked Claude Code to browse" in words
        assert "it isn't AI Browser" in words
```

In `tests/test_cli.py` add:

```python
def test_the_everyday_line_names_the_place_and_never_a_profiles_name(tmp_path, monkeypatch, capsys):
    from places_rig import write_local_state

    server, _ = _browser_port_stand_in()
    try:
        env = _setup_env(tmp_path, monkeypatch, server.getsockname()[1])
        write_local_state(Path(env["AIB_CHROME_DIR"]), {"profile": {"info_cache": {
            "Default": {"name": "SECRET-NAME-9", "user_name": "secret@example.com"}}, "last_used": "Default"}})
        main(["doctor", "--setup"])
    finally:
        server.close()
    out = capsys.readouterr().out
    line = next(line for line in out.splitlines() if "everyday" in line)
    assert line == "✓ everyday    Chrome · profile folder Default (set by AIB_CHROME_DIR): remote debugging is on"
    assert "SECRET-NAME-9" not in out and "secret@example.com" not in out


def test_doctor_says_whether_the_place_was_chosen(tmp_path, monkeypatch, capsys):
    from ai_browser.places import Place, save_place
    from places_rig import install

    folders = install(monkeypatch, tmp_path, "brave", default="brave")
    monkeypatch.setenv("AIB_HOME", str(tmp_path / "aib-home"))
    monkeypatch.delenv("AIB_CHROME_DIR")
    monkeypatch.delenv("AIB_CHROME_PROFILE")
    main(["doctor", "--setup"])
    assert "Brave · profile folder Profile 1 (chosen for you)" in capsys.readouterr().out  # the profile used last
    save_place(tmp_path / "aib-home", Place("brave", str(folders["brave"]), "Default"))
    main(["doctor", "--setup"])
    assert "Brave · profile folder Default (chosen in Settings)" in capsys.readouterr().out
```

(`test_doctor_setup_checks_without_docker_or_a_browser_connection`'s "everyday" assertion stays true: the line still
starts "✓ everyday" and holds "remote debugging is on".)

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_app_run.py -k "its_place or allow_line" tests/test_cli.py -k "everyday_line or was_chosen" -q -p no:randomly`

Expected: FAIL. The app prints no "Agents browse in" line and its agents' env carries `AIB_CHROME_DIR` from
`agents.env`; the Allow line has no "switched to"; `doctor` says "profile folder found".

- [ ] **Step 3: Start on the place**

In `src/ai_browser/app/run.py`, import `places`, `place_label` (with `inspect_address`) from `..chrome`,
`InstanceLink` from `.bravelink` and `InstanceLinks` from `.links`. Wave B's start-up prepares the watcher with
`prepare_watcher(home, url, server.token)`, builds the `BraveLink`, puts `brave_env(own)` into `agents.env`, attaches
it and writes link.json. Replace those lines with:

```python
        place, automatic = places.resolve(home)  # AIB_CHROME_DIR, else the saved place, else chosen for the user
        folders = server.copies.prepare_all(url, server.token)  # the primary and every profile's copy, current
        server.watcher_build = server.copies.build
        server.watcher_folder = extension_path(server.copies.primary)
        for extension_id in folders:
            server.allow_watcher(f"chrome-extension://{extension_id}", copy=server.copies.name_of(extension_id))
        links = InstanceLinks(lambda where: InstanceLink(Path(where.user_data_dir), watcher_ids=set(folders),
                                                         tokens=server.tokens, app_origin=url))
        server.attach_links(links, place, automatic)
        await links.started(place)  # its first look at the switch (TCP only): it never connects by itself
        out(f"Agents browse in {place_label(place)} (change it in AI Browser's Settings)")  # a folder, never a name
        cdp = f"{url.replace('http', 'ws', 1)}/cdp"
        link_file = write_link(home, url, server.session_token, cdp, place.user_data_dir)
        server.on_browser_changed = lambda where: write_link(home, url, server.session_token, cdp,
                                                             where.user_data_dir)
```

(keep wave B's other lines, `AIB_APP_ORIGIN`, `AIB_APP_EVENTS` and `AIB_APP_CDP` in `agents.env`, as they are;
`brave_env` goes, and nothing else puts `AIB_CHROME_DIR` in `agents.env`). Where wave B printed `SWITCH` for a link
that is off and otherwise connected once:

```python
        link = server.brave
        if link.state == "off":
            out(SWITCH.format(name=link.name, inspect=inspect_address(Path(place.user_data_dir))))
        else:
            server.connect_brave("start")  # once, as the app starts: the browser asks "Allow remote debugging?"
```

In the ending (`finally`), wave B's `await brave.close()` (after `server.stop()`, wave 2A's order) becomes
`await links.close()` when `links` was made. Wave B's `open_url` already uses the current place (Task 20).

In `SWITCH`, the Allow line's "gave an agent a task, asked Claude Code to browse" becomes "gave an agent a task,
switched to {name} in AI Browser's Settings, asked Claude Code to browse". In `src/ai_browser/app/ui/setup.html` and
`README.md`, the same Allow line (wave 2A's words, "Only click Allow right after you started AI Browser, clicked
Connect, gave an agent a task, …") gains "switched to Brave in AI Browser's Settings," after "gave an agent a task,".

In `src/ai_browser/cli.py`, `_doctor_setup`'s "everyday" block becomes (import `os`, `places` and `place_label`):

```python
    place, automatic = places.resolve(home())
    folder = Path(place.user_data_dir)
    how = ("set by AIB_CHROME_DIR" if os.environ.get("AIB_CHROME_DIR", "").strip()
           else "chosen for you" if automatic else "chosen in Settings")
    label = f"{place_label(place)} ({how})"  # the profile folder, never its name: Claude Code may read this
    if not folder.is_dir():
        report("-", "everyday", f"{label}: no profile folder at {folder}")
    elif switch_on(folder):  # a TCP check of DevToolsActivePort's port: no DevTools session, so no Allow question
        report("✓", "everyday", f"{label}: remote debugging is on")
    else:
        report("-", "everyday", f"{label}: remote debugging is off ({inspect_address(folder)})")
```

- [ ] **Step 4: Run them, and the app-run and CLI files**

Run: `uv run pytest tests/test_app_run.py tests/test_cli.py -q -p no:randomly`

Expected: PASS (the Chrome ones skip without Google Chrome). Wave B's app-run tests that checked `agents.env` for
`AIB_CHROME_DIR` check an agent's own env instead.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/run.py src/ai_browser/cli.py src/ai_browser/app/ui/setup.html README.md \
        tests/test_app_run.py tests/test_cli.py
git commit -m "feat: the app starts on the saved place with every watcher copy, and the terminal names folders only"
```

### Task 22: The watcher opens the tab (`openTab`), proven in a throwaway Chrome

**Files:**
- Modify: `src/ai_browser/app/watcher/groups.js` (`validOpen`, `openTab`, `windowFor`)
- Modify: `src/ai_browser/app/watcher/worker.js` (`handle` answers `open_tab`; `watcher_caps` says `open: true`)
- Test: `tests/test_watcher_groups.py`

**Interfaces:**
- Consumes: `groups.js`'s `KEY`, `MARKER`, `COLORS`, `grouping`, `stored()`, `live()`, `put()`, `groupsAvailable()`;
  the `watcher` fixture (Task 18 placed its copy); Task 19's `/agent-open`; Task 7's engine; wave 2A's relay.
- Produces:
  - `export function validOpen(message) -> bool`: `key` matches `KEY`, `color` is one of the nine, `title` a string of
    at most 40 characters, `marker` matches `MARKER`, and no `url` field;
  - `export function openTab(message) -> Promise<{request, ok, tab, window, group, new_window} | {request, ok: false,
    reason: "invalid" | "failed"}>`, queued on `grouping`;
  - `worker.js`: `open_tab` → `opened_tab`; `watcher_caps {"groups": …, "open": true}`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_watcher_groups.py` add (`agent_engine`, `group_of`, `groups_on` and `ACTIVE` are this file's):

```python
async def open_ready(watcher):  # noqa: F811
    """The fixture's copy can open tabs: its caps said so, and its worker's context is known."""
    def ready():
        conn = watcher.server.watchers.brain()
        return conn is not None and conn.groups.can_open() and watcher.server.watchers.context(conn) is not None
    assert await watcher.until(ready, 30), "the watcher never said it can open tabs"


@CHROME
async def test_open_tab_makes_a_background_tab_at_the_marker_in_the_group(watcher, tmp_path):  # noqa: F811
    import httpx

    add_agent(watcher.server.agents, "a1", "Fix the footer", "blue")
    await open_ready(watcher)
    front = await watcher.worker_js(ACTIVE)
    marker = "0123456789abcdef"
    async with httpx.AsyncClient() as client:
        answer = (await client.post(watcher.server.url + "/agent-open", json={"agent": "a1", "marker": marker},
                                    headers={"X-AIB-Agent-Token": watcher.server.token_for("a1")}, timeout=10)).json()
    assert answer["opened"] is True and answer["new_window"] is False and isinstance(answer["tab"], int)
    title, color, group_window, window = await group_of(watcher, f"about:blank#aib-{marker}")
    assert (title, color) == ("Fix the footer", "blue") and group_window == window
    assert await watcher.worker_js(ACTIVE) == front  # nothing came to the front
    assert answer["target"] in watcher.server.agents.agents["a1"].tabs


@CHROME
async def test_open_tab_opens_nothing_but_the_marker(watcher):  # noqa: F811
    await open_ready(watcher)
    conn = watcher.server.watchers.brain()
    answers = []
    real = conn.groups.opened
    conn.groups.opened = lambda message: answers.append(message) or real(message)
    count = "chrome.tabs.query({}).then(tabs => tabs.length)"
    before = await watcher.worker_js(count)
    base = {"type": "open_tab", "marker": "0123456789abcdef", "key": "a1", "title": "Fix", "color": "blue"}
    changes = ({"marker": "../../etc"}, {"title": "x" * 41}, {"color": "black"}, {"url": "https://example.com"},
               {"key": "A B"})
    for number, change in enumerate(changes):  # sent as the app would send them, straight to the copy's socket
        conn.queue.put_nowait({**base, "request": f"x{number}", **change})
    assert await watcher.until(lambda: len(answers) == len(changes))
    assert all(answer["ok"] is False and answer["reason"] == "invalid" for answer in answers), answers
    assert await watcher.worker_js(count) == before
    shown = await watcher.worker_js("chrome.tabs.query({}).then(tabs => tabs.map(tab => tab.url || tab.pendingUrl))")
    assert not any("example.com" in url for url in shown)


@CHROME
async def test_the_watcher_says_it_can_open_tabs(watcher):  # noqa: F811
    await open_ready(watcher)
    assert watcher.server.watchers.brain().groups.caps == {"groups": True, "open": True}


@CHROME
async def test_an_agent_engine_uses_the_watcher_and_creates_no_target(watcher, tmp_path, monkeypatch):  # noqa: F811
    from ai_browser.cdp import CDP

    add_agent(watcher.server.agents, "a1", "Fix the footer", "blue")
    await open_ready(watcher)
    sent = []
    real = CDP.send

    async def spy(self, method, params=None, session_id=None, timeout=30):
        sent.append(method)  # every CDP command any client of this process sends, the engine's included
        return await real(self, method, params, session_id=session_id, timeout=timeout)

    monkeypatch.setattr(CDP, "send", spy)
    engine = agent_engine(watcher, tmp_path, monkeypatch)
    try:
        page = (await engine.open(watcher.base + "popup.html")).text
        assert 'page  "Popup test"' in page and "profile the user used last" not in page
        assert "Target.createTarget" not in sent and "Target.attachToTarget" in sent
        assert "t1" in (await engine.tabs("list")).text
    finally:
        await engine.close()


@CHROME
async def test_without_the_profiles_watcher_the_engine_falls_back_and_says_so(watcher, tmp_path,  # noqa: F811
                                                                              monkeypatch):
    from ai_browser.places import Place

    agent = add_agent(watcher.server.agents, "a1", "Fix the footer", "blue")
    agent.where = Place("", watcher.server.links.current.user_data_dir, "Profile 7")  # no copy there
    await groups_on(watcher)
    engine = agent_engine(watcher, tmp_path, monkeypatch)
    monkeypatch.setenv("AIB_CHROME_PROFILE", "Profile 7")  # the engine's own place, as place_env would set it
    try:
        first = (await engine.open(watcher.base + "popup.html")).text
        assert first.count("opened in the Chrome profile the user used last") == 1
        second = (await engine.tabs("new", url=watcher.base + "report.html")).text
        assert "profile the user used last" not in second  # said once per session
    finally:
        await engine.close()
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_watcher_groups.py -k "open_tab or can_open_tabs or creates_no_target or falls_back_and_says_so" -q -p no:randomly`

Expected: FAIL. The watcher's caps have no `open` (so `/agent-open` answers `refused` and the engine creates the tab
itself), and `groups.js` has no `openTab`.

- [ ] **Step 3: Teach the watcher to open one blank tab**

In `src/ai_browser/app/watcher/groups.js`, the header comment gains: "Its one new act (browser-profile-choice): the
app may ask it to open one blank background tab at a secret mark, `about:blank#aib-<16 hex>`, in this profile, for an
agent; it builds that address itself, never opens one the app names, never navigates or reads it, and never uses a
private window." Add after `valid`:

```js
export function validOpen(message) { // a blank tab at a secret mark, nothing else: an address in the message refuses it
  if (!message || typeof message !== "object" || "url" in message) return false;
  return KEY.test(String(message.key ?? "")) && COLORS.has(message.color) && typeof message.title === "string"
    && message.title.length <= 40 && MARKER.test(String(message.marker ?? ""));
}

async function windowFor(key) { // the agent's live group's window, else the last focused normal one, else any normal
  const { groups } = await stored();
  for (const [windowId, groupId] of Object.entries(groups[key] || {})) {
    if (await live(groupId, Number(windowId)) === undefined) continue;
    const found = await chrome.windows.get(Number(windowId)).catch(() => null);
    if (found && !found.incognito) return found.id;
  }
  const last = await chrome.windows.getLastFocused({ windowTypes: ["normal"] }).catch(() => null);
  if (last && !last.incognito) return last.id;
  const all = await chrome.windows.getAll({ windowTypes: ["normal"] }).catch(() => []);
  return all.find((found) => !found.incognito)?.id; // never a private window
}

async function opening(message) {
  const request = message?.request;
  if (!validOpen(message)) return { request, ok: false, reason: "invalid" };
  const url = `about:blank#aib-${message.marker}`; // built here: the app never sends an address
  try {
    const windowId = await windowFor(message.key);
    let tab;
    let newWindow = false;
    if (windowId === undefined) { // this profile has no window: one behind the user's (documented focused: false)
      const made = await chrome.windows.create({ url, focused: false, incognito: false, type: "normal" });
      tab = made.tabs?.[0] ?? (await chrome.tabs.query({ windowId: made.id }))[0];
      newWindow = true;
    } else {
      tab = await chrome.tabs.create({ url, active: false, windowId }); // in the background: focus doesn't move
    }
    let group = null;
    if (groupsAvailable()) {
      group = (await put(tab, message.key, message.title, message.color, false).catch(() => null))?.group ?? null;
    }
    return { request, ok: true, tab: tab.id, window: tab.windowId, group, new_window: newWindow };
  } catch {
    return { request, ok: false, reason: "failed" };
  }
}

export function openTab(message) { // one at a time with grouping: two requests for one key make one group
  const answer = grouping.then(() => opening(message));
  grouping = answer.catch(() => {});
  return answer;
}
```

In `src/ai_browser/app/watcher/worker.js`, import `openTab` from `./groups.js`; in `handle`, beside `group_tab`:

```js
  else if (message.type === "open_tab") link.send({ type: "opened_tab", ...(await openTab(message)) });
```

and the caps it sends right after its hello: `link.send({ type: "watcher_caps", groups: groupsAvailable(), open: true
});`. The header comment of `worker.js` gains "and opens a blank background tab for an agent when the app asks".

- [ ] **Step 4: Run them, and the whole watcher-groups file**

Run: `uv run pytest tests/test_watcher_groups.py -q -p no:randomly`

Expected: PASS (skips without Google Chrome, and on Windows). The earlier grouping tests now place their first tab
through the watcher; they check groups and focus, which hold the same way.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/watcher/groups.js src/ai_browser/app/watcher/worker.js tests/test_watcher_groups.py
git commit -m "feat: the watcher in the agent's profile opens its blank background tab at the secret marker, nothing else"
```

### Task 23: Settings → **Where agents browse** (`places.js`)

**Files:**
- Create: `src/ai_browser/app/ui/places.js` (`SAYS`, `safeColor`, `profileName`, `browserLabel`, `watcherLine`,
  `pickProfile`, `needsWatcher`, `mountWhere`; Task 24 adds `mountChip`)
- Modify: `src/ai_browser/app/ui/settings.html`, `settings.js`, and `home.css` (the stylesheet wave B's Settings
  page links)
- Test: `tests/test_home.py`

**Interfaces:**
- Consumes: Task 20's `browsers`, `place_set`, `watcher_copy` messages and answers; wave B's `ui/settings.html`,
  `settings.js` (its `connect({view: "settings", onMessage, onState})` from `link.js`), `ui/chat.js`'s `el`, the
  rebuilt `stack` and `home` fixtures, `open_page`, `until`; Task 2's `places_rig` (`install`, `load_watcher`).
- Produces:
  - `ui/places.js` exports as listed; `mountWhere(root, { send }) -> { render(view), copied(message) }`;
  - Settings' second section `<section id="where">`: `.where-card[data-id][data-agents]` (with `.pick`, `.state`,
    `.count`, `.at-work`, and for a switch that is off a `details.how` with its steps and warnings);
    `.where-profile[data-folder]` (with `.dot`, `.name`, `.used-last`, `.watcher`, `.at-work`, `.use`, and `.setup`
    when the profile has no watcher); `.where-copy` (the steps and a read-only `input.folder`); `.where-notes`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_home.py` add (`home` is wave B's fixture: `js, stack = home`):

```python
def settings_rig(monkeypatch, tmp_path, stack, local_state=None):
    """Brave, Chrome and Edge "installed"; Brave's Default holds the primary watcher, Profile 2's copy is loaded in
    two places (shared); Brave's Default is the current place."""
    from ai_browser.extension_id import extension_id_for
    from ai_browser.places import Place
    from fake_brave import FakeBrave
    from places_rig import install, load_watcher

    server = stack["server"]
    folders = install(monkeypatch, tmp_path, "brave", "chrome", "edge", default="brave", local_state=local_state)
    primary = server.copies.primary
    load_watcher(folders["brave"], "Default", extension_id_for(primary), primary)
    copy = server.copies.folder_for("brave", "Profile 2")
    for data, profile in ((folders["brave"], "Profile 2"), (folders["chrome"], "Default")):
        load_watcher(data, profile, extension_id_for(copy), copy)
    copy.mkdir(parents=True)
    place = Place("brave", str(folders["brave"]), "Default")
    server.attach_brave(FakeBrave([], state="ready", folder=folders["brave"]), place=place)
    real = server.watchers.status_for
    monkeypatch.setattr(server.watchers, "status_for",
                        lambda where: "on" if where is not None and where.key == place.key else real(where))
    return folders


@CHROME
async def test_settings_lists_browsers_profiles_and_watcher_states(home, monkeypatch, tmp_path):
    from ai_browser.extension_id import extension_path

    js, stack = home
    server = stack["server"]
    settings_rig(monkeypatch, tmp_path, stack)
    _, page = await open_page(stack["cdp"], f"{stack['url']}/settings")
    card = "(id => document.querySelector(`#where .where-card[data-id='${id}']`))"
    row = "(folder => document.querySelector(`#where .where-profile[data-folder='${folder}']`))"
    assert await until(page, "document.querySelectorAll('#where .where-card').length === 3")
    assert await page(f"[{card}('brave').querySelector('.name').textContent, {card}('brave').dataset.agents]") == [
        "Brave", "true"]
    assert await page(f"{card}('edge').querySelector('.state').textContent") == "not supported yet"
    assert await page(f"{card}('edge').querySelector('.pick').disabled") is True  # greyed: it can't be picked
    assert await page(f"[...document.querySelectorAll('#where .where-profile .name')].map(n => n.textContent)") == [
        "Personal", "Work", "Side"]
    assert await page(f"{row}('Default').querySelector('.watcher').textContent") == "✓ watcher"
    assert await page(f"{row}('Profile 1').querySelector('.watcher').textContent") == \
        "Needs the watcher (once) · Set it up"
    assert await page(f"{row}('Profile 2').querySelector('.watcher').textContent") == \
        "This watcher folder is loaded in two profiles: remove it from one in brave://extensions"
    assert await page(f"{row}('Profile 1').querySelector('.used-last').textContent") == "used last"
    assert await page(f"{row}('Default').querySelector('.use').textContent") == "✓ chosen"
    notes = await page("document.querySelector('#where .where-notes').textContent")
    assert "Switching profile in Brave needs no new Allow." in notes and "never sends profile names to Claude" in notes
    await page(f"{row}('Profile 1').querySelector('.setup').click(); true")
    assert await until(page, "!document.querySelector('#where .where-copy').hidden")
    folder = extension_path(server.copies.folder_for("brave", "Profile 1"))
    assert await page("document.querySelector('#where .where-copy input.folder').value") == folder
    assert "switch to the Work profile" in await page("document.querySelector('#where .where-copy').textContent")
    await page(f"{row}('Profile 1').querySelector('.use').click(); true")
    for _ in range(50):
        if server.links.current.profile == "Profile 1":
            break
        await asyncio.sleep(0.1)
    assert server.links.current.profile == "Profile 1"
    assert await until(page, f"{row}('Profile 1').querySelector('.use').textContent === '✓ chosen'")


@CHROME
async def test_a_hostile_profile_name_stays_text_in_settings(home, monkeypatch, tmp_path):
    from places_rig import LOCAL_STATE

    js, stack = home
    state = json.loads(json.dumps(LOCAL_STATE))
    state["profile"]["info_cache"]["Profile 1"]["name"] = HOSTILE
    settings_rig(monkeypatch, tmp_path, stack, local_state=state)
    _, page = await open_page(stack["cdp"], f"{stack['url']}/settings")
    assert await until(page, "document.querySelectorAll('#where .where-profile').length === 3")
    names = await page("[...document.querySelectorAll('#where .where-profile .name')].map(n => n.textContent)")
    assert HOSTILE in names
    assert await page("document.querySelectorAll('#where img').length") == 0 and await page("document.title") != \
        "pwned"
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_home.py -k "settings_lists or hostile_profile_name_stays_text_in_settings" -q -p no:randomly`

Expected: FAIL: the Settings page has no `#where` section.

- [ ] **Step 3: Write `places.js` and the section**

Create `src/ai_browser/app/ui/places.js`:

```js
// Where agents browse (browser-profile-choice): Settings' section, and AI Home's chip (mountChip, below). Both draw the
// app's `browsers` view. Names, colours, counts and paths are set as text: a profile's name is the user's own text,
// never markup. Names stay on this computer's pages; nothing here sends one anywhere but back to our own server, by id.
import { el } from "./chat.js";

export const SAYS = { switch_on: "switch on", switch_off: "switch off", not_running: "not running",
                      connected: "connected", asking: "waiting for Allow", refused: "not allowed", lost: "closed" };
const COLOR = /^#[0-9a-f]{6}$/;

export function safeColor(color) {
  return typeof color === "string" && COLOR.test(color) ? color : "var(--muted)";
}

export function profileName(place) { // "Brave · Work" -> "Work"
  const label = String(place?.label || "");
  const at = label.indexOf(" · ");
  return at >= 0 ? label.slice(at + 3) : String(place?.profile || "");
}

export function browserLabel(place) { // "Brave · Work" -> "Brave"
  const label = String(place?.label || "");
  const at = label.indexOf(" · ");
  return at >= 0 ? label.slice(0, at) : label;
}

export function needsWatcher(profile) {
  return !profile.watcher || profile.shared_watcher;
}

export function watcherLine(profile, browser) {
  if (profile.shared_watcher) {
    return `This watcher folder is loaded in two profiles: remove it from one in ${browser.extensions}`;
  }
  if (profile.watcher && profile.live) return "✓ watcher";
  if (profile.watcher) return `Watcher loaded, not connected: open a ${browser.name} window in this profile`;
  return "Needs the watcher (once) · Set it up";
}

export function pickProfile(browser) { // a browser picked as a whole: its profile with the watcher, else used last
  const profiles = browser.profiles || [];
  const chosen = profiles.find((profile) => profile.watcher && !profile.shared_watcher)
    || profiles.find((profile) => profile.last_used) || profiles[0];
  return chosen ? chosen.folder : null;
}

const STEPS = (browser) => [
  `In ${browser.name}, open ${browser.inspect}.`,
  "Tick \"Allow remote debugging for this browser instance\".",
  `When ${browser.name} asks "Allow remote debugging?", click Allow.`,
];
const WARNINGS = (name) => [
  `While this switch is on, any program on this computer can reach your ${name}, not only AI Browser. That includes `
    + "the sites you are signed in to.",
  `While AI Browser is connected, a program that can read AI Browser's files can also use your ${name} through it `
    + "without a new question. AI Home lists everything connected, with Disconnect.",
  "Turn it off when agents aren't working: untick the same box.",
];
const NOTES = (name) => [
  `Switching profile in ${name} needs no new Allow.`,
  "Switching to another browser: it asks \"Allow remote debugging?\" once, right after you switch. Agents already at "
    + "work stay where they are.",
  "While agents work in two browsers, each shows its own \"controlled by automated test software\" bar.",
  "AI Browser only reads files and checks a port to show this page. It connects only when AI Browser starts, when you "
    + "click Connect, give an agent a task or switch browser, and when you ask Claude Code to browse.",
  `Names and colours come from ${name}'s own files on this computer. AI Browser never shows or sends the email you are `
    + "signed in with, and never sends profile names to Claude.",
];

function button(className, label, onClick) {
  const node = el("button", className, label);
  node.type = "button";
  node.addEventListener("click", onClick);
  return node;
}

// root: Settings' #where section. send(message): to the app.
export function mountWhere(root, { send }) {
  let view = null;
  let copy = null; // the last watcher_copy answer: the folder and its steps, until that profile shows ✓ watcher
  const cards = el("div", "where-cards");
  const profiles = el("div", "where-profiles");
  const copyBox = el("div", "where-copy");
  const notes = el("ul", "where-notes muted");
  copyBox.hidden = true;
  root.append(cards, profiles, copyBox, notes);

  function choose(browser, folder) {
    if (folder) send({ type: "place_set", browser, profile: folder }); // saved at once: no Save button
  }

  function card(browser) {
    const node = el("div", "where-card");
    node.dataset.id = browser.id;
    node.dataset.agents = String(Boolean(browser.agents));
    const current = view.current.browser === browser.id;
    node.classList.toggle("current", current);
    const pick = button("pick", "", () => choose(browser.id, pickProfile(browser)));
    pick.append(el("span", "glyph", "◉"), el("span", "name", browser.name));
    pick.disabled = !browser.agents || current;
    const count = (browser.profiles || []).length;
    node.append(pick,
      el("span", "state chip", browser.agents ? (SAYS[browser.state] || String(browser.state || ""))
        : "not supported yet"),
      el("span", "count muted", browser.agents ? `${count} profile${count === 1 ? "" : "s"}` : ""),
      el("span", "at-work muted", browser.at_work ? `${browser.at_work} at work` : ""));
    if (browser.agents && browser.state === "switch_off") { // its three steps, with the setup page's warnings
      const how = el("details", "how");
      how.open = current;
      how.append(el("summary", "", "Show me how"));
      const steps = el("ol", "steps");
      for (const step of STEPS(browser)) steps.append(el("li", "", step));
      how.append(steps);
      for (const line of WARNINGS(browser.name)) how.append(el("p", "muted", line));
      node.append(how);
    }
    return node;
  }

  function profileRow(browser, profile) {
    const row = el("div", "where-profile");
    row.dataset.folder = profile.folder;
    const dot = el("span", "dot");
    dot.style.background = safeColor(profile.color);
    const current = view.current.browser === browser.id && view.current.profile === profile.folder;
    const use = button(current ? "use chosen" : "use",
      current ? (view.automatic ? "chosen for you" : "✓ chosen") : "Use this profile",
      () => choose(browser.id, profile.folder));
    use.disabled = current;
    row.append(dot, el("span", "name", profile.name), el("span", "used-last muted", profile.last_used ? "used last" : ""),
      el("span", "watcher", watcherLine(profile, browser)),
      el("span", "at-work muted", profile.at_work ? `${profile.at_work} at work` : ""), use);
    if (!profile.watcher) {
      row.append(button("setup ghost", "Set it up",
        () => send({ type: "watcher_copy", browser: browser.id, profile: profile.folder })));
    }
    return row;
  }

  function renderCopy() {
    copyBox.textContent = "";
    copyBox.hidden = !copy;
    if (!copy) return;
    const browser = (view?.browsers || []).find((found) => found.id === copy.browser);
    const profile = (browser?.profiles || []).find((found) => found.folder === copy.profile);
    const name = browser?.name || "your browser";
    const steps = el("ol", "copy-steps");
    steps.append(
      el("li", "", `In ${name}, switch to the ${profile?.name || copy.profile} profile (click your profile picture at `
        + "the top right)."),
      el("li", "", `Open ${copy.extensions} and turn on Developer mode.`),
      el("li", "", "Drag the folder onto that page (or Load unpacked and pick it)."));
    const folder = el("input", "folder");
    folder.readOnly = true;
    folder.value = copy.folder;
    folder.setAttribute("aria-label", "This profile's watcher folder");
    copyBox.append(steps, folder);
  }

  function render(next) {
    view = next;
    cards.replaceChildren(...view.browsers.map(card));
    const shown = view.browsers.find((browser) => browser.id === view.current.browser);
    profiles.replaceChildren(...(shown ? shown.profiles.map((profile) => profileRow(shown, profile)) : []));
    const lines = [...NOTES(shown?.name || "your browser"), view.new_window_note].filter(Boolean);
    notes.replaceChildren(...lines.map((line) => el("li", "", line)));
    const done = copy && view.browsers.find((browser) => browser.id === copy.browser)?.profiles
      .find((profile) => profile.folder === copy.profile);
    if (done?.watcher && done.live) copy = null; // the row turned ✓ watcher: the steps are done
    renderCopy();
  }

  function copied(message) {
    copy = message;
    renderCopy();
  }

  return { render, copied };
}
```

In `src/ai_browser/app/ui/settings.html`, after wave B's **App window** section:

```html
<section id="where" class="card" aria-labelledby="where-title">
  <h2 id="where-title">Where agents browse</h2>
  <p id="where-error" class="muted" role="status"></p>
</section>
```

In `src/ai_browser/app/ui/settings.js` (wave B's), import `mountWhere` from `./places.js` and mount it after the
`$` helper:

```js
import { mountWhere } from "./places.js";

const where = mountWhere($("where"), { send: (message) => link.send(message) });
let whereShown = false;
```

`setStatus(state)` gains, at its end:

```js
  if (state === "connected") link.send({ type: "browsers" }); // a fresh read of the browsers' files: this page asked
```

and `handle(message)` gains these branches (before its `error` branch):

```js
  } else if (message.type === "browsers") {
    where.render(message);
    if (!whereShown && location.hash === "#where") $("where").scrollIntoView();
    whereShown = true;
  } else if (message.type === "watcher_copy") {
    where.copied(message);
  } else if (message.type === "browser" || message.type === "place_changed") {
    link.send({ type: "browsers" });
  } else if (message.type === "error" && !message.request) { // place_set's and watcher_copy's errors
    $("where-error").textContent = message.text || "";
```

(`#where-error` is in the section's HTML above.)

Styles, appended to `home.css` (scoped under `.settings`, as wave B's are): `.where-cards { display: flex; gap: 8px; flex-wrap: wrap }`; `.where-card` (a
bordered box; `.current` outlined; `[data-agents="false"]` at `opacity: .5`); `.where-profile { display: grid;
grid-template-columns: 12px 1fr auto auto auto auto auto; gap: 8px; align-items: center }`; `.dot { width: 10px;
height: 10px; border-radius: 50% }`; `.where-copy input.folder { width: 100% }`. No inline styles in the HTML (wave
B's CSP); the dot's colour is set from script, as `tablist.js` already sets a chip's.

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest tests/test_home.py -k "settings_lists or hostile_profile_name_stays_text_in_settings" -q -p no:randomly`

Then: `uv run pytest tests/test_ui_static.py -q -p no:randomly`

Expected: PASS (wave B's static test: no `innerHTML`, no inline script or style, `chrome.` only in `link.js` and
`brainui.js`).

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/ui/places.js src/ai_browser/app/ui/settings.html src/ai_browser/app/ui/settings.js \
        src/ai_browser/app/ui/home.css tests/test_home.py
git commit -m "feat: Settings shows where agents browse: browsers, profiles, watcher states, and Set it up"
```

### Task 24: AI Home: the place chip, the notice, the watcher line, **Restart in**, the tab list and Give to

**Files:**
- Modify: `src/ai_browser/app/ui/places.js` (add `mountChip`), `home.html`, `home.js`, `home.css`, `tablist.js`
- Test: `tests/test_home.py`

**Interfaces:**
- Consumes: Task 23's `places.js` helpers; Task 17's `browser` message (`place`, `watcher`, `extra_watcher`); Task
  20's `browsers`, `place_set`, `place_changed`, `restart_in`; Task 13's rows with `place` and `other_profile`; Task
  16's `agent.place`; wave A's `agentLabel(agent)`, `tablist.js`'s `render(tabs, { brave, ownerOf, scope })` and its
  scope lines; wave 2A's clients list in `home.js` (`#browser-clients`); wave B's `openWindow(path, name, width,
  height)` in `nav.js`, `click_as_user`.
- Produces:
  - `places.js`: `mountChip(root, { send, openSettings }) -> { render(view, browserInfo) }`, drawing
    `button.place-chip` ("Brave · Personal ▾", "(chosen for you)" when automatic) and `div.place-menu` with
    `.place-profile[data-folder]`, `.place-browser[data-id]` and `.place-settings`;
  - `home.html`: `#place-chip` (in the browser card's header, before `#browser-title`), `#place-notice` with
    `#place-notice-text` and `#place-notice-close`, `#browser-chosen`, `#browser-setup`;
  - agent rows: `.place-chip`, `.restart` ("Restart in Chrome · Work") and `.restart-note`;
  - `tablist.js`: `render(tabs, { brave, ownerOf, scope, place })`; rows' `.place` and `.other`; Give to lists only
    agents in the tab's browser, with "(in Work)" for another profile; the `last_used` line names the chosen profile.

- [ ] **Step 1: Write the failing tests**

In `tests/test_home.py` add:

```python
@CHROME
async def test_the_chip_shows_the_place_and_switches_profiles(home, monkeypatch, tmp_path):
    from ai_browser.extension_id import extension_id_for
    from places_rig import load_watcher

    js, stack = home
    server = stack["server"]
    folders = settings_rig(monkeypatch, tmp_path, stack)
    work = server.copies.folder_for("brave", "Profile 1")
    load_watcher(folders["brave"], "Profile 1", extension_id_for(work), work)  # Work has its own copy
    chip = "document.querySelector('#place-chip .place-chip')"
    assert await until(js, f"{chip}?.textContent === 'Brave · Personal ▾'")
    await js(f"{chip}.click(); true")
    item = "(folder => document.querySelector(`#place-chip .place-profile[data-folder='${folder}']`))"
    assert await until(js, f"!!{item}('Profile 2')")
    assert "needs the watcher" in await js(f"{item}('Profile 2').textContent")  # shared: it can't place tabs
    assert await js("document.querySelector('#place-chip .place-browser[data-id=\"chrome\"]').textContent") == \
        "Chrome · Show me how"
    await js(f"{item}('Profile 1').click(); true")
    assert await until(js, f"{chip}?.textContent === 'Brave · Work ▾'")
    assert server.links.current.profile == "Profile 1"
    assert await until(js, "!document.getElementById('place-notice').hidden")
    assert await js("document.getElementById('place-notice-text').textContent") == "New agents use Brave · Work."
    await js(f"{chip}.click(); true")
    assert await until(js, f"!!{item}('Profile 2')")
    await click_as_user(js, "#place-chip .place-profile[data-folder='Profile 2']")  # needs the watcher: Settings
    for _ in range(50):
        infos = (await stack["cdp"].send("Target.getTargets"))["targetInfos"]
        if any(info["url"].endswith("/settings#where") for info in infos):
            break
        await asyncio.sleep(0.1)
    assert any(info["url"].endswith("/settings#where") for info in infos)
    assert server.links.current.profile == "Profile 1"  # it sent nothing


@CHROME
async def test_a_hostile_profile_name_stays_text_in_ai_home(home, monkeypatch, tmp_path):
    from places_rig import LOCAL_STATE

    js, stack = home
    state = json.loads(json.dumps(LOCAL_STATE))
    state["profile"]["info_cache"]["Default"]["name"] = HOSTILE
    settings_rig(monkeypatch, tmp_path, stack, local_state=state)
    assert await until(js, "(document.querySelector('#place-chip .place-chip')?.textContent || '').includes('<img')")
    assert await js("document.querySelectorAll('#place-chip img, #browser-card img').length") == 0
    assert await js("document.title") != "pwned"


@CHROME
async def test_restart_in_shows_only_for_agents_elsewhere(home, monkeypatch, tmp_path):
    from ai_browser.places import Place

    js, stack = home
    server = stack["server"]
    folders = settings_rig(monkeypatch, tmp_path, stack)
    old = await server.agents.create("Fix the footer")  # placed in Brave · Personal
    restart = f"document.querySelector(\"#agents .agent[data-id='{old.id}'] .restart\")"
    assert await until(js, f"!!{restart} && {restart}.hidden")
    work = Place("brave", str(folders["brave"]), "Profile 1")
    server.links.set_current(work)  # as place_set does
    server.agents.place = work
    server._browser_changed()
    assert await until(js, f"!{restart}.hidden && {restart}.textContent === 'Restart in Brave · Work'")
    assert await js(f"document.querySelector(\"#agents .agent[data-id='{old.id}'] .place-chip\").textContent") == \
        "Brave · Personal"
    assert "Its tabs here stay open." in await js(
        f"document.querySelector(\"#agents .agent[data-id='{old.id}'] .restart-note\").textContent")
    await js(f"{restart}.click(); true")
    for _ in range(50):
        if len(server.agents.agents) == 2:
            break
        await asyncio.sleep(0.1)
    assert len(server.agents.agents) == 2 and old.id in server.agents.agents


@CHROME
async def test_the_tab_list_says_it_shows_the_chosen_profile(home, monkeypatch, tmp_path):
    from ai_browser.places import Place
    from fake_brave import FakeBrave

    js, stack = home
    server = stack["server"]
    folders = settings_rig(monkeypatch, tmp_path, stack)
    agent = await server.agents.create("Fix the footer", place=Place("brave", str(folders["brave"]), "Profile 1"))
    brave = FakeBrave([{"target": "U1", "url": "https://mail.example/", "title": "Mail"},
                       {"target": "A1", "url": "https://shop.example/", "title": "Shop", "context": "C0"}],
                      state="connected", folder=folders["brave"])
    brave.owners["A1"] = {"kind": "agent", "id": agent.id, "name": agent.name, "color": agent.color}
    brave.tab_scope = {"profile": "last_used", "elsewhere": 2}
    server.attach_brave(brave, place=Place("brave", str(folders["brave"]), "Default"))
    server.links.place_context = lambda place: "C9"  # the agent's place's copy is in C9; its tab landed in C0
    server._tabs_changed()
    row = "(target => document.querySelector(`#tabs .tab[data-target='${target}']`))"
    assert await until(js, f"{row}('A1')?.querySelector('.place')?.textContent === 'Brave · Work'")
    assert await js(f"{row}('A1').querySelector('.other').textContent") == "in another profile"
    assert await js(f"{row}('U1').querySelector('.place').hidden") is True
    assert await js("document.querySelector('#tabs .scope-source').textContent") == (
        "Showing the Brave profile you used last: the watcher isn't in Personal yet, so agents' tabs open there too.")
    assert await js("document.querySelector('#tabs .elsewhere').textContent") == (
        "2 more tabs in other profiles or private windows: not shown here.")  # wave 1B's line, unchanged


@CHROME
async def test_give_to_lists_only_agents_in_the_same_browser(home, monkeypatch, tmp_path):
    from ai_browser.places import Place
    from fake_brave import FakeBrave

    js, stack = home
    server = stack["server"]
    folders = settings_rig(monkeypatch, tmp_path, stack)
    personal = Place("brave", str(folders["brave"]), "Default")
    server.attach_brave(FakeBrave([{"target": "U1", "url": "https://mail.example/", "title": "Mail"}],
                                  folder=folders["brave"]), place=personal)
    first = await server.agents.create("Fix the footer")
    await server.agents.create("Check prices", place=Place("chrome", str(folders["chrome"]), "Default"))
    third = await server.agents.create("Work task", place=Place("brave", str(folders["brave"]), "Profile 1"))
    hand = "document.querySelector(\"#tabs .tab[data-target='U1'] .hand\")"
    assert await until(js, f"!!{hand}")
    await js(f"{hand}.click(); true")
    labels = await js("[...document.querySelectorAll(\"#tabs .tab[data-target='U1'] .give\")]"
                      ".map(node => node.textContent)")
    assert labels == [f"Give to {third.number} · Work task (in Work)", f"Give to {first.number} · Fix the footer"]
```

(`click_as_user` is wave B's helper in this file.)

In wave B's `test_the_browser_card_follows_brave`, the "Tab groups off: Load the watcher in Brave…" expectation
becomes the watcher line for the attached place: `"Agents' tabs open in whichever Brave profile you used last: the
watcher isn't in Default yet."` (the `FakeBrave` there has no Local State, so the profile's name is its folder).

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_home.py -k "chip_shows or hostile_profile_name_stays_text_in_ai_home or restart_in_shows or says_it_shows_the_chosen or give_to_lists_only" -q -p no:randomly`

Expected: FAIL: there is no `#place-chip`, no `.restart`, no `.place` on rows, and Give to lists every agent.

- [ ] **Step 3: Write the chip, the card's lines, Restart in and the tab list**

Add to `src/ai_browser/app/ui/places.js`:

```js
// AI Home's chip: "Brave · Personal ▾", and its menu. openSettings(section) opens Settings' window there.
export function mountChip(root, { send, openSettings }) {
  const chip = el("button", "place-chip");
  chip.type = "button";
  chip.setAttribute("aria-haspopup", "menu");
  const dot = el("span", "dot");
  const text = el("span", "text");
  chip.append(dot, text);
  const menu = el("div", "place-menu");
  menu.hidden = true;
  root.replaceChildren(chip, menu);
  let view = null;
  let place = null;

  function item(className, label, onClick) {
    const node = button(className, label, () => {
      menu.hidden = true;
      onClick();
    });
    return node;
  }

  function build() {
    menu.textContent = "";
    const browsers = view?.browsers || [];
    const current = browsers.find((browser) => browser.id === place?.browser);
    menu.append(el("p", "head muted", "New agents browse in:"));
    for (const profile of current?.profiles || []) {
      const needs = needsWatcher(profile);
      const here = profile.folder === place.profile;
      const node = item("place-profile", "", () => {
        if (needs) openSettings("where"); // set it up there; nothing is switched
        else if (!here) send({ type: "place_set", browser: current.id, profile: profile.folder }); // instant
      });
      node.dataset.folder = profile.folder;
      const swatch = el("span", "dot");
      swatch.style.background = safeColor(profile.color);
      node.append(swatch, el("span", "name", profile.name),
        el("span", "muted", needs ? " · needs the watcher" : here ? " · ✓" : ""));
      menu.append(node);
    }
    for (const browser of browsers.filter((found) => found.agents && found.id !== place?.browser)) {
      const on = browser.state === "switch_on" || browser.state === "connected";
      const node = item("place-browser", `${browser.name} · ${on ? "it will ask Allow once" : "Show me how"}`, () => {
        const folder = pickProfile(browser);
        if (on && folder) send({ type: "place_set", browser: browser.id, profile: folder });
        else openSettings("where");
      });
      node.dataset.id = browser.id;
      menu.append(node);
    }
    menu.append(item("place-settings", "Settings…", () => openSettings("where")));
  }

  chip.addEventListener("click", () => {
    menu.hidden = !menu.hidden;
    if (!menu.hidden) {
      build();
      send({ type: "browsers" }); // the profiles as the files say now; the menu redraws when they arrive
    }
  });

  function render(nextView, browserInfo) {
    if (nextView) view = nextView;
    if (browserInfo?.place) place = browserInfo.place;
    if (!place) return;
    text.textContent = `${place.label}${place.automatic ? " (chosen for you)" : ""} ▾`;
    dot.style.background = safeColor(place.color);
    if (!menu.hidden) build();
  }

  return { render };
}
```

In `src/ai_browser/app/ui/home.html`, the browser card's header line gains `<div id="place-chip"></div>` before
`#browser-title`, and the card gains, after `#browser-groups`:

```html
  <p id="browser-chosen" class="muted" hidden>Pick the profile you're signed in on in Settings.</p>
  <p id="browser-window-note" class="muted" hidden></p>
  <button id="browser-setup" class="ghost" type="button" hidden>Set it up</button>
  <p id="place-notice" class="notice" hidden><span id="place-notice-text"></span>
    <button id="place-notice-close" class="ghost" type="button" aria-label="Dismiss">✕</button></p>
```

In `src/ai_browser/app/ui/home.js`, import `browserLabel`, `mountChip`, `profileName` from `./places.js` and wave B's
`openWindow` from `./nav.js`:

```js
const openSettings = (section) => openWindow(`/settings#${section}`, "aib-settings", 720, 760);
const placeChip = mountChip($("place-chip"), { send: (message) => link.send(message), openSettings });
let browsersView = null;

const WATCHER_LINES = { // the card's line for the chosen profile, in place of the old "tab groups off" text
  missing: (name, profile) => `Agents' tabs open in whichever ${name} profile you used last: the watcher isn't in `
    + `${profile} yet.`,
  asleep: (name, profile) => `The watcher in ${profile} isn't connected: open a ${name} window in ${profile}.`,
  shared: (name, profile, extensions) => `The watcher folder for ${profile} is loaded in two profiles: remove it from `
    + `one in ${extensions}.`,
  unknown: (name) => `Checking which ${name} profile the watcher is in…`,
};

function extensionsOf(place) {
  return String(place?.browser || "").startsWith("brave") ? "brave://extensions" : "chrome://extensions";
}
```

In `renderBrowser()`, after wave B's lines, replace what sets `#browser-groups` with:

```js
  const place = browser.place;
  const profile = profileName(place);
  const extensions = extensionsOf(place);
  let line = "";
  if (place && browser.extra_watcher) {
    line = `Two AI Browser watchers are loaded in ${profile}: remove the extra one in ${extensions}.`;
  } else if (place && WATCHER_LINES[browser.watcher]) {
    line = WATCHER_LINES[browser.watcher](name, profile, extensions);
  } else if (browser.groups === "old_watcher") {
    line = `Update the watcher: reload it in ${extensions}.`;
  }
  show($("browser-groups"), line);
  $("browser-setup").hidden = browser.watcher !== "missing";
  $("browser-chosen").hidden = !place?.automatic;
  placeChip.render(browsersView, browser);
  renderAgents(); // Restart in follows the current place
```

`#browser-setup` opens `openSettings("where")` on click. In `handle(message)`, the `browser` case keeps the whole
message (`browser = { ...message }`, so `place`, `watcher` and `extra_watcher` are kept), and:

```js
    case "browsers":
      browsersView = message;
      placeChip.render(browsersView, browser);
      show($("browser-window-note"), message.new_window_note || ""); // Task 1, fact 1: only when it comes forward
      break;
    case "place_changed": {
      const stay = message.elsewhere === 1 ? "1 running agent stays" : `${message.elsewhere} running agents stay`;
      const elsewhere = message.elsewhere ? ` ${stay} in ${message.elsewhere_labels.join(" and ")}.` : "";
      $("place-notice-text").textContent = `New agents use ${message.label}.${elsewhere}`;
      $("place-notice").hidden = false;
      break;
    }
```

with `$("place-notice-close").addEventListener("click", () => { $("place-notice").hidden = true; })`. In wave 2A's
connected-clients list, a row's text starts with its `browser` ("Chrome · ") when the rows name more than one browser.

Agent rows (`makeAgentRow` / `fillAgentRow`): `makeAgentRow` makes `parts.place = el("span", "place-chip")` (appended
to `head`, after the state chip), `parts.restart = button("restart ghost", "", () => link.send({ type: "restart_in",
id }))` (appended to `buttons`, before Close) and `parts.restartNote = el("p", "restart-note muted", "Stops this agent
and starts a new one there with the same task. Its tabs here stay open.")` (appended to `main`), all three `hidden` at
first. `fillAgentRow` sets them:

```js
  const here = browser?.place;
  const elsewhere = Boolean(agent.place && here && (agent.place.browser !== here.browser
    || agent.place.profile !== here.profile));
  setText(parts.place, elsewhere ? agent.place.label : "");
  parts.place.hidden = !elsewhere;
  setText(parts.restart, elsewhere ? `Restart in ${here.label}` : "");
  parts.restart.hidden = !elsewhere;
  parts.restartNote.hidden = !elsewhere;
```

`renderTabs()` passes the current place: `tabList.render(tabs, { brave: true, ownerOf, scope: tabScope, place:
browser?.place })`.

In `src/ai_browser/app/ui/tablist.js`, import `profileName` from `./places.js`. `makeRow` adds `parts.place =
el("span", "place chip")` and `parts.other = el("span", "other muted")` after `parts.chip`. In `render`, for each
row:

```js
      setText(parts.place, tab.place ? tab.place.label : ""); // its owner's place, never from the page
      parts.place.hidden = !tab.place;
      setText(parts.other, tab.other_profile ? "in another profile" : "");
      parts.other.hidden = !tab.other_profile;
```

`render`'s options gain `place`; wave 1B's `p.scope-source` line for `"last_used"` becomes, when `place` is known:

```js
      `Showing the ${browserName} profile you used last: the watcher isn't in ${profileName(place)} yet, so agents' `
        + "tabs open there too."
```

(`browserName` is `place.label`'s part before " · "; without `place`, wave 1B's words stay). `"chosen"` has no line,
as `"watcher"` had none. `toggleMenu`'s Give to keeps only agents in the tab's browser, the current one, and marks
another profile:

```js
    const here = current?.place; // set by render(…, { place })
    for (const agent of agents().filter((one) => !here || !one.place || one.place.browser === here.browser)) {
      const other = here && agent.place && agent.place.profile !== here.profile ? ` (in ${profileName(agent.place)})`
        : "";
      const give = button("give", `Give to ${agentLabel(agent)}${other}`, () => {
        menu.hidden = true;
        send({ type: "hand_tab", id: agent.id, target: row.tab.target });
      });
      give.dataset.id = agent.id;
      menu.append(give);
    }
```

where `current` is a variable `render` sets from its options (`current = { place }`). The server checks the same rule
(Task 20).

`home.css`: `.place-chip` (a pill with its dot), `.place-menu` (an absolutely placed list under the chip),
`.notice`, `.restart`, `.restart-note`, `#tabs .place`, `#tabs .other`.

- [ ] **Step 4: Run them, and AI Home's other tests**

Run: `uv run pytest tests/test_home.py tests/test_ui_static.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/ui/places.js src/ai_browser/app/ui/home.html src/ai_browser/app/ui/home.js \
        src/ai_browser/app/ui/home.css src/ai_browser/app/ui/tablist.js tests/test_home.py
git commit -m "feat: AI Home's place chip, its notice and watcher line, Restart in, and a tab list on the chosen profile"
```

### Task 25: Mission Control: the agent's place, **Restart in**, and Your tabs per browser

**Files:**
- Modify: `src/ai_browser/app/ui/mission.js`, `mission.css`, `tablist.js` (`mountYourTabs`)
- Test: `tests/test_mission.py`

**Interfaces:**
- Consumes: wave A's drawer (`openAgent`, `fillDrawer`, `drawer.parts`), `mountYourTabs(root, { send, agentId })`
  with `render(tabs, { brave, connected, name })`, Mission Control's `tabs` and `browser` state; Task 23's
  `browserLabel`, `profileName`; Task 20's `restart_in`.
- Produces:
  - the drawer's `parts.place` (`.place-chip`) and `parts.restart` (`.restart`, "Restart in Chrome · Work");
  - `mountYourTabs`'s `render(tabs, { brave, connected, name, agentPlace, current })`: an agent in another browser
    gets no rows and one `.elsewhere-browser` line, "This agent works in Chrome: your tabs here are Brave's."; an
    agent in another profile of the same browser gets "Give to this agent (in Work)".

- [ ] **Step 1: Write the failing test**

In `tests/test_mission.py` add (`mission` is this file's fixture, on wave B's rebuilt `stack`):

```python
@CHROME
async def test_your_tabs_follow_the_agents_browser(mission, monkeypatch, tmp_path):
    from ai_browser.places import Place
    from fake_brave import FakeBrave
    from test_home import settings_rig

    js, stack = mission
    server = stack["server"]
    folders = settings_rig(monkeypatch, tmp_path, stack)
    server.attach_brave(FakeBrave([{"target": "U1", "url": "https://mail.example/", "title": "Mail"}],
                                  folder=folders["brave"]), place=Place("brave", str(folders["brave"]), "Default"))
    chrome = await server.agents.create("Check prices", place=Place("chrome", str(folders["chrome"]), "Default"))
    work = await server.agents.create("Work task", place=Place("brave", str(folders["brave"]), "Profile 1"))
    drawer = "document.querySelector('#drawer:not([hidden])')"
    assert await until(js, f"!!document.querySelector(\"#list [data-id='{chrome.id}']\")")
    await js(f"document.querySelector(\"#list [data-id='{chrome.id}']\").click(); true")
    assert await until(js, f"!!{drawer}?.querySelector('.your-tabs .elsewhere-browser')")
    assert await js(f"{drawer}.querySelector('.your-tabs .elsewhere-browser').textContent") == \
        "This agent works in Chrome: your tabs here are Brave's."
    assert await js(f"{drawer}.querySelectorAll('.your-tab').length") == 0
    assert await js(f"{drawer}.querySelector('.place-chip').textContent") == "Chrome · Personal"  # the rig's names
    assert await js(f"{drawer}.querySelector('.restart').textContent") == "Restart in Brave · Personal"
    await js(f"document.querySelector(\"#list [data-id='{work.id}']\").click(); true")
    assert await until(js, f"{drawer}?.querySelector('.your-tab .give-here')?.textContent === "
                           "'Give to this agent (in Work)'")
    await js(f"{drawer}.querySelector('.restart').click(); true")
    for _ in range(50):
        if len(server.agents.agents) == 3:
            break
        await asyncio.sleep(0.1)
    assert len(server.agents.agents) == 3  # Restart in from Mission Control's drawer
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_mission.py::test_your_tabs_follow_the_agents_browser -q -p no:randomly`

Expected: FAIL: the drawer has no `.elsewhere-browser` line and no `.restart`.

- [ ] **Step 3: Write the drawer's place**

In `src/ai_browser/app/ui/mission.js`, import `browserLabel`, `profileName` from `./places.js`. Wave A's `browser`
state keeps the whole message (its `place` included): where it copies chosen keys from a `browser` message, it takes
`{ ...message }` instead. `openAgent` adds two parts to the drawer's buttons row:

```js
  parts.place = el("span", "place-chip");
  parts.restart = button("restart ghost", "", () => link.send({ type: "restart_in", id }));
  parts.restart.title = "Stops this agent and starts a new one there with the same task. Its tabs here stay open.";
  parts.buttons.append(parts.place, parts.restart);
```

`fillDrawer(agent)` sets them, and passes the places to Your tabs:

```js
  const here = browser?.place;
  const elsewhere = Boolean(agent.place && here && (agent.place.browser !== here.browser
    || agent.place.profile !== here.profile));
  setText(parts.place, agent.place ? agent.place.label : "");
  setText(parts.restart, elsewhere ? `Restart in ${here.label}` : "");
  parts.restart.hidden = !elsewhere;
```

and wherever wave A renders the drawer's Your tabs (`yourTabs.render(tabs, { brave, connected, name })`), add
`agentPlace: agent.place, current: browser?.place`.

In `src/ai_browser/app/ui/tablist.js`, `mountYourTabs`'s `render` (wave A's) takes two more options and, right after
its "isn't connected yet" branch, handles an agent in another browser and labels one in another profile:

```js
  function render(tabs, { brave = false, connected = false, name = "Brave", agentPlace = null, current = null } = {}) {
    // wave A's first lines stay: root.hidden = !brave; list.textContent = ""; the !brave return; the !connected branch
    if (agentPlace && current && agentPlace.browser !== current.browser) { // its relay can't reach this browser's tabs
      summary.textContent = "Your tabs (0)";
      list.append(el("p", "elsewhere-browser muted",
        `This agent works in ${browserLabel(agentPlace)}: your tabs here are ${browserLabel(current)}'s.`));
      return;
    }
    const other = agentPlace && current && agentPlace.profile !== current.profile
      ? ` (in ${profileName(agentPlace)})` : "";
    // wave A's rows follow unchanged, except the `.give-here` button's text: `Give to this agent${other}`
  }
```

with `import { browserLabel, profileName } from "./places.js";` at the top of `tablist.js` (Task 24 already imports
`profileName` there). `summary` and `list` are wave A's names for the `<summary>` and the rows' container.

- [ ] **Step 4: Run it, and Mission Control's file**

Run: `uv run pytest tests/test_mission.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/ui/mission.js src/ai_browser/app/ui/mission.css src/ai_browser/app/ui/tablist.js \
        tests/test_mission.py
git commit -m "feat: Mission Control shows an agent's place, offers Restart in, and Your tabs per browser"
```

### Task 26: Two profiles, visibly: tabs land in the chosen profile (headful, run by the main session)

**Files:**
- Test: `tests/test_profiles_headful.py` (new; every test `headful`)

**Interfaces:**
- Consumes: Task 1's `tests/two_profiles.py` (`launch_two_profiles`, `page_contexts`, `page_outside`, `worker`);
  Tasks 11-22 (the copies, the links, `Watchers`, `/agent-open`, the engine's placement and notes); Task 15's
  `where.WINDOW_FRONT_NOTE` (fact 1); `tests/fake_brave.add_agent`; `test_home.evaluate`; `testpages.serve_host`.
- Produces: the spec's four "Visible browser, two profiles" tests, skipped unless `AIB_HEADFUL=1`.

- [ ] **Step 1: Write the tests**

`tests/test_profiles_headful.py`:

```python
"""Two profiles in a visible throwaway Chrome (AIB_HEADFUL=1 only; the main session runs these with the user's OK):
an agent's tabs land in its copy's profile whatever the user clicked last; without a copy there they fall back and
say so; a profile with no window gets one behind; a private window is never listed or used. Never the user's own
browsers: the Chrome here has its own temporary --user-data-dir."""

import asyncio
import subprocess
from types import SimpleNamespace

import pytest

from ai_browser.chrome import chrome_binary
from fake_brave import add_agent
from test_home import evaluate

pytestmark = [pytest.mark.headful, pytest.mark.posix_only,
              pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")]


async def profiles_app(tmp_path):
    """An app server holding a link on the two-profile Chrome; Profile 2's copy loaded there and connected."""
    from ai_browser import testpages
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.bravelink import InstanceLink
    from ai_browser.app.server import AppServer
    from ai_browser.cdp import CDP
    from ai_browser.extension_id import extension_id_for
    from ai_browser.places import Place
    from two_profiles import launch_two_profiles, page_outside, worker

    home = tmp_path / "home"
    server = AppServer(home, AgentManager(home))
    url = await server.start()
    server.copies.prepare_all(url, server.token)
    copy = server.copies.make("chrome", "Profile 2", url, server.token, ["Default", "Profile 2"])
    two = launch_two_profiles(tmp_path / "browser")  # Profile 2 first: the only profile open
    loaded = two.load(copy)
    assert loaded == extension_id_for(copy)
    cdp = await CDP.connect(two.ws_url)
    _, p2 = await worker(cdp, loaded)
    two.open_profile("Default")  # the user's window, in the other profile
    user = await page_outside(cdp, p2)
    work = Place("", str(two.folder), "Profile 2")
    server.attach_brave(InstanceLink(two.folder, watcher_ids={loaded}, tokens=server.tokens, app_origin=url),
                        place=work)
    server.allow_watcher(f"chrome-extension://{loaded}", copy=copy.name)
    server.watchers.find_places = lambda: {loaded: [work]}  # what its Secure Preferences say (fact 2's timing aside)
    await server.links.started(work)
    await server.links.connect(work, "start")  # a --remote-debugging-port browser never asks Allow
    for _ in range(300):
        conn = server.watchers.for_place(work)
        if conn is not None and server.watchers.context(conn) == p2 and conn.groups.can_open():
            break
        await asyncio.sleep(0.1)
    else:
        raise AssertionError("Profile 2's copy never connected with its context")
    base, _, stop_pages = testpages.serve_host()
    session = (await cdp.send("Target.attachToTarget", {"targetId": user, "flatten": True}))["sessionId"]
    return SimpleNamespace(server=server, url=url, two=two, cdp=cdp, p2=p2, user=user, user_session=session,
                           work=work, base=base, stop_pages=stop_pages, home=home)


async def close_app(app):
    await app.server.stop()
    await app.server.links.close()
    await app.cdp.close()
    app.two.close()
    app.stop_pages()


def engine_for(app, monkeypatch, agent_id, profile):
    from ai_browser.engine import Engine
    from ai_browser.skills import Catalog

    for key, value in {"AIB_BROWSER": "chrome", "AIB_CHROME_DIR": str(app.two.folder), "AIB_CHROME_PROFILE": profile,
                       "AIB_APP_AGENT": agent_id, "AIB_APP_EVENTS": app.url + "/agent-events",
                       "AIB_APP_AGENT_TOKEN": app.server.token_for(agent_id),
                       "AIB_APP_CDP": app.url.replace("http", "ws") + "/cdp"}.items():
        monkeypatch.setenv(key, value)
    return Engine(home=app.home / f"engine-{agent_id}", catalog=Catalog([], set()))


async def context_of(app, target):
    return (await app.cdp.send("Target.getTargetInfo", {"targetId": target}))["targetInfo"]["browserContextId"]


async def front_is_the_users(app) -> bool:
    await app.cdp.send("Target.activateTarget", {"targetId": app.user})
    await asyncio.sleep(1)
    return await evaluate(app.cdp, app.user_session, "document.hasFocus()") is True


async def test_tabs_land_in_the_watchers_profile_whatever_was_used_last(tmp_path, monkeypatch):
    app = await profiles_app(tmp_path)
    engine = None
    try:
        add_agent(app.server.agents, "a1").where = app.work
        assert await front_is_the_users(app)  # a Default tab is active: Default is the profile used last
        engine = engine_for(app, monkeypatch, "a1", "Profile 2")
        text = (await engine.open(app.base + "form.html")).text
        assert await context_of(app, engine.browser.current.target) == app.p2
        assert "profile the user used last" not in text
        assert await evaluate(app.cdp, app.user_session, "document.hasFocus()") is True  # the focus never moved
    finally:
        if engine is not None:
            await engine.close()
        await close_app(app)


async def test_the_fallback_lands_in_the_profile_used_last_and_says_so(tmp_path, monkeypatch):
    from ai_browser.places import Place

    app = await profiles_app(tmp_path)
    engine = None
    try:
        add_agent(app.server.agents, "a2").where = Place("", str(app.two.folder), "Default")  # no copy in Default
        assert await front_is_the_users(app)
        engine = engine_for(app, monkeypatch, "a2", "Default")
        text = (await engine.open(app.base + "form.html")).text
        assert await context_of(app, engine.browser.current.target) == await context_of(app, app.user)
        assert "(tab t1 opened in the Chrome profile the user used last" in text
    finally:
        if engine is not None:
            await engine.close()
        await close_app(app)


async def test_a_profile_with_no_window_gets_one_behind(tmp_path, monkeypatch):
    from ai_browser.app import where
    from two_profiles import page_contexts

    app = await profiles_app(tmp_path)
    engine = None
    try:
        for target, (_, context) in (await page_contexts(app.cdp)).items():
            if context == app.p2:
                await app.cdp.send("Target.closeTarget", {"targetId": target})  # Profile 2 has no window now
        await asyncio.sleep(1)  # its copy stays connected a while (Task 1, fact 4)
        add_agent(app.server.agents, "a1").where = app.work
        assert await front_is_the_users(app)
        engine = engine_for(app, monkeypatch, "a1", "Profile 2")
        text = (await engine.open(app.base + "form.html")).text
        assert "(a new Chrome window was opened for tab t1: the chosen profile had none open)" in text
        assert await context_of(app, engine.browser.current.target) == app.p2
        if not where.WINDOW_FRONT_NOTE:  # fact 1 found the window stays behind on this OS
            assert await evaluate(app.cdp, app.user_session, "document.hasFocus()") is True
    finally:
        if engine is not None:
            await engine.close()
        await close_app(app)


async def test_a_private_window_is_never_listed_or_used(tmp_path, monkeypatch):
    from two_profiles import page_contexts

    app = await profiles_app(tmp_path)
    engine = None
    try:
        before = app.server.links.tabs()[1]["elsewhere"]
        subprocess.run([chrome_binary(), f"--user-data-dir={app.two.folder}", "--profile-directory=Profile 2",
                        "--incognito", app.base + "privacy.html"], timeout=30, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await asyncio.sleep(2)
        private = [target for target, (url, context) in (await page_contexts(app.cdp)).items()
                   if url == app.base + "privacy.html" and context not in (app.p2, await context_of(app, app.user))]
        assert len(private) == 1
        rows, scope = app.server.links.tabs()
        assert private[0] not in [row["target"] for row in rows] and scope["elsewhere"] == before + 1
        add_agent(app.server.agents, "a1").where = app.work
        engine = engine_for(app, monkeypatch, "a1", "Profile 2")
        await engine.open(app.base + "form.html")
        assert await context_of(app, engine.browser.current.target) == app.p2  # never the private window's
    finally:
        if engine is not None:
            await engine.close()
        await close_app(app)
```

- [ ] **Step 2: Run them to see them skip**

Run: `uv run pytest tests/test_profiles_headful.py -q -p no:randomly`

Expected: four SKIPPED ("headful: opens visible throwaway browser windows; runs only with AIB_HEADFUL=1"). A
subagent stops here.

- [ ] **Step 3: The main session runs them, with the user's OK**

The main session asks: "May I open visible throwaway Chrome windows for about three minutes, to check that agents'
tabs land in the chosen profile? They use their own temporary profiles, never your Brave or Chrome." Only after a yes:

Run: `AIB_HEADFUL=1 uv run pytest tests/test_profiles_headful.py -q -s -p no:randomly`

Expected: four PASSED. If one fails, fix it test-first in the task that owns the code (Task 22 for the watcher's
`openTab`, Task 19 for `/agent-open`, Task 6 for the engine's placement), then run this file again.

- [ ] **Step 4: Record**

Write the run's tail to the ledger, with which of the four passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_profiles_headful.py
git commit -m "test: two profiles in a visible throwaway Chrome: tabs land in the chosen profile, private windows never"
```

### Task 27: The README; the whole suite and the bench

**Files:**
- Modify: `README.md`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: every earlier task; the README as waves A and B and Task 21 left it ("Which browser", "Use your everyday
  Brave (the default)", the "AI Browser" section with AI Home's browser card and tab list, "Commands").
- Produces: the README says where agents browse, how to choose, the per-profile watcher, what stays private, and the
  `AIB_CHROME_DIR` rule.

- [ ] **Step 1: Write the failing test**

In `tests/test_cli.py` add:

```python
def test_the_readme_says_where_agents_browse():
    from ai_browser.config import project_root

    text = " ".join((project_root() / "README.md").read_text(encoding="utf-8").split())
    for words in ("Settings → Where agents browse",
                  "one Load unpacked in each profile agents use",
                  "Switching profile needs no new Allow; switching to another browser asks once",
                  "never sends profile names to Claude",
                  "remove `AIB_CHROME_DIR` from your `.mcp.json` to follow Settings",
                  "Restart in"):
        assert words in text, words
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_cli.py::test_the_readme_says_where_agents_browse -q -p no:randomly`

Expected: FAIL on "Settings → Where agents browse".

- [ ] **Step 3: Write the README**

1. In "Which browser", after its first paragraph, add:

```markdown
**Where agents browse is your choice, in Settings → Where agents browse.** Pick the browser and the profile you are
signed in on; it is saved, and every new agent uses it. Until you pick, AI Browser chooses for you (your default
browser, in the profile that holds the watcher, else the one you used last) and says "chosen for you".
- Switching profile needs no new Allow; switching to another browser asks once, right after you switch. Agents already
  at work stay where they started: a button on each, **Restart in**, starts the same task in the new place (its old
  tabs stay open).
- Each profile agents use needs its own copy of the watcher: one Load unpacked in each profile agents use. **Set it up**
  on a profile's row makes its folder and shows it in Finder (File Explorer on Windows).
- With the watcher in the chosen profile, each agent's tab opens there, in its group, in the background, whatever
  profile you are clicking in. Without it, the tab opens in the profile you used last, and the agent says so once.
- Names and colours come from the browser's own files on this computer. AI Browser never reads the email you are signed
  in with, never sends profile names to Claude, and its terminal shows profile folders only ("profile folder
  Profile 1").
```

2. In "Use your everyday Brave (the default)", replace the sentence that says Google Chrome is found by itself
   ("…The folder is found by itself, Brave first; set `AIB_CHROME_DIR` to pick one…") with:

```markdown
Google Chrome works the same way (`chrome://inspect/#remote-debugging`): pick it in Settings → Where agents browse.
Claude Code sessions follow that choice too, from their first browser call until they end. A session whose
environment sets `AIB_CHROME_DIR` keeps that browser whatever Settings says (it still follows Settings' profile while
both name the same browser): remove `AIB_CHROME_DIR` from your `.mcp.json` to follow Settings.
```

3. In the "AI Browser" section's browser-card bullet, add: "Its title is a chip, **Brave · Personal ▾**: pick another
   profile or browser there, or open Settings." In its tab-list bullet, replace "the web tabs of the Brave profile the
   watcher is in (without the watcher, the profile you used last)" (wave A's words) with "the web tabs of the profile
   agents use (without its watcher, the profile you used last)", and add: "an agent's tab in another profile or
   browser shows a small place chip".

4. In "Commands", the `doctor` line's comment gains "(and where agents browse)".

- [ ] **Step 4: Run the docs test, then the whole suite and the bench**

Run: `uv run pytest tests/test_cli.py tests/test_app_run.py::test_the_allow_line_names_a_browser_switch -q -p no:randomly`

Expected: PASS.

Run: `uv run pytest -q -p no:randomly`

Expected: PASS. Docker tests skip when Docker or the image is missing; the Chrome tests need Google Chrome; the
`headful` tests skip (Task 26 ran them). Write the tail of the output to the ledger. If anything fails, fix it
test-first in the task that owns the code, then run the whole suite again.

Run: `uv run ai-browser bench`

Expected: every row PASS. This wave adds one round trip to the app (`/agent-open`) when an agent opens a tab, and
nothing to reading or acting; the bench runs in the sandbox. Write the table to the ledger.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_cli.py
git commit -m "docs: where agents browse: Settings' choice, a watcher per profile, Restart in, and what stays private"
```

Then:
1. **The final review.** A fresh reviewer checks the branch against the Global Constraints, the Review Focus and the
   Seams. One fix pass follows, test-first; minor findings go to the ledger.
2. **The manual check, by the user, in their own Brave** (the spec's list; the main session asks the user, and no
   agent connects to the user's Brave):
   1. Open Settings → Where agents browse. Brave and Chrome show, with no Arc, Edge, Vivaldi or Opera card. Brave's
      profiles show with names and colours and no email.
   2. Pick the profile you're signed in on. If it says "Needs the watcher", click **Set it up** and load the folder
      there once.
   3. Click in a window of your other profile, then give an agent a task. Its tab appears in the chosen profile, in its
      group, and your window keeps the focus.
   4. In the chip, switch to the other profile: no Allow appears. Switch back.
   5. AI Home's tab list shows only the chosen profile's tabs, and one line counting the rest. Open a private window:
      no row appears for it.
   6. Optional: switch to Chrome with its switch on. Chrome asks Allow once. The running Brave agent keeps working, and
      offers **Restart in Chrome · …**.
   7. If the repo's `.mcp.json` still sets `AIB_CHROME_DIR`, Claude Code sessions stay in that browser whatever
      Settings says. Remove it to let them follow Settings.
3. **On the Windows laptop** (added to the windows-and-repo spec's laptop list): Settings lists the installed browsers
   from the registry, with Brave's profiles; **Set it up** on a second profile opens File Explorer at its folder, and
   after Load unpacked there the row shows ✓ watcher (this confirms a copy's Windows extension id); steps 3 and 4 of
   the Mac check; a new window for a profile with no window stays behind (Task 1, fact 1).
4. **Restart the user's `ai-browser app`** only when the user says so, so the new pages and every watcher copy load.
   Each copy reloads itself when its files change.

