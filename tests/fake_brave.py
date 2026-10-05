"""Test stand-ins: the user's Brave as the app sees it (app/bravelink.BraveLink), Brave's debugging port itself
(FakePort, which counts handshakes the way Brave counts its "Allow remote debugging?" questions), the relay served on
a uvicorn of its own, and an agent with no Claude Code process behind it."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
from pathlib import Path

from websockets.asyncio.server import serve

async def until(check, seconds=5):
    for _ in range(int(seconds * 20)):
        if check():
            return True
        await asyncio.sleep(0.05)
    return check()


class FakePort:
    """Brave's debugging port, faked: a DevToolsActivePort file, and a WebSocket answering the CDP methods the relay
    and the engines use, the way Chrome does in flatten mode. answer: "accept"; "refuse" (a 403 instead of the
    WebSocket, as when the user clicks Deny); "silent" (no answer until `release` is set, then as `answer` says then).
    `sessions` counts handshakes: each is a moment the real Brave would ask "Allow remote debugging?". `received`
    records every command as (method, sessionId, params, id); `hold` names methods it never answers. `workers` are
    service workers ({"target", "url", "context"}); `default` is the context Target.getBrowserContexts names as the
    default (the profile used last), and None makes that read fail."""

    def __init__(self, folder, answer="accept", pages=(), workers=(), default="C1"):
        self.folder, self.answer = Path(folder), answer
        self.pages = [dict(page) for page in pages]  # {"target", "url", "title", optional "type", "opener", "context"}
        self.workers = [dict(worker) for worker in workers]  # {"target", "url", "context"}: service workers
        self.default = default  # Target.getBrowserContexts' defaultBrowserContextId; None makes it fail
        self.sessions, self.methods, self.attached, self.received = 0, [], [], []
        self.hold: set[str] = set()
        self.held: list[dict] = []  # commands in `hold`, unanswered until answer_held()
        self.server, self.release, self.socket = None, asyncio.Event(), None
        self.bound: dict[str, str] = {}  # session id -> target id
        self._targets = self._sessions = 0

    async def start(self):
        self.server = await serve(self._handler, "127.0.0.1", 0, process_request=self._process, max_size=None,
                                  open_timeout=None)  # like Brave: a handshake waits for its answer
        port = self.server.sockets[0].getsockname()[1]
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "DevToolsActivePort").write_text(f"{port}\n/devtools/browser/fake\n", encoding="utf-8")

    async def _process(self, connection, request):
        self.sessions += 1  # a debugging session asked for: the moment the real Brave would ask "Allow?"
        if self.answer == "silent":
            await asyncio.wait_for(self.release.wait(), 30)
        if self.answer == "vanish":  # Brave quits while it asks: the handshake ends with no answer at all
            connection.transport.abort()
            return connection.respond(500, "")  # never reaches the client
        if self.answer == "refuse":
            return connection.respond(403, "Denied\n")
        return None

    def page(self, target):
        return next((page for page in self.pages if page["target"] == target), None)

    @staticmethod
    def info(page):
        info = {"targetId": page["target"], "type": page.get("type", "page"), "url": page["url"],
                "title": page.get("title", ""), "attached": False, "canAccessOpener": False,
                "browserContextId": page.get("context", "C1")}
        if page.get("opener"):
            info["openerId"] = page["opener"]
        return info

    def infos(self):
        return [self.info(page) for page in self.pages] + [self._worker_info(worker) for worker in self.workers]

    async def emit(self, method, params, session=None):
        """An event from "Brave"."""
        message = {"method": method, "params": params}
        if session:
            message["sessionId"] = session
        await self.socket.send(json.dumps(message))

    async def popup(self, opener, url="https://popup.example/"):
        """A page `opener` opened (window.open), announced as Chrome announces it; returns its target id."""
        self._targets += 1
        page = {"target": f"P{self._targets}", "url": url, "title": "", "opener": opener}
        self.pages.append(page)
        await self.emit("Target.targetCreated", {"targetInfo": self.info(page)})
        return page["target"]

    async def flood(self, session, megabytes):
        chunk = "x" * (1024 * 1024)
        for _ in range(megabytes):
            await self.emit("Page.screencastFrame", {"data": chunk, "sessionId": 1, "metadata": {}}, session)

    async def drop(self):
        """Brave quits: the connection goes (the port file stays, like a crashed browser's)."""
        if self.socket is not None:
            await self.socket.close()

    async def _handler(self, ws):
        self.socket = ws
        async for raw in ws:
            message = json.loads(raw)
            method, params, session = message["method"], message.get("params") or {}, message.get("sessionId")
            self.methods.append(method)
            self.received.append((method, session, params, message["id"]))
            if method in self.hold:
                self.held.append(message)
                continue
            await self._reply(ws, message)

    async def answer_held(self):
        """Answer the commands `hold` kept waiting, as the browser would have."""
        held, self.held = self.held, []
        for message in held:
            await self._reply(self.socket, message)

    async def _reply(self, ws, message):
        method, params, session = message["method"], message.get("params") or {}, message.get("sessionId")
        result, error, before, after = {}, None, [], []
        target, missing = params.get("targetId"), {"code": -32602, "message": "No target with given id found"}
        if method == "Target.getTargets":
            result = {"targetInfos": self.infos()}
        elif method == "Target.getBrowserContexts":
            if self.default is None:  # a failed read
                error = {"code": -32000, "message": "Not available"}
            else:
                result = {"browserContextIds": ["C2"], "defaultBrowserContextId": self.default}
        elif method == "Target.getTargetInfo":
            page = self.page(target)
            error, result = (missing, {}) if page is None else (None, {"targetInfo": self.info(page)})
        elif method == "Target.createTarget":
            self._targets += 1
            page = {"target": f"T{self._targets}", "url": params.get("url", ""), "title": "",
                    "context": self.default or "C1"}  # as Chromium: in the profile used last
            self.pages.append(page)
            before.append(("Target.targetCreated", {"targetInfo": self.info(page)}, None))  # as Chrome may
            result = {"targetId": page["target"]}
        elif method == "Target.attachToTarget":
            page = self.page(target)
            if page is None:
                error = missing
            else:
                self.attached.append(target)
                self._sessions += 1
                sid = f"S{self._sessions}"
                self.bound[sid] = target
                before.append(("Target.attachedToTarget", {"sessionId": sid, "waitingForDebugger": False,
                                                           "targetInfo": {**self.info(page), "attached": True}},
                               None))
                before.append(("Page.lifecycleEvent", {"name": "init", "frameId": target}, sid))
                result = {"sessionId": sid}
        elif method == "Target.detachFromTarget":
            sid = params.get("sessionId")
            after.append(("Target.detachedFromTarget", {"sessionId": sid, "targetId": self.bound.pop(sid, "")},
                          None))
        elif method == "Target.closeTarget":
            page = self.page(target)
            if page is None:
                error = missing
            else:
                self.pages.remove(page)
                for sid in [sid for sid, bound in self.bound.items() if bound == target]:
                    del self.bound[sid]
                    after.append(("Target.detachedFromTarget", {"sessionId": sid, "targetId": target}, None))
                after.append(("Target.targetDestroyed", {"targetId": target}, None))
                result = {"success": True}
        elif method == "Page.getLayoutMetrics":
            result = {"cssVisualViewport": {"clientWidth": 800, "clientHeight": 600, "pageX": 0, "pageY": 0}}
        elif method == "Page.captureScreenshot":
            result = {"data": base64.b64encode(b"\xff\xd8jpeg").decode()}
        elif method == "Page.getFrameTree":
            result = {"frameTree": {"frame": {"id": f"F-{self.bound.get(session, '')}", "url": "about:blank"}}}
        elif method == "Runtime.evaluate":
            result = {"result": {"value": "page text"}}
        elif method == "Page.createIsolatedWorld":
            result = {"executionContextId": 7}
        elif method == "Browser.getVersion":
            result = {"product": "FakeBrave/1"}
        for name, event_params, event_session in before:
            await self.emit(name, event_params, event_session)
        reply = {"id": message["id"], **({"error": error} if error else {"result": result})}
        if session:
            reply["sessionId"] = session
        await ws.send(json.dumps(reply))
        for name, event_params, event_session in after:
            await self.emit(name, event_params, event_session)
        if method == "Target.setDiscoverTargets" and params.get("discover"):
            for info in self.infos():
                await self.emit("Target.targetCreated", {"targetInfo": info})

    # ---- watcher-safety: profiles, private windows and the watcher's worker --------------------------------------

    def set_default(self, context):
        """The context Brave would name as its default (the profile used last); None makes the read fail."""
        self.default = context

    @staticmethod
    def _worker_info(worker):
        return {"targetId": worker["target"], "type": "service_worker", "url": worker["url"], "title": "",
                "attached": False, "canAccessOpener": False, "browserContextId": worker["context"]}

    async def _tell_all(self, method, params):
        if self.socket is not None:
            with contextlib.suppress(Exception):  # no connection now: nobody to tell
                await self.emit(method, params)

    async def destroy(self, target):
        """A page closes, or a service worker goes to sleep: Target.targetDestroyed."""
        self.pages = [page for page in self.pages if page["target"] != target]
        self.workers = [worker for worker in self.workers if worker["target"] != target]
        await self._tell_all("Target.targetDestroyed", {"targetId": target})

    async def add_worker(self, worker):
        """A service worker starts (the watcher's worker wakes up): Target.targetCreated."""
        self.workers.append(dict(worker))
        await self._tell_all("Target.targetCreated", {"targetInfo": self._worker_info(worker)})

    async def stop(self):
        self.release.set()
        self.server.close()
        await self.server.wait_closed()


async def serve_relay(relay):
    """The relay's /cdp on a uvicorn of its own, served as AppServer serves it (the sans-I/O websockets it pins):
    (its ws:// address, stop)."""
    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import WebSocketRoute

    from ai_browser.live import _bind, _QuietServer, _serve

    sock = _bind("127.0.0.1", 0)
    server = _QuietServer(uvicorn.Config(Starlette(routes=[WebSocketRoute("/cdp", relay.serve)]), log_level="warning",
                                         lifespan="off", ws="websockets-sansio"))
    task = asyncio.create_task(_serve(server, sock))
    assert await until(lambda: server.started, 5), "the relay's server did not start"
    relay.port = sock.getsockname()[1]

    async def stop():
        server.should_exit = True
        with contextlib.suppress(Exception):
            await asyncio.wait_for(task, 5)

    return f"ws://127.0.0.1:{relay.port}/cdp", stop


async def relay_client(url, token, open_timeout=10):
    """An engine's connection to the relay: plain CDP, its token in the header."""
    from ai_browser.cdp import CDP

    return await CDP.connect(url, open_timeout=open_timeout, headers={"X-AIB-Agent-Token": token})


async def raw_handshake(port, host, token) -> int:
    """The HTTP status a /cdp handshake with this Host header gets (a raw socket: any Host at all)."""
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write((f"GET /cdp HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                  "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n"
                  f"X-AIB-Agent-Token: {token}\r\n\r\n").encode())
    await writer.drain()
    try:
        return int((await asyncio.wait_for(reader.readline(), 5)).split()[1])
    finally:
        writer.close()


class FakeRelay:
    """The relay's surface for FakeBrave: a test declares grants with own(); cuts, forgets, disconnects and closes are
    recorded; clients() answers `rows`."""

    def __init__(self):
        self.port = 0
        self.handed = lambda identity: set()
        self.may_open = lambda identity: False
        self.granted: dict[str, str] = {}  # target -> identity
        self.cuts, self.forgot, self.disconnected, self.closed_clients = [], [], [], []
        self.cut_off: set[str] = set()
        self.rows: list[dict] = []
        self._grant_hooks, self._changes = [], []

    def on_grant(self, callback):
        self._grant_hooks.append(callback)

    def on_change(self, callback):
        self._changes.append(callback)

    def own(self, identity, target, announce=True):
        """A tab `identity` opened through the relay (announce: the owner chip comes at once, as the relay's does)."""
        self.granted[target] = identity
        if announce:
            for callback in list(self._grant_hooks):
                callback(identity, target)

    def grants(self, identity, target):
        return self.granted.get(target) == identity

    def own_targets(self, identity):
        return [target for target, owner in self.granted.items() if owner == identity]

    def is_cut_off(self, identity):
        return identity in self.cut_off

    def clients(self):
        return [dict(row) for row in self.rows]

    async def cut(self, identity, target):
        self.cuts.append((identity, target))

    async def forget(self, identity, close_tabs=False):
        self.forgot.append((identity, close_tabs))

    async def disconnect(self, identity):
        self.disconnected.append(identity)
        self.cut_off.add(identity)
        for callback in list(self._changes):
            callback()

    async def close_clients(self, code=1001):
        self.closed_clients.append(code)


class FakePlace:
    """ProfilePlace's surface: the profiles a test lists ({"folder", "name", "color"})."""

    def __init__(self):
        self.listed: list[dict] = []
        self.chosen = None

    def profiles(self):
        return [dict(profile) for profile in self.listed]


class FakeBrave:
    """BraveLink's surface, holding the tabs a test gives it; owners, Watch, closes and connects are recorded."""

    name = "Brave"

    def __init__(self, pages=(), state="connected"):
        self.state = state
        self.pages = [dict(page) for page in pages]  # {"target", "url", "title"}
        self.owners: dict[str, dict] = {}
        self.watched, self.closed, self.ended = [], [], []  # Watch, closes, picks ended
        self.connects = 0
        self.connect_calls = []  # (why, identity) of each connect
        self.relay = FakeRelay()
        self.place = FakePlace()  # Settings → Where agents browse
        self._changes, self._states = [], []

    def on_change(self, callback):
        self._changes.append(callback)

    def on_state(self, callback):
        self._states.append(callback)

    def set_state(self, state):
        self.state = state
        for callback in list(self._states):
            callback(state)

    def tabs(self):
        return [{**page, "owner": dict(self.owners.get(page["target"], {"kind": "you"}))} for page in self.pages]

    tab_scope = {"profile": "chosen", "elsewhere": 0}  # what BraveLink.scope() answers (watcher-safety)

    def scope(self):
        return dict(self.tab_scope)

    def set_scope(self, profile, elsewhere):
        self.tab_scope = {"profile": profile, "elsewhere": elsewhere}
        self.changed()

    def changed(self):
        for callback in list(self._changes):
            callback(self.tabs())

    def set_owner(self, target, owner):
        self.owners[target] = dict(owner)
        self.changed()

    def forget(self, target):
        self.owners.pop(target, None)
        self.changed()

    def release(self, owner_id):
        for target in [target for target, owner in self.owners.items() if owner.get("id") == owner_id]:
            del self.owners[target]
        self.changed()

    async def connect(self, why="connect", identity=""):
        self.connects += 1
        self.connect_calls.append((why, identity))

    async def watch(self, target):
        self.watched.append(target)

    def set_place(self, folder):
        self.place.chosen = folder

    def brain_tabs(self):  # the Brain's reading: nothing here (tests/fake_reading.py fakes it whole)
        return []

    async def end_pick(self, target):
        self.ended.append(target)

    async def close_targets(self, targets):
        self.closed += list(targets)

    async def thumbnail(self, target):
        return None

    async def page_text(self, target, picked=False):
        return ""


class NoBridge:
    """An agent's bridge with no Claude Code process: each message ends its turn at once."""

    loaded_skills: set = set()
    model = "sonnet"

    async def send(self, text, tab_url="", tab_title="", skills=(), tab_label="panel"):
        yield {"type": "done", "seconds": 0, "cost": 0}

    async def stop(self):
        pass

    async def close(self):
        pass


def add_agent(manager, agent_id="a1", name="Fix the footer", color="blue", adopted=()):
    """An agent in the manager's list, as if started and done with its turn, with no process behind it."""
    from ai_browser.app.agents import Agent

    agent = Agent(agent_id, name, color, "sonnet", NoBridge(), state="your_turn")
    agent.adopted += list(adopted)
    manager.agents[agent_id] = agent
    return agent


class BraveApp:
    """A real app server in brave mode with its BraveLink (and relay) on a FakePort: what an agent's engine or a
    Claude Code session meets while `ai-browser app` runs."""

    def __init__(self, home, folder, pages=(), answer="accept"):
        self.home, self.folder, self.pages, self.answer = Path(home), Path(folder), list(pages), answer

    async def start(self, connect=True):
        from ai_browser.app.agents import AgentManager
        from ai_browser.app.bravelink import BraveLink
        from ai_browser.app.server import AppServer

        self.port = FakePort(self.folder, answer=self.answer, pages=self.pages)
        await self.port.start()
        self.agents = AgentManager(self.home)
        self.server = AppServer(self.home, self.agents)
        self.url = await self.server.start()
        self.brave = BraveLink(self.folder, allow_wait=2, every=0.1, tokens=self.server.tokens)
        self.server.attach_brave(self.brave)
        self.agents.close_tabs = self.brave.close_targets
        await self.brave.start()
        if connect:
            await self.brave.connect()
        self.cdp = self.url.replace("http://", "ws://", 1) + "/cdp"
        return self

    def write_link(self):
        from ai_browser.app.run import write_link

        return write_link(self.home, self.url, self.server.session_token, self.cdp, self.folder)

    def agent_env(self, monkeypatch, agent="a1"):
        """An app agent's engine environment, as ai-browser app sets it."""
        monkeypatch.setenv("AIB_BROWSER", "chrome")
        monkeypatch.setenv("AIB_CHROME_DIR", str(self.folder))
        monkeypatch.setenv("AIB_APP_AGENT", agent)
        monkeypatch.setenv("AIB_APP_EVENTS", self.url + "/agent-events")
        monkeypatch.setenv("AIB_APP_AGENT_TOKEN", self.server.token_for(agent))
        monkeypatch.setenv("AIB_APP_CDP", self.cdp)

    async def stop(self):
        await self.server.stop()
        await self.brave.close()
        await self.port.stop()
