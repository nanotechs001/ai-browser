# Mission Control visuals: a sentient particle brain and chibi workers

Date: 2026-10-02.

**Status:** written and reviewed by agents, without a user review round. The user chose the visuals below, then said
"yeah then proceed build".

**The user's choice:** for the visuals, "Yes, both": the particle brain and original SVG chibi workers, as in the
prototypes. The user's reference for the workers is a picture of a chibi office worker. That picture is a licensed
Pngtree stock image with watermarks: its style is the brief, and the image itself is never used (see Safety).

**Builds on:** Mission Control (project 6: `mission.html`, `mission.js`, `scene.js`, `blob.js`, `voice.js`;
docs/superpowers/specs/2026-10-02-mission-control-design.md). Line numbers in this spec are those of the baseline
commit (1974d2d).

**Build order:** this spec is built first (wave 1), side by side with the safe-browsing spec. The everyday-Brave and
voice-input specs follow (wave 2), then Windows (wave 3). The safe-browsing spec's last section lists the shared files
and who changes what.

**The specs written the same day** share these things with this one:
- **safe-browsing, built at the same time:** it changes `mission.js` and `scene.js` too, so that a bot check counts as
  **needs you** (`stateOf`, `told`, `fill()`'s state, and the ticker "bot check · <site>"). This spec doesn't touch
  those lines: it changes `build()`, `upsert()`, `update()` and `renderBrain()`, and the desk keeps `.ticker`, so the
  check's ticker lands in it. The Brain's focus reads `stateOf`, so a bot check aims it like a tool request;
- **`voice.js`:** this spec adds `onWord`; the voice-input spec adds `priority`, `pause()` and `resume()`. The changes
  don't overlap;
- **`blob.js`:** the voice-input spec adds a fifth Brain state, `listening`. It is built after this one, so it adds
  `listening` to the particle brain, drawn as decision 4 says, with test 31;
- **agent colours:** the everyday-Brave spec gives agents 7 of the 9 colours (no purple or orange). The tie follows
  whatever colour the agent has;
- **Mission Control's place:** the everyday-Brave spec keeps Mission Control in AI Browser (Google Chrome), and changes
  only the Watch tooltip in `mission.js`.

**Supersedes** these parts of the Mission Control spec:
- "a little robot" and "an animated, glowing blob" (lines 19-27), the station's parts (lines 84-100), and the blob's
  ray-marching shader and gradient orb (lines 135-137);
- "swirls while the Brain sorts, drafts or thinks" (line 49): the brain sends a wave instead, and the orb rocks;
- "the blob moves slowly" under reduced motion (line 63): the Brain is now still (decision 9);
- "up to 5 in the first arc" (line 81): the code seats 6 (scene.js:60), and that stays;
- "avatars beyond the simple robot" under Out of scope (line 245).

Everything else in that spec holds: the room, the camera, the drawer, the messages, the voice, and its safety rules.

**Prototypes,** in a temporary folder outside the project that may be cleared (/private/tmp/claude-501/chibi-brain-probe/):
- brain2.html and brain2.png: the shape and the shaders, in all four states;
- brain3.html: GPU timing against today's blob;
- chibi.js and gallery.png: the character in all six poses, at three sizes;
- room.html and room-*.png: 20 workers in the tilted room, in four build styles;
- ctx.html: the WebGL context limit.

This spec carries every number the build needs. The workers' shapes are the one exception: they are our own drawing, in
chibi.js's table, and the build starts from them (turned into `createElementNS` calls, decision 5). So the plan's first
step copies brain2.html, brain2.png, chibi.js and gallery.png into `docs/superpowers/prototypes/mission-visuals/`, as
references only: nothing in the extension loads them. If the folder is already gone, the shapes are drawn again from
decision 6.

## Goal

Make Mission Control feel alive:
- **the Brain becomes a brain:** thousands of glowing points in the shape of a human brain (two hemispheres with their
  folds, the cerebellum and the stem), turning slowly, with signals running across it. Its motion shows what the Brain
  is doing: a calm drift when idle, a wave when thinking, a heartbeat aimed at the agent that needs the user, and a glow
  that pulses with each spoken word;
- **every agent becomes a little office worker at a desk:** an original chibi character (big head, dark swept hair,
  black glasses, a light suit, a tie in the agent's colour), sitting beside a monitor that shows the agent's tab live.
  His pose shows the agent's state;
- **a new agent arrives with a short scene:** the Brain flares, a spark flies to the new desk, the monitor switches on,
  and the worker pops up and waves.

Success means:
1. **The Brain:**
   - it reads as a brain in screenshots, in all four states, from its usual three-quarter view;
   - it is drawn with points in one WebGL1 canvas; the stage's `data-mode` is `webgl`, and `data-state` follows the
     Brain as today;
   - **alert:** the heartbeat's signals gather on the side facing the oldest station that needs the user, and follow it
     when the user turns the room;
   - **speaking:** the glow pulses once per spoken word, or 5 times a second when the voice reports no words.
2. **Cost:**
   - at most 30 frames a second for the Brain;
   - 8000 points, halved (never below 2500) on a machine whose frames come more than 45 ms apart;
   - one WebGL context on the page, even with 20 agents;
   - no layout while agents work, with 20 agents.
3. **Fallback:** without WebGL, or after the context is lost, a dotted brain silhouette in the state's colour.
4. **Workers:**
   - one per station, with the tie in the agent's colour, and hair and skin picked from the agent's id;
   - a pose for each of the six states.
5. **Arrival:** the spawn scene plays for an agent created while the page is open, and never for agents already there
   when it opens.
6. **Reduced motion:** nothing moves. No animation runs, and a new agent's desk simply appears. The Brain is still: it
   is drawn once when its points are ready, then only for 0.7 s after a change of state or a new agent (a colour fade).
7. **Unchanged guarantees:**
   - text stays text, and no image element shows except the monitors' JPEGs (the art is inline SVG built in code);
   - nothing is downloaded;
   - no new messages and no new permissions.
8. **Tests:** every current Mission Control test still passes (listed under Testing), and 20 agents still fit at
   1280 × 760 without covering each other.

## What the user sees

### The Brain

- **The look:** a brain made of about 8000 tiny glowing points, floating over its ring.
  - It has two hemispheres with their folds, the cerebellum at the back and the stem below.
  - A faint web of links runs over its surface, and sparks of light travel along it.
- **It is alive:**
  - it turns slowly back and forth, showing its left side three-quarters on;
  - its points drift over the surface;
  - it breathes.
- **The states:**
  - **idle:** blue to violet, slow, with a few signals;
  - **thinking** (the Brain sorts, drafts or thinks): cyan, faster. Most links fire, and a wave of light sweeps from front
    to back;
  - **needs you:** amber and coral. It beats like a heart, twice per beat, and its signals gather on the side facing the
    agent that needs the user. When the user turns the room, the glow turns with it;
  - **speaking:** mint. Rings of light spread from the front left (the speech area), one per word.
- **A new agent:** the Brain flares and sends a spark to the new desk.
- **Unchanged:** the count and "what it's doing" under the Brain, the speech bubble above it, and a click opening its
  inbox.

### A station

- **A little desk diorama,** 200 × 156 px:
  - the monitor, at the top left, shows the agent's tab live, as today;
  - a chibi office worker sits beside it, behind the desk, with his hands on the desk's edge;
  - the desk's front carries the agent's name, the state light and the ticker, as text.
- **The worker** is an original character: big round head, dark swept hair, thick black glasses, rosy cheeks, a light
  suit and a tie in the agent's colour (the colour of its tab group). Hair shape and skin tone differ between agents.
- **His pose shows the state:**
  - **working:** he types (his hands tap in turn), nods, looks at the screen and blinks now and then. The screen keeps
    its scan line;
  - **waiting in line:** he sits back, glances around, and checks his watch now and then;
  - **needs you:** he turns to the user, raises a hand and waves, with his mouth open. The station's glow and the
    **needs you** badge stay as today;
  - **done:** a thumbs up, happy eyes and a little hop, and a sparkle when the agent finishes;
  - **failed:** he slumps onto the desk, eyes shut, with a sad mouth and a drop of sweat. The red light and the reason in
    the ticker stay as today;
  - **stopped:** he dozes, eyes shut, his colours greyed.
- **Unchanged:** where stations stand (the rows), how the room fits the window, and a click (or Enter) opening the
  drawer.

### A new agent

In about two seconds:
1. the Brain flares;
2. a spark arcs from the Brain over the floor to the new desk;
3. the monitor switches on;
4. the worker pops up from behind the desk and waves once, then gets to work.

Agents that were already there when the page opens simply appear, as today.

### With Reduce Motion on

- The Brain is still, in its state's colour. A change of state is a short colour fade.
- Workers hold their poses without moving: the raised hand, the thumbs up and the slump still show the state.
- A new agent's desk appears at once, with the worker already seated. The Brain gives one colour flash.

### Without WebGL

The Brain is a dotted brain silhouette in the state's colour, which breathes, rocks, beats or talks the same way.

## Decisions

### 1. The Brain is a point cloud, drawn by blob.js in one WebGL1 context

- **The file stays.** `blob.js` keeps its name and `createBlob(canvas, orb, {reduced})`, so mission.js:3 and
  mission.js:44 don't change. The ray-marched sphere (blob.js:9-67) goes.
- **WebGL1 only:** `canvas.getContext("webgl", {alpha: true, premultipliedAlpha: true, antialias: false})`, as today
  (blob.js:169). test_mission.py:565 asks the page's canvas for `getContext('webgl')`, which would be null on a WebGL2
  canvas.
- **Two programs, three draws a frame,** blended with `ONE, ONE_MINUS_SRC_ALPHA` (premultiplied colours):
  1. **the web:** faint lines between linked points (`gl.LINES`, 2 vertices per link, at most 900 links);
  2. **the pulses:** one bright point travelling along each link (`gl.POINTS`, at most 900 — always fewer than 1000,
     which the tests use to tell them from the cloud);
  3. **the cloud:** `gl.POINTS`, `n` points, 8000 by default.
- **Kept from today:**
  - the 30 fps cap (`FRAME_MS`, blob.js:68 and 126-132);
  - the canvas size: at most 360 CSS px, at a device pixel ratio of at most 2 (blob.js:166-167);
  - `#brain` at 300 × 300 (mission.css:58, 62), so BRAIN_SHAPE stays near 1;
  - the `u_mix` easing toward the target state (blob.js:137-140), in normal motion;
  - `fallback()` and the context-lost handler (blob.js:89-97, 178-181);
  - the API `{mode, setState, destroy}`, and the stage's `data-state` and `data-mode` (blob.js:83, 94, 175).
- **New:**
  - `burst(direction)`, `focus(direction)` and `word()` (Messages and interfaces, below). In css mode they do nothing;
  - `stage.dataset.points`: the number of points drawn, written only when it changes (a DOM write every frame would
    cost style work), and removed by `fallback()`;
  - every uniform the tests read (`u_mix`, `u_burst`, `u_focus`, `u_word`, and `u_listen` once it exists) is set on
    every drawn frame.
- **Points are made after the first paint:**
  - `createBlob` reads the canvas size, builds the context and both programs at once, and sets `data-mode` to `webgl`,
    as today. But the canvas stays hidden and the orb (the dotted silhouette) shown for now: `.brain` is a grid, and the
    two would sit one under the other if both showed;
  - the points are generated in a task after the first animation frame (17-25 ms for 6-16k points on the M5 Mac). A
    slower laptop waits a little longer for the brain; the page doesn't;
  - that task wakes the drawing loop, so a still brain (reduced motion) is drawn at least once;
  - the first frame with points is drawn into the hidden canvas, then, in the same frame, the canvas shows and the orb
    hides;
  - a lost context cancels a generation still pending, so the orb keeps the stage.
- **Why:**
  - the prototype reads clearly as a brain; today's sphere reads as a planet;
  - it is cheaper. On the M5 at 600 × 600 device px, the GPU takes 0.47-1.25 ms a frame for 6-16k points, against
    0.97-1.65 ms for today's sphere. Its cost grows with the number of points, not with pixels × ray-march steps, which
    suits the integrated GPU (ANGLE on Direct3D 11) of the user's Windows laptop;
  - no library, so nothing to download (the Mission Control spec's decision 2 holds);
  - every blob and orb test keeps working.

### 2. The shape is generated from a seed, in a pure module

- **New file `brainshape.js`:** no DOM, no WebGL and no `Math.random`. Random numbers come from mulberry32, and the
  noise is integer-hash value noise, so one seed always gives the same brain.
- **`brainPoints(count = 8000, seed = 7)`** returns a `Float32Array` with 6 numbers per point: `x, y, z, kind, fold,
  phase`.
  - **Axes:** x across (+x is the brain's own left), y up, z toward the brain's front.
  - **kind:** 0 cortex, 1 cerebellum, 2 stem, 3 core.
  - **fold:** 0 in a groove to 1 on a ridge. **phase:** a random number from 0 to 1, for each point's own timing.
  - **The mix is exact:** cortex `round(0.80·count)`, cerebellum `round(0.11·count)`, stem `round(0.05·count)`, and the
    core the rest. For 8000, that's 6400, 880, 400 and 320.
- **The recipe,** as prototyped:
  - **Cortex:**
    - pick a hemisphere, h = ±1, and a random direction (dx, dy, dz) on the unit sphere;
    - stretch it to an ellipsoid: x = 0.42·dx, y = 0.47·dy, z = 0.70·dz;
    - **the gap between the hemispheres:** on the inner side (x·h < 0), x × 0.30;
    - **a flatter underside:** below y = −0.12, the part below is × 0.55;
    - **the back narrows:** where dz < −0.35, x × 0.92 and y × 0.94;
    - **the temporal lobe hangs down at the side:** with T = exp(−(z − 0.10)²/0.05 − (y + 0.20)²/0.02)·|dx|,
      y −= 0.10·T and x += 0.05·h·T;
    - move it to its hemisphere's centre, (0.17·h, 0.06, 0);
    - **the two big grooves:** reject a point in the lateral groove (|dx| > 0.45, −0.2 < z < 0.34 and
      |y − (−0.07 + 0.30·(0.34 − z))| < 0.025) or in the central groove (y > 0.05, x·h > 0.05 and
      |z − (0.02 + 0.25·(y − 0.05))| < 0.018);
    - **the folds:** fold = ridged value noise at frequency 9.5: 2 octaves, each 1 − |2·noise − 1|, with weights 0.65
      and 0.65 × 0.35, the second at 2.3 times the frequency, divided by their sum (0.8775) so it runs 0 to 1. Keep the
      point with probability 0.04 + 0.96·fold⁶, so points crowd onto the ridges and the maze shows;
    - **the grooves sink:** move the point by 0.03·(fold − 0.6) along its normal (the point minus its hemisphere's
      centre, normalised).
  - **Cerebellum:** two small ellipsoids at (±0.13, −0.30, −0.42), radii (0.20, 0.14, 0.19), on a random direction
    (dx, dy, dz). Points that face inward (dx·h < −0.3) are rejected. Its fine horizontal folds:
    folia = 0.5 + 0.5·sin(120·(y + 0.3) + 4·dz); keep with probability 0.1 + 0.9·folia², and folia is the point's fold.
  - **Stem:** t from 0 to 1 down its length, centred at (0, −0.18 − 0.62·t, −0.10 − 0.12·t), each point on the circle
    around that centre in the x-z plane. Its radius tapers, with a bulge for the pons: 0.075 − 0.02·t +
    0.035·exp(−(t − 0.25)²/0.01). Fold 0.6.
  - **Core:** faint points inside, at (0, 0.04, 0), within radius 0.32·∛u, scaled by (0.9, 0.7, 1.3). Fold 0.3.
  - **Every rejection loop has a guard** (count × 40 tries). The stem and core never reject, and the stem fills up to
    the cortex, cerebellum and stem total, so the total is always exact. With the default seed, no guard runs out, so
    the mix is exact too (test 2).
  - **Shuffled at the end** (Fisher-Yates, same random stream). Any first N points are then an even sample of the whole
    brain, so the level of detail is one argument: `drawArrays(POINTS, 0, n)`.
- **`synapses(points, {picks = 450, perNode = 2, max = 900, seed = 3})`** returns a `Uint16Array` of index pairs (so
  `count` is at most 65536):
  - walk the points in order, and pick cortex points with probability 0.12, up to 450;
  - link each pick to its 2 nearest other picks between 0.06 and 0.22 away, up to 900 links;
  - each link's phase is (link number × 0.618) mod 1;
  - the link buffers hold copies of both ends' positions, so the web doesn't depend on how many points are drawn.
- **Also exported:** `KIND`, and `HEMISPHERES`, the two centres used for the normals.
- **Why:**
  - it can be tested in a page without a GPU;
  - one seed gives the same brain every time, so screenshots compare;
  - the level of detail is just the prefix;
  - there's no asset file to ship.

### 3. What makes it feel alive

- **Every per-state number** below is blended by the state weights (`u_mix`, and `u_listen` once it exists): the value
  is the weights' dot product with the table's numbers in decision 4, so a change of state never jumps.
- **The view:**
  - **the turn:** about the y axis, x′ = x·cos yaw + z·sin yaw and z′ = −x·sin yaw + z·cos yaw. At yaw −55° the brain's
    left side (+x) faces the user and its front points to the screen's left, so the speech area (the left frontal
    lobe) faces the user. A straight front view would look like two blobs;
  - **the sway:** yaw = −55° + 30°·sin φ. The phase φ is kept in JavaScript and advances by 2π per sway period (decision
    4), so a change of period never jumps;
  - **a slight nod:** pitch = 0.22 + 0.05·sin(0.6·φ) radians, about the x axis: y′ = y·cos p − z·sin p and
    z′ = y·sin p + z·cos p, so the user looks down onto it a little;
  - **perspective:** 2.6 / (2.6 − z′), then × 1.05 in clip space. The stem's tip then lands about 27 px above the
    canvas's bottom edge, clear of the count label, which overlaps the canvas's bottom 24 px (mission.css:72);
  - **breathing:** scale 1 + 0.015·sin(1.3·t), t in seconds.
- **Drift along the surface:** each point wanders on a small Lissajous path from its `phase`: (sin(0.7·t·s + 2π·phase),
  cos(0.5·t·s + 3.4π·phase), sin(0.6·t·s + 4.6π·phase)) × the state's drift, with s the state's motion speed. For cortex
  points, the part along the normal is removed, so they slide over the surface without leaving it. Other points drift
  half as much.
- **Synapse flashes:** flash = pow(max(0, sin(t·rate + 37·2π·phase)), 60), with the state's flash rate. A flashing
  point gets brighter by 1.2·flash (towards white) and larger by × (1 + 1.6·flash). These are sparse, random sparks.
- **Travelling pulses:**
  - a bright 4 px point moves along each link on a quadratic curve through the link's midpoint pushed 0.04 further from
    the brain's centre (the origin), so it follows the cortex;
  - its position is t = fract(time·speed + link phase), with the state's pulse speed;
  - a link fires when fract(7·link phase) < the state's share of links firing;
  - over the last 15% of its path the pulse swells to twice its size and brightens, so the target point seems to flash;
  - links that don't fire show only as the faint web (alpha 0.10).
- **Depth and size:**
  - nearer points are brighter: 0.45 + 0.55·smoothstep(−0.8, 0.8, z′);
  - points are soft round sprites of 1.5 CSS px × the pixel ratio × perspective, larger when they flash;
  - when the level of detail drops, points grow by √(8000 / n), at most × 1.6, so the brain keeps its body.
- **Colours:** each point mixes the state's two colours by its fold (ridge colour at fold 1, groove colour at fold 0),
  so the ridges are bright. Other points are drawn at 0.85 alpha × depth; core points are 30% whiter and drawn at 0.35
  alpha × depth.

### 4. The states

The state is picked exactly as today (mission.js:156-163): speaking, then thinking, then alert, then idle (the
voice-input spec puts listening first). `u_mix` holds the weights of today's four states, in that order: idle,
thinking, alert, speaking.

| State | Colours (ridge → groove) | Motion speed | Drift | Flash rate | Pulse speed | Links firing | Sway period |
|---|---|---|---|---|---|---|---|
| idle | indigo-blue (0.30, 0.45, 1.00) → violet (0.70, 0.50, 1.00) | 0.25 | 0.006 | 0.35 | 0.15 | 10% | 20 s |
| thinking | cyan (0.30, 0.85, 1.00) → violet (0.65, 0.50, 1.00) | 1.0 | 0.020 | 2.2 | 0.84 | 85% | 12 s |
| alert | amber (1.00, 0.55, 0.30) → coral (1.00, 0.30, 0.25) | 0.6 | 0.010 | 1.2 | 0.54 | 60%, weighted by the focus | 20 s |
| speaking | mint (0.30, 0.95, 0.75) → teal (0.55, 1.00, 0.90) | 0.8 | 0.010 | 1.6 | 0.60 | 50% | 20 s |
| listening | white (1.00, 0.95, 0.98) → rose (0.95, 0.55, 0.85) | 0.25 | 0.004 | 0 | 0.30 | 20%, weighted toward the user | still |

Each state also has its own motion:
- **thinking:** a wave of light sweeps front to back and back again: points brighten by
  exp(−(z − 0.7·sin(1.6·t))²/0.01), with z in the brain's own frame;
- **alert:** a double heartbeat every 1.1 s. With τ the time since the beat began and b(x) = exp(−(x / 0.06)²), the
  scale grows by 0.035·b(τ) + 0.02·b(τ − 0.22), and every point brightens by up to 25% with it. Signals gather toward
  the focus (below);
- **speaking:** rings of light spread from the speech area at (0.30, 0.0, 0.35), one per word (below);
- **listening:** the sway eases to a stop at yaw −55° (its 30° is × (1 − `u_listen`), and its phase stops), and the
  signals gather on the side facing the user, as if the focus were {0, 1}.

The colours are in the same families as the orb's (mission.css:63-71) and the accent (#d97757, mission.css:5).

- **Listening, from the voice-input spec:**
  - that spec adds the state, and, being built after this one (wave 2), puts it in the particle brain as this decision
    says. This spec leaves `u_listen` out;
  - `STATES` (blob.js:7) gains `listening`, so `setState('listening')` sets `data-state`;
  - its weight is a separate float, `u_listen`, so `u_mix` keeps today's four weights and the tests that read it hold;
  - the dotted brain takes its colours from the orb's `listening` rule, which the voice-input spec adds to mission.css.

- **Focus (alert):**
  - `focus(direction)` takes a unit direction in the viewer's frame (x to the right of the screen, z toward the user),
    or `null`, which is (0, 0). `u_focus` moves to it linearly over 0.5 s;
  - in alert, pulse and flash activity is × (0.35 + 0.65·smoothstep(−0.2, 0.8, dot(point's direction, focus))), where
    the point's direction is its (x′, z′) after the view turn, normalised. The side facing the station lights up,
    whatever the brain's sway. With a focus of (0, 0), the factor is the same everywhere: the heartbeat is even;
  - mission.js aims it at the oldest agent (by `created`) whose `stateOf(agent)` is `needs_you`: a tool request, or,
    with the safe-browsing spec, a bot check. When only inbox items need the user, the focus is `null`;
  - it is recomputed in `renderBrain()` and after every camera change, through a new `onCamera` callback that
    `createScene` calls at the end of `apply()` (scene.js:123-131).
- **Words (speaking):**
  - `voice.js` sets `utterance.onboundary`, and calls a new `onWord` callback for each event whose `name` is `word`;
  - mission.js passes `() => blob.word()`;
  - `word()` sets `u_word` to 1, and it fades linearly to 0 over 0.6 s. Meanwhile a ring spreads from the speech area:
    points whose distance d from it is within 0.05 of 0.6·(1 − `u_word`) brighten by `u_word`;
  - with no word for 0.4 s while the state is speaking (some voices report none), the blob calls `word()` itself,
    5 times a second, until a word comes or the state changes.
- **Spawn:** `burst(direction)` sets `u_burst` to 1, and it fades linearly to 0 over 0.8 s:
  - every point brightens by `u_burst` and is pushed out by 3%·`u_burst` along its normal;
  - the links whose midpoint, after the view turn, faces `direction` (a positive dot product) fire while `u_burst` is
    above 0.2. The direction goes in its own uniform, `u_burst_dir`.
- **Under reduced motion** focus, words and the burst's pulses do nothing: they only shape pulses, flashes and rings,
  which are off. A burst is a colour flash (decision 9).

### 5. The workers are HTML layers, each holding a small SVG, posed by CSS

- **New file `chibi.js`:**
  - `createWorker(id)` returns a `div.worker` with `aria-hidden="true"`, holding one `div.part.<name>` per part;
  - each part holds one small `<svg viewBox="0 0 80 88">`, built with `createElementNS` from a fixed table of shapes in
    the code (a tag and its attributes, about 60 paths in all). Nothing is parsed from strings, and there is no
    `innerHTML`;
  - `ensureDefs(document)` adds one `<svg>` per page with the shared gradients: `mc-skin-0` to `mc-skin-2`,
    `mc-hair`, `mc-suit`, `mc-cheek`, `mc-lens`. `url(#…)` reaches across the SVGs of a page (confirmed in the
    prototype). That `<svg>` is 0 × 0, absolutely placed and `aria-hidden`, but never `display: none` or `hidden`
    (mission.css:23 makes `[hidden]` `display: none`): gradients inside an undisplayed SVG don't paint. scene.js calls
    it once, in `createScene`;
  - `variantOf(id)` takes the FNV-1a 32-bit hash of the id's UTF-16 code units (offset 0x811c9dc5, prime 0x01000193):
    hair = h mod 3, skin = ⌊h / 3⌋ mod 3. They are written on the worker as `data-hair` and `data-skin`. The ids a1 to
    a20 cover all 9 combinations;
  - **the variant reaches the art only through those numbers:** `createWorker` builds only its hair shape (one of three
    in the table); shapes in the skin colour carry the class `skin`, and CSS fills them from `data-skin`
    (`.worker[data-skin="1"] .skin { fill: url(#mc-skin-1) }`);
  - **the tie's colour** comes only from the CSS rule `.worker .tie { fill: var(--c) }`, never from an attribute.
- **The parts,** back to front. Their names are stable (the "skin seam": other art can replace a part later):

  | Part | Layer | What it holds | Shown |
  |---|---|---|---|
  | body | 1 | suit, lapels, shirt, the tie (`.tie`, filled with `var(--c)`), neck | always |
  | head | 1 | ears, head, the hair (one of 3 shapes) | always |
  | face | 1 | brows, cheeks, glasses with glints; eyes in three sets (`.eyes-open`, `.eyes-happy`, `.eyes-shut`); mouths (`.mouth-smile`, `.mouth-o`, `.mouth-sad`) | always |
  | blink | 1 | lids in the skin colour, with shut-eye lines | for a blink |
  | sweat | 1 | a drop of sweat | failed |
  | arm-l, arm-r | 3 | arms, and hands on the desk's edge | most states |
  | arm-up | 3 | a raised hand | needs you, and the arrival wave |
  | arm-thumb | 3 | a thumbs up | done |
  | sparkle | 3 | a small star | once, as the agent finishes |

  The monitor is layer 0, and the desk's front is layer 2, so the body sits behind the desk and the hands in front of
  it. Every part is an absolutely placed `div` filling the worker's box, with its layer as its `z-index`.
- **Head, face and blink move together:** every head motion (the nod, the droop, the slump, sitting back) is a
  `transform` on all three, with the same keyframes and timing. Where the eyes look (toward the screen, toward the
  user, the glance) is the `translate` property of the face and blink parts, which adds to their `transform` instead
  of replacing it.
- **Poses come from CSS only,** keyed on the station's `data-state` (scene.js:175-176). No JavaScript runs per frame:

  | State | Pose |
  |---|---|
  | working | hands tap in turn (0.32 s); the head nods (1.6 s); the face looks toward the screen (3.5 px left); a blink (the lids show for 150 ms) every 5 s |
  | waiting | sits back (the head, face and body 2 px lower); the face glances left and right (5 s); arm-l lifts to check the watch for 1 s in every 8 s |
  | needs_you | the face turns to the user; arm-r hides and arm-up waves from the shoulder (1 s); `.mouth-o` |
  | your_turn | the face turns to the user; arm-r hides and arm-thumb shows; `.eyes-happy`; every part hops 3 px once every 2.4 s; the sparkle plays once (0.8 s) when the state starts |
  | failed | head and body tip forward and drop onto the desk (a static transform); `.eyes-shut`, `.mouth-sad`; the sweat drop slides down 4 px over 3 s, again and again |
  | stopped | `.eyes-shut`; the head droops 2 px; slow breathing (4 s); every part greyed with `filter: saturate(0.4) brightness(0.8)` |
  | anything else | seated and still, eyes open, smiling |

  The blink and the glance start later for each worker, by 0.6 s × `data-hair` + 0.2 s × `data-skin` (a negative
  `animation-delay`), so neighbours don't move in step.

- **Hard rules,** from the measurements:
  - in the worker, animate only `transform` and `opacity`, and only on the `.part` HTML wrappers. Never animate SVG
    elements (`<g>`, `<path>`): animating SVG groups cost one layout per frame (180 in 3 s with 20 agents), which fails
    the no-layout test (test_mission.py:391-413);
  - inside an SVG, only state rules change things (which eyes, which mouth): a static opacity, never an animation;
  - nothing on `.worker` itself may create a stacking context: no `transform`, `filter`, `opacity` below 1,
    `will-change`, `z-index` or `isolation`. The prototype showed that the hands then drop behind the desk. An effect
    that must cover the whole worker (stopped's grey) goes on each part;
  - the monitor's boot line and scan line, and the spark, are HTML elements outside the worker, animated the same way
    (`transform`, `translate` and `opacity`);
  - no WebGL and no canvas in a station.
- **Why:**
  - the measured cost for 20 agents is in the same class as today's robots (decision 10);
  - text stays text, and the art never holds agent data;
  - the poses are visible to DOM tests;
  - nothing to download;
  - the stable part names let pre-rendered art drop in later, if the user ever wants it and approves it.

### 6. The character: original, in the reference's style

- **The style, taken from the reference:**
  - chibi proportions, shown as a half body behind a desk, so the head is about 55% of what shows;
  - a big round head with soft skin shading;
  - dark brown swept hair with a highlight;
  - thick black rounded-rectangle glasses with lens glints;
  - large brown eyes with two catch-lights, rosy cheeks and a small smile;
  - a light suit with lapels and a white shirt.
- **Its own design,** never a copy:
  - its own hair shapes: 0 a swept quiff, 1 a side part with a fringe, 2 a short crop. The hair is always dark brown to
    near black;
  - three skin tones: 0 light, 1 medium, 2 deep;
  - the half-body desk pose and its own face geometry;
  - the tie in the agent's colour;
  - every shape hand-written in SVG, from a written description of the style.
- **Variety:** 7 to 9 tie colours (7 once the everyday-Brave spec lands) × 3 hair shapes × 3 skin tones are enough that
  20 agents rarely look alike.
- **Honest expectation:** this is a 2D illustrated cousin of the reference (see gallery.png in the prototypes), with the
  same feel and flatter shading. The reference's soft 3D render would need pre-rendered art, which is out of scope.

### 7. The station: a desk diorama

- **Size:** 200 × 156 px, from 176 × about 168. The height is fixed, so the layout never depends on the content.
- **The parts,** built once in `build()` (scene.js:148-171) and updated in place by `fill()` (scene.js:173-183):

  ```
  button.station.billboard        data-id, data-state, --c (as today); 200 px wide
    div.card                      200 × 156, position relative, 10 px padding, overflow hidden
      div.monitor                 132 × 84, at (10, 10): img.shot, div.scan, div.boot
      div.stand                   under the monitor, down to the desk
      div.worker                  70 × 77, 4 px from the right, 45 px from the bottom (from chibi.js)
      div.desk                    the bottom 50 px, layer 2:
        div.plate                   span.nameplate, span.light
        div.ticker
    span.badge                    "needs you"
  ```

- **The card clips its content,** so a part rising from below the desk (the arrival) never shows under the card. Its
  border glow (`box-shadow`) and focus outline aren't clipped by its own `overflow`, and the badge sits outside it.
- **Kept:** `.nameplate`, `.light`, `.ticker`, `.badge`, `.monitor img.shot` and `.scan` keep their names and rules
  (mission.css:98-103, 117-136), so the tests that read them hold; only `.monitor`'s size changes, from 92 px high and
  the card's width to 132 × 84. The needs-you glow, the light colours, and the dimmed card for stopped and done
  (mission.css:128) stay too.
- **Gone:** `.robot` and the old `.head` row (scene.js:153, 158, 160; mission.css:104-116). No test reads them.
- **Placement unchanged:** `SEAT` 240, `ROW` 340, `BACK` 440, `at()`, `rowSeats()` and `placeOf()` (scene.js:32-68).
  - 240 between seats still leaves a 40 px gap between 200-wide cards;
  - rows are 340 apart on the floor: about 180 px on screen at the same zoom, more than a card's 156 px height.
- **The screen fit, re-tuned:**
  - scene.js exports `CARD = {w: 200, h: 156}`, so the code, the CSS and the tests agree;
  - `fit()`'s width term becomes `2 * extent.dx + CARD.w + 64` (264, from 240, scene.js:118);
  - `fits()`'s far-card height becomes `CARD.h + 24` (180, the same value as today, scene.js:111);
  - the shadow grows to 240 × 90, with its margins to match (mission.css:50).
- **If 20 agents no longer fit** at 1280 × 760 (test_mission.py:365-374), `fit()` is re-tuned first, and `CARD` (with
  test 23 below) only if that can't work. The placement and test_mission.py's tests don't change.

### 8. The arrival scene

- **Only for agents new to this page:**
  - in `update()` (mission.js:130-140), `fresh = agentsKnown && !before`. `agentsKnown` is false until the first
    snapshot is in (mission.js:18, 346);
  - mission.js calls `scene.upsert(agent, {fresh})`, then `blob.burst(scene.directionTo(agent.id))`.
- **Who does what:** scene.js's `upsert(agent, {fresh: true})` adds `.spawning` to the new station and flies the spark,
  unless `matchMedia('(prefers-reduced-motion: reduce)')` matches at that moment. mission.js fires the burst.
- **The steps,** in normal motion:
  1. **0 ms, the burst:** the Brain flares and fires toward the new seat (decision 4).
  2. **0-700 ms, the spark:**
     - a `div.spark.billboard` with `pointer-events: none`, an 18 px glowing dot in the agent's colour, appears at the
       Brain (`left`/`top` set once, at CENTER);
     - `element.animate()` moves its `translate` property along 9 keyframes, linear between them, at f = 0, 1/8, … 1:
       (f·dx, f·dy, z) with z = 200 − 140·f + 440·f·(1 − f) px. (dx, dy) is the new seat minus CENTER in room px, so
       it starts 200 px up at the Brain, peaks 240 px up halfway, and lands 60 px up at the new desk. These are the
       room's own coordinates, so it arcs over the floor whatever the camera does;
     - it is removed when the animation finishes.
  3. **700-1000 ms, the monitor boots:** `.boot`, a bright line, grows across the screen, opens to full height and fades
     (transform and opacity).
  4. **850-1300 ms, the worker pops up:** each part behind the desk (layer 1) slides up from 80 px lower, with an
     overshoot; below the desk it is hidden by the desk and the card's clip. The arms (layer 3) are in front of the
     desk, so they stay at opacity 0 until 1150 ms, then fade in over 100 ms.
  5. **1300-1900 ms, the wave:** arm-up waves once (arm-r hidden meanwhile), then the state's pose takes over.
  6. **2000 ms:** a timer removes `.spawning`. A timer, not `animationend`, which never fires when animations are off.
- **Steps 3 to 5** are CSS animations with delays, under `.station.spawning`. They come after the pose rules, with
  higher specificity.
- **Several at once:** each new agent gets its own spark, with at most 6 in flight; any more skip the spark. A new
  burst restarts the Brain's.
- **Reduced motion:** no spark and no `.spawning`. The station appears as today, and the burst is a colour flash.
- **Kept:** every station's arrival fade (`arriving` and `placing`, scene.js:149, 166-169), so stations still open in
  their places (test_mission.py:416-424).

### 9. Reduced motion

- **CSS:** the existing rule (mission.css:204-207) stops every CSS animation. The poses are static rules (the raised
  hand, the thumbs up, the slump, the shut eyes), so the state still shows.
- **The spark** uses `element.animate()`, which that rule doesn't stop, so the code skips it under reduced motion.
- **The Brain:**
  - no drift, sway, breathing, beats, flashes, waves, rings or pulses; a fixed yaw of −55° and pitch of 0.22; drawn in
    the state's colour, with the web faint and still;
  - it is drawn once when its points are ready;
  - on a change of state, `u_mix` moves in a straight line to the new state over 0.7 s and lands exactly on it, then
    drawing stops. Today it eases at 1.5 a second (blob.js:138), which takes about 4 s to settle;
  - a burst is a colour flash that fades over 0.7 s, then drawing stops.
- **It follows the setting live,** through the existing `change` listener (blob.js:182). On Windows, turning off
  "Animation effects" sets the same media query.

### 10. Performance budget

**Measured** on the M5 Mac in headless Chrome, 20 typing workers inside a copy of the room's CSS (its perspective and
preserve-3d billboards), 1280 × 760, over 3 s:

| Build | Layouts | Style recalcs | Main-thread task time |
|---|---|---|---|
| SVG `<g>` groups animated by CSS | 180 (one a frame) | 180 | 220 ms |
| HTML layers, each holding an SVG (chosen) | 0 | 180 (46 ms) | 125 ms |
| Today's robots | 0 | 181 (28 ms) | 84 ms |
| One canvas per station at 15 fps | 0 | 0 | 73 ms (script 26 ms) |
| Static, nothing animated | 0 | 0 | 37 ms |

- `will-change` didn't change the HTML-layer numbers, and neither did removing the 3D room.
- **The Brain:** 0.47-1.25 ms of GPU a frame for 6-16k points at 600 × 600 device px (each frame followed by a
  one-pixel `readPixels`, which waits for the GPU); about 15 ms of main-thread time a second; 0 layouts and 0 style
  recalcs; exactly 90 frames in 3 s with the cap.
- **The context limit:** with 20 WebGL contexts on a page, the 4 oldest were lost, so the limit is 16. The Brain's
  context is the oldest, so it would die first.

**The budget,** with 20 agents working and the Brain thinking, at 1280 × 760, over 3 s on the M5:
- **layouts:** none from animations (tested: fewer than 10 in 2 s);
- **style recalcs:** at most one a frame, and at most 60 ms in all;
- **main-thread task time:** at most 250 ms (about 170 ms expected: 125 for the workers and 45 for the Brain);
- **the Brain's GPU time:** at most 1.5 ms a frame;
- **frames:** the Brain at most 30 a second; CSS animations at the display's rate, on `transform` and `opacity` only;
- **WebGL contexts:** one.
- **Adaptive detail:**
  - start at 8000 points;
  - over a window of at least 2 s of drawn frames, if they average more than 45 ms apart, halve `n`, never below 2500;
  - a gap over 250 ms (a hidden tab, or a pause under reduced motion) throws the window away;
  - `n` never grows back while the page is open.
- **How it's checked on the M5:** test 29 (`test_the_budget`, run with `AIB_PERF=1`).
- **On Windows:** measured on the user's laptop, in AI Browser (Google Chrome, where Mission Control runs; WebGL on
  ANGLE over Direct3D 11). The test stack can't run there yet (the Windows spec keeps the pipe-based UI tests on the
  Mac), so it is done by hand, as part of the Windows spec's manual laptop check, once the repo exists:
  - open Mission Control, open DevTools on it, and run `PERF_ROOM`, a snippet kept in tests/test_mission_visuals.py. It
    imports scene.js and builds a second room over the page with 20 working stand-in stations (`p1` to `p20`). They
    are only drawn: nothing is sent, and a reload removes them;
  - record 3 s in DevTools' Performance panel, and write down layouts, style recalcs (count and time) and total task
    time;
  - if style recalcs take more than 150 ms in 3 s, move the hands to `steps()` timing;
  - if that is still over, a one-canvas-per-station mode is the next step, in its own spec.
- This plan is done when the M5 numbers meet the budget. The Windows numbers decide only whether those two steps follow.

### 11. What was rejected, and why

- **three.js:**
  - it would be a download, which needs the user's OK;
  - no 3D model of the character exists;
  - the room would need a rewrite, which breaks the tests that read its transform (test_mission.py:90-91,
    scene.js:127).
- **WebGL characters:** one context per station hits the limit of 16, and the Brain's dies first. One shared overlay
  can't sit between the DOM cards.
- **Animating SVG groups:** a layout every frame.
- **One canvas per station:** the lowest main-thread cost, but poses would be invisible to the DOM, reduced motion would
  live in JavaScript, and it blurs on zoom. It is kept as the fallback if Windows needs it.
- **Pre-rendered art:** the closest to the reference's look, but it needs art to be generated or commissioned, which
  needs the user's OK. It can come later through the stable part names.

### 12. Order of work

1. Copy the prototypes into `docs/superpowers/prototypes/mission-visuals/` (above).
2. `brainshape.js` and its tests.
3. The renderer swap in `blob.js`, with every existing blob and orb test still passing, then the new Brain tests.
   `listening` is left to the voice-input spec, built next (decision 4).
4. The dotted-brain fallback in CSS.
5. `chibi.js`: the art, the defs, the variants and the pose CSS, with the pose tests.
6. The station re-layout (200 × 156, `CARD`, `fit()`), with the overlap and spacing tests.
7. The arrival scene, the focus, and `onWord`.
8. Screenshots checked by eye, then the performance pass on the M5 (test 29). The Windows measurement joins the Windows
   spec's manual laptop check.

## Messages and interfaces

**No new messages.** The page reads `snapshot`, `agent`, `agent_closed`, `thumb`, `thumbs` and `brain_*` as today, and
sends nothing new (the Mission Control spec's Messages section).

**`brainshape.js` (new):**
- `brainPoints(count = 8000, seed = 7) → Float32Array` (6 numbers per point: x, y, z, kind, fold, phase);
- `synapses(points, {picks = 450, perNode = 2, max = 900, seed = 3}) → Uint16Array` (index pairs);
- `KIND = {cortex: 0, cerebellum: 1, stem: 2, core: 3}`;
- `HEMISPHERES = [[-0.17, 0.06, 0], [0.17, 0.06, 0]]`.

**`blob.js` (rewritten inside):**
- `createBlob(canvas, orb, {reduced, count = 8000, seed = 7}) → {mode, setState(state), burst(direction),
  focus(direction), word(), destroy()}`;
- **a direction** is `{dx, dz}`, a unit vector in the viewer's frame (dx toward the right of the screen, dz toward the
  user), or `null`;
- `burst`, `focus` and `word` do nothing in css mode;
- **the stage's dataset:**
  - `state`: idle, thinking, alert or speaking (and listening, with the voice-input spec);
  - `mode`: webgl or css;
  - `points`: the number of points drawn, in webgl mode only;
- **uniform names the tests read,** set on every drawn frame: `u_mix` (vec4: idle, thinking, alert, speaking),
  `u_burst` (float), `u_focus` (vec2), `u_word` (float), and `u_listen` (float) once listening exists. The others
  (`u_time`, `u_yaw`, `u_pitch`, `u_dpr`, `u_size`, `u_pulse`, `u_burst_dir`) are free to change.

**`scene.js`:**
- `createScene(root, {onSelect, onCamera})`. `onCamera()` is called at the end of every `apply()`: turn, zoom, reset,
  resize and layout. It is not called by the first `apply()` inside `createScene` (scene.js:237): the blob doesn't
  exist yet then (mission.js:25 comes before mission.js:44);
- `upsert(agent, {fresh = false} = {})`: with `fresh`, and without reduced motion, it adds `.spawning` and flies the
  spark (decision 8);
- `directionTo(id) → {dx, dz} | null`:
  - from CENTER to the station's seat, turned by the camera's spin s into the viewer's frame:
    dx = x·cos s − y·sin s and dz = x·sin s + y·cos s, normalised, with (x, y) the seat minus CENTER in room px;
  - check: a seat straight in front of the Brain gives {0, 1} at spin 0, and {0, −1} at spin 180°;
- `export const CARD = {w: 200, h: 156}`.

**`chibi.js` (new):**
- `createWorker(id) → HTMLDivElement`: `.worker`, `aria-hidden`, `data-hair`, `data-skin`, and the parts;
- `variantOf(id) → {hair, skin}`;
- `ensureDefs(doc)`: safe to call more than once;
- `PARTS`: the part names, back to front.

**`voice.js`:** `createVoice({bubble, onSpeaking, onBlocked, onWord = () => {}, hold})`. `speak()` sets
`utterance.onboundary`, and `onWord()` fires for each event whose `name` is `word`. This spec changes nothing else in
voice.js (the voice-input spec's `priority`, `pause()` and `resume()` are its own).

**`mission.js`:**
- `update()`: works out `fresh`, calls `scene.upsert(agent, {fresh})`, and calls `blob.burst(...)` when fresh;
- `renderBrain()`: also calls `blob.focus(...)` for the oldest agent that needs the user;
- `createScene(..., {onCamera: aimBrain})` and `createVoice(..., {onWord: () => blob.word()})`.

**`mission.css`:** new sections for the dotted brain (`.orb`), the station diorama, the worker's parts and poses,
`.spawning`, and `.spark`. The dotted brain:
- `.orb` becomes 240 × 180 px, with no border radius and no box-shadow;
- **the dots are the orb's `::before`** (absolutely placed over the whole orb): a dot pattern (a `radial-gradient`
  repeated every 6 px) in the state's colours (`--a`, `--b`, as today, and the `listening` rule once the voice-input
  spec adds it, in white and rose), with one more background layer for the lateral groove, a faint dark stripe across
  its lower third;
- **that `::before` is cut to a side-view brain silhouette** with `mask-image`, front to the left: one wide ellipse (the
  cerebrum), a small one low at the back, on the right (the cerebellum), and a short bar (the stem);
- **the glow is the orb's own background,** a soft radial gradient in `--glow`. A mask on the orb itself would cut its
  own glow and pseudo-elements too, so the mask stays on `::before`;
- **its motion,** through `transform` on the orb only, and off under reduced motion as today: breathe (idle, as today);
  rock (thinking: ±4° and a 4% swell over 1.1 s, instead of today's full spin); a double beat (alert: scale 1.06, then
  1.03 0.22 s later, every 1.1 s); talk (speaking, as today).

## Safety

Mission Control's rules hold (the Mission Control spec's Safety section):
- **Text stays text:**
  - names, tickers, the badge and the Brain's labels are set with `textContent`, as today (scene.js:179-180);
  - the worker has no text at all: its art is built by `createElementNS` from a fixed table in the code, never from
    strings, and never with `innerHTML`;
  - agent data never reaches the art. The id only picks one of 3 × 3 fixed variants, through two numbers written as
    `data-hair` and `data-skin`. The colour only comes through `--c`, from the `COLORS` whitelist (scene.js:7-8,
    177-178).
- **Pictures:**
  - monitors show only the app's own JPEGs, through the existing check (scene.js:15, 212-218);
  - the art is code: no image files in the extension, and no `<image>`, `<use>`, `<foreignObject>` or `<text>` in the
    SVGs. The prototypes copied into `docs/` are references that nothing loads.
- **Nothing leaves the machine.** Everything is drawn locally: no network, no web fonts, no CDN, no telemetry.
- **No download:** no library, model, font or art is fetched. Pre-rendered art would need the user's explicit OK first,
  and it is out of scope.
- **The reference image:** it is a licensed, watermarked Pngtree stock image, and we hold no licence. It is never
  embedded, shipped, cropped, recoloured, traced, cleaned of its watermark, or fed to any image generator. The character
  is drawn from scratch from a written description of the style.
- **No new permissions,** and MV3's default policy holds: only packaged scripts run. The new files ship with the
  extension folder (`prepare_extension` copies it whole, appbrowser.py:46-55).
- **No new way to act:** the spark and the burst are decoration. Clicks still only open the drawer, and no message is
  added.

**The browsing rules are untouched.** This spec changes only what Mission Control draws, in our own extension page:
- **no spoofing:** it adds no browsing, typing or clicking. The worker's "typing" and the Brain's motion are for the
  user's eyes only. Nothing here simulates human timing, mouse paths or input in any page, and nothing changes the
  browser's fingerprint: no `navigator.webdriver` patches, no user-agent, screen, timezone or GPU changes, no stealth
  plugins, and no proxies or profile rotation. The WebGL canvas draws only our own picture;
- **bot checks are handed to the user, never bypassed or solved:** the safe-browsing spec reports a bot check as the
  agent's `needs_you` state (with `check` set). The station then shows the raised hand and the badge, and the Brain
  aims its alert at it, like any other. A click opens the drawer as today. Mission Control never acts on the page
  itself, and nothing here touches a check;
- **the agent never types passwords:** nothing here shows or fills a password field;
- **the user's own words are instructions, and page or message text never is:** the visuals read only the app's state
  fields (`id`, `state`, `color`, whether a `permission` or a `check` waits, `created`) to pick variants, poses and
  the arrival. A page's text, a message or an agent's name can't change a pose, a colour or the art. `onWord` only
  counts words: the words themselves never reach the Brain's picture;
- **the `PERF_ROOM` snippet** (decision 10) is the project's own code, run by hand on the user's own page. It draws
  stand-in stations and sends nothing.

## Testing

**Where:** a new file, `tests/test_mission_visuals.py`, on the same stack as test_mission.py. It imports `stack`,
`until`, `evaluate` and `HOSTILE` from test_home; `open_mission`, `open_with`, `station`, `key`, `needs_reply`,
`voice_on`, `CARDS`, `overlapping` and `WORKING` from test_mission; and `ask_for_clickup` and `answered` from
test_ai_home_phase2.

**In front:** every test that reads a uniform, counts draws or measures time opens the page with `open_with` and brings
it to the front first (`Page.bringToFront` on `js.session`), as test_mission.py:402 does, because a hidden tab runs no
animations and no `requestAnimationFrame`.

**Before and after:** every test below fails on today's code (there is no brainshape.js, no `data-points`, no cloud
draw, no worker, no `u_burst`, `u_focus` or `u_word`), except the three marked **guard**, which pass today and must keep
passing.

**Hooks injected before the page's scripts** (through `open_with`'s `source`):
- **GL,** on `WebGLRenderingContext.prototype`:
  - wrap `getUniformLocation` to tag each location with its name;
  - wrap `uniform1f`, `uniform2f`, `uniform2fv` and `uniform4fv` to record the last value per name (`window.gl.last`)
    and, for floats, the largest (`window.gl.max`);
  - wrap `drawArrays` to count `POINTS` draws of 1000 points or more (`window.gl.cloud`);
