"""Paths, limits and the user's config file for ai-browser."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

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
    """The repository root (holds docker/ and skills/)."""
    return Path(__file__).resolve().parents[2]


@dataclass
class Config:
    blocked_skills: list[str] = field(default_factory=list)
    risky_words: list[str] = field(default_factory=lambda: list(RISKY_WORDS))


def load_config(root: Path) -> Config:
    """Read root/config.json; a missing or invalid file gives the defaults."""
    try:
        data = json.loads((root / "config.json").read_text())
    except (OSError, ValueError):
        return Config()
    cfg = Config()
    if not isinstance(data, dict):
        return cfg
    blocked = data.get("blocked_skills")
    if isinstance(blocked, list):
        cfg.blocked_skills = [str(item) for item in blocked]
    words = data.get("risky_words")
    if isinstance(words, list) and words:
        cfg.risky_words = [str(item) for item in words]
    return cfg
