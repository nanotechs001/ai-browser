# The Brain's Chat as a Floating Panel, with History; a Profile Indicator per Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mission Control's talk with the Brain leaves the composer for a floating, non-modal panel (Ask AI opens it,
× or Esc closes it, it drags and stays on screen, it opens itself when the Brain needs the user and a countdown runs
only while it is open), Mission Control's chats are kept (the last 50, New chat, History, Delete), and every agent
shows whether its Brave profile is ready.

**Architecture:**
- **`src/ai_browser/brain/chats.py` (new):** `Chats`, one private file per kept chat in `<home>/brain/chats/<id>.json`,
  for chat ids the app made (`new()`); exchanges come from the Brain's own memory (`Talks.on_add`), cards are kept as
  text and settled once (`BrainService.card_ended`), a reopened chat is restored into the Brain's memory
  (`Talks.restore`, its last `KEEP` exchanges).
- **The app (`app/server.py`):** four app-only messages (`brain_chats`, `brain_chat_open`, `brain_chat_new`,
  `brain_chat_delete`); a kept chat's card recorded from the Brain's answer; `saved_agents` gains `chosen` and
  `connected`, and is sent again when Brave connects or goes, when a profile is learned (`BraveLink.on_place`) and
  when Settings' choice changes.
- **The pages:** `ui/brainchat.js` and `ui/brainchat.css` (new): the panel, holding the hand-off slot (`#handoff`),
  the talk (`#talk`, moved out of the composer) and the mic; the composer keeps Build a Mission and gains the Ask AI
  button; `link.js` counts Mission Control as showing hand-offs only while the panel is open; `talk.js` reveals the
  panel and shows another kept chat (`setTalk`); `ui/profiledot.js` (new) draws the indicator on the Agents page's
  cards, the desks' nameplates and the drawer.

**Tech Stack:**
- Python 3.12, asyncio; Starlette's WebSocket line to the pages; the fake `claude` (`tests/fake_claude.py`) answers the
  Brain's talk (`talk_script`) and logs every one-shot prompt (`oneshots`);
- plain ES modules under the pages' CSP (no inline script or style), `confirm.js`'s modal `<dialog>` for Delete;
- pytest with throwaway headless Chromes for the pages (the `stack` fixture), FakeBrave and FakePort.

**Spec:** `docs/superpowers/specs/2026-10-10-brain-chat-panel-design.md`. This plan argues from it: read both.

**Branch:** build on `brain-chat`, made from `plan-brainchat` (= `main` at 96375f0, the spec and this plan). Every
quoted text was read there; find every place a step changes by the text it quotes, never by a line number.

**One lane.** The tasks run in order: each later task builds on the names the earlier ones made (Interfaces).

## Plan decisions

The user's standing word: decide with the recommended option, and say each one. Where the spec leaves a choice, or
meets the code, this plan rules. Each ruling says why, and what it costs if it is wrong.

1. **The hand-off slot (`#handoff`) moves into the panel**, at its top. *Why:* a countdown runs only while the panel
   is open (spec 3); a card left by the globe would show a countdown that the closed panel holds. *If wrong:* a card
   is seen only with the panel open, and the panel opens itself for every card, so it is one place the user looks.
2. **The mic button moves into the panel's form** (spec 2's "the voice button"). **Space** still talks page-wide:
   with the panel open the words go to the Brain, with it closed they fill Build a Mission's box (today's "outside
   Ask AI"). *Why:* the mic belongs to the talk, and Space keeps dictation for tasks. *If wrong:* moving one button
   back is one markup move.
3. **Its default place is bottom-right, above the composer** (`--composer`, the composer's height, set on `:root` by
   the existing ResizeObserver), 380 px wide and `min(520px, the room above the composer)` tall, so **Start Mission**
   stays in view. Under 900 px: full width at the bottom, 70 % of the height, not dragged. Its z-index (13) is over
   the drawer (10) and the Agents page's panel (12); the confirm dialog is the top layer. *If wrong:* a user who wants
   it lower drags it once; the place is remembered for that window size.
4. **Ask AI toggles the panel.** Opened by Ask AI, the cursor goes into its box; opened by itself (a card, an answer),
   it never takes the focus. Closing it while the focus is inside gives the focus back to Ask AI. *If wrong:* a second
   click that should do nothing closes it.
5. **Esc:** inside the panel it closes the panel; elsewhere Esc closes the drawer first, then the panel. A talk turn's
   Esc (`talk.js`, a window capture) only throws the turn away, as today. *If wrong:* Esc in Build a Mission's box
   closes the panel too.
6. **The composer's modes row:** the **Ask AI** button (`#ask-ai`, `aria-expanded`, `aria-controls="brainchat"`),
   then **Build a Mission** as a label (`#mode-build`, a `span`): a tablist of one tab is no choice. *If wrong:* a
   style change.
7. **Chat ids are the app's:** `c` and 16 hex digits (inside `_TALK_ID`, and a safe file name). `brain_ask` with any
   other well-formed talk id stays an unkept talk (the floating chat's `k…` ids, unchanged). A chat file is written
   at its first exchange, so an empty chat is never listed. `brain_chat_open` or `brain_chat_delete` with an id that
   has no file (unknown, malformed, or empty) answers `{"type": "error", "text": "That chat is gone"}`. *If wrong:* a
   chat the user made but never used can't be "reopened": there was nothing in it.
8. **An exchange is kept exactly as the Brain remembers it** (`Talks.add` calls `Talks.on_add`): a question that
   sounded like a password as `HIDDEN`, a Start or Send press as `(pressed Start)`, an answer that failed not at all.
   Reopened, the log shows those lines. 200 kept: the newest. The title: the first words, one line, 60 at most (an
   ellipsis ends a longer one). *If wrong:* a reopened log shows "You: (pressed Send)" where the live log showed no
   "You:" line.
9. **Cards are kept as `{id, kind, outcome}`**, never their words or buttons. The outcome: the answer to Start, Send
   or Draft it (or a yes); "Cancelled" (`CARD_CANCELLED`) for Cancel or a no; a hand-off's own note ("Sent to agent
   2", "Cancelled: nothing was sent"); still open when the app quits: none, shown as "Not answered". `Talks.restore`
   restores exchanges only, never a proposal, a question or a hand-off. *If wrong:* an outcome reads in the app's
   words, not the spec's three examples.
10. **A kept chat is restored into the Brain's memory before each question** when that talk has nothing in memory
    (after a restart, after `FORGET_AFTER`, or reopened): its last `KEEP` exchanges. *If wrong:* one small file read
    per question to a kept chat.
11. **Each connection asks a New chat while the talk is empty and quiet.** One that answers after the user already
    asked leaves that talk as it is (this page load's, unkept until New chat); a reconnect with words keeps its chat
    (its file exists). *If wrong:* words typed within milliseconds of the page connecting stay unkept.
12. **The panel opens itself** on a `brain_handoff` that is counting or waiting, on a `brain_snapshot` with one open,
    and on any line or card in the talk (`talk.js`'s `reveal`: an answer, a "which agent?" question, a setup card).
13. **The indicator rides `saved_agents`**, which gains `chosen` (Settings' choice) and `connected` (Brave's state is
    "connected"), sent again on Brave's state change, a profile learned (`BraveLink.on_place`, from its place loop) and
    Settings' choice. "Settings' choice" follows the chosen profile; with none chosen (the profile Brave used last) it
    is **Ready** while Brave is connected. *If wrong:* that one case says Ready a moment before Brave's first page.
14. **On a desk the indicator is the dot only**, before the name inside the nameplate (172 px, already clipped); its
    word and hint are the dot's tooltip and join the desk's `aria-label`. Cards and the drawer show the dot and the
    word, with the hint on hover and keyboard focus. Desks show it for saved agents' runs only; every drawer shows it.
    *If wrong:* the word on a desk takes the room its name needs.
15. **Mission Control's log keeps 600 lines** (200 exchanges, two lines each, and a card line each).

## Global Constraints

Copied from the spec. Every task's requirements include these.

**The panel (spec 1–3):**
- "The composer keeps Build a Mission only; its Ask AI tab becomes an **Ask AI** button (same place, same keyboard
  reach) that opens the panel."
- "A floating panel inside the window (`ui/brainchat.js`, `ui/brainchat.css`, markup in `mission.html`): about 380×520,
  bottom-right by default, dragged by its title bar (kept on screen; its place remembered per window size in
  `localStorage`, read and written in try/catch), closed with **×** or Esc. It is **not modal**: the office, the desks
  and the drawers stay clickable behind it. Under 900 px wide it fills the width at the bottom, 70 % of the height. It
  holds everything `#talk` held (log, status, notice, card, form, the voice button and note) — the same elements moved,
  so `talk.js` keeps working on them."
- "The panel opens itself when the Brain needs the user: a hand-off card, a suggestion card, or a "which agent?"
  question for Mission Control's talk. A countdown runs only while the panel is open and the page visible (the panel
  counts as a `HANDOFF_VIEWS` view only while open)."

**Chats (spec 4–6):**
- "Each Mission Control chat is a file `<home>/brain/chats/<id>.json` (0600): id, title (the user's first words, one
  line, at most 60 characters), created and updated times (ISO 8601 UTC), and its exchanges (said, answer, time), at
  most 200 exchanges. Saving a 51st drops the least recently updated. Only the app writes them; pages ask with app-only
  messages. The inbox's per-item talks and the floating ⌥Space chat are not kept (unchanged)."
