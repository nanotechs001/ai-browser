"""What differs between macOS, Windows and Linux, tested on any OS through `system` and a fake `env`."""

import os
import sys
from pathlib import Path

import pytest

from ai_browser import platforms

WINDOWS_ENV = {"LOCALAPPDATA": "C:\\Users\\me\\AppData\\Local", "APPDATA": "C:\\Users\\me\\AppData\\Roaming",
               "ProgramFiles": "C:\\Program Files", "ProgramFiles(x86)": "C:\\Program Files (x86)"}


def test_browser_folders_for_each_system():
    home, support = Path.home(), Path.home() / "Library" / "Application Support"
    assert platforms.user_data_dir("chrome", "darwin") == support / "Google" / "Chrome"
    assert platforms.user_data_dir("brave", "darwin") == support / "BraveSoftware" / "Brave-Browser"
    local = "C:\\Users\\me\\AppData\\Local"
    assert platforms.user_data_dir("chrome", "win32", WINDOWS_ENV) == Path(local, "Google", "Chrome", "User Data")
    assert platforms.user_data_dir("brave", "win32", WINDOWS_ENV) == Path(local, "BraveSoftware", "Brave-Browser",
                                                                        "User Data")
    assert platforms.user_data_dir("chrome", "linux") == home / ".config" / "google-chrome"
    assert platforms.user_data_dir("brave", "linux") == home / ".config" / "BraveSoftware" / "Brave-Browser"
    with pytest.raises(ValueError):
        platforms.user_data_dir("firefox", "darwin")


def test_the_usual_install_places():
    assert platforms.browser_candidates("chrome", "darwin") == [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
    assert platforms.browser_candidates("brave", "darwin") == [
        Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")]
    assert platforms.browser_candidates("chrome", "win32", WINDOWS_ENV) == [
        Path(root, "Google", "Chrome", "Application", "chrome.exe")
        for root in ("C:\\Program Files", "C:\\Program Files (x86)", "C:\\Users\\me\\AppData\\Local")]
    assert platforms.browser_candidates("brave", "win32", {"LOCALAPPDATA": "C:\\L"}) == [
        Path("C:\\L", "BraveSoftware", "Brave-Browser", "Application", "brave.exe")]
    assert platforms.browser_candidates("chrome", "linux") == []


def test_the_claude_desktop_folder():
    assert platforms.claude_desktop_dir("darwin") == Path.home() / "Library" / "Application Support" / "Claude"
    assert platforms.claude_desktop_dir("win32", WINDOWS_ENV) == Path("C:\\Users\\me\\AppData\\Roaming", "Claude")
    assert platforms.claude_desktop_dir("linux") == Path.home() / ".config" / "Claude"


def test_words_for_each_system():
    systems = ("darwin", "win32", "linux")
    assert [platforms.file_manager(s) for s in systems] == ["Finder", "File Explorer", "your file manager"]
    assert [platforms.this_computer(s) for s in systems] == ["this Mac", "this PC", "this computer"]
    assert [platforms.shortcut("⌘⇧Y", "Ctrl+Shift+Y", s) for s in systems] == ["⌘⇧Y", "Ctrl+Shift+Y", "Ctrl+Shift+Y"]


def test_the_defaults_are_read_at_call_time(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", "C:\\Elsewhere")
    assert platforms.this_computer() == "this PC"
    assert platforms.user_data_dir("brave") == Path("C:\\Elsewhere", "BraveSoftware", "Brave-Browser", "User Data")


def test_reveal_commands(monkeypatch):
    assert platforms.reveal_command("/Users/me/x", "darwin") == ["open", "-R", "/Users/me/x"]
    assert platforms.reveal_command("C:\\Users\\a b\\x", "win32") == 'explorer /select,"C:\\Users\\a b\\x"'
    assert platforms.reveal_command("C:\\Users\\José & Ana\\x", "win32") == 'explorer /select,"C:\\Users\\José & Ana\\x"'
    monkeypatch.setattr(platforms.shutil, "which", lambda name: "/usr/bin/xdg-open" if name == "xdg-open" else None)
    assert platforms.reveal_command("/home/me/x/extension", "linux") == ["xdg-open", "/home/me/x"]
    monkeypatch.setattr(platforms.shutil, "which", lambda name: None)
    assert platforms.reveal_command("/home/me/x/extension", "linux") is None


def test_reveal_says_whether_a_folder_window_could_open(monkeypatch, tmp_path):
    if platforms.reveal_command(str(tmp_path)) is None:
        pytest.skip("this system has no file manager command")
    started = []
    monkeypatch.setattr(platforms.subprocess, "Popen", lambda command, **options: started.append(command) or object())
    assert platforms.reveal(str(tmp_path)) is True and started == [platforms.reveal_command(str(tmp_path))]

    def cannot_start(command, **options):
        raise OSError("no file manager")

    monkeypatch.setattr(platforms.subprocess, "Popen", cannot_start)
    assert platforms.reveal(str(tmp_path)) is False


def test_windows_is_read_from_os_name():
    assert platforms.WINDOWS == (os.name == "nt") and platforms.O_BINARY == getattr(os, "O_BINARY", 0)
