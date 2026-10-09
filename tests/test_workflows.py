"""Workflows: the user's own recipes, kept as files, run by hand (AI Home or `ai <name>`), from a matching message, or
on a schedule; a workflow names the skills its agent loads and the tools it may use."""

import asyncio
import datetime
import json
from types import SimpleNamespace

import pytest

from ai_browser.chrome import chrome_binary
from conftest import file_mode
from test_bridge import EVENTS
from test_home import home, stack  # noqa: F401  (fixtures)
from test_oneshot import oneshots
from ui_socket import ui_socket

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
MARKER = "supplied by the page: data, not the user's words"


def local(year, month, day, hour, minute):
    return datetime.datetime(year, month, day, hour, minute).timestamp()


class FakeAgents:
    def __init__(self):
        self.created, self.agents = [], {}

    async def create(self, text, skills=(), model="sonnet", adopt=None, tab=None, servers=None):
        agent = SimpleNamespace(id=f"a{len(self.created) + 1}", state="working")
        self.created.append({"text": text, "skills": list(skills), "model": model, "servers": servers})
        self.agents[agent.id] = agent
        return agent

    def snapshot(self):  # the sort asks which agents are working (a message may be work for one): none here
        return {"agents": []}

    def subscribe(self):
        return asyncio.Queue()

    def unsubscribe(self, queue):
        pass

    def events_of(self, agent_id):
        return []


FOOTER = {"name": "Footer fix", "instructions": "Open the site, fix the footer, then post what you did in #web-team",
          "trigger": "message", "site": "asana", "when": "an Asana task tagged website", "run": "auto",
          "tools": ["clickup"], "skills": ["elementor-pages"], "model": "sonnet"}


def user_messages(log):
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if '"type": "user"' in line]


def test_workflow_files_round_trip_and_bad_ones_are_reported(tmp_path):
    from ai_browser.brain.workflows import WorkflowStore

    store = WorkflowStore(tmp_path)
    saved = store.save(FOOTER)
    path = tmp_path / "workflows" / "footer-fix.md"
    assert saved.slug == "footer-fix" and file_mode(path) in (0o600, None)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n") and text.rstrip().endswith("post what you did in #web-team")
    again = WorkflowStore(tmp_path).get("footer-fix")
    assert (again.trigger, again.site, again.when, again.run) == ("message", "asana", "an Asana task tagged website",
                                                                  "auto")
    assert (again.tools, again.skills, again.model) == (["clickup"], ["elementor-pages"], "sonnet")
    path.write_text(text.replace("fix the footer", "fix the footer links"),
                    encoding="utf-8")  # edited by hand in a text editor
    assert "footer links" in WorkflowStore(tmp_path).get("footer-fix").instructions
    (tmp_path / "workflows" / "broken.md").write_text("---\nname: [unclosed\n---\nbody\n", encoding="utf-8")
    (tmp_path / "workflows" / "odd.md").write_text("---\nname: Odd\ntrigger: sometimes\n---\nbody\n", encoding="utf-8")
    store = WorkflowStore(tmp_path)
    assert [workflow.slug for workflow in store.all()] == ["footer-fix"]
    problems = store.problems()
    assert any(problem.startswith("broken.md:") for problem in problems)
    assert any(problem.startswith("odd.md:") for problem in problems)
    assert store.save({**FOOTER, "trigger": "manual"}).slug == "footer-fix-2"  # a new one never replaces another
    store.save({**FOOTER, "slug": "footer-fix", "instructions": "Edited in AI Home"})  # editing keeps its file
    assert store.get("footer-fix").instructions == "Edited in AI Home"
    for bad in ({**FOOTER, "name": ""}, {**FOOTER, "trigger": "schedule", "schedule": "whenever"},
                {**FOOTER, "model": "gpt"}, {**FOOTER, "skills": ["../evil"]}, {**FOOTER, "instructions": ""}):
        with pytest.raises(ValueError):
            store.save(bad)
    store.delete("footer-fix-2")
    assert store.get("footer-fix-2") is None and not (tmp_path / "workflows" / "footer-fix-2.md").exists()


