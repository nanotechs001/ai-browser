"""AI Home's features, found in Mission Control and Settings (the saved-agents spec, 6): Brave's connection, Settings →
Brave, the Tabs page, a one-off run's skills, the drawer's run pieces, the Brain's limit card, a notification's click
and the window's count. Against a real app server (agents on the fake claude) in a throwaway headless Chrome; every
word stays text."""

import json

import pytest

from ai_browser.chrome import chrome_binary
from test_app_server import wait_for
from test_home import HOSTILE, open_settings, stack, until  # noqa: F401  (fixtures)
from test_mission import open_drawer, open_mission

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
BAR = "document.getElementById('brave-bar')"
CHIP = "(target => document.querySelector(`#tabs .tab[data-target='${target}'] .chip`)?.textContent)"


def page_link(name):
    return f"document.querySelector('.page-link[data-page={json.dumps(name)}]')"


def in_row(target, selector):
    return f"document.querySelector(\"#tabs .tab[data-target='{target}'] {selector}\")"


# ---- Brave's connection, at the top of Mission Control (Task 9) ------------------------------------------------------

@CHROME
async def test_mission_control_shows_braves_connection_until_it_is_connected(stack):
    brave = stack["brave"]
    js = await open_mission(stack)
    assert await until(js, f"{BAR}.hidden === true")  # connected: nothing to say
    brave.set_state("off")
    assert await until(js, f"!{BAR}.hidden && {BAR}.querySelector('.brave-title').textContent"
                           " === 'Your Brave · switch off'")
    assert await js(f"[...{BAR}.querySelectorAll('.brave-steps li')].map(item => item.textContent)") == [
        "In Brave, open brave://inspect/#remote-debugging.", 'Tick "Allow remote debugging for this browser instance".',
        'When Brave asks "Allow remote debugging?", click Allow.']
    assert await js(f"{BAR}.querySelector('.brave-action').textContent") == "Show me how"
    brave.set_state("ready")
    assert await until(js, f"{BAR}.querySelector('.brave-action').textContent === 'Connect'"
                           f" && {BAR}.querySelector('.brave-steps').hidden")
    await js(f"{BAR}.querySelector('.brave-action').click(); true")
    await wait_for(lambda: brave.connects == 1)  # Connect: the app asks Brave, which asks the user once
    brave.set_state("asking")
    assert await until(js, f"{BAR}.querySelector('.brave-action').hidden && {BAR}.querySelector('.brave-note')"
                           ".textContent.startsWith('Brave is asking \"Allow remote debugging?\"')")
    brave.set_state("refused")
    assert await until(js, f"{BAR}.querySelector('.brave-action').textContent === 'Try again'"
                           f" && {BAR}.querySelector('.brave-note').textContent === 'Brave said no.'")
    brave.set_state("connected")
    assert await until(js, f"{BAR}.hidden === true")
    brave.set_state("off")
    assert await until(js, f"!{BAR}.hidden")
    await js(f"{BAR}.querySelector('.brave-action').click(); true")  # Show me how: the setup steps' own page
    assert await until(js, "location.pathname === '/setup' && location.hash === '#switch'")


# ---- Settings → Brave: what uses Brave through AI Browser, Brave's old extension; Settings' own styles (Task 10) ----

CLIENTS = [
    {"id": "app", "kind": "app", "number": None, "name": "AI Browser", "color": "", "tabs": 0, "connected": True,
     "cut_off": False},
    {"id": "a3", "kind": "agent", "number": 3, "name": "Fix the footer", "color": "blue", "tabs": 2, "connected": True,
     "cut_off": False},
    {"id": "cc-x", "kind": "session", "number": None, "name": "Claude Code", "color": "orange", "tabs": 1,
     "connected": True, "cut_off": False},
    {"id": "a4", "kind": "agent", "number": 4, "name": "<img src=x onerror=alert(1)>", "color": "red", "tabs": 0,
     "connected": True, "cut_off": False}]


