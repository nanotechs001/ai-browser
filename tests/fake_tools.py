"""Stand-ins for macOS's codesign and sips, for setup's tests. Each run is logged with its exact argv (the tool's
name first) to FAKE_TOOLS_LOG. sips writes its --out file as sips would (here a copy of the PNG). FAKE_TOOLS_FAIL
names a tool that fails, as the real one would, with a line on stderr."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    name, args = argv[0], argv[1:]
    with open(os.environ["FAKE_TOOLS_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps([name, *args]) + "\n")
    if os.environ.get("FAKE_TOOLS_FAIL") == name:
        sys.stderr.write(f"{name}: fake failure\n")
        return 1
    if name == "sips":  # sips -s format icns <png> --out <icns>
        shutil.copyfile(args[3], args[args.index("--out") + 1])
    return 0


def fake_tools(tmp_path, monkeypatch):
    """(Tools that run this file instead of codesign and sips, the log they write)."""
    from ai_browser.desktop.assemble import Tools
    from conftest import fake_python

    log = tmp_path / "tools.log"
    monkeypatch.setenv("FAKE_TOOLS_LOG", str(log))
    me = str(Path(__file__).resolve())
    return Tools(codesign=(fake_python(), me, "codesign"), sips=(fake_python(), me, "sips")), log


def tool_runs(log: Path) -> list[list[str]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
