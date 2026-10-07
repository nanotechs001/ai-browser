"""Which sandbox AI Browser uses for its sandboxed browser, website QA and skill scripts (the no-Docker spec,
docs/superpowers/specs/2026-10-07-no-docker-design.md):
- "docker": Chromium and a script shell in Docker containers (sandbox.py), as before;
- "local": a separate browser on this computer with an empty profile of its own (localbox.py), and no shell of AI
  Browser's: skill scripts run through the agent's own commands, which ask the user first.
Settings → Sandbox holds the user's choice: Auto (the default: Docker when it runs and its image is built, Local
otherwise), Docker, or Local. AIB_SANDBOX ("docker" or "local") wins over it for one process: the app sets it for each
agent's tools, so an agent's MCP server uses the sandbox its Claude Code was started with."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from .config import IMAGE
from .sandbox import DockerError, Sandboxes
from .settings import Settings

DOCKER, LOCAL = "docker", "local"
NAMES = {DOCKER: "Docker", LOCAL: "Local, without Docker"}
LOOK_AGAIN = 30.0  # seconds a look at Docker holds: Auto asks Docker at most this often
_looked: dict[str, tuple[float, bool, str]] = {}  # image -> (when, ready, why not)
_lock = threading.Lock()
clock = time.monotonic  # (tests replace it)


def docker_ready(image: str = IMAGE) -> tuple[bool, str]:
    """(True, "") when Docker runs and the sandbox image is built; else (False, its one-line reason)."""
    with _lock:
        seen = _looked.get(image)
        if seen is not None and clock() - seen[0] < LOOK_AGAIN:
            return seen[1], seen[2]
    try:
        Sandboxes(Path.home(), image).check()  # `docker info`, then the image: nothing starts
        ready, why = True, ""
    except DockerError as exc:
        ready, why = False, str(exc)
    with _lock:
        _looked[image] = (clock(), ready, why)
    return ready, why


def forced(env=None) -> str:
    """AIB_SANDBOX's "docker" or "local", or "" (unset, or anything else)."""
    value = str((os.environ if env is None else env).get("AIB_SANDBOX", "")).strip().lower()
    return value if value in (DOCKER, LOCAL) else ""


def resolve(home, env=None) -> str:
    """"docker" or "local": AIB_SANDBOX, else the user's choice; Auto asks Docker whether it is ready."""
    pinned = forced(env)
    if pinned:
        return pinned
    choice = Settings(home).get()["sandbox"]
    if choice in (DOCKER, LOCAL):
        return choice
    return DOCKER if docker_ready()[0] else LOCAL


def describe(home, env=None) -> dict:
    """What AI Home, Settings and doctor say, in one line: {"choice": "auto" | "docker" | "local", "using": "docker" |
    "local", "line": …}. A chosen Docker is looked at too, so the line can say it isn't ready."""
    choice = Settings(home).get()["sandbox"]
    pinned = forced(env)
    if pinned:
        return {"choice": choice, "using": pinned, "line": f"Sandbox: {NAMES[pinned]} (set by AIB_SANDBOX)"}
    if choice == LOCAL:
        return {"choice": choice, "using": LOCAL, "line": f"Sandbox: {NAMES[LOCAL]}"}
    ready, why = docker_ready()
    if choice == DOCKER:
        return {"choice": choice, "using": DOCKER,
                "line": "Sandbox: Docker" if ready else f"Sandbox: Docker, which isn't ready: {why}"}
    if ready:
        return {"choice": choice, "using": DOCKER, "line": "Sandbox: Docker (Auto: Docker is ready)"}
    return {"choice": choice, "using": LOCAL, "line": f"Sandbox: {NAMES[LOCAL]} (Auto: Docker isn't ready)"}