- **contexts:** wrap `HTMLCanvasElement.prototype.getContext` to keep the distinct WebGL contexts that aren't null in a
  `Set` (`window.gl.contexts` is its size). A second `getContext('webgl')` on the same canvas returns the same context,
  so it isn't counted twice;
- **states:** a `MutationObserver` (subtree, the `data-state` attribute) records each new `data-state` of the `.stage`
  (`window.states`);
- **arrivals:** a `MutationObserver` (subtree, child list and class changes) records every station id that ever carries
  `.spawning` (`window.spawned`), and every `.spark` added (`window.sparks`) and removed (`window.sparksGone`).

**`brainshape.js`,** imported in mission.html with `await import(chrome.runtime.getURL('brainshape.js'))`:
1. `brainPoints(8000, 7)` holds 48000 numbers; a second call gives the same numbers (a checksum), and seed 8 gives
   different ones.
2. **The mix:** exactly 6400 cortex, 880 cerebellum, 400 stem and 320 core points.
3. **Bounds:** every point within |x| ≤ 0.7, −0.85 ≤ y ≤ 0.6 and |z| ≤ 0.75; fold and phase within 0 to 1.
4. **The gap:** no cortex point with |x| < 0.02; left and right cortex counts within 10% of each other.
5. **The parts:** stem points have y ≤ −0.17 and |x| < 0.15; cerebellum points have z < −0.2 and y < −0.1.
6. **The prefix:** the first 2000 points hold each kind within 3 percentage points of its share, and left and right
   within 15%.
