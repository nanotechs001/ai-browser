"""AI Home's phase-2 sections against a real app server (agents on the fake claude): the permission card (also in the
chat panel and on the watcher's Brain page, with a Brave notification), Tools, Workflows, and Train a new agent."""

import asyncio
import json

import pytest

from ai_browser.chrome import chrome_binary
from test_bridge import EVENTS
from test_home import HOSTILE, evaluate, home, open_page, post_tab, stack, until  # noqa: F401  (fixtures)
from test_panel import panel  # noqa: F401  (fixture)
from test_tools import answers, asking, user_config
from test_watcher import watcher  # noqa: F401  (fixture)

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
DRAFT = f"""---
name: elementor-landing
description: Build landing pages {HOSTILE}
---
# Elementor landing pages

1. Start from the Landing template.
"""


def ask_for_clickup(stack, tmp_path):
    """The agents' tools: ClickUp switched on; the fake claude asks for one of its tools."""
    user_config(tmp_path)
    stack["tools"].set_enabled("clickup", True)
    stack["script"].write_text(json.dumps(asking()))


async def answered(log):
    for _ in range(50):
        if answers(log):
            break
        await asyncio.sleep(0.1)
    return answers(log)


@CHROME
async def test_a_permission_prompt_is_answered_from_ai_home(home, tmp_path):
    js, _, stack = home
    ask_for_clickup(stack, tmp_path)
    agent = await stack["server"].agents.create("make a ClickUp task")
    row = f"document.querySelector('.agent[data-id=\"{agent.id}\"]')"
    assert await until(js, f"{row} !== null && {row}.querySelector('.permission') !== null")
    assert await js(f"{row}.querySelector('.chip').textContent") == "needs you"
    card = await js(f"{row}.querySelector('.permission').textContent")
    assert "clickup" in card and "create_task" in card and '"name": "Fix footer"' in card
    await js(f"{row}.querySelector('.permission .allow-once').click(); true")
    assert await answered(stack["log"]) == [{"behavior": "allow", "updatedInput": {"name": "Fix footer"}}]
    assert await until(js, f"{row}.querySelector('.permission') === null")


@CHROME
async def test_the_panel_shows_the_same_card(panel, tmp_path):
    js, user_tab, stack = panel
    ask_for_clickup(stack, tmp_path)
    agent = await stack["server"].agents.create("make a ClickUp task")
    await post_tab(stack, agent.id, "working_tab", user_tab)
    assert await until(js, "document.querySelector('#permission-slot .permission') !== null")
    await js("document.querySelector('#permission-slot .deny').click(); true")
    assert [answer["behavior"] for answer in await answered(stack["log"])] == ["deny"]


@CHROME
async def test_tools_page_switches_a_server_and_forgets_a_tool(home, tmp_path):
    js, _, stack = home
    user_config(tmp_path)
    stack["tools"].allow_always("mcp__figma__get_file")
    await js("document.getElementById('tools-section').open = true;"
             "document.getElementById('tools-section').dispatchEvent(new Event('toggle')); true")
    server = "document.querySelector('.tool-server[data-name=\"figma\"]')"
    assert await until(js, f"{server} !== null")
    await js(f"{server}.querySelector('.on').click(); true")
    for _ in range(50):
        if "figma" in stack["tools"].enabled():
            break
        await asyncio.sleep(0.1)
    assert stack["tools"].enabled() == {"figma"}
    forget = "document.querySelector('.always-tool[data-tool=\"mcp__figma__get_file\"] .forget')"
    assert await until(js, f"{forget} !== null")
    await js(f"{forget}.click(); true")
    for _ in range(50):
        if not stack["tools"].always():
            break
        await asyncio.sleep(0.1)
    assert stack["tools"].always() == set()


@CHROME
async def test_a_workflow_is_saved_from_the_form_and_run(home):
    js, _, stack = home
    await js("document.getElementById('workflows-section').open = true; true")
    form = "document.querySelector('.workflow-form')"
    assert await until(js, f"{form} !== null")
    await js(f"const form = {form};"
             "form.querySelector('[name=name]').value = 'Morning report';"
             "form.querySelector('[name=instructions]').value = 'Check the sites and tell me what changed';"
             "form.querySelector('[name=trigger]').value = 'schedule';"
             "form.querySelector('[name=trigger]').dispatchEvent(new Event('change'));"
             "form.querySelector('[name=schedule]').value = 'weekdays 09:00';"
             "form.querySelector('.save').click(); true")
    assert await until(js, "document.querySelector('.workflow[data-slug=\"morning-report\"]') !== null")
    path = stack["home"] / "workflows" / "morning-report.md"
    assert path.exists() and "weekdays 09:00" in path.read_text()
    assert str(path) in await js(f"{form}.querySelector('.saved').textContent")  # it says where the file is
    await js("const run = document.querySelector('.workflow[data-slug=\"morning-report\"] .run');"
             "run.click(); run.click(); true")  # a double click: one run
    for _ in range(50):
        if stack["server"].agents.agents:
            break
        await asyncio.sleep(0.1)
    await asyncio.sleep(1)
    assert len(stack["server"].agents.agents) == 1


@CHROME
async def test_train_a_new_agent_saves_a_skill_after_review(home, monkeypatch):
    js, _, stack = home
    monkeypatch.setenv("HOME", str(stack["user"]))  # the skills list reads ~/.claude/skills
    monkeypatch.setenv("USERPROFILE", str(stack["user"]))  # Path.home() on Windows
    stack["script"].write_text(json.dumps({"default": EVENTS, "You write a skill": [{"result": DRAFT}]}))
    await js("document.getElementById('train-section').open = true; true")
    train = "document.getElementById('train')"
    await js(f"{train}.querySelector('.job').value = 'build Elementor landing pages the way I like';"
             f"{train}.querySelector('.draft').click(); true")
    assert await until(js, f"{train}.querySelector('.skill-text').value.includes('elementor-landing')")
    assert await js("document.querySelectorAll('#train img').length") == 0 and await js("document.title") != "pwned"
    assert await js(f"{train}.querySelector('.skill-name').textContent") == "elementor-landing"
    await js(f"const text = {train}.querySelector('.skill-text');"
             "text.value = text.value.replace('Start from the Landing template.', 'Start from the Hero template.');"
             f"{train}.querySelector('.save').click(); true")
    skill = stack["user"] / ".claude" / "skills" / "elementor-landing" / "SKILL.md"
    for _ in range(50):
        if skill.exists():
            break
        await asyncio.sleep(0.1)
    assert "Hero template" in skill.read_text()
    assert await until(js, "[...document.querySelectorAll('#skill-list .skill .name')]"
                           ".some(node => node.textContent === 'elementor-landing')")


@CHROME
async def test_the_watcher_shows_a_permission_request(watcher, tmp_path):
    from ai_browser.brain.tools import ToolsConfig

    tools = ToolsConfig(watcher.home, claude_home=user_config(tmp_path))
    tools.set_enabled("clickup", True)
    watcher.server.agents.tools = tools
    watcher.script.write_text(json.dumps(asking()))
    _, js = await open_page(watcher.cdp, f"chrome-extension://{watcher.app.extension_id}/brain.html")
    await watcher.server.agents.create("make a ClickUp task")
    assert await until(watcher.worker_js, "chrome.notifications.getAll().then(all => Object.keys(all).length === 1)")
    assert await until(js, "document.querySelector('#permissions .permission') !== null")
    assert "create_task" in await js("document.querySelector('#permissions .permission').textContent")
    await js("document.querySelector('#permissions .deny').click(); true")
    assert [answer["behavior"] for answer in await answered(watcher.log)] == ["deny"]
