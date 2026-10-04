"""`ai-browser app`: the server, the watcher's folder, BraveLink and AI Browser's window together. FakeWindow stands in
for the window (its start address opens in a throwaway headless Chrome, as the real window opens it: the one-time
code, then the cookie); SocketWindow opens no browser, only a socket with the window's cookie. The app ends once the
last window's socket has been gone WINDOW_GRACE seconds, or when `stop` is set."""

import asyncio
import json
import os
import socket
import time
from pathlib import Path

import httpx
import pytest

from ai_browser.chrome import chrome_binary
from conftest import file_mode
from fake_window import FakeWindow, SocketWindow
from test_home import until
from test_tab_menu import connected, pick
from ui_socket import ui_socket

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


def quiet(*args):
    pass


def port_free(url) -> bool:
    with socket.socket() as probe:  # closed connections may linger in TIME_WAIT
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", int(url.rsplit(":", 1)[1])))
        except OSError:
            return False
    return True


@pytest.fixture
async def window(throwaway_chrome):
    """A FakeWindow on a throwaway headless Chrome."""
    from ai_browser.cdp import CDP
    from ai_browser.chrome import find_ws_url

    cdp = await CDP.connect(find_ws_url(throwaway_chrome, timeout=20))
    yield FakeWindow(cdp)
    await cdp.close()


@pytest.fixture
def servers(monkeypatch):
    """Every AppServer run_app makes, for the tests that look inside it."""
    from ai_browser.app import run
    from ai_browser.app.server import AppServer

    made = []

    class Recording(AppServer):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            made.append(self)

    monkeypatch.setattr(run, "AppServer", Recording)
    return made


@CHROME
async def test_it_opens_the_window_and_ends_when_the_window_closes(fake_claude, tmp_path, window, monkeypatch,
                                                                   servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    monkeypatch.setattr(run, "WINDOW_GRACE", 1)
    seen, asked = {}, []

    async def ready(url, opened):
        seen["url"], seen["opened"] = url, opened
        async with httpx.AsyncClient() as client:
            seen["health"] = (await client.get(url + "/health")).json()
        page = await window.page()
        seen["home"] = await until(page, f"location.pathname === '/app' && {connected('/home')}")  # the tab menu
        await window.cdp.send("Target.closeTarget", {"targetId": window.targets[0]})  # the user closes the window
        seen["closed_at"] = time.monotonic()

    def launcher(setting):
        asked.append(setting)
        return window

    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, ready=ready, out=quiet,
                                              launcher=launcher), 60)
    assert code == 0 and seen["health"] == {"ok": True} and seen["home"] and seen["opened"] is window
    assert time.monotonic() - seen["closed_at"] < run.WINDOW_GRACE + 2
    assert asked == ["auto"] and window.urls[0].startswith(seen["url"] + "/open?code=") and window.closed
    assert servers[0].window_seen and not (tmp_path / "home" / "app" / "extension").exists()
    assert port_free(seen["url"])


