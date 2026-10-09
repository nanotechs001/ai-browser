"""Mission Control's new look: the layout at three widths, the left menu and its pages, the Flow · List · Calendar
switch and the right column (Task 12); the composer (Task 13); My Missions and History (Task 14); Templates, Knowledge
and Integrations (Task 15); workspaces and the Usage card (Task 16); the Calendar (Task 17); and the README (Task
18). Against a real app server (agents on the fake claude) in a throwaway headless Chrome. Every word stays text."""

import asyncio
import json

import pytest

from ai_browser.chrome import chrome_binary
from test_app_server import wait_for
from test_bridge import EVENTS
from test_bridge_powers import INIT, PLAN, use
from test_home import stack, until  # noqa: F401  (fixtures)
from test_mission import WORKING, open_mission, open_with, station
from test_office import front, planned

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
WIDE, MIDDLE, NARROW = (1440, 900), (1100, 800), (760, 900)
BOX = "((node) => { const r = node.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; })"
CHECKLIST = ("[...document.querySelectorAll('#checklist li')].map(li => [li.className,"
             " li.querySelector('.clip')?.textContent])")


def page_link(name):
    return f"document.querySelector('.page-link[data-page={json.dumps(name)}]')"


@CHROME
async def test_the_layout_at_three_widths(stack):
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await stack["server"].agents.create("Fix the footer")
    for size in (WIDE, MIDDLE, NARROW):
        js = await open_with(stack, size=size)
        assert await until(js, f"{station('a1')} !== null"), size
        menu, centre, side = [await js(f"{BOX}(document.getElementById({json.dumps(name)}))")
                              for name in ("menu", "centre", "side")]
        assert menu[2] <= centre[0] + 1, size  # the menu on the left
        if size == WIDE:
            assert centre[2] <= side[0] + 1 and abs(side[1] - centre[1]) < 2  # three columns
        else:
            assert side[1] >= centre[3] - 1, size  # the right column folds under the centre
        label = "getComputedStyle(document.querySelector('.page-link .label')).display"
        if size == NARROW:
            assert menu[2] - menu[0] <= 72 and await js(label) == "none"  # the menu shrinks to icons
        else:
            assert await js(label) != "none", size
        assert await js("document.documentElement.scrollWidth <= innerWidth"
                        " && document.querySelector('.mc').scrollWidth <= document.querySelector('.mc').clientWidth"), \
            size  # nothing scrolls sideways
        # no visible heading (the user's hand check): the page keeps an accessible title, visually hidden
        assert await js("document.querySelector('#page-dashboard :is(.heading, .eyebrow, .lede)') === null"), size
        assert await js("document.querySelectorAll('#page-dashboard :is(h1, h2)').length") == 1, size
        title = "document.querySelector('#page-dashboard > h2')"
        assert await js(f"{title}.textContent") == "Mission Control"
        box = await js(f"{BOX}({title})")
        assert box[2] - box[0] <= 1 and box[3] - box[1] <= 1, (size, box)


@CHROME
async def test_the_icon_only_menu_still_names_each_button(stack):  # the final review, F10
    js = await open_with(stack, size=NARROW)
    assert await until(js, "document.getElementById('status').dataset.state === 'connected'")
    assert await js("getComputedStyle(document.querySelector('.page-link .label')).display") == "none"  # icons only
    cdp, session = stack["cdp"], js.session
    root = (await cdp.send("DOM.getDocument", {"depth": 0}, session_id=session))["root"]["nodeId"]
    buttons = (await cdp.send("DOM.querySelectorAll", {"nodeId": root, "selector": "#new-mission, .page-link"},
                              session_id=session))["nodeIds"]
    names = []
    for node in buttons:  # what a screen reader says: the accessibility tree's name
        tree = await cdp.send("Accessibility.getPartialAXTree", {"nodeId": node, "fetchRelatives": False},
                              session_id=session)
        names.append(tree["nodes"][0].get("name", {}).get("value", ""))
    assert names == ["New Mission", "Dashboard", "My Missions", "Agents", "Knowledge", "Integrations", "Tabs",
                     "History"]
    assert await js("[...document.querySelectorAll('#new-mission, .page-link')].map(node => node.title)") == names


@CHROME
async def test_the_menu_counts_and_opens_its_pages(stack):
    agents = stack["server"].agents
    js = await open_mission(stack)
    assert await js("document.getElementById('counts').textContent") == "No agents yet"
    await agents.create("Fix the footer")  # the stack's script: done at once
    await wait_for(lambda: agents.agents["a1"].state == "your_turn")
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await agents.create("keep working")
    assert await until(js, "document.getElementById('counts').textContent === '1 active task · 1 completed'")
    for name in ("missions", "agents", "knowledge", "integrations", "tabs", "history", "dashboard"):
        await js(f"{page_link(name)}.click(); true")
        shown = await js("[...document.querySelectorAll('.centre > .page')].filter(node => !node.hidden)"
                         ".map(node => node.id)")
        assert shown == [f"page-{name}"], name
        assert await js(f"{page_link(name)}.getAttribute('aria-current')") == "page"
        assert await js("document.getElementById('composer').hidden") is (name not in ("dashboard", "missions"))
    await js(f"{page_link('history')}.click(); document.getElementById('new-mission').click(); true")
    assert await js("!document.getElementById('page-dashboard').hidden && document.activeElement.id === 'task'")


@CHROME
async def test_the_switch_shows_flow_list_or_calendar_and_the_list_names_the_rooms_agents(stack):
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    for name in ("first", "second", "third"):
        await stack["server"].agents.create(name)
    js = await open_mission(stack)
    rows = "[...document.querySelectorAll('#view-list .mission')].map(row => row.dataset.id)"
    assert await until(js, f"{rows}.length === 3")
    assert await js(rows) == ["a1", "a2", "a3"]  # oldest first, as the desks stand
    for name in ("list", "calendar", "flow"):
        tab = f"document.querySelector('#views-switch [data-view={json.dumps(name)}]')"
        await js(f"{tab}.click(); true")
        assert await js("['flow', 'list', 'calendar'].filter(one => !document.getElementById('view-' + one).hidden)") \
            == [name]
        assert await js(f"{tab}.getAttribute('aria-selected')") == "true"
    await js("document.querySelector('#views-switch [data-view=\"list\"]').click();"
             "document.querySelector('#view-list .mission[data-id=\"a2\"] .open').click(); true")
    assert await until(js, f"{station('a2')}.classList.contains('selected')")
    assert await js("document.querySelector('#view-list .mission[data-id=\"a2\"] .label').textContent") == "2 · second"


@CHROME
async def test_the_right_column_follows_the_agent_picked(stack):
    stack["script"].write_text(json.dumps([INIT, use("t1", "TodoWrite", PLAN),
                                           use("u1", "Bash", {"command": "npm test"}), {"sleep": 30}]),
                               encoding="utf-8")
    await stack["server"].agents.create("fix the footer")
    js = await open_mission(stack)
    assert await until(js, "document.getElementById('current-step').textContent === '2. Fixing the bug'")
    assert await js("document.getElementById('progress-text').textContent") == "1 / 3 steps complete"
    assert await js("document.getElementById('progress-percent').textContent") == "33%"
    assert await js("document.getElementById('progress-bar').style.width") == "33%"
    assert await js(CHECKLIST) == [["done", "Read the code"], ["current", "Fixing the bug"],
                                   ["pending", "Run the tests"]]
    assert await js("document.querySelector('#current-badge .badge-text').textContent") == "Bash"
    assert await js("document.getElementById('running-label').textContent") == "Running…"
    groups = ("[...document.querySelectorAll('#groups .group')].map(group => [group.dataset.group,"
              " group.querySelector('.count').textContent])")
    assert await js(groups) == [["completed", "0"], ["working", "1"], ["pending", "0"]]
    assert await js("document.querySelector('#groups .working .avatar svg.avatar-art') !== null")
    assert await js("document.querySelector('#current-avatar svg.avatar-art') !== null")


@CHROME
async def test_in_the_folded_layout_the_wheel_scrolls_the_page_and_ctrl_zooms(stack):  # the final review, F11
    cdp = stack["cdp"]
    for size, scrolls in ((MIDDLE, True), (WIDE, False)):
        js = await open_with(stack, size=size)
        assert await until(js, "document.getElementById('status').dataset.state === 'connected'")
        left, top, right, bottom = await js(f"{BOX}(document.querySelector('.viewport'))")
        x, y = (left + right) / 2, top + (min(bottom, size[1]) - top) * 0.4
        assert await js(f"document.elementFromPoint({x}, {y}).closest('.viewport') !== null")  # over the room
        scale = "document.querySelector('.room').dataset.scale"
        before = await js(scale)

        async def wheel(modifiers=0):
            await cdp.send("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": x, "y": y, "deltaX": 0,
                                                        "deltaY": 240, "modifiers": modifiers}, session_id=js.session)
            await asyncio.sleep(0.3)

        await wheel()  # a plain wheel
        scrolled = await js("document.querySelector('.mc').scrollTop")
        if scrolls:  # 1100 px: the right column is under the room, and the wheel reaches it
            assert scrolled > 0 and await js(scale) == before, size
            await wheel(modifiers=2)  # with Ctrl (a trackpad's pinch too): it zooms, and the page stays
            assert await js(scale) != before and await js("document.querySelector('.mc').scrollTop") == scrolled
        else:  # 1440 px: nothing to scroll, the wheel zooms as before
            assert scrolled == 0 and await js(scale) != before, size


@CHROME
async def test_an_agent_without_a_to_do_list_shows_its_actions(stack):
    from test_bridge_powers import result

    stack["script"].write_text(json.dumps([INIT, use("u1", "Bash", {"command": "ls"}), result("u1"),
                                           use("u2", "Bash", {"command": "npm test"}), {"sleep": 30}]),
                               encoding="utf-8")
    await stack["server"].agents.create("look around")
    js = await open_mission(stack)
    want = json.dumps([["done", "Bash ls"], ["current", "Bash npm test"]], separators=(",", ":"))  # as JS has it
    assert await until(js, f"JSON.stringify({CHECKLIST}) === {json.dumps(want)}")
    assert await js("document.getElementById('progress-percent').textContent") == ""  # no percentage
    assert await js("document.getElementById('progress-bar').parentElement.hidden") is True
    assert await js("document.getElementById('progress-text').textContent") == "Working"


@CHROME
async def test_a_long_answer_never_pushes_the_actions_off_the_checklist(stack):  # the final review, F1
    from test_bridge_powers import result

    piece = {"type": "stream_event", "event": {"type": "content_block_delta",
                                               "delta": {"type": "text_delta", "text": "word "}}}
    stack["script"].write_text(json.dumps([INIT, use("u1", "Bash", {"command": "ls"}), result("u1"),
                                           use("u2", "Bash", {"command": "npm test"}), result("u2"),
                                           *[piece] * 250, {"sleep": 30}]), encoding="utf-8")
    agents = stack["server"].agents
    js = await open_mission(stack)  # open first: the pieces arrive one by one
    await agents.create("look around")
    await wait_for(lambda: sum(event["type"] == "delta" for event in agents.events_of("a1")) == 250)
    want = json.dumps([["done", "Bash ls"], ["done", "Bash npm test"]], separators=(",", ":"))
    assert await until(js, f"JSON.stringify({CHECKLIST}) === {json.dumps(want)}"), await js(CHECKLIST)
    later = await open_mission(stack)  # opened after the answer: its whole conversation at once
    assert await until(later, f"JSON.stringify({CHECKLIST}) === {json.dumps(want)}"), await later(CHECKLIST)


