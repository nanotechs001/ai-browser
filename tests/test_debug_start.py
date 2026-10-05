"""AIB_DEBUG_START=1 (ai_browser/debugstart.py): `ai-browser app` says each step of its start on stderr, each line
starting "[start] ", for the Windows build's start check (packaging/windows_app.py start). It is off by default, and
on it adds those lines and changes nothing else. No line ever holds a cookie's value or a start code: names, paths,
and yes or no only. AI Browser's own app keeps its side in its profile (main.js, test_desktop_js)."""

import asyncio
import contextlib

import pytest

from fake_desktop import FakeDesktop
from fake_window import SocketWindow
from test_app_run import servers  # noqa: F401  (a fixture)
from test_app_server import fetch, started
from test_bridge import EVENTS
from test_desktop_launch import URL, windows_app
from ui_socket import ui_cookie, ui_socket


def start_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("[start] ")]


async def walk(server, url) -> str:
    """What a window does as it starts: its code swapped (and used again), the tab menu without and with the cookie,
    a socket with the cookie and one without. The code."""
    code = server.new_launch_code()
    await fetch("GET", f"{url}/open", params={"code": code})
    await fetch("GET", f"{url}/open", params={"code": code})
    await fetch("GET", f"{url}/app")
    await fetch("GET", f"{url}/app", headers=ui_cookie(server))
    async with ui_socket(server, url):
        for _ in range(100):
            if server.window_seen:
                break
            await asyncio.sleep(0.05)
    with contextlib.suppress(Exception):
        async with ui_socket(server, url, cookie=False) as refused:
            await asyncio.wait_for(refused.recv(), 10)
    return code


async def test_the_start_log_is_off_by_default(fake_claude, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("AIB_DEBUG_START", raising=False)
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        await walk(server, url)
    finally:
        await server.stop()
    captured = capsys.readouterr()
    assert start_lines(captured.out + captured.err) == []


async def test_the_server_says_each_step_of_the_windows_start_and_never_a_secret(fake_claude, tmp_path, monkeypatch,
                                                                                capsys):
    monkeypatch.setenv("AIB_DEBUG_START", "1")
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        code = await walk(server, url)
    finally:
        await server.stop()
    err = capsys.readouterr().err
    name = f"aib_ui_{server.port}"
    assert start_lines(err) == [
        f"[start] GET /open: a valid start code: the window's cookie {name} is set",
        f"[start] GET /open: an unknown, used or expired start code, and no window cookie {name}",
        f"[start] GET /app: no window cookie {name} (cookies sent: none)",
        "[start] GET /app: the window's cookie is there",
        "[start] window socket connected (1 open)",
        "[start] socket refused: origin ok, host ok, window cookie missing",
    ]
    assert code not in err and server.ui_secret not in err


async def test_the_engine_says_each_step_of_the_apps_start(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AIB_DEBUG_START", "1")
    app, log = windows_app(tmp_path, monkeypatch)
    await app.launch(URL)
    pid = app.pid
    await app.close()
    err = capsys.readouterr().err
    lines = start_lines(err)
    assert lines[0].startswith("[start] app: starting ") and "fake_electron.py" in lines[0]
    assert lines[1:3] == ["[start] app: start sent (http://127.0.0.1:8793/open?code=…)",
                          f"[start] app: hello from pid {pid}"]
    assert lines[-1].startswith("[start] app: its line or its process ended")
    assert "the-one-time-code" not in err
    assert log.read_text(encoding="utf-8").splitlines()[0] == '{"argv": [], "electron_logging": "1"}'  # Chromium's log


async def test_an_app_that_never_says_hello_is_said_in_the_start_log(tmp_path, monkeypatch, capsys):
    from ai_browser.desktop import launch

    monkeypatch.setenv("AIB_DEBUG_START", "1")
    monkeypatch.setattr(launch, "START_WAIT", 1.0)
    app, _ = windows_app(tmp_path, monkeypatch, hello=False)
    with pytest.raises(launch.DesktopError):
        await app.launch(URL)
    assert "[start] app: no hello within 1 s: it is ended" in start_lines(capsys.readouterr().err)


async def test_the_run_says_which_window_draws_ai_browser(fake_claude, tmp_path, servers, monkeypatch,  # noqa: F811
                                                          capsys):
    from ai_browser.app import run
    from ai_browser.desktop.launch import DesktopError

    monkeypatch.setenv("AIB_DEBUG_START", "1")
    runner, _, _ = fake_claude
    app, stop = FakeDesktop(servers=servers), asyncio.Event()
    await asyncio.wait_for(run.run_app(tmp_path / "home", claude=runner, ready=lambda url, opened: stop.set(),
                                       stop=stop, out=lambda line: None, desktop=lambda home, shortcut: app), 60)
    assert "[start] window: AI Browser's own app" in start_lines(capsys.readouterr().err)

    failing = FakeDesktop(launch_error=DesktopError("AI Browser's app didn't answer as it started"))
    window, stop = SocketWindow(servers), asyncio.Event()
    await asyncio.wait_for(run.run_app(tmp_path / "home2", claude=runner, ready=lambda url, opened: stop.set(),
                                       stop=stop, out=lambda line: None, launcher=lambda setting: window,
                                       desktop=lambda home, shortcut: failing), 60)
    assert f"[start] window: a browser window ({window.name})" in start_lines(capsys.readouterr().err)
