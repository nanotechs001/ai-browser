// The menu's workspaces (the new look, Decision 6): named groups of agents and templates. Each shows its count (its
// agents this run, and its templates the workflows list still has); a click filters the Dashboard, My Missions and
// Templates, and a second click shows every agent again. ⋯ renames or deletes one (deleting removes the grouping only:
// its agents keep running, in no workspace); New Workspace adds one. Names are set as text.
"use strict";

import { el } from "./chat.js";
import { icon } from "./icons.js";

export function countsOf(workspace, agents, slugs) {
  const agentCount = [...agents.values()].filter((agent) => agent.workspace === workspace.id).length;
  const templateCount = (workspace.templates || []).filter((slug) => slugs.has(slug)).length;
  return { agents: agentCount, templates: templateCount, total: agentCount + templateCount };
}

// A Workspace ▾ beside an agent's row or a template: "No workspace", then each workspace. Rebuilt only when what it
// lists changes, and never while it is open.
export function fillMove(select, rows, current) {
  const signature = JSON.stringify([rows.map((row) => [row.id, row.name]), current || ""]);
  if (select.dataset.rows === signature || document.activeElement === select) return;
  select.replaceChildren(...[["", "No workspace"], ...rows.map((row) => [row.id, row.name])].map(([value, label]) => {
    const option = el("option", "", label);
    option.value = value;
    return option;
  }));
  select.value = rows.some((row) => row.id === current) ? current : "";
  select.dataset.rows = signature;
}

export function mountWorkspaces(root, { send, onFilter }) {
  const list = el("ul", "workspace-list");
  const add = el("button", "workspace-new");
  add.type = "button";
  add.title = "New Workspace";
  add.append(icon("plus"), el("span", "label", "New Workspace"));
  const note = el("p", "muted workspace-note");
  root.replaceChildren(el("p", "eyebrow head", "Workspace"), list, add, note);
  let rows = [];
  let agents = new Map();
  let slugs = new Set();
  let active = null;
  let editing = false; // a name is being typed: the list waits, so the box isn't lost to an agent's update
  let asked = 0;
  let drawn = null; // what the list shows now: an agent's update that changes none of it leaves the list alone

  function editor(value, save) { // Enter saves, Esc puts the list back
    const input = el("input", "workspace-name");
    input.type = "text";
    input.maxLength = 40;
    input.value = value;
    input.setAttribute("aria-label", "Workspace name");
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        asked += 1;
        send({ ...save(input.value), request: `ws${asked}` });
      } else if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        editing = false;
        note.textContent = "";
        render();
      }
    });
    editing = true;
    drawn = null; // the list holds the box now: it is drawn again when the box goes
    return input;
  }

  function row(workspace) {
    const item = el("li", "workspace");
    item.dataset.id = workspace.id;
    const counts = countsOf(workspace, agents, slugs);
    const pick = el("button", "workspace-pick");
    pick.type = "button";
    pick.setAttribute("aria-pressed", String(active === workspace.id));
    pick.title = `${workspace.name} · ${counts.agents} agent${counts.agents === 1 ? "" : "s"} · ` // its name too:
      + `${counts.templates} template${counts.templates === 1 ? "" : "s"}`; // the shrunk menu shows icons only
    const name = el("span", "name clip", workspace.name);
    pick.append(icon("folder"), name, el("span", "count", String(counts.total)));
    pick.addEventListener("click", () => onFilter(active === workspace.id ? null : workspace.id));
    const more = el("button", "workspace-more ghost");
    more.type = "button";
    more.setAttribute("aria-label", `More for ${workspace.name}`);
    more.append(icon("more"));
    const menu = el("div", "workspace-menu");
    menu.hidden = true;
    const rename = el("button", "rename", "Rename");
    rename.type = "button";
    rename.addEventListener("click", () => {
      const input = editor(workspace.name, (value) => ({ type: "workspace_save", id: workspace.id, name: value }));
      item.replaceChildren(input);
      input.focus();
    });
    const remove = el("button", "delete", "Delete");
    remove.type = "button";
    remove.addEventListener("click", () => { // a second click: the grouping goes, its agents keep running
      if (!remove.dataset.sure) {
        remove.dataset.sure = "1";
        remove.textContent = "Delete? Its agents keep running";
        return;
      }
      send({ type: "workspace_delete", id: workspace.id });
    });
    menu.append(rename, remove);
    more.addEventListener("click", () => {
      menu.hidden = !menu.hidden;
    });
    item.append(pick, more, menu);
    return item;
  }

  function render() {
    if (editing) return;
    const shown = JSON.stringify([rows.map((one) => [one.id, one.name, countsOf(one, agents, slugs)]), active]);
    if (shown === drawn) return;
    drawn = shown;
    list.replaceChildren(...rows.map(row));
  }

  add.addEventListener("click", () => {
    const input = editor("", (value) => ({ type: "workspace_save", name: value }));
    const item = el("li", "workspace new");
    item.append(input);
    list.append(item);
    input.focus();
  });

  return {
    setActive(id) {
      active = id;
      render();
    },
    agents(map) {
      agents = map;
      render();
    },
    onMessage(message) {
      if (message.type === "snapshot" || message.type === "workspaces") {
        rows = message.workspaces || [];
        editing = false;
        note.textContent = "";
        if (active && !rows.some((one) => one.id === active)) onFilter(null); // deleted: every agent again
        render();
      } else if (message.type === "workflows_snapshot") {
        slugs = new Set((message.workflows || []).map((one) => one.slug));
        render();
      } else if (message.type === "error" && typeof message.request === "string" && /^ws\d+$/.test(message.request)) {
        note.textContent = String(message.text || ""); // the box stays, so the name can be fixed
      }
    },
  };
}
