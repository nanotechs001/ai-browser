// Mission Control's office (the new look, Decision 3), drawn with CSS 3D: a floor in the page's plain navy, tilted
// away from the user, the glowing globe in the middle (the Brain's seat: #brain), and one desk per agent in rings
// around it (desk.js). Desks and the globe are billboards: they stand upright and face the user (their own turn undoes
// the room's). Dotted lines on the floor join each desk to the globe's foot. There is no other decor (the user's hand
// checks: no wall, no grid, no lamp, no sign, no big plants, and nothing under the globe: no rings, no light disc).
// Past 12 desks the oldest finished agents leave the room (step.js roomAgents); with more than 6 desks the step cards
// fold to chips. Everything is built once and updated in place; the timers tick together once a second, and stop while
// the room is paused. Text is set with textContent.
"use strict";

import { ensureDefs } from "./chibi.js";
import { createDesk, DESK } from "./desk.js";
import { roomAgents, stateOf } from "./step.js";

export { COLORS } from "./desk.js";
export { STATES, toolLabel } from "./step.js";

const CENTER = { x: 1000, y: 640 }; // the globe, in room pixels (the room is 2000 × 1400)
const START = { tilt: 58, spin: 0, scale: 1 };
const TILT = [35, 70];
const SCALE = [0.6, 1.6];
const RING = 430; // the first ring's radius, in room pixels
const RING_STEP = 330; // between two rings
const WIDE = 1.25; // rings are ellipses, wider than deep: desks stand side by side on screen
const ARC = 240; // degrees of each ring in front of the globe: no desk stands right behind it
const PUSH = 100; // room pixels: in a ring after the first, every odd seat stands this much further out (see placeOf)
const FOOT = 48; // room pixels: a dotted line stops this far in front of the globe's foot (WIDE times that sideways)
// Ring 1's seats, in degrees (90 is the front): left, right, front-left, front-right, far left, far right. The far two
// stand back and out (215°, -35°), so that a full step card (a desk with it is TALL) never hides the desk behind it.
const FIRST_RING = [150, 30, 112, 68, 215, -35];
const TALL = 280; // a desk with its step card, in CSS pixels: the card, the gap and the desk
const TOP = 72; // CSS pixels kept clear along the box's top, for no step card to sit under the Flow · List · Calendar
// switch (mission.css: its foot is 62 px down), the only words over the room
const ORIGIN = 0.2; // the perspective's origin, as a share of the box's height (office.css .viewport: 50% 20%)
const BOTTOM = 12; // CSS pixels kept clear below the near desks
const LOW = 0.75; // where the room stands in the room it has to spare: 0 at the top, 1 at the foot (see frame)
const FLOOR = 0.15; // the room's smallest zoom to fit in (20 desks in a box 700 px wide fit at about 0.2)
const CHIPS_PAST = 6; // more desks than this: step cards fold to chips
const SPARKS = 6; // arrivals in flight at once: any more arrive without a spark
const SVG = "http://www.w3.org/2000/svg";
const CONTINENTS = [ // [longitude, latitude, half-width, half-height] in degrees: rough blobs, enough for a globe
  [-100, 45, 32, 20], [-62, -16, 16, 26], [-40, 72, 12, 8], [12, 50, 18, 10], [20, 4, 20, 28], [46, 25, 10, 8],
  [92, 46, 46, 20], [78, 20, 8, 10], [112, 4, 16, 8], [135, -25, 17, 10], [138, 36, 4, 7],
];

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function svg(tag, attributes = {}) {
  const node = document.createElementNS(SVG, tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, String(value));
  return node;
}

function shortly(value) {
  return String(Math.round(value * 100) / 100);
}

function place(node, point) {
  node.style.left = `${point.x}px`;
  node.style.top = `${point.y}px`;
}

