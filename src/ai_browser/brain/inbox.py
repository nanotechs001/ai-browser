"""Reading the user's Gmail, Slack and Asana tabs, and the parts of pages they picked to watch, for the Brain.

While Settings → Brain → "Read my Gmail, Slack and Asana tabs" is on, every READ_EVERY seconds each such tab open in
Brave (the user's own, in the profile where agents browse: BraveLink.brain_tabs) is read by its site's reader in an
isolated world, through the relay's one connection. What is new goes to the Brain, and so does what the user answered
there; each site's line in Settings says how its reading goes. Turning the switch off stops at once: the loop is
cancelled with the read under way, and nothing a read started before it found is kept. Page text is data: readers
answer plain fields, the Brain checks and trims them, and quotes them to Claude as page data. Nothing here ever
connects to Brave: while it isn't connected, nothing is read."""

from __future__ import annotations

import asyncio
import contextlib
import time

from ..app.inworld import WorldError
from .store import built_in

READ_EVERY = 4.0  # seconds between two rounds of reads
FIELDS = ("id", "from", "subject", "snippet", "url", "time")
NO_TAB = "no open tab"
STALE = "reader needs an update"
ELSEWHERE = "open the page to watch in this tab"


class _Tab:
    """What one tab gave already, for one site: so a row is handed to the Brain once (the Brain also keeps every
    id it has seen, across restarts)."""

    def __init__(self, site: str):
        self.site = site
        self.reported: set[str] = set()
        self.replied: set[str] = set()
        self.unknown_since: float | None = None


class InboxReader:
    def __init__(self, brain, brave, every: float = READ_EVERY, clock=time.monotonic):
        self.brain, self.brave = brain, brave
        self.every, self.clock = every, clock
        self.on = False
        self._task: asyncio.Task | None = None
        self._turn = 0  # changed by every set_on: a read that began before it keeps nothing
        self._tabs: dict[str, _Tab] = {}  # target -> what it gave already
        self._said: dict[str, tuple[bool, str]] = {}  # site -> its line, as last said
        brain.set_reading(self.state())

    def state(self) -> str:
        """"off" (Settings → Brain's switch), "waiting" (on, but Brave isn't connected) or "on"."""
        if not self.on:
            return "off"
        return "on" if self.brave.state == "connected" else "waiting"

    def set_on(self, on: bool) -> None:
        """The switch. Off stops at once: the loop and the read under way are cancelled, and what they found is
        dropped."""
        on = bool(on)
        if on != self.on:
            self.on = on
            self._turn += 1
            if self._task is not None:
                self._task.cancel()
                self._task = None
            self._tabs.clear()
            self._said.clear()
            if on:
                self._task = asyncio.ensure_future(self._loop())
        self.brain.set_reading(self.state())

    async def stop(self) -> None:
        """The app quits: reading ends, and waits for nothing."""
        task, self._task = self._task, None
        self.on = False
        self._turn += 1
        if task is not None:
            task.cancel()
            with contextlib.suppress(BaseException):
                await task

    async def _loop(self) -> None:
        while True:
            with contextlib.suppress(Exception):  # one round that breaks must not stop reading
                await self.read_once()
            await asyncio.sleep(self.every)

    async def read_once(self) -> None:
        """One round: every tab the Brain may read now, then each site's line."""
        turn = self._turn
        self.brain.set_reading(self.state())
        if self.state() != "on":
            return  # off, or Brave isn't connected: nothing is read, and nothing asks Brave anything
        tabs = self.brave.brain_tabs()
        for target in [target for target in self._tabs if target not in {tab["target"] for tab in tabs}]:
            del self._tabs[target]  # closed, gone to another site, or not the user's any more
        found: dict[str, list[tuple[bool, str, bool]]] = {}
        for tab in tabs:
            outcome = await self._read(tab, turn)
            if turn != self._turn:
                return  # switched off (or on again) meanwhile: nothing from this round counts
            if outcome is not None:
                found.setdefault(tab["site"], []).append(outcome)
        for site in self._sites():
            if not any(tab["site"] == site for tab in tabs):
                self._say(site, False, NO_TAB)
            elif found.get(site):  # a tab that reads fine wins; "reader needs an update" outranks "open the inbox"
                states = found[site]
                best = (next((state for state in states if state[0]), None)
                        or next((state for state in states if not state[2]), None) or states[0])
                self._say(site, best[0], best[1])

    def _sites(self) -> list[str]:
        """The sites the Brain reads: the three, and the picked parts that are on."""
        return [entry.site for entry in self.brain.store.watch() if entry.enabled]

    def _say(self, site: str, ok: bool, note: str) -> None:
        if self._said.get(site) != (ok, note):
            self._said[site] = (ok, note)
            self.brain.reader_status(site, ok, note)

    @staticmethod
    def _kind(site: str) -> str:
        return site if built_in(site) else "region"

    def _config(self, site: str) -> dict:
        """What the site's reader is given: Slack's spells, or a picked part's place."""
        if site == "slack":
            return {"memory": self.brain.store.memory("slack")}
        entry = self.brain.store.entry(site)
        if entry is None or built_in(site):
            return {}
        return {"selector": entry.selector, "url_match": entry.url_match}

    async def _read(self, tab: dict, turn: int) -> tuple[bool, str, bool] | None:
        """(ok, note, elsewhere) for one tab, after handing the Brain what is new there; None when it couldn't be
        read this time."""
        site, target = tab["site"], tab["target"]
        entry = self.brain.store.entry(site)
        if entry is None or not entry.enabled:
            return None
        memory = self._tabs.get(target)
        if memory is None or memory.site != site:
            memory = self._tabs[target] = _Tab(site)
        try:
            answer = await self.brave.run_reader(target, "brain", "read", self._kind(site), self._config(site))
        except WorldError:
            return None  # gone, navigating, or Brave went away: the next round tries again
        if turn != self._turn or not isinstance(answer, dict):
            return None
        known = answer.get("known")
        if known == "elsewhere":  # a page of the site this reader doesn't read (Spam, a board): no alarm
            memory.unknown_since = None
            note = answer.get("note")
            return False, note[:200] if isinstance(note, str) and note else ELSEWHERE, True
        if known is not True:  # a layout it doesn't know: an alarm only after a while (the page may still load)
            memory.unknown_since = self.clock() if memory.unknown_since is None else memory.unknown_since
            return (False, STALE, False) if self.clock() - memory.unknown_since >= self.brain.reader_timeout else None
        memory.unknown_since = None
        if site == "slack" and isinstance(answer.get("memory"), dict):
            self.brain.store.set_memory(site, answer["memory"])
        await self._hand_over(site, entry, memory, answer.get("items"))
        return True, "", False

    async def _hand_over(self, site: str, entry, memory: _Tab, items) -> None:
        """What is new in this tab, and what the user answered there, to the Brain. A picked part's first rows are
        only remembered: watching starts from what is there."""
        fresh, replied = [], []
        for item in items[:200] if isinstance(items, list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
                continue
            if item.get("from_me") is True:
                if item["id"] not in memory.replied:
                    memory.replied.add(item["id"])
                    replied.append(item["id"])
            elif item.get("unread") is not False and item["id"] not in memory.reported:
                memory.reported.add(item["id"])
                fresh.append({key: item.get(key) for key in FIELDS})
        for raw_id in replied:
            self.brain.on_replied(site, raw_id)
        baseline = not built_in(site) and not self.brain.store.baselined(site, entry.selector)
        if baseline:
            self.brain.store.mark_baselined(site, entry.selector)
        if fresh or baseline:
            await self.brain.on_items(site, fresh, baseline=baseline)
