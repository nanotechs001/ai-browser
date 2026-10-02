// A tool request waiting for the user: which agent, the server, the tool and its exact input, shown as text. Allow
// once, Always allow (remembered in AI Home's Tools) or Deny: only these clicks answer it, never anything a page says.
"use strict";

const LIMIT = 4000; // characters of the input shown before "Show all"

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function permissionCard(request, send, agentName = "") {
  const card = el("div", "permission card");
  card.dataset.request = request.request;
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
  const buttons = el("div", "row permission-buttons");
  const done = el("span", "muted");
  for (const [className, label, answer] of [["allow-once primary", "Allow once", "once"],
                                             ["allow-always", "Always allow", "always"], ["deny", "Deny", "deny"]]) {
    const choice = el("button", className, label);
    choice.addEventListener("click", () => {
      if (!send({ type: "permission", agent: request.agent, request: request.request, answer })) return;
      for (const other of buttons.querySelectorAll("button")) other.disabled = true;
      done.textContent = answer === "deny" ? "Denied" : "Allowed";
    });
    buttons.append(choice);
  }
  buttons.append(done);
  card.append(buttons);
  return card;
}
