"""Mission Control's visuals: the Brain as a brain of glowing points (brainshape.js, blob.js) and a chibi office worker
at every station (chibi.js), against a real app server (agents on the fake claude) in a throwaway headless AI Browser.
The art holds no agent data, text stays text, and nothing is downloaded."""

import asyncio
import base64
import json
import os
from pathlib import Path

import pytest

from test_home import HOSTILE, stack, until  # noqa: F401  (fixtures)
from test_mission import CHROME, WORKING, key, needs_reply, open_mission, open_with, station, voice_on


async def shape(stack, body):
    """Runs `body` (statements ending in a return) in Mission Control, with brainshape.js imported as `shape`."""
    js = await open_mission(stack)
    return await js(f"(async () => {{ const shape = await import('/brainshape.js'); {body} }})()")


# ---- brainshape.js ---------------------------------------------------------------------------------------------------

SUM = ("const sum = (array) => { let total = 0; for (let index = 0; index < array.length; index += 1)"
       " total = (total * 31 + Math.round(array[index] * 1e6)) % 1000000007; return total; };")


@CHROME
async def test_one_seed_always_gives_the_same_brain(stack):
    length, one, two, other = await shape(stack, SUM + "const points = shape.brainPoints(8000, 7);"
                                          " return [points.length, sum(points), sum(shape.brainPoints(8000, 7)),"
                                          " sum(shape.brainPoints(8000, 8))];")
    assert length == 48000 and one == two and one != other


@CHROME
async def test_the_brain_mixes_its_parts_exactly(stack):
    kinds, kind = await shape(stack, "const points = shape.brainPoints(8000, 7); const kinds = [0, 0, 0, 0];"
                                     " for (let index = 3; index < points.length; index += 6)"
                                     "  kinds[points[index]] += 1;"
                                     " return [kinds, shape.KIND];")
    assert kinds == [6400, 880, 400, 320]
    assert kind == {"cortex": 0, "cerebellum": 1, "stem": 2, "core": 3}


@CHROME
async def test_every_point_is_inside_the_brains_bounds(stack):
    outside = await shape(stack, "const points = shape.brainPoints(8000, 7); let outside = 0;"
                                 " for (let index = 0; index < points.length; index += 6) {"
                                 "  const [x, y, z, , fold, phase] = points.slice(index, index + 6);"
                                 "  if (!(Math.abs(x) <= 0.7 && y >= -0.85 && y <= 0.6 && Math.abs(z) <= 0.75"
                                 "        && fold >= 0 && fold <= 1 && phase >= 0 && phase <= 1)) outside += 1; }"
                                 " return outside;")
    assert outside == 0


@CHROME
async def test_the_hemispheres_have_a_gap_and_match(stack):
    closest, left, right = await shape(stack, "const points = shape.brainPoints(8000, 7);"
                                              " let closest = 1, left = 0, right = 0;"
                                              " for (let index = 0; index < points.length; index += 6) {"
                                              "  if (points[index + 3] !== shape.KIND.cortex) continue;"
                                              "  closest = Math.min(closest, Math.abs(points[index]));"
                                              "  if (points[index] > 0) left += 1; else right += 1; }"
                                              " return [closest, left, right];")
    assert closest >= 0.02
    assert abs(left - right) <= 0.1 * max(left, right), (left, right)


@CHROME
async def test_the_stem_and_cerebellum_sit_below_and_behind(stack):
    wrong = await shape(stack, "const points = shape.brainPoints(8000, 7); const wrong = { stem: 0, cerebellum: 0 };"
                               " for (let index = 0; index < points.length; index += 6) {"
                               "  const [x, y, z, kind] = points.slice(index, index + 4);"
                               "  if (kind === shape.KIND.stem && !(y <= -0.17 && Math.abs(x) < 0.15)) wrong.stem += 1;"
                               "  if (kind === shape.KIND.cerebellum && !(z < -0.2 && y < -0.1))"
                               "   wrong.cerebellum += 1; }"
                               " return wrong;")
    assert wrong == {"stem": 0, "cerebellum": 0}


@CHROME
async def test_any_first_points_are_an_even_sample(stack):
    kinds, left, right = await shape(stack, "const points = shape.brainPoints(8000, 7); const kinds = [0, 0, 0, 0];"
                                            " let left = 0, right = 0;"
                                            " for (let index = 0; index < 2000 * 6; index += 6) {"
                                            "  kinds[points[index + 3]] += 1;"
                                            "  if (points[index + 3] === 0) { if (points[index] > 0) left += 1;"
                                            "   else right += 1; } }"
                                            " return [kinds, left, right];")
    for count, share in zip(kinds, (0.80, 0.11, 0.05, 0.04)):
        assert abs(count / 2000 - share) <= 0.03, kinds
    assert abs(left - right) <= 0.15 * max(left, right), (left, right)


