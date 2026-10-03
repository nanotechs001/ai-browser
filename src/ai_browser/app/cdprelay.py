"""One connection to the user's browser for everyone: the app's relay (the cdp-relay spec).

With its remote-debugging switch on, Brave asks "Allow remote debugging?" for every connection and remembers nothing,
and it shows its "controlled by automated test software" bar again whenever a connection opens or closes. So the app
holds the only connection (the upstream) for its whole run, and every agent's engine, every Claude Code session while
the app runs, and the app's own tab list talk to the browser through it: plain CDP over ws://127.0.0.1:<port>/cdp.

The relay remaps message ids per client, routes flattened sessions to the client that attached, and decides which tabs
each client may see and drive (its own, their popups, tabs the user handed it) and which commands pass. It opens the
upstream only right after something the user did, and everyone waiting shares that one question. It never answers,
clicks, hides or suppresses the browser's question or its bar: it only makes fewer connections."""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import ipaddress
import itertools
import json
import logging
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from starlette.responses import PlainTextResponse
from starlette.websockets import WebSocket
from websockets.asyncio.client import connect

from ..cdp import CDP, CDPError
from ..chrome import ChromeError, browser_name, find_ws_url, inspect_address, switch_on

log = logging.getLogger(__name__)

ALLOW_WAIT = 60  # seconds Brave's "Allow remote debugging?" may stay open
SWITCH_EVERY = 2.0  # seconds between two looks at the switch while not connected
BIND_WAIT = 2.0  # seconds a new session's first events wait for its attach answer
BIND_BUFFER = 256  # ...at most this many of them per session
QUEUE_BYTES = 64 * 1024 * 1024  # what one client may have waiting before it counts as too slow
QUEUE_MESSAGES = 10_000
TOKEN_HEADER = "x-aib-agent-token"
APP = "app"  # the app's own client
NOT_CDP, CUT_OFF, TOO_SLOW, GONE, QUITTING = 4400, 4401, 4408, 4410, 1001

BROWSER_COMMANDS = frozenset({
    "Target.setDiscoverTargets", "Target.createTarget", "Target.attachToTarget", "Target.detachFromTarget",
    "Target.closeTarget", "Target.activateTarget", "Target.getTargets", "Target.getTargetInfo", "Browser.getVersion",
    "Browser.cancelDownload", "Browser.getWindowForTarget"})
APP_COMMANDS = frozenset({"Target.getBrowserContexts"})  # the app's client's one extra read (wave 1B's profiles)
SESSION_DOMAINS = frozenset({"Runtime", "DOM", "Input", "IO", "Log"})  # they act only inside that page
SESSION_METHODS = frozenset({
    "Page.enable", "Page.setLifecycleEventsEnabled", "Page.addScriptToEvaluateOnNewDocument", "Page.getFrameTree",
    "Page.navigate", "Page.getNavigationHistory", "Page.navigateToHistoryEntry", "Page.reload",
    "Page.createIsolatedWorld", "Page.getLayoutMetrics", "Page.captureScreenshot", "Page.handleJavaScriptDialog",
    "Page.startScreencast", "Page.stopScreencast", "Page.screencastFrameAck", "Network.enable",
    "Network.loadNetworkResource", "Emulation.setFocusEmulationEnabled", "Emulation.setDeviceMetricsOverride",
    "Emulation.clearDeviceMetricsOverride"})
WEB_ONLY = "only web pages (http, https, data:, about:blank) open through AI Browser's connection"
APP_PAGE = "AI Browser's own pages don't open in your browser through its connection"
UNREADABLE = "not an address the browser could read"


def allowed(method, level: str, app: bool = False) -> bool:
    """Whether `method` may pass: at "browser" level (no session) the short list, at "session" level the page's own
    domains and listed methods (Decision 7). `app` adds the app's own client's extra read."""
    if not isinstance(method, str) or "." not in method:
        return False
    if level == "browser":
        return method in BROWSER_COMMANDS or (app and method in APP_COMMANDS)
    return method in SESSION_METHODS or method.split(".", 1)[0] in SESSION_DOMAINS


def address_problem(url, app_port: int) -> str | None:
    """Why the relay won't open `url` (Target.createTarget, Page.navigate, Network.loadNetworkResource), or None: web
    pages, data: and about:blank only, and never the app's own origin, however the host is spelled (read as Chrome
    reads it)."""
    if not isinstance(url, str):
        return WEB_ONLY
    text = url.strip("\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17"
                     "\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f ")
    scheme = text.split(":", 1)[0].lower() if ":" in text else ""
    if scheme == "about":
        rest = text.split(":", 1)[1].split("#", 1)[0]
        return None if rest.lower() == "blank" else WEB_ONLY
    if scheme == "data":
        return None
    if scheme not in ("http", "https"):
        return WEB_ONLY
    text = text.replace("\\", "/")  # Chrome reads a backslash as a slash in web addresses
    try:
        parts = urlsplit(text)
        host, port = parts.hostname, parts.port
    except ValueError:
        return UNREADABLE
    if not host:
        return UNREADABLE
    host = unquote(host).lower()
    if (port if port is not None else 443 if scheme == "https" else 80) != app_port:
        return None
    if not _plain(host):
        return UNREADABLE  # on the app's port only a host Chrome reads as written: never one it maps (IDNA)
    try:
        return APP_PAGE if _loopback(host) else None
    except ValueError:
        return UNREADABLE  # Chrome wouldn't read it either: refused, never guessed


_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?")


def _plain(host: str) -> bool:
    """A host Chrome reads as written: ASCII labels of letters, digits and hyphens (one trailing dot at most), or an
    IPv6 literal. Chrome maps anything else through IDNA first (full-width dots, soft hyphens, zero-width characters
    can all become 127.0.0.1 or localhost), so it is refused rather than mapped here and maybe mapped differently."""
    if not host.isascii():
        return False
    if ":" in host:
        return True  # IPv6 (urlsplit took the brackets off): _loopback reads it
    name = host[:-1] if host.endswith(".") else host
    return bool(name) and all(_LABEL.fullmatch(label) for label in name.split("."))


