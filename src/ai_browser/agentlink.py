"""Tell `ai-browser app` which tabs an agent (or a Claude Code session) works in, and ask it for what only it knows.

Each agent's engine (in its own `ai-browser mcp` process) posts small reports to the app's /agent-events with the
agent token; a Claude Code session uses a session token from <home>/app/link.json. Reports go one at a time, in order;
a lost one only costs AI Home a stale line, never the agent its work. Beside /agent-events sit /agent-claim (group a
new tab), /agent-status (tab groups on? tabs the user handed over), /agent-hello and /agent-bye (sessions)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlsplit

_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # the app is always local: never a proxy
HANDED_TTL = 1.0  # seconds a status answer serves for the handed tabs
GROUPS_TTL = 10.0  # ...and for whether tab groups are on
NO_APP = {"grouped": False, "reason": "no_app"}


class AgentLink:
    def __init__(self, url: str, token: str, agent: str):
        self.url, self.token, self.agent = url, token, agent
        self.base = url.rsplit("/agent-events", 1)[0]  # the app's address: its other routes sit beside /agent-events
        self._queue: asyncio.Queue[dict] = asyncio.Queue()
        self._sender: asyncio.Task | None = None
        self._status: dict | None = None
        self._status_at = 0.0

    def report(self, kind: str, target: str, adopted: bool = False, **extra) -> None:
        """kind: tab_opened, tab_closed or working_tab; or a bot check: check (with check and site) and
        check_cleared (with how). The app checks every value it is sent."""
        self._queue.put_nowait({"agent": self.agent, "kind": kind, "target": target, "adopted": adopted, **extra})
        if self._sender is None or self._sender.done():
            self._sender = asyncio.ensure_future(self._send())

    async def _send(self) -> None:
        while not self._queue.empty():
            report = self._queue.get_nowait()
            with contextlib.suppress(Exception):
                await asyncio.to_thread(self._post, report)

    def _post(self, report: dict) -> None:
        request = urllib.request.Request(self.url, data=json.dumps(report).encode(), method="POST", headers={
            "Content-Type": "application/json", "X-AIB-Agent-Token": self.token})
        with _DIRECT.open(request, timeout=2):
            pass

    async def flush(self) -> None:
        """Deliver what is queued (a few seconds at most)."""
        if self._sender is not None and not self._sender.done():
            await asyncio.wait({self._sender}, timeout=3)

    # ---- asking the app ---------------------------------------------------------------------------------------

    async def claim(self, target: str, marker: str | None = None, opener: str | None = None, url: str = "") -> dict:
        """Ask the app to put a new tab of ours in our tab group; its answer, or {"grouped": False, "reason":
        "no_app"}."""
        body = {"agent": self.agent, "target": target}
        body.update({"marker": marker} if marker else {"opener": opener or "", "url": url})
        answer = await asyncio.to_thread(self._request, "POST", "/agent-claim", body)
        return answer if isinstance(answer, dict) and "grouped" in answer else dict(NO_APP)

    async def status(self, max_age: float = HANDED_TTL) -> dict:
        """{"groups": tab groups on?, "handed": tabs the user handed us}, no older than `max_age` seconds. When the
        app doesn't answer, the last answer stands (a moment's silence must not take a handed tab away)."""
        if self._status is not None and time.monotonic() - self._status_at < max_age:
            return self._status
        answer = await asyncio.to_thread(self._request, "GET", f"/agent-status?agent={quote(self.agent)}", None)
        if isinstance(answer, dict) and "handed" in answer:
            handed = [item for item in answer.get("handed") or []
                      if isinstance(item, dict) and isinstance(item.get("target"), str)]
            self._status = {"groups": answer.get("groups") is True, "handed": handed}
        elif self._status is None:
            self._status = {"groups": False, "handed": []}
        self._status_at = time.monotonic()
        return self._status

    async def hello(self) -> None:
        """A Claude Code session joins the running app (its tabs then show in AI Home, grouped "Claude Code")."""
        await asyncio.to_thread(self._request, "POST", "/agent-hello", {"agent": self.agent, "pid": os.getpid()})

    async def bye(self) -> None:
        await asyncio.to_thread(self._request, "POST", "/agent-bye", {"agent": self.agent})

    def _request(self, method: str, path: str, body: dict | None) -> dict | None:
        """One request to the app (2 s at most): its JSON answer, {} for an empty one, None when it failed."""
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "Content-Type": "application/json", "X-AIB-Agent-Token": self.token})
        try:
            with _DIRECT.open(request, timeout=2) as response:
                raw = response.read()
        except (OSError, ValueError):  # refused, timed out, or an HTTP error (403, 404)
            return None
        try:
            return json.loads(raw) if raw else {}
        except ValueError:
            return None

    @classmethod
    def discover(cls, home: Path, task_id: str) -> AgentLink | None:
        """A Claude Code session's link to a running `ai-browser app` (<home>/app/link.json), or None."""
        from .engine import _alive  # the engine's own process check, in one place (Windows changes only that)

        try:
            data = json.loads((Path(home) / "app" / "link.json").read_text(encoding="utf-8"))
            events, token, pid = data["events"], data["session_token"], int(data["pid"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if not (isinstance(events, str) and isinstance(token, str) and _local_events(events)):
            return None
        return cls(events, token, f"cc-{task_id}") if _alive(pid) else None


def _local_events(url: str) -> bool:
    """Whether `url` is the app's /agent-events on this computer: http, 127.0.0.1 itself (no user part such as
    `127.0.0.1:80@elsewhere`), a port, and that path. Nothing a session reports may go anywhere else."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return (parts.scheme == "http" and parts.hostname == "127.0.0.1" and port is not None
            and parts.username is None and parts.password is None and parts.path == "/agent-events"
            and not parts.query and not parts.fragment)
