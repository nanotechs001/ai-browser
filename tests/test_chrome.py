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
    # With AIB_BROWSER unset the engine would use the user's own Brave, which would ask "Allow remote debugging?". The
    # app's agents browse in the browser AIB_CHROME_DIR names: an empty folder here, so BraveLink stays off.
    assert os.environ["AIB_BROWSER"] == "sandbox" and "AIB_APP_BROWSER" not in os.environ
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


def test_a_throwaway_chrome_never_asks_for_a_keychain(monkeypatch, tmp_path):
    """macOS asks "A keychain cannot be found to store Chrome" when a test Chrome starts under a HOME with no keychain:
    a throwaway profile never needs one, so it gets Chrome's mock keychain."""
    import subprocess

    import ai_browser.chrome as chrome

    started = []
    monkeypatch.setattr(chrome, "chrome_binary", lambda: "/fake/chrome")
    monkeypatch.setattr(subprocess, "Popen", lambda args, **_: started.append(args))
    launch(tmp_path / "profile")
    assert "--use-mock-keychain" in started[0]


def test_missing_folder_explains_the_fix(tmp_path):
    with pytest.raises(ChromeError, match="chrome://inspect/#remote-debugging"):
        find_ws_url(tmp_path / "nope")


def test_missing_port_file_explains_the_fix(tmp_path):
    with pytest.raises(ChromeError, match="chrome://inspect/#remote-debugging"):
        find_ws_url(tmp_path)


def test_stale_port_file_says_chrome_is_not_running(tmp_path):
    (tmp_path / "DevToolsActivePort").write_text(f"{free_port()}\n/devtools/browser/abc\n", encoding="utf-8")
    with pytest.raises(ChromeError, match="isn't running"):
        find_ws_url(tmp_path)


def test_a_port_file_removed_while_reading_counts_as_missing(tmp_path, monkeypatch):
    (tmp_path / "DevToolsActivePort").write_text("1\n/devtools/browser/abc\n", encoding="utf-8")

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
@pytest.mark.direct_only  # tests the Browser alone over one shared connection
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
    secret.write_text("TOP SECRET", encoding="utf-8")
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
    for _ in range(50):  # a closed tab is listed a moment longer (on Windows, more than 0.2 s)
        if await pages() == before:
            break
        await asyncio.sleep(0.1)
    assert await pages() == before


class RecordingPlacer:
    """Stands in for grouping.Placer: plain background tabs, and a record of each one it opened."""

    def __init__(self):
        self.link, self.opened = None, []

    async def open_tab(self, cdp):
        target = (await cdp.send("Target.createTarget", {"url": "about:blank", "background": True}))["targetId"]
        self.opened.append(target)
        return target


async def chrome_pages(cdp) -> set[str]:
    return {info["targetId"] for info in (await cdp.send("Target.getTargets"))["targetInfos"] if info["type"] == "page"}


@pytest.fixture
async def own_browser(throwaway_chrome, tmp_path, route):
    """(make(**options) -> a started Browser in chrome mode, base URL, the test's own CDP connection). The Browsers'
    connection is the test's own (direct) or goes through the app's relay (`route`)."""
    from ai_browser import testpages
    from ai_browser.browser import Browser
    from ai_browser.config import Config
    from ai_browser.workfs import WorkDir
    from conftest import browser_connection

    base, _, stop_pages = testpages.serve_host()
    cdp = await CDP.connect(find_ws_url(throwaway_chrome, timeout=20))
    made = []
    # direct: the Browsers share the test's own connection, as they always did (some tests spy on it)
    routed = contextlib.nullcontext(cdp) if route == "direct" else browser_connection(throwaway_chrome, route,
                                                                                         tmp_path / "relay-home")
    async with routed as browsers:
        async def make(**options):
            browser = Browser(browsers, WorkDir(tmp_path / "work", f"t{len(made)}"), Config(), mode="chrome",
                              **options)
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


