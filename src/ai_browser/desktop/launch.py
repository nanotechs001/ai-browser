"""AI Browser's own app for one run of `ai-browser app` (app/run.py): started, linked by one private line, and ended.

The line carries JSON, one object per line, both ways (desktop/electron/line.js is the other end):
- the engine sends start (the start address with its one-time code, and the shortcut from Settings), shortcut (try
  this one), notify, show and quit;
- the app sends hello (its pid), shortcut (whether it holds one, and its first press), clicked (a notification) and
  quit (the user's Quit).

How it starts:
- Windows: its own program, AI Browser.exe, with the line on its stdin and stdout.
- macOS: through LaunchServices (`open -n -W -a`), so macOS treats it as an app of its own: its Dock icon, and the
  microphone and Brave permissions it asks for are its own (a program started from a terminal would ask as the
  terminal). LaunchServices gives it no pipe. So the line is a socket in a new folder only this user can open. Its
  path is the app's one argument, only the first connection is taken, and the socket goes at once.

The start code never goes on a command line, and nothing here passes a debugging switch."""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import os
import signal
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from ..app.window import WindowError
from . import layout
from .assemble import SetupError, refresh, stale

START_WAIT = 20.0  # seconds for the app to start and say hello
ANSWER_WAIT = 5.0  # seconds for its answer about a shortcut
QUIT_WAIT = 10.0  # seconds it gets to quit before it is ended
LINE_LIMIT = 64 * 1024  # bytes in one line
UPDATED = "AI Browser's app was updated for this version: macOS may ask for the microphone once more."


class DesktopError(WindowError):
    """AI Browser's own app can't start; app/run.py opens a browser window instead (plain words, no full stop)."""


def mac_command(app: Path, line: Path, opener: Sequence[str] = ("open",)) -> list[str]:
    return [*opener, "-n", "-W", "-a", str(app), "--args", f"--aib-line={line}"]


def windows_command(program: Path) -> list[str]:
    return [str(program)]


def _parse(raw: bytes) -> dict | None:
    try:
        message = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return message if isinstance(message, dict) and isinstance(message.get("type"), str) else None


