"""Building AI Browser's own app from Electron's zip (desktop/assemble.py). The zips are miniatures with Electron's
layout (tests/fake_electron_zip.py), and codesign and sips are stand-ins (tests/fake_tools.py) whose exact command
lines are checked. Nothing is downloaded, and no real tool runs."""

import os
import plistlib

import pytest

from conftest import file_mode
from fake_electron_zip import mac_zip, windows_zip
from fake_tools import fake_tools, tool_runs


def unpacked(tmp_path, data: bytes):
    from ai_browser.desktop.unpack import unpack

    archive = tmp_path / "electron.zip"
    archive.write_bytes(data)
    unpack(archive, tmp_path / "electron")
    return tmp_path / "electron"


@pytest.mark.posix_only  # the Mac's zip holds symbolic links
def test_the_mac_app_gets_its_name_icon_javascript_fuses_and_signature(tmp_path, monkeypatch):
    from ai_browser.desktop import assemble, fuses, layout
    from ai_browser.desktop.release import VERSION
    from ai_browser.desktop.stage import APP_FILES, ELECTRON, ICON

    tools, log = fake_tools(tmp_path, monkeypatch)
    home = tmp_path / "home"
    app = assemble.build(unpacked(tmp_path, mac_zip()), home, "darwin", tools, arch="arm64", move=True)
    assert app == home / "desktop" / "AI Browser.app"
    with open(app / "Contents" / "Info.plist", "rb") as handle:
        info = plistlib.load(handle)
    assert {key: info[key] for key in assemble.PLIST} == assemble.PLIST
    assert (info["CFBundleName"], info["CFBundleDisplayName"]) == ("AI Browser", "AI Browser")
    assert info["CFBundleIdentifier"] == "io.github.nanotechs001.ai-browser"
    assert info["CFBundleExecutable"] == "Electron"  # Electron's own keys stay,
    assert "CFBundleIconName" not in info  # but not its asset catalog's icon, which macOS would show instead of ours
    resources = app / "Contents" / "Resources"
    assert sorted(path.name for path in (resources / "app").iterdir()) == sorted([*APP_FILES, "icon.png"])
    assert all((resources / "app" / name).read_bytes() == (ELECTRON / name).read_bytes() for name in APP_FILES)
    assert (resources / "AI Browser.icns").read_bytes() == ICON.read_bytes()  # the fake sips copies; sips converts
    assert not (resources / "default_app.asar").exists()  # Electron's own app can't run in AI Browser's place
    assert fuses.states(layout.framework(app)) == ["000000011"]  # runAsNode, nodeOptions, nodeCliInspect off
    current = app / "Contents" / "Frameworks" / "Electron Framework.framework" / "Versions" / "Current"
    assert current.is_symlink() and os.readlink(current) == "A"
    assert os.access(layout.executable(app, "darwin"), os.X_OK)
    building = home / "desktop" / ".build" / "AI Browser.app"
    assert tool_runs(log) == [
        ["sips", "-s", "format", "icns", str(ICON), "--out",
         str(building / "Contents" / "Resources" / "AI Browser.icns")],
        ["codesign", "--force", "--deep", "--sign", "-", str(building)]]  # signed last, once everything is in
    stamp = layout.stamp(home)
    assert {key: stamp[key] for key in ("electron", "system", "arch", "layer")} == {
        "electron": VERSION, "system": "darwin", "arch": "arm64", "layer": assemble.layer_hash("darwin")}
    assert file_mode(home / "desktop" / "app.json") in (0o600, None)
    assert sorted(path.name for path in (home / "desktop").iterdir()) == ["AI Browser.app", "app.json"]
    assert not (tmp_path / "electron" / "Electron.app").exists()  # moved, not copied


def test_the_windows_app_is_a_folder_with_ai_browser_exe(tmp_path, monkeypatch):
    from ai_browser.desktop import assemble, fuses, layout
    from ai_browser.desktop.stage import APP_FILES

    tools, log = fake_tools(tmp_path, monkeypatch)
    home = tmp_path / "home"
    app = assemble.build(unpacked(tmp_path, windows_zip()), home, "win32", tools, arch="x64", move=True)
    assert app == home / "desktop" / "AI Browser"
    assert (app / "AI Browser.exe").is_file() and not (app / "electron.exe").exists()
    assert sorted(path.name for path in (app / "resources" / "app").iterdir()) == sorted([*APP_FILES, "icon.png"])
    assert not (app / "resources" / "default_app.asar").exists()
    assert fuses.states(app / "AI Browser.exe") == ["000000011"]
    assert tool_runs(log) == []  # no icon tool and no signing: the .exe keeps Electron's icon in File Explorer
    assert layout.installed(home, "win32")["system"] == "win32"


