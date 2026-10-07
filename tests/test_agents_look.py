"""What the office shows of an agent (the new look): its latest action's badge, when its step started, each to-do's
times, when it finished, the first line of its last answer, the files it changed, and when a card started waiting. On
the fake claude, in a throwaway home."""

import time

from test_agents_powers import manager
from test_app_server import wait_for
from test_bridge import EVENTS
from test_bridge_powers import INIT, RESULT, ask, result, use


async def test_the_badge_the_answer_and_when_it_finished(fake_claude, tmp_path):
    agents, _ = manager(fake_claude, tmp_path, EVENTS)  # a click on the page, the words "Opening", then done
    try:
        agent = await agents.create("fix the footer")
        await wait_for(lambda: agent.state == "your_turn")
        row = agents.snapshot()["agents"][0]
        assert row["badge"] == "Browser Agent" and row["result"] == "Opening"
        assert isinstance(row["finished"], float) and row["finished"] >= row["created"] - 1
        assert isinstance(row["step_since"], float) and row["files"] == []
    finally:
        await agents.close_all()


async def test_finished_is_cleared_while_it_works_again(fake_claude, tmp_path):
    agents, _ = manager(fake_claude, tmp_path, EVENTS)
    try:
        agent = await agents.create("one")
        await wait_for(lambda: agent.state == "your_turn")
        feed = agents.subscribe()
        await agents.send(agent.id, "two")
        await wait_for(lambda: agent.state == "your_turn")
        rows = []
        while not feed.empty():
            message = feed.get_nowait()
            if message["type"] == "agent":
                rows.append(message["agent"])
        assert any(row["state"] == "working" and row["finished"] is None for row in rows)
        assert rows[-1]["state"] == "your_turn" and isinstance(rows[-1]["finished"], float)
    finally:
        await agents.close_all()


async def test_each_to_do_keeps_when_it_started_and_how_long_it_took(fake_claude, tmp_path):
    first = {"todos": [{"content": "Read the code", "status": "in_progress", "activeForm": "Reading the code"},
                       {"content": "Fix the bug", "status": "pending", "activeForm": "Fixing the bug"}]}
    second = {"todos": [{"content": "Read the code", "status": "completed", "activeForm": "Reading the code"},
                        {"content": "Fix the bug", "status": "in_progress", "activeForm": "Fixing the bug"}]}
    agents, _ = manager(fake_claude, tmp_path, [INIT, use("t1", "TodoWrite", first), {"sleep": 0.5},
                                                use("t2", "TodoWrite", second), {"sleep": 0.2}, RESULT])
    try:
        agent = await agents.create("fix it")
        await wait_for(lambda: agent.state == "your_turn")
        read, fix = agent.todos
        assert read["status"] == "completed" and 0.3 <= read["took"] <= 5
        assert fix["started"] >= read["started"] and fix["took"] is None
        assert agent.step_since == fix["started"]  # the step at work now
    finally:
        await agents.close_all()


async def test_the_files_it_changed_are_kept_once_each(fake_claude, tmp_path):
    edit = {"file_path": "/x/app.py", "old_string": "a", "new_string": "b"}
    agents, _ = manager(fake_claude, tmp_path, [
        INIT, use("e1", "Edit", edit), result("e1"), use("w1", "Write", {"file_path": "/x/new.txt", "content": "x"}),
        result("w1", error=True), use("w2", "Write", {"file_path": "/x/notes.md", "content": "x"}, parent="s1"),
        result("w2", parent="s1"), use("e2", "Edit", edit), result("e2"), RESULT])
    try:
        agent = await agents.create("fix it")
        await wait_for(lambda: agent.state == "your_turn")
        assert agent.files == ["/x/notes.md", "/x/app.py"]  # a failed write isn't a change; one path once, newest last
    finally:
        await agents.close_all()


async def test_a_card_says_since_when_it_waits(fake_claude, tmp_path):
    agents, _ = manager(fake_claude, tmp_path, [INIT, ask("Bash", {"command": "npm test"}), {"sleep": 0.5}, RESULT])
    try:
        before = time.time()
        agent = await agents.create("test it")
        await wait_for(lambda: agent.permission is not None)
        assert before - 1 <= agent.permission["since"] <= time.time() + 1
        assert agent.public()["finished"] is None  # it waits for the user: not finished
    finally:
        await agents.close_all()
