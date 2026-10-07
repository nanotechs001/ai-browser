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


def said(text):
    """Claude Code's answer streaming in: the words, one delta."""
    return {"type": "stream_event", "event": {"type": "content_block_delta",
                                              "delta": {"type": "text_delta", "text": text}}}


WHOLE = {"type": "assistant", "message": {"content": [{"type": "text", "text": "x"}]}}  # a whole message: its end


async def test_a_stopped_answer_leaves_nothing_in_the_next_turns_result(fake_claude, tmp_path):
    agents, _ = manager(fake_claude, tmp_path, {
        "default": [INIT, said("Half of the answer\nand more"), {"sleep": 30}],  # Stop comes before it is whole
        "second": [INIT, said("Whole answer\nwith details"), WHOLE, RESULT]})
    try:
        agent = await agents.create("fix it")
        await wait_for(lambda: agent.words.startswith("Half"))
        await agents.stop(agent.id)
        await wait_for(lambda: agent.state == "stopped")
        assert agent.public()["result"] == "Half of the answer"  # the partial is the newest answer there is
        await agents.send(agent.id, "second try")
        await wait_for(lambda: agent.state == "your_turn")
        assert agent.public()["result"] == "Whole answer"  # nothing of the first turn's words glued on
    finally:
        await agents.close_all()


async def test_the_newest_partial_beats_an_older_whole_answer_and_a_quiet_turn_keeps_it(fake_claude, tmp_path):
    agents, _ = manager(fake_claude, tmp_path, {
        "default": [INIT, said("First answer\nin full"), WHOLE, RESULT],
        "partial": [INIT, said("Newer partial\nonly"), {"sleep": 30}],
        "quiet": [INIT, RESULT]})  # a turn that says nothing at all
    try:
        agent = await agents.create("fix it")
        await wait_for(lambda: agent.state == "your_turn")
        assert agent.public()["result"] == "First answer"
        await agents.send(agent.id, "partial one")
        await wait_for(lambda: agent.words.startswith("Newer"))
        await agents.stop(agent.id)
        await wait_for(lambda: agent.state == "stopped")
        assert agent.public()["result"] == "Newer partial"  # not the older whole message
        await agents.send(agent.id, "quiet one")
        await wait_for(lambda: agent.state == "your_turn")
        assert agent.public()["result"] == "First answer"  # said nothing: the last whole answer stays
    finally:
        await agents.close_all()


async def test_a_failed_turn_never_shows_the_last_turns_answer(fake_claude, tmp_path):  # the final review, F6
    resets = int(time.time()) + 3 * 3600
    agents, _ = manager(fake_claude, tmp_path, {
        "default": [INIT, said("First answer\nin full"), WHOLE, RESULT],
        "broken": [INIT, said("Half way there\nand more"), {"exit": 1}],  # it fails with words said
        "silent": [INIT, {"exit": 1}],  # it fails before a word
        "limited": [INIT, {"usage_limit": f"Claude AI usage limit reached|{resets}"}]})  # the account's limit
    try:
        agent = await agents.create("fix it")
        await wait_for(lambda: agent.state == "your_turn")
        assert agent.public()["result"] == "First answer"
        for text, words in (("broken one", "Half way there"), ("silent one", ""), ("limited one", "")):
            before = len(agent.events)
            await agents.send(agent.id, text)
            await wait_for(lambda: agent.state == "failed"
                           and any(event["type"] in ("error", "limit") for event in list(agent.events)[before:]))
            assert agent.public()["result"] == words, text  # this turn's words, never the first turn's line
    finally:
        await agents.close_all()
