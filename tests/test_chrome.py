import asyncio
import os
import socket
from pathlib import Path

import pytest

from ai_browser.cdp import CDP, CDPError
from ai_browser.chrome import ChromeError, chrome_binary, default_chrome_dir, find_ws_url, launch

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
REAL_CHROME = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_tests_never_reach_the_real_chrome():
    # AIB_BROWSER=chrome or the default folder would make the user's own Chrome ask "Allow remote debugging?"
    assert "AIB_BROWSER" not in os.environ
    assert default_chrome_dir() != REAL_CHROME


def test_missing_folder_explains_the_fix(tmp_path):
    with pytest.raises(ChromeError, match="chrome://inspect/#remote-debugging"):
        find_ws_url(tmp_path / "nope")


def test_missing_port_file_explains_the_fix(tmp_path):
    with pytest.raises(ChromeError, match="chrome://inspect/#remote-debugging"):
        find_ws_url(tmp_path)


def test_stale_port_file_says_chrome_is_not_running(tmp_path):
    (tmp_path / "DevToolsActivePort").write_text(f"{free_port()}\n/devtools/browser/abc\n")
    with pytest.raises(ChromeError, match="isn't running"):
        find_ws_url(tmp_path)


def test_a_port_file_removed_while_reading_counts_as_missing(tmp_path, monkeypatch):
    (tmp_path / "DevToolsActivePort").write_text("1\n/devtools/browser/abc\n")

    def removed(self, *args, **kwargs):
        raise FileNotFoundError(str(self))

    monkeypatch.setattr(Path, "read_text", removed)  # Chrome deleted it between the check and the read
    with pytest.raises(ChromeError, match="chrome://inspect/#remote-debugging"):
        find_ws_url(tmp_path)


# ---- which pages each browser may open ---------------------------------------------------------------------

WEB_PAGES = ["https://example.com", "http://localhost:8080/wp-admin/", "about:blank", "data:text/html,<p>hi</p>"]


@pytest.mark.parametrize("url", WEB_PAGES)
def test_web_pages_open_in_both_browsers(url):
    from ai_browser.browser import url_problem

    assert url_problem(url, "chrome") is None and url_problem(url, "sandbox") is None


@pytest.mark.parametrize("url", ["file:///Users/me/.ssh/id_rsa", "FILE:///etc/hosts", " file:///etc/hosts",
                                 "file:///work/t/report.html", "chrome://settings", "chrome://history",
                                 "view-source:https://example.com", "javascript:alert(1)", "about:settings",
                                 "chrome-extension://abc/page.html", "devtools://devtools/bundled/inspector.html"])
def test_the_users_chrome_opens_only_web_pages(url):
    from ai_browser.browser import url_problem

    assert url_problem(url, "chrome")


@pytest.mark.parametrize("url", ["file:///work/t/report.html", "file:///work/shared.txt",
                                 "file://localhost/work/t/a.html"])
def test_the_sandbox_opens_files_it_shares_with_the_shell(url):
    from ai_browser.browser import url_problem

    assert url_problem(url, "sandbox") is None


@pytest.mark.parametrize("url", ["file:///profile/Default/Cookies", "file:///work/../profile/Default/Cookies",
                                 "file:///work/%2e%2e/profile/Default/Cookies", "file:///work\\..\\profile\\x",
                                 "file:///etc/passwd", "file:///workx/a", "file://elsewhere/work/a",
                                 "chrome://settings"])
def test_the_sandbox_never_opens_its_own_profile(url):
    from ai_browser.browser import url_problem

    assert url_problem(url, "sandbox")


# ---- a throwaway Chrome stands in for the user's own (fixtures in conftest.py) --------------------------------


@CHROME
async def test_chrome_mode_reads_and_acts(chrome_browser):
    from ai_browser.steps import parse_steps

    browser, base, _ = chrome_browser
    page = await browser.open(base + "form.html")
    assert 'page  "Form test"' in page
    increment = next(line.split()[0] for line in page.splitlines() if '"Increment"' in line)
    assert (await browser.act(parse_steps([f"click {increment}"]))).startswith("✓ click")
    assert await browser._eval("document.getElementById('count').textContent") == "1"


@CHROME
async def test_chrome_mode_leaves_the_users_tabs_alone(chrome_browser):
    browser, base, before = chrome_browser
    await browser.open(base + "privacy.html")
    listing = await browser.tabs("list")
    assert listing.count("\n") == 0  # only the tab this session opened
    ours = set(browser.owned_targets())
    assert not ours & before
    await browser.close()
    after = {t["targetId"] for t in (await browser.cdp.send("Target.getTargets"))["targetInfos"]
             if t["type"] == "page"}
    assert before <= after and not ours & after


