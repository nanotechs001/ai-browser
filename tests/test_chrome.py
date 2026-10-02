import asyncio
import contextlib
import json
import os
import socket
from pathlib import Path

import pytest

from ai_browser.cdp import CDP, CDPError
from ai_browser.chrome import (ChromeError, chrome_binary, find_ws_url, launch, own_browser_dir,
                               own_browser_dirs)
from conftest import symlink_or_skip

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_tests_never_reach_the_real_browsers():
    # With AIB_BROWSER unset the engine would use the user's own Brave, which would ask "Allow remote debugging?"
    assert os.environ["AIB_BROWSER"] == "sandbox" and os.environ["AIB_APP_BROWSER"] == "app"
    assert own_browser_dir() not in own_browser_dirs()


@pytest.mark.parametrize("platform, parts", [
    ("darwin", ["Library/Application Support/BraveSoftware/Brave-Browser", "Library/Application Support/Google/Chrome"]),
    ("linux", [".config/BraveSoftware/Brave-Browser", ".config/google-chrome"]),
])
def test_own_browser_folders_brave_first(monkeypatch, tmp_path, platform, parts):
    from ai_browser import chrome

    monkeypatch.setattr(chrome.sys, "platform", platform)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert chrome.own_browser_dirs() == [tmp_path / part for part in parts]


