# Mission Control Visuals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Mission Control feel alive:
- the Brain becomes a brain of 8000 glowing points in one WebGL1 canvas, whose motion shows what it is doing;
- every agent becomes an original chibi office worker at a little desk, posed by the agent's state;
- a new agent arrives with a short scene (a flare, a spark to its desk, the monitor switching on, a wave).

**Architecture:**
- **The Brain:**
  - `brainshape.js` (new, pure: no DOM, no WebGL, no `Math.random`) makes the points and the links from a seed;
  - `blob.js` keeps its name and `createBlob(canvas, orb, {reduced})`, and draws them: two programs, three draws a
    frame (the web, the pulses, the cloud), at most 30 frames a second, with adaptive detail;
  - the dotted brain in CSS (`.orb`) is the fallback, and shows until the points are ready.
- **The workers:**
  - `chibi.js` (new) builds each worker from a fixed table of SVG shapes (`createElementNS`, never strings), one HTML
    layer per part;
  - `mission.css` poses the layers from the station's `data-state`, with `transform`, `translate` and `opacity` only.
- **The room:** `scene.js` builds the 200 × 156 desk diorama (`CARD`), tells the page when the camera moves
  (`onCamera`), gives directions from the Brain (`directionTo`) and plays the arrival (`upsert(agent, {fresh})`).
- **The page:** `mission.js` works out `fresh`, fires the Brain's `burst`, aims its `focus`, and passes each spoken
  word (`voice.js`'s new `onWord`) to `blob.word()`.

**Tech Stack:** plain ES modules, CSS and inline SVG in AI Browser's MV3 extension, with no libraries; WebGL 1 (GLSL ES
1.00); the Web Animations API (the spark); Python 3.12 with pytest and pytest-asyncio, driving a throwaway headless AI
Browser over CDP against a real app server and the fake `claude` (`tests/fake_claude.py`).

**Spec:** `docs/superpowers/specs/2026-10-02-mission-visuals-design.md`

## Global Constraints

Copied from the spec; every task's requirements include them.

- **The Brain** (Goal, success 2 and decision 1):
  - "at most 30 frames a second for the Brain";
  - "8000 points, halved (never below 2500) on a machine whose frames come more than 45 ms apart";
  - "one WebGL context on the page, even with 20 agents";
  - "no layout while agents work, with 20 agents";
  - "**WebGL1 only:** `canvas.getContext("webgl", {alpha: true, premultipliedAlpha: true, antialias: false})`";
  - "**The file stays.** `blob.js` keeps its name and `createBlob(canvas, orb, {reduced})`, so mission.js:3 and
    mission.js:44 don't change."
- **Unchanged guarantees** (success 7):
  - "text stays text, and no image element shows except the monitors' JPEGs (the art is inline SVG built in code)";
  - "nothing is downloaded";
  - "no new messages and no new permissions."
- **The workers' hard rules** (decision 5):
  - "in the worker, animate only `transform` and `opacity`, and only on the `.part` HTML wrappers. Never animate SVG
    elements (`<g>`, `<path>`)";
  - "inside an SVG, only state rules change things (which eyes, which mouth): a static opacity, never an animation";
  - "nothing on `.worker` itself may create a stacking context: no `transform`, `filter`, `opacity` below 1,
    `will-change`, `z-index` or `isolation`";
  - "no WebGL and no canvas in a station."
- **Safety:**
  - "the art is code: no image files in the extension, and no `<image>`, `<use>`, `<foreignObject>` or `<text>` in
    the SVGs. The prototypes copied into `docs/` are references that nothing loads";
  - "**The reference image:** it is a licensed, watermarked Pngtree stock image, and we hold no licence. It is never
    embedded, shipped, cropped, recoloured, traced, cleaned of its watermark, or fed to any image generator.";
  - "**Nothing leaves the machine.** Everything is drawn locally: no network, no web fonts, no CDN, no telemetry.";
  - "**No new permissions,** and MV3's default policy holds: only packaged scripts run.";
  - "agent data never reaches the art. The id only picks one of 3 × 3 fixed variants, through two numbers written as
    `data-hair` and `data-skin`. The colour only comes through `--c`, from the `COLORS` whitelist";
  - "`onWord` only counts words: the words themselves never reach the Brain's picture."
