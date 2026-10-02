"""Per-session record of every tool call, plus saved screenshots."""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

CLIP = 500


def new_task_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)


def _clip(value):
    if isinstance(value, str) and len(value) > CLIP:
        return value[:CLIP] + "…"
    return value


class TaskLog:
    def __init__(self, root: Path, task_id: str):
        self.dir = Path(root) / task_id
        self.shots = self.dir / "shots"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._shot_count = len(list(self.shots.glob("*.jpg"))) if self.shots.is_dir() else 0

    def record(self, tool: str, args: dict, ms: int, outcome: str, result: str) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "tool": tool,
            "args": {key: _clip(value) for key, value in args.items()},
            "ms": ms,
            "outcome": outcome,
            "result": _clip(result),
        }
        with open(self.dir / "log.jsonl", "a", encoding="utf-8", errors="replace") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def save_shot(self, data: bytes, label: str) -> Path:
        self.shots.mkdir(parents=True, exist_ok=True)
        self._shot_count += 1
        slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "shot"
        path = self.shots / f"{self._shot_count:03d}-{slug}.jpg"
        path.write_bytes(data)
        return path