async def test_a_tab_a_page_opens_is_followed_and_only_the_first_is_the_placers(own_browser):
    from ai_browser.steps import parse_steps

    make, base, _ = own_browser
    placer = RecordingPlacer()
    browser = await make(placer=placer)
    page = await browser.open(base + "popup.html")
    opener = browser.current.target
    assert placer.opened == [opener]  # the first tab came from the placer, before its first load
    link = next(line.split()[0] for line in page.splitlines() if '"Preview in new tab"' in line)
    await browser.act(parse_steps([f"click {link}"]))
    for _ in range(30):
        if browser.current.target != opener:
            break
        await asyncio.sleep(0.1)
    assert browser.current.target != opener and placer.opened == [opener]  # the page's own tab: followed, not placed


async def location(browser, tab) -> str:
    return await browser.eval_in(tab, "location.href")


def reused(tab) -> str:
    return f"(opened in your oldest tab {tab.key}: at most 2 tabs of your own)"


@CHROME
async def test_a_third_tab_of_its_own_reuses_the_oldest_and_opens_none(own_browser):
    """At most MAX_OWN_TABS tabs of its own (each a window of its own in the user's Brave): a third new tab is the
    oldest one, the tab switched to least recently, which opens the page; no tab, so no window, opens."""
    from ai_browser.browser import MAX_OWN_TABS

    make, base, cdp = own_browser
    placer = RecordingPlacer()
    browser = await make(placer=placer)
    await browser.open(base + "form.html")
    first = browser.current
    await browser.open(base + "privacy.html", new_tab=True)
    second = browser.current
    pages = await chrome_pages(cdp)
    assert MAX_OWN_TABS == 2 and placer.opened == [first.target, second.target]
    out = await browser.open(base + "popup.html", new_tab=True)
    assert out.splitlines()[0] == reused(first) and out.splitlines()[1].startswith('page  "Popup test"')
    assert browser.current is first and list(browser.owned) == [first.key, second.key]
    assert placer.opened == [first.target, second.target] and await chrome_pages(cdp) == pages  # nothing opened
    assert await location(browser, second) == base + "privacy.html"  # the other tab is left as it was
    out = await browser.tabs("new", url=base + "form.html")  # tabs new too: now the second is the oldest
    assert out.splitlines()[0] == reused(second) and browser.current is second
    assert await location(browser, first) == base + "popup.html" and await location(browser, second) == base + \
        "form.html"
    await browser.tabs("switch", first.key)  # the oldest is the one switched to least recently: the second again
    assert (await browser.open(base + "privacy.html", new_tab=True)).splitlines()[0] == reused(second)
    assert (await browser.tabs("new")).splitlines()[0] == reused(first)  # a blank one: the oldest, blank
    assert browser.current is first and await location(browser, first) == "about:blank"
    assert placer.opened == [first.target, second.target] and await chrome_pages(cdp) == pages


@CHROME
async def test_a_reused_tab_that_cant_load_leaves_the_agent_where_it_was(own_browser):
    from ai_browser.browser import StepBlocked
    from ai_browser.steps import parse_steps

    make, base, cdp = own_browser
    placer = RecordingPlacer()
    browser = await make(placer=placer)
    page = await browser.open(base + "dialogs.html")
    first = browser.current
    changes = next(line.split()[0] for line in page.splitlines() if '"Make changes"' in line)
    await browser.act(parse_steps([f"click {changes}"]))  # the page now asks before leaving
    await browser.open(base + "form.html", new_tab=True)
    second = browser.current
    for _ in range(2):  # and again: the oldest is still the first, and nothing moved
        with pytest.raises(StepBlocked) as blocked:
            await browser.open(base + "privacy.html", new_tab=True)
        said = str(blocked.value)
        assert said.startswith(f"(tried your oldest tab {first.key}: at most 2 tabs of your own) ") and \
            "asks before leaving" in said
        assert browser.current is second and list(browser.owned) == [first.key, second.key]
        assert await location(browser, first) == base + "dialogs.html"
        assert await location(browser, second) == base + "form.html"
    assert placer.opened == [first.target, second.target]