def _loopback(host: str) -> bool:
    """Whether `host` names this computer: localhost and *.localhost, 127.0.0.0/8 in any IPv4 form Chrome reads,
    0.0.0.0, ::1, :: and IPv4 addresses inside IPv6. ValueError for a numeric host Chrome would refuse."""
    if host.endswith("."):
        host = host[:-1]
    if host == "localhost" or host.endswith(".localhost"):
        return True
    if ":" in host:  # IPv6 (urlsplit took the brackets off)
        address = ipaddress.IPv6Address(host.split("%", 1)[0])
        inner = address.ipv4_mapped or (ipaddress.IPv4Address(address.packed[12:])
                                        if address.packed[:12] == bytes(12) else None)
        return address.is_loopback or address.is_unspecified or (
            inner is not None and (inner.is_loopback or inner.is_unspecified))
    v4 = _ipv4(host)
    return v4 is not None and (v4.is_loopback or v4.is_unspecified)


def _ipv4(host: str) -> ipaddress.IPv4Address | None:
    """`host` as Chrome reads an IPv4 address (one to four parts, each decimal, octal or hex), None for a name, or
    ValueError for a number Chrome refuses."""
    parts = host.split(".")
    if not re.fullmatch(r"[0-9]+|0[xX][0-9a-fA-F]*", parts[-1]):
        return None  # ends in a name, not a number: a domain
    if len(parts) > 4:
        raise ValueError(host)
    numbers = [_number(part) for part in parts]
    if any(number > 255 for number in numbers[:-1]) or numbers[-1] >= 256 ** (5 - len(numbers)):
        raise ValueError(host)
    value = numbers[-1]
    for index, number in enumerate(numbers[:-1]):
        value += number << (8 * (3 - index))
    return ipaddress.IPv4Address(value)


def _number(part: str) -> int:
    if re.fullmatch(r"0[xX][0-9a-fA-F]*", part):
        return int(part[2:] or "0", 16)
    if re.fullmatch(r"0[0-7]+", part):
        return int(part[1:], 8)
    if re.fullmatch(r"0|[1-9][0-9]*", part):
        return int(part)
    raise ValueError(part)  # "08", "", "1x": Chrome refuses the whole address


class Tokens:
    """Who a client is: a token per agent (minted when it is created) and per Claude Code session (from /agent-hello).
    In memory only, new every app run. A revoked token is remembered as gone, so its engine hears "disconnected"."""

    def __init__(self) -> None:
        self._live: dict[str, str] = {}
        self._gone: dict[str, str] = {}

    def mint(self, identity: str) -> str:
        if identity not in self._live:
            self._live[identity] = secrets.token_urlsafe(24)
            self._gone.pop(identity, None)
        return self._live[identity]

    def check(self, identity: str, given) -> bool:
        wanted = self._live.get(identity)
        return wanted is not None and _same(given, wanted)

    def who(self, given) -> str | None:
        return _find(self._live, given)

    def gone(self, given) -> str | None:
        return _find(self._gone, given)

    def revoke(self, identity: str) -> None:
        token = self._live.pop(identity, None)
        if token is not None:
            self._gone[identity] = token


def _same(given, wanted: str) -> bool:
    return isinstance(given, str) and bool(given) and hmac.compare_digest(given.encode("utf-8", "replace"),
                                                                          wanted.encode())


def _find(table: dict[str, str], given) -> str | None:
    found = None
    for identity, token in list(table.items()):  # every one compared, in constant time each
        if _same(given, token):
            found = identity
    return found


TARGET_EVENTS = frozenset({"Target.targetCreated", "Target.targetInfoChanged", "Target.targetDestroyed",
                           "Target.targetCrashed"})
NOT_FOUND = (-32602, "No target with given id found")
NO_SESSION = (-32001, "Session with given id not found.")
HANDED_CLOSE = (-32000, "a tab the user handed over can be let go of, never closed")
LOST = (-32000, "browser connection lost")
NO_DOWNLOAD = (-32602, "No download with given guid found")
NO_CONTEXT = (-32602, "Failed to find browser context with given id")
SPECIAL_TAB = (-32000, "hidden, focused or special tabs don't open through AI Browser's connection")
NOT_FLAT = (-32000, "AI Browser's connection needs flatten: true")
CREATE_PARAMS = frozenset({"url", "newWindow", "background", "browserContextId"})  # what an engine sends
CUT_OFF_TEXT = "The user disconnected this client in AI Home."
_SESSION_ID = re.compile(r"^cc-[0-9a-z-]{1,40}$")
_AGENT_ID = re.compile(r"^a[0-9]{1,9}$")
_HANDSHAKE_NOISE = "ASGI callable returned without completing handshake."


