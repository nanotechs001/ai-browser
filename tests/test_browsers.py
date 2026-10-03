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
import time
import unicodedata
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


# The default browser (Task 6)


def test_an_empty_fake_computer_has_no_default_browser():
    assert [browsers.os_default(system) for system in (None, "darwin", "win32", "linux")] == [None] * 4


def test_os_default_on_the_mac():
    record = platforms.launch_services_file()
    record.parent.mkdir(parents=True)
    record.write_bytes(sample("launchservices.plist"))
    assert browsers.os_default("darwin") == "brave"
    handlers = plistlib.loads(sample("launchservices.plist"))
    record.write_bytes(plistlib.dumps(handlers, fmt=plistlib.FMT_BINARY))  # as macOS writes it
    assert browsers.os_default("darwin") == "brave"
    mail_only = {"LSHandlers": [entry for entry in handlers["LSHandlers"]
                                if entry.get("LSHandlerURLScheme") == "mailto"]}
    record.write_bytes(plistlib.dumps(mail_only))
    assert browsers.os_default("darwin") is None  # the mail handler (Chrome here) is never taken for the browser
    record.write_bytes(b"\x00garbage")
    assert browsers.os_default("darwin") is None
    record.write_bytes(plistlib.dumps({"LSHandlers": [{"LSHandlerURLScheme": "https",
                                                       "LSHandlerRoleAll": "org.mozilla.firefox"}]}))
    assert browsers.os_default("darwin") is None


@pytest.mark.parametrize("progid, expected", [
    ("ChromeHTML", "chrome"), ("BraveHTML", "brave"), ("MSEdgeHTM", "edge"), ("ChromeHTML.ABC123", "chrome"),
    ("bravehtml", "brave"), ("ChromeBHTML", None), ("FirefoxURL-308046B0AF4A39CB", None), (None, None)])
def test_os_default_on_windows(monkeypatch, progid, expected):
    monkeypatch.setattr(platforms, "windows_https_progid", lambda: progid)
    assert browsers.os_default("win32") == expected


# Profiles (Task 7)

BRAVE_FOLDERS = ("Default", "Profile 1", "Profile 2", "Profile 3", "System Profile", "Guest Profile")


def data_folder(path: Path, local_state: bytes | None, folders=()) -> Path:
    """A browser's data folder: its Local State (unless None) and these profile folders."""
    path.mkdir(parents=True, exist_ok=True)
    if local_state is not None:
        (path / "Local State").write_bytes(local_state)
    for folder in folders:
        (path / folder).mkdir(exist_ok=True)
    return path


def local_state(drop=(), **changes) -> bytes:
    """The Brave sample's Local State with keys under "profile" changed, or dropped."""
    data = json.loads(sample("brave-local-state.json"))
    data["profile"].update(changes)
    for key in drop:
        data["profile"].pop(key)
    return json.dumps(data).encode("utf-8")


def one_profile(entry) -> bytes:
    return json.dumps({"profile": {"info_cache": {"Default": entry}}}).encode("utf-8")


def test_profiles_read_name_colour_and_order(tmp_path):
    data = data_folder(tmp_path / "Brave", sample("brave-local-state.json"), BRAVE_FOLDERS)
    expected = [browsers.Profile("Default", "Personal", "#3f51b5", False),
                browsers.Profile("Profile 1", "Work", "#1b5e20", True),
                browsers.Profile("Profile 2", "Profile 2", None, False)]
    assert browsers.profiles(data) == expected  # no System, Guest, ephemeral or folderless profile
    (data / "Local State").write_bytes(local_state(profiles_order=["Profile 4", "Profile 3", "Profile 2",
                                                                   "Profile 1", "Default"]))
    assert browsers.profiles(data) == expected[::-1]
    (data / "Local State").write_bytes(local_state(drop=("profiles_order",)))
    assert browsers.profiles(data) == expected  # Default first, then the rest sorted
    (data / "Profile 5").mkdir()
    assert [profile.folder for profile in browsers.profiles(data)] == ["Default", "Profile 1", "Profile 2"]


def test_profiles_never_return_an_email(tmp_path):
    data = data_folder(tmp_path / "Brave", sample("brave-local-state.json"), BRAVE_FOLDERS)
    shown = repr(browsers.profiles(data))
    for secret in ("alex@example.com", "Alex Example", "Alex", "123456789012345678901", "@"):
        assert secret not in shown
    assert browsers.profiles(data)[2] == browsers.Profile("Profile 2", "Profile 2", None, False)
    assert [field.name for field in dataclasses.fields(browsers.Profile)] == ["folder", "name", "color", "last_used"]


