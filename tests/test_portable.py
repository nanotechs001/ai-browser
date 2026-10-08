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

    from conftest import POSIX_ONLY, WINDOWS_ONLY, platform_skip

    def item(*markers, fixtures=()):
        return SimpleNamespace(keywords={name: True for name in markers}, fixturenames=list(fixtures))

    assert platform_skip(item("posix_only"), windows=True) == POSIX_ONLY
    assert platform_skip(item("posix_only"), windows=False) is None
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


MAC_ONLY = {
    ("platforms.py", "this Mac"),  # this_computer() itself
    ("app/ui/mission.js", 'MAC ? "⌘ K"'),  # New Mission's key, named so on a Mac only
    ("app/ui/composer.js", 'MAC ? "⌘ ↵"'),  # the main button's key, named so on a Mac only
    # Add (path, snippet) here only for text shown when a platform value says macOS, for example voice-input's
    # macOS microphone lines chosen by hearing_status.platform == "mac".
}
PAGE_SUFFIXES = {".html", ".js", ".css", ".json", ".svg", ".txt", ".md"}


def _mac_only(path: Path, text: str) -> bool:
    relative = path.relative_to(SRC).as_posix()
    return any(relative == where and snippet in text for where, snippet in MAC_ONLY)


def _docstrings(tree: ast.AST) -> set[int]:
    return {id(node.body[0].value) for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body
            and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)}


def test_no_mac_words_where_windows_shows_them():
    found = []
    pages = [*(SRC / "app" / "ui").rglob("*"), *(SRC / "brain" / "readers").rglob("*")]  # and the tabs' scripts
    for path in sorted(pages):
        if path.is_file() and path.suffix in PAGE_SUFFIXES:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for word in ("this Mac", "⌘"):
                    if word in line and not _mac_only(path, line):
                        found.append(f"{path.relative_to(SRC).as_posix()}:{number}: {word}")
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        skip = _docstrings(tree)  # comments aren't in the tree; docstrings may keep "this Mac"
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip \
                    and "this Mac" in node.value and not _mac_only(path, node.value):
                found.append(f"{path.relative_to(SRC).as_posix()}:{node.lineno}: this Mac")
    assert not found, "Mac-only words in text Windows shows:\n" + "\n".join(found)


def test_the_voice_model_swap_goes_through_the_retrying_helpers():
    path = SRC / "hearing" / "model.py"
    if not path.exists():
        pytest.skip("voice input isn't in this checkout")
    calls = {ast.unparse(node.func) for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
             if isinstance(node, ast.Call)}
    assert {"platforms.rmtree", "platforms.replace"} <= calls  # Defender may hold a fresh file for a moment
    assert not calls & {"shutil.rmtree", "os.replace", "os.rename"}


