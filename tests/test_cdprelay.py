"""The app's one connection to the user's browser, shared by everyone (app/cdprelay.py): its policy and tokens, the CDP
client's header, and the relay in front of a fake debugging port that counts handshakes the way Brave counts its
"Allow remote debugging?" questions."""

import ast
import asyncio
import contextlib
import json
import logging
import time
from pathlib import Path

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import InvalidStatus

from ai_browser.app import cdprelay
from ai_browser.app.cdprelay import Tokens, address_problem, allowed
from ai_browser.cdp import CDP, CDPError
from fake_brave import FakePort, raw_handshake, relay_client, serve_relay, until

SRC = Path(cdprelay.__file__).resolve().parents[1]  # src/ai_browser
APP_PORT = 8795


def test_the_browser_level_list_is_short():
    for method in ("Target.setDiscoverTargets", "Target.createTarget", "Target.attachToTarget",
                   "Target.detachFromTarget", "Target.closeTarget", "Target.activateTarget", "Target.getTargets",
                   "Target.getTargetInfo", "Browser.getVersion", "Browser.cancelDownload",
                   "Browser.getWindowForTarget"):
        assert allowed(method, "browser"), method
    for method in ("Browser.close", "Browser.crash", "Browser.setDownloadBehavior", "Browser.grantPermissions",
                   "Browser.setPermission", "Browser.resetPermissions", "Storage.getCookies", "Target.setAutoAttach",
                   "Target.autoAttachRelated", "Target.attachToBrowserTarget", "Target.sendMessageToTarget",
                   "Target.exposeDevToolsProtocol", "Target.createBrowserContext", "Target.disposeBrowserContext",
                   "Target.getBrowserContexts", "SystemInfo.getInfo", "Tethering.bind", "Extensions.loadUnpacked",
                   "PWA.install", "Runtime.evaluate", "", "Target", 7, None):
        assert not allowed(method, "browser"), method
    assert allowed("Target.getBrowserContexts", "browser", app=True)  # the app's own client: one extra read
    assert not allowed("Browser.close", "browser", app=True)


def test_the_session_level_list_keeps_to_the_page():
    for method in ("Runtime.evaluate", "DOM.setFileInputFiles", "Input.dispatchMouseEvent", "IO.read", "Log.enable",
                   "Page.navigate", "Page.captureScreenshot", "Page.screencastFrameAck", "Network.enable",
                   "Network.loadNetworkResource", "Emulation.setFocusEmulationEnabled",
                   "Emulation.setDeviceMetricsOverride", "Emulation.clearDeviceMetricsOverride"):
        assert allowed(method, "session"), method
    for method in ("Network.getAllCookies", "Network.getCookies", "Network.setCookie", "Network.setCookies",
                   "Network.deleteCookies", "Network.clearBrowserCookies", "Network.clearBrowserCache",
                   "Network.setExtraHTTPHeaders", "Network.setUserAgentOverride", "Emulation.setUserAgentOverride",
                   "Emulation.setAutomationOverride", "Emulation.setLocaleOverride", "Emulation.setTimezoneOverride",
                   "Page.setDownloadBehavior", "Fetch.enable", "Autofill.trigger", "WebAuthn.enable",
                   "FedCm.enable", "Target.createTarget", "Browser.close", "Storage.clearDataForOrigin", "Runtime"):
        assert not allowed(method, "session"), method


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "chrome://settings", "brave://settings", "javascript:alert(1)",
    "view-source:https://a.example", "chrome-extension://abc/home.html", "blob:https://a.example/x",
    "ws://127.0.0.1:1/", "", None, "http://", "about:settings",
    f"http://127.0.0.1:{APP_PORT}/setup", f"http://localhost:{APP_PORT}/", f"http://LOCALHOST.:{APP_PORT}/",
    f"http://app.localhost:{APP_PORT}/", f"http://2130706433:{APP_PORT}/", f"http://0x7f.1:{APP_PORT}/",
    f"http://0177.0.0.1:{APP_PORT}/", f"http://127.1:{APP_PORT}/", f"http://0.0.0.0:{APP_PORT}/",
    f"http://[::1]:{APP_PORT}/", f"http://[::ffff:127.0.0.1]:{APP_PORT}/", f"https://127.0.0.1:{APP_PORT}/",
    f"http://user@127.0.0.1:{APP_PORT}/", f"http://%31%32%37.0.0.1:{APP_PORT}/",
    f"http://１２７.0.0.1:{APP_PORT}/", f"http://127.0.0.1:{APP_PORT}\\@example.com/",
    f"http://127.0.0.1:0{APP_PORT}/", f"http://1.2.3.09:{APP_PORT}/", f" http://127.0.0.1:{APP_PORT}/",
])
def test_the_address_check_refuses_local_files_browser_pages_and_the_apps_own_origin(url):
    assert address_problem(url, APP_PORT) is not None, url


@pytest.mark.parametrize("url", [
    "about:blank", "about:blank#aib-0123456789abcdef", "https://example.com", f"http://example.com:{APP_PORT}/",
    "data:text/html,hi", f"http://localhost:{APP_PORT + 1}/", "http://127.0.0.1:80/", "http://127.0.0.2.example/",
])
def test_the_address_check_lets_web_pages_through(url):
    assert address_problem(url, APP_PORT) is None, url


