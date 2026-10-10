// The Brain's chat (the chat-panel spec, 1-3): a floating panel in Mission Control holding the talk (talk.js: its
// log, status, notice, card, box, mic and note) and the Brain's hand-off cards (brainui.js). It is never modal: the
// office, the desks and the drawers stay clickable around it. Ask AI opens (and closes) it, × or Esc closes it, and it
// opens itself when the Brain needs the user: a hand-off or a suggestion, or a line or a card in the talk. Dragged by
// its bar and kept on screen; its place is remembered per window size (localStorage, read and written in try/catch).
// Under 900 px it fills the width at the bottom and isn't dragged. Every word is set as text.
"use strict";

import { el } from "./chat.js";
import { confirmAction } from "./confirm.js";
import { PICTURES_NOTE, takeFiles } from "./paste.js";

const NARROW = matchMedia("(max-width: 899px)"); // full width at the bottom: it isn't dragged
const EDGE = 8; // px it keeps from the window's edges
const PLACES = "brainchat-places"; // localStorage: {"<width>x<height>": [left, top]}
const OPEN = ["counting", "waiting"]; // a hand-off that needs the user
const shownCards = new Set(); // the ids of the hand-offs and suggestions that opened it once

function places() {
  try {
    const saved = JSON.parse(localStorage.getItem(PLACES) || "{}");
    return saved && typeof saved === "object" ? saved : {};
  } catch {
    return {}; // storage blocked, or a damaged entry: the default place
  }
}

function when(iso) { // "Oct 10, 14:05", in the user's own way of writing it
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? ""
    : date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

// link: the line to the app; talk(): talk.js's talk, which shows the kept chat; onToggle(open): it opened or closed
// (Mission Control tells the app whether its cards can be seen). New chat and History ▾ (the spec, 5): the app makes
// a chat's id and keeps its file; a reopened chat shows its whole log, its cards as text.
export function mountBrainChat({ link, talk = () => null, onToggle = () => {} }) {
  const $ = (id) => document.getElementById(id);
  const root = $("brainchat");
  const bar = $("brainchat-bar");
  const opener = $("ask-ai");
  let drag = null;
  let current = null; // the kept chat shown: its id (the app made it)
  let waiting = null; // the New chat or the reopened chat whose brain_chat comes next
  let automatic = null; // the New chat a connection asked for: it takes over only a talk with nothing in it
  let reopening = null; // History's reopen whose brain_chat (or error) comes next: the keys go on from there
  let asked = 0;

  function request(type, fields = {}) { // one request each, named chat-<n>
    asked += 1;
    const id = `chat-${asked}`;
    if (type !== "brain_chat_delete") waiting = id;
    link.send({ type, request: id, ...fields });
    return id;
  }

  function newChat(auto = false) { // an empty chat, with an id the app made (only those are kept)
    const id = request("brain_chat_new");
    automatic = auto ? id : null;
  }

  function show(chat) { // the chat the app sent: its id, and its whole log in the talk
    current = chat.id;
    root.dataset.chat = current;
    talk()?.setTalk(current, Array.isArray(chat.exchanges) ? chat.exchanges : []);
  }

  function renderList(rows) { // newest first, title and date; a click reopens one, Delete asks first
    $("chat-list").replaceChildren(...rows.map((row) => {
      const item = el("div", "chat-row");
      item.dataset.id = String(row.id || "");
      if (row.id === current) item.setAttribute("aria-current", "true");
      const title = String(row.title || "Untitled chat");
      const reopen = el("button", "open");
      reopen.type = "button";
      reopen.title = title;
      reopen.append(el("span", "title", title), el("span", "when muted", when(row.updated)));
      reopen.addEventListener("click", () => {
        $("chat-history").open = false;
        // the chat shown is never reopened: the app would drop its open card (Task 2's forget)
        if (row.id !== current) {
          summary().focus(); // never on the page while the app answers: then the box, or History again
          reopening = request("brain_chat_open", { id: row.id });
        } else $("talk-text").focus();
      });
      const remove = el("button", "ghost delete", "Delete");
      remove.type = "button";
      remove.setAttribute("aria-label", `Delete ${title}`);
      remove.addEventListener("click", () => forget(row.id, title));
      item.append(reopen, remove);
      return item;
    }));
    if (!rows.length) $("chat-list").append(el("p", "empty muted", "No chats yet"));
  }

  async function forget(id, title) { // Delete: asked first, Keep by default (confirm.js)
    if (!await confirmAction({ title: `Delete "${title}"?`, yes: "Delete",
                               lines: ["Your words and the Brain's answers in it are deleted from this computer."] })) {
      return;
    }
    request("brain_chat_delete", { id });
    summary().focus(); // its row goes: the keys stay on History
    if (id === current) newChat(); // the chat shown went: an empty one takes its place
  }

  $("chat-new").addEventListener("click", () => newChat());
  $("chat-history").addEventListener("toggle", () => {
    if ($("chat-history").open) link.send({ type: "brain_chats" });
  });

  const summary = () => $("chat-history").querySelector("summary");
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
      $("talk-log").scrollTop = $("talk-log").scrollHeight; // the newest line in view again
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
    if ($("chat-history").open) { // History's list first, a second Esc the panel
      $("chat-history").open = false;
      summary().focus();
    } else close();
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
    if (drag?.id !== event.pointerId) return;
    drag.moved = true;
    moveTo(event.clientX - drag.dx, event.clientY - drag.dy);
  });
  for (const type of ["pointerup", "pointercancel"]) {
    bar.addEventListener(type, (event) => {
      if (drag?.id !== event.pointerId) return;
      const { moved } = drag;
      drag = null;
      if (moved) remember(); // a click without a move keeps no place
    });
  }
  addEventListener("resize", place); // another window size: its place for that size, or the default, on screen
  NARROW.addEventListener("change", place);

  return {
    open,
    close,
    get isOpen() { return !root.hidden; },
    onMessage(message) { // the Brain needs the user: a hand-off or a suggestion opens it, never taking the focus
      const cards = message.type === "brain_handoff" ? [message.handoff]
        : message.type === "brain_snapshot" ? message.handoffs || [] : [];
      // only a card it hasn't shown yet: a known card's change (× held its countdown) never reopens it
      const fresh = cards.filter((one) => OPEN.includes(one?.state) && !shownCards.has(one.id));
      for (const one of fresh) shownCards.add(one.id);
      if (fresh.length) {
        $("chat-history").open = false; // History's list never covers the card
        open();
      }
      switch (message.type) {
        case "snapshot": // connected (again): a talk with nothing in it gets a chat of its own; one with words keeps it
          shownCards.clear(); // the app may have restarted: its hand-off ids start again at h1
          if (!current || !$("talk-log").children.length) newChat(true); // never brain_chat_open: its card stays
          break;
        case "brain_chat":
          if (message.request !== waiting || typeof message.chat?.id !== "string") break;
          waiting = null;
          if (message.request === automatic && !talk()?.fresh) break; // words came first: they stay as they are
          show(message.chat);
          if (message.request === reopening) $("talk-text").focus();
          break;
        case "brain_chats":
          renderList(Array.isArray(message.chats) ? message.chats : []);
          break;
        case "error":
          if (!String(message.request || "").startsWith("chat-")) break;
          $("talk-notice").textContent = String(message.text || ""); // "That chat is gone": said, never silent
          if (message.request === reopening) summary().focus();
          link.send({ type: "brain_chats" }); // gone meanwhile
          break;
      }
    },
  };
}