- "**New chat** starts an empty chat (a new talk id). **History ▾** lists the chats, newest first, title and date; a
  click reopens one; **Delete** asks first (the `confirm.js` dialog) and removes its file. A reopened chat shows its
  whole log; the Brain gets only its last `KEEP` exchanges as context (today's cost). Cards are never re-armed: a past
  hand-off, suggestion or question shows as text ("Sent to agent 2", "Cancelled", "Not answered")."
- "New page messages, app-only in `MESSAGE_RULES` with their copy in `tests/test_watcher_rules.py`: `brain_chats`
  (list), `brain_chat_open` (one chat's log), `brain_chat_new`, `brain_chat_delete`. A chat's id is the talk id the
  page uses; the server keeps talk ids it made and refuses unknown or malformed ones (`_TALK_ID`)."

**The indicator (spec 7):** "the Agents page's cards, each run's desk nameplate and its drawer show a dot and a word:
**Ready** (green: the profile's context is learned), **Open it once** (amber: open a Brave window of that profile),
**Brave not connected** (grey). Hover (and focus) says what to do. "Settings' choice" shows the profile Settings
picks. One-off runs show it in their drawer only. It updates with the agents and Brave messages the pages already get
(within about 30 s of the user opening a window). Colours from `theme.css` tokens only. Nothing opens Brave by itself
(unchanged)."

**Safety rules (spec):**
- Stays: "only the user's own clicks and words reach the Brain from the panel; a hand-off counts down only while the
  user can see it; page and message text is data, set with `textContent`; no inline script or style; the Brain and
  templates never write a chat file; tests never touch the user's real browsers, `~/.ai-browser`, `~/.claude` or port
  8792, and never run the real `claude`."
- New: "chat files hold the user's words and the Brain's answers: 0600, in `<home>/brain/chats/`, never sent anywhere
  but AI Browser's own pages."

**Coordination rules (earlier waves, still binding):**
- text files name `encoding="utf-8"`; every Python module imports on a Windows-like Python (`tests/test_portable.py`);
- every word from a page, a message, a file or an agent is set with `textContent`: no `innerHTML`, `outerHTML`,
  `insertAdjacentHTML` or `document.write` in `app/ui/` (`tests/test_ui_static.py`), no inline script or style, and no
  script that opens a window;
- every CSS variable a sheet uses is defined in `theme.css` or set by a script with `setProperty("--name", …)`
  (`tests/test_theme.py`); no sheet but `theme.css` has a `:root`.

**House rules:**
- UI text: plain words, short sentences.
- Run only the tests a step names: `uv run pytest <path>::<test> -q -p no:randomly` (or the files it names). The whole
  suite runs only in Task 7, with `-m "not docker"`.
- **Never set HOME for a test run: a throwaway Chrome then asks macOS for a keychain (a dialog on the user's screen).**
  The tests keep AI Browser's own folders in pytest's `tmp_path`.
- **Tests never touch the user's real Brave or Chrome, `~/.ai-browser`, `~/.claude`, `~/Downloads` or port 8792, and
  never run the real `claude`.** Pages run in the `stack` fixture's throwaway headless Chrome.
- Commit only the task's files. Each commit message ends with a blank line, then
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

The five inputs the spec implies, but no other test exercises, most likely to bite first. Each has its test in the
task that owns the code.

1. **A chat file that is damaged or hand-edited** (not JSON, wrong types, another chat's id inside). It is skipped or
   read back with only the fields and types `chats.py` writes; History and the panel never break on it.
   - Task 1: `test_only_ids_the_app_made_are_kept_and_a_damaged_file_is_skipped`.
2. **The chat on screen is deleted** (from History, or in another window) while the talk goes on. The page starts a
   New chat, and an answer for the deleted chat never writes its file back.
   - Task 2: the end of `test_the_panels_chats_are_kept_reopened_after_a_restart_and_deleted`; Task 5:
     `test_history_reopens_a_chat_with_its_cards_as_text_and_deletes_it_after_asking`.
3. **The window gets smaller after the panel was dragged.** It stays on screen, and its place comes back at the old
   size.
   - Task 3: `test_a_smaller_window_keeps_the_dragged_chat_on_screen`.
4. **A home whose `brain/chats` can't be written** (a full disk, a read-only folder, a file in its place). The talk
   goes on, unkept; nothing raises into the Brain's answer.
   - Task 1: `test_a_folder_that_cant_be_written_leaves_the_talk_going`.
5. **A "yes" to an old card in a reopened chat** (its proposal id sent along). Nothing runs: the card is text now.
   - Task 2: the "yes" step of `test_the_panels_chats_are_kept_reopened_after_a_restart_and_deleted`.

## File map

**New:**
- `src/ai_browser/brain/chats.py` (Task 1).
- Pages (`src/ai_browser/app/ui/`): `brainchat.js`, `brainchat.css` (Task 3), `profiledot.js` (Task 6).
- Tests: `tests/test_brain_chats.py` (Tasks 1–2, 7), `tests/test_chat_panel.py` (Tasks 3–5).

**Changed:** listed in each task's Files.

---

### Task 1: Kept chats in the Brain (`brain/chats.py`, `Talks.on_add` and `restore`, `card_ended`)

**Files:**
- Create: `src/ai_browser/brain/chats.py`
- Modify: `src/ai_browser/brain/talk.py` (`Talks`)
- Modify: `src/ai_browser/brain/service.py` (`__init__`, `confirm`, `dismiss`, `_show_handoff`)
- Test: `tests/test_brain_chats.py` (new)

**Interfaces:**
- Consumes: `brain/talk.py`'s `Talks`, `KEEP`; `brain/handoffs.py`'s `OPEN`; `syncdir.write_atomic(path, data, mode)`.
- Produces:
  - `brain/chats.py`: `KEEP_CHATS = 50`, `KEEP_EXCHANGES = 200`, `TITLE_LIMIT = 60`, `OUTCOME_LIMIT = 200`,
    `CARD_CANCELLED = "Cancelled"`, `CHAT_ID = re.compile(r"^c[0-9a-f]{16}$")`;
  - `Chats(home, clock=_now)`: `.folder` (`<home>/brain/chats`); `.new() -> str`; `.kept(chat_id) -> bool`;
    `.get(chat_id) -> dict | None` (`{"id", "title", "created", "updated", "exchanges": [{"said", "answer", "time",
    "card"?: {"id", "kind", "outcome": str | None}}]}`); `.list() -> list[dict]` (`{"id", "title", "updated",
    "count"}`, the most recently updated first); `.last(chat_id, count) -> list[tuple[str, str]]`;
    `.add(chat_id, said, answer) -> None`; `.card(chat_id, card: dict) -> None`; `.settle(card_id, outcome) -> None`;
    `.delete(chat_id) -> bool` (may raise `OSError` other than a missing file);
  - `Talks.on_add: Callable[[str, str, str], None]` (called by `Talks.add` with `(talk_id, said, answer)`);
    `Talks.restore(talk_id, exchanges) -> None`;
  - `BrainService.card_ended: Callable[[str, str], None]` (`(card_id, outcome)`: a proposal confirmed or cancelled,
    a hand-off ended).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_brain_chats.py`:

```python
"""The Brain's kept chats (the chat-panel spec, 4-6; brain/chats.py): Mission Control's chat panel keeps the last 50
chats, each a private file of the user's words and the Brain's answers, written only by the app for ids it made; a
reopened chat gives the Brain only its last few exchanges, and its cards come back as text, never re-armed. Unit tests
first, then over the socket against a real app server (the fake claude)."""

import json
from datetime import UTC, datetime, timedelta
from itertools import count

from conftest import file_mode
from test_bridge import EVENTS

START = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
TITLE = "Find the cheapest flight to Manila next month, with one sto…"


def ticking():
    """A clock for Chats: a second later at each call, so "least recently updated" is the test's to say."""
    seconds = count()
    return lambda: (START + timedelta(seconds=next(seconds))).isoformat()


def test_a_kept_chat_is_a_private_file_with_its_title_and_times(tmp_path):
    from ai_browser.brain.chats import Chats

    chats = Chats(tmp_path / "home", clock=ticking())
    chat_id = chats.new()
    assert chats.kept(chat_id) and chats.list() == []  # made: nothing is written until its first exchange
    said = "  Find the cheapest flight\nto Manila next month, with one stop at most and a window seat please  "
    chats.add(chat_id, said, "On it.")
    chats.add(chat_id, "and a hotel", "Noted.")
    path = tmp_path / "home" / "brain" / "chats" / f"{chat_id}.json"
    assert file_mode(path) in (None, 0o600)  # the user's words: only they can read it
    assert chats.get(chat_id) == {
        "id": chat_id, "title": TITLE,  # the first words, one line, 60 characters at most
        "created": "2026-10-10T09:00:00+00:00", "updated": "2026-10-10T09:00:01+00:00",
        "exchanges": [{"said": said, "answer": "On it.", "time": "2026-10-10T09:00:00+00:00"},
                      {"said": "and a hotel", "answer": "Noted.", "time": "2026-10-10T09:00:01+00:00"}]}
    assert chats.list() == [{"id": chat_id, "title": TITLE, "updated": "2026-10-10T09:00:01+00:00", "count": 2}]
    assert chats.last(chat_id, 1) == [("and a hotel", "Noted.")]
    assert chats.delete(chat_id) is True and not path.exists() and chats.list() == []
    assert chats.delete(chat_id) is False


def test_the_last_50_chats_and_200_exchanges_are_kept(tmp_path):
    from ai_browser.brain.chats import KEEP_CHATS, KEEP_EXCHANGES, Chats

    chats = Chats(tmp_path / "home", clock=ticking())
    made = []
    for number in range(KEEP_CHATS):
        made.append(chats.new())
        chats.add(made[-1], f"chat {number}", "Noted.")
    chats.add(made[0], "the first one, again", "Noted.")  # now the most recently updated
    newest = chats.new()
    chats.add(newest, "chat 50", "Noted.")  # a 51st: the least recently updated goes
    listed = [row["id"] for row in chats.list()]
    assert len(listed) == KEEP_CHATS == 50 and made[1] not in listed
    assert listed[:2] == [newest, made[0]]  # newest first
    assert not (tmp_path / "home" / "brain" / "chats" / f"{made[1]}.json").exists()
    for number in range(KEEP_EXCHANGES + 5):
        chats.add(newest, f"question {number}", "Noted.")
    chat = chats.get(newest)
    assert len(chat["exchanges"]) == KEEP_EXCHANGES == 200  # the newest 200
    assert chat["exchanges"][0]["said"] == "question 5" and chat["title"] == "chat 50"  # the first words, still


def test_only_ids_the_app_made_are_kept_and_a_damaged_file_is_skipped(tmp_path):  # Review Focus 1
    from ai_browser.brain.chats import Chats

    home = tmp_path / "home"
    chats = Chats(home)
    folder = home / "brain" / "chats"
    for stranger in ("k1", "../x", "c" + "0" * 16, "C" + "a" * 16, "c" + "a" * 17, None, 7):
        assert chats.kept(stranger) is False and chats.get(stranger) is None and chats.delete(stranger) is False
        chats.add(stranger, "hello", "Noted.")  # a talk the app didn't make: never written
    assert not folder.exists() or list(folder.iterdir()) == []
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ("c" + "1" * 16 + ".json")).write_text("{ not json", encoding="utf-8")
    other = "c" + "2" * 16
    (folder / f"{other}.json").write_text(json.dumps({"id": other, "title": ["a"], "exchanges": [
        "a line", {"said": 7, "answer": "kept", "card": {"id": "p1", "kind": 3}}]}), encoding="utf-8")
    assert [row["id"] for row in chats.list()] == [other]  # the broken one is skipped
    assert chats.get(other)["exchanges"] == [{"said": "", "answer": "kept", "time": ""}]  # only what it should hold
    assert chats.get(other)["title"] == ""


def test_a_folder_that_cant_be_written_leaves_the_talk_going(tmp_path):  # Review Focus 4
    from ai_browser.brain.chats import Chats

    home = tmp_path / "home"
    (home / "brain").mkdir(parents=True)
    (home / "brain" / "chats").write_text("a file where the folder should be", encoding="utf-8")
    chats = Chats(home)
    chat_id = chats.new()
    chats.add(chat_id, "hello", "Noted.")  # no error: the talk goes on, unkept
    chats.card(chat_id, {"id": "p1", "kind": "start_agent"})
    chats.settle("p1", "Cancelled")
    assert chats.kept(chat_id) and chats.get(chat_id) is None and chats.list() == []


def test_a_card_is_kept_as_text_and_ends_once(tmp_path):
    from ai_browser.brain.chats import Chats

    chats = Chats(tmp_path / "home")
    chat_id = chats.new()
    chats.add(chat_id, "check the shop", "I can start an agent.")
    chats.card(chat_id, {"id": "p1", "kind": "start_agent", "task": "check the shop", "expires_in": 120})
    assert chats.get(chat_id)["exchanges"][-1]["card"] == {"id": "p1", "kind": "start_agent", "outcome": None}
    chats.settle("p1", "Started: 1 · check the shop")
    chats.settle("p1", "Cancelled")  # it ended once: a second word changes nothing
    assert chats.get(chat_id)["exchanges"][-1]["card"]["outcome"] == "Started: 1 · check the shop"
    chats.add(chat_id, "tell agent 2 too", "Giving your words to 2 · Research.")
    chats.card(chat_id, {"id": "h1", "kind": "give", "instruction": "tell agent 2 too"})
    again = Chats(tmp_path / "home")  # the app restarted: this run's cards ended with it
    again.settle("h1", "Sent to agent 2")
    assert again.get(chat_id)["exchanges"][-1]["card"] == {"id": "h1", "kind": "give", "outcome": None}


def test_a_restored_talk_gives_the_brain_only_its_last_exchanges():
    from ai_browser.brain.talk import KEEP, Talks

    talks = Talks()
    added = []
    talks.on_add = lambda talk, said, answer: added.append((talk, said, answer))
    talks.restore("c1", [(f"q{number}", f"a{number}") for number in range(10)])
    assert talks.history("c1") == [(f"q{number}", f"a{number}") for number in range(10 - KEEP, 10)]
    talks.restore("c1", [("other", "x")])  # a talk still in memory keeps its own
    assert talks.history("c1")[-1] == ("q9", "a9")
    talks.add("c1", "q10", "a10")
    assert added == [("c1", "q10", "a10")]  # a restore is no exchange: only add is heard


async def test_the_brain_says_how_each_card_ended(tmp_path):
    from ai_browser.brain.chats import CARD_CANCELLED
    from ai_browser.brain.handoffs import CANCELLED
    from test_brain_handoffs import brain_with, row

    brain, agents, _, _ = brain_with(tmp_path, [row()])
    ended = []
    brain.card_ended = lambda card, outcome: ended.append((card, outcome))
    cancelled = brain.talks.propose("c1", "start_agent", task="check the shop", model="sonnet")
    brain.dismiss("c1", cancelled.id)
    brain.dismiss("c1", cancelled.id)  # a second Cancel: nothing more
    started = brain.talks.propose("c1", "start_agent", task="check the cart", model="sonnet")
    answer = await brain.confirm("c1", started.id)
    one = brain.give(row(), "Check the footer too", "you")
    brain.cancel_handoff(one.id)
    two = brain.give(row(), "Check the header too", "you")
    await brain.send_handoff(two.id)
    assert answer["say"].startswith("Started: ")
    assert ended == [(cancelled.id, CARD_CANCELLED), (started.id, answer["say"]), (one.id, CANCELLED),
                     (two.id, "Sent to agent 2")]
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_brain_chats.py -q -p no:randomly`

Expected: FAIL. The `Chats` tests with `ModuleNotFoundError: No module named 'ai_browser.brain.chats'`; the restore
test with `AttributeError: 'Talks' object has no attribute 'restore'`; the card test with the same
`ModuleNotFoundError` (its first import).

- [ ] **Step 3: Write `brain/chats.py`**

Create `src/ai_browser/brain/chats.py`:

```python
"""The Brain's kept chats: Mission Control's chat panel, the last 50 (the chat-panel spec, 4 and 5).

One file per chat, <home>/brain/chats/<id>.json, mode 0600 because it holds the user's words and the Brain's answers:
its id, its title (the user's first words, one line, at most 60 characters), when it was made and last updated (ISO
8601, UTC), and its exchanges, at most 200: said, answer, time, and the card an answer showed, kept as text (its kind
and how it ended, never its words or its buttons). Only the app writes them, and only for chat ids it made itself
(new()); the inbox's talks and the floating chat are never kept. Saving a 51st chat drops the least recently updated.
A file that can't be read, or isn't a chat, is skipped; a folder that can't be written leaves the talk going, unkept."""

from __future__ import annotations

import contextlib
import json
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path

from ..syncdir import write_atomic

KEEP_CHATS = 50  # chats kept: a 51st drops the least recently updated
KEEP_EXCHANGES = 200  # exchanges kept per chat: the newest
TITLE_LIMIT = 60  # characters of a chat's title
OUTCOME_LIMIT = 200  # characters of how a card ended
CARD_CANCELLED = "Cancelled"  # a proposal card's Cancel, or a plain no
CHAT_ID = re.compile(r"^c[0-9a-f]{16}$")  # within the app's talk ids (^[A-Za-z0-9-]{1,40}$), and a safe file name


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _line(text, limit: int) -> str:
    """`text` on one line, at most `limit` characters: an ellipsis ends a longer one."""
    line = " ".join(str(text).split())
    return line if len(line) <= limit else line[:limit - 1].rstrip() + "…"


def _text(value) -> str:
    return value if isinstance(value, str) else ""


def _card(value) -> dict | None:
    if not isinstance(value, dict) or not isinstance(value.get("id"), str) or not isinstance(value.get("kind"), str):
        return None
    outcome = value.get("outcome")
    return {"id": value["id"], "kind": value["kind"], "outcome": outcome if isinstance(outcome, str) else None}


def _clean(data, chat_id: str) -> dict | None:
    """A chat as read from its file, with only the fields and types this module writes; None if it isn't one."""
    if not isinstance(data, dict) or data.get("id") != chat_id or not isinstance(data.get("exchanges"), list):
        return None
    exchanges = []
    for one in data["exchanges"][-KEEP_EXCHANGES:]:
        if not isinstance(one, dict):
            continue
        exchange = {"said": _text(one.get("said")), "answer": _text(one.get("answer")), "time": _text(one.get("time"))}
        card = _card(one.get("card"))
        if card is not None:
            exchange["card"] = card
        exchanges.append(exchange)
    return {"id": chat_id, "title": _line(_text(data.get("title")), TITLE_LIMIT), "created": _text(data.get("created")),
            "updated": _text(data.get("updated")), "exchanges": exchanges}


class Chats:
    def __init__(self, home, clock=_now):
        self.folder = Path(home) / "brain" / "chats"
        self.clock = clock
        self._made: set[str] = set()  # ids this run made that have no file yet (an empty chat is never written)
        self._cards: dict[str, str] = {}  # this run's open cards: id -> its chat (a restart ends them all)

    def _path(self, chat_id: str) -> Path:
        return self.folder / f"{chat_id}.json"

    def new(self) -> str:
        """A new chat's id, for the panel's New chat: kept from its first exchange on."""
        chat_id = f"c{secrets.token_hex(8)}"
        self._made.add(chat_id)
        return chat_id

    def kept(self, chat_id) -> bool:
        """Whether this talk id is a kept chat: one the app made this run, or one with a file."""
        if not isinstance(chat_id, str) or not CHAT_ID.match(chat_id):
            return False
        return chat_id in self._made or self._path(chat_id).is_file()

    def get(self, chat_id) -> dict | None:
        if not isinstance(chat_id, str) or not CHAT_ID.match(chat_id):
            return None
        try:
            data = json.loads(self._path(chat_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return _clean(data, chat_id)

    def list(self) -> list[dict]:
        """The kept chats, the most recently updated first: id, title, when it was last updated, and how many
        exchanges it has (never their words)."""
        try:
            paths = sorted(self.folder.glob("c*.json"))
        except OSError:
            return []
        rows = []
        for path in paths:
            chat = self.get(path.stem)
            if chat is not None:
                rows.append({"id": chat["id"], "title": chat["title"], "updated": chat["updated"],
                             "count": len(chat["exchanges"])})
        return sorted(rows, key=lambda row: row["updated"], reverse=True)

    def last(self, chat_id, count: int) -> list[tuple[str, str]]:
        """Its last `count` exchanges, as the Brain remembers a talk: (said, answer)."""
        chat = self.get(chat_id)
        return [(one["said"], one["answer"]) for one in chat["exchanges"][-count:]] if chat and count > 0 else []

    def add(self, chat_id, said: str, answer: str) -> None:
        """One exchange of a kept chat, as the Brain remembers it (talk.py's Talks.on_add). Any other talk is not
        kept."""
        if not self.kept(chat_id):
            return
        now = self.clock()
        chat = self.get(chat_id) or {"id": chat_id, "title": "", "created": now, "updated": now, "exchanges": []}
        if not chat["title"]:
            chat["title"] = _line(said, TITLE_LIMIT)
        chat["exchanges"] = [*chat["exchanges"],
                             {"said": str(said), "answer": str(answer), "time": now}][-KEEP_EXCHANGES:]
        chat["updated"] = now
        if self._write(chat):
            self._made.discard(chat_id)
            self._trim()

    def card(self, chat_id, card) -> None:
        """The card the last answer showed (a proposal, or a hand-off), kept as text: its id and kind, and later how
        it ended (settle). Its words and buttons are never kept: a reopened chat never re-arms it."""
        chat = self.get(chat_id)
        shown = _card({**card, "outcome": None}) if isinstance(card, dict) else None
        if chat is None or not chat["exchanges"] or shown is None:
            return
        chat["exchanges"][-1]["card"] = shown
        if self._write(chat):
            self._cards[shown["id"]] = chat_id

    def settle(self, card_id, outcome) -> None:
        """How one of this run's cards ended (the Brain's card_ended): kept once, in the chat that showed it."""
        chat_id = self._cards.pop(str(card_id), None)
        chat = self.get(chat_id)
        if chat is None:
            return
        for exchange in reversed(chat["exchanges"]):
            card = exchange.get("card")
            if card is not None and card["id"] == card_id and card["outcome"] is None:
                card["outcome"] = _line(outcome, OUTCOME_LIMIT) or "Done"
                self._write(chat)
                return

    def delete(self, chat_id) -> bool:
        """History's Delete, after the user's yes: its file goes. False when there was none."""
        if not isinstance(chat_id, str) or not CHAT_ID.match(chat_id):
            return False
        self._made.discard(chat_id)
        self._cards = {card: chat for card, chat in self._cards.items() if chat != chat_id}
        try:
            self._path(chat_id).unlink()
        except FileNotFoundError:
            return False
        return True

    def _trim(self) -> None:
        for row in self.list()[KEEP_CHATS:]:  # the least recently updated go
            with contextlib.suppress(OSError):
                self._path(row["id"]).unlink()

    def _write(self, chat: dict) -> bool:
        try:
            write_atomic(self._path(chat["id"]), (json.dumps(chat, ensure_ascii=False) + "\n").encode("utf-8"), 0o600)
        except OSError:  # a full disk, a read-only home: the talk goes on, unkept
            return False
        return True
```

- [ ] **Step 4: Give `Talks` its hook and its restore**

In `src/ai_browser/brain/talk.py`, replace:

```python
from collections import deque
```

with:

```python
from collections import deque
from collections.abc import Callable
```

In `src/ai_browser/brain/talk.py`, replace:

```python
        self._talks: dict[str, Talk] = {}
        self._made = 0
```

with:

```python
        self._talks: dict[str, Talk] = {}
        self._made = 0
        # the app's: each exchange, as remembered here, for Mission Control's kept chats (chats.py; the others ignore it)
        self.on_add: Callable[[str, str, str], None] = lambda talk_id, said, answer: None
```

In `src/ai_browser/brain/talk.py`, replace:

```python
    def add(self, talk_id: str, said: str, answer: str) -> None:
        self._get(talk_id).exchanges.append((said, answer))
```

with:

```python
    def add(self, talk_id: str, said: str, answer: str) -> None:
        self._get(talk_id).exchanges.append((said, answer))
        self.on_add(talk_id, said, answer)

    def restore(self, talk_id: str, exchanges) -> None:
        """A kept chat (chats.py), reopened or back after FORGET_AFTER: its last `keep` exchanges, unless this talk
        still has its own in memory. Exchanges only: never a proposal, a question or a hand-off. No exchange is
        heard (on_add)."""
        talk = self._get(talk_id)
        if not talk.exchanges:
            talk.exchanges.extend((str(said), str(answer)) for said, answer in exchanges)
```

- [ ] **Step 5: Tell how each card ended**

In `src/ai_browser/brain/service.py`, replace:

```python
from .handoffs import (CANCELLED, COUNTDOWN, FROM_BRAIN, HELD, INSTRUCTION_LIMIT, KEPT, NOT_SENT, NOT_STARTED,
```

with:

```python
from .chats import CARD_CANCELLED
from .handoffs import (CANCELLED, COUNTDOWN, FROM_BRAIN, HELD, INSTRUCTION_LIMIT, KEPT, NOT_SENT, NOT_STARTED,
```

In `src/ai_browser/brain/service.py`, replace:

```python
        self.countdown = asyncio.sleep  # how a countdown waits (tests give it their own clock)
        self.clock = time.monotonic
```

with:

```python
        self.countdown = asyncio.sleep  # how a countdown waits (tests give it their own clock)
        self.clock = time.monotonic
        # the app's: how a card of Mission Control's talk ended (a proposal confirmed or cancelled, a hand-off done), for
        # the kept chats (chats.py): (card id, the words it ended with)
        self.card_ended: Callable[[str, str], None] = lambda card, outcome: None
```

In `src/ai_browser/brain/service.py`, replace:

```python
        answer = await self._run_card(talk, card, task, model)
        self.talks.add(talk, said or PRESSED.get(card.kind, ""), answer.get("say", ""))
        return answer
```

with:

```python
        answer = await self._run_card(talk, card, task, model)
        self.talks.add(talk, said or PRESSED.get(card.kind, ""), answer.get("say", ""))
        self.card_ended(card.id, answer.get("say", ""))
        return answer
```

In `src/ai_browser/brain/service.py`, replace:

```python
    def dismiss(self, talk: str, proposal: str) -> None:
        """Cancel on the card, or a plain no."""
        self.talks.take(talk, proposal)
```

with:

```python
    def dismiss(self, talk: str, proposal: str) -> None:
        """Cancel on the card, or a plain no."""
        if self.talks.take(talk, proposal) is not None:
            self.card_ended(proposal, CARD_CANCELLED)
```

In `src/ai_browser/brain/service.py`, replace:

```python
    def _show_handoff(self, handoff: Handoff, notify: bool = False) -> None:
        self.broadcast({"type": "brain_handoff", "handoff": handoff.public(self.clock())})
```

with:

```python
    def _show_handoff(self, handoff: Handoff, notify: bool = False) -> None:
        self.broadcast({"type": "brain_handoff", "handoff": handoff.public(self.clock())})
        if handoff.state not in OPEN and handoff.state != "sending":  # it ended: a kept chat keeps how, as text
            self.card_ended(handoff.id, handoff.note)
```

- [ ] **Step 6: Run them to see them pass, with their neighbours**

Run: `uv run pytest tests/test_brain_chats.py tests/test_brain_talk.py tests/test_brain_handoffs.py -q -p no:randomly`

Expected: PASS (the Chrome tests of `test_brain_handoffs.py` run too: they pass unchanged here).

- [ ] **Step 7: Commit**

```bash
git add src/ai_browser/brain/chats.py src/ai_browser/brain/talk.py src/ai_browser/brain/service.py tests/test_brain_chats.py
git commit -m "feat: the Brain keeps Mission Control's chats: the last 50, private files, cards kept as text

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The chats over the socket: four app-only messages, kept exchanges, restore (security-sensitive: new page messages)

**Files:**
- Modify: `src/ai_browser/app/server.py`
- Test: `tests/test_brain_chats.py`
- Test: `tests/test_watcher_rules.py`

**Interfaces:**
- Consumes: Task 1's `Chats`, `Talks.on_add`, `Talks.restore`, `BrainService.card_ended`; `brain/talk.py`'s `KEEP`.
- Produces:
  - `AppServer.chats: Chats` (`<home>/brain/chats`); `CHAT_MESSAGES`; `CHAT_GONE = "That chat is gone"`;
  - `brain_chat_new` → `{"type": "brain_chat", "request", "chat": {"id", "title": "", "exchanges": []}}`;
    `brain_chat_open` (`id`) → `{"type": "brain_chat", "request", "chat": Chats.get(id)}`;
    `brain_chats` → `{"type": "brain_chats", "chats": Chats.list()}` (to the asking page);
    `brain_chat_delete` (`id`) → every page hears `brain_chats`; an id with no file → `{"type": "error", "text":
    CHAT_GONE, "request"}`;
  - `brain_ask` to a kept chat: the Brain's memory restored first, the exchange and its card kept.

- [ ] **Step 1: Write the failing tests**

In `tests/test_brain_chats.py`, add at the end:

```python


# ---- over the socket: the panel's four messages, app-only (Task 2) ---------------------------------------------------

def test_the_chat_messages_are_app_only_rows():
    from ai_browser.app.server import MESSAGE_RULES, may_send

    for kind in ("brain_chats", "brain_chat_open", "brain_chat_new", "brain_chat_delete"):
        assert MESSAGE_RULES[kind].app and may_send("app", {"type": kind})
        assert not may_send("watcher", {"type": kind}) and not may_send("none", {"type": kind})


async def test_the_panels_chats_are_kept_reopened_after_a_restart_and_deleted(fake_claude, tmp_path):
    from ai_browser.brain.talk import KEEP, START_SAY
    from test_app_server import TALKING, hello, until, with_hearing
    from test_oneshot import oneshots
    from ui_socket import ui_socket

    _, log, _ = fake_claude
    script = {"default": EVENTS, TALKING: [
        {"result": json.dumps({"say": "I can start an agent.", "action": "start_agent"})},
        {"result": json.dumps({"say": "Noted.", "action": "none"})}]}
    server, url, _ = await with_hearing(fake_claude, tmp_path, script)
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            await ws.send(json.dumps({"type": "brain_chat_new", "request": "n1"}))
            made = (await until(ws, lambda m: m["type"] == "brain_chat"))[-1]
            chat_id = made["chat"]["id"]
            assert made == {"type": "brain_chat", "request": "n1",
                            "chat": {"id": chat_id, "title": "", "exchanges": []}}
            await ws.send(json.dumps({"type": "brain_chats"}))
            assert (await until(ws, lambda m: m["type"] == "brain_chats"))[-1]["chats"] == []  # empty: never listed
            for number in range(KEEP + 2):
                await ws.send(json.dumps({"type": "brain_ask", "talk": chat_id, "request": f"t{number}",
                                          "text": f"question {number}"}))
                answer = (await until(ws, lambda m: m["type"] == "brain_answer"
                                      and m["request"] == f"t{number}"))[-1]
                if number == 0:  # a card: Cancel on it
                    assert answer["say"] == START_SAY
                    card = answer["proposal"]["id"]
                    await ws.send(json.dumps({"type": "brain_dismiss", "talk": chat_id, "proposal": card}))
            await ws.send(json.dumps({"type": "brain_ask", "talk": "k1", "request": "f1", "text": "a floating one"}))
            await until(ws, lambda m: m["type"] == "brain_answer" and m["request"] == "f1")  # a talk the app didn't make
            await ws.send(json.dumps({"type": "brain_chats"}))
            [row] = (await until(ws, lambda m: m["type"] == "brain_chats"))[-1]["chats"]
            assert (row["id"], row["title"], row["count"]) == (chat_id, "question 0", KEEP + 2)
    finally:
        await server.stop()
    path = tmp_path / "home" / "brain" / "chats" / f"{chat_id}.json"
    assert file_mode(path) in (None, 0o600) and [one.name for one in path.parent.iterdir()] == [path.name]
    first = json.loads(path.read_text(encoding="utf-8"))["exchanges"][0]
    assert first["card"] == {"id": card, "kind": "start_agent", "outcome": "Cancelled"}  # kept as text
    server, url, _ = await with_hearing(fake_claude, tmp_path, script)  # the app again, on the same home
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            await ws.send(json.dumps({"type": "brain_chat_open", "id": chat_id, "request": "o1"}))
            reopened = (await until(ws, lambda m: m["type"] == "brain_chat"))[-1]
            assert reopened["request"] == "o1"
            assert [one["said"] for one in reopened["chat"]["exchanges"]] == [f"question {n}" for n in range(KEEP + 2)]
            asked = len(oneshots(log))
            await ws.send(json.dumps({"type": "brain_ask", "talk": chat_id, "request": "t9", "text": "and now?"}))
            await until(ws, lambda m: m["type"] == "brain_answer" and m["request"] == "t9")
            prompt = [call["oneshot"] for call in oneshots(log)[asked:] if TALKING in call["oneshot"]][-1]
            assert "- The user: question 1\n" not in prompt  # the Brain gets its last KEEP exchanges only
            assert "- The user: question 2\n" in prompt and f"- The user: question {KEEP + 1}\n" in prompt
            await ws.send(json.dumps({"type": "brain_ask", "talk": chat_id, "request": "t10", "text": "yes",
                                      "proposal": card}))  # Review Focus 5: a yes to the old card runs nothing
            said = (await until(ws, lambda m: m["type"] == "brain_answer" and m["request"] == "t10"))[-1]
            assert "proposal" not in said and "created" not in said and server.agents.agents == {}
            for bad in ("../../x", "k1", "c" + "0" * 16, 7):
                await ws.send(json.dumps({"type": "brain_chat_open", "id": bad, "request": "o2"}))
                gone = (await until(ws, lambda m: m["type"] == "error" and m.get("request") == "o2"))[-1]
                assert gone["text"] == "That chat is gone"
            await ws.send(json.dumps({"type": "brain_chat_delete", "id": chat_id, "request": "d1"}))
            assert (await until(ws, lambda m: m["type"] == "brain_chats"))[-1]["chats"] == []
            assert not path.exists()
            await ws.send(json.dumps({"type": "brain_ask", "talk": chat_id, "request": "t11", "text": "still there?"}))
            await until(ws, lambda m: m["type"] == "brain_answer" and m["request"] == "t11")
            assert not path.exists()  # Review Focus 2: an answer for the deleted chat writes nothing back
    finally:
        await server.stop()
```

In `tests/test_watcher_rules.py`, replace:

```python
    "saved_agents", "saved_agent_save", "saved_agent_delete",  # saved agents: the Agents page, the user's clicks only
```

with:

```python
    "saved_agents", "saved_agent_save", "saved_agent_delete",  # saved agents: the Agents page, the user's clicks only
    "brain_chats", "brain_chat_open", "brain_chat_new", "brain_chat_delete",  # the Brain's chat panel: its kept chats
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_brain_chats.py tests/test_watcher_rules.py -q -p no:randomly`

Expected: FAIL. `test_the_chat_messages_are_app_only_rows` with `KeyError: 'brain_chats'`; the socket test with
`TimeoutError` (the type has no row, so it is dropped); `test_the_message_table_has_exactly_the_written_down_types`
and four of `test_only_ai_browsers_own_pages_send_anything` (the copy names rows the table hasn't got).

- [ ] **Step 3: Write the code**

In `src/ai_browser/app/server.py`, replace:

```python
from ..brain import sites
```

with:

```python
from ..brain import sites
from ..brain.chats import Chats
```

In `src/ai_browser/app/server.py`, replace:

```python
from ..brain.talk import PAGE_TEXT_LIMIT
```

with:

```python
from ..brain.talk import KEEP as TALK_KEEP
from ..brain.talk import PAGE_TEXT_LIMIT
```

In `src/ai_browser/app/server.py`, replace:

```python
TALK_MESSAGES = {"brain_ask", "brain_confirm", "brain_dismiss"}  # the talk with the Brain
```

with:

```python
TALK_MESSAGES = {"brain_ask", "brain_confirm", "brain_dismiss"}  # the talk with the Brain
CHAT_MESSAGES = {"brain_chats", "brain_chat_open", "brain_chat_new", "brain_chat_delete"}  # the panel's kept chats
CHAT_GONE = "That chat is gone"
```

In `src/ai_browser/app/server.py`, replace:

```python
    "brain_ask": APP_ONLY, "brain_confirm": APP_ONLY, "brain_dismiss": APP_ONLY,
```

with:

```python
    "brain_ask": APP_ONLY, "brain_confirm": APP_ONLY, "brain_dismiss": APP_ONLY,
    # the Brain's chat panel (2026-10-10): its kept chats, listed, opened, made and deleted on the user's clicks in our
    # own page. Only the app writes them: never the Brain, a template or a page's text
    "brain_chats": APP_ONLY, "brain_chat_open": APP_ONLY, "brain_chat_new": APP_ONLY, "brain_chat_delete": APP_ONLY,
```

In `src/ai_browser/app/server.py`, replace:

```python
        self.saved = SavedAgents(self.home)  # <home>/agents: the saved agents (the Agents page)
```

with:

```python
        self.saved = SavedAgents(self.home)  # <home>/agents: the saved agents (the Agents page)
        self.chats = Chats(self.home)  # <home>/brain/chats: the Brain's chat panel's kept chats
```

In `src/ai_browser/app/server.py`, replace:

```python
            brain.closed_note = self._brain_closed
```

with:

```python
            brain.closed_note = self._brain_closed
            brain.talks.on_add = self.chats.add  # Mission Control's talk: a kept chat keeps each exchange (ids it made)
            brain.card_ended = self.chats.settle  # and how each of its cards ended
```

In `src/ai_browser/app/server.py`, replace:

```python
        elif kind in TALK_MESSAGES:
            self._talk_command(queue, kind, message, chat=self._views.get(ws) == "chat")
```

with:

```python
        elif kind in TALK_MESSAGES:
            self._talk_command(queue, kind, message, chat=self._views.get(ws) == "chat")
        elif kind in CHAT_MESSAGES:  # AI Browser's own pages only (MESSAGE_RULES)
            self._chat_command(queue, kind, message)
```

In `src/ai_browser/app/server.py`, replace:

```python
    def _talk_command(self, queue: asyncio.Queue, kind: str, message: dict, chat: bool = False) -> None:
```

with:

```python
    def _chat_command(self, queue: asyncio.Queue, kind: str, message: dict) -> None:
        """The Brain's chat panel: New chat (an id the app makes), History's list, a chat reopened, and Delete after
        the user's yes. Only these clicks on our own page reach the kept chats; an id with no file (unknown,
        malformed, or a chat never used) is answered with words and changes nothing."""
        request = message.get("request") if isinstance(message.get("request"), (str, int)) else None
        if kind == "brain_chats":
            queue.put_nowait({"type": "brain_chats", "chats": self.chats.list()})
            return
        if kind == "brain_chat_new":
            queue.put_nowait({"type": "brain_chat", "request": request,
                              "chat": {"id": self.chats.new(), "title": "", "exchanges": []}})
            return
        chat = self.chats.get(message.get("id"))
        if chat is None:
            queue.put_nowait({"type": "error", "text": CHAT_GONE, "request": request})
            return
        if kind == "brain_chat_open":
            queue.put_nowait({"type": "brain_chat", "request": request, "chat": chat})
            return
        try:
            self.chats.delete(chat["id"])
        except OSError as exc:  # a read-only home: nothing changed
            queue.put_nowait({"type": "error", "text": f"Couldn't delete that chat: {exc.strerror or exc}",
                              "request": request})
            return
        self._send_all({"type": "brain_chats", "chats": self.chats.list()})

    def _talk_command(self, queue: asyncio.Queue, kind: str, message: dict, chat: bool = False) -> None:
```

In `src/ai_browser/app/server.py`, replace:

```python
            if text and page is None:  # as before: no page is in it
                self._job(self._answer(queue, talk, request,
```

with:

```python
            if text and page is None:  # as before: no page is in it
                if self.chats.kept(talk):  # a kept chat: the Brain remembers its last few exchanges, as kept
                    self.brain.talks.restore(talk, self.chats.last(talk, TALK_KEEP))
                self._job(self._answer(queue, talk, request,
```

In `src/ai_browser/app/server.py`, replace:

```python
    @staticmethod
    async def _answer(queue: asyncio.Queue, talk: str, request, answering) -> None:
        """The Brain's answer, to the asking page only; an agent it started is `created` there first. If it breaks, the
        page is still answered (in plain words, never the error's own), so it never waits forever."""
        try:
            answer = await answering
        except Exception:  # a newer question's cancel is not an Exception: that answer is never given
            answer = {"say": "", "error": "The Brain couldn't answer"}
        if answer.get("agent"):
```

with:

```python
    async def _answer(self, queue: asyncio.Queue, talk: str, request, answering) -> None:
        """The Brain's answer, to the asking page only; an agent it started is `created` there first. If it breaks, the
        page is still answered (in plain words, never the error's own), so it never waits forever. A kept chat keeps
        the card the answer showed, as text (chats.py)."""
        try:
            answer = await answering
        except Exception:  # a newer question's cancel is not an Exception: that answer is never given
            answer = {"say": "", "error": "The Brain couldn't answer"}
        card = answer.get("proposal") or answer.get("handoff")
        if isinstance(card, dict) and self.chats.kept(talk):  # never re-armed: its kind, and later how it ended
            self.chats.card(talk, card)
        if answer.get("agent"):
```

- [ ] **Step 4: Run them to see them pass, with their neighbours**

Run: `uv run pytest tests/test_brain_chats.py tests/test_watcher_rules.py tests/test_app_server.py tests/test_chat_talk.py tests/test_brain_sources.py tests/test_server_powers.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/server.py tests/test_brain_chats.py tests/test_watcher_rules.py
git commit -m "feat: the Brain's chat panel's messages: list, open, new and delete, app-only; kept chats restored before a question

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The panel: Ask AI opens it, it holds the talk, the mic and the hand-offs, it drags and closes; the composer keeps Build a Mission

**Files:**
- Create: `src/ai_browser/app/ui/brainchat.js`, `src/ai_browser/app/ui/brainchat.css`
- Modify: `src/ai_browser/app/ui/mission.html`, `src/ai_browser/app/ui/mission.js`, `src/ai_browser/app/ui/mission.css`
- Modify: `src/ai_browser/app/ui/composer.js`, `src/ai_browser/app/ui/composer.css`, `src/ai_browser/app/ui/talk.js`
- Test: `tests/test_chat_panel.py` (new)
- Test (moved to the panel, never weakened): `tests/test_talk.py`, `tests/test_delegation_pages.py`,
  `tests/test_mission_look.py`, `tests/test_named_missions.py`, `tests/test_mission_home.py`, `tests/test_office.py`

**Interfaces:**
- Consumes: `talk.js`'s `mountTalk`; `brainui.js`'s `mountHandoffSlot` (unchanged, on `#handoff`); `paste.js`'s
  `takeFiles`, `PICTURES_NOTE`.
- Produces:
  - DOM: `#brainchat` (the panel, `hidden` while closed), `#brainchat-bar`, `#brainchat-title`, `#brainchat-close`;
    inside it `#handoff`, `#talk` (with `#talk-log`, `#talk-status`, `#talk-notice`, `#talk-card`, `#talk-form`,
    `#talk-text`, `#mic`, `#talk-send`); the composer's `#ask-ai` button and `#mode-build` label; `--composer` on
    `:root` (the composer's height);
  - `brainchat.js`: `mountBrainChat({ onToggle = () => {} } = {}) -> { open({ focus = false } = {}), close(),
    isOpen (getter), onMessage(message) }`; `onToggle(open: boolean)` is called when it opens or closes;
  - `talk.js`: `mountTalk({ …, reveal = () => {} })`: `reveal()` runs for each line and each card shown.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_chat_panel.py`:

```python
"""The Brain's chat as a floating panel in Mission Control (the chat-panel spec): Ask AI opens it, × and Esc close it,
the office stays clickable around it, it drags and stays on screen, it opens itself for the Brain's cards and counts
down only while open, and New chat and History keep the last 50 chats. Against a real app server (the fake claude) in
a throwaway headless Chrome; every word stays text."""

import asyncio
import json

import pytest

from ai_browser.chrome import chrome_binary
from test_delegation_pages import hits, size
from test_home import HOSTILE, stack, until  # noqa: F401  (fixtures)
from test_mission import open_mission, open_with, station
from test_talk import ESCAPE, click, front, tap

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
CHAT = "document.getElementById('brainchat')"
ASK = "document.getElementById('ask-ai')"
LOG = "document.getElementById('talk-log')"
LINES = "[...document.querySelectorAll('#talk-log li')].map(line => line.textContent)"
BOX = ("(selector) => { const r = document.querySelector(selector).getBoundingClientRect();"
       " return [Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)]; }")
TITLE = ("(() => { const r = document.getElementById('brainchat-title').getBoundingClientRect();"
         " return [r.left + 10, r.top + r.height / 2]; })()")


async def drag(stack, js, start, end, steps=5):
    """A real drag with the mouse: pressed at `start`, moved to `end` in `steps`, let go there."""
    cdp, session, held = stack["cdp"], js.session, {"button": "left", "buttons": 1}
    await cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": start[0], "y": start[1], "clickCount": 1,
                                                **held}, session_id=session)
    for step in range(1, steps + 1):
        x, y = (start[0] + (end[0] - start[0]) * step / steps, start[1] + (end[1] - start[1]) * step / steps)
        await cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, **held}, session_id=session)
    await cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": end[0], "y": end[1], "clickCount": 1,
                                                **held}, session_id=session)


async def opened(js):
    await js(f"{ASK}.click(); true")
    assert await until(js, f"!{CHAT}.hidden")


# ---- the panel: Ask AI, ×, Esc, not modal, dragged, narrow (Task 3) --------------------------------------------------

@CHROME
async def test_ask_ai_opens_the_brains_chat_and_x_or_esc_closes_it(stack):
    js = await open_with(stack, size=(1440, 900))
    await front(stack, js)
    assert await js(f"{CHAT}.hidden") is True and await js(f"{ASK}.getAttribute('aria-expanded')") == "false"
    assert await js("document.querySelector('#composer #talk, #composer #mic') === null"
                    " && document.getElementById('mode-ask') === null")  # the composer keeps Build a Mission only
    assert await js(f"['talk', 'mic', 'handoff'].every(id => {CHAT}.contains(document.getElementById(id)))")
    await js(f"{ASK}.click(); true")
    assert await until(js, f"!{CHAT}.hidden && document.activeElement.id === 'talk-text'")  # the cursor in its box
    assert await js(f"{ASK}.getAttribute('aria-expanded')") == "true"
    assert await js(f"[{CHAT}.offsetWidth, {CHAT}.offsetHeight]") == [380, 520]
    _, _, right, bottom = await js(f"({BOX})('#brainchat')")
    assert right == 1440 - 16 and bottom <= (await js(f"({BOX})('#composer')"))[1]  # bottom-right, over the composer
    assert await js(hits("document.getElementById('start')"))  # Start Mission stays in view
    await js("document.getElementById('brainchat-close').click(); true")  # ×
    assert await until(js, f"{CHAT}.hidden && document.activeElement === {ASK}")  # the focus back on Ask AI
    assert await js(f"{ASK}.getAttribute('aria-expanded')") == "false"
    await opened(js)
    await tap(stack, js, ESCAPE)  # Esc, the cursor in its box
    assert await until(js, f"{CHAT}.hidden")
    await js(f"{ASK}.click(); document.activeElement.blur(); true")
    await tap(stack, js, ESCAPE)  # Esc anywhere else, with no drawer open
    assert await until(js, f"{CHAT}.hidden")
    await opened(js)
    await js(f"{ASK}.click(); true")  # Ask AI again: it closes
    assert await until(js, f"{CHAT}.hidden")


@CHROME
async def test_the_office_and_the_drawer_stay_clickable_beside_the_brains_chat(stack):
    stack["script"].write_text(json.dumps([{"sleep": 30}]), encoding="utf-8")  # it stays at work
    await stack["server"].agents.create("Fix the footer")
    js = await open_with(stack, size=(1440, 900))
    await front(stack, js)
    assert await until(js, f"{station('a1')} !== null")
    await opened(js)
    await asyncio.sleep(1)  # the desk in its place
    assert await js(hits(station("a1", ".nameplate")))  # nothing covers the desk: the chat isn't modal
    await click(stack, js, '.station[data-id="a1"] .nameplate')  # a real click on it, the chat still open
    assert await until(js, f"{station('a1')}.classList.contains('selected')")
    await js("document.getElementById('current-chat').click(); true")  # its drawer opens beside the chat
    assert await until(js, "!document.getElementById('drawer').hidden")
    assert await js(f"!{CHAT}.hidden") and await js(hits("document.getElementById('drawer-close')"))


@CHROME
async def test_the_brains_chat_drags_by_its_bar_stays_on_screen_and_keeps_its_place(stack):
    js = await open_with(stack, size=(1440, 900))
    await front(stack, js)
    await opened(js)
    left, top, _, _ = await js(f"({BOX})('#brainchat')")
    x, y = await js(TITLE)
    await drag(stack, js, (x, y), (x - 600, y - 100))
    moved = await js(f"({BOX})('#brainchat')")
    assert abs(moved[0] - (left - 600)) <= 1 and abs(moved[1] - (top - 100)) <= 1  # it follows the bar
    x, y = await js(TITLE)
    await drag(stack, js, (x, y), (1, 1))  # past the window's corner: it stops 8 px in
    assert (await js(f"({BOX})('#brainchat')"))[:2] == [8, 8]
    again = await open_with(stack, size=(1440, 900))  # this window size again: the same place
    await opened(again)
    assert (await again(f"({BOX})('#brainchat')"))[:2] == [8, 8]
    other = await open_with(stack, size=(1280, 800))  # another size: the default place
    await opened(other)
    assert (await other(f"({BOX})('#brainchat')"))[2] == 1280 - 16


@CHROME
async def test_a_smaller_window_keeps_the_dragged_chat_on_screen(stack):  # Review Focus 3
    js = await open_with(stack, size=(1440, 900))
    js.cdp = stack["cdp"]
    await front(stack, js)
    await opened(js)
    x, y = await js(TITLE)
    await drag(stack, js, (x, y), (1439, 899))  # into the bottom-right corner
    assert (await js(f"({BOX})('#brainchat')"))[2:] == [1440 - 8, 900 - 8]
    await size(js, 1100, 700)  # the window gets smaller
    assert await until(js, f"(({BOX})('#brainchat'))[2] <= 1100 && (({BOX})('#brainchat'))[3] <= 700")
    await size(js, 1440, 900)  # and back: its place for that size again
    assert await until(js, f"JSON.stringify(({BOX})('#brainchat').slice(2)) === '[{1440 - 8},{900 - 8}]'")


@CHROME
async def test_under_900_px_the_brains_chat_fills_the_width_at_the_bottom(stack):
    js = await open_with(stack, size=(800, 700))
    await opened(js)
    assert await js(f"(() => {{ const r = {CHAT}.getBoundingClientRect();"
                    " return [r.left, r.right, r.bottom, Math.round(r.height)]; })()") == [0, 800, 700, 490]
    assert await js(hits("document.getElementById('talk-text')"))


@CHROME
async def test_a_card_from_the_brain_opens_its_chat_without_taking_the_focus(stack):
    js = await open_mission(stack)
    await js("document.getElementById('task').focus(); true")  # the user is writing a task
    stack["brain"].suggest(f"Research Globex's prices {HOSTILE}", "gmail")  # a suggestion: only ever the user's Start
    card = "document.querySelector('#brainchat #handoff .handoff')"
    assert await until(js, f"!{CHAT}.hidden && {card} !== null")
    assert await js(f"{card}.querySelector('.handoff-words').textContent") == f"Research Globex's prices {HOSTILE}"
    assert await js("document.activeElement.id") == "task"  # the box keeps the cursor
    assert await js("document.querySelectorAll('img[src=x]').length === 0 && document.title !== 'pwned'")
    again = await open_mission(stack)  # a card still open when a page loads opens its chat too
    assert await until(again, f"!{CHAT}.hidden")


@CHROME
async def test_a_card_in_the_talk_opens_the_chat(stack):
    from test_talk import SPACE, mic, open_talk

    js = await open_talk(stack, mic(), hearing="no_model", ask=False)  # the chat closed
    await tap(stack, js, SPACE, " ")  # Space: talking isn't set up yet, and its card says how
    assert await until(js, f"!{CHAT}.hidden && !!document.querySelector('#talk-card .download')")
```

In `tests/test_talk.py`, replace:

```python
async def open_talk(stack, *sources, hearing="ready", ask=True):
    """Mission Control with `sources` run before its scripts, in front, once it knows whether talking is ready, and in
    Ask AI: the talk with the Brain is Ask AI's (in the composer's other modes the mic fills the box), unless not
    ask."""
    js = await open_with(stack, "".join(sources))
    await front(stack, js)
    assert await until(js, f"{PANEL}.dataset.hearing === {json.dumps(hearing)}")
    if ask:
        await js("document.getElementById('mode-ask').click(); true")
    return js
```

with:

```python
async def open_talk(stack, *sources, hearing="ready", ask=True):
    """Mission Control with `sources` run before its scripts, in front, once it knows whether talking is ready, and
    with the Brain's chat open and nothing focused (Space talks to the Brain; while the chat is closed the mic fills
    Build a Mission's box), unless not ask."""
    js = await open_with(stack, "".join(sources))
    await front(stack, js)
    assert await until(js, f"{PANEL}.dataset.hearing === {json.dumps(hearing)}")
    if ask:
        await js("document.getElementById('ask-ai').click(); document.activeElement.blur(); true")
    return js
```

In `tests/test_talk.py`, replace:

```python
    assert await js(f"{PANEL}.hidden") is True  # the talk panel stays hidden until the first turn
```

with:

```python
    assert await js(LOG) == []  # nothing in the talk until the first turn
```

In `tests/test_talk.py`, replace:

```python
    assert await js("document.getElementById('drawer').hidden") is False  # and the drawer stays open
```

with:

```python
    assert await js("document.getElementById('drawer').hidden") is False  # and the drawer stays open
    assert await js("document.getElementById('brainchat').hidden") is False  # and so does the Brain's chat
```

In `tests/test_talk.py`, replace:

```python
async def test_the_mic_fills_the_box_outside_ask_ai(stack):  # the new look: "voice, as today, filling the box"
```

with:

```python
async def test_the_mic_fills_the_box_while_the_brains_chat_is_closed(stack):  # "voice, as today, filling the box"
```

In `tests/test_talk.py`, replace:

```python
    await js("document.getElementById('mode-ask').click(); document.getElementById('task').value = ''; true")
    stack["engine"].answers = ["what is going on"]
    await talk(stack, js)
    assert await eventually(lambda: len(talk_calls(stack)) == 1)  # in Ask AI the Brain hears it, as before
```

with:

```python
    await js("document.getElementById('ask-ai').click(); document.activeElement.blur();"
             " document.getElementById('task').value = ''; true")
    stack["engine"].answers = ["what is going on"]
    await talk(stack, js)
    assert await eventually(lambda: len(talk_calls(stack)) == 1)  # with the chat open the Brain hears it, as before
```

In `tests/test_delegation_pages.py`, replace:

```python
    assert await js("[...document.querySelectorAll('.modes [data-mode]')].map(tab => tab.textContent.trim())") == [
        "Ask AI", "Build a Mission"]  # no Use a Template
```

with:

```python
    assert await js("[...document.querySelectorAll('.modes > :is(button, span)')].map(node => node.textContent.trim())"
                    ".slice(0, 2)") == ["Ask AI", "Build a Mission"]  # no Use a Template
```

In `tests/test_delegation_pages.py`, replace everything from:

```python
# ---- Ask AI's history (spec 3) ---------------------------------------------------------------------------------------
```

up to (not including) the line `@CHROME` that comes before `async def test_the_floating_chat_keeps_six_lines(stack):`,
with:

```python
# ---- the talk, in the Brain's chat (spec 3; the chat-panel spec moved it out of the composer) -----------------------

LOG = "document.getElementById('talk-log')"
PANEL = "document.getElementById('talk')"
CHAT = "document.getElementById('brainchat')"
CENTRE = (f"(() => {{ const r = {LOG}.getBoundingClientRect();"
          " return [r.left + r.width / 2, r.top + r.height / 2]; })()")
ZOOM = "document.querySelector('.room').style.transform"


@CHROME
async def test_the_brains_chat_keeps_this_runs_talk_and_the_wheel_scrolls_it(stack):
    from test_talk import ask_typed, talk_script

    talk_script(stack, {"say": f"Noted {HOSTILE}", "action": "none"})
    js = await open_with(stack, size=(1440, 900))
    await js("document.getElementById('ask-ai').click(); true")
    for number in range(12):  # 24 lines: more than the 6 the talk kept before, and more than the chat shows at once
        await ask_typed(js, f"question {number}")
        assert await until(js, f"{LOG}.querySelectorAll('li.brain').length === {number + 1}", 15)
    assert await js(f"{LOG}.children.length") == 24
    assert await js(f"{LOG}.firstElementChild.textContent") == "You: question 0"
    assert await js(f"{LOG}.querySelector('img') === null && document.title !== 'pwned'")  # text only
    assert await js(f"{LOG}.scrollHeight > {LOG}.clientHeight"
                    f" && Math.abs({LOG}.scrollTop + {LOG}.clientHeight - {LOG}.scrollHeight) <= 1")  # newest in view
    cdp, session = stack["cdp"], js.session
    x, y = await js(CENTRE)
    zoom, bottom = await js(ZOOM), await js(f"{LOG}.scrollTop")
    await cdp.send("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": x, "y": y, "deltaX": 0, "deltaY": -400},
                   session_id=session)
    assert await until(js, f"{LOG}.scrollTop < {bottom}")  # over the chat the wheel scrolls the talk
    assert await js(ZOOM) == zoom  # and the office stays as it was
    left = await js(f"{CHAT}.getBoundingClientRect().left")
    await cdp.send("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": left - 200, "y": y, "deltaX": 0,
                                                "deltaY": -400}, session_id=session)
    assert await until(js, f"{ZOOM} !== {json.dumps(zoom)}")  # beside it, the wheel zooms the office
    await js("document.querySelector('.page-link[data-page=\"history\"]').click(); true")
    assert await until(js, "document.getElementById('composer').hidden")
    assert await js(f"!{CHAT}.hidden && {LOG}.children.length === 24")  # over every page, the talk as it was


@CHROME
async def test_an_empty_talk_takes_no_space_and_a_click_on_it_leaves_space_to_talking(stack):
    from test_talk import SPACE, ask_typed, eventually, mic, mouse, open_talk, talk, talk_script, tap

    talk_script(stack, {"say": "Noted", "action": "none"})
    js = await open_talk(stack, mic())
    await tap(stack, js, SPACE, " ")  # too short: "Hold Space while you talk", and the talk shows no lines
    assert await until(js, "document.getElementById('talk-notice').textContent === 'Hold Space while you talk'")
    assert await js(f"{PANEL}.hidden") is False and await js(f"getComputedStyle({LOG}).display") == "none"
    await ask_typed(js, "hello")
    assert await until(js, f"{LOG}.querySelectorAll('li.brain').length === 1", 15)
    assert await js(f"getComputedStyle({LOG}).display") != "none"
    await mouse(stack, js, "#talk-log", "mousePressed")  # a real click on the talk
    await mouse(stack, js, "#talk-log", "mouseReleased")
    assert await js(f"document.activeElement === {LOG}")
    await talk(stack, js)  # the log has the focus, and Space still talks
    assert await eventually(lambda: len(stack["engine"].heard) == 1)


```

In `tests/test_delegation_pages.py`, replace:

```python
async def test_a_countdown_card_shows_by_the_globe_and_cancel_stops_it(stack):
```

with:

```python
async def test_a_countdown_card_shows_in_the_brains_chat_and_cancel_stops_it(stack):
```

In `tests/test_delegation_pages.py`, replace:

```python
    assert await until(js, hits(cancel))  # wide again: under the view switch, in the middle of the centre, as before
    box = "document.getElementById('handoff').getBoundingClientRect()"
    assert await js(f"[{box}.top, {box}.left + {box}.width / 2, {box}.width]") == [72, (248 + 1440 - 330) / 2, 440]
```

with:

```python
    assert await until(js, hits(cancel))  # wide again: in the Brain's chat, on screen, as before
    assert await js(f"document.getElementById('handoff').closest('#brainchat') === {CHAT}")
```

In `tests/test_delegation_pages.py`, replace:

```python
@CHROME
async def test_several_long_countdowns_never_cover_ask_ais_history(stack):
    from test_talk import talk_script

    row = await working_agent(stack)
    talk_script(stack, {"say": "Noted", "action": "none"})
    js = await open_with(stack, size=(1100, 800))
    await js("document.getElementById('mode-ask').click(); document.getElementById('task').value = 'hello';"
             " document.getElementById('start').click(); true")
    assert await until(js, f"{LOG}.querySelectorAll('li.brain').length === 1", 15)
    words = "Compare every plan. " * 100
    for number in range(3):
        stack["brain"].give(row, f"{number} {words}", "you")
    assert await until(js, f"{IN_SLOT}.length === 3")
    slot = "document.getElementById('handoff')"
    assert await until(js, f"{slot}.getBoundingClientRect().bottom <= {PANEL}.getBoundingClientRect().top")
    assert await js(f"{slot}.scrollHeight > {slot}.clientHeight")  # the rest scrolls, in the slot
    assert await js(hits("document.getElementById('task')"))
```

with:

```python
@CHROME
async def test_several_long_countdowns_scroll_in_the_brains_chat_and_keep_its_box_in_sight(stack):
    row = await working_agent(stack)
    js = await open_with(stack, size=(1100, 800))
    words = "Compare every plan. " * 100
    for number in range(3):
        stack["brain"].give(row, f"{number} {words}", "you")
    assert await until(js, f"{IN_SLOT}.length === 3")
    assert await until(js, f"!{CHAT}.hidden")  # the cards opened it
    slot = "document.getElementById('handoff')"
    assert await js(f"{slot}.scrollHeight > {slot}.clientHeight")  # the rest scrolls, in the slot
    assert await js(hits(f"{in_slot('counting')}.querySelector('.handoff-cancel')"))
    assert await js(hits("document.getElementById('talk-text')"))  # the ask box stays in sight
    assert await js(hits("document.getElementById('task')"))  # and so does the composer
```

In `tests/test_mission_look.py`, replace:

```python
@CHROME
async def test_ask_ai_asks_the_brain_and_shows_its_answer(stack):
    from test_talk import talk_script

    talk_script(stack, {"say": "Two agents are at work.", "action": "none"})
    js = await open_mission(stack)
    await js("document.getElementById('mode-ask').click(); true")
    assert await js("document.getElementById('start-label').textContent") == "Ask"
    hidden = ("['task-web', 'task-think', 'task-model', 'task-effort', 'task-folder', 'attach']"
              ".every(id => document.getElementById(id).hidden)")
    assert await js(hidden)
    await js("document.getElementById('task').value = 'what are my agents doing?';"
             "document.getElementById('start').click(); true")
    log = "[...document.querySelectorAll('#talk-log li')].map(line => line.textContent)"
    assert await until(js, f"{log}.includes('Brain: Two agents are at work.')", 15)
    assert await js(f"{log}.includes('You: what are my agents doing?')")
    assert stack["server"].agents.agents == {}  # Ask AI starts nothing by itself
    assert await js("document.getElementById('task').value") == ""
    assert await js("document.getElementById('talk-form').hidden") is True  # the composer is the talk's box
```

with:

```python
@CHROME
async def test_ask_ai_opens_the_brains_chat_and_shows_its_answer(stack):
    from test_talk import ask_typed, talk_script

    talk_script(stack, {"say": "Two agents are at work.", "action": "none"})
    js = await open_mission(stack)
    await js("document.getElementById('task').value = 'a task I was writing'; true")
    await js("document.getElementById('ask-ai').click(); true")
    assert await until(js, "!document.getElementById('brainchat').hidden")
    assert await js("document.getElementById('start-label').textContent") == "Start Mission"  # Build a Mission stays
    shown = ("['task-web', 'task-think', 'task-model', 'task-effort', 'task-folder', 'attach']"
             ".every(id => !document.getElementById(id).hidden)")
    assert await js(shown)
    await ask_typed(js, "what are my agents doing?")
    log = "[...document.querySelectorAll('#talk-log li')].map(line => line.textContent)"
    assert await until(js, f"{log}.includes('Brain: Two agents are at work.')", 15)
    assert await js(f"{log}.includes('You: what are my agents doing?')")
    assert stack["server"].agents.agents == {}  # Ask AI starts nothing by itself
    assert await js("document.getElementById('talk-text').value") == ""
    assert await js("document.getElementById('task').value") == "a task I was writing"  # the composer's box: as it was
    assert await js("document.getElementById('talk-form').hidden") is False  # the chat has a box of its own
```

In `tests/test_mission_look.py`, replace:

```python
    await js(f"{page_link('history')}.click(); document.getElementById('mode-ask').click(); true")
    await js(f"({KEY})('k', true, false)")  # ⌘K (Ctrl+K)
    assert await js("!document.getElementById('page-dashboard').hidden && document.activeElement.id === 'task'")
    assert await js("document.getElementById('mode-build').getAttribute('aria-selected')") == "true"
```

with:

```python
    await js(f"{page_link('history')}.click(); document.getElementById('ask-ai').click(); true")  # the cursor in the chat
    await js(f"({KEY})('k', true, false)")  # ⌘K (Ctrl+K)
    assert await js("!document.getElementById('page-dashboard').hidden && document.activeElement.id === 'task'")
    assert await js("!document.getElementById('brainchat').hidden")  # Build a Mission's box: the chat stays as it was
```

In `tests/test_mission_look.py`, replace:

```python
@CHROME
async def test_ask_ai_takes_no_picture_and_says_where_pictures_go(stack):
    js = await open_mission(stack)
    for mode in ("ask",):
        await js(f"document.getElementById('mode-{mode}').click(); true")
        await js(f"({PASTE})('#task', {json.dumps(PICTURE)})")
        assert await until(js, f"{NOTE} === {json.dumps(PICTURES_GO)}"), mode
        assert await js("document.getElementById('composer').dataset.mode") == mode  # nothing switched by itself
        assert await js(f"{CHIPS}.length") == 0
        await js("document.getElementById('task-note').textContent = ''; true")
    assert await js(f"({PASTE})('#task', {json.dumps(PICTURE)}, 'A1 B1')") is False  # cells from a spreadsheet come
    await asyncio.sleep(0.5)                                                           # with a picture: they're text
    assert await js(NOTE) == ""
    assert list((stack["home"] / "app" / "uploads").glob("*.part")) == []  # nothing was sent to the app
```

with:

```python
@CHROME
async def test_the_brains_chat_takes_no_picture_and_says_where_pictures_go(stack):
    js = await open_mission(stack)
    talk_note = "document.getElementById('talk-notice').textContent"
    await js("document.getElementById('ask-ai').click(); true")
    await js(f"({PASTE})('#talk-text', {json.dumps(PICTURE)})")
    assert await until(js, f"{talk_note} === {json.dumps(PICTURES_GO)}")
    assert await js("!document.getElementById('brainchat').hidden")  # nothing switched by itself
    assert await js(f"{CHIPS}.length") == 0
    await js("document.getElementById('talk-notice').textContent = ''; true")
    assert await js(f"({PASTE})('#talk-text', {json.dumps(PICTURE)}, 'A1 B1')") is False  # cells from a spreadsheet
    await asyncio.sleep(0.5)                                                             # come with a picture: text
    assert await js(talk_note) == ""
    assert list((stack["home"] / "app" / "uploads").glob("*.part")) == []  # nothing was sent to the app
```

In `tests/test_mission_look.py`, replace:

```python
    await js("document.getElementById('mode-ask').click(); true")
    assert await js(f"({PASTE})('#task', [['report.pdf', 10, 'application/pdf']], 'report.pdf')") is False
    assert await until(js, f"{NOTE} === {json.dumps(PICTURES_GO)}")  # a file in Ask AI: where files go
    await js("document.getElementById('mode-build').click(); true")
```

with:

```python
    await js("document.getElementById('ask-ai').click(); true")
    assert await js(f"({PASTE})('#talk-text', [['report.pdf', 10, 'application/pdf']], 'report.pdf')") is False
    assert await until(js, "document.getElementById('talk-notice').textContent"
                           f" === {json.dumps(PICTURES_GO)}")  # a file in the Brain's chat: where files go
```

In `tests/test_named_missions.py`, replace:

```python
    await js("document.getElementById('mode-ask').click(); true")
    assert await js("document.getElementById('mission-words').hidden")  # Ask AI: no fields
```

with:

```python
    await js("document.getElementById('ask-ai').click(); true")
    assert await js("!document.getElementById('mission-words').hidden")  # the chat leaves Name and What it works on
```

In `tests/test_mission_home.py`, replace:

```python
    await js("document.getElementById('mode-ask').click(); true")
    assert await js("document.getElementById('task-skills').hidden") is True  # Build a Mission's only
```

with:

```python
    await js("document.getElementById('ask-ai').click(); true")  # the Brain's chat opens beside the composer
    assert await js("document.getElementById('task-skills').hidden") is False  # Build a Mission keeps its Skills
```

In `tests/test_office.py`, replace:

```python
    await js("document.getElementById('mode-ask').click()")
    assert await until(js, "document.getElementById('task-agent').offsetParent === null")  # Ask AI: hidden
```

with:

```python
    await js("document.getElementById('ask-ai').click()")
    assert await until(js, "!document.getElementById('brainchat').hidden")
    assert (await js(COMPOSER))[:2] == [mine, True]  # the chat opens beside it: Agent ▾ and the height stay
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_chat_panel.py tests/test_mission_look.py::test_ask_ai_opens_the_brains_chat_and_shows_its_answer -q -p no:randomly`

Expected: FAIL. Every test of `test_chat_panel.py` and the Ask AI test wait in vain for `#brainchat` and `#ask-ai`
(`TypeError: Cannot read properties of null`, or an `until` that times out).

- [ ] **Step 3: Write the panel's markup**

In `src/ai_browser/app/ui/mission.html`, replace:

```html
<link rel="stylesheet" href="composer.css">
```

with:

```html
<link rel="stylesheet" href="composer.css">
<link rel="stylesheet" href="brainchat.css">
```

In `src/ai_browser/app/ui/mission.html`, replace:

```html
    <section id="handoff" class="handoff-slot" hidden aria-live="polite" aria-label="The Brain's hand-offs"></section>
    <section id="page-dashboard" class="page dashboard" aria-label="Dashboard">
```

with:

```html
    <section id="page-dashboard" class="page dashboard" aria-label="Dashboard">
```

In `src/ai_browser/app/ui/mission.html`, replace:

```html
    <section id="composer" class="composer" data-mode="build" aria-label="Give an agent a task">
      <section id="talk" class="talk panel" hidden data-state="idle" aria-label="Ask AI: the Brain's answers">
        <ol id="talk-log" class="talk-log" aria-live="polite" tabindex="0" aria-label="Your talk with the Brain"></ol>
        <div id="talk-status" class="talk-status muted"></div>
        <div id="talk-notice" class="talk-notice" role="status"></div>
        <div id="talk-card" class="talk-card"></div>
        <form id="talk-form" class="talk-form" hidden>
          <input id="talk-text" type="text" maxlength="2000" autocomplete="off" aria-label="Ask the Brain">
        </form>
        <p class="talk-note muted">Your voice stays on this computer. Your words go to Claude, like typed text.</p>
      </section>
      <div class="composer-box">
        <div class="modes" role="tablist" aria-label="What to do">
          <button id="mode-ask" type="button" role="tab" data-mode="ask" data-icon="sparkle"
                  aria-selected="false">Ask AI</button>
          <button id="mode-build" type="button" role="tab" data-mode="build" data-icon="missions"
                  aria-selected="true">Build a Mission</button>
```

with:

```html
    <section id="composer" class="composer" aria-label="Give an agent a task">
      <div class="composer-box">
        <div class="modes" role="group" aria-label="What to do">
          <button id="ask-ai" class="ask-ai" type="button" data-icon="sparkle" aria-controls="brainchat"
                  aria-expanded="false" title="The Brain's chat: it opens over the office">Ask AI</button>
          <span id="mode-build" class="mode-label" data-icon="missions">Build a Mission</span>
```

In `src/ai_browser/app/ui/mission.html`, replace:

```html
            <button id="mic" class="mic" type="button" aria-pressed="false" aria-label="Talk to the Brain"
                    title="Talk to the Brain: hold Space, or hold or click here"><svg viewBox="0 0 24 24"
              aria-hidden="true"><path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11z"/></svg></button>
            <button id="start" class="primary start" type="button" data-icon="play"><span id="start-label">Start
```

with:

```html
            <button id="start" class="primary start" type="button" data-icon="play"><span id="start-label">Start
```

In `src/ai_browser/app/ui/mission.html`, replace:

```html
<script type="module" src="mission.js"></script>
```

with:

```html
<section id="brainchat" class="brainchat panel" hidden role="dialog" aria-modal="false"
         aria-labelledby="brainchat-title">
  <header id="brainchat-bar" class="brainchat-bar">
    <strong id="brainchat-title">Ask AI</strong>
    <button id="brainchat-close" class="ghost" type="button" aria-label="Close the Brain's chat"
            title="Close (Esc)">✕</button>
  </header>
  <section id="handoff" class="handoff-slot" hidden aria-live="polite" aria-label="The Brain's hand-offs"></section>
  <section id="talk" class="talk" data-state="idle" aria-label="Ask AI: the Brain's answers">
    <ol id="talk-log" class="talk-log" aria-live="polite" tabindex="0" aria-label="Your talk with the Brain"></ol>
    <div id="talk-status" class="talk-status muted"></div>
    <div id="talk-notice" class="talk-notice" role="status"></div>
    <div id="talk-card" class="talk-card"></div>
    <form id="talk-form" class="talk-form">
      <input id="talk-text" type="text" maxlength="2000" autocomplete="off" aria-label="Ask the Brain"
             placeholder="Ask anything about your agents, your messages or what to do next…">
      <button id="mic" class="mic" type="button" aria-pressed="false" aria-label="Talk to the Brain"
              title="Talk to the Brain: hold Space, or hold or click here"><svg viewBox="0 0 24 24"
        aria-hidden="true"><path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11z"/></svg></button>
      <button id="talk-send" class="primary" type="submit">Ask</button>
    </form>
    <p class="talk-note muted">Your voice stays on this computer. Your words go to Claude, like typed text.</p>
  </section>
</section>
<script type="module" src="mission.js"></script>
```

- [ ] **Step 4: Write the panel's styles, and take the talk's out of the composer's**

Create `src/ai_browser/app/ui/brainchat.css`:

```css
/* The Brain's chat (brainchat.js; the chat-panel spec): a floating panel over Mission Control, never modal. By default
   bottom-right, above the composer (--composer: its height, set by mission.js) so Start Mission stays in view; dragged
   by its bar to a place of the user's (.placed: left and top from the script, kept on screen). It holds the Brain's
   hand-off cards (brainui.js), then the talk (talk.js). Under 900 px it fills the width at the bottom, 70 % of the
   window's height. */
.brainchat { position: fixed; z-index: 13; right: 16px; bottom: calc(var(--composer, 0px) + 12px); width: 380px;
             height: min(520px, calc(100vh - var(--composer, 0px) - 24px)); max-width: calc(100vw - 16px);
             display: flex; flex-direction: column; overflow: hidden; background: var(--card);
             border-color: var(--line-strong); box-shadow: var(--shadow); }
.brainchat.placed { right: auto; bottom: auto; }
.brainchat-bar { flex: none; display: flex; align-items: center; gap: 6px; padding: 8px 10px; cursor: move;
                 user-select: none; touch-action: none; border-bottom: 1px solid var(--line); }
.brainchat-bar strong { flex: 1; min-width: 0; }
.brainchat-bar button { padding: 2px 8px; font-size: 13px; }
.brainchat > .handoff-slot { flex: none; max-height: 45%; padding: 8px 10px 0; }
.brainchat > .talk { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 6px; padding: 8px 10px 10px; }
.talk-log { flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain; list-style: none; margin: 0;
            padding: 0; display: flex; flex-direction: column; gap: 4px; }
.talk-log:empty { display: none; }
.talk-log:focus-visible { outline: 2px solid var(--accent); }
.talk-log li { white-space: pre-wrap; word-break: break-word; }
.talk-log li.you { color: var(--muted); }
.talk-status:empty, .talk-notice:empty, .talk-card:empty { display: none; }
.talk-notice { color: var(--needs); font-size: 13px; }
.talk-card { flex: none; max-height: 50%; overflow-y: auto; border-top: 1px solid var(--line); padding-top: 8px;
             display: flex; flex-direction: column; gap: 6px; }
.talk-card p { margin: 0; }
.talk-card code { font: 12px var(--mono); background: var(--soft); border-radius: 4px; padding: 0 4px; }
.talk-card textarea { width: 100%; resize: vertical; border: 1px solid var(--line); border-radius: 8px;
                      padding: 6px 8px; background: var(--bg); }
.talk-card progress { width: 100%; }
.talk-card blockquote { margin: 0; padding-left: 8px; border-left: 3px solid var(--line); white-space: pre-wrap; }
.talk-card .talk-state, .talk-card .talk-hint { font-size: 13px; }
.talk-card .row { margin-top: 0; }
.talk-form { flex: none; display: flex; gap: 6px; align-items: center; }
.talk-form input { flex: 1; min-width: 0; padding: 7px 10px; }
.talk-note { margin: 0; font-size: 12px; }
.mic { width: 36px; height: 36px; padding: 0; justify-content: center; flex: none; }
.mic svg { width: 18px; height: 18px; fill: currentColor; }
.mic[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: var(--accent-fg);
                            box-shadow: 0 0 0 3px rgba(79, 141, 253, 0.35); }
@media (max-width: 899px) {
  .brainchat { left: 0; right: 0; bottom: 0; width: auto; max-width: none; height: 70vh;
               border-radius: var(--radius) var(--radius) 0 0; }
  .brainchat-bar { cursor: default; }
}
```

In `src/ai_browser/app/ui/composer.css`, replace:

```css
/* Mission Control's composer (the new look, Decision 9): the modes, the box, the attached files, the pickers (folded
   into ⋯ Options on a narrow window), the mic and the main button; above it, the Brain's answers (Ask AI). */
```

with:

```css
/* Mission Control's composer (the new look, Decision 9): Ask AI (it opens the Brain's chat: brainchat.css), Build a
   Mission, the box, the attached files, the pickers (folded into ⋯ Options on a narrow window) and the main button. */
```

In `src/ai_browser/app/ui/composer.css`, replace:

```css
.modes [data-mode] { gap: 8px; border: 1px solid transparent; background: transparent; padding: 8px 14px;
                     border-radius: 11px; color: var(--text-2); }
.modes [data-mode][aria-selected="true"] { background: linear-gradient(180deg, #10287c, #0b1f66); border-color: #1b41a8;
                                           color: var(--text); box-shadow: 0 0 14px var(--glow); }
```

with:

```css
.modes :is(.ask-ai, .mode-label) { display: inline-flex; align-items: center; gap: 8px; border: 1px solid transparent;
                                   background: transparent; padding: 8px 14px; border-radius: 11px;
                                   color: var(--text-2); }
.modes .ask-ai[aria-expanded="true"] { border-color: var(--line-strong); color: var(--text); } /* its chat is open */
.modes .mode-label { background: linear-gradient(180deg, #10287c, #0b1f66); border-color: #1b41a8; color: var(--text);
                     box-shadow: 0 0 14px var(--glow); } /* the composer's one job */
```

In `src/ai_browser/app/ui/composer.css`, replace:

```css
.mic { width: 36px; height: 36px; padding: 0; justify-content: center; flex: none; }
.mic svg { width: 18px; height: 18px; fill: currentColor; }
.mic[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: var(--accent-fg);
                            box-shadow: 0 0 0 3px rgba(79, 141, 253, 0.35); }
.start { margin-left: auto;
```

with:

```css
.start { margin-left: auto;
```

In `src/ai_browser/app/ui/composer.css`, replace (the whole block, Ask AI's fading history and the talk's styles):

```css
.talk { max-height: 38vh; overflow: auto; padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; }
/* Ask AI's history: over the office, above the box. Idle it is a short strip, only as tall as its lines, so the office
   stays within reach around it: the newest line is at the bottom, older ones fade out towards the top. On hover (or
   keyboard focus inside) it grows upwards from the box, turns solid and scrolls, and the wheel scrolls it, never the
   office. A card (Start, Send) keeps it solid. A mouse click on the log is no keyboard focus: it pins nothing. */
.composer > .talk { position: absolute; left: 24px; right: 24px; bottom: 100%; z-index: 4; background: transparent;
                    border-color: transparent; }
.composer > .talk .talk-log { max-height: 12vh; overflow: hidden; overscroll-behavior: contain; scrollbar-gutter: stable;
                              text-shadow: 0 0 8px var(--bg);
                              -webkit-mask-image: linear-gradient(to top, #000 35%, transparent);
                              mask-image: linear-gradient(to top, #000 35%, transparent); }
.composer > .talk .talk-note { opacity: 0; }
.composer > .talk:is(:hover, :has(:focus-visible)) { background: var(--panel); border-color: var(--line); }
.composer > .talk:has(.talk-card:not(:empty)) { background: var(--panel); border-color: var(--line); }
.composer > .talk:is(:hover, :has(:focus-visible)) .talk-log { max-height: 26vh; overflow-y: auto;
                                                               -webkit-mask-image: none; mask-image: none; }
.composer > .talk:is(:hover, :has(:focus-visible)) .talk-note { opacity: 1; }
.talk-log:empty { display: none; }
.talk-log:focus-visible { outline: 2px solid var(--accent); }
.talk-log { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.talk-log li { white-space: pre-wrap; word-break: break-word; }
.talk-log li.you { color: var(--muted); }
.talk-status:empty, .talk-notice:empty, .talk-card:empty { display: none; }
.talk-notice { color: var(--needs); font-size: 13px; }
.talk-card { border-top: 1px solid var(--line); padding-top: 8px; display: flex; flex-direction: column; gap: 6px; }
.talk-card p { margin: 0; }
.talk-card code { font: 12px var(--mono); background: var(--soft); border-radius: 4px; padding: 0 4px; }
.talk-card textarea { width: 100%; resize: vertical; border: 1px solid var(--line); border-radius: 8px;
                      padding: 6px 8px; background: var(--bg); }
.talk-card progress { width: 100%; }
.talk-card blockquote { margin: 0; padding-left: 8px; border-left: 3px solid var(--line); white-space: pre-wrap; }
.talk-card .talk-state, .talk-card .talk-hint { font-size: 13px; }
.talk-card .row { margin-top: 0; }
.talk-note { margin: 0; font-size: 12px; }
```

with nothing (delete it).

In `src/ai_browser/app/ui/mission.css`, replace:

```css
/* The Brain's hand-offs (brainui.js), under the view switch in the middle of the centre (16 px in from the menu and
   the right column), over whatever it shows and the drawer, never over the composer or Ask AI's history: --composer is
   their height (mission.js). Fixed to the window: a narrow page scrolls, and a countdown stays in reach */
.handoff-slot { position: fixed; top: 72px; left: 264px; right: 346px; margin-inline: auto; z-index: 11;
                max-width: 440px; max-height: calc(100vh - 80px - var(--composer, 0px));
                box-shadow: var(--shadow); border-radius: 10px; }
.page {
```

with:

```css
.page {
```

In `src/ai_browser/app/ui/mission.css`, replace:

```css
          grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); align-items: start; }
  .handoff-slot { right: 16px; }
}
@media (max-width: 899px) {
  .mc { grid-template-columns: 64px minmax(0, 1fr); }
  .handoff-slot { left: 80px; }
```

with:

```css
          grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); align-items: start; }
}
@media (max-width: 899px) {
  .mc { grid-template-columns: 64px minmax(0, 1fr); }
```

- [ ] **Step 5: Write `brainchat.js`**

Create `src/ai_browser/app/ui/brainchat.js`:

```js
// The Brain's chat (the chat-panel spec, 1-3): a floating panel in Mission Control holding the talk (talk.js: its
// log, status, notice, card, box, mic and note) and the Brain's hand-off cards (brainui.js). It is never modal: the
// office, the desks and the drawers stay clickable around it. Ask AI opens (and closes) it, × or Esc closes it, and it
// opens itself when the Brain needs the user: a hand-off or a suggestion, or a line or a card in the talk. Dragged by
// its bar and kept on screen; its place is remembered per window size (localStorage, read and written in try/catch).
// Under 900 px it fills the width at the bottom and isn't dragged. Every word is set as text.
"use strict";

import { PICTURES_NOTE, takeFiles } from "./paste.js";

const NARROW = matchMedia("(max-width: 899px)"); // full width at the bottom: it isn't dragged
const EDGE = 8; // px it keeps from the window's edges
const PLACES = "brainchat-places"; // localStorage: {"<width>x<height>": [left, top]}
const OPEN = ["counting", "waiting"]; // a hand-off that needs the user

function places() {
  try {
    const saved = JSON.parse(localStorage.getItem(PLACES) || "{}");
    return saved && typeof saved === "object" ? saved : {};
  } catch {
    return {}; // storage blocked, or a damaged entry: the default place
  }
}

// onToggle(open): it opened or closed (Mission Control tells the app whether its cards can be seen)
export function mountBrainChat({ onToggle = () => {} } = {}) {
  const $ = (id) => document.getElementById(id);
  const root = $("brainchat");
  const bar = $("brainchat-bar");
  const opener = $("ask-ai");
  let drag = null;

  const size = () => `${innerWidth}x${innerHeight}`;

  function moveTo(left, top) { // on screen, EDGE px in
    const box = root.getBoundingClientRect();
    root.classList.add("placed");
    root.style.left = `${Math.round(Math.min(Math.max(EDGE, left), innerWidth - box.width - EDGE))}px`;
    root.style.top = `${Math.round(Math.min(Math.max(EDGE, top), innerHeight - box.height - EDGE))}px`;
  }

  function place() { // its place for this window size, else the stylesheet's: bottom-right, above the composer
    root.classList.remove("placed");
    root.style.removeProperty("left");
    root.style.removeProperty("top");
    const saved = places()[size()];
    if (root.hidden || NARROW.matches || !Array.isArray(saved)) return;
    moveTo(Number(saved[0]) || 0, Number(saved[1]) || 0);
  }

  function remember() {
    const box = root.getBoundingClientRect();
    try {
      localStorage.setItem(PLACES, JSON.stringify({ ...places(), [size()]: [Math.round(box.left), Math.round(box.top)] }));
    } catch { /* storage blocked: it opens at the default place next time */ }
  }

  function open({ focus = false } = {}) { // Ask AI's click focuses its box; opening by itself never takes the focus
    const was = !root.hidden;
    root.hidden = false;
    opener.setAttribute("aria-expanded", "true");
    if (!was) {
      place();
      onToggle(true);
    }
    if (focus) $("talk-text").focus();
  }

  function close() {
    if (root.hidden) return;
    const inside = root.contains(document.activeElement);
    root.hidden = true;
    opener.setAttribute("aria-expanded", "false");
    onToggle(false);
    if (inside) opener.focus(); // the keys go back where the user opened it
  }

  opener.addEventListener("click", () => (root.hidden ? open({ focus: true }) : close()));
  $("brainchat-close").addEventListener("click", close);
  root.addEventListener("keydown", (event) => { // Esc inside it closes it (a talk turn's Esc is talk.js's, first)
    if (event.key !== "Escape" || event.defaultPrevented) return;
    event.preventDefault();
    event.stopPropagation();
    close();
  });
  takeFiles($("talk-text"), () => { // the Brain's box: text only, and it says where pictures go
    $("talk-notice").textContent = PICTURES_NOTE;
  });
  bar.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || NARROW.matches || event.target.closest("button, summary, details, a, input")) return;
    const box = root.getBoundingClientRect();
    drag = { id: event.pointerId, dx: event.clientX - box.left, dy: event.clientY - box.top };
    bar.setPointerCapture(event.pointerId);
    event.preventDefault(); // no text selection while it moves
  });
  bar.addEventListener("pointermove", (event) => {
    if (drag?.id === event.pointerId) moveTo(event.clientX - drag.dx, event.clientY - drag.dy);
  });
  for (const type of ["pointerup", "pointercancel"]) {
    bar.addEventListener(type, (event) => {
      if (drag?.id !== event.pointerId) return;
      drag = null;
      remember();
    });
  }
  addEventListener("resize", place); // another window size: its place for that size, or the default, on screen
  NARROW.addEventListener("change", place);

  return {
    open,
    close,
    get isOpen() { return !root.hidden; },
    onMessage(message) { // the Brain needs the user: a hand-off or a suggestion opens it, never taking the focus
      if (message.type === "brain_handoff" && OPEN.includes(message.handoff?.state)) open();
      else if (message.type === "brain_snapshot" && (message.handoffs || []).some((one) => OPEN.includes(one?.state))) {
        open();
      }
    },
  };
}
```

- [ ] **Step 6: `talk.js` reveals the panel for each line and card**

In `src/ai_browser/app/ui/talk.js`, replace:

```js
// fill(words): the page may take heard words into its own box instead (Mission Control's composer outside Ask AI):
// true when it did, and the Brain isn't asked. keep: how many lines the log keeps, the newest at the bottom.
export function mountTalk({ panel, micButton, link, voice, onState = () => {}, openAgent = () => {},
                            openBrain = () => {}, model = () => "sonnet", aboutPage = () => null,
                            hintVoice = true, fill = () => false, keep = LOG_LINES }) {
```

with:

```js
// fill(words): the page may take heard words into its own box instead (Mission Control's composer, while the Brain's
// chat is closed): true when it did, and the Brain isn't asked. keep: how many lines the log keeps, the newest at the
// bottom. reveal(): a line or a card is shown (Mission Control opens the Brain's chat for it).
export function mountTalk({ panel, micButton, link, voice, onState = () => {}, openAgent = () => {},
                            openBrain = () => {}, model = () => "sonnet", aboutPage = () => null,
                            hintVoice = true, fill = () => false, keep = LOG_LINES, reveal = () => {} }) {
```

In `src/ai_browser/app/ui/talk.js`, replace:

```js
  function line(who, text) {
    show();
```

with:

```js
  function line(who, text) {
    show();
    reveal();
```

In `src/ai_browser/app/ui/talk.js`, replace:

```js
  function setCard(...nodes) {
    card.replaceChildren(...nodes);
    if (nodes.length) show();
  }
```

with:

```js
  function setCard(...nodes) {
    card.replaceChildren(...nodes);
    if (nodes.length) {
      show();
      reveal();
    }
  }
```

- [ ] **Step 7: The composer keeps Build a Mission**

In `src/ai_browser/app/ui/composer.js`, replace:

```js
// Mission Control's composer (the new look, Decision 9): Ask AI (the Brain: it answers and proposes, and nothing runs
// without the user's Start, Send or a plain yes) and Build a Mission (start an agent). Agent ▾ picks a new agent (Name
// and What it works on) or a saved one: then its own settings apply, and while its run works the task goes to that
// run (the saved-agents spec, 2). Templates are the Agents page's. Under the box: Attach (uploads.js),
// Web ▾, Model ▾ (Model and Effort, behind one face), Account ▾, Folder ▾ (agent powers' picker), Auto-approve in
// its folder (a switch, off again for each new task), Skills (loaded at start; Knowledge's Use in new mission ticks
// one) and Workspace ▾, the mic, and the main button. Enter or Command-Enter (Ctrl+Enter) presses it; Shift+Enter
// makes a new line. A picture pasted into the box, or a file dropped on it (paste.js), is attached as Attach does in
// Build a Mission; Ask AI takes none, and says where pictures go. Narrow windows fold the pickers into ⋯ Options.
// Every word is set as text.
```

with:

```js
// Mission Control's composer (the new look, Decision 9): Build a Mission (start an agent); beside it, Ask AI opens
// the Brain's chat (brainchat.js). Agent ▾ picks a new agent (Name and What it works on) or a saved one: then its own
// settings apply, and while its run works the task goes to that run (the saved-agents spec, 2). Templates are the
// Agents page's. Under the box: Attach (uploads.js), Web ▾, Model ▾ (Model and Effort, behind one face), Account ▾,
// Folder ▾ (agent powers' picker), Auto-approve in its folder (a switch, off again for each new task), Skills (loaded
// at start; Knowledge's Use in new mission ticks one) and Workspace ▾, and the main button. Enter or Command-Enter
// (Ctrl+Enter) presses it; Shift+Enter makes a new line. A picture pasted into the box, or a file dropped on it
// (paste.js), is attached as Attach does. Narrow windows fold the pickers into ⋯ Options. Every word is set as text.
```

In `src/ai_browser/app/ui/composer.js`, replace:

```js
import { PICTURES_NOTE, takeFiles } from "./paste.js";
```

with:

```js
import { takeFiles } from "./paste.js";
```

In `src/ai_browser/app/ui/composer.js`, replace:

```js
const MODES = {
  ask: { label: "Ask", placeholder: "Ask anything about your agents, your messages or what to do next…" },
  build: { label: "Start Mission", placeholder: "Describe what you want to accomplish…" },
};
const WAIT
```

with:

```js
const WAIT
```

In `src/ai_browser/app/ui/composer.js`, replace:

```js
  let mode = "build";
  let pending = null;
```

with:

```js
  let pending = null;
```

In `src/ai_browser/app/ui/composer.js`, replace:

```js
  function savedPicked() { // the saved agent Agent ▾ picked in Build a Mission, if any
    return mode === "build" ? savedAgents.find((row) => row.slug === $("task-agent").value) || null : null;
  }
```

with:

```js
  function savedPicked() { // the saved agent Agent ▾ picked, if any
    return savedAgents.find((row) => row.slug === $("task-agent").value) || null;
  }
```

In `src/ai_browser/app/ui/composer.js`, replace:

```js
  function setMode(next) {
    mode = MODES[next] ? next : "build";
    for (const tab of document.querySelectorAll(".modes [data-mode]")) {
      tab.setAttribute("aria-selected", String(tab.dataset.mode === mode));
    }
    $("composer").dataset.mode = mode;
    const row = savedPicked(); // its run works: the task is a message to it
    const going = row && [...runs.values()].some((run) => run.saved === row.slug && GOING.includes(stateOf(run)));
    $("start-label").textContent = going ? `Send to ${row.name}` : MODES[mode].label;
    if (!note.timer) $("task-note").textContent = hint();
    $("task").placeholder = MODES[mode].placeholder;
    const build = mode === "build";
    const own = build && $("task-agent").value === ""; // a new agent: the pickers are its settings
    for (const id of ["task-web", "task-think", "task-model", "task-effort", "task-folder", "task-auto-switch",
                      "task-skills", "mission-words"]) {
      $(id).hidden = !own;
    }
    $("attach").hidden = !build;
    // Agent ▾ (in the modes' row, beside Name) only once there is a saved agent to pick: alone, "New agent" is no
    // choice
    $("task-agent").hidden = !build || savedAgents.length === 0;
    $("task-account").hidden = !own || rows.length < 2;
    $("task-workspace").hidden = mode === "ask";
    $("attached").hidden = !build || uploads.count() === 0;
  }
```

with:

```js
  function render() { // Agent ▾'s pick: a new agent's pickers, or a saved agent's own settings (and Send to its run)
    const row = savedPicked(); // its run works: the task is a message to it
    const going = row && [...runs.values()].some((run) => run.saved === row.slug && GOING.includes(stateOf(run)));
    $("start-label").textContent = going ? `Send to ${row.name}` : "Start Mission";
    if (!note.timer) $("task-note").textContent = hint();
    const own = $("task-agent").value === ""; // a new agent: the pickers are its settings
    for (const id of ["task-web", "task-think", "task-model", "task-effort", "task-folder", "task-auto-switch",
                      "task-skills", "mission-words"]) {
      $(id).hidden = !own;
    }
    // Agent ▾ (in the modes' row, beside Name) only once there is a saved agent to pick: alone, "New agent" is no
    // choice
    $("task-agent").hidden = savedAgents.length === 0;
    $("task-account").hidden = !own || rows.length < 2;
    $("attached").hidden = uploads.count() === 0;
  }
```

In `src/ai_browser/app/ui/composer.js`, replace:

```js
    const text = $("task").value.trim();
    if (mode === "ask") { // the Brain's talk (talk.js): its answer, and any card, show above the box
      if (!text) {
        note("Write what you want to ask");
        return;
      }
      $("talk-text").value = text;
      $("talk-form").requestSubmit();
      $("task").value = "";
      return;
    }
    if (pending) return;
```

with:

```js
    const text = $("task").value.trim();
    if (pending) return;
```

In `src/ai_browser/app/ui/composer.js`, replace:

```js
  for (const tab of document.querySelectorAll(".modes [data-mode]")) {
    tab.addEventListener("click", () => setMode(tab.dataset.mode));
  }
  $("start").addEventListener("click", run);
```

with:

```js
  $("start").addEventListener("click", run);
```

In `src/ai_browser/app/ui/composer.js`, replace:

```js
  takeFiles($("task"), (pasted) => { // a picture pasted or a file dropped: Build a Mission's, as Attach
    if (mode === "build") uploads.add(pasted);
    else note(PICTURES_NOTE); // Ask AI takes none, and nothing switches by itself
  }, { area: $("task").closest(".box") });
```

with:

```js
  takeFiles($("task"), (pasted) => uploads.add(pasted), // a picture pasted or a file dropped: attached, as Attach does
            { area: $("task").closest(".box") });
```

In `src/ai_browser/app/ui/composer.js`, replace:

```js
    fill(words) { // the mic's words outside Ask AI: into the box, for the user to start (talk.js's `fill`)
      if (mode === "ask") return false;
```

with:

```js
    fill(words) { // the mic's words while the Brain's chat is closed: into the box, for the user to start (talk.js)
```

Then, in `src/ai_browser/app/ui/composer.js`, replace every `setMode(mode)` with `render()` (six places), and every
`setMode("build")` with `render()` (four places). Afterwards `grep -n "setMode\|mode ===\|MODES" src/ai_browser/app/ui/composer.js`
prints nothing.

- [ ] **Step 8: Mission Control mounts the panel**

In `src/ai_browser/app/ui/mission.js`, replace:

```js
import { askError } from "./accountui.js";
import { mountAgentsPage } from "./agentspage.js";
```

with:

```js
import { askError } from "./accountui.js";
import { mountAgentsPage } from "./agentspage.js";
import { mountBrainChat } from "./brainchat.js";
```

In `src/ai_browser/app/ui/mission.js`, replace:

```js
const composer = mountComposer({ link, workspaceOf: () => workspace }); // Ask AI and Build a Mission
parts.push(composer);
```

with:

```js
const composer = mountComposer({ link, workspaceOf: () => workspace }); // Build a Mission, and Ask AI's button
parts.push(composer);
const chat = mountBrainChat(); // the Brain's chat (Ask AI): a floating panel over the office, never modal
parts.push(chat);
```

In `src/ai_browser/app/ui/mission.js`, replace:

```js
// the hand-offs never cover the composer, nor Ask AI's history above it
const reserved = new ResizeObserver(() => $("centre").style.setProperty("--composer",
  `${$("composer").offsetHeight + $("talk").offsetHeight}px`));
reserved.observe($("composer"));
reserved.observe($("talk"));
```

with:

```js
// the Brain's chat opens above the composer, so Start Mission stays in view (brainchat.css)
const reserved = new ResizeObserver(() => document.documentElement.style.setProperty("--composer",
  `${$("composer").offsetHeight}px`));
reserved.observe($("composer"));
```

In `src/ai_browser/app/ui/mission.js`, replace:

```js
  fill: (words) => composer.fill(words), // the mic outside Ask AI fills the box
  keep: 200, // Ask AI's history: this run's talk with the Brain, scrolled on hover (composer.css)
});
```

with:

```js
  fill: (words) => !chat.isOpen && composer.fill(words), // the mic while the Brain's chat is closed fills the box
  keep: 200, // the Brain's chat: this run's talk with the Brain
  reveal: () => chat.open(), // a line or a card in the talk: its chat opens to show it
});
```

In `src/ai_browser/app/ui/mission.js`, replace:

```js
  $("composer").hidden = page !== "dashboard" && page !== "missions";
  $("talk-log").scrollTop = $("talk-log").scrollHeight; // a hidden log loses its place: newest in view again
```

with:

```js
  $("composer").hidden = page !== "dashboard" && page !== "missions";
```

In `src/ai_browser/app/ui/mission.js`, replace:

```js
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && drawer.isOpen) {
    drawer.close();
    return;
  }
```

with:

```js
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && drawer.isOpen) {
    drawer.close();
    return;
  }
  if (event.key === "Escape" && chat.isOpen) { // then the Brain's chat (Esc inside it closes it first: brainchat.js)
    chat.close();
    return;
  }
```

- [ ] **Step 9: Run them to see them pass, with the room-height tests and the other pages that drive the talk**

Run: `uv run pytest tests/test_chat_panel.py tests/test_talk.py tests/test_delegation_pages.py tests/test_mission_look.py tests/test_named_missions.py tests/test_mission_home.py tests/test_chat_page.py tests/test_ui_static.py tests/test_theme.py -q -p no:randomly`

Then the room's height, with the composer changed:

Run: `uv run pytest tests/test_office.py::test_no_step_card_hides_the_name_of_a_desk_behind_it tests/test_office.py::test_agent_pick_sits_in_the_modes_row_and_the_composer_keeps_its_height tests/test_agents_page.py::test_a_long_agent_name_does_not_widen_the_agent_picker_or_add_a_row -q -p no:randomly`

Expected: PASS. (`grep -rn "mode-ask\|data-mode=\"ask\"" src tests` prints nothing.)

- [ ] **Step 10: Commit**

```bash
git add src/ai_browser/app/ui/brainchat.js src/ai_browser/app/ui/brainchat.css src/ai_browser/app/ui/mission.html src/ai_browser/app/ui/mission.js src/ai_browser/app/ui/mission.css src/ai_browser/app/ui/composer.js src/ai_browser/app/ui/composer.css src/ai_browser/app/ui/talk.js tests/test_chat_panel.py tests/test_talk.py tests/test_delegation_pages.py tests/test_mission_look.py tests/test_named_missions.py tests/test_mission_home.py tests/test_office.py
git commit -m "feat: the Brain's chat is a floating panel: Ask AI opens it, it drags, closes with × or Esc, and holds the talk, the mic and the hand-offs

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: A countdown runs only while the panel is open (security-sensitive: a hand-off counts down only while the user can see it)

**Files:**
- Modify: `src/ai_browser/app/ui/link.js`, `src/ai_browser/app/ui/mission.js`
- Test: `tests/test_chat_panel.py`, `tests/test_brain_handoffs.py`, `tests/test_delegation_pages.py`

**Interfaces:**
- Consumes: Task 3's `mountBrainChat({ onToggle })`; the app's `visibility` message and `_seen` (unchanged:
  `HANDOFF_VIEWS` stays `{"mission", "chat"}`, and the page now says it is seen only while the panel is open).
- Produces: `link.js`'s `connect({ view, onMessage, onState, shown = () => true }) -> { send, whenOpen, seen() }`:
  the page counts as seen while it is shown, in front, and `shown()`; `seen()` tells the app at once when that
  changed. Mission Control passes `shown: () => chatOpen`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_chat_panel.py`, add at the end:

```python


# ---- a countdown runs only while the chat is open (Task 4) ------------------------------------------------------------

@CHROME
async def test_a_countdown_runs_only_while_the_brains_chat_is_open(stack):
    from test_app_server import wait_for
    from test_delegation_pages import in_slot, sent_by_the_brain, working_agent

    row = await working_agent(stack)
    brain = stack["brain"]
    js = await open_mission(stack)
    await asyncio.sleep(0.5)
    assert brain.visible() is False  # Mission Control with its chat closed shows no card
    held = brain.give(row, "Compare the annual plans", "you")
    assert held.state == "waiting"  # so nothing counts down: it waits for Send
    assert await until(js, f"!{CHAT}.hidden && {in_slot(handoff_id=held.id)}?.dataset.state === 'waiting'")
    await wait_for(brain.visible)  # the card opened the chat: now a card can be seen
    counting = brain.give(row, "Check the logos too", "you")
    assert counting.state == "counting"
    await js("document.getElementById('brainchat-close').click(); true")  # × holds it
    await wait_for(lambda: counting.state == "waiting")
    await brain.countdown.tick()
    assert sent_by_the_brain(stack) == []  # nothing was sent unseen
```

In `tests/test_brain_handoffs.py`, replace:

```python
from test_tab_menu import connected, pick, shell  # noqa: F401  (fixture)
```

with:

```python
from test_tab_menu import connected, frame, pick, shell  # noqa: F401  (fixture)
```

In `tests/test_brain_handoffs.py`, replace:

```python
@CHROME
async def test_a_page_says_when_it_is_hidden_and_shown(page):
    js, stack = page
    brain = stack["brain"]
    assert await eventually(brain.visible)  # Mission Control, seen: its hello says so
    hide = ("Object.defineProperty(document, 'hidden', { value: %s, configurable: true });"
            "document.dispatchEvent(new Event('visibilitychange')); true")
    await js(hide % "true")  # the window hidden (the desktop app hides it on close)
    assert await eventually(lambda: not brain.visible())
    await js(hide % "false")
    assert await eventually(brain.visible)
```

with:

```python
@CHROME
async def test_a_page_says_when_it_is_hidden_and_shown(page):
    js, stack = page
    brain = stack["brain"]
    await asyncio.sleep(0.5)
    assert brain.visible() is False  # Mission Control with the Brain's chat closed: no card can be seen there
    await js("document.getElementById('ask-ai').click(); true")
    assert await eventually(brain.visible)  # the chat open: its cards can be seen
    hide = ("Object.defineProperty(document, 'hidden', { value: %s, configurable: true });"
            "document.dispatchEvent(new Event('visibilitychange')); true")
    await js(hide % "true")  # the window hidden (the desktop app hides it on close)
    assert await eventually(lambda: not brain.visible())
    await js(hide % "false")
    assert await eventually(brain.visible)
    await js("document.getElementById('brainchat-close').click(); true")  # ×: the chat closed
    assert await eventually(lambda: not brain.visible())
```

In `tests/test_brain_handoffs.py`, replace:

```python
    js, stack = shell  # the window's tab menu (app.js), Mission Control's tab in front
    brain = stack["brain"]
    brain.countdown = Clock()
    assert await eventually(brain.visible)  # Mission Control's tab, shown: the tab menu says so as its page loads
```

with:

```python
    js, stack = shell  # the window's tab menu (app.js), Mission Control's tab in front
    brain = stack["brain"]
    brain.countdown = Clock()
    assert await page_until(js, connected("/mission"))
    await js(f"{frame('/mission')}.document.getElementById('ask-ai').click(); true")  # its Brain's chat, open
    assert await eventually(brain.visible)  # Mission Control's tab, shown: the tab menu says so as its page loads
```

In `tests/test_delegation_pages.py`, replace:

```python
def colour(token):
```

with:

```python
async def open_panel(stack, js):
    """The Brain's chat open (Ask AI, unless a card opened it already): only then does Mission Control show hand-offs,
    and only then may the user's words count down (the chat-panel spec, 3)."""
    from test_app_server import wait_for

    await js("document.getElementById('brainchat').hidden && document.getElementById('ask-ai').click(); true")
    await wait_for(stack["brain"].visible)


def colour(token):
```

In `tests/test_delegation_pages.py`, replace:

```python
    js = await open_mission(stack)
    handoff = stack["brain"].give(row, f"Compare the annual plans {HOSTILE}", "you")
```

with:

```python
    js = await open_mission(stack)
    await open_panel(stack, js)
    handoff = stack["brain"].give(row, f"Compare the annual plans {HOSTILE}", "you")
```

In `tests/test_delegation_pages.py`, replace:

```python
    js = await open_with(stack, size=(1440, 800))
    words = "Compare every plan. " * 100  # 2000 characters: the most a hand-off holds
```

with:

```python
    js = await open_with(stack, size=(1440, 800))
    await open_panel(stack, js)
    words = "Compare every plan. " * 100  # 2000 characters: the most a hand-off holds
```

In `tests/test_delegation_pages.py`, replace:

```python
    js = await open_mission(stack)
    first = stack["brain"].give(row, "Compare the annual plans", "you")
```

with:

```python
    js = await open_mission(stack)
    await open_panel(stack, js)
    first = stack["brain"].give(row, "Compare the annual plans", "you")
```

In `tests/test_delegation_pages.py`, replace:

```python
    js = await open_with(stack, size=(1100, 800))
    handoff = stack["brain"].give(row, "Compare the annual plans", "you")
```

with:

```python
    js = await open_with(stack, size=(1100, 800))
    await open_panel(stack, js)
    handoff = stack["brain"].give(row, "Compare the annual plans", "you")
```

In `tests/test_delegation_pages.py`, replace:

```python
    js = await open_with(stack, size=(1100, 800))
    words = "Compare every plan. " * 100
    for number in range(3):
```

with:

```python
    js = await open_with(stack, size=(1100, 800))
    await open_panel(stack, js)
    words = "Compare every plan. " * 100
    for number in range(3):
```

In `tests/test_delegation_pages.py`, replace:

```python
    js = await open_mission(stack)
    stack["brain"].give(row, "Compare the annual plans", "you")
```

with:

```python
    js = await open_mission(stack)
    await open_panel(stack, js)
    stack["brain"].give(row, "Compare the annual plans", "you")
```

In `tests/test_delegation_pages.py`, replace:

```python
    stack["brain"].countdown = Clock()
    stack["brain"].give(row, "Compare the annual plans", "you")  # the slot shows a countdown, in reach
```

with:

```python
    stack["brain"].countdown = Clock()
    await open_panel(stack, js)  # (the email's card opened it already)
    stack["brain"].give(row, "Compare the annual plans", "you")  # the slot shows a countdown, in reach
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_chat_panel.py::test_a_countdown_runs_only_while_the_brains_chat_is_open tests/test_brain_handoffs.py::test_a_page_says_when_it_is_hidden_and_shown -q -p no:randomly`

Expected: FAIL. Both at `assert brain.visible() is False`: Mission Control still counts as seen with its chat closed.

- [ ] **Step 3: Write the code**

In `src/ai_browser/app/ui/link.js`, replace:

```js
export function connect({ view, onMessage = () => {}, onState = () => {} }) {
```

with:

```js
// shown(): whether the page shows the Brain's hand-off cards now (Mission Control: only while the Brain's chat is
// open); seen() tells the app at once when that changed
export function connect({ view, onMessage = () => {}, onState = () => {}, shown = () => true }) {
```

In `src/ai_browser/app/ui/link.js`, replace:

```js
  const seen = () => !document.hidden && inFront;
```

with:

```js
  const seen = () => !document.hidden && inFront && shown();
```

In `src/ai_browser/app/ui/link.js`, replace:

```js
    whenOpen() {
```

with:

```js
    seen: report, // the page's own change (Mission Control's chat opened or closed): told at once
    whenOpen() {
```

In `src/ai_browser/app/ui/mission.js`, replace:

```js
const link = connect({ view: "mission", onMessage: handle, onState: setStatus });
```

with:

```js
let chatOpen = false; // the Brain's chat: only while it is open does Mission Control show hand-offs (link.js's shown)
const link = connect({ view: "mission", onMessage: handle, onState: setStatus, shown: () => chatOpen });
```

In `src/ai_browser/app/ui/mission.js`, replace:

```js
const chat = mountBrainChat(); // the Brain's chat (Ask AI): a floating panel over the office, never modal
```

with:

```js
const chat = mountBrainChat({ // the Brain's chat (Ask AI): a floating panel over the office, never modal
  onToggle: (open) => { // opened or closed: the app hears at once whether its cards can be seen (a countdown holds)
    chatOpen = open;
    link.seen();
  },
});
```

- [ ] **Step 4: Run them to see them pass, with every page that counts down or shows a card**

Run: `uv run pytest tests/test_chat_panel.py tests/test_brain_handoffs.py tests/test_delegation_pages.py tests/test_tab_menu.py tests/test_talk.py tests/test_chat_page.py -q -p no:randomly`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/ui/link.js src/ai_browser/app/ui/mission.js tests/test_chat_panel.py tests/test_brain_handoffs.py tests/test_delegation_pages.py
git commit -m "feat: a hand-off counts down in Mission Control only while the Brain's chat is open; closing it holds the countdown

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: New chat, History ▾ and Delete in the panel

**Files:**
- Modify: `src/ai_browser/app/ui/mission.html`, `src/ai_browser/app/ui/brainchat.js`, `src/ai_browser/app/ui/brainchat.css`
- Modify: `src/ai_browser/app/ui/talk.js`, `src/ai_browser/app/ui/mission.js`
- Test: `tests/test_chat_panel.py`

**Interfaces:**
- Consumes: Task 2's messages (`brain_chat_new`, `brain_chat_open`, `brain_chats`, `brain_chat_delete`, the `brain_chat`
  answer, the `"That chat is gone"` error); Task 3's `mountBrainChat`; `confirm.js`'s `confirmAction({ title, lines,
  yes })`.
- Produces:
  - `talk.js`: the returned object gains `setTalk(id: string, exchanges: Array<{said, answer, time, card?}>)` (the
    talk becomes that chat: its log redrawn, any open card and question closed) and `fresh` (a getter: nothing asked,
    nothing waiting, an empty log);
  - `brainchat.js`: `mountBrainChat({ link, talk = () => null, onToggle = () => {} })`; `#brainchat[data-chat]` is
    the kept chat shown; requests are named `chat-<n>`;
  - DOM: `#chat-new`, `#chat-history` (a `<details>`), `#chat-list` (rows `.chat-row[data-id]` with `.open` (`.title`,
    `.when`) and `.delete`; `.empty` when there are none), and in the log `li.past` for a kept card.

- [ ] **Step 1: Write the failing tests**

In `tests/test_chat_panel.py`, add at the end:

```python


# ---- New chat, History ▾ and Delete (Task 5) --------------------------------------------------------------------------

MADE = f"/^c[0-9a-f]{{16}}$/.test({CHAT}.dataset.chat || '')"  # the app made the chat's id


@CHROME
async def test_new_chat_starts_empty_and_history_lists_the_chats_newest_first(stack):
    from test_talk import ask_typed, talk_calls, talk_script

    talk_script(stack, {"say": "Noted.", "action": "none"})
    js = await open_mission(stack)
    assert await until(js, MADE)
    await opened(js)
    await ask_typed(js, "first question")
    assert await until(js, f"{LOG}.querySelectorAll('li.brain').length === 1", 15)
    first = await js(f"{CHAT}.dataset.chat")
    await js("document.getElementById('chat-new').click(); true")
    assert await until(js, f"{CHAT}.dataset.chat !== {json.dumps(first)} && {LOG}.children.length === 0")
    await ask_typed(js, f"second {HOSTILE}")
    assert await until(js, f"{LOG}.querySelectorAll('li.brain').length === 1", 15)
    assert "first question" not in talk_calls(stack)[-1]  # a new chat: the Brain starts afresh
    await js("document.querySelector('#chat-history summary').click(); true")
    titles = "[...document.querySelectorAll('#chat-list .chat-row .title')].map(node => node.textContent)"
    assert await until(js, f"{titles}.length === 2")
    assert await js(titles) == [f"second {HOSTILE}", "first question"]  # newest first, as text
    current = "document.querySelector('#chat-list .chat-row[aria-current=\"true\"] .title').textContent"
    assert await js(current) == f"second {HOSTILE}"
    assert await js("document.querySelector('#chat-list .chat-row .when').textContent") != ""  # and its date
    assert await js("document.querySelectorAll('img[src=x]').length === 0 && document.title !== 'pwned'")


@CHROME
async def test_history_reopens_a_chat_with_its_cards_as_text_and_deletes_it_after_asking(stack):
    from test_app_server import wait_for
    from test_talk import ask_typed, talk_script

    talk_script(stack, {"say": "I can start an agent.", "action": "start_agent"}, {"say": "Noted.", "action": "none"})
    folder = stack["home"] / "brain" / "chats"
    folder.mkdir(parents=True, exist_ok=True)
    old = "c" + "a" * 16  # an earlier run's chat: its hand-off was sent, its suggestion never answered
    (folder / f"{old}.json").write_text(json.dumps({
        "id": old, "title": "Compare the plans", "created": "2026-10-09T09:00:00+00:00",
        "updated": "2026-10-09T09:05:00+00:00", "exchanges": [
            {"said": "tell agent 2 to compare the plans", "answer": "Giving your words to 2 · Research.",
             "time": "2026-10-09T09:00:00+00:00", "card": {"id": "h1", "kind": "give", "outcome": "Sent to agent 2"}},
            {"said": "and a new one for the logos", "answer": "I can start an agent.",
             "time": "2026-10-09T09:05:00+00:00", "card": {"id": "p1", "kind": "start_agent", "outcome": None}}]}),
        encoding="utf-8")
    js = await open_mission(stack)
    assert await until(js, MADE)
    await opened(js)
    await ask_typed(js, "check the shop")  # this chat's card: live, with Start
    assert await until(js, "!!document.querySelector('#talk-card .talk-go')", 15)
    await js("document.querySelector('#chat-history summary').click(); true")
    row = f"document.querySelector('#chat-list .chat-row[data-id=\"{old}\"]')"
    assert await until(js, f"{row} !== null")
    await js(f"{row}.querySelector('.open').click(); true")
    assert await until(js, f"{CHAT}.dataset.chat === {json.dumps(old)}")
    assert await js(LINES) == ["You: tell agent 2 to compare the plans", "Brain: Giving your words to 2 · Research.",
                               "Your words for an agent: Sent to agent 2", "You: and a new one for the logos",
                               "Brain: I can start an agent.", "Start a new agent: Not answered"]
    assert await js("document.querySelector('#talk-card .talk-go') === null")  # never re-armed: no Start, no Send
    assert await js("document.getElementById('chat-history').open") is False
    await js("document.querySelector('#chat-history summary').click(); true")
    assert await until(js, f"{row} !== null")
    dialog = "document.querySelector('dialog.confirm')"
    await js(f"{row}.querySelector('.delete').click(); true")  # Delete asks first
    assert await until(js, f"{dialog}?.open === true")
    assert await js(f"{dialog}.querySelector('h2').textContent") == 'Delete "Compare the plans"?'
    await js(f"{dialog}.querySelector('.keep').click(); true")  # Keep keeps it
    assert await until(js, f"{dialog} === null")
    assert (folder / f"{old}.json").exists()
    await js(f"{row}.querySelector('.delete').click(); true")
    assert await until(js, f"{dialog}?.open === true")
    await js(f"{dialog}.querySelector('.go').click(); true")
    await wait_for(lambda: not (folder / f"{old}.json").exists())
    assert await until(js, f"{row} === null")  # gone from History
    assert await until(js, f"{MADE} && {CHAT}.dataset.chat !== {json.dumps(old)} && {LOG}.children.length === 0")
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_chat_panel.py::test_new_chat_starts_empty_and_history_lists_the_chats_newest_first tests/test_chat_panel.py::test_history_reopens_a_chat_with_its_cards_as_text_and_deletes_it_after_asking -q -p no:randomly`

Expected: FAIL. Both wait in vain for `#brainchat`'s `data-chat` (`until` returns false: `assert False`).

- [ ] **Step 3: The panel's bar gets New chat and History ▾**

In `src/ai_browser/app/ui/mission.html`, replace:

```html
    <strong id="brainchat-title">Ask AI</strong>
    <button id="brainchat-close" class="ghost" type="button" aria-label="Close the Brain's chat"
```

with:

```html
    <strong id="brainchat-title">Ask AI</strong>
    <button id="chat-new" class="ghost" type="button"
            title="Start an empty chat: this one stays in History">New chat</button>
    <details id="chat-history" class="chat-history"><summary>History ▾</summary>
      <div id="chat-list" class="chat-list" aria-label="Your last 50 chats"></div></details>
    <button id="brainchat-close" class="ghost" type="button" aria-label="Close the Brain's chat"
```

In `src/ai_browser/app/ui/brainchat.css`, replace:

```css
.brainchat > .handoff-slot { flex: none; max-height: 45%; padding: 8px 10px 0; }
```

with:

```css
.chat-history { position: relative; }
.chat-history summary { list-style: none; cursor: pointer; font-size: 13px; padding: 2px 8px;
                        border: 1px solid var(--line); border-radius: var(--radius-sm); }
.chat-list { position: absolute; right: 0; top: calc(100% + 4px); z-index: 1; width: 300px; max-height: 320px;
             overflow-y: auto; display: flex; flex-direction: column; gap: 2px; padding: 6px; cursor: default;
             border-radius: 10px; background: var(--card); border: 1px solid var(--line-strong);
             box-shadow: var(--shadow); }
.chat-row { display: flex; align-items: center; gap: 4px; }
.chat-row .open { flex: 1; min-width: 0; display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
                  border: 0; background: transparent; padding: 4px 6px; text-align: left; }
.chat-row[aria-current="true"] .open { background: var(--selected); }
.chat-row .title { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chat-row .when { font-size: 11px; }
.chat-list .empty { margin: 4px 6px; font-size: 13px; }
.brainchat > .handoff-slot { flex: none; max-height: 45%; padding: 8px 10px 0; }
.talk-log li.past { color: var(--muted); font-style: italic; } /* a kept chat's card: how it ended, never live */
```

- [ ] **Step 4: `talk.js` shows another kept chat**

In `src/ai_browser/app/ui/talk.js`, replace:

```js
const GO = { start_agent: "Start", message_agent: "Send" }; // anything else is a draft card's "Draft it"
```

with:

```js
const GO = { start_agent: "Start", message_agent: "Send" }; // anything else is a draft card's "Draft it"
const PAST = { start_agent: "Start a new agent", message_agent: "Send to an agent", draft_reply: "Draft a reply",
               give: "Your words for an agent", start: "Start a new agent" }; // a kept chat's cards, as text
```

In `src/ai_browser/app/ui/talk.js`, replace:

```js
  const talkId = newId("k"); // one talk per page load: the Brain remembers its last few exchanges
```

with:

```js
  let talkId = newId("k"); // one talk per page load, or the kept chat Mission Control's chat shows (setTalk)
```

In `src/ai_browser/app/ui/talk.js`, replace:

```js
  function onMessage(message) {
    if (message.type === "hearing_status") statusChanged(message);
```

with:

```js
  function setTalk(id, exchanges = []) { // Mission Control's New chat and History: another kept chat, its whole log
    talkId = String(id);
    asking = null; // an answer for the chat before is never shown here
    confirming = null;
    closeProposal();
    closeCard();
    log.replaceChildren();
    status.textContent = "";
    notice.textContent = "";
    if (!turn && !finishing) setState("idle");
    for (const one of exchanges) { // its cards as text: how each ended, never a live button
      if (one?.said) line("You", String(one.said));
      if (one?.answer) line("Brain", String(one.answer));
      if (one?.card) {
        log.append(el("li", "past", `${PAST[one.card.kind] || "A card"}: ${one.card.outcome || "Not answered"}`));
      }
    }
    log.scrollTop = log.scrollHeight;
  }

  function onMessage(message) {
    if (message.type === "hearing_status") statusChanged(message);
```

In `src/ai_browser/app/ui/talk.js`, replace:

```js
  return { onMessage, connection, get state() { return state; } };
```

with:

```js
  return {
    onMessage, connection, setTalk,
    get state() { return state; },
    get fresh() { return !asking && !confirming && !log.children.length; }, // nothing said yet, nothing waiting
  };
```

- [ ] **Step 5: `brainchat.js` keeps the chats**

In `src/ai_browser/app/ui/brainchat.js`, replace:

```js
import { PICTURES_NOTE, takeFiles } from "./paste.js";
```

with:

```js
import { el } from "./chat.js";
import { confirmAction } from "./confirm.js";
import { PICTURES_NOTE, takeFiles } from "./paste.js";
```

In `src/ai_browser/app/ui/brainchat.js`, replace:

```js
// onToggle(open): it opened or closed (Mission Control tells the app whether its cards can be seen)
export function mountBrainChat({ onToggle = () => {} } = {}) {
  const $ = (id) => document.getElementById(id);
  const root = $("brainchat");
  const bar = $("brainchat-bar");
  const opener = $("ask-ai");
  let drag = null;
```

with:

```js
function when(iso) { // "Oct 10, 14:05", in the user's own way of writing it
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? ""
    : date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

// link: the line to the app; talk(): talk.js's talk, which shows the kept chat; onToggle(open): it opened or closed
// (Mission Control tells the app whether its cards can be seen). New chat and History ▾ (the spec, 5): the app makes
// a chat's id and keeps its file; a reopened chat shows its whole log, its cards as text.
export function mountBrainChat({ link, talk = () => null, onToggle = () => {} }) {
  const $ = (id) => document.getElementById(id);
  const root = $("brainchat");
  const bar = $("brainchat-bar");
  const opener = $("ask-ai");
  let drag = null;
  let current = null; // the kept chat shown: its id (the app made it)
  let waiting = null; // the New chat or the reopened chat whose brain_chat comes next
  let automatic = null; // the New chat a connection asked for: it takes over only a talk with nothing in it
  let asked = 0;

  function request(type, fields = {}) { // one request each, named chat-<n>
    asked += 1;
    const id = `chat-${asked}`;
    if (type !== "brain_chat_delete") waiting = id;
    link.send({ type, request: id, ...fields });
    return id;
  }

  function newChat(auto = false) { // an empty chat, with an id the app made (only those are kept)
    const id = request("brain_chat_new");
    automatic = auto ? id : null;
  }

  function show(chat) { // the chat the app sent: its id, and its whole log in the talk
    current = chat.id;
    root.dataset.chat = current;
    talk()?.setTalk(current, Array.isArray(chat.exchanges) ? chat.exchanges : []);
  }

  function renderList(rows) { // newest first, title and date; a click reopens one, Delete asks first
    $("chat-list").replaceChildren(...rows.map((row) => {
      const item = el("div", "chat-row");
      item.dataset.id = String(row.id || "");
      if (row.id === current) item.setAttribute("aria-current", "true");
      const title = String(row.title || "Untitled chat");
      const reopen = el("button", "open");
      reopen.type = "button";
      reopen.title = title;
      reopen.append(el("span", "title", title), el("span", "when muted", when(row.updated)));
      reopen.addEventListener("click", () => {
        $("chat-history").open = false;
        request("brain_chat_open", { id: row.id });
      });
      const remove = el("button", "ghost delete", "Delete");
      remove.type = "button";
      remove.setAttribute("aria-label", `Delete ${title}`);
      remove.addEventListener("click", () => forget(row.id, title));
      item.append(reopen, remove);
      return item;
    }));
    if (!rows.length) $("chat-list").append(el("p", "empty muted", "No chats yet"));
  }

  async function forget(id, title) { // Delete: asked first, Keep by default (confirm.js)
    if (!await confirmAction({ title: `Delete "${title}"?`, yes: "Delete",
                               lines: ["Your words and the Brain's answers in it are deleted from this computer."] })) {
      return;
    }
    request("brain_chat_delete", { id });
    if (id === current) newChat(); // the chat shown went: an empty one takes its place
  }

  $("chat-new").addEventListener("click", () => newChat());
  $("chat-history").addEventListener("toggle", () => {
    if ($("chat-history").open) link.send({ type: "brain_chats" });
  });
```

In `src/ai_browser/app/ui/brainchat.js`, replace:

```js
    onMessage(message) { // the Brain needs the user: a hand-off or a suggestion opens it, never taking the focus
      if (message.type === "brain_handoff" && OPEN.includes(message.handoff?.state)) open();
      else if (message.type === "brain_snapshot" && (message.handoffs || []).some((one) => OPEN.includes(one?.state))) {
        open();
      }
    },
```

with:

```js
    onMessage(message) { // the Brain needs the user: a hand-off or a suggestion opens it, never taking the focus
      if (message.type === "brain_handoff" && OPEN.includes(message.handoff?.state)) open();
      else if (message.type === "brain_snapshot" && (message.handoffs || []).some((one) => OPEN.includes(one?.state))) {
        open();
      }
      switch (message.type) {
        case "snapshot": // connected (again): a talk with nothing in it gets a chat of its own; one with words keeps it
          if (!current || !$("talk-log").children.length) newChat(true);
          break;
        case "brain_chat":
          if (message.request !== waiting || typeof message.chat?.id !== "string") break;
          waiting = null;
          if (message.request === automatic && !talk()?.fresh) break; // words came first: they stay as they are
          show(message.chat);
          break;
        case "brain_chats":
          renderList(Array.isArray(message.chats) ? message.chats : []);
          break;
        case "error":
          if (String(message.request || "").startsWith("chat-")) link.send({ type: "brain_chats" }); // gone meanwhile
          break;
      }
    },
```

- [ ] **Step 6: Mission Control hands the panel its line and its talk**

In `src/ai_browser/app/ui/mission.js`, replace:

```js
const chat = mountBrainChat({ // the Brain's chat (Ask AI): a floating panel over the office, never modal
  onToggle: (open) => {
```

with:

```js
const chat = mountBrainChat({ // the Brain's chat (Ask AI): a floating panel over the office, never modal
  link,
  talk: () => talk, // New chat and History show another kept chat in it
  onToggle: (open) => {
```

In `src/ai_browser/app/ui/mission.js`, replace:

```js
  keep: 200, // the Brain's chat: this run's talk with the Brain
```

with:

```js
  keep: 600, // the Brain's chat: a kept chat's whole log (200 exchanges, and their cards)
```

- [ ] **Step 7: Run them to see them pass, with their neighbours**

Run: `uv run pytest tests/test_chat_panel.py tests/test_brain_chats.py tests/test_talk.py tests/test_chat_page.py tests/test_delegation_pages.py tests/test_mission_look.py::test_ask_ai_opens_the_brains_chat_and_shows_its_answer -q -p no:randomly`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/ai_browser/app/ui/mission.html src/ai_browser/app/ui/brainchat.js src/ai_browser/app/ui/brainchat.css src/ai_browser/app/ui/talk.js src/ai_browser/app/ui/mission.js tests/test_chat_panel.py
git commit -m "feat: the Brain's chat keeps its chats: New chat, History ▾ (reopen, old cards as text) and Delete after asking

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Each agent's profile indicator: the Agents page's cards, the desks and the drawer

**Files:**
- Create: `src/ai_browser/app/ui/profiledot.js`
- Modify: `src/ai_browser/app/bravelink.py` (`__init__`, `_place_loop`), `src/ai_browser/app/server.py`
  (`_saved_snapshot`, `_browser_changed`, `_settings_set`, `attach_brave`)
- Modify: `src/ai_browser/app/ui/agentspage.js`, `src/ai_browser/app/ui/desk.js`, `src/ai_browser/app/ui/drawer.js`,
  `src/ai_browser/app/ui/mission.js`, `src/ai_browser/app/ui/mission.css`
- Test: `tests/test_bravelink.py`, `tests/test_agent_profiles.py`, `tests/test_agents_page.py`

**Interfaces:**
- Consumes: `ProfilePlace.ready(folder)`; the agent rows' `saved` and `profile`; `saved_agents`' `profiles`
  (`{folder, name, color, ready}`); `settings.get()["agents_profile"]`.
- Produces:
  - `saved_agents` gains `"chosen": str | None` (Settings' choice) and `"connected": bool` (Brave's state is
    "connected"); every page hears it again when Brave's state changes, when a profile is learned and when Settings'
    choice changes;
  - `BraveLink.on_place: Callable[[], None]` (called when its place loop learned something);
  - `profiledot.js`: `setProfiles(message)`, `profileState(folder: string | null) -> { state: "ready" | "open" |
    "off", word, hint }`, `profileDot(folder, { word = true } = {}) -> HTMLSpanElement` (`.profile-dot[data-state]`
    with `.dot`, and `.word` and `.hint` when `word`; else its `title` is "word: hint").

- [ ] **Step 1: Write the failing tests**

In `tests/test_bravelink.py`, replace:

```python
async def test_with_none_chosen_the_profile_used_last_is_listed(tmp_path):
```

with:

```python
async def test_a_profile_learned_is_told_to_the_app(tmp_path):  # the chat-panel spec, 7: the agents' indicator
    from ai_browser.app.bravelink import BraveLink

    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    local_state(folder, last_used="Default")
    port = FakePort(folder, pages=PROFILES, default="W")
    await port.start()
    link = BraveLink(folder, every=0.1, settle=0.3)
    learned = []
    link.on_place = lambda: learned.append(link.place.ready("Default"))
    link.set_place("Default")
    await link.start()
    try:
        await link.connect()
        assert await until(lambda: True in learned)  # Work's context learned: the app hears it at once
    finally:
        await link.close()
        await port.stop()


async def test_with_none_chosen_the_profile_used_last_is_listed(tmp_path):
```

In `tests/test_agent_profiles.py`, add at the end:

```python


async def test_every_page_hears_whether_each_profile_is_ready(fake_claude, tmp_path):  # the chat-panel spec, 7
    from test_app_server import until as told
    from ui_socket import ui_socket

    server, url = await started(fake_claude, tmp_path, EVENTS)
    brave = FakeBrave([])
    brave.place.listed = [{"folder": "Profile 1", "name": "Work", "color": None}]
    server.attach_brave(brave)
    try:
        async with ui_socket(server, url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "mission"}))
            await told(ws, lambda m: m["type"] == "snapshot")
            await ws.send(json.dumps({"type": "saved_agents"}))
            shown = (await told(ws, lambda m: m["type"] == "saved_agents"))[-1]
            assert (shown["connected"], shown["chosen"], [row["ready"] for row in shown["profiles"]]) == (
                True, None, [False])
            brave.place.learned.add("Profile 1")
            brave.on_place()  # BraveLink learned it (its place loop): every page hears it at once
            assert [row["ready"] for row in (await told(ws, lambda m: m["type"] == "saved_agents"))[-1]["profiles"]] \
                == [True]
            await ws.send(json.dumps({"type": "settings_set", "key": "agents_profile", "value": "Profile 1"}))
            assert (await told(ws, lambda m: m["type"] == "saved_agents"))[-1]["chosen"] == "Profile 1"
            brave.set_state("lost")  # Brave went
            assert (await told(ws, lambda m: m["type"] == "saved_agents"))[-1]["connected"] is False
    finally:
        await server.stop()
```

In `tests/test_agents_page.py`, replace:

```python
# ---- Effort: beside Model on the Agents page, and in the drawer with the model ---------------------------------------
```

with:

```python
# ---- the profile indicator: cards, desks and drawers (the chat-panel spec, 7) ----------------------------------------

@CHROME
async def test_each_agent_shows_whether_its_brave_profile_is_ready(stack):
    server, brave = stack["server"], stack["brave"]
    brave.place.listed = [{"folder": "Profile 1", "name": f"Work {HOSTILE}", "color": None}]
    saved = server.saved.save({**AGENT, "profile": "Profile 1"})
    stack["script"].write_text(json.dumps([{"sleep": 30}]), encoding="utf-8")  # its runs stay at work
    await server.agents.run_as(saved, "List the prices")
    run = server.agents.run_of(saved.slug)
    plain = await server.agents.create("Fix the footer")  # a one-off run: the indicator in its drawer only
    js = await open_agents(stack)
    dot = f"{card(saved.slug)}?.querySelector('.profile-dot')"
    desk = f"document.querySelector('.station[data-id=\"{run.id}\"] .nameplate .profile-dot')"
    in_drawer = "document.querySelector('#drawer-body .profile-dot')"
    assert await until(js, f"{dot}?.dataset.state === 'open'")
    assert await js(f"{dot}.querySelector('.word').textContent") == "Open it once"
    hint = f"Open a Brave window of the Work {HOSTILE} profile once: AI Browser learns it in about 30 seconds"
    assert await js(f"{dot}.querySelector('.hint').textContent") == hint
    assert await js("document.querySelectorAll('img[src=x]').length === 0 && document.title !== 'pwned'")
    x, y = await js(f"(() => {{ const r = {dot}.querySelector('.dot').getBoundingClientRect();"
                    " return [r.left + r.width / 2, r.top + r.height / 2]; })()")
    await stack["cdp"].send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y}, session_id=js.session)
    assert await until(js, f"getComputedStyle({dot}.querySelector('.hint')).display === 'block'")  # what to do
    await js("document.querySelector('.page-link[data-page=\"dashboard\"]').click(); true")
    assert await until(js, f"{desk}?.dataset.state === 'open'")
    assert (await js(f"{desk}.title")).startswith("Open it once: ")
    label = f"document.querySelector('.station[data-id=\"{run.id}\"]').getAttribute('aria-label')"
    assert "Brave profile: Open it once" in await js(label)
    assert await js(f"document.querySelector('.station[data-id=\"{plain.id}\"] .profile-dot') === null")  # one-off
    await js(open_drawer(plain.id))
    assert await until(js, f"{in_drawer}?.dataset.state === 'ready'")  # Settings' choice: the profile Brave used last
    await js(open_drawer(run.id))
    assert await until(js, f"{in_drawer}?.dataset.state === 'open'")
    brave.place.learned.add("Profile 1")
    brave.on_place()  # AI Browser learned it: every page hears it at once
    for node in (dot, desk, in_drawer):
        assert await until(js, f"{node}?.dataset.state === 'ready'"), node
    assert await js(f"{dot}.querySelector('.word').textContent") == "Ready"
    brave.set_state("lost")  # Brave went
    for node in (dot, desk, in_drawer):
        assert await until(js, f"{node}?.dataset.state === 'off'"), node
    assert await js(f"{in_drawer}.querySelector('.word').textContent") == "Brave not connected"


# ---- Effort: beside Model on the Agents page, and in the drawer with the model ---------------------------------------
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_bravelink.py::test_a_profile_learned_is_told_to_the_app tests/test_agent_profiles.py::test_every_page_hears_whether_each_profile_is_ready tests/test_agents_page.py::test_each_agent_shows_whether_its_brave_profile_is_ready -q -p no:randomly`

Expected: FAIL. The BraveLink test: `until` returns False (nothing calls `on_place`); the socket test: `KeyError:
'connected'`; the page test: no `.profile-dot` on the card (`until` returns False).

- [ ] **Step 3: The app tells every page**

In `src/ai_browser/app/bravelink.py`, replace:

```python
        self.brain_site: Callable[[str], str | None] = lambda url: None  # the server's: which site an address is
```

with:

```python
        self.brain_site: Callable[[str], str | None] = lambda url: None  # the server's: which site an address is
        self.on_place: Callable[[], None] = lambda: None  # the server's: a profile was learned (the agents' indicator)
```

In `src/ai_browser/app/bravelink.py`, replace:

```python
            if self.place.look(watch, watch.default_context):
                self._changed()
```

with:

```python
            if self.place.look(watch, watch.default_context):
                self._changed()
                self.on_place()  # each agent's "Ready" (the chat-panel spec, 7): every page hears it at once
```

In `src/ai_browser/app/server.py`, replace:

```python
    def _saved_snapshot(self) -> dict:
        """The saved agents, and Brave's profiles for their settings: each "ready" once AI Browser has learned it on
        this connection (else the page says "open it once")."""
        place = self.brave.place if self.brave is not None else None
        return {"type": "saved_agents", "agents": [saved.public() for saved in self.saved.all()],
                "profiles": [{**row, "ready": place.ready(row["folder"])} for row in self._profiles()]}
```

with:

```python
    def _saved_snapshot(self) -> dict:
        """The saved agents, and Brave's profiles for their settings: each "ready" once AI Browser has learned it on
        this connection (else the page says "open it once"); Settings' choice and whether Brave is connected, for
        each agent's indicator (the Agents page's cards, the desks and the drawer)."""
        place = self.brave.place if self.brave is not None else None
        return {"type": "saved_agents", "agents": [saved.public() for saved in self.saved.all()],
                "profiles": [{**row, "ready": place.ready(row["folder"])} for row in self._profiles()],
                "chosen": self.settings.get()["agents_profile"],
                "connected": self.brave is not None and self.brave.state == "connected"}
```

In `src/ai_browser/app/server.py`, replace:

```python
        self._send_all({"type": "browser", **self._browser_info()})
```

with:

```python
        self._send_all({"type": "browser", **self._browser_info()})
        self._send_all(self._saved_snapshot())  # and each agent's indicator: Brave connected, or not
```

In `src/ai_browser/app/server.py`, replace:

```python
        if key == "agents_profile" and self.brave is not None:  # Settings → Where agents browse
            self.brave.set_place(self.settings.get()["agents_profile"])
```

with:

```python
        if key == "agents_profile" and self.brave is not None:  # Settings → Where agents browse
            self.brave.set_place(self.settings.get()["agents_profile"])
            self._send_all(self._saved_snapshot())  # the indicator of the agents that follow Settings' choice
```

In `src/ai_browser/app/server.py`, replace:

```python
        brave.on_state(lambda state: self._browser_changed())
```

with:

```python
        brave.on_state(lambda state: self._browser_changed())
        brave.on_place = lambda: self._send_all(self._saved_snapshot())  # a profile learned: each agent's "Ready"
```

- [ ] **Step 4: Write `profiledot.js`**

Create `src/ai_browser/app/ui/profiledot.js`:

```js
// Each agent's profile indicator (the chat-panel spec, 7): whether the Brave profile it browses in is ready. A dot and
// a word: Ready (its context is learned: its tabs can open there), Open it once (open a Brave window of that profile:
// AI Browser learns it in about 30 seconds) or Brave not connected. The hint says what to do, on hover and on focus.
// An agent on "Settings' choice" follows the profile Settings picks; with none picked, the one Brave used last. It
// follows the saved_agents message, which the app sends again when Brave connects or goes, when a profile is learned
// and when Settings' choice changes. Nothing opens Brave by itself. Every word is set as text.
"use strict";

import { el } from "./chat.js";

let known = { profiles: [], chosen: null, connected: false };

export function setProfiles(message) { // saved_agents: {profiles: [{folder, name, ready}], chosen, connected}
  known = { profiles: Array.isArray(message?.profiles) ? message.profiles : [],
            chosen: typeof message?.chosen === "string" && message.chosen ? message.chosen : null,
            connected: message?.connected === true };
}

// folder: the agent's own profile, or null (Settings' choice)
export function profileState(folder) {
  if (!known.connected) {
    return { state: "off", word: "Brave not connected",
             hint: "Connect Brave at the top of Mission Control: then it shows whether this profile is ready" };
  }
  const chosen = typeof folder === "string" && folder ? folder : known.chosen;
  if (!chosen) return { state: "ready", word: "Ready", hint: "It browses in the profile Brave used last" };
  const row = known.profiles.find((one) => one?.folder === chosen);
  const name = String(row?.name || chosen);
  if (row?.ready === true) return { state: "ready", word: "Ready", hint: `It browses in Brave's ${name} profile` };
  return { state: "open", word: "Open it once",
           hint: `Open a Brave window of the ${name} profile once: AI Browser learns it in about 30 seconds` };
}

