"""Several Claude agents at once: the agent manager, with the fake claude."""

import asyncio
import json

from test_bridge import EVENTS

SLOW = [EVENTS[0], {"sleep": 1}, *EVENTS[1:]]


async def settle(manager, predicate, seconds=10):
    for _ in range(int(seconds * 20)):
        if predicate(manager.snapshot()["agents"]):
            return True
        await asyncio.sleep(0.05)
    return False


def state(agents, agent_id):
    return next((agent["state"] for agent in agents if agent["id"] == agent_id), None)


def drain(queue):
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


def sent_to_claude(log):
    lines = [json.loads(line) for line in log.read_text().splitlines()]
    return [line for line in lines if isinstance(line, dict)]


async def test_three_agents_work_at_once_and_a_fourth_waits(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager

    runner, log, script = fake_claude
    script.write_text(json.dumps(SLOW))
    manager = AgentManager(tmp_path / "home", claude=str(runner), max_working=3)
    try:
        for n in range(4):
            await manager.create(f"task {n}")
        assert await settle(manager, lambda agents: sorted(a["state"] for a in agents)
                            == ["waiting", "working", "working", "working"])
        assert await settle(manager, lambda agents: all(a["state"] == "your_turn" for a in agents))
        assert sum(line.startswith("[") for line in log.read_text().splitlines()) == 4  # one Claude Code each
    finally:
        await manager.close_all()


async def test_stop_leaves_the_others_working(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager

    runner, _, script = fake_claude
    script.write_text(json.dumps([EVENTS[0], EVENTS[1], {"sleep": 3}, *EVENTS[2:]]))
    manager = AgentManager(tmp_path / "home", claude=str(runner))
    try:
        first = await manager.create("one")
        await manager.create("two")
        assert await settle(manager, lambda agents: all(a["state"] == "working" for a in agents))
        await asyncio.sleep(0.5)  # both are mid-answer
        await manager.stop(first.id)
        assert await settle(manager, lambda agents: state(agents, "a1") == "stopped", 2)
        assert state(manager.snapshot()["agents"], "a2") == "working"
        assert first.bridge._process.returncode is None  # Claude Code keeps running, and so do its tabs
        assert await settle(manager, lambda agents: state(agents, "a2") == "your_turn")
    finally:
        await manager.close_all()


async def test_a_crashed_agent_leaves_the_others_working(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager

    runner, _, script = fake_claude
    script.write_text(json.dumps({"crash": [EVENTS[0], {"exit": 3}], "default": SLOW}))
    manager = AgentManager(tmp_path / "home", claude=str(runner))
    try:
        await manager.create("please crash now")
        await manager.create("all good")
        assert await settle(manager, lambda agents: state(agents, "a1") == "failed"
                            and state(agents, "a2") == "your_turn")
        failed = next(agent for agent in manager.snapshot()["agents"] if agent["id"] == "a1")
        assert "stopped unexpectedly" in failed["status"]
    finally:
        await manager.close_all()


async def test_close_ends_the_agent_and_closes_only_its_own_tabs(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager

    runner, _, script = fake_claude
    script.write_text(json.dumps(EVENTS))
    closed = []

    async def close_tabs(targets):
        closed.append(list(targets))

    manager = AgentManager(tmp_path / "home", claude=str(runner), close_tabs=close_tabs)
    queue = manager.subscribe()
    try:
        agent = await manager.create("one")
        assert await settle(manager, lambda agents: state(agents, "a1") == "your_turn")
        manager.tab_event("a1", "tab_opened", "T1")
        manager.tab_event("a1", "tab_opened", "U1", adopted=True)
        await manager.close("a1")
        assert closed == [["T1"]] and manager.snapshot()["agents"] == []
        assert agent.bridge._process is None
        assert {"type": "agent_closed", "id": "a1"} in drain(queue)
    finally:
        await manager.close_all()


async def test_a_message_to_a_busy_agent_waits_for_its_turn(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager

    runner, log, script = fake_claude
    script.write_text(json.dumps(SLOW))
    manager = AgentManager(tmp_path / "home", claude=str(runner))
    queue = manager.subscribe()
    try:
        await manager.create("one")
        assert await settle(manager, lambda agents: state(agents, "a1") == "working")
        await manager.send("a1", "and then this")
        assert await settle(manager, lambda _: sum(e["type"] == "done" for e in manager.events_of("a1")) == 2)
        assert {"type": "agent_event", "id": "a1", "event": {"type": "queued", "text": "and then this"}} in drain(queue)
        users = [line["message"]["content"] for line in sent_to_claude(log) if line.get("type") == "user"]
        assert users == ["one", "and then this"]
        assert state(manager.snapshot()["agents"], "a1") == "your_turn"
    finally:
        await manager.close_all()


async def test_names_colours_skills_and_models(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS))
    manager = AgentManager(tmp_path / "home", claude=str(runner))
    task = "please check every page of the shop for broken links and layout problems"
    try:
        first = await manager.create(task)
        second = await manager.create("two", skills=["ai-browser:website-qa"])
        assert len(first.name) <= 40 and task.startswith(first.name) and task[len(first.name)] == " "
        assert (first.color, second.color) == ("blue", "green")
        assert await settle(manager, lambda agents: all(a["state"] == "your_turn" for a in agents))
        manager.set_model("a1", "haiku")
        await manager.send("a1", "again")
        assert await settle(manager, lambda _: sum(e["type"] == "done" for e in manager.events_of("a1")) == 2)
        sent = sent_to_claude(log)
        assert {"subtype": "set_model", "model": "haiku"} in [line.get("request") for line in sent]
        assert any(line.get("type") == "user" and line["message"]["content"].startswith(
            "Load and use these skills with load_skill: ai-browser:website-qa") for line in sent)
    finally:
        await manager.close_all()


def test_agent_names_stay_readable_with_addresses_in_the_task():
    from ai_browser.app.agents import _name

    assert _name("Open https://shop.example.com/products/shoes and list the prices") == \
        "Open shop.example.com/products/shoes"  # no scheme, no dangling "and"
    assert _name("Open http://localhost:61257/qa/index.html and list the link texts") == \
        "Open localhost:61257/qa/index.html"
    long = _name("https://example.com/a/very/long/path/that/goes/on/and/on/forever")
    assert len(long) <= 40 and long.endswith("…") and long.startswith("example.com/a/very")


CHECK = {"agent": "a1", "kind": "check", "target": "T1", "adopted": False, "check": "google", "site": "www.google.com"}


def users(log):
    return [line["message"]["content"] for line in sent_to_claude(log) if line.get("type") == "user"]


async def test_a_bot_check_makes_the_agent_need_you_until_continue(fake_claude, tmp_path):
    from ai_browser.app.agents import CONTINUE_TEXT, AgentManager
    from ai_browser.checks import KINDS

    runner, log, script = fake_claude
    script.write_text(json.dumps(SLOW))
    manager = AgentManager(tmp_path / "home", claude=str(runner))
    feed = manager.subscribe()
    try:
        agent = await manager.create("Flights to Manila")
        manager.tab_event(agent.id, "tab_opened", "T1")
        assert await settle(manager, lambda agents: state(agents, "a1") == "working")
        manager.check_event(agent.id, CHECK)
        assert agent.state == "needs_you" and agent.public()["check"]["what"] == KINDS["google"]
        requests = [message for message in drain(feed) if message["type"] == "check_request"]
        assert requests == [{"type": "check_request", "agent": "a1", "name": "Flights to Manila",
                             "site": "www.google.com", "what": KINDS["google"], "target": "T1", "live": None}]
        manager.check_event(agent.id, CHECK)  # the same hold reported again: no second request
        assert not [message for message in drain(feed) if message["type"] == "check_request"]
        assert await settle(manager, lambda _: any(e["type"] == "done" for e in manager.events_of("a1")))
        await asyncio.sleep(0.2)
        assert agent.state == "needs_you"  # the turn ended while the check waits: not "your turn"
        await manager.continue_check(agent.id)
        assert agent.check is None
        assert await settle(manager, lambda _: sum(e["type"] == "done" for e in manager.events_of("a1")) == 2)
        assert users(log) == ["Flights to Manila", CONTINUE_TEXT]
        assert state(manager.snapshot()["agents"], "a1") == "your_turn"
    finally:
        await manager.close_all()


async def test_a_tool_answered_during_a_check_keeps_the_agent_needing_you(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager

    runner, _, script = fake_claude
    script.write_text(json.dumps([EVENTS[0], {"ask_permission": {"tool_name": "mcp__ai-browser__open",
                                                                 "input": {"url": "https://example.com"}}},
                                  {"sleep": 1}, EVENTS[-1]]))
    manager = AgentManager(tmp_path / "home", claude=str(runner))
    try:
        agent = await manager.create("look up flights")
        assert await settle(manager, lambda _: agent.permission is not None)
        manager.check_event(agent.id, CHECK)
        manager.answer_permission(agent.id, agent.permission["request"], "once")
        assert await settle(manager, lambda _: agent.permission is None)
        assert agent.state == "needs_you" and agent.check is not None
        assert await settle(manager, lambda _: any(e["type"] == "done" for e in manager.events_of(agent.id)))
        await asyncio.sleep(0.2)
        assert agent.state == "needs_you"
    finally:
        await manager.close_all()


async def test_skip_closes_only_the_agents_own_tab_and_tells_it_so(fake_claude, tmp_path):
    from ai_browser.app.agents import SKIP_TEXT, AgentManager

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS))
    closed = []

    async def close_tabs(targets):
        closed.append(list(targets))

    manager = AgentManager(tmp_path / "home", claude=str(runner), close_tabs=close_tabs)
    try:
        own, mine, sandboxed = [await manager.create(name) for name in ("own tab", "the user's tab", "qa sandbox")]
        assert await settle(manager, lambda agents: all(a["state"] == "your_turn" for a in agents))
        manager.tab_event(own.id, "tab_opened", "T1")
        manager.tab_event(mine.id, "tab_opened", "U1", adopted=True)
        manager.tab_event(sandboxed.id, "tab_opened", "Q1")
        manager.check_event(own.id, {**CHECK, "target": "T1"})
        manager.check_event(mine.id, {**CHECK, "target": "U1", "adopted": True})
        manager.check_event(sandboxed.id, {**CHECK, "target": "Q1", "live": "http://127.0.0.1:8770/live?token=abc"})
        await manager.skip_check(mine.id)
        await manager.skip_check(sandboxed.id)
        assert closed == [] and mine.check is not None and sandboxed.check is not None  # never the user's, nor QA's
        await manager.skip_check(own.id)
        assert closed == [["T1"]] and own.check is None
        assert await settle(manager, lambda _: sum(e["type"] == "done" for e in manager.events_of(own.id)) == 2)
        assert users(log).count(SKIP_TEXT) == 1
    finally:
        await manager.close_all()


async def test_the_check_clears_when_the_engine_says_so_or_on_stop(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager

    runner, _, script = fake_claude
    script.write_text(json.dumps(EVENTS))
    manager = AgentManager(tmp_path / "home", claude=str(runner))
    try:
        agent = await manager.create("one")
        assert await settle(manager, lambda agents: state(agents, "a1") == "your_turn")
        manager.check_event(agent.id, {**CHECK, "check": "dragon"})  # not one of ours: ignored
        assert agent.check is None and agent.state == "your_turn"
        manager.check_event(agent.id, CHECK)
        manager.check_cleared(agent.id, "OTHER", "solved")  # another tab's: nothing changes
        assert agent.check is not None and agent.state == "needs_you"
        manager.check_cleared(agent.id, "T1", "solved")
        assert agent.check is None and agent.state == "your_turn"
        manager.check_event(agent.id, CHECK)
        await manager.stop(agent.id)
        assert agent.check is None and agent.state == "stopped"
    finally:
        await manager.close_all()


async def test_continue_pressed_twice_sends_one_message(fake_claude, tmp_path):
    from ai_browser.app.agents import CONTINUE_TEXT, AgentManager

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS))
    manager = AgentManager(tmp_path / "home", claude=str(runner))
    try:
        agent = await manager.create("one")
        assert await settle(manager, lambda agents: state(agents, "a1") == "your_turn")
        manager.check_event(agent.id, CHECK)
        await asyncio.gather(manager.continue_check(agent.id), manager.continue_check(agent.id))
        assert await settle(manager, lambda _: sum(e["type"] == "done" for e in manager.events_of("a1")) == 2)
        await asyncio.sleep(0.3)
        assert users(log).count(CONTINUE_TEXT) == 1
    finally:
        await manager.close_all()
