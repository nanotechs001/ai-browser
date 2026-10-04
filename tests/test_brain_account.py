"""The Brain's account (AI accounts Decision 10): the Brain's and its skill writer's Claude calls run on the account
chosen in Settings, and a call refused at a usage limit waits for the card's click, then runs once more there."""

import asyncio
import json
import os
import time

from websockets.asyncio.client import connect

from fake_accounts import sign_in
from test_app_server import WATCHER, quiet, socket_url, until
from test_oneshot import oneshots
from ui_socket import ui_socket

RESETS = int(time.time()) + 3600


def brain_rig(fake_claude, tmp_path, answers):
    from ai_browser.accounts import Accounts
    from ai_browser.brain.account import BrainAccount

    runner, log, script = fake_claude
    script.write_text(json.dumps(answers), encoding="utf-8")
    accounts = Accounts(tmp_path / "home", claude=runner)
    work = accounts.add("Work")
    sign_in(work.folder)
    return BrainAccount(accounts), accounts, work, runner, log


async def test_the_brains_calls_run_on_its_account(fake_claude, tmp_path):
    brain, accounts, work, runner, log = brain_rig(fake_claude, tmp_path, [{"result": "sorted"}])
    assert (await brain("Sort these", claude=runner, cwd=tmp_path / "calls")).text == "sorted"
    accounts.set_brain(work.id)
    assert (await brain("Sort these", claude=runner, cwd=tmp_path / "calls")).text == "sorted"
    assert [made["config"] for made in oneshots(log)] == [os.environ["CLAUDE_CONFIG_DIR"], work.folder]


async def test_a_limit_waits_for_the_click_and_runs_once_more(fake_claude, tmp_path):
    brain, accounts, work, runner, log = brain_rig(fake_claude, tmp_path, [
        {"result": f"Claude AI usage limit reached|{RESETS}", "is_error": True}, {"result": "drafted"}])
    cards = []
    brain.on_limit = cards.append
    call = asyncio.ensure_future(brain("Draft a reply", claude=runner, cwd=tmp_path / "calls", timeout=20))
    for _ in range(100):
        if cards:
            break
        await asyncio.sleep(0.05)
    assert cards == [{"account": "default", "resets_at": float(RESETS)}] and not call.done()  # it waits
    assert accounts.limit("default") == float(RESETS)
    accounts.set_brain(work.id)  # the card's click
    brain.switched()
    answer = await asyncio.wait_for(call, 10)
    assert answer.text == "drafted" and not answer.error
    assert [made["config"] for made in oneshots(log)] == [os.environ["CLAUDE_CONFIG_DIR"], work.folder]


async def test_without_a_click_the_call_ends_with_its_error_in_time(fake_claude, tmp_path):
    brain, _, _, runner, log = brain_rig(fake_claude, tmp_path, [{"result": "Usage limit reached", "is_error": True}])
    started = asyncio.get_running_loop().time()
    answer = await brain("Sort these", claude=runner, cwd=tmp_path / "calls", timeout=2)
    assert answer.error == "Default hit its usage limit" and answer.text == ""
    assert asyncio.get_running_loop().time() - started < 5 and len(oneshots(log)) == 1  # never tried again by itself


async def test_the_server_shows_the_brains_card_and_its_click_retries(fake_claude, tmp_path):
    from ai_browser.accounts import Accounts
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer
    from ai_browser.brain.account import BrainAccount

    runner, _, script = fake_claude
    script.write_text(json.dumps([{"result": "You have reached your weekly usage limit", "is_error": True},
                                  {"result": "fine"}]), encoding="utf-8")
    home = tmp_path / "home"
    accounts = Accounts(home, claude=runner)
    work = accounts.add("Work")
    sign_in(work.folder)
    brain = BrainAccount(accounts)
    server = AppServer(home, AgentManager(home, claude=runner), accounts=accounts, brain_account=brain)
    url = await server.start()
    server.allow_watcher(WATCHER)
    try:
        async with ui_socket(server, url) as page, connect(socket_url(server, url), origin=WATCHER) as watcher:
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            await watcher.send(json.dumps({"type": "hello", "view": "brain"}))
            assert (await until(page, lambda m: m["type"] == "snapshot"))[-1]["brain_limit"] is None
            await until(watcher, lambda m: m["type"] == "snapshot")
            call = asyncio.ensure_future(brain("Sort these", claude=runner, cwd=tmp_path / "calls", timeout=20))
            card = (await until(page, lambda m: m["type"] == "brain_limit"))[-1]
            assert card == {"type": "brain_limit", "limit": {"account": "default", "resets_at": None}}
            await page.send(json.dumps({"type": "account_brain", "id": work.id}))  # the card's click
            assert (await asyncio.wait_for(call, 10)).text == "fine"
            gone = await until(page, lambda m: m["type"] == "brain_limit" and m["limit"] is None)
            later = [*gone, *await quiet(page, 0.5)]
            assert any(m["type"] == "accounts" and m["accounts"][1]["brain"] for m in later)
            seen = await quiet(watcher, 0.5)
        assert not any(m["type"] in ("brain_limit", "accounts") for m in seen)  # the watcher gets neither
        assert server.brain_limit is None and accounts.brain_id() == work.id
    finally:
        await server.stop()
