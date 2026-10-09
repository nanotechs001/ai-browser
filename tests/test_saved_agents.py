"""Saved agents (the saved-agents spec, 1 to 3): an agent the user sets up once and runs many times. Its file in
<home>/agents (fields, limits, cleaning, mode 0600), saved and deleted only by AI Browser's own pages, and what its
runs get: its instruction in the system prompt, its skills. On the fake claude, in throwaway folders."""

import re

import pytest

from conftest import file_mode

AGENT = {"name": "Research", "description": "Pricing pages of the three biggest rivals",
         "instruction": "Always answer in French.\nKeep a table of every price.", "web": "brave", "model": "opus",
         "auto_approve": True, "can_use": ["personal:prices", "personal:tables"], "load_at_start": ["personal:prices"]}


def test_a_saved_agent_is_a_file_of_its_own(tmp_path):
    from ai_browser.app.savedagents import SavedAgents

    store = SavedAgents(tmp_path / "home")
    saved = store.save(AGENT)
    path = tmp_path / "home" / "agents" / "research.md"
    assert saved.slug == "research" and path.is_file() and file_mode(path) in (0o600, None)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\nname: Research\n") and text.endswith("Always answer in French.\nKeep a table of "
                                                                      "every price.\n")  # the body is its instruction
    again = store.get("research")
    assert again == saved and again.public() == {
        "slug": "research", "name": "Research", "description": "Pricing pages of the three biggest rivals",
        "instruction": "Always answer in French.\nKeep a table of every price.", "profile": None, "web": "brave",
        "model": "opus", "account": None, "folder": None, "auto": True, "use": ["personal:prices", "personal:tables"],
        "load": ["personal:prices"]}
    assert store.save({**AGENT, "description": ""}).slug == "research-2"  # a new one never takes another's file
    edited = store.save({**AGENT, "slug": "research", "name": "Rivals"})
    assert edited.slug == "research" and store.get("research").name == "Rivals"  # an edit keeps its file
    assert [one.slug for one in store.all()] == ["research-2", "research"]  # by name: Research, Rivals
    assert store.delete("research") is True and store.get("research") is None and not path.exists()
    assert store.delete("research") is False
    with pytest.raises(ValueError, match="There is no such agent"):  # deleted meanwhile: an edit makes nothing
        store.save({**AGENT, "slug": "research"})


@pytest.mark.parametrize(("fields", "error"), [
    ({"name": ""}, "An agent needs a name"),
    ({"name": "‮​"}, "An agent needs a name"),
    ({"name": "n" * 61}, "An agent's name is at most 60 characters"),
    ({"description": "d" * 161}, "What it works on is at most 160 characters"),
    ({"instruction": "i" * 8001}, "The instruction is at most 8,000 characters"),
    ({"model": "gpt"}, "The model is opus, sonnet or haiku"),
    ({"web": "everything"}, "Web is Web + Brave, Brave only or No web"),
    ({"can_use": ["prices"]}, "Pick the skills from the list"),
    ({"load_at_start": "personal:prices"}, "Pick the skills from the list"),
    ({"profile": 7}, "Pick one of the profiles listed"),
    ({"account": ["a"]}, "Pick one of the accounts listed"),
    ({"folder": 3}, "Pick a folder"),
    ({"auto_approve": "yes"}, "Auto-approve is on or off"),
])
def test_refused_values_save_nothing(tmp_path, fields, error):
    from ai_browser.app.savedagents import SavedAgents

    store = SavedAgents(tmp_path / "home")
    with pytest.raises(ValueError, match=re.escape(error)):
        store.save({**AGENT, **fields})
    assert store.all() == []


