"""Agent powers' rules and folders (app/powers.py): the user's answers per folder (its real path) in
<home>/permissions.json, mode 0600; the folders no task may work in; and what Claude Code is told to load and ask.
Throwaway folders and homes only."""

import json
import os
import sys

import pytest

from conftest import file_mode, symlink_or_skip


def test_rules_and_trust_are_kept_per_folder_in_a_private_file(tmp_path):  # Decisions 5 and 7
    from ai_browser.app.powers import Rules

    project = tmp_path / "project"
    project.mkdir()
    rules = Rules(tmp_path / "home")
    assert rules.allowed(project) == [] and rules.trusted(project) is None  # never asked
    rules.add(project, "Bash(npm test:*)")
    rules.add(project, "Edit")
    rules.add(project, "Edit")  # once
    rules.trust(project)
    again = Rules(tmp_path / "home")
    assert again.allowed(project) == ["Bash(npm test:*)", "Edit"] and again.trusted(project) is True
    assert again.allowed(f"{project}/src/..") == ["Bash(npm test:*)", "Edit"]  # the real path is the key
    assert file_mode(tmp_path / "home" / "permissions.json") in (0o600, None)
    again.remove(project, "Edit")
    again.untrust(project)
    assert again.allowed(project) == ["Bash(npm test:*)"] and again.trusted(project) is False
    for bad in ("Bash(*)", "Bash(:*)", "Bash( :*)", "Read", "WebFetch(domain:*)", "Edit(/x/**)", 7):
        with pytest.raises(ValueError):
            again.add(project, bad)  # no wildcard rule that allows every command (Safety)


def test_a_damaged_file_reads_as_nothing_and_a_write_keeps_what_it_doesnt_know(tmp_path):
    from ai_browser.app.powers import Rules

    project = tmp_path / "project"
    project.mkdir()
    (tmp_path / "home").mkdir()
    path = tmp_path / "home" / "permissions.json"
    path.write_text("{not json", encoding="utf-8")
    rules = Rules(tmp_path / "home")
    assert rules.allowed(project) == [] and rules.folders() == []
    key = os.path.realpath(project)
    path.write_text(json.dumps({"future": 1, "folders": {key: {"rules": ["Edit", 7, "Bash(*)"], "trusted": "yes",
                                                               "later": True}}}), encoding="utf-8")
    assert rules.allowed(project) == ["Edit"] and rules.trusted(project) is None
    rules.add(project, "WebSearch")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["future"] == 1 and data["folders"][key]["later"] is True


def test_a_folder_deleted_or_renamed_keeps_its_rules_until_removed(tmp_path):  # Review Focus 4
    from ai_browser.app.powers import Rules

    project = tmp_path / "project"
    project.mkdir()
    rules = Rules(tmp_path / "home")
    rules.add(project, "Bash(npm test:*)")
    rules.trust(project)
    rules.note_used(project)
    key = os.path.realpath(project)
    project.rename(tmp_path / "renamed")
    rows = rules.folders()
    assert rows[0]["path"] == key and rows[0]["missing"] is True and rows[0]["trusted"] is True
    assert rows[0]["name"] == "project"
    assert rows[0]["rules"] == [{"rule": "Bash(npm test:*)", "label": "Run commands that start with: npm test"}]
    assert rules.allowed(project) == ["Bash(npm test:*)"]  # kept, for when it comes back
    rules.forget(project)
    assert rules.folders() == []


def test_only_site_rules_are_handed_to_claude_code_and_each_rule_has_words(tmp_path):  # plan decision 1
    from ai_browser.app.powers import Rules, rule_label

    project = tmp_path / "project"
    project.mkdir()
    rules = Rules(tmp_path / "home")
    for rule in ("Bash(npm test:*)", "Edit", "WebSearch", "WebFetch(domain:docs.python.org)"):
        rules.add(project, rule)
    assert rules.claude_rules(project) == ["WebFetch(domain:docs.python.org)"]
    assert [rule_label(rule) for rule in rules.allowed(project)] == [
        "Run commands that start with: npm test", "Edit and write files in this folder", "Search the web",
        "Fetch pages from docs.python.org"]


