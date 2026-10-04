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
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    home = tmp_path / "home"
    agents = AgentManager(home, claude=runner)
    from ai_browser.brain.skillwriter import SkillWriter
    from ai_browser.brain.tools import ToolsConfig
    from ai_browser.brain.workflows import WorkflowRunner, WorkflowStore

    brain = BrainService(BrainStore(home), agents, claude=runner)
    from ai_browser.hearing.service import HearingService
    from fake_engine import FakeEngine, tiny_store

    engine = FakeEngine(answers=["what is fix the footer doing"])
    hearing = HearingService(tiny_store(home / "models"), engine)  # talking is ready: the tiny model is in place
    workflows = WorkflowStore(home)
    tools = ToolsConfig(home, claude_home=tmp_path / "user")  # the tests that use it write a configuration there
    skills = SkillWriter(tmp_path / "user" / ".claude" / "skills", claude=runner, cwd=tmp_path / "calls")
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
        await client.post(stack["url"] + "/agent-events", headers={"X-AIB-Agent-Token": stack["server"].token_for(agent)},
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
    agents = AgentManager(stack["home"], claude=stack["runner"])
    server = AppServer(stack["home"], agents)
    url = await server.start()
    server.allow_origin(f"chrome-extension://{stack['app'].extension_id}")
    stack["server"] = server
    (stack["folder"] / "config.json").write_text(json.dumps({"server": url, "token": server.token}), encoding="utf-8")
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
    stack["script"].write_text(json.dumps([EVENTS[0], {"sleep": 4}, *EVENTS[1:]]),
                               encoding="utf-8")  # it keeps working a while
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


@CHROME
async def test_ai_browser_groups_nothing_when_agents_browse_in_brave(home):
    from fake_brave import FakeBrave

    js, _, stack = home
    stack["server"].attach_brave(FakeBrave([]))
    await asyncio.sleep(0.5)  # the worker hears that agents browse in Brave
    page, _ = await open_page(stack["cdp"], "data:text/html,<title>Agent page</title>", background=True)
    agent = await stack["server"].agents.create("group me")
    await post_tab(stack, agent.id, "tab_opened", page)
    await asyncio.sleep(2)
    assert await js("chrome.tabGroups.query({}).then(groups => groups.length)") == 0


CHIP = "(target => document.querySelector(`#tabs .tab[data-target='${target}'] .chip`)?.textContent)"


def in_row(target, selector):
    return f"document.querySelector(\"#tabs .tab[data-target='{target}'] {selector}\")"


@CHROME
async def test_the_tab_list_marks_owners_and_hands_tabs_over(home):
    from fake_brave import FakeBrave

    js, _, stack = home
    server = stack["server"]
    agent = await server.agents.create("Fix the footer")
    brave = FakeBrave([{"target": "T1", "url": "https://shop.example/cart", "title": "Agent page"},
                       {"target": "U1", "url": "https://mail.example/", "title": HOSTILE},
                       {"target": "U2", "url": "https://docs.example/", "title": "Docs"},
                       {"target": "S1", "url": "https://s.example/", "title": "Session page"},
                       {"target": "B1", "url": "https://mail.example/#t1", "title": "Thread"}])
    mine = {"id": agent.id, "name": agent.name, "color": agent.color}
    brave.owners.update({"T1": {"kind": "agent", **mine}, "U2": {"kind": "handed", **mine},
                         "S1": {"kind": "session", "id": "cc-x", "name": "Claude Code", "color": "orange"},
                         "B1": {"kind": "brain", "name": "Brain", "color": "purple"}})
    agent.adopted.append("U2")  # handed to it, as Hand over leaves it: only a handed tab can be taken back
    server.attach_brave(brave)
    assert await until(js, f"{CHIP}('T1') === 'Fix the footer'")
    assert await js(f"['S1', 'B1', 'U2', 'U1'].map({CHIP})") == ["Claude Code", "Brain", "handed to Fix the footer",
                                                                 "you"]
    assert "<img" in await js(f"{in_row('U1', '.title')}.textContent")  # a hostile title stays text
    assert await js("document.querySelectorAll('#tabs img').length") == 0 and await js("document.title") != "pwned"
    assert await js(f"[{in_row('U1', '.hand')}.hidden, {in_row('T1', '.hand')}.hidden, {in_row('B1', '.hand')}.hidden,"
                    f" {in_row('U2', '.take')}.hidden]") == [False, True, False, False]
    await js(f"{in_row('U1', '.hand')}.click(); true")
    assert "The agent will read this tab and act in it." in await js(f"{in_row('U1', '.menu')}.textContent")
    await js(f"{in_row('U1', f'.give[data-id={agent.id}]')}.click(); true")
    for _ in range(50):
        if "U1" in agent.adopted:
            break
        await asyncio.sleep(0.1)
    assert "U1" in agent.adopted
    await js(f"{in_row('U2', '.take')}.click(); true")
    assert await until(js, f"{CHIP}('U2') === 'you'")
    await js(f"{in_row('B1', '.hand')}.click(); true")
    await js(f"{in_row('B1', '.new')}.click(); true")  # New agent…: the next task starts in that tab
    assert await until(js, "document.getElementById('handing-text').textContent === 'Starts in your tab: Thread'")
    await js("document.getElementById('task').value = 'reply to it'; document.getElementById('start').click(); true")
    for _ in range(50):
        if len(server.agents.agents) == 2:
            break
        await asyncio.sleep(0.1)
    assert server.agents.agents["a2"].adopted == ["B1"]


LAST_USED = ("Showing the Brave profile you used last. With the watcher loaded, this list stays on the watcher's "
             "profile.")
NO_PROFILE = "Your tabs aren't listed: AI Browser can't tell which Brave profile is yours yet."


@CHROME
async def test_the_tab_list_counts_what_it_doesnt_show(home):
    from fake_brave import FakeBrave

    js, _, stack = home
    brave = FakeBrave([{"target": "U1", "url": "https://mail.example/", "title": "Mail"}])
    brave.set_scope("watcher", 3)
    stack["server"].attach_brave(brave)
    source = "document.querySelector('#tabs p.scope-source')?.textContent ?? null"
    count = "document.querySelector('#tabs p.elsewhere')?.textContent ?? null"
    empty = "document.querySelector('#tabs .empty')?.textContent ?? null"

    async def shows(expression, text):
        return await until(js, f"({expression}) === {json.dumps(text)}")

    assert await shows(count, "3 more tabs in other profiles or private windows: not shown here.")
    assert await js(source) is None
    brave.set_scope("watcher", 1)
    assert await shows(count, "1 more tab in other profiles or private windows: not shown here.")
    brave.set_scope("last_used", 0)
    assert await shows(source, LAST_USED)
    assert await js(count) is None  # no line when the count is 0
    brave.set_scope("none", 2)
    assert await shows(source, NO_PROFILE)
    assert await shows(count, "2 more tabs in other profiles or private windows: not shown here.")
    brave.set_scope("watcher", 0)
    assert await shows(source, None)
    assert await js(count) is None
    brave.pages = []
    brave.changed()
    assert await shows(empty, "No web pages open in this profile.")
    brave.set_scope("none", 4)  # Review Focus 1: while Brave isn't connected, the list claims nothing about profiles
    brave.set_state("ready")
    assert await shows(empty, "No web pages open in your browser.")
    assert await js(source) is None and await js(count) is None
    brave.set_state("connected")  # connected again: the scope sent before is stale until the new connection's list
    assert await until(js, "document.getElementById('browser-card').dataset.state === 'connected'")
    assert await js(source) is None and await js(count) is None
    assert await js(empty) == "No web pages open in your browser."
    brave.changed()  # the new connection's first list brings its own scope
    assert await shows(source, NO_PROFILE)
    assert await shows(count, "4 more tabs in other profiles or private windows: not shown here.")
    brave.set_scope("watcher", 0)
    assert await shows(source, None)
    await js("window.flashed = []; new MutationObserver(() => { const line = document.querySelector("
             "'#tabs p.scope-source'); if (line) window.flashed.push(line.textContent); }).observe("
             "document.getElementById('tabs'), {childList: true, subtree: true, characterData: true}); true")
    brave.tab_scope = {"profile": "none", "elsewhere": 0}  # BraveLink's scope once its connection is gone
    brave.state = "lost"  # Brave quits, in BraveLink's order: the state, then the empty list, then the card
    brave.changed()
    brave.set_state("lost")
    assert await until(js, "document.getElementById('browser-card').dataset.state === 'lost'")
    assert await js("window.flashed") == [] and await js(source) is None  # not even for a moment


@CHROME
async def test_while_brave_connects_ai_home_claims_no_profile(home, tmp_path):  # final review R1
    from ai_browser.app.bravelink import BraveLink
    from fake_brave import FakePort

    js, _, stack = home
    server, app = stack["server"], stack["app"]
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=[{"target": "U1", "url": "https://mail.example/", "title": "Mail"}])
    port.hold = {"Target.getBrowserContexts"}  # the tab list's first read waits: the moment right after Allow
    await port.start()
    brave = BraveLink(folder, every=0.1, tokens=server.tokens)
    server.attach_brave(brave)
    await brave.start()
    connecting = asyncio.ensure_future(brave.connect())
    source = "document.querySelector('#tabs p.scope-source')?.textContent ?? null"
    empty = "document.querySelector('#tabs .empty')?.textContent ?? null"
    try:
        for _ in range(100):
            if brave.state == "connected" and port.held:
                break
            await asyncio.sleep(0.05)
        _, late = await open_page(stack["cdp"], f"chrome-extension://{app.extension_id}/home.html")  # loads now
        assert await until(late, "document.getElementById('browser-card').dataset.state === 'connected'")
        assert await until(late, f"({empty}) !== null")  # its snapshot is drawn
        assert await late(source) is None and await late(empty) == "No web pages open in your browser."
        port.hold = set()
        await port.answer_held()
        await connecting
        assert await until(late, "document.querySelector(\"#tabs .tab[data-target='U1']\") !== null")
        assert await late(source) == LAST_USED  # the first list brings its scope (no watcher here)
        assert port.sessions == 1  # one connection: Brave asked "Allow remote debugging?" once
    finally:
        connecting.cancel()
        await brave.close()
        await port.stop()


