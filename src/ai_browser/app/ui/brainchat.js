// The Brain's chat (the chat-panel spec, 1-3): a floating panel in Mission Control holding the talk (talk.js: its
// log, status, notice, card, box, mic and note) and the Brain's hand-off cards (brainui.js). It is never modal: the
// office, the desks and the drawers stay clickable around it. Ask AI opens (and closes) it, × or Esc closes it, and it
// opens itself when the Brain needs the user: a hand-off or a suggestion, or a line or a card in the talk. Dragged by
// its bar and kept on screen; its place is remembered per window size (localStorage, read and written in try/catch).
// Under 900 px it fills the width at the bottom and isn't dragged. Every word is set as text.
"use strict";

import { PICTURES_NOTE, takeFiles } from "./paste.js";

const NARROW = matchMedia("(max-width: 899px)"); // full width at the bottom: it isn't dragged
const EDGE = 8; // px it keeps from the window's edges
const PLACES = "brainchat-places"; // localStorage: {"<width>x<height>": [left, top]}
const OPEN = ["counting", "waiting"]; // a hand-off that needs the user

function places() {
  try {
    const saved = JSON.parse(localStorage.getItem(PLACES) || "{}");
    return saved && typeof saved === "object" ? saved : {};
  } catch {
    return {}; // storage blocked, or a damaged entry: the default place
  }
}

// onToggle(open): it opened or closed (Mission Control tells the app whether its cards can be seen)
export function mountBrainChat({ onToggle = () => {} } = {}) {
  const $ = (id) => document.getElementById(id);
  const root = $("brainchat");
  const bar = $("brainchat-bar");
  const opener = $("ask-ai");
  let drag = null;

  const size = () => `${innerWidth}x${innerHeight}`;

  function moveTo(left, top) { // on screen, EDGE px in
    const box = root.getBoundingClientRect();
    root.classList.add("placed");
    root.style.left = `${Math.round(Math.min(Math.max(EDGE, left), innerWidth - box.width - EDGE))}px`;
    root.style.top = `${Math.round(Math.min(Math.max(EDGE, top), innerHeight - box.height - EDGE))}px`;
  }

  function place() { // its place for this window size, else the stylesheet's: bottom-right, above the composer
    root.classList.remove("placed");
    root.style.removeProperty("left");
    root.style.removeProperty("top");
    const saved = places()[size()];
    if (root.hidden || NARROW.matches || !Array.isArray(saved)) return;
    moveTo(Number(saved[0]) || 0, Number(saved[1]) || 0);
  }

  function remember() {
    const box = root.getBoundingClientRect();
    try {
      localStorage.setItem(PLACES, JSON.stringify({ ...places(), [size()]: [Math.round(box.left), Math.round(box.top)] }));
    } catch { /* storage blocked: it opens at the default place next time */ }
  }

  function open({ focus = false } = {}) { // Ask AI's click focuses its box; opening by itself never takes the focus
    const was = !root.hidden;
    root.hidden = false;
    opener.setAttribute("aria-expanded", "true");
    if (!was) {
      place();
      onToggle(true);
    }
    if (focus) $("talk-text").focus();
  }

  function close() {
    if (root.hidden) return;
    const inside = root.contains(document.activeElement);
    root.hidden = true;
    opener.setAttribute("aria-expanded", "false");
    onToggle(false);
    if (inside) opener.focus(); // the keys go back where the user opened it
  }

  opener.addEventListener("click", () => (root.hidden ? open({ focus: true }) : close()));
  $("brainchat-close").addEventListener("click", close);
  root.addEventListener("keydown", (event) => { // Esc inside it closes it (a talk turn's Esc is talk.js's, first)
    if (event.key !== "Escape" || event.defaultPrevented) return;
    event.preventDefault();
    event.stopPropagation();
    close();
  });
  takeFiles($("talk-text"), () => { // the Brain's box: text only, and it says where pictures go
    $("talk-notice").textContent = PICTURES_NOTE;
  });
  bar.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || NARROW.matches || event.target.closest("button, summary, details, a, input")) return;
    const box = root.getBoundingClientRect();
    drag = { id: event.pointerId, dx: event.clientX - box.left, dy: event.clientY - box.top };
    bar.setPointerCapture(event.pointerId);
    event.preventDefault(); // no text selection while it moves
  });
  bar.addEventListener("pointermove", (event) => {
    if (drag?.id === event.pointerId) moveTo(event.clientX - drag.dx, event.clientY - drag.dy);
  });
  for (const type of ["pointerup", "pointercancel"]) {
    bar.addEventListener(type, (event) => {
      if (drag?.id !== event.pointerId) return;
      drag = null;
      remember();
    });
  }
  addEventListener("resize", place); // another window size: its place for that size, or the default, on screen
  NARROW.addEventListener("change", place);

  return {
    open,
    close,
    get isOpen() { return !root.hidden; },
    onMessage(message) { // the Brain needs the user: a hand-off or a suggestion opens it, never taking the focus
      if (message.type === "brain_handoff" && OPEN.includes(message.handoff?.state)) open();
      else if (message.type === "brain_snapshot" && (message.handoffs || []).some((one) => OPEN.includes(one?.state))) {
        open();
      }
    },
  };
}
