"""Website QA against a throwaway headless Chrome and the planted test site (pages/qa/)."""

import asyncio
import time

import pytest

from ai_browser.chrome import chrome_binary

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


@CHROME
async def test_link_checker_reports_status_files_and_errors(chrome_browser):
    from ai_browser.qa.checker import LinkChecker
    from ai_browser.qa.issues import link_verdict
    from ai_browser.qa.polite import HostGate

    browser, base, _ = chrome_browser
    await browser.open(base + "qa/index.html")
    other = base.replace("localhost", "127.0.0.1")
    checker = LinkChecker(browser.cdp, browser.current, HostGate(delay=0.05))
    results = await asyncio.gather(*[checker.check(url, credentials) for url, credentials in [
        (base + "qa/about.html", True), (base + "qa/missing.html", True), (other + "qa/forbidden", False),
        (base + "qa/old", True), (base + "qa/files/brochure.zip", True), (base + "qa/attachment", True),
        ("http://no-such-host.invalid/", False)]])
    about, missing, forbidden, old, zip_file, attachment, nowhere = results
    assert about.status == 200 and about.page
    assert link_verdict(missing) == "broken" and missing.status == 404
    assert link_verdict(forbidden) == "unchecked"
    assert old.status == 200 and old.page  # redirects are followed
    assert link_verdict(zip_file) == "ok" and not zip_file.page
    assert attachment.status == 200 and attachment.attachment and not attachment.page
    assert link_verdict(nowhere) == "broken" and nowhere.error == "net::ERR_NAME_NOT_RESOLVED"


@CHROME
async def test_visit_finds_planted_page_problems(chrome_browser):
    from ai_browser.qa.page import PageVisitor, page_issues
    from ai_browser.qa.polite import HostGate

    browser, base, _ = chrome_browser
    site = base.rstrip("/")
    tab = await browser.open_worker()
    visitor = PageVisitor(browser, tab, HostGate(delay=0.05))
    try:
        contact = await visitor.visit(base + "qa/contact.html")
        kinds = {(i.severity, i.kind) for i in page_issues(contact, site)}
        assert kinds == {("medium", "console error"), ("high", "script error")}
        products = await visitor.visit(base + "qa/products.html")
        assert products.sizes["mobile"].scrolls and not products.sizes["tablet"].scrolls
        assert not products.sizes["desktop"].scrolls
        assert products.sizes["mobile"].offenders[0].startswith('div.wide-table "')
        [sideways] = page_issues(products, site)
        assert (sideways.severity, sideways.kind, sideways.sizes) == ("high", "sideways scroll", ["mobile"])
        team = await visitor.visit(base + "qa/team.html")
        [image] = page_issues(team, site)
        assert (image.severity, image.kind) == ("medium", "broken image") and "missing-photo.jpg" in image.detail
        about = await visitor.visit(base + "qa/about.html")
        assert page_issues(about, site) == [] and about.title == "About us"
        old = await visitor.visit(base + "qa/old")
        assert [status for _, status in old.hops] == [301, 301] and old.final_url == base + "qa/about.html"
        for size in ("desktop", "tablet", "mobile"):
            shot = about.sizes[size]
            assert shot.shot[:2] == b"\xff\xd8" and shot.thumb[:2] == b"\xff\xd8" and shot.width <= 1280
    finally:
        visitor.close()
        await browser.close_tab(tab)
    assert tab.key not in browser.owned


@CHROME
async def test_visit_stays_quick_on_heavy_noisy_and_dialog_pages(chrome_browser):
    from ai_browser.qa.page import PageVisitor
    from ai_browser.qa.polite import HostGate

    browser, base, _ = chrome_browser
    tab = await browser.open_worker()
    visitor = PageVisitor(browser, tab, HostGate(delay=0.05))
    try:
        for page, limit in (("heavy.html", 6), ("qa/pending.html", 10), ("qa/greeting.html", 6)):
            started = time.monotonic()
            result = await visitor.visit(base + page)
            assert not result.error and time.monotonic() - started < limit, page
    finally:
        visitor.close()
        await browser.close_tab(tab)


