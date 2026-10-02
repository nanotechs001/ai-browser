import json
import subprocess
from pathlib import Path

import pytest

from ai_browser import testpages
from ai_browser.engine import Engine, ToolResult
from ai_browser.skills import Catalog, SkillSource

DOCKER = pytest.mark.docker


def skill_catalog(tmp_path: Path) -> Catalog:
    root = tmp_path / "plugin"
    folder = root / "skills" / "hello"
    (folder / "scripts").mkdir(parents=True)
    (folder / "SKILL.md").write_text("---\nname: hello\ndescription: Says hello from a script\n---\n"
                                     "Run python3 ${CLAUDE_PLUGIN_ROOT}/skills/hello/scripts/hi.py\n")
    (folder / "scripts" / "hi.py").write_text("print('hello from the skill')\n")
    return Catalog([SkillSource("demo", root, "/skills/plugins/demo", "skills/*/SKILL.md")], set())


def test_docker_unavailable_message(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "unix:///nonexistent/docker.sock")
    engine = Engine(home=tmp_path, catalog=Catalog([], set()))
    import asyncio
    result = asyncio.run(engine.open("http://example.com"))
    assert isinstance(result, ToolResult)
    assert result.text.startswith("error:") and "Docker Desktop" in result.text
    assert result.text.splitlines()[-1].startswith("⏱")


async def test_find_skills_without_docker(tmp_path):
    engine = Engine(home=tmp_path, catalog=skill_catalog(tmp_path))
    found = await engine.find_skills("hello script")
    assert "demo:hello [scripts] — Says hello from a script" in found.text
    listing = await engine.find_skills("")
    assert "demo (1): hello" in listing.text
    loaded = await engine.load_skill("demo:hello")
    assert "python3 /skills/plugins/demo/skills/hello/scripts/hi.py" in loaded.text
    missing = await engine.load_skill("nope")
    assert missing.text.startswith("error: no skill 'nope'")


async def test_bad_steps_are_reported_not_raised(tmp_path):
    engine = Engine(home=tmp_path, catalog=Catalog([], set()))
    result = await engine.act(["fly e1"])
    assert result.text.startswith("error: step 1:")


@pytest.fixture
async def engine(tmp_path):
    engine = Engine(home=tmp_path, catalog=skill_catalog(tmp_path))
    started = await engine.sandbox_start(fresh=True)
    assert "ready" in started.text
    base, _ = testpages.serve(engine.sandboxes, engine.info)
    yield engine, base
    await engine.close()


@DOCKER
async def test_open_observe_act_and_timing(engine):
    engine, base = engine
    opened = await engine.open(base + "form.html")
    assert 'page  "Form test"' in opened.text
    assert opened.text.splitlines()[-1].startswith("⏱")
    increment = next(line.split()[0] for line in opened.text.splitlines() if '"Increment"' in line)
    acted = await engine.act([f"click {increment}"])
    assert acted.text.startswith("✓ click")


@DOCKER
async def test_screenshot_returns_images_and_saves_them(engine):
    engine, base = engine
    await engine.open(base + "report.html")
    result = await engine.screenshot(size="all")
    assert len(result.images) == 3
    saved = [line for line in result.text.splitlines() if "saved" in line]
    assert len(saved) == 3
    assert all(Path(line.rsplit(" ", 1)[-1]).exists() for line in saved)


@DOCKER
async def test_shell_runs_in_the_task_folder(engine):
    engine, _ = engine
    result = await engine.shell("pwd && echo hi")
    assert result.text.splitlines()[:2] == [engine.work.sandbox_task, "hi"]
    assert "[exit 0]" in result.text


@DOCKER
async def test_shell_reports_exit_code_and_timeout(engine):
    engine, _ = engine
    assert "[exit 3]" in (await engine.shell("exit 3")).text
    assert "[timed out after 1s]" in (await engine.shell("sleep 10", timeout=1)).text


@DOCKER
async def test_long_shell_output_is_truncated_and_saved(engine):
    engine, _ = engine
    result = await engine.shell("python3 -c \"print('x' * 20000)\"")
    assert len(result.text) < 10_400
    saved = result.text.split("full output saved to ")[1].split("]")[0]
    assert len(engine.work.to_host(saved).read_text().strip()) == 20000


@DOCKER
async def test_files_roundtrip_and_escape(engine):
    engine, _ = engine
    wrote = await engine.write_file("notes/a.txt", "hello")
    assert f"{engine.work.sandbox_task}/notes/a.txt" in wrote.text
    assert (await engine.read_file("notes/a.txt")).text.startswith("hello")
    assert "hello" in (await engine.shell("cat notes/a.txt")).text
    assert (await engine.read_file("/etc/passwd")).text.startswith("error:")
    assert (await engine.read_file("missing.txt")).text.startswith("error: missing.txt: no such file")


