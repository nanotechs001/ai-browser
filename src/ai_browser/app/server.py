"""The AI Browser app server: AI Home's, the chat panel's and the extension worker's only way to the agents.

It listens on 127.0.0.1 only. UI sockets need the extension token and our extension's origin; the agents' engines
report their tabs to /agent-events with a token of their own. Everything that happens to an agent is broadcast to
every socket; an agent's conversation is sent on request (`events`), so a page opened later can draw it whole."""

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
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from .. import platforms
from ..appbrowser import extension_path
from ..brain.service import BrainService
from ..brain.skillwriter import SkillError, SkillWriter
from ..brain.tools import ToolsConfig
from ..brain.workflows import WorkflowRunner, WorkflowStore
from ..checks import KINDS
from ..config import load_config, project_root
from ..engine import _alive
from ..grouping import MARKER
from ..hearing.service import HearingService, unavailable_status
from ..live import _bind, _QuietServer, _serve
from ..skills import Catalog
from .agents import Agent, AgentManager
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
TELL_CARD_MESSAGES = {"tell_confirm", "tell_dismiss"}  # an inbox card's Start (Send) and Cancel: AI Browser's own
# pages only. The watcher may ask for a card (tell), never run one.
TOOLS_MESSAGES = {"tools", "tool_set", "tool_allow", "tool_forget", "permission"}
WORKFLOW_MESSAGES = {"workflows", "workflow_save", "workflow_delete", "workflow_run"}
SKILL_MESSAGES = {"skill_draft", "skill_save"}
HEARING_MESSAGES = {"hearing", "hearing_download", "hearing_cancel", "listen_start", "listen_chunk", "listen_end",
                    "listen_cancel"}  # push-to-talk: only AI Browser's own pages, never the watcher
TALK_MESSAGES = {"brain_ask", "brain_confirm", "brain_dismiss"}  # the talk with the Brain: the same
_TALK_ID = re.compile(r"^[A-Za-z0-9-]{1,40}$")
CHECK_MESSAGES = {"check_continue", "check_skip"}  # a bot check's buttons; the watcher may Continue, never Skip
BRAVE_MESSAGES = {"brave_connect", "hand_tab", "take_back", "browser_disconnect"}  # only AI Browser's own pages
CHECK_SITE = re.compile(r"[a-z0-9.-]{1,253}")  # a host name, nothing else
CHECK_LIVE = re.compile(r"http://127\.0\.0\.1:\d{1,5}/live\?token=[A-Za-z0-9_-]{1,64}")  # an engine's live view
WORKFLOW_FIELDS = ("slug", "name", "instructions", "trigger", "site", "when", "schedule", "run", "tools", "skills",
                   "model")
WATCH_FIELDS = ("site", "label", "url_match", "selector", "instructions", "enabled")
SETUP_PAGE = Path(__file__).with_name("setup.html")
SOURCES = {"personal": "personal", "anthropic-skills": "claude.ai", "ai-browser": "ai-browser"}  # else: plugins
SESSION_ID = re.compile(r"^cc-[0-9a-z-]{1,40}$")  # a Claude Code session's id (cc-<task id>)
AGENT_ID = re.compile(r"^a[0-9]{1,9}$")  # an agent's id (a<number>)
SESSION_SWEEP = 30  # seconds between two looks at the sessions' processes
YOU = {"kind": "you"}


reveal_folder = platforms.reveal  # a file manager window with the folder selected; False when none could open
GOTO_MAC = "press ⌘⇧G, paste the path and press Enter"
GOTO_OTHER = "click the address bar at the top of the folder window, paste the path and press Enter"


def setup_page(extension: str, watcher: str, key: str, system: str | None = None) -> str:
    """The one-time setup page, worded for the computer it runs on; every value is escaped."""
    values = {"{{FILE_MANAGER}}": platforms.file_manager(system),
              "{{GOTO}}": platforms.shortcut(GOTO_MAC, GOTO_OTHER, system),
              "{{THIS_COMPUTER}}": platforms.this_computer(system),
              "{{FOLDER}}": extension, "{{WATCHER}}": watcher, "{{KEY}}": key}
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


