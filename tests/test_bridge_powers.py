"""The bridge with agent powers (app/bridge.py): Claude Code's own tools, the task's folder as its cwd, trust deciding
--setting-sources, every request decided by the app (app/powers.py), and the stream's badges, to-do list and
sub-agents. On the fake claude, in throwaway folders and a throwaway home."""

import json
import os
from pathlib import Path

import pytest

from conftest import file_mode, symlink_or_skip
from test_app_server import told
from test_bridge import EVENTS
from test_tools import answers, commands

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


@pytest.fixture
def repo(project):
    """The project as a Git folder whose settings run nothing: git status is harmless there."""
    (project / ".git").mkdir()
    (project / ".git" / "config").write_text("[core]\n\tbare = false\n", encoding="utf-8")
    return project


def behaviors(log):
    return [answer["behavior"] for answer in answers(log)]


async def run(bridge, text="go"):
    events = [event async for event in bridge.send(text)]
    await bridge.close()
    return events


async def test_reads_inside_the_list_a_sub_agent_and_harmless_commands_never_show_a_card(  # Decision 3
        fake_claude, tmp_path, repo):
    from ai_browser.app.powers import SUBAGENT_TOOL

    runner, log, script = fake_claude
    script.write_text(json.dumps([INIT, ask("Read", {"file_path": str(repo / "src" / "app.py")}),
                                  ask("TodoWrite", PLAN),
                                  ask(SUBAGENT_TOOL, {"description": "Research", "prompt": "Find it"}),
                                  ask("Bash", {"command": "git status"}), ask("Bash", {"command": "ls src"}), RESULT]),
                      encoding="utf-8")
    bridge, shown = bridge_for(tmp_path, runner, work=repo)
    await run(bridge, "look")
    assert shown == [] and behaviors(log) == ["allow"] * 5


async def test_a_command_shows_a_card_and_always_saves_a_rule_for_the_folder(  # Decisions 2 and 5, Review Focus 1
        fake_claude, tmp_path, project):
    from ai_browser.app.powers import Rules

    runner, log, script = fake_claude
    script.write_text(json.dumps([INIT, ask("Bash", {"command": "npm test"}),
                                  ask("Bash", {"command": "npm test --watch"}),
                                  ask("Bash", {"command": "npm test; rm -rf src"}), RESULT]), encoding="utf-8")
    rules = Rules(tmp_path / "home")
    bridge, shown = bridge_for(tmp_path, runner, ["always", "deny"], work=project, rules=rules)
    await run(bridge, "test it")
    assert [request["card"]["text"] for request in shown] == ["npm test", "npm test; rm -rf src"]  # --watch: a rule
    first, last = shown
    assert (first["tool"], first["server"], first["sub"], first["input"]) == ("Bash", "", "", {"command": "npm test"})
    assert first["card"]["always"] is True and first["card"]["folder"] == str(project)
    assert first["card"]["scratch"] is False
    assert last["card"]["always"] is False  # a rule never covers a second command
    assert rules.allowed(project) == ["Bash(npm test:*)"]
    assert behaviors(log) == ["allow", "allow", "deny"]


async def test_always_in_the_scratch_folder_lasts_for_this_agent_only(fake_claude, tmp_path):  # plan decision 10
    from ai_browser.app.powers import Rules

    runner, log, script = fake_claude
    script.write_text(json.dumps([INIT, ask("Bash", {"command": "make build"}), ask("Bash", {"command": "make build"}),
                                  RESULT]), encoding="utf-8")
    rules = Rules(tmp_path / "home")
    bridge, shown = bridge_for(tmp_path, runner, ["always"], rules=rules)
    await run(bridge)
    assert len(shown) == 1 and shown[0]["card"]["scratch"] is True and behaviors(log) == ["allow", "allow"]
    assert not (tmp_path / "home" / "permissions.json").exists()  # never saved: numbers start at 1 again
    again, asked_again = bridge_for(tmp_path, runner, ["once", "once"], agent_id="a2", rules=rules)
    await run(again)
    assert len(asked_again) == 2  # another agent asks again


