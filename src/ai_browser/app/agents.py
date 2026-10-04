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
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from ..accounts import DEFAULT, DEFAULT_NAME, GONE, NOT_SIGNED_IN, clean_env
from ..checks import KINDS
from .bridge import ClaudeBridge

COLORS = ("blue", "green", "cyan", "pink", "yellow", "red", "grey")  # Brave's group colours, minus the Brain's
# purple and Claude Code's orange, so a group's colour never suggests the wrong owner
HANDED_NOTE = ("The user handed you a tab: call tabs list and switch to it (it is listed as handed to you by the "
               "user)")
KEEP_EVENTS = 5000  # an agent's conversation kept for the chat views (the newest)
NAME_LIMIT = 40
CLOSE_WAIT = 10  # seconds a closing agent's turn gets to end after Stop
# What the agent hears from Continue and Skip this site: fixed texts, never a site's name or any page data.
CONTINUE_TEXT = "I've dealt with the bot check. Call observe and carry on with the task."
SKIP_TEXT = ("Skip the site with the bot check: I closed its tab. Carry on without it, and tell me what you couldn't "
             "do.")
LIMIT_STATUS = "Hit its usage limit"  # an agent's status line when its account hit its usage limit
_SCHEME = re.compile(r"\bhttps?://(?:www\.)?", re.IGNORECASE)
_FILLER = {"and", "or", "then", "to", "the", "a", "an", "of", "in", "on", "with", "for", "from"}
_AGENT_ID = re.compile(r"a([0-9]{1,9})")  # the ids the server and the relay accept: ^a[0-9]{1,9}$


def agent_number(agent_id) -> int | None:
    """The number the user sees for an agent ("1 · Fix the footer"): its id without the "a" (a12 is 12). It is fixed
    for the app's run, and numbers start at 1 again after a restart, as ids do. None for any other id (the app's own,
    a Claude Code session's). One rule, used by the agents' rows and the relay's list of what is connected."""
    match = _AGENT_ID.fullmatch(agent_id) if isinstance(agent_id, str) else None
    return int(match.group(1)) if match else None


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
    # a bot check waiting for the user: {kind, check, what, site, target, adopted, live, since}
    check: dict | None = None
    # AI accounts: the account it runs on, and the usage limit that paused it, if any (public: AI Browser's own pages
    # show them; WATCHER_AGENT_FIELDS keeps them from the watcher)
    account: dict = field(default_factory=lambda: {"id": DEFAULT, "name": DEFAULT_NAME})  # {"id", "name"}
    limit: dict | None = None  # {"account": id, "resets_at": seconds since 1970, or None}
    moved: str = ""  # how its last move went: "Moved to Work with its conversation"
    task: str = field(default="", repr=False)  # its first words: the hand-over note (wave C's Restart in too)

    PUBLIC: ClassVar[tuple[str, ...]] = ("id", "name", "color", "model", "state", "status", "last_action", "tabs",
                                         "adopted", "working_tab", "loaded_skills", "seconds", "cost", "created",
                                         "permission", "check", "number", "queued", "account", "limit", "moved")

    @property
    def number(self) -> int:
        """The number the user sees, fixed for the app's run: a3 is 3."""
        return agent_number(self.id) or 0

    @property
    def queued(self) -> int:
        """Messages the agent hasn't read yet: each waits for its current answer to end."""
        return len(self.pending)

    def public(self) -> dict:
        return {key: list(value) if isinstance(value, list) else value
                for key, value in ((key, getattr(self, key)) for key in self.PUBLIC)}


