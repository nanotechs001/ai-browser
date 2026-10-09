// Mission Control's Knowledge and Integrations (the new look, Decision 5), on the menu's pages. Knowledge is the skills
// (what each one teaches, which agents use it, Use in new mission, Ask an agent to use it, Remove, Bring back) and
// Train. Integrations are the Tools, each server on or off per account. Every word is set as text.
"use strict";

import { el } from "./chat.js";
import { pageHead } from "./pages.js";
import { mountTools } from "./tools.js";
import { mountTrain } from "./train.js";

// useSkill(ref): Use in new mission (Build a Mission's Skills ticks it)
export function mountKnowledge(root, link, { tabs = () => [], model = () => "sonnet", useSkill = () => {} } = {}) {
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
  let running = []; // the open agents an agent's Ask can go to (not failed)
  let all = []; // every agent: "in use by" reads what each one loaded

  function usedBy(skill) {
    return all.filter((agent) => (agent.loaded_skills || []).some((name) => name === skill.ref || name === skill.name
      || name.endsWith(`:${skill.name}`)));
  }

  function refreshUses() { // the "in use by" chips and the agents to ask, updated in place: a list never rebuilt
    const options = running.map((agent) => `${agent.id}:${agent.name}`).join("|");
    for (const row of list.querySelectorAll(".skill")) {
      const { inUse, choose, ask } = row.parts;
      const names = usedBy(row.skill).map((agent) => agent.name);
      if (inUse.dataset.names !== names.join("|")) {
        inUse.replaceChildren(...names.map((name) => el("span", "chip", `in use by ${name}`)));
        inUse.dataset.names = names.join("|");
      }
      if (choose.dataset.options !== options && document.activeElement !== choose) { // never while it's open
        const kept = choose.value;
        choose.replaceChildren(...running.map((agent) => {
          const option = el("option", "", agent.name);
          option.value = agent.id;
          return option;
        }));
        if (running.some((agent) => agent.id === kept)) choose.value = kept;
        choose.dataset.options = options;
      }
      choose.hidden = ask.hidden = !running.length;
    }
  }

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
      const uses = el("div", "uses");
      const inUse = el("span", "in-use");
      const use = el("button", "use", "Use in new mission");
      use.type = "button";
      use.addEventListener("click", () => useSkill(skill.ref));
      const choose = el("select", "ask-who");
      choose.setAttribute("aria-label", "An agent to ask");
      const ask = el("button", "ask", "Ask an agent to use it");
      ask.type = "button";
      ask.addEventListener("click", () => { // a message to that agent, the user's click: as the drawer's Send
        if (choose.value) link.send({ type: "send", id: choose.value,
                                      text: `Load and use the skill ${skill.ref} with load_skill` });
      });
      uses.append(inUse, use, choose, ask);
      row.append(top, el("div", "desc muted", skill.description || "No description"), uses);
      row.skill = skill;
      row.parts = { inUse, choose, ask };
      return row;
    }));
    if (!shown.length) list.append(el("p", "empty", skills.length ? "No skill matches." : "No skills yet."));
    refreshUses();
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
    agents(map) { // mission.js, on every change of an agent
      all = [...map.values()];
      running = all.filter((agent) => agent.state !== "failed");
      refreshUses();
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
