"""What differs between macOS, Windows and Linux: folders, names, wording, and the few OS calls that differ.

Two kinds of function live here:
- pure ones take `system` (sys.platform's values: "darwin", "win32", "linux") and `env` (os.environ by default), both
  read at call time, so the Mac's tests can ask for any OS;
- the ones that use the real OS branch on WINDOWS (os.name == "nt", read at call time, never sys.platform). Their
  Win32 calls go through ctypes.WinDLL("kernel32", use_last_error=True) and read errors with ctypes.get_last_error().

Every macOS-only path of the project is written here and nowhere else (tests/test_portable.py checks it)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path

WINDOWS = os.name == "nt"
O_BINARY = getattr(os, "O_BINARY", 0)  # without it, os.open on Windows turns every "\n" written into "\r\n"

_MAC_DATA = {"chrome": ("Google", "Chrome"), "brave": ("BraveSoftware", "Brave-Browser")}
_WINDOWS_DATA = {"chrome": ("Google", "Chrome", "User Data"), "brave": ("BraveSoftware", "Brave-Browser", "User Data")}
_LINUX_DATA = {"chrome": ("google-chrome",), "brave": ("BraveSoftware", "Brave-Browser")}
_MAC_APPS = {"chrome": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
             "brave": "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"}
_WINDOWS_APPS = {"chrome": ("Google", "Chrome", "Application", "chrome.exe"),
                 "brave": ("BraveSoftware", "Brave-Browser", "Application", "brave.exe")}


def _system(system: str | None) -> str:
    return system or sys.platform


def _env(env: Mapping | None) -> Mapping:
    return os.environ if env is None else env


def _browser(browser: str) -> str:
    if browser not in _MAC_DATA:
        raise ValueError(f"unknown browser {browser!r}: chrome or brave")
    return browser


def _windows_folder(env: Mapping, name: str, *fallback: str) -> Path:
    """%LOCALAPPDATA% or %APPDATA%, or where Windows keeps it when the variable is missing."""
    value = env.get(name)
    return Path(value) if value else Path.home().joinpath(*fallback)


def user_data_dir(browser: str, system: str | None = None, env: Mapping | None = None) -> Path:
    """The browser's folder of profiles: where it writes DevToolsActivePort (on Windows, its "User Data")."""
    browser, system, env = _browser(browser), _system(system), _env(env)
    if system == "darwin":
        return Path.home().joinpath("Library", "Application Support", *_MAC_DATA[browser])
    if system == "win32":
        return _windows_folder(env, "LOCALAPPDATA", "AppData", "Local").joinpath(*_WINDOWS_DATA[browser])
    return Path.home().joinpath(".config", *_LINUX_DATA[browser])


def browser_candidates(browser: str, system: str | None = None, env: Mapping | None = None) -> list[Path]:
    """The usual places the browser's program is installed, in the order to try them."""
    browser, system, env = _browser(browser), _system(system), _env(env)
    if system == "darwin":
        return [Path(_MAC_APPS[browser])]
    if system == "win32":
        roots = [env.get(name) for name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
        return [Path(root, *_WINDOWS_APPS[browser]) for root in roots if root]
    return []


def claude_desktop_dir(system: str | None = None, env: Mapping | None = None) -> Path:
    """Where the Claude desktop app keeps its data, the skills synced from claude.ai among them."""
    system, env = _system(system), _env(env)
    if system == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude"
    if system == "win32":
        return _windows_folder(env, "APPDATA", "AppData", "Roaming") / "Claude"
    return Path.home() / ".config" / "Claude"


def file_manager(system: str | None = None) -> str:
    return {"darwin": "Finder", "win32": "File Explorer"}.get(_system(system), "your file manager")


def this_computer(system: str | None = None) -> str:
    return {"darwin": "this Mac", "win32": "this PC"}.get(_system(system), "this computer")


def shortcut(mac: str, other: str, system: str | None = None) -> str:
    """Wording that differs by keyboard: `mac` on macOS (⌘⇧Y), `other` elsewhere (Ctrl+Shift+Y)."""
    return mac if _system(system) == "darwin" else other


def reveal_command(path: str, system: str | None = None) -> list[str] | str | None:
    """The command that shows a folder in the file manager, selected; None when there is none."""
    system = _system(system)
    if system == "darwin":
        return ["open", "-R", str(path)]
    if system == "win32":
        # A string: explorer.exe parses its own command line, and a list would break on a space in the user name.
        # A Windows path can't contain ".
        return f'explorer /select,"{path}"'
    if shutil.which("xdg-open") is None:
        return None
    return ["xdg-open", os.path.dirname(str(path)) or "."]


def reveal(path: str) -> bool:
    """Show a folder in the file manager, selected; True when the command started."""
    command = reveal_command(path)
    if command is None:
        return False
    try:
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    return True


RETRY_WAITS = (0.05, 0.1, 0.2, 0.4)  # seconds between tries: Defender, Brave or an editor holds a file that long


def _retrying(action):
    """Run `action`; on Windows a PermissionError (a file another process holds open) is tried again, 5 times in
    all, then raised as before."""
    for wait in (*RETRY_WAITS, None):
        try:
            return action()
        except PermissionError:
            if not WINDOWS or wait is None:
                raise
            time.sleep(wait)


def replace(src, dst) -> None:
    _retrying(lambda: os.replace(src, dst))


def unlink(path, missing_ok: bool = False) -> None:
    _retrying(lambda: Path(path).unlink(missing_ok=missing_ok))


def rmtree(path) -> None:
    _retrying(lambda: shutil.rmtree(path))
