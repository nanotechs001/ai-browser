"""Electron's zip, fetched only after the user's yes (setup.py asks), and checked twice. The release's own
SHASUMS256.txt must list the pinned SHA-256 for it, and the zip must have the pinned size and that SHA-256. It is
written as <name>.part beside where it goes, and keeps its name only once checked. A mismatch, an error, a connection
that drops, or Ctrl-C keeps nothing."""

from __future__ import annotations

import contextlib
import hashlib
import http.client
import re
import shutil
import ssl
import urllib.error
from collections.abc import Callable
from pathlib import Path

from .. import platforms
from ..hearing.model import urlopen_fetch  # the same checked connection as the voice model's (truststore)
from .release import SHASUMS, Asset

PIECE = 1 << 20  # bytes read at a time
SUMS_LIMIT = 64_000  # bytes of SHASUMS256.txt read at most (6,740 for 44.5.1)
NEEDED = 1_000_000_000  # free disk space for the zip, Electron unpacked, and the app built from it
MISMATCH = "The download didn't match Electron's checksum: nothing was kept"
NOT_LISTED = "Electron's SHASUMS256.txt doesn't list the expected checksum: nothing was downloaded"
CUT = "The download stopped before the end: nothing was kept"
_LINE = re.compile(r"^([0-9a-f]{64}) [ *](.+)$")


class SetupError(Exception):
    """A setup step that failed, in plain words for the terminal and for Settings."""


def listed(text: str, name: str) -> str | None:
    """The SHA-256 SHASUMS256.txt lists for `name` (a "<hex> *<name>" or "<hex>  <name>" line), or None."""
    for line in text.splitlines():
        found = _LINE.match(line.strip())
        if found is not None and found.group(2) == name:
            return found.group(1)
    return None


def _plain(exc: BaseException) -> str | None:
    """A network or disk failure in plain words; None for anything else."""
    if isinstance(exc, urllib.error.HTTPError):
        return f"The download failed: GitHub answered {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        if isinstance(exc.reason, ssl.SSLError):
            return "The download failed: the connection to GitHub couldn't be checked"
        if isinstance(exc.reason, TimeoutError):
            return "The download stopped: the connection timed out"
        return "No internet connection"
    if isinstance(exc, TimeoutError):
        return "The download stopped: the connection timed out"
    if isinstance(exc, (ConnectionError, http.client.IncompleteRead)):
        return CUT
    if isinstance(exc, OSError):
        return f"The download failed: {exc.strerror or type(exc).__name__}"
    return None


def _small(fetch: Callable, url: str, limit: int) -> bytes:
    """A small file (SHASUMS256.txt), at most `limit` bytes."""
    try:
        with fetch(url) as answer:
            data = answer.read(limit + 1)
    except Exception as exc:
        said = _plain(exc)
        if said is None:
            raise
        raise SetupError(said) from None
    if len(data) > limit:
        raise SetupError(NOT_LISTED)
    return data


def _zip(asset: Asset, part: Path, fetch: Callable, progress: Callable[[int], None]) -> None:
    digest, size = hashlib.sha256(), 0
    try:
        with fetch(asset.url) as answer, open(part, "wb") as out:
            while piece := answer.read(PIECE):
                size += len(piece)
                if size > asset.size:
                    raise SetupError(MISMATCH)
                digest.update(piece)
                out.write(piece)
                progress(size)
    except SetupError:
        raise
    except Exception as exc:
        said = _plain(exc)
        if said is None:
            raise
        raise SetupError(said) from None
    if size < asset.size:
        raise SetupError(CUT)
    if digest.hexdigest() != asset.sha256:
        raise SetupError(MISMATCH)


def download(asset: Asset, folder: Path, fetch: Callable = urlopen_fetch,
             progress: Callable[[int], None] = lambda done: None) -> Path:
    """The checked zip at <folder>/<asset.name>. SetupError when anything fails: nothing is kept then, nor on Ctrl-C
    (KeyboardInterrupt goes on up). `progress` gets the bytes so far."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(folder).free < NEEDED:
        raise SetupError(f"Not enough free disk space: {NEEDED // 1_000_000_000} GB is needed")
    if listed(_small(fetch, SHASUMS, SUMS_LIMIT).decode("utf-8", "replace"), asset.name) != asset.sha256:
        raise SetupError(NOT_LISTED)
    final, part = folder / asset.name, folder / f"{asset.name}.part"
    for leftover in (final, part):
        platforms.unlink(leftover, missing_ok=True)
    try:
        _zip(asset, part, fetch, progress)
        platforms.replace(part, final)
    except BaseException:
        with contextlib.suppress(OSError):
            platforms.unlink(part, missing_ok=True)
        raise
    return final
