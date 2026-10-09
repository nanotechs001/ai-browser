"""AI Browser's window and its pages over http, opened the way the window opens them (a one-time code swapped for the
window's cookie) in a throwaway headless Chrome, talking to a real app server (agents run the fake claude). The window
opens on Mission Control; AI Home's old address leads there (the saved-agents spec, 6). The `stack` fixture lives here:
every page test starts from it."""

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
    menu (/app); the page then shows Mission Control by itself, as every page of ours still works on its own, so these
    tests drive it directly (tests/test_tab_menu.py drives the tabs). The throwaway keeps its debugging port because
    the tests drive the pages through it; the product's window never has one. Agents browse in the user's browser,
    here a FakeBrave with no tabs (a test that needs tabs attaches its own)."""
    from ai_browser.accounts import Accounts
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
    accounts = Accounts(home, claude=runner)  # AI accounts: Default only, until a test adds one
    server = AppServer(home, agents, brain=brain, workflows=workflows, runner=WorkflowRunner(workflows, agents),
                       tools=tools, skill_writer=skills, hearing=hearing, accounts=accounts)
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
    await cdp.send("Page.navigate", {"url": f"{url}/mission"}, session_id=js.session)  # Mission Control by itself
    assert await until(js, "location.pathname === '/mission' && document.readyState === 'complete'")
    state = {"server": server, "cdp": cdp, "url": url, "ws_url": ws_url, "home": home, "log": log, "runner": runner,
             "script": script, "brain": brain, "workflows": workflows, "tools": tools, "hearing": hearing,
             "engine": engine, "user": tmp_path / "user", "brave": brave, "page_js": js, "page_target": target,
             "accounts": accounts}
    yield state
    await cdp.close()
    await state["server"].stop()
    process.terminate()
    process.wait(timeout=15)


@pytest.fixture
async def page(stack):
    """(js in Mission Control, the page the window opened; stack)."""
    js = stack["page_js"]
    assert await until(js, "document.getElementById('status').dataset.state === 'connected'")
    return js, stack


async def post_tab(stack, agent, kind, target):
    async with httpx.AsyncClient() as client:
        await client.post(stack["url"] + "/agent-events", headers={"X-AIB-Agent-Token": stack["server"].token_for(agent)},
                          json={"agent": agent, "kind": kind, "target": target, "adopted": False})


@CHROME
async def test_the_window_lands_on_mission_control_over_http_with_its_cookie(page):
    js, stack = page
    assert await js("location.pathname") == "/mission" and await js("location.origin") == stack["url"]
    assert stack["server"].window_count >= 1
    assert await js("document.cookie") == ""  # HttpOnly: the page's own script can't read the window's cookie


@CHROME
async def test_ai_homes_old_address_opens_mission_control(page):
    js, stack = page
    await js("location.assign('/home'); true")  # an old bookmark
    assert await until(js, "location.pathname === '/mission' && document.readyState === 'complete'")
    assert await until(js, "document.getElementById('status').dataset.state === 'connected'")


@CHROME
async def test_an_old_window_is_refused_after_the_app_restarts(page):
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer

    js, stack = page
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
async def test_the_pages_csp_blocks_injected_script_and_the_other_routes(page):
    js, _ = page
    await js("window.violations = 0;"
             "document.addEventListener('securitypolicyviolation', () => { window.violations += 1; });"
             "const script = document.createElement('script'); script.textContent = 'window.pwned = true';"
             "document.body.append(script); true")
    assert await until(js, "window.violations >= 1")
    assert await js("window.pwned === undefined")
    assert await js("fetch('/agent-status').then(() => 'reached', () => 'blocked')") == "blocked"


@CHROME
async def test_a_page_opened_any_other_way_gets_no_socket(page):
    js, stack = page
    cdp, server = stack["cdp"], stack["server"]
    before = server.window_count
    context = (await cdp.send("Target.createBrowserContext"))["browserContextId"]  # no cookie there, as in Brave
    try:
        target = (await cdp.send("Target.createTarget", {"url": stack["url"] + "/mission",
                                                         "browserContextId": context}))["targetId"]
        other = await page_js(cdp, target)
        assert await until(other, "document.body !== null && "
                                  "document.body.textContent.includes('open only in its own window')")
        await asyncio.sleep(1)
        assert server.window_count == before and await other("document.scripts.length") == 0
    finally:
        await cdp.send("Target.disposeBrowserContext", {"browserContextId": context})


LAST_USED = "Showing the Brave profile you used last. Pick the one agents use in Settings → Where agents browse."


@CHROME
async def test_while_brave_connects_the_tabs_page_claims_no_profile(page, tmp_path):  # final review R1
    from ai_browser.app.bravelink import BraveLink
    from fake_brave import FakePort

    js, stack = page
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
        _, late = await open_page(stack["cdp"], stack["url"] + "/mission")  # loads now, with the window's cookie
        assert await until(late, "document.getElementById('status').dataset.state === 'connected'")
        await late("document.querySelector('.page-link[data-page=\"tabs\"]').click(); true")
        assert await until(late, f"({empty}) !== null")  # its snapshot is drawn
        assert await late(source) is None and await late(empty) == "No web pages open in your browser."
        port.hold = set()
        await port.answer_held()
        await connecting
        assert await until(late, "document.querySelector(\"#tabs .tab[data-target='U1']\") !== null")
        assert await late(source) == LAST_USED  # the first list brings its scope (none chosen here)
        assert port.sessions == 1  # one connection: Brave asked "Allow remote debugging?" once
    finally:
        connecting.cancel()
        await brave.close()
        await port.stop()


@CHROME
async def test_a_page_by_itself_sends_links_to_the_users_browser_or_moves_to_our_page(page, monkeypatch):
    """Mission Control opened by itself, outside the window's tab menu (tests/test_tab_menu.py has the tabs): a website opens
    in the user's browser, and a link to one of our pages moves this page there. Neither opens a window."""
    from ai_browser import platforms

    js, stack = page
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
async def test_settings_saves_the_choice(page):
    from ai_browser.settings import read_settings

    _, stack = page
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
async def test_a_browser_that_isnt_installed_is_greyed_out(page):
    _, stack = page
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
