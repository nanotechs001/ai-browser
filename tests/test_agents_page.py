"""Mission Control's Agents page and the saved agents on the pages (the saved-agents spec, 1, 2 and 5): the cards, the
settings panel and its Save, Skills (Can use, Load at start), Tasks (Runs as), Agent ▾ in Build a Mission, the
dialogs that confirm Delete agent and Close, and Save as agent. Against a real app server (agents on the fake claude)
in a throwaway headless Chrome; every word stays text."""

import json

import pytest

from ai_browser.chrome import chrome_binary
from test_app_server import wait_for
from test_home import HOSTILE, stack, until  # noqa: F401  (fixtures)
from test_mission import open_mission

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
PANEL = "document.getElementById('agent-panel')"
TICK = ("(ref, box) => document.getElementById('agent-panel').querySelector("
        "`.agent-skill[data-ref='${ref}'] .${box}`).click()")  # a skill's Can use or Load at start
AGENT = {"name": "Research", "description": "Pricing pages of the three biggest rivals",
         "instruction": "Answer in French.", "web": "brave", "model": "opus"}


def card(slug):
    return f"document.querySelector('#page-agents .agent-card[data-slug={json.dumps(slug)}]')"


def in_panel(name):
    return f"{PANEL}.querySelector('[name={json.dumps(name)}]')"


def user_skills(stack, monkeypatch, *names):
    """Skills of the user's in the stack's throwaway folder: the catalog reads them there, never ~/.claude."""
    from ai_browser import skills
    from test_skills import make_skill

    for name in names:
        make_skill(stack["user"] / ".claude" / "skills", name, desc=f"About {name}")
    monkeypatch.setattr(skills, "user_folders", lambda: (stack["user"] / ".claude", stack["user"] / "Claude"))
    stack["server"].skills_changed()


async def open_agents(stack):
    js = await open_mission(stack)
    await js("document.querySelector('.page-link[data-page=\"agents\"]').click(); true")
    assert await until(js, "!document.getElementById('page-agents').hidden")
    return js


# ---- the Agents page: cards, settings, Save, Skills, Tasks (Task 15) -------------------------------------------------

@CHROME
async def test_the_agents_page_lists_saved_agents_as_cards(stack):
    server, brave = stack["server"], stack["brave"]
    brave.place.listed = [{"folder": "Profile 1", "name": "Work", "color": None},
                          {"folder": "Profile 2", "name": "Home", "color": None}]
    brave.place.learned = {"Profile 1"}
    saved = server.saved.save({**AGENT, "name": HOSTILE, "profile": "Profile 1"})
    stack["workflows"].save({"name": "Morning prices", "instructions": "List them", "trigger": "schedule",
                             "schedule": "daily 09:00", "runs_as": saved.slug})
    js = await open_agents(stack)
    assert await until(js, f"{card(saved.slug)} !== null")
    words = await js(f"[...{card(saved.slug)}.children].map(node => node.textContent)")
    assert words[0] == HOSTILE and words[1:3] == [AGENT["description"], "Brave: Work"]  # text stays text
    assert words[3].startswith("Next: Morning prices · ")  # its next scheduled task
    assert await js(f"{card(saved.slug)}.querySelectorAll('img').length") == 0
    assert await js("document.querySelector('#page-agents .any-tasks .workflow') === null")  # its own task only
    stack["script"].write_text(json.dumps([{"sleep": 30}]), encoding="utf-8")  # a run of it, at work
    await server.agents.run_as(saved, "List the prices")
    assert await until(js, f"{card(saved.slug)}.querySelector('.chip.working')?.textContent === 'Working'")
    await js(f"{card(saved.slug)}.click(); true")  # its settings
    assert await until(js, f"!{PANEL}.hidden && {in_panel('agent-name')}.value === {json.dumps(HOSTILE)}")
    profiles = await js(f"[...{in_panel('agent-profile')}.options].map(option => option.textContent)")
    assert profiles == ["Settings' choice", "Work · ready", "Home · open it once"]
    assert await js(f"{in_panel('agent-profile')}.value") == "Profile 1"
    assert await js(f"{PANEL}.querySelector('.agent-tasks .workflow[data-slug=\"morning-prices\"]') !== null")