@pytest.mark.parametrize("name, shown", [
    ("\u202eevil\x07", "evil"), ("x" * 200, "x" * 64), ("   ", "Default"), (" Work ", "Work"),
    ("Alex (alex@example.com)", "Default"),  # an email among other words never comes out either
    ("\u200e\u2066\u202e\x1b", "Default"),  # only invisible characters: blank
    (42, "Default"),
    pytest.param("\ud800", "Default", id="a lone surrogate"),  # dropped: a page's socket can't send one
    pytest.param("Work\udfff", "Work", id="a lone surrogate after a name"),
    pytest.param("\u200b\u2060\ufeff", "Default", id="zero-width characters only"),
    pytest.param("\u200b" * 64 + "Work", "Default", id="nothing visible in the first 64 characters"),
    pytest.param("\u061cWork", "Work", id="the Arabic letter mark")])  # a bidi control too
def test_profile_names_are_cleaned(tmp_path, name, shown):
    data = data_folder(tmp_path / "Brave", one_profile({"name": name}), ["Default"])
    found = browsers.profiles(data)
    assert [profile.name for profile in found] == [shown]
    brave = browsers.Installed(browsers.by_id("brave"), Path("program"), None, None, data)
    page = browsers.public([browsers.Found(brave, "not_running", tuple(found), (), False)])
    json.dumps(page, ensure_ascii=False).encode("utf-8")  # what a page's socket sends: never a UnicodeEncodeError


@pytest.mark.parametrize("value, color", [
    (-16777216, "#000000"), (-1, "#ffffff"), (4282339765, "#3f51b5"), (-12627531, "#3f51b5"), (True, None),
    ("#fff", None), (2**40, None), (None, None)])
def test_colours(tmp_path, value, color):
    data = data_folder(tmp_path / "Brave", one_profile({"name": "Personal", "profile_highlight_color": value}),
                       ["Default"])
    assert [profile.color for profile in browsers.profiles(data)] == [color]


BAD_FOLDERS = ["../Default", "/etc", "a/b", "a\\b", "C:x", "", ".", "..", "nul\x00here", "x" * 65]


def test_a_profile_folder_name_cannot_leave_the_data_folder(tmp_path):
    assert not any(browsers.plain_folder(name) for name in BAD_FOLDERS) and not browsers.plain_folder(None)
    assert browsers.plain_folder("Default") and browsers.plain_folder("Profile 12")
    cache = {name: {"name": "Sneaky"} for name in [*BAD_FOLDERS, "Profile 1"]}
    data = data_folder(tmp_path / "Brave", json.dumps({"profile": {"info_cache": cache}}).encode("utf-8"),
                       ["Profile 1"])
    (tmp_path / "Default").mkdir()  # beside the data folder: "../Default" names it
    if os.name != "nt":
        (data / "C:x").mkdir()  # on Windows "C:x" is a path on drive C:, not a folder name
    assert [profile.folder for profile in browsers.profiles(data)] == ["Profile 1"]


# Folder names Chromium never makes and a page can't show safely: a bidi override, an email, nothing visible, a lone
# surrogate. A profile with no name of its own is labelled with its folder's name.
UNSHOWABLE_FOLDERS = ["Profile \u202e1gpj.exe", "alex@example.com", "\u200b", " ", "Profile \ud800"]


def test_a_profile_folder_a_page_cannot_show_is_skipped(tmp_path):
    assert not any(browsers.plain_folder(name) for name in UNSHOWABLE_FOLDERS)
    cache = {name: {"name": ""} for name in [*UNSHOWABLE_FOLDERS, "Profile 1"]}  # blank: the folder's name shows
    data = data_folder(tmp_path / "Brave", json.dumps({"profile": {"info_cache": cache}}).encode("utf-8"),
                       ["Profile 1"])
    for name in UNSHOWABLE_FOLDERS:
        with contextlib.suppress(OSError, ValueError):  # Windows refuses " ", and no disk takes a lone surrogate
            (data / name).mkdir()
    assert [(profile.folder, profile.name) for profile in browsers.profiles(data)] == [("Profile 1", "Profile 1")]


def test_each_profile_is_listed_once(tmp_path):
    state = {"profile": {"info_cache": {"Default": {"name": "Personal"}, "Profile 1": {"name": "Work"},
                                        "Profile 3": {"name": "Gone", "is_ephemeral": True}},
                         "profiles_order": ["Profile 1", "Default", "Profile 1", "Default"], "last_used": "Profile 3"}}
    data = data_folder(tmp_path / "Brave", json.dumps(state).encode("utf-8"), ["Default", "Profile 1", "Profile 3"])
    assert browsers.profiles(data) == [browsers.Profile("Profile 1", "Work", None, False),
                                       browsers.Profile("Default", "Personal", None, False)]


