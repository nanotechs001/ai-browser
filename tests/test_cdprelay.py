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