@pytest.mark.posix_only
def test_a_failed_signature_keeps_the_app_that_was_there(tmp_path, monkeypatch):
    from ai_browser.desktop import assemble
    from ai_browser.desktop.download import SetupError

    tools, _ = fake_tools(tmp_path, monkeypatch)
    home = tmp_path / "home"
    before = home / "desktop" / "AI Browser.app"
    before.mkdir(parents=True)
    (before / "marker").write_text("the app from before", encoding="utf-8")
    monkeypatch.setenv("FAKE_TOOLS_FAIL", "codesign")
    with pytest.raises(SetupError) as error:
        assemble.build(unpacked(tmp_path, mac_zip()), home, "darwin", tools, move=True)
    assert str(error.value) == "macOS couldn't sign AI Browser's app: codesign: fake failure"
    assert (before / "marker").read_text(encoding="utf-8") == "the app from before"
    assert sorted(path.name for path in (home / "desktop").iterdir()) == ["AI Browser.app"]  # no .build, no stamp


def test_an_electron_without_fuses_is_refused_and_nothing_is_kept(tmp_path, monkeypatch):
    from ai_browser.desktop import assemble
    from ai_browser.desktop.download import SetupError

    tools, _ = fake_tools(tmp_path, monkeypatch)
    with pytest.raises(SetupError, match="^This Electron build has no fuses: nothing was kept$"):
        assemble.build(unpacked(tmp_path, windows_zip(wire=b"")), tmp_path / "home", "win32", tools, move=True)
    assert sorted(path.name for path in (tmp_path / "home" / "desktop").iterdir()) == []


def test_a_changed_part_is_noticed_and_built_again(tmp_path, monkeypatch):  # Review Focus 5
    from ai_browser.desktop import assemble, fuses, layout
    from ai_browser.desktop.stage import ELECTRON

    tools, _ = fake_tools(tmp_path, monkeypatch)
    home = tmp_path / "home"
    app = assemble.build(unpacked(tmp_path, windows_zip()), home, "win32", tools, move=True)
    assert not assemble.stale(home, "win32")
    (app / "resources" / "app" / "main.js").write_text("// an older main.js", encoding="utf-8")
    monkeypatch.setattr(assemble, "layer_hash", lambda system: "a newer part")  # a pull changed AI Browser's part
    assert assemble.stale(home, "win32")
    assert assemble.refresh(home, "win32", tools) == app
    assert layout.stamp(home)["layer"] == "a newer part" and not assemble.stale(home, "win32")
    assert (app / "resources" / "app" / "main.js").read_bytes() == (ELECTRON / "main.js").read_bytes()
    assert fuses.states(app / "AI Browser.exe") == ["000000011"]  # still off: setting them again changes nothing
    assert sorted(path.name for path in (home / "desktop").iterdir()) == ["AI Browser", "app.json"]


def test_the_part_hash_follows_every_file_the_app_gets(tmp_path, monkeypatch):
    from ai_browser.desktop import assemble, stage

    copy = tmp_path / "electron"
    copy.mkdir()
    for name in stage.APP_FILES:
        (copy / name).write_bytes((stage.ELECTRON / name).read_bytes())
    monkeypatch.setattr(stage, "ELECTRON", copy)
    first = assemble.layer_hash("darwin")
    (copy / "preload.js").write_bytes(b"// changed")
    assert assemble.layer_hash("darwin") != first
    assert assemble.layer_hash("darwin") != assemble.layer_hash("win32")  # the Info.plist part is the Mac's own


def test_the_commands_are_exactly_these(tmp_path):
    from ai_browser.desktop.assemble import Tools, icon_command, sign_command

    app = tmp_path / "AI Browser.app"
    assert sign_command(Tools(), app) == ["codesign", "--force", "--deep", "--sign", "-", str(app)]
    assert icon_command(Tools(), tmp_path / "icon.png", tmp_path / "AI Browser.icns") == [
        "sips", "-s", "format", "icns", str(tmp_path / "icon.png"), "--out", str(tmp_path / "AI Browser.icns")]