// The dot and the word, the hint shown on hover and focus. A desk's nameplate has no room: the dot alone (word:
// false), its word and hint as its tooltip.
export function profileDot(folder, { word = true } = {}) {
  const shown = profileState(folder);
  const node = el("span", "profile-dot");
  node.dataset.state = shown.state;
  node.append(el("span", "dot"));
  if (word) node.append(el("span", "word", shown.word), el("span", "hint", shown.hint));
  else node.title = `${shown.word}: ${shown.hint}`;
  return node;
}
```

In `src/ai_browser/app/ui/mission.css`, replace:

```css
.agent-card .about:empty { display: none; }
```

with:

```css
.agent-card .about:empty { display: none; }
/* Each agent's profile indicator (profiledot.js): green Ready, amber Open it once, grey Brave not connected; its hint
   on hover, and on keyboard focus of the card or the drawer's line */
.profile-dot { position: relative; display: inline-flex; align-items: center; gap: 6px; font-size: 12px;
               color: var(--text-2); }
.profile-dot .dot { flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--wait); }
.profile-dot[data-state="ready"] .dot { background: var(--ok); }
.profile-dot[data-state="open"] .dot { background: var(--needs); }
.profile-dot .hint { display: none; position: absolute; left: 0; top: calc(100% + 4px); z-index: 5; width: max-content;
                     max-width: 260px; padding: 6px 8px; border-radius: 8px; background: var(--card);
                     border: 1px solid var(--line-strong); box-shadow: var(--shadow); color: var(--text);
                     font-weight: 400; text-align: left; white-space: normal; }
