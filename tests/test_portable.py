"""Guards that keep ai-browser portable. They run on every OS and cover every sub-project's code."""

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "ai_browser"


def test_platform_markers_skip_with_their_reason():
    import tomllib

    from conftest import PIPE_FIXTURES, POSIX_ONLY, WINDOWS_ONLY, platform_skip

    def item(*markers, fixtures=()):
        return SimpleNamespace(keywords={name: True for name in markers}, fixturenames=list(fixtures))

    assert PIPE_FIXTURES == {"stack", "watcher", "app_browser", "app_engine"}
    assert platform_skip(item("posix_only"), windows=True) == POSIX_ONLY
    assert platform_skip(item("posix_only"), windows=False) is None
    for fixture in sorted(PIPE_FIXTURES):  # they launch AI Browser over the DevTools pipe
        assert platform_skip(item(fixtures=["tmp_path", fixture]), windows=True) == POSIX_ONLY
        assert platform_skip(item(fixtures=[fixture]), windows=False) is None
    assert platform_skip(item("windows_only"), windows=False) == WINDOWS_ONLY
    assert platform_skip(item("windows_only"), windows=True) is None
    assert platform_skip(item(fixtures=["fake_claude", "tmp_path"]), windows=True) is None
    with (ROOT / "pyproject.toml").open("rb") as handle:
        markers = tomllib.load(handle)["tool"]["pytest"]["ini_options"]["markers"]
    assert f"posix_only: {POSIX_ONLY}" in markers and f"windows_only: {WINDOWS_ONLY}" in markers


def test_the_test_helpers_work_on_this_system(tmp_path):
    from conftest import file_mode, symlink_or_skip

    target = tmp_path / "target.txt"
    target.write_bytes(b"x")
    target.chmod(0o600)
    assert file_mode(target) == (None if os.name == "nt" else 0o600)
    symlink_or_skip(target, tmp_path / "link.txt")  # skips, with the reason, where links can't be made
    assert (tmp_path / "link.txt").is_symlink()


LIST_MODULES = r'''
import importlib, pkgutil, sys
import ai_browser
for module in pkgutil.walk_packages(ai_browser.__path__, "ai_browser."):
    importlib.import_module(module.name)
print("\n".join(sorted(name for name in sys.modules if not name.startswith("ai_browser") and name != "__main__")))
'''

LIKE_WINDOWS = r'''
import importlib, importlib.abc, os, pkgutil, sys

BLOCKED = ("fcntl", "termios", "resource", "pwd", "grp")
for name in sys.stdin.read().split():  # the libraries ai_browser brings in, loaded first, the way this OS loads them
    if name.split(".")[0] not in BLOCKED:
        try:
            importlib.import_module(name)
        except Exception:
            pass


class WindowsHasNone(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return None


for name in BLOCKED:
    sys.modules.pop(name, None)
sys.meta_path.insert(0, WindowsHasNone())
for attr in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK", "posix_spawn", "POSIX_SPAWN_OPEN", "POSIX_SPAWN_DUP2",
             "WNOHANG"):
    if hasattr(os, attr):
        delattr(os, attr)
import ai_browser

failed = {}


def note(name):
    failed.setdefault(name, f"{sys.exc_info()[0].__name__}: {sys.exc_info()[1]}")


for module in pkgutil.walk_packages(ai_browser.__path__, "ai_browser.", onerror=note):
    if module.name in sys.modules or module.name in failed:
        continue
    try:
        importlib.import_module(module.name)
    except Exception as exc:
        failed[module.name] = f"{type(exc).__name__}: {exc}"
print("\n".join(f"{name}: {why}" for name, why in sorted(failed.items())))
'''


def test_every_module_imports_on_a_windows_like_python():
    """The investigation's simulation, kept: no POSIX-only module or os name may be needed at import time."""
    names = subprocess.run([sys.executable, "-c", LIST_MODULES], capture_output=True, encoding="utf-8", check=True,
                           timeout=180).stdout
    result = subprocess.run([sys.executable, "-c", LIKE_WINDOWS], input=names, capture_output=True,
                            encoding="utf-8", timeout=180)
    assert result.returncode == 0 and not result.stdout.strip(), result.stdout + result.stderr[-2000:]


def test_the_mcp_example_sets_utf8_for_the_server():
    example = json.loads((ROOT / ".mcp.json.example").read_text(encoding="utf-8"))
    assert example["mcpServers"]["ai-browser"]["env"]["PYTHONUTF8"] == "1"


def _binary_mode(node) -> bool:
    """A mode counts as binary when it is a literal with b, or an `x if c else y` of such literals."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return "b" in node.value
    if isinstance(node, ast.IfExp):
        return _binary_mode(node.body) and _binary_mode(node.orelse)
    return False


def _true(call: ast.Call, name: str) -> bool:
    return any(kw.arg == name and isinstance(kw.value, ast.Constant) and kw.value.value is True for kw in call.keywords)


def text_io_calls(source: str) -> list[ast.Call]:
    """The calls that read or write text without naming the encoding (Windows would use its code page):
    .read_text() with no positional argument, .write_text(x) with one, open() and os.fdopen() in a mode without b,
    and subprocess calls with text=True or universal_newlines=True."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or any(kw.arg == "encoding" for kw in node.keywords):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
        owner = func.value.id if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) else ""
        if isinstance(func, ast.Attribute) and name == "read_text" and not node.args:
            found.append(node)  # WorkDir.read_text(path, limit) has two
        elif isinstance(func, ast.Attribute) and name == "write_text" and len(node.args) == 1:
            found.append(node)  # WorkDir.write_text(path, content) has two
        elif (isinstance(func, ast.Name) and name == "open") or (owner == "os" and name == "fdopen"):
            mode = node.args[1] if len(node.args) > 1 else next(
                (kw.value for kw in node.keywords if kw.arg == "mode"), None)
            if mode is None or not _binary_mode(mode):
                found.append(node)
        elif owner == "subprocess" and (_true(node, "text") or _true(node, "universal_newlines")):
            found.append(node)
    return found


def test_text_io_names_its_encoding():
    found = [f"{path.relative_to(ROOT)}:{call.lineno}"
             for top in (SRC, ROOT / "tests") for path in sorted(top.rglob("*.py"))
             for call in text_io_calls(path.read_text(encoding="utf-8"))]
    assert not found, "text read or written without encoding=:\n" + "\n".join(sorted(found))
