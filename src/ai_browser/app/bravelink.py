"""The app's one connection to the user's Brave (brave mode): the tab list with whose each tab is, Watch, thumbnails
of the AI's tabs, and closing an agent's tabs.

Brave asks "Allow remote debugging?" for this connection, so it connects only right after something the user did
(the app starting, Connect or Try again in AI Home, an agent starting a turn). While it isn't connected it looks at
the switch every few seconds with a TCP check alone, which never opens a debugging session. It never attaches to,
reads or pictures a tab of the user's: only the AI's tabs, a tab handed over, or the page the user picked in the
Train form."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from pathlib import Path

from ..chrome import ChromeError, browser_name, find_ws_url, switch_on
from .tabs import TabWatch

SWITCH_EVERY = 2.0  # seconds between two looks at the switch while not connected
ALLOW_WAIT = 60  # seconds Brave's "Allow remote debugging?" may stay open
READABLE = {"agent", "session", "handed"}  # tabs whose picture or text the app may take
YOU = {"kind": "you"}


class BraveLink:
    def __init__(self, folder: Path, allow_wait: float = ALLOW_WAIT, every: float = SWITCH_EVERY):
        self.folder = Path(folder)
        self.name = browser_name(self.folder)
        self.state = "off"  # off · ready · asking · connected · refused · lost
        self.allow_wait, self.every = allow_wait, every
        self._watch: TabWatch | None = None
        self._owners: dict[str, dict] = {}  # target id -> its owner (no entry: the user's)
        self._changes: list[Callable[[list[dict]], None]] = []
        self._states: list[Callable[[str], None]] = []
        self._poll: asyncio.Task | None = None

    # ---- the connection --------------------------------------------------------------------------------------

    async def start(self) -> None:
        """Look at the switch now, then every few seconds (never connecting by itself)."""
        await self._look()
        self._poll = asyncio.create_task(self._watch_switch())

    async def connect(self) -> None:
        """Ask Brave for a debugging session: Brave asks the user, who has up to ALLOW_WAIT seconds to click Allow."""
        if self.state in ("connected", "asking"):
            return
        try:
            ws_url = await asyncio.to_thread(find_ws_url, self.folder)
        except ChromeError:
            self._set("off")
            return
        self._set("asking")
        watch = TabWatch(ws_url, "", open_timeout=self.allow_wait)
        try:
            await watch.start()
        except Exception:  # Deny, a refused handshake, or no answer in time
            with contextlib.suppress(Exception):
                await watch.close()
            self._set("refused")
            return
        self._watch = watch
        watch.on_change(lambda _tabs: self._changed())
        self._set("connected")
        self._changed()

    async def close(self) -> None:
        if self._poll is not None:
            self._poll.cancel()
            self._poll = None
        await self._drop()

    async def _drop(self) -> None:
        watch, self._watch = self._watch, None
        if watch is not None:
            with contextlib.suppress(Exception):
                await watch.close()

    async def _look(self) -> None:
        """Between off and ready, by the switch alone; refused and lost stay until the user's next Connect."""
        if self.state not in ("off", "ready"):
            return
        on = await asyncio.to_thread(switch_on, self.folder)
        if on and self.state == "off":
            self._set("ready")
        elif not on and self.state == "ready":
            self._set("off")

    async def _watch_switch(self) -> None:
        while True:
            await asyncio.sleep(self.every)
            if self.state == "connected" and (self._watch is None or self._watch.closed):
                await self._drop()  # Brave quit or restarted
                self._set("lost")
                self._changed()
                continue
            with contextlib.suppress(Exception):
                await self._look()

    def on_state(self, callback: Callable[[str], None]) -> None:
        self._states.append(callback)

    def _set(self, state: str) -> None:
        if state != self.state:
            self.state = state
            for callback in list(self._states):
                with contextlib.suppress(Exception):
                    callback(state)

    # ---- the tab list ----------------------------------------------------------------------------------------

    def on_change(self, callback: Callable[[list[dict]], None]) -> None:
        self._changes.append(callback)

    def _changed(self) -> None:
        tabs = self.tabs()
        for callback in list(self._changes):
            with contextlib.suppress(Exception):
                callback(tabs)

    def tabs(self) -> list[dict]:
        """The user's web pages (http and https) and the AI's own blank tabs, each with its owner."""
        if self._watch is None:
            return []
        listed = []
        for page in self._watch.tabs():
            owner = self._owners.get(page["target"])
            web = page["url"].startswith(("http://", "https://"))
            ours = owner is not None and owner["kind"] in ("agent", "session") and page["url"].startswith("about:blank")
            if web or ours:
                listed.append({**page, "owner": dict(owner) if owner else dict(YOU)})
        return listed

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
        """A tab's text for a skill draft: the AI's tabs, or the page the user picked in the Train form."""
        if self._watch is None or not (picked or self._readable(target)):
            return ""
        return await self._watch.page_text(target)
