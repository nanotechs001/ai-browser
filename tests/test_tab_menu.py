"""AI Browser's window as one page with a tab menu (/app): Mission Control and Settings in tabs that keep their state
while hidden, and a title that follows the tab; the setup steps and an agent's live view as closable tabs;
links and buttons between our pages that switch tabs, never open a window; and the close-tab key, which closes a tab
with a ×, never the window. Drawn in a throwaway headless Chrome against a real app server (agents on the fake claude),
with the window's cookie taken the real way (the `stack` fixture)."""

import asyncio
import json
import sys

import pytest

from ai_browser.chrome import chrome_binary
from fake_brave import until as settled
from test_bridge import EVENTS
from test_check_card import checked
from test_home import page_targets, stack, until  # noqa: F401  (fixture)

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
WORKING = [EVENTS[0], {"sleep": 30}]  # an agent that stays at work


def tab(key: str) -> str:
    """A tab in the bar, by its key ("/mission", "/settings", "/setup", "live:a1")."""
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
    """js in the window's page, back on /app (the stack's page shows Mission Control by itself until then)."""
    js = stack["page_js"]
    await stack["cdp"].send("Page.navigate", {"url": stack["url"] + "/app"}, session_id=js.session)
    assert await until(js, "location.pathname === '/app'")
    assert await until(js, connected("/mission"))
    assert await settled(lambda: stack["server"].window_count == 1)  # Mission Control by itself has gone
    return js


@pytest.fixture
async def shell(stack):
    """(js in AI Browser's window page, the tab menu with Mission Control's tab connected; stack)."""
    return await window_page(stack), stack


@CHROME
async def test_the_window_opens_on_mission_control_in_a_tab_menu(shell):
    js, stack = shell
    tabs = "[...document.querySelectorAll('#tabs .tab')].map((one) => [one.dataset.key, one.textContent])"
    assert await js(tabs) == [["/mission", "Mission Control"], ["/settings", "Settings"]]  # AI Home has gone
    assert await js("[...document.querySelectorAll('#views iframe')].map((one) => one.getAttribute('src'))") == [
        "/mission"]  # Settings loads the first time it is picked
    assert await until(js, "document.title === 'Mission Control · AI Browser'")
    assert await until(js, f"{frame('/mission')}.document.getElementById('counts').textContent === 'No agents yet'")
    assert stack["server"].window_count == 1  # Mission Control's line to the app: the window's only socket so far


@CHROME
async def test_switching_tabs_keeps_each_page_as_it_was(shell):
    js, stack = shell
    mission = frame("/mission")
    await js(f"(() => {{ const page = {mission}; page.document.getElementById('task').value = 'half typed';"
             "page.marker = 7; return true; })()")
    await pick(js, "/settings")
    assert await until(js, connected("/settings"))
    settings = frame("/settings")
    await js(f"(() => {{ const page = {settings}; const tall = page.document.createElement('div');"
             "tall.style.height = '4000px'; page.document.body.append(tall); page.scrollTo(0, 1234); page.marker = 8;"
             " return true; })()")
    # Mission Control runs on while hidden, and its own script may lay it out (as a broadcast's update can)
    assert await js(f"{mission}.innerWidth > 0") is True
    assert await settled(lambda: stack["server"].window_count == 2)
    await pick(js, "/mission")
    await asyncio.sleep(0.6)  # drawn again
    assert await js(f"[{mission}.document.getElementById('task').value, {mission}.marker]") == ["half typed", 7]
    await pick(js, "/settings")
    await asyncio.sleep(0.6)  # drawn again (a page hidden with display:none and laid out comes back at the top)
    assert await js(f"[{settings}.scrollY, {settings}.marker]") == [1234, 8]  # the same page, never reloaded
    assert await js("document.querySelectorAll('#views iframe').length") == 2  # picked again: no second frame
    assert stack["server"].window_count == 2  # the hidden page's line to the app stayed open


@CHROME
async def test_the_active_tab_is_marked_and_the_others_are_hidden(shell):
    js, _ = shell
    await pick(js, "/settings")
    assert await until(js, connected("/settings"))
    marks = ("[...document.querySelectorAll('#tabs .tab')].map((one) => [one.dataset.key, "
             "one.querySelector('.tab-label').getAttribute('aria-current'), one.classList.contains('active')])")
    assert await js(marks) == [["/mission", None, False], ["/settings", "page", True]]
    shown = ("[...document.querySelectorAll('#views .view')].map((one) => [one.dataset.key, "
             "getComputedStyle(one).visibility, getComputedStyle(one).contentVisibility])")
    assert await js(shown) == [["/mission", "hidden", "hidden"], ["/settings", "visible", "visible"]]
    await pick(js, "/mission")
    assert await js(marks) == [["/mission", "page", True], ["/settings", None, False]]
    assert await js(shown) == [["/mission", "visible", "visible"], ["/settings", "hidden", "hidden"]]


