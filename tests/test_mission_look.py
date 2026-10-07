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
        assert await js("document.querySelector('.heading h2').textContent") == "Your AI Workforce"
        assert await js("document.querySelector('.heading .eyebrow').textContent") == "Mission Control"


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
    for name in ("missions", "templates", "knowledge", "integrations", "history", "dashboard"):
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
    from test_ai_home_phase2 import ask_for_clickup

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
@pytest.mark.parametrize("size", [WIDE, (1280, 760), MIDDLE, NARROW])
async def test_the_list_and_the_calendar_start_below_the_heading_and_the_switch(stack, size):
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
                                " Math.max(bottom('.heading'), bottom('.switch-views'))]; })()")
        assert first >= words, (name, first, words)  # its first row (or its content's top) is below the words over it


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
  const words = ['.heading', '.switch-views', '.sign']
    .map((selector) => [selector, box(document.querySelector(selector))]);
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
async def test_no_step_card_sits_under_the_heading_the_switch_or_the_sign(stack, count, size):  # Task 11's far desks
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
    assert hits == [], hits  # no desk's step card under the heading's words, the switch or the AI OFFICE sign
    assert outside == [], outside  # and every desk, with its card, in view in the room's box


@CHROME
@pytest.mark.parametrize(("count", "size", "least"), [(5, (1280, 760), 0.5), (6, (1280, 760), 0.5), (5, WIDE, 0.6)])
async def test_a_few_desks_fill_the_room_below_the_heading_and_stay_in_view(stack, count, size, least):
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
    assert zoom >= least, zoom  # the room is placed between the heading's band and the box's bottom, not squeezed
    shown, hits, outside = await js(CARDS_UNDER_WORDS)
    assert (shown, hits, outside) == (count, [], [])
