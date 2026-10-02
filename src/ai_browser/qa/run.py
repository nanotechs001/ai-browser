"""Run a whole-site QA: crawl same-site pages in a few tabs of their own, check every link, write the report."""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import anyio

from ..browser import Browser, BrowserError, url_problem
from ..workfs import WorkDir
from .checker import LinkChecker
from .issues import link_issue, link_verdict, merge
from .model import Issue, LinkResult, PageResult, QARun
from .page import PageVisitor, page_issues
from .polite import HOST_DELAY, HostGate
from .report import folder_for, save_shots, summary, write_report
from .urls import action_link, is_file, normalize, origin

WORKERS = 2  # tabs visiting pages at the same time
MAX_PAGES = 200
CRAWL_BUDGET = 180.0  # seconds for visiting pages...
LINK_BUDGET = 60.0  # ...then for checking the links not visited

Progress = Callable[[int, int, str], Awaitable[None]]


@dataclass
class Link:
    url: str
    internal: bool
    referrers: list[tuple[str, str]] = field(default_factory=list)  # (page, link text)
    result: LinkResult | None = None
    visited: bool = False


class Frontier:
    """Every link seen so far, and the same-site pages still to visit, in breadth-first order."""

    def __init__(self, site: str, max_variants: int = 5):
        self.site = site
        self.max_variants = max_variants
        self.links: dict[str, Link] = {}
        self.action: list[str] = []  # links that look like actions: never requested
        self._blocked: set[str] = set()
        self.variants: list[str] = []  # query variants beyond max_variants: status-checked only
        self._queue: deque[str] = deque()
        self._marked: set[str] = set()
        self._per_path: dict[str, int] = {}

    def mark(self, url: str) -> None:
        """A page that was visited: it is never queued again."""
        url = normalize(url) or url
        if url not in self._marked:
            self._marked.add(url)
            self._count(url)
        if url in self.links:
            self.links[url].visited = True

    def marked(self, url: str) -> bool:
        return (normalize(url) or url) in self._marked

    def add(self, url: str, page: str, text: str) -> str:
        """Record a link found on `page`; returns new, seen, external, file, action, variant or ignored."""
        url = normalize(url)
        if url is None:
            return "ignored"
        internal = origin(url) == self.site
        if internal and (url in self._blocked or action_link(url, text)):
            if url not in self._blocked:  # maybe seen before without its tell-tale text (an icon-only link)
                self._blocked.add(url)
                self.action.append(url)
                self.links.pop(url, None)
            return "action"
        link = self.links.get(url)
        if link is not None:
            link.referrers.append((page, text))
            return "seen"
        link = self.links[url] = Link(url, internal, [(page, text)])
        if url in self._marked:
            link.visited = True
            return "seen"
        if not internal:
            return "external"
        if is_file(url):
            return "file"
        if self._count(url) > self.max_variants:
            self.variants.append(url)
            return "variant"
        self._queue.append(url)
        return "new"

    def pop(self) -> str | None:
        while self._queue:
            url = self._queue.popleft()
            if url not in self._marked and url not in self._blocked:
                return url
        return None

    def pending(self) -> int:
        return len(self.queued())

    def queued(self) -> list[str]:
        """Pages still to visit, in order."""
        return [url for url in self._queue if url not in self._marked and url not in self._blocked]

    def _count(self, url: str) -> int:
        parts = urlsplit(url)
        key = f"{parts.scheme}://{parts.netloc}{parts.path}"
        self._per_path[key] = self._per_path.get(key, 0) + 1
        return self._per_path[key]


async def run_qa(browser: Browser, work: WorkDir, url: str, max_pages: int = 30, progress: Progress | None = None,
                 on_tabs: Callable[[], None] | None = None, crawl_budget: float = CRAWL_BUDGET,
                 link_budget: float = LINK_BUDGET, delay: float = HOST_DELAY) -> str:
    """Check a whole site in the session's browser, write the report and return its summary."""
    with browser.acting():  # pages QA opens may open popups: those are QA's to follow and close
        return await _run_qa(browser, work, url, max_pages, progress, on_tabs, crawl_budget, link_budget, delay)


