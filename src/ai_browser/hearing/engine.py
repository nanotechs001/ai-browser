"""The speech engine: faster-whisper with Whisper base.en, on the CPU in int8, on macOS and Windows alike. It is an
optional extra (`uv sync --extra voice`): nothing heavy is imported until the model loads, so the app starts the same
without it. The audio arrives as 16 kHz mono 16-bit little-endian samples and stays in memory."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Heard:
    text: str
    speech_seconds: float  # how much speech the voice detector found: 0 means nothing was said


class Engine(Protocol):
    def available(self) -> bool: ...

    def load(self, folder: Path) -> None: ...  # in a worker thread

    def transcribe(self, pcm: bytes) -> Heard: ...  # in a worker thread


class WhisperEngine:
    def __init__(self):
        self._model = None
        self._available: bool | None = None

    def available(self) -> bool:
        if self._available is None:  # looked up, never imported
            self._available = importlib.util.find_spec("faster_whisper") is not None
        return self._available

    def load(self, folder: Path) -> None:
        folder = Path(folder)
        if not folder.is_dir():  # a name that isn't a folder would make faster-whisper look it up on Hugging Face
            raise FileNotFoundError(f"no model folder at {folder}")
        from faster_whisper import WhisperModel

        self._model = WhisperModel(str(folder), device="cpu", compute_type="int8", local_files_only=True)

    def transcribe(self, pcm: bytes) -> Heard:
        import numpy

        if self._model is None:
            raise RuntimeError("the speech model isn't loaded")
        audio = numpy.frombuffer(pcm, "<i2").astype(numpy.float32) / 32768.0
        segments, info = self._model.transcribe(audio, language="en", beam_size=1, vad_filter=True,
                                                condition_on_previous_text=False, without_timestamps=True)
        text = " ".join(segment.text.strip() for segment in segments).strip()  # the work happens here, in the thread
        return Heard(text=text, speech_seconds=float(info.duration_after_vad or 0.0))