@CHROME
async def test_a_reload_doesnt_end_it(fake_claude, tmp_path, window, monkeypatch, servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    monkeypatch.setattr(run, "WINDOW_GRACE", 1)
    stop, seen, jobs = asyncio.Event(), {}, []

    async def check(page):
        await page("location.reload(); true")
        await asyncio.sleep(2.5)  # more than twice the grace
        seen["running"], seen["windows"] = not running.done(), servers[0].window_count
        stop.set()

    async def ready(url, opened):
        page = await window.page()
        assert await until(page, connected("/home"))
        jobs.append(asyncio.create_task(check(page)))

    running = asyncio.create_task(run.run_app(tmp_path / "home", claude=runner, ready=ready, stop=stop, out=quiet,
                                              launcher=lambda setting: window))
    assert await asyncio.wait_for(running, 60) == 0 and seen["running"] and seen["windows"] == 1


@CHROME
async def test_switching_tabs_never_ends_it_and_closing_the_window_does(fake_claude, tmp_path, window, monkeypatch,
                                                                       servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    monkeypatch.setattr(run, "WINDOW_GRACE", 1)
    seen, jobs = {}, []

    async def check(page):
        for key in ("/mission", "/settings", "/home", "/mission"):  # every tab's page is the window's
            await pick(page, key)
            assert await until(page, connected(key))
        await asyncio.sleep(2.5)  # more than twice the grace
        seen["alive"], seen["windows"] = not running.done(), servers[0].window_count
        await window.cdp.send("Target.closeTarget", {"targetId": window.targets[0]})  # the user closes the window
        seen["closed_at"] = time.monotonic()

    async def ready(url, opened):
        page = await window.page()
        assert await until(page, connected("/home"))
        jobs.append(asyncio.create_task(check(page)))

    running = asyncio.create_task(run.run_app(tmp_path / "home", claude=runner, ready=ready, out=quiet,
                                              launcher=lambda setting: window))
    assert await asyncio.wait_for(running, 60) == 0 and seen["alive"] and seen["windows"] == 3
    assert time.monotonic() - seen["closed_at"] < run.WINDOW_GRACE + 2


class Nothing:
    """A window whose page never connects (its browser started, and nothing else happened)."""
    id, name, note = "chrome", "Google Chrome", ""

    def __init__(self):
        self.launched, self.closed = [], False

    def launch(self, url):
        self.launched.append(url)

    def close(self):
        self.closed = True
        return ""


async def test_a_window_that_never_connects_ends_the_start(fake_claude, tmp_path, monkeypatch):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    monkeypatch.setattr(run, "WINDOW_START_WAIT", 1)
    nothing, lines = Nothing(), []
    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, out=lines.append,
                                              launcher=lambda setting: nothing), 30)
    assert code == 1 and nothing.launched and nothing.closed
    assert ("AI Browser's window didn't open: Google Chrome started, but the page never connected. Try again, or pick "
            "another browser with `ai-browser app --window brave`") in lines


async def test_stop_before_the_window_connects_still_closes_it(fake_claude, tmp_path):  # Review Focus 1
    from ai_browser.app import run

    runner, _, _ = fake_claude
    nothing, lines, stop = Nothing(), [], asyncio.Event()
    asyncio.get_running_loop().call_later(1, stop.set)  # Ctrl-C while the window is still opening
    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, stop=stop, out=lines.append,
                                              launcher=lambda setting: nothing), 30)
    assert code == 0 and nothing.launched and nothing.closed
    assert not any("didn't open" in line for line in lines)


async def test_no_browser_for_the_window_is_said_plainly(fake_claude, tmp_path):
    from ai_browser.app import run
    from ai_browser.app.window import NO_BROWSER, WindowError

    runner, _, _ = fake_claude
    lines = []

    def launcher(setting):
        raise WindowError(NO_BROWSER)

    assert await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, out=lines.append,
                                              launcher=launcher), 30) == 1
    assert f"error: {NO_BROWSER}" in lines and not (tmp_path / "home" / "app" / "link.json").exists()


async def test_the_setting_picks_the_window_and_window_overrides_it_once(fake_claude, tmp_path):
    from ai_browser.app import run
    from ai_browser.app.window import WindowError
    from ai_browser.settings import Settings, read_settings

    runner, _, _ = fake_claude
    home, asked = tmp_path / "home", []
    Settings(home).set("window_browser", "brave")

    def launcher(setting):
        asked.append(setting)
        raise WindowError("no window in this test")

    assert await run.run_app(home, claude=runner, out=quiet, launcher=launcher) == 1
    assert await run.run_app(home, claude=runner, out=quiet, launcher=launcher, window_browser="chrome") == 1
    assert asked == ["brave", "chrome"] and read_settings(home)["window_browser"] == "brave"  # --window saves nothing
    lines = []
    assert await run.run_app(home, out=lines.append, window_browser="firefox", launcher=launcher) == 1
    assert lines == ["error: --window must be auto, chrome, brave or edge, not 'firefox'"]


async def test_the_window_notes_are_printed(fake_claude, tmp_path, servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    note = "Brave isn't installed: the window uses Google Chrome. Change it in Settings."
    handed = "AI Browser's window was opened by a browser already running on its profile: quit it yourself (⌘Q)"
    window, lines, stop = SocketWindow(servers, note=note, close_note=handed), [], asyncio.Event()
    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, ready=lambda url, opened: stop.set(),
                                              stop=stop, out=lines.append, launcher=lambda setting: window), 60)
    assert code == 0 and note in lines and lines[-1] == handed and window.closed
    assert servers[0].window_info["using"] == "chrome" and servers[0].window_info["note"] == note


