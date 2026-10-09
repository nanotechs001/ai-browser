"""The AI Browser app server: Mission Control's, Settings' and the floating chat's only way to the agents.

It listens on 127.0.0.1 only, and every route checks the Host header. AI Browser's pages are served here to its own
window, which swaps a one-time code for an HttpOnly cookie and lands on its tab menu (/app); the menu shows our other
pages in frames, and only it may frame them. A window socket needs that cookie and our exact Origin and Host, and the
pages in the menu's frames are the window's sockets: no other socket is taken. The agents' engines report their tabs
to /agent-events with tokens of their own, and reach the browser through /cdp. Everything that happens to an agent is
broadcast to every socket; an agent's conversation is sent on request (`events`), so a page opened later can draw it
whole."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hmac
import html
import json
import re
import secrets
import sys
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

from .. import browsers, debugstart, platforms
from ..accounts import Accounts
from ..brain import sites
from ..brain.inbox import InboxReader
from ..brain.service import BrainService, source_of
from ..brain.skillwriter import SkillError, SkillWriter
from ..brain.store import built_in
from ..brain.talk import PAGE_TEXT_LIMIT
from ..brain.tools import ToolsConfig
from ..brain.workflows import WorkflowRunner, WorkflowStore
from ..checks import KINDS
from ..chrome import own_browser_dir
from ..claudecli import claude_argv
from ..config import LIVE_PORTS, load_config, project_root, set_blocked
from ..desktop import layout
from ..desktop.notes import note_for
from ..desktop.release import asset_for, setup_command
from ..desktop.release import VERSION as ELECTRON_VERSION
from ..desktop.shortcut import SHORTCUT_ERROR, SHORTCUTS
from ..desktop.shortcut import label as shortcut_label
from ..desktop.shortcut import state as shortcut_state
from ..engine import _alive
from ..hearing.service import HearingService, unavailable_status
from ..live import _bind, _QuietServer, _serve
from ..settings import Settings
from ..skills import Catalog
from ..syncdir import write_atomic
from . import attachments
from . import pagematch
from . import powers
from .agents import CLOSED, Agent, AgentManager
from .bravelink import NOT_CONNECTED, NOT_OPEN, PlaceError
from .inworld import WorldError
from .savedagents import BAD_ACCOUNT, BAD_PROFILE, NOT_AN_AGENT, SavedAgents
from .workspaces import GONE as WORKSPACE_GONE
from .workspaces import Workspaces, one_line
from .cdprelay import Tokens

APP_PORTS = range(8792, 8812)
MODELS = {"opus", "sonnet", "haiku"}
REFUSED = 4403  # WebSocket close code for a wrong token or origin
PING_EVERY = 20  # seconds: a message now and then keeps a page's socket alive
THUMB_EVERY = 2  # seconds between two thumbnails of one agent's tab
TEXT_LIMIT = 20_000  # characters of a task or a message
BRAIN_MESSAGES = {"brain", "draft", "approve", "hand", "done", "tell", "watch_set", "watch_remove", "style",
                  "tell_confirm", "tell_dismiss", "handoff_send", "handoff_cancel"}
HANDOFF_VIEWS = frozenset({"mission", "chat"})  # the pages that show the Brain's hand-off cards
HOLD_AFTER = 0.3  # seconds without a page that can show a card before every countdown holds (a tab switch is quicker)
TOOLS_MESSAGES = {"tools", "tool_set", "tool_allow", "tool_forget", "permission"}
WORKFLOW_MESSAGES = {"workflows", "workflow_save", "workflow_delete", "workflow_run"}
SKILL_MESSAGES = {"skill_draft", "skill_save"}
HEARING_MESSAGES = {"hearing", "hearing_download", "hearing_cancel", "listen_start", "listen_chunk", "listen_end",
                    "listen_cancel"}  # push-to-talk
TALK_MESSAGES = {"brain_ask", "brain_confirm", "brain_dismiss"}  # the talk with the Brain
_TALK_ID = re.compile(r"^[A-Za-z0-9-]{1,40}$")
CHECK_MESSAGES = {"check_continue", "check_skip", "check_show"}  # a bot check's buttons (who may: MESSAGE_RULES)
BRAVE_MESSAGES = {"brave_connect", "hand_tab", "take_back", "browser_disconnect"}  # only AI Browser's own pages
CHECK_SITE = re.compile(r"[a-z0-9.-]{1,253}")  # a host name, nothing else
CHECK_LIVE = re.compile(r"http://127\.0\.0\.1:\d{1,5}/live\?token=[A-Za-z0-9_-]{1,64}")  # an engine's live view
WORKFLOW_FIELDS = ("slug", "name", "instructions", "trigger", "site", "when", "schedule", "run", "tools", "skills",
                   "model", "runs_as")
WATCH_FIELDS = ("site", "label", "url_match", "selector", "instructions", "enabled")
UI = Path(__file__).with_name("ui")  # AI Browser's pages, served to its window only
SETUP_PAGE = UI / "setup.html"
SHELL = "/app"  # the window's own page: the tab menu, which shows the others in frames
PAGES = {SHELL: "app.html", "/mission": "mission.html", "/settings": "settings.html",
         "/chat": "chat.html"}  # /chat: the floating chat, in a window of its own (nothing frames it)
FRAMED = frozenset({"/mission", "/settings", "/setup"})  # the pages the tab menu shows: only it frames them
OLD_HOME = "/home"  # the old home page's address (the saved-agents spec, 6): a bookmark of it opens Mission Control
LIVE_VIEWS = " ".join(f"http://127.0.0.1:{port}" for port in LIVE_PORTS)  # an engine's live view binds one of these
FILE_TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".png": "image/png"}
OPEN_ANYWHERE = {"setup.js", "setup.css", "icon.png", "theme.css"}  # the setup page's own files: it opens in Brave too
CODE_TTL = 60  # seconds a one-time start code is good for
PICK_WAIT = 120.0  # seconds a pick may take: the user points and clicks in Brave
PICK_OFF = "Turn on Read my Gmail, Slack and Asana tabs first"
PICK_TAB = "Pick one of your open tabs in Brave"
# watcher_note: Settings → Brave's Got it; read_tabs, brain_sources and auto_hand: Settings → Brain's switch, checkboxes
# and hand-off switch
SETTING_KEYS = ("model", "voice", "window_browser", "shortcut", "watcher_note", "read_tabs", "agents_profile",
                "brain_sources", "auto_hand")
CHAT_OFF = "The Brain isn't listening to the floating chat: check it in Settings → Brain"
NOTES_KEPT = 50  # the app's notifications whose click is still answered
PLATFORM_WORDS = {"darwin": "mac", "win32": "windows"}  # the pages say "the menu bar" or "by the clock"
APP_SILENT = "AI Browser's app didn't answer: try again"
CHAT_NOT_CONNECTED = ("Brave isn't connected to AI Browser, so the chat can't read that page: connect it at the top of "
                      "Mission Control")
CHAT_PAGE_CHANGED = "That tab went to another site before AI Browser read it, so nothing was sent: ask again"
URL_LIMIT = 2000  # characters of a website address a page may ask the user's browser to open
NOT_HERE = "AI Browser's pages open only in its own window. Start it {how}."  # not_here()
USED_CODE = "This start link was used already or has expired. Start AI Browser again."
SOURCES = {"personal": "personal", "anthropic-skills": "claude.ai", "ai-browser": "ai-browser"}  # else: plugins
SESSION_ID = re.compile(r"^cc-[0-9a-z-]{1,40}$")  # a Claude Code session's id (cc-<task id>)
AGENT_ID = re.compile(r"^a[0-9]{1,9}$")  # an agent's id (a<number>)
SKILL_REF = re.compile(r"^[A-Za-z0-9_.-]{1,100}:[A-Za-z0-9_.-]{1,100}$")  # a skill's ref (namespace:name)
SESSION_SWEEP = 30  # seconds between two looks at the sessions' processes
ACCOUNT_MESSAGES = {"accounts", "account_add", "account_add_existing", "account_remove", "account_default",
                    "account_brain", "account_signin", "account_move"}  # AI accounts: AI Browser's own pages only
POWERS_MESSAGES = {"folder_choose", "folder_trust", "permission_rules", "permission_rule_remove"}  # agent powers
WORKSPACE_MESSAGES = {"workspaces", "workspace_save", "workspace_delete", "workspace_assign"}  # the new look
ATTACH_MESSAGES = {"attach_start", "attach_chunk", "attach_drop"}  # the new look's Attach: a file in pieces
SAVED_MESSAGES = {"saved_agents", "saved_agent_save", "saved_agent_delete"}  # the Agents page: our own pages only
SAVED_FIELDS = ("slug", "name", "description", "instruction", "profile", "web", "model", "effort", "account",
                "folder", "auto_approve", "can_use", "load_at_start")
SIGNIN_EVERY = 5  # seconds between two looks at an account the user is signing in
SIGNIN_WAIT = 600  # seconds the app keeps looking
IN_USE = "{name} is in use by {label}: move or close that agent first"
NOT_LEARNED = ("Agent {number} browses in Brave's {name} profile. Open a window of that profile once; AI Browser learns "
               "it in about 30 seconds.")  # the user's words on the run (Claude hears bravelink's NOT_OPEN)
EMPTY_MESSAGE = "Write a message, or attach a file"
YOU = {"kind": "you"}


@dataclass(frozen=True)
class Rule:
    """Who may send one message type: AI Browser's own pages ("app"). Brave's watcher, the one other role there was,
    retired with its extension."""
    app: bool = True


APP_ONLY = Rule()

# Every message type a page may send (watcher-safety Decision 1, for AI Browser's own pages alone now). A type missing
# here is dropped, with no answer. tests/test_watcher_rules.py holds a copy: a row added here fails there until the
# copy says the same.
MESSAGE_RULES: dict[str, Rule] = {
    "hello": APP_ONLY,
    "visibility": APP_ONLY,  # the Brain's hand-offs (2026-10-08): a page shown or hidden (link.js)
    # the Brain's inbox, in Mission Control and Settings
    "brain": APP_ONLY, "draft": APP_ONLY, "approve": APP_ONLY, "hand": APP_ONLY, "done": APP_ONLY,
    "tell": APP_ONLY, "watch_set": APP_ONLY, "watch_remove": APP_ONLY, "style": APP_ONLY,
    "watch_pick": APP_ONLY,  # Settings → Brain: Pick the part to watch, on the user's click
    "workflow_run": APP_ONLY,
    "workflows": APP_ONLY, "workflow_save": APP_ONLY, "workflow_delete": APP_ONLY,
    "permission": APP_ONLY,
    "tools": APP_ONLY, "tool_set": APP_ONLY, "tool_allow": APP_ONLY, "tool_forget": APP_ONLY,
    "skills": APP_ONLY, "skill_draft": APP_ONLY, "skill_save": APP_ONLY,
    "hearing": APP_ONLY, "hearing_download": APP_ONLY, "hearing_cancel": APP_ONLY, "listen_start": APP_ONLY,
    "listen_chunk": APP_ONLY, "listen_end": APP_ONLY, "listen_cancel": APP_ONLY,
    "brain_ask": APP_ONLY, "brain_confirm": APP_ONLY, "brain_dismiss": APP_ONLY,
    "tell_confirm": APP_ONLY, "tell_dismiss": APP_ONLY,  # brain-delegation: a card runs only from our own pages
    # the Brain's hand-offs (2026-10-08): Send now, Send, Start and Cancel on a card, the user's click on our pages
    "handoff_send": APP_ONLY, "handoff_cancel": APP_ONLY,
    "check_continue": APP_ONLY, "check_skip": APP_ONLY, "check_show": APP_ONLY,
    "brave_connect": APP_ONLY, "hand_tab": APP_ONLY, "take_back": APP_ONLY,
    "browser_disconnect": APP_ONLY,  # cdp-relay: Disconnect in Settings → Brave's list
    "new_task": APP_ONLY,  # with or without adopt
    # send: the user's message to an agent, with the files a page staged (the drawer's chat): a file, never a right
    "send": APP_ONLY, "stop": APP_ONLY, "close": APP_ONLY, "model": APP_ONLY,
    "watch": APP_ONLY, "events": APP_ONLY, "thumbs": APP_ONLY,
    "settings_set": APP_ONLY,  # the window's Settings and Mission Control's picks
    "open_url": APP_ONLY,  # a website link in one of our pages
    # the floating chat (native-app part c): "This page" as AI Browser's own app read it, and Open Mission Control
    "this_page": APP_ONLY, "show_app": APP_ONLY,
    # AI accounts: Settings → Accounts, the Account pickers and Continue on. The Brain and voice never add, sign in,
    # choose or move (the spec's Safety)
    "accounts": APP_ONLY, "account_add": APP_ONLY, "account_add_existing": APP_ONLY, "account_remove": APP_ONLY,
    "account_default": APP_ONLY, "account_brain": APP_ONLY, "account_signin": APP_ONLY, "account_move": APP_ONLY,
    # agent powers: the Folder picker's check and "Trust this folder?", and Settings → Permissions (its list, Remove).
    # A trust answer or a rule's removal is the user's click on one of our pages: never the Brain or voice
    "folder_choose": APP_ONLY, "folder_trust": APP_ONLY, "permission_rules": APP_ONLY,
    "permission_rule_remove": APP_ONLY,
    # the new look: Mission Control's workspaces, named groups of agents and templates. A filter: no new right
    "workspaces": APP_ONLY, "workspace_save": APP_ONLY, "workspace_delete": APP_ONLY, "workspace_assign": APP_ONLY,
    # the new look's Attach: a page sends a file in pieces, for a task it starts. A file, never a right
    "attach_start": APP_ONLY, "attach_chunk": APP_ONLY, "attach_drop": APP_ONLY,
    # the new look's Knowledge: Remove hides a skill from AI Browser's agents (config.json), Bring back shows it
    "skill_block": APP_ONLY,
    # Auto-approve in its folder (the user's choice, 2026-10-07): the drawer's switch, on or off, the user's click on
    # one of our pages. The Brain, templates and voice never turn it on (new_task's "auto" is the composer's switch)
    "agent_auto": APP_ONLY,
    # Saved agents (2026-10-08): the Agents page lists, saves and deletes them, on the user's click on one of our pages.
    # Their instruction reaches their system prompt: the Brain, templates, voice and pages' text never write one
    "saved_agents": APP_ONLY, "saved_agent_save": APP_ONLY, "saved_agent_delete": APP_ONLY,
}


def may_send(role: str, message: dict) -> bool:
    """Whether a page of this role may send this message: only AI Browser's own pages ("app") send anything. An
    unknown type, a message without one, or a type that isn't a string is never allowed."""
    kind = message.get("type")
    rule = MESSAGE_RULES.get(kind) if isinstance(kind, str) else None
    return rule is not None and role == "app" and rule.app


