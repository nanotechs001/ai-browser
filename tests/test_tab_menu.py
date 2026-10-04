"""AI Browser's window as one page with a tab menu (/app): AI Home, Mission Control and Settings in tabs that keep
their state while hidden, and a title that follows the tab; the setup steps and an agent's live view as closable tabs;
links and buttons between our pages that switch tabs, never open a window. Drawn in a throwaway headless Chrome against
a real app server (agents on the fake claude), with the window's cookie taken the real way (the `stack` fixture)."""

import asyncio
import json

import pytest

from ai_browser.chrome import chrome_binary
from fake_brave import until as settled
from test_bridge import EVENTS
from test_check_card import checked
from test_home import page_targets, stack, until  # noqa: F401  (fixture)

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
WORKING = [EVENTS[0], {"sleep": 30}]  # an agent that stays at work


def tab(key: str) -> str:
    """A tab in the bar, by its key ("/home", "/mission", "/settings", "/setup", "live:a1")."""
    return f"document.querySelector('#tabs .tab[data-key={json.dumps(key)}]')"


def active_is(key: str) -> str:
    return f"{tab(key)}?.classList.contains('active') === true"


def keys() -> str:
    return "[...document.querySelectorAll('#tabs .tab')].map((one) => one.dataset.key)"


def view(key: str) -> str:
    """The box that holds a tab's frame."""
    return f"document.querySelector('#views .view[data-key={json.dumps(key)}]')"


def frame(key: str) -> str:
    """The window inside a tab's frame (our own pages: same origin, so the test reads them from the window's page)."""
    return f"{view(key)}?.querySelector('iframe')?.contentWindow"


def connected(key: str) -> str:
    return f"{frame(key)}?.document.getElementById('status')?.dataset.state === 'connected'"


async def pick(js, key: str) -> None:
    """A click on a tab in the bar."""
    await js(f"{tab(key)}.querySelector('.tab-label').click(); true")


async def in_frame(js, key: str, expression: str, gesture: bool = False):
    """`expression` run inside a tab's frame, in a world of the test's own (the page's DOM and events, not its
    script's variables): its postMessage comes from that frame, and with `gesture` the browser counts a click there as
    the user's own, so a link's own target would open a window if nothing stopped it. A live view's sandboxed frame
    runs in a process of its own (Chrome isolates sandboxed frames): it is reached as a target of its own."""
    cdp, session = js.cdp, js.session
    src = (await js(f"{view(key)}.querySelector('iframe').src")).split("#")[0]
    tree = (await cdp.send("Page.getFrameTree", session_id=session))["frameTree"]
    frame_id = next((child["frame"]["id"] for child in tree.get("childFrames", []) if child["frame"]["url"] == src),
                    None)
    if frame_id is None:
        infos = (await cdp.send("Target.getTargets"))["targetInfos"]
        frame_id = next(info["targetId"] for info in infos if info["type"] == "iframe" and info["url"] == src)
        session = (await cdp.send("Target.attachToTarget", {"targetId": frame_id, "flatten": True}))["sessionId"]
    context = (await cdp.send("Page.createIsolatedWorld", {"frameId": frame_id, "worldName": "test"},
                              session_id=session))["executionContextId"]
    result = await cdp.send("Runtime.evaluate", {"expression": expression, "contextId": context, "userGesture": gesture,
                                                 "returnByValue": True, "awaitPromise": True}, session_id=session)
    return result.get("result", {}).get("value")


async def click_in(js, key: str, selector: str) -> None:
    """The user's own click on an element of a tab's page."""
    await in_frame(js, key, f"document.querySelector({json.dumps(selector)}).click(); true", gesture=True)


async def window_page(stack):
    """js in the window's page, back on /app (the stack's page shows AI Home by itself until then)."""
    js = stack["home_js"]
    await stack["cdp"].send("Page.navigate", {"url": stack["url"] + "/app"}, session_id=js.session)
    assert await until(js, "location.pathname === '/app'")
    assert await until(js, connected("/home"))
    assert await settled(lambda: stack["server"].window_count == 1)  # AI Home by itself has gone
    return js


@pytest.fixture
async def shell(stack):
    """(js in AI Browser's window page, the tab menu with AI Home's tab connected; stack)."""
    return await window_page(stack), stack


@CHROME
async def test_the_window_opens_on_ai_home_in_a_tab_menu(shell):
    js, stack = shell
    tabs = "[...document.querySelectorAll('#tabs .tab')].map((one) => [one.dataset.key, one.textContent])"
    assert await js(tabs) == [["/home", "AI Home"], ["/mission", "Mission Control"], ["/settings", "Settings"]]
    assert await js("[...document.querySelectorAll('#views iframe')].map((one) => one.getAttribute('src'))") == [
        "/home"]  # the other tabs load the first time they are picked
    assert await until(js, "document.title === 'AI Home · AI Browser'")
    assert await until(js, f"{frame('/home')}.document.querySelector('#agents .empty') !== null")  # AI Home drew
    assert stack["server"].window_count == 1  # AI Home's line to the app: the window's only socket so far


