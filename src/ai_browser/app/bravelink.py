"""The app's view of the user's Brave (brave mode): the tab list with whose each tab is, Watch, thumbnails of the AI's
tabs, and closing an agent's tabs. Its relay (app/cdprelay.py) holds the one connection to Brave that the app, every
agent and every Claude Code session share, so Brave asks "Allow remote debugging?" once per app run.

That connection opens only right after something the user did (the app starting, Connect or Try again in AI Home, an
agent starting a turn, a session's browser call). While it isn't connected the relay looks at the switch every few
seconds with a TCP check alone, which never opens a debugging session. The app never attaches to, reads or pictures a
tab of the user's: only the AI's tabs, a tab handed over, or the page the user picked in the Train form; and, while
Settings → Brain's switch is on, the user's Gmail, Slack and Asana tabs and the parts of pages they picked to watch,
where the Brain's readers run in an isolated world (may_run decides; app/inworld.py runs).

AI Home lists the user's web tabs of one profile only, the agents' (the one chosen in Settings → Where agents browse,
app/place.py; else the one Brave used last): other profiles and private windows are only counted. The AI's tabs are
listed wherever they are. Context ids never leave this class."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from pathlib import Path

from ..brain import readers
from ..cdp import CDPError
from . import inworld
from .cdprelay import ALLOW_WAIT, SWITCH_EVERY, Relay, Tokens
from .place import PLACE_EVERY, SETTLE, ProfilePlace
from .tabs import TabWatch

READABLE = {"agent", "session", "handed"}  # tabs whose picture or text the app may take
YOU = {"kind": "you"}
USERS = ("you", "brain")  # the user's own tabs (a Brain row is theirs): listed only in the agents' profile
WEB = ("http://", "https://")
BRAIN = {"kind": "brain", "name": "Brain", "color": "purple"}  # a tab AI Browser opened for the Brain: still the user's
OPEN_WAIT = 10.0  # seconds for a tab AI Browser opened to show in the tab list
NOT_CONNECTED = "Brave isn't connected: connect it in AI Home"
OTHER_PROFILE = ("Brave's last window is in another profile: click a window of the profile where agents browse, then "
                 "try again")
NOT_OPEN = ("The profile where agents browse isn't open in Brave yet: open a window of it and click in it once, then "
            "try again")


class PlaceError(RuntimeError):
    """Why a tab couldn't open where it must, in plain words that name no profile (they may reach Claude)."""


__all__ = ["ALLOW_WAIT", "SWITCH_EVERY", "BraveLink"]


