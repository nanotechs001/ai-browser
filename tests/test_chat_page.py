"""AI Browser's floating chat (/chat) in a throwaway headless Chrome against a real app server (the `stack` fixture),
opened as AI Browser's own app opens it: with the window's cookie, and window.aib, the app's bridge, played here by a
stand-in that records what the page asks it and answers what "Brave's front tab" is (never the user's Brave). Every
text is read with textContent."""

import asyncio
import json

import pytest

from ai_browser.chrome import chrome_binary
from fake_brave import FakeBrave, add_agent
from fake_desktop import FakeDesktop
from test_home import HOSTILE, evaluate, stack, until  # noqa: F401  (stack is a fixture)
from test_talk import ask_typed, talk_calls, talk_script

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
CART = {"target": "U1", "url": "https://shop.example/cart", "title": "Cart"}
NEWS = {"target": "U2", "url": "https://news.example/", "title": "News"}
SEEN = {"state": "ok", "url": "https://shop.example/cart", "title": "Cart"}  # what the app read from Brave
BRIDGE = """
window.aibCalls = [];
window.aibAnswer = %s;
window.aib = Object.freeze({
  chat: async (what) => { window.aibCalls.push(["chat", what]); return null; },
  thisPage: async () => { window.aibCalls.push(["thisPage"]); return window.aibAnswer; },
});
"""


async def eventually(check, seconds=8.0):
    """True once `check()` is: polled in Python, for the app's side of things."""
    for _ in range(int(seconds * 20)):
        if check():
            return True
        await asyncio.sleep(0.05)
    return bool(check())


async def open_chat(stack, answer=SEEN, bridge=True, pages=(CART, NEWS), state="connected"):
    """(js in /chat, the FakeBrave behind it): Brave's listed tabs are `pages`, in `state`; the bridge's stand-in says
    Brave's front tab is `answer` (bridge=False: no bridge, as in a plain browser). The page is in front and shows."""
    brave = FakeBrave(pages, state=state)
    stack["server"].attach_brave(brave)
    cdp = stack["cdp"]
    target = (await cdp.send("Target.createTarget", {"url": "about:blank"}))["targetId"]
    session = (await cdp.send("Target.attachToTarget", {"targetId": target, "flatten": True}))["sessionId"]
    await cdp.send("Page.enable", session_id=session)
    if bridge:
        await cdp.send("Page.addScriptToEvaluateOnNewDocument", {"source": BRIDGE % json.dumps(answer)},
                       session_id=session)
    await cdp.send("Page.navigate", {"url": stack["url"] + "/chat"}, session_id=session)

    async def js(expression):
        return await evaluate(cdp, session, expression)

    js.cdp, js.session = cdp, session
    await cdp.send("Page.bringToFront", session_id=session)
    await cdp.send("Emulation.setFocusEmulationEnabled", {"enabled": True}, session_id=session)
    assert await until(js, "document.getElementById('status')?.dataset.state === 'connected'")
    return js, brave


def bar(part: str) -> str:
    return f"document.getElementById('page-{part}')"


async def look_again(js, answer):
    """Brave's front tab is now `answer`, and the user clicks ↻."""
    await js(f"window.aibAnswer = {json.dumps(answer)}; {bar('look')}.click(); true")


async def pick(js, target):
    await js(f"{bar('picker')}.value = {json.dumps(target)}; {bar('picker')}.dispatchEvent(new Event('change')); true")


@CHROME
async def test_this_page_is_the_tab_youre_on(stack):
    js, brave = await open_chat(stack)
    assert await until(js, f"{bar('title')}.textContent === 'Cart'")
    assert await js(f"{bar('host')}.textContent") == "shop.example"
    assert await js(f"{bar('ask')}.disabled") is False and await js(f"{bar('picker')}.hidden") is True
    await look_again(js, {"state": "ok", "url": "https://news.example/", "title": "News"})  # another tab, in Brave
    assert await until(js, f"{bar('title')}.textContent === 'News'")
    assert brave.connects == 0 and brave.read_pages == []  # looking reads no page, and asks Brave nothing


