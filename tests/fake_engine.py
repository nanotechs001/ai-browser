"""Stand-ins for the speech model's download (and, from Task 2, the speech engine): no test downloads or loads Whisper.

TINY is a pinned "model" of two small files, checked like the real one (a git blob id and a SHA-256). LocalFetch serves
them by name, never over the network: it records every URL asked for, and can fail, slow down or corrupt a file."""

from __future__ import annotations

import hashlib
import io
import threading
import time
from pathlib import Path

from ai_browser.hearing.model import ModelFile, ModelSpec, ModelStore
from ai_browser.hearing.engine import Heard

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


class FakeEngine:
    """The speech engine, faked: each transcription gives the next answer (the last one repeats). It records every
    turn's audio, every load, and whether two transcriptions ever ran at once."""

    def __init__(self, answers=("hello",), available: bool = True, delay: float = 0.0,
                 load_error: Exception | None = None):
        self.answers = list(answers)
        self.installed = available  # False: as if `uv sync --extra voice` hadn't been run
        self.delay = delay  # seconds each load and each transcription take
        self.load_error = load_error
        self.error: Exception | None = None  # raised by transcribe
        self.speech_seconds = 1.0  # how much speech the voice detector "found"
        self.heard: list[bytes] = []
        self.loads: list[Path] = []
        self.overlapped = False
        self._busy = 0
        self._guard = threading.Lock()

    def available(self) -> bool:
        return self.installed

    def load(self, folder) -> None:
        self.loads.append(Path(folder))
        if self.delay:
            time.sleep(self.delay)
        if self.load_error is not None:
            raise self.load_error

    def transcribe(self, pcm: bytes) -> Heard:
        with self._guard:
            self._busy += 1
            self.overlapped = self.overlapped or self._busy > 1
        try:
            self.heard.append(bytes(pcm))
            if self.delay:
                time.sleep(self.delay)
            if self.error is not None:
                raise self.error
            text = self.answers.pop(0) if len(self.answers) > 1 else (self.answers[0] if self.answers else "")
            return Heard(text=text, speech_seconds=self.speech_seconds)
        finally:
            with self._guard:
                self._busy -= 1
