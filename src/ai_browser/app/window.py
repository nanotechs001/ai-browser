"""AI Browser's own window: AI Home, Mission Control and Settings, drawn by an installed browser in Chrome's --app
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

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .. import browsers

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
