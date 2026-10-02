"""Stand-ins for the speech model's download (and, from Task 2, the speech engine): no test downloads or loads Whisper.

TINY is a pinned "model" of two small files, checked like the real one (a git blob id and a SHA-256). LocalFetch serves
them by name, never over the network: it records every URL asked for, and can fail, slow down or corrupt a file."""

from __future__ import annotations

import hashlib
import io
import time
from pathlib import Path

from ai_browser.hearing.model import ModelFile, ModelSpec, ModelStore

CONFIG = b'{"tiny": true}\n'
WEIGHTS = bytes(range(256)) * 7813  # 2,000,128 bytes: "2 MB" on the page, two 1 MB pieces and a little more
FILES = {"config.json": CONFIG, "model.bin": WEIGHTS}


def git_blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


TINY = ModelSpec(name="tiny.en", repo="test/tiny", revision="0" * 40, files=(
    ModelFile("config.json", len(CONFIG), git_sha1=git_blob_id(CONFIG)),
    ModelFile("model.bin", len(WEIGHTS), sha256=hashlib.sha256(WEIGHTS).hexdigest())))


class Slow(io.BytesIO):
    """A file's bytes, each read after `delay` seconds."""

    def __init__(self, data: bytes, delay: float):
        super().__init__(data)
        self.delay = delay

    def read(self, size: int = -1) -> bytes:
        if self.delay:
            time.sleep(self.delay)
        return super().read(size)


class LocalFetch:
    """Serves TINY's files by the last part of the URL."""

    def __init__(self):
        self.urls: list[str] = []
        self.delay = 0.0  # seconds before each read
        self.fail: Exception | None = None  # raised instead of answering
        self.corrupt: set[str] = set()  # these files come with their first byte changed
        self.extra = b""  # appended to model.bin

    def __call__(self, url: str) -> Slow:
        self.urls.append(url)
        if self.fail is not None:
            raise self.fail
        name = url.rsplit("/", 1)[1]
        data = FILES[name] + (self.extra if name == "model.bin" else b"")
        if name in self.corrupt:
            data = bytes([data[0] ^ 1]) + data[1:]
        return Slow(data, self.delay)


def install(store: ModelStore) -> None:
    """The tiny model in its folder, as after a good download."""
    store.folder.mkdir(parents=True, exist_ok=True)
    for name, data in FILES.items():
        (store.folder / name).write_bytes(data)


def tiny_store(root: Path, present: bool = True) -> ModelStore:
    """A ModelStore over TINY with a LocalFetch (store.fetch); the model in place unless present=False."""
    store = ModelStore(root, spec=TINY, fetch=LocalFetch())
    if present:
        install(store)
    return store