.profile-dot:is(:hover, :focus-visible) .hint, :focus-visible > .profile-dot .hint { display: block; }
.nameplate .profile-dot { display: inline-block; margin-right: 4px; vertical-align: 1px; }
.nameplate .profile-dot .dot { display: block; }
.profile-line { display: flex; align-items: center; gap: 6px; }
```

- [ ] **Step 5: Cards, desks and the drawer show it**

In `src/ai_browser/app/ui/agentspage.js`, replace:

```js
import { pageHead } from "./pages.js";
```

with:

```js
import { pageHead } from "./pages.js";
import { profileDot } from "./profiledot.js";
```

In `src/ai_browser/app/ui/agentspage.js`, replace:

```js
                  el("span", "next muted", nextRun(row.slug)));
```

with:

```js
                  el("span", "next muted", nextRun(row.slug)),
                  profileDot(row.profile)); // Ready, Open it once, or Brave not connected
```

In `src/ai_browser/app/ui/desk.js`, replace:

```js
import { STATES, stepOf, timerOf } from "./step.js";
```

with:

```js
import { profileDot } from "./profiledot.js";
import { STATES, stepOf, timerOf } from "./step.js";
```

In `src/ai_browser/app/ui/desk.js`, replace:

```js
    setTitled(parts.nameplate, name, agentTip(agent, name)); // the whole name, then what it works on
