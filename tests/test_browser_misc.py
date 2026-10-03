import csv
import json

import pytest

from ai_browser import testpages
from ai_browser.browser import Browser, BrowserError, JSError
from ai_browser.cdp import CDP
from ai_browser.config import Config
from ai_browser.workfs import WorkDir

pytestmark = pytest.mark.docker


@pytest.fixture(scope="session")
async def env(sandbox):
    boxes, info = sandbox
    base, _ = testpages.serve(boxes, info)
    cdp = await CDP.connect(boxes.ws_url(info))
    browser = Browser(cdp, WorkDir(info.work_host, "pytest-misc"), Config())
    await browser.start()
    yield browser, base
    await browser.close()
    await cdp.close()


def jpeg_size(data: bytes) -> tuple[int, int]:
    i = 2
    while i < len(data):
        marker, length = data[i + 1], int.from_bytes(data[i + 2:i + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2):
            return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
        i += 2 + length
    raise AssertionError("not a JPEG")


async def test_desktop_screenshot_is_a_small_jpeg(env):
    browser, base = env
    await browser.open(base + "report.html")
    [shot] = await browser.screenshot()
    assert shot.label == "desktop"
    assert shot.data[:2] == b"\xff\xd8"
    assert jpeg_size(shot.data) == (shot.width, shot.height)
    assert shot.width <= 1280


async def test_all_sizes_then_back_to_desktop(env):
    browser, base = env
    await browser.open(base + "report.html")
    shots = await browser.screenshot("all")
    assert [shot.label for shot in shots] == ["desktop", "tablet", "mobile"]
    assert jpeg_size(shots[2].data)[0] == 390
    state = await browser.state()
    assert state["w"] == 1440
    assert "Desktop layout" in state["text"]


async def test_full_page_is_taller_than_the_viewport(env):
    browser, base = env
    await browser.open(base + "long.html")
    [viewport] = await browser.screenshot()
    [full] = await browser.screenshot(full_page=True)
    assert full.height > viewport.height * 3


async def test_element_screenshot_is_cropped_to_the_element(env):
    browser, base = env
    await browser.open(base + "form.html")
    submit = next(row["id"] for row in (await browser.state())["rows"] if row["name"] == "Submit order")
    [shot] = await browser.screenshot(element=submit)
    width, height = await browser._eval(
        "[document.getElementById('submit').getBoundingClientRect().width,"
        " document.getElementById('submit').getBoundingClientRect().height]")
    assert abs(shot.width - width) <= 2 and abs(shot.height - height) <= 2


async def test_unknown_size_is_an_error(env):
    browser, base = env
    with pytest.raises(BrowserError, match="desktop, tablet, mobile or all"):
        await browser.screenshot("huge")


async def test_page_log_reports_errors_then_clears(env):
    browser, base = env
    await browser.page_log()  # drop anything from earlier tests
    await browser.open(base + "errors.html")
    await browser._eval("new Promise((resolve) => setTimeout(resolve, 100))", await_promise=True)
    log = await browser.page_log()
    assert "boom error" in log
    assert "careful now" in log
    assert "uncaught kaboom" in log
    assert "404" in log and "missing.png" in log
    assert "nothing new" in await browser.page_log()


async def test_extract_links_writes_json(env):
    browser, base = env
    await browser.open(base + "report.html")
    out = await browser.extract("links")
    assert "Privacy policy → http://localhost:8000/privacy.html" in out
    links = json.loads(browser.work.to_host("links.json").read_text(encoding="utf-8"))
    assert {"text": "External about", "href": "https://example.org/about"} in links


async def test_extract_tables_writes_csv(env):
    browser, base = env
    await browser.open(base + "report.html")
    out = await browser.extract("tables")
    assert "table-1.csv" in out and "Fruit prices" in out
    with open(browser.work.to_host("table-1.csv"), newline="", encoding="utf-8") as handle:
        assert list(csv.reader(handle)) == [["Name", "Price"], ["Apple", "1.00"], ["Banana, ripe", "0.50"]]


async def test_extract_saves_everything_and_says_so(env):
    browser, base = env
    await browser.open(base + "bigdata.html")
    links_out = await browser.extract("links")
    assert links_out.startswith("1200 links")
    assert len(json.loads(browser.work.to_host("links.json").read_text(encoding="utf-8"))) == 1200
    tables_out = await browser.extract("tables")
    assert "701 rows" in tables_out
    with open(browser.work.to_host("table-1.csv"), newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert len(rows) == 701


async def test_extract_meta(env):
    browser, base = env
    await browser.open(base + "report.html")
    out = await browser.extract("meta")
    assert "description: A page for testing extraction." in out
    assert "canonical: https://example.com/report" in out
    assert "og:title: Report OG title" in out
    assert "h1 Quarterly report" in out
    assert "images without alt: 1 of 1" in out


async def test_extract_unknown_kind(env):
    browser, _ = env
    with pytest.raises(BrowserError, match="links, tables or meta"):
        await browser.extract("everything")


async def test_js_values_returns_and_errors(env):
    browser, base = env
    await browser.open(base + "report.html")
    assert await browser.js("1 + 2") == "3"
    assert await browser.js("return document.title") == '"Report test"'
    assert await browser.js("await new Promise((r) => setTimeout(() => r({a: 1}), 10))") == '{"a": 1}'
    assert await browser.js("undefined") == "undefined"
    with pytest.raises(JSError, match="nope"):
        await browser.js("throw new Error('nope')")


async def test_link_opening_a_new_tab_is_followed(env):
    from ai_browser.steps import parse_steps

    browser, base = env
    await browser.open(base + "popup.html")
    link = next(row["id"] for row in (await browser.state())["rows"] if row["name"] == "Preview in new tab")
    out = await browser.act(parse_steps([f"click {link}"]))
    assert "new tab" in out.splitlines()[0]
    assert 'page  "Privacy"' in out
    listing = await browser.tabs("list")
    assert listing.count("\n") >= 1 and "* t" in listing and "privacy.html" in listing
    await browser.tabs("close", browser.current.key)


async def test_window_open_popup_is_followed(env):
    from ai_browser.steps import parse_steps

    browser, base = env
    await browser.open(base + "popup.html")
    button = next(row["id"] for row in (await browser.state())["rows"] if row["name"] == "Sign in with popup")
    out = await browser.act(parse_steps([f"click {button}"]))
    assert "new tab" in out.splitlines()[0]
    assert 'page  "Form test"' in out
    await browser.tabs("close", browser.current.key)


async def test_tabs_new_list_switch_close(env):
    browser, base = env
    await browser.open(base + "form.html")
    out = await browser.tabs("new", url=base + "privacy.html")
    assert 'page  "Privacy"' in out
    new = browser.current.key
    listing = await browser.tabs("list")
    assert "t1" in listing and f"* {new}" in listing
    assert 'page  "Form test"' in await browser.tabs("switch", "t1")
    assert new not in await browser.tabs("close", new)
    with pytest.raises(BrowserError, match="no tab t9"):
        await browser.tabs("switch", "t9")