@CHROME
async def test_brave_not_running_or_not_connected_is_said_and_nothing_connects(stack):  # Review Focus 2
    desktop = FakeDesktop()
    stack["server"].attach_desktop(desktop)
    js, brave = await open_chat(stack, answer={"state": "closed"})
    assert await until(js, f"{bar('says')}.textContent === \"Brave isn't running.\"")
    assert await js(f"{bar('picker')}.hidden") is True and await js(f"{bar('title')}.textContent") == ""
    brave.set_state("ready")  # Brave runs, but isn't connected to AI Browser
    await look_again(js, SEEN)
    not_connected = "Brave isn't connected to AI Browser: connect it in AI Home."
    assert await until(js, f"{bar('says')}.textContent === {json.dumps(not_connected)}")
    await js(f"{bar('home')}.click(); true")  # Open AI Home: AI Browser's window comes forward, where Connect is
    assert await eventually(lambda: {"type": "show"} in desktop.sent)
    brave.set_state("asking")
    await look_again(js, SEEN)
    asking = "Brave is asking whether AI Browser may connect: answer it in Brave."
    assert await until(js, f"{bar('says')}.textContent === {json.dumps(asking)}")
    assert brave.connects == 0  # nothing in the chat connects: Brave asks nothing new


@CHROME
async def test_automation_refused_says_where_to_allow_it_and_offers_your_tabs(stack):  # Review Focus 3
    js, _ = await open_chat(stack, answer={"state": "denied"})
    assert await until(js, f"{bar('says')}.textContent.startsWith(\"macOS doesn't let AI Browser see\")")
    steps = await js(f"{bar('steps')}.textContent")
    assert "System Settings → Privacy & Security → Automation → AI Browser → turn on Brave Browser" in steps
    assert await js(f"{bar('picker')}.hidden") is False
    assert await js(f"[...{bar('picker')}.options].map((option) => option.textContent)") == [
        "Pick the tab you mean…", "Cart · shop.example", "News · news.example"]
    await pick(js, "U2")
    assert await until(js, f"{bar('title')}.textContent === 'News'")
    await js(f"{bar('look')}.click(); true")  # ↻ looks again: still not allowed, said again
    assert await until(js, f"{bar('steps')}.hidden === false && {bar('title')}.textContent === ''")


@CHROME
async def test_the_same_page_in_two_windows_is_yours_to_pick(stack):  # Review Focus 4
    from ai_browser.brain.talk import PAGE_TEXT_LIMIT

    twin = {"target": "U3", "url": CART["url"], "title": "Cart"}
    js, brave = await open_chat(stack, pages=(CART, twin, NEWS))
    choose = "Pick the tab you mean: AI Browser couldn't tell which one it is."
    assert await until(js, f"{bar('says')}.textContent === {json.dumps(choose)}")
    assert await js(f"{bar('title')}.textContent") == "" and await js(f"{bar('picker')}.hidden") is False
    await pick(js, "U3")
    assert await until(js, f"{bar('title')}.textContent === 'Cart'")
    talk_script(stack, {"say": "It's a cart.", "action": "none"})
    await js(f"{bar('ask')}.click(); true")
    await ask_typed(js, "what is in it?")
    assert await eventually(lambda: brave.read_pages == [("U3", PAGE_TEXT_LIMIT)])  # the tab the user picked


@CHROME
async def test_a_hostile_title_stays_one_line_of_plain_text(stack):  # Review Focus 5
    title = HOSTILE + "‮ evil \n" + "x" * 300
    hostile = {"target": "U1", "url": CART["url"], "title": title}
    js, _ = await open_chat(stack, answer={"state": "ok", "url": CART["url"], "title": title}, pages=(hostile,))
    assert await until(js, f"{bar('title')}.textContent.startsWith('<img')")
    shown = await js(f"{bar('title')}.textContent")
    assert len(shown) == 80 and shown.endswith("…") and "‮" not in shown and "\n" not in shown
    assert await js("document.querySelectorAll('#page img').length") == 0 and await js("document.title") != "pwned"


@CHROME
async def test_outside_ai_browsers_own_app_the_chat_asks_you_to_pick(stack):
    js, _ = await open_chat(stack, bridge=False)
    outside = "Pick the tab: only AI Browser's own app can see which one you're on."
    assert await until(js, f"{bar('says')}.textContent === {json.dumps(outside)}")
    assert await js(f"{bar('picker')}.hidden") is False


