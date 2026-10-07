// One desk in the office (the new look, Decision 3): a round desk with a neon rim, the agent's chibi at a laptop with a
// glowing logo, a mug and a plant, its name on the desk's front, its sub-agents as smaller chibis beside it, and above
// it the step card: the current step, its timer, the line under it, the badge of its latest action, and (once there
// is one) the latest picture of its tab. Built once, then updated in place, so a click is never lost to a rebuild.
// Every word is set as text, with its whole as a tooltip; the picture is only ever the app's own JPEG.
"use strict";

import { agentLabel } from "./chat.js";
import { createWorker } from "./chibi.js";
import { BADGE_ICONS, icon } from "./icons.js";
import { STATES, stepOf, timerOf } from "./step.js";

export const COLORS = { grey: "#8a8f98", blue: "#4c8df6", red: "#ef6a5f", yellow: "#f6c344", green: "#3fb26b",
                        pink: "#ea5aa8", purple: "#b57bf7", cyan: "#2bb3bd", orange: "#fb9f4e" };
export const DESK = { w: 220, h: 150 }; // a desk's art, in CSS pixels (office.css uses the same numbers)
export const CARD = { w: 210, h: 110 }; // a step card, at most
const SUBS_SHOWN = 3; // sub-agents at one desk; more working ones show as "+2"
const SUB_POSE = { working: "working", done: "your_turn", failed: "failed", stopped: "stopped" };
const JPEG = /^[A-Za-z0-9+/]+={0,2}$/;
const SVG = "http://www.w3.org/2000/svg";

const TABLE = [ // the round desk, seen from the front and a little above (office.css colours its classes)
  ["path", { class: "side", d: "M4 40 L4 74 A106 30 0 0 0 216 74 L216 40 Z" }],
  ["path", { class: "rim", d: "M4 74 A106 30 0 0 0 216 74" }],
  ["ellipse", { class: "top", cx: "110", cy: "40", rx: "106", ry: "30" }],
  ["ellipse", { class: "shine", cx: "110", cy: "36", rx: "86", ry: "20" }],
];
const LID = [["rect", { class: "shell", x: "2", y: "2", width: "60", height: "36", rx: "4" }],
             ["path", { class: "logo", d: "M32 12 L39 26 H25 Z" }]];
const CHAIR = [["rect", { x: "4", y: "2", width: "50", height: "58", rx: "14", fill: "#1a2142" }],
               ["rect", { x: "9", y: "7", width: "40", height: "48", rx: "11", fill: "#232b55" }]];
const MUG = [["path", { d: "M5 7h11v9a4 4 0 0 1-4 4H9a4 4 0 0 1-4-4z", fill: "#e9edf7" }],
             ["path", { d: "M16 9h2a3 3 0 0 1 0 6h-2", fill: "none", stroke: "#e9edf7", "stroke-width": "2" }],
             ["ellipse", { cx: "10.5", cy: "7.5", rx: "5.5", ry: "1.6", fill: "#7a4a2a" }]];
const PLANT = [["path", { d: "M12 30h16l-2 16H14z", fill: "#2a2f4a" }],
               ["path", { d: "M20 30 C18 20 10 16 4 16 C8 22 12 28 20 30z", fill: "#3fae6a" }],
               ["path", { d: "M20 30 C22 18 30 12 36 12 C32 20 28 27 20 30z", fill: "#56c47e" }],
               ["path", { d: "M20 30 C19 18 20 8 22 2 C25 10 24 22 20 30z", fill: "#4bb874" }]];

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

function setTitled(node, text) { // a line that may be clipped: its whole words as a tooltip (Review Focus 1)
  setText(node, text);
  if (node.title !== text) node.title = text;
}

export function art(className, viewBox, shapes) { // a small fixed drawing from [tag, attributes] pairs, never parsed
  const holder = el("div", className);
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", viewBox);
  svg.setAttribute("aria-hidden", "true");
  for (const [tag, attributes] of shapes) {
    const node = document.createElementNS(SVG, tag);
    for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
    svg.append(node);
  }
  holder.append(svg);
  return holder;
}

export function plantArt(className = "plant") {
  return art(className, "0 0 40 48", PLANT);
}