def test_names_are_one_line_and_the_instruction_keeps_its_lines(tmp_path):
    from ai_browser.app.savedagents import SavedAgents

    store = SavedAgents(tmp_path / "home")
    saved = store.save({"name": "  Re\u0007search‮  rivals ", "description": "One\nline",
                        "instruction": "First\r\nsecond​‮\tthird\x00 fourth﻿",
                        "can_use": [], "load_at_start": ["personal:prices"]})
    assert (saved.name, saved.description) == ("Research rivals", "One line")
    assert saved.instruction == "First\nsecond third\nfourth"  # line breaks kept; control and format marks dropped
    assert (saved.web, saved.model, saved.auto, saved.use, saved.load) == ("web", "sonnet", False, [],
                                                                         ["personal:prices"])  # the defaults
    narrow = store.save({**AGENT, "can_use": ["personal:tables"], "load_at_start": ["personal:prices"]})
    assert narrow.use == ["personal:prices", "personal:tables"]  # what it loads at start it may use
    assert store.save({**AGENT, "instruction": "i" * 8000}).instruction == "i" * 8000  # at the limit


def test_a_file_written_by_hand_is_read_and_a_broken_one_skipped(tmp_path):
    from ai_browser.app.savedagents import SavedAgents

    folder = tmp_path / "home" / "agents"
    folder.mkdir(parents=True)
    (folder / "helper.md").write_text("﻿---\nname: Helper\nmodel: haiku\n---\nBe brief.\n", encoding="utf-8")
    (folder / "broken.md").write_text("no front matter", encoding="utf-8")
    (folder / "Bad Name.md").write_text("---\nname: Bad\n---\n", encoding="utf-8")
    store = SavedAgents(tmp_path / "home")
    assert [(one.slug, one.name, one.model, one.instruction) for one in store.all()] == [
        ("helper", "Helper", "haiku", "Be brief.")]
    assert store.get("broken") is None and store.get("../workflows/x") is None
    with pytest.raises(ValueError, match="There is no such agent"):
        store.save({**AGENT, "slug": "../x"})


# ---- saved and deleted over the socket, by AI Browser's own pages only (Task 2) -------------------------------------

async def test_the_agents_page_saves_lists_and_deletes_agents(fake_claude, tmp_path):
    import json

    from fake_brave import FakeBrave
    from test_app_server import started, until
    from test_bridge import EVENTS
    from ui_socket import ui_socket

    server, url = await started(fake_claude, tmp_path, EVENTS)
    brave = FakeBrave([])
    brave.place.listed = [{"folder": "Profile 1", "name": "Work", "color": "#1a73e8"}]
    server.attach_brave(brave)
    try:
        async with ui_socket(server, url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "mission"}))
            await until(ws, lambda m: m["type"] == "snapshot")
            await ws.send(json.dumps({"type": "saved_agent_save", "request": "s1", **AGENT, "profile": "Profile 1"}))
            saved = await until(ws, lambda m: m["type"] == "saved_agent_saved")
            listed = await until(ws, lambda m: m["type"] == "saved_agents")  # every page hears the new list
            assert saved[-1] == {"type": "saved_agent_saved", "request": "s1", "slug": "research"}
            assert [(row["slug"], row["profile"], row["instruction"]) for row in listed[-1]["agents"]] == [
                ("research", "Profile 1", AGENT["instruction"])]
            for refused, words in ((dict(profile="Profile 9"), "Pick one of the profiles listed"),
                                   (dict(profile=["Profile 1"]), "Pick one of the profiles listed"),
                                   (dict(account="acct-gone"), "Pick one of the accounts listed"),
                                   (dict(name="n" * 61), "An agent's name is at most 60 characters"),
                                   (dict(folder=str(tmp_path / "home")), "AI Browser's own folder")):
                await ws.send(json.dumps({"type": "saved_agent_save", "request": "s2", **AGENT, **refused}))
                error = await until(ws, lambda m: m["type"] == "error" and m.get("request") == "s2")
                assert words in error[-1]["text"], error[-1]
            assert [one.slug for one in server.saved.all()] == ["research"]  # nothing refused was written
            await ws.send(json.dumps({"type": "saved_agent_delete", "slug": "research", "request": "d1"}))
            listed = await until(ws, lambda m: m["type"] == "saved_agents")
            assert listed[-1]["agents"] == [] and server.saved.all() == []
            await ws.send(json.dumps({"type": "saved_agents"}))
            assert (await until(ws, lambda m: m["type"] == "saved_agents"))[-1]["agents"] == []
    finally:
        await server.stop()


