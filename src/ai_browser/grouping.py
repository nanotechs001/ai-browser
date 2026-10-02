"""Where the AI's new tabs go in the user's Brave (Decisions 5 and 9 of the everyday-Brave spec).

With the watcher able to group (the app says so), a new tab opens at about:blank#aib-<marker>, a secret mark of 16
random hex characters, and the app asks the watcher to put the one tab showing that address in the agent's group; the
first page loads only after that, or after CLAIM_WAIT. Without it, each new tab gets a window of its own.

Measured in Chrome 154 (2026-10-02): the watcher sees the marked address as the tab's url; the blank entry stays in the
tab's history, so Back from the first page shows a blank page; the first page loads with no referrer. Tabs never carry
a browserContextId, so they open in the browser's default profile, never in a private window."""

from __future__ import annotations

import asyncio
import contextlib
import re
import secrets
import time
from collections.abc import Callable

from .agentlink import GROUPS_TTL, AgentLink

MARKER_PREFIX = "about:blank#aib-"
MARKER = re.compile(r"^[0-9a-f]{16}$")
CLAIM_WAIT = 1.5  # seconds a new tab waits for its group before its first load
REREAD_EVERY = 10.0  # seconds between two reads of link.json by a Claude Code session


def new_marker() -> str:
    return secrets.token_hex(8)


def marker_url(marker: str) -> str:
    return MARKER_PREFIX + marker


class Placer:
    """Picks where each new tab of ours opens, and asks the app to group it."""

    def __init__(self, link: AgentLink | None, rediscover: Callable[[], AgentLink | None] | None = None):
        self.link = link
        self.rediscover = rediscover  # a Claude Code session reads link.json again (the app started or restarted)
        self._read_at = time.monotonic()

    async def create_params(self) -> tuple[dict, str | None]:
        """Target.createTarget's parameters, and the tab's marker (None: a window of its own, nothing to claim)."""
        await self._refresh()
        if self.link is not None and (await self.link.status(GROUPS_TTL))["groups"]:
            marker = new_marker()
            return {"url": marker_url(marker), "background": True}, marker
        return {"url": "about:blank", "newWindow": True, "background": True}, None

    async def placed(self, target: str, marker: str | None) -> None:
        """Claim the new tab for our group, waiting at most CLAIM_WAIT; whatever happens, the page loads after."""
        if marker is None or self.link is None:
            return
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self.link.claim(target, marker=marker), CLAIM_WAIT)

    def popup(self, target: str, opener: str, url: str, adopted: bool = False) -> None:
        """A tab one of our pages opened: reported with its opener and address, so it joins the opener's group."""
        if self.link is not None:
            self.link.report("tab_opened", target, adopted, opener=opener, url=url)

    async def _refresh(self) -> None:
        if self.rediscover is None or time.monotonic() - self._read_at < REREAD_EVERY:
            return
        self._read_at = time.monotonic()
        found = self.rediscover()
        if found is None:
            self.link = None
        elif self.link is None or (found.url, found.token) != (self.link.url, self.link.token):
            self.link = found
            with contextlib.suppress(Exception):
                await found.hello()