@CHROME
async def test_synapses_link_near_cortex_points(stack):
    links, typed, cortex, lengths, same = await shape(stack, (
        "const points = shape.brainPoints(8000, 7); const pairs = shape.synapses(points);"
        " let cortex = true, lengths = true;"
        " for (let index = 0; index < pairs.length; index += 2) {"
        "  const one = pairs[index], two = pairs[index + 1];"
        "  if (one >= 8000 || two >= 8000 || points[one * 6 + 3] !== 0 || points[two * 6 + 3] !== 0) cortex = false;"
        "  const length = Math.hypot(points[one * 6] - points[two * 6], points[one * 6 + 1] - points[two * 6 + 1],"
        "                            points[one * 6 + 2] - points[two * 6 + 2]);"
        "  if (length < 0.06 || length > 0.22) lengths = false; }"
        " const again = shape.synapses(shape.brainPoints(8000, 7));"
        " return [pairs.length / 2, pairs instanceof Uint16Array, cortex, lengths,"
        "         again.length === pairs.length && again.every((value, index) => value === pairs[index])];"))
    assert 0 < links <= 900 and typed and cortex and lengths and same


# ---- the Brain: hooks injected before the page's own scripts, and helpers --------------------------------------------

GL = """(() => {
  const gl = window.gl = { last: {}, max: {}, cloud: 0, contexts: 0, gpu: [], timing: 0, t0: 0 };
  const proto = WebGLRenderingContext.prototype;
  const names = new WeakMap();
  const locate = proto.getUniformLocation;
  proto.getUniformLocation = function (program, name) {
    const location = locate.call(this, program, name);
    if (location) names.set(location, name);
    return location;
  };
  for (const method of ['uniform1f', 'uniform2f', 'uniform2fv', 'uniform4fv']) {
    const real = proto[method];
    proto[method] = function (location, ...values) {
      const name = location && names.get(location);
      if (name) {
        const value = method === 'uniform1f' ? values[0] : method === 'uniform2f' ? values.slice(0, 2)
          : Array.from(values[0]);
        gl.last[name] = value;
        if (typeof value === 'number') gl.max[name] = Math.max(gl.max[name] ?? -Infinity, value);
      }
      return real.call(this, location, ...values);
    };
  }
  const drawArrays = proto.drawArrays;
  proto.drawArrays = function (mode, first, count) {
    if (gl.timing > 0 && !gl.t0) gl.t0 = performance.now();
    const result = drawArrays.call(this, mode, first, count);
    if (mode === this.POINTS && count >= 1000) {
      gl.cloud += 1;
      if (gl.timing > 0 && gl.t0) { // the Brain's GPU time: from the frame's first draw to a pixel read after its cloud
        this.readPixels(0, 0, 1, 1, this.RGBA, this.UNSIGNED_BYTE, new Uint8Array(4));
        gl.gpu.push(performance.now() - gl.t0);
        gl.t0 = 0;
        gl.timing -= 1;
      }
    }
    return result;
  };
  const contexts = new Set();
  const getContext = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (kind, ...rest) {
    const context = getContext.call(this, kind, ...rest);
    if (context && /webgl/.test(String(kind))) {
      contexts.add(context);
      gl.contexts = contexts.size;
    }
    return context;
  };
})();
"""
STATES = """(() => {
  window.states = [];
  new MutationObserver((records) => {
    for (const record of records) {
      const node = record.target;
      if (node.classList && node.classList.contains('stage') && node.dataset.state !== window.states.at(-1)) {
        window.states.push(node.dataset.state);
      }
    }
  }).observe(document, { subtree: true, attributes: true, attributeFilter: ['data-state'] });
})();
"""
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
HOOKS = GL + STATES + ARRIVALS


async def front(stack, js):
    """Bring the page to the front: a hidden tab runs no animations and no requestAnimationFrame."""
    await stack["cdp"].send("Page.bringToFront", session_id=js.session)
    assert await until(js, "document.visibilityState === 'visible'")


async def brain_page(stack, extra="", size=None, points=True):
    """Mission Control with the hooks (and `extra`, also run before the page's scripts), in front, and (with `points`)
    its Brain's points made."""
    js = await open_with(stack, HOOKS + extra, size)
    await front(stack, js)
    if points:
        assert await until(js, "document.querySelector('.stage').dataset.points === '8000'", 5)
    return js


def near(name, values, within):
    """True once the last value given to the uniform `name` is within `within` of `values`."""
    return (f"(() => {{ const value = window.gl.last[{json.dumps(name)}]; const want = {json.dumps(values)};"
            " return Array.isArray(value) && value.length === want.length"
            f" && value.every((one, index) => Math.abs(one - want[index]) <= {within}); }})()")


