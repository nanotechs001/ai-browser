"""AI Browser's own window: Mission Control and Settings, drawn by an installed browser in Chrome's --app
mode (a title bar only: no tabs, no address bar), on a profile of the app's own.

The window has no debugging port: no --remote-debugging-port, no --remote-debugging-pipe, no --enable-automation and
no --load-extension. Nothing drives it, so it never brings "Allow remote debugging?" or the automation bar, and
navigator.webdriver is false there because nothing automates it, not because anything hides it. No agent browses in
it: agents use the user's browser, or the Docker sandbox. The app only starts the browser process on its own profile,
and ends that process when the app ends; it never connects to it.

Which browser draws it is a setting: Auto, Google Chrome, Brave, or Microsoft Edge on Windows. Auto tries Chrome, then
Brave (on Windows: Edge, Chrome, Brave). On macOS it skips the everyday browser when another is installed, so a link
clicked in another app never lands in this window's app."""

from __future__ import annotations

import contextlib
import ntpath
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .. import browsers, platforms

WINDOW_CHOICES = ("auto", "chrome", "brave", "edge")
NAMES = {"chrome": "Google Chrome", "brave": "Brave", "edge": "Microsoft Edge"}


def _system(system: str | None) -> str:
    return system or sys.platform


def offered(system: str | None = None) -> tuple[str, ...]:
    """The choices Settings shows on this system: Edge only on Windows."""
    return ("auto", "edge", "chrome", "brave") if _system(system) == "win32" else ("auto", "chrome", "brave")


def _order(system: str) -> tuple[str, ...]:
    return ("edge", "chrome", "brave") if system == "win32" else ("chrome", "brave")


@dataclass(frozen=True)
class WindowBrowser:
    id: str
    name: str
    binary: str


@dataclass(frozen=True)
class WindowPick:
    browser: WindowBrowser
    note: str  # why a choice that can't be used fell back to Auto, or ""


def _installed(system: str) -> dict[str, str]:
    """The browsers here that can draw the window: id -> program. Reads files only, never connects."""
    found: dict[str, str] = {}
    for row in browsers.installed(system=system):
        if row.window and row.id in NAMES and row.id in offered(system):
            found.setdefault(row.id, str(row.binary))
    if system not in ("darwin", "win32"):  # Linux: detection lists nothing there; today's finders do
        from ..chrome import brave_binary, chrome_binary

        for browser_id, finder in (("chrome", chrome_binary), ("brave", brave_binary)):
            program = finder()
            if program and Path(program).is_file():
                found.setdefault(browser_id, program)
    configured = os.environ.get("AIB_CHROME_BINARY")
    if configured and Path(configured).is_file():  # tests and CI: Chrome's program, whatever detection says
        found["chrome"] = configured
    return found


def _os_default(system: str) -> str | None:
    return browsers.os_default(system=system) if system == "darwin" else None


def pick(setting: str, system: str | None = None, installed: dict | None = None,
         os_default: str | None = None) -> WindowPick | None:
    """The browser that draws the window for `setting`, or None when no browser here can. A choice that can't be used
    falls back to Auto, with a note for the terminal and the Settings page."""
    system = _system(system)
    if installed is None:
        found = _installed(system)
        default = os_default if os_default is not None else _os_default(system)
    else:
        found, default = {key: str(value) for key, value in installed.items()}, os_default
    usable = [choice for choice in _order(system) if choice in found and choice in offered(system)]
    if not usable:
        return None
    auto = usable[0]
    if system == "darwin" and len(usable) > 1:  # not the everyday browser, when there is another
        auto = next(choice for choice in usable if choice != default)
    if setting in usable:
        return WindowPick(WindowBrowser(setting, NAMES[setting], found[setting]), "")
    note = ""
    if setting in NAMES:
        why = "isn't installed" if setting in offered(system) else "draws the window only on Windows"
        note = f"{NAMES[setting]} {why}: the window uses {NAMES[auto]}. Change it in Settings."
    return WindowPick(WindowBrowser(auto, NAMES[auto], found[auto]), note)