@CHROME
async def test_the_title_follows_the_tab_and_keeps_mission_controls_count(shell):
    js, stack = shell
    assert await until(js, "document.title === 'Mission Control · AI Browser'")
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    agent = await stack["server"].agents.create("keep working")
    assert await until(js, "document.title === '(1) Mission Control · AI Browser'")  # Mission Control counts
    await pick(js, "/settings")
    assert await until(js, "document.title === '(1) Settings · AI Browser'")  # it counts while hidden
    await pick(js, "/mission")
    await stack["server"].agents.stop(agent.id)
    assert await until(js, "document.title === 'Mission Control · AI Browser'")


@CHROME
async def test_the_count_and_a_notifications_click_work_before_mission_control_is_ever_picked(shell):
    js, stack = shell  # a fresh window: Mission Control loads with it (it once loaded only when picked)
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    agent = await stack["server"].agents.create("keep working")
    await pick(js, "/settings")  # the user is on Settings; the test never picks Mission Control
    assert await until(js, "document.title === '(1) Settings · AI Browser'")  # Mission Control counts, unpicked
    assert await until(js, f"{frame('/mission')}.document.querySelector("
                           f"'.station[data-id={json.dumps(agent.id)}]') !== null")
    stack["server"]._send_all({"type": "focus", "agent": agent.id})  # a notification's click
    drawer = f"{frame('/mission')}.document.getElementById('drawer')"
    assert await until(js, f"{active_is('/mission')} && {drawer}.hidden === false")  # its drawer, in front
    await stack["server"].agents.stop(agent.id)


async def mouse_click(js, at) -> None:
    """A real mouse click at (x, y) in the window's page: the browser picks what is under it."""
    for kind in ("mousePressed", "mouseReleased"):
        await js.cdp.send("Input.dispatchMouseEvent", {"type": kind, "x": at[0], "y": at[1], "button": "left",
                                                       "clickCount": 1}, session_id=js.session)


CENTRE = "((box) => [box.x + box.width / 2, box.y + box.height / 2])"


@CHROME
async def test_a_real_click_lands_on_the_tab_shown_never_on_a_hidden_one(shell):
    js, _ = shell
    await pick(js, "/settings")  # a hidden page now lies above Mission Control's in the page
    assert await until(js, connected("/settings"))
    await mouse_click(js, await js(f"{CENTRE}({tab('/mission')}.querySelector('.tab-label').getBoundingClientRect())"))
    assert await until(js, active_is("/mission"))
    task = (f"(() => {{ const frame = {view('/mission')}.querySelector('iframe'); const outer = "
            "frame.getBoundingClientRect(); const box = frame.contentDocument.getElementById('task')"
            ".getBoundingClientRect();"
            "return [outer.x + box.x + box.width / 2, outer.y + box.y + box.height / 2]; })()")
    await mouse_click(js, await js(task))
    assert await until(js, f"{frame('/mission')}.document.activeElement?.id === 'task'")  # Mission Control's box


async def all_pages(stack) -> list[str]:
    """Every page target in the throwaway Chrome: a window opened by any page would add one."""
    return sorted(await page_targets(stack["cdp"], ""))


@CHROME
async def test_our_buttons_switch_tabs_and_never_open_a_window(shell):
    js, stack = shell
    pages = await all_pages(stack)
    await click_in(js, "/mission", "#usage")  # Mission Control's Usage card: Settings → Accounts
    assert await until(js, f"{active_is('/settings')} && {connected('/settings')}")
    await click_in(js, "/settings", "#mission-link")  # Settings' way back: Mission Control
    assert await until(js, active_is("/mission"))
    await click_in(js, "/mission", "#usage")  # open already: shown again, never a second one
    assert await until(js, active_is("/settings"))
    await click_in(js, "/settings", "#mission-link")
    assert await until(js, active_is("/mission"))
    await asyncio.sleep(0.5)
    assert await js(keys()) == ["/mission", "/settings"]
    assert await js("document.querySelectorAll('#views iframe').length") == 2
    assert await all_pages(stack) == pages  # no window of any kind
    assert stack["server"].window_count == 2


@CHROME
async def test_a_link_to_one_of_our_pages_switches_tabs(shell):
    js, stack = shell
    pages = await all_pages(stack)
    await in_frame(js, "/mission", "const ours = document.createElement('a'); ours.id = 'ours';"
                                   "ours.href = '/settings'; ours.target = '_blank'; ours.textContent = 'Settings';"
                                   "document.body.append(ours); true")
    await click_in(js, "/mission", "#ours")
    assert await until(js, f"{active_is('/settings')} && {connected('/settings')}")
    await asyncio.sleep(0.5)
    assert await js(f"{frame('/mission')}.location.pathname") == "/mission"  # the link itself never navigates
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
    assert await js(keys()) == ["/mission", "/settings"] and await all_pages(stack) == pages


