# Mission Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AI Browser's **Mission Control**, a 3D room where:
- every agent works at its own station (live screen, ticker, state light, "needs you");
- the Brain is an animated WebGL blob in the middle that reacts to what it is doing and talks back (bubbles, and an
  optional on-device voice);
- everything is actionable through a drawer and a task bar.

**Architecture:**
- **The page:** a new page of AI Browser's extension (`mission.html`) on the same WebSocket as AI Home (`link.js`).
- **Drawing:**
  - CSS 3D transforms draw the room and the stations (`scene.js`);
  - one raw-WebGL canvas draws the Brain (`blob.js`), with a CSS fallback;
  - `voice.js` turns events into updates (bubbles, plus `speechSynthesis` with local voices only).
- **Server additions:**
  - the app server keeps each agent's latest thumbnail (`thumbs`);
  - the BrainService broadcasts `brain_activity`.

**Tech Stack:** plain HTML, CSS and JS (ES modules) in the MV3 extension, with no libraries; WebGL 1; Web Speech
(`speechSynthesis`); Python 3.12 (app server, BrainService); pytest with throwaway headless Chrome and the fake
`claude`.

**Spec:** `docs/superpowers/specs/2026-10-02-mission-control-design.md`

## Global Constraints

- **No libraries and no downloads:** everything is written in the repo. MV3 pages run only packaged scripts.
- **Text is text:** every name, title, action, summary and update is set with `textContent`. Monitor pictures are only
  `data:image/jpeg;base64,` thumbnails from the app.
- **No new manifest permissions,** and no new kind of action: buttons send only messages AI Home already sends.
- **Speech:**
  - only voices with `localService === true`;
  - off by default;
  - the choice is kept in `chrome.storage.local` under `voice`;
  - only summaries and names are spoken, never message bodies or tool inputs.
- **Motion:** `prefers-reduced-motion: reduce` stops idle animations, and the blob moves slowly.
- **No test switches in the pages:** tests change the browser from outside (for example a script added before the
  page loads).
- **No git.** The ledger is `.superpowers/sdd/2026-10-02-mission-control/progress.md`.
- **Approval:** per the user's "do not ask for my input for now", this plan is self-reviewed, not user-reviewed.

## Review Focus

1. **Many agents** (10 or more, finished ones included):
   - stations fill two arcs without overlapping;
   - updates touch only what changed, so the page stays smooth.

   Test: Task 2.
2. **A burst of events** (five agents finish while three needs-you items arrive):
   - one bubble at a time, and the overflow becomes one summary;
   - speech never piles up: the queue drops to the summary and the voice is cancelled.

   Test: Task 5.
3. **No WebGL** (or the context is lost): the CSS orb takes over, with the same states, and nothing breaks. Test:
   Task 4.
4. **Mission Control opened while agents already work, or while a permission already waits:**
   - the snapshot shows "needs you" at once;
   - the screens fill from `thumbs`.

   Test: Tasks 2 and 3.
5. **Hostile names, summaries and titles** (HTML) stay text in stations, the list, bubbles and the drawer, and the
   spoken text is the same plain text. Test: Tasks 2 and 5.

## File map

- **New** in `src/ai_browser/app/extension/`: `mission.html`, `mission.css`, `mission.js`, `scene.js`, `blob.js`,
  `voice.js`.
- **Modified:**
  - `app/server.py` (`thumbs`), `brain/service.py` (`brain_activity`);
  - AI Home: `app/extension/home.html` and `home.js` (the Mission Control button);
  - `README.md`.
- **Tests:**
  - new: `tests/test_mission.py`;
  - modified: `test_app_server.py` and `test_brain_service.py`.

---

### Task 1: The server keeps thumbnails; the Brain says what it is doing

**Files:** modify `src/ai_browser/app/server.py` and `src/ai_browser/brain/service.py`; test
`tests/test_app_server.py` and `tests/test_brain_service.py`.

**Interfaces (produced):**
- **Thumbnails:**
  - each agent's latest thumbnail is kept as `_thumbs[agent_id]["jpeg"]` (base64);
  - `{"type": "thumbs"}` is answered with `{"type": "thumbs", "thumbs": {agent_id: jpeg}}` for live agents only;
  - an `agent_closed` message drops that agent's thumbnail.
- **`BrainService._busy(what)` / `_idle()`** broadcast `{"type": "brain_activity", "busy": true|false, "what": text}`:
  - around each sorted batch: "Sorting N new messages from <label>";
  - around each draft: "Drafting a reply to <sender>";
  - around each Tell: "Thinking about your answer".

  It counts nested work, so busy lasts until the last piece ends.

