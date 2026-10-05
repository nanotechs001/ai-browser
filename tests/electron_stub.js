// A stand-in for Electron's main-process API, so the tests can run AI Browser's own main.js under Node.js. Nothing is
// shown and nothing is registered with the system: every call main.js makes is recorded, and app.exit and app.quit end
// the run, as they would end the app. node:child_process is a stand-in too, so nothing ever runs: execFile is
// recorded, and "prints" STUB_PLAN's "stdout". The calls go to STUB_OUT as JSON, when the app ends or after
// STUB_PLAN's "settle" ms.
// Usage: node electron_stub.js <main.js> [the app's switches…]. STUB_PLAN (JSON):
// - "ready_after": ms before app.whenReady() resolves (default 0);
// - "lock": false: another instance holds the single-instance lock;
// - "taken": the accelerators another app holds (registering one answers false);
// - "statuses": {address: [codes]}: the HTTP status each load of that address gets, in turn (default 200);
// - "area": the screen's work area (default {x: 0, y: 0, width: 1440, height: 900});
// - "stdout": what a program run with execFile prints (default "");
// - "folder": the path the folder dialog (dialog.showOpenDialog) returns; without it, the user cancels;
// - "steps": [[ms, what, ...args]], done that many ms after the start, as the user or a page would:
//   - ["press"]: the global shortcut; ["tray", label]: a click on the menu-bar icon's item;
//   - ["focus", kind] and ["blur"]: a click in one of the app's windows ("main", "chat"), or in another app;
//   - ["move", {x, y, width, height}]: the user moves the chat;
//   - ["navigate", kind, url]: that window's page tries to go to `url` (recorded with whether it may);
//   - ["invoke", kind, action, ...args], ["invoke_framed", kind, action, ...args]: that window's page (or a frame in
//     it) asks the bridge for `action`; the answer is recorded as ["answer", action, value].
// It runs as a test's unpackaged Electron does: Electron's default app loaded the folder (process.defaultApp).
"use strict";

const fs = require("node:fs");
const Module = require("node:module");

const plan = JSON.parse(process.env.STUB_PLAN || "{}");
const calls = [];
const TITLES = { main: "AI Browser", chat: "AI Browser chat" };
const opened = []; // every window main.js made, in order
const held = new Map(); // accelerator -> what it calls
const handlers = new Map(); // ipcMain channel -> handler
const paths = {};
let tray = null;
let ended = false;

function record(...call) {
  if (!ended) calls.push(call);
}

function end() { // the app is gone: what it did, for the test
  if (ended) return;
  ended = true;
  fs.writeFileSync(process.env.STUB_OUT, JSON.stringify(calls));
  process.exit(0);
}

class Emitter {
  constructor() { this.handlers = {}; }
  on(name, handler) { (this.handlers[name] ||= []).push(handler); return this; }
  once(name, handler) { return this.on(name, handler); }
  emit(name, ...args) { for (const handler of this.handlers[name] || []) handler(...args); }
}

const ready = new Promise((resolve) => setTimeout(resolve, plan.ready_after || 0));
const app = Object.assign(new Emitter(), {
  isPackaged: false,
  commandLine: { hasSwitch: (name) => process.argv.some((arg) => arg === `--${name}` || arg.startsWith(`--${name}=`)) },
  setPath: (name, value) => {
    record("app.setPath", name);
    paths[name] = value;
  },
  getPath: (name) => paths[name] || `/nonexistent/${name}`,
  requestSingleInstanceLock: () => { record("app.requestSingleInstanceLock"); return plan.lock !== false; },
  releaseSingleInstanceLock: () => record("app.releaseSingleInstanceLock"),
  whenReady: () => ready,
  focus: () => {},
  hide: () => {
    record("app.hide");
    for (const win of opened) win.focused = false;
  },
  setAppUserModelId: () => {},
  exit: (code) => { record("app.exit", code); end(); },
  quit: () => {
    record("app.quit");
    app.emit("before-quit");
    app.emit("will-quit");
    end();
  },
});

class WebContents extends Emitter {
  constructor() {
    super();
    this.mainFrame = { url: "" };
  }

  setWindowOpenHandler() {}
}

class BrowserWindow extends Emitter {
  static getFocusedWindow() { return opened.find((win) => win.focused) || null; }
  static fromWebContents(contents) { return opened.find((win) => win.webContents === contents) || null; }

  constructor(options) {
    super();
    this.title = options.title;
    this.bounds = { x: options.x ?? 0, y: options.y ?? 0, width: options.width, height: options.height };
    this.visible = false;
    this.focused = false;
    this.webContents = new WebContents();
    opened.push(this);
    record("new BrowserWindow", options.title, { ...this.bounds, alwaysOnTop: options.alwaysOnTop === true,
                                                 skipTaskbar: options.skipTaskbar === true });
    app.emit("web-contents-created", {}, this.webContents);
  }