@CHROME
@pytest.mark.parametrize("url", ["file:///etc/hosts", ""])
async def test_a_refused_address_changes_nothing_even_at_the_limit(own_browser, url):
    from ai_browser.browser import BrowserError

    make, base, cdp = own_browser
    placer = RecordingPlacer()
    browser = await make(placer=placer)
    await browser.open(base + "form.html")
    first = browser.current
    with pytest.raises(BrowserError):
        await browser.open(url, new_tab=True)  # below the limit: no tab opens
    assert browser.current is first and placer.opened == [first.target]
    await browser.open(base + "privacy.html", new_tab=True)
    second = browser.current
    with pytest.raises(BrowserError):
        await browser.open(url, new_tab=True)  # at the limit: the oldest isn't touched
    assert browser.current is second and list(browser.owned) == [first.key, second.key]
    assert await location(browser, first) == base + "form.html"
    assert await location(browser, second) == base + "privacy.html"
    assert placer.opened == [first.target, second.target]


@CHROME
async def test_without_new_tab_the_page_opens_in_the_current_tab_as_before(own_browser):
    make, base, cdp = own_browser
    placer = RecordingPlacer()
    browser = await make(placer=placer)
    assert (await browser.open(base + "form.html")).startswith('page  "Form test"')  # the first tab: a new one
    first = browser.current
    assert (await browser.open(base + "privacy.html")).startswith('page  "Privacy"')
    assert browser.current is first and placer.opened == [first.target]
    await browser.open(base + "popup.html", new_tab=True)
    second = browser.current
    assert (await browser.open(base + "form.html")).startswith('page  "Form test"')  # at two: no note, no reuse
    assert browser.current is second and await location(browser, first) == base + "privacy.html"
    assert placer.opened == [first.target, second.target]


@CHROME
@pytest.mark.direct_only  # tests the Browser alone over one shared connection (as the other hand-over tests)
async def test_a_handed_tab_neither_counts_nor_is_reused(own_browser):
    make, base, cdp = own_browser
    user = (await cdp.send("Target.createTarget", {"url": base + "privacy.html"}))["targetId"]
    for _ in range(50):  # until the user's page has loaded
        infos = (await cdp.send("Target.getTargets"))["targetInfos"]
        if any(info["targetId"] == user and info.get("title") == "Privacy" for info in infos):
            break
        await asyncio.sleep(0.1)
    handed = [{"target": user, "title": "Privacy", "url": base + "privacy.html"}]

    async def handed_tabs():
        return list(handed)

    placer = RecordingPlacer()
    browser = await make(handed=handed_tabs, placer=placer)
    await browser.tabs("switch", "h1")
    users = browser.current
    await browser.open(base + "form.html", new_tab=True)
    second = browser.current
    await browser.open(base + "popup.html", new_tab=True)
    third = browser.current
    assert users.adopted and placer.opened == [second.target, third.target]  # the handed tab didn't count
    assert users.used < second.used < third.used  # the handed tab is the one used least recently, yet not reused
    out = await browser.open(base + "privacy.html", new_tab=True)
    assert out.splitlines()[0] == reused(second) and browser.current is second
    assert placer.opened == [second.target, third.target]
    assert await location(browser, users) == base + "privacy.html" and users.key in browser.owned  # never reused


@CHROME
async def test_a_closed_tab_frees_its_place(own_browser):
    make, base, cdp = own_browser
    placer = RecordingPlacer()
    browser = await make(placer=placer)
    await browser.open(base + "form.html")
    await browser.open(base + "privacy.html", new_tab=True)
    second = browser.current
    await cdp.send("Target.closeTarget", {"targetId": second.target})  # the user closes it
    for _ in range(50):
        if second.key not in browser.owned:
            break
        await asyncio.sleep(0.1)
    await browser.ensure_tab()  # as the engine does first in every call
    out = await browser.open(base + "popup.html", new_tab=True)
    assert "oldest tab" not in out and len(placer.opened) == 3 and len(browser.owned) == 2
    await browser.tabs("close", browser.current.key)  # the agent closes one itself
    out = await browser.tabs("new", url=base + "privacy.html")
    assert "oldest tab" not in out and len(placer.opened) == 4 and len(browser.owned) == 2


