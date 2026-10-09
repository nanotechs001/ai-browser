"""AI Home's features, found in Mission Control and Settings (the saved-agents spec, 6): Brave's connection, Settings →
Brave, the Tabs page, a one-off run's skills, the drawer's run pieces, the Brain's limit card, a notification's click
and the window's count. Against a real app server (agents on the fake claude) in a throwaway headless Chrome; every
word stays text."""

import pytest

from ai_browser.chrome import chrome_binary
from test_app_server import wait_for
from test_home import open_settings, stack, until  # noqa: F401  (fixtures)
from test_mission import open_mission

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
BAR = "document.getElementById('brave-bar')"


# ---- Brave's connection, at the top of Mission Control (Task 9) ------------------------------------------------------

@CHROME
async def test_mission_control_shows_braves_connection_until_it_is_connected(stack):
    brave = stack["brave"]
    js = await open_mission(stack)
    assert await until(js, f"{BAR}.hidden === true")  # connected: nothing to say
    brave.set_state("off")
    assert await until(js, f"!{BAR}.hidden && {BAR}.querySelector('.brave-title').textContent"
                           " === 'Your Brave · switch off'")
    assert await js(f"[...{BAR}.querySelectorAll('.brave-steps li')].map(item => item.textContent)") == [
        "In Brave, open brave://inspect/#remote-debugging.", 'Tick "Allow remote debugging for this browser instance".',
        'When Brave asks "Allow remote debugging?", click Allow.']
    assert await js(f"{BAR}.querySelector('.brave-action').textContent") == "Show me how"
    brave.set_state("ready")
    assert await until(js, f"{BAR}.querySelector('.brave-action').textContent === 'Connect'"
                           f" && {BAR}.querySelector('.brave-steps').hidden")
    await js(f"{BAR}.querySelector('.brave-action').click(); true")
    await wait_for(lambda: brave.connects == 1)  # Connect: the app asks Brave, which asks the user once
    brave.set_state("asking")
    assert await until(js, f"{BAR}.querySelector('.brave-action').hidden && {BAR}.querySelector('.brave-note')"
                           ".textContent.startsWith('Brave is asking \"Allow remote debugging?\"')")
    brave.set_state("refused")
    assert await until(js, f"{BAR}.querySelector('.brave-action').textContent === 'Try again'"
                           f" && {BAR}.querySelector('.brave-note').textContent === 'Brave said no.'")
    brave.set_state("connected")
    assert await until(js, f"{BAR}.hidden === true")
    brave.set_state("off")
    assert await until(js, f"!{BAR}.hidden")
    await js(f"{BAR}.querySelector('.brave-action').click(); true")  # Show me how: the setup steps' own page
    assert await until(js, "location.pathname === '/setup' && location.hash === '#switch'")


# ---- Settings → Brave: what uses Brave through AI Browser, Brave's old extension; Settings' own styles (Task 10) ----

CLIENTS = [
    {"id": "app", "kind": "app", "number": None, "name": "AI Browser", "color": "", "tabs": 0, "connected": True,
     "cut_off": False},
    {"id": "a3", "kind": "agent", "number": 3, "name": "Fix the footer", "color": "blue", "tabs": 2, "connected": True,
     "cut_off": False},
    {"id": "cc-x", "kind": "session", "number": None, "name": "Claude Code", "color": "orange", "tabs": 1,
     "connected": True, "cut_off": False},
    {"id": "a4", "kind": "agent", "number": 4, "name": "<img src=x onerror=alert(1)>", "color": "red", "tabs": 0,
     "connected": True, "cut_off": False}]


@CHROME
async def test_settings_lists_what_uses_brave_with_disconnect(stack):
    server, brave = stack["server"], stack["brave"]
    settings = await open_settings(stack)
    assert await until(settings, "document.getElementById('brave-state').textContent"
                                 " === 'Brave is connected to AI Browser.'")
    server._send_all({"type": "browser_clients", "clients": CLIENTS})
    labels = "[...document.querySelectorAll('#brave-clients li span')].map(span => span.textContent)"
    assert await until(settings, f"{labels}.length === 4")
    assert await settings(labels) == ["AI Browser · the tab list and pictures", "3 · Fix the footer · 2 tabs",
                                      "Claude Code · 1 tab", "4 · <img src=x onerror=alert(1)> · 0 tabs"]
    assert await settings("document.querySelectorAll('#brave-clients img').length") == 0  # text stays text
    assert await settings("[...document.querySelectorAll('#brave-clients li')].map(li => !!li.querySelector("
                          "'button'))") == [False, True, True, True]
    assert await settings("document.getElementById('brave-using-title').textContent") == (
        "Using your Brave through AI Browser")
    await settings("document.querySelectorAll('#brave-clients li')[1].querySelector('button').click(); true")
    await wait_for(lambda: brave.relay.disconnected == ["a3"])
    brave.set_state("lost")
    assert await until(settings, "document.getElementById('brave-state').textContent === \"Brave isn't connected: "
                                 "connect it at the top of Mission Control.\" && document.getElementById('brave-using')"
                                 ".hidden")
    assert await settings("getComputedStyle(document.querySelector('.card')).borderRadius") == "12px"  # its own styles
    assert await settings("[...document.styleSheets].map(sheet => sheet.href.split('/').pop())") == [
        "theme.css", "settings.css"]


@CHROME
async def test_settings_says_the_old_extension_can_be_removed_until_got_it(stack):
    server = stack["server"]
    settings = await open_settings(stack)
    note = "document.getElementById('watcher-note')"
    assert await settings(f"{note}.hidden") is True  # no old folder here: nothing to say
    folder = stack["home"] / "app" / "watcher"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text("{}", encoding="utf-8")  # an earlier AI Browser made it
    server._send_all({"type": "settings", **server._settings_payload()})
    assert await until(settings, f"!{note}.hidden")
    text = " ".join((await settings(f"{note}.textContent")).split())
    assert 'You can remove "AI Browser Watcher" from Brave' in text and "AI Browser never removes it for you." in text
    await settings("document.getElementById('watcher-note-close').click(); true")
    await wait_for(lambda: server.settings.get()["watcher_note"] is False)
    assert (folder / "manifest.json").is_file()  # AI Browser never removes it
    server._send_all({"type": "settings", **server._settings_payload()})
    assert await until(settings, f"{note}.hidden")
