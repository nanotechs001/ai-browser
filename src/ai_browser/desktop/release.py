"""The one Electron release AI Browser's own app is built on, pinned: its version, and for each computer the zip's
name, size and SHA-256 as the release lists them (GitHub's releases API, 2026-10-04). Setup downloads only these
files, from this release, and checks them against its SHASUMS256.txt. Nothing here touches the network."""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from pathlib import Path

VERSION = "44.5.1"  # the newest stable Electron on 2026-10-04 (45 was still an alpha)
RELEASE = f"https://github.com/electron/electron/releases/download/v{VERSION}"
SHASUMS = f"{RELEASE}/SHASUMS256.txt"
SETUP_COMMAND = "uv run ai-browser doctor --setup"


@dataclass(frozen=True)
class Asset:
    system: str  # sys.platform's value: "darwin" or "win32"
    arch: str  # "arm64" or "x64"
    name: str
    size: int  # bytes
    sha256: str
    where: str  # the computer, in plain words

    @property
    def url(self) -> str:
        return f"{RELEASE}/{self.name}"

    @property
    def megabytes(self) -> str:
        return f"{round(self.size / 1_000_000)} MB"


ASSETS = (
    Asset("darwin", "arm64", f"electron-v{VERSION}-darwin-arm64.zip", 130_259_261,
          "1d75703019bb16461ae65f3081d7e6f5c0b11e901d0ccb5c343bcf7bcdd6435c", "a Mac with Apple silicon"),
    Asset("darwin", "x64", f"electron-v{VERSION}-darwin-x64.zip", 134_208_970,
          "e567d13833d0e161d7749727355b98643461df3395b537cfa7bdddf8a8bfedff", "an Intel Mac"),
    Asset("win32", "x64", f"electron-v{VERSION}-win32-x64.zip", 157_998_329,
          "9b382492dcfee91f8f9e92c91f7972550a1b95d2299cac72279dab33a600d7db", "Windows (x64)"),
)
_ARCHES = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64", "amd64": "x64", "x64": "x64"}


def arch(machine: str | None = None) -> str:
    """platform.machine() in Electron's words ("arm64", "x64"), or "" for anything else."""
    return _ARCHES.get((platform.machine() if machine is None else machine).lower(), "")


def asset_for(system: str | None = None, machine: str | None = None) -> Asset | None:
    """The zip for this computer; None where AI Browser's own app doesn't run (Linux, Windows on Arm)."""
    system, found = system or sys.platform, arch(machine)
    return next((asset for asset in ASSETS if asset.system == system and asset.arch == found), None)


def offer(asset: Asset, folder: Path, system: str | None = None) -> list[str]:
    """What `doctor --setup` shows before it asks: what the app adds, what is downloaded (the version, the size, the
    address), how it is checked, and where the app goes."""
    if (system or sys.platform) == "darwin":
        adds = "its own Dock icon, a menu-bar icon, the ⌥Space shortcut and notifications"
    else:
        adds = "a taskbar icon, an icon by the clock, the Alt+Space shortcut and notifications"
    lines = [f"AI Browser can run as its own app: {adds}.",
             f"It is built from Electron {VERSION} for {asset.where}: {asset.megabytes}, from",
             f"  {asset.url}",
             "The download is checked against Electron's SHASUMS256.txt. If anything doesn't match, nothing is kept.",
             f"The app is built in {folder}. Nothing else is downloaded."]
    if (system or sys.platform) == "win32":
        lines.append("It also adds AI Browser to the Start menu, so Windows can show its notifications.")
    return lines