@CHROME
async def test_a_tab_its_page_opened_counts_as_its_own(own_browser):
    from ai_browser.steps import parse_steps

    make, base, cdp = own_browser
    placer = RecordingPlacer()
    browser = await make(placer=placer)
    page = await browser.open(base + "popup.html")
    opener = browser.current
    link = next(line.split()[0] for line in page.splitlines() if '"Preview in new tab"' in line)
    await browser.act(parse_steps([f"click {link}"]))
    for _ in range(30):
        if browser.current is not opener:
            break
        await asyncio.sleep(0.1)
    assert browser.current is not opener and len(browser.owned) == 2  # the page's tab is the agent's own
    out = await browser.open(base + "form.html", new_tab=True)
    assert out.splitlines()[0] == reused(opener) and placer.opened == [opener.target]


@CHROME
async def test_the_engine_says_a_new_tab_reused_the_oldest(chrome_engine):
    engine, base, _ = chrome_engine
    await engine.sandbox_start(chrome=True)
    await engine.open(base + "form.html")
    first = engine.browser.current
    await engine.open(base + "privacy.html", new_tab=True)
    pages = await chrome_pages(engine.cdp)
    text = (await engine.open(base + "popup.html", new_tab=True)).text
    assert text.startswith(reused(first) + '\npage  "Popup test"')
    assert await chrome_pages(engine.cdp) == pages and engine.browser.current is first


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
@pytest.mark.direct_only  # tests the Browser alone over one shared connection
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
@pytest.mark.direct_only  # tests the Browser alone over one shared connection
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
    assert placer.opened == []  # a tab a page opened is the page's: the placer opens none
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
    for mode in ("sandbox",):  # unchanged there
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
    app = App({"/agent-status": {"handed": []}})  # an app that relays nothing: the session browses on its own
    try:
        (engine.home / "app").mkdir(parents=True)
        (engine.home / "app" / "link.json").write_text(json.dumps({
            "events": app.url + "/agent-events", "session_token": "sess", "pid": os.getpid()}), encoding="utf-8")
        assert "its tabs open in their own window" in (await engine.sandbox_start(chrome=True)).text
        await engine.open(base + "form.html")
        agent = f"cc-{engine.task_id}"
        sent = [(method, path.split("?")[0], body) for method, path, body, _ in app.requests]
        assert ("POST", "/agent-hello", {"agent": agent, "pid": os.getpid()}) in sent
        assert "/agent-tab" not in [path for _, path, _ in sent]  # its own connection: it opens its own tabs
        assert {token for *_, token in app.requests} == {"sess"}  # the session token, never an agent's
        await engine.close()
        assert ("POST", "/agent-bye", {"agent": agent}) in [(m, p, b) for m, p, b, _ in app.requests]
    finally:
        app.stop()


def test_aib_chrome_binary_wins_over_the_usual_places(tmp_path, monkeypatch):
    custom = tmp_path / "chrome.exe"
    custom.write_bytes(b"")
    monkeypatch.setenv("AIB_CHROME_BINARY", str(custom))
    assert chrome_binary() == str(custom)


def test_browsers_are_found_in_the_usual_places_then_on_path(tmp_path, monkeypatch):
    from ai_browser import chrome, platforms

    brave = tmp_path / "Brave Browser"
    brave.write_bytes(b"")
    monkeypatch.delenv("AIB_CHROME_BINARY", raising=False)
    monkeypatch.setattr(platforms, "browser_candidates",
                        lambda browser, system=None, env=None: [tmp_path / "missing", brave] if browser == "brave" else [])
    monkeypatch.setattr(chrome, "_registry_path", lambda program: None)
    assert chrome.brave_binary() == str(brave)
    monkeypatch.setattr(chrome.shutil, "which", lambda name: f"/bin/{name}")
    assert chrome.chrome_binary() == "/bin/" + ("chrome" if os.name == "nt" else "google-chrome")