async def test_the_retired_ai_browser_choice_is_refused(tmp_path, monkeypatch):
    from ai_browser.app.run import RETIRED_APP, run_app

    launched = []
    for browser, env in (("app", None), (" APP ", None), (None, "app")):
        if env:
            monkeypatch.setenv("AIB_APP_BROWSER", env)
        lines = []
        assert await run_app(tmp_path / "home", browser=browser, out=lines.append, launcher=launched.append) == 1
        assert lines == [f"error: {RETIRED_APP}"]
    assert launched == [] and RETIRED_APP == (
        "AI Browser's own Chrome is gone: agents browse in your browser (Brave or Chrome). Drop --browser app (and "
        "AIB_APP_BROWSER).")


def test_agents_always_browse_in_the_users_browser(tmp_path, monkeypatch):
    from ai_browser.app.run import RETIRED_APP, app_browser, brave_env

    monkeypatch.delenv("AIB_APP_BROWSER", raising=False)
    monkeypatch.setenv("AIB_CHROME_DIR", str(tmp_path / "missing"))
    assert app_browser() == "brave"  # no browser folder: still the user's browser, never AI Browser's own
    assert app_browser(" Brave ") == "brave"
    with pytest.raises(ValueError) as refused:
        app_browser("app")
    assert str(refused.value) == RETIRED_APP
    with pytest.raises(ValueError, match="--browser must be brave, not 'firefox'"):
        app_browser("firefox")
    assert brave_env(tmp_path) == {"AIB_BROWSER": "chrome", "AIB_CHROME_DIR": str(tmp_path)}


async def test_a_bad_browser_choice_is_refused(tmp_path):
    from ai_browser.app.run import run_app

    lines = []
    assert await run_app(tmp_path / "home", browser="firefox", out=lines.append) == 1
    assert lines == ["error: --browser must be brave, not 'firefox'"]


async def test_brave_the_relay_and_the_windows_origin_are_wired(fake_claude, tmp_path, monkeypatch, servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    folder.mkdir(parents=True)  # Brave is installed; its switch is off
    monkeypatch.setenv("AIB_CHROME_DIR", str(folder))
    home, lines, seen, stop = tmp_path / "home", [], {}, asyncio.Event()

    async def ready(url, opened):
        link = home / "app" / "link.json"
        seen["mode"], seen["link"], seen["url"] = file_mode(link), json.loads(link.read_text(encoding="utf-8")), url
        seen["env"] = dict(servers[0].agents.env)
        async with ui_socket(servers[0], url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "home"}))
            seen["browser"] = json.loads(await asyncio.wait_for(ws.recv(), 10))["browser"]
            for request in ("r1", "r2"):
                await ws.send(json.dumps({"type": "new_task", "text": "look around", "request": request}))
            created = 0
            while created < 2:
                if json.loads(await asyncio.wait_for(ws.recv(), 10))["type"] == "created":
                    created += 1
        for agent in ("a1", "a2"):
            mcp = home / "app" / "agents" / agent / "mcp.json"
            for _ in range(100):
                if mcp.exists():
                    break
                await asyncio.sleep(0.1)
            seen[agent] = json.loads(mcp.read_text(encoding="utf-8"))["mcpServers"]["ai-browser"]["env"]
        stop.set()

    code = await asyncio.wait_for(run.run_app(home, claude=runner, ready=ready, stop=stop, out=lines.append,
                                              launcher=lambda setting: SocketWindow(servers)), 60)
    url = seen["url"]
    cdp = url.replace("http://", "ws://", 1) + "/cdp"
    assert code == 0 and seen["mode"] in (0o600, None)
    assert seen["link"] == {"events": url + "/agent-events", "session_token": seen["link"]["session_token"],
                            "pid": os.getpid(), "cdp": cdp, "browser_dir": str(folder)}
    assert seen["browser"] == {"kind": "brave", "name": "Brave", "state": "off", "groups": "no_watcher"}
    env = seen["env"]
    assert (env["AIB_APP_ORIGIN"], env["AIB_APP_CDP"], env["AIB_BROWSER"], env["AIB_CHROME_DIR"]) == (
        url, cdp, "chrome", str(folder))
    assert not {"AIB_APP_PROFILE", "AIB_APP_EXTENSION", "AIB_APP_AGENT_TOKEN"} & set(env)  # each agent has its own
    for agent in ("a1", "a2"):
        agent_env = seen[agent]
        assert (agent_env["AIB_APP_ORIGIN"], agent_env["AIB_APP_CDP"], agent_env["AIB_BROWSER"],
                agent_env["AIB_CHROME_DIR"]) == (url, cdp, "chrome", str(folder))
    tokens = {seen["a1"]["AIB_APP_AGENT_TOKEN"], seen["a2"]["AIB_APP_AGENT_TOKEN"]}
    assert len(tokens) == 2 and seen["link"]["session_token"] not in tokens  # each agent its own
    printed = "\n".join(lines)
    assert "brave://inspect/#remote-debugging" in printed and "asks once each time AI Browser starts" in printed
    assert "any program on this computer can reach your Brave" in printed
    assert not (home / "app" / "link.json").exists()  # removed at exit


