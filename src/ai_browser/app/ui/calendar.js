// The Calendar (the new look, Decision 8): a month, or a week, with the scheduled templates' next runs (the app's
// workflows list: brain/workflows.py's schedule) and this run's finished agents, at the time each one finished. A
// template opens AI Home at its templates; an agent opens its drawer. Every word is set as text.
"use strict";

import { agentLabel, el } from "./chat.js";
import { icon } from "./icons.js";
import { isFinished } from "./step.js";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                "November", "December"];
const ENDS = { your_turn: "✓", failed: "✗", stopped: "■" };
const IN_A_MONTH = 3; // entries a month's day shows; more say "+2 more"
const MINUTE = 60000; // ms between the grid's own redraws

function startOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function nextDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + 1);
}

function dayKey(date) { // "2026-10-7": a day's cell
  return `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`;
}

function hhmm(date) {
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

export function monthGrid(year, month) { // the 42 days a month shows, from the Monday on or before its 1st
  const lead = (new Date(year, month, 1).getDay() + 6) % 7;
  return Array.from({ length: 42 }, (_, index) => new Date(year, month, 1 - lead + index));
}

export function weekDays(date) { // the week, Monday to Sunday, that holds `date`
  const day = startOfDay(date);
  const lead = (day.getDay() + 6) % 7;
  return Array.from({ length: 7 }, (_, index) => new Date(day.getFullYear(), day.getMonth(), day.getDate() - lead
                                                          + index));
}

export function everyWords(seconds) { // "Every 2h", "Every 30m"
  return seconds % 3600 === 0 ? `Every ${seconds / 3600}h` : `Every ${Math.round(seconds / 60)}m`;
}

// An interval template's next run as of `now`: the one the app sent while it is still ahead, else the run after now
// (the app computed it when it sent the list, and a page left open outlives it). Seconds, as the app's runs are.
function runAfter(run, every, now) {
  const ahead = now.getTime() / 1000;
  return run >= ahead ? run : run + Math.ceil((ahead - run) / every) * every;
}

// What the days from `start` to `end` show: a scheduled template at each of its runs still ahead of `now`, an
// interval one ("every 2h") once a day from its next run, and each finished agent at the time it finished (past by
// then, and kept). In time order.
export function calendarItems(nextRuns, agents, start, end, now = new Date()) {
  const items = [];
  for (const row of Array.isArray(nextRuns) ? nextRuns : []) {
    const runs = (Array.isArray(row.runs) ? row.runs : []).filter(Number.isFinite);
    if (Number.isFinite(row.every) && row.every > 0 && runs.length) {
      const first = startOfDay(new Date(runAfter(runs[0], row.every, now) * 1000));
      for (let day = first > start ? first : startOfDay(start); day < end; day = nextDay(day)) {
        items.push({ kind: "template", slug: row.slug, at: day, label: `${row.name} · ${everyWords(row.every)}`,
                     allDay: true });
      }
    } else {
      for (const run of runs) {
        const at = new Date(run * 1000);
        if (at >= start && at < end && at >= now) items.push({ kind: "template", slug: row.slug, at, label: row.name });
      }
    }
  }
  for (const agent of agents) {
    if (!isFinished(agent) || !Number.isFinite(agent.finished)) continue;
    const at = new Date(agent.finished * 1000);
    if (at >= start && at < end) items.push({ kind: "agent", id: agent.id, at, label: agentLabel(agent),
                                              state: agent.state });
  }
  return items.sort((one, two) => one.at - two.at);
}

export function mountCalendar(root, { onAgent, onTemplate, visible = () => true,
                                 visibleTemplate = () => true }) {
  let mode = "month";
  let cursor = startOfDay(new Date());
  let nextRuns = [];
  let agents = [];
  let showing = false; // drawn only while the Calendar is the view shown
  const title = el("h3", "calendar-title");
  const earlier = el("button", "earlier ghost");
  earlier.type = "button";
  earlier.setAttribute("aria-label", "Earlier");
  earlier.append(icon("left"));
  const today = el("button", "today", "Today");
  today.type = "button";
  const later = el("button", "later ghost");
  later.type = "button";
  later.setAttribute("aria-label", "Later");
  later.append(icon("right"));
  const modes = el("div", "calendar-modes filters");
  for (const [key, label] of [["month", "Month"], ["week", "Week"]]) {
    const tab = el("button", "filter", label);
    tab.type = "button";
    tab.dataset.mode = key;
    tab.addEventListener("click", () => {
      mode = key;
      render();
    });
    modes.append(tab);
  }
  const head = el("div", "calendar-head");
  head.append(earlier, today, later, title, modes);
  const grid = el("div", "calendar-grid");
  root.replaceChildren(head, grid);

  function days() {
    return mode === "month" ? monthGrid(cursor.getFullYear(), cursor.getMonth()) : weekDays(cursor);
  }

  function entry(item) {
    const words = `${item.allDay ? "" : `${hhmm(item.at)} `}${item.kind === "agent" ? `${ENDS[item.state] || "✓"} `
      : ""}${item.label}`;
    const node = el("button", `entry ${item.kind}${item.state ? ` ${item.state}` : ""}`, words);
    node.type = "button";
    node.title = words;
    if (item.kind === "agent") {
      node.dataset.agent = item.id;
      node.addEventListener("click", () => onAgent(item.id));
    } else {
      node.dataset.slug = item.slug;
      node.addEventListener("click", () => onTemplate(item.slug));
    }
    return node;
  }

  function render() {
    if (!showing) return;
    const shown = days();
    const start = shown[0];
    const end = nextDay(shown.at(-1));
    const rows = (Array.isArray(nextRuns) ? nextRuns : []).filter((row) => visibleTemplate(row.slug));
    const items = calendarItems(rows, agents.filter(visible), start, end);
    const todayKey = dayKey(new Date());
    // What it would draw: unchanged, the grid stays as it is (a focused entry keeps its focus, a click isn't lost)
    const signature = JSON.stringify([mode, dayKey(cursor), todayKey, items.map((item) => [
      item.kind, item.id || item.slug, item.at.getTime(), item.label, item.state || "", Boolean(item.allDay)])]);
    if (grid.dataset.drawn === signature) return;
    grid.dataset.drawn = signature;
    title.textContent = mode === "month" ? `${MONTHS[cursor.getMonth()]} ${cursor.getFullYear()}`
      : `${shown[0].getDate()} ${MONTHS[shown[0].getMonth()]} – ${shown[6].getDate()} ${MONTHS[shown[6].getMonth()]}`;
    for (const tab of modes.children) tab.setAttribute("aria-selected", String(tab.dataset.mode === mode));
    const byDay = new Map();
    for (const item of items) {
      const key = dayKey(item.at);
      if (!byDay.has(key)) byDay.set(key, []);
      byDay.get(key).push(item);
    }
    grid.dataset.mode = mode;
    grid.replaceChildren(...WEEKDAYS.map((name) => el("div", "weekday muted", name)), ...shown.map((day) => {
      const cell = el("div", "day");
      cell.dataset.day = dayKey(day);
      if (mode === "month" && day.getMonth() !== cursor.getMonth()) cell.classList.add("other");
      if (dayKey(day) === todayKey) cell.classList.add("today");
      cell.append(el("span", "date", String(day.getDate())));
      const items = byDay.get(dayKey(day)) || [];
      const listed = mode === "month" ? items.slice(0, IN_A_MONTH) : items;
      cell.append(...listed.map(entry));
      if (items.length > listed.length) cell.append(el("span", "more muted", `+${items.length - listed.length} more`));
      return cell;
    }));
  }

  function move(step) {
    cursor = mode === "month" ? new Date(cursor.getFullYear(), cursor.getMonth() + step, 1)
      : new Date(cursor.getFullYear(), cursor.getMonth(), cursor.getDate() + 7 * step);
    render();
  }

  earlier.addEventListener("click", () => move(-1));
  later.addEventListener("click", () => move(1));
  today.addEventListener("click", () => {
    cursor = startOfDay(new Date());
    render();
  });
  setInterval(render, MINUTE); // a page left open: a run that has passed leaves the grid (render does nothing unseen)

  return {
    onMessage(message) {
      if (message.type !== "workflows_snapshot") return;
      nextRuns = message.next_runs || [];
      render();
    },
    agents(map) {
      agents = [...map.values()];
      render();
    },
    shown(page, view) {
      showing = page === "dashboard" && view === "calendar";
      render();
    },
  };
}
