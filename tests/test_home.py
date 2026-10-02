"""AI Home, the extension worker, tab groups and the `ai` keyword: the extension in a throwaway headless AI Browser,
talking to a real app server (agents run the fake claude)."""

import asyncio
import contextlib
import json

import httpx
import pytest

from ai_browser.cdp import CDPError
from ai_browser.chrome import chrome_binary
from test_bridge import EVENTS

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
HOSTILE = '<img src=x onerror="document.title=\'pwned\'"> shop'


async def evaluate(cdp, session, expression):
    result = await cdp.send("Runtime.evaluate", {"expression": expression, "returnByValue": True,
                                                 "awaitPromise": True}, session_id=session)
    return result.get("result", {}).get("value")


async def until(js, expression, seconds=8):
    for _ in range(int(seconds * 10)):
        with contextlib.suppress(CDPError):
            if await js(expression):
                return True
        await asyncio.sleep(0.1)
    return False


async def open_page(cdp, url, background=False):
    """(target, js) for a new tab showing `url`, once it has left about:blank."""
    params = {"url": url, **({"background": True} if background else {})}
    target = (await cdp.send("Target.createTarget", params))["targetId"]
    session = (await cdp.send("Target.attachToTarget", {"targetId": target, "flatten": True}))["sessionId"]

    async def js(expression):
        return await evaluate(cdp, session, expression)

    await until(js, "location.protocol !== 'about:' && document.readyState === 'complete'")
    return target, js


@pytest.fixture
async def stack(fake_claude, tmp_path):
    """A real app server (agents on the fake claude), a headless AI Browser with the extension, the TabWatch."""
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer
    from ai_browser.app.tabs import TabWatch
    from ai_browser.appbrowser import launch_app_browser, prepare_extension
    from ai_browser.brain.service import BrainService
    from ai_browser.brain.store import BrainStore
    from ai_browser.cdp import CDP

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS))
    home = tmp_path / "home"
    agents = AgentManager(home, claude=str(runner))
    from ai_browser.brain.skillwriter import SkillWriter
    from ai_browser.brain.tools import ToolsConfig
    from ai_browser.brain.workflows import WorkflowRunner, WorkflowStore

    brain = BrainService(BrainStore(home), agents, claude=str(runner))
    from ai_browser.hearing.service import HearingService
    from fake_engine import FakeEngine, tiny_store

    engine = FakeEngine(answers=["what is fix the footer doing"])
    hearing = HearingService(tiny_store(home / "models"), engine)  # talking is ready: the tiny model is in place
    workflows = WorkflowStore(home)
    tools = ToolsConfig(home, claude_home=tmp_path / "user")  # the tests that use it write a configuration there
    skills = SkillWriter(tmp_path / "user" / ".claude" / "skills", claude=str(runner), cwd=tmp_path / "calls")
    server = AppServer(home, agents, brain=brain, workflows=workflows, runner=WorkflowRunner(workflows, agents),
                       tools=tools, skill_writer=skills, hearing=hearing)
    url = await server.start()
    folder = prepare_extension(home, url, server.token)
    app = launch_app_browser(tmp_path / "profile", folder, headless=True)
    server.allow_origin(f"chrome-extension://{app.extension_id}")
    watch = TabWatch(app.ws_url, app.extension_id)
    await watch.start()
    server.attach_tabs(watch)
    agents.close_tabs = watch.close_targets
    cdp = await CDP.connect(app.ws_url)
    state = {"server": server, "app": app, "cdp": cdp, "url": url, "folder": folder, "home": home, "log": log,
             "runner": runner, "script": script, "brain": brain, "workflows": workflows, "tools": tools,
             "hearing": hearing, "engine": engine, "user": tmp_path / "user"}
    yield state
    await cdp.close()
    await watch.close()
    await state["server"].stop()
    app.close()


@pytest.fixture
async def home(stack):
    """(js in AI Home, js in the extension's worker, stack)."""
    app, cdp = stack["app"], stack["cdp"]
    _, js = await open_page(cdp, f"chrome-extension://{app.extension_id}/home.html")
    worker_session = None
    for _ in range(50):
        workers = [t for t in (await cdp.send("Target.getTargets"))["targetInfos"]
                   if t["type"] == "service_worker" and app.extension_id in t["url"]]
        if workers:
            worker_session = (await cdp.send("Target.attachToTarget", {"targetId": workers[0]["targetId"],
                                                                       "flatten": True}))["sessionId"]
            break
        await asyncio.sleep(0.1)
    assert worker_session, "the extension's worker is not running"

    async def worker_js(expression):
        return await evaluate(cdp, worker_session, expression)

    assert await until(js, "document.getElementById('status').dataset.state === 'connected'")
    return js, worker_js, stack


async def post_tab(stack, agent, kind, target):
    async with httpx.AsyncClient() as client:
        await client.post(stack["url"] + "/agent-events", headers={"X-AIB-Agent-Token": stack["server"].agent_token},
                          json={"agent": agent, "kind": kind, "target": target, "adopted": False})


