"""Claude Code, found the same way on every OS: the native executable, never the npm install's .cmd script.

On Windows an npm claude.cmd runs through cmd.exe. cmd.exe cuts the multi-line --append-system-prompt at its first
line (the agent's safety rules are in it) and mangles quoting, and stopping it would end only cmd.exe while the real
CLI kept running. So it is refused, with the whole explanation."""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

NPM_SCRIPT = ("Claude Code was found at {path}, a script from the npm install. AI Browser needs the native claude.exe: "
              "install it with `irm https://claude.ai/install.ps1 | iex` in PowerShell, or set AIB_CLAUDE to the full "
              "path of claude.exe.")


class ClaudeNotUsable(OSError):
    """Claude Code can't be used as found; the message is the whole explanation."""


def claude_argv(claude: str | Sequence[str] | None = None, system: str | None = None,
                env: Mapping | None = None) -> list[str]:
    """The command that starts Claude Code: the argument (a string, or a list such as [python, fake_claude.py]),
    else $AIB_CLAUDE, else (Windows) %USERPROFILE%\\.local\\bin\\claude.exe, else claude on PATH, else
    ~/.local/bin/claude (claude.exe on Windows)."""
    windows = (system or sys.platform) == "win32"
    env = os.environ if env is None else env
    if isinstance(claude, (list, tuple)):
        argv = [str(part) for part in claude]
    elif claude:
        argv = [str(claude)]
    elif env.get("AIB_CLAUDE"):
        argv = [env["AIB_CLAUDE"]]
    else:
        argv = [_find(windows, env)]
    if windows and argv[0].lower().endswith((".cmd", ".bat")):
        raise ClaudeNotUsable(NPM_SCRIPT.format(path=argv[0]))
    return argv


def _find(windows: bool, env: Mapping) -> str:
    if windows:  # where the native installer puts it, ahead of an npm claude.cmd on PATH
        native = Path(env.get("USERPROFILE") or Path.home()) / ".local" / "bin" / "claude.exe"
        if native.is_file():
            return str(native)
    found = shutil.which("claude", path=env.get("PATH"))
    if found:
        return found
    return str(Path.home() / ".local" / "bin" / ("claude.exe" if windows else "claude"))
