"""Through the app's relay, in a throwaway headless Chrome (started with --remote-debugging-port=0, which never asks):
two agents' engines on one connection, Take back, a reconnect, and the live view with thumbnails."""

import asyncio
import base64
import json

import pytest
from websockets.asyncio.client import connect

from ai_browser import testpages
from ai_browser.app.agents import AgentManager
from ai_browser.app.bravelink import BraveLink
from ai_browser.app.cdprelay import LocalClient
from ai_browser.app.server import AppServer
from ai_browser.cdp import CDP
from ai_browser.chrome import chrome_binary, find_ws_url
from ai_browser.engine import Engine
from ai_browser.skills import Catalog
from fake_brave import add_agent, until

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
SECRET = "data:text/html,<title>SECRET-7f3a</title><p>the user's own page"


@pytest.fixture
async def relayed(throwaway_chrome, tmp_path):
    """(app server in brave mode, its BraveLink on the throwaway Chrome, connected; the test pages' base URL; the
    test's own direct CDP connection, standing in for the user)."""
    base, _, stop_pages = testpages.serve_host()
    home = tmp_path / "home"
    agents = AgentManager(home)
    server = AppServer(home, agents)
    await server.start()
    brave = BraveLink(throwaway_chrome, every=0.1, tokens=server.tokens)
    server.attach_brave(brave)
    agents.close_tabs = brave.close_targets
    await brave.start()
    await brave.connect()
    own = await CDP.connect(find_ws_url(throwaway_chrome, timeout=20))
    yield server, brave, base, own
    await own.close()
    await server.stop()
    await brave.close()
    stop_pages()


def agent_engine(server, folder, tmp_path, monkeypatch, agent):
    """An engine set up as ai-browser app sets up an agent's: through the relay, with its own token."""
    monkeypatch.setenv("AIB_BROWSER", "chrome")
    monkeypatch.setenv("AIB_CHROME_DIR", str(folder))
    monkeypatch.setenv("AIB_APP_AGENT", agent)
    monkeypatch.setenv("AIB_APP_EVENTS", server.url + "/agent-events")
    monkeypatch.setenv("AIB_APP_AGENT_TOKEN", server.token_for(agent))
    monkeypatch.setenv("AIB_APP_CDP", server.url.replace("http://", "ws://", 1) + "/cdp")
    return Engine(home=tmp_path / f"engine-{agent}", catalog=Catalog([], set()))


def ok(result):
    assert not result.text.startswith("error"), result.text
    return result.text


async def pages(own) -> set[str]:
    return {info["targetId"] for info in (await own.send("Target.getTargets"))["targetInfos"] if info["type"] == "page"}


@CHROME
async def test_two_engines_one_upstream_and_only_their_own_tabs(relayed, throwaway_chrome, tmp_path, monkeypatch):
    server, brave, base, own = relayed
    await own.send("Target.createTarget", {"url": SECRET})  # the user's own tab
    frames, dispatch = [], CDP._dispatch

    def spy(self, message):  # every frame an engine's connection gets (not the app's, not the test's own)
        if not isinstance(self, LocalClient) and self is not own:
            frames.append(json.dumps(message))
        dispatch(self, message)

    monkeypatch.setattr(CDP, "_dispatch", spy)
    engines = []
    try:
        for agent, page in (("a1", "form.html"), ("a2", "privacy.html")):
            add_agent(server.agents, agent)
            engine = agent_engine(server, throwaway_chrome, tmp_path, monkeypatch, agent)
            engines.append(engine)
            ok(await engine.open(base + page))  # now, while the environment names this agent
        one, two = ok(await engines[0].tabs("list")), ok(await engines[1].tabs("list"))
        assert "form.html" in one and "privacy.html" not in one and "privacy.html" in two and "form.html" not in two
        assert brave.relay.upstream_opens == 1
        logs = b"".join(path.read_bytes() for engine in engines for path in (engine.home / "tasks").rglob("*")
                        if path.is_file())
        assert "SECRET-7f3a" not in "".join(frames) + one + two and b"SECRET-7f3a" not in logs
    finally:
        for engine in engines:
            await engine.close()


