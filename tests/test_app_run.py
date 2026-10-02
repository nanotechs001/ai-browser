"""`ai-browser app`: server, AI Browser and panel together; it ends cleanly when the browser closes."""

import asyncio
import json
import os
import socket
import time

import httpx
import pytest

from ai_browser.chrome import chrome_binary
from conftest import file_mode

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


async def page_urls(app) -> list[str]:
    from ai_browser.cdp import CDP

    cdp = await CDP.connect(app.ws_url)
    try:
        for _ in range(80):  # until AI Home, or the setup page, is open
            urls = [info["url"] for info in (await cdp.send("Target.getTargets"))["targetInfos"]
                    if info["type"] == "page"]
            if any("home.html" in url or url.endswith("/setup") for url in urls):
                return urls
            await asyncio.sleep(0.1)
        return urls
    finally:
        await cdp.close()


@pytest.mark.posix_only
@CHROME
async def test_run_app_opens_the_browser_and_ends_when_it_closes(fake_claude, tmp_path):
    from ai_browser.app.run import run_app

    runner, _, _ = fake_claude
    seen = {}

    async def ready(url, app):
        async with httpx.AsyncClient() as client:
            seen["health"] = (await client.get(url + "/health")).json()
        seen["config"] = json.loads((tmp_path / "home" / "app" / "extension" / "config.json").read_text())
        seen["url"] = url
        seen["pages"] = await page_urls(app)
        app.process.kill()  # the user closes AI Browser (here, abruptly)

    started = time.monotonic()
    code = await asyncio.wait_for(run_app(tmp_path / "home", headless=True, claude=str(runner), ready=ready,
                                          out=lambda *args: None), 30)
    assert code == 0 and time.monotonic() - started < 20
    assert seen["health"] == {"ok": True} and seen["config"]["server"] == seen["url"]
    assert any("/home.html" in url for url in seen["pages"])  # AI Home is the first thing it shows
    with socket.socket() as probe:  # the server's port is free again (closed connections may linger in TIME_WAIT)
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", int(seen["url"].rsplit(":", 1)[1])))


@pytest.mark.posix_only
@CHROME
async def test_run_app_refuses_a_profile_already_in_use(fake_claude, tmp_path):
    from ai_browser.app.run import run_app
    from ai_browser.appbrowser import app_profile, launch_app_browser, prepare_extension

    runner, _, _ = fake_claude
    other = launch_app_browser(app_profile(tmp_path / "home"),
                               prepare_extension(tmp_path / "other", "http://127.0.0.1:1", "t"), headless=True)
    lines = []
    try:
        code = await asyncio.wait_for(run_app(tmp_path / "home", headless=True, claude=str(runner),
                                              out=lines.append), 30)
    finally:
        other.close()
    assert code == 1 and any("already open" in line for line in lines)


@pytest.mark.posix_only
@CHROME
async def test_a_second_run_changes_nothing_for_the_running_one(fake_claude, tmp_path):
    from ai_browser.app.run import run_app

    runner, _, _ = fake_claude
    config = tmp_path / "home" / "app" / "extension" / "config.json"
    seen = {}
    stop = asyncio.Event()

    async def ready(url, app):
        before, lines = config.read_text(), []
        seen["code"] = await run_app(tmp_path / "home", headless=True, claude=str(runner), out=lines.append)
        seen["lines"], seen["unchanged"] = lines, config.read_text() == before
        stop.set()

    code = await asyncio.wait_for(run_app(tmp_path / "home", headless=True, claude=str(runner), ready=ready,
                                          stop=stop, out=lambda *args: None), 60)
    assert code == 0 and seen["code"] == 1
    assert any("already running" in line for line in seen["lines"]) and seen["unchanged"]


@pytest.mark.posix_only
@CHROME
async def test_run_app_ends_when_the_last_window_closes(fake_claude, tmp_path):
    from ai_browser.app.run import run_app
    from ai_browser.cdp import CDP

    runner, _, _ = fake_claude
    seen = {}

    async def ready(url, app):
        seen["app"] = app
        await page_urls(app)  # AI Home has opened (the worker opens it when the extension is installed)
        cdp = await CDP.connect(app.ws_url)
        for info in (await cdp.send("Target.getTargets"))["targetInfos"]:
            if info["type"] == "page":  # like closing the last window on macOS: Chrome itself keeps running
                await cdp.send("Target.closeTarget", {"targetId": info["targetId"]})
        await cdp.close()

    code = await asyncio.wait_for(run_app(tmp_path / "home", headless=True, claude=str(runner), ready=ready,
                                          out=lambda *args: None), 30)
    assert code == 0 and seen["app"].closed  # the command ended and quit AI Browser


