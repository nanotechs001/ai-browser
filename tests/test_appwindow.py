"""AI Browser's window (app/window.py): which browser draws it, its exact command line, starting it and ending only
what it started. No test opens a visible window: the launch tests record Popen, and the one real launch (Task 13) is
headless."""

import subprocess
import sys

import pytest

from ai_browser.app import window

MAC_BOTH = {"chrome": "/x/Google Chrome", "brave": "/x/Brave Browser"}
ALL_THREE = {"edge": "C:\\Edge\\msedge.exe", "chrome": "C:\\Chrome\\chrome.exe", "brave": "C:\\Brave\\brave.exe"}


def picked(setting, system, installed, default=None):
    found = window.pick(setting, system=system, installed=installed, os_default=default)
    return None if found is None else (found.browser.id, found.browser.binary, found.note)


def test_auto_skips_the_everyday_browser_on_macos():
    assert picked("auto", "darwin", MAC_BOTH, "brave") == ("chrome", "/x/Google Chrome", "")  # this Mac's case
    assert picked("auto", "darwin", MAC_BOTH, "chrome")[0] == "brave"
    assert picked("auto", "darwin", {"brave": "/x/Brave Browser"}, "brave")[0] == "brave"  # nothing else to use
    assert picked("auto", "darwin", MAC_BOTH, None)[0] == "chrome"


def test_auto_on_windows_is_edge_first_with_no_skip():
    assert picked("auto", "win32", ALL_THREE, "chrome")[0] == "edge"
    assert picked("auto", "win32", ALL_THREE, "edge")[0] == "edge"  # no skip there
    assert picked("auto", "win32", {"chrome": "C:\\Chrome\\chrome.exe", "brave": "C:\\Brave\\brave.exe"})[0] == "chrome"


def test_auto_on_linux_is_chrome_then_brave():
    assert picked("auto", "linux", {"chrome": "/usr/bin/google-chrome", "brave": "/usr/bin/brave"})[0] == "chrome"
    assert picked("auto", "linux", {"brave": "/usr/bin/brave"})[0] == "brave"


def test_a_choice_that_cant_be_used_falls_back_to_auto_with_a_note():
    assert picked("brave", "darwin", {"chrome": "/x/Google Chrome"}) == (
        "chrome", "/x/Google Chrome", "Brave isn't installed: the window uses Google Chrome. Change it in Settings.")
    found = picked("edge", "darwin", MAC_BOTH, "brave")
    assert found[0] == "chrome" and found[2] == ("Microsoft Edge draws the window only on Windows: the window uses "
                                                 "Google Chrome. Change it in Settings.")
    assert picked("brave", "darwin", MAC_BOTH, "brave") == ("brave", "/x/Brave Browser", "")  # the user's choice wins
    assert picked("chrome", "win32", ALL_THREE)[0] == "chrome"
    assert picked("nonsense", "darwin", MAC_BOTH, "brave")[0] == "chrome"  # an unknown setting is Auto
    assert picked("auto", "darwin", {}) is None and picked("chrome", "win32", {}) is None


def test_offered_choices_per_system():
    assert window.offered("darwin") == ("auto", "chrome", "brave") == window.offered("linux")
    assert window.offered("win32") == ("auto", "edge", "chrome", "brave")
    assert set(window.offered("win32")) == set(window.WINDOW_CHOICES)


def test_choices_name_auto_after_its_pick():
    assert window.choices(system="darwin", installed={"chrome": "/x/c"}, os_default="brave") == [
        {"id": "auto", "name": "Auto (Google Chrome)", "installed": True},
        {"id": "chrome", "name": "Google Chrome", "installed": True},
        {"id": "brave", "name": "Brave", "installed": False}]
    rows = window.choices(system="win32", installed=ALL_THREE)
    assert [(row["id"], row["name"]) for row in rows] == [("auto", "Auto (Microsoft Edge)"), ("edge", "Microsoft Edge"),
                                                          ("chrome", "Google Chrome"), ("brave", "Brave")]
    assert window.choices(system="darwin", installed={})[0] == {"id": "auto", "name": "Auto", "installed": False}


def test_the_command_line_is_exactly_this(tmp_path):
    profile = tmp_path / "home" / "app" / "window" / "chrome"
    url = "http://127.0.0.1:8792/open?code=abc"
    args = window.window_args("/x/Google Chrome", profile, url)
    assert args == ["/x/Google Chrome", f"--user-data-dir={profile}", f"--app={url}", "--no-first-run",
                    "--no-default-browser-check", "--disable-search-engine-choice-screen", "--window-size=1440,960",
                    "--autoplay-policy=no-user-gesture-required"]
    banned = ("--remote-debugging", "--enable-automation", "--load-extension", "--headless", "--user-agent",
              "--disable-infobars", "--silent-debugger-extension-api")
    assert not [arg for arg in args if arg.startswith(banned)]
    assert window.window_profile(tmp_path / "home", "brave") == tmp_path / "home" / "app" / "window" / "brave"


def test_detection_never_reads_this_computers_apps(monkeypatch):
    from ai_browser import browsers

    monkeypatch.delenv("AIB_CHROME_BINARY", raising=False)
    for system in (None, "darwin", "win32"):
        assert browsers.installed(system=system) == [], system
    assert browsers.os_default() is None and browsers.os_default(system="darwin") is None


def test_aib_chrome_binary_is_chromes_program(tmp_path, monkeypatch):
    program = tmp_path / "chrome-bin"
    program.write_bytes(b"")
    monkeypatch.setenv("AIB_CHROME_BINARY", str(program))
    found = window.pick("auto")  # nothing is installed: the conftest fixture keeps detection off this computer
    assert (found.browser.id, found.browser.name, found.browser.binary) == ("chrome", "Google Chrome", str(program))
    monkeypatch.setenv("AIB_CHROME_BINARY", str(tmp_path / "missing"))
    if sys.platform in ("darwin", "win32"):  # on Linux the PATH finders still look
        assert window.pick("auto") is None
