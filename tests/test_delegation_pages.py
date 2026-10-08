"""The brain-delegation spec's pages: Templates gone from Mission Control (2), Ask AI's fading history (3), Settings →
Brain's checkboxes and switch (4) and the Brain's hand-off cards (5). Against a real app server (agents on the fake
claude) in a throwaway headless Chrome. Every word stays text."""

import asyncio
import json

import pytest

from ai_browser.chrome import chrome_binary
from test_brain_handoffs import Clock
from test_home import HOSTILE, home, stack, until  # noqa: F401  (fixtures)
from test_mission import WORKING, open_mission, open_with

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


# ---- Templates leave Mission Control (spec 2) ------------------------------------------------------------------------

@CHROME
async def test_templates_leave_mission_control_and_the_calendar_opens_ai_home(stack):
    server = stack["server"]
    stack["workflows"].save({"name": "Morning report", "instructions": "Write it", "trigger": "schedule",
                             "schedule": "daily 09:00"})
    research = server.workspaces.create("Research")
    server.workspaces.assign_template("morning-report", research["id"])
    js = await open_mission(stack)
    assert await js("[...document.querySelectorAll('.modes [data-mode]')].map(tab => tab.textContent.trim())") == [
        "Ask AI", "Build a Mission"]  # no Use a Template
    assert await js("document.getElementById('task-template') === null && document.getElementById('page-templates')"
                    " === null && document.querySelector('.page-link[data-page=\"templates\"]') === null")
    pick = "document.querySelector('#workspaces .workspace-pick')"
    assert await until(js, f"{pick}?.querySelector('.count').textContent === '1'")  # it still counts its template
    await js("document.querySelector('#views-switch [data-view=\"calendar\"]').click(); true")
    entry = "document.querySelector('#view-calendar .entry.template')"
    assert await until(js, f"{entry} !== null")  # the Calendar still shows the scheduled template
    await js(f"{entry}.click(); true")
    assert await until(js, "location.pathname === '/home' && location.hash === '#workflows-section'"
                           " && document.getElementById('workflows-section').open === true")


# ---- Ask AI's history (spec 3) ---------------------------------------------------------------------------------------

LOG = "document.getElementById('talk-log')"
PANEL = "document.getElementById('talk')"
CENTRE = (f"(() => {{ const r = {LOG}.getBoundingClientRect();"
          " return [r.left + r.width / 2, r.top + r.height / 2]; })()")
ZOOM = "document.querySelector('.room').style.transform"
RECT = f"(() => {{ const r = {PANEL}.getBoundingClientRect(); return [r.left + r.width / 2, r.top, r.height]; }})()"


@CHROME
async def test_ask_ai_keeps_this_runs_talk_fading_upwards_and_solid_on_hover(stack):
    from test_talk import talk_script

    talk_script(stack, {"say": f"Noted {HOSTILE}", "action": "none"})
    js = await open_with(stack, size=(1440, 900))
    await js("document.getElementById('mode-ask').click(); true")
    for number in range(8):  # 16 lines: more than the 6 the talk kept before
        await js(f"document.getElementById('task').value = 'question {number}';"
                 " document.getElementById('start').click(); true")
        assert await until(js, f"{LOG}.querySelectorAll('li.brain').length === {number + 1}", 15)
    assert await js(f"{LOG}.children.length") == 16
    assert await js(f"{LOG}.firstElementChild.textContent") == "You: question 0"
    assert await js(f"{LOG}.querySelector('img') === null && document.title !== 'pwned'")  # text only
    style = f"getComputedStyle({LOG})"
    assert "linear-gradient" in await js(f"{style}.maskImage || {style}.webkitMaskImage")  # it fades upwards
    assert await js(f"{style}.overflowY") == "hidden"
    assert await js(f"getComputedStyle({PANEL}).backgroundColor") == "rgba(0, 0, 0, 0)"  # the office shows through
    assert await js(f"{LOG}.scrollHeight > {LOG}.clientHeight"
                    f" && Math.abs({LOG}.scrollTop + {LOG}.clientHeight - {LOG}.scrollHeight) <= 1")  # newest in view
    cdp, session = stack["cdp"], js.session
    left, top, height = await js(RECT)
    assert height < await js("innerHeight * 0.2")  # the idle strip is short: it doesn't cover the office
    above = f"document.elementFromPoint({left}, {top - 10})"
    assert await js(f"{above}.closest('.viewport') !== null && {above}.closest('#talk') === null")
    zoom = await js(ZOOM)
    await cdp.send("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": left, "y": top - 10, "deltaX": 0,
                                                "deltaY": -400}, session_id=session)
    assert await until(js, f"{ZOOM} !== {json.dumps(zoom)}")  # the wheel just above the strip zooms the office
    assert await js(f"{style}.overflowY") == "hidden" and await js(f"{LOG}.scrollTop > 0")  # and not the history
    x, y = await js(CENTRE)
    await cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y}, session_id=session)
    assert await until(js, f"{style}.overflowY === 'auto'")  # hovered: solid, and it scrolls
    assert await js(RECT + "[2]") > height and await js(RECT + "[1]") < top  # it grew upwards, under the pointer
    assert await js(f"({style}.maskImage || {style}.webkitMaskImage) === 'none'")
    assert await js(f"getComputedStyle({PANEL}).backgroundColor") != "rgba(0, 0, 0, 0)"
    zoom, bottom = await js(ZOOM), await js(f"{LOG}.scrollTop")
    await cdp.send("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": x, "y": y, "deltaX": 0, "deltaY": -400},
                   session_id=session)
    assert await until(js, f"{LOG}.scrollTop < {bottom}")  # over the strip the wheel scrolls the history
    assert await js(ZOOM) == zoom  # and the office stays as it was
    await cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 5, "y": 5}, session_id=session)
    assert await until(js, f"{style}.overflowY === 'hidden'")  # faded again
    page = "document.querySelector('.page-link[data-page=\"%s\"]').click(); true"
    await js(page % "history")  # the composer goes, and comes back with the newest line in view
    assert await until(js, "document.getElementById('composer').hidden")
    await js(page % "dashboard")
    assert await until(js, f"Math.abs({LOG}.scrollTop + {LOG}.clientHeight - {LOG}.scrollHeight) <= 1")


