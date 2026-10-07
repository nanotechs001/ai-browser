"""Workspaces (the new look, Decision 6): the store in <home>/workspaces.json (Task 5), and the messages that change it
(Task 6). In a throwaway home; the messages over a real socket, on the fake claude."""

import json

import pytest

from conftest import file_mode


def store(tmp_path):
    from ai_browser.app.workspaces import Workspaces

    return Workspaces(tmp_path / "home")


def test_a_workspace_is_created_renamed_and_deleted(tmp_path):
    workspaces = store(tmp_path)
    assert workspaces.list() == []
    research = workspaces.create("  Research \n")
    assert research["name"] == "Research" and research["templates"] == []
    assert research["id"].startswith("w") and len(research["id"]) == 9
    marketing = workspaces.create("Marketing")
    assert [row["name"] for row in workspaces.list()] == ["Research", "Marketing"]
    workspaces.rename(research["id"], "Deep research")
    assert workspaces.get(research["id"])["name"] == "Deep research"
    assert workspaces.delete(marketing["id"]) is True and workspaces.delete(marketing["id"]) is False
    path = tmp_path / "home" / "workspaces.json"
    assert file_mode(path) in (None, 0o600)
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "workspaces": [{"id": research["id"], "name": "Deep research", "templates": []}]}


@pytest.mark.parametrize(("name", "words"), [("", "a name"), ("   ", "a name"), (None, "a name"), (7, "a name"),
                                             ("x" * 41, "at most 40")])
def test_a_name_is_one_short_line(tmp_path, name, words):
    with pytest.raises(ValueError, match=words):
        store(tmp_path).create(name)


def test_a_direction_mark_can_never_reorder_a_name(tmp_path):
    assert store(tmp_path).create("‮evil​ one")["name"] == "evil one"


def test_a_name_is_taken_once_whatever_its_case(tmp_path):
    workspaces = store(tmp_path)
    research = workspaces.create("Research")
    other = workspaces.create("Product")
    with pytest.raises(ValueError, match="named research already"):
        workspaces.create("research")
    with pytest.raises(ValueError, match="already"):
        workspaces.rename(other["id"], "RESEARCH")
    workspaces.rename(research["id"], "research")  # its own name, in another case: fine
    with pytest.raises(ValueError, match="was deleted"):
        workspaces.rename("w00000000", "Gone")


def test_at_most_fifty(tmp_path):
    workspaces = store(tmp_path)
    for number in range(50):
        workspaces.create(f"Group {number}")
    with pytest.raises(ValueError, match="At most 50"):
        workspaces.create("One more")


def test_a_template_is_in_at_most_one_workspace(tmp_path):
    workspaces = store(tmp_path)
    one, two = workspaces.create("One"), workspaces.create("Two")
    workspaces.assign_template("weekly-report", one["id"])
    workspaces.assign_template("weekly-report", two["id"])
    assert workspaces.get(one["id"])["templates"] == [] and workspaces.get(two["id"])["templates"] == ["weekly-report"]
    workspaces.assign_template("weekly-report", None)
    assert workspaces.get(two["id"])["templates"] == []
    for slug, where, words in (("../x", one["id"], "Not a template"), ("ok\n", one["id"], "Not a template"),
                               ("ok", "w00000000", "was deleted")):
        with pytest.raises(ValueError, match=words):
            workspaces.assign_template(slug, where)


def test_a_broken_file_reads_as_none_and_a_broken_row_is_skipped(tmp_path):
    path = tmp_path / "home" / "workspaces.json"
    path.parent.mkdir(parents=True)
    workspaces = store(tmp_path)
    for text in ("{", "[]", '{"workspaces": 7}', ""):
        path.write_text(text, encoding="utf-8")
        assert workspaces.list() == []
    path.write_text(json.dumps({"workspaces": [
        {"id": "w1234abcd", "name": "Fine", "templates": ["a", "../b", 7, "a", "c\n"]},
        {"id": "nope", "name": "Bad id"}, {"id": "w1234abcd", "name": "Twice"}, {"id": "wabcdef01", "name": ""},
        {"id": "wabcdef02\n", "name": "Line"}, "not a row"]}), encoding="utf-8")
    assert workspaces.list() == [{"id": "w1234abcd", "name": "Fine", "templates": ["a"]}]


