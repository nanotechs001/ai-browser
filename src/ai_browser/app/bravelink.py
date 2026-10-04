"""The app's view of the user's Brave (brave mode): the tab list with whose each tab is, Watch, thumbnails of the AI's
tabs, and closing an agent's tabs. Its relay (app/cdprelay.py) holds the one connection to Brave that the app, every
agent and every Claude Code session share, so Brave asks "Allow remote debugging?" once per app run.

That connection opens only right after something the user did (the app starting, Connect or Try again in AI Home, an
agent starting a turn, a session's browser call). While it isn't connected the relay looks at the switch every few
seconds with a TCP check alone, which never opens a debugging session. The app never attaches to, reads or pictures a
tab of the user's: only the AI's tabs, a tab handed over, or the page the user picked in the Train form.

AI Home lists the user's web tabs of one profile only, the agents' (the one the watcher runs in, else the one Brave
used last): other profiles and private windows are only counted. The AI's tabs are listed wherever they are. Context
ids never leave this class."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from pathlib import Path

from .cdprelay import ALLOW_WAIT, SWITCH_EVERY, Relay, Tokens
from .tabs import TabWatch

READABLE = {"agent", "session", "handed"}  # tabs whose picture or text the app may take
YOU = {"kind": "you"}
USERS = ("you", "brain")  # the user's own tabs (a Brain row is theirs): listed only in the agents' profile
WEB = ("http://", "https://")
__all__ = ["ALLOW_WAIT", "SWITCH_EVERY", "BraveLink"]


class BraveLink:
    def __init__(self, folder: Path, watcher_id: str = "", allow_wait: float = ALLOW_WAIT, every: float = SWITCH_EVERY,
                 tokens: Tokens | None = None):
        self.folder = Path(folder)
        self.watcher_id = watcher_id  # the watcher's extension id; "" = no watcher, so the profile used last
        self.relay = Relay(self.folder, tokens if tokens is not None else Tokens(), allow_wait=allow_wait,
                           every=every)
        self.name = self.relay.name
        self.allow_wait, self.every = allow_wait, every
        self._watch: TabWatch | None = None
        self._starting: asyncio.Task | None = None
        self._owners: dict[str, dict] = {}  # target id -> its owner (no entry: the user's)
        self._changes: list[Callable[[list[dict]], None]] = []
        self._watcher_contexts: set[str] = set()  # every context its worker was seen in, on this connection
        self._seen_on: TabWatch | None = None  # the connection those were seen on: a new one starts again
        self._last = None  # (connection, rows, scope) last sent to the on_change callbacks
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
        """Ask Brave for the one connection: Brave asks the user, who has up to ALLOW_WAIT seconds to click Allow.
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
        watch = TabWatch("", "", cdp=self.relay.local())
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
        self._changed()

    def _drop_watch(self) -> None:
        watch, self._watch, self._starting = self._watch, None, None
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
        watch, self._watch = self._watch, None
        if watch is not None:
            await self._close_watch(watch)
        await self.relay.close()

    # ---- the tab list ----------------------------------------------------------------------------------------

    def on_change(self, callback: Callable[[list[dict]], None]) -> None:
        self._changes.append(callback)

    def _changed(self) -> None:
        """Call back only when the rows or the scope changed (a worker waking or sleeping changes neither), or the
        connection did: connecting and losing it always call back. While Brave is connected and the tab list is still
        starting, nothing is sent: the list's first round calls back."""
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
        """(context, source) of the profile whose tabs AI Home lists: the one the watcher runs in ("watcher"), else
        the one Brave used last ("last_used"), else none ("none"). A sleeping worker drops out of Brave's target list,
        so a context it was seen in counts for the rest of this connection."""
        watch = self._watch
        if watch is not self._seen_on:  # a new connection (or none): what the last one saw is forgotten
            self._seen_on, self._watcher_contexts = watch, set()
        if watch is None:
            return None, "none"
        if self.watcher_id:
            self._watcher_contexts |= watch.worker_contexts(self.watcher_id)
        if len(self._watcher_contexts) == 1:  # in two profiles the app can't tell which one groups: the fallback
            return next(iter(self._watcher_contexts)), "watcher"
        if watch.default_context:
            return watch.default_context, "last_used"
        return None, "none"

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

    def mark_brain(self, url: str) -> None:
        """A thread the watcher opened for the Brain: when exactly one tab nobody owns shows that address, its row
        says "Brain". Display only: it stays the user's tab."""
        found = [tab["target"] for tab in self.tabs() if tab["url"] == url and tab["owner"]["kind"] == "you"]
        if len(found) == 1:
            self.set_owner(found[0], {"kind": "brain", "name": "Brain", "color": "purple"})

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