@CHROME
async def test_recent_activity_lists_starts_steps_and_ends(stack):
    first = {"todos": [{"content": "Read the code", "status": "in_progress", "activeForm": "Reading the code"}]}
    second = {"todos": [{"content": "Read the code", "status": "completed", "activeForm": "Reading the code"}]}
    stack["script"].write_text(json.dumps([INIT, use("t1", "TodoWrite", first), {"sleep": 0.3},
                                           use("t2", "TodoWrite", second), *EVENTS[1:]]), encoding="utf-8")
    await stack["server"].agents.create("fix the footer")
    js = await open_mission(stack)
    titles = "[...document.querySelectorAll('#activity-list .activity-row strong')].map(node => node.textContent)"
    assert await until(js, f"{titles}.includes('Mission complete')")
    assert await js(titles) == ["Mission complete", "Step done", "Mission started"]
    assert await js("[...document.querySelectorAll('#activity-list .line')].map(node => node.textContent)") == [
        "Opening", "Read the code", "1 · fix the footer"]
    assert await js("[...document.querySelectorAll('#activity-list .when')].every(node =>"
                    " node.textContent === 'just now')")
    await js("document.getElementById('see-all').click(); true")
    assert await js("document.getElementById('page-history').hidden") is False


@CHROME
async def test_long_words_clip_in_the_right_column(stack):  # Review Focus 1
    step = "Read every page of the site and " + "check each link " * 20
    todos = {"todos": [{"content": step, "status": "in_progress", "activeForm": step}]}
    stack["script"].write_text(json.dumps([INIT, use("t1", "TodoWrite", todos),
                                           use("u1", "Bash", {"command": "echo " + "x" * 2000}), {"sleep": 30}]),
                               encoding="utf-8")
    await stack["server"].agents.create("a" * 2000)
    js = await open_with(stack, size=WIDE)
    assert await until(js, "document.getElementById('current-step').textContent.startsWith('1. Read every page')")
    for selector in ("#current-step", "#current-line", "#checklist .current .clip"):
        node = f"document.querySelector({json.dumps(selector)})"
        assert await js(f"{node}.scrollWidth > {node}.clientWidth && {node}.title === {node}.textContent"), selector
    assert await js("(() => { const side = document.getElementById('side');"
                    " return side.scrollWidth <= side.clientWidth; })()")


@CHROME
async def test_a_click_picks_a_desk_and_a_waiting_card_opens_its_drawer(stack, tmp_path):
    from test_tools import ask_for_clickup

    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await stack["server"].agents.create("keep working")
    js = await open_mission(stack)
    assert await until(js, f"{station('a1')} !== null")
    await js(f"{station('a1')}.click(); true")
    assert await until(js, "document.getElementById('current-step').textContent === '1 · keep working'")
    assert await js("document.getElementById('drawer').hidden") is True  # a click picks; the drawer stays shut
    ask_for_clickup(stack, tmp_path)
    await stack["server"].agents.create("make a ClickUp task")
    await wait_for(lambda: stack["server"].agents.agents["a2"].permission is not None)
    assert await until(js, f"{station('a2')}?.dataset.state === 'needs_you'")
    await js(f"{station('a2')}.click(); true")
    assert await until(js, "document.querySelector('#drawer:not([hidden]) .permission') !== null")
    assert await js("document.getElementById('current-answer').hidden") is False
    assert await js("document.getElementById('current-needs').textContent") == "wants clickup: create task"


@CHROME
async def test_stop_chat_and_hand_over(stack):
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await stack["server"].agents.create("keep working")
    js = await open_mission(stack)
    assert await until(js, "document.getElementById('current-step').textContent === '1 · keep working'")
    await js("document.getElementById('current-chat').click(); true")
    assert await until(js, "document.querySelector('#drawer:not([hidden]) .messages')?.textContent"
                           ".includes('keep working')")
    assert await js("document.querySelector('#drawer .your-tabs').open") is False
    await js("document.getElementById('drawer-close').click(); document.getElementById('current-hand').click(); true")
    assert await until(js, "document.querySelector('#drawer:not([hidden]) .your-tabs')?.open === true")
    await js("document.getElementById('current-stop').click(); true")
    assert await until(js, f"{station('a1')}.dataset.state === 'stopped'")
    assert await until(js, "document.getElementById('current-stop').hidden")


@CHROME
async def test_watch_beside_hand_over_brings_the_agents_tab_to_the_front(stack):  # the user's look, 2026-10-07
    from test_check_card import heard, recorded

    seen = recorded(stack)  # what the app was asked to do, instead of doing it
    agents = stack["server"].agents
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await agents.create("keep working")
    js = await open_mission(stack)
    assert await until(js, "document.getElementById('current-step').textContent === '1 · keep working'")
    watch = "document.getElementById('current-watch')"
    assert await js(f"{watch}.previousElementSibling.id") == "current-hand"  # to the right of Hand over
    assert await js(f"[{watch}.textContent, {watch}.title, {watch}.querySelectorAll('svg.icon').length]") == [
        "Watch", "Bring this agent's tab to the front", 1]
    assert await js(f"{watch}.disabled") is True  # no tab of its own yet
    agents.tab_event("a1", "working_tab", "T1")
    assert await until(js, f"!{watch}.disabled")
    await js(f"{watch}.click(); true")
    assert await heard(seen, ("watch", "T1"))  # the drawer's Watch: its tab to the front
    assert await js("document.getElementById('drawer').hidden") is True  # without opening the drawer
    agents.tab_event("a1", "tab_closed", "T1")
    assert await until(js, f"{watch}.disabled")
    await js(f"{watch}.click(); true")
    await asyncio.sleep(0.5)
    assert seen.count(("watch", "T1")) == 1  # nothing to bring forward: nothing sent


@CHROME
@pytest.mark.parametrize("size", [WIDE, (1280, 760)])
async def test_watch_stays_right_of_hand_over_with_stop_shown_or_hidden(stack, size):  # the review of look-3, F2
    agents = stack["server"].agents
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await agents.create("keep working")
    agents.tab_event("a1", "working_tab", "T1")
    js = await open_with(stack, size=size)
    assert await until(js, "!document.getElementById('current-watch').disabled")
    pair = f"[{BOX}(document.getElementById('current-hand')), {BOX}(document.getElementById('current-watch'))]"
    for stop_shown in (True, False):
        assert await until(js, f"document.getElementById('current-stop').hidden === {str(not stop_shown).lower()}")
        hand, watch = await js(pair)
        assert watch[0] >= hand[2] and abs(watch[1] - hand[1]) < 2, (size, stop_shown, hand, watch)  # one row
        await agents.stop("a1")  # a finished agent that still has its tab: Stop goes, Watch stays


@CHROME
@pytest.mark.parametrize("size", [WIDE, (1280, 760), MIDDLE, NARROW])
async def test_the_list_and_the_calendar_start_right_under_the_switch(stack, size):
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await stack["server"].agents.create("first")
    js = await open_with(stack, size=size)
    assert await until(js, "document.querySelectorAll('#view-list .mission').length === 1")
    for name in ("list", "calendar"):
        await js(f"document.querySelector('#views-switch [data-view={json.dumps(name)}]').click(); true")
        first, words = await js("(() => { const view = document.getElementById('view-" + name + "');"
                                " const row = view.querySelector('.mission');"
                                " const bottom = (one) => document.querySelector(one).getBoundingClientRect().bottom;"
                                " return [row ? row.getBoundingClientRect().top : view.getBoundingClientRect().top"
                                " + parseFloat(getComputedStyle(view).paddingTop),"
                                " bottom('.switch-views')]; })()")
        # its first row (or its content's top) is below the switch, and right under it: no room kept for a heading
        assert words <= first <= words + 24, (name, first, words)


@CHROME
@pytest.mark.parametrize("size", [MIDDLE, NARROW])
async def test_the_folded_right_column_shows_all_its_panels_under_the_centre(stack, size):
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await stack["server"].agents.create("keep working")
    js = await open_with(stack, size=size)
    assert await until(js, "document.getElementById('current-step').textContent === '1 · keep working'")
    assert await js("(() => { const side = document.getElementById('side');"
                    " return side.scrollHeight <= side.clientHeight + 1 && side.clientHeight > 300; })()")  # whole
    await js("document.querySelector('.mc').scrollTop = 99999; true")  # the page scrolls to its last panel
    assert await js("document.getElementById('activity').getBoundingClientRect().bottom") <= size[1] + 1


CARDS_UNDER_WORDS = """(() => {
  const box = (node) => node.getBoundingClientRect();
  const over = (one, two) => Math.min(one.right, two.right) > Math.max(one.left, two.left)
    && Math.min(one.bottom, two.bottom) > Math.max(one.top, two.top);
  const words = ['.switch-views'].map((selector) => [selector, box(document.querySelector(selector))]);
  const scene = box(document.querySelector('.scene'));
  const inside = (r) => r.left >= scene.left - 1 && r.right <= scene.right + 1 && r.top >= scene.top - 1
    && r.bottom <= scene.bottom + 1;
  const nodes = [...document.querySelectorAll('.station:not(.away):not(.leaving)')];
  const hits = [];
  const outside = [];
  for (const node of nodes) {
    const step = box(node.querySelector('.step'));
    for (const [selector, rect] of words) if (over(step, rect)) hits.push([node.dataset.id, selector]);
    if (!inside(step) || !inside(box(node.querySelector('.desk-art')))) outside.push(node.dataset.id);
  }
  return [nodes.length, hits, outside];
})()"""


@CHROME
@pytest.mark.parametrize("size", [WIDE, (1280, 760), MIDDLE, NARROW])  # three columns (widest, narrowest), two, one
@pytest.mark.parametrize("count", [5, 6, 12, 20])
async def test_no_step_card_sits_under_the_switch(stack, count, size):  # Task 11's far desks; only the switch is left
    stack["script"].write_text(json.dumps(planned()), encoding="utf-8")
    stack["server"].agents.max_working = count  # all of them at work at once, none waiting in line
    for number in range(count):
        await stack["server"].agents.create(f"Task number {number}")
    js = await open_with(stack, size=size)
    await front(stack, js)
    working = "document.querySelectorAll('.station[data-state=\"working\"]:not(.away)').length"
    assert await until(js, f"{working} === {count}", 15)
    await asyncio.sleep(1.5)  # every desk in its place
    shown, hits, outside = await js(CARDS_UNDER_WORDS)
    assert shown == count
    assert hits == [], hits  # no desk's step card under the Flow · List · Calendar switch
    assert outside == [], outside  # and every desk, with its card, in view in the room's box


@CHROME
# with the heading and the sign gone the room grows into the box's top, where only the switch's band is kept clear,
# up to the width it has: measured 0.5545 at 1280x760 (0.4545 under the heading) and 0.6609 at 1440x900 (0.6409)
@pytest.mark.parametrize(("count", "size", "least"), [(5, (1280, 760), 0.54), (6, (1280, 760), 0.54), (5, WIDE, 0.65)])
async def test_a_few_desks_fill_the_room_below_the_switch_and_stay_in_view(stack, count, size, least):
    stack["script"].write_text(json.dumps(planned()), encoding="utf-8")
    stack["server"].agents.max_working = count
    for number in range(count):
        await stack["server"].agents.create(f"Task number {number}")
    js = await open_with(stack, size=size)
    await front(stack, js)
    working = "document.querySelectorAll('.station[data-state=\"working\"]:not(.away)').length"
    assert await until(js, f"{working} === {count}", 15)
    await asyncio.sleep(1.5)  # every desk in its place
    zoom = await js("parseFloat(/scale3d\\(([\\d.]+)/.exec(document.querySelector('.room').style.transform)[1])")
    assert zoom >= least, zoom  # the room is placed between the switch's band and the box's bottom, not squeezed
    shown, hits, outside = await js(CARDS_UNDER_WORDS)
    assert (shown, hits, outside) == (count, [], [])


# ---- the composer (Task 13) ------------------------------------------------------------------------------------------

ATTACH = ("(files) => { const transfer = new DataTransfer();"
          " for (const [name, size] of files) transfer.items.add(new File([new Uint8Array(size).fill(65)], name));"
          " const input = document.getElementById('attach-files'); input.files = transfer.files;"
          " input.dispatchEvent(new Event('change')); return true; }")
KEY = ("(key, command, shift) => { const mac = /mac/i.test(navigator.userAgentData?.platform || navigator.platform);"
       " (document.activeElement || document.body).dispatchEvent(new KeyboardEvent('keydown', {key,"
       " metaKey: command && mac, ctrlKey: command && !mac, shiftKey: shift, bubbles: true, cancelable: true}));"
       " return true; }")
CHIPS = "[...document.querySelectorAll('#attached .attached-file')]"


