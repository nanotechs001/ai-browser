"""Frames from another site (the frames spec): a fake page builder whose canvas is a frame from another site, drawn at
three quarters of its size, in a throwaway headless Chrome (never the user's Brave). The Browser reads and drives it
directly and through the app's relay (conftest's RELAYED_MODULES), as a Claude Code session and the app's agents do."""

import asyncio
from urllib.parse import urlsplit

import pytest

from ai_browser import testpages
from ai_browser.browser import Browser
from ai_browser.chrome import chrome_binary
from ai_browser.config import Config
from ai_browser.workfs import WorkDir
from conftest import browser_connection

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


@pytest.fixture
async def builder(throwaway_chrome, tmp_path, route):
    """(a started Browser in chrome mode, direct or through the app's relay; the fake builder's address). The builder is
    on localhost, its canvas on 127.0.0.1 (another site), its side frame on the test pages' second port."""
    base, other, stop_pages = testpages.serve_host()
    async with browser_connection(throwaway_chrome, route, tmp_path / "relay-home") as cdp:
        browser = Browser(cdp, WorkDir(tmp_path / "work", "frames"), Config(), mode="chrome")
        await browser.start()
        try:
            yield browser, f"{base}frames/builder.html?other={urlsplit(other).port}"
        finally:
            await browser.close()
    stop_pages()


@CHROME
@pytest.mark.direct_only  # the test pages themselves, in Chrome's own target list
async def test_the_canvas_runs_in_a_process_of_its_own(builder):
    browser, page = builder
    await browser.open(page)
    frames = set()
    for _ in range(50):
        infos = (await browser.cdp.send("Target.getTargets"))["targetInfos"]
        frames = {urlsplit(info["url"]).path for info in infos if info["type"] == "iframe"}
        if len(frames) >= 2:
            break
        await asyncio.sleep(0.1)
    # The canvas and the frame inside it are each a target of their own, as GoHighLevel's builder is. The side frame
    # (the same site, another port) runs in the page's process: no target.
    assert frames == {"/frames/canvas.html", "/frames/nested.html"}