@CHROME
async def test_the_setup_steps_open_as_one_closable_tab(shell):
    js, stack = shell
    action = f"{frame('/mission')}.document.querySelector('#brave-bar .brave-action')"
    stack["brave"].set_state("off")
    assert await until(js, f"{action}.textContent === 'Show me how'")
    await click_in(js, "/mission", "#brave-bar .brave-action")  # Brave's switch: its steps, in a closable tab
    assert await until(js, f"{active_is('/setup')} && {frame('/setup')}?.location.hash === '#switch'")
    assert await js(f"{tab('/setup')}.querySelector('.tab-label').textContent") == "Setup"
    assert await js(f"{tab('/setup')}.querySelector('.tab-close').getAttribute('aria-label')") == "Close Setup"
    assert await until(js, "document.title === 'Setup · AI Browser'")
    await pick(js, "/mission")
    await click_in(js, "/mission", "#brave-bar .brave-action")  # again: the same tab
    assert await until(js, f"{active_is('/setup')} && {frame('/setup')}.location.hash === '#switch'")
    assert await js(keys()) == ["/mission", "/settings", "/setup"]
    assert await js("document.querySelectorAll('#views .view').length") == 2  # Mission Control's and the setup's
    await js(f"{tab('/setup')}.querySelector('.tab-close').click(); true")  # its ×
    assert await until(js, f"{tab('/setup')} === null && {view('/setup')} === null && {active_is('/mission')}")
    assert await js("document.title") == "Mission Control · AI Browser"


