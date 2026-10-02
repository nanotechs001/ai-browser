r"""The work folder on Windows: open a file below the work root without following any link, junction or WSL link.

POSIX opens each folder relative to the one before it (dir_fd); Windows can't. So every folder on the way is opened
by its full path (with the \\?\ prefix, so deep folders work) and held, without FILE_SHARE_DELETE, until the file is
open: none of them can be renamed or swapped meanwhile. Each folder below the root is checked for a reparse point
(symbolic links, junctions, and the links a Linux container makes through Docker Desktop's file share all are one),
and the file's final path must lie inside the work root's. Imports on any OS; Win32 is touched only in functions."""

from __future__ import annotations

import ctypes
import errno
import functools
import ntpath
import os

from . import platforms
from .workfs import PathError

_BAD = frozenset('<>:"/\\|?*') | frozenset(chr(code) for code in range(32))
_DEVICES = frozenset({"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
                      *(f"COM{n}" for n in "123456789¹²³"), *(f"LPT{n}" for n in "123456789¹²³")})
LINK = "{}: is a symbolic link (or inside one); use the file it points to"

GENERIC_READ, GENERIC_WRITE, FILE_READ_ATTRIBUTES = 0x80000000, 0x40000000, 0x80
FILE_SHARE_READ, FILE_SHARE_WRITE = 0x1, 0x2  # never FILE_SHARE_DELETE: a held folder can't be renamed or swapped
OPEN_EXISTING, OPEN_ALWAYS = 3, 4
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000  # lets a folder open, so it can be told apart from a file
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000  # a link is opened as itself, never followed
FILE_ATTRIBUTE_DIRECTORY, FILE_ATTRIBUTE_REPARSE_POINT = 0x10, 0x400
ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND, ERROR_ACCESS_DENIED, ERROR_ALREADY_EXISTS = 2, 3, 5, 183
_INVALID = ctypes.c_void_p(-1).value


def windows_name_problem(name: str) -> str | None:
    """Why Windows can't hold this file or folder name, or None. The device names are the ones Python 3.13's
    ntpath.isreserved knows, in any case, with or without an extension (nul.txt too)."""
    if not name:
        return "an empty name"
    bad = sorted({char for char in name if char in _BAD})
    if bad:  # ":" also rules out alternate data streams
        return "it contains " + " ".join(repr(char) for char in bad)
    if name[-1] in ". ":
        return "it ends with a dot or a space"
    if name.partition(".")[0].rstrip(" ").upper() in _DEVICES:
        return "it is a device name (CON, NUL, COM1…)"
    return None


class _FileTime(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]


class _Info(ctypes.Structure):  # BY_HANDLE_FILE_INFORMATION
    _fields_ = [("attributes", ctypes.c_uint32), ("created", _FileTime), ("accessed", _FileTime),
                ("written", _FileTime), ("volume", ctypes.c_uint32), ("size_high", ctypes.c_uint32),
                ("size_low", ctypes.c_uint32), ("links", ctypes.c_uint32), ("index_high", ctypes.c_uint32),
                ("index_low", ctypes.c_uint32)]


@functools.cache
def _kernel32():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle, dword, boolean, text = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p
    kernel32.CreateFileW.argtypes = (text, dword, dword, ctypes.c_void_p, dword, dword, handle)
    kernel32.CreateFileW.restype = handle
    kernel32.CreateDirectoryW.argtypes, kernel32.CreateDirectoryW.restype = (text, ctypes.c_void_p), boolean
    kernel32.GetFileInformationByHandle.argtypes = (handle, ctypes.POINTER(_Info))
    kernel32.GetFileInformationByHandle.restype = boolean
    kernel32.GetFinalPathNameByHandleW.argtypes = (handle, text, dword, dword)
    kernel32.GetFinalPathNameByHandleW.restype = dword
    kernel32.SetEndOfFile.argtypes, kernel32.SetEndOfFile.restype = (handle,), boolean
    kernel32.CloseHandle.argtypes, kernel32.CloseHandle.restype = (handle,), boolean
    return kernel32


def _long(path: str) -> str:
    r"""A full path in the \\?\ form, so folders deeper than 260 characters work."""
    if path.startswith("\\\\?\\"):
        return path
    if path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path[2:]
    return "\\\\?\\" + path


def _error(code: int, shown: str) -> OSError:
    if code in (ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND):
        return FileNotFoundError(errno.ENOENT, "no such file", shown)
    if code == ERROR_ACCESS_DENIED:
        return PermissionError(errno.EACCES, "access denied", shown)
    error = ctypes.WinError(code)
    error.filename = shown
    return error


def _open(path: str, access: int, disposition: int, flags: int, shown: str) -> int:
    handle = _kernel32().CreateFileW(path, access, FILE_SHARE_READ | FILE_SHARE_WRITE, None, disposition, flags, None)
    if handle in (None, _INVALID):
        raise _error(ctypes.get_last_error(), shown)
    return handle


