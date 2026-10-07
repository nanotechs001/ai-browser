"""The app server with agent powers (app/server.py): the four folder messages, AI Browser's own pages only; new_task
with a folder; and Deny's note, over a real socket. On the fake claude, in throwaway folders and a throwaway home."""

import json
import os

import pytest

from test_app_server import started, until, wait_for
from test_bridge import EVENTS
from test_bridge_powers import INIT, RESULT, ask
from test_tools import answers
from ui_socket import ui_socket

POWERS = ("folder_choose", "folder_trust", "permission_rules", "permission_rule_remove")


@pytest.fixture
def project(tmp_path, user_home):
    folder = tmp_path / "project"
    folder.mkdir()
    return folder


async def hello(ws):
    await ws.send(json.dumps({"type": "hello", "view": "home"}))
    await until(ws, lambda message: message["type"] == "snapshot")


async def answer_to(ws, message):
    await ws.send(json.dumps(message))
    return (await until(ws, lambda heard: heard.get("request") == message["request"]))[-1]


def test_the_folder_messages_are_app_only():  # the spec's Interfaces: every new message app-only
    from ai_browser.app.server import MESSAGE_RULES, may_send

    for kind in POWERS:
        assert kind in MESSAGE_RULES and may_send("app", {"type": kind})
        assert not may_send("none", {"type": kind}) and not may_send("watcher", {"type": kind})


async def test_choosing_a_folder_checks_it_and_says_whether_its_trusted(  # Decisions 6 and 7
        fake_claude, tmp_path, project):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    (tmp_path / "home").mkdir(exist_ok=True)
    (project / "notes.txt").write_text("x", encoding="utf-8")
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            assert await answer_to(ws, {"type": "folder_choose", "path": str(project), "request": "f1"}) == {
                "type": "folder", "request": "f1",
                "folder": {"path": os.path.realpath(project), "name": "project", "trusted": None}}
            for path, words in ((str(tmp_path / "home"), "AI Browser's own folder"),
                                (str(project / "notes.txt"), "a file"), ("relative/path", "full path"),
                                (str(tmp_path / "gone"), "isn't there"), (7, "full path")):
                error = await answer_to(ws, {"type": "folder_choose", "path": path, "request": "f2"})
                assert error["type"] == "error" and words in error["text"], path
    finally:
        await server.stop()


async def test_trust_is_answered_once_kept_and_shown_to_every_page(fake_claude, tmp_path, project):  # Decision 7
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        async with ui_socket(server, url) as ws, ui_socket(server, url) as other:
            await hello(ws)
            await hello(other)
            trusted = await answer_to(ws, {"type": "folder_trust", "path": str(project), "trust": True,
                                           "request": "t1"})
            assert trusted["folder"]["trusted"] is True and server.agents.rules.trusted(project) is True
            heard = (await until(other, lambda message: message["type"] == "permissions"))[-1]
            assert heard["folders"][0]["path"] == os.path.realpath(project) and heard["folders"][0]["trusted"]
            untrusted = await answer_to(ws, {"type": "folder_trust", "path": str(project), "trust": False,
                                             "request": "t2"})
            assert untrusted["folder"]["trusted"] is False and server.agents.rules.trusted(project) is False
            refused = await answer_to(ws, {"type": "folder_trust", "path": str(tmp_path), "trust": True,
                                           "request": "t3"})
            assert refused["type"] == "error" and server.agents.rules.trusted(tmp_path) is None
    finally:
        await server.stop()


async def test_a_new_task_starts_in_its_folder_once_trust_is_answered(fake_claude, tmp_path, project):  # Decision 6
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            task = {"type": "new_task", "text": "fix the footer", "folder": str(project)}
            first = await answer_to(ws, {**task, "request": "r1"})
            assert first["type"] == "error" and "Trust this folder" in first["text"] and not server.agents.agents
            await answer_to(ws, {"type": "folder_trust", "path": str(project), "trust": True, "request": "t1"})
            created = await answer_to(ws, {**task, "request": "r2"})
            assert created["type"] == "created"
            agent = server.agents.agents[created["id"]]
            assert agent.folder == os.path.realpath(project) and agent.trusted is True
            scratch = await answer_to(ws, {**task, "folder": "", "request": "r3"})
            assert server.agents.agents[scratch["id"]].folder is None  # "" is No folder
    finally:
        await server.stop()


async def test_settings_lists_the_folders_and_removes_a_rule_or_a_folder(  # Review Focus 4
        fake_claude, tmp_path, project):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    rules = server.agents.rules
    for rule in ("Bash(npm test:*)", "Edit"):
        rules.add(project, rule)
    rules.trust(project)
    rules.note_used(project)
    gone = tmp_path / "old-project"
    gone.mkdir()
    rules.add(gone, "WebSearch")
    gone.rmdir()  # unplugged since: its rules stay until removed
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            await ws.send(json.dumps({"type": "permission_rules"}))
            listed = (await until(ws, lambda message: message["type"] == "permissions"))[-1]["folders"]
            rows = {row["path"]: row for row in listed}
            assert [rule["rule"] for rule in rows[os.path.realpath(project)]["rules"]] == ["Bash(npm test:*)", "Edit"]
            old = rows[os.path.realpath(gone)]
            assert old["missing"] is True and old["rules"] == [{"rule": "WebSearch", "label": "Search the web"}]
            await ws.send(json.dumps({"type": "permission_rule_remove", "folder": os.path.realpath(project),
                                      "rule": "Edit"}))
            await until(ws, lambda message: message["type"] == "permissions")
            assert rules.allowed(project) == ["Bash(npm test:*)"]
            await ws.send(json.dumps({"type": "permission_rule_remove", "folder": os.path.realpath(gone),
                                      "all": True}))
            after = (await until(ws, lambda message: message["type"] == "permissions"))[-1]["folders"]
            assert [row["path"] for row in after] == [os.path.realpath(project)]
    finally:
        await server.stop()


