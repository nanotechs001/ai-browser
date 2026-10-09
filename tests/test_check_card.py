"""A bot check in AI Browser: the card in the floating chat and in Mission Control, with Show me, Continue and Skip
this site. Names, sites and words stay text; the buttons send only our own fixed messages."""

import asyncio
import json

import pytest

from ai_browser.chrome import chrome_binary
from test_home import HOSTILE, post_tab, stack, until  # noqa: F401  (fixtures)
from test_mission import WORKING, open_mission, station

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
REPORT = {"kind": "check", "check": "google", "site": "www.google.com", "target": "T1", "adopted": False}
LIVE = "http://127.0.0.1:8770/live?token=abc"


async def checked(stack, name="Flights to Manila", **report):
    """An agent at work whose engine reported a bot check (what /agent-events delivers)."""
    agents = stack["server"].agents
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    agent = await agents.create(name)
    report = {**REPORT, **report}
    agents.tab_event(agent.id, "tab_opened", report["target"], report["adopted"])
    agents.check_event(agent.id, report)
    return agent


def recorded(stack) -> list[tuple[str, str]]:
    """What the cards' buttons asked the app for (watch, check_continue, check_skip), recorded instead of done."""
    server, seen = stack["server"], []

    async def watch(target):
        seen.append(("watch", target))

    async def continue_check(agent_id):
        seen.append(("check_continue", agent_id))

    async def skip_check(agent_id):
        seen.append(("check_skip", agent_id))

    server.tabs.watch = watch
    server.agents.continue_check = continue_check
    server.agents.skip_check = skip_check
    return seen


async def heard(seen, expected, seconds=5) -> bool:
    for _ in range(int(seconds * 10)):
        if expected in seen:
            return True
        await asyncio.sleep(0.1)
    return False


@CHROME
async def test_mission_control_shows_a_bot_check_as_needs_you(stack):
    js = await open_mission(stack)
    seen = recorded(stack)
    agent = await checked(stack)
    assert await until(js, f"{station(agent.id)}?.dataset.state === 'needs_you'")
    assert await js(f"{station(agent.id, '.ticker')}.textContent") == "bot check · www.google.com"
    assert await until(js, "document.getElementById('bubble').textContent.includes("
                           "'Flights to Manila hit a bot check on www.google.com. It\\'s waiting for you')")
    assert "needs you" in await js("document.getElementById('counts').textContent")
    await js(f"{station(agent.id)}.click(); true")
    card = "document.querySelector('#drawer:not([hidden]) .bot-check')"
    assert await until(js, f"{card} !== null")
    assert await js("document.querySelector('#drawer .stop').hidden") is False
    await js(f"{card}.querySelector('.continue').click(); true")
    assert await heard(seen, ("check_continue", agent.id))
