"""Several Claude agents at once. Each agent is its own Claude Code process (a ClaudeBridge) working in its own tabs.

Up to `max_working` agents work at the same time; the rest wait in line, first come first served. A message sent to an
agent that is working waits for that agent's turn to end and then runs in the same slot. Every change is broadcast to
the app's sockets: {"type": "agent", "agent": …} for the row, {"type": "agent_event", …} for the conversation."""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from .bridge import ClaudeBridge

COLORS = ("blue", "green", "purple", "orange", "cyan", "pink", "yellow", "red", "grey")  # Chrome's tab group colours
KEEP_EVENTS = 5000  # an agent's conversation kept for the chat views (the newest)
NAME_LIMIT = 40
CLOSE_WAIT = 10  # seconds a closing agent's turn gets to end after Stop
_SCHEME = re.compile(r"\bhttps?://(?:www\.)?", re.IGNORECASE)
_FILLER = {"and", "or", "then", "to", "the", "a", "an", "of", "in", "on", "with", "for", "from"}


def _name(text: str) -> str:
    """The task's first words, up to NAME_LIMIT characters: addresses without their scheme, no dangling "and"."""
    words, name = " ".join(_SCHEME.sub("", text).split()), ""
    for word in words.split(" "):
        if len(name) + len(word) + bool(name) > NAME_LIMIT:
            break
        name = f"{name} {word}" if name else word
    if len(name) < 20 and len(words) > len(name):  # a long word (an address, say) would leave too little
        return words[:NAME_LIMIT - 1].rstrip() + "…"
    parts = name.split(" ")
    while len(parts) > 1 and parts[-1].lower().strip(",.;:") in _FILLER:
        parts.pop()
    return " ".join(parts).rstrip(",.;:") or "task"


@dataclass
class Agent:
    id: str
    name: str
    color: str
    model: str
    bridge: ClaudeBridge = field(repr=False)
    state: str = "waiting"  # working | waiting | your_turn | stopped | failed
    status: str = ""  # the tool running now and its summary, or why it failed
    last_action: str = ""  # "click e14 · 38 ms"
    tabs: list[str] = field(default_factory=list)  # targets the agent opened (closed when the user closes it)
    adopted: list[str] = field(default_factory=list)  # the user's tabs it works in (never closed)
    working_tab: str | None = None
    loaded_skills: list[str] = field(default_factory=list)
    seconds: float = 0.0
    cost: float = 0.0
    created: float = field(default_factory=time.time)
    events: deque = field(default_factory=lambda: deque(maxlen=KEEP_EVENTS), repr=False)
    pending: list = field(default_factory=list, repr=False)  # (text, tab, skills) waiting for this agent's turn
    tools: dict = field(default_factory=dict, repr=False)  # tool_use id -> (name, summary)
    permission: dict | None = None  # a tool request waiting for the user: {request, server, tool, input}

    PUBLIC: ClassVar[tuple[str, ...]] = ("id", "name", "color", "model", "state", "status", "last_action", "tabs",
                                         "adopted", "working_tab", "loaded_skills", "seconds", "cost", "created",
                                         "permission")

    def public(self) -> dict:
        return {key: list(value) if isinstance(value, list) else value
                for key, value in ((key, getattr(self, key)) for key in self.PUBLIC)}


