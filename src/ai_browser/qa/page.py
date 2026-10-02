"""Visit one page in a QA tab: load it, wake lazy content, then check and photograph it at three screen sizes."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

from ..browser import Browser, JSError, Tab, _arg_text, _forget, _jpeg_size
from ..cdp import CDPError
from ..config import SHOT_MAX_WIDTH, SIZES
from .issues import lower
from .model import Issue, PageResult, SizeResult
from .polite import HostGate, retry_after, stop_reason
from .urls import origin

PROBE_JS = Path(__file__).with_name("probe.js").read_text()
LOAD_WAIT = 15  # seconds for the load event; a page still loading after that is checked as it is
QUIET_WAIT = 3  # then at most this long for the network to go quiet
QUIET_AFTER_WAKE = 2
QUIET_GAP = 0.3  # quiet: nothing started or finished for this long...
STALE_REQUEST = 1.5  # ...ignoring requests open longer than this (long polling, streams)
FULL_MAX_HEIGHT = 8000
THUMB_WIDTH = 320
_MISSING = "__aibqa_missing__"
_IGNORED_ERRORS = {"net::ERR_ABORTED", "net::ERR_BLOCKED_BY_CLIENT"}  # navigation aborts, ad and tracker blockers
_IGNORED_BLOCKS = {"inspector", "subresource-filter", "mixed-content"}  # mixed content is reported on its own
_LOG_SOURCES = {"javascript", "worker", "storage", "rendering", "other"}  # not network or security: seen elsewhere
_RESOURCES = {"Script": ("high", "broken script"), "Stylesheet": ("high", "broken stylesheet"),
              "Image": ("medium", "broken image"), "Font": ("medium", "broken font"),
              "XHR": ("medium", "failed request"), "Fetch": ("medium", "failed request")}
_SOURCE = re.compile(r"^(https?://.+?)(?::\d+)?$")  # a URL with an optional :line


class PageVisitor:
    """Visits pages one after another in one tab, collecting what each page reports while it loads. Each visit holds
    its host's turn at the gate, from the navigation until the visit ends."""

    def __init__(self, browser: Browser, tab: Tab, gate: HostGate | None = None):
        self.browser = browser
        self.cdp = browser.cdp
        self.tab = tab
        self.gate = gate if gate is not None else HostGate()
        self._page: PageResult | None = None
        self._document: dict[str, str] = {}  # the page's own response headers, lower case (retry-after, cf-mitigated)
        self._open: dict[str, float] = {}  # request id -> when it started
        self._requests: dict[str, tuple[str, str, str]] = {}  # request id -> (url, resource type, frame id)
        self._activity = 0.0
        self._handlers = [
            ("Network.requestWillBeSent", self._on_request),
            ("Network.responseReceived", self._on_response),
            ("Network.loadingFinished", self._on_finished),
            ("Network.loadingFailed", self._on_failed),
            ("Runtime.consoleAPICalled", self._on_console),
            ("Runtime.exceptionThrown", self._on_exception),
            ("Log.entryAdded", self._on_log),
            ("Page.downloadWillBegin", self._on_download),
        ]
        self._cancels: set[asyncio.Future] = set()
        for method, handler in self._handlers:
            self.cdp.on(method, handler)

    def close(self) -> None:
        for method, handler in self._handlers:
            self.cdp.off(method, handler)

    # ---- one page --------------------------------------------------------------------------------------

    async def visit(self, url: str) -> PageResult:
        """Load and check one page. Raises HostStopped, sending nothing, when QA stopped on its host."""
        host = (urlsplit(url).hostname or "").lower()
        async with self.gate.turn(host):
            return await self._visit(url, host)

    async def _visit(self, url: str, host: str) -> PageResult:
        started = time.monotonic()
        page = PageResult(url)
        self._open.clear()
        self._requests.clear()
        self._document = {}
        self._activity = time.monotonic()
        self._page = page
        navigated = False
        try:
            await self._emulate("desktop")
            loaded = asyncio.ensure_future(
                self.cdp.wait_for("Page.loadEventFired", session_id=self.tab.session, timeout=LOAD_WAIT))
            try:
                navigation = await self._send("Page.navigate", {"url": url}, timeout=LOAD_WAIT + 5)
                if navigation.get("errorText"):
                    page.error = navigation["errorText"]
                    return page
                navigated = True
                await asyncio.wait([loaded], timeout=LOAD_WAIT)
            finally:
                _forget(loaded)
            await self._quiet(QUIET_WAIT)
            if self._refused(page, host, url):  # 429, 403 or a bot check header: the page is left as it is
                page.final_url = await self._eval("location.href")
                return page
            await self._probe("wake()", await_promise=True)
            await self._quiet(QUIET_AFTER_WAKE)
            page.final_url = await self._eval("location.href")
            page.title = await self._probe("title()") or ""
            page.links = [(href, text) for href, text in await self._probe("links()") or []]
            for name in SIZES:
                page.sizes[name] = await self._check_size(name)
        except (CDPError, JSError) as exc:
            if navigated:  # it loaded, then moved on (a script redirect) or stopped answering: keep what was found
                page.note = f"the page changed while it was being checked ({exc})"
            else:
                page.error = page.error or str(exc)
        finally:
            page.seconds = round(time.monotonic() - started, 2)
            self._page = None
        return page

    async def _check_size(self, name: str) -> SizeResult:
        if name != "desktop":
            await self._emulate(name)
            await self._settle()
        layout = await self._probe("layout()") or {}
        shot, thumb, width, height = await self._shots()
        return SizeResult(name, bool(layout.get("scrolls")), int(layout.get("overflow") or 0),
                          [str(item) for item in layout.get("offenders") or []], shot, thumb, width, height)

    def _refused(self, page: PageResult, host: str, url: str) -> bool:
        """The page itself answered 429 or 403, or with a bot check header: its host is stopped (with the pause it
        asked for), and the page isn't woken, scrolled or photographed."""
        challenge = self._document.get("cf-mitigated", "").strip().lower() == "challenge"
        if not challenge and page.status not in (403, 429):
            return False
        wait = retry_after(self._document.get("retry-after"), time.time())
        self.gate.stop(host, stop_reason(page.status, urlsplit(url).path or "/", wait, challenge=challenge), wait)
        return True

    async def _emulate(self, name: str) -> None:
        width, height, mobile = SIZES[name]
        await self._send("Emulation.setDeviceMetricsOverride",
                         {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": mobile})

    async def _settle(self) -> None:
        """Two animation frames for the new layout, then a moment for any images it asks for."""
        await self._eval("new Promise((resolve) => { let frames = 0; const tick = () => ++frames >= 2 ? "
                         "resolve(true) : requestAnimationFrame(tick); requestAnimationFrame(tick); "
                         "setTimeout(resolve, 300); })", await_promise=True)
        await self._quiet(1.0)

    async def _quiet(self, limit: float) -> None:
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            now = time.monotonic()
            busy = any(now - begun < STALE_REQUEST for begun in self._open.values())
            if not busy and now - self._activity >= QUIET_GAP:
                return
            await asyncio.sleep(0.05)

    async def _shots(self) -> tuple[bytes, bytes, int, int]:
        """A full-page JPEG (as wide as the content, at most 1280 px) and a small one of the top of the page."""
        metrics = await self._send("Page.getLayoutMetrics")
        view, content = metrics["cssVisualViewport"], metrics["cssContentSize"]
        view_width, view_height = view["clientWidth"], view["clientHeight"]
        device_width = metrics.get("visualViewport", {}).get("clientWidth", 0)
        density = max(1.0, device_width / view_width) if view_width else 1.0
        width = min(max(view_width, content["width"]), view_width * 2)
        height = max(1, min(content["height"], FULL_MAX_HEIGHT))
        full = await self._capture({"x": 0, "y": 0, "width": width, "height": height,
                                    "scale": min(1.0, SHOT_MAX_WIDTH / (width * density))}, beyond=True)
        thumb = await self._capture({"x": 0, "y": 0, "width": view_width, "height": view_height,
                                     "scale": min(1.0, THUMB_WIDTH / (view_width * density))}, beyond=False)
        shot_width, shot_height = _jpeg_size(full)
        return full, thumb, shot_width, shot_height

    async def _capture(self, clip: dict, beyond: bool) -> bytes:
        result = await self._send("Page.captureScreenshot", {
            "format": "jpeg", "quality": 60, "clip": clip, "captureBeyondViewport": beyond}, timeout=60)
        return base64.b64decode(result["data"])

    async def _send(self, method: str, params: dict | None = None, timeout: float = 30) -> dict:
        return await self.cdp.send(method, params, session_id=self.tab.session, timeout=timeout)

    async def _eval(self, expression: str, await_promise: bool = False):
        """In the reader's isolated world of this tab: a page can't hide its own problems from QA either."""
        return await self.browser.eval_in(self.tab, expression, await_promise, timeout=20)

    async def _probe(self, call: str, await_promise: bool = False):
        """Call window.__aibqa.<call>, injecting the probe first when this document lacks it."""
        expression = f"window.__aibqa ? window.__aibqa.{call} : {json.dumps(_MISSING)}"
        value = await self._eval(expression, await_promise)
        if value == _MISSING:
            await self._eval(PROBE_JS)
            value = await self._eval(expression, await_promise)
        return value

    # ---- what the page reports while it loads -----------------------------------------------------------

    def _mine(self, session: str | None) -> bool:
        return session == self.tab.session and self._page is not None

    def _on_request(self, params: dict, session: str | None) -> None:
        if not self._mine(session):
            return
        request_id, request = params.get("requestId", ""), params.get("request", {})
        kind, frame = params.get("type", "Other"), params.get("frameId", "")
        redirect = params.get("redirectResponse")
        if redirect and kind == "Document" and frame == self.tab.frame:
            self._page.hops.append((redirect.get("url", ""), int(redirect.get("status") or 0)))
        self._open[request_id] = self._activity = time.monotonic()  # a redirect keeps its id: still open
        self._requests[request_id] = (request.get("url", ""), kind, frame)
        mixed = request.get("mixedContentType")
        if mixed in ("blockable", "optionally-blockable"):
            self._page.insecure.append((request.get("url", ""), mixed))

    def _on_response(self, params: dict, session: str | None) -> None:
        if not self._mine(session):
            return
        response, kind = params.get("response", {}), params.get("type", "Other")
        status = int(response.get("status") or 0)
        if kind == "Document" and params.get("frameId") == self.tab.frame:
            self._page.status = status
            self._document = {str(key).lower(): str(value) for key, value in (response.get("headers") or {}).items()}
        elif status >= 400:
            self._page.failed.append((response.get("url", ""), kind, str(status)))

    def _on_finished(self, params: dict, session: str | None) -> None:
        if session == self.tab.session:
            self._open.pop(params.get("requestId", ""), None)
            self._activity = time.monotonic()

    def _on_failed(self, params: dict, session: str | None) -> None:
        if session != self.tab.session:
            return
        request_id = params.get("requestId", "")
        self._open.pop(request_id, None)
        self._activity = time.monotonic()
        if self._page is None or params.get("canceled"):
            return
        error, blocked = params.get("errorText", ""), params.get("blockedReason", "")
        if error in _IGNORED_ERRORS or blocked in _IGNORED_BLOCKS:
            return
        url, kind, frame = self._requests.get(request_id, ("", params.get("type", "Other"), ""))
        if kind == "Document" and frame == self.tab.frame:
            return  # the page itself: its navigation reports that
        self._page.failed.append((url, params.get("type") or kind, f"blocked: {blocked}" if blocked else error))

    def _on_console(self, params: dict, session: str | None) -> None:
        if not self._mine(session) or params.get("type") not in ("error", "assert"):
            return
        frames = (params.get("stackTrace") or {}).get("callFrames") or []
        top = frames[0] if frames else {}
        where = f"{top['url']}:{top.get('lineNumber', 0) + 1}" if top.get("url") else ""
        text = " ".join(_arg_text(arg) for arg in params.get("args", []))
        self._page.console.append((text[:300], where))

    def _on_exception(self, params: dict, session: str | None) -> None:
        if not self._mine(session):
            return
        details = params.get("exceptionDetails", {})
        text = (details.get("exception", {}).get("description") or details.get("text") or "").split("\n")[0]
        where = f"{details['url']}:{details.get('lineNumber', 0) + 1}" if details.get("url") else ""
        self._page.exceptions.append((text[:300], where))

    def _on_log(self, params: dict, session: str | None) -> None:
        if not self._mine(session):
            return
        entry = params.get("entry", {})
        if entry.get("level") == "error" and entry.get("source") in _LOG_SOURCES:
            self._page.console.append((entry.get("text", "")[:300], entry.get("url", "")))

    def _on_download(self, params: dict, session: str | None) -> None:
        """A page started a download by itself (a refresh or a script): cancel it, whenever it happens."""
        if session != self.tab.session:
            return
        if self._page is not None:
            self._page.downloads.append(params.get("url", ""))
        if params.get("guid"):
            cancel = asyncio.ensure_future(self._cancel_download(params["guid"]))
            self._cancels.add(cancel)
            cancel.add_done_callback(self._cancels.discard)

    async def _cancel_download(self, guid: str) -> None:
        with contextlib.suppress(CDPError):
            await self.cdp.send("Browser.cancelDownload", {"guid": guid})


def page_issues(page: PageResult, site: str) -> list[Issue]:
    """The problems found on one page (links are judged separately, once for the whole site)."""
    where_url = page.final_url or page.url
    issues: list[Issue] = []

    def add(severity: str, kind: str, detail: str, extra: str = "", elsewhere: bool = False, sizes=()) -> None:
        issues.append(Issue(lower(severity) if elsewhere else severity, kind, detail, [where_url], list(sizes), extra))

    if page.error:
        add("high", "page didn't load", f"{page.url} ({page.error})")
        return issues
    if page.status and page.status >= 400 and page.status not in (403, 429):  # the start page has no check first;
        add("high", "broken page", f"{page.url} ({page.status})")  # a refusal stops QA there (the summary says so)
    if page.note:
        add("low", "check incomplete", page.note)
    for url in page.downloads:
        add("low", "starts a download", url)
    for text, where in page.exceptions:
        if not _extension(where):
            add("high", "script error", text, where, _elsewhere(where, site))
    for text, where in page.console:
        if not _extension(where):
            add("medium", "console error", text, where, _elsewhere(where, site))
    for url, kind, why in page.failed:
        if _extension(url):
            continue
        if why == "blocked: csp":
            add("medium", "blocked by CSP", url)  # the site's own policy, whoever's file it was
            continue
        severity, name = _RESOURCES.get(kind, ("medium", "broken resource"))
        add(severity, name, f"{url} ({why})", elsewhere=_elsewhere(url, site))
    for url, mixed in page.insecure:
        if mixed == "blockable":
            add("high", "insecure content blocked", url)
        else:
            add("medium", "insecure content", url)
    scrolling = [name for name in SIZES if name in page.sizes and page.sizes[name].scrolls]
    if scrolling:
        smallest = page.sizes[scrolling[-1]]  # SIZES runs from desktop down to mobile
        detail = "; ".join(smallest.offenders) or f"the page is {smallest.overflow_px} px wider than the screen"
        add("high" if "mobile" in scrolling else "medium", "sideways scroll", detail, sizes=scrolling)
    return issues


def _extension(location: str) -> bool:
    """A browser extension's own code or files (in the user's own browser), not the site's."""
    return location.startswith(("chrome-extension://", "moz-extension://", "safari-web-extension://"))


def _elsewhere(location: str, site: str) -> bool:
    """True when the location (a URL, maybe with :line) is on another site: someone else's code."""
    match = _SOURCE.match(location or "")
    return bool(match) and origin(match.group(1)) != site
