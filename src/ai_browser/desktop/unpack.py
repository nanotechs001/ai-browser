"""Electron's zip, unpacked into a new folder: every file with its executable bits, and every symbolic link as a link.
A Mac app's frameworks are built of links, and Python's zipfile alone would write each one as a small text file. An
entry that would land outside the folder, or a link that points outside it, stops everything. The zip was checked
against Electron's checksums first, so that never happens with Electron's own."""

from __future__ import annotations

import os
import shutil
import stat
import zipfile
from pathlib import Path

PIECE = 1 << 20
LIMIT = 2_000_000_000  # bytes unpacked at most (Electron 44 unpacks to about 400 MB)


class UnpackError(Exception):
    """The zip can't be unpacked safely; the message says why, in plain words."""


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def unpack(archive: Path, dest: Path) -> None:
    """Every entry of `archive` under `dest`, which must not exist yet (FileExistsError). UnpackError when it can't
    be done safely. What was written stays in `dest`, for the caller to remove."""
    dest = Path(dest)
    dest.mkdir(parents=True)
    root = os.path.realpath(dest)
    try:
        with zipfile.ZipFile(archive) as zipped:
            entries = zipped.infolist()
            if sum(entry.file_size for entry in entries) > LIMIT:
                raise UnpackError("Electron's zip is larger than expected")
            for entry in entries:
                _one(zipped, entry, root)
    except zipfile.BadZipFile:
        raise UnpackError("Electron's zip can't be read") from None


def _one(zipped: zipfile.ZipFile, entry: zipfile.ZipInfo, root: str) -> None:
    place = os.path.join(root, *entry.filename.split("/"))
    if not _inside(os.path.realpath(place), root):  # realpath follows the links unpacked so far
        raise UnpackError(f"Electron's zip has an entry outside its folder: {entry.filename}")
    if entry.is_dir():
        os.makedirs(place, exist_ok=True)
        return
    os.makedirs(os.path.dirname(place), exist_ok=True)
    mode = entry.external_attr >> 16
    if stat.S_ISLNK(mode):
        target = zipped.read(entry).decode("utf-8")
        if os.path.isabs(target) or not _inside(os.path.realpath(os.path.join(os.path.dirname(place), target)), root):
            raise UnpackError(f"Electron's zip has a link outside its folder: {entry.filename}")
        os.symlink(target, place)
        return
    with zipped.open(entry) as source, open(place, "wb") as out:
        shutil.copyfileobj(source, out, PIECE)
    if mode & 0o111:
        os.chmod(place, (mode & 0o777) | 0o200)  # a program stays one (and its owner may replace it)
