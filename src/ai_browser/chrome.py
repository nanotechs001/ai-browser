"""Connect to the user's own running browser, Brave or Google Chrome (its remote-debugging switch must be on: the user
turns it on themselves), and launch separate throwaway Chromes for tests and AI Browser."""

from __future__ import annotations

import ntpath
import os
import shutil
import socket
import subprocess
import sys  # noqa: F401 (kept: tests patch chrome.sys.platform, the one sys platforms reads)
import time
from pathlib import Path

from . import platforms

TICK = 'tick "Allow remote debugging for this browser instance"'


class ChromeError(RuntimeError):
    """The browser cannot be reached; the message says how to fix it."""


def own_browser_dirs() -> list[Path]:
    """Where the user's own browsers keep their profiles on this platform, Brave first."""
    return [platforms.user_data_dir("brave"), platforms.user_data_dir("chrome")]  # Brave first


def _port_of(folder: Path) -> tuple[int, str] | None:
    """(port, path) from the folder's DevToolsActivePort, or None."""
    try:
        lines = (Path(folder) / "DevToolsActivePort").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:  # missing, or the browser removed it as we read it (it is closing or restarting)
        return None
    if len(lines) >= 2 and lines[0].strip().isdigit():
        return int(lines[0].strip()), lines[1].strip()
    return None


def _listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def switch_on(folder: Path) -> bool:
    """Whether the browser's remote-debugging switch is on: its DevToolsActivePort names a port that accepts a TCP
    connection. A TCP check only: no debugging session is opened, so the browser never asks the user anything."""
    found = _port_of(folder)
    return found is not None and _listening(found[0])


def own_browser_dir() -> Path:
    """The user's browser folder: $AIB_CHROME_DIR; else the first candidate whose switch is on; else the first that
    exists (Brave before Chrome); else the first, so an error can name it."""
    configured = os.environ.get("AIB_CHROME_DIR")
    if configured:
        return Path(configured).expanduser()
    candidates = own_browser_dirs()
    return next((folder for folder in candidates if switch_on(folder)), None) \
        or next((folder for folder in candidates if folder.is_dir()), candidates[0])


default_chrome_dir = own_browser_dir  # its earlier name


def browser_name(folder: Path) -> str:
    """ "Brave" for a Brave folder, else "Chrome": the word every hint uses."""
    return "Brave" if "bravesoftware" in Path(folder).as_posix().lower() else "Chrome"


def inspect_address(folder: Path) -> str:
    """Where the user turns the remote-debugging switch on."""
    return f"{'brave' if browser_name(folder) == 'Brave' else 'chrome'}://inspect/#remote-debugging"


def allow_hint(folder: Path) -> str:
    return f"open {inspect_address(folder)} in {browser_name(folder)} and {TICK}, then try again"


_ON_PATH = {"chrome": (("chrome",), ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")),
            "brave": (("brave",), ("brave-browser",))}


def chrome_binary() -> str | None:
    """Google Chrome for AI Browser and the throwaway test browsers: $AIB_CHROME_BINARY as given, else the usual
    places, else Windows' App Paths record, else PATH."""
    configured = os.environ.get("AIB_CHROME_BINARY")
    if configured:
        return configured  # a wrong path shows up as "AI Browser could not start: …"
    return _installed("chrome")


def brave_binary() -> str | None:
    """Whether Brave is installed (doctor --setup says so). The app never starts the user's Brave."""
    return _installed("brave")


def _installed(browser: str) -> str | None:
    for candidate in platforms.browser_candidates(browser):
        if candidate.is_file():
            return str(candidate)
    if platforms.WINDOWS:
        found = _registry_path(f"{browser}.exe")
        if found:
            return found
    windows_names, other_names = _ON_PATH[browser]
    for name in windows_names if platforms.WINDOWS else other_names:
        found = shutil.which(name)
        if found:
            return found
    return None


def _registry_path(program: str) -> str | None:
    """Windows' own record of where a program is installed (App Paths), current user first."""
    import winreg  # Windows only

    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{program}") as key:
                value, _ = winreg.QueryValueEx(key, "")
        except OSError:
            continue
        path = str(value or "").strip().strip('"')
        if path and Path(path).is_file():
            return path
    return None


def _same_folder(a, b) -> bool:
    """Whether two paths name the same folder: resolved, and on Windows without regard to case."""
    left, right = os.path.realpath(a), os.path.realpath(b)
    if platforms.WINDOWS:
        return ntpath.normcase(left) == ntpath.normcase(right)
    return left == right


def find_ws_url(user_data_dir: Path, timeout: float = 0) -> str:
    """The browser websocket URL from DevToolsActivePort, waiting up to `timeout` seconds for it."""
    folder = Path(user_data_dir)
    name, hint = browser_name(folder), allow_hint(folder)
    deadline = time.monotonic() + timeout
    while True:
        problem = "missing"
        found = _port_of(folder)
        if found is not None:
            if _listening(found[0]):
                return f"ws://127.0.0.1:{found[0]}{found[1]}"
            problem = "stale"
        if time.monotonic() >= deadline:
            break
        time.sleep(0.1)
    if problem == "stale":
        raise ChromeError(f"{name} isn't running (or was restarted without remote debugging): open {name}; if it "
                          f"still fails, {hint}")
    if not folder.is_dir():
        raise ChromeError(f"no {name} profile folder at {folder}: install or open {name}, then {hint}")
    raise ChromeError(f"{name} doesn't allow remote debugging yet: {hint}")


def launch(user_data_dir: Path, headless: bool = True, extra_args: tuple[str, ...] = ()) -> subprocess.Popen:
    """Start a separate, throwaway Chrome with its own profile folder (never one of the user's own browsers')."""
    binary = chrome_binary()
    if binary is None:
        raise ChromeError("Google Chrome is not installed")
    folder = Path(user_data_dir)
    if any(_same_folder(folder, candidate) for candidate in own_browser_dirs()):  # never a real browser folder
        raise ChromeError("refusing to launch a browser on the user's own profile folder")
    folder.mkdir(parents=True, exist_ok=True)
    args = [binary, f"--user-data-dir={folder}", "--remote-debugging-port=0", "--no-first-run",
            "--no-default-browser-check", "--disable-search-engine-choice-screen", "--window-size=1440,960",
            "--use-mock-keychain"]  # a throwaway profile keeps no secrets: macOS never asks for a keychain for it
    if headless:
        args.append("--headless=new")
    args += [*extra_args, "about:blank"]
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
