// Mission Control's composer (the new look, Decision 9): Ask AI (the Brain: it answers and proposes, and nothing runs
// without the user's Start, Send or a plain yes) and Build a Mission (start an agent). Agent ▾ picks a new agent (Name
// and What it works on) or a saved one: then its own settings apply, and while its run works the task goes to that
// run (the saved-agents spec, 2). Templates are the Agents page's. Under the box: Attach (uploads.js),
// Web ▾, Model ▾ (Model and Effort, behind one face), Account ▾, Folder ▾ (agent powers' picker), Auto-approve in
// its folder (a switch, off again for each new task), Skills (loaded at start; Knowledge's Use in new mission ticks
// one) and Workspace ▾, the mic, and the main button. Enter or Command-Enter (Ctrl+Enter) presses it; Shift+Enter
// makes a new line. A picture pasted into the box, or a file dropped on it (paste.js), is attached as Attach does in
// Build a Mission; Ask AI takes none, and says where pictures go. Narrow windows fold the pickers into ⋯ Options.
// Every word is set as text.
"use strict";

import { fillPicker, pickDefault } from "./accountui.js";
import { autoTitle, el } from "./chat.js";
import { mountFolderPicker } from "./folderpick.js";
import { PICTURES_NOTE, takeFiles } from "./paste.js";
import { stateOf } from "./step.js";
import { mountUploads } from "./uploads.js";

const MAC = /mac/i.test(navigator.userAgentData?.platform || navigator.platform || "");
const MODES = {
  ask: { label: "Ask", placeholder: "Ask anything about your agents, your messages or what to do next…" },
  build: { label: "Start Mission", placeholder: "Describe what you want to accomplish…" },
};
const WAIT = 10000; // ms a press waits for "created" before the button works again
const NOT_CONNECTED = "Not connected: is `ai-browser app` running?";
const GOING = ["working", "waiting", "needs_you"]; // a saved agent's run still going: Start sends to it

