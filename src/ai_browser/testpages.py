"""Serve ai-browser's local test pages from inside a sandbox, on two origins."""

from __future__ import annotations

import functools
import importlib.util
import shutil
import threading
import time
from collections.abc import Callable
from http.server import ThreadingHTTPServer
from pathlib import Path

from .sandbox import DockerError, SandboxInfo, Sandboxes

PAGES = Path(__file__).with_name("pages")
BASE = "http://localhost:8000/"
OTHER = "http://127.0.0.1:8001/"  # a different site, so frames from it are cross-origin
_PROBE = "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/form.html; echo; " \
         "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/form.html"


def _handler() -> type:
    """The request handler of pages/_serve.py, which the in-sandbox servers run too."""
    spec = importlib.util.spec_from_file_location("ai_browser_test_serve", PAGES / "_serve.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.NoStore


def serve_host() -> tuple[str, str, Callable[[], None]]:
    """Serve the pages from this Mac (for a Chrome running outside Docker). Returns (base, other, stop)."""
    handler = functools.partial(_handler(), directory=str(PAGES))
    servers = [ThreadingHTTPServer(("127.0.0.1", 0), handler) for _ in range(2)]
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()

    def stop() -> None:
        for server in servers:
            server.shutdown()
            server.server_close()

    first, second = (server.server_address[1] for server in servers)
    return f"http://localhost:{first}/", f"http://127.0.0.1:{second}/", stop


def serve(sandboxes: Sandboxes, info: SandboxInfo) -> tuple[str, str]:
    """Copy the pages into /work/_pages and start two static servers. Returns (base, other)."""
    shutil.copytree(PAGES, info.work_host / "_pages", dirs_exist_ok=True)
    if sandboxes.exec(info.name, _PROBE, timeout=5).output.split() == ["200", "200"]:
        return BASE, OTHER
    sandboxes.exec(
        info.name,
        "cd /work/_pages && "
        "(nohup python3 _serve.py 8000 >/dev/null 2>&1 &) && "
        "(nohup python3 _serve.py 8001 >/dev/null 2>&1 &)",
        timeout=10,
    )
    deadline = time.monotonic() + 10
    while sandboxes.exec(info.name, _PROBE, timeout=5).output.split() != ["200", "200"]:
        if time.monotonic() > deadline:
            raise DockerError("test page servers did not start in the sandbox")
        time.sleep(0.2)
    return BASE, OTHER
