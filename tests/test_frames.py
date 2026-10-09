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


async def read_until(browser, *names, find=None) -> dict:
    """The state once rows with all these names are read (a frame's address comes a moment after its page's)."""
    for _ in range(100):
        state = await browser.state(find)
        if all(any(row["name"] == name for row in state["rows"]) for name in names):
            return state
        await asyncio.sleep(0.1)
    raise AssertionError(f"never read {names}: {[row['name'] for row in state['rows']]}")


def row(state, name) -> dict:
    return next(row for row in state["rows"] if row["name"] == name)


def line(state, label) -> dict:
    return next(frame for frame in state["frames"] if frame["label"] == label)


@CHROME
async def test_observe_numbers_the_canvas_with_its_frames_label(builder):
    browser, page = builder
    await browser.open(page)
    state = await read_until(browser, "Add row", "Nested button", "Side button")
    assert row(state, "Add section").get("frame") is None  # the builder's own toolbar
    assert row(state, "Add row")["frame"] == "page-builder" and row(state, "Add row")["role"] == "button"
    assert row(state, "Headline")["role"] == "textbox"
    sticky = row(state, "Sticky")
    assert (sticky["role"], sticky["value"], sticky["options"], sticky["frame"]) == ("select", "Off", ["Off", "On"],
                                                                                     "page-builder")
    assert row(state, "Nested button")["frame"] == "nested"  # a frame from another site inside the canvas
    assert row(state, "Side button")["frame"] == "side"  # another origin on the same site, in the page's process
    ids = [item["id"] for item in state["rows"]]
    assert len(ids) == len(set(ids))  # one number space for the whole page
    assert all(line(state, label).get("readable") for label in ("page-builder", "nested", "side"))
    assert "Header section" in state["text"]  # the canvas's text is the page's text too (data, as any page text)
    again = await browser.state()
    assert [(item["id"], item["name"]) for item in again["rows"]] == [(item["id"], item["name"])
                                                                     for item in state["rows"]]  # ids stay put


@CHROME
async def test_find_reaches_into_frames_and_a_frame_out_of_view_waits(builder):
    browser, page = builder
    await browser.open(page)
    await read_until(browser, "Add row")
    found = await browser.state(find="Deep button")  # below the fold of the canvas's panel
    assert [(item["name"], item["frame"]) for item in found["rows"]] == [("Deep button", "page-builder")]
    await browser._eval("document.querySelector('[name=page-builder]').style.top = '5000px'")
    state = await browser.state()
    assert not [item for item in state["rows"] if item.get("frame") in ("page-builder", "nested")]
    assert line(state, "page-builder").get("readable")  # out of view: left for when it shows, never "not readable"
    assert [item["name"] for item in (await browser.state(find="Add row"))["rows"]] == ["Add row"]


@CHROME
async def test_a_frame_that_goes_mid_read_is_reported_not_crashed_on(builder, monkeypatch):
    from ai_browser.browser import Frame

    browser, page = builder
    await browser.open(page)
    await read_until(browser, "Add row", "Side button")
    reader_in = browser._reader_in

    async def removing(where, call, *args, **kwargs):
        if isinstance(where, Frame) and where.url.endswith("/frames/canvas.html") and call.startswith("observe("):
            await browser.cdp.send("Runtime.evaluate", {"expression": "document.querySelector('[name=page-builder]')"
                                                                      ".remove()"}, session_id=browser.current.session)
            await asyncio.sleep(0.3)  # gone by the time it is read
        return await reader_in(where, call, *args, **kwargs)

    monkeypatch.setattr(browser, "_reader_in", removing)
    state = await browser.state()
    assert row(state, "Add section") and row(state, "Side button")  # the rest of the page reads as before
    assert not line(state, "page-builder").get("readable")  # "(not readable)"
    assert not [item for item in state["rows"] if item.get("frame") in ("page-builder", "nested")]


@CHROME
async def test_an_editor_drawn_on_a_canvas_is_noticed(builder):
    browser, page = builder
    await browser.open(page)
    assert not (await read_until(browser, "Add row")).get("canvas")
    await browser.open(page.split("frames/")[0] + "frames/drawn.html")  # Figma's or Canva's kind, in a frame
    for _ in range(100):
        state = await browser.state()
        if state.get("canvas"):
            break
        await asyncio.sleep(0.1)
    assert state["canvas"] is True and line(state, "board").get("readable")


