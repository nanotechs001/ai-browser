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
