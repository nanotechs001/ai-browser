"""The Brain's reading and Use draft end to end: a real app server and BraveLink, the relay's one connection to a
throwaway headless Chrome, and the fake Gmail on an address of its own. The user's inbox tab is read in an isolated
world, a thread opens in a background tab marked Brain, Use draft puts the reply in its reply box above the signature,
and nothing clicks Send."""

import json

import pytest

from ai_browser.chrome import chrome_binary
from fake_brave import until
from fake_sites import inbox_sites  # noqa: F401  (a fixture)

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
NEEDS = [{"id": "gmail:t1", "kind": "needs_reply", "summary": "Maria asks to move the launch", "why": "a client",
          "suggest": "draft"}]


@CHROME
async def test_the_fake_gmail_is_read_and_use_draft_fills_it_through_the_relay(fake_claude, throwaway_chrome,
                                                                              tmp_path, inbox_sites):
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.bravelink import BraveLink
    from ai_browser.app.server import AppServer
    from ai_browser.brain.service import BrainService
    from ai_browser.brain.store import BrainStore
    from ai_browser.cdp import CDP
    from ai_browser.chrome import find_ws_url
    from test_brain_service import DRAFT, dict_script
    from test_home import open_page, page_js
    from ui_socket import ui_socket

    runner, _, script = fake_claude
    script.write_text(json.dumps(dict_script(NEEDS)), encoding="utf-8")
    home = tmp_path / "home"
    agents = AgentManager(home, claude=runner)
    brain = BrainService(BrainStore(home), agents, claude=runner, batch_wait=0.1)
    server = AppServer(home, agents, brain=brain)
    url = await server.start()
    brave = BraveLink(throwaway_chrome, every=0.1, tokens=server.tokens)
    server.attach_brave(brave)
    await brave.start()
    await brave.connect()
    own = await CDP.connect(find_ws_url(throwaway_chrome, timeout=20))  # the user, by hand
    try:
        inbox, page = await open_page(own, inbox_sites["gmail"] + "brain/gmail.html")
        async with ui_socket(server, url) as settings:  # Settings → Brain → Read my Gmail, Slack and Asana tabs
            await settings.send(json.dumps({"type": "hello", "view": "settings"}))
            await settings.send(json.dumps({"type": "settings_set", "key": "read_tabs", "value": True}))
            assert await until(lambda: brain.store.get("gmail:t1") is not None, 20)
        assert await page("typeof globalThis.AIB") == "undefined"  # the page never sees the reader
        await brain.draft("gmail:t1")
        item = brain.store.get("gmail:t1")
        assert item.state == "draft_ready" and item.draft == DRAFT, item.note
        thread = next(tab for tab in brave.tabs() if tab["url"].endswith("#all/t1"))
        assert thread["owner"] == {"kind": "brain", "name": "Brain", "color": "purple"}  # opened for the Brain
        await brain.approve("gmail:t1", DRAFT, item.draft_version)  # the user's Use draft
        assert await until(lambda: brain.store.get("gmail:t1").state == "filled", 20)
        js = await page_js(own, thread["target"])
        box = await js("document.getElementById('box').innerText")
        assert box.index(DRAFT) < box.index("-- Alex, Web team")  # above the signature, which stays
        assert await js("window.sendClicks") == 0  # nothing pressed Send
        assert await page("window.sendClicks") == 0
        assert brave.relay.upstream_opens == 1  # one connection: Brave asked "Allow remote debugging?" once
    finally:
        await own.close()
        await server.stop()
        await brave.close()
