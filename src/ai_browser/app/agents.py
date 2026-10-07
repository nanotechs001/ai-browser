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

from ..accounts import DEFAULT, DEFAULT_NAME, GONE, NOT_SIGNED_IN, clean_env, default_folder
from ..checks import KINDS
from . import attachments
from . import move as moving
from . import powers
from .bridge import ClaudeBridge

COLORS = ("blue", "green", "cyan", "pink", "yellow", "red", "grey")  # the agents' chip colours, minus the Brain's
# purple and Claude Code's orange, so a chip's colour never suggests the wrong owner
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
CONTINUE_TASK = "Continue the task."  # the first message on the new account, when its conversation came along
MOVING = "Moving to {name}…"
MOVED = "Moved to {name} with its conversation"
FRESH = "Started fresh on {name} with a hand-over note"
FRESH_NOTE = "Started fresh with a hand-over note"  # the chat's line: no account name (other views may get it)
BUSY_MOVE = "{label} is still working: stop it, or wait for its turn to end, then move it"
NO_CONVERSATION = "no conversation found"
TRUST_FIRST = "Answer “Trust this folder?” for that folder first"  # agent powers, Decision 7
NOTE_LIMIT = 300  # characters of Deny's note to the agent
SUBAGENTS_KEPT = 20  # sub-agents an agent's drawer lists, the newest
FINISHED = ("your_turn", "stopped", "failed")  # a turn that ended: the room's finished agents (the new look)
FILES_KEPT = 50  # files an agent changed, the newest, for History
RESULT_LIMIT = 200  # characters of its last answer's first line, for History
WORDS_LIMIT = 20_000  # characters of an answer kept while it streams in
EDITS = ("Edit", "Write")  # the tools whose path is a file the agent changed
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


def _not_resumed(event: dict, started: bool) -> bool:
    """A resume that didn't take: Claude Code ended before its init event, or said it has no such conversation. (A
    sign-in check that stopped it isn't one: the next message tries the resume again.)"""
    return event.get("type") == "error" and ((bool(event.get("ended")) and not started)
                                             or NO_CONVERSATION in str(event.get("text", "")).lower())


def _first_line(text) -> str:
    """An answer's first line that has words, at most RESULT_LIMIT characters."""
    line = next((one.strip() for one in str(text or "").splitlines() if one.strip()), "")
    return line if len(line) <= RESULT_LIMIT else line[:RESULT_LIMIT - 1].rstrip() + "…"


