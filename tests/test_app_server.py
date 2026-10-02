"""The AI Browser app server: AI Home's, the panel's and the extension's only way to the agents. Guarded by a token
and the extension's origin; the agents' engines report their tabs with a token of their own."""

import asyncio
import json
import os

import httpx
import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from test_bridge import EVENTS
from test_oneshot import oneshots

ORIGIN = "chrome-extension://good"
WATCHER = "chrome-extension://watcher"


async def started(fake_claude, tmp_path, events, **options):
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer

    runner, log, script = fake_claude
    script.write_text(json.dumps(events))
    server = AppServer(tmp_path / "home", AgentManager(tmp_path / "home", claude=str(runner)), **options)
    url = await server.start()
    server.allow_origin(ORIGIN)
    return server, url


def socket_url(server, url, token=None):
    return url.replace("http", "ws") + "/ws?token=" + (server.token if token is None else token)


async def recv(ws) -> dict:
    """The next message, or a test failure after 10 s (instead of waiting forever)."""
    return json.loads(await asyncio.wait_for(ws.recv(), 10))


async def until(ws, predicate) -> list[dict]:
    """Messages up to and including the first one `predicate` accepts."""
    seen = []
    while not seen or not predicate(seen[-1]):
        seen.append(await recv(ws))
    return seen


def finished(message) -> bool:
    return message["type"] == "agent" and message["agent"]["state"] in ("your_turn", "failed", "stopped")


async def test_strangers_are_refused(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        for token, origin in ((server.token, "https://evil.example"), ("wrong", ORIGIN)):
            async with connect(socket_url(server, url, token), origin=origin) as ws:
                with pytest.raises(ConnectionClosed) as closed:
                    await ws.recv()
                assert closed.value.rcvd.code == 4403
    finally:
        await server.stop()


async def test_a_task_runs_and_every_socket_sees_it(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        async with connect(socket_url(server, url), origin=ORIGIN) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "home"}))
            assert (await recv(ws))["type"] == "snapshot"
            await ws.send(json.dumps({"type": "new_task", "text": "check the shop", "skills": [], "model": "haiku",
                                      "request": "r1"}))
            seen = await until(ws, finished)
            assert {"type": "created", "id": "a1", "request": "r1"} in seen
        async with connect(socket_url(server, url), origin=ORIGIN) as ws:  # a page opened later
            await ws.send(json.dumps({"type": "hello", "view": "panel"}))
            snapshot = await recv(ws)
            assert snapshot["agents"][0]["name"] == "check the shop" and "events" not in snapshot["agents"][0]
            assert snapshot["max_working"] == 3
            await ws.send(json.dumps({"type": "events", "id": "a1"}))
            history = (await until(ws, lambda message: message["type"] == "agent_events"))[-1]
            assert any(event["type"] == "done" for event in history["events"])
            assert history["events"][0] == {"type": "user", "text": "check the shop"}
    finally:
        await server.stop()


async def test_agent_events_need_the_agent_token(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        await server.agents.create("one")
        report = {"agent": "a1", "kind": "tab_opened", "target": "T", "adopted": False}
        async with httpx.AsyncClient() as client:
            assert (await client.post(url + "/agent-events", json=report)).status_code == 403
            wrong = {"X-AIB-Agent-Token": server.token}  # the extension's token is not the engines'
            assert (await client.post(url + "/agent-events", json=report, headers=wrong)).status_code == 403
            right = {"X-AIB-Agent-Token": server.agent_token}
            assert (await client.post(url + "/agent-events", json=report, headers=right)).status_code == 204
        assert server.agents.snapshot()["agents"][0]["tabs"] == ["T"]
    finally:
        await server.stop()


async def test_setup_page_and_status(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        async with httpx.AsyncClient() as client:
            page = (await client.get(url + "/setup")).text
            assert str(tmp_path / "home" / "app" / "extension") in page and server.token not in page
            assert (await client.get(url + "/setup/status")).json() == {"installed": False, "watcher": False}
            async with connect(socket_url(server, url), origin=ORIGIN) as ws:
                await ws.send(json.dumps({"type": "hello", "view": "home"}))
                await recv(ws)
            assert (await client.get(url + "/setup/status")).json() == {"installed": True, "watcher": False}
    finally:
        await server.stop()


async def test_skills_for_the_dashboard(fake_claude, tmp_path):
    from ai_browser.skills import Catalog, SkillSource

    root = tmp_path / "skills"
    for name, description in (("alpha", "<img src=x onerror=alert(1)>"), ("beta", "Builds pages")):
        (root / name).mkdir(parents=True)
        (root / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\nbody\n")
    catalog = Catalog([SkillSource("personal", root, "/skills/personal", "*/SKILL.md")], set())
    server, url = await started(fake_claude, tmp_path, EVENTS, catalog=catalog)
    try:
        async with connect(socket_url(server, url), origin=ORIGIN) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "home"}))
            assert (await recv(ws))["skills_summary"] == {"total": 2, "by_source": {"personal": 2}}
            await ws.send(json.dumps({"type": "skills"}))
            skills = (await until(ws, lambda message: message["type"] == "skills"))[-1]["skills"]
            assert {"ref": "personal:alpha", "name": "alpha", "namespace": "personal", "source": "personal",
                    "description": "<img src=x onerror=alert(1)>"} in skills  # the page renders it as text
    finally:
        await server.stop()


