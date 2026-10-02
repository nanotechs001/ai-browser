// Mission Control's room, drawn with CSS 3D: a floor tilted away from the user, the Brain's stage in the middle, and
// one station per agent around it. Stations and the stage are billboards: they stand upright and face the user (their
// own turn undoes the room's). Stations are built once and then updated in place, so a click is never lost to a
// rebuild; text is set with textContent, and a monitor only ever shows the app's own JPEG pictures.
"use strict";

export const COLORS = { grey: "#8a8f98", blue: "#4c8df6", red: "#ef6a5f", yellow: "#f6c344", green: "#3fb26b",
                        pink: "#ea5aa8", purple: "#b57bf7", cyan: "#2bb3bd", orange: "#fb9f4e" };
export const STATES = { working: "working", waiting: "waiting in line", your_turn: "done", stopped: "stopped",
                        failed: "failed", needs_you: "needs you" };
const CENTER = { x: 1000, y: 540 }; // the Brain, in room pixels (the room is 2000 × 1400)
const START = { tilt: 58, spin: 0, scale: 1 };
const TILT = [35, 70];
const SCALE = [0.6, 1.6];
const JPEG = /^[A-Za-z0-9+/]+={0,2}$/;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

function shortly(value) {
  return String(Math.round(value * 100) / 100);
}

const SEAT = 240; // room pixels between two stations side by side (a card is 176 wide: they never overlap)
const ROW = 340; // between two rows, front to back: more than a card's height on screen
const BACK = 440; // the rows behind are farther apart: far away, a card looks shorter but the Brain needs the room

function at(depth, dx) { // every row is an arc around the Brain, the first one just in front of it
  const arc = Math.sqrt(Math.max(0, 1 - (dx / 1000) ** 2));
  return { x: Math.round(CENTER.x + dx), y: Math.round(CENTER.y + 380 * arc + depth) };
}

// The rows after the first take turns: behind it (beside the Brain, leaving the Brain's place free), then in front of
// it, then further behind, and so on. A row's seats fill from the middle out, half a seat over from the row before.
function rowSeats(row) {
  const step = Math.ceil(row / 2);
  const behind = row % 2 === 1;
  const half = step % 2 === 0;
  const widest = 720 + (half ? 120 : 0) + (step > 2 ? SEAT : 0);
  const seats = [];
  for (let dx = half ? SEAT / 2 : 0; dx <= widest; dx += SEAT) {
    if (behind && dx < SEAT) continue;
    if (dx === 0) seats.push(0);
    else seats.push(-dx, dx);
  }
  return { seats, depth: behind ? -step * BACK : step * ROW };
}

// Where the index-th of `count` agents works: the first six side by side in an arc in front of the Brain (centred),
// the rest in the rows behind and in front of it.
export function placeOf(index, count) {
  const first = Math.min(count, 6);
  if (index < first) return at(0, (index - (first - 1) / 2) * SEAT);
  let start = 6;
  for (let row = 1; ; row += 1) {
    const { seats, depth } = rowSeats(row);
    if (index < start + seats.length) return at(depth, seats[index - start]);
    start += seats.length;
  }
}

function place(node, point) {
  node.style.left = `${point.x}px`;
  node.style.top = `${point.y}px`;
}

export function toolLabel(permission) { // "ClickUp: create task", for a station's ticker and the Brain's words
  const server = String(permission?.server || "a tool").replace(/^claude_ai_/, "").replaceAll("_", " ");
  const tool = String(permission?.tool || "").split("__").slice(2).join("__").replaceAll("_", " ");
  return tool ? `${server}: ${tool}` : server;
}

function tickerOf(agent, state) {
  if (state === "needs_you" && agent.check) return `bot check · ${agent.check.site}`;
  if (state === "needs_you" && agent.permission) return `wants ${toolLabel(agent.permission)}`;
  if (state === "failed") return agent.status || "failed";
  return agent.last_action || agent.status || STATES[state] || state;
}

