"""The AI's tabs (Decision 7): an agent's new tab is opened by the app (POST /agent-tab) in the profile where agents
browse, never among the user's windows, and it is that agent's alone from the start, with its row in AI Home and
Mission Control saying whose it is. In a throwaway headless Chrome, through the relay's one connection."""

import httpx
import pytest

from ai_browser.chrome import chrome_binary
from fake_brave import add_agent, until
from test_app_server import agent_headers, started
from test_bridge import EVENTS

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


async def window_of(cdp, target) -> int:
    return (await cdp.send("Browser.getWindowForTarget", {"targetId": target}))["windowId"]


@CHROME
async def test_an_agents_new_tab_opens_in_a_window_of_its_own_and_is_its_alone(fake_claude, throwaway_chrome,
                                                                                tmp_path):
    from ai_browser.app.bravelink import BraveLink
    from ai_browser.cdp import CDP
    from ai_browser.chrome import find_ws_url

    server, url = await started(fake_claude, tmp_path, EVENTS)
    brave = BraveLink(throwaway_chrome, every=0.1, tokens=server.tokens)
    server.attach_brave(brave)
    await brave.start()
    await brave.connect()
    own = await CDP.connect(find_ws_url(throwaway_chrome, timeout=20))  # the user, by hand: to look at windows
    try:
        user = next(info["targetId"] for info in (await own.send("Target.getTargets"))["targetInfos"]
                    if info["type"] == "page")
        add_agent(server.agents)
        assert await until(lambda: brave.agents_context()[0] is not None, 10)
        async with httpx.AsyncClient() as client:
            answer = (await client.post(url + "/agent-tab", headers=agent_headers(server), json={"agent": "a1"})).json()
        target = answer["target"]
        assert await window_of(own, target) != await window_of(own, user)  # never among the user's windows
        assert brave.relay.grants("a1", target) and not brave.relay.visible("a2", target)  # a1's alone
        assert await until(lambda: any(tab["target"] == target and tab["owner"].get("id") == "a1"
                                       for tab in brave.tabs()), 10)  # its row says whose it is
        assert brave.relay.upstream_opens == 1
    finally:
        await own.close()
        await server.stop()
        await brave.close()
