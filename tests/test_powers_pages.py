"""Agent powers on AI Browser's own pages, in a throwaway headless Chrome against a real app server (agents on the
fake claude): the extended card, the action feed's badges, the plan and the sub-agents, the Folder picker and "Trust
this folder?", and Settings → Permissions. Every word from Claude or a path stays text."""

import asyncio
import json
import os

import pytest

from ai_browser.chrome import chrome_binary
from test_ai_home_phase2 import answered
from test_bridge_powers import INIT, PLAN, RESULT, ask, use
from test_home import home, open_page, stack, until  # noqa: F401  (fixtures)

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
HOSTILE = "echo '<img src=x onerror=\"document.title=1\">' > out.html"
ROW = "document.querySelector('#agents .agent[data-id=\"a1\"]')"
CARD = f"{ROW}?.querySelector('.permission')"


async def settled(check, seconds=8.0):
    for _ in range(int(seconds * 20)):
        if check():
            return True
        await asyncio.sleep(0.05)
    return bool(check())


@CHROME
async def test_a_command_card_shows_the_command_as_text_and_denies_with_a_note(home):  # Decision 2
    js, stack = home
    stack["script"].write_text(json.dumps([INIT, ask("Bash", {"command": HOSTILE}), {"sleep": 1}, RESULT]),
                               encoding="utf-8")
    await stack["server"].agents.create("make the page")
    assert await until(js, f"{CARD} != null")
    assert await js(f"{CARD}.querySelector('.permission-text').textContent") == HOSTILE
    assert await js(f"{CARD}.querySelectorAll('img').length") == 0 and await js("document.title") != "1"
    text = await js(f"{CARD}.textContent")
    assert "make the page wants to run a command" in text and "Asked every time: " in text  # AI Home: by name
    assert (await js(f"{CARD}.querySelector('.permission-where').textContent")).startswith("In ")
    assert await js(f"{CARD}.querySelector('.allow-always')") is None  # never for a redirect (Decision 4)
    await js(f"(() => {{ const card = {CARD}; card.querySelector('.deny-note').value = 'write it in the docs folder';"
             " card.querySelector('.deny').click(); return true; })()")
    assert await answered(stack["log"]) == [{"behavior": "deny",
                                             "message": "The user said no: write it in the docs folder"}]
    assert await until(js, f"{CARD} == null")


@CHROME
async def test_an_edit_card_shows_red_and_green_lines_and_always_for_this_agent(home):  # Decision 2
    js, stack = home
    work = stack["home"] / "app" / "agents" / "a1" / "work"
    edit = {"file_path": str(work / "app.py"), "old_string": "a\nb\nc", "new_string": "a\n<b>B</b>\nc"}
    stack["script"].write_text(json.dumps([INIT, ask("Edit", edit), {"sleep": 1}, RESULT]), encoding="utf-8")
    await stack["server"].agents.create("fix it")
    assert await until(js, f"{CARD} != null")
    lines = await js(f"[...{CARD}.querySelectorAll('.diff > div')].map((line) => [line.className, line.textContent])")
    assert lines == [["ctx", "  a"], ["del", "- b"], ["add", "+ <b>B</b>"], ["ctx", "  c"]]
    assert await js(f"{CARD}.querySelector('.chip.badge').textContent") == "Edit"
    assert await js(f"{CARD}.querySelector('.allow-always').textContent") == "Always allow for this agent"
    await js(f"{CARD}.querySelector('.allow-always').click(); true")
    assert [answer["behavior"] for answer in await answered(stack["log"])] == ["allow"]


@CHROME
async def test_a_huge_or_binary_file_shows_a_clipped_card_with_its_size(home):  # Review Focus 5
    js, stack = home
    work = stack["home"] / "app" / "agents" / "a1" / "work"
    big = "".join(f"row {n}\n" for n in range(50_000))
    png = "\x89PNG\x00\x00" + "x" * 3000
    stack["script"].write_text(json.dumps([INIT, ask("Write", {"file_path": str(work / "big.txt"), "content": big}),
                                           {"sleep": 0.5}, ask("Write", {"file_path": str(work / "logo.png"),
                                                                         "content": png}),
                                           {"sleep": 1}, RESULT]), encoding="utf-8")
    await stack["server"].agents.create("write them")
    assert await until(js, f"{CARD} != null")
    assert await js(f"{CARD}.querySelectorAll('.diff > div').length") == 300
    size = await js(f"{CARD}.querySelector('.permission-size').textContent")
    assert size.startswith("Showing the first 300 lines · ") and size.endswith(" KB")
    await js(f"{CARD}.querySelector('.allow-once').click(); true")
    assert await until(js, f"{CARD}?.textContent.includes('A binary file · ')")
    assert await js(f"{CARD}.querySelectorAll('.diff').length") == 0