def test_schedules():
    from ai_browser.brain.workflows import Schedule

    for text in ("daily 09:00", "weekdays 09:00", "mon 08:30", "mon,wed,fri 17:45", "every 2h", "every 30m"):
        Schedule.parse(text)
    for bad in ("weekly", "every 5m", "daily 25:00", "every 0h", "tuesday 9:00", "", "mon"):
        with pytest.raises(ValueError):
            Schedule.parse(bad)
    weekdays = Schedule.parse("weekdays 09:00")
    monday = local(2026, 10, 5, 9, 0)  # 5 October 2026 is a Monday
    assert weekdays.due(monday - 60, monday + 1)
    assert not weekdays.due(local(2026, 10, 3, 8, 0), local(2026, 10, 3, 10, 0))  # a Saturday
    assert not weekdays.due(monday + 1, monday + 3600)  # already ran this morning
    weekly = Schedule.parse("mon 08:30")
    assert weekly.due(local(2026, 10, 4, 12, 0), local(2026, 10, 5, 8, 31))
    assert not weekly.due(local(2026, 10, 5, 8, 31), local(2026, 10, 11, 23, 0))
    every = Schedule.parse("every 2h")
    assert not every.due(1000, 1000 + 3600) and every.due(1000, 1000 + 7200)


async def test_a_schedule_never_piles_up(tmp_path):
    from ai_browser.brain.workflows import WorkflowRunner, WorkflowStore

    store = WorkflowStore(tmp_path)
    store.save({"name": "Morning report", "instructions": "Check the inbox and report", "trigger": "schedule",
                "schedule": "every 1h"})
    clock = [local(2026, 10, 5, 9, 0)]
    agents = FakeAgents()
    runner = WorkflowRunner(store, agents, clock=lambda: clock[0])
    await runner.tick()  # the first tick starts the clock: nothing missed before is caught up
    assert agents.created == []
    clock[0] += 3600
    await runner.tick()
    assert len(agents.created) == 1
    agents.agents["a1"].state = "needs_you"  # waiting on a permission, overnight
    clock[0] += 3600
    await runner.tick()
    assert len(agents.created) == 1 and "still" in runner.notes["morning-report"]
    agents.agents["a1"].state = "your_turn"
    clock[0] += 3600
    await runner.tick()
    assert len(agents.created) == 2
    agents.agents["a2"].state = "your_turn"
    clock[0] += 3 * 86400  # the app was asleep for three days
    await runner.tick()
    assert len(agents.created) == 3  # once, not 72 times


async def test_a_message_workflow_is_offered_or_runs_right_away(fake_claude, tmp_path):
    from ai_browser.brain.service import BrainService
    from ai_browser.brain.store import BrainStore
    from ai_browser.brain.workflows import WorkflowRunner, WorkflowStore

    runner_bin, log, script = fake_claude
    verdicts = [{"id": "asana:1", "kind": "new", "summary": "A website task", "why": "", "suggest": "agent",
                 "workflow": "site-fix"},
                {"id": "asana:2", "kind": "new", "summary": "Something else", "why": "", "suggest": "tell",
                 "workflow": "made-up"},
                {"id": "asana:3", "kind": "new", "summary": "Another website task", "why": "", "suggest": "agent",
                 "workflow": "site-fix"}]
    script.write_text(json.dumps([{"result": json.dumps(verdicts)}]), encoding="utf-8")
    workflows = WorkflowStore(tmp_path / "home")
    workflows.save({"name": "Site fix", "instructions": "Fix what the task asks on the website", "trigger": "message",
                    "site": "asana", "when": "a task tagged website", "run": "ask"})
    agents = FakeAgents()
    brain = BrainService(BrainStore(tmp_path / "home"), agents, claude=runner_bin, batch_wait=0.1)
    brain.workflows, brain.runner = workflows, WorkflowRunner(workflows, agents)
    sent = []
    brain.outbox = lambda message: sent.append(message) or True
    brain.set_watch({"site": "asana", "enabled": True, "url_match": "https://app.asana.com/*"})

    def raw(raw_id):
        return {"id": raw_id, "from": "Ana", "subject": f"Task {raw_id}", "snippet": "Please fix the footer",
                "url": f"https://app.asana.com/1/1/task/{raw_id}"}

    await brain.on_items("asana", [raw("1"), raw("2")])
    await brain.settle()
    prompt = oneshots(log)[0]["oneshot"]
    assert "site-fix: a task tagged website" in prompt and prompt.index("site-fix") < prompt.index(MARKER)
    assert brain.store.get("asana:1").workflow == "site-fix" and brain.store.get("asana:2").workflow is None
    assert brain.store.get("asana:1").public()["workflow_name"] == "Site fix"  # Run shows the name
    assert agents.created == []  # "ask me first": offered as Run Site fix
    await brain.run_workflow("asana:1", "site-fix")
    text = agents.created[0]["text"]
    assert text.startswith("Fix what the task asks on the website") and text.index(MARKER) < text.index("footer")
    assert brain.store.get("asana:1").state == "agent"
    workflows.save({"slug": "site-fix", "name": "Site fix", "instructions": "Fix what the task asks on the website",
                    "trigger": "message", "site": "asana", "when": "a task tagged website", "run": "auto"})
    await brain.on_items("asana", [raw("3")])
    await brain.settle()
    item = brain.store.get("asana:3")
    assert len(agents.created) == 2 and item.state == "agent" and item.note == "Started Site fix"
    assert [message for message in sent if message["type"] == "notify"][-1]["items"][0]["note"] == "Started Site fix"


