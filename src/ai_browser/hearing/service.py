"""HearingService: whether talking is ready, the speech model's download, and push-to-talk turns.

Only the user's Download click touches the network; a status is a look at file sizes. The model loads in a worker
thread at the first turn (so it loads while the user speaks), never when the app starts and never from a status. A
turn's audio is kept in memory for that turn only: never written to disk, logged, or put in an error."""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import math
import re
import sys
import threading
import time
from array import array
from collections.abc import Callable
from dataclasses import dataclass, field

from .engine import Engine
from .model import DownloadCancelled, DownloadError, ModelStore

PROGRESS_EVERY = 0.5  # seconds between two download progress messages
NO_ENGINE = ("Talking needs one extra part on this computer: in the ai-browser folder, run `uv sync --extra voice`, "
             "then restart `ai-browser app`")
NO_MODEL = "The speech model isn't on this computer yet"
BYTES_PER_SECOND = 32_000  # 16 kHz × 2 bytes, mono
MIN_BYTES = 9_600  # 0.3 s: shorter is a slip of the key
SILENCE = 0.003  # RMS as a share of full scale: below it, nothing was said
CHUNK_LIMIT = 65_536  # characters of base64 in one chunk (a 250 ms chunk is about 10.7 KB)
OPEN_GRACE = 5  # seconds a turn may stay open beyond max_seconds before it is dropped
TURN = re.compile(r"^[A-Za-z0-9-]{1,40}$")
NOTHING = "I didn't hear anything"
NOT_OPEN = "That turn isn't open"


def platform_name(platform: str = sys.platform) -> str:
    """mac, windows or linux: the page words its system-settings steps for it."""
    if platform == "darwin":
        return "mac"
    return "windows" if platform.startswith("win") else "linux"


def unavailable_status(max_seconds: int = 30) -> dict:
    """What a page hears when the app has no HearingService at all."""
    return {"state": "no_engine", "reason": NO_ENGINE, "size_bytes": 0, "done_bytes": 0, "folder": "",
            "model": "Whisper base.en", "max_seconds": max_seconds, "platform": platform_name(), "loaded": False}


def _rms(pcm: bytes | bytearray) -> float:
    """The loudness of 16-bit little-endian samples, as a share of full scale."""
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder == "big":
        samples.byteswap()
    return math.sqrt(sum(value * value for value in samples) / len(samples)) / 32768 if samples else 0.0


def _short(exc: BaseException) -> str:
    text = str(exc).strip()
    return (text.splitlines()[0] if text else type(exc).__name__)[:160]


@dataclass
class Turn:
    """One socket's open turn: its audio so far (kept only until the turn ends) and the next chunk's number."""
    id: str
    audio: bytearray = field(default_factory=bytearray)
    seq: int = 0
    timer: asyncio.TimerHandle | None = None


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
        self._lock = asyncio.Lock()  # one transcription at a time
        self._turns: dict[object, Turn] = {}  # per socket: its open turn

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

    # ---- turns: begin, chunks, finish ----------------------------------------------------------------------------

    def begin(self, key, turn) -> str:
        """Open a turn for this socket: "" when it is open, else why not. The first turn loads the model meanwhile."""
        if not isinstance(turn, str) or not TURN.match(turn):
            return "That turn has no valid id"
        self.drop(key)  # one turn per socket: a new one replaces any other
        state, reason = self._state()
        if state != "ready":
            return reason
        timer = asyncio.get_running_loop().call_later(self.max_seconds + OPEN_GRACE, self.cancel, key, turn)
        self._turns[key] = Turn(turn, timer=timer)
        self._load()
        return ""

    def add(self, key, turn, seq, b64) -> str:
        """One chunk of the turn's audio: "" when kept, else why not (and the turn is dropped)."""
        current = self._turns.get(key)
        if current is None or current.id != turn:
            return NOT_OPEN
        problem = ""
        if not isinstance(seq, int) or isinstance(seq, bool) or seq != current.seq:
            problem = "The audio arrived out of order"
        elif not isinstance(b64, str) or len(b64) > CHUNK_LIMIT:
            problem = "A piece of the audio was too big"
        else:
            try:
                pcm = base64.b64decode(b64, validate=True)
            except (binascii.Error, ValueError):
                pcm = None
            if pcm is None or len(pcm) % 2:
                problem = "A piece of the audio was damaged"
            elif len(current.audio) + len(pcm) > self.max_seconds * BYTES_PER_SECOND:
                problem = f"That was longer than {self.max_seconds} second{'' if self.max_seconds == 1 else 's'}"
            else:
                current.audio += pcm
                current.seq += 1
        if problem:
            self.drop(key)
        return problem

    async def finish(self, key, turn) -> tuple[str, str]:
        """(text, "") or ("", why not). The turn's audio is cleared whatever happens."""
        current = self._take(key, turn)
        if current is None:
            return "", NOT_OPEN
        audio = current.audio
        try:
            if len(audio) < MIN_BYTES or _rms(audio) < SILENCE:
                return "", NOTHING
            error = await asyncio.shield(self._load())
            if error:
                return "", error
            async with self._lock:
                try:
                    heard = await asyncio.to_thread(self.engine.transcribe, bytes(audio))
                except Exception as exc:  # never the audio, never the engine's own words about it
                    return "", f"Couldn't turn the speech into text ({type(exc).__name__})"
            text = heard.text.strip()
            if heard.speech_seconds <= 0 or not text:
                return "", NOTHING
            return text, ""
        finally:
            audio.clear()

    def cancel(self, key, turn) -> None:
        """Esc, a slip of the key, or a turn left open too long: its audio is dropped unheard."""
        current = self._take(key, turn)
        if current is not None:
            current.audio.clear()

    def drop(self, key) -> None:
        """Whatever turn this socket has open goes (the socket closed, or a new turn began)."""
        current = self._take(key)
        if current is not None:
            current.audio.clear()

    def _take(self, key, turn: str | None = None) -> Turn | None:
        current = self._turns.get(key)
        if current is None or (turn is not None and current.id != turn):
            return None
        del self._turns[key]
        if current.timer is not None:
            current.timer.cancel()
        return current

    def _load(self) -> asyncio.Task:
        """The model, loading in a worker thread (once): its task gives "" or why it couldn't load."""
        if self._loading is None:
            self._loading = asyncio.ensure_future(self._load_model())
        return self._loading

    async def _load_model(self) -> str:
        try:
            await asyncio.to_thread(self.engine.load, self.models.folder)
        except Exception as exc:
            self._failed = f"The speech model couldn't load: {_short(exc)}"
            self._loading = None
            self._tell()
            return self._failed
        self._loaded = True
        self._tell()
        return ""

    async def stop(self) -> None:
        """The app is closing: a download in progress is cancelled (nothing half-written is kept), and every turn's
        audio is dropped."""
        self._cancel.set()
        if self._download is not None:
            await asyncio.wait({self._download}, timeout=10)
        for key in list(self._turns):
            self.drop(key)
