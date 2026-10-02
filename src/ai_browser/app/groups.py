"""Tab groups for the AI's tabs in the user's Brave, made by the Brain's watcher (the extension already in Brave).

The app asks the watcher (`group_tab`) and waits a little for its answer (`tab_grouped`). A group is only a picture:
who may use a tab is decided by target ids, never by a group (Decision 4 of the everyday-Brave spec)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

GROUP_WAIT = 1.2  # seconds for the watcher's answer
REASONS = {"not_found", "ambiguous", "pinned"}  # the watcher's own reasons; anything else counts as not_found


class GroupKeeper:
    def __init__(self, send_to_watcher: Callable[[dict], bool], on_change: Callable[[], None] | None = None):
        self.send = send_to_watcher  # False when the watcher isn't connected
        self.on_change = on_change  # the browser card shows whether groups are on
        self.connected = False
        self.caps: dict | None = None  # watcher_caps: None until this watcher said what it can do
        self._waiting: dict[str, asyncio.Future] = {}
        self._seq = 0
        self._tabs: dict[str, int] = {}  # target id -> Brave's tab id, from the watcher's answers

    def watcher_changed(self, connected: bool) -> None:
        """The watcher said hello (True) or went away (False): a claim still waiting ends at once."""
        self.connected, self.caps = connected, None
        if not connected:
            for future in self._waiting.values():
                if not future.done():
                    future.set_result({"grouped": False, "reason": "no_watcher"})
        self._changed()

    def caps_from(self, message: dict) -> None:
        self.caps = {"groups": message.get("groups") is True}
        self._changed()

    def available(self) -> str:
        if not self.connected:
            return "no_watcher"
        return "on" if self.caps is not None and self.caps["groups"] else "old_watcher"

    async def group(self, key: str, title: str, color: str, find: dict) -> dict:
        """Ask the watcher to put the tab `find` names in the group for `key`."""
        state = self.available()
        if state != "on":
            return {"grouped": False, "reason": state}
        self._seq += 1
        request = f"g{self._seq}"
        future = asyncio.get_running_loop().create_future()
        self._waiting[request] = future
        try:
            if not self.send({"type": "group_tab", "request": request, "key": key, "title": title, "color": color,
                              "find": find}):
                return {"grouped": False, "reason": "no_watcher"}
            return await asyncio.wait_for(future, GROUP_WAIT)
        except TimeoutError:
            return {"grouped": False, "reason": "timeout"}
        finally:
            self._waiting.pop(request, None)

    def answered(self, message: dict) -> None:
        """The watcher's tab_grouped."""
        future = self._waiting.get(str(message.get("request", "")))
        if future is None or future.done():
            return
        tab = message.get("tab")
        if message.get("ok") is True and isinstance(tab, int):
            future.set_result({"grouped": True, "tab": tab})
        else:
            reason = message.get("reason")
            future.set_result({"grouped": False, "reason": reason if reason in REASONS else "not_found"})

    def remember(self, target: str, tab: int) -> None:
        self._tabs[target] = tab

    def tab_of(self, target: str) -> int | None:
        return self._tabs.get(target)

    def ungroup(self, tab_ids: list[int]) -> None:
        """Take tabs out of their group (a handed tab taken back, or released when its agent closes)."""
        ids = [tab for tab in tab_ids if isinstance(tab, int)]
        if ids:
            self.send({"type": "ungroup_tabs", "tabs": ids})

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()
