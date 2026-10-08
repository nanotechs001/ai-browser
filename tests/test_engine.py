import json
import subprocess
from pathlib import Path

import pytest

from ai_browser import engine as engine_module
from ai_browser import testpages
from ai_browser.engine import Engine, ToolResult
from ai_browser.skills import Catalog, SkillSource
from fake_brave import BraveApp, FakePort, add_agent, until

DOCKER = pytest.mark.docker


def skill_catalog(tmp_path: Path) -> Catalog:
    root = tmp_path / "plugin"
    folder = root / "skills" / "hello"
    (folder / "scripts").mkdir(parents=True)
    (folder / "SKILL.md").write_text("---\nname: hello\ndescription: Says hello from a script\n---\n"
                                     "Run python3 ${CLAUDE_PLUGIN_ROOT}/skills/hello/scripts/hi.py\n", encoding="utf-8")
    (folder / "scripts" / "hi.py").write_text("print('hello from the skill')\n", encoding="utf-8")
    return Catalog([SkillSource("demo", root, "/skills/plugins/demo", "skills/*/SKILL.md")], set())


def test_docker_unavailable_message(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "unix:///nonexistent/docker.sock")
    engine = Engine(home=tmp_path, catalog=Catalog([], set()))
    import asyncio
    result = asyncio.run(engine.open("http://example.com"))
    assert isinstance(result, ToolResult)
    assert result.text.startswith("error:") and "Docker Desktop" in result.text
    assert result.text.splitlines()[-1].startswith("⏱")


async def test_find_skills_without_docker(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_module.Sandboxes, "check", lambda self: None)  # Docker answers (it starts nothing)
    engine = Engine(home=tmp_path, catalog=skill_catalog(tmp_path))
    found = await engine.find_skills("hello script")
    assert "demo:hello [scripts] — Says hello from a script" in found.text
    listing = await engine.find_skills("")
    assert "demo (1): hello" in listing.text
    loaded = await engine.load_skill("demo:hello")
    assert "python3 /skills/plugins/demo/skills/hello/scripts/hi.py" in loaded.text
    missing = await engine.load_skill("nope")
    assert missing.text.startswith("error: no skill 'nope'")


async def test_when_docker_isnt_running_skills_scripts_run_with_the_agents_own_bash(tmp_path, monkeypatch):  # Part 2
    from ai_browser.sandbox import DockerError

    asked = []

    def down(self):
        asked.append(self)
        raise DockerError("Docker isn't running. Start Docker Desktop, then retry.")

    monkeypatch.setattr(engine_module.Sandboxes, "check", down)
    engine = Engine(home=tmp_path, catalog=skill_catalog(tmp_path))
    loaded = await engine.load_skill("demo:hello")
    root = (tmp_path / "plugin").as_posix()
    assert f"python3 {root}/skills/hello/scripts/hi.py" in loaded.text and "/skills/plugins/demo" not in loaded.text
    assert f"{root}/skills/hello" in loaded.text.splitlines()[0]
    assert "Run its scripts with your own commands (Bash), from your task's folder." in loaded.text
    told = await engine.shell("python3 hi.py --fast")
    assert told.text.startswith("Docker isn't running, so there's no shell here: run it with your own Bash: "
                                "python3 hi.py --fast\n")
    refused = await engine.shell("curl -A 'Mozilla/5.0' https://example.com")
    assert refused.text.startswith("⛔")  # a command the shell refuses is never handed to Bash instead
    assert len(asked) == 1 and engine.sandboxes is None and engine.browser is None  # asked once; nothing started


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
    assert len(engine.work.to_host(saved).read_text(encoding="utf-8").strip()) == 20000


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
    assert json.loads((engine.log.dir / "log.jsonl").read_text(encoding="utf-8").splitlines()[-1])["tool"] == "open"


async def test_lone_surrogates_are_cleaned_and_logged(tmp_path):
    engine = Engine(home=tmp_path, catalog=Catalog([], set()))

    async def broken():
        return "half an emoji: \ud83d"

    result = await engine._run("observe", {}, broken)
    result.text.encode("utf-8")
    assert "�" in result.text
    assert (engine.log.dir / "log.jsonl").read_text(encoding="utf-8").count("\n") == 1


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
    lines = (engine.log.dir / "log.jsonl").read_text(encoding="utf-8").splitlines()
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
                              capture_output=True, text=True, encoding="utf-8").stdout.strip()
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
                              capture_output=True, text=True, encoding="utf-8").stdout.strip()
        sessions = engine.work.host_task.parent.parent / "sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        (sessions / "old-task.json").write_text(json.dumps({"pid": int(dead), "targets": [orphan]}), encoding="utf-8")
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