@CHROME
async def test_take_back_through_the_relay(relayed, throwaway_chrome, tmp_path, monkeypatch):
    import ai_browser.agentlink as agentlink

    monkeypatch.setattr(agentlink, "HANDED_TTL", 60)  # only the relay's cut can tell the engine
    server, brave, base, own = relayed
    user = (await own.send("Target.createTarget", {"url": base + "form.html"}))["targetId"]
    assert await until(lambda: any(tab["target"] == user for tab in brave.tabs()))
    add_agent(server.agents, "a1", adopted=[user])
    engine = agent_engine(server, throwaway_chrome, tmp_path, monkeypatch, "a1")
    try:
        assert "h1" in ok(await engine.tabs("list"))
        ok(await engine.tabs("switch", "h1"))
        ok(await engine.observe())
        await server._brave_command(asyncio.Queue(), "take_back", {"target": user})  # AI Home's Take back
        assert await until(lambda: engine.browser.current.detached)  # the browser's detach note reached the engine
        assert ok(await engine.observe()).startswith("(the user took back tab t")
        assert user in await pages(own)  # let go of, never closed
    finally:
        await engine.close()


@CHROME
async def test_a_new_engine_or_a_dropped_socket_keeps_one_upstream(relayed, throwaway_chrome, tmp_path,
                                                                    monkeypatch):
    server, brave, base, own = relayed
    add_agent(server.agents, "a1")
    engine = agent_engine(server, throwaway_chrome, tmp_path, monkeypatch, "a1")
    ok(await engine.open(base + "form.html"))
    first = engine.browser.current.target
    await engine.close()  # New chat: this engine ends; its tab stays the agent's
    engine = agent_engine(server, throwaway_chrome, tmp_path, monkeypatch, "a1")
    try:
        ok(await engine.open(base + "privacy.html"))
        assert brave.relay.upstream_opens == 1 and first in brave.relay.own_targets("a1")
        stale = engine.browser.current.target
        socket = next(client for client in brave.relay._clients if client.identity == "a1")
        brave.relay._too_slow(socket)  # the relay drops a1's socket, as for 4408
        assert await until(lambda: engine.cdp.closed)
        assert ok(await engine.tabs("list")).startswith("(reconnected to your Chrome")
        for _ in range(50):
            if stale not in await pages(own):
                break
            await asyncio.sleep(0.1)
        assert stale not in await pages(own)  # closed through the relay
        assert brave.relay.upstream_opens == 1
    finally:
        await engine.close()
    await server.agents.close("a1")  # closing a1 closes its earlier tab: the relay says it is its own
    for _ in range(50):
        if first not in await pages(own):
            break
        await asyncio.sleep(0.1)
    assert first not in await pages(own)


@CHROME
async def test_live_view_and_thumbnails_through_the_relay(relayed, throwaway_chrome, tmp_path, monkeypatch,
                                                         patient_thumbnails):
    server, brave, base, own = relayed
    add_agent(server.agents, "a1")
    engine = agent_engine(server, throwaway_chrome, tmp_path, monkeypatch, "a1")
    try:
        ok(await engine.open(base + "form.html"))
        target = engine.browser.current.target
        assert engine.live is not None and engine.live.url

        async with connect(engine.live.url.replace("http://", "ws://").replace("/live?", "/live/ws?")) as ws:
            async def frame():
                while True:
                    message = json.loads(await asyncio.wait_for(ws.recv(), 20))
                    if message["t"] == "frame":
                        return message

            await asyncio.sleep(0.3)  # the viewer started the screencast; a still page may send no frame until it changes
            ok(await engine.js("document.body.style.background = 'rgb(4, 5, 6)'"))
            first = await frame()  # the live view streams through the relay
            picture = await brave.thumbnail(target)  # meanwhile the app pictures the same tab on its own session
            ok(await engine.js("document.body.style.background = 'rgb(1, 2, 3)'"))  # a change makes a new frame
            second = await frame()  # still streaming after the thumbnail's session came and went
        for shot in (first, second):
            assert base64.b64decode(shot["data"])[:2] == b"\xff\xd8"
        assert picture[:2] == b"\xff\xd8"
    finally:
        await engine.close()


