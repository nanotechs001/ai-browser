"""Map sandbox paths under /work to the host folder that backs them, refusing escapes.

The sandboxed shell can change the work folder at any moment, so host-side reads and writes open every path step
without following symbolic links: a link swapped in after a check cannot point them at the user's own files."""

from __future__ import annotations

import errno
import os
import posixpath
import shutil
import stat
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from . import platforms

SANDBOX_ROOT = "/work"
_FOLDER = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)  # Windows Python has neither


class PathError(ValueError):
    """A path outside /work, or one the sandbox could have redirected."""


class WorkDir:
    def __init__(self, host_root: Path, task_id: str):
        self.host_root = Path(host_root)
        self.task_id = task_id
        self.host_task = self.host_root / task_id
        self.sandbox_task = f"{SANDBOX_ROOT}/{task_id}"
        self.host_task.mkdir(parents=True, exist_ok=True)
        # copies of uploads sit next to the work folder, where no container can see or swap them
        self.staging = self.host_root.parent / "uploads" / task_id
        self._snapshots = 0

    def _relative(self, path: str) -> PurePosixPath:
        """Path relative to /work; relative inputs are relative to the task folder."""
        if path.startswith("/"):
            norm = posixpath.normpath(path)
            if norm != SANDBOX_ROOT and not norm.startswith(SANDBOX_ROOT + "/"):
                raise PathError(f"{path!r}: files must be under /work")
            return PurePosixPath(norm).relative_to(SANDBOX_ROOT)
        rel = PurePosixPath(posixpath.normpath(f"{self.task_id}/{path}"))
        if rel.parts and rel.parts[0] == "..":
            raise PathError(f"{path!r}: files must be under /work")
        return rel

    def to_host(self, path: str) -> Path:
        host = self.host_root / self._relative(path)
        if not host.resolve().is_relative_to(self.host_root.resolve()):
            raise PathError(f"{path!r}: points outside /work")
        return host

    def to_sandbox(self, path: str) -> str:
        rel = self._relative(path).as_posix()
        return SANDBOX_ROOT if rel == "." else f"{SANDBOX_ROOT}/{rel}"

    def _open(self, path: str, flags: int) -> BinaryIO:
        """Open a regular file in the work folder, never through a symbolic link (writes create folders)."""
        *folders, name = self._relative(path).parts or ("",)
        if not name:
            raise IsADirectoryError(errno.EISDIR, "is a folder", path)
        writing = bool(flags & os.O_WRONLY)
        if platforms.WINDOWS:  # no dir_fd there: winfs holds each folder open instead (and NTFS has no FIFOs)
            from . import winfs

            return os.fdopen(winfs.open_in(self.host_root, folders, name, writing, path), "wb" if writing else "rb")
        fd = os.open(self.host_root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            for folder in folders:
                if writing:
                    try:
                        os.mkdir(folder, dir_fd=fd)
                    except FileExistsError:
                        pass
                parent, fd = fd, -1
                try:
                    fd = os.open(folder, _FOLDER, dir_fd=parent)
                except NotADirectoryError:  # macOS reports a linked folder this way
                    if stat.S_ISLNK(os.stat(folder, dir_fd=parent, follow_symlinks=False).st_mode):
                        raise OSError(errno.ELOOP, "symbolic link", path) from None
                    raise
                finally:
                    os.close(parent)
            # O_NONBLOCK: a FIFO the shell left behind must not hang the engine
            file = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o644, dir_fd=fd)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise PathError(f"{path}: is a symbolic link (or inside one); use the file it points to") from None
            if exc.errno == errno.ENOTDIR:
                raise FileNotFoundError(errno.ENOENT, "no such file", path) from None
            if exc.errno == errno.ENXIO:
                raise PathError(f"{path}: not a regular file") from None
            raise
        finally:
            if fd >= 0:
                os.close(fd)
        mode = os.fstat(file).st_mode
        if not stat.S_ISREG(mode):
            os.close(file)
            if stat.S_ISDIR(mode):
                raise IsADirectoryError(errno.EISDIR, "is a folder", path)
            raise PathError(f"{path}: not a regular file")
        os.set_blocking(file, True)
        return os.fdopen(file, "wb" if writing else "rb")

    def read_text(self, path: str, limit: int) -> str:
        with self._open(path, os.O_RDONLY) as handle:
            text = handle.read().decode(errors="replace")
        if len(text) > limit:
            text = text[:limit] + f"\n[truncated: {len(text) - limit} more chars]"
        return text

    def write_text(self, path: str, content: str) -> str:
        return self.write_bytes(path, content.encode())

    def write_bytes(self, path: str, data: bytes) -> str:
        with self._open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC) as handle:
            handle.write(data)
        return self.to_sandbox(path)

    def snapshot(self, path: str) -> Path:
        """Copy a work-folder file into a private folder for an upload, so the sandbox cannot swap it later."""
        with self._open(path, os.O_RDONLY) as source:
            self._snapshots += 1
            folder = self.staging / str(self._snapshots)
            folder.mkdir(parents=True, exist_ok=True)
            copy = folder / self._relative(path).name  # the site sees the original file name
            with open(copy, "wb") as target:
                shutil.copyfileobj(source, target)
        return copy

    def drop_snapshots(self) -> None:
        shutil.rmtree(self.staging, ignore_errors=True)