def test_tokens_are_per_identity_and_a_revoked_one_is_remembered_as_gone():
    tokens = Tokens()
    a1, a2 = tokens.mint("a1"), tokens.mint("a2")
    assert a1 != a2 and tokens.mint("a1") == a1 and len(a1) >= 32
    assert tokens.check("a1", a1) and not tokens.check("a1", a2) and not tokens.check("a3", a1)
    assert not tokens.check("a1", None) and not tokens.check("a1", "")
    assert tokens.who(a2) == "a2" and tokens.who("nope") is None and tokens.who("") is None
    tokens.revoke("a1")
    assert tokens.who(a1) is None and not tokens.check("a1", a1) and tokens.gone(a1) == "a1"
    assert tokens.gone(a2) is None


def _sent_methods(path: Path) -> set[str]:
    """Every "Domain.method" a file passes as the first argument of send(, _call( or _send(."""
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant) \
                and isinstance(node.args[0].value, str):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if name in ("send", "_call", "_send") and "." in node.args[0].value:
                found.add(node.args[0].value)
    return found


def _level(method: str) -> str:
    return "browser" if method.startswith(("Target.", "Browser.")) else "session"


def test_every_method_the_engine_sends_passes_the_policy():
    """The drift guard (spec test 18): a new CDP call in the engine fails here until the relay's lists allow it."""
    files = [SRC / name for name in ("browser.py", "live.py", "engine.py", "checks.py", "grouping.py")]
    files += sorted((SRC / "qa").glob("*.py"))
    sandbox_only = {"Browser.setDownloadBehavior"}  # browser.py sends it in the Docker sandbox only, never here
    seen = set()
    for path in files:
        for method in _sent_methods(path):
            seen.add(method)
            if method not in sandbox_only:
                assert allowed(method, _level(method)), f"{path.name} sends {method}, which the relay refuses"
    for method in _sent_methods(SRC / "app" / "tabs.py"):
        assert allowed(method, _level(method), app=True), f"tabs.py sends {method}, which the relay refuses"
    assert {"Target.createTarget", "Page.navigate", "Network.loadNetworkResource", "Input.dispatchMouseEvent",
            "Page.screencastFrameAck", "IO.read", "Browser.cancelDownload"} <= seen  # the scan found the engine


async def test_cdp_connect_sends_the_header_and_no_origin_and_uses_no_proxy(monkeypatch):
    """Spec test 32: a token in a header must never pass through a proxy the environment names."""
    headers = {}

    def record(connection, request):
        headers.update({key.lower(): value for key, value in request.headers.raw_items()})

    async def answer(ws):
        async for raw in ws:
            await ws.send(json.dumps({"id": json.loads(raw)["id"], "result": {}}))

    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")  # nothing listens there
    async with serve(answer, "127.0.0.1", 0, process_request=record) as server:
        port = server.sockets[0].getsockname()[1]
        cdp = await CDP.connect(f"ws://127.0.0.1:{port}/cdp", open_timeout=5, headers={"X-AIB-Agent-Token": "t0k"})
        try:
            assert await cdp.send("Browser.getVersion") == {}
        finally:
            await cdp.close()
    assert headers["x-aib-agent-token"] == "t0k" and "origin" not in headers


from ai_browser.app.cdprelay import Relay  # noqa: E402

USER_TAB = {"target": "U1", "url": "https://mail.example/", "title": "SECRET-7f3a"}


class Rig:
    def __init__(self, port, tokens, relay, url):
        self.port, self.tokens, self.relay, self.url = port, tokens, relay, url
        self.working, self.handed, self.clients = set(), {}, []

    async def client(self, identity):
        cdp = await relay_client(self.url, self.tokens.mint(identity))
        self.clients.append(cdp)
        return cdp

    def sent(self, method):
        return [params for name, _, params, _ in self.port.received if name == method]


@pytest.fixture
async def rig(tmp_path):
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, pages=[USER_TAB])
    await port.start()
    tokens = Tokens()
    relay = Relay(folder, tokens, allow_wait=2, every=0.1)
    url, stop = await serve_relay(relay)
    rig = Rig(port, tokens, relay, url)
    relay.may_open = lambda identity: identity.startswith("cc-") or identity in rig.working
    relay.handed = lambda identity: set(rig.handed.get(identity, ()))
    await relay.start()
    yield rig
    for cdp in rig.clients:
        with contextlib.suppress(Exception):
            await cdp.close()
    await relay.close()
    await stop()
    await port.stop()


