# Review of the browser-profile-choice plan (before it is built)

Date: 2026-10-03. Reviewer: a fresh agent on the most capable model, against the spec and the code at b8de841 (after
the cdp-relay merge, before waves A and B). The builder applies every finding below as a `Pre-flight: Ruling:` in the
plan's ledger, after re-reading the code at HEAD (waves A and B will have moved more anchors). Plan line numbers are
`plan:`.

## Critical

**C1. Agents get `rediscover`, so their link turns into a phantom session after 10 s.**
- Where: plan:2269-2274. One statement replaces the three Placer branches at engine.py:245-252, and every Placer gets
  `rediscover=rediscover`.
- Problem: an agent's engine has AIB_HOME set to the app's home. After REREAD_EVERY (grouping.py:25, `_refresh`
  :64-74), `AgentLink.discover` (agentlink.py:132-146) returns link.json's session link. It has the same events URL but
  a different token, so the agent's link is swapped. Then:
  - `hello` creates a phantom "Claude Code" session in AI Home;
  - `/agent-open` assigns the watcher's tab to `cc-…`;
  - the agent's relay client (`a1`) can't see it (`visible`, cdprelay.py:954-964), so every later tab fails with "the
    new tab was closed…".
- It also drops wave 2A's `elif self._note: Placer(None)` branch. No test in the plan runs an agent past 10 s.
- Fix: keep the three branches and only add `name=`/`place=`. Agents get `Placer(self._link, …)` with no rediscover.
  Add a test that ages `_read_at` and asserts the agent's link is unchanged.

## Important

**I1. Task 7's `_route` snippet doesn't fit the merged engine.**
- Where: plan:2276-2297.
- Problem:
  - `_route()` is sync and returns `Route(kind, folder, url, token, link, note)` (engine.py:61-68, 285-305).
  - The hello happens in `_through_relay` (:311-317). A second hello without a place makes the server record
    `where=None` and answer `{"place": null}` with no token, so `_app_down` is raised.
  - The snippet raises unformatted templates (`APP_GONE`, `CUT_OFF_SESSION`).
  - It invents `_not_through`; the real flag is `Route.note` → `self._note` (:223, 622).
  - The test edit for test_chrome.py:866 expects `place` in the hello body, but `_start_chrome`'s `session.hello()`
    (:266-269) never gets the place.
- Fix:
  - make `_route` async and do the one hello there;
  - return `Route("relay", …, token=answer["cdp_token"], link=link)` and skip `_through_relay`'s hello when
    `route.token` is set;
  - a null place gives a direct `Route` with a `note`;
  - keep `.format(name=…)` and `_app_down`;
  - pass the place to `_start_chrome`'s hello.

**I2. A session can connect directly to a browser the app already holds.**
- Where: `_session_place` (plan:6108-6114) accepts only `browsers.installed()` rows.
- Problem:
  - Plan decision 10 (plan:135-136) lets the app hold a `""` place as its current one. A session on that same folder
    (or on any browser detection missed) gets `{"place": null}` and connects directly. That means a second Allow and a
    second automation connection behind the relay.
  - It silently breaks wave 2A tests the plan never mentions: test_engine.py:573-655. Three of them hit `no_direct`.
    In `…another_browser_goes_direct`, the session is now in `server.sessions`.
  - Decision 10 also contradicts spec :352-353 ("never held by the app").
- Fix:
  - accept a hello whose browser id matches a link the app already holds, and `""` when the current place is `""`;
  - rewrite those four tests;
  - record a Ruling for decision 10.

**I3. A browser switch never connects.**
- Where: `_set_place` (plan:6481) and `InstanceLinks.connect` (plan:3719).
- Problem: a new Relay is "off" until its first look at the switch (cdprelay.py:382, 443-455). `_set_place` calls
  `links.connect(...)` right after `set_current`, and `connect` returns early on "off". This breaks spec success 7 and
  the Safety line "asks once, right after the click". A session's `/cdp` right after its hello's `ensure` (plan:6131)
  can likewise get a false 409 "switch is off". FakeBrave starts "ready", so the tests can't see it.
- Fix:
  - `connect` awaits `self.started(place)` before reading the state;
  - `_agent_hello` awaits `links.started(where)`;
  - add a test whose fake starts "off".

**I4. The tab list stays on "last_used" after Allow.**
- Where: `chosen_context` is set only by `Watchers.sync()` (plan:4317-4325).
- Problem: on "connected", `sync()` runs before the TabWatch exists (bravelink.py:60-69). The link's `_changed` fires
  only when rows or scope change, so nothing re-syncs. AI Home then shows the last-used profile with the false line
  "the watcher isn't in Personal yet" (success 8).
- Fix: re-sync from `links.on_change`, and have InstanceLink signal when the worker contexts it has seen change.