@CHROME
async def test_new_agent_is_saved_with_every_setting_and_refused_words_show(stack, monkeypatch):
    server = stack["server"]
    user_skills(stack, monkeypatch, "prices", "tables", "secrets")
    js = await open_agents(stack)
    await js("document.querySelector('#page-agents .new-agent').click(); true")
    assert await until(js, f"!{PANEL}.hidden && document.activeElement === {in_panel('agent-name')}")
    assert await until(js, f"{PANEL}.querySelector('.agent-skill[data-ref=\"personal:prices\"]') !== null")
    await js(f"const tick = {TICK};"
             f"{in_panel('agent-name')}.value = 'Research';"
             f"{in_panel('agent-about')}.value = 'Rivals\\' prices';"
             f"{in_panel('agent-instruction')}.value = 'Answer in French.\\nKeep a table.';"
             f"{in_panel('agent-web')}.value = 'brave'; {in_panel('agent-model')}.value = 'haiku';"
             f"{in_panel('agent-auto')}.checked = true;"
             "tick('personal:tables', 'can-use'); tick('personal:prices', 'load-at-start'); true")
    assert await js(f"{PANEL}.querySelector('.agent-skill[data-ref=\"personal:prices\"] .can-use').checked")  # implied
    assert await js(f"{PANEL}.querySelector('.skills-note').textContent") == "Can use 2 skills only."
    await js(f"{PANEL}.querySelector('.save-agent').click(); true")
    await wait_for(lambda: server.saved.get("research") is not None)
    saved = server.saved.get("research")
    assert (saved.name, saved.description, saved.instruction, saved.web, saved.model, saved.auto) == (
        "Research", "Rivals' prices", "Answer in French.\nKeep a table.", "brave", "haiku", True)
    assert (saved.use, saved.load, saved.profile, saved.folder) == (["personal:prices", "personal:tables"],
                                                                    ["personal:prices"], None, None)
    assert await until(js, f"{PANEL}.querySelector('.agent-note').textContent === 'Saved.' && {card('research')}"
                           " !== null")
    await js(f"{PANEL}.querySelector('.agent-skill[data-ref=\"personal:prices\"] .can-use').click(); true")
    assert not await js(f"{PANEL}.querySelector('.agent-skill[data-ref=\"personal:prices\"] .load-at-start').checked")
    await js(f"{in_panel('agent-name')}.value = ''; {PANEL}.querySelector('.save-agent').click(); true")
    assert await until(js, f"{PANEL}.querySelector('.agent-note').textContent === 'An agent needs a name'")
    assert server.saved.get("research").name == "Research"  # refused: nothing written


@CHROME
async def test_an_agents_tasks_run_as_it_and_runs_as_moves_one_there(stack):
    server = stack["server"]
    saved = server.saved.save(AGENT)
    stack["workflows"].save({"name": "Footer", "instructions": "Fix it"})
    js = await open_agents(stack)
    any_task = "document.querySelector('#page-agents .any-tasks .workflow[data-slug=\"footer\"]')"
    assert await until(js, f"{any_task} !== null")
    await js(f"{card(saved.slug)}.click(); true")
    form = f"{PANEL}.querySelector('.agent-tasks .workflow-form')"
    assert await until(js, f"{form} !== null && {form}.querySelector('[name=runs_as]') === null")  # it is its own
    await js(f"{form}.querySelector('[name=name]').value = 'Weekly prices';"
             f"{form}.querySelector('[name=instructions]').value = 'List this week\\'s prices';"
             f"{form}.querySelector('.save').click(); true")
    await wait_for(lambda: getattr(stack["workflows"].get("weekly-prices"), "runs_as", None) == "research")
    assert await until(js, f"{PANEL}.querySelector('.agent-tasks .workflow[data-slug=\"weekly-prices\"] .delete')"
                           "?.textContent === 'Remove'")
    assert await js("document.querySelector('#page-agents .any-tasks .workflow[data-slug=\"weekly-prices\"]')"
                    " === null")
    await js(f"{PANEL}.querySelector('header button').click(); true")
    await js(f"{any_task}.querySelector('.edit').click(); true")  # Tasks for any agent: Runs as moves it
    pick = "document.querySelector('#page-agents .any-tasks .workflow-form [name=runs_as]')"
    assert await until(js, f"[...{pick}.options].map(option => option.textContent).join('|') === "
                           "'A new agent|Research'")
    await js(f"{pick}.value = 'research'; document.querySelector('#page-agents .any-tasks .save').click(); true")
    await wait_for(lambda: stack["workflows"].get("footer").runs_as == "research")
    assert await until(js, f"{any_task} === null")


