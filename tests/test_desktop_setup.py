"""`ai-browser doctor --setup` offers AI Browser's own app (desktop/setup.py, cli.py). It builds the app only after a
typed yes. Before it asks, it shows the pinned Electron's version, size and address. The download is checked against
SHASUMS256.txt. When the download is cut, doesn't match or is stopped, nothing is kept, and the reason is kept for
Settings. Every release here is a miniature (tests/fake_electron_zip.py), and codesign and sips are stand-ins."""

import sys
from pathlib import Path

import pytest

from fake_electron_zip import ReleaseFetch, checksum, mac_zip, windows_zip
from fake_tools import fake_tools, tool_runs
from test_cli import _browser_port_stand_in, _setup_env

ZIPS = {"darwin": mac_zip, "win32": windows_zip}
APP_SYSTEMS = pytest.mark.skipif(sys.platform not in ZIPS, reason="AI Browser's own app is for macOS and Windows")


@pytest.fixture
def doctor(tmp_path, monkeypatch):
    """doctor --setup's world: a throwaway home, a fake Claude Code and browser (test_cli's), a miniature Electron
    release for this computer, stand-in tools, and someone at the terminal who answers from `answers`."""
    from ai_browser import cli
    from ai_browser.desktop import release, setup

    server, _ = _browser_port_stand_in()
    env = _setup_env(tmp_path, monkeypatch, server.getsockname()[1])
    data = ZIPS[sys.platform]()
    asset = release.Asset(sys.platform, "arm64" if sys.platform == "darwin" else "x64", "electron-test.zip",
                          len(data), checksum(data), "a test computer")
    fetch = ReleaseFetch(asset, data)
    tools, log = fake_tools(tmp_path, monkeypatch)
    answers = ["y"]
    monkeypatch.setattr(release, "asset_for", lambda system=None, machine=None: asset)
    monkeypatch.setattr(setup, "FETCH", fetch)
    monkeypatch.setattr(setup, "TOOLS", tools)
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    monkeypatch.setattr(cli, "_ask", lambda question: answers.pop(0))
    yield {"home": Path(env["AIB_HOME"]), "asset": asset, "fetch": fetch, "log": log, "answers": answers}
    server.close()


def listing(home: Path) -> list[str]:
    folder = home / "desktop"
    return sorted(path.name for path in folder.iterdir()) if folder.exists() else []


@APP_SYSTEMS
def test_the_offer_says_what_and_where_and_a_yes_builds_the_app(doctor, capsys):
    from ai_browser.cli import main
    from ai_browser.desktop import layout
    from ai_browser.desktop.release import SHASUMS, VERSION

    asset, home = doctor["asset"], doctor["home"]
    assert main(["doctor", "--setup"]) == 0
    out = capsys.readouterr().out
    assert "- app         AI Browser's own app isn't set up: AI Browser opens in a browser window" in out
    assert f"It is built from Electron {VERSION} for a test computer: {asset.megabytes}, from" in out
    assert f"\n  {asset.url}\n" in out and "checked against Electron's SHASUMS256.txt" in out
    assert f"The app is built in {home / 'desktop'}." in out
    assert "✓ app         AI Browser's own app is ready: start it with `uv run ai-browser app`" in out
    assert out.splitlines()[-1] == "all good"
    assert doctor["fetch"].urls == [SHASUMS, asset.url]  # the checksums first, then the zip
    assert layout.installed(home) is not None and layout.problem(home) == ""
    assert listing(home) == sorted([layout.app_path(home).name, "app.json"])  # no zip, no unpacked Electron
    if sys.platform == "darwin":
        assert [run[0] for run in tool_runs(doctor["log"])] == ["sips", "codesign"]


@APP_SYSTEMS
def test_a_download_cut_halfway_keeps_nothing_and_settings_will_say_why(doctor, capsys):  # Review Focus 2
    from ai_browser.cli import main
    from ai_browser.desktop import layout
    from ai_browser.desktop.download import CUT

    doctor["fetch"].cut_at = doctor["asset"].size // 2
    assert main(["doctor", "--setup"]) == 1
    out = capsys.readouterr().out
    assert f"✗ app         {CUT}" in out and out.splitlines()[-1] == "some checks failed"
    assert layout.problem(doctor["home"]) == CUT
    assert listing(doctor["home"]) == ["problem.json"]  # no zip, no part, no app