@CHROME
async def test_first_start_opens_the_setup_steps(fake_claude, tmp_path, monkeypatch):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    lines, seen = [], {}
    stop = asyncio.Event()

    async def ready(url, app):
        seen["pages"] = await page_urls(app)
        async with httpx.AsyncClient() as client:
            seen["status"] = (await client.get(url + "/setup/status")).json()
        stop.set()

    shown = []
    monkeypatch.setattr(run, "reveal", shown.append)  # on a Mac: a Finder window with the folder selected
    code = await asyncio.wait_for(run.run_app(tmp_path / "home", headless=True, pipe_install=False, claude=str(runner),
                                              ready=ready, stop=stop, out=lines.append), 60)
    assert shown == [str((tmp_path / "home" / "app" / "extension").resolve())]
    printed = "\n".join(lines)
    assert code == 0 and "Developer mode" in printed and str((tmp_path / "home" / "app" / "extension").resolve()) in printed
    assert "chrome://extensions/" in seen["pages"] and any(url.endswith("/setup") for url in seen["pages"])
    assert seen["status"] == {"installed": False, "watcher": False}  # one Finder window at a time: AI Browser first


@CHROME
async def test_a_stale_install_record_still_gets_the_setup_steps(fake_claude, tmp_path, monkeypatch):
    from ai_browser.app import run
    from ai_browser.appbrowser import extension_id_for

    runner, _, _ = fake_claude
    monkeypatch.setattr(run, "EXTENSION_WAIT", 1)
    monkeypatch.setattr(run, "reveal", lambda folder: None)
    folder = tmp_path / "home" / "app" / "extension"
    prefs = tmp_path / "home" / "browser" / "Default" / "Secure Preferences"
    prefs.parent.mkdir(parents=True)
    # what a one-run install (an older ai-browser, over the pipe) leaves behind: Chrome does not load it again
    prefs.write_text(json.dumps({"extensions": {"settings": {extension_id_for(folder): {"path": str(folder),
                                                                                        "location": 4}}}}))
    lines, seen = [], {}
    stop = asyncio.Event()

    async def ready(url, app):
        seen["pages"] = await page_urls(app)
        stop.set()

    code = await asyncio.wait_for(run.run_app(tmp_path / "home", headless=True, pipe_install=False, claude=str(runner),
                                              ready=ready, stop=stop, out=lines.append), 60)
    assert code == 0 and "Developer mode" in "\n".join(lines)
    assert any(url.endswith("/setup") for url in seen["pages"])


async def opened(app, ending, seconds=10) -> bool:
    from ai_browser.cdp import CDP

    cdp = await CDP.connect(app.ws_url)
    try:
        for _ in range(int(seconds * 10)):
            if any(info["url"].endswith(ending) for info in (await cdp.send("Target.getTargets"))["targetInfos"]):
                return True
            await asyncio.sleep(0.1)
        return False
    finally:
        await cdp.close()


@pytest.mark.posix_only
@CHROME
async def test_first_start_also_sets_up_the_watcher(fake_claude, tmp_path, monkeypatch):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    lines, seen, shown = [], {}, []
    monkeypatch.setattr(run, "reveal", shown.append)
    stop = asyncio.Event()

    async def ready(url, app):
        async with httpx.AsyncClient() as client:
            for _ in range(50):  # AI Browser's own extension (installed over the pipe) connects first
                seen["status"] = (await client.get(url + "/setup/status")).json()
                if seen["status"]["installed"]:
                    break
                await asyncio.sleep(0.2)
        seen["brave_page"] = await opened(app, "/setup#brave")
        stop.set()

    home = tmp_path / "home"
    code = await asyncio.wait_for(run.run_app(home, headless=True, claude=str(runner), ready=ready, stop=stop,
                                              out=lines.append), 60)
    watcher = str((home / "app" / "watcher").resolve())
    printed = "\n".join(lines)
    assert code == 0 and "brave://extensions" in printed and watcher in printed
    assert shown == [watcher] and seen["brave_page"]
    assert seen["status"] == {"installed": True, "watcher": False}
    again = asyncio.Event()

    async def ready_again(url, app):
        again.set()

    code = await asyncio.wait_for(run.run_app(home, headless=True, claude=str(runner), ready=ready_again, stop=again,
                                              out=lines.append), 60)
    assert code == 0 and shown == [watcher]  # the Finder window, once; the printed steps until it is set up


