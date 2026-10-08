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

from ..app.bravelink import NOT_CONNECTED, PlaceError
from ..app.inworld import WorldError
from .service import source_of
from .store import built_in

READ_EVERY = 4.0  # seconds between two rounds of reads
FIELDS = ("id", "from", "subject", "snippet", "url", "time")
NO_TAB = "no open tab"
STALE = "reader needs an update"
ELSEWHERE = "open the page to watch in this tab"
OFF_NOTE = "Reading your tabs is off: turn it on in Settings → Brain"
TURNED_OFF = "reading your tabs was turned off"
OFF_SITE = "its link leads off its site, and AI Browser opens only the site's own pages"
SHOW_WAIT = 20.0  # seconds for a thread's tab to show the thread


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
        self._jobs: set[asyncio.Task] = set()  # threads being opened, reply boxes being filled
        self._closing: set[asyncio.Task] = set()  # tabs a stopped job had opened, being closed
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
            for job in list(self._jobs):  # a thread being opened, a reply box being filled: stopped too
                job.cancel()
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
        for job in [task, *self._jobs]:
            if job is not None:
                job.cancel()
                with contextlib.suppress(BaseException):
                    await job

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
        """The sites the Brain reads: the three, and the picked parts that are on, each while its checkbox in
        Settings → Brain is."""
        return [entry.site for entry in self.brain.store.watch()
                if entry.enabled and self.brain.listens(source_of(entry.site))]

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
        if entry is None or not entry.enabled or not self.brain.listens(source_of(site)):
            return None  # unchecked in Settings → Brain: not read at all
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

    # ---- drafts: a thread to read, and Use draft --------------------------------------------------------------

    def handle(self, message: dict) -> bool:
        """The Brain's outbox for the user's tabs: open_thread (a thread to read, for a draft) and fill_reply (Use
        draft: the reply into its reply box). True when taken; the answer comes later, as the Brain's on_thread or
        on_filled. False while the switch is off or Brave isn't connected: why_closed() says which."""
        kind = message.get("type")
        if kind not in ("open_thread", "fill_reply") or self.state() != "on":
            return False
        if not isinstance(message.get("url"), str) or not isinstance(message.get("site"), str):
            return False
        job = asyncio.ensure_future(self._open_thread(message) if kind == "open_thread" else self._fill_reply(message))
        self._jobs.add(job)
        job.add_done_callback(self._jobs.discard)
        return True

    def why_closed(self) -> str:
        """Why handle() took nothing, for the item's note."""
        return OFF_NOTE if not self.on else NOT_CONNECTED

    async def _open_thread(self, message: dict) -> None:
        request, opened = message.get("request"), []
        try:
            target = await self._thread_tab(message["url"], message["site"], opened)
            text = await self._thread_text(target, message["site"])
        except asyncio.CancelledError:  # the switch went off: nothing of this read is kept, nor the tab it opened
            self._close(opened)
            self.brain.on_thread(request, "", TURNED_OFF)
            raise
        except (WorldError, PlaceError) as exc:
            self.brain.on_thread(request, "", str(exc))
            return
        self.brain.on_thread(request, text, "" if text else "the thread didn't show in its tab")

    async def _fill_reply(self, message: dict) -> None:
        """Use draft: the thread's tab comes forward (opened again if it was closed), and the reply goes into its
        reply box. The readers never click Send."""
        request, site = message.get("request"), message["site"]
        try:
            target = await self._thread_tab(message["url"], site, [], background=False)
            await self.brave.watch(target)
            await self._thread_text(target, site)  # the thread showing: its reply box can open
            text = str(message.get("text") or "")
            config = {**self._config(site), "url": message["url"]}  # the reader checks the tab still shows it
            answer = await self.brave.run_reader(target, "brain", "fill", self._kind(site), text, config)
        except asyncio.CancelledError:
            self.brain.on_filled(request, False, TURNED_OFF)
            raise
        except (WorldError, PlaceError) as exc:
            self.brain.on_filled(request, False, str(exc))
            return
        answer = answer if isinstance(answer, dict) else {}
        reason = answer.get("reason") if isinstance(answer.get("reason"), str) else ""
        ok = answer.get("ok") is True
        self.brain.on_filled(request, ok, reason if ok or reason else "the reply box didn't answer")

    async def _thread_tab(self, url: str, site: str, opened: list, background: bool = True) -> str:
        """The user's tab that shows this thread, or a new one (its row says "Brain", and it goes in `opened` as soon
        as Brave made it). Only an address on the item's own site: a link someone wrote in a message opens nothing."""
        if self.brave.brain_site(url) != site:
            raise PlaceError(OFF_SITE)
        for tab in self.brave.brain_tabs():
            if tab["url"] == url:
                return tab["target"]
        return await self.brave.open_user_tab(url, background=background, opened=opened)

    async def _thread_text(self, target: str, site: str) -> str:
        """The thread's text once its tab shows it ("" if it never does in SHOW_WAIT)."""
        deadline = self.clock() + SHOW_WAIT
        while True:
            with contextlib.suppress(WorldError):
                answer = await self.brave.run_reader(target, "brain", "thread", self._kind(site), self._config(site))
                text = answer.get("text") if isinstance(answer, dict) else ""
                if isinstance(text, str) and text.strip():
                    return text
            if self.clock() >= deadline:
                return ""
            await asyncio.sleep(0.5)

    def _close(self, targets: list) -> None:
        if targets:
            closing = asyncio.ensure_future(self.brave.close_targets(list(targets)))
            self._closing.add(closing)
            closing.add_done_callback(self._closing.discard)