@APP_SYSTEMS
def test_a_zip_or_a_list_that_doesnt_match_keeps_nothing(doctor, capsys):  # Review Focus 2
    from ai_browser.cli import main
    from ai_browser.desktop.download import MISMATCH, NOT_LISTED
    from ai_browser.desktop.release import SHASUMS

    doctor["fetch"].corrupt = True
    assert main(["doctor", "--setup"]) == 1
    assert f"✗ app         {MISMATCH}" in capsys.readouterr().out
    assert listing(doctor["home"]) == ["problem.json"]
    doctor["fetch"].corrupt, doctor["fetch"].listed = False, "f" * 64
    doctor["answers"][:] = ["y"]
    doctor["fetch"].urls.clear()
    assert main(["doctor", "--setup"]) == 1
    out = capsys.readouterr().out
    assert f"- app         the last setup didn't finish: {MISMATCH}" in out  # what went wrong before, said first
    assert f"✗ app         {NOT_LISTED}" in out and doctor["fetch"].urls == [SHASUMS]  # the zip: never fetched


@APP_SYSTEMS
def test_only_a_yes_downloads(doctor, capsys):
    from ai_browser.cli import main

    for answer in ("n", "", "yes please"):
        doctor["answers"][:] = [answer]
        assert main(["doctor", "--setup"]) == 0
        assert "Skipped: nothing was downloaded." in capsys.readouterr().out
    assert doctor["fetch"].urls == [] and listing(doctor["home"]) == []


@APP_SYSTEMS
def test_ctrl_c_during_the_download_keeps_nothing(doctor, monkeypatch, capsys):
    from ai_browser.cli import main
    from ai_browser.desktop import layout, setup

    def stopping(asset, out):
        def progress(done):
            raise KeyboardInterrupt
        return progress

    monkeypatch.setattr(setup, "_progress", stopping)
    assert main(["doctor", "--setup"]) == 130
    assert layout.problem(doctor["home"]) == setup.STOPPED == ("The setup was stopped before the end: nothing was "
                                                               "kept")
    assert listing(doctor["home"]) == ["problem.json"]


@APP_SYSTEMS
def test_the_setup_waits_until_ai_browser_is_not_running(doctor, capsys):
    from ai_browser import platforms
    from ai_browser.cli import main

    (doctor["home"] / "app").mkdir(parents=True)
    lock = platforms.lock_file(doctor["home"] / "app" / "lock")  # a running `ai-browser app` holds it
    try:
        assert main(["doctor", "--setup"]) == 1
    finally:
        lock.close()
    assert "✗ app         AI Browser is running: quit it, then run the setup again" in capsys.readouterr().out
    assert doctor["fetch"].urls == []


@APP_SYSTEMS
def test_once_set_up_it_says_so_and_asks_nothing(doctor, capsys):
    from ai_browser.cli import main
    from ai_browser.desktop import layout
    from ai_browser.desktop.release import VERSION

    assert main(["doctor", "--setup"]) == 0
    capsys.readouterr()
    assert main(["doctor", "--setup"]) == 0  # `answers` is empty now: a question would fail the test
    out = capsys.readouterr().out
    assert f"✓ app         AI Browser's own app (Electron {VERSION}): {layout.app_path(doctor['home'])}" in out


@APP_SYSTEMS
def test_with_no_one_to_answer_it_says_how_and_downloads_nothing(doctor, monkeypatch, capsys):
    from ai_browser import cli

    monkeypatch.setattr(cli, "_interactive", lambda: False)
    assert cli.main(["doctor", "--setup"]) == 0
    line = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("- app"))
    assert line == ("- app         AI Browser's own app isn't set up: AI Browser opens in a browser window. To set it "
                    "up, run `uv run ai-browser doctor --setup` in a terminal (it asks first)")
    assert doctor["fetch"].urls == []


def test_where_the_app_doesnt_run_the_doctor_says_so(tmp_path, monkeypatch, capsys):
    from ai_browser.cli import main
    from ai_browser.desktop import release

    server, _ = _browser_port_stand_in()
    try:
        _setup_env(tmp_path, monkeypatch, server.getsockname()[1])
        monkeypatch.setattr(release, "asset_for", lambda system=None, machine=None: None)
        assert main(["doctor", "--setup"]) == 0
    finally:
        server.close()
    assert ("- app         AI Browser's own app runs on macOS and on Windows (x64): here it opens in a browser "
            "window") in capsys.readouterr().out


def test_no_test_downloads_electron_or_waits_for_an_answer(tmp_path):
    from ai_browser import cli
    from ai_browser.config import home
    from ai_browser.desktop import setup

    with pytest.raises(AssertionError, match="tests never download Electron"):
        setup.FETCH("https://github.com/electron/electron/releases/download/v44.5.1/SHASUMS256.txt")
    assert cli._interactive() is False and home() != Path.home() / ".ai-browser"