class Raw:
    """A client on /cdp that keeps every frame it gets, to look for what must never reach it."""

    def __init__(self, ws):
        self.ws, self.frames, self._id = ws, [], 0

    @classmethod
    async def open(cls, url, token, **options):
        return cls(await connect(url, additional_headers={"X-AIB-Agent-Token": token}, proxy=None, max_size=None,
                                 **options))

    async def call(self, method, params=None, session=None):
        self._id += 1
        message = {"id": self._id, "method": method, "params": params or {}}
        if session:
            message["sessionId"] = session
        await self.ws.send(json.dumps(message))
        while True:
            raw = await asyncio.wait_for(self.ws.recv(), 5)
            self.frames.append(raw)
            reply = json.loads(raw)
            if reply.get("id") == self._id:
                return reply

    async def drain(self, seconds=0.3):
        with contextlib.suppress(TimeoutError):
            while True:
                self.frames.append(await asyncio.wait_for(self.ws.recv(), seconds))


async def own_tab(cdp, url="about:blank"):
    """(target, session): a tab the client opened, attached in flatten mode."""
    target = (await cdp.send("Target.createTarget", {"url": url}))["targetId"]
    return target, (await cdp.send("Target.attachToTarget", {"targetId": target, "flatten": True}))["sessionId"]


async def test_one_upstream_for_the_app_two_agents_and_a_session(rig):
    assert rig.relay.state == "ready" and rig.port.sessions == 0  # TCP looks only: nothing asked yet
    assert await rig.relay.open("start")
    local = rig.relay.local()
    a1, a2, session = await rig.client("a1"), await rig.client("a2"), await rig.client("cc-x")
    for cdp in (local, a1, a2, session):
        assert (await cdp.send("Browser.getVersion"))["product"] == "FakeBrave/1"
    tab = (await a1.send("Target.createTarget", {"url": "https://example.com"}))["targetId"]
    await a2.send("Target.createTarget", {"url": "about:blank"})
    await session.send("Target.createTarget", {"url": "about:blank"})
    assert rig.relay.grants("a1", tab) and not rig.relay.grants("a2", tab)
    assert rig.port.sessions == 1 and rig.relay.upstream_opens == 1


async def test_ids_are_remapped_per_client(rig):
    await rig.relay.open("start")
    a1, a2 = await rig.client("a1"), await rig.client("a2")
    one, two = await asyncio.gather(a1.send("Browser.getVersion"), a2.send("Browser.getVersion"))  # both are id 1
    assert one == two == {"product": "FakeBrave/1"}
    upstream = [message_id for name, _, _, message_id in rig.port.received if name == "Browser.getVersion"]
    assert len(upstream) == 2 and len(set(upstream)) == 2


async def test_attach_events_before_the_answer_reach_only_the_attacher(rig):
    await rig.relay.open("start")
    a1, a2 = await rig.client("a1"), await rig.client("a2")
    seen = {"a1": [], "a2": []}
    for name, cdp in (("a1", a1), ("a2", a2)):
        cdp.on("Target.attachedToTarget", lambda params, sid, name=name: seen[name].append(("attached",
                                                                                              params["sessionId"])))
        cdp.on("Page.lifecycleEvent", lambda params, sid, name=name: seen[name].append(("event", sid)))
    tab = (await a1.send("Target.createTarget", {"url": "about:blank"}))["targetId"]
    session = (await a1.send("Target.attachToTarget", {"targetId": tab, "flatten": True}))["sessionId"]
    assert seen["a1"] == [("attached", session), ("event", session)]  # both, in order, before the answer
    await asyncio.sleep(0.2)
    assert seen["a2"] == []


async def test_two_clients_on_one_tab_get_two_sessions(rig):
    await rig.relay.open("start")
    local, a1 = rig.relay.local(), await rig.client("a1")
    tab, mine = await own_tab(a1)
    apps = (await local.send("Target.attachToTarget", {"targetId": tab, "flatten": True}))["sessionId"]
    assert mine != apps
    got = {"a1": [], "app": []}
    a1.on("Page.lifecycleEvent", lambda params, sid: got["a1"].append(sid))
    local.on("Page.lifecycleEvent", lambda params, sid: got["app"].append(sid))
    await rig.port.emit("Page.lifecycleEvent", {"name": "load"}, mine)
    await rig.port.emit("Page.lifecycleEvent", {"name": "load"}, apps)
    assert await until(lambda: got == {"a1": [mine], "app": [apps]})


async def test_the_users_tabs_are_invisible_to_agents(rig):
    await rig.relay.open("start")
    a1 = await Raw.open(rig.url, rig.tokens.mint("a1"))
    try:
        await a1.call("Target.setDiscoverTargets", {"discover": True})
        mine = (await a1.call("Target.createTarget", {"url": "about:blank"}))["result"]["targetId"]
        listed = (await a1.call("Target.getTargets"))["result"]["targetInfos"]
        assert [info["targetId"] for info in listed] == [mine]
        for method in ("Target.attachToTarget", "Target.activateTarget", "Target.getTargetInfo"):
            reply = await a1.call(method, {"targetId": "U1", "flatten": True})
            assert reply["error"] == {"code": -32602, "message": "No target with given id found"}, method
        await rig.port.emit("Target.targetInfoChanged", {"targetInfo": FakePort.info({**USER_TAB,
                                                                                        "title": "SECRET-7f3a 2"})})
        await a1.drain()
        assert not any("SECRET-7f3a" in frame or "mail.example" in frame for frame in a1.frames)
        assert [name for name, _, params, _ in rig.port.received if params.get("targetId") == "U1"] == []
        local = rig.relay.local()
        assert "U1" in [info["targetId"] for info in (await local.send("Target.getTargets"))["targetInfos"]]
        assert (await local.send("Target.getBrowserContexts"))["defaultBrowserContextId"] == "C1"
        assert (await a1.call("Target.getBrowserContexts"))["error"]["code"] == -32601
    finally:
        await a1.ws.close()