async def reduce_motion(stack, js, on=True):
    """The system's Reduce Motion, switched on (or off) in this page, as the user would while it is open."""
    await stack["cdp"].send("Emulation.setEmulatedMedia", {"features": [
        {"name": "prefers-reduced-motion", "value": "reduce" if on else ""}]}, session_id=js.session)


# ---- the Brain -------------------------------------------------------------------------------------------------------

@CHROME
async def test_the_brain_is_drawn_with_points_once_they_are_made(stack):
    js = await open_with(stack, HOOKS)
    await front(stack, js)
    stage = "document.querySelector('.stage')"
    assert await js(f"{stage}.dataset.mode") == "webgl"
    assert await until(js, f"{stage}.dataset.points === '8000'", 3)
    assert await until(js, "getComputedStyle(document.querySelector('.stage .orb')).display === 'none'"
                           " && getComputedStyle(document.querySelector('.stage canvas')).display !== 'none'", 2)
    assert await js("window.gl.cloud") > 0
    await js("document.querySelector('.stage canvas').getContext('webgl').getExtension('WEBGL_lose_context')"
             ".loseContext(); true")
    assert await until(js, f"{stage}.dataset.mode === 'css' && {stage}.dataset.points === undefined")  # fallback()


@CHROME
async def test_a_brain_opened_with_reduce_motion_on_is_drawn_once(stack):
    js = await brain_page(stack, points=False)
    await reduce_motion(stack, js)  # on before the page loads again: the Brain never moves
    await js("window.before = true; location.reload(); true")
    assert await until(js, "window.before === undefined"
                           " && document.getElementById('status')?.dataset.state === 'connected'")
    assert await js("matchMedia('(prefers-reduced-motion: reduce)').matches")
    assert await until(js, "document.querySelector('.stage').dataset.points === '8000'"
                           " && getComputedStyle(document.querySelector('.stage canvas')).display !== 'none'", 5)
    await asyncio.sleep(0.5)  # the page's first messages are in
    drawn = await js("window.gl.cloud")
    await asyncio.sleep(1)
    assert drawn >= 1 and await js("window.gl.cloud") == drawn  # drawn once its points were ready, then still


@CHROME
async def test_a_context_lost_before_the_points_leaves_the_dotted_brain(stack):
    lose = ("(() => { const real = HTMLCanvasElement.prototype.getContext;"
            " HTMLCanvasElement.prototype.getContext = function (kind, ...rest) {"
            "  const context = real.call(this, kind, ...rest);"
            "  if (context && /webgl/.test(kind) && !this.lost) { this.lost = true;"
            "   setTimeout(() => context.getExtension('WEBGL_lose_context').loseContext(), 0); }"
            "  return context; }; })();")
    js = await brain_page(stack, lose, points=False)
    stage = "document.querySelector('.stage')"
    assert await until(js, f"{stage}.dataset.mode === 'css'")
    await asyncio.sleep(1.5)  # long after the points would have been made
    assert await js(f"{stage}.dataset.points") is None
    assert await js("getComputedStyle(document.querySelector('.stage .orb')).display") != "none"
    assert await js("getComputedStyle(document.querySelector('.stage canvas')).display") == "none"
    assert await js("[window.errors, window.gl.cloud]") == [[], 0]


@CHROME
async def test_the_brain_draws_at_most_30_frames_a_second(stack):
    js = await brain_page(stack)
    before = await js("window.gl.cloud")
    await asyncio.sleep(2)
    drawn = await js("window.gl.cloud") - before
    assert 20 <= drawn <= 62, drawn


@CHROME
async def test_the_brain_blends_its_states(stack):
    js = await brain_page(stack, points=False)
    brain = stack["brain"]
    brain.broadcast({"type": "brain_activity", "busy": True, "what": "Sorting 2 new messages from Gmail"})
    assert await until(js, near("u_mix", [0, 1, 0, 0], 0.05))
    needs_reply(brain)
    brain.broadcast({"type": "brain_activity", "busy": False, "what": ""})
    assert await until(js, near("u_mix", [0, 0, 1, 0], 0.05))
    brain.done("gmail:t1")
    assert await until(js, near("u_mix", [1, 0, 0, 0], 0.05))


@CHROME
async def test_twenty_agents_share_one_webgl_context(stack):
    js = await brain_page(stack, points=False)
    for number in range(20):
        await stack["server"].agents.create(f"Task number {number}")
    assert await until(js, "document.querySelectorAll('.station').length === 20")
    await asyncio.sleep(1)
    assert await js("window.gl.contexts") == 1


