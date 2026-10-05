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