class _DenialNoise(logging.Filter):
    """uvicorn's sans-I/O websockets log an error after every refusal sent before the upgrade, though the refusal (a
    403, 409 or 410 with its reason) reached the client as meant: that one line is left out."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage() != _HANDSHAKE_NOISE


def _quiet_denials() -> None:
    logger = logging.getLogger("uvicorn.error")
    if not any(isinstance(item, _DenialNoise) for item in logger.filters):
        logger.addFilter(_DenialNoise())


def _target_info(info) -> bool:
    return isinstance(info, dict) and isinstance(info.get("targetId"), str)


def _command_of(text) -> dict | None:
    """A CDP command from a client, or None for anything else (a binary frame, broken JSON, a wrong shape)."""
    if not isinstance(text, str):
        return None
    try:
        message = json.loads(text)
    except ValueError:
        return None
    if not isinstance(message, dict) or type(message.get("id")) is not int \
            or not isinstance(message.get("method"), str):
        return None
    if not isinstance(message.get("params", {}), dict) or not isinstance(message.get("sessionId", ""), str):
        return None
    return message


def _order(identity: str) -> tuple:
    return (0, int(identity[1:]), "") if _AGENT_ID.match(identity) else (1, 0, identity)


async def _shut(ws, code: int) -> None:
    with contextlib.suppress(Exception):
        await ws.close(code)


@dataclass
class _Session:
    client: object | None  # the client that attached; None once it left (its events are dropped)
    target: str
    cut: bool = False  # Take back: refused at once, until the browser's detach note drops it


class _Socket:
    """One engine on /cdp (an agent's or a Claude Code session's), with its bounded outbound queue."""

    app = False

    def __init__(self, identity: str, ws: WebSocket):
        self.identity, self.ws = identity, ws
        self.discover = self.closed = self.ending = False
        self.sessions: set[str] = set()
        self.downloads: set[str] = set()
        self.announced: set[str] = set()
        self.queue: asyncio.Queue = asyncio.Queue()
        self.size = 0
        self.writer: asyncio.Task | None = None

    def deliver(self, message: dict, raw: str | None = None) -> bool:
        """Queue one message; False when the queue is full (the client reads too slowly)."""
        if self.closed:
            return True
        text = raw if raw is not None else json.dumps(message)
        if self.size + len(text) > QUEUE_BYTES or self.queue.qsize() >= QUEUE_MESSAGES:
            return False
        self.size += len(text)
        self.queue.put_nowait(text)
        return True

    def end(self, code: int) -> None:
        """Close once what is queued is sent (the detach notes before 4410)."""
        self.closed = self.ending = True
        self.queue.put_nowait(code)

    async def write(self) -> None:
        with contextlib.suppress(Exception):
            while True:
                item = await self.queue.get()
                if isinstance(item, int):
                    await self.ws.close(item)
                    return
                self.size -= len(item)
                await self.ws.send_text(item)


class LocalClient(CDP):
    """The app's own client, in-process (Decision 9): the cdp.CDP surface TabWatch uses, with the app's rights. It sees
    every target, may attach to and activate any, and may close only a tab an agent or a session owns."""

    app = True
    identity = APP

    def __init__(self, relay: "Relay"):  # no websocket and no reader: the relay hands it its messages
        self._relay = relay
        self._ids = itertools.count(1)
        self._pending: dict[int, tuple[asyncio.Future, str]] = {}
        self._handlers: dict[str, list] = {}
        self._closed = False
        self.discover = False
        self.sessions: set[str] = set()
        self.downloads: set[str] = set()
        self.announced: set[str] = set()

    async def send(self, method: str, params: dict | None = None, session_id: str | None = None,
                   timeout: float = 30) -> dict:
        if self._closed:
            raise CDPError("connection closed", method=method)
        message_id = next(self._ids)
        message = {"id": message_id, "method": method, "params": params or {}}
        if session_id:
            message["sessionId"] = session_id
        future = asyncio.get_running_loop().create_future()
        self._pending[message_id] = (future, method)
        try:
            await self._relay._command(self, message)
            return await asyncio.wait_for(future, timeout)
        except TimeoutError:
            raise CDPError(f"{method} timed out after {timeout:g}s", code=-1, method=method) from None
        finally:
            self._pending.pop(message_id, None)

    def deliver(self, message: dict, raw: str | None = None) -> bool:
        if not self._closed:
            self._dispatch(message)
        return True

    def end(self, code: int) -> None:
        self._closed = True
        self._fail_pending()

    async def close(self) -> None:
        if not self._closed:
            self.end(1000)
            self._relay._left(self)


class Relay:
    """The one upstream connection to the browser of `folder`, and everyone's way to it (see the module's docstring).
    One per browser folder, so a later wave can hold one per browser."""

    def __init__(self, folder: Path, tokens: Tokens, allow_wait: float = ALLOW_WAIT, every: float = SWITCH_EVERY):
        self.folder = Path(folder)
        self.name = browser_name(self.folder)
        self.tokens = tokens
        self.allow_wait, self.every = allow_wait, every
        self.state = "off"  # off · ready · asking · connected · refused · lost
        self.port = 0  # the app's port, set by the server once it listens: the Host check and the address check
        self.upstream_opens = 0  # handshakes started to the browser: each one is a question the user is asked
        self.handed: Callable[[str], set[str]] = lambda identity: set()  # set by the server: agent.adopted, live
        self.may_open: Callable[[str], bool] = lambda identity: bool(_SESSION_ID.match(identity))  # by the server
        self._ws = None
        self._reader: asyncio.Task | None = None
        self._ids = itertools.count(1)
        self._lock = asyncio.Lock()
        self._attempt: asyncio.Future | None = None
        self._poll: asyncio.Task | None = None
        self._quitting = False
        self._clients: list = []  # _Socket and LocalClient, in the order they came
        self._targets: dict[str, dict] = {}  # target id -> its latest targetInfo
        self._grants: dict[str, tuple[str, str]] = {}  # target id -> (identity, "own" | "popup")
        self._sessions: dict[str, _Session] = {}
        self._pending: dict[int, tuple] = {}  # upstream id -> (client | None, client id, method, params, session)
        self._waiting: dict[int, asyncio.Future] = {}  # upstream id -> the relay's own command's future
        self._unbound: dict[str, list] = {}  # session id -> [(message, raw)] that came before its attach answer
        self._cut_off: set[str] = set()
        self._forgotten: set[str] = set()  # closed agents and ended sessions, until they connect again
        self._states: list[Callable[[str], None]] = []
        self._changes: list[Callable[[], None]] = []
        self._grant_hooks: list[Callable[[str, str], None]] = []
        self._jobs: set[asyncio.Task] = set()
        _quiet_denials()

    # ---- hooks and state -----------------------------------------------------------------------------------

    def on_state(self, callback: Callable[[str], None]) -> None:
        self._states.append(callback)

    def on_change(self, callback: Callable[[], None]) -> None:
        """callback() when the list of clients (AI Home's rows) may have changed."""
        self._changes.append(callback)

    def on_grant(self, callback: Callable[[str, str], None]) -> None:
        """callback(identity, target) when a tab becomes a client's own (the server's owner chip)."""
        self._grant_hooks.append(callback)

    def _set(self, state: str) -> None:
        if state == self.state:
            return
        self.state = state
        for callback in list(self._states):
            with contextlib.suppress(Exception):
                callback(state)
        self._changed()

    def _changed(self) -> None:
        for callback in list(self._changes):
            with contextlib.suppress(Exception):
                callback()

    def _job(self, coroutine) -> None:
        task = asyncio.ensure_future(coroutine)
        self._jobs.add(task)
        task.add_done_callback(self._jobs.discard)

    # ---- the switch, and opening the upstream (Decision 10) ------------------------------------------------

    async def start(self) -> None:
        """Look at the switch now, then every few seconds: a TCP check only, so the browser never asks anything."""
        await self._look()
        self._poll = asyncio.create_task(self._watch_switch())

    async def _look(self) -> None:
        if self.state not in ("off", "ready"):
            return  # asking, connected, refused and lost change only by what happens to the connection
        on = await asyncio.to_thread(switch_on, self.folder)
        if on and self.state == "off":
            self._set("ready")
        elif not on and self.state == "ready":
            self._set("off")

    async def _watch_switch(self) -> None:
        while True:
            await asyncio.sleep(self.every)
            with contextlib.suppress(Exception):
                await self._look()

    def _decide(self, why: str, identity: str = "") -> str:
        """Decision 10's table: "accept" (connected), "join" (the attempt under way), "open" (the one place a question
        can start) or "no"."""
        if self._quitting or (identity and identity in self._cut_off):
            return "no"
        if self.state == "connected":
            return "accept"
        if self.state == "asking":
            return "join"
        if self.state == "off":
            return "no"
        if why == "start":
            return "open" if self.state == "ready" else "no"
        if why in ("connect", "turn"):
            return "open"
        if why == "client" and self.state in ("ready", "lost") and self.may_open(identity):
            return "open"
        return "no"

    async def open(self, why: str, identity: str = "") -> bool:
        """Whether the upstream is up after this call. It opens only where Decision 10's table says so, and everyone
        waiting shares the one attempt, so the user sees one question."""
        decision = self._decide(why, identity)
        if decision == "accept":
            return True
        if decision == "no":
            return False
        if decision == "open" and (self._attempt is None or self._attempt.done()):
            self._attempt = asyncio.ensure_future(self._connect())
        attempt = self._attempt
        if attempt is None:
            return False
        try:
            opened = await asyncio.shield(attempt)
        except asyncio.CancelledError:
            if attempt.cancelled():  # the app is quitting
                return False
            raise
        return opened and identity not in self._cut_off

    async def _connect(self) -> bool:
        try:
            ws_url = await asyncio.to_thread(find_ws_url, self.folder)
        except ChromeError:
            self._set("off")
            return False
        self._set("asking")
        self.upstream_opens += 1
        try:
            ws = await connect(ws_url, max_size=None, ping_interval=None, open_timeout=self.allow_wait, proxy=None)
        except Exception:  # Deny, a refused handshake, or no answer in time: never retried by itself
            self._set("refused")
            return False
        if self._quitting:
            with contextlib.suppress(Exception):
                await ws.close()
            return False
        self._ws = ws
        self._reader = asyncio.create_task(self._read(ws))
        try:
            await self._call("Target.setDiscoverTargets", {"discover": True})  # for everyone, once
            infos = (await self._call("Target.getTargets")).get("targetInfos") or []
        except CDPError:
            await self._close_upstream()
            self._set("lost")
            return False
        self._targets.update({info["targetId"]: dict(info) for info in infos if _target_info(info)})
        for target in [target for target in self._grants if target not in self._targets]:
            del self._grants[target]  # tabs that didn't come back
        self._set("connected")
        return True

    async def _close_upstream(self) -> None:
        ws, self._ws = self._ws, None
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.close()
        if self._reader is not None:
            self._reader.cancel()
            self._reader = None

    async def _call(self, method: str, params: dict | None = None, timeout: float = 10) -> dict:
        """A command of the relay's own (discovery, Take back's detach, closing a session's tabs)."""
        upstream_id = next(self._ids)
        future = asyncio.get_running_loop().create_future()
        self._waiting[upstream_id] = future
        self._pending[upstream_id] = (None, None, method, params or {}, None)
        try:
            await self._up({"id": upstream_id, "method": method, "params": params or {}})
            return await asyncio.wait_for(future, timeout)
        except TimeoutError:
            raise CDPError(f"{method} timed out after {timeout:g}s", -1, method) from None
        finally:
            self._waiting.pop(upstream_id, None)
            self._pending.pop(upstream_id, None)

    async def _quietly(self, method: str, params: dict) -> None:
        with contextlib.suppress(Exception):
            await self._call(method, params)

    async def _up(self, message: dict, still: Callable[[], bool] | None = None) -> bool:
        """Send one message to the browser, in turn; with `still`, only if it is still wanted once its turn comes."""
        ws = self._ws
        if ws is None:
            raise CDPError(LOST[1], LOST[0], message.get("method", ""))
        async with self._lock:
            if still is not None and not still():
                return False  # cut, disconnected or gone while it waited: never sent
            try:
                await ws.send(json.dumps(message))
            except Exception:
                raise CDPError(LOST[1], LOST[0], message.get("method", "")) from None
        return True

    # ---- the /cdp route (Decision 8) -----------------------------------------------------------------------

    async def serve(self, ws: WebSocket) -> None:
        """The checks, and the wait for the browser, happen before the upgrade, so a refusal reaches the client as an
        HTTP answer with its reason. After the upgrade: plain CDP both ways."""
        status, text, identity = self._check(ws)
        if status == 0 and not await self.open("client", identity):
            status, text = (410, CUT_OFF_TEXT) if identity in self._cut_off else (409, self._closed_text())
        if status:
            with contextlib.suppress(Exception):
                await ws.send_denial_response(PlainTextResponse(text, status_code=status))
            return
        try:
            await ws.accept()
        except Exception:
            return  # it gave up while the browser was asking
        client = _Socket(identity, ws)
        self._forgotten.discard(identity)  # a session that said bye and came back is itself again
        self._clients.append(client)
        client.writer = asyncio.ensure_future(client.write())
        self._changed()
        try:
            await self._listen(client)
        finally:
            self._left(client)
            if client.writer is not None and not client.writer.done():
                if client.ending:  # a close code is queued: let it go out
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(asyncio.shield(client.writer), 5)
                client.writer.cancel()

    def _check(self, ws: WebSocket) -> tuple[int, str, str]:
        """(0, "", identity) when the handshake may go on to the browser, else (status, why, "")."""
        if "origin" in ws.headers or ws.headers.get("host", "") != f"127.0.0.1:{self.port}":
            return 403, "refused", ""  # a web page, or a name that isn't this computer (DNS rebinding)
        given = ws.headers.get(TOKEN_HEADER, "")
        identity = self.tokens.who(given)
        if identity is None:
            return (410, CUT_OFF_TEXT, "") if self.tokens.gone(given) else (403, "refused", "")
        if identity in self._cut_off:
            return 410, CUT_OFF_TEXT, ""
        if self._quitting:
            return 409, "AI Browser is quitting", ""
        return 0, "", identity

    def _closed_text(self) -> str:
        """Why a client may not have the browser now: the 409's body."""
        if self._quitting:
            return "AI Browser is quitting"
        if self.state == "off":
            return (f"{self.name}'s remote-debugging switch is off: the user turns it on at "
                    f"{inspect_address(self.folder)}")
        if self.state == "refused":
            return f"{self.name} said no to AI Browser's connection: ask the user to click Try again in AI Home"
        return f"AI Browser isn't connected to {self.name}: ask the user to click Connect in AI Home"

    async def _listen(self, client: _Socket) -> None:
        while True:
            try:
                message = await client.ws.receive()
            except Exception:
                return
            if message.get("type") == "websocket.disconnect":
                return
            if client.closed:
                continue  # cut off or closing: the rest is ignored until the socket closes
            command = _command_of(message.get("text"))
            if command is None:
                log.info("relay: %s sent a message that isn't CDP, so its connection was closed", client.identity)
                self._release(client)
                self._end(client, NOT_CDP)
                self._changed()
                continue
            await self._command(client, command)

    # ---- clients' commands (Decisions 3, 5 and 7) ----------------------------------------------------------

    async def _command(self, client, message: dict) -> None:
        client_id, method = message["id"], message["method"]
        params = message.get("params") or {}
        session_id = message.get("sessionId") or None
        if session_id is not None:
            session = self._sessions.get(session_id)
            if session is None or session.client is not client or session.cut:
                return self._error(client, client_id, NO_SESSION, session_id)
            if not allowed(method, "session", client.app):
                return self._refuse(client, client_id, method, session_id)
            if method in ("Page.navigate", "Network.loadNetworkResource"):
                problem = address_problem(params.get("url"), self.port)
                if problem:
                    return self._error(client, client_id, (-32000, problem), session_id)
            return await self._forward(client, client_id, method, params, session_id)
        if not allowed(method, "browser", client.app):
            return self._refuse(client, client_id, method)
        if method == "Target.setDiscoverTargets":
            return self._discovery(client, client_id, params.get("discover") is True)
        problem = self._target_problem(client, method, params)
        if problem is not None:
            return self._error(client, client_id, problem)
        if method == "Target.createTarget":
            params = {**params, "background": True}  # no AI tab takes the user's focus
        await self._forward(client, client_id, method, params)

    def _target_problem(self, client, method: str, params: dict) -> tuple[int, str] | None:
        identity, target = client.identity, params.get("targetId")
        if method == "Target.createTarget":
            problem = address_problem(params.get("url"), self.port)
            if problem:
                return -32000, problem
            if set(params) - CREATE_PARAMS:  # hidden, focused, minimized, off-screen or special: never
                return SPECIAL_TAB
            context = params.get("browserContextId")
            if context is not None and context not in self._contexts_of(identity):
                return NO_CONTEXT  # never a private window or another profile it learned of
            return None
        if method == "Target.attachToTarget":
            if params.get("flatten") is not True:
                return NOT_FLAT
            return None if self.visible(identity, target) else NOT_FOUND
        if method == "Target.detachFromTarget":
            session = self._sessions.get(params.get("sessionId"))
            return None if session is not None and session.client is client else NO_SESSION
        if method == "Target.closeTarget":
            if client.app:  # closing an agent's tabs, Skip this site: only a tab someone owns here
                return None if isinstance(target, str) and target in self._grants else NOT_FOUND
            if isinstance(target, str) and target in self.handed(identity):
                return HANDED_CLOSE
            return None if self.grants(identity, target) else NOT_FOUND
        if method in ("Target.activateTarget", "Browser.getWindowForTarget"):
            mine = self.grants(identity, target) or (isinstance(target, str) and target in self.handed(identity))
            return None if client.app or mine else NOT_FOUND
        if method == "Target.getTargetInfo":
            return None if self.visible(identity, target) else NOT_FOUND
        if method == "Browser.cancelDownload":
            return None if params.get("guid") in client.downloads else NO_DOWNLOAD
        return None  # Target.getTargets (filtered on its way back), Browser.getVersion, the app's extra read

    def _discovery(self, client, client_id, on: bool) -> None:
        """Discovery is per client: the browser's is on from the start; a client gets a targetCreated for each target
        it may see, then its answer."""
        client.discover = on
        if on:
            for target, info in list(self._targets.items()):
                self._announce(client, target, info)
        else:
            client.announced.clear()
        self._answer_to(client, client_id, {})

    def _announce(self, client, target: str, info: dict) -> None:
        if client.discover and target not in client.announced and self.visible(client.identity, target):
            client.announced.add(target)
            self._to(client, {"method": "Target.targetCreated", "params": {"targetInfo": dict(info)}})

    async def _forward(self, client, client_id, method: str, params: dict, session_id: str | None = None) -> None:
        upstream_id = next(self._ids)
        self._pending[upstream_id] = (client, client_id, method, params, session_id)
        message = {"id": upstream_id, "method": method, "params": params}
        if session_id is not None:
            message["sessionId"] = session_id

        def still() -> bool:  # Take back, Disconnect or a closed socket while it waited its turn: dropped
            if upstream_id not in self._pending or client.closed:
                return False
            session = self._sessions.get(session_id) if session_id is not None else None
            return session_id is None or (session is not None and session.client is client and not session.cut)

        try:
            sent, why = await self._up(message, still), NO_SESSION
        except CDPError:
            sent, why = False, LOST
        if not sent and self._pending.pop(upstream_id, None) is not None:
            self._error(client, client_id, why, session_id)

    def _answer_to(self, client, client_id, result: dict, session_id: str | None = None) -> None:
        reply = {"id": client_id, "result": result}
        if session_id is not None:
            reply["sessionId"] = session_id
        self._to(client, reply)

    def _error(self, client, client_id, error: tuple[int, str], session_id: str | None = None) -> None:
        reply = {"id": client_id, "error": {"code": error[0], "message": error[1]}}
        if session_id is not None:
            reply["sessionId"] = session_id
        self._to(client, reply)

    def _refuse(self, client, client_id, method: str, session_id: str | None = None) -> None:
        name = method[:100]
        log.info("relay: %s isn't allowed for %s", name, client.identity)  # the method and who, never params
        self._error(client, client_id, (-32601, f"{name} isn't allowed through AI Browser's connection"), session_id)

    def _to(self, client, message: dict, raw: str | None = None) -> None:
        if not client.closed and not client.deliver(message, raw):
            self._too_slow(client)

    def _too_slow(self, client) -> None:
        """Decision 12: a client that doesn't read is cut, never the browser link."""
        log.info("relay: %s read too slowly, so its connection was closed", client.identity)
        self._release(client)
        self._end(client, TOO_SLOW, at_once=True)
        self._changed()

    # ---- the browser's messages ----------------------------------------------------------------------------

    async def _read(self, ws) -> None:
        try:
            async for raw in ws:
                try:
                    message = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(message, dict):
                    try:
                        self._from_browser(message, raw if isinstance(raw, str) else None)
                    except Exception:  # one odd message must not stop everyone (its text is never logged)
                        log.exception("relay: a message from the browser could not be routed")
        except Exception:
            pass
        finally:
            if self._ws is ws:
                self._lost()

    def _from_browser(self, message: dict, raw: str | None) -> None:
        if "id" in message:
            self._answer(message)
            return
        method = message.get("method")
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        session_id = message.get("sessionId")
        if isinstance(session_id, str) and session_id:
            self._session_event(session_id, method, params, message, raw)
        elif method in ("Target.attachedToTarget", "Target.detachedFromTarget"):
            self._attach_event(method, params, message, raw)
        elif method in TARGET_EVENTS:
            self._target_event(method, params, message, raw)
        elif method == "Inspector.detached":
            for client in list(self._clients):
                self._to(client, message, raw)
        else:
            app = self._app_client()
            if app is not None:
                self._to(app, message, raw)

    def _answer(self, message: dict) -> None:
        upstream_id = message.get("id")
        entry = self._pending.pop(upstream_id, None) if isinstance(upstream_id, int) else None
        if entry is None:
            return
        client, client_id, method, params, session_id = entry
        future = self._waiting.pop(upstream_id, None)
        error = message.get("error")
        result = message.get("result") if isinstance(message.get("result"), dict) else {}
        if client is None:  # the relay's own
            if future is not None and not future.done():
                if error is not None:
                    text = error.get("message") if isinstance(error, dict) else error
                    code = error.get("code", 0) if isinstance(error, dict) else 0
                    future.set_exception(CDPError(f"{method}: {text}", code, method))
                else:
                    future.set_result(result)
            return
        if error is not None:
            reply = {"id": client_id, "error": error}
        else:
            result = self._after(client, client_id, method, params, result)
            if result is None:
                return
            reply = {"id": client_id, "result": result}
        if session_id is not None:
            reply["sessionId"] = session_id
        self._to(client, reply)

    def _after(self, client, client_id, method: str, params: dict, result: dict) -> dict | None:
        """An answer's effects before it goes back: a new tab becomes its creator's (and is announced to it first), an
        attach binds the session (its early events go first), a target list keeps what the client may see."""
        if method == "Target.createTarget" and isinstance(result.get("targetId"), str):
            target = result["targetId"]
            if client.identity in self._forgotten:  # its agent closed while the tab was being made: nobody's
                self._job(self._quietly("Target.closeTarget", {"targetId": target}))
                return result
            if not client.app:
                self._grant(client.identity, target, "own")
            info = self._targets.get(target)
            if info is not None:
                self._announce(client, target, info)
        elif method == "Target.attachToTarget" and isinstance(result.get("sessionId"), str):
            session_id, target = result["sessionId"], params.get("targetId")
            queued = self._unbound.pop(session_id, [])
            if client.closed:  # it left meanwhile: nobody will use this session
                self._job(self._quietly("Target.detachFromTarget", {"sessionId": session_id}))
                return None
            if not client.app and not self.visible(client.identity, target):  # taken back while it attached
                self._job(self._quietly("Target.detachFromTarget", {"sessionId": session_id}))
                self._error(client, client_id, NOT_FOUND)
                return None
            self._sessions[session_id] = _Session(client, str(target))
            client.sessions.add(session_id)
            if not client.app and isinstance(target, str):
                self._take_popup(client.identity, target)
            for event, raw in queued:
                self._to(client, event, raw)
        elif method == "Target.getTargets":
            infos = [info for info in result.get("targetInfos") or [] if _target_info(info)]
            for info in infos:
                self._targets[info["targetId"]] = {**self._targets.get(info["targetId"], {}), **info}
            result = {**result, "targetInfos": [info for info in infos
                                                if self.visible(client.identity, info["targetId"])]}
        return result

    def _session_event(self, session_id: str, method, params: dict, message: dict, raw: str | None) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            self._hold(session_id, message, raw)  # its attach answer hasn't come yet
            return
        client = session.client
        if client is None or session.cut:
            return
        if method == "Page.downloadWillBegin" and isinstance(params.get("guid"), str):
            client.downloads.add(params["guid"])  # Browser.cancelDownload may name it now
        self._to(client, message, raw)

    def _hold(self, session_id: str, message: dict, raw: str | None) -> None:
        held = self._unbound.get(session_id)
        if held is None:
            held = self._unbound[session_id] = []
            asyncio.get_running_loop().call_later(BIND_WAIT, self._unbound.pop, session_id, None)
        if len(held) < BIND_BUFFER:
            held.append((message, raw))

    def _attach_event(self, method: str, params: dict, message: dict, raw: str | None) -> None:
        """attachedToTarget and detachedFromTarget come on the browser session: routed by the session in params."""
        session_id = params.get("sessionId")
        if not isinstance(session_id, str):
            return
        session = self._sessions.get(session_id)
        if method == "Target.attachedToTarget":
            if session is None:
                self._hold(session_id, message, raw)
            elif session.client is not None:
                self._to(session.client, message, raw)
            return
        self._unbound.pop(session_id, None)
        if session is None:
            return
        del self._sessions[session_id]
        if session.client is not None:
            session.client.sessions.discard(session_id)
            self._to(session.client, message, raw)

    def _target_event(self, method: str, params: dict, message: dict, raw: str | None) -> None:
        info = params.get("targetInfo") if isinstance(params.get("targetInfo"), dict) else None
        target = info.get("targetId") if info is not None else params.get("targetId")
        if not isinstance(target, str):
            return
        if info is not None:
            self._targets[target] = {**self._targets.get(target, {}), **info}
        watching = [client for client in self._clients
                    if client.discover and not client.closed and self.visible(client.identity, target)]
        if method == "Target.targetDestroyed":
            self._targets.pop(target, None)
            if self._grants.pop(target, None) is not None:
                self._changed()
        for client in watching:
            if method == "Target.targetDestroyed":
                client.announced.discard(target)
                self._to(client, message, raw)
            elif method in ("Target.targetCreated", "Target.targetInfoChanged") and target not in client.announced:
                client.announced.add(target)  # created, or changed into sight: announced once, as created
                self._to(client, {"method": "Target.targetCreated",
                                  "params": {"targetInfo": dict(self._targets[target])}})
            elif method != "Target.targetCreated":
                self._to(client, message, raw)

    def _app_client(self):
        return next((client for client in reversed(self._clients) if client.app and not client.closed), None)

    # ---- who may use what (Decision 5) ---------------------------------------------------------------------

    def visible(self, identity: str, target) -> bool:
        """Whether a client may see and use `target`: its own tabs and attached popups, a popup of one of them, a tab
        the user handed it. The app's own client sees everything. Hidden and missing look the same."""
        if not isinstance(target, str):
            return False
        if identity == APP:
            return True
        owner = self._grants.get(target)
        if owner is not None:
            return owner[0] == identity
        return target in self.handed(identity) or self._popup_of(identity, target)

    def _popup_of(self, identity: str, target: str) -> bool:
        opener = self._targets.get(target, {}).get("openerId")
        if not isinstance(opener, str) or opener == target:
            return False
        if self.grants(identity, opener):
            return True
        return opener in self.handed(identity) and any(
            session.target == opener and not session.cut and session.client is not None
            and session.client.identity == identity for session in self._sessions.values())

    def _take_popup(self, identity: str, target: str) -> None:
        """A popup becomes the client's own once it attaches to it; a handed tab never does."""
        if target not in self._grants and target not in self.handed(identity) and self._popup_of(identity, target):
            self._grant(identity, target, "popup")

    def _grant(self, identity: str, target: str, kind: str) -> None:
        if self._grants.get(target, ("",))[0] == identity:
            return
        self._grants[target] = (identity, kind)
        for hook in list(self._grant_hooks):
            with contextlib.suppress(Exception):
                hook(identity, target)
        self._changed()

    def _contexts_of(self, identity: str) -> set:
        return {self._targets.get(target, {}).get("browserContextId") for target in self.own_targets(identity)} - {None}

    def grants(self, identity: str, target) -> bool:
        """Whether `target` is the client's own here (created through the relay, or a popup it attached to)."""
        return isinstance(target, str) and self._grants.get(target, ("",))[0] == identity

    def own_targets(self, identity: str) -> list[str]:
        return [target for target, (owner, _kind) in self._grants.items() if owner == identity]

    def is_cut_off(self, identity: str) -> bool:
        return identity in self._cut_off

    # ---- clients ---------------------------------------------------------------------------------------------

    def local(self) -> LocalClient:
        """The app's own client (Decision 9): TabWatch runs over it, so the app never opens a second connection."""
        client = LocalClient(self)
        if self.state == "connected":
            self._clients.append(client)
            self._changed()
        else:
            client.end(GONE)
        return client

    def _release(self, client) -> None:
        """A client went away, was cut off or was too slow: its sessions are detached in the browser (ending their
        focus emulation, scripts and network buffers there). Its tabs stay open, and stay its own."""
        for session_id in list(client.sessions):
            session = self._sessions.get(session_id)
            if session is not None and session.client is client:
                session.client = None
                self._job(self._quietly("Target.detachFromTarget", {"sessionId": session_id}))
        client.sessions.clear()

    def _left(self, client) -> None:
        if client in self._clients:
            self._clients.remove(client)
        if isinstance(client, _Socket):
            client.closed = True
        self._release(client)
        self._changed()

    def _end(self, client, code: int, at_once: bool = False) -> None:
        """Close one client: a socket once what is queued is sent (at once when it is too slow), the app's own client
        by failing what it waits for."""
        if client in self._clients:
            self._clients.remove(client)
        if client.closed:
            return
        if isinstance(client, LocalClient):
            client.end(code)
            return
        if not at_once:
            client.end(code)
            return
        client.closed = True
        if client.writer is not None:
            client.writer.cancel()
        while not client.queue.empty():
            client.queue.get_nowait()
        client.size = 0
        self._job(_shut(client.ws, code))

    def _lost(self) -> None:
        """The upstream dropped: Brave quit or restarted, or the switch went off (Decision 11)."""
        self._ws = None
        for upstream_id, (client, client_id, method, _params, session_id) in list(self._pending.items()):
            del self._pending[upstream_id]
            future = self._waiting.pop(upstream_id, None)
            if future is not None:
                if not future.done():
                    future.set_exception(CDPError(LOST[1], LOST[0], method))
            elif client is not None:
                self._error(client, client_id, LOST, session_id)
        for session_id, session in list(self._sessions.items()):
            if session.client is not None:
                self._to(session.client, {"method": "Target.detachedFromTarget",
                                          "params": {"sessionId": session_id, "targetId": session.target}})
                session.client.sessions.discard(session_id)
        self._sessions.clear()
        self._unbound.clear()
        self._targets.clear()
        for client in list(self._clients):
            self._end(client, GONE)
        if not self._quitting:
            self._set("lost")
        self._changed()

    async def cut(self, identity: str, target: str) -> None:
        """Take back (Decision 6): the agent's sessions on that tab end now. Each is refused at once, its pending
        commands fail, and the relay detaches it in the browser; the browser's detach note reaches the agent."""
        doomed = []
        for session_id, session in list(self._sessions.items()):  # all of them first, before any await
            client = session.client
            if session.target != target or session.cut or client is None or client.identity != identity:
                continue
            session.cut = True
            doomed.append(session_id)
            for upstream_id, entry in list(self._pending.items()):
                if entry[0] is client and entry[4] == session_id:
                    del self._pending[upstream_id]
                    self._error(client, entry[1], NO_SESSION, session_id)
        for session_id in doomed:
            with contextlib.suppress(CDPError):
                await self._call("Target.detachFromTarget", {"sessionId": session_id}, timeout=5)

    async def disconnect(self, identity: str) -> None:
        """AI Home's Disconnect (Decision 14): cut off for the rest of this run; its tabs stay open."""
        if identity == APP:
            return
        self._cut_off.add(identity)
        for client in [client for client in self._clients if client.identity == identity]:
            self._release(client)
            self._end(client, CUT_OFF)
        self._changed()

    async def forget(self, identity: str, close_tabs: bool = False) -> None:
        """An agent closed or a session ended (Decision 11): its sockets close and, with close_tabs, its own tabs still
        open close too. Its grants go; the cut-off list stays for the run."""
        self._forgotten.add(identity)
        for client in [client for client in self._clients if client.identity == identity]:
            self._release(client)
            self._end(client, 1000)
        if close_tabs and self._ws is not None:
            for target in self.own_targets(identity):
                with contextlib.suppress(CDPError):
                    await self._call("Target.closeTarget", {"targetId": target}, timeout=5)
        for target in self.own_targets(identity):
            self._grants.pop(target, None)
        self._changed()

    def clients(self) -> list[dict]:
        """AI Home's list (Decision 14): the app while connected, then each agent and session with an open socket or
        own tabs. The server adds names and colours."""
        rows = []
        if self.state == "connected":
            rows.append({"id": APP, "kind": "app", "number": None, "tabs": 0, "connected": True, "cut_off": False})
        connected = {client.identity for client in self._clients if not client.closed and not client.app}
        owners = {owner for owner, _kind in self._grants.values()}
        for identity in sorted(connected | owners, key=_order):
            agent = _AGENT_ID.match(identity) is not None
            rows.append({"id": identity, "kind": "agent" if agent else "session",
                         "number": int(identity[1:]) if agent else None, "tabs": len(self.own_targets(identity)),
                         "connected": identity in connected, "cut_off": identity in self._cut_off})
        return rows

    async def close_clients(self, code: int = QUITTING) -> None:
        """The app is quitting, its agents have ended: every client socket closes. The upstream stays for close()."""
        self._quitting = True
        if self._attempt is not None and not self._attempt.done():
            self._attempt.cancel()  # a handshake waiting for Brave's question hears "AI Browser is quitting" now
        for client in [client for client in self._clients if not client.app]:
            self._end(client, code)
        self._changed()

    async def close(self) -> None:
        self._quitting = True
        if self._poll is not None:
            self._poll.cancel()
            self._poll = None
        if self._attempt is not None and not self._attempt.done():
            self._attempt.cancel()
        for client in list(self._clients):
            self._end(client, QUITTING)
        await self._close_upstream()
        for job in list(self._jobs):
            job.cancel()
