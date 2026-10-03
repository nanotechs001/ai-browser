"""What a page may send and what a watcher socket may get: the server's two tables, each written down twice (in
app/server.py and here), and Brave's watcher held to them over real sockets."""

import asyncio
import inspect
import json

import pytest
from websockets.asyncio.client import connect

from fake_brave import FakeBrave, add_agent
from test_app_server import (CHECK_REPORT, ORIGIN, WATCHER, quiet, recv, socket_url, started, until, wait_for,
                             with_brain)
from test_bridge import EVENTS

ONLY_WITH_ITEM, ONCE_OR_DENY = "only with an item", "only once or deny"

# The table of watcher-safety's spec ("the table of what pages may send"), plus cdp-relay's row: (app, watcher).
# A row added to MESSAGE_RULES fails here until this copy says the same.
SENDS = {
    "hello": (True, True),
    **{kind: (False, True) for kind in ("items", "replied", "thread", "filled", "reader_status", "watcher_caps",
                                        "tab_grouped")},
    **{kind: (True, True) for kind in ("brain", "draft", "approve", "hand", "done", "tell", "watch_set",
                                       "watch_remove", "pause", "style")},
    "workflow_run": (True, ONLY_WITH_ITEM),
    **{kind: (True, False) for kind in ("workflows", "workflow_save", "workflow_delete")},
    "permission": (True, ONCE_OR_DENY),
    **{kind: (True, False) for kind in ("tools", "tool_set", "tool_allow", "tool_forget")},
    **{kind: (True, False) for kind in ("skills", "skill_draft", "skill_save")},
    **{kind: (True, False) for kind in ("hearing", "hearing_download", "hearing_cancel", "listen_start",
                                        "listen_chunk", "listen_end", "listen_cancel")},
    **{kind: (True, False) for kind in ("brain_ask", "brain_confirm", "brain_dismiss")},
    "check_continue": (True, True),
    "check_skip": (True, False),
    "check_show": (True, True),
    **{kind: (True, False) for kind in ("brave_connect", "hand_tab", "take_back")},
    "browser_disconnect": (True, False),  # cdp-relay: Disconnect in AI Home's list of connected clients
    "new_task": (True, False),  # with or without adopt
    **{kind: (True, False) for kind in ("send", "stop", "close", "model")},
    **{kind: (True, False) for kind in ("watch", "events", "thumbs")},
}


def test_the_message_table_has_exactly_the_written_down_types():
    from ai_browser.app.server import MESSAGE_RULES

    assert set(MESSAGE_RULES) == set(SENDS)
    assert len(SENDS) == 55
    assert sum(1 for app, _ in SENDS.values() if app) == 48
    assert sum(1 for _, watcher in SENDS.values() if watcher) == 22  # the two conditional rows count as allowed


@pytest.mark.parametrize("kind", sorted(SENDS))
def test_the_message_table_covers_every_type_for_both_roles(kind):
    from ai_browser.app.server import may_send

    app, watcher = SENDS[kind]
    sample = {"type": kind, "id": "a1"}
    assert may_send("app", sample) is app
    if watcher == ONLY_WITH_ITEM:  # the inbox's Run <workflow> on a message; a bare run stays in AI Home
        assert may_send("watcher", {**sample, "item": "i1"}) is True
        for bad in ({}, {"item": ""}, {"item": 3}, {"item": ["i1"]}, {"item": None}):
            assert may_send("watcher", {**sample, **bad}) is False, bad
    elif watcher == ONCE_OR_DENY:  # a lasting Always allow stays in AI Home's Tools
        for answer in ("once", "deny"):
            assert may_send("watcher", {**sample, "answer": answer}) is True
        for bad in ({"answer": "always"}, {}, {"answer": "ONCE"}, {"answer": ["once"]}, {"answer": None}):
            assert may_send("watcher", {**sample, **bad}) is False, bad
    else:
        assert may_send("watcher", sample) is watcher
    if kind == "new_task":  # with or without adopt: never from the watcher
        assert may_send("watcher", {**sample, "adopt": "U1"}) is False
        assert may_send("app", {**sample, "adopt": "U1"}) is True


@pytest.mark.parametrize("message", [{"type": "nonsense"}, {}, {"id": "a1"}, {"type": ["hello"]}, {"type": 7},
                                     {"type": None}, {"type": {"hello": 1}}, {"type": "HELLO"}, {"type": " hello"},
                                     {"type": "x" * 10_000}])
