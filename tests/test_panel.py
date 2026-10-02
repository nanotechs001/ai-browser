"""The chat beside the page: it follows the agent working in the current tab, or starts one there."""

import asyncio
import json

import pytest

from ai_browser.chrome import chrome_binary
from test_bridge import EVENTS
from test_home import HOSTILE, open_page, post_tab, stack, until  # noqa: F401 (stack is a fixture)

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


@pytest.fixture
async def panel(stack):  # noqa: F811
    """(js in the panel, the user's tab target, stack): the panel is opened in the background, as a side panel would be,
    so the user's page stays the tab in front."""
    cdp, app = stack["cdp"], stack["app"]
    for _ in range(50):  # the worker opens AI Home in front when it is installed: let that happen first
        if any("/home.html" in info["url"] for info in (await cdp.send("Target.getTargets"))["targetInfos"]):
            break
        await asyncio.sleep(0.1)
    user_tab, _ = await open_page(cdp, "data:text/html,<title>User page</title><h1>Hello</h1>")
    _, js = await open_page(cdp, f"chrome-extension://{app.extension_id}/panel.html", background=True)
    assert await until(js, "document.getElementById('status').dataset.state === 'connected'")
    return js, user_tab, stack


@CHROME
async def test_the_panel_follows_the_agent_of_the_current_tab(panel):
    js, user_tab, stack = panel
    assert await until(js, "document.getElementById('start-here') && !document.getElementById('start-here').hidden")
    agent = await stack["server"].agents.create("fix the header")
    await post_tab(stack, agent.id, "working_tab", user_tab)
    assert await until(js, "document.getElementById('agent-name').textContent === 'fix the header'")
    assert await until(js, "document.getElementById('messages').textContent.includes('fix the header')")


@CHROME
async def test_start_a_task_here_works_in_the_current_tab(panel):
    js, user_tab, stack = panel
    assert await until(js, "!document.getElementById('start-here').hidden")
    await js("document.getElementById('input').value = 'summarize this page'; "
             "document.getElementById('send').click(); true")
    assert await until(js, "document.getElementById('agent-name').textContent === 'summarize this page'")
    agents = list(stack["server"].agents.agents.values())
    assert len(agents) == 1 and agents[0].adopted == [user_tab]
    config = json.loads((stack["home"] / "app" / "agents" / agents[0].id / "mcp.json").read_text())
    assert config["mcpServers"]["ai-browser"]["env"]["AIB_APP_ADOPT"] == user_tab


@CHROME
async def test_replies_stay_text(panel):
    js, user_tab, stack = panel
    reply = {"type": "stream_event", "event": {"type": "content_block_delta",
                                               "delta": {"type": "text_delta", "text": "Sure " + HOSTILE}}}
    stack["script"].write_text(json.dumps([EVENTS[0], reply] + EVENTS[3:]))
    await js("document.getElementById('input').value = 'hi'; document.getElementById('send').click(); true")
    assert await until(js, "document.getElementById('messages').textContent.includes('click e5')")
    assert "<img" in await js("document.getElementById('messages').textContent")  # the planted markup is text...
    assert await js("document.querySelectorAll('#messages img').length") == 0  # ...never elements
    assert await js("document.title") != "pwned"
