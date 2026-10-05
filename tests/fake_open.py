"""A stand-in for macOS's `open`, for the launcher's tests. It takes the arguments LaunchServices would get
(-n -W -a <app> --args …), and logs them, with the mode of the line's folder, to FAKE_OPEN_LOG. Then it runs the fake
app (fake_electron.py) with the --args, and waits for it, as `open -W` does. With FAKE_OPEN_EXIT, the new copy
quits at once instead, as when another copy holds the app's profile: `open` ends with that code."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import fake_electron


def main(argv: list[str]) -> int:
    folder = next((Path(arg.split("=", 1)[1]).parent for arg in argv if arg.startswith("--aib-line=")), None)
    mode = stat.S_IMODE(os.stat(folder).st_mode) if folder is not None and folder.exists() else None
    with open(os.environ["FAKE_OPEN_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps({"argv": argv, "folder_mode": mode}) + "\n")
    if argv[:3] != ["-n", "-W", "-a"] or len(argv) < 5 or argv[4] != "--args" or not Path(argv[3]).is_dir():
        return 1
    if os.environ.get("FAKE_OPEN_EXIT"):
        return int(os.environ["FAKE_OPEN_EXIT"])
    return fake_electron.main(argv[5:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
