// What AI Browser's own app allows, as small functions main.js calls (and the tests run under Node.js): where a frame
// may go, which permission a page may have, which global shortcuts there are and how one is moved, what a
// notification may say, which switches the packaged app refuses, where the floating chat opens, where the app keeps
// its profile, and its Start menu entry. Nothing here touches Electron, the network or the disk, except through what
// main.js hands over (profileFor's look at the disk, startMenuEntry's app and shell).
"use strict";

const path = require("node:path");

const LIVE_PORTS = [8770, 8790]; // an engine's live view binds one of these (config.LIVE_PORTS)
const APP_ID = "io.github.nanotechs001.ai-browser"; // desktop/layout.py's BUNDLE_ID, and Windows' AppUserModelID
const TOAST_CLSID = "{52E8D68C-5CAC-4680-848A-E80657E0B4D5}"; // Windows: the Start menu entry's toast activator
const LIVE = /^http:\/\/127\.0\.0\.1:(\d{4})\/live\?token=[A-Za-z0-9_-]{1,64}$/;
const SHORTCUTS = ["Alt+Space", "Alt+Shift+Space", "Control+Shift+Space"]; // desktop/shortcut.py's, in its order
const DEBUG_SWITCHES = ["remote-debugging-port", "remote-debugging-pipe", "remote-debugging-address",
  "remote-allow-origins", "inspect", "inspect-brk", "inspect-port", "js-flags", "auto-open-devtools-for-tabs"];
const NOTE_ID = /^n\d{1,9}$/;
const TITLE_LIMIT = 120;
const BODY_LIMIT = 240;
const CONTROL = /[\u0000-\u001f\u007f]/g;
const CHAT_PATH = "/chat"; // the floating chat's page: its window shows this one page and nothing else
const CHAT_SIZE = Object.freeze({ width: 380, height: 560, minWidth: 320, minHeight: 360 });
const CHAT_EDGE = 16; // px between the chat and the main screen's right edge, the first time
const CHAT_TOP = 48; // px below the top of the main screen's work area, the first time
const TITLE_BAR = 28; // px: the chat's title bar, which must stay on a screen so it can be dragged back
const ON_SCREEN = 64; // px of the title bar's width that must be on one screen
const LARGEST = 4000; // px: the most a remembered width or height may be

function originOf(url) { // an http(s) address's origin, or null
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.origin : null;
  } catch {
    return null;
  }
}

// The app's own origin, from the start address the engine sent: http://127.0.0.1:<port>/open?code=…, nothing else.
function startOrigin(open) {
  let url;
  try {
    url = new URL(open);
  } catch {
    return null;
  }
  const ours = url.protocol === "http:" && url.hostname === "127.0.0.1" && url.port !== "" && url.pathname === "/open"
    && url.username === "" && url.password === "";
  return ours ? url.origin : null;
}

function isLiveView(url) { // an engine's live view (the tab menu shows one in a frame), on its own ports only
  const found = typeof url === "string" ? LIVE.exec(url) : null;
  return found !== null && Number(found[1]) >= LIVE_PORTS[0] && Number(found[1]) <= LIVE_PORTS[1];
}

// A frame may load AI Browser's own pages only; a frame inside our page (never the window itself) may also show an
// engine's live view. The floating chat's window (`kind` "chat") shows its one page, /chat, and nothing else, in no
// frame. Anything else stays where it was: a website link goes to the user's own browser through the engine
// (open_url), never into a window of ours. Before the engine's start (no `own`), nothing loads.
function mayNavigate(url, own, isMainFrame, kind = "main") {
  if (typeof own !== "string" || !own) return false;
  if (kind === "chat") return isMainFrame !== false && isChatPage(url, own);
  if (originOf(url) === own) return true;
  return isMainFrame === false && isLiveView(url);
}

function isChatPage(url, own) { // own + /chat, a #part allowed; no query, no user name, no other address
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return false;
  }
  return parsed.origin === own && parsed.pathname === CHAT_PATH && parsed.search === "" && parsed.username === ""
    && parsed.password === "";
}

