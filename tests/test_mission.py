"""Mission Control: the agents at their stations in a 3D room and the Brain that talks back, against a real app server
(agents on the fake claude) in a throwaway headless AI Browser. Names, summaries and updates stay text."""

import asyncio
import itertools
import json
import math

import pytest

from ai_browser.chrome import chrome_binary
from test_bridge import EVENTS
from test_home import HOSTILE, evaluate, home, open_page, stack, until  # noqa: F401  (fixtures)

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
WORKING = [EVENTS[0], {"sleep": 30}]  # an agent that stays at work
JPEG = "/9j/4AAQSkZJRg=="


async def open_mission(stack):
    _, js = await open_page(stack["cdp"], stack["url"] + "/mission")
    assert await until(js, "document.getElementById('status').dataset.state === 'connected'")
    return js


@pytest.fixture
async def mission(stack):
    """(js in Mission Control, stack)."""
    return await open_mission(stack), stack


def station(agent_id, part=""):
    return f"document.querySelector('.station[data-id=\"{agent_id}\"] {part}'.trim())"


def key(name):
    return f"document.dispatchEvent(new KeyboardEvent('keydown', {{key: {json.dumps(name)}, bubbles: true}})); true"


def open_drawer(agent_id):
    """A desk picked, then its Chat: its drawer. A click alone picks it for the right column (plan decision 11)."""
    return f"{station(agent_id)}.click(); document.getElementById('current-chat').click(); true"


@CHROME
async def test_every_agent_has_a_station_and_names_stay_text(mission):
    js, stack = mission
    agents = stack["server"].agents
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    for name in ("Fix the footer", HOSTILE, "Check my-site.com"):
        await agents.create(name)
    assert await until(js, "document.querySelectorAll('.station').length === 3")
    assert "<img" in await js(f"{station('a2', '.nameplate')}.textContent")
    assert await js("[...document.images].filter(img => !img.closest('.monitor')).length") == 0
    assert await js("document.title") != "pwned"
    await js(f"{station('a1')}.marker = 7; true")
    await agents.stop("a1")
    assert await until(js, f"{station('a1')}.dataset.state === 'stopped'")
    assert await js(f"{station('a1')}.marker") == 7  # the same element: updated in place, a click is never lost
    await agents.close("a1")
    assert await until(js, "document.querySelectorAll('.station').length === 2")


@CHROME
async def test_monitors_show_thumbnails_and_late_pages_get_them(mission):
    js, stack = mission
    server = stack["server"]
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await server.agents.create("Fix the footer")
    assert await until(js, "document.querySelectorAll('.station').length === 1")
    server._thumbs["a1"] = {"last": 0.0, "task": None, "again": False, "jpeg": JPEG}
    server._send_all({"type": "thumb", "id": "a1", "jpeg": JPEG})
    shown = f"{station('a1', '.monitor img')}?.src === 'data:image/jpeg;base64,{JPEG}'"
    assert await until(js, shown)
    later = await open_mission(stack)  # opened after the picture was taken
    assert await until(later, shown)


@CHROME
async def test_the_camera_turns_and_zooms_within_limits(mission):
    js, _ = mission
    room = "document.querySelector('.room').dataset"
    assert [await js(f"{room}.{name}") for name in ("tilt", "spin", "scale")] == ["58", "0", "1"]
    for _ in range(10):
        await js(key("ArrowUp"))
    await js(key("ArrowLeft"))
    for _ in range(10):
        await js(key("+"))
    assert [await js(f"{room}.{name}") for name in ("tilt", "spin", "scale")] == ["70", "15", "1.6"]
    for _ in range(20):
        await js(key("ArrowDown"))
        await js(key("-"))
    assert [await js(f"{room}.{name}") for name in ("tilt", "scale")] == ["35", "0.6"]
    await js(key("0"))
    assert [await js(f"{room}.{name}") for name in ("tilt", "spin", "scale")] == ["58", "0", "1"]
    assert "rotateX(58deg)" in await js("document.querySelector('.room').style.transform")


@CHROME
async def test_many_agents_fill_the_rings_without_overlap(mission):
    js, stack = mission
    for number in range(15):  # the spec's scene with 15 agents
        await stack["server"].agents.create(f"Task number {number}")  # each is done at once: 12 stay in the room
    shown = "document.querySelectorAll('.station:not(.away)')"
    assert await until(js, f"document.querySelectorAll('.station').length === 15 && {shown}.length === 12", 20)
    points = await js(f"[...{shown}].map(s => [Number(s.dataset.x), Number(s.dataset.y)])")
    closest = min(math.dist(one, two) for one, two in itertools.combinations(points, 2))
    assert closest >= 160, points


