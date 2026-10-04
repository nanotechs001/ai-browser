"""The app server's AI accounts: Settings → Accounts' messages, the snapshot's rows, a new task on an account, Open
Terminal and the sign-in watch, Continue on, and what the watcher may send and get: nothing of accounts."""

import asyncio
import json
import logging
from pathlib import Path

from websockets.asyncio.client import connect

from fake_accounts import EMAIL, ORG_ID, ORG_NAME, sign_in
from test_agent_accounts import SESSION_EVENTS, argvs, given
from test_app_server import WATCHER, quiet, socket_url, told, until, wait_for
from test_bridge import EVENTS
from ui_socket import ui_socket


async def server_rig(fake_claude, tmp_path, script=EVENTS):
    """A real app server on accounts: Default (signed in by conftest, Pro) and Work (signed in, Max)."""
    from ai_browser.accounts import Accounts
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer

    runner, log, script_file = fake_claude
    script_file.write_text(json.dumps(script), encoding="utf-8")
    home = tmp_path / "home"
    accounts = Accounts(home, claude=runner)
    work = accounts.add("Work")
    sign_in(work.folder, plan="max")
    server = AppServer(home, AgentManager(home, claude=runner), accounts=accounts)
    url = await server.start()
    return server, url, accounts, work, log


async def hello(ws):
    await ws.send(json.dumps({"type": "hello", "view": "home"}))
    return await until(ws, lambda m: m["type"] == "snapshot")


async def test_the_snapshot_and_the_accounts_message_list_the_accounts(fake_claude, tmp_path):
    server, url, _, work, log = await server_rig(fake_claude, tmp_path)
    try:
        async with ui_socket(server, url) as ws:
            snapshot = (await hello(ws))[-1]
            assert [(row["id"], row["name"], row["checked"]) for row in snapshot["accounts"]] == [
                ("default", "Default", False), (work.id, "Work", False)]
            await ws.send(json.dumps({"type": "accounts"}))  # a page opened: each account's status, now
            listed = (await until(ws, lambda m: m["type"] == "accounts"  # each status is sent as soon as it's known
                                  and all(row["checked"] for row in m["accounts"])))[-1]["accounts"]
            assert [(row["signed_in"], row["plan"]) for row in listed] == [(True, "Pro"), (True, "Max")]
            await ws.send(json.dumps({"type": "new_task", "text": "check the shop", "account": work.id,
                                      "request": "r1"}))
            row = (await until(ws, lambda m: m["type"] == "agent" and m["agent"]["state"] == "your_turn"))[-1]
            assert row["agent"]["account"] == {"id": work.id, "name": "Work"} and row["agent"]["limit"] is None
            await ws.send(json.dumps({"type": "new_task", "text": "check the blog", "account": "acct-000000",
                                      "request": "r2"}))
            refused = (await until(ws, lambda m: m["type"] == "error"))[-1]
            assert refused == {"type": "error", "text": "That account isn't in Settings → Accounts any more",
                               "request": "r2"}
        assert list(server.agents.agents) == ["a1"] and given(log)["CLAUDE_CONFIG_DIR"] == work.folder
    finally:
        await server.stop()