def test_refused_folders(tmp_path, user_home):  # Decision 6, Review Focus 2
    from ai_browser.app import powers

    home = tmp_path / "aib-home"
    (home / "app").mkdir(parents=True)
    claude = tmp_path / "claude-work"
    claude.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    (user_home / "Library" / "Caches").mkdir(parents=True)
    (user_home / ".claude").mkdir()
    (user_home / "code" / "app").mkdir(parents=True)

    def check(path):
        return powers.check_folder(str(path), home=home, claude_dirs=[str(claude)])

    assert check(project) is None and check(user_home / "code" / "app") is None
    assert check(os.sep) == powers.WHOLE_DISK and check(user_home) == powers.WHOLE_HOME
    assert "Library" in check(user_home / "Library") and "Library" in check(user_home / "Library" / "Caches")
    assert "Claude Code's own folder" in check(user_home / ".claude") and "Claude Code's own folder" in check(claude)
    assert "AI Browser's own folder" in check(home) and "AI Browser's own folder" in check(home / "app")
    assert check(tmp_path).startswith("That folder holds")  # it holds the ones above
    assert check(tmp_path / "missing") == powers.GONE
    (project / "a.txt").write_text("x", encoding="utf-8")
    assert check(project / "a.txt") == powers.NOT_A_FOLDER
    for given in ("relative/path", "", "   ", "/x\x00", "/" + "x" * 5000, 7):
        assert powers.check_folder(given, home=home) == powers.NOT_A_PATH, given
    symlink_or_skip(user_home / ".claude", tmp_path / "sneaky")
    assert "Claude Code's own folder" in check(tmp_path / "sneaky")  # after realpath
    if os.name != "nt":
        assert check("/usr") == check("/tmp") == powers.IT_IS.format(what="a system folder")


def test_trust_decides_the_sources_and_the_settings_ask_for_everything(monkeypatch):  # Decision 7, R1 to R3
    from ai_browser.app import powers

    assert powers.setting_sources(True) == "local,project"
    assert powers.setting_sources(False) == powers.UNTRUSTED_SOURCES and "local" not in powers.UNTRUSTED_SOURCES
    monkeypatch.setattr(powers, "ASK_ALL", True)
    assert powers.claude_settings(False) == {"permissions": {"ask": list(powers.ASKED)}}
    assert powers.claude_settings(True)["sandbox"] == {"enabled": True, "autoAllowBashIfSandboxed": False,
                                                       "allowUnsandboxedCommands": True}
    monkeypatch.setattr(powers, "ASK_ALL", False)
    assert powers.claude_settings(False) == {}
    monkeypatch.setattr(powers, "SANDBOX", True)
    assert powers.sandbox_on() is (sys.platform == "darwin")  # macOS only: Task 1 probed nothing else
    monkeypatch.setattr(powers, "SANDBOX", False)
    assert powers.sandbox_on() is False


def case_blind(folder) -> bool:
    """Whether this disk treats names alike whatever their case (macOS's and Windows' default)."""
    return (folder.parent / folder.name.swapcase()).exists()


def test_a_case_variant_of_a_refused_folder_is_refused(tmp_path, user_home):  # fresh review F1, Decision 6
    from ai_browser.app import powers

    home = tmp_path / "aib-home"
    home.mkdir()
    (user_home / ".claude").mkdir()
    (user_home / "Library").mkdir()
    if not case_blind(user_home / ".claude"):
        pytest.skip("this disk tells names apart by case: no case variant names the same folder")

    def check(path):
        return powers.check_folder(str(path), home=home)

    assert "Claude Code's own folder" in check(user_home / ".CLAUDE")  # the same folder as ~/.claude
    assert "Library" in check(user_home / "LIBRARY")
    assert "AI Browser's own folder" in check(tmp_path / "AIB-HOME")
    assert check(tmp_path.parent / tmp_path.name.swapcase()).startswith("That folder holds")
    assert check(user_home.parent / "USER-HOME") == powers.WHOLE_HOME
    assert check(home.parent / "Project") is None or not (home.parent / "Project").exists()


def test_the_probes_answers_are_what_claude_code_does():  # Task 1's probe, run 2026-10-07 on Claude Code 2.1.263
    from ai_browser.app import powers

    assert powers.SUBAGENT_TOOL == "Task"  # R4: `--tools Agent` lists nothing; `--tools Task` lists Task
    assert "Task" in powers.TOOLS and "Agent" not in powers.TOOLS and "Task" in powers.FREE
    assert powers.SUBAGENTS >= {"Agent", "Task"}  # its uses still stream as "Agent": both names are read
    assert powers.SANDBOX is True and powers.SANDBOX_NETWORK is True  # R1: held; curl got no network
    assert powers.UNTRUSTED_SOURCES == ""  # R2: no hook ran and no CLAUDE.md loaded
    assert powers.ASK_ALL is True  # R3: without the ask rule, in-folder reads, `ls` and `echo && echo` went unasked
