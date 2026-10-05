"""Where the AI's new tabs go in the user's Brave (native app part b, Decision 7).

With `ai-browser app` running, the app opens each new tab (POST /agent-tab): in the profile where agents browse, never
among the user's windows, and it gives the tab to this agent or Claude Code session before anything else can see it.
The app's words, when it can't, name no profile: they reach Claude as a tool error. Without the app (another browser
than its own), each new tab gets a window of its own. Tabs never carry a browserContextId, so they never open in a
private window."""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable

from .agentlink import AgentLink
from .browser import BrowserError

REREAD_EVERY = 10.0  # seconds between two reads of link.json by a Claude Code session
NO_ANSWER = "AI Browser didn't open a tab: is `ai-browser app` still running?"


class PlaceError(BrowserError):
    """Why the app couldn't open a tab for us, in its plain words."""


class Placer:
    """Opens each new tab of ours where it belongs: through the app, or (without one) in a window of its own."""

    def __init__(self, link: AgentLink | None, rediscover: Callable[[], AgentLink | None] | None = None,
                 through_app: bool = True):
        self.link = link
        self.through_app = through_app  # False: a session that browses its own connection (the app relays nothing)
        self.rediscover = rediscover  # a Claude Code session reads link.json again (the app started or restarted)
        self._read_at = time.monotonic()

    async def open_tab(self, cdp) -> str:
        """A new blank tab's target id; PlaceError when the app couldn't open one where it must."""
        await self._refresh()
        if self.link is None or not self.through_app:
            params = {"url": "about:blank", "newWindow": True, "background": True}
            return (await cdp.send("Target.createTarget", params))["targetId"]
        answer = await self.link.open_tab()
        if isinstance(answer, dict) and isinstance(answer.get("target"), str) and answer["target"]:
            return answer["target"]
        if isinstance(answer, dict) and isinstance(answer.get("error"), str) and answer["error"]:
            raise PlaceError(answer["error"][:300])
        raise PlaceError(NO_ANSWER)

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