def test_the_switch_text_says_once_per_run():
    from ai_browser.app.run import SWITCH

    text = " ".join(SWITCH.split())
    assert "asks once each time AI Browser starts" in text and "it isn't AI Browser" in text
    assert "lists everything connected, with Disconnect" in text
    assert "each agent first uses the browser" not in text


async def test_quitting_while_brave_asks_says_to_click_cancel(fake_claude, tmp_path, monkeypatch, servers):
    """Brave's question outlives the app that asked (app/cdprelay.py): an Allow after AI Browser has quit opens a
    connection nobody holds, and Brave's bar then stays until Brave restarts. So quitting while it asks says so."""
    from ai_browser.app import run
    from fake_brave import FakePort
    from fake_brave import until as settled

    runner, _, _ = fake_claude
    monkeypatch.setattr(run, "WINDOW_GRACE", 1)
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    port = FakePort(folder, answer="silent")  # the switch is on, and nobody answers Brave's question
    await port.start()
    monkeypatch.setenv("AIB_CHROME_DIR", str(folder))
    lines, window = [], SocketWindow(servers)

    async def ready(url, opened):
        assert await settled(lambda: port.sessions == 1)  # the app asked as it started
        await window.ws.close()  # the user closes AI Browser's window while Brave still asks

    try:
        code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, ready=ready, out=lines.append,
                                                  launcher=lambda setting: window), 60)
    finally:
        await port.stop()
    assert code == 0 and port.sessions == 1
    assert any('Brave is still showing "Allow remote debugging?"' in line and "click Cancel" in line
               for line in lines), lines


async def test_brave_mode_gives_the_link_the_watchers_id(fake_claude, tmp_path, monkeypatch, servers):
    from ai_browser.app import run
    from ai_browser.extension_id import extension_id_for

    runner, _, _ = fake_claude
    home, made, stop = tmp_path / "home", [], asyncio.Event()
    real = run.BraveLink

    def recording(*args, **kwargs):
        link = real(*args, **kwargs)
        made.append(link)
        return link

    monkeypatch.setattr(run, "BraveLink", recording)
    code = await asyncio.wait_for(run.run_app(home, claude=runner, ready=lambda url, opened: stop.set(), stop=stop,
                                              out=quiet, launcher=lambda setting: SocketWindow(servers)), 60)
    assert code == 0 and len(made) == 1
    assert made[0].watcher_id == extension_id_for(home / "app" / "watcher") != ""  # the id the app allows
    assert made[0].app_origin == servers[0].origin  # a copy of our pages in Brave is never one of the user's tabs