class AgentManager:
    def __init__(self, home: Path, claude: str | None = None, max_working: int = 3, env: dict[str, str] | None = None,
                 close_tabs: Callable[[list[str]], Awaitable[None]] | None = None,
                 on_action: Callable[[Agent], None] | None = None):
        self.home = Path(home)
        self.claude = claude
        self.max_working = max(1, max_working)
        self.env = dict(env or {})  # for every agent's ai-browser server: AIB_APP_PROFILE, AIB_APP_EVENTS...
        self.close_tabs = close_tabs  # set by the app once AI Browser is open
        self.on_action = on_action  # after each action: the app takes a thumbnail
        self.tools = None  # the user's MCP servers (ToolsConfig), set by the app: agents ask before using them
        self._asks: dict[str, asyncio.Future] = {}  # agent id -> its tool request waiting for the user
        self.agents: dict[str, Agent] = {}
        self._line: deque[str] = deque()  # agents waiting for a free slot, first come first served
        self._turns: dict[str, asyncio.Task] = {}  # agents working now
        self._queues: list[asyncio.Queue] = []
        self._seq = 0

    # ---- views --------------------------------------------------------------------------------------------

    def snapshot(self) -> dict:
        newest_first = sorted(self.agents.values(), key=lambda agent: int(agent.id[1:]), reverse=True)
        return {"agents": [agent.public() for agent in newest_first]}

    def events_of(self, agent_id: str) -> list[dict]:
        agent = self.agents.get(agent_id)
        return list(agent.events) if agent else []

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._queues.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with contextlib.suppress(ValueError):
            self._queues.remove(queue)

    def _broadcast(self, message: dict) -> None:
        for queue in list(self._queues):
            queue.put_nowait(message)

    def _changed(self, agent: Agent) -> None:
        self._broadcast({"type": "agent", "agent": agent.public()})

    def _record(self, agent: Agent, event: dict) -> None:
        agent.events.append(event)
        self._broadcast({"type": "agent_event", "id": agent.id, "event": event})

    # ---- commands -----------------------------------------------------------------------------------------

    async def create(self, text: str, skills=(), model: str = "sonnet", adopt: str | None = None,
                     tab: dict | None = None, servers: list[str] | None = None) -> Agent:
        """A new agent for `text`; with `adopt`, it works in that tab of the user's (started from the panel). Its MCP
        servers are the ones switched on in Tools, or only `servers` of them (a workflow's own list)."""
        self._seq += 1
        agent_id = f"a{self._seq}"
        env = {**self.env, "AIB_APP_AGENT": agent_id, **({"AIB_APP_ADOPT": adopt} if adopt else {})}
        bridge = ClaudeBridge(self.home, model=model, claude=self.claude, env=env, agent_id=agent_id,
                              tools=self.tools, servers=servers,
                              on_permission=lambda request, agent_id=agent_id: self._ask(agent_id, request))
        agent = Agent(agent_id, _name(text), COLORS[(self._seq - 1) % len(COLORS)], model, bridge)
        if adopt:  # the panel can show this agent for that tab before Claude's first step
            agent.adopted.append(adopt)
            agent.working_tab = adopt
        agent.pending.append((text, tab or {}, list(skills)))
        self.agents[agent_id] = agent
        self._changed(agent)
        self._line.append(agent_id)
        self._pump()
        return agent

    async def send(self, agent_id: str, text: str, tab: dict | None = None) -> None:
        agent = self.agents.get(agent_id)
        if agent is None:
            return
        agent.pending.append((text, tab or {}, []))
        if agent_id in self._turns or agent_id in self._line:  # it gets its turn after the current one
            self._record(agent, {"type": "queued", "text": text})
            return
        agent.state = "waiting"
        self._changed(agent)
        self._line.append(agent_id)
        self._pump()

    async def stop(self, agent_id: str) -> None:
        """Stop the agent's answer (its process and tabs stay), or take it out of the line."""
        agent = self.agents.get(agent_id)
        if agent is None:
            return
        agent.pending.clear()
        if agent.permission is not None:  # a tool request still waiting: Stop is a no
            self.answer_permission(agent_id, agent.permission["request"], "deny")
        if agent_id in self._line:
            self._line.remove(agent_id)
            agent.state = "stopped"
            self._changed(agent)
        elif agent_id in self._turns:
            await agent.bridge.stop()

    async def close(self, agent_id: str, keep_tabs: bool = False) -> None:
        """End the agent: its Claude Code process, and the tabs it opened (never the user's)."""
        agent = self.agents.get(agent_id)
        if agent is None:
            return
        await self.stop(agent_id)
        turn = self._turns.get(agent_id)
        if turn is not None:
            await asyncio.wait({turn}, timeout=CLOSE_WAIT)
            turn.cancel()
        await agent.bridge.close()
        self.agents.pop(agent_id, None)
        if not keep_tabs and agent.tabs and self.close_tabs is not None:
            with contextlib.suppress(Exception):
                await self.close_tabs(list(agent.tabs))
        self._broadcast({"type": "agent_closed", "id": agent_id})

    async def close_all(self) -> None:
        """The app is ending: every agent's process (AI Browser closes with the app, so tabs are left to it)."""
        for agent_id in list(self.agents):
            await self.close(agent_id, keep_tabs=True)

    async def _ask(self, agent_id: str, request: dict) -> str:
        """An agent wants a tool that isn't allowed yet: it waits ("needs you") for the user's answer."""
        agent = self.agents.get(agent_id)
        if agent is None:
            return "deny"
        if self.tools is not None and request["tool"] in self.tools.always():
            return "once"  # allowed always since this agent started
        future = asyncio.get_running_loop().create_future()
        self._asks[agent_id] = future
        agent.permission = {key: request[key] for key in ("request", "server", "tool", "input")}
        agent.state = "needs_you"
        self._changed(agent)
        self._broadcast({"type": "permission_request", "agent": agent_id, **agent.permission})
        try:
            return await future
        finally:
            self._asks.pop(agent_id, None)
            agent.permission = None
            if agent.state == "needs_you":
                agent.state = "working"
            self._changed(agent)

    def answer_permission(self, agent_id: str, request: str, answer: str) -> None:
        """The user's answer: "once", "always" (remembered in Tools) or "deny"."""
        agent, future = self.agents.get(agent_id), self._asks.get(agent_id)
        if agent is None or future is None or future.done() or agent.permission is None \
                or agent.permission["request"] != request:
            return
        answer = answer if answer in ("once", "always") else "deny"
        if answer == "always" and self.tools is not None:
            self.tools.allow_always(agent.permission["tool"])
        future.set_result(answer)

    def set_model(self, agent_id: str, model: str) -> None:
        agent = self.agents.get(agent_id)
        if agent is not None:
            agent.model = agent.bridge.model = model  # from its next message, in the same process
            self._changed(agent)

    def tab_event(self, agent_id: str, kind: str, target: str, adopted: bool = False) -> None:
        """An agent's engine reports a tab: tab_opened, tab_closed or working_tab."""
        agent = self.agents.get(agent_id)
        if agent is None or not target:
            return
        if kind in ("tab_opened", "working_tab"):
            if target not in agent.tabs and target not in agent.adopted:
                (agent.adopted if adopted else agent.tabs).append(target)
            if kind == "working_tab":
                agent.working_tab = target
        elif kind == "tab_closed":
            for bucket in (agent.tabs, agent.adopted):
                if target in bucket:
                    bucket.remove(target)
            if agent.working_tab == target:
                agent.working_tab = None
        else:
            return
        self._changed(agent)

    # ---- turns --------------------------------------------------------------------------------------------

    def _pump(self) -> None:
        while self._line and len(self._turns) < self.max_working:
            agent = self.agents.get(self._line.popleft())
            if agent is None or not agent.pending:
                continue
            agent.state = "working"
            self._changed(agent)
            self._turns[agent.id] = asyncio.create_task(self._run(agent))
        for agent_id in self._line:
            agent = self.agents.get(agent_id)
            if agent is not None and agent.state != "waiting":
                agent.state = "waiting"
                self._changed(agent)

    async def _run(self, agent: Agent) -> None:
        try:
            while agent.pending and agent.id in self.agents:
                text, tab, skills = agent.pending.pop(0)
                self._record(agent, {"type": "user", "text": text})
                async for event in agent.bridge.send(text, tab.get("url", ""), tab.get("title", ""), skills):
                    self._on_event(agent, event)
        except Exception as exc:  # the row must always learn that the turn ended
            self._on_event(agent, {"type": "error", "text": f"{type(exc).__name__}: {exc}"})
        finally:
            self._turns.pop(agent.id, None)
            if agent.state == "working":
                agent.state = "your_turn"
                self._changed(agent)
            self._pump()

    def _on_event(self, agent: Agent, event: dict) -> None:
        self._record(agent, event)
        kind = event.get("type")
        if kind == "tool":
            agent.tools[event.get("id", "")] = (event.get("name", ""), event.get("summary", ""))
            agent.status = f"{event.get('name', '')} {event.get('summary', '')}".strip()
            if event.get("name") == "load_skill":
                agent.loaded_skills = sorted(agent.bridge.loaded_skills)
        elif kind == "tool_result":
            name, summary = agent.tools.get(event.get("id", ""), (event.get("name", ""), ""))
            ms = event.get("ms")
            agent.last_action = f"{name} {summary}".strip() + (f" · {ms} ms" if ms is not None else "")
            if self.on_action is not None:
                with contextlib.suppress(Exception):
                    self.on_action(agent)
        elif kind == "done":
            agent.seconds = round(agent.seconds + (event.get("seconds") or 0), 1)
            agent.cost = round(agent.cost + (event.get("cost") or 0), 4)
            agent.status = ""
            agent.state = "working" if agent.pending else "stopped" if event.get("stopped") else "your_turn"
        elif kind == "error":
            agent.status = str(event.get("text", ""))
            agent.state = "working" if agent.pending else "failed"
        else:
            return
        self._changed(agent)