@CHROME
async def test_build_a_mission_starts_an_agent_with_its_pickers(stack):
    research = stack["server"].workspaces.create("Research")
    js = await open_mission(stack)
    models = "[...document.querySelectorAll('#task-model option')].map(option => option.textContent)"
    assert await js(models) == ["Opus · most capable", "Sonnet · balanced", "Haiku · fastest"]
    webs = "[...document.querySelectorAll('#task-web option')].map(option => [option.value, option.textContent])"
    assert await js(webs) == [["web", "Web + Brave"], ["brave", "Brave only"], ["none", "No web"]]
    assert await until(js, "[...document.getElementById('task-workspace').options].some(option =>"
                           f" option.value === {json.dumps(research['id'])})")
    assert await js("document.getElementById('start-label').textContent") == "Start Mission"
    await js("document.getElementById('task').value = 'check the shop';"
             "document.getElementById('task-model').value = 'haiku';"
             "document.getElementById('task-web').value = 'none';"
             f"document.getElementById('task-workspace').value = {json.dumps(research['id'])};"
             "document.getElementById('start').click(); document.getElementById('start').click(); true")
    agents = stack["server"].agents
    await wait_for(lambda: "a1" in agents.agents)
    await asyncio.sleep(0.5)
    agent = agents.agents["a1"]
    assert len(agents.agents) == 1  # a double press makes one agent
    assert (agent.model, agent.web, agent.workspace) == ("haiku", "none", research["id"])
    assert await until(js, "document.getElementById('task').value === ''")


@CHROME
async def test_ask_ai_asks_the_brain_and_shows_its_answer(stack):
    from test_talk import talk_script

    talk_script(stack, {"say": "Two agents are at work.", "action": "none"})
    js = await open_mission(stack)
    await js("document.getElementById('mode-ask').click(); true")
    assert await js("document.getElementById('start-label').textContent") == "Ask"
    hidden = "['task-web', 'task-model', 'task-folder', 'attach'].every(id => document.getElementById(id).hidden)"
    assert await js(hidden)
    await js("document.getElementById('task').value = 'what are my agents doing?';"
             "document.getElementById('start').click(); true")
    log = "[...document.querySelectorAll('#talk-log li')].map(line => line.textContent)"
    assert await until(js, f"{log}.includes('Brain: Two agents are at work.')", 15)
    assert await js(f"{log}.includes('You: what are my agents doing?')")
    assert stack["server"].agents.agents == {}  # Ask AI starts nothing by itself
    assert await js("document.getElementById('task').value") == ""
    assert await js("document.getElementById('talk-form').hidden") is True  # the composer is the talk's box


@CHROME
async def test_attach_sends_files_into_the_agents_folder(stack):
    from test_app_server import told

    js = await open_mission(stack)
    await js(f"({ATTACH})([['../shot.png', 2000], ['notes.txt', 900000]])")  # notes.txt goes in two pieces
    assert await until(js, f"{CHIPS}.length === 2 && {CHIPS}.every(chip => chip.dataset.state === 'done')", 15)
    assert await js(f"{CHIPS}.map(chip => chip.querySelector('.name').textContent)") == ["shot.png", "notes.txt"]
    await js("document.getElementById('task').value = 'look at these'; document.getElementById('start').click(); true")
    folder = stack["home"] / "app" / "agents" / "a1" / "work" / "attachments"
    await wait_for(lambda: folder.is_dir() and len(list(folder.iterdir())) == 2)
    assert (folder / "notes.txt").stat().st_size == 900000
    await wait_for(lambda: bool(told(stack["log"])))
    assert "- attachments/shot.png (a picture: look at it with Read)" in told(stack["log"])[0]
    assert await until(js, f"{CHIPS}.length === 0")


@CHROME
async def test_attach_refuses_too_many_or_too_big_files(stack):  # Review Focus 5
    js = await open_mission(stack)
    await js(f"({ATTACH})([['big.mov', 20000001]])")
    assert await until(js, "document.getElementById('task-note').textContent === 'big.mov is over 20 MB'")
    await js(f"({ATTACH})({json.dumps([[f'f{number}.txt', 10] for number in range(11)])})")
    assert await until(js, "document.getElementById('task-note').textContent === 'At most 10 files at once'")
    assert await js(f"{CHIPS}.length") == 10
    assert await until(js, f"{CHIPS}.every(chip => chip.dataset.state === 'done')", 10)
    await js("document.querySelector('#attached .attached-file .drop').click(); true")
    assert await js(f"{CHIPS}.length") == 9
    uploads = stack["home"] / "app" / "uploads"
    await wait_for(lambda: len(list(uploads.glob("*.part"))) == 9)  # the app dropped it too


@CHROME
async def test_the_keys_jump_to_the_box_and_start(stack):
    js = await open_mission(stack)
    await js(f"{page_link('history')}.click(); document.getElementById('mode-ask').click(); true")
    await js(f"({KEY})('k', true, false)")  # ⌘K (Ctrl+K)
    assert await js("!document.getElementById('page-dashboard').hidden && document.activeElement.id === 'task'")
    assert await js("document.getElementById('mode-build').getAttribute('aria-selected')") == "true"
    await js("document.getElementById('task').value = 'first line'; true")
    await js(f"({KEY})('Enter', false, true)")  # Shift+Enter: a new line, nothing starts
    await asyncio.sleep(0.5)
    assert stack["server"].agents.agents == {}
    await js(f"({KEY})('Enter', true, false)")  # ⌘↵ (Ctrl+Enter)
    await wait_for(lambda: "a1" in stack["server"].agents.agents)
    assert await js("document.getElementById('start-key').textContent") in ("⌘ ↵", "Ctrl ↵")


@CHROME
async def test_narrow_windows_fold_the_pickers_into_options(stack):
    wide = await open_with(stack, size=WIDE)
    assert await wide("getComputedStyle(document.getElementById('pickers')).display") != "none"
    assert await wide("getComputedStyle(document.getElementById('options')).display") == "none"
    narrow = await open_with(stack, size=NARROW)
    assert await narrow("getComputedStyle(document.getElementById('pickers')).display") == "none"
    await narrow("document.getElementById('options').click(); true")
    assert await narrow("getComputedStyle(document.getElementById('pickers')).display") != "none"
    assert await narrow("document.getElementById('options').getAttribute('aria-expanded')") == "true"


@CHROME
async def test_the_options_open_above_the_whole_composer_not_over_its_modes(stack):
    js = await open_with(stack, size=NARROW)
    await js("document.getElementById('options').click(); true")
    pickers = await js(f"{BOX}(document.getElementById('pickers'))")
    modes = await js(f"{BOX}(document.querySelector('.modes'))")
    assert pickers[3] <= modes[1], (pickers, modes)  # the pickers end where the modes' row begins: its tabs stay in view
    assert pickers[1] >= 0 and pickers[0] >= 0 and pickers[2] <= NARROW[0]  # and the panel is inside the window


DONE = f"{CHIPS}.length > 0 && {CHIPS}.every(chip => chip.dataset.state === 'done')"
HOLD = ("(() => { const send = WebSocket.prototype.send; const held = [];"  # a new_task waits until window.release()
        " WebSocket.prototype.send = function (data) {"
        "   if (!window.released && typeof data === 'string' && data.includes('\"new_task\"')) {"
        "     held.push([this, data]); return; }"
        "   return send.call(this, data); };"
        " window.release = () => { window.released = true; for (const [socket, data] of held.splice(0))"
        " send.call(socket, data); }; })();")


@CHROME
async def test_a_file_attached_while_a_start_waits_stays_for_the_next_one(stack):  # review of Task 13, F1
    js = await open_with(stack, HOLD)
    await js(f"({ATTACH})([['first.txt', 100]])")
    assert await until(js, DONE, 15)
    await js("document.getElementById('task').value = 'one'; document.getElementById('start').click(); true")
    await js(f"({ATTACH})([['second.txt', 100]])")  # the app hasn't heard the Start yet
    assert await until(js, f"{CHIPS}.length === 2 && {CHIPS}.every(chip => chip.dataset.state === 'done')", 15)
    await js("window.release(); true")
    agents = stack["server"].agents
    await wait_for(lambda: "a1" in agents.agents)
    names = f"{CHIPS}.map(chip => chip.querySelector('.name').textContent)"
    assert await until(js, f"{names}.join() === 'second.txt'")  # only the file that went with the Start left
    assert await until(js, "!document.getElementById('start').disabled")
    await js("document.getElementById('task').value = 'two'; document.getElementById('start').click(); true")
    work = stack["home"] / "app" / "agents"
    await wait_for(lambda: (work / "a2" / "work" / "attachments" / "second.txt").is_file())
    assert (work / "a1" / "work" / "attachments" / "first.txt").is_file()


@CHROME
async def test_after_a_reconnect_the_attached_files_must_be_attached_again(stack):  # review of Task 13, F2
    js = await open_mission(stack)
    await js(f"({ATTACH})([['a.txt', 100], ['b.txt', 100]])")
    assert await until(js, f"{CHIPS}.length === 2 && {CHIPS}.every(chip => chip.dataset.state === 'done')", 15)
    server = stack["server"]
    for socket in list(server._sockets):  # the line drops: the app forgets every staged file
        await socket.close()
    assert await until(js, f"{CHIPS}.every(chip => chip.dataset.state === 'failed')", 15)  # the page said so, on its
    words = f"{CHIPS}.map(chip => chip.querySelector('.progress').textContent)"           # new connection's snapshot
    assert await js(words) == ["Not sent: attach it again"] * 2
    await js("document.getElementById('task').value = 'go'; document.getElementById('start').click(); true")
    assert await until(js, "document.getElementById('task-note').textContent.startsWith('Remove the files that didn')")
    await asyncio.sleep(0.5)
    assert server.agents.agents == {}  # nothing was sent: Start waited for the user to attach them again


# ---- pictures pasted into any chat (the user's look, 2026-10-07) -----------------------------------------------------

# ⌘V (Ctrl+V) in a box, as the browser sends it: a paste event whose clipboard holds `files` ([name, size, type]) and,
# if given, `text`. True when the page kept the browser from pasting (only files: nothing to paste as text).
PASTE = ("(selector, files, text) => { const transfer = new DataTransfer();"
         " for (const [name, size, type] of files) transfer.items.add(new File([new Uint8Array(size).fill(137)],"
         " name, {type}));"
         " if (text) transfer.setData('text/plain', text);"
         " const box = document.querySelector(selector); box.focus();"
         " const event = new ClipboardEvent('paste', {clipboardData: transfer, bubbles: true, cancelable: true});"
         " box.dispatchEvent(event); return event.defaultPrevented; }")
# files dragged from the Finder (Explorer) and dropped on a box: [whether dragover and drop were taken by the page]
DROP = ("(selector, files) => { const transfer = new DataTransfer();"
        " for (const [name, size, type] of files) transfer.items.add(new File([new Uint8Array(size).fill(65)],"
        " name, {type}));"
        " const box = document.querySelector(selector);"
        " return ['dragover', 'drop'].map(kind => { const event = new DragEvent(kind, {dataTransfer: transfer,"
        " bubbles: true, cancelable: true}); box.dispatchEvent(event); return event.defaultPrevented; }); }")
PICTURE = [["image.png", 3000, "image/png"]]  # a copied screenshot: Chrome names it image.png
NOTE = "document.getElementById('task-note').textContent"
PICTURES_GO = "Pictures go with Build a Mission or an agent's chat"
ELEVEN = [[f"shot{number}.png", 10, "image/png"] for number in range(11)]