@CHROME
async def test_show_me_opens_one_live_view_tab_per_agent_and_closing_it_ends_only_that(shell):
    from ai_browser.live import LiveView

    js, stack = shell
    live = LiveView()  # an engine's live view, with no browser behind it
    address = await live.start()
    try:
        agent = await checked(stack, "Flights to Manila", target="Q1", live=address)
        assert await until(js, f"{frame('/mission')}.document.querySelector('.station[data-id=\"{agent.id}\"]') != null")
        await click_in(js, "/mission", f".station[data-id='{agent.id}']")  # it needs the user: its drawer opens
        card = f"{frame('/mission')}.document.querySelector('#drawer-body .bot-check')"
        assert await until(js, f"{card} != null")
        key = f"live:{agent.id}"
        await click_in(js, "/mission", "#drawer-body .bot-check .show-me")
        assert await until(js, active_is(key))
        assert await js(f"{tab(key)}.querySelector('.tab-label').textContent") == "Live view · 1 · Flights to Manila"
        assert await until(js, "document.title === 'Live view · 1 · Flights to Manila · AI Browser'")
        live_frame = f"{view(key)}.querySelector('iframe')"
        assert await js(f"[{live_frame}.getAttribute('src'), {live_frame}.getAttribute('sandbox')]") == [
            address, "allow-scripts"]
        assert await settled(lambda: len(live.viewers) == 1)  # its page is up, with its own line to the live view
        await pick(js, "/mission")
        await click_in(js, "/mission", "#drawer-body .bot-check .show-me")  # Show me again
        assert await until(js, active_is(key))
        await asyncio.sleep(0.5)
        assert await js(keys()) == ["/mission", "/settings", key]  # the same tab, never a second
        assert await js(f"document.querySelectorAll('#views .view[data-key=\"{key}\"]').length") == 1
        assert len(live.viewers) == 1
        windows = stack["server"].window_count
        await js(f"{tab(key)}.querySelector('.tab-close').click(); true")
        assert await settled(lambda: not live.viewers)  # its page has gone, and its socket with it
        assert await js(f"{view(key)} === null && {active_is('/mission')}")
        await asyncio.sleep(0.5)
        assert stack["server"].window_count == windows and await js(connected("/mission"))  # the app runs on
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
        for message in refused:  # from Mission Control's own frame: never a tab
            assert await in_frame(js, "/mission", f"parent.postMessage({json.dumps(message)}, location.origin); true")
        for message in ({"type": "tab", "path": "/settings"}, {"type": "live", "url": address, "agent": "a1"}):
            await js(f"window.postMessage({json.dumps(message)}, location.origin); true")  # the window's own page
        await asyncio.sleep(1)
        assert await js(keys()) == before and await js(active_is("/mission"))
        await in_frame(js, "/mission", "parent.postMessage({type: 'live', url: " + json.dumps(address)
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


# ---- the close-tab key -----------------------------------------------------------------------------------------------

MAC = sys.platform == "darwin"
CLOSE_KEY = {"key": "w", "code": "KeyW", "windowsVirtualKeyCode": 87, "modifiers": 4 if MAC else 2}  # Command / Ctrl
KEPT = ("window.addEventListener('keydown', (event) => { if (event.key === 'w') "  # after every other listener: did one
        "document.documentElement.dataset.kept = String(event.defaultPrevented); }); true")  # keep it from the browser?


def ready_for_keys(key: str) -> str:
    """A tab's own page has loaded (not the new frame's first blank document) and has the keyboard."""
    return (f"{frame(key)}?.location.pathname === {json.dumps(key)} && {frame(key)}.document.readyState === "
            f"'complete' && {frame(key)}.document.hasFocus()")


async def close_key(js) -> None:
    """The close-tab key (Command-W on a Mac, Ctrl+W elsewhere), pressed as a person presses it (CDP Input, as
    test_talk sends keys): it goes to the frame that has the focus. In an app window the browser would close the whole
    window for it unless the page keeps it; headless Chrome never closes one, so these tests look at what our pages do
    with it, and the real window's own close is a hand check."""
    for kind in ("rawKeyDown", "keyUp"):
        await js.cdp.send("Input.dispatchKeyEvent", {"type": kind, **CLOSE_KEY}, session_id=js.session)


@CHROME
async def test_the_close_tab_key_closes_the_tab_shown_if_it_has_a_close_button(shell):
    js, stack = shell
    stack["brave"].set_state("off")
    assert await until(js, f"{frame('/mission')}.document.querySelector('#brave-bar .brave-action')?.textContent === "
                           "'Show me how'")
    await click_in(js, "/mission", "#brave-bar .brave-action")  # Brave's switch: its steps, in a closable tab
    assert await until(js, f"{active_is('/setup')} && {ready_for_keys('/setup')}")
    windows = stack["server"].window_count
    await close_key(js)  # the focus is in the setup steps' page, the tab shown
    assert await until(js, f"{tab('/setup')} === null && {view('/setup')} === null && {active_is('/mission')}")
    await click_in(js, "/mission", "#brave-bar .brave-action")
    assert await until(js, active_is("/setup"))
    await js(f"{tab('/setup')}.querySelector('.tab-label').focus(); true")  # the focus on the window's row of tabs
    await close_key(js)
    assert await until(js, f"{tab('/setup')} === null && {active_is('/mission')}")
    await asyncio.sleep(0.5)
    assert stack["server"].window_count == windows and await js(connected("/mission"))  # the window and lines stay


@CHROME
async def test_the_close_tab_key_closes_nothing_on_a_fixed_tab_and_never_reaches_the_browser(shell):
    js, stack = shell
    for key in ("/settings", "/mission"):
        await pick(js, key)
        assert await until(js, connected(key))
        await in_frame(js, key, KEPT)
        await close_key(js)  # the focus is in that tab's page
        assert await until(js, f"{frame(key)}.document.documentElement.dataset.kept === 'true'")  # it kept the key
        assert await js(keys()) == ["/mission", "/settings"] and await js(active_is(key))
    await js(KEPT)
    await js(f"{tab('/mission')}.querySelector('.tab-label').focus(); true")  # the window's own page, its row of tabs
    await close_key(js)
    assert await until(js, "document.documentElement.dataset.kept === 'true'")
    await asyncio.sleep(0.5)
    assert await js(keys()) == ["/mission", "/settings"] and await js(active_is("/mission"))
    assert stack["server"].window_count == 2  # every page's line to the app stays


@CHROME
async def test_the_close_tab_key_in_a_live_view_never_reaches_the_browser(shell):
    from ai_browser.live import LiveView

    js, stack = shell
    live = LiveView()
    address = await live.start()
    try:
        await in_frame(js, "/mission", "parent.postMessage({type: 'live', url: " + json.dumps(address)
                       + ", agent: 'a1', label: '1 · Live'}, location.origin); true")
        assert await until(js, active_is("live:a1"))
        assert await settled(lambda: len(live.viewers) == 1)
        windows = stack["server"].window_count
        corner = (f"(() => {{ const box = {view('live:a1')}.querySelector('iframe').getBoundingClientRect();"
                  " return [box.x + 40, box.y + 12]; })()")
        await mouse_click(js, await js(corner))  # into the live view's page, beside its picture: its own focus
        await in_frame(js, "live:a1", KEPT)
        await close_key(js)
        await asyncio.sleep(0.5)
        assert await in_frame(js, "live:a1", "document.documentElement.dataset.kept") == "true"  # kept from the browser
        assert await js(active_is("live:a1"))  # another origin's page can't ask the window for anything: × closes it
        assert stack["server"].window_count == windows and len(live.viewers) == 1
    finally:
        await live.stop()