async def test_reading_turned_off_during_a_sort_keeps_nothing_of_that_batch(fake_claude, tmp_path):  # Review Focus 2
    """Settings → Brain's switch goes off while Claude sorts a batch: the batch is dropped when the answer comes, so
    nothing is listed, nothing is notified, and a workflow set to run right away doesn't start."""
    from ai_browser.brain.oneshot import OneShot
    from ai_browser.brain.service import BrainService
    from ai_browser.brain.store import BrainStore
    from ai_browser.brain.workflows import WorkflowRunner, WorkflowStore

    runner_bin, _, _ = fake_claude
    workflows = WorkflowStore(tmp_path / "home")
    workflows.save({"name": "Site fix", "instructions": "Fix what the task asks on the website", "trigger": "message",
                    "site": "asana", "when": "a task tagged website", "run": "auto"})
    agents = FakeAgents()
    brain = BrainService(BrainStore(tmp_path / "home"), agents, claude=runner_bin, batch_wait=0.05)
    brain.workflows, brain.runner = workflows, WorkflowRunner(workflows, agents)
    sent = []
    brain.outbox = lambda message: sent.append(message) or True
    brain.set_watch({"site": "asana", "enabled": True, "url_match": "https://app.asana.com/*"})
    asked, answer = asyncio.Event(), asyncio.Event()

    async def slow_ask(prompt, **options):  # Claude, sorting while the user turns the switch off
        asked.set()
        await answer.wait()
        return OneShot(text=json.dumps([{"id": "asana:1", "kind": "needs_reply", "summary": "A website task",
                                         "why": "", "suggest": "agent", "workflow": "site-fix"}]))

    brain.ask = slow_ask
    await brain.on_items("asana", [{"id": "1", "from": "Ana", "subject": "Task 1", "snippet": "Please fix the footer",
                                    "url": "https://app.asana.com/1/1/task/1"}])
    await asyncio.wait_for(asked.wait(), 5)
    brain.set_reading("off")
    answer.set()
    await brain.settle()
    assert brain.snapshot()["items"] == [] and sent == [] and agents.created == []
    assert brain.store.get("asana:1") is None


