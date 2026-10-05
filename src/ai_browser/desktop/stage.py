"""AI Browser's part of its own app: the JavaScript in desktop/electron/ and the icon, as they go into the app's
resources/app folder, and a hash of them, so a changed file is noticed (assemble.py adds the rest of what setup
changes to the hash)."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from .. import platforms

ELECTRON = Path(__file__).with_name("electron")
ICON = Path(__file__).parents[1] / "app" / "ui" / "icon.png"
APP_FILES = ("package.json", "main.js", "preload.js", "policy.js", "line.js")


def stage_app(dest: Path) -> None:
    """`dest` holds exactly the app's files and icon.png (whatever was there before goes)."""
    dest = Path(dest)
    if dest.exists():
        platforms.rmtree(dest)
    dest.mkdir(parents=True)
    for name in APP_FILES:
        shutil.copyfile(ELECTRON / name, dest / name)
    shutil.copyfile(ICON, dest / "icon.png")


def part_hash(extra: bytes = b"") -> str:
    """A SHA-256 over every file stage_app copies, and `extra`."""
    digest = hashlib.sha256()
    for name, path in [*((name, ELECTRON / name) for name in APP_FILES), ("icon.png", ICON)]:
        data = path.read_bytes()
        digest.update(f"{name}\0{len(data)}\0".encode("utf-8") + data)
    digest.update(extra)
    return digest.hexdigest()
