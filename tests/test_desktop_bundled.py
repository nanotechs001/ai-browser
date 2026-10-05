"""AI Browser's own app, shipped beside the packaged AI Browser.exe (the Windows test build, packaging/): a `desktop`
folder next to the exe, built there by the build with the same layout as <home>/desktop. The exe finds it first,
treats it as set up, and never offers the download; Settings and doctor describe it. Its Electron profile is in the
user's own folder (<home>/desktop-profile), so it works wherever the zip was unzipped, and a new copy keeps the
sign-in. Python running the code never looks there. The packaged exe never tells the user to run `uv run ai-browser`:
it names itself. The apps here are miniatures (tests/fake_electron_zip.py), built with stand-in tools."""

import sys

import pytest

from fake_electron_zip import mac_zip, windows_zip
from fake_tools import fake_tools
from test_bridge import EVENTS
from test_app_server import started
from test_desktop_setup import doctor  # noqa: F401 (a fixture: doctor --setup's world)

ZIPS = {"darwin": mac_zip, "win32": windows_zip}
APP_SYSTEMS = pytest.mark.skipif(sys.platform not in ZIPS, reason="AI Browser's own app is for macOS and Windows")


@pytest.fixture
def package(tmp_path, monkeypatch):
    """The packaged AI Browser.exe's folder, with the app built beside it in desktop/ (for this computer's system).
    Its sys.frozen and sys.executable are set the way PyInstaller sets them, once the app is built."""
    from ai_browser.desktop import assemble
    from ai_browser.desktop.unpack import unpack

    folder = tmp_path / "AI Browser"
    tools, _ = fake_tools(tmp_path, monkeypatch)
    archive = tmp_path / "electron.zip"
    archive.write_bytes(ZIPS[sys.platform]())
    unpack(archive, tmp_path / "electron")
    assemble.build(tmp_path / "electron", folder, sys.platform, tools, arch="x64", move=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(folder / "AI Browser.exe"))
    return folder


@APP_SYSTEMS
def test_the_packaged_exe_finds_the_app_beside_it_first(package, tmp_path):
    from ai_browser.desktop import assemble, layout
    from ai_browser.desktop.launch import default_desktop

    home = tmp_path / "home"  # the user's ~/.ai-browser: no app was set up there
    assert layout.folder(home) == package / "desktop"
    assert layout.app_path(home) == package / "desktop" / layout.app_path(home).name
    assert layout.installed(home) is not None and not assemble.stale(home)  # set up, and built from this code
    assert layout.profile(home) == home / "desktop-profile"  # the user's own folder: main.js keeps it there too
    assert default_desktop(home).app == layout.app_path(home)


@APP_SYSTEMS
def test_without_an_app_beside_it_the_packaged_exe_uses_the_home_folder(package, tmp_path, monkeypatch):
    from ai_browser.desktop import layout

    monkeypatch.setattr(sys, "executable", str(tmp_path / "elsewhere" / "AI Browser.exe"))
    assert layout.folder(tmp_path / "home") == tmp_path / "home" / "desktop"


@APP_SYSTEMS
def test_python_running_the_code_never_looks_beside_itself(package, tmp_path, monkeypatch):
    from ai_browser.desktop import layout

    monkeypatch.delattr(sys, "frozen")
    assert layout.folder(tmp_path / "home") == tmp_path / "home" / "desktop"
    assert layout.installed(tmp_path / "home") is None


@APP_SYSTEMS
def test_doctor_says_the_bundled_app_is_ready_and_offers_no_download(doctor, package, capsys):  # noqa: F811
    from ai_browser.cli import main
    from ai_browser.desktop import layout
    from ai_browser.desktop.release import VERSION

    assert main(["doctor", "--setup"]) == 0  # someone could answer (the fixture), but nothing is asked
    out = capsys.readouterr().out
    assert f"✓ app         AI Browser's own app (Electron {VERSION}): {layout.app_path(doctor['home'])}" in out
    assert str(package / "desktop") in out and "Download it now?" not in out
    assert "uv run" not in out and '- Docker      not checked here: run `"AI Browser.exe" doctor`' in out
    assert doctor["fetch"].urls == [] and doctor["answers"] == ["y"]


@APP_SYSTEMS
async def test_settings_and_the_terminal_say_the_bundled_app_is_set_up(fake_claude, package, tmp_path):
    from ai_browser.app.run import setup_hint

    server, _ = await started(fake_claude, tmp_path, EVENTS)
    try:
        payload = server._settings_payload()["desktop"]
        assert payload["set_up"] is True and payload["problem"] == ""
    finally:
        await server.stop()
    assert setup_hint(tmp_path / "home") == ""  # the browser window's "run doctor --setup once" line: not shown


@APP_SYSTEMS
def test_the_app_built_in_the_home_keeps_its_profile_beside_it(tmp_path, monkeypatch):
    from ai_browser.desktop import layout

    monkeypatch.delattr(sys, "frozen", raising=False)
    assert layout.profile(tmp_path / "home") == tmp_path / "home" / "desktop" / "profile"  # as before (macOS too)


@APP_SYSTEMS
async def test_a_page_without_the_cookie_says_to_double_click_the_exe(fake_claude, package, tmp_path):
    from test_app_server import fetch

    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        answer = await fetch("GET", url + "/app")
    finally:
        await server.stop()
    assert answer.status_code == 403
    assert "AI Browser's pages open only in its own window. Start it by double-clicking AI Browser.exe." in answer.text
    assert "uv run" not in answer.text


@APP_SYSTEMS
def test_every_command_the_packaged_exe_names_is_its_own(package):
    from ai_browser import platforms
    from ai_browser.app import run
    from ai_browser.app.server import not_here
    from ai_browser.desktop.release import setup_command

    assert platforms.command("build") == '"AI Browser.exe" build'
    assert setup_command() == '"AI Browser.exe" doctor --setup'
    assert platforms.start_words() == "by double-clicking AI Browser.exe"
    assert "`\"AI Browser.exe\" app --window chrome`" in run.no_app_page() and "uv run" not in run.no_app_page()
    assert not_here() == "AI Browser's pages open only in its own window. Start it by double-clicking AI Browser.exe."


def test_python_running_the_code_names_uv_run_as_before(monkeypatch):
    from ai_browser import platforms
    from ai_browser.app import run
    from ai_browser.app.server import not_here
    from ai_browser.desktop.release import SETUP_COMMAND, setup_command

    monkeypatch.delattr(sys, "frozen", raising=False)
    assert platforms.command("build") == "uv run ai-browser build" and setup_command() == SETUP_COMMAND
    assert platforms.start_words() == "with `uv run ai-browser app`"
    assert not_here() == "AI Browser's pages open only in its own window. Start it with `uv run ai-browser app`."
    assert run.no_app_page() == ("AI Browser's app started, but its page never connected. Try again, or use a "
                                 "browser window: `uv run ai-browser app --window chrome`")


def test_only_one_place_spells_uv_run_for_the_user():
    """Every message that names a command gets it from platforms.command or start_words, so the packaged exe names
    itself: the words `uv run ai-browser` are in platforms.py and release.py's SETUP_COMMAND only."""
    from pathlib import Path

    source = Path(__file__).parents[1] / "src" / "ai_browser"
    found = sorted(str(path.relative_to(source)) for path in source.rglob("*.py")
                   if "uv run ai-browser" in path.read_text(encoding="utf-8"))
    assert found == ["desktop/release.py", "platforms.py"]