async def test_a_dangerous_command_never_offers_always_and_a_forged_always_saves_nothing(  # Decision 4
        fake_claude, tmp_path, project):
    from ai_browser.app.powers import Rules

    runner, log, script = fake_claude
    script.write_text(json.dumps([INIT, ask("Bash", {"command": "sudo ls"}), ask("Bash", {"command": "sudo ls"}),
                                  RESULT]), encoding="utf-8")
    rules = Rules(tmp_path / "home")
    bridge, shown = bridge_for(tmp_path, runner, ["always", "deny"], work=project, rules=rules)
    await run(bridge)
    assert [request["card"]["always"] for request in shown] == [False, False]
    assert rules.allowed(project) == [] and behaviors(log) == ["allow", "deny"]  # "always" counted as once


async def test_deny_carries_the_users_note_to_the_agent(fake_claude, tmp_path, project):  # Decision 2
    runner, log, script = fake_claude
    edit = {"file_path": str(project / "src" / "app.py"), "old_string": "hi", "new_string": "bye"}
    script.write_text(json.dumps([INIT, ask("Edit", edit), RESULT]), encoding="utf-8")
    bridge, shown = bridge_for(tmp_path, runner, [("deny", "keep the greeting")], work=project)
    await run(bridge)
    assert shown[0]["card"]["lines"] == [["-", "hi"], ["+", "bye"]]
    assert answers(log) == [{"behavior": "deny", "message": "The user said no: keep the greeting"}]


async def test_a_sub_agents_request_names_the_sub_agent(fake_claude, tmp_path):  # Decision 2
    from ai_browser.app.powers import SUBAGENT_TOOL

    runner, log, script = fake_claude
    script.write_text(json.dumps([INIT, use("u1", SUBAGENT_TOOL, {"description": "Research", "prompt": "x"}),
                                  use("u2", "Bash", {"command": "npm install"}, parent="u1"),
                                  ask("Bash", {"command": "npm install"}, tool_id="u2"), RESULT]), encoding="utf-8")
    bridge, shown = bridge_for(tmp_path, runner, ["once"])
    await run(bridge)
    assert shown[0]["sub"] == "Research" and behaviors(log) == ["allow"]


async def test_after_stop_a_sub_agents_request_is_denied_without_a_card(  # Review Focus 3
        fake_claude, tmp_path, monkeypatch):
    from ai_browser.app import bridge as bridge_module
    from ai_browser.app.powers import SUBAGENT_TOOL

    monkeypatch.setattr(bridge_module, "STOP_GRACE", 3)
    runner, log, script = fake_claude
    script.write_text(json.dumps([{"ignore_interrupt": True}, INIT,
                                  use("u1", SUBAGENT_TOOL, {"description": "Research", "prompt": "x"}), {"sleep": 1},
                                  use("u2", "Bash", {"command": "npm install"}, parent="u1"),
                                  ask("Bash", {"command": "npm install"}, tool_id="u2"), RESULT]), encoding="utf-8")
    bridge, shown = bridge_for(tmp_path, runner, ["once"])
    async for event in bridge.send("research it"):
        if event["type"] == "subagent":
            await bridge.stop()  # the user's Stop, while the sub-agent works
    await bridge.close()
    assert shown == [] and behaviors(log) == ["deny"]  # nothing runs, and no card shows


async def test_a_read_through_a_symlink_that_leaves_the_folder_shows_a_card(  # Review Focus 2
        fake_claude, tmp_path, project):
    symlink_or_skip(tmp_path / "outside", project / "link")
    runner, log, script = fake_claude
    script.write_text(json.dumps([INIT, ask("Read", {"file_path": str(project / "link" / "secret.txt")}), RESULT]),
                      encoding="utf-8")
    bridge, shown = bridge_for(tmp_path, runner, ["once"], work=project)
    await run(bridge)
    assert len(shown) == 1 and shown[0]["card"]["badge"] == "Read" and shown[0]["card"]["always"] is False


async def test_after_an_allowed_cd_harmless_commands_ask(fake_claude, tmp_path, project):  # plan decision 8
    runner, log, script = fake_claude
    script.write_text(json.dumps([INIT, ask("Bash", {"command": "ls"}), ask("Bash", {"command": "cd src"}),
                                  ask("Bash", {"command": "ls"}), RESULT]), encoding="utf-8")
    bridge, shown = bridge_for(tmp_path, runner, ["once", "once"], work=project)
    await run(bridge)
    assert [request["card"]["text"] for request in shown] == ["cd src", "ls"]
    assert behaviors(log) == ["allow", "allow", "allow"]