@CHROME
async def test_save_keeps_an_agents_folder_and_account_or_refuses_them_with_words(stack):
    server = stack["server"]
    place = stack["user"] / "Project"
    place.mkdir(parents=True)
    kept = server.saved.save({**AGENT, "name": "Kept", "folder": str(place)})
    gone = server.saved.save({**AGENT, "name": "Gone", "folder": str(stack["user"] / "Gone"), "account": "old"})
    js = await open_agents(stack)
    assert await until(js, f"{card(kept.slug)} !== null")
    await js(f"{card(kept.slug)}.click(); {PANEL}.querySelector('.save-agent').click(); true")  # before the check
    assert await until(js, f"{PANEL}.querySelector('.agent-note').textContent === 'Saved.'")
    assert server.saved.get(kept.slug).folder == str(place)  # never folder: null
    await js(f"{PANEL}.querySelector('header button').click(); {card(gone.slug)}.click(); true")
    assert await until(js, f"{in_panel('agent-account')}.value === 'old'")  # an account no longer listed stays
    assert await until(js, f"{PANEL}.querySelector('.folder-note')?.textContent.startsWith(\"That folder isn't\")")
    await js(f"{PANEL}.querySelector('.save-agent').click(); true")
    assert await until(js, f"{PANEL}.querySelector('.agent-note').textContent === 'Pick one of the accounts listed'")
    await js(f"{in_panel('agent-account')}.value = ''; {PANEL}.querySelector('.save-agent').click(); true")
    assert await until(js, f"{PANEL}.querySelector('.agent-note').textContent.startsWith(\"That folder isn't\")")
    assert (server.saved.get(gone.slug).folder, server.saved.get(gone.slug).account) == (
        str(stack["user"] / "Gone"), "old")  # refused: nothing written


# ---- Build a Mission's Agent ▾: a saved agent's settings apply, one run at a time (Task 16) -------------------------

@CHROME
async def test_build_a_mission_runs_a_saved_agent_with_its_own_settings(stack):
    server = stack["server"]
    server.saved.save({**AGENT, "auto_approve": True})
    stack["script"].write_text(json.dumps([{"sleep": 30}]), encoding="utf-8")  # its run stays at work
    js = await open_mission(stack)
    pick = "document.getElementById('task-agent')"
    assert await until(js, f"[...{pick}.options].map(option => option.textContent).join('|') === 'New agent|Research'")
    await js(f"{pick}.value = 'research'; {pick}.dispatchEvent(new Event('change')); true")
    own = "['mission-words', 'task-web', 'task-model', 'task-folder', 'task-auto-switch', 'task-skills']"
    assert await js(f"{own}.every(id => document.getElementById(id).hidden)")  # its settings, not the pickers'
    await js("document.getElementById('task').value = 'List the prices'; document.getElementById('start').click(); true")
    await wait_for(lambda: server.agents.run_of("research") is not None)
    run = server.agents.run_of("research")
    assert (run.name, run.description, run.model, run.web, run.auto) == (
        "Research", AGENT["description"], "opus", "brave", True)
    assert await until(js, "!document.getElementById('start').disabled && document.getElementById('task').value === ''")
    await js("document.getElementById('task').value = 'And the yearly ones';"
             "document.getElementById('start').click(); true")
    await wait_for(lambda: run.queued == 1)  # its run works: the task is a message to it
    assert list(server.agents.agents) == [run.id]
    await js(f"{pick}.value = ''; {pick}.dispatchEvent(new Event('change')); true")
    assert await js(f"{own}.every(id => !document.getElementById(id).hidden)")  # New agent: the pickers again
