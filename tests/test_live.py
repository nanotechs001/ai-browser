import asyncio
import base64
import json

import httpx
import pytest
from websockets.asyncio.client import connect

from ai_browser import testpages
from ai_browser.browser import Browser
from ai_browser.cdp import CDP
from ai_browser.config import Config
from ai_browser.engine import Engine
from ai_browser.live import LiveView
from ai_browser.skills import Catalog
from ai_browser.workfs import WorkDir

pytestmark = pytest.mark.docker


@pytest.fixture
async def env(sandbox):
    boxes, info = sandbox
    base, _ = testpages.serve(boxes, info)
    cdp = await CDP.connect(boxes.ws_url(info))
    browser = Browser(cdp, WorkDir(info.work_host, "pytest-live"), Config())
    await browser.start()
    live = LiveView(ports=range(8795, 8810))
    url = await live.start()
    await live.attach(browser)
    yield browser, live, url, base
    await live.stop()
    await browser.close()
    await cdp.close()


def ws_url(url: str) -> str:
    return url.replace("http://", "ws://").replace("/live?", "/live/ws?")


async def next_frame(ws) -> dict:
    while True:
        message = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        if message["t"] == "frame":
            return message


async def test_page_needs_the_token(env):
    _, _, url, _ = env
    async with httpx.AsyncClient() as client:
        page = await client.get(url)
        assert page.status_code == 200 and "live view" in page.text
        assert (await client.get(url.split("?")[0])).status_code == 403
        assert (await client.get(url.split("?")[0] + "?token=wrong")).status_code == 403


async def test_websocket_streams_jpeg_frames(env):
    browser, _, url, base = env
    await browser.open(base + "form.html")
    async with connect(ws_url(url)) as ws:
        frame = await next_frame(ws)
    assert base64.b64decode(frame["data"])[:2] == b"\xff\xd8"
    assert (frame["w"], frame["h"]) == (1440, 900)


async def test_wrong_token_websocket_is_refused(env):
    _, _, url, _ = env
    with pytest.raises(Exception):
        async with connect(ws_url(url).split("token=")[0] + "token=wrong") as ws:
            await asyncio.wait_for(ws.recv(), timeout=3)


async def test_viewer_clicks_and_types_reach_the_page(env):
    browser, _, url, base = env
    await browser.open(base + "form.html")
    x, y = await browser._eval(
        "(() => { const r = document.getElementById('inc').getBoundingClientRect();"
        " return [r.left + r.width / 2, r.top + r.height / 2]; })()")
    nx, ny = await browser._eval(
        "(() => { const r = document.getElementById('notes').getBoundingClientRect();"
        " return [r.left + r.width / 2, r.top + r.height / 2]; })()")
    async with connect(ws_url(url)) as ws:
        await next_frame(ws)
        for event in ("down", "up"):
            await ws.send(json.dumps({"t": "mouse", "e": event, "x": x, "y": y, "b": "left", "c": 1}))
        for event in ("down", "up"):
            await ws.send(json.dumps({"t": "mouse", "e": event, "x": nx, "y": ny, "b": "left", "c": 1}))
        await ws.send(json.dumps({"t": "text", "text": "typed by a human"}))
        await asyncio.sleep(0.3)
    assert await browser._eval("document.getElementById('count').textContent") == "1"
    assert await browser._eval("document.getElementById('notes').value") == "typed by a human"


async def test_screencast_stops_when_the_last_viewer_leaves(env):
    browser, live, url, base = env
    await browser.open(base + "form.html")
    async with connect(ws_url(url)) as ws:
        await next_frame(ws)
        assert live.streaming
    await asyncio.sleep(0.3)
    assert not live.streaming


async def test_a_port_taken_at_the_last_moment_does_not_kill_the_server(monkeypatch):
    import socket

    from ai_browser import live as live_module

    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen()
    port = blocker.getsockname()[1]
    monkeypatch.setattr(live_module, "_free", lambda host, p: True, raising=False)  # probe says free: a race
    try:
        with pytest.raises(RuntimeError, match="no free port"):
            await LiveView(ports=range(port, port + 1)).start()
    finally:
        blocker.close()


async def test_engine_reports_its_live_view(tmp_path):
    engine = Engine(home=tmp_path, catalog=Catalog([], set()))
    try:
        started = await engine.sandbox_start(fresh=True)
        line = next(line for line in started.text.splitlines() if line.startswith("live view: "))
        url = line.removeprefix("live view: ")
        assert url.startswith("http://127.0.0.1:") and "token=" in url
        async with httpx.AsyncClient() as client:
            assert (await client.get(url)).status_code == 200
    finally:
        await engine.close()