@pytest.mark.parametrize("contents, shown", [
    pytest.param(lambda: None, [], id="missing file"),
    pytest.param(lambda: b"", [], id="empty file"),
    pytest.param(lambda: sample("brave-local-state.json")[:300], [], id="cut JSON"),
    pytest.param(lambda: b"[]", [], id="a list"),
    pytest.param(lambda: b'{"profile": "Default"}', [], id="profile is a string"),
    pytest.param(lambda: b'{"profile": {"info_cache": ["Default"]}}', [], id="info_cache is a list"),
    pytest.param(lambda: b'{"profile": {"info_cache": {"Default": 7, "Profile 1": {"name": "Work"}}}}',
                 ["Profile 1:Work"], id="an entry is a number"),
    pytest.param(lambda: b'{"profile": {"info_cache": {"Default": {"name": 7}}}}', ["Default:Default"],
                 id="name is a number"),
    pytest.param(lambda: b'{"profile": {"info_cache": {"Default": {"name": "A"}}, "profiles_order": [1, null]}}',
                 ["Default:A"], id="order holds numbers"),
    pytest.param(lambda: b'{"profile": {"info_cache": {"Default": {"name": "A"}}, "profiles_order": ["\xff\xfe"]}}',
                 ["Default:A"], id="invalid UTF-8"),
    pytest.param(lambda: b'{"profile": {"profiles_order": ' + b"[" * 10000 + b"]" * 10000 + b"}}", [],
                 id="10,000 nested lists"),
    pytest.param(lambda: many_profiles(48000), [], id="48,000 profiles under the size cap"),
])
def test_profiles_fail_safely(tmp_path, contents, shown):
    data = data_folder(tmp_path / "Brave", contents(), ["Default", "Profile 1"])
    started = time.perf_counter()
    found = browsers.profiles(data)
    assert time.perf_counter() - started < 2  # linear: a hostile file under the cap never hangs Settings
    assert [f"{profile.folder}:{profile.name}" for profile in found] == shown


def many_profiles(count: int) -> bytes:
    """A Local State under the size cap: `count` profiles in info_cache and `count` other folders in profiles_order,
    names of one length, none on disk. Matching the two lists pair by pair takes seconds; with a set, milliseconds."""
    return json.dumps({"profile": {"info_cache": {f"Profile {number:08d}a": {} for number in range(count)},
                                   "profiles_order": [f"Profile {number:08d}b" for number in range(count)]}}
                      ).encode("utf-8")


def test_profiles_fail_safely_on_odd_files(tmp_path, monkeypatch):
    data = data_folder(tmp_path / "Brave", None, ["Default"])
    (data / "Local State").mkdir()  # a folder called Local State
    assert browsers.profiles(data) == []
    (data / "Local State").rmdir()
    if hasattr(os, "mkfifo"):
        os.mkfifo(data / "Local State")  # a plain read would wait forever
        assert browsers.profiles(data) == []
        (data / "Local State").unlink()
    (data / "Local State").write_bytes(b"")
    os.truncate(data / "Local State", 17 * 1024 * 1024)
    reads = recording_reads(monkeypatch)
    assert browsers.profiles(data) == [] and reads == []  # 17 MB: not read at all
    if os.name != "nt" and os.geteuid() != 0:  # root reads any folder
        locked = data_folder(tmp_path / "Locked", sample("brave-local-state.json"), ["Default"])
        locked.chmod(0)  # Path.is_file() would raise PermissionError here
        try:
            assert browsers.profiles(locked) == []
        finally:
            locked.chmod(0o700)


# Watcher copies (Task 8)

WATCHER_ID, OTHER_ID = "mnopmnopmnopmnopmnopmnopmnopmnop", "ijklijklijklijklijklijklijklijkl"
SAMPLE_ID = "aaaabbbbccccddddeeeeffffgggghhhh"  # the watcher's entry in the samples


def preferences(profile: Path, file_name: str, watcher_folder, extension_id: str = WATCHER_ID,
                sample_name: str = "secure-preferences-watcher.json", **changes) -> None:
    """A profile's Secure Preferences or Preferences: the sample's watcher entry, under `extension_id`, loaded from
    `watcher_folder`, with `changes` made to the entry. json.dumps writes a Windows path with its escapes."""
    data = json.loads(sample(sample_name))
    settings = data["extensions"]["settings"]
    entry = settings.pop(SAMPLE_ID)
    entry["path"] = str(watcher_folder)
    entry.update(changes)
    settings[extension_id] = entry
    profile.mkdir(parents=True, exist_ok=True)
    (profile / file_name).write_bytes(json.dumps(data).encode("utf-8"))


