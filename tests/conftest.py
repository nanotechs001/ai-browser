import contextlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest


def _docker_unavailable() -> str | None:
    """Return why Docker tests cannot run, or None when Docker and the image are ready."""
    from ai_browser.config import IMAGE

    if not shutil.which("docker"):
        return "docker CLI not found"
    try:
        result = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"docker not reachable: {exc}"
    if result.returncode != 0:
        return "sandbox image not built (run: uv run ai-browser build)"
    return None


POSIX_ONLY = "needs macOS or Linux (file descriptors 3 and 4, or the DevTools pipe)"
WINDOWS_ONLY = "Windows behaviour (junctions, msvcrt, Win32 APIs)"
PIPE_FIXTURES = {"stack", "watcher", "app_browser", "app_engine"}  # they launch AI Browser over the DevTools pipe


def platform_skip(item, windows: bool) -> str | None:
    """Why this test can't run on this OS, or None. On Windows: a posix_only test, or one that uses a fixture that
    installs the extension over the DevTools pipe (item.fixturenames holds every fixture it needs, however deep)."""
    if windows and ("posix_only" in item.keywords or set(getattr(item, "fixturenames", ())) & PIPE_FIXTURES):
        return POSIX_ONLY
    if not windows and "windows_only" in item.keywords:
        return WINDOWS_ONLY
    return None


def symlink_or_skip(target, link) -> None:
    """os.symlink, or a skip with the reason where this system can't make links (Windows without Developer Mode)."""
    try:
        os.symlink(target, link, target_is_directory=Path(target).is_dir())
    except OSError as exc:
        pytest.skip(f"this system can't make symbolic links: {exc}")


def file_mode(path) -> int | None:
    """A file's permission bits, or None on Windows: there chmod only toggles read-only, and the token files keep
    Windows' per-user folder permissions instead (the spec's Safety section)."""
    return None if os.name == "nt" else Path(path).stat().st_mode & 0o777


@pytest.fixture(autouse=True)
def _never_the_users_browsers(monkeypatch, tmp_path_factory):
    """No test may reach the user's own Brave or Chrome. With AIB_BROWSER unset the engine uses the user's browser,
    which would ask "Allow remote debugging?", so every test runs with the sandbox and the app with AI Browser. Tests
    of the new defaults change these with monkeypatch, and tests that need a browser launch a throwaway one.
    Detection (`browsers.installed()`, `os_default()`) sees no app folder, no registry and no LaunchServices file of
    this computer."""
    monkeypatch.setenv("AIB_BROWSER", "sandbox")
    monkeypatch.setenv("AIB_APP_BROWSER", "app")
    monkeypatch.setenv("AIB_CHROME_DIR", str(tmp_path_factory.getbasetemp() / "no-chrome-here"))
    from ai_browser import browsers, platforms

    nothing = tmp_path_factory.getbasetemp() / "no-apps-here"
    nothing.mkdir(exist_ok=True)
    fakes = {"app_folders": lambda system=None, env=None: [nothing],
             "windows_browser_commands": lambda: [],
             "windows_https_progid": lambda: None,
             "launch_services_file": lambda: nothing / "no-launch-services.plist"}
    for module in (platforms, browsers):  # browsers.py may hold its own reference to one of them
        for name, fake in fakes.items():
            if hasattr(module, name):
                monkeypatch.setattr(module, name, fake)


@pytest.fixture(autouse=True)
def _no_finder_windows(monkeypatch):
    """No test may open a file manager window on the machine running the suite (tests that check it patch it again)."""
    import ai_browser.app.run as run
    import ai_browser.app.server as server

    monkeypatch.setattr(run, "reveal", lambda path: True)
    monkeypatch.setattr(server, "reveal_folder", lambda path: True)


@pytest.fixture
def throwaway_chrome(tmp_path):
    """A separate headless Chrome with its own temporary profile, standing in for the user's own browser."""
    from ai_browser.chrome import find_ws_url, launch

    folder = tmp_path / "chrome-profile"
    process = launch(folder, headless=True)
    find_ws_url(folder, timeout=20)  # wait until it is up
    yield folder
    process.terminate()
    process.wait(timeout=15)


RELAYED_MODULES = {"test_chrome", "test_checks_browser", "test_isolation"}  # their own-mode tests run both ways


def pytest_generate_tests(metafunc):
    """The own-mode browser tests also run through the app's relay (the cdp-relay spec, Testing): `route` is "direct"
    or "relay" for chrome_browser and own_browser, except in tests marked direct_only (they test the Browser alone,
    over one shared connection)."""
    if "route" in metafunc.fixturenames and metafunc.module.__name__ in RELAYED_MODULES \
            and metafunc.definition.get_closest_marker("direct_only") is None:
        metafunc.parametrize("route", ["direct", "relay"], indirect=True)


@pytest.fixture
def route(request):
    return getattr(request, "param", "direct")


