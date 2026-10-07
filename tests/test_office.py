"""Mission Control's office (the new look, Decision 3): the workers (chibi.js) in their hoodies and headphones, the
icons (icons.js), and from Task 11 the room: desks in rings around the globe, step cards, dotted lines, sub-agents,
the empty room, the room's limit and its pause. Against a real app server (agents on the fake claude) in a throwaway
headless Chrome. The art holds no agent data, text stays text, and nothing is downloaded."""

import asyncio
import itertools
import json
import re

import pytest

from ai_browser.chrome import chrome_binary
from test_app_server import wait_for
from test_bridge import EVENTS
from test_bridge_powers import INIT, PLAN, use
from test_home import stack, until  # noqa: F401  (fixtures)
from test_mission import WORKING, open_mission, open_with, station
from test_tab_menu import connected, frame, pick, shell  # noqa: F401  (fixture)

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")


async def front(stack, js):
    """Bring the page to the front: a hidden tab runs no animations."""
    await stack["cdp"].send("Page.bringToFront", session_id=js.session)
    assert await until(js, "document.visibilityState === 'visible'")


async def reduce_motion(stack, js, on=True):
    """The system's Reduce Motion, switched on (or off) in this page, as the user would while it is open."""
    await stack["cdp"].send("Emulation.setEmulatedMedia", {"features": [
        {"name": "prefers-reduced-motion", "value": "reduce" if on else ""}]}, session_id=js.session)


# ---- the workers, in a pose harness: one worker per state ------------------------------------------------------------

POSE_STATES = ["working", "waiting", "needs_you", "your_turn", "failed", "stopped"]
PARTS = ["body", "head", "face", "phones", "blink", "sweat", "arm-l", "arm-r", "arm-up", "arm-thumb", "sparkle"]
POSES = """(async () => {
  const chibi = await import('/chibi.js');
  chibi.ensureDefs(document);
  const box = document.createElement('div');
  box.id = 'poses';
  box.style.cssText = 'position: fixed; left: 0; top: 60px; display: flex; gap: 8px; z-index: 50';
  for (const state of ['working', 'waiting', 'needs_you', 'your_turn', 'failed', 'stopped']) {
    const holder = document.createElement('div');
    holder.style.cssText = 'position: relative; width: 110px; height: 110px';
    holder.style.setProperty('--c', '#4c8df6');
    const pose = document.createElement('div');
    pose.className = 'pose';
    pose.dataset.state = state;
    pose.append(chibi.createWorker('pose-' + state));
    holder.append(pose);
    box.append(holder);
  }
  document.body.append(box);
  window.chibi = chibi;
  return true;
})()"""


def worker(state, part=""):
    return f"document.querySelector('#poses .pose[data-state=\"{state}\"] > .worker {part}'.trim())"


def opacity(state, part):
    return f"getComputedStyle({worker(state, part)}).opacity"


async def poses(stack):
    """Mission Control, in front, with the pose harness (`window.chibi` is the module)."""
    js = await open_with(stack)
    await front(stack, js)
    assert await js(POSES)
    return js


@CHROME
async def test_a_worker_is_made_of_parts_with_no_text_or_pictures(stack):
    js = await poses(stack)
    assert await js("window.chibi.PARTS") == PARTS
    for state in POSE_STATES:
        found = await js(f"[...{worker(state)}.children].map(part => [part.className,"
                         " part.querySelectorAll(':scope > svg').length, part.children.length])")
        assert found == [[f"part {name}", 1, 1] for name in PARTS], state
        assert await js(f"{worker(state)}.textContent") == ""
        assert await js(f"{worker(state)}.querySelectorAll('image, foreignObject, text, use').length") == 0
        assert await js(f"{worker(state)}.getAttribute('aria-hidden')") == "true"
    assert await js(f"{worker('working', '.phones')}.querySelectorAll('ellipse').length") == 2  # the ear cups


