"""AI Browser's window as one page with a tab menu (/app): AI Home, Mission Control and Settings in tabs that keep
their state while hidden, and a title that follows the tab. Drawn in a throwaway headless Chrome against a real app
server (agents on the fake claude), with the window's cookie taken the real way (the `stack` fixture)."""

import json

import pytest

from ai_browser.chrome import chrome_binary
from fake_brave import until as settled
from test_bridge import EVENTS
from test_home import stack, until  # noqa: F401  (fixture)

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
WORKING = [EVENTS[0], {"sleep": 30}]  # an agent that stays at work


def tab(key: str) -> str:
    """A tab in the bar, by its key ("/home", "/mission", "/settings")."""
    return f"document.querySelector('#tabs .tab[data-key={json.dumps(key)}]')"


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
    assert await settled(lambda: stack["server"].window_count == 2)
    await pick(js, "/home")
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