- **The browsing rules are untouched** (the spec's Safety):
  - "**no spoofing:** it adds no browsing, typing or clicking. The worker's "typing" and the Brain's motion are for
    the user's eyes only";
  - "**bot checks are handed to the user, never bypassed or solved**";
  - "**the agent never types passwords:** nothing here shows or fills a password field";
  - "**the user's own words are instructions, and page or message text never is**".
- **Side by side with safe-browsing (wave 1):** "This spec doesn't touch those lines: it changes `build()`,
  `upsert()`, `update()` and `renderBrain()`, and the desk keeps `.ticker`". Those lines are the imports, `stateOf`,
  `told` and `fillDrawer` in `mission.js`, and `fill()`'s `state` line and `tickerOf` in `scene.js` (the safe-browsing
  plan's Task 16): never edit them here. Every hunk below leaves at least one unchanged line between it and those, so
  the two branches merge without a conflict.
- **Earlier never leans on later:** "`listening` is left to the voice-input spec, built next" ("This spec leaves
  `u_listen` out"). The everyday-Brave spec later gives agents 7 colours: "The tie follows whatever colour the agent
  has".
- **New text** (from the rules every wave keeps, in the safe-browsing spec's coordination section): "no new text in
  Python or in the extension says "this Mac" or "⌘": use "this computer"."

## Review Focus

The five inputs most likely to bite a person using this, that no numbered spec test covers. Each line's test is
written in the task that owns the code:

1. **A workflow starts eight agents at once, and one is closed while it arrives:** at most 6 sparks fly, every spark
   is removed, every `.spawning` ends, nothing throws, and each desk settles into its pose. Test:
   `test_many_new_agents_at_once_fly_at_most_six_sparks` (Task 10).
2. **Two agents wait for a permission, and the user answers the oldest:** the Brain's alert moves to the one still
   waiting, instead of staying on the answered one or going even. Test:
   `test_the_alert_moves_to_the_next_agent_still_waiting` (Task 9).
3. **Mission Control sits in a background tab for a while, then comes back:** the long gap without frames isn't read
   as a slow machine, so the Brain keeps its 8000 points. Test: `test_a_tab_hidden_for_a_while_keeps_every_point`
   (Task 4).
4. **The WebGL context is lost before the points are made** (a GPU reset at page load): the dotted brain keeps the
   stage, `data-points` never appears, nothing is drawn and nothing throws. Test:
   `test_a_context_lost_before_the_points_leaves_the_dotted_brain` (Task 2).
5. **A voice that reports no words finishes a long update:** the self-started rings stop with the speech and `u_word`
   returns to 0 and stays there. Test: the last lines of `test_a_long_update_without_words_rings_until_it_ends`
   (Task 11).

## Before you start

- **Wave 1:** create the branch `mission-visuals` from `main` (HEAD, the commit with the five specs) and build there;
  safe-browsing is built beside it, on its own branch. Never merge or rebase onto the other branch mid-plan.
- **Running tests:** `uv run pytest <file or test> -q -p no:randomly`. Every browser test launches its own
  throwaway headless AI Browser (Google Chrome, a temporary profile) and a real app server with the fake `claude`
  (`tests/fake_claude.py`), never the user's own browser. Run only the tests each step names; the full suite runs
  once, in Task 13.
- **Commits:** each task ends with a commit of exactly the files it touched. End each message with the attribution
  line your session's instructions give.
- **In front:** a hidden tab runs no CSS animations and no `requestAnimationFrame`. Every test that reads a uniform,
  counts draws or measures time brings its page to the front (`front()`, Task 2), as `test_mission.py:402` does.
- **Line numbers** below are those of HEAD (the commit with the five specs). Every edit quotes the text it replaces.
- **The prototypes** are in `/private/tmp/claude-501/chibi-brain-probe/` (a temporary folder that may be cleared).
  Task 1 copies four of them into `docs/` as references. If the folder is gone, skip that copy: every shape and
  number this plan needs is written out below.

## File map

- **New:**
  - `src/ai_browser/app/extension/brainshape.js`: the brain's points and links (Task 1);
  - `src/ai_browser/app/extension/chibi.js`: the workers' art, defs and variants (Task 6);
  - `tests/test_mission_visuals.py`: every test of this plan (Tasks 1-12);
  - `docs/superpowers/prototypes/mission-visuals/`: `brain2.html`, `brain2.png`, `chibi.js`, `gallery.png`,
    references only (Task 1).
- **Rewritten:** `src/ai_browser/app/extension/blob.js`, the particle brain (Task 2, then Tasks 3, 4, 9, 10, 11).
- **Modified:**
  - `src/ai_browser/app/extension/scene.js`: the desk diorama, `CARD`, `fit()` (Task 8); `onCamera` and
    `directionTo` (Task 9); `upsert(agent, {fresh})` and the spark (Task 10);
  - `src/ai_browser/app/extension/mission.js`: the focus (Task 9), `fresh` and the burst (Task 10), `onWord`
    (Task 11);
  - `src/ai_browser/app/extension/voice.js`: `onWord` (Task 11);
  - `src/ai_browser/app/extension/mission.css`: the dotted brain (Task 5), the worker and its poses (Task 7), the
    station (Task 8), the arrival (Task 10);
  - `README.md`: Mission Control's stations and Brain (Task 13).
- **Unchanged:** `mission.html`, `manifest.json` (no new permission), `appbrowser.py` (`prepare_extension` copies the
  extension folder whole, so the new files ship), and `tests/test_mission.py` (every test in it must keep passing).

---

### Task 1: Reference prototypes, and the brain's shape (`brainshape.js`)

The spec's order of work, steps 1 and 2: the prototypes are copied into `docs/` as references (nothing loads them),
and the brain's points are made by a pure module, tested in the page without a GPU. The generator is the prototype's
(`brain2.html`), so the spec's numbers hold: 6400/880/400/320 points, 3120 right and 3280 left, the closest cortex
point 0.039 from the middle, 900 links. It takes about 11 ms for 8000 points.

**Files:**
- Create: `docs/superpowers/prototypes/mission-visuals/brain2.html`, `brain2.png`, `chibi.js`, `gallery.png` (copies)
- Create: `src/ai_browser/app/extension/brainshape.js`
- Create: `tests/test_mission_visuals.py`

**Interfaces:**
- Consumes: `tests/test_home.py`: the `stack` fixture; `tests/test_mission.py`: `CHROME` (skip without Chrome) and
  `open_mission(stack) -> js` (`js(expression)` evaluates in Mission Control and returns the value).
- Produces (`brainshape.js`, an ES module with no imports):
  - `brainPoints(count = 8000, seed = 7) -> Float32Array`: 6 numbers a point, `x, y, z, kind, fold, phase`
    (+x is the brain's own left, y up, z toward its front); kinds mixed exactly (cortex `round(0.8·count)`,
    cerebellum `round(0.11·count)`, stem `round(0.05·count)`, core the rest) and shuffled, so any first `n` points
    are an even sample;
  - `synapses(points, {picks = 450, perNode = 2, max = 900, seed = 3} = {}) -> Uint16Array`: index pairs of cortex
    points 0.06 to 0.22 apart;
  - `KIND = {cortex: 0, cerebellum: 1, stem: 2, core: 3}` and `HEMISPHERES = [[-0.17, 0.06, 0], [0.17, 0.06, 0]]`
    (frozen).
- Produces (tests): `shape(stack, body) -> value`, which runs `body` in Mission Control with the module as `shape`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mission_visuals.py`:

```python
"""Mission Control's visuals: the Brain as a brain of glowing points (brainshape.js, blob.js) and a chibi office worker
at every station (chibi.js), against a real app server (agents on the fake claude) in a throwaway headless AI Browser.
The art holds no agent data, text stays text, and nothing is downloaded."""

from test_home import stack  # noqa: F401  (fixture)
from test_mission import CHROME, open_mission


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
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_mission_visuals.py -q -p no:randomly`

Expected: 7 failed. `brainshape.js` doesn't exist, so the page's `import()` rejects and `js()` returns an empty object: the
tests fail with `ValueError: not enough values to unpack (expected 4, got 0)` and the like, or `assert {} == 0`.

- [ ] **Step 3: Implement**

Copy the four reference prototypes (if `/private/tmp/claude-501/chibi-brain-probe/` is gone, skip this: nothing in the
build needs them). Never copy any other picture: the user's reference image is a licensed stock picture that this
project must not hold. Before copying, look at `brain2.png` and `gallery.png`: they must be the prototypes' own renders
(the particle brain in four states; the worker gallery on dark cards) with no stock watermark, and
`grep -il "pngtree\|data:image\|http" brain2.html chibi.js` must print nothing. If either check fails, copy only what
passes and say so in the commit message. If you skip the copy, leave `docs/superpowers/prototypes/mission-visuals` out
of Step 5's `git add`.

Run:

```bash
mkdir -p docs/superpowers/prototypes/mission-visuals
cp /private/tmp/claude-501/chibi-brain-probe/brain2.html /private/tmp/claude-501/chibi-brain-probe/brain2.png \
   /private/tmp/claude-501/chibi-brain-probe/chibi.js /private/tmp/claude-501/chibi-brain-probe/gallery.png \
   docs/superpowers/prototypes/mission-visuals/
```

Create `src/ai_browser/app/extension/brainshape.js`:

```js
// The Brain's shape: thousands of points in the form of a human brain (two hemispheres with their folds, the
// cerebellum at the back and the stem below), made from a seed. Pure: no DOM, no WebGL and no Math.random, so one seed
// always gives the same brain. Axes: x across (+x is the brain's own left), y up, z toward the brain's front.
"use strict";

export const KIND = Object.freeze({ cortex: 0, cerebellum: 1, stem: 2, core: 3 });
export const HEMISPHERES = Object.freeze([Object.freeze([-0.17, 0.06, 0]), Object.freeze([0.17, 0.06, 0])]);

function rng(seed) { // mulberry32: a small, fast generator with a 32-bit state
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hash(x, y, z) { // integer lattice point -> 0..1
  let h = Math.imul(x, 374761393) ^ Math.imul(y, 668265263) ^ Math.imul(z, 1440670441);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
}

function noise(x, y, z) { // value noise, smoothly blended between lattice points
  const ix = Math.floor(x);
  const iy = Math.floor(y);
  const iz = Math.floor(z);
  const fx = x - ix;
  const fy = y - iy;
  const fz = z - iz;
  const u = fx * fx * (3 - 2 * fx);
  const v = fy * fy * (3 - 2 * fy);
  const w = fz * fz * (3 - 2 * fz);
  const lerp = (a, b, t) => a + (b - a) * t;
  return lerp(
    lerp(lerp(hash(ix, iy, iz), hash(ix + 1, iy, iz), u), lerp(hash(ix, iy + 1, iz), hash(ix + 1, iy + 1, iz), u), v),
    lerp(lerp(hash(ix, iy, iz + 1), hash(ix + 1, iy, iz + 1), u),
         lerp(hash(ix, iy + 1, iz + 1), hash(ix + 1, iy + 1, iz + 1), u), v),
    w);
}

function ridge(x, y, z) { // 1 on a fold's crest, 0 in a groove: 2 octaves of 1 - |2·noise - 1|
  let value = 0;
  let weight = 0.65;
  let frequency = 1;
  for (let octave = 0; octave < 2; octave += 1) {
    value += weight * (1 - Math.abs(2 * noise(x * frequency + 11.3 * octave, y * frequency, z * frequency) - 1));
    frequency *= 2.3;
    weight *= 0.35;
  }
  return value / 0.8775;
}

function direction(random) { // a random direction on the unit sphere: [dx, dy (up), dz (front)]
  const dy = random() * 2 - 1;
  const turn = random() * Math.PI * 2;
  const radius = Math.sqrt(1 - dy * dy);
  return [radius * Math.cos(turn), dy, radius * Math.sin(turn)];
}

// count points, 6 numbers each: x, y, z, kind (KIND), fold (0 in a groove to 1 on a ridge), phase (0 to 1). The kinds
// are mixed exactly (80% cortex, 11% cerebellum, 5% stem, the core the rest) and shuffled, so any first n points are an
// even sample of the whole brain: the level of detail is just how many are drawn.
export function brainPoints(count = 8000, seed = 7) {
  const random = rng(seed);
  const out = [];
  const cortex = Math.round(count * 0.8);
  const cerebellum = cortex + Math.round(count * 0.11);
  const stem = cerebellum + Math.round(count * 0.05);
  let guard = 0;
  while (out.length / 6 < cortex && guard++ < count * 40) {
    const h = random() < 0.5 ? -1 : 1; // the hemisphere: -1 right, +1 left
    const [dx, dy, dz] = direction(random);
    let x = dx * 0.42;
    let y = dy * 0.47;
    let z = dz * 0.7;
    if (x * h < 0) x *= 0.3; // the flat inner face: the gap between the hemispheres
    if (y < -0.12) y = -0.12 + (y + 0.12) * 0.55; // a flatter underside
    if (dz < -0.35) { // the back narrows
      x *= 0.92;
      y *= 0.94;
    }
    const temporal = Math.exp(-((z - 0.1) ** 2) / 0.05 - ((y + 0.2) ** 2) / 0.02) * Math.abs(dx);
    y -= 0.1 * temporal; // the temporal lobe hangs down at the side
    x += h * 0.05 * temporal;
    x += h * 0.17;
    y += 0.06;
    const lateral = Math.abs(dx) > 0.45 && z > -0.2 && z < 0.34 && Math.abs(y - (-0.07 + (0.34 - z) * 0.3)) < 0.025;
    const central = y > 0.05 && Math.abs(z - (0.02 + (y - 0.05) * 0.25)) < 0.018 && x * h > 0.05;
    if (lateral || central) continue; // the two big grooves
    const fold = ridge(x * 9.5 + 3, y * 9.5, z * 9.5);
    if (random() > 0.04 + 0.96 * fold ** 6) continue; // points crowd onto the ridges, so the maze shows
    const length = Math.hypot(x - h * 0.17, y - 0.06, z) || 1;
    const dent = 0.03 * (fold - 0.6); // and the grooves sink in, along the normal
    out.push(x + ((x - h * 0.17) / length) * dent, y + ((y - 0.06) / length) * dent, z + (z / length) * dent,
             KIND.cortex, fold, random());
  }
  guard = 0;
  while (out.length / 6 < cerebellum && guard++ < count * 40) {
    const h = random() < 0.5 ? -1 : 1;
    const [dx, dy, dz] = direction(random);
    if (dx * h < -0.3) continue; // no points on the inner faces
    const x = h * 0.13 + dx * 0.2;
    const y = -0.3 + dy * 0.14;
    const z = -0.42 + dz * 0.19;
    const folia = 0.5 + 0.5 * Math.sin((y + 0.3) * 120 + dz * 4); // its fine horizontal folds
    if (random() > 0.1 + 0.9 * folia ** 2) continue;
    out.push(x, y, z, KIND.cerebellum, folia, random());
  }
  while (out.length / 6 < stem) { // never rejects: it fills up to the three parts' total
    const t = random();
    const turn = random() * Math.PI * 2;
    const radius = 0.075 - 0.02 * t + 0.035 * Math.exp(-((t - 0.25) ** 2) / 0.01); // tapering, with the pons' bulge
    out.push(radius * Math.cos(turn), -0.18 - 0.62 * t, -0.1 - 0.12 * t + radius * Math.sin(turn), KIND.stem, 0.6,
             random());
  }
  while (out.length / 6 < count) { // the faint core: never rejects either, so the total is exact
    const [dx, dy, dz] = direction(random);
    const radius = Math.cbrt(random()) * 0.32;
    out.push(dx * radius * 0.9, 0.04 + dy * radius * 0.7, dz * radius * 1.3, KIND.core, 0.3, random());
  }
  for (let index = out.length / 6 - 1; index > 0; index -= 1) { // Fisher-Yates, on the same random stream
    const other = Math.floor(random() * (index + 1));
    for (let part = 0; part < 6; part += 1) {
      const kept = out[index * 6 + part];
      out[index * 6 + part] = out[other * 6 + part];
      out[other * 6 + part] = kept;
    }
  }
  return new Float32Array(out);
}

// The links the signals travel along: cortex points picked in order (probability 0.12, at most `picks`), each linked
// to its `perNode` nearest other picks between 0.06 and 0.22 away, at most `max` links. Index pairs, so at most 65536
// points.
export function synapses(points, { picks = 450, perNode = 2, max = 900, seed = 3 } = {}) {
  const random = rng(seed);
  const count = points.length / 6;
  const chosen = [];
  for (let index = 0; index < count && chosen.length < picks; index += 1) {
    if (points[index * 6 + 3] === KIND.cortex && random() < 0.12) chosen.push(index);
  }
  const links = [];
  for (const one of chosen) {
    const near = [];
    for (const two of chosen) {
      if (one === two) continue;
      const distance = Math.hypot(points[one * 6] - points[two * 6], points[one * 6 + 1] - points[two * 6 + 1],
                                  points[one * 6 + 2] - points[two * 6 + 2]);
      if (distance > 0.06 && distance < 0.22) near.push([distance, two]);
    }
    near.sort((a, b) => a[0] - b[0]);
    for (const [, two] of near.slice(0, perNode)) if (links.length / 2 < max) links.push(one, two);
  }
  return new Uint16Array(links);
}
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_mission_visuals.py -q -p no:randomly`

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/prototypes/mission-visuals src/ai_browser/app/extension/brainshape.js tests/test_mission_visuals.py
git commit -m "Mission visuals: the brain's shape from a seed (brainshape.js), and the prototypes as references"
```


### Task 2: The particle brain (`blob.js` rewritten inside)

Decisions 1, 3 and 4 (without listening): the ray-marched sphere goes, and `blob.js` draws the brain's points in the
same single WebGL1 context, keeping its name, `createBlob(canvas, orb, {reduced})`, the 30 fps cap, the canvas size,
`u_mix`'s easing, `fallback()` and the context-lost handler. Two programs and three draws a frame: the faint web
(`gl.LINES`, 900 links), the pulses (`gl.POINTS`, 900, always fewer than 1000) and the cloud (`gl.POINTS`, 8000). The
points are made in a task after the first animation frame; until the first frame with points is drawn, the canvas
stays hidden and the orb shows. A lost context cancels a generation still pending, and `makePoints()` and `draw()`
also check `gl.isContextLost()`, because the `webglcontextlost` event arrives a moment after the loss: nothing is
drawn into a lost context, and the orb keeps the stage.

Three rulings, beyond the spec's words:
- **No `pow()` on a value that can be negative:** the thinking wave's (z − 0.7·sin(1.6·t))² is written as a product.
  GLSL ES leaves `pow(x, y)` undefined for x < 0, and GPUs commonly compute it as `exp2(y·log2(x))` (HLSL's `pow`
  on the user's Windows laptop, through ANGLE, does), a NaN that `u_mix.y = 0` doesn't cancel. The flashes' `pow`
  stays: its base is `max(0, …)`.
- **Clocks, not `t·speed`:** the drift, the flashes and the pulses each run on a clock that JavaScript advances by
  `step × the blended speed`, as decision 3 already asks for the sway's phase. With `sin(t·s)` the phase would jump
  when `s` changes after a long session (at t = 1000 s, idle to thinking moves `t·s` by 750 radians in a second).
  The thinking wave, the breathing and the heartbeat are computed in JavaScript too. The clocks wrap at a common
  period (200π for the drift's 0.7/0.5/0.6, 2π for the flashes, 1 for the pulses), so they never lose precision.
- **The pulse flag reaches the fragment shader as a varying (`v_round`),** not a uniform: in WebGL1 a uniform
  declared in both shaders must have the same precision, and the fragment shaders are `mediump`.

Reduced motion already draws the still view here (yaw −55°, pitch 0.22, no drift, flashes, pulses or beat); Task 3
makes its colour fade a straight 0.7 s line that lands. `burst()`, `focus()` and `word()` come in Tasks 10, 9 and 11:
until then their uniforms are set to 0 on every frame.

**Files:**
- Modify (rewrite): `src/ai_browser/app/extension/blob.js` (all 188 lines)
- Test: `tests/test_mission_visuals.py`

**Interfaces:**
- Consumes: `brainPoints(count, seed)` and `synapses(points)` from `./brainshape.js` (Task 1); from
  `tests/test_mission.py`: `open_with(stack, source="", size=None) -> js` (the page in a new tab, `source` run before
  its scripts; `js.session` is its DevTools session) and `needs_reply(brain, raw_id="t1", ...)`.
- Produces (`blob.js`):
  - `createBlob(canvas, orb, {reduced = matchMedia(...), count = 8000, seed = 7} = {}) -> {mode, setState(state),
    destroy()}`; `mode` is `"webgl"` or `"css"`;
  - the stage's dataset: `state` (idle, thinking, alert, speaking), `mode`, and `points` (the number drawn, as a
    string, written only when it changes, removed by `fallback()`);
  - uniforms set on every drawn frame: `u_mix` (`uniform4fv`, the weights of idle, thinking, alert, speaking),
    `u_focus` (`uniform2fv`), `u_burst` and `u_word` (`uniform1f`);
  - seams the later tasks edit: `effects = {burst, burstDir, focus, word}`; `ease(step, still) -> changing`;
    `draw(now)`; the constants block ending in `const BEAT_S`; `const pending = {...}`; `const api = {...}`.
- Produces (tests): the hooks `GL` (`window.gl.last[name]`, `window.gl.max[name]`, `window.gl.cloud`,
  `window.gl.contexts`, and the GPU timer `window.gl.timing`/`window.gl.gpu`), `STATES` (`window.states`), `ARRIVALS`
  (`window.spawned`, `window.sparks`, `window.sparksGone`, `window.sparksMost`, `window.errors`) and `HOOKS`
  (all three); the helpers `front(stack, js)`, `brain_page(stack, extra="", size=None, points=True) -> js`,
  `near(name, values, within) -> str` (a JS expression) and `reduce_motion(stack, js, on=True)`
  (`Emulation.setEmulatedMedia` on the page's session).

- [ ] **Step 1: Write the failing tests**

In `tests/test_mission_visuals.py`, replace:

```python
from test_home import stack  # noqa: F401  (fixture)
from test_mission import CHROME, open_mission
```

with:

```python
import asyncio
import json

from test_home import stack, until  # noqa: F401  (fixtures)
from test_mission import CHROME, needs_reply, open_mission, open_with
```

Append to the end of `tests/test_mission_visuals.py` (two blank lines before it):

```python
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
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_mission_visuals.py::test_the_brain_is_drawn_with_points_once_they_are_made tests/test_mission_visuals.py::test_a_brain_opened_with_reduce_motion_on_is_drawn_once tests/test_mission_visuals.py::test_a_context_lost_before_the_points_leaves_the_dotted_brain tests/test_mission_visuals.py::test_the_brain_draws_at_most_30_frames_a_second tests/test_mission_visuals.py::test_the_brain_blends_its_states tests/test_mission_visuals.py::test_twenty_agents_share_one_webgl_context -q -p no:randomly`

Expected: 3 failed, 3 passed. `test_the_brain_is_drawn_with_points_once_they_are_made`,
`test_a_brain_opened_with_reduce_motion_on_is_drawn_once` and `test_the_brain_draws_at_most_30_frames_a_second` fail
with `assert False`: today's blob never sets `data-points`. `test_the_brain_blends_its_states`,
`test_twenty_agents_share_one_webgl_context` (the spec's guards 13 and 16) and
`test_a_context_lost_before_the_points_leaves_the_dotted_brain` (Review Focus 4) pass today and must keep passing:
they are guards, so watch them pass again after Step 3 rather than taking their green as proof of anything new.

- [ ] **Step 3: Implement**

Replace the whole of `src/ai_browser/app/extension/blob.js` with:

```js
// The Brain, drawn as a brain: thousands of glowing points in its shape (brainshape.js) over a faint web of links,
// with signals running along them. One WebGL1 canvas and three draws a frame (the web, the pulses, the cloud), at most
// 30 frames a second. Its state (idle, thinking, alert, speaking) blends the colours and the motion from one to the
// next. The points are made after the page's first paint; until then, and without WebGL or once the context is lost,
// the dotted brain in CSS (the orb) shows the same states (the stage's data-state). With reduced motion it is still:
// drawn once its points are ready, then only for a short colour fade after a change.
"use strict";

import { brainPoints, synapses } from "./brainshape.js";

const STATES = ["idle", "thinking", "alert", "speaking"];
const FRAME_MS = 1000 / 30; // the Brain doesn't need more than 30 frames a second
const TABLE = { // the states' own numbers, in STATES' order; what is drawn is their blend by the state weights
  speed: [0.25, 1, 0.6, 0.8], // how fast the points drift
  flash: [0.35, 2.2, 1.2, 1.6], // how often a point flashes
  pulse: [0.15, 0.84, 0.54, 0.6], // how fast the signals travel
  sway: [20, 12, 20, 20], // seconds per sway, there and back
};
const YAW = (-55 * Math.PI) / 180; // its left side three-quarters on: the speech area faces the user
const SWAY = (30 * Math.PI) / 180;
const PITCH = 0.22; // the user looks down onto it a little
const STILL = { yaw: YAW, pitch: PITCH, scale: 1, bright: 0, motion: 0 }; // reduced motion: no drift, sway or beat
const BEAT_S = 1.1; // alert: a double heartbeat this often
const CLOUD = ["u_mix", "u_yaw", "u_pitch", "u_scale", "u_dpr", "u_motion", "u_focus", "u_burst", "u_bright", "u_flow",
               "u_flash", "u_wave", "u_size", "u_word"];
const LINKS = ["u_mix", "u_yaw", "u_pitch", "u_scale", "u_dpr", "u_motion", "u_focus", "u_burst", "u_travel", "u_pulse",
               "u_burst_dir"];

const SHARED = `
precision highp float;
uniform vec4 u_mix;
uniform float u_yaw;
uniform float u_pitch;
uniform float u_scale;
uniform float u_dpr;
uniform float u_motion;
uniform vec2 u_focus;
uniform float u_burst;
varying vec3 v_color;
varying float v_alpha;
vec3 view(vec3 p) {
  float c = cos(u_yaw);
  float s = sin(u_yaw);
  p = vec3(c * p.x + s * p.z, p.y, -s * p.x + c * p.z);
  float cp = cos(u_pitch);
  float sp = sin(u_pitch);
  return vec3(p.x, cp * p.y - sp * p.z, sp * p.y + cp * p.z);
}
float aim(vec3 q) {
  vec2 side = normalize(q.xz + vec2(0.0001, 0.0));
  return mix(1.0, 0.35 + 0.65 * smoothstep(-0.2, 0.8, dot(side, u_focus)), u_mix.z);
}
`;
const CLOUD_VERTEX = `${SHARED}
attribute vec3 a_pos;
attribute vec3 a_info;
uniform float u_bright;
uniform float u_flow;
uniform float u_flash;
uniform float u_wave;
uniform float u_size;
uniform float u_word;
void main() {
  float kind = a_info.x;
  float phase = a_info.z * 6.2831853;
  vec3 centre = kind < 0.5 ? vec3(a_pos.x < 0.0 ? -0.17 : 0.17, 0.06, 0.0) : vec3(0.0);
  vec3 normal = a_pos - centre;
  normal /= max(length(normal), 0.0001);
  float drift = dot(u_mix, vec4(0.006, 0.020, 0.010, 0.010)) * u_motion;
  vec3 wander = vec3(sin(0.7 * u_flow + phase), cos(0.5 * u_flow + 1.7 * phase),
                     sin(0.6 * u_flow + 2.3 * phase)) * drift;
  if (kind < 0.5) wander -= normal * dot(wander, normal);
  else wander *= 0.5;
  vec3 q = view((a_pos + wander + normal * 0.03 * u_burst * u_motion) * u_scale);
  float persp = 2.6 / (2.6 - q.z);
  gl_Position = vec4(q.xy * persp * 1.05, 0.0, 1.0);
  float flash = pow(max(0.0, sin(u_flash + 37.0 * phase)), 60.0) * aim(q) * u_motion;
  float ahead = a_pos.z - u_wave; // squared by hand: GLSL's pow() is undefined for a negative base (NaN on ANGLE)
  float wave = u_mix.y * exp(-ahead * ahead / 0.01) * u_motion;
  float ring = u_word * step(abs(distance(a_pos, vec3(0.30, 0.0, 0.35)) - 0.6 * (1.0 - u_word)), 0.05) * u_motion;
  vec3 ridge = (mat4(vec4(0.30, 0.45, 1.00, 0.0), vec4(0.30, 0.85, 1.00, 0.0), vec4(1.00, 0.55, 0.30, 0.0),
                     vec4(0.30, 0.95, 0.75, 0.0)) * u_mix).rgb;
  vec3 groove = (mat4(vec4(0.70, 0.50, 1.00, 0.0), vec4(0.65, 0.50, 1.00, 0.0), vec4(1.00, 0.30, 0.25, 0.0),
                      vec4(0.55, 1.00, 0.90, 0.0)) * u_mix).rgb;
  vec3 base = mix(groove, ridge, a_info.y);
  bool core = kind > 2.5;
  if (core) base = mix(base, vec3(1.0), 0.3);
  float depth = 0.45 + 0.55 * smoothstep(-0.8, 0.8, q.z);
  v_color = base * depth * (1.0 + u_bright) + vec3(1.0, 0.95, 0.9) * (1.2 * flash + wave + ring + u_burst);
  v_alpha = (core ? 0.35 : 0.85) * depth;
  gl_PointSize = u_size * u_dpr * persp * (1.0 + 1.6 * flash);
}`;
const CLOUD_FRAGMENT = `
precision mediump float;
varying vec3 v_color;
varying float v_alpha;
void main() {
  float a = (1.0 - smoothstep(0.05, 0.5, length(gl_PointCoord - 0.5))) * v_alpha;
  gl_FragColor = vec4(v_color * a, a);
}`;
const LINK_VERTEX = `${SHARED}
attribute vec3 a_a;
attribute vec3 a_b;
attribute float a_t;
attribute float a_phase;
uniform float u_travel;
uniform float u_pulse;
uniform vec2 u_burst_dir;
varying float v_round;
void main() {
  float t = u_pulse > 0.5 ? fract(u_travel + a_phase) : a_t;
  vec3 mid = (a_a + a_b) * 0.5;
  vec3 bow = mid + mid / max(length(mid), 0.0001) * 0.04;
  vec3 q = view(mix(mix(a_a, bow, t), mix(bow, a_b, t), t) * u_scale);
  float persp = 2.6 / (2.6 - q.z);
  gl_Position = vec4(q.xy * persp * 1.05, 0.0, 1.0);
  vec3 m = view(mid);
  float fires = step(fract(a_phase * 7.0), dot(u_mix, vec4(0.10, 0.85, 0.60, 0.50)) * aim(m));
  vec2 side = normalize(m.xz + vec2(0.0001, 0.0));
  fires = max(fires, step(0.2, u_burst) * step(0.0001, dot(side, u_burst_dir)));
  float swell = smoothstep(0.85, 1.0, t) * u_pulse;
  float depth = 0.5 + 0.5 * smoothstep(-0.8, 0.8, q.z);
  vec3 tint = (mat4(vec4(0.55, 0.75, 1.00, 0.0), vec4(0.60, 1.00, 1.00, 0.0), vec4(1.00, 0.80, 0.50, 0.0),
                    vec4(0.70, 1.00, 0.90, 0.0)) * u_mix).rgb;
  v_color = tint * (1.0 + 0.6 * swell);
  v_alpha = (u_pulse > 0.5 ? fires * u_motion : 0.10) * depth;
  v_round = u_pulse;
  gl_PointSize = 4.0 * u_dpr * persp * (1.0 + swell);
}`;
const LINK_FRAGMENT = `
precision mediump float;
varying vec3 v_color;
varying float v_alpha;
varying float v_round;
void main() {
  float a = v_alpha;
  if (v_round > 0.5) a *= 1.0 - smoothstep(0.0, 0.5, length(gl_PointCoord - 0.5));
  gl_FragColor = vec4(v_color * a, a);
}`;

export function createBlob(canvas, orb, { reduced = matchMedia("(prefers-reduced-motion: reduce)"), count = 8000,
                                          seed = 7 } = {}) {
  const stage = canvas.closest(".stage") || canvas.parentElement;
  const target = [1, 0, 0, 0]; // the state's weights the Brain moves toward
  const mix = [1, 0, 0, 0];
  const clock = { flow: 0, flash: 0, travel: 0, sway: 0, wave: 0, breath: 0, beat: 0 };
  // a new agent's flash (and the side it fires toward), the alert's aim, a spoken word's ring
  const effects = { burst: 0, burstDir: [0, 0], focus: [0, 0], word: 0 };
  const pending = { frame: 0, timer: 0 }; // the points are made after the first paint
  let gl = null;
  let cloud = null;
  let links = null;
  let buffers = null;
  let pairs = 0; // links
  let n = 0; // points drawn: 0 until they are made
  let ratio = 1;
  let frame = 0;
  let last = 0;
  let shown = false; // the canvas has replaced the orb
  const api = { mode: "css", setState, destroy };

  function setState(state) {
    if (!STATES.includes(state)) return;
    const was = stage.dataset.state;
    if (was !== state) stage.dataset.state = state; // the CSS orb (and the tests) follow this
    target.fill(0);
    target[STATES.indexOf(state)] = 1;
    wake();
  }

  function setCount(value) {
    n = value;
    if (stage.dataset.points !== String(n)) stage.dataset.points = String(n); // only when it changes: no style work
  }

  function fallback() { // no WebGL here, or the context was lost: the dotted brain in CSS
    cancelAnimationFrame(frame);
    frame = 0;
    cancelAnimationFrame(pending.frame);
    clearTimeout(pending.timer);
    gl = null;
    n = 0;
    api.mode = "css";
    stage.dataset.mode = "css";
    delete stage.dataset.points;
    orb.hidden = false;
    canvas.hidden = true;
  }

  function compile(kind, source) {
    const shader = gl.createShader(kind);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    return gl.getShaderParameter(shader, gl.COMPILE_STATUS) ? shader : null;
  }

  function program(vertexSource, fragmentSource, attributes, names) {
    const vertex = compile(gl.VERTEX_SHADER, vertexSource);
    const fragment = compile(gl.FRAGMENT_SHADER, fragmentSource);
    if (!vertex || !fragment) return null;
    const made = gl.createProgram();
    gl.attachShader(made, vertex);
    gl.attachShader(made, fragment);
    attributes.forEach((name, index) => gl.bindAttribLocation(made, index, name));
    gl.linkProgram(made);
    if (!gl.getProgramParameter(made, gl.LINK_STATUS)) return null;
    const uniforms = {};
    for (const name of names) uniforms[name] = gl.getUniformLocation(made, name);
    return { program: made, uniforms };
  }

  function build() {
    cloud = program(CLOUD_VERTEX, CLOUD_FRAGMENT, ["a_pos", "a_info"], CLOUD);
    links = program(LINK_VERTEX, LINK_FRAGMENT, ["a_a", "a_b", "a_t", "a_phase"], LINKS);
    if (!cloud || !links) return false;
    buffers = { cloud: gl.createBuffer(), web: gl.createBuffer(), pulses: gl.createBuffer() };
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA); // premultiplied colours
    return true;
  }

  function makePoints() { // a task after the first paint: the page shows first, the brain a moment later
    pending.timer = 0;
    if (!gl || gl.isContextLost()) return; // lost meanwhile: the orb stays, and fallback() follows
    const points = brainPoints(count, seed);
    const ends = synapses(points);
    pairs = ends.length / 2;
    const web = new Float32Array(pairs * 16); // 2 vertices a link: both ends' positions, t (0 or 1), the link's phase
    const pulses = new Float32Array(pairs * 8); // 1 vertex a link
    for (let link = 0; link < pairs; link += 1) {
      const one = ends[link * 2] * 6;
      const two = ends[link * 2 + 1] * 6;
      const phase = (link * 0.618) % 1;
      const both = [points[one], points[one + 1], points[one + 2], points[two], points[two + 1], points[two + 2]];
      web.set([...both, 0, phase, ...both, 1, phase], link * 16);
      pulses.set([...both, 0, phase], link * 8);
    }
    for (const [name, data] of [["cloud", points], ["web", web], ["pulses", pulses]]) {
      gl.bindBuffer(gl.ARRAY_BUFFER, buffers[name]);
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
    }
    setCount(count);
    wake();
  }

  function blend(row) {
    return row[0] * mix[0] + row[1] * mix[1] + row[2] * mix[2] + row[3] * mix[3];
  }

  function advance(step) { // normal motion: every clock moves on at its state's blended speed, so nothing jumps
    clock.flow = (clock.flow + step * blend(TABLE.speed)) % (200 * Math.PI);
    clock.flash = (clock.flash + step * blend(TABLE.flash)) % (2 * Math.PI);
    clock.travel = (clock.travel + step * blend(TABLE.pulse)) % 1;
    clock.sway = (clock.sway + (step * 2 * Math.PI) / blend(TABLE.sway)) % (10 * Math.PI);
    clock.wave = (clock.wave + step * 1.6) % (2 * Math.PI);
    clock.breath = (clock.breath + step * 1.3) % (2 * Math.PI);
    clock.beat = (clock.beat + step) % BEAT_S;
    const peak = (x) => Math.exp(-((x / 0.06) ** 2));
    const beat = (0.035 * peak(clock.beat) + 0.02 * peak(clock.beat - 0.22)) * mix[2];
    return { yaw: YAW + SWAY * Math.sin(clock.sway), pitch: PITCH + 0.05 * Math.sin(0.6 * clock.sway),
             scale: (1 + 0.015 * Math.sin(clock.breath)) * (1 + beat), bright: (0.25 * beat) / 0.035, motion: 1 };
  }

  function ease(step, still) { // the weights move toward the state: eased as before, slower when still
    let changing = false;
    for (let index = 0; index < 4; index += 1) {
      mix[index] += (target[index] - mix[index]) * Math.min(1, step * (still ? 1.5 : 3));
      if (Math.abs(target[index] - mix[index]) > 0.003) changing = true;
    }
    return changing;
  }

  function attribute(index, size, stride, offset) {
    gl.enableVertexAttribArray(index);
    gl.vertexAttribPointer(index, size, gl.FLOAT, false, stride, offset);
  }

  function shared(uniforms, view) { // set on every drawn frame: the tests read u_mix, u_focus and u_burst
    gl.uniform4fv(uniforms.u_mix, mix);
    gl.uniform1f(uniforms.u_yaw, view.yaw);
    gl.uniform1f(uniforms.u_pitch, view.pitch);
    gl.uniform1f(uniforms.u_scale, view.scale);
    gl.uniform1f(uniforms.u_dpr, ratio);
    gl.uniform1f(uniforms.u_motion, view.motion);
    gl.uniform2fv(uniforms.u_focus, effects.focus);
    gl.uniform1f(uniforms.u_burst, effects.burst);
  }

  function draw(now) {
    frame = 0;
    if (!gl || !n || gl.isContextLost()) return;
    if (last && now - last < FRAME_MS - 2) { // not yet time for the next frame
      frame = requestAnimationFrame(draw);
      return;
    }
    const step = last ? Math.min(0.1, (now - last) / 1000) : 1 / 30;
    last = now;
    const still = reduced.matches;
    const changing = ease(step, still);
    const view = still ? STILL : advance(step);
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(links.program); // 1. the web, faint lines
    shared(links.uniforms, view);
    gl.uniform1f(links.uniforms.u_travel, clock.travel);
    gl.uniform2fv(links.uniforms.u_burst_dir, effects.burstDir);
    gl.uniform1f(links.uniforms.u_pulse, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffers.web);
    attribute(0, 3, 32, 0);
    attribute(1, 3, 32, 12);
    attribute(2, 1, 32, 24);
    attribute(3, 1, 32, 28);
    gl.drawArrays(gl.LINES, 0, pairs * 2);
    if (!still) { // 2. the pulses, one bright point travelling along each link that fires
      gl.uniform1f(links.uniforms.u_pulse, 1);
      gl.bindBuffer(gl.ARRAY_BUFFER, buffers.pulses);
      attribute(0, 3, 32, 0);
      attribute(1, 3, 32, 12);
      attribute(2, 1, 32, 24);
      attribute(3, 1, 32, 28);
      gl.drawArrays(gl.POINTS, 0, pairs);
    }
    gl.useProgram(cloud.program); // 3. the cloud
    shared(cloud.uniforms, view);
    gl.uniform1f(cloud.uniforms.u_bright, view.bright);
    gl.uniform1f(cloud.uniforms.u_flow, clock.flow);
    gl.uniform1f(cloud.uniforms.u_flash, clock.flash);
    gl.uniform1f(cloud.uniforms.u_wave, 0.7 * Math.sin(clock.wave));
    gl.uniform1f(cloud.uniforms.u_size, 1.5 * Math.min(1.6, Math.sqrt(count / n)));
    gl.uniform1f(cloud.uniforms.u_word, effects.word);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffers.cloud);
    gl.disableVertexAttribArray(2);
    gl.disableVertexAttribArray(3);
    attribute(0, 3, 24, 0);
    attribute(1, 3, 24, 12);
    gl.drawArrays(gl.POINTS, 0, n);
    if (!shown) { // the first frame with points: the canvas takes the orb's place
      shown = true;
      canvas.hidden = false;
      orb.hidden = true;
    }
    if (!still || changing) frame = requestAnimationFrame(draw); // still: drawn only while it changes
  }

  function wake() {
    if (gl && !frame) {
      last = 0;
      frame = requestAnimationFrame(draw);
    }
  }

  function destroy() {
    cancelAnimationFrame(frame);
    frame = 0;
    cancelAnimationFrame(pending.frame);
    clearTimeout(pending.timer);
    gl?.getExtension("WEBGL_lose_context")?.loseContext();
    gl = null;
  }

  const size = Math.min(360, canvas.clientWidth || 300); // CSS pixels, at most twice that in device pixels
  canvas.width = canvas.height = Math.round(size * Math.min(2, devicePixelRatio || 1));
  ratio = canvas.width / size;
  try {
    gl = canvas.getContext("webgl", { alpha: true, premultipliedAlpha: true, antialias: false });
  } catch {
    gl = null;
  }
  if (gl && build()) {
    api.mode = "webgl";
    stage.dataset.mode = "webgl";
    orb.hidden = false; // the dotted brain shows until the first frame with points
    canvas.hidden = true;
    canvas.addEventListener("webglcontextlost", (event) => {
      event.preventDefault();
      fallback();
    });
    reduced.addEventListener?.("change", wake);
    pending.frame = requestAnimationFrame(() => {
      pending.frame = 0;
      pending.timer = setTimeout(makePoints, 0);
    });
  } else {
    fallback();
  }
  setState(stage.dataset.state || "idle");
  return api;
}
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_mission_visuals.py tests/test_mission.py::test_the_blob_follows_the_brain tests/test_mission.py::test_without_webgl_the_orb_takes_over tests/test_mission.py::test_a_lost_webgl_context_hands_over_to_the_orb tests/test_mission.py::test_the_room_keeps_its_shapes_at_any_zoom -q -p no:randomly`

Expected: 17 passed: the whole new file (Task 1's 7 and this task's 6) and the 4 blob and orb tests of `test_mission.py`.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/extension/blob.js tests/test_mission_visuals.py
git commit -m "Mission visuals: the Brain as a brain of glowing points, in the same single WebGL1 context"
```


### Task 3: Reduced motion: a still Brain, with a 0.7 s colour fade

Decision 9: with Reduce Motion on, the Brain is drawn once when its points are ready (Task 2 already does that, and
its `test_a_brain_opened_with_reduce_motion_on_is_drawn_once` holds it); a change of state moves `u_mix` in a straight
line to the new state over 0.7 s and lands exactly on it, then drawing stops (today it eases at 1.5 a second and takes
about 4 s to settle). It follows the setting live through the existing `change` listener.

**Files:**
- Modify: `src/ai_browser/app/extension/blob.js` (the constants, `ease()`, `setState()`'s wake)
- Test: `tests/test_mission_visuals.py`

**Interfaces:**
- Consumes: `ease(step, still) -> changing`, `setState(state)` and `draw(now)`'s `if (!still || changing)` loop rule
  (Task 2);
  `brain_page`, `near`, `HOOKS` and `reduce_motion` (Task 2).
- Produces: `FADE_S = 0.7` (Task 10's flash fades with it too).

- [ ] **Step 1: Write the failing test**

Append to the end of `tests/test_mission_visuals.py` (two blank lines before it):

```python
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
```

- [ ] **Step 2: Run the test to see it fail**

Run: `uv run pytest tests/test_mission_visuals.py::test_with_reduced_motion_the_brain_is_still -q -p no:randomly`

Expected: FAIL. After the busy activity the draw count still grows 2 s later (the old 1.5-a-second easing needs about 4 s to
come within 0.003), so `assert ... == settled` fails; and the last `u_mix` would not be exactly `[0, 1, 0, 0]`. Its
last line fails too until Step 3's `setState()` change: today every `renderBrain()` wakes a still Brain for one more
frame, even when the state didn't change (Mission Control calls it on every agent update).

- [ ] **Step 3: Implement**

In `src/ai_browser/app/extension/blob.js`, replace:

```js
const BEAT_S = 1.1; // alert: a double heartbeat this often
```

with:

```js
const BEAT_S = 1.1; // alert: a double heartbeat this often
const FADE_S = 0.7; // reduced motion: a change of state, or a new agent's flash, is a straight fade this long
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
  function ease(step, still) { // the weights move toward the state: eased as before, slower when still
    let changing = false;
    for (let index = 0; index < 4; index += 1) {
      mix[index] += (target[index] - mix[index]) * Math.min(1, step * (still ? 1.5 : 3));
      if (Math.abs(target[index] - mix[index]) > 0.003) changing = true;
    }
    return changing;
  }
```

with:

```js
  function ease(step, still) { // the weights move toward the state: eased, or a straight line that lands when still
    let changing = false;
    const move = step / FADE_S;
    for (let index = 0; index < 4; index += 1) {
      const gap = target[index] - mix[index];
      if (still) mix[index] = Math.abs(gap) <= move ? target[index] : mix[index] + Math.sign(gap) * move;
      else mix[index] += gap * Math.min(1, step * 3);
      if (mix[index] !== target[index]) changing = true;
    }
    return changing;
  }
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
    target[STATES.indexOf(state)] = 1;
    wake();
  }
```

with:

```js
    target[STATES.indexOf(state)] = 1;
    if (was !== state) wake(); // a still Brain is drawn again only for a change (in motion it never stops)
  }
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_mission_visuals.py -q -p no:randomly`

Expected: 14 passed (the whole file so far).

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/extension/blob.js tests/test_mission_visuals.py
git commit -m "Mission visuals: with Reduce Motion the Brain is still, and a change is a 0.7 s fade that lands"
```


### Task 4: Adaptive detail: fewer points on a slow machine

Decision 10's adaptive detail: start at 8000 points; over a window of at least 2 s of drawn frames, if they average
more than 45 ms apart, halve `n` (never below 2500); a gap over 250 ms (a hidden tab, or a pause under reduced motion)
throws the window away; `n` never grows back. Since the points are shuffled, the level of detail is just
`drawArrays(POINTS, 0, n)`, and the points grow by `√(8000 / n)` (at most × 1.6, already in Task 2's `u_size`).

**Files:**
- Modify: `src/ai_browser/app/extension/blob.js` (the constants, the state, `measure()`, `draw()`)
- Test: `tests/test_mission_visuals.py`

**Interfaces:**
- Consumes: `setCount(value)`, `n`, `count` and `draw(now)` (Task 2); `brain_page`, `front`, `HOOKS` (Task 2).
- Produces: `measure(now)`, called once per drawn frame; `data-points` falls 8000 → 4000 → 2500 on a slow machine;
  the test hook `SLOW_FRAMES` (every `requestAnimationFrame` callback 80 ms late).

- [ ] **Step 1: Write the failing tests**

Append to the end of `tests/test_mission_visuals.py` (two blank lines before it):

```python
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
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_mission_visuals.py::test_a_slow_machine_draws_fewer_points tests/test_mission_visuals.py::test_a_fast_machine_keeps_every_point tests/test_mission_visuals.py::test_a_tab_hidden_for_a_while_keeps_every_point -q -p no:randomly`

Expected: 1 failed, 2 passed. `test_a_slow_machine_draws_fewer_points` fails with `assert False`: `data-points` stays `8000`.
`test_a_fast_machine_keeps_every_point` and `test_a_tab_hidden_for_a_while_keeps_every_point` (Review Focus 3) pass
today; they fail if a fast machine, or a tab that comes back, is ever taken for a slow one.

- [ ] **Step 3: Implement**

In `src/ai_browser/app/extension/blob.js`, replace:

```js
const BEAT_S = 1.1; // alert: a double heartbeat this often
const FADE_S = 0.7; // reduced motion: a change of state, or a new agent's flash, is a straight fade this long
```

with:

```js
const BEAT_S = 1.1; // alert: a double heartbeat this often
const FADE_S = 0.7; // reduced motion: a change of state, or a new agent's flash, is a straight fade this long
const LOW = 2500; // adaptive detail: never fewer points than this
const SLOW_MS = 45; // drawn frames further apart than this, on average over 2 s, halve the points
const GAP_MS = 250; // a longer gap (a hidden tab, a still Brain) isn't a slow machine: the window starts again
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
  const pending = { frame: 0, timer: 0 }; // the points are made after the first paint
```

with:

```js
  const pace = { start: 0, frames: 0, last: 0 }; // adaptive detail: the drawn frames of the current window
  const pending = { frame: 0, timer: 0 }; // the points are made after the first paint
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
  function attribute(index, size, stride, offset) {
```

with:

```js
  function measure(now) { // adaptive detail: frames that come too far apart halve the points (never grown back)
    if (!pace.last || now - pace.last > GAP_MS) Object.assign(pace, { start: now, frames: 0 });
    else pace.frames += 1;
    pace.last = now;
    if (now - pace.start < 2000) return;
    if ((now - pace.start) / pace.frames > SLOW_MS && n > LOW) setCount(Math.max(LOW, Math.floor(n / 2)));
    Object.assign(pace, { start: now, frames: 0 });
  }

  function attribute(index, size, stride, offset) {
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
    const step = last ? Math.min(0.1, (now - last) / 1000) : 1 / 30;
    last = now;
    const still = reduced.matches;
```

with:

```js
    const step = last ? Math.min(0.1, (now - last) / 1000) : 1 / 30;
    last = now;
    measure(now);
    const still = reduced.matches;
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_mission_visuals.py -q -p no:randomly`

Expected: 17 passed (the whole file so far).

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/extension/blob.js tests/test_mission_visuals.py
git commit -m "Mission visuals: fewer points on a machine whose frames come more than 45 ms apart"
```


### Task 5: The dotted brain (the CSS fallback)

Order of work step 4 and the spec's `mission.css` section: without WebGL, after a lost context, and until the points
are ready, the orb is a dotted brain silhouette in the state's colours, 240 × 180 px with no border radius and no
box-shadow. The dots are the orb's `::before`, cut by `mask-image` to a side view (front to the left); the glow is the
orb's own background, so the mask stays on `::before`. Its motion is `transform` on the orb only: breathe (idle, as
today), rock (thinking: ±4° and a 4% swell over 1.1 s, instead of the full spin), a double beat (alert: 1.06, then
1.03 0.22 s later, every 1.1 s), talk (speaking, as today). The `speaking` rule (and `talk`) is unchanged; the
voice-input spec adds `listening` beside it later.

**Files:**
- Modify: `src/ai_browser/app/extension/mission.css:56` (the stage's comment), `:63-69` (`.orb` and its thinking and
  alert rules), `:199-200` (`@keyframes swirl` becomes `rock` and `beat`)
- Test: `tests/test_mission_visuals.py`

**Interfaces:**
- Consumes: `blob.js`'s `fallback()` and the first-frame swap (Task 2) set `orb.hidden`; the stage's `data-state`.
- Produces: `.orb` (240 × 180) and `.orb::before` with a mask; `@keyframes rock` and `@keyframes beat`; the test hook
  `NO_WEBGL` (`getContext('webgl')` returns `null`).

- [ ] **Step 1: Write the failing test**

Append to the end of `tests/test_mission_visuals.py` (two blank lines before it):

```python
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
```

- [ ] **Step 2: Run the test to see it fail**

Run: `uv run pytest tests/test_mission_visuals.py::test_without_webgl_the_orb_is_a_dotted_brain -q -p no:randomly`

Expected: FAIL on `assert mask and mask != "none"`: today's orb has no `::before`, so its `maskImage` is `"none"`.

- [ ] **Step 3: Implement**

In `src/ai_browser/app/extension/mission.css`, replace:

```css
/* ---- the Brain's stage: the blob (WebGL, or a CSS orb), what it is doing, and its speech bubble ------------------- */
```

with:

```css
/* ---- the Brain's stage: the particle brain (WebGL, or the dotted brain in CSS), what it does, its speech bubble -- */
```

In `src/ai_browser/app/extension/mission.css`, replace:

```css
.orb { --a: #79a0ff; --b: #4a55d8; --glow: rgba(110, 130, 255, 0.55); width: 190px; height: 190px; border-radius: 50%;
       background: radial-gradient(circle at 36% 30%, rgba(255, 255, 255, 0.7), transparent 28%),
                   radial-gradient(circle at 50% 55%, var(--a), var(--b) 62%, transparent 72%);
       box-shadow: 0 0 60px var(--glow), 0 0 120px var(--glow); animation: breathe 4.2s ease-in-out infinite; }
.stage[data-state="thinking"] .orb { --a: #8fd0ff; --b: #4d5cff; animation: swirl 1.1s ease-in-out infinite; }
.stage[data-state="alert"] .orb { --a: #ffc08a; --b: #e0603c; --glow: rgba(240, 130, 80, 0.55);
                                  animation: breathe 1.8s ease-in-out infinite; }
```

with:

```css
/* The dotted brain (no WebGL, a lost context, or the points not ready yet): dots in the state's colours on ::before,
   cut by a mask to a side view of a brain, front to the left (the cerebrum, the cerebellum low at the back, the stem).
   The glow is the orb's own background: a mask on the orb itself would cut its glow too. */
.orb { --a: #79a0ff; --b: #4a55d8; --glow: rgba(110, 130, 255, 0.55); position: relative; width: 240px;
       height: 180px; background: radial-gradient(closest-side, var(--glow), transparent);
       animation: breathe 4.2s ease-in-out infinite; }
.orb::before { content: ""; position: absolute; inset: 0;
  background: linear-gradient(168deg, transparent 0 63%, rgba(11, 12, 19, 0.45) 63% 65.5%, transparent 65.5%),
              radial-gradient(circle, var(--a) 0 1.3px, transparent 1.8px) 0 0 / 6px 6px,
              radial-gradient(circle, var(--b) 0 1.3px, transparent 1.8px) 3px 3px / 6px 6px;
  -webkit-mask: radial-gradient(ellipse 42% 36% at 44% 42%, #000 97%, transparent 100%) 0 0 / 100% 100% no-repeat,
                radial-gradient(ellipse 17% 13% at 75% 68%, #000 97%, transparent 100%) 0 0 / 100% 100% no-repeat,
                linear-gradient(#000, #000) 62% 92% / 7% 22% no-repeat;
  mask: radial-gradient(ellipse 42% 36% at 44% 42%, #000 97%, transparent 100%) 0 0 / 100% 100% no-repeat,
        radial-gradient(ellipse 17% 13% at 75% 68%, #000 97%, transparent 100%) 0 0 / 100% 100% no-repeat,
        linear-gradient(#000, #000) 62% 92% / 7% 22% no-repeat; }
.stage[data-state="thinking"] .orb { --a: #8fd0ff; --b: #4d5cff; animation: rock 1.1s ease-in-out infinite; }
.stage[data-state="alert"] .orb { --a: #ffc08a; --b: #e0603c; --glow: rgba(240, 130, 80, 0.55);
                                  animation: beat 1.1s linear infinite; }
```

In `src/ai_browser/app/extension/mission.css`, replace:

```css
@keyframes swirl { 0% { transform: scale(1) rotate(0deg); } 50% { transform: scale(1.06) rotate(180deg); }
                   100% { transform: scale(1) rotate(360deg); } }
```

with:

```css
@keyframes rock { 0%, 100% { transform: rotate(-4deg) scale(1); } 50% { transform: rotate(4deg) scale(1.04); } }
@keyframes beat { 0%, 14%, 20%, 34%, 100% { transform: scale(1); } 6% { transform: scale(1.06); }
                  26% { transform: scale(1.03); } }
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_mission_visuals.py tests/test_mission.py::test_the_blob_follows_the_brain tests/test_mission.py::test_without_webgl_the_orb_takes_over tests/test_mission.py::test_a_lost_webgl_context_hands_over_to_the_orb tests/test_mission.py::test_the_room_keeps_its_shapes_at_any_zoom -q -p no:randomly`

Expected: 22 passed: the whole new file (18) and the 4 blob and orb tests of `test_mission.py`.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/extension/mission.css tests/test_mission_visuals.py
git commit -m "Mission visuals: without WebGL the Brain is a dotted brain silhouette"
```


### Task 6: The workers' art (`chibi.js`)

Decisions 5 and 6 (the art; the poses are Task 7): an original chibi office worker, drawn from scratch from the written
description of the style, never from the reference image. `createWorker(id)` returns a `div.worker`
(`aria-hidden="true"`, `data-hair`, `data-skin`) holding one `div.part.<name>` per part, back to front, each with one
`<svg viewBox="0 0 80 88">` built with `createElementNS` from the fixed table below. The variant comes from the FNV-1a
32-bit hash of the id's UTF-16 code units: `hair = h mod 3`, `skin = ⌊h / 3⌋ mod 3` (a1 is hair 1, skin 1; a1 to a20
cover all 9). Only the hair shape is chosen in code; shapes in the skin's colour carry the class `skin`, and the tie
the class `tie`: CSS fills both (Task 7). `ensureDefs(document)` adds one 0 × 0 `<svg id="mc-defs">` with the shared
gradients, absolutely placed and never `display: none`.

The body, the face, the arms and the gradients start from the prototype's shapes (`chibi.js` in the prototypes); the
fingers are small rounded rectangles (so they take the skin colour from CSS), and hair shapes 1 (a side part with a
fringe) and 2 (a short crop), the sweat drop, the blink lids and the sparkle are new.

**Files:**
- Create: `src/ai_browser/app/extension/chibi.js`
- Test: `tests/test_mission_visuals.py`

**Interfaces:**
- Consumes: `open_with`, `front` (Task 2).
- Produces (`chibi.js`, no imports):
  - `PARTS = ["body", "head", "face", "blink", "sweat", "arm-l", "arm-r", "arm-up", "arm-thumb", "sparkle"]`
    (back to front);
  - `variantOf(id) -> {hair: 0..2, skin: 0..2}`;
  - `ensureDefs(doc = document)`: adds `svg#mc-defs` with `mc-skin-0`, `mc-skin-1`, `mc-skin-2`, `mc-hair`,
    `mc-suit`, `mc-cheek`, `mc-lens`, once;
  - `createWorker(id) -> HTMLDivElement` (`.worker`, `aria-hidden`, `data-hair`, `data-skin`, the parts); inside the
    face: `g.eyes-open`, `g.eyes-happy`, `g.eyes-shut`, `.mouth-smile`, `.mouth-o`, `.mouth-sad`; on the body: two
    `.tie` paths; every skin-coloured shape: `.skin`.
- Produces (tests): `POSE_STATES`, `PARTS`, `POSES` (the harness: `#poses` with one `div.station[data-state] > div.card
  > .worker` per state, `--c` blue), `worker(state, part="") -> str`, `opacity(state, part) -> str`,
  `poses(stack) -> js`.

- [ ] **Step 1: Write the failing tests**

Append to the end of `tests/test_mission_visuals.py` (two blank lines before it):

```python
# ---- the workers, in a pose harness: one worker per state in a test container ----------------------------------------

POSE_STATES = ["working", "waiting", "needs_you", "your_turn", "failed", "stopped"]
PARTS = ["body", "head", "face", "blink", "sweat", "arm-l", "arm-r", "arm-up", "arm-thumb", "sparkle"]
POSES = """(async () => {
  const chibi = await import(chrome.runtime.getURL('chibi.js'));
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
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_mission_visuals.py::test_a_worker_is_made_of_parts_with_no_text_or_pictures tests/test_mission_visuals.py::test_the_id_picks_the_hair_and_the_skin -q -p no:randomly`

Expected: 2 failed: `assert await js(POSES)` gets `{}`, because `import(chrome.runtime.getURL('chibi.js'))` rejects (no such
file).

- [ ] **Step 3: Implement**

Create `src/ai_browser/app/extension/chibi.js`:

```js
// The workers: one original chibi office worker per agent (a big round head, dark swept hair, thick black glasses,
// rosy cheeks, a light suit and a tie in the agent's colour), sitting behind the station's desk. Each part is an HTML
// layer holding one small SVG built here from a fixed table of shapes: nothing is parsed from strings and there is no
// innerHTML, so the poses (mission.css) move HTML layers only. The agent's id picks one of 3 hair shapes and one of 3
// skin tones; nothing else of the agent reaches the art, and the tie takes its colour from CSS (--c).
"use strict";

const SVG = "http://www.w3.org/2000/svg";
const INK = "#141418"; // the glasses
const BROWN = "#3c2517"; // the eyes
const LIP = "#8a3f30";
const SHADE = "#c4c8d6"; // the suit's outline

// The parts, back to front. Their names are stable: other art can replace a part later.
export const PARTS = ["body", "head", "face", "blink", "sweat", "arm-l", "arm-r", "arm-up", "arm-thumb", "sparkle"];

const sleeve = (d) => [
  ["path", { d, stroke: SHADE, "stroke-width": "9.8", fill: "none", "stroke-linecap": "round" }],
  ["path", { d, stroke: "url(#mc-suit)", "stroke-width": "9", fill: "none", "stroke-linecap": "round" }],
];
const line = (d, stroke, width, extra = {}) => ["path", { d, stroke, "stroke-width": width, fill: "none",
                                                          "stroke-linecap": "round", ...extra }];

// Each shape is [tag, attributes, children?]. Shapes in the skin's colour carry the class "skin" (CSS fills them from
// the worker's data-skin); the tie carries the class "tie" (CSS fills it with var(--c)).
const ART = {
  body: [
    ["path", { d: "M14 86 C12 70 18 60 40 58 C62 60 68 70 66 86 Z", fill: "url(#mc-suit)", stroke: SHADE,
               "stroke-width": "0.8" }],
    ["path", { d: "M34 58 L40 72 L46 58 Z", fill: "#ffffff" }],
    ["path", { d: "M34 58 L39 74 L31 69 Z", fill: "#e6e8f1", stroke: "#cdd1de", "stroke-width": "0.5" }],
    ["path", { d: "M46 58 L41 74 L49 69 Z", fill: "#e6e8f1", stroke: "#cdd1de", "stroke-width": "0.5" }],
    ["path", { class: "tie", d: "M38.2 60 L41.8 60 L43 63 L41.6 76 L40 78.5 L38.4 76 L37 63 Z" }],
    ["path", { class: "tie", d: "M37.6 58.4 h4.8 l-0.9 3.2 h-3 z" }],
    ["path", { d: "M37.6 58.4 h4.8 l-0.9 3.2 h-3 z", fill: "#000000", "fill-opacity": "0.2" }],
    ["rect", { class: "skin", x: "35", y: "50", width: "10", height: "9", rx: "4" }],
  ],
  head: [
    ["circle", { class: "skin", cx: "15.5", cy: "36", r: "5.5" }],
    ["circle", { class: "skin", cx: "64.5", cy: "36", r: "5.5" }],
    ["ellipse", { class: "skin", cx: "40", cy: "33", rx: "25", ry: "23.5" }],
  ],
  face: [
    ["ellipse", { cx: "25", cy: "44", rx: "5.5", ry: "3.2", fill: "url(#mc-cheek)" }],
    ["ellipse", { cx: "55", cy: "44", rx: "5.5", ry: "3.2", fill: "url(#mc-cheek)" }],
    line("M24 25.5 q5 -3 10 0", "#2a201b", "2.2"),
    line("M46 25.5 q5 -3 10 0", "#2a201b", "2.2"),
    ["g", { class: "eyes-open" }, [
      ["ellipse", { cx: "30", cy: "34", rx: "4", ry: "4.8", fill: BROWN }],
      ["ellipse", { cx: "50", cy: "34", rx: "4", ry: "4.8", fill: BROWN }],
      ["circle", { cx: "28.8", cy: "32.2", r: "1.5", fill: "#ffffff" }],
      ["circle", { cx: "48.8", cy: "32.2", r: "1.5", fill: "#ffffff" }],
      ["circle", { cx: "31.2", cy: "36.2", r: "0.7", fill: "#ffffff", opacity: "0.8" }],
      ["circle", { cx: "51.2", cy: "36.2", r: "0.7", fill: "#ffffff", opacity: "0.8" }],
    ]],
    ["g", { class: "eyes-happy" }, [line("M26 35 q4 -5 8 0 M46 35 q4 -5 8 0", BROWN, "2")]],
    ["g", { class: "eyes-shut" }, [line("M26 35 q4 2.5 8 0 M46 35 q4 2.5 8 0", BROWN, "1.8")]],
    ["rect", { x: "21.5", y: "27.5", width: "17", height: "13.5", rx: "3.5", fill: "url(#mc-lens)", stroke: INK,
               "stroke-width": "2.4" }],
    ["rect", { x: "41.5", y: "27.5", width: "17", height: "13.5", rx: "3.5", fill: "url(#mc-lens)", stroke: INK,
               "stroke-width": "2.4" }],
    ["path", { d: "M38.5 32 h3", stroke: INK, "stroke-width": "2" }],
    ["path", { d: "M21.5 31.5 L15.5 33 M58.5 31.5 L64.5 33", stroke: INK, "stroke-width": "1.8" }],
    line("M24.5 30.5 l3 -1.4 M44.5 30.5 l3 -1.4", "#ffffff", "1.1", { opacity: "0.7" }),
    line("M36 46 q4 3.6 8 0", LIP, "1.7", { class: "mouth-smile" }),
    ["ellipse", { class: "mouth-o", cx: "40", cy: "47", rx: "2.6", ry: "2.2", fill: LIP }],
    line("M36.5 48 q3.5 -3 7 0", LIP, "1.7", { class: "mouth-sad" }),
  ],
  blink: [
    ["ellipse", { class: "skin", cx: "30", cy: "34", rx: "4.6", ry: "5.4" }],
    ["ellipse", { class: "skin", cx: "50", cy: "34", rx: "4.6", ry: "5.4" }],
    line("M26 35 q4 2.5 8 0 M46 35 q4 2.5 8 0", BROWN, "1.8"),
  ],
  sweat: [
    ["path", { d: "M61 17 C59 20.5 58 22.5 58 24 a3 3 0 0 0 6 0 C64 22.5 63 20.5 61 17 Z", fill: "#9bd8ff",
               stroke: "#5aa9e0", "stroke-width": "0.6" }],
  ],
  "arm-l": [...sleeve("M18 64 C10 70 10 78 16 82"), ["circle", { class: "skin", cx: "18", cy: "83", r: "4.4" }]],
  "arm-r": [...sleeve("M62 64 C70 70 70 78 64 82"), ["circle", { class: "skin", cx: "62", cy: "83", r: "4.4" }]],
  "arm-up": [
    ...sleeve("M62 64 C70 58 72 46 70 36"),
    ["ellipse", { class: "skin", cx: "70", cy: "31", rx: "5", ry: "6" }],
    ["rect", { class: "skin", x: "65.4", y: "21.9", width: "2.2", height: "6.2", rx: "1.1" }],
    ["rect", { class: "skin", x: "67.9", y: "19.9", width: "2.2", height: "7.2", rx: "1.1" }],
    ["rect", { class: "skin", x: "70.4", y: "19.9", width: "2.2", height: "7.2", rx: "1.1" }],
    ["rect", { class: "skin", x: "72.9", y: "22.4", width: "2.2", height: "5.7", rx: "1.1" }],
  ],
  "arm-thumb": [
    ...sleeve("M62 64 C74 70 72 80 64 74"),
    ["rect", { class: "skin", x: "55", y: "62", width: "11", height: "10", rx: "4", stroke: "#000000",
               "stroke-opacity": "0.15", "stroke-width": "0.6" }],
    ["rect", { class: "skin", x: "57.5", y: "52", width: "4.6", height: "12", rx: "2.3", stroke: "#000000",
               "stroke-opacity": "0.15", "stroke-width": "0.6" }],
  ],
  sparkle: [
    ["path", { d: "M69 40 L70.6 44.4 L75 46 L70.6 47.6 L69 52 L67.4 47.6 L63 46 L67.4 44.4 Z", fill: "#fff6c2",
               stroke: "#ffd75a", "stroke-width": "0.8" }],
  ],
};

const HAIR_HIGHLIGHT = "#8a6c58";
const HAIR = [ // always dark brown to near black; drawn over the head, under the face's brows and glasses
  [ // 0: a swept quiff
    ["path", { d: "M15 37 C11 15 25 3 42 3 C58 3 70 13 66 33 C63 25 60 21 55 19 C46 22 33 22 24 17 C20 22 17 29 "
                  + "15 37 Z", fill: "url(#mc-hair)" }],
    ["path", { d: "M24 17 C30 3 52 -3 66 9 C58 7 47 9 40 18 Z", fill: "url(#mc-hair)" }],
    line("M30 11 C38 5 50 4 58 8", HAIR_HIGHLIGHT, "1.6", { opacity: "0.7" }),
  ],
  [ // 1: a side part with a fringe
    ["path", { d: "M15 37 C12 16 25 5 41 5 C57 5 69 15 65 35 C63 28 61 24 58 22 C55 16 47 12 40 12 C33 12 26 15 22 21 "
                  + "C19 25 17 30 15 37 Z", fill: "url(#mc-hair)" }],
    ["path", { d: "M26 14 C34 8 49 9 58 16 C61 19 62 22 61 25 C56 21 49 19 42 20 C36 20.5 30 20 25 18 Z",
               fill: "url(#mc-hair)" }],
    line("M31 6.5 C29.5 9 28.5 11.5 28 14", "#120d0b", "1.2"),
    line("M38 9 C45 7.5 52 9 57 13", HAIR_HIGHLIGHT, "1.5", { opacity: "0.6" }),
  ],
  [ // 2: a short crop
    ["path", { d: "M16 33 C14 16 26 6.5 40 6.5 C54 6.5 66 16 64 33 C63 27 61.5 23 59 20 C52 17.5 46 17 40 17 "
                  + "C34 17 28 17.5 21 20 C18.5 23 17 27 16 33 Z", fill: "url(#mc-hair)" }],
    line("M27 11 C34 8.5 46 8.5 53 11", HAIR_HIGHLIGHT, "1.4", { opacity: "0.55" }),
  ],
];

const stops = (list) => list.map(([offset, color, opacity = "1"]) =>
  ["stop", { offset, "stop-color": color, "stop-opacity": opacity }]);
const GRADIENTS = [
  ["radialGradient", { id: "mc-skin-0", cx: "38%", cy: "32%", r: "75%" },
   stops([["0", "#ffe9db"], ["0.65", "#f7cdb3"], ["1", "#e2a587"]])], // light
  ["radialGradient", { id: "mc-skin-1", cx: "38%", cy: "32%", r: "75%" },
   stops([["0", "#f6d2ae"], ["0.65", "#dfab80"], ["1", "#bb8158"]])], // medium
  ["radialGradient", { id: "mc-skin-2", cx: "38%", cy: "32%", r: "75%" },
   stops([["0", "#b98463"], ["0.65", "#8f5e3f"], ["1", "#6b412a"]])], // deep
  ["radialGradient", { id: "mc-hair", cx: "30%", cy: "20%", r: "90%" },
   stops([["0", "#6a5040"], ["0.45", "#33271f"], ["1", "#17110e"]])],
  ["linearGradient", { id: "mc-suit", x1: "0", y1: "0", x2: "0.3", y2: "1" },
   stops([["0", "#ffffff"], ["1", "#d6d9e4"]])],
  ["radialGradient", { id: "mc-cheek" }, stops([["0", "#ff8a80", "0.6"], ["1", "#ff8a80", "0"]])],
  ["radialGradient", { id: "mc-lens", cx: "35%", cy: "30%", r: "80%" },
   stops([["0", "#ffffff", "0.35"], ["1", "#ffffff", "0"]])],
];

function shape(doc, [tag, attributes, children = []]) {
  const node = doc.createElementNS(SVG, tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
  for (const child of children) node.append(shape(doc, child));
  return node;
}

// FNV-1a (32 bits) over the id's UTF-16 code units: the same id always looks the same.
export function variantOf(id) {
  let hash = 0x811c9dc5;
  const text = String(id);
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return { hair: hash % 3, skin: Math.floor(hash / 3) % 3 };
}

// The page's shared gradients, in one <svg>: url(#mc-…) reaches every worker's SVG. It is 0 × 0 and absolutely placed,
// never display: none or hidden, because the gradients of an undisplayed SVG don't paint. Safe to call more than once.
export function ensureDefs(doc = document) {
  if (doc.getElementById("mc-defs")) return;
  const svg = doc.createElementNS(SVG, "svg");
  svg.id = "mc-defs";
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("width", "0");
  svg.setAttribute("height", "0");
  svg.style.position = "absolute";
  const defs = doc.createElementNS(SVG, "defs");
  for (const gradient of GRADIENTS) defs.append(shape(doc, gradient));
  svg.append(defs);
  doc.body.append(svg);
}

export function createWorker(id) {
  const { hair, skin } = variantOf(id);
  const worker = document.createElement("div");
  worker.className = "worker";
  worker.setAttribute("aria-hidden", "true");
  worker.dataset.hair = String(hair);
  worker.dataset.skin = String(skin);
  for (const name of PARTS) {
    const part = document.createElement("div");
    part.className = `part ${name}`;
    const svg = document.createElementNS(SVG, "svg");
    svg.setAttribute("viewBox", "0 0 80 88");
    for (const item of name === "head" ? [...ART.head, ...HAIR[hair]] : ART[name]) svg.append(shape(document, item));
    part.append(svg);
    worker.append(part);
  }
  return worker;
}
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_mission_visuals.py -q -p no:randomly`

Expected: 20 passed (the whole file so far).

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/extension/chibi.js tests/test_mission_visuals.py
git commit -m "Mission visuals: an original chibi office worker, built from a fixed table of SVG shapes"
```


### Task 7: The workers' poses (`mission.css`)

Decision 5's poses, from CSS only, keyed on the station's `data-state`; no JavaScript runs per frame. Every part is an
absolutely placed `div` filling the worker's box, with its layer as its `z-index` (1 behind the desk, 3 in front;
the monitor is 0 and the desk 2, Task 8). Head, face and blink move together: every head motion is a `transform` on
all three, with the same keyframes and timing, and where the eyes look is the `translate` property of the face and
blink (it adds to their `transform`). The blink, the glance and the watch start later for each worker, by 0.6 s ×
`data-hair` + 0.2 s × `data-skin` (`--lag`, a negative `animation-delay`), so neighbours don't move in step. The
existing rule `*, *::before, *::after { animation: none !important; }` stops all of it under Reduce Motion; the poses
themselves are static rules (the raised hand, the thumbs up, the slump, the shut eyes), so the state still shows.

| State | Pose |
|---|---|
| working | hands tap in turn (0.32 s); the head nods (1.6 s); the face looks toward the screen (3.5 px left); a 150 ms blink every 5 s |
| waiting | sits back (head, face and body 2 px lower); the face glances left and right (5 s); arm-l lifts to check the watch for 1 s in every 8 s |
| needs_you | the face turns to the user; arm-r hides and arm-up waves from the shoulder (1 s); `.mouth-o` |
| your_turn | the face turns to the user; arm-r hides and arm-thumb shows; `.eyes-happy`; a 3 px hop every 2.4 s (the parts that show); the sparkle once (0.8 s) |
| failed | head, face, blink, body and sweat tip forward onto the desk (static); `.eyes-shut`, `.mouth-sad`; the drop slides 4 px over 3 s, again and again |
| stopped | `.eyes-shut`; the head droops 2 px; slow breathing (4 s); every part greyed with `filter: saturate(0.4) brightness(0.8)` |
| anything else | seated and still, eyes open, smiling |

**Files:**
- Modify `src/ai_browser/app/extension/mission.css`:
  - a new worker section after the station section (`:135-136`);
  - new keyframes after `:202`.
- Test: `tests/test_mission_visuals.py`

**Interfaces:**
- Consumes: the classes `chibi.js` puts on the worker (Task 6); `reduce_motion` (Task 2); `WORKING` from
  `tests/test_mission.py` (an agent that stays at work: `[EVENTS[0], {"sleep": 30}]`).
- Produces: the `.worker` and `.worker .part` rules; `--hair`, `--skin` and `--lag` on `.worker`; the pose rules for
  `.station[data-state=…] .worker`; `@keyframes mc-tap`, `mc-nod`, `mc-blink`, `mc-glance`, `mc-watch`, `mc-wave`,
  `mc-hop`, `mc-sparkle`, `mc-sweat`, `mc-doze`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_mission_visuals.py`, replace:

```python
from test_mission import CHROME, needs_reply, open_mission, open_with
```

with:

```python
from test_mission import CHROME, WORKING, needs_reply, open_mission, open_with
```

Append to the end of `tests/test_mission_visuals.py` (two blank lines before it):

```python
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
    stack["script"].write_text(json.dumps(WORKING))
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
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_mission_visuals.py::test_a_workers_pose_shows_the_agents_state tests/test_mission_visuals.py::test_the_worker_itself_never_makes_a_stacking_context tests/test_mission_visuals.py::test_only_html_layers_are_animated tests/test_mission_visuals.py::test_with_reduced_motion_nothing_moves -q -p no:randomly`

Expected: 4 failed. No worker rule exists yet: `test_a_workers_pose_shows_the_agents_state` fails on
`("working", ".arm-up")` (no rule hides it: `'1' == '0'`); `test_the_worker_itself_never_makes_a_stacking_context` on
its `layers` (every part's `z-index` is `auto`), while the wrapper's own style already passes and must keep passing;
`test_only_html_layers_are_animated` on its second assertion and `test_with_reduced_motion_nothing_moves` on its first
`until` (no part is animated yet, so neither can show anything stopping).

- [ ] **Step 3: Implement**

In `src/ai_browser/app/extension/mission.css`, replace:

```css
.station[data-state="needs_you"] .card { border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(217, 119, 87, 0.4), 0 0 30px rgba(217, 119, 87, 0.4), 0 18px 40px rgba(0, 0, 0, 0.45); }
```

with:

```css
.station[data-state="needs_you"] .card { border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(217, 119, 87, 0.4), 0 0 30px rgba(217, 119, 87, 0.4), 0 18px 40px rgba(0, 0, 0, 0.45); }

/* ---- the worker (chibi.js): one HTML layer per part, each holding a small SVG. Only the layers move (transform,
   translate and opacity), never an SVG element, and nothing on .worker itself may make a stacking context (no
   transform, filter, opacity, will-change, z-index or isolation), so its parts stack with the desk: the body behind
   it (layer 1), the hands in front (layer 3). Poses follow the station's data-state; neighbours blink out of step. */
.worker { position: absolute; right: 4px; bottom: 45px; width: 70px; height: 77px; pointer-events: none;
          --hair: 0; --skin: 0; --lag: calc(-0.6s * var(--hair) - 0.2s * var(--skin)); }
.worker[data-hair="1"] { --hair: 1; }
.worker[data-hair="2"] { --hair: 2; }
.worker[data-skin="1"] { --skin: 1; }
.worker[data-skin="2"] { --skin: 2; }
.worker .part { position: absolute; inset: 0; z-index: 1; transform-origin: 50% 62%; }
.worker .part svg { display: block; width: 100%; height: 100%; overflow: visible; }
.worker :is(.arm-l, .arm-r, .arm-up, .arm-thumb, .sparkle) { z-index: 3; }
.worker .arm-l { transform-origin: 22% 74%; }
.worker .arm-up { transform-origin: 78% 74%; }
.worker .sparkle { transform-origin: 86% 52%; }
.worker .skin { fill: url(#mc-skin-0); }
.worker[data-skin="1"] .skin { fill: url(#mc-skin-1); }
.worker[data-skin="2"] .skin { fill: url(#mc-skin-2); }
.worker .tie { fill: var(--c, #8a8f98); }
.worker :is(.blink, .sweat, .arm-up, .arm-thumb, .sparkle) { opacity: 0; }
.worker :is(.eyes-happy, .eyes-shut, .mouth-o, .mouth-sad) { opacity: 0; }
/* working: types (the hands tap in turn), nods, looks at the screen, blinks now and then */
.station[data-state="working"] .worker .arm-l { animation: mc-tap 0.32s ease-in-out infinite alternate; }
.station[data-state="working"] .worker .arm-r { animation: mc-tap 0.32s ease-in-out infinite alternate-reverse; }
.station[data-state="working"] .worker :is(.head, .face) { animation: mc-nod 1.6s ease-in-out infinite; }
.station[data-state="working"] .worker .blink { animation: mc-nod 1.6s ease-in-out infinite,
                                                           mc-blink 5s linear var(--lag) infinite; }
.station[data-state="working"] .worker :is(.face, .blink) { translate: -3.5px 0; }
/* waiting in line: sits back, glances around, checks his watch now and then */
.station[data-state="waiting"] .worker :is(.body, .head, .face, .blink) { transform: translateY(2px); }
.station[data-state="waiting"] .worker :is(.face, .blink) { animation: mc-glance 5s ease-in-out var(--lag) infinite; }
.station[data-state="waiting"] .worker .arm-l { animation: mc-watch 8s ease-in-out var(--lag) infinite; }
/* needs you: turns to the user, raises a hand and waves, mouth open */
.station[data-state="needs_you"] .worker .arm-r { opacity: 0; }
.station[data-state="needs_you"] .worker .arm-up { opacity: 1; animation: mc-wave 1s ease-in-out infinite; }
.station[data-state="needs_you"] .worker .mouth-smile { opacity: 0; }
.station[data-state="needs_you"] .worker .mouth-o { opacity: 1; }
/* done: a thumbs up, happy eyes, a little hop, and a sparkle as it starts */
.station[data-state="your_turn"] .worker .arm-r { opacity: 0; }
.station[data-state="your_turn"] .worker .arm-thumb { opacity: 1; }
.station[data-state="your_turn"] .worker .eyes-open { opacity: 0; }
.station[data-state="your_turn"] .worker .eyes-happy { opacity: 1; }
.station[data-state="your_turn"] .worker :is(.body, .head, .face, .arm-l, .arm-thumb) {
  animation: mc-hop 2.4s ease-in-out infinite; }
.station[data-state="your_turn"] .worker .sparkle { animation: mc-sparkle 0.8s ease-out 1; }
/* failed: slumps onto the desk, eyes shut, a sad mouth and a drop of sweat */
.station[data-state="failed"] .worker :is(.body, .head, .face, .blink, .sweat) {
  transform: translateY(9px) rotate(-12deg); transform-origin: 50% 90%; }
.station[data-state="failed"] .worker :is(.eyes-open, .mouth-smile) { opacity: 0; }
.station[data-state="failed"] .worker :is(.eyes-shut, .mouth-sad) { opacity: 1; }
.station[data-state="failed"] .worker .sweat { opacity: 1; animation: mc-sweat 3s ease-in infinite; }
/* stopped: dozes, eyes shut, his colours greyed (on each part: never on .worker) */
.station[data-state="stopped"] .worker .eyes-open { opacity: 0; }
.station[data-state="stopped"] .worker .eyes-shut { opacity: 1; }
.station[data-state="stopped"] .worker :is(.head, .face, .blink) { translate: 0 2px; }
.station[data-state="stopped"] .worker :is(.body, .head, .face, .blink) { animation: mc-doze 4s ease-in-out infinite; }
.station[data-state="stopped"] .worker .part { filter: saturate(0.4) brightness(0.8); }
```

In `src/ai_browser/app/extension/mission.css`, replace:

```css
@keyframes wave { 0%, 100% { transform: rotate(18deg); } 50% { transform: rotate(-8deg); } }
```

with:

```css
@keyframes wave { 0%, 100% { transform: rotate(18deg); } 50% { transform: rotate(-8deg); } }
@keyframes mc-tap { from { transform: translateY(0); } to { transform: translateY(-2px); } }
@keyframes mc-nod { 0%, 100% { transform: rotate(0deg); } 50% { transform: rotate(-2deg) translateY(0.6px); } }
@keyframes mc-blink { 0%, 96.99% { opacity: 0; } 97%, 100% { opacity: 1; } }
@keyframes mc-glance { 0%, 100% { translate: -3px 0; } 50% { translate: 3px 0; } }
@keyframes mc-watch { 0%, 84%, 100% { transform: none; } 87%, 97% { transform: translate(5px, -9px) rotate(-28deg); } }
@keyframes mc-wave { 0%, 100% { transform: rotate(0deg); } 50% { transform: rotate(14deg); } }
@keyframes mc-hop { 0%, 80%, 100% { transform: translateY(0); } 88% { transform: translateY(-3px); } }
@keyframes mc-sparkle { 0% { opacity: 0; transform: scale(0.4) rotate(0deg); } 30% { opacity: 1; }
                        100% { opacity: 0; transform: scale(1.3) rotate(90deg); } }
@keyframes mc-sweat { from { translate: 0 0; } to { translate: 0 4px; } }
@keyframes mc-doze { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(0.8px) scale(1.01); } }
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_mission_visuals.py -q -p no:randomly`

Expected: 24 passed (the whole file so far).

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/extension/mission.css tests/test_mission_visuals.py
git commit -m "Mission visuals: the worker's poses follow the agent's state, on HTML layers only"
```


### Task 8: The station: a desk diorama with its worker

Decision 7: a station becomes a 200 × 156 desk diorama, built once in `build()` and updated in place by `fill()` (whose
lines don't change). The card clips its content (`overflow: hidden`), so a part rising from below the desk never shows
under the card; its glow and focus outline aren't clipped, and the badge sits outside it. `.nameplate`, `.light`,
`.ticker`, `.badge`, `.monitor img.shot` and `.scan` keep their names and rules; the monitor becomes 132 × 84; the
robot and the old `.head` row go (no test reads them). Placement is unchanged (`SEAT`, `ROW`, `BACK`, `placeOf()`);
the fit is re-tuned with `CARD`: the width term becomes `2 * extent.dx + CARD.w + 64`, and the far card's height
`CARD.h + 24` (180, as today); the shadow grows to 240 × 90. 20 agents still fit at 1280 × 760 without covering each
other (`test_mission.py`'s `test_twenty_agents_dont_cover_each_other_on_screen`, run in Step 4).

```
button.station.billboard        data-id, data-state, --c (as today); 200 px wide
  div.card                      200 × 156, position relative, 10 px padding, overflow hidden
    div.monitor                 132 × 84 at (10, 10), layer 0: img.shot, div.scan, div.boot (Task 10)
    div.stand                   under the monitor, down to the desk
    div.worker                  70 × 77, 4 px from the right, 45 px from the bottom (chibi.js)
    div.desk                    the bottom 50 px, layer 2: div.plate (span.nameplate, span.light), div.ticker
  span.badge                    "needs you"
```

The `PERF_ROOM` snippet (decision 10) is written here too: the project's own code, kept in the test file, for the
Windows laptop's manual check. It builds a second room over the page with 20 working stand-in stations
(`p1` to `p20`); nothing is sent, and a reload removes them.

**Files:**
- Modify `src/ai_browser/app/extension/scene.js`:
  - `:1-5` (the header and the import), `:15` (`CARD`), `:32` (`SEAT`'s comment);
  - `:95-96` (`ensureDefs`), `:111` (`fits()`), `:118` (`fit()`), `:152-162` (`build()`'s parts).
- Modify `src/ai_browser/app/extension/mission.css`:
  - `:50` (the shadow), `:84-85` (the station), `:92-94` (the card), `:98` (the monitor);
  - `:104-116` (the robot and the head row become the stand, the desk and the plate);
  - the keyframes `bob` and `wave` (removed).
- Test: `tests/test_mission_visuals.py`

**Interfaces:**
- Consumes: `createWorker(id)` and `ensureDefs(doc)` from `./chibi.js` (Task 6); the worker CSS (Task 7);
  `ask_for_clickup(stack, tmp_path)` from `tests/test_ai_home_phase2.py` (the fake claude asks for a ClickUp tool);
  `station(agent_id, part="") -> str` and `HOSTILE` (`tests/test_mission.py`, `tests/test_home.py`).
- Produces (`scene.js`): `export const CARD = {w: 200, h: 156}`; each station's `parts` gains `boot`, `stand`,
  `worker`, `desk` and `plate` (and loses `head` and `robot`); `createScene` calls `ensureDefs(document)` once.
- Produces (tests): `wait_for_permissions(agents, ids)`, and `PERF_ROOM` (a JS snippet: run it in Mission Control's
  DevTools console; it returns 20).

- [ ] **Step 1: Write the failing tests**

In `tests/test_mission_visuals.py`, replace:

```python
from test_home import stack, until  # noqa: F401  (fixtures)
from test_mission import CHROME, WORKING, needs_reply, open_mission, open_with
```

with:

```python
from test_home import HOSTILE, stack, until  # noqa: F401  (fixtures)
from test_mission import CHROME, WORKING, needs_reply, open_mission, open_with, station
```

Append to the end of `tests/test_mission_visuals.py` (two blank lines before it):

```python
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
    stack["script"].write_text(json.dumps(WORKING))
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
    stack["script"].write_text(json.dumps(WORKING))
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
  const { createScene } = await import(chrome.runtime.getURL('scene.js'));
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
    stack["script"].write_text(json.dumps(WORKING))
    await stack["server"].agents.create("Fix the footer")
    js = await open_with(stack)
    assert await until(js, "document.querySelectorAll('#scene .station').length === 1")
    assert await js(PERF_ROOM) == 20
    assert await js("[...document.querySelectorAll('#perf-room .station')].every(node => node.dataset.state"
                    " === 'working' && node.querySelectorAll('.worker').length === 1)")
    assert await js("document.querySelectorAll('#scene .station').length") == 1  # the page's own room is as it was
    assert len(stack["server"].agents.agents) == 1  # nothing was sent
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_mission_visuals.py::test_every_station_has_a_worker_with_the_agents_tie tests/test_mission_visuals.py::test_a_station_is_a_200_by_156_desk tests/test_mission_visuals.py::test_a_station_that_needs_the_user_raises_a_hand tests/test_mission_visuals.py::test_twenty_working_agents_cause_no_layout tests/test_mission_visuals.py::test_perf_room_adds_twenty_working_stand_ins -q -p no:randomly`

Expected: 4 failed, 1 passed. The stations have no `.worker` yet: `test_every_station_has_a_worker_with_the_agents_tie`,
`test_a_station_that_needs_the_user_raises_a_hand` and `test_perf_room_adds_twenty_working_stand_ins` fail with
`assert False`, and `test_a_station_is_a_200_by_156_desk` on the card's width (`176 != 200`). The spec's guard
`test_twenty_working_agents_cause_no_layout` passes today and must keep passing.

- [ ] **Step 3: Implement**

In `src/ai_browser/app/extension/scene.js`, replace:

```js
// own turn undoes the room's). Stations are built once and then updated in place, so a click is never lost to a
// rebuild; text is set with textContent, and a monitor only ever shows the app's own JPEG pictures.
"use strict";
```

with:

```js
// own turn undoes the room's). Stations are built once and then updated in place, so a click is never lost to a
// rebuild; text is set with textContent, and a monitor only ever shows the app's own JPEG pictures. Each station is a
// little desk: the monitor, a chibi worker (chibi.js) posed by the agent's state, and the desk's nameplate and ticker.
"use strict";

import { createWorker, ensureDefs } from "./chibi.js";
```

In `src/ai_browser/app/extension/scene.js`, replace:

```js
const JPEG = /^[A-Za-z0-9+/]+={0,2}$/;
```

with:

```js
const JPEG = /^[A-Za-z0-9+/]+={0,2}$/;
export const CARD = { w: 200, h: 156 }; // a station's card, in CSS pixels (mission.css uses the same numbers)
```

In `src/ai_browser/app/extension/scene.js`, replace:

```js
const SEAT = 240; // room pixels between two stations side by side (a card is 176 wide: they never overlap)
```

with:

```js
const SEAT = 240; // room pixels between two stations side by side (a card is 200 wide: they never overlap)
```

In `src/ai_browser/app/extension/scene.js`, replace:

```js
  root.replaceChildren(viewport);
  place(ring, CENTER);
```

with:

```js
  root.replaceChildren(viewport);
  ensureDefs(document);
  place(ring, CENTER);
```

In `src/ai_browser/app/extension/scene.js`, replace:

```js
    return screen(extent.near) <= height - 100 && screen(extent.far) >= 64 + 180 * scale
```

with:

```js
    return screen(extent.near) <= height - 100 && screen(extent.far) >= 64 + (CARD.h + 24) * scale
```

In `src/ai_browser/app/extension/scene.js`, replace:

```js
    let scale = Math.max(0.35, Math.min(1.15, (width * 0.94) / (2 * extent.dx + 240), height / 880));
```

with:

```js
    let scale = Math.max(0.35, Math.min(1.15, (width * 0.94) / (2 * extent.dx + CARD.w + 64), height / 880));
```

In `src/ai_browser/app/extension/scene.js`, replace:

```js
    const parts = { card: el("div", "card"), monitor: el("div", "monitor"), shot: el("img", "shot"),
                    scan: el("div", "scan"), head: el("div", "head"), robot: el("span", "robot"),
                    nameplate: el("span", "nameplate"), light: el("span", "light"), ticker: el("div", "ticker"),
                    badge: el("span", "badge", "needs you") };
    parts.shot.alt = "";
    parts.shot.hidden = true;
    parts.robot.append(el("span", "eye"), el("span", "eye"), el("span", "arm"));
    parts.monitor.append(parts.shot, parts.scan);
    parts.head.append(parts.robot, parts.nameplate, parts.light);
    parts.card.append(parts.monitor, parts.head, parts.ticker);
    node.append(parts.card, parts.badge);
```

with:

```js
    const parts = { card: el("div", "card"), monitor: el("div", "monitor"), shot: el("img", "shot"),
                    scan: el("div", "scan"), boot: el("div", "boot"), stand: el("div", "stand"),
                    worker: createWorker(id), desk: el("div", "desk"), plate: el("div", "plate"),
                    nameplate: el("span", "nameplate"), light: el("span", "light"), ticker: el("div", "ticker"),
                    badge: el("span", "badge", "needs you") };
    parts.shot.alt = "";
    parts.shot.hidden = true;
    parts.monitor.append(parts.shot, parts.scan, parts.boot);
    parts.plate.append(parts.nameplate, parts.light);
    parts.desk.append(parts.plate, parts.ticker);
    parts.card.append(parts.monitor, parts.stand, parts.worker, parts.desk);
    node.append(parts.card, parts.badge);
```

In `src/ai_browser/app/extension/mission.css`, replace:

```css
.shadow { position: absolute; width: 220px; height: 90px; margin: -45px 0 0 -110px; border-radius: 50%;
```

with:

```css
.shadow { position: absolute; width: 240px; height: 90px; margin: -45px 0 0 -120px; border-radius: 50%;
```

In `src/ai_browser/app/extension/mission.css`, replace:

```css
/* ---- a station ---------------------------------------------------------------------------------------------------- */
.station { width: 176px; border: 0; background: none; color: inherit; padding: 0; cursor: pointer; font: inherit;
```

with:

```css
/* ---- a station: a little desk diorama (the monitor, the worker, the desk's front with the name and the ticker) ---- */
.station { width: 200px; border: 0; background: none; color: inherit; padding: 0; cursor: pointer; font: inherit;
```

In `src/ai_browser/app/extension/mission.css`, replace:

```css
.station .card { background: linear-gradient(180deg, rgba(38, 42, 64, 0.94), rgba(22, 24, 38, 0.94));
                 border: 1px solid rgba(140, 150, 220, 0.25); border-radius: 14px; padding: 10px;
                 box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45); transition: border-color 0.3s, box-shadow 0.3s; }
```

with:

```css
.station .card { position: relative; width: 200px; height: 156px; padding: 10px; overflow: hidden; /* scene.js CARD */
                 background: linear-gradient(180deg, rgba(38, 42, 64, 0.94), rgba(22, 24, 38, 0.94));
                 border: 1px solid rgba(140, 150, 220, 0.25); border-radius: 14px;
                 box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45); transition: border-color 0.3s, box-shadow 0.3s; }
```

In `src/ai_browser/app/extension/mission.css`, replace:

```css
.monitor { height: 92px; border-radius: 8px; overflow: hidden; position: relative; border: 1px solid rgba(255, 255, 255, 0.08);
```

with:

```css
.monitor { width: 132px; height: 84px; border-radius: 8px; overflow: hidden; position: relative; z-index: 0;
           border: 1px solid rgba(255, 255, 255, 0.08);
```

In `src/ai_browser/app/extension/mission.css`, replace:

```css
.head { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.robot { width: 26px; height: 26px; border-radius: 50%; position: relative; flex: none;
         background: radial-gradient(circle at 35% 30%, rgba(255, 255, 255, 0.55), transparent 40%), var(--c, #4c8df6);
         box-shadow: 0 0 12px var(--c, #4c8df6); }
.robot .eye { position: absolute; top: 9px; width: 4px; height: 6px; border-radius: 2px; background: #10121c; }
.robot .eye:first-child { left: 7px; }
.robot .eye:nth-child(2) { right: 7px; }
.robot .arm { position: absolute; right: -3px; bottom: 14px; width: 5px; height: 15px; border-radius: 3px;
              background: var(--c, #4c8df6); display: none; transform-origin: 50% 100%; transform: rotate(18deg); }
.robot .arm::after { content: ""; position: absolute; top: -4px; left: -2px; width: 9px; height: 9px; border-radius: 50%;
                     background: var(--c, #4c8df6); }
.station[data-state="working"] .robot { animation: bob 0.9s ease-in-out infinite; }
.station[data-state="needs_you"] .robot .arm { display: block; animation: wave 1.2s ease-in-out infinite; }
```

with:

```css
.stand { position: absolute; left: 65px; top: 94px; width: 22px; height: 12px; z-index: 0; border-radius: 0 0 4px 4px;
         background: linear-gradient(90deg, #2c3046, #3a3f58, #2c3046); }
.desk { position: absolute; left: 0; right: 0; bottom: 0; height: 50px; z-index: 2; padding: 9px 10px 0;
        background: linear-gradient(180deg, #3a3550 0 3px, #2a2740 3px, #201e31);
        box-shadow: inset 0 2px 0 rgba(255, 255, 255, 0.06); }
.plate { display: flex; align-items: center; gap: 8px; }
```

In `src/ai_browser/app/extension/mission.css`, replace:

```css
@keyframes scan { from { transform: translateY(-100%); } to { transform: translateY(334%); } }
@keyframes bob { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-3px); } }
```

with:

```css
@keyframes scan { from { transform: translateY(-100%); } to { transform: translateY(334%); } }
```

In `src/ai_browser/app/extension/mission.css`, replace:

```css
@keyframes wave { 0%, 100% { transform: rotate(18deg); } 50% { transform: rotate(-8deg); } }
@keyframes mc-tap { from { transform: translateY(0); } to { transform: translateY(-2px); } }
```

with:

```css
@keyframes mc-tap { from { transform: translateY(0); } to { transform: translateY(-2px); } }
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_mission_visuals.py tests/test_mission.py -q -p no:randomly`

Expected: 57 passed: the whole new file (29) and every test of `test_mission.py` (28), the room's included.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/extension/scene.js src/ai_browser/app/extension/mission.css tests/test_mission_visuals.py
git commit -m "Mission visuals: each station is a little desk with its worker, 200 x 156"
```


### Task 9: The alert aims at the agent that needs the user

Decision 4's focus. `focus(direction)` takes a unit direction in the viewer's frame (x to the screen's right, z toward
the user) or `null` (that is, (0, 0)); `u_focus` moves to it in a straight line over 0.5 s. In alert, pulses and
flashes are × (0.35 + 0.65·smoothstep(−0.2, 0.8, dot(point's direction, focus))) (already in Task 2's shaders), so the
side facing the station lights up, whatever the brain's sway; with (0, 0) the heartbeat is even. `mission.js` aims it
at the oldest agent (by `created`) whose `stateOf(agent)` is `needs_you`: a tool request, or, with the safe-browsing
spec, a bot check, since this reads `stateOf` and never changes it. It is recomputed in `renderBrain()` and after every
camera change, through `onCamera`, which `createScene` calls at the end of every `apply()` except the first (the blob
doesn't exist yet then). `directionTo(id)` turns the seat minus CENTER by the camera's spin `s`:
`dx = x·cos s − y·sin s`, `dz = x·sin s + y·cos s`, normalised. A seat straight in front of the Brain gives {0, 1} at
spin 0, and {0, −1} at 180°. A `focus()` with the same target as before does nothing, so the many `renderBrain()`
calls never restart the 0.5 s move.

**Files:**
- Modify `src/ai_browser/app/extension/scene.js`:
  - `:87` (`createScene`'s options), `:102` (`started`), `:130` (`apply()` ends with `onCamera`);
  - before `:199` (`directionTo`), and `:236-238` (`started = true` and the returned API).
- Modify `src/ai_browser/app/extension/mission.js`:
  - `:25` (`onCamera: aimBrain`);
  - `:156` and `:162-163` (`renderBrain()` calls `aimBrain()`, and `aimBrain()` itself).
- Modify: `src/ai_browser/app/extension/blob.js` (the constants, the state, `focus()`, `settle()`, `draw()`, the API)
- Test: `tests/test_mission_visuals.py`

**Interfaces:**
- Consumes: `effects.focus` and `u_focus` (Task 2); `wait_for_permissions` (Task 8); `key(name) -> str` (a keydown
  on the page, `tests/test_mission.py`); `stateOf(agent)` in `mission.js` (not changed here).
- Produces:
  - `createScene(root, {onSelect, onCamera = () => {}})`; `scene.directionTo(id) -> {dx, dz} | null`;
  - `blob.focus(direction)` with `direction` = `{dx, dz}` or `null` (does nothing in css mode: no frames are drawn);
  - in `blob.js`: `settle(now)`, called once per drawn frame after `ease()` (Tasks 10 and 11 extend it);
  - in `mission.js`: `aimBrain()`, called at the end of `renderBrain()` and as `onCamera`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_mission_visuals.py`, replace:

```python
from test_mission import CHROME, WORKING, needs_reply, open_mission, open_with, station
```

with:

```python
from test_mission import CHROME, WORKING, key, needs_reply, open_mission, open_with, station
```

Append to the end of `tests/test_mission_visuals.py` (two blank lines before it):

```python
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
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_mission_visuals.py::test_the_alert_aims_at_the_agent_that_needs_the_user tests/test_mission_visuals.py::test_the_alert_moves_to_the_next_agent_still_waiting -q -p no:randomly`

Expected: 2 failed with `assert False` at the first `near("u_focus", ...)`: `u_focus` stays `[0, 0]`.

- [ ] **Step 3: Implement**

In `src/ai_browser/app/extension/scene.js`, replace:

```js
export function createScene(root, { onSelect = () => {} } = {}) {
```

with:

```js
export function createScene(root, { onSelect = () => {}, onCamera = () => {} } = {}) {
```

In `src/ai_browser/app/extension/scene.js`, replace:

```js
  let extent = { dx: 600, near: 920, far: CENTER.y }; // how far the stations reach: the room is fitted to them
```

with:

```js
  let extent = { dx: 600, near: 920, far: CENTER.y }; // how far the stations reach: the room is fitted to them
  let started = false; // the first apply() runs before the Brain exists: onCamera only after it
```

In `src/ai_browser/app/extension/scene.js`, replace:

```js
    room.dataset.scale = shortly(camera.scale);
  }
```

with:

```js
    room.dataset.scale = shortly(camera.scale);
    if (started) onCamera(); // turn, zoom, reset, resize and layout: the Brain re-aims its alert
  }
```

In `src/ai_browser/app/extension/scene.js`, replace:

```js
  function remove(id) {
```

with:

```js
  function directionTo(id) { // from the Brain to a station, in the viewer's frame: dx to the right, dz to the user
    const station = stations.get(id);
    if (!station) return null;
    const x = Number(station.node.dataset.x) - CENTER.x;
    const y = Number(station.node.dataset.y) - CENTER.y;
    const spin = (camera.spin * Math.PI) / 180;
    const dx = x * Math.cos(spin) - y * Math.sin(spin);
    const dz = x * Math.sin(spin) + y * Math.cos(spin);
    const length = Math.hypot(dx, dz);
    return length ? { dx: dx / length, dz: dz / length } : null;
  }

  function remove(id) {
```

In `src/ai_browser/app/extension/scene.js`, replace:

```js
  addEventListener("resize", apply);
  apply();
  return { upsert, remove, thumb, turn, zoom, reset, camera, stage, viewport };
```

with:

```js
  addEventListener("resize", apply);
  apply();
  started = true;
  return { upsert, remove, thumb, turn, zoom, reset, directionTo, camera, stage, viewport };
```

In `src/ai_browser/app/extension/mission.js`, replace:

```js
const scene = createScene($("scene"), { onSelect: select });
```

with:

```js
const scene = createScene($("scene"), { onSelect: select, onCamera: aimBrain });
```

In `src/ai_browser/app/extension/mission.js`, replace:

```js
function renderBrain() { // the blob swirls while the Brain works, glows while something needs the user
```

with:

```js
function renderBrain() { // the Brain thinks while it works, beats while something needs the user
```

In `src/ai_browser/app/extension/mission.js`, replace:

```js
  setText(brainWhat, brainState.busy ? brainState.what : "");
}
```

with:

```js
  setText(brainWhat, brainState.busy ? brainState.what : "");
  aimBrain();
}

function aimBrain() { // the alert's signals gather on the side facing the oldest agent that needs the user
  const waiting = [...agents.values()].filter((agent) => stateOf(agent) === "needs_you")
    .sort((one, two) => (Number(one.created) || Infinity) - (Number(two.created) || Infinity))[0];
  blob.focus(waiting ? scene.directionTo(waiting.id) : null);
}
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
const GAP_MS = 250; // a longer gap (a hidden tab, a still Brain) isn't a slow machine: the window starts again
```

with:

```js
const GAP_MS = 250; // a longer gap (a hidden tab, a still Brain) isn't a slow machine: the window starts again
const FOCUS_MS = 500; // focus(): the alert's aim moves to its new side in a straight line this long
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
  const pace = { start: 0, frames: 0, last: 0 }; // adaptive detail: the drawn frames of the current window
```

with:

```js
  const aim = { from: [0, 0], to: [0, 0], at: 0 }; // focus(): where u_focus moves from and to, and since when
  const pace = { start: 0, frames: 0, last: 0 }; // adaptive detail: the drawn frames of the current window
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
  const api = { mode: "css", setState, destroy };
```

with:

```js
  const api = { mode: "css", setState, focus, destroy };
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
    target[STATES.indexOf(state)] = 1;
    if (was !== state) wake(); // a still Brain is drawn again only for a change (in motion it never stops)
  }
```

with:

```js
    target[STATES.indexOf(state)] = 1;
    if (was !== state) wake(); // a still Brain is drawn again only for a change (in motion it never stops)
  }

  function focus(direction) { // alert: the signals gather on the side facing this direction ({dx, dz}), or evenly
    const to = direction ? [direction.dx, direction.dz] : [0, 0];
    if (to[0] === aim.to[0] && to[1] === aim.to[1]) return;
    Object.assign(aim, { from: [...effects.focus], to, at: performance.now() });
  }
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
    return changing;
  }
```

with:

```js
    return changing;
  }

  function settle(now) { // the effects move on, frame by frame
    const k = Math.min(1, Math.max(0, (now - aim.at) / FOCUS_MS));
    effects.focus = [aim.from[0] + (aim.to[0] - aim.from[0]) * k, aim.from[1] + (aim.to[1] - aim.from[1]) * k];
  }
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
    const changing = ease(step, still);
```

with:

```js
    const changing = ease(step, still);
    settle(now);
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_mission_visuals.py tests/test_mission.py::test_the_camera_turns_and_zooms_within_limits tests/test_mission.py::test_turning_past_half_a_turn_keeps_going tests/test_mission.py::test_a_waiting_permission_is_answered_from_mission_control tests/test_mission.py::test_the_blob_follows_the_brain -q -p no:randomly`

Expected: 35 passed: the whole new file (31) and 4 camera, permission and blob tests of `test_mission.py`.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/extension/scene.js src/ai_browser/app/extension/mission.js src/ai_browser/app/extension/blob.js tests/test_mission_visuals.py
git commit -m "Mission visuals: the Brain's alert gathers on the side of the agent that needs the user"
```


### Task 10: A new agent's arrival

Decision 8. Only for an agent created while the page is open: in `update()`, `fresh = agentsKnown && !before`
(`agentsKnown` is false until the first snapshot is in), then `scene.upsert(agent, {fresh})` and
`blob.burst(scene.directionTo(agent.id))`. `upsert` adds `.spawning` and flies the spark unless
`matchMedia('(prefers-reduced-motion: reduce)')` matches at that moment. In about two seconds:
1. **0 ms, the burst:** `u_burst` goes to 1 and fades linearly over 0.8 s (0.7 s with reduced motion, as a colour
   flash). Every point brightens and is pushed out 3% along its normal, and the links facing the new desk fire while
   it is above 0.2 (Task 2's shaders).
2. **0-700 ms, the spark:** a `div.spark.billboard` (18 px, the agent's colour) placed once at the Brain; its
   `translate` moves along 9 linear keyframes, f = 0, 1/8, … 1: (f·dx, f·dy, z), z = 200 − 140·f + 440·f·(1 − f) px,
   in the room's own pixels, so it arcs over the floor whatever the camera does. It is removed when it finishes. At
   most 6 fly at once; any more skip the spark.
3. **700-1000 ms:** the monitor's `.boot` line grows across the screen, opens to full height and fades.
4. **850-1300 ms:** the parts behind the desk slide up from 80 px lower, with an overshoot; the arms stay at opacity 0
   until 1150 ms, then fade in over 100 ms.
5. **1300-1900 ms:** arm-up waves once (arm-r hidden meanwhile), then the state's pose takes over.
6. **2000 ms:** a timer removes `.spawning` (`animationend` never fires when animations are off).

Steps 3 to 5 are CSS animations under `.station.spawning`, after the pose rules and with higher specificity
(`.station.spawning .worker .part.arm-l` beats `.station[data-state=…] .worker .arm-l`). Every station's own
arrival fade (`arriving`, `placing`) stays, so stations still open in their places.

**Files:**
- Modify: `src/ai_browser/app/extension/scene.js` (`SPARKS`, `arrive()`, `upsert(agent, {fresh})`: HEAD `:185-197`)
- Modify: `src/ai_browser/app/extension/mission.js:135` (`update()`)
- Modify: `src/ai_browser/app/extension/blob.js` (the constants, `burst()`, `settle()`, `draw()`, the API)
- Modify: `src/ai_browser/app/extension/mission.css` (the arrival section after the worker section; its keyframes after
  `mc-doze`)
- Test: `tests/test_mission_visuals.py`

**Interfaces:**
- Consumes: `scene.directionTo(id)` (Task 9); `settle(now)` and `FADE_S` (Tasks 9 and 3); `effects.burst`,
  `effects.burstDir`, `u_burst` and `u_burst_dir` (Task 2); the `ARRIVALS` hook and `reduce_motion` (Task 2);
  `.station[data-state] .worker` poses (Task 7); `.monitor`'s `div.boot` (built in Task 8).
- Produces: `scene.upsert(agent, {fresh = false} = {})`; `blob.burst(direction)` with `direction` = `{dx, dz}` or
  `null` (nothing in css mode); `settle(now, step, still)`; `.station.spawning` (2 s); `.spark`.

- [ ] **Step 1: Write the failing tests**

Append to the end of `tests/test_mission_visuals.py` (two blank lines before it):

```python
# ---- the arrival -----------------------------------------------------------------------------------------------------

@CHROME
async def test_agents_already_there_simply_appear(stack):
    stack["script"].write_text(json.dumps(WORKING))
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
    stack["script"].write_text(json.dumps(WORKING))
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
    stack["script"].write_text(json.dumps(WORKING))
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
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_mission_visuals.py::test_agents_already_there_simply_appear tests/test_mission_visuals.py::test_a_new_agent_arrives_with_a_spark tests/test_mission_visuals.py::test_with_reduced_motion_a_new_agent_simply_appears tests/test_mission_visuals.py::test_many_new_agents_at_once_fly_at_most_six_sparks -q -p no:randomly`

Expected: 4 failed. No `.spawning`, no spark and no `u_burst` yet: `test_agents_already_there_simply_appear` passes
its first part (nothing arrives for the three agents already there, and `u_burst` is set to 0 on every frame since
Task 2) and fails with `assert False` when the fourth agent never arrives; `test_a_new_agent_arrives_with_a_spark`
fails on its first `until`; `test_many_new_agents_at_once_fly_at_most_six_sparks` (Review Focus 1) on its second
(`window.sparks > 0`: the stations themselves do appear); and `test_with_reduced_motion_a_new_agent_simply_appears`
on `window.gl.max.u_burst > 0.5`.

- [ ] **Step 3: Implement**

In `src/ai_browser/app/extension/scene.js`, replace:

```js
export const CARD = { w: 200, h: 156 }; // a station's card, in CSS pixels (mission.css uses the same numbers)
```

with:

```js
export const CARD = { w: 200, h: 156 }; // a station's card, in CSS pixels (mission.css uses the same numbers)
const SPARKS = 6; // arrivals in flight at once: any more arrive without a spark
```

In `src/ai_browser/app/extension/scene.js`, replace:

```js
  function upsert(agent) {
    if (!agent?.id) return;
    let station = stations.get(agent.id);
    if (!station) {
      station = build(agent.id);
      stations.set(agent.id, station);
      created.set(agent.id, Number(agent.created) || Infinity);
      order.push(agent.id);
      order.sort((one, two) => created.get(one) - created.get(two));
      layout();
    }
    fill(station, agent);
  }
```

with:

```js
  function arrive(station) { // a new agent's short scene: the spark flies from the Brain, the desk plays .spawning
    const { node } = station;
    node.classList.add("spawning");
    setTimeout(() => node.classList.remove("spawning"), 2000); // a timer: animationend never fires without animations
    if (room.querySelectorAll(".spark").length >= SPARKS) return;
    const spark = el("div", "spark billboard");
    spark.style.setProperty("--c", node.style.getPropertyValue("--c"));
    place(spark, CENTER);
    room.append(spark);
    const dx = Number(node.dataset.x) - CENTER.x;
    const dy = Number(node.dataset.y) - CENTER.y;
    const frames = [];
    for (let step = 0; step <= 8; step += 1) { // an arc over the floor, in the room's own pixels
      const f = step / 8;
      frames.push({ translate: `${f * dx}px ${f * dy}px ${200 - 140 * f + 440 * f * (1 - f)}px` });
    }
    const flight = spark.animate(frames, { duration: 700, easing: "linear" });
    flight.onfinish = () => spark.remove();
    flight.oncancel = () => spark.remove();
  }

  function upsert(agent, { fresh = false } = {}) { // fresh: created while the page is open, so its arrival plays
    if (!agent?.id) return;
    let station = stations.get(agent.id);
    const added = !station;
    if (added) {
      station = build(agent.id);
      stations.set(agent.id, station);
      created.set(agent.id, Number(agent.created) || Infinity);
      order.push(agent.id);
      order.sort((one, two) => created.get(one) - created.get(two));
      layout();
    }
    fill(station, agent);
    if (added && fresh && !matchMedia("(prefers-reduced-motion: reduce)").matches) arrive(station);
  }
```

In `src/ai_browser/app/extension/mission.js`, replace:

```js
  agents.set(agent.id, agent);
  scene.upsert(agent);
```

with:

```js
  agents.set(agent.id, agent);
  const fresh = agentsKnown && !before; // created while this page is open: its arrival plays
  scene.upsert(agent, { fresh });
  if (fresh) blob.burst(scene.directionTo(agent.id));
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
const FOCUS_MS = 500; // focus(): the alert's aim moves to its new side in a straight line this long
```

with:

```js
const FOCUS_MS = 500; // focus(): the alert's aim moves to its new side in a straight line this long
const BURST_S = 0.8; // a new agent: the Brain's flare fades this long (FADE_S with reduced motion)
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
  const api = { mode: "css", setState, focus, destroy };
```

with:

```js
  const api = { mode: "css", setState, burst, focus, destroy };
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
  function focus(direction) { // alert: the signals gather on the side facing this direction ({dx, dz}), or evenly
```

with:

```js
  function burst(direction) { // a new agent: the Brain flares and fires toward its desk ({dx, dz} or null)
    if (!gl) return;
    effects.burst = 1;
    effects.burstDir = direction ? [direction.dx, direction.dz] : [0, 0];
    wake();
  }

  function focus(direction) { // alert: the signals gather on the side facing this direction ({dx, dz}), or evenly
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
  function settle(now) { // the effects move on, frame by frame
```

with:

```js
  function settle(now, step, still) { // the effects move on, frame by frame
    effects.burst = Math.max(0, effects.burst - step / (still ? FADE_S : BURST_S));
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
    settle(now);
```

with:

```js
    settle(now, step, still);
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
    if (!still || changing) frame = requestAnimationFrame(draw); // still: drawn only while it changes
```

with:

```js
    if (!still || changing || effects.burst > 0) frame = requestAnimationFrame(draw); // still: only while it changes
```

In `src/ai_browser/app/extension/mission.css`, replace:

```css
.station[data-state="stopped"] .worker .part { filter: saturate(0.4) brightness(0.8); }
```

with:

```css
.station[data-state="stopped"] .worker .part { filter: saturate(0.4) brightness(0.8); }

/* ---- a new agent's arrival: scene.js adds .spawning for 2 s (never with Reduce Motion on) and flies a .spark ----- */
.monitor .boot { position: absolute; inset: 0; opacity: 0; pointer-events: none; transform: scale(0, 0.03);
                 background: linear-gradient(180deg, transparent, rgba(200, 225, 255, 0.95) 50%, transparent); }
.station.spawning .monitor .boot { animation: mc-boot 0.3s linear 0.7s both; }
.station.spawning .worker .part:is(.body, .head, .face, .blink, .sweat) {
  animation: mc-pop 0.45s ease-out 0.85s backwards; }
.station.spawning .worker .part.arm-l { animation: mc-arm-in 1.25s linear; }
.station.spawning .worker .part.arm-r { animation: mc-arm-r-in 1.9s linear; }
.station.spawning .worker .part.arm-up { animation: mc-hello 1.9s linear; }
.station.spawning .worker .part:is(.arm-thumb, .sparkle) { animation: mc-hidden 1.9s linear; }
.spark { width: 18px; height: 18px; border-radius: 50%; pointer-events: none;
         background: radial-gradient(circle, #ffffff 0 18%, var(--c, #4c8df6) 45%, transparent 72%);
         box-shadow: 0 0 14px var(--c, #4c8df6), 0 0 28px var(--c, #4c8df6); }
```

In `src/ai_browser/app/extension/mission.css`, replace:

```css
@keyframes mc-doze { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(0.8px) scale(1.01); } }
```

with:

```css
@keyframes mc-doze { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(0.8px) scale(1.01); } }
@keyframes mc-boot { 0% { opacity: 1; transform: scale(0, 0.03); } 45% { opacity: 1; transform: scale(1, 0.03); }
                     80% { opacity: 0.8; transform: scale(1, 1); } 100% { opacity: 0; transform: scale(1, 1); } }
@keyframes mc-pop { 0% { transform: translateY(80px); } 70% { transform: translateY(-4px); } 100% { transform: none; } }
@keyframes mc-arm-in { 0%, 92% { opacity: 0; } 100% { opacity: 1; } }
@keyframes mc-arm-r-in { 0%, 60.5% { opacity: 0; } 65.8%, 68.4% { opacity: 1; } 68.5%, 100% { opacity: 0; } }
@keyframes mc-hello { 0%, 68.4% { opacity: 0; transform: rotate(0deg); } 68.5% { opacity: 1; transform: rotate(0deg); }
                      84% { transform: rotate(16deg); } 100% { opacity: 1; transform: rotate(0deg); } }
@keyframes mc-hidden { from, to { opacity: 0; } }
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_mission_visuals.py tests/test_mission.py -q -p no:randomly`

Expected: 63 passed: the whole new file (35) and every test of `test_mission.py` (28).

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/extension/scene.js src/ai_browser/app/extension/mission.js src/ai_browser/app/extension/blob.js src/ai_browser/app/extension/mission.css tests/test_mission_visuals.py
git commit -m "Mission visuals: a new agent arrives with a flare, a spark to its desk and a wave"
```


### Task 11: Each spoken word pulses the Brain (`onWord`)

Decision 4's words. `voice.js` sets `utterance.onboundary` and calls a new `onWord` callback for each event whose
`name` is `word` (only while that utterance is still speaking); `mission.js` passes `() => blob.word()`. `word()` sets
`u_word` to 1, and it fades linearly to 0 over 0.6 s while a ring spreads from the speech area (Task 2's shader:
points within 0.05 of 0.6·(1 − `u_word`) from (0.30, 0.0, 0.35) brighten by `u_word`). With no word for 0.4 s while
the state is speaking (some voices report none), the blob starts a ring itself, 5 times a second, until a word comes
or the state changes. Under reduced motion `word()` does nothing (the rings are off). `onWord` only counts words:
the words never reach the picture. The voice-input spec's `priority`, `pause()` and `resume()` (wave 2) touch other
parts of `voice.js`.

**Files:**
- Modify: `src/ai_browser/app/extension/voice.js:9` (`createVoice`'s options) and `:58` (`onboundary`)
- Modify: `src/ai_browser/app/extension/mission.js:51-52` (`onWord`)
- Modify: `src/ai_browser/app/extension/blob.js` (the constants, the state, `setState()`, `word()`, `settle()`, the API)
- Test: `tests/test_mission_visuals.py`

**Interfaces:**
- Consumes: `settle(now, step, still)` (Task 10); `effects.word` and `u_word` (Task 2); `voice_on(js)` (switches Voice
  on, `tests/test_mission.py`); the `STATES` hook's `window.states` (Task 2).
- Produces: `createVoice({bubble, onSpeaking, onBlocked, onWord = () => {}, hold})`; `blob.word()`; the test helpers
  `WORDS`, `speaking(words, end) -> str` and `spoken(stack, voice) -> js`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_mission_visuals.py`, replace:

```python
from test_mission import CHROME, WORKING, key, needs_reply, open_mission, open_with, station
```

with:

```python
from test_mission import CHROME, WORKING, key, needs_reply, open_mission, open_with, station, voice_on
```

Append to the end of `tests/test_mission_visuals.py` (two blank lines before it):

```python
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
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_mission_visuals.py::test_each_spoken_word_pulses_the_brain tests/test_mission_visuals.py::test_a_short_update_without_words_starts_no_rings tests/test_mission_visuals.py::test_a_long_update_without_words_rings_until_it_ends -q -p no:randomly`

Expected: 2 failed, 1 passed. `u_word` is still 0 on every frame: `test_each_spoken_word_pulses_the_brain` fails on
`assert 0 > 0.5`, and `test_a_long_update_without_words_rings_until_it_ends` with `assert False` on its first
`until`. `test_a_short_update_without_words_starts_no_rings` passes, and must keep passing: rings of the Brain's own
wait 0.4 s.

- [ ] **Step 3: Implement**

In `src/ai_browser/app/extension/voice.js`, replace:

```js
export function createVoice({ bubble, onSpeaking = () => {}, onBlocked = () => {}, hold = 5000 } = {}) {
```

with:

```js
export function createVoice({ bubble, onSpeaking = () => {}, onBlocked = () => {}, onWord = () => {},
                              hold = 5000 } = {}) {
```

In `src/ai_browser/app/extension/voice.js`, replace:

```js
      utterance.onend = () => finish();
```

with:

```js
      utterance.onend = () => finish();
      utterance.onboundary = (event) => { // each spoken word pulses the Brain (only counted: the words stay here)
        if (event?.name === "word" && !done) onWord();
      };
```

In `src/ai_browser/app/extension/mission.js`, replace:

```js
  onBlocked: (blocked) => setText($("voice-note"), blocked ? "Click anywhere on this page to let the Brain speak" : ""),
});
```

with:

```js
  onBlocked: (blocked) => setText($("voice-note"), blocked ? "Click anywhere on this page to let the Brain speak" : ""),
  onWord: () => blob.word(),
});
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
const BURST_S = 0.8; // a new agent: the Brain's flare fades this long (FADE_S with reduced motion)
```

with:

```js
const BURST_S = 0.8; // a new agent: the Brain's flare fades this long (FADE_S with reduced motion)
const WORD_S = 0.6; // a spoken word's ring spreads and fades this long
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
  const aim = { from: [0, 0], to: [0, 0], at: 0 }; // focus(): where u_focus moves from and to, and since when
```

with:

```js
  const speech = { heard: 0, self: 0 }; // speaking: the last word heard (or when it began), the last ring started here
  const aim = { from: [0, 0], to: [0, 0], at: 0 }; // focus(): where u_focus moves from and to, and since when
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
  const api = { mode: "css", setState, burst, focus, destroy };
```

with:

```js
  const api = { mode: "css", setState, burst, focus, word, destroy };
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
    if (was !== state) stage.dataset.state = state; // the CSS orb (and the tests) follow this
```

with:

```js
    if (was !== state) stage.dataset.state = state; // the CSS orb (and the tests) follow this
    if (state === "speaking" && was !== "speaking") speech.heard = performance.now();
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
    Object.assign(aim, { from: [...effects.focus], to, at: performance.now() });
  }
```

with:

```js
    Object.assign(aim, { from: [...effects.focus], to, at: performance.now() });
  }

  function word() { // speaking: a ring of light spreads from the speech area
    if (!gl || reduced.matches) return;
    effects.word = 1;
    speech.heard = performance.now();
  }
```

In `src/ai_browser/app/extension/blob.js`, replace:

```js
    effects.focus = [aim.from[0] + (aim.to[0] - aim.from[0]) * k, aim.from[1] + (aim.to[1] - aim.from[1]) * k];
  }
```

with:

```js
    effects.focus = [aim.from[0] + (aim.to[0] - aim.from[0]) * k, aim.from[1] + (aim.to[1] - aim.from[1]) * k];
    effects.word = still ? 0 : Math.max(0, effects.word - step / WORD_S);
    if (!still && target[3] === 1 && now - speech.heard >= 400 && now - speech.self >= 200) {
      speech.self = now; // no words reported for 0.4 s: rings 5 times a second, until a word comes
      effects.word = 1;
    }
  }
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_mission_visuals.py tests/test_mission.py::test_voice_is_off_by_default_and_needs_a_voice_on_this_mac tests/test_mission.py::test_a_burst_stops_the_voice tests/test_mission.py::test_a_voice_that_never_ends_is_stopped tests/test_mission.py::test_voice_waits_for_a_click_when_chrome_asks_for_one tests/test_mission.py::test_updates_are_written_in_order -q -p no:randomly`

Expected: 43 passed: the whole new file (38) and the 5 voice tests of `test_mission.py`.

- [ ] **Step 5: Commit**

```bash
git add src/ai_browser/app/extension/voice.js src/ai_browser/app/extension/mission.js src/ai_browser/app/extension/blob.js tests/test_mission_visuals.py
git commit -m "Mission visuals: each spoken word sends a ring of light across the Brain"
```


### Task 12: The performance pass and the screenshots

The spec's order of work, step 8: screenshots checked by eye, then the performance pass on the M5 (test 29), with its
numbers written into the plan's report. This task adds measurements of what Tasks 2 to 11 built and no production
code, so its tests can't fail first: both are skipped unless their variable is set, and a failure when they run sends
you back to the task that owns the line that failed.

`test_the_budget` asserts decision 10's budget: fewer than 10 layouts, at most one style recalc a frame and 60 ms of
them, at most 250 ms of task time, at most 92 cloud draws, one context, and (timed afterwards, because the pixel read
stalls the GPU) at most 1.5 ms of GPU a frame from the frame's first `drawArrays` to a one-pixel `readPixels` after its
cloud. It prints every number.

**What this plan's rehearsal measured** (this plan's finished build, on the M5, while other test runs shared the
machine): 0 layouts; 180 recalcs for 180 frames; 67-85 ms of recalcs in the calmer runs (up to 130 ms under load);
180-210 ms of task time; 90 cloud draws; 1 context; 0.88-1.65 ms of GPU a frame. Two lines can fail here, and both
follow the machine's load: the prototype room's HTML-layer workers, measured the same hour, took 44-76 ms of recalcs
where the spec recorded 46 ms, and today's robots 41-45 ms where it recorded 28. A probe of the parts (CSS overrides
in one open page, three rounds) put the 20 monitors' scan lines alone at 22-25 ms of recalcs and the workers'
animations at about 45 ms more; the measurement behind the spec's 60 ms (46 ms) had the workers alone, without the
monitors' scan lines, which the spec keeps. The same probe found that `steps()` timing on the hands left the recalc count at one a frame and its time
unchanged, which matters to decision 10's Windows remedy.

**Files:**
- Test: `tests/test_mission_visuals.py` (`FRAMES`, `test_the_budget`, `shoot`, `brain_clip`,
  `test_screenshots_for_the_eye`)
- Create: `docs/superpowers/reports/2026-10-02-mission-visuals.md`

**Interfaces:**
- Consumes: every hook and helper above (`brain_page`, `front`, `reduce_motion`, `poses`, `speaking`, `voice_on`,
  `NO_WEBGL`, `near`), and `key` (`tests/test_mission.py`).
- Produces: `test_the_budget` (runs only with `AIB_PERF=1`), `test_screenshots_for_the_eye` (runs only with
  `AIB_SHOTS=<folder>`), and the report.

- [ ] **Step 1: Write the measuring tests**

In `tests/test_mission_visuals.py`, replace:

```python
import asyncio
import json

from test_home import HOSTILE, stack, until  # noqa: F401  (fixtures)
```

with:

```python
import asyncio
import base64
import json
import os
from pathlib import Path

import pytest

from test_home import HOSTILE, stack, until  # noqa: F401  (fixtures)
```

Append to the end of `tests/test_mission_visuals.py` (two blank lines before it):

```python
# ---- the budget, and screenshots for the eye -------------------------------------------------------------------------

FRAMES = ("(() => { window.rafFrames = 0; const tick = () => { window.rafFrames += 1; requestAnimationFrame(tick); };"
          " requestAnimationFrame(tick); })();")


@CHROME
@pytest.mark.skipif(os.environ.get("AIB_PERF") != "1", reason="timing depends on the machine: set AIB_PERF=1")
async def test_the_budget(stack):
    stack["script"].write_text(json.dumps(WORKING))
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
    stack["script"].write_text(json.dumps(WORKING))
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
```

- [ ] **Step 2: Run them: they are skipped**

Run: `uv run pytest tests/test_mission_visuals.py::test_the_budget tests/test_mission_visuals.py::test_screenshots_for_the_eye -q -p no:randomly -rs`

Expected: 2 skipped, with the reasons "timing depends on the machine: set AIB_PERF=1" and "screenshots for the eye: set
AIB_SHOTS to a folder". Nothing fails: the code they measure is done.

- [ ] **Step 3: Take the screenshots, run the performance pass, and write the report**

Take the screenshots, then look at each one and compare it with the prototypes' `brain2.png` and `gallery.png` (the
table in the report says what to see):

Run:

```bash
AIB_SHOTS=/tmp/mission-visuals-shots uv run pytest tests/test_mission_visuals.py::test_screenshots_for_the_eye -q -p no:randomly
```

Expected: 1 passed, and 13 PNG files in `/tmp/mission-visuals-shots`. If a picture is wrong, fix it in the task that
owns it (the Brain: Tasks 2-5; the worker: Tasks 6-7; the desk: Task 8; the arrival: Task 10), with that task's tests,
before going on.

Then the performance pass, three times, on a quiet machine (no other test run, nothing heavy open):

Run:

```bash
AIB_PERF=1 uv run pytest tests/test_mission_visuals.py::test_the_budget -q -p no:randomly -s
```

Expected: each run prints a line that starts with "the budget over 3 s:" before its assertions; it passes when the
machine meets the budget. Be ready for a failure on `RecalcStyleDuration`: the rehearsal above measured 67-85 ms of
recalcs against the spec's 60 ms, even on calm runs, because the spec's 46 ms left out the monitors' scan lines. The
budget is met when the middle run of the three meets every line. If it doesn't, stop and report the three printed
lines to the user: the remedies (fewer animated parts, the scan lines, or a canvas per station) change the design or
the spec's budget, which is the user's call. Don't loosen an assertion to make it pass.

Write the numbers and what you saw into the report:

Create `docs/superpowers/reports/2026-10-02-mission-visuals.md`:

```markdown
# Mission Control visuals: measurements

Spec: `docs/superpowers/specs/2026-10-02-mission-visuals-design.md`.
Plan: `docs/superpowers/plans/2026-10-02-mission-visuals.md`.

## The budget on the M5 (`test_the_budget`, `AIB_PERF=1`)

20 working agents, the Brain thinking, 1280 × 760, over 3 s; three runs on a quiet machine. Each cell holds the number
the test printed.

| Measure | Budget | Run 1 | Run 2 | Run 3 |
|---|---|---|---|---|
| Layouts (`LayoutCount`) | fewer than 10 | | | |
| Style recalcs (`RecalcStyleCount`) / rAF frames | at most one a frame | | | |
| Style recalc time (`RecalcStyleDuration`) | at most 60 ms | | | |
| Main-thread task time (`TaskDuration`) | at most 250 ms | | | |
| Cloud draws | at most 92 | | | |
| WebGL contexts | 1 | | | |
| The Brain's GPU time | at most 1.5 ms a frame | | | |
| Points | 8000 | | | |

## Checked by eye

Screenshots (`AIB_SHOTS`), compared with `docs/superpowers/prototypes/mission-visuals/brain2.png` and `gallery.png`:

| Screenshot | What to see | Seen |
|---|---|---|
| brain-idle, brain-thinking, brain-alert, brain-speaking | a brain (two hemispheres with folds, the cerebellum, the stem) in blue-violet, cyan, amber-coral, mint | |
| brain-turned | the room turned, the Brain still facing the user | |
| room-1, room-6, room-14, room-20 | desks with workers, no card covering another, every name readable | |
| poses | the six poses: typing, waiting, a raised hand, a thumbs up, slumped with a drop of sweat, dozing in grey | |
| arrival | the spark on its way, the new desk's worker below the desk or popping up | |
| reduced | the same room, still | |
| dotted | the dotted brain silhouette, front to the left | |

## On Windows

Not measured here. The Windows spec's manual laptop check runs `PERF_ROOM` (kept in `tests/test_mission_visuals.py`)
in Mission Control's DevTools, records 3 s in the Performance panel, and writes down layouts, style recalcs (count and
time) and total task time (decision 10). If style recalcs take more than 150 ms in 3 s there, decision 10's next steps
are the user's call: the hands on `steps()` timing (the rehearsal above found it doesn't lower the recalc time on the
M5), then a canvas per station, in a spec of its own.
```

Fill every empty cell of the two tables: the numbers from the three printed lines, and "yes", or what was wrong and
the task where you fixed it.

- [ ] **Step 4: Run the whole file**

Run: `uv run pytest tests/test_mission_visuals.py -q -p no:randomly`

Expected: 38 passed, 2 skipped.

- [ ] **Step 5: Commit**

```bash
git add tests/test_mission_visuals.py docs/superpowers/reports/2026-10-02-mission-visuals.md
git commit -m "Mission visuals: the performance pass on the M5, and screenshots checked by eye"
```


### Task 13: The README, the full suite and the bench

The last task: the README's Mission Control section says what the user now sees (the robot and the blob are gone),
then the whole suite and the bench run once.

The safe-browsing spec's coordination list says this spec changes nothing in the README, but the README's Mission
Control section describes "a little robot at a desk" and "a glowing blob", which are no longer true. So this task
changes only that section's lines about the stations, the Brain and Reduce Motion. None of the README parts the other
specs change (AI Browser is automated, What sites can see, Bot checks, the own-Chrome section, QA's pace, Which
browser, Talking to the Brain, Windows) is touched, so the waves still merge cleanly. The Voice bullet ("a voice that
runs on this Mac") isn't this spec's to change, and stays.

**Files:**
- Modify: `README.md:226-230` (Stations), `:233-235` (the Brain), `:244-245` (Reduce Motion)
- Modify: `docs/superpowers/reports/2026-10-02-mission-visuals.md` (the suite and the bench)

**Interfaces:**
- Consumes: everything above.
- Produces: the README's description of the new Mission Control; the report's results.

- [ ] **Step 1: Update the README**

In `README.md`, replace:

```markdown
- **Stations:** every agent works at its own station, a little robot at a desk.
  - Its monitor shows the tab it works in (the same pictures as AI Home), and the ticker its last action
    ("click e14 · 38 ms").
  - The light shows its state: green working, amber waiting in line, ✓ done, red failed.
  - A station that **needs you** (a tool waiting for your permission) glows, and its robot raises a hand.
```

with:

```markdown
- **Stations:** every agent works at its own little desk, where a chibi office worker in a tie of the agent's colour
  sits beside the monitor. The art is drawn in code on this computer: nothing is downloaded.
  - Its monitor shows the tab it works in (the same pictures as AI Home), and the ticker its last action
    ("click e14 · 38 ms").
  - The light shows its state: green working, amber waiting in line, ✓ done, red failed. The worker shows it too: he
    types while the agent works, checks his watch while it waits, gives a thumbs up when it is done, slumps on the
    desk when it failed, and dozes when it was stopped.
  - A station that **needs you** (a tool waiting for your permission) glows, and its worker turns to you and waves.
  - A new agent arrives with a short scene: the Brain flares, a spark flies to its desk, the monitor switches on, and
    the worker pops up and waves.
```

In `README.md`, replace:

```markdown
- **The Brain** floats in the middle as a glowing blob:
  - it breathes while idle, swirls while it sorts messages or writes a draft, glows warm while something needs you
    (the count shows under it), and pulses when it speaks;
```

with:

```markdown
- **The Brain** floats in the middle as a brain of glowing points, turning slowly:
  - it drifts while idle, sends a wave of light across itself while it sorts messages or writes a draft, and beats
    like a heart, in amber, while something needs you, its signals gathering on the side of the agent that waits (the
    count shows under it); each word it speaks sends a ring of light across it;
  - without WebGL it is a dotted brain in the same colours, and on a slower computer it draws fewer points;
```

In `README.md`, replace:

```markdown
  0 resets. With Reduce Motion on (System Settings → Accessibility → Display), the room stands still and the blob
  changes slowly.
```

with:

```markdown
  0 resets. With Reduce Motion on (System Settings → Accessibility → Display), the room, the workers and the Brain
  stand still: a change is a short colour fade, and a new agent's desk simply appears.
```

- [ ] **Step 2: Run the full suite**

Run:

```bash
uv run pytest -q -p no:randomly
```

Expected: no failures. The Docker tests are skipped with a stated reason when Docker or the sandbox image is missing,
and this file's `test_the_budget` and `test_screenshots_for_the_eye` are skipped without their variables; the new file
adds 40 tests. This plan changes only Mission Control's extension files and its own test file, so a failure anywhere
else isn't its doing: write it into the report, tell the user, and don't fix it here.

- [ ] **Step 3: Run the bench**

Run:

```bash
uv run ai-browser bench
```

Expected: every line says PASS (observe, observe heavy page, click step, type step, open local page, screenshot), as
before this plan: it doesn't touch the engine. The bench starts the Docker sandbox; if Docker isn't running, write
"not run: Docker isn't running" in the report instead of starting it. If it says the sandbox image is missing, write
"not run: no sandbox image" instead: never run `ai-browser build` here, since it downloads base images, which needs
the user's OK.

- [ ] **Step 4: Write the results into the report**

In `docs/superpowers/reports/2026-10-02-mission-visuals.md`, replace:

```markdown
## On Windows
```

with:

```markdown
## The full suite and the bench

| Run | Result |
|---|---|
| `uv run pytest -q -p no:randomly` | |
| `uv run ai-browser bench` | |

## On Windows
```

Fill the two cells with the suite's last line (passed, skipped) and the bench's six results.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/superpowers/reports/2026-10-02-mission-visuals.md
git commit -m "Mission visuals: the README describes the workers and the brain of points"
```