@CHROME
async def test_with_reduced_motion_the_brain_is_still(stack):
    js = await brain_page(stack)
    await reduce_motion(stack, js)
    await asyncio.sleep(1.5)
    before = await js("window.gl.cloud")
    await asyncio.sleep(1)
    assert await js("window.gl.cloud") == before  # still: nothing is drawn
    stack["brain"].broadcast({"type": "brain_activity", "busy": True, "what": "Sorting 2 new messages from Gmail"})
    assert await until(js, "document.querySelector('.stage').dataset.state === 'thinking'")
    assert await until(js, f"window.gl.cloud > {before}")  # a change of state: a short colour fade
    await asyncio.sleep(2)
    settled = await js("window.gl.cloud")
    await asyncio.sleep(1)
    assert await js("window.gl.cloud") == settled  # still again
    assert await js("window.gl.last.u_mix") == [0, 1, 0, 0]  # landed exactly on the state
    stack["brain"].broadcast({"type": "brain_activity", "busy": True, "what": "Drafting a reply to Maria"})
    assert await until(js, "document.getElementById('brain-what').textContent === 'Drafting a reply to Maria'")
    await asyncio.sleep(1)
    assert await js("window.gl.cloud") == settled  # news in the same state isn't a change: nothing is drawn


SLOW_FRAMES = ("(() => { const real = window.requestAnimationFrame.bind(window);"
               " window.requestAnimationFrame = (callback) => real(() => setTimeout(() => callback(performance.now()),"
               " 80)); })();")


@CHROME
async def test_a_slow_machine_draws_fewer_points(stack):
    js = await open_with(stack, HOOKS + SLOW_FRAMES)  # every frame 80 ms late
    await front(stack, js)
    points = "document.querySelector('.stage').dataset.points"
    assert await until(js, f"{points} === '2500'", 10)
    await asyncio.sleep(3)
    assert await js(points) == "2500"  # never below


@CHROME
async def test_a_fast_machine_keeps_every_point(stack):
    js = await brain_page(stack)
    for _ in range(4):
        await asyncio.sleep(1)
        assert await js("document.querySelector('.stage').dataset.points") == "8000"


@CHROME
async def test_a_tab_hidden_for_a_while_keeps_every_point(stack):
    js = await brain_page(stack)
    cdp = stack["cdp"]
    other = (await cdp.send("Target.createTarget", {"url": "about:blank"}))["targetId"]
    session = (await cdp.send("Target.attachToTarget", {"targetId": other, "flatten": True}))["sessionId"]
    await cdp.send("Page.bringToFront", session_id=session)
    assert await until(js, "document.visibilityState === 'hidden'")
    await asyncio.sleep(3)  # no frames while hidden: a long gap, not a slow machine
    await front(stack, js)
    for _ in range(4):
        await asyncio.sleep(1)
        assert await js("document.querySelector('.stage').dataset.points") == "8000"


NO_WEBGL = ("const real = HTMLCanvasElement.prototype.getContext;"
            "HTMLCanvasElement.prototype.getContext = function (kind, ...rest) {"
            "  return /webgl/.test(kind) ? null : real.call(this, kind, ...rest); };")


@CHROME
async def test_without_webgl_the_orb_is_a_dotted_brain(stack):
    js = await open_with(stack, NO_WEBGL)
    stage = "document.querySelector('.stage')"
    assert await until(js, f"{stage}.dataset.mode === 'css'")
    assert await js("getComputedStyle(document.querySelector('.stage .orb')).display") != "none"
    mask = await js("(() => { const style = getComputedStyle(document.querySelector('.stage .orb'), '::before');"
                    " return style.maskImage || style.webkitMaskImage; })()")
    assert mask and mask != "none"
    assert await js(f"{stage}.dataset.points") is None


# ---- the workers, in a pose harness: one worker per state in a test container ----------------------------------------

POSE_STATES = ["working", "waiting", "needs_you", "your_turn", "failed", "stopped"]
PARTS = ["body", "head", "face", "blink", "sweat", "arm-l", "arm-r", "arm-up", "arm-thumb", "sparkle"]
POSES = """(async () => {
  const chibi = await import('/chibi.js');
  chibi.ensureDefs(document);
  const box = document.createElement('div');
  box.id = 'poses';
  box.style.cssText = 'position: fixed; left: 0; top: 60px; display: flex; gap: 8px; z-index: 5';
  for (const state of ['working', 'waiting', 'needs_you', 'your_turn', 'failed', 'stopped']) {
    const station = document.createElement('div');
    station.className = 'station';
    station.dataset.state = state;
    station.style.setProperty('--c', '#4c8df6');
    const card = document.createElement('div');
    card.className = 'card';
    card.append(chibi.createWorker('pose-' + state));
    station.append(card);
    box.append(station);
  }
  document.body.append(box);
  window.chibi = chibi;
  return true;
})()"""


def worker(state, part=""):
    return f"document.querySelector('#poses .station[data-state=\"{state}\"] .worker {part}'.trim())"


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


