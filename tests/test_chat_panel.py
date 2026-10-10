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
from test_talk import ENTER, ESCAPE, SPACE, click, front, tap

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
CHAT = "document.getElementById('brainchat')"
ASK = "document.getElementById('ask-ai')"
LOG = "document.getElementById('talk-log')"
LINES = "[...document.querySelectorAll('#talk-log li')].map(line => line.textContent)"
BOX = ("(selector) => { const r = document.querySelector(selector).getBoundingClientRect();"
       " return [Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)]; }")
SIDE = 330  # the right column's width from 1280 px (mission.css)
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
    assert right == 1440 - SIDE - 16  # bottom-right, left of the right column (fix round 1)
    assert bottom <= (await js(f"({BOX})('#composer')"))[1]  # over the composer
    assert await js(hits("document.getElementById('start-label')"))  # Start Mission stays in view
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
    assert (await other(f"({BOX})('#brainchat')"))[2] == 1280 - SIDE - 16


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


DRAWER_HIT = ("(() => { const r = document.getElementById('drawer-body').getBoundingClientRect();"
              " return document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)?.closest('#drawer')"
              " === document.getElementById('drawer'); })()")


@CHROME
@pytest.mark.parametrize("width, height", [(1440, 900), (1280, 760), (1100, 800), (800, 700)])
async def test_the_brains_chat_never_covers_the_right_column_or_an_open_drawer(stack, width, height):  # fix round 1
    stack["script"].write_text(json.dumps([{"sleep": 30}]), encoding="utf-8")  # it stays at work
    await stack["server"].agents.create("Fix the footer")
    js = await open_with(stack, size=(width, height))
    await front(stack, js)
    assert await until(js, f"{station('a1')} !== null")
    await js(f"{station('a1', '.nameplate')}.click(); true")
    await opened(js)
    if width >= 1280:  # the right column beside the office: Current Task's Chat and the Activity stay in reach
        assert await js(hits("document.getElementById('current-chat')"))
        await click(stack, js, "#current-chat")  # a real click on it, the chat open
    else:  # the right column folds under the office: the drawer opens from it all the same
        await js("document.getElementById('current-chat').click(); true")
    assert await until(js, "!document.getElementById('drawer').hidden")
    assert await js(f"!{CHAT}.hidden")
    assert await until(js, DRAWER_HIT)  # the open drawer's middle: the drawer, never the chat
    await click(stack, js, "#drawer-close")  # a real click closes it
    assert await until(js, "document.getElementById('drawer').hidden")


@CHROME
async def test_the_brains_chat_reopens_with_its_newest_line_in_view(stack):  # fix round 1
    from test_talk import ask_typed, talk_script

    talk_script(stack, {"say": "Noted", "action": "none"})
    js = await open_with(stack, size=(1440, 900))
    await opened(js)
    for number in range(12):  # more lines than the chat shows at once
        await ask_typed(js, f"question {number}")
        assert await until(js, f"{LOG}.querySelectorAll('li.brain').length === {number + 1}", 15)
    newest = (f"{LOG}.scrollTop > 0"
              f" && Math.abs({LOG}.scrollTop + {LOG}.clientHeight - {LOG}.scrollHeight) <= 1")
    assert await until(js, newest)
    await js(f"{LOG}.scrollTop = 0; true")  # the user read back to the first line
    await js("document.getElementById('brainchat-close').click(); true")
    assert await until(js, f"{CHAT}.hidden")
    await js(f"{ASK}.click(); true")
    assert await until(js, f"!{CHAT}.hidden")
    assert await js(newest)  # reopened: the newest line, not the oldest


@CHROME
async def test_a_voice_notice_opens_the_brains_chat(stack):  # fix round 1
    from test_talk import SPACE, mic, open_talk

    js = await open_talk(stack, mic(), ask=False)  # the chat closed
    await tap(stack, js, SPACE, " ")  # too short: "Hold Space while you talk"
    assert await until(js, f"!{CHAT}.hidden"
                           " && document.getElementById('talk-notice').textContent === 'Hold Space while you talk'")


