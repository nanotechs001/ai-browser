"""The sandbox's browser without Docker (the no-Docker spec): a separate browser on this computer. AI Browser starts the
installed Google Chrome (else Brave) on a profile of its own, <home>/sandboxes/<profile>/profile (0700): none of the
user's logins, cookies or history, and never one of the user's own profile folders (chrome.launch refuses them).
- Headless, with Chromium's own sandbox on (no --no-sandbox). Logging in and bot checks use the live view, as in
  Docker.
- One browser per profile, shared by every session on it, as the container was. Its record, browser.json (its pid,
  its program, whether it is a throwaway), lets stop and `ai-browser stop --all` find it.
- Its DevTools port is on 127.0.0.1 only, named in the profile's own DevToolsActivePort, inside the 0700 folder.
- A throwaway (fresh) profile is removed when its browser stops; the work folder stays, as in Docker.
- Its downloads stay in the sandbox's folders, never the user's Downloads, even while no session is connected.
- Lock files a browser left are cleared only once its process is gone. A process counts as the profile's browser only
  when its command line names the profile (macOS, Linux), or this process started it for this profile.
- Folders that are links (the sandboxes folder, a profile's, its profile, Default, Preferences), and the user's own
  browser folders, are refused before anything is touched, again once the profile's lock is held, and the
  preferences are written without following a link.
It is a separate profile on this computer, not a separate machine: Settings and the README say so."""

from __future__ import annotations

import contextlib
import errno
import json
import os
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import platforms
from .chrome import (ChromeError, _listening, _port_of, _same_folder, brave_binary, chrome_binary, launch,
                     own_browser_dirs)
from .sandbox import PROFILE_RE, SandboxInfo
from .syncdir import write_atomic

READY_TIMEOUT = 20  # seconds a new browser gets to answer
ANSWER_WAIT = 5.0  # seconds a running browser gets to answer before it is said not to
STOP_WAIT = 10  # seconds a browser gets to close by itself before it is ended
KILL_WAIT = 5  # seconds an ended browser gets to be gone
LOCK_MARGIN = 15  # seconds beyond a holder's worst case that a start or stop waits for the profile's start lock
RECORD = "browser.json"
LOCKS = ("SingletonLock", "SingletonSocket", "SingletonCookie", "lockfile", "DevToolsActivePort")
# As Docker's Chromium runs (docker/entrypoint.sh), minus --no-sandbox: Chromium's own sandbox stays on here
FLAGS = ("--disable-extensions", "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
         "--disable-backgrounding-occluded-windows", "--disable-features=Translate,MediaRouter",
         "--disable-smooth-scrolling", "--mute-audio", "--password-store=basic")
MAC_FLAGS = ("--use-mock-keychain",)  # the user's Keychain is never asked
NO_BROWSER = ("Without Docker, the sandbox needs Google Chrome or Brave on this computer: install one, or start Docker "
              "Desktop and pick Docker in Settings → Sandbox")
_launched: dict[int, subprocess.Popen] = {}  # browsers this process started: polled, so one that ended is reaped


def sandbox_binary() -> str | None:
    """The browser the local sandbox runs: Google Chrome ($AIB_CHROME_BINARY too), else Brave. Never downloaded."""
    return chrome_binary() or brave_binary()


def _alive(pid: int) -> bool:
    process = _launched.get(pid)
    return process.poll() is None if process is not None else platforms.pid_alive(pid)


def _holds(pid: int, profile: Path) -> bool:
    """Whether pid still is the profile's browser. A zombie (a browser that ended, its parent not yet told) isn't: ps
    shows no command line for it, and a launched process is polled. Windows has no ps: a pid this process didn't start
    only counts while it lives (its port said it was the profile's)."""
    if platforms.WINDOWS and pid not in _launched:
        return _alive(pid)
    return _runs_profile(pid, profile)


def _kill(pid: int) -> None:
    """End the browser and its helpers: it leads a process group of its own (launch's detach), so the group goes."""
    with contextlib.suppress(OSError):
        if hasattr(os, "killpg") and os.getpgid(pid) == pid:
            os.killpg(pid, signal.SIGKILL)
        else:
            os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))


def _answers(profile: Path) -> bool:
    """Whether the profile's browser answers: its DevToolsActivePort names a port that takes a connection."""
    found = _port_of(profile)
    return found is not None and _listening(found[0])


def _is_link(path: Path) -> bool:
    """Whether the last step of the path is a link (a symbolic link, or a Windows junction: the real path of the step
    isn't its parent's real path plus its name)."""
    return path.is_symlink() or os.path.realpath(path) != os.path.join(os.path.realpath(path.parent), path.name)


def _link_words(name: str) -> str:
    return (f"the sandbox folders for profile {name} include a link, or one of your own browser's folders: AI Browser "
            "won't use or change them. Remove the link, then try again")


