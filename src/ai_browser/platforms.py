"""What differs between macOS, Windows and Linux: folders, names, wording, and the few OS calls that differ.

Two kinds of function live here:
- pure ones take `system` (sys.platform's values: "darwin", "win32", "linux") and `env` (os.environ by default), both
  read at call time, so the Mac's tests can ask for any OS;
- the ones that use the real OS branch on WINDOWS (os.name == "nt", read at call time, never sys.platform). Their
  Win32 calls go through ctypes.WinDLL("kernel32", use_last_error=True) and read errors with ctypes.get_last_error().

Every macOS-only path of the project is written here and nowhere else (tests/test_portable.py checks it)."""

from __future__ import annotations

import contextlib
import ctypes
import functools
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import IO, BinaryIO

WINDOWS = os.name == "nt"
O_BINARY = getattr(os, "O_BINARY", 0)  # without it, os.open on Windows turns every "\n" written into "\r\n"


@dataclass(frozen=True)
class BrowserFacts:
    """One known browser: its names, where its app and its data folder are on each OS, and what AI Browser may do
    with it. `agents`: offered under "Where agents browse" (its remote-debugging switch works as measured in Brave
    and Chrome). `window`: it may draw the app window. `inspect`: the scheme of <scheme>://inspect/#remote-debugging.
    Paths are tuples of parts: `mac_data` under ~/Library/Application Support, `win_exe` under each Windows app
    folder, `win_data` under %LOCALAPPDATA%, `linux_data` under ~/.config. None: the browser has none there."""

    id: str
    name: str
    agents: bool
    window: bool
    inspect: str
    mac_app: str
    mac_bundle_id: str
    mac_data: tuple[str, ...]
    win_exe: tuple[str, ...] | None
    win_data: tuple[str, ...] | None
    win_progid: str | None = None
    linux_data: tuple[str, ...] | None = None