@pytest.mark.parametrize("value, kind", [("", "chrome"), ("own", "chrome"), ("chrome", "chrome"), ("brave", "chrome"),
                                         (" Brave ", "chrome"), ("OWN", "chrome"), ("sandbox", "sandbox")])
def test_aib_browser_picks_the_browser(monkeypatch, tmp_path, value, kind):
    monkeypatch.setenv("AIB_BROWSER", value)
    assert Engine(home=tmp_path, catalog=Catalog([], set()))._default_kind() == kind



@pytest.mark.parametrize("browser, profile, kind", [("", "client-acme", "sandbox"), (" ", " client-acme ", "sandbox"),
                                                    ("", "default", "chrome"), ("", "", "chrome"),
                                                    ("brave", "client-acme", "chrome"),
                                                    ("sandbox", "client-acme", "sandbox")])
def test_a_sandbox_profile_alone_chooses_the_sandbox_up_front(monkeypatch, tmp_path, browser, profile, kind):
    """Review (final), Important 3: AIB_PROFILE names a sandbox profile (README "Logging in to sites"). Set without
    AIB_BROWSER it chooses the Docker sandbox up front, as before Brave became the default: a session set up for a
    client's logins never browses in the user's personal Brave instead."""
    monkeypatch.setenv("AIB_BROWSER", browser)
    monkeypatch.setenv("AIB_PROFILE", profile)
    assert Engine(home=tmp_path, catalog=Catalog([], set()))._default_kind() == kind


def test_the_status_line_says_a_sandbox_profile_isnt_used_in_the_users_browser(monkeypatch, tmp_path):
    from ai_browser.sandbox import SandboxInfo
    from ai_browser.workfs import WorkDir

    monkeypatch.setenv("AIB_BROWSER", "brave")  # chosen explicitly: the profile can't apply there
    monkeypatch.setenv("AIB_PROFILE", "client-acme")
    engine = Engine(home=tmp_path, catalog=Catalog([], set()))
    engine.info = SandboxInfo("aib-chrome", "chrome", "", tmp_path / "w", False, False, chrome=True)
    engine.work = WorkDir(tmp_path / "w", engine.task_id)
    assert ("\nAIB_PROFILE=client-acme is a Docker sandbox profile: not used here (sandbox_start(profile="
            "\"client-acme\") uses it)") in engine._status_text()
    monkeypatch.setenv("AIB_PROFILE", "default")
    assert "AIB_PROFILE" not in engine._status_text()

async def test_an_unknown_aib_browser_is_refused_never_guessed(monkeypatch, tmp_path):
    monkeypatch.setenv("AIB_BROWSER", "firefox")

    async def nothing(*args, **kwargs):
        raise AssertionError("started a browser")

    monkeypatch.setattr(Engine, "_start", nothing)
    monkeypatch.setattr(Engine, "_start_chrome", nothing)
    engine = Engine(home=tmp_path, catalog=Catalog([], set()))
    result = await engine.open("https://example.com")
    assert result.text.startswith("error: AIB_BROWSER must be own, chrome, brave or sandbox")


async def test_sandbox_start_chooses_up_front(monkeypatch, tmp_path):
    monkeypatch.delenv("AIB_BROWSER")
    started = []

    async def sandbox(self, profile, fresh):
        started.append(("sandbox", profile))
        raise RuntimeError("stop here")

    async def own(self, mode="chrome"):
        started.append((mode,))
        raise RuntimeError("stop here")

    monkeypatch.setattr(Engine, "_start", sandbox)
    monkeypatch.setattr(Engine, "_start_chrome", own)
    engine = Engine(home=tmp_path, catalog=Catalog([], set()))
    await engine.sandbox_start()
    await engine.sandbox_start(chrome=True)
    assert started == [("sandbox", "default"), ("chrome",)]


