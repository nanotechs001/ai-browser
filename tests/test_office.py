"""Mission Control's office (the new look, Decision 3): the workers (chibi.js) in their hoodies and headphones, the
icons (icons.js), and from Task 11 the room: desks in rings around the globe, step cards, dotted lines, sub-agents,
the empty room, the room's limit and its pause. Against a real app server (agents on the fake claude) in a throwaway
headless Chrome. The art holds no agent data, text stays text, and nothing is downloaded."""

import asyncio
import json

import pytest

from ai_browser.chrome import chrome_binary
from test_home import stack, until  # noqa: F401  (fixtures)
from test_mission import open_with

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
