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

from . import platforms
from .cdp import CDP, CDPError
from .checks import CHECK_FRAME, Check, box_frames, detect
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
NO_TAB_CHROME = ("no tab to work in yet: open a page (open url), or switch to a tab the user handed you (tabs list, "
                 "then tabs switch hN)")
_MISSING = "__aib_missing__"
_UNDEFINED = object()
CF_WAIT = 8.0  # seconds Cloudflare's own "Just a moment…" page gets to finish by itself; nothing is sent meanwhile
CF_POLL = 0.5
# Tabs a session keeps of its own (in the user's Brave each opens in a background window of its own): a new tab past
# these reuses the oldest. Tabs the user handed over never count; tabs its pages opened do.
MAX_OWN_TABS = 2
REUSED = "(opened in your oldest tab {key}: at most {limit} tabs of your own)\n"
# Frames from another site (the frames spec): Chrome attaches each frame of our tabs that runs in a process of its own,
# and nothing else, flattened and never paused at its start. The relay sends exactly this too, whatever it is asked.
AUTO_ATTACH = {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True, "filter": [{"type": "iframe"}]}
MAX_DEPTH = 5  # frames inside frames: deeper ones are never attached
MAX_FRAMES = 20  # frames read per observe; the rest stay "(not readable)" in it
FRAME_TIME = 2.0  # seconds the frames of one read share, so a page with many frames can't stall observe
PAGE = {"x": 0.0, "y": 0.0, "sx": 1.0, "sy": 1.0}  # where the page itself is drawn: a frame's place is relative to it
TRIED = "(tried your oldest tab {key}: at most {limit} tabs of your own) "  # before the error when it couldn't


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
    adopted: bool = False  # a tab the user handed over: left open when the session ends
    handed: bool = False  # a tab the user handed this agent in Mission Control: let go of when they take it back
    detached: bool = False  # the relay cut our session on this handed tab (Take back): let go of at the next call
    world: int | None = None  # the reader's isolated-world context in the current document (dropped on navigation)
    inside: dict = field(default_factory=dict)  # row id -> the Frame it was read in (the page's own rows: not listed)
    next: int = 1  # the next row number: the page and its frames number their rows from one count
    used: int = 0  # when the session last switched to it (0: never): the lowest is the oldest, reused past MAX_OWN_TABS
    frames: dict = field(default_factory=dict)  # frame id -> Frame: its frames from another site


@dataclass
class Frame:
    """A frame from another site in one of our tabs, read by a reader of its own (the frames spec). `session` reaches
    its document: its own session (a frame in a process of its own), or its parent's (another origin on the same site,
    in the parent's process). Its <iframe> element is in the document `host` is the session of."""
    frame: str  # its frame id; for a frame of its own process, its target id
    session: str
    host: str
    url: str = ""  # "" until the browser says (a new frame's address comes a moment after it is attached)
    depth: int = 1  # 1: in the tab's page; 2: in a frame of it; at most MAX_DEPTH
    world: int | None = None  # the reader's isolated world in its document (as Tab.world)
    followed: bool = False  # its address is known and isn't a check's: its downloads are caught, its frames attached


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


def _same_origin(parts, origin: str) -> bool:
    try:
        own = urlsplit(origin)
        return (parts.scheme.lower(), parts.hostname or "", parts.port) == (own.scheme.lower(), own.hostname or "",
                                                                            own.port)
    except ValueError:
        return False


def on_page(placed: dict, box: dict) -> dict:
    """Where a frame is drawn on the page: its <iframe> draws it at `box` in a document drawn at `placed`."""
    return {"x": placed["x"] + box["x"] * placed["sx"], "y": placed["y"] + box["y"] * placed["sy"],
            "sx": placed["sx"] * box["sx"], "sy": placed["sy"] * box["sy"]}


def url_problem(url: str, mode: str, app_origin: str = "") -> str | None:
    """Why a URL may not be opened, or None. Never AI Browser's own pages (the app's origin): they open only in its
    window, and an agent has no cookie for them anyway. The user's own browser runs on this computer, so it opens
    web pages only; the sandbox may also open the files it shares with the shell under file:///work/ (never its own
    profile)."""
    try:
        parts = urlsplit(url.strip())
    except ValueError as exc:
        return f"not a valid address ({exc})"
    if app_origin and _same_origin(parts, app_origin):
        return "AI Browser's own pages open only in its window"
    scheme = parts.scheme.lower()
    if scheme in {"http", "https", "data"} or (scheme == "about" and parts.path == "blank"):
        return None
    if not scheme:
        return "use a full address such as https://example.com"
    if mode == "chrome":
        return ("only web pages (http, https, data:, about:blank) open in your own Chrome: local files and chrome:// "
                f"pages would reach {platforms.this_computer()} and Chrome's settings (use read_file for work files)")
    path = posixpath.normpath(unquote(parts.path).replace("\\", "/"))
    if scheme == "file" and parts.netloc in {"", "localhost"} and (path == "/work" or path.startswith("/work/")):
        return None
    return "only web pages and files under file:///work/ can be opened in the sandbox"


