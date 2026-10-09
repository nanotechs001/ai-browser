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