@CHROME
async def test_background_tabs_keep_full_speed(chrome_browser):
    browser, base, _ = chrome_browser
    await browser.open(base + "form.html")
    # Measured in a visible Chrome, even minimized: with focus emulation our background tab stays visible and a
    # click step takes ~20 ms; without it the tab is hidden, frames stop and timers run once a second (6 s a click).
    assert await browser._eval("document.hasFocus()") is True
    plain = (await browser.cdp.send("Target.createTarget", {"url": "about:blank", "background": True}))["targetId"]
    session = (await browser.cdp.send("Target.attachToTarget", {"targetId": plain, "flatten": True}))["sessionId"]
    focus = await browser.cdp.send("Runtime.evaluate", {"expression": "document.hasFocus()", "returnByValue": True},
                                   session_id=session)
    await browser.cdp.send("Target.closeTarget", {"targetId": plain})
    assert focus["result"]["value"] is False  # the check above tells the two apart


@CHROME
async def test_chrome_mode_keeps_the_real_window_size(chrome_browser):
    browser, base, _ = chrome_browser
    await browser.open(base + "report.html")
    size = await browser._eval("[innerWidth, innerHeight]")
    assert size[1] != 900  # no fixed 1440×900 override in the user's Chrome
    await browser.screenshot("all")
    assert await browser._eval("[innerWidth, innerHeight]") == size