async def _run_qa(browser: Browser, work: WorkDir, url: str, max_pages: int, progress: Progress | None,
                  on_tabs: Callable[[], None] | None, crawl_budget: float, link_budget: float, delay: float) -> str:
    problem = url_problem(url, browser.mode)
    if problem:
        raise BrowserError(f"{url}: {problem}")
    start = normalize(url)
    if start is None:
        raise BrowserError(f"{url}: qa needs a full http(s) address")
    max_pages = max(1, min(MAX_PAGES, int(max_pages)))
    started, clock = time.time(), time.monotonic()
    before = set(browser.owned)
    visitors: list[PageVisitor] = []
    checks: _Checks | None = None

    def tabs_changed() -> None:  # keeps the session registry current, so a crash can't strand our tabs
        if on_tabs is not None:
            with contextlib.suppress(Exception):
                on_tabs()

    async def report(done: int) -> None:
        if progress is not None:
            with contextlib.suppress(Exception):
                await progress(done, max_pages, f"checked {done} of up to {max_pages} pages")

    try:
        home = await browser.open_worker()  # opens the start page, then stays there to check links
        tabs_changed()
        visitors.append(PageVisitor(browser, home))
        first = await visitors[0].visit(start)
        if first.error:
            raise BrowserError(f"could not open {url}: {first.error}")
        site = origin(normalize(first.final_url) or start)
        folder = folder_for(site, started)
        save_shots(work, folder, 1, first)
        frontier = Frontier(site)
        frontier.mark(start)
        frontier.mark(first.final_url)
        pages, chains = [first], []
        if len(first.hops) >= 2:
            chains.append(_chain(start, first, [start]))
        for href, text in first.links:
            frontier.add(href, first.final_url, text)
        await report(1)
        checker = LinkChecker(browser.cdp, home, HostGate(delay=delay))  # one gate per run
        checks = _Checks(checker)
        workers = [PageVisitor(browser, await browser.open_worker()) for _ in range(WORKERS)]
        visitors += workers
        tabs_changed()
        stopped = await _crawl(frontier, checker, checks, workers, pages, chains, max_pages, clock + crawl_budget,
                               report, lambda page, number: save_shots(work, folder, number, page))
        await checks.finish(frontier.links.values(), time.monotonic() + link_budget)
        issues, unchecked = list(chains), []
        for page in pages:
            issues += page_issues(page, site)
        for link in frontier.links.values():
            if link.visited:
                continue
            if link.result is None:
                unchecked.append((link.url, "not checked: time limit"))
                continue
            issue = link_issue(link.result, link.internal, link.referrers)
            if issue is not None:
                issues.append(issue)
            elif link_verdict(link.result) == "unchecked":
                unchecked.append((link.url, _unchecked(link.result)))
        run = QARun(start, site, "your own browser" if browser.mode == "chrome" else "sandbox", started,
                    round(time.monotonic() - clock, 1), pages, merge(issues), unchecked, list(frontier.action),
                    frontier.pending(), stopped)
        return summary(run, write_report(work, run))
    finally:
        with anyio.CancelScope(shield=True):  # even when the call is cancelled, every QA tab must close
            if checks is not None:
                await checks.cancel()
            for visitor in visitors:
                visitor.close()
            if browser._adopting:  # popups still being set up
                await asyncio.wait(set(browser._adopting), timeout=2)
            for key in [key for key in browser.owned if key not in before]:  # our tabs, and popups pages opened
                tab = browser.owned.get(key)
                if tab is not None:
                    await browser.close_tab(tab)
            browser._opened = [tab for tab in browser._opened if tab.key in before]
            tabs_changed()


def _unchecked(result: LinkResult) -> str:
    """Why a link couldn't be judged: "not checked: …" when QA left it alone, else what the site answered."""
    error = result.error or ""
    if error.startswith("not checked: "):
        return error
    if error.startswith("stopped: "):
        return "not checked: " + error.removeprefix("stopped: ")
    return str(result.status or error or "no answer")


