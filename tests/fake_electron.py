"""A stand-in for AI Browser's own app (desktop/electron/main.js), for the launcher's tests. It speaks the same line:
JSON lines on its stdin and stdout, or on the socket --aib-line=<path> names. It answers start with hello (its pid),
answers a shortcut as its plan says, and quits on the engine's quit or when the line ends. FAKE_ELECTRON_LOG gets its
argv and every message it reads. FAKE_ELECTRON_PLAN (JSON) says what else it does:
- "hello": false: it never says hello;
- "start_status": {...}: right after hello, the state of the shortcut it was started with;
- "shortcuts": {value: {"ok", "why"}}: its answer to a shortcut request (any other value: ok);
- "click": true: it clicks each notification it gets;
- "quit_after": seconds: the user's Quit, that long after the start."""

from __future__ import annotations

import json
import os
import socket
import sys
import threading


def main(argv: list[str]) -> int:
    plan = json.loads(os.environ.get("FAKE_ELECTRON_PLAN") or "{}")
    lock = threading.Lock()
    log = open(os.environ["FAKE_ELECTRON_LOG"], "a", encoding="utf-8")  # noqa: SIM115 (open until the end)

    def note(entry: dict) -> None:
        with lock:
            log.write(json.dumps(entry) + "\n")
            log.flush()

    note({"argv": argv})
    path = next((arg.split("=", 1)[1] for arg in argv if arg.startswith("--aib-line=")), None)
    if path:
        line = socket.socket(socket.AF_UNIX)
        line.connect(path)
        reader, writer = line.makefile("rb"), line.makefile("wb")
    else:
        reader, writer = sys.stdin.buffer, sys.stdout.buffer

    def say(message: dict) -> None:
        with lock:
            writer.write((json.dumps(message) + "\n").encode("utf-8"))
            writer.flush()

    def quit_later(seconds: float) -> None:
        def now() -> None:
            say({"type": "quit"})
            os._exit(0)

        threading.Timer(seconds, now).start()

    for raw in reader:
        message = json.loads(raw.decode("utf-8"))
        note({"got": message})
        kind = message.get("type")
        if kind == "start":
            if plan.get("hello", True):
                say({"type": "hello", "pid": os.getpid()})
            if "start_status" in plan:
                say({"type": "shortcut", "value": message.get("shortcut"), "pressed": False, **plan["start_status"]})
            if "quit_after" in plan:
                quit_later(plan["quit_after"])
        elif kind == "shortcut":
            answer = plan.get("shortcuts", {}).get(str(message.get("value")), {"ok": True, "why": ""})
            say({"type": "shortcut", "value": message.get("value"), "request": message.get("request"),
                 "pressed": False, **answer})
        elif kind == "notify" and plan.get("click"):
            say({"type": "clicked", "id": message["id"]})
        elif kind == "quit":
            break
    log.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
