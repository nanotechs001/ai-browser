// Mission Control's agent lists (the new look): the List view, My Missions and History. One row per agent, updated in
// place; every word is the app's or Claude's, set as text, with its whole as a tooltip where it may be clipped.
"use strict";

import { agentLabel, el } from "./chat.js";
import { createAvatar } from "./chibi.js";
import { folderName } from "./plan.js";
import { clock, FINISHED, isFinished, STATES, stateOf, stepOf } from "./step.js";

function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

function setClip(node, text, title = text) {
  setText(node, text);
  if (node.title !== title) node.title = title;
}

// One agent as a row: its picture, its name, its current step, its folder and account, its state, and its time (how
// long it took once done, else how long it has run). A click lands on `.open`.
export function missionRow(agent) {
  const row = el("div", "mission");
  row.dataset.id = agent.id;
  const open = el("button", "open");
  open.type = "button";
  const face = el("span", "avatar");
  face.append(createAvatar(agent.id));
  row.parts = { open, label: el("strong", "label clip"), step: el("span", "step-words clip"),
                folder: el("span", "folder muted clip"), account: el("span", "account muted clip"),
                state: el("span", "chip"), time: el("span", "time muted") };
  const words = el("span", "words");
  words.append(row.parts.label, row.parts.step);
  const meta = el("span", "meta");
  meta.append(row.parts.folder, row.parts.account);
  open.append(face, words, meta, row.parts.state, row.parts.time);
  row.append(open);
  fillMissionRow(row, agent);
  return row;
}

export function fillMissionRow(row, agent, now = Date.now() / 1000) {
  const step = stepOf(agent);
  const state = stateOf(agent);
  const label = agentLabel(agent);
  setClip(row.parts.label, label);
  setClip(row.parts.step, step.title === label ? step.line : step.title);
  setClip(row.parts.folder, agent.folder ? folderName(agent.folder) : "No folder",
          agent.folder || "Its own scratch folder");
  setClip(row.parts.account, agent.account?.name || "");
  setText(row.parts.state, STATES[state] || state);
  if (row.parts.state.className !== `chip ${state}`) row.parts.state.className = `chip ${state}`;
  setText(row.parts.time, isFinished(agent) ? clock(agent.seconds) : clock(now - (Number(agent.created) || now)));
}

// The List view: the room's agents, oldest first, as the desks stand.
export function mountList(root, { onOpen }) {
  const box = el("div", "missions-list");
  const empty = el("p", "muted empty", "No agents in the room yet: start a mission below.");
  root.replaceChildren(box, empty);
  const rows = new Map();
  return {
    render(agents) {
      const ids = agents.map((agent) => agent.id);
      for (const [id, row] of rows) {
        if (!ids.includes(id)) {
          row.remove();
          rows.delete(id);
        }
      }
      agents.forEach((agent, index) => {
        let row = rows.get(agent.id);
        if (!row) {
          row = missionRow(agent);
          row.parts.open.addEventListener("click", () => onOpen(agent.id));
          rows.set(agent.id, row);
        } else {
          fillMissionRow(row, agent);
        }
        if (box.children[index] !== row) box.insertBefore(row, box.children[index] || null);
      });
      empty.hidden = agents.length > 0;
    },
  };
}

const FILTERS = { all: () => true, working: (state) => state === "working" || state === "waiting",
                  needs_you: (state) => state === "needs_you", done: (state) => FINISHED.has(state) };
const FILTER_WORDS = [["all", "All"], ["working", "Working"], ["needs_you", "Needs you"], ["done", "Done"]];
const MARKS = { your_turn: "done", stopped: "stopped", failed: "failed" };

export function pageHead(title, ...rest) { // a menu page's heading, and its controls beside it
  const head = el("header", "page-head");
  head.append(el("h2", "", title), ...rest);
  return head;
}