@CHROME
async def test_the_id_picks_the_hair_its_colour_and_the_skin(stack):
    js = await poses(stack)
    assert await js("window.chibi.variantOf('a1')") == {"hair": 1, "skin": 1, "colour": 1}
    assert await js("window.chibi.variantOf('a1')") == {"hair": 1, "skin": 1, "colour": 1}  # every time
    seen = await js("Array.from({length: 20}, (_, index) => window.chibi.variantOf('a' + (index + 1)))")
    assert len({(one["hair"], one["skin"]) for one in seen}) == 9 and {one["colour"] for one in seen} == {0, 1, 2}
    made = await js("(() => { const made = window.chibi.createWorker('a7'); return [made.dataset.hair,"
                    " made.dataset.skin, made.dataset.colour]; })()")
    assert made == [str(value) for value in (await js("window.chibi.variantOf('a7')")).values()]
    assert await js(f"{worker('working')}.dataset.colour") == "1"  # pose-working: hair 0, skin 1, colour 1
    assert "mc-hair-1" in await js(f"getComputedStyle({worker('working')}.querySelector('.hair')).fill")


@CHROME
async def test_a_workers_pose_shows_the_agents_state(stack):
    js = await poses(stack)
    shown = {
        "working": {".arm-l": "1", ".arm-r": "1", ".arm-up": "0", ".arm-thumb": "0", ".eyes-open": "1"},
        "needs_you": {".arm-up": "1", ".arm-r": "0", ".mouth-o": "1"},
        "your_turn": {".arm-thumb": "1", ".arm-r": "0", ".eyes-happy": "1"},
        "failed": {".eyes-shut": "1", ".mouth-sad": "1", ".sweat": "1"},
        "stopped": {".eyes-shut": "1"},
    }
    for state, parts in shown.items():
        for part, value in parts.items():
            assert await js(opacity(state, part)) == value, (state, part)
    assert await js(f"getComputedStyle({worker('failed', '.head')}).transform") != "none"
    filters = await js(f"[...{worker('stopped')}.querySelectorAll('.part')].map(part => getComputedStyle(part).filter)")
    assert len(filters) == len(PARTS) and "none" not in filters
    delays = await js(f"getComputedStyle({worker('working', '.blink')}).animationDelay.split(',').map(parseFloat)")
    assert [round(delay, 3) for delay in delays] == [0, -0.2]  # the nod, then the blink: pose-working is hair 0, skin 1
    assert await js(f"getComputedStyle({worker('working', '.shirt')}).fill") == "rgb(76, 141, 246)"  # --c


@CHROME
async def test_the_worker_itself_never_makes_a_stacking_context(stack):
    js = await poses(stack)
    for state in POSE_STATES:
        style = await js(f"(() => {{ const style = getComputedStyle({worker(state)}); return [style.transform,"
                         " style.filter, style.opacity, style.willChange, style.zIndex, style.isolation]; })()")
        assert style == ["none", "none", "1", "auto", "auto", "auto"], state
        layers = await js(f"[...{worker(state)}.children].map(part => getComputedStyle(part).zIndex)")
        assert layers == ["1"] * 6 + ["3"] * 5, state  # behind the desk (layer 2), or in front of it


@CHROME
async def test_only_html_layers_are_animated(stack):
    js = await poses(stack)
    assert await js("document.getAnimations().filter(animation => animation.effect?.target instanceof SVGElement"
                    " && animation.effect.target.closest('.worker')).length") == 0
    assert await js("document.getAnimations().some(animation => animation.effect"
                    " && animation.effect.target.matches('#poses .worker .part'))")


@CHROME
async def test_a_sub_agents_worker_is_smaller_and_an_avatar_is_the_head_alone(stack):
    js = await poses(stack)
    sizes = await js("(() => { const pose = document.querySelector('#poses .pose');"
                     " const small = window.chibi.createWorker('a1', {small: true}); pose.append(small);"
                     " return [small.className, small.offsetWidth, pose.querySelector('.worker').offsetWidth]; })()")
    assert sizes == ["worker small", 42, 70]
    avatar = await js("(() => { const art = window.chibi.createAvatar('a1'); document.body.append(art);"
                      " return [art.getAttribute('class'), art.querySelectorAll('.hair').length > 0,"
                      " art.querySelectorAll('.skin').length > 0, art.textContent,"
                      " art.querySelectorAll('image, foreignObject, text, use').length, art.dataset.colour]; })()")
    assert avatar == ["avatar-art", True, True, "", 0, "1"]


@CHROME
async def test_with_reduced_motion_nothing_moves(stack):
    js = await poses(stack)
    moving = ("document.getAnimations().filter(animation => animation.playState === 'running'"
              " && animation.effect?.target?.closest?.('.worker')).length")
    assert await until(js, f"{moving} > 0")  # the workers move, until the user turns Reduce Motion on
    await reduce_motion(stack, js)
    await asyncio.sleep(1)
    assert await js("document.getAnimations().filter(animation => animation.playState === 'running').length") == 0