async def test_with_brave_unreachable_open_explains_and_never_starts_the_sandbox(monkeypatch, tmp_path):
    monkeypatch.delenv("AIB_BROWSER")
    folder = tmp_path / "BraveSoftware" / "Brave-Browser"
    folder.mkdir(parents=True)  # Brave is installed; its switch is off
    monkeypatch.setenv("AIB_CHROME_DIR", str(folder))

    async def no_sandbox(self, profile, fresh):
        raise AssertionError("fell back to the Docker sandbox")

    monkeypatch.setattr(Engine, "_start", no_sandbox)
    engine = Engine(home=tmp_path / "home", catalog=Catalog([], set()))
    for _ in range(2):  # each call explains; none quietly switches browsers
        text = (await engine.open("https://example.com")).text
        assert text.startswith("error: Brave doesn't allow remote debugging yet: open brave://inspect/#remote-debugging")
        assert ("Ask the user to turn the switch on, or whether they want the Docker sandbox instead "
                "(sandbox_start()).") in text


async def must_not(*args, **kwargs):
    raise AssertionError("must not be called")


def test_the_readme_opens_with_the_default_browser_not_the_sandbox():
    """Review (final), Important 3: someone deciding whether to install reads first that, by default, Claude works in
    their signed-in Brave; the sandbox's "can't see your files" promise is the sandbox's alone."""
    from ai_browser.config import project_root

    text = (project_root() / "README.md").read_text(encoding="utf-8")
    opening = text.split("\n## ", 1)[0]
    assert "by default your everyday Brave" in opening and "with your logins" in opening
    assert "A sandboxed browser" not in opening and "**Its own browser:**" not in opening
    assert "in the sandbox and list its links" not in text  # the first example no longer assumes the sandbox
    assert "with no `AIB_BROWSER` set, that chooses the sandbox up front" in text  # what AIB_PROFILE does now
    assert "starts one right there, in your tab" not in text.split("With `--browser app`")[0].split("## AI Browser")[1]


async def test_a_session_record_that_cant_be_judged_is_left_alone(tmp_path, monkeypatch):
    import sys

    from ai_browser import platforms
    from ai_browser.sandbox import SandboxInfo

    engine = Engine(home=tmp_path, catalog=Catalog([], set()))
    engine.info = SandboxInfo("aib-chrome", "chrome", "", tmp_path / "work", False, False, chrome=True)
    dead = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True,
                          encoding="utf-8").stdout.strip()
    record = engine._sessions_dir() / "old-task.json"
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"pid": int(dead), "targets": ["T-orphan"]}), encoding="utf-8")
    sent = []

    class Recorder:
        async def send(self, method, params=None):
            sent.append(method)

    def cannot_tell(pid):
        raise OSError("OpenProcess failed")

    engine.cdp = Recorder()
    monkeypatch.setattr(platforms, "pid_alive", cannot_tell)
    await engine._close_orphans()
    assert sent == [] and record.exists()  # its tabs are not closed


def no_direct(*args, **kwargs):
    raise AssertionError("connected directly")  # find_ws_url runs in a thread: a plain function that raises


def brave_folder(tmp_path):
    return tmp_path / "BraveSoftware" / "Brave-Browser"


def ok(result):
    assert not result.text.startswith("error"), result.text
    return result.text


async def test_an_app_agent_always_uses_the_relay(monkeypatch, tmp_path):
    monkeypatch.setattr(engine_module, "find_ws_url", no_direct)  # never a direct connection
    app = await BraveApp(tmp_path / "home", brave_folder(tmp_path)).start()
    app.agent_env(monkeypatch)
    engine = Engine(home=tmp_path / "engine", catalog=Catalog([], set()))
    try:
        ok(await engine.tabs("list"))
        assert app.port.sessions == 1 and app.brave.relay.upstream_opens == 1  # the app's one question
        assert "a1" in [row["id"] for row in app.brave.relay.clients()]
    finally:
        await engine.close()
        await app.stop()
    idle = await BraveApp(tmp_path / "home2", tmp_path / "two" / "BraveSoftware" / "Brave-Browser").start(
        connect=False)  # ready, and a1 isn't in a turn: the relay may not ask for it
    idle.agent_env(monkeypatch)
    engine = Engine(home=tmp_path / "engine2", catalog=Catalog([], set()))
    try:
        text = (await engine.tabs("list")).text
        assert text.startswith("error: AI Browser isn't connected to Brave: ask the user to click Connect in AI Home")
        assert idle.port.sessions == 0
    finally:
        await engine.close()
        await idle.stop()


