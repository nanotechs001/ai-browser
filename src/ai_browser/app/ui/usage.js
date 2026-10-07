// The Usage card (the new look, Decision 7; the user's hand check of 2026-10-07): for each signed-in account (at most
// 3, Default first), its name and two bars, as Claude Code reports them with each request (limits.py): "Current
// session" (its five-hour limit) and "Weekly", each with how much is used and when it resets. The latest reading is
// kept across restarts (accounts.py), so the card says when it was read: "as of 3:12 pm". Never a made-up number: with
// no reading the bars are empty and it says "Updates when an agent works"; a reading whose reset has passed says
// "Reset at 9:30 pm · updates with your next mission". At its limit (a window at 100%, or the account's limit, which
// ends when that window resets) the bar is full: "At its limit until 9:00 pm". A click opens Settings → Accounts
// (mission.js). When the menu shrinks to icons (mission.css) the card is an icon, and its tooltip lists each
// account's numbers. Words are set with textContent; a bar's width only from a number clamped to 0..100.
"use strict";

import { resetTime } from "./accountui.js";
import { el } from "./chat.js";
import { icon } from "./icons.js";

const SHOWN = 3; // accounts listed; more say "+2 more"
const WINDOWS = [["five_hour", "Current session"], ["seven_day", "Weekly"]]; // limits.SHOWN_WINDOWS, with their words
const NEAR = 80; // from this percentage a bar turns amber (--needs); at its limit it is full and red (--fail)
const SAME_RESET = 90; // seconds: an account's limit that ends this close to a window's reset is that window's
const MINUTE = 60000; // a page left open redraws the card once a minute: a reset that passes stops showing its number

const number = (value) => (typeof value === "number" && Number.isFinite(value) ? value : null);

function percentOf(reading) { // a reported percentage from 0 to 100, or null: nothing else is ever drawn
  const used = number(reading?.used);
  return used !== null && used >= 0 && used <= 100 ? used : null;
}

function tipOf(bar) { // a bar in the tooltip of the icon-only menu
  if (bar.percent !== null) return `${bar.label} ${bar.percent}%`;
  if (bar.state === "limit") {
    return `${bar.label} at its limit${bar.end !== null ? ` until ${resetTime(bar.end)}` : ""}`;
  }
  if (bar.state === "reset") return `${bar.label} reset at ${resetTime(bar.end)}`;
  return `${bar.label} no reading yet`;
}

// One account's card in plain data: a bar per window ({window, label, percent: the number shown or null, width:
// 0..100, state: ok | high | limit | reset | none, text: the line under it}), the note by its name, and its tooltip.
export function usageOf(row, now = Date.now() / 1000) {
  const windows = row?.windows && typeof row.windows === "object" ? row.windows : {};
  const limit = number(row?.limit_until);
  const until = limit !== null && limit > now ? limit : null; // the account is at a limit until then
  let placed = false; // that limit is shown on one of the bars
  const bars = WINDOWS.map(([key, label]) => {
    const reading = windows[key];
    const used = percentOf(reading);
    const resets = number(reading?.resets_at);
    const bar = { window: key, label, percent: null, width: 0, state: "none", text: "", end: resets };
    if (used === null) return bar;
    if (resets !== null && resets <= now) {
      return { ...bar, state: "reset", text: `Reset at ${resetTime(resets)} · updates with your next mission` };
    }
    const limited = until !== null && resets !== null && Math.abs(until - resets) <= SAME_RESET;
    if (used >= 100 || limited) {
      placed ||= limited;
      const end = limited ? until : resets;
      return { ...bar, width: 100, state: "limit", end,
               text: end !== null ? `At its limit until ${resetTime(end)}` : "At its limit" };
    }
    return { ...bar, percent: Math.floor(used), width: used, state: used >= NEAR ? "high" : "ok", // never "100%" early
             text: resets !== null ? `resets ${resetTime(resets)}` : "" };
  });
  const read = WINDOWS.map(([key]) => windows[key]).filter((reading) => percentOf(reading) !== null)
    .map((reading) => number(reading.at)).filter((at) => at !== null);
  let note = "";
  let tip = bars.map(tipOf).join(" · ");
  if (until !== null && !placed) { // a limit that ends when no window resets: the account's own words
    note = `At its limit until ${resetTime(until)}`;
    const words = `at its limit until ${resetTime(until)}`;
    tip = bars.every((bar) => bar.state === "none") ? words : `${tip} · ${words}`;
  } else if (bars.every((bar) => bar.state === "none")) {
    note = "Updates when an agent works";
    tip = "updates when an agent works";
  } else if (read.length) {
    note = `as of ${resetTime(Math.max(...read))}`;
  }
  return { bars, note, noteState: until !== null && !placed ? "limit" : "", tip };
}

function accountNode(row, shown) {
  const node = el("span", "usage-account");
  const head = el("span", "usage-head");
  const name = el("span", "usage-name", String(row.name ?? ""));
  name.title = name.textContent;
  head.append(name, el("span", `usage-note ${shown.noteState}`.trim(), shown.note));
  node.append(head);
  for (const bar of shown.bars) {
    const line = el("span", "usage-window");
    line.dataset.window = bar.window;
    line.dataset.state = bar.state;
    const top = el("span", "usage-top");
    top.append(el("span", "usage-label", bar.label),
               el("span", "usage-percent", bar.percent === null ? "" : `${bar.percent}%`));
    const track = el("span", "usage-bar");
    const fill = el("span", "usage-fill");
    fill.style.width = `${Math.min(100, Math.max(0, Number(bar.width) || 0))}%`; // a number, never markup
    track.append(fill);
    const when = el("span", "usage-when", bar.text);
    when.title = bar.text;
    line.append(top, track, when);
    node.append(line);
  }
  return node;
}

export function mountUsage(button) {
  const accounts = el("span", "usage-accounts");
  const words = el("span", "usage-words");
  words.append(el("span", "usage-title", "Usage"), accounts);
  button.replaceChildren(icon("bolt", "icon usage-icon"), words); // the icon shows only in the shrunk menu
  let rows = [];

  function render() {
    const now = Date.now() / 1000;
    const signed = rows.filter((row) => row && typeof row === "object" && row.signed_in !== false);
    const shown = signed.slice(0, SHOWN).map((row) => [row, usageOf(row, now)]);
    accounts.replaceChildren(...shown.map(([row, one]) => accountNode(row, one)));
    if (signed.length > SHOWN) accounts.append(el("span", "usage-more", `+${signed.length - SHOWN} more`));
    if (!signed.length) accounts.append(el("span", "usage-more", "Settings → Accounts"));
    button.title = [...shown.map(([row, one]) => `${String(row.name ?? "")}: ${one.tip}`), "Settings → Accounts"]
      .join("\n");
  }

  setInterval(render, MINUTE);
  return {
    render(next) {
      rows = Array.isArray(next) ? next : [];
      render();
    },
  };
}