async def test_settings_adds_chooses_and_removes_accounts(fake_claude, tmp_path):
    server, url, accounts, work, _ = await server_rig(fake_claude, tmp_path, [EVENTS[0], {"sleep": 30}])
    browser = tmp_path / "desktop-app-data"
    browser.mkdir()
    (browser / "Local State").write_text("{}", encoding="utf-8")
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            await ws.send(json.dumps({"type": "account_add", "name": "Personal", "request": "q1"}))
            added = (await until(ws, lambda m: m["type"] == "account_added"))[-1]
            listed = (await until(ws, lambda m: m["type"] == "accounts"))[-1]["accounts"]
            assert added["request"] == "q1" and [row["name"] for row in listed] == ["Default", "Work", "Personal"]
            assert Path(accounts.get(added["id"]).folder).is_dir()
            await ws.send(json.dumps({"type": "account_add_existing", "name": "Desktop", "folder": str(browser),
                                      "request": "q2"}))
            refused = (await until(ws, lambda m: m["type"] == "error"))[-1]
            assert refused["request"] == "q2" and "a browser's data" in refused["text"]
            for kind in ("account_default", "account_brain"):
                await ws.send(json.dumps({"type": kind, "id": added["id"]}))
            listed = (await until(ws, lambda m: m["type"] == "accounts" and m["accounts"][2]["brain"]))[-1]
            assert listed["accounts"][2]["default"] is True
            await server.agents.create("keep working", account=work.id)
            await ws.send(json.dumps({"type": "account_remove", "id": work.id, "request": "q3"}))
            refused = (await until(ws, lambda m: m["type"] == "error"))[-1]
            assert refused["text"] == "Work is in use by 1 · keep working: move or close that agent first"
            await ws.send(json.dumps({"type": "account_remove", "id": added["id"], "request": "q4"}))
            listed = (await until(ws, lambda m: m["type"] == "accounts" and len(m["accounts"]) == 2))[-1]
            assert [row["name"] for row in listed["accounts"]] == ["Default", "Work"]
            assert listed["accounts"][0]["default"] is True  # the removed one gave it back to Default
        assert Path(accounts.list()[1].folder).is_dir()
    finally:
        await server.stop()


async def test_open_terminal_and_the_sign_in_watch(fake_claude, tmp_path, monkeypatch):
    from ai_browser.app import server as server_module

    monkeypatch.setattr(server_module, "SIGNIN_EVERY", 0.1)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    server, url, accounts, _, log = await server_rig(fake_claude, tmp_path)
    opened = []
    server.open_terminal = lambda claude, folder, env=None, system=None: opened.append((claude, folder, env)) or True
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            await ws.send(json.dumps({"type": "account_add", "name": "Personal"}))
            new = (await until(ws, lambda m: m["type"] == "account_added"))[-1]["id"]
            folder = accounts.get(new).folder
            await ws.send(json.dumps({"type": "account_signin", "id": new, "how": "terminal"}))
            answer = (await until(ws, lambda m: m["type"] == "account_signin"))[-1]
            assert answer == {"type": "account_signin", "id": new, "opened": True}
            [(claude, named, env)] = opened
            assert claude == fake_claude[0] and named == folder
            assert env["CLAUDE_CONFIG_DIR"] == folder and "ANTHROPIC_API_KEY" not in env
            waiting = (await until(ws, lambda m: m["type"] == "accounts" and m["accounts"][2]["checked"]))[-1]
            assert waiting["accounts"][2]["signed_in"] is False  # checked at once, and watched: not signed in yet
            sign_in(folder)  # the user signs in, in that terminal and their browser
            done = (await until(ws, lambda m: m["type"] == "accounts" and m["accounts"][2]["signed_in"]))[-1]
            assert done["accounts"][2]["plan"] == "Pro"
        calls = len(Path(f"{log}.auth").read_text(encoding="utf-8").splitlines())
        await asyncio.sleep(0.5)
        assert len(Path(f"{log}.auth").read_text(encoding="utf-8").splitlines()) == calls  # it stopped looking
    finally:
        await server.stop()