@CHROME
async def test_mission_control_and_the_chat_show_the_same_card(stack):  # the spec's Interfaces: every page
    from test_chat_page import open_chat
    from test_mission import open_mission, station

    stack["script"].write_text(json.dumps([INIT, ask("Bash", {"command": "npm test"}), {"sleep": 5}, RESULT]),
                               encoding="utf-8")
    agents = stack["server"].agents
    agent = await agents.create("test it")
    assert await settled(lambda: agent.permission is not None)
    mission = await open_mission(stack)
    assert await until(mission, f"{station('a1', '.ticker')}?.textContent === 'wants to run a command'")
    await mission(f"{station('a1')}.click(); true")
    card = "document.querySelector('#drawer:not([hidden]) .permission')"
    assert await until(mission, f"{card} != null")
    assert await mission(f"{card}.querySelector('.permission-text').textContent") == "npm test"
    assert await mission(f"{card}.querySelector('.allow-always').textContent") == "Always allow for this agent"
    chat, _ = await open_chat(stack)
    needs = "document.querySelector('#needs-you .permission')"
    assert await until(chat, f"{needs} != null")
    assert "1 · test it wants to run a command" in await chat(f"{needs}.textContent")
    await chat(f"{needs}.querySelector('.allow-once').click(); true")
    assert [answer["behavior"] for answer in await answered(stack["log"])] == ["allow"]


def planned():
    """An agent that keeps a to-do list, opens a page, and starts a sub-agent that runs ls, then stays at work."""
    from ai_browser.app.powers import SUBAGENT_TOOL

    return [INIT, use("t1", "TodoWrite", PLAN), use("u0", "mcp__ai-browser__open", {"url": "https://shop.example/"}),
            use("u1", SUBAGENT_TOOL, {"description": "Research", "prompt": "Look it up"}),
            use("u2", "Bash", {"command": "ls"}, parent="u1"), {"sleep": 30}]


@CHROME
async def test_ai_homes_row_and_chat_show_the_folder_the_plan_the_sub_agents_and_badges(home):  # Decisions 6, 8-10
    js, stack = home
    stack["script"].write_text(json.dumps(planned()), encoding="utf-8")
    await stack["server"].agents.create("fix the footer")
    assert await until(js, f"{ROW}?.querySelector('.subagents')?.textContent === '1 sub-agent working'")
    assert await js(f"{ROW}.querySelector('.plan').textContent") == "1 / 3 steps · 33%"
    assert await js(f"{ROW}.querySelector('.folder').textContent") == "No folder"
    await js(f"{ROW}.querySelector('.chat').click(); true")
    rows = "[...document.querySelectorAll('#chat-messages .action')]"
    assert await until(js, f"{rows}.length === 3")  # TodoWrite is the plan, not a line
    assert await js(f"{rows}.map((row) => [row.querySelector('.badge').textContent, row.classList.contains('sub')])"
                    ) == [["Browser Agent", False], ["Sub-agent", False], ["Bash", True]]
    assert await js(f"{rows}.every((row) => /^\\d\\d:\\d\\d$/.test(row.querySelector('.at').textContent))")


@CHROME
async def test_mission_controls_drawer_lists_the_plan_and_the_sub_agents(stack):  # Decisions 8 and 9, Review Focus 3
    from test_mission import open_drawer, open_mission, station

    stack["script"].write_text(json.dumps(planned()), encoding="utf-8")
    agent = await stack["server"].agents.create("fix the footer")
    assert await settled(lambda: bool(agent.subagents) and bool(agent.subagents[0]["action"]))
    mission = await open_mission(stack)  # opened later: the plan comes with the agent
    assert await until(mission, f"{station('a1')} != null")
    await mission(open_drawer("a1"))
    plan = "[...document.querySelectorAll('#drawer-body .plan li')].map((item) => item.textContent)"
    assert await until(mission, f"{plan}.length === 3")
    assert await mission(plan) == ["✓ Read the code", "● Fixing the bug", "○ Run the tests"]
    assert await mission("document.querySelector('#drawer-body .plan-progress').textContent") == "1 / 3 steps · 33%"
    assert await mission("document.querySelector('#drawer-body .subagents li').textContent") == "● Research · Bash ls"
    assert await mission("document.querySelector('#drawer-body .folder').textContent") == \
        "No folder: its own scratch folder"
    await mission("document.querySelector('#drawer-body .stop').click(); true")  # Stop stops its sub-agents
    assert await until(mission, "document.querySelector('#drawer-body .subagents li')?.textContent.startsWith('■')")