def test_the_everyday_folders_come_from_platforms(monkeypatch):
    import sys

    from ai_browser import chrome, platforms

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", "C:\\Users\\me\\AppData\\Local")
    assert chrome.own_browser_dirs() == [platforms.user_data_dir("brave"), platforms.user_data_dir("chrome")]
    assert all(folder.name.endswith("User Data") for folder in chrome.own_browser_dirs())


def test_the_guard_ignores_case_on_windows(tmp_path, monkeypatch):
    from ai_browser import chrome, platforms

    real = tmp_path / "BraveSoftware" / "Brave-Browser" / "User Data"
    monkeypatch.setattr(chrome, "own_browser_dirs", lambda: [real])
    monkeypatch.setenv("AIB_CHROME_BINARY", str(tmp_path / "chrome.exe"))
    monkeypatch.setattr(platforms, "WINDOWS", True)  # only the comparison changes: no Win32 call is made
    assert chrome._same_folder(tmp_path / "bravesoftware" / "brave-browser" / "user data", real)
    with pytest.raises(ChromeError):
        launch(tmp_path / "bravesoftware" / "brave-browser" / "user data")
    assert not (tmp_path / "bravesoftware").exists()  # refused before anything was made


@CHROME
async def test_the_session_carries_on_when_the_user_closes_its_tab(chrome_engine):  # moved from test_appmode.py
    from ai_browser.cdp import CDP
    from ai_browser.chrome import find_ws_url

    engine, base, folder = chrome_engine
    await engine.sandbox_start(chrome=True)
    user = await CDP.connect(find_ws_url(folder, timeout=20))  # stands in for the user's own clicks
    try:
        await engine.open(base + "form.html")
        old = engine.browser.current.target
        await user.send("Target.closeTarget", {"targetId": old})  # the user closes the session's tab
        await asyncio.sleep(0.3)
        assert "new tab" in (await engine.observe()).text
        assert engine.browser.current.target != old
    finally:
        await user.close()


@CHROME
async def test_a_tab_the_user_opens_from_a_sessions_tab_stays_theirs(chrome_engine):  # moved from test_appmode.py
    from ai_browser.cdp import CDP
    from ai_browser.chrome import find_ws_url
    from ai_browser.steps import parse_step

    engine, base, folder = chrome_engine
    await engine.sandbox_start(chrome=True)
    user = await CDP.connect(find_ws_url(folder, timeout=20))
    try:
        await engine.open(base + "popup.html")  # the session's own (background) tab
        own = engine.browser.current.target
        session = (await user.send("Target.attachToTarget", {"targetId": own, "flatten": True}))["sessionId"]
        await user.send("Runtime.evaluate", {"expression": f"window.open('{base}form.html', '_blank'); 1",
                                             "userGesture": True}, session_id=session)
        await asyncio.sleep(1)
        users = [t["targetId"] for t in (await user.send("Target.getTargets"))["targetInfos"]
                 if t["url"].endswith("form.html")]
        assert users and not {tab.target for tab in engine.browser.owned.values()} & set(users)
        reply = await engine.browser.act([parse_step("scroll down")])
        assert "opened new tab" not in reply and engine.browser.current.target == own  # no jump into the user's tab
    finally:
        await user.close()


@CHROME
async def test_the_apps_pages_are_refused_through_the_engine(chrome_engine, monkeypatch):
    engine, _, _ = chrome_engine
    monkeypatch.setenv("AIB_APP_ORIGIN", "http://127.0.0.1:8799")  # as ai-browser app sets it for its agents
    await engine.sandbox_start(chrome=True)
    assert engine.browser.app_origin == "http://127.0.0.1:8799"
    result = await engine.open("http://127.0.0.1:8799/setup")
    assert result.text.startswith("error") and "AI Browser's own pages open only in its window" in result.text