@CHROME
async def test_icons_are_built_never_parsed(stack):
    js = await open_with(stack)
    found = await js("import('/icons.js').then(({ icon, BADGE_ICONS }) => { const home = icon('home');"
                     " const odd = icon('no such icon'); return [home.getAttribute('viewBox'),"
                     " home.getAttribute('aria-hidden'), home.querySelectorAll('path').length,"
                     " odd.querySelector('path').getAttribute('d').length > 0, Object.keys(BADGE_ICONS)]; })")
    assert found[:4] == ["0 0 24 24", "true", 1, True]
    assert set(found[4]) >= {"Bash", "Edit", "Write", "Read", "Web Search", "Web Fetch", "Browser Agent", "Sub-agent",
                             "Skill", "Tool"}


# ---- the room (Task 11) ----------------------------------------------------------------------------------------------

ARRIVALS = """(() => {
  Object.assign(window, { spawned: [], sparks: 0, sparksGone: 0, sparksMost: 0, errors: [] });
  addEventListener('error', (event) => window.errors.push(String(event.message)));
  addEventListener('unhandledrejection', (event) => window.errors.push(String(event.reason)));
  const note = (node) => {
    if (node.classList && node.classList.contains('spawning') && !window.spawned.includes(node.dataset.id)) {
      window.spawned.push(node.dataset.id);
    }
  };
  new MutationObserver((records) => {
    for (const record of records) {
      if (record.type === 'attributes') note(record.target);
      for (const node of record.addedNodes) {
        note(node);
        if (node.classList && node.classList.contains('spark')) window.sparks += 1;
      }
      for (const node of record.removedNodes) {
        if (node.classList && node.classList.contains('spark')) window.sparksGone += 1;
      }
    }
    window.sparksMost = Math.max(window.sparksMost, document.querySelectorAll('.spark').length);
  }).observe(document, { subtree: true, childList: true, attributes: true, attributeFilter: ['class'] });
})();
"""
ARTS = ("[...document.querySelectorAll('.station:not(.leaving):not(.away) .desk-art')].map(art => {"
        " const r = art.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; })")
SHOWN = "[...document.querySelectorAll('.station:not(.away):not(.leaving)')].map(node => node.dataset.id)"


def overlapping(rects):
    return [(one, two) for one, two in itertools.combinations(rects, 2)
            if min(one[2], two[2]) - max(one[0], two[0]) > 4 and min(one[3], two[3]) - max(one[1], two[1]) > 4]


async def layouts(stack, js):
    metrics = (await stack["cdp"].send("Performance.getMetrics", session_id=js.session))["metrics"]
    return next(metric["value"] for metric in metrics if metric["name"] == "LayoutCount")


def planned():
    """An agent that keeps a to-do list, opens a page, and starts a sub-agent that runs ls, then stays at work."""
    from ai_browser.app.powers import SUBAGENT_TOOL

    return [INIT, use("t1", "TodoWrite", PLAN), use("u0", "mcp__ai-browser__open", {"url": "https://shop.example/"}),
            use("u1", SUBAGENT_TOOL, {"description": "Research", "prompt": "Look it up"}),
            use("u2", "Bash", {"command": "ls"}, parent="u1"), {"sleep": 30}]


@CHROME
async def test_an_empty_room_says_start_a_mission_below(stack):
    js = await open_mission(stack)
    note = "document.querySelector('.empty-note')"
    assert await js("document.querySelector('.room').dataset.empty") == "true"
    assert await js(f"{note}.textContent") == "Start a mission below"
    assert await js(f"getComputedStyle({note}).display") != "none"
    assert await js("document.getElementById('brain').classList.contains('globe')")
    # the user's hand check: no AI OFFICE sign, no hanging lamp, no big plants (each desk keeps its small one)
    assert await js("document.querySelectorAll('.sign, .lamp, .plant-big').length") == 0
    assert await js("document.querySelectorAll('.globe .map circle').length") > 300  # the dotted continents
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await stack["server"].agents.create("Fix the footer")
    assert await until(js, f"getComputedStyle({note}).display === 'none'")


