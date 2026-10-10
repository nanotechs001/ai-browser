"""Where agents browse (Settings → Where agents browse): the Brave profile the user chose, by its folder, and the live
browser context Brave gives that profile on this connection.

CDP can't name a profile: a browser context is an id, and Brave opens a new tab only in the profile it used last (wave
C's measurement). So the chosen profile's context is learned from Brave's own record of the profile it used last, read
two ways: live, as Target.getBrowserContexts' defaultBrowserContextId (the tab list reads it), and on disk, as Local
State's profile.last_used, which Brave writes a few seconds later. When both have named the same pair for SETTLE
seconds, that context is that profile's until the connection ends; a later pair that says otherwise replaces it. A
Brave with one profile needs no wait. Nothing here opens a connection or asks Brave anything: it reads what the tab list
already has, and a file. Profile names and colours come from browser detection (never an email), and only Settings
shows them."""

from __future__ import annotations

import time
from pathlib import Path

from .. import browsers

SETTLE = 30.0  # seconds both records must agree (Task 1's ruling: Local State's lag is unmeasured, so 30)
PLACE_EVERY = 2.0  # seconds between two looks, while Brave is connected


class ProfilePlace:
    def __init__(self, folder, settle: float = SETTLE, clock=time.monotonic):
        self.folder = Path(folder)  # Brave's folder of profiles
        self.settle, self.clock = settle, clock
        self.chosen: str | None = None  # a profile's folder; None: the profile Brave used last
        self._connection = None  # the tab list the contexts below were seen on
        self._learned: dict[str, str] = {}  # profile folder -> its context, on that connection
        self._pair: tuple[str, str] | None = None  # (folder, context) both records name now
        self._since = 0.0
        self.default_known = False  # Brave named the profile it used last, on this connection (Settings' choice, none picked)

    def profiles(self) -> list[dict]:
        """Brave's profiles as Settings lists them: folder, name and colour (browser detection's, never an email)."""
        return [{"folder": profile.folder, "name": profile.name, "color": profile.color}
                for profile in browsers.profiles(self.folder)]

    def look(self, connection, default_context: str | None) -> bool:
        """One look (every PLACE_EVERY seconds while connected): True when what was learned changed, forgetting
        included, or whether Brave names the profile it used last did. BraveLink looks with (None, None) when the
        connection ends, so nothing learned outlives it."""
        forgot = bool(default_context) != self.default_known
        self.default_known = bool(default_context)
        if connection is not self._connection:  # a new connection: its contexts are new ids
            forgot = forgot or bool(self._learned)
            self._connection, self._learned, self._pair = connection, {}, None
        if not default_context:
            self._pair = None
            return forgot
        found = browsers.profiles(self.folder)
        if len(found) == 1:
            return self._learn(found[0].folder, default_context) or forgot
        last = next((profile.folder for profile in found if profile.last_used), None)
        pair = (last, default_context) if last is not None else None
        if pair != self._pair:
            self._pair, self._since = pair, self.clock()
            return forgot
        if pair is None or self.clock() - self._since < self.settle:
            return forgot
        return self._learn(*pair) or forgot

    def _learn(self, folder: str, context: str) -> bool:
        if self._learned.get(folder) == context:
            return False
        self._learned = {known: other for known, other in self._learned.items() if other != context}
        self._learned[folder] = context  # one context per profile, one profile per context
        return True

    def ready(self, folder: str) -> bool:
        """Whether this profile's context is learned on this connection: a saved agent's settings say "ready", else
        "open it once"."""
        return folder in self._learned

    def context(self, default_context: str | None, folder: str | None = None) -> tuple[str | None, str]:
        """(context, source) of the profile where agents browse: the chosen one's (a saved agent's own `folder`, else
        Settings' choice), once Brave has shown it on this connection ("chosen"), else None ("not_open"); with none
        chosen, the profile Brave used last ("last_used"), or none yet ("none")."""
        chosen = folder if folder is not None else self.chosen
        if chosen is None:
            return (default_context, "last_used") if default_context else (None, "none")
        context = self._learned.get(chosen)
        return (context, "chosen") if context else (None, "not_open")