export function mountComposer({ link, workspaceOf = () => null }) {
  const $ = (id) => document.getElementById(id);
  const send = (message) => link.send(message);
  let mode = "build";
  let pending = null; // the request waiting for its "created": one press, one agent
  let taking = []; // the upload ids sent with a pending new_task: only those chips go when it is created
  let timer = null;
  let rows = []; // the accounts
  let workspaces = [];
  let workspacePicked = false; // the user chose one here: the menu's filter no longer sets it
  let handing = null; // one of the user's tabs the next Start begins in (the Tabs page's Hand over → New agent…)
  let skillRows = []; // the skills, as Knowledge lists them
  let savedAgents = []; // the saved agents, for Agent ▾
  let runs = new Map(); // the runs, as mission.js keeps them: whether a saved agent's run works
  const picked = new Set(); // Skills: the refs the next run loads at start
  const folders = mountFolderPicker({ select: $("task-folder"), box: $("folder-ask") }, send);
  const uploads = mountUploads({ list: $("attached"), send, note });

  function savedPicked() { // the saved agent Agent ▾ picked in Build a Mission, if any
    return mode === "build" ? savedAgents.find((row) => row.slug === $("task-agent").value) || null : null;
  }

  function hint() { // the line under the box while a saved agent is picked: what applies instead of the pickers
    const row = savedPicked();
    return row ? `Uses ${row.name}'s own settings` : "";
  }

  function note(text) { // a passing word; then the line goes back to the hint
    $("task-note").textContent = text;
    clearTimeout(note.timer);
    note.timer = setTimeout(() => {
      note.timer = null;
      $("task-note").textContent = hint();
    }, 6000);
  }

  function setMode(next) {
    mode = MODES[next] ? next : "build";
    for (const tab of document.querySelectorAll(".modes [data-mode]")) {
      tab.setAttribute("aria-selected", String(tab.dataset.mode === mode));
    }
    $("composer").dataset.mode = mode;
    const row = savedPicked(); // its run works: the task is a message to it
    const going = row && [...runs.values()].some((run) => run.saved === row.slug && GOING.includes(stateOf(run)));
    $("start-label").textContent = going ? `Send to ${row.name}` : MODES[mode].label;
    if (!note.timer) $("task-note").textContent = hint();
    $("task").placeholder = MODES[mode].placeholder;
    const build = mode === "build";
    const own = build && $("task-agent").value === ""; // a new agent: the pickers are its settings
    for (const id of ["task-web", "task-think", "task-model", "task-effort", "task-folder", "task-auto-switch",
                      "task-skills", "mission-words"]) {
      $(id).hidden = !own;
    }
    $("attach").hidden = !build;
    // Agent ▾ (in the modes' row, beside Name) only once there is a saved agent to pick: alone, "New agent" is no
    // choice
    $("task-agent").hidden = !build || savedAgents.length === 0;
    $("task-account").hidden = !own || rows.length < 2;
    $("task-workspace").hidden = mode === "ask";
    $("attached").hidden = !build || uploads.count() === 0;
  }

  function thinkFace() { // Model ▾'s face: "Sonnet · balanced", or "Sonnet · Low effort" unless Default
    const model = $("task-model").selectedOptions[0]?.textContent || "";
    const effort = $("task-effort").selectedOptions[0];
    const face = $("task-think").querySelector("summary");
    face.textContent = $("task-effort").value === "default" ? model
      : `${model.split(" · ")[0]} · ${effort.textContent} effort`;
    face.title = `Model and effort: ${face.textContent}`; // the whole face, when a long one is cut short
  }

  function renderSkills() { // the picked ones first, then what the search finds (there may be hundreds)
    const query = $("skills-find").value.trim().toLowerCase();
    const shown = skillRows.filter((skill) => picked.has(skill.ref) || !query
      || `${skill.ref} ${skill.description || ""}`.toLowerCase().includes(query))
      .sort((one, two) => Number(picked.has(two.ref)) - Number(picked.has(one.ref))).slice(0, 200);
    $("skills-pick").replaceChildren(...shown.map((skill) => {
      const label = el("label", "check");
      const box = el("input");
      box.type = "checkbox";
      box.value = skill.ref;
      box.checked = picked.has(skill.ref);
      box.addEventListener("change", () => {
        if (box.checked) picked.add(skill.ref);
        else picked.delete(skill.ref);
        $("skills-count").textContent = picked.size ? `(${picked.size})` : "";
      });
      label.title = skill.description || skill.ref;
      label.append(box, el("span", "", skill.ref));
      return label;
    }));
    if (!shown.length) $("skills-pick").append(el("p", "muted", skillRows.length ? "No skill matches." : "No skills."));
    $("skills-count").textContent = picked.size ? `(${picked.size})` : "";
  }

  function setHanding(tab) {
    handing = tab || null;
    $("handing").hidden = !handing;
    $("handing-text").textContent = handing ? `Starts in your tab: ${handing.title || handing.url}` : "";
  }

  function finish() {
    pending = null;
    taking = [];
    clearTimeout(timer);
    $("start").disabled = false;
  }

  function begin(message) { // one press, one request: the button waits for its answer
    pending = `m${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
    taking = message.attachments || [];
    $("start").disabled = true;
    if (!send({ ...message, request: pending })) {
      finish();
      note(NOT_CONNECTED);
      return;
    }
    timer = setTimeout(finish, WAIT);
  }

  function workspace() {
    return $("task-workspace").value ? { workspace: $("task-workspace").value } : {};
  }

  function run() {
    const text = $("task").value.trim();
    if (mode === "ask") { // the Brain's talk (talk.js): its answer, and any card, show above the box
      if (!text) {
        note("Write what you want to ask");
        return;
      }
      $("talk-text").value = text;
      $("talk-form").requestSubmit();
      $("task").value = "";
      return;
    }
    if (pending) return;
    if (!text) {
      note("Write what the agent should do");
      return;
    }
    const agent = $("task-agent").value;
    if (agent) { // a saved agent: its own settings, Auto-approve too; while its run works, a message to it
      const why = uploads.why();
      if (why) {
        note(why);
        return;
      }
      const files = uploads.ids();
      begin({ type: "new_task", agent, text, ...(files.length ? { attachments: files } : {}), ...workspace(),
              ...(handing ? { adopt: handing.target } : {}) });
      return;
    }
    const why = folders.ready() || uploads.why();
    if (why) {
      note(why);
      return;
    }
    const folder = folders.value();
    const files = uploads.ids();
    const account = $("task-account").hidden ? {} : { account: $("task-account").value };
    const auto = $("task-auto").checked ? { auto: true } : {}; // the user's own tick, never a default
    const name = $("task-name").value.trim(); // Name and What it works on: shown as text, never the agent's instruction
    const description = $("task-about").value.trim();
    begin({ type: "new_task", text, skills: [...picked], model: $("task-model").value, web: $("task-web").value,
            effort: $("task-effort").value,
            ...account,
            ...(name ? { name } : {}), ...(description ? { description } : {}),
            ...(folder ? { folder } : {}), ...(files.length ? { attachments: files } : {}), ...auto, ...workspace(),
            ...(handing ? { adopt: handing.target } : {}) });
  }

  function option(value, label) {
    const node = el("option", "", label);
    node.value = value;
    return node;
  }

  function fillAgents() { // Agent ▾: New agent, then each saved agent by name (kept while it is still there)
    const select = $("task-agent");
    const signature = JSON.stringify(savedAgents.map((row) => [row.slug, row.name]));
    if (select.dataset.rows === signature) return;
    const kept = select.value;
    select.replaceChildren(option("", "New agent"), ...savedAgents.map((row) => option(row.slug, row.name)));
    select.value = savedAgents.some((row) => row.slug === kept) ? kept : "";
    select.dataset.rows = signature;
    setMode(mode);
  }

  function fillWorkspaces() {
    const select = $("task-workspace");
    const signature = JSON.stringify(workspaces.map((row) => [row.id, row.name]));
    if (select.dataset.rows !== signature) {
      const kept = select.value;
      select.replaceChildren(option("", "No workspace"), ...workspaces.map((row) => option(row.id, row.name)));
      select.value = workspaces.some((row) => row.id === kept) ? kept : "";
      select.dataset.rows = signature;
    }
    if (!workspacePicked) {
      const filter = workspaceOf();
      select.value = workspaces.some((row) => row.id === filter) ? filter : "";
    }
  }

  for (const tab of document.querySelectorAll(".modes [data-mode]")) {
    tab.addEventListener("click", () => setMode(tab.dataset.mode));
  }
  $("start").addEventListener("click", run);
  $("task").addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.altKey || event.isComposing) return;
    event.preventDefault(); // Enter, or Command-Enter (Ctrl+Enter): the main button
    run();
  });
  $("attach").addEventListener("click", () => $("attach-files").click());
  takeFiles($("task"), (pasted) => { // a picture pasted or a file dropped: Build a Mission's, as Attach
    if (mode === "build") uploads.add(pasted);
    else note(PICTURES_NOTE); // Ask AI takes none, and nothing switches by itself
  }, { area: $("task").closest(".box") });
  $("attach-files").addEventListener("change", () => {
    uploads.add([...$("attach-files").files]);
    $("attach-files").value = ""; // the same file can be picked again
  });
  $("options").addEventListener("click", () => {
    const open = !$("composer").classList.contains("options-open");
    $("composer").classList.toggle("options-open", open);
    $("options").setAttribute("aria-expanded", String(open));
  });
  $("task-workspace").addEventListener("change", () => {
    workspacePicked = true;
  });
  $("handing-clear").addEventListener("click", () => setHanding(null));
  $("task-agent").addEventListener("change", () => setMode(mode));
  $("skills-find").addEventListener("input", renderSkills);
  $("task-think").addEventListener("change", thinkFace);
  $("start-key").textContent = MAC ? "⌘ ↵" : "Ctrl ↵";
  $("task-auto-switch").title = autoTitle(false, false); // until the app says this computer runs commands
  setMode("build");
  thinkFace();

  return {
    note,
    thinkFace, // the model set from the app's settings

    focus() { // Command-K (Ctrl+K) and New Mission: Build a Mission, the cursor in the box
      setMode("build");
      $("task").focus();
    },
    pickSkill(ref) { // Knowledge's Use in new mission: ticked in Build a Mission's Skills, the cursor in the box
      picked.add(ref);
      renderSkills();
      setMode("build");
      $("task").focus();
    },
    startIn(tab) { // the Tabs page's Hand over → New agent…: the next Start begins in that tab of the user's
      setHanding(tab);
      setMode("build");
      $("task").focus();
    },
    fill(words) { // the mic's words outside Ask AI: into the box, for the user to start (talk.js's `fill`)
      if (mode === "ask") return false;
      $("task").value = [$("task").value.trim(), String(words || "").trim()].filter(Boolean).join(" ");
      return true;
    },
    workspaceChanged() { // the menu's filter changed: the picker follows, unless the user chose here
      fillWorkspaces();
    },
    agents(map) { // a run started, changed or closed: Start Mission, or Send to a saved agent's working run
      runs = map;
      setMode(mode);
    },
    onMessage(message) {
      folders.onMessage(message);
      uploads.onMessage(message);
      switch (message.type) {
        case "snapshot":
          $("task-auto-switch").title = autoTitle(message.auto_commands === true, message.auto_sandbox === true);
          rows = message.accounts || [];
          fillPicker($("task-account"), rows);
          workspaces = message.workspaces || [];
          fillWorkspaces();
          setMode(mode);
          uploads.lost(); // a new connection: the app dropped the files staged for the old one
          if (pending) finish(); // and an unanswered press can be pressed again
          break;
        case "accounts":
          rows = message.accounts || [];
          fillPicker($("task-account"), rows);
          setMode(mode);
          break;
        case "workspaces":
          workspaces = message.workspaces || [];
          fillWorkspaces();
          break;
        case "skills":
          skillRows = message.skills || [];
          renderSkills();
          break;
        case "saved_agents":
          savedAgents = Array.isArray(message.agents) ? message.agents : [];
          fillAgents();
          break;
        case "created":
          if (pending && message.request === pending) {
            const took = taking;
            finish();
            $("task").value = "";
            $("task-name").value = "";
            $("task-about").value = "";
            $("task-auto").checked = false; // each task is its own choice: the next one starts off
            setHanding(null);
            picked.clear(); // each run picks its own
            renderSkills();
            uploads.taken(took); // the app moved those into the agent's folder
            setMode(mode); // the chips show in Build a Mission only
            pickDefault($("task-account"), rows);
          }
          break;
        case "error":
          if (pending && message.request === pending) finish();
          if (message.text && (!message.request || String(message.request).startsWith("m"))) note(message.text);
          break;
      }
    },
  };
}
