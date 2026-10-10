// Mission Control's Agents page (the saved-agents spec, 1): the saved agents as cards (name, what it works on, its
// Brave profile, its next scheduled task, whether a run of it works) with New agent, and under them Tasks for any
// agent (the templates that run as a new agent, workflows.js). A card opens the agent's settings in a panel over the
// page: Name, What it works on, Instruction, Browser profile, Web, Model, Effort, Account, Folder, Auto-approve in its
// folder, Skills (Can use, Load at start) and its Tasks. Only Save writes an agent (saved_agent_save, app-only); the
// app's refusal words show under it. Delete agent asks first, in the page (confirm.js). Every word is set as text.
"use strict";

import { EFFORTS, agentLabel, el } from "./chat.js";
import { confirmAction } from "./confirm.js";
import { mountFolderPicker } from "./folderpick.js";
import { stateOf } from "./step.js";
import { pageHead } from "./pages.js";
import { profileDot } from "./profiledot.js";
import { mountWorkflows } from "./workflows.js";

const WEBS = [["web", "Web + Brave"], ["brave", "Brave only"], ["none", "No web"]];
const MODELS = [["opus", "Opus · most capable"], ["sonnet", "Sonnet · balanced"], ["haiku", "Haiku · fastest"]];
const GOING = ["working", "waiting", "needs_you"]; // a run still going: one run at a time per agent
const EMPTY = { slug: "", name: "", description: "", instruction: "", profile: null, web: "web", model: "sonnet",
                effort: "default", account: null, folder: null, auto: false, use: [], load: [] };

function option(value, label) {
  const node = el("option", "", label);
  node.value = value;
  return node;
}

function field(label, control, note = "") {
  const wrap = el("label", "field");
  wrap.append(el("span", "muted", label), control);
  if (note) wrap.append(el("span", "muted field-note", note));
  return wrap;
}

function when(seconds) { // "Mon 09:00", in the user's own way of writing it
  return new Date(seconds * 1000).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" });
}