export function createScene(root, { onSelect = () => {} } = {}) {
  const viewport = el("div", "viewport");
  const room = el("div", "room");
  const floor = el("div", "floor");
  const ring = el("div", "ring");
  const stage = el("div", "stage billboard");
  room.append(floor, ring, stage);
  viewport.append(room);
  root.replaceChildren(viewport);
  place(ring, CENTER);
  place(stage, CENTER);
  const stations = new Map(); // agent id -> {node, shadow, parts, jpeg}
  const camera = { ...START };
  const created = new Map(); // agent id -> when it was created: the oldest gets the first place
  let order = []; // agent ids, oldest first
  let extent = { dx: 600, near: 920, far: CENTER.y }; // how far the stations reach: the room is fitted to them

  function fits(scale, height) { // with this zoom, the nearest station stands above the task bar, the farthest
    const tilt = (START.tilt * Math.PI) / 180; // card and the Brain below the top bar (the room's perspective)
    const middle = 0.38 * height; // the room's middle, below the perspective's origin (.room top 58%, origin 20%)
    const screen = (y) => {
      const depth = (y - 700) * scale;
      return 0.2 * height + ((middle + depth * Math.cos(tilt)) * 1800) / (1800 - depth * Math.sin(tilt));
    };
    return screen(extent.near) <= height - 100 && screen(extent.far) >= 64 + 180 * scale
      && screen(CENTER.y) >= 64 + 400 * scale;
  }

  function fit() { // the room fills the window it is in, with every station in view
    const width = viewport.clientWidth || innerWidth;
    const height = viewport.clientHeight || innerHeight;
    let scale = Math.max(0.35, Math.min(1.15, (width * 0.94) / (2 * extent.dx + 240), height / 880));
    while (scale > 0.35 && !fits(scale, height)) scale -= 0.02;
    return scale;
  }

  function apply() {
    room.style.setProperty("--tilt", `${camera.tilt}deg`);
    room.style.setProperty("--spin", `${camera.spin}deg`);
    const scale = camera.scale * fit(); // in 3D: the stations stand up through z, and keep their shape
    room.style.transform = `rotateX(${camera.tilt}deg) rotateZ(${camera.spin}deg) scale3d(${scale}, ${scale}, ${scale})`;
    room.dataset.tilt = shortly(camera.tilt);
    room.dataset.spin = shortly(camera.spin);
    room.dataset.scale = shortly(camera.scale);
  }

  function layout() {
    extent = { dx: 600, near: 920, far: CENTER.y };
    order.forEach((id, index) => {
      const station = stations.get(id);
      const point = placeOf(index, order.length);
      place(station.node, point);
      place(station.shadow, point);
      station.node.dataset.x = String(point.x);
      station.node.dataset.y = String(point.y);
      extent = { dx: Math.max(extent.dx, Math.abs(point.x - CENTER.x)), near: Math.max(extent.near, point.y),
                 far: Math.min(extent.far, point.y) };
    });
    apply();
  }

  function build(id) {
    const node = el("button", "station billboard arriving placing"); // its first place: no sliding into it
    node.type = "button";
    node.dataset.id = id;
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
    node.addEventListener("click", () => onSelect(id));
    const shadow = el("div", "shadow placing");
    room.append(shadow, node);
    requestAnimationFrame(() => requestAnimationFrame(() => {
      node.classList.remove("arriving", "placing");
      shadow.classList.remove("placing");
    }));
    return { node, shadow, parts, jpeg: null };
  }

  function fill(station, agent) {
    const { node, parts } = station;
    const state = agent.permission || agent.check ? "needs_you" : String(agent.state || "waiting");
    if (node.dataset.state !== state) node.dataset.state = state;
    const color = COLORS[agent.color] || COLORS.grey;
    if (node.style.getPropertyValue("--c") !== color) node.style.setProperty("--c", color);
    setText(parts.nameplate, String(agent.name || ""));
    setText(parts.ticker, tickerOf(agent, state));
    const label = `${agent.name}: ${STATES[state] || state}`;
    if (node.getAttribute("aria-label") !== label) node.setAttribute("aria-label", label);
  }

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

  function remove(id) {
    const station = stations.get(id);
    if (!station) return;
    stations.delete(id);
    created.delete(id);
    order = order.filter((other) => other !== id);
    station.node.classList.add("leaving");
    station.node.disabled = true;
    station.shadow.remove();
    setTimeout(() => station.node.remove(), 300);
    layout();
  }

  function thumb(id, jpeg) { // a picture for an agent without a station (closed meanwhile) is dropped
    const station = stations.get(id);
    if (!station || typeof jpeg !== "string" || !JPEG.test(jpeg) || station.jpeg === jpeg) return;
    station.jpeg = jpeg;
    station.parts.shot.src = `data:image/jpeg;base64,${jpeg}`;
    station.parts.shot.hidden = false;
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

  addEventListener("resize", apply);
  apply();
  return { upsert, remove, thumb, turn, zoom, reset, camera, stage, viewport };
}
