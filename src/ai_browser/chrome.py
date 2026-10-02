"""Connect to the user's own running Google Chrome (remote debugging must be allowed by the user)."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

MAC_CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
ALLOW_HINT = ('open chrome://inspect/#remote-debugging in Chrome and tick "Allow remote debugging for this '
              'browser instance", then try again')


class ChromeError(RuntimeError):
    """Chrome cannot be reached; the message says how to fix it."""


def default_chrome_dir() -> Path:
    """The user's Chrome profile folder ($AIB_CHROME_DIR overrides it)."""
    configured = os.environ.get("AIB_CHROME_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / "Library" / "Application Support" / "Google" / "Chrome"


def chrome_binary() -> str | None:
    if MAC_CHROME.exists():
        return str(MAC_CHROME)
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def find_ws_url(user_data_dir: Path, timeout: float = 0) -> str:
    """The browser websocket URL from DevToolsActivePort, waiting up to `timeout` seconds for it."""
    folder = Path(user_data_dir)
    port_file = folder / "DevToolsActivePort"
    deadline = time.monotonic() + timeout
    while True:
        problem = "missing"
        if port_file.is_file():
            try:
                lines = port_file.read_text(errors="replace").splitlines()
            except OSError:  # Chrome removed it as we read it (it is closing or restarting)
                lines = []
            if len(lines) >= 2 and lines[0].strip().isdigit():
                port, path = int(lines[0].strip()), lines[1].strip()
                if _listening(port):
                    return f"ws://127.0.0.1:{port}{path}"
                problem = "stale"
        if time.monotonic() >= deadline:
            break
        time.sleep(0.1)
    if problem == "stale":
        raise ChromeError("Chrome isn't running (or was restarted without remote debugging): open Chrome; "
                          f"if it still fails, {ALLOW_HINT}")
    if not folder.is_dir():
        raise ChromeError(f"no Chrome profile folder at {folder}: install or open Google Chrome, then {ALLOW_HINT}")
    raise ChromeError(f"Chrome doesn't allow remote debugging yet: {ALLOW_HINT}")


def launch(user_data_dir: Path, headless: bool = True, extra_args: tuple[str, ...] = ()) -> subprocess.Popen:
    """Start a separate, throwaway Chrome with its own profile folder (never the user's default profile)."""
    binary = chrome_binary()
    if binary is None:
        raise ChromeError("Google Chrome is not installed")
    folder = Path(user_data_dir)
    real_profile = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    if folder.resolve() == real_profile.resolve():  # never the user's real profile, whatever AIB_CHROME_DIR says
        raise ChromeError("refusing to launch Chrome on the user's own profile folder")
    folder.mkdir(parents=True, exist_ok=True)
    args = [binary, f"--user-data-dir={folder}", "--remote-debugging-port=0", "--no-first-run",
            "--no-default-browser-check", "--disable-search-engine-choice-screen", "--window-size=1440,960"]
    if headless:
        args.append("--headless=new")
    args += [*extra_args, "about:blank"]
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
