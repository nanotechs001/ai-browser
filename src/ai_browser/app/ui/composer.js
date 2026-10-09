// Mission Control's composer (the new look, Decision 9): Ask AI (the Brain: it answers and proposes, and nothing runs
// without the user's Start, Send or a plain yes) and Build a Mission (start an agent). Templates are AI Home's own
// (Run, Edit, New): Mission Control has none since the brain-delegation spec. Under the box: Attach (uploads.js),
// Web ▾, Model ▾, Account ▾, Folder ▾ (agent powers' picker), Auto-approve in its folder (a switch, off again for each
// new task) and Workspace ▾, the mic, and the main button. Enter or Command-Enter (Ctrl+Enter) presses it; Shift+Enter
// makes a new line. A picture pasted into the box, or a file dropped on it (paste.js), is attached as Attach does in
// Build a Mission; Ask AI takes none, and says where pictures go. Narrow windows fold the pickers into ⋯ Options.
// Every word is set as text.
"use strict";

import { fillPicker, pickDefault } from "./accountui.js";
import { autoTitle, el } from "./chat.js";
import { mountFolderPicker } from "./folderpick.js";
import { PICTURES_NOTE, takeFiles } from "./paste.js";
import { mountUploads } from "./uploads.js";

const MAC = /mac/i.test(navigator.userAgentData?.platform || navigator.platform || "");
const MODES = {
  ask: { label: "Ask", placeholder: "Ask anything about your agents, your messages or what to do next…" },
  build: { label: "Start Mission", placeholder: "Describe what you want to accomplish…" },
};
const WAIT = 10000; // ms a press waits for "created" before the button works again
const NOT_CONNECTED = "Not connected: is `ai-browser app` running?";

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
    for (const id of ["task-web", "task-model", "task-folder", "task-auto-switch", "attach", "mission-words"]) {
      $(id).hidden = !build;
    }
    $("task-account").hidden = !build || rows.length < 2;
    $("task-workspace").hidden = mode === "ask";
    $("attached").hidden = !build || uploads.count() === 0;
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
    begin({ type: "new_task", text, skills: [], model: $("task-model").value, web: $("task-web").value, ...account,
            ...(name ? { name } : {}), ...(description ? { description } : {}),
            ...(folder ? { folder } : {}), ...(files.length ? { attachments: files } : {}), ...auto, ...workspace(),
            ...(handing ? { adopt: handing.target } : {}) });
  }

  function option(value, label) {
    const node = el("option", "", label);
    node.value = value;
    return node;
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
  $("start-key").textContent = MAC ? "⌘ ↵" : "Ctrl ↵";
  $("task-auto-switch").title = autoTitle(false, false); // until the app says this computer runs commands
  setMode("build");

  return {
    note,
    focus() { // Command-K (Ctrl+K) and New Mission: Build a Mission, the cursor in the box
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
        case "created":
          if (pending && message.request === pending) {
            const took = taking;
            finish();
            $("task").value = "";
            $("task-name").value = "";
            $("task-about").value = "";
            $("task-auto").checked = false; // each task is its own choice: the next one starts off
            setHanding(null);
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