@CHROME
async def test_a_waiting_permission_is_answered_from_mission_control(stack, tmp_path):
    from test_ai_home_phase2 import answered, ask_for_clickup

    ask_for_clickup(stack, tmp_path)
    agents = stack["server"].agents
    await agents.create("make a ClickUp task")
    for _ in range(50):
        if agents.agents["a1"].permission:
            break
        await asyncio.sleep(0.1)
    js = await open_mission(stack)  # opened while the request already waits
    assert await until(js, f"{station('a1')}?.dataset.state === 'needs_you'")
    assert "needs you" in await js("document.getElementById('counts').textContent")
    assert await js(f"{station('a1', '.ticker')}.textContent") == "wants clickup: create task"
    await js(f"{station('a1')}.click(); true")
    card = "document.querySelector('#drawer:not([hidden]) .permission')"
    assert await until(js, f"{card} !== null")
    assert "create_task" in await js(f"{card}.textContent")
    await js(f"{card}.querySelector('.allow-once').click(); true")
    assert [answer["behavior"] for answer in await answered(stack["log"])] == ["allow"]
    assert await until(js, f"{station('a1')}.dataset.state !== 'needs_you'")


@CHROME
async def test_the_drawer_shows_the_chat_and_closes_an_agent(mission):
    js, stack = mission
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await stack["server"].agents.create(f"Fix the footer {HOSTILE}")
    assert await until(js, f"{station('a1')} !== null")
    await js(open_drawer("a1"))
    chat = "document.querySelector('#drawer:not([hidden]) .messages')"
    assert await until(js, f"{chat}?.textContent.includes('Fix the footer')")
    assert "<img" in await js("document.getElementById('drawer-title').textContent")
    assert await js("[...document.images].filter(img => !img.closest('.monitor')).length") == 0
    await js(key("Escape"))
    assert await js("document.getElementById('drawer').hidden")
    await js(open_drawer("a1"))
    await js("document.querySelector('#drawer .close').click(); true")
    confirm = "document.querySelector('dialog.confirm')"  # it still works: Close asks first (Task 17)
    assert await until(js, f"{confirm}?.open === true")
    await js(f"{confirm}.querySelector('.go').click(); true")
    assert await until(js, "document.querySelectorAll('.station').length === 0")
    assert await until(js, "document.getElementById('drawer').hidden")


@CHROME
async def test_the_task_bar_starts_one_agent(mission):
    js, stack = mission
    await js("document.getElementById('task').value = 'check the shop'; document.getElementById('task-model').value"
             " = 'haiku'; document.getElementById('start').click(); document.getElementById('start').click(); true")
    assert await until(js, "document.querySelectorAll('.station').length === 1")
    await asyncio.sleep(1)
    assert len(stack["server"].agents.agents) == 1  # a double click makes one agent
    assert stack["server"].agents.agents["a1"].model == "haiku"
    assert await js("document.getElementById('task').value") == ""


def needs_reply(brain, raw_id="t1", sender="Maria", summary="Maria asks to move the launch", snippet=""):
    from ai_browser.brain.store import Item

    entry = Item(id=f"gmail:{raw_id}", site="gmail", raw_id=raw_id, sender=sender, subject="Launch", summary=summary,
                 snippet=snippet, kind="needs_reply", url=f"https://mail.google.com/mail/u/0/#all/{raw_id}")
    brain.store.put(entry)
    brain.broadcast({"type": "brain_item", "item": entry.public()})
    return entry


def changed(brain, entry, **fields):
    for key, value in fields.items():
        setattr(entry, key, value)
    brain.store.put(entry)
    brain.broadcast({"type": "brain_item", "item": entry.public()})


