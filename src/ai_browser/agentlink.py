"""Tell `ai-browser app` which tabs an agent works in: AI Home, the tab groups and closing an agent follow these.

Each agent's engine (in its own `ai-browser mcp` process) posts small reports to the app's /agent-events with the
agent token. Reports go one at a time, in order; a lost one only costs AI Home a stale line, never the agent its work.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import urllib.request

_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # the app is always local: never a proxy


class AgentLink:
    def __init__(self, url: str, token: str, agent: str):
        self.url, self.token, self.agent = url, token, agent
        self._queue: asyncio.Queue[dict] = asyncio.Queue()
        self._sender: asyncio.Task | None = None

    def report(self, kind: str, target: str, adopted: bool = False) -> None:
        """kind: tab_opened, tab_closed or working_tab."""
        self._queue.put_nowait({"agent": self.agent, "kind": kind, "target": target, "adopted": adopted})
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