  loadURL(url) {
    record("win.loadURL", url);
    this.webContents.mainFrame.url = url;
    const codes = (plan.statuses || {})[url];
    const code = Array.isArray(codes) && codes.length ? codes.shift() : 200;
    setTimeout(() => this.webContents.emit("did-navigate", {}, url, code, ""), 0);
    return Promise.resolve();
  }

  isMinimized() { return false; }
  restore() {}
  show() { record("win.show", this.title); this.visible = true; }
  focus() { for (const win of opened) win.focused = win === this; }
  isVisible() { return this.visible; }
  isFocused() { return this.focused; }
  hide() { record("win.hide", this.title); this.visible = false; this.focused = false; }
  getBounds() { return { ...this.bounds }; }
}

class Notification extends Emitter {
  static isSupported() { return true; }
  constructor(options) { super(); record("new Notification", options.title); }
  show() {}
}

class Tray extends Emitter {
  constructor() { super(); record("new Tray"); tray = this; }
  setToolTip() {}
  setContextMenu(menu) { this.menu = menu; }
}

const electron = {
  app, BrowserWindow, Notification, Tray,
  Menu: { setApplicationMenu: () => {}, buildFromTemplate: (template) => template },
  dialog: {
    showMessageBox: async (options) => { record("dialog.showMessageBox", options.message); return { response: 0 }; },
    showOpenDialog: async (win, options) => {
      record("dialog.showOpenDialog", win?.title ?? null, options.properties);
      return plan.folder ? { canceled: false, filePaths: [plan.folder] } : { canceled: true, filePaths: [] };
    },
  },
  globalShortcut: {
    register: (accelerator, callback) => {
      record("globalShortcut.register", accelerator);
      if ((plan.taken || []).includes(accelerator)) return false;
      held.set(accelerator, callback);
      return true;
    },
    unregister: (accelerator) => { held.delete(accelerator); },
    unregisterAll: () => { held.clear(); },
  },
  ipcMain: { handle: (channel, handler) => { handlers.set(channel, handler); } },
  nativeImage: { createFromPath: () => ({ resize: () => ({}) }) },
  screen: { getAllDisplays: () => [{ workArea: plan.area || { x: 0, y: 0, width: 1440, height: 900 } }] },
  session: { defaultSession: { setPermissionRequestHandler: () => {}, setPermissionCheckHandler: () => {},
                               setDevicePermissionHandler: () => {}, on: () => {} } },
  shell: {},
};

const childProcess = { // nothing runs: the command is recorded, and STUB_PLAN's stdout is what it "printed"
  execFile: (file, args, options, callback) => {
    record("execFile", file, args);
    setTimeout(() => callback(null, plan.stdout ?? "", ""), 0);
    return { kill: () => {} };
  },
};

function windowOf(kind) {
  return opened.find((win) => win.title === TITLES[kind]) || null;
}

async function invoke(kind, action, args, framed) { // a page asks the bridge, as preload.js's ipcRenderer.invoke does
  const win = windowOf(kind);
  const handler = handlers.get(`aib:${action}`);
  if (!win || !handler) {
    record("answer", action, "nothing to ask");
    return;
  }
  const frame = framed ? { url: win.webContents.mainFrame.url } : win.webContents.mainFrame;
  const value = await handler({ sender: win.webContents, senderFrame: frame }, ...args);
  record("answer", action, value === undefined ? null : value);
}

function step(what, args) {
  if (what === "press") {
    record("press");
    for (const callback of held.values()) callback();
  } else if (what === "tray") {
    const item = (tray?.menu || []).find((entry) => entry.label === args[0]);
    const enabled = Boolean(item) && item.enabled !== false;
    record("tray", args[0], enabled);
    if (enabled && item.click) item.click();
  } else if (what === "focus") {
    windowOf(args[0])?.focus();
  } else if (what === "blur") {
    for (const win of opened) win.focused = false;
  } else if (what === "move") {
    const win = windowOf("chat");
    if (win) {
      win.bounds = { ...args[0] };
      win.emit("moved");
    }
  } else if (what === "navigate") {
    const win = windowOf(args[0]);
    let refused = false;
    const details = { url: args[1], isMainFrame: true, preventDefault: () => { refused = true; } };
    win?.webContents.emit("will-navigate", details);
    record("navigate", args[0], args[1], Boolean(win) && !refused);
  } else if (what === "invoke" || what === "invoke_framed") {
    invoke(args[0], args[1], args.slice(2), what === "invoke_framed");
  }
}

Object.defineProperty(process, "defaultApp", { value: true }); // as Electron's default app sets it
const load = Module._load;
Module._load = function (request, ...rest) {
  if (request === "electron") return electron;
  if (request === "node:child_process" || request === "child_process") return childProcess;
  return load.call(this, request, ...rest);
};
const main = process.argv[2];
process.argv = [process.argv[0], main, ...process.argv.slice(3)]; // as the app sees it: the program, then its switches
setTimeout(end, plan.settle || 3000);
for (const [ms, what, ...args] of plan.steps || []) setTimeout(() => step(what, args), ms);
require(main);
