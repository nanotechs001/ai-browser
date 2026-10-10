"""Agents on AI accounts: each runs on its account (its folder, never an API key), a signed-out account stops it with
a plain line, and a usage limit pauses it. With the fake claude, never the user's own Claude Code folder."""

import asyncio
import json
import os
import time
from pathlib import Path

import pytest

from fake_accounts import sign_in, sign_out
from test_agents import settle, state
from test_app_server import told
from test_bridge import EVENTS

RESETS = int(time.time()) + 3 * 3600
API = {"ANTHROPIC_API_KEY": "sk-test", "ANTHROPIC_AUTH_TOKEN": "token-test"}
LIMITED = [EVENTS[0], {"sleep": 0.5}, EVENTS[1],
           {"rate_limit": {"status": "rejected", "resetsAt": RESETS, "rateLimitType": "five_hour"}},
           {"usage_limit": f"Claude AI usage limit reached|{RESETS}"}]


def given(log):
    """The environment and folder the fake claude last started with."""
    return json.loads(Path(f"{log}.env").read_text(encoding="utf-8"))


def argvs(log):
    """Every Claude Code process started, as its argv."""
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return [json.loads(line) for line in lines if line.startswith("[")]


def rig(fake_claude, tmp_path, script=EVENTS):
    """An AgentManager on accounts: Default (signed in by conftest) and Work (signed in)."""
    from ai_browser.accounts import Accounts
    from ai_browser.app.agents import AgentManager

    runner, log, script_file = fake_claude
    script_file.write_text(json.dumps(script), encoding="utf-8")
    home = tmp_path / "home"
    accounts = Accounts(home, claude=runner)
    work = accounts.add("Work")
    sign_in(work.folder)
    return AgentManager(home, claude=runner, accounts=accounts), accounts, work, log


async def test_an_agent_runs_on_its_account_and_keeps_it(fake_claude, tmp_path, monkeypatch):
    for key, value in API.items():
        monkeypatch.setenv(key, value)
    manager, accounts, work, log = rig(fake_claude, tmp_path)
    try:
        first = await manager.create("check the shop", account=work.id)
        assert await settle(manager, lambda agents: state(agents, first.id) == "your_turn")
        env = given(log)
        assert env["CLAUDE_CONFIG_DIR"] == work.folder
        assert env["ANTHROPIC_API_KEY"] is None and env["ANTHROPIC_AUTH_TOKEN"] is None
        assert first.public()["account"] == {"id": work.id, "name": "Work"} and first.public()["limit"] is None
        assert first.public()["moved"] == "" and "task" not in first.public()
        second = await manager.create("check the blog")  # the default for new agents: Default
        assert await settle(manager, lambda agents: state(agents, second.id) == "your_turn")
        assert given(log)["CLAUDE_CONFIG_DIR"] == os.environ["CLAUDE_CONFIG_DIR"]
        assert second.account == {"id": "default", "name": "Default"}
        accounts.set_default(work.id)
        third = await manager.create("check the cart")
        assert third.account == {"id": work.id, "name": "Work"}
        accounts.set_default("default")  # an agent keeps its account until it is moved
        assert first.account["id"] == third.account["id"] == work.id
        with pytest.raises(ValueError, match="isn't in Settings"):
            await manager.create("check the stock", account="acct-000000")
        assert sorted(manager.agents) == ["a1", "a2", "a3"]  # a refused account leaves no agent
    finally:
        await manager.close_all()


async def test_a_signed_out_account_is_never_swapped_for_another(fake_claude, tmp_path, monkeypatch):  # Review Focus 2
    from ai_browser import accounts as module

    monkeypatch.setattr(module, "STATUS_TTL", 0)  # every start asks again
    manager, _, work, log = rig(fake_claude, tmp_path)
    sign_out(work.folder)  # it signed out after the page was drawn
    try:
        agent = await manager.create("check the shop", account=work.id)
        assert await settle(manager, lambda agents: state(agents, agent.id) == "failed")
        assert agent.status == "Work isn't signed in: sign in from Settings → Accounts"
        assert argvs(log) == [] and agent.account["id"] == work.id  # nothing ran, on no other account
        sign_in(work.folder)
        await manager.send(agent.id, "go on")
        assert await settle(manager, lambda agents: state(agents, agent.id) == "your_turn")
        assert len(argvs(log)) == 1 and given(log)["CLAUDE_CONFIG_DIR"] == work.folder
    finally:
        await manager.close_all()