function isRect(value) {
  return Boolean(value) && typeof value === "object"
    && ["x", "y", "width", "height"].every((key) => Number.isFinite(value[key])) && value.width > 0 && value.height > 0;
}

function shared(a, b) { // the width and the height two rectangles have in common (negative: none)
  return [Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x),
          Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y)];
}

// Where the floating chat opens. `areas`: each screen's work area, the main screen first. `saved`: where the user left
// it (chat.json). It opens there, at its size kept within limits, while ON_SCREEN px of its title bar are still on one
// screen. Else it opens at the main screen's right edge, near the top, at the default size. Always whole pixels.
function chatBounds(saved, areas) {
  const screens = (Array.isArray(areas) ? areas : []).filter(isRect);
  const first = screens[0] || { x: 0, y: 0, width: 1280, height: 800 };
  if (isRect(saved)) {
    const place = { x: Math.round(saved.x), y: Math.round(saved.y),
                    width: Math.round(Math.min(Math.max(saved.width, CHAT_SIZE.minWidth), LARGEST)),
                    height: Math.round(Math.min(Math.max(saved.height, CHAT_SIZE.minHeight), LARGEST)) };
    const bar = { x: place.x, y: place.y, width: place.width, height: TITLE_BAR };
    const seen = screens.some((area) => {
      const [wide, tall] = shared(bar, area);
      return wide >= ON_SCREEN && tall >= TITLE_BAR / 2;
    });
    if (seen) return place;
  }
  const width = Math.min(CHAT_SIZE.width, Math.round(first.width));
  const height = Math.min(CHAT_SIZE.height, Math.round(first.height));
  return { x: Math.round(Math.max(first.x, first.x + first.width - width - CHAT_EDGE)),
           y: Math.round(first.y + CHAT_TOP), width, height };
}

// A permission request (setPermissionRequestHandler): the microphone alone (talking to the Brain), and writing to the
// clipboard (the Copy buttons), for AI Browser's own pages only. Everything else is refused, for everyone.
function mayRequest(permission, details, own) {
  if (!own || originOf(details?.requestingUrl) !== own) return false;
  if (permission === "media") {
    const types = Array.isArray(details?.mediaTypes) ? details.mediaTypes : [];
    return types.length > 0 && types.every((type) => type === "audio");
  }
  return permission === "clipboard-sanitized-write";
}

// The quiet check before a request (setPermissionCheckHandler, navigator.permissions.query): the same answers.
function mayCheck(permission, requestingOrigin, details, own) {
  if (!own || originOf(requestingOrigin) !== own) return false;
  if (permission === "media") return details?.mediaType === "audio";
  return permission === "clipboard-sanitized-write";
}

function shortcutOk(value) {
  return value === null || SHORTCUTS.includes(value);
}

function tryRegister(keys, accelerator, onPress) {
  try {
    return keys.register(accelerator, onPress) === true;
  } catch {
    return false;
  }
}

// Moving the global shortcut from `current` to `next`. When another app holds `next`, the one before comes back, so
// nothing is lost by trying. `keys` is Electron's globalShortcut (or a test's stand-in). `registered` is what the app
// holds afterwards.
function moveShortcut(keys, current, next, onPress) {
  if (!shortcutOk(next)) return { registered: current, ok: false, why: "unknown" };
  if (current) keys.unregister(current);
  if (next === null) return { registered: null, ok: true, why: "" };
  if (tryRegister(keys, next, onPress)) return { registered: next, ok: true, why: "" };
  const back = current && tryRegister(keys, current, onPress) ? current : null;
  return { registered: back, ok: false, why: "taken" };
}

// A notification exactly as the engine wrote it: its id, a title and a body, as plain text, cut to length. Nothing
// else reaches the screen. null when it isn't one.
function notice(message) {
  if (!message || typeof message.id !== "string" || !NOTE_ID.test(message.id)) return null;
  const text = (value, limit) => (typeof value === "string" ? value : "").replace(CONTROL, " ").trim().slice(0, limit);
  const title = text(message.title, TITLE_LIMIT);
  return title ? { id: message.id, title, body: text(message.body, BODY_LIMIT) } : null;
}

