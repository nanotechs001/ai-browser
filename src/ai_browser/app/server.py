"""The AI Browser app server: AI Home's, Mission Control's and Settings' only way to the agents, and Brave's
watcher's.

It listens on 127.0.0.1 only, and every route checks the Host header. AI Browser's pages are served here to its own
window, which swaps a one-time code for an HttpOnly cookie and lands on its tab menu (/app); the menu shows our other
pages in frames, and only it may frame them. A window socket needs that cookie and our exact Origin and Host, and the
pages in the menu's frames are the window's sockets. Brave's watcher connects with its token from its own extension origin. The agents' engines report their
tabs to /agent-events with tokens of their own, and reach the browser through /cdp. Everything that happens to an
agent is broadcast to every socket (the watcher gets a trimmed copy); an agent's conversation is sent on request
(`events`), so a page opened later can draw it whole."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hmac
import html
import json
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from .. import browsers, platforms
from ..brain.service import BrainService
from ..brain.skillwriter import SkillError, SkillWriter
from ..brain.tools import ToolsConfig
from ..brain.workflows import WorkflowRunner, WorkflowStore
from ..checks import KINDS
from ..chrome import own_browser_dir
from ..config import LIVE_PORTS, load_config, project_root
from ..engine import _alive
from ..extension_id import extension_path
from ..grouping import MARKER
from ..hearing.service import HearingService, unavailable_status
from ..live import _bind, _QuietServer, _serve
from ..settings import Settings
from ..skills import Catalog
from ..syncdir import write_atomic
from .agents import Agent, AgentManager, agent_number
from .cdprelay import Tokens
from .groups import GroupKeeper

APP_PORTS = range(8792, 8812)
MODELS = {"opus", "sonnet", "haiku"}
REFUSED = 4403  # WebSocket close code for a wrong token or origin
PING_EVERY = 20  # seconds: a message now and then keeps the extension's service worker, and its socket, alive
THUMB_EVERY = 2  # seconds between two thumbnails of one agent's tab
TEXT_LIMIT = 20_000  # characters of a task or a message
# only Brave's watcher sends these
WATCHER_MESSAGES = {"items", "replied", "thread", "filled", "reader_status", "watcher_caps", "tab_grouped"}
BRAIN_MESSAGES = {"brain", "draft", "approve", "hand", "done", "tell", "watch_set", "watch_remove", "pause", "style",
                  "tell_confirm", "tell_dismiss"}
TOOLS_MESSAGES = {"tools", "tool_set", "tool_allow", "tool_forget", "permission"}
WORKFLOW_MESSAGES = {"workflows", "workflow_save", "workflow_delete", "workflow_run"}
SKILL_MESSAGES = {"skill_draft", "skill_save"}
HEARING_MESSAGES = {"hearing", "hearing_download", "hearing_cancel", "listen_start", "listen_chunk", "listen_end",
                    "listen_cancel"}  # push-to-talk: only AI Browser's own pages, never the watcher
TALK_MESSAGES = {"brain_ask", "brain_confirm", "brain_dismiss"}  # the talk with the Brain: the same
_TALK_ID = re.compile(r"^[A-Za-z0-9-]{1,40}$")
CHECK_MESSAGES = {"check_continue", "check_skip", "check_show"}  # a bot check's buttons (who may: MESSAGE_RULES)
BRAVE_MESSAGES = {"brave_connect", "hand_tab", "take_back", "browser_disconnect"}  # only AI Browser's own pages
CHECK_SITE = re.compile(r"[a-z0-9.-]{1,253}")  # a host name, nothing else
CHECK_LIVE = re.compile(r"http://127\.0\.0\.1:\d{1,5}/live\?token=[A-Za-z0-9_-]{1,64}")  # an engine's live view
WORKFLOW_FIELDS = ("slug", "name", "instructions", "trigger", "site", "when", "schedule", "run", "tools", "skills",
                   "model")
WATCH_FIELDS = ("site", "label", "url_match", "selector", "instructions", "enabled")
UI = Path(__file__).with_name("ui")  # AI Browser's pages, served to its window only
SETUP_PAGE = UI / "setup.html"
SHELL = "/app"  # the window's own page: the tab menu, which shows the others in frames
PAGES = {SHELL: "app.html", "/home": "home.html", "/mission": "mission.html", "/settings": "settings.html"}
FRAMED = frozenset({"/home", "/mission", "/settings", "/setup"})  # the pages the tab menu shows: only it frames them
LIVE_VIEWS = " ".join(f"http://127.0.0.1:{port}" for port in LIVE_PORTS)  # an engine's live view binds one of these
FILE_TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".png": "image/png"}
OPEN_ANYWHERE = {"setup.js", "setup.css", "icon.png"}  # the setup page's own files: it opens in Brave too
CODE_TTL = 60  # seconds a one-time start code is good for
SETTING_KEYS = ("model", "voice", "window_browser")
URL_LIMIT = 2000  # characters of a website address a page may ask the user's browser to open
KEYWORD_LIMIT = 2000  # characters of what the user typed after "ai" in Brave's address bar
NOT_HERE = "AI Browser's pages open only in its own window. Start it with `uv run ai-browser app`."
USED_CODE = "This start link was used already or has expired. Start AI Browser again."
SOURCES = {"personal": "personal", "anthropic-skills": "claude.ai", "ai-browser": "ai-browser"}  # else: plugins
SESSION_ID = re.compile(r"^cc-[0-9a-z-]{1,40}$")  # a Claude Code session's id (cc-<task id>)
AGENT_ID = re.compile(r"^a[0-9]{1,9}$")  # an agent's id (a<number>)
SESSION_SWEEP = 30  # seconds between two looks at the sessions' processes
YOU = {"kind": "you"}


@dataclass(frozen=True)
class Rule:
    """Who may send one message type: AI Browser's own pages ("app"), and Brave's watcher ("watcher"), which may send
    it never, always, or when the check on the message passes."""
    app: bool = True
    watcher: bool | Callable[[dict], bool] = False


def _has_item(message: dict) -> bool:
    """The inbox's "Run <workflow>" on a message: never a bare run, which stays in AI Home."""
    return isinstance(message.get("item"), str) and message["item"] != ""


def _once_or_deny(message: dict) -> bool:
    """A tool request allowed once, or denied: a lasting Always allow stays in AI Home's Tools."""
    return message.get("answer") in ("once", "deny")


APP_ONLY, BOTH, WATCHER_ONLY = Rule(), Rule(watcher=True), Rule(app=False, watcher=True)

# Every message type a page may send, and who may send it (watcher-safety Decision 1). A type missing here is dropped
# for everyone, with no answer. tests/test_watcher_rules.py holds a copy: a row added here fails there until the copy
# says the same. A row may allow the watcher only if it can't give an agent a tab of the user's, save a lasting allow,
# connect to Brave, talk or listen, skip a check or close a tab.
MESSAGE_RULES: dict[str, Rule] = {
    "hello": BOTH,
    # the watcher's reports: they count only from the socket that said hello as the watcher (_handle)
    "items": WATCHER_ONLY, "replied": WATCHER_ONLY, "thread": WATCHER_ONLY, "filled": WATCHER_ONLY,
    "reader_status": WATCHER_ONLY, "watcher_caps": WATCHER_ONLY, "tab_grouped": WATCHER_ONLY,
    # the Brain's inbox, in AI Home and on the watcher's Brain page
    "brain": BOTH, "draft": BOTH, "approve": BOTH, "hand": BOTH, "done": BOTH, "tell": BOTH, "watch_set": BOTH,
    "watch_remove": BOTH, "pause": BOTH, "style": BOTH,
    "workflow_run": Rule(watcher=_has_item),
    "workflows": APP_ONLY, "workflow_save": APP_ONLY, "workflow_delete": APP_ONLY,
    "permission": Rule(watcher=_once_or_deny),
    "tools": APP_ONLY, "tool_set": APP_ONLY, "tool_allow": APP_ONLY, "tool_forget": APP_ONLY,
    "skills": APP_ONLY, "skill_draft": APP_ONLY, "skill_save": APP_ONLY,
    "hearing": APP_ONLY, "hearing_download": APP_ONLY, "hearing_cancel": APP_ONLY, "listen_start": APP_ONLY,
    "listen_chunk": APP_ONLY, "listen_end": APP_ONLY, "listen_cancel": APP_ONLY,
    "brain_ask": APP_ONLY, "brain_confirm": APP_ONLY, "brain_dismiss": APP_ONLY,
    "tell_confirm": APP_ONLY, "tell_dismiss": APP_ONLY,  # brain-delegation: a card runs only from our own pages
    "check_continue": BOTH, "check_skip": APP_ONLY, "check_show": BOTH,  # Skip closes a tab: never the watcher's
    "brave_connect": APP_ONLY, "hand_tab": APP_ONLY, "take_back": APP_ONLY,
    "browser_disconnect": APP_ONLY,  # cdp-relay: Disconnect in AI Home's list of connected clients
    "new_task": APP_ONLY,  # with or without adopt
    "send": APP_ONLY, "stop": APP_ONLY, "close": APP_ONLY, "model": APP_ONLY,
    "watch": APP_ONLY, "events": APP_ONLY, "thumbs": APP_ONLY,
    "settings_set": Rule(app=True, watcher=False),  # the window's Settings, AI Home's and Mission Control's picks
    "open_url": Rule(app=True, watcher=False),  # a website link in one of our pages
    "ai_keyword": Rule(app=False, watcher=True),  # Brave's address bar: only the watcher's omnibox handler
}