@CHROME
async def test_ai_home_shows_agents_tabs_and_skills_as_text(home):
    js, _, stack = home
    await stack["server"].agents.create(HOSTILE)
    assert await until(js, "document.querySelectorAll('#agents .agent').length === 1")
    assert "<img" in await js("document.querySelector('#agents .agent .name').textContent")
    assert await js("document.querySelectorAll('#agents img:not(.thumb)').length") == 0
    assert await js("document.title") != "pwned"
    assert await until(js, "/\\d/.test(document.querySelector('#skills .count').textContent)")
    _, _ = await open_page(stack["cdp"], "data:text/html,<title>Shop page</title>", background=True)
    assert await until(js, "document.getElementById('tabs').textContent.includes('Shop page')")


@CHROME
async def test_a_task_starts_once_from_ai_home(home):
    js, _, stack = home
    await js("document.getElementById('task').value = 'check the shop'; "
             "document.getElementById('start').click(); document.getElementById('start').click(); true")
    assert await until(js, "document.querySelectorAll('#agents .agent').length === 1")
    await asyncio.sleep(1)
    assert len(stack["server"].agents.agents) == 1  # a double click makes one agent
    assert await until(js, "!document.getElementById('start').disabled")


@CHROME
async def test_the_address_bar_keyword_starts_a_task(home):
    _, worker_js, stack = home
    await worker_js("startTask('check example.com'); true")
    for _ in range(50):
        if stack["server"].agents.agents:
            break
        await asyncio.sleep(0.1)
    assert [agent.name for agent in stack["server"].agents.agents.values()] == ["check example.com"]


@CHROME
async def test_agent_tabs_are_grouped_once(home):
    js, _, stack = home
    page, _ = await open_page(stack["cdp"], "data:text/html,<title>Agent page</title>", background=True)
    agent = await stack["server"].agents.create("group me")
    await post_tab(stack, agent.id, "tab_opened", page)
    titles = "chrome.tabGroups.query({}).then(groups => groups.map(group => group.title))"
    assert await until(js, f"{titles}.then(names => names.includes('group me'))")
    tab_id = await js("chrome.tabs.query({}).then(tabs => tabs.find(tab => tab.title === 'Agent page').id)")
    await js(f"chrome.tabs.ungroup({tab_id}).then(() => true)")
    await post_tab(stack, agent.id, "working_tab", page)  # the agent keeps working there
    await asyncio.sleep(2)
    assert await js(f"chrome.tabs.get({tab_id}).then(tab => tab.groupId)") == -1  # the user's move stands


@CHROME
async def test_pages_reconnect_after_the_app_restarts(home):
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer

    js, _, stack = home
    await stack["server"].stop()
    assert await until(js, "document.getElementById('status').dataset.state !== 'connected'")
    agents = AgentManager(stack["home"], claude=str(stack["runner"]))
    server = AppServer(stack["home"], agents)
    url = await server.start()
    server.allow_origin(f"chrome-extension://{stack['app'].extension_id}")
    stack["server"] = server
    (stack["folder"] / "config.json").write_text(json.dumps({"server": url, "token": server.token}))
    await agents.create("after the restart")
    assert await until(js, "document.getElementById('status').dataset.state === 'connected'", 10)
    assert await until(js, "document.getElementById('agents').textContent.includes('after the restart')")


@CHROME
async def test_ai_home_is_the_new_tab_page(home):
    _, _, stack = home
    _, js = await open_page(stack["cdp"], "chrome://newtab/")
    assert await until(js, "!!document.getElementById('agents')")


@CHROME
async def test_rows_are_updated_in_place_so_clicks_land(home):
    js, _, stack = home
    stack["script"].write_text(json.dumps([EVENTS[0], {"sleep": 4}, *EVENTS[1:]]))  # it keeps working a while
    page, _ = await open_page(stack["cdp"], "data:text/html,<title>Some page</title>", background=True)
    agent = await stack["server"].agents.create("keep working")
    row = "#agents .agent[data-id='a1']"
    assert await until(js, f"!!document.querySelector(\"{row} .stop\") && "
                           "document.getElementById('tabs').textContent.includes('Some page')")
    await js(f"window.held = [document.querySelector(\"{row} .stop\"), document.querySelector('#tabs .tab')]; true")
    for n in range(3):  # each report changes the agent, and so its row
        await post_tab(stack, agent.id, "tab_opened", f"T{n}")
    await post_tab(stack, agent.id, "working_tab", page)
    await asyncio.sleep(0.5)
    assert await js("window.held.every(node => node.isConnected)")  # the same elements: a click can't be lost


@CHROME
async def test_ai_home_is_one_pinned_tab_in_front_after_a_start(home):
    js, worker_js, stack = home
    home_url = f"chrome-extension://{stack['app'].extension_id}/home.html"
    await js(f"chrome.tabs.create({{url: '{home_url}', pinned: true}}).then(() => true)")  # a restored duplicate
    await open_page(stack["cdp"], "data:text/html,<title>Restored tab</title>")  # in front, as after a restore
    await worker_js("ensureHome().then(() => true)")  # what the worker does when AI Browser starts
    homes = await js(f"chrome.tabs.query({{}}).then(tabs => tabs.filter(tab => (tab.url || tab.pendingUrl || '')"
                     f".startsWith('{home_url}')).map(tab => [tab.pinned, tab.active, tab.index]))")
    assert [tab for tab in homes if tab[0]] == [[True, True, 0]]  # one pinned AI Home, first and in front