@CHROME
async def test_a_frame_whose_address_hasnt_come_is_not_readable_yet(builder):
    browser, page = builder
    await browser.open(page)
    await read_until(browser, "Add row")
    canvas = next(frame for frame in browser.current.frames.values() if frame.url.endswith("/frames/canvas.html"))
    address, canvas.url = canvas.url, ""  # as just after Chrome attached it: its address comes a moment later
    state = await browser.state()
    assert not line(state, "page-builder").get("readable")  # "(not readable)", never an error
    assert not [item for item in state["rows"] if item.get("frame") in ("page-builder", "nested")]
    canvas.url = address
    assert row(await browser.state(), "Add row")["frame"] == "page-builder"  # read at the next observe


@CHROME
async def test_frames_share_one_limit_and_one_time(builder, monkeypatch):
    from ai_browser import browser as browser_module

    browser, page = builder
    await browser.open(page)
    await read_until(browser, "Add row", "Nested button", "Side button")
    monkeypatch.setattr(browser_module, "MAX_FRAMES", 1)
    state = await browser.state()
    assert {item.get("frame") for item in state["rows"]} == {None, "page-builder"}  # the first frame only
    assert not line(state, "nested").get("readable") and not line(state, "side").get("readable")
    monkeypatch.setattr(browser_module, "FRAME_TIME", 0)
    state = await browser.state()
    assert {item.get("frame") for item in state["rows"]} == {None}  # out of time: the page's own rows still come


@CHROME
@pytest.mark.parametrize("counter_fails", [False, True])
async def test_a_dropped_frame_read_never_makes_two_rows_share_a_number(builder, monkeypatch, counter_fails):
    from ai_browser.browser import BrowserError, Frame

    browser, page = builder
    await browser.open(page)
    await read_until(browser, "Add row", "Side button")
    reader_in = browser._reader_in
    drop = [True]

    async def dropping(where, call, *args, **kwargs):
        if counter_fails and call == "nextId()":
            raise BrowserError("the frame is busy")  # its counter is never learned
        result = await reader_in(where, call, *args, **kwargs)
        if drop[0] and isinstance(where, Frame) and where.url.endswith("/frames/canvas.html") \
                and call.startswith("observe("):
            raise BrowserError("lost")  # the frame's reader ran (it numbered rows), but its result is dropped
        return result

    canvas = next(frame for frame in browser.current.frames.values() if frame.url.endswith("/frames/canvas.html"))
    await browser.eval_in(canvas, "for (let i = 0; i < 8; i++) { const b = document.createElement('button'); "
                                  "b.textContent = 'Fresh ' + i; document.body.prepend(b); }")
    monkeypatch.setattr(browser, "_reader_in", dropping)
    await browser.state()
    drop[0] = False
    await browser._eval("for (let i = 0; i < 8; i++) { const b = document.createElement('button'); "
                        "b.textContent = 'New ' + i; document.body.prepend(b); }")
    state = await read_until(browser, "New 7", "Add row")
    ids = [item["id"] for item in state["rows"]]
    assert len(ids) == len(set(ids))
    framed = {item["id"] for item in state["rows"] if item.get("frame")}
    assert set(browser.current.inside) == framed  # only the frame's own rows


@CHROME
async def test_a_page_row_always_beats_a_stale_frame_entry_with_its_number(builder):
    """A frame's row once numbered e72 (its read was dropped, so the entry outlived it) and the page later numbered its
    own e72: the page's row wins, and an act on it reaches the page, not the frame."""
    browser, page = builder
    await browser.open(page)
    state = await read_until(browser, "Add row", "Side button")
    tab = browser.current
    canvas = next(frame for frame in tab.frames.values() if frame.url.endswith("/frames/canvas.html"))
    mine = row(state, "Add section")["id"]
    tab.inside[mine] = canvas  # the stale entry
    await browser.state()
    assert mine not in tab.inside
    assert browser._where(mine) is tab


@CHROME
async def test_a_same_process_frame_that_moves_to_a_bot_check_is_refused_before_any_act(builder):
    from ai_browser.browser import StepBlocked

    browser, page = builder
    await browser.open(page)
    state = await read_until(browser, "Add row", "Side button")
    tab = browser.current
    side = row(state, "Side button")["id"]
    assert browser._where(side).session == tab.session  # a frame of the page's own process
    await browser._eval("document.querySelector('[name=side]').src = location.origin.replace(/:\\d+$/, ':' + "
                        "new URLSearchParams(location.search).get('other')) + '/checks/recaptcha/api2/anchor?k=x'")
    for _ in range(100):
        try:
            browser._where(side)
        except StepBlocked as stop:
            assert "bot check" in str(stop)
            return
        await asyncio.sleep(0.1)
    raise AssertionError("the side frame became a bot check and still counts as readable")