def test_repo_hygiene():
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git isn't installed")
    inside = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=ROOT, capture_output=True,
                            encoding="utf-8")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        pytest.skip("not a git checkout")
    listing = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    tracked = [name for name in listing.decode("utf-8").split("\0") if name]
    personal = [name for name in tracked
                if PurePosixPath(name).name in {".mcp.json", ".DS_Store", "Thumbs.db", "desktop.ini"}
                or PurePosixPath(name).name.startswith(".env")
                or name.endswith(".log") or name.split("/")[0] in {".venv", ".superpowers", ".pytest_cache", ".claude"}]
    assert not personal, f"personal or generated files are tracked: {personal}"
    home = str(Path.home()).encode("utf-8")
    leaking = []
    for name in tracked:
        try:
            data = (ROOT / name).read_bytes()
        except OSError:  # deleted, and not committed yet
            continue
        if b"\0" not in data and home in data:
            leaking.append(name)
    assert not leaking, f"tracked files name this computer's home folder ({Path.home()}): {leaking}"
    eol = subprocess.run(["git", "check-attr", "eol", "--", "docker/entrypoint.sh"], cwd=ROOT, capture_output=True,
                         encoding="utf-8", check=True).stdout
    assert eol.strip() == "docker/entrypoint.sh: eol: lf"
    assert (ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.12"
    dockerfile = (ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
    assert r"RUN sed -i 's/\r$//' /usr/local/bin/aib-entrypoint /usr/local/bin/aib-cdp-proxy" in dockerfile


def test_the_hand_off_says_where_to_look_on_windows():
    from ai_browser.checks import Check, CheckGate
    from ai_browser.render import render_check

    check = Check("google", "www.google.com")
    windows = CheckGate.handoff(check, "t2", None, system="win32")
    mac = CheckGate.handoff(check, "t2", None, system="darwin")
    assert windows.splitlines()[2] == "The tab is now in front. (if its window didn't come up, look for it in the taskbar)"
    assert mac.splitlines()[2] == "The tab is now in front."
    live = render_check(check, "t2", "http://127.0.0.1:8770/live?token=abc", system="win32")
    assert live.splitlines()[2] == ("The tab is now in front. (if its window didn't come up, look for it in the "
                                    "taskbar) The user can solve it in the live view: http://127.0.0.1:8770/live?token=abc")


def test_no_macos_paths_outside_platforms():
    pattern = re.compile(r'Application Support|/Applications/|"open", "-R"|os\.kill\(\s*[^,()]+,\s*0\s*\)')
    found = [f"{path.relative_to(SRC).as_posix()}:{number}: {line.strip()}"
             for path in sorted(SRC.rglob("*.py")) if path != SRC / "platforms.py"
             for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if pattern.search(line)]
    assert not found, "macOS-only paths, or a liveness probe, outside platforms.py:\n" + "\n".join(found)


WINDOWS_312 = {"implementation_name": "cpython", "implementation_version": "3.12.10", "os_name": "nt",
               "platform_machine": "AMD64", "platform_python_implementation": "CPython", "platform_release": "10",
               "platform_system": "Windows", "platform_version": "10.0.26100", "python_full_version": "3.12.10",
               "python_version": "3.12", "sys_platform": "win32", "extra": ""}


def _windows_wheel(url: str) -> bool:
    name = url.rsplit("/", 1)[-1].split("#", 1)[0]
    if not name.endswith(".whl"):
        return False
    python, abi, platform = name[:-4].split("-")[-3:]
    if platform == "any":
        return True
    return "win_amd64" in platform.split(".") and ("cp312" in python.split(".") or abi in ("abi3", "none"))


def test_voice_extra_has_windows_wheels():
    import tomllib

    from packaging.markers import Marker

    packages = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8")).get("package", [])
    if not any(package["name"] == "faster-whisper" for package in packages):
        pytest.skip("uv.lock has no voice extra (faster-whisper): the user hasn't chosen to install it")
    by_name: dict[str, list] = {}
    for package in packages:
        by_name.setdefault(package["name"], []).append(package)
    root = next(package for package in packages if package["name"] == "ai-browser")

    def applies(dependency) -> bool:  # left out when its marker is false for 64-bit Windows and CPython 3.12
        return "marker" not in dependency or Marker(dependency["marker"]).evaluate(WINDOWS_312)

    def find(dependency):
        found = by_name.get(dependency["name"], [])
        if "version" in dependency:
            found = [package for package in found if package["version"] == dependency["version"]] or found
        return found[0] if found else None

    todo = [dependency for dependency in root.get("optional-dependencies", {}).get("voice", []) if applies(dependency)]
    seen, missing = set(), []
    while todo:
        dependency = todo.pop()
        package = find(dependency)
        if package is None:
            missing.append(f"{dependency['name']} (not in uv.lock)")
            continue
        extras = tuple(dependency.get("extra", ()))
        key = (package["name"], package.get("version"), extras)
        if key in seen:
            continue
        seen.add(key)
        if not any(_windows_wheel(wheel["url"]) for wheel in package.get("wheels", [])):
            missing.append(f"{package['name']} {package.get('version', '')}")
        todo += [dep for dep in package.get("dependencies", []) if applies(dep)]
        for extra in extras:
            todo += [dep for dep in package.get("optional-dependencies", {}).get(extra, []) if applies(dep)]
    assert not missing, "no Windows (win_amd64, cp312) or pure wheel for: " + ", ".join(sorted(set(missing)))


def test_the_ci_workflow_runs_only_by_hand():
    import yaml

    text = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    triggers = workflow[True]  # PyYAML reads the `on:` key as True
    assert list(triggers) == ["workflow_dispatch"]  # never on a push, a pull request or a schedule
    inputs = triggers["workflow_dispatch"]["inputs"]
    assert inputs["os"]["options"] == ["windows", "macos", "both"] and inputs["os"]["default"] == "windows"
    assert inputs["voice"]["type"] == "boolean" and inputs["voice"]["default"] is False
    assert inputs["pytest_args"]["type"] == "string" and inputs["pytest_args"]["default"] == ""  # empty: every test
    assert workflow["permissions"] == {"contents": "read"}
    assert "windows-latest" in text and "macos-latest" in text
    job = workflow["jobs"]["test"]
    assert job["strategy"]["fail-fast"] is False and job["timeout-minutes"] == 75
    runs = [step.get("run", "") for step in job["steps"]]
    assert any(run.startswith("uv sync --locked") for run in runs)
    assert any(run.startswith("uv run --no-sync pytest") and run.endswith(" ${{ inputs.pytest_args }}") for run in runs)
    assert "secrets." not in text and "PYTHONUTF8" not in text  # no secrets; Windows' own encoding is what's tested
    uses = [step["uses"] for step in job["steps"] if "uses" in step]
    assert [use.split("@")[0] for use in uses] == ["actions/checkout", "astral-sh/setup-uv", "actions/upload-artifact"]
    assert all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", use) for use in uses), uses
    assert len(re.findall(r"uses: \S+@[0-9a-f]{40} +# v\d", text)) == 3  # each pin names its release
    upload = job["steps"][-1]
    assert upload["if"] == "always()" and upload["with"]["path"] == "pytest.xml"
    assert upload["with"]["retention-days"] == 7
    checkout = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@"))
    assert checkout.get("with", {}).get("persist-credentials") is False  # the run's token isn't left in .git/config


def test_windows_explorer_and_ci_files_stay_out_of_the_repo():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert {"Thumbs.db", "desktop.ini", "pytest.xml"} <= set(ignored)


def test_the_fake_claude_runs_on_the_base_python_on_windows(monkeypatch):
    import sys

    import conftest

    monkeypatch.setattr(sys, "platform", "win32")  # the venv's python.exe is a launcher there: its child could
    assert conftest.fake_python() == sys._base_executable  # start outside the test's job before the job holds it
    monkeypatch.setattr(sys, "platform", "darwin")
    assert conftest.fake_python() == sys.executable


def test_the_readme_has_the_windows_steps():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for needed in ("## Windows", "winget install --id astral-sh.uv -e", "irm https://claude.ai/install.ps1 | iex",
                   "gh auth login", "git clone https://github.com/nanotechs001/ai-browser.git C:\\dev\\ai-browser",
                   "uv run ai-browser doctor --setup", "-e PYTHONUTF8=1", "%USERPROFILE%\\.ai-browser\\app\\watcher",
                   "brave://inspect/#remote-debugging", "any program on this PC can reach your Brave", "wsl --install",
                   "uv sync --extra voice", "netsh interface ipv4 show excludedportrange protocol=tcp", "AIB_CLAUDE",
                   "AIB_CHROME_BINARY", "$env:USERPROFILE", "Run workflow", ".mcp.json.example"):
        assert needed in text, needed
    assert "This folder has a `.mcp.json`" not in text and "This repo's `.mcp.json`" not in text