7. **`synapses(points)`:** at most 900 pairs; every index is a cortex point below 8000; every link is 0.06 to 0.22 long;
   the same seed gives the same links.

The prototype's generator, run with these numbers, passes 1 to 7: 3120 left and 3280 right; the closest cortex point
is 0.039 from the middle; 900 links, all in range.

**The Brain:**

8. **Points:** `data-points` becomes `8000` within 3 s of opening; then the orb is hidden and the canvas shown.
9. **The fallback is a silhouette:** with WebGL blocked (as in test_mission.py:220-241), the orb shows, and the computed
   `mask-image` of its `::before` isn't `none`.
10. **The 30 fps cap:** between 20 and 62 cloud draws in 2 s.
11. **Reduced motion** (`Emulation.setEmulatedMedia` with `prefers-reduced-motion: reduce`, set once the page is open):
    - after 1.5 s, the cloud draw count doesn't change for 1 s;
    - a busy `brain_activity` makes it grow, with `data-state` `thinking`, and it stops growing within 2 s;
    - the last `u_mix` is exactly [0, 1, 0, 0].
12. **Adaptive detail:**
    - with `requestAnimationFrame` delayed by 80 ms (injected), `data-points` falls to `2500` within 10 s and never
      below;
    - with normal frames, it stays `8000` for 4 s.
