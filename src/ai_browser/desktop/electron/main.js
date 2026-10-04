// AI Browser's own app (Electron). `ai-browser app` starts it (desktop/launch.py) and talks to it over one private
// line (line.js): the start address, with its one-time code, comes that way, never on a command line.
// - It shows the tab menu at http://127.0.0.1:<port>/app in a window locked down as policy.js says.
// - It keeps an icon in the menu bar (by the clock on Windows), and holds the shortcut picked in Settings (in part a
//   it shows and hides the window).
// - It shows the notifications the engine writes, word for word.
// Closing the window hides it. Quit ends the app and tells the engine, which stops too. When the engine goes, the app
// quits. The packaged app never runs with a debugging port or an inspector, and its pages never get DevTools.
"use strict";

const { app, BrowserWindow, Menu, Notification, Tray, dialog, globalShortcut, ipcMain, nativeImage, session, shell } =
  require("electron");
const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");
const policy = require("./policy.js");
const { encode, lineOption, splitter } = require("./line.js");

const APP_ID = "io.github.nanotechs001.ai-browser"; // desktop/layout.py's BUNDLE_ID, and Windows' AppUserModelID
const TOAST_CLSID = "{52E8D68C-5CAC-4680-848A-E80657E0B4D5}"; // Windows: the Start menu entry's toast activator
const PROFILE = "--aib-profile="; // an unpackaged Electron only (the tests'): its throwaway profile
// A test's Electron, started on this folder: Electron's own default app loaded it, and its program has Electron's
// name. Never AI Browser's app, whose Electron loads resources/app and has no default app left. app.isPackaged alone
// isn't enough: it only compares the program's name, and the Mac app's program keeps Electron's (Contents/MacOS).
const UNPACKAGED = !app.isPackaged && process.defaultApp === true;
const ICON = path.join(__dirname, "icon.png");
const START_WAIT = 20000; // ms for the engine's start message
const NOTES_KEPT = 20; // notifications whose click still reaches the engine
const WEB = Object.freeze({ // every window's webPreferences (makeWindow)
  contextIsolation: true,
  sandbox: true,
  nodeIntegration: false,
  nodeIntegrationInWorker: false,
  nodeIntegrationInSubFrames: false,
  webSecurity: true,
  allowRunningInsecureContent: false,
  webviewTag: false,
  devTools: false,
  spellcheck: false,
  navigateOnDragDrop: false,
  safeDialogs: true,
  autoplayPolicy: "no-user-gesture-required", // Mission Control speaks without a click first
  preload: path.join(__dirname, "preload.js"),
});
const ACTIONS = new Map(); // name -> handler: what a page may ask the app for (preload.js lists the same names)

const windows = new Map(); // "main" (the floating chat adds "chat")
const notes = new Map(); // id -> Notification, kept so a click still reaches us
let own = null; // the app's own origin, http://127.0.0.1:<port>, once the engine has started it
let send = () => false; // a message to the engine
let starting = false;
let started = false;
let quitting = false;
let engineQuit = false; // the engine asked for the quit, or went away: there is no one to tell
let shortcut = null; // the accelerator registered now
let pressed = false; // it fired since it was registered
let tray = null;

function profileFolder() { // <home>/desktop/profile, beside the app (a test's unpackaged Electron: its own)
  const given = process.argv.find((arg) => arg.startsWith(PROFILE));
  if (given && UNPACKAGED) return given.slice(PROFILE.length);
  const up = process.platform === "darwin" ? ["..", "..", "..", ".."] : ["..", ".."]; // out of the .app, or the folder
  return path.join(path.resolve(process.execPath, ...up), "profile");
}

function openLine(onMessage, onEnd) {
  const feed = splitter(onMessage);
  let ended = false;
  const end = () => {
    if (!ended) {
      ended = true;
      onEnd();
    }
  };
  const where = lineOption(process.argv);
  if (where) { // macOS: the socket the engine named
    const socket = net.createConnection({ path: where });
    socket.setEncoding("utf8");
    socket.on("data", feed);
    socket.on("close", end);
    socket.on("error", () => {}); // "close" follows
    send = (message) => !socket.destroyed && socket.write(encode(message));
    return;
  }
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", feed);
  process.stdin.on("end", end);
  process.stdin.on("error", end);
  process.stdout.on("error", () => {});
  send = (message) => {
    try {
      return process.stdout.write(encode(message));
    } catch {
      return false;
    }
  };
}