@pytest.mark.parametrize("broken", [b'{"workspaces": [{"id": "w1234abcd", "name": "Mine"', b"\xff\xfe not text",
                                    "unreadable"])
def test_a_file_that_cant_be_read_is_never_written_over(tmp_path, broken):  # the final review, F7
    import os

    path = tmp_path / "home" / "workspaces.json"
    path.parent.mkdir(parents=True)
    kept = b'{"workspaces": [{"id": "w1234abcd", "name": "Mine", "templates": []}]}' if broken == "unreadable" \
        else broken
    path.write_bytes(kept)
    if broken == "unreadable":
        if os.name == "nt" or os.geteuid() == 0:
            pytest.skip("a file only the owner can't read: POSIX, not as root")
        path.chmod(0)
    workspaces = store(tmp_path)
    try:
        assert workspaces.list() == []  # for display: no workspaces
        for change in (lambda: workspaces.create("Research"), lambda: workspaces.rename("w1234abcd", "Other"),
                       lambda: workspaces.delete("w1234abcd"), lambda: workspaces.assign_template("weekly", None)):
            with pytest.raises(ValueError, match=r"^Couldn't read your workspaces file: .*workspaces\.json .*"
                                                 r"Fix it or remove it, then try again\.$"):
                change()
    finally:
        path.chmod(0o600)
    assert path.read_bytes() == kept  # never replaced


def test_a_missing_or_blank_file_is_no_workspaces_and_can_be_written(tmp_path):  # the final review, F7
    workspaces = store(tmp_path)
    assert workspaces.create("First")["name"] == "First"  # no file yet
    path = tmp_path / "home" / "workspaces.json"
    path.write_text("  \n", encoding="utf-8")  # blank: nothing in it to lose
    assert workspaces.create("Second")["name"] == "Second" and [row["name"] for row in workspaces.list()] == ["Second"]


from test_app_server import recv, started, until, wait_for  # noqa: E402
from test_bridge import EVENTS  # noqa: E402
from ui_socket import ui_socket  # noqa: E402

WORKING = [EVENTS[0], {"sleep": 30}]  # an agent that stays at work
WORKSPACE_MESSAGES = ("workspaces", "workspace_save", "workspace_delete", "workspace_assign")


async def hello(ws):
    await ws.send(json.dumps({"type": "hello", "view": "mission"}))
    return (await until(ws, lambda message: message["type"] == "snapshot"))[-1]


async def answer_to(ws, message):
    await ws.send(json.dumps(message))
    return (await until(ws, lambda heard: heard.get("request") == message["request"]))[-1]


def test_the_workspace_messages_are_app_only():  # the spec's Safety: no new right
    from ai_browser.app.server import MESSAGE_RULES, may_send

    for kind in WORKSPACE_MESSAGES:
        assert kind in MESSAGE_RULES and may_send("app", {"type": kind})
        assert not may_send("none", {"type": kind}) and not may_send("watcher", {"type": kind})