@contextlib.asynccontextmanager
async def browser_connection(folder, route, home):
    """The Browser's CDP connection to a throwaway Chrome: direct, or through an app's relay (an AppServer in brave
    mode with a BraveLink on that Chrome, and agent a1's token), as an app agent connects."""
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.bravelink import BraveLink
    from ai_browser.app.server import AppServer
    from ai_browser.cdp import CDP
    from ai_browser.chrome import find_ws_url

    if route == "direct":
        cdp = await CDP.connect(find_ws_url(folder, timeout=20))
        try:
            yield cdp
        finally:
            await cdp.close()
        return
    server = AppServer(home, AgentManager(home))
    url = await server.start()
    brave = BraveLink(folder, tokens=server.tokens)
    server.attach_brave(brave)
    await brave.start()
    await brave.connect()
    cdp = await CDP.connect(url.replace("http://", "ws://", 1) + "/cdp",
                            headers={"X-AIB-Agent-Token": server.token_for("a1")})
    try:
        yield cdp
    finally:
        await cdp.close()
        await server.stop()
        await brave.close()


@pytest.fixture
async def chrome_browser(throwaway_chrome, tmp_path, route):
    """(Browser in chrome mode, base URL of the host-served test pages, the Chrome's page targets before). The
    Browser's connection is direct, or through the app's relay (`route`)."""
    from ai_browser import testpages
    from ai_browser.browser import Browser
    from ai_browser.cdp import CDP
    from ai_browser.chrome import find_ws_url
    from ai_browser.config import Config
    from ai_browser.workfs import WorkDir

    base, _, stop_pages = testpages.serve_host()
    own = await CDP.connect(find_ws_url(throwaway_chrome, timeout=20))
    before = {t["targetId"] for t in (await own.send("Target.getTargets"))["targetInfos"] if t["type"] == "page"}
    await own.close()
    async with browser_connection(throwaway_chrome, route, tmp_path / "relay-home") as cdp:
        browser = Browser(cdp, WorkDir(tmp_path / "work", "chrome-task"), Config(), mode="chrome")
        await browser.start()
        yield browser, base, before
        await browser.close()
    stop_pages()


@pytest.fixture(scope="session")
def sandbox(tmp_path_factory):
    """One running sandbox shared by the Docker tests: (Sandboxes, SandboxInfo)."""
    from ai_browser.sandbox import Sandboxes

    boxes = Sandboxes(tmp_path_factory.mktemp("aib-home"))
    info = boxes.start(fresh=True)  # throwaway profile: no cache or cookies carried between runs
    yield boxes, info
    boxes.stop(info.name)


def pytest_collection_modifyitems(config, items):
    windows = os.name == "nt"
    for item in items:
        reason = platform_skip(item, windows)
        if reason:
            item.add_marker(pytest.mark.skip(reason=reason))
    docker_items = [item for item in items if "docker" in item.keywords]
    if not docker_items:
        return
    reason = _docker_unavailable()
    if reason:
        for item in docker_items:
            item.add_marker(pytest.mark.skip(reason=reason))


def fake_python() -> str:
    """The Python the fake claude runs on. On Windows a venv's python.exe is a launcher that starts the real one a
    moment later, which could slip out of the Job the bridge puts it in; the fake needs only the standard library."""
    import sys

    return sys._base_executable if sys.platform == "win32" else sys.executable


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    """The fake `claude`: (runner, log, script). runner is an argv prefix, [python, fake_claude.py], which every
    `claude` parameter accepts, the same on every OS. Write the reply events to `script` as a JSON list."""
    script, log = tmp_path / "fake-claude-script.json", tmp_path / "fake-claude.log"
    script.write_text("[]", encoding="utf-8")
    runner = [fake_python(), str(Path(__file__).with_name("fake_claude.py"))]
    monkeypatch.setenv("FAKE_CLAUDE_SCRIPT", str(script))
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    return runner, log, script


@pytest.fixture
async def chrome_engine(throwaway_chrome, tmp_path, monkeypatch):
    """(Engine on the throwaway Chrome once sandbox_start(chrome=true) is called, the test pages' base URL, the
    Chrome's profile folder)."""
    from ai_browser import testpages
    from ai_browser.engine import Engine
    from ai_browser.skills import Catalog

    monkeypatch.setenv("AIB_CHROME_DIR", str(throwaway_chrome))
    base, _, stop_pages = testpages.serve_host()
    # never the real "default" profile: a slip back to the sandbox must not leave containers tied to this temp home
    engine = Engine(home=tmp_path / "home", default_profile="pytest-chrome", catalog=Catalog([], set()))
    yield engine, base, throwaway_chrome
    await engine.close()
    stop_pages()
    if engine.sandboxes is not None:  # the shell container this temp home started (Docker tests)
        engine.sandboxes.stop(engine.sandboxes.chrome_shell())
