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

import hmac
import ipaddress
import re
import secrets
import unicodedata
from urllib.parse import unquote, urlsplit

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
    host = unicodedata.normalize("NFKC", unquote(host)).lower()
    if (port if port is not None else 443 if scheme == "https" else 80) != app_port:
        return None
    try:
        return APP_PAGE if _loopback(host) else None
    except ValueError:
        return UNREADABLE  # Chrome wouldn't read it either: refused, never guessed


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