open_terminal = platforms.open_terminal  # Settings → Accounts → Open Terminal (tests replace it: never a real window)


def setup_page(system: str | None = None) -> str:
    """The setup page (Brave's switch, once), worded for the computer it runs on; every value is escaped. It holds no
    secret: it is the one page of ours that opens anywhere."""
    return SETUP_PAGE.read_text(encoding="utf-8").replace("{{THIS_COMPUTER}}",
                                                          html.escape(platforms.this_computer(system)))


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


def not_here() -> str:
    """A page asked for without the window's cookie: it opens only in AI Browser's own window, and how to start that
    (the packaged AI Browser.exe names itself)."""
    return NOT_HERE.format(how=platforms.start_words())


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
    """On every HTTP answer: scripts and styles from our own files only, sockets only to /ws, and no fetch at all
    (so a page's script can never reach /cdp or /agent-*), no sniffing, no referrer, nothing cached. A page frames
    nothing and nothing frames it, except the window's tab menu: it frames `frames`, and the pages it shows let only
    their own origin frame them (`ancestors`, from _page_headers)."""
    origin = f"{host}:{port}"
    csp = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
           f"connect-src ws://{origin}/ws; {f'frame-src {frames}; ' if frames else ''}"
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
                 settings: Settings | None = None, port_file: Path | None = None,
                 accounts: Accounts | None = None, brain_account=None):
        self.home = Path(home)
        self.settings = settings if settings is not None else Settings(self.home)  # <home>/settings.json
        self.workspaces = Workspaces(self.home)  # <home>/workspaces.json: the new look's groups
        self.saved = SavedAgents(self.home)  # <home>/agents: the saved agents (the Agents page)
        self.uploads = attachments.Uploads(self.home / "app" / "uploads")  # files on their way from a page
        self.port_file = Path(port_file) if port_file is not None else None  # run_app: <home>/app/port
        self.window_info: dict = {"using": None, "name": "", "note": "", "choices": []}  # run_app sets it once
        self.desktop = None  # AI Browser's own app while it runs (run_app attaches it): the shortcut, notifications
        self._notes: dict[str, dict] = {}  # the app's notifications: id -> {"kind", "agent"}, for their clicks
        self._note_seq = 0
        self.agents = agents
        self.brain = brain
        self.skill_writer = skill_writer  # skills the Brain drafts, written only on the user's Save
        if skill_writer is not None and skill_writer.on_saved is None:
            skill_writer.on_saved = self.skills_changed
        self.hearing = hearing  # push-to-talk: the user's speech becomes text on this computer (Mission Control)
        if hearing is not None:
            hearing.on_status = lambda status: self._send_all({"type": "hearing_status", **status})
        self.tools = tools  # the user's MCP servers for the agents (Integrations)
        if tools is not None:
            agents.tools = tools
        self.accounts = accounts  # AI accounts (Settings → Accounts); None: Default only, as before
        if accounts is not None:
            agents.accounts = accounts
            agents.on_limit = lambda account: self._accounts_changed()  # the pickers' "at its limit until"
            agents.on_usage = lambda account: self._accounts_changed()  # the Usage card's bars (the new look)
            accounts.on_change = self._accounts_changed  # a status that changed, whoever asked: every page hears it
        self.open_terminal = open_terminal
        self._signing_in: dict[str, asyncio.Task] = {}  # account id -> the look at its sign-in
        self.brain_account = brain_account  # the Brain's and its skill writer's calls, on the Brain's account
        self.brain_limit: dict | None = None  # {"account", "resets_at"}: the Brain's card in its inbox, until a switch
        if brain_account is not None:
            brain_account.on_limit = self._brain_limit_hit
        self.workflows, self.runner = workflows, runner  # the user's templates (the Agents page)
        if runner is not None:
            runner.on_change = self.workflows_changed
            runner.saved = self.saved  # a template's Runs as: a saved agent
        if brain is not None:
            brain.workflows, brain.runner = workflows, runner
        self._roles: dict[WebSocket, str] = {}  # "app", stored when a socket is accepted
        self._views: dict[WebSocket, str] = {}  # which page said hello on a socket: "mission", "chat", "settings"…
        self._shown: set[WebSocket] = set()  # the sockets whose page says it can be seen (link.js: hello, visibility)
        self._holding: asyncio.TimerHandle | None = None  # the hold that waits HOLD_AFTER for another page in front
        self._windows: set[WebSocket] = set()  # AI Browser's window's sockets: the pages in its tabs (Mission Control…)
        self.window_seen = False  # the window's first socket has come in
        if brain is not None:
            brain.broadcast = self._send_all
            brain.outbox = self._brain_out
            brain.closed_note = self._brain_closed
        self.default_model = default_model if default_model in MODELS else "sonnet"  # ai-browser app --model
        self.host = host
        self.ports = ports
        self.tokens = Tokens()  # each agent's own token (and each session's for /cdp), new every run
        self.session_token = secrets.token_urlsafe(24)  # Claude Code sessions (in <home>/app/link.json, mode 0600)
        self.brave = None  # BraveLink in brave mode (attach_brave): the user's Brave
        self.inbox: InboxReader | None = None  # the Brain's reading of the user's tabs (attach_brave makes it)
        self._picks: set[asyncio.Future] = set()  # Pick the part to watch, waiting for the user's click in Brave
        self.sessions: dict[str, dict] = {}  # Claude Code sessions browsing in Brave while the app runs
        self._sweeper: asyncio.Task | None = None
        self.url: str | None = None
        self.port: int | None = None  # the bound port, once start() has one
        self.strict_headers: list[tuple[bytes, bytes]] = []  # every HTTP answer's headers, once the port is known
        self.page_headers: dict[str, list[tuple[bytes, bytes]]] = {}  # the tab menu's and its pages' own (by path)
        self.ui_secret = secrets.token_urlsafe(32)  # the window's session cookie: set only by swapping a start code
        self._codes: dict[str, float] = {}  # one-time start codes -> when they expire (_clock)
        self._files = {path.name for path in UI.iterdir() if path.is_file() and path.suffix in FILE_TYPES}
        self.out: Callable[[str], None] = print  # where the app's one-line notes go (run_app passes its own)
        self.tabs = None
        self._catalog = catalog
        self._sockets: dict[WebSocket, asyncio.Queue] = {}  # sockets that said hello: they get every broadcast
        self._writers: dict[WebSocket, asyncio.Task] = {}
        self._feed = agents.subscribe()
        self._fanout: asyncio.Task | None = None
        self._thumbs: dict[str, dict] = {}  # agent id -> {"last": monotonic time, "task", "again", "jpeg"}
        self._told_profile: set[str] = set()  # runs told their profile isn't learned yet (once each)
        self._jobs: set[asyncio.Task] = set()
        self._server: _QuietServer | None = None
        self._task: asyncio.Task | None = None
        agents.on_action = self._on_action
        agents.let_go = self._let_go  # a handed tab taken back, or let go when its agent closes
        agents.on_turn = lambda agent: self.connect_brave("turn", agent.id)  # right after the user's task
        agents.mint_token = self.tokens.mint
        agents.catalog = self._skill_catalog  # Load at start: a run's first message carries its skills' text
        if brain is not None:
            brain.set_sources(self.settings.get()["brain_sources"])  # Settings → Brain's checkboxes
            brain.auto_hand = lambda: self.settings.get()["auto_hand"]  # Settings → Brain's hand-off switch
            brain.visible = self._shows_handoffs
        if tabs is not None:
            self.attach_tabs(tabs)

    @property
    def window_count(self) -> int:
        return len(self._windows)  # a set: never below 0, never a socket twice

    def _socket_kind(self, ws: WebSocket) -> str | None:
        """Who opens this socket: AI Browser's window (its cookie, our exact Origin and Host). None: refused, whatever
        else it carries (a token, an extension's origin)."""
        origin = ws.headers.get("origin")
        if origin == self.origin and ws.headers.get("host") == self.host_header and self._cookie_ok(ws):
            return "window"
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
        return {**self.settings.get(), "window": dict(self.window_info), "desktop": self._desktop_payload(),
                "old_watcher": self._old_watcher(), "profiles": self._profiles()}

    def _profiles(self) -> list[dict]:
        """Brave's profiles for Settings → Where agents browse (folder, name, colour; never an email), or none
        without Brave. Only AI Browser's own pages get them: never Claude, an agent or the Brain."""
        return self.brave.place.profiles() if self.brave is not None else []

    def _old_watcher(self) -> bool:
        """Whether an earlier AI Browser's copy of Brave's watcher is still in <home>/app/watcher, so the extension may
        still be loaded in Brave: Settings → Brave then says the user can remove it. AI Browser never removes either."""
        return (self.home / "app" / "watcher" / "manifest.json").is_file()

    def _settings_set(self, queue: asyncio.Queue, message: dict) -> None:
        request = message.get("request") if isinstance(message.get("request"), (str, int)) else None
        key = message.get("key")
        if key not in SETTING_KEYS:
            queue.put_nowait({"type": "error", "text": "There is no such setting", "request": request})
            return
        value = message.get("value")
        if key == "agents_profile" and value is not None and (not isinstance(value, str) or value not in {
                profile["folder"] for profile in self._profiles()}):
            queue.put_nowait({"type": "error", "text": "Pick one of the profiles listed", "request": request})
            return
        if key == "shortcut" and self.desktop is not None:  # the app tries it first: only one it could take is saved
            self._job(self._shortcut_set(queue, message.get("value"), request))
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
        if key == "agents_profile" and self.brave is not None:  # Settings → Where agents browse
            self.brave.set_place(self.settings.get()["agents_profile"])
        if key == "read_tabs" and self.inbox is not None:  # Settings → Brain: reading starts or stops at once
            self.inbox.set_on(self.settings.get()["read_tabs"])
        if key == "brain_sources" and self.brain is not None:  # Settings → Brain's checkboxes: at once
            self.brain.set_sources(self.settings.get()["brain_sources"])
        if key == "auto_hand" and self.brain is not None and not self.settings.get()["auto_hand"]:
            self.brain.hold_countdowns()  # off: every hand-off waits for Send, a counting one too
        if key == "read_tabs" and not self.settings.get()["read_tabs"]:
            for pick in list(self._picks):  # a pick under way ends too, and keeps nothing
                pick.cancel()
        self._send_all({"type": "settings", **self._settings_payload()})

    def attach_desktop(self, desktop) -> None:
        """AI Browser's own app (desktop/launch.py), for this run: its shortcut, its notifications and their clicks."""
        self.desktop = desktop
        desktop.on_message = self._from_desktop

    def detach_desktop(self) -> None:
        if self.desktop is not None:
            self.desktop.on_message = None
        self.desktop = None

    def _desktop_payload(self) -> dict:
        """Settings' view of AI Browser's own app: whether it is set up and running, what went wrong
        last, and the shortcut with the app's word on it."""
        value = self.settings.get()["shortcut"]
        said = self.desktop.shortcut if self.desktop is not None else {}
        return {"running": self.desktop is not None, "supported": asset_for() is not None,
                "set_up": layout.installed(self.home) is not None, "version": ELECTRON_VERSION,
                "platform": PLATFORM_WORDS.get(sys.platform, "other"), "command": setup_command(),
                "problem": layout.problem(self.home),
                "shortcut": {"value": value, "label": shortcut_label(value),
                             "state": shortcut_state(value, said, self.desktop is not None)},
                "shortcuts": [{"value": one, "label": shortcut_label(one)} for one in SHORTCUTS]}

    async def _shortcut_set(self, queue: asyncio.Queue, value, request) -> None:
        """A shortcut picked in Settings while the app runs. The app tries it first, and only a shortcut it could take
        is saved. When another app holds it, the one before stays, and Settings says so."""
        if value is not None and value not in SHORTCUTS:
            queue.put_nowait({"type": "error", "text": SHORTCUT_ERROR, "request": request})
            return
        answer = await self.desktop.try_shortcut(value)
        if not answer.get("ok"):
            text = (f"{shortcut_label(value)} is used by another app. Pick another one." if answer.get("why") == "taken"
                    else APP_SILENT)
            queue.put_nowait({"type": "error", "text": text, "request": request})  # its page checks the saved one
            return
        try:
            self.settings.set("shortcut", value)
        except (ValueError, OSError) as exc:
            queue.put_nowait({"type": "error", "request": request,
                              "text": f"Couldn't save that setting: {getattr(exc, 'strerror', None) or exc}"})
            return
        self._send_all({"type": "settings", **self._settings_payload()})

    def _from_desktop(self, message: dict) -> None:
        """What the app says unasked: the shortcut it holds (or can't, or its first press), and a click on one of its
        notifications."""
        kind = message.get("type")
        if kind == "shortcut":
            if message.get("ok") is False and isinstance(message.get("value"), str):
                self.out(f"{shortcut_label(message['value'])} is used by another app, so it does nothing in AI "
                         "Browser: pick another in Settings")
            self._send_all({"type": "settings", **self._settings_payload()})
        elif kind == "clicked" and isinstance(message.get("id"), str):
            self._job(self._clicked(message["id"]))

    def _notify_desktop(self, message: dict) -> bool:
        """A notification from AI Browser's own app, in place of Brave's, in fixed words (desktop/notes.py). False when
        the app isn't running: Mission Control shows it then."""
        desktop = self.desktop
        note = note_for(message) if desktop is not None and not desktop.ended.is_set() else None
        if note is None:
            return False
        self._note_seq += 1
        note_id = f"n{self._note_seq}"
        self._notes[note_id] = {"kind": note["kind"], "agent": note["agent"]}
        while len(self._notes) > NOTES_KEPT:
            self._notes.pop(next(iter(self._notes)))
        return desktop.send({"type": "notify", "id": note_id, "title": note["title"], "body": note["body"]})

    async def _clicked(self, note_id: str) -> None:
        """A click on one of the app's notifications. A bot check brings the agent's tab forward, in Brave. Anything
        else brings the app's window forward, on Mission Control, at that agent's drawer (or the Brain's inbox)."""
        note = self._notes.pop(note_id, None)
        if note is None or self.desktop is None:
            return
        if note["kind"] == "check" and self._check_target(note["agent"]) is not None:
            await self._show_check(note["agent"])
            return
        self.desktop.send({"type": "show"})
        self._send_all({"type": "focus", **({"agent": note["agent"]} if note["agent"] else {"brain": True})})

    def _check_target(self, agent_id: str) -> str | None:
        """The tab in Brave where this agent's bot check waits, if there is one (a live view's has none)."""
        agent = self.agents.agents.get(agent_id)
        check = agent.check if agent is not None else None
        if check is None or check.get("live") or not check.get("target") or self.tabs is None:
            return None
        return check["target"]

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

    def _this_page(self, queue: asyncio.Queue, message: dict) -> None:
        """The floating chat's "This page" (native-app Decision 4): the address and title AI Browser's own app read
        from Brave's front tab, matched to the tab list (pagematch). The answer, to the asking page only: "found" with
        the tab's row, "choose" (the user picks), or "not_connected" with Brave's state. It never connects to Brave,
        so Brave asks nothing new (Review Focus 2)."""
        request = message.get("request") if isinstance(message.get("request"), (str, int)) else None
        answer = {"type": "this_page", "request": request}
        if self.brave is None or self.brave.state != "connected":
            queue.put_nowait({**answer, "state": "not_connected",
                              "browser": self.brave.state if self.brave is not None else "off"})
            return
        found = pagematch.seen(message)
        tabs = self.brave.tabs()
        target = pagematch.match(found, tabs) if found is not None else None
        tab = next((row for row in tabs if row["target"] == target), None)
        queue.put_nowait({**answer, "state": "found", "tab": tab} if tab is not None else {**answer, "state": "choose"})

    def _show_app(self, message: dict) -> None:
        """The floating chat's Open Mission Control (or an agent's number in it): AI Browser's window comes forward on
        Mission Control,
        at that agent's row, or the Brain's. A view only: nothing runs."""
        agent = message.get("agent")
        if isinstance(agent, str) and AGENT_ID.match(agent):
            focus = {"agent": agent}
        else:
            focus = {"brain": True} if message.get("brain") is True else {}
        if self.desktop is not None:
            self.desktop.send({"type": "show"})
        self._send_all({"type": "focus", **focus})

    async def _this_page_text(self, target: str, site: str) -> dict:
        """The page the user asked about in the floating chat, read now (native-app Decision 4): its title, address
        and words (brain/readers/page.js, at most PAGE_TEXT_LIMIT characters), or {"error": why} in plain words. It
        is used only when it is still on `site`, the site the user marked with Ask about it: a tab that went elsewhere
        since gives nothing to Claude. It never connects to Brave (Review Focus 2)."""
        if self.brave is None or self.brave.state != "connected":
            return {"error": CHAT_NOT_CONNECTED}
        try:
            read = await self.brave.read_page(target, PAGE_TEXT_LIMIT)
        except WorldError as exc:
            return {"error": f"Couldn't read that page: {exc}"}
        if not site or pagematch.site(read.get("url")) != site:
            return {"error": CHAT_PAGE_CHANGED}  # what was read is dropped here
        return read

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
        self.uploads.clear()  # a crash's leftovers: no page is there to send them any more
        app = _Guard(Starlette(routes=[Route("/", self._root), Route("/open", self._open), Route(SHELL, self._page),
                                       Route(OLD_HOME, self._old_home), Route("/mission", self._page),
                                       Route("/settings", self._page), Route("/chat", self._page),
                                       Route("/health", self._health), Route("/setup", self._setup),
                                       Route("/agent-events", self._agent_events, methods=["POST"]),
                                       Route("/agent-tab", self._agent_tab, methods=["POST"]),
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
        if self.inbox is not None:
            await self.inbox.stop()  # no tab of the user's is read any more
        if self.brain is not None:
            await self.brain.stop()
        await self.agents.close_all()  # every agent's Claude Code process ends with the app
        if self.brave is not None:  # the agents have ended: their sockets close (1001) before uvicorn stops
            with contextlib.suppress(Exception):
                await self.brave.relay.close_clients(1001)
        for task in [self._fanout, self._sweeper, *self._jobs, *(state["task"] for state in self._thumbs.values()),
                     *self._signing_in.values()]:
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

    async def _old_home(self, request: Request) -> Response:
        """The old home page's address: Mission Control, where everything it had now is."""
        return RedirectResponse("/mission", status_code=303)

    async def _open(self, request: Request) -> Response:
        """The window's start address: a valid code becomes the cookie, and the redirect to the tab menu drops the code
        from the window's address and history. A used or unknown code is a 403, unless the cookie is already there (a
        reload)."""
        if self._take_code(request.query_params.get("code", "")):
            debugstart.say(f"GET /open: a valid start code: the window's cookie {self.cookie_name} is set")
            response = RedirectResponse(SHELL, status_code=303)
            response.set_cookie(self.cookie_name, self.ui_secret, httponly=True, samesite="strict", path="/")
            return response
        if self._cookie_ok(request):
            debugstart.say("GET /open: an unknown, used or expired start code, but the window's cookie is there")
            return RedirectResponse(SHELL, status_code=303)
        debugstart.say(f"GET /open: an unknown, used or expired start code, and no window cookie {self.cookie_name}")
        return _refused_page(USED_CODE)

    def _say_cookie(self, request: Request, ok: bool) -> None:
        """The start log's line for a page: whether the window's cookie came, and the names of those that did."""
        if ok:
            debugstart.say(f"GET {request.url.path}: the window's cookie is there")
        else:
            sent = ", ".join(sorted(request.cookies)) or "none"
            debugstart.say(f"GET {request.url.path}: no window cookie {self.cookie_name} (cookies sent: {sent})")

    async def _page(self, request: Request) -> Response:
        ok = self._cookie_ok(request)
        self._say_cookie(request, ok)
        if not ok:
            return _refused_page(not_here())
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
            self._say_cookie(request, False)
            return _refused_page(not_here())
        return Response((UI / name).read_bytes(), media_type=FILE_TYPES[Path(name).suffix])

    async def _setup(self, request: Request) -> HTMLResponse:
        return HTMLResponse(setup_page())

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
            report["adopted"] = False  # a bot check shown in a live view: no tab of the user's Brave
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
        """Who an id is, as the Tabs page's chips show it: an agent (or a tab handed to it), or a Claude Code
        session."""
        if SESSION_ID.match(agent_id):
            session = self.sessions.get(agent_id)
            return None if session is None else {"kind": "session", "id": agent_id, "name": session["name"],
                                                 "color": session["color"]}
        agent = self.agents.agents.get(agent_id)
        if agent is None:
            return None
        return {"kind": "handed" if handed else "agent", "id": agent.id, "name": agent.name, "color": agent.color}

    def _own(self, target: str, owner: dict | None) -> None:
        """Whose a tab of the user's Brave is, for the Tabs page (brave mode only)."""
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
        elif kind == "tab_closed":
            if target in session["tabs"]:
                session["tabs"].remove(target)
                self._sessions_changed()
            self._own(target, None)

    def _after_agent_report(self, report: dict) -> None:
        """The Tabs page's chips follow an agent's tabs."""
        agent_id, kind, target = report["agent"], report.get("kind"), report.get("target")
        if not isinstance(target, str) or not target or self.agents.agents.get(agent_id) is None:
            return
        if kind in ("tab_opened", "working_tab"):
            self._own(target, self._owner_of(agent_id, handed=bool(report.get("adopted"))))
        elif kind == "tab_closed":
            self._own(target, None)

    async def _agent_tab(self, request: Request) -> Response:
        """A new tab for an agent's or a Claude Code session's engine (grouping.Placer): opened by the app in the
        profile where agents browse, never among the user's windows, and theirs at once. {"target"}, or {"error"} in
        plain words that name no profile: they reach Claude as a tool error."""
        body, refused = await self._engine_body(request)
        if refused is not None:
            return refused
        owner_id = body["agent"]
        owner = self._owner_of(owner_id)
        if owner is None:
            return Response(status_code=404)
        if self.brave is None:
            return JSONResponse({"error": NOT_CONNECTED})
        agent = self.agents.agents.get(owner_id)
        profile = agent.profile if agent is not None else None  # a saved agent's own Brave profile, else Settings'
        try:
            target = await self.brave.open_ai_tab(owner_id, profile=profile)
        except PlaceError as exc:
            if profile is not None and str(exc) == NOT_OPEN:
                self._not_learned(agent)
            return JSONResponse({"error": str(exc)})
        self._record_tab(owner_id, target)
        self._own(target, owner)
        return JSONResponse({"target": target})

    def _not_learned(self, agent: Agent) -> None:
        """A run's profile isn't learned yet: its chat says so once, in fixed words that name the profile. Nothing
        opens a Brave window by itself."""
        if agent.id in self._told_profile:
            return
        self._told_profile.add(agent.id)
        name = next((row["name"] for row in self._profiles() if row["folder"] == agent.profile), agent.profile)
        name = one_line(name)[:60]  # Brave's name is the user's own: one line, as long as the other one-line fields
        self.agents.note(agent.id, NOT_LEARNED.format(number=agent.number, name=name))

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
        return JSONResponse({"handed": handed})

    async def _agent_hello(self, request: Request) -> Response:
        body, refused = await self._engine_body(request)
        if refused is not None:
            return refused
        session_id, pid = body["agent"], body.get("pid")
        if not SESSION_ID.match(session_id) or not isinstance(pid, int):
            return Response(status_code=404)
        relay = self.brave.relay if self.brave is not None else None
        if relay is not None and relay.is_cut_off(session_id):
            return Response(status_code=410)  # the user disconnected it in Settings → Brave: not again this run
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
        relay.placed_only = self._placed_only  # a run with a Brave profile of its own: the app opens its tabs
        self.agents.own_tabs = relay.own_targets
        relay.on_grant(lambda identity, target: self._own(target, self._owner_of(identity)))
        relay.on_change(self._clients_changed)
        brave.on_state(lambda state: self._browser_changed())
        brave.set_place(self.settings.get()["agents_profile"])  # Settings → Where agents browse
        brave.brain_reading = lambda: self.settings.get()["read_tabs"]  # BraveLink's gate asks: Settings → Brain
        brave.brain_site = self._brain_site
        if self.inbox is not None:
            self.inbox.set_on(False)  # a tab source replaced (tests): its reading ends
            self.inbox = None
        if self.brain is not None:
            self.inbox = InboxReader(self.brain, brave)
            self.inbox.set_on(self.settings.get()["read_tabs"])
        self._browser_changed()
        self._send_all(self._tabs_message(brave.tabs()))  # pages already open see Brave's list at once

    def _brain_site(self, url: str) -> str | None:
        """Which site the Brain reads at this address, for BraveLink's gate: one of the three, or a part of a page the
        user picked to watch (switched on), by the address it was picked on. None for any other."""
        site = sites.inbox_site(url)
        if site is None and self.brain is not None:
            site = next((entry.site for entry in self.brain.store.watch() if not built_in(entry.site)
                         and entry.enabled and entry.selector and sites.matches(entry.url_match, url)), None)
        if site is not None and self.brain is not None and not self.brain.listens(source_of(site)):
            return None  # unchecked in Settings → Brain: no reader runs there
        return site

    async def _watch_pick(self, queue: asyncio.Queue, message: dict) -> None:
        """Pick the part to watch, on the user's click in Settings → Brain: the tab they chose comes forward in Brave,
        and the picker runs there in the isolated world (BraveLink's gate: one of their listed web tabs, only while
        reading is on). A click picks, Escape cancels, and what was picked is watched from now on. A pick nobody
        finished, or one that ends after reading went off, keeps nothing."""
        request = message.get("request") if isinstance(message.get("request"), (str, int)) else None
        target, brave = message.get("target"), self.brave

        def answer(**fields) -> None:
            queue.put_nowait({"type": "watch_picked", "request": request, **fields})

        if brave is None or brave.state != "connected" or self.brain is None:
            answer(error=NOT_CONNECTED)
            return
        if not self.settings.get()["read_tabs"]:
            answer(error=PICK_OFF)
            return
        tab = next((tab for tab in brave.tabs() if tab["target"] == target), None)
        if not isinstance(target, str) or tab is None or not brave.may_run(target, "pick"):
            answer(error=PICK_TAB)
            return
        await brave.watch(target)  # the tab comes forward in Brave: the user picks there
        pick = asyncio.ensure_future(brave.run_reader(target, "pick", "pick", timeout=PICK_WAIT))
        self._picks.add(pick)
        try:
            result = await pick
        except (asyncio.CancelledError, WorldError):
            result = None
        finally:
            self._picks.discard(pick)
        if not isinstance(result, dict) or not self.settings.get()["read_tabs"]:
            await brave.end_pick(target)  # given up, or reading went off: the outline leaves the page
            answer(cancelled=True)
            return
        selector = result.get("selector")
        if result.get("cancelled") or not isinstance(selector, str):
            answer(cancelled=True)  # Escape
            return
        place = urlsplit(tab["url"]).hostname or ""
        site = f"custom:{place}"
        error = self.brain.set_watch({"site": site, "label": place, "url_match": sites.watch_pattern(tab["url"]),
                                     "selector": selector[:500], "enabled": True})
        if error:
            answer(error=error)
        else:
            answer(site=site, sample=_text(result.get("sample"))[:300])

    def _placed_only(self, identity: str) -> bool:
        """Whether only the app may open this client's tabs: a run with a Brave profile of its own, or an agent's id
        the app no longer knows (its socket outlived AgentManager.close): fail closed, never the profile used last."""
        agent = self.agents.agents.get(identity)
        if agent is None:
            return bool(AGENT_ID.match(identity))
        return agent.profile is not None

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
        """Settings → Brave's list of what uses the user's Brave through the app (the relay's rows, with names and
        colours). No token is in it."""
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
            return {"kind": "brave", "name": "Brave", "state": "off"}
        return {"kind": "brave", "name": self.brave.name, "state": self.brave.state}

    def _browser_changed(self) -> None:
        if self.inbox is not None:  # Brave connected or went: reading goes on, or waits for it
            self.brain.set_reading(self.inbox.state())
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
        return ""

    def _let_go(self, targets: list[str]) -> None:
        """Handed tabs taken back, or let go when their agent closes: they're the user's again."""
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
            if debugstart.on():
                origin, host = ws.headers.get("origin") == self.origin, ws.headers.get("host") == self.host_header
                debugstart.say(f"socket refused: origin {'ok' if origin else 'wrong'}, "
                               f"host {'ok' if host else 'wrong'}, "
                               f"window cookie {'ok' if self._cookie_ok(ws) else 'missing'}")
            await ws.close(code=REFUSED)
            return
        self._roles[ws] = "app"  # AI Browser's window: _socket_kind takes no other socket
        self._windows.add(ws)
        self.window_seen = True
        debugstart.say(f"window socket connected ({len(self._windows)} open)")
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
        """Every message to a socket passes here (answers and _send_all), so a path added later is covered: a socket
        that isn't one of AI Browser's own pages is sent nothing but pings (none gets past _socket_kind)."""
        ours = self._role(ws) == "app"  # read once (set at accept)
        with contextlib.suppress(Exception):
            while True:
                message = await queue.get()
                if ours or message.get("type") == "ping":
                    await ws.send_json(message)

    def _unsubscribe(self, ws: WebSocket) -> None:
        self._sockets.pop(ws, None)
        self._roles.pop(ws, None)
        self._views.pop(ws, None)
        self._seen(ws, False)  # a closed page can't show a hand-off's card
        self._windows.discard(ws)
        self.uploads.drop_all(ws)  # a closed page's files go with it
        if self.hearing is not None:
            self.hearing.drop(ws)  # a closed page's turn, and its audio, go with it
        writer = self._writers.pop(ws, None)
        if writer is not None:
            writer.cancel()

    def _send_all(self, message: dict) -> None:
        for queue in self._sockets.values():
            queue.put_nowait(message)

    def _brain_out(self, message: dict) -> bool:
        """What the Brain asks of the app: its new notes, notified by AI Browser's own app in fixed words; or a
        thread to open and a reply box to fill, in the user's tabs. False when nothing took it: the Brain says why."""
        kind = message.get("type")
        if kind in ("notify", "handoff"):
            return self._notify_desktop(message)
        if kind in ("open_thread", "fill_reply") and self.inbox is not None:
            return self.inbox.handle(message)  # in the user's tabs, only while reading is on
        return False

    def _shows_handoffs(self) -> bool:
        """Whether a page that shows the Brain's hand-off cards (Mission Control, the floating chat) can be seen: it is
        open and says it isn't hidden (the desktop app only hides its window on close). Only then may a hand-off count
        down. Nothing is sent while nobody can see it."""
        return any(self._views.get(ws) in HANDOFF_VIEWS for ws in self._shown)

    def _seen(self, ws: WebSocket, shown: bool) -> None:
        """A page says whether it can be seen. When none that shows hand-off cards can for HOLD_AFTER seconds, every
        countdown holds. Only that sweep waits, for a tab switch whose pages the app hears in either order: what a
        page says counts at once, and a countdown's end sends nothing unless a page can show its card then."""
        if shown:
            self._shown.add(ws)
        else:
            self._shown.discard(ws)
        if self.brain is not None and not self._shows_handoffs() and self._holding is None:
            self._holding = asyncio.get_running_loop().call_later(HOLD_AFTER, self._hold_unseen)

    def _hold_unseen(self) -> None:
        self._holding = None
        if self.brain is not None and not self._shows_handoffs():
            self.brain.hold_countdowns()  # still no page can show a card: every countdown waits for Send

    def _brain_closed(self) -> str:
        """Why the Brain's outbox took a thread or a reply box nowhere, for the item's note."""
        return self.inbox.why_closed() if self.inbox is not None else NOT_CONNECTED

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
                self._notify_desktop(message)  # AI Browser's own app shows it too, in fixed words

    def _job(self, coroutine) -> None:
        task = asyncio.ensure_future(coroutine)
        self._jobs.add(task)
        task.add_done_callback(self._jobs.discard)

    def _role(self, ws: WebSocket) -> str:
        """The role stored when the socket was accepted: "app" (AI Browser's window: its cookie, Origin and Host). A
        socket with no stored role is "none": it may send nothing (may_send), and is sent nothing but pings."""
        return self._roles.get(ws, "none")

    async def _handle(self, ws: WebSocket, queue: asyncio.Queue, message: dict) -> None:
        if not may_send(self._role(ws), message):  # MESSAGE_RULES, before anything reads the message's fields
            return  # dropped, with no answer: a page can't map the table by trying types
        kind, agent_id, agents = message["type"], str(message.get("id", "")), self.agents
        if kind in BRAIN_MESSAGES:
            if self.brain is not None:
                await self._brain_command(queue, kind, agent_id, message)
        elif kind == "watch_pick":  # Settings → Brain: the user's click on Pick the part to watch
            self._job(self._watch_pick(queue, message))
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
        elif kind in CHECK_MESSAGES:  # a bot check's buttons
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
            self._talk_command(queue, kind, message, chat=self._views.get(ws) == "chat")
        elif kind in ACCOUNT_MESSAGES:  # AI Browser's own pages only (MESSAGE_RULES)
            await self._account_command(queue, kind, message)
        elif kind in POWERS_MESSAGES:  # AI Browser's own pages only (MESSAGE_RULES)
            self._powers_command(queue, kind, message)
        elif kind == "skill_block":  # AI Browser's own pages only (MESSAGE_RULES)
            self._skill_block(queue, message)
        elif kind in ATTACH_MESSAGES:  # AI Browser's own pages only (MESSAGE_RULES)
            self._attach_command(ws, queue, kind, message)
        elif kind in WORKSPACE_MESSAGES:  # AI Browser's own pages only (MESSAGE_RULES)
            self._workspace_command(queue, kind, message)
        elif kind in SAVED_MESSAGES:  # AI Browser's own pages only (MESSAGE_RULES)
            self._saved_command(queue, kind, message)
        elif kind == "hello":
            self._views[ws] = message.get("view") if isinstance(message.get("view"), str) else ""
            self._seen(ws, message.get("visible") is True)
            if ws not in self._sockets:  # the snapshot, then every broadcast (no await between the two)
                queue.put_nowait(self._snapshot())
                self._sockets[ws] = queue
        elif kind == "visibility":  # the page was shown or hidden (link.js)
            self._seen(ws, message.get("visible") is True)
        elif kind == "settings_set":
            self._settings_set(queue, message)
        elif kind == "open_url":
            self._job(self._open_url(queue, message))
        elif kind == "this_page":  # the floating chat: which listed tab the user is on
            self._this_page(queue, message)
        elif kind == "show_app":  # the floating chat's Open Mission Control, or an agent's number
            self._show_app(message)
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
            account = message.get("account") if isinstance(message.get("account"), str) else None
            folder = message.get("folder") if isinstance(message.get("folder"), str) and message.get("folder") \
                else None  # agent powers: the task's folder; none is the agent's own scratch folder
            listed = message.get("attachments") if isinstance(message.get("attachments"), list) else []
            web = message.get("web") if message.get("web") in powers.WEB_CHOICES else "web"
            saved = self.saved.get(message["agent"]) if message.get("agent") is not None else None  # Agent ▾
            if message.get("agent") is not None and saved is None:
                queue.put_nowait({"type": "error", "text": NOT_AN_AGENT, "request": request})
                return
            started = True
            try:  # an account that isn't listed any more is said, never swapped for another
                files = self.uploads.take(ws, listed)  # each attached file whole, or nothing starts
                if saved is not None:  # its own settings, Auto-approve too: the page's pickers don't apply
                    agent, started = await agents.run_as(saved, text, skills, tab=_tab(message.get("tab")),
                                                         adopt=adopt, files=files,
                                                         workspace=self._workspace_of(message))
                else:
                    agent = await agents.create(text, skills, model, adopt, _tab(message.get("tab")),
                                                account=account, folder=folder, workspace=self._workspace_of(message),
                                                files=files, web=web, effort=message.get("effort"),
                                                auto=message.get("auto") is True,  # the composer's switch
                                                name=message.get("name"), description=message.get("description"))
            except ValueError as exc:
                queue.put_nowait({"type": "error", "text": str(exc), "request": request})
                return
            self.uploads.done(ws, listed)
            if handed is not None and not started:  # its run is at work: the tab is handed to that run
                await self._hand(agent.id, adopt)
            elif handed is not None:
                self._own(adopt, self._owner_of(agent.id, handed=True))
            queue.put_nowait({"type": "created", "id": agent.id, "request": request})
        elif kind == "send":
            await self._send(ws, queue, agent_id, message)
        elif kind == "stop":
            if self.brain is not None:
                self.brain.agent_stopped(agent_id)  # its hand-offs' countdowns stop too
            await agents.stop(agent_id)
        elif kind == "close":
            if self.brain is not None:
                self.brain.agent_stopped(agent_id)
            self._job(agents.close(agent_id))  # it may wait for the agent's turn to end
        elif kind == "model" and message.get("model") in MODELS:
            agents.set_model(agent_id, message["model"])
        elif kind == "agent_auto" and isinstance(message.get("agent"), str) and isinstance(message.get("on"), bool):
            agents.set_auto(message["agent"], message["on"])  # the drawer's switch: a yes or a no, nothing else
        elif kind == "watch" and self.tabs is not None and isinstance(message.get("target"), str):
            await self.tabs.watch(message["target"])
        elif kind == "events":
            queue.put_nowait({"type": "agent_events", "id": agent_id, "events": agents.events_of(agent_id)})
        elif kind == "skills":
            queue.put_nowait({"type": "skills", "skills": self._skill_list(), "blocked": self._blocked_skills()})
        elif kind == "thumbs":  # a page opened later: the latest picture of each agent's tab
            queue.put_nowait({"type": "thumbs", "thumbs": {
                agent: state["jpeg"] for agent, state in self._thumbs.items()
                if state.get("jpeg") and agent in self.agents.agents}})

    async def _send(self, ws: WebSocket, queue: asyncio.Queue, agent_id: str, message: dict) -> None:
        """The user's message to an agent, with the files this page staged for it (the drawer's chat: pasted,
        dropped or attached), placed in the agent's folder under attachments/ and named in the message, all or none.
        A page that gives a request id hears "sent", or an error with the reason; refused files stay staged."""
        request = message.get("request") if isinstance(message.get("request"), (str, int)) else None

        def answer(reply: dict) -> None:
            if request is not None:
                queue.put_nowait({**reply, "request": request})

        text = _text(message.get("text"))
        listed = message.get("attachments") if isinstance(message.get("attachments"), list) else []
        try:
            files = self.uploads.take(ws, listed)  # each file whole, or nothing is sent
            if not text and not files:  # ids that name no file are none
                raise ValueError(EMPTY_MESSAGE)
            sent = await self.agents.send(agent_id, text, _tab(message.get("tab")), files=files)
        except ValueError as exc:
            answer({"type": "error", "text": str(exc)})
            return
        if not sent:
            answer({"type": "error", "text": CLOSED})
            return
        self.uploads.done(ws, listed)
        answer({"type": "sent", "id": agent_id})

    async def _show_check(self, agent_id: str) -> None:
        """Show me (a bot check's card): bring forward the tab where this agent's bot check waits. The app holds
        that tab, so no page names one. A check shown in a live view has no tab here, and without a
        tab source nothing happens. It uses the link's one connection and never opens one."""
        agent = self.agents.agents.get(agent_id)
        check = agent.check if agent is not None else None
        if check is None or check.get("live") or not check.get("target") or self.tabs is None:
            return
        await self.tabs.watch(check["target"])

    async def _brain_command(self, queue: asyncio.Queue, kind: str, item_id: str,
                             message: dict) -> None:
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
                                 task=_text(message.get("task")) or None))
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
        elif kind == "style":
            brain.set_style(_text(message.get("text")))
        elif kind == "handoff_send":  # Send now, Send or Start on a hand-off's card: once
            self._job(brain.send_handoff(item_id))
        elif kind == "handoff_cancel":
            brain.cancel_handoff(item_id)

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

    def _talk_command(self, queue: asyncio.Queue, kind: str, message: dict, chat: bool = False) -> None:
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
        if kind == "brain_ask" and chat and not self.brain.listens("chat"):  # Settings → Brain: The floating chat
            queue.put_nowait({"type": "brain_answer", "talk": talk, "request": request, "say": "", "error": CHAT_OFF})
        elif kind == "brain_ask":
            text = message.get("text").strip()[:2000] if isinstance(message.get("text"), str) else ""
            page = message.get("page") if isinstance(message.get("page"), str) and message.get("page") else None
            site = message.get("site") if isinstance(message.get("site"), str) else ""  # the site the user marked
            if text and page is None:  # as before: no page is in it
                self._job(self._answer(queue, talk, request,
                                       self.brain.respond(talk, text, proposal=proposal, task=task, model=model)))
            elif text:  # the floating chat's "Ask about it": the tab is read only if Claude is asked
                self._job(self._answer(queue, talk, request, self.brain.respond(
                    talk, text, proposal=proposal, task=task, model=model,
                    page=lambda: self._this_page_text(page, site))))
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
                note = message.get("note") if isinstance(message.get("note"), str) else ""
                self.agents.answer_permission(message["agent"], message["request"], message["answer"], note)
            return
        account = message.get("account") if isinstance(message.get("account"), str) else "default"
        tools = self._tools_of(account)  # one account's tools at a time (AI accounts); Default when none is named
        if tools is None:
            return
        if kind == "tools":
            queue.put_nowait(self._tools_snapshot(account, tools))
            if message.get("refresh") is True:
                self._job(self.probe_tools(account))
            return
        if kind == "tool_set" and isinstance(message.get("server"), str):
            tools.set_enabled(message["server"], message.get("on") is True)
        elif kind == "tool_allow" and isinstance(message.get("tool"), str):
            tools.allow_always(message["tool"])
        elif kind == "tool_forget" and isinstance(message.get("tool"), str):
            tools.forget(message["tool"])
        else:
            return
        self._send_all(self._tools_snapshot(account, tools))

    def _tools_of(self, account: str):
        """An account's ToolsConfig, by the id a page sent: Default's, or a listed account's; None for any other."""
        if self.tools is None:
            return None
        if account == "default":
            return self.tools
        accounts = self.agents.accounts
        return self.agents.tools_for(account) if accounts is not None and accounts.get(account) is not None else None

    # ---- agent powers: the Folder picker, "Trust this folder?" and Settings → Permissions (our pages only) ---------

    def _powers_command(self, queue: asyncio.Queue, kind: str, message: dict) -> None:
        request = message.get("request") if isinstance(message.get("request"), (str, int)) else None
        rules, path = self.agents.rules, message.get("path")
        try:
            if kind == "folder_choose":
                why = self.agents.folder_problem(path)
                queue.put_nowait({"type": "error", "text": why, "request": request} if why else
                                 {"type": "folder", "request": request, "folder": self._folder_row(path)})
                return
            if kind == "permission_rules":
                queue.put_nowait(self._permissions())
                return
            if kind == "folder_trust":
                if message.get("trust") is True:  # trusting checks the folder; Remove works on one that has gone
                    why = self.agents.folder_problem(path)
                    if why:
                        queue.put_nowait({"type": "error", "text": why, "request": request})
                        return
                    rules.trust(path)
                elif message.get("trust") is False and isinstance(path, str) and path:
                    rules.untrust(path)
                else:
                    return
                queue.put_nowait({"type": "folder", "request": request, "folder": self._folder_row(path)})
            elif kind == "permission_rule_remove":
                folder = message.get("folder")
                if not isinstance(folder, str) or not folder:
                    return
                if message.get("all") is True:
                    rules.forget(folder)
                elif isinstance(message.get("rule"), str):
                    rules.remove(folder, message["rule"])
                else:
                    return
        except OSError as exc:  # a read-only home, a full disk: nothing changed
            queue.put_nowait({"type": "error", "text": f"Couldn't save that: {exc.strerror or exc}",
                              "request": request})
            return
        self._send_all(self._permissions())

    def _folder_row(self, path: str) -> dict:
        real = powers.real_path(path)
        return {"path": real, "name": Path(real).name or real, "trusted": self.agents.rules.trusted(real)}

    def _permissions(self) -> dict:
        return {"type": "permissions", "folders": self.agents.rules.folders()}

    async def probe_tools(self, account: str = "default") -> None:
        """Which claude.ai connectors Claude Code loads for that account now (and their tools)."""
        tools = self._tools_of(account)
        if tools is not None and await tools.probe(self.agents.claude):
            self._send_all(self._tools_snapshot(account, tools))

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
                    workspace = self._workspace_of(message)
                    if workspace is not None:
                        self.agents.set_workspace(agent_id, workspace)
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
        self._send_all({"type": "skills", "skills": self._skill_list(), "blocked": self._blocked_skills()})

    def workflows_changed(self) -> None:
        if self.workflows is not None:
            self._send_all(self._workflows_snapshot())

    def _workflows_snapshot(self) -> dict:
        workflows = [{**workflow.public(), "path": str(self.workflows.path_of(workflow.slug)),
                      "note": self.runner.notes.get(workflow.slug, "") if self.runner else ""}
                     for workflow in self.workflows.all()]
        return {"type": "workflows_snapshot", "workflows": workflows, "problems": self.workflows.problems(),
                "next_runs": self.runner.upcoming() if self.runner is not None else []}  # the Calendar's

    def _attach_command(self, ws: WebSocket, queue: asyncio.Queue, kind: str, message: dict) -> None:
        """The composer's Attach: a file comes in pieces, staged for this page until its task starts (or it is
        dropped). Each answer names the page's own id for that file."""
        upload = message.get("upload") if isinstance(message.get("upload"), str) else ""
        if kind == "attach_drop":
            self.uploads.drop(ws, upload)
            return
        if kind == "attach_start":
            try:
                name, problem = self.uploads.start(ws, upload, message.get("name"), message.get("size"))
            except OSError as exc:
                name, problem = "", f"Couldn't keep that file: {exc.strerror or exc}"
            if problem:
                queue.put_nowait({"type": "error", "text": problem, "request": upload})
                return
            queue.put_nowait({"type": "attach_ready", "upload": upload, "name": name})
            if self.uploads.whole(ws, upload):  # an empty file is whole already
                queue.put_nowait({"type": "attach_done", "upload": upload})
            return
        try:
            whole, problem = self.uploads.add(ws, upload, message.get("seq"), message.get("data"))
        except OSError as exc:
            self.uploads.drop(ws, upload)
            whole, problem = False, f"Couldn't keep that file: {exc.strerror or exc}"
        if problem:
            queue.put_nowait({"type": "error", "text": problem, "request": upload})
        elif whole:
            queue.put_nowait({"type": "attach_done", "upload": upload})

    def _workspaces_message(self) -> dict:
        return {"type": "workspaces", "workspaces": self.workspaces.list()}

    def _workspace_of(self, message: dict) -> str | None:
        """The workspace a new agent goes in: one that exists, else none. A filter: a start is never refused for it."""
        given = message.get("workspace")
        return given if isinstance(given, str) and self.workspaces.get(given) is not None else None

    def _workspace_command(self, queue: asyncio.Queue, kind: str, message: dict) -> None:
        """The new look's workspaces: the list, New and rename, Delete (its agents keep running, ungrouped), and moving
        an agent or a template. Every page then hears the list again; an agent's move is its own row."""
        request = message.get("request") if isinstance(message.get("request"), (str, int)) else None
        if kind == "workspaces":
            queue.put_nowait(self._workspaces_message())
            return
        try:
            if kind == "workspace_save":
                given = message.get("id")
                row = self.workspaces.rename(given, message.get("name")) if isinstance(given, str) and given \
                    else self.workspaces.create(message.get("name"))
                queue.put_nowait({"type": "workspace_saved", "request": request, "id": row["id"]})
            elif kind == "workspace_delete" and isinstance(message.get("id"), str):
                if self.workspaces.delete(message["id"]):
                    self.agents.ungroup(message["id"])
            elif kind == "workspace_assign":
                target = message.get("workspace")
                if target is not None and (not isinstance(target, str) or self.workspaces.get(target) is None):
                    raise ValueError(WORKSPACE_GONE)
                if isinstance(message.get("agent"), str):
                    self.agents.set_workspace(message["agent"], target)
                    return
                if not isinstance(message.get("template"), str):
                    return
                self.workspaces.assign_template(message["template"], target)
            else:
                return
        except ValueError as exc:
            queue.put_nowait({"type": "error", "text": str(exc), "request": request})
            return
        except OSError as exc:  # a read-only home, a full disk: nothing changed
            queue.put_nowait({"type": "error", "text": f"Couldn't save that: {exc.strerror or exc}",
                              "request": request})
            return
        self._send_all(self._workspaces_message())

    # ---- saved agents: the Agents page lists, saves and deletes them (AI Browser's own pages only) -------------------

    def _saved_snapshot(self) -> dict:
        """The saved agents, and Brave's profiles for their settings: each "ready" once AI Browser has learned it on
        this connection (else the page says "open it once")."""
        place = self.brave.place if self.brave is not None else None
        return {"type": "saved_agents", "agents": [saved.public() for saved in self.saved.all()],
                "profiles": [{**row, "ready": place.ready(row["folder"])} for row in self._profiles()]}

    def _saved_check(self, fields: dict) -> None:
        """What only the app can judge, before the file is written: a profile Brave lists, an account Settings lists,
        a folder a task may use. ValueError in the words the Agents page shows."""
        profile, account, folder = fields.get("profile"), fields.get("account"), fields.get("folder")
        # a list, not a set: a page's ["x"] is refused, never hashed (a TypeError would drop the window's socket)
        if profile not in (None, "") and profile not in [row["folder"] for row in self._profiles()]:
            raise ValueError(BAD_PROFILE)
        listed = self.accounts.get(account) if self.accounts is not None else account == "default" or None
        if account not in (None, "") and listed is None:
            raise ValueError(BAD_ACCOUNT)
        why = self.agents.folder_problem(folder) if isinstance(folder, str) and folder else None
        if why:
            raise ValueError(why)

    def _forget_tasks(self, slug: str) -> None:
        """A saved agent was deleted: its tasks (the templates that run as it) are deleted with it."""
        if self.workflows is None:
            return
        for workflow in self.workflows.all():
            if workflow.runs_as == slug:
                self.workflows.delete(workflow.slug)
        self.workflows_changed()

    def _saved_command(self, queue: asyncio.Queue, kind: str, message: dict) -> None:
        """The Agents page: the list, Save (a new agent, or an edit) and Delete agent. Every page then hears the list
        again. Nothing but these clicks writes an agent."""
        request = message.get("request") if isinstance(message.get("request"), (str, int)) else None
        if kind == "saved_agents":
            queue.put_nowait(self._saved_snapshot())
            return
        try:
            if kind == "saved_agent_save":
                fields = {key: message[key] for key in SAVED_FIELDS if key in message}
                self._saved_check(fields)
                saved = self.saved.save(fields)
                queue.put_nowait({"type": "saved_agent_saved", "request": request, "slug": saved.slug})
            elif kind == "saved_agent_delete":
                if not self.saved.delete(message.get("slug")):
                    raise ValueError(NOT_AN_AGENT)
                self.agents.forget_saved(message["slug"])  # a run at work goes on, as a one-off run
                self._forget_tasks(message["slug"])
        except ValueError as exc:
            queue.put_nowait({"type": "error", "text": str(exc), "request": request})
            return
        except OSError as exc:  # a read-only home, a full disk: nothing changed
            queue.put_nowait({"type": "error", "text": f"Couldn't save that: {exc.strerror or exc}",
                              "request": request})
            return
        self._send_all(self._saved_snapshot())

    def _tools_snapshot(self, account: str = "default", tools=None) -> dict:
        tools = tools if tools is not None else self.tools
        return {"type": "tools_snapshot", "account": account, "servers": tools.servers(),
                "always": sorted(tools.always())}

    def _snapshot(self) -> dict:
        return {"type": "snapshot", "agents": self.agents.snapshot()["agents"],
                "tabs": self.tabs.tabs() if self.tabs is not None else [],
                "tab_scope": self._tab_scope(),
                "skills_summary": self._skills_summary(), "max_working": self.agents.max_working,
                "default_model": self.default_model, "browser": self._browser_info(),
                "sessions": self._session_list(), "browser_clients": self._browser_clients(),
                "settings": self._settings_payload(), "accounts": self._account_rows(),
                "brain_limit": self.brain_limit, "workspaces": self.workspaces.list(),
                "auto_commands": powers.auto_commands(),  # Auto-approve may run commands here (a Mac, Windows)
                "auto_sandbox": powers.sandbox_on()}  # and in Claude Code's sandbox (a Mac): the switch's words

    # ---- AI accounts: Settings → Accounts, the pickers and Continue on (AI Browser's own pages only) -------------

    def _account_rows(self) -> list[dict]:
        return self.accounts.rows() if self.accounts is not None else []

    def _accounts_changed(self) -> None:
        self._send_all({"type": "accounts", "accounts": self._account_rows()})

    def _brain_limit_hit(self, limit: dict) -> None:
        """The Brain's account hit its usage limit: the Brain's card asks to continue on another account."""
        self.brain_limit = {"account": str(limit.get("account", "")), "resets_at": limit.get("resets_at")}
        self._send_all({"type": "brain_limit", "limit": self.brain_limit})
        self._accounts_changed()

    def _brain_switched(self) -> None:
        """The Brain's account changed (the card's click, or Settings): the card goes, and calls waiting at a limit
        run once more on the new account."""
        if self.brain_limit is not None:
            self.brain_limit = None
            self._send_all({"type": "brain_limit", "limit": None})
        if self.brain_account is not None:
            self.brain_account.switched()

    async def _refresh_accounts(self) -> None:
        """A page of ours opened: each account's status (kept 5 s), then the list to every page."""
        await self.accounts.refresh()
        self._accounts_changed()

    async def _account_command(self, queue: asyncio.Queue, kind: str, message: dict) -> None:
        if self.accounts is None:
            return
        request = message.get("request") if isinstance(message.get("request"), (str, int)) else None
        account_id = message.get("id") if isinstance(message.get("id"), str) else ""
        if kind == "accounts":
            self._job(self._refresh_accounts())
            return
        if kind == "account_move":
            self._job(self._move(queue, request, message))
            return
        if kind == "account_signin":
            await self._sign_in(queue, account_id, message.get("how"))
            return
        try:
            if kind == "account_add":
                account = self.accounts.add(message.get("name"))
                queue.put_nowait({"type": "account_added", "id": account.id, "request": request})
                self._job(self._refresh_accounts())  # its status at once, never "Checking…" until a page reopens
            elif kind == "account_add_existing":
                account = self.accounts.add_existing(message.get("name"), message.get("folder"))
                queue.put_nowait({"type": "account_added", "id": account.id, "request": request})
                self._job(self._refresh_accounts())  # a folder signed in already says so at once
            elif kind == "account_remove":
                self._check_unused(account_id)
                self.accounts.remove(account_id)
            elif kind == "account_default":
                self.accounts.set_default(account_id)
            elif kind == "account_brain":
                self.accounts.set_brain(account_id)
                self._brain_switched()
        except ValueError as exc:
            queue.put_nowait({"type": "error", "text": str(exc), "request": request})
            return
        except OSError as exc:  # a read-only home, a full disk: nothing changed
            queue.put_nowait({"type": "error", "text": f"Couldn't save that: {exc.strerror or exc}",
                              "request": request})
            return
        self._accounts_changed()

    def _check_unused(self, account_id: str) -> None:
        """Remove only forgets, so an open agent on that account would fail at its next start: it is refused."""
        account = self.accounts.get(account_id)
        using = next((agent for agent in self.agents.agents.values() if agent.account["id"] == account_id), None)
        if account is not None and using is not None:
            raise ValueError(IN_USE.format(name=account.name, label=f"{using.number} · {using.name}"))

    async def _sign_in(self, queue: asyncio.Queue, account_id: str, how) -> None:
        """Sign in (Settings → Accounts). Open Terminal opens a terminal window running Claude Code on the account's
        folder; Copy the command is the page's own. Either way the app then looks at the account's status every
        SIGNIN_EVERY seconds until it is signed in, for SIGNIN_WAIT seconds at most. The user signs in there and in
        their browser: AI Browser never sees a password or a token."""
        account = self.accounts.get(account_id)
        if account is None or how not in ("terminal", "copy"):
            return
        if how == "terminal":
            try:
                claude = claude_argv(self.accounts.claude)
            except OSError:  # an npm claude.cmd on Windows (ClaudeNotUsable): Copy the command still works
                claude = None
            opened = claude is not None and await asyncio.to_thread(
                self.open_terminal, claude, self.accounts.signin_folder(account.id), self.accounts.env_for(account.id))
            queue.put_nowait({"type": "account_signin", "id": account.id, "opened": bool(opened)})
        task = self._signing_in.get(account.id)
        if task is None or task.done():
            self._signing_in[account.id] = asyncio.ensure_future(self._until_signed_in(account.id))

    async def _until_signed_in(self, account_id: str) -> None:
        deadline, last = time.monotonic() + SIGNIN_WAIT, None
        while time.monotonic() < deadline and self.accounts.get(account_id) is not None:
            status = await self.accounts.status(account_id, fresh=True)
            if status != last:
                last = status
                self._accounts_changed()
            if status["signed_in"] is True:
                return
            await asyncio.sleep(SIGNIN_EVERY)

    async def _move(self, queue: asyncio.Queue, request, message: dict) -> None:
        """Continue on another account: the user's click on an agent's row or drawer. Its open tabs go into the
        hand-over note by their titles and addresses, as page data."""
        agent_id, account_id = message.get("id"), message.get("account")
        if not isinstance(agent_id, str) or not isinstance(account_id, str):
            return
        agent = self.agents.agents.get(agent_id)
        if agent is None:
            return
        listed = {tab["target"]: tab for tab in (self.tabs.tabs() if self.tabs is not None else [])
                  if isinstance(tab, dict) and isinstance(tab.get("target"), str)}
        tabs = [{"url": str(listed[target].get("url", "")), "title": str(listed[target].get("title", ""))}
                for target in [*agent.tabs, *agent.adopted] if target in listed]
        error = await self.agents.move(agent_id, account_id, tabs)
        if error:
            queue.put_nowait({"type": "error", "text": error, "request": request})

    # ---- skills -----------------------------------------------------------------------------------------------

    def _skill_catalog(self) -> Catalog:
        if self._catalog is None:  # the same skills the agents' engines see
            self._catalog = Catalog.of_user(project_root() / "skills", set(load_config(self.home).blocked_skills))
        return self._catalog

    def _skills(self) -> list:
        return self._skill_catalog().all()

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

    def _blocked_skills(self) -> list[str]:
        return sorted(load_config(self.home).blocked_skills)

    def _skill_block(self, queue: asyncio.Queue, message: dict) -> None:
        """Knowledge's Remove and Bring back: a skill hidden from AI Browser's agents, or shown again, in
        <home>/config.json. Its files are the user's and stay where they are."""
        request = message.get("request") if isinstance(message.get("request"), (str, int)) else None
        ref = message.get("ref")
        if not isinstance(ref, str) or not SKILL_REF.match(ref):
            queue.put_nowait({"type": "error", "text": "That isn't a skill", "request": request})
            return
        try:
            set_blocked(self.home, ref, message.get("blocked") is True)
        except (ValueError, OSError) as exc:
            queue.put_nowait({"type": "error", "text": str(exc), "request": request})
            return
        self.skills_changed()

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
