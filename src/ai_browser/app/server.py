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
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from ..brain.service import BrainService
from ..brain.skillwriter import SkillError, SkillWriter
from ..brain.tools import ToolsConfig
from ..brain.workflows import WorkflowRunner, WorkflowStore
from ..config import load_config, project_root
from ..live import _bind, _QuietServer, _serve
from ..skills import Catalog
from .agents import Agent, AgentManager

APP_PORTS = range(8792, 8812)
MODELS = {"opus", "sonnet", "haiku"}
REFUSED = 4403  # WebSocket close code for a wrong token or origin
PING_EVERY = 20  # seconds: a message now and then keeps the extension's service worker, and its socket, alive
THUMB_EVERY = 2  # seconds between two thumbnails of one agent's tab
TEXT_LIMIT = 20_000  # characters of a task or a message
WATCHER_MESSAGES = {"items", "replied", "thread", "filled", "reader_status"}  # only Brave's watcher sends these
BRAIN_MESSAGES = {"brain", "draft", "approve", "hand", "done", "tell", "watch_set", "watch_remove", "pause", "style"}
TOOLS_MESSAGES = {"tools", "tool_set", "tool_allow", "tool_forget", "permission"}
WORKFLOW_MESSAGES = {"workflows", "workflow_save", "workflow_delete", "workflow_run"}
SKILL_MESSAGES = {"skill_draft", "skill_save"}
WORKFLOW_FIELDS = ("slug", "name", "instructions", "trigger", "site", "when", "schedule", "run", "tools", "skills",
                   "model")
WATCH_FIELDS = ("site", "label", "url_match", "selector", "instructions", "enabled")
SETUP_PAGE = Path(__file__).with_name("setup.html")
SOURCES = {"personal": "personal", "anthropic-skills": "claude.ai", "ai-browser": "ai-browser"}  # else: plugins


