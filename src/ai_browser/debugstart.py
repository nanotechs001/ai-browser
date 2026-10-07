"""AIB_DEBUG_START=1: `ai-browser app` says each step of its start on stderr, each line starting "[start] ": the app's
launch, its start message, its hello or the wait running out, which window draws AI Browser, each page's cookie, and
each window socket. The Windows build's start check turns it on (packaging/windows_app.py start). It is off by
default, and on it adds those lines and changes nothing else. AI Browser's own app keeps its side of the start in its
profile then (debug-start.log, main.js). No line ever holds a cookie's value or a start code: names, paths, and yes or
no only."""

from __future__ import annotations

import os
import sys

SWITCH = "AIB_DEBUG_START"
PREFIX = "[start] "


def on() -> bool:
    return os.environ.get(SWITCH) == "1"


def say(text: str) -> None:
    if on():
        print(PREFIX + text, file=sys.stderr, flush=True)


def address(url: str) -> str:
    """A start address with its code hidden: http://127.0.0.1:8793/open?code=…"""
    base, _, query = url.partition("?")
    return f"{base}?code=…" if query else base