- [ ] **Step 1: Write the failing tests:**
  - `test_late_pages_get_the_latest_thumbnails`: after `_on_action` with a stubbed `tabs.thumbnail` returning bytes,
    `thumbs` gives that JPEG; after `close`, it is gone;
  - `test_the_brain_says_when_it_is_busy`: a sort gives `brain_activity` busy then idle with the "Sorting 2 new
    messages from Gmail" text; a draft gives "Drafting a reply to Maria".
- [ ] **Step 2: Run** `uv run pytest tests/test_app_server.py tests/test_brain_service.py -q`. Expected: the new tests
  FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same. Expected: PASS.
- [ ] **Step 5: Ledger.**

### Task 2: The room and its stations

**Files:**
- create `mission.html`, `mission.css`, `mission.js` and `scene.js` (in `app/extension/`);
- modify `home.html` and `home.js` (the **Mission Control** button);
- test `tests/test_mission.py`.

**Interfaces:**
- **`scene.js`:** `export function createScene(root, {onSelect}) -> {upsert(agent), remove(id), thumb(id, jpeg),
  turn(dx, dy), zoom(factor), reset(), camera}`:
  - **the room:** a `div.room` under a `div.viewport` (perspective 1400px); a floor grid; `div.stage` for the Brain;
  - **stations:**
    - each is a `button.station[data-id]` (with an `aria-label`), holding `.desk`, `.monitor img`, `.robot`,
      `.nameplate`, `.light` and `.ticker`;
    - the state is in a `data-state` attribute (`working`, `waiting`, `needs_you`, `your_turn`, `stopped`, `failed`);
    - **placement:**
      - an arc of radius 520px for indexes 0–4, 760px for 5–11, and 1000px after that;
      - each arc's angles spread over ±60°;
      - room coordinates are in `data-x` and `data-y`;
  - **camera:** state `{tilt: 55, spin: 0, scale: 1}`, clamped (tilt 35–70, scale 0.6–1.6). It is applied as the
    room's transform and mirrored in `data-tilt`, `data-spin` and `data-scale`.
- **`mission.js`:**
  - `connect({view: "mission"})`;
  - on `snapshot`: stations for every agent, then `thumbs {}` and `brain {}`;
  - `agent` → `scene.upsert`; `agent_closed` → `scene.remove`; `thumb` and `thumbs` → `scene.thumb`;
  - **keys:** arrows turn (15°), `+` and `-` zoom (×1.15), `0` resets;
  - **pointer:** drag turns, the wheel zooms, a double click resets;
  - **the top bar:** counts ("2 working · 1 needs you · 3 done"), **List** (`#list`, a plain list of buttons) and
    **AI Home**.
- **AI Home:** `#mission` button in the header. It opens `mission.html`, or brings an open one to the front.

- [ ] **Step 1: Write the failing tests** (AI Home's `stack` fixture, plus a `mission` fixture that opens
  `mission.html`):
  - `test_every_agent_has_a_station_and_names_stay_text`: three agents, one with a hostile name, give three
    `.station` elements and no `img` except monitors; a station is the same element after an update (a marker
    property set by the test survives); Close removes it;
  - `test_monitors_show_thumbnails_and_late_pages_get_them`: a `thumb` sets the monitor's src; a second Mission
    Control page gets it through `thumbs`;
  - `test_the_camera_turns_and_zooms_within_limits`: keys change `data-tilt`, `data-spin` and `data-scale`, clamped,
    and 0 resets;
  - `test_many_agents_fill_the_arcs_without_overlap`: 11 agents; no two stations closer than 160px in room
    coordinates;
  - `test_ai_home_opens_mission_control`: the button opens one Mission Control tab, even when clicked twice.
- [ ] **Step 2: Run** `uv run pytest tests/test_mission.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest tests/test_mission.py tests/test_home.py -q`. Expected: PASS.
- [ ] **Step 5: Ledger.**

### Task 3: The drawer and the task bar

**Files:** modify `mission.js`, `mission.html` and `mission.css`; test `tests/test_mission.py`.

**Interfaces:**
- **`#drawer`:**
  - **for an agent:**
    - its name, state and status;
    - **Watch**, **Stop**, **Close**, sending the same messages as AI Home;
    - its permission card (`permissionCard`), while `agent.permission` is set;
    - its chat (`createChat` plus an `events` request);
  - **for the Brain:** `mountBrain(drawerBody, link)`;
  - **Escape** or ✕ closes it.
- **`#task`, the bottom task bar:** a textarea, the model, and **Start**, sending `new_task` like AI Home (one request
  at a time).

- [ ] **Step 1: Write the failing tests:**
  - `test_a_waiting_permission_is_answered_from_mission_control`: the fake asks for a tool; the station shows "needs
    you" at once (even for a page opened after the request); a click opens the drawer with the card; **Allow once**
    reaches the fake as an allow;
  - `test_the_task_bar_starts_an_agent`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Ledger.**

