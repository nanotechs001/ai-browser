"""The bridge with agent powers (app/bridge.py): Claude Code's own tools, the task's folder as its cwd, trust deciding
--setting-sources, every request decided by the app (app/powers.py), and the stream's badges, to-do list and
sub-agents. On the fake claude, in throwaway folders and a throwaway home."""

import json
import os
from pathlib import Path

import pytest

from conftest import file_mode
from test_app_server import told
from test_bridge import EVENTS
from test_tools import commands

INIT, RESULT = EVENTS[0], EVENTS[-1]
PLAN = {"todos": [{"content": "Read the code", "status": "completed", "activeForm": "Reading the code"},
                  {"content": "Fix the bug", "status": "in_progress", "activeForm": "Fixing the bug"},
                  {"content": "Run the tests", "status": "pending", "activeForm": "Running the tests"}]}


def use(tool_id, name, data, parent=None):
    """An assistant event with one tool use: the agent's own, or a sub-agent's (parent: its sub-agent tool's id)."""
    event = {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": tool_id, "name": name,
                                                           "input": data}]}}
    return {**event, "parent_tool_use_id": parent} if parent else event


def result(tool_id, text="ok", parent=None, error=False):
    """A tool's result, as Claude Code streams it back."""
    event = {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tool_id, "is_error": error,
                                                      "content": [{"type": "text", "text": text}]}]}}
    return {**event, "parent_tool_use_id": parent} if parent else event


def ask(name, data, tool_id=None):
    """Claude Code asking the app for one of its own tools (a can_use_tool request); tool_id: the use it is for."""
    return {"ask_permission": {"tool_name": name, "input": data, **({"tool_use_id": tool_id} if tool_id else {})}}


def bridge_for(tmp_path, runner, replies=(), agent_id="a1", **options):
    """(a bridge, the requests it showed the user): the user answers each card in turn from `replies` ("once",
    "always", or ("deny", "a note")), and denies once they run out."""
    from ai_browser.app.bridge import ClaudeBridge

    shown, queue = [], list(replies)

    async def on_permission(request):
        shown.append(request)
        return queue.pop(0) if queue else "deny"

    bridge = ClaudeBridge(tmp_path / "home", claude=runner, agent_id=agent_id, on_permission=on_permission, **options)
    return bridge, shown


def flag(argv, name):
    return argv[argv.index(name) + 1]


def cwd_of(tmp_path) -> str:
    """The folder the fake claude ran in."""
    return json.loads((tmp_path / "fake-claude.log.env").read_text(encoding="utf-8"))["cwd"]


@pytest.fixture
def project(tmp_path, user_home):
    """A throwaway project folder, and a folder outside it."""
    folder = tmp_path / "project"
    (folder / "src").mkdir(parents=True)
    (folder / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "secret.txt").write_text("secret\n", encoding="utf-8")
    return folder


async def test_an_agent_has_claude_codes_own_tools_and_asks_the_app(fake_claude, tmp_path):  # Decision 1
    from ai_browser.app import powers

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    bridge, _ = bridge_for(tmp_path, runner)
    [event async for event in bridge.send("hi")]
    await bridge.close()
    argv = commands(log)[0]
    assert flag(argv, "--tools") == ",".join(powers.TOOLS)
    assert flag(argv, "--permission-prompt-tool") == "stdio" and "--permission-mode" not in argv
    allowed = flag(argv, "--allowedTools").split(",")
    assert allowed == ["mcp__ai-browser__*", "TodoWrite", powers.SUBAGENT_TOOL]  # Decision 3: never asked
    assert flag(argv, "--setting-sources") == powers.UNTRUSTED_SOURCES  # the scratch folder: nothing of its own
    scratch = tmp_path / "home" / "app" / "agents" / "a1" / "work"
    assert scratch.is_dir() and cwd_of(tmp_path) == str(scratch.resolve())
    assert "--bare" not in argv


