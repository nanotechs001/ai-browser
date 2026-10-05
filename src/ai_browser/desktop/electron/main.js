// AI Browser's own app (Electron). `ai-browser app` starts it (desktop/launch.py) and talks to it over one private
// line (line.js): the start address, with its one-time code, comes that way, never on a command line.
// - It shows the tab menu at http://127.0.0.1:<port>/app in a window locked down as policy.js says.
// - The floating chat: a small window above the others, beside Brave, that shows /chat and nothing else. The shortcut
//   picked in Settings (⌥Space) shows and hides it from any app, and so does the menu-bar icon's Show chat. It opens
//   where the user left it, at the size they left it (chat.json, in the profile).
// - Its pages may ask it for three things (preload.js): to show or hide the chat; and, from the chat alone while it
//   shows, which Brave tab the user is on (thispage.js: the tab's address and title, nothing else).
//   And the system's folder dialog, for a task's folder (chooseFolder), from the main window's page or the chat's.
// - It keeps an icon in the menu bar (by the clock on Windows).
// - It shows the notifications the engine writes, word for word.
// Closing a window hides it. Quit ends the app and tells the engine, which stops too. When the engine goes, the app
// quits. The packaged app never runs with a debugging port or an inspector, and its pages never get DevTools.
"use strict";

const { app, BrowserWindow, Menu, Notification, Tray, dialog, globalShortcut, ipcMain, nativeImage, screen, session,
        shell } = require("electron");
const fs = require("node:fs");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");
const policy = require("./policy.js");
const thispage = require("./thispage.js");
const { LINE_KEY, encode, lineOption, lineTarget, splitter } = require("./line.js");

const PROFILE = "--aib-profile="; // an unpackaged Electron only (the tests'): its throwaway profile
const FAKE_PAGE = "--aib-fake-page="; // an unpackaged Electron only (the tests'): a file that stands in for Brave
// A test's Electron, started on this folder: Electron's own default app loaded it, and its program has Electron's
// name. Never AI Browser's app, whose Electron loads resources/app and has no default app left. app.isPackaged alone
// isn't enough: it only compares the program's name, and the Mac app's program keeps Electron's (Contents/MacOS).
const UNPACKAGED = !app.isPackaged && process.defaultApp === true;
const ICON = path.join(__dirname, "icon.png");
const START_WAIT = 20000; // ms for the engine's start message
const NOTES_KEPT = 20; // notifications whose click still reaches the engine
const CHAT_FILE = "chat.json"; // in the profile: where the floating chat was, and its size
const SAVE_AFTER = 500; // ms after the chat stops moving or resizing before its place is kept
// AIB_DEBUG_START=1 (the engine's start log, ai_browser/debugstart.py): each step of the start, in debug-start.log in
// the profile. Off by default, and on it changes nothing else. Never a cookie's value or a start code.
const DEBUG = process.env.AIB_DEBUG_START === "1";
const DEBUG_FILE = "debug-start.log";
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
// What a page may ask the app for, by name (preload.js lists the same names, in the same order). Each handler gets the
// asking page's webContents first: answerActions has checked it is AI Browser's own top-level page.
const ACTIONS = new Map([["chat", chatAction], ["thisPage", thisPageAction], ["chooseFolder", chooseFolderAction]]);

const windows = new Map(); // "main", and "chat" once the floating chat has shown
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
let chatLoaded = false; // the chat's window shows /chat now (the engine answered it with 200)
let chatFrom = false; // another app was in front when the chat came: on a Mac, hiding the chat goes back to it
let saving = null; // the timer that keeps the chat's place
let looking = null; // a look at Brave's front tab under way: one at a time
let choosing = null; // the folder dialog open now: one at a time
let debugFile = null; // the start log's file, once the profile is known

function debug(text) {
  if (!DEBUG || !debugFile) return;
  try {
    fs.appendFileSync(debugFile, `${new Date().toISOString()} ${text}\n`);
  } catch {
    // the start log only
  }
}

function shown(url) { // an address for the start log: its code hidden
  const text = String(url || "");
  const at = text.indexOf("?");
  return at === -1 ? text : `${text.slice(0, at)}?code=…`;
}