@CHROME
async def test_an_empty_history_takes_no_space_and_a_click_on_it_leaves_space_to_talking(stack):
    from test_talk import SPACE, eventually, mic, mouse, open_talk, talk, talk_script, tap

    talk_script(stack, {"say": "Noted", "action": "none"})
    js = await open_talk(stack, mic())
    await tap(stack, js, SPACE, " ")  # too short: "Hold Space while you talk", and the panel shows with no lines
    assert await until(js, "document.getElementById('talk-notice').textContent === 'Hold Space while you talk'")
    assert await js(f"{PANEL}.hidden") is False and await js(f"getComputedStyle({LOG}).display") == "none"
    await js("document.getElementById('task').value = 'hello'; document.getElementById('start').click(); true")
    assert await until(js, f"{LOG}.querySelectorAll('li.brain').length === 1", 15)
    assert await js(f"getComputedStyle({LOG}).display") != "none"
    await mouse(stack, js, "#talk-log", "mousePressed")  # a real click on the history
    await mouse(stack, js, "#talk-log", "mouseReleased")
    assert await js(f"document.activeElement === {LOG}")
    await talk(stack, js)  # the log has the focus, and Space still talks
    assert await eventually(lambda: len(stack["engine"].heard) == 1)
    await stack["cdp"].send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 5, "y": 5},
                            session_id=js.session)
    assert await until(js, f"getComputedStyle({PANEL}).backgroundColor === 'rgba(0, 0, 0, 0)'")  # a click pins nothing
    await js(f"{LOG}.blur(); {LOG}.focus(); true")  # but the keyboard's focus keeps it solid
    assert await until(js, f"getComputedStyle({PANEL}).backgroundColor !== 'rgba(0, 0, 0, 0)'")


@CHROME
async def test_the_floating_chat_keeps_six_lines(stack):
    from test_chat_page import open_chat
    from test_talk import ask_typed, eventually, talk_calls, talk_script

    talk_script(stack, {"say": "Noted", "action": "none"})
    js, _ = await open_chat(stack)
    for number in range(4):  # 8 lines asked for
        await ask_typed(js, f"question {number}")
        assert await eventually(lambda: len(talk_calls(stack)) == number + 1)
        assert await until(js, f"{LOG}.lastElementChild.classList.contains('brain')", 15)
    assert await js(f"{LOG}.children.length") == 6
    assert await js(f"{LOG}.firstElementChild.textContent") == "You: question 1"


# ---- Settings → Brain: what the Brain listens to, and the hand-off switch (spec 4 and 5) -------------------------

SOURCES = "[...document.querySelectorAll('#brain-sources input[data-source]')]"