def test_saving_and_deleting_an_agent_are_app_only_rows():
    from ai_browser.app.server import MESSAGE_RULES, may_send

    for kind in ("saved_agents", "saved_agent_save", "saved_agent_delete"):
        assert MESSAGE_RULES[kind].app and may_send("app", {"type": kind})
        assert not may_send("watcher", {"type": kind}) and not may_send("none", {"type": kind})


# ---- its instruction, in its system prompt (Task 3) -------------------------------------------------------------------

def launches(log) -> list[list[str]]:
    """The argv of each Claude Code process the fake claude ran (its first log line each time)."""
    import json

    lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    return [line for line in lines if isinstance(line, list)]


async def test_its_instruction_reaches_its_system_prompt_and_nothing_else(fake_claude, tmp_path):
    import json

    from ai_browser.app.agents import AgentManager
    from ai_browser.app.bridge import BRAVE_PROMPT, INSTRUCTION_LINE
    from ai_browser.app.savedagents import SavedAgents
    from test_app_server import told, wait_for
    from test_bridge import EVENTS

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    saved = SavedAgents(tmp_path / "home").save({**AGENT, "instruction": "Answer in French.\nNever buy anything."})
    manager = AgentManager(tmp_path / "home", claude=runner)
    try:
        run = await manager.create("List the prices", saved_agent=saved)
        await wait_for(lambda: run.state == "your_turn")
        assert run.saved == "research" and manager.snapshot()["agents"][0]["saved"] == "research"
        argv = launches(log)[0]
        prompt = argv[argv.index("--append-system-prompt") + 1]
        assert INSTRUCTION_LINE == "The user's standing instruction for this agent:"
        assert prompt == f"{BRAVE_PROMPT}\n\n{INSTRUCTION_LINE}\nAnswer in French.\nNever buy anything."
        assert "Answer in French" not in " ".join(told(log))  # only the task is its message
        log.write_text("", encoding="utf-8")
        plain = await manager.create("Fix the footer")  # a one-off run: AI Browser's own prompt alone
        await wait_for(lambda: plain.state == "your_turn")
        argv = launches(log)[0]
        assert argv[argv.index("--append-system-prompt") + 1] == BRAVE_PROMPT and plain.saved == ""
    finally:
        await manager.close_all()


def test_the_bridge_cleans_the_instruction_once_more():
    from ai_browser.app.bridge import BRAVE_PROMPT, INSTRUCTION_LINE, ClaudeBridge

    bridge = ClaudeBridge("home", instruction="Be brief\x00‮.\r\nThanks")
    assert bridge.system_prompt() == f"{BRAVE_PROMPT}\n\n{INSTRUCTION_LINE}\nBe brief.\nThanks"
    assert ClaudeBridge("home", instruction="  ​ ").system_prompt() == BRAVE_PROMPT


# ---- Can use: enforced by AI Browser's own skill tools (Task 4) --------------------------------------------------------