class AgentManager:
    def __init__(self, home: Path, claude: str | Sequence[str] | None = None, max_working: int = 3,
                 env: dict[str, str] | None = None, close_tabs: Callable[[list[str]], Awaitable[None]] | None = None,
                 on_action: Callable[[Agent], None] | None = None, accounts=None):
        self.home = Path(home)
        self.claude = claude
        self.max_working = max(1, max_working)
        self.env = dict(env or {})  # for every agent's ai-browser server: AIB_APP_PROFILE, AIB_APP_EVENTS...
        self.close_tabs = close_tabs  # set by the app once AI Browser is open
        self.on_action = on_action  # after each action: the app takes a thumbnail
        self.ungroup: Callable[[list[str]], None] | None = None  # set by the app: take tabs out of their group
        self.on_turn: Callable[[Agent], None] | None = None  # set by the app: an agent starts a turn
        self.mint_token: Callable[[str], str] | None = None  # set by the app: each agent's own token
        self.own_tabs: Callable[[str], list[str]] | None = None  # set by the app in brave mode: the relay's table
        self.tools = None  # the user's MCP servers (ToolsConfig), set by the app: agents ask before using them
        self.accounts = accounts  # AI accounts (Accounts); None: every agent runs on Default, as before
        self.on_limit: Callable[[str], None] | None = None  # set by the app: an account hit its usage limit
        self._asks: dict[str, asyncio.Future] = {}  # agent id -> its tool request waiting for the user
        self.agents: dict[str, Agent] = {}
        self._line: deque[str] = deque()  # agents waiting for a free slot, first come first served
        self._turns: dict[str, asyncio.Task] = {}  # agents working now
        self._queues: list[asyncio.Queue] = []
        self._seq = 0

    # ---- views --------------------------------------------------------------------------------------------

    def snapshot(self) -> dict:
        newest_first = sorted(self.agents.values(), key=lambda agent: agent.number, reverse=True)
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
                     tab: dict | None = None, servers: list[str] | None = None,
                     account: str | None = None) -> Agent:
        """A new agent for `text`; with `adopt`, it works in that tab of the user's (started from the panel). Its MCP
        servers are the ones switched on in Tools, or only `servers` of them (a workflow's own list). It runs on
        `account`, else on the default account for new agents; ValueError for an account that isn't listed."""
        chosen = self._account_row(account)  # first: a refused account leaves no agent and no number behind
        self._seq += 1
        agent_id = f"a{self._seq}"
        env = {**self.env, "AIB_APP_AGENT": agent_id, **({"AIB_APP_ADOPT": adopt} if adopt else {})}
        if self.mint_token is not None:  # its own token: the app knows who reports, claims and connects
            env["AIB_APP_AGENT_TOKEN"] = self.mint_token(agent_id)
        bridge = ClaudeBridge(self.home, model=model, claude=self.claude, env=env, agent_id=agent_id,
                              tools=self.tools, servers=servers,
                              on_permission=lambda request, agent_id=agent_id: self._ask(agent_id, request),
                              environment=self._environment(chosen["id"]))
        if self.accounts is not None:  # its account must be signed in before its Claude Code starts
            bridge.preflight = lambda agent_id=agent_id: self._sign_in_problem(agent_id)
        agent = Agent(agent_id, _name(text), COLORS[(self._seq - 1) % len(COLORS)], model, bridge, account=chosen,
                      task=text)
        if adopt:  # the panel can show this agent for that tab before Claude's first step
            agent.adopted.append(adopt)
            agent.working_tab = adopt
        agent.pending.append((text, tab or {}, list(skills)))
        self.agents[agent_id] = agent
        self._changed(agent)
        self._line.append(agent_id)
        self._pump()
        return agent

    def _account_row(self, account_id: str | None) -> dict:
        """{"id", "name"} of the account a new agent runs on: the one asked for, else the default for new agents."""
        if self.accounts is None:
            if account_id not in (None, DEFAULT):
                raise ValueError(GONE)
            return {"id": DEFAULT, "name": DEFAULT_NAME}
        chosen = self.accounts.get(account_id if account_id is not None else self.accounts.default_id())
        if chosen is None:
            raise ValueError(GONE)
        return {"id": chosen.id, "name": chosen.name}

    def _environment(self, account_id: str) -> dict[str, str]:
        """Claude Code's environment on that account: CLAUDE_CONFIG_DIR, and never the API variables."""
        return self.accounts.env_for(account_id) if self.accounts is not None else clean_env()

    async def _sign_in_problem(self, agent_id: str) -> str:
        """Before an agent's Claude Code starts: "" when its account is signed in, or Claude Code can't tell (it then
        says why itself); else the line its row shows. The agent never moves to another account by itself."""
        agent = self.agents.get(agent_id)
        if agent is None or self.accounts is None:
            return ""
        status = await self.accounts.status(agent.account["id"])
        return NOT_SIGNED_IN.format(name=agent.account["name"]) if status["signed_in"] is False else ""

    async def send(self, agent_id: str, text: str, tab: dict | None = None) -> bool:
        """The user's message: now, or after the agent's current answer. False when the agent has closed."""
        agent = self.agents.get(agent_id)
        if agent is None:
            return False
        agent.limit = None  # the user's own message: it tries again, on the same account
        agent.pending.append((text, tab or {}, []))
        if agent_id in self._turns or agent_id in self._line:  # it gets its turn after the current one
            self._record(agent, {"type": "queued", "text": text})
            self._changed(agent)  # the row's queued count
            return True
        agent.state = "waiting"
        self._changed(agent)
        self._line.append(agent_id)
        self._pump()
        return True

    async def stop(self, agent_id: str) -> None:
        """Stop the agent's answer (its process and tabs stay), or take it out of the line."""
        agent = self.agents.get(agent_id)
        if agent is None:
            return
        agent.pending.clear()
        if agent.permission is not None:  # a tool request still waiting: Stop is a no
            self.answer_permission(agent_id, agent.permission["request"], "deny")
        if agent.check is not None:  # the card goes; only a read of the page or a closed tab ends the engine's hold
            agent.check = None
            if agent_id not in self._turns and agent_id not in self._line:
                agent.state = "stopped"
                self._changed(agent)
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
        own = list(agent.tabs)
        if self.own_tabs is not None:  # tabs the relay says it opened, reported or not
            with contextlib.suppress(Exception):
                own += [target for target in self.own_tabs(agent_id) if target not in own]
        if not keep_tabs and own and self.close_tabs is not None:
            with contextlib.suppress(Exception):
                await self.close_tabs(own)
        if not keep_tabs and agent.adopted and self.ungroup is not None:  # handed tabs: let go, never closed
            with contextlib.suppress(Exception):
                self.ungroup(list(agent.adopted))
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
            if agent.state == "needs_you" and agent.check is None:  # a bot check still waits: it still needs you
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

    def working(self, agent_id: str) -> bool:
        """Whether the agent is in a turn now: its engine may then open the browser connection (Decision 10)."""
        return agent_id in self._turns

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

    async def hand_tab(self, agent_id: str, target: str, tab: dict) -> bool:
        """The user handed one of their tabs to this agent (AI Home's Hand over): it is the agent's to use, and stays
        the user's. The note reaches the agent now, or when its turn ends; the tab's title and address go as page
        data."""
        agent = self.agents.get(agent_id)
        if agent is None or not target:
            return False
        if target not in agent.adopted:
            agent.adopted.append(target)
        self._changed(agent)
        await self.send(agent_id, HANDED_NOTE, {"url": str(tab.get("url", "")), "title": str(tab.get("title", "")),
                                                "label": "handed"})
        return True

    def take_back(self, target: str) -> str | None:
        """The user took a handed tab back (AI Home's Take back): the id of the agent that had it, or None. The
        agent's engine lets go of it at its next action."""
        for agent in self.agents.values():
            if target in agent.adopted:
                agent.adopted.remove(target)
                if agent.working_tab == target:
                    agent.working_tab = None
                if self.ungroup is not None:
                    with contextlib.suppress(Exception):
                        self.ungroup([target])
                self._changed(agent)
                return agent.id
        return None

    # ---- bot checks: the agent's engine stopped at one, and the user deals with it -------------------------------

    def check_event(self, agent_id: str, report: dict) -> None:
        """The agent's engine holds at a bot check (the app checked the report's values first): it needs the user."""
        agent = self.agents.get(agent_id)
        kind = report.get("check")
        if agent is None or kind not in KINDS:
            return
        target = str(report.get("target", ""))
        fresh = agent.check is None or agent.check["target"] != target
        live = report.get("live") if isinstance(report.get("live"), str) else None
        agent.check = {"kind": "check", "check": kind, "what": KINDS[kind], "site": str(report.get("site", "")),
                       "target": target, "adopted": bool(report.get("adopted")), "live": live,
                       "since": time.time() if fresh else agent.check["since"]}
        agent.state = "needs_you"
        self._changed(agent)
        if fresh:  # once per hold: every page, and Brave's watcher
            self._broadcast({"type": "check_request", "agent": agent.id, "name": agent.name,
                             **{key: agent.check[key] for key in ("site", "what", "target", "live")}})

    def check_cleared(self, agent_id: str, target: str, how: str) -> None:
        """The engine's hold ended: the check is gone ("solved") or its tab was closed ("closed")."""
        agent = self.agents.get(agent_id)
        if agent is None or agent.check is None or agent.check["target"] != target:
            return
        agent.check = None
        self._settle(agent)
        self._changed(agent)

    async def continue_check(self, agent_id: str) -> None:
        """The user's Continue: the card goes, and the agent hears CONTINUE_TEXT (once, however often it's pressed)."""
        agent = self.agents.get(agent_id)
        if agent is None or agent.check is None:
            return
        agent.check = None
        self._settle(agent)
        self._changed(agent)
        await self.send(agent_id, CONTINUE_TEXT)

    async def skip_check(self, agent_id: str) -> None:
        """The user's Skip this site: the app closes the agent's own tab with the check (never the user's tab, never
        one in QA's sandbox), and the agent hears SKIP_TEXT. The engine sees the tab close and skips the site."""
        agent = self.agents.get(agent_id)
        check = agent.check if agent is not None else None
        if check is None or check["adopted"] or check["live"] or check["target"] not in agent.tabs:
            return
        agent.check = None
        self._settle(agent)
        self._changed(agent)
        if self.close_tabs is not None:
            with contextlib.suppress(Exception):
                await self.close_tabs([check["target"]])
        await self.send(agent_id, SKIP_TEXT)

    def _settle(self, agent: Agent) -> None:
        """The state once a tool request or a bot check stopped waiting."""
        if agent.permission is not None or agent.check is not None:
            agent.state = "needs_you"
        elif agent.id in self._turns:
            agent.state = "working"
        elif agent.id in self._line:
            agent.state = "waiting"
        elif agent.state == "needs_you":
            agent.state = "your_turn"

    # ---- turns --------------------------------------------------------------------------------------------

    def _pump(self) -> None:
        while self._line and len(self._turns) < self.max_working:
            agent = self.agents.get(self._line.popleft())
            if agent is None or not agent.pending:
                continue
            agent.state = "working"
            self._changed(agent)
            if self.on_turn is not None:  # the app may connect to the user's Brave now (right after the user's task)
                with contextlib.suppress(Exception):
                    self.on_turn(agent)
            self._turns[agent.id] = asyncio.create_task(self._run(agent))
        for agent_id in self._line:
            agent = self.agents.get(agent_id)
            if agent is not None and agent.state != "waiting":
                agent.state = "waiting"
                self._changed(agent)

    async def _run(self, agent: Agent) -> None:
        try:
            while agent.pending and agent.id in self.agents and agent.limit is None:  # a limit pauses the agent
                text, tab, skills = agent.pending.pop(0)
                self._changed(agent)  # one fewer waiting: the row's queued count drops
                self._record(agent, {"type": "user", "text": text})
                async for event in agent.bridge.send(text, tab.get("url", ""), tab.get("title", ""), skills,
                                                     tab.get("label", "panel")):
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
        kind = event.get("type")
        self._record(agent, {"type": "limit"} if kind == "limit" else event)  # the chat names no account or time
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
        elif kind == "limit":
            self._limited(agent, event.get("resets_at"))
        elif kind == "done":
            agent.limit = None  # the turn ended well: a limit it heard of didn't stop it
            agent.seconds = round(agent.seconds + (event.get("seconds") or 0), 1)
            agent.cost = round(agent.cost + (event.get("cost") or 0), 4)
            agent.status = ""
            agent.state = "working" if agent.pending else "stopped" if event.get("stopped") else \
                "needs_you" if agent.check is not None else "your_turn"
        elif kind == "error":
            if agent.limit is None:  # at a limit, its own line stays
                agent.status = str(event.get("text", ""))
            agent.state = "working" if agent.pending and agent.limit is None else "failed"
        else:
            return
        self._changed(agent)

    def _limited(self, agent: Agent, resets_at) -> None:
        """Its account hit its usage limit (the bridge tells it once per turn): the agent pauses, its partial answer
        stays in its chat, its queued messages wait, and the account's reset time is kept for the pickers."""
        account = agent.account["id"]
        resets = float(resets_at) if isinstance(resets_at, (int, float)) and not isinstance(resets_at, bool) else None
        agent.limit = {"account": account, "resets_at": resets}
        agent.status, agent.state = LIMIT_STATUS, "failed"
        if self.accounts is not None:
            self.accounts.set_limit(account, resets)
        if self.on_limit is not None:
            with contextlib.suppress(Exception):
                self.on_limit(account)
