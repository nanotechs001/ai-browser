"""Files written whole and in binary, the same on every OS.

write_atomic writes a temp file in the same folder (opened with O_BINARY: without it Windows turns every "\n" into
"\r\n", which corrupts icon.png and keeps "rewrite only what changed" from ever matching), then replaces the target
with platforms.replace, which waits out a moment's hold by Defender, Brave or an editor on Windows."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from . import platforms


def write_atomic(path, data: bytes, mode: int = 0o644) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | platforms.O_BINARY, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(temp, mode)
        platforms.replace(temp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp)
        raise