async def test_can_use_is_enforced_by_ai_browsers_own_skill_tools(tmp_path, monkeypatch):
    import json

    from ai_browser.engine import Engine
    from ai_browser.skills import NOT_ALLOWED, Catalog, SkillSource
    from test_skills import make_skill

    root = tmp_path / "skills"
    make_skill(root, "prices", desc="Read price pages", scripts=True)
    make_skill(root, "tables", desc="Keep tables of prices")
    make_skill(root, "secrets", desc="Prices of the secret plans")

    def engine():
        source = SkillSource("personal", root, "/skills/personal", "*/SKILL.md")
        return Engine(home=tmp_path / "home", catalog=Catalog([source], set()))

    assert NOT_ALLOWED == "This agent can't use that skill: change it in its settings"
    monkeypatch.setenv("AIB_APP_SKILLS", json.dumps(["personal:prices", "personal:tables"]))
    only = engine()
    found = (await only.find_skills("prices")).text
    assert "personal:prices" in found and "personal:tables" in found and "secrets" not in found
    assert "secrets" not in (await only.find_skills("")).text  # the whole list too
    for call in (only.load_skill("personal:secrets"), only.load_skill("secrets"),
                 only.read_skill_file("personal:secrets", "SKILL.md")):
        assert (await call).text.startswith(f"error: {NOT_ALLOWED}")
    assert "Read price pages" in (await only.load_skill("prices")).text  # one it may use loads as before
    assert (await only.read_skill_file("personal:prices", "scripts/run.py")).text.startswith("print('hi')")
    assert (await only.load_skill("personal:nothing")).text.startswith("error: no skill")  # not installed: as before
    assert (await only.read_skill_file("secrets", "SKILL.md")).text.startswith(f"error: {NOT_ALLOWED}")  # short name
    make_skill(tmp_path / "a", "prices", desc="Prices from A")
    make_skill(tmp_path / "b", "prices", desc="Prices from B")
    twins = [SkillSource(space, tmp_path / space, f"/skills/{space}", "*/SKILL.md") for space in ("a", "b")]
    monkeypatch.setenv("AIB_APP_SKILLS", json.dumps(["a:prices"]))
    same = Engine(home=tmp_path / "home", catalog=Catalog(twins, set()))
    assert (await same.load_skill("b:prices")).text.startswith(f"error: {NOT_ALLOWED}")
    loaded = (await same.load_skill("prices")).text  # one short name, two skills: the one it may use
    assert "Prices from A" in loaded and "Prices from B" not in loaded
    monkeypatch.setenv("AIB_APP_SKILLS", "[]")  # none named: every skill
    assert "secrets" in (await engine().find_skills("prices")).text
    monkeypatch.setenv("AIB_APP_SKILLS", "not json")  # broken: no skill at all, never every skill
    assert (await engine().load_skill("personal:prices")).text.startswith(f"error: {NOT_ALLOWED}")


async def test_a_run_tells_its_tools_which_skills_it_may_use(fake_claude, tmp_path):
    import json

    from ai_browser.app.agents import AgentManager
    from ai_browser.app.savedagents import SavedAgents
    from test_app_server import wait_for
    from test_bridge import EVENTS

    runner, _, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    store = SavedAgents(tmp_path / "home")
    narrow, every = store.save(AGENT), store.save({**AGENT, "can_use": [], "load_at_start": []})
    manager = AgentManager(tmp_path / "home", claude=runner)

    def tools_env(agent_id):
        config = tmp_path / "home" / "app" / "agents" / agent_id / "mcp.json"
        return json.loads(config.read_text(encoding="utf-8"))["mcpServers"]["ai-browser"]["env"]

    try:
        one, two, three = (await manager.create("a", saved_agent=narrow), await manager.create("b", saved_agent=every),
                           await manager.create("c"))
        await wait_for(lambda: all(agent.state == "your_turn" for agent in (one, two, three)))
        assert json.loads(tools_env("a1")["AIB_APP_SKILLS"]) == ["personal:prices", "personal:tables"]
        assert "AIB_APP_SKILLS" not in tools_env("a2") and "AIB_APP_SKILLS" not in tools_env("a3")  # every skill
    finally:
        await manager.close_all()


def test_an_edit_never_writes_over_a_file_it_cannot_read(tmp_path):
    from ai_browser.app.savedagents import SavedAgents

    folder = tmp_path / "home" / "agents"
    folder.mkdir(parents=True)
    (folder / "broken.md").write_bytes(b"no front matter")
    with pytest.raises(ValueError, match="There is no such agent"):
        SavedAgents(tmp_path / "home").save({**AGENT, "slug": "broken"})
    assert (folder / "broken.md").read_bytes() == b"no front matter"


def test_every_line_break_kind_becomes_a_line_break():
    from ai_browser.app.savedagents import clean_instruction

    assert clean_instruction("a\u2029b") == "a\nb" and clean_instruction("c\rd") == "c\nd"


# ---- Load at start: the skills' own text in the run's first message (Task 5) -----------------------------------------

