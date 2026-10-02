"""Website QA inside the Docker sandbox: the planted site served from the sandbox itself. Also QA in its own Docker
sandbox when the session browses in the user's browser (a throwaway Chrome here), and a bot check QA finds there, held
in that sandbox (where="qa")."""

import asyncio
import re
import subprocess

import pytest

from ai_browser import testpages
from ai_browser.cdp import CDP
from ai_browser.chrome import chrome_binary, find_ws_url
from ai_browser.engine import Engine
from ai_browser.skills import Catalog

pytestmark = pytest.mark.docker
needs_chrome = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


async def test_qa_runs_in_the_sandbox(tmp_path):
    engine = Engine(home=tmp_path, catalog=Catalog([], set()))
    try:
        assert "ready" in (await engine.sandbox_start(fresh=True)).text
        base, _ = testpages.serve(engine.sandboxes, engine.info)
        result = await engine.qa(base + "qa/index.html")
        lines = result.text.splitlines()
        assert lines[0].startswith("qa http://localhost:8000/qa/index.html — 6 pages"), result.text
        assert lines[1].startswith("issues: 3 high · 3 medium · 1 low · 1 link couldn't be checked"), result.text
    finally:
        await engine.close()


@pytest.fixture
async def qa_engine(tmp_path, monkeypatch, throwaway_chrome):
    """(engine in own mode, base URL of the pages served in QA's sandbox, Sandboxes, its info, the "Brave" folder)."""
    from ai_browser import engine as engine_module
    from ai_browser.sandbox import Sandboxes

    monkeypatch.setattr(engine_module, "QA_PROFILE", "pytest-qa")  # never the user's own `qa` sandbox
    monkeypatch.delenv("AIB_BROWSER")  # the user's own browser by default
    monkeypatch.setenv("AIB_CHROME_DIR", str(throwaway_chrome))
    home = tmp_path / "home"
    boxes = Sandboxes(home)
    info = await asyncio.to_thread(boxes.start, "pytest-qa")
    base, _ = await asyncio.to_thread(testpages.serve, boxes, info)
    engine = Engine(home=home, catalog=Catalog([], set()))
    yield engine, base, boxes, info, throwaway_chrome
    await engine.close()
    subprocess.run(["docker", "rm", "-f", "aib-pytest-qa", "aib-pytest-qa-sh"], capture_output=True)
    subprocess.run(["docker", "volume", "rm", "aib-profile-pytest-qa"], capture_output=True)


async def pages(folder) -> set[str]:
    cdp = await CDP.connect(find_ws_url(folder, timeout=20))
    try:
        return {info["targetId"] for info in (await cdp.send("Target.getTargets"))["targetInfos"]
                if info["type"] == "page"}
    finally:
        await cdp.close()


@needs_chrome
async def test_qa_in_own_mode_crawls_in_the_sandbox(qa_engine):
    engine, base, _, _, folder = qa_engine
    before = await pages(folder)
    result = (await engine.qa(base + "qa/index.html", 3)).text
    assert result.startswith("checked in the Docker sandbox") and await pages(folder) == before
    assert list(engine._qa_work().host_task.rglob("report.html"))  # in the session's own work folder


@needs_chrome
async def test_a_bot_check_in_qas_sandbox_is_held_there_until_solved(qa_engine):
    engine, base, boxes, info, _ = qa_engine
    result = (await engine.qa(base + "qa2/check.html", 3)).text
    held = engine.gate.held
    assert held is not None and held.where == "qa" and re.fullmatch(r"q\d+", held.tab_key)
    assert f"tab {held.tab_key}" in result and engine.live.url in result  # that sandbox's live-view link
    assert engine.live.browser is engine._qa_browser
    assert held.tab_key in (await engine.tabs("list")).text
    assert "⛔ bot check" in (await engine.observe()).text  # observe reads it there: still a check
    assert (await engine.open(base + "form.html")).text.startswith("⏸ waiting for the user")
    cdp = await CDP.connect(await asyncio.to_thread(boxes.ws_url, info))  # the user solves it (the test moves on)
    try:
        session = (await cdp.send("Target.attachToTarget", {"targetId": held.target, "flatten": True}))["sessionId"]
        await cdp.send("Page.navigate", {"url": base + "checks/counter.html"}, session_id=session)
        await asyncio.sleep(1)
    finally:
        await cdp.close()
    solved = (await engine.observe()).text
    assert solved.startswith(f"(the bot check in tab {held.tab_key} is gone: carrying on)")
    assert engine.gate.held is None and engine._qa_browser is None and engine.live.browser is None


@needs_chrome
async def test_skip_it_closes_the_held_tab_in_qas_sandbox(qa_engine):
    engine, base, _, _, _ = qa_engine
    await engine.qa(base + "qa2/check.html", 3)
    key = engine.gate.held.tab_key
    closed = (await engine.tabs("close", key)).text  # the user said "skip it"
    assert "off-limits" in closed and engine.gate.held is None and engine._qa_browser is None
