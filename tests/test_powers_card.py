"""Agent powers' card (app/powers.py): what a request will do, as plain text the page sets with textContent: the
command and its folder, a clipped diff, the path, the site or the query. And each action's badge and one-line
summary, the to-do list and a sub-agent's task. Throwaway folders only."""

import json
import time

from test_powers_classify import project  # noqa: F401  (a fixture)


def test_a_command_card_holds_the_command_and_its_folder_as_text(project):  # Decision 2
    from ai_browser.app.powers import card

    hostile = "echo '<img src=x onerror=alert(1)>' > out.html"
    shown = card("Bash", {"command": hostile}, project)
    assert shown["text"] == hostile and shown["folder"] == str(project) and shown["badge"] == "Bash"
    assert shown["title"] == "run a command" and shown["always"] is False and "redirect" in shown["why"]
    assert card("Bash", {"command": "npm test"}, project)["always"] is True


def test_an_edit_card_is_a_diff_of_plain_text_lines(project):  # Testing: the card's diff, as text
    from ai_browser.app.powers import card

    old = "def footer():\n    return 'old'\n"
    new = "def footer():\n    return '<b>new</b>'\n"
    shown = card("Edit", {"file_path": str(project / "src" / "app.py"), "old_string": old, "new_string": new},
                 project)
    assert shown["lines"] == [[" ", "def footer():"], ["-", "    return 'old'"], ["+", "    return '<b>new</b>'"]]
    assert shown["size"] == len(old.encode()) + len(new.encode()) and shown["hidden"] == 0 and not shown["binary"]
    assert shown["badge"] == "Edit" and shown["title"] == "edit a file" and shown["always"] is True
    written = card("Write", {"file_path": str(project / "notes.md"), "content": "one\ntwo"}, project)
    assert written["lines"] == [["+", "one"], ["+", "two"]] and written["title"] == "write a file"
    three = card("Edit", {"file_path": str(project / "a.txt"), "old_string": "a\nb\nc", "new_string": "a\n<b>B</b>\nc"},
                 project)
    assert three["lines"] == [[" ", "a"], ["-", "b"], ["+", "<b>B</b>"], [" ", "c"]]


def test_a_huge_or_binary_edit_is_clipped_with_its_size(project):  # Review Focus 5
    from ai_browser.app.powers import LINE_LIMIT, LINES_SHOWN, card

    old = "".join(f"line {n}\n" for n in range(60_000))
    new = old.replace("line 5\n", "line five\n")
    started = time.monotonic()
    shown = card("Edit", {"file_path": str(project / "big.txt"), "old_string": old, "new_string": new}, project)
    assert time.monotonic() - started < 5  # two sides too long to compare are listed, never diffed
    assert len(shown["lines"]) == LINES_SHOWN and shown["hidden"] > 0
    assert shown["size"] == len(old.encode()) + len(new.encode()) and len(json.dumps(shown)) < 120_000
    medium = card("Edit", {"file_path": str(project / "m.txt"),
                           "old_string": "".join(f"row {n}\n" for n in range(1500)),
                           "new_string": "".join(f"row {n}!\n" for n in range(1500))}, project)
    assert len(medium["lines"]) == LINES_SHOWN and medium["hidden"] == 3000 - LINES_SHOWN
    long_line = card("Write", {"file_path": str(project / "long.txt"), "content": "y" * 5000}, project)
    assert len(long_line["lines"][0][1]) == LINE_LIMIT and long_line["lines"][0][1].endswith("…")
    binary = card("Write", {"file_path": str(project / "logo.png"), "content": "\x89PNG\x00\x00" + "x" * 3000},
                  project)
    assert binary["binary"] is True and binary["lines"] == [] and binary["size"] > 3000


def test_a_card_never_carries_a_control_character_or_a_direction_mark(project):  # what a line says can't hide
    from ai_browser.app.powers import card

    shown = card("Bash", {"command": "ls src ‮; rm -rf ~ ‬\rnpm test"}, project)
    assert "‮" not in shown["text"] and "\r" not in shown["text"]
    assert "␍" in shown["text"] and "�" in shown["text"]  # a carriage return shows as ␍
    lines = card("Write", {"file_path": str(project / "a.txt"), "content": "ok⁦hidden⁩\x1b[31m"},
                 project)["lines"]
    assert lines == [["+", "ok�hidden��[31m"]]