async def test_a_handed_tab_is_visible_and_take_back_cuts_at_once(rig):
    await rig.relay.open("start")
    rig.handed["a1"] = {"U1"}
    a1 = await rig.client("a1")
    detached = []
    a1.on("Target.detachedFromTarget", lambda params, sid: detached.append(params["sessionId"]))
    session = (await a1.send("Target.attachToTarget", {"targetId": "U1", "flatten": True}))["sessionId"]
    assert await a1.send("Runtime.evaluate", {"expression": "1"}, session_id=session) == {"result": {"value":
                                                                                                    "page text"}}
    rig.port.hold = {"Runtime.evaluate", "Target.detachFromTarget"}  # the browser is slow to answer both
    waiting = asyncio.ensure_future(a1.send("Runtime.evaluate", {"expression": "slow"}, session_id=session))
    assert await until(lambda: len(rig.port.held) == 1)
    cutting = asyncio.ensure_future(rig.relay.cut("a1", "U1"))
    assert await until(lambda: {"sessionId": session} in rig.sent("Target.detachFromTarget"))
    rig.handed["a1"] = set()  # the server's agent.adopted no longer lists it
    with pytest.raises(CDPError, match="Session with given id not found"):
        await waiting  # what was waiting fails at once
    before = len(rig.port.received)
    with pytest.raises(CDPError, match="Session with given id not found"):
        await a1.send("Runtime.evaluate", {"expression": "2"}, session_id=session)  # refused before the detach ends
    assert len(rig.port.received) == before  # without reaching the browser
    rig.port.hold = set()
    await rig.port.answer_held()
    await cutting
    assert await until(lambda: detached == [session])
    with pytest.raises(CDPError, match="No target with given id found"):
        await a1.send("Target.attachToTarget", {"targetId": "U1", "flatten": True})


BROWSER_REFUSED = ["Browser.close", "Browser.crash", "Browser.setDownloadBehavior", "Browser.grantPermissions",
                   "Browser.setPermission", "Storage.getCookies", "Target.setAutoAttach",
                   "Target.attachToBrowserTarget", "Target.createBrowserContext", "Target.exposeDevToolsProtocol",
                   "SystemInfo.getInfo"]
SESSION_REFUSED = ["Network.getAllCookies", "Network.getCookies", "Network.setUserAgentOverride",
                   "Emulation.setUserAgentOverride", "Emulation.setAutomationOverride", "Page.setDownloadBehavior",
                   "Fetch.enable", "Autofill.trigger"]


@pytest.mark.parametrize("method", BROWSER_REFUSED + SESSION_REFUSED)
async def test_refused_commands_never_reach_the_browser(rig, method):
    await rig.relay.open("start")
    a1 = await rig.client("a1")
    session = (await own_tab(a1))[1] if method in SESSION_REFUSED else None
    with pytest.raises(CDPError) as refused:
        await a1.send(method, {}, session_id=session)
    assert refused.value.code == -32601 and f"{method} isn't allowed through AI Browser's connection" in str(
        refused.value)
    assert method not in rig.port.methods


async def test_create_target_forces_background_and_checks_the_address(rig):
    await rig.relay.open("start")
    a1, app_port = await rig.client("a1"), rig.relay.port
    for url in ("file:///etc/passwd", "chrome://settings", "brave://settings", "javascript:alert(1)",
                f"http://127.0.0.1:{app_port}/setup", f"http://localhost:{app_port}/", f"http://2130706433:{app_port}/",
                f"http://0x7f.1:{app_port}/", f"http://[::1]:{app_port}/", f"http://app.localhost:{app_port}/"):
        with pytest.raises(CDPError):
            await a1.send("Target.createTarget", {"url": url})
    for extra in ({"hidden": True}, {"focus": True}, {"browserContextId": "C-private"}):
        with pytest.raises(CDPError):
            await a1.send("Target.createTarget", {"url": "about:blank", **extra})
    assert "Target.createTarget" not in rig.port.methods
    allowed_urls = ["about:blank#aib-0123456789abcdef", "https://example.com", f"http://localhost:{app_port + 1}/"]
    for url in allowed_urls:
        await a1.send("Target.createTarget", {"url": url, "background": False})
    sent = rig.sent("Target.createTarget")
    assert [params["url"] for params in sent] == allowed_urls and all(params["background"] is True for params in sent)
    await a1.send("Target.createTarget", {"url": "about:blank", "browserContextId": "C1"})  # its own tabs' context
    _, session = await own_tab(a1)
    for method, url in (("Page.navigate", "file:///etc/passwd"),
                        ("Network.loadNetworkResource", f"http://127.0.0.1:{app_port}/setup")):
        with pytest.raises(CDPError):
            await a1.send(method, {"url": url, "frameId": "F", "options": {}}, session_id=session)
        assert method not in rig.port.methods