function noEngine() { // started by a double-click (Finder, the Start menu), with no `ai-browser app` behind it
  if (started) return;
  starting = true; // a start message coming now is too late
  app.whenReady().then(async () => {
    await dialog.showMessageBox({ type: "info", message: "Start AI Browser from a terminal",
                                  detail: "Run: uv run ai-browser app", buttons: ["OK"] });
    app.exit(0);
  });
}

function makeWindow(kind, options) { // every window: locked down the same way, kept by its kind
  const win = new BrowserWindow({ ...options, show: false, webPreferences: { ...WEB } });
  windows.set(kind, win);
  win.on("closed", () => windows.delete(kind));
  return win;
}

function showWindow(kind) {
  const win = windows.get(kind);
  if (!win) return;
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
  if (process.platform === "darwin") app.focus({ steal: true });
}

function toggleMain() { // the shortcut: AI Browser's window comes forward, or hides when it is in front
  if (!pressed) {
    pressed = true; // it works: Settings says so
    send({ type: "shortcut", value: shortcut, ok: true, why: "", pressed: true });
  }
  const win = windows.get("main");
  if (win && win.isVisible() && win.isFocused()) win.hide();
  else showWindow("main");
}

function useShortcut(value, request) { // move the global shortcut, and tell the engine how it went
  const result = policy.moveShortcut(globalShortcut, shortcut, value, toggleMain);
  if (result.registered !== shortcut) pressed = false;
  shortcut = result.registered;
  send({ type: "shortcut", value: value ?? null, ok: result.ok, why: result.why, pressed: false,
         ...(request ? { request } : {}) });
}

function lockContents(contents) { // every page, frame and window: AI Browser's own pages only
  contents.setWindowOpenHandler(() => ({ action: "deny" })); // no window opens another; a website goes to Brave
  contents.on("will-attach-webview", (event) => event.preventDefault());
  for (const name of ["will-navigate", "will-frame-navigate", "will-redirect"]) {
    contents.on(name, (details) => {
      if (!policy.mayNavigate(details.url, own, details.isMainFrame)) details.preventDefault();
    });
  }
}

function lockSession(ses) { // the microphone and copying, for AI Browser's own pages; nothing else, for anyone
  ses.setPermissionRequestHandler((contents, permission, callback, details) => {
    callback(policy.mayRequest(permission, details, own));
  });
  ses.setPermissionCheckHandler((contents, permission, requestingOrigin, details) =>
    policy.mayCheck(permission, requestingOrigin, details, own));
  ses.setDevicePermissionHandler(() => false);
  ses.on("will-download", (event) => event.preventDefault()); // nothing downloads here
}

function makeMenu() { // a Mac's menu bar: hiding, copy and paste, the window, Quit; Windows: a title bar only
  if (process.platform !== "darwin") {
    Menu.setApplicationMenu(null);
    return;
  }
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { label: "AI Browser", submenu: [{ role: "hide" }, { role: "hideOthers" }, { role: "unhide" },
                                     { type: "separator" }, { role: "quit" }] },
    { role: "editMenu" },
    { label: "Window", submenu: [{ role: "minimize" }, { role: "zoom" }, { type: "separator" }, { role: "close" }] },
  ]));
}

function makeTray() { // the menu-bar icon (by the clock on Windows)
  const size = process.platform === "darwin" ? 18 : 16;
  tray = new Tray(nativeImage.createFromPath(ICON).resize({ width: size, height: size }));
  tray.setToolTip("AI Browser");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Open AI Browser", click: () => showWindow("main") },
    { label: "Show chat", enabled: false }, // the floating chat: part c
    { type: "separator" },
    { label: "Quit", click: () => app.quit() },
  ]));
  if (process.platform === "win32") tray.on("click", () => showWindow("main"));
}

// Windows shows an app's notifications only when the Start menu has a shortcut to it with the same AppUserModelID and
// toast activator (setup's offer says so). Started from that entry, the app says to start AI Browser from a terminal.
function startMenuEntry() {
  if (UNPACKAGED) return;
  app.setAppUserModelId(APP_ID);
  if (typeof app.setToastActivatorCLSID === "function") app.setToastActivatorCLSID(TOAST_CLSID); // where it exists
  const link = path.join(app.getPath("appData"), "Microsoft", "Windows", "Start Menu", "Programs", "AI Browser.lnk");
  const want = { target: process.execPath, appUserModelId: APP_ID, toastActivatorClsid: TOAST_CLSID,
                 description: "AI Browser" };
  let have = null;
  try {
    have = shell.readShortcutLink(link);
  } catch {
    have = null;
  }
  if (have && have.target === want.target && have.appUserModelId === APP_ID) return;
  try {
    shell.writeShortcutLink(link, have ? "replace" : "create", want);
  } catch {
    // without it Windows may not show the notifications; everything else works
  }
}

