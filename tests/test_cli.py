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


def test_app_takes_the_browser_choice(capsys):
    with pytest.raises(SystemExit):
        main(["app", "--help"])
    out = capsys.readouterr().out
    assert "--browser" in out and "{brave,app}" in out
