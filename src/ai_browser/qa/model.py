"""Data passed between the QA crawl, page visits, link checks and the report."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..checks import Check

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
SITE_STOPPED = "host stopped"  # QARun.stopped when the site under QA refused (429, 403 or a bot check)
HTML_TYPES = {"text/html", "application/xhtml+xml", ""}  # no content type: browsers sniff, usually a page


@dataclass
class Issue:
    severity: str  # high | medium | low
    kind: str  # "broken link", "sideways scroll", ...
    detail: str  # what exactly: the URL and status, the message, the elements
    pages: list[str]  # where it shows up
    sizes: list[str] = field(default_factory=list)  # screen sizes, for layout issues
    extra: str = ""  # link text, source location...

    @property
    def rank(self) -> tuple:
        return SEVERITY_ORDER[self.severity], -len(self.pages), self.kind, self.detail


@dataclass
class LinkResult:
    url: str
    status: int | None
    error: str | None  # network error name (net::ERR_...) or "timeout"
    content_type: str = ""
    attachment: bool = False
    challenge: bool = False  # a bot check answered instead of the page
    retry_after: float | None = None  # seconds the site asked for (its Retry-After header)

    @property
    def page(self) -> bool:
        """An HTML page a browser would show, not a file or a download."""
        return self.content_type in HTML_TYPES and not self.attachment


@dataclass
class SizeResult:
    name: str  # desktop | tablet | mobile
    scrolls: bool  # the page scrolls sideways at this size
    overflow_px: int
    offenders: list[str]  # the outermost elements sticking out, named
    shot: bytes  # full-page JPEG (emptied once written to disk)
    thumb: bytes  # small JPEG of the top of the page
    width: int
    height: int


@dataclass
class PageResult:
    url: str
    final_url: str = ""
    status: int | None = None
    title: str = ""
    hops: list[tuple[str, int]] = field(default_factory=list)  # redirects on the way: (url, status)
    links: list[tuple[str, str]] = field(default_factory=list)  # (href, text)
    sizes: dict[str, SizeResult] = field(default_factory=dict)
    console: list[tuple[str, str]] = field(default_factory=list)  # (message, where)
    exceptions: list[tuple[str, str]] = field(default_factory=list)  # (message, where)
    failed: list[tuple[str, str, str]] = field(default_factory=list)  # (url, resource type, "404" or why)
    insecure: list[tuple[str, str]] = field(default_factory=list)  # (url, "blockable" | "optionally-blockable")
    downloads: list[str] = field(default_factory=list)  # downloads the page started (each one cancelled)
    error: str = ""  # the page itself could not be loaded
    note: str = ""  # the page changed while it was checked: what was found so far is kept
    check: Check | None = None  # the page is a bot check: handed to the user, never woken, scrolled or photographed
    seconds: float = 0.0


@dataclass
class QARun:
    start_url: str
    site: str  # origin of the start page, after its redirects
    browser: str  # "sandbox" | "your own browser"
    started: float  # epoch seconds
    seconds: float
    pages: list[PageResult]
    issues: list[Issue]  # merged and ranked
    unchecked: list[tuple[str, str]]  # links that couldn't be judged: (url, why)
    not_followed: list[str]  # action links left alone (log out, delete...)
    more_found: int  # pages found but not checked
    stopped: str = ""  # "max_pages", "time budget", SITE_STOPPED or ""
    stopped_hosts: dict[str, str] = field(default_factory=dict)  # host -> why QA stopped asking it
    robots: str = ""  # how robots.txt was used: followed, ignored at the user's request, or the site closed
