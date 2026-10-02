"""The AI Browser launcher: a dedicated Chrome profile with our side panel installed over the DevTools pipe."""

import asyncio
import json

import pytest

from ai_browser.chrome import chrome_binary

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


def test_prepare_extension_copies_the_panel_with_its_config(tmp_path):
    from ai_browser.appbrowser import prepare_extension

    folder = prepare_extension(tmp_path, "http://127.0.0.1:8792", "secret")
    assert folder == tmp_path / "app" / "extension"
    assert json.loads((folder / "manifest.json").read_text())["side_panel"]["default_path"] == "panel.html"
    assert json.loads((folder / "config.json").read_text()) == {"server": "http://127.0.0.1:8792", "token": "secret"}


@CHROME
async def test_launch_installs_the_panel_and_the_engine_can_connect(tmp_path):
    from ai_browser.appbrowser import AppBrowserError, launch_app_browser, prepare_extension
    from ai_browser.cdp import CDP

    extension = prepare_extension(tmp_path, "http://127.0.0.1:1", "t")
    app = launch_app_browser(tmp_path / "profile", extension, headless=True)
    try:
        assert len(app.extension_id) == 32
        cdp = await CDP.connect(app.ws_url)  # the engine's way in: the debugging port
        panel = (await cdp.send("Target.createTarget", {"url": f"chrome-extension://{app.extension_id}/panel.html"}))
        for _ in range(100):  # until the page has its title (a fixed wait failed once under load)
            infos = {t["targetId"]: t for t in (await cdp.send("Target.getTargets"))["targetInfos"]}
            if infos[panel["targetId"]]["title"] == "AI Browser":
                break
            await asyncio.sleep(0.1)
        await cdp.close()
        assert infos[panel["targetId"]]["title"] == "AI Browser"  # the installed panel page loads
        with pytest.raises(AppBrowserError, match="already open"):
            launch_app_browser(tmp_path / "profile", extension, headless=True)
    finally:
        app.close()
    assert app.closed


@CHROME
def test_launch_works_whatever_descriptors_the_caller_has_open(tmp_path):
    import subprocess
    import sys

    # A busy process (like `ai-browser app`): fds 3 and 4 are free while new pipes land on high numbers.
    code = """
import fcntl, os, sys
for fd in (3, 4):
    try:
        os.close(fd)
    except OSError:
        pass
real_pipe = os.pipe
def high_pipe():
    r, w = real_pipe()
    high = fcntl.fcntl(r, fcntl.F_DUPFD, 50), fcntl.fcntl(w, fcntl.F_DUPFD, 50)
    os.close(r)
    os.close(w)
    return high
os.pipe = high_pipe
from ai_browser.appbrowser import launch_app_browser, prepare_extension
app = launch_app_browser(sys.argv[1] + "/profile", prepare_extension(sys.argv[1], "http://127.0.0.1:1", "t"),
                         headless=True)
print(len(app.extension_id))
app.close()
"""
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path)], capture_output=True, text=True, timeout=90)
    assert result.stdout.strip() == "32", result.stderr[-800:]


def test_a_chrome_that_cannot_run_is_reported_plainly(tmp_path, monkeypatch):
    import ai_browser.appbrowser as appbrowser

    monkeypatch.setattr(appbrowser, "chrome_binary", lambda: str(tmp_path / "missing-chrome"))
    with pytest.raises(appbrowser.AppBrowserError, match="AI Browser could not start"):
        appbrowser.launch_app_browser(tmp_path / "profile", tmp_path / "extension", headless=True)


def test_headed_ai_browser_is_not_in_automation_mode(tmp_path):
    from ai_browser.appbrowser import chrome_args

    args = chrome_args("/chrome", tmp_path / "profile", headless=False, pipe=False,
                       urls=["chrome-extension://abc/home.html"])
    for flag in ("--remote-debugging-pipe", "--enable-unsafe-extension-debugging", "--enable-automation"):
        assert flag not in args
    assert "--remote-debugging-port=0" in args and args[-1] == "chrome-extension://abc/home.html"


def test_the_install_check_reads_the_profile(tmp_path):
    from ai_browser.appbrowser import extension_id_for, extension_installed

    folder, profile = tmp_path / "ext", tmp_path / "profile"
    folder.mkdir()
    assert not extension_installed(profile, folder)  # no profile yet
    prefs = profile / "Default" / "Secure Preferences"
    prefs.parent.mkdir(parents=True)
    prefs.write_text(json.dumps({"extensions": {"settings": {extension_id_for(folder): {"path": str(tmp_path / "x")}}}}))
    assert not extension_installed(profile, folder)  # same ID, another folder
    prefs.write_text(json.dumps({"extensions": {"settings": {extension_id_for(folder): {"path": str(folder)}}}}))
    assert extension_installed(profile, folder)
    prefs.write_text("not json")
    assert not extension_installed(profile, folder)
    (profile / "Default" / "Preferences").write_text(
        json.dumps({"extensions": {"settings": {extension_id_for(folder): {"path": str(folder)}}}}))
    assert extension_installed(profile, folder)  # some Chrome builds keep it in Preferences


@CHROME
def test_the_extension_id_is_the_one_chrome_gives(tmp_path):
    from ai_browser.appbrowser import extension_id_for, launch_app_browser, prepare_extension

    folder = prepare_extension(tmp_path, "http://127.0.0.1:1", "t")
    app = launch_app_browser(tmp_path / "profile", folder, headless=True)
    try:
        assert app.extension_id == extension_id_for(folder) and app.installed
    finally:
        app.close()


@CHROME
async def test_without_the_pipe_chrome_opens_the_urls_and_quits_on_close(tmp_path):
    import time

    from ai_browser.appbrowser import launch_app_browser, prepare_extension
    from ai_browser.cdp import CDP

    folder = prepare_extension(tmp_path, "http://127.0.0.1:1", "t")
    app = launch_app_browser(tmp_path / "profile", folder, headless=True, pipe_install=False,
                             urls=["data:text/html,<title>hi</title>"])
    try:
        assert app.installed is False
        cdp = await CDP.connect(app.ws_url)
        try:
            for _ in range(50):
                titles = [t["title"] for t in (await cdp.send("Target.getTargets"))["targetInfos"]]
                if "hi" in titles:
                    break
                await asyncio.sleep(0.1)
            assert "hi" in titles
        finally:
            await cdp.close()
    finally:
        started = time.monotonic()
        await asyncio.to_thread(app.close)
    assert app.closed and time.monotonic() - started < 15