@CHROME
async def test_the_globe_follows_the_brain(mission):
    js, stack = mission
    brain = stack["brain"]
    stage = "document.querySelector('.stage')"
    assert await until(js, f"{stage}.dataset.state === 'idle'")
    brain.broadcast({"type": "brain_activity", "busy": True, "what": "Sorting 2 new messages from Gmail"})
    assert await until(js, f"{stage}.dataset.state === 'thinking'")
    assert await js("document.getElementById('brain-what').textContent") == "Sorting 2 new messages from Gmail"
    needs_reply(brain, summary=f"Maria asks {HOSTILE}")
    brain.broadcast({"type": "brain_activity", "busy": False, "what": ""})
    assert await until(js, f"{stage}.dataset.state === 'alert'")
    assert await js("document.getElementById('brain-count').textContent") == "1 needs you"
    await js("document.getElementById('brain').click(); true")  # the Brain's inbox, in the drawer
    item = "document.querySelector('#drawer:not([hidden]) .brain-item .summary')"
    assert await until(js, f"{item} !== null")
    assert "<img" in await js(f"{item}.textContent") and await js("document.title") != "pwned"
    brain.done("gmail:t1")
    assert await until(js, f"{stage}.dataset.state === 'idle'")


BUBBLES = ("window.seen = []; const bubble = document.getElementById('bubble');"  # every update shown, in order
           "new MutationObserver((records) => { for (const record of records) if (record.addedNodes.length"
           " && !bubble.hidden) window.seen.push(bubble.textContent); }).observe(bubble, {childList: true}); true")
NO_LOCAL_VOICE = "speechSynthesis.getVoices = () => [{name: 'Cloud', lang: 'en-US', localService: false}];"
LOCAL_VOICE = ("window.spoken = []; window.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };"
               "speechSynthesis.getVoices = () => [{name: 'Cloud', lang: 'en-US', localService: false},"
               " {name: 'Samantha', lang: 'en-US', localService: true}];"
               "speechSynthesis.speak = (said) => { window.spoken.push([said.text, said.voice && said.voice.name]);"
               " setTimeout(() => said.onend && said.onend(), 30); };"
               "speechSynthesis.cancel = () => {};")


async def open_with(stack, source="", size=None):
    """Mission Control in a tab where `source` ran before the page's own scripts (the browser changed from outside),
    in a window of `size` (width, height) if given. js.session is the page's DevTools session."""
    cdp = stack["cdp"]
    target = (await cdp.send("Target.createTarget", {"url": "about:blank"}))["targetId"]
    session = (await cdp.send("Target.attachToTarget", {"targetId": target, "flatten": True}))["sessionId"]
    await cdp.send("Page.enable", session_id=session)
    if size:
        await cdp.send("Emulation.setDeviceMetricsOverride", {"width": size[0], "height": size[1],
                                                              "deviceScaleFactor": 1, "mobile": False},
                       session_id=session)
    if source:
        await cdp.send("Page.addScriptToEvaluateOnNewDocument", {"source": source}, session_id=session)
    await cdp.send("Page.navigate", {"url": stack["url"] + "/mission"},
                   session_id=session)

    async def js(expression):
        return await evaluate(cdp, session, expression)

    js.session = session
    assert await until(js, "document.getElementById('status')?.dataset.state === 'connected'")
    return js


@CHROME
async def test_updates_are_written_in_order(mission):
    js, stack = mission
    await js(BUBBLES)
    needs_reply(stack["brain"], sender="Maria Santos", summary="she asks to move the launch")
    await asyncio.sleep(0.3)
    await stack["server"].agents.create("Fix the footer")  # the fake claude finishes at once
    assert await until(js, "window.seen.length >= 2", 15)
    assert (await js("window.seen"))[:2] == ["Maria Santos needs your reply: she asks to move the launch",
                                             "Fix the footer is done"]


@CHROME
async def test_a_burst_becomes_a_summary(mission):
    js, stack = mission
    await js(BUBBLES)
    for number in range(8):
        needs_reply(stack["brain"], raw_id=f"t{number}", sender=f"Client {number}", summary="asks for a quote")
    assert await until(js, "window.seen.length >= 2", 15)
    assert (await js("window.seen"))[:2] == ["Client 0 needs your reply: asks for a quote",
                                             "7 more updates: open the Brain"]


@CHROME
async def test_old_news_is_not_told_and_hostile_text_stays_text(stack):
    needs_reply(stack["brain"], raw_id="old", sender="Old news", summary="from before the page opened")
    js = await open_mission(stack)
    await js(BUBBLES)
    await asyncio.sleep(1.5)
    assert await js("window.seen") == [] and await js("document.getElementById('bubble').hidden")
    needs_reply(stack["brain"], raw_id="t9", sender=HOSTILE, summary=HOSTILE)
    assert await until(js, "window.seen.length === 1")
    assert "<img" in (await js("window.seen"))[0]
    assert await js("[...document.images].filter(img => !img.closest('.monitor')).length") == 0
    assert await js("document.title") != "pwned"