@CHROME
async def test_settings_brain_checks_what_the_brain_listens_to_and_keeps_it(stack):
    from test_home import open_settings

    server = stack["server"]
    settings = await open_settings(stack)
    assert await until(settings, f"{SOURCES}.length === 6")
    boxes = f"{SOURCES}.map(box => [box.dataset.source, box.checked, box.parentElement.textContent.trim()])"
    assert await settings(boxes) == [["agents", True, "Agents' chats and results"], ["gmail", True, "Gmail"],
                                ["slack", True, "Slack"], ["asana", True, "Asana"],
                                ["pages", True, "Watched page parts"], ["chat", True, "The floating chat"]]
    assert await settings("document.getElementById('auto-hand').checked") is True  # on by default
    assert await settings("document.getElementById('read-tabs').checked") is False  # today's switch: as it was
    await settings("document.querySelector('#brain-sources input[data-source=\"gmail\"]').click();"
                   "document.querySelector('#brain-sources input[data-source=\"chat\"]').click(); true")
    for _ in range(50):
        if server.settings.get()["brain_sources"]["chat"] is False:
            break
        await asyncio.sleep(0.1)
    assert server.settings.get()["brain_sources"] == {"agents": True, "gmail": False, "slack": True, "asana": True,
                                                      "pages": True, "chat": False}
    assert server.brain.listens("gmail") is False and server.brain.listens("slack") is True  # at once
    await settings("document.getElementById('auto-hand').click(); true")
    for _ in range(50):
        if server.settings.get()["auto_hand"] is False:
            break
        await asyncio.sleep(0.1)
    assert server.settings.get()["auto_hand"] is False
    again = await open_settings(stack)  # kept: a page opened later reads them back
    assert await until(again, f"{SOURCES}.length === 6 && {SOURCES}.filter(box => !box.checked)"
                              ".map(box => box.dataset.source).join() === 'gmail,chat'")
    assert await again("document.getElementById('auto-hand').checked") is False


# ---- the Brain's hand-off cards (spec 5) -----------------------------------------------------------------------------

SLOT = "document.querySelector('#handoff .handoff')"
IN_SLOT = "[...document.querySelectorAll('#handoff .handoff')]"


async def working_agent(stack, name="Find Acme's prices"):
    """Agent 1, at work (it stays so), and the Brain's countdown on the test's clock: its row, as the Brain reads it."""
    from test_app_server import wait_for

    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    stack["brain"].countdown = Clock()
    agents = stack["server"].agents
    await agents.create("Find Acme's prices and plans", name=name)
    await wait_for(lambda: agents.agents["a1"].state == "working")
    return next(row for row in agents.snapshot()["agents"] if row["id"] == "a1")


def sent_by_the_brain(stack):
    return [event["text"] for event in stack["server"].agents.events_of("a1")
            if event.get("type") in ("queued", "user") and str(event.get("text", "")).startswith("From the Brain:")]


@CHROME
async def test_a_countdown_card_shows_by_the_globe_and_cancel_stops_it(stack):
    row = await working_agent(stack, name=f"Prices {HOSTILE}")
    js = await open_mission(stack)
    handoff = stack["brain"].give(row, f"Compare the annual plans {HOSTILE}", "you")
    assert await until(js, f"{SLOT}?.dataset.state === 'counting'")
    assert await js(f"{SLOT}.querySelector('.handoff-head').textContent") == f"Giving 1 · Prices {HOSTILE}:"
    assert await js(f"{SLOT}.querySelector('.handoff-words').textContent") == f"Compare the annual plans {HOSTILE}"
    assert await js(f"{SLOT}.querySelector('.handoff-from').textContent") == "From your words"
    assert (await js(f"{SLOT}.querySelector('.handoff-line').textContent")).startswith("Sends in 1")  # 15 or 14 s
    assert await js(f"[...{SLOT}.querySelectorAll('button')].map(button => button.textContent)") == [
        "Send now", "Cancel"]
    assert await js("document.querySelectorAll('img[src=x]').length === 0 && document.title !== 'pwned'")
    await js(f"{SLOT}.querySelector('.handoff-cancel').click(); true")
    assert await until(js, f"{SLOT}?.querySelector('.handoff-line').textContent === 'Cancelled: nothing was sent'")
    await stack["brain"].countdown.tick()
    assert handoff.state == "cancelled" and sent_by_the_brain(stack) == []
    stack["brain"].countdown = Clock()
    stack["brain"].give(row, "Compare the logos", "agent")  # an agent's result waits for Send (2026-10-08)
    assert await until(js, f"{SLOT}?.dataset.state === 'waiting'")
    assert await js(f"{SLOT}.querySelector('.handoff-from').textContent") == "From an agent's result"
    assert await js(f"{SLOT}.querySelector('.handoff-line').textContent") == "Waiting for your Send"  # no countdown
    assert await js(f"[...{SLOT}.querySelectorAll('button')].map(button => button.textContent)") == ["Send", "Cancel"]
    stack["brain"].give(row, "Reply to Maria with the prices", "gmail")  # the newest waiting one shows
    assert await until(js, f"{SLOT}?.querySelector('.handoff-words').textContent === 'Reply to Maria with the prices'")
    stack["brain"].give(row, "Check the logos too", "you")  # one counting down shows first
    assert await until(js, f"{SLOT}?.querySelector('.handoff-words').textContent === 'Check the logos too'")
    stack["brain"].give(row, "Check the fonts too", "you")  # and every one counting down shows: none counts unseen
    words = f"{IN_SLOT}.map(card => card.querySelector('.handoff-words').textContent)"
    assert await until(js, f"JSON.stringify({words}) === '[\"Check the fonts too\",\"Check the logos too\"]'")
    assert await js(f"{IN_SLOT}.every(card => card.dataset.state === 'counting'"
                    " && card.querySelector('.handoff-line').textContent.startsWith('Sends in 1'))")
    await js("document.getElementById('brain').click(); true")  # the Brain's inbox lists them all, newest first
    states = "[...document.querySelectorAll('#drawer .brain-handoffs .handoff')].map(card => card.dataset.state)"
    assert await until(js, f"JSON.stringify({states})"
                           " === '[\"counting\",\"counting\",\"waiting\",\"waiting\",\"cancelled\"]'")


