"""The Brain's memory: the inbox (only what is new or needs the user), the ids already seen, and the watch list.

Three files under <home>/brain, mode 0600 because they hold message snippets: inbox.json, watch.json and
readers.json (what the readers keep between reads: Slack's unread spells, and which picked parts had their first rows
remembered). Every change is saved at once, atomically, by the one `ai-browser app` that holds <home>/app/lock. A
damaged file is kept beside as <name>.bad and that part starts empty."""

from __future__ import annotations

import contextlib
import json
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .. import platforms
from ..syncdir import write_atomic

SEEN_LIMIT = 5000  # ids remembered so nothing is sorted twice (the oldest are forgotten first)
NEW_FOR = 24 * 3600  # a "new" item stays this long unless the user marks it Done; skips are counted this long
MEMORY_LIMIT = 500  # entries a reader may keep for one site (the oldest are forgotten first)
BUILT_IN = (("gmail", "Gmail", "https://mail.google.com/*"), ("slack", "Slack", "https://app.slack.com/*"),
            ("asana", "Asana", "https://app.asana.com/*"))


@dataclass
class Item:
    id: str  # "<site>:<the site's own id>"
    site: str
    raw_id: str
    sender: str = ""
    subject: str = ""
    snippet: str = ""
    url: str = ""
    time: str = ""
    kind: str = "new"  # needs_reply | new
    summary: str = ""
    why: str = ""
    suggest: str = "tell"  # draft | agent | tell
    workflow: str | None = None  # a message workflow the Brain offers for it
    workflow_name: str = ""  # its name, for the Run button
    state: str = "open"  # open | drafting | draft_ready | filling | filled | agent
    draft: str = ""
    draft_version: int = 0
    agent_id: str | None = None
    agent_state: str = ""
    result: str = ""
    note: str = ""
    created: float = 0.0

    def public(self) -> dict:
        return asdict(self)


@dataclass
class WatchEntry:
    site: str  # gmail | slack | asana | custom:<host>
    label: str
    url_match: str  # a match pattern: where its reader runs
    selector: str = ""  # added sites: the part of the page the user picked
    instructions: str = ""  # the user's own words for this site
    enabled: bool = False  # the three sites are always on: Settings → Brain's switch reads all three
    status: str = ""  # the reading's latest note ("reader needs an update", "no open tab"); not saved

    def public(self) -> dict:
        return asdict(self)


def built_in(site: str) -> bool:
    return any(site == name for name, _, _ in BUILT_IN)


def _load(cls, data) -> object | None:
    if not isinstance(data, dict):
        return None
    known = {field.name for field in fields(cls)}
    try:
        return cls(**{key: value for key, value in data.items() if key in known})
    except TypeError:
        return None


