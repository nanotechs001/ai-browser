"""Starting AI Browser's own app and its private line (desktop/launch.py). The app is a fake
(tests/fake_electron.py), and on macOS so is `open` (tests/fake_open.py), whose arguments are checked as
LaunchServices would get them. The one-time code goes over the line, never on a command line."""

import asyncio
import json
import sys
from pathlib import Path

import pytest

from conftest import fake_python

TESTS = Path(__file__).parent
URL = "http://127.0.0.1:8793/open?code=the-one-time-code"


def entries(log: Path) -> list[dict]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []


def plan(tmp_path, monkeypatch, **steps) -> Path:
    log = tmp_path / "app.log"
    monkeypatch.setenv("FAKE_ELECTRON_LOG", str(log))
    monkeypatch.setenv("FAKE_ELECTRON_PLAN", json.dumps(steps))
    return log


def windows_app(tmp_path, monkeypatch, **steps):
    """(the app as Windows starts it: its own program, the line on its stdin and stdout; the fake's log)."""
    from ai_browser.desktop.launch import DesktopWindow

    log = plan(tmp_path, monkeypatch, **steps)
    app = DesktopWindow(tmp_path / "home", "Alt+Space", system="win32",
                        program=[fake_python(), str(TESTS / "fake_electron.py")])
    return app, log


async def test_on_windows_the_line_is_the_apps_stdin_and_the_code_stays_off_every_command_line(tmp_path,
                                                                                                 monkeypatch):
    app, log = windows_app(tmp_path, monkeypatch, shortcuts={"Alt+Shift+Space": {"ok": False, "why": "taken"}})
    await app.launch(URL)
    try:
        assert app.pid is not None and app.running and not app.ended.is_set()
        assert await app.try_shortcut("Alt+Shift+Space") == {"value": "Alt+Shift+Space", "ok": False, "why": "taken",
                                                             "pressed": False}
        assert await app.try_shortcut(None) == {"value": None, "ok": True, "why": "", "pressed": False}
        assert app.shortcut["value"] is None  # what the app holds now: no shortcut
        assert app.send({"type": "notify", "id": "n1", "title": "An agent is waiting for you", "body": "…"})
    finally:
        assert await app.close() == ""
    assert app.ended.is_set() and not app.quit_by_user and not app.running
    seen = entries(log)
    assert seen[0] == {"argv": []}  # its command line: the program alone
    got = [entry["got"] for entry in seen[1:]]
    assert got[0] == {"type": "start", "open": URL, "shortcut": "Alt+Space"}  # the code: over the line only
    assert [message["type"] for message in got] == ["start", "shortcut", "shortcut", "notify", "quit"]


@pytest.mark.posix_only  # macOS's line is a socket in a folder; Windows' is stdin
async def test_on_macos_launchservices_starts_it_and_the_line_is_a_private_socket(tmp_path, monkeypatch):
    from ai_browser.desktop import layout
    from ai_browser.desktop.launch import DesktopWindow

    log = plan(tmp_path, monkeypatch)
    opened = tmp_path / "open.log"
    monkeypatch.setenv("FAKE_OPEN_LOG", str(opened))
    home = tmp_path / "home"
    bundle = layout.app_path(home, "darwin")
    bundle.mkdir(parents=True)  # the built app
    app = DesktopWindow(home, None, system="darwin", opener=[fake_python(), str(TESTS / "fake_open.py")])
    await app.launch(URL)
    try:
        [entry] = entries(opened)
        line = entry["argv"][-1].removeprefix("--aib-line=")
        assert entry["argv"] == ["-n", "-W", "-a", str(bundle), "--args", f"--aib-line={line}"]
        assert entry["folder_mode"] == 0o700  # only this user can open the line's folder
        assert not Path(line).exists() and not Path(line).parent.exists()  # taken once, then gone
        assert entries(log)[1]["got"] == {"type": "start", "open": URL, "shortcut": None}
    finally:
        await app.close()
    assert app.ended.is_set() and not app.running


async def test_the_apps_quit_ends_the_run_as_the_users(tmp_path, monkeypatch):
    app, _ = windows_app(tmp_path, monkeypatch, quit_after=0.3)
    await app.launch(URL)
    await asyncio.wait_for(app.ended.wait(), 10)
    assert app.quit_by_user
    assert await app.close() == ""


async def test_what_the_app_says_unasked_reaches_the_engine(tmp_path, monkeypatch):
    app, _ = windows_app(tmp_path, monkeypatch, start_status={"ok": False, "why": "taken"}, click=True)
    heard = []
    app.on_message = heard.append
    await app.launch(URL)
    try:
        app.send({"type": "notify", "id": "n7", "title": "A bot check on example.com", "body": "…"})
        for _ in range(100):
            if len(heard) >= 2:
                break
            await asyncio.sleep(0.05)
    finally:
        await app.close()
    assert heard == [{"type": "shortcut", "value": "Alt+Space", "ok": False, "why": "taken", "pressed": False},
                     {"type": "clicked", "id": "n7"}]
    assert app.shortcut == {"value": "Alt+Space", "ok": False, "why": "taken", "pressed": False}