@CHROME
async def test_settings_lists_what_uses_brave_with_disconnect(stack):
    server, brave = stack["server"], stack["brave"]
    settings = await open_settings(stack)
    assert await until(settings, "document.getElementById('brave-state').textContent"
                                 " === 'Brave is connected to AI Browser.'")
    server._send_all({"type": "browser_clients", "clients": CLIENTS})
    labels = "[...document.querySelectorAll('#brave-clients li span')].map(span => span.textContent)"
    assert await until(settings, f"{labels}.length === 4")
    assert await settings(labels) == ["AI Browser · the tab list and pictures", "3 · Fix the footer · 2 tabs",
                                      "Claude Code · 1 tab", "4 · <img src=x onerror=alert(1)> · 0 tabs"]
    assert await settings("document.querySelectorAll('#brave-clients img').length") == 0  # text stays text
    assert await settings("[...document.querySelectorAll('#brave-clients li')].map(li => !!li.querySelector("
                          "'button'))") == [False, True, True, True]
    assert await settings("document.getElementById('brave-using-title').textContent") == (
        "Using your Brave through AI Browser")
    await settings("document.querySelectorAll('#brave-clients li')[1].querySelector('button').click(); true")
    await wait_for(lambda: brave.relay.disconnected == ["a3"])
    brave.set_state("lost")
    assert await until(settings, "document.getElementById('brave-state').textContent === \"Brave isn't connected: "
                                 "connect it at the top of Mission Control.\" && document.getElementById('brave-using')"
                                 ".hidden")
    assert await settings("getComputedStyle(document.querySelector('.card')).borderRadius") == "12px"  # its own styles
    assert await settings("[...document.styleSheets].map(sheet => sheet.href.split('/').pop())") == [
        "theme.css", "settings.css"]


@CHROME
async def test_settings_says_the_old_extension_can_be_removed_until_got_it(stack):
    server = stack["server"]
    settings = await open_settings(stack)
    note = "document.getElementById('watcher-note')"
    assert await settings(f"{note}.hidden") is True  # no old folder here: nothing to say
    folder = stack["home"] / "app" / "watcher"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text("{}", encoding="utf-8")  # an earlier AI Browser made it
    server._send_all({"type": "settings", **server._settings_payload()})
    assert await until(settings, f"!{note}.hidden")
    text = " ".join((await settings(f"{note}.textContent")).split())
    assert 'You can remove "AI Browser Watcher" from Brave' in text and "AI Browser never removes it for you." in text
    await settings("document.getElementById('watcher-note-close').click(); true")
    await wait_for(lambda: server.settings.get()["watcher_note"] is False)
    assert (folder / "manifest.json").is_file()  # AI Browser never removes it
    server._send_all({"type": "settings", **server._settings_payload()})
    assert await until(settings, f"{note}.hidden")


# ---- the Tabs page: the user's tabs, whose each one is, Hand over and Take back (Task 11) ---------------------------