@CHROME
async def test_a_pasted_picture_is_attached_as_attach_does_and_goes_with_the_mission(stack):
    from test_app_server import told

    js = await open_mission(stack)
    assert await js(f"({PASTE})('#task', {json.dumps(PICTURE)})") is True
    assert await until(js, f"{CHIPS}.length === 1 && {CHIPS}[0].dataset.state === 'done'", 15)  # staged, like Attach
    assert await js(f"{CHIPS}[0].querySelector('.name').textContent") == "image.png"
    assert await js(f"({PASTE})('#task', [], 'look at this')") is False  # pasted text: the browser pastes it
    assert await js(f"{CHIPS}.length") == 1 and await js(NOTE) == ""
    assert await js(f"({DROP})('#composer .box', [['notes.txt', 500, 'text/plain']])") == [True, True]
    assert await until(js, f"{CHIPS}.length === 2 && {CHIPS}.every(chip => chip.dataset.state === 'done')", 15)
    await js("document.getElementById('task').value = 'what is wrong here';"
             " document.getElementById('start').click(); true")
    folder = stack["home"] / "app" / "agents" / "a1" / "work" / "attachments"
    await wait_for(lambda: folder.is_dir() and sorted(path.name for path in folder.iterdir()) == [
        "image.png", "notes.txt"])
    await wait_for(lambda: bool(told(stack["log"])))
    assert "- attachments/image.png (a picture: look at it with Read)" in told(stack["log"])[0]
    assert await until(js, f"{CHIPS}.length === 0")


@CHROME
async def test_ask_ai_takes_no_picture_and_says_where_pictures_go(stack):
    js = await open_mission(stack)
    for mode in ("ask",):
        await js(f"document.getElementById('mode-{mode}').click(); true")
        await js(f"({PASTE})('#task', {json.dumps(PICTURE)})")
        assert await until(js, f"{NOTE} === {json.dumps(PICTURES_GO)}"), mode
        assert await js("document.getElementById('composer').dataset.mode") == mode  # nothing switched by itself
        assert await js(f"{CHIPS}.length") == 0
        await js("document.getElementById('task-note').textContent = ''; true")
    assert await js(f"({PASTE})('#task', {json.dumps(PICTURE)}, 'A1 B1')") is False  # cells from a spreadsheet come
    await asyncio.sleep(0.5)                                                           # with a picture: they're text
    assert await js(NOTE) == ""
    assert list((stack["home"] / "app" / "uploads").glob("*.part")) == []  # nothing was sent to the app


@CHROME
async def test_a_pasted_picture_over_20_mb_or_an_eleventh_file_is_refused(stack):
    js = await open_mission(stack)
    await js(f"({PASTE})('#task', [['image.png', 21000000, 'image/png']])")
    assert await until(js, f"{NOTE} === 'image.png is over 20 MB'")
    assert await js(f"{CHIPS}.length") == 0
    await js(f"({PASTE})('#task', {json.dumps(ELEVEN)})")
    assert await until(js, f"{NOTE} === 'At most 10 files at once'")
    assert await js(f"{CHIPS}.length") == 10


LINE = "#drawer .chat-box"
DRAWER_CHIPS = f"[...document.querySelectorAll('{LINE} .attached-file')]"
DRAWER_NOTE = f"document.querySelector('{LINE} .note').textContent"
PICK_FILE = ("(files) => { const transfer = new DataTransfer();"
             " for (const [name, size] of files) transfer.items.add(new File([new Uint8Array(size).fill(66)], name));"
             f" const input = document.querySelector('{LINE} input[type=file]'); input.files = transfer.files;"
             " input.dispatchEvent(new Event('change')); return true; }")


async def drawer_of_a_finished_agent(stack):
    """Mission Control with a1 done (it answered once) and its drawer open: its chat is where the user writes."""
    from test_mission import open_drawer

    await stack["server"].agents.create("check the page")  # EVENTS: one answer, then its turn ends
    js = await open_mission(stack)
    assert await until(js, f"{station('a1')}?.dataset.state === 'your_turn'")
    await js(open_drawer("a1"))
    assert await until(js, f"document.querySelector('{LINE} textarea') !== null")
    return js


@CHROME
async def test_an_agents_chat_takes_pasted_dropped_and_attached_files(stack):
    from test_app_server import told

    js = await drawer_of_a_finished_agent(stack)
    attach = f"document.querySelector('{LINE} .attach')"
    assert await js(f"[{attach}.getAttribute('aria-label'), {attach}.title]") == [
        "Attach files", "Attach files: at most 10, 20 MB each"]
    assert await js(f"({PASTE})('{LINE} textarea', {json.dumps(PICTURE)})") is True
    assert await js(f"({PASTE})('{LINE} textarea', [], 'words')") is False  # text stays text
    assert await js(f"({DROP})('{LINE}', [['log.txt', 100, 'text/plain']])") == [True, True]
    await js(f"({PICK_FILE})([['report.pdf', 900000]])")  # Attach: two pieces
    assert await until(js, f"{DRAWER_CHIPS}.length === 3 && {DRAWER_CHIPS}.every(chip =>"
                           " chip.dataset.state === 'done')", 15)
    assert await js(f"{CHIPS}.length") == 0  # the composer's chips are its own
    await js(f"document.querySelector('{LINE} textarea').value = 'why does it fail here?';"
             f" document.querySelector('{LINE} .send').click(); true")
    folder = stack["home"] / "app" / "agents" / "a1" / "work" / "attachments"
    await wait_for(lambda: folder.is_dir() and sorted(path.name for path in folder.iterdir()) == [
        "image.png", "log.txt", "report.pdf"])
    await wait_for(lambda: len(told(stack["log"])) == 2)
    message = told(stack["log"])[1]
    assert message.startswith("why does it fail here?\n\nThe user attached these files.")
    assert "- attachments/image.png (a picture: look at it with Read)" in message and "- attachments/log.txt" in message
    assert await until(js, f"{DRAWER_CHIPS}.length === 0 && document.querySelector('{LINE} textarea').value === ''")
    assert await until(js, "document.querySelector('#drawer .messages').textContent.includes('why does it fail')")


@CHROME
async def test_an_agents_chat_keeps_its_files_until_the_app_takes_them(stack):
    from conftest import symlink_or_skip
    from test_app_server import told

    js = await drawer_of_a_finished_agent(stack)
    box = f"document.querySelector('{LINE} textarea')"
    await js(f"({PASTE})('{LINE} textarea', [['image.png', 21000000, 'image/png']])")
    assert await until(js, f"{DRAWER_NOTE} === 'image.png is over 20 MB'")
    await js(f"({PASTE})('{LINE} textarea', {json.dumps(ELEVEN)})")
    assert await until(js, f"{DRAWER_NOTE} === 'At most 10 files at once'")
    assert await until(js, f"{DRAWER_CHIPS}.length === 10 && {DRAWER_CHIPS}.every(chip =>"
                           " chip.dataset.state === 'done')", 15)
    work = stack["home"] / "app" / "agents" / "a1" / "work"
    work.mkdir(parents=True, exist_ok=True)
    outside = stack["home"].parent / "outside"
    outside.mkdir()
    symlink_or_skip(outside, work / "attachments")  # the app refuses to place them: the page keeps them
    await js(f"{box}.value = 'see these'; document.querySelector('{LINE} .send').click(); true")
    assert await until(js, f"{DRAWER_NOTE}.startsWith('The attachments folder in that folder leads somewhere else')")
    assert await js(f"[{DRAWER_CHIPS}.length, {box}.value]") == [10, "see these"]  # nothing lost
    assert list(outside.iterdir()) == [] and len(told(stack["log"])) == 1
    (work / "attachments").unlink()
    await js(f"document.querySelector('{LINE} .send').click(); true")
    assert await until(js, f"{DRAWER_CHIPS}.length === 0 && {box}.value === ''")
    await wait_for(lambda: len(list((work / "attachments").iterdir())) == 10)


# A page whose long timers (10 s and more) run at once, and whose messages to an agent with files wait for
# window.release(): the app's answer comes later than any timer the page sets.
LATE = ("(() => { const later = window.setTimeout;"
        " window.setTimeout = (run, ms, ...rest) => later(run, ms >= 10000 ? 50 : ms, ...rest);"
        " const send = WebSocket.prototype.send; const held = [];"
        " WebSocket.prototype.send = function (data) {"
        "   if (!window.released && typeof data === 'string' && data.startsWith('{\"type\":\"send\"')"
        "       && data.includes('\"attachments\"')) { held.push([this, data]); return; }"
        "   return send.call(this, data); };"
        " window.release = () => { window.released = true; for (const [socket, data] of held.splice(0))"
        " send.call(socket, data); }; })();")


@CHROME
async def test_an_agents_chat_waits_for_the_apps_answer_however_late_it_comes(stack):  # the review of look-3, F5
    from test_mission import open_drawer

    await stack["server"].agents.create("check the page")
    js = await open_with(stack, LATE)
    assert await until(js, f"{station('a1')}?.dataset.state === 'your_turn'")
    await js(open_drawer("a1"))
    assert await until(js, f"document.querySelector('{LINE} textarea') !== null")
    await js(f"({PASTE})('{LINE} textarea', {json.dumps(PICTURE)})")
    assert await until(js, f"{DRAWER_CHIPS}.length === 1 && {DRAWER_CHIPS}[0].dataset.state === 'done'", 15)
    await js(f"document.querySelector('{LINE} textarea').value = 'see this';"
             f" document.querySelector('{LINE} .send').click(); true")
    await asyncio.sleep(1)  # well past every timer the page set
    assert await js(f"document.querySelector('{LINE} .send').disabled") is True  # still waiting for the answer
    await js("window.release(); true")
    assert await until(js, f"{DRAWER_CHIPS}.length === 0 && document.querySelector('{LINE} textarea').value === ''")
    assert await js(f"document.querySelector('{LINE} .send').disabled") is False
    folder = stack["home"] / "app" / "agents" / "a1" / "work" / "attachments"
    await wait_for(lambda: (folder / "image.png").is_file())


@CHROME
async def test_spreadsheet_cells_paste_as_text_and_a_copied_file_still_attaches(stack):  # the review of look-3, F6
    js = await drawer_of_a_finished_agent(stack)
    await js("document.getElementById('mode-ask').click(); true")
    assert await js(f"({PASTE})('#task', [['report.pdf', 10, 'application/pdf']], 'report.pdf')") is False
    assert await until(js, f"{NOTE} === {json.dumps(PICTURES_GO)}")  # a file in Ask AI: where files go
    await js("document.getElementById('mode-build').click(); true")
    for box, chips in (("#task", CHIPS), (f"{LINE} textarea", DRAWER_CHIPS)):
        # cells copied from a spreadsheet: their text, and a picture of them that the browser names image.png
        assert await js(f"({PASTE})('{box}', {json.dumps(PICTURE)}, 'A1\\tB1')") is False
        await asyncio.sleep(0.5)
        assert await js(f"{chips}.length") == 0, box
        # a file copied in the Finder (Explorer): the file, and its name as text
        assert await js(f"({PASTE})('{box}', [['notes.txt', 10, 'text/plain']], 'notes.txt')") is False
        assert await until(js, f"{chips}.length === 1", 15), box


@CHROME
async def test_build_a_mission_and_an_agents_chat_each_hold_their_own_ten_files(stack):  # the review of look-3, F4
    js = await drawer_of_a_finished_agent(stack)
    await js(f"({ATTACH})({json.dumps([[f'build{number}.txt', 10] for number in range(7)])})")
    assert await until(js, f"{CHIPS}.length === 7 && {CHIPS}.every(chip => chip.dataset.state === 'done')", 15)
    four = [[f"chat{number}.png", 10, "image/png"] for number in range(4)]
    await js(f"({PASTE})('{LINE} textarea', {json.dumps(four)})")
    assert await until(js, f"{DRAWER_CHIPS}.length === 4 && {DRAWER_CHIPS}.every(chip =>"
                           " chip.dataset.state === 'done')", 15)  # the page holds 11: none refused


# ---- My Missions and History (Task 14) -------------------------------------------------------------------------------

@CHROME
async def test_my_missions_lists_every_agent_and_filters_by_state(stack):
    from test_bridge_powers import RESULT, ask

    card = [INIT, ask("Bash", {"command": "npm test"}), {"sleep": 30}, RESULT]
    stack["script"].write_text(json.dumps({"default": EVENTS, "keep": WORKING, "card": card}), encoding="utf-8")
    agents = stack["server"].agents
    for words in ("finish the report", "keep working", "card please"):
        await agents.create(words)
    await wait_for(lambda: agents.agents["a1"].state == "your_turn" and agents.agents["a3"].permission is not None)
    js = await open_mission(stack)
    await js(f"{page_link('missions')}.click(); true")
    rows = "[...document.querySelectorAll('#page-missions .mission:not([hidden])')].map(row => row.dataset.id)"
    assert await until(js, f"{rows}.length === 3")
    assert await js(rows) == ["a3", "a2", "a1"]  # newest first
    for name, ids in (("working", ["a2"]), ("needs_you", ["a3"]), ("done", ["a1"]), ("all", ["a3", "a2", "a1"])):
        await js(f"document.querySelector('#page-missions [data-filter={json.dumps(name)}]').click(); true")
        assert await js(rows) == ids, name
    await js("document.querySelector('#page-missions .mission[data-id=\"a2\"] .open').click(); true")
    assert await until(js, "document.getElementById('drawer-title').textContent === '2 · keep working'")


