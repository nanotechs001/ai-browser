"""The global shortcuts AI Browser's own app offers (Settings → AI Browser app), and how each is written: ⌥Space on a
Mac, Alt+Space elsewhere. policy.js lists the same values, in the same order (a test checks). None of them is a macOS
default: ⌃Space and ⌃⌥Space switch input sources there."""

from __future__ import annotations

import sys

SHORTCUTS = ("Alt+Space", "Alt+Shift+Space", "Control+Shift+Space")  # Electron accelerators
DEFAULT = "Alt+Space"
SHORTCUT_ERROR = "The shortcut must be one of the offered ones, or Off"
_MAC = {"Control": "⌃", "Alt": "⌥", "Shift": "⇧"}
_OTHER = {"Control": "Ctrl"}


def label(value: str | None, system: str | None = None) -> str:
    """How Settings writes a shortcut: "⌥⇧Space" on a Mac, "Alt+Shift+Space" elsewhere, "Off" for none."""
    if value is None:
        return "Off"
    keys = value.split("+")
    if (system or sys.platform) == "darwin":
        return "".join(_MAC.get(key, key) for key in keys)
    return "+".join(_OTHER.get(key, key) for key in keys)


def state(value: str | None, said: dict, running: bool) -> str:
    """What Settings says about the saved shortcut, from what the app said (`said`):
    - "off": no shortcut;
    - "taken": another app holds it;
    - "ready": the app holds it, and it hasn't been pressed yet;
    - "works": it was pressed;
    - "unknown": the app isn't running, or hasn't said yet."""
    if value is None:
        return "off"
    if not running or said.get("value") != value or said.get("ok") is None:
        return "unknown"
    if said.get("ok") is False:
        return "taken"
    return "works" if said.get("pressed") else "ready"