@CHROME
async def test_chrome_mode_uploads_from_host_paths(chrome_browser):
    from ai_browser.steps import parse_steps

    browser, base, _ = chrome_browser
    browser.work.to_host("logo.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    page = await browser.open(base + "upload.html")
    chooser = next(line.split()[0] for line in page.splitlines() if '"Choose image"' in line)
    await browser.act(parse_steps([f"upload {chooser} logo.png"]))
    assert await browser._eval("document.getElementById('names').textContent") == "logo.png"


@CHROME
async def test_chrome_mode_uploads_a_copy_the_sandbox_cannot_swap(chrome_browser, tmp_path):
    from ai_browser.steps import parse_steps

    browser, base, _ = chrome_browser
    logo = browser.work.to_host("logo.png")
    logo.write_bytes(b"real image bytes")
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET")
    page = await browser.open(base + "upload.html")
    chooser = next(line.split()[0] for line in page.splitlines() if '"Choose image"' in line)
    assert (await browser.act(parse_steps([f"upload {chooser} logo.png"]))).startswith("✓ upload")
    logo.unlink()
    logo.symlink_to(secret)  # what a process in the sandboxed shell could do once the upload was checked
    read = "document.getElementById('file').files[0].text()"
    assert await browser._eval(read, await_promise=True) == "real image bytes"
    staged = list((browser.work.host_root.parent / "uploads").rglob("logo.png"))
    assert staged and not any(path.is_relative_to(browser.work.host_root) for path in staged)
    await browser.close()
    assert not browser.work.staging.exists()  # the copies go when the session's tabs close


@CHROME
async def test_chrome_mode_refuses_local_files_and_browser_pages(chrome_browser):
    from ai_browser.browser import BrowserError
    from ai_browser.steps import parse_steps

    browser, base, _ = chrome_browser
    for url in ("file:///etc/hosts", "chrome://settings"):
        with pytest.raises(BrowserError, match="only web pages"):
            await browser.open(url)
    tabs = dict(browser.owned)
    with pytest.raises(BrowserError, match="only web pages"):
        await browser.tabs("new", url="file:///etc/hosts")
    assert browser.owned == tabs  # no blank tab left behind
    await browser.open(base + "form.html")
    out = await browser.act(parse_steps(["goto file:///etc/hosts"]))
    assert out.startswith("✗ error goto file:///etc/hosts") and "only web pages" in out
    assert await browser._eval("location.href") == base + "form.html"


@CHROME
async def test_a_tab_that_fails_to_set_up_is_closed_again(chrome_browser, monkeypatch):
    from ai_browser.browser import Browser

    browser, _, _ = chrome_browser

    async def pages():
        infos = (await browser.cdp.send("Target.getTargets"))["targetInfos"]
        return {info["targetId"] for info in infos if info["type"] == "page"}

    before = await pages()

    async def broken(self, target):
        raise CDPError("setup failed")

    monkeypatch.setattr(Browser, "_setup_tab", broken)
    with pytest.raises(CDPError):
        await browser.tabs("new")
    await asyncio.sleep(0.2)
    assert await pages() == before


# ---- the engine in the user's own Chrome ---------------------------------------------------------------------


async def wait_closed(engine) -> None:
    for _ in range(50):
        if engine.cdp.closed:
            return
        await asyncio.sleep(0.1)


@CHROME
async def test_engine_drives_the_users_chrome(chrome_engine):
    engine, base, _ = chrome_engine
    started = await engine.sandbox_start(chrome=True)
    assert "your own Chrome" in started.text
    assert f"work folder /work/{engine.task_id}" in started.text  # the path read_file and upload take
    opened = await engine.open(base + "form.html")
    assert 'page  "Form test"' in opened.text
    increment = next(line.split()[0] for line in opened.text.splitlines() if '"Increment"' in line)
    assert (await engine.act([f"click {increment}"])).text.startswith("✓ click")


@CHROME
async def test_aib_browser_chrome_makes_it_the_default(chrome_engine, monkeypatch):
    engine, base, _ = chrome_engine
    monkeypatch.setenv("AIB_BROWSER", "chrome")
    from ai_browser.engine import Engine
    from ai_browser.skills import Catalog

    other = Engine(home=engine.home, default_profile="pytest-chrome", catalog=Catalog([], set()))
    try:
        opened = await other.open(base + "privacy.html")  # no sandbox_start: the default is the user's Chrome
        assert 'page  "Privacy"' in opened.text
        assert other.browser.mode == "chrome"
    finally:
        await other.close()


async def test_engine_explains_when_remote_debugging_is_off(tmp_path, monkeypatch):
    from ai_browser.engine import Engine
    from ai_browser.skills import Catalog

    monkeypatch.setenv("AIB_CHROME_DIR", str(tmp_path))
    engine = Engine(home=tmp_path / "home", default_profile="pytest-chrome", catalog=Catalog([], set()))
    result = await engine.sandbox_start(chrome=True)
    assert result.text.startswith("error: Chrome doesn't allow remote debugging yet")
    assert "chrome://inspect/#remote-debugging" in result.text


@CHROME
async def test_engine_reconnects_after_chrome_restarts(chrome_engine):
    engine, base, folder = chrome_engine
    assert "your own Chrome" in (await engine.sandbox_start(chrome=True)).text
    await engine.open(base + "form.html")
    await engine.cdp.send("Browser.close")  # relaunch the same throwaway profile on a new port after closing it
    await wait_closed(engine)
    (folder / "DevToolsActivePort").unlink(missing_ok=True)
    process = launch(folder, headless=True)
    try:
        result = await engine.open(base + "privacy.html")
        assert "reconnected to your Chrome" in result.text
        assert 'page  "Privacy"' in result.text
    finally:
        await engine.close()
        process.terminate()
        process.wait(timeout=15)


@CHROME
async def test_a_failed_reconnect_never_falls_back_to_the_sandbox(chrome_engine, monkeypatch):
    from ai_browser.engine import Engine

    engine, base, folder = chrome_engine

    async def no_sandbox(self, profile, fresh):
        raise AssertionError("fell back to the Docker sandbox")

    monkeypatch.setattr(Engine, "_start", no_sandbox)
    assert "your own Chrome" in (await engine.sandbox_start(chrome=True)).text
    await engine.open(base + "form.html")
    await engine.cdp.send("Browser.close")  # the user quits Chrome
    await wait_closed(engine)
    (folder / "DevToolsActivePort").unlink(missing_ok=True)
    for _ in range(2):  # each call explains; none quietly switches to another browser
        result = await engine.observe()
        assert result.text.startswith("error: Chrome") and "sandbox" not in result.text
    process = launch(folder, headless=True)
    try:
        find_ws_url(folder, timeout=20)
        result = await engine.open(base + "privacy.html")
        assert "reconnected to your Chrome" in result.text and 'page  "Privacy"' in result.text
    finally:
        await engine.close()
        process.terminate()
        process.wait(timeout=15)


@CHROME
async def test_a_dropped_connection_closes_the_old_tabs_on_reconnect(chrome_engine):
    engine, base, _ = chrome_engine
    assert "your own Chrome" in (await engine.sandbox_start(chrome=True)).text
    await engine.open(base + "form.html")
    old = engine.browser.current.target
    await engine.cdp.close()  # the connection drops while Chrome keeps running
    result = await engine.open(base + "privacy.html")
    assert "reconnected to your Chrome" in result.text and 'page  "Privacy"' in result.text
    targets = {info["targetId"] for info in (await engine.cdp.send("Target.getTargets"))["targetInfos"]}
    assert old not in targets


@CHROME
async def test_a_tab_closed_outside_the_session_is_replaced(chrome_engine):
    engine, base, _ = chrome_engine
    assert "your own Chrome" in (await engine.sandbox_start(chrome=True)).text
    await engine.open(base + "form.html")
    gone = engine.browser.current.target
    await engine.cdp.send("Target.closeTarget", {"targetId": gone})  # the user closes our tab
    await asyncio.sleep(0.3)
    result = await engine.open(base + "privacy.html")
    assert "was closed" in result.text and 'page  "Privacy"' in result.text
    assert gone not in engine.browser.owned_targets()


@CHROME
async def test_a_popup_that_closes_itself_hands_back_to_its_opener(chrome_engine):
    engine, base, _ = chrome_engine
    assert "your own Chrome" in (await engine.sandbox_start(chrome=True)).text
    page = (await engine.open(base + "popup.html")).text
    button = next(line.split()[0] for line in page.splitlines() if '"Sign in, then close"' in line)
    out = (await engine.act([f"click {button}"])).text
    assert 'page  "Sign in"' in out
    done = next(line.split()[0] for line in out.splitlines() if '"Done"' in line)
    clicked = (await engine.act([f"click {done}"])).text
    assert clicked.startswith("✓ click")
    if "was closed" not in clicked:  # Chrome reported the close after the step's own read: the next call says it
        await asyncio.sleep(0.3)
        clicked = (await engine.observe()).text
    assert "was closed" in clicked and 'page  "Popup test"' in clicked


@pytest.mark.docker
@CHROME
async def test_shell_still_runs_in_the_docker_sandbox(chrome_engine):
    engine, _, _ = chrome_engine
    assert "your own Chrome" in (await engine.sandbox_start(chrome=True)).text
    result = await engine.shell("whoami && (ls /profile >/dev/null 2>&1 || echo no-profile)")
    assert result.text.splitlines()[:2] == ["agent", "no-profile"]
    assert engine.info.shell == engine.sandboxes.chrome_shell()  # this home's own shell, never another home's


@pytest.mark.docker
@CHROME
async def test_the_shell_outlives_other_sessions_and_comes_back_when_stopped(chrome_engine):
    from ai_browser.engine import Engine
    from ai_browser.skills import Catalog

    engine, _, _ = chrome_engine
    assert "your own Chrome" in (await engine.sandbox_start(chrome=True)).text
    assert (await engine.shell("echo one")).text.startswith("one")
    other = Engine(home=engine.home, default_profile="pytest-chrome", catalog=Catalog([], set()))
    try:
        assert "your own Chrome" in (await other.sandbox_start(chrome=True)).text
        assert (await other.shell("echo other")).text.startswith("other")
        await other.sandbox_stop()  # another session ends: the shell they shared keeps running
        assert engine.sandboxes.is_running(engine.info.shell)
        engine.sandboxes.stop(engine.info.shell)  # e.g. `ai-browser stop --all`
        assert (await engine.shell("echo two")).text.startswith("two")
    finally:
        await other.close()


@CHROME
async def test_screenshots_stay_small_on_retina_screens(tmp_path):
    from ai_browser import testpages
    from ai_browser.browser import Browser
    from ai_browser.config import Config
    from ai_browser.workfs import WorkDir

    folder = tmp_path / "retina"
    process = launch(folder, headless=True, extra_args=("--force-device-scale-factor=2",))
    base, _, stop_pages = testpages.serve_host()
    try:
        cdp = await CDP.connect(find_ws_url(folder, timeout=20))
        browser = Browser(cdp, WorkDir(tmp_path / "work", "t"), Config(), mode="chrome")
        await browser.start()
        await browser.open(base + "report.html")
        assert await browser._eval("devicePixelRatio") == 2
        [shot] = await browser.screenshot()
        assert shot.width <= 1280
        await browser._eval("void Object.defineProperty(window, 'devicePixelRatio', {value: 'x'})")  # pages can fake it
        [shot] = await browser.screenshot()
        assert shot.width <= 1280
        await browser.close()
        await cdp.close()
    finally:
        stop_pages()
        process.terminate()
        process.wait(timeout=15)


@CHROME
async def test_a_throwaway_chrome_answers(throwaway_chrome):
    url = find_ws_url(throwaway_chrome, timeout=20)
    assert url.startswith("ws://127.0.0.1:") and "/devtools/browser/" in url
    cdp = await CDP.connect(url)
    try:
        assert "Chrome" in (await cdp.send("Browser.getVersion"))["product"]
    finally:
        await cdp.close()