KNOWN_BROWSERS: tuple[BrowserFacts, ...] = (  # display order: Brave, Chrome, Chromium, then the ones agents can't use
    BrowserFacts("brave", "Brave", True, True, "brave", "Brave Browser.app", "com.brave.Browser",
                 ("BraveSoftware", "Brave-Browser"), ("BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
                 ("BraveSoftware", "Brave-Browser", "User Data"), win_progid="BraveHTML",
                 linux_data=("BraveSoftware", "Brave-Browser")),
    BrowserFacts("brave-beta", "Brave Beta", True, False, "brave", "Brave Browser Beta.app", "com.brave.Browser.beta",
                 ("BraveSoftware", "Brave-Browser-Beta"),
                 ("BraveSoftware", "Brave-Browser-Beta", "Application", "brave.exe"),
                 ("BraveSoftware", "Brave-Browser-Beta", "User Data")),
    BrowserFacts("brave-nightly", "Brave Nightly", True, False, "brave", "Brave Browser Nightly.app",
                 "com.brave.Browser.nightly", ("BraveSoftware", "Brave-Browser-Nightly"),
                 ("BraveSoftware", "Brave-Browser-Nightly", "Application", "brave.exe"),
                 ("BraveSoftware", "Brave-Browser-Nightly", "User Data")),
    BrowserFacts("chrome", "Chrome", True, True, "chrome", "Google Chrome.app", "com.google.Chrome",
                 ("Google", "Chrome"), ("Google", "Chrome", "Application", "chrome.exe"),
                 ("Google", "Chrome", "User Data"), win_progid="ChromeHTML", linux_data=("google-chrome",)),
    BrowserFacts("chrome-beta", "Chrome Beta", True, False, "chrome", "Google Chrome Beta.app",
                 "com.google.Chrome.beta", ("Google", "Chrome Beta"),
                 ("Google", "Chrome Beta", "Application", "chrome.exe"), ("Google", "Chrome Beta", "User Data")),
    BrowserFacts("chrome-dev", "Chrome Dev", True, False, "chrome", "Google Chrome Dev.app", "com.google.Chrome.dev",
                 ("Google", "Chrome Dev"), ("Google", "Chrome Dev", "Application", "chrome.exe"),
                 ("Google", "Chrome Dev", "User Data")),
    BrowserFacts("chrome-canary", "Chrome Canary", True, False, "chrome", "Google Chrome Canary.app",
                 "com.google.Chrome.canary", ("Google", "Chrome Canary"),
                 ("Google", "Chrome SxS", "Application", "chrome.exe"), ("Google", "Chrome SxS", "User Data")),
    BrowserFacts("chromium", "Chromium", True, False, "chrome", "Chromium.app", "org.chromium.Chromium",
                 ("Chromium",), ("Chromium", "Application", "chrome.exe"), ("Chromium", "User Data")),
    BrowserFacts("edge", "Edge", False, True, "edge", "Microsoft Edge.app", "com.microsoft.edgemac",
                 ("Microsoft Edge",), ("Microsoft", "Edge", "Application", "msedge.exe"),
                 ("Microsoft", "Edge", "User Data"), win_progid="MSEdgeHTM"),
    BrowserFacts("arc", "Arc", False, False, "chrome", "Arc.app", "company.thebrowser.Browser", ("Arc", "User Data"),
                 None, None),  # on Windows an MSIX package: no program path to look for
    BrowserFacts("vivaldi", "Vivaldi", False, False, "chrome", "Vivaldi.app", "com.vivaldi.Vivaldi", ("Vivaldi",),
                 ("Vivaldi", "Application", "vivaldi.exe"), ("Vivaldi", "User Data")),
)

# The two browsers the older helpers (user_data_dir, browser_candidates) know: views of their rows, as before.
_ROWS = {row.id: row for row in KNOWN_BROWSERS}
_MAC_DATA = {name: _ROWS[name].mac_data for name in ("chrome", "brave")}
_WINDOWS_DATA = {name: _ROWS[name].win_data for name in ("chrome", "brave")}
_LINUX_DATA = {name: _ROWS[name].linux_data for name in ("chrome", "brave")}
_MAC_APPS = {name: f"/Applications/{_ROWS[name].mac_app}/Contents/MacOS/{_ROWS[name].mac_app.removesuffix('.app')}"
             for name in ("chrome", "brave")}
_WINDOWS_APPS = {name: _ROWS[name].win_exe for name in ("chrome", "brave")}


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


def browser_data_dir(facts: BrowserFacts, system: str | None = None, env: Mapping | None = None) -> Path | None:
    """A known browser's folder of profiles on `system`, installed or not; None when it keeps none there. For brave
    and chrome it is user_data_dir()'s folder."""
    system, env = _system(system), _env(env)
    if system == "darwin":
        return Path.home().joinpath("Library", "Application Support", *facts.mac_data)
    if system == "win32":
        if facts.win_data is None:
            return None
        return _windows_folder(env, "LOCALAPPDATA", "AppData", "Local").joinpath(*facts.win_data)
    if facts.linux_data is None:
        return None
    return Path.home().joinpath(".config", *facts.linux_data)


def app_folders(system: str | None = None, env: Mapping | None = None) -> list[Path]:
    """Where apps are installed, in the order to look: /Applications then ~/Applications on macOS; on Windows
    %ProgramFiles%, %ProgramFiles(x86)% and %LOCALAPPDATA%, the ones that are set; none elsewhere."""
    system, env = _system(system), _env(env)
    if system == "darwin":
        return [Path("/Applications"), Path.home() / "Applications"]
    if system == "win32":
        return [Path(env[name]) for name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA") if env.get(name)]
    return []


def launch_services_file() -> Path:
    """macOS's record of the default app for each URL scheme (its https entry names the default browser)."""
    return Path.home().joinpath("Library", "Preferences", "com.apple.LaunchServices",
                                "com.apple.launchservices.secure.plist")


def lock_name(system: str | None = None) -> str:
    """The file a running Chromium browser holds in its data folder."""
    return "lockfile" if _system(system) == "win32" else "SingletonLock"


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


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
ERROR_ACCESS_DENIED = 5


@functools.cache
def _kernel32():
    """kernel32 with the prototypes used here (Windows only: ctypes.WinDLL exists nowhere else)."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle, dword, boolean = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int
    kernel32.OpenProcess.argtypes, kernel32.OpenProcess.restype = (dword, boolean, dword), handle
    kernel32.GetExitCodeProcess.argtypes = (handle, ctypes.POINTER(dword))
    kernel32.GetExitCodeProcess.restype = boolean
    kernel32.CloseHandle.argtypes, kernel32.CloseHandle.restype = (handle,), boolean
    kernel32.CreateJobObjectW.argtypes, kernel32.CreateJobObjectW.restype = (ctypes.c_void_p, ctypes.c_wchar_p), handle
    kernel32.SetInformationJobObject.argtypes = (handle, ctypes.c_int, ctypes.c_void_p, dword)
    kernel32.SetInformationJobObject.restype = boolean
    kernel32.AssignProcessToJobObject.argtypes, kernel32.AssignProcessToJobObject.restype = (handle, handle), boolean
    kernel32.CreateFileW.argtypes = (ctypes.c_wchar_p, dword, dword, ctypes.c_void_p, dword, dword, handle)
    kernel32.CreateFileW.restype = handle
    return kernel32


GENERIC_READ = 0x80000000
FILE_SHARE_READ, FILE_SHARE_WRITE, FILE_SHARE_DELETE = 0x1, 0x2, 0x4
OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL = 3, 0x80
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


def open_shared(path) -> BinaryIO:
    """Open a file for reading only (binary), never in the way of the program that owns it. On Windows a plain open
    doesn't share delete access, so a browser saving its Local State (a new file, then ReplaceFile, which first
    renames the old one away) would fail while we read; this open shares read, write and delete access."""
    if not WINDOWS:
        return open(path, "rb")
    import msvcrt  # Windows only

    kernel32 = _kernel32()
    handle = kernel32.CreateFileW(str(path), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                                  None, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None)
    if not handle or handle == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | O_BINARY)
    except BaseException:
        kernel32.CloseHandle(handle)
        raise
    try:
        return os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)  # closes the handle with it
        raise


_APP_PATHS = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
_START_MENU_INTERNET = r"SOFTWARE\Clients\StartMenuInternet"
_START_MENU_INTERNET_32 = r"SOFTWARE\WOW6432Node\Clients\StartMenuInternet"
_HTTPS_CHOICE = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https"
_REGISTERED_PROGRAMS = ("brave.exe", "chrome.exe", "msedge.exe", "vivaldi.exe")


def windows_browser_commands() -> list[str]:
    """Where Windows' registry says browsers are installed, as command strings: App Paths for each known program
    (current user first), then Windows' own list of registered browsers (StartMenuInternet) in HKCU, HKLM and HKLM's
    32-bit view. Read only: keys are opened with KEY_READ and nothing is ever created, set or deleted. [] elsewhere."""
    if not WINDOWS:
        return []
    import winreg  # Windows only

    user, machine = winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE
    found = [_registry_text(winreg, root, rf"{_APP_PATHS}\{program}", "")
             for program in _REGISTERED_PROGRAMS for root in (user, machine)]
    for root, key in ((user, _START_MENU_INTERNET), (machine, _START_MENU_INTERNET),
                      (machine, _START_MENU_INTERNET_32)):
        found += [_registry_text(winreg, root, rf"{key}\{name}\shell\open\command", "")
                  for name in _registry_subkeys(winreg, root, key)]
    return [command for command in found if command]


def windows_https_progid() -> str | None:
    """The ProgId of the user's default browser for https links (Windows 11 25H2 writes UserChoiceLatest, older
    Windows UserChoice), or None. Read only; None elsewhere."""
    if not WINDOWS:
        return None
    import winreg  # Windows only

    for key in (rf"{_HTTPS_CHOICE}\UserChoiceLatest\ProgId", rf"{_HTTPS_CHOICE}\UserChoiceLatest",
                rf"{_HTTPS_CHOICE}\UserChoice"):
        value = _registry_text(winreg, winreg.HKEY_CURRENT_USER, key, "ProgId")
        if value:
            return value
    return None


def _registry_text(winreg, root, key: str, name: str) -> str | None:
    """A string value, stripped, or None: a missing key, an unreadable one or a value of another type."""
    try:
        with winreg.OpenKey(root, key, 0, winreg.KEY_READ) as handle:
            value, _ = winreg.QueryValueEx(handle, name)
    except OSError:
        return None
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _registry_subkeys(winreg, root, key: str) -> list[str]:
    """The names of a key's subkeys (at most 256), or [] when the key can't be opened."""
    names = []
    try:
        with winreg.OpenKey(root, key, 0, winreg.KEY_READ) as handle:
            for index in range(256):
                try:
                    names.append(winreg.EnumKey(handle, index))
                except OSError:  # no more subkeys
                    break
    except OSError:
        return []
    return names


def pid_alive(pid: int) -> bool:
    """Whether a process still runs. Never a signal: on Windows, os.kill(pid, 0) sends Ctrl-C to a console group."""
    if pid <= 0:
        return False
    if WINDOWS:
        return _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # it runs, as another user
        return True
    return True


def _windows_pid_alive(pid: int) -> bool:
    kernel32 = _kernel32()
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ctypes.get_last_error() == ERROR_ACCESS_DENIED  # it exists, but isn't ours to look at
    try:
        code = ctypes.c_uint32()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


class _WindowsLock:
    """The lock file's handle on Windows. close() unlocks the byte before closing: Windows may release the lock of a
    closed file late, and the next start must not find it taken."""

    def __init__(self, handle):
        self._handle = handle

    @property
    def closed(self) -> bool:
        return self._handle.closed

    def close(self) -> None:
        import msvcrt  # Windows only

        if self._handle.closed:
            return
        with contextlib.suppress(OSError):
            self._handle.seek(0)
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
        self._handle.close()


def lock_file(path) -> IO | _WindowsLock | None:
    """An exclusive lock on `path`, held until the returned object's close(); None when another holder has it. If
    the holder dies, the OS releases the lock either way."""
    handle = open(path, "a+b")
    if WINDOWS:
        import msvcrt  # Windows only

        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            handle.close()
            return None
        return _WindowsLock(handle)
    import fcntl  # POSIX only

    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
PROCESS_TERMINATE, PROCESS_SET_QUOTA = 0x0001, 0x0100


class _BasicLimits(ctypes.Structure):  # JOBOBJECT_BASIC_LIMIT_INFORMATION
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", ctypes.c_uint32), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", ctypes.c_uint32),
                ("SchedulingClass", ctypes.c_uint32)]


class _IoCounters(ctypes.Structure):  # IO_COUNTERS
    _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount",
                                                     "OtherOperationCount", "ReadTransferCount",
                                                     "WriteTransferCount", "OtherTransferCount")]


class _ExtendedLimits(ctypes.Structure):  # JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    _fields_ = [("BasicLimitInformation", _BasicLimits), ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class KillOnCloseJob:
    """A Windows job object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: when its handle closes (the app's process
    ending, even by a crash), Windows ends every process in it, and the ones they started. Windows only."""

    def __init__(self):
        kernel32 = _kernel32()
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits),
                                                ctypes.sizeof(limits)):
            error = ctypes.get_last_error()
            kernel32.CloseHandle(handle)
            raise ctypes.WinError(error)
        self._handle = handle

    def add(self, pid: int) -> None:
        """Put a running process in the job; OSError when it can't (for example, it has already exited)."""
        kernel32 = _kernel32()
        process = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not kernel32.AssignProcessToJobObject(self._handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel32.CloseHandle(process)

    def close(self) -> None:
        """End every process in the job now. Tests call it; the app never does, its handle closes with the app."""
        if self._handle:
            _kernel32().CloseHandle(self._handle)
            self._handle = None