@CHROME
async def test_desks_stand_in_rings_round_the_globe(stack):  # the spec's scene with 5 agents
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    stack["server"].agents.max_working = 5  # all of them at work, none waiting in line
    for name in ("one", "two", "three", "four", "five"):
        await stack["server"].agents.create(name)
    js = await open_mission(stack)
    assert await until(js, f"{SHOWN}.length === 5")
    places = await js("[...document.querySelectorAll('.station')].map(s => [s.dataset.id, Number(s.dataset.x),"
                      " Number(s.dataset.y)])")
    expected = await js("import('/scene.js').then(scene => [0, 1, 2, 3, 4].map(index => scene.placeOf(index, 5)))")
    assert [[x, y] for _, x, y in sorted(places)] == [[point["x"], point["y"]] for point in expected]
    assert places[0][1] < 1000 < places[1][1]  # the first on the globe's left, the second on its right
    assert await js("document.querySelectorAll('.links path.link:not(.away)').length") == 5
    assert await until(js, "document.querySelectorAll('.links path.live').length === 5")  # working: their dots run
    assert await js("getComputedStyle(document.querySelector('.links path')).strokeDasharray") != "none"


@CHROME
async def test_a_desk_is_220_by_150_with_its_step_card_and_decor(stack):
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await stack["server"].agents.create("Fix the footer")
    js = await open_mission(stack)
    assert await until(js, f"{station('a1')} !== null")
    assert await js(f"[{station('a1', '.desk-art')}.offsetWidth, {station('a1', '.desk-art')}.offsetHeight]") == [
        220, 150]
    assert await js(f"{station('a1', '.step')}.offsetWidth") == 210
    for part in (".chair", ".table", ".laptop .lid", ".mug", ".plant", ".nameplate", ".pose.main .worker"):
        assert await js(f"{station('a1', part)} !== null"), part
    assert await js(f"{station('a1', '.monitor')}.hidden") is True  # no picture of its tab yet


@CHROME
async def test_every_desk_has_a_worker_in_the_agents_colour_and_names_stay_text(stack):
    from test_home import HOSTILE

    js = await open_with(stack)
    agents = stack["server"].agents
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    for name in ("Fix the footer", HOSTILE, "QA my-site.com"):
        await agents.create(name)
    assert await until(js, "document.querySelectorAll('.station').length === 3")
    assert await js("[...document.querySelectorAll('.station')].every(node =>"
                    " node.querySelectorAll('.pose.main > .worker').length === 1)")
    assert await js(f"getComputedStyle({station('a1', '.worker .shirt')}).fill") == "rgb(76, 141, 246)"  # blue
    assert await js(f"getComputedStyle({station('a2', '.worker .shirt')}).fill") == "rgb(63, 178, 107)"  # green
    assert "mc-skin-1" in await js(f"getComputedStyle({station('a1', '.worker .head .skin')}).fill")
    assert await js("(() => { const defs = document.getElementById('mc-defs'); return [defs.querySelectorAll("
                    "'radialGradient, linearGradient').length, getComputedStyle(defs).display !== 'none',"
                    " defs.getAttribute('aria-hidden')]; })()") == [8, True, "true"]
    assert "<img" in await js(f"{station('a2', '.nameplate')}.textContent")
    assert await js("[...document.images].filter(img => !img.closest('.monitor')).length") == 0
    assert await js("document.title") != "pwned"


@CHROME
async def test_the_step_card_shows_the_step_its_timer_and_its_badge(stack):
    stack["script"].write_text(json.dumps([INIT, use("t1", "TodoWrite", PLAN),
                                           use("u1", "Bash", {"command": "npm test"}), {"sleep": 30}]),
                               encoding="utf-8")
    await stack["server"].agents.create("fix the footer")
    js = await open_mission(stack)
    assert await until(js, f"{station('a1', '.step-title')}?.textContent === '2. Fixing the bug'")
    assert await js(f"{station('a1', '.ticker')}.textContent") == "Bash npm test"
    assert await js(f"{station('a1', '.step-badge .badge-text')}.textContent") == "Bash"
    assert await js(f"{station('a1', '.step-badge svg.icon')} !== null")
    first = await js(f"{station('a1', '.timer')}.textContent")
    assert re.fullmatch(r"\d+s", first), first
    await asyncio.sleep(2.2)
    assert int((await js(f"{station('a1', '.timer')}.textContent"))[:-1]) >= int(first[:-1]) + 1  # it ticks
    assert await js(f"{station('a1', '.step')}.dataset.mode") == "full"


