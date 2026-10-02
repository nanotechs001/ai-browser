"""Drive Chromium over CDP for ai-browser: owned tabs, reading pages, and guarded actions."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import csv
import io
import json
import posixpath
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .cdp import CDP, CDPError
from .checks import Check, box_frames, detect
from .config import JS_LIMIT, MAX_ROWS, NAME_LIMIT, SHOT_MAX_HEIGHT, SHOT_MAX_WIDTH, SIZES, TEXT_LIMIT, Config
from .keys import key_event
from .render import diff_rows, render_check, render_diff, render_page, risky_regex
from .steps import ID_OPS, Step
from .workfs import WorkDir

READER_JS = Path(__file__).with_name("reader.js").read_text(encoding="utf-8")  # it holds "…": never the OS default
WORLD = "aib"  # the reader's own isolated world: the page's scripts can neither see nor change it
LOAD_TIMEOUT = 15
CONTENT_WAIT = 3.0
WAIT_TEXT_CAP = 10
WAIT_MS_CAP = 10_000
NAV_OPS = {"goto", "back", "forward", "reload"}
LEAVE_BLOCKED = ("the page asks before leaving (it may have unsaved changes), so it stayed put — "
                 "ask the user, then repeat with confirmed=true")
LOG_KEEP = 200
LOG_SHOW = 50
NO_TAB = ("no tab to work in yet: open a page (open url), or adopt one of the user's tabs (tabs list, then tabs "
          "switch uN)")
_MISSING = "__aib_missing__"
_UNDEFINED = object()
CF_WAIT = 8.0  # seconds Cloudflare's own "Just a moment…" page gets to finish by itself; nothing is sent meanwhile
CF_POLL = 0.5


class BrowserError(RuntimeError):
    """A browser action failed; the message is meant for the user."""


class JSError(BrowserError):
    """JavaScript evaluated in the page threw."""


class StepStale(BrowserError):
    """The target changed, vanished or is covered; nothing was done."""


class StepBlocked(BrowserError):
    """The target is risky and the step was not confirmed; nothing was done."""


@dataclass
class Tab:
    key: str
    target: str
    session: str
    frame: str = ""      # main frame id
    loads: int = 0       # main-frame loads started (navigation detection)
    loading: bool = False
    last: dict | None = None  # last full-page reader state, the base for diffs
    log: deque = field(default_factory=lambda: deque(maxlen=LOG_KEEP))  # (kind, text, where)
    requests: dict = field(default_factory=dict)  # requestId -> "GET url"
    dialogs: list = field(default_factory=list)  # (kind, message, accepted), answered automatically
    reported: int = 0  # dialogs already shown to the caller
    adopted: bool = False  # a tab the user opened (AI Browser): left open when the session ends
    world: int | None = None  # the reader's isolated-world context in the current document (dropped on navigation)


@dataclass
class Shot:
    label: str
    data: bytes
    width: int
    height: int


def _exception_text(result: dict) -> str:
    details = result.get("exceptionDetails", {})
    exception = details.get("exception", {})
    return exception.get("description") or details.get("text") or "JavaScript error"


def _jpeg_size(data: bytes) -> tuple[int, int]:
    i = 2
    while i + 9 < len(data):
        marker, length = data[i + 1], int.from_bytes(data[i + 2:i + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2):
            return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
        i += 2 + length
    return 0, 0


def _arg_text(arg: dict) -> str:
    if "value" in arg:
        return arg["value"] if isinstance(arg["value"], str) else json.dumps(arg["value"])
    return arg.get("description") or arg.get("type", "")


def _forget(*futures: asyncio.Future) -> None:
    for future in futures:
        if not future.done():
            future.cancel()
        elif not future.cancelled():
            future.exception()  # mark as retrieved


def url_problem(url: str, mode: str) -> str | None:
    """Why a URL may not be opened, or None. The user's own Chrome runs on this Mac, so it opens web pages only;
    AI Browser (app mode) also opens its extensions' pages; the sandbox may also open the files it shares with the
    shell under file:///work/ (never its own profile)."""
    try:
        parts = urlsplit(url.strip())
    except ValueError as exc:
        return f"not a valid address ({exc})"
    scheme = parts.scheme.lower()
    if scheme in {"http", "https", "data"} or (scheme == "about" and parts.path == "blank"):
        return None
    if not scheme:
        return "use a full address such as https://example.com"
    if mode == "app":
        if scheme == "chrome-extension":
            return ("AI Browser's own pages and other extensions' pages don't open from here: if the user opened one, "
                    "adopt it with tabs switch uN")
        return ("only web pages open in AI Browser: local files and chrome:// pages would reach this Mac and Chrome's "
                "settings (use read_file for work files)")
    if mode == "chrome":
        return ("only web pages (http, https, data:, about:blank) open in your own Chrome: local files and chrome:// "
                "pages would reach this Mac and Chrome's settings (use read_file for work files)")
    path = posixpath.normpath(unquote(parts.path).replace("\\", "/"))
    if scheme == "file" and parts.netloc in {"", "localhost"} and (path == "/work" or path.startswith("/work/")):
        return None
    return "only web pages and files under file:///work/ can be opened in the sandbox"