@pytest.mark.posix_only
@CHROME
async def test_the_brain_survives_a_restart(fake_claude, tmp_path):
    from websockets.asyncio.client import connect

    from ai_browser.app.run import run_app
    from ai_browser.brain.store import BrainStore, Item

    runner, _, _ = fake_claude
    home = tmp_path / "home"
    BrainStore(home).put(Item(id="gmail:t1", site="gmail", raw_id="t1", sender="Maria", subject="Launch",
                              kind="needs_reply", summary="Move the launch?"))
    seen = {}

    async def ready(url, app):
        token = json.loads((home / "app" / "extension" / "config.json").read_text())["token"]
        async with connect(url.replace("http", "ws") + "/ws?token=" + token,
                           origin=f"chrome-extension://{app.extension_id}") as ws:
            await ws.send(json.dumps({"type": "brain"}))
            while "snapshot" not in seen:
                message = json.loads(await asyncio.wait_for(ws.recv(), 10))
                if message["type"] == "brain_snapshot":
                    seen["snapshot"] = message
        app.process.kill()

    code = await asyncio.wait_for(run_app(home, headless=True, claude=str(runner), ready=ready,
                                          out=lambda *args: None), 60)
    assert code == 0 and [item["id"] for item in seen["snapshot"]["items"]] == ["gmail:t1"]


@pytest.mark.posix_only
@CHROME
async def test_scheduled_workflows_tick_while_the_app_runs(fake_claude, tmp_path, monkeypatch):
    from ai_browser.app import run
    from ai_browser.brain import workflows as workflow_module
    from ai_browser.brain.workflows import WorkflowStore
    from test_bridge import EVENTS

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS))
    home = tmp_path / "home"
    WorkflowStore(home).save({"name": "Hourly check", "instructions": "Check the sites and tell me what changed",
                              "trigger": "schedule", "schedule": "every 15m"})
    clock = [1_000_000.0]
    monkeypatch.setattr(workflow_module, "_now", lambda: clock[0])
    monkeypatch.setattr(run, "TICK", 0.1)
    seen = {}

    def users():
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines() if '"type": "user"' in line]

    async def ready(url, app):
        await asyncio.sleep(0.5)  # the first tick starts the schedule's clock: nothing missed is caught up
        assert users() == []
        clock[0] += 16 * 60
        for _ in range(100):
            if users():
                break
            await asyncio.sleep(0.1)
        seen["users"] = users()
        app.process.kill()

    code = await asyncio.wait_for(run.run_app(home, headless=True, claude=str(runner), ready=ready,
                                              out=lambda *args: None), 60)
    assert code == 0 and seen["users"][0]["message"]["content"].startswith("Check the sites and tell me what changed")


def test_the_app_picks_brave_when_its_folder_exists(tmp_path, monkeypatch):  # Review Focus 5
    from ai_browser.app.run import app_browser, brave_env

    monkeypatch.delenv("AIB_APP_BROWSER")
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    monkeypatch.setenv("AIB_CHROME_DIR", str(folder))
    assert app_browser() == "app"  # no browser folder: AI Browser, as before
    folder.mkdir(parents=True)
    assert app_browser() == "brave"
    assert app_browser("app") == "app" and app_browser(" Brave ") == "brave"
    monkeypatch.setenv("AIB_APP_BROWSER", "APP")
    assert app_browser() == "app"
    with pytest.raises(ValueError, match="--browser must be brave or app"):
        app_browser("firefox")
    assert brave_env(folder) == {"AIB_BROWSER": "chrome", "AIB_CHROME_DIR": str(folder)}