async def test_a_session_goes_through_a_running_app(monkeypatch, tmp_path):
    monkeypatch.setattr(engine_module, "find_ws_url", no_direct)
    monkeypatch.setattr(Engine, "_close_orphans", must_not)
    app = await BraveApp(tmp_path / "home", brave_folder(tmp_path)).start()
    app.write_link()
    monkeypatch.setenv("AIB_BROWSER", "chrome")
    monkeypatch.delenv("AIB_CHROME_DIR")  # unset: the app's browser
    engine = Engine(home=app.home, catalog=Catalog([], set()))
    try:
        ok(await engine.tabs("list"))
        status = ok(await engine.sandbox_status())
        assert status.startswith("browser: your Brave, through AI Browser's connection · only tabs this session")
        assert f"cc-{engine.task_id}" in app.server.sessions and app.port.sessions == 1
    finally:
        await engine.close()
        await app.stop()


async def test_a_session_never_falls_back_while_the_app_is_up(monkeypatch, tmp_path):
    monkeypatch.setattr(engine_module, "find_ws_url", no_direct)
    app = await BraveApp(tmp_path / "home", brave_folder(tmp_path), answer="refuse").start()  # the user said Deny
    link = app.write_link()
    monkeypatch.setenv("AIB_BROWSER", "chrome")
    monkeypatch.setenv("AIB_CHROME_DIR", str(app.folder))
    engine = Engine(home=app.home, catalog=Catalog([], set()))
    try:
        assert app.brave.state == "refused"
        text = (await engine.tabs("list")).text
        assert text.startswith("error: Brave said no to AI Browser's connection: ask the user to click Try again")
        data = json.loads(link.read_text(encoding="utf-8"))
        link.write_text(json.dumps({**data, "events": "http://127.0.0.1:9/agent-events",
                                    "cdp": "ws://127.0.0.1:9/cdp"}), encoding="utf-8")  # alive, but silent
        text = (await engine.tabs("list")).text
        assert text.startswith("error: AI Browser didn't answer, so this session can't use your Brave through it")
        link.write_text(json.dumps(data), encoding="utf-8")
        await app.brave.relay.disconnect(f"cc-{engine.task_id}")  # AI Home's Disconnect
        text = (await engine.tabs("list")).text
        assert text.startswith("error: The user disconnected this Claude Code session from Brave in AI Home")
        assert app.port.sessions == 1  # the app's own attempt only
    finally:
        await engine.close()
        await app.stop()


async def test_a_session_whose_app_stopped_asks_first(monkeypatch, tmp_path):
    app = await BraveApp(tmp_path / "home", brave_folder(tmp_path)).start()
    link = app.write_link()
    monkeypatch.setenv("AIB_BROWSER", "chrome")
    monkeypatch.setenv("AIB_CHROME_DIR", str(app.folder))
    engine = Engine(home=app.home, catalog=Catalog([], set()))
    try:
        ok(await engine.tabs("list"))
        link.unlink()
        await app.server.stop()  # the app quits: the session's connection closes
        await app.brave.close()
        before = app.port.sessions
        text = (await engine.tabs("list")).text
        assert text.startswith("error: AI Browser stopped, so this session lost its connection to your Brave.")
        assert "call sandbox_start(chrome=true)" in text and app.port.sessions == before  # it connected nowhere
        ok(await engine.sandbox_start(chrome=True))  # the user's choice: directly, Brave asks
        assert app.port.sessions == before + 1
    finally:
        await engine.close()
        await app.port.stop()


async def test_aib_chrome_dir_naming_another_browser_goes_direct(monkeypatch, tmp_path):
    app = await BraveApp(tmp_path / "home", brave_folder(tmp_path)).start()
    app.write_link()
    chrome = FakePort(tmp_path / "Google" / "Chrome")
    await chrome.start()
    monkeypatch.setenv("AIB_BROWSER", "chrome")
    monkeypatch.setenv("AIB_CHROME_DIR", str(chrome.folder))
    engine = Engine(home=app.home, catalog=Catalog([], set()))
    try:
        ok(await engine.tabs("list"))
        status = ok(await engine.sandbox_status())
        assert status.startswith("browser: your Chrome · not through AI Browser: AIB_CHROME_DIR names your Chrome")
        assert chrome.sessions == 1 and app.port.sessions == 1 and f"cc-{engine.task_id}" not in app.server.sessions
    finally:
        await engine.close()
        await chrome.stop()
        await app.stop()


