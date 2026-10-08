// Mission Control's right column (the new look, Decision 4): Mission Progress for the agent picked (or the one at
// work), its Current Task with the Running… checklist and Stop, Chat, Hand over and Watch (Answer when a card
// waits), and Recent Activity. Built from the app's agent rows and, for an agent without a to-do list, its actions.
// Every word is set as text, with its whole as a tooltip where it may be clipped.
"use strict";

import { agentLabel, el } from "./chat.js";
import { createAvatar } from "./chibi.js";
import { BADGE_ICONS, icon } from "./icons.js";
import { activityOf, ago, checklistOf, groupsOf, progressOf } from "./progress.js";
import { stateOf, stepOf, timerOf } from "./step.js";

const MARKS = { done: "✓", current: "●", pending: "○" };
const KEPT = 200; // the agent's latest actions and their results: never pushed out by its streamed words
const isAction = (event) => (event?.type === "tool" || event?.type === "tool_result") && !event.sub;
const RUNNING = { working: "Running…", waiting: "Waiting in line…", needs_you: "Waiting for you…", your_turn: "Done",
                  stopped: "Stopped", failed: "Failed" };

export function mountSide({ send, openDrawer, openHistory }) {
  const $ = (id) => document.getElementById(id);
  let agent = null; // the agent shown
  let events = []; // its actions: a checklist without a to-do list
  let all = [];

  function setText(node, text) {
    if (node.textContent !== text) node.textContent = text;
  }

  function setClip(node, text) {
    setText(node, text);
    if (node.title !== text) node.title = text;
  }

  function avatar(holder, row) { // the agent's head, redrawn only when the agent changes
    const id = row?.id || "";
    if (holder.dataset.id === id) return;
    holder.dataset.id = id;
    holder.replaceChildren(...(row ? [createAvatar(row.id)] : []));
  }

  function bar(node, percent) {
    node.parentElement.hidden = percent === null;
    const width = `${percent ?? 0}%`;
    if (node.style.width !== width) node.style.width = width;
  }

  function renderProgress() {
    const { text, percent } = progressOf(agent);
    setText($("progress-text"), agent ? text : "No mission yet");
    setText($("progress-percent"), percent === null ? "" : `${percent}%`);
    bar($("progress-bar"), percent);
    const groups = groupsOf(all);
    const list = $("groups");
    if (list.children.length !== groups.length) {
      list.replaceChildren(...groups.map((group) => {
        const item = el("li", `group ${group.key}`);
        item.dataset.group = group.key;
        item.parts = { face: el("span", "avatar"), count: el("span", "count") };
        item.append(item.parts.face, item.parts.count, el("span", "label muted", group.label));
        return item;
      }));
    }
    groups.forEach((group, index) => {
      const item = list.children[index];
      setText(item.parts.count, String(group.count));
      avatar(item.parts.face, group.face);
    });
  }

  function renderCurrent() {
    $("current-empty").hidden = Boolean(agent);
    $("current-body").hidden = !agent;
    if (!agent) return;
    const step = stepOf(agent);
    const state = stateOf(agent);
    avatar($("current-avatar"), agent);
    const label = agentLabel(agent);
    // with a to-do list the step is the list's: a name the user gave gets a line of its own (else the step is it)
    const nameLine = agent.named === true && step.title !== label;
    setClip($("current-name"), nameLine ? label : "");
    $("current-name").hidden = !nameLine;
    const about = $("current-about"); // What it works on: under the name, wherever the name is
    setClip(about, String(agent.description || ""));
    about.hidden = !agent.description;
    const under = nameLine ? $("current-name") : $("current-step").parentElement;
    if (under.nextElementSibling !== about) under.after(about);
    setClip($("current-step"), step.title);
    setClip($("current-line"), step.line);
    setText($("current-timer"), timerOf(agent));
    const badge = $("current-badge");
    badge.hidden = !step.badge;
    if (badge.dataset.badge !== step.badge) {
      badge.dataset.badge = step.badge;
      badge.replaceChildren(...(step.badge ? [icon(BADGE_ICONS[step.badge] || "tool"),
                                              el("span", "badge-text", step.badge)] : []));
    }
    $("current-needs").hidden = state !== "needs_you";
    setText($("current-needs"), state === "needs_you" ? step.line : "");
    $("current-answer").hidden = state !== "needs_you";
    $("current-stop").hidden = !(agent.state === "working" || agent.state === "waiting" || agent.check);
    $("current-watch").disabled = !agent.working_tab; // the drawer's Watch: only while it has a tab to bring forward
    setText($("running-label"), RUNNING[state] || "");
    bar($("running-bar"), progressOf(agent).percent);
    const items = checklistOf(agent, events);
    const list = $("checklist");
    const signature = JSON.stringify(items);
    if (list.dataset.items !== signature) {
      list.dataset.items = signature;
      list.replaceChildren(...items.map((item) => {
        const row = el("li", item.mark);
        const words = el("span", "clip", item.text);
        words.title = item.text;
        row.append(el("span", "mark", MARKS[item.mark]), words);
        return row;
      }));
      if (!items.length) list.append(el("li", "muted", "No steps yet"));
    }
  }

  function renderActivity() {
    const rows = activityOf(all);
    const list = $("activity-list");
    const signature = JSON.stringify(rows.map((row) => [row.kind, row.agent.id, row.at, row.title, row.line]));
    if (list.dataset.rows !== signature) {
      list.dataset.rows = signature;
      list.replaceChildren(...rows.map((row) => {
        const item = el("li");
        const open = el("button", `activity-row ${row.kind}`);
        open.type = "button";
        const face = el("span", "avatar");
        avatar(face, row.agent);
        const words = el("span", "words");
        const line = el("span", "line muted clip", row.line);
        line.title = row.line;
        words.append(el("strong", "clip", row.title), line);
        const when = el("span", "when muted");
        when.dataset.at = String(row.at);
        open.append(face, el("span", "dot"), words, when);
        open.addEventListener("click", () => openDrawer(row.agent.id));
        item.append(open);
        return item;
      }));
      if (!rows.length) list.append(el("li", "muted empty", "Nothing yet"));
    }
    for (const when of list.querySelectorAll(".when")) setText(when, ago(Number(when.dataset.at)));
  }

  $("current-stop").addEventListener("click", () => agent && send({ type: "stop", id: agent.id }));
  $("current-chat").addEventListener("click", () => agent && openDrawer(agent.id));
  $("current-hand").addEventListener("click", () => agent && openDrawer(agent.id, { tabs: true }));
  $("current-watch").addEventListener("click", () => { // its tab to the front, without opening the drawer
    if (agent?.working_tab) send({ type: "watch", target: agent.working_tab });
  });
  $("current-answer").addEventListener("click", () => agent && openDrawer(agent.id));
  $("see-all").addEventListener("click", openHistory);

  return {
    show(rows, picked) { // every agent (in the workspace), and the one the column is about
      all = rows;
      if (picked?.id !== agent?.id) events = [];
      agent = picked || null;
      renderProgress();
      renderCurrent();
      renderActivity();
    },
    events(id, list) {
      if (agent?.id !== id) return;
      events = Array.isArray(list) ? list.filter(isAction).slice(-KEPT) : [];
      renderCurrent();
    },
    event(id, event) {
      if (agent?.id !== id || !isAction(event)) return;
      events = [...events, event].slice(-KEPT);
      renderCurrent();
    },
    tick() { // once a second: the step's timer and "2m ago"
      if (agent) setText($("current-timer"), timerOf(agent));
      for (const when of $("activity-list").querySelectorAll(".when")) setText(when, ago(Number(when.dataset.at)));
    },
  };
}