@CHROME
async def test_voice_is_off_by_default_and_needs_a_voice_on_this_computer(stack):
    js = await open_with(stack, NO_LOCAL_VOICE)
    assert await js("document.getElementById('voice').checked") is False
    await js("document.getElementById('voice').click(); true")
    assert await until(js, "document.getElementById('voice-note').textContent === 'No voice on this computer'")
    assert await js("document.getElementById('voice').checked") is False
    spoken = await open_with(stack, LOCAL_VOICE)
    assert await spoken("document.getElementById('voice').checked") is False
    await spoken("document.getElementById('voice').click(); true")
    assert await until(spoken, "document.getElementById('voice').checked === true")
    needs_reply(stack["brain"], sender="Maria Santos", summary="she asks to move the launch")
    assert await until(spoken, "window.spoken.length === 1")
    assert await spoken("window.spoken[0]") == ["Maria Santos needs your reply: she asks to move the launch",
                                                "Samantha"]  # only a voice that runs on this computer
    await spoken("location.reload(); true")
    await asyncio.sleep(0.5)
    assert await until(spoken, "document.getElementById('status')?.dataset.state === 'connected'"
                               " && document.getElementById('voice').checked === true")  # remembered



# ---- the final review's findings ------------------------------------------------------------------------------------

def overlapping(rects):
    return [(one, two) for one, two in itertools.combinations(rects, 2)
            if min(one[2], two[2]) - max(one[0], two[0]) > 4 and min(one[3], two[3]) - max(one[1], two[1]) > 4]


ARTS = ("[...document.querySelectorAll('.station:not(.leaving):not(.away) .desk-art')].map(art => {"
        " const r = art.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; })")
BRAIN_SHAPE = "(() => { const r = document.getElementById('brain').getBoundingClientRect(); return r.height / r.width; })()"


@CHROME
async def test_the_room_keeps_its_shapes_at_any_zoom(stack):
    js = await open_with(stack, size=(1024, 700))
    for number in range(14):
        await stack["server"].agents.create(f"Task number {number}")
    assert await until(js, "document.querySelectorAll('.station').length === 14")
    await asyncio.sleep(1)
    for keys in ([], ["+", "+", "+"], ["-"] * 9):
        for name in keys:
            await js(key(name))
        await asyncio.sleep(0.4)
        assert 0.95 <= await js(BRAIN_SHAPE) <= 1.05, keys  # the Brain stays round, cards keep their shape


@CHROME
async def test_twenty_agents_dont_cover_each_other_on_screen(stack):
    js = await open_with(stack, size=(1280, 760))
    for number in range(20):
        await stack["server"].agents.create(f"Task number {number}")
    assert await until(js, "document.querySelectorAll('.station:not(.away)').length === 12", 20)  # done: 12 stay
    await asyncio.sleep(1.5)
    desks = await js(ARTS)
    assert len(desks) == 12 and overlapping(desks) == []
    assert all(desk[0] >= 0 and desk[2] <= 1280 and desk[1] >= 0 and desk[3] <= 760 for desk in desks), desks


@CHROME
async def test_a_failed_fill_is_not_told_as_ready(stack):
    entry = needs_reply(stack["brain"], sender="Maria", summary="asks to move the launch")  # before the page opened
    js = await open_mission(stack)
    await js(BUBBLES)
    brain = stack["brain"]
    changed(brain, entry, state="draft_ready", draft="Monday works.", draft_version=1)
    assert await until(js, "window.seen.length === 1")
    changed(brain, entry, state="filling")
    changed(brain, entry, state="draft_ready", note="Couldn't fill the reply box: no reply box")
    await asyncio.sleep(6.5)
    assert await js("window.seen") == ["Your reply to Maria is ready to check"]  # once: the failure isn't news


@CHROME
async def test_an_open_room_does_no_layout_while_agents_work(mission):
    js, stack = mission
    cdp = stack["cdp"]
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    for name in ("one", "two", "three"):
        await stack["server"].agents.create(name)
    assert await until(js, "document.querySelectorAll('.station[data-state=\"working\"]').length === 3")
    targets = (await cdp.send("Target.getTargets"))["targetInfos"]
    page = next(t for t in targets if t["type"] == "page" and t["url"].endswith("/mission"))
    session = (await cdp.send("Target.attachToTarget", {"targetId": page["targetId"], "flatten": True}))["sessionId"]
    await cdp.send("Page.bringToFront", session_id=session)  # a hidden tab runs no animations
    await cdp.send("Performance.enable", session_id=session)
    assert await until(js, "document.visibilityState === 'visible'")

    async def layouts():
        metrics = (await cdp.send("Performance.getMetrics", session_id=session))["metrics"]
        return next(metric["value"] for metric in metrics if metric["name"] == "LayoutCount")

    await asyncio.sleep(1.5)
    before = await layouts()
    await asyncio.sleep(2)
    assert await layouts() - before < 10  # the page stays open all day: its animations don't lay the page out


