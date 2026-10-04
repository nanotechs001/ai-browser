"""The ID Chrome and Brave give an unpacked extension, and the folder path it is computed from. Brave's watcher is
loaded once from a fixed folder (<home>/app/watcher), so the app knows its ID, and allows its origin, before it ever
connects."""

from __future__ import annotations

import hashlib
import ntpath
import os
import sys
from pathlib import Path


def extension_path(folder: Path | str, system: str | None = None) -> str:
    """The folder's path as Chrome sees it: the string that is hashed into the ID, and the one the user sees, pastes
    and gets revealed. Windows: the absolute path as written (Chrome resolves neither junctions nor OneDrive's
    redirection), with the drive letter upper-cased as Chromium's MaybeNormalizePath does. Elsewhere: the real
    path."""
    if (system or sys.platform) == "win32":
        path = ntpath.abspath(str(folder))
        return path[0].upper() + path[1:] if path[1:2] == ":" else path
    return os.path.realpath(folder)


def extension_id_for(folder: Path | str, system: str | None = None) -> str:
    """The ID Chrome gives an unpacked extension: SHA-256 of its folder's path, 0-f mapped to a-p. Windows hashes the
    path as UTF-16LE (Chromium's id_util.cc, GenerateIdForPath); extension_path already upper-cased its drive."""
    path = extension_path(folder, system)
    data = path.encode("utf-16-le" if (system or sys.platform) == "win32" else "utf-8")
    digest = hashlib.sha256(data).hexdigest()[:32]
    return "".join(chr(ord("a") + int(char, 16)) for char in digest)
