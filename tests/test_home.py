"""AI Home and its window: the pages over http, opened the way AI Browser's window opens them (a one-time code swapped
for the window's cookie) in a throwaway headless Chrome, talking to a real app server (agents run the fake claude)."""

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
    """(target, js) for a new tab showing `url`, once it has left about:blank. js.cdp and js.session drive it."""
    params = {"url": url, **({"background": True} if background else {})}
    target = (await cdp.send("Target.createTarget", params))["targetId"]
    session = (await cdp.send("Target.attachToTarget", {"targetId": target, "flatten": True}))["sessionId"]

    async def js(expression):
        return await evaluate(cdp, session, expression)

    js.cdp, js.session = cdp, session
    await until(js, "location.protocol !== 'about:' && document.readyState === 'complete'")
    return target, js


async def page_js(cdp, target):
    """js(expression) in a page that is already open (a window one of ours opened)."""
    session = (await cdp.send("Target.attachToTarget", {"targetId": target, "flatten": True}))["sessionId"]

    async def js(expression):
        return await evaluate(cdp, session, expression)

    js.cdp, js.session = cdp, session
    return js


async def click_as_user(js, selector):
    """A click the browser counts as the user's own (Runtime.evaluate with userGesture): window.open needs one."""
    result = await js.cdp.send("Runtime.evaluate", {
        "expression": f"document.querySelector({json.dumps(selector)}).click(); true", "userGesture": True,
        "returnByValue": True}, session_id=js.session)
    return result.get("result", {}).get("value")


async def page_targets(cdp, ending) -> list[str]:
    """The page targets whose address ends with `ending` ("/mission", "/setup#brave")."""
    infos = (await cdp.send("Target.getTargets"))["targetInfos"]
    return [info["targetId"] for info in infos if info["type"] == "page" and info["url"].endswith(ending)]


WINDOW_INFO = {"using": "chrome", "name": "Google Chrome", "note": "",
               "choices": [{"id": "auto", "name": "Auto (Google Chrome)", "installed": True},
                           {"id": "chrome", "name": "Google Chrome", "installed": True},
                           {"id": "brave", "name": "Brave", "installed": True}]}


@pytest.fixture
async def stack(fake_claude, tmp_path):
    """A real app server (agents on the fake claude) and its pages in a throwaway headless Chrome, opened the way AI
    Browser's window opens them: a one-time code swapped for the window's cookie. The swap lands on the window's tab
    menu (/app); the page then shows AI Home by itself, as every page of ours still works on its own, so these tests
    drive AI Home directly (tests/test_tab_menu.py drives the tabs). The throwaway keeps its debugging port because
    the tests drive the pages through it; the product's window never has one. Agents browse in the user's browser,
    here a FakeBrave with no tabs (a test that needs tabs attaches its own)."""
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer
    from ai_browser.brain.service import BrainService
    from ai_browser.brain.skillwriter import SkillWriter
    from ai_browser.brain.store import BrainStore
    from ai_browser.brain.tools import ToolsConfig
    from ai_browser.brain.workflows import WorkflowRunner, WorkflowStore
    from ai_browser.cdp import CDP
    from ai_browser.chrome import find_ws_url, launch
    from ai_browser.hearing.service import HearingService
    from fake_brave import FakeBrave
    from fake_engine import FakeEngine, tiny_store

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    home = tmp_path / "home"
    agents = AgentManager(home, claude=runner)
    brain = BrainService(BrainStore(home), agents, claude=runner)
    engine = FakeEngine(answers=["what is fix the footer doing"])
    hearing = HearingService(tiny_store(home / "models"), engine)  # talking is ready: the tiny model is in place
    workflows = WorkflowStore(home)
    tools = ToolsConfig(home, claude_home=tmp_path / "user")  # the tests that use it write a configuration there
    skills = SkillWriter(tmp_path / "user" / ".claude" / "skills", claude=runner, cwd=tmp_path / "calls")
    server = AppServer(home, agents, brain=brain, workflows=workflows, runner=WorkflowRunner(workflows, agents),
                       tools=tools, skill_writer=skills, hearing=hearing)
    url = await server.start()
    server.window_info = WINDOW_INFO  # Chrome draws it; Chrome and Brave installed, whatever this computer has
    brave = FakeBrave([])
    server.attach_brave(brave)
    agents.close_tabs = brave.close_targets
    profile = tmp_path / "profile"
    process = launch(profile, headless=True)
    ws_url = find_ws_url(profile, timeout=20)
    cdp = await CDP.connect(ws_url)
    target, js = await open_page(cdp, f"{url}/open?code={server.new_launch_code()}")  # the cookie, the real way
    assert await until(js, "location.pathname === '/app'")  # the window's tab menu (tests/test_tab_menu.py)
    await cdp.send("Page.navigate", {"url": f"{url}/home"}, session_id=js.session)  # AI Home by itself, top-level
    assert await until(js, "location.pathname === '/home' && document.readyState === 'complete'")
    state = {"server": server, "cdp": cdp, "url": url, "ws_url": ws_url, "home": home, "log": log, "runner": runner,
             "script": script, "brain": brain, "workflows": workflows, "tools": tools, "hearing": hearing,
             "engine": engine, "user": tmp_path / "user", "brave": brave, "home_js": js, "home_target": target}
    yield state
    await cdp.close()
    await state["server"].stop()
    process.terminate()
    process.wait(timeout=15)