def may_send(role: str, message: dict) -> bool:
    """Whether a page of this role ("app" or "watcher") may send this message. An unknown type, a message without
    one, or a type that isn't a string is never allowed, for anyone."""
    kind = message.get("type")
    rule = MESSAGE_RULES.get(kind) if isinstance(kind, str) else None
    if rule is None:
        return False
    if role == "app":
        return rule.app
    if role == "watcher":
        return bool(rule.watcher(message)) if callable(rule.watcher) else rule.watcher is True
    return False


# What a socket from Brave's watcher's origin may get (watcher-safety Decision 5): never a tab list, a session, a
# picture, an agent's conversation or the Tools, workflow and skill messages, and never a tab's target id.
WATCHER_RECEIVES = frozenset({
    "ping", "error", "watcher_hello", "watch_list", "notify", "permission_request", "check_request", "group_tab",
    "ungroup_tabs", "open_thread", "fill_reply",  # for the worker
    "snapshot", "agent", "agent_closed", "brain_snapshot", "brain_item", "brain_item_gone", "brain_state",  # Brain page
    "keyword_started",  # the worker: the answer to the ai keyword
})
WATCHER_AGENT_FIELDS = ("id", "name", "color", "state", "permission")  # what the Brain page reads of an agent


def _watcher_row(agent) -> dict:
    return {key: agent[key] for key in WATCHER_AGENT_FIELDS if key in agent} if isinstance(agent, dict) else {}


def for_watcher(message: dict) -> dict | None:
    """What a watcher-origin socket may get: the message, a trimmed copy, or None. It never changes its input,
    because _send_all puts one dict in every queue."""
    kind = message.get("type")
    if not isinstance(kind, str) or kind not in WATCHER_RECEIVES:
        return None  # a type added later is dropped too, until it is written down here
    if kind == "snapshot":
        agents = message.get("agents")
        return {"type": "snapshot", "agents": [_watcher_row(agent) for agent in agents]
                if isinstance(agents, list) else []}
    if kind == "agent":
        return {"type": "agent", "agent": _watcher_row(message.get("agent"))}
    if kind == "check_request":
        return {key: value for key, value in message.items() if key != "target"}  # Show me asks by agent id
    return message


reveal_folder = platforms.reveal  # a file manager window with the folder selected; False when none could open
GOTO_MAC = "press ⌘⇧G, paste the path and press Enter"
GOTO_OTHER = "click the address bar at the top of the folder window, paste the path and press Enter"


def setup_page(watcher: str, system: str | None = None) -> str:
    """The one-time setup page (Brave's two steps), worded for the computer it runs on; every value is escaped. It
    holds no secret: it is the one page of ours that opens anywhere."""
    values = {"{{FILE_MANAGER}}": platforms.file_manager(system),
              "{{GOTO}}": platforms.shortcut(GOTO_MAC, GOTO_OTHER, system),
              "{{THIS_COMPUTER}}": platforms.this_computer(system), "{{WATCHER}}": watcher}
    page = SETUP_PAGE.read_text(encoding="utf-8")
    for placeholder, value in values.items():
        page = page.replace(placeholder, html.escape(value))
    return page


def _first_line(text, limit: int = 200) -> str:
    return next((line.strip() for line in str(text or "").splitlines() if line.strip()), "")[:limit]


def _text(value) -> str:
    return value.strip()[:TEXT_LIMIT] if isinstance(value, str) else ""


def _tab(value) -> dict:
    """The tab a message was written beside: page data, trimmed again by the bridge."""
    if not isinstance(value, dict):
        return {}
    return {key: value[key][:2000] for key in ("url", "title") if isinstance(value.get(key), str)}


def _valid_check(report: dict) -> bool:
    """A check report the app may show: a kind from our own table, a plain host name, our own live-view link."""
    site, live = report.get("site"), report.get("live")
    return (report.get("check") in KINDS and isinstance(site, str) and CHECK_SITE.fullmatch(site) is not None
            and (live is None or (isinstance(live, str) and CHECK_LIVE.fullmatch(live) is not None)))


def _clock() -> float:
    return time.monotonic()  # its own function, so a test moves the start codes' clock and nothing else


def _refused_page(text: str) -> HTMLResponse:
    """A plain 403 page: one line of text, no script."""
    return HTMLResponse('<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><title>AI Browser</title>'
                        f"</head><body><p>{html.escape(text, quote=False)}</p></body></html>\n", status_code=403)


def _web_address(value) -> str | None:
    """A link's address, if the user's browser may open it: http or https with a host, no user name or password, no
    whitespace or control character, at most URL_LIMIT characters."""
    if not isinstance(value, str) or not value.startswith(("http://", "https://")) or len(value) > URL_LIMIT:
        return None
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value):
        return None
    try:
        parts = urlsplit(value)
        parts.port  # noqa: B018  (a bad port raises here)
    except ValueError:
        return None
    if not parts.hostname or parts.username is not None or parts.password is not None:
        return None
    return value


def _strict_headers(host: str, port: int, frames: str = "", ancestors: str = "'none'") -> list[tuple[bytes, bytes]]:
    """On every HTTP answer: scripts and styles from our own files only, sockets only to /ws, fetches only to /setup/
    (so a page's script can never reach /cdp or /agent-*), no sniffing, no referrer, nothing cached. A page frames
    nothing and nothing frames it, except the window's tab menu: it frames `frames`, and the pages it shows let only
    their own origin frame them (`ancestors`, from _page_headers)."""
    origin = f"{host}:{port}"
    csp = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
           f"connect-src ws://{origin}/ws http://{origin}/setup/; {f'frame-src {frames}; ' if frames else ''}"
           f"base-uri 'none'; form-action 'none'; frame-ancestors {ancestors}")
    return [(b"content-security-policy", csp.encode()), (b"x-content-type-options", b"nosniff"),
            (b"referrer-policy", b"no-referrer"), (b"cache-control", b"no-store"),
            (b"cross-origin-resource-policy", b"same-origin")]


def _page_headers(host: str, port: int) -> dict[str, list[tuple[bytes, bytes]]]:
    """The answers that differ from the strict headers, by path: the tab menu frames our pages and an engine's live
    view (its own ports only), and nothing frames the menu; each page it shows may be framed by its own origin only.
    Every other header stays as strict."""
    shown = _strict_headers(host, port, ancestors="'self'")
    return {SHELL: _strict_headers(host, port, frames=f"'self' {LIVE_VIEWS}"), **dict.fromkeys(FRAMED, shown)}


def _with_headers(send, headers: list[tuple[bytes, bytes]]):
    """`send`, with `headers` on the answer in place of any the route set under the same names."""
    names = {name for name, _ in headers}

    async def sending(message):
        if message["type"] == "http.response.start":
            kept = [(name, value) for name, value in message.get("headers", []) if name.lower() not in names]
            message = {**message, "headers": kept + headers}
        await send(message)

    return sending


class _Guard:
    """The whole app, HTTP and WebSocket alike, behind one check: the Host header must be exactly 127.0.0.1:<port>,
    which blocks DNS rebinding (Starlette's TrustedHostMiddleware ignores the port, so it isn't used). Every HTTP
    answer, a refusal too, carries the strict headers, or a page's own from _page_headers."""

    def __init__(self, app, server: AppServer):
        self.app, self.server = app, server

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        host = next((value.decode("latin-1") for key, value in scope["headers"] if key == b"host"), "")
        if self.server.port is None or host != self.server.host_header:
            if scope["type"] == "websocket":
                await receive()  # websocket.connect
                await send({"type": "websocket.close", "code": 1008})  # before accept: the client reads HTTP 403
            else:
                await PlainTextResponse("refused", status_code=403)(
                    scope, receive, _with_headers(send, self.server.strict_headers))
            return
        if scope["type"] == "http":
            send = _with_headers(send, self.server.page_headers.get(scope["path"], self.server.strict_headers))
        await self.app(scope, receive, send)


