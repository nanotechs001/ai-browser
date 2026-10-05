from pathlib import Path

import pytest

from ai_browser.cli import main

BENCH_ROWS = ["observe", "observe heavy page", "click step", "type step", "open local page", "screenshot"]


def test_help_lists_every_command(capsys):
    with pytest.raises(SystemExit) as exited:
        main(["--help"])
    assert exited.value.code == 0
    out = capsys.readouterr().out
    for command in ("mcp", "build", "doctor", "bench", "live", "stop", "app"):
        assert command in out


def test_stop_rejects_a_bad_profile_name(capsys):
    assert main(["stop", "Bad Name!"]) == 2
    assert "profile" in capsys.readouterr().err


@pytest.mark.docker
def test_doctor_passes(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AIB_HOME", str(tmp_path))
    code = main(["doctor"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "✗" not in out
    for check in ("Docker", "image", "sandbox", "page read", "screenshot", "skills", "live view"):
        assert check in out


def test_doctor_chrome_explains_when_remote_debugging_is_off(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AIB_CHROME_DIR", str(tmp_path))
    monkeypatch.setenv("AIB_HOME", str(tmp_path / "home"))
    assert main(["doctor", "--chrome"]) == 1
    out = capsys.readouterr().out
    assert "✗ Chrome" in out and "chrome://inspect/#remote-debugging" in out


def test_doctor_chrome_passes_with_a_reachable_chrome(tmp_path, monkeypatch, capsys):
    from ai_browser.chrome import chrome_binary, find_ws_url, launch

    if chrome_binary() is None:
        pytest.skip("Google Chrome is not installed")
    folder = tmp_path / "chrome-profile"
    process = launch(folder, headless=True)
    try:
        find_ws_url(folder, timeout=20)  # wait until the throwaway Chrome is up
        monkeypatch.setenv("AIB_CHROME_DIR", str(folder))
        monkeypatch.setenv("AIB_HOME", str(tmp_path / "home"))
        code = main(["doctor", "--chrome"])
        out = capsys.readouterr().out
        assert code == 0, out
        assert "✓ Chrome" in out and "✓ page read" in out
    finally:
        process.terminate()
        process.wait(timeout=15)


@pytest.mark.docker
def test_bench_prints_every_measurement(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AIB_HOME", str(tmp_path))
    main(["bench", "--runs", "3"])
    out = capsys.readouterr().out
    for row in BENCH_ROWS:
        assert any(line.startswith(row + " ") for line in out.splitlines()), out


def test_doctor_own_names_brave(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    folder.mkdir(parents=True)
    monkeypatch.setenv("AIB_CHROME_DIR", str(folder))
    monkeypatch.setenv("AIB_HOME", str(tmp_path / "home"))
    assert main(["doctor", "--own"]) == 1
    out = capsys.readouterr().out
    assert "✗ Brave" in out and "brave://inspect/#remote-debugging" in out


def test_the_mcp_example_needs_no_browser_folder():
    import json

    from ai_browser.config import project_root

    example = json.loads((project_root() / ".mcp.json.example").read_text(encoding="utf-8"))
    assert "AIB_CHROME_DIR" not in example["mcpServers"]["ai-browser"].get("env", {})  # found by itself (Brave first)


def _browser_port_stand_in():
    """A local socket in place of a browser's debugging port: it records each connection and the bytes sent."""
    import socket
    import threading

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    seen = {"connections": 0, "bytes": b""}

    def serve():
        while True:
            try:
                connection, _ = server.accept()
            except OSError:
                return
            with connection:
                seen["connections"] += 1
                connection.settimeout(1)
                try:
                    while chunk := connection.recv(1024):
                        seen["bytes"] += chunk
                except OSError:
                    pass

    threading.Thread(target=serve, daemon=True).start()
    return server, seen


def _setup_env(tmp_path, monkeypatch, port) -> dict:
    claude, chrome, profile = tmp_path / "claude-bin", tmp_path / "chrome-bin", tmp_path / "everyday"
    claude.write_bytes(b"")
    chrome.write_bytes(b"")
    profile.mkdir()
    (profile / "DevToolsActivePort").write_text(f"{port}\n/devtools/browser/x\n", encoding="utf-8")
    env = {"AIB_CLAUDE": str(claude), "AIB_CHROME_BINARY": str(chrome), "AIB_CHROME_DIR": str(profile),
           "AIB_HOME": str(tmp_path / "aib-home")}  # never the user's own config.json
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env


def test_doctor_setup_checks_without_docker_or_a_browser_connection(tmp_path, monkeypatch, capsys):
    import time

    server, seen = _browser_port_stand_in()
    try:
        _setup_env(tmp_path, monkeypatch, server.getsockname()[1])
        code = main(["doctor", "--setup"])
        for _ in range(20):
            if seen["connections"]:
                break
            time.sleep(0.1)
    finally:
        server.close()
    out = capsys.readouterr().out
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith("✓ Python      3.")
    assert lines[1] == f"✓ Claude Code {tmp_path / 'claude-bin'}"
    assert lines[2] == f"✓ window      Google Chrome (Auto) {tmp_path / 'chrome-bin'}"
    assert lines[3] == f"✓ Chrome      {tmp_path / 'chrome-bin'}"  # information now: agents may browse in it
    assert lines[4].startswith(("✓ Brave", "- Brave"))  # information only
    assert lines[5].startswith("✓ everyday") and "remote debugging is on" in lines[5]
    assert lines[6] == "✓ ports       app 8792-8811 and live view 8770-8790 have free ports"
    assert lines[7] == "- Docker      not checked here: run `uv run ai-browser doctor`"
    assert lines[-1] == "all good"
    assert seen["connections"] >= 1 and seen["bytes"] == b""  # a TCP check only: no DevTools request, so no Allow


def test_doctor_setup_says_when_config_json_cant_be_used(tmp_path, monkeypatch, capsys):
    server, _ = _browser_port_stand_in()
    try:
        env = _setup_env(tmp_path, monkeypatch, server.getsockname()[1])
        Path(env["AIB_HOME"]).mkdir()
        (Path(env["AIB_HOME"]) / "config.json").write_text('{"blocked_skills": ["ecc:x"],}', encoding="utf-8")
        code = main(["doctor", "--setup"])
    finally:
        server.close()
    out = capsys.readouterr().out
    assert code == 1, out  # the skills the user blocked aren't blocked: not "all good"
    line = next((line for line in out.splitlines() if line.startswith("✗ config")), out)
    assert str(Path(env["AIB_HOME"]) / "config.json") in line and "defaults" in line
    assert out.splitlines()[-1] == "some checks failed"


def test_doctor_setup_fails_without_claude_code_or_a_window_browser(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AIB_CLAUDE", str(tmp_path / "no-claude"))
    monkeypatch.setenv("AIB_CHROME_BINARY", str(tmp_path / "no-chrome"))
    assert main(["doctor", "--setup"]) == 1
    out = capsys.readouterr().out
    assert "✗ Claude Code" in out and "✗ window" in out and "AIB_CHROME_BINARY" in out
    assert "AI Browser needs Google Chrome, Brave or Microsoft Edge to draw its window" in out
    assert out.splitlines()[-1] == "some checks failed"


def test_doctor_setup_prints_its_marks_on_any_console(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys

    server, _ = _browser_port_stand_in()
    try:
        _setup_env(tmp_path, monkeypatch, server.getsockname()[1])
        env = {**os.environ, "PYTHONIOENCODING": "ascii"}  # a console or file that can't hold ✓, as cp1252 can't
        env["HOME"] = str(tmp_path / "user-home")  # detection (the window line) never reads the user's LaunchServices
        env.pop("PYTHONUTF8", None)
        result = subprocess.run([sys.executable, "-m", "ai_browser.cli", "doctor", "--setup"], env=env,
                                capture_output=True, timeout=60)
    finally:
        server.close()
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert "✓ Python" in result.stdout.decode("utf-8")


def test_app_help_offers_the_window_and_brave_only(capsys):
    with pytest.raises(SystemExit) as exited:
        main(["app", "--help"])
    assert exited.value.code == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "--window {auto,chrome,brave,edge}" in out and "--browser {brave}" in out
    assert "--headless" not in out and "side panel" not in out


def test_app_hands_its_choices_to_run_app(monkeypatch):
    import ai_browser.app.run as run

    seen = {}

    async def fake_run_app(home, model="sonnet", **options):
        seen.update(model=model, **options)
        return 0

    monkeypatch.setattr(run, "run_app", fake_run_app)
    assert main(["app", "--model", "haiku", "--window", "brave", "--browser", "brave"]) == 0
    assert seen == {"model": "haiku", "browser": "brave", "window_browser": "brave"}


@pytest.fixture
def double_clicked(monkeypatch):
    """AI Browser.exe, the packaged Windows build (packaging/), started by a double-click: no command. `ended` is
    what its app run returns; `runs` and `asked` record the runs and the questions asked at the console."""
    import sys

    import ai_browser.app.run as run
    import ai_browser.cli as cli

    world = {"ended": 0, "runs": [], "asked": []}

    async def fake_run_app(home, model="sonnet", **options):
        world["runs"].append({"model": model, **options})
        return world["ended"]

    monkeypatch.setattr(run, "run_app", fake_run_app)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    monkeypatch.setattr(cli, "_ask", lambda question: world["asked"].append(question) or "")
    return world


def test_the_packaged_exe_with_no_command_opens_the_app(double_clicked):
    assert main([]) == 0
    assert double_clicked["runs"] == [{"model": "sonnet", "browser": None, "window_browser": None}]
    assert double_clicked["asked"] == []  # the app's own Quit closes the console window with it


def test_the_packaged_exe_keeps_its_window_open_when_the_app_cant_start(double_clicked):
    double_clicked["ended"] = 1  # for example: AI Browser is already running
    assert main([]) == 1
    assert double_clicked["asked"] == ["AI Browser stopped (see above). Press Enter to close this window."]


def test_the_packaged_exe_runs_the_command_it_is_given(double_clicked, capsys):
    assert main(["stop", "Bad Name!"]) == 2
    assert "profile" in capsys.readouterr().err and double_clicked["runs"] == []


def test_without_a_command_python_still_asks_for_one(monkeypatch, capsys):
    import sys

    monkeypatch.delattr(sys, "frozen", raising=False)
    with pytest.raises(SystemExit) as exited:
        main([])
    assert exited.value.code == 2 and "command" in capsys.readouterr().err