@CHROME
async def test_switching_tabs_keeps_each_page_as_it_was(shell):
    js, stack = shell
    home = frame("/home")
    await js(f"(() => {{ const page = {home}; page.document.getElementById('task').value = 'half typed';"
             "const tall = page.document.createElement('div'); tall.style.height = '4000px';"
             "page.document.body.append(tall); page.scrollTo(0, 1234); page.marker = 7; return true; })()")
    await pick(js, "/mission")
    assert await until(js, connected("/mission"))
    await js(f"(() => {{ const page = {frame('/mission')}; page.marker = 8; return true; }})()")
    # AI Home runs on while hidden, and its own script may lay it out (as a broadcast's update can)
    assert await js(f"[{home}.innerWidth > 0, {home}.document.body.getBoundingClientRect().height > 4000]") == [
        True, True]
    assert await settled(lambda: stack["server"].window_count == 2)
    await pick(js, "/home")
    await asyncio.sleep(0.6)  # drawn again (a page hidden with display:none and laid out comes back at the top)
    assert await js(f"{home}.document.getElementById('task').value") == "half typed"
    assert await js(f"[{home}.scrollY, {home}.marker]") == [1234, 7]  # the same page, never reloaded
    await pick(js, "/mission")
    assert await js(f"{frame('/mission')}.marker") == 8 and await js(connected("/mission"))
    assert await js("document.querySelectorAll('#views iframe').length") == 2  # picked again: no second frame
    assert stack["server"].window_count == 2  # the hidden page's line to the app stayed open


@CHROME
async def test_the_active_tab_is_marked_and_the_others_are_hidden(shell):
    js, _ = shell
    await pick(js, "/settings")
    assert await until(js, connected("/settings"))
    marks = ("[...document.querySelectorAll('#tabs .tab')].map((one) => [one.dataset.key, "
             "one.querySelector('.tab-label').getAttribute('aria-current'), one.classList.contains('active')])")
    assert await js(marks) == [["/home", None, False], ["/mission", None, False], ["/settings", "page", True]]
    shown = ("[...document.querySelectorAll('#views .view')].map((one) => [one.dataset.key, "
             "getComputedStyle(one).visibility, getComputedStyle(one).contentVisibility])")
    assert await js(shown) == [["/home", "hidden", "hidden"], ["/settings", "visible", "visible"]]
    await pick(js, "/home")
    assert await js(marks) == [["/home", "page", True], ["/mission", None, False], ["/settings", None, False]]
    assert await js(shown) == [["/home", "visible", "visible"], ["/settings", "hidden", "hidden"]]


@CHROME
async def test_the_title_follows_the_tab_and_keeps_ai_homes_count(shell):
    js, stack = shell
    assert await until(js, "document.title === 'AI Home · AI Browser'")
    await pick(js, "/mission")
    assert await until(js, "document.title === 'Mission Control · AI Browser'")
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    agent = await stack["server"].agents.create("keep working")
    assert await until(js, "document.title === '(1) Mission Control · AI Browser'")  # AI Home counts, hidden
    await pick(js, "/settings")
    assert await until(js, "document.title === '(1) Settings · AI Browser'")
    await pick(js, "/home")
    assert await until(js, "document.title === '(1) AI Home · AI Browser'")
    await stack["server"].agents.stop(agent.id)
    assert await until(js, "document.title === 'AI Home · AI Browser'")


async def mouse_click(js, at) -> None:
    """A real mouse click at (x, y) in the window's page: the browser picks what is under it."""
    for kind in ("mousePressed", "mouseReleased"):
        await js.cdp.send("Input.dispatchMouseEvent", {"type": kind, "x": at[0], "y": at[1], "button": "left",
                                                       "clickCount": 1}, session_id=js.session)


CENTRE = "((box) => [box.x + box.width / 2, box.y + box.height / 2])"


@CHROME
async def test_a_real_click_lands_on_the_tab_shown_never_on_a_hidden_one(shell):
    js, _ = shell
    for key in ("/mission", "/settings"):  # two hidden pages now lie above AI Home's in the page
        await pick(js, key)
        assert await until(js, connected(key))
    await mouse_click(js, await js(f"{CENTRE}({tab('/home')}.querySelector('.tab-label').getBoundingClientRect())"))
    assert await until(js, active_is("/home"))
    task = (f"(() => {{ const frame = {view('/home')}.querySelector('iframe'); const outer = "
            "frame.getBoundingClientRect(); const box = frame.contentDocument.getElementById('task')"
            ".getBoundingClientRect(); return [outer.x + box.x + box.width / 2, outer.y + box.y + box.height / 2]; })()")
    await mouse_click(js, await js(task))
    assert await until(js, f"{frame('/home')}.document.activeElement?.id === 'task'")  # AI Home's own box