async def test_close_target_only_own(rig):
    await rig.relay.open("start")
    rig.handed["a1"] = {"U1"}
    a1, a2 = await rig.client("a1"), await rig.client("a2")
    mine = (await a1.send("Target.createTarget", {"url": "about:blank"}))["targetId"]
    theirs = (await a2.send("Target.createTarget", {"url": "about:blank"}))["targetId"]
    await a1.send("Target.closeTarget", {"targetId": mine})
    with pytest.raises(CDPError, match="a tab the user handed over can be let go of, never closed"):
        await a1.send("Target.closeTarget", {"targetId": "U1"})
    with pytest.raises(CDPError, match="No target with given id found"):
        await a1.send("Target.closeTarget", {"targetId": theirs})
    assert [params["targetId"] for params in rig.sent("Target.closeTarget")] == [mine]
    local = rig.relay.local()  # the app closes an agent's tab, never one nobody owns
    await local.send("Target.closeTarget", {"targetId": theirs})
    with pytest.raises(CDPError, match="No target with given id found"):
        await local.send("Target.closeTarget", {"targetId": "U1"})


async def test_cancel_download_only_for_seen_guids(rig):
    await rig.relay.open("start")
    a1, a2 = await rig.client("a1"), await rig.client("a2")
    _, session = await own_tab(a1)
    begun = []
    a1.on("Page.downloadWillBegin", lambda params, sid: begun.append(params["guid"]))
    await rig.port.emit("Page.downloadWillBegin", {"guid": "G1", "url": "https://x.example/f.zip",
                                                   "suggestedFilename": "f.zip", "frameId": "F"}, session)
    assert await until(lambda: begun == ["G1"])
    await a1.send("Browser.cancelDownload", {"guid": "G1"})
    for cdp, guid in ((a1, "G2"), (a2, "G1")):
        with pytest.raises(CDPError):
            await cdp.send("Browser.cancelDownload", {"guid": guid})
    assert [params["guid"] for params in rig.sent("Browser.cancelDownload")] == ["G1"]


async def test_popups_are_visible_and_become_own_when_attached(rig):
    await rig.relay.open("start")
    grants = []
    rig.relay.on_grant(lambda identity, target: grants.append((identity, target)))
    a1, a2 = await rig.client("a1"), await rig.client("a2")
    created = {"a1": [], "a2": []}
    for name, cdp in (("a1", a1), ("a2", a2)):
        await cdp.send("Target.setDiscoverTargets", {"discover": True})
        cdp.on("Target.targetCreated", lambda params, sid, name=name: created[name].append(
            params["targetInfo"]["targetId"]))
    tab = (await a1.send("Target.createTarget", {"url": "about:blank"}))["targetId"]
    popup = await rig.port.popup(tab)
    assert await until(lambda: popup in created["a1"])
    await asyncio.sleep(0.2)
    assert popup not in created["a2"] and not rig.relay.grants("a1", popup)
    await a1.send("Target.attachToTarget", {"targetId": popup, "flatten": True})
    assert rig.relay.grants("a1", popup) and popup in rig.relay.own_targets("a1")
    assert grants == [("a1", tab), ("a1", popup)]  # each once: the popup on its attach


async def test_discovery_is_per_client(rig):
    await rig.relay.open("start")
    a1 = await rig.client("a1")
    tab = (await a1.send("Target.createTarget", {"url": "about:blank"}))["targetId"]
    seen = []
    a1.on("Target.targetCreated", lambda params, sid: seen.append(params["targetInfo"]["targetId"]))
    assert await a1.send("Target.setDiscoverTargets", {"discover": True}) == {}
    assert seen == [tab]  # its own tab only, before the answer
    assert rig.port.methods.count("Target.setDiscoverTargets") == 1  # sent once, by the relay, at connect


async def test_a_client_that_leaves_has_its_sessions_detached(rig):
    await rig.relay.open("start")
    a1 = await rig.client("a1")
    tab, session = await own_tab(a1)
    await a1.close()
    assert await until(lambda: {"sessionId": session} in rig.sent("Target.detachFromTarget"))
    assert rig.relay.state == "connected" and rig.port.sessions == 1
    again = await rig.client("a1")  # New chat, a crash, a dropped socket: the same token, the same tabs
    session = (await again.send("Target.attachToTarget", {"targetId": tab, "flatten": True}))["sessionId"]
    assert (await again.send("Runtime.evaluate", {"expression": "1"}, session_id=session))["result"]["value"] == \
        "page text"


