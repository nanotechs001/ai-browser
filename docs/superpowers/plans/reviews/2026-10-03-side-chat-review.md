# Review of the side-chat plan (before it is built)

Date: 2026-10-03. Reviewer: a fresh agent on the most capable model, against the spec and the code at b8de841 (after
the cdp-relay merge, before waves A, B and C). The builder applies every finding below as a `Pre-flight: Ruling:` in the
plan's ledger, after re-reading the code at HEAD (waves A, B and C will have moved more anchors). Numbers are plan
lines unless named.

## Critical

None found. The safety rules hold in the plan's code:
- The chat and the watcher open no CDP connection of their own. `window_of` and `refresh` go through
  `self._watch.cdp`, which is the relay's `LocalClient`. The relay allows `Browser.getWindowForTarget` for the app
  client on any target (cdprelay.py:705-707).
- Page text is set with `textContent` only.
- Hand over, Start here and Take back act only on `isTrusted` clicks, and Enter never hands a tab.
- Take back never connects.
- Nothing answers or hides Brave's question or its bar.
- The Brain has no path to `start_here`, `hand_here` or `take_back_here`.

## Important

**1. Stale anchor: FakePort's dispatch (Task 3, 1033-1050).**
- The relay moved FakePort's replies into `FakePort._reply(ws, message)` (tests/fake_brave.py:112-180). It is not a
  loop; it fills `result, error, before, after` and sends one reply.
- The plan's branch, at loop indentation with `await ws.send(...)` and `continue`, is a SyntaxError there. Every test
  that imports `fake_brave` would fail to collect.
- Fix: write it in `_reply`'s style at 8 spaces, as `Target.getTargetInfo` does (:120-122):
  `window = self.windows.get(target); error, result = (missing, {}) if window is None else (None, {"windowId": window,
  "bounds": {...}})`.

**2. Stale anchor: the drift-test string (Task 0, 364-365).**
- The seams test asserts `"app/tabs.py" in drift`. The merged drift test spells it
  `_sent_methods(SRC / "app" / "tabs.py")` (tests/test_cdprelay.py:128), so the string is never present.
- The guard fails on merged code (the plan says "Expected: PASS") and points the implementer at a rename that doesn't
  exist.
- Fix: assert `'SRC / "app" / "tabs.py"' in drift`, and quote the same form in Task 3 Step 1 (1016-1017).

**3. Task 14 deletes `app/extension/`, but two tests still list it.**
- The plan's own `test_wave_b_names` (398-399) calls `(watcher.APP/"extension").iterdir()`.
- Wave B's `test_ui_static.py::test_the_pages_live_in_app_ui_and_the_watcher_shares_them` expects
  `["panel.css","panel.html","panel.js"]` (app-window.md:1623, and :6629).
- Both raise FileNotFoundError. Task 16 Step 4 (4658) runs `test_ui_static.py`.
- Fix: in Task 14, change both to assert the folder is gone, and add them to Task 14's Files list and Step 4. Also,
  `rmdir … || true` silently leaves the folder if an untracked `.DS_Store` or `__pycache__` remains; remove the folder
  outright after `git rm`.

**4. Take back's cut in the relay is never asserted.**
- `test_take_back_here_from_the_chat` (2421-2446) doesn't check the relay. The cut is cdp-relay's Decision 6
  (server.py:597-598); FakeRelay records it in `cuts` (fake_brave.py:271-272).
- A `_take_back_here` that called `agents.take_back` directly would still pass.
- Fix: assert `brave.relay.cuts == [("a1","U1")]`, and that it is unchanged after the two `not_handed` clicks.

**5. Nothing proves `browser_clients` and tokens stay out of the chat.**
- The chat is a new broadcast subscriber: a plain `hello` joins `_sockets` (server.py:766-769).
- `_clients_changed` broadcasts `browser_clients` to every socket (server.py:567-568), and the snapshot carries it too
  (:1041).
- The relay's guard, `test_browser_disconnect_only_from_our_pages` (tests/test_app_server.py:1352-1372), watches only
  the worker socket. That socket never joins `_sockets` (server.py:728-735), so the guard is vacuous for broadcasts.
- Fix, in the updated `test_watcher_sockets_get_no_target_ids` (1745-1767):
  - set `brave.relay.rows` and call `server._clients_changed()`;
  - assert no `browser_clients` message reaches the chat or the Brain page;
  - assert `server.token_for("a1")` and `server.session_token` never appear.
