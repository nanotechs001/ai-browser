import shutil
import subprocess

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


@pytest.fixture(autouse=True)
def _never_the_users_chrome(monkeypatch, tmp_path_factory):
    """No test may reach the user's own Chrome: AIB_BROWSER=chrome in their shell, or the default Chrome folder,
    would make their real browser ask "Allow remote debugging?" (tests that need a Chrome launch a throwaway one)."""
    monkeypatch.delenv("AIB_BROWSER", raising=False)
    monkeypatch.setenv("AIB_CHROME_DIR", str(tmp_path_factory.getbasetemp() / "no-chrome-here"))


@pytest.fixture(autouse=True)
def _no_finder_windows(monkeypatch):
    """No test may open a Finder window on the machine running the suite (tests that check it patch it again)."""
    import ai_browser.app.run as run
    import ai_browser.app.server as server

    monkeypatch.setattr(run, "reveal", lambda path: None)
    monkeypatch.setattr(server, "reveal_in_finder", lambda path: None)


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


@pytest.fixture
async def chrome_browser(throwaway_chrome, tmp_path):
    """(Browser in chrome mode, base URL of the host-served test pages, the Chrome's page targets before)."""
    from ai_browser import testpages
    from ai_browser.browser import Browser
    from ai_browser.cdp import CDP
    from ai_browser.chrome import find_ws_url
    from ai_browser.config import Config
    from ai_browser.workfs import WorkDir

    base, _, stop_pages = testpages.serve_host()
    cdp = await CDP.connect(find_ws_url(throwaway_chrome, timeout=20))
    before = {t["targetId"] for t in (await cdp.send("Target.getTargets"))["targetInfos"] if t["type"] == "page"}
    browser = Browser(cdp, WorkDir(tmp_path / "work", "chrome-task"), Config(), mode="chrome")
    await browser.start()
    yield browser, base, before
    await browser.close()
    await cdp.close()
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
    docker_items = [item for item in items if "docker" in item.keywords]
    if not docker_items:
        return
    reason = _docker_unavailable()
    if reason:
        for item in docker_items:
            item.add_marker(pytest.mark.skip(reason=reason))


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    """A fake `claude` executable: (runner, log, script). Write the reply events to `script` as a JSON list."""
    import sys
    from pathlib import Path

    script, log = tmp_path / "fake-claude-script.json", tmp_path / "fake-claude.log"
    script.write_text("[]")
    runner = tmp_path / "claude"
    runner.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{Path(__file__).with_name("fake_claude.py")}" "$@"\n')
    runner.chmod(0o755)
    monkeypatch.setenv("FAKE_CLAUDE_SCRIPT", str(script))
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    return runner, log, script
