"""AI Browser's own app, shipped beside the packaged AI Browser.exe (the Windows test build, packaging/): a `desktop`
folder next to the exe, built there by the build with the same layout as <home>/desktop. The exe finds it first,
treats it as set up, and never offers the download; Settings and doctor describe it. Python running the code never
looks there. The apps here are miniatures (tests/fake_electron_zip.py), built with stand-in tools."""

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
    assert layout.profile(home) == package / "desktop" / "profile"  # where its main.js keeps its profile
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