CHOOSE_LAST = ("(() => { const pick = document.getElementById('task-folder');"
               "pick.value = pick.options[pick.options.length - 1].value;"  # Choose…
               "pick.dispatchEvent(new Event('change')); return true; })()")


@CHROME
async def test_ai_home_asks_trust_once_and_starts_the_task_in_the_folder(home, user_home, tmp_path):  # Decisions 6, 7
    js, stack = home
    project = tmp_path / "project"
    project.mkdir()
    box = "document.getElementById('folder-ask')"
    names = "[...document.getElementById('task-folder').options].map((option) => option.textContent).join('|')"
    assert await until(js, f"{names} === 'No folder|Choose…'")
    await js(CHOOSE_LAST)
    assert await until(js, f"{box}.querySelector('.folder-typed') != null")  # not AI Browser's own app: typed
    await js(f"{box}.querySelector('.folder-typed').value = {json.dumps(str(project))};"
             f"{box}.querySelector('.folder-use').click(); true")
    assert await until(js, f"{box}.querySelector('.trust') != null")
    assert "Trust project?" in await js(f"{box}.textContent")
    await js("document.getElementById('task').value = 'fix the footer';"
             "document.getElementById('start').click(); true")
    assert await until(js, "document.getElementById('hint').textContent.includes('Trust this folder')")
    assert stack["server"].agents.agents == {}  # Start waits for the answer
    await js(f"{box}.querySelector('.trust').click(); true")
    assert await until(js, f"{box}.textContent.startsWith('Trusted: ')")
    assert stack["server"].agents.rules.trusted(project) is True
    await js("document.getElementById('start').click(); true")
    agents = stack["server"].agents
    assert await settled(lambda: "a1" in agents.agents)
    assert agents.agents["a1"].folder == os.path.realpath(project)
    real = json.dumps(os.path.realpath(project))
    assert await until(js, f"document.getElementById('task-folder').value === {real}")  # kept for the next task


@CHROME
async def test_a_refused_folder_is_said_and_the_typed_path_stays(home, user_home):  # Decision 6
    js, stack = home
    box = "document.getElementById('folder-ask')"
    await js(CHOOSE_LAST)
    assert await until(js, f"{box}.querySelector('.folder-typed') != null")
    await js(f"{box}.querySelector('.folder-typed').value = {json.dumps(str(stack['home']))};"
             f"{box}.querySelector('.folder-use').click(); true")
    assert await until(js, f"{box}.textContent.includes(\"AI Browser's own folder\")")
    assert await js(f"{box}.querySelector('.folder-typed') != null")  # the user can type another
    assert await js("document.getElementById('task-folder').value") == ""  # still No folder


@CHROME
async def test_the_tab_menu_opens_the_folder_dialog_for_ai_home(stack, user_home, tmp_path):  # plan decision 13
    from test_tab_menu import frame, in_frame, window_page

    project = tmp_path / "project"
    project.mkdir()
    js = await window_page(stack)
    await js(f"window.aib = {{ chooseFolder: async () => {json.dumps(str(project))} }}; true")  # the app's bridge
    assert await until(js, f"{frame('/home')}.document.getElementById('task-folder')?.options.length === 2")
    await in_frame(js, "/home", CHOOSE_LAST)
    assert await until(js, f"{frame('/home')}.document.querySelector('#folder-ask .trust') != null")
    await in_frame(js, "/home", "document.querySelector('#folder-ask .trust').click(); true")
    assert await settled(lambda: stack["server"].agents.rules.trusted(project) is True)