13. **State weights (guard):** `u_mix` settles within 0.05 of [0, 1, 0, 0] on a busy `brain_activity`; of [0, 0, 1, 0]
    after a needs-reply item and a `brain_activity` that isn't busy; and of [1, 0, 0, 0] once the item is done
    (`brain.done`), as test_mission.py:198-216 drives it.
14. **The alert aims** (one agent waiting for a permission, with `ask_for_clickup`):
    - `u_focus` comes within 0.1 of [0, 1];
    - after 12 presses of ArrowLeft (180°), within 0.1 of [0, −1];
    - once the permission is answered from the drawer (as test_mission.py:140-146) and nothing needs the user, it
      comes within 0.05 of [0, 0].
15. **Words,** each on its own page, with Voice on (`voice_on`) and a needs-reply item to speak. The stub voices follow
    test_mission.py's `LOCAL_VOICE`:
    - **words:** `speak()` calls `onboundary({name: 'word'})` at 0, 100 and 200 ms, and `onend` at 350 ms.
      `window.states` holds `speaking`, and the largest `u_word` is above 0.5. The self-started rings wait 0.4 s, so
      only the words can have raised it;
    - **no words, short:** no boundary events, and `onend` at 300 ms: the largest `u_word` stays 0;
    - **no words, long:** no boundary events, and `onend` at 1500 ms: the largest `u_word` is above 0.5 (the
      self-started rings).
