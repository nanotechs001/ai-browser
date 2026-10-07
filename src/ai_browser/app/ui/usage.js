// The Usage card (the new look, Decision 7): a line per account, and a ring only when Claude Code reported how much of
// a limit is used. Without that: "Within limits", or "At its limit until 9:00 pm" (AI accounts), never a made-up
// number. A click opens Settings → Accounts (mission.js). When the menu shrinks to icons (mission.css), the card is an
// icon alone, so it is never an empty pill.
"use strict";

import { resetTime } from "./accountui.js";
import { el } from "./chat.js";
import { icon } from "./icons.js";

const SHOWN = 3; // accounts listed; more say "+2 more"

export function usageLine(row, now = Date.now() / 1000) {
  if (row.signed_in === false) return { text: "Not signed in", percent: null, state: "out" };
  if (Number.isFinite(row.limit_until) && row.limit_until > now) {
    return { text: `At its limit until ${resetTime(row.limit_until)}`, percent: null, state: "limit" };
  }
  if (Number.isFinite(row.used)) {
    const resets = Number.isFinite(row.used_resets_at) ? ` · resets ${resetTime(row.used_resets_at)}` : "";
    return { text: `${Math.round(row.used)}% used${resets}`, percent: Math.round(row.used),
             state: row.used >= 90 ? "high" : "ok" };
  }
  return { text: "Within limits", percent: null, state: "ok" };
}

export function mountUsage(button) {
  const lines = el("span", "usage-lines");
  const words = el("span", "usage-words");
  words.append(el("span", "usage-title", "Usage"), lines);
  const ring = el("span", "usage-ring");
  const ringText = el("span", "usage-ring-text");
  ring.append(ringText);
  ring.hidden = true;
  button.replaceChildren(icon("bolt", "icon usage-icon"), words, ring); // the icon shows only in the shrunk menu
  return {
    render(rows) {
      const list = Array.isArray(rows) ? rows : [];
      lines.replaceChildren(...list.slice(0, SHOWN).map((row) => {
        const line = usageLine(row);
        const node = el("span", `usage-line ${line.state}`, `${row.name} · ${line.text}`);
        node.title = node.textContent;
        return node;
      }));
      if (list.length > SHOWN) lines.append(el("span", "usage-line muted", `+${list.length - SHOWN} more`));
      if (!list.length) lines.append(el("span", "usage-line muted", "Settings → Accounts"));
      const reported = list.map((row) => usageLine(row)).find((line) => line.percent !== null);
      ring.hidden = !reported; // a ring only for a number Claude Code reported
      ringText.textContent = reported ? `${reported.percent}%` : "";
      if (reported) ring.style.setProperty("--p", String(reported.percent));
    },
  };
}
