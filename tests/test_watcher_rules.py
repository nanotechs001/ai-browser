"""What a page may send and what a watcher socket may get: the server's two tables, each written down twice (in
app/server.py and here), and Brave's watcher held to them over real sockets."""

import asyncio
import inspect
import json
import os
from pathlib import Path

import pytest
from websockets.asyncio.client import connect

from fake_brave import FakeBrave, add_agent
from test_app_server import (CHECK_REPORT, ORIGIN, WATCHER, quiet, recv, socket_url, started, until, wait_for,
                             with_brain)
from test_bridge import EVENTS

ONLY_WITH_ITEM, ONCE_OR_DENY = "only with an item", "only once or deny"

# The table of watcher-safety's spec, plus cdp-relay's and brain-delegation's rows: (app, watcher).
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
    "tell_confirm": (True, False), "tell_dismiss": (True, False),  # brain-delegation: Start/Send and Cancel on a card
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
    assert len(SENDS) == 57
    assert sum(1 for app, _ in SENDS.values() if app) == 50
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


async def test_show_me_from_the_watcher_brings_the_checks_tab_forward(fake_claude, tmp_path):
    server, url, _ = await with_brain(fake_claude, tmp_path, [{"result": "[]"}])
    brave = FakeBrave([{"target": "U1", "url": "https://shop.example/", "title": "Shop"}])
    server.attach_brave(brave)
    agents = server.agents
    for agent_id, live in (("a1", None), ("a3", "http://127.0.0.1:8770/live?token=abc")):
        add_agent(agents, agent_id)
        agents.tab_event(agent_id, "tab_opened", f"T{agent_id[1:]}")
        agents.check_event(agent_id, {**CHECK_REPORT, "target": f"T{agent_id[1:]}", "live": live})
    add_agent(agents, "a2", "Other", "green")  # no bot check
    try:
        async with connect(socket_url(server, url), origin=WATCHER) as watcher:
            await watcher.send(json.dumps({"type": "hello", "view": "watcher"}))
            await until(watcher, lambda m: m["type"] == "watch_list")
            for message in ({"type": "check_show", "id": "a2"},  # no check: nothing
                            {"type": "check_show", "id": "a3"},  # shown in the live view: nothing here
                            {"type": "check_show", "id": "nobody"},
                            {"type": "watch", "target": "U1"},  # a tab the watcher names: never
                            {"type": "check_show", "id": "a1"}):
                await watcher.send(json.dumps(message))
            await watcher.send(json.dumps({"type": "brain"}))  # handled in order: every message above came first
            await until(watcher, lambda m: m["type"] == "brain_snapshot")
        assert brave.watched == ["T1"] and agents.agents["a1"].check is not None  # Show me answers nothing
        async with connect(socket_url(server, url), origin=ORIGIN) as page:  # AI Home's own Watch still names a tab
            await page.send(json.dumps({"type": "watch", "target": "U1"}))
            await wait_for(lambda: brave.watched == ["T1", "U1"])
    finally:
        await server.stop()


async def test_show_me_with_no_tab_source_does_nothing(fake_claude, tmp_path):  # Review Focus 5
    server, url, _ = await with_brain(fake_claude, tmp_path, [{"result": "[]"}])  # no browser link attached
    agents = server.agents
    add_agent(agents)
    agents.tab_event("a1", "tab_opened", "T1")
    agents.check_event("a1", {**CHECK_REPORT, "target": "T1"})
    try:
        async with connect(socket_url(server, url), origin=WATCHER) as watcher:
            await watcher.send(json.dumps({"type": "hello", "view": "watcher"}))
            await until(watcher, lambda m: m["type"] == "watch_list")
            await watcher.send(json.dumps({"type": "check_show", "id": "a1"}))
            await watcher.send(json.dumps({"type": "check_continue", "id": "a1"}))  # the socket goes on
            await wait_for(lambda: agents.agents["a1"].check is None)
    finally:
        await server.stop()


