// What a desk, the right column and the lists say of an agent (the new look): its state, its current step and timer,
// and which agents have a desk in the room. Pure functions over the app's agent rows: no page, no element.
"use strict";

import { agentLabel } from "./chat.js";

export const ROOM_LIMIT = 12; // desks in the room, past which the oldest finished agents leave (Decision 3)
export const FINISHED = new Set(["your_turn", "stopped", "failed"]);
export const STATES = { working: "working", waiting: "waiting in line", your_turn: "done", stopped: "stopped",
                        failed: "failed", needs_you: "needs you" };

export function stateOf(agent) { // a card or a bot check waiting: it needs the user, whatever its turn says
  return agent?.permission || agent?.check ? "needs_you" : String(agent?.state || "waiting");
}

export function isFinished(agent) {
  return FINISHED.has(stateOf(agent));
}

// Which agents have a desk: every one that isn't finished, then the newest finished ones, up to `limit` desks in all.
// Past `limit` agents at work, every one of them keeps its desk. Oldest first, as the desks fill the rings.
export function roomAgents(agents, limit = ROOM_LIMIT) {
  const oldest = [...agents].sort((one, two) => (Number(one.created) || 0) - (Number(two.created) || 0));
  const active = oldest.filter((agent) => !isFinished(agent));
  const finished = oldest.filter(isFinished);
  const room = Math.max(0, limit - active.length);
  const kept = new Set([...active, ...finished.slice(Math.max(0, finished.length - room))].map((agent) => agent.id));
  return oldest.filter((agent) => kept.has(agent.id));
}

export function clock(seconds) { // "12s", "3m 05s", "1h 02m"
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  if (total < 60) return `${total}s`;
  if (total < 3600) return `${Math.floor(total / 60)}m ${String(total % 60).padStart(2, "0")}s`;
  return `${Math.floor(total / 3600)}h ${String(Math.floor((total % 3600) / 60)).padStart(2, "0")}m`;
}

export function toolLabel(permission) { // "ClickUp: create task", for a desk's line and the Brain's words
  if (permission?.card) return String(permission.card.title || "use a tool"); // agent powers: "run a command"
  const server = String(permission?.server || "a tool").replace(/^claude_ai_/, "").replaceAll("_", " ");
  const tool = String(permission?.tool || "").split("__").slice(2).join("__").replaceAll("_", " ");
  return tool ? `${server}: ${tool}` : server;
}

export function tickerOf(agent, state = stateOf(agent)) { // the line under the step: what it does, or what waits
  if (state === "needs_you" && agent.check) return `bot check · ${agent.check.site}`;
  if (state === "needs_you" && agent.permission) {
    return `wants ${agent.permission.card ? "to " : ""}${toolLabel(agent.permission)}`;
  }
  if (state === "failed") return agent.status || "failed";
  return agent.last_action || agent.status || STATES[state] || state;
}

// The step card: "2. Analyze" (the to-do list's current item, numbered; else the next one, or the last once all are
// done; without a list, the agent's own name), the line under it, when the step started, and its latest badge.
export function stepOf(agent) {
  const todos = Array.isArray(agent?.todos) ? agent.todos : [];
  const state = stateOf(agent);
  let index = todos.findIndex((item) => item.status === "in_progress");
  if (index < 0 && todos.length) {
    index = Math.min(todos.filter((item) => item.status === "completed").length, todos.length - 1);
  }
  const item = index >= 0 ? todos[index] : null;
  const words = item ? (item.status === "in_progress" ? item.active || item.content : item.content) : "";
  return { state, title: item ? `${index + 1}. ${words}` : agentLabel(agent), line: tickerOf(agent, state),
           since: item?.started ?? agent?.step_since ?? null, badge: String(agent?.badge || "") };
}

// The step's timer: how long the step has run (working), how long a card has waited (needs you), or the whole task's
// time once it is done; "" while it waits in line.
export function timerOf(agent, now = Date.now() / 1000) {
  const state = stateOf(agent);
  if (FINISHED.has(state)) return Number(agent?.seconds) > 0 ? clock(agent.seconds) : "";
  if (state === "needs_you") {
    const since = agent?.permission?.since ?? agent?.check?.since;
    return Number.isFinite(since) ? clock(now - since) : "";
  }
  if (state === "working") {
    const since = stepOf(agent).since;
    return Number.isFinite(since) ? clock(now - since) : "";
  }
  return "";
}