@CHROME
async def test_the_tabs_page_marks_owners_and_hands_tabs_over(stack):
    from fake_brave import FakeBrave

    server = stack["server"]
    agent = await server.agents.create("Fix the footer")
    brave = FakeBrave([{"target": "T1", "url": "https://shop.example/cart", "title": "Agent page"},
                       {"target": "U1", "url": "https://mail.example/", "title": HOSTILE},
                       {"target": "U2", "url": "https://docs.example/", "title": "Docs"},
                       {"target": "S1", "url": "https://s.example/", "title": "Session page"},
                       {"target": "B1", "url": "https://mail.example/#t1", "title": "Thread"}])
    mine = {"id": agent.id, "name": agent.name, "color": agent.color}
    brave.owners.update({"T1": {"kind": "agent", **mine}, "U2": {"kind": "handed", **mine},
                         "S1": {"kind": "session", "id": "cc-x", "name": "Claude Code", "color": "orange"},
                         "B1": {"kind": "brain", "name": "Brain", "color": "purple"}})
    agent.adopted.append("U2")  # handed to it, as Hand over leaves it: only a handed tab can be taken back
    server.attach_brave(brave)
    js = await open_mission(stack)
    await js(f"{page_link('tabs')}.click(); true")
    assert await until(js, f"{CHIP}('T1') === '1 · Fix the footer'")
    assert await js(f"['S1', 'B1', 'U2', 'U1'].map({CHIP})") == ["Claude Code", "Brain",
                                                                 "handed to 1 · Fix the footer", "you"]
    assert "<img" in await js(f"{in_row('U1', '.title')}.textContent")  # a hostile title stays text
    assert await js("document.querySelectorAll('#tabs img').length") == 0 and await js("document.title") != "pwned"
    assert await js(f"[{in_row('U1', '.hand')}.hidden, {in_row('T1', '.hand')}.hidden, {in_row('B1', '.hand')}.hidden,"
                    f" {in_row('U2', '.take')}.hidden]") == [False, True, False, False]
    await js(f"{in_row('U1', '.title')}.click(); true")  # a click on a row brings that tab to the front
    await wait_for(lambda: brave.watched == ["U1"])
    await js(f"{in_row('U1', '.hand')}.click(); true")
    assert "The agent will read this tab and act in it." in await js(f"{in_row('U1', '.menu')}.textContent")
    assert await js(f"{in_row('U1', '.menu')}.getBoundingClientRect().height < 200")  # never the left menu's look
    await js(f"{in_row('U1', f'.give[data-id={agent.id}]')}.click(); true")
    await wait_for(lambda: "U1" in agent.adopted)
    await js(f"{in_row('U2', '.take')}.click(); true")
    assert await until(js, f"{CHIP}('U2') === 'you'")
    await js(f"{in_row('B1', '.hand')}.click(); true")
    await js(f"{in_row('B1', '.new')}.click(); true")  # New agent…: Build a Mission, starting in that tab
    assert await until(js, "!document.getElementById('page-dashboard').hidden && document.getElementById("
                           "'handing-text').textContent === 'Starts in your tab: Thread'")
    await js("document.getElementById('task').value = 'reply to it'; document.getElementById('start').click(); true")
    await wait_for(lambda: len(server.agents.agents) == 2)
    assert server.agents.agents["a2"].adopted == ["B1"]
    assert await until(js, "document.getElementById('handing').hidden")  # the next Start begins anywhere again


LAST_USED = "Showing the Brave profile you used last. Pick the one agents use in Settings → Where agents browse."
NO_PROFILE = "Your tabs aren't listed: AI Browser can't tell which Brave profile is yours yet."


@CHROME
async def test_the_tabs_page_counts_what_it_doesnt_show_and_claims_nothing_unconnected(stack):
    from fake_brave import FakeBrave

    brave = FakeBrave([{"target": "U1", "url": "https://mail.example/", "title": "Mail"}])
    brave.set_scope("chosen", 3)
    stack["server"].attach_brave(brave)
    js = await open_mission(stack)
    await js(f"{page_link('tabs')}.click(); true")
    source = "document.querySelector('#tabs p.scope-source')?.textContent ?? null"
    count = "document.querySelector('#tabs p.elsewhere')?.textContent ?? null"
    empty = "document.querySelector('#tabs .empty')?.textContent ?? null"

    async def shows(expression, text):
        return await until(js, f"({expression}) === {json.dumps(text)}")

    assert await shows(count, "3 more tabs in other profiles or private windows: not shown here.")
    brave.set_scope("last_used", 0)
    assert await shows(source, LAST_USED) and await js(count) is None
    brave.set_scope("none", 2)
    assert await shows(source, NO_PROFILE)
    brave.pages = []
    brave.set_scope("chosen", 0)
    assert await shows(empty, "No web pages open in this profile.")
    brave.set_scope("none", 4)
    brave.set_state("ready")  # while Brave isn't connected, the list claims nothing about profiles
    assert await shows(empty, "No web pages open in your browser.")
    assert await js(source) is None and await js(count) is None
    brave.set_state("connected")  # connected again: the scope sent before is stale until the new connection's list
    assert await until(js, f"{BAR}.hidden")
    assert await js(source) is None and await js(count) is None
    brave.changed()  # the new connection's first list brings its own scope
    assert await shows(source, NO_PROFILE)


# ---- a one-off run's skills: Build a Mission's Skills, and Knowledge's uses (Task 12) ---------------------------------

