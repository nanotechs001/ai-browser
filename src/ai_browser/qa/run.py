"""Run a whole-site QA politely: crawl same-site pages in a tab of their own, one request at a time per site, check
every link, write the report. robots.txt is followed, a host that refuses is left alone, big sites are never asked."""

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
from .model import SITE_STOPPED, Issue, LinkResult, PageResult, QARun
from .page import PageVisitor, page_issues
from .polite import (BIG_SITE_NOTE, COOL_DOWN, HOST_DELAY, ROBOTS_NOTE, HostGate, HostStopped, Robots, big_site,
                     cool_reason, short_reason)
from .report import folder_for, save_shots, summary, write_report
from .urls import action_link, is_file, normalize, origin

WORKERS = 1  # one page tab: a second one on the same site would only wait for the gate
MAX_PAGES = 200
CRAWL_BUDGET = 300.0  # seconds for visiting pages (about 6 s a page at the polite pace)...
LINK_BUDGET = 60.0  # ...then for checking the links not visited
ROBOTS_LIMIT = 500_000  # bytes of robots.txt read
IGNORED_ROBOTS = "robots.txt: ignored at the user's request"

Progress = Callable[[int, int, str], Awaitable[None]]
HostStoppedHook = Callable[[str, float, str], None]  # (host, until, why): the Engine's cool-down


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


class _Rules:
    """What QA may request: never a big site, and only what each origin's robots.txt allows of its own pages."""

    def __init__(self, checker: LinkChecker, ignore: bool):
        self.checker = checker
        self.ignore = ignore
        self.robots: dict[str, Robots] = {}

    async def read(self, site: str) -> Robots | None:
        """robots.txt of an origin, fetched once through the gate (None when the user said the site is theirs)."""
        if self.ignore:
            return None
        if site not in self.robots:
            result, text = await self.checker.fetch_text(site + "/robots.txt", ROBOTS_LIMIT)
            robots = self.robots[site] = Robots.from_reply(result.status, text, result.challenge)
            if robots.crawl_delay:
                self.checker.gate.set_delay(urlsplit(site).hostname or "", robots.crawl_delay)
        return self.robots[site]

    def skip(self, url: str, internal: bool) -> str | None:
        """Why a link is never requested, or None."""
        if big_site(urlsplit(url).hostname or ""):
            return BIG_SITE_NOTE
        robots = self.robots.get(origin(url))
        if internal and robots is not None and not robots.allowed(url):
            return ROBOTS_NOTE
        return None

    def note(self, site: str) -> str:
        if self.ignore:
            return IGNORED_ROBOTS
        robots = self.robots.get(site)
        return robots.note if robots is not None else ""


async def run_qa(browser: Browser, work: WorkDir, url: str, max_pages: int = 30, progress: Progress | None = None,
                 on_tabs: Callable[[], None] | None = None, crawl_budget: float = CRAWL_BUDGET,
                 link_budget: float = LINK_BUDGET, delay: float = HOST_DELAY, ignore_robots: bool = False,
                 on_host_stopped: HostStoppedHook | None = None) -> str:
    """Check a whole site in the session's browser, politely, write the report and return its summary.
    `ignore_robots` only when the user says the site is theirs; `on_host_stopped(host, until, why)` hears of every
    host that refused, for the Engine's cool-down."""
    with browser.acting():  # pages QA opens may open popups: those are QA's to follow and close
        return await _run_qa(browser, work, url, max_pages, progress, on_tabs, crawl_budget, link_budget, delay,
                             ignore_robots, on_host_stopped)


async def _run_qa(browser: Browser, work: WorkDir, url: str, max_pages: int, progress: Progress | None,
                  on_tabs: Callable[[], None] | None, crawl_budget: float, link_budget: float, delay: float,
                  ignore_robots: bool, on_host_stopped: HostStoppedHook | None) -> str:
    problem = url_problem(url, browser.mode)
    if problem:
        raise BrowserError(f"{url}: {problem}")
    start = normalize(url)
    if start is None:
        raise BrowserError(f"{url}: qa needs a full http(s) address")
    start_host = urlsplit(start).hostname or ""
    if big_site(start_host):
        raise BrowserError(f"{url}: {start_host} is a big site, and qa never crawls one (they refuse or rate-limit "
                           "automated checks); open single pages with open")
    max_pages = max(1, min(MAX_PAGES, int(max_pages)))
    started, clock = time.time(), time.monotonic()
    before = set(browser.owned)
    visitors: list[PageVisitor] = []
    checks: _Checks | None = None
    gate = HostGate(delay=delay)  # one gate per run: every request QA makes takes its host's turn

    def tabs_changed() -> None:  # keeps the session registry current, so a crash can't strand our tabs
        if on_tabs is not None:
            with contextlib.suppress(Exception):
                on_tabs()

    async def report(done: int) -> None:
        if progress is not None:
            with contextlib.suppress(Exception):
                await progress(done, max_pages, f"checked {done} of up to {max_pages} pages")

    try:
        home = await browser.open_worker()  # reads robots.txt, opens the start page, then stays there to check links
        tabs_changed()
        checker = LinkChecker(browser.cdp, home, gate)
        rules = _Rules(checker, ignore_robots)
        robots = await rules.read(origin(start))
        if robots is not None and not robots.allowed(start):
            why = robots.note if robots.closed else "robots.txt asks crawlers not to visit this page"
            return (f"qa {url} — nothing checked: {why}. If the site is the user's own (a staging site, say) and they "
                    "say so, run qa again with ignore_robots=true.")
        visitors.append(PageVisitor(browser, home, gate))
        try:
            first = await visitors[0].visit(start)
        except HostStopped as stopped:
            return f"qa {url} — nothing checked: {stopped.host} {stopped.why}"
        if first.error:
            raise BrowserError(f"could not open {url}: {first.error}")
        site = origin(normalize(first.final_url) or start)
        if site != origin(start):  # redirected to another origin: its own robots.txt, before any other page of it
            await rules.read(site)
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
        checks = _Checks(checker, rules)
        workers = [PageVisitor(browser, await browser.open_worker(), gate) for _ in range(WORKERS)]
        visitors += workers
        tabs_changed()
        site_host = urlsplit(site).hostname or ""
        stopped = await _crawl(frontier, checker, checks, workers, pages, chains, max_pages, clock + crawl_budget,
                               report, lambda page, number: save_shots(work, folder, number, page), rules, site_host)
        await checks.finish(frontier.links.values(), time.monotonic() + link_budget)
        issues, unchecked = list(chains), []
        for page in pages:
            issues += page_issues(page, site)
        late = "not checked: QA stopped early" if stopped == SITE_STOPPED else "not checked: time limit"
        for link in frontier.links.values():
            if link.visited:
                continue
            if link.result is None:
                unchecked.append((link.url, late))
                continue
            issue = link_issue(link.result, link.internal, link.referrers)
            if issue is not None:
                issues.append(issue)
            elif link_verdict(link.result) == "unchecked":
                unchecked.append((link.url, _unchecked(link.result)))
        run = QARun(start, site, "your own browser" if browser.mode == "chrome" else "sandbox", started,
                    round(time.monotonic() - clock, 1), pages, merge(issues), unchecked, list(frontier.action),
                    frontier.pending(), stopped, stopped_hosts=dict(gate.stops), robots=rules.note(site))
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
            _tell_stopped(gate, on_host_stopped)


