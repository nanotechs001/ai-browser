"""Electron's release in miniature, for setup's tests: its SHASUMS256.txt and a zip served from memory
(ReleaseFetch). From Task 3 it also has zips with Electron's own layout: a Mac's Electron.app with its framework's
links and fuses, or Windows' electron.exe, a few bytes per file. No test downloads Electron."""

from __future__ import annotations

import hashlib
import io
import stat
import zipfile

SENTINEL = b"dL7pKGdnNz796PbbjQWNKmHXBZaB9tsX"  # Electron's fuse wire starts after it (desktop/fuses.py)
WIRE = SENTINEL + bytes([1, 9]) + b"101100011"  # Electron 44's fuses as it ships them: runAsNode, nodeOptions and
#                                                 nodeCliInspect on
FRAMEWORK = "Electron.app/Contents/Frameworks/Electron Framework.framework"
PLIST = (b'<?xml version="1.0" encoding="UTF-8"?>\n'
         b'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
         b'<plist version="1.0"><dict>'
         b"<key>CFBundleExecutable</key><string>Electron</string>"
         b"<key>CFBundleIconFile</key><string>electron.icns</string>"
         b"<key>CFBundleIconName</key><string>AppIcon</string>"  # an asset catalog's icon, which macOS prefers
         b"<key>CFBundleIdentifier</key><string>com.github.Electron</string>"
         b"<key>CFBundleName</key><string>Electron</string>"
         b"<key>CFBundleShortVersionString</key><string>44.5.1</string>"
         b"</dict></plist>\n")
WHEN = (2026, 10, 4, 0, 0, 0)


def add_file(archive: zipfile.ZipFile, name: str, data: bytes, mode: int = 0o644) -> None:
    info = zipfile.ZipInfo(name, WHEN)
    info.external_attr = (stat.S_IFREG | mode) << 16
    archive.writestr(info, data, zipfile.ZIP_DEFLATED)


def add_link(archive: zipfile.ZipFile, name: str, target: str) -> None:
    """A symbolic link, stored as zip stores one: its mode says link, and its content is the target."""
    info = zipfile.ZipInfo(name, WHEN)
    info.external_attr = (stat.S_IFLNK | 0o755) << 16
    archive.writestr(info, target.encode("utf-8"))


def mac_zip(wire: bytes = WIRE) -> bytes:
    """Electron's darwin zip, in miniature. Electron.app has its program, its Info.plist, its default app and its
    icon. Its framework's binary holds the fuses and is reached through links, as in the real one."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        add_file(archive, "Electron.app/Contents/Info.plist", PLIST)
        add_file(archive, "Electron.app/Contents/MacOS/Electron", b"\xcf\xfa\xed\xfe the program", 0o755)
        add_file(archive, "Electron.app/Contents/Resources/default_app.asar", b"Electron's own app")
        add_file(archive, "Electron.app/Contents/Resources/electron.icns", b"Electron's icon")
        add_file(archive, f"{FRAMEWORK}/Versions/A/Electron Framework", b"\x00framework\x00" + wire + b"\x00rest",
                 0o755)
        add_file(archive, f"{FRAMEWORK}/Versions/A/Resources/Info.plist", PLIST)
        add_link(archive, f"{FRAMEWORK}/Versions/Current", "A")
        add_link(archive, f"{FRAMEWORK}/Electron Framework", "Versions/Current/Electron Framework")
        add_link(archive, f"{FRAMEWORK}/Resources", "Versions/Current/Resources")
        add_file(archive, "LICENSE", b"MIT")
        add_file(archive, "version", b"44.5.1")
    return buffer.getvalue()


def windows_zip(wire: bytes = WIRE) -> bytes:
    """Electron's win32-x64 zip, in miniature: electron.exe holds the fuses."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        add_file(archive, "electron.exe", b"MZ the program\x00" + wire + b"\x00rest")
        add_file(archive, "resources/default_app.asar", b"Electron's own app")
        add_file(archive, "ffmpeg.dll", b"MZ a library")
        add_file(archive, "LICENSE", b"MIT")
        add_file(archive, "version", b"44.5.1")
    return buffer.getvalue()


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