@CHROME
async def test_history_lists_finished_agents_with_their_result_and_files(stack):
    from test_bridge_powers import result

    edit = {"file_path": "/x/footer.html", "old_string": "a", "new_string": "b"}
    said = {"type": "stream_event", "event": {"type": "content_block_delta", "delta": {
        "type": "text_delta", "text": "Fixed the footer.\nIt was missing a link."}}}
    end = {"type": "assistant", "message": {"content": [{"type": "text", "text": "Fixed the footer."}]}}
    stack["script"].write_text(json.dumps({"default": [INIT, use("e1", "Edit", edit), result("e1"), said, end,
                                                       EVENTS[-1]], "keep": WORKING}), encoding="utf-8")
    agents = stack["server"].agents
    await agents.create("fix the footer")
    await agents.create("keep working")
    await wait_for(lambda: agents.agents["a1"].state == "your_turn")
    js = await open_mission(stack)
    await js(f"{page_link('history')}.click(); true")
    rows = "[...document.querySelectorAll('#page-history .history-row:not([hidden])')]"
    assert await until(js, f"{rows}.length === 1")  # only the finished one
    row = f"{rows}[0]"
    assert await js(f"{row}.querySelector('.result').textContent") == "Fixed the footer."
    assert await js(f"{row}.querySelector('.files').textContent") == "1 file changed"
    assert await js(f"{row}.querySelector('.files').title") == "/x/footer.html"
    assert await js(f"{row}.querySelector('.took').textContent") == "2s"
    assert await js(f"{row}.querySelector('.account').textContent") == "Default"
    search = "document.getElementById('history-search')"
    for words, count in (("FOOTER.HTML", 1), ("nothing like it", 0), ("fixed", 1)):
        await js(f"{search}.value = {json.dumps(words)}; {search}.dispatchEvent(new Event('input')); true")
        assert await js(f"{rows}.length") == count, words
    await js(f"{row}.querySelector('.open').click(); true")
    assert await until(js, "document.querySelector('#drawer:not([hidden]) .messages')?.textContent"
                           ".includes('fix the footer')")


@CHROME
async def test_long_words_clip_in_my_missions_and_history(stack, user_home, tmp_path):  # Review Focus 1
    import os

    # a long name (the row shows the folder's name), yet Claude Code's own folder for it (projects/<the whole path,
    # dashed>) stays within a file name's 255 bytes
    deep = tmp_path / ("a-very-long-folder-name-" * 4)
    deep.mkdir()
    stack["server"].agents.rules.trust(deep)
    said = {"type": "stream_event", "event": {"type": "content_block_delta", "delta": {
        "type": "text_delta", "text": "Done: " + "word " * 400}}}
    end = {"type": "assistant", "message": {"content": [{"type": "text", "text": "x"}]}}
    stack["script"].write_text(json.dumps([INIT, said, end, EVENTS[-1]]), encoding="utf-8")
    await stack["server"].agents.create("t" * 2000, folder=str(deep))
    await wait_for(lambda: stack["server"].agents.agents["a1"].state == "your_turn")
    js = await open_with(stack, size=WIDE)
    await js(f"{page_link('missions')}.click(); true")
    folder = "document.querySelector('#page-missions .mission[data-id=\"a1\"] .folder')"
    assert await until(js, f"{folder} !== null")
    assert await js(f"{folder}.title") == os.path.realpath(deep)
    assert await js(f"{folder}.scrollWidth > {folder}.clientWidth")
    assert await js("(() => { const page = document.getElementById('page-missions');"
                    " return page.scrollWidth <= page.clientWidth; })()")
    await js(f"{page_link('history')}.click(); true")
    words = "document.querySelector('#page-history .history-row .result')"
    assert await until(js, f"{words} !== null")
    assert await js(f"{words}.scrollWidth > {words}.clientWidth && {words}.title === {words}.textContent")
    assert await js("(() => { const page = document.getElementById('page-history');"
                    " return page.scrollWidth <= page.clientWidth; })()")


@CHROME
async def test_the_columns_line_up_row_by_row_in_my_missions_and_history(stack):  # found by looking at screenshots
    from test_bridge_powers import RESULT, ask, result

    edit = {"file_path": "/x/footer.html", "old_string": "a", "new_string": "b"}
    card = [INIT, ask("Bash", {"command": "npm test"}), {"sleep": 30}, RESULT]
    stack["script"].write_text(json.dumps({
        "default": EVENTS, "fix": [INIT, use("e1", "Edit", edit), result("e1"), RESULT], "keep": WORKING,
        "card": card}), encoding="utf-8")
    agents = stack["server"].agents
    for words in ("fix the footer", "finish the report", "keep working", "card please"):
        await agents.create(words)
    await wait_for(lambda: agents.agents["a2"].state == "your_turn" and agents.agents["a4"].permission is not None)
    js = await open_mission(stack)

    def edges(page, row, part, side):  # one edge of one part, for each row shown
        return (f"[...document.querySelectorAll('#page-{page} {row}:not([hidden])')]"
                f".map(row => Math.round(row.querySelector('{part}').getBoundingClientRect().{side}))")

    await js(f"{page_link('missions')}.click(); true")
    assert await until(js, f"{edges('missions', '.mission', '.folder', 'left')}.length === 4")
    for part, side in (("meta", "left"), ("chip", "right"), ("time", "left")):
        found = await js(edges("missions", ".mission", f".{part}", side))
        assert len(set(found)) == 1, (part, found)  # the same place in every row, whatever the chip or the time says
    await js(f"{page_link('history')}.click(); true")
    assert await until(js, f"{edges('history', '.history-row', '.chip', 'left')}.length === 2")
    for part in ("chip", "took", "account", "files", "open"):
        found = await js(edges("history", ".history-row", f".{part}", "left"))
        assert len(set(found)) == 1, (part, found)


@CHROME
async def test_a_long_run_time_stays_on_one_line_in_my_missions_and_history(stack):  # review of Task 14
    agents = stack["server"].agents
    for words in ("one", "two"):
        await agents.create(words)  # the stack's script: done at once
    await wait_for(lambda: agents.agents["a1"].state == agents.agents["a2"].state == "your_turn")
    js = await open_mission(stack)
    for page, row, part in (("missions", ".mission", ".time"), ("history", ".history-row", ".took")):
        await js(f"{page_link(page)}.click(); true")
        nodes = f"[...document.querySelectorAll('#page-{page} {row} {part}')]"
        assert await until(js, f"{nodes}.length === 2")
        heights = await js(f"(() => {{ const nodes = {nodes}; const heights = [];"  # each time the page may say, all rows
                           " for (const text of ['2s', '12m 05s', '59m 59s', '23h 59m']) {"  # set at once, so no update
                           "   for (const node of nodes) node.textContent = text;"            # comes between
                           "   heights.push(nodes.map(node => Math.round(node.getBoundingClientRect().height))); }"
                           " return heights; })()")
        assert all(one == heights[0] for one in heights), (part, heights)  # one line, whatever the time
        assert await js(f"{nodes}.every(node => getComputedStyle(node).whiteSpace === 'nowrap')"), part


# ---- Templates, Knowledge and Integrations (Task 15) -----------------------------------------------------------------

@CHROME
async def test_integrations_have_their_own_page(stack):
    js = await open_mission(stack)
    await js(f"{page_link('integrations')}.click(); true")
    assert await until(js, "document.querySelector('#page-integrations .tool-servers') !== null")


@CHROME
async def test_knowledge_lists_skills_and_remove_hides_one_without_deleting_it(stack, tmp_path, monkeypatch):
    from ai_browser.config import load_config

    user = tmp_path / "skills-user"
    skill = user / ".claude" / "skills" / "footer-fixer"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: footer-fixer\ndescription: Fixes footers the way I like\n---\nSteps.\n",
                                    encoding="utf-8")
    monkeypatch.setenv("HOME", str(user))  # the skills come from this throwaway folder, never the user's own
    monkeypatch.setenv("USERPROFILE", str(user))  # Path.home() on Windows
    monkeypatch.setenv("APPDATA", str(user / "AppData" / "Roaming"))  # and the Claude app's synced skills there
    stack["server"]._catalog = None
    js = await open_mission(stack)
    await js(f"{page_link('knowledge')}.click(); true")
    row = "document.querySelector('#page-knowledge .skill[data-ref=\"personal:footer-fixer\"]')"
    assert await until(js, f"{row} !== null")
    assert await js(f"{row}.querySelector('.desc').textContent") == "Fixes footers the way I like"
    await js(f"{row}.querySelector('.remove').click(); true")
    assert await until(js, f"{row} === null")
    assert await until(js, "[...document.querySelectorAll('#page-knowledge .removed li .name')]"
                           ".map(node => node.textContent).includes('personal:footer-fixer')")
    assert load_config(stack["home"]).blocked_skills == ["personal:footer-fixer"]
    assert (skill / "SKILL.md").is_file()  # its files stay
    await js("document.querySelector('#page-knowledge .removed .bring-back').click(); true")
    assert await until(js, f"{row} !== null")
    assert load_config(stack["home"]).blocked_skills == []
    assert await js("document.querySelector('#page-knowledge .train-body .job') !== null")  # Train is here too


def test_skill_block_is_app_only():  # the spec's Safety: no new right
    from ai_browser.app.server import MESSAGE_RULES, may_send

    assert "skill_block" in MESSAGE_RULES and may_send("app", {"type": "skill_block"})
    assert not may_send("none", {"type": "skill_block"})


# ---- workspaces and the Usage card (Task 16) -------------------------------------------------------------------------

def press_enter(selector):
    return (f"(() => {{ const box = document.querySelector({json.dumps(selector)});"
            " box.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); return true; })()")


@CHROME
async def test_workspaces_are_made_renamed_and_filter_the_pages(stack):
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    agents = stack["server"].agents
    for name in ("research the market", "plan the launch"):
        await agents.create(name)
    js = await open_mission(stack)
    box = "#workspaces input.workspace-name"
    await js("document.querySelector('#workspaces .workspace-new').click(); true")
    assert await until(js, f"document.querySelector({json.dumps(box)}) !== null")
    await js(f"document.querySelector({json.dumps(box)}).value = 'Research'; true")
    await js(press_enter(box))
    pick = "document.querySelector('#workspaces .workspace-pick')"
    assert await until(js, f"{pick}?.querySelector('.name').textContent === 'Research'")
    [research] = stack["server"].workspaces.list()
    assert await js(f"{pick}.querySelector('.count').textContent") == "0"
    await js(f"{page_link('missions')}.click(); true")
    move = "document.querySelector('#page-missions .mission[data-id=\"a1\"] select.move')"
    assert await until(js, f"{move} !== null")
    await js(f"{move}.value = {json.dumps(research['id'])}; {move}.dispatchEvent(new Event('change')); true")
    await wait_for(lambda: agents.agents["a1"].workspace == research["id"])
    assert await until(js, f"{pick}.querySelector('.count').textContent === '1'")  # an agent
    await js(f"{pick}.click(); {page_link('dashboard')}.click(); true")  # the filter
    shown = "[...document.querySelectorAll('.station:not(.away)')].map(node => node.dataset.id)"
    assert await until(js, f"JSON.stringify({shown}) === '[\"a1\"]'")
    await js(f"{page_link('missions')}.click(); true")
    assert await js("[...document.querySelectorAll('#page-missions .mission:not([hidden])')]"
                    ".map(row => row.dataset.id)") == ["a1"]
    assert await js("document.getElementById('task-workspace').value") == research["id"]  # new missions go there
    await js("document.querySelector('#workspaces .workspace-more').click();"
             "document.querySelector('#workspaces .rename').click(); true")
    assert await until(js, f"document.querySelector({json.dumps(box)}) !== null")
    await js(f"document.querySelector({json.dumps(box)}).value = 'Deep research'; true")
    await js(press_enter(box))
    assert await until(js, f"{pick}?.querySelector('.name').textContent === 'Deep research'")
    await js(f"{pick}.click(); true")  # picked again: every agent
    assert await until(js, "document.querySelectorAll('#page-missions .mission:not([hidden])').length === 2")