// The seat of the index-th of `count` desks. Ring 1's six seats come in a fixed order (three desks sit as in the
// mockup); ring r ≥ 2 holds 6·r desks over the ARC in front of the globe, a ring that isn't full spreading its desks
// over the whole arc. Along a full ring's two sides, neighbours stand in line one behind the other, and the card of the
// nearer one would hide the name of the next: so the odd seats of a ring after the first stand PUSH further out.
export function placeOf(index, count) {
  let ring = 1;
  let first = 0;
  while (index >= first + 6 * ring) {
    first += 6 * ring;
    ring += 1;
  }
  let angle;
  let radius = RING + RING_STEP * (ring - 1);
  if (ring === 1) {
    angle = FIRST_RING[index];
  } else {
    const seats = 6 * ring;
    const inRing = Math.min(seats, count - first);
    const seat = Math.round((index - first + 0.5) * (seats / inRing) - 0.5);
    angle = 90 + ARC / 2 - (seat + 0.5) * (ARC / seats);
    if (seat % 2 === 1) radius += PUSH;
  }
  const radians = (angle * Math.PI) / 180;
  return { x: Math.round(CENTER.x + WIDE * radius * Math.cos(radians)),
           y: Math.round(CENTER.y + radius * Math.sin(radians)), ring };
}

function globeMap() { // the dotted continents, twice side by side: sliding by one width turns the globe
  const map = svg("svg", { viewBox: "0 0 800 200", class: "map-art", "aria-hidden": "true" });
  for (let lat = 84; lat >= -84; lat -= 6) {
    for (let lon = -177; lon < 180; lon += 6) {
      if (!CONTINENTS.some(([x, y, w, h]) => ((lon - x) / w) ** 2 + ((lat - y) / h) ** 2 <= 1)) continue;
      for (const offset of [0, 400]) {
        map.append(svg("circle", { cx: ((lon + 180) / 360) * 400 + offset, cy: ((90 - lat) / 180) * 200, r: 1.7 }));
      }
    }
  }
  return map;
}

function createGlobe() { // the Brain's seat: click it for its inbox (mission.js)
  const globe = el("button", "globe");
  globe.id = "brain";
  globe.type = "button";
  globe.setAttribute("aria-label", "The Brain: open its inbox");
  const sphere = el("div", "sphere");
  const map = el("div", "map");
  map.append(globeMap());
  sphere.append(map, el("div", "shine"));
  globe.append(sphere);
  return globe;
}

