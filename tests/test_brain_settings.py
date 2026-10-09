"""Settings → Brain (native app part b): the switch, how reading goes, and Pick the part to watch. The pick runs in
one of the user's open tabs in Brave, only on their click and only while the switch is on; a pick the switch ends
keeps nothing. On the server with the user's Brave faked, then the real picker in a throwaway headless Chrome through
the relay, then the pages."""

import asyncio
import json
from urllib.parse import urlsplit

import pytest

from ai_browser.chrome import chrome_binary
from fake_brave import until
from fake_reading import ReadingBrave
from test_app_server import recv, with_brain
from test_app_server import until as told
from test_home import page, open_page, open_settings, stack  # noqa: F401  (fixtures)
from test_home import until as page_until
from ui_socket import ui_socket

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
SHOP = "https://shop.example/orders"


def picking_brave():
    """The user's Brave with one web tab of theirs (U3) and an agent's (A1); a pick there answers what a test sets."""
    brave = ReadingBrave([{"target": "U3", "url": SHOP, "site": "custom:shop.example"}])
    brave.pages = [{"target": "U3", "url": SHOP, "title": "Orders"}, {"target": "A1", "url": SHOP, "title": "Agent"}]
    brave.owners["A1"] = {"kind": "agent", "id": "a1", "name": "Fix the footer", "color": "blue"}
    return brave


async def pick(page, target, request="p"):
    await page.send(json.dumps({"type": "watch_pick", "target": target, "request": request}))
    return (await told(page, lambda m: m["type"] == "watch_picked" and m["request"] == request))[-1]


async def test_a_pick_needs_brave_the_switch_and_one_of_the_users_tabs(fake_claude, tmp_path):  # Review Focus 1
    from ai_browser.app.bravelink import NOT_CONNECTED
    from ai_browser.app.server import PICK_OFF, PICK_TAB

    server, url, brain = await with_brain(fake_claude, tmp_path, [{"result": "[]"}])
    try:
        async with ui_socket(server, url) as page:
            await page.send(json.dumps({"type": "hello", "view": "settings"}))
            await recv(page)
            assert (await pick(page, "U3", "p1"))["error"] == NOT_CONNECTED  # no Brave at all
            brave = picking_brave()
            brave.set_state("lost")
            server.attach_brave(brave)
            assert (await pick(page, "U3", "p2"))["error"] == NOT_CONNECTED  # Brave not connected: never asked
            brave.set_state("connected")
            assert (await pick(page, "U3", "p3"))["error"] == PICK_OFF  # the switch is off
            server.settings.set("read_tabs", True)
            for target in ("A1", "NO-SUCH-TAB", None):  # an agent's tab, a tab that isn't there, no tab
                assert (await pick(page, target, f"p-{target}"))["error"] == PICK_TAB
        assert brave.calls == [] and brave.watched == [] and brave.connects == 0
        assert [entry.site for entry in brain.store.watch()] == ["gmail", "slack", "asana"]
    finally:
        await server.stop()


async def test_a_picked_part_is_watched_and_a_pick_the_switch_ends_keeps_nothing(fake_claude, tmp_path):
    server, url, brain = await with_brain(fake_claude, tmp_path, [{"result": "[]"}])
    brave = picking_brave()
    brave.answers[("U3", "pick")] = {"selector": "#orders tbody", "sample": "Order 1001 · 2 items"}
    server.attach_brave(brave)
    server.settings.set("read_tabs", True)
    try:
        async with ui_socket(server, url) as page:
            await page.send(json.dumps({"type": "hello", "view": "settings"}))
            await recv(page)
            picked = await pick(page, "U3", "p1")
            assert picked["site"] == "custom:shop.example" and picked["sample"] == "Order 1001 · 2 items"
            entry = brain.store.entry("custom:shop.example")
            assert entry.selector == "#orders tbody" and entry.url_match == "https://shop.example/orders*"
            assert entry.enabled and brave.watched == ["U3"]  # the tab came forward for the pick
            brain.remove_watch("custom:shop.example")
            brave.hold = asyncio.Event()  # the next pick waits for the user's click in Brave
            await page.send(json.dumps({"type": "watch_pick", "target": "U3", "request": "p2"}))
            assert await until(lambda: len(brave.reads("pick")) == 2)
            await page.send(json.dumps({"type": "settings_set", "key": "read_tabs", "value": False}))
            ended = (await told(page, lambda m: m["type"] == "watch_picked" and m["request"] == "p2"))[-1]
            assert ended.get("cancelled") is True and brave.ended == ["U3"]  # the outline leaves the page
            brave.hold.set()  # the click comes after all
            await asyncio.sleep(0.3)
        assert brain.store.entry("custom:shop.example") is None  # nothing from that pick was kept
    finally:
        await server.stop()


