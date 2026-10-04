"""A throwaway headless Chrome with an unpacked extension loaded over the DevTools pipe, for the watcher's tests only.
Branded Chrome ignores --load-extension, so the tests install the watcher for one run with Extensions.loadUnpacked;
Chrome quits when the pipe closes. The product never does this: the user loads Brave's watcher once, by hand. POSIX
only (file descriptors 3 and 4): tests/conftest.py skips the `watcher` fixture on Windows."""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from ai_browser.chrome import ChromeError, chrome_binary, find_ws_url

START_TIMEOUT = 20  # seconds for Chrome to start and open its debugging port


class PipeError(RuntimeError):
    """The throwaway Chrome could not start, or didn't answer over its pipe."""


class _Pipe:
    """Chrome DevTools over --remote-debugging-pipe: NUL-separated JSON."""

    def __init__(self, to_chrome: int, from_chrome: int):
        self._out, self._in = to_chrome, from_chrome
        self._buffer = b""
        self._id = 0

    def call(self, method: str, params: dict, timeout: float = START_TIMEOUT) -> dict:
        import select  # POSIX only, like the pipe itself

        self._id += 1
        os.write(self._out, json.dumps({"id": self._id, "method": method, "params": params}).encode() + b"\0")
        deadline = time.monotonic() + timeout
        while True:
            while b"\0" not in self._buffer:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PipeError(f"Chrome did not answer {method} within {timeout:g} s")
                if not select.select([self._in], [], [], remaining)[0]:
                    continue
                chunk = os.read(self._in, 65536)
                if not chunk:
                    raise PipeError("Chrome closed its DevTools pipe")
                self._buffer += chunk
            raw, self._buffer = self._buffer.split(b"\0", 1)
            message = json.loads(raw)
            if message.get("id") != self._id:
                continue  # an event
            if "error" in message:
                raise PipeError(f"{method}: {message['error'].get('message', message['error'])}")
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
    """Chrome, started with posix_spawn: Popen can't move descriptors onto 3 and 4 without preexec_fn."""

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
class PipeChrome:
    process: _Process
    ws_url: str
    extension_id: str
    profile: Path
    _pipe: _Pipe = field(repr=False)

    def close(self) -> None:
        """Chrome quits when its pipe closes; it is stopped if it hasn't after 10 s."""
        self._pipe.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)


def _spawn_posix(binary: str, args: list[str], pipe: bool = True) -> tuple[_Process, _Pipe | None]:
    """posix_spawn. With the pipe, Chrome reads commands on fd 3 and writes answers on fd 4."""
    import fcntl  # POSIX only

    actions = [(os.POSIX_SPAWN_OPEN, 1, os.devnull, os.O_WRONLY, 0), (os.POSIX_SPAWN_OPEN, 2, os.devnull, os.O_WRONLY, 0)]
    ours: list[int] = []  # our ends of the pipe
    theirs: list[int] = []  # Chrome's ends, closed here once it has started
    if pipe:
        to_read, to_write = os.pipe()  # Chrome reads commands on fd 3...
        from_read, from_write = os.pipe()  # ...and writes answers on fd 4
        # Chrome's ends go above 9 first, so moving one onto 3 or 4 in the child can never overwrite the other.
        theirs = [fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 10) for fd in (to_read, from_write)]
        for fd in (to_read, from_write):
            os.close(fd)
        actions = [(os.POSIX_SPAWN_DUP2, theirs[0], 3), (os.POSIX_SPAWN_DUP2, theirs[1], 4), *actions]
        ours = [to_write, from_read]
    try:
        process = _Process(os.posix_spawn(binary, args, os.environ, file_actions=actions,
                                          setsigdef=(signal.SIGPIPE, signal.SIGXFSZ)))
    except OSError as exc:
        for fd in ours:
            os.close(fd)
        raise PipeError(f"the throwaway Chrome could not start: {exc}") from None
    finally:
        for fd in theirs:
            os.close(fd)
    return process, (_Pipe(*ours) if pipe else None)


def launch_with_extension(profile, folder) -> PipeChrome:
    """A headless throwaway Chrome on `profile` with the unpacked extension in `folder` loaded for this run."""
    binary = chrome_binary()
    if binary is None:
        raise PipeError("Google Chrome is not installed")
    profile = Path(profile)
    profile.mkdir(parents=True, exist_ok=True)
    args = [binary, f"--user-data-dir={profile}", "--remote-debugging-port=0", "--no-first-run",
            "--no-default-browser-check", "--disable-search-engine-choice-screen", "--window-size=1440,960",
            "--remote-debugging-pipe", "--enable-unsafe-extension-debugging", "--headless=new"]
    process, pipe = _spawn_posix(binary, args, True)
    try:
        extension_id = pipe.call("Extensions.loadUnpacked", {"path": str(folder)})["id"]
        ws_url = find_ws_url(profile, START_TIMEOUT)
    except (PipeError, ChromeError, OSError, KeyError) as exc:
        pipe.close()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.terminate()
            process.wait(timeout=10)
        raise PipeError(f"the throwaway Chrome could not start: {exc}") from None
    pipe.drain()
    return PipeChrome(process, ws_url, extension_id, profile, pipe)