@CHROME
async def test_a_workspace_deleted_while_its_agents_run_keeps_them_in_the_room(stack):  # Review Focus 4
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    research = stack["server"].workspaces.create("Research")
    agent = await stack["server"].agents.create("keep working", workspace=research["id"])
    js = await open_mission(stack)
    pick = "document.querySelector('#workspaces .workspace-pick')"
    assert await until(js, f"{pick}?.querySelector('.count').textContent === '1'")
    await js(f"{pick}.click(); true")  # the room shows only this workspace
    assert await until(js, f"{station('a1')} !== null && !{station('a1')}.classList.contains('away')")
    await js("document.querySelector('#workspaces .workspace-more').click();"
             "const del = document.querySelector('#workspaces .delete'); del.click(); del.click(); true")
    assert await until(js, "document.querySelectorAll('#workspaces .workspace').length === 0")
    assert await until(js, f"!{station('a1')}.classList.contains('away')")  # the filter went with it
    assert agent.state == "working" and agent.workspace is None  # still at work, ungrouped


@CHROME
async def test_closing_the_menu_disarms_delete(stack):  # the final review, F9
    research = stack["server"].workspaces.create("Research")
    js = await open_mission(stack)
    more, delete = "document.querySelector('#workspaces .workspace-more')", "document.querySelector('#workspaces .delete')"
    assert await until(js, f"{more} !== null")
    await js(f"{more}.click(); {delete}.click(); true")  # armed: "Delete? Its agents keep running"
    assert await js(f"{delete}.textContent") == "Delete? Its agents keep running"
    await js(f"{more}.click(); {more}.click(); true")  # closed, and opened again later
    assert await js(f"{delete}.textContent") == "Delete"
    await js(f"{delete}.click(); true")  # one click only arms it again
    await asyncio.sleep(0.5)
    assert stack["server"].workspaces.get(research["id"]) is not None
    assert await js(f"{delete}.textContent") == "Delete? Its agents keep running"


USAGE = "document.getElementById('usage')"
CARD = """[...document.querySelectorAll('#usage .usage-account')].map((account) => ({
  name: account.querySelector('.usage-name').textContent, note: account.querySelector('.usage-note').textContent,
  noteColor: getComputedStyle(account.querySelector('.usage-note')).color,
  windows: [...account.querySelectorAll('.usage-window')].map((one) => ({ window: one.dataset.window,
    state: one.dataset.state, label: one.querySelector('.usage-label').textContent,
    percent: one.querySelector('.usage-percent').textContent, width: one.querySelector('.usage-fill').style.width,
    fill: getComputedStyle(one.querySelector('.usage-fill')).backgroundColor,
    when: one.querySelector('.usage-when').textContent,
    whenColor: getComputedStyle(one.querySelector('.usage-when')).color })) }))"""
ACCENT_2, NEEDS, FAIL = "rgb(79, 141, 253)", "rgb(255, 181, 71)", "rgb(255, 93, 108)"  # the theme's tokens


async def clock(js, seconds):
    """The time the page writes for `seconds` since 1970: "9:30 pm", or "Tue 4:00 pm" on another day (accountui.js)."""
    return await js(f"import('/accountui.js').then(({{ resetTime }}) => resetTime({seconds}))")


async def card_says(js, expression):
    """The Usage card, once `expression` (about `card`, its first account) holds."""
    assert await until(js, f"(() => {{ const card = ({CARD})[0]; return Boolean(card && ({expression})); }})()"), \
        await js(CARD)
    return (await js(CARD))[0]


@CHROME
async def test_the_usage_card_shows_the_session_and_the_week_and_never_makes_up_a_number(stack):  # Review Focus 3
    import time

    accounts, server = stack["accounts"], stack["server"]
    js = await open_mission(stack)
    card = await card_says(js, "card.name === 'Default'")
    assert card["note"] == "Updates when an agent works"  # no reading yet: empty bars, and no number
    assert [(one["window"], one["label"], one["percent"], one["width"], one["when"]) for one in card["windows"]] == [
        ("five_hour", "Current session", "", "0%", ""), ("seven_day", "Weekly", "", "0%", "")]
    assert "%" not in await js(f"{USAGE}.textContent")
    assert await js(f"{USAGE}.querySelector('.usage-ring')") is None  # the ring went: the bars say it
    later = time.time() + 3600  # a limit Claude Code gave no reading for: the words, still no number
    accounts.set_limit("default", later)
    server._accounts_changed()
    card = await card_says(js, "card.note.startsWith('At its limit until ')")
    assert card["note"] == f"At its limit until {await clock(js, later)}" and card["noteColor"] == NEEDS
    assert "%" not in await js(f"{USAGE}.textContent")
    accounts._limits.clear()
    now = time.time()
    session, week = now + 3 * 3600, now + 4 * 86400
    accounts.set_windows("default", {"five_hour": {"used": 14.0, "resets_at": session},
                                     "seven_day": {"used": 83.0, "resets_at": week}})
    server._accounts_changed()
    card = await card_says(js, "card.windows[0].percent === '14%'")
    five, seven = card["windows"]
    assert (five["percent"], five["width"], five["state"], five["fill"]) == ("14%", "14%", "ok", ACCENT_2)
    assert (seven["percent"], seven["width"], seven["state"], seven["fill"]) == ("83%", "83%", "high", NEEDS)  # 80%+
    assert five["when"] == f"resets {await clock(js, session)}"
    assert seven["when"] == f"resets {await clock(js, week)}" and seven["when"].split()[1] in (
        "Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")  # another day: its weekday too
    at = accounts.windows("default")["five_hour"]["at"]
    assert card["note"] == f"as of {await clock(js, at)}"  # the reading's own time, as after a restart
    # at its limit: a window at 100%, or the account's limit that ends when a window resets
    accounts.set_windows("default", {"five_hour": {"used": 100.0, "resets_at": session}})
    server._accounts_changed()
    five = (await card_says(js, "card.windows[0].state === 'limit'"))["windows"][0]
    assert (five["percent"], five["width"], five["fill"]) == ("", "100%", FAIL)
    assert five["when"] == f"At its limit until {await clock(js, session)}" and five["whenColor"] == NEEDS
    accounts.set_limit("default", week)
    server._accounts_changed()
    seven = (await card_says(js, "card.windows[1].state === 'limit'"))["windows"][1]
    assert (seven["width"], seven["when"]) == ("100%", f"At its limit until {await clock(js, week)}")
    # a reading whose reset has passed: no number any more
    accounts._limits.clear()
    passed = now - 60
    accounts.set_windows("default", {"five_hour": {"used": 64.0, "resets_at": passed}})
    server._accounts_changed()
    five = (await card_says(js, "card.windows[0].state === 'reset'"))["windows"][0]
    assert (five["percent"], five["width"]) == ("", "0%")
    assert five["when"] == f"Reset at {await clock(js, passed)} · updates with your next mission"
    assert "64" not in await js(f"{USAGE}.textContent")


@CHROME
async def test_the_usage_card_lists_three_signed_in_accounts_default_first_as_text(stack):
    from ai_browser.accounts import clean_name
    from fake_accounts import sign_in
    from test_home import HOSTILE

    accounts, server = stack["accounts"], stack["server"]
    for name in ("Work", HOSTILE, "Side", "Spare"):
        sign_in(accounts.add(name).folder)
    accounts.add("Signed out")  # not signed in: not listed
    js = await open_mission(stack)
    names = "[...document.querySelectorAll('#usage .usage-name')].map((node) => node.textContent)"
    more = f"{USAGE}.querySelector('.usage-more')?.textContent"
    assert await until(js, f"{more} === '+2 more'"), await js(more)  # once each status is known: Side and Spare
    assert await js(names) == ["Default", "Work", clean_name(HOSTILE)]  # Default first, then as listed, at most 3
    assert await js(f"{USAGE}.querySelectorAll('img').length") == 0 and await js("document.title") != "pwned"
    server._accounts_changed()  # drawn again: still three
    assert await js(f"{USAGE}.querySelectorAll('.usage-account').length") == 3


@CHROME
async def test_the_usage_cards_words_and_bars_in_plain_data(stack):  # usage.js's usageOf, no page needed
    js = await open_mission(stack)
    found = await js("""import('/usage.js').then(({ usageOf }) => {
      const now = 1800000000;
      const row = (windows, more = {}) => ({ name: 'Work', signed_in: true, limit_until: null, windows, ...more });
      const bars = (shown) => shown.bars.map((bar) => [bar.window, bar.percent, bar.width, bar.state]);
      return [
        bars(usageOf(row({ five_hour: { used: 14.4, resets_at: now + 60, at: now - 5 } }), now)),
        bars(usageOf(row({ five_hour: { used: 'x' }, seven_day: { used: NaN, at: now } }), now)),
        bars(usageOf(row({ five_hour: { used: 1e9, at: now }, seven_day: { used: -3, at: now } }), now)),
        bars(usageOf(row({ seven_day: { used: 99.6, resets_at: now - 1, at: now - 9 } }), now)),
        usageOf(row({}), now).note, usageOf(row({ five_hour: { used: 1, at: now } }), now).note.startsWith('as of '),
        bars(usageOf(row({ five_hour: { used: 40, resets_at: now + 600, at: now } }, { limit_until: now + 600 }), now)),
        bars(usageOf(row({ five_hour: { used: 40, resets_at: now + 600, at: now } }, { limit_until: now - 1 }), now)),
        bars(usageOf(row({ five_hour: { used: 99.6, at: now } }), now)),
      ];
    })""")
    assert found == [
        [["five_hour", 14, 14.4, "ok"], ["seven_day", None, 0, "none"]],
        [["five_hour", None, 0, "none"], ["seven_day", None, 0, "none"]],  # not a number: no reading
        [["five_hour", None, 0, "none"], ["seven_day", None, 0, "none"]],  # outside 0 to 100: no reading either
        [["five_hour", None, 0, "none"], ["seven_day", None, 0, "reset"]],  # its reset passed
        "Updates when an agent works", True,
        [["five_hour", None, 100, "limit"], ["seven_day", None, 0, "none"]],  # the account's limit ends at its reset
        [["five_hour", 40, 40, "ok"], ["seven_day", None, 0, "none"]],  # a limit that has ended
        [["five_hour", 99, 99.6, "high"], ["seven_day", None, 0, "none"]],  # never "100%" short of the limit
    ]


@CHROME
async def test_a_row_without_a_name_never_says_undefined(stack):  # the polish's review, F4
    js = await open_mission(stack)
    shown = await js("""import('/usage.js').then(({ mountUsage }) => {
      const button = document.createElement('button');
      mountUsage(button).render([{ id: 'x', signed_in: true, windows: {} }]);
      return [button.title, button.querySelector('.usage-name').textContent];
    })""")
    assert shown == [": updates when an agent works\nSettings → Accounts", ""]


@CHROME
async def test_a_reading_left_open_past_its_reset_stops_showing_its_number(stack):  # the card redraws once a minute
    import time

    accounts, server = stack["accounts"], stack["server"]
    source = ("window.minute = []; const every = window.setInterval;"
              "window.setInterval = (callback, wait, ...rest) => { if (wait === 60000) window.minute.push(callback);"
              " return every(callback, wait, ...rest); };")  # the page's once-a-minute timers, to run them by hand
    accounts.set_windows("default", {"five_hour": {"used": 64.0, "resets_at": time.time() + 2}})
    js = await open_with(stack, source)
    await card_says(js, "card.windows[0].percent === '64%'")
    await asyncio.sleep(2.5)
    await js("window.minute.forEach((callback) => callback()); true")
    await card_says(js, "card.windows[0].state === 'reset' && card.windows[0].percent === ''")


