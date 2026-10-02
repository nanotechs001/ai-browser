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