@CHROME
async def test_worker_tabs_never_become_the_working_tab(chrome_browser):
    browser, base, _ = chrome_browser
    working = browser.current
    tab = await browser.open_worker()
    assert browser.current is working and tab.key in browser.owned
    await browser.close_tab(tab)
    assert tab.key not in browser.owned


EXPECTED = {("high", "broken link", "qa/missing.html (404)"),
            ("medium", "broken link (external)", "qa/missing.html (404)"),
            ("high", "sideways scroll", "products.html"), ("medium", "console error", "Contact form failed to load"),
            ("high", "script error", "map widget crashed"), ("medium", "broken image", "missing-photo.jpg"),
            ("low", "redirect chain", "qa/old")}


def matches(issues, expected):
    """Each expected (severity, kind, text) matches exactly one issue, and nothing else is reported."""
    remaining = list(issues)
    for severity, kind, text in expected:
        hits = [i for i in remaining if (i.severity, i.kind) == (severity, kind)
                and (text in i.detail or any(text in page for page in i.pages))]
        assert len(hits) == 1, (severity, kind, text, issues)
        remaining.remove(hits[0])
    assert remaining == [], remaining


@CHROME
async def test_qa_run_finds_exactly_the_planted_problems(chrome_browser, monkeypatch):
    from ai_browser.qa import run as run_module

    browser, base, _ = chrome_browser
    captured, saved, saved_before_report = {}, [], []
    real_write, real_save = run_module.write_report, run_module.save_shots

    def keep(work, run):
        captured["run"] = run
        saved_before_report.append(len(saved))
        return real_write(work, run)

    def save(work, folder, number, page):
        saved.append(number)
        return real_save(work, folder, number, page)

    monkeypatch.setattr(run_module, "write_report", keep)
    monkeypatch.setattr(run_module, "save_shots", save)
    working, before = browser.current, set(browser.owned)
    progress = []

    async def note(done, total, message):
        progress.append(done)

    started = time.monotonic()
    text = await run_module.run_qa(browser, browser.work, base + "qa/index.html", progress=note, delay=0.05)
    took = time.monotonic() - started
    run = captured["run"]
    matches(run.issues, EXPECTED)
    assert [url for url, _ in run.unchecked] == [base.replace("localhost", "127.0.0.1") + "qa/forbidden"]
    assert run.not_followed == [base + "qa/logout.html", base + "qa/account/exit"]
    opened = {page.final_url for page in run.pages}
    assert base + "qa/files/brochure.zip" not in opened and base + "qa/attachment" not in opened
    assert base + "qa/logout.html" not in opened and len(run.pages) == 6
    assert progress == list(range(1, 7)) and took < 30  # one page tab now
    assert browser.current is working and set(browser.owned) == before
    assert text.splitlines()[1].startswith("issues: 3 high · 3 medium · 1 low")
    assert saved_before_report == [6]  # every page's screenshots were on disk before the report was written
    html = browser.work.to_host(next(line for line in text.splitlines() if line.startswith("report: "))
                                .split()[1]).read_text(encoding="utf-8")
    assert "products.html" in html


@CHROME
async def test_qa_run_respects_max_pages(chrome_browser):
    from ai_browser.qa import run_qa

    browser, base, _ = chrome_browser
    text = await run_qa(browser, browser.work, base + "qa/index.html", max_pages=2, delay=0.05)
    assert "2 pages" in text.splitlines()[0] and "stopped at max_pages" in text.splitlines()[0]


@CHROME
async def test_qa_refuses_local_files_in_the_users_own_browser(chrome_browser):
    from ai_browser.browser import BrowserError
    from ai_browser.qa import run_qa

    browser, _, _ = chrome_browser
    with pytest.raises(BrowserError, match="only web pages"):
        await run_qa(browser, browser.work, "file:///etc/hosts")


