# Review of the app-window plan (before it is built)

Date: 2026-10-03. Reviewer: a fresh agent on the most capable model, against the spec and the code at b8de841 (after
the cdp-relay merge, before wave A). Anchors that depend on wave A were checked against the 1A, 1B and 2B plans. The
builder applies every finding below as a `Pre-flight: Ruling:` in the plan's ledger, after re-reading the code at HEAD
(wave A will have moved more anchors). Numbers are plan lines unless named.

The reviewer's probe started a headless Chrome with the plan's exact `window_args` plus `--headless=new` (a throwaway
profile):
- the page loads `/open?code` → `/home` exactly once, with or without the extra positional URL;
- the profile gets no `DevToolsActivePort`;
- the browser exits 0 on SIGTERM.

So Task 13's real-window test is sound.

**What already holds:**
- The plan uses everything the relay added correctly: `tokens`/`token_for`, `connect_brave`, `BraveLink.state`/`connect`,
  `/cdp` (kept, behind the guard), `browser_clients`, `write_link`, the server-before-BraveLink stop order, and
  FakePort/FakeBrave/FakeRelay.
- No step bypasses the relay, reconnects directly, reuses a shared token or breaks "Allow once".
- The safety rules hold: the command line is pinned, `textContent` only, keyword and `open_url` hand over nothing, and no
  secret reaches a URL, broadcast or log beyond the spec-approved one-time code.

## Critical

None.

## Important

1. **A Task 19 test that can never pass.** 6203: `assert result.text == f"error: {RETIRED_BROWSER}"`. `Engine._run`
   appends `"\n⏱ {ms} ms"` to every result (engine.py:181).
   - Fix: use `startswith(...)`, as test_engine.py:296 already does.
2. **The pinned `PIPE_FIXTURES` set breaks test_portable.** tests/test_portable.py:26 asserts
   `PIPE_FIXTURES == {"stack","watcher","app_browser","app_engine"}`.
   - Tasks 4 (1564), 13 (3835), 19 (6285) and 21 (6851) shrink the set.
   - Tasks 5 (1690) and 11 (3173) run test_portable.py and expect PASS.
   - Fix: update that assertion in each of those tasks, ending at `{"watcher"}`, and add the file to their commits.
3. **A stale `--help` test.** tests/test_cli.py:80-84 (`test_app_takes_the_browser_choice`) asserts `"{brave,app}" in
   out`.
   - Task 17 sets `metavar="{brave}"` (5833), and Step 4 (5875) expects test_cli.py to pass.
   - Fix: delete that test in Task 17; `test_app_help_offers_the_window_and_brave_only` replaces it.
4. **Mission Control is found by its old `.html` address.** tests/test_mission.py:400
   (`test_an_open_room_does_no_layout_while_agents_work`) uses `t["url"].endswith("/mission.html")`.
   - After Task 13 the page is `/mission`, so `next()` raises StopIteration.
   - Task 13's script and grep (3796-3814) miss it, and Step 4 (4168) expects PASS.
   - Fix: add that replacement (`endswith("/mission")`) to the script, or use `page_targets`.
5. **1B's static guard is never updated.** Watcher-safety's `test_only_the_role_reads_the_watchers_origins` (in
   tests/test_watcher_rules.py; 1B plan 1089-1094) pins the readers of `_watcher_origins` to
   `["__init__","_mismatch","_role","_socket","allow_origin"]`.
   - Task 9 (2653-2702) moves the read into `_socket_kind` and takes it out of `_role` and `_socket`.
   - Task 18 (6056-6062) moves it into `allow_watcher` and deletes `allow_origin`.
   - Both Step 4s (2706-2708 and Task 18's) expect test_watcher_rules.py to pass.
   - Fix: Task 9 sets the list to `["__init__","_mismatch","_socket_kind","allow_origin"]`; Task 18 sets it to
     `["__init__","_mismatch","_socket_kind","allow_watcher"]`, noting that the role is now fixed at accept.
6. **Stale `port` anchors from before the relay.** The relay already has `self.port = 0` (server.py:158), and sets
   `self.port = port` plus `relay.port` after startup (server.py:237-239).
   - Task 6 (1871) inserts `self.port: int | None = None` after `self.url`. The relay's `= 0` line follows and
     overwrites it, so "None before start()" is false.
   - Task 6 (1935) adds a second `self.port = port`, which makes Task 8's "right after `self.port = port`" (2475)
     ambiguous.
   - The import anchor at 1840-1842 is gone: `PlainTextResponse` is already imported (server.py:24).
   - Fix: replace the relay's `= 0` line, move its assignment up to after `if sock is None: continue` (keeping
     `relay.port` after start), and set `strict_headers` there. The import step becomes "add `RedirectResponse`".
7. **The rewritten run tests drop relay assertions.** `test_brave_the_relay_and_the_windows_origin_are_wired`
   (5276-5318) replaces test_app_run.py:316-371 but starts only one agent.
   - It loses "two agents get distinct tokens, neither is the session token" (:368) and the exact link.json keys.
   - The switch-text test (5321-5326) drops "lists everything connected, with Disconnect" (:483).
   - Fix: keep two `new_task`s and those assertions.

## Minor

8. **Task 4 example (1553-1554):** the shown call isn't HEAD's. Use
   `TabWatch("", hidden_origin=self.app_origin, cdp=self.relay.local())` (bravelink.py:72).
9. **Task 8 note (2487-2489):** the relay's Host test (test_cdprelay.py:595-596) runs on `serve_relay`
   (fake_brave.py:188), not AppServer, so the guard never answers it. Drop the note and `tests/test_cdprelay.py` from
   the commit.
10. **setup.html wording (2215-2218):** the plan merges the relay's two warning paragraphs (HEAD setup.html:85-88). Copy
    HEAD's #switch section exactly.
11. **`write_link`:** Task 17 says "keep the merged code's exact words" (5540) but rewrites it with required
    `cdp`/`browser_dir` (5657). It's harmless, since every caller passes both. Keep HEAD's version or record a Ruling.
12. **Missing icon link:** the spec says `ui/icon.png` is for the title bar and taskbar, but only setup.html and
    settings.html link it. In the probe the window requested `/favicon.ico` and got 404. Add
    `<link rel="icon" href="icon.png">` to home.html and mission.html.
13. **Unrecorded spec deviations:**
    - `openWindow` re-navigates when the window shows another page of ours (4396); the spec says only at about:blank.
      Record it as a Ruling.
    - The real-window test passes the URL twice and accepts 1-2 sockets (3859, 3865). Per the probe, drop the duplicate
      URL and assert `== 1`, as the spec says.
14. **Not RED:** `test_no_script_writes_html_and_no_page_runs_inline_code` (4329-4339) already passes after Task 7. Say
    so in Step 2's expectation.
15. **README:** README.md:97 says "the extension's `config.json`" holds a token; Task 23 doesn't update it. It should
    name the watcher's `config.json`.