def user_skills(stack, monkeypatch):
    """A skill of the user's in the stack's throwaway folder: the catalog reads it there, never ~/.claude."""
    from ai_browser import skills
    from test_skills import make_skill

    make_skill(stack["user"] / ".claude" / "skills", "prices", desc="Read price pages")
    monkeypatch.setattr(skills, "user_folders", lambda: (stack["user"] / ".claude", stack["user"] / "Claude"))
    stack["server"].skills_changed()  # read again: every page hears the list


@CHROME
async def test_build_a_mission_loads_the_skills_picked_at_start(stack, monkeypatch):
    server = stack["server"]
    user_skills(stack, monkeypatch)
    asked = []
    create = server.agents.create

    async def recording(text, skills=(), *args, **options):  # what the page asked the app for
        asked.append(list(skills))
        return await create(text, skills, *args, **options)

    monkeypatch.setattr(server.agents, "create", recording)
    js = await open_mission(stack)
    box = "document.querySelector('#skills-pick input[value=\"personal:prices\"]')"
    assert await until(js, f"{box} !== null")
    await js("document.getElementById('task-skills').open = true;"
             f"{box}.click(); true")
    assert await js("document.getElementById('skills-count').textContent") == "(1)"
    await js("document.getElementById('task').value = 'List the prices';"
             "document.getElementById('start').click(); true")
    await wait_for(lambda: asked == [["personal:prices"]])
    assert await until(js, f"!{box}.checked && document.getElementById('skills-count').textContent === ''")
    await js("document.getElementById('mode-ask').click(); true")
    assert await js("document.getElementById('task-skills').hidden") is True  # Build a Mission's only


@CHROME
async def test_knowledge_says_who_uses_a_skill_and_hands_it_on(stack, monkeypatch):
    server = stack["server"]
    stack["script"].write_text(json.dumps([{"sleep": 30}]), encoding="utf-8")  # it stays at work
    agent = await server.agents.create("Fix the footer")
    user_skills(stack, monkeypatch)
    js = await open_mission(stack)
    await js(f"{page_link('knowledge')}.click(); true")
    row = "document.querySelector('#page-knowledge .skill[data-ref=\"personal:prices\"]')"
    assert await until(js, f"{row} !== null")
    agent.loaded_skills = ["personal:prices"]
    server.agents._changed(agent)
    assert await until(js, f"{row}.querySelector('.in-use').textContent === 'in use by Fix the footer'")
    await js(f"{row}.querySelector('select.ask-who').value = 'a1'; {row}.querySelector('.ask').click(); true")
    await wait_for(lambda: any(event.get("text") == "Load and use the skill personal:prices with load_skill"
                               for event in server.agents.events_of("a1")))
    await js(f"{row}.querySelector('.use').click(); true")  # Use in new mission
    assert await until(js, "!document.getElementById('page-dashboard').hidden && document.querySelector("
                           "'#skills-pick input[value=\"personal:prices\"]').checked")
    assert await js("document.activeElement.id") == "task"


# ---- the drawer: Save as skill, time, cost and skills loaded; the Brain's inbox: its limit card (Task 13) ------------

@CHROME
async def test_the_drawer_shows_cost_and_skills_and_saves_a_skill(stack):
    server = stack["server"]
    agent = await server.agents.create("Fix the footer")
    await wait_for(lambda: agent.state == "your_turn")
    agent.cost, agent.loaded_skills = 0.25, ["personal:prices"]
    server.agents._changed(agent)
    js = await open_mission(stack)
    assert await until(js, "document.querySelector('.station[data-id=\"a1\"]') !== null")
    await js(open_drawer("a1"))
    totals = "document.querySelector('#drawer-body .totals')?.textContent"
    assert await until(js, f"{totals}?.endsWith(' · $0.25 · skills: personal:prices')")
    await js("document.querySelector('#drawer-body .save-skill').click(); true")  # Knowledge's Train drafts it
    assert await until(js, "!document.getElementById('page-knowledge').hidden && document.querySelector("
                           "'#page-knowledge .train-body').textContent.includes(\"Drafting a skill from 1 · Fix "
                           "the footer's chat…\")")