async def test_run_by_hand_over_the_socket(fake_claude, tmp_path):
    from websockets.asyncio.client import connect

    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer
    from ai_browser.brain.workflows import WorkflowRunner, WorkflowStore

    runner_bin, log, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    home = tmp_path / "home"
    agents = AgentManager(home, claude=runner_bin)
    workflows = WorkflowStore(home)
    server = AppServer(home, agents, workflows=workflows, runner=WorkflowRunner(workflows, agents))
    url = await server.start()

    async def until(ws, accept):
        while True:
            message = json.loads(await asyncio.wait_for(ws.recv(), 10))
            if accept(message):
                return message

    try:
        async with ui_socket(server, url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "home"}))
            await ws.send(json.dumps({"type": "workflow_save", "request": "s1",
                                      **{**FOOTER, "trigger": "manual", "tools": []}}))
            saved = await until(ws, lambda m: m["type"] == "workflow_saved")
            assert saved["slug"] == "footer-fix" and saved["path"].endswith("workflows/footer-fix.md")
            snapshot = await until(ws, lambda m: m["type"] == "workflows_snapshot")
            assert [workflow["name"] for workflow in snapshot["workflows"]] == ["Footer fix"]
            await ws.send(json.dumps({"type": "workflow_save", "request": "s2", "name": "", "instructions": "x"}))
            assert (await until(ws, lambda m: m["type"] == "error"))["request"] == "s2"
            await ws.send(json.dumps({"type": "workflow_run", "slug": "footer-fix", "text": "the header",
                                      "request": "r1"}))
            created = await until(ws, lambda m: m["type"] == "created")
            assert created["request"] == "r1"
            await until(ws, lambda m: m["type"] == "agent" and m["agent"]["state"] == "your_turn")
        content = user_messages(log)[0]["message"]["content"]
        assert "elementor-pages" not in content  # not installed here: Load at start skips it, with a note on the run
        assert {"type": "note", "text": "Not loaded, no longer installed: elementor-pages"} in server.agents.events_of(
            created["id"])
        assert "Open the site, fix the footer" in content and content.rstrip().endswith("The user adds: the header")
    finally:
        await server.stop()