class _Checks:
    """Link checks running in the background while pages are visited, so a run doesn't end with a long wait."""

    def __init__(self, checker: LinkChecker):
        self.checker = checker
        self.tasks: dict[str, asyncio.Future] = {}

    def start(self, link: Link) -> None:
        if link.result is None and not link.visited and link.url not in self.tasks:
            self.tasks[link.url] = asyncio.ensure_future(self._check(link))

    async def _check(self, link: Link) -> None:
        result = await self.checker.check(link.url, link.internal)
        if link.result is None:
            link.result = result

    async def finish(self, links, deadline: float) -> None:
        """Check every link still unchecked, waiting until the deadline; later ones stay unchecked."""
        for link in links:
            self.start(link)
        pending = [task for task in self.tasks.values() if not task.done()]
        if pending:
            await asyncio.wait(pending, timeout=max(0.0, deadline - time.monotonic()))
        await self.cancel()

    async def cancel(self) -> None:
        late = [task for task in self.tasks.values() if not task.done()]
        for task in late:
            task.cancel()
        await asyncio.gather(*late, return_exceptions=True)


def _check_unvisited(frontier: Frontier, checks: _Checks, capacity: int, busy: set[str]) -> None:
    """Start checking the links no worker will visit: other sites, files, and pages beyond max_pages."""
    queued = frontier.queued()
    later = set(queued[:max(0, capacity)])  # these pages will be visited (and checked) by the workers
    for url, link in frontier.links.items():
        if url not in later and url not in busy:
            checks.start(link)


async def _crawl(frontier: Frontier, checker: LinkChecker, checks: _Checks, workers: list[PageVisitor],
                 pages: list[PageResult], chains: list[Issue], max_pages: int, deadline: float, report,
                 saved) -> str:
    """Visit queued pages with the workers until none are left, max_pages is reached or time runs out."""
    idle = list(workers)
    running: dict[asyncio.Future, tuple[str, PageVisitor]] = {}
    try:
        return await _visit_all(frontier, checker, checks, idle, running, pages, chains, max_pages, deadline, report,
                                saved)
    finally:  # cancelled, or done: no visit may go on in the background
        for task in running:
            task.cancel()
        if running:
            await asyncio.gather(*running, return_exceptions=True)


async def _visit_all(frontier, checker, checks, idle, running, pages, chains, max_pages, deadline, report,
                     saved) -> str:
    while True:
        while idle and len(pages) + len(running) < max_pages and time.monotonic() < deadline:
            url = frontier.pop()
            if url is None:
                break
            visitor = idle.pop()
            running[asyncio.ensure_future(_process(url, visitor, frontier, checker))] = (url, visitor)
        _check_unvisited(frontier, checks, max_pages - len(pages) - len(running),
                         {url for url, _ in running.values()})
        if not running:
            break
        done, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            idle.append(running.pop(task)[1])
            url, page = task.result()
            if page is None:
                continue
            final = normalize(page.final_url) or page.url
            link = frontier.links.get(url)
            if len(page.hops) >= 2:
                chains.append(_chain(url, page, [where for where, _ in link.referrers] if link else [url]))
            if origin(final) != frontier.site:
                continue  # it led to another site: checked as a link, not a page of this one
            if final != url and frontier.marked(final):
                continue  # a redirect to a page already checked
            frontier.mark(final)
            pages.append(page)
            saved(page, len(pages))
            for href, text in page.links:
                frontier.add(href, final, text)
            await report(len(pages))
    if not frontier.pending():
        return ""
    return "max_pages" if len(pages) >= max_pages else "time budget"


async def _process(url: str, visitor: PageVisitor, frontier: Frontier,
                   checker: LinkChecker) -> tuple[str, PageResult | None]:
    """Check the URL first; open it only when it is an HTML page (never a file or a download)."""
    link = frontier.links.get(url)
    try:
        result = link.result if link is not None and link.result is not None else await checker.check(url, True)
        if link is not None:
            link.result = result
        if link_verdict(result) != "ok" or not result.page:
            return url, None
        frontier.mark(url)
        return url, await visitor.visit(url)
    except Exception as exc:  # one page must not end the whole run
        return url, PageResult(url, error=f"{type(exc).__name__}: {exc}")


def _chain(url: str, page: PageResult, referrers: list[str]) -> Issue:
    final = page.final_url or page.url
    return Issue("low", "redirect chain", f"{url} → {final} ({len(page.hops)} redirects)",
                 list(dict.fromkeys(referrers)))