def skill_catalog(tmp_path):
    from ai_browser.skills import Catalog, SkillSource
    from test_skills import make_skill

    root = tmp_path / "skills"
    make_skill(root, "prices", desc="Read price pages", body="Open every pricing page. Run ${CLAUDE_SKILL_DIR}/x.py")
    make_skill(root, "tables", desc="Keep tables", body="One row per plan.")
    make_skill(root, "big", desc="A long one", body="b" * 60_001)
    return Catalog([SkillSource("personal", root, "/skills/personal", "*/SKILL.md")], set())


def test_load_at_start_fits_its_cap_and_names_the_rest():
    from ai_browser.app.agents import PRELOAD_LINE, preload

    class Skills:  # a catalog: load() as load_skill gives it
        def load(self, ref, host=False):
            if ref == "personal:gone":
                raise KeyError(ref)
            return f"skill {ref}\n\n" + "x" * 30

    block, loaded, later, gone = preload(Skills(), ["personal:a", "personal:gone", "personal:b", "personal:a"], 90)
    assert PRELOAD_LINE == "Skills the user loaded for you:"
    assert block == f"{PRELOAD_LINE}\n\nskill personal:a\n\n{'x' * 30}"  # each once, as long as they fit
    assert (loaded, later, gone) == (["personal:a"], ["personal:b"], ["personal:gone"])
    assert preload(Skills(), [], 90) == ("", [], [], [])


async def test_load_at_start_goes_before_the_task_and_never_into_the_chat(fake_claude, tmp_path):
    import json

    from ai_browser.app.agents import AgentManager
    from ai_browser.app.savedagents import SavedAgents
    from test_app_server import told, wait_for
    from test_bridge import EVENTS

    runner, _, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    catalog = skill_catalog(tmp_path)
    saved = SavedAgents(tmp_path / "home").save({**AGENT, "can_use": [], "load_at_start": [
        "personal:prices", "personal:gone", "personal:big", "personal:tables"]})
    manager = AgentManager(tmp_path / "home", claude=runner)
    manager.catalog = lambda: catalog
    try:
        run = await manager.create("List the prices", skills=saved.load, saved_agent=saved)
        await wait_for(lambda: run.state == "your_turn")
        first = told(fake_claude[1])[0]
        assert first.startswith("Load and use these skills with load_skill: personal:big\n"  # past the cap
                                "Skills the user loaded for you:\n\nskill personal:prices · sandbox folder "
                                "/skills/personal/prices (read-only)\ndescription: Read price pages")
        assert "Run /skills/personal/prices/x.py" in first  # paths as load_skill gives them
        assert "One row per plan." in first and first.endswith("\n\nList the prices") and "b" * 1000 not in first
        events = manager.events_of(run.id)
        assert [event["text"] for event in events if event["type"] == "user"] == ["List the prices"]  # the chat
        assert {"type": "note", "text": "Not loaded, no longer installed: personal:gone"} in events
        assert run.loaded_skills == ["personal:prices", "personal:tables"]
        await manager.send(run.id, "and the yearly ones")
        await wait_for(lambda: len(told(fake_claude[1])) == 2 and run.state == "your_turn")
        assert told(fake_claude[1])[1] == "and the yearly ones"  # only the first message carries them
    finally:
        await manager.close_all()


async def test_load_at_start_names_the_skills_own_folder_when_docker_doesnt_answer(fake_claude, tmp_path,
                                                                                  monkeypatch):
    import json

    import ai_browser.app.agents as agents_module
    from ai_browser.app.agents import AgentManager
    from test_app_server import told, wait_for
    from test_bridge import EVENTS

    monkeypatch.setattr(agents_module, "docker_answers", lambda home: False)  # as load_skill: its own folder, then
    runner, _, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    catalog = skill_catalog(tmp_path)
    manager = AgentManager(tmp_path / "home", claude=runner)
    manager.catalog = lambda: catalog
    try:
        run = await manager.create("List the prices", skills=["personal:prices"])
        await wait_for(lambda: run.state == "your_turn")
        first = told(fake_claude[1])[0]
        folder = catalog.get("personal:prices").host_dir.as_posix()
        assert first.startswith(f"Skills the user loaded for you:\n\nskill personal:prices · folder {folder} · Run its "
                                "scripts with your own commands (Bash), from your task's folder.")
        assert f"Run {folder}/x.py" in first and "/skills/personal" not in first
    finally:
        await manager.close_all()