async def test_a_workflow_loads_its_skills_and_only_its_tools(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager
    from ai_browser.brain.tools import ToolsConfig
    from ai_browser.brain.workflows import WorkflowRunner, WorkflowStore
    from test_tools import INIT, RESULT, user_config

    runner_bin, log, script = fake_claude
    script.write_text(json.dumps([INIT, RESULT]), encoding="utf-8")
    home = tmp_path / "home"
    tools = ToolsConfig(home, claude_home=user_config(tmp_path))
    tools.set_enabled("figma", True)
    tools.set_enabled("clickup", True)
    agents = AgentManager(home, claude=runner_bin)
    agents.tools = tools
    store = WorkflowStore(home)
    store.save({**FOOTER, "trigger": "manual", "tools": ["figma"]})
    agent_id = await WorkflowRunner(store, agents).run("footer-fix")
    for _ in range(100):
        if agents.agents[agent_id].state == "your_turn":
            break
        await asyncio.sleep(0.05)
    servers = json.loads((home / "app" / "agents" / agent_id / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert set(servers) == {"ai-browser", "figma"}  # clickup is on, but not in this workflow's list
    assert user_messages(log)[0]["message"]["content"].startswith(
        "Load and use these skills with load_skill: elementor-pages")
    await agents.close_all()


def test_workflows_and_skills_keep_arrows_emoji_and_cjk(tmp_path):
    from ai_browser.brain.skillwriter import SkillWriter
    from ai_browser.brain.workflows import WorkflowStore

    store = WorkflowStore(tmp_path)
    saved = store.save({"name": "Morning → report 🚀", "instructions": "Check 日本語 mail\nthen tell me"})
    raw = (tmp_path / "workflows" / f"{saved.slug}.md").read_bytes()
    assert b"\r\n" not in raw and "→".encode("utf-8") in raw
    assert store.get(saved.slug).name == "Morning → report 🚀"
    skills = SkillWriter(tmp_path / "skills")
    text = "---\nname: notes\ndescription: Takes notes → fast 🚀\n---\nWrite 日本語 notes.\n"
    path = skills.save(text)
    assert path.read_bytes() == text.encode("utf-8")


def test_files_saved_by_notepad_load_like_the_macs(tmp_path):
    from ai_browser.brain.workflows import WorkflowStore
    from ai_browser.skills import Catalog, SkillSource

    store = WorkflowStore(tmp_path)
    store.folder.mkdir(parents=True)
    (store.folder / "morning.md").write_bytes(  # UTF-8 with a BOM, and CRLF line ends
        "﻿---\r\nname: Morning → report 🚀\r\ntrigger: manual\r\n---\r\nCheck 日本語 mail\r\n".encode("utf-8"))
    assert [(w.slug, w.name, w.instructions) for w in store.all()] == [
        ("morning", "Morning → report 🚀", "Check 日本語 mail")]
    assert store.problems() == []
    folder = tmp_path / "skills" / "notes"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_bytes(
        "﻿---\r\nname: notes\r\ndescription: Takes notes — fast\r\n---\r\nBody\r\n".encode("utf-8"))
    catalog = Catalog([SkillSource("personal", tmp_path / "skills", "/skills/personal", "*/SKILL.md")], set())
    [skill] = catalog.all()
    assert (skill.name, skill.description) == ("notes", "Takes notes — fast")
    assert catalog.load("notes").rstrip().endswith("Body")


def test_deleting_a_workflow_waits_out_a_short_hold(tmp_path, monkeypatch):
    from pathlib import Path

    from ai_browser import platforms
    from ai_browser.brain.workflows import WorkflowStore

    store = WorkflowStore(tmp_path)
    saved = store.save({"name": "Morning report", "instructions": "Check the inbox"})
    real, held = Path.unlink, []

    def busy_once(self, missing_ok=False):
        if not held:
            held.append(self)
            raise PermissionError(13, "open in an editor")
        return real(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", busy_once)
    monkeypatch.setattr(platforms.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(platforms, "WINDOWS", True)
    store.delete(saved.slug)
    assert held and store.get(saved.slug) is None


def test_a_schedules_moments_for_the_calendar():
    from ai_browser.brain.workflows import Schedule

    monday = local(2026, 10, 5, 0, 0)  # a Monday, local time
    week = monday + 7 * 86400
    weekdays = Schedule.parse("weekdays 09:00").moments(monday, monday, week)
    assert [datetime.datetime.fromtimestamp(moment).strftime("%a %H:%M") for moment in weekdays] == [
        "Mon 09:00", "Tue 09:00", "Wed 09:00", "Thu 09:00", "Fri 09:00"]
    assert len(Schedule.parse("daily 09:00").moments(monday, monday, week, most=3)) == 3
    every = Schedule.parse("every 2h")
    assert every.moments(monday, monday, monday + 7 * 3600) == [monday + 7200, monday + 14400, monday + 21600]
    assert every.moments(monday, monday + 3 * 3600, monday + 5 * 3600) == [monday + 14400]  # from the last run
    assert every.moments(monday, monday, week, most=1) == [monday + 7200]


def test_the_runner_lists_the_next_runs_of_scheduled_templates(tmp_path):
    from ai_browser.brain.workflows import WorkflowRunner, WorkflowStore

    store = WorkflowStore(tmp_path)
    store.save({"name": "Morning report", "instructions": "Write it", "trigger": "schedule",
                "schedule": "daily 09:00"})
    store.save({"name": "Check often", "instructions": "Check", "trigger": "schedule", "schedule": "every 2h"})
    store.save({"name": "By hand", "instructions": "Do it"})
    now = local(2026, 10, 5, 8, 0)
    rows = {row["slug"]: row for row in WorkflowRunner(store, None, clock=lambda: now).upcoming()}
    assert set(rows) == {"morning-report", "check-often"}
    morning = rows["morning-report"]
    assert morning["runs"][0] == local(2026, 10, 5, 9, 0) and 61 <= len(morning["runs"]) <= 63
    assert morning["every"] is None and morning["schedule"] == "daily 09:00"
    assert rows["check-often"] == {"slug": "check-often", "name": "Check often", "schedule": "every 2h",
                                   "every": 7200, "runs": [now + 7200], "runs_as": ""}  # a new agent's


async def test_pages_get_the_next_runs_with_the_workflows(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer
    from ai_browser.brain.workflows import WorkflowRunner, WorkflowStore

    home = tmp_path / "home"
    agents = AgentManager(home, claude=fake_claude[0])
    workflows = WorkflowStore(home)
    workflows.save({"name": "Morning report", "instructions": "Write it", "trigger": "schedule",
                    "schedule": "daily 09:00"})
    server = AppServer(home, agents, workflows=workflows, runner=WorkflowRunner(workflows, agents))
    url = await server.start()
    try:
        async with ui_socket(server, url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "mission"}))
            await ws.send(json.dumps({"type": "workflows"}))
            while True:
                message = json.loads(await asyncio.wait_for(ws.recv(), 10))
                if message["type"] == "workflows_snapshot":
                    break
            [row] = message["next_runs"]
            assert row["slug"] == "morning-report" and len(row["runs"]) >= 61
    finally:
        await server.stop()