def test_windows_folders_are_under_local_app_data(monkeypatch):
    from ai_browser import chrome

    monkeypatch.setattr(chrome.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", "/fake/local")
    assert chrome.own_browser_dirs() == [Path("/fake/local/BraveSoftware/Brave-Browser/User Data"),
                                         Path("/fake/local/Google/Chrome/User Data")]


def test_own_browser_dir_order(monkeypatch, tmp_path):
    from ai_browser import chrome

    brave, google = tmp_path / "brave", tmp_path / "google"
    monkeypatch.setattr(chrome, "own_browser_dirs", lambda: [brave, google])
    monkeypatch.delenv("AIB_CHROME_DIR")
    assert chrome.own_browser_dir() == brave  # none exists: the first, so an error can name it
    google.mkdir()
    assert chrome.own_browser_dir() == google  # the first that exists
    brave.mkdir()
    assert chrome.own_browser_dir() == brave
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        (google / "DevToolsActivePort").write_text(f"{listener.getsockname()[1]}\n/devtools/browser/x\n",
                                                   encoding="utf-8")
        assert chrome.switch_on(google) and not chrome.switch_on(brave)
        assert chrome.own_browser_dir() == google  # a switch that is on wins
    monkeypatch.setenv("AIB_CHROME_DIR", str(tmp_path / "set"))
    assert chrome.own_browser_dir() == tmp_path / "set"  # the setting wins over everything
    assert chrome.default_chrome_dir is chrome.own_browser_dir


def test_every_hint_names_the_browser(tmp_path):
    from ai_browser.chrome import browser_name, inspect_address

    brave = tmp_path / "BraveSoftware" / "Brave-Browser"
    brave.mkdir(parents=True)
    assert (browser_name(brave), inspect_address(brave)) == ("Brave", "brave://inspect/#remote-debugging")
    google = tmp_path / "Google" / "Chrome"
    assert (browser_name(google), inspect_address(google)) == ("Chrome", "chrome://inspect/#remote-debugging")
    with pytest.raises(ChromeError) as raised:
        find_ws_url(brave)
    text = str(raised.value)
    assert text.startswith("Brave doesn't allow remote debugging yet: open brave://inspect/#remote-debugging in Brave")
    (brave / "DevToolsActivePort").write_text(f"{free_port()}\n/devtools/browser/x\n", encoding="utf-8")
    with pytest.raises(ChromeError, match="^Brave isn't running"):
        find_ws_url(brave)


def test_launch_refuses_every_real_browser_folder(monkeypatch):
    from ai_browser import chrome

    monkeypatch.setattr(chrome, "chrome_binary", lambda: "/usr/bin/false")
    for folder in chrome.own_browser_dirs():
        monkeypatch.setenv("AIB_CHROME_DIR", str(folder))  # whatever AIB_CHROME_DIR says
        with pytest.raises(ChromeError, match="refusing to launch a browser on the user's own profile folder"):
            chrome.launch(folder)


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
    symlink_or_skip(secret, logo)  # what a process in the sandboxed shell could do once the upload was checked
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


class RecordingPlacer:
    """Stands in for grouping.Placer: plain background tabs, and a record of what was placed and reported."""

    def __init__(self, params=None):
        self.link, self.placed_calls, self.popups = None, [], []
        self.params = params or {"url": "about:blank", "background": True}

    async def create_params(self):
        return dict(self.params), None

    async def placed(self, target, marker):
        self.placed_calls.append((target, marker))

    def popup(self, target, opener, url, adopted=False):
        self.popups.append((target, opener, url, adopted))


async def chrome_pages(cdp) -> set[str]:
    return {info["targetId"] for info in (await cdp.send("Target.getTargets"))["targetInfos"] if info["type"] == "page"}


@pytest.fixture
async def own_browser(throwaway_chrome, tmp_path):
    """(make(**options) -> a started Browser in chrome mode, base URL, the test's own CDP connection)."""
    from ai_browser import testpages
    from ai_browser.browser import Browser
    from ai_browser.config import Config
    from ai_browser.workfs import WorkDir

    base, _, stop_pages = testpages.serve_host()
    cdp = await CDP.connect(find_ws_url(throwaway_chrome, timeout=20))
    made = []

    async def make(**options):
        browser = Browser(cdp, WorkDir(tmp_path / "work", f"t{len(made)}"), Config(), mode="chrome", **options)
        await browser.start()
        made.append(browser)
        return browser

    yield make, base, cdp
    for browser in made:
        with contextlib.suppress(Exception):
            await browser.close()
    await cdp.close()
    stop_pages()


@CHROME
async def test_the_users_browser_gets_no_tab_until_the_first_open(own_browser):
    from ai_browser.browser import BrowserError

    make, base, cdp = own_browser
    before = await chrome_pages(cdp)
    browser = await make()
    assert await chrome_pages(cdp) == before and await browser.ensure_tab() == ""  # no blank tab in the user's window
    with pytest.raises(BrowserError, match="switch to a tab the user handed you"):
        await browser.observe()
    await browser.open(base + "form.html")
    assert len(await chrome_pages(cdp) - before) == 1


@CHROME
async def test_without_the_app_each_tab_gets_its_own_window(own_browser):
    from ai_browser.grouping import Placer

    make, base, cdp = own_browser
    user = next(iter(await chrome_pages(cdp)))  # the throwaway Chrome's own first tab stands in for the user's
    browser = await make(placer=Placer(None))
    await browser.open(base + "form.html")
    window = "Browser.getWindowForTarget"
    ours = (await cdp.send(window, {"targetId": browser.current.target}))["windowId"]
    assert ours != (await cdp.send(window, {"targetId": user}))["windowId"]


@CHROME
async def test_keep_tabs_lets_go_instead_of_closing(own_browser):
    make, base, cdp = own_browser
    browser = await make(keep_tabs=True)  # an agent of ai-browser app: the app closes its tabs with the agent
    await browser.open(base + "form.html")
    target = browser.current.target
    await browser.close()
    assert target in await chrome_pages(cdp)


@CHROME
async def test_a_tab_a_page_opens_is_reported_with_its_opener(own_browser):
    from ai_browser.steps import parse_steps

    make, base, _ = own_browser
    placer = RecordingPlacer()
    browser = await make(placer=placer)
    page = await browser.open(base + "popup.html")
    opener = browser.current.target
    assert placer.placed_calls == [(opener, None)]  # the first tab was placed before its first load
    link = next(line.split()[0] for line in page.splitlines() if '"Preview in new tab"' in line)
    await browser.act(parse_steps([f"click {link}"]))
    for _ in range(30):
        if placer.popups:
            break
        await asyncio.sleep(0.1)
    [(target, by, url, adopted)] = placer.popups
    assert by == opener and url == base + "privacy.html" and not adopted and target == browser.current.target


@CHROME
async def test_a_reconnect_with_no_tab_left_still_says_so(chrome_engine):
    engine, base, _ = chrome_engine
    await engine.sandbox_start(chrome=True)
    await engine.open(base + "form.html")
    await engine.cdp.close()  # the connection drops while Chrome keeps running: the old tab is closed on reconnect
    text = (await engine.observe()).text
    assert text.startswith("(reconnected to your Chrome") and "open a page (open url)" in text


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
    assert "your Chrome" in started.text
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
    assert "your Chrome" in (await engine.sandbox_start(chrome=True)).text
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
    assert "your Chrome" in (await engine.sandbox_start(chrome=True)).text
    await engine.open(base + "form.html")
    await engine.cdp.send("Browser.close")  # the user quits Chrome
    await wait_closed(engine)
    (folder / "DevToolsActivePort").unlink(missing_ok=True)
    for _ in range(2):  # each call explains; none quietly switches to another browser
        result = await engine.observe()
        assert result.text.startswith("error: Chrome") and "Ask the user to turn the switch on" in result.text
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
    assert "your Chrome" in (await engine.sandbox_start(chrome=True)).text
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
    assert "your Chrome" in (await engine.sandbox_start(chrome=True)).text
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
    assert "your Chrome" in (await engine.sandbox_start(chrome=True)).text
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
    assert "your Chrome" in (await engine.sandbox_start(chrome=True)).text
    result = await engine.shell("whoami && (ls /profile >/dev/null 2>&1 || echo no-profile)")
    assert result.text.splitlines()[:2] == ["agent", "no-profile"]
    assert engine.info.shell == engine.sandboxes.chrome_shell()  # this home's own shell, never another home's


@pytest.mark.docker
@CHROME
async def test_the_shell_outlives_other_sessions_and_comes_back_when_stopped(chrome_engine):
    from ai_browser.engine import Engine
    from ai_browser.skills import Catalog

    engine, _, _ = chrome_engine
    assert "your Chrome" in (await engine.sandbox_start(chrome=True)).text
    assert (await engine.shell("echo one")).text.startswith("one")
    other = Engine(home=engine.home, default_profile="pytest-chrome", catalog=Catalog([], set()))
    try:
        assert "your Chrome" in (await other.sandbox_start(chrome=True)).text
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


@CHROME
async def test_a_handed_tab_is_listed_taken_on_and_given_back(own_browser):  # Review Focus 3
    from ai_browser.browser import BrowserError

    make, base, cdp = own_browser
    handed: list[dict] = []

    async def handed_tabs():
        return list(handed)

    user = (await cdp.send("Target.createTarget", {"url": base + "privacy.html"}))["targetId"]
    gone = (await cdp.send("Target.createTarget", {"url": base + "form.html"}))["targetId"]
    for _ in range(50):  # until the user's page shows its title (the listing below reads it)
        infos = (await cdp.send("Target.getTargets"))["targetInfos"]
        if any(info["targetId"] == user and info.get("title") == "Privacy" for info in infos):
            break
        await asyncio.sleep(0.1)
    browser = await make(handed=handed_tabs)
    with pytest.raises(BrowserError, match="isn't a tab the user handed you"):
        await browser.adopt(user)  # never a tab of the user's that wasn't handed over
    handed[:] = [{"target": user, "title": "Privacy", "url": base + "privacy.html"},
                 {"target": gone, "title": "Form", "url": base + "form.html"}]
    await cdp.send("Target.closeTarget", {"targetId": gone})  # the user closes one before the agent looks
    await asyncio.sleep(0.3)
    attached = []
    send = cdp.send

    async def spy(method, params=None, session_id=None, timeout=30):
        if method == "Target.attachToTarget":
            attached.append(params["targetId"])
        return await send(method, params, session_id=session_id, timeout=timeout)

    cdp.send = spy
    try:
        assert (await browser.tabs("list")).splitlines() == [
            f'  h1  "Privacy"  {base}privacy.html  (handed to you by the user)']
        with pytest.raises(BrowserError, match="no tab h2"):
            await browser.tabs("switch", "h2")  # the closed one is not offered, and nothing attaches to it
        assert 'page  "Privacy"' in await browser.tabs("switch", "h1")
        assert browser.current.adopted and browser.current.handed and attached == [user]
        assert (await browser.tabs("list")).endswith("(handed by the user)")
        handed.clear()  # AI Home's Take back
        assert await browser.let_go_of_taken_back() == "(the user took back tab t1)\n"
        assert browser.current is None and not browser.owned
        assert user in await chrome_pages(cdp)  # let go of, never closed
    finally:
        cdp.send = send



@CHROME
async def test_a_tab_the_agent_opens_from_a_handed_tab_is_its_own_and_take_back_ends_the_handed_one(own_browser):
    """Review (final), Important 2: the agent's click in a handed tab opens a new tab. That tab is the agent's own
    (its steps opened it: reported as not the user's, grouped with the agent, closed with it), never a second handed
    tab that Take back would miss. Take back lets go of the handed tab, and the session carries on in its own."""
    from ai_browser.steps import parse_steps

    make, base, cdp = own_browser
    user = (await cdp.send("Target.createTarget", {"url": base + "popup.html"}))["targetId"]
    for _ in range(50):  # until the user's page shows its title
        infos = (await cdp.send("Target.getTargets"))["targetInfos"]
        if any(info["targetId"] == user and info.get("title") == "Popup test" for info in infos):
            break
        await asyncio.sleep(0.1)
    handed = [{"target": user, "title": "Popup test", "url": base + "popup.html"}]

    async def handed_tabs():
        return list(handed)

    placer = RecordingPlacer()
    browser = await make(handed=handed_tabs, keep_tabs=True, placer=placer)
    reports = []
    browser.on_tab_event(lambda kind, tab: reports.append((kind, tab.target, tab.adopted)))
    page = await browser.tabs("switch", "h1")
    link = next(line.split()[0] for line in page.splitlines() if '"Preview in new tab"' in line)
    assert "opened new tab" in await browser.act(parse_steps([f"click {link}"]))
    preview = browser.current
    assert preview.target != user and not preview.adopted and not preview.handed
    assert ("opened", preview.target, False) in reports  # AI Home files it under the agent's own tabs
    for _ in range(30):
        if placer.popups:
            break
        await asyncio.sleep(0.1)
    assert placer.popups == [(preview.target, user, base + "privacy.html", False)]  # it joins the agent's group
    await browser.tabs("switch", "t1")  # back in the handed tab when the user takes it back
    handed.clear()  # AI Home's Take back
    assert await browser.let_go_of_taken_back() == "(the user took back tab t1)\n"
    assert [tab.target for tab in browser.owned.values()] == [preview.target] and browser.current is preview
    assert not any(tab.adopted or tab.handed for tab in browser.owned.values())  # nothing of the user's is kept
    assert user in await chrome_pages(cdp)  # let go of, never closed

def test_download_is_a_risky_word_only_in_the_users_browser(tmp_path):
    import re

    from ai_browser.browser import Browser
    from ai_browser.config import Config
    from ai_browser.workfs import WorkDir

    class NoCDP:
        def on(self, method, handler):
            pass

    work = WorkDir(tmp_path / "work", "t")
    assert re.search(Browser(NoCDP(), work, Config(), mode="chrome")._risky, "Download report", re.IGNORECASE)
    for mode in ("sandbox", "app"):  # unchanged there
        assert not re.search(Browser(NoCDP(), work, Config(), mode=mode)._risky, "Download report", re.IGNORECASE)


@CHROME
async def test_downloads_need_the_users_ok_in_their_own_browser(own_browser, tmp_path):
    from ai_browser.steps import parse_steps

    make, base, cdp = own_browser
    downloads = tmp_path / "downloads"  # never the real Downloads folder, even if the cancel failed
    await cdp.send("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(downloads),
                                                   "eventsEnabled": True})
    browser = await make()
    page = await browser.open(base + "downloads.html")
    rows = {name: line for line in page.splitlines()
            for name in ("Download report", "Save a copy", "Get the installer") if f'"{name}"' in line}
    ids = {name: line.split()[0] for name, line in rows.items()}
    # a link's row ends `"name" → address ⚠`: the mark comes last, after the address
    assert rows["Download report"].endswith(" ⚠") and rows["Save a copy"].endswith(" ⚠")
    assert not rows["Get the installer"].endswith("⚠")
    for name in ("Download report", "Save a copy"):
        assert (await browser.act(parse_steps([f"click {ids[name]}"]))).startswith(f"⛔ blocked click {ids[name]}")
    assert await browser._eval("document.getElementById('log').textContent") == ""
    out = await browser.act(parse_steps([f"click {ids['Get the installer']}"]))  # says nothing of a download
    if "was stopped" not in out:  # the browser may announce the download after the step's own read
        await asyncio.sleep(1)
        out = await browser.observe()
    assert "⛔ a download of setup.dmg was stopped: ask the user, then repeat with confirmed=true" in out
    await asyncio.sleep(3.5)  # longer than the whole file takes to arrive
    assert not downloads.exists() or not list(downloads.iterdir())