function watchContents(contents) { // the start log: where each page and frame went, and how
  contents.on("did-navigate", (event, url, code) => debug(`did-navigate ${shown(url)} ${code}`));
  contents.on("did-frame-navigate", (event, url, code, status, isMainFrame) => {
    if (!isMainFrame) debug(`did-frame-navigate ${shown(url)} ${code}`);
  });
  contents.on("did-fail-load", (event, code, description, url, isMainFrame) =>
    debug(`did-fail-load ${shown(url)} ${code} ${description} ${isMainFrame ? "main" : "frame"}`));
  contents.on("render-process-gone", (event, details) => debug(`render-process-gone ${details && details.reason}`));
  contents.on("did-finish-load", () => {
    const where = own;
    if (!where) return;
    session.defaultSession.cookies.get({ url: where })
      .then((found) => debug(`did-finish-load ${shown(contents.getURL())}: cookies for `
                             + `${where}: ${found.map((cookie) => cookie.name).join(", ") || "none"}`))
      .catch((error) => debug(`did-finish-load: the cookies couldn't be read: ${error}`));
  });
}

// <home>/desktop/profile, beside the app; the packaged AI Browser.exe's app: <home>/desktop-profile, in the user's own
// folder (policy.profileFor). A test's unpackaged Electron: its own.
function profileFolder() {
  const given = process.argv.find((arg) => arg.startsWith(PROFILE));
  if (given && UNPACKAGED) return given.slice(PROFILE.length);
  return policy.profileFor({ execPath: process.execPath, platform: process.platform, env: process.env,
                             homedir: os.homedir(), cwd: process.cwd(), exists: fs.existsSync });
}

