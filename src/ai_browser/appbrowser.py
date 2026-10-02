"""Launch AI Browser: a Google Chrome with its own profile and our extension (AI Home and the chat panel).

Headed, AI Browser is a normal Chrome: started with a debugging port only, never with --remote-debugging-pipe, which
puts Chrome in automation mode (navigator.webdriver true on every page, so Google answered searches with its "unusual
traffic" page; measured with Chrome 154). Branded Chrome ignores --load-extension since version 137, so the user loads
the extension once (Developer mode, Load unpacked) from a fixed folder; Chrome derives its ID from that folder's path.

Headless launches (tests) still install the extension over the pipe with Extensions.loadUnpacked, for that run only;
Chrome quits when that pipe closes. The engine connects separately, through the debugging port."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import select
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from websockets.sync.client import connect

from .chrome import ChromeError, chrome_binary, find_ws_url

EXTENSION_SOURCE = Path(__file__).with_name("app") / "extension"
START_TIMEOUT = 20  # seconds for Chrome to start and open its debugging port
ALREADY_OPEN = ("AI Browser is already open (profile {}), maybe from an earlier run: quit it (⌘Q in its window), then "
                "start again")


class AppBrowserError(RuntimeError):
    """AI Browser could not start; the message says why and what to do."""


def app_profile(home: Path) -> Path:
    """AI Browser's own Chrome profile: its logins and extensions, apart from the user's browsers."""
    return Path(home) / "browser"


def prepare_extension(home: Path, server_url: str, token: str) -> Path:
    """Copy the side panel to home/app/extension (a fixed path keeps its ID) with the server's address and token."""
    folder = Path(home) / "app" / "extension"
    if folder.exists():
        shutil.rmtree(folder)
    shutil.copytree(EXTENSION_SOURCE, folder)
    config = os.open(folder / "config.json", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # holds the token
    with os.fdopen(config, "w") as handle:
        json.dump({"server": server_url, "token": token}, handle)
    return folder


def extension_id_for(folder: Path) -> str:
    """The ID Chrome gives an unpacked extension: from its folder's absolute path (SHA-256, 0-f mapped to a-p)."""
    digest = hashlib.sha256(os.path.realpath(folder).encode()).hexdigest()[:32]
    return "".join(chr(ord("a") + int(char, 16)) for char in digest)


def extension_installed(profile: Path, extension_dir: Path) -> bool:
    """Whether the user loaded our extension into this profile: Chrome records it in its Preferences files."""
    wanted, key = os.path.realpath(extension_dir), extension_id_for(extension_dir)
    for name in ("Secure Preferences", "Preferences"):
        try:
            path = json.loads((Path(profile) / "Default" / name).read_text())["extensions"]["settings"][key]["path"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if isinstance(path, str) and os.path.realpath(path) == wanted:
            return True
    return False


def chrome_args(binary: str, profile: Path, headless: bool, pipe: bool, urls) -> list[str]:
    """Chrome's command line. The pipe (tests only) installs the extension for one run; headed runs never use it."""
    args = [binary, f"--user-data-dir={profile}", "--remote-debugging-port=0", "--no-first-run",
            "--no-default-browser-check", "--disable-search-engine-choice-screen", "--window-size=1440,960"]
    if pipe:
        args += ["--remote-debugging-pipe", "--enable-unsafe-extension-debugging"]
    if headless:
        args.append("--headless=new")
    return [*args, *urls]  # none: Chrome's own start (AI Home, once the extension is in), not a blank tab


class _Pipe:
    """Chrome DevTools over --remote-debugging-pipe: NUL-separated JSON. Used only to install the side panel."""

    def __init__(self, to_chrome: int, from_chrome: int):
        self._out, self._in = to_chrome, from_chrome
        self._buffer = b""
        self._id = 0

    def call(self, method: str, params: dict, timeout: float = START_TIMEOUT) -> dict:
        self._id += 1
        os.write(self._out, json.dumps({"id": self._id, "method": method, "params": params}).encode() + b"\0")
        deadline = time.monotonic() + timeout
        while True:
            while b"\0" not in self._buffer:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AppBrowserError(f"Chrome did not answer {method} within {timeout:g} s")
                if not select.select([self._in], [], [], remaining)[0]:
                    continue
                chunk = os.read(self._in, 65536)
                if not chunk:
                    raise AppBrowserError("Chrome closed its DevTools pipe")
                self._buffer += chunk
            raw, self._buffer = self._buffer.split(b"\0", 1)
            message = json.loads(raw)
            if message.get("id") != self._id:
                continue  # an event
            if "error" in message:
                raise AppBrowserError(f"{method}: {message['error'].get('message', message['error'])}")
            return message.get("result", {})

    def drain(self) -> None:
        """Keep reading (and dropping) whatever Chrome sends, so its writes can never block."""
        def run() -> None:
            with contextlib.suppress(OSError):
                while os.read(self._in, 65536):
                    pass
        threading.Thread(target=run, name="aib-pipe-drain", daemon=True).start()

    def close(self) -> None:
        for fd in (self._out, self._in):
            with contextlib.suppress(OSError):
                os.close(fd)


@dataclass
class _Process:
    """Chrome, started with posix_spawn: Popen can keep descriptors open but not move them onto 3 and 4 (only with
    preexec_fn, which is unsafe once the app runs threads)."""

    pid: int
    returncode: int | None = None

    def poll(self) -> int | None:
        if self.returncode is None:
            try:
                pid, status = os.waitpid(self.pid, os.WNOHANG)
            except ChildProcessError:  # reaped elsewhere: it has exited, the code is lost
                self.returncode = -1
            else:
                if pid:
                    self.returncode = os.waitstatus_to_exitcode(status)
        return self.returncode

    def wait(self, timeout: float) -> int:
        deadline = time.monotonic() + timeout
        while self.poll() is None:
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired("Google Chrome", timeout)
            time.sleep(0.05)
        return self.returncode

    def _signal(self, number: int) -> None:
        if self.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.kill(self.pid, number)

    def terminate(self) -> None:
        self._signal(signal.SIGTERM)

    def kill(self) -> None:
        self._signal(signal.SIGKILL)


@dataclass
class AppBrowser:
    process: _Process
    ws_url: str
    extension_id: str
    profile: Path
    installed: bool  # our extension is in this profile (headless runs install it over the pipe)
    _pipe: _Pipe | None = field(repr=False, default=None)

    @property
    def closed(self) -> bool:
        return self.process.poll() is not None

    def close(self) -> None:
        """Quit AI Browser (closing the pipe, or Browser.close); it is stopped if it hasn't quit after 10 s."""
        if self._pipe is not None:
            self._pipe.close()
        elif not self.closed:
            with contextlib.suppress(Exception), connect(self.ws_url, max_size=None, open_timeout=5) as ws:
                ws.send(json.dumps({"id": 1, "method": "Browser.close"}))
                ws.recv(timeout=5)
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)


def launch_app_browser(profile: Path, extension_dir: Path, headless: bool = False, pipe_install: bool | None = None,
                       urls=()) -> AppBrowser:
    """Start AI Browser on its own profile, opening `urls`; refuses a profile already in use. Headed, it is a normal
    Chrome and the extension is whatever the user installed; headless (or pipe_install=True) installs it for the run."""
    binary = chrome_binary()
    if binary is None:
        raise AppBrowserError("Google Chrome is not installed: install it from google.com/chrome, then try again")
    profile = Path(profile)
    pipe = headless if pipe_install is None else pipe_install
    with contextlib.suppress(ChromeError):
        find_ws_url(profile)
        raise AppBrowserError(ALREADY_OPEN.format(profile))
    profile.mkdir(parents=True, exist_ok=True)
    (profile / "DevToolsActivePort").unlink(missing_ok=True)  # a stale one from a crash would mislead the wait
    installed = pipe or extension_installed(profile, extension_dir)
    actions = [(os.POSIX_SPAWN_OPEN, 1, os.devnull, os.O_WRONLY, 0), (os.POSIX_SPAWN_OPEN, 2, os.devnull, os.O_WRONLY, 0)]
    ours: list[int] = []  # our ends of the pipe
    if pipe:
        to_read, to_write = os.pipe()  # Chrome reads commands on fd 3...
        from_read, from_write = os.pipe()  # ...and writes answers on fd 4
        # Chrome's ends go above 9 first, so moving one onto 3 or 4 in the child can never overwrite the other.
        commands, answers = (fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 10) for fd in (to_read, from_write))
        for fd in (to_read, from_write):
            os.close(fd)
        actions = [(os.POSIX_SPAWN_DUP2, commands, 3), (os.POSIX_SPAWN_DUP2, answers, 4), *actions]
        ours = [to_write, from_read]
    urls = list(urls)
    first, later = (urls[:1], urls[1:]) if headless else (urls, [])  # headless Chrome takes one start page only
    args = chrome_args(binary, profile, headless, pipe, first)
    try:
        process = _Process(os.posix_spawn(binary, args, os.environ, file_actions=actions,
                                          setsigdef=(signal.SIGPIPE, signal.SIGXFSZ)))
    except OSError as exc:
        for fd in ours:
            os.close(fd)
        raise AppBrowserError(f"AI Browser could not start: {exc}") from None
    finally:
        if pipe:
            for fd in (commands, answers):
                os.close(fd)
    channel = _Pipe(*ours) if pipe else None
    try:
        extension_id = (channel.call("Extensions.loadUnpacked", {"path": str(extension_dir)})["id"] if channel
                        else extension_id_for(extension_dir))
        ws_url = find_ws_url(profile, START_TIMEOUT)
    except (AppBrowserError, ChromeError, OSError, KeyError) as exc:
        if channel is not None:
            channel.close()
        exited_at_once = process.poll() is not None
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.terminate()
            process.wait(timeout=10)
        if exited_at_once:  # another Chrome holds this profile and took over the launch
            raise AppBrowserError(ALREADY_OPEN.format(profile)) from None
        raise AppBrowserError(f"AI Browser could not start: {exc}") from None
    if channel is not None:
        channel.drain()
    if later:
        _open_tabs(ws_url, later)
    return AppBrowser(process, ws_url, extension_id, profile, installed, channel)


def _open_tabs(ws_url: str, urls: list[str]) -> None:
    """Open more start pages over the debugging port (headless Chrome refuses a second one on its command line)."""
    with contextlib.suppress(Exception), connect(ws_url, max_size=None, open_timeout=5) as ws:
        for number, url in enumerate(urls, 1):
            ws.send(json.dumps({"id": number, "method": "Target.createTarget", "params": {"url": url}}))
            ws.recv(timeout=5)