@CHROME
async def test_the_picker_picks_in_the_users_tab_through_the_relay(fake_claude, throwaway_chrome, tmp_path):
    from ai_browser import testpages
    from ai_browser.app.bravelink import BraveLink
    from ai_browser.cdp import CDP
    from ai_browser.chrome import find_ws_url

    base, _, stop_pages = testpages.serve_host()
    server, url, brain = await with_brain(fake_claude, tmp_path, [{"result": "[]"}])
    brave = BraveLink(throwaway_chrome, every=0.1, tokens=server.tokens)
    server.attach_brave(brave)
    await brave.start()
    await brave.connect()
    own = await CDP.connect(find_ws_url(throwaway_chrome, timeout=20))  # the user, by hand
    try:
        orders, js = await open_page(own, base + "brain/orders.html")
        assert await until(lambda: any(tab["target"] == orders for tab in brave.tabs()), 10)
        server.settings.set("read_tabs", True)
        async with ui_socket(server, url) as page:
            await page.send(json.dumps({"type": "hello", "view": "settings"}))
            await recv(page)
            await page.send(json.dumps({"type": "watch_pick", "target": orders, "request": "p1"}))
            box = None
            for _ in range(100):  # the picker is in place once the page has AI Browser's outline
                box = await js("(() => { const t = document.querySelector('#orders tbody');"
                               " const r = t.getBoundingClientRect(); return [r.x + 5, r.y + 5]; })()")
                if await js("[...document.documentElement.children].some((n) => n.style?.zIndex === '2147483647')"):
                    break
                await asyncio.sleep(0.1)
            for kind in ("mouseMoved", "mousePressed", "mouseReleased"):  # the user's click, as Brave sends it
                await own.send("Input.dispatchMouseEvent", {"type": kind, "x": box[0], "y": box[1], "button": "left",
                                                            "clickCount": 1}, session_id=js.session)
            picked = (await told(page, lambda m: m["type"] == "watch_picked"))[-1]
        site = "custom:" + urlsplit(base).hostname
        assert picked["site"] == site and picked["sample"], picked
        entry = brain.store.entry(site)
        assert entry.selector and entry.url_match.endswith("/brain/orders.html*")
        assert await js(f"document.querySelectorAll({json.dumps(entry.selector)}).length") == 1
        assert await js("typeof globalThis.AIB") == "undefined"  # the page never saw the picker
        assert brave.relay.upstream_opens == 1
    finally:
        await own.close()
        await server.stop()
        await brave.close()
        stop_pages()


@CHROME
async def test_settings_brain_has_the_switch_and_the_brains_inbox_says_when_reading_is_off(page):
    js, stack = page
    await js("document.getElementById('bubble').click(); true")  # Mission Control's globe: the Brain's inbox
    settings = await open_settings(stack)
    assert await settings("document.getElementById('read-tabs').checked") is False  # off until the user turns it on
    assert await page_until(settings, "document.getElementById('reading-state').textContent.startsWith('Off')")
    assert await settings("document.getElementById('pick-start').disabled") is True
    assert await page_until(js, "document.querySelector('#drawer-body .brain-reading')?.textContent === "
                                "'Reading your tabs is off'")
    assert await js("document.querySelector('#drawer-body .brain-turn-on').hidden") is False
    await settings("document.getElementById('read-tabs').click()")
    assert await page_until(settings, "document.getElementById('read-tabs').checked === true")
    for _ in range(50):
        if stack["server"].settings.get()["read_tabs"]:
            break
        await asyncio.sleep(0.1)
    assert stack["server"].settings.get()["read_tabs"] is True
    assert await page_until(js, "document.querySelector('#drawer-body .brain-turn-on').hidden === true")
    names = "[...document.querySelectorAll('#brain-sites .brain-site strong')].map((n) => n.textContent)"
    assert await page_until(settings, f"{names}.join() === 'Gmail,Slack,Asana'")