@CHROME
async def test_the_id_picks_the_hair_and_the_skin(stack):
    js = await poses(stack)
    assert await js("window.chibi.variantOf('a1')") == {"hair": 1, "skin": 1}
    assert await js("window.chibi.variantOf('a1')") == {"hair": 1, "skin": 1}  # every time
    assert await js("new Set(Array.from({length: 20}, (_, index) => {"
                    " const variant = window.chibi.variantOf('a' + (index + 1));"
                    " return variant.hair + '-' + variant.skin; })).size") == 9
    made, wanted = await js("(() => { const made = window.chibi.createWorker('a7');"
                            " const variant = window.chibi.variantOf('a7');"
                            " return [[made.dataset.hair, made.dataset.skin], [String(variant.hair),"
                            " String(variant.skin)]]; })()")
    assert made == wanted


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


@CHROME
async def test_the_worker_itself_never_makes_a_stacking_context(stack):
    js = await poses(stack)
    for state in POSE_STATES:
        style = await js(f"(() => {{ const style = getComputedStyle({worker(state)}); return [style.transform,"
                         " style.filter, style.opacity, style.willChange, style.zIndex, style.isolation]; })()")
        assert style == ["none", "none", "1", "auto", "auto", "auto"], state
        layers = await js(f"[...{worker(state)}.children].map(part => getComputedStyle(part).zIndex)")
        assert layers == ["1"] * 5 + ["3"] * 5, state  # behind the desk (layer 2), or in front of it


@CHROME
async def test_only_html_layers_are_animated(stack):
    js = await poses(stack)
    assert await js("document.getAnimations().filter(animation => animation.effect"
                    " && animation.effect.target instanceof SVGElement).length") == 0
    assert await js("document.getAnimations().some(animation => animation.effect"
                    " && animation.effect.target.matches('#poses .worker .part'))")


@CHROME
async def test_with_reduced_motion_nothing_moves(stack):
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    for name in ("one", "two", "three"):
        await stack["server"].agents.create(name)
    js = await open_with(stack)
    await front(stack, js)
    assert await until(js, "document.querySelectorAll('.station[data-state=\"working\"]').length === 3")
    assert await js(POSES)
    moving = ("document.getAnimations().filter(animation => animation.playState === 'running'"
              " && animation.effect?.target?.closest?.('.worker')).length")
    assert await until(js, f"{moving} > 0")  # the workers move, until the user turns Reduce Motion on
    await reduce_motion(stack, js)
    await asyncio.sleep(1)
    assert await js("document.getAnimations().filter(animation => animation.playState === 'running').length") == 0


# ---- the workers, in the room ----------------------------------------------------------------------------------------

async def wait_for_permissions(agents, ids):
    """Until each of these agents (on the fake claude's ClickUp request) waits for the user's answer."""
    for _ in range(80):
        if all(agents.agents[agent_id].permission for agent_id in ids if agent_id in agents.agents):
            return
        await asyncio.sleep(0.1)


@CHROME
async def test_every_station_has_a_worker_with_the_agents_tie(stack):
    js = await open_with(stack)
    agents = stack["server"].agents
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    for name in ("Fix the footer", HOSTILE, "QA my-site.com"):
        await agents.create(name)
    assert await until(js, "document.querySelectorAll('.station').length === 3")
    assert await js("[...document.querySelectorAll('.station')].every(node => node.querySelectorAll('.worker').length"
                    " === 1)")
    assert await js(f"getComputedStyle({station('a1', '.worker .tie')}).fill") == "rgb(76, 141, 246)"  # blue
    assert await js(f"getComputedStyle({station('a2', '.worker .tie')}).fill") == "rgb(63, 178, 107)"  # green
    assert await js(f"[{station('a1', '.worker')}.dataset.hair, {station('a1', '.worker')}.dataset.skin]") == ["1", "1"]
    assert "mc-skin-1" in await js(f"getComputedStyle({station('a1', '.worker .head .skin')}).fill")  # from data-skin
    assert await js("(() => { const defs = document.getElementById('mc-defs'); return [defs.querySelectorAll("
                    "'radialGradient, linearGradient').length, getComputedStyle(defs).display !== 'none',"
                    " defs.getAttribute('aria-hidden')]; })()") == [7, True, "true"]  # once, and never undisplayed
    assert "<img" in await js(f"{station('a2', '.nameplate')}.textContent")
    assert await js("[...document.images].filter(img => !img.closest('.monitor')).length") == 0
    assert await js("document.title") != "pwned"


@CHROME
async def test_a_station_is_a_200_by_156_desk(stack):
    js = await open_with(stack)
    await stack["server"].agents.create("Fix the footer")
    assert await until(js, f"{station('a1')} !== null")
    assert await js(f"[{station('a1', '.card')}.offsetWidth, {station('a1', '.card')}.offsetHeight]") == [200, 156]
    assert await js(f"[{station('a1', '.monitor')}.offsetWidth, {station('a1', '.monitor')}.offsetHeight]") == [132, 84]
    assert await js(f"{station('a1', '.desk .ticker')} !== null && {station('a1', '.desk .nameplate')} !== null")


