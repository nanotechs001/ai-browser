"""The app's own view of AI Browser's tabs: the tab list, Watch, closing an agent's tabs, thumbnails."""

import asyncio

import pytest

from ai_browser.chrome import chrome_binary
from test_appmode import front_url, settled

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


@pytest.fixture
async def app_browser(tmp_path):
    from ai_browser import testpages
    from ai_browser.appbrowser import launch_app_browser, prepare_extension

    app = launch_app_browser(tmp_path / "profile", prepare_extension(tmp_path, "http://127.0.0.1:1", "t"),
                             headless=True)
    await settled(app)
    base, _, stop = testpages.serve_host()
    yield app, base
    stop()
    app.close()


async def until(check, seconds=5):
    for _ in range(int(seconds * 10)):
        if check():
            return True
        await asyncio.sleep(0.1)
    return False


@CHROME
async def test_the_tab_list_follows_chrome_and_leaves_out_our_pages(app_browser):
    from ai_browser.app.tabs import TabWatch
    from ai_browser.cdp import CDP

    app, base = app_browser
    watch = TabWatch(app.ws_url, app.extension_id)
    changes = []
    watch.on_change(changes.append)
    await watch.start()
    cdp = await CDP.connect(app.ws_url)
    try:
        page = (await cdp.send("Target.createTarget", {"url": base + "privacy.html"}))["targetId"]
        await cdp.send("Target.createTarget", {"url": f"chrome-extension://{app.extension_id}/panel.html"})
        assert await until(lambda: any(t["target"] == page and t["title"] == "Privacy" for t in watch.tabs()))
        assert changes and watch.has_pages()
        assert not any(app.extension_id in tab["url"] for tab in watch.tabs())
        shot = await watch.thumbnail(page)
        assert shot and shot[:2] == b"\xff\xd8" and len(shot) < 80_000  # a small JPEG
        await watch.close_targets([page, "no-such-target"])
        assert await until(lambda: not any(tab["target"] == page for tab in watch.tabs()))
    finally:
        await cdp.close()
        await watch.close()


@CHROME
async def test_watch_brings_a_tab_to_the_front(app_browser):
    from ai_browser.app.tabs import TabWatch
    from ai_browser.cdp import CDP

    app, base = app_browser
    watch = TabWatch(app.ws_url, app.extension_id)
    await watch.start()
    cdp = await CDP.connect(app.ws_url)
    try:
        first = (await cdp.send("Target.createTarget", {"url": base + "privacy.html"}))["targetId"]
        await cdp.send("Target.createTarget", {"url": base + "form.html"})
        assert (await front_url(app, cdp)).endswith("form.html")
        await watch.watch(first)
        assert (await front_url(app, cdp)).endswith("privacy.html")
    finally:
        await cdp.close()
        await watch.close()


@CHROME
async def test_the_text_of_a_tab_for_a_skill_draft(app_browser):
    from ai_browser.app.tabs import TabWatch
    from ai_browser.cdp import CDP

    app, base = app_browser
    watch = TabWatch(app.ws_url, app.extension_id)
    await watch.start()
    cdp = await CDP.connect(app.ws_url)
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