@pytest.fixture
async def home(stack):
    """(js in AI Home, the page the window opened; stack)."""
    js = stack["home_js"]
    assert await until(js, "document.getElementById('status').dataset.state === 'connected'")
    return js, stack


async def post_tab(stack, agent, kind, target):
    async with httpx.AsyncClient() as client:
        await client.post(stack["url"] + "/agent-events", headers={"X-AIB-Agent-Token": stack["server"].token_for(agent)},
                          json={"agent": agent, "kind": kind, "target": target, "adopted": False})


@CHROME
async def test_ai_home_shows_agents_tabs_and_skills_as_text(home):
    from fake_brave import FakeBrave

    js, stack = home
    await stack["server"].agents.create(HOSTILE)
    assert await until(js, "document.querySelectorAll('#agents .agent').length === 1")
    assert "<img" in await js("document.querySelector('#agents .agent .name').textContent")
    assert await js("document.querySelectorAll('#agents img:not(.thumb)').length") == 0
    assert await js("document.title") != "pwned"
    assert await until(js, "/\\d/.test(document.querySelector('#skills .count').textContent)")
    stack["server"].attach_brave(FakeBrave([{"target": "S1", "url": "https://shop.example/", "title": "Shop page"}]))
    assert await until(js, "document.getElementById('tabs').textContent.includes('Shop page')")


@CHROME
async def test_ai_home_connects_over_http_with_the_windows_cookie(home):
    js, stack = home
    assert await js("location.origin") == stack["url"] and stack["server"].window_count >= 1
    assert await js("document.cookie") == ""  # HttpOnly: the page's own script can't read the window's cookie


@CHROME
async def test_an_old_window_is_refused_after_the_app_restarts(home):
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer

    js, stack = home
    port = stack["server"].port
    await stack["server"].stop()
    assert await until(js, "document.getElementById('status').dataset.state !== 'connected'")
    server = AppServer(stack["home"], AgentManager(stack["home"], claude=stack["runner"]), ports=range(port, port + 1))
    stack["server"] = server
    try:
        await server.start()  # the same address, a new run: the window's cookie holds the old secret
    except RuntimeError:
        pytest.skip("this system still holds the old address")
    assert await until(js, "document.getElementById('status').dataset.state === 'refused'", 15)
    assert await js("document.getElementById('status').title") == (
        "This window wasn't opened by this run of ai-browser app: close it")
    await asyncio.sleep(2)
    assert await js("document.getElementById('status').dataset.state") == "refused"  # it stopped trying
    assert server.window_count == 0


@CHROME
async def test_rows_are_updated_in_place_so_clicks_land(home):
    from fake_brave import FakeBrave

    js, stack = home
    server = stack["server"]
    stack["script"].write_text(json.dumps([EVENTS[0], {"sleep": 4}, *EVENTS[1:]]),
                               encoding="utf-8")  # it keeps working a while
    server.attach_brave(FakeBrave([{"target": "P1", "url": "https://some.example/", "title": "Some page"}]))
    agent = await server.agents.create("keep working")
    row = f"#agents .agent[data-id='{agent.id}']"
    assert await until(js, f"!!document.querySelector(\"{row} .stop\") && "
                           "document.getElementById('tabs').textContent.includes('Some page')")
    await js(f"window.held = [document.querySelector(\"{row} .stop\"), document.querySelector('#tabs .tab')]; true")
    for step in range(3):  # each change of the agent redraws its row: in place
        agent.status = f"step {step}"
        server.agents._changed(agent)
        await asyncio.sleep(0.1)
    await asyncio.sleep(0.5)
    assert await js(f"document.querySelector(\"{row} .status\").textContent") == "step 2"
    assert await js("window.held.every(node => node.isConnected)")  # the same elements: a click can't be lost