@CHROME
async def test_a_station_that_needs_the_user_raises_a_hand(stack, tmp_path):
    from test_ai_home_phase2 import ask_for_clickup

    ask_for_clickup(stack, tmp_path)
    agents = stack["server"].agents
    await agents.create("make a ClickUp task")
    await wait_for_permissions(agents, ["a1"])
    js = await open_with(stack)
    assert await until(js, f"{station('a1')}?.dataset.state === 'needs_you'")
    assert await until(js, f"getComputedStyle({station('a1', '.worker .arm-up')}).opacity === '1'")


@CHROME
async def test_twenty_working_agents_cause_no_layout(stack):
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    stack["server"].agents.max_working = 20  # all of them at work at once, none waiting in line
    for number in range(20):
        await stack["server"].agents.create(f"Task number {number}")
    js = await open_with(stack, size=(1280, 760))
    await front(stack, js)
    assert await until(js, "document.querySelectorAll('.station[data-state=\"working\"]').length === 20")
    cdp = stack["cdp"]
    await cdp.send("Performance.enable", session_id=js.session)

    async def layouts():
        metrics = (await cdp.send("Performance.getMetrics", session_id=js.session))["metrics"]
        return next(metric["value"] for metric in metrics if metric["name"] == "LayoutCount")

    await asyncio.sleep(1.5)
    before = await layouts()
    await asyncio.sleep(2)
    assert await layouts() - before < 10


PERF_ROOM = """(async () => {
  // PERF_ROOM: 20 working stand-in stations in a second room over Mission Control, for DevTools' Performance panel.
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
  return document.querySelectorAll('#perf-room .station').length;
})()"""


@CHROME
async def test_perf_room_adds_twenty_working_stand_ins(stack):
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await stack["server"].agents.create("Fix the footer")
    js = await open_with(stack)
    assert await until(js, "document.querySelectorAll('#scene .station').length === 1")
    assert await js(PERF_ROOM) == 20
    assert await js("[...document.querySelectorAll('#perf-room .station')].every(node => node.dataset.state"
                    " === 'working' && node.querySelectorAll('.worker').length === 1)")
    assert await js("document.querySelectorAll('#scene .station').length") == 1  # the page's own room is as it was
    assert len(stack["server"].agents.agents) == 1  # nothing was sent


# ---- the alert aims at the agent that needs the user -----------------------------------------------------------------

@CHROME
async def test_the_alert_aims_at_the_agent_that_needs_the_user(stack, tmp_path):
    from test_ai_home_phase2 import ask_for_clickup

    ask_for_clickup(stack, tmp_path)
    agents = stack["server"].agents
    await agents.create("make a ClickUp task")
    await wait_for_permissions(agents, ["a1"])
    js = await brain_page(stack)
    assert await until(js, f"{station('a1')}?.dataset.state === 'needs_you'")
    assert await until(js, near("u_focus", [0, 1], 0.1))  # straight in front of the Brain
    for _ in range(12):  # the room turns half a turn: the station is now behind the Brain
        await js(key("ArrowLeft"))
    assert await until(js, near("u_focus", [0, -1], 0.1))
    await js(f"{station('a1')}.click(); true")
    card = "document.querySelector('#drawer:not([hidden]) .permission')"
    assert await until(js, f"{card} !== null")
    await js(f"{card}.querySelector('.allow-once').click(); true")
    assert await until(js, f"{station('a1')}.dataset.state !== 'needs_you'")
    assert await until(js, near("u_focus", [0, 0], 0.05))  # nothing needs the user: an even heartbeat


@CHROME
async def test_the_alert_moves_to_the_next_agent_still_waiting(stack, tmp_path):
    from test_ai_home_phase2 import ask_for_clickup

    ask_for_clickup(stack, tmp_path)
    agents = stack["server"].agents
    await agents.create("make a ClickUp task")
    await agents.create("make another ClickUp task")
    await wait_for_permissions(agents, ["a1", "a2"])
    js = await brain_page(stack)
    assert await until(js, "document.querySelectorAll('.station[data-state=\"needs_you\"]').length === 2")
    assert await until(js, near("u_focus", [-0.30, 0.95], 0.1))  # the oldest, a1, on the left of the first row
    await js(f"{station('a1')}.click(); true")
    card = "document.querySelector('#drawer:not([hidden]) .permission')"
    assert await until(js, f"{card} !== null")
    await js(f"{card}.querySelector('.deny').click(); true")
    assert await until(js, f"{station('a1')}.dataset.state !== 'needs_you'")
    assert await until(js, near("u_focus", [0.30, 0.95], 0.1))  # a2, still waiting, on the right


# ---- the arrival -----------------------------------------------------------------------------------------------------

