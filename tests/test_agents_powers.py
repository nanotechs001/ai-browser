"""Agents with powers (app/agents.py): a folder per task and its trust, Always allow for the folder, Deny's note, Stop
ending sub-agents and their cards, and the plan and the sub-agents kept for pages opened later. On the fake claude,
in throwaway folders and a throwaway home."""

import json
import os

import pytest

from test_agents import drain
from test_app_server import wait_for
from test_bridge import EVENTS
from test_bridge_powers import INIT, PLAN, RESULT, ask, cwd_of, result, use
from test_tools import answers, commands


@pytest.fixture
def project(tmp_path, user_home):
    folder = tmp_path / "project"
    (folder / "src").mkdir(parents=True)
    (folder / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    return folder


def manager(fake_claude, tmp_path, script):
    from ai_browser.app.agents import AgentManager

    runner, log, script_file = fake_claude
    script_file.write_text(json.dumps(script), encoding="utf-8")
    return AgentManager(tmp_path / "home", claude=runner), log


async def test_a_task_runs_in_its_folder_and_its_row_says_so(fake_claude, tmp_path, project):  # Decision 6
    agents, log = manager(fake_claude, tmp_path, EVENTS)
    agents.rules.trust(project)
    try:
        agent = await agents.create("fix the footer", folder=str(project))
        await wait_for(lambda: agent.state == "your_turn")
        row = agents.snapshot()["agents"][0]
        assert (row["folder"], row["trusted"], row["todos"], row["subagents"]) == (
            os.path.realpath(project), True, [], [])
        assert cwd_of(tmp_path) == os.path.realpath(project)
        argv = commands(log)[0]
        assert argv[argv.index("--setting-sources") + 1] == "local,project"
        plain = await agents.create("look around")  # No folder: its own scratch folder
        await wait_for(lambda: plain.state == "your_turn")
        assert plain.folder is None and plain.trusted is False
        assert agents.rules.folders()[0]["path"] == os.path.realpath(project)  # recent, for the picker
    finally:
        await agents.close_all()


async def test_a_folder_needs_its_trust_answer_and_a_refused_one_never_starts(  # Decisions 6 and 7
        fake_claude, tmp_path, project, user_home):
    from ai_browser.app.powers import GONE, WHOLE_HOME

    agents, _ = manager(fake_claude, tmp_path, EVENTS)
    with pytest.raises(ValueError, match="Trust this folder"):
        await agents.create("x", folder=str(project))
    (tmp_path / "home").mkdir(exist_ok=True)
    for refused, words in ((str(tmp_path / "home"), "AI Browser's own folder"), (str(user_home), WHOLE_HOME),
                           (str(tmp_path / "gone"), GONE), ("relative", "full path")):
        with pytest.raises(ValueError, match=words.replace("?", r"\?")):
            await agents.create("x", folder=refused)
    assert agents.agents == {}
    agents.rules.untrust(project)  # "Don't trust" is an answer too
    agent = await agents.create("x", folder=str(project))
    assert agent.number == 1 and agent.trusted is False  # no number was spent on the refusals
    await agents.close_all()


async def test_always_allow_for_this_folder_is_kept_for_the_next_agent_there(  # Decision 5
        fake_claude, tmp_path, project):
    agents, log = manager(fake_claude, tmp_path, [INIT, ask("Bash", {"command": "npm test"}), {"sleep": 0.5}, RESULT])
    agents.rules.trust(project)
    feed = agents.subscribe()
    try:
        first = await agents.create("test it", folder=str(project))
        await wait_for(lambda: first.permission is not None)
        assert first.permission["card"]["text"] == "npm test" and first.permission["input"] == {}
        agents.answer_permission(first.id, first.permission["request"], "always")
        await wait_for(lambda: first.state == "your_turn")
        second = await agents.create("test it again", folder=str(project))
        await wait_for(lambda: second.state == "your_turn")
        asked = [message["agent"] for message in drain(feed) if message["type"] == "permission_request"]
        assert asked == [first.id]  # the second rode the folder's rule
        assert agents.rules.allowed(project) == ["Bash(npm test:*)"]
        assert [answer["behavior"] for answer in answers(log)] == ["allow", "allow"]
    finally:
        await agents.close_all()


async def test_deny_with_a_note_reaches_the_agent(fake_claude, tmp_path, project):  # Decision 2
    edit = {"file_path": str(project / "src" / "app.py"), "old_string": "hi", "new_string": "bye"}
    agents, log = manager(fake_claude, tmp_path, [INIT, ask("Edit", edit), {"sleep": 0.5}, RESULT])
    agents.rules.trust(project)
    try:
        agent = await agents.create("change it", folder=str(project))
        await wait_for(lambda: agent.permission is not None)
        agents.answer_permission(agent.id, agent.permission["request"], "deny", "  keep\nthe greeting  ")
        await wait_for(lambda: agent.state == "your_turn")
        assert answers(log) == [{"behavior": "deny", "message": "The user said no: keep the greeting"}]
    finally:
        await agents.close_all()


async def test_stop_ends_the_sub_agents_and_closes_their_card(fake_claude, tmp_path):  # Review Focus 3, Decision 8
    from ai_browser.app.powers import SUBAGENT_TOOL

    agents, log = manager(fake_claude, tmp_path, [
        INIT, use("u1", SUBAGENT_TOOL, {"description": "Research", "prompt": "x"}),
        use("u2", "Bash", {"command": "npm install"}, parent="u1"),
        ask("Bash", {"command": "npm install"}, tool_id="u2"), {"sleep": 5}, RESULT])
    try:
        agent = await agents.create("research it")
        await wait_for(lambda: agent.permission is not None)
        assert agent.permission["sub"] == "Research"
        assert agent.subagents == [{"id": "u1", "task": "Research", "action": "Bash npm install", "state": "working"}]
        await agents.stop(agent.id)
        await wait_for(lambda: agent.state == "stopped")
        assert agent.permission is None and [row["state"] for row in agent.subagents] == ["stopped"]
        assert [answer["behavior"] for answer in answers(log)] == ["deny"]
    finally:
        await agents.close_all()


async def test_a_card_answered_after_the_agent_closed_does_nothing(fake_claude, tmp_path):  # Review Focus 3
    agents, log = manager(fake_claude, tmp_path, [INIT, ask("Bash", {"command": "npm test"}), {"sleep": 5}, RESULT])
    agent = await agents.create("test it")
    await wait_for(lambda: agent.permission is not None)
    request = agent.permission["request"]
    await agents.close(agent.id)
    agents.answer_permission(agent.id, request, "once")  # a page's late click
    assert agent.id not in agents.agents and [answer["behavior"] for answer in answers(log)] == ["deny"]


async def test_the_plan_and_the_sub_agents_are_kept_for_pages_opened_later(fake_claude, tmp_path):  # Decisions 8, 9
    from ai_browser.app.powers import SUBAGENT_TOOL

    agents, _ = manager(fake_claude, tmp_path, [
        INIT, use("t1", "TodoWrite", PLAN), use("u1", SUBAGENT_TOOL, {"description": "Research", "prompt": "x"}),
        use("u2", "Bash", {"command": "ls"}, parent="u1"), result("u1", "found it"), RESULT])
    try:
        agent = await agents.create("fix the footer")
        await wait_for(lambda: agent.state == "your_turn")
        row = agents.snapshot()["agents"][0]
        assert [item["status"] for item in row["todos"]] == ["completed", "in_progress", "pending"]
        assert row["subagents"] == [{"id": "u1", "task": "Research", "action": "Bash ls", "state": "done"}]
        kinds = [event["type"] for event in agents.events_of(agent.id)]
        assert "todos" in kinds and "subagent" in kinds  # with the agent's events, too
    finally:
        await agents.close_all()


async def test_a_huge_edit_never_rides_in_the_agents_row(fake_claude, tmp_path, project):  # Review Focus 5
    big = "x\n" * 400_000
    agents, _ = manager(fake_claude, tmp_path, [INIT, ask("Write", {"file_path": str(project / "big.txt"),
                                                                    "content": big}), {"sleep": 5}, RESULT])
    agents.rules.trust(project)
    try:
        agent = await agents.create("write it", folder=str(project))
        await wait_for(lambda: agent.permission is not None)
        assert len(json.dumps(agents.snapshot()["agents"][0])) < 150_000
        assert agent.permission["input"] == {} and agent.permission["card"]["hidden"] > 0
    finally:
        await agents.close_all()


async def test_auto_approve_is_each_agents_own_switch(fake_claude, tmp_path, project):  # the user's choice, 2026-10-07
    agents, log = manager(fake_claude, tmp_path, [INIT, use("u1", "Bash", {"command": "npm test"}),
                                                  ask("Bash", {"command": "npm test"}, tool_id="u1"), RESULT])
    agents.rules.trust(project)
    try:
        agent = await agents.create("test it", folder=str(project), auto=True)
        assert agent.auto is True and agent.bridge.auto is True
        assert agents.snapshot()["agents"][0]["auto"] is True  # its row says so
        await wait_for(lambda: agent.state == "your_turn")
        assert {"type": "auto", "id": "u1"} in agents.events_of(agent.id)  # the mark, for pages opened later
        assert [answer["behavior"] for answer in answers(log)] == ["allow"]
        plain = await agents.create("look around", folder=str(project))
        odd = await agents.create("look around", folder=str(project), auto="yes")
        assert (plain.auto, plain.bridge.auto, odd.auto, odd.bridge.auto) == (False, False, False, False)
        feed = agents.subscribe()
        assert agents.set_auto(plain.id, True) is True and plain.auto is True and plain.bridge.auto is True
        assert [message["agent"]["auto"] for message in drain(feed) if message["type"] == "agent"] == [True]
        assert agents.set_auto(plain.id, False) is True and plain.auto is False and plain.bridge.auto is False
        assert agents.set_auto("a99", True) is False
    finally:
        await agents.close_all()
