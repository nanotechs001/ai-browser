"""The watcher's folder: the small extension the user loads once in Brave, their everyday browser.

Brave keeps an unpacked extension loaded from its folder, and computes its ID from the folder's path, so the folder
stays at <home>/app/watcher and is updated in place: a file is rewritten only when it changed, never deleted and
copied again under Brave's feet. config.json (the server's address and token, mode 0600) is rewritten at every start;
the watcher reads it again before each connection. build.js names this version of the files: when the app reports
another one, the watcher reloads itself from disk."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"
WATCHER_SOURCE = APP / "watcher"
SHARED_SOURCE = APP / "extension"
WATCHER_SHARED = ("link.js", "brainui.js", "brainui.css", "permission.js")  # shared with AI Browser's extension


def _sources() -> dict[str, bytes]:
    files = {}
    for path in sorted(WATCHER_SOURCE.rglob("*")):
        if path.is_file() and not path.name.startswith(".") and "__pycache__" not in path.parts:
            files[path.relative_to(WATCHER_SOURCE).as_posix()] = path.read_bytes()
    for name in WATCHER_SHARED:
        files[name] = (SHARED_SOURCE / name).read_bytes()
    return files


def _write(path: Path, data: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode), "wb") as handle:
        handle.write(data)
    os.chmod(temp, mode)
    os.replace(temp, path)


def prepare_watcher(home: Path, server_url: str, token: str) -> tuple[Path, str]:
    """The watcher folder, current, with this run's address and token; returns (folder, build)."""
    folder = Path(home) / "app" / "watcher"
    files = _sources()
    digest = hashlib.sha256()
    for name, data in files.items():
        digest.update(name.encode() + b"\0" + data + b"\0")
    build = digest.hexdigest()[:12]
    files["build.js"] = f'export const BUILD = "{build}";\n'.encode()
    for name, data in files.items():
        path = folder / name
        try:
            if path.read_bytes() == data:
                continue
        except OSError:
            pass
        _write(path, data)
    keep = set(files) | {"config.json"}
    for path in list(folder.rglob("*")):
        if path.is_file() and path.relative_to(folder).as_posix() not in keep:
            path.unlink()
    _write(folder / "config.json", json.dumps({"server": server_url, "token": token}).encode(), 0o600)
    return folder, build
