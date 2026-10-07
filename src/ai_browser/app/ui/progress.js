// What the right column says (the new look, Decision 4): an agent's progress from its to-do list, its Running…
// checklist, the agents by group, and Recent Activity, all from the app's agent rows (and, for an agent without a
// to-do list, its actions). Pure functions: no page, no element.
"use strict";

import { agentLabel } from "./chat.js";
import { isFinished, stateOf, toolLabel } from "./step.js";

const ACTIONS_SHOWN = 6; // a checklist made of actions: the latest ones
const STATE_WORDS = { working: "Working", waiting: "Waiting in line", needs_you: "Needs you", your_turn: "Done",
                      stopped: "Stopped", failed: "Failed" };
const ENDS = { your_turn: "Mission complete", stopped: "Mission stopped", failed: "Mission failed" };

// "3 / 5 steps complete" and 60, from the to-do list; without one, its state's word and no percentage.
export function progressOf(agent) {
  const todos = Array.isArray(agent?.todos) ? agent.todos : [];
  if (!todos.length) return { text: agent ? STATE_WORDS[stateOf(agent)] || "" : "", percent: null };
  const done = todos.filter((item) => item.status === "completed").length;
  return { text: `${done} / ${todos.length} steps complete`, percent: Math.round((done / todos.length) * 100) };
}

// The Running… checklist: the to-do list (done, current, pending); without one, its latest actions, done once their
// result came back and current until then.
export function checklistOf(agent, events = []) {
  const todos = Array.isArray(agent?.todos) ? agent.todos : [];
  if (todos.length) {
    return todos.map((item) => ({
      mark: item.status === "completed" ? "done" : item.status === "in_progress" ? "current" : "pending",
      text: item.status === "in_progress" ? item.active || item.content : item.content,
    }));
  }
  const list = Array.isArray(events) ? events : [];
  const answered = new Set(list.filter((event) => event?.type === "tool_result").map((event) => event.id));
  return list.filter((event) => event?.type === "tool" && !event.sub).slice(-ACTIONS_SHOWN)
    .map((event) => ({ mark: answered.has(event.id) ? "done" : "current",
                       text: `${event.name || "action"} ${event.summary || ""}`.trim() }));
}

// Mission Progress's groups: Completed (done), In Progress (working) and Pending (waiting in line or needing you),
// each with its newest agent for the picture.
export function groupsOf(agents) {
  const newest = (list) => [...list].sort((one, two) => (Number(two.created) || 0) - (Number(one.created) || 0))[0];
  const of = (states) => agents.filter((agent) => states.includes(stateOf(agent)));
  return [["completed", "Completed", of(["your_turn"])], ["working", "In Progress", of(["working"])],
          ["pending", "Pending", of(["waiting", "needs_you"])]]
    .map(([key, label, list]) => ({ key, label, count: list.length, face: newest(list) || null }));
}

export function ago(seconds, now = Date.now() / 1000) { // "just now", "2m ago", "3h ago", "2d ago"
  const gone = Math.max(0, now - Number(seconds || 0));
  if (gone < 45) return "just now";
  if (gone < 3600) return `${Math.max(1, Math.round(gone / 60))}m ago`;
  if (gone < 86400) return `${Math.round(gone / 3600)}h ago`;
  return `${Math.round(gone / 86400)}d ago`;
}

// Recent Activity, newest first: each agent's start, each step it finished, a card waiting for the user, its end. A
// step's end (its start plus how long it took, both rounded) never comes after the agent's own end, and at the same
// moment the later part of the story comes first.
export function activityOf(agents, limit = 6) {
  const out = [];
  for (const agent of agents) {
    const label = agentLabel(agent);
    if (Number.isFinite(agent.created)) {
      out.push({ kind: "started", agent, at: agent.created, title: "Mission started", line: label });
    }
    for (const item of Array.isArray(agent.todos) ? agent.todos : []) {
      if (item.status === "completed" && Number.isFinite(item.started) && Number.isFinite(item.took)) {
        const at = Math.min(item.started + item.took, Number(agent.finished) || Infinity);
        out.push({ kind: "step", agent, at, title: "Step done", line: item.content });
      }
    }
    const since = agent.permission?.since ?? agent.check?.since;
    if (stateOf(agent) === "needs_you" && Number.isFinite(since)) {
      const what = agent.check ? `bot check on ${agent.check.site}`
        : `wants ${agent.permission?.card ? "to " : ""}${toolLabel(agent.permission)}`;
      out.push({ kind: "needs", agent, at: since, title: "Needs you", line: `${label}: ${what}` });
    }
    if (isFinished(agent) && Number.isFinite(agent.finished)) {
      out.push({ kind: agent.state === "failed" ? "failed" : "done", agent, at: agent.finished,
                 title: ENDS[agent.state] || "Mission ended", line: agent.result || agent.status || label });
    }
  }
  return out.map((item, order) => ({ item, order }))
    .sort((one, two) => two.item.at - one.item.at || two.order - one.order)
    .slice(0, limit).map(({ item }) => item);
}