function openLine(onMessage, onEnd) {
  const feed = splitter(onMessage);
  let ended = false;
  const end = () => {
    if (!ended) {
      ended = true;
      debug("the line ended");
      onEnd();
    }
  };
  const where = lineOption(process.argv);
  if (where) { // the line the engine named: the Mac's socket, or Windows' port on 127.0.0.1 with its key
    const target = lineTarget(where, process.env);
    delete process.env[LINE_KEY]; // the key goes no further: no process the app starts inherits it
    if (!target) {
      debug("line: none it can join");
      end();
      return;
    }
    debug(`line: ${target.path ? "socket" : `${target.host}:${target.port}`}`);
    const socket = target.path ? net.createConnection({ path: target.path })
      : net.createConnection({ host: target.host, port: target.port });
    if (!target.path) socket.write(`${target.key}\n`); // first of all: the engine takes no line without its key
    socket.setEncoding("utf8");
    socket.on("connect", () => debug("line: joined"));
    socket.on("data", feed);
    socket.on("close", end);
    socket.on("error", (error) => debug(`line: ${error && error.code}`)); // "close" follows
    send = (message) => !socket.destroyed && socket.write(encode(message));
    return;
  }
  debug("line: stdin");
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

// No engine behind the app: its line ended, or no start came in time. When an `ai-browser app` started it and went
// away, the app quits quietly, before any window or menu-bar icon. Started by a double-click, it says how to start AI
// Browser (the packaged AI Browser.exe's app names that exe), after letting go of the single-instance lock: while the
// box is up, a real start is never blocked.
function noEngine() {
  const verdict = policy.withoutEngine({ line: lineOption(process.argv) !== null, start: starting });
  debug(`no engine: ${verdict}`);
  if (verdict === "quit") {
    engineQuit = true; // there is no one to tell
    if (started) app.quit();
    else app.exit(0);
    return;
  }
  starting = true; // a start message coming now is too late
  app.releaseSingleInstanceLock();
  const hint = policy.startHint(policy.packaged({ execPath: process.execPath, platform: process.platform,
                                                   exists: fs.existsSync }));
  app.whenReady().then(async () => {
    await dialog.showMessageBox({ type: "info", message: hint.message, detail: hint.detail, buttons: ["OK"] });
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

function kindOf(contents) { // which of our windows a page is in: "chat" for the floating chat's, else "main"
  const chat = windows.get("chat");
  return chat && chat.webContents === contents ? "chat" : "main";
}

function chatFile() {
  return path.join(app.getPath("userData"), CHAT_FILE);
}

function savedPlace() { // where the chat was last time; null when it never was, or the file can't be read
  try {
    return JSON.parse(fs.readFileSync(chatFile(), "utf8"));
  } catch {
    return null;
  }
}

function keepPlace() { // where the chat is now, for the next time (a write that fails only forgets it)
  clearTimeout(saving);
  saving = null;
  const win = windows.get("chat");
  if (!win) return;
  try {
    fs.writeFileSync(chatFile(), JSON.stringify(win.getBounds()), { mode: 0o600 });
  } catch {
    // the first-time place, next time
  }
}

function makeChat() { // the floating chat: small, above the other windows, where the user left it
  const areas = screen.getAllDisplays().map((display) => display.workArea);
  const win = makeWindow("chat", { ...policy.chatBounds(savedPlace(), areas), minWidth: policy.CHAT_SIZE.minWidth,
                                   minHeight: policy.CHAT_SIZE.minHeight,
                                   title: "AI Browser chat", alwaysOnTop: true, minimizable: false,
                                   maximizable: false, fullscreenable: false, skipTaskbar: true,
                                   backgroundColor: "#faf9f5", icon: ICON });
  win.on("close", (event) => { // closing it hides it, like the shortcut
    if (!quitting) {
      event.preventDefault();
      hideChat();
    }
  });
  for (const name of ["moved", "resized"]) {
    win.on(name, () => {
      clearTimeout(saving);
      saving = setTimeout(keepPlace, SAVE_AFTER);
    });
  }
  win.webContents.on("did-navigate", (event, url, code) => {
    chatLoaded = code === 200 && policy.mayNavigate(url, own, true, "chat");
  });
  return win;
}

function showChat() { // the floating chat comes forward; its page loads the first time, and again after a refusal
  if (!own) return;
  const win = windows.get("chat") || makeChat();
  if (!chatLoaded) win.loadURL(own + policy.CHAT_PATH).catch(() => {});
  if (!win.isVisible() || !win.isFocused()) chatFrom = BrowserWindow.getFocusedWindow() === null;
  showWindow("chat");
}

function hideChat() { // the chat goes, and keeps its place; on a Mac, the app that was in front comes back
  const win = windows.get("chat");
  if (!win || !win.isVisible()) return;
  keepPlace();
  win.hide();
  if (process.platform === "darwin" && chatFrom) app.hide();
}

function toggleChat() { // the shortcut: the floating chat comes forward, or hides when it is the window in front
  if (!pressed) {
    pressed = true; // it works: Settings says so
    send({ type: "shortcut", value: shortcut, ok: true, why: "", pressed: true });
  }
  const win = windows.get("chat");
  if (win && win.isVisible() && win.isFocused()) hideChat();
  else showChat();
}

// The bridge's "chat": AI Browser's pages may show the chat, and the chat hides itself.
function chatAction(sender, what) {
  if (what === "show") showChat();
  else if (what === "hide") hideChat();
  return null;
}

// The bridge's "thisPage": which Brave tab the user is on. Only the chat's own page gets an answer, and only while
// the chat shows: nothing reads Brave's tab in the background. One look at a time: an ask while one runs gets its
// answer.
function thisPageAction(sender) {
  const chat = windows.get("chat");
  if (!chat || sender !== chat.webContents || !chat.isVisible()) return { state: "hidden" };
  if (!looking) looking = thispage.read(process.platform, pageRunner()).finally(() => { looking = null; });
  return looking;
}

// The bridge's "chooseFolder": the system's folder dialog, over the window that asked, for a task's folder (agent
// powers). The user's pick as a path, or null when they cancel. answerActions has checked that the page is one of AI
// Browser's own top-level pages; only the tab menu (which asks for AI Home and Mission Control in its frames) and the
// floating chat get a dialog. One at a time: an ask while one is open gets its answer.
function chooseFolderAction(sender) {
  const win = BrowserWindow.fromWebContents(sender);
  if (!win || (win !== windows.get("main") && win !== windows.get("chat"))) return null;
  if (!choosing) {
    choosing = dialog.showOpenDialog(win, { title: "Choose a folder for this task", buttonLabel: "Choose",
                                            properties: ["openDirectory", "createDirectory"] })
      .then((result) => (!result.canceled && typeof result.filePaths?.[0] === "string" ? result.filePaths[0] : null))
      .catch(() => null)
      .finally(() => { choosing = null; });
  }
  return choosing;
}

// The real osascript or PowerShell. A test's unpackaged Electron alone may name a file (--aib-fake-page) whose text
// stands in for what they would print: the packaged app never reads one, and no test reads the user's Brave.
function pageRunner() {
  const given = process.argv.find((arg) => arg.startsWith(FAKE_PAGE));
  if (!given || !UNPACKAGED) return thispage.run;
  const file = given.slice(FAKE_PAGE.length);
  return async () => ({ error: "", stdout: fs.readFileSync(file, "utf8"), stderr: "" });
}

function useShortcut(value, request) { // move the global shortcut, and tell the engine how it went
  const result = policy.moveShortcut(globalShortcut, shortcut, value, toggleChat);
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
      if (!policy.mayNavigate(details.url, own, details.isMainFrame, kindOf(contents))) {
        debug(`${name} refused: ${shown(details.url)}`);
        details.preventDefault();
      }
    });
  }
  if (DEBUG) watchContents(contents);
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
    { label: "Show chat", click: () => showChat() }, // works whatever the shortcut, even one another app holds
    { type: "separator" },
    { label: "Quit", click: () => app.quit() },
  ]));
  if (process.platform === "win32") tray.on("click", () => showWindow("main"));
}