class BrainStore:
    def __init__(self, home: Path, clock=time.time):
        self.home = Path(home)
        self.folder = self.home / "brain"
        self.clock = clock
        self._items: dict[str, Item] = {}  # in arrival order
        self._seen: dict[str, None] = {}  # an ordered set
        self._skips: list[float] = []
        self._watch = [WatchEntry(site, label, match, enabled=True) for site, label, match in BUILT_IN]
        self.style = ""
        self._memory: dict[str, dict] = {}  # site -> what its reader keeps between reads (Slack's spells)
        self._baselined: list[str] = []  # "<site>|<selector>": picked parts whose first rows were remembered
        self._read_inbox()
        self._read_watch()
        self._read_readers()

    # ---- the inbox ----------------------------------------------------------------------------------------

    def items(self) -> list[Item]:
        """Newest first (an update keeps an item's place)."""
        return list(reversed(self._items.values()))

    def get(self, item_id: str) -> Item | None:
        return self._items.get(item_id)

    def put(self, item: Item) -> None:
        if not item.created:
            item.created = self.clock()
        self._items[item.id] = item
        self._save_inbox()

    def remove(self, item_id: str) -> None:
        if self._items.pop(item_id, None) is not None:
            self._save_inbox()

    def seen(self, item_id: str) -> bool:
        return item_id in self._seen

    def mark_seen(self, ids) -> None:
        for item_id in ids:
            self._seen[item_id] = None
        while len(self._seen) > SEEN_LIMIT:
            del self._seen[next(iter(self._seen))]
        self._save_inbox()

    @property
    def others(self) -> int:
        """Messages skipped (nothing for the user) in the last day."""
        since = self.clock() - NEW_FOR
        return sum(1 for when in self._skips if when > since)

    def add_others(self, count: int) -> None:
        now = self.clock()
        self._skips = [when for when in self._skips if when > now - NEW_FOR] + [now] * max(0, count)
        self._save_inbox()

    def expire(self) -> None:
        """Forget "new" items older than a day, and old skips."""
        since = self.clock() - NEW_FOR
        old = [item_id for item_id, item in self._items.items() if item.kind == "new" and item.created < since]
        for item_id in old:
            del self._items[item_id]
        self._skips = [when for when in self._skips if when > since]
        self._save_inbox()

    # ---- the watch list and settings --------------------------------------------------------------------------

    def watch(self) -> list[WatchEntry]:
        return list(self._watch)

    def entry(self, site: str) -> WatchEntry | None:
        return next((entry for entry in self._watch if entry.site == site), None)

    def set_watch(self, entry: WatchEntry) -> None:
        for index, old in enumerate(self._watch):
            if old.site == entry.site:
                self._watch[index] = entry
                break
        else:
            self._watch.append(entry)
        self._save_watch()

    def remove_watch(self, site: str) -> None:
        """An added site goes; the three sites stay (Settings → Brain's switch reads them)."""
        entry = self.entry(site)
        if entry is None or built_in(site):
            return
        self._watch.remove(entry)
        self._save_watch()

    def set_style(self, text: str) -> None:
        self.style = str(text)
        self._save_watch()

    # ---- what the readers keep between reads ------------------------------------------------------------------

    def memory(self, site: str) -> dict:
        """What the site's reader keeps between reads (Slack: its unread spells), as it gave it back last."""
        return dict(self._memory.get(site) or {})

    def set_memory(self, site: str, value: dict) -> None:
        if not isinstance(value, dict):
            return
        kept = dict(list(value.items())[-MEMORY_LIMIT:])
        if kept != self._memory.get(site):
            self._memory[site] = kept
            self._save_readers()

    def baselined(self, site: str, selector: str) -> bool:
        """Whether this picked part's first rows were remembered already (they are never reported)."""
        return f"{site}|{selector}" in self._baselined

    def mark_baselined(self, site: str, selector: str) -> None:
        key = f"{site}|{selector}"
        watched = {f"{entry.site}|{entry.selector}" for entry in self._watch}
        self._baselined = [one for one in self._baselined if one in watched and one != key] + [key]
        self._save_readers()

    # ---- files --------------------------------------------------------------------------------------------

    def _read_inbox(self) -> None:
        data = self._read("inbox.json")
        if data is None:
            return
        for raw in data.get("items") or []:
            item = _load(Item, raw)
            if item is not None and isinstance(item.id, str):
                self._items[item.id] = item
        self._seen = {str(item_id): None for item_id in (data.get("seen") or [])[-SEEN_LIMIT:]}
        self._skips = [float(when) for when in data.get("skips") or [] if isinstance(when, (int, float))]

    def _read_watch(self) -> None:
        data = self._read("watch.json")
        if data is None:
            return
        saved = [entry for entry in (_load(WatchEntry, raw) for raw in data.get("watch") or []) if entry is not None]
        by_site = {entry.site: entry for entry in saved}
        self._watch = [by_site.get(site) or WatchEntry(site, label, match) for site, label, match in BUILT_IN]
        self._watch += [entry for entry in saved if not built_in(entry.site)]
        for entry in self._watch:
            entry.status = ""
            if built_in(entry.site):
                entry.enabled = True  # Settings → Brain's switch reads all three (an older file may say off)
        self.style = str(data.get("style") or "")

    def _read_readers(self) -> None:
        data = self._read("readers.json")
        if data is None:
            return
        memory = data.get("memory")
        self._memory = {site: value for site, value in memory.items() if isinstance(site, str)
                        and isinstance(value, dict)} if isinstance(memory, dict) else {}
        self._baselined = [key for key in data.get("baselined") or [] if isinstance(key, str)]

    def _read(self, name: str) -> dict | None:
        path = self.folder / name
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if isinstance(data, dict):
            return data
        with contextlib.suppress(OSError):
            platforms.replace(path, path.with_name(name + ".bad"))  # a scanner may hold it a moment on Windows
        return None

    def _save_inbox(self) -> None:
        self._write("inbox.json", {"items": [item.public() for item in self._items.values()],
                                   "seen": list(self._seen), "skips": self._skips})

    def _save_watch(self) -> None:
        watch = [{key: value for key, value in entry.public().items() if key != "status"} for entry in self._watch]
        self._write("watch.json", {"watch": watch, "style": self.style})

    def _save_readers(self) -> None:
        self._write("readers.json", {"memory": self._memory, "baselined": self._baselined})

    def _write(self, name: str, data: dict) -> None:
        write_atomic(self.folder / name, json.dumps(data).encode("utf-8"), 0o600)