@CHROME
async def test_a_confirm_in_a_frame_is_answered_as_a_pages_is(builder):
    browser, page = builder
    await browser.open(page)
    tab = browser.current
    assert await until(lambda: ("/frames/canvas.html", 1) in own_frames(tab))
    canvas = next(frame for frame in tab.frames.values() if frame.url.endswith("/frames/canvas.html"))
    await browser.eval_in(canvas, "setTimeout(() => confirm('Sure?'), 0)")
    assert await until(lambda: tab.dialogs)
    assert tab.dialogs == [("confirm", "Sure?", False)]  # dismissed: nobody confirmed it
    assert await browser.eval_in(canvas, "1 + 1") == 2  # the frame is not frozen by it


async def act(browser, *steps, confirmed=False) -> str:
    from ai_browser.steps import parse_steps

    return await browser.act(parse_steps(list(steps)), confirmed=confirmed)


@CHROME
async def test_clicks_land_on_the_right_element_in_the_scaled_canvas(builder):
    browser, page = builder
    await browser.open(page)
    state = await read_until(browser, "Add row", "Nested button", "Side button")
    out = await act(browser, *(f"click {row(state, name)['id']}" for name in ("Add row", "Nested button",
                                                                             "Side button")))
    assert out.count("✓ click") == 3, out
    await read_until(browser, "Row added", "Nested clicked", "Side clicked")  # the canvas at 3/4, a frame in it


@CHROME
async def test_type_and_append_reach_a_field_in_the_canvas(builder):
    browser, page = builder
    await browser.open(page)
    headline = row(await read_until(browser, "Headline"), "Headline")["id"]
    out = await act(browser, f'type {headline} "Big sale"', f'append {headline} " today"')
    assert out.count("✓ ") == 2, out
    assert row(await browser.state(), "Headline")["value"] == "Big sale today"


@CHROME
async def test_select_sets_a_native_menu_in_the_canvas_as_a_pick_does(builder):
    browser, page = builder
    await browser.open(page)
    sticky = row(await read_until(browser, "Sticky"), "Sticky")["id"]
    assert (await act(browser, f'select {sticky} "On"')).startswith("✓ select"), sticky
    state = await browser.state()
    assert row(state, "Sticky")["value"] == "On"
    assert "input On; change On;" in state["text"]  # the events a person's pick fires, without the OS menu