@CHROME
async def test_a_download_qa_meets_is_not_the_agents(own_browser, tmp_path):
    from ai_browser.qa import run_qa

    make, base, cdp = own_browser
    await cdp.send("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(tmp_path / "downloads"),
                                                   "eventsEnabled": True})
    browser = await make()
    await browser.open(base + "form.html")
    await run_qa(browser, browser.work, base + "qa/autodownload.html", 1, delay=0.05)  # it starts a download itself
    assert "was stopped" not in await browser.observe()  # QA's report says it; the agent wasn't the one downloading


@CHROME
async def test_qa_after_sandbox_start_chrome_crawls_in_the_users_browser(chrome_engine):
    engine, base, _ = chrome_engine
    await engine.sandbox_start(chrome=True)  # the user asked for their own browser
    result = (await engine.qa(base + "qa/index.html", 2)).text
    assert not result.startswith("checked in the Docker sandbox") and not result.startswith("error")
    assert list(engine.work.host_task.rglob("report.html"))


# ---- the engine in the user's browser: the link, the placer, kept tabs, handed tabs ---------------------------


@CHROME
async def test_only_its_own_tabs_reach_the_session(chrome_engine):
    engine, base, folder = chrome_engine
    cdp = await CDP.connect(find_ws_url(folder, timeout=20))
    try:
        secret = (await cdp.send("Target.createTarget", {
            "url": "data:text/html,<title>SECRET-7f3a</title><p>SECRET-7f3a</p>"}))["targetId"]
        await engine.sandbox_start(chrome=True)
        attached = []
        send = engine.cdp.send

        async def spy(method, params=None, session_id=None, timeout=30):
            if method == "Target.attachToTarget":
                attached.append(params["targetId"])
            return await send(method, params, session_id=session_id, timeout=timeout)

        engine.cdp.send = spy
        texts = [(await engine.open(base + "form.html")).text, (await engine.tabs("list")).text,
                 (await engine.sandbox_status()).text, (await engine.observe()).text,
                 (await engine.tabs("switch", "u1")).text, (await engine.tabs("switch", "h1")).text]
        assert texts[4].startswith("error: no tab u1") and texts[5].startswith("error: no tab h1")
        assert not any("SECRET-7f3a" in text for text in texts)
        assert "SECRET-7f3a" not in (engine.log.dir / "log.jsonl").read_text(encoding="utf-8")
        assert attached and secret not in attached  # our own tab was attached to, never the user's
    finally:
        await cdp.close()


