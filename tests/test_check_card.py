"""A bot check in AI Browser: the card on AI Home's row, in the chat panel and in Mission Control, with Show me,
Continue and Skip this site. Names, sites and words stay text; the buttons send only our own fixed messages."""

import asyncio
import json

import pytest

from ai_browser.chrome import chrome_binary
from test_home import HOSTILE, home, post_tab, stack, until  # noqa: F401  (fixtures)
from test_mission import WORKING, open_mission, station
from test_panel import panel  # noqa: F401  (fixture)

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
REPORT = {"kind": "check", "check": "google", "site": "www.google.com", "target": "T1", "adopted": False}
LIVE = "http://127.0.0.1:8770/live?token=abc"


async def checked(stack, name="Flights to Manila", **report):
    """An agent at work whose engine reported a bot check (what /agent-events delivers)."""
    agents = stack["server"].agents
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    agent = await agents.create(name)
    report = {**REPORT, **report}
    agents.tab_event(agent.id, "tab_opened", report["target"], report["adopted"])
    agents.check_event(agent.id, report)
    return agent


def recorded(stack) -> list[tuple[str, str]]:
    """What the cards' buttons asked the app for (watch, check_continue, check_skip), recorded instead of done."""
    server, seen = stack["server"], []

    async def watch(target):
        seen.append(("watch", target))

    async def continue_check(agent_id):
        seen.append(("check_continue", agent_id))

    async def skip_check(agent_id):
        seen.append(("check_skip", agent_id))

    server.tabs.watch = watch
    server.agents.continue_check = continue_check
    server.agents.skip_check = skip_check
    return seen


async def heard(seen, expected, seconds=5) -> bool:
    for _ in range(int(seconds * 10)):
        if expected in seen:
            return True
        await asyncio.sleep(0.1)
    return False


def row_card(agent) -> str:
    return f"document.querySelector('.agent[data-id=\"{agent.id}\"] .bot-check')"


@CHROME
async def test_ai_home_shows_the_card_and_its_buttons(home):
    js, stack = home
    seen = recorded(stack)
    agent = await checked(stack)
    agent.check = {**agent.check, "what": HOSTILE, "since": agent.check["since"] + 1}  # markup stays text
    stack["server"].agents._changed(agent)
    card = row_card(agent)
    assert await until(js, f"{card} !== null && {card}.textContent.includes('<img')")
    text = await js(f"{card}.textContent")
    assert "Flights to Manila stopped at a bot check" in text and "www.google.com · " in text
    assert "Solve it in the tab yourself, then click Continue. The agent never touches it." in text
    assert await js(f"{card}.querySelectorAll('img').length") == 0 and await js("document.title") != "pwned"
    row = f"document.querySelector('.agent[data-id=\"{agent.id}\"]')"
    assert await js(f"{row}.querySelector('.chip').textContent") == "needs you"
    assert await js(f"{row}.querySelector('.stop').hidden") is False
    await js(f"{card}.querySelector('.show-me').click(); true")
    assert await heard(seen, ("watch", "T1"))
    await js(f"{card}.querySelector('.continue').click(); true")
    assert await heard(seen, ("check_continue", agent.id))


@CHROME
async def test_skip_is_offered_only_for_the_agents_own_tab(home):
    js, stack = home
    seen = recorded(stack)
    own = await checked(stack, "Own tab")
    users = await checked(stack, "Your tab", target="U1", adopted=True)
    sandboxed = await checked(stack, "QA sandbox", target="Q1", live=LIVE)
    for agent in (own, users, sandboxed):
        assert await until(js, f"{row_card(agent)} !== null")
    assert "It's in your own tab" in await js(f"{row_card(users)}.textContent")
    for agent in (users, sandboxed):
        assert "To skip it, tell the agent: skip it" in await js(f"{row_card(agent)}.textContent")
        assert await js(f"{row_card(agent)}.querySelector('.skip-site') === null")
    await js("window.opened = []; window.open = (url) => { window.opened.push(url); return null; }; true")
    await js(f"{row_card(sandboxed)}.querySelector('.show-me').click(); true")
    assert await js("window.opened") == [LIVE] and ("watch", "Q1") not in seen
    await js(f"{row_card(own)}.querySelector('.skip-site').click(); true")
    assert await heard(seen, ("check_skip", own.id))


@pytest.mark.skip(reason="AI Browser's side panel retired in wave B; the side-chat plan (wave D) moves this test")
@CHROME
async def test_the_panel_shows_the_same_card_for_the_users_own_tab(panel):
    js, user_tab, stack = panel
    seen = recorded(stack)
    agent = await checked(stack, target=user_tab, adopted=True)
    await post_tab(stack, agent.id, "working_tab", user_tab)
    card = "document.querySelector('#check-slot .bot-check')"
    assert await until(js, f"{card} !== null")
    assert "It's in your own tab" in await js(f"{card}.textContent")
    assert await js(f"{card}.querySelector('.skip-site') === null")
    await js(f"{card}.querySelector('.continue').click(); true")
    assert await heard(seen, ("check_continue", agent.id))


@CHROME
async def test_mission_control_shows_a_bot_check_as_needs_you(stack):
    js = await open_mission(stack)
    seen = recorded(stack)
    agent = await checked(stack)
    assert await until(js, f"{station(agent.id)}?.dataset.state === 'needs_you'")
    assert await js(f"{station(agent.id, '.ticker')}.textContent") == "bot check · www.google.com"
    assert await until(js, "document.getElementById('bubble').textContent.includes("
                           "'Flights to Manila hit a bot check on www.google.com. It\\'s waiting for you')")
    assert "needs you" in await js("document.getElementById('counts').textContent")
    await js(f"{station(agent.id)}.click(); true")
    card = "document.querySelector('#drawer:not([hidden]) .bot-check')"
    assert await until(js, f"{card} !== null")
    assert await js("document.querySelector('#drawer .stop').hidden") is False
    await js(f"{card}.querySelector('.continue').click(); true")
    assert await heard(seen, ("check_continue", agent.id))