@CHROME
async def test_a_click_on_the_bar_without_a_move_keeps_no_place(stack):  # fix round 1
    js = await open_with(stack, size=(1440, 900))
    await front(stack, js)
    await opened(js)
    before = await js(f"({BOX})('#brainchat')")
    x, y = await js(TITLE)
    await drag(stack, js, (x, y), (x, y), steps=0)  # pressed and let go where it was
    await asyncio.sleep(0.3)
    assert await js("localStorage.getItem('brainchat-places')") is None  # nothing saved: it keeps the default place
    assert await js(f"({BOX})('#brainchat')") == before and await js(f"!{CHAT}.classList.contains('placed')")


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
    import shutil

    from test_talk import SPACE, mic, open_talk

    shutil.rmtree(stack["hearing"].models.folder)  # talking isn't set up yet: no model
    js = await open_talk(stack, mic(), hearing="no_model", ask=False)  # the chat closed
    await tap(stack, js, SPACE, " ")  # Space: talking isn't set up yet, and its card says how
    assert await until(js, f"!{CHAT}.hidden && !!document.querySelector('#talk-card .download')")


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
    assert await until(js, f"{in_slot(handoff_id=counting.id)}?.dataset.state === 'counting'")  # on the page first
    await js("document.getElementById('brainchat-close').click(); true")  # × holds it
    await wait_for(lambda: counting.state == "waiting")
    await brain.countdown.tick()
    assert sent_by_the_brain(stack) == []  # nothing was sent unseen


@CHROME
async def test_x_keeps_the_brains_chat_closed_while_its_held_card_changes(stack):
    """The chat opens itself only for a card it hasn't shown yet: × holds a countdown, and the held card's change (and
    every broadcast after it) never reopens it. Ask AI shows the card again, and a countdown runs again."""
    from test_app_server import wait_for
    from test_delegation_pages import in_slot, open_panel, sent_by_the_brain, working_agent

    row = await working_agent(stack)
    brain = stack["brain"]
    js = await open_mission(stack)
    await open_panel(stack, js)
    counting = brain.give(row, "Compare the annual plans", "you")
    assert counting.state == "counting"
    assert await until(js, f"{in_slot(handoff_id=counting.id)}?.dataset.state === 'counting'")
    await js("document.getElementById('brainchat-close').click(); true")  # ×: the countdown holds
    await wait_for(lambda: counting.state == "waiting")
    await asyncio.sleep(1.5)  # past the held card's broadcast and the snapshots after it
    assert await js(f"{CHAT}.hidden") is True  # × kept it closed
    assert brain.visible() is False
    await brain.countdown.tick()
    assert sent_by_the_brain(stack) == []
    await js(f"{ASK}.click(); true")  # Ask AI: the held card shows again, and a countdown may run again
    assert await until(js, f"!{CHAT}.hidden && {in_slot(handoff_id=counting.id)}?.dataset.state === 'waiting'")
    await wait_for(brain.visible)
    assert brain.give(row, "Check the logos too", "you").state == "counting"


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


@CHROME
async def test_a_reconnect_or_a_click_on_the_chat_shown_never_reopens_it(stack):  # Task 2's carry: its card stays
    from test_talk import ask_typed, talk_script

    talk_script(stack, {"say": "Shall I start an agent on that?", "action": "start_agent"})
    js = await open_mission(stack)
    assert await until(js, MADE)
    await opened(js)
    await ask_typed(js, "check the shop")
    go = "document.querySelector('#talk-card .talk-go')"
    assert await until(js, f"!!{go}", 15)
    shown = await js(f"{CHAT}.dataset.chat")
    for ws in list(stack["server"]._sockets):  # the app's end of the line closes, and the page connects again
        await ws.close()
    assert await until(js, "document.getElementById('status').dataset.state !== 'connected'", 5)
    assert await until(js, "document.getElementById('status').dataset.state === 'connected'", 10)
    await asyncio.sleep(1)  # past the snapshot that follows the hello
    assert await js(f"{CHAT}.dataset.chat") == shown and await js(f"!!{go}")  # the same chat, its card still live
    await js("document.querySelector('#chat-history summary').click(); true")
    row = f"document.querySelector('#chat-list .chat-row[data-id=\"{shown}\"] .open')"
    assert await until(js, f"{row} !== null")
    await js(f"{row}.click(); true")  # History's row for the chat shown: nothing to reopen
    assert await until(js, "document.getElementById('chat-history').open === false")
    await asyncio.sleep(0.5)
    await js(f"{go}.click(); true")  # the app still holds its card: Start starts the agent
    assert await until(js, f"{station('a1')} !== null", 15)


