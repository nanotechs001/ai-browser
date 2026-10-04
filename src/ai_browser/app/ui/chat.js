// An agent's conversation, drawn from its events. Everything from Claude or from pages is set as text, never parsed
// as HTML; **bold** and `code` become elements built here.
"use strict";

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

function actionRow(name, summary) {
  const row = el("div", "action pending");
  row.append(el("span", "icon", "•"), el("span", "name", name || "action"), el("span", "summary", summary || ""),
    el("span", "ms", ""));
  return row;
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
        rows.set(event.id || `row${rows.size}`, add(actionRow(event.name, event.summary)));
        break;
      case "tool_result": {
        const row = rows.get(event.id) || add(actionRow(event.name, ""));
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
