"""Browser detection (browsers.py), read from sample files in a fake computer under tmp_path. No test reads the
user's real browser files or reaches a real browser: the autouse fixture `fake` points the home folder, the app
folders, the LaunchServices file and the Windows folders at tmp_path, and turns the registry readers off."""

import ast
import contextlib
import dataclasses
import json
import os
import plistlib
import socket
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_browser import browsers, platforms
from conftest import symlink_or_skip

SAMPLES = Path(__file__).parent / "samples" / "browsers"
AGENTS = {"brave", "brave-beta", "brave-nightly", "chrome", "chrome-beta", "chrome-dev", "chrome-canary", "chromium"}


@pytest.fixture(autouse=True)
def fake(tmp_path, monkeypatch):
    """A fake computer: its home, macOS's two app folders and LaunchServices file, Windows' three app folders, and an
    empty registry. It sets each one itself, so a conftest fixture that patches the same names can't change them."""
    home, apps = tmp_path / "home", tmp_path / "Applications"
    local, program_files = tmp_path / "Local", tmp_path / "Program Files"
    program_files_x86 = tmp_path / "Program Files (x86)"
    for folder in (home, apps, local, program_files, program_files_x86):
        folder.mkdir()
    for name, folder in (("HOME", home), ("USERPROFILE", home), ("LOCALAPPDATA", local),
                         ("ProgramFiles", program_files), ("ProgramFiles(x86)", program_files_x86)):
        monkeypatch.setenv(name, str(folder))
    launch_services = home.joinpath("Library", "Preferences", "com.apple.LaunchServices",
                                    "com.apple.launchservices.secure.plist")  # where macOS keeps it in a home

    def app_folders(system=None, env=None):
        system = system or sys.platform
        if system == "darwin":
            return [apps, home / "Applications"]
        if system == "win32":
            return [program_files, program_files_x86, local]
        return []

    monkeypatch.setattr(platforms, "app_folders", app_folders)
    monkeypatch.setattr(platforms, "launch_services_file", lambda: launch_services)
    monkeypatch.setattr(platforms, "windows_browser_commands", lambda: [])
    monkeypatch.setattr(platforms, "windows_https_progid", lambda: None)
    return SimpleNamespace(home=home, apps=apps, user_apps=home / "Applications", local=local,
                           program_files=program_files, program_files_x86=program_files_x86)


def recording_reads(monkeypatch) -> list:
    """platforms.open_shared, patched so that every read() call notes its size argument in the returned list."""
    reads, real = [], platforms.open_shared

    class Handle:
        def __init__(self, path):
            self.handle = real(path)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.handle.close()

        def fileno(self):
            return self.handle.fileno()

        def read(self, size=-1):
            reads.append(size)
            return self.handle.read(size)

    monkeypatch.setattr(platforms, "open_shared", Handle)
    return reads


# The table, and the module's own rules (Task 4)


def test_the_tests_never_read_the_real_browsers(fake, tmp_path):
    assert Path.home() == fake.home
    for system in ("darwin", "win32", "linux"):
        assert all(folder.is_relative_to(tmp_path) for folder in platforms.app_folders(system))
        assert all(folder.is_relative_to(tmp_path) for folder in browsers.all_data_dirs(system))
    assert platforms.launch_services_file().is_relative_to(tmp_path)
    assert platforms.windows_browser_commands() == [] and platforms.windows_https_progid() is None


def test_the_table_lists_each_browser_once():
    ids = [facts.id for facts in platforms.KNOWN_BROWSERS]
    assert ids == ["brave", "brave-beta", "brave-nightly", "chrome", "chrome-beta", "chrome-dev", "chrome-canary",
                   "chromium", "edge", "arc", "vivaldi"]  # each once, Brave first; no Opera, Firefox or Safari
    assert {facts.id for facts in platforms.KNOWN_BROWSERS if facts.agents} == AGENTS
    assert {facts.id for facts in platforms.KNOWN_BROWSERS if facts.window} == {"brave", "chrome", "edge"}
    assert all(facts.mac_data and facts.win_data for facts in platforms.KNOWN_BROWSERS if facts.agents)
    assert browsers.by_id("chrome-canary").name == "Chrome Canary" and browsers.by_id("opera") is None
    inspect = {facts.id: facts.inspect for facts in platforms.KNOWN_BROWSERS}
    assert inspect["brave-nightly"] == "brave" and inspect["edge"] == "edge" and inspect["chromium"] == "chrome"