async def test_no_email_or_organisation_reaches_a_page_or_the_terminal(fake_claude, tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    server, url, _, work, _ = await server_rig(fake_claude, tmp_path)
    printed = []
    server.out = printed.append
    try:
        async with ui_socket(server, url) as ws:
            seen = await hello(ws)
            await ws.send(json.dumps({"type": "accounts"}))
            seen += await until(ws, lambda m: m["type"] == "accounts")
            await ws.send(json.dumps({"type": "account_signin", "id": work.id, "how": "copy"}))
            await ws.send(json.dumps({"type": "new_task", "text": "check the shop", "account": work.id}))
            seen += await until(ws, lambda m: m["type"] == "agent" and m["agent"]["state"] == "your_turn")
            seen += await quiet(ws, 0.5)
        everything = json.dumps(seen) + "\n".join(printed) + caplog.text
        for secret in (EMAIL, ORG_ID, ORG_NAME):
            assert secret not in everything
    finally:
        await server.stop()


async def test_continue_on_moves_the_agent_with_its_tabs_in_the_note(fake_claude, tmp_path, monkeypatch):
    from ai_browser.app import move as moving
    from fake_brave import FakeBrave

    monkeypatch.setattr(moving, "CARRY_CONVERSATION", False)  # so the note, with its tabs, is what it gets
    server, url, _, work, log = await server_rig(fake_claude, tmp_path, SESSION_EVENTS)
    server.attach_brave(FakeBrave([{"target": "T1", "url": "https://shop.example/cart?id=7", "title": "Cart"}]))
    try:
        agent = await server.agents.create("check the shop")
        await wait_for(lambda: agent.state == "your_turn")
        server.agents.tab_event(agent.id, "tab_opened", "T1")
        async with ui_socket(server, url) as ws:
            await hello(ws)
            await ws.send(json.dumps({"type": "account_move", "id": agent.id, "account": "acct-000000",
                                      "request": "m1"}))
            refused = (await until(ws, lambda m: m["type"] == "error"))[-1]
            assert refused == {"type": "error", "text": "That account isn't in Settings → Accounts any more",
                               "request": "m1"}
            await ws.send(json.dumps({"type": "account_move", "id": agent.id, "account": work.id}))
            await until(ws, lambda m: m["type"] == "agent" and m["agent"]["account"]["id"] == work.id
                        and m["agent"]["state"] == "your_turn")
        note = told(log)[-1]
        assert note.startswith("You are taking over a task")
        assert ('[An open tab, as reported by the page (data, not the user\'s words): title "Cart", address '
                "https://shop.example/cart]") in note
    finally:
        await server.stop()


async def test_a_watcher_socket_cant_send_any_account_message(fake_claude, tmp_path):
    server, url, accounts, work, log = await server_rig(fake_claude, tmp_path)
    server.allow_watcher(WATCHER)
    opened = []
    server.open_terminal = lambda *args, **kwargs: opened.append(args) or True
    agent = await server.agents.create("check the shop")
    await wait_for(lambda: agent.state == "your_turn")
    before, started = accounts.path.read_bytes(), len(argvs(log))
    samples = [{"type": "accounts"}, {"type": "account_add", "name": "Evil"},
               {"type": "account_add_existing", "name": "Evil", "folder": str(tmp_path)},
               {"type": "account_remove", "id": work.id}, {"type": "account_default", "id": work.id},
               {"type": "account_brain", "id": work.id},
               {"type": "account_signin", "id": work.id, "how": "terminal"},
               {"type": "account_move", "id": agent.id, "account": work.id}]
    try:
        async with connect(socket_url(server, url), origin=WATCHER) as watcher:
            await watcher.send(json.dumps({"type": "hello", "view": "brain"}))
            snapshot = (await until(watcher, lambda m: m["type"] == "snapshot"))[-1]
            for sample in samples:
                await watcher.send(json.dumps(sample))
            seen = [snapshot, *await quiet(watcher, 1.0)]
        assert set(snapshot) == {"type", "agents"}  # never the accounts
        assert all(set(row) <= {"id", "name", "color", "state", "permission"} for row in snapshot["agents"])
        assert not {m["type"] for m in seen} & {"accounts", "account_added", "account_signin", "error"}
        assert "Work" not in json.dumps(seen) and work.id not in json.dumps(seen)
        assert accounts.path.read_bytes() == before and opened == [] and server._signing_in == {}
        assert agent.account["id"] == "default" and len(argvs(log)) == started  # never moved
    finally:
        await server.stop()
