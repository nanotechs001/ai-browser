"""Files the user attaches to a new task (the new look, Decision 9, and its Safety): at most 10, 20 MB each. A page
sends each one in pieces over its socket (the pages' CSP allows no fetch), so they are staged first, in
<home>/app/uploads (the folder 0700, each file 0600, under a random name), and moved when the task starts: into an
`attachments` folder in the task's folder (the one the user chose, or the agent's own scratch folder), never
overwriting a file and never outside that folder. Names are cleaned. Images reach the agent as pictures through
Claude Code's own Read, which runs without a card inside the task's folder (agent powers, Decision 3)."""

from __future__ import annotations

import base64
import binascii
import contextlib
import os
import re
import secrets
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .. import platforms

MAX_FILES = 10
MAX_BYTES = 20_000_000  # 20 MB, as the pages count megabytes (1 MB is 1,000,000 bytes)
CHUNK_CHARS = 1_048_576  # base64 characters in one piece: 768 KiB of the file
FOLDER = "attachments"
NAME_LIMIT = 120
IMAGES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})
UPLOAD_ID = re.compile(r"^[A-Za-z0-9-]{1,40}$")
_UNSAFE = re.compile(r'[\x00-\x1f\x7f-\x9f<>:"/\\|?*​-‏‪-‮⁦-⁩﻿]')
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³]|conin\$|conout\$)$", re.IGNORECASE)
TOO_MANY = f"At most {MAX_FILES} files at once"
TOO_BIG = "{name} is over 20 MB"
NOT_A_FILE = "That isn't a file the app can take"
NOT_OPEN = "That file isn't being sent any more: attach it again"
OUT_OF_ORDER = "{name} arrived out of order: attach it again"
DAMAGED = "A piece of {name} was damaged: attach it again"
TOO_LONG = "{name} is longer than it said it was: attach it again"
NOT_READY = "Wait for the attached files to finish"
OUTSIDE = "The attachments folder in that folder leads somewhere else: rename or remove it, then try again"
FULL = "There are too many files named {name} in attachments already"


def clean_name(name) -> str:
    """A file's name as it is saved: its last part only (so "../x" is "x"), control characters, direction marks and
    <>:"/\\|?* turned into "_", whitespace squeezed, no dot or space at either end, at most NAME_LIMIT characters
    with its extension kept, and last of all Windows' reserved device names made plain: Windows reads the part before
    the FIRST dot (so "con.tar.gz" and "NUL.txt.bak" count, and "con .txt" too). Never empty, never "." or ".."."""
    text = unicodedata.normalize("NFC", name) if isinstance(name, str) else ""
    text = re.split(r"[\\/]", text)[-1]
    text = " ".join(_UNSAFE.sub("_", text).split()).strip(" .")
    stem, dot, suffix = text.rpartition(".")
    if not dot:
        stem, suffix = text, ""
    if not stem.strip(" ."):
        stem = "file"
    suffix = suffix[:16]
    stem = stem[:NAME_LIMIT - len(suffix) - 1].rstrip(" .") or "file"
    cleaned = f"{stem}.{suffix}" if suffix else stem
    head, dot, rest = cleaned.partition(".")
    if _RESERVED.fullmatch(head.rstrip(" .")):
        head = "file"
    return head + dot + rest


def _numbered(name: str, number: int) -> str:
    """"notes.txt", then "notes (2).txt", "notes (3).txt"…"""
    if number == 1:
        return name
    stem, dot, suffix = name.rpartition(".")
    return f"{stem} ({number}).{suffix}" if dot and stem else f"{name} ({number})"


def note(names) -> str:
    """The words added to the task: where each attached file is, and which are pictures."""
    if not names:
        return ""
    lines = [f"- {FOLDER}/{name}" + (" (a picture: look at it with Read)" if Path(name).suffix.lower() in IMAGES
                                     else "") for name in names]
    return ("\n\nThe user attached these files. They are in the attachments folder of your working folder:\n"
            + "\n".join(lines))


def place(work, files) -> list[str]:
    """Move staged files into <work>/attachments, each under its cleaned name or "name (2).ext": opened with O_EXCL
    (and O_NOFOLLOW where there is one), so nothing is overwritten, even in a race, and nothing is written through a
    link. An attachments folder that is a link, or leads outside `work`, is refused (ValueError). Returns the names
    used, in order."""
    if not files:
        return []
    root = Path(os.path.realpath(work))
    folder = root / FOLDER
    if folder.is_symlink():
        raise ValueError(OUTSIDE)
    folder.mkdir(parents=True, exist_ok=True)
    if Path(os.path.realpath(folder)) != folder:
        raise ValueError(OUTSIDE)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | platforms.O_BINARY
    saved = []
    for staged, name in files:
        for number in range(1, 1000):
            used = _numbered(name, number)
            try:
                fd = os.open(folder / used, flags, 0o600)
                break
            except FileExistsError:
                continue
        else:
            raise ValueError(FULL.format(name=name))
        try:
            with os.fdopen(fd, "wb") as out, open(staged, "rb") as source:
                shutil.copyfileobj(source, out, 1 << 20)
        except OSError:
            with contextlib.suppress(OSError):
                os.unlink(folder / used)
            raise
        with contextlib.suppress(OSError):
            os.unlink(staged)
        saved.append(used)
    return saved