@CHROME
async def test_the_browser_card_follows_brave(home):
    from fake_brave import FakeBrave

    js, _, stack = home
    brave = FakeBrave([], state="off")
    stack["server"].attach_brave(brave)
    title = "document.getElementById('browser-title').textContent"
    assert await until(js, f"{title} === 'Your Brave · switch off'")
    assert "brave://inspect/#remote-debugging" in await js("document.getElementById('browser-steps').textContent")
    assert await js("document.getElementById('browser-action').textContent") == "Show me how"
    assert "any program on this computer can reach your Brave" in await js(
        "document.getElementById('browser-warning').textContent")
    for state, words in (("ready", "Your Brave · ready"), ("asking", "Your Brave · waiting for Allow"),
                         ("refused", "Your Brave · not allowed"), ("lost", "Your Brave · closed")):
        brave.set_state(state)
        assert await until(js, f"{title} === {json.dumps(words)}")
    brave.set_state("ready")
    assert await until(js, "document.getElementById('browser-action').textContent === 'Connect'")
    await js("document.getElementById('browser-action').click(); true")
    for _ in range(50):
        if brave.connects:
            break
        await asyncio.sleep(0.1)
    assert brave.connects == 1
    brave.set_state("connected")
    assert await until(js, f"{title} === 'Your Brave · connected'")  # no watcher here: groups are off
    assert (await js("document.getElementById('browser-groups').textContent")).startswith(
        "Tab groups off: Load the watcher in Brave to group the AI's tabs")