@CHROME
async def test_the_chat_opens_the_folder_dialog_itself_and_starts_there(stack, user_home, tmp_path):  # Decision 6
    from test_chat_page import open_chat

    project = tmp_path / "project"
    project.mkdir()
    stack["server"].agents.rules.trust(project)  # answered before: no question this time
    chat, _ = await open_chat(stack)
    await chat(f"window.aib = Object.freeze({{ ...window.aib, chooseFolder: async () => {json.dumps(str(project))} }});"
               "document.getElementById('new-open').click(); true")
    await chat(CHOOSE_LAST)
    assert await until(chat, "document.getElementById('folder-ask').textContent.startsWith('Trusted: ')")
    await chat("document.getElementById('task').value = 'fix the footer';"
               "document.getElementById('task-start').click(); true")
    agents = stack["server"].agents
    assert await settled(lambda: "a1" in agents.agents and agents.agents["a1"].folder == os.path.realpath(project))


@CHROME
async def test_mission_control_starts_a_task_in_a_recent_folder(stack, user_home, tmp_path):  # Decision 6
    from test_mission import open_mission

    project = tmp_path / "project"
    project.mkdir()
    rules = stack["server"].agents.rules
    rules.trust(project)
    rules.note_used(project)
    mission = await open_mission(stack)
    pick = "document.getElementById('task-folder')"
    real = json.dumps(os.path.realpath(project))
    assert await until(mission, f"[...{pick}.options].some((option) => option.value === {real})")
    assert await mission(f"[...{pick}.options].find((option) => option.value === {real}).textContent") == "project"
    await mission(f"{pick}.value = {real}; {pick}.dispatchEvent(new Event('change')); true")
    assert await until(mission, "document.getElementById('folder-ask').textContent.startsWith('Trusted: ')")
    await mission("document.getElementById('task').value = 'fix the footer';"
                  "document.getElementById('start').click(); true")
    agents = stack["server"].agents
    assert await settled(lambda: "a1" in agents.agents and agents.agents["a1"].folder == os.path.realpath(project))


def folder_box(path):
    """Settings → Permissions' card for one folder, found by its real path (as text, never a selector)."""
    return (f"[...document.querySelectorAll('#permissions .perm-folder')]"
            f".find((node) => node.dataset.path === {json.dumps(os.path.realpath(path))})")


@CHROME
async def test_settings_lists_folders_and_removes_rules_and_trust(stack, user_home, tmp_path):  # Review Focus 4
    from test_accounts_pages import open_settings

    project, gone = tmp_path / "project", tmp_path / "old-project"
    project.mkdir()
    gone.mkdir()
    rules = stack["server"].agents.rules
    for rule in ("Bash(npm test:*)", "Edit"):
        rules.add(project, rule)
    rules.trust(project)
    rules.note_used(project)
    rules.add(gone, "WebSearch")
    gone.rmdir()  # unplugged since: its rules stay until removed
    settings = await open_settings(stack)
    mine, old = folder_box(project), folder_box(gone)
    assert await until(settings, f"{mine} != null && {old} != null")
    assert await settings(f"{mine}.querySelector('.trust').textContent") == "Trusted"
    assert await settings(f"[...{mine}.querySelectorAll('.rule-label')].map((node) => node.textContent)") == [
        "Run commands that start with: npm test", "Edit and write files in this folder"]
    assert "isn't there any more" in await settings(f"{old}.querySelector('.missing').textContent")
    await settings(f"{mine}.querySelector('.rule[data-rule=\"Edit\"] .remove').click(); true")
    assert await until(settings, f"{mine}.querySelectorAll('.rule-label').length === 1")
    assert rules.allowed(project) == ["Bash(npm test:*)"]
    await settings(f"{mine}.querySelector('.untrust').click(); true")
    assert await until(settings, f"{mine}.querySelector('.trust').textContent === 'Not trusted'")
    assert rules.trusted(project) is False
    await settings(f"{old}.querySelector('.forget').click(); true")
    assert await until(settings, f"{old} == null")
    assert [row["path"] for row in rules.folders()] == [os.path.realpath(project)]