@CHROME
async def test_sandbox_start_chrome_opens_no_tab(chrome_engine):
    engine, base, folder = chrome_engine
    cdp = await CDP.connect(find_ws_url(folder, timeout=20))
    try:
        before = await chrome_pages(cdp)
        text = (await engine.sandbox_start(chrome=True)).text
        assert ("your Chrome · only tabs this session opens, and tabs the user hands it · its tabs open in their own "
                "window: ai-browser app isn't running") in text
        assert await chrome_pages(cdp) == before
        await engine.open(base + "form.html")
        assert len(await chrome_pages(cdp) - before) == 1
    finally:
        await cdp.close()


@CHROME
async def test_an_app_agents_tabs_stay_when_its_engine_ends(chrome_engine, monkeypatch):
    engine, base, folder = chrome_engine
    monkeypatch.setenv("AIB_APP_AGENT", "a1")  # an agent of ai-browser app (no app to report to in this test)
    await engine.sandbox_start(chrome=True)
    await engine.open(base + "form.html")
    target = engine.browser.current.target
    assert not (engine.home / "sandboxes" / "chrome" / "sessions").exists()  # the app cleans up, not the next session
    await engine.close()
    cdp = await CDP.connect(find_ws_url(folder, timeout=20))
    try:
        assert target in await chrome_pages(cdp)
    finally:
        await cdp.close()