export function createDesk(id, onSelect = () => {}) {
  const node = el("button", "station billboard arriving placing"); // its first place: no sliding into it
  node.type = "button";
  node.dataset.id = id;
  const parts = {
    step: el("div", "step"), ring: el("span", "step-ring"), title: el("strong", "step-title"),
    timer: el("span", "timer"), ticker: el("div", "ticker"), badge: el("span", "step-badge"),
    badgeText: el("span", "badge-text"), badgeIcon: null, monitor: el("div", "monitor"), shot: el("img", "shot"),
    art: el("div", "desk-art"), pose: el("div", "pose main"), subs: el("div", "subs"), more: el("span", "more"),
    nameplate: el("span", "nameplate"), needs: el("span", "badge", "needs you"),
  };
  parts.shot.alt = "";
  parts.shot.hidden = true;
  parts.monitor.hidden = true;
  parts.monitor.append(parts.shot);
  const head = el("div", "step-head");
  head.append(parts.title, parts.timer);
  parts.badge.append(parts.badgeText);
  parts.step.append(parts.ring, head, parts.monitor, parts.ticker, parts.badge);
  parts.pose.append(createWorker(id));
  parts.more.hidden = true;
  const laptop = el("div", "laptop");
  laptop.append(art("lid", "0 0 64 40", LID), el("div", "keyboard"));
  parts.art.append(art("chair", "0 0 58 66", CHAIR), parts.pose, art("table", "0 0 220 110", TABLE), laptop,
                   art("mug", "0 0 24 24", MUG), plantArt(), parts.subs, parts.more, parts.nameplate);
  node.append(parts.step, parts.art, parts.needs);
  node.addEventListener("click", () => onSelect(id));
  const subs = new Map(); // sub-agent id -> its pose
  let jpeg = null;

  function fillSubs(rows) { // at most SUBS_SHOWN smaller chibis: those at work first, then the newest
    const list = Array.isArray(rows) ? rows : [];
    const working = list.filter((row) => row.state === "working");
    const shown = [...working, ...list.filter((row) => row.state !== "working").reverse()].slice(0, SUBS_SHOWN);
    const keep = new Set(shown.map((row) => row.id));
    for (const [sub, pose] of subs) {
      if (!keep.has(sub)) {
        pose.remove();
        subs.delete(sub);
      }
    }
    for (const row of shown) {
      let pose = subs.get(row.id);
      if (!pose) {
        pose = el("div", "pose sub");
        pose.append(createWorker(`${id}:${row.id}`, { small: true }));
        subs.set(row.id, pose);
        parts.subs.append(pose);
      }
      const state = SUB_POSE[row.state] || "working";
      if (pose.dataset.state !== state) pose.dataset.state = state;
      const words = `Sub-agent: ${row.task}${row.action ? ` · ${row.action}` : ""}`;
      if (pose.title !== words) pose.title = words;
    }
    const more = working.length - shown.filter((row) => row.state === "working").length;
    setText(parts.more, more > 0 ? `+${more}` : "");
    parts.more.hidden = more <= 0;
  }

  function tick(agent, now = Date.now() / 1000) {
    setText(parts.timer, timerOf(agent, now));
  }

  function fill(agent, mode = "full") { // mode: "full", or "chip" when the room is crowded
    const step = stepOf(agent);
    if (node.dataset.state !== step.state) node.dataset.state = step.state;
    if (parts.pose.dataset.state !== step.state) parts.pose.dataset.state = step.state;
    if (parts.step.dataset.mode !== mode) parts.step.dataset.mode = mode;
    const color = COLORS[agent.color] || COLORS.grey;
    if (node.style.getPropertyValue("--c") !== color) node.style.setProperty("--c", color);
    const name = agentLabel(agent);
    setTitled(parts.nameplate, name);
    setTitled(parts.title, step.title);
    setTitled(parts.ticker, step.line);
    setText(parts.badgeText, step.badge);
    parts.badge.hidden = !step.badge;
    if (parts.badge.dataset.icon !== step.badge) { // its icon is swapped only when the badge changes
      parts.badgeIcon?.remove();
      parts.badgeIcon = step.badge ? icon(BADGE_ICONS[step.badge] || "tool") : null;
      if (parts.badgeIcon) parts.badge.prepend(parts.badgeIcon);
      parts.badge.dataset.icon = step.badge;
    }
    fillSubs(agent.subagents);
    tick(agent);
    const label = `${name}: ${STATES[step.state] || step.state}`;
    if (node.getAttribute("aria-label") !== label) node.setAttribute("aria-label", label);
  }

  function thumb(next) { // a picture of its tab: the app's own JPEG, shown once there is one
    if (typeof next !== "string" || !JPEG.test(next) || next === jpeg) return;
    jpeg = next;
    parts.shot.src = `data:image/jpeg;base64,${next}`;
    parts.shot.hidden = false;
    parts.monitor.hidden = false;
  }

  return { node, parts, fill, tick, thumb };
}