def choices(system: str | None = None, installed: dict | None = None, os_default: str | None = None) -> list[dict]:
    """What Settings lists: each offered choice, whether it is installed, and Auto named after its pick."""
    system = _system(system)
    if installed is None:
        found = _installed(system)
        default = os_default if os_default is not None else _os_default(system)
    else:
        found, default = dict(installed), os_default
    auto = pick("auto", system, found, default)
    rows = []
    for choice in offered(system):
        if choice == "auto":
            rows.append({"id": "auto", "name": f"Auto ({auto.browser.name})" if auto else "Auto",
                         "installed": auto is not None})
        else:
            rows.append({"id": choice, "name": NAMES[choice], "installed": choice in found})
    return rows


def window_profile(home, browser_id: str) -> Path:
    """The window's own profile, one per browser: two Chromium brands must never share a profile folder."""
    return Path(home) / "app" / "window" / browser_id


def window_args(binary, profile, url: str) -> list[str]:
    """The window's whole command line. The autoplay flag lets Mission Control speak without a click first; it applies
    only to this browser process, on AI Browser's own profile, where no site is ever loaded."""
    return [str(binary), f"--user-data-dir={profile}", f"--app={url}", "--no-first-run", "--no-default-browser-check",
            "--disable-search-engine-choice-screen", "--window-size=1440,960",
            "--autoplay-policy=no-user-gesture-required"]


QUIT_WAIT = 10  # seconds the window's browser gets to quit before it is killed
NO_BROWSER = ("AI Browser needs Google Chrome, Brave or Microsoft Edge to draw its window: install one, then start "
              "again.")
HANDED_OFF = "AI Browser's window was opened by a browser already running on its profile: quit it yourself ({how})"


class WindowError(RuntimeError):
    """AI Browser's window can't start; the message says why, in plain words."""


def _inside(path, folder, system: str) -> bool:
    """Whether `path` is `folder` or inside it: resolved, and on Windows without regard to case."""
    left, right = os.path.realpath(path), os.path.realpath(folder)
    if system == "win32":
        left, right = ntpath.normcase(left), ntpath.normcase(right)
    return left == right or left.startswith(right.rstrip("/\\") + os.sep)


class AppWindow:
    """This run's window: started on <home>/app/window/<browser>, ended at the app's end. It ends only the process it
    started, and nothing after a hand-off (a browser already running on its profile took the launch)."""

    def __init__(self, home, browser: WindowBrowser, note: str = "", extra_args=(), system: str | None = None):
        self.browser = browser
        self.id, self.name, self.note = browser.id, browser.name, note
        self.profile = window_profile(home, browser.id)
        self.extra_args = tuple(extra_args)  # one test only: ("--headless=new", url); the product never passes any
        self.system = _system(system)
        self.process = None
        self.handed_off = False

    def launch(self, url: str) -> None:
        if any(_inside(self.profile, folder, self.system) for folder in browsers.all_data_dirs(system=self.system)):
            raise WindowError(f"AI Browser's window could not start: {self.profile} is in a browser's own data folder")
        self.profile.mkdir(parents=True, exist_ok=True)
        # Left from a crashed run: the new process hands its command line to that browser and exits, and that browser
        # opens the window. It reads the profile's own lock only, and never connects.
        self.handed_off = browsers.running(self.profile, system=self.system) is True
        try:
            self.process = subprocess.Popen([*window_args(self.browser.binary, self.profile, url), *self.extra_args],
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            raise WindowError(f"AI Browser's window could not start: {exc.strerror or exc}") from None

    def close(self) -> str:
        """Quit the browser this run started: asked first (SIGTERM; on Windows taskkill without /F, as a click on its
        × does, so Edge offers no "Restore pages?" next time), killed after QUIT_WAIT. After a hand-off it ends nothing
        and returns what the user should do."""
        if self.handed_off:
            return HANDED_OFF.format(how=platforms.shortcut("⌘Q", "close its windows", self.system))
        process = self.process
        if process is None or process.poll() is not None:
            return ""
        if self.system == "win32":
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                subprocess.run(["taskkill", "/PID", str(process.pid)], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=QUIT_WAIT)
        else:
            process.terminate()
        try:
            process.wait(timeout=QUIT_WAIT)
        except subprocess.TimeoutExpired:
            process.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=QUIT_WAIT)
        return ""


def default_launcher(home) -> Callable[[str], AppWindow]:
    """run_app's launcher: the window_browser setting in, this run's AppWindow out (or WindowError)."""
    def launcher(setting: str) -> AppWindow:
        found = pick(setting)
        if found is None:
            raise WindowError(NO_BROWSER)
        return AppWindow(home, found.browser, found.note)
    return launcher