async def test_a_direct_question_stays_open_and_the_next_call_joins_it(monkeypatch, tmp_path):
    """Without the app a session connects by itself, and Brave's question outlives a handshake given up on (see
    app/cdprelay.py). So a call waits CHROME_ALLOW_WAIT for the answer, then says Brave is still asking, and the next
    call joins the same handshake: one question, however long the user takes."""
    monkeypatch.setattr(engine_module, "CHROME_ALLOW_WAIT", 0.5)
    port = FakePort(tmp_path / "BraveSoftware" / "Brave-Browser", answer="silent")
    await port.start()
    monkeypatch.setenv("AIB_BROWSER", "chrome")
    monkeypatch.setenv("AIB_CHROME_DIR", str(port.folder))
    engine = Engine(home=tmp_path / "home", catalog=Catalog([], set()))  # no link.json: the app isn't running
    try:
        for _ in range(2):
            text = (await engine.tabs("list")).text
            assert 'Brave is asking "Allow remote debugging?"' in text and port.sessions == 1, text
        port.answer = "accept"
        port.release.set()  # the user clicks Allow, however late
        assert await until(lambda: port.socket is not None)
        ok(await engine.tabs("list"))  # the connection that question opened
        assert port.sessions == 1
    finally:
        await engine.close()
        await port.stop()


async def test_a_session_that_ends_while_brave_asks_keeps_no_connection_open(monkeypatch, tmp_path):
    """The session's own socket closes when it ends. (Brave's question may stay on screen, and an Allow there
    afterwards is Brave's to clear: see app/cdprelay.py.)"""
    import asyncio

    monkeypatch.setattr(engine_module, "CHROME_ALLOW_WAIT", 0.3)
    port = FakePort(tmp_path / "BraveSoftware" / "Brave-Browser", answer="silent")
    await port.start()
    monkeypatch.setenv("AIB_BROWSER", "chrome")
    monkeypatch.setenv("AIB_CHROME_DIR", str(port.folder))
    engine = Engine(home=tmp_path / "home", catalog=Catalog([], set()))
    try:
        assert "is asking" in (await engine.tabs("list")).text
        await engine.close()  # the session ends while Brave still asks
        port.answer = "accept"
        port.release.set()  # a late Allow
        await asyncio.sleep(0.5)
        assert port.socket is None or port.socket.state.name == "CLOSED"  # no open connection that nobody holds
    finally:
        await port.stop()


async def test_a_connection_allowed_after_the_last_call_closes_with_the_session(monkeypatch, tmp_path):
    monkeypatch.setattr(engine_module, "CHROME_ALLOW_WAIT", 0.3)
    port = FakePort(tmp_path / "BraveSoftware" / "Brave-Browser", answer="silent")
    await port.start()
    monkeypatch.setenv("AIB_BROWSER", "chrome")
    monkeypatch.setenv("AIB_CHROME_DIR", str(port.folder))
    engine = Engine(home=tmp_path / "home", catalog=Catalog([], set()))
    try:
        assert "is asking" in (await engine.tabs("list")).text
        port.answer = "accept"
        port.release.set()  # Allow, after the call stopped waiting: nothing has used the connection yet
        assert await until(lambda: port.socket is not None and port.socket.state.name == "OPEN")
        await engine.close()
        assert await until(lambda: port.socket.state.name == "CLOSED")
    finally:
        await port.stop()


async def test_a_direct_connection_that_dropped_asks_again_instead_of_reusing_it(monkeypatch, tmp_path):
    port = FakePort(tmp_path / "BraveSoftware" / "Brave-Browser")
    await port.start()
    monkeypatch.setenv("AIB_BROWSER", "chrome")
    monkeypatch.setenv("AIB_CHROME_DIR", str(port.folder))
    engine = Engine(home=tmp_path / "home", catalog=Catalog([], set()))
    try:
        ok(await engine.tabs("list"))
        assert port.sessions == 1
        await port.drop()  # the connection goes while the port file stays the same (the switch, off and on)
        assert await until(lambda: engine.cdp is not None and engine.cdp.closed)
        assert ok(await engine.tabs("list")).startswith("(reconnected to your Brave") and port.sessions == 2
    finally:
        await engine.close()
        await port.stop()