// My Missions (Decision 5): every agent as a row, newest first, filtered by All · Working (at work, or waiting in
// line) · Needs you · Done, and by the menu's workspace. A click opens its drawer.
export function mountMissions(root, { onOpen, visible = () => true, decorate = () => {} }) {
  const filters = el("div", "filters");
  filters.setAttribute("role", "tablist");
  filters.setAttribute("aria-label", "Show");
  const box = el("div", "missions-list");
  const empty = el("p", "empty", "No missions here yet.");
  root.replaceChildren(pageHead("My Missions", filters), box, empty);
  const rows = new Map();
  let agents = new Map();
  let filter = "all";

  function render() {
    const listed = [...agents.values()].filter(visible)
      .sort((one, two) => (Number(two.created) || 0) - (Number(one.created) || 0));
    const ids = new Set(listed.map((agent) => agent.id));
    for (const [id, row] of rows) {
      if (!agents.has(id)) {
        row.remove();
        rows.delete(id);
      } else if (!ids.has(id)) {
        row.hidden = true; // outside the workspace picked in the menu
      }
    }
    let shown = 0;
    listed.forEach((agent, index) => {
      let row = rows.get(agent.id);
      if (!row) {
        row = missionRow(agent);
        row.parts.open.addEventListener("click", () => onOpen(agent.id));
        rows.set(agent.id, row);
      } else {
        fillMissionRow(row, agent);
      }
      decorate(row, agent);
      row.hidden = !FILTERS[filter](stateOf(agent));
      if (!row.hidden) shown += 1;
      if (box.children[index] !== row) box.insertBefore(row, box.children[index] || null);
    });
    empty.hidden = shown > 0;
  }

  for (const [key, label] of FILTER_WORDS) {
    const tab = el("button", "filter", label);
    tab.type = "button";
    tab.dataset.filter = key;
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-selected", String(key === filter));
    tab.addEventListener("click", () => {
      filter = key;
      for (const one of filters.children) one.setAttribute("aria-selected", String(one.dataset.filter === filter));
      render();
    });
    filters.append(tab);
  }

  return {
    agents(map) {
      agents = map;
      render();
    },
    shown(page) {
      if (page === "missions") render();
    },
  };
}

// History (Decision 5): this run's finished agents, newest first: the task, its result, how long it took, its account
// and the files it changed, with a search. Open shows its whole chat and actions (its drawer). Agents aren't kept
// across restarts: resuming one comes with Projects.
export function mountHistory(root, { onOpen, visible = () => true }) {
  const search = el("input", "search");
  search.type = "search";
  search.id = "history-search";
  search.placeholder = "Search a task, a result or a file";
  search.setAttribute("aria-label", "Search history");
  const box = el("ol", "history-list");
  const empty = el("p", "empty", "Nothing finished yet.");
  root.replaceChildren(pageHead("History", search), box, empty);
  const rows = new Map();
  let agents = new Map();

  function row(agent) {
    const item = el("li", "history-row");
    item.dataset.id = agent.id;
    const face = el("span", "avatar");
    face.append(createAvatar(agent.id));
    item.parts = { label: el("strong", "label clip"), result: el("span", "result clip"), state: el("span", "chip"),
                   took: el("span", "took muted"), account: el("span", "account muted clip"),
                   files: el("span", "files muted") };
    const words = el("span", "words");
    words.append(item.parts.label, item.parts.result);
    const open = el("button", "open", "Open");
    open.type = "button";
    open.addEventListener("click", () => onOpen(agent.id));
    item.append(face, words, item.parts.state, item.parts.took, item.parts.account, item.parts.files, open);
    return item;
  }

  function fill(item, agent) {
    const state = stateOf(agent);
    setClip(item.parts.label, agentLabel(agent));
    setClip(item.parts.result, agent.result || agent.status || STATES[state] || state);
    setText(item.parts.state, MARKS[state] || state);
    if (item.parts.state.className !== `chip ${state}`) item.parts.state.className = `chip ${state}`;
    setText(item.parts.took, clock(agent.seconds));
    setClip(item.parts.account, agent.account?.name || "");
    const files = Array.isArray(agent.files) ? agent.files : [];
    setText(item.parts.files, files.length ? `${files.length} file${files.length === 1 ? "" : "s"} changed`
      : "No files changed");
    if (item.parts.files.title !== files.join("\n")) item.parts.files.title = files.join("\n");
  }

  function words(agent) { // what the search looks in
    return [agentLabel(agent), agent.result, agent.status, agent.folder, agent.account?.name, ...(agent.files || [])]
      .join("\n").toLowerCase();
  }

  function render() {
    const query = search.value.trim().toLowerCase();
    const listed = [...agents.values()].filter((agent) => isFinished(agent) && visible(agent))
      .sort((one, two) => (Number(two.finished) || 0) - (Number(one.finished) || 0));
    const ids = new Set(listed.map((agent) => agent.id));
    for (const [id, item] of rows) {
      if (!ids.has(id)) {
        item.remove();
        rows.delete(id);
      }
    }
    let shown = 0;
    listed.forEach((agent, index) => {
      let item = rows.get(agent.id);
      if (!item) {
        item = row(agent);
        rows.set(agent.id, item);
      }
      fill(item, agent);
      item.hidden = Boolean(query) && !words(agent).includes(query);
      if (!item.hidden) shown += 1;
      if (box.children[index] !== item) box.insertBefore(item, box.children[index] || null);
    });
    empty.hidden = shown > 0;
    empty.textContent = listed.length ? "Nothing matches." : "Nothing finished yet.";
  }

  search.addEventListener("input", render);
  return {
    agents(map) {
      agents = map;
      render();
    },
    shown(page) {
      if (page === "history") render();
    },
  };
}