@CHROME
async def test_a_link_that_is_slow_once_is_tried_again(chrome_browser):
    from ai_browser.qa.checker import LinkChecker
    from ai_browser.qa.polite import HostGate

    browser, base, _ = chrome_browser
    await browser.open(base + "qa/index.html")
    checker = LinkChecker(browser.cdp, browser.current, HostGate(delay=0.05), timeout=1.0)
    result = await checker.check(base + "qa/flaky", True)
    assert result.status == 200 and result.error is None


def record_timeline(monkeypatch) -> tuple[list[tuple[float, str]], list[tuple[float, str]]]:
    """(every link check QA's checker sends, every page visit's navigation), each as (when, url)."""
    from ai_browser.qa.checker import LinkChecker
    from ai_browser.qa.page import PageVisitor

    fetches, navigations = [], []
    real_fetch, real_send = LinkChecker._fetch, PageVisitor._send

    async def fetch(self, url, credentials):
        fetches.append((time.monotonic(), url))
        return await real_fetch(self, url, credentials)

    async def send(self, method, params=None, timeout=30):
        if method == "Page.navigate":
            navigations.append((time.monotonic(), params["url"]))
        return await real_send(self, method, params, timeout)

    monkeypatch.setattr(LinkChecker, "_fetch", fetch)
    monkeypatch.setattr(PageVisitor, "_send", send)
    return fetches, navigations


@CHROME
async def test_other_sites_links_are_checked_while_pages_are_visited(chrome_browser, monkeypatch):
    run_module, captured = capture(monkeypatch)
    fetches, navigations = record_timeline(monkeypatch)
    browser, base, _ = chrome_browser
    await run_module.run_qa(browser, browser.work, base + "qa/index.html", delay=0.05)
    run = captured["run"]
    assert any(i.kind == "broken link (external)" for i in run.issues)
    assert [why for _, why in run.unchecked] == ["403"]
    last_visit = navigations[-1][0]
    elsewhere = [at for at, url in fetches if url.startswith("http://127.0.0.1:")]
    assert elsewhere and all(at < last_visit for at in elsewhere)  # other sites: during the crawl, on their own turns
    brochure = [at for at, url in fetches if url == base + "qa/files/brochure.zip"]
    assert brochure and all(at > last_visit for at in brochure)  # the site's own: after its pages, never ahead of them


@CHROME
async def test_a_link_rich_site_gets_its_pages_visited_before_its_other_links_are_checked(chrome_browser, monkeypatch):
    run_module, captured = capture(monkeypatch)
    fetches, navigations = record_timeline(monkeypatch)
    browser, base, _ = chrome_browser
    pages = [base + f"qa3/24/{n}.html" for n in range(5)]
    text = await run_module.run_qa(browser, browser.work, pages[0], max_pages=5, delay=0.05)
    run = captured["run"]
    assert [page.url for page in run.pages] == pages and "5 pages" in text.splitlines()[0]
    assert [url for _, url in navigations] == pages
    last_visit = navigations[-1][0]
    early = [url for at, url in fetches if at < last_visit]
    assert early == pages[1:]  # before the last visit, only each visit's own status check went to the site
    later = {url for at, url in fetches if at > last_visit}
    assert len(later) == 24 * 5 - 4 and later.isdisjoint(pages)  # then every link not visited, once
    assert not run.unchecked



@CHROME
async def test_a_cancelled_run_closes_its_tabs(chrome_browser):
    import anyio

    from ai_browser.qa import run_qa

    browser, base, _ = chrome_browser
    working, before = browser.current, set(browser.owned)
    with anyio.move_on_after(1.0):  # how the MCP server cancels a tool call the user interrupted
        await run_qa(browser, browser.work, base + "qa/index.html", delay=0.05)
    await asyncio.sleep(0.5)
    assert browser.current is working and set(browser.owned) == before and browser._opened == []