def test_reads_fetches_and_searches_say_what_and_where(project, tmp_path):  # Decision 2
    from ai_browser.app.powers import card

    secret = str(tmp_path / "outside" / "secret.txt")
    read = card("Read", {"file_path": secret}, project)
    assert read["text"] == secret and read["badge"] == "Read" and read["why"] and read["always"] is False
    listed = card("Glob", {"pattern": "*.txt", "path": str(tmp_path / "outside")}, project)
    assert listed["text"] == f"*.txt in {tmp_path / 'outside'}" and listed["title"] == "list files outside its folder"
    fetch = card("WebFetch", {"url": "https://docs.python.org/3/", "prompt": "x"}, project)
    assert (fetch["site"], fetch["badge"], fetch["title"]) == ("docs.python.org", "Web Fetch", "fetch a page")
    search = card("WebSearch", {"query": "shlex"}, project)
    assert (search["text"], search["badge"], search["always"]) == ("shlex", "Web Search", True)


def test_a_command_says_when_it_runs_in_the_sandbox_and_leaving_it_asks_every_time(project, monkeypatch):  # R1
    from ai_browser.app import powers

    assert powers.card("Bash", {"command": "npm test"}, project)["sandbox"] == ""  # cards only
    assert powers.card("Bash", {"command": "npm test"}, project, sandbox=True)["sandbox"] == powers.SANDBOXED
    monkeypatch.setattr(powers, "SANDBOX_NETWORK", True)
    assert "reach the network" in powers.card("Bash", {"command": "npm test"}, project, sandbox=True)["sandbox"]
    leaving = powers.card("Bash", {"command": "npm test", "dangerouslyDisableSandbox": True}, project, sandbox=True)
    assert leaving["title"] == "run a command outside the sandbox" and leaving["always"] is False
    assert leaving["sandbox"] == "" and leaving["why"] == powers.WHY_SANDBOX


def test_every_action_has_a_badge_and_a_one_line_summary():  # Decision 10
    from ai_browser.app.powers import badge, summary

    names = ("Bash", "Edit", "Write", "Read", "Glob", "Grep", "WebSearch", "WebFetch", "Agent", "Task",
             "mcp__ai-browser__open", "mcp__ai-browser__act", "mcp__ai-browser__load_skill", "mcp__ai-browser__shell",
             "mcp__clickup__create_task")
    assert [badge(name) for name in names] == [
        "Bash", "Edit", "Write", "Read", "Read", "Read", "Web Search", "Web Fetch", "Sub-agent", "Sub-agent",
        "Browser Agent", "Browser Agent", "Skill", "Skill", "Tool"]
    assert summary("Bash", {"command": "npm test\n  --watch"}) == "npm test --watch"
    assert summary("Agent", {"description": "Research the footer", "prompt": "..."}) == "Research the footer"
    assert len(summary("WebSearch", {"query": "q" * 500})) == 120


def test_the_to_do_list_and_a_sub_agents_task_are_plain_and_bounded():  # Decisions 8 and 9
    from ai_browser.app.powers import subagent_task, todos

    items = todos({"todos": [{"content": "Read\nthe code", "status": "completed", "activeForm": "Reading"},
                             {"content": "Fix", "status": "in_progress", "activeForm": "Fixing"},
                             {"content": "Ship", "status": "weird"}, {"status": "pending"}, "junk"]})
    assert items == [{"content": "Read the code", "status": "completed", "active": "Reading"},
                     {"content": "Fix", "status": "in_progress", "active": "Fixing"},
                     {"content": "Ship", "status": "pending", "active": "Ship"}]
    assert len(todos({"todos": [{"content": str(n), "status": "pending"} for n in range(80)]})) == 50
    assert todos(None) == [] and todos({"todos": "x"}) == []
    assert subagent_task({"description": "Research‮", "prompt": "x"}) == "Research�"
    assert subagent_task({"prompt": "Find the footer's bug and tell me"}) == "Find the footer's bug and tell me"
    assert subagent_task({}) == "a sub-agent"