async def test_the_watchers_steps_show_the_path_the_id_is_hashed_from(fake_claude, tmp_path, monkeypatch, servers):
    from conftest import symlink_or_skip

    from ai_browser.app import run
    from ai_browser.extension_id import extension_id_for, extension_path

    runner, _, _ = fake_claude
    real = tmp_path / "real"
    real.mkdir()
    if os.name == "nt":  # a junction needs no rights; Brave doesn't resolve it
        import _winapi

        _winapi.CreateJunction(str(real), str(tmp_path / "link"))
    else:
        symlink_or_skip(real, tmp_path / "link")
    home = tmp_path / "link" / "home"
    folder = home / "app" / "watcher"
    lines, shown, stop = [], [], asyncio.Event()
    monkeypatch.setattr(run, "reveal", shown.append)
    code = await asyncio.wait_for(run.run_app(home, claude=runner, ready=lambda url, opened: stop.set(), stop=stop,
                                              out=lines.append, launcher=lambda setting: SocketWindow(servers)), 60)
    expected = extension_path(folder)
    assert code == 0 and shown == [expected] and expected in "\n".join(lines)
    assert extension_id_for(expected) == extension_id_for(folder)
    if os.name == "nt":
        assert expected == str(folder)  # the junction's path, as Brave sees it, not the resolved one


async def test_the_window_closes_first_and_the_relay_last(fake_claude, tmp_path, monkeypatch, servers):
    from ai_browser.app import run
    from ai_browser.app.bravelink import BraveLink
    from ai_browser.app.server import AppServer

    runner, _, _ = fake_claude
    order, stop = [], asyncio.Event()
    window = SocketWindow(servers)
    real_close, real_unlink = window.close, run.platforms.unlink

    async def close():
        order.append("window")
        return await real_close()

    def unlink(path, missing_ok=False):
        if Path(path).name == "link.json":
            order.append("link")
        return real_unlink(path, missing_ok=missing_ok)

    async def server_stop(self, original=AppServer.stop):
        order.append("server")
        await original(self)

    async def brave_close(self, original=BraveLink.close):
        order.append("brave")
        await original(self)

    window.close = close
    monkeypatch.setattr(run.platforms, "unlink", unlink)
    monkeypatch.setattr(AppServer, "stop", server_stop)
    monkeypatch.setattr(BraveLink, "close", brave_close)
    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, ready=lambda url, opened: stop.set(),
                                              stop=stop, out=quiet, launcher=lambda setting: window), 60)
    assert code == 0 and order == ["window", "link", "server", "brave"]  # no agent sees its browser vanish first