def test_the_readme_explains_agent_powers():  # what the user reads first
    from pathlib import Path

    readme = " ".join((Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8").split())
    for phrase in ("### Agent powers: commands, file edits, the web, sub-agents and to-do lists",
                   "**Always allow for this folder**", "**Trust this folder?**", "**Settings → Permissions**",
                   "`~/.ai-browser/permissions.json`", "**No folder**", "Asked every time, never \"Always\"",
                   "**Stop** stops its sub-agents too", "Agents' own commands, edits and reads ask first"):
        assert phrase in readme, phrase
    assert "Its only tools are ai-browser's" not in readme


@CHROME
async def test_a_folder_chosen_in_the_dialog_shows_in_the_picker(stack, user_home, tmp_path):  # final review
    from test_chat_page import open_chat

    project = tmp_path / "project"
    project.mkdir()
    stack["server"].agents.rules.trust(project)  # answered before: no question, so nothing else takes the focus
    chat, _ = await open_chat(stack)
    await chat(f"window.aib = Object.freeze({{ ...window.aib, chooseFolder: async () => {json.dumps(str(project))} }});"
               "document.getElementById('new-open').click(); document.getElementById('task-folder').focus(); true")
    await chat(CHOOSE_LAST)  # the picker keeps the focus while the app's dialog is open
    assert await until(chat, "document.getElementById('folder-ask').textContent.startsWith('Trusted: ')")
    real = json.dumps(os.path.realpath(project))
    assert await until(chat, f"document.getElementById('task-folder').value === {real}")  # what Start will use


def test_the_readme_says_always_trusts_the_whole_program():  # fresh review: per-program rules
    from pathlib import Path

    readme = " ".join((Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8").split())
    for phrase in ("can't see inside that program's own options", "`curl -T`", "`sed 'w …'`",
                   "Allow only programs you trust with any input", "`find -delete`", "`git reset --hard`",
                   "`git push --force`", "`git branch -D`"):
        assert phrase in readme, phrase


# Auto-approve in its folder (the user's choice, 2026-10-07): a switch per task, the user's click only.
AUTO_SWITCH = "document.getElementById('task-auto')"


@CHROME
async def test_build_a_missions_switch_starts_an_agent_that_auto_approves(stack):  # the user's choice
    from test_mission import open_mission

    mission = await open_mission(stack)
    label = "document.getElementById('task-auto-switch')"
    assert await mission(f"{AUTO_SWITCH}.checked") is False  # off by default
    assert await mission(f"{label}.textContent.trim()") == "Auto-approve in its folder"
    assert await mission(f"{label}.closest('.pickers') === document.getElementById('task-folder').closest('.pickers')"
                         f" && {label}.hidden === false")  # beside Folder, in Build a Mission
    for mode, hidden in (("ask", True), ("template", True), ("build", False)):
        await mission(f"document.getElementById('mode-{mode}').click(); true")
        assert await mission(f"{label}.hidden") is hidden, mode
    await mission(f"{AUTO_SWITCH}.click(); document.getElementById('task').value = 'fix the footer';"
                  "document.getElementById('start').click(); true")
    agents = stack["server"].agents
    assert await settled(lambda: "a1" in agents.agents)
    assert agents.agents["a1"].auto is True and agents.agents["a1"].bridge.auto is True
    assert await until(mission, f"{AUTO_SWITCH}.checked === false")  # each task is its own choice: off again
    await mission("document.getElementById('task').value = 'look around';"
                  "document.getElementById('start').click(); true")
    assert await settled(lambda: "a2" in agents.agents)
    assert agents.agents["a2"].auto is False


@CHROME
async def test_the_drawers_switch_turns_auto_approve_on_and_off_and_says_where(stack, user_home, tmp_path):
    from test_mission import WORKING, open_drawer, open_mission, station

    project = tmp_path / "project"
    project.mkdir()
    agents = stack["server"].agents
    agents.rules.trust(project)
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    agent = await agents.create("keep working")
    mission = await open_mission(stack)
    assert await until(mission, f"{station('a1')} != null")
    await mission(open_drawer("a1"))
    toggle = "document.querySelector('#drawer-body .auto-toggle input')"
    words = "document.querySelector('#drawer-body .auto-words')"
    assert await until(mission, f"{toggle} != null")
    assert await mission(f"{toggle}.checked") is False and await mission(f"{words}.hidden") is True
    assert await mission("document.querySelector('#drawer-body .auto-toggle').textContent.trim()") == (
        "Auto-approve in its folder")
    await mission(f"{toggle}.click(); true")  # while it works
    assert await settled(lambda: agent.auto and agent.bridge.auto)
    assert await until(mission, f"{words}.hidden === false")
    assert await mission(f"{words}.textContent") == "Auto-approving inside its own scratch folder"
    await mission(f"{toggle}.click(); true")
    assert await settled(lambda: not agent.auto and not agent.bridge.auto)
    assert await until(mission, f"{words}.hidden === true && {toggle}.checked === false")
    inside = await agents.create("fix it", folder=str(project), auto=True)
    assert await until(mission, f"{station(inside.id)} != null")
    await mission(open_drawer(inside.id))
    assert await until(mission, f"document.getElementById('drawer-title').textContent.startsWith('2 ·')"
                                f" && {toggle}?.checked === true")
    assert await mission(f"{words}.textContent") == f"Auto-approving inside {os.path.realpath(project)}"


@CHROME
async def test_an_auto_approved_action_line_carries_its_mark(stack, monkeypatch):  # what ran without a card
    from ai_browser.app import powers
    from test_bridge_powers import result
    from test_mission import open_drawer, open_mission, station

    monkeypatch.setattr(powers, "sandbox_on", lambda: True)  # where the sandbox holds commands
    stack["script"].write_text(json.dumps([INIT, use("u1", "Bash", {"command": "npm test"}),
                                           ask("Bash", {"command": "npm test"}, tool_id="u1"),
                                           result("u1", "3 passed"),
                                           use("u2", "mcp__ai-browser__open", {"url": "https://shop.example/"}),
                                           {"sleep": 30}]), encoding="utf-8")
    agent = await stack["server"].agents.create("test it", auto=True)
    assert await settled(lambda: {"type": "auto", "id": "u1"} in stack["server"].agents.events_of(agent.id))
    mission = await open_mission(stack)
    assert await until(mission, f"{station('a1')} != null")
    await mission(open_drawer("a1"))
    rows = "[...document.querySelectorAll('#drawer-body .messages .action')]"
    assert await until(mission, f"{rows}.length === 2")
    assert await mission(f"{rows}.map((row) => row.querySelector('.auto')?.textContent ?? null)") == ["auto", None]
    assert await mission(f"{rows}[0].querySelector('.auto').title") == "Ran without a card: Auto-approve in its folder"


EDITS_ONLY = "On this computer, commands still ask: only file edits run without a card"


@CHROME
@pytest.mark.parametrize("sandbox", [True, False])
async def test_the_switch_says_what_runs_without_a_card_on_this_computer(stack, monkeypatch, sandbox):  # I3
    from ai_browser.app import powers
    from test_mission import WORKING, open_drawer, open_mission, station

    monkeypatch.setattr(powers, "sandbox_on", lambda: sandbox)
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await stack["server"].agents.create("keep working", auto=True)
    mission = await open_mission(stack)
    title = "document.getElementById('task-auto-switch').title"
    assert await until(mission, f"{title}.length > 0")
    words = await mission(title)
    assert "judged from what a command names, not from what a script it runs does" in words
    assert words.startswith(EDITS_ONLY) is (not sandbox) and ("ordinary commands" in words) is sandbox
    assert await until(mission, f"{station('a1')} != null")
    await mission(open_drawer("a1"))
    note = "document.querySelector('#drawer-body .auto-note')"
    assert await until(mission, f"{note} != null && "
                                "document.querySelector('#drawer-body .auto-words').hidden === false")
    assert await mission(f"{note}.hidden") is sandbox and await mission(f"{note}.textContent") == EDITS_ONLY
    assert await mission("document.querySelector('#drawer-body .auto-toggle').title") == words


def test_the_readme_explains_auto_approve():  # the user's choice, 2026-10-07: what it covers and what still asks
    from pathlib import Path

    readme = " ".join((Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8").split())
    for phrase in ("- **Auto-approve in its folder:** a switch per task, off by default",
                   "edits and new files inside the task's folder run without a card",
                   "a small **auto** mark beside its badge", '"Auto-approving inside <folder>"',
                   "on a Mac, where the sandbox holds commands in the folder, ordinary commands run without a card too",
                   "Any other command asks",
                   "on Windows and Linux, commands still ask: only file edits run without a card",
                   "Web Search and Web Fetch, a command reaching a site, your own tools",
                   "a `cd` that isn't into a folder inside", "Once the shell has left the folder, commands ask again",
                   "judged from what a command names, not from what a script it runs does",
                   "Turn it on only for folders and tasks you trust",
                   "The Brain, templates and Claude Code sessions never turn it on",
                   "**Model**, **Account**, **Folder**, **Auto-approve in its folder** and **Workspace**",
                   "unless **Auto-approve in its folder** runs an ordinary one", "only your click turns it on",
                   "`caffeinate`, `strace`, `flock`", "`deno eval`", "`git rm -f` or `-r`", "`rsync --delete`",
                   "`.husky`, `.vscode` or `.idea` settings, its Git hooks folder"):
        assert phrase in readme, phrase
    for gone in ("a command whose job is reaching a site asks", "or one **Auto-approve in its folder** runs"):
        assert gone not in readme, gone