16. **One context (guard):** with 20 agents, `window.gl.contexts` is 1.

**The workers, in a pose harness:** in mission.html, import `chibi.js`, and build one `div.station[data-state=…] >
div.card > .worker` per state in a test container. Each check reads computed styles:

17. **Parts:** each worker has the parts in `PARTS` order, one `<svg>` each, no text (`textContent` is empty), no
    `<image>`, `<foreignObject>`, `<text>` or `<use>`, and `aria-hidden="true"`.
18. **Poses** (computed opacity 1 or 0):
    - **working:** arm-l and arm-r shown, arm-up and arm-thumb hidden, `.eyes-open` shown;
    - **needs_you:** arm-up 1, arm-r 0, `.mouth-o` 1;
    - **your_turn:** arm-thumb 1, arm-r 0, `.eyes-happy` 1;
    - **failed:** `.eyes-shut` 1, `.mouth-sad` 1, sweat 1, and the head's transform isn't `none`;
    - **stopped:** `.eyes-shut` 1, and every part's filter isn't `none`.
19. **The wrapper rule,** in every state: `.worker`'s computed `transform` and `filter` are `none`, `opacity` is 1,
    `will-change` is `auto`, and `z-index` is `auto`.
20. **Animations only on HTML:** with working, needs-you and done workers shown, no `document.getAnimations()` target is
    an SVG element.
