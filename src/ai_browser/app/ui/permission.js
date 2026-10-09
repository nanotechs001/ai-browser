// A tool request waiting for the user, shown as text. Two kinds:
// - one of the user's MCP tools: which agent, the server, the tool and its exact input. Allow once, Always allow
//   (remembered in Integrations), Deny;
// - one of Claude Code's own tools (agent powers): what will happen, as the app read it from the request: the command
//   and its folder, a clipped diff (removed lines red, added green) or the new file, and the size; the path, the site
//   or the query. A sub-agent's request names the sub-agent. Allow once, Always allow for this folder (only where the
//   app offers it: never for a dangerous command or anything outside the folder), and Deny, with a short note to the
//   agent if the user writes one.
// Only these clicks answer it, never anything a page says. Every word is set as text.
"use strict";

const LIMIT = 4000; // characters of an MCP tool's input shown before "Show all"
const NOTE_LIMIT = 300; // characters of Deny's note (the app keeps as many)
const SIGNS = { "-": "del", "+": "add", " ": "ctx", "…": "gap" };

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function bytes(size) { // "840 bytes", "12 KB", "3.4 MB"
  if (!Number.isFinite(size)) return "";
  if (size < 1024) return `${size} bytes`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function toolCard(card, request, agentName) { // one of the user's MCP tools: the server, the tool, its input
  const tool = String(request.tool || "");
  const short = tool.split("__").slice(2).join("__") || tool;
  card.append(el("div", "permission-head", `${agentName || "An agent"} wants to use a tool`));
  const line = el("div", "permission-tool");
  line.append(el("span", "chip", request.server || "tool"), el("strong", "", short));
  card.append(line);
  const input = JSON.stringify(request.input ?? {}, null, 2);
  const shown = el("pre", "permission-input", input.length > LIMIT ? `${input.slice(0, LIMIT)}…` : input);
  card.append(shown);
  if (input.length > LIMIT) {
    const more = el("button", "ghost more", "Show all");
    more.addEventListener("click", () => {
      shown.textContent = input;
      more.remove();
    });
    card.append(more);
  }
}

function diff(lines) { // the clipped diff or the new file: one line each, removed red and added green
  const box = el("div", "diff");
  for (const [sign, text] of lines) box.append(el("div", SIGNS[sign] || "ctx", sign === "…" ? "…" : `${sign} ${text}`));
  return box;
}

function powerCard(card, request, agentName) { // one of Claude Code's own tools, as the app read the request
  const shown = request.card;
  const who = `${agentName || "An agent"}${request.sub ? ` · sub-agent: ${request.sub}` : ""}`;
  card.append(el("div", "permission-head", `${who} wants to ${shown.title || "use a tool"}`));
  const line = el("div", "permission-tool");
  line.append(el("span", "chip badge", shown.badge || "Tool"));
  if (shown.site) line.append(el("strong", "permission-site", shown.site));
  card.append(line);
  if (shown.text) card.append(el("pre", "permission-text", shown.text));
  if (shown.tool === "Bash" && shown.folder) card.append(el("div", "permission-where muted", `In ${shown.folder}`));
  const lines = Array.isArray(shown.lines) ? shown.lines : [];
  if (shown.binary) {
    card.append(el("div", "permission-size muted", `A binary file · ${bytes(shown.size)}`));
  } else if (Number.isFinite(shown.size)) {
    if (lines.length) card.append(diff(lines));
    const first = shown.hidden > 0 ? `Showing the first ${lines.length} lines · ` : "";
    card.append(el("div", "permission-size muted", `${first}${bytes(shown.size)}`));
  }
  if (shown.sandbox) card.append(el("div", "permission-sandbox muted", shown.sandbox));
  if (shown.why) card.append(el("div", "permission-why", `Asked every time: ${shown.why}`));
}

function answers(request, send, power) { // Allow once · Always allow · Deny, and Deny's note
  const box = el("div", "permission-answer");
  const note = el("input", "deny-note");
  note.type = "text";
  note.maxLength = NOTE_LIMIT;
  note.placeholder = "A note for the agent, if you deny (optional)";
  note.setAttribute("aria-label", "A note for the agent, if you deny");
  const row = el("div", "row permission-buttons");
  const done = el("span", "muted");
  let always = "Always allow";
  if (power) {
    always = request.card.always !== true ? ""
      : request.card.scratch ? "Always allow for this agent" : "Always allow for this folder";
  }
  const choices = [["allow-once primary", "Allow once", "once"],
                   ...(always ? [["allow-always", always, "always"]] : []),
                   ["deny", "Deny", "deny"]];
  for (const [className, label, answer] of choices) {
    const choice = el("button", className, label);
    choice.type = "button";
    choice.addEventListener("click", () => {
      const message = { type: "permission", agent: request.agent, request: request.request, answer };
      const words = note.value.trim().slice(0, NOTE_LIMIT);
      if (answer === "deny" && words) message.note = words;
      if (!send(message)) return;
      for (const other of row.querySelectorAll("button")) other.disabled = true;
      note.disabled = true;
      done.textContent = answer === "deny" ? "Denied" : "Allowed";
    });
    row.append(choice);
  }
  row.append(done);
  box.append(note, row);
  return box;
}

export function permissionCard(request, send, agentName = "") {
  const card = el("div", "permission card");
  card.dataset.request = request.request;
  const power = Boolean(request.card) && typeof request.card === "object";
  if (power) powerCard(card, request, agentName);
  else toolCard(card, request, agentName);
  card.append(answers(request, send, power));
  return card;
}