class AppServer:
    def __init__(self, home: Path, agents: AgentManager, tabs=None, catalog: Catalog | None = None,
                 host: str = "127.0.0.1", ports: range = APP_PORTS, default_model: str = "sonnet",
                 brain: BrainService | None = None, tools: ToolsConfig | None = None,
                 workflows: WorkflowStore | None = None, runner: WorkflowRunner | None = None,
                 skill_writer: SkillWriter | None = None, hearing: HearingService | None = None,
                 settings: Settings | None = None, port_file: Path | None = None):
        self.home = Path(home)
        self.settings = settings if settings is not None else Settings(self.home)  # <home>/settings.json
        self.port_file = Path(port_file) if port_file is not None else None  # run_app: <home>/app/port
        self.window_info: dict = {"using": None, "name": "", "note": "", "choices": []}  # run_app sets it once
        self.agents = agents
        self.brain = brain
        self.skill_writer = skill_writer  # skills the Brain drafts, written only on the user's Save
        if skill_writer is not None and skill_writer.on_saved is None:
            skill_writer.on_saved = self.skills_changed
        self.hearing = hearing  # push-to-talk: the user's speech becomes text on this computer (Mission Control)
        if hearing is not None:
            hearing.on_status = lambda status: self._send_all({"type": "hearing_status", **status})
        self.tools = tools  # the user's MCP servers for the agents (AI Home → Tools)
        if tools is not None:
            agents.tools = tools
        self.workflows, self.runner = workflows, runner  # the user's workflows (AI Home → Workflows)
        if runner is not None:
            runner.on_change = self.workflows_changed
        if brain is not None:
            brain.workflows, brain.runner = workflows, runner
        self.watcher_build = ""  # the watcher files' version (prepare_watcher): an older watcher reloads itself
        self.watcher_folder: str | None = None
        self._watcher_origins: set[str] = set()
        self._origin_of: dict[WebSocket, str] = {}
        self._roles: dict[WebSocket, str] = {}  # "app" or "watcher", stored when a socket is accepted
        self._windows: set[WebSocket] = set()  # AI Browser's window's sockets: the pages in its tabs (AI Home…)
        self.window_seen = False  # the window's first socket has come in
        self._watcher: tuple[WebSocket, asyncio.Queue] | None = None  # Brave's watcher (the latest one to connect)
        if brain is not None:
            brain.broadcast = self._send_all
            brain.send_watcher = self._to_watcher
        self.default_model = default_model if default_model in MODELS else "sonnet"  # ai-browser app --model
        self.host = host
        self.ports = ports
        self.token = secrets.token_urlsafe(24)  # Brave's watcher (in its config.json)
        self.tokens = Tokens()  # each agent's own token (and each session's for /cdp), new every run
        self.session_token = secrets.token_urlsafe(24)  # Claude Code sessions (in <home>/app/link.json, mode 0600)
        self.groups = GroupKeeper(self._to_watcher, on_change=self._browser_changed)  # tab groups, through the watcher
        self.brave = None  # BraveLink in brave mode (attach_brave): the user's Brave
        self.sessions: dict[str, dict] = {}  # Claude Code sessions browsing in Brave while the app runs
        self._thread_urls: dict[str, str] = {}  # open_thread request -> its address (the Brain's group in AI Home)
        self._sweeper: asyncio.Task | None = None
        self.url: str | None = None
        self.port: int | None = None  # the bound port, once start() has one
        self.strict_headers: list[tuple[bytes, bytes]] = []  # every HTTP answer's headers, once the port is known
        self.page_headers: dict[str, list[tuple[bytes, bytes]]] = {}  # the tab menu's and its pages' own (by path)
        self.ui_secret = secrets.token_urlsafe(32)  # the window's session cookie: set only by swapping a start code
        self._codes: dict[str, float] = {}  # one-time start codes -> when they expire (_clock)
        self._files = {path.name for path in UI.iterdir() if path.is_file() and path.suffix in FILE_TYPES}
        self.origin_mismatch: str | None = None  # an extension with our token, from an origin we didn't compute
        self.out: Callable[[str], None] = print  # where the app's one-line notes go (run_app passes its own)
        self.reveal = reveal_folder
        self.tabs = None
        self._catalog = catalog
        self._sockets: dict[WebSocket, asyncio.Queue] = {}  # sockets that said hello: they get every broadcast
        self._writers: dict[WebSocket, asyncio.Task] = {}
        self._feed = agents.subscribe()
        self._fanout: asyncio.Task | None = None
        self._thumbs: dict[str, dict] = {}  # agent id -> {"last": monotonic time, "task", "again", "jpeg"}
        self._jobs: set[asyncio.Task] = set()
        self._server: _QuietServer | None = None
        self._task: asyncio.Task | None = None
        agents.on_action = self._on_action
        agents.ungroup = self._ungroup  # a handed tab taken back, or let go when its agent closes
        agents.on_turn = lambda agent: self.connect_brave("turn", agent.id)  # right after the user's task
        agents.mint_token = self.tokens.mint
        if tabs is not None:
            self.attach_tabs(tabs)

    def allow_watcher(self, origin: str) -> None:
        """Brave's watcher's origin (chrome-extension://<id>): the only origin that may connect with the token."""
        self._watcher_origins.add(origin)

    @property
    def window_count(self) -> int:
        return len(self._windows)  # a set: never below 0, never a socket twice

    def _socket_kind(self, ws: WebSocket) -> str | None:
        """Who opens this socket: AI Browser's window (its cookie, our exact Origin and Host), or Brave's watcher (the
        token and a watcher origin). None: refused."""
        origin = ws.headers.get("origin")
        if origin == self.origin and ws.headers.get("host") == self.host_header and self._cookie_ok(ws):
            return "window"
        if not hmac.compare_digest(ws.query_params.get("token", "").encode(), self.token.encode()):
            return None
        if origin in self._watcher_origins:
            return "watcher"
        if self._watcher_origins and isinstance(origin, str) and origin.startswith("chrome-extension://"):
            self._mismatch(origin)  # only once the app has allowed its computed ID: before that, no mismatch
        return None

    @property
    def origin(self) -> str:
        """AI Browser's pages' own origin: the only Origin a window socket may carry."""
        return f"http://{self.host}:{self.port}"

    @property
    def host_header(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def cookie_name(self) -> str:
        return f"aib_ui_{self.port}"  # cookies on 127.0.0.1 reach every port: the name keeps two apps apart

    def new_launch_code(self) -> str:
        """A start code for the window's address: single use, CODE_TTL seconds. Expired ones are dropped here."""
        now = _clock()
        self._codes = {code: until for code, until in self._codes.items() if until > now}
        code = secrets.token_urlsafe(32)
        self._codes[code] = now + CODE_TTL
        return code

    def _take_code(self, given: str) -> bool:
        now = _clock()
        for code, until in list(self._codes.items()):
            if hmac.compare_digest(code.encode(), given.encode()):
                del self._codes[code]  # used: never again, valid or not
                return until > now
        return False

    def _cookie_ok(self, connection) -> bool:
        """The window's cookie on a request or a socket (Starlette gives both .cookies)."""
        given = connection.cookies.get(self.cookie_name, "")
        return bool(given) and hmac.compare_digest(given.encode(), self.ui_secret.encode())

    def _settings_payload(self) -> dict:
        return {**self.settings.get(), "window": dict(self.window_info)}

    def _settings_set(self, queue: asyncio.Queue, message: dict) -> None:
        request = message.get("request") if isinstance(message.get("request"), (str, int)) else None
        key = message.get("key")
        if key not in SETTING_KEYS:
            queue.put_nowait({"type": "error", "text": "There is no such setting", "request": request})
            return
        try:
            self.settings.set(key, message.get("value"))
        except ValueError as exc:
            queue.put_nowait({"type": "error", "text": str(exc), "request": request})
            return
        except OSError as exc:  # a read-only home, a full disk: nothing changed
            queue.put_nowait({"type": "error", "text": f"Couldn't save that setting: {exc.strerror or exc}",
                              "request": request})
            return
        self._send_all({"type": "settings", **self._settings_payload()})  # the watcher's filter keeps it out

    def _agents_browser(self):
        """The agents' browser, as an installed row (it opens a website the user clicked), or None for the system's
        default. Wave C uses the saved place instead."""
        facts = browsers.for_data_dir(own_browser_dir())
        if facts is None:
            return None
        return next((row for row in browsers.installed() if row.id == facts.id), None)

    async def _open_url(self, queue: asyncio.Queue, message: dict) -> None:
        url = _web_address(message.get("url"))
        if url is None:
            queue.put_nowait({"type": "error", "text": "Only web addresses open from here"})
            return
        browser = await asyncio.to_thread(self._agents_browser)
        if not await asyncio.to_thread(platforms.open_url, url, browser):
            queue.put_nowait({"type": "error", "text": "Couldn't open that address in your browser"})

    def _keyword_workflow(self, text: str) -> tuple[str, str] | None:
        """The workflow a keyword's text starts with: the longest name it starts with, then a space or nothing more,
        without regard to case. (slug, the rest of the text), or None."""
        if self.workflows is None:
            return None
        lower, found = text.lower(), None
        for workflow in self.workflows.all():
            name = workflow.name.lower()
            if (lower == name or lower.startswith(f"{name} ")) and (found is None or len(name) > len(found[0])):
                found = (name, workflow.slug)
        return None if found is None else (found[1], text[len(found[0]):].strip())

    async def _keyword(self, queue: asyncio.Queue, message: dict) -> None:
        """"ai", a space and a task in Brave's address bar: the user's own Enter, like Start in AI Home. It never
        goes through the Brain, and it never hands over a tab: adopt and tab are ignored here."""
        request = message.get("request") if isinstance(message.get("request"), (str, int)) else None
        text = message.get("text").strip()[:KEYWORD_LIMIT].strip() if isinstance(message.get("text"), str) else ""
        if not text:
            return
        try:
            found = self._keyword_workflow(text)
            if found is not None and self.runner is not None:
                agent_id = await self.runner.run(found[0], text=found[1] or None)
            else:
                model = self.settings.get()["model"] or self.default_model
                agent_id = (await self.agents.create(text, [], model)).id
        except ValueError as exc:
            queue.put_nowait({"type": "error", "request": request, "text": str(exc)})
            return
        agent = self.agents.agents.get(agent_id)
        queue.put_nowait({"type": "keyword_started", "request": request, "id": agent_id,
                          "number": agent.number if agent is not None else agent_number(agent_id),
                          "name": agent.name if agent is not None else ""})

    def _saved_port(self) -> int | None:
        """The port this home used before (the microphone grant belongs to that address), if it is one of ours."""
        if self.port_file is None:
            return None
        try:
            port = int(self.port_file.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None
        return port if port in self.ports else None

    def _remember_port(self, saved: int | None, port: int) -> None:
        if self.port_file is None:
            return
        if saved is None:  # missing, unreadable, or not one of ours: this port from now on
            with contextlib.suppress(OSError):
                write_atomic(self.port_file, f"{port}\n".encode("utf-8"))
        elif saved != port:  # busy this once: the file stays, so the next start goes back to the granted address
            self.out(f"Port {saved} is busy: AI Browser uses {port} this time, and may ask for the microphone "
                     "again.")

    def _mismatch(self, origin: str) -> None:
        """Only a watcher holding our config.json has the token: from an origin we didn't compute, it means an
        extension ID is computed wrong on this computer. The socket is still refused; this says so, once."""
        if origin == self.origin_mismatch:
            return
        self.origin_mismatch = origin
        expected = ", ".join(sorted(self._watcher_origins)) or "?"
        self.out(f"A watcher connected as {origin}, but the app expected {expected}: please report this")

    def token_for(self, agent_id: str) -> str:
        """An agent's own token (minted when it is created): its engine's key to the reports and to /cdp."""
        return self.tokens.mint(agent_id)

    def attach_tabs(self, tabs) -> None:
        """The tab source (AI Browser's TabWatch, or BraveLink in brave mode): the tab list, Watch and thumbnails."""
        self.tabs = tabs
        tabs.on_change(lambda listing: self._tabs_changed(tabs, listing))

    def _tabs_changed(self, source, listing: list[dict]) -> None:
        if self.tabs is source:  # a source replaced since (brave mode attached after it) is no longer heard
            self._send_all(self._tabs_message(listing))

    def _tab_scope(self) -> dict | None:
        """BraveLink's {"profile", "elsewhere"}: which profile the list shows, and how many of the user's tabs it
        leaves out (a number only). None for AI Browser's own TabWatch, which lists every tab, and while Brave isn't
        connected: then the list is empty and claims nothing (BraveLink sends that list before the browser card)."""
        scope = getattr(self.tabs, "scope", None)
        if not callable(scope) or getattr(self.tabs, "state", "connected") != "connected":
            return None
        return scope()

    def _tabs_message(self, listing: list[dict]) -> dict:
        scope = self._tab_scope()
        return {"type": "tabs", "tabs": listing, **({"tab_scope": scope} if scope is not None else {})}

    async def start(self) -> str:
        app = _Guard(Starlette(routes=[Route("/", self._root), Route("/open", self._open), Route(SHELL, self._page),
                                       Route("/home", self._page), Route("/mission", self._page),
                                       Route("/settings", self._page),
                                       Route("/health", self._health), Route("/setup", self._setup),
                                       Route("/setup/status", self._setup_status),
                                       Route("/setup/reveal", self._setup_reveal, methods=["POST"]),
                                       Route("/agent-events", self._agent_events, methods=["POST"]),
                                       Route("/agent-claim", self._agent_claim, methods=["POST"]),
                                       Route("/agent-status", self._agent_status),
                                       Route("/agent-hello", self._agent_hello, methods=["POST"]),
                                       Route("/agent-bye", self._agent_bye, methods=["POST"]),
                                       Route("/{name}", self._file),
                                       WebSocketRoute("/ws", self._socket), WebSocketRoute("/cdp", self._cdp)]), self)
        self._fanout = asyncio.create_task(self._forward())
        self._sweeper = asyncio.create_task(self._sweep_sessions())
        if self.brain is not None:
            await self.brain.start()
        saved = self._saved_port()
        for port in ([saved] if saved is not None else []) + [port for port in self.ports if port != saved]:
            sock = _bind(self.host, port)
            if sock is None:
                continue
            self.port = port
            self.strict_headers = _strict_headers(self.host, port)
            self.page_headers = _page_headers(self.host, port)
            # websockets-sansio: no handshake timeout, so the relay can hold one while the user answers Allow
            self._server = _QuietServer(uvicorn.Config(app, host=self.host, port=port, log_level="warning",
                                                       access_log=False, lifespan="off", ws="websockets-sansio"))
            self._task = asyncio.create_task(_serve(self._server, sock))
            for _ in range(200):
                if self._server.started or self._task.done():
                    break
                await asyncio.sleep(0.01)
            if self._server.started:
                self.url = f"http://{self.host}:{port}"
                self._remember_port(saved, port)
                if self.brave is not None:
                    self.brave.relay.port = port
                return self.url
            sock.close()
        self.port = None
        raise RuntimeError(f"no free port for the AI Browser app server ({self.ports.start}-{self.ports.stop - 1})")

    async def stop(self) -> None:
        if self.hearing is not None:
            await self.hearing.stop()  # a download in progress is cancelled, and nothing half-written is kept
        if self.brain is not None:
            await self.brain.stop()
        await self.agents.close_all()  # every agent's Claude Code process ends with the app
        if self.brave is not None:  # the agents have ended: their sockets close (1001) before uvicorn stops
            with contextlib.suppress(Exception):
                await self.brave.relay.close_clients(1001)
        for task in [self._fanout, self._sweeper, *self._jobs, *(state["task"] for state in self._thumbs.values())]:
            if task is not None:
                task.cancel()
        self.agents.unsubscribe(self._feed)
        for ws in list(self._writers):
            self._unsubscribe(ws)
            with contextlib.suppress(Exception):
                await ws.close()
        if self._server is not None:
            self._server.should_exit = True
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._task, timeout=5)
        self._server = self._task = None

    # ---- HTTP -----------------------------------------------------------------------------------------------

    async def _health(self, request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    async def _root(self, request: Request) -> Response:
        return RedirectResponse(SHELL, status_code=303)

    async def _open(self, request: Request) -> Response:
        """The window's start address: a valid code becomes the cookie, and the redirect to the tab menu drops the code
        from the window's address and history. A used or unknown code is a 403, unless the cookie is already there (a
        reload)."""
        if self._take_code(request.query_params.get("code", "")):
            response = RedirectResponse(SHELL, status_code=303)
            response.set_cookie(self.cookie_name, self.ui_secret, httponly=True, samesite="strict", path="/")
            return response
        if self._cookie_ok(request):
            return RedirectResponse(SHELL, status_code=303)
        return _refused_page(USED_CODE)

    async def _page(self, request: Request) -> Response:
        if not self._cookie_ok(request):
            return _refused_page(NOT_HERE)
        path = UI / PAGES[request.url.path]
        if not path.is_file():
            return Response(status_code=404)
        return HTMLResponse(path.read_text(encoding="utf-8"))

    async def _file(self, request: Request) -> Response:
        """A script, style or picture of app/ui: only names read at start, so no other path is ever served."""
        name = request.path_params["name"]
        if name not in self._files:
            return Response(status_code=404)
        if name not in OPEN_ANYWHERE and not self._cookie_ok(request):
            return _refused_page(NOT_HERE)
        return Response((UI / name).read_bytes(), media_type=FILE_TYPES[Path(name).suffix])

    def _watcher_folder(self) -> str:
        return extension_path(self.watcher_folder or self.home / "app" / "watcher")

    async def _setup(self, request: Request) -> HTMLResponse:
        return HTMLResponse(setup_page(self._watcher_folder()))

    async def _setup_reveal(self, request: Request) -> Response:
        """Show the watcher's folder: only from AI Browser's own window (its cookie and our exact Origin), so no
        other page, in Brave or anywhere, can open a folder window."""
        if not (self._cookie_ok(request) and request.headers.get("origin") == self.origin):
            return Response(status_code=403)
        shown = self.reveal(self._watcher_folder())
        return Response(status_code=204 if shown else 501)  # 501: nothing could show it (no file manager)

    async def _setup_status(self, request: Request) -> JSONResponse:
        answer = {"watcher": self.brain is not None and self.brain.store.watcher_seen}
        if self.origin_mismatch:
            answer["mismatch"] = self.origin_mismatch
        return JSONResponse(answer)

    async def _agent_events(self, request: Request) -> Response:
        try:
            report = await request.json()
        except ValueError:
            return Response(status_code=400)
        if not isinstance(report, dict) or not isinstance(report.get("agent"), str):
            return Response(status_code=204)
        agent = report["agent"]
        if not self._token_ok(request, agent):
            return Response(status_code=403)
        if self._relay_drops(report):  # brave mode: only tabs the relay gives this agent or session
            return Response(status_code=204)
        if SESSION_ID.match(agent):  # first: a session's tabs; its check reports are dropped (it has no row)
            self._session_report(agent, report)
            return Response(status_code=204)
        self._agent_report(report)  # wave 1: check reports, then tab_event
        self._after_agent_report(report)
        return Response(status_code=204)

    def _token_ok(self, request: Request, agent: str) -> bool:
        """The session token for a session's id; for an agent's id, that agent's own token and no other."""
        given = request.headers.get("x-aib-agent-token", "")
        if SESSION_ID.match(agent):
            return hmac.compare_digest(given.encode("utf-8", "replace"), self.session_token.encode())
        return self.tokens.check(agent, given)

    def _granted(self, owner_id: str, target) -> str | None:
        """Brave mode (Decision 5): "own" when the relay says the agent or session opened `target`, "handed" when the
        user handed it to the agent, else None."""
        if not isinstance(target, str) or not target:
            return None
        if self.brave.relay.grants(owner_id, target):
            return "own"
        agent = self.agents.agents.get(owner_id)
        return "handed" if agent is not None and target in agent.adopted else None

    def _relay_drops(self, report: dict) -> bool:
        """A tab report about a tab the relay doesn't give this agent or session is dropped; a kept one's `adopted`
        is the relay's answer, never the engine's. So no report can hand a tab, or put a handed one among the tabs
        closing the agent closes."""
        if self.brave is None or report.get("kind") not in ("tab_opened", "working_tab", "check"):
            return False
        if report.get("kind") == "check" and report.get("live") and _valid_check(report):
            report["adopted"] = False  # a bot check in QA's own sandbox (its live view): no tab of the user's Brave
            return False
        granted = self._granted(report["agent"], report.get("target"))
        if granted is None:
            return True
        report["adopted"] = granted == "handed"
        return False

    async def _engine_body(self, request: Request) -> tuple[dict | None, Response | None]:
        try:
            body = await request.json()
        except ValueError:
            return None, Response(status_code=400)
        if not isinstance(body, dict) or not isinstance(body.get("agent"), str):
            return None, Response(status_code=400)
        if not self._token_ok(request, body["agent"]):
            return None, Response(status_code=403)
        return body, None

    def _owner_of(self, agent_id: str, handed: bool = False) -> dict | None:
        """Who an id is, as AI Home's chips show it: an agent (or a tab handed to it), or a Claude Code session."""
        if SESSION_ID.match(agent_id):
            session = self.sessions.get(agent_id)
            return None if session is None else {"kind": "session", "id": agent_id, "name": session["name"],
                                                 "color": session["color"]}
        agent = self.agents.agents.get(agent_id)
        if agent is None:
            return None
        return {"kind": "handed" if handed else "agent", "id": agent.id, "name": agent.name, "color": agent.color}

    def _own(self, target: str, owner: dict | None) -> None:
        """Whose a tab of the user's Brave is, for AI Home (brave mode only)."""
        if self.brave is None or not target:
            return
        if owner is None:
            self.brave.forget(target)
        else:
            self.brave.set_owner(target, owner)

    def _record_tab(self, agent_id: str, target: str) -> None:
        if SESSION_ID.match(agent_id):
            tabs = self.sessions[agent_id]["tabs"]
            if target not in tabs:
                tabs.append(target)
                self._sessions_changed()
        else:
            self.agents.tab_event(agent_id, "tab_opened", target)

    def _session_report(self, session_id: str, report: dict) -> None:
        session, kind, target = self.sessions.get(session_id), report.get("kind"), report.get("target")
        if session is None or not isinstance(target, str) or not target:
            return
        if kind in ("tab_opened", "working_tab"):
            self._record_tab(session_id, target)
            self._own(target, self._owner_of(session_id))
            self._group_opened(session_id, target, report)
        elif kind == "tab_closed":
            if target in session["tabs"]:
                session["tabs"].remove(target)
                self._sessions_changed()
            self._own(target, None)

    def _after_agent_report(self, report: dict) -> None:
        """AI Home's chips follow an agent's tabs; a tab one of its pages opened joins its group."""
        agent_id, kind, target = report["agent"], report.get("kind"), report.get("target")
        if not isinstance(target, str) or not target or self.agents.agents.get(agent_id) is None:
            return
        if kind in ("tab_opened", "working_tab"):
            self._own(target, self._owner_of(agent_id, handed=bool(report.get("adopted"))))
            self._group_opened(agent_id, target, report)
        elif kind == "tab_closed":
            self._own(target, None)

    def _group_opened(self, owner_id: str, target: str, report: dict) -> None:
        opener, url = report.get("opener"), report.get("url")
        if report.get("kind") == "tab_opened" and isinstance(opener, str) and isinstance(url, str):
            owner = self._owner_of(owner_id)
            opener_tab = self.groups.tab_of(opener)
            if owner is not None and opener_tab is not None:
                self._job(self._group(owner_id, owner["name"], owner["color"], target,
                                      {"opener_tab": opener_tab, "url": url}))

    async def _group(self, key: str, title: str, color: str, target: str, find: dict) -> dict:
        answer = await self.groups.group(key, title, color, find)
        if answer.get("grouped") and isinstance(answer.get("tab"), int):
            self.groups.remember(target, answer["tab"])
        return answer

    async def _agent_claim(self, request: Request) -> Response:
        body, refused = await self._engine_body(request)
        if refused is not None:
            return refused
        agent_id, target = body["agent"], body.get("target")
        owner = self._owner_of(agent_id)
        if owner is None:
            return Response(status_code=404)
        if not isinstance(target, str) or not target:
            return Response(status_code=400)
        if self.brave is not None and self._granted(agent_id, target) is None:
            return JSONResponse({"grouped": False, "reason": "not_yours"})
        self._record_tab(agent_id, target)  # whatever happens to its group, the tab is this agent's or session's
        self._own(target, owner)
        if isinstance(body.get("marker"), str) and MARKER.match(body["marker"]):
            find = {"marker": body["marker"]}
        elif isinstance(body.get("opener"), str):
            opener_tab = self.groups.tab_of(body["opener"])
            if opener_tab is None:
                return JSONResponse({"grouped": False, "reason": "not_found"})
            find = {"opener_tab": opener_tab, "url": body["url"] if isinstance(body.get("url"), str) else ""}
        else:
            return Response(status_code=400)
        return JSONResponse(await self._group(agent_id, owner["name"], owner["color"], target, find))

    async def _agent_status(self, request: Request) -> Response:
        agent_id = request.query_params.get("agent", "")
        if not self._token_ok(request, agent_id):
            return Response(status_code=403)
        if self._owner_of(agent_id) is None:
            return Response(status_code=404)
        handed = []
        agent = self.agents.agents.get(agent_id)
        if agent is not None:
            listed = {tab["target"]: tab for tab in (self.brave.tabs() if self.brave is not None else [])}
            for target in agent.adopted:
                tab = listed.get(target, {})
                handed.append({"target": target, "title": tab.get("title", ""), "url": tab.get("url", "")})
        return JSONResponse({"groups": self.groups.available() == "on", "handed": handed})

    async def _agent_hello(self, request: Request) -> Response:
        body, refused = await self._engine_body(request)
        if refused is not None:
            return refused
        session_id, pid = body["agent"], body.get("pid")
        if not SESSION_ID.match(session_id) or not isinstance(pid, int):
            return Response(status_code=404)
        relay = self.brave.relay if self.brave is not None else None
        if relay is not None and relay.is_cut_off(session_id):
            return Response(status_code=410)  # the user disconnected it in AI Home: not listed again this run
        known = self.sessions.get(session_id)
        self.sessions[session_id] = {"id": session_id, "name": "Claude Code", "color": "orange",
                                     "tabs": known["tabs"] if known else [], "pid": pid}
        self._sessions_changed()
        if relay is not None:  # its key to /cdp, for this session id only
            return JSONResponse({"cdp_token": self.tokens.mint(session_id)})
        return Response(status_code=204)

    async def _agent_bye(self, request: Request) -> Response:
        body, refused = await self._engine_body(request)
        if refused is not None:
            return refused
        if body["agent"] not in self.sessions:
            return Response(status_code=404)
        await self._session_gone(body["agent"])
        return Response(status_code=204)

    async def _sweep_sessions(self) -> None:
        """Every SESSION_SWEEP seconds: a session whose process has ended leaves the list (it couldn't say bye)."""
        while True:
            await asyncio.sleep(SESSION_SWEEP)
            for session_id in [key for key, session in self.sessions.items() if not _alive(session["pid"])]:
                await self._session_gone(session_id)

    async def _session_gone(self, session_id: str) -> None:
        """A session said bye or its process ended: its own tabs still open close (Decision 11), it leaves the
        lists."""
        self.sessions.pop(session_id, None)
        if self.brave is not None:
            self.brave.release(session_id)
            with contextlib.suppress(Exception):
                await self.brave.relay.forget(session_id, close_tabs=True)
        self._sessions_changed()

    def _session_list(self) -> list[dict]:
        return [dict(session, tabs=list(session["tabs"])) for session in self.sessions.values()]

    def _sessions_changed(self) -> None:
        self._send_all({"type": "sessions", "sessions": self._session_list()})

    def attach_brave(self, brave) -> None:
        """Brave mode: the tab list, Watch, thumbnails and the browser card come from the user's Brave (BraveLink),
        and its relay carries every agent's and session's connection to it."""
        self.brave = brave
        self.attach_tabs(brave)
        relay = brave.relay
        relay.port = self.port or 0  # 0 until the server listens (the relay's own default)
        relay.handed = self._handed_to
        relay.may_open = lambda identity: bool(SESSION_ID.match(identity)) or self.agents.working(identity)
        self.agents.own_tabs = relay.own_targets
        relay.on_grant(lambda identity, target: self._own(target, self._owner_of(identity)))
        relay.on_change(self._clients_changed)
        brave.on_state(lambda state: self._browser_changed())
        self._browser_changed()
        self._send_all(self._tabs_message(brave.tabs()))  # pages already open see Brave's list at once

    def _handed_to(self, identity: str) -> set[str]:
        """The tabs the user handed this agent now (Hand over, or a task started in a tab): read live."""
        agent = self.agents.agents.get(identity)
        return set(agent.adopted) if agent is not None else set()

    def connect_brave(self, why: str = "connect", identity: str = "") -> None:
        """Connect to Brave now (Brave asks the user): only right after something the user did."""
        if self.brave is not None and self.brave.state in ("ready", "refused", "lost"):
            self._job(self.brave.connect(why, identity))

    async def _cdp(self, ws: WebSocket) -> None:
        """Brave mode: every agent's and session's connection to the user's Brave goes through the relay."""
        relay = getattr(self.brave, "relay", None)
        if relay is None or not hasattr(relay, "serve"):
            with contextlib.suppress(Exception):
                await ws.send_denial_response(PlainTextResponse("not found", status_code=404))
            return
        await relay.serve(ws)

    def _browser_clients(self) -> list[dict]:
        """AI Home's list of what uses the user's Brave through the app (the relay's rows, with names and colours).
        No token is in it."""
        if self.brave is None:
            return []
        rows = []
        for row in self.brave.relay.clients():
            if row.get("kind") == "app":
                rows.append({**row, "name": "AI Browser", "color": ""})
                continue
            owner = self._owner_of(row["id"]) or {}
            session = row.get("kind") == "session"
            rows.append({**row, "name": owner.get("name") or ("Claude Code" if session else row["id"]),
                         "color": owner.get("color") or ("orange" if session else "grey")})
        return rows

    def _clients_changed(self) -> None:
        self._send_all({"type": "browser_clients", "clients": self._browser_clients()})

    def _browser_info(self) -> dict:
        if self.brave is None:  # no BraveLink attached (a server built alone, in tests): agents can't browse yet
            return {"kind": "brave", "name": "Brave", "state": "off", "groups": self.groups.available()}
        return {"kind": "brave", "name": self.brave.name, "state": self.brave.state,
                "groups": self.groups.available()}

    def _browser_changed(self) -> None:
        self._send_all({"type": "browser", **self._browser_info()})

    def _handable(self, target: str | None) -> dict | None:
        """A tab of the user's Brave that may be handed to an agent: listed there, and nobody else's."""
        if self.brave is None or not target:
            return None
        return next((tab for tab in self.brave.tabs()
                     if tab["target"] == target and tab["owner"]["kind"] in ("you", "brain")), None)

    async def _brave_command(self, queue: asyncio.Queue, kind: str, message: dict) -> None:
        if kind == "brave_connect":
            self.connect_brave("connect")
        elif kind == "hand_tab":
            error = await self._hand(str(message.get("id", "")), message.get("target"))
            if error:
                queue.put_nowait({"type": "error", "text": error})
        elif kind == "take_back" and isinstance(message.get("target"), str):
            had = self.agents.take_back(message["target"])  # the agent it was handed to, or None
            if had is not None:  # only a handed tab: an agent's own tab is never the user's to take back
                self._own(message["target"], None)
                if self.brave is not None:  # its session on that tab ends now (Decision 6)
                    await self.brave.relay.cut(had, message["target"])
        elif kind == "browser_disconnect":
            client = message.get("id")
            if self.brave is not None and isinstance(client, str) and (AGENT_ID.match(client)
                                                                       or SESSION_ID.match(client)):
                await self.brave.relay.disconnect(client)  # a session stays listed until it ends (bye, the sweep)
                self._clients_changed()

    async def _hand(self, agent_id: str, target) -> str:
        """Hand over: the user's click gives one of their tabs to an agent; "" when done, else why not."""
        tab = self._handable(target if isinstance(target, str) else None)
        if tab is None:
            return "That tab can't be handed over: it is closed, or an agent or Claude Code already works in it"
        agent = self.agents.agents.get(agent_id)
        if agent is None:
            return "That agent has closed"
        self._own(target, self._owner_of(agent_id, handed=True))
        await self.agents.hand_tab(agent_id, target, {"url": tab["url"], "title": tab["title"]})
        self._job(self._group(agent.id, agent.name, agent.color, target, {"url": tab["url"]}))
        return ""

    def _ungroup(self, targets: list[str]) -> None:
        """Out of their group (a handed tab taken back, or let go when its agent closes): they're the user's again."""
        self.groups.ungroup([tab for tab in (self.groups.tab_of(target) for target in targets) if tab is not None])
        for target in targets:
            self._own(target, None)

    def _agent_report(self, report: dict) -> None:
        """An engine's report, read and authenticated: wave 1's check reports, then the tab report."""
        if isinstance(report, dict) and all(isinstance(report.get(key), str) for key in ("agent", "kind", "target")):
            if report["kind"] == "check":  # a bot check: only values from our own table and plain host names
                if _valid_check(report):
                    self.agents.check_event(report["agent"], report)
            elif report["kind"] == "check_cleared":
                if report.get("how") in ("solved", "closed"):
                    self.agents.check_cleared(report["agent"], report["target"], report["how"])
            else:
                self.agents.tab_event(report["agent"], report["kind"], report["target"], bool(report.get("adopted")))

    # ---- sockets ----------------------------------------------------------------------------------------------

    async def _socket(self, ws: WebSocket) -> None:
        await ws.accept()  # accept first, so a refusal arrives as a close code the page can read
        kind = self._socket_kind(ws)
        if kind is None:
            await ws.close(code=REFUSED)
            return
        self._roles[ws] = "watcher" if kind == "watcher" else "app"
        self._origin_of[ws] = ws.headers.get("origin", "")
        if kind == "window":
            self._windows.add(ws)
            self.window_seen = True
        queue: asyncio.Queue = asyncio.Queue()
        self._writers[ws] = asyncio.create_task(self._write(ws, queue))
        try:
            while True:
                try:
                    raw = await asyncio.wait_for(ws.receive_text(), PING_EVERY)
                except TimeoutError:
                    queue.put_nowait({"type": "ping"})
                    continue
                try:
                    message = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(message, dict):
                    await self._handle(ws, queue, message)
        except WebSocketDisconnect:
            pass
        finally:
            self._unsubscribe(ws)

    async def _write(self, ws: WebSocket, queue: asyncio.Queue) -> None:
        """Every message to a socket passes here (answers, _send_all, _to_watcher), so a path added later is covered:
        a watcher-origin socket gets only for_watcher's part of each."""
        watcher = self._role(ws) != "app"  # read once (set at accept): all but our own pages get the watcher's part
        with contextlib.suppress(Exception):
            while True:
                message = await queue.get()
                if watcher:
                    message = for_watcher(message)
                    if message is None:
                        continue
                await ws.send_json(message)

    def _unsubscribe(self, ws: WebSocket) -> None:
        self._sockets.pop(ws, None)
        self._origin_of.pop(ws, None)
        self._roles.pop(ws, None)
        self._windows.discard(ws)
        if self.hearing is not None:
            self.hearing.drop(ws)  # a closed page's turn, and its audio, go with it
        writer = self._writers.pop(ws, None)
        if writer is not None:
            writer.cancel()
        if self._watcher is not None and self._watcher[0] is ws:
            self._watcher = None
            self.groups.watcher_changed(False)
            if self.brain is not None:
                self.brain.watcher = False

    def _send_all(self, message: dict) -> None:
        for queue in self._sockets.values():
            queue.put_nowait(message)

    def _to_watcher(self, message: dict) -> bool:
        """A message for Brave's watcher; False when it isn't connected."""
        if message.get("type") == "open_thread" and isinstance(message.get("url"), str):
            self._thread_urls[str(message.get("request", ""))] = message["url"]
        if self._watcher is None:
            return False
        self._watcher[1].put_nowait(message)
        return True

    async def _forward(self) -> None:
        while True:
            message = await self._feed.get()
            if message.get("type") == "agent_closed":
                agent_id = str(message.get("id"))
                self._thumbs.pop(agent_id, None)
                self.tokens.revoke(agent_id)  # its engine's next connect hears "disconnected" (410)
                if self.brave is not None:
                    self.brave.release(agent_id)
                    with contextlib.suppress(Exception):
                        await self.brave.relay.forget(agent_id)
            self._send_all(message)
            if message.get("type") in ("permission_request", "check_request"):
                self._to_watcher(message)  # a Brave notification too

    def _job(self, coroutine) -> None:
        task = asyncio.ensure_future(coroutine)
        self._jobs.add(task)
        task.add_done_callback(self._jobs.discard)

    def _role(self, ws: WebSocket) -> str:
        """The role stored when the socket was accepted: "app" (AI Browser's window, its cookie, Origin and Host; or,
        until it retires, AI Browser's extension) or "watcher" (Brave's watcher: the token and a watcher origin). A
        socket with no stored role is "none": it may send nothing (may_send), and gets no more than a watcher."""
        return self._roles.get(ws, "none")

    async def _handle(self, ws: WebSocket, queue: asyncio.Queue, message: dict) -> None:
        if not may_send(self._role(ws), message):  # MESSAGE_RULES, before anything reads the message's fields
            return  # dropped, with no answer: a page can't map the table by trying types
        kind, agent_id, agents = message["type"], str(message.get("id", "")), self.agents
        if kind == "hello" and message.get("view") == "watcher" and self.brain is not None \
                and self._role(ws) == "watcher":
            self._watcher = (ws, queue)  # the latest watcher wins (a reloaded extension connects again)
            queue.put_nowait({"type": "watcher_hello", "build": self.watcher_build})
            queue.put_nowait(self.brain.watch_message())
            self.brain.store.set_watcher_seen()
            self.brain.watcher = True
            self.groups.watcher_changed(True)
        elif kind in WATCHER_MESSAGES:
            if self.brain is not None and self._watcher is not None and self._watcher[0] is ws:
                await self._from_watcher(kind, message)
        elif kind in BRAIN_MESSAGES:
            if self.brain is not None:  # a card's Start and Cancel are AI Browser's own (MESSAGE_RULES): the
                # watcher may ask for a card (tell), never run one, and its typed yes is only a question
                await self._brain_command(queue, kind, agent_id, message, from_watcher=self._role(ws) == "watcher")
        elif kind in TOOLS_MESSAGES:
            self._tools_command(queue, kind, message)
        elif kind in WORKFLOW_MESSAGES:
            if self.workflows is not None and self.runner is not None:
                await self._workflow_command(queue, kind, message)
        elif kind in SKILL_MESSAGES:
            if self.skill_writer is not None and kind == "skill_draft":
                self._job(self._skill_draft(queue, message))  # a Claude call: the socket goes on meanwhile
            elif self.skill_writer is not None:
                self._skill_save(queue, message)
        elif kind in CHECK_MESSAGES:  # a bot check's buttons; MESSAGE_RULES lets the watcher Continue, never Skip
            if kind == "check_continue":
                await agents.continue_check(agent_id)
            elif kind == "check_skip":
                await agents.skip_check(agent_id)
            elif kind == "check_show":
                await self._show_check(agent_id)
        elif kind in BRAVE_MESSAGES:  # AI Browser's own pages only (MESSAGE_RULES)
            await self._brave_command(queue, kind, message)
        elif kind in HEARING_MESSAGES:  # only AI Browser's own pages talk or listen (MESSAGE_RULES)
            self._hearing_command(ws, queue, kind, message)
        elif kind in TALK_MESSAGES:
            self._talk_command(queue, kind, message)
        elif kind == "hello":
            if ws not in self._sockets:  # the snapshot, then every broadcast (no await between the two)
                queue.put_nowait(self._snapshot())
                self._sockets[ws] = queue
        elif kind == "settings_set":
            self._settings_set(queue, message)
        elif kind == "open_url":
            self._job(self._open_url(queue, message))
        elif kind == "ai_keyword":
            await self._keyword(queue, message)
        elif kind == "new_task":
            request = message.get("request") if isinstance(message.get("request"), (str, int)) else None
            text = _text(message.get("text"))
            if not text:
                queue.put_nowait({"type": "error", "text": "Write what the agent should do", "request": request})
                return
            skills = [skill for skill in message.get("skills") or [] if isinstance(skill, str)][:20]
            adopt = message.get("adopt") if isinstance(message.get("adopt"), str) and message.get("adopt") else None
            handed = self._handable(adopt) if adopt else None
            if adopt and handed is None:  # only a tab the user's browser lists: never an unchecked target
                queue.put_nowait({"type": "error", "request": request,
                                  "text": "That tab can't be handed over: it is closed, or an agent works in it"})
                return
            model = message.get("model") if message.get("model") in MODELS else self.default_model
            agent = await agents.create(text, skills, model, adopt, _tab(message.get("tab")))
            if handed is not None:
                self._own(adopt, self._owner_of(agent.id, handed=True))
                self._job(self._group(agent.id, agent.name, agent.color, adopt, {"url": handed["url"]}))
            queue.put_nowait({"type": "created", "id": agent.id, "request": request})
        elif kind == "send":
            text = _text(message.get("text"))
            if text:
                await agents.send(agent_id, text, _tab(message.get("tab")))
        elif kind == "stop":
            await agents.stop(agent_id)
        elif kind == "close":
            self._job(agents.close(agent_id))  # it may wait for the agent's turn to end
        elif kind == "model" and message.get("model") in MODELS:
            agents.set_model(agent_id, message["model"])
        elif kind == "watch" and self.tabs is not None and isinstance(message.get("target"), str):
            await self.tabs.watch(message["target"])
        elif kind == "events":
            queue.put_nowait({"type": "agent_events", "id": agent_id, "events": agents.events_of(agent_id)})
        elif kind == "skills":
            queue.put_nowait({"type": "skills", "skills": self._skill_list()})
        elif kind == "thumbs":  # a page opened later: the latest picture of each agent's tab
            queue.put_nowait({"type": "thumbs", "thumbs": {
                agent: state["jpeg"] for agent, state in self._thumbs.items()
                if state.get("jpeg") and agent in self.agents.agents}})

    async def _show_check(self, agent_id: str) -> None:
        """Show me, from Brave's notification: bring forward the tab where this agent's bot check waits. The app holds
        that tab, so no page names one. A check shown in the live view (QA's sandbox) has no tab here, and without a
        tab source nothing happens. It uses the link's one connection and never opens one."""
        agent = self.agents.agents.get(agent_id)
        check = agent.check if agent is not None else None
        if check is None or check.get("live") or not check.get("target") or self.tabs is None:
            return
        await self.tabs.watch(check["target"])

    async def _from_watcher(self, kind: str, message: dict) -> None:
        if kind == "watcher_caps":
            self.groups.caps_from(message)
            return
        if kind == "tab_grouped":
            self.groups.answered(message)
            return
        brain = self.brain
        site = message.get("site") if isinstance(message.get("site"), str) else ""
        if kind == "items":
            await brain.on_items(site, message.get("items"), baseline=message.get("baseline") is True)
        elif kind == "replied" and isinstance(message.get("id"), str):
            brain.on_replied(site, message["id"])
        elif kind == "thread":
            if brain is not None:
                brain.on_thread(str(message.get("request", "")), message.get("text") or "", message.get("error") or "")
            url = self._thread_urls.pop(str(message.get("request", "")), None)
            if url is not None and self.brave is not None:
                self.brave.mark_brain(url)  # display only: "Brain" on that row
        elif kind == "filled":
            brain.on_filled(str(message.get("request", "")), message.get("ok") is True, _text(message.get("reason")))
        elif kind == "reader_status":
            brain.reader_status(site, message.get("ok") is True, _text(message.get("note")))

    async def _brain_command(self, queue: asyncio.Queue, kind: str, item_id: str, message: dict,
                             from_watcher: bool = False) -> None:
        brain = self.brain
        if kind == "brain":
            queue.put_nowait({"type": "brain_snapshot", **brain.snapshot()})
        elif kind == "draft":
            self._job(brain.draft(item_id))
        elif kind == "approve":
            await brain.approve(item_id, message.get("text"), message.get("version"))
        elif kind == "hand":
            self._job(brain.hand(item_id, _text(message.get("instruction"))))
        elif kind == "done":
            brain.done(item_id)
        elif kind == "tell":  # proposal and task: the item's open card, as its box now reads
            proposal = message.get("proposal") if isinstance(message.get("proposal"), str) else None
            self._job(brain.tell(item_id, _text(message.get("text")), proposal=proposal,
                                 task=_text(message.get("task")) or None, from_watcher=from_watcher))
        elif kind == "tell_confirm" and isinstance(message.get("proposal"), str):
            self._job(brain.confirm_tell(item_id, message["proposal"], _text(message.get("task")) or None))
        elif kind == "tell_dismiss" and isinstance(message.get("proposal"), str):
            brain.dismiss_tell(item_id, message["proposal"])
        elif kind == "watch_set":
            error = brain.set_watch({key: message[key] for key in WATCH_FIELDS if key in message})
            if error:
                queue.put_nowait({"type": "error", "text": error, "request": message.get("request")})
        elif kind == "watch_remove" and isinstance(message.get("site"), str):
            brain.remove_watch(message["site"])
        elif kind == "pause":
            brain.set_paused(message.get("on") is True)
        elif kind == "style":
            brain.set_style(_text(message.get("text")))

    # ---- talking to the Brain: push-to-talk turns and the talk (AI Browser's own pages only) ----------------------

    def _hearing_command(self, ws: WebSocket, queue: asyncio.Queue, kind: str, message: dict) -> None:
        hearing = self.hearing
        if kind == "hearing":
            queue.put_nowait({"type": "hearing_status", **(hearing.status() if hearing else unavailable_status())})
            return
        if hearing is None:
            return
        turn = message.get("turn") if isinstance(message.get("turn"), str) else ""
        if kind == "hearing_download":  # only the Download button sends it: the one way the model is fetched
            hearing.start_download()
        elif kind == "hearing_cancel":
            hearing.cancel_download()
        elif kind == "listen_start":
            self._heard_error(queue, turn, hearing.begin(ws, turn))
        elif kind == "listen_chunk":
            self._heard_error(queue, turn, hearing.add(ws, turn, message.get("seq"), message.get("pcm")))
        elif kind == "listen_end":
            self._job(self._listen_end(ws, queue, turn))  # the words take a moment: the socket reads on meanwhile
        elif kind == "listen_cancel":
            hearing.cancel(ws, turn)

    @staticmethod
    def _heard_error(queue: asyncio.Queue, turn: str, error: str) -> None:
        if error:  # to the asking page only: its turn ended
            queue.put_nowait({"type": "heard", "turn": turn[:40], "error": error})

    async def _listen_end(self, ws: WebSocket, queue: asyncio.Queue, turn: str) -> None:
        text, error = await self.hearing.finish(ws, turn)
        queue.put_nowait({"type": "heard", "turn": turn[:40], **({"error": error} if error else {"text": text})})

    def _talk_command(self, queue: asyncio.Queue, kind: str, message: dict) -> None:
        talk = message.get("talk")
        if not isinstance(talk, str) or not _TALK_ID.match(talk):
            return
        request = message.get("request") if isinstance(message.get("request"), (str, int)) else None
        if self.brain is None:
            if kind != "brain_dismiss":
                queue.put_nowait({"type": "brain_answer", "talk": talk, "request": request, "say": "",
                                  "error": "The Brain isn't running"})
            return
        proposal = message.get("proposal") if isinstance(message.get("proposal"), str) else None
        task = _text(message.get("task")) or None  # the card's box, as the user left it
        model = message.get("model") if message.get("model") in MODELS else None
        if kind == "brain_ask":
            text = message.get("text").strip()[:2000] if isinstance(message.get("text"), str) else ""
            if text:
                self._job(self._answer(queue, talk, request,
                                       self.brain.respond(talk, text, proposal=proposal, task=task, model=model)))
        elif kind == "brain_confirm" and proposal is not None:
            self._job(self._answer(queue, talk, request, self.brain.confirm(talk, proposal, task=task, model=model)))
        elif kind == "brain_dismiss" and proposal is not None:
            self.brain.dismiss(talk, proposal)

    @staticmethod
    async def _answer(queue: asyncio.Queue, talk: str, request, answering) -> None:
        """The Brain's answer, to the asking page only; an agent it started is `created` there first. If it breaks, the
        page is still answered (in plain words, never the error's own), so it never waits forever."""
        try:
            answer = await answering
        except Exception:  # a newer question's cancel is not an Exception: that answer is never given
            answer = {"say": "", "error": "The Brain couldn't answer"}
        if answer.get("agent"):
            queue.put_nowait({"type": "created", "id": answer["agent"], "request": request})
        queue.put_nowait({"type": "brain_answer", "talk": talk, "request": request,
                          **{key: value for key, value in answer.items() if key != "agent"}})

    def _tools_command(self, queue: asyncio.Queue, kind: str, message: dict) -> None:
        if kind == "permission":  # only a click in one of our pages answers a tool request
            if all(isinstance(message.get(key), str) for key in ("agent", "request", "answer")):
                self.agents.answer_permission(message["agent"], message["request"], message["answer"])
            return
        tools = self.tools
        if tools is None:
            return
        if kind == "tools":
            queue.put_nowait(self._tools_snapshot())
            if message.get("refresh") is True:
                self._job(self.probe_tools())
            return
        if kind == "tool_set" and isinstance(message.get("server"), str):
            tools.set_enabled(message["server"], message.get("on") is True)
        elif kind == "tool_allow" and isinstance(message.get("tool"), str):
            tools.allow_always(message["tool"])
        elif kind == "tool_forget" and isinstance(message.get("tool"), str):
            tools.forget(message["tool"])
        else:
            return
        self._send_all(self._tools_snapshot())

    async def probe_tools(self) -> None:
        """Which claude.ai connectors Claude Code loads for the user now (and their tools)."""
        if self.tools is not None and await self.tools.probe(self.agents.claude):
            self._send_all(self._tools_snapshot())

    async def _workflow_command(self, queue: asyncio.Queue, kind: str, message: dict) -> None:
        request = message.get("request") if isinstance(message.get("request"), (str, int)) else None
        try:
            if kind == "workflows":
                queue.put_nowait(self._workflows_snapshot())
            elif kind == "workflow_save":
                workflow = self.workflows.save({key: message[key] for key in WORKFLOW_FIELDS if key in message})
                queue.put_nowait({"type": "workflow_saved", "request": request, "slug": workflow.slug,
                                  "path": str(self.workflows.path_of(workflow.slug))})
                self.workflows_changed()
            elif kind == "workflow_delete" and isinstance(message.get("slug"), str):
                self.workflows.delete(message["slug"])
                self.workflows_changed()
            elif kind == "workflow_run" and isinstance(message.get("slug"), str):
                if isinstance(message.get("item"), str):  # the inbox's Run on a message: only through the Brain,
                    if self.brain is None:                # never a bare run in its place
                        return
                    agent_id = await self.brain.run_workflow(message["item"], message["slug"])
                else:
                    agent_id = await self.runner.run(message["slug"], text=_text(message.get("text")) or None)
                queue.put_nowait({"type": "created", "id": agent_id, "request": request})
        except ValueError as exc:
            queue.put_nowait({"type": "error", "text": str(exc), "request": request})

    async def _skill_draft(self, queue: asyncio.Queue, message: dict) -> None:
        request = message.get("request") if isinstance(message.get("request"), (str, int)) else None
        writer = self.skill_writer
        try:
            if isinstance(message.get("from_agent"), str):  # Save as skill, from a finished agent's chat
                events = self.agents.events_of(message["from_agent"])
                if not events:
                    raise ValueError("That agent has no conversation to learn from")
                name, text = await writer.from_run(events)
            else:  # Train a new agent
                description = _text(message.get("description"))
                if not description:
                    raise ValueError("Write what the agent should do")
                page = ""
                if isinstance(message.get("page_target"), str) and self.tabs is not None:
                    page = await self.tabs.page_text(message["page_target"], picked=True)
                name, text = await writer.from_description(description, _text(message.get("examples")), page)
            queue.put_nowait({"type": "skill_drafted", "request": request, "name": name, "text": text})
        except (ValueError, SkillError) as exc:
            queue.put_nowait({"type": "error", "request": request, "text": str(exc)})

    def _skill_save(self, queue: asyncio.Queue, message: dict) -> None:
        """Save writes a new skill; Update first answers with the diff, and writes only with confirm."""
        request = message.get("request") if isinstance(message.get("request"), (str, int)) else None
        writer, text = self.skill_writer, message.get("text")
        try:
            if message.get("update") is True and message.get("confirm") is not True:
                name = writer.check(text)
                queue.put_nowait({"type": "skill_diff", "request": request, "name": name, "diff": writer.diff(text)})
                return
            path = writer.update(text) if message.get("update") is True else writer.save(text)
            queue.put_nowait({"type": "skill_saved", "request": request, "name": path.parent.name})
        except FileExistsError:
            name = writer.check(text)
            suggest = writer.free_name(name)
            queue.put_nowait({"type": "error", "request": request, "exists": name, "suggest": suggest,
                              "text": f"A skill named {name} already exists: save this one as {suggest}, or Update "
                                      "the existing one"})
        except ValueError as exc:
            queue.put_nowait({"type": "error", "request": request, "text": str(exc)})

    def skills_changed(self, name: str = "") -> None:
        """A skill was saved: read the skills again and show them at once."""
        self._catalog = None
        self._send_all({"type": "skills", "skills": self._skill_list()})

    def workflows_changed(self) -> None:
        if self.workflows is not None:
            self._send_all(self._workflows_snapshot())

    def _workflows_snapshot(self) -> dict:
        workflows = [{**workflow.public(), "path": str(self.workflows.path_of(workflow.slug)),
                      "note": self.runner.notes.get(workflow.slug, "") if self.runner else ""}
                     for workflow in self.workflows.all()]
        return {"type": "workflows_snapshot", "workflows": workflows, "problems": self.workflows.problems()}

    def _tools_snapshot(self) -> dict:
        return {"type": "tools_snapshot", "servers": self.tools.servers(), "always": sorted(self.tools.always())}

    def _snapshot(self) -> dict:
        return {"type": "snapshot", "agents": self.agents.snapshot()["agents"],
                "tabs": self.tabs.tabs() if self.tabs is not None else [],
                "tab_scope": self._tab_scope(),
                "skills_summary": self._skills_summary(), "max_working": self.agents.max_working,
                "default_model": self.default_model, "browser": self._browser_info(),
                "sessions": self._session_list(), "browser_clients": self._browser_clients(),
                "settings": self._settings_payload()}

    # ---- skills -----------------------------------------------------------------------------------------------

    def _skills(self) -> list:
        if self._catalog is None:  # the same skills the agents' engines see
            self._catalog = Catalog.discover(Path.home() / ".claude",
                                             platforms.claude_desktop_dir(),
                                             project_root() / "skills", set(load_config(self.home).blocked_skills))
        return self._catalog.all()

    def _skills_summary(self) -> dict:
        by_source: dict[str, int] = {}
        skills = self._skills()
        for skill in skills:
            source = SOURCES.get(skill.namespace, "plugins")
            by_source[source] = by_source.get(source, 0) + 1
        return {"total": len(skills), "by_source": by_source}

    def _skill_list(self) -> list[dict]:
        return [{"ref": skill.ref, "name": skill.name, "namespace": skill.namespace,
                 "source": SOURCES.get(skill.namespace, "plugins"), "description": _first_line(skill.description)}
                for skill in self._skills()]

    # ---- thumbnails -------------------------------------------------------------------------------------------

    def _on_action(self, agent: Agent) -> None:
        """After an agent's action: a thumbnail of its tab now, or when THUMB_EVERY seconds have passed."""
        state = self._thumbs.setdefault(agent.id, {"last": 0.0, "task": None, "again": False})
        if state["task"] is not None and not state["task"].done():
            state["again"] = True
            return
        state["task"] = asyncio.ensure_future(self._thumb(agent.id, state))

    async def _thumb(self, agent_id: str, state: dict) -> None:
        while True:
            wait = state["last"] + THUMB_EVERY - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            state["again"], state["last"] = False, time.monotonic()
            agent = self.agents.agents.get(agent_id)
            if agent is None or agent.working_tab is None or self.tabs is None:
                return
            shot = await self.tabs.thumbnail(agent.working_tab)
            if agent_id not in self.agents.agents:
                return  # closed while the picture was being taken
            if shot:
                state["jpeg"] = base64.b64encode(shot).decode()  # the latest, for a page opened later
                self._send_all({"type": "thumb", "id": agent_id, "jpeg": state["jpeg"]})
            if not state["again"]:
                return