async def test_trust_decides_what_of_the_folder_loads(fake_claude, tmp_path, project):  # Decision 7
    from ai_browser.app import powers

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    for trusted, sources in ((True, "local,project"), (False, powers.UNTRUSTED_SOURCES)):
        log.write_text("", encoding="utf-8")
        bridge, _ = bridge_for(tmp_path, runner, work=project, trusted=trusted)
        [event async for event in bridge.send("hi")]
        await bridge.close()
        assert flag(commands(log)[0], "--setting-sources") == sources
        assert cwd_of(tmp_path) == os.path.realpath(project)


async def test_only_a_folders_site_rules_are_handed_over(fake_claude, tmp_path, project):  # plan decision 1
    from ai_browser.app.powers import Rules

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    rules = Rules(tmp_path / "home")
    for rule in ("Bash(npm test:*)", "Edit", "WebSearch", "WebFetch(domain:docs.python.org)"):
        rules.add(project, rule)
    bridge, _ = bridge_for(tmp_path, runner, work=project, rules=rules, trusted=True)
    [event async for event in bridge.send("hi")]
    await bridge.close()
    allowed = flag(commands(log)[0], "--allowedTools").split(",")
    assert "WebFetch(domain:docs.python.org)" in allowed
    assert not {"Bash(npm test:*)", "Edit", "WebSearch"} & set(allowed)


@pytest.mark.parametrize("sandbox", [False, True])
async def test_the_settings_file_asks_for_everything_and_holds_the_sandbox_where_it_works(  # R1, R3
        fake_claude, tmp_path, monkeypatch, sandbox):
    from ai_browser.app import powers

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    monkeypatch.setattr(powers, "ASK_ALL", True)
    monkeypatch.setattr(powers, "sandbox_on", lambda: sandbox)
    bridge, _ = bridge_for(tmp_path, runner)
    [event async for event in bridge.send("hi")]
    await bridge.close()
    path = Path(flag(commands(log)[0], "--settings"))
    settings = json.loads(path.read_text(encoding="utf-8"))
    assert settings["permissions"] == {"ask": list(powers.ASKED)} and ("sandbox" in settings) is sandbox
    assert path.parent == tmp_path / "home" / "app" / "agents" / "a1" and file_mode(path) in (0o600, None)
    monkeypatch.setattr(powers, "ASK_ALL", False)
    monkeypatch.setattr(powers, "sandbox_on", lambda: False)
    log.write_text("", encoding="utf-8")
    plain, _ = bridge_for(tmp_path, runner, agent_id="a2")
    [event async for event in plain.send("hi")]
    await plain.close()
    assert "--settings" not in commands(log)[0]  # nothing to say: no file


async def test_a_folder_gone_between_turns_is_said_plainly(fake_claude, tmp_path, project):  # Review Focus 4
    from ai_browser.app.bridge import FOLDER_GONE

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    bridge, _ = bridge_for(tmp_path, runner, work=project, trusted=False)
    assert [event async for event in bridge.send("one")][-1]["type"] == "done"
    project.rename(tmp_path / "renamed")
    events = [event async for event in bridge.send("two")]
    await bridge.close()
    assert events == [{"type": "error", "text": FOLDER_GONE.format(path=project), "folder_gone": True}]
    assert "isn't there any more" in events[0]["text"] and "Settings → Permissions" in events[0]["text"]
    assert told(log) == ["one"]  # nothing reached Claude Code


def test_the_prompt_tells_agents_about_their_own_tools():  # Decision 12
    from ai_browser.app.bridge import BRAVE_PROMPT

    words = " ".join(BRAVE_PROMPT.split()).lower()
    for line in ("use web search and web fetch for quick lookups, and brave for pages that need the user's login or "
                 "clicks", "never use them, curl or any other command to get around a bot check or a block",
                 "commands and file edits run in the task's folder", "keep a to-do list",
                 "use sub-agents for independent parts", "never type passwords",
                 "if a result says ⛔ bot check, stop and tell the user"):
        assert line in words, line