# ---- running a saved agent: its settings apply, one run at a time (Task 6) --------------------------------------------

async def test_a_task_for_a_saved_agent_starts_its_run_or_goes_to_the_one_at_work(fake_claude, tmp_path):
    import json

    from test_app_server import started, until, wait_for
    from test_bridge import EVENTS
    from ui_socket import ui_socket

    server, url = await started(fake_claude, tmp_path, [EVENTS[0], {"sleep": 30}])  # its run stays at work
    agents = server.agents
    saved = server.saved.save({**AGENT, "auto_approve": True})
    calm = server.saved.save({**AGENT, "name": "Calm", "auto_approve": False})
    try:
        async with ui_socket(server, url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "mission"}))
            await until(ws, lambda m: m["type"] == "snapshot")
            await ws.send(json.dumps({"type": "new_task", "agent": saved.slug, "text": "List the prices",
                                      "name": "Not this", "model": "haiku", "web": "none", "request": "m1"}))
            created = await until(ws, lambda m: m["type"] == "created" and m.get("request") == "m1")
            run = agents.agents[created[-1]["id"]]
            assert (run.saved, run.name, run.description, run.model, run.web, run.auto) == (
                "research", "Research", AGENT["description"], "opus", "brave", True)  # its settings, not the box's
            await wait_for(lambda: run.state == "working")
            await ws.send(json.dumps({"type": "new_task", "agent": saved.slug, "text": "Add the yearly plans",
                                      "request": "m2"}))
            again = await until(ws, lambda m: m["type"] == "created" and m.get("request") == "m2")
            assert again[-1]["id"] == run.id and list(agents.agents) == [run.id]  # one run at a time: a message
            await wait_for(lambda: run.queued == 1)
            await ws.send(json.dumps({"type": "new_task", "agent": calm.slug, "text": "Check", "auto": True,
                                      "request": "m3"}))
            other = agents.agents[(await until(ws, lambda m: m["type"] == "created" and m.get("request") == "m3"))[-1]
                                  ["id"]]
            assert other.auto is False and other.saved == "calm"  # its setting, never the page's switch
            await ws.send(json.dumps({"type": "new_task", "agent": "gone", "text": "x", "request": "m4"}))
            refused = await until(ws, lambda m: m["type"] == "error" and m.get("request") == "m4")
            assert refused[-1]["text"] == "There is no such agent" and len(agents.agents) == 2
            await ws.send(json.dumps({"type": "saved_agent_delete", "slug": saved.slug, "request": "d1"}))
            await until(ws, lambda m: m["type"] == "saved_agents")
            assert run.saved == "" and run.state == "working"  # it goes on, as a one-off run
    finally:
        await server.stop()


async def test_a_run_keeps_the_template_skills_it_may_use(fake_claude, tmp_path):
    import json

    from ai_browser.app.agents import AgentManager
    from ai_browser.app.savedagents import SavedAgents
    from test_bridge import EVENTS

    runner, _, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    saved = SavedAgents(tmp_path / "home").save(AGENT)  # Can use: prices and tables
    manager = AgentManager(tmp_path / "home", claude=runner)
    try:
        run, started = await manager.run_as(saved, "Weekly prices", skills=["personal:tables", "personal:secrets"])
        assert started is True and run.pending[0][2] == ["personal:prices", "personal:tables"]  # not secrets
    finally:
        await manager.close_all()


# ---- its tasks: templates that run as it, on their schedules (Task 8) ------------------------------------------------