def kept(stack, *ids):
    """Earlier runs' chats, one exchange each, titled by their id."""
    folder = stack["home"] / "brain" / "chats"
    folder.mkdir(parents=True, exist_ok=True)
    for one in ids:
        (folder / f"{one}.json").write_text(json.dumps({
            "id": one, "title": f"Chat {one}", "created": "2026-10-09T09:00:00+00:00",
            "updated": "2026-10-09T09:00:00+00:00",
            "exchanges": [{"said": "hello", "answer": "Hi.", "time": "2026-10-09T09:00:00+00:00"}]}),
            encoding="utf-8")
    return folder


HISTORY = "document.getElementById('chat-history')"
SUMMARY = "document.querySelector('#chat-history summary')"
FOCUSED = "document.activeElement"


@CHROME
async def test_history_keeps_the_keys_in_the_panel_and_esc_closes_the_list_first(stack):  # fix wave: 4 and 6
    from test_app_server import wait_for

    one, two = "c" + "1" * 16, "c" + "2" * 16
    folder = kept(stack, one, two)
    js = await open_mission(stack)
    await front(stack, js)
    assert await until(js, MADE)
    await opened(js)
    await click(stack, js, "#chat-history summary")
    assert await until(js, f"{HISTORY}.open && document.querySelectorAll('#chat-list .chat-row').length === 2")
    await tap(stack, js, ESCAPE)  # Esc with the list open: the list closes, the panel stays
    assert await until(js, f"!{HISTORY}.open && {FOCUSED} === {SUMMARY}")
    assert await js(f"{CHAT}.hidden") is False
    await tap(stack, js, ESCAPE)  # a second Esc: the panel closes
    assert await until(js, f"{CHAT}.hidden")
    await opened(js)
    await click(stack, js, "#chat-history summary")
    assert await until(js, f"document.querySelector('#chat-list .chat-row[data-id=\"{one}\"]') !== null")
    await click(stack, js, f"#chat-list .chat-row[data-id=\"{one}\"] .open")  # reopened: the cursor in its box
    assert await until(js, f"{CHAT}.dataset.chat === {json.dumps(one)} && {FOCUSED}.id === 'talk-text'")
    await click(stack, js, "#chat-history summary")
    row = f"#chat-list .chat-row[data-id=\"{two}\"]"
    assert await until(js, f"document.querySelector({json.dumps(row)}) !== null")
    await click(stack, js, f"{row} .delete")
    assert await until(js, "document.querySelector('dialog.confirm')?.open === true")
    await click(stack, js, "dialog.confirm .go")
    await wait_for(lambda: not (folder / f"{two}.json").exists())
    assert await until(js, f"{FOCUSED} === {SUMMARY}")  # deleted: the keys stay on History, never on the page
    assert await js(f"{CHAT}.dataset.chat") == one
    await tap(stack, js, SPACE, " ")  # Space on History: never a talk with the Brain
    await asyncio.sleep(0.5)
    assert await js("document.getElementById('talk-status').textContent") == ""
    assert await js(f"{LOG}.querySelectorAll('li').length") == 2  # the reopened chat's two lines, nothing more
    await tap(stack, js, ENTER, "\r")  # Enter opens History: the keys are there
    assert await until(js, f"{HISTORY}.open")


@CHROME
async def test_a_chat_gone_meanwhile_says_so(stack):  # fix wave: 5 (and 4: the keys back on History)
    gone = "c" + "3" * 16
    folder = kept(stack, gone)
    js = await open_mission(stack)
    await front(stack, js)
    assert await until(js, MADE)
    await opened(js)
    shown = await js(f"{CHAT}.dataset.chat")
    await click(stack, js, "#chat-history summary")
    row = f"#chat-list .chat-row[data-id=\"{gone}\"] .open"
    assert await until(js, f"document.querySelector({json.dumps(row)}) !== null")
    (folder / f"{gone}.json").unlink()  # deleted meanwhile (another window)
    await click(stack, js, row)
    assert await until(js, "document.getElementById('talk-notice').textContent === 'That chat is gone'")
    assert await until(js, f"{FOCUSED} === {SUMMARY}")
    assert await js(f"{CHAT}.dataset.chat") == shown