@CHROME
async def test_a_done_desk_shows_a_tick_and_the_time_it_took(stack):
    js = await open_mission(stack)
    await stack["server"].agents.create("Fix the footer")  # the stack's script: done, in 2.5 s by Claude Code's clock
    assert await until(js, f"{station('a1')}?.dataset.state === 'your_turn'")
    assert await js(f"getComputedStyle({station('a1', '.step-ring')}, '::before').content") == '"✓"'
    assert await until(js, f"{station('a1', '.timer')}.textContent === '2s'")
    assert await until(js, f"getComputedStyle({station('a1', '.pose.main .worker .arm-thumb')}).opacity === '1'")


@CHROME
async def test_a_desk_that_needs_the_user_raises_a_hand_in_amber(stack, tmp_path):
    from test_ai_home_phase2 import ask_for_clickup

    ask_for_clickup(stack, tmp_path)
    agents = stack["server"].agents
    await agents.create("make a ClickUp task")
    await wait_for(lambda: agents.agents["a1"].permission is not None)
    js = await open_with(stack)
    assert await until(js, f"{station('a1')}?.dataset.state === 'needs_you'")
    assert await until(js, f"getComputedStyle({station('a1', '.pose.main .worker .arm-up')}).opacity === '1'")
    assert await js(f"getComputedStyle({station('a1', '.table .rim')}).stroke") == "rgb(255, 181, 71)"  # --needs
    assert await js(f"getComputedStyle({station('a1', '.badge')}).display") != "none"
    assert await js(f"{station('a1', '.ticker')}.textContent") == "wants clickup: create task"


@CHROME
async def test_a_sub_agent_sits_at_its_parents_desk(stack):
    stack["script"].write_text(json.dumps(planned()), encoding="utf-8")
    agent = await stack["server"].agents.create("fix the footer")
    await wait_for(lambda: bool(agent.subagents) and bool(agent.subagents[0]["action"]))
    js = await open_mission(stack)
    sub = station("a1", ".subs .pose")
    assert await until(js, f"{sub}?.dataset.state === 'working'")
    assert await js(f"{sub}.title") == "Sub-agent: Research · Bash ls"
    assert await js(f"[{sub}.querySelector('.worker').offsetWidth,"
                    f" {station('a1', '.pose.main .worker')}.offsetWidth]") == [42, 70]
    await stack["server"].agents.stop("a1")  # Stop stops its sub-agents
    assert await until(js, f"{sub}?.dataset.state === 'stopped'")


@CHROME
async def test_the_workers_sit_at_the_desk_and_sub_agents_show_over_its_far_edge(stack):
    stack["script"].write_text(json.dumps(planned()), encoding="utf-8")
    await stack["server"].agents.create("fix the footer")
    js = await open_mission(stack)
    assert await until(js, f"{station('a1', '.subs .pose')} !== null")

    def box(part):
        return (f"(() => {{ const r = {station('a1', part)}.getBoundingClientRect();"
                " return [r.left, r.top, r.right, r.bottom]; })()")

    art, worker, sub, table = [await js(box(part)) for part in (".desk-art", ".pose.main .worker",
                                                                 ".subs .worker", ".table")]
    assert art[0] <= worker[0] and worker[2] <= art[2] and art[1] <= worker[1] and worker[3] <= art[3]  # in its desk
    assert worker[3] - art[1] > 0.6 * (art[3] - art[1])  # behind the desk's rim, at any zoom: 0.6 of its art's height
    assert worker[1] < table[1]  # its head above the desk's box
    assert sub[1] < table[1] < sub[3]  # a sub-agent too: its head over the desk's far edge, not wholly behind it


@CHROME
async def test_clicking_a_desk_picks_it(stack):
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    for name in ("one", "two"):
        await stack["server"].agents.create(name)
    js = await open_mission(stack)
    assert await until(js, f"{SHOWN}.length === 2")
    await js(f"{station('a2')}.click(); true")
    assert await until(js, f"{station('a2')}.classList.contains('selected')")
    assert await js(f"{station('a1')}.classList.contains('selected')") is False