// panel: the <aside> its settings open in; agents(): the runs, as mission.js keeps them (a Map); accounts(): Settings
// → Accounts' rows (names and "signed in", never an email)
export function mountAgentsPage(root, panel, { link, agents = () => new Map(), accounts = () => [] }) {
  const send = (message) => link.send(message);
  let saved = []; // the saved agents, as the app lists them
  let profiles = []; // Brave's profiles: {folder, name, color, ready}
  let snapshot = { workflows: [], next_runs: [] }; // the latest workflows snapshot
  let skills = []; // every installed skill: {ref, name, description}
  let sites = []; // the Brain's watch list: a message task's sites
  let servers = []; // the MCP servers switched on for the default account: what a task may use
  let editing = null; // the agent in the panel: its slug, or "" for a new one; null: the panel is shut
  let pending = null; // the Save waiting for its answer
  let saves = 0;
  const use = new Set(); // Can use: none ticked is every skill
  const load = new Set(); // Load at start

  const newAgent = el("button", "primary new-agent", "New agent");
  newAgent.type = "button";
  const cards = el("div", "agent-cards");
  const anyBox = el("div", "any-tasks");
  root.replaceChildren(pageHead("Agents", newAgent), el("p", "page-note", "Agents you set up once and run many "
    + "times: each with its own instruction, Brave profile, skills and schedule."), cards,
                       el("h3", "", "Tasks for any agent"), el("p", "page-note", "Templates that run as a new agent "
    + "each time. Runs as moves one to an agent of yours."), anyBox);
  const anyTasks = mountWorkflows(anyBox, link, { skills: () => skills, sites: () => sites, servers: () => servers,
                                                  heading: "New task", filter: (task) => !task.runs_as,
                                                  agents: () => saved });

  // ---- the settings panel ----------------------------------------------------------------------------------------
  const title = el("strong", "agent-panel-title");
  const close = el("button", "ghost", "✕");
  close.type = "button";
  close.setAttribute("aria-label", "Close");
  const head = el("header");
  head.append(title, close);
  const body = el("div", "agent-panel-body");
  panel.replaceChildren(head, body);
  const name = el("input");
  name.type = "text";
  name.maxLength = 60;
  name.name = "agent-name";
  const about = el("input");
  about.type = "text";
  about.maxLength = 160;
  about.name = "agent-about";
  const instruction = el("textarea");
  instruction.rows = 6;
  instruction.maxLength = 8000;
  instruction.name = "agent-instruction";
  instruction.placeholder = "What this agent should always keep in mind, in your words";
  const profile = el("select");
  profile.name = "agent-profile";
  const web = el("select");
  web.name = "agent-web";
  web.replaceChildren(...WEBS.map(([value, label]) => option(value, label)));
  const model = el("select");
  model.name = "agent-model";
  model.replaceChildren(...MODELS.map(([value, label]) => option(value, label)));
  const effort = el("select");
  effort.name = "agent-effort";
  effort.replaceChildren(...EFFORTS.map(([value, label]) => option(value, label)));
  const account = el("select");
  account.name = "agent-account";
  const accountField = field("Account", account);
  const folderSelect = el("select");
  folderSelect.name = "agent-folder";
  folderSelect.setAttribute("aria-label", "Folder");
  const folderBox = el("div", "folder-ask");
  folderBox.hidden = true;
  const folders = mountFolderPicker({ select: folderSelect, box: folderBox, prefix: "agent-fold" }, send);
  const auto = el("input");
  auto.type = "checkbox";
  auto.name = "agent-auto";
  const autoLabel = el("label", "check");
  autoLabel.append(auto, document.createTextNode(" Auto-approve in its folder: every run of it starts with it on"));
  const skillFind = el("input", "skill-find");
  skillFind.type = "search";
  skillFind.placeholder = "Find a skill";
  skillFind.setAttribute("aria-label", "Find a skill");
  const skillNote = el("p", "muted skills-note");
  const skillList = el("div", "agent-skills");
  const tasksBox = el("div", "agent-tasks");
  let tasks = null; // its Tasks (workflows.js), mounted for each agent the panel shows
  const save = el("button", "primary save-agent", "Save");
  save.type = "button";
  const note = el("p", "muted agent-note");
  note.setAttribute("role", "status");
  const remove = el("button", "danger delete-agent", "Delete agent");
  remove.type = "button";
  const buttons = el("div", "row agent-buttons");
  buttons.append(save, remove, note); // kept in view at the panel's foot (mission.css)
  body.append(field("Name", name), field("What it works on", about),
              field("Instruction", instruction, "Its standing instruction: it goes into the agent's system prompt."),
              field("Browser profile", profile), field("Web", web), field("Model", model),
              field("Effort", effort, "More effort: it thinks longer, and uses more of your plan."), accountField,
              field("Folder", folderSelect), folderBox, autoLabel, el("h3", "", "Skills"), skillNote, skillFind,
              skillList, el("h3", "", "Tasks"), tasksBox, buttons);

  function profileName(folder) { // the card's words; the picker's option stays "Settings' choice"
    if (!folder) return "as in Settings";
    return profiles.find((row) => row.folder === folder)?.name || folder;
  }

  function fillProfiles(chosen) {
    profile.replaceChildren(option("", "Settings' choice"), ...profiles.map((row) => option(row.folder,
      `${row.name} · ${row.ready ? "ready" : "open it once"}`)));
    if (chosen && !profiles.some((row) => row.folder === chosen)) profile.append(option(chosen, chosen));
    profile.value = chosen || "";
  }

  function fillAccounts(chosen) {
    const rows = accounts();
    account.replaceChildren(option("", "The default account"), ...rows.map((row) => option(row.id, row.name)));
    if (chosen && !rows.some((row) => row.id === chosen)) account.append(option(chosen, chosen)); // kept: Save asks
    account.value = chosen || "";
    accountField.hidden = rows.length < 2 && !chosen;
  }

  function renderSkills() { // the ticked ones first, then what the search finds (there may be hundreds)
    const query = skillFind.value.trim().toLowerCase();
    const ticked = (skill) => use.has(skill.ref) || load.has(skill.ref);
    const shown = skills.filter((skill) => ticked(skill) || !query
      || `${skill.ref} ${skill.description || ""}`.toLowerCase().includes(query))
      .sort((one, two) => Number(ticked(two)) - Number(ticked(one))).slice(0, 200);
    skillList.replaceChildren(...shown.map((skill) => {
      const row = el("div", "agent-skill");
      row.dataset.ref = skill.ref;
      const canUse = el("input", "can-use");
      canUse.type = "checkbox";
      canUse.checked = use.has(skill.ref);
      canUse.setAttribute("aria-label", `Can use ${skill.ref}`);
      const atStart = el("input", "load-at-start");
      atStart.type = "checkbox";
      atStart.checked = load.has(skill.ref);
      atStart.setAttribute("aria-label", `Load ${skill.ref} at start`);
      canUse.addEventListener("change", () => {
        if (canUse.checked) use.add(skill.ref);
        else {
          use.delete(skill.ref);
          load.delete(skill.ref); // Load at start implies Can use
        }
        renderSkills();
      });
      atStart.addEventListener("change", () => {
        if (atStart.checked) {
          load.add(skill.ref);
          if (use.size) use.add(skill.ref); // with a list to keep to, what it loads is on it
        } else load.delete(skill.ref);
        renderSkills();
      });
      const one = el("label", "check");
      one.append(canUse, document.createTextNode(" Can use"));
      const two = el("label", "check");
      two.append(atStart, document.createTextNode(" Load at start"));
      row.title = skill.description || skill.ref;
      row.append(el("span", "ref", skill.ref), one, two);
      return row;
    }));
    if (!shown.length) skillList.append(el("p", "muted", skills.length ? "No skill matches." : "No skills."));
    skillNote.textContent = use.size ? `Can use ${use.size} skill${use.size === 1 ? "" : "s"} only.`
      : "Can use every skill: tick some to keep it to those.";
  }

  function renderTasks() { // its own templates: Add task, Edit, Run, Remove; a new agent has none until it is saved
    tasks = null;
    if (!editing) {
      tasksBox.replaceChildren(el("p", "muted", "Save the agent first, then add its tasks."));
      return;
    }
    const slug = editing;
    tasks = mountWorkflows(tasksBox, link, { skills: () => skills, sites: () => sites, servers: () => servers,
                                             heading: "Add task", filter: (task) => task.runs_as === slug,
                                             runsAs: slug, removeLabel: "Remove" });
    tasks.onMessage({ ...snapshot, type: "workflows_snapshot" });
  }

  function showAgent(slug, from = null) { // its settings: a saved agent's, or a new one's (from: its first values)
    const row = saved.find((one) => one.slug === slug) || { ...EMPTY, ...(from || {}) };
    editing = row.slug;
    title.textContent = row.slug ? row.name : "New agent";
    remove.hidden = !row.slug; // a new agent has nothing to delete yet
    name.value = row.name;
    about.value = row.description;
    instruction.value = row.instruction;
    fillProfiles(row.profile);
    web.value = row.web;
    model.value = row.model;
    effort.value = row.effort || "default";
    fillAccounts(row.account);
    folders.set(row.folder);
    auto.checked = row.auto === true;
    use.clear();
    load.clear();
    for (const ref of row.use) use.add(ref);
    for (const ref of row.load) load.add(ref);
    skillFind.value = "";
    note.textContent = "";
    pending = null;
    renderSkills();
    renderTasks();
    panel.hidden = false;
    name.focus();
  }

  function shut() {
    panel.hidden = true;
    editing = null;
    tasks = null;
  }

  function nextRun(slug) { // its next scheduled task: "Next: Morning prices · Mon 09:00"
    let soonest = null;
    for (const row of snapshot.next_runs || []) {
      if (row.runs_as !== slug || !row.runs?.length) continue;
      if (!soonest || row.runs[0] < soonest.at) soonest = { name: row.name, at: row.runs[0] };
    }
    return soonest ? `Next: ${soonest.name} · ${when(soonest.at)}` : "No scheduled task";
  }

  function renderCards() {
    const runs = [...agents().values()];
    cards.replaceChildren(...saved.map((row) => {
      const card = el("button", "agent-card card");
      card.type = "button";
      card.dataset.slug = row.slug;
      const top = el("span", "top-line");
      top.append(el("strong", "name", row.name));
      if (runs.some((run) => run.saved === row.slug && GOING.includes(run.state))) {
        top.append(el("span", "chip working", "Working"));
      }
      card.append(top, el("span", "about muted", row.description || ""),
                  el("span", "profile muted", `Brave: ${profileName(row.profile)}`),
                  el("span", "next muted", nextRun(row.slug)),
                  profileDot(row.profile)); // Ready, Open it once, or Brave not connected
      card.addEventListener("click", () => showAgent(row.slug));
      return card;
    }));
    if (!saved.length) cards.append(el("p", "empty", "No agents yet: New agent sets one up."));
  }

  save.addEventListener("click", () => {
    if (editing === null) return;
    const why = folders.ready(); // "Trust this folder?" first
    if (why) {
      note.textContent = why;
      return;
    }
    saves += 1;
    pending = `sa-${saves}`;
    const sent = send({ type: "saved_agent_save", request: pending, ...(editing ? { slug: editing } : {}),
                        name: name.value, description: about.value, instruction: instruction.value,
                        profile: profile.value || null, web: web.value, model: model.value,
                        effort: effort.value, account: account.value || null, folder: folders.value(),
                        auto_approve: auto.checked,
                        can_use: [...use], load_at_start: [...load] });
    note.textContent = sent ? "Saving…" : "Not connected: is `ai-browser app` running?";
  });
  remove.addEventListener("click", async () => { // Delete agent: asked first, Keep by default
    const row = saved.find((one) => one.slug === editing);
    if (!row) return;
    const own = (snapshot.workflows || []).filter((task) => task.runs_as === row.slug);
    const count = `${own.length} task${own.length === 1 ? "" : "s"}`;
    const lines = [`Its settings, its instruction and its ${count} are deleted${own.length ? `: ${own.map((task) =>
      task.name).join(", ")}` : ""}.`, "Its runs and their files stay."];
    const run = [...agents().values()].find((one) => one.saved === row.slug && GOING.includes(stateOf(one)));
    if (run) lines.push(`${agentLabel(run)} is working: it keeps going, as a one-off run.`);
    if (!await confirmAction({ title: `Delete ${row.name}?`, lines, yes: "Delete" })) return;
    saves += 1;
    if (!send({ type: "saved_agent_delete", slug: row.slug, request: `sd-${saves}` })) {
      note.textContent = "Not connected: is `ai-browser app` running?";
    }
  });
  close.addEventListener("click", shut);
  newAgent.addEventListener("click", () => showAgent(""));
  skillFind.addEventListener("input", renderSkills);
  panel.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      shut();
    }
  });

  return {
    showAgent,
    showTemplate(slug) { // the Calendar's click: its agent's settings, or the template among Tasks for any agent
      const task = (snapshot.workflows || []).find((one) => one.slug === slug);
      if (task?.runs_as && saved.some((row) => row.slug === task.runs_as)) {
        showAgent(task.runs_as);
        return;
      }
      const row = anyBox.querySelector(`.workflow[data-slug="${CSS.escape(slug)}"]`);
      row?.scrollIntoView({ block: "center" });
      row?.classList.add("focus");
      setTimeout(() => row?.classList.remove("focus"), 2000);
    },
    shown(page) { // the panel belongs to this page: hidden on the others, as it was when the user comes back
      panel.hidden = page !== "agents" || editing === null;
      if (page !== "agents") return;
      for (const kind of ["saved_agents", "workflows", "skills"]) send({ type: kind });
      send({ type: "tools", account: "default" }); // the servers a task may use
    },
    agents() { // a run started, changed or closed: the cards' Working
      renderCards();
    },
    onMessage(message) {
      anyTasks.onMessage(message);
      tasks?.onMessage(message);
      folders.onMessage(message);
      switch (message.type) {
        case "snapshot":
          send({ type: "saved_agents" });
          break;
        case "saved_agents":
          saved = Array.isArray(message.agents) ? message.agents : [];
          profiles = Array.isArray(message.profiles) ? message.profiles : [];
          renderCards();
          anyTasks.options(); // Runs as lists them
          if (editing && !saved.some((row) => row.slug === editing)) shut(); // deleted meanwhile
          break;
        case "saved_agent_saved":
          if (message.request !== pending) break;
          pending = null;
          note.textContent = "Saved.";
          if (editing !== message.slug) { // a new agent: its file is made, and it may have tasks now
            editing = message.slug;
            renderTasks();
          }
          title.textContent = name.value.trim() || title.textContent;
          break;
        case "workflows_snapshot":
          snapshot = message;
          renderCards();
          break;
        case "skills":
          skills = message.skills || [];
          renderSkills();
          anyTasks.options();
          tasks?.options();
          break;
        case "brain_snapshot":
        case "brain_state":
          sites = message.watch_list || [];
          anyTasks.options();
          tasks?.options();
          break;
        case "tools_snapshot":
          if ((message.account || "default") !== "default") break;
          servers = (message.servers || []).filter((server) => server.enabled);
          anyTasks.options();
          tasks?.options();
          break;
        case "error":
          if (pending && message.request === pending) {
            pending = null;
            note.textContent = String(message.text || ""); // the app's refusal words
          } else if (String(message.request || "").startsWith("sd-") && !panel.hidden) {
            note.textContent = String(message.text || ""); // a Delete the app refused
          }
          break;
      }
    },
  };
}