def brave_data(tmp_path) -> Path:
    return data_folder(tmp_path / "Brave", sample("brave-local-state.json"), BRAVE_FOLDERS)


def test_watcher_places(tmp_path):
    data, watcher = brave_data(tmp_path), tmp_path / "watcher"
    watcher.mkdir()
    watchers = {WATCHER_ID: watcher}
    profile_1 = [browsers.WatcherPlace("Profile 1", WATCHER_ID)]
    preferences(data / "Profile 1", "Secure Preferences", watcher)
    assert browsers.watcher_places(data, watchers) == profile_1
    preferences(data / "Default", "Preferences", watcher)  # only in Preferences: counts too
    assert browsers.watcher_places(data, watchers) == [browsers.WatcherPlace("Default", WATCHER_ID), *profile_1]
    for disabled in ({"disable_reasons": [1]}, {"disable_reasons": 1}, {"state": 0}):
        preferences(data / "Default", "Preferences", watcher, **disabled)
        assert browsers.watcher_places(data, watchers) == profile_1, disabled
    preferences(data / "Default", "Preferences", tmp_path / "another-folder")
    assert browsers.watcher_places(data, watchers) == profile_1
    preferences(data / "Default", "Preferences", watcher, extension_id=OTHER_ID)  # not one of the watchers
    assert browsers.watcher_places(data, watchers) == profile_1
    preferences(data / "Profile 1", "Preferences", watcher)  # enabled here, but Secure Preferences says disabled
    preferences(data / "Profile 1", "Secure Preferences", watcher, sample_name="preferences-watcher-disabled.json")
    assert browsers.watcher_places(data, watchers) == []


def test_the_same_watcher_in_two_profiles_is_listed_twice(tmp_path):
    data, watcher = brave_data(tmp_path), tmp_path / "watcher"
    for profile in ("Default", "Profile 1"):
        preferences(data / profile, "Secure Preferences", watcher)
    assert browsers.watcher_places(data, {WATCHER_ID: watcher}) == [browsers.WatcherPlace("Default", WATCHER_ID),
                                                                    browsers.WatcherPlace("Profile 1", WATCHER_ID)]


def test_watcher_paths_ignore_case_only_on_windows(tmp_path):
    data = brave_data(tmp_path)
    default = [browsers.WatcherPlace("Default", WATCHER_ID)]

    def places(folder, system):
        return browsers.watcher_places(data, {WATCHER_ID: folder}, system=system)

    preferences(data / "Default", "Secure Preferences", "c:\\users\\alex\\.ai-browser\\app\\watcher")
    assert places("C:\\Users\\Alex\\.ai-browser\\app\\watcher", "win32") == default
    assert places("C:\\Users\\Alex\\.ai-browser\\app\\watcher\\", "win32") == default  # a trailing separator
    assert places("C:\\Users\\Alex\\.ai-browser\\app\\watcher2", "win32") == []
    if os.name != "nt":  # Windows' realpath restores the case found on disk
        watcher = tmp_path / "home" / ".ai-browser" / "app" / "watcher"
        watcher.mkdir(parents=True)
        preferences(data / "Default", "Secure Preferences", watcher.parent / "WATCHER")
        assert places(watcher, "darwin") == []  # the id hashes the exact path: other case is another copy
        preferences(data / "Default", "Secure Preferences", f"{watcher}/")
        assert places(watcher, "darwin") == default


@pytest.mark.parametrize("contents", [
    pytest.param(lambda folder: b"{broken", id="broken file"),
    pytest.param(lambda folder: {"extensions": []}, id="extensions is a list"),
    pytest.param(lambda folder: {"extensions": {"settings": "x"}}, id="settings is a string"),
    pytest.param(lambda folder: {"extensions": {"settings": {WATCHER_ID: {"path": 7}}}}, id="path is a number"),
    pytest.param(lambda folder: {"extensions": {"settings": {WATCHER_ID: {"path": str(folder),
                                                                          "disable_reasons": "none"}}}},
                 id="disable_reasons is a string"),
    pytest.param(lambda folder: {"extensions": {"settings": {WATCHER_ID: {"path": f"{folder}\0x"}}}},
                 id="path holds a NUL"),
    pytest.param(lambda folder: {"extensions": {"settings": {WATCHER_ID: ["path", str(folder)]}}},
                 id="the entry is a list"),
    pytest.param(lambda folder: {"extensions": {"settings": {WATCHER_ID: {"path": "/x/" + "a/" * 320000}}}},
                 id="a path of 320,000 parts under the size cap"),
])
def test_watcher_places_fail_safely(tmp_path, contents):
    data, watcher = brave_data(tmp_path), tmp_path / "watcher"
    watcher.mkdir()
    written = contents(watcher)
    (data / "Default" / "Secure Preferences").write_bytes(
        written if isinstance(written, bytes) else json.dumps(written).encode("utf-8"))
    started = time.perf_counter()
    assert browsers.watcher_places(data, {WATCHER_ID: watcher}) == []
    assert time.perf_counter() - started < 2  # linear: a hostile path never hangs Settings


