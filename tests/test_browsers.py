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
