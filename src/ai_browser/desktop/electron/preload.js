// The bridge between AI Browser's pages and its app: named actions only, each answered by main.js's ACTIONS, for AI
// Browser's own top-level pages (anything else gets null). contextIsolation keeps this file's world apart from the
// page's, and the sandbox gives it no Node.js. The shortcut and notifications go through the engine, which the pages
// already talk to. The actions:
// - chat("show" | "hide"): show the chat, or hide it;
// - thisPage(): which Brave tab the user is on, as {state, url, title}. main.js answers only the chat's own page, and
//   only while the chat shows.
// - chooseFolder(): the system's folder dialog, for a task's folder (agent powers): the path picked, or null. main.js
//   answers AI Browser's own top-level pages only: the tab menu (for AI Home and Mission Control in its frames) and
//   the chat.
"use strict";

const { contextBridge, ipcRenderer } = require("electron");

const ACTIONS = ["chat", "thisPage", "chooseFolder"]; // the names main.js's ACTIONS answers, in the same order
const bridge = {};
for (const name of ACTIONS) bridge[name] = (...args) => ipcRenderer.invoke(`aib:${name}`, ...args);
contextBridge.exposeInMainWorld("aib", Object.freeze(bridge));
