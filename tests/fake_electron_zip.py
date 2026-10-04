"""Electron's release in miniature, for setup's tests: its SHASUMS256.txt and a zip served from memory
(ReleaseFetch). From Task 3 it also has zips with Electron's own layout: a Mac's Electron.app with its framework's
links and fuses, or Windows' electron.exe, a few bytes per file. No test downloads Electron."""

from __future__ import annotations

import hashlib
import io


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Cut(io.BytesIO):
    """A zip's bytes. With `at`, the connection drops once that many have been read (ConnectionResetError)."""

    def __init__(self, data: bytes, at: int | None = None):
        super().__init__(data)
        self.at = at

    def read(self, size: int = -1) -> bytes:
        if self.at is not None:
            if self.tell() >= self.at:
                raise ConnectionResetError(54, "Connection reset by peer")
            size = self.at - self.tell() if size < 0 else min(size, self.at - self.tell())
        return super().read(size)


class ReleaseFetch:
    """GitHub's release, from memory, by the last part of the address: SHASUMS256.txt (listing `asset`'s checksum, or
    `listed`) and the zip. It records every address asked for. It can fail (`fail`), drop the connection mid-zip
    (`cut_at`), end the zip early with no error (`short`), change a byte (`corrupt`) or add bytes (`extra`)."""

    def __init__(self, asset, data: bytes):
        self.asset, self.data = asset, data
        self.urls: list[str] = []
        self.listed = asset.sha256
        self.fail: Exception | None = None
        self.cut_at: int | None = None
        self.short = False
        self.corrupt = False
        self.extra = b""

    def __call__(self, url: str) -> io.BytesIO:
        self.urls.append(url)
        if self.fail is not None:
            raise self.fail
        if url.rsplit("/", 1)[1] == "SHASUMS256.txt":
            lines = f"{'0' * 64} *electron-v44.5.1-linux-x64.zip\n{self.listed} *{self.asset.name}\n"
            return io.BytesIO(lines.encode("utf-8"))
        data = self.data[:-1000] if self.short else self.data
        if self.corrupt:
            data = bytes([data[0] ^ 1]) + data[1:]
        return Cut(data + self.extra, self.cut_at)