# Running, the switch and the state (Task 9)


def test_running_reads_the_lock_on_mac_and_linux(tmp_path):
    lock = tmp_path / "SingletonLock"
    assert browsers.running(tmp_path, "darwin") is False  # no lock: not running
    symlink_or_skip(f"{socket.gethostname()}-{os.getpid()}", lock)
    assert browsers.running(tmp_path, "darwin") is True
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=30)
    for target, expected in ((f"{socket.gethostname()}-{child.pid}", False),  # exited and waited for
                             (f"elsewhere.local-{os.getpid()}", None), ("garbage", None),
                             (f"{socket.gethostname()}-99999999999", None)):  # too big for os.kill: no OverflowError
        lock.unlink()
        os.symlink(target, lock)
        assert browsers.running(tmp_path, "darwin") is expected, target
    lock.unlink()
    lock.write_bytes(b"not a link")
    assert browsers.running(tmp_path, "darwin") is None


def test_a_host_name_with_dashes(tmp_path, monkeypatch):
    monkeypatch.setattr(browsers.socket, "gethostname", lambda: "Alexs-Mac-Book.local")
    lock = tmp_path / "SingletonLock"
    symlink_or_skip(f"Alexs-Mac-Book.local-{os.getpid()}", lock)
    assert browsers.running(tmp_path, "darwin") is True  # split at the last dash
    lock.unlink()
    os.symlink("Alexs-Mac-Book.local-", lock)
    assert browsers.running(tmp_path, "darwin") is None


def test_running_on_windows_only_looks_for_the_lockfile(tmp_path, monkeypatch):
    import builtins

    lock = tmp_path / "lockfile"
    assert browsers.running(tmp_path, "win32") is False
    lock.write_bytes(b"")
    if os.name != "nt":
        lock.chmod(0)

    def refusing(real):
        def opener(file, *args, **kwargs):
            if isinstance(file, (str, os.PathLike)) and Path(file).name == "lockfile":
                pytest.fail(f"the lockfile was opened: {file}")
            return real(file, *args, **kwargs)
        return opener

    monkeypatch.setattr(builtins, "open", refusing(builtins.open))
    monkeypatch.setattr(platforms, "open_shared", refusing(platforms.open_shared))
    try:
        assert browsers.running(tmp_path, "win32") is True
    finally:
        lock.chmod(0o600)


def test_the_switch_check_sends_nothing(tmp_path):
    server = socket.create_server(("127.0.0.1", 0))
    port, received = server.getsockname()[1], []

    def serve():
        connection, _ = server.accept()
        with connection:
            connection.settimeout(5)
            received.append(connection.recv(1024))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        (tmp_path / "DevToolsActivePort").write_bytes(f"{port}\n/devtools/browser/x\n".encode("utf-8"))
        assert browsers.devtools_port(tmp_path) == port
        assert browsers.listening(port) is True
        thread.join(timeout=10)
    finally:
        server.close()
    assert received == [b""]  # connected and closed: no HTTP request, no websocket


class Listener:
    """A port on 127.0.0.1 that accepts in a thread and keeps what each connection sent before it closed: the switch
    check may connect, but must send nothing (no HTTP request and no websocket, so no "Allow remote debugging?")."""

    def __init__(self):
        self.server = socket.create_server(("127.0.0.1", 0))
        self.server.settimeout(0.2)
        self.port, self.received, self._stop = self.server.getsockname()[1], [], threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        while True:
            try:
                connection, _ = self.server.accept()
            except TimeoutError:
                if self._stop.is_set():
                    return  # every connection made before close() has been read
                continue
            except OSError:
                return
            with connection:
                connection.settimeout(5)
                try:
                    self.received.append(connection.recv(1024))
                except OSError as error:  # still open after 5 s: it waits for an answer
                    self.received.append(repr(error))

    def close(self) -> list:
        """Stop listening once every waiting connection is read; what each connection sent."""
        self._stop.set()
        self._thread.join(timeout=10)
        self.server.close()
        return self.received


@pytest.mark.parametrize("alive, answers, expected", [
    (False, True, "not_running"), (True, True, "switch_on"), (True, False, "switch_off"), (None, True, "switch_on"),
    (None, False, "not_running")])