@CHROME
async def test_a_page_that_starts_a_download_is_stopped_and_reported(chrome_browser, tmp_path):
    from ai_browser.qa.page import PageVisitor, page_issues

    browser, base, _ = chrome_browser
    downloads = tmp_path / "downloads"
    # stands in for a browser that downloads (the user's own setting, not something QA changes)
    await browser.cdp.send("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(downloads)})
    tab = await browser.open_worker()
    visitor = PageVisitor(browser, tab)
    try:
        page = await visitor.visit(base + "qa/autodownload.html")
    finally:
        visitor.close()
        await browser.close_tab(tab)
    await asyncio.sleep(1)
    assert not downloads.exists() or not list(downloads.iterdir())
    assert [(i.severity, i.kind) for i in page_issues(page, base.rstrip("/"))] == [("low", "starts a download")]


@CHROME
async def test_a_page_that_moves_on_by_script_keeps_its_findings(chrome_browser):
    from ai_browser.qa.page import PageVisitor, page_issues

    browser, base, _ = chrome_browser
    tab = await browser.open_worker()
    visitor = PageVisitor(browser, tab)
    try:
        page = await visitor.visit(base + "qa/jsredirect.html")
    finally:
        visitor.close()
        await browser.close_tab(tab)
    assert not page.error
    assert "page didn't load" not in {i.kind for i in page_issues(page, base.rstrip("/"))}


def gated_checker(browser):
    from ai_browser.qa.checker import LinkChecker
    from ai_browser.qa.polite import HostGate

    return LinkChecker(browser.cdp, browser.current, HostGate(delay=0.05))


@CHROME
async def test_a_host_that_refuses_is_asked_nothing_more(chrome_browser):
    from ai_browser.qa.issues import link_verdict

    browser, base, _ = chrome_browser
    await browser.open(base + "qa/index.html")
    checker = gated_checker(browser)
    asked, real = [], checker._fetch

    async def fetch(url, credentials):
        asked.append(url)
        return await real(url, credentials)

    checker._fetch = fetch
    busy = await checker.check(base + "qa2/busy", True)
    assert busy.status == 429 and busy.retry_after == 120 and link_verdict(busy) == "unchecked"
    assert checker.gate.stopped("localhost") == ("answered 429 Too Many Requests on /qa2/busy (it asked for a "
                                                 "2-minute pause)")
    after = await checker.check(base + "qa/about.html", True)
    assert after.error == "stopped: localhost refused (429)" and link_verdict(after) == "unchecked"
    assert asked == [base + "qa2/busy"]  # nothing more went to that host
    other = base.replace("localhost", "127.0.0.1")
    assert (await checker.check(other + "qa/about.html", True)).status == 200  # other hosts go on


@CHROME
async def test_a_short_503_pause_is_waited_out_once(chrome_browser):
    browser, base, _ = chrome_browser
    await browser.open(base + "qa/index.html")
    checker = gated_checker(browser)
    started = time.monotonic()
    later = await checker.check(base + "qa2/later", True)
    assert later.status == 200 and time.monotonic() - started >= 1
    assert checker.gate.stopped("localhost") is None


@CHROME
async def test_fetch_text_reads_a_capped_body_through_the_gate(chrome_browser):
    browser, base, _ = chrome_browser
    await browser.open(base + "qa/index.html")
    result, text = await gated_checker(browser).fetch_text(base + "qa/about.html", 60)
    assert result.status == 200 and text.lower().startswith("<!doctype html>") and len(text.encode()) <= 60


from ai_browser.qa.polite import BIG_SITE_NOTE  # noqa: E402


def capture(monkeypatch):
    """(run module, dict that gets the QARun the report was written from)."""
    from ai_browser.qa import run as run_module

    captured, real = {}, run_module.write_report

    def keep(work, run):
        captured["run"] = run
        return real(work, run)

    monkeypatch.setattr(run_module, "write_report", keep)
    return run_module, captured


def record_fetches(monkeypatch) -> list[str]:
    """Every URL QA's link checks ask for."""
    from ai_browser.qa.checker import LinkChecker

    asked, real = [], LinkChecker._fetch

    async def fetch(self, url, credentials):
        asked.append(url)
        return await real(self, url, credentials)

    monkeypatch.setattr(LinkChecker, "_fetch", fetch)
    return asked


def report_html(browser, text):
    path = next(line for line in text.splitlines() if line.startswith("report: ")).split()[1]
    return browser.work.to_host(path).read_text(encoding="utf-8")


@CHROME
async def test_qa_follows_robots_txt_unless_the_user_says_the_site_is_theirs(chrome_browser, monkeypatch):
    run_module, captured = capture(monkeypatch)
    asked = record_fetches(monkeypatch)
    browser, base, _ = chrome_browser
    private = base + "qa-robots/private/x.html"
    text = await run_module.run_qa(browser, browser.work, base + "qa-robots/index.html", delay=0.05)
    run = captured["run"]
    assert (private, "not checked: robots.txt") in run.unchecked and private not in asked
    assert private not in {page.url for page in run.pages} and base + "qa-robots/public.html" in \
        {page.url for page in run.pages}
    assert "not checked: 1 page robots.txt asks crawlers to skip" in text
    text = await run_module.run_qa(browser, browser.work, base + "qa-robots/index.html", delay=0.05,
                                   ignore_robots=True)
    assert private in {page.url for page in captured["run"].pages}
    assert "robots.txt: ignored at the user's request" in text
    assert "robots.txt: ignored at the user&#x27;s request" in report_html(browser, text)


@CHROME
async def test_a_429_stops_the_crawl_and_says_how_long_to_wait(chrome_browser, monkeypatch):
    run_module, captured = capture(monkeypatch)
    browser, base, _ = chrome_browser
    stops = []
    text = await run_module.run_qa(browser, browser.work, base + "qa2/busy.html", delay=0.05,
                                   on_host_stopped=lambda host, until, why: stops.append(
                                       (host, round(until - time.time()), why)))
    run = captured["run"]
    assert (base + "qa/about.html", "not checked: localhost refused (429)") in run.unchecked
    assert text.splitlines()[0].endswith("(stopped early)")
    assert ("stopped early: localhost answered 429 Too Many Requests on /qa2/busy (it asked for a 2-minute pause), "
            "so QA stopped after 1 page") in text
    assert "not checked: 1 link on hosts that refused (localhost: 429)" in text
    assert stops == [("localhost", 120, "429, it asked for 2 minutes")]
    assert "<h3>localhost refused (429)</h3>" in report_html(browser, text)


@CHROME
async def test_a_429_from_another_site_stops_only_that_host(chrome_browser, monkeypatch):
    run_module, captured = capture(monkeypatch)
    browser, base, _ = chrome_browser
    text = await run_module.run_qa(browser, browser.work, base + "qa2/partner.html", delay=0.05)
    run = captured["run"]
    assert base + "qa/about.html" in {page.url for page in run.pages}  # the crawl of the site went on
    assert run.stopped_hosts["127.0.0.1"].startswith("answered 429") and "localhost" not in run.stopped_hosts
    assert "stopped early" not in text and run.stopped != "host stopped"


@CHROME
async def test_a_short_pause_is_waited_out_and_big_sites_are_never_asked(chrome_browser, monkeypatch):
    run_module, captured = capture(monkeypatch)
    asked = record_fetches(monkeypatch)
    browser, base, _ = chrome_browser
    text = await run_module.run_qa(browser, browser.work, base + "qa2/wait.html", delay=0.05)
    run = captured["run"]
    assert base + "qa2/later" in {page.url for page in run.pages}
    assert ("https://www.google.com/maps", BIG_SITE_NOTE) in run.unchecked
    assert not any("google.com" in url for url in asked)
    assert "not checked: 1 link to big sites (google.com)" in text


@CHROME
async def test_no_two_requests_to_one_host_overlap(chrome_browser, monkeypatch):
    import contextlib

    from ai_browser.qa import run as run_module
    from ai_browser.qa.page import PageVisitor
    from ai_browser.qa.polite import HostGate

    spans, navigations = [], []

    class Recording(HostGate):
        @contextlib.asynccontextmanager
        async def turn(self, host):
            async with super().turn(host):
                began = time.monotonic()
                try:
                    yield
                finally:
                    spans.append((host, began, time.monotonic()))

    real_send = PageVisitor._send

    async def send(self, method, params=None, timeout=30):
        if method == "Page.navigate":  # a page visit's own request
            navigations.append(time.monotonic())
        return await real_send(self, method, params, timeout)

    monkeypatch.setattr(run_module, "HostGate", Recording)
    monkeypatch.setattr(PageVisitor, "_send", send)
    browser, base, _ = chrome_browser
    await run_module.run_qa(browser, browser.work, base + "qa/index.html", max_pages=3, delay=0.05)
    for host in {host for host, _, _ in spans}:
        mine = sorted((began, ended) for name, began, ended in spans if name == host)
        assert all(later[0] >= earlier[1] for earlier, later in zip(mine, mine[1:])), host
    local = sorted((began, ended) for name, began, ended in spans if name == "localhost")
    assert len(navigations) >= 3 and local[0][1] <= navigations[0]  # robots.txt is read before the start page
    assert all(any(began <= at <= ended for began, ended in local) for at in navigations)  # each visit holds a turn


async def test_qa_never_crawls_a_big_site():
    import contextlib

    from ai_browser.browser import BrowserError
    from ai_browser.qa import run_qa

    class Stub:
        mode, owned = "sandbox", {}

        def acting(self):
            return contextlib.nullcontext()

    with pytest.raises(BrowserError, match="www.youtube.com is a big site"):
        await run_qa(Stub(), None, "https://www.youtube.com/@someone")


@CHROME
async def test_a_bot_check_found_by_qa_is_handed_over_in_its_own_tab(chrome_browser, monkeypatch):
    from ai_browser.checks import Check
    from ai_browser.render import render_check

    run_module, captured = capture(monkeypatch)
    asked = record_fetches(monkeypatch)
    browser, base, _ = chrome_browser
    before = set(browser.owned)
    calls = []

    async def on_check(tab, check):
        calls.append((tab, check))
        return None  # the run writes the plain hand-off itself

    text = await run_module.run_qa(browser, browser.work, base + "qa2/check.html", delay=0.05, on_check=on_check)
    [(tab, check)] = calls
    assert check == Check("traffic", "localhost")
    assert set(browser.owned) == before | {tab.key}  # the check's tab stays open; QA's other tabs closed
    assert text.startswith(render_check(check, tab.key) + "\n\nqa ")
    assert "stopped early: localhost answered with a bot check on /checks/unusual.html" in text
    assert ("https://www.google.com/maps", BIG_SITE_NOTE) in captured["run"].unchecked
    assert not any("google.com" in url for url in asked)
    await browser.close_tab(tab)

    async def engine_hold(tab, check):
        return "HELD BY THE ENGINE"

    text = await run_module.run_qa(browser, browser.work, base + "qa2/check.html", delay=0.05, on_check=engine_hold)
    assert text.startswith("HELD BY THE ENGINE\n\nqa ")


@CHROME
async def test_in_the_users_own_browser_the_check_tab_gets_the_real_window_back(chrome_browser):
    from ai_browser.qa import run_qa

    browser, base, _ = chrome_browser
    await browser.open(base + "checks/counter.html")
    real = await browser._eval("[innerWidth, innerHeight, devicePixelRatio]")
    assert real[:2] != [1440, 900]  # QA's own size, so the two can be told apart
    seen = []

    async def on_check(tab, check):  # what the user gets to solve the check in
        seen.append(await browser.eval_in(tab, "[innerWidth, innerHeight, devicePixelRatio]"))
        return None

    await run_qa(browser, browser.work, base + "qa2/check.html", delay=0.05, on_check=on_check)
    assert seen == [real]