@CHROME
async def test_the_usage_card_opens_settings_at_accounts(stack):
    from test_tab_menu import active_is, click_in, connected, frame, pick, window_page

    js = await window_page(stack)
    await pick(js, "/mission")
    assert await until(js, connected("/mission"))
    await click_in(js, "/mission", "#usage")
    assert await until(js, f"{active_is('/settings')} && {connected('/settings')}")
    assert await until(js, f"{frame('/settings')}.location.hash === '#accounts-section'")


# ---- the controller's rulings for Task 16 ------------------------------------------------------------------------------

@CHROME
async def test_the_rooms_note_follows_whether_any_agent_exists_at_all(stack):  # carried from Task 11's review
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    server = stack["server"]
    research = server.workspaces.create("Research")
    server.workspaces.create("Empty")  # nothing in it
    await server.agents.create("keep working", workspace=research["id"])
    js = await open_mission(stack)
    note = "document.querySelector('.empty-note')"
    shown = f"getComputedStyle({note}).display !== 'none'"

    def pick(name):
        return ("[...document.querySelectorAll('#workspaces .workspace-pick')]"
                f".find(button => button.querySelector('.name').textContent === {json.dumps(name)})")

    assert await until(js, f"{pick('Empty')} !== undefined && {station('a1')} !== null")
    assert await until(js, f"!({shown})")  # an agent stands in the room: no note
    await js(f"{pick('Empty')}.click(); true")  # agents exist, none in this workspace
    assert await until(js, shown)
    assert await js(f"{note}.textContent") == "No missions in this workspace"
    assert await js("document.querySelector('.room').dataset.empty") == "true"
    await js(f"{pick('Empty')}.click(); true")  # picked again: every agent, and no note
    assert await until(js, f"!({shown})")
    await js(f"{pick('Empty')}.click(); true")
    assert await until(js, shown)
    await server.agents.close("a1")  # no agent anywhere: the room says how to start one
    assert await until(js, f"{note}.textContent === 'Start a mission below' && {shown}")


@CHROME
async def test_the_usage_card_shows_an_icon_when_the_menu_shrinks_to_icons(stack):  # carried from Task 12's review
    import time

    accounts, server = stack["accounts"], stack["server"]
    usage = "document.getElementById('usage')"
    mark = f"{usage}.querySelector('.usage-icon')"
    js = await open_with(stack, size=NARROW)
    assert await until(js, f"{usage}.querySelector('.usage-account') !== null")
    menu = await js(f"{BOX}(document.getElementById('menu'))")

    async def narrow_card():
        card = await js(f"{BOX}({usage})")
        assert menu[0] <= card[0] and card[2] <= menu[2], card  # inside the menu, never wider than it
        assert card[2] - card[0] >= 36 and card[3] - card[1] >= 36, card  # a button to press, not an empty pill
        assert await js(f"getComputedStyle({usage}.querySelector('.usage-words')).display") == "none"
        icon = await js(f"{BOX}({mark})")
        assert icon[2] - icon[0] >= 16 and icon[3] - icon[1] >= 16, icon  # an icon, seen
        assert card[0] <= icon[0] and icon[2] <= card[2] and card[1] <= icon[1] and icon[3] <= card[3], (card, icon)
        assert await js("document.documentElement.scrollWidth <= innerWidth")

    await narrow_card()
    assert await js(f"{usage}.title") == "Default: updates when an agent works\nSettings → Accounts"
    accounts.set_windows("default", {"five_hour": {"used": 64.0, "resets_at": time.time() + 3600},
                                     "seven_day": {"used": 20.0, "resets_at": time.time() + 86400 * 3}})
    server._accounts_changed()  # numbers were reported: the icon stays, and its tooltip lists them
    assert await until(js, f"{usage}.title.startsWith('Default: Current session 64%')")
    assert await js(f"{usage}.title") == "Default: Current session 64% · Weekly 20%\nSettings → Accounts"
    await narrow_card()
    js = await open_with(stack, size=WIDE)  # at full width the words say it, not the icon
    assert await until(js, f"{usage}.querySelector('.usage-account') !== null")
    assert await js(f"getComputedStyle({mark}).display") == "none"


@CHROME
async def test_moving_an_agent_never_waits_for_an_answer(stack):  # from Task 6: an unknown agent gets no reply
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    server = stack["server"]
    agents = server.agents
    research = server.workspaces.create("Research")
    for name in ("one", "two"):
        await agents.create(name)
    asked, real = [], agents.set_workspace

    def set_workspace(agent_id, workspace_id):  # the app finds no agent a1, and (as with an unknown one) says nothing
        asked.append((agent_id, workspace_id))
        return False if agent_id == "a1" else real(agent_id, workspace_id)

    agents.set_workspace = set_workspace
    js = await open_mission(stack)
    await js(f"{page_link('missions')}.click(); true")

    def move(agent_id):
        return f"document.querySelector('#page-missions .mission[data-id=\"{agent_id}\"] select.move')"

    assert await until(js, f"{move('a1')} !== null && {move('a2')} !== null")
    await js(f"{move('a1')}.value = {json.dumps(research['id'])}; {move('a1')}.dispatchEvent(new Event('change')); true")
    await wait_for(lambda: asked == [("a1", research["id"])])
    assert await js(f"{move('a1')}.disabled") is False  # nothing waits for an answer that never comes
    assert await js("document.getElementById('task-note').textContent") == ""
    await js(f"{move('a2')}.value = {json.dumps(research['id'])}; {move('a2')}.dispatchEvent(new Event('change')); true")
    await wait_for(lambda: agents.agents["a2"].workspace == research["id"])  # the next move goes at once
    assert asked[-1] == ("a2", research["id"])
    assert await until(js, f"{move('a2')}.value === {json.dumps(research['id'])} && !{move('a2')}.disabled")


@CHROME
async def test_workspace_menus_keep_one_width_and_the_columns_still_line_up(stack):  # Task 14's alignment test, with it
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    server = stack["server"]
    short, other = server.workspaces.create("QA"), server.workspaces.create("Docs")
    for words, workspace in (("one", short["id"]), ("two", other["id"]), ("three", None)):
        await server.agents.create(words, workspace=workspace)
    js = await open_mission(stack)
    await js(f"{page_link('missions')}.click(); true")
    rows = "[...document.querySelectorAll('#page-missions .mission:not([hidden])')]"

    def edges(part, side):  # one edge of one part, for each row shown
        return f"{rows}.map(row => Math.round(row.querySelector('{part}').getBoundingClientRect().{side}))"

    async def lined_up():
        for part, side in (("select.move", "left"), ("select.move", "right"), (".meta", "left"), (".chip", "right"),
                           (".time", "left")):
            found = await js(edges(part, side))
            assert len(set(found)) == 1, (part, side, found)  # the same place in every row, whatever the name says
        [width] = set(await js(f"{rows}.map(row => Math.round(row.querySelector('select.move')"
                               ".getBoundingClientRect().width))"))
        return width

    assert await until(js, f"{edges('select.move', 'left')}.length === 3")
    assert await js(f"{rows}.map(row => row.querySelector('select.move').value)") \
        == ["", other["id"], short["id"]]  # newest first: three different things to say
    before = await lined_up()
    assert before > 0
    server.workspaces.create("A workspace with a very long name indeed")  # a longer name: no wider a menu
    server._send_all(server._workspaces_message())
    assert await until(js, f"{rows}.every(row => row.querySelector('select.move').options.length === 4)")
    assert await lined_up() == before


@CHROME
async def test_the_shrunk_menu_lists_workspaces_as_icons_that_fit(stack):  # found by looking at a screenshot
    server = stack["server"]
    server.workspaces.create("Research")
    server.workspaces.create("Launch plan")
    js = await open_with(stack, size=NARROW)
    assert await until(js, "document.querySelectorAll('#workspaces .workspace-pick').length === 2")
    menu = await js(f"{BOX}(document.getElementById('menu'))")
    assert await js("document.getElementById('menu').scrollWidth <= document.getElementById('menu').clientWidth")
    for selector in ("#workspaces .workspace-pick", "#workspaces .workspace-new", "#usage"):
        box = await js(f"{BOX}(document.querySelector({json.dumps(selector)}))")
        assert menu[0] <= box[0] and box[2] <= menu[2], (selector, box, menu)  # inside the menu
        assert abs((box[0] + box[2]) / 2 - (menu[0] + menu[2]) / 2) <= 2, (selector, box, menu)  # as centred as the rest
        assert box[2] - box[0] >= 36, (selector, box)  # a button to press
    assert await js("getComputedStyle(document.querySelector('#workspaces .workspace-pick .name')).display") == "none"


@CHROME
async def test_a_settings_tab_already_open_moves_to_accounts_without_reloading_and_only_for_a_plain_section(stack):
    import asyncio

    from test_tab_menu import active_is, click_in, connected, frame, in_frame, pick, window_page

    js = await window_page(stack)
    await pick(js, "/settings")
    assert await until(js, connected("/settings"))
    assert await js(f"(() => {{ const page = {frame('/settings')}; page.marker = 'same page'; return page.marker; }})()") \
        == "same page"
    await pick(js, "/mission")
    assert await until(js, connected("/mission"))
    for section in ("#Accounts", "#a b", "#<img src=x>", "#1x", "#" + "a" * 50):  # not a plain section: dropped
        path = json.dumps("/settings" + section)
        await in_frame(js, "/mission", f"parent.postMessage({{type: 'tab', path: {path}}}, location.origin); true")
        assert await until(js, active_is("/settings"))
        assert await js(f"{frame('/settings')}.location.hash") == "", section
        await pick(js, "/mission")
    await click_in(js, "/mission", "#usage")
    assert await until(js, f"{active_is('/settings')} && {frame('/settings')}.location.hash === '#accounts-section'")
    assert await js(f"{frame('/settings')}.marker") == "same page"  # its section moved: the page was not reloaded
    await asyncio.sleep(0.2)
    assert await js(f"{frame('/settings')}.document.getElementById('status')?.dataset.state") == "connected"


# ---- the Calendar (Task 17) ------------------------------------------------------------------------------------------

@CHROME
async def test_the_calendar_shows_scheduled_templates_and_finished_agents(stack):
    import datetime

    stack["workflows"].save({"name": "Morning report", "instructions": "Write it", "trigger": "schedule",
                             "schedule": "daily 09:00"})
    stack["workflows"].save({"name": "Check often", "instructions": "Check", "trigger": "schedule",
                             "schedule": "every 2h"})
    await stack["server"].agents.create("Fix the footer")  # the stack's script: done at once
    await wait_for(lambda: stack["server"].agents.agents["a1"].state == "your_turn")
    js = await open_mission(stack)
    await js("document.querySelector('#views-switch [data-view=\"calendar\"]').click(); true")
    today = datetime.date.today()
    cell = f"document.querySelector('#view-calendar .day[data-day=\"{today.year}-{today.month}-{today.day}\"]')"
    assert await until(js, f"{cell}?.querySelector('.entry.agent') !== null")
    assert (await js(f"{cell}.querySelector('.entry.agent').textContent")).endswith("✓ 1 · Fix the footer")
    entries = "[...document.querySelectorAll('#view-calendar .entry.template')].map(node => node.textContent)"
    assert await until(js, f"{entries}.some(text => text.endsWith('09:00 Morning report'))")
    assert await js(f"{entries}.some(text => text === 'Check often · Every 2h')")
    assert await js("document.querySelectorAll('#view-calendar .day').length") == 42
    await js("document.querySelector('#view-calendar [data-mode=\"week\"]').click(); true")
    assert await js("document.querySelectorAll('#view-calendar .day').length") == 7
    await js(f"{cell}.querySelector('.entry.agent').click(); true")
    assert await until(js, "document.getElementById('drawer-title').textContent === '1 · Fix the footer'")
    await js("document.getElementById('drawer-close').click();"
             "document.querySelector('#view-calendar .entry.template').click(); true")
    assert await until(js, "!document.getElementById('page-agents').hidden && document.querySelector("
                           "'#page-agents .workflow[data-slug=\"morning-report\"]') !== null")  # Tasks for any agent