def reveal_in_finder(path: str) -> None:
    """Show a folder in Finder, selected, so it can be dragged onto chrome://extensions (macOS only)."""
    if sys.platform == "darwin":
        with contextlib.suppress(OSError):
            subprocess.Popen(["open", "-R", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _first_line(text, limit: int = 200) -> str:
    return next((line.strip() for line in str(text or "").splitlines() if line.strip()), "")[:limit]


def _text(value) -> str:
    return value.strip()[:TEXT_LIMIT] if isinstance(value, str) else ""


def _tab(value) -> dict:
    """The tab a message was written beside: page data, trimmed again by the bridge."""
    if not isinstance(value, dict):
        return {}
    return {key: value[key][:2000] for key in ("url", "title") if isinstance(value.get(key), str)}


class AppServer:
    def __init__(self, home: Path, agents: AgentManager, tabs=None, catalog: Catalog | None = None,
                 host: str = "127.0.0.1", ports: range = APP_PORTS, default_model: str = "sonnet",
                 brain: BrainService | None = None, tools: ToolsConfig | None = None,
                 workflows: WorkflowStore | None = None, runner: WorkflowRunner | None = None,
                 skill_writer: SkillWriter | None = None):
        self.home = Path(home)
        self.agents = agents
        self.brain = brain
        self.skill_writer = skill_writer  # skills the Brain drafts, written only on the user's Save
        if skill_writer is not None and skill_writer.on_saved is None:
            skill_writer.on_saved = self.skills_changed
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
        self.agent_token = secrets.token_urlsafe(24)  # the agents' engines (in each agent's mcp.json)
        self.url: str | None = None
        self.extension_seen = False  # the extension has connected: the one-time setup is done
        self.setup_key = secrets.token_urlsafe(16)  # only the setup page has it: other sites can't open Finder
        self.reveal = reveal_in_finder
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
        if tabs is not None:
            self.attach_tabs(tabs)

    def allow_origin(self, origin: str, watcher: bool = False) -> None:
        """An extension's origin (chrome-extension://<id>); nothing else may open a socket. Only the watcher's
        origin may connect as the watcher and report what it reads."""
        self._origins.add(origin)
        if watcher:
            self._watcher_origins.add(origin)

    def attach_tabs(self, tabs) -> None:
        """The TabWatch, once AI Browser is open: the tab list, Watch and thumbnails."""
        self.tabs = tabs
        tabs.on_change(lambda listing: self._send_all({"type": "tabs", "tabs": listing}))

    async def start(self) -> str:
        app = Starlette(routes=[Route("/health", self._health), Route("/setup", self._setup),
                                Route("/setup/status", self._setup_status),
                                Route("/setup/reveal", self._setup_reveal, methods=["POST"]),
                                Route("/agent-events", self._agent_events, methods=["POST"]),
                                WebSocketRoute("/ws", self._socket)])
        self._fanout = asyncio.create_task(self._forward())
        if self.brain is not None:
            await self.brain.start()
        for port in self.ports:
            sock = _bind(self.host, port)
            if sock is None:
                continue
            self._server = _QuietServer(uvicorn.Config(app, host=self.host, port=port, log_level="warning",
                                                       access_log=False, lifespan="off"))
            self._task = asyncio.create_task(_serve(self._server, sock))
            for _ in range(200):
                if self._server.started or self._task.done():
                    break
                await asyncio.sleep(0.01)
            if self._server.started:
                self.url = f"http://{self.host}:{port}"
                return self.url
            sock.close()
        raise RuntimeError(f"no free port for the AI Browser app server ({self.ports.start}-{self.ports.stop - 1})")

    async def stop(self) -> None:
        if self.brain is not None:
            await self.brain.stop()
        await self.agents.close_all()  # every agent's Claude Code process ends with the app
        for task in [self._fanout, *self._jobs, *(state["task"] for state in self._thumbs.values())]:
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
        return os.path.realpath(self.home / "app" / "extension")

    def _watcher_folder(self) -> str:
        return os.path.realpath(self.watcher_folder or self.home / "app" / "watcher")

    async def _setup(self, request: Request) -> HTMLResponse:
        page = SETUP_PAGE.read_text().replace("{{FOLDER}}", html.escape(self._extension_folder()))
        page = page.replace("{{WATCHER}}", html.escape(self._watcher_folder()))
        return HTMLResponse(page.replace("{{KEY}}", self.setup_key))

    async def _setup_reveal(self, request: Request) -> Response:
        if not hmac.compare_digest(request.headers.get("x-aib-setup", "").encode(), self.setup_key.encode()):
            return Response(status_code=403)
        watcher = request.query_params.get("which") == "watcher"
        self.reveal(self._watcher_folder() if watcher else self._extension_folder())
        return Response(status_code=204)

    async def _setup_status(self, request: Request) -> JSONResponse:
        seen = self.brain is not None and self.brain.store.watcher_seen
        return JSONResponse({"installed": self.extension_seen, "watcher": seen})

    async def _agent_events(self, request: Request) -> Response:
        given = request.headers.get("x-aib-agent-token", "")
        if not hmac.compare_digest(given.encode(), self.agent_token.encode()):
            return Response(status_code=403)
        try:
            report = await request.json()
        except ValueError:
            return Response(status_code=400)
        if isinstance(report, dict) and all(isinstance(report.get(key), str) for key in ("agent", "kind", "target")):
            self.agents.tab_event(report["agent"], report["kind"], report["target"], bool(report.get("adopted")))
        return Response(status_code=204)

    # ---- sockets ----------------------------------------------------------------------------------------------

    async def _socket(self, ws: WebSocket) -> None:
        await ws.accept()  # accept first, so a refusal arrives as a close code the page can read
        token = ws.query_params.get("token", "")
        origin = ws.headers.get("origin")
        if not hmac.compare_digest(token.encode(), self.token.encode()) or origin not in self._origins:
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
        writer = self._writers.pop(ws, None)
        if writer is not None:
            writer.cancel()
        if self._watcher is not None and self._watcher[0] is ws:
            self._watcher = None
            if self.brain is not None:
                self.brain.watcher = False

    def _send_all(self, message: dict) -> None:
        for queue in self._sockets.values():
            queue.put_nowait(message)

    def _to_watcher(self, message: dict) -> bool:
        """A message for Brave's watcher; False when it isn't connected."""
        if self._watcher is None:
            return False
        self._watcher[1].put_nowait(message)
        return True

    async def _forward(self) -> None:
        while True:
            message = await self._feed.get()
            if message.get("type") == "agent_closed":
                self._thumbs.pop(str(message.get("id")), None)
            self._send_all(message)
            if message.get("type") == "permission_request":
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
        elif kind in WATCHER_MESSAGES:
            if self.brain is not None and self._watcher is not None and self._watcher[0] is ws:
                await self._from_watcher(kind, message)
        elif kind in BRAIN_MESSAGES:
            if self.brain is not None:
                await self._brain_command(queue, kind, agent_id, message)
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
            model = message.get("model") if message.get("model") in MODELS else self.default_model
            agent = await agents.create(text, skills, model, adopt, _tab(message.get("tab")))
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
        brain = self.brain
        site = message.get("site") if isinstance(message.get("site"), str) else ""
        if kind == "items":
            await brain.on_items(site, message.get("items"), baseline=message.get("baseline") is True)
        elif kind == "replied" and isinstance(message.get("id"), str):
            brain.on_replied(site, message["id"])
        elif kind == "thread":
            brain.on_thread(str(message.get("request", "")), message.get("text") or "", message.get("error") or "")
        elif kind == "filled":
            brain.on_filled(str(message.get("request", "")), message.get("ok") is True, _text(message.get("reason")))
        elif kind == "reader_status":
            brain.reader_status(site, message.get("ok") is True, _text(message.get("note")))

    async def _brain_command(self, queue: asyncio.Queue, kind: str, item_id: str, message: dict) -> None:
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
        elif kind == "tell":
            self._job(brain.tell(item_id, _text(message.get("text"))))
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
                    page = await self.tabs.page_text(message["page_target"])
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
                "default_model": self.default_model}

    # ---- skills -----------------------------------------------------------------------------------------------

    def _skills(self) -> list:
        if self._catalog is None:  # the same skills the agents' engines see
            self._catalog = Catalog.discover(Path.home() / ".claude",
                                             Path.home() / "Library" / "Application Support" / "Claude",
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