@CHROME
async def test_past_twelve_the_oldest_finished_leave_first(stack):  # Review Focus 2
    agents = stack["server"].agents
    js = await open_mission(stack)
    for number in range(14):
        await agents.create(f"Task number {number}")  # the stack's script: each is done at once
    await wait_for(lambda: len(agents.agents) == 14 and all(one.state == "your_turn" for one in agents.agents.values()),
                   30)
    assert await until(js, f"{SHOWN}.length === 12", 10)
    assert sorted(await js(SHOWN), key=lambda one: int(one[1:])) == [f"a{number}" for number in range(3, 15)]
    assert await js("document.querySelectorAll('.station.away').length") == 2  # out of the room, still there
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await agents.create("keep working")
    assert await until(js, f"{SHOWN}.includes('a15') && !{SHOWN}.includes('a3') && {SHOWN}.length === 12")


ROOM_ROWS = """import('/step.js').then(({ roomAgents }) => {
  const some = (count, state, from) => Array.from({ length: count }, (_, index) => ({
    id: `${state}${index}`, state, created: from + index }));
  const kept = (agents) => roomAgents(agents).map((agent) => agent.id);
  return [kept(some(3, 'your_turn', 0)), kept(some(7, 'your_turn', 0)), kept(some(12, 'your_turn', 0)),
          kept([...some(5, 'working', 0), ...some(5, 'your_turn', 100)]),
          kept([...some(5, 'working', 0), ...some(9, 'your_turn', 100)]), kept(some(14, 'working', 0)),
          kept([...some(14, 'working', 0), ...some(3, 'failed', 100)])];
})"""


@CHROME
async def test_the_room_keeps_every_desk_it_has_room_for(stack):  # roomAgents' limit, in plain data
    js = await open_mission(stack)
    three, seven, twelve, five_and_five, five_and_nine, fourteen, over = await js(ROOM_ROWS)
    assert [len(three), len(seven), len(twelve)] == [3, 7, 12]  # fewer finished than desks: all of them stay
    assert len(five_and_five) == 10  # 5 at work and 5 done, in a room for 12
    assert five_and_nine == ([f"working{number}" for number in range(5)]  # the newest 7 of the 9 done stay
                             + [f"your_turn{number}" for number in range(2, 9)])
    assert len(fourteen) == 14 and over == fourteen  # every agent at work keeps its desk, however many


@CHROME
async def test_twenty_agents_with_sub_agents_keep_the_room_readable_and_fast(stack):  # Review Focus 2
    stack["script"].write_text(json.dumps(planned()), encoding="utf-8")
    stack["server"].agents.max_working = 20  # all of them at work at once, none waiting in line
    for number in range(20):
        await stack["server"].agents.create(f"Task number {number}")
    js = await open_with(stack, size=(1280, 760))
    await front(stack, js)
    assert await until(js, "document.querySelectorAll('.station[data-state=\"working\"]:not(.away)').length === 20",
                       15)
    assert await until(js, "document.querySelectorAll('.station .subs .pose').length === 20", 15)
    await asyncio.sleep(1.5)  # every desk in its place
    assert await js("document.querySelectorAll('.step[data-mode=\"chip\"]').length") == 20
    desks = await js(ARTS)
    assert overlapping(desks) == []
    assert all(desk[0] >= 0 and desk[2] <= 1280 and desk[1] >= 0 and desk[3] <= 760 for desk in desks), desks
    await stack["cdp"].send("Performance.enable", session_id=js.session)
    before = await layouts(stack, js)
    await asyncio.sleep(2)
    assert await layouts(stack, js) - before < 10  # open all day: its animations and timers barely lay out


NAMES_UNDER_CARDS = """(() => {
  const area = (r) => Math.max(0, r.right - r.left) * Math.max(0, r.bottom - r.top);
  const desks = [...document.querySelectorAll('.station:not(.away):not(.leaving)')].map((node) => ({
    id: node.dataset.id, y: Number(node.dataset.y), step: node.querySelector('.step').getBoundingClientRect(),
    name: node.querySelector('.nameplate').getBoundingClientRect() }));
  const covered = [];
  for (const near of desks) {
    for (const far of desks) {
      if (near.y <= far.y) continue; // `near` stands nearer the user: its card is drawn over the desk behind it
      const wide = Math.min(near.step.right, far.name.right) - Math.max(near.step.left, far.name.left);
      const high = Math.min(near.step.bottom, far.name.bottom) - Math.max(near.step.top, far.name.top);
      const share = Math.max(0, wide) * Math.max(0, high) / area(far.name);
      if (share > 0) covered.push([near.id, far.id, share]); // not rounded: a sliver counts
    }
  }
  return [desks.length, covered];
})()"""