async def test_an_app_that_never_says_hello_is_ended_and_said_plainly(tmp_path, monkeypatch):
    from ai_browser.desktop import launch

    monkeypatch.setattr(launch, "START_WAIT", 1.0)
    app, _ = windows_app(tmp_path, monkeypatch, hello=False)
    with pytest.raises(launch.DesktopError) as error:
        await app.launch(URL)
    assert str(error.value) == "AI Browser's app didn't answer as it started"
    assert app.ended.is_set() and not app.running  # nothing is left running


async def test_a_program_that_isnt_there_is_said_plainly(tmp_path):
    from ai_browser.desktop.launch import DesktopError, DesktopWindow

    app = DesktopWindow(tmp_path / "home", None, system="win32", program=[str(tmp_path / "missing.exe")])
    with pytest.raises(DesktopError, match="^AI Browser's app could not start: "):
        await app.launch(URL)
    assert app.ended.is_set()


@pytest.mark.posix_only
async def test_a_line_that_cant_be_made_is_said_plainly_and_leaves_nothing(tmp_path, monkeypatch):
    from ai_browser.desktop import launch, layout

    home = tmp_path / "home"
    layout.app_path(home, "darwin").mkdir(parents=True)
    deep = tmp_path / ("a-temporary-folder-too-deep-for-a-socket-" * 3)  # past AF_UNIX's 104 bytes (108 on Linux)
    deep.mkdir()
    monkeypatch.setattr(launch.tempfile, "tempdir", str(deep))  # what a long TMPDIR does
    monkeypatch.setenv("FAKE_OPEN_LOG", str(tmp_path / "open.log"))
    app = launch.DesktopWindow(home, None, system="darwin", opener=[fake_python(), str(TESTS / "fake_open.py")])
    with pytest.raises(launch.DesktopError, match="^AI Browser's app could not start: "):
        await app.launch(URL)
    assert app.ended.is_set() and not app.running and list(deep.iterdir()) == []  # no line's folder left behind
    assert not (tmp_path / "open.log").exists()  # nothing was opened


async def test_a_stale_app_is_built_again_before_it_starts(tmp_path, monkeypatch):  # Review Focus 5
    from ai_browser.desktop import launch

    built = []
    monkeypatch.setattr(launch, "stale", lambda home, system=None: True)
    monkeypatch.setattr(launch, "refresh", lambda home, system=None: built.append((home, system)))
    app, _ = windows_app(tmp_path, monkeypatch)
    await app.launch(URL)
    await app.close()
    assert built == [(tmp_path / "home", "win32")] and app.note == ""  # the microphone's note is the Mac's

    def failing(home, system=None):
        raise launch.SetupError("macOS couldn't sign AI Browser's app: test")

    monkeypatch.setattr(launch, "refresh", failing)
    again, _ = windows_app(tmp_path, monkeypatch)
    with pytest.raises(launch.DesktopError) as error:
        await again.launch(URL)
    assert str(error.value) == "AI Browser's app couldn't be updated: macOS couldn't sign AI Browser's app: test"
    assert not again.running  # never started: run_app opens a browser window instead


def test_the_app_is_used_only_once_it_is_built_here(tmp_path):
    from ai_browser.desktop import layout
    from ai_browser.desktop.launch import DesktopWindow, default_desktop

    home = tmp_path / "home"
    assert default_desktop(home, "Alt+Space") is None
    program = layout.executable(layout.app_path(home))
    program.parent.mkdir(parents=True)
    program.write_bytes(b"")
    layout.write_stamp(home, {"electron": "44.5.1", "system": sys.platform, "arch": "", "layer": "x"})
    found = default_desktop(home, "Alt+Shift+Space")
    assert isinstance(found, DesktopWindow) and found.start_shortcut == "Alt+Shift+Space"
    assert (found.id, found.name, found.note) == ("desktop", "AI Browser", "")


def first_answer(url: str) -> int:
    """The status the server gives a start address, without following its redirect."""
    import http.client
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=10)
    try:
        connection.request("GET", f"{parts.path}?{parts.query}")
        return connection.getresponse().status
    finally:
        connection.close()


async def test_the_start_code_is_made_after_a_slow_rebuild(fake_claude, tmp_path, monkeypatch):
    import time

    from ai_browser.app import run
    from ai_browser.app import server as server_module
    from ai_browser.desktop import launch
    from test_app_server import started
    from test_bridge import EVENTS

    server, url = await started(fake_claude, tmp_path, EVENTS)
    log = plan(tmp_path, monkeypatch)
    monkeypatch.setattr(server_module, "CODE_TTL", 1)  # a start code lives 1 s here (60 s in the product)
    monkeypatch.setattr(launch, "stale", lambda home, system=None: True)  # a pull changed AI Browser's part,
    monkeypatch.setattr(launch, "refresh", lambda home, system=None: time.sleep(1.5))  # and the rebuild is slower
    app = launch.DesktopWindow(server.home, None, system="win32",
                               program=[fake_python(), str(TESTS / "fake_electron.py")])
    try:
        assert await run._open_app(server.home, server, url, lambda home, shortcut: app, None, lambda line: None) is app
        start = next(entry["got"] for entry in entries(log) if "got" in entry)
        assert start["open"].startswith(url + "/open?code=")
        assert await asyncio.to_thread(first_answer, start["open"]) == 303  # still good: made after the rebuild
    finally:
        await app.close()
        await server.stop()
