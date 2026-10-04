"""Setting up AI Browser's own app, for `ai-browser doctor --setup` (cli.py). After the user's typed yes, the pinned
Electron is downloaded and checked (download.py), unpacked (unpack.py) and built into the app (assemble.py), all in
<home>/desktop/. Whatever fails, and on Ctrl-C, nothing is kept but a note of why (layout.set_problem), which
Settings shows; the browser window works as before. It runs only while AI Browser itself isn't running."""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Callable
from pathlib import Path

from .. import platforms
from ..hearing.model import urlopen_fetch
from . import layout
from .assemble import Tools, build
from .download import SetupError, download
from .release import Asset
from .unpack import UnpackError, unpack

FETCH = urlopen_fetch  # the network (conftest replaces it: no test downloads Electron)
TOOLS = Tools()  # codesign and sips (the tests pass stand-ins)
STOPPED = "The setup was stopped before the end: nothing was kept"
RUNNING = "AI Browser is running: quit it, then run the setup again"


def _progress(asset: Asset, out: Callable[[str], None]) -> Callable[[int], None]:
    """A line about every tenth of the download."""
    step, shown = max(1, asset.size // 10), [0]

    def progress(done: int) -> None:
        if done - shown[0] >= step or done == asset.size:
            shown[0] = done
            out(f"Downloaded {round(done / 1_000_000)} of {asset.megabytes}")

    return progress


def _clear(work: Path) -> None:
    if work.exists():
        with contextlib.suppress(OSError):
            platforms.rmtree(work)


def set_up(home, asset: Asset, out: Callable[[str], None] = print, system: str | None = None) -> Path:
    """The app, downloaded, checked and built: its path. SetupError when anything fails, with the reason kept for
    Settings. On Ctrl-C the reason is kept too, and KeyboardInterrupt goes on up. Nothing else is kept either way."""
    system = system or sys.platform
    (Path(home) / "app").mkdir(parents=True, exist_ok=True)
    lock = platforms.lock_file(Path(home) / "app" / "lock")  # `ai-browser app` holds it while it runs
    if lock is None:
        raise SetupError(RUNNING)
    work = layout.folder(home) / ".download"
    try:
        _clear(work)
        zipped = download(asset, work, FETCH, _progress(asset, out))
        out("It matches Electron's SHASUMS256.txt. Building AI Browser's app…")
        unpack(zipped, work / "electron")
        platforms.unlink(zipped)
        app = build(work / "electron", home, system, TOOLS, arch=asset.arch, move=True)
    except (UnpackError, OSError) as exc:
        reason = str(exc) if isinstance(exc, UnpackError) else f"Electron couldn't be unpacked: {exc.strerror or exc}"
        layout.set_problem(home, reason)
        raise SetupError(reason) from None
    except SetupError as exc:
        layout.set_problem(home, str(exc))
        raise
    except BaseException:
        layout.set_problem(home, STOPPED)
        raise
    finally:
        _clear(work)
        lock.close()
    layout.set_problem(home, None)
    return app