async def test_long_histories_are_capped(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        agent = await server.agents.create("long qa")
        await asyncio.sleep(1)
        for n in range(6000):
            server.agents._record(agent, {"type": "delta", "text": str(n)})
        async with connect(socket_url(server, url), origin=ORIGIN) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "home"}))
            snapshot = await recv(ws)
            assert "events" not in snapshot["agents"][0] and len(json.dumps(snapshot)) < 5000
            await ws.send(json.dumps({"type": "events", "id": agent.id}))
            history = (await until(ws, lambda message: message["type"] == "agent_events"))[-1]["events"]
            assert len(history) == 5000 and history[-1] == {"type": "delta", "text": "5999"}
    finally:
        await server.stop()


class StubTabs:
    def __init__(self):
        self.shots = 0

    def on_change(self, callback):
        pass

    def tabs(self):
        return []

    async def thumbnail(self, target):
        self.shots += 1
        return b"\xff\xd8x"

    async def watch(self, target):
        pass


async def test_thumbnails_follow_actions_at_most_every_two_seconds(fake_claude, tmp_path):
    def tool(n):
        return [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"u{n}",
                                                               "name": "mcp__ai-browser__act", "input": {}}]}},
                {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"u{n}",
                                                          "content": [{"type": "text", "text": "ok\n⏱ 5 ms"}]}]}}]

    tabs = StubTabs()
    # the second action comes after the first picture was taken, but within the same 2 s
    script = [EVENTS[0], {"sleep": 0.5}, *tool(1), {"sleep": 0.3}, *tool(2), EVENTS[-1]]
    server, url = await started(fake_claude, tmp_path, script, tabs=tabs)
    try:
        async with connect(socket_url(server, url), origin=ORIGIN) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "home"}))
            await recv(ws)
            await ws.send(json.dumps({"type": "new_task", "text": "act twice", "skills": [], "request": "r"}))
            await until(ws, lambda message: message["type"] == "created")
            async with httpx.AsyncClient() as client:
                await client.post(url + "/agent-events", headers={"X-AIB-Agent-Token": server.agent_token},
                                  json={"agent": "a1", "kind": "working_tab", "target": "T", "adopted": False})
            seen = await until(ws, finished)
            await asyncio.sleep(0.5)
            assert tabs.shots == 1  # two actions within 2 s: one picture now...
            await asyncio.sleep(2.5)
            assert tabs.shots == 2  # ...and one when the 2 s are over, so the row ends on the latest state
            seen += await until(ws, lambda message: message["type"] == "thumb")
            assert {"type": "thumb", "id": "a1", "jpeg": "/9h4"} in seen
    finally:
        await server.stop()


async def test_new_tasks_use_the_apps_default_model(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS, default_model="haiku")  # ai-browser app --model haiku
    try:
        async with connect(socket_url(server, url), origin=ORIGIN) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "home"}))
            assert (await recv(ws))["default_model"] == "haiku"
            await ws.send(json.dumps({"type": "new_task", "text": "quick look", "request": "r"}))
            await until(ws, lambda message: message["type"] == "created")
        assert server.agents.agents["a1"].model == "haiku"
    finally:
        await server.stop()


