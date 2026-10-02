"""Check links from inside the browser, so they are tested from the same network the pages use: one request at a time
per site (polite.HostGate), and nothing more to a site that refused."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import time
from urllib.parse import urlsplit

from ..browser import Tab
from ..cdp import CDP, CDPError
from .model import LinkResult
from .polite import MAX_RETRY_WAIT, HostGate, HostStopped, retry_after, short_reason, stop_reason

READ_CHUNK = 64 * 1024


def _stopped(url: str, stopped: HostStopped) -> LinkResult:
    return LinkResult(url, None, f"stopped: {stopped.host} refused ({short_reason(stopped.why)})")


class LinkChecker:
    """Asks the browser to fetch each URL (Network.loadNetworkResource, from one parked tab).

    Works for any site (no CORS), follows redirects, sends the browser's cookies only when asked, and stops a big file
    after its headers. Every request takes its host's turn at the gate: one at a time per host, a pause between two,
    and none at all once the host answered 429, 403, a long 503 or a bot check."""

    def __init__(self, cdp: CDP, tab: Tab, gate: HostGate | None = None, total: int = 4, timeout: float = 12.0):
        self.cdp = cdp
        self.tab = tab
        self.gate = gate if gate is not None else HostGate(total=total)
        self.timeout = timeout
        self._waited: set[str] = set()  # hosts whose short 503 pause was already waited out

    async def check(self, url: str, credentials: bool) -> LinkResult:
        """The URL's status; a timeout gets one more try."""
        result = await self._turn(url, credentials)
        if result.error == "timeout":  # servers have slow moments: try once more before calling it a timeout
            result = await self._turn(url, credentials)
        return result

    async def fetch_text(self, url: str, limit: int) -> tuple[LinkResult, str]:
        """One GET through the gate, without cookies, with up to `limit` bytes of its body as text (robots.txt)."""
        host = (urlsplit(url).hostname or "").lower()
        try:
            async with self.gate.turn(host):
                result, text = await self._load(url, False, limit)
        except HostStopped as stopped:
            return _stopped(url, stopped), ""
        self._judge(host, url, result)
        return result, text

    async def _turn(self, url: str, credentials: bool) -> LinkResult:
        host = (urlsplit(url).hostname or "").lower()
        try:
            async with self.gate.turn(host):
                result = await self._fetch(url, credentials)
                wait = result.retry_after
                if result.status == 503 and wait is not None and wait <= MAX_RETRY_WAIT and host not in self._waited:
                    self._waited.add(host)  # waited out once, holding the host's turn: nothing else goes there
                    await asyncio.sleep(wait)
                    result = await self._fetch(url, credentials)
        except HostStopped as stopped:
            return _stopped(url, stopped)
        self._judge(host, url, result)
        return result

    def _judge(self, host: str, url: str, result: LinkResult) -> None:
        """A 429, a 403, a bot check or a 503 asking for a pause stops every later request to the host."""
        path = urlsplit(url).path or "/"
        if result.challenge:
            self.gate.stop(host, stop_reason(result.status, path, result.retry_after, challenge=True),
                           result.retry_after)
        elif result.status in (403, 429) or (result.status == 503 and result.retry_after is not None):
            self.gate.stop(host, stop_reason(result.status, path, result.retry_after), result.retry_after)

    async def _fetch(self, url: str, credentials: bool) -> LinkResult:
        return (await self._load(url, credentials))[0]

    async def _load(self, url: str, credentials: bool, body: int = 0) -> tuple[LinkResult, str]:
        try:
            reply = await self.cdp.send("Network.loadNetworkResource", {
                "frameId": self.tab.frame, "url": url,
                "options": {"disableCache": True, "includeCredentials": credentials}},
                session_id=self.tab.session, timeout=self.timeout)
        except CDPError as exc:
            return LinkResult(url, None, "timeout" if exc.code == -1 else str(exc)), ""
        resource = reply.get("resource", {})
        text = ""
        if resource.get("stream"):
            if body:
                with contextlib.suppress(CDPError):
                    text = await self._read(resource["stream"], body)
            with contextlib.suppress(CDPError):  # closing the stream stops the download after the headers
                await self.cdp.send("IO.close", {"handle": resource["stream"]}, session_id=self.tab.session)
        headers = {str(key).lower(): str(value) for key, value in (resource.get("headers") or {}).items()}
        status = resource.get("httpStatusCode")
        error = resource.get("netErrorName") or None
        if resource.get("success") or (status is not None and error == "net::ERR_HTTP_RESPONSE_CODE_FAILURE"):
            error = None
        return LinkResult(
            url, status, error,
            content_type=headers.get("content-type", "").split(";", 1)[0].strip().lower(),
            attachment=headers.get("content-disposition", "").strip().lower().startswith("attachment"),
            challenge=headers.get("cf-mitigated", "").strip().lower() == "challenge",
            retry_after=retry_after(headers.get("retry-after"), time.time()),
        ), text

    async def _read(self, stream: str, limit: int) -> str:
        """Up to `limit` bytes of a resource's body, as text."""
        chunks, size = [], 0
        while size < limit:
            reply = await self.cdp.send("IO.read", {"handle": stream, "size": min(READ_CHUNK, limit - size)},
                                        session_id=self.tab.session, timeout=self.timeout)
            data = reply.get("data") or ""
            chunk = base64.b64decode(data) if reply.get("base64Encoded") else data.encode()
            chunks.append(chunk)
            size += len(chunk)
            if reply.get("eof") or not chunk:
                break
        return b"".join(chunks)[:limit].decode("utf-8", "replace")
