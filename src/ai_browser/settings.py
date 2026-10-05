"""The app's own settings: <home>/settings.json, one small JSON object the app reads and writes for the user.

One reader and one writer touch the file: read_settings and write_setting (wave C's places.py uses them too). A
missing, unreadable, broken or half-written file reads as {} and never raises, so the app always starts. A write is
atomic, mode 0600, and keeps every key it doesn't set, so a file written by a newer build survives an older one.
Settings(home) is the typed view on top: the window's browser, the model, Voice, the app's shortcut, reading the
user's tabs, where agents browse and the old extension's note, each value checked."""

from __future__ import annotations

import json
from pathlib import Path

from .app.window import NAMES, offered
from .browsers import plain_folder
from .desktop.shortcut import DEFAULT as DEFAULT_SHORTCUT
from .desktop.shortcut import SHORTCUT_ERROR, SHORTCUTS
from .syncdir import write_atomic

FILE = "settings.json"
MODELS = ("opus", "sonnet", "haiku")
DEFAULTS = {"window_browser": "auto", "model": None, "voice": False, "shortcut": DEFAULT_SHORTCUT,
            "read_tabs": False, "agents_profile": None, "watcher_note": True}


def _path(home) -> Path:
    return Path(home) / FILE


def read_settings(home) -> dict:
    """The file's object, or {} when it is missing, unreadable or not a JSON object."""
    try:
        data = json.loads(_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_setting(home, key: str, value) -> None:
    """Set one key, keeping every other."""
    data = read_settings(home)
    data[key] = value
    write_atomic(_path(home), (json.dumps(data, indent=1, ensure_ascii=False) + "\n").encode("utf-8"), 0o600)


def _either(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} or {names[-1]}"


class Settings:
    """The typed view: get() never raises, and set() checks the value before anything is written."""

    def __init__(self, home, system: str | None = None):
        self.home = Path(home)
        self.path = _path(home)
        self.system = system

    def _check(self, key: str, value) -> None:
        if key == "window_browser":
            choices = offered(self.system)
            if not isinstance(value, str) or value not in choices:
                names = [NAMES.get(choice, "Auto") for choice in choices]
                raise ValueError(f"The window's browser must be {_either(names)}")
        elif key == "model":
            if value is not None and value not in MODELS:
                raise ValueError("The model must be Opus, Sonnet or Haiku")
        elif key == "voice":
            if not isinstance(value, bool):
                raise ValueError("Voice is on or off")
        elif key == "shortcut":
            if value is not None and value not in SHORTCUTS:
                raise ValueError(SHORTCUT_ERROR)
        elif key in ("read_tabs", "watcher_note"):  # Settings → Brain's switch; AI Home's note about the old extension
            if not isinstance(value, bool):
                raise ValueError("That setting is on or off")
        elif key == "agents_profile":  # Settings → Where agents browse: a profile's folder, or the one used last
            if value is not None and not plain_folder(value):
                raise ValueError("Pick one of the profiles listed")
        else:
            raise ValueError(f"There is no setting {key!r}")

    def get(self) -> dict:
        stored, result = read_settings(self.home), dict(DEFAULTS)
        for key in DEFAULTS:
            if key in stored:
                try:
                    self._check(key, stored[key])
                except ValueError:
                    continue  # this key falls back; the others stand
                result[key] = stored[key]
        return result

    def set(self, key: str, value) -> dict:
        self._check(key, value)
        write_setting(self.home, key, value)
        return self.get()
