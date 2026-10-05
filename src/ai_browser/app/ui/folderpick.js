// The Folder picker beside the model and the account (agent powers, Decisions 6 and 7). It offers No folder (the
// agent's own scratch folder), the folders used lately, and Choose…. In AI Browser's own app, Choose… opens the
// system's folder dialog: the floating chat asks the app itself (window.aib.chooseFolder), and AI Home and Mission
// Control, which sit in the tab menu's frames, ask the tab menu, the one page there the app answers. Anywhere else the
// user types the path. The app checks the folder (folder_choose); the first time one is used the user answers "Trust
// this folder?" (folder_trust). Every path and word is set as text.
"use strict";

import { el } from "./chat.js";
import { folderName } from "./plan.js";

const NONE = "";
const CHOOSE = "\u0000choose"; // never a path
const RECENT = 8; // folders used lately, in the list
const PICK_WAIT = 10 * 60 * 1000; // ms the tab menu's dialog may stay open
export const TRUST_FIRST = "Answer “Trust this folder?” first";

function trustWords(name) {
  return `Trust ${name}? Then its CLAUDE.md, its .claude agents and its settings load, as in Claude Code, with its `
    + "own hooks and its own rules for what runs without asking. If not, only your answers here count. Trust only "
    + "folders you know.";
}

let asks = 0;

function askTabMenu() { // AI Home and Mission Control: the tab menu opens the dialog (undefined: type the path)
  return new Promise((resolve) => {
    const id = `folder-${Date.now()}-${++asks}`;
    const done = (value) => {
      clearTimeout(timer);
      removeEventListener("message", heard);
      resolve(value);
    };
    const timer = setTimeout(() => done(null), PICK_WAIT);
    function heard(event) {
      if (event.source !== window.parent || event.origin !== location.origin) return;
      const answer = event.data;
      if (answer?.type !== "folder-chosen" || answer.id !== id) return;
      done(answer.typed ? undefined : typeof answer.path === "string" ? answer.path : null);
    }
    addEventListener("message", heard);
    window.parent.postMessage({ type: "choose-folder", id }, location.origin);
  });
}

async function pickPath() { // a path, null (cancelled), or undefined (no dialog here: the user types it)
  if (typeof window.aib?.chooseFolder === "function") {
    try {
      const path = await window.aib.chooseFolder();
      return typeof path === "string" && path ? path : null;
    } catch {
      return undefined;
    }
  }
  return window.parent !== window ? askTabMenu() : undefined;
}

// parts: {select, box}: the picker, and the box under the task bar for the typed path, the trust question or a note.
export function mountFolderPicker({ select, box }, send) {
  let recent = []; // the folders the app lists, newest first: {path, name, trusted, missing}
  let chosen = null; // the folder picked and checked by the app: {path, name, trusted}
  let waiting = null; // the request id of the check or the trust answer under way
  let requests = 0;

  function show(...nodes) {
    box.replaceChildren(...nodes);
    box.hidden = nodes.length === 0;
  }

  function say(text) {
    show(...(text ? [el("p", "muted folder-note", text)] : []));
  }

  function ask(message) {
    requests += 1;
    waiting = `fold-${requests}`;
    if (send({ ...message, request: waiting })) return true;
    waiting = null;
    say("Not connected: is `ai-browser app` running?");
    return false;
  }

  function option(label, value, title) {
    const node = el("option", "", label);
    node.value = value;
    if (title) node.title = title;
    return node;
  }

  function fill() { // rebuilt only when what it lists changes, and never while it's open
    const rows = recent.filter((row) => !row.missing).slice(0, RECENT);
    if (chosen && !rows.some((row) => row.path === chosen.path)) rows.unshift(chosen);
    const signature = JSON.stringify([rows.map((row) => row.path), chosen?.path || NONE]);
    if (select.dataset.rows === signature || document.activeElement === select) return;
    select.replaceChildren(option("No folder", NONE, "The agent's own scratch folder"),
      ...rows.map((row) => option(row.name || folderName(row.path), row.path, row.path)), option("Choose…", CHOOSE));
    select.value = chosen?.path || NONE;
    select.dataset.rows = signature;
  }

  function showTrust(folder) { // "Trust this folder?": the first time a folder is used
    const yes = el("button", "trust primary", "Trust");
    const no = el("button", "distrust", "Don't trust");
    for (const [button, trust] of [[yes, true], [no, false]]) {
      button.type = "button";
      button.addEventListener("click", () => ask({ type: "folder_trust", path: folder.path, trust }));
    }
    const row = el("div", "row");
    row.append(yes, no);
    show(el("p", "folder-trust", trustWords(folder.name || folderName(folder.path))),
         el("p", "muted folder-path", folder.path), row);
  }

  function showTyped() { // no folder dialog here: the user types the path
    const input = el("input", "folder-typed");
    input.type = "text";
    input.maxLength = 4096;
    input.placeholder = "The folder's full path";
    input.setAttribute("aria-label", "The folder's full path");
    const use = el("button", "folder-use", "Use");
    use.type = "button";
    const check = () => {
      const path = input.value.trim();
      if (path) ask({ type: "folder_choose", path });
    };
    use.addEventListener("click", check);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") check();
    });
    const row = el("div", "row folder-typing");
    row.append(input, use);
    show(row);
    input.focus();
  }

  function showChosen() {
    if (!chosen) say("");
    else if (chosen.trusted === null) showTrust(chosen);
    else if (chosen.trusted) say(`Trusted: ${chosen.path}`);
    else say(`Not trusted: ${chosen.path}. Its own settings and hooks don't load.`);
  }

  async function choose() {
    select.value = chosen?.path || NONE; // the list shows the folder in use until another is checked
    const path = await pickPath();
    if (typeof path === "string") ask({ type: "folder_choose", path });
    else if (path === undefined) showTyped();
  }

  select.addEventListener("change", () => {
    if (select.value === CHOOSE) {
      choose();
    } else if (select.value === NONE) {
      chosen = null;
      showChosen();
    } else {
      ask({ type: "folder_choose", path: select.value });
    }
  });
  fill();

  return {
    onMessage(message) {
      if (message.type === "permissions") {
        recent = Array.isArray(message.folders) ? message.folders : [];
        const row = chosen && recent.find((one) => one.path === chosen.path);
        if (row && row.trusted !== chosen.trusted) { // answered elsewhere: another page, or Settings
          chosen = { ...chosen, trusted: row.trusted };
          showChosen();
        }
        fill();
      } else if (message.type === "folder" && message.request && message.request === waiting) {
        waiting = null;
        chosen = message.folder || null;
        if (document.activeElement === select) select.blur(); // the pick is made: the list may show it now
        fill();
        showChosen();
      } else if (message.type === "error" && message.request && message.request === waiting) {
        waiting = null;
        const typing = box.querySelector(".folder-typing");
        const why = el("p", "muted folder-note", String(message.text || ""));
        if (typing) show(typing, why);
        else show(why);
        select.value = chosen?.path || NONE;
      }
    },
    value() { return chosen?.path || null; }, // the task's folder; null: its own scratch folder
    ready() { return chosen && chosen.trusted === null ? TRUST_FIRST : ""; }, // "" when Start may go
  };
}