def test_state_combines_the_lock_and_the_switch(tmp_path, monkeypatch, alive, answers, expected):
    monkeypatch.setattr(browsers, "running", lambda data_dir, system=None: alive)
    listener = Listener()
    try:
        if not answers:
            listener.close()
        (tmp_path / "DevToolsActivePort").write_bytes(f"{listener.port}\n/devtools/browser/x\n".encode("utf-8"))
        assert browsers.state(tmp_path) == expected
    finally:
        received = listener.close()
    assert received == ([b""] if answers and alive is not False else [])  # one check that sent nothing, or none


@pytest.mark.parametrize("contents", [None, b"abc\n/x\n", b"0\n/x\n", b"70000\n/x\n", "\u00b2\n/x\n".encode("utf-8"),
                                      b""], ids=["no port file", "abc", "0", "70000", "superscript two", "empty"])
def test_a_running_browser_without_a_usable_port_has_its_switch_off(tmp_path, monkeypatch, contents):
    monkeypatch.setattr(browsers, "running", lambda data_dir, system=None: True)
    if contents is not None:
        (tmp_path / "DevToolsActivePort").write_bytes(contents)
    assert browsers.devtools_port(tmp_path) is None
    assert browsers.state(tmp_path) == "switch_off"


def test_the_port_file_may_end_its_lines_with_crlf(tmp_path):
    (tmp_path / "DevToolsActivePort").write_bytes(b"9222\r\n/devtools/browser/x\r\n")
    assert browsers.devtools_port(tmp_path) == 9222


def test_a_missing_data_folder_is_not_running(tmp_path):
    assert browsers.state(tmp_path / "missing") == "not_running" and browsers.state(None) == "not_running"


def test_a_stale_port_of_a_stopped_browser_is_never_checked(tmp_path, monkeypatch):
    (tmp_path / "DevToolsActivePort").write_bytes(b"9222\n/devtools/browser/old\n")
    monkeypatch.setattr(browsers, "running", lambda data_dir, system=None: False)
    monkeypatch.setattr(browsers, "listening", lambda port, timeout=0.5: pytest.fail("a stopped browser's port"))
    assert browsers.state(tmp_path) == "not_running"


# All together (Task 10)


def fake_mac(fake, port: int) -> SimpleNamespace:
    """Brave (running, its switch on, the watcher in Profile 1), Chrome (not running) and Edge on the fake Mac."""
    mac_app(fake.apps, "Brave Browser.app", sample("brave-info.plist"), "Brave Browser")
    mac_app(fake.apps, "Google Chrome.app", sample("chrome-info.plist"), "Google Chrome")
    mac_app(fake.apps, "Microsoft Edge.app", info_plist("com.microsoft.edgemac", "Microsoft Edge"), "Microsoft Edge")
    brave = data_folder(browsers.data_dir(browsers.by_id("brave"), "darwin"), sample("brave-local-state.json"),
                        BRAVE_FOLDERS)
    symlink_or_skip(f"{socket.gethostname()}-{os.getpid()}", brave / "SingletonLock")
    (brave / "DevToolsActivePort").write_bytes(f"{port}\n/devtools/browser/x\n".encode("utf-8"))
    watcher = fake.home / ".ai-browser" / "app" / "watcher"
    watcher.mkdir(parents=True)
    preferences(brave / "Profile 1", "Secure Preferences", watcher)
    chrome = data_folder(browsers.data_dir(browsers.by_id("chrome"), "darwin"), sample("chrome-local-state.json"),
                         ["Default"])
    edge = data_folder(browsers.data_dir(browsers.by_id("edge"), "darwin"), sample("brave-local-state.json"),
                       ["Default"])
    record = platforms.launch_services_file()
    record.parent.mkdir(parents=True)
    record.write_bytes(sample("launchservices.plist"))
    for profile in [*(brave / name for name in BRAVE_FOLDERS), chrome / "Default", edge / "Default"]:
        for decoy in ("Cookies", "Login Data", "History", "Web Data"):
            (profile / decoy).write_bytes(b"SQLite format 3\x00decoy")
    return SimpleNamespace(brave=brave, chrome=chrome, edge=edge, watchers={WATCHER_ID: watcher})


def shown_profile(folder, name, color, last_used, watcher=False, shared_watcher=False) -> dict:
    return {"folder": folder, "name": name, "color": color, "last_used": last_used, "watcher": watcher,
            "shared_watcher": shared_watcher}


EXPECTED = [
    {"id": "brave", "name": "Brave", "agents": True, "default": True, "state": "switch_on",
     "profiles": [shown_profile("Default", "Personal", "#3f51b5", False),
                  shown_profile("Profile 1", "Work", "#1b5e20", True, watcher=True),
                  shown_profile("Profile 2", "Profile 2", None, False)]},
    {"id": "chrome", "name": "Chrome", "agents": True, "default": False, "state": "not_running",
     "profiles": [shown_profile("Default", "Your Chrome", None, True)]},
    {"id": "edge", "name": "Edge", "agents": False, "default": False, "state": None, "profiles": []},
]