class Browser:
    def __init__(self, cdp: CDP, work: WorkDir, cfg: Config, mode: str = "sandbox", placer=None,
                 keep_tabs: bool = False, handed=None, app_origin: str = ""):
        self.cdp = cdp
        self.work = work
        self.cfg = cfg
        # "sandbox" (Docker Chromium) or "chrome" (the user's own browser: change nothing, only our background tabs)
        self.mode = mode
        self.app_origin = app_origin  # AI Browser's own origin: never opened here (url_problem)
        self.placer = placer  # grouping.Placer in the user's own browser: it opens each new tab of ours
        self.keep_tabs = keep_tabs  # an agent of ai-browser app: its tabs outlive this process (the app closes them)
        self.handed = handed  # async () -> the tabs the user handed this agent ([{"target", "title", "url"}])
        self._handed_keys: dict[str, str] = {}  # listing key (h1...) -> target id, until taken on
        self._tab_events: list[Callable[[str, Tab], None]] = []  # ("opened" | "closed", tab)
        self.owned: dict[str, Tab] = {}
        self.current: Tab | None = None
        self._seq = 0
        # In the user's own browser a download lands in their Downloads folder: it is ⚠, and asks first
        self._risky = risky_regex(cfg.risky_words + (["download"] if mode == "chrome" else [])).pattern
        self._downloads = mode == "chrome"  # links that say they download (a[download]) are ⚠ too
        self._stopped: list[str] = []  # downloads stopped since the caller last heard (file names)
        self._cancels: set[asyncio.Future] = set()
        self._tab_listeners: list[Callable[[Tab], None]] = []
        self._allow_dialogs = False  # True only while running steps the user confirmed
        self._adopting: set[asyncio.Future] = set()
        self._opened: list[Tab] = []
        self._switches = 0  # tab switches so far: each tab's `used`
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
        cdp.on("Target.detachedFromTarget", self._on_detached)
        cdp.on("Target.attachedToTarget", self._on_frame_attached)
        cdp.on("Target.targetInfoChanged", self._on_frame_changed)
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
        if mode == "chrome":
            cdp.on("Page.downloadWillBegin", self._on_download)

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
            tab.inside.clear()  # its frames went with the old one
        elif tab and (known := tab.frames.get(frame.get("id"))) is not None:
            known.url = frame.get("url") or known.url  # a frame of the page's own process: no targetInfoChanged
            if CHECK_FRAME.search(known.url):
                tab.frames.pop(known.frame, None)  # _where refuses its rows as a bot check's

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

    # ---- downloads in the user's own browser: asked first, else cancelled ------------------

    def _on_download(self, params: dict, session: str | None) -> None:
        """A download started in one of our tabs. Outside a step the user confirmed it is cancelled at once: in the
        user's own browser it would land in their Downloads folder (Decision 15). The agent hears of it when it was
        its working tab (or a tab its step just opened)."""
        tab, _ = self._session_root(session)  # a frame's download is told on the frame's own session
        if tab is None or self._allow_dialogs or not params.get("guid"):
            return
        if tab is self.current or tab in self._opened:
            self._stopped.append(params.get("suggestedFilename") or params.get("url") or "a file")
        cancel = asyncio.ensure_future(self._cancel_download(params["guid"]))
        self._cancels.add(cancel)
        cancel.add_done_callback(self._cancels.discard)

    async def _cancel_download(self, guid: str) -> None:
        with contextlib.suppress(CDPError):
            await self.cdp.send("Browser.cancelDownload", {"guid": guid})

    def _download_notes(self) -> list[str]:
        notes = [f"⛔ a download of {name} was stopped: ask the user, then repeat with confirmed=true"
                 for name in self._stopped]
        self._stopped.clear()
        return notes

    async def start(self) -> None:
        if self.mode == "sandbox":  # the user's own browser keeps the user's Downloads folder
            await self.cdp.send("Browser.setDownloadBehavior", {
                "behavior": "allow", "downloadPath": f"{self.work.sandbox_task}/downloads", "eventsEnabled": True})
        await self.cdp.send("Target.setDiscoverTargets", {"discover": True})
        if self.mode == "sandbox":  # in the user's browser a blank tab would pop up
            await self._new_tab()

    def owned_targets(self) -> list[str]:
        """Tabs to close if this session dies: never the user's own (adopted) tabs."""
        return [tab.target for tab in self.owned.values() if not tab.adopted]

    async def close(self) -> None:
        for tab in list(self.owned.values()):
            try:
                if tab.adopted or self.keep_tabs:  # the user's tab, or the app closes ours
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
            raise BrowserError(self._no_tab())
        return await self.cdp.send(method, params, session_id=self.session_id, timeout=timeout)

    def _no_tab(self) -> str:
        return NO_TAB_CHROME if self.mode == "chrome" else "no open tab"

    def _check_url(self, url: str) -> None:
        problem = url_problem(url, self.mode, self.app_origin)
        if problem:
            raise BrowserError(f"{url}: {problem}")

    async def _new_tab(self, url: str | None = None) -> str:
        """Work in a new tab of ours, opening `url` there; returns a note. With MAX_OWN_TABS of our own already open,
        no tab opens (in the user's Brave, no window): the oldest of ours, the one switched to least recently, opens
        `url` (about:blank without one) instead, and the note says so. The user's handed tabs are never reused. When
        the oldest can't open `url`, the session goes back to the tab it was in (nothing it relies on moved) and the
        error says which tab was tried."""
        if url is not None:  # "" too: refused as open("") is
            self._check_url(url)  # before a tab exists, so a refused URL leaves nothing behind
        ours = [tab for tab in self.owned.values() if not tab.adopted]
        if len(ours) >= MAX_OWN_TABS:
            oldest = min(ours, key=lambda tab: tab.used)
            previous, used = self.current, oldest.used
            await self._switch(oldest)
            try:
                await self._navigate(url if url is not None else "about:blank")
            except BaseException as exc:
                await self._back_to(previous)
                oldest.used = used  # still the oldest
                if isinstance(exc, BrowserError):
                    raise type(exc)(TRIED.format(key=oldest.key, limit=MAX_OWN_TABS) + str(exc)) from None
                raise
            return REUSED.format(key=oldest.key, limit=MAX_OWN_TABS)
        tab = await self.open_worker(background=self.mode == "chrome")
        await self._switch(tab)
        if url is not None:
            await self._navigate(url)
        return ""

    async def _back_to(self, previous: Tab | None) -> None:
        """Work in `previous` again, the tab in use before; if it went meanwhile, the next call carries on as after
        any closed tab (ensure_tab)."""
        if previous is not None and self.owned.get(previous.key) is previous:
            self._lost = None
            await self._switch(previous)
        else:
            self.current, self._lost = None, previous.key if previous is not None else None

    async def open_worker(self, background: bool | None = None) -> Tab:
        """A new tab of ours (closed with the session) that does not become the working tab. In the user's own
        browser the placer opens it (through the app, in a window of the AI's own)."""
        if self.placer is not None:
            target = await self.placer.open_tab(self.cdp)
        else:
            params = {"url": "about:blank"}
            if self.mode == "chrome" if background is None else background:
                params["background"] = True  # don't steal the user's focus
            target = (await self.cdp.send("Target.createTarget", params))["targetId"]
        try:
            tab = await self._setup_tab(target)
        except BaseException:  # never leave a blank tab in the user's browser
            with contextlib.suppress(CDPError):
                await self.cdp.send("Target.closeTarget", {"targetId": target})
            raise
        return tab

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

    def _on_detached(self, params: dict, session: str | None) -> None:
        """Our session on a handed tab ended from outside: the user's Take back, cut at once by the app's relay. The
        next call lets go of the tab without waiting for the app's status answer."""
        tab = self._tab_for(params.get("sessionId"))
        if tab is not None and tab.handed:
            tab.detached = True
        gone = {params.get("sessionId")}
        for owned in self.owned.values():  # a frame that went (removed, or its page moved on), and the frames inside
            for frame in sorted(owned.frames.values(), key=lambda frame: frame.depth):
                if frame.session in gone or frame.host in gone:
                    gone.add(frame.session)
                    owned.frames.pop(frame.frame, None)

    # ---- frames from another site: followed with their tab, a bot check's never (the frames spec) -------------------

    def _session_root(self, session: str | None) -> tuple[Tab | None, Frame | None]:
        """(the tab, and the frame of its own process or None for the tab's page) that `session` is the session of."""
        for tab in self.owned.values():
            if tab.session == session:
                return tab, None
            for frame in tab.frames.values():
                if frame.session == session and frame.session != frame.host:
                    return tab, frame
        return None, None

    def _on_frame_attached(self, params: dict, session: str | None) -> None:
        """Chrome attached a frame of one of our tabs, or of a frame of one (auto-attach). It is followed, and read only
        once its address is known and isn't a check's."""
        info = params.get("targetInfo") or {}
        tab, parent = self._session_root(session)
        if tab is None or info.get("type") != "iframe" or not isinstance(params.get("sessionId"), str):
            return
        depth = (parent.depth if parent else 0) + 1
        frame = Frame(str(info.get("targetId")), params["sessionId"], session, depth=depth)
        tab.frames[frame.frame] = frame
        self._frame_address(tab, frame, str(info.get("url") or ""))

    def _on_frame_changed(self, params: dict, session: str | None) -> None:
        """A frame's address came or changed (Chrome tells the session it was attached under)."""
        info = params.get("targetInfo") or {}
        for tab in list(self.owned.values()):
            frame = tab.frames.get(info.get("targetId"))
            if frame is not None and frame.session != frame.host:
                self._frame_address(tab, frame, str(info.get("url") or ""))

    def _frame_address(self, tab: Tab, frame: Frame, url: str) -> None:
        """A bot check's frame is let go of at once: nothing is ever sent to it, only the let-go on its parent's
        session. Any other frame is followed: its downloads are caught as the page's are, and its own frames are
        attached too, MAX_DEPTH deep."""
        frame.url = url
        if CHECK_FRAME.search(url):
            tab.frames.pop(frame.frame, None)
            self._later("Target.detachFromTarget", {"sessionId": frame.session}, frame.host)
        elif url and not frame.followed:
            frame.followed = True
            self._later("Page.enable", {}, frame.session)  # a download it starts is told on its own session only
            if frame.depth < MAX_DEPTH:
                self._later("Target.setAutoAttach", AUTO_ATTACH, frame.session)

    def _later(self, method: str, params: dict, session: str) -> None:
        """Send a command from an event handler, without waiting for it: a frame gone meanwhile is no error."""
        async def send() -> None:
            with contextlib.suppress(CDPError):
                await self.cdp.send(method, params, session_id=session)

        job = asyncio.ensure_future(send())
        self._cancels.add(job)  # kept until done, as a download's cancel is
        job.add_done_callback(self._cancels.discard)

    async def ensure_tab(self) -> str:
        """Carry on after the tab in use was closed (in another of ours, or a new one); returns a note."""
        if self.current is not None or (self._lost is None and self.mode == "chrome"):
            return ""  # (in the user's browser a session starts without a tab of its own)
        lost, self._lost = self._lost or "in use", None
        fallback = self._fallback()
        if fallback is not None:
            await self._switch(fallback)
            return f"(tab {lost} was closed by the page or the user; now working in tab {self.current.key})\n"
        await self._new_tab()
        return f"(tab {lost} was closed by the page or the user, so a new tab {self.current.key} was opened)\n"

    def _on_target_created(self, params: dict, session: str | None) -> None:
        """Adopt tabs and popups that one of our tabs opened (target=_blank, window.open) while our own steps were
        running. Any other new tab is the user's, even when it was opened from one of our tabs. In AI
        Browser one opened from the user's (adopted) tab stays theirs too: followed, never closed. In the user's own
        browser one our steps opened from a handed tab is ours (Decision 4: popups its own steps opened), and
        closed with us: Take back gives back the handed tab, and no tab of the user's is kept beyond it."""
        info = params.get("targetInfo", {})
        opener = next((tab for tab in self.owned.values() if tab.target == info.get("openerId")), None)
        if info.get("type") != "page" or opener is None or not self._stepping:
            return
        users = opener.adopted and self.mode != "chrome"
        adoption = asyncio.ensure_future(self._adopt(info["targetId"], users=users, opener=opener.target))
        self._adopting.add(adoption)
        adoption.add_done_callback(self._adopting.discard)

    async def _adopt(self, target: str, users: bool = False, opener: str = "") -> None:
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
            send("Target.setAutoAttach", AUTO_ATTACH),  # its frames from another site, each with a session of its own
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
        """Work in one of the user's tabs: it stays theirs (released, never closed, by this session). In the user's
        own browser only a tab they handed over in Mission Control can be taken on."""
        if self.mode == "chrome" and target not in {item["target"] for item in await self._handed_now()}:
            raise BrowserError("that tab isn't a tab the user handed you: only tabs you open, and tabs the user hands "
                               "you in Mission Control (tabs list shows them as h1…), can be used")
        tab = await self._setup_tab(target, adopted=True)
        tab.handed = self.mode == "chrome"
        await self._switch(tab)
        return tab

    async def _handed_now(self) -> list[dict]:
        """The tabs the user handed this agent, as the app lists them now (none without the app)."""
        if self.handed is None:
            return []
        try:
            return [item for item in await self.handed() if isinstance(item.get("target"), str)]
        except Exception:  # the app is gone: nothing more is handed
            return []

    async def let_go_of_taken_back(self) -> str:
        """Let go of handed tabs the user took back (the Tabs page's Take back): detached, never closed. Returns the
        notes; the session carries on in its newest own tab."""
        mine = [tab for tab in self.owned.values() if tab.handed]
        if not mine:
            return ""
        still = {item["target"] for item in await self._handed_now()}
        notes = []
        for tab in mine:
            if tab.detached or tab.target not in still:
                await self.close_tab(tab)
                notes.append(f"(the user took back tab {tab.key})\n")
        if notes and self.current is None:
            self._lost = None
            fallback = self._fallback()
            if fallback is not None:
                await self._switch(fallback)
        return "".join(notes)

    async def _switch(self, tab: Tab) -> None:
        self._switches += 1
        tab.used = self._switches
        self.current = tab
        for callback in self._tab_listeners:
            callback(tab)

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
            raise BrowserError(self._no_tab())
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
                "risky": self._risky, "downloads": self._downloads, "next": self.current.next if self.current else 1}
        state = await self._reader(f"observe({json.dumps(opts)})")
        for item in state["rows"]:  # the page's own numbers win over any frame entry left with the same number
            self.current.inside.pop(item["id"], None)
        await self._read_frames(self.current, state, opts)
        signals = state.get("signals") or {}
        state["check"] = detect(state.get("url", ""), signals)
        state["boxes"] = box_frames(signals)
        boxed = {box.get("src") for box in state["boxes"]}
        for frame in state.get("frames") or []:
            if frame.get("url") in boxed or frame.get("src") in boxed:  # src: still on its first blank page, loading
                frame["box"] = True
        if find is None and self.current:
            self.current.last = state
        return state

    async def _read_frames(self, tab: Tab, page: dict, opts: dict) -> None:
        """Read the tab's frames from another site into `page`, its page's state (the frames spec, 1). Their rows follow
        the page's, numbered on from them and labelled with their frame; their frames, text, check signals and counts
        join the page's. Parents before children, MAX_FRAMES at most, in FRAME_TIME together. A frame that can't be
        read (no address yet, gone, crashed, out of time) stays "(not readable)" in the frames line."""
        loop = asyncio.get_running_loop()
        deadline, count = loop.time() + FRAME_TIME, 0
        tab.next = max(tab.next, page.get("next") or 1)
        roots = [(tab, PAGE, page)]
        for root, placed, state in roots:  # grows as frames of their own process are read
            try:
                frames = await self._frames_in(tab, root)
            except (BrowserError, CDPError):
                continue  # root went meanwhile
            for frame in frames:
                if count >= MAX_FRAMES or loop.time() >= deadline:
                    return
                count += 1
                try:
                    read = await asyncio.wait_for(self._read_frame(tab, frame, root, placed, state, page, opts),
                                                  deadline - loop.time())
                except (BrowserError, CDPError, TimeoutError):
                    # its reader may have numbered rows before the result was dropped: keep those numbers taken
                    with contextlib.suppress(BrowserError, CDPError, TimeoutError):
                        tab.next = max(tab.next, await asyncio.wait_for(self._reader_in(frame, "nextId()"),
                                                                     max(deadline - loop.time(), 0.1)))
                    continue
                if read is not None and frame.session != frame.host:
                    roots.append(read)

    async def _frames_in(self, tab: Tab, root) -> list[Frame]:
        """The frames whose <iframe> element is in the document of `root` (the tab, or a frame of its own process): the
        frames of their own process attached under its session (with an address, never a check's), then the frames of
        another origin in its process."""
        own = [frame for frame in tab.frames.values() if frame.host == root.session and frame.session != frame.host
               and frame.url and not CHECK_FRAME.search(frame.url)]
        return own + await self._same_site(tab, root)

    async def _same_site(self, tab: Tab, root) -> list[Frame]:
        """The frames of another origin on root's own site: they run in root's process, so root's session reaches them
        (Page.createIsolatedWorld with their frame id). Frames of root's own origin are left to root's reader, which
        reads them as today; frames inside these are not looked for."""
        tree = (await self.cdp.send("Page.getFrameTree", session_id=root.session))["frameTree"]
        found, todo = [], [(tree, tree["frame"].get("securityOrigin"))]
        while todo:
            node, origin = todo.pop()
            for child in node.get("childFrames") or []:
                info = child["frame"]
                url = str(info.get("url") or "")
                if url.startswith("about:") or info.get("securityOrigin") == origin:
                    todo.append((child, origin))  # root's reader reads it (about:blank has its parent's origin)
                elif not CHECK_FRAME.search(url):
                    frame = tab.frames.get(info["id"]) or Frame(info["id"], root.session, root.session,
                                                                depth=getattr(root, "depth", 0) + 1)
                    frame.url = url
                    tab.frames[frame.frame] = frame
                    found.append(frame)
        kept = {frame.frame for frame in found}
        for key, frame in list(tab.frames.items()):  # gone from root's process since the last read
            if frame.session == frame.host == root.session and key not in kept:
                del tab.frames[key]
        return found

    async def _frame_box(self, frame: Frame, root) -> dict | None:
        """Where frame's <iframe> element draws it in root's document (reader.js's frameAt, asked of root's reader with
        that element), or None when it shows nowhere."""
        return await self._on_owner(frame, root, "frameAt(this)")

    async def _on_owner(self, frame: Frame, root, call: str):
        """`window.__aib.<call>` in root's reader, with `this` the <iframe> element that draws frame in root."""
        owner = await self.cdp.send("DOM.getFrameOwner", {"frameId": frame.frame}, session_id=root.session)
        node = await self.cdp.send("DOM.resolveNode", {"backendNodeId": owner.get("backendNodeId"),
                                                       "executionContextId": await self.isolated(root)},
                                   session_id=root.session)
        handle = (node.get("object") or {}).get("objectId")
        if handle is None:
            return None
        try:
            result = await self.cdp.send("Runtime.callFunctionOn", {
                "objectId": handle, "returnByValue": True,
                "functionDeclaration": f"function () {{ return window.__aib ? window.__aib.{call} : null; }}"},
                session_id=root.session)
        finally:
            with contextlib.suppress(CDPError):
                await self.cdp.send("Runtime.releaseObject", {"objectId": handle}, session_id=root.session)
        return (result.get("result") or {}).get("value")

    async def _read_frame(self, tab: Tab, frame: Frame, root, placed: dict, state: dict, page: dict,
                          opts: dict) -> tuple | None:
        """Read one frame into `page`. Returns (frame, where it is drawn, its state), to read the frames inside it, or
        None when it shows nowhere or not in view (left for when it shows, or for a find)."""
        box = await self._frame_box(frame, root)
        if not box or box.get("slot", -1) < 0:  # not drawn, or too small to list: skipped, as today
            return None
        line = state["frames"][box["slot"]]  # its place in the frames line
        here = on_page(placed, box)
        right, bottom = placed["x"] + box["right"] * placed["sx"], placed["y"] + box["bottom"] * placed["sy"]
        if not opts.get("find") and not (right > 0 and bottom > 0 and here["x"] < page["w"] and here["y"] < page["h"]):
            line["readable"] = True  # nothing of it in view: left for when it shows, or for a find
            return None
        call = {**opts, "at": {**here, "w": page["w"], "h": page["h"], "label": line["label"]},
                "maxRows": max(0, opts["maxRows"] - len(page["rows"])),
                "textLimit": max(0, opts["textLimit"] - len(page["text"]) - 1)}
        part = await self._reader_in(frame, "observe(" + json.dumps({**call, "next": tab.next}) + ")")
        taken = {item["id"] for item in page["rows"]}
        if any(item["id"] in taken or tab.inside.get(item["id"], frame) is not frame for item in part["rows"]):
            # an earlier read of this frame was dropped after it numbered rows (its counter never learned): its
            # numbers clash with ones given since. It numbers again, once, from the page's count.
            tab.next = max(tab.next, part.get("next") or 1)
            for key in [key for key, owner in tab.inside.items() if owner is frame]:
                del tab.inside[key]
            part = await self._reader_in(frame, "observe(" + json.dumps({**call, "next": tab.next,
                                                                         "renumber": True}) + ")")
        line["readable"] = True
        tab.next = max(tab.next, part.get("next") or 1)
        for row in part["rows"]:
            tab.inside[row["id"]] = frame
        page["rows"] += part["rows"]
        page["frames"] += part["frames"]
        page["text"] = "\n".join(text for text in (page["text"], part["text"]) if text)
        page["signals"]["frames"] += part["signals"]["frames"]  # a check box inside a frame is marked too
        page["canvas"] = bool(page.get("canvas") or part.get("canvas"))
        for key in ("above", "below", "truncated"):
            page[key] += part[key]
        return frame, here, part

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
        return "\n".join(self._download_notes() + dialogs + [skipped if skipped is not None else render_page(state)])

    async def open(self, url: str, new_tab: bool = False) -> str:
        """Open `url` in the working tab, or with new_tab in another tab of ours (past MAX_OWN_TABS, the oldest)."""
        note = ""
        if new_tab or self.current is None:
            note = await self._new_tab(url)
        else:
            await self._navigate(url)
        return note + await self.observe()

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
        if name == "desktop" and self.mode == "chrome":
            await self._call("Emulation.clearDeviceMetricsOverride")  # back to the real window
        else:
            width, height, mobile = SIZES[name]
            await self._call("Emulation.setDeviceMetricsOverride",
                             {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": mobile})
        await self._settle(None)

    async def _capture(self, label: str, full_page: bool, element: str | None) -> Shot:
        metrics = await self._call("Page.getLayoutMetrics")
        if element:
            if self.current is not None and element in self.current.inside:
                raise BrowserError(f"{element} is in a frame from another site: take a screenshot of the page instead")
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
            note = await self._new_tab(url or None)  # url optional: none (or "") is a blank tab
            return note + await self.observe()
        if action == "switch" and tab and tab.startswith("h") and tab not in self._handed_keys and self.handed:
            await self._tab_list()  # h keys come from the list: read it now
        if action == "switch" and tab in self._handed_keys:  # a tab the user handed this agent: take it on
            await self.adopt(self._handed_keys.pop(tab))
            return await self.observe()
        if action in {"switch", "close"}:
            if tab not in self.owned:
                raise BrowserError(f"no tab {tab}; open tabs: "
                                   f"{', '.join([*self.owned, *self._handed_keys]) or 'none'}")
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
            handed = "  (handed by the user)" if tab.handed else ""
            lines.append(f"{mark} {key}  {json.dumps(info.get('title', ''), ensure_ascii=False)}  "
                         f"{info.get('url', '')}{handed}")
        if self.mode == "chrome" and self.handed is not None:  # tabs the user handed this agent, until taken on
            self._handed_keys = {}
            ours = {tab.target for tab in self.owned.values()}
            for item in await self._handed_now():
                info = targets.get(item["target"])
                if info is None or item["target"] in ours:
                    continue  # closed meanwhile, or already worked in
                key = f"h{len(self._handed_keys) + 1}"
                self._handed_keys[key] = item["target"]
                lines.append(f"  {key}  {json.dumps(info.get('title', ''), ensure_ascii=False)}  "
                             f"{info.get('url', '')}  (handed to you by the user)")
        return "\n".join(lines)

    # ---- acting -------------------------------------------------------------------------------

    async def act(self, steps: list[Step], confirmed: bool = False) -> str:
        waiting = self.waiting()
        if waiting is not None:  # the session is held at a bot check: no step runs
            return waiting
        if self.current is None:
            raise BrowserError(self._no_tab())
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
                    return "\n".join(lines + self._download_notes())
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
        return "\n".join(lines + self._download_notes() + [page])

    @contextlib.contextmanager
    def acting(self):
        """While our own steps work: tabs the pages open now are ours to follow and close."""
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

    def _where(self, element: str | None):
        """Where a row's element is: the frame from another site it was read in, or else the working tab. A row in a
        frame that has since become a bot check's is refused; one whose frame went is stale."""
        tab = self.current
        frame = tab.inside.get(element) if tab is not None and element else None
        if frame is None:
            return tab
        if CHECK_FRAME.search(frame.url):
            raise StepBlocked(f"{element} is in a bot check box: the user ticks it, never you")
        if tab.frames.get(frame.frame) is not frame:
            raise StepStale(f"{element} gone (its frame went); the current page is below")
        return frame

    async def _placed(self, tab: Tab, frame: Frame) -> dict | None:
        """Where `frame` is drawn on the page now ({x, y, sx, sy}), its parent frames placed first; None when it shows
        nowhere."""
        found, parent = self._session_root(frame.host)
        if found is not tab:
            return None
        placed = PAGE if parent is None else await self._placed(tab, parent)
        box = await self._frame_box(frame, parent or tab) if placed else None
        return on_page(placed, box) if box else None

    async def _frame_target(self, frame: Frame, call: str) -> dict:
        """target() in a frame's own reader, with where the frame is drawn now: its element's position is read again
        there, as a same-site frame's is. Once more when scrolling to the element moved the frame too."""
        tab = self.current
        for _ in range(2):
            placed = await self._placed(tab, frame)
            if placed is None:
                return {"ok": False, "reason": "hidden"}
            place = {**placed, "w": (tab.last or {}).get("w", 0), "h": (tab.last or {}).get("h", 0)}
            result = await self._reader_in(frame, f"{call}, {json.dumps(place)})")
            if result.get("reason") != "moved":
                return result if '"upload"' in call else await self._uncovered(tab, frame, result)  # no input lands
            await self._settle(None)  # the page scrolled too: a frame of its own process is hit where it is drawn
        return {"ok": False, "reason": "offscreen"}

    async def _uncovered(self, tab: Tab, frame: Frame, result: dict) -> dict:
        """`result` (an ok target in `frame`), unless something on the page (or in a frame above) covers the frame
        where the input would land: then the same answer as a covered element on the page."""
        if not result.get("ok"):
            return result
        x, y, f = result["x"], result["y"], frame
        while True:
            root = self._session_root(f.host)[1]
            if root is None:
                root_tab, scale = tab, None
            else:
                scale = await self._placed(tab, root)
                if scale is None:
                    return {"ok": False, "reason": "hidden"}
                root_tab = root
            rx, ry = (x, y) if scale is None else ((x - scale["x"]) / scale["sx"], (y - scale["y"]) / scale["sy"])
            by = await self._on_owner(f, root_tab, f"coveredAt(this, {rx}, {ry})")
            if by:
                return {"ok": False, "reason": "covered", "by": by}
            if root is None:
                return result
            f = root

    async def _target(self, element: str, kind: str, confirmed: bool) -> dict:
        where = self._where(element)
        call = (f"target({json.dumps(element)}, {json.dumps(kind)}, "
                f"{json.dumps(self._risky)}, {json.dumps(self._downloads)}")
        result = await (self._frame_target(where, call) if isinstance(where, Frame) else
                        self._reader_in(where, call + ")"))
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
            await self._reader_in(self._where(element), f"settle({json.dumps(element)})", await_promise=True,
                                  timeout=5)
        except (BrowserError, CDPError):
            pass  # the page (or the frame) is navigating away; _finish_navigation handles it

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
        if step.target:  # in its own frame, if it is in one: scrolled there, never guessed with the wheel
            if not await self._reader_in(self._where(step.target), f"scrollIntoView({json.dumps(step.target)})"):
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
        if self.mode == "chrome":  # Chrome reads it from this Mac later: a copy the sandbox cannot swap
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
                if op == "type":  # focused in its own frame: the typing below follows the focus there
                    await self._reader_in(self._where(element), f"selectContents({json.dumps(element)})")
                elif await self._reader_in(self._where(element), f"caretEnd({json.dumps(element)})") == "end-key":
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
            result = await self._reader_in(self._where(element),
                                           f"selectOption({json.dumps(element)}, {json.dumps(step.value)})")
            if not result.get("ok"):
                options = ", ".join(result.get("options") or [])
                raise BrowserError(result.get("reason", "cannot select") + (f"; options: {options}" if options else ""))
            await self._settle(element)
        elif op in {"check", "uncheck"}:
            target = await self._target(element, "click", confirmed)  # identity first, then state
            row = await self._reader_in(self._where(element), f"state({json.dumps(element)})")
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
            where = self._where(element)
            node = await self._evaluate(where, {"expression": f"window.__aib.node({json.dumps(element)})"})
            object_id = node.get("result", {}).get("objectId")
            if not object_id:
                raise StepStale(f"{element} gone; the current page is below")
            await self.cdp.send("DOM.setFileInputFiles", {"files": [path], "objectId": object_id},
                                session_id=where.session)
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