async def test_the_setup_page_can_show_the_folder_in_finder(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    shown = []
    server.reveal = shown.append
    try:
        async with httpx.AsyncClient() as client:
            page = (await client.get(url + "/setup")).text
            key = page.split('data-key="', 1)[1].split('"', 1)[0]
            assert key and key not in (server.token, server.agent_token)
            assert (await client.post(url + "/setup/reveal")).status_code == 403  # another site can't open Finder
            assert (await client.post(url + "/setup/reveal", headers={"X-AIB-Setup": key})).status_code == 204
        assert shown == [str((tmp_path / "home" / "app" / "extension").resolve())]
    finally:
        await server.stop()


async def test_the_setup_page_covers_chromes_questions(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        async with httpx.AsyncClient() as client:
            page = (await client.get(url + "/setup")).text
        assert "Keep it" in page  # Chrome asks once about the new tab page: "Change it back" turns AI Browser off
        assert "switch it on" in page  # already listed in chrome://extensions, but off
    finally:
        await server.stop()


async def with_brain(fake_claude, tmp_path, answers):
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer
    from ai_browser.brain.service import BrainService
    from ai_browser.brain.store import BrainStore

    runner, log, script = fake_claude
    script.write_text(json.dumps(answers))
    home = tmp_path / "home"
    agents = AgentManager(home, claude=str(runner))
    brain = BrainService(BrainStore(home), agents, claude=str(runner), batch_wait=0.1)
    server = AppServer(home, agents, brain=brain)
    url = await server.start()
    server.allow_origin(ORIGIN)
    server.allow_origin(WATCHER, watcher=True)
    brain.set_watch({"site": "gmail", "enabled": True, "url_match": "https://mail.google.com/*"})
    return server, url, brain


async def test_the_watcher_feeds_the_brain_and_pages_see_it(fake_claude, tmp_path):
    verdicts = [{"id": "gmail:t1", "kind": "needs_reply", "summary": "Maria asks to move the launch", "why": "a client",
                 "suggest": "draft"}]
    server, url, brain = await with_brain(fake_claude, tmp_path, [{"result": json.dumps(verdicts)}])
    try:
        async with connect(socket_url(server, url), origin=WATCHER) as watcher:
            await watcher.send(json.dumps({"type": "hello", "view": "watcher"}))
            greeting = await until(watcher, lambda m: m["type"] == "watch_list")
            assert greeting[0]["type"] == "watcher_hello" and greeting[-1]["sites"][0]["site"] == "gmail"
            async with httpx.AsyncClient() as client:  # Brave's watcher is not AI Browser's extension
                assert (await client.get(url + "/setup/status")).json() == {"installed": False, "watcher": True}
            async with connect(socket_url(server, url), origin=ORIGIN) as page:
                await page.send(json.dumps({"type": "hello", "view": "home"}))
                await page.send(json.dumps({"type": "brain"}))
                assert (await until(page, lambda m: m["type"] == "brain_snapshot"))[-1]["watcher"] is True
                await watcher.send(json.dumps({"type": "items", "site": "gmail", "items": [
                    {"id": "t1", "from": "Maria", "subject": "Launch", "snippet": "Monday?", "url": "https://x/1",
                     "time": "1"}]}))
                item = (await until(page, lambda m: m["type"] == "brain_item"))[-1]["item"]
                assert item["kind"] == "needs_reply" and item["summary"] == "Maria asks to move the launch"
                assert (await until(watcher, lambda m: m["type"] == "notify"))[-1]["count"] == 1
                await watcher.send(json.dumps({"type": "reader_status", "site": "gmail", "ok": False,
                                               "note": "reader needs an update"}))
                state = (await until(page, lambda m: m["type"] == "brain_state"))[-1]
                assert state["watch_list"][0]["status"] == "reader needs an update"
            await watcher.close()
        for _ in range(50):
            if not brain.watcher:
                break
            await asyncio.sleep(0.05)
        assert brain.watcher is False
    finally:
        await server.stop()


async def test_only_the_watcher_may_report_items(fake_claude, tmp_path):
    server, url, brain = await with_brain(fake_claude, tmp_path, [{"result": "[]"}])
    log = fake_claude[1]
    try:
        async with connect(socket_url(server, url), origin=ORIGIN) as page:
            await page.send(json.dumps({"type": "hello", "view": "watcher"}))
            assert (await recv(page))["type"] == "snapshot"  # AI Browser's own page, not the watcher
            await page.send(json.dumps({"type": "items", "site": "gmail", "items": [
                {"id": "t1", "from": "Maria", "subject": "Launch", "snippet": "Monday?", "url": "https://x/1"}]}))
            await page.send(json.dumps({"type": "brain"}))
            snapshot = (await until(page, lambda m: m["type"] == "brain_snapshot"))[-1]
            await brain.settle()
            assert snapshot["items"] == [] and snapshot["watcher"] is False and oneshots(log) == []
    finally:
        await server.stop()


async def test_a_draft_without_the_watcher_says_so(fake_claude, tmp_path):
    from ai_browser.brain.store import Item

    server, url, brain = await with_brain(fake_claude, tmp_path, [{"result": "[]"}])
    brain.store.put(Item(id="gmail:t1", site="gmail", raw_id="t1", url="https://mail.google.com/mail/u/0/#inbox/t1",
                         kind="needs_reply"))
    try:
        async with connect(socket_url(server, url), origin=ORIGIN) as page:
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            await page.send(json.dumps({"type": "draft", "id": "gmail:t1"}))
            seen = await until(page, lambda m: m["type"] == "brain_item" and "isn't connected" in m["item"]["note"])
            assert seen[-1]["item"]["state"] == "open"
    finally:
        await server.stop()


def test_prepare_watcher_updates_its_folder_in_place(tmp_path):
    from ai_browser.appbrowser import extension_id_for, prepare_extension
    from ai_browser.brain.watcher import prepare_watcher

    folder, build = prepare_watcher(tmp_path, "http://127.0.0.1:8792", "secret")
    assert folder == tmp_path / "app" / "watcher" and len(build) == 12
    assert json.loads((folder / "config.json").read_text()) == {"server": "http://127.0.0.1:8792", "token": "secret"}
    assert (folder / "config.json").stat().st_mode & 0o777 == 0o600
    assert (folder / "link.js").exists() and f'"{build}"' in (folder / "build.js").read_text()
    manifest = json.loads((folder / "manifest.json").read_text())
    assert "https://mail.google.com/*" in manifest["host_permissions"]
    assert extension_id_for(folder) != extension_id_for(prepare_extension(tmp_path, "http://127.0.0.1:1", "t"))
    (folder / "stale.js").write_text("old")
    before = (folder / "manifest.json").stat().st_mtime_ns
    again, same = prepare_watcher(tmp_path, "http://127.0.0.1:8793", "other")
    assert same == build and (folder / "manifest.json").stat().st_mtime_ns == before  # unchanged files stay as they are
    assert json.loads((folder / "config.json").read_text())["token"] == "other" and not (folder / "stale.js").exists()


async def test_the_setup_page_has_the_brave_steps(fake_claude, tmp_path):
    server, url, brain = await with_brain(fake_claude, tmp_path, [{"result": "[]"}])
    shown = []
    server.reveal = shown.append
    try:
        async with httpx.AsyncClient() as client:
            page = (await client.get(url + "/setup")).text
            assert "brave://extensions" in page and str(tmp_path / "home" / "app" / "watcher") in page
            key = page.split('data-key="', 1)[1].split('"', 1)[0]
            reveal = await client.post(url + "/setup/reveal?which=watcher", headers={"X-AIB-Setup": key})
            assert reveal.status_code == 204
        assert shown == [os.path.realpath(tmp_path / "home" / "app" / "watcher")]
    finally:
        await server.stop()


async def test_late_pages_get_the_latest_thumbnails(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, [EVENTS[0], {"sleep": 30}], tabs=StubTabs())
    try:
        agent = await server.agents.create("look around")
        agent.working_tab = "T"
        server._on_action(agent)
        async with connect(socket_url(server, url), origin=ORIGIN) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "mission"}))
            await recv(ws)
            for _ in range(50):  # the picture is taken in the background
                await ws.send(json.dumps({"type": "thumbs"}))
                [*_, answer] = await until(ws, lambda message: message["type"] == "thumbs")
                if answer["thumbs"]:
                    break
                await asyncio.sleep(0.1)
            assert answer["thumbs"] == {"a1": "/9h4"}  # a page opened later sees the latest picture at once
            await server.agents.close("a1")
            await ws.send(json.dumps({"type": "thumbs"}))
            [*_, answer] = await until(ws, lambda message: message["type"] == "thumbs")
            assert answer["thumbs"] == {} and "a1" not in server._thumbs  # a closed agent's picture is gone
    finally:
        await server.stop()