@CHROME
async def test_only_a_question_with_ask_about_it_reads_the_page(stack):
    from ai_browser.brain.talk import PAGE_TEXT_LIMIT

    js, brave = await open_chat(stack)
    brave.page_answers["U1"] = {"title": "Cart", "url": CART["url"], "text": "Open 9 to 5.", "cut": False}
    talk_script(stack, {"say": "It opens at 9.", "action": "none"})
    assert await until(js, f"{bar('title')}.textContent === 'Cart'")
    await ask_typed(js, "what is new?")  # Ask about it is off: no page is read
    assert await until(js, "document.getElementById('talk-log').textContent.includes('Brain: It opens at 9.')")
    assert brave.read_pages == []
    await js(f"{bar('ask')}.click(); true")
    assert await js(f"{bar('ask')}.getAttribute('aria-pressed')") == "true"
    assert await js("document.getElementById('talk-text').placeholder") == "Ask about shop.example"
    await ask_typed(js, "when does it open?")
    assert await eventually(lambda: brave.read_pages == [("U1", PAGE_TEXT_LIMIT)])
    assert await until(js, "document.querySelectorAll('#talk-log li.brain').length === 2")
    calls = talk_calls(stack)
    assert "Open 9 to 5." in calls[-1] and "Open 9 to 5." not in calls[0]


@CHROME
async def test_a_hidden_chat_looks_at_nothing_and_asks_about_no_page(stack):  # Plan decision 7
    js, _ = await open_chat(stack)
    assert await until(js, f"{bar('title')}.textContent === 'Cart'")
    await js(f"{bar('ask')}.click(); true")
    await js("Object.defineProperty(document, 'hidden', { value: true, configurable: true });"
             "Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });"
             "document.dispatchEvent(new Event('visibilitychange')); true")
    looked = "window.aibCalls.filter((call) => call[0] === 'thisPage').length"
    before = await js(looked)
    await js(f"{bar('look')}.click(); true")
    await asyncio.sleep(0.5)
    assert await js(looked) == before  # hidden: the app is never asked
    assert await js(f"{bar('ask')}.getAttribute('aria-pressed')") == "false"


@CHROME
async def test_escape_hides_the_chat_and_our_own_links_bring_ai_home_forward(stack):
    desktop = FakeDesktop()
    stack["server"].attach_desktop(desktop)
    js, _ = await open_chat(stack)
    await js("document.getElementById('talk-text').blur();"
             "document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); true")
    assert await until(js, "window.aibCalls.some((call) => call[0] === 'chat' && call[1] === 'hide')")
    await js("const link = document.createElement('a'); link.href = '/home'; link.textContent = 'AI Home';"
             "document.body.append(link); link.click(); true")
    assert await eventually(lambda: {"type": "show"} in desktop.sent)
    assert await js("location.pathname") == "/chat"  # the chat's window never leaves its page


def record_creates(stack):
    """AgentManager.create, recorded: each call's words, model, tab and account. Its agent has no process behind it."""
    agents, made = stack["server"].agents, []

    async def create(text, skills=(), model="sonnet", adopt=None, tab=None, servers=None, account=None):
        made.append({"text": text, "model": model, "adopt": adopt, "account": account})
        agent = add_agent(agents, f"a{len(made)}", text)
        if adopt:
            agent.adopted.append(adopt)
        agents._changed(agent)
        return agent

    agents.create = create
    return made


TWO_ACCOUNTS = [{"id": "default", "name": "Personal", "default": True, "signed_in": True, "checked": True},
                {"id": "work", "name": "Work", "default": False, "signed_in": True, "checked": True}]


@CHROME
async def test_new_task_starts_an_agent_with_the_model_and_account_picked(stack):  # New task replaces `ai`
    stack["server"]._account_rows = lambda: [dict(row) for row in TWO_ACCOUNTS]
    made = record_creates(stack)
    js, _ = await open_chat(stack)
    await js("document.getElementById('new-open').click(); true")
    assert await js("document.getElementById('new').hidden") is False
    assert await until(js, "!document.getElementById('task-account').hidden")  # two accounts: the picker shows
    await js("document.getElementById('task').value = 'find flights to Manila';"
             "document.getElementById('task-model').value = 'haiku';"
             "document.getElementById('task-account').value = 'work';"
             "document.getElementById('task-start').click(); true")
    assert await eventually(lambda: made == [{"text": "find flights to Manila", "model": "haiku", "adopt": None,
                                              "account": "work"}])
    assert await until(js, "document.getElementById('new').hidden"
                           " && document.getElementById('hint').textContent.startsWith('Started ')")
    assert await js("document.getElementById('task').value") == ""


