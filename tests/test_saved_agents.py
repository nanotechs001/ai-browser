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