def _unchecked(result: LinkResult) -> str:
    """Why a link couldn't be judged: "not checked: …" when QA left it alone, else what the site answered."""
    error = result.error or ""
    if error.startswith("not checked: "):
        return error
    if error.startswith("stopped: "):
        return "not checked: " + error.removeprefix("stopped: ")
    return str(result.status or error or "no answer")


def _tell_stopped(gate: HostGate, hook: HostStoppedHook | None) -> None:
    """Every host that refused, for the Engine's cool-down: until the pause it asked for, or COOL_DOWN."""
    if hook is None:
        return
    now = time.time()
    for host, why in gate.stops.items():
        wait = gate.waits.get(host)
        with contextlib.suppress(Exception):
            hook(host, now + (wait if wait is not None else COOL_DOWN), cool_reason(why, wait))


class _Checks:
    """Link checks running in the background while pages are visited, so a run doesn't end with a long wait."""

    def __init__(self, checker: LinkChecker, rules: _Rules):
        self.checker = checker
        self.rules = rules
        self.tasks: dict[str, asyncio.Future] = {}

    def start(self, link: Link) -> None:
        if link.result is not None or link.visited or link.url in self.tasks:
            return
        note = self.rules.skip(link.url, link.internal)
        if note is not None:  # a big site, or robots.txt: never requested
            link.result = LinkResult(link.url, None, note)
            return
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
                 saved, rules: _Rules, site_host: str) -> str:
    """Visit queued pages with the workers until none are left, max_pages is reached, time runs out or the site
    refused."""
    idle = list(workers)
    running: dict[asyncio.Future, tuple[str, PageVisitor]] = {}
    try:
        return await _visit_all(frontier, checker, checks, idle, running, pages, chains, max_pages, deadline, report,
                                saved, rules, site_host)
    finally:  # cancelled, or done: no visit may go on in the background
        for task in running:
            task.cancel()
        if running:
            await asyncio.gather(*running, return_exceptions=True)


async def _visit_all(frontier, checker, checks, idle, running, pages, chains, max_pages, deadline, report,
                     saved, rules, site_host) -> str:
    gate = checker.gate
    while True:
        while idle and len(pages) + len(running) < max_pages and time.monotonic() < deadline \
                and gate.stopped(site_host) is None:
            url = frontier.pop()
            if url is None:
                break
            visitor = idle.pop()
            running[asyncio.ensure_future(_process(url, visitor, frontier, checker, rules))] = (url, visitor)
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
    if gate.stopped(site_host) is not None:
        return SITE_STOPPED
    if not frontier.pending():
        return ""
    return "max_pages" if len(pages) >= max_pages else "time budget"


async def _process(url: str, visitor: PageVisitor, frontier: Frontier, checker: LinkChecker,
                   rules: _Rules) -> tuple[str, PageResult | None]:
    """Check the URL first; open it only when it is an HTML page (never a file or a download), and never when
    robots.txt excludes it."""
    link = frontier.links.get(url)
    note = rules.skip(url, True)
    if note is not None:
        if link is not None and link.result is None:
            link.result = LinkResult(url, None, note)
        return url, None
    try:
        result = link.result if link is not None and link.result is not None else await checker.check(url, True)
        if link is not None:
            link.result = result
        if link_verdict(result) != "ok" or not result.page:
            return url, None
        frontier.mark(url)
        try:
            return url, await visitor.visit(url)
        except HostStopped as stopped:  # the site refused something else meanwhile: this page wasn't visited
            if link is not None:
                link.visited = False
                link.result = LinkResult(url, None, f"stopped: {stopped.host} refused ({short_reason(stopped.why)})")
            return url, None
    except Exception as exc:  # one page must not end the whole run
        return url, PageResult(url, error=f"{type(exc).__name__}: {exc}")


def _chain(url: str, page: PageResult, referrers: list[str]) -> Issue:
    final = page.final_url or page.url
    return Issue("low", "redirect chain", f"{url} → {final} ({len(page.hops)} redirects)",
                 list(dict.fromkeys(referrers)))