// Windows: the Start menu entry its notifications need (policy.startMenuEntry, which never throws). Started from that
// entry, the app says how to start AI Browser.
function startMenuEntry() {
  if (UNPACKAGED) return;
  debug(`Start menu entry: ${policy.startMenuEntry(app, shell, process.execPath)}`);
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
      return handler(event.sender, ...args);
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
  debug(`loadURL ${shown(message.open)}`);
  win.loadURL(message.open)
    .then(() => debug(`loadURL done: ${shown(message.open)}`))
    .catch((error) => debug(`loadURL failed: ${error && (error.code || error.message)}`)); // the engine says so
  const said = send({ type: "hello", pid: process.pid });
  debug(said === false ? "hello not sent" : "hello sent");
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
  if (DEBUG) debugFile = path.join(profile, DEBUG_FILE);
  debug(`profile ${profile}`);
  if (!app.requestSingleInstanceLock()) {
    debug("single-instance lock: another copy holds it");
    app.exit(0); // one app per profile: the running one comes forward instead (second-instance)
    return;
  }
  debug("single-instance lock: held");
  app.on("second-instance", () => showWindow("main"));
  app.on("activate", () => showWindow("main")); // a click on the Dock icon
  app.on("before-quit", () => {
    quitting = true;
    keepPlace(); // the chat's place, if it has one
    if (!engineQuit) send({ type: "quit" });
  });
  app.on("will-quit", () => globalShortcut.unregisterAll());
  app.on("window-all-closed", () => {}); // only Quit ends the app
  app.on("web-contents-created", (event, contents) => lockContents(contents));
  const waiting = setTimeout(noEngine, START_WAIT);
  openLine((message) => {
    if (message.type === "start" && !starting) {
      debug("start received");
      starting = true;
      clearTimeout(waiting);
      app.whenReady().then(() => begin(message)).catch((error) => { // a broken start: the engine hears it
        debug(`start failed: ${error}`);
        app.exit(1);
      });
    } else if (started) {
      onEngine(message);
    }
  }, () => {
    clearTimeout(waiting);
    noEngine(); // the engine is gone: quit (test_desktop_js runs these under a stand-in Electron)
  });
  app.whenReady().then(() => {
    debug("ready");
    if (DEBUG) { // the session exists only once the app is ready
      session.defaultSession.cookies.on("changed", (event, cookie, cause, removed) =>
        debug(`cookie ${removed ? "removed" : "set"}: ${cookie.name} (${cause})`));
    }
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
