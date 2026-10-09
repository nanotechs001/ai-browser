"""AI Home's features, found in Mission Control and Settings (the saved-agents spec, 6): Brave's connection, Settings →
Brave, the Tabs page, a one-off run's skills, the drawer's run pieces, the Brain's limit card, a notification's click
and the window's count. Against a real app server (agents on the fake claude) in a throwaway headless Chrome; every
word stays text."""

import pytest

from ai_browser.chrome import chrome_binary
from test_app_server import wait_for
from test_home import stack, until  # noqa: F401  (fixtures)
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