@CHROME
async def test_the_pages_csp_blocks_injected_script_and_the_other_routes(home):
    js, _ = home
    await js("window.violations = 0;"
             "document.addEventListener('securitypolicyviolation', () => { window.violations += 1; });"
             "const script = document.createElement('script'); script.textContent = 'window.pwned = true';"
             "document.body.append(script); true")
    assert await until(js, "window.violations >= 1")
    assert await js("window.pwned === undefined")
    assert await js("fetch('/agent-status').then(() => 'reached', () => 'blocked')") == "blocked"


@CHROME
async def test_a_page_opened_any_other_way_gets_no_socket(home):
    js, stack = home
    cdp, server = stack["cdp"], stack["server"]
    before = server.window_count
    context = (await cdp.send("Target.createBrowserContext"))["browserContextId"]  # no cookie there, as in Brave
    try:
        target = (await cdp.send("Target.createTarget", {"url": stack["url"] + "/home",
                                                         "browserContextId": context}))["targetId"]
        other = await page_js(cdp, target)
        assert await until(other, "document.body !== null && "
                                  "document.body.textContent.includes('open only in its own window')")
        await asyncio.sleep(1)
        assert server.window_count == before and await other("document.scripts.length") == 0
    finally:
        await cdp.send("Target.disposeBrowserContext", {"browserContextId": context})


@CHROME
async def test_a_task_starts_once_from_ai_home(home):
    js, stack = home
    await js("document.getElementById('task').value = 'check the shop'; "
             "document.getElementById('start').click(); document.getElementById('start').click(); true")
    assert await until(js, "document.querySelectorAll('#agents .agent').length === 1")
    await asyncio.sleep(1)
    assert len(stack["server"].agents.agents) == 1  # a double click makes one agent
    assert await until(js, "!document.getElementById('start').disabled")


CHIP = "(target => document.querySelector(`#tabs .tab[data-target='${target}'] .chip`)?.textContent)"


def in_row(target, selector):
    return f"document.querySelector(\"#tabs .tab[data-target='{target}'] {selector}\")"


@CHROME
async def test_the_tab_list_marks_owners_and_hands_tabs_over(home):
    from fake_brave import FakeBrave

    js, stack = home
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
    assert await until(js, f"{CHIP}('T1') === '1 · Fix the footer'")
    assert await js(f"['S1', 'B1', 'U2', 'U1'].map({CHIP})") == ["Claude Code", "Brain",
                                                                 "handed to 1 · Fix the footer", "you"]
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

    js, stack = home
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

    js, stack = home
    server = stack["server"]
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
        _, late = await open_page(stack["cdp"], stack["url"] + "/home")  # loads now, with the window's cookie
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
async def test_ai_home_shows_numbers_on_rows_and_give_to(home):
    from fake_brave import FakeBrave

    js, stack = home
    server = stack["server"]
    await server.agents.create("Fix the footer")
    server.attach_brave(FakeBrave([{"target": "U1", "url": "https://mail.example/", "title": "Mail"}]))
    assert await until(js, "document.querySelector('#agents .agent .name')?.textContent === '1 · Fix the footer'")
    await js("document.querySelector('#agents .agent .chat').click(); true")
    assert await until(js, "document.getElementById('chat-name').textContent === '1 · Fix the footer'")
    assert await until(js, f"{in_row('U1', '.hand')} !== null")
    await js(f"{in_row('U1', '.hand')}.click(); true")
    assert await js(f"{in_row('U1', '.give[data-id=a1]')}.textContent") == "Give to 1 · Fix the footer"


@CHROME
async def test_the_connected_list_names_agents_like_every_other_list(home):
    from fake_brave import FakeBrave

    js, stack = home
    stack["server"].attach_brave(FakeBrave([]))
    stack["server"]._send_all({"type": "browser_clients", "clients": [
        {"id": "a3", "kind": "agent", "number": None, "name": "Fix the footer", "color": "blue", "tabs": 2,
         "connected": True, "cut_off": False}]})
    listed = "document.getElementById('browser-clients').textContent"
    assert await until(js, f"{listed}.includes('3 · Fix the footer')")  # agentLabel: the id's digits, if need be
    assert "null" not in await js(listed)


@CHROME
async def test_the_browser_card_follows_brave(home):
    from fake_brave import FakeBrave

    js, stack = home
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
async def test_ai_home_lists_connected_clients_with_disconnect(home):
    from fake_brave import FakeBrave

    js, stack = home
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

    js, stack = home
    brave = FakeBrave([], state="ready")
    stack["server"].attach_brave(brave)
    note = "document.getElementById('browser-note').textContent"
    ready = json.dumps('Brave will ask "Allow remote debugging?" once for AI Browser: click Allow')
    assert await until(js, f"{note} === {ready}")
    brave.set_state("asking")
    assert await until(js, f"{note}.includes('Everything waiting for Brave shares this one question.')")
    brave.set_state("refused")  # only a no: the question never runs out of time (app/cdprelay.py)
    assert await until(js, f"{note} === 'Brave said no.'")