def test_the_old_folder_helpers_read_the_table():
    env = {"LOCALAPPDATA": "C:\\Users\\Alex\\AppData\\Local", "ProgramFiles": "C:\\Program Files"}
    for name in ("brave", "chrome"):
        for system, given in (("darwin", None), ("win32", env), ("linux", None)):
            assert platforms.user_data_dir(name, system, given) == browsers.data_dir(browsers.by_id(name), system,
                                                                                      given)
    assert platforms.browser_candidates("brave", "darwin") == [
        Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")]
    assert platforms.browser_candidates("chrome", "win32", env) == [
        Path("C:\\Program Files", "Google", "Chrome", "Application", "chrome.exe"),
        Path("C:\\Users\\Alex\\AppData\\Local", "Google", "Chrome", "Application", "chrome.exe")]
    with pytest.raises(ValueError):
        platforms.user_data_dir("chrome-beta")


def test_for_data_dir_names_the_browser(fake, tmp_path):
    brave = browsers.by_id("brave")
    assert browsers.for_data_dir(browsers.data_dir(brave, "darwin"), "darwin") is brave
    env = {"LOCALAPPDATA": str(fake.local)}
    other_case = fake.local / "bravesoftware" / "BRAVE-BROWSER" / "user data"
    assert browsers.for_data_dir(other_case, "win32", env) is brave  # Windows paths ignore case
    linux = browsers.data_dir(brave, "linux")
    assert browsers.for_data_dir(linux, "linux") is brave
    if os.name != "nt":  # Windows' realpath restores the case found on disk
        assert browsers.for_data_dir(linux.parent / "brave-browser", "linux") is None
    assert browsers.for_data_dir(tmp_path / "elsewhere", "darwin") is None
    assert browsers.for_data_dir("bad\0folder", "darwin") is None
    for name in ("edge", "arc", "vivaldi"):  # installed or not, every known folder is listed
        assert browsers.data_dir(browsers.by_id(name), "darwin") in browsers.all_data_dirs("darwin")


def test_for_data_dir_agrees_with_the_relays_folder_rule(fake, tmp_path):
    """Wave C names the browser behind each relay with for_data_dir(relay.folder); the relay's engine compares
    folders with chrome._same_folder. On this computer's own OS the two rules must name the same folders."""
    from ai_browser.chrome import _same_folder

    own = browsers.data_dir(browsers.by_id("brave"))
    own.mkdir(parents=True)
    link = tmp_path / "link-to-brave"
    symlink_or_skip(own, link)
    asked = [own, Path(f"{own}{os.sep}"), own / ".." / own.name, link, own.parent / own.name.upper(),
             own.parent / "Brave-Browser-Beta", tmp_path / "elsewhere"]
    for folder in asked:
        for facts in platforms.KNOWN_BROWSERS:
            known = browsers.data_dir(facts)
            if known is not None:
                assert (browsers.for_data_dir(folder) is facts) == _same_folder(folder, known), (folder, facts.id)
    assert browsers.for_data_dir(link) is browsers.by_id("brave")  # a link to the folder is the folder


def test_the_reader_reads_only_small_regular_files(tmp_path, monkeypatch):
    small = tmp_path / "small"
    small.write_bytes(b"{}")
    assert browsers._read(small) == b"{}"
    assert browsers._read(tmp_path / "missing") is None and browsers._read(tmp_path) is None  # a folder
    if hasattr(os, "mkfifo"):
        os.mkfifo(tmp_path / "pipe")
        assert browsers._read(tmp_path / "pipe") is None  # a plain open would wait for a writer forever
    huge = tmp_path / "huge"
    huge.write_bytes(b"")
    os.truncate(huge, 17 * 1024 * 1024)  # sparse where the file system allows it
    reads = recording_reads(monkeypatch)
    assert browsers._read(huge) is None and reads == []  # too big: never read
    assert browsers._read(small) == b"{}" and reads == [browsers.MAX_FILE + 1]  # one read, capped


def test_a_file_that_grows_while_it_is_read_is_not_used(tmp_path, monkeypatch):
    grown, before = tmp_path / "Local State", tmp_path / "before"
    grown.write_bytes(b"x" * 20)
    before.write_bytes(b"x" * 4)
    real = platforms.open_shared

    class SizeBeforeTheWrite:  # fstat sees the file as it was, read() sees it after the browser's write
        def __init__(self, path):
            self.handle, self.old = real(path), real(before)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.handle.close()
            self.old.close()

        def fileno(self):
            return self.old.fileno()

        def read(self, size=-1):
            return self.handle.read(size)

    monkeypatch.setattr(browsers, "MAX_FILE", 8)
    monkeypatch.setattr(platforms, "open_shared", SizeBeforeTheWrite)
    assert browsers._read(grown) is None


def test_browsers_imports_no_connection_code():
    tree = ast.parse(Path(browsers.__file__).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {part for alias in node.names for part in alias.name.split(".")}
        elif isinstance(node, ast.ImportFrom):
            names |= set((node.module or "").split("."))
            if not node.module:  # from . import chrome
                names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "__import__":
            names.add("__import__")
    forbidden = {"cdp", "websockets", "chrome", "appbrowser", "http", "urllib", "aiohttp", "subprocess", "importlib",
                 "__import__"}
    assert not names & forbidden, names & forbidden


# Installed apps on macOS (Task 5)


def sample(name: str) -> bytes:
    return (SAMPLES / name).read_bytes()


def info_plist(bundle_id: str, program: str, version: str = "1.0", fmt=plistlib.FMT_XML) -> bytes:
    return plistlib.dumps({"CFBundleIdentifier": bundle_id, "CFBundleExecutable": program,
                           "CFBundleShortVersionString": version}, fmt=fmt)


def mac_app(folder: Path, app: str, info: bytes | None, program: str | None) -> Path:
    """An app bundle in `folder`: Contents/Info.plist (unless `info` is None) and Contents/MacOS/<program>."""
    bundle = folder / app
    (bundle / "Contents" / "MacOS").mkdir(parents=True, exist_ok=True)
    if info is not None:
        (bundle / "Contents" / "Info.plist").write_bytes(info)
    if program:
        (bundle / "Contents" / "MacOS" / program).write_bytes(b"#!/bin/sh\n")
    return bundle


def test_an_empty_fake_computer_has_no_browsers():
    assert browsers.installed() == [] and browsers.installed(system="darwin") == []
    assert browsers.installed(system="win32") == [] and browsers.installed(system="linux") == []


def test_mac_installed_means_the_app_with_its_bundle_id(fake):
    brave = mac_app(fake.apps, "Brave Browser.app", sample("brave-info.plist"), "Brave Browser")
    chrome = mac_app(fake.apps, "Google Chrome.app", sample("chrome-info.plist"), "Google Chrome")
    support = fake.home / "Library" / "Application Support"
    for leftover in ("Arc/User Data", "Chromium", "Microsoft Edge", "Vivaldi", "com.operasoftware.Opera"):
        (support / leftover).mkdir(parents=True)  # data folders of apps that are gone prove nothing
    found = browsers.installed(system="darwin")
    assert [item.id for item in found] == ["brave", "chrome"]
    assert (found[0].binary, found[0].bundle) == (brave / "Contents" / "MacOS" / "Brave Browser", brave)
    assert (found[1].binary, found[1].bundle) == (chrome / "Contents" / "MacOS" / "Google Chrome", chrome)
    assert (found[0].version, found[1].version) == ("152.1.94.121", "154.0.8037.93")
    assert found[0].data_dir == support / "BraveSoftware" / "Brave-Browser"
    assert found[1].data_dir == support / "Google" / "Chrome"
    assert (found[0].name, found[0].agents, found[0].window, found[0].inspect_address) == (
        "Brave", True, True, "brave://inspect/#remote-debugging")


def test_mac_apps_in_the_users_applications_folder(fake):
    canary = mac_app(fake.user_apps, "Google Chrome Canary.app",
                     info_plist("com.google.Chrome.canary", "Google Chrome Canary"), "Google Chrome Canary")
    found = browsers.installed(system="darwin")
    assert [(item.id, item.bundle) for item in found] == [("chrome-canary", canary)]


BROKEN_DATE = (b'<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict>'
               b"<key>CFBundleIdentifier</key><string>com.brave.Browser</string>"
               b"<key>CFBundleExecutable</key><string>Brave Browser</string>"
               b"<key>Built</key><date>not a date</date></dict></plist>")


@pytest.mark.parametrize("info, program, counted", [
    pytest.param(lambda: info_plist("com.example.NotBrave", "Brave Browser"), "Brave Browser", False,
                 id="another bundle id"),
    pytest.param(lambda: None, "Brave Browser", False, id="no Info.plist"),
    pytest.param(lambda: b"\x00\xffgarbage", "Brave Browser", False, id="garbage"),
    pytest.param(lambda: sample("brave-info.plist")[:200], "Brave Browser", False, id="cut XML (ExpatError)"),
    pytest.param(lambda: BROKEN_DATE, "Brave Browser", False, id="broken date (AttributeError)"),
    pytest.param(lambda: info_plist("com.brave.Browser", "../../x"), "Brave Browser", False,
                 id="its program is outside the app"),
    pytest.param(lambda: sample("brave-info.plist"), None, False, id="no program"),
    pytest.param(lambda: info_plist("com.brave.Browser", "Brave Browser", fmt=plistlib.FMT_BINARY), "Brave Browser",
                 True, id="binary plist"),
    pytest.param(lambda: info_plist("com.brave.browser", "Brave Browser"), "Brave Browser", True,
                 id="bundle id in lower case"),
])
def test_a_mac_app_that_isnt_the_browser_is_skipped(fake, info, program, counted):
    bundle = mac_app(fake.apps, "Brave Browser.app", info(), program)
    (bundle / "x").write_bytes(b"#!/bin/sh\n")  # what "../../x" would name
    assert [item.id for item in browsers.installed(system="darwin")] == (["brave"] if counted else [])


# Installed programs on Windows (Task 5, Windows)


def windows_program(root: Path, *parts: str) -> Path:
    program = root.joinpath(*parts)
    program.parent.mkdir(parents=True, exist_ok=True)
    program.write_bytes(b"MZ")
    return program


def test_windows_installed_from_the_app_folders(fake):
    brave = windows_program(fake.local, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")
    chrome = windows_program(fake.program_files, "Google", "Chrome", "Application", "chrome.exe")
    edge = windows_program(fake.program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe")
    found = browsers.installed(system="win32")
    assert [(item.id, item.binary) for item in found] == [("brave", brave), ("chrome", chrome), ("edge", edge)]
    assert [item.agents for item in found] == [True, True, False]
    assert all(item.bundle is None and item.version is None for item in found)
    assert [item.data_dir for item in found] == [fake.local / "BraveSoftware" / "Brave-Browser" / "User Data",
                                                 fake.local / "Google" / "Chrome" / "User Data",
                                                 fake.local / "Microsoft" / "Edge" / "User Data"]


def test_windows_installed_from_the_registry(tmp_path):
    beta = windows_program(tmp_path / "Elsewhere", "Google", "Chrome Beta", "Application", "chrome.exe")
    local = tmp_path / "Other Local"
    chromium = windows_program(local, "Chromium", "Application", "CHROME.EXE")
    beta_command = f'"{beta.as_posix()}" --single-argument %1'
    commands = [beta_command,
                "%localappdata%/Chromium/Application/CHROME.EXE -- %1",  # unquoted, other letter case
                f'"{(tmp_path / "Gone" / "Google" / "Chrome" / "Application" / "chrome.exe").as_posix()}" %1',
                "not a path",
                beta_command]
    found = browsers.installed(system="win32", env={"LOCALAPPDATA": str(local)}, folders=[], commands=commands)
    assert [(item.id, item.binary) for item in found] == [("chrome-beta", beta), ("chromium", chromium)]


def test_canary_is_never_taken_for_chrome(tmp_path):
    canary = windows_program(tmp_path / "Apps", "Google", "Chrome SxS", "Application", "chrome.exe")
    found = browsers.installed(system="win32", folders=[], commands=[f'"{canary.as_posix()}"'])
    assert [item.id for item in found] == ["chrome-canary"]


def test_a_windows_browser_found_twice_is_listed_once(fake):
    machine = windows_program(fake.program_files, "Google", "Chrome", "Application", "chrome.exe")
    user = windows_program(fake.local, "Google", "Chrome", "Application", "chrome.exe")
    commands = [f'"{user}" --single-argument %1', str(user).upper()]
    found = browsers.installed(system="win32", commands=commands)
    assert [(item.id, item.binary) for item in found] == [("chrome", machine)]  # where it was found first


def test_a_windows_app_folder_is_a_path_not_a_command(tmp_path):
    local = tmp_path / "alex.exeter" / "AppData" / "Local %TEMP%"  # a user's folder may hold ".exe" or "%"
    brave = windows_program(local, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")
    env = {"LOCALAPPDATA": str(local), "TEMP": str(tmp_path / "Temp")}
    found = browsers.installed(system="win32", env=env, folders=[local], commands=[])
    assert [(item.id, item.binary) for item in found] == [("brave", brave)]  # never cut at "alex.exe", never expanded
