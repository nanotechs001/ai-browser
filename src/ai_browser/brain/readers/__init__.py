"""The Brain's readers: page scripts AI Browser's engine runs in an isolated world of a tab in the user's Brave
(app/inworld.py, through BraveLink.run_reader). BUNDLE holds them all, in FILES' order, under one KEY: a world whose
AIB has this KEY has them already, so they go in once per page. call() builds one call: its name is one of CALLS, and
its arguments go as JSON, never as code. page.js is the floating chat's: it reads the page the user asked about
(BraveLink.read_page), only on that ask."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

FILES = ("common.js", "gmail.js", "slack.js", "asana.js", "region.js", "picker.js", "page.js")
_SOURCE = "\n".join(Path(__file__).with_name(name).read_text(encoding="utf-8") for name in FILES)
KEY = hashlib.sha256(_SOURCE.encode("utf-8")).hexdigest()[:12]
BUNDLE = _SOURCE.replace("{{KEY}}", KEY)
MISSING = "__aib_missing__"  # what a call answers in a world without this bundle
CALLS = frozenset({"read", "thread", "fill", "loaded", "pick", "unpick", "page"})
KINDS = frozenset({"gmail", "slack", "asana", "region"})  # region: a part of a page the user picked


def call(name: str, *args) -> str:
    """The expression that calls AIB.<name>(*args) in a world that has this bundle, and answers MISSING in one that
    doesn't (a new page: the bundle goes in, then the same call again)."""
    if name not in CALLS:
        raise ValueError(f"there is no reader call {name!r}")
    arguments = ", ".join(json.dumps(arg) for arg in args)
    return f'(globalThis.AIB?.key === "{KEY}" ? AIB.{name}({arguments}) : "{MISSING}")'