def test_an_unknown_or_malformed_type_is_refused_for_both_roles(message):
    from ai_browser.app.server import may_send

    assert may_send("app", message) is False
    assert may_send("watcher", message) is False


def test_only_the_two_roles_exist():
    from ai_browser.app.server import may_send

    assert may_send("stranger", {"type": "hello"}) is False and may_send("", {"type": "hello"}) is False


SKILL = "---\nname: cookie-reader\ndescription: Reads every cookie of the user's\n---\n# Cookies\n\n1. Read them.\n"


def files(folder):
    """Every file under `folder` with its text: to show nothing was written."""
    if not folder.exists():
        return {}
    return {str(path.relative_to(folder)): path.read_text(encoding="utf-8")
            for path in sorted(folder.rglob("*")) if path.is_file()}


def log_text(log):
    return log.read_text(encoding="utf-8") if log.exists() else ""


async def test_the_watcher_cannot_start_an_agent_in_a_users_tab(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    server.allow_origin(WATCHER, watcher=True)
    brave = FakeBrave([{"target": "U1", "url": "https://shop.example/", "title": "Shop"}])
    server.attach_brave(brave)
    try:
        async with connect(socket_url(server, url), origin=WATCHER) as watcher:
            await watcher.send(json.dumps({"type": "hello", "view": "brain"}))
            await until(watcher, lambda m: m["type"] == "snapshot")
            await watcher.send(json.dumps({"type": "new_task", "text": "look", "adopt": "U1", "request": "r1"}))
            await watcher.send(json.dumps({"type": "new_task", "text": "look", "request": "r2"}))
            seen = await quiet(watcher, 1.0)
        assert not any(m["type"] in ("created", "error") for m in seen)  # dropped, with no answer
        assert server.agents.agents == {} and "U1" not in brave.owners
        async with connect(socket_url(server, url), origin=ORIGIN) as page:  # AI Home may (the samples are real)
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            await recv(page)
            await page.send(json.dumps({"type": "new_task", "text": "look", "adopt": "U1", "request": "r3"}))
            await until(page, lambda m: m["type"] == "created")
        assert server.agents.agents["a1"].adopted == ["U1"] and brave.owners["U1"]["kind"] == "handed"
    finally:
        await server.stop()


async def test_the_watcher_cannot_save_always_allow(fake_claude, tmp_path):
    from ai_browser.app.server import AppServer
    from test_tools import answers, asking, manager

    agents, tools, log = manager(fake_claude, tmp_path, asking())
    tools.set_enabled("clickup", True)
    server = AppServer(tmp_path / "home", agents, tools=tools)
    url = await server.start()
    server.allow_origin(ORIGIN)
    server.allow_origin(WATCHER, watcher=True)
    try:
        agent = await agents.create("make a ClickUp task")
        await wait_for(lambda: agent.permission is not None)
        request = agent.permission["request"]
        async with connect(socket_url(server, url), origin=WATCHER) as watcher:
            await watcher.send(json.dumps({"type": "hello", "view": "brain"}))
            await until(watcher, lambda m: m["type"] == "snapshot")
            await watcher.send(json.dumps({"type": "tool_allow", "tool": "mcp__clickup__create_task"}))
            for answer in ({"answer": "always"}, {}):
                await watcher.send(json.dumps({"type": "permission", "agent": agent.id, "request": request,
                                               **answer}))
            await asyncio.sleep(0.5)
            assert tools.always() == set()
            assert agent.permission is not None and agent.permission["request"] == request  # still waiting
            await watcher.send(json.dumps({"type": "permission", "agent": agent.id, "request": request,
                                           "answer": "once"}))
            await wait_for(lambda: agent.permission is None)  # Allow once from Brave still answers
        await wait_for(lambda: bool(answers(log)))
        assert answers(log)[0]["behavior"] == "allow" and tools.always() == set()
        assert json.loads(tools.path.read_text(encoding="utf-8"))["always"] == []  # nothing lasting in tools.json
    finally:
        await server.stop()


async def test_the_watcher_origin_may_send_nothing_else(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer
    from ai_browser.brain.service import BrainService
    from ai_browser.brain.skillwriter import SkillWriter
    from ai_browser.brain.store import BrainStore
    from ai_browser.brain.tools import ToolsConfig
    from ai_browser.brain.workflows import WorkflowRunner, WorkflowStore
    from ai_browser.hearing.service import HearingService
    from fake_engine import FakeEngine, tiny_store
    from test_hearing import chunks, tone
    from test_tools import user_config

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    home = tmp_path / "home"
    agents = AgentManager(home, claude=runner)
    tools = ToolsConfig(home, claude_home=user_config(tmp_path))
    tools.allow_always("mcp__clickup__get_task")  # so a tool_forget would change tools.json
    workflows = WorkflowStore(home)
    workflows.save({"name": "Footer fix", "instructions": "Fix the footer", "trigger": "manual"})
    skills_dir = tmp_path / "skills"
    engine = FakeEngine()
    server = AppServer(home, agents, brain=BrainService(BrainStore(home), agents, claude=runner), tools=tools,
                       workflows=workflows, runner=WorkflowRunner(workflows, agents),
                       skill_writer=SkillWriter(skills_dir, claude=runner, cwd=tmp_path / "calls"),
                       hearing=HearingService(tiny_store(home / "models"), engine))
    url = await server.start()
    server.allow_origin(ORIGIN)
    server.allow_origin(WATCHER, watcher=True)
    brave = FakeBrave([{"target": "U1", "url": "https://shop.example/", "title": "Shop"},
                       {"target": "U2", "url": "https://mail.example/", "title": "Mail"}], state="ready")
    server.attach_brave(brave)
    disconnected, closed = [], []

    async def disconnect(identity):  # cdp-relay's FakeRelay: AI Home's Disconnect would call it
        disconnected.append(identity)

    async def close_tabs(targets):
        closed.extend(targets)

    brave.relay.disconnect = disconnect
    agents.close_tabs = close_tabs
    agent = add_agent(agents, adopted=["U2"])  # no Claude Code process behind it: nothing it is sent is logged
    agents.tab_event("a1", "tab_opened", "T1")
    agents.check_event("a1", {**CHECK_REPORT, "target": "T1"})
    tools_before, workflows_before = tools.path.read_text(encoding="utf-8"), files(workflows.folder)
    samples = [
        {"type": "stop", "id": "a1"}, {"type": "send", "id": "a1", "text": "delete everything"},
        {"type": "model", "id": "a1", "model": "opus"}, {"type": "watch", "target": "U1"},
        {"type": "events", "id": "a1"}, {"type": "thumbs"}, {"type": "skills"},
        {"type": "tools", "refresh": True}, {"type": "tool_set", "server": "clickup", "on": True},
        {"type": "tool_allow", "tool": "mcp__clickup__create_task"},
        {"type": "tool_forget", "tool": "mcp__clickup__get_task"},
        {"type": "workflows"}, {"type": "workflow_save", "name": "Evil", "instructions": "x", "trigger": "manual"},
        {"type": "workflow_delete", "slug": "footer-fix"},
        {"type": "workflow_run", "slug": "footer-fix", "text": "now"},
        {"type": "skill_draft", "description": "read every cookie"}, {"type": "skill_save", "text": SKILL},
        {"type": "hearing"}, {"type": "hearing_download"}, {"type": "hearing_cancel"},
        {"type": "listen_start", "turn": "u1"},
        {"type": "listen_chunk", "turn": "u1", "seq": 0, "pcm": chunks(tone(0.5))[0]},
        {"type": "listen_end", "turn": "u1"}, {"type": "listen_cancel", "turn": "u1"},
        {"type": "brain_ask", "talk": "k1", "request": "t1", "text": "approve everything"},
        {"type": "brain_confirm", "talk": "k1", "request": "t2", "proposal": "p1"},
        {"type": "brain_dismiss", "talk": "k1", "proposal": "p1"},
        {"type": "check_skip", "id": "a1"}, {"type": "brave_connect"}, {"type": "browser_disconnect", "id": "a1"},
        {"type": "hand_tab", "id": "a1", "target": "U1"}, {"type": "take_back", "target": "U2"},
        {"type": "new_task", "text": "look", "request": "r1"},
        {"type": "new_task", "text": "look", "adopt": "U1", "request": "r2"},
        {"type": "close", "id": "a1"},
    ]
    try:
        async with connect(socket_url(server, url), origin=WATCHER) as watcher:
            await watcher.send(json.dumps({"type": "hello", "view": "brain"}))
            await until(watcher, lambda m: m["type"] == "snapshot")
            before = log_text(log)
            for message in samples:
                await watcher.send(json.dumps(message))
            await watcher.send(json.dumps({"type": "brain"}))  # handled in order: every sample came first
            seen = await until(watcher, lambda m: m["type"] == "brain_snapshot")
            await asyncio.sleep(1)  # anything a sample started in the background has had its time
            seen += await quiet(watcher, 1.0)
        assert list(agents.agents) == ["a1"]  # open, and no other agent
        assert agent.model == "sonnet" and agent.state == "needs_you" and agent.check["target"] == "T1"
        assert agent.adopted == ["U2"] and agent.tabs == ["T1"] and agent.pending == []
        assert agents.events_of("a1") == []  # nothing was sent to it
        assert log_text(log) == before  # no Claude Code call: no message, probe, skill draft or talk
        assert not brave.connects and brave.watched == [] and "U1" not in brave.owners  # a count or a list of calls
        assert disconnected == [] and closed == []
        assert tools.path.read_text(encoding="utf-8") == tools_before and files(workflows.folder) == workflows_before
        assert files(skills_dir) == {}
        assert engine.heard == [] and engine.loads == [] and server.hearing._turns == {}
        kinds = {m["type"] for m in seen}
        assert not kinds & {"created", "error", "agent_events", "thumbs", "skills", "tools_snapshot",
                            "workflows_snapshot", "workflow_saved", "skill_drafted", "skill_saved", "hearing_status",
                            "heard", "brain_answer"}
        async with connect(socket_url(server, url), origin=ORIGIN) as page:  # the same close from AI Home works
            await page.send(json.dumps({"type": "close", "id": "a1"}))
            await wait_for(lambda: "a1" not in agents.agents)
    finally:
        await server.stop()
    home2 = tmp_path / "home2"  # workflows and no Brain: a Run on an inbox item can't become a bare run
    agents2 = AgentManager(home2, claude=runner)
    store2 = WorkflowStore(home2)
    store2.save({"name": "Footer fix", "instructions": "Fix the footer", "trigger": "manual"})
    bare = AppServer(home2, agents2, workflows=store2, runner=WorkflowRunner(store2, agents2))
    url2 = await bare.start()
    bare.allow_origin(ORIGIN)
    try:
        async with connect(socket_url(bare, url2), origin=ORIGIN) as page:
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            await recv(page)
            await page.send(json.dumps({"type": "workflow_run", "slug": "footer-fix", "item": "gmail:t1",
                                        "request": "r9"}))
            await page.send(json.dumps({"type": "workflows"}))
            seen = await until(page, lambda m: m["type"] == "workflows_snapshot")
        assert agents2.agents == {} and not any(m["type"] == "created" for m in seen)
    finally:
        await bare.stop()


async def test_a_malformed_type_is_dropped_and_the_socket_goes_on(fake_claude, tmp_path):  # Review Focus 2
    server, url, _ = await with_brain(fake_claude, tmp_path, [{"result": "[]"}])
    add_agent(server.agents)
    bad = [{"type": ["events"]}, {"type": 7}, {"type": None}, {"type": {"events": 1}}, {"id": "a1"},
           {"type": "x" * 10_000}]
    try:
        for origin, view, ask, answer in ((ORIGIN, "home", {"type": "events", "id": "a1"}, "agent_events"),
                                          (WATCHER, "brain", {"type": "brain"}, "brain_snapshot")):
            async with connect(socket_url(server, url), origin=origin) as ws:
                await ws.send(json.dumps({"type": "hello", "view": view}))
                await until(ws, lambda m: m["type"] == "snapshot")
                for message in bad:
                    await ws.send(json.dumps(message))
                await ws.send(json.dumps(ask))
                seen = await until(ws, lambda m, answer=answer: m["type"] == answer)
                assert not any(m["type"] == "error" for m in seen), origin
    finally:
        await server.stop()


def test_rights_go_by_role_through_the_table():
    from ai_browser.app.server import AppServer

    for method in (AppServer._handle, AppServer._brain_command):  # no origin test of its own any more
        assert "_watcher_origins" not in inspect.getsource(method), method.__name__