def test_detect_lists_installed_browsers_with_their_state_profiles_and_watchers(fake, monkeypatch):
    listener = Listener()
    try:
        mac = fake_mac(fake, listener.port)
        seen, real_read = [], browsers._read
        monkeypatch.setattr(browsers, "_read", lambda path: seen.append(Path(path)) or real_read(path))
        found = browsers.detect(mac.watchers, system="darwin")
    finally:
        received = listener.close()
    assert received == [b""]  # one switch check, Brave's, and it sent nothing
    assert browsers.public(found, connected=()) == EXPECTED
    assert seen and not any(path.is_relative_to(mac.edge) for path in seen)  # agents can't use Edge: not read
    assert browsers.detect(mac.watchers, system="linux") == []


def test_public_has_no_paths_or_emails(fake, tmp_path):
    listener = Listener()
    try:
        found = browsers.detect(fake_mac(fake, listener.port).watchers, system="darwin")
    finally:
        received = listener.close()
    assert received == [b""]  # the switch check sent nothing
    text = json.dumps(browsers.public(found))
    for secret in (str(tmp_path), tmp_path.as_posix(), "@", "Library", "Alex", "123456789012345678901", WATCHER_ID,
                   "152.1"):
        assert secret not in text
    shown = browsers.public(found, connected=("brave",))
    assert [browser["state"] for browser in shown] == ["connected", "not_running", None]
    assert all(set(browser) == {"id", "name", "agents", "default", "state", "profiles"} for browser in shown)
    assert all(set(profile) == {"folder", "name", "color", "last_used", "watcher", "shared_watcher"}
               for browser in shown for profile in browser["profiles"])
    assert [browser["state"] for browser in browsers.public(found, connected=("edge", "firefox"))] == [
        "switch_on", "not_running", None]  # Edge has no state to replace, and an unknown id adds nothing


def found_for(browser_id: str, folders, places) -> "browsers.Found":
    """A Found with these profile folders, and the watcher enabled in `places`."""
    browser = browsers.Installed(browsers.by_id(browser_id), Path("program"), None, None, Path("data"))
    return browsers.Found(browser, "not_running", tuple(browsers.Profile(f, f, None, False) for f in folders),
                          tuple(browsers.WatcherPlace(f, WATCHER_ID) for f in places), False)


def test_the_same_watcher_in_two_profiles_is_reported():
    def marks(*found):
        return [[(profile["folder"], profile["watcher"], profile["shared_watcher"]) for profile in browser["profiles"]]
                for browser in browsers.public(list(found))]

    assert marks(found_for("brave", ["Default", "Profile 1"], ["Default", "Profile 1"])) == [
        [("Default", True, True), ("Profile 1", True, True)]]
    assert marks(found_for("brave", ["Default"], ["Default"]), found_for("chrome", ["Default"], ["Default"])) == [
        [("Default", True, True)], [("Default", True, True)]]  # Chrome gives the same folder the same id
    assert marks(found_for("brave", ["Default", "Profile 1"], ["Profile 1"]), found_for("chrome", ["Default"], [])) == [
        [("Default", False, False), ("Profile 1", True, False)], [("Default", False, False)]]


READ_NAMES = {"Info.plist", "Local State", "Secure Preferences", "Preferences", "DevToolsActivePort",
              "com.apple.launchservices.secure.plist"}
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
_OPENED: list | None = None
_HOOKED: list = []


def _note_open(event, args):
    """The "open" audit event's path and flags (open() and os.open() both raise it with the OS flags they ask for)."""
    if _OPENED is not None and event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
        flags = args[2] if len(args) > 2 and isinstance(args[2], int) else None
        _OPENED.append((os.fsdecode(args[0]), flags))


@contextlib.contextmanager
def recording_opens():
    """(path, flags) of every file opened in the block, by any code (an audit hook: it can't be removed, so it
    records only while the block runs)."""
    global _OPENED
    if not _HOOKED:
        sys.addaudithook(_note_open)
        _HOOKED.append(_note_open)
    _OPENED = opened = []
    try:
        yield opened
    finally:
        _OPENED = None


def snapshot(root: Path) -> dict:
    """Every file, folder and link under root: its mtime, and its bytes or link target. Links are not followed."""
    tree = {}
    for folder, folders, files in os.walk(root):
        for name in [*folders, *files]:
            path = Path(folder, name)
            content = os.readlink(path) if path.is_symlink() else path.read_bytes() if path.is_file() else None
            tree[path.relative_to(root).as_posix()] = (path.lstat().st_mtime_ns, content)
    return tree