def test_a_template_runs_as_a_saved_agent_or_a_new_one(tmp_path):
    from ai_browser.brain.workflows import WorkflowStore

    store = WorkflowStore(tmp_path / "home")
    task = store.save({"name": "Weekly prices", "instructions": "List this week's prices", "trigger": "schedule",
                       "schedule": "mon 09:00", "runs_as": "research"})
    text = (tmp_path / "home" / "workflows" / "weekly-prices.md").read_text(encoding="utf-8")
    assert task.runs_as == "research" and "runs_as: research\n" in text
    assert store.get("weekly-prices").runs_as == "research"
    plain = store.save({"name": "Footer", "instructions": "Fix it"})
    assert plain.runs_as == "" and "runs_as" not in (tmp_path / "home" / "workflows" / "footer.md").read_text(
        encoding="utf-8")  # a new agent, as before: the file is as it was
    with pytest.raises(ValueError, match="Runs as is one of your agents, or a new agent"):
        store.save({"name": "Bad", "instructions": "x", "runs_as": "../agents/research"})


async def test_a_task_runs_as_its_agent_with_its_settings_and_waits_while_it_works(fake_claude, tmp_path):
    import datetime
    import json

    from ai_browser.app.agents import AgentManager
    from ai_browser.app.savedagents import SavedAgents
    from ai_browser.brain.workflows import WorkflowRunner, WorkflowStore
    from test_bridge import EVENTS

    runner_bin, _, script = fake_claude
    script.write_text(json.dumps([EVENTS[0], {"sleep": 30}]), encoding="utf-8")  # its run stays at work
    home = tmp_path / "home"
    saved = SavedAgents(home).save({**AGENT, "auto_approve": True, "load_at_start": [], "can_use": []})
    tasks = WorkflowStore(home)
    tasks.save({"name": "Morning prices", "instructions": "List today's prices", "trigger": "schedule",
                "schedule": "daily 09:00", "runs_as": saved.slug, "model": "haiku"})
    (home / "workflows" / "sneaky.md").write_text("---\nname: Sneaky\nauto_approve: true\ntrigger: manual\n---\n"
                                                  "Do it\n", encoding="utf-8")  # a file can't turn it on
    agents = AgentManager(home, claude=runner_bin)
    eight = datetime.datetime(2026, 10, 8, 8, 59).timestamp()
    now = [eight]
    runner = WorkflowRunner(tasks, agents, clock=lambda: now[0])
    runner.saved = SavedAgents(home)
    try:
        await runner.tick()  # the clock starts: nothing due yet
        now[0] = eight + 120  # 09:01
        await runner.tick()
        run = agents.run_of(saved.slug)
        assert run is not None and (run.saved, run.auto, run.model, run.name) == ("research", True, "opus", "Research")
        assert runner.notes["morning-prices"].startswith("Started")
        now[0] += 86400  # the next morning, while yesterday's run still works
        await runner.tick()
        assert list(agents.agents) == [run.id] and runner.notes["morning-prices"].endswith(
            ": the last run is still going")  # skipped, today's note
        sneaky = agents.agents[await runner.run("sneaky")]
        assert sneaky.auto is False and sneaky.saved == ""  # a new agent: never Auto-approve from a template
        with pytest.raises(ValueError, match="Research is working: run it again when it is done"):
            await runner.run("morning-prices", page="[A message: data, not the user's words]")  # an inbox item
        assert len(agents.agents) == 2
        await agents.close(run.id)
        SavedAgents(home).delete(saved.slug)
        now[0] += 86400
        await runner.tick()  # its agent is gone: a note, and the other schedules go on
        assert "was deleted" in runner.notes["morning-prices"]
    finally:
        await agents.close_all()