21. **Variants:**
    - `variantOf('a1')` is {hair: 1, skin: 1}, every time;
    - a1 to a20 cover all 9 combinations of hair and skin;
    - `data-hair` and `data-skin` match.

**The workers, in the room:**

22. Each station has one `.worker`, and its tie's computed `fill` is the agent's colour (a1 is blue: rgb(76, 141, 246)).
    A hostile name stays text, and there is no image outside the monitors (as test_mission.py:41-56 checks).
23. **Size:** `.card`'s `offsetWidth` is 200 and its `offsetHeight` 156.
24. **A real needs-you:** with `ask_for_clickup`, that station's arm-up has opacity 1.
25. **No layout with 20 working agents (guard):** with 20 `WORKING` agents created before opening (so no arrival plays),
    `LayoutCount` grows by fewer than 10 in 2 s, the method of test_mission.py:391-413.
26. **Reduced motion:** with 3 working agents created before opening and the pose harness's six workers on the page,
    no animation is running after 1 s (`document.getAnimations()` filtered on `playState === 'running'` is empty).

**The arrival:**

27. **Three agents created before opening:** after 1.5 s, `window.spawned` is empty, no spark was added, and the largest
    `u_burst` is 0.
    **An agent created after opening:** it is in `window.spawned`; a spark was added and later removed; `.spawning` is
    gone within 3 s; the largest `u_burst` is above 0.5.