function notify(message) { // the engine's words, as written (policy.notice keeps text only, cut to length)
  const text = policy.notice(message);
  if (!text || !Notification.isSupported()) return;
  const note = new Notification({ title: text.title, body: text.body,
                                  ...(process.platform === "win32" ? { icon: ICON } : {}) });
  note.on("click", () => {
    notes.delete(text.id);
    send({ type: "clicked", id: text.id });
  });
  note.on("close", () => notes.delete(text.id));
  notes.set(text.id, note);
  while (notes.size > NOTES_KEPT) notes.delete(notes.keys().next().value);
  note.show();
}

function answerActions() { // each named action, for AI Browser's own top-level pages only
  for (const [name, handler] of ACTIONS) {
    ipcMain.handle(`aib:${name}`, (event, ...args) => {
      const frame = event.senderFrame;
      if (!frame || frame !== event.sender.mainFrame || policy.originOf(frame.url) !== own) return null;
      return handler(...args);
    });
  }
}

function begin(message) { // the engine's start: the window on its start address, the menu-bar icon, the shortcut
  own = policy.startOrigin(message.open);
  if (!own) {
    engineQuit = true;
    app.exit(1); // not the engine's own address: nothing loads
    return;
  }
  started = true;
  if (process.platform === "win32") startMenuEntry();
  makeTray();
  const win = makeWindow("main", { width: 1440, height: 960, minWidth: 720, minHeight: 480, title: "AI Browser",
                                   backgroundColor: "#faf9f5", icon: ICON });
  win.on("close", (event) => { // closing hides it: the app keeps running, and so do the agents
    if (!quitting) {
      event.preventDefault();
      win.hide();
    }
  });
  win.once("ready-to-show", () => showWindow("main"));
  win.loadURL(message.open).catch(() => {}); // a page that can't load: the engine says so (it waits for the page)
  send({ type: "hello", pid: process.pid });
  useShortcut(policy.shortcutOk(message.shortcut) ? message.shortcut : null, null);
}

function onEngine(message) {
  if (message.type === "notify") notify(message);
  else if (message.type === "show") showWindow("main");
  else if (message.type === "shortcut" && "value" in message) {
    useShortcut(message.value, typeof message.request === "string" ? message.request.slice(0, 40) : null);
  } else if (message.type === "quit") {
    engineQuit = true;
    app.quit();
  }
}

function main() {
  const profile = profileFolder();
  fs.mkdirSync(profile, { recursive: true });
  app.setPath("userData", profile);
  if (!app.requestSingleInstanceLock()) {
    app.exit(0); // one app per profile: the running one comes forward instead (second-instance)
    return;
  }
  app.on("second-instance", () => showWindow("main"));
  app.on("activate", () => showWindow("main")); // a click on the Dock icon
  app.on("before-quit", () => {
    quitting = true;
    if (!engineQuit) send({ type: "quit" });
  });
  app.on("will-quit", () => globalShortcut.unregisterAll());
  app.on("window-all-closed", () => {}); // only Quit ends the app
  app.on("web-contents-created", (event, contents) => lockContents(contents));
  const waiting = setTimeout(noEngine, START_WAIT);
  openLine((message) => {
    if (message.type === "start" && !starting) {
      starting = true;
      clearTimeout(waiting);
      app.whenReady().then(() => begin(message)).catch(() => app.exit(1)); // a broken start: the engine hears it
    } else if (started) {
      onEngine(message);
    }
  }, () => {
    clearTimeout(waiting);
    if (started) {
      engineQuit = true;
      app.quit();
    } else {
      noEngine();
    }
  });
  app.whenReady().then(() => {
    lockSession(session.defaultSession);
    makeMenu();
    answerActions();
  });
}

if (!UNPACKAGED && policy.DEBUG_SWITCHES.some((name) => app.commandLine.hasSwitch(name))) {
  app.exit(1); // the packaged app never runs with a debugging port or an inspector
} else {
  main();
}
