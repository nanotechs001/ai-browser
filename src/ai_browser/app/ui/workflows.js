// Templates (tasks): the user's own recipes, each a file in ~/.ai-browser/workflows, on the Agents page: Tasks for any
// agent, and each saved agent's own Tasks. Run one by hand (with extra words if you like), edit it, or delete it; the
// form writes the file and says where. Triggers: by hand, a message (a site from the Brain's watch list, and when it
// applies), or a schedule. Runs as: a new agent, or one of the saved agents (its settings, one run at a time).
import { el } from "./chat.js";

const TRIGGERS = { manual: "By hand", message: "When a message comes", schedule: "On a schedule" };

function field(label, control) {
  const wrap = el("label", "field");
  wrap.append(el("span", "muted", label), control);
  return wrap;
}

function input(name, placeholder = "") {
  const node = el("input");
  node.name = name;
  node.placeholder = placeholder;
  return node;
}

function select(name, options) {
  const node = el("select");
  node.name = name;
  for (const [value, label] of options) {
    const option = el("option", "", label);
    option.value = value;
    node.append(option);
  }
  return node;
}

// filter(workflow): which templates this list shows; runsAs: the saved agent every save from here runs as (its own
// Tasks), or null for a Runs as picker of agents() (the saved agents: {slug, name}); removeLabel: the delete button's
export function mountWorkflows(root, link, { skills = () => [], sites = () => [], servers = () => [],
                                              heading = "New workflow", filter = () => true, runsAs = null,
                                              agents = () => [], removeLabel = "Delete" } = {}) {
  const list = el("div", "list workflows-list");
  const problems = el("div", "problems muted");
  const form = el("div", "workflow-form card");
  root.replaceChildren(list, problems, el("h3", "", heading), form);
  let editing = null; // the slug being edited
  let pending = null; // the request waiting for its answer
  let last = {}; // the latest workflows snapshot
  const running = new Map(); // slug -> its Run request, until the agent has started
  const name = input("name", "Name, for example: Footer fix");
  const instructions = el("textarea");
  instructions.name = "instructions";
  instructions.rows = 4;
  instructions.placeholder = "What the agent should do, in your words. For example: open the site in AI Browser, make "
    + "the change the task asks for, then post what you did in #web-team";
  const trigger = select("trigger", Object.entries(TRIGGERS));
  const site = select("site", []);
  const when = input("when", "When it applies, for example: an Asana task tagged website");
  const run = select("run", [["ask", "Ask me first"], ["auto", "Run right away"]]);
  const schedule = input("schedule", "daily 09:00, weekdays 09:00, mon 08:30 or every 2h");
  const model = select("model", [["sonnet", "Sonnet"], ["opus", "Opus"], ["haiku", "Haiku"]]);
  const runsAsPick = select("runs_as", []); // a new agent, or a saved one: then its settings, not this form's
  const tools = el("div", "checks tools");
  const skillChecks = el("div", "skill-picker"); // the chosen skills, and a search for more (there may be hundreds)
  const chosenBox = el("div", "chosen");
  const skillFind = el("input", "skill-find");
  skillFind.placeholder = "Find a skill to add";
  const matches = el("div", "matches");
  skillChecks.append(chosenBox, skillFind, matches);
  const chosenSkills = new Set(); // skill refs (namespace:name): a name alone could match two skills
  const message = el("div", "message-fields");
  message.append(field("Site", site), field("When", when), field("Then", run));
  const timing = el("div", "schedule-fields");
  timing.append(field("Schedule", schedule));
  const save = el("button", "save primary", "Save");
  const cancel = el("button", "cancel ghost", "Cancel");
  const saved = el("span", "saved muted");
  const buttons = el("div", "row");
  buttons.append(save, cancel, saved);
  form.append(field("Name", name), field("Instructions", instructions), field("Trigger", trigger), message, timing,
              ...(runsAs === null ? [field("Runs as", runsAsPick)] : []),
              field("Model", model), el("span", "muted", "Tools it may use (it still asks before each)"), tools,
              el("span", "muted", "Skills its agent loads first"), skillChecks, buttons);

  function ran(request) { // a Run was answered (or waited long enough): its button works again
    for (const [slug, waiting] of running) {
      if (waiting === request) {
        running.delete(slug);
        render(last);
      }
    }
  }

  function send(payload) {
    const sent = link.send(payload);
    if (!sent) saved.textContent = "Not connected: is ai-browser app running?";
    return sent;
  }

  function showFields() {
    message.hidden = trigger.value !== "message";
    timing.hidden = trigger.value !== "schedule";
  }

  function checks(container, values, picked) {
    const chosen = new Set(picked ?? [...container.querySelectorAll("input:checked")].map((box) => box.value));
    container.replaceChildren();
    for (const [value, label] of values) {
      const option = el("label", "check");
      const box = el("input");
      box.type = "checkbox";
      box.value = value;
      box.checked = chosen.has(value);
      option.append(box, el("span", "", label));
      container.append(option);
    }
    if (!values.length) container.append(el("span", "muted", "none"));
  }

  function renderSkills() {
    chosenBox.replaceChildren();
    for (const ref of chosenSkills) {
      const chip = el("button", "chip chosen-skill", `${ref.split(":").pop()} ×`);
      chip.title = `${ref}: click to remove`;
      chip.addEventListener("click", () => {
        chosenSkills.delete(ref);
        renderSkills();
      });
      chosenBox.append(chip);
    }
    if (!chosenSkills.size) chosenBox.append(el("span", "muted", "None yet"));
    const query = skillFind.value.trim().toLowerCase();
    matches.replaceChildren();
    if (!query) return;
    const found = skills().filter((skill) => !chosenSkills.has(skill.ref) && (skill.name.toLowerCase().includes(query)
      || (skill.description || "").toLowerCase().includes(query))).slice(0, 8);
    for (const skill of found) {
      const add = el("button", "ghost add-skill", `+ ${skill.name}`);
      add.title = skill.description || skill.ref;
      add.addEventListener("click", () => {
        chosenSkills.add(skill.ref);
        skillFind.value = "";
        renderSkills();
      });
      matches.append(add, el("span", "chip", skill.source || ""));
    }
    if (!found.length) matches.append(el("span", "muted", "No skill matches"));
  }

  function fillRunsAs(picked) {
    const kept = picked ?? runsAsPick.value;
    runsAsPick.replaceChildren(...[["", "A new agent"], ...agents().map((agent) => [agent.slug, agent.name])]
      .map(([value, label]) => {
        const option = el("option", "", label);
        option.value = value;
        return option;
      }));
    runsAsPick.value = [...runsAsPick.options].some((option) => option.value === kept) ? kept : "";
  }

  function options(picked = {}) {
    fillRunsAs(picked.runs_as);
    const current = site.value;
    site.replaceChildren();
    for (const entry of sites()) {
      const option = el("option", "", entry.label);
      option.value = entry.site;
      site.append(option);
    }
    site.value = picked.site ?? current;
    checks(tools, servers().map((server) => [server.name, server.label || server.name]), picked.tools);
    if (picked.skills) {
      chosenSkills.clear();
      for (const ref of picked.skills) chosenSkills.add(ref);
    }
    renderSkills();
  }

  function reset() {
    editing = null;
    name.value = instructions.value = when.value = schedule.value = "";
    trigger.value = "manual";
    run.value = "ask";
    model.value = "sonnet";
    options({ tools: [], skills: [], runs_as: "" });
    showFields();
  }

  function edit(workflow) {
    editing = workflow.slug;
    name.value = workflow.name;
    instructions.value = workflow.instructions;
    trigger.value = workflow.trigger;
    when.value = workflow.when || "";
    schedule.value = workflow.schedule || "";
    run.value = workflow.run || "ask";
    model.value = workflow.model || "sonnet";
    options({ site: workflow.site, tools: workflow.tools, skills: workflow.skills, runs_as: workflow.runs_as || "" });
    showFields();
    saved.textContent = `Editing ${workflow.path}`;
    name.focus();
  }

  function summary(workflow) {
    if (workflow.trigger === "message") return `${workflow.run === "auto" ? "Runs" : "Offered"} when: ${workflow.when}`;
    if (workflow.trigger === "schedule") return `On a schedule: ${workflow.schedule}`;
    return "By hand: press Run";
  }

  function render(snapshot) {
    last = snapshot;
    list.replaceChildren();
    const shown = (snapshot.workflows || []).filter(filter);
    for (const workflow of shown) {
      const row = el("div", "workflow card");
      row.dataset.slug = workflow.slug;
      const extra = el("input", "run-text");
      extra.placeholder = "Extra words (optional)";
      const runButton = el("button", "run primary", "Run");
      runButton.disabled = running.has(workflow.slug);
      runButton.addEventListener("click", () => {
        if (runButton.disabled) return;
        const request = `w${Date.now()}`;
        if (send({ type: "workflow_run", slug: workflow.slug, text: extra.value.trim(), request })) {
          extra.value = "";
          runButton.disabled = true; // one click, one run: until its agent starts (or 15 s)
          running.set(workflow.slug, request);
          setTimeout(() => ran(request), 15000);
        }
      });
      const editButton = el("button", "edit", "Edit");
      editButton.addEventListener("click", () => edit(workflow));
      const remove = el("button", "delete ghost", removeLabel);
      remove.addEventListener("click", () => { // a second click: it deletes the user's file
        if (remove.dataset.sure) send({ type: "workflow_delete", slug: workflow.slug });
        else {
          remove.dataset.sure = "1";
          remove.textContent = "Delete the file?";
        }
      });
      const buttons = el("div", "row");
      buttons.append(extra, runButton, editButton, remove);
      row.append(el("strong", "", workflow.name), el("div", "muted", summary(workflow)));
      if (workflow.note) row.append(el("div", "muted note", workflow.note));
      row.append(buttons);
      list.append(row);
    }
    if (!shown.length) list.append(el("p", "empty", "No tasks yet: write one below."));
    problems.replaceChildren(...(snapshot.problems || []).map((problem) => el("div", "", `Can't read ${problem}`)));
  }

  trigger.addEventListener("change", showFields);
  cancel.addEventListener("click", () => {
    reset();
    saved.textContent = "";
  });
  save.addEventListener("click", () => {
    pending = `s${Date.now()}`;
    const picked = (container) => [...container.querySelectorAll("input:checked")].map((box) => box.value);
    send({ type: "workflow_save", request: pending, ...(editing ? { slug: editing } : {}), name: name.value,
           instructions: instructions.value, trigger: trigger.value, site: site.value, when: when.value,
           schedule: schedule.value, run: run.value, model: model.value, tools: picked(tools),
           skills: [...chosenSkills], runs_as: runsAs ?? runsAsPick.value });
  });
  skillFind.addEventListener("input", renderSkills);
  reset();

  return {
    refresh() {
      link.send({ type: "workflows" });
    },
    options() {
      options();
    },
    onMessage(message) {
      if ((message.type === "created" || message.type === "error") && message.request) ran(message.request);
      if (message.type === "workflows_snapshot") render(message);
      else if (message.type === "workflow_saved" && message.request === pending) {
        reset();
        saved.textContent = `Saved to ${message.path}`;
      } else if (message.type === "error" && message.request && message.request === pending) {
        saved.textContent = message.text;
      }
    },
  };
}
