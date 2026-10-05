"""AI Browser's own app on AI Browser's pages, in a throwaway headless Chrome against a real app server (the `stack`
fixture):
- Settings → AI Browser app: the app's state, the shortcut, the setup command, and what went wrong;
- AI Home's offer of the setup;
- a notification's click landing on AI Home's row;
- the microphone's steps naming AI Browser.
The app is a fake (tests/fake_desktop.py). Every text is set as text."""

import asyncio
import json

import pytest

from ai_browser.chrome import chrome_binary
from fake_brave import add_agent
from fake_desktop import FakeDesktop
from test_home import home, open_page, stack, until  # noqa: F401  (fixtures)

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
PROBLEM = "The download stopped before the end: nothing was kept"


def tell_pages(stack) -> None:
    server = stack["server"]
    server._send_all({"type": "settings", **server._settings_payload()})


async def open_settings(stack):
    _, js = await open_page(stack["cdp"], stack["url"] + "/settings")  # the stack's browser has the window's cookie
    assert await until(js, "document.getElementById('status').dataset.state === 'connected'")
    return js


@CHROME
async def test_settings_says_the_shortcut_is_taken_and_offers_another(stack):  # Review Focus 1
    from ai_browser.desktop.shortcut import SHORTCUTS, label
    from ai_browser.settings import read_settings

    app = FakeDesktop()
    stack["server"].attach_desktop(app)
    settings = await open_settings(stack)
    app.says({"type": "shortcut", "value": "Alt+Space", "ok": False, "why": "taken", "pressed": False})
    taken = f"{label('Alt+Space')} is used by another app, so it does nothing here. Pick another shortcut."
    assert await until(settings, f"document.getElementById('shortcut-note').textContent === {json.dumps(taken)}")
    assert await settings("document.getElementById('app-state').textContent") == "AI Browser runs as its own app."
    assert await settings("document.getElementById('window-section').hidden") is True  # the window's browser: unused
    assert await settings("[...document.querySelectorAll('#shortcut-choices label')].map((one) => one.textContent)"
                          ) == [label(one) for one in SHORTCUTS] + ["Off"]
    await settings("document.querySelector('#shortcut-choices input[value=\"Alt+Shift+Space\"]').click(); true")
    ready = (f"{label('Alt+Shift+Space')} shows and hides the chat. Press it once to check: if another app answers "
             "instead, pick another shortcut.")
    assert await until(settings, f"document.getElementById('shortcut-note').textContent === {json.dumps(ready)}")
    assert read_settings(stack["home"])["shortcut"] == "Alt+Shift+Space"
    assert await settings("document.querySelector('#shortcut-choices input:checked').value") == "Alt+Shift+Space"


@CHROME
async def test_settings_says_what_the_shortcut_does(stack):  # Review Focus 1
    stack["server"].attach_desktop(FakeDesktop())
    settings = await open_settings(stack)
    what = "document.getElementById('shortcut-what').textContent"
    assert await until(settings, f"{what}.startsWith('The shortcut shows and hides the floating chat from any app.')")
    platform = stack["server"]._desktop_payload()["platform"]
    if platform == "mac":
        assert "opens from its Dock icon, or Open AI Browser in the menu-bar icon" in await settings(what)
    elif platform == "windows":
        assert "opens from the taskbar, or Open AI Browser in the icon by the clock" in await settings(what)


@CHROME
async def test_a_shortcut_the_app_cant_take_leaves_the_one_before_checked(stack):
    from ai_browser.desktop.shortcut import label

    stack["server"].attach_desktop(FakeDesktop(answers={"Control+Shift+Space": {"ok": False, "why": "taken"}}))
    settings = await open_settings(stack)
    await settings("document.querySelector('#shortcut-choices input[value=\"Control+Shift+Space\"]').click(); true")
    said = f"{label('Control+Shift+Space')} is used by another app. Pick another one."
    assert await until(settings, f"document.getElementById('shortcut-note').textContent === {json.dumps(said)}")
    assert await settings("document.querySelector('#shortcut-choices input:checked').value") == "Alt+Space"


@CHROME
async def test_settings_and_ai_home_offer_the_app_and_say_what_went_wrong(home, monkeypatch):  # Review Focus 2
    from ai_browser.app import server as server_module
    from ai_browser.desktop import layout
    from ai_browser.desktop.release import ASSETS, SETUP_COMMAND

    js, stack = home
    monkeypatch.setattr(server_module, "asset_for", lambda system=None, machine=None: ASSETS[0])  # the app runs here
    layout.set_problem(stack["home"], PROBLEM)
    tell_pages(stack)
    said = f"The last try didn't work: {PROBLEM}"
    assert await until(js, "!document.getElementById('app-card').hidden")
    assert await js("document.getElementById('app-card-command').textContent") == SETUP_COMMAND
    assert await js("document.getElementById('app-card-problem').textContent") == said
    settings = await open_settings(stack)
    assert await until(settings, "!document.getElementById('app-setup').hidden")
    assert await settings("document.getElementById('app-command').textContent") == SETUP_COMMAND
    assert await settings("document.getElementById('app-problem').textContent") == said
    assert await settings("document.getElementById('app-state').textContent") == ("AI Browser runs in a browser "
                                                                                 "window now.")
    assert await settings("document.getElementById('window-section').hidden") is False  # a browser window is in use
    await js("document.getElementById('app-card-close').click(); true")  # Not now
    assert await until(js, "document.getElementById('app-card').hidden")


@CHROME
async def test_ai_home_offers_nothing_while_the_app_runs(home, monkeypatch):
    from ai_browser.app import server as server_module
    from ai_browser.desktop.release import ASSETS

    js, stack = home
    monkeypatch.setattr(server_module, "asset_for", lambda system=None, machine=None: ASSETS[0])
    stack["server"].attach_desktop(FakeDesktop())
    tell_pages(stack)
    await asyncio.sleep(0.5)
    assert await js("document.getElementById('app-card').hidden") is True


@CHROME
async def test_a_notifications_click_lands_on_the_agents_row_or_the_brain(home):
    js, stack = home
    server = stack["server"]
    add_agent(server.agents, "a1")
    server._send_all({"type": "agent", "agent": server.agents.agents["a1"].public()})
    row = "document.querySelector('#agents .agent[data-id=\"a1\"]')"
    assert await until(js, f"{row} !== null")
    server._send_all({"type": "focus", "agent": "a1"})
    assert await until(js, f"{row}.classList.contains('focus')")
    server._send_all({"type": "focus", "brain": True})
    assert await until(js, "document.getElementById('brain').classList.contains('focus')")
    assert await js("location.pathname") == "/home"  # AI Home by itself (here): no tab menu to ask, it stays put


@CHROME
async def test_the_microphones_steps_name_ai_browser_in_its_own_app(home):
    js, _ = home
    name = await js("import('/talk.js').then(({ browserName }) => browserName({ userAgent: 'Mozilla/5.0 "
                    "(Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) ai-browser-app/0.1.0 "
                    "Chrome/150.0.0.0 Electron/44.5.1 Safari/537.36', userAgentData: { brands: [{ brand: 'Chromium' "
                    "}] } }))")
    assert name == "AI Browser"