28. **Under reduced motion,** an agent created after opening gets no `.spawning` and no spark, and `u_burst` still rises
    (the flash).

**The budget and the snippet:**

29. **`test_the_budget`,** skipped unless `AIB_PERF=1` is set (timing depends on the machine). 20 `WORKING` agents are
    created before opening, at 1280 × 760, with the Brain thinking (a busy `brain_activity`). Over 3 s, from
    `Performance.getMetrics` deltas and an injected `requestAnimationFrame` frame counter, it asserts decision 10's
    budget: fewer than 10 layouts, at most one style recalc per frame and 60 ms of them, at most 250 ms of task time,
    at most 92 cloud draws, and one context. For the Brain's GPU time, the hook then times 60 frames from the frame's
    first `drawArrays` to a one-pixel `readPixels` after its cloud draw (the prototype's method; only here, because the
    read stalls the GPU): at most 1.5 ms on average. It prints every number, for the plan's report.
30. **`PERF_ROOM`,** run in an open Mission Control, adds a second `.scene` with 20 stations, each with one worker in
    the working pose, and leaves the page's own room as it was.
31. **Listening** (written and run by the voice-input spec, which is built after this one): while `data-state` is
    `listening`, driven the way the voice-input tests drive it, `u_listen` settles within 0.05 of 1 and `u_mix` within
    0.05 of [0, 0, 0, 0]; afterwards `u_listen` returns to 0.