- Also add `for_watcher({"type":"browser_clients",…}) is None` to `test_what_the_chat_receives` (1315-1342).

**6. The by-hand fallbacks are incomplete (728-736, 4429-4439).**
- The icon fallback ("the shortcut is dropped") changes only the manifest, worker, `sidepanel.js` and setup step 3.
- Tasks 16-17 would still write and test "the watcher's icon or ⌘⇧Y opens the chat" in:
  - `ready_text` (4613-4618);
  - `brave_text` step 3 (4631-4633);
  - AI Home's empty agent list (4639-4654);
  - the README chat section (4740-4743).
- If both the icon and the Brain page's Chat button fail, the chat has no way in, and the plan has no stop rule.
- Fix: list every text and test each fallback changes, and add "both no: stop and ask the user".

## Minor

1. **`_ready_for_hands` (2341-2360) connects `self.links.current`, not the place `_here` already chose (2310-2311).**
   `_here` also never rechecks `_panel_place(ws)` after the wait of up to 65 s. Pass the place in, and recheck hands
   and place after connecting.
2. **A `hand_here` that can't succeed still makes Brave ask.** `closed` and `other_place` are checked only after
   `_ready_for_hands` (2329-2335). Check them before connecting as well, and again after.
3. **Enter before `panel_place` arrives.** `place` is `null` (3379), so `modeFor` returns `"start"` (2910), and Enter
   on the user's own tab starts an agent. The spec's table says Enter does nothing there. Treat `place === null` as
   "no Enter action yet".
4. **To: switches on any owner change.** The `tab_owners` handler (3533-3538) calls `defaultTo` with
   `tabChanged: true` whenever the owner changes, for example after AI Home's Give to. That can retarget a half-typed
   message. Spec Decision 5 switches only on a tab switch, so only `readTab` should pass `tabChanged`.
5. **`descriptor()` (3777-3780) doesn't mirror `tab_desc`'s non-negative integer checks.** The table drops a refused
   message with no answer, so the button stays disabled for 65 s.
6. **A handed tab its agent navigated to `about:blank` or `data:` can't be taken back from the chat.** The relay allows
   those navigations (cdprelay.py:85-89).
   - `stripFor` checks `isWebPage` before the owner (2890), so the strip says "a browser page" and hides Take back.
   - `_here_ok` requires an http(s) URL for `take_back_here` too (1513-1517), although Take back needs only the tab id
     (spec Decision 7).
   - Fix: check `handed` before `isWebPage`, and validate only `id` and `window` for `take_back_here`.
7. **`_here`'s docstring says "Every way out answers hand_result" (2288-2339), but an exception doesn't.** An error in
   `refresh`, `_hand` or `_start_in` leaves the chat waiting. Wrap it with a fallback answer.
8. **`test_the_side_chats_rows` hard-codes 68/32/56 (1310-1312).** It has no "merged +3/+8/+0" fallback like the one
   at 1353-1356. Its "stays no" sweep (1306) also omits the relay's `browser_disconnect` (server.py:62).
9. **Task 14's grep expects "no line" (4110-4113), but it will match two files.**
   - Wave B moves the extension-ID test cases that contain `.ai-browser/app/extension` into
     `tests/test_extension_id.py` (today tests/test_appbrowser.py:245-247).
   - tests/test_app_server.py:1208 also matches.
   - Narrow the pattern to `src/ai_browser/app/extension\|extension/panel\|test_panel import`.
10. **Dot colour:** `panel.css` makes the disconnected dot red (3317); the spec says grey (spec line 318).
11. **Flaky reload:** `test_the_brain_page_has_chat_and_shows_the_promise_once` reloads right after an
    `chrome.storage.local.set` that nobody waits for (4243-4245, 4423-4426). Mark the page once the write resolves,
    and wait for that mark before reloading.
12. **Name drift to note in the ledger:** HEAD's FakeBrave records `connect_calls` (fake_brave.py:298, 336-338). The
    plan's Task 6 says `connect` "records `asked`", which arrives only with wave C's FakeBrave
    (browser-profile-choice.md:3311-3327, together with its `gate`). Keep both.

The reviewer found the other anchors match HEAD or the earlier plans, and spec coverage complete: all 38 spec tests and
the four facts map to tasks.