# ---- final fix wave: the Agents page's settings, a drawer over a counting card, History over a fresh card ------------

def panel_hit(node):
    """True when a click in the middle of `node` lands inside the Agents page's settings panel."""
    return (f"(() => {{ const r = {node}.getBoundingClientRect();"
            " return document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)?.closest('#agent-panel')"
            " === document.getElementById('agent-panel'); })()")


@CHROME
@pytest.mark.parametrize("width, height", [(1440, 900), (1280, 760), (1100, 800), (800, 700)])
async def test_the_brains_chat_never_covers_an_agents_settings(stack, width, height):  # final review: Important 1
    saved = stack["server"].saved.save({"name": "Research", "web": "brave", "model": "opus"})
    js = await open_with(stack, size=(width, height))
    await front(stack, js)
    await js("document.querySelector('.page-link[data-page=\"agents\"]').click(); true")
    card = f"document.querySelector('#page-agents .agent-card[data-slug={json.dumps(saved.slug)}]')"
    assert await until(js, f"{card} !== null")
    await js(f"{card}.click(); true")
    panel = "document.getElementById('agent-panel')"
    assert await until(js, f"!{panel}.hidden && {panel}.querySelector('.save-agent') !== null")
    await opened(js)
    assert await js(panel_hit(f"{panel}.querySelector('.save-agent')"))  # its Save: the panel, never the chat
    assert await js(panel_hit(panel))  # and its middle


@CHROME
async def test_under_900_px_a_drawer_over_the_chat_holds_its_countdown(stack):  # final review: Important 2
    from test_app_server import wait_for
    from test_delegation_pages import in_slot, sent_by_the_brain, working_agent
    from test_mission import open_drawer

    row = await working_agent(stack)
    brain = stack["brain"]
    js = await open_with(stack, size=(800, 700))
    await front(stack, js)
    assert await until(js, f"{station('a1')} !== null")
    await opened(js)
    await wait_for(brain.visible)
    counting = brain.give(row, "Compare the annual plans", "you")
    assert counting.state == "counting"
    assert await until(js, f"{in_slot(handoff_id=counting.id)}?.dataset.state === 'counting'")
    await js(open_drawer("a1"))  # the drawer opens over the chat: the card can't be read
    assert await until(js, "!document.getElementById('drawer').hidden")
    await wait_for(lambda: counting.state == "waiting")  # so it holds, and waits for Send
    assert brain.visible() is False
    await brain.countdown.tick()
    assert sent_by_the_brain(stack) == []
    await js("document.getElementById('drawer-close').click(); true")
    await wait_for(brain.visible)  # the drawer closed: the chat's cards are seen again


@CHROME
async def test_after_the_app_restarts_a_card_with_a_reused_id_opens_the_chat(stack):  # final review: Minor 2
    brain = stack["brain"]
    js = await open_mission(stack)
    first = brain.suggest("Research Globex's prices", "gmail")
    assert first.id == "h1" and await until(js, f"!{CHAT}.hidden")
    await js("document.getElementById('brainchat-close').click(); true")
    assert await until(js, f"{CHAT}.hidden")
    brain.handoffs.clear()  # the app restarts: its hand-off ids start again at h1
    brain._handoff_seq = 0
    for ws in list(stack["server"]._sockets):
        await ws.close()
    assert await until(js, "document.getElementById('status').dataset.state !== 'connected'", 5)
    assert await until(js, "document.getElementById('status').dataset.state === 'connected'", 10)
    await asyncio.sleep(0.5)  # past the snapshot that follows the hello
    assert brain.suggest("Check the logos too", "gmail").id == "h1"
    assert await until(js, f"!{CHAT}.hidden")  # a new card: the chat opens for it


@CHROME
async def test_a_fresh_card_closes_historys_list(stack):  # final review: Minor 1
    js = await open_mission(stack)
    assert await until(js, MADE)
    await opened(js)
    await js(f"{SUMMARY}.click(); true")
    assert await until(js, f"{HISTORY}.open")
    stack["brain"].suggest("Research Globex's prices", "gmail")
    assert await until(js, "document.querySelector('#brainchat #handoff .handoff') !== null")
    assert await until(js, f"!{HISTORY}.open")  # the list never covers the card