@CHROME
async def test_send_now_sends_the_words_shown_and_the_chat_says_from_the_brain(stack):
    row = await working_agent(stack)
    js = await open_mission(stack)
    stack["brain"].give(row, "Compare the annual plans", "you")
    assert await until(js, f"{SLOT}?.dataset.state === 'counting'")
    await js(f"{SLOT}.querySelector('.handoff-go').click(); true")
    assert await until(js, f"{SLOT}?.querySelector('.handoff-line').textContent === 'Sent to agent 1'")
    assert sent_by_the_brain(stack) == ["From the Brain: Compare the annual plans"]  # exactly the card's words
    await js("document.querySelector('.station[data-id=\"a1\"]').click();"
             " document.getElementById('current-chat').click(); true")
    assert await until(js, "[...document.querySelectorAll('#drawer .msg.user')]"
                           ".some(node => node.textContent === 'From the Brain: Compare the annual plans')")
    assert await until(js, f"document.getElementById('handoff').hidden === true", 10)  # gone from the globe after


@CHROME
async def test_an_emails_handoff_waits_for_send_in_ai_home(home):
    js, stack = home
    row = await working_agent(stack)
    stack["brain"].give(row, "Reply to Maria with the new prices", "gmail", item="gmail:t1")
    card = "document.querySelector('#brain .brain-handoffs .handoff')"
    assert await until(js, f"{card}?.dataset.state === 'waiting'")
    assert await js(f"{card}.querySelector('.handoff-line').textContent") == "Waiting for your Send"  # no countdown
    assert await js(f"{card}.querySelector('.handoff-from').textContent") == "From an email in Gmail"
    assert await js(f"[...{card}.querySelectorAll('button')].map(button => button.textContent)") == ["Send", "Cancel"]
    await stack["brain"].countdown.tick()
    assert sent_by_the_brain(stack) == []  # it waits, however long
    await js(f"{card}.querySelector('.handoff-go').click(); true")
    assert await until(js, f"{card}?.dataset.state === 'sent'")
    assert sent_by_the_brain(stack) == ["From the Brain: Reply to Maria with the new prices"]


@CHROME
async def test_the_floating_chats_words_count_down_on_its_own_card(stack):
    from test_chat_page import open_chat
    from test_talk import talk_script

    await working_agent(stack, name="Fix the footer")
    talk_script(stack, {"say": "OK.", "action": "message_agent", "agent": "a1"})
    chat, _ = await open_chat(stack)
    await chat("document.getElementById('talk-text').value = 'tell agent 1 to check the header too';"
               " document.getElementById('talk-form').requestSubmit(); true")
    card = "document.querySelector('#handoff .handoff')"
    assert await until(chat, f"{card}?.dataset.state === 'counting'", 15)
    assert await chat(f"{card}.querySelector('.handoff-words').textContent") == "tell agent 1 to check the header too"
    said = ("Brain: Giving your words to 1 · Fix the footer in 15 seconds. Press Cancel on its card, or say no, to "
            "stop it.")
    log = "[...document.querySelectorAll('#talk-log li')].map(li => li.textContent)"
    assert await until(chat, f"{log}.includes({json.dumps(said)})")
    await chat(f"{card}.querySelector('.handoff-cancel').click(); true")
    assert await until(chat, f"{card}?.querySelector('.handoff-line').textContent === 'Cancelled: nothing was sent'")
    assert sent_by_the_brain(stack) == []
