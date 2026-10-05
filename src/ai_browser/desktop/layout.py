"""Where AI Browser's own app lives: <home>/desktop/ holds the app ("AI Browser.app" on macOS, an "AI Browser" folder
on Windows), its Electron profile, app.json and problem.json.
- app.json says what was built: the Electron version, the system, and a hash of AI Browser's own part, so a change
  to the JavaScript is noticed (assemble.py).
- problem.json says why the last setup or start didn't work, for Settings.
The packaged AI Browser.exe (the Windows test build, packaging/) ships its app in a `desktop` folder beside itself,
laid out the same way, and uses that one first: it is set up already.
The paths inside the bundle describe AI Browser's own app, never the user's computer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .. import platforms
from ..syncdir import write_atomic

APP_NAME = "AI Browser"
BUNDLE_ID = "io.github.nanotechs001.ai-browser"  # also Windows' AppUserModelID (main.js's APP_ID)


def _system(system: str | None) -> str:
    return system or sys.platform


def bundled() -> Path | None:
    """The packaged AI Browser.exe's own app (the Windows test build, packaging/): a `desktop` folder beside the exe,
    built there with this same layout. None when this isn't that exe, or no app was built beside it."""
    if not platforms.frozen():
        return None
    found = Path(sys.executable).parent / "desktop"
    return found if (found / "app.json").is_file() else None


def folder(home) -> Path:
    """Where the app lives: beside the packaged AI Browser.exe when it ships one, else <home>/desktop."""
    return bundled() or Path(home) / "desktop"


def app_path(home, system: str | None = None) -> Path:
    return folder(home) / (f"{APP_NAME}.app" if _system(system) == "darwin" else APP_NAME)


def executable(app: Path, system: str | None = None) -> Path:
    """The program inside an app built here (`app`: its bundle, or its folder on Windows)."""
    if _system(system) == "darwin":
        return Path(app) / "Contents" / "MacOS" / "Electron"
    return Path(app) / f"{APP_NAME}.exe"


def resources(app: Path, system: str | None = None) -> Path:
    return Path(app) / "Contents" / "Resources" if _system(system) == "darwin" else Path(app) / "resources"


def framework(app: Path) -> Path:
    """macOS: the Electron Framework binary, which holds the fuses."""
    return Path(app) / "Contents" / "Frameworks" / "Electron Framework.framework" / "Electron Framework"


def profile(home) -> Path:
    return folder(home) / "profile"  # main.js finds the same folder from where its program is


def _read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def stamp(home) -> dict | None:
    """app.json: what was built here, or None (missing, unreadable or broken: it never raises)."""
    return _read(folder(home) / "app.json")


def write_stamp(home, data: dict) -> None:
    write_atomic(folder(home) / "app.json", (json.dumps(data, indent=1) + "\n").encode("utf-8"), 0o600)


def installed(home, system: str | None = None) -> dict | None:
    """The stamp of an app built here for this system, if its program is there too; else None."""
    system, found = _system(system), stamp(home)
    if found is None or found.get("system") != system:
        return None
    return found if executable(app_path(home, system), system).is_file() else None


def problem(home) -> str:
    """Why the last setup or start didn't work, in plain words; "" when nothing went wrong."""
    found = _read(folder(home) / "problem.json")
    text = found.get("text") if found is not None else None
    return text if isinstance(text, str) else ""


def set_problem(home, text: str | None) -> None:
    """Keep why the last setup or start didn't work, for Settings; None forgets it."""
    path = folder(home) / "problem.json"
    if text:
        write_atomic(path, (json.dumps({"text": text[:300]}) + "\n").encode("utf-8"), 0o600)
    else:
        platforms.unlink(path, missing_ok=True)