async def test_deny_with_a_note_over_the_socket(fake_claude, tmp_path):  # Decision 2
    server, url = await started(fake_claude, tmp_path, [INIT, ask("Bash", {"command": "npm test"}), {"sleep": 1},
                                                        RESULT])
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            await ws.send(json.dumps({"type": "new_task", "text": "test it", "request": "r1"}))
            request = (await until(ws, lambda message: message["type"] == "permission_request"))[-1]
            assert request["card"]["text"] == "npm test" and request["input"] == {}
            await ws.send(json.dumps({"type": "permission", "agent": request["agent"], "request": request["request"],
                                      "answer": "deny", "note": "not now"}))
            await wait_for(lambda: answers(fake_claude[1]))
            assert answers(fake_claude[1]) == [{"behavior": "deny", "message": "The user said no: not now"}]
    finally:
        await server.stop()


def test_the_auto_approve_switch_is_app_only():  # the user's choice, 2026-10-07: every new message app-only
    from ai_browser.app.server import MESSAGE_RULES, may_send

    assert "agent_auto" in MESSAGE_RULES and may_send("app", {"type": "agent_auto"})
    assert not may_send("none", {"type": "agent_auto"}) and not may_send("watcher", {"type": "agent_auto"})


async def test_new_task_takes_auto_and_agent_auto_switches_it(fake_claude, tmp_path):  # the user's choice
    server, url = await started(fake_claude, tmp_path, EVENTS)
    agents = server.agents.agents
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            made = [await answer_to(ws, {"type": "new_task", "text": "fix it", **extra, "request": f"r{n}"})
                    for n, extra in enumerate(({"auto": True}, {}, {"auto": "yes"}, {"auto": 1}))]
            assert [agents[created["id"]].auto for created in made] == [True, False, False, False]
            assert [agents[created["id"]].bridge.auto for created in made] == [True, False, False, False]
            off = made[1]["id"]
            await ws.send(json.dumps({"type": "agent_auto", "agent": off, "on": True}))
            await until(ws, lambda heard: heard["type"] == "agent" and heard["agent"]["id"] == off
                        and heard["agent"]["auto"] is True)
            assert agents[off].bridge.auto is True
            for odd in ({"on": "false"}, {"on": 0}, {}):  # not a yes or a no: nothing changes
                await ws.send(json.dumps({"type": "agent_auto", "agent": off, **odd}))
            await ws.send(json.dumps({"type": "agent_auto", "agent": "a99", "on": True}))  # no such agent
            await ws.send(json.dumps({"type": "events", "id": off}))
            await until(ws, lambda heard: heard["type"] == "agent_events")
            assert agents[off].auto is True and agents[off].bridge.auto is True
            await ws.send(json.dumps({"type": "agent_auto", "agent": off, "on": False}))
            await until(ws, lambda heard: heard["type"] == "agent" and heard["agent"]["id"] == off
                        and heard["agent"]["auto"] is False)
            assert agents[off].bridge.auto is False
    finally:
        await server.stop()


async def test_a_template_run_and_a_brain_started_task_never_auto_approve(fake_claude, tmp_path):  # the Brain's rule
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer
    from ai_browser.brain.workflows import WorkflowRunner, WorkflowStore
    from test_app_server import TALKING, with_hearing

    runner, _, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    home = tmp_path / "home"
    agents = AgentManager(home, claude=runner)
    workflows = WorkflowStore(home)
    workflows.save({"name": "Weekly report", "instructions": "Write the weekly report"})
    server = AppServer(home, agents, workflows=workflows, runner=WorkflowRunner(workflows, agents))
    url = await server.start()
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            created = await answer_to(ws, {"type": "workflow_run", "slug": "weekly-report", "text": "",
                                           "auto": True, "request": "r1"})
            assert agents.agents[created["id"]].auto is False and agents.agents[created["id"]].bridge.auto is False
    finally:
        await agents.close_all()
        await server.stop()
    talk = {"default": EVENTS, TALKING: [{"result": json.dumps({"say": "I can start an agent.",
                                                                "action": "start_agent"})}]}
    server, url, _ = await with_hearing(fake_claude, tmp_path / "brain", talk)
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            await ws.send(json.dumps({"type": "brain_ask", "talk": "k1", "request": "t1", "text": "check the shop"}))
            answer = (await until(ws, lambda heard: heard["type"] == "brain_answer"))[-1]
            await ws.send(json.dumps({"type": "brain_confirm", "talk": "k1", "request": "t2", "auto": True,
                                      "proposal": answer["proposal"]["id"]}))
            await until(ws, lambda heard: heard["type"] == "created")
            assert server.agents.agents["a1"].auto is False and server.agents.agents["a1"].bridge.auto is False
    finally:
        await server.agents.close_all()
        await server.stop()
