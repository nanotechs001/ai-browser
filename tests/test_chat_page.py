"""AI Browser's floating chat (/chat) in a throwaway headless Chrome against a real app server (the `stack` fixture),
opened as AI Browser's own app opens it: with the window's cookie, and window.aib, the app's bridge, played here by a
stand-in that records what the page asks it and answers what "Brave's front tab" is (never the user's Brave). Every
text is read with textContent."""

import asyncio
import json

import pytest

from ai_browser.chrome import chrome_binary
from fake_brave import FakeBrave
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