def _preferences(data: object, folder: Path) -> bytes:
    data = data if isinstance(data, dict) else {}
    for key in ("download", "savefile"):
        data[key] = {**(data.get(key) if isinstance(data.get(key), dict) else {}), "default_directory": str(folder)}
    data["download"]["prompt_for_download"] = False
    return json.dumps(data).encode("utf-8")


def _keep_downloads_in(profile: Path, folder: Path) -> None:
    """Downloads land in the sandbox's own folder even while no session says where: CDP's download choice ends with the
    session that set it, and the browser's own default is the user's Downloads folder. The profile's preference,
    written before each start (the browser isn't running then), names the sandbox's folder instead. Nothing here
    follows a link, in case one was put there after the checks (to the user's real profile, say): each step is opened
    from the one before it (macOS, Linux); Windows can't, so it checks each step right before the write. Also the
    profile's mode: none of the user's other programs' business (mkdir's mode is cut by the umask)."""
    words = _link_words(profile.parent.name)
    path = profile / "Default" / "Preferences"
    if platforms.WINDOWS:
        if any(_is_link(step) for step in (profile, profile / "Default", path)):
            raise ChromeError(words)
        os.chmod(profile, 0o700)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        write_atomic(path, _preferences(data, folder), 0o600)
        return
    folder_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        root = os.open(profile, folder_flags)
        try:
            os.fchmod(root, 0o700)
            with contextlib.suppress(FileExistsError):
                os.mkdir("Default", 0o700, dir_fd=root)
            default = os.open("Default", folder_flags, dir_fd=root)
        finally:
            os.close(root)
        try:
            try:
                with os.fdopen(os.open("Preferences", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=default), "rb") as handle:
                    data = json.loads(handle.read().decode("utf-8"))
            except (OSError, ValueError) as exc:
                if getattr(exc, "errno", None) == errno.ELOOP:
                    raise
                data = {}
            temp = f".Preferences.{os.getpid()}.tmp"
            try:
                with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600,
                                       dir_fd=default), "wb") as handle:
                    os.fchmod(handle.fileno(), 0o600)
                    handle.write(_preferences(data, folder))
                os.rename(temp, "Preferences", src_dir_fd=default, dst_dir_fd=default)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(temp, dir_fd=default)
                raise
        finally:
            os.close(default)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):  # a link (macOS says ENOTDIR for a linked folder)
            raise ChromeError(words) from None
        raise


def _lock_pid(profile: Path) -> int | None:
    """The pid in Chromium's SingletonLock (a link to "host-pid"; Windows has none), or None."""
    try:
        tail = os.readlink(profile / "SingletonLock").rsplit("-", 1)[-1]
    except OSError:
        return None
    return int(tail) if tail.isdigit() else None


