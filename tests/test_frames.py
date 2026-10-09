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


def test_the_engine_and_the_reader_name_the_same_check_frames():
    import re
    from pathlib import Path

    from ai_browser.checks import CHECK_FRAME

    reader = Path(testpages.__file__).with_name("reader.js").read_text(encoding="utf-8")
    assert CHECK_FRAME.pattern == re.search(r"const CHECK_FRAME = /(.+)/i;", reader).group(1)
    for url in ("https://www.google.com/recaptcha/api2/anchor?k=x&size=normal", "https://newassets.hcaptcha.com/c/",
                "https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/turnstile/if/ov2/av0/rcv0/0",
                "https://client-api.arkoselabs.com/fc/gc/?token=x", "https://funcaptcha.com/fc/api/nojs/?pkey=x",
                "http://127.0.0.1:8000/checks/recaptcha/api2/anchor?k=test&size=normal"):
        assert CHECK_FRAME.search(url), url
    assert not CHECK_FRAME.search("http://127.0.0.1:8000/frames/canvas.html")


def own_frames(tab) -> set:
    """(path, depth) of each frame of its own process the tab follows."""
    return {(urlsplit(frame.url).path, frame.depth) for frame in tab.frames.values() if frame.session != frame.host}


async def until(check, seconds=10):
    for _ in range(int(seconds * 10)):
        if check():
            return True
        await asyncio.sleep(0.1)
    return check()


@CHROME
async def test_the_canvas_and_the_frame_inside_it_are_followed(builder):
    browser, page = builder
    await browser.open(page)
    tab = browser.current
    assert await until(lambda: own_frames(tab) == {("/frames/canvas.html", 1), ("/frames/nested.html", 2)}), \
        own_frames(tab)


@CHROME
async def test_a_bot_check_frame_is_let_go_of_and_sent_nothing(builder, monkeypatch):
    browser, page = builder
    sent, attached, addresses = [], {}, {}
    send = browser.cdp.send

    async def spy(method, params=None, session_id=None, timeout=30):
        sent.append((method, session_id, params or {}))
        return await send(method, params, session_id, timeout)

    monkeypatch.setattr(browser.cdp, "send", spy)
    browser.cdp.on("Target.attachedToTarget", lambda params, sid: attached.update(
        {params["targetInfo"]["targetId"]: params["sessionId"]}))
    browser.cdp.on("Target.targetInfoChanged", lambda params, sid: addresses.update(
        {params["targetInfo"]["targetId"]: params["targetInfo"]["url"]}))
    await browser.open(page.split("frames/")[0] + "checks/form-box.html")  # a reCAPTCHA box from another site
    check = lambda: [attached[target] for target, url in addresses.items()  # noqa: E731
                     if "/recaptcha/" in url and target in attached]
    assert await until(lambda: check() and any(method == "Target.detachFromTarget" for method, _, _ in sent))
    session = check()[0]
    assert [method for method, sid, _ in sent if sid == session] == []  # nothing was ever sent to it
    assert ("Target.detachFromTarget", browser.current.session, {"sessionId": session}) in sent  # let go of at once
    assert not browser.current.frames


@CHROME
async def test_a_download_in_a_frame_needs_the_users_ok_as_the_pages_does(builder, throwaway_chrome, tmp_path):
    from ai_browser.cdp import CDP
    from ai_browser.chrome import find_ws_url

    browser, page = builder
    own = await CDP.connect(find_ws_url(throwaway_chrome, timeout=20))  # the test's own connection, not the relay
    downloads = tmp_path / "downloads"  # never the real Downloads folder, even if the cancel failed
    await own.send("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(downloads),
                                                   "eventsEnabled": True})
    try:
        await browser.open(page)
        tab = browser.current
        assert await until(lambda: ("/frames/canvas.html", 1) in own_frames(tab))
        canvas = next(frame for frame in tab.frames.values() if frame.url.endswith("/frames/canvas.html"))
        await browser.eval_in(canvas, "document.querySelector('a[href$=bigfile]').click()")  # Get the template
        out = ""
        for _ in range(50):
            out = await browser.observe()
            if "was stopped" in out:
                break
            await asyncio.sleep(0.1)
        assert "⛔ a download of setup.dmg was stopped: ask the user, then repeat with confirmed=true" in out
        await asyncio.sleep(3.5)  # longer than the whole file takes to arrive
        assert not downloads.exists() or not list(downloads.iterdir())
    finally:
        await own.close()


@CHROME
async def test_a_frame_that_goes_is_forgotten_with_the_frames_inside_it(builder):
    browser, page = builder
    await browser.open(page)
    tab = browser.current
    assert await until(lambda: len(own_frames(tab)) == 2)
    await browser._eval("document.querySelector('[name=page-builder]').remove()")
    assert await until(lambda: not own_frames(tab))