@CHROME
async def test_start_it_in_this_page_hands_the_tab_over_with_the_start(stack):  # Plan decision 13
    made = record_creates(stack)
    js, brave = await open_chat(stack)
    assert await until(js, f"{bar('title')}.textContent === 'Cart'")
    await js("document.getElementById('new-open').click(); true")
    assert await until(js, "document.getElementById('task-here').disabled === false")
    await js("document.getElementById('task').value = 'compare prices';"
             "document.getElementById('task-here').click(); document.getElementById('task-start').click(); true")
    assert await eventually(lambda: made and made[0]["adopt"] == "U1")
    assert await eventually(lambda: brave.owners.get("U1", {}).get("kind") == "handed")


@CHROME
async def test_hand_over_gives_this_page_to_an_open_agent_on_the_click_only(stack):  # Plan decision 13
    agent = add_agent(stack["server"].agents, "a1", "Fix the footer")
    talk_script(stack, {"say": "Only you can hand a tab over: use Hand over.", "action": "none"})
    js, _ = await open_chat(stack)
    assert await until(js, f"{bar('title')}.textContent === 'Cart'")
    options = f"[...{bar('hand')}.options].map((option) => option.textContent).join('|')"
    assert await until(js, f"{options} === 'Hand over…|1 · Fix the footer'")
    await ask_typed(js, "hand this page to agent 1")  # words never hand a tab over
    assert await until(js, "document.querySelectorAll('#talk-log li.brain').length === 1")
    assert agent.adopted == []
    await js(f"{bar('hand')}.value = 'a1'; {bar('hand')}.dispatchEvent(new Event('change')); true")
    assert await eventually(lambda: agent.adopted == ["U1"])
    assert await until(js, f"{bar('host')}.textContent === 'shop.example · handed to 1 · Fix the footer'")
    assert await js(f"{bar('hand')}.disabled") is True  # handed: not the user's to hand over again


@CHROME
async def test_the_open_agents_show_by_number_and_a_click_opens_ai_home_there(stack):
    desktop = FakeDesktop()
    stack["server"].attach_desktop(desktop)
    add_agent(stack["server"].agents, "a1", "Fix the footer")
    add_agent(stack["server"].agents, "a2", "Check flights")
    told = []
    real = stack["server"]._send_all
    stack["server"]._send_all = lambda message: (told.append(message), real(message))[1]
    js, _ = await open_chat(stack)
    names = "[...document.querySelectorAll('#agents .agent-chip .agent-name')].map((one) => one.textContent)"
    assert await until(js, f"{names}.join('|') === '1 · Fix the footer|2 · Check flights'")
    await js("document.querySelector('#agents .agent-chip[data-id=\"a2\"]').click(); true")
    assert await eventually(lambda: {"type": "focus", "agent": "a2"} in told and {"type": "show"} in desktop.sent)


@CHROME
async def test_the_chat_shows_the_same_permission_card(stack, tmp_path):  # moved from test_ai_home_phase2
    from test_ai_home_phase2 import answered, ask_for_clickup

    js, _ = await open_chat(stack)
    ask_for_clickup(stack, tmp_path)
    await stack["server"].agents.create("make a ClickUp task")
    card = "document.querySelector('#needs-you .permission')"
    assert await until(js, f"{card} !== null")
    assert "1 · make a ClickUp task wants to use a tool" in await js(f"{card}.textContent")
    state = "document.querySelector('#agents .agent-chip .agent-state')?.textContent"
    assert await until(js, f"{state} === 'needs you'")
    await js(f"{card}.querySelector('.deny').click(); true")
    assert [answer["behavior"] for answer in await answered(stack["log"])] == ["deny"]


@CHROME
async def test_the_chat_shows_the_same_bot_check_card_for_the_users_own_tab(stack):  # moved from test_check_card
    from test_check_card import checked, heard, recorded

    js, _ = await open_chat(stack)
    seen = recorded(stack)
    agent = await checked(stack, target="U1", adopted=True)
    card = "document.querySelector('#needs-you .bot-check')"
    assert await until(js, f"{card} !== null")
    assert "It's in your own tab" in await js(f"{card}.textContent")
    assert await js(f"{card}.querySelector('.skip-site') === null")
    await js(f"{card}.querySelector('.show-me').click(); true")
    assert await heard(seen, ("watch", "U1"))
    await js(f"{card}.querySelector('.continue').click(); true")
    assert await heard(seen, ("check_continue", agent.id))