async def test_no_picture_is_sent_for_an_agent_closed_meanwhile(fake_claude, tmp_path):
    taken = asyncio.Event()

    class SlowTabs(StubTabs):
        async def thumbnail(self, target):
            await taken.wait()  # the picture is still being taken when the agent has closed
            return await super().thumbnail(target)

    server, url = await started(fake_claude, tmp_path, [EVENTS[0], {"sleep": 30}], tabs=SlowTabs())
    try:
        async with connect(socket_url(server, url), origin=ORIGIN) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "mission"}))
            await recv(ws)
            agent = await server.agents.create("look around")
            agent.working_tab = "T"
            server._on_action(agent)
            await asyncio.sleep(0.1)
            await server.agents.close("a1")
            taken.set()
            seen = []
            with pytest.raises(TimeoutError):
                while True:
                    seen.append(json.loads(await asyncio.wait_for(ws.recv(), 1.5)))
            kinds = [message["type"] for message in seen]
            assert "agent_closed" in kinds and "thumb" not in kinds[kinds.index("agent_closed"):]
    finally:
        await server.stop()


CHECK_REPORT = {"kind": "check", "target": "T1", "adopted": False, "check": "google", "site": "www.google.com"}


async def wait_for(predicate, seconds=10):
    for _ in range(int(seconds * 20)):
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("it never happened")