async def test_each_action_has_a_badge_a_summary_and_a_time(fake_claude, tmp_path):  # Decision 10
    import time

    runner, _, script = fake_claude
    script.write_text(json.dumps([INIT, use("u1", "Bash", {"command": "npm test"}), result("u1", "3 passed"),
                                  use("u2", "WebFetch", {"url": "https://docs.python.org/3/", "prompt": "x"}),
                                  use("u3", "mcp__ai-browser__load_skill", {"name": "ai-browser:website-qa"}),
                                  use("u4", "mcp__ai-browser__open", {"url": "https://shop.example/"}), RESULT]),
                      encoding="utf-8")
    bridge, _ = bridge_for(tmp_path, runner)
    before = time.time()
    events = [event async for event in bridge.send("go")]
    await bridge.close()
    tools = [event for event in events if event["type"] == "tool"]
    assert [(tool["name"], tool["badge"]) for tool in tools] == [
        ("Bash", "Bash"), ("WebFetch", "Web Fetch"), ("load_skill", "Skill"), ("open", "Browser Agent")]
    assert [tools[0]["summary"], tools[1]["summary"], tools[3]["summary"]] == [
        "npm test", "https://docs.python.org/3/", "https://shop.example/"]
    assert all(before - 1 <= tool["at"] <= time.time() + 1 and "sub" not in tool for tool in tools)
    done = next(event for event in events if event["type"] == "tool_result")
    assert (done["id"], done["name"], done["lines"]) == ("u1", "Bash", ["3 passed"])


async def test_the_to_do_list_comes_from_the_stream_and_is_no_action_line(fake_claude, tmp_path):  # Decision 9
    runner, _, script = fake_claude
    script.write_text(json.dumps([INIT, use("t1", "TodoWrite", PLAN), result("t1", "Todos have been modified"),
                                  RESULT]), encoding="utf-8")
    bridge, _ = bridge_for(tmp_path, runner)
    events = [event async for event in bridge.send("plan it")]
    await bridge.close()
    assert [event["type"] for event in events] == ["status", "todos", "message_end", "done"]
    assert events[1]["todos"] == [{"content": "Read the code", "status": "completed", "active": "Reading the code"},
                                  {"content": "Fix the bug", "status": "in_progress", "active": "Fixing the bug"},
                                  {"content": "Run the tests", "status": "pending", "active": "Running the tests"}]


async def test_sub_agents_start_work_and_end_in_the_stream(fake_claude, tmp_path):  # Decision 8
    from ai_browser.app.powers import SUBAGENT_TOOL

    runner, _, script = fake_claude
    sub_words = {"type": "stream_event", "parent_tool_use_id": "u1",
                 "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "sub words"}}}
    script.write_text(json.dumps([INIT, use("u1", SUBAGENT_TOOL, {"description": "Research", "prompt": "Find it"}),
                                  sub_words, use("u2", "Bash", {"command": "ls"}, parent="u1"),
                                  result("u2", "src", parent="u1"), use("t2", "TodoWrite", PLAN, parent="u1"),
                                  result("u1", "Found it"), RESULT]), encoding="utf-8")
    bridge, _ = bridge_for(tmp_path, runner)
    events = [event async for event in bridge.send("research it")]
    await bridge.close()
    assert {"type": "subagent", "id": "u1", "task": "Research", "state": "working"} in events
    started = next(event for event in events if event["type"] == "tool" and event["id"] == "u1")
    assert started["badge"] == "Sub-agent" and started["summary"] == "Research" and "sub" not in started
    sub_tool = next(event for event in events if event["type"] == "tool" and event["id"] == "u2")
    assert sub_tool["sub"] == "u1" and sub_tool["badge"] == "Bash"
    assert next(event for event in events if event["type"] == "tool_result" and event["id"] == "u2")["sub"] == "u1"
    assert events[-2] == {"type": "subagent", "id": "u1", "task": "Research", "state": "done"}
    assert not any(event["type"] == "delta" and "sub words" in event["text"] for event in events)  # its words stay out
    assert not any(event["type"] == "todos" for event in events)  # a sub-agent's own list isn't the agent's
    assert [event["type"] for event in events].count("message_end") == 1  # the agent's own message only
    assert bridge._parents == {"u2": "u1", "t2": "u1"} and bridge._subagents == {"u1": "Research"}