@CHROME
async def test_the_brains_inbox_has_its_limit_card_and_turn_it_on(stack):
    from fake_accounts import sign_in

    server, accounts = stack["server"], stack["accounts"]
    work = accounts.add("Work")
    sign_in(work.folder)
    await server._refresh_accounts()
    js = await open_mission(stack)
    await js("document.getElementById('bubble').click(); true")  # the globe's drawer: the Brain's inbox
    card = "document.querySelector('#drawer-body .brain-limit')"
    assert await until(js, f"{card} !== null && {card}.hidden")  # no limit: no card
    server._brain_limit_hit({"account": "default", "resets_at": None})
    assert await until(js, f"!{card}.hidden && {card}.querySelector('.account-ask-head').textContent"
                           " === 'The Brain hit its limit on Default. Continue on Work?'")
    await js(f"{card}.querySelector('.continue').click(); true")
    await wait_for(lambda: accounts.brain_id() == work.id)
    assert await until(js, f"{card}.hidden")
    turn_on = "document.querySelector('#drawer-body .brain-turn-on')"
    assert await until(js, f"{turn_on} !== null && !{turn_on}.hidden")  # reading is off: Turn it on in Settings
    await js(f"{turn_on}.click(); true")
    assert await until(js, "location.pathname === '/settings' && location.hash === '#brain-section'")


# ---- a notification's click and the window's count: Mission Control's (Task 14) -------------------------------------

@CHROME
async def test_mission_controls_title_counts_the_working_agents(stack):
    from test_bridge import EVENTS

    js = await open_mission(stack)
    stack["script"].write_text(json.dumps([EVENTS[0], {"sleep": 30}]), encoding="utf-8")  # it stays at work
    agent = await stack["server"].agents.create("keep working")
    assert await until(js, "document.title === '(1) Mission Control'")  # the window's title and badge read it
    await stack["server"].agents.stop(agent.id)
    assert await until(js, "document.title === 'Mission Control'")


# ---- the words: none the user or Claude reads names AI Home (Task 19) ------------------------------------------------

WORDS = ("agentlink.py", "browser.py", "cli.py", "engine.py", "settings.py", "app/__init__.py", "app/agents.py",
         "app/bravelink.py", "app/bridge.py", "app/cdprelay.py", "app/run.py", "app/tabs.py", "app/window.py",
         "brain/account.py", "brain/workflows.py", "desktop/notes.py", "desktop/electron/main.js",
         "desktop/electron/preload.js", "app/ui/setup.html", "app/ui/accountui.js", "app/ui/brainui.css",
         "app/ui/brainui.js", "app/ui/permission.js", "app/ui/plan.js", "app/ui/settings.css", "app/ui/tabspage.js",
         "app/ui/tools.js", "app/ui/train.js", "app/ui/uploads.js")


def test_no_word_the_user_or_claude_reads_names_ai_home():
    from pathlib import Path

    from ai_browser import engine

    root = Path(__file__).parents[1] / "src" / "ai_browser"
    for name in WORDS:
        assert "AI Home" not in (root / name).read_text(encoding="utf-8"), name
    for text in (engine.ASK_AGENT, engine.CUT_OFF_AGENT, engine.CUT_OFF_SESSION):
        assert "AI Home" not in text
    assert "the top of Mission Control" in engine.ASK_AGENT


# ---- AI Home's last sections, now Mission Control's: Integrations, Tasks for any agent, Train (Task 20) ----------------

@CHROME
async def test_integrations_switch_a_server_on_and_forget_an_always_allowed_tool(stack, tmp_path):
    from test_tools import user_config

    user_config(tmp_path)
    stack["tools"].allow_always("mcp__figma__get_file")
    js = await open_mission(stack)
    await js(f"{page_link('integrations')}.click(); true")
    server = "document.querySelector('#page-integrations .tool-server[data-name=\"figma\"]')"
    assert await until(js, f"{server} !== null")
    await js(f"{server}.querySelector('.on').click(); true")
    await wait_for(lambda: stack["tools"].enabled() == {"figma"})
    forget = "document.querySelector('#page-integrations .always-tool[data-tool=\"mcp__figma__get_file\"] .forget')"
    assert await until(js, f"{forget} !== null")
    await js(f"{forget}.click(); true")
    await wait_for(lambda: stack["tools"].always() == set())


