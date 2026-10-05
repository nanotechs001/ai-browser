"""AI Browser's own app, built in <home>/desktop/ from Electron as it was unpacked (layout.py says where).
- macOS: Electron.app becomes "AI Browser.app".
  - Its Info.plist gets AI Browser's name, bundle id, and why it asks for the microphone and for Brave, and its icon
    (an .icns that sips makes from app/ui/icon.png). Electron's CFBundleIconName goes, or macOS would show Electron's
    icon from its asset catalog.
  - AI Browser's JavaScript goes in Contents/Resources/app/, and Electron's default app goes.
  - The fuses that would run it as Node.js or with an inspector are turned off (fuses.py).
  - Then it is signed on this computer, ad hoc (codesign --force --deep --sign -). macOS then keeps one identity for
    it, and remembers its microphone and Brave permissions.
- Windows: an "AI Browser" folder. electron.exe is renamed "AI Browser.exe", AI Browser's JavaScript goes in
  resources\\app\\, the default app goes, and the same fuses are turned off. There is no icon tool there, so
  AI Browser.exe keeps Electron's icon in File Explorer and in Task Manager. The window, the icon by the clock and the
  notifications show AI Browser's own (main.js sets them).
Everything is built in <home>/desktop/.build/ and moved into place only when complete. On any failure the app that
was there stays as it was, and the half-built one goes."""

from __future__ import annotations

import contextlib
import json
import plistlib
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .. import platforms
from . import fuses, layout
from .download import SetupError
from .release import VERSION
from .stage import ICON, part_hash, stage_app

PLIST = {"CFBundleName": layout.APP_NAME, "CFBundleDisplayName": layout.APP_NAME,
         "CFBundleIdentifier": layout.BUNDLE_ID, "CFBundleIconFile": "AI Browser.icns",
         "NSMicrophoneUsageDescription": "AI Browser listens only while you hold its talk button, in Mission Control "
                                         "or the chat.",
         # macOS shows it when it asks, once, whether AI Browser may control Brave (the chat's "This page")
         "NSAppleEventsUsageDescription": "AI Browser's chat reads the address and title of the Brave tab you're on, "
                                          "and nothing else. It never types, clicks or opens anything in Brave."}
TOOL_WAIT = 300  # seconds codesign or sips may take


@dataclass(frozen=True)
class Tools:
    """The macOS commands setup runs, as argv prefixes (tests pass stand-ins): codesign signs the app, sips makes its
    icon."""
    codesign: tuple[str, ...] = ("codesign",)
    sips: tuple[str, ...] = ("sips",)


def sign_command(tools: Tools, app: Path) -> list[str]:
    return [*tools.codesign, "--force", "--deep", "--sign", "-", str(app)]


def icon_command(tools: Tools, png: Path, icns: Path) -> list[str]:
    return [*tools.sips, "-s", "format", "icns", str(png), "--out", str(icns)]


def layer_hash(system: str) -> str:
    """AI Browser's part of the app, as this checkout would build it for `system`."""
    extra = json.dumps({"plist": PLIST if system == "darwin" else {}, "fuses": list(fuses.OFF)}, sort_keys=True)
    return part_hash(extra.encode("utf-8"))


def stale(home, system: str | None = None) -> bool:
    """An app is built here, but from another AI Browser part: a pull changed the JavaScript, the icon or the plist."""
    system = system or sys.platform
    found = layout.installed(home, system)
    return found is not None and found.get("layer") != layer_hash(system)


def _run(command: list[str], what: str) -> None:
    try:
        done = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=TOOL_WAIT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SetupError(f"{what}: {exc}") from None
    if done.returncode != 0:
        lines = done.stderr.decode("utf-8", "replace").strip().splitlines()
        raise SetupError(f"{what}: {lines[-1] if lines else f'it ended with {done.returncode}'}")


