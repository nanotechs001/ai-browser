"""The Brain's memory: the inbox (only what is new or needs the user), the ids already seen, and the watch list.

Two files under <home>/brain, mode 0600 because they hold message snippets: inbox.json and watch.json. Every change
is saved at once, atomically, by the one `ai-browser app` that holds <home>/app/lock. A damaged file is kept beside
as <name>.bad and that part starts empty."""

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
    enabled: bool = False
    status: str = ""  # the watcher's latest note ("reader needs an update", "no open tab"); not saved

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
        self._watch = [WatchEntry(site, label, match) for site, label, match in BUILT_IN]
        self.paused = False
        self.style = ""
        self.watcher_seen = False  # the watcher has connected once: Brave's one-time setup is done
        self.watcher_prompted = False  # its setup steps were shown once (with a Finder window)
        self._read_inbox()
        self._read_watch()

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
        """An added site goes; a built-in one is switched off."""
        entry = self.entry(site)
        if entry is None:
            return
        if built_in(site):
            entry.enabled = False
        else:
            self._watch.remove(entry)
        self._save_watch()

    def set_paused(self, on: bool) -> None:
        self.paused = bool(on)
        self._save_watch()

    def set_style(self, text: str) -> None:
        self.style = str(text)
        self._save_watch()

    def set_watcher_seen(self) -> None:
        if not self.watcher_seen:
            self.watcher_seen = True
            self._save_watch()

    def set_watcher_prompted(self) -> None:
        if not self.watcher_prompted:
            self.watcher_prompted = True
            self._save_watch()

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
        self.paused = bool(data.get("paused"))
        self.style = str(data.get("style") or "")
        self.watcher_seen = bool(data.get("watcher_seen"))
        self.watcher_prompted = bool(data.get("watcher_prompted"))

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
        self._write("watch.json", {"watch": watch, "paused": self.paused, "style": self.style,
                                   "watcher_seen": self.watcher_seen, "watcher_prompted": self.watcher_prompted})

    def _write(self, name: str, data: dict) -> None:
        write_atomic(self.folder / name, json.dumps(data).encode("utf-8"), 0o600)