@CHROME
async def test_a_task_for_any_agent_is_saved_from_the_form_and_runs_once(stack):
    import asyncio

    js = await open_mission(stack)
    await js(f"{page_link('agents')}.click(); true")
    form = "document.querySelector('#page-agents .any-tasks .workflow-form')"
    assert await until(js, f"{form} !== null")
    await js("document.querySelector('#page-agents .any-tasks details.new-task > summary').click(); true")  # unfolded
    assert await js("document.querySelector('#page-agents .any-tasks details.new-task').open")
    await js(f"const form = {form};"
             "form.querySelector('[name=name]').value = 'Morning report';"
             "form.querySelector('[name=instructions]').value = 'Check the sites and tell me what changed';"
             "form.querySelector('[name=trigger]').value = 'schedule';"
             "form.querySelector('[name=trigger]').dispatchEvent(new Event('change'));"
             "form.querySelector('[name=schedule]').value = 'weekdays 09:00';"
             "form.querySelector('.save').click(); true")
    task = "document.querySelector('#page-agents .any-tasks .workflow[data-slug=\"morning-report\"]')"
    assert await until(js, f"{task} !== null")
    path = stack["home"] / "workflows" / "morning-report.md"
    assert path.exists() and "weekdays 09:00" in path.read_text(encoding="utf-8")
    assert str(path) in await js(f"{form}.querySelector('.saved').textContent")  # it says where the file is
    await js(f"const run = {task}.querySelector('.run'); run.click(); run.click(); true")  # a double click: one run
    await wait_for(lambda: len(stack["server"].agents.agents) == 1)
    await asyncio.sleep(1)
    assert len(stack["server"].agents.agents) == 1


DRAFT = f"""---
name: elementor-landing
description: Build landing pages {HOSTILE}
---
# Elementor landing pages

1. Start from the Landing template.
"""


@CHROME
async def test_knowledge_trains_a_skill_and_saves_it_after_review(stack, monkeypatch):
    from ai_browser import skills
    from test_bridge import EVENTS

    monkeypatch.setattr(skills, "user_folders", lambda: (stack["user"] / ".claude", stack["user"] / "Claude"))
    stack["script"].write_text(json.dumps({"default": EVENTS, "You write a skill": [{"result": DRAFT}]}),
                               encoding="utf-8")
    js = await open_mission(stack)
    await js(f"{page_link('knowledge')}.click(); true")
    train = "document.querySelector('#page-knowledge .train-body')"
    assert await until(js, f"{train}?.querySelector('.job') != null")
    await js(f"{train}.querySelector('.job').value = 'build Elementor landing pages the way I like';"
             f"{train}.querySelector('.draft').click(); true")
    assert await until(js, f"{train}.querySelector('.skill-text').value.includes('elementor-landing')")
    assert await js(f"{train}.querySelectorAll('img').length") == 0 and await js("document.title") != "pwned"
    assert await js(f"{train}.querySelector('.skill-name').textContent") == "elementor-landing"
    await js(f"const text = {train}.querySelector('.skill-text');"
             "text.value = text.value.replace('Start from the Landing template.', 'Start from the Hero template.');"
             f"{train}.querySelector('.save').click(); true")
    skill = stack["user"] / ".claude" / "skills" / "elementor-landing" / "SKILL.md"
    await wait_for(skill.exists)
    assert "Hero template" in skill.read_text(encoding="utf-8")
    assert await until(js, "document.querySelector('#page-knowledge .skill[data-ref=\"personal:elementor-landing\"]')"
                           " !== null")  # the list reads it again


# ---- nothing the user reads names AI Home (Task 21) -----------------------------------------------------------------

def test_no_page_the_app_or_the_readme_names_ai_home():  # the saved-agents spec, 6: AI Home has gone
    from pathlib import Path

    root = Path(__file__).parents[1]
    app = root / "src" / "ai_browser" / "app"
    pages = [path for path in sorted((app / "ui").iterdir()) if path.suffix in (".html", ".js", ".css")]
    electron = sorted((root / "src" / "ai_browser" / "desktop" / "electron").glob("*.js"))
    assert pages and electron
    for path in [*pages, *electron, app / "server.py", root / "README.md"]:
        assert "AI Home" not in path.read_text(encoding="utf-8"), path.name