CALENDAR_FUNCTIONS = """import('/calendar.js').then(({ monthGrid, weekDays, everyWords, calendarItems }) => {
  const at = (month, date, hour = 0, minute = 0) => new Date(2026, month - 1, date, hour, minute);
  const secs = (date) => date.getTime() / 1000;
  const days = (grid) => grid.map((date) => `${date.getMonth() + 1}-${date.getDate()}`);
  const time = (date) => `${date.getMonth() + 1}-${date.getDate()} ${date.getHours()}:${String(date.getMinutes())
    .padStart(2, '0')}`;
  const shown = (items) => items.map((item) => [item.kind, item.slug || item.id, item.label, time(item.at),
                                                 Boolean(item.allDay)]);
  const grids = [monthGrid(2026, 9), monthGrid(2026, 1), monthGrid(2026, 5)].map((grid) => [
    grid.length, days(grid)[0], days(grid)[41], grid[0].getDay()]);
  const week = weekDays(at(10, 7, 15, 30));
  const rows = [
    { slug: 'morning', name: 'Morning report', every: null,
      runs: [secs(at(10, 7, 9)), secs(at(10, 8, 9)), secs(at(10, 9, 9)), secs(at(10, 13, 9))] },
    { slug: 'often', name: 'Check often', every: 7200, runs: [secs(at(10, 7, 9))] }, // its next run passed an hour ago
    { slug: 'late', name: 'Check late', every: 7200, runs: [secs(at(10, 8, 2))] },
  ];
  const agents = [
    { id: 'a1', name: 'Fix the footer', state: 'your_turn', finished: secs(at(10, 6, 12)) },
    { id: 'a2', name: 'Still going', state: 'working' },
    { id: 'a3', name: 'No time', state: 'failed' },
    { id: 'a4', name: 'Broke', state: 'failed', finished: secs(at(10, 7, 8, 30)) },
    { id: 'a5', name: 'Asks', state: 'your_turn', permission: { tool: 'Bash' }, finished: secs(at(10, 7, 8)) },
  ];
  return {
    grids,
    week: [days(week), week.map((date) => date.getHours() + date.getMinutes())],
    sunday: days(weekDays(at(10, 11, 23, 59))),
    across: days(weekDays(at(11, 1))),
    words: [7200, 1800, 5400, 3600].map(everyWords),
    items: shown(calendarItems(rows, agents, at(10, 5), at(10, 12), at(10, 7, 10))),
    later: shown(calendarItems(rows, [], at(10, 9), at(10, 12), at(10, 7, 10))),
    odd: [calendarItems(null, [], at(10, 5), at(10, 12), at(10, 7, 10)).length,
          calendarItems([{ slug: 'x', name: 'x', runs: 'no' }, { slug: 'y', name: 'y', runs: [NaN, 'a'] }, {}],
                        [{ id: 'a9', state: 'your_turn', finished: 'soon' }], at(10, 5), at(10, 12),
                        at(10, 7, 10)).length],
  };
})"""


@CHROME
async def test_the_calendars_days_words_and_items_in_plain_data(stack):  # calendar.js's functions, no page
    js = await open_mission(stack)
    found = await js(CALENDAR_FUNCTIONS)
    assert found["grids"] == [[42, "9-28", "11-8", 1],  # October 2026 starts on a Thursday: from Monday 28 September
                              [42, "1-26", "3-8", 1],  # February 2026 starts on a Sunday: six days back
                              [42, "6-1", "7-12", 1]]  # June 2026 starts on a Monday: no days before it
    assert found["week"] == [[f"10-{day}" for day in range(5, 12)], [0] * 7]  # Monday to Sunday, each from midnight
    assert found["sunday"] == [f"10-{day}" for day in range(5, 12)]  # a Sunday belongs to the week before it
    assert found["across"] == ["10-26", "10-27", "10-28", "10-29", "10-30", "10-31", "11-1"]
    assert found["words"] == ["Every 2h", "Every 30m", "Every 90m", "Every 1h"]
    morning = lambda day: ["template", "morning", "Morning report", f"10-{day} 9:00", False]  # noqa: E731
    often = lambda day: ["template", "often", "Check often · Every 2h", f"10-{day} 0:00", True]  # noqa: E731
    late = lambda day: ["template", "late", "Check late · Every 2h", f"10-{day} 0:00", True]  # noqa: E731
    assert found["items"] == [  # now is Wednesday 7 October, 10:00: nothing scheduled earlier than that
        ["agent", "a1", "1 · Fix the footer", "10-6 12:00", False],  # a finished agent stays at its finish time
        often(7),  # its stale next run (9:00) moved on to 11:00, so today has it
        ["agent", "a4", "4 · Broke", "10-7 8:30", False],  # finished earlier today: stays
        often(8), late(8), morning(8), often(9), late(9), morning(9), often(10), late(10), often(11), late(11)]
    assert found["later"] == [often(9), late(9), morning(9), often(10), late(10), often(11), late(11)]
    assert found["odd"] == [0, 0]  # rows and agents that say nothing usable draw nothing


@CHROME
async def test_a_calendar_left_open_drops_a_run_once_it_has_passed(stack):  # next_runs is computed when it is sent
    import time

    source = ("window.minute = []; const every = window.setInterval;"
              "window.setInterval = (callback, wait, ...rest) => { if (wait === 60000) window.minute.push(callback);"
              " return every(callback, wait, ...rest); };")  # the page's once-a-minute timers, to run them by hand
    js = await open_with(stack, source)
    await js("document.querySelector('#views-switch [data-view=\"calendar\"]').click(); true")
    now = time.time()

    def row(slug, moment):
        return {"slug": slug, "name": slug.title(), "schedule": "daily 09:00", "every": None, "runs": [moment]}

    stack["server"]._send_all({"type": "workflows_snapshot", "workflows": [], "problems": [],
                               "next_runs": [row("past", now - 60), row("soon", now + 4),
                                             row("tomorrow", now + 86400)]})
    slugs = "[...document.querySelectorAll('#view-calendar .entry.template')].map(node => node.dataset.slug).sort()"
    assert await until(js, f"{slugs}.includes('tomorrow')")
    assert await js(slugs) == ["soon", "tomorrow"]  # a run a minute ago is not drawn
    await asyncio.sleep(4.5)  # "soon" has passed; nothing told the page (the margins hold under a loaded suite)
    assert await js("window.minute.length") >= 1
    both = await js(f"(() => {{ const before = {slugs}; window.minute.forEach((callback) => callback());"
                    f" return [before, {slugs}]; }})()")
    assert both == [["soon", "tomorrow"], ["tomorrow"]]  # its own timer drew it again, without "soon"


@CHROME
async def test_the_calendar_follows_the_menus_workspace_for_templates_as_for_agents(stack):  # the review of Task 17
    server = stack["server"]
    research, docs = server.workspaces.create("Research"), server.workspaces.create("Docs")
    for name, schedule in (("Morning report", "daily 09:00"), ("Check often", "every 2h"),
                           ("Weekly plan", "daily 10:00")):
        stack["workflows"].save({"name": name, "instructions": "Do it", "trigger": "schedule", "schedule": schedule})
    server.workspaces.assign_template("morning-report", research["id"])
    server.workspaces.assign_template("check-often", docs["id"])  # "weekly-plan" is in no workspace
    js = await open_mission(stack)
    await js("document.querySelector('#views-switch [data-view=\"calendar\"]').click(); true")
    slugs = ("[...new Set([...document.querySelectorAll('#view-calendar .entry.template')]"
             ".map(node => node.dataset.slug))].sort()")

    def pick(name):
        return ("[...document.querySelectorAll('#workspaces .workspace-pick')]"
                f".find(button => button.querySelector('.name').textContent === {json.dumps(name)})")

    assert await until(js, f"JSON.stringify({slugs}) === '[\"check-often\",\"morning-report\",\"weekly-plan\"]'")
    assert await until(js, f"{pick('Research')} !== undefined")
    await js(f"{pick('Research')}.click(); true")  # a template of another workspace, or of none, is not drawn
    assert await until(js, f"JSON.stringify({slugs}) === '[\"morning-report\"]'")
    await js(f"{pick('Docs')}.click(); true")
    assert await until(js, f"JSON.stringify({slugs}) === '[\"check-often\"]'")
    await js(f"{pick('Docs')}.click(); true")  # picked again: every template
    assert await until(js, f"JSON.stringify({slugs}) === '[\"check-often\",\"morning-report\",\"weekly-plan\"]'")


@CHROME
async def test_an_agent_update_that_changes_nothing_drawn_keeps_the_calendars_focus(stack):  # the final review, F2
    agents = stack["server"].agents
    await agents.create("Fix the footer")  # the stack's script: done at once
    await wait_for(lambda: agents.agents["a1"].state == "your_turn")
    source = ("window.minute = []; const every = window.setInterval;"
              "window.setInterval = (callback, wait, ...rest) => { if (wait === 60000) window.minute.push(callback);"
              " return every(callback, wait, ...rest); };")  # the page's once-a-minute timers, to run them by hand
    js = await open_with(stack, source)
    await js("document.querySelector('#views-switch [data-view=\"calendar\"]').click(); true")
    entry = "document.querySelector('#view-calendar .entry.agent[data-agent=\"a1\"]')"
    assert await until(js, f"{entry} !== null")
    await js(f"window.picked = {entry}; window.picked.focus(); true")
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await agents.create("keep working")  # an agent at work: nothing the Calendar draws
    assert await until(js, "document.getElementById('counts').textContent === '1 active task · 1 completed'")
    agents._changed(agents.agents["a1"])  # its row sent again, unchanged
    await asyncio.sleep(0.5)
    assert await js("window.picked.isConnected && document.activeElement === window.picked")
    await js("window.minute.forEach((callback) => callback()); true")  # the once-a-minute redraw: nothing changed
    assert await js("window.picked.isConnected && document.activeElement === window.picked")


def test_the_readme_describes_the_new_look():  # what the user reads first
    from pathlib import Path

    readme = " ".join((Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8").split())
    for phrase in ("## Mission Control (your AI office)", "`~/.ai-browser/workspaces.json`", "never deletes its files",
                   "each account's current session and weekly limits, as Claude Code reports them with each request",
                   "the last reading is kept, with its time", "`~/.ai-browser/usage.json`",
                   '"Updates when an agent works"', "under `attachments/`",
                   '"name (2).ext"', "**Brave only**", "**⋯ Options**",
                   "past 12 desks, the oldest finished agents leave the room", "**Ask AI**, in the composer",
                   '"No missions in this workspace"', '"Not sent: attach it again"',
                   "applies to the agents you start next",  # the rulings' results (Task 18, the final review)
                   'After a reconnect, every attached file says "Not sent: attach it again", even one that showed ✓',
                   "the task refuses to start and says which folder",
                   "no Web Search, Web Fetch, browser tools or skills shell",
                   "a command can still reach a site",
                   "On a Mac it asks you first, with a card, every time",
                   "except a command you chose **Always allow** for",
                   "your own tools (Integrations) still run",
                   "scrolling over the office scrolls the page: hold Ctrl or ⌘ (or pinch) to zoom",
                   # the user's look, 2026-10-07: nothing under the globe, Watch beside Hand over, pictures in any chat
                   "Dotted lines run from each desk to the globe's foot",
                   "**Stop**, **Chat**, **Hand over** and **Watch**",
                   "**Watch** brings its tab to the front without opening its drawer",
                   "Its message box takes files as **Build a Mission** does",
                   "their chips go only once the app has placed them",
                   "Paste a picture into the box (⌘V; Ctrl+V on Windows), or drop a file on it",
                   '"Pictures go with Build a Mission or an agent\'s chat"', "Pasted text stays text",
                   "The floating chat's **New task** takes pictures and files the same way",
                   "Cells copied from a spreadsheet paste as text"):
        assert phrase in readme, phrase
    for gone in ("brain of glowing points", "WebGL", "no web tools at all", "a file that was not yet sent",
                 "a command still asks you, with a card, before it reaches a site",
                 "a percentage only when Claude Code reports one", '"Within limits"'):  # the polish's Usage card
        assert gone not in readme, gone
