"""What the fake claude's `auth status` says, for the AI accounts tests. A Claude Code folder holding SIGNED_IN is
signed in: the fake then prints EMAIL, ORG_ID and ORG_NAME too, as Claude Code does, so the tests can show that none of
them ever reaches a file, a page or a log. conftest signs every test's throwaway Default folder in."""

import json
from pathlib import Path

SIGNED_IN = "fake-signed-in.json"  # {"plan": "pro"}; with "say", `auth status` prints that text; "sleep" waits first
EMAIL = "someone.private@example.com"
ORG_ID = "org-7f3a9e1c-0000-secret"
ORG_NAME = "Private Org Name"


def sign_in(folder, plan: str | None = "pro", **extra) -> Path:
    """Mark a Claude Code folder signed in, for the fake claude's `auth status`."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / SIGNED_IN
    marker.write_text(json.dumps({"plan": plan, **extra}), encoding="utf-8")
    return marker


def sign_out(folder) -> None:
    (Path(folder) / SIGNED_IN).unlink(missing_ok=True)