@CHROME
async def test_a_tabs_frames_reach_its_own_agent_only(relayed, throwaway_chrome, tmp_path, monkeypatch):
    """The frames spec, 3: through the relay an agent reads the frames of its own tab. Another agent gets none of them,
    the user's own tab with the same frames gives nobody anything, and only frames are attached (the builder runs a
    worker too)."""
    from urllib.parse import urlsplit

    from ai_browser.cdp import CDPError

    server, brave, base, own = relayed
    users = (await own.send("Target.createTarget", {"url": base + "frames/builder.html"}))["targetId"]
    got, dispatch = {}, CDP._dispatch

    def spy(self, message):  # every message each connection gets
        got.setdefault(id(self), []).append(json.dumps(message))
        dispatch(self, message)

    monkeypatch.setattr(CDP, "_dispatch", spy)
    engines = []
    try:
        for agent, page in (("a2", "form.html"), ("a1", "frames/builder.html")):  # a2 listens before a1's frames come
            add_agent(server.agents, agent)
            engine = agent_engine(server, throwaway_chrome, tmp_path, monkeypatch, agent)
            engines.append(engine)
            ok(await engine.open(base + page))
        two, one = engines
        for _ in range(100):
            if '"Add row"' in ok(await one.observe()):
                break
            await asyncio.sleep(0.1)
        assert "frames: [page-builder] [side] [nested]" in ok(await one.observe())  # side: no address, so blank
        frames = [frame for frame in one.browser.current.frames.values() if frame.session != frame.host]
        assert {urlsplit(frame.url).path for frame in frames} == {"/frames/canvas.html", "/frames/nested.html"}
        attached = [json.loads(message)["params"]["targetInfo"]["type"] for message in got[id(one.cdp)]
                    if json.loads(message).get("method") == "Target.attachedToTarget"]
        assert set(attached) == {"page", "iframe"}  # its tab, and its tab's frames: never the worker
        children = [session for session in brave.relay._sessions.values() if session.parent]
        assert children and all(session.page == one.browser.current.target and session.client.identity == "a1"
                                for session in children)  # none of the user's own builder tab
        assert users not in {session.page for session in brave.relay._sessions.values()}
        theirs = "".join(got.get(id(two.cdp), []))  # all a2 heard
        assert "canvas.html" not in theirs and not any(frame.session in theirs for frame in frames)
        for frame in frames:
            with pytest.raises(CDPError, match="Session with given id not found"):
                await two.cdp.send("Runtime.evaluate", {"expression": "1"}, session_id=frame.session)
    finally:
        for engine in engines:
            await engine.close()


async def test_shots_at_once_leave_the_tab_its_size(relayed):
    """Two scaled shots of one tab at once (an agent's and Mission Control's thumbnail) shrank it for good in a real
    Chrome: 320×213 in GHL's builder. Through the relay they take turns, and the tab keeps its size."""
    _server, brave, base, own = relayed
    target = (await own.send("Target.createTarget", {"url": base + "form.html"}))["targetId"]
    mine = (await own.send("Target.attachToTarget", {"targetId": target, "flatten": True}))["sessionId"]

    async def size():
        answer = await own.send("Runtime.evaluate", {"expression": "[innerWidth, innerHeight]", "returnByValue": True},
                                session_id=mine)
        return answer["result"]["value"]

    before = await size()
    clients = [brave.relay.local(), brave.relay.local()]
    sessions = [(await c.send("Target.attachToTarget", {"targetId": target, "flatten": True}))["sessionId"]
                for c in clients]
    clip = {"x": 0, "y": 0, "width": before[0], "height": before[1]}
    for _ in range(4):
        await asyncio.gather(*(c.send("Page.captureScreenshot", {"format": "jpeg", "clip": {**clip, "scale": scale}},
                                      session_id=s)
                               for c, s, scale in zip(clients, sessions, (0.83, 320 / before[0]))))
    assert await size() == before
