// Mission Control's agent lists (the new look): the List view, My Missions and History. One row per agent, updated in
// place; every word is the app's or Claude's, set as text, with its whole as a tooltip where it may be clipped.
"use strict";

import { agentLabel, el } from "./chat.js";
import { createAvatar } from "./chibi.js";
import { folderName } from "./plan.js";
import { clock, isFinished, STATES, stateOf, stepOf } from "./step.js";

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
