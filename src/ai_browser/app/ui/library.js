// Mission Control's Knowledge and Integrations (the new look, Decision 5): AI Home's own pieces, on the menu's pages.
// Knowledge is the skills (what each one teaches, Remove, Bring back) and Train. Integrations are the Tools, each
// server on or off per account. Templates stay AI Home's alone (the brain-delegation spec). Every word is set as text.
"use strict";

import { el } from "./chat.js";
import { pageHead } from "./pages.js";
import { mountTools } from "./tools.js";
import { mountTrain } from "./train.js";

export function mountKnowledge(root, link, { tabs = () => [], model = () => "sonnet" } = {}) {
  const search = el("input", "search");
  search.type = "search";
  search.id = "skill-find";
  search.placeholder = "Search the skills";
  search.setAttribute("aria-label", "Search the skills");
  const list = el("div", "skills-list");
  const note = el("p", "muted knowledge-note");
  const removed = el("details", "removed");
  const removedList = el("ul", "removed-list");
  removed.append(el("summary", "", "Removed from AI Browser's agents"), removedList);
  const trainBody = el("div", "train-body");
  root.replaceChildren(pageHead("Knowledge", search), el("p", "page-note", "Skills teach agents how you like things "
    + "done. Remove hides one from AI Browser's agents: its files stay where they are."), list, note, removed,
                       el("h3", "", "Train a new skill"), trainBody);
  const train = mountTrain(trainBody, link, { tabs, model });
  let skills = [];
  let blocked = [];
  let asked = 0;

  function block(ref, on) {
    asked += 1;
    note.textContent = "";
    link.send({ type: "skill_block", ref, blocked: on, request: `k${asked}` });
  }

  function render() {
    const query = search.value.trim().toLowerCase();
    const shown = skills.filter((skill) => !query || `${skill.ref} ${skill.description}`.toLowerCase().includes(query));
    list.replaceChildren(...shown.slice(0, 300).map((skill) => {
      const row = el("div", "skill card");
      row.dataset.ref = skill.ref;
      const top = el("div", "top-line");
      const remove = el("button", "remove ghost", "Remove");
      remove.type = "button";
      remove.title = "Hide it from AI Browser's agents. Its files stay where they are.";
      remove.addEventListener("click", () => block(skill.ref, true));
      top.append(el("strong", "name", skill.name), el("span", "chip", skill.source), remove);
      row.append(top, el("div", "desc muted", skill.description || "No description"));
      return row;
    }));
    if (!shown.length) list.append(el("p", "empty", skills.length ? "No skill matches." : "No skills yet."));
    removed.hidden = !blocked.length;
    removedList.replaceChildren(...blocked.map((ref) => {
      const item = el("li");
      const back = el("button", "bring-back", "Bring back");
      back.type = "button";
      back.addEventListener("click", () => block(ref, false));
      item.append(el("span", "name", ref), back);
      return item;
    }));
  }

  search.addEventListener("input", render);
  return {
    onMessage(message) {
      train.onMessage(message);
      if (message.type === "skills") {
        skills = message.skills || [];
        blocked = Array.isArray(message.blocked) ? message.blocked : [];
        render();
      } else if (message.type === "error" && typeof message.request === "string" && /^k\d+$/.test(message.request)) {
        note.textContent = String(message.text || "");
      } else if (message.type === "tabs" || message.type === "snapshot") {
        queueMicrotask(() => train.tabsChanged()); // after mission.js has kept the new tab list
      }
    },
    shown(page) {
      if (page === "knowledge") link.send({ type: "skills" });
    },
  };
}

export function mountIntegrations(root, link) {
  const body = el("div", "integrations-body");
  root.replaceChildren(pageHead("Integrations"), el("p", "page-note", "Your tools (MCP servers), switched on or off "
    + "for each account's agents."), body);
  const tools = mountTools(body, link);
  return {
    onMessage(message) {
      tools.onMessage(message);
      if (message.type === "snapshot" || message.type === "accounts") tools.setAccounts(message.accounts || []);
    },
    shown(page) {
      if (page === "integrations") tools.refresh();
    },
  };
}
