"""TEMPORARY: what GitHub's Windows runner does, printed (run with -s). Removed once read."""

import asyncio
import json
import time

import pytest

from ai_browser.chrome import chrome_binary
from fake_brave import until as settled
from test_app_run import servers, window  # noqa: F401  (fixtures)
from test_home import stack, until  # noqa: F401  (fixtures)
from test_tab_menu import KEPT, active_is, close_key, in_frame, mouse_click, shell, view  # noqa: F401
from test_tabwatch import pages  # noqa: F401  (fixture)

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


def say(*args):
    print("DIAG", *args, flush=True)


@CHROME
async def test_diag_reduced_motion(throwaway_chrome):
    from ai_browser.cdp import CDP
    from ai_browser.chrome import find_ws_url
    from test_home import open_page

    cdp = await CDP.connect(find_ws_url(throwaway_chrome, timeout=20))
    try:
        _, js = await open_page(cdp, "data:text/html,<p>hi</p>")
        say("reduce (no switch):", await js("matchMedia('(prefers-reduced-motion: reduce)').matches"))
    finally:
        await cdp.close()


@CHROME
async def test_diag_thumbnail(pages):
    from ai_browser.app.tabs import TabWatch
    from ai_browser.cdp import CDP

    ws_url, base, app_origin = pages
    watch = TabWatch(ws_url, hidden_origin=app_origin)
    await watch.start()
    cdp = await CDP.connect(ws_url)
    try:
        page = (await cdp.send("Target.createTarget", {"url": base + "privacy.html"}))["targetId"]
        await cdp.send("Target.createTarget", {"url": app_origin + "/form.html"})
        await asyncio.sleep(1)
        for attempt in range(3):
            started = time.monotonic()
            try:
                shot = await asyncio.wait_for(watch._shot(page), 30)
                say("thumbnail", attempt, "took", round(time.monotonic() - started, 2), "bytes", len(shot))
            except BaseException as exc:  # noqa: BLE001
                say("thumbnail", attempt, "failed after", round(time.monotonic() - started, 2), repr(exc))
    finally:
        await cdp.close()
        await watch.close()


@CHROME
async def test_diag_live_focus(shell):
    from ai_browser.live import LiveView

    js, stack = shell
    live = LiveView()
    address = await live.start()
    try:
        await in_frame(js, "/home", "parent.postMessage({type: 'live', url: " + json.dumps(address)
                       + ", agent: 'a1', label: '1 · Live'}, location.origin); true")
        assert await until(js, active_is("live:a1"))
        assert await settled(lambda: len(live.viewers) == 1)
        corner = (f"(() => {{ const box = {view('live:a1')}.querySelector('iframe').getBoundingClientRect();"
                  " return [box.x + 40, box.y + 12]; })()")
        at = await js(corner)
        say("live corner", at, "viewport", await js("[innerWidth, innerHeight, devicePixelRatio]"))
        say("element there", await js(f"(() => {{ const one = document.elementFromPoint({at[0]}, {at[1]});"
                                      " return one && one.outerHTML.slice(0, 120); })()"))
        for attempt in range(3):
            await mouse_click(js, at)
            await asyncio.sleep(0.3)
            say("after click", attempt, "live has focus:", await in_frame(js, "live:a1", "document.hasFocus()"),
                "window active:", await js("document.activeElement && document.activeElement.outerHTML.slice(0, 80)"),
                "window has focus:", await js("document.hasFocus()"))
        await in_frame(js, "live:a1", KEPT)
        await close_key(js)
        await asyncio.sleep(0.5)
        say("after key: live tab there:", await js(f"{view('live:a1')} !== null"),
            "kept:", await js(f"{view('live:a1')} && 1") and await in_frame(js, "live:a1",
                                                                          "document.documentElement.dataset.kept"))
    finally:
        await live.stop()


@CHROME
async def test_diag_app_run_close(fake_claude, tmp_path, window, monkeypatch, servers):  # noqa: F811
    from ai_browser.app import run
    from ai_browser.app.server import AppServer
    from test_app_run import test_switching_or_closing_tabs_never_ends_it_and_closing_the_window_does as original

    marks = []
    stop, until_closed = AppServer.stop, run._until_closed

    async def timed_stop(self):
        marks.append(("stop starts", time.monotonic()))
        await stop(self)
        marks.append(("stop ends", time.monotonic()))

    async def timed_until(server, *args):
        async def watch():
            while server.window_count:
                await asyncio.sleep(0.05)
            marks.append(("no window socket", time.monotonic()))
        watcher = asyncio.ensure_future(watch())
        await until_closed(server, *args)
        watcher.cancel()
        marks.append(("closed", time.monotonic()))

    monkeypatch.setattr(AppServer, "stop", timed_stop)
    monkeypatch.setattr(run, "_until_closed", timed_until)
    original_close = window.close

    async def timed_close():
        marks.append(("window.close starts", time.monotonic()))
        note = await original_close()
        marks.append(("window.close ends", time.monotonic()))
        return note

    window.close = timed_close
    send = window.cdp.send

    async def timed_send(method, *args, **kwargs):
        if method == "Target.closeTarget":
            marks.append(("closeTarget", time.monotonic()))
        return await send(method, *args, **kwargs)

    window.cdp.send = timed_send
    try:
        await original(fake_claude, tmp_path, window, monkeypatch, servers)
        say("app run passed")
    except AssertionError as exc:
        say("app run failed", str(exc)[:200])
    first = marks[0][1] if marks else 0
    say("marks", [(name, round(at - first, 2)) for name, at in marks])
