// A stand-in for Electron's main-process API, so the tests can run AI Browser's own main.js under Node.js. Nothing is
// shown and nothing is registered with the system: every call main.js makes is recorded, and app.exit and app.quit end
// the run, as they would end the app. The calls go to STUB_OUT as JSON, when the app ends or after STUB_PLAN's
// "settle" ms.
// Usage: node electron_stub.js <main.js> [the app's switches…]. STUB_PLAN (JSON):
// - "ready_after": ms before app.whenReady() resolves (default 0);
// - "lock": false: another instance holds the single-instance lock.
// It runs as a test's unpackaged Electron does: Electron's default app loaded the folder (process.defaultApp).
"use strict";

const fs = require("node:fs");
const Module = require("node:module");

const plan = JSON.parse(process.env.STUB_PLAN || "{}");
const calls = [];
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
  setPath: (name) => record("app.setPath", name),
  getPath: (name) => `/nonexistent/${name}`,
  requestSingleInstanceLock: () => { record("app.requestSingleInstanceLock"); return plan.lock !== false; },
  releaseSingleInstanceLock: () => record("app.releaseSingleInstanceLock"),
  whenReady: () => ready,
  focus: () => {},
  setAppUserModelId: () => {},
  exit: (code) => { record("app.exit", code); end(); },
  quit: () => {
    record("app.quit");
    app.emit("before-quit");
    app.emit("will-quit");
    end();
  },
});

class BrowserWindow extends Emitter {
  constructor(options) { super(); record("new BrowserWindow", options.title); }
  loadURL(url) { record("win.loadURL", url); return Promise.resolve(); }
  isMinimized() { return false; }
  restore() {}
  show() { record("win.show"); }
  focus() {}
  isVisible() { return false; }
  isFocused() { return false; }
  hide() { record("win.hide"); }
}

class Notification extends Emitter {
  static isSupported() { return true; }
  constructor(options) { super(); record("new Notification", options.title); }
  show() {}
}

class Tray extends Emitter {
  constructor() { super(); record("new Tray"); }
  setToolTip() {}
  setContextMenu() {}
}

const electron = {
  app, BrowserWindow, Notification, Tray,
  Menu: { setApplicationMenu: () => {}, buildFromTemplate: (template) => template },
  dialog: {
    showMessageBox: async (options) => { record("dialog.showMessageBox", options.message); return { response: 0 }; },
  },
  globalShortcut: { register: (accelerator) => { record("globalShortcut.register", accelerator); return true; },
                    unregister: () => {}, unregisterAll: () => {} },
  ipcMain: { handle: () => {} },
  nativeImage: { createFromPath: () => ({ resize: () => ({}) }) },
  session: { defaultSession: { setPermissionRequestHandler: () => {}, setPermissionCheckHandler: () => {},
                               setDevicePermissionHandler: () => {}, on: () => {} } },
  shell: {},
};

Object.defineProperty(process, "defaultApp", { value: true }); // as Electron's default app sets it
const load = Module._load;
Module._load = function (request, ...rest) {
  return request === "electron" ? electron : load.call(this, request, ...rest);
};
const main = process.argv[2];
process.argv = [process.argv[0], main, ...process.argv.slice(3)]; // as the app sees it: the program, then its switches
setTimeout(end, plan.settle || 3000);
require(main);