```

with:

```js
    setTitled(parts.nameplate, name, agentTip(agent, name)); // the whole name, then what it works on
    const plate = agent.saved ? profileDot(agent.profile, { word: false }) : null; // a saved agent's run: its profile
    if (parts.plateDot && !parts.plateDot.isConnected) parts.plateDot = null; // the name was written over it
    if (plate?.title !== parts.plateDot?.title || plate?.dataset.state !== parts.plateDot?.dataset.state) {
      parts.plateDot?.remove();
      parts.plateDot = plate;
      if (plate) parts.nameplate.prepend(plate);
    }
```

In `src/ai_browser/app/ui/desk.js`, replace:

```js
    const label = `${name}: ${STATES[step.state] || step.state}`;
```

with:

```js
    const label = `${name}: ${STATES[step.state] || step.state}${plate ? ` · Brave profile: ${plate.title}` : ""}`;
```

In `src/ai_browser/app/ui/drawer.js`, replace:

```js
import { permissionCard } from "./permission.js";
```

with:

```js
import { permissionCard } from "./permission.js";
import { profileDot } from "./profiledot.js";
```

In `src/ai_browser/app/ui/drawer.js`, replace:

```js
    setText(parts.folder, agent.folder ? `Folder: ${agent.folder}` : "No folder: its own scratch folder");
