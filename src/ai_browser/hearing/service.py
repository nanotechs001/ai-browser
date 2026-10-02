"""HearingService: whether talking is ready, the speech model's download, and push-to-talk turns.

Only the user's Download click touches the network; a status is a look at file sizes. The model loads in a worker
thread at the first turn (so it loads while the user speaks), never when the app starts and never from a status. A
turn's audio is kept in memory for that turn only: never written to disk, logged, or put in an error."""

from __future__ import annotations

import asyncio
import contextlib
import sys
import threading
import time
from collections.abc import Callable

from .engine import Engine
from .model import DownloadCancelled, DownloadError, ModelStore

PROGRESS_EVERY = 0.5  # seconds between two download progress messages
NO_ENGINE = ("Talking needs one extra part on this computer: in the ai-browser folder, run `uv sync --extra voice`, "
             "then restart `ai-browser app`")
NO_MODEL = "The speech model isn't on this computer yet"


def platform_name(platform: str = sys.platform) -> str:
    """mac, windows or linux: the page words its system-settings steps for it."""
    if platform == "darwin":
        return "mac"
    return "windows" if platform.startswith("win") else "linux"


def unavailable_status(max_seconds: int = 30) -> dict:
    """What a page hears when the app has no HearingService at all."""
    return {"state": "no_engine", "reason": NO_ENGINE, "size_bytes": 0, "done_bytes": 0, "folder": "",
            "model": "Whisper base.en", "max_seconds": max_seconds, "platform": platform_name(), "loaded": False}


class HearingService:
    def __init__(self, models: ModelStore, engine: Engine, max_seconds: int = 30, platform: str = sys.platform):
        self.models = models
        self.engine = engine
        self.max_seconds = max_seconds
        self.platform = platform_name(platform)
        self.on_status: Callable[[dict], None] = lambda status: None  # the app server's broadcast to every page
        self._failed = ""  # why the last download or load failed (cleared by the next Download)
        self._download: asyncio.Task | None = None
        self._cancel = threading.Event()
        self._done = 0  # bytes downloaded so far
        self._sent_at = 0.0
        self._loading: asyncio.Task | None = None
        self._loaded = False

    # ---- status ----------------------------------------------------------------------------------------------------

    def _state(self) -> tuple[str, str]:
        if not self.engine.available():
            return "no_engine", NO_ENGINE
        if self._download is not None:
            return "downloading", "Downloading the speech model"
        if self._failed:
            return "failed", self._failed
        if not self.models.present():
            return "no_model", NO_MODEL
        return "ready", ""

    def status(self) -> dict:
        state, reason = self._state()
        return {"state": state, "reason": reason, "size_bytes": self.models.size_bytes,
                "done_bytes": self._done if state == "downloading" else 0, "folder": str(self.models.folder),
                "model": f"Whisper {self.models.spec.name}", "max_seconds": self.max_seconds,
                "platform": self.platform, "loaded": self._loaded}

    def _tell(self) -> None:
        self._sent_at = time.monotonic()
        with contextlib.suppress(Exception):  # a page that went away never breaks hearing
            self.on_status(self.status())

    # ---- the model's download: only from the Download button -------------------------------------------------------

    def start_download(self) -> None:
        if self._download is not None or self._state()[0] not in ("no_model", "failed"):
            return  # one at a time, and never over a model that is there and loads
        self._failed, self._done = "", 0
        self._cancel.clear()
        self._loaded, self._loading = False, None  # the new files load at the next turn
        self._download = asyncio.ensure_future(self._fetch(asyncio.get_running_loop()))
        self._tell()

    def cancel_download(self) -> None:
        self._cancel.set()

    async def _fetch(self, loop: asyncio.AbstractEventLoop) -> None:
        def progress(done: int) -> None:  # called in the worker thread
            loop.call_soon_threadsafe(self._progressed, done)

        try:
            await asyncio.to_thread(self.models.download, progress, self._cancel.is_set)
        except DownloadCancelled:
            pass  # nothing was kept: the model is still missing
        except DownloadError as exc:
            self._failed = str(exc)
        except Exception as exc:  # whatever else went wrong, the page learns that it failed
            self._failed = f"The download failed: {type(exc).__name__}"
        finally:
            self._download, self._done = None, 0
            self._tell()

    def _progressed(self, done: int) -> None:
        if self._download is None:
            return
        self._done = done
        if time.monotonic() - self._sent_at >= PROGRESS_EVERY:
            self._tell()

    async def stop(self) -> None:
        """The app is closing: a download in progress is cancelled, and nothing half-written is kept."""
        self._cancel.set()
        if self._download is not None:
            await asyncio.wait({self._download}, timeout=10)
