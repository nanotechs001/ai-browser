"""The one Electron release AI Browser's own app is built on (desktop/release.py), and where the app lives
(desktop/layout.py): pure facts, no network, no download."""

from conftest import file_mode


def test_the_pin_is_electron_44_5_1_with_its_listed_sizes_and_checksums():
    from ai_browser.desktop import release

    assert release.VERSION == "44.5.1"
    assert release.SHASUMS == "https://github.com/electron/electron/releases/download/v44.5.1/SHASUMS256.txt"
    assert release.SETUP_COMMAND == "uv run ai-browser doctor --setup"
    assert [(asset.system, asset.arch, asset.name, asset.size, asset.sha256) for asset in release.ASSETS] == [
        ("darwin", "arm64", "electron-v44.5.1-darwin-arm64.zip", 130_259_261,
         "1d75703019bb16461ae65f3081d7e6f5c0b11e901d0ccb5c343bcf7bcdd6435c"),
        ("darwin", "x64", "electron-v44.5.1-darwin-x64.zip", 134_208_970,
         "e567d13833d0e161d7749727355b98643461df3395b537cfa7bdddf8a8bfedff"),
        ("win32", "x64", "electron-v44.5.1-win32-x64.zip", 157_998_329,
         "9b382492dcfee91f8f9e92c91f7972550a1b95d2299cac72279dab33a600d7db")]
    assert release.ASSETS[0].url == ("https://github.com/electron/electron/releases/download/v44.5.1/"
                                     "electron-v44.5.1-darwin-arm64.zip")
    assert [asset.megabytes for asset in release.ASSETS] == ["130 MB", "134 MB", "158 MB"]


def test_each_computer_gets_its_own_zip_or_none():
    from ai_browser.desktop.release import ASSETS, arch, asset_for

    assert asset_for("darwin", "arm64") is ASSETS[0]
    assert asset_for("darwin", "x86_64") is ASSETS[1]
    assert asset_for("win32", "AMD64") is ASSETS[2]
    assert asset_for("win32", "ARM64") is None  # Windows on Arm: a browser window
    assert asset_for("linux", "x86_64") is None
    assert asset_for("darwin", "ppc") is None and arch("ppc") == ""


def test_the_offer_shows_the_version_size_and_address_first(tmp_path):
    from ai_browser.desktop.release import ASSETS, offer

    assert offer(ASSETS[0], tmp_path / "desktop", "darwin") == [
        "AI Browser can run as its own app: its own Dock icon, a menu-bar icon, the ⌥Space shortcut and "
        "notifications.",
        "It is built from Electron 44.5.1 for a Mac with Apple silicon: 130 MB, from",
        "  https://github.com/electron/electron/releases/download/v44.5.1/electron-v44.5.1-darwin-arm64.zip",
        "The download is checked against Electron's SHASUMS256.txt. If anything doesn't match, nothing is kept.",
        f"The app is built in {tmp_path / 'desktop'}. Nothing else is downloaded."]
    windows = offer(ASSETS[2], tmp_path / "desktop", "win32")
    assert windows[0] == ("AI Browser can run as its own app: a taskbar icon, an icon by the clock, the Alt+Space "
                          "shortcut and notifications.")
    assert windows[1] == "It is built from Electron 44.5.1 for Windows (x64): 158 MB, from"
    assert windows[-1] == "It also adds AI Browser to the Start menu, so Windows can show its notifications."
    assert "⌥" not in " ".join(windows)


def test_the_app_lives_in_the_homes_desktop_folder(tmp_path):
    from ai_browser.desktop import layout

    home = tmp_path / "home"
    mac, windows = layout.app_path(home, "darwin"), layout.app_path(home, "win32")
    assert mac == home / "desktop" / "AI Browser.app" and windows == home / "desktop" / "AI Browser"
    assert layout.executable(mac, "darwin") == mac / "Contents" / "MacOS" / "Electron"
    assert layout.executable(windows, "win32") == windows / "AI Browser.exe"
    assert layout.resources(mac, "darwin") == mac / "Contents" / "Resources"
    assert layout.resources(windows, "win32") == windows / "resources"
    assert layout.framework(mac) == (mac / "Contents" / "Frameworks" / "Electron Framework.framework"
                                     / "Electron Framework")
    assert layout.profile(home) == home / "desktop" / "profile"
    assert (layout.APP_NAME, layout.BUNDLE_ID) == ("AI Browser", "io.github.nanotechs001.ai-browser")


def test_installed_means_built_here_for_this_system(tmp_path):
    from ai_browser.desktop import layout

    home = tmp_path / "home"
    assert layout.installed(home, "darwin") is None and layout.stamp(home) is None
    stamp = {"electron": "44.5.1", "system": "darwin", "arch": "arm64", "layer": "x"}
    layout.write_stamp(home, stamp)
    assert layout.installed(home, "darwin") is None  # the record alone: no program
    program = layout.executable(layout.app_path(home, "darwin"), "darwin")
    program.parent.mkdir(parents=True)
    program.write_bytes(b"")
    assert layout.installed(home, "darwin") == stamp and layout.installed(home, "win32") is None
    assert file_mode(home / "desktop" / "app.json") in (0o600, None)
    (home / "desktop" / "app.json").write_text("{broken", encoding="utf-8")
    assert layout.installed(home, "darwin") is None and layout.stamp(home) is None  # never raises


def test_the_last_problem_is_kept_for_settings_and_then_forgotten(tmp_path):
    from ai_browser.desktop import layout

    home = tmp_path / "home"
    assert layout.problem(home) == ""
    layout.set_problem(home, "The download stopped before the end: nothing was kept")
    assert layout.problem(home) == "The download stopped before the end: nothing was kept"
    assert file_mode(home / "desktop" / "problem.json") in (0o600, None)
    layout.set_problem(home, None)
    assert layout.problem(home) == "" and not (home / "desktop" / "problem.json").exists()
    layout.set_problem(home, None)  # nothing to forget: fine