@CHROME
async def test_check_and_upload_work_in_the_canvas(builder):
    browser, page = builder
    browser.work.to_host("hero.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    await browser.open(page)
    state = await read_until(browser, "Full width", "Background image")
    out = await act(browser, f"check {row(state, 'Full width')['id']}",
                    f"upload {row(state, 'Background image')['id']} hero.png")
    assert out.count("✓ ") == 2, out
    state = await browser.state()
    assert row(state, "Full width")["checked"] is True and "wide true; file hero.png;" in state["text"]


@CHROME
async def test_scroll_brings_an_element_below_the_panels_fold_into_view(builder):
    browser, page = builder
    await browser.open(page)
    await read_until(browser, "Add row")
    deep = row(await browser.state(find="Deep button"), "Deep button")["id"]
    assert not [item for item in (await browser.state())["rows"] if item["id"] == deep]  # not in view yet
    assert (await act(browser, f"scroll {deep}")).startswith("✓ scroll")
    assert row(await browser.state(), "Deep button")["id"] == deep  # in view now, the same number


@CHROME
async def test_a_click_out_of_view_in_the_canvas_scrolls_to_it_first(builder):
    browser, page = builder
    await browser.open(page)
    await read_until(browser, "Add row")
    deep = row(await browser.state(find="Deep button"), "Deep button")["id"]
    assert (await act(browser, f"click {deep}")).startswith("✓ click")
    await read_until(browser, "Deep clicked")


@CHROME
async def test_a_step_into_a_frame_that_became_a_bot_check_is_refused(builder):
    browser, page = builder
    await browser.open(page)
    add = row(await read_until(browser, "Add row"), "Add row")["id"]
    canvas = next(frame for frame in browser.current.frames.values() if frame.url.endswith("/frames/canvas.html"))
    check = canvas.url.replace("/frames/canvas.html", "/checks/recaptcha/api2/anchor?k=test&size=normal")
    await browser._eval(f"document.querySelector('[name=page-builder]').src = {check!r}")
    assert await until(lambda: canvas.url == check)
    out = await act(browser, f"click {add}")
    assert out.startswith(f"⛔ blocked click {add}: {add} is in a bot check box: the user ticks it, never you"), out
    state = await browser.state()
    assert not [item for item in state["rows"] if item.get("frame") == "page-builder"]  # never read
    assert line(state, "page-builder").get("box")  # [bot check box: the user ticks it]


@CHROME
async def test_a_step_below_the_pages_fold_in_a_frame_scrolls_the_page_to_it(builder):
    browser, page = builder
    await browser.open(page)
    await read_until(browser, "Add row")
    # the canvas starts 100 px above the fold: its "Full width" box (about 160 px down it) is below the fold
    await browser._eval("document.querySelector('[name=page-builder]').style.top = (innerHeight - 100) + 'px'")
    assert "Full width" not in [item["name"] for item in (await browser.state())["rows"]]
    wide = row(await browser.state(find="Full width"), "Full width")["id"]
    assert (await act(browser, f"check {wide}")).startswith("✓ check")
    assert row(await browser.state(), "Full width")["checked"] is True


@CHROME
async def test_a_row_of_a_frames_old_page_is_stale(builder):
    browser, page = builder
    await browser.open(page)
    add = row(await read_until(browser, "Add row"), "Add row")["id"]
    assert (await act(browser, f"click {add}")).startswith("✓ click")  # reached on the canvas's page
    await browser._eval("(() => { const frame = document.querySelector('[name=page-builder]');"
                        " frame.src = frame.src.replace('canvas.html', 'nested.html'); })()")  # the builder moves on
    for _ in range(100):
        state = await browser.state()
        if any(item.get("frame") == "page-builder" and item["name"] == "Nested button" for item in state["rows"]):
            break
        await asyncio.sleep(0.1)
    out = await act(browser, f"click {add}")
    assert out.startswith(f"✗ stale click {add}: {add} gone; the current page is below"), out


@CHROME
async def test_a_screenshot_of_an_element_in_a_frame_says_what_to_do(builder):
    from ai_browser.browser import BrowserError

    browser, page = builder
    await browser.open(page)
    add = row(await read_until(browser, "Add row"), "Add row")["id"]
    with pytest.raises(BrowserError, match="is in a frame from another site: take a screenshot of the page instead"):
        await browser.screenshot(element=add)


@CHROME
async def test_a_click_on_a_frame_row_under_a_page_element_is_covered_and_one_not_under_it_clicks(builder):
    browser, page = builder
    await browser.open(page)
    state = await read_until(browser, "Add row", "Nested button")
    add, nested = row(state, "Add row")["id"], row(state, "Nested button")["id"]
    await browser._eval("document.body.insertAdjacentHTML('beforeend', '<div id=cover style=\"position:fixed;left:200px;"
                        "top:80px;width:350px;height:700px;background:#fff\">cover</div>')")
    out = await act(browser, f"click {add}")
    assert out.startswith(f"✗ stale click {add}: {add} covered by div#cover"), out
    assert (await act(browser, f"click {nested}")).startswith("✓ click")
    await read_until(browser, "Nested clicked")
    assert "Row added" not in [item["name"] for item in (await browser.state())["rows"]]


@CHROME
async def test_the_frames_line_names_a_read_frame_and_a_canvas_says_so(builder):
    from ai_browser.render import CANVAS_HINT

    browser, page = builder
    await browser.open(page)
    await read_until(browser, "Add row", "Nested button", "Side button")
    out = await browser.observe()
    assert "frames: [page-builder] [side] [nested]" in out.splitlines()[1]
    assert CANVAS_HINT not in out
    await browser.open(page.split("frames/")[0] + "frames/drawn.html")  # an editor drawn on a canvas, in a frame
    for _ in range(100):
        out = await browser.observe()
        if CANVAS_HINT in out:
            break
        await asyncio.sleep(0.1)
    assert CANVAS_HINT in out and "frames: [board]" in out


def test_the_readme_says_frames_are_read_and_check_boxes_never():
    from pathlib import Path

    from ai_browser.render import BOX_TAG

    text = " ".join((Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8").split())
    assert "listed but not read" not in text
    for words in ("**Frames from other sites**", "`select` (a native menu, without opening it)", BOX_TAG,
                  "`(not readable)`", "at most 20 are read per observe, 5 deep", "more than 5 deep",
                  "has nothing to read: observe says so"):
        assert words in text, words
