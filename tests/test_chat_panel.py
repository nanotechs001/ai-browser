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
