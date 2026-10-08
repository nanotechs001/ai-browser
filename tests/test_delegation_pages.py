"""The brain-delegation spec's pages: Templates gone from Mission Control (2), Ask AI's fading history (3), Settings →
Brain's checkboxes and switch (4) and the Brain's hand-off cards (5). Against a real app server (agents on the fake
claude) in a throwaway headless Chrome. Every word stays text."""

import asyncio
import json

import pytest

from ai_browser.chrome import chrome_binary
from test_home import HOSTILE, stack, until  # noqa: F401  (fixtures)
from test_mission import open_mission, open_with

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