export function createScene(root, { onSelect = () => {} } = {}) {
  const viewport = el("div", "viewport");
  const room = el("div", "room");
  const links = svg("svg", { class: "links", "aria-hidden": "true" });
  const stage = el("div", "stage billboard");
  const globe = createGlobe();
  stage.append(globe);
  const empty = el("div", "empty-note billboard", "Start a mission below");
  room.append(links, stage, empty);
  viewport.append(room);
  root.replaceChildren(viewport);
  ensureDefs(document);
  place(stage, CENTER);
  place(empty, { x: CENTER.x, y: CENTER.y + 250 });
  const desks = new Map(); // agent id -> {desk, shadow, link}
  const rows = new Map(); // agent id -> its latest row
  const camera = { ...START };
  let filter = () => true;
  let selected = null;
  let shownKey = null;
  let current = []; // the ids with a desk in the room, oldest first
  let extent = { dx: 300, near: CENTER.y + 200, far: CENTER.y };
  let ticking = null;
  let pulsing = null;

  // Where the room stands at this zoom, and whether every desk and the globe are in view. `middle` is how far the
  // room's middle hangs below the perspective's origin (office.css .viewport): the room's span, from the top of the
  // highest card (or the globe) to the near desks' bottom, goes in the band between TOP and the box's bottom (less
  // BOTTOM), three quarters of the way down what the band has to spare (LOW). A room as wide as its box has room to
  // spare above it, now that only the switch is kept clear: lower down it is seen from higher up, and a nearer chip
  // covers less of the name behind it (centred, 16 and 20 desks covered more than half a name).
  function frame(scale, width, height) {
    const tilt = (START.tilt * Math.PI) / 180;
    const at = (y) => { // a room's y: how far down the screen it falls from the room's middle, and its magnification
      const depth = (y - 700) * scale;
      return { down: depth * Math.cos(tilt), factor: 1800 / (1800 - depth * Math.sin(tilt)) };
    };
    const far = at(extent.far);
    const near = at(extent.near);
    const globe = at(CENTER.y);
    const origin = ORIGIN * height; // a point's screen y: origin + (middle + down) * factor
    const highest = Math.max((TOP - origin) / far.factor - far.down + TALL * scale,
                             (TOP - origin) / globe.factor - globe.down + 340 * scale); // the least `middle` may be
    const lowest = (height - BOTTOM - origin) / near.factor - near.down; // and the most
    const sideways = width / 2 - (extent.dx + DESK.w / 2) * scale * near.factor >= 0;
    return { fits: highest <= lowest && sideways, middle: highest + (lowest - highest) * LOW };
  }

  function fit() { // the room's zoom, the largest with every desk in the box (below the top band), and where it stands
    const width = viewport.clientWidth || innerWidth;
    const height = viewport.clientHeight || innerHeight;
    let scale = Math.min(1.2, (width * 0.94) / (2 * extent.dx + DESK.w + 40)); // frame() checks the height
    let found = frame(scale, width, height);
    while (scale > FLOOR && !found.fits) {
      scale -= 0.02;
      found = frame(scale, width, height);
    }
    scale = Math.max(FLOOR, scale);
    return { scale, top: ORIGIN * height + frame(scale, width, height).middle };
  }

  function apply() {
    room.style.setProperty("--tilt", `${camera.tilt}deg`);
    room.style.setProperty("--spin", `${camera.spin}deg`);
    const { scale: fitted, top } = fit();
    const scale = camera.scale * fitted; // in 3D: the desks stand up through z, and keep their shape
    const where = `${Math.round(top * 10) / 10}px`;
    if (room.style.top !== where) room.style.top = where; // the room's middle, in the box (the sheet's 58% before this)
    room.style.transform = `rotateX(${camera.tilt}deg) rotateZ(${camera.spin}deg) scale3d(${scale}, ${scale}, ${scale})`;
    room.dataset.tilt = shortly(camera.tilt);
    room.dataset.spin = shortly(camera.spin);
    room.dataset.scale = shortly(camera.scale);
  }

  function shownIds() {
    return roomAgents([...rows.values()].filter(filter)).map((agent) => agent.id);
  }

  function modeOf(agent, count) {
    return count > CHIPS_PAST && agent.id !== selected && stateOf(agent) !== "needs_you" ? "chip" : "full";
  }

  function linkPath(point) { // from under the desk to the globe's foot, on the floor
    const angle = Math.atan2(point.y - CENTER.y, point.x - CENTER.x);
    return `M ${point.x} ${point.y} L ${Math.round(CENTER.x + WIDE * FOOT * Math.cos(angle))} `
      + `${Math.round(CENTER.y + FOOT * Math.sin(angle))}`;
  }

  function fillOne(id, count) {
    const entry = desks.get(id);
    const row = rows.get(id);
    entry.desk.fill(row, modeOf(row, count));
    entry.link.classList.toggle("live", stateOf(row) === "working");
  }

  function refresh() { // who is in the room, where each desk stands, and how each card shows
    const ids = shownIds();
    extent = { dx: 300, near: CENTER.y + 200, far: CENTER.y };
    for (const [id, entry] of desks) {
      const index = ids.indexOf(id);
      const away = index < 0;
      entry.desk.node.classList.toggle("away", away);
      entry.desk.node.disabled = away;
      entry.shadow.classList.toggle("away", away);
      entry.link.classList.toggle("away", away);
      if (away) continue;
      const point = placeOf(index, ids.length);
      place(entry.desk.node, point);
      place(entry.shadow, point);
      entry.desk.node.dataset.x = String(point.x);
      entry.desk.node.dataset.y = String(point.y);
      entry.link.setAttribute("d", linkPath(point));
      extent = { dx: Math.max(extent.dx, Math.abs(point.x - CENTER.x)), near: Math.max(extent.near, point.y),
                 far: Math.min(extent.far, point.y) };
    }
    current = ids;
    shownKey = ids.join(" ");
    for (const id of ids) fillOne(id, ids.length);
    room.dataset.empty = String(!ids.length);
    // the empty note: agents exist and the workspace picked hides them all, or no agent exists at all
    const words = rows.size ? "No missions in this workspace" : "Start a mission below";
    if (empty.textContent !== words) empty.textContent = words;
    apply();
  }

  function build(id) {
    const desk = createDesk(id, onSelect);
    const shadow = el("div", "shadow placing");
    const link = svg("path", { class: "link" });
    links.append(link);
    room.append(shadow, desk.node);
    const entry = { desk, shadow, link };
    desks.set(id, entry);
    requestAnimationFrame(() => requestAnimationFrame(() => {
      desk.node.classList.remove("arriving", "placing");
      shadow.classList.remove("placing");
    }));
    return entry;
  }

  function arrive(entry) { // a new agent's short scene: a spark flies from the globe, the worker pops up and waves
    const { node } = entry.desk;
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
    rows.set(agent.id, agent);
    const added = !desks.has(agent.id);
    if (added) build(agent.id);
    const ids = shownIds();
    if (added || ids.join(" ") !== shownKey) refresh();
    else if (ids.includes(agent.id)) fillOne(agent.id, ids.length);
    if (added && fresh && ids.includes(agent.id) && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
      arrive(desks.get(agent.id));
    }
  }

  function remove(id) {
    const entry = desks.get(id);
    if (!entry) return;
    desks.delete(id);
    rows.delete(id);
    if (selected === id) selected = null;
    entry.desk.node.classList.add("leaving");
    entry.desk.node.disabled = true;
    entry.shadow.remove();
    entry.link.remove();
    setTimeout(() => entry.desk.node.remove(), 300);
    refresh();
  }

  function thumb(id, jpeg) { // a picture for an agent without a desk (closed meanwhile) is dropped
    desks.get(id)?.desk.thumb(jpeg);
  }

  function select(id) {
    selected = id;
    for (const [one, entry] of desks) entry.desk.node.classList.toggle("selected", one === id);
    refresh(); // the picked desk's card stays whole in a crowded room
  }

  function setFilter(next) {
    filter = typeof next === "function" ? next : () => true;
    refresh();
  }

  function tick() {
    const now = Date.now() / 1000;
    for (const id of current) {
      if (rows.has(id)) desks.get(id)?.desk.tick(rows.get(id), now);
    }
  }

  function pause(on) { // its tab or the window is hidden: the timers wait (mission.js pauses the animations)
    clearInterval(ticking);
    ticking = on ? null : setInterval(tick, 1000);
  }

  function pulse() { // a word the Brain says
    globe.classList.add("pulse");
    clearTimeout(pulsing);
    pulsing = setTimeout(() => globe.classList.remove("pulse"), 250);
  }

  function turn(degrees, tilt = 0) {
    camera.spin += degrees; // not wrapped at ±180°: the room never swings back the long way
    camera.tilt = Math.min(TILT[1], Math.max(TILT[0], camera.tilt + tilt));
    apply();
  }

  function zoom(factor) {
    camera.scale = Math.min(SCALE[1], Math.max(SCALE[0], camera.scale * factor));
    apply();
  }

  function reset() {
    Object.assign(camera, START);
    apply();
  }

  new ResizeObserver(() => apply()).observe(viewport); // the box it is in changed: fit again (after layout)
  refresh();
  pause(false);
  return { upsert, remove, thumb, select, setFilter, pause, pulse, refit: apply, shown: () => [...current], turn, zoom,
           reset, camera, stage, globe, viewport };
}