@CHROME
@pytest.mark.parametrize(("count", "size", "most"), [
    (5, (1280, 760), 0), (6, (1280, 760), 0), (5, (1440, 960), 0), (6, (1440, 960), 0), (12, (1280, 760), 0.5),
    (16, (1280, 760), 0.5), (20, (1280, 760), 0.5), (20, (1024, 700), 0.5)])
async def test_no_step_card_hides_the_name_of_a_desk_behind_it(stack, count, size, most):  # review: rings 1 and 2
    stack["script"].write_text(json.dumps(planned()), encoding="utf-8")
    stack["server"].agents.max_working = count  # all of them at work at once, none waiting in line
    for number in range(count):
        await stack["server"].agents.create(f"Task number {number}")
    js = await open_with(stack, size=size)
    await front(stack, js)
    working = "document.querySelectorAll('.station[data-state=\"working\"]:not(.away)').length"
    assert await until(js, f"{working} === {count}", 15)
    await asyncio.sleep(1.5)  # every desk in its place
    shown, covered = await js(NAMES_UNDER_CARDS)
    assert shown == count
    # a full card (5 and 6 desks) hides no part of a nameplate behind it; a chip (12 to 20) at most half of one
    assert [one for one in covered if one[2] > most] == [], covered
    assert await js("document.querySelectorAll('.step[data-mode=\"chip\"]').length") == (count if count > 6 else 0)
    desks = await js(ARTS)  # and the desks themselves: none over another, all in the window
    assert overlapping(desks) == []
    assert all(desk[0] >= 0 and desk[2] <= size[0] and desk[1] >= 0 and desk[3] <= size[1] for desk in desks), desks


@CHROME
async def test_long_words_clip_on_the_step_card_with_a_tooltip(stack):  # Review Focus 1
    step = "Read every page of the site and " + "check each link " * 20
    todos = {"todos": [{"content": step, "status": "in_progress", "activeForm": step}]}
    stack["script"].write_text(json.dumps([INIT, use("t1", "TodoWrite", todos),
                                           use("u1", "Bash", {"command": "echo " + "x" * 2000}), {"sleep": 30}]),
                               encoding="utf-8")
    await stack["server"].agents.create("a" * 2000)
    js = await open_mission(stack)
    title = station("a1", ".step-title")
    assert await until(js, f"{title}?.textContent.startsWith('1. Read every page')")
    assert await js(f"{station('a1', '.step')}.offsetWidth") == 210  # the card keeps its size
    for part in (".step-title", ".ticker", ".nameplate"):
        node = station("a1", part)
        assert await js(f"{node}.scrollWidth > {node}.clientWidth"), part  # clipped, with an ellipsis
        assert await js(f"{node}.title === {node}.textContent"), part  # and the whole words as a tooltip
    assert (await js(f"{station('a1', '.ticker')}.title")).startswith("Bash echo xxx")


@CHROME
async def test_the_room_pauses_while_its_tab_is_hidden(shell):  # the spec's performance line
    js, stack = shell
    await pick(js, "/mission")
    assert await until(js, connected("/mission"))
    stack["script"].write_text(json.dumps([INIT, use("u1", "Bash", {"command": "ls"}), {"sleep": 30}]),
                               encoding="utf-8")  # at work on a step: its timer ticks
    await stack["server"].agents.create("keep working")
    page = frame("/mission")
    running = f"{page}.document.getAnimations().filter((one) => one.playState === 'running').length"
    assert await until(js, f"{page}.document.querySelector('.station[data-state=\"working\"]') !== null"
                           f" && {running} > 0")
    await pick(js, "/home")
    assert await until(js, f"{page}.document.documentElement.classList.contains('paused')")
    assert await until(js, f"{running} === 0")
    timer = f"{page}.document.querySelector('.station .timer').textContent"
    before = await js(timer)
    assert before.endswith("s")
    await asyncio.sleep(2.2)
    assert await js(timer) == before  # its timers wait too
    await pick(js, "/mission")
    assert await until(js, f"!{page}.document.documentElement.classList.contains('paused') && {running} > 0")