def test_the_readme_explains_the_floating_chat():
    from pathlib import Path

    text = " ".join((Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8").split())
    for needed in ("### The floating chat (⌥Space, beside Brave)",
                   "**Show chat** works even when another app holds the shortcut",
                   "Privacy & Security → Automation → AI Browser → turn on Brave Browser", "**Ask about it:**",
                   "It replaces typing `ai` in Brave's address bar", "**Hand over…**",
                   "the chat never connects by itself", "the Brain only answers, and proposes nothing",
                   "and for Brave, once more", "The old side panel is gone"):
        assert needed in text, needed
    assert "(the floating chat, coming next)" not in text


@CHROME
async def test_ask_about_it_goes_off_when_the_tab_goes_to_another_site(stack):  # final review: the mark is per site
    js, brave = await open_chat(stack)
    assert await until(js, f"{bar('title')}.textContent === 'Cart'")
    await js(f"{bar('ask')}.click(); true")
    assert await js("document.getElementById('talk-text').placeholder") == "Ask about shop.example"

    async def go(url, title):  # the user goes elsewhere in the same tab: the list and Brave's front tab agree
        await js(f"window.aibAnswer = {json.dumps({'state': 'ok', 'url': url, 'title': title})}; true")
        brave.pages[0].update(url=url, title=title)
        brave.changed()
        assert await until(js, f"{bar('title')}.textContent === {json.dumps(title)}")

    await go("https://shop.example/checkout", "Checkout")  # the same site: the mark holds
    assert await js(f"{bar('ask')}.getAttribute('aria-pressed')") == "true"
    await go("https://bank.example/", "Bank")  # another site: the user never marked it
    assert await js(f"{bar('ask')}.getAttribute('aria-pressed')") == "false"
    assert await js("document.getElementById('talk-text').placeholder") == "Ask the Brain"


@CHROME
async def test_start_it_in_this_page_never_hands_over_a_tab_the_user_didnt_mark(stack):  # fix pass 2, I1
    made = record_creates(stack)
    js, _ = await open_chat(stack)
    assert await until(js, f"{bar('title')}.textContent === 'Cart'")
    await js("document.getElementById('new-open').click(); true")
    assert await until(js, "document.getElementById('task-here').disabled === false")
    await js("document.getElementById('task-here').click(); true")  # ticked on Cart (U1)
    await look_again(js, {"state": "ok", "url": NEWS["url"], "title": "News"})  # then the user went to News (U2)
    assert await until(js, f"{bar('title')}.textContent === 'News'")
    assert await js("document.getElementById('task-here').checked") is False  # the mark was for Cart
    await js("document.getElementById('task').value = 'compare prices';"
             "document.getElementById('task-start').click(); true")
    assert await eventually(lambda: len(made) == 1)
    assert made[0]["adopt"] is None  # nothing is handed over that the user didn't tick


@CHROME
async def test_a_private_window_is_never_matched_and_offers_your_tabs(stack):  # fix pass 2, I2
    js, brave = await open_chat(stack, answer={"state": "private"})
    private = "That's a private window: AI Browser doesn't read those. Pick the tab you mean."
    assert await until(js, f"{bar('says')}.textContent === {json.dumps(private)}")
    assert await js(f"{bar('picker')}.hidden") is False and await js(f"{bar('title')}.textContent") == ""
    assert brave.read_pages == []


@CHROME
async def test_a_question_never_reads_another_site_the_tab_went_to_meanwhile(stack):  # fix pass 2, I3: the race
    from ai_browser.app.server import CHAT_PAGE_CHANGED

    js, brave = await open_chat(stack)
    talk_script(stack, {"say": "It's a bank.", "action": "none"})
    assert await until(js, f"{bar('title')}.textContent === 'Cart'")
    await js(f"{bar('ask')}.click(); true")  # the mark: shop.example
    # the tab goes to the bank, and the question leaves before the tab list says so: the read finds the bank
    brave.page_answers["U1"] = {"title": "Bank", "url": "https://bank.example/", "text": "BANK-WORDS", "cut": False}
    await ask_typed(js, "what is on it?")
    assert await eventually(lambda: len(brave.read_pages) == 1)
    assert await until(js, f"document.getElementById('talk').textContent.includes({json.dumps(CHAT_PAGE_CHANGED)})")
    assert not any("BANK-WORDS" in call for call in talk_calls(stack))  # nothing of the bank reached Claude


@CHROME
async def test_a_window_without_an_address_bar_offers_your_tabs(stack):  # fix pass 2, I5 (Windows)
    js, _ = await open_chat(stack, answer={"state": "unknown"})
    unknown = "AI Browser can't see this window's address: pick the tab you mean."
    assert await until(js, f"{bar('says')}.textContent === {json.dumps(unknown)}")
    assert await js(f"{bar('picker')}.hidden") is False