async def all_pages(stack) -> list[str]:
    """Every page target in the throwaway Chrome: a window opened by any page would add one."""
    return sorted(await page_targets(stack["cdp"], ""))


@CHROME
async def test_our_buttons_switch_tabs_and_never_open_a_window(shell):
    js, stack = shell
    pages = await all_pages(stack)
    await click_in(js, "/home", "#mission")  # AI Home's Mission Control button
    assert await until(js, f"{active_is('/mission')} && {connected('/mission')}")
    await click_in(js, "/mission", "#home-link")  # Mission Control's AI Home button
    assert await until(js, active_is("/home"))
    await click_in(js, "/home", "#mission")  # open already: shown again, never a second one
    assert await until(js, active_is("/mission"))
    await click_in(js, "/mission", "#home-link")
    assert await until(js, active_is("/home"))
    await click_in(js, "/home", "#settings")
    assert await until(js, f"{active_is('/settings')} && {connected('/settings')}")
    await click_in(js, "/settings", "#home-link")
    assert await until(js, active_is("/home"))
    await asyncio.sleep(0.5)
    assert await js(keys()) == ["/home", "/mission", "/settings"]
    assert await js("document.querySelectorAll('#views iframe').length") == 3
    assert await all_pages(stack) == pages  # no window of any kind
    assert stack["server"].window_count == 3


@CHROME
async def test_a_link_to_one_of_our_pages_switches_tabs(shell):
    js, stack = shell
    pages = await all_pages(stack)
    await in_frame(js, "/home", "const ours = document.createElement('a'); ours.id = 'ours'; ours.href = '/settings';"
                                "ours.target = '_blank'; ours.textContent = 'Settings'; document.body.append(ours); true")
    await click_in(js, "/home", "#ours")
    assert await until(js, f"{active_is('/settings')} && {connected('/settings')}")
    await asyncio.sleep(0.5)
    assert await js(f"{frame('/home')}.location.pathname") == "/home"  # the link itself never navigates
    assert await all_pages(stack) == pages  # and its _blank target opened nothing


@CHROME
async def test_a_website_link_goes_to_the_users_browser(shell, monkeypatch):
    from ai_browser import platforms

    js, stack = shell
    opened = []
    monkeypatch.setattr(platforms, "open_url", lambda url, browser=None, system=None: opened.append(url) or True)
    await pick(js, "/settings")
    assert await until(js, connected("/settings"))
    pages = await all_pages(stack)
    await in_frame(js, "/settings", "const site = document.createElement('a'); site.id = 'site';"
                                    "site.href = 'https://example.com/pricing'; site.target = '_blank';"
                                    "site.textContent = 'pricing'; document.body.append(site); true")
    await click_in(js, "/settings", "#site")
    assert await settled(lambda: opened == ["https://example.com/pricing"])
    await asyncio.sleep(0.5)
    assert await js(f"{frame('/settings')}.location.pathname") == "/settings"  # never in the window
    assert await js(keys()) == ["/home", "/mission", "/settings"] and await all_pages(stack) == pages


@CHROME
async def test_the_setup_steps_open_as_one_closable_tab(shell):
    js, stack = shell
    home = frame("/home")
    assert await until(js, f"{home}.document.querySelector('#brain .brain-setup') !== null")  # no watcher yet
    await click_in(js, "/home", "#brain .brain-setup")  # the Brain's "Set it up"
    assert await until(js, f"{active_is('/setup')} && {frame('/setup')}?.location.hash === '#brave'")
    assert await js(f"{tab('/setup')}.querySelector('.tab-label').textContent") == "Setup"
    assert await js(f"{tab('/setup')}.querySelector('.tab-close').getAttribute('aria-label')") == "Close Setup"
    assert await until(js, "document.title === 'Setup · AI Browser'")
    assert await until(js, f"{frame('/setup')}.document.getElementById('watcher-folder').textContent !== ''")
    await pick(js, "/home")
    stack["brave"].set_state("off")
    assert await until(js, f"{home}.document.getElementById('browser-action').textContent === 'Show me how'")
    await click_in(js, "/home", "#browser-action")  # Brave's switch: the same tab, at the switch's steps
    assert await until(js, f"{active_is('/setup')} && {frame('/setup')}.location.hash === '#switch'")
    assert await js(keys()) == ["/home", "/mission", "/settings", "/setup"]
    assert await js("document.querySelectorAll('#views .view').length") == 2  # AI Home's and the setup's
    await js(f"{tab('/setup')}.querySelector('.tab-close').click(); true")  # its ×
    assert await until(js, f"{tab('/setup')} === null && {view('/setup')} === null && {active_is('/home')}")
    assert await js("document.title") == "AI Home · AI Browser"