class AppServer:
    def __init__(self, home: Path, agents: AgentManager, tabs=None, catalog: Catalog | None = None,
                 host: str = "127.0.0.1", ports: range = APP_PORTS, default_model: str = "sonnet",
                 brain: BrainService | None = None, tools: ToolsConfig | None = None,
                 workflows: WorkflowStore | None = None, runner: WorkflowRunner | None = None,
                 skill_writer: SkillWriter | None = None, hearing: HearingService | None = None):
        self.home = Path(home)
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
        self._watcher: tuple[WebSocket, asyncio.Queue] | None = None  # Brave's watcher (the latest one to connect)
        if brain is not None:
            brain.broadcast = self._send_all
            brain.send_watcher = self._to_watcher
        self.default_model = default_model if default_model in MODELS else "sonnet"  # ai-browser app --model
        self.host = host
        self.ports = ports
        self.token = secrets.token_urlsafe(24)  # AI Home, the panel and the worker (in the extension's config.json)
        self.tokens = Tokens()  # each agent's own token (and each session's for /cdp), new every run
        self.session_token = secrets.token_urlsafe(24)  # Claude Code sessions (in <home>/app/link.json, mode 0600)
        self.groups = GroupKeeper(self._to_watcher, on_change=self._browser_changed)  # tab groups, through the watcher
        self.brave = None  # BraveLink in brave mode (attach_brave): the user's Brave
        self.sessions: dict[str, dict] = {}  # Claude Code sessions browsing in Brave while the app runs
        self._thread_urls: dict[str, str] = {}  # open_thread request -> its address (the Brain's group in AI Home)
        self._sweeper: asyncio.Task | None = None
        self.url: str | None = None
        self.port = 0
        self.extension_seen = False  # the extension has connected: the one-time setup is done
        self.origin_mismatch: str | None = None  # an extension with our token, from an origin we didn't compute
        self.out: Callable[[str], None] = print  # where the app's one-line notes go (run_app passes its own)
        self.setup_key = secrets.token_urlsafe(16)  # only the setup page has it: other sites can't open Finder
        self.reveal = reveal_folder
        self.tabs = None
        self._catalog = catalog
        self._origins: set[str] = set()
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

    def allow_origin(self, origin: str, watcher: bool = False) -> None:
        """An extension's origin (chrome-extension://<id>); nothing else may open a socket. Only the watcher's
        origin may connect as the watcher and report what it reads."""
        self._origins.add(origin)
        if watcher:
            self._watcher_origins.add(origin)

    def _mismatch(self, origin: str) -> None:
        """Only an extension holding our config.json has the token: from an origin we didn't compute, it means an
        extension ID is computed wrong on this computer. The socket is still refused; this says so, once."""
        if origin == self.origin_mismatch:
            return
        self.origin_mismatch = origin
        app = ", ".join(sorted(self._origins - self._watcher_origins)) or "?"
        watcher = ", ".join(sorted(self._watcher_origins)) or "?"
        self.out(f"An AI Browser extension connected as {origin}, but the app expected {app} (AI Browser) or "
                 f"{watcher} (the watcher): please report this")

    def token_for(self, agent_id: str) -> str:
        """An agent's own token (minted when it is created): its engine's key to the reports and to /cdp."""
        return self.tokens.mint(agent_id)

    def attach_tabs(self, tabs) -> None:
        """The TabWatch, once AI Browser is open: the tab list, Watch and thumbnails."""
        self.tabs = tabs
        tabs.on_change(lambda listing: self._send_all({"type": "tabs", "tabs": listing}))

    async def start(self) -> str:
        app = Starlette(routes=[Route("/health", self._health), Route("/setup", self._setup),
                                Route("/setup/status", self._setup_status),
                                Route("/setup/reveal", self._setup_reveal, methods=["POST"]),
                                Route("/agent-events", self._agent_events, methods=["POST"]),
                                Route("/agent-claim", self._agent_claim, methods=["POST"]),
                                Route("/agent-status", self._agent_status),
                                Route("/agent-hello", self._agent_hello, methods=["POST"]),
                                Route("/agent-bye", self._agent_bye, methods=["POST"]),
                                WebSocketRoute("/ws", self._socket), WebSocketRoute("/cdp", self._cdp)])
        self._fanout = asyncio.create_task(self._forward())
        self._sweeper = asyncio.create_task(self._sweep_sessions())
        if self.brain is not None:
            await self.brain.start()
        for port in self.ports:
            sock = _bind(self.host, port)
            if sock is None:
                continue
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
                self.port = port
                if self.brave is not None:
                    self.brave.relay.port = port
                return self.url
            sock.close()
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

    def _extension_folder(self) -> str:
        return extension_path(self.home / "app" / "extension")

    def _watcher_folder(self) -> str:
        return extension_path(self.watcher_folder or self.home / "app" / "watcher")

    async def _setup(self, request: Request) -> HTMLResponse:
        return HTMLResponse(setup_page(self._extension_folder(), self._watcher_folder(), self.setup_key))

    async def _setup_reveal(self, request: Request) -> Response:
        if not hmac.compare_digest(request.headers.get("x-aib-setup", "").encode(), self.setup_key.encode()):
            return Response(status_code=403)
        watcher = request.query_params.get("which") == "watcher"
        shown = self.reveal(self._watcher_folder() if watcher else self._extension_folder())
        return Response(status_code=204 if shown else 501)  # 501: nothing could show it (no file manager)

    async def _setup_status(self, request: Request) -> JSONResponse:
        seen = self.brain is not None and self.brain.store.watcher_seen
        answer = {"installed": self.extension_seen, "watcher": seen}
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
        relay.port = self.port
        relay.handed = self._handed_to
        relay.may_open = lambda identity: bool(SESSION_ID.match(identity)) or self.agents.working(identity)
        self.agents.own_tabs = relay.own_targets
        relay.on_grant(lambda identity, target: self._own(target, self._owner_of(identity)))
        relay.on_change(self._clients_changed)
        brave.on_state(lambda state: self._browser_changed())
        self._browser_changed()
        self._send_all({"type": "tabs", "tabs": brave.tabs()})  # pages already open see Brave's list at once

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
        if self.brave is None:
            return {"kind": "app", "name": "AI Browser", "state": "connected", "groups": "on"}
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
        token = ws.query_params.get("token", "")
        origin = ws.headers.get("origin")
        token_ok = hmac.compare_digest(token.encode(), self.token.encode())
        if not token_ok or origin not in self._origins:
            # Only once the app has allowed its computed IDs: during start-up the extension can connect before
            # allow_origin runs (AI Browser is launched in a thread), and that is no mismatch.
            if token_ok and self._origins and isinstance(origin, str) and origin.startswith("chrome-extension://"):
                self._mismatch(origin)
            await ws.close(code=REFUSED)
            return
        if origin not in self._watcher_origins:
            self.extension_seen = True  # AI Browser's own extension (Brave's watcher is set up apart)
        self._origin_of[ws] = origin
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
        with contextlib.suppress(Exception):
            while True:
                await ws.send_json(await queue.get())

    def _unsubscribe(self, ws: WebSocket) -> None:
        self._sockets.pop(ws, None)
        self._origin_of.pop(ws, None)
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

    async def _handle(self, ws: WebSocket, queue: asyncio.Queue, message: dict) -> None:
        kind, agent_id, agents = message.get("type"), str(message.get("id", "")), self.agents
        if kind == "hello" and message.get("view") == "watcher" and self.brain is not None \
                and self._origin_of.get(ws) in self._watcher_origins:
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
            from_watcher = self._origin_of.get(ws) in self._watcher_origins
            if self.brain is not None and not (from_watcher and kind in TELL_CARD_MESSAGES):
                # the watcher's origin may ask for a card (tell), never run one: its typed yes is only a question
                await self._brain_command(queue, kind, agent_id, message, from_watcher=from_watcher)
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
        elif kind in CHECK_MESSAGES:  # only a click in one of our pages (or the watcher's Continue) answers a check
            if kind == "check_continue":
                await agents.continue_check(agent_id)
            elif self._origin_of.get(ws) not in self._watcher_origins:
                await agents.skip_check(agent_id)
        elif kind in BRAVE_MESSAGES:  # (everyday Brave) only AI Browser's own pages, never the watcher's origin
            if self._origin_of.get(ws) not in self._watcher_origins:
                await self._brave_command(queue, kind, message)
        elif kind in HEARING_MESSAGES:
            if self._origin_of.get(ws) not in self._watcher_origins:  # only AI Browser's own pages talk or listen
                self._hearing_command(ws, queue, kind, message)
        elif kind in TALK_MESSAGES:
            if self._origin_of.get(ws) not in self._watcher_origins:
                self._talk_command(queue, kind, message)
        elif kind == "hello":
            if ws not in self._sockets:  # the snapshot, then every broadcast (no await between the two)
                queue.put_nowait(self._snapshot())
                self._sockets[ws] = queue
        elif kind == "new_task":
            request = message.get("request") if isinstance(message.get("request"), (str, int)) else None
            text = _text(message.get("text"))
            if not text:
                queue.put_nowait({"type": "error", "text": "Write what the agent should do", "request": request})
                return
            skills = [skill for skill in message.get("skills") or [] if isinstance(skill, str)][:20]
            adopt = message.get("adopt") if isinstance(message.get("adopt"), str) and message.get("adopt") else None
            handed = self._handable(adopt) if adopt and self.brave is not None else None
            if adopt and self.brave is not None and handed is None:  # in brave mode: only a tab Brave lists
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
                if isinstance(message.get("item"), str) and self.brain is not None:
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
                "skills_summary": self._skills_summary(), "max_working": self.agents.max_working,
                "default_model": self.default_model, "browser": self._browser_info(),
                "sessions": self._session_list(), "browser_clients": self._browser_clients()}

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