def test_detection_reads_only_its_files_and_writes_nothing(fake, tmp_path, monkeypatch):
    listener = Listener()
    try:
        mac = fake_mac(fake, listener.port)
        shared, real = [], platforms.open_shared
        monkeypatch.setattr(platforms, "open_shared", lambda path: shared.append(os.fspath(path)) or real(path))
        before = snapshot(tmp_path)
        with recording_opens() as opened:
            browsers.detect(mac.watchers, system="darwin")
        after = snapshot(tmp_path)
    finally:
        received = listener.close()
    inside = [(Path(path), flags) for path, flags in opened if Path(path).is_relative_to(tmp_path)]
    names = {path.name for path, _ in inside} | {Path(path).name for path in shared
                                                 if Path(path).is_relative_to(tmp_path)}
    assert "Local State" in {Path(path).name for path, _ in opened}  # the audit hook sees every open
    assert names <= READ_NAMES, names - READ_NAMES  # never Cookies, Login Data, History or Web Data
    assert [path.name for path, flags in inside if flags is None or flags & WRITE_FLAGS] == []  # each open: read only
    assert after == before  # nothing written, touched or created
    assert received == [b""]  # and the one switch check sent nothing


@pytest.mark.parametrize("name", [
    "brave-local-state.json", "chrome-local-state.json", "secure-preferences-watcher.json",
    "preferences-watcher-disabled.json", "brave-info.plist", "chrome-info.plist", "launchservices.plist",
    "launchservices.plist (binary)"])
def test_every_read_survives_a_truncated_file(fake, name):
    data = sample(name.removesuffix(" (binary)"))
    if name.endswith("(binary)"):
        data = plistlib.dumps(plistlib.loads(data), fmt=plistlib.FMT_BINARY)
    mac_app(fake.apps, "Brave Browser.app", sample("brave-info.plist"), "Brave Browser")
    brave = data_folder(browsers.data_dir(browsers.by_id("brave"), "darwin"), sample("brave-local-state.json"),
                        BRAVE_FOLDERS)
    record = platforms.launch_services_file()
    record.parent.mkdir(parents=True)
    record.write_bytes(sample("launchservices.plist"))
    watchers = {SAMPLE_ID: "/Users/Alex/.ai-browser/app/watcher"}
    for size in sorted({0, *range(1, len(data), 37)}):
        piece = data[:size]
        if name.endswith("local-state.json"):
            (brave / "Local State").write_bytes(piece)
            browsers.profiles(brave)
        elif "preferences" in name:
            (brave / "Default" / "Secure Preferences").write_bytes(piece)
            browsers.watcher_places(brave, watchers)
        elif "info" in name:
            mac_app(fake.apps, "Brave Browser.app", piece, "Brave Browser")
            browsers.installed(system="darwin")
        else:
            record.write_bytes(piece)
            browsers.os_default("darwin")
        browsers.public(browsers.detect(watchers, system="darwin"))  # and the whole detection, with that piece


# The README (Task 11)


def test_the_readme_says_what_detection_reads():
    from ai_browser.config import project_root

    text = (project_root() / "README.md").read_text(encoding="utf-8")
    development = " ".join(text.split("## Development", 1)[1].split())
    assert "**Browser detection** (`src/ai_browser/browsers.py`)" in development
    assert ("for each browser that runs, or whose lock can't tell, opens a TCP connection to 127.0.0.1 that sends "
            "nothing") in development
    assert 'so it never makes your browser ask "Allow remote debugging?"' in development
    assert ("It never opens cookies, saved passwords or history; it reads only what it needs, and never keeps or shows "
            "your account's email.") in development
    assert "browsers.public(browsers.detect({extension_id_for(w): w})" in development


# The files of this track (final review)


def test_the_detection_files_hold_no_invisible_characters():
    """Bidi controls and other invisible format characters (Unicode category Cf) are written as escapes in these
    files, never as the characters themselves: in source they can make code read differently from what runs (Trojan
    Source), and a review can't see them."""
    root = Path(__file__).parent.parent
    files = [root / "src" / "ai_browser" / "browsers.py", root / "src" / "ai_browser" / "platforms.py",
             Path(__file__), Path(__file__).parent / "test_platforms.py", *sorted(SAMPLES.iterdir())]
    hidden = {}
    for file in files:
        found = sorted({f"U+{ord(char):04X}" for char in file.read_text(encoding="utf-8")
                        if unicodedata.category(char) == "Cf"})
        if found:
            hidden[file.name] = found
    assert hidden == {}