### Task 4: The Brain blob

**Files:** create `blob.js`; modify `mission.js`, `mission.html` and `mission.css`; test `tests/test_mission.py`.

**Interfaces:**
- **`createBlob(canvas, orb) -> {setState(state), destroy(), mode}`:**
  - **states:** `idle`, `thinking`, `alert`, `speaking`;
  - **WebGL 1:**
    - a full-canvas quad;
    - the fragment shader ray-marches a sphere displaced by noise over time;
    - uniforms: `u_time`, `u_mix` (state weights, eased toward the target), `u_res`;
  - **without a context, or when it is lost:** the `orb` element (a CSS orb) is shown, and the stage gets
    `data-mode="css"`. The CSS states follow `data-state`;
  - `requestAnimationFrame` drives it, slowed when reduced motion is on.
- **`mission.js`:**
  - **the state:**
    - `thinking` while the last `brain_activity` was busy;
    - else `alert` while any item has `kind === "needs_reply"` or an agent needs you;
    - else `idle`;
    - `speaking` comes from voice (Task 5);
  - **the stage:**
    - `#brain-count` shows "N need you";
    - `#brain-what` shows the activity text;
    - clicking `#brain` opens the Brain drawer.

- [ ] **Step 1: Write the failing tests:**
  - `test_the_blob_follows_the_brain`: `brain_activity` busy gives `data-state="thinking"`; idle with a needs-you item
    gives `alert` and "1 need you"; a click opens the inbox in the drawer;
  - `test_without_webgl_the_orb_takes_over`: before Mission Control loads, the test adds a script (CDP
    `Page.addScriptToEvaluateOnNewDocument`) that makes `getContext("webgl")` return null. The stage shows
    `data-mode="css"` and still follows the states.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Ledger.**

### Task 5: Talking back

**Files:** create `voice.js`; modify `mission.js` and `mission.html`; test `tests/test_mission.py`.

**Interfaces:**
- **`createVoice({bubble, onSpeaking, hold = 5000}) -> {say(text), setEnabled(on) -> Promise<{on, reason}>,
  enabled}`:**
  - **the queue:**
    - one update at a time, `#bubble` shows it with `textContent`;
    - it moves on after `hold` ms, or when its speech ends;
    - more than 3 waiting become one "N more updates: open the Brain", cancelling the speech in progress;
  - **speech:**
    - only voices with `localService` (English first);
    - `setEnabled(true)` with none gives `{on: false, reason: "No voice on this Mac"}`;
    - `onSpeaking(true|false)` drives the blob.
- **`mission.js` updates:**
  - **from the Brain:** a new `brain_item` with `kind === "needs_reply"` gives "<sender> needs your reply:
    <summary>"; a change to `state === "draft_ready"` gives "Your reply to <sender> is ready to check";
  - **from agents:** an `agent` turning `your_turn` gives "<name> is done"; `failed` gives "<name> hit a problem";
    `needs_you` gives "<name> wants to use <server>: <tool>. It's waiting for you";
  - only for changes seen while the page is open, never for the first snapshot.
- **The Voice switch:** `#voice`, a checkbox kept in `chrome.storage.local`.

- [ ] **Step 1: Write the failing tests:**
  - `test_updates_are_written_in_order`: a needs-you item, then an agent finishing, give bubbles with those words in
    order;
  - `test_a_burst_becomes_a_summary` (Review Focus 2): eight updates at once show the first, then a "more updates"
    summary;
  - `test_hostile_text_stays_text_in_bubbles` (Review Focus 5);
  - `test_voice_is_off_by_default_and_needs_a_local_voice`: the switch starts off; turned on in headless Chrome
    without local voices, it reports "No voice on this Mac" and stays off. With a local voice stubbed in before the page
    loads, it turns on and is still on after a reload.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Ledger.**

### Task 6: README, screenshots, final review

- [ ] **Step 1:** README: a "Mission Control" section covering the room, stations, the Brain blob, talking back and
  Voice (on-device voices only), plus the keys.
- [ ] **Step 2: Screenshots** with sample agents (one working with a thumbnail, one needs-you, one done) and the Brain
  alert, checked by eye. Fix the layout where it fails.
- [ ] **Step 3:** the whole suite and the bench. Expected: PASS.
- [ ] **Step 4: Final review.**
  1. A fresh reviewer (opus) reviews against the Global Constraints and the Review Focus.
  2. One fix pass, test-first; minor findings go to the ledger.
  3. The suite and the bench again.
  4. "Mission Control plan: COMPLETE."
- [ ] **Step 5: Restart the user's `ai-browser app`,** so the new extension files load.