@CHROME
async def test_stations_open_in_their_places(stack):
    for number in range(6):
        await stack["server"].agents.create(f"Task number {number}")
    js = await open_mission(stack)
    assert await until(js, "document.querySelectorAll('.station').length === 6")
    sliding = ("document.getAnimations().filter(animation => ['left', 'top'].includes(animation.transitionProperty))"
               ".length")
    assert await js(sliding) == 0


@CHROME
async def test_turning_past_half_a_turn_keeps_going(mission):
    js, _ = mission
    for _ in range(13):
        await js(key("ArrowLeft"))
    assert await js("document.querySelector('.room').dataset.spin") == "195"
    assert "rotateZ(195deg)" in await js("document.querySelector('.room').style.transform")
    assert await js("document.querySelector('.room').getAnimations().length") == 0  # stations always face the user


@CHROME
async def test_updates_never_read_out_a_message(mission):
    js, stack = mission
    await js(BUBBLES)
    text = "Hi, here is everything about the launch, the budget and the passwords for the staging site"
    needs_reply(stack["brain"], raw_id="t1", sender="Maria", summary=text, snippet=text)  # no summary: the text itself
    needs_reply(stack["brain"], raw_id="t2", sender="Ben", summary="asks about the launch " + "and more " * 40)
    assert await until(js, "window.seen.length >= 2", 12)
    first, second = (await js("window.seen"))[:2]
    assert first == "Maria needs your reply"
    assert second.startswith("Ben needs your reply: asks about the launch") and len(second) <= 141
    assert second.endswith("…")


@CHROME
async def test_a_picture_for_an_unknown_agent_is_dropped(mission):
    js, stack = mission
    server = stack["server"]
    server._send_all({"type": "thumb", "id": "a1", "jpeg": JPEG})  # a closed agent's late picture
    await asyncio.sleep(0.5)
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await server.agents.create("Fix the footer")  # gets the id a1
    assert await until(js, f"{station('a1')} !== null")
    await asyncio.sleep(0.5)
    assert await js(f"{station('a1', '.monitor img')}.hidden") is True


@CHROME
async def test_a_trackpad_zooms_gently(mission):
    js, _ = mission
    for _ in range(10):  # one light two-finger scroll on a Mac trackpad
        await js("document.querySelector('.viewport').dispatchEvent(new WheelEvent('wheel', "
                 "{deltaY: 4, bubbles: true, cancelable: true})); true")
    assert 0.9 <= float(await js("document.querySelector('.room').dataset.scale")) < 1


SLOW_VOICE = ("window.spoken = []; let current = null;"
              "window.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };"
              "speechSynthesis.getVoices = () => [{name: 'Samantha', lang: 'en-US', localService: true}];"
              "speechSynthesis.speak = (said) => { window.spoken.push(['speak', said.text]); current = said;"
              " setTimeout(() => { if (current === said) { current = null; said.onend && said.onend(); } }, 2000); };"
              "speechSynthesis.cancel = () => { window.spoken.push(['cancel']); const was = current; current = null;"
              " if (was && was.onerror) was.onerror({error: 'interrupted'}); };")
STUCK_VOICE = ("window.spoken = [];"
               "window.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };"
               "speechSynthesis.getVoices = () => [{name: 'Samantha', lang: 'en-US', localService: true}];"
               "speechSynthesis.speak = (said) => { window.spoken.push(['speak', said.text]); };"
               "speechSynthesis.cancel = () => { window.spoken.push(['cancel']); };")
BLOCKED_VOICE = ("window.spoken = [];"
                 "window.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };"
                 "speechSynthesis.getVoices = () => [{name: 'Samantha', lang: 'en-US', localService: true}];"
                 "speechSynthesis.speak = (said) => { if (!navigator.userActivation.hasBeenActive) {"
                 " setTimeout(() => said.onerror && said.onerror({error: 'not-allowed'}), 10); return; }"
                 " window.spoken.push(['speak', said.text]); setTimeout(() => said.onend && said.onend(), 30); };"
                 "speechSynthesis.cancel = () => {};")