async def test_a_limit_pauses_the_agent_and_keeps_its_partial_answer(fake_claude, tmp_path):  # Review Focus 4
    manager, accounts, work, log = rig(fake_claude, tmp_path, LIMITED)
    limited = []
    manager.on_limit = limited.append
    try:
        agent = await manager.create("check the shop", account=work.id)
        await asyncio.sleep(0.3)
        await manager.send(agent.id, "and the cart")  # waits for the turn: it never runs at the limit
        assert await settle(manager, lambda agents: state(agents, agent.id) == "failed")
        await asyncio.sleep(0.5)
        assert agent.limit == {"account": work.id, "resets_at": float(RESETS)}
        assert agent.status == "Hit its usage limit" and agent.queued == 1 and limited == [work.id]
        assert accounts.limit(work.id) == float(RESETS)
        events = manager.events_of(agent.id)
        assert {"type": "delta", "text": "Open"} in events and events.count({"type": "limit"}) == 1
        assert str(RESETS) not in json.dumps(events)  # the chat names no time and no account
        assert told(log) == ["check the shop"]
        fake_claude[2].write_text(json.dumps(EVENTS), encoding="utf-8")
        await manager.send(agent.id, "try again")  # the user's own message: again, on the same account
        assert await settle(manager, lambda agents: state(agents, agent.id) == "your_turn" and not agent.pending)
        assert agent.limit is None and told(log) == ["check the shop", "and the cart", "try again"]
    finally:
        await manager.close_all()


async def test_a_turn_that_ends_well_clears_the_limit(fake_claude, tmp_path):
    manager, _, work, _ = rig(fake_claude, tmp_path, [EVENTS[0], {"rate_limit": {"status": "rejected"}}, *EVENTS[1:]])
    try:
        agent = await manager.create("check the shop", account=work.id)
        assert await settle(manager, lambda agents: state(agents, agent.id) == "your_turn")
        assert agent.limit is None and agent.status == ""
    finally:
        await manager.close_all()