@CHROME
async def test_agents_already_there_simply_appear(stack):
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    for name in ("one", "two", "three"):
        await stack["server"].agents.create(name)
    js = await brain_page(stack)
    assert await until(js, "document.querySelectorAll('.station').length === 3")
    await asyncio.sleep(1.5)
    assert await js("[window.spawned, window.sparks, window.gl.max.u_burst]") == [[], 0, 0]
    await stack["server"].agents.create("four")  # created while the page is open: only this one arrives
    assert await until(js, "window.spawned.length === 1")
    assert await js("window.spawned") == ["a4"]


@CHROME
async def test_a_new_agent_arrives_with_a_spark(stack):
    js = await brain_page(stack)
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await stack["server"].agents.create("Fix the footer")
    assert await until(js, "window.spawned.includes('a1')")
    assert await until(js, "window.sparks === 1 && window.sparksGone === 1", 3)
    assert await until(js, f"!{station('a1')}.classList.contains('spawning')", 3)
    assert await js("window.gl.max.u_burst") > 0.5
    assert await js("window.errors") == []


@CHROME
async def test_with_reduced_motion_a_new_agent_simply_appears(stack):
    js = await brain_page(stack)
    await reduce_motion(stack, js)
    await asyncio.sleep(0.5)
    await stack["server"].agents.create("Fix the footer")
    assert await until(js, f"{station('a1')} !== null")
    assert await until(js, "window.gl.max.u_burst > 0.5")  # the Brain's colour flash
    await asyncio.sleep(0.5)
    assert await js("[window.spawned, window.sparks]") == [[], 0]


@CHROME
async def test_many_new_agents_at_once_fly_at_most_six_sparks(stack):
    js = await brain_page(stack)
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
    assert await until(js, f"getComputedStyle({station('a1', '.worker .arm-l')}).opacity === '1'")


# ---- spoken words ----------------------------------------------------------------------------------------------------

WORDS = ("window.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };"
         "speechSynthesis.getVoices = () => [{name: 'Samantha', lang: 'en-US', localService: true}];"
         "speechSynthesis.cancel = () => {};")


def speaking(words, end):
    """A local voice (as test_mission.py's LOCAL_VOICE) whose speech reports a word at each time in `words` (ms) and
    ends at `end` (ms)."""
    return WORDS + ("speechSynthesis.speak = (said) => {"
                    f" for (const at of {json.dumps(words)}) setTimeout(() => said.onboundary"
                    " && said.onboundary({name: 'word'}), at);"
                    f" setTimeout(() => said.onend && said.onend(), {end}); }};")


async def spoken(stack, voice):
    """Mission Control with Voice on and a local voice, speaking an update about a message that needs a reply."""
    js = await brain_page(stack, voice)
    await voice_on(js)
    needs_reply(stack["brain"], sender="Maria", summary="asks to move the launch")
    assert await until(js, "window.states.includes('speaking')")
    return js


@CHROME
async def test_each_spoken_word_pulses_the_brain(stack):
    js = await spoken(stack, speaking([0, 100, 200], 350))
    assert await until(js, "window.states.at(-1) !== 'speaking'")
    assert await js("window.gl.max.u_word") > 0.5  # the words, since rings of its own wait 0.4 s


@CHROME
async def test_a_short_update_without_words_starts_no_rings(stack):
    js = await spoken(stack, speaking([], 300))
    assert await until(js, "window.states.at(-1) !== 'speaking'")
    await asyncio.sleep(0.5)
    assert await js("window.gl.max.u_word") == 0


@CHROME
async def test_a_long_update_without_words_rings_until_it_ends(stack):
    js = await spoken(stack, speaking([], 1500))
    assert await until(js, "window.gl.max.u_word > 0.5", 3)  # its own rings, 5 a second
    assert await until(js, "window.states.at(-1) !== 'speaking'", 3)
    await asyncio.sleep(1)  # the last ring has faded
    assert await js("window.gl.last.u_word") == 0
    await asyncio.sleep(1)
    assert await js("window.gl.last.u_word") == 0  # and none starts once the speech is over


# ---- the budget, and screenshots for the eye -------------------------------------------------------------------------

FRAMES = ("(() => { window.rafFrames = 0; const tick = () => { window.rafFrames += 1; requestAnimationFrame(tick); };"
          " requestAnimationFrame(tick); })();")


