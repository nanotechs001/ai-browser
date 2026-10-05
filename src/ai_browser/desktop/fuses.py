"""Electron's fuses, set in AI Browser's own copy before it is signed. Fuses are switches built into the Electron
binary that no command line and no environment variable can turn back on. AI Browser turns off the three that would
let another program borrow the app, with the microphone and Brave permissions macOS gives it: running it as plain
Node.js, NODE_OPTIONS, and Node's inspector switches. The wire sits right after a fixed sentinel:
| sentinel | version (1) | length | one byte per fuse: "0" off, "1" on, "r" removed |
On macOS it is in the Electron Framework binary, on Windows in the program itself (layout.py)."""

from __future__ import annotations

import mmap
from pathlib import Path

SENTINEL = b"dL7pKGdnNz796PbbjQWNKmHXBZaB9tsX"
WIRE_VERSION = 1
RUN_AS_NODE, NODE_OPTIONS, NODE_CLI_INSPECT = 0, 2, 3  # Electron's fuse order (its docs: tutorial/fuses)
OFF = (RUN_AS_NODE, NODE_OPTIONS, NODE_CLI_INSPECT)
STATES = frozenset(b"01r")
NONE_FOUND = "This Electron build has no fuses: nothing was kept"
UNKNOWN = "This Electron build has fuses AI Browser doesn't know: nothing was kept"


class FuseError(Exception):
    """The binary's fuses can't be found or read, so the app isn't built (plain words)."""


def wires(data) -> list[int]:
    """Where each fuse wire starts (one per architecture in the binary), each one checked. FuseError when there is
    none, or one can't be read. `data` is bytes or an mmap."""
    found, start = [], 0
    while (at := data.find(SENTINEL, start)) != -1:
        head = at + len(SENTINEL)
        if head + 2 > len(data) or data[head] != WIRE_VERSION:
            raise FuseError(UNKNOWN)
        length, wire = data[head + 1], head + 2
        if length <= max(OFF) or wire + length > len(data) \
                or any(byte not in STATES for byte in data[wire:wire + length]):
            raise FuseError(UNKNOWN)
        found.append(wire)
        start = wire + length
    if not found:
        raise FuseError(NONE_FOUND)
    return found


def lock_down(binary: Path) -> None:
    """Turn the OFF fuses off in `binary`, in place: its other bytes and its file mode stay. Every wire is checked
    before any byte changes."""
    if Path(binary).stat().st_size == 0:
        raise FuseError(NONE_FOUND)
    with open(binary, "r+b") as handle, mmap.mmap(handle.fileno(), 0) as data:
        for wire in wires(data):
            for fuse in OFF:
                if data[wire + fuse] == ord("1"):
                    data[wire + fuse] = ord("0")
        data.flush()


def states(binary: Path) -> list[str]:
    """Each wire's fuses as text ("000000011"), for the tests."""
    if Path(binary).stat().st_size == 0:
        raise FuseError(NONE_FOUND)
    with open(binary, "rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
        return [data[wire:wire + data[wire - 1]].decode("ascii") for wire in wires(data)]