async def test_an_upstream_drop_fails_pending_and_closes_clients(rig):
    await rig.relay.open("start")
    raw = await Raw.open(rig.url, rig.tokens.mint("a1"))
    tab = (await raw.call("Target.createTarget", {"url": "about:blank"}))["result"]["targetId"]
    session = (await raw.call("Target.attachToTarget", {"targetId": tab, "flatten": True}))["result"]["sessionId"]
    rig.port.hold = {"Runtime.evaluate"}
    await raw.ws.send(json.dumps({"id": 99, "method": "Runtime.evaluate", "params": {"expression": "1"},
                                  "sessionId": session}))
    assert await until(lambda: "Runtime.evaluate" in rig.port.methods)
    await rig.port.drop()  # Brave quits
    replies = []

    async def read_to_the_end():
        with contextlib.suppress(Exception):
            async for frame in raw.ws:
                replies.append(json.loads(frame))

    await asyncio.wait_for(read_to_the_end(), 10)  # the relay closes it, so the reading ends
    failed = {"id": 99, "error": {"code": -32000, "message": "browser connection lost"}, "sessionId": session}
    detached = [message for message in replies if message.get("method") == "Target.detachedFromTarget"]
    assert failed in replies and detached and detached[0]["params"]["sessionId"] == session
    assert replies.index(failed) < replies.index(detached[0])
    assert raw.ws.close_code == 4410 and rig.relay.state == "lost"


async def test_a_slow_client_is_cut_not_the_upstream(rig, monkeypatch):
    monkeypatch.setattr(cdprelay, "QUEUE_BYTES", 8 * 1024 * 1024)  # 70 MB overflows the real 64 MiB too; quicker
    await rig.relay.open("start")
    a1 = await rig.client("a1")
    slow = await Raw.open(rig.url, rig.tokens.mint("a2"), max_queue=1)
    tab = (await slow.call("Target.createTarget", {"url": "about:blank"}))["result"]["targetId"]
    session = (await slow.call("Target.attachToTarget", {"targetId": tab, "flatten": True}))["result"]["sessionId"]
    flood = asyncio.ensure_future(rig.port.flood(session, 70))  # a2 reads nothing from here on
    while not flood.done():
        started = time.monotonic()
        await a1.send("Browser.getVersion")
        assert time.monotonic() - started < 1
        await asyncio.sleep(0.05)
    async def read_to_the_end():
        with contextlib.suppress(Exception):
            async for _ in slow.ws:
                pass

    await asyncio.wait_for(read_to_the_end(), 30)  # it is closed, so the reading ends
    assert slow.ws.close_code == 4408 and rig.relay.state == "connected"


async def test_one_shared_attempt_and_deny_is_not_retried(tmp_path):
    for outcome in ("accept", "refuse"):
        folder = tmp_path / outcome / "BraveSoftware" / "Brave-Browser"
        port = FakePort(folder, answer="silent")
        await port.start()
        tokens = Tokens()
        relay = Relay(folder, tokens, allow_wait=5, every=0.1)
        relay.may_open = lambda identity: True  # a1 is in its turn
        url, stop = await serve_relay(relay)
        await relay.start()
        try:
            asking = asyncio.ensure_future(relay.open("connect"))
            assert await until(lambda: relay.state == "asking")
            clients = [asyncio.ensure_future(relay_client(url, tokens.mint(who), open_timeout=20))
                       for who in ("a1", "cc-1", "cc-2")]
            await asyncio.sleep(0.5)
            assert port.sessions == 1 and not any(client.done() for client in clients)  # held, not answered yet
            port.answer = outcome
            port.release.set()
            if outcome == "accept":
                for cdp in await asyncio.gather(*clients):
                    await cdp.close()
                assert await asking and relay.state == "connected" and port.sessions == 1
                continue
            for client in clients:
                with pytest.raises(InvalidStatus) as refused:
                    await client
                assert refused.value.response.status_code == 409
                assert b"said no to AI Browser's connection: ask the user to click Try again" in bytes(
                    refused.value.response.body)
            assert not await asking and relay.state == "refused"
            with pytest.raises(InvalidStatus):
                await relay_client(url, tokens.mint("cc-3"))  # a client's own connect never asks after a Deny
            assert port.sessions == 1
            await relay.open("connect")  # Try again: the user's click asks once more
            assert port.sessions == 2
        finally:
            await relay.close()
            await stop()
            await port.stop()


TABLE = {  # Decision 10: (who asks, identity) -> the decision in each state
    ("start", ""): dict(connected="accept", asking="join", ready="open", lost="no", refused="no", off="no"),
    ("connect", ""): dict(connected="accept", asking="join", ready="open", lost="open", refused="open", off="no"),
    ("turn", "a1"): dict(connected="accept", asking="join", ready="open", lost="open", refused="open", off="no"),
    ("client", "a1"): dict(connected="accept", asking="join", ready="open", lost="open", refused="no", off="no"),
    ("client", "a2"): dict(connected="accept", asking="join", ready="no", lost="no", refused="no", off="no"),
    ("client", "cc-1"): dict(connected="accept", asking="join", ready="open", lost="open", refused="no", off="no"),
}


async def test_open_follows_the_table(tmp_path):
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"  # no port file: the switch is off
    relay = Relay(folder, Tokens(), allow_wait=1, every=0.1)
    relay.may_open = lambda identity: identity in ("a1", "cc-1")  # a1 works; a2 doesn't
    for (why, identity), row in TABLE.items():
        for state, decision in row.items():
            relay.state = state
            assert relay._decide(why, identity) == decision, (why, identity, state)
    relay.state = "ready"
    assert not await relay.open("connect") and relay.state == "off" and relay.upstream_opens == 0  # no port file
    relay.state = "refused"
    assert not await relay.open("client", "cc-1") and relay.upstream_opens == 0
    await relay.disconnect("a1")
    relay.state = "ready"
    assert relay._decide("turn", "a1") == "no" and not await relay.open("turn", "a1") and relay.upstream_opens == 0
    await relay.close()