@CHROME
@pytest.mark.skipif(os.environ.get("AIB_PERF") != "1", reason="timing depends on the machine: set AIB_PERF=1")
async def test_the_budget(stack):
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    stack["server"].agents.max_working = 20  # all of them at work at once, none waiting in line
    for number in range(20):
        await stack["server"].agents.create(f"Task number {number}")
    js = await brain_page(stack, FRAMES, size=(1280, 760))
    assert await until(js, "document.querySelectorAll('.station[data-state=\"working\"]').length === 20")
    stack["brain"].broadcast({"type": "brain_activity", "busy": True, "what": "Sorting 2 new messages from Gmail"})
    assert await until(js, "document.querySelector('.stage').dataset.state === 'thinking'")
    cdp = stack["cdp"]
    await cdp.send("Performance.enable", session_id=js.session)
    await asyncio.sleep(1.5)

    async def metrics():
        values = (await cdp.send("Performance.getMetrics", session_id=js.session))["metrics"]
        return {metric["name"]: metric["value"] for metric in values}

    before, frames, cloud = await metrics(), await js("window.rafFrames"), await js("window.gl.cloud")
    await asyncio.sleep(3)
    after = await metrics()
    frames = await js("window.rafFrames") - frames
    cloud = await js("window.gl.cloud") - cloud
    spent = {name: round(after[name] - before[name], 4)
             for name in ("LayoutCount", "RecalcStyleCount", "RecalcStyleDuration", "TaskDuration", "ScriptDuration")}
    await js("window.gl.timing = 60; true")  # now the GPU timer: it stalls the GPU, so only after the 3 s
    assert await until(js, "window.gl.gpu.length >= 60", 10)
    gpu = await js("window.gl.gpu.reduce((sum, ms) => sum + ms, 0) / window.gl.gpu.length")
    contexts = await js("window.gl.contexts")
    points = await js("document.querySelector('.stage').dataset.points")
    print(f"\nthe budget over 3 s: {spent}, rAF frames {frames}, cloud draws {cloud}, WebGL contexts {contexts},"
          f" points {points}, the Brain's GPU time {gpu:.2f} ms a frame")
    assert spent["LayoutCount"] < 10
    assert spent["RecalcStyleCount"] <= frames and spent["RecalcStyleDuration"] <= 0.060
    assert spent["TaskDuration"] <= 0.250
    assert cloud <= 92 and contexts == 1
    assert gpu <= 1.5


SHOTS = os.environ.get("AIB_SHOTS")


async def shoot(stack, js, name, clip=None):
    params = {"format": "png", **({"clip": {**clip, "scale": 1}} if clip else {})}
    shot = await stack["cdp"].send("Page.captureScreenshot", params, session_id=js.session)
    Path(SHOTS, f"{name}.png").write_bytes(base64.b64decode(shot["data"]))


async def brain_clip(js):
    return await js("(() => { const r = document.querySelector('.stage').getBoundingClientRect();"
                    " return {x: r.left - 20, y: r.top - 20, width: r.width + 40, height: r.height + 40}; })()")


@CHROME
@pytest.mark.skipif(not SHOTS, reason="screenshots for the eye: set AIB_SHOTS to a folder")
async def test_screenshots_for_the_eye(stack):
    Path(SHOTS).mkdir(parents=True, exist_ok=True)
    brain = stack["brain"]
    js = await brain_page(stack, speaking([], 4000), size=(1280, 760))
    await asyncio.sleep(1)
    await shoot(stack, js, "brain-idle", await brain_clip(js))
    brain.broadcast({"type": "brain_activity", "busy": True, "what": "Sorting 2 new messages from Gmail"})
    await asyncio.sleep(1.5)
    await shoot(stack, js, "brain-thinking", await brain_clip(js))
    needs_reply(brain)
    brain.broadcast({"type": "brain_activity", "busy": False, "what": ""})
    await asyncio.sleep(1.5)
    await shoot(stack, js, "brain-alert", await brain_clip(js))
    await voice_on(js)
    needs_reply(brain, raw_id="t2", sender="Ben", summary="asks about staging")
    assert await until(js, "document.querySelector('.stage').dataset.state === 'speaking'")
    await asyncio.sleep(1.5)
    await shoot(stack, js, "brain-speaking", await brain_clip(js))
    for _ in range(3):
        await js(key("ArrowLeft"))
    await asyncio.sleep(0.5)
    await shoot(stack, js, "brain-turned")
    await js(key("0"))
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    agents = stack["server"].agents
    for total in (1, 6, 14, 20):
        while len(agents.agents) < total:
            await agents.create(f"Task number {len(agents.agents) + 1}")
        assert await until(js, f"document.querySelectorAll('.station').length === {total}")
        await asyncio.sleep(2.5)
        await shoot(stack, js, f"room-{total}")
    await agents.create("One more task")
    await asyncio.sleep(0.4)
    await shoot(stack, js, "arrival")
    poses_page = await poses(stack)
    await asyncio.sleep(0.5)
    await shoot(stack, poses_page, "poses")
    await reduce_motion(stack, js)
    await front(stack, js)
    await asyncio.sleep(1)
    await shoot(stack, js, "reduced")
    flat = await open_with(stack, NO_WEBGL, size=(1280, 760))
    await front(stack, flat)
    await asyncio.sleep(0.5)
    await shoot(stack, flat, "dotted", await brain_clip(flat))