@CHROME
async def test_ai_browser_mode_says_so(home):
    js, _, _ = home
    assert await until(js, "document.getElementById('browser-title').textContent === 'Agents browse in AI Browser'")


@CHROME
async def test_ai_home_lists_connected_clients_with_disconnect(home):
    from fake_brave import FakeBrave

    js, _, stack = home
    brave = FakeBrave([], state="connected")
    stack["server"].attach_brave(brave)
    rows = [
        {"id": "app", "kind": "app", "number": None, "name": "AI Browser", "color": "", "tabs": 0,
         "connected": True, "cut_off": False},
        {"id": "a3", "kind": "agent", "number": 3, "name": "Fix the footer", "color": "blue", "tabs": 2,
         "connected": True, "cut_off": False},
        {"id": "cc-x", "kind": "session", "number": None, "name": "Claude Code", "color": "orange", "tabs": 1,
         "connected": True, "cut_off": False},
        {"id": "a4", "kind": "agent", "number": 4, "name": "<img src=x onerror=alert(1)>", "color": "red",
         "tabs": 0, "connected": True, "cut_off": False}]
    stack["server"]._send_all({"type": "browser_clients", "clients": rows})
    labels = "Array.from(document.querySelectorAll('#browser-clients li span')).map(span => span.textContent)"
    assert await until(js, f"{labels}.length === 4")
    assert await js(labels) == ["AI Browser · the tab list and pictures", "3 · Fix the footer · 2 tabs",
                                "Claude Code · 1 tab", "4 · <img src=x onerror=alert(1)> · 0 tabs"]
    assert await js("document.querySelectorAll('#browser-clients img').length") == 0  # text stays text
    buttons = "Array.from(document.querySelectorAll('#browser-clients li')).map(li => !!li.querySelector('button'))"
    assert await js(buttons) == [False, True, True, True]
    assert "without a new question until AI Browser quits" in await js(
        "document.getElementById('browser-clients-note').textContent")
    assert await js("document.getElementById('browser-using-title').textContent") == \
        "Using your Brave through AI Browser"
    await js("document.querySelectorAll('#browser-clients li')[1].querySelector('button').click(); true")
    for _ in range(50):
        if brave.relay.disconnected:
            break
        await asyncio.sleep(0.1)
    assert brave.relay.disconnected == ["a3"]


@CHROME
async def test_the_browser_card_says_one_question(home):
    from fake_brave import FakeBrave

    js, _, stack = home
    brave = FakeBrave([], state="ready")
    stack["server"].attach_brave(brave)
    note = "document.getElementById('browser-note').textContent"
    ready = json.dumps('Brave will ask "Allow remote debugging?" once for AI Browser: click Allow')
    assert await until(js, f"{note} === {ready}")
    brave.set_state("asking")
    assert await until(js, f"{note}.includes('Everything waiting for Brave shares this one question.')")