async def test_deleting_an_agent_deletes_its_tasks(fake_claude, tmp_path):
    import json

    from ai_browser.brain.workflows import WorkflowRunner, WorkflowStore
    from test_app_server import started, until
    from test_bridge import EVENTS
    from ui_socket import ui_socket

    workflows = WorkflowStore(tmp_path / "home")
    server, url = await started(fake_claude, tmp_path, EVENTS, workflows=workflows,
                                runner=WorkflowRunner(workflows, None))
    saved = server.saved.save(AGENT)
    workflows.save({"name": "Its task", "instructions": "x", "runs_as": saved.slug})
    workflows.save({"name": "Any agent's", "instructions": "y"})
    try:
        async with ui_socket(server, url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "mission"}))
            await until(ws, lambda m: m["type"] == "snapshot")
            await ws.send(json.dumps({"type": "workflow_save", "request": "w1", "name": "Mine", "instructions": "z",
                                      "runs_as": saved.slug, "auto_approve": True}))
            await until(ws, lambda m: m["type"] == "workflow_saved")
            snapshot = await until(ws, lambda m: m["type"] == "workflows_snapshot")
            assert {row["name"]: row["runs_as"] for row in snapshot[-1]["workflows"]} == {
                "Any agent's": "", "Its task": "research", "Mine": "research"}
            await ws.send(json.dumps({"type": "saved_agent_delete", "slug": saved.slug, "request": "d1"}))
            snapshot = await until(ws, lambda m: m["type"] == "workflows_snapshot")
            assert [row["name"] for row in snapshot[-1]["workflows"]] == ["Any agent's"]
    finally:
        await server.stop()


def test_a_narrowed_runs_bash_treats_skills_outside_can_use_like_blocked_ones(tmp_path, monkeypatch):
    import json

    from ai_browser import config, skills
    from ai_browser.app.bridge import ClaudeBridge
    from test_skills import make_skill

    claude = tmp_path / ".claude"
    prices, secrets, tidy = (make_skill(claude / "skills", name, scripts=True) for name in ("prices", "secrets", "tidy"))
    monkeypatch.setattr(skills, "user_folders", lambda: (claude, tmp_path / "app"))  # never the user's own
    config.set_blocked(tmp_path / "home", "personal:tidy", True)

    def hidden(env):
        return set(ClaudeBridge(tmp_path / "home", env=env).skill_folders().blocked)

    narrowed = hidden({"AIB_APP_SKILLS": json.dumps(["personal:prices"])})
    assert str(secrets) in narrowed and str(tidy) in narrowed and str(prices) not in narrowed
    assert hidden({}) == {str(tidy)}  # every skill: as before, only the blocked one
    assert hidden({"AIB_APP_SKILLS": "not json"}) == {str(prices), str(secrets), str(tidy)}  # broken: none of them


def test_a_narrowed_run_auto_approves_only_the_scripts_of_skills_it_may_use(tmp_path, monkeypatch):
    import json

    from ai_browser import skills
    from ai_browser.app import powers
    from ai_browser.app.bridge import ClaudeBridge
    from test_skills import make_skill

    claude, project = tmp_path / ".claude", tmp_path / "project"
    project.mkdir()
    found = {name: make_skill(claude / "skills", name, scripts=True) for name in ("prices", "secrets")}
    found["copy"] = make_skill(claude / "skills", "copy", name="secrets", scripts=True)  # shadowed: never catalogued
    found["loose"] = claude / "skills" / "loose" / "scripts"  # no SKILL.md: never catalogued
    found["loose"].mkdir(parents=True)
    (found["loose"] / "run.py").write_text("print('hi')", encoding="utf-8")
    monkeypatch.setattr(skills, "user_folders", lambda: (claude, tmp_path / "app"))  # never the user's own

    def auto(env, name):
        folders = ClaudeBridge(tmp_path / "home", env=env).skill_folders()
        script = found[name] / "run.py" if name == "loose" else found[name] / "scripts" / "run.py"
        command = {"command": f"python3 {script}"}
        return powers.auto_approves("Bash", command, powers.classify("Bash", command, project, skills=folders),
                                    sandbox=True, skills=folders)

    every, prices, none = {}, {"AIB_APP_SKILLS": json.dumps(["personal:prices"])}, {"AIB_APP_SKILLS": "not json"}
    assert all(auto(every, name) for name in found)  # every skill: as before, every folder under a root runs
    assert auto(prices, "prices") and not any(auto(prices, name) for name in ("secrets", "copy", "loose"))
    assert not any(auto(none, name) for name in found)  # broken: no skill folder is trusted