def _runs_profile(pid: int, profile: Path) -> bool:
    """Whether a running process is a browser on this profile: this process started it for this profile (and it still
    runs), or (macOS, Linux) its command line names the profile folder. Never a guess from a pid alone: pids are
    reused, so a launched process vouches only for the profile it was started on, and once it has ended its pid is
    anyone's."""
    process = _launched.get(pid)
    if process is not None:
        if process.poll() is None:
            return f"--user-data-dir={profile}" in process.args
        _launched.pop(pid, None)
    if platforms.WINDOWS or not platforms.pid_alive(pid):
        return False
    try:
        line = subprocess.run(["ps", "-ww", "-o", "command=", "-p", str(pid)], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return f"--user-data-dir={profile} " in line.strip() + " "


class LocalSandboxes:
    """sandbox.Sandboxes' calls for the engine (start, ws_url, stop, is_running), and running() for `stop --all`."""

    def __init__(self, home: Path):
        self.home = Path(home).resolve()  # one spelling: the ps check below compares the profile's path as written

    def _folder(self, profile: str) -> Path:
        return self.home / "sandboxes" / profile

    def start(self, profile: str = "default", fresh: bool = False) -> SandboxInfo:
        if fresh:
            profile = "fresh-" + secrets.token_hex(3)
        elif profile in ("chrome", "app"):  # their folders and sessions belong to your-own-Chrome mode and AI Browser
            raise ValueError(f"profile {profile!r} is reserved (your own Chrome and AI Browser use it): pick another "
                             "profile name")
        elif profile.startswith("fresh-"):  # a throwaway's name: stop removes its profile
            raise ValueError(f"profile {profile!r} is reserved (names starting with fresh- are throwaway sandboxes): "
                             "pick another profile name")
        elif not PROFILE_RE.match(profile):
            raise ValueError(f"profile {profile!r}: use lowercase letters, digits and dashes (max 31)")
        folder = self._folder(profile)
        self._refuse_unsafe(folder)
        folder.mkdir(parents=True, exist_ok=True)
        work_host = folder / "work"
        with self._one_start(folder):  # (which checks again, with the lock held)
            work_host.mkdir(exist_ok=True)
            port, created = self._running_port(folder), False
            if port is None:
                port, created = self._launch(folder, fresh), True
        return SandboxInfo(f"aib-{profile}", profile, f"http://127.0.0.1:{port}", work_host, fresh, created,
                           local=True)

    @staticmethod
    def _unsafe(folder: Path) -> str | None:
        """Why the profile's folders can't be used, or None: a link anywhere on the way (a way into some other folder,
        maybe a browser's of the user), or one of the user's own browser folders. Checked before anything is touched
        (launch refuses those too, but only after locks, preferences and modes were changed) and again once the lock is
        held: a link may appear while a start waits."""
        profile = folder / "profile"
        steps = (folder.parent, folder, profile, profile / "Default", profile / "Default" / "Preferences")
        if any(_is_link(step) for step in steps) or any(_same_folder(profile, own) for own in own_browser_dirs()):
            return _link_words(folder.name)
        return None

    def _refuse_unsafe(self, folder: Path) -> None:
        problem = self._unsafe(folder)
        if problem is not None:
            raise ChromeError(problem)

    @contextlib.contextmanager
    def _one_start(self, folder: Path):
        """One start or stop of a profile's browser at a time, across processes: two sessions starting at once share
        one. The wait covers a holder's worst case (it waits for an answer, launches, then stops what didn't answer).
        A lock is per open file: a start that has to stop its browser calls _end, never stop."""
        deadline = time.monotonic() + ANSWER_WAIT + READY_TIMEOUT + STOP_WAIT + KILL_WAIT + LOCK_MARGIN
        while True:
            self._refuse_unsafe(folder)  # before each try: opening the lock file follows a link that came meanwhile
            if (lock := platforms.lock_file(folder / "start.lock")) is not None:
                break
            if time.monotonic() > deadline:
                raise ChromeError(f"another start or stop of the sandbox browser for profile {folder.name} didn't "
                                  "finish: try again")
            time.sleep(0.1)
        try:
            self._refuse_unsafe(folder)  # and with the lock held: nothing below follows a link that came while waiting
            yield
        finally:
            lock.close()

    def _record(self, folder: Path) -> dict:
        try:
            data = json.loads((folder / RECORD).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _owner(self, folder: Path) -> int | None:
        """The pid of the browser that holds the profile (its record's, else its lock's), or None when none runs (or
        the folder isn't one to use: nothing in it is read as a browser's then)."""
        profile = folder / "profile"
        if self._unsafe(folder) is not None:
            return None
        recorded = self._record(folder).get("pid")
        if isinstance(recorded, int) and recorded > 0:
            if _runs_profile(recorded, profile):
                return recorded
            if platforms.WINDOWS and platforms.pid_alive(recorded) and _answers(profile):  # no ps: its port says
                return recorded
        locked = _lock_pid(profile)
        return locked if locked is not None and _runs_profile(locked, profile) else None

    def _clear(self, folder: Path, stopping: bool = False) -> None:
        """No browser holds the profile: the lock files, the port file and the record it left are stale."""
        profile = folder / "profile"
        try:
            for name in LOCKS:
                platforms.unlink(profile / name, missing_ok=True)  # SingletonLock links to nothing: never exists()
            platforms.unlink(folder / RECORD, missing_ok=True)
        except PermissionError:  # Windows: a browser still holds its lockfile
            if stopping:  # the command that would be named is the one just run
                raise ChromeError(f"a browser still holds the sandbox profile {folder.name} and can't be ended from "
                                  "here: end it in Task Manager (a Chrome or Brave with its folder "
                                  f"{profile}), then try again") from None
            raise ChromeError(f"another browser holds the sandbox profile {folder.name}: run "
                              f"`{platforms.command('stop ' + folder.name)}`, then try again") from None

    def _running_port(self, folder: Path) -> int | None:
        """The DevTools port of the profile's browser, when one runs and answers; None when none runs (what it left
        is cleared then). One that runs but doesn't answer is never touched: ChromeError."""
        pid = self._owner(folder)
        if pid is None:
            self._clear(folder)
            return None
        deadline = time.monotonic() + ANSWER_WAIT
        while True:
            found = _port_of(folder / "profile")
            if found is not None and _listening(found[0]):
                return found[0]
            if not _holds(pid, folder / "profile"):
                self._clear(folder)
                return None
            if time.monotonic() > deadline:
                raise ChromeError(f"the sandbox browser for profile {folder.name} runs but doesn't answer: run "
                                  f"`{platforms.command('stop ' + folder.name)}`, then try again")
            time.sleep(0.1)

    def _launch(self, folder: Path, fresh: bool) -> int:
        binary = sandbox_binary()
        if binary is None:
            raise ChromeError(NO_BROWSER)
        profile = folder / "profile"
        profile.mkdir(parents=True, exist_ok=True)
        (folder / "downloads").mkdir(exist_ok=True)  # there before the browser could write a download to its place
        flags = FLAGS + (MAC_FLAGS if sys.platform == "darwin" else ())
        try:
            _keep_downloads_in(profile, folder / "downloads")  # (and the profile's mode)
            process = launch(profile, headless=True, extra_args=flags, binary=binary, detach=True)
        except BaseException:
            self._discard(folder, fresh)
            raise
        _launched[process.pid] = process
        write_atomic(folder / RECORD, json.dumps({"pid": process.pid, "binary": binary, "fresh": fresh}).encode(
            "utf-8"), 0o600)
        deadline = time.monotonic() + READY_TIMEOUT
        while True:
            found = _port_of(profile)
            if found is not None and _listening(found[0]):
                return found[0]
            if process.poll() is not None:
                self._clear(folder)
                self._discard(folder, fresh)
                raise ChromeError(f"the sandbox browser ({Path(binary).name}) stopped as it started (exit "
                                  f"{process.returncode}): try again, or run `{platforms.command('doctor')}`")
            if time.monotonic() > deadline:
                self._end(folder)  # (not stop: this start holds the lock)
                raise ChromeError(f"the sandbox browser ({Path(binary).name}) didn't answer within {READY_TIMEOUT}s")
            time.sleep(0.1)

    def _discard(self, folder: Path, fresh: bool) -> None:
        """A throwaway whose browser never ran leaves no profile behind: its record, which would tell stop, is gone."""
        self._refuse_unsafe(folder)
        if fresh and (folder / "profile").exists():
            platforms.rmtree(folder / "profile")

    def ws_url(self, info: SandboxInfo) -> str:
        found = _port_of(self._folder(info.profile) / "profile")
        if found is None or not _listening(found[0]):
            raise ChromeError(f"the sandbox browser for profile {info.profile} isn't running any more: try again")
        return f"ws://127.0.0.1:{found[0]}{found[1]}"

    @staticmethod
    def _close(profile: Path) -> None:
        """Ask the browser to close (CDP Browser.close): it saves its profile and ends its own helper processes."""
        found = _port_of(profile)
        if found is None or not _listening(found[0]):
            return
        from websockets.sync.client import connect

        with contextlib.suppress(Exception):
            with connect(f"ws://127.0.0.1:{found[0]}{found[1]}", open_timeout=3, close_timeout=1, max_size=None,
                         proxy=None) as ws:
                ws.send(json.dumps({"id": 1, "method": "Browser.close"}))
                ws.recv(timeout=3)

    @staticmethod
    def _wait_gone(pid: int, profile: Path, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while _holds(pid, profile) and time.monotonic() < deadline:
            time.sleep(0.1)

    def stop(self, name: str) -> None:
        """Stop a profile's browser (its logins stay in its profile); a throwaway profile is removed with it."""
        profile = name.removeprefix("aib-")
        folder = self._folder(profile)
        if not PROFILE_RE.match(profile) or not folder.is_dir():
            return
        with self._one_start(folder):  # (which refuses a link, before and after it takes the lock)
            self._end(folder)

    def _end(self, folder: Path) -> None:
        """stop's work, with the profile's start lock held by the caller."""
        self._refuse_unsafe(folder)  # before it clears or removes anything
        profile = folder / "profile"
        throwaway = self._record(folder).get("fresh") is True  # never from the name: a named profile keeps its logins
        pid = self._owner(folder)
        if pid is not None:
            self._close(profile)
            self._wait_gone(pid, profile, STOP_WAIT)
            # still the profile's own browser, checked again right before (a pid can be given to another process)
            if _holds(pid, profile) and (pid in _launched or not platforms.WINDOWS):
                _kill(pid)
                self._wait_gone(pid, profile, KILL_WAIT)
            _launched.pop(pid, None)
        self._clear(folder, stopping=True)
        if throwaway and (folder / "profile").exists():
            platforms.rmtree(folder / "profile")

    def is_running(self, name: str) -> bool:
        profile = name.removeprefix("aib-")
        return bool(PROFILE_RE.match(profile)) and self._owner(self._folder(profile)) is not None

    def running(self) -> list[str]:
        """The names (aib-<profile>) of this home's local sandbox browsers that run now."""
        root = self.home / "sandboxes"
        folders = sorted(path for path in root.iterdir() if path.is_dir()) if root.is_dir() else []
        return [f"aib-{folder.name}" for folder in folders
                if PROFILE_RE.match(folder.name) and self._owner(folder) is not None]