def _timed(old: list, new: list, now: float) -> list:
    """A to-do list as Claude Code sent it, with each item's times: when it started (first seen in progress) and how
    long it took (first seen completed). Items are matched by their words, in order; a time once known stays."""
    left = [dict(item) for item in old]
    out = []
    for item in new:
        before = next((one for one in left if one.get("content") == item.get("content")), None)
        if before is not None:
            left.remove(before)
        status = item.get("status")
        started = before.get("started") if before is not None and before.get("started") is not None else (
            now if status == "in_progress" else None)
        took = before.get("took") if before is not None and before.get("took") is not None else (
            round(now - started, 1) if status == "completed" and started is not None else None)
        out.append({**item, "started": started, "took": took})
    return out


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
    # show them)
    account: dict = field(default_factory=lambda: {"id": DEFAULT, "name": DEFAULT_NAME})  # {"id", "name"}
    limit: dict | None = None  # {"account": id, "resets_at": seconds since 1970, or None}
    moved: str = ""  # how its last move went: "Moved to Work with its conversation"
    task: str = field(default="", repr=False)  # its first words: the hand-over note (wave C's Restart in too)
    handover: str | None = field(default=None, repr=False)  # the note a resume that doesn't take falls back to
    moving: bool = field(default=False, repr=False)  # one move at a time
    # agent powers: the task's folder (its real path; None: the agent's own scratch folder) and whether the user trusts
    # it; Claude Code's to-do list, and its sub-agents ({id, task, action, state}), for the row and the drawer
    folder: str | None = None
    trusted: bool = False
    todos: list = field(default_factory=list)
    subagents: list = field(default_factory=list)
    # the new look: its latest action's badge, when its current step started, when it finished, the first line of its
    # last answer, the files it changed; and the answer streaming in now, and the last whole one
    badge: str = ""
    step_since: float | None = None
    finished: float | None = None
    result: str = ""
    files: list = field(default_factory=list)
    words: str = field(default="", repr=False)
    said: str = field(default="", repr=False)
    workspace: str | None = None  # the new look: its workspace, a filter only (in memory: ids start again each run)
    web: str = "web"  # the new look's Web ▾: "web", "brave" or "none"

    PUBLIC: ClassVar[tuple[str, ...]] = ("id", "name", "color", "model", "state", "status", "last_action", "tabs",
                                         "adopted", "working_tab", "loaded_skills", "seconds", "cost", "created",
                                         "permission", "check", "number", "queued", "account", "limit", "moved",
                                         "folder", "trusted", "todos", "subagents", "badge", "step_since", "finished",
                                         "result", "files", "workspace", "web")

    @property
    def number(self) -> int:
        """The number the user sees, fixed for the app's run: a3 is 3."""
        return agent_number(self.id) or 0

    @property
    def queued(self) -> int:
        """Messages the agent hasn't read yet: each waits for its current answer to end."""
        return len(self.pending)

    def public(self) -> dict:
        return {key: [dict(item) if isinstance(item, dict) else item for item in value] if isinstance(value, list)
                else value for key, value in ((key, getattr(self, key)) for key in self.PUBLIC)}


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
        self.let_go: Callable[[list[str]], None] | None = None  # set by the app: handed tabs are the user's again
        self.on_turn: Callable[[Agent], None] | None = None  # set by the app: an agent starts a turn
        self.mint_token: Callable[[str], str] | None = None  # set by the app: each agent's own token
        self.own_tabs: Callable[[str], list[str]] | None = None  # set by the app in brave mode: the relay's table
        self.tools = None  # the user's MCP servers (ToolsConfig), set by the app: agents ask before using them
        self.accounts = accounts  # AI accounts (Accounts); None: every agent runs on Default, as before
        self.rules = powers.Rules(self.home)  # agent powers: the user's rules and trusted folders, per folder
        self.on_limit: Callable[[str], None] | None = None  # set by the app: an account hit its usage limit
        self.on_usage: Callable[[str], None] | None = None  # set by the app: an account reported how much is used
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
        if agent.state in FINISHED and agent.permission is None and agent.check is None:
            if agent.finished is None:
                agent.finished = round(time.time(), 1)  # when it ended up done, stopped or failed
        else:
            agent.finished = None
        self._broadcast({"type": "agent", "agent": agent.public()})

    def _record(self, agent: Agent, event: dict) -> None:
        agent.events.append(event)
        self._broadcast({"type": "agent_event", "id": agent.id, "event": event})

    # ---- commands -----------------------------------------------------------------------------------------

    async def create(self, text: str, skills=(), model: str = "sonnet", adopt: str | None = None,
                     tab: dict | None = None, servers: list[str] | None = None,
                     account: str | None = None, folder: str | None = None, workspace: str | None = None,
                     files=(), web: str = "web") -> Agent:
        """A new agent for `text`; with `adopt`, it works in that tab of the user's (started from the panel). Its MCP
        servers are the ones switched on in Tools, or only `servers` of them (a workflow's own list). It runs on
        `account`, else on the default account for new agents; ValueError for an account that isn't listed. With
        `folder` it works there (agent powers, Decision 6): a folder no task may use, or one whose "Trust this
        folder?" isn't answered yet, is a ValueError too. Without, it works in its own scratch folder."""
        chosen = self._account_row(account)  # first: a refused account leaves no agent and no number behind
        work, trusted = self._folder_for(folder)  # and so does a refused folder
        web = web if web in powers.WEB_CHOICES else "web"
        agent_id = f"a{self._seq + 1}"
        try:  # the attached files, into its folder's attachments/ (the scratch folder is the bridge's own path)
            saved = attachments.place(work or self.home / "app" / "agents" / agent_id / "work", list(files))
        except OSError as exc:
            raise ValueError(f"Couldn't save the attached files: {exc.strerror or exc}") from None
        self._seq += 1
        env = {**self.env, "AIB_APP_AGENT": agent_id, **({"AIB_APP_ADOPT": adopt} if adopt else {})}
        if self.mint_token is not None:  # its own token: the app knows who reports, asks for tabs and connects
            env["AIB_APP_AGENT_TOKEN"] = self.mint_token(agent_id)
        bridge = ClaudeBridge(self.home, model=model, claude=self.claude, env=env, agent_id=agent_id,
                              tools=self.tools_for(chosen["id"]), servers=servers,
                              on_permission=lambda request, agent_id=agent_id: self._ask(agent_id, request),
                              environment=self._environment(chosen["id"]), work=work, rules=self.rules, web=web,
                              trusted=trusted)
        if self.accounts is not None:  # its account must be signed in before its Claude Code starts
            bridge.preflight = lambda agent_id=agent_id: self._sign_in_problem(agent_id)
        agent = Agent(agent_id, _name(text), COLORS[(self._seq - 1) % len(COLORS)], model, bridge, account=chosen,
                      task=text, folder=work, trusted=trusted, workspace=workspace, web=web)
        if work is not None:
            with contextlib.suppress(OSError):  # a read-only home: the folder isn't listed as recent, nothing more
                self.rules.note_used(work)
        if adopt:  # the panel can show this agent for that tab before Claude's first step
            agent.adopted.append(adopt)
            agent.working_tab = adopt
        agent.pending.append((text + attachments.note(saved), tab or {}, list(skills)))
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

    def _folder_for(self, folder) -> tuple[str | None, bool]:
        """(the real path a task works in, whether it is trusted); (None, False) for its own scratch folder. A
        ValueError with the words the user sees for a folder no task may use, or one never answered for."""
        if folder is None:
            return None, False
        why = self.folder_problem(folder)
        if why:
            raise ValueError(why)
        real = powers.real_path(folder)
        trusted = self.rules.trusted(real)
        if trusted is None:
            raise ValueError(TRUST_FIRST)
        return real, trusted

    def claude_dirs(self) -> list[str]:
        """Claude Code's own folders, which no task may use: the environment's (else ~/.claude), and each account's."""
        dirs = [str(default_folder())]
        if self.accounts is not None:
            dirs += [account.folder for account in self.accounts.list()]
        return dirs

    def folder_problem(self, path) -> str | None:
        """Why `path` can't be a task's folder (Decision 6), or None."""
        return powers.check_folder(path, home=self.home, claude_dirs=self.claude_dirs())

    def _environment(self, account_id: str) -> dict[str, str]:
        """Claude Code's environment on that account: CLAUDE_CONFIG_DIR, and never the API variables."""
        return self.accounts.env_for(account_id) if self.accounts is not None else clean_env()

    def tools_for(self, account_id: str):
        """An account's tools (AI Home → Tools, one account at a time): its own servers, switches and always-allowed
        tools. Default's are `self.tools`; None without Tools."""
        if self.tools is None or self.accounts is None or account_id == DEFAULT:
            return self.tools
        return self.tools.for_account(account_id, self.accounts.claude_home(account_id),
                                      self.accounts.env_for(account_id))

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
        if agent_id in self._turns or agent_id in self._line or agent.moving:  # after the current turn, or the move
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
        if not keep_tabs and agent.adopted and self.let_go is not None:  # handed tabs: let go, never closed
            with contextlib.suppress(Exception):
                self.let_go(list(agent.adopted))
        self._broadcast({"type": "agent_closed", "id": agent_id})

    async def close_all(self) -> None:
        """The app is ending: every agent's process (AI Browser closes with the app, so tabs are left to it)."""
        for agent_id in list(self.agents):
            await self.close(agent_id, keep_tabs=True)

    async def _ask(self, agent_id: str, request: dict) -> tuple[str, str]:
        """An agent wants a tool that isn't allowed yet: it waits ("needs you") for the user's answer and note. A power
        card shows what the app read from the input, clipped: the input itself stays in the bridge, so no row carries
        an edit's whole file (Review Focus 5)."""
        agent = self.agents.get(agent_id)
        if agent is None:
            return "deny", ""
        tools = self.tools_for(agent.account["id"])  # its own account's always-allowed tools, never another's
        if not request.get("card") and tools is not None and request["tool"] in tools.always():
            return "once", ""  # allowed always since this agent started
        future = asyncio.get_running_loop().create_future()
        self._asks[agent_id] = future
        agent.permission = {"request": request["request"], "server": request.get("server", ""),
                            "tool": request["tool"], "input": {} if request.get("card") else request.get("input", {}),
                            "card": request.get("card"), "sub": str(request.get("sub") or ""),
                            "since": round(time.time(), 1)}
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

    def answer_permission(self, agent_id: str, request: str, answer: str, note: str = "") -> None:
        """The user's answer: "once", "always" or "deny", and with a deny an optional note to the agent (one line).
        "always" is remembered in Tools for one of the user's MCP tools. For Claude Code's own tools the bridge keeps
        it for the task's folder, and only where the card offered it. An answer for a card that has gone (Stop, Close,
        another answer) does nothing (Review Focus 3)."""
        agent, future = self.agents.get(agent_id), self._asks.get(agent_id)
        if agent is None or future is None or future.done() or agent.permission is None \
                or agent.permission["request"] != request:
            return
        answer = answer if answer in ("once", "always") else "deny"
        tools = self.tools_for(agent.account["id"])
        if answer == "always" and tools is not None and not agent.permission.get("card"):
            tools.allow_always(agent.permission["tool"])  # remembered for its own account
        note = " ".join(str(note or "").split())[:NOTE_LIMIT] if answer == "deny" else ""
        future.set_result((answer, note))

    def working(self, agent_id: str) -> bool:
        """Whether the agent is in a turn now: its engine may then open the browser connection (Decision 10)."""
        return agent_id in self._turns

    def set_workspace(self, agent_id: str, workspace_id: str | None) -> bool:
        """Move an agent into a workspace, or out of any (None): a filter only, nothing about its work changes."""
        agent = self.agents.get(agent_id)
        if agent is None:
            return False
        if agent.workspace != workspace_id:
            agent.workspace = workspace_id
            self._changed(agent)
        return True

    def ungroup(self, workspace_id: str) -> list[str]:
        """A workspace was deleted: its agents keep working, in no workspace (the new look's Review Focus 4)."""
        moved = [agent for agent in self.agents.values() if agent.workspace == workspace_id]
        for agent in moved:
            agent.workspace = None
            self._changed(agent)
        return [agent.id for agent in moved]

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
                if self.let_go is not None:
                    with contextlib.suppress(Exception):
                        self.let_go([target])
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
        if fresh:  # once per hold: every page, and AI Browser's own app
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
                if tab.get("handover"):  # a move's hand-over note: the chat gets one line, never the whole note
                    self._record(agent, {"type": "note", "text": FRESH_NOTE})
                else:
                    self._record(agent, {"type": "user", "text": text})
                resuming, started = agent.handover is not None, False  # the first turn after a move that copied
                agent.words = ""  # a turn Stop, a limit or an error cut short left its words: they aren't this turn's
                async for event in agent.bridge.send(text, tab.get("url", ""), tab.get("title", ""), skills,
                                                     tab.get("label", "panel")):
                    started = started or event.get("type") == "status"
                    if resuming and _not_resumed(event, started):
                        resuming = False
                        self._moved(agent, resumed=False)  # the hand-over note goes next, in a fresh session
                        continue
                    self._on_event(agent, event)
                if resuming and started:
                    self._moved(agent, resumed=True)
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
        if kind == "usage":  # how much of its account's limit is used: the Usage card's, never the chat's
            self._usage(agent, event)
            return
        self._record(agent, {"type": "limit"} if kind == "limit" else event)  # the chat names no account or time
        if kind == "tool":
            agent.tools[event.get("id", "")] = (event.get("name", ""), event.get("summary", ""))
            line = f"{event.get('name', '')} {event.get('summary', '')}".strip()
            if event.get("sub"):  # a sub-agent's action: its line in the drawer (Decision 8)
                self._sub_action(agent, str(event["sub"]), line)
            else:
                agent.status = line
                agent.badge = str(event.get("badge") or "")
                at = event.get("at")
                self._step(agent, float(at) if isinstance(at, (int, float)) and not isinstance(at, bool)
                           else round(time.time(), 1))
            if event.get("name") == "load_skill":
                agent.loaded_skills = sorted(agent.bridge.loaded_skills)
        elif kind == "subagent":
            self._subagent(agent, event)
        elif kind == "todos":  # Claude Code's to-do list (Decision 9), each item with its times (the new look)
            agent.todos = _timed(agent.todos, [dict(item) for item in event.get("todos") or []
                                               if isinstance(item, dict)], round(time.time(), 1))
            self._step(agent)
        elif kind == "tool_result":
            name, summary = agent.tools.get(event.get("id", ""), (event.get("name", ""), ""))
            ms = event.get("ms")
            agent.last_action = f"{name} {summary}".strip() + (f" · {ms} ms" if ms is not None else "")
            if name in EDITS and summary and not event.get("is_error"):
                self._changed_file(agent, summary)
            if self.on_action is not None:
                with contextlib.suppress(Exception):
                    self.on_action(agent)
        elif kind == "delta":  # the answer as it streams in: History's result is its first line
            if len(agent.words) < WORDS_LIMIT:
                agent.words += str(event.get("text", ""))
            return
        elif kind == "message_end":
            if agent.words.strip():
                agent.said = agent.words
            agent.words = ""
            return
        elif kind == "limit":
            self._end_subagents(agent)
            self._limited(agent, event.get("resets_at"))
        elif kind == "done":
            self._end_subagents(agent)
            agent.limit = None  # the turn ended well: a limit it heard of didn't stop it
            agent.seconds = round(agent.seconds + (event.get("seconds") or 0), 1)
            agent.cost = round(agent.cost + (event.get("cost") or 0), 4)
            agent.status = ""
            # the words of an answer cut short are the newest there is; a turn that said nothing keeps the last answer
            agent.result = _first_line(agent.words if agent.words.strip() else agent.said)
            agent.state = "working" if agent.pending else "stopped" if event.get("stopped") else \
                "needs_you" if agent.check is not None else "your_turn"
        elif kind == "error":
            self._end_subagents(agent)
            if agent.limit is None:  # at a limit, its own line stays
                agent.status = str(event.get("text", ""))
            agent.state = "working" if agent.pending and agent.limit is None else "failed"
        else:
            return
        self._changed(agent)

    @staticmethod
    def _subagent(agent: Agent, event: dict) -> None:
        """A sub-agent started, or its result came back (done or failed)."""
        row = next((row for row in agent.subagents if row["id"] == event.get("id")), None)
        if row is None:
            if len(agent.subagents) >= SUBAGENTS_KEPT:
                agent.subagents.pop(0)
            row = {"id": str(event.get("id", "")), "task": str(event.get("task", "")), "action": "",
                   "state": "working"}
            agent.subagents.append(row)
        if event.get("state") in ("working", "done", "failed"):
            row["state"] = event["state"]

    @staticmethod
    def _sub_action(agent: Agent, sub: str, line: str) -> None:
        for row in agent.subagents:
            if row["id"] == sub:
                row["action"] = line[:120]

    @staticmethod
    def _end_subagents(agent: Agent) -> None:
        """The turn ended (done, stopped, failed, a limit): a sub-agent still working was stopped with it."""
        for row in agent.subagents:
            if row["state"] == "working":
                row["state"] = "stopped"

    @staticmethod
    def _step(agent: Agent, at: float | None = None) -> None:
        """When the agent's current step started: the to-do in progress, else its latest action (`at`)."""
        current = next((item for item in agent.todos if item.get("status") == "in_progress"), None)
        if current is not None and current.get("started") is not None:
            agent.step_since = current["started"]
        elif at is not None:
            agent.step_since = at

    @staticmethod
    def _changed_file(agent: Agent, path: str) -> None:
        if path in agent.files:
            agent.files.remove(path)
        agent.files.append(path)
        del agent.files[:-FILES_KEPT]

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

    def _usage(self, agent: Agent, event: dict) -> None:
        if self.accounts is None:
            return
        account = agent.account["id"]
        self.accounts.set_usage(account, event.get("used"), event.get("resets_at"), event.get("kind"))
        if self.on_usage is not None:
            with contextlib.suppress(Exception):
                self.on_usage(account)

    async def move(self, agent_id: str, account_id: str, tabs=()) -> str:
        """Continue on another account (a click in AI Home or Mission Control; app-only in MESSAGE_RULES). One move
        per agent at a time, and only while it isn't working:
        1. its Claude Code process ends (it ended its turn already);
        2. its conversation is copied to the other account's folder;
        3. it resumes there with CONTINUE_TASK; when nothing could be copied, or that resume doesn't take (_run), a
           fresh session there starts with the hand-over note.
        Its tabs stay its own: the browser connection doesn't change. "" once the move is under way, else why not."""
        agent = self.agents.get(agent_id)
        if agent is None or self.accounts is None:
            return "That agent has closed"
        if agent.moving:
            return ""  # a second move while one runs does nothing
        label = f"{agent.number} · {agent.name}"
        target = self.accounts.get(account_id)
        if target is None:
            return GONE
        if target.id == agent.account["id"]:
            return f"{label} is on {target.name} already"
        if agent_id in self._turns or agent_id in self._line or agent.permission is not None \
                or agent.check is not None:
            return BUSY_MOVE.format(label=label)
        agent.moving = True
        try:
            if (await self.accounts.status(target.id))["signed_in"] is False:
                return NOT_SIGNED_IN.format(name=target.name)
            source, session = self.accounts.get(agent.account["id"]), agent.bridge.session_id
            note = moving.handover_note(agent, tabs)  # from AI Browser's own log, before anything more is added
            await agent.bridge.switch(self.accounts.env_for(target.id), self.tools_for(target.id))
            copied = bool(moving.CARRY_CONVERSATION and session and source is not None and await asyncio.to_thread(
                moving.move_conversation, source.folder, target.folder, session))
            if agent_id not in self.agents:
                return ""  # closed meanwhile
            agent.account, agent.limit = {"id": target.id, "name": target.name}, None
            if copied:
                agent.handover, agent.moved = note, MOVING.format(name=target.name)
                agent.pending.insert(0, (CONTINUE_TASK, {}, []))
            else:
                agent.bridge.reset()
                agent.handover, agent.moved = None, FRESH.format(name=target.name)
                agent.pending.insert(0, (note, {"handover": True}, []))
            agent.state = "waiting"
            self._changed(agent)
            if agent_id not in self._line:
                self._line.append(agent_id)
            self._pump()
            return ""
        finally:
            agent.moving = False

    def _moved(self, agent: Agent, resumed: bool) -> None:
        """How the move went, once its first turn tells: resumed, or not, and then the hand-over note goes first, in
        a fresh session."""
        name = agent.account["name"]
        if resumed:
            agent.moved = MOVED.format(name=name)
        else:
            agent.bridge.reset()
            agent.pending.insert(0, (agent.handover, {"handover": True}, []))
            agent.moved = FRESH.format(name=name)
        agent.handover = None
        self._changed(agent)