async def test_handshake_refusals(rig):
    await rig.relay.open("start")
    token = rig.tokens.mint("a1")
    for options in ({"origin": "https://evil.example", "additional_headers": {"X-AIB-Agent-Token": token}},
                    {"origin": "null", "additional_headers": {"X-AIB-Agent-Token": token}},
                    {}, {"additional_headers": {"X-AIB-Agent-Token": "wrong"}}):
        with pytest.raises(InvalidStatus) as refused:
            await connect(rig.url, proxy=None, **options)
        assert refused.value.response.status_code == 403, options
    with pytest.raises(InvalidStatus) as refused:
        await connect(rig.url + "?token=" + token, proxy=None)  # a token in the address counts for nothing
    assert refused.value.response.status_code == 403
    for host in (f"localhost:{rig.relay.port}", f"attacker.example:{rig.relay.port}"):
        assert await raw_handshake(rig.relay.port, host, token) == 403, host
    assert [row for row in rig.relay.clients() if row["kind"] != "app"] == []  # no client was opened
    await rig.relay.disconnect("a1")
    with pytest.raises(InvalidStatus) as refused:
        await connect(rig.url, additional_headers={"X-AIB-Agent-Token": token}, proxy=None)
    assert refused.value.response.status_code == 410
    assert b"The user disconnected this client in AI Home." in bytes(refused.value.response.body)


async def test_the_relay_logs_no_page_text(rig, caplog):
    caplog.set_level(logging.DEBUG, logger="ai_browser")  # the relay's own lines (websockets logs frames at DEBUG)
    await rig.relay.open("start")
    a1 = await rig.client("a1")
    with pytest.raises(CDPError):
        await a1.send("Runtime.evaluate", {"expression": "'SECRET-7f3a'"})  # at browser level: refused
    with pytest.raises(CDPError):
        await a1.send("Runtime.evaluate", {"expression": "'SECRET-7f3a'"}, session_id="S-not-its-own")
    await rig.relay.local().send("Target.getTargets")  # the user's tab, titled SECRET-7f3a, goes through
    ours = [record.getMessage() for record in caplog.records if record.name.startswith(("ai_browser", "uvicorn"))]
    assert not any("SECRET-7f3a" in line for line in ours)
    assert any("Runtime.evaluate" in line for line in ours)  # the refusal, by name


async def test_clients_lists_who_is_connected_and_disconnect_cuts_one_off(rig):
    await rig.relay.open("start")
    rig.relay.local()
    a3, session = await rig.client("a3"), await rig.client("cc-x")
    tab = (await a3.send("Target.createTarget", {"url": "about:blank"}))["targetId"]
    await session.send("Browser.getVersion")
    assert rig.relay.clients() == [
        {"id": "app", "kind": "app", "number": None, "tabs": 0, "connected": True, "cut_off": False},
        {"id": "a3", "kind": "agent", "number": 3, "tabs": 1, "connected": True, "cut_off": False},
        {"id": "cc-x", "kind": "session", "number": None, "tabs": 0, "connected": True, "cut_off": False}]
    changes = []
    rig.relay.on_change(lambda: changes.append(1))
    await rig.relay.disconnect("a3")
    assert await until(lambda: a3.closed) and a3._ws.close_code == 4401 and changes
    assert rig.relay.clients()[1] == {"id": "a3", "kind": "agent", "number": 3, "tabs": 1, "connected": False,
                                      "cut_off": True}
    await rig.relay.forget("a3", close_tabs=True)
    assert [params["targetId"] for params in rig.sent("Target.closeTarget")] == [tab]
    assert [row["id"] for row in rig.relay.clients()] == ["app", "cc-x"]
    assert rig.relay.is_cut_off("a3")  # forget never clears it


# ---- Review Focus -----------------------------------------------------------------------------------------

async def test_a_closed_agents_old_token_gets_410(rig):
    await rig.relay.open("start")
    token = rig.tokens.mint("a4")
    rig.tokens.revoke("a4")  # the agent closed
    with pytest.raises(InvalidStatus) as refused:
        await relay_client(rig.url, token)
    assert refused.value.response.status_code == 410


async def test_a_frame_that_isnt_cdp_closes_only_that_client(rig):
    await rig.relay.open("start")
    a1 = await rig.client("a1")
    for frame in (b"\x00binary", "not json", json.dumps({"id": "x", "method": "Browser.getVersion"})):
        odd = await Raw.open(rig.url, rig.tokens.mint("a2"))
        await odd.ws.send(frame)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(odd.ws.wait_closed(), 10)
        assert odd.ws.close_code == 4400, frame
    assert (await a1.send("Browser.getVersion"))["product"] == "FakeBrave/1"


