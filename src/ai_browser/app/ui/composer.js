// Mission Control's composer (the new look, Decision 9): Ask AI (the Brain: it answers and proposes, and nothing runs
// without the user's Start, Send or a plain yes), Build a Mission (start an agent) and Use a Template (run a workflow,
// with the box as its extra words). Under the box: Attach (uploads.js), Web ▾, Model ▾, Account ▾, Folder ▾ (agent
// powers' picker), Template ▾ and Workspace ▾, the mic, and the main button. Enter or Command-Enter (Ctrl+Enter) presses it;
// Shift+Enter makes a new line. Narrow windows fold the pickers into ⋯ Options. Every word is set as text.
"use strict";

import { fillPicker, pickDefault } from "./accountui.js";
import { el } from "./chat.js";
import { mountFolderPicker } from "./folderpick.js";
import { mountUploads } from "./uploads.js";

const MAC = /mac/i.test(navigator.userAgentData?.platform || navigator.platform || "");
const MODES = {
  ask: { label: "Ask", placeholder: "Ask anything about your agents, your messages or what to do next…" },
  build: { label: "Start Mission", placeholder: "Describe what you want to accomplish…" },
  template: { label: "Run Template", placeholder: "Anything to add for this template (optional)" },
};
const WAIT = 10000; // ms a press waits for "created" before the button works again
const NOT_CONNECTED = "Not connected: is `ai-browser app` running?";

export function mountComposer({ link, workspaceOf = () => null }) {
  const $ = (id) => document.getElementById(id);
  const send = (message) => link.send(message);
  let mode = "build";
  let pending = null; // the request waiting for its "created": one press, one agent
  let timer = null;
  let rows = []; // the accounts
  let templates = []; // the workflows, as Templates lists them
  let workspaces = [];
  let workspacePicked = false; // the user chose one here: the menu's filter no longer sets it
  const folders = mountFolderPicker({ select: $("task-folder"), box: $("folder-ask") }, send);
  const uploads = mountUploads({ list: $("attached"), send, note });

  function note(text) {
    $("task-note").textContent = text;
    clearTimeout(note.timer);
    note.timer = setTimeout(() => { $("task-note").textContent = ""; }, 6000);
  }

  function setMode(next) {
    mode = MODES[next] ? next : "build";
    for (const tab of document.querySelectorAll(".modes [data-mode]")) {
      tab.setAttribute("aria-selected", String(tab.dataset.mode === mode));
    }
    $("composer").dataset.mode = mode;
    $("start-label").textContent = MODES[mode].label;
    $("task").placeholder = MODES[mode].placeholder;
    const build = mode === "build";
    for (const id of ["task-web", "task-model", "task-folder", "attach"]) $(id).hidden = !build;
    $("task-account").hidden = !build || rows.length < 2;
    $("task-template").hidden = mode !== "template";
    $("task-workspace").hidden = mode === "ask";
    $("attached").hidden = !build || uploads.count() === 0;
  }

  function finish() {
    pending = null;
    clearTimeout(timer);
    $("start").disabled = false;
  }

  function begin(message) { // one press, one request: the button waits for its answer
    pending = `m${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
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
    if (mode === "template") {
      if (!$("task-template").value) {
        note("Pick a template, or write one in Templates");
        return;
      }
      begin({ type: "workflow_run", slug: $("task-template").value, text, ...workspace() });
      return;
    }
    if (!text) {
      note("Write what the agent should do");
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
    begin({ type: "new_task", text, skills: [], model: $("task-model").value, web: $("task-web").value, ...account,
            ...(folder ? { folder } : {}), ...(files.length ? { attachments: files } : {}), ...workspace() });
  }

  function option(value, label) {
    const node = el("option", "", label);
    node.value = value;
    return node;
  }

  function fillTemplates() { // rebuilt only when the list changes, so a pick stays
    const select = $("task-template");
    const signature = JSON.stringify(templates.map((row) => [row.slug, row.name]));
    if (select.dataset.rows === signature) return;
    const kept = select.value;
    select.replaceChildren(option("", templates.length ? "Pick a template" : "No templates yet"),
                           ...templates.map((row) => option(row.slug, row.name)));
    select.value = templates.some((row) => row.slug === kept) ? kept : "";
    select.dataset.rows = signature;
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
  $("start-key").textContent = MAC ? "⌘ ↵" : "Ctrl ↵";
  setMode("build");

  return {
    note,
    focus() { // Command-K (Ctrl+K) and New Mission: Build a Mission, the cursor in the box
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
    onMessage(message) {
      folders.onMessage(message);
      uploads.onMessage(message);
      switch (message.type) {
        case "snapshot":
          rows = message.accounts || [];
          fillPicker($("task-account"), rows);
          workspaces = message.workspaces || [];
          fillWorkspaces();
          setMode(mode);
          if (pending) finish(); // a new connection: an unanswered press can be pressed again
          send({ type: "workflows" }); // Use a Template's list
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
        case "workflows_snapshot":
          templates = message.workflows || [];
          fillTemplates();
          break;
        case "created":
          if (pending && message.request === pending) {
            finish();
            $("task").value = "";
            uploads.clear(); // the app moved them into the agent's folder
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