@dataclass
class Upload:
    name: str
    size: int
    path: Path
    received: int = 0
    seq: int = 0


class Uploads:
    """Files on their way from a page: each socket's own (its `key`), staged in `folder` until a task takes them, and
    dropped when the page says so or its socket closes."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self._open: dict[object, dict[str, Upload]] = {}

    def clear(self) -> None:
        """Every staged file (the app starts: anything left was a page's that has gone)."""
        self._open.clear()
        if self.folder.is_dir():
            for path in self.folder.glob("*.part"):
                with contextlib.suppress(OSError):
                    path.unlink()

    def start(self, key, upload, name, size) -> tuple[str, str]:
        """(the cleaned name, "") once a file may come, else ("", why not)."""
        if not isinstance(upload, str) or not UPLOAD_ID.match(upload) \
                or isinstance(size, bool) or not isinstance(size, int) or size < 0:
            return "", NOT_A_FILE
        clean = clean_name(name)
        if size > MAX_BYTES:
            return "", TOO_BIG.format(name=clean)
        mine = self._open.setdefault(key, {})
        self.drop(key, upload)  # the same id again: the page starts that file over
        if len(mine) >= MAX_FILES:
            return "", TOO_MANY
        self.folder.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(self.folder, 0o700)
        path = self.folder / f"{secrets.token_hex(12)}.part"
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | platforms.O_BINARY, 0o600))
        mine[upload] = Upload(clean, size, path)
        return clean, ""

    def add(self, key, upload, seq, data) -> tuple[bool, str]:
        """One piece: (whether the file is whole now, ""), or (False, why not), and the file is dropped."""
        current = self._open.get(key, {}).get(upload) if isinstance(upload, str) else None
        if current is None:
            return False, NOT_OPEN
        problem = ""
        if isinstance(seq, bool) or not isinstance(seq, int) or seq != current.seq:
            problem = OUT_OF_ORDER.format(name=current.name)
        elif not isinstance(data, str) or len(data) > CHUNK_CHARS:
            problem = DAMAGED.format(name=current.name)
        else:
            try:
                piece = base64.b64decode(data, validate=True)
            except (binascii.Error, ValueError):
                piece = None
            if piece is None:
                problem = DAMAGED.format(name=current.name)
            elif current.received + len(piece) > current.size:
                problem = TOO_LONG.format(name=current.name)
            else:
                with open(current.path, "ab") as out:
                    out.write(piece)
                current.received += len(piece)
                current.seq += 1
        if problem:
            self.drop(key, upload)
            return False, problem
        return current.received == current.size, ""

    def whole(self, key, upload) -> bool:
        current = self._open.get(key, {}).get(upload)
        return current is not None and current.received == current.size

    def drop(self, key, upload) -> None:
        current = self._open.get(key, {}).pop(upload, None)
        if current is not None:
            with contextlib.suppress(OSError):
                current.path.unlink()

    def drop_all(self, key) -> None:
        for upload in list(self._open.get(key, {})):
            self.drop(key, upload)
        self._open.pop(key, None)

    def take(self, key, uploads) -> list[tuple[Path, str]]:
        """The staged files a new task names, in order: ValueError unless each is whole. They stay staged until
        done(), so a refused start can be tried again."""
        ids = [one for one in uploads if isinstance(one, str)] if isinstance(uploads, list) else []
        if len(ids) > MAX_FILES:
            raise ValueError(TOO_MANY)
        mine = self._open.get(key, {})
        out = []
        for upload in dict.fromkeys(ids):
            current = mine.get(upload)
            if current is None or not current.path.is_file():
                raise ValueError(NOT_OPEN)
            if current.received != current.size:
                raise ValueError(NOT_READY)
            out.append((current.path, current.name))
        return out

    def done(self, key, uploads) -> None:
        """A task took these files (they were moved): they are no longer the page's to send."""
        for upload in uploads if isinstance(uploads, list) else []:
            if isinstance(upload, str):
                self._open.get(key, {}).pop(upload, None)