async def test_connect_twice_while_asking_is_one_question(tmp_path):
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, answer="silent")
    await port.start()
    relay = Relay(folder, Tokens(), allow_wait=5, every=0.1)
    await relay.start()  # the switch is on: ready
    try:
        first, second = relay.open("connect"), relay.open("connect")
        both = asyncio.gather(first, second)
        assert await until(lambda: relay.state == "asking")
        port.answer = "accept"
        port.release.set()
        assert await both == [True, True] and port.sessions == 1 and relay.upstream_opens == 1
    finally:
        await relay.close()
        await port.stop()


async def test_a_client_that_gives_up_during_the_question_leaves_nothing(tmp_path):
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, answer="silent")
    await port.start()
    tokens = Tokens()
    relay = Relay(folder, tokens, allow_wait=5, every=0.1)
    url, stop = await serve_relay(relay)
    await relay.start()
    try:
        with pytest.raises(TimeoutError):  # the engine gives up while Brave is asking
            await relay_client(url, tokens.mint("cc-1"), open_timeout=0.5)
        assert relay.state == "asking"
        port.answer = "accept"
        port.release.set()
        assert await until(lambda: relay.state == "connected")
        assert await until(lambda: [row for row in relay.clients() if row["kind"] != "app"] == [])
        later = await relay_client(url, tokens.mint("cc-1"))
        assert (await later.send("Browser.getVersion"))["product"] == "FakeBrave/1" and port.sessions == 1
        await later.close()
    finally:
        await relay.close()
        await stop()
        await port.stop()


# ---- plan review ---------------------------------------------------------------------------------------------

async def test_an_attach_that_lands_after_take_back_is_refused(rig):
    """Plan review, Important 3: an attach under way when the user clicks Take back is not bound when it lands."""
    await rig.relay.open("start")
    rig.handed["a1"] = {"U1"}
    a1 = await rig.client("a1")
    rig.port.hold = {"Target.attachToTarget"}
    attaching = asyncio.ensure_future(a1.send("Target.attachToTarget", {"targetId": "U1", "flatten": True}))
    assert await until(lambda: len(rig.port.held) == 1)
    await rig.relay.cut("a1", "U1")  # no session yet
    rig.handed["a1"] = set()
    rig.port.hold = set()
    await rig.port.answer_held()
    with pytest.raises(CDPError, match="No target with given id found"):
        await attaching
    assert await until(lambda: len(rig.sent("Target.detachFromTarget")) == 1)  # the browser's session ended too


async def test_create_target_takes_only_the_params_the_engine_uses(rig):
    """Plan review, Minor 7: no minimized or off-screen window; the AI's tabs stay in plain sight."""
    await rig.relay.open("start")
    a1 = await rig.client("a1")
    for extra in ({"windowState": "minimized"}, {"left": -5000}, {"width": 1}, {"hidden": False}):
        with pytest.raises(CDPError):
            await a1.send("Target.createTarget", {"url": "about:blank", "newWindow": True, **extra})
    assert "Target.createTarget" not in rig.port.methods
    await a1.send("Target.createTarget", {"url": "about:blank", "newWindow": True, "background": True})
    assert len(rig.sent("Target.createTarget")) == 1


async def test_a_tab_created_after_its_agent_was_forgotten_is_closed(rig):
    """Plan review, Minor 8: an agent closed while its new tab was being made leaves no tab and no row behind."""
    await rig.relay.open("start")
    a5 = await rig.client("a5")
    rig.port.hold = {"Target.createTarget"}
    creating = asyncio.ensure_future(a5.send("Target.createTarget", {"url": "about:blank"}))
    assert await until(lambda: len(rig.port.held) == 1)
    await rig.relay.forget("a5")  # the agent closed meanwhile
    rig.port.hold = set()
    await rig.port.answer_held()
    assert await until(lambda: len(rig.sent("Target.closeTarget")) == 1)
    assert rig.relay.own_targets("a5") == [] and "a5" not in [row["id"] for row in rig.relay.clients()]
    with contextlib.suppress(Exception):
        await asyncio.wait_for(creating, 1)


async def test_quitting_while_brave_asks_answers_the_waiting_handshakes(tmp_path):
    """Plan review, Minor 10: a handshake held for Brave's question gets "AI Browser is quitting" at once."""
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, answer="silent")
    await port.start()
    tokens = Tokens()
    relay = Relay(folder, tokens, allow_wait=30, every=0.1)
    url, stop = await serve_relay(relay)
    await relay.start()
    try:
        asking = asyncio.ensure_future(relay.open("connect"))
        assert await until(lambda: relay.state == "asking")
        waiting = asyncio.ensure_future(relay_client(url, tokens.mint("cc-1"), open_timeout=20))
        await asyncio.sleep(0.3)
        started = time.monotonic()
        await relay.close_clients(1001)
        with pytest.raises(InvalidStatus) as refused:
            await waiting
        assert refused.value.response.status_code == 409
        assert b"AI Browser is quitting" in bytes(refused.value.response.body) and time.monotonic() - started < 2
        assert not await asking
    finally:
        await relay.close()
        await stop()
        await port.stop()
