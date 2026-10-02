"""Mission Control's visuals: the Brain as a brain of glowing points (brainshape.js, blob.js) and a chibi office worker
at every station (chibi.js), against a real app server (agents on the fake claude) in a throwaway headless AI Browser.
The art holds no agent data, text stays text, and nothing is downloaded."""

import asyncio
import json

from test_home import stack, until  # noqa: F401  (fixtures)
from test_mission import CHROME, needs_reply, open_mission, open_with


async def shape(stack, body):
    """Runs `body` (statements ending in a return) in Mission Control, with brainshape.js imported as `shape`."""
    js = await open_mission(stack)
    return await js(f"(async () => {{ const shape = await import(chrome.runtime.getURL('brainshape.js')); {body} }})()")


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