@CHROME
async def test_show_me_opens_one_live_view_tab_per_agent_and_closing_it_ends_only_that(shell):
    from ai_browser.live import LiveView

    js, stack = shell
    live = LiveView()  # an engine's live view (QA's sandbox), with no browser behind it
    address = await live.start()
    try:
        agent = await checked(stack, "Flights to Manila", target="Q1", live=address)
        card = f"{frame('/home')}.document.querySelector('.agent[data-id=\"{agent.id}\"] .bot-check')"
        assert await until(js, f"{card} != null")
        key = f"live:{agent.id}"
        await click_in(js, "/home", f".agent[data-id='{agent.id}'] .show-me")
        assert await until(js, active_is(key))
        assert await js(f"{tab(key)}.querySelector('.tab-label').textContent") == "Live view · 1 · Flights to Manila"
        assert await until(js, "document.title === 'Live view · 1 · Flights to Manila · AI Browser'")
        live_frame = f"{view(key)}.querySelector('iframe')"
        assert await js(f"[{live_frame}.getAttribute('src'), {live_frame}.getAttribute('sandbox')]") == [
            address, "allow-scripts"]
        assert await settled(lambda: len(live.viewers) == 1)  # its page is up, with its own line to the live view
        await pick(js, "/home")
        await click_in(js, "/home", f".agent[data-id='{agent.id}'] .show-me")  # Show me again
        assert await until(js, active_is(key))
        await asyncio.sleep(0.5)
        assert await js(keys()) == ["/home", "/mission", "/settings", key]  # the same tab, never a second
        assert await js(f"document.querySelectorAll('#views .view[data-key=\"{key}\"]').length") == 1
        assert len(live.viewers) == 1
        windows = stack["server"].window_count
        await js(f"{tab(key)}.querySelector('.tab-close').click(); true")
        assert await settled(lambda: not live.viewers)  # its page has gone, and its socket with it
        assert await js(f"{view(key)} === null && {active_is('/home')}")
        await asyncio.sleep(0.5)
        assert stack["server"].window_count == windows and await js(connected("/home"))  # the app runs on
    finally:
        await live.stop()


@CHROME
async def test_only_our_pages_open_tabs_and_only_for_our_pages(shell):
    from ai_browser.live import LiveView

    js, stack = shell
    live = LiveView()
    address = await live.start()
    try:
        before = await js(keys())
        refused = [{"type": "tab", "path": "/app"}, {"type": "tab", "path": "https://example.com/"},
                   {"type": "tab", "path": "//example.com/setup"}, {"type": "tab", "path": "/agent-status"},
                   {"type": "tab", "path": 7}, {"type": "window", "path": "/settings"}, "tab", None,
                   {"type": "live", "url": "https://example.com/live?token=abc", "agent": "a1"},
                   {"type": "live", "url": address + "&next=https://example.com", "agent": "a1"},
                   {"type": "live", "url": address, "agent": "../a1"}, {"type": "live", "url": address}]
        for message in refused:  # from AI Home's own frame: never a tab
            assert await in_frame(js, "/home", f"parent.postMessage({json.dumps(message)}, location.origin); true")
        for message in ({"type": "tab", "path": "/settings"}, {"type": "live", "url": address, "agent": "a1"}):
            await js(f"window.postMessage({json.dumps(message)}, location.origin); true")  # the window's own page
        await asyncio.sleep(1)
        assert await js(keys()) == before and await js(active_is("/home"))
        await in_frame(js, "/home", "parent.postMessage({type: 'live', url: " + json.dumps(address)
                       + ", agent: 'a1', label: '<img src=x onerror=alert(1)>'}, location.origin); true")
        assert await until(js, active_is("live:a1"))  # the one valid ask: its label stays text
        assert await js(f"{tab('live:a1')}.querySelector('img') === null")
        assert (await js(f"{tab('live:a1')}.textContent")).startswith("Live view · <img src=x")
        assert await settled(lambda: len(live.viewers) == 1)
        assert await in_frame(js, "live:a1", "parent.postMessage({type: 'tab', path: '/settings'}, '*'); true")
        await asyncio.sleep(1)
        assert await js(active_is("live:a1")) and await js(f"{view('/settings')} === null")
    finally:
        await live.stop()