async def test_pages_create_rename_and_hear_the_workspaces(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        async with ui_socket(server, url) as ws, ui_socket(server, url) as other:
            assert (await hello(ws))["workspaces"] == []
            await hello(other)
            saved = await answer_to(ws, {"type": "workspace_save", "name": "Research", "request": "s1"})
            assert saved["type"] == "workspace_saved"
            heard = (await until(other, lambda message: message["type"] == "workspaces"))[-1]
            assert heard["workspaces"] == [{"id": saved["id"], "name": "Research", "templates": []}]
            await answer_to(ws, {"type": "workspace_save", "id": saved["id"], "name": "Deep research", "request": "s2"})
            assert server.workspaces.get(saved["id"])["name"] == "Deep research"
            taken = await answer_to(ws, {"type": "workspace_save", "name": "deep RESEARCH", "request": "s3"})
            assert taken["type"] == "error" and "already" in taken["text"]
            gone = await answer_to(ws, {"type": "workspace_save", "id": "w00000000", "name": "X", "request": "s4"})
            assert gone == {"type": "error", "text": "That workspace was deleted", "request": "s4"}
            await ws.send(json.dumps({"type": "workspaces"}))
            listed = (await until(ws, lambda message: message["type"] == "workspaces"))[-1]
            assert [row["name"] for row in listed["workspaces"]] == ["Deep research"]
    finally:
        await server.stop()


async def test_a_new_agent_starts_in_its_workspace_and_moves(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, WORKING)
    research = server.workspaces.create("Research")
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            created = await answer_to(ws, {"type": "new_task", "text": "look it up", "workspace": research["id"],
                                           "request": "n1"})
            agent = server.agents.agents[created["id"]]
            assert agent.workspace == research["id"] and agent.public()["workspace"] == research["id"]
            other_id = (await answer_to(ws, {"type": "new_task", "text": "no group", "workspace": "w00000000",
                                             "request": "n2"}))["id"]
            assert server.agents.agents[other_id].workspace is None  # a deleted workspace never refuses a start
            await ws.send(json.dumps({"type": "workspace_assign", "agent": other_id, "workspace": research["id"]}))
            moved = (await until(ws, lambda m: m["type"] == "agent" and m["agent"]["id"] == other_id
                                 and m["agent"]["workspace"] == research["id"]))[-1]
            assert moved["agent"]["state"] == "working"
            await ws.send(json.dumps({"type": "workspace_assign", "template": "weekly-report",
                                      "workspace": research["id"]}))
            heard = (await until(ws, lambda message: message["type"] == "workspaces"))[-1]
            assert heard["workspaces"][0]["templates"] == ["weekly-report"]
            refused = await answer_to(ws, {"type": "workspace_assign", "agent": other_id, "workspace": "w00000000",
                                           "request": "a1"})
            assert refused == {"type": "error", "text": "That workspace was deleted", "request": "a1"}
    finally:
        await server.agents.close_all()
        await server.stop()


async def test_deleting_a_workspace_ungroups_its_running_agents(fake_claude, tmp_path):  # Review Focus 4
    server, url = await started(fake_claude, tmp_path, WORKING)
    research = server.workspaces.create("Research")
    try:
        agent = await server.agents.create("keep working", workspace=research["id"])
        await wait_for(lambda: agent.state == "working")
        async with ui_socket(server, url) as ws:
            await hello(ws)
            await ws.send(json.dumps({"type": "workspace_delete", "id": research["id"]}))
            heard = {}  # the list comes at once; the agent's row through the agents' feed, a moment later
            while len(heard) < 2:
                message = await recv(ws)
                if message["type"] == "workspaces" or (message["type"] == "agent"
                                                       and message["agent"]["id"] == agent.id):
                    heard[message["type"]] = message
            assert heard["workspaces"]["workspaces"] == []
            row = heard["agent"]["agent"]
            assert row["workspace"] is None and row["state"] == "working"  # still at work, in no workspace
        assert agent.state == "working" and server.workspaces.list() == []
    finally:
        await server.agents.close_all()
        await server.stop()


async def test_a_template_runs_in_its_workspace(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer
    from ai_browser.brain.workflows import WorkflowRunner, WorkflowStore

    runner, _, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    home = tmp_path / "home"
    agents = AgentManager(home, claude=runner)
    workflows = WorkflowStore(home)
    workflows.save({"name": "Weekly report", "instructions": "Write the weekly report"})
    server = AppServer(home, agents, workflows=workflows, runner=WorkflowRunner(workflows, agents))
    url = await server.start()
    research = server.workspaces.create("Research")
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            created = await answer_to(ws, {"type": "workflow_run", "slug": "weekly-report", "text": "",
                                           "workspace": research["id"], "request": "r1"})
            assert agents.agents[created["id"]].workspace == research["id"]
    finally:
        await agents.close_all()
        await server.stop()
