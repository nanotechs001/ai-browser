// Settings → Permissions (agent powers, Decisions 5 and 7): the folders agents worked in, each with the user's answer
// to "Trust this folder?" and the rules they allowed always there. Remove a rule; Remove trust (the folder is then
// not trusted: its own settings and hooks don't load); Forget the folder (its rules and its answer; the folder itself
// stays). A folder that has gone says so, and keeps its rules until they're removed. Every path and rule is set as
// text.
"use strict";

import { el } from "./chat.js";

const TRUST = { true: "Trusted", false: "Not trusted", null: "Not asked yet" };
const GONE = "This folder isn't there any more: deleted, renamed or unplugged. Its rules stay until you remove them.";

export function mountPermissions({ list, note }, send) {
  let folders = [];
  let drawn = ""; // what the list was drawn from: redrawn only when that changes, so a click isn't lost
  let requests = 0;

  function ask(message) { // each message has a request id, so the app's error comes back to this section
    requests += 1;
    if (!send({ ...message, request: `perm-${requests}` })) {
      note.textContent = "Not connected: is `ai-browser app` running?";
    }
  }

  function button(className, label, onClick) {
    const node = el("button", className, label);
    node.type = "button";
    node.addEventListener("click", onClick);
    return node;
  }

  function drawFolder(row) {
    const box = el("div", "perm-folder card");
    box.dataset.path = row.path;
    const top = el("div", "top-line");
    top.append(el("strong", "name", row.name || row.path),
               el("span", "chip trust", TRUST[String(row.trusted)] || TRUST.null));
    box.append(top, el("p", "muted path", row.path));
    if (row.missing) box.append(el("p", "muted missing", GONE));
    const rules = el("ul", "rules");
    for (const rule of row.rules || []) {
      const item = el("li", "rule");
      item.dataset.rule = rule.rule;
      item.append(el("span", "rule-label", rule.label || rule.rule), button("remove ghost", "Remove",
        () => ask({ type: "permission_rule_remove", folder: row.path, rule: rule.rule })));
      rules.append(item);
    }
    if (!(row.rules || []).length) rules.append(el("li", "muted", "Nothing allowed always."));
    const buttons = el("div", "row");
    if (row.trusted === true) {
      buttons.append(button("untrust", "Remove trust",
        () => ask({ type: "folder_trust", path: row.path, trust: false })));
    }
    const forget = button("forget ghost", "Forget this folder",
      () => ask({ type: "permission_rule_remove", folder: row.path, all: true }));
    forget.title = "Its rules and your trust answer go. The folder itself stays.";
    buttons.append(forget);
    box.append(rules, buttons);
    return box;
  }

  function draw() {
    const signature = JSON.stringify(folders);
    if (signature === drawn) return;
    drawn = signature;
    list.replaceChildren(...folders.map(drawFolder));
    if (!folders.length) list.append(el("p", "muted empty", "No folders yet: pick one for a new task."));
  }

  return {
    onMessage(message) {
      if (message.type === "snapshot") {
        send({ type: "permission_rules" });
      } else if (message.type === "permissions") {
        folders = Array.isArray(message.folders) ? message.folders : [];
        note.textContent = "";
        draw();
      } else if (message.type === "error" && String(message.request || "").startsWith("perm-")) {
        note.textContent = message.text || "";
      }
    },
  };
}