class Browser:
    def __init__(self, cdp: CDP, work: WorkDir, cfg: Config, mode: str = "sandbox", hidden_extension: str = "",
                 front: bool = True):
        self.cdp = cdp
        self.work = work
        self.cfg = cfg
        # "sandbox" (Docker Chromium), "chrome" (the user's own Chrome: change nothing, only our background tabs) or
        # "app" (AI Browser, the agent's own Chrome: visible tabs, the user's tabs can be adopted)
        self.mode = mode
        self.hidden_extension = hidden_extension  # AI Browser's own side panel: never listed or touched
        # In AI Browser: True when the user watches this session work (it started in their tab), so its tabs come to
        # the front; an agent started from AI Home works in background tabs and never takes the user's focus.
        self.front = front
        self._tab_events: list[Callable[[str, Tab], None]] = []  # ("opened" | "closed", tab)
        self._others: dict[str, str] = {}  # AI Browser tabs the user opened, by listing key (u1...) -> target id
        self.owned: dict[str, Tab] = {}
        self.current: Tab | None = None
        self._seq = 0
        self._risky = risky_regex(cfg.risky_words).pattern
        self._tab_listeners: list[Callable[[Tab], None]] = []
        self._allow_dialogs = False  # True only while running steps the user confirmed
        self._adopting: set[asyncio.Future] = set()
        self._opened: list[Tab] = []
        self._stepping = 0  # act steps running now
        self._lost: str | None = None  # key of the tab in use when something outside this session closed it
        self._check_hook: Callable[[Tab, Check], Awaitable[str]] | None = None  # the Engine's hold (on_check)
        # Set by the Engine: the refusal for an address on a site the user skipped after a bot check, or None...
        self.skipped_site: Callable[[str], str | None] = lambda url: None
        # ...and, while the session is held at a bot check, the waiting text (act then runs no step).
        self.waiting: Callable[[], str | None] = lambda: None
        cdp.on("Page.javascriptDialogOpening", self._on_dialog)
        cdp.on("Target.targetCreated", self._on_target_created)
        cdp.on("Target.targetDestroyed", self._on_target_destroyed)
        cdp.on("Page.frameStartedLoading", self._on_started)
        cdp.on("Page.frameStoppedLoading", self._on_stopped)
        cdp.on("Page.domContentEventFired", self._on_stopped_any)
        cdp.on("Page.frameNavigated", self._on_navigated)
        cdp.on("Runtime.consoleAPICalled", self._on_console)
        cdp.on("Runtime.exceptionThrown", self._on_exception)
        cdp.on("Log.entryAdded", self._on_log_entry)
        cdp.on("Network.requestWillBeSent", self._on_request)
        cdp.on("Network.responseReceived", self._on_response)
        cdp.on("Network.loadingFailed", self._on_failed)
        cdp.on("Runtime.executionContextDestroyed", self._on_context_destroyed)
        cdp.on("Runtime.executionContextsCleared", self._on_contexts_cleared)

    # ---- tabs and navigation tracking ---------------------------------------------------------

    @property
    def session_id(self) -> str | None:
        return self.current.session if self.current else None

    def on_tab_event(self, callback: Callable[[str, Tab], None]) -> None:
        """callback("opened" | "closed", tab) for each tab this session takes on or lets go of."""
        self._tab_events.append(callback)

    def _fire(self, kind: str, tab: Tab) -> None:
        for callback in self._tab_events:
            callback(kind, tab)

    def on_tab_change(self, callback: Callable[[Tab], None]) -> None:
        self._tab_listeners.append(callback)

    def _tab_for(self, session: str | None) -> Tab | None:
        return next((tab for tab in self.owned.values() if tab.session == session), None)

    def _on_started(self, params: dict, session: str | None) -> None:
        tab = self._tab_for(session)
        if tab and params.get("frameId") == tab.frame:
            tab.loads += 1
            tab.loading = True

    def _on_stopped(self, params: dict, session: str | None) -> None:
        tab = self._tab_for(session)
        if tab and params.get("frameId") == tab.frame:
            tab.loading = False

    def _on_stopped_any(self, params: dict, session: str | None) -> None:
        tab = self._tab_for(session)
        if tab:
            tab.loading = False

    def _on_navigated(self, params: dict, session: str | None) -> None:
        tab, frame = self._tab_for(session), params.get("frame", {})
        if tab and not frame.get("parentId"):
            tab.frame = frame.get("id", tab.frame)
            tab.world = None  # a new document: the reader's world there is a new context

    def _on_context_destroyed(self, params: dict, session: str | None) -> None:
        tab = self._tab_for(session)
        if tab and params.get("executionContextId") == tab.world:
            tab.world = None

    def _on_contexts_cleared(self, params: dict, session: str | None) -> None:
        tab = self._tab_for(session)
        if tab:
            tab.world = None

    # ---- dialogs: answered at once (a dialog left open freezes the tab) -----------------------

    def _on_dialog(self, params: dict, session: str | None) -> None:
        tab = self._tab_for(session)
        if tab is None:
            return
        kind, message = params.get("type", "alert"), params.get("message", "")
        accept = kind == "alert" or self._allow_dialogs
        reply = {"accept": accept}
        if kind == "prompt" and accept:
            reply["promptText"] = params.get("defaultPrompt", "")
        tab.dialogs.append((kind, message, accept))
        asyncio.ensure_future(self._answer_dialog(session, reply))

    async def _answer_dialog(self, session: str, reply: dict) -> None:
        try:
            await self.cdp.send("Page.handleJavaScriptDialog", reply, session_id=session)
        except CDPError:
            pass

    def _new_dialogs(self) -> list[tuple]:
        tab = self.current
        if tab is None:  # the tab was closed
            return []
        fresh = tab.dialogs[tab.reported:]
        tab.reported = len(tab.dialogs)
        return fresh

    @staticmethod
    def _dialog_text(kind: str, message: str, accepted: bool) -> str:
        return f'{kind} "{message}" {"accepted" if accepted else "dismissed"}'

    # ---- page log: console errors, exceptions and failed requests ---------------------------

    def _on_console(self, params: dict, session: str | None) -> None:
        tab, kind = self._tab_for(session), params.get("type")
        if not tab or kind not in {"error", "warning", "assert"}:
            return
        frames = (params.get("stackTrace") or {}).get("callFrames") or []
        where = f"{frames[0]['url'].rsplit('/', 1)[-1]}:{frames[0]['lineNumber'] + 1}" if frames else ""
        text = " ".join(_arg_text(arg) for arg in params.get("args", []))
        tab.log.append(("console." + ("warn" if kind == "warning" else kind), text, where))

    def _on_exception(self, params: dict, session: str | None) -> None:
        tab = self._tab_for(session)
        if tab:
            details = params.get("exceptionDetails", {})
            text = (details.get("exception", {}).get("description") or details.get("text") or "").split("\n")[0]
            tab.log.append(("exception", text, details.get("url", "").rsplit("/", 1)[-1]))

    def _on_log_entry(self, params: dict, session: str | None) -> None:
        tab, entry = self._tab_for(session), params.get("entry", {})
        if tab and entry.get("source") != "network" and entry.get("level") in {"error", "warning"}:
            tab.log.append((f"log.{entry['level']}", entry.get("text", ""), entry.get("url", "")))

    def _on_request(self, params: dict, session: str | None) -> None:
        tab = self._tab_for(session)
        if tab:
            if len(tab.requests) > 2000:
                tab.requests.clear()
            request = params.get("request", {})
            tab.requests[params.get("requestId")] = f"{request.get('method', 'GET')} {request.get('url', '')}"

    def _on_response(self, params: dict, session: str | None) -> None:
        tab, response = self._tab_for(session), params.get("response", {})
        if tab and response.get("status", 0) >= 400:
            request = tab.requests.get(params.get("requestId"), f"GET {response.get('url', '')}")
            tab.log.append((f"http {response['status']}", request, ""))

    def _on_failed(self, params: dict, session: str | None) -> None:
        tab = self._tab_for(session)
        if tab and not params.get("canceled"):
            request = tab.requests.get(params.get("requestId"), "request")
            tab.log.append(("request failed", f"{request} — {params.get('errorText', '')}", ""))

    async def page_log(self) -> str:
        if self.current is None:
            raise BrowserError("no open tab")
        entries = list(self.current.log)
        self.current.log.clear()
        if not entries:
            return "page log: nothing new (no console errors or warnings, exceptions, or failed requests)"
        shown = entries[-LOG_SHOW:]
        header = f"page log: {len(entries)} new"
        if len(shown) < len(entries):
            header += f" (showing the last {len(shown)})"
        lines = [header]
        for kind, text, where in shown:
            text = text if len(text) <= 300 else text[:299] + "…"
            lines.append(f"{kind:<15} {text}" + (f"  ({where})" if where else ""))
        return "\n".join(lines)

    async def start(self) -> None:
        if self.mode == "sandbox":  # a real Chrome (yours, or AI Browser) keeps the user's Downloads folder
            await self.cdp.send("Browser.setDownloadBehavior", {
                "behavior": "allow", "downloadPath": f"{self.work.sandbox_task}/downloads", "eventsEnabled": True})
        await self.cdp.send("Target.setDiscoverTargets", {"discover": True})
        if self.mode != "app":  # in AI Browser a blank tab would cover the user's page: one opens when needed
            await self._new_tab()

    def owned_targets(self) -> list[str]:
        """Tabs to close if this session dies: never the user's own (adopted) tabs."""
        return [tab.target for tab in self.owned.values() if not tab.adopted]

    async def close(self) -> None:
        for tab in list(self.owned.values()):
            try:
                if tab.adopted or self.mode == "app":  # the user's tab, or AI Browser (the app closes agents' tabs)
                    await self.cdp.send("Target.detachFromTarget", {"sessionId": tab.session})
                else:
                    await self.cdp.send("Target.closeTarget", {"targetId": tab.target})
            except CDPError:
                pass
        self.owned.clear()
        self.current = None
        self.work.drop_snapshots()  # upload copies are only needed while our tabs are open

    async def _call(self, method: str, params: dict | None = None, timeout: float = 30) -> dict:
        if self.current is None:
            raise BrowserError(NO_TAB)
        return await self.cdp.send(method, params, session_id=self.session_id, timeout=timeout)

    def _check_url(self, url: str) -> None:
        problem = url_problem(url, self.mode)
        if problem:
            raise BrowserError(f"{url}: {problem}")

    async def _new_tab(self, url: str | None = None) -> Tab:
        if url:
            self._check_url(url)  # before a tab exists, so a refused URL leaves nothing behind
        tab = await self.open_worker(background=self.mode == "chrome" or not self.front)
        await self._switch(tab)
        if url:
            await self._navigate(url)
        return tab

    async def open_worker(self, background: bool | None = None) -> Tab:
        """A new tab of ours (closed with the session) that does not become the working tab: Website QA uses these."""
        params = {"url": "about:blank"}
        if self.mode in ("chrome", "app") if background is None else background:
            params["background"] = True  # don't steal the user's focus
        target = (await self.cdp.send("Target.createTarget", params))["targetId"]
        try:
            return await self._setup_tab(target)
        except BaseException:  # never leave a blank tab in the user's Chrome
            with contextlib.suppress(CDPError):
                await self.cdp.send("Target.closeTarget", {"targetId": target})
            raise

    async def close_tab(self, tab: Tab) -> None:
        if self.owned.pop(tab.key, None) is not None:
            self._fire("closed", tab)
        if tab is self.current:  # the next call carries on in another tab (ensure_tab)
            self.current, self._lost = None, tab.key
        with contextlib.suppress(CDPError):
            if tab.adopted:  # the user's own tab: let go of it, leave it open
                await self.cdp.send("Target.detachFromTarget", {"sessionId": tab.session})
            else:
                await self.cdp.send("Target.closeTarget", {"targetId": tab.target})

    def _fallback(self) -> Tab | None:
        """The tab to carry on in when the current one is gone: the newest of ours, never one of the user's."""
        ours = [tab for tab in self.owned.values() if not tab.adopted]
        return ours[-1] if ours else None

    def _on_target_destroyed(self, params: dict, session: str | None) -> None:
        """One of our tabs was closed outside our own tabs(close): by the user, its window, or the page itself."""
        target = params.get("targetId")
        for key, tab in list(self.owned.items()):
            if tab.target == target:
                del self.owned[key]
                self._fire("closed", tab)
                self._opened = [opened for opened in self._opened if opened is not tab]
                if tab is self.current:
                    self.current, self._lost = None, key

    async def ensure_tab(self) -> str:
        """Carry on after the tab in use was closed (in another of ours, or a new one); returns a note."""
        if self.current is not None or (self._lost is None and self.mode == "app"):
            return ""  # (in AI Browser a session starts without a tab of its own)
        lost, self._lost = self._lost or "in use", None
        fallback = self._fallback()
        if fallback is not None:
            await self._switch(fallback)
            return f"(tab {lost} was closed by the page or the user; now working in tab {self.current.key})\n"
        await self._new_tab()
        return f"(tab {lost} was closed by the page or the user, so a new tab {self.current.key} was opened)\n"

    def _on_target_created(self, params: dict, session: str | None) -> None:
        """Adopt tabs and popups that one of our tabs opened (target=_blank, window.open) while our own steps (or a
        QA run) were running. Any other new tab is the user's, even when it was opened from one of our tabs; and one
        opened from the user's (adopted) tab stays theirs too: followed, never closed."""
        info = params.get("targetInfo", {})
        opener = next((tab for tab in self.owned.values() if tab.target == info.get("openerId")), None)
        if info.get("type") != "page" or opener is None or not self._stepping:
            return
        adoption = asyncio.ensure_future(self._adopt(info["targetId"], users=opener.adopted))
        self._adopting.add(adoption)
        adoption.add_done_callback(self._adopting.discard)

    async def _adopt(self, target: str, users: bool = False) -> None:
        try:
            tab = await self._setup_tab(target, adopted=users)
        except CDPError:
            return  # closed before we could attach
        self._opened.append(tab)

    async def _follow_opened(self) -> str | None:
        """After a step: switch to a tab the page just opened; returns a note for the step line."""
        if self._adopting:
            await asyncio.wait(set(self._adopting), timeout=2)
        if not self._opened:
            return None
        previous, tab = self.current.key if self.current else None, self._opened[-1]
        self._opened.clear()
        await self._switch(tab)
        try:
            await self._ready()
        except (BrowserError, CDPError):
            pass
        back = f" (tabs switch {previous} to go back)" if previous in self.owned else ""
        return f"the page opened new tab {tab.key}; now working in it{back}"

    async def _setup_tab(self, target: str, adopted: bool = False) -> Tab:
        session = (await self.cdp.send("Target.attachToTarget", {"targetId": target, "flatten": True}))["sessionId"]
        self._seq += 1
        tab = Tab(f"t{self._seq}", target, session)
        width, height, _ = SIZES["desktop"]

        def send(method: str, params: dict | None = None):
            return self.cdp.send(method, params, session_id=session)

        setup = [
            send("Page.enable"),
            send("Runtime.enable"),
            send("Network.enable", {"maxTotalBufferSize": 1_000_000, "maxResourceBufferSize": 100_000}),
            send("Log.enable"),
            send("Page.setLifecycleEventsEnabled", {"enabled": True}),
            # Also keeps a background tab in the user's Chrome visible: without it the tab is hidden (even more so
            # when the window is minimized), frames stop and timers run once a second, so a click took 6 s, not 20 ms.
            send("Emulation.setFocusEmulationEnabled", {"enabled": True}),
            send("Page.addScriptToEvaluateOnNewDocument", {"source": READER_JS, "worldName": WORLD}),
        ]
        if self.mode == "sandbox":  # the user's own Chrome keeps its real window size
            setup.append(send("Emulation.setDeviceMetricsOverride",
                              {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False}))
        await asyncio.gather(*setup)
        tab.frame = (await send("Page.getFrameTree"))["frameTree"]["frame"]["id"]
        tab.adopted = adopted
        self.owned[tab.key] = tab
        self._fire("opened", tab)
        return tab

    async def adopt(self, target: str) -> Tab:
        """Work in one of the user's tabs: it stays theirs (released, never closed, by this session)."""
        tab = await self._setup_tab(target, adopted=True)
        await self._switch(tab)
        return tab

    async def _switch(self, tab: Tab) -> None:
        self.current = tab
        for callback in self._tab_listeners:
            callback(tab)
        if self.mode == "app" and self.front:  # the user sees the tab Claude works in
            with contextlib.suppress(CDPError):
                await self.cdp.send("Target.activateTarget", {"targetId": tab.target})

    async def _load(self, start: Awaitable[dict], history: bool = False) -> None:
        """Run a navigation command and wait until the new page has content."""
        session = self.session_id
        leave = asyncio.ensure_future(self.cdp.wait_for(
            "Page.javascriptDialogOpening", session_id=session, timeout=LOAD_TIMEOUT,
            predicate=lambda p: p.get("type") == "beforeunload"))

        def asked_to_leave() -> bool:
            return leave.done() and not leave.cancelled() and leave.exception() is None

        waiters = [
            asyncio.ensure_future(self.cdp.wait_for("Page.domContentEventFired", session_id=session,
                                                    timeout=LOAD_TIMEOUT)),
            asyncio.ensure_future(self.cdp.wait_for(
                "Page.frameNavigated", session_id=session, timeout=LOAD_TIMEOUT,
                predicate=lambda p: p.get("type") == "BackForwardCacheRestore" and not p["frame"].get("parentId"))),
            asyncio.ensure_future(self.cdp.wait_for("Page.navigatedWithinDocument", session_id=session,
                                                    timeout=LOAD_TIMEOUT)),
        ]
        try:
            result = await start
            if asked_to_leave() and not self._allow_dialogs:
                raise StepBlocked(LEAVE_BLOCKED)
            if result.get("errorText"):
                raise BrowserError(f"navigation failed: {result['errorText']}")
            if history or result.get("loaderId"):
                done, _ = await asyncio.wait([*waiters, leave], timeout=LOAD_TIMEOUT,
                                             return_when=asyncio.FIRST_COMPLETED)
                if asked_to_leave():
                    if not self._allow_dialogs:
                        raise StepBlocked(LEAVE_BLOCKED)
                    if not any(waiter in done for waiter in waiters):  # accepted: now wait for the page
                        await asyncio.wait(waiters, timeout=LOAD_TIMEOUT, return_when=asyncio.FIRST_COMPLETED)
        finally:
            _forget(*waiters, leave)
        await self._ready()

    async def _navigate(self, url: str) -> None:
        self._check_url(url)
        try:
            await self._load(self._call("Page.navigate", {"url": url}))
        except StepBlocked:
            raise
        except BrowserError as exc:
            raise BrowserError(f"could not open {url}: {exc}") from None

    async def _history(self, delta: int) -> None:
        history = await self._call("Page.getNavigationHistory")
        index = history["currentIndex"] + delta
        if not 0 <= index < len(history["entries"]):
            raise BrowserError("there is no page to go " + ("back" if delta < 0 else "forward") + " to")
        entry = history["entries"][index]["id"]
        await self._load(self._call("Page.navigateToHistoryEntry", {"entryId": entry}), history=True)

    async def _ready(self) -> None:
        """Wait (up to CONTENT_WAIT) while the page is still a bare loading shell, so reads aren't empty."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + CONTENT_WAIT
        while not await self._reader("ready()") and loop.time() < deadline:
            await asyncio.sleep(0.05)

    # ---- evaluation: the reader's isolated world (js alone runs in the page's own world) ------------

    async def isolated(self, tab: Tab) -> int:
        """The reader's isolated world in the tab's current document. Chrome keeps one per frame and name, so this is
        the world the reader was installed in at document start; cached until the page navigates."""
        if tab.world is None:
            reply = await self.cdp.send("Page.createIsolatedWorld", {"frameId": tab.frame, "worldName": WORLD},
                                        session_id=tab.session)
            tab.world = reply["executionContextId"]
        return tab.world

    async def _evaluate(self, tab: Tab | None, params: dict, timeout: float = 30) -> dict:
        """Runtime.evaluate in the reader's world of `tab`; a context gone with its page is renewed once."""
        if tab is None:
            raise BrowserError(NO_TAB)
        context = await self.isolated(tab)
        try:
            return await self.cdp.send("Runtime.evaluate", {**params, "contextId": context},
                                       session_id=tab.session, timeout=timeout)
        except CDPError as exc:
            if "Cannot find context" not in str(exc):
                raise
        if tab.world == context:
            tab.world = None
        return await self.cdp.send("Runtime.evaluate", {**params, "contextId": await self.isolated(tab)},
                                   session_id=tab.session, timeout=timeout)

    async def eval_in(self, tab: Tab | None, expression: str, await_promise: bool = False, timeout: float = 30):
        """Evaluate in the reader's isolated world of `tab`: it shares the page's DOM, never its JavaScript."""
        result = await self._evaluate(tab, {"expression": expression, "returnByValue": True,
                                            "awaitPromise": await_promise}, timeout)
        if "exceptionDetails" in result:
            raise JSError(_exception_text(result))
        return result.get("result", {}).get("value")

    async def _eval(self, expression: str, await_promise: bool = False, timeout: float = 30):
        return await self.eval_in(self.current, expression, await_promise, timeout)

    async def _reader_in(self, tab: Tab | None, call: str, await_promise: bool = False, timeout: float = 30):
        """Call window.__aib.<call> in the tab's isolated world, injecting the reader there if this document lacks it
        (a tab adopted before the session attached)."""
        expression = f"window.__aib ? window.__aib.{call} : {json.dumps(_MISSING)}"
        value = await self.eval_in(tab, expression, await_promise, timeout)
        if value == _MISSING:
            await self.eval_in(tab, READER_JS)
            value = await self.eval_in(tab, expression, await_promise, timeout)
        return value

    async def _reader(self, call: str, await_promise: bool = False, timeout: float = 30):
        return await self._reader_in(self.current, call, await_promise, timeout)

    # ---- reading ------------------------------------------------------------------------------

    async def state(self, find: str | None = None) -> dict:
        """The reader's page state, plus `check` (a bot check, or None) and `boxes` (checkbox frames, each also
        marked `box` among the frames), decided here from its signals."""
        opts = {"find": find, "maxRows": MAX_ROWS, "textLimit": TEXT_LIMIT, "nameLimit": NAME_LIMIT,
                "risky": self._risky}
        state = await self._reader(f"observe({json.dumps(opts)})")
        signals = state.get("signals") or {}
        state["check"] = detect(state.get("url", ""), signals)
        state["boxes"] = box_frames(signals)
        boxed = {box.get("src") for box in state["boxes"]}
        for frame in state.get("frames") or []:
            if frame.get("url") in boxed:
                frame["box"] = True
        if find is None and self.current:
            self.current.last = state
        return state

    async def _settled_state(self, find: str | None = None) -> dict:
        """The state; on Cloudflare's own check, read again once it moved on by itself (CF_WAIT at most)."""
        state = await self.state(find)
        check = state["check"]
        if check is not None and check.kind == "cloudflare" and await self._cloudflare_wait(self.current) is not None:
            await self._ready()
            state = await self.state(find)
        return state

    async def observe(self, find: str | None = None) -> str:
        state = await self._settled_state(find)
        dialogs = [f"(page {self._dialog_text(*dialog)})" for dialog in self._new_dialogs()]
        if state["check"] is not None:  # nothing to click, no text, no picture: the user's to solve
            return "\n".join(dialogs + [await self._handoff(state["check"])])
        skipped = self.skipped_site(state.get("url", ""))
        return "\n".join(dialogs + [skipped if skipped is not None else render_page(state)])

    async def open(self, url: str, new_tab: bool = False) -> str:
        if new_tab or self.current is None:
            await self._new_tab(url)
        else:
            await self._navigate(url)
        return await self.observe()

    # ---- bot checks: seen, handed to the user, never touched ------------------------------------

    def on_check(self, callback: Callable[[Tab, Check], Awaitable[str]]) -> None:
        """The Engine's hook: a read found a bot check in this tab; it holds the session and returns the hand-off."""
        self._check_hook = callback

    async def check_now(self, tab: Tab | None = None) -> Check | None:
        """The bot check the tab's page is, or None: the signals only, never anything inside a check frame."""
        return (await self._check_tab(tab or self.current))[1]

    async def _check_tab(self, tab: Tab | None) -> tuple[str, Check | None]:
        """(address, bot check or None) of the tab's page; Cloudflare's own check gets CF_WAIT to move on."""
        signals = await self._reader_in(tab, "signals()") or {}
        url = str(signals.get("url") or "")
        found = detect(url, signals)
        if found is not None and found.kind == "cloudflare":
            moved = await self._cloudflare_wait(tab)
            if moved is not None:
                return moved
        return url, found

    async def _cloudflare_wait(self, tab: Tab | None) -> tuple[str, Check | None] | None:
        """Watch Cloudflare's own check for up to CF_WAIT, touching nothing: (address, check) once the page moved on,
        or None while it is still there."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + CF_WAIT
        while loop.time() < deadline:
            await asyncio.sleep(CF_POLL)
            try:
                signals = await self._reader_in(tab, "signals()") or {}
            except (BrowserError, CDPError):
                continue  # the page is moving on: read it again
            url = str(signals.get("url") or "")
            found = detect(url, signals)
            if found is None or found.kind != "cloudflare":
                return url, found
        return None

    async def bring_to_front(self, tab: Tab) -> None:
        """The tab becomes the working one (the live view follows) and comes to the front, whatever `front` says."""
        await self._switch(tab)
        with contextlib.suppress(CDPError):
            await self.cdp.send("Target.activateTarget", {"targetId": tab.target})

    async def _handoff(self, check: Check) -> str:
        """The working tab is a bot check: the Engine holds the session; without it, the tab comes forward."""
        tab = self.current
        if self._check_hook is not None:
            return await self._check_hook(tab, check)
        await self.bring_to_front(tab)
        return render_check(check, tab.key)

    async def _landed(self, opened: bool = False) -> str | None:
        """After a step that loaded a page or opened a tab: the hand-off or the skipped text that ends the batch. A tab
        the step just opened may still show its first blank page: it gets CONTENT_WAIT to load what it was opened for,
        so a check in a popup ends the batch before the next step runs."""
        if self.current is None:
            return None
        loop = asyncio.get_running_loop()
        deadline = loop.time() + (CONTENT_WAIT if opened else 0)
        while True:
            try:
                url, check = await self._check_tab(self.current)
            except (BrowserError, CDPError):
                url, check = "", None  # still changing: the read after the steps looks again
            if check is not None or url not in ("", "about:blank") or loop.time() >= deadline:
                break
            await asyncio.sleep(0.1)
        if check is not None:
            return await self._handoff(check)
        return self.skipped_site(url) if url else None

    async def _blocked(self) -> str | None:
        """Before screenshot, extract, js or act touch the working tab: the hand-off for a bot check that came up since
        the last read (an invisible check's picture challenge shows up a moment after a submit click, with no new
        page), or the skipped text for a skipped site; None when the page is clear. One read of the signals."""
        if self.current is None:
            return None
        url, check = await self._check_tab(self.current)
        if check is not None:
            return await self._handoff(check)
        return self.skipped_site(url) if url else None

    # ---- screenshots ----------------------------------------------------------------------------

    async def screenshot(self, size: str = "desktop", full_page: bool = False,
                         element: str | None = None) -> list[Shot] | str:
        """The shots, or the hand-off (or skipped) text instead when the page is a bot check (or a skipped site)."""
        names = list(SIZES) if size == "all" else [size]
        if any(name not in SIZES for name in names):
            raise BrowserError(f"size {size!r}: use desktop, tablet, mobile or all")
        blocked = await self._blocked()
        if blocked is not None:  # never a picture of a check: the user's to solve
            return blocked
        shots = []
        try:
            for name in names:
                if name != "desktop":
                    await self._emulate(name)
                shots.append(await self._capture(name, full_page, element))
        finally:
            if names != ["desktop"]:
                await self._emulate("desktop")
        return shots

    async def _emulate(self, name: str) -> None:
        if name == "desktop" and self.mode in ("chrome", "app"):
            await self._call("Emulation.clearDeviceMetricsOverride")  # back to the real window
        else:
            width, height, mobile = SIZES[name]
            await self._call("Emulation.setDeviceMetricsOverride",
                             {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": mobile})
        await self._settle(None)

    async def _capture(self, label: str, full_page: bool, element: str | None) -> Shot:
        metrics = await self._call("Page.getLayoutMetrics")
        if element:
            rect = await self._reader(f"rect({json.dumps(element)})")
            if not rect:
                raise StepStale(f"{element} gone; observe again")
            clip = {"x": rect["x"], "y": rect["y"], "width": rect["w"], "height": rect["h"]}
        else:
            if full_page:
                content = metrics["cssContentSize"]
                clip = {"x": 0, "y": 0, "width": content["width"], "height": min(content["height"], SHOT_MAX_HEIGHT)}
            else:
                view = metrics["cssVisualViewport"]
                clip = {"x": view["pageX"], "y": view["pageY"], "width": view["clientWidth"],
                        "height": view["clientHeight"]}
        if clip["width"] <= 0 or clip["height"] <= 0:
            raise BrowserError("nothing to capture: the area has zero size")
        # Device pixels per CSS pixel (2 on Retina screens, in the user's own Chrome), measured by Chrome itself:
        # a page can overwrite its own devicePixelRatio.
        device, css = metrics.get("visualViewport", {}), metrics["cssVisualViewport"]
        density = device.get("clientWidth", 0) / css["clientWidth"] if css["clientWidth"] > 0 else 1
        scale = min(1.0, SHOT_MAX_WIDTH / (clip["width"] * max(density, 1)))
        result = await self._call("Page.captureScreenshot", {
            "format": "jpeg", "quality": 70, "clip": {**clip, "scale": scale},
            "captureBeyondViewport": bool(full_page or element)}, timeout=60)
        data = base64.b64decode(result["data"])
        width, height = _jpeg_size(data)
        return Shot(label, data, width, height)

    # ---- extraction and JavaScript ----------------------------------------------------------------

    async def extract(self, kind: str) -> str:
        if kind not in {"links", "tables", "meta"}:
            raise BrowserError(f"extract {kind!r}: use links, tables or meta")
        blocked = await self._blocked()
        if blocked is not None:
            return blocked
        data = await self._reader(f"extract({json.dumps(kind)})")
        if kind == "links":
            links = data["items"]
            path = self.work.write_text("links.json", json.dumps(links, ensure_ascii=False, indent=1))
            header = f"{len(links)} links saved to {path}"
            if data["total"] > len(links):
                header += f" (the page has {data['total']}; only the first {len(links)} were saved)"
            lines = [header] + [f"{link['text'] or '(no text)'} → {link['href']}" for link in links[:LOG_SHOW]]
            if len(links) > LOG_SHOW:
                lines.append(f"… {len(links) - LOG_SHOW} more in {path}")
            return "\n".join(lines)
        if kind == "tables":
            if not data["items"]:
                return "no tables on this page"
            lines = []
            for number, table in enumerate(data["items"], 1):
                buffer = io.StringIO()
                csv.writer(buffer).writerows(table["rows"])
                path = self.work.write_text(f"table-{number}.csv", buffer.getvalue())
                columns = max(len(row) for row in table["rows"])
                caption = f' "{table["caption"]}"' if table["caption"] else ""
                saved = len(table["rows"])
                cut = f" (of {table['totalRows']}; the rest was over the limit)" if table["totalRows"] > saved else ""
                lines.append(f"table-{number}.csv{caption}: {saved} rows{cut} × {columns} columns → {path}")
                lines += ["  " + " | ".join(row) for row in table["rows"][:3]]
            if data["total"] > len(data["items"]):
                lines.append(f"… the page has {data['total']} tables; only the first {len(data['items'])} were saved")
            return "\n".join(lines)
        lines = [f"{key}: {data[key]}" for key in ("title", "lang", "description", "canonical", "robots", "viewport")]
        lines += [f"{key}: {value}" for key, value in data["og"].items()]
        lines.append("headings:")
        lines += [f"  {'  ' * (level - 1)}h{level} {text}" for level, text in data["headings"]]
        lines.append(f"images without alt: {data['noAlt']} of {data['images']}")
        lines += [f"  {src}" for src in data["noAltExamples"]]
        lines.append(f"links: {data['links']} · words: {data['words']}")
        return "\n".join(lines)

    async def js(self, code: str) -> str:
        """Plain expression first; a top-level `return` gets a function wrapper; top-level `await` gets REPL mode."""
        blocked = await self._blocked()
        if blocked is not None:  # nothing runs in a check page
            return blocked
        try:
            value = await self._js_eval(code)
        except JSError as exc:
            if "Illegal return statement" in str(exc):
                value = await self._js_eval(f"(async () => {{\n{code}\n}})()")
            elif "await is only valid" in str(exc):
                value = await self._js_eval(code, repl=True)
            else:
                raise
        text = "undefined" if value is _UNDEFINED else json.dumps(value, ensure_ascii=False)
        if len(text) > JS_LIMIT:
            text = text[:JS_LIMIT] + f"… [truncated: {len(text) - JS_LIMIT} more chars]"
        return text

    async def _js_eval(self, expression: str, repl: bool = False):
        result = await self._call("Runtime.evaluate", {
            "expression": expression, "returnByValue": True, "awaitPromise": True, "userGesture": True,
            "replMode": repl}, timeout=60)
        if "exceptionDetails" in result:
            raise JSError(_exception_text(result))
        remote = result.get("result", {})
        if remote.get("type") == "undefined":
            return _UNDEFINED
        if "value" in remote:
            return remote["value"]
        return remote.get("description", remote.get("type"))

    # ---- tabs -------------------------------------------------------------------------------------

    async def tabs(self, action: str = "list", tab: str | None = None, url: str | None = None) -> str:
        if action == "list":
            return await self._tab_list()
        if action == "new":
            await self._new_tab(url)
            return await self.observe()
        if action == "switch" and tab in self._others:  # a tab the user opened in AI Browser: adopt it
            await self.adopt(self._others.pop(tab))
            return await self.observe()
        if action in {"switch", "close"}:
            if tab not in self.owned:
                raise BrowserError(f"no tab {tab}; open tabs: {', '.join([*self.owned, *self._others]) or 'none'}")
            if action == "switch":
                await self._switch(self.owned[tab])
                return await self.observe()
            closing = self.owned[tab]
            current = self.current is closing
            await self.close_tab(closing)
            if current:
                self._lost = None
                fallback = self._fallback()
                if fallback is not None:
                    await self._switch(fallback)
                else:
                    await self._new_tab()
            note = f"{tab} is the user's own tab: let go of it and left it open\n" if closing.adopted else ""
            return note + await self._tab_list()
        raise BrowserError(f"tabs action {action!r}: use list, new, switch or close")

    async def _tab_list(self) -> str:
        infos = (await self.cdp.send("Target.getTargets"))["targetInfos"]
        targets = {info["targetId"]: info for info in infos}
        lines = []
        for key, tab in self.owned.items():
            info = targets.get(tab.target, {})
            mark = "*" if tab is self.current else " "
            lines.append(f"{mark} {key}  {json.dumps(info.get('title', ''), ensure_ascii=False)}  {info.get('url', '')}")
        if self.mode == "app":  # AI Browser is the agent's: the user's tabs there may be used too (tabs switch u1)
            self._others = {}
            ours = {tab.target for tab in self.owned.values()}
            for info in infos:
                url = info.get("url", "")
                if info.get("type") != "page" or info["targetId"] in ours or url in ("", "about:blank") or \
                        url_problem(url, "app") or \
                        (self.hidden_extension and url.startswith(f"chrome-extension://{self.hidden_extension}/")):
                    continue  # empty tabs, chrome:// pages and our own side panel are never offered
                key = f"u{len(self._others) + 1}"
                self._others[key] = info["targetId"]
                lines.append(f"  {key}  {json.dumps(info.get('title', ''), ensure_ascii=False)}  {url}  "
                             "(not opened by this session)")
        return "\n".join(lines)

    # ---- acting -------------------------------------------------------------------------------

    async def act(self, steps: list[Step], confirmed: bool = False) -> str:
        waiting = self.waiting()
        if waiting is not None:  # the session is held at a bot check: no step runs
            return waiting
        if self.current is None:
            raise BrowserError("no open tab")
        blocked = await self._blocked()
        if blocked is not None:  # a check came up since the last read, or the page went to a skipped site: no step
            return blocked
        before = self.current.last or await self.state()
        lines: list[str] = [self._dialog_text(*dialog) for dialog in self._new_dialogs()]
        navigated, ended = False, None
        self._allow_dialogs = confirmed
        try:
            navigated, ended = await self._run_steps(steps, confirmed, lines)
        finally:
            self._allow_dialogs = False
        if ended is not None:  # the batch landed on a bot check or a skipped site: that is the whole answer
            return "\n".join(lines + [ended])
        # The steps already ran: their results must reach the caller even if the page is mid-change.
        state = None
        for attempt in range(2):
            if self.current is None:  # a step closed the tab (a sign-in popup that finished, say)
                lines.append((await self.ensure_tab()).strip())
                navigated = True
            try:
                state = await self._settled_state()
                break
            except (BrowserError, CDPError) as exc:
                if attempt == 1:
                    lines.append(f"(the page is still changing, so it could not be read: {exc}; call observe)")
                    return "\n".join(lines)
                await asyncio.sleep(0.5)
        if state["check"] is not None:
            return "\n".join(lines + [await self._handoff(state["check"])])
        skipped = self.skipped_site(state.get("url", ""))
        if skipped is not None:
            return "\n".join(lines + [skipped])
        if not navigated and state["doc"] == before.get("doc"):
            page = render_diff(diff_rows(before["rows"], state["rows"]), state, old_text=before.get("text"))
        else:
            page = render_page(state)
        return "\n".join(lines + [page])

    @contextlib.contextmanager
    def acting(self):
        """While our own steps (or a QA run) work: tabs the pages open now are ours to follow and close."""
        self._stepping += 1
        try:
            yield
        finally:
            self._stepping -= 1

    async def _run_steps(self, steps: list[Step], confirmed: bool, lines: list[str]) -> tuple[bool, str | None]:
        """Run steps until one fails, or one lands on a bot check or a skipped site; append a line per step.
        Returns (whether the page navigated, the text that ended the batch or None)."""
        with self.acting():
            return await self._run_steps_counted(steps, confirmed, lines)

    async def _run_steps_counted(self, steps: list[Step], confirmed: bool,
                                 lines: list[str]) -> tuple[bool, str | None]:
        navigated = False
        for index, step in enumerate(steps):
            remaining = steps[index:]
            if self.current is None or (navigated and any(s.op in ID_OPS or s.target for s in remaining)):
                count = len(remaining)
                lines.append(f"– skipped {count} step{'' if count == 1 else 's'} "
                             "(the page changed, so their element ids are gone)")
                break
            loads = self.current.loads
            started = time.perf_counter()
            try:
                note = await self._step(step, confirmed)
            except StepBlocked as exc:
                lines.append(f"⛔ blocked {step.raw}: {exc}")
                break
            except StepStale as exc:
                lines.append(f"✗ stale {step.raw}: {exc}")
                break
            except (BrowserError, CDPError, ValueError) as exc:
                lines.append(f"✗ error {step.raw}: {exc}")
                break
            ms = round((time.perf_counter() - started) * 1000)
            dialogs = self._new_dialogs()
            refused = [d for d in dialogs if not d[2]]
            if refused:  # the page asked for confirmation and we said no: the action did not happen
                kind, message, _ = refused[0]
                lines.append(f'⛔ blocked {step.raw}: the page asked "{message}" ({kind}) and it was dismissed — '
                             "ask the user, then repeat with confirmed=true")
                break
            notes = [note] if note else []
            notes += [self._dialog_text(*dialog) for dialog in dialogs]
            opened = await self._follow_opened()
            if opened:
                notes.append(opened)
                navigated = True
            lines.append(f"✓ {step.raw} {ms} ms" + (f" ({'; '.join(notes)})" if notes else ""))
            landed = bool(opened)
            if not opened:
                try:
                    if step.op in NAV_OPS or await self._finish_navigation(loads):
                        navigated = landed = True
                except (BrowserError, CDPError):
                    navigated = landed = True  # still loading: look for a check now; the read after the steps retries
            if landed:  # a new page or tab: a bot check or a skipped site ends the batch here
                ended = await self._landed(opened=bool(opened))
                if ended is not None:
                    rest = len(steps) - index - 1
                    if rest:
                        lines.append(f"– skipped {rest} step{'' if rest == 1 else 's'} (the batch stopped here: "
                                     "see below)")
                    return navigated, ended
        return navigated, None

    async def _finish_navigation(self, loads_before: int) -> bool:
        """If the last step started a page load, wait for it; True when the page changed."""
        tab = self.current
        if tab is None:  # the step closed the tab
            return True
        if tab.loads == loads_before:
            return False
        loop = asyncio.get_running_loop()
        deadline = loop.time() + LOAD_TIMEOUT
        while tab.loading and loop.time() < deadline:
            await asyncio.sleep(0.02)
        await self._ready()
        return True

    async def _target(self, element: str, kind: str, confirmed: bool) -> dict:
        result = await self._reader(
            f"target({json.dumps(element)}, {json.dumps(kind)}, {json.dumps(self._risky)})")
        if not result.get("ok"):
            reason = result.get("reason", "unavailable")
            if reason in {"disabled", "not editable", "not a file input"}:
                raise BrowserError(f"{element} is {reason}")
            by = f" by {result['by']}" if result.get("by") else ""
            raise StepStale(f"{element} {reason}{by}; the current page is below")
        if result.get("risky") and not confirmed and kind in {"click", "dblclick"}:
            raise StepBlocked(f'{element} "{result.get("name")}" is ⚠ risky — ask the user, '
                              "then repeat with confirmed=true")
        return result

    async def _settle(self, element: str | None) -> None:
        try:
            await self._reader(f"settle({json.dumps(element)})", await_promise=True, timeout=5)
        except (BrowserError, CDPError):
            pass  # the page is navigating away; _finish_navigation handles it

    async def _mouse(self, kind: str, x: float, y: float, **extra) -> None:
        await self._call("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, **extra})

    async def _click(self, target: dict, count: int = 1) -> None:
        x, y = target["x"], target["y"]
        await self._mouse("mouseMoved", x, y)
        for n in range(1, count + 1):
            await self._mouse("mousePressed", x, y, button="left", buttons=1, clickCount=n)
            await self._mouse("mouseReleased", x, y, button="left", buttons=0, clickCount=n)

    async def _press(self, combo: str) -> None:
        params, _ = key_event(combo)
        await self._call("Input.dispatchKeyEvent", {"type": "keyDown" if "text" in params else "rawKeyDown", **params})
        up = {k: v for k, v in params.items() if k not in {"text", "unmodifiedText", "commands"}}
        await self._call("Input.dispatchKeyEvent", {"type": "keyUp", **up})

    async def _drag(self, source: dict, dest: dict) -> None:
        x0, y0, x1, y1 = source["x"], source["y"], dest["x"], dest["y"]
        await self._call("Input.setInterceptDrags", {"enabled": True})
        intercepted = asyncio.ensure_future(
            self.cdp.wait_for("Input.dragIntercepted", session_id=self.session_id, timeout=0.3))
        try:
            await self._mouse("mouseMoved", x0, y0)
            await self._mouse("mousePressed", x0, y0, button="left", buttons=1, clickCount=1)
            await self._mouse("mouseMoved", x0 + 8, y0 + 8, button="left", buttons=1)
            try:
                data = (await intercepted)["data"]
            except asyncio.TimeoutError:
                data = None
            if data is not None:  # HTML5 drag and drop
                for kind in ("dragEnter", "dragOver", "drop"):
                    await self._call("Input.dispatchDragEvent", {"type": kind, "x": x1, "y": y1, "data": data})
            else:  # mouse-event dragging (sortable libraries)
                for i in range(1, 6):
                    await self._mouse("mouseMoved", x0 + (x1 - x0) * i / 5, y0 + (y1 - y0) * i / 5,
                                      button="left", buttons=1)
            await self._mouse("mouseReleased", x1, y1, button="left", buttons=0, clickCount=1)
        finally:
            _forget(intercepted)
            await self._call("Input.setInterceptDrags", {"enabled": False})

    async def _wait_text(self, text: str) -> None:
        """Wait for visible text, following the tab through navigations until the deadline."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + WAIT_TEXT_CAP
        while (remaining := deadline - loop.time()) > 0:
            try:
                if await self._reader(f"waitText({json.dumps(text)}, {int(remaining * 1000)})",
                                      await_promise=True, timeout=remaining + 5):
                    return
            except (JSError, CDPError):  # the page navigated mid-wait: keep waiting on the new one
                await asyncio.sleep(0.1)
                continue
            break
        raise BrowserError(f'"{text}" did not appear within {WAIT_TEXT_CAP:g}s')

    async def _scroll(self, step: Step) -> None:
        if step.target:
            if not await self._reader(f"scrollIntoView({json.dumps(step.target)})"):
                raise StepStale(f"{step.target} gone; the current page is below")
        elif step.value in {"top", "bottom"}:
            await self._eval("window.scrollTo(0, " +
                             ("0" if step.value == "top" else "document.documentElement.scrollHeight") + ")")
        else:
            width, height = await self._eval("[innerWidth, innerHeight]")
            amount = step.amount or int(height * 0.8)
            await self._mouse("mouseWheel", width / 2, height / 2, deltaX=0,
                              deltaY=amount if step.value == "down" else -amount)
        await self._settle(None)

    def _upload_path(self, value: str) -> str:
        """The file path to hand the browser for an upload from the work folder."""
        missing = BrowserError(f"{value}: no such file in the work folder {self.work.sandbox_task}")
        if self.mode in ("chrome", "app"):  # Chrome reads it from this Mac later: a copy the sandbox cannot swap
            try:
                return str(self.work.snapshot(value))
            except (FileNotFoundError, IsADirectoryError):
                raise missing from None
        if not self.work.to_host(value).is_file():
            raise missing
        return self.work.to_sandbox(value)

    async def _step(self, step: Step, confirmed: bool) -> str | None:
        op, element = step.op, step.target
        if op in {"click", "dblclick", "hover"}:
            target = await self._target(element, op, confirmed)
            if op == "hover":
                await self._mouse("mouseMoved", target["x"], target["y"])
            else:
                await self._click(target, 2 if op == "dblclick" else 1)
            await self._settle(element)
        elif op in {"type", "append"}:
            if element:
                await self._click(await self._target(element, op, confirmed=True))
                if op == "type":
                    await self._reader(f"selectContents({json.dumps(element)})")
                elif await self._reader(f"caretEnd({json.dumps(element)})") == "end-key":
                    await self._press("End")
            if step.value:
                await self._call("Input.insertText", {"text": step.value})
            elif op == "type" and element:
                await self._press("Delete")
            await self._settle(element)
        elif op == "key":
            await self._press(step.value)
            await self._settle(None)
        elif op == "select":
            await self._target(element, "select", confirmed=True)
            result = await self._reader(f"selectOption({json.dumps(element)}, {json.dumps(step.value)})")
            if not result.get("ok"):
                options = ", ".join(result.get("options") or [])
                raise BrowserError(result.get("reason", "cannot select") + (f"; options: {options}" if options else ""))
            await self._settle(element)
        elif op in {"check", "uncheck"}:
            target = await self._target(element, "click", confirmed)  # identity first, then state
            row = await self._reader(f"state({json.dumps(element)})")
            if row is None:
                raise StepStale(f"{element} gone; the current page is below")
            want = op == "check"
            if (row.get("checked") is True) == want:
                return "already " + ("checked" if want else "unchecked")
            await self._click(target)
            await self._settle(element)
        elif op == "drag":
            source = await self._target(element, "drag", confirmed=True)
            dest = await self._target(step.target2, "drop", confirmed=True)
            await self._drag(source, dest)
            await self._settle(None)
        elif op == "upload":
            await self._target(element, "upload", confirmed=True)
            path = self._upload_path(step.value)
            node = await self._evaluate(self.current, {"expression": f"window.__aib.node({json.dumps(element)})"})
            object_id = node.get("result", {}).get("objectId")
            if not object_id:
                raise StepStale(f"{element} gone; the current page is below")
            await self._call("DOM.setFileInputFiles", {"files": [path],
                                                        "objectId": object_id})
            await self._settle(None)
        elif op == "scroll":
            await self._scroll(step)
        elif op == "wait":
            if step.value is None:
                await asyncio.sleep(min(step.amount, WAIT_MS_CAP) / 1000)
            else:
                await self._wait_text(step.value)
        elif op == "goto":
            await self._navigate(step.value)
        elif op in {"back", "forward"}:
            await self._history(-1 if op == "back" else 1)
        elif op == "reload":
            await self._load(self._call("Page.reload"))
        return None