// The app with no engine behind it (its line ended, or no start came in time). An `ai-browser app` started it (it
// named a line, or sent its start) and went away: "quit", quietly, with no box and no window. Nothing started it (a
// double-click in Finder or the Start menu): "box", which says to start AI Browser from a terminal.
function withoutEngine({ line, start }) {
  return line || start ? "quit" : "box";
}

// Whether the app is the one shipped beside the packaged AI Browser.exe (the Windows test build): its folder is the
// `desktop` folder beside that program, whose PyInstaller bundle (_internal) is there too. desktop/layout.py's
// bundled() says the same from the engine's side.
function packaged({ execPath, platform, exists }) {
  const folder = appFolder(execPath, platform);
  return path.basename(folder) === "desktop" && exists(path.join(path.dirname(folder), "_internal"));
}

function appFolder(execPath, platform) { // <home>/desktop, or <the packaged exe's folder>/desktop
  return path.resolve(execPath, ...(platform === "darwin" ? ["..", "..", "..", ".."] : ["..", ".."]));
}

// The app's profile (userData), as desktop/layout.py's profile() says: beside the app doctor --setup built in
// <home>/desktop; for the packaged AI Browser.exe's, <home>/desktop-profile in the user's own folder, the home the
// engine uses ($AIB_HOME, else ~/.ai-browser), so it works wherever the zip was unzipped and a new copy keeps the
// sign-in. `exists` looks at the disk; homedir and cwd are the user's home folder and the working folder.
function profileFor({ execPath, platform, env, homedir, cwd, exists }) {
  if (!packaged({ execPath, platform, exists })) return path.join(appFolder(execPath, platform), "profile");
  let home = env.AIB_HOME !== undefined ? env.AIB_HOME : "~/.ai-browser"; // config.home()
  if (home === "~") home = homedir;
  else if (home.startsWith("~/") || home.startsWith("~\\")) home = path.join(homedir, home.slice(2));
  return path.join(path.resolve(cwd, home), "desktop-profile");
}

// Windows shows an app's notifications only when the Start menu has a shortcut to it with the same AppUserModelID and
// toast activator (setup's offer says so). The entry, made or mended with Electron's `app` and `shell`: "made",
// "kept", or why not ("failed: …"). It never throws: begin() makes it first, and a Start menu that can't be found or
// written costs only the notifications, never the start (an AppData Windows couldn't find: run 37311955729).
function startMenuEntry(app, shell, execPath) {
  try {
    app.setAppUserModelId(APP_ID);
    if (typeof app.setToastActivatorCLSID === "function") app.setToastActivatorCLSID(TOAST_CLSID); // where it exists
    const link = path.join(app.getPath("appData"), "Microsoft", "Windows", "Start Menu", "Programs",
                           "AI Browser.lnk");
    const want = { target: execPath, appUserModelId: APP_ID, toastActivatorClsid: TOAST_CLSID,
                   description: "AI Browser" };
    let have = null;
    try {
      have = shell.readShortcutLink(link);
    } catch {
      have = null; // none yet
    }
    if (have && have.target === want.target && have.appUserModelId === APP_ID) return "kept";
    return shell.writeShortcutLink(link, have ? "replace" : "create", want) ? "made" : "failed: not written";
  } catch (error) {
    return `failed: ${error && error.message}`;
  }
}

// What a double-click on the app itself says (no engine started it): how to start AI Browser.
function startHint(fromPackagedExe) {
  return fromPackagedExe
    ? { message: "Start AI Browser with AI Browser.exe",
        detail: "Double-click AI Browser.exe, in the folder this app came in: it opens this app." }
    : { message: "Start AI Browser from a terminal", detail: "Run: uv run ai-browser app" };
}

module.exports = {
  CHAT_PATH, CHAT_SIZE, DEBUG_SWITCHES, LIVE_PORTS, SHORTCUTS, chatBounds, isLiveView, mayCheck, mayNavigate,
  mayRequest, moveShortcut, notice, originOf, packaged, profileFor, shortcutOk, startHint, startMenuEntry, startOrigin,
  withoutEngine,
};
