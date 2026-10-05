"""The Brain's section in AI Home (the inbox, its cards and buttons), against a real app server with the Brain. Page
and message text stays text."""

import asyncio
import json

import pytest

from ai_browser.chrome import chrome_binary
from test_home import HOSTILE, home, stack, until  # noqa: F401  (fixtures)

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


def item(**fields):
    from ai_browser.brain.store import Item

    return Item(**{"id": "gmail:t1", "site": "gmail", "raw_id": "t1", "sender": "Maria", "subject": "Launch date",
                   "snippet": "Can we move the launch to Monday?", "url": "https://mail.google.com/mail/u/0/#all/t1",
                   "kind": "needs_reply", "summary": "Maria asks to move the launch", "why": "a client",
                   "suggest": "draft", **fields})


def show(brain, entry):
    brain.store.put(entry)
    brain.broadcast({"type": "brain_item", "item": entry.public()})


@CHROME
async def test_ai_home_shows_the_needs_you_items_as_text(home):
    js, stack = home
    show(stack["brain"], item(sender=HOSTILE, subject=HOSTILE, summary=HOSTILE))
    assert await until(js, "document.querySelectorAll('#brain .brain-item').length === 1")
    assert "<img" in await js("document.querySelector('#brain .brain-item .summary').textContent")
    assert "<img" in await js("document.querySelector('#brain .brain-item .sender').textContent")
    assert await js("document.querySelectorAll('#brain img').length") == 0 and await js("document.title") != "pwned"
    stack["brain"].done("gmail:t1")
    assert await until(js, "document.querySelectorAll('#brain .brain-item').length === 0")


@CHROME
async def test_approve_sends_the_edited_text_once(home):
    js, stack = home
    brain, calls = stack["brain"], []
    real = brain.approve

    async def recording(item_id, text, version):
        calls.append((item_id, text, version))
        await real(item_id, text, version)

    brain.approve = recording
    show(brain, item(state="draft_ready", draft="Monday works for us.", draft_version=1))
    assert await until(js, "document.querySelector('#brain .draft-text')?.value === 'Monday works for us.'")
    await js("const box = document.querySelector('#brain .draft-text'); box.value = 'Monday works. Thanks!';"
             "box.dispatchEvent(new Event('input', {bubbles: true}));"
             "const approve = document.querySelector('#brain .approve'); approve.click(); approve.click(); true")
    await asyncio.sleep(1)
    assert calls == [("gmail:t1", "Monday works. Thanks!", 1)]


@CHROME
async def test_hand_and_run_take_one_click(home):
    js, stack = home
    brain, calls = stack["brain"], []

    async def hand(item_id, instruction):
        calls.append(("hand", item_id, instruction))

    async def run_workflow(item_id, slug):
        calls.append(("run", item_id, slug))
        return "a9"

    brain.hand, brain.run_workflow = hand, run_workflow
    show(brain, item(workflow="site-fix", workflow_name="Site fix"))
    assert await until(js, "document.querySelector('#brain .run')?.textContent === 'Run Site fix'")
    await js("const row = document.querySelector('#brain .brain-item');"
             "row.querySelector('.say').value = 'check the page';"
             "row.querySelector('.hand').click(); row.querySelector('.hand').click();"
             "row.querySelector('.run').click(); row.querySelector('.run').click(); true")
    await asyncio.sleep(1)
    # each once, double clicks ignored; their order is the server's (Hand runs as a job, Run inline), not the clicks'
    assert sorted(calls) == [("hand", "gmail:t1", "check the page"), ("run", "gmail:t1", "site-fix")]


@CHROME
async def test_tell_the_brain_shows_a_card_and_runs_only_on_start(home):
    from test_bridge import EVENTS

    js, stack = home
    brain, agents = stack["brain"], stack["server"].agents
    stack["script"].write_text(json.dumps({"default": EVENTS, "You map the user's answer": [
        {"result": json.dumps({"action": "agent"})}]}), encoding="utf-8")
    show(brain, item())
    row = "document.querySelector('#brain .brain-item')"
    assert await until(js, f"{row} !== null")
    words = f"ask an agent to check the launch page {HOSTILE}"
    await js(f"{row}.querySelector('.say').value = {json.dumps(words)}; {row}.querySelector('.tell').click(); true")
    assert await until(js, f"{row}.querySelector('.brain-card-task')?.value === {json.dumps(words)}")
    assert await js(f"{row}.querySelector('.brain-card-head').textContent") == "Start a NEW agent with your words:"
    assert await js("document.querySelectorAll('#brain img').length") == 0 and await js("document.title") != "pwned"
    await asyncio.sleep(0.5)
    assert agents.agents == {}  # nothing starts before Start
    await js(f"const go = {row}.querySelector('.brain-card-go'); go.click(); go.click(); true")
    for _ in range(50):
        if agents.agents:
            break
        await asyncio.sleep(0.1)
    await asyncio.sleep(1)
    assert list(agents.agents) == ["a1"]  # a second click does nothing
    for _ in range(50):
        if agents.events_of("a1"):
            break
        await asyncio.sleep(0.1)
    assert agents.events_of("a1")[0]["text"].startswith(words)  # the words, then the message as page data
    assert await until(js, f"{row}.querySelector('.agent').textContent.startsWith('Agent 1: ')")
    assert await until(js, f"{row}.querySelector('.brain-card').hidden === true")