def told(log) -> list[str]:
    """What the agents' Claude Code processes were sent as user messages."""
    lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    return [line["message"]["content"] for line in lines if isinstance(line, dict) and line.get("type") == "user"]


async def test_check_reports_are_checked_then_reach_pages_and_the_watcher(fake_claude, tmp_path):
    from ai_browser.checks import KINDS

    server, url, _ = await with_brain(fake_claude, tmp_path, EVENTS)
    try:
        agent = await server.agents.create("Flights to Manila")
        good = {**CHECK_REPORT, "agent": agent.id}
        headers = {"X-AIB-Agent-Token": server.agent_token}
        async with connect(socket_url(server, url), origin=WATCHER) as watcher:
            await watcher.send(json.dumps({"type": "hello", "view": "watcher"}))
            await until(watcher, lambda message: message["type"] == "watch_list")
            async with httpx.AsyncClient() as client:
                for bad in ({**good, "check": "dragon"}, {**good, "site": "www.google.com <b>"}, {**good, "site": "a b"},
                            {**good, "site": "www.google.com\n"}, {**good, "live": "http://evil.example/live?token=x"},
                            {**good, "live": "http://127.0.0.1:80@evil.example/live?token=x"}):  # Review Focus 2
                    response = await client.post(url + "/agent-events", json=bad, headers=headers)
                    assert response.status_code == 204 and agent.check is None, bad
                await client.post(url + "/agent-events", json=good, headers=headers)
                request = (await until(watcher, lambda message: message["type"] == "check_request"))[-1]
                assert request == {"type": "check_request", "agent": agent.id, "name": "Flights to Manila",
                                   "site": "www.google.com", "what": KINDS["google"], "target": "T1", "live": None}
                assert agent.state == "needs_you" and agent.check["check"] == "google"
                cleared = {"agent": agent.id, "kind": "check_cleared", "target": "T1", "adopted": False,
                           "how": "solved"}
                await client.post(url + "/agent-events", json=cleared, headers=headers)
                assert agent.check is None
    finally:
        await server.stop()


async def test_check_buttons_come_from_our_pages_and_the_watcher_only_continues(fake_claude, tmp_path):
    from ai_browser.app.agents import CONTINUE_TEXT, SKIP_TEXT

    _, log, _ = fake_claude
    server, url = await started(fake_claude, tmp_path, EVENTS)
    server.allow_origin(WATCHER, watcher=True)
    closed = []

    async def close_tabs(targets):
        closed.append(list(targets))

    agents = server.agents
    agents.close_tabs = close_tabs
    try:
        first, second = await agents.create("one"), await agents.create("two")
        for agent in (first, second):
            agents.tab_event(agent.id, "tab_opened", f"T{agent.id}")
            agents.check_event(agent.id, {**CHECK_REPORT, "target": f"T{agent.id}"})
        async with connect(socket_url(server, url), origin=WATCHER) as watcher:
            await watcher.send(json.dumps({"type": "check_skip", "id": first.id}))  # the watcher never closes a tab
            await watcher.send(json.dumps({"type": "check_continue", "id": second.id}))
            await wait_for(lambda: second.check is None)
        assert first.check is not None and closed == []
        async with connect(socket_url(server, url), origin=ORIGIN) as page:
            await page.send(json.dumps({"type": "check_skip", "id": first.id}))
            await wait_for(lambda: first.check is None)
        assert closed == [[f"T{first.id}"]]
        await wait_for(lambda: SKIP_TEXT in told(log) and CONTINUE_TEXT in told(log))
    finally:
        await server.stop()
