import contextlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REAL_HOME = Path.home()  # the user's own home, read when the suite starts, before any test sets HOME


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


def platform_skip(item, windows: bool) -> str | None:
    """Why this test can't run on this OS, or None: a posix_only test on Windows, a windows_only one elsewhere."""
    if windows and "posix_only" in item.keywords:
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


@pytest.fixture
def user_home(tmp_path, monkeypatch):
    """A throwaway home folder for agent powers (app/powers.py's user_home): its Library and .claude are refused there,
    and no test names the user's own. HOME itself stays: a test that needs ~ to mean this folder sets HOME too."""
    from ai_browser.app import powers

    folder = tmp_path / "user-home"
    folder.mkdir()
    monkeypatch.setattr(powers, "user_home", lambda: folder)
    return folder


def file_mode(path) -> int | None:
    """A file's permission bits, or None on Windows: there chmod only toggles read-only, and the token files keep
    Windows' per-user folder permissions instead (the spec's Safety section)."""
    return None if os.name == "nt" else Path(path).stat().st_mode & 0o777


@pytest.fixture(autouse=True)
def _never_the_users_browsers(monkeypatch, tmp_path_factory):
    """No test may reach the user's own Brave or Chrome. With AIB_BROWSER unset the engine uses the user's browser,
    which would ask "Allow remote debugging?", so every test runs with the sandbox, and `ai-browser app` with BraveLink
    off (no browser folder). Tests of the new defaults change these with monkeypatch, and tests that need a browser
    launch a throwaway one.
    Detection (`browsers.installed()`, `os_default()`) sees no app folder, no registry and no LaunchServices file of
    this computer."""
    monkeypatch.setenv("AIB_BROWSER", "sandbox")
    monkeypatch.delenv("AIB_APP_BROWSER", raising=False)  # retired: a shell that still sets it can't change a test
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
def _no_real_window(monkeypatch):
    """No test opens AI Browser's real window: run_app's tests pass a launcher (tests/fake_window.py)."""
    import ai_browser.app.run as run
    from ai_browser.app.window import WindowError

    def launcher(home):
        def refuse(setting):
            raise WindowError("tests never open AI Browser's real window: pass launcher=")
        return refuse

    monkeypatch.setattr(run, "default_launcher", launcher)


@pytest.fixture(autouse=True)
def _no_real_desktop(monkeypatch):
    """No test starts AI Browser's own app: run_app's tests pass desktop= (tests/fake_desktop.py)."""
    import ai_browser.app.run as run

    monkeypatch.setattr(run, "default_desktop", lambda home, shortcut=None: None)


def _no_terminal_windows(monkeypatch):
    """No test may open a terminal window on the machine running the suite (tests that check it patch it again)."""
    import ai_browser.app.server as server

    monkeypatch.setattr(server, "open_terminal", lambda *args, **kwargs: True)  # never a real terminal window


@pytest.fixture(autouse=True)
def _never_the_users_claude_folder(monkeypatch, tmp_path_factory):
    """No test reads or writes the user's own Claude Code folder (~/.claude). The Default account's folder,
    CLAUDE_CONFIG_DIR, is a throwaway in every test. It is signed in for the fake claude, as the user's own login
    normally is (fake_accounts.sign_out undoes that), and the fake keeps its conversations there."""
    from fake_accounts import sign_in

    folder = tmp_path_factory.mktemp("claude-default")
    sign_in(folder)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(folder))


@pytest.fixture(autouse=True)
def _never_the_users_skills(monkeypatch, tmp_path_factory):
    """No test's skill catalog reads the user's own ~/.claude or Claude desktop folder (Mission Control's pages ask for
    the skills on every snapshot): while HOME is still the user's, the catalog's folders are a throwaway that holds
    nothing. A test that sets HOME (USERPROFILE on Windows) to its own folder steers the catalog there, as before."""
    from ai_browser import skills

    found, spare = skills.user_folders, tmp_path_factory.getbasetemp() / "no-user-skills"

    def folders():
        return found() if Path.home() != REAL_HOME else (spare / ".claude", spare / "Claude")

    monkeypatch.setattr(skills, "user_folders", folders)


USERS_APP_PORT = 8792  # APP_PORTS' first: the port the user's own `ai-browser app` remembers and comes back on


@pytest.fixture(autouse=True)
def _never_the_users_app_port(monkeypatch):
    """No test's app server takes 8792, whether or not the user's own AI Browser runs there now: it may start while
    the suite runs, and would then have to take another port (and ask for the microphone again). A test's server
    takes the next free port instead, as it does while that app runs."""
    import ai_browser.app.server as server

    bind = server._bind
    monkeypatch.setattr(server, "_bind", lambda host, port: None if port == USERS_APP_PORT else bind(host, port))


@pytest.fixture(autouse=True)
def _no_setup_outside_the_test(monkeypatch, tmp_path_factory):
    """No test reads or writes the user's own ~/.ai-browser (AIB_HOME is a throwaway unless a test sets its own), no
    test downloads Electron, and no doctor --setup waits for a typed answer or binds 8792 to see if it is free. The
    setup's tests pass a fake release and say whether someone can answer."""
    import ai_browser.cli as cli
    from ai_browser import live
    from ai_browser.desktop import setup

    def refuse(url):
        raise AssertionError(f"tests never download Electron ({url})")

    bind = live._bind
    monkeypatch.setenv("AIB_HOME", str(tmp_path_factory.mktemp("aib-home")))
    monkeypatch.setattr(setup, "FETCH", refuse)
    monkeypatch.setattr(cli, "_interactive", lambda: False)
    monkeypatch.setattr(live, "_bind", lambda host, port: None if port == USERS_APP_PORT else bind(host, port))


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


async def let_its_folder_go(bridge) -> None:
    """Before a test renames or deletes the folder an agent works in: on Windows, a folder a running program works in
    can't be renamed or deleted (Windows refuses: the file is in use), so its Claude Code process ends first, as it
    does when Claude Code exits between turns. Elsewhere the folder goes while Claude Code runs, as it may there."""
    if os.name == "nt":
        await bridge.close()


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