async def test_a_second_run_changes_nothing_for_the_running_one(fake_claude, tmp_path, servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    home, seen, stop = tmp_path / "home", {}, asyncio.Event()

    def files():
        return {name: (home / "app" / name).read_bytes() for name in ("link.json", "port")} | {
            "watcher": (home / "app" / "watcher" / "config.json").read_bytes()}

    async def ready(url, opened):
        before, lines = files(), []
        seen["code"] = await run.run_app(home, claude=runner, out=lines.append,
                                         launcher=lambda setting: pytest.fail("a second window"))
        seen["lines"], seen["unchanged"] = lines, files() == before
        stop.set()

    code = await asyncio.wait_for(run.run_app(home, claude=runner, ready=ready, stop=stop, out=quiet,
                                              launcher=lambda setting: SocketWindow(servers)), 60)
    assert code == 0 and seen["code"] == 1 and seen["unchanged"]
    assert any(line.startswith("error: AI Browser is already running: its window is open (look for it in")
               for line in seen["lines"])


async def test_first_start_shows_the_watchers_steps_once(fake_claude, tmp_path, monkeypatch, servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    shown, lines, home = [], [], tmp_path / "home"
    monkeypatch.setattr(run, "reveal", shown.append)
    for _ in range(2):
        stop = asyncio.Event()
        code = await asyncio.wait_for(run.run_app(home, claude=runner, ready=lambda url, opened: stop.set(),
                                                  stop=stop, out=lines.append,
                                                  launcher=lambda setting: SocketWindow(servers)), 60)
        assert code == 0
    watcher = os.path.realpath(home / "app" / "watcher")
    printed = "\n".join(lines)
    assert shown == [watcher]  # the folder window once; the printed steps until the watcher is set up
    assert printed.count("brave://extensions") == 2 and "Type ai and a space in Brave's address bar" in printed


async def test_the_brain_survives_a_restart(fake_claude, tmp_path, servers):
    from ai_browser.app import run
    from ai_browser.brain.store import BrainStore, Item

    runner, _, _ = fake_claude
    home, seen, stop = tmp_path / "home", {}, asyncio.Event()
    BrainStore(home).put(Item(id="gmail:t1", site="gmail", raw_id="t1", sender="Maria", subject="Launch",
                              kind="needs_reply", summary="Move the launch?"))

    async def ready(url, opened):
        async with ui_socket(servers[0], url) as ws:
            await ws.send(json.dumps({"type": "brain"}))
            while "snapshot" not in seen:
                message = json.loads(await asyncio.wait_for(ws.recv(), 10))
                if message["type"] == "brain_snapshot":
                    seen["snapshot"] = message
        stop.set()

    code = await asyncio.wait_for(run.run_app(home, claude=runner, ready=ready, stop=stop, out=quiet,
                                              launcher=lambda setting: SocketWindow(servers)), 60)
    assert code == 0 and [item["id"] for item in seen["snapshot"]["items"]] == ["gmail:t1"]


async def test_scheduled_workflows_tick_while_the_app_runs(fake_claude, tmp_path, monkeypatch, servers):
    from ai_browser.app import run
    from ai_browser.brain import workflows as workflow_module
    from ai_browser.brain.workflows import WorkflowStore
    from test_bridge import EVENTS

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    home, seen, stop = tmp_path / "home", {}, asyncio.Event()
    WorkflowStore(home).save({"name": "Hourly check", "instructions": "Check the sites and tell me what changed",
                              "trigger": "schedule", "schedule": "every 15m"})
    clock = [1_000_000.0]
    monkeypatch.setattr(workflow_module, "_now", lambda: clock[0])
    monkeypatch.setattr(run, "TICK", 0.1)

    def users():
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if '"type": "user"' in line]

    async def ready(url, opened):
        await asyncio.sleep(0.5)  # the first tick starts the schedule's clock: nothing missed is caught up
        assert users() == []
        clock[0] += 16 * 60
        for _ in range(100):
            if users():
                break
            await asyncio.sleep(0.1)
        seen["users"] = users()
        stop.set()

    code = await asyncio.wait_for(run.run_app(home, claude=runner, ready=ready, stop=stop, out=quiet,
                                              launcher=lambda setting: SocketWindow(servers)), 60)
    assert code == 0 and seen["users"][0]["message"]["content"].startswith("Check the sites and tell me what changed")


async def test_the_app_can_hear_with_its_models_folder(fake_claude, tmp_path, servers):
    from ai_browser.app import run

    runner, _, _ = fake_claude
    seen, stop = {}, asyncio.Event()

    async def ready(url, opened):
        async with ui_socket(servers[0], url) as ws:
            await ws.send(json.dumps({"type": "hearing"}))
            while (message := json.loads(await asyncio.wait_for(ws.recv(), 10)))["type"] != "hearing_status":
                pass
            seen["status"] = message
        stop.set()

    code = await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, ready=ready, stop=stop, out=quiet,
                                              launcher=lambda setting: SocketWindow(servers)), 60)
    status = seen["status"]
    assert code == 0 and status["folder"] == str(tmp_path / "home" / "models" / "faster-whisper-base.en")
    assert status["size_bytes"] == 147_769_510 and status["model"] == "Whisper base.en"
    assert status["state"] in ("no_engine", "no_model")  # never ready by itself: the model comes only on Download


def test_the_terminal_texts_name_no_extension_and_no_panel():
    from ai_browser.app.run import brave_text, ready_text

    expected = ("AI Browser is open in its own window: AI Home shows every agent, tab and skill.\n"
                "With the watcher in Brave, type ai and a space in Brave's address bar to start a task from there.\n"
                "Close the window, or press Ctrl-C here, to stop.")
    assert ready_text("darwin") == ready_text("win32") == expected
    for system, folder in (("darwin", "/x/watcher"), ("win32", "C:\\Users\\me\\.ai-browser\\app\\watcher")):
        for text in (ready_text(system), brave_text(folder, system)):
            assert "⌘⇧Y" not in text and "Ctrl+Shift+Y" not in text and "chrome://extensions" not in text
            assert "Pin the AI Browser icon" not in text
        assert "4. Type ai and a space in Brave's address bar to start a task" in brave_text(folder, system)
    windows = brave_text("C:\\Users\\me\\.ai-browser\\app\\watcher", "win32")
    assert "address bar at the top of the folder window" in windows and "⌘" not in windows
    assert "⌘⇧G" in brave_text("/x/watcher", "darwin")