RECEIVES = {"ping", "error", "watcher_hello", "watch_list", "notify", "permission_request", "check_request",
            "group_tab", "ungroup_tabs", "open_thread", "fill_reply",  # the worker's
            "snapshot", "agent", "agent_closed", "brain_snapshot", "brain_item", "brain_item_gone",
            "brain_state"}  # the Brain page's
NEVER = {"tabs", "thumb", "thumbs", "sessions", "browser", "agent_event", "agent_events", "created", "brain_activity",
         "brain_answer", "hearing_status", "heard", "tools_snapshot", "workflows_snapshot", "workflow_saved", "skills",
         "skill_drafted", "skill_diff", "skill_saved",
         "browser_clients",  # cdp-relay's list of connected clients
         "a_type_added_later"}
AGENT_ROW = {"id": "a1", "name": "Fix the footer", "color": "blue", "model": "sonnet", "state": "needs_you",
             "status": "", "last_action": "", "tabs": ["T1"], "adopted": ["U2"], "working_tab": "T1",
             "loaded_skills": [], "seconds": 0, "cost": 0, "created": 1.0,
             "permission": {"request": "r1", "server": "clickup", "tool": "mcp__clickup__create_task", "input": {}},
             "check": {"target": "T1", "live": None}}


def test_what_the_watcher_receives_is_a_fixed_list():
    from ai_browser.app.server import WATCHER_AGENT_FIELDS, WATCHER_RECEIVES, for_watcher

    assert WATCHER_RECEIVES == RECEIVES and len(RECEIVES) == 18
    assert WATCHER_AGENT_FIELDS == ("id", "name", "color", "state", "permission")
    for kind in RECEIVES | NEVER:
        assert (for_watcher({"type": kind}) is not None) is (kind in RECEIVES), kind
    row = {key: AGENT_ROW[key] for key in WATCHER_AGENT_FIELDS}
    snapshot = {"type": "snapshot", "agents": [AGENT_ROW], "tabs": [{"target": "U1"}], "sessions": [],
                "browser": {"kind": "brave"}, "skills_summary": {}, "max_working": 3, "default_model": "sonnet",
                "browser_clients": [], "tab_scope": {"profile": "watcher", "elsewhere": 1}}
    agent = {"type": "agent", "agent": AGENT_ROW}
    check = {"type": "check_request", "agent": "a1", "name": "Fix the footer", "site": "www.google.com",
             "what": "a check", "target": "T1", "live": None}
    before = json.dumps([snapshot, agent, check])
    assert for_watcher(snapshot) == {"type": "snapshot", "agents": [row]}
    assert for_watcher(agent) == {"type": "agent", "agent": row}
    assert for_watcher(check) == {key: value for key, value in check.items() if key != "target"}
    assert json.dumps([snapshot, agent, check]) == before  # _send_all puts one dict in every queue
    for kind in ("watcher_hello", "watch_list", "notify", "open_thread", "fill_reply", "group_tab", "ungroup_tabs",
                 "permission_request", "check_request"):  # everything _to_watcher sends
        assert for_watcher({"type": kind}) is not None, kind
    assert for_watcher({"type": ["agent"]}) is None and for_watcher({}) is None
    assert for_watcher({"type": "snapshot"}) == {"type": "snapshot", "agents": []}


