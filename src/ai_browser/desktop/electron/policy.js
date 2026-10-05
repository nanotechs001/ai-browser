// What AI Browser's own app allows, as small functions main.js calls (and the tests run under Node.js): where a frame
// may go, which permission a page may have, which global shortcuts there are and how one is moved, what a
// notification may say, and which switches the packaged app refuses. Nothing here touches Electron, the network or
// the disk.
"use strict";

const LIVE_PORTS = [8770, 8790]; // an engine's live view binds one of these (config.LIVE_PORTS)
const LIVE = /^http:\/\/127\.0\.0\.1:(\d{4})\/live\?token=[A-Za-z0-9_-]{1,64}$/;
const SHORTCUTS = ["Alt+Space", "Alt+Shift+Space", "Control+Shift+Space"]; // desktop/shortcut.py's, in its order
const DEBUG_SWITCHES = ["remote-debugging-port", "remote-debugging-pipe", "remote-debugging-address",
  "remote-allow-origins", "inspect", "inspect-brk", "inspect-port", "js-flags", "auto-open-devtools-for-tabs"];
const NOTE_ID = /^n\d{1,9}$/;
const TITLE_LIMIT = 120;
const BODY_LIMIT = 240;
const CONTROL = /[\u0000-\u001f\u007f]/g;

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
// engine's live view. Anything else stays where it was: a website link goes to the user's own browser through the
// engine (open_url), never into this window. Before the engine's start (no `own`), nothing loads.
function mayNavigate(url, own, isMainFrame) {
  if (typeof own !== "string" || !own) return false;
  if (originOf(url) === own) return true;
  return isMainFrame === false && isLiveView(url);
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

module.exports = {
  DEBUG_SWITCHES, LIVE_PORTS, SHORTCUTS, isLiveView, mayCheck, mayNavigate, mayRequest, moveShortcut, notice,
  originOf, shortcutOk, startOrigin, withoutEngine,
};
