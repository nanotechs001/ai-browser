"""The brain-delegation spec's pages: Templates gone from Mission Control (2), Ask AI's fading history (3), Settings →
Brain's checkboxes and switch (4) and the Brain's hand-off cards (5). Against a real app server (agents on the fake
claude) in a throwaway headless Chrome. Every word stays text."""

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
    x, y = await js(CENTRE)
    await cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y}, session_id=session)
    assert await until(js, f"{style}.overflowY === 'auto'")  # hovered: solid, and it scrolls
    assert await js(f"({style}.maskImage || {style}.webkitMaskImage) === 'none'")
    assert await js(f"getComputedStyle({PANEL}).backgroundColor") != "rgba(0, 0, 0, 0)"
    zoom, bottom = await js(ZOOM), await js(f"{LOG}.scrollTop")
    await cdp.send("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": x, "y": y, "deltaX": 0, "deltaY": -400},
                   session_id=session)
    assert await until(js, f"{LOG}.scrollTop < {bottom}")  # the wheel scrolls the history
    assert await js(ZOOM) == zoom  # and never the office
    await cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 5, "y": 5}, session_id=session)
    assert await until(js, f"{style}.overflowY === 'hidden'")  # faded again