async def test_watcher_sockets_get_no_target_ids(fake_claude, tmp_path):
    from ai_browser.app.server import WATCHER_RECEIVES

    server, url, _ = await with_brain(fake_claude, tmp_path, [{"result": "[]"}])
    brave = FakeBrave([{"target": "U1-7f3a", "url": "https://shop.example/", "title": "Shop"},
                       {"target": "U2-7f3a", "url": "https://mail.example/", "title": "Mail"}])
    server.attach_brave(brave)
    agents = server.agents
    agent = add_agent(agents, adopted=["U2-7f3a"])
    agents.tab_event("a1", "working_tab", "T1-7f3a")
    server.sessions["cc-x"] = {"id": "cc-x", "name": "Claude Code", "color": "orange", "tabs": ["S1-7f3a"],
                               "pid": os.getpid()}
    brave.relay.rows = [{"id": "a1", "kind": "agent", "number": 1, "tabs": 1, "connected": True, "cut_off": False}]
    try:
        async with (connect(socket_url(server, url), origin=WATCHER) as worker,
                    connect(socket_url(server, url), origin=WATCHER) as page,
                    connect(socket_url(server, url), origin=ORIGIN) as home):
            await worker.send(json.dumps({"type": "hello", "view": "watcher"}))
            got = {"worker": await until(worker, lambda m: m["type"] == "watch_list")}
            await page.send(json.dumps({"type": "hello", "view": "brain"}))
            got["page"] = await until(page, lambda m: m["type"] == "snapshot")
            await home.send(json.dumps({"type": "hello", "view": "home"}))
            got["home"] = await until(home, lambda m: m["type"] == "snapshot")
            agents.check_event("a1", {**CHECK_REPORT, "target": "T1-7f3a"})
            agent.permission = {"request": "r1", "server": "clickup", "tool": "mcp__clickup__create_task",
                                "input": {"name": "Fix footer"}}
            agents._changed(agent)
            agents._broadcast({"type": "permission_request", "agent": "a1", **agent.permission})
            brave.changed()
            server._sessions_changed()
            server._clients_changed()  # cdp-relay's list of what uses Brave: AI Home's only
            server._send_all({"type": "thumb", "id": "a1", "jpeg": "eHh4"})
            for name, ws in (("worker", worker), ("page", page), ("home", home)):
                got[name] += await quiet(ws, 1.0)
        for name in ("worker", "page"):
            assert "-7f3a" not in json.dumps(got[name]), name
            assert {m["type"] for m in got[name]} <= WATCHER_RECEIVES, name
            assert not any(m["type"] == "browser_clients" for m in got[name]), name
        assert "browser_clients" not in next(m for m in got["page"] if m["type"] == "snapshot")
        rows = [m["agent"] for m in got["page"] if m["type"] == "agent" and m["agent"].get("id") == "a1"]
        assert rows and rows[-1]["permission"]["request"] == "r1"  # the Brain page's card still works
        assert {"check_request", "permission_request"} <= {m["type"] for m in got["worker"]}
        assert any(m["type"] == "tabs" and any(tab["target"] == "U1-7f3a" for tab in m["tabs"])
                   for m in got["home"])  # AI Home still gets the list
        assert "browser_clients" in next(m for m in got["home"] if m["type"] == "snapshot")
        assert any(m["type"] == "browser_clients" and m["clients"] for m in got["home"])  # and the clients
    finally:
        await server.stop()


def test_only_the_role_reads_the_watchers_origins():
    from ai_browser.app.server import AppServer

    readers = sorted(name for name, member in vars(AppServer).items()
                     if inspect.isfunction(member) and "_watcher_origins" in inspect.getsource(member))
    assert readers == ["__init__", "_mismatch", "_role", "_socket", "allow_origin"]  # the rest asks _role


def test_the_readme_says_what_ai_home_lists_and_where_always_allow_is():
    text = " ".join((Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8").split())
    assert ("**Tabs:** the web tabs of the Brave profile the watcher is in (without the watcher, the profile you used "
            "last), each marked with whose it is") in text
    assert "Other profiles and private windows are only counted, never listed." in text
    assert ("The watcher's Brain page in Brave shows them with **Allow once** and **Deny** only, because Always "
            "allow is kept for AI Home's Tools.") in text
    assert "and the watcher's Brain page all show the tool" not in text
    assert ("AI Home shows the ones in the agents' profile (other profiles and private windows only as a count)"
            in text)
