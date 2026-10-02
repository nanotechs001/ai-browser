"""The speech model: Whisper base.en for faster-whisper, pinned to one revision of Systran's repo on Hugging Face.

It is downloaded only when the user clicks Download (the page shows its size and source first), file by file into a
`.part` folder, and checked: model.bin by its SHA-256, the small files by their git blob id (SHA-1 of b"blob <size>\\0"
plus the content). Only when every size and hash matches does the folder take its place; on a mismatch, an error or
Cancel, nothing is kept. Nothing else here touches the network: whether the model is present is a look at file sizes."""

from __future__ import annotations

import hashlib
import os
import shutil
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REVISION = "3d3d5dee26484f91867d81cb899cfcf72b96be6c"  # the repo's head on 2026-10-02 (last changed 2023-11-23)
PIECE = 1 << 20  # bytes read at a time: Cancel is checked between pieces
SPARE = 50_000_000  # free disk space kept beyond the model itself
MISMATCH = "The download didn't match the expected file: nothing was kept"


class DownloadError(Exception):
    """A download that failed, in plain words for the page."""


class DownloadCancelled(Exception):
    """The user pressed Cancel, or the app is closing."""


@dataclass(frozen=True)
class ModelFile:
    name: str
    size: int
    sha256: str | None = None  # large (LFS) files: SHA-256 of the content
    git_sha1: str | None = None  # small files: git's blob id


@dataclass(frozen=True)
class ModelSpec:
    name: str
    repo: str
    revision: str
    files: tuple[ModelFile, ...]

    @property
    def size_bytes(self) -> int:
        return sum(file.size for file in self.files)

    def url(self, file: ModelFile) -> str:
        return f"https://huggingface.co/{self.repo}/resolve/{self.revision}/{file.name}"


MODEL = ModelSpec(name="base.en", repo="Systran/faster-whisper-base.en", revision=REVISION, files=(
    ModelFile("config.json", 2_227, git_sha1="594369787efe617005d199b03739ee0ead7e3ab7"),
    ModelFile("model.bin", 145_216_508, sha256="2a166925539a16005f14ff328359f9b9adb9dc4fb631bb3b227526862e93e2ef"),
    ModelFile("tokenizer.json", 2_128_466, git_sha1="15d7bdf9ba25718ca2504eec6a8f02bc55af0a6a"),
    ModelFile("vocabulary.txt", 422_309, git_sha1="ee695b8d3e3c10d488304e04468efec4ca27554a")))


def tls_context() -> ssl.SSLContext:
    """The computer's own certificate store (truststore, in the base install), else Python's defaults. Certificates
    are always checked."""
    try:
        import truststore
    except ImportError:
        return ssl.create_default_context()
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def urlopen_fetch(url: str):
    """The answer to one GET. Hugging Face redirects to its file store, and urllib follows."""
    return urllib.request.urlopen(url, context=tls_context(), timeout=30)


def _network(reason) -> str:
    if isinstance(reason, ssl.SSLError):
        return "The download failed: the connection to Hugging Face couldn't be checked"
    if isinstance(reason, TimeoutError):
        return "The download stopped: the connection timed out"
    return "No internet connection"


class ModelStore:
    def __init__(self, root: Path, spec: ModelSpec = MODEL, fetch: Callable = urlopen_fetch):
        self.root = Path(root)
        self.spec = spec
        self.fetch = fetch

    @property
    def folder(self) -> Path:
        return self.root / f"faster-whisper-{self.spec.name}"

    @property
    def part(self) -> Path:
        return self.root / f"faster-whisper-{self.spec.name}.part"

    @property
    def size_bytes(self) -> int:
        return self.spec.size_bytes

    def present(self) -> bool:
        """Every pinned file is there at its pinned size (the hashes were checked when it was downloaded)."""
        try:
            return all((self.folder / file.name).stat().st_size == file.size for file in self.spec.files)
        except OSError:
            return False

    def remove_partial(self) -> None:
        shutil.rmtree(self.part, ignore_errors=True)

    def download(self, progress: Callable[[int], None] = lambda done: None,
                 cancelled: Callable[[], bool] = lambda: False) -> None:
        """Fetch every file into the .part folder, check it, then put the folder in place. A worker thread runs it;
        `progress` gets the bytes so far, and `cancelled` is asked between pieces."""
        need = self.size_bytes + SPARE
        self.root.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(self.root).free < need:
            raise DownloadError(f"Not enough free disk space: {round(need / 1_000_000)} MB is needed")
        self.remove_partial()
        self.part.mkdir(parents=True)
        try:
            done = 0
            for file in self.spec.files:
                done = self._fetch(file, done, progress, cancelled)
            if self.folder.exists():  # only now, with every file checked, does the old folder go
                shutil.rmtree(self.folder)
            os.replace(self.part, self.folder)
        except BaseException:
            self.remove_partial()
            raise

    def _fetch(self, file: ModelFile, done: int, progress, cancelled) -> int:
        digest = hashlib.sha256() if file.sha256 else hashlib.sha1(b"blob %d\0" % file.size)
        size = 0
        try:
            with self.fetch(self.spec.url(file)) as answer, open(self.part / file.name, "wb") as out:
                while True:
                    if cancelled():
                        raise DownloadCancelled()
                    piece = answer.read(PIECE)
                    if not piece:
                        break
                    size += len(piece)
                    if size > file.size:
                        raise DownloadError(MISMATCH)
                    digest.update(piece)
                    out.write(piece)
                    progress(done + size)
        except urllib.error.HTTPError as exc:
            raise DownloadError(f"The download failed: Hugging Face answered {exc.code}") from None
        except urllib.error.URLError as exc:
            raise DownloadError(_network(exc.reason)) from None
        except TimeoutError:
            raise DownloadError("The download stopped: the connection timed out") from None
        except OSError as exc:  # writing the file: the disk filled up, or the folder went away
            raise DownloadError(f"The download failed: {exc.strerror or type(exc).__name__}") from None
        if size != file.size or digest.hexdigest() != (file.sha256 or file.git_sha1):
            raise DownloadError(MISMATCH)
        return done + size
