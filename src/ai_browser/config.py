"""Paths, limits and the user's config file for ai-browser."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import platforms

IMAGE = "ai-browser-sandbox:0.1"
CDP_PORT = 9223  # socat inside the container, forwarding to Chromium's 127.0.0.1:9222
LIVE_PORTS = range(8770, 8791)

# name -> (width, height, mobile)
SIZES = {"desktop": (1440, 900, False), "tablet": (768, 1024, True), "mobile": (390, 844, True)}

MAX_ROWS = 150
TEXT_LIMIT = 1500
NAME_LIMIT = 80
SHELL_LIMIT = 10_000
READ_LIMIT = 50_000
JS_LIMIT = 10_000
SHOT_MAX_WIDTH = 1280
SHOT_MAX_HEIGHT = 10_000

RISKY_WORDS = [
    "publish", "update", "delete", "remove", "trash", "submit", "send", "pay", "buy",
    "purchase", "order", "checkout", "confirm", "sign up", "register", "subscribe", "post",
    "share", "invite", "transfer", "unpublish", "schedule", "deactivate",
]


def home() -> Path:
    """ai-browser's state directory: $AIB_HOME or ~/.ai-browser."""
    return Path(os.environ.get("AIB_HOME", "~/.ai-browser")).expanduser()


def project_root() -> Path:
    """The repository root (holds docker/ and skills/). In the packaged AI Browser.exe (packaging/): its bundle's
    folder, where the build put both."""
    if platforms.frozen():
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


@dataclass
class Config:
    blocked_skills: list[str] = field(default_factory=list)
    risky_words: list[str] = field(default_factory=lambda: list(RISKY_WORDS))


def _read(path: Path) -> dict:
    """config.json's object. Read as bytes: json finds UTF-8 with or without a BOM (Notepad's "UTF-8 with BOM",
    PowerShell 5.1's `Set-Content -Encoding UTF8`) and UTF-16 (PowerShell 5.1's `>`). OSError or ValueError when
    it can't be used."""
    data = json.loads(path.read_bytes())
    if isinstance(data, dict):
        return data
    raise ValueError("not a JSON object {...}")  # caught with json's own errors


def config_problem(root: Path) -> str | None:
    """Why root/config.json is ignored (the defaults apply then), or None when it is fine or there is none."""
    path = root / "config.json"
    try:
        _read(path)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        return f"{path} can't be used ({exc}), so the defaults apply: fix it, or save it as UTF-8"
    return None


def load_config(root: Path) -> Config:
    """Read root/config.json; a missing or invalid file gives the defaults (config_problem says why)."""
    try:
        data = _read(root / "config.json")
    except (OSError, ValueError):
        return Config()
    cfg = Config()
    blocked = data.get("blocked_skills")
    if isinstance(blocked, list):
        cfg.blocked_skills = [str(item) for item in blocked]
    words = data.get("risky_words")
    if isinstance(words, list) and words:
        cfg.risky_words = [str(item) for item in words]
    return cfg
