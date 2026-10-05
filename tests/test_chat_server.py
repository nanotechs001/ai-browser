"""The floating chat and the app server (app/server.py): "This page" matched to the tab list, and Open AI Home. The
server never connects to Brave for the chat: Brave not running or not connected is answered, never fixed."""

import json

from fake_brave import FakeBrave, add_agent
from fake_desktop import FakeDesktop
from test_app_server import recv, started, until
from test_bridge import EVENTS
from ui_socket import ui_socket

CART = {"target": "U1", "url": "https://shop.example/cart", "title": "Cart"}
NEWS = {"target": "U2", "url": "https://news.example/", "title": "News"}


async def hello(ws):
    await ws.send(json.dumps({"type": "hello", "view": "chat"}))
    assert (await recv(ws))["type"] == "snapshot"


async def this_page(ws, request, **found):
    await ws.send(json.dumps({"type": "this_page", "request": request, **found}))
    return (await until(ws, lambda message: message["type"] == "this_page"))[-1]


async def test_this_page_is_matched_to_the_tab_list(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    server.attach_brave(FakeBrave([CART, NEWS]))
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            assert await this_page(ws, "p1", url="shop.example/cart", title="Cart") == {
                "type": "this_page", "request": "p1", "state": "found", "tab": {**CART, "owner": {"kind": "you"}}}
            assert (await this_page(ws, "p2", url="https://bank.example/", title="Bank"))["state"] == "choose"
            assert (await this_page(ws, "p3", url=7, title="Cart"))["state"] == "choose"  # not what the app reads
    finally:
        await server.stop()


async def test_this_page_never_connects_and_says_why_not(fake_claude, tmp_path):  # Review Focus 2
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            assert await this_page(ws, "p1", url=CART["url"], title="Cart") == {
                "type": "this_page", "request": "p1", "state": "not_connected", "browser": "off"}  # no Brave link
            brave = FakeBrave([CART], state="ready")  # Brave runs, but isn't connected to AI Browser
            server.attach_brave(brave)
            assert (await this_page(ws, "p2", url=CART["url"], title="Cart"))["browser"] == "ready"
            brave.set_state("asking")  # Brave asks "Allow remote debugging?": the user answers it, in Brave
            answer = await this_page(ws, "p3", url=CART["url"], title="Cart")
            assert answer["state"] == "not_connected" and answer["browser"] == "asking"
            assert brave.connects == 0  # the chat's look never connects: Brave asks nothing new
    finally:
        await server.stop()


async def test_open_ai_home_brings_the_window_forward_at_the_agent(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    desktop = FakeDesktop()
    server.attach_desktop(desktop)
    add_agent(server.agents, "a1")
    asked = [({"agent": "a1"}, {"agent": "a1"}), ({"brain": True}, {"brain": True}), ({}, {}),
             ({"agent": "../x"}, {}), ({"agent": "a1", "brain": True}, {"agent": "a1"})]
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            for sent, focus in asked:
                await ws.send(json.dumps({"type": "show_app", **sent}))
                assert (await until(ws, lambda message: message["type"] == "focus"))[-1] == {"type": "focus", **focus}
        assert desktop.sent == [{"type": "show"}] * len(asked)
    finally:
        await server.stop()