async def test_a_session_that_asked_before_the_app_started_holds_no_second_connection(monkeypatch, tmp_path):
    """A session asked Brave by itself, then the app started and asked too, and the user allowed both. The session's
    next call goes through the app, and the connection its own question opened is closed rather than held unused:
    Brave would count two, and its bar would come back whenever one of them opened or closed."""
    monkeypatch.setattr(engine_module, "CHROME_ALLOW_WAIT", 0.3)
    app = await BraveApp(tmp_path / "home", brave_folder(tmp_path), answer="silent").start(connect=False)
    monkeypatch.setenv("AIB_BROWSER", "chrome")
    monkeypatch.setenv("AIB_CHROME_DIR", str(app.folder))
    engine = Engine(home=app.home, catalog=Catalog([], set()))  # no link.json yet: it connects by itself
    try:
        assert "is asking" in (await engine.tabs("list")).text
        app.server.connect_brave("start")  # the app starts, and asks too
        assert await until(lambda: app.brave.state == "asking")
        app.write_link()
        app.port.answer = "accept"
        app.port.release.set()  # the user clicks Allow on both
        assert await until(lambda: app.brave.state == "connected")
        assert await until(lambda: sum(c.state.name == "OPEN" for c in app.port.server.connections) == 2)
        ok(await engine.tabs("list"))  # through the app now
        assert await until(lambda: sum(c.state.name == "OPEN" for c in app.port.server.connections) == 1)
    finally:
        await engine.close()
        await app.stop()


async def test_take_back_reaches_the_engine_through_the_relay_at_once(monkeypatch, tmp_path):
    import ai_browser.agentlink as agentlink

    monkeypatch.setattr(agentlink, "HANDED_TTL", 60)  # the status answer still says "handed" after Take back
    app = await BraveApp(tmp_path / "home", brave_folder(tmp_path),
                         pages=[{"target": "U1", "url": "https://shop.example/", "title": "Shop"}]).start()
    add_agent(app.agents, "a1", adopted=["U1"])
    app.agent_env(monkeypatch)
    engine = Engine(home=tmp_path / "engine", catalog=Catalog([], set()))
    try:
        assert "h1" in ok(await engine.tabs("list"))
        await engine.tabs("switch", "h1")  # taken on (the fake can't draw the page the switch then reads)
        assert engine.browser.current is not None and engine.browser.current.handed
        had = app.agents.take_back("U1")
        await app.brave.relay.cut(had, "U1")  # what the server's take_back does
        assert await until(lambda: engine.browser.current.detached)  # the browser's detach note reached the engine
        assert ok(await engine.tabs("list")).startswith("(the user took back tab t1)")
        assert app.port.page("U1") is not None  # let go of, never closed
    finally:
        await engine.close()
        await app.stop()


def test_the_apps_own_pages_never_open_in_an_agents_browser():
    from ai_browser.browser import url_problem

    app = "http://127.0.0.1:8792"
    for mode in ("chrome", "sandbox"):
        for url in ("http://127.0.0.1:8792/home", "http://127.0.0.1:8792/setup#switch", "HTTP://127.0.0.1:8792/x"):
            assert url_problem(url, mode, app_origin=app) == "AI Browser's own pages open only in its window", url
    assert url_problem("http://127.0.0.1:8793/home", "chrome", app_origin=app) is None  # another port
    assert url_problem("http://127.0.0.1:8792/home", "chrome") is None  # no app running
    assert url_problem("chrome-extension://abc/options.html", "chrome")  # extension pages: never, as before


async def test_the_retired_ai_browser_mode_is_said_plainly(monkeypatch, tmp_path):
    from ai_browser.engine import RETIRED_BROWSER

    monkeypatch.setenv("AIB_BROWSER", "app")

    async def nothing(*args, **kwargs):
        raise AssertionError("started a browser")

    monkeypatch.setattr(Engine, "_start", nothing)
    monkeypatch.setattr(Engine, "_start_chrome", nothing)
    result = await Engine(home=tmp_path, catalog=Catalog([], set())).open("https://example.com")
    assert result.text.startswith(f"error: {RETIRED_BROWSER}")  # the engine adds its timing line
    assert RETIRED_BROWSER == ("AIB_BROWSER=app is retired: AI Browser's own Chrome is gone. Use own (your browser) "
                               "or sandbox.")


def test_the_engine_needs_no_development_packages():  # moved from test_appmode.py
    import subprocess
    import sys

    code = "import sys; sys.modules['httpx'] = None; import ai_browser.engine, ai_browser.server"  # httpx is dev-only
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60, encoding="utf-8")
    assert result.returncode == 0, result.stderr[-500:]
