"""Which browsers are installed, whether each one runs with its remote-debugging switch on, its profiles (name and
colour) and which profile holds a copy of the Brain's watcher: found by reading files only.

Pure, like platforms.py: no module state, no cache, no threads, no writes. Every function takes its paths, or
`system` and `env`, read at call time, so the Mac's tests can ask for any OS. The OS facts (the app folders, the data
folder, the LaunchServices file, the registry) come from platforms.py; this module never spells them.

Every public function returns a safe value for a missing, broken, huge or hostile file, and never raises. The only
network use is a TCP connect to 127.0.0.1 that sends no bytes: no DevTools session is opened, so the browser never
asks "Allow remote debugging?" and shows no automation bar because of it. Account fields (emails, account names) are
never read into a result, and nothing here starts a program."""

from __future__ import annotations

import json
import ntpath
import os
import plistlib
import re
import socket
import sys
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from . import platforms

MAX_FILE = 16 * 1024 * 1024  # bytes: a bigger Local State or Preferences file is not read at all


def _system(system: str | None) -> str:
    return system or sys.platform


def by_id(browser_id: str) -> platforms.BrowserFacts | None:
    """The table's row for an id ("brave", "chrome-beta", …), or None."""
    return next((facts for facts in platforms.KNOWN_BROWSERS if facts.id == browser_id), None)


def data_dir(facts: platforms.BrowserFacts, system: str | None = None, env: Mapping | None = None) -> Path | None:
    """The browser's folder of profiles on `system`, installed or not (None when it keeps none there)."""
    return platforms.browser_data_dir(facts, system, env)


def all_data_dirs(system: str | None = None, env: Mapping | None = None) -> list[Path]:
    """Every known browser's folder of profiles on `system`, installed or not, in the table's order."""
    return [folder for facts in platforms.KNOWN_BROWSERS if (folder := data_dir(facts, system, env)) is not None]


def _path_key(path, system: str) -> str | None:
    """A path as compared here: resolved, and on Windows without regard to case; None for a path that can't be (it
    holds a NUL)."""
    try:
        resolved = os.path.realpath(path)
    except (OSError, ValueError):
        return None
    return ntpath.normcase(resolved) if system == "win32" else resolved


def for_data_dir(folder, system: str | None = None, env: Mapping | None = None) -> platforms.BrowserFacts | None:
    """Which known browser owns this data folder, or None."""
    system = _system(system)
    wanted = _path_key(folder, system)
    if wanted is None:
        return None
    for facts in platforms.KNOWN_BROWSERS:
        own = data_dir(facts, system, env)
        if own is not None and _path_key(own, system) == wanted:
            return facts
    return None


def _read(path) -> bytes | None:
    """A file's bytes, or None. Only a regular file is opened, so a pipe or a device can't hang it; the open lets the
    browser replace the file meanwhile (platforms.open_shared); a file over MAX_FILE is never read."""
    try:
        if not os.path.isfile(path):
            return None
        with platforms.open_shared(path) as handle:
            if os.fstat(handle.fileno()).st_size > MAX_FILE:
                return None
            data = handle.read(MAX_FILE + 1)
    except (OSError, ValueError):
        return None
    return data if len(data) <= MAX_FILE else None  # it grew past the limit while we looked
