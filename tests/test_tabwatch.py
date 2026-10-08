"""TabWatch, the app's view of a browser's tabs: the tab list (without AI Browser's own pages), Watch, closing an
agent's tabs, thumbnails, and a tab's text for a skill draft. A throwaway headless Chrome stands in for the browser."""

import asyncio

import pytest

from ai_browser.chrome import chrome_binary

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


@pytest.fixture
async def pages(throwaway_chrome):
    """(the throwaway Chrome's websocket, the test pages' base, another local origin standing in for the app's)."""
    from ai_browser import testpages
    from ai_browser.chrome import find_ws_url

    base, other, stop = testpages.serve_host()
    yield find_ws_url(throwaway_chrome, timeout=20), base, other.rstrip("/")
    stop()


async def until(check, seconds=5):
    for _ in range(int(seconds * 10)):
        if check():
            return True
        await asyncio.sleep(0.1)
    return False


def test_the_rows_leave_out_the_apps_origin_and_new_tab_pages():
    from ai_browser.app.tabs import TabWatch

    watch = TabWatch("ws://127.0.0.1:1/unused", hidden_origin="http://127.0.0.1:8792")
    for target, url in (("U1", "https://mail.example/"), ("W1", "http://127.0.0.1:8792/home"),
                        ("W2", "http://127.0.0.1:8792/open?code=x"), ("N1", "chrome://newtab/"),
                        ("P1", "http://127.0.0.1:87921/x"), ("O1", "http://127.0.0.1:8793/home")):
        watch._pages[target] = {"target": target, "url": url, "title": target}
    assert [tab["target"] for tab in watch.tabs()] == ["U1", "P1", "O1"]  # another port is another origin
    assert watch.hidden_origin == "http://127.0.0.1:8792"
    assert [tab["target"] for tab in TabWatch("ws://127.0.0.1:1/unused").tabs()] == []


@CHROME
async def test_the_tab_list_follows_chrome_and_leaves_out_the_apps_pages(pages, patient_thumbnails):
    from ai_browser.app.tabs import TabWatch
    from ai_browser.cdp import CDP

    ws_url, base, app_origin = pages
    watch = TabWatch(ws_url, hidden_origin=app_origin)
    changes = []
    watch.on_change(changes.append)
    await watch.start()
    cdp = await CDP.connect(ws_url)
    try:
        page = (await cdp.send("Target.createTarget", {"url": base + "privacy.html"}))["targetId"]
        ours = (await cdp.send("Target.createTarget", {"url": app_origin + "/form.html"}))["targetId"]
        assert await until(lambda: any(t["target"] == page and t["title"] == "Privacy" for t in watch.tabs()))
        await asyncio.sleep(0.5)
        assert changes and not any(tab["target"] == ours for tab in watch.tabs())  # a 403 page in Brave isn't a tab
        shot = await watch.thumbnail(page)
        assert shot and shot[:2] == b"\xff\xd8" and len(shot) < 80_000  # a small JPEG
        await watch.close_targets([page, "no-such-target"])
        assert await until(lambda: not any(tab["target"] == page for tab in watch.tabs()))
    finally:
        await cdp.close()
        await watch.close()


@CHROME
async def test_watch_asks_chrome_to_bring_the_tab_forward(pages, monkeypatch):
    from ai_browser.app.tabs import TabWatch
    from ai_browser.cdp import CDP

    ws_url, base, _ = pages
    watch = TabWatch(ws_url)
    await watch.start()
    cdp = await CDP.connect(ws_url)
    sent, original = [], CDP.send

    async def spy(self, method, params=None, *args, **kwargs):
        sent.append((method, params))
        return await original(self, method, params, *args, **kwargs)

    try:
        first = (await cdp.send("Target.createTarget", {"url": base + "privacy.html"}))["targetId"]
        monkeypatch.setattr(CDP, "send", spy)
        await watch.watch(first)
        assert ("Target.activateTarget", {"targetId": first}) in sent
    finally:
        monkeypatch.undo()
        await cdp.close()
        await watch.close()


@CHROME
async def test_the_text_of_a_tab_for_a_skill_draft(pages):
    from ai_browser.app.tabs import TabWatch
    from ai_browser.cdp import CDP

    ws_url, base, _ = pages
    watch = TabWatch(ws_url)
    await watch.start()
    cdp = await CDP.connect(ws_url)
    try:
        page = (await cdp.send("Target.createTarget", {"url": base + "brain/orders.html"}))["targetId"]
        for _ in range(50):
            text = await watch.page_text(page)
            if "#1001" in text:
                break
            await asyncio.sleep(0.1)
        assert "Orders" in text and "#1001" in text
        assert await watch.page_text("no-such-target") == ""
    finally:
        await cdp.close()
        await watch.close()


async def test_contexts_and_the_default_on_a_fake_port(tmp_path):
    from ai_browser.app.tabs import TabWatch
    from ai_browser.chrome import find_ws_url
    from fake_brave import FakePort

    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    page = {"target": "U1", "url": "https://mail.example/", "title": "Mail", "context": "W"}
    worker = {"target": "SW1", "url": "chrome-extension://abc/worker.js", "context": "W"}
    port = FakePort(folder, pages=[page], workers=[worker], default="P")
    await port.start()
    watch = TabWatch(find_ws_url(folder), "")
    changes = []
    watch.on_change(changes.append)
    await watch.start()
    try:
        assert await until(lambda: watch.pages() == [page])
        assert watch.tabs() == [{"target": "U1", "url": "https://mail.example/", "title": "Mail"}]
        assert watch.default_context == "P"
        port.set_default("C2")  # the user used another profile last
        assert await until(lambda: watch.default_context == "C2")
        port.set_default(None)  # a failed read keeps the last value
        await asyncio.sleep(2)
        assert watch.default_context == "C2"
        await port.destroy("U1")
        assert await until(lambda: watch.pages() == [])
        assert watch.tabs() == []  # a service worker is never a page
    finally:
        await watch.close()
        await port.stop()


@CHROME
async def test_pages_carry_their_context(pages):
    from ai_browser.app.tabs import TabWatch
    from ai_browser.cdp import CDP

    ws_url, base, _ = pages
    watch = TabWatch(ws_url)
    await watch.start()
    cdp = await CDP.connect(ws_url)
    try:
        page = (await cdp.send("Target.createTarget", {"url": base + "privacy.html"}))["targetId"]
        assert await until(lambda: any(row["target"] == page for row in watch.pages()))
        contexts = {row["context"] for row in watch.pages()}
        assert len(contexts) == 1 and "" not in contexts  # one profile, one context
        assert watch.default_context in contexts
        assert all(set(tab) == {"target", "url", "title"} for tab in watch.tabs())
    finally:
        await cdp.close()
        await watch.close()