def _layer(app: Path, system: str, tools: Tools) -> None:
    """AI Browser's part, on a copy of Electron in .build: its JavaScript, its name and icon, Electron's default app
    gone, the fuses off; on macOS, signed last."""
    resources = layout.resources(app, system)
    stage_app(resources / "app")
    platforms.unlink(resources / "default_app.asar", missing_ok=True)
    if system == "darwin":
        plist = app / "Contents" / "Info.plist"
        with open(plist, "rb") as handle:
            info = plistlib.load(handle)
        info.update(PLIST)
        info.pop("CFBundleIconName", None)  # else macOS shows the asset catalog's icon (Electron's), not ours
        with open(plist, "wb") as handle:
            plistlib.dump(info, handle)
        _run(icon_command(tools, ICON, resources / PLIST["CFBundleIconFile"]), "macOS couldn't make AI Browser's icon")
        fuses.lock_down(layout.framework(app))
        _run(sign_command(tools, app), "macOS couldn't sign AI Browser's app")
    else:
        fuses.lock_down(layout.executable(app, system))


@contextlib.contextmanager
def _building(home):
    """<home>/desktop/.build, new (a stopped build's leftovers go first), and gone afterwards whatever happens.
    Failures come out as SetupError."""
    work = layout.folder(home) / ".build"
    if work.exists():
        platforms.rmtree(work)
    work.mkdir(parents=True)
    try:
        yield work
    except SetupError:
        raise
    except fuses.FuseError as exc:
        raise SetupError(str(exc)) from None
    except (OSError, ValueError) as exc:  # a copy or a rename; a broken Info.plist
        raise SetupError(f"AI Browser's app couldn't be built: {exc}") from None
    finally:
        with contextlib.suppress(OSError):
            platforms.rmtree(work)


def _into_place(built: Path, home, system: str, stamp: dict) -> Path:
    """The built app takes the place of the one there (if any), only now that it is complete."""
    final = layout.app_path(home, system)
    old = final.with_name(f".old-{final.name}")
    if old.exists():
        platforms.rmtree(old)
    if final.exists():
        platforms.replace(final, old)
    platforms.replace(built, final)
    layout.write_stamp(home, stamp)
    if old.exists():
        with contextlib.suppress(OSError):
            platforms.rmtree(old)
    return final


def build(electron: Path, home, system: str | None = None, tools: Tools = Tools(), arch: str = "",
          move: bool = False) -> Path:
    """The app, from Electron unpacked at `electron` (the zip's top folder): its path. `move` takes that folder's
    files (setup's own unpacking) instead of copying them. SetupError when it can't; nothing new is kept then."""
    system = system or sys.platform
    with _building(home) as work:
        built = work / layout.app_path(home, system).name
        source = Path(electron) / "Electron.app" if system == "darwin" else Path(electron)
        if not source.is_dir():
            raise SetupError("Electron's zip doesn't hold the app: nothing was kept")
        if move:
            platforms.replace(source, built)
        else:
            shutil.copytree(source, built, symlinks=True)
        if system != "darwin":
            platforms.replace(built / "electron.exe", layout.executable(built, system))
        _layer(built, system, tools)
        return _into_place(built, home, system, {"electron": VERSION, "system": system, "arch": arch,
                                                 "layer": layer_hash(system),
                                                 "built": time.strftime("%Y-%m-%dT%H:%M:%S")})


def refresh(home, system: str | None = None, tools: Tools = Tools()) -> Path:
    """AI Browser's part again, on the app that is there (a pull changed it), with no download: its path."""
    system = system or sys.platform
    found = layout.installed(home, system)
    if found is None:
        raise SetupError("AI Browser's app isn't set up")
    with _building(home) as work:
        built = work / layout.app_path(home, system).name
        shutil.copytree(layout.app_path(home, system), built, symlinks=True)
        _layer(built, system, tools)
        return _into_place(built, home, system, {**found, "layer": layer_hash(system),
                                                 "built": time.strftime("%Y-%m-%dT%H:%M:%S")})