class BraveLink:
    def __init__(self, folder: Path, allow_wait: float = ALLOW_WAIT, every: float = SWITCH_EVERY,
                 tokens: Tokens | None = None, app_origin: str = "", settle: float = SETTLE):
        self.folder = Path(folder)
        self.app_origin = app_origin  # AI Browser's own pages: a copy opened in Brave is never one of the user's tabs
        self.place = ProfilePlace(self.folder, settle=settle)  # Settings → Where agents browse
        self._placing: asyncio.Task | None = None  # its looks, while Brave is connected
        self.relay = Relay(self.folder, tokens if tokens is not None else Tokens(), allow_wait=allow_wait,
                           every=every)
        self.name = self.relay.name
        self.allow_wait, self.every = allow_wait, every
        self._watch: TabWatch | None = None
        self._starting: asyncio.Task | None = None
        self._owners: dict[str, dict] = {}  # target id -> its owner (no entry: the user's)
        self._changes: list[Callable[[list[dict]], None]] = []
        self._last = None  # (connection, rows, scope) last sent to the on_change callbacks
        self.brain_reading: Callable[[], bool] = lambda: False  # the server's: Settings → Brain's switch
        self.brain_site: Callable[[str], str | None] = lambda url: None  # the server's: which site an address is
        self.relay.on_state(self._state_changed)  # first: the tab list follows the connection

    # ---- the connection (the relay's) ------------------------------------------------------------------------

    @property
    def state(self) -> str:
        """off · ready · asking · connected · refused · lost"""
        return self.relay.state

    def on_state(self, callback: Callable[[str], None]) -> None:
        self.relay.on_state(callback)

    async def start(self) -> None:
        """Look at the switch now, then every few seconds (never connecting by itself)."""
        await self.relay.start()

    async def connect(self, why: str = "connect", identity: str = "") -> None:
        """Ask Brave for the one connection: Brave asks the user once, and the question stays until they answer.
        `why` is "start", "connect" (AI Home's Connect or Try again) or "turn" (an agent's turn, its id in
        `identity`)."""
        if await self.relay.open(why, identity):
            await asyncio.shield(self._ensure_watch())

    def _state_changed(self, state: str) -> None:
        if state == "connected":
            self._ensure_watch()
        else:
            self._drop_watch()

    def _ensure_watch(self) -> asyncio.Task:
        if self._starting is None or (self._starting.done() and self._watch is None):
            self._starting = asyncio.ensure_future(self._start_watch())
        return self._starting

    async def _start_watch(self) -> None:
        watch = TabWatch("", hidden_origin=self.app_origin, cdp=self.relay.local())
        try:
            await watch.start()
        except Exception:  # the connection went again at once
            with contextlib.suppress(Exception):
                await watch.close()
            return
        if self.relay.state != "connected":
            with contextlib.suppress(Exception):
                await watch.close()
            return
        self._watch = watch
        watch.on_change(lambda _tabs: self._changed())
        self._placing = asyncio.ensure_future(self._place_loop(watch))
        self._changed()

    async def _place_loop(self, watch: TabWatch) -> None:
        """Brave's record of the profile it used last, every PLACE_EVERY seconds while connected: what Where agents
        browse learns from it redraws the list."""
        while self._watch is watch and not watch.closed:
            if self.place.look(watch, watch.default_context):
                self._changed()
            await asyncio.sleep(PLACE_EVERY)

    def set_place(self, folder: str | None) -> None:
        """Settings → Where agents browse: a profile's folder, or None for the profile Brave used last."""
        self.place.chosen = folder
        self._changed()

    def _drop_watch(self) -> None:
        watch, self._watch, self._starting = self._watch, None, None
        if self._placing is not None:
            self._placing.cancel()
            self._placing = None
        if watch is not None:
            asyncio.ensure_future(self._close_watch(watch))
            self._changed()

    @staticmethod
    async def _close_watch(watch: TabWatch) -> None:
        with contextlib.suppress(Exception):
            await watch.close()

    async def close(self) -> None:
        """The app quits (after its agents ended): the tab list, then the one connection."""
        if self._starting is not None and not self._starting.done():
            self._starting.cancel()
        if self._placing is not None:
            self._placing.cancel()
        watch, self._watch = self._watch, None
        if watch is not None:
            await self._close_watch(watch)
        await self.relay.close()

    # ---- the tab list ----------------------------------------------------------------------------------------

    def on_change(self, callback: Callable[[list[dict]], None]) -> None:
        self._changes.append(callback)

    def _changed(self) -> None:
        """Call back only when the rows or the scope changed (a look at the profile that changes neither doesn't), or
        the connection did: connecting and losing it always call back. While Brave is connected and the tab list is
        still starting, nothing is sent: the list's first round calls back."""
        if self._watch is None and self.relay.state == "connected":
            return
        tabs, scope = self.tabs(), self.scope()
        sent = (self._watch, tabs, scope)
        if sent == self._last:
            return
        self._last = sent
        for callback in list(self._changes):
            with contextlib.suppress(Exception):
                callback(tabs)

    def agents_context(self) -> tuple[str | None, str]:
        """(context, source) of the profile where agents browse: the one chosen in Settings, once Brave has shown it
        on this connection ("chosen"), else none ("not_open"); with none chosen, the one Brave used last
        ("last_used"), or none yet ("none")."""
        watch = self._watch
        if watch is None:
            return None, "none"
        return self.place.context(watch.default_context)

    def _shown(self, page: dict, context: str | None) -> bool:
        owner = self._owners.get(page["target"], YOU)
        web = page["url"].startswith(WEB)
        if owner["kind"] in READABLE:  # the AI's tabs, wherever they are: the user must see, Watch and Take back them
            return web or (owner["kind"] in ("agent", "session") and page["url"].startswith("about:blank"))
        return web and context is not None and page["context"] == context

    def tabs(self) -> list[dict]:
        """The rows AI Home may show: the user's web pages (http and https) in the agents' profile, and the AI's tabs
        anywhere (its own blank tabs too), each with its owner. No row carries its context."""
        if self._watch is None:
            return []
        context, _ = self.agents_context()
        return [{"target": page["target"], "url": page["url"], "title": page["title"],
                 "owner": dict(self._owners.get(page["target"], YOU))}
                for page in self._watch.pages() if self._shown(page, context)]

    def scope(self) -> dict | None:
        """Which profile tabs() shows, and how many of the user's web pages it leaves out (other profiles and private
        windows, which CDP can't tell apart): a number, never a title, an address or an id. None while there is no
        tab list (not connected, or connected and the list still starting): no claim about profiles then."""
        if self._watch is None:
            return None
        context, source = self.agents_context()
        pages = self._watch.pages()
        elsewhere = sum(1 for page in pages if page["url"].startswith(WEB)
                        and self._owners.get(page["target"], YOU)["kind"] in USERS and not self._shown(page, context))
        return {"profile": source, "elsewhere": elsewhere}

    def set_owner(self, target: str, owner: dict) -> None:
        self._owners[target] = dict(owner)
        self._changed()

    def forget(self, target: str) -> None:
        if self._owners.pop(target, None) is not None:
            self._changed()

    def release(self, owner_id: str) -> None:
        """An agent closed, or a session ended: none of the tabs it had are its any more."""
        gone = [target for target, owner in self._owners.items() if owner.get("id") == owner_id]
        for target in gone:
            del self._owners[target]
        if gone:
            self._changed()

    # ---- the Brain's readers: which tab may be read, and running them there -----------------------------------

    def client(self):
        """The relay's in-process client the tab list reads through, while Brave is connected; else None."""
        watch = self._watch
        return watch.cdp if watch is not None and not watch.closed else None

    def brain_tabs(self) -> list[dict]:
        """The user's tabs the Brain may read now, as {"target", "url", "site"}: listed in tabs() (the profile where
        agents browse; the user's own, a Brain row too), web pages, on a site the Brain reads. None while Settings →
        Brain's switch is off, or while Brave isn't connected."""
        if self._watch is None or not self.brain_reading():
            return []
        found = []
        for tab in self.tabs():
            site = self.brain_site(tab["url"]) if tab["owner"]["kind"] in USERS and tab["url"].startswith(WEB) else None
            if site:
                found.append({"target": tab["target"], "url": tab["url"], "site": site})
        return found

    def may_run(self, target: str, purpose: str) -> bool:
        """Whether one of AI Browser's page scripts may run in this tab, for this purpose. "brain": a tab brain_tabs()
        lists. "pick": one of the user's listed web tabs, while Settings → Brain's switch is on (the user clicked
        Pick the part to watch there). Never another profile's tab or a private window's, never an agent's for the
        Brain, and nothing while Brave isn't connected."""
        if purpose == "brain":
            return any(tab["target"] == target for tab in self.brain_tabs())
        if purpose == "pick":
            tab = next((tab for tab in self.tabs() if tab["target"] == target), None)
            return (tab is not None and self.brain_reading() and tab["owner"]["kind"] in USERS
                    and tab["url"].startswith(WEB))
        return False

    async def open_user_tab(self, url: str, background: bool = True) -> str:
        """A page the Brain needs (a thread, for a draft or Use draft), opened as a tab of the user's in the profile
        where agents browse: its row says "Brain". Brave opens a new tab only in the profile it used last (CDP can't
        name one), so it opens only when that is the agents' profile; else PlaceError says what to do. It waits until
        the tab list shows the tab, so the readers may run there."""
        watch = self._watch
        if watch is None or watch.closed:
            raise PlaceError(NOT_CONNECTED)
        context, _ = self.agents_context()
        if context is None or watch.default_context != context:
            raise PlaceError(OTHER_PROFILE)
        try:
            answer = await watch.cdp.send("Target.createTarget", {"url": url, "background": background}, timeout=10)
            target = answer["targetId"]
        except (CDPError, KeyError, TypeError):
            raise PlaceError("Brave didn't open the tab") from None
        self.set_owner(target, BRAIN)
        for _ in range(int(OPEN_WAIT * 10)):
            if any(tab["target"] == target for tab in self.tabs()):
                break
            await asyncio.sleep(0.1)
        return target

    async def open_ai_tab(self, identity: str) -> str:
        """A new blank tab for an agent or a Claude Code session (POST /agent-tab): opened by the app's own client in
        the profile where agents browse, in a window of its own (never one of the user's windows), and theirs at once
        (Relay.assign), before any other client can see it. PlaceError says why not, in words that name no profile:
        they reach Claude."""
        watch = self._watch
        if watch is None or watch.closed:
            raise PlaceError(NOT_CONNECTED)
        context, source = self.agents_context()
        if context is None:
            raise PlaceError(NOT_OPEN if source == "not_open" else NOT_CONNECTED)
        if watch.default_context != context:
            raise PlaceError(OTHER_PROFILE)
        params = {"url": "about:blank", "newWindow": True, "background": True}
        try:
            target = (await watch.cdp.send("Target.createTarget", params, timeout=10))["targetId"]
        except (CDPError, KeyError, TypeError):
            raise PlaceError("Brave didn't open the tab") from None
        self.relay.assign(target, identity)
        return target

    async def end_pick(self, target: str) -> None:
        """A pick nobody finished (the wait ran out, or reading went off): AI Browser's outline leaves the page. It
        reads nothing, so it runs in any of the user's listed tabs, whatever the switch says; a page without the
        readers has nothing to end."""
        client = self.client()
        if client is None or not any(tab["target"] == target and tab["owner"]["kind"] in USERS for tab in self.tabs()):
            return
        with contextlib.suppress(inworld.WorldError):
            await inworld.run(client, target, readers.call("unpick"), timeout=5)

    async def run_reader(self, target: str, purpose: str, name: str, *args, timeout: float = inworld.SCRIPT_WAIT):
        """One of the Brain's readers (brain/readers/) in the tab's isolated world, only where may_run says so: its
        plain JSON answer. inworld.WorldError says, in plain words, why it couldn't."""
        if not self.may_run(target, purpose):
            raise inworld.WorldError("AI Browser doesn't read that tab")
        return await inworld.run(self.client(), target, readers.call(name, *args), install=readers.BUNDLE,
                                 missing=readers.MISSING, timeout=timeout)

    # ---- actions ---------------------------------------------------------------------------------------------

    def _readable(self, target: str) -> bool:
        return self._owners.get(target, YOU)["kind"] in READABLE

    async def watch(self, target: str) -> None:
        """Bring a tab to the front in Brave (the user's click: Watch, a row, Show me)."""
        if self._watch is not None:
            await self._watch.watch(target)

    async def close_targets(self, targets: list[str]) -> None:
        if self._watch is not None:
            await self._watch.close_targets(targets)

    async def thumbnail(self, target: str) -> bytes | None:
        """A small picture of one of the AI's tabs (never one of the user's: nothing is attached for those)."""
        if self._watch is None or not self._readable(target):
            return None
        return await self._watch.thumbnail(target)

    async def page_text(self, target: str, picked: bool = False) -> str:
        """A tab's text for a skill draft: the AI's tabs, or the page the user picked in the Train form, which must be
        a listed tab (never one in another profile or a private window). Nothing attaches otherwise."""
        if self._watch is None:
            return ""
        if not (self._readable(target) or (picked and any(tab["target"] == target for tab in self.tabs()))):
            return ""
        return await self._watch.page_text(target)
