"""Check links from inside the browser, so they are tested from the same network the pages use."""

from __future__ import annotations

import asyncio
import contextlib
from urllib.parse import urlsplit

from ..browser import Tab
from ..cdp import CDP, CDPError
from .model import LinkResult


class LinkChecker:
    """Asks the browser to fetch each URL (Network.loadNetworkResource, from one parked tab).

    Works for any site (no CORS), follows redirects, sends the browser's cookies only when asked, and stops a big
    file after its headers. At most `per_host` checks run against one site at a time, and `total` overall."""

    def __init__(self, cdp: CDP, tab: Tab, per_host: int = 2, total: int = 8, timeout: float = 12.0):
        self.cdp = cdp
        self.tab = tab
        self.per_host = per_host
        self.timeout = timeout
        self._total = asyncio.Semaphore(total)
        self._hosts: dict[str, asyncio.Semaphore] = {}

    async def check(self, url: str, credentials: bool, priority: bool = False) -> LinkResult:
        """The URL's status; a timeout gets one more try. `priority` skips the queue (a page about to be visited)."""
        result = await self._queued(url, credentials, priority)
        if result.error == "timeout":  # servers have slow moments: try once more before calling it a timeout
            result = await self._queued(url, credentials, priority)
        return result

    async def _queued(self, url: str, credentials: bool, priority: bool) -> LinkResult:
        if priority:
            return await self._fetch(url, credentials)
        host = urlsplit(url).hostname or ""
        polite = self._hosts.setdefault(host, asyncio.Semaphore(self.per_host))
        async with polite, self._total:
            return await self._fetch(url, credentials)

    async def _fetch(self, url: str, credentials: bool) -> LinkResult:
        try:
            reply = await self.cdp.send("Network.loadNetworkResource", {
                "frameId": self.tab.frame, "url": url,
                "options": {"disableCache": True, "includeCredentials": credentials}},
                session_id=self.tab.session, timeout=self.timeout)
        except CDPError as exc:
            return LinkResult(url, None, "timeout" if exc.code == -1 else str(exc))
        resource = reply.get("resource", {})
        if resource.get("stream"):  # closing the stream stops the download after the headers
            with contextlib.suppress(CDPError):
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
        )
