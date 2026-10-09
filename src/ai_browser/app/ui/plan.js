// An agent's plan (Claude Code's to-do list: agent powers, Decision 9) and its sub-agents (Decision 8), as the drawer's
// row and Mission Control's drawer show them, and a task's folder by name. Every word is Claude's or a path, set as
// text.
"use strict";

import { el } from "./chat.js";

const TODO_MARKS = { completed: "✓", in_progress: "●", pending: "○" };
const SUB_MARKS = { done: "✓", working: "●", failed: "✗", stopped: "■" };

export function folderName(path) { // "project", from "/Users/me/code/project"
  const parts = String(path || "").split(/[\\/]+/).filter(Boolean);
  return parts.at(-1) || String(path || "");
}

export function planProgress(todos) { // "3 / 5 steps · 60%", or "" without a list
  const list = Array.isArray(todos) ? todos : [];
  if (!list.length) return "";
  const done = list.filter((item) => item.status === "completed").length;
  return `${done} / ${list.length} steps · ${Math.round((done / list.length) * 100)}%`;
}

export function subagentCount(agent) { // "2 sub-agents working", or ""
  const working = (agent?.subagents || []).filter((row) => row.state === "working").length;
  return working ? `${working} sub-agent${working === 1 ? "" : "s"} working` : "";
}

// The drawer's plan: done ✓, current ● (its activeForm), pending ○. Hidden without a list: the agent's actions show
// instead, in its chat below. Rebuilt only when the list changes.
export function renderPlan(box, todos) {
  const list = Array.isArray(todos) ? todos : [];
  const signature = JSON.stringify(list);
  if (box.dataset.list === signature) return;
  box.dataset.list = signature;
  box.replaceChildren();
  box.hidden = !list.length;
  if (!list.length) return;
  const items = el("ol", "plan-items");
  for (const item of list) {
    const text = item.status === "in_progress" ? item.active || item.content : item.content;
    items.append(el("li", item.status, `${TODO_MARKS[item.status] || "○"} ${text}`));
  }
  box.append(el("h3", "", "Plan"), el("p", "plan-progress muted", planProgress(list)), items);
}

// The drawer's sub-agents: done ✓, working ●, failed ✗ or stopped ■, each with its task and its current action.
export function renderSubagents(box, rows) {
  const list = Array.isArray(rows) ? rows : [];
  const signature = JSON.stringify(list);
  if (box.dataset.list === signature) return;
  box.dataset.list = signature;
  box.replaceChildren();
  box.hidden = !list.length;
  if (!list.length) return;
  const items = el("ul", "subagent-items");
  for (const row of list) {
    const action = row.action ? ` · ${row.action}` : "";
    items.append(el("li", row.state, `${SUB_MARKS[row.state] || "●"} ${row.task}${action}`));
  }
  box.append(el("h3", "", "Sub-agents"), items);
}