class DesktopWindow:
    """This run's own app: AppWindow's surface (id, name, note, launch(url), close() -> str), plus the line."""

    id, name = "desktop", "AI Browser"

    def __init__(self, home, shortcut: str | None = None, system: str | None = None,
                 program: Sequence[str] | None = None, opener: Sequence[str] = ("open",)):
        self.home, self.system = Path(home), system or sys.platform
        self.app = layout.app_path(self.home, self.system)
        self.program = list(program) if program else windows_command(layout.executable(self.app, self.system))
        self.opener = tuple(opener)
        self.start_shortcut = shortcut
        self.note = ""
        self.shortcut: dict = {"value": shortcut, "ok": None, "why": "", "pressed": False}
        self.on_message: Callable[[dict], None] | None = None
        self.ended = asyncio.Event()
        self.quit_by_user = False
        self.pid: int | None = None
        self._process = None
        self._writer = None
        self._tasks: list[asyncio.Task] = []
        self._hello: asyncio.Future | None = None
        self._waiters: dict[str, asyncio.Future] = {}
        self._requests = itertools.count(1)

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def launch(self, url: str | Callable[[], str]) -> None:
        """Start the app on `url` (the /open address with its one-time code, or a function that makes it), and wait for
        its hello. A stale app is built again first. A function is called only once the app is up, right before the
        start: its one-time code (good for a minute) never waits out a rebuild. DesktopError when it can't start:
        nothing is left running then."""
        if stale(self.home, self.system):
            try:
                await asyncio.to_thread(refresh, self.home, self.system)
            except SetupError as exc:
                raise DesktopError(f"AI Browser's app couldn't be updated: {exc}") from None
            self.note = UPDATED if self.system == "darwin" else ""
        self._hello = asyncio.get_running_loop().create_future()
        try:
            await (self._start_mac() if self.system == "darwin" else self._start_direct())
            self.send({"type": "start", "open": url() if callable(url) else url, "shortcut": self.start_shortcut})
            hello = await asyncio.wait_for(self._hello, START_WAIT)
        except TimeoutError:
            await self._end_now()
            raise DesktopError("AI Browser's app didn't answer as it started") from None
        except DesktopError:
            await self._end_now()
            raise
        except OSError as exc:  # the line couldn't be made (a temporary folder too deep for a socket, a full disk)
            await self._end_now()
            raise DesktopError(f"AI Browser's app could not start: {exc.strerror or exc}") from None
        pid = hello.get("pid")
        self.pid = pid if isinstance(pid, int) and not isinstance(pid, bool) and pid > 1 else None

    async def _start_direct(self) -> None:
        try:
            self._process = await asyncio.create_subprocess_exec(
                *self.program, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, limit=LINE_LIMIT)
        except OSError as exc:
            raise DesktopError(f"AI Browser's app could not start: {exc.strerror or exc}") from None
        self._listen(self._process.stdout, self._process.stdin)

    async def _start_mac(self) -> None:
        if not self.app.is_dir():
            raise DesktopError(f"AI Browser's app isn't at {self.app}")
        folder = Path(tempfile.mkdtemp(prefix="aib-"))  # mode 0700: only this user can open what's in it
        line = folder / "line"
        joined = asyncio.get_running_loop().create_future()

        def accept(reader, writer) -> None:
            if joined.done():
                writer.close()  # the first connection only: the app's
            else:
                joined.set_result((reader, writer))

        try:
            server = await asyncio.start_unix_server(accept, path=str(line), limit=LINE_LIMIT)
        except OSError:
            with contextlib.suppress(OSError):
                folder.rmdir()  # nothing is left behind
            raise
        try:
            os.chmod(line, 0o600)
            try:
                self._process = await asyncio.create_subprocess_exec(
                    *mac_command(self.app, line, self.opener), stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            except OSError as exc:
                raise DesktopError(f"macOS couldn't open AI Browser's app: {exc.strerror or exc}") from None
            exited = asyncio.ensure_future(self._process.wait())
            try:
                await asyncio.wait({joined, exited}, timeout=START_WAIT, return_when=asyncio.FIRST_COMPLETED)
            finally:
                exited.cancel()
            if not joined.done():
                if self._process.returncode is not None:
                    raise DesktopError(f"macOS couldn't open AI Browser's app (open ended with "
                                       f"{self._process.returncode})")
                raise DesktopError("AI Browser's app didn't answer as it started")
        finally:
            server.close()
            with contextlib.suppress(OSError):
                line.unlink()
            with contextlib.suppress(OSError):
                folder.rmdir()
        reader, writer = joined.result()
        self._listen(reader, writer)

    def _listen(self, reader, writer) -> None:
        self._writer = writer
        self._tasks += [asyncio.create_task(self._read(reader)), asyncio.create_task(self._exited())]

    async def _read(self, reader) -> None:
        try:
            while True:
                try:
                    raw = await reader.readline()
                except ValueError:  # a line longer than LINE_LIMIT: dropped
                    continue
                except (ConnectionError, OSError):
                    break
                if not raw:
                    break
                message = _parse(raw)
                if message is not None:
                    self._dispatch(message)
        finally:
            self._gone()

    async def _exited(self) -> None:
        with contextlib.suppress(Exception):
            await self._process.wait()
        self._gone()

    def _dispatch(self, message: dict) -> None:
        kind = message["type"]
        if kind == "hello":
            if self._hello is not None and not self._hello.done():
                self._hello.set_result(message)
        elif kind == "quit":
            self.quit_by_user = True
            self._gone()
        elif kind == "shortcut":
            status = {"value": message.get("value") if isinstance(message.get("value"), str) else None,
                      "ok": message.get("ok") is True, "why": str(message.get("why") or "")[:40],
                      "pressed": message.get("pressed") is True}
            request = message.get("request") if isinstance(message.get("request"), str) else None
            if status["ok"] or request is None:
                self.shortcut = status  # what the app holds now: a refused try leaves the one before held
            waiter = self._waiters.pop(request, None) if request is not None else None
            if waiter is not None:
                if not waiter.done():
                    waiter.set_result(status)
            elif self.on_message is not None:
                self.on_message({"type": "shortcut", **status})
        elif kind == "clicked" and isinstance(message.get("id"), str) and self.on_message is not None:
            self.on_message({"type": "clicked", "id": message["id"][:20]})

    def _gone(self) -> None:
        """The app has quit, or its line or its process ended: everything waiting for it hears so."""
        if self.ended.is_set():
            return
        self.ended.set()
        if self._hello is not None and not self._hello.done():
            self._hello.set_exception(DesktopError("AI Browser's app closed as it started"))
            self._hello.exception()  # read once here: a hello nobody waits for any more leaves no warning
        for waiter in self._waiters.values():
            if not waiter.done():
                waiter.set_result({"value": None, "ok": False, "why": "gone", "pressed": False})
        self._waiters.clear()

    def send(self, message: dict) -> bool:
        """A message to the app; False when it can't get one (not started, or gone)."""
        if self._writer is None or self.ended.is_set():
            return False
        try:
            self._writer.write((json.dumps(message) + "\n").encode("utf-8"))
        except (OSError, RuntimeError):
            return False
        return True

    async def try_shortcut(self, value: str | None) -> dict:
        """Ask the app to hold `value` instead (None: no shortcut). Its answer: {value, ok, why, pressed}. When it can't
        take it, the one before stays held."""
        request = f"s{next(self._requests)}"
        waiter = asyncio.get_running_loop().create_future()
        self._waiters[request] = waiter
        if not self.send({"type": "shortcut", "value": value, "request": request}):
            self._waiters.pop(request, None)
            return {"value": value, "ok": False, "why": "gone", "pressed": False}
        try:
            return await asyncio.wait_for(waiter, ANSWER_WAIT)
        except TimeoutError:
            self._waiters.pop(request, None)
            return {"value": value, "ok": False, "why": "no answer", "pressed": False}

    def _kill(self) -> None:
        if self.system == "darwin" and self.pid is not None:
            with contextlib.suppress(OSError):
                os.kill(self.pid, signal.SIGKILL)  # the app itself: `open` only waits for it
        with contextlib.suppress(ProcessLookupError, OSError):
            self._process.kill()

    async def _end_now(self) -> None:
        """A start that failed: nothing may stay running."""
        if self._writer is not None:
            with contextlib.suppress(Exception):
                self._writer.close()  # the line ends: the app quits on that
        if self.running:
            self._kill()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._process.wait(), QUIT_WAIT)
        for task in self._tasks:
            task.cancel()
        self._gone()

    async def close(self) -> str:
        """Quit the app (the engine is stopping): asked over the line, then the line ends, and after QUIT_WAIT it is
        ended. "" (AppWindow's surface: there is never a note)."""
        if self._process is None:
            self._gone()
            return ""
        if self.running:
            self.send({"type": "quit"})
            if self._writer is not None:
                with contextlib.suppress(Exception):
                    self._writer.close()  # the line's end: the app quits on that too
            try:
                await asyncio.wait_for(self._process.wait(), QUIT_WAIT)
            except TimeoutError:
                self._kill()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._process.wait(), QUIT_WAIT)
        for task in self._tasks:
            task.cancel()
        self._gone()
        return ""


def default_desktop(home, shortcut: str | None = None) -> DesktopWindow | None:
    """This run's own app, if it is built here for this computer. None: a browser window draws AI Browser
    (app/window.py)."""
    if layout.installed(home) is None:
        return None
    return DesktopWindow(home, shortcut)