async def test_without_accounts_agents_run_as_before(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    manager = AgentManager(tmp_path / "home", claude=runner)
    try:
        agent = await manager.create("check the shop")
        assert await settle(manager, lambda agents: state(agents, agent.id) == "your_turn")
        assert agent.account == {"id": "default", "name": "Default"} and agent.bridge.preflight is None
        assert given(log)["CLAUDE_CONFIG_DIR"] == os.environ["CLAUDE_CONFIG_DIR"]
        with pytest.raises(ValueError):
            await manager.create("check the blog", account="acct-000000")
    finally:
        await manager.close_all()


SESSION_EVENTS = [{**EVENTS[0], "session_id": "$session"}, *EVENTS[1:-1], {**EVENTS[-1], "session_id": "$session"}]


def transcripts(folder):
    return sorted((Path(folder) / "projects").glob("*/*.jsonl"))


async def test_a_move_carries_the_conversation_and_resumes_it(fake_claude, tmp_path):
    from ai_browser.app.bridge import RESTARTED

    manager, _, work, log = rig(fake_claude, tmp_path, SESSION_EVENTS)
    try:
        agent = await manager.create("check the shop")  # on Default
        assert await settle(manager, lambda agents: state(agents, agent.id) == "your_turn")
        manager.tab_event(agent.id, "tab_opened", "T1")
        session = agent.bridge.session_id
        [original] = transcripts(os.environ["CLAUDE_CONFIG_DIR"])
        before = original.read_bytes()
        assert await manager.move(agent.id, work.id, [{"url": "https://shop.example/", "title": "Shop"}]) == ""
        assert await settle(manager, lambda agents: state(agents, agent.id) == "your_turn"
                            and agent.moved == "Moved to Work with its conversation")
        assert argvs(log)[-1][argvs(log)[-1].index("--resume") + 1] == session
        assert given(log)["CLAUDE_CONFIG_DIR"] == work.folder
        [copy] = transcripts(work.folder)
        assert copy.name == f"{session}.jsonl" and copy.parent.name == original.parent.name
        assert original.read_bytes() == before  # the original stays as it was
        assert told(log)[-1] == f"{RESTARTED}\nContinue the task."
        assert agent.account == {"id": work.id, "name": "Work"} and agent.tabs == ["T1"]  # its tabs stay its own
    finally:
        await manager.close_all()


async def test_a_resume_that_ends_at_once_starts_fresh_with_the_note(fake_claude, tmp_path, monkeypatch):
    from ai_browser.app import move as moving

    manager, _, work, log = rig(fake_claude, tmp_path, SESSION_EVENTS)
    monkeypatch.setattr(moving, "move_conversation", lambda *args: True)  # says copied, copies nothing
    try:
        agent = await manager.create("check the shop")
        assert await settle(manager, lambda agents: state(agents, agent.id) == "your_turn")
        assert await manager.move(agent.id, work.id) == ""
        assert await settle(manager, lambda agents: state(agents, agent.id) == "your_turn"
                            and agent.moved == "Started fresh on Work with a hand-over note")
        assert "--resume" in argvs(log)[-2] and "--resume" not in argvs(log)[-1]  # it ended at once, then fresh
        assert told(log)[-1].startswith("You are taking over a task") and "check the shop" in told(log)[-1]
        events = manager.events_of(agent.id)
        assert {"type": "note", "text": "Started fresh with a hand-over note"} in events
        assert not any("No conversation found" in json.dumps(event) for event in events)
        assert not any(str(event.get("text", "")).startswith("You are taking over") for event in events)
    finally:
        await manager.close_all()


async def test_no_conversation_to_carry_starts_fresh_with_the_note(fake_claude, tmp_path):
    manager, _, work, log = rig(fake_claude, tmp_path, SESSION_EVENTS)
    try:
        agent = await manager.create("check the shop")
        assert await settle(manager, lambda agents: state(agents, agent.id) == "your_turn")
        old = agent.bridge.session_id
        for path in transcripts(os.environ["CLAUDE_CONFIG_DIR"]):
            path.unlink()  # nothing to copy
        assert await manager.move(agent.id, work.id) == ""
        assert await settle(manager, lambda agents: state(agents, agent.id) == "your_turn"
                            and agent.moved == "Started fresh on Work with a hand-over note")
        assert "--resume" not in argvs(log)[-1] and told(log)[-1].startswith("You are taking over a task")
        assert old not in [path.stem for path in transcripts(work.folder)]  # a new conversation there
    finally:
        await manager.close_all()


async def test_a_second_move_while_one_runs_does_nothing(fake_claude, tmp_path, monkeypatch):
    from ai_browser.app import move as moving
    from ai_browser.app.bridge import RESTARTED

    manager, accounts, work, log = rig(fake_claude, tmp_path, SESSION_EVENTS)
    personal = accounts.add("Personal")
    sign_in(personal.folder)
    copies, real = [], moving.move_conversation

    def slow(*args):
        copies.append(args)
        time.sleep(1)
        return real(*args)

    monkeypatch.setattr(moving, "move_conversation", slow)
    try:
        agent = await manager.create("check the shop")
        assert await settle(manager, lambda agents: state(agents, agent.id) == "your_turn")
        first = asyncio.ensure_future(manager.move(agent.id, work.id))
        await asyncio.sleep(0.4)  # the move is under way
        assert await manager.move(agent.id, personal.id) == ""  # does nothing
        await manager.send(agent.id, "and then the cart")  # waits for the move
        assert await first == ""
        assert await settle(manager, lambda agents: state(agents, agent.id) == "your_turn" and not agent.pending)
        assert len(copies) == 1 and agent.account["id"] == work.id
        assert told(log)[-2:] == [f"{RESTARTED}\nContinue the task.", "and then the cart"]
    finally:
        await manager.close_all()


async def test_two_agents_move_to_the_same_account_at_once(fake_claude, tmp_path):  # Review Focus 3
    manager, _, work, log = rig(fake_claude, tmp_path, SESSION_EVENTS)
    try:
        one, two = await manager.create("check the shop"), await manager.create("check the blog")
        assert await settle(manager, lambda agents: all(state(agents, agent.id) == "your_turn"
                                                        for agent in (one, two)))
        sessions = {one.bridge.session_id, two.bridge.session_id}
        assert len(sessions) == 2
        assert await asyncio.gather(manager.move(one.id, work.id), manager.move(two.id, work.id)) == ["", ""]
        assert await settle(manager, lambda agents: all(
            state(agents, agent.id) == "your_turn" and agent.moved == "Moved to Work with its conversation"
            for agent in (one, two)))
        assert {path.stem for path in transcripts(work.folder)} == sessions  # each its own copy, nothing overwritten
        resumed = [argv[argv.index("--resume") + 1] for argv in argvs(log) if "--resume" in argv]
        assert sorted(resumed) == sorted(sessions)
    finally:
        await manager.close_all()


async def test_a_move_needs_an_idle_agent_and_a_signed_in_account(fake_claude, tmp_path):
    manager, accounts, work, _ = rig(fake_claude, tmp_path, [EVENTS[0], {"sleep": 30}])
    try:
        agent = await manager.create("keep working")
        assert await settle(manager, lambda agents: any(event["type"] == "status"
                                                        for event in manager.events_of(agent.id)))  # mid-turn
        assert await manager.move(agent.id, work.id) == (
            "1 · keep working is still working: stop it, or wait for its turn to end, then move it")
        await manager.stop(agent.id)
        assert await settle(manager, lambda agents: state(agents, agent.id) == "stopped")
        sign_out(work.folder)
        accounts._status.clear()  # it signed out a moment ago
        assert await manager.move(agent.id, work.id) == "Work isn't signed in: sign in from Settings → Accounts"
        assert agent.account["id"] == "default" and agent.bridge._process is not None  # nothing changed
        assert await manager.move(agent.id, "acct-000000") == "That account isn't in Settings → Accounts any more"
        assert await manager.move(agent.id, "default") == "1 · keep working is on Default already"
    finally:
        await manager.close_all()


async def test_when_conversations_cant_be_carried_every_move_starts_fresh(fake_claude, tmp_path, monkeypatch):
    from ai_browser.app import move as moving

    monkeypatch.setattr(moving, "CARRY_CONVERSATION", False)  # Task 0's ruling, if the probe failed
    manager, _, work, log = rig(fake_claude, tmp_path, SESSION_EVENTS)
    try:
        agent = await manager.create("check the shop")
        assert await settle(manager, lambda agents: state(agents, agent.id) == "your_turn")
        assert await manager.move(agent.id, work.id) == ""
        assert await settle(manager, lambda agents: state(agents, agent.id) == "your_turn"
                            and agent.moved == "Started fresh on Work with a hand-over note")
        assert "--resume" not in argvs(log)[-1] and told(log)[-1].startswith("You are taking over a task")
    finally:
        await manager.close_all()


async def test_moving_back_and_forth_carries_the_conversation_both_ways(fake_claude, tmp_path):
    manager, _, work, log = rig(fake_claude, tmp_path, SESSION_EVENTS)
    default = Path(os.environ["CLAUDE_CONFIG_DIR"])
    try:
        agent = await manager.create("check the shop")  # on Default
        assert await settle(manager, lambda agents: state(agents, agent.id) == "your_turn")
        session = agent.bridge.session_id
        [first] = transcripts(default)
        before = first.read_bytes()
        assert await manager.move(agent.id, work.id) == ""  # Default's limit: on to Work
        assert await settle(manager, lambda agents: state(agents, agent.id) == "your_turn"
                            and agent.moved == "Moved to Work with its conversation")
        assert await manager.move(agent.id, "default") == ""  # Work's limit: back to Default
        assert await settle(manager, lambda agents: state(agents, agent.id) == "your_turn"
                            and agent.moved == "Moved to Default with its conversation")
        assert argvs(log)[-1][argvs(log)[-1].index("--resume") + 1] == session  # resumed both ways
        assert given(log)["CLAUDE_CONFIG_DIR"] == str(default)
        [aside] = [path for path in first.parent.iterdir() if path.name.startswith(f"{session}.jsonl.before-")]
        assert aside.read_bytes() == before  # Default's older copy stays, beside the newer one
        assert first.read_bytes().startswith(before) and len(first.read_bytes()) > len(before)
        carried = transcripts(work.folder)[0]
        carried.write_bytes(b'{"another": "conversation"}\n')  # not an older copy of this one any more
        assert await manager.move(agent.id, work.id) == ""
        assert await settle(manager, lambda agents: state(agents, agent.id) == "your_turn"
                            and agent.moved == "Started fresh on Work with a hand-over note")
        assert carried.read_bytes() == b'{"another": "conversation"}\n'  # never overwritten
    finally:
        await manager.close_all()


async def test_a_move_keeps_the_runs_effort(fake_claude, tmp_path):
    manager, _, work, log = rig(fake_claude, tmp_path, SESSION_EVENTS)
    try:
        agent = await manager.create("check the shop", effort="high")
        assert await settle(manager, lambda agents: state(agents, agent.id) == "your_turn")
        assert agent.public()["effort"] == "high"
        assert await manager.move(agent.id, work.id) == ""
        assert await settle(manager, lambda agents: state(agents, agent.id) == "your_turn"
                            and agent.moved == "Moved to Work with its conversation")
        last = argvs(log)[-1]
        assert "--resume" in last and last[last.index("--effort") + 1] == "high"
    finally:
        await manager.close_all()
