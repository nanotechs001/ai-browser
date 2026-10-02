"""Website QA's manners: one request at a time per site, robots.txt, Retry-After, and the big sites QA leaves alone.

Bursts from the user's home network trigger firewalls and Google's per-network "unusual traffic" limit; then the
user's own browsing gets challenged too. So every request QA makes takes its host's turn at one HostGate per run."""

from __future__ import annotations

import asyncio
import contextlib
import email.utils
import math
import urllib.robotparser
from collections.abc import AsyncIterator
from datetime import timezone

from ..checks import google_host

HOST_DELAY = 1.0  # seconds from the end of one request to a host to the start of the next
MAX_CRAWL_DELAY = 10  # a robots.txt Crawl-delay is followed up to this
MAX_RETRY_WAIT = 30  # a 503 asking for at most this long is waited out once
COOL_DOWN = 300  # seconds before a new qa on a host that refused without saying for how long
AGENT = "ai-browser"  # robots.txt groups for this name, then for *, apply
BIG_SITES = ("goo.gl", "g.co", "youtube.com", "youtu.be", "facebook.com", "fb.com", "fb.me", "instagram.com",
             "whatsapp.com", "wa.me", "m.me", "linkedin.com", "lnkd.in", "x.com", "twitter.com", "t.co", "tiktok.com",
             "pinterest.com")  # and every Google host (checks.google_host)
BIG_SITE_NOTE = "not checked: big site (open by hand if it matters)"
ROBOTS_NOTE = "not checked: robots.txt"
ROBOTS_FOLLOWED = "robots.txt: followed"
_STATUS = {403: "403 Forbidden", 429: "429 Too Many Requests", 503: "503 Service Unavailable"}


def big_site(host: str) -> bool:
    """A site whose links QA never requests: it refuses or rate-limits automated checks anyway."""
    host = (host or "").lower().rstrip(".")
    return google_host(host) or any(host == site or host.endswith("." + site) for site in BIG_SITES)


def retry_after(value: str | None, now: float) -> float | None:
    """Seconds to wait from a Retry-After header (seconds, or an HTTP date), or None when it says nothing usable."""
    text = (value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return float(text)
    try:
        when = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, when.timestamp() - now)


def pause(seconds: float) -> str:
    """'2 minutes', '1 minute', '30 seconds'."""
    if seconds >= 60:
        minutes = math.ceil(seconds / 60)
        return f"{minutes} minute{'' if minutes == 1 else 's'}"
    whole = max(1, math.ceil(seconds))
    return f"{whole} second{'' if whole == 1 else 's'}"


def stop_reason(status: int | None, path: str, wait: float | None = None, challenge: bool = False) -> str:
    """Why QA stopped asking a host: 'answered 429 Too Many Requests on /pricing (it asked for a 2-minute pause)'."""
    what = "with a bot check" if challenge else _STATUS.get(status, str(status))
    asked = ""
    if wait is not None:
        amount, unit = pause(wait).split(" ")
        asked = f" (it asked for a {amount}-{unit.rstrip('s')} pause)"
    return f"answered {what} on {path}{asked}"


def short_reason(why: str) -> str:
    """'429', '403', '503' or 'bot check', from a stop_reason text."""
    if why.startswith("answered with a bot check"):
        return "bot check"
    return why.removeprefix("answered ").split(" ", 1)[0]


def cool_reason(why: str, wait: float | None) -> str:
    """For the Engine's cool-down note: '429, it asked for 2 minutes'."""
    short = short_reason(why)
    return f"{short}, it asked for {pause(wait)}" if wait is not None else short


class HostStopped(Exception):
    """A request to a host QA stopped on: nothing was sent."""

    def __init__(self, host: str, why: str):
        super().__init__(f"{host} {why}")
        self.host, self.why = host, why


class HostGate:
    """One request at a time per host, `delay` apart, in the order asked; at most `total` hosts at once."""

    def __init__(self, delay: float = HOST_DELAY, total: int = 4):
        self.delay = delay
        self._total = asyncio.Semaphore(total)
        self._locks: dict[str, asyncio.Lock] = {}  # asyncio.Lock wakes its waiters first come, first served
        self._free: dict[str, float] = {}  # host -> loop time from which its next request may start
        self._delays: dict[str, float] = {}
        self.stops: dict[str, str] = {}  # host -> why QA stopped asking it
        self.waits: dict[str, float | None] = {}  # host -> the pause it asked for, in seconds

    @contextlib.asynccontextmanager
    async def turn(self, host: str) -> AsyncIterator[None]:
        host = host.lower()
        self._refuse(host)
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            self._refuse(host)
            loop = asyncio.get_running_loop()
            wait = self._free.get(host, 0.0) - loop.time()
            if wait > 0:
                await asyncio.sleep(wait)
                self._refuse(host)
            async with self._total:
                self._refuse(host)  # it may have been stopped while this turn waited for a free slot
                try:
                    yield
                finally:
                    self._free[host] = loop.time() + self.delay_for(host)

    def _refuse(self, host: str) -> None:
        if host in self.stops:
            raise HostStopped(host, self.stops[host])

    def stop(self, host: str, why: str, wait: float | None = None) -> None:
        """A 429, a 403 or a bot check: every later turn on this host raises HostStopped. The first reason stays."""
        host = host.lower()
        if host not in self.stops:
            self.stops[host] = why
            self.waits[host] = wait

    def stopped(self, host: str) -> str | None:
        return self.stops.get(host.lower())

    def set_delay(self, host: str, seconds: float) -> None:
        """A robots.txt Crawl-delay: it replaces the pause when longer, up to MAX_CRAWL_DELAY."""
        self._delays[host.lower()] = min(float(MAX_CRAWL_DELAY), max(self.delay, float(seconds)))

    def delay_for(self, host: str) -> float:
        return self._delays.get(host.lower(), self.delay)


class Robots:
    """robots.txt as QA follows it (RFC 9309 for the 4xx and 5xx rules; a 403, 429 or bot check stops the host)."""

    def __init__(self, parser: urllib.robotparser.RobotFileParser | None = None, crawl_delay: float | None = None,
                 note: str = "", closed: bool = False, stops: bool = False):
        self._parser = parser
        self.crawl_delay = crawl_delay
        self.note = note
        self.closed = closed  # 5xx or no answer: treated as closed to crawlers
        self.stops = stops  # 403, 429 or a bot check: the host is stopped (the checker stopped it)

    @classmethod
    def from_reply(cls, status: int | None, text: str, challenge: bool = False) -> Robots:
        if challenge:
            return cls(note="robots.txt answered with a bot check", stops=True)
        if status in (403, 429):
            return cls(note=f"robots.txt answered {status}", stops=True)
        if status is None or status >= 500:
            answer = "didn't answer" if status is None else f"answered {status}"
            return cls(note=f"robots.txt {answer}: the site is treated as closed to crawlers", closed=True)
        if 200 <= status < 300:
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(text.splitlines())
            delay = parser.crawl_delay(AGENT)
            return cls(parser, min(float(MAX_CRAWL_DELAY), float(delay)) if delay is not None else None,
                       ROBOTS_FOLLOWED)
        return cls(note=f"robots.txt answered {status}: no rules")

    def allowed(self, url: str) -> bool:
        if self.closed:
            return False
        return True if self._parser is None else self._parser.can_fetch(AGENT, url)