@DOCKER
async def test_skill_script_runs_inside_the_sandbox(engine):
    engine, _ = engine
    loaded = await engine.load_skill("demo:hello")
    command = next(line for line in loaded.text.splitlines() if line.startswith("Run "))[4:]
    assert "hello from the skill" in (await engine.shell(command)).text


@DOCKER
async def test_tool_text_is_always_valid_utf8(engine):
    engine, base = engine
    result = await engine.open(base + "unicode.html")
    assert not result.text.startswith("error")
    result.text.encode("utf-8")
    assert json.loads((engine.log.dir / "log.jsonl").read_text().splitlines()[-1])["tool"] == "open"


async def test_lone_surrogates_are_cleaned_and_logged(tmp_path):
    engine = Engine(home=tmp_path, catalog=Catalog([], set()))

    async def broken():
        return "half an emoji: \ud83d"

    result = await engine._run("observe", {}, broken)
    result.text.encode("utf-8")
    assert "�" in result.text
    assert (engine.log.dir / "log.jsonl").read_text().count("\n") == 1


@DOCKER
async def test_a_failed_start_is_retried_not_stuck(tmp_path, monkeypatch):
    from ai_browser.browser import Browser

    engine = Engine(home=tmp_path, catalog=Catalog([], set()))
    original, calls = Browser.start, {"n": 0}

    async def flaky(self):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return await original(self)

    monkeypatch.setattr(Browser, "start", flaky)
    try:
        assert (await engine.sandbox_start(fresh=True)).text.startswith("error:")
        assert "ready" in (await engine.sandbox_start(fresh=True)).text
        assert not (await engine.observe()).text.startswith("error")
    finally:
        await engine.close()


@DOCKER
async def test_every_call_is_logged(engine):
    engine, base = engine
    await engine.open(base + "form.html")
    await engine.observe()
    lines = (engine.log.dir / "log.jsonl").read_text().splitlines()
    tools = [json.loads(line)["tool"] for line in lines]
    assert tools[-2:] == ["open", "observe"]


@DOCKER
async def test_restarts_after_the_sandbox_dies(engine):
    engine, base = engine
    await engine.open(base + "form.html")
    subprocess.run(["docker", "kill", engine.info.name], capture_output=True)
    for _ in range(50):  # the websocket notices the container is gone
        if engine.cdp.closed:
            break
        import asyncio
        await asyncio.sleep(0.1)
    old_shell = engine.info.shell
    result = await engine.observe()
    assert result.text.startswith("(sandbox restarted")
    assert not result.text.startswith("error")
    leftover = subprocess.run(["docker", "ps", "-a", "--filter", f"name=^{old_shell}$", "--format", "{{.Names}}"],
                              capture_output=True, text=True).stdout.strip()
    assert leftover == "" or old_shell == engine.info.shell  # a throwaway pair is replaced whole


@DOCKER
async def test_tabs_left_by_a_dead_session_are_closed(tmp_path):
    import sys

    from ai_browser.cdp import CDP

    engine = Engine(home=tmp_path, default_profile="pytest-orphans", catalog=Catalog([], set()))
    try:
        await engine.sandbox_start(profile="pytest-orphans")
        orphan = (await engine.cdp.send("Target.createTarget", {"url": "about:blank#orphan"}))["targetId"]
        dead = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                              capture_output=True, text=True).stdout.strip()
        sessions = engine.work.host_task.parent.parent / "sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        (sessions / "old-task.json").write_text(json.dumps({"pid": int(dead), "targets": [orphan]}))
        await engine.close()

        again = Engine(home=tmp_path, default_profile="pytest-orphans", catalog=Catalog([], set()))
        await again.sandbox_start(profile="pytest-orphans")
        targets = {t["targetId"] for t in (await again.cdp.send("Target.getTargets"))["targetInfos"]}
        assert orphan not in targets
        assert not (sessions / "old-task.json").exists()
        await again.sandbox_stop()
    finally:
        subprocess.run(["docker", "rm", "-f", "aib-pytest-orphans"], capture_output=True)
        subprocess.run(["docker", "volume", "rm", "aib-profile-pytest-orphans"], capture_output=True)


@DOCKER
async def test_two_engines_share_container(tmp_path):
    first = Engine(home=tmp_path, default_profile="pytest-two", catalog=Catalog([], set()))
    second = Engine(home=tmp_path, default_profile="pytest-two", catalog=Catalog([], set()))
    try:
        await first.sandbox_start(profile="pytest-two")
        await second.sandbox_start(profile="pytest-two")
        assert first.info.name == second.info.name
        base, _ = testpages.serve(first.sandboxes, first.info)
        await first.open(base + "form.html")
        await second.open(base + "privacy.html")
        assert '"Form test"' in (await first.observe()).text
        assert '"Privacy"' in (await second.observe()).text
        await first.close()
        assert '"Privacy"' in (await second.observe()).text
    finally:
        await second.sandbox_stop()
        subprocess.run(["docker", "volume", "rm", "aib-profile-pytest-two"], capture_output=True)