@CHROME
async def test_a_page_by_itself_sends_links_to_the_users_browser_or_moves_to_our_page(home, monkeypatch):
    """AI Home opened by itself, outside the window's tab menu (tests/test_tab_menu.py has the tabs): a website opens
    in the user's browser, and a link to one of our pages moves this page there. Neither opens a window."""
    from ai_browser import platforms

    js, stack = home
    opened = []
    monkeypatch.setattr(platforms, "open_url", lambda url, browser=None, system=None: opened.append(url) or True)
    before, pages = await js("location.href"), sorted(await page_targets(stack["cdp"], ""))
    await js("const site = document.createElement('a'); site.id = 'site'; site.href = 'https://example.com/pricing';"
             "site.target = '_blank'; site.textContent = 'pricing'; document.body.append(site);"
             "const ours = document.createElement('a'); ours.id = 'ours'; ours.href = '/settings';"
             "ours.target = '_blank'; ours.textContent = 'Settings'; document.body.append(ours); true")
    await click_as_user(js, "#site")
    for _ in range(50):
        if opened:
            break
        await asyncio.sleep(0.1)
    assert opened == ["https://example.com/pricing"] and await js("location.href") == before  # never in the window
    await click_as_user(js, "#ours")
    assert await until(js, "location.pathname === '/settings'")
    assert sorted(await page_targets(stack["cdp"], "")) == pages  # the same page moved: no window opened


async def open_settings(stack):
    """Settings by itself, with the window's cookie (in the window it is a tab: tests/test_tab_menu.py)."""
    _, settings = await open_page(stack["cdp"], stack["url"] + "/settings")
    assert await until(settings, "document.querySelectorAll('#window-choices input').length === 3")
    return settings


@CHROME
async def test_settings_saves_the_choice(home):
    from ai_browser.settings import read_settings

    _, stack = home
    settings = await open_settings(stack)
    labels = "[...document.querySelectorAll('#window-choices label')].map((label) => label.textContent)"
    assert await settings(labels) == ["Auto (Google Chrome)", "Google Chrome", "Brave"]
    assert await settings("document.querySelector('#window-choices input[value=auto]').checked") is True
    assert await settings("document.getElementById('window-using').textContent") == (
        "This window: Google Chrome. A change applies the next time AI Browser starts.")
    await settings("document.querySelector('#window-choices input[value=brave]').click(); true")
    for _ in range(50):
        if read_settings(stack["home"]).get("window_browser") == "brave":
            break
        await asyncio.sleep(0.1)
    assert read_settings(stack["home"])["window_browser"] == "brave"
    assert await until(settings, "document.querySelector('#window-choices input[value=brave]').checked")


@CHROME
async def test_a_browser_that_isnt_installed_is_greyed_out(home):
    _, stack = home
    stack["server"].window_info = {
        "using": "chrome", "name": "Google Chrome",
        "note": "Brave isn't installed: the window uses Google Chrome. Change it in Settings.",
        "choices": [{"id": "auto", "name": "Auto (Google Chrome)", "installed": True},
                    {"id": "chrome", "name": "Google Chrome", "installed": True},
                    {"id": "brave", "name": "Brave", "installed": False}]}
    settings = await open_settings(stack)
    assert await settings("document.querySelector('#window-choices input[value=brave]').disabled") is True
    assert await settings("document.querySelectorAll('#window-choices label')[2].textContent") == (
        "Brave · not installed")
    assert (await settings("document.getElementById('window-note').textContent")).startswith("Brave isn't installed")


@CHROME
async def test_ai_homes_words_for_the_window(home):
    js, _ = home
    assert await js("document.querySelector('.new-task .grow').textContent") == (
        "Or type ai and a space in Brave's address bar")
    assert await until(js, "document.querySelector('#agents .empty')?.textContent === "
                           "'No agents yet. Start a task above.'")


@CHROME
async def test_the_title_counts_the_working_agents(home):
    js, stack = home
    stack["script"].write_text(json.dumps([EVENTS[0], {"sleep": 30}]), encoding="utf-8")  # it stays at work
    agent = await stack["server"].agents.create("keep working")
    assert await until(js, "document.title === '(1) AI Home'")
    await stack["server"].agents.stop(agent.id)
    assert await until(js, "document.title === 'AI Home'")
