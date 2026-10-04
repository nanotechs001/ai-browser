// The bridge between AI Browser's pages and its app: named actions only, each answered by main.js's ACTIONS, for AI
// Browser's own top-level pages (anything else gets null). contextIsolation keeps this file's world apart from the
// page's, and the sandbox gives it no Node.js. Part a has no action for pages: the shortcut and notifications go
// through the engine, which the pages already talk to. The floating chat adds its own (part c), here and in main.js.
"use strict";

const { contextBridge, ipcRenderer } = require("electron");

const ACTIONS = []; // the names main.js's ACTIONS answers, in the same order
const bridge = {};
for (const name of ACTIONS) bridge[name] = (...args) => ipcRenderer.invoke(`aib:${name}`, ...args);
contextBridge.exposeInMainWorld("aib", Object.freeze(bridge));
