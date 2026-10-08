"""The brain-delegation spec's pages: Templates gone from Mission Control (2), Ask AI's fading history (3), Settings →
Brain's checkboxes and switch (4) and the Brain's hand-off cards (5). Against a real app server (agents on the fake
claude) in a throwaway headless Chrome. Every word stays text."""

import json

import pytest

from ai_browser.chrome import chrome_binary
from test_home import stack, until  # noqa: F401  (fixtures)
from test_mission import open_mission

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