```

with:

```js
    setText(parts.folder, agent.folder ? `Folder: ${agent.folder}` : "No folder: its own scratch folder");
    const where = profileDot(agent.profile); // where it browses: Ready, Open it once, or Brave not connected
    where.tabIndex = 0; // its hint shows on keyboard focus too
    const was = parts.profile.lastElementChild;
    if (was?.dataset.state !== where.dataset.state || was?.textContent !== where.textContent) {
      parts.profile.replaceChildren(el("span", "muted", "Brave profile:"), where);
    }
```

In `src/ai_browser/app/ui/drawer.js`, replace:

```js
                    folder: el("div", "status muted folder"), plan: el("section", "plan"),
```

with:

```js
                    folder: el("div", "status muted folder"), plan: el("section", "plan"),
                    profile: el("div", "status profile-line"),
```

In `src/ai_browser/app/ui/drawer.js`, replace:

```js
    $("drawer-body").replaceChildren(parts.about, parts.status, parts.moved, parts.folder, parts.auto, parts.autoWords,
```

with:

```js
    $("drawer-body").replaceChildren(parts.about, parts.status, parts.moved, parts.folder, parts.profile, parts.auto,
                                     parts.autoWords,
```

In `src/ai_browser/app/ui/mission.js`, replace:

```js
import { createScene } from "./scene.js";
```

with:

```js
import { setProfiles } from "./profiledot.js";
import { createScene } from "./scene.js";
```

In `src/ai_browser/app/ui/mission.js`, replace:

```js
function handle(message) {
  for (const part of parts) part.onMessage?.(message);
  switch (message.type) {
```

with:

```js
function handle(message) {
  if (message.type === "saved_agents") setProfiles(message); // first: the Agents page's cards read it (profiledot.js)
  for (const part of parts) part.onMessage?.(message);
  switch (message.type) {
    case "saved_agents": // whether each profile is ready: every desk and the drawer show it again
      for (const agent of agents.values()) scene.upsert(agent);
      if (drawer.id) drawer.fill(agents.get(drawer.id));
      break;
```

- [ ] **Step 6: Run them to see them pass, with every test that reads a desk, a card or the drawer**

Run: `uv run pytest tests/test_bravelink.py tests/test_agent_profiles.py tests/test_agents_page.py tests/test_saved_agents.py tests/test_place.py tests/test_named_missions.py tests/test_mission.py tests/test_office.py tests/test_talk.py::test_numbers_show_on_stations_the_list_and_the_drawer tests/test_mission_home.py tests/test_theme.py tests/test_ui_static.py -q -p no:randomly`

Expected: PASS (the room's step-card test among them: the dot sits inside the nameplate, whose box doesn't move).

- [ ] **Step 7: Commit**

```bash
git add src/ai_browser/app/ui/profiledot.js src/ai_browser/app/bravelink.py src/ai_browser/app/server.py src/ai_browser/app/ui/agentspage.js src/ai_browser/app/ui/desk.js src/ai_browser/app/ui/drawer.js src/ai_browser/app/ui/mission.js src/ai_browser/app/ui/mission.css tests/test_bravelink.py tests/test_agent_profiles.py tests/test_agents_page.py
git commit -m "feat: each agent shows whether its Brave profile is ready: Ready, Open it once or Brave not connected, on its card, desk and drawer

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: The README, and the whole suite

**Files:**
- Modify: `README.md`
- Test: `tests/test_brain_chats.py`, `tests/test_delegation_pages.py`, `tests/test_mission_look.py` (their README
  assertions)

**Interfaces:**
- Consumes: everything above, as the README tells the user.
- Produces: nothing new for code.

- [ ] **Step 1: Write the failing README tests**

In `tests/test_brain_chats.py`, add at the end:

```python


# ---- the README (Task 7) --------------------------------------------------------------------------------------------

def test_the_readme_explains_the_brains_chat_and_the_profile_dot():
    from pathlib import Path

    text = " ".join((Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8").split())
    for needed in ("### The Brain's chat (Ask AI)", "the office, the desks and the drawers stay clickable around it",
                   "**×** or **Esc** closes it", "It opens by itself when the Brain needs you",
                   "count down only while it is open", "**History ▾** lists your last 50 chats",
                   "the Brain reads its last 6 exchanges again", "never run again", "**Delete** asks first",
                   "`~/.ai-browser/brain/chats/<id>.json`", "The floating chat and the inbox's talks are not kept",
                   "**Ready** (green), **Open it once** (amber", "**Brave not connected** (grey)",
                   "Nothing opens Brave by itself"):
        assert needed in text, needed
    for gone in ("a short strip", "turns solid and scrolls", "**Ask AI**, in the composer", "beside Start"):
        assert gone not in text, gone
```

In `tests/test_delegation_pages.py`, replace:

```python
                   "**Ask AI** keeps this run's talk above the box", "the wheel scrolls your talk, not the office",
                   "a short strip", "turns solid and scrolls",
```

with:

```python
                   "the **Ask AI** button, which opens **the Brain's chat**",
                   "the office, the desks and the drawers stay clickable around it",
```

In `tests/test_mission_look.py`, replace:

```python
                   "past 12 desks, the oldest finished agents leave the room", "**Ask AI**, in the composer",
```

with:

```python
                   "past 12 desks, the oldest finished agents leave the room", "**Ask AI** opens the Brain's chat",
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_brain_chats.py::test_the_readme_explains_the_brains_chat_and_the_profile_dot tests/test_delegation_pages.py::test_the_readme_explains_names_handoffs_sources_and_the_history tests/test_mission_look.py::test_the_readme_describes_the_new_look -q -p no:randomly`

Expected: FAIL: `AssertionError: ### The Brain's chat (Ask AI)`, `AssertionError: the **Ask AI** button, which opens
**the Brain's chat**`, `AssertionError: **Ask AI** opens the Brain's chat`.

- [ ] **Step 3: Write the README**

In `README.md`, replace:

```markdown
  cancels it; saying anything else pauses it, and it then waits for your **Send**. It counts down only while an AI
  Browser window that shows the card is on screen (Mission Control or the floating chat): a hidden window, or
  another tab in front, makes it wait for your **Send**. Stop on that agent cancels it. Turning off **Hand tasks to
  working agents by itself** makes every hand-off wait for your **Send**, and nothing is sent once AI Browser quits.
```

with:

```markdown
  cancels it; saying anything else pauses it, and it then waits for your **Send**. It counts down only while a card
  can be seen: the Brain's chat open in Mission Control, or the floating chat, on screen. The Brain's chat closed (×
  or Esc), a hidden window, or another tab in front, makes it wait for your **Send**. Stop on that agent cancels it.
  Turning off **Hand tasks to working agents by itself** makes every hand-off wait for your **Send**, and nothing is
  sent once AI Browser quits.
```

In `README.md`, replace:

```markdown
- The card shows in the Brain's inbox (the globe's drawer in Mission Control), under Mission Control's
  view switch and in the floating chat, and AI Browser's own app notifies you, never with the instruction. The agent's
  chat shows "From the Brain: …", and the Brain's inbox keeps this run's cards.
```

with:

```markdown
- The card shows in the Brain's inbox (the globe's drawer in Mission Control), in the Brain's chat (which opens
  itself for it) and in the floating chat, and AI Browser's own app notifies you, never with the instruction. The
  agent's chat shows "From the Brain: …", and the Brain's inbox keeps this run's cards.
```

In `README.md`, replace:

```markdown
- **The composer:** **Ask AI** (the Brain answers and proposes; nothing runs until you press Start or Send, or say
  yes, except your words for a working agent you named, after a 15-second countdown you can cancel) and **Build a
  Mission** (a new agent). Templates are on the Agents page. **Build a Mission** has two optional fields above
```

with:

```markdown
- **The composer:** **Build a Mission** (a new agent), and beside it the **Ask AI** button, which opens **the Brain's
  chat** (see below). Templates are on the Agents page. **Build a Mission** has two optional fields above
```

In `README.md`, replace:

```markdown
  tooltip elsewhere, and neither is sent to the agent (your task is its instruction). **Ask AI** keeps this run's talk
  above the box, the newest at the bottom: a short strip, older lines fading out above it. Point at it (or tab into
  it) and it grows, turns solid and scrolls, and the wheel scrolls your talk, not the office. Under the box:
```

with:

```markdown
  tooltip elsewhere, and neither is sent to the agent (your task is its instruction). Under the box:
```

In `README.md`, replace:

```markdown
    of them that comes along. **Ask AI** takes no files: a picture pasted there says "Pictures
```

with:

```markdown
    of them that comes along. The Brain's chat takes no files: a picture pasted there says "Pictures
```

In `README.md`, replace:

```markdown
  - **Model**, **Account**, **Folder**, **Auto-approve in its folder** and **Workspace**; the mic (in Ask AI it talks
    to the Brain; otherwise your words fill the box); and **Start Mission** (⌘↵; Ctrl+Enter on Windows).
```

with:

```markdown
  - **Model**, **Account**, **Folder**, **Auto-approve in its folder** and **Workspace**; and **Start Mission** (⌘↵;
    Ctrl+Enter on Windows). While the Brain's chat is closed, holding **Space** puts your words in the box.
```

In `README.md`, replace:

```markdown
- **Brave profile:** its tabs open only in that profile of your Brave. Until AI Browser has learned the profile, the
  run says so: open a window of it in Brave once.
```

with:

```markdown
- **Brave profile:** its tabs open only in that profile of your Brave. Until AI Browser has learned the profile, the
  run says so: open a window of it in Brave once. Its card, its runs' desks and their drawers show a dot and a word:
  **Ready** (green), **Open it once** (amber: open a Brave window of that profile, and AI Browser learns it in about
  30 seconds) or **Brave not connected** (grey). Point at it (or tab to it) to read what to do. A one-off run shows it
  in its drawer, for the profile Settings picks. Nothing opens Brave by itself.
```

In `README.md`, replace:

```markdown
Each agent is a file, `~/.ai-browser/agents/<slug>.md` (front matter, then the instruction), written by the Agents
page's Save; one you edit by hand is read too and checked as a Save is; a broken one is skipped.
```

with:

```markdown
Each agent is a file, `~/.ai-browser/agents/<slug>.md` (front matter, then the instruction), written by the Agents
page's Save; one you edit by hand is read too and checked as a Save is; a broken one is skipped.

### The Brain's chat (Ask AI)

**Ask AI**, beside **Build a Mission**, opens the Brain's chat: a panel over Mission Control (bottom-right, above the
composer), where you type to the Brain or talk with its **mic button**. It is never in the way: the office, the desks
and the drawers stay clickable around it. Drag it by its title bar: it stays on screen, and keeps its place for this
window size. **×** or **Esc** closes it. Under 900 px wide it fills the width at the bottom. It opens by itself when
the Brain needs you: a hand-off card, a suggestion, or an answer to your words.
- **Hand-off cards** show at its top, and count down only while it is open: closing it holds the countdown, and the
  card waits for your **Send**.
- **New chat** starts an empty chat, and the Brain starts afresh. **History ▾** lists your last 50 chats, newest
  first, with their titles (your first words) and dates. A click reopens one with its whole talk, and the Brain reads
  its last 6 exchanges again. Its old cards show as text, with how they ended ("Sent to agent 2", "Cancelled", "Not
  answered"), and never run again. **Delete** asks first.
- Each chat is a file, `~/.ai-browser/brain/chats/<id>.json`, that only you can read: your words and the Brain's
  answers, at most 200 exchanges. Only AI Browser writes them, and they go nowhere but AI Browser's own pages. The
  floating chat and the inbox's talks are not kept.
```

In `README.md`, replace:

```markdown
In Mission Control, hold **Space** (while no text box or button has focus) and talk to the Brain, then let go. Or
hold the **mic button** beside Start, or click it once to start and again to stop. **Esc** throws the turn away, and a
turn stops by itself at 30 seconds. **Ask AI**, in the composer, does the same, typed.
```

with:

```markdown
In Mission Control, hold **Space** (while no text box or button has focus) and talk to the Brain, then let go. Or
hold the **mic button** in the Brain's chat, or click it once to start and again to stop. **Esc** throws the turn
away, and a turn stops by itself at 30 seconds. **Ask AI** opens the Brain's chat, where you can type the same.
```

- [ ] **Step 4: Run the README tests, then the whole suite**

Run: `uv run pytest tests/test_brain_chats.py tests/test_delegation_pages.py::test_the_readme_explains_names_handoffs_sources_and_the_history tests/test_mission_look.py::test_the_readme_describes_the_new_look tests/test_talk.py::test_the_readme_says_how_to_talk_and_the_zero_setup_way tests/test_talk.py::test_the_readme_says_the_brain_can_send_to_an_open_agent tests/test_saved_agents.py -q -p no:randomly`

Expected: PASS.

Run: `uv run pytest -m "not docker" -q -p no:randomly`

Expected: PASS (the Chrome tests too: they run in throwaway headless Chromes, never the user's Brave). A failure here
is fixed in the task that owns its file, and that task's tests run again.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_brain_chats.py tests/test_delegation_pages.py tests/test_mission_look.py
git commit -m "docs: the README tells of the Brain's chat panel, its History, and each agent's profile indicator

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Self-review

Run against the spec with fresh eyes, after the plan was written.

**1. Spec coverage.**
- Decision 1 (the talk leaves the composer; Ask AI becomes a button): Task 3 (markup, `composer.js`, the moved tests).
- Decision 2 (a floating panel, 380×520, bottom-right, dragged, kept on screen, its place per window size in
  `localStorage` with try/catch, × or Esc, not modal, under 900 px full width at 70 %, holding everything `#talk`
  held): Task 3 (`brainchat.js`, `brainchat.css`; tests: Ask AI/×/Esc, desk and drawer clickable, drag and place,
  Review Focus 3, narrow).
- Decision 3 (opens itself for a hand-off, a suggestion, a "which agent?" question; a countdown only while open):
  Task 3 (self-open on `brain_handoff`, `brain_snapshot` and the talk's `reveal`; tests for a card and a setup card),
  Task 4 (`link.js`'s `shown`, the countdown test, and every page test that relied on Mission Control being seen).
- Decision 4 (the last 50 chats, files, 0600, fields, 200 exchanges, only the app writes, the floating chat and inbox
  talks not kept): Task 1 (`chats.py` and its tests), Task 2 (only for ids the app made; the floating `k1` talk stays
  unkept in the socket test).
- Decision 5 (New chat, History ▾ newest first with title and date, reopen, Delete after `confirm.js`, the whole log,
  the Brain gets its last `KEEP`, cards as text): Task 1 (`restore`, `card`, `settle`), Task 2 (the restart test's
  prompt), Task 5 (the UI and its two tests).
- Decision 6 (four app-only messages with their copy in `test_watcher_rules.py`; unknown or malformed ids refused):
  Task 2.
- Decision 7 (the indicator on cards, desks and the drawer; three states; hover and focus; Settings' choice; one-off
  runs in the drawer only; within about 30 s; tokens only; nothing opens Brave): Task 6.
- Safety: chat files 0600 (Tasks 1, 2); only the user's clicks and words reach them (Task 2's app-only rows; the
  Brain, templates and pages never call `Chats`); text set with `textContent` (every page test checks a hostile
  string); countdown only while seen (Task 4).
- Testing section: pages (Tasks 3–6), server (Tasks 1–2), room height (Task 3, Step 9: the step-card and
  composer-height tests).
- Out of scope, untouched: the inbox drawer (`brainui.js`'s `mountBrain`), the floating chat (`chat.html`,
  `chatpage.js`: `talk.js`'s new options default to today's behaviour), the inbox's per-item talks (`BrainService.tells`
  never gets `on_add`).

**2. Placeholder scan.** No step says "TBD", "handle edge cases" or "similar to Task N"; every code step shows its
code, and every changed place is found by quoted text. The one mechanical step without a quote (Task 3, Step 7's
`setMode` → `render` renames) names the exact count of places and the `grep` that shows none are left.

**3. Type consistency.** `Chats.add(chat_id, said, answer)` matches `Talks.on_add(talk_id, said, answer)`;
`Chats.settle(card_id, outcome)` matches `BrainService.card_ended(card, outcome)`; `Chats.last` returns the
`(said, answer)` tuples `Talks.restore` takes; `brain_chat`'s `chat.exchanges` is what `talk.setTalk(id, exchanges)`
reads (`said`, `answer`, `card.kind`, `card.outcome`); `mountBrainChat` grows from `{ onToggle }` (Task 3) to
`{ link, talk, onToggle }` (Task 5), and Task 4 and Task 5 each quote the exact call they change; `link.seen()` (Task
4) is `report`; `setProfiles(message)` reads the `chosen`, `connected` and `profiles` that `_saved_snapshot` sends
(Task 6).

**4. Review Focus.** The five lines above each name the test that pins them, in the task that owns the code.
Checked and left out (covered elsewhere): a hand-off that ends while its chat is not the one shown (settle finds its
chat by the card's id); two Mission Control windows on one chat (each writes through the app, one file, in order).