@CHROME
async def test_a_session_joins_the_running_app_and_says_goodbye(chrome_engine):
    from test_grouping import App

    engine, base, _ = chrome_engine
    app = App({"/agent-status": {"groups": True, "handed": []}, "/agent-claim": {"grouped": True, "tab": 7}})
    try:
        (engine.home / "app").mkdir(parents=True)
        (engine.home / "app" / "link.json").write_text(json.dumps({
            "events": app.url + "/agent-events", "session_token": "sess", "pid": os.getpid()}), encoding="utf-8")
        assert "tab group 'Claude Code'" in (await engine.sandbox_start(chrome=True)).text
        await engine.open(base + "form.html")
        agent = f"cc-{engine.task_id}"
        sent = [(method, path.split("?")[0], body) for method, path, body, _ in app.requests]
        assert ("POST", "/agent-hello", {"agent": agent, "pid": os.getpid()}) in sent
        claim = next(body for _, path, body in sent if path == "/agent-claim")
        assert claim["agent"] == agent and len(claim["marker"]) == 16
        assert {token for *_, token in app.requests} == {"sess"}  # the session token, never an agent's
        await engine.close()
        assert ("POST", "/agent-bye", {"agent": agent}) in [(m, p, b) for m, p, b, _ in app.requests]
    finally:
        app.stop()