@CHROME
async def test_agents_already_there_simply_appear(stack):
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    for name in ("one", "two", "three"):
        await stack["server"].agents.create(name)
    js = await open_with(stack, ARRIVALS)
    await front(stack, js)
    assert await until(js, "document.querySelectorAll('.station').length === 3")
    await asyncio.sleep(1.5)
    assert await js("[window.spawned, window.sparks]") == [[], 0]
    await stack["server"].agents.create("four")  # created while the page is open: only this one arrives
    assert await until(js, "window.spawned.length === 1")
    assert await js("window.spawned") == ["a4"]


@CHROME
async def test_a_new_agent_arrives_with_a_spark(stack):
    js = await open_with(stack, ARRIVALS)
    await front(stack, js)
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await stack["server"].agents.create("Fix the footer")
    assert await until(js, "window.spawned.includes('a1')")
    assert await until(js, "window.sparks === 1 && window.sparksGone === 1", 3)
    assert await until(js, f"!{station('a1')}.classList.contains('spawning')", 3)
    assert await js("window.errors") == []


@CHROME
async def test_with_reduced_motion_a_new_agent_simply_appears(stack):
    js = await open_with(stack, ARRIVALS)
    await front(stack, js)
    await reduce_motion(stack, js)
    await asyncio.sleep(0.5)
    await stack["server"].agents.create("Fix the footer")
    assert await until(js, f"{station('a1')} !== null")
    await asyncio.sleep(0.5)
    assert await js("[window.spawned, window.sparks]") == [[], 0]


@CHROME
async def test_many_new_agents_at_once_fly_at_most_six_sparks(stack):
    js = await open_with(stack, ARRIVALS)
    await front(stack, js)
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    for number in range(8):
        await stack["server"].agents.create(f"Task number {number}")
    await stack["server"].agents.close("a2")  # closed while it arrives
    assert await until(js, "document.querySelectorAll('.station:not(.leaving)').length === 7")
    assert await until(js, "window.sparks > 0 && window.sparksGone === window.sparks", 4)
    assert await js("window.sparksMost") <= 6
    assert len(await js("window.spawned")) >= 7  # every new desk played its arrival, with or without a spark
    assert await until(js, "document.querySelectorAll('.spawning').length === 0", 3)
    assert await js("window.errors") == []


@CHROME
async def test_with_reduced_motion_the_room_stands_still(stack):
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    for name in ("one", "two", "three"):
        await stack["server"].agents.create(name)
    js = await open_with(stack)
    await front(stack, js)
    assert await until(js, "document.querySelectorAll('.station[data-state=\"working\"]').length === 3")
    running = "document.getAnimations().filter(animation => animation.playState === 'running').length"
    assert await until(js, f"{running} > 0")
    await reduce_motion(stack, js)
    await asyncio.sleep(1)
    assert await js(running) == 0


PERF_ROOM = """(async () => {
  // PERF_ROOM: 20 working stand-in desks in a second room over Mission Control, for DevTools' Performance panel.
  // They are only drawn: nothing is sent to the app, and a reload removes them.
  const { createScene } = await import('/scene.js');
  const root = document.createElement('div');
  root.className = 'scene';
  root.id = 'perf-room';
  document.body.append(root);
  const room = createScene(root);
  const colors = ['blue', 'green', 'cyan', 'pink', 'yellow', 'red', 'grey'];
  for (let index = 1; index <= 20; index += 1) {
    room.upsert({ id: `p${index}`, name: `Stand-in ${index}`, state: 'working', color: colors[index % colors.length],
                  created: index });
  }
  return document.querySelectorAll('#perf-room .station:not(.away)').length;
})()"""


@CHROME
async def test_perf_room_adds_twenty_working_stand_ins(stack):
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await stack["server"].agents.create("Fix the footer")
    js = await open_with(stack)
    assert await until(js, "document.querySelectorAll('#scene .station').length === 1")
    assert await js(PERF_ROOM) == 20
    assert await js("[...document.querySelectorAll('#perf-room .station')].every(node => node.dataset.state"
                    " === 'working' && node.querySelectorAll('.pose.main > .worker').length === 1)")
    assert await js("document.querySelectorAll('#scene .station').length") == 1  # the page's own room is as it was
    assert len(stack["server"].agents.agents) == 1  # nothing was sent