async def voice_on(js):
    await js("document.getElementById('voice').click(); true")
    assert await until(js, "document.getElementById('voice').checked === true")


@CHROME
async def test_a_burst_stops_the_voice(stack):
    js = await open_with(stack, SLOW_VOICE)
    await voice_on(js)
    for number in range(8):
        needs_reply(stack["brain"], raw_id=f"t{number}", sender=f"Client {number}", summary="asks for a quote")
    assert await until(js, "window.spoken.length >= 3", 10)
    assert (await js("window.spoken"))[:3] == [["speak", "Client 0 needs your reply: asks for a quote"], ["cancel"],
                                                ["speak", "7 more updates: open the Brain"]]


@CHROME
async def test_a_voice_that_never_ends_is_stopped(stack):
    js = await open_with(stack, STUCK_VOICE)
    await voice_on(js)
    needs_reply(stack["brain"], raw_id="t1", sender="Maria", summary="asks to move the launch")
    await asyncio.sleep(0.3)
    needs_reply(stack["brain"], raw_id="t2", sender="Ben", summary="asks about staging")
    assert await until(js, "window.spoken.length >= 3", 16)
    assert (await js("window.spoken"))[:3] == [["speak", "Maria needs your reply: asks to move the launch"],
                                                ["cancel"], ["speak", "Ben needs your reply: asks about staging"]]


@CHROME
async def test_voice_waits_for_a_click_when_chrome_asks_for_one(stack):
    js = await open_with(stack, BLOCKED_VOICE)
    await voice_on(js)  # a scripted click: not a user's, so Chrome won't let the page speak yet
    needs_reply(stack["brain"], raw_id="t1", sender="Maria", summary="asks to move the launch")
    assert await until(js, "document.getElementById('voice-note').textContent.includes('Click')")
    assert await js("document.getElementById('bubble').textContent") == "Maria needs your reply: asks to move the launch"
    for kind in ("mousePressed", "mouseReleased"):  # the user clicks the page
        await stack["cdp"].send("Input.dispatchMouseEvent", {"type": kind, "x": 40, "y": 300, "button": "left",
                                                             "clickCount": 1}, session_id=js.session)
    assert await until(js, "document.getElementById('voice-note').textContent === ''")
    await asyncio.sleep(5.5)  # the bubble moves on
    needs_reply(stack["brain"], raw_id="t2", sender="Ben", summary="asks about staging")
    assert await until(js, "window.spoken.length === 1", 8)
    assert await js("window.spoken[0]") == ["speak", "Ben needs your reply: asks about staging"]


@CHROME
async def test_watch_says_it_brings_the_agents_tab_to_the_front(mission):
    js, stack = mission
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await stack["server"].agents.create("Fix the footer")
    assert await until(js, f"{station('a1')} !== null")
    await js(open_drawer("a1"))
    assert await until(js, "document.querySelector('#drawer .watch')?.title === "
                           "\"Bring this agent's tab to the front\"")


@CHROME
async def test_the_model_is_the_apps_choice_in_every_window(home):
    from ai_browser.settings import read_settings

    js, stack = home
    mission = await open_mission(stack)
    assert await mission("document.getElementById('task-model').value") == "sonnet"  # ai-browser app --model
    await js("const picker = document.getElementById('task-model'); picker.value = 'opus';"
             "picker.dispatchEvent(new Event('change')); true")
    assert await until(mission, "document.getElementById('task-model').value === 'opus'")  # no reload needed
    assert read_settings(stack["home"])["model"] == "opus"
    await js("location.reload(); true")
    await asyncio.sleep(0.5)
    assert await until(js, "document.getElementById('status')?.dataset.state === 'connected' && "
                           "document.getElementById('task-model').value === 'opus'")


@CHROME
async def test_voice_comes_back_on_from_the_apps_settings(stack):
    from ai_browser.settings import read_settings

    js = await open_with(stack, LOCAL_VOICE)
    await voice_on(js)
    for _ in range(50):
        if read_settings(stack["home"]).get("voice") is True:
            break
        await asyncio.sleep(0.1)
    assert read_settings(stack["home"])["voice"] is True
    later = await open_with(stack, LOCAL_VOICE)  # Mission Control opened again: Voice is on at load
    assert await until(later, "document.getElementById('voice').checked === true")
