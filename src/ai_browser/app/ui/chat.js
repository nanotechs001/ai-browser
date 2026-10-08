// An agent's conversation, drawn from its events. Everything from Claude or from pages is set as text, never parsed
// as HTML; **bold** and `code` become elements built here.
"use strict";

// Auto-approve in its folder (the user's choice, 2026-10-07): the switch's words, and the mark of what ran without a
// card. The composer's and the drawer's switch say the same. Ordinary commands run without a card where the app says
// so (`auto_commands`): on a Mac, in Claude Code's sandbox (`auto_sandbox`); on Windows, without one (the user's
// choice, 2026-10-08). Elsewhere only file edits do.
export const AUTO_LABEL = "Auto-approve in its folder";
export const AUTO_EDITS_ONLY = "On this computer, commands still ask: only file edits run without a card";
export const AUTO_NO_SANDBOX = "On Windows there's no sandbox: a script it runs can read your files and reach sites";
const AUTO_JUDGED = "What still asks is judged from what a command names, not from what a script it runs does.";
const AUTO_MARK = "Ran without a card: Auto-approve in its folder";

export function autoTitle(commands, sandbox) { // the switch's title, for this computer
  if (!commands) {
    return `${AUTO_EDITS_ONLY}. Edits and new files inside the task's folder run without one; anything outside it, `
      + `and Git's, Claude Code's or an editor's own settings, still ask. ${AUTO_JUDGED}`;
  }
  return sandbox
    ? "Edits, new files, ordinary commands and scripts (reading, building, testing, everyday Git) inside the task's "
      + "folder run without a card, the commands in Claude Code's sandbox. Deleting, sudo, anything outside the "
      + `folder, force-push and reaching a site still ask. ${AUTO_JUDGED}`
    : "Edits, new files, ordinary commands and scripts (reading, building, testing, everyday Git) inside the task's "
      + `folder run without a card. ${AUTO_NO_SANDBOX}. Deleting, admin, anything outside its folder, force-push and `
      + "reaching a site (installing, git push or pull, a build that downloads, like cargo or go) still ask. "
      + AUTO_JUDGED;
}

export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// An agent's number, the one the user sees ("1 · Fix the footer"): the app's `number`, else its id's digits (a3 is
// 3). It is fixed while the app runs; numbers start at 1 again after a restart.
export function agentNumber(agent) {
  if (Number.isInteger(agent?.number)) return agent.number;
  const digits = String(agent?.id ?? "").replace(/\D/g, "");
  return digits ? Number(digits) : null;
}

export function agentLabel(agent) { // "1 · Fix the footer": every page names an agent this one way
  const number = agentNumber(agent);
  const name = String(agent?.name || "an agent");
  return number === null ? name : `${number} · ${name}`;
}

// A clipped line's tooltip: the whole name, then what it works on.
export function agentTip(agent, label = agentLabel(agent)) {
  return agent?.description ? `${label}\n${agent.description}` : label;
}

export function renderText(node, text) {
  node.textContent = "";
  let last = 0;
  for (const match of String(text).matchAll(/(\*\*[^*\n]+\*\*|`[^`\n]+`)/g)) {
    if (match.index > last) node.append(document.createTextNode(text.slice(last, match.index)));
    const token = match[0];
    node.append(token.startsWith("**") ? el("strong", "", token.slice(2, -2)) : el("code", "", token.slice(1, -1)));
    last = match.index + token.length;
  }
  if (last < text.length) node.append(document.createTextNode(text.slice(last)));
}

function clock(seconds) { // "14:05", this computer's time; "" without one
  const when = new Date(Number(seconds) * 1000);
  if (!seconds || Number.isNaN(when.getTime())) return "";
  return `${String(when.getHours()).padStart(2, "0")}:${String(when.getMinutes()).padStart(2, "0")}`;
}

// One tool use: its badge (Bash, Edit, Web Fetch, Browser Agent, Sub-agent, Skill…), its name and summary, and its
// time (agent powers, Decision 10). A sub-agent's own lines are marked "sub"; what Auto-approve in its folder ran
// without a card, "auto" beside its badge.
function actionRow(event) {
  const row = el("div", `action pending${event.sub ? " sub" : ""}`);
  row.append(el("span", "icon", "•"), el("span", "badge", event.badge || "Tool"),
    el("span", "name", event.name || "action"), el("span", "summary", event.summary || ""), el("span", "ms", ""),
    el("span", "at", clock(event.at)));
  if (event.auto === true) markAuto(row);
  return row;
}

function markAuto(row) {
  if (row.querySelector(".auto")) return;
  const mark = el("span", "auto", "auto");
  mark.title = AUTO_MARK;
  row.querySelector(".badge").after(mark);
}

export function createChat(container, { onPage = () => {} } = {}) {
  let bubble = null;
  const rows = new Map(); // tool_use id -> its action row

  function add(node) {
    container.querySelector(".empty")?.remove();
    container.append(node);
    container.scrollTop = container.scrollHeight;
    return node;
  }

  function append(event) {
    switch (event.type) {
      case "user":
        bubble = null;
        add(el("div", "msg user", event.text));
        break;
      case "queued":
        add(el("div", "msg user queued", event.text)).title = "Runs when the current answer is done";
        break;
      case "delta":
        if (!bubble) {
          bubble = add(el("div", "msg claude"));
          bubble.raw = "";
        }
        bubble.raw += event.text || "";
        renderText(bubble, bubble.raw);
        container.scrollTop = container.scrollHeight;
        break;
      case "message_end":
        bubble = null;
        break;
      case "tool":
        rows.set(event.id || `row${rows.size}`, add(actionRow(event)));
        break;
      case "auto": { // Auto-approve in its folder ran this line's action without a card
        const row = rows.get(event.id);
        if (row) markAuto(row);
        break;
      }
      case "tool_result": {
        const row = rows.get(event.id) || add(actionRow({ name: event.name, sub: event.sub }));
        row.classList.remove("pending");
        row.classList.add(event.is_error ? "fail" : "ok");
        row.querySelector(".icon").textContent = event.is_error ? "✗" : "✓";
        if (event.ms !== null && event.ms !== undefined) row.querySelector(".ms").textContent = `${event.ms} ms`;
        const lines = (event.lines || []).filter((line) => line.trim() && !line.startsWith("⏱")).slice(0, 6);
        if (lines.length) row.append(el("pre", "result", lines.join("\n")));
        if (event.page) onPage(event.page);
        container.scrollTop = container.scrollHeight;
        break;
      }
      case "done":
        bubble = null;
        add(el("div", "meta", event.stopped ? "Stopped" : `Done in ${event.seconds} s`));
        break;
      case "note": // a line from AI Browser itself (a move's hand-over note): set as text
        bubble = null;
        add(el("div", "meta", event.text || ""));
        break;
      case "error":
        bubble = null;
        add(el("div", "msg error", event.text || "Something went wrong"));
        break;
      case "limit": // its account hit its usage limit: its row says which, and when it resets
        bubble = null;
        add(el("div", "msg error", "Stopped at the account's usage limit."));
        break;
    }
  }

  function reset(emptyText) {
    container.textContent = "";
    bubble = null;
    rows.clear();
    if (emptyText) container.append(el("p", "empty", emptyText));
  }

  return { append, reset };
}
