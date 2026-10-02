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

    browser, base, _ = chrome_browser
    await browser.open(base + "qa/index.html")
    other = base.replace("localhost", "127.0.0.1")
    checker = LinkChecker(browser.cdp, browser.current)
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

    browser, base, _ = chrome_browser
    site = base.rstrip("/")
    tab = await browser.open_worker()
    visitor = PageVisitor(browser, tab)
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

    browser, base, _ = chrome_browser
    tab = await browser.open_worker()
    visitor = PageVisitor(browser, tab)
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
    text = await run_module.run_qa(browser, browser.work, base + "qa/index.html", progress=note)
    took = time.monotonic() - started
    run = captured["run"]
    matches(run.issues, EXPECTED)
    assert [url for url, _ in run.unchecked] == [base.replace("localhost", "127.0.0.1") + "qa/forbidden"]
    assert run.not_followed == [base + "qa/logout.html", base + "qa/account/exit"]
    opened = {page.final_url for page in run.pages}
    assert base + "qa/files/brochure.zip" not in opened and base + "qa/attachment" not in opened
    assert base + "qa/logout.html" not in opened and len(run.pages) == 6
    assert progress == list(range(1, 7)) and took < 20
    assert browser.current is working and set(browser.owned) == before
    assert text.splitlines()[1].startswith("issues: 3 high · 3 medium · 1 low")
    assert saved_before_report == [6]  # every page's screenshots were on disk before the report was written
    html = browser.work.to_host(next(line for line in text.splitlines() if line.startswith("report: "))
                                .split()[1]).read_text()
    assert "products.html" in html


@CHROME
async def test_qa_run_respects_max_pages(chrome_browser):
    from ai_browser.qa import run_qa

    browser, base, _ = chrome_browser
    text = await run_qa(browser, browser.work, base + "qa/index.html", max_pages=2)
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

    browser, base, _ = chrome_browser
    await browser.open(base + "qa/index.html")
    result = await LinkChecker(browser.cdp, browser.current, timeout=1.0).check(base + "qa/flaky", True)
    assert result.status == 200 and result.error is None


@CHROME
async def test_links_are_checked_while_pages_are_visited(chrome_browser, monkeypatch):
    from ai_browser.qa import run as run_module

    browser, base, _ = chrome_browser
    captured = {}
    real_write = run_module.write_report

    def keep(work, run):
        captured["run"] = run
        return real_write(work, run)

    monkeypatch.setattr(run_module, "write_report", keep)
    await run_module.run_qa(browser, browser.work, base + "qa/index.html", link_budget=0)
    run = captured["run"]  # no time after the crawl: the links must have been checked during it
    assert any(i.kind == "broken link (external)" for i in run.issues)
    assert [why for _, why in run.unchecked] == ["403"]



@CHROME
async def test_a_cancelled_run_closes_its_tabs(chrome_browser):
    import anyio

    from ai_browser.qa import run_qa

    browser, base, _ = chrome_browser
    working, before = browser.current, set(browser.owned)
    with anyio.move_on_after(1.0):  # how the MCP server cancels a tool call the user interrupted
        await run_qa(browser, browser.work, base + "qa/index.html")
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