def _attributes(handle: int, shown: str) -> int:
    info = _Info()
    if not _kernel32().GetFileInformationByHandle(handle, ctypes.byref(info)):
        raise _error(ctypes.get_last_error(), shown)
    return info.attributes


def _final_path(handle: int, shown: str) -> str:
    size = 512
    while True:
        buffer = ctypes.create_unicode_buffer(size)
        length = _kernel32().GetFinalPathNameByHandleW(handle, buffer, size, 0)
        if not length:
            raise _error(ctypes.get_last_error(), shown)
        if length < size:
            return buffer.value
        size = length + 1


def _close(handle: int) -> None:
    _kernel32().CloseHandle(handle)


def _hold_folder(path: str, follow: bool, shown: str) -> int:
    """Open and hold a folder. GENERIC_READ, not only attributes: an open that reads nothing takes no part in the
    sharing checks, and the missing FILE_SHARE_DELETE is what stops a rename while it is held."""
    flags = FILE_FLAG_BACKUP_SEMANTICS | (0 if follow else FILE_FLAG_OPEN_REPARSE_POINT)
    handle = _open(path, GENERIC_READ, OPEN_EXISTING, flags, shown)
    if follow:  # the work root: the app made it, and the sandbox can't replace its own mount point
        return handle
    try:
        attributes = _attributes(handle, shown)
        if attributes & FILE_ATTRIBUTE_REPARSE_POINT:
            raise PathError(LINK.format(shown))
        if not attributes & FILE_ATTRIBUTE_DIRECTORY:  # like POSIX's ENOTDIR
            raise FileNotFoundError(errno.ENOENT, "no such file", shown)
    except BaseException:
        _close(handle)
        raise
    return handle


def _what_is(path: str, shown: str) -> str:
    """"link", "folder" or "file", read with attribute access only (for a name Windows wouldn't open for writing)."""
    handle = _open(path, FILE_READ_ATTRIBUTES, OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS,
                   shown)
    try:
        attributes = _attributes(handle, shown)
    finally:
        _close(handle)
    if attributes & FILE_ATTRIBUTE_REPARSE_POINT:
        return "link"
    return "folder" if attributes & FILE_ATTRIBUTE_DIRECTORY else "file"


def _inside(final: str, root: str) -> bool:
    final, root = ntpath.normcase(final), ntpath.normcase(root).rstrip("\\")
    return final.startswith(root + "\\")


def open_in(root, folders, name: str, writing: bool, shown: str = "") -> int:
    """A binary file descriptor for root/folders.../name, opened without following any link below the root. Writes
    create missing folders, and truncate only after every check."""
    shown = shown or "/".join([*folders, name])
    for part in (*folders, name):
        if windows_name_problem(part):
            raise PathError(f"{shown}: not a valid file name on Windows")
    held: list[int] = []
    try:
        path = _long(os.path.abspath(root))
        held.append(_hold_folder(path, True, shown))
        root_final = _final_path(held[0], shown)
        for folder in folders:
            path = f"{path}\\{folder}"
            if writing and not _kernel32().CreateDirectoryW(path, None):
                code = ctypes.get_last_error()
                if code != ERROR_ALREADY_EXISTS:
                    raise _error(code, shown)
            held.append(_hold_folder(path, False, shown))
        return _open_file(f"{path}\\{name}", writing, root_final, shown)
    finally:
        for handle in held:
            _close(handle)


def _open_file(path: str, writing: bool, root_final: str, shown: str) -> int:
    import msvcrt  # Windows only

    access = GENERIC_READ | (GENERIC_WRITE if writing else 0)
    flags = FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS
    try:
        handle = _open(path, access, OPEN_ALWAYS if writing else OPEN_EXISTING, flags, shown)
    except PermissionError:
        kind = _what_is(path, shown)
        if kind == "link":
            raise PathError(LINK.format(shown)) from None
        if kind == "folder":
            raise IsADirectoryError(errno.EISDIR, "is a folder", shown) from None
        raise
    try:
        attributes = _attributes(handle, shown)
        if attributes & FILE_ATTRIBUTE_REPARSE_POINT:
            raise PathError(LINK.format(shown))
        if attributes & FILE_ATTRIBUTE_DIRECTORY:
            raise IsADirectoryError(errno.EISDIR, "is a folder", shown)
        if not _inside(_final_path(handle, shown), root_final):  # belt and braces
            raise PathError(f"{shown}: points outside /work")
        if writing and not _kernel32().SetEndOfFile(handle):  # at 0: the file was just opened
            raise _error(ctypes.get_last_error(), shown)
        return msvcrt.open_osfhandle(handle, (os.O_WRONLY if writing else os.O_RDONLY) | platforms.O_BINARY)
    except BaseException:
        _close(handle)
        raise