**I5. Settings never shows ✓ watcher after a delayed file write.**
- Where: the re-reads in `arrived` (plan:4305-4315) broadcast `_browsers_view(fresh=False)` (plan:6466-6469).
- Problem: that keeps the stale `watcher` flag from the kept `detect()`. The row needs `watcher && live`
  (plan:7151), so it stays "Needs the watcher".
- Fix: overlay `watcher`/`shared_watcher` from `Watchers._places`, or rebuild the view fresh when placements change.

**I6. Task 9's tests can't run as written.**
- Where: plan:2476-2520 and the seams at plan:84-85.
- Problem:
  - The tests use `relay_client(relay, token)` as an async context manager yielding a raw socket. The real helper is
    `relay_client(url, token) -> CDP` in tests/fake_brave.py:212.
  - `relay_on` never serves the relay, so the port is 0 and the handshake gets 403 (cdprelay.py:610).
  - The internal names don't exist: `targets`→`_targets`, `_fire_grant`→`_grant(id, t, "own")` (:981),
    `_clients_of`→filter `_clients`, `discovery`→`discover`, `_queue_to`→`_announce`/`_to`, `_own_command`→`_call`
    (:544).
- Fix:
  - use test_cdprelay's `rig` fixture (:178-196) and `Raw.open` (:199-227);
  - `close_marker` should suppress `CDPError`;
  - `assign` to a forgotten identity should close the tab, as `_after` does (:853-855).

**I7. Relay plumbing still serves only the current link.**
- Problem:
  - `stop()` closes clients only on `self.brave.relay` (server.py:250-252). Other browsers' sessions and pending Allow
    handshakes aren't answered before uvicorn stops, which undoes the relay's "quitting answers at once".
  - `release()` at :505 and :714 reaches only the current link.
  - `start()` sets the port only on the current relay (:238-239).
  - `_clients()` (plan:5316-5320) drops the name/colour enrichment of `_browser_clients` (:551-565).
- Fix: iterate `self.links.all()` in each, and keep the enrichment while adding `browser`.

**I8. The cut-off check never fires with the real relay.**
- Where: `_cut_off` (plan:6116-6118) uses `getattr(link.relay, "cut_off", ())`.
- Problem: only FakeRelay has that attribute; the real Relay has `is_cut_off()` (cdprelay.py:1000). A disconnected
  session is listed again and gets a token again, against the relay ruling. The plan's test passes only on the fake.
- Also: the cut-off set is lost when a link is pruned.
- Fix: call `is_cut_off`, and keep cut-offs at the server, seeding them into new relays.

**I9. The claim that wave 2A/1B tests "pass unchanged" is wrong.**
- Where: plan:5413-5415.
- Problem:
  - test_app_server.py:557-559 expects 204 from a hello without a relay; the plan answers 200 `{"place": null}`;
  - :777 calls `_from_watcher(kind, msg)`, but the plan adds a `conn` parameter;
  - `_agent_hello` calls `self.links.ensure` even when `links` is None.
- Fix: list these edits in the plan, and guard on `self.links`.

## Minor

- **M1.** `_cdp` (plan:5361-5364) answers 403 for a revoked token; wave 2A answers 410 (cdprelay.py:613-615). Fix:
  hand unknown tokens to the current relay's `serve`.
- **M2.** A place-less re-hello overwrites `where` with None, so a live session's link becomes prunable. Fix: keep the
  known place.
- **M3.** run.py's link factory freezes `watcher_ids=set(folders)` at start (plan:6733), so copies made later by Set it
  up are missing from links made later. Fix: read `server.watchers.ids()` when each link is made.
- **M4.** `Relay.start()` isn't idempotent (cdprelay.py:443-446). `ensure()` now starts links, and BraveApp
  (fake_brave.py:397-399), conftest.py:124-125, test_cdprelay_chrome.py:36 and `tab_list_on` (plan:3535) start them
  again, leaving orphan poll tasks.
- **M5.** FakeBrave already records `connect_calls` (fake_brave.py:298, 338; used at test_app_server.py:1439). The new
  `asked` list must keep appending to it.
- **M6.** `validOpen` limits the title to 40 UTF-16 units, but agent names are limited to 40 code points
  (agents.py:27, 37-49). An emoji name always falls back. Fix: clip the title on the server.
- **M7.** Tests that don't fail first:
  - Task 20 admits two guards already pass at step 2 (plan:6422-6424), against spec :1196-1199;
  - Task 7's stated failure reason is wrong: after Task 3 it fails at `asked == [brave, brave]`.
- **M8.** Task 4 anchor: the hello body is built in `_hello()` (agentlink.py:94-97). Pass it through
  `asyncio.to_thread(self._hello, place)`.

The reviewer found spec coverage otherwise complete. The open_tab marker, assign and close_marker design keeps other
profiles' tabs away from agents, puts no token in pages or logs, and touches neither the Allow prompt nor the bar.