@pytest.mark.posix_only
@CHROME
async def test_in_brave_mode_the_app_shows_the_switch_and_writes_link_json(fake_claude, tmp_path, monkeypatch):
    from websockets.asyncio.client import connect

    from ai_browser.app import run

    runner, _, _ = fake_claude
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    folder.mkdir(parents=True)  # Brave is installed; its switch is off
    monkeypatch.setenv("AIB_CHROME_DIR", str(folder))
    home, lines, seen = tmp_path / "home", [], {}

    async def ready(url, app):
        link = home / "app" / "link.json"
        seen["mode"] = file_mode(link)
        seen["link"] = json.loads(link.read_text(encoding="utf-8"))
        seen["url"] = url
        token = json.loads((home / "app" / "extension" / "config.json").read_text())["token"]
        async with connect(url.replace("http", "ws") + "/ws?token=" + token,
                           origin=f"chrome-extension://{app.extension_id}") as ws:
            await ws.send(json.dumps({"type": "hello", "view": "home"}))
            await ws.send(json.dumps({"type": "new_task", "text": "look around", "request": "r"}))
            while "created" not in seen:
                message = json.loads(await asyncio.wait_for(ws.recv(), 10))
                if message["type"] == "snapshot":
                    seen["browser"] = message["browser"]
                elif message["type"] == "created":
                    seen["created"] = True
        mcp = home / "app" / "agents" / "a1" / "mcp.json"
        for _ in range(100):
            if mcp.exists():
                break
            await asyncio.sleep(0.1)
        seen["env"] = json.loads(mcp.read_text())["mcpServers"]["ai-browser"]["env"]
        app.process.kill()

    code = await asyncio.wait_for(run.run_app(home, headless=True, claude=str(runner), ready=ready,
                                              out=lines.append, browser="brave"), 60)
    printed = "\n".join(lines)
    assert code == 0 and seen["mode"] in (0o600, None)
    assert seen["link"] == {"events": seen["url"] + "/agent-events", "session_token": seen["link"]["session_token"],
                            "pid": os.getpid()} and seen["link"]["session_token"]
    assert seen["browser"] == {"kind": "brave", "name": "Brave", "state": "off", "groups": "no_watcher"}
    assert seen["env"]["AIB_BROWSER"] == "chrome" and seen["env"]["AIB_CHROME_DIR"] == str(folder)
    assert "brave://inspect/#remote-debugging" in printed
    assert "any program on this computer can reach your Brave" in printed
    assert not (home / "app" / "link.json").exists()  # removed at exit


async def test_a_bad_browser_choice_is_refused(tmp_path):
    from ai_browser.app.run import run_app

    lines = []
    assert await run_app(tmp_path / "home", browser="firefox", out=lines.append) == 1
    assert lines == ["error: --browser must be brave or app, not 'firefox'"]


@CHROME
async def test_first_start_in_brave_mode_names_the_extension_folder(fake_claude, tmp_path, monkeypatch):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    brave = tmp_path / "BraveSoftware" / "Brave-Browser"
    brave.mkdir(parents=True)  # Brave is installed; its switch is off
    monkeypatch.setenv("AIB_CHROME_DIR", str(brave))
    lines, shown, stop = [], [], asyncio.Event()
    monkeypatch.setattr(run, "reveal", shown.append)
    code = await asyncio.wait_for(run.run_app(tmp_path / "home", headless=True, pipe_install=False, claude=str(runner),
                                              ready=lambda url, app: stop.set(), stop=stop, out=lines.append,
                                              browser="brave"), 60)
    extension = str((tmp_path / "home" / "app" / "extension").resolve())
    assert code == 0 and shown == [extension]  # the extension's folder in Finder, never the user's Brave folder
    assert extension in "\n".join(lines)


@pytest.mark.posix_only
@CHROME
async def test_the_app_can_hear_with_its_models_folder(fake_claude, tmp_path):
    from websockets.asyncio.client import connect

    from ai_browser.app.run import run_app

    runner, _, _ = fake_claude
    seen = {}

    async def ready(url, app):
        config = json.loads((tmp_path / "home" / "app" / "extension" / "config.json").read_text(encoding="utf-8"))
        socket_url = url.replace("http", "ws") + "/ws?token=" + config["token"]
        async with connect(socket_url, origin=f"chrome-extension://{app.extension_id}") as ws:
            await ws.send(json.dumps({"type": "hearing"}))
            while (message := json.loads(await asyncio.wait_for(ws.recv(), 10)))["type"] != "hearing_status":
                pass
            seen["status"] = message
        app.process.kill()  # the user closes AI Browser

    code = await asyncio.wait_for(run_app(tmp_path / "home", headless=True, claude=str(runner), ready=ready,
                                          out=lambda *args: None), 30)
    status = seen["status"]
    assert code == 0 and status["folder"] == str(tmp_path / "home" / "models" / "faster-whisper-base.en")
    assert status["size_bytes"] == 147_769_510 and status["model"] == "Whisper base.en"
    assert status["state"] in ("no_engine", "no_model")  # never ready by itself: the model comes only on Download