**Existing tests that bind this design,** all kept unchanged in tests/test_mission.py:
- names stay text and stations update in place (41-56);
- monitors show thumbnails (59-71), and a picture for an unknown agent is dropped (451-461);
- the camera's limits (74-91), and turning past half a turn (427-434);
- stations at least 160 px apart in the room (94-102);
- the blob follows the Brain (197-216), the orb without WebGL (219-241), and the orb after a lost context (561-570);
- the Brain stays round at any zoom (351-362);
- 20 agents don't cover each other at 1280 × 760 (365-374);
- no layout while agents work (391-413);
- stations open in their places (416-424).

If 20 agents no longer fit, decision 7 says what changes; these tests don't. No test reads `.robot`.

**Checked by eye** (screenshots, compared with the prototypes' brain2.png and gallery.png):
- the Brain in all four states, at the start view and turned;
- rooms with 1, 6, 14 and 20 agents;
- each pose at full size and at the 20-agent scale;
- the arrival scene, mid-flight;
- reduced motion, and the dotted fallback.

**The performance pass** (the plan's last step): test 29 on the M5, with its numbers written into the plan's report.
The Windows laptop follows decision 10, by hand.

## Out of scope

- **Pre-rendered or 3D-rendered art** with the reference's soft 3D look: it needs art to be generated or commissioned,
  which needs the user's OK. The stable part names leave the door open.
- **three.js** or any other library, font or image download.
- **A one-canvas-per-station mode:** only if the Windows measurement fails the budget, in its own spec.
- **Voice input itself** (the mic, the talk panel, the `listening` state's place in `renderBrain`): the voice-input
  spec. Only how the particle brain draws `listening` is here (decision 4), so the voice-input spec, built next, can
  add it.
- **Sound effects.**
- **Workers walking around the room,** agents moving between desks, and the camera flying to a station.
- **Avatars the user picks or designs.**
- **Changes to the room's rows, the camera, the heads-up display or the drawer.**
