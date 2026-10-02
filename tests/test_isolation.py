"""The page reader lives in an isolated world: a page can't replace it or bend what it reads (security work)."""

import pytest

from ai_browser.chrome import chrome_binary
from ai_browser.steps import parse_steps

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


def element_of(page: str, name: str) -> str:
    return next(line.split()[0] for line in page.splitlines() if f'"{name}"' in line)


@CHROME
async def test_a_hostile_page_cannot_bend_what_the_reader_sees_or_does(chrome_browser):
    browser, base, _ = chrome_browser
    page = await browser.open(base + "checks/forge.html")
    assert '"Buy now" ⚠' in page and '"Look"' in page and "Safe button" not in page
    blocked = await browser.act(parse_steps([f"click {element_of(page, 'Buy now')}"]))
    assert blocked.startswith("⛔ blocked") and "Buy" not in await browser.js("document.getElementById('log').textContent")
    await browser.act(parse_steps([f"click {element_of(page, 'Look')}"]))
    assert await browser.js("document.getElementById('log').textContent") == '"Look clicked. "'
    browser.work.to_host("note.txt").write_text("hello", encoding="utf-8")
    await browser.act(parse_steps([f"upload {element_of(page, 'File A')} note.txt"]))
    assert await browser.js("[document.getElementById('a').files.length, "
                            "document.getElementById('b').files.length]") == "[1, 0]"


@CHROME
async def test_the_pages_own_world_has_no_reader_and_reads_survive_navigation(chrome_browser):
    browser, base, _ = chrome_browser
    await browser.open(base + "form.html")
    assert await browser.js("typeof window.__aib") == '"undefined"'
    first = await browser._reader("doc")
    browser.current.world = None  # forget the cached context: Chrome hands back the world the reader runs in
    assert await browser._reader("doc") == first
    other = base.replace("localhost", "127.0.0.1")  # another site: a new document, a new context
    page = await browser.open(other + "form.html")
    assert 'page  "Form test"' in page and other in page


@CHROME
async def test_a_react_style_select_still_sees_the_change(chrome_browser):
    browser, base, _ = chrome_browser
    page = await browser.open(base + "checks/react-select.html")
    await browser.act(parse_steps([f'select {element_of(page, "Size")} "Large"']))
    assert await browser.js("document.getElementById('state').textContent") == '"Large"'


@CHROME
async def test_qas_probe_runs_in_the_isolated_world_too(chrome_browser):
    from ai_browser.qa.page import PageVisitor

    browser, base, _ = chrome_browser
    tab = await browser.open_worker()
    visitor = PageVisitor(browser, tab)
    try:
        page = await visitor.visit(base + "qa/about.html")
        assert page.title == "About us" and not page.error
        seen = await browser.cdp.send("Runtime.evaluate", {
            "expression": "typeof window.__aibqa + ' ' + typeof window.__aib", "returnByValue": True},
            session_id=tab.session)
        assert seen["result"]["value"] == "undefined undefined"
    finally:
        visitor.close()
        await browser.close_tab(tab)
