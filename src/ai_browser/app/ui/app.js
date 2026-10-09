// AI Browser's window: one page with a row of tabs under the title bar (AI Home, Mission Control, Settings) over one
// frame per tab. A tab's page loads the first time the tab is picked, and is then only hidden, never reloaded, so
// nothing in it resets: a half-typed message, the scroll, Mission Control's room. The setup steps and an agent's live
// view (Show me) open as closable tabs at the end, one live view per agent. Our pages ask for a tab with a message
// (nav.js); only a message from one of our own pages' frames counts, and only for one of our pages or an engine's
// live view. Each page in a frame keeps its own line to the app, and those lines are the window's: the app ends when
// the window closes (app/run.py), never on a switch or a closed tab. The close-tab key (Command-W on a Mac, Ctrl+W
// elsewhere) closes the tab shown if it has a ×, and never the window: this page and our pages keep it from the
// browser. The window's title follows the active tab and keeps Mission Control's count of agents at work. Every label is set
// as text. A page of ours may also ask for the system's folder dialog (agent powers): the tab menu asks AI Browser's
// own app, and answers that page alone.
import { closeTabKey } from "./nav.js";

const FIXED = [["/home", "AI Home"], ["/mission", "Mission Control"], ["/settings", "Settings"]];
const SETUP = "/setup"; // the setup steps (#brave, #switch): one closable tab
const LIVE = /^http:\/\/127\.0\.0\.1:\d{1,5}\/live\?token=[A-Za-z0-9_-]{1,64}$/; // an engine's live view, nothing else
const AGENT = /^a\d{1,9}$/;
const COUNT = /^\((\d+)\) /; // Mission Control's own title while agents work: "(2) Mission Control"
const LABEL_LIMIT = 80;
const SECTION = /^#[a-z][a-z0-9-]{0,40}$/; // a page's section ("#accounts-section"): passed on to its fixed tab
const $ = (id) => document.getElementById(id);
const tabs = new Map(); // key -> {key, label, src, closable, live, node, button, view, frame}
let active = null;
let picked = []; // the keys shown, latest last: closing the active tab goes back to the one before

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function addTab(key, label, src, { closable = false, live = false } = {}) {
  const node = el("div", "tab");
  node.dataset.key = key;
  const button = el("button", "tab-label", label);
  button.type = "button";
  button.title = label;
  button.addEventListener("click", () => show(key));
  node.append(button);
  if (closable) {
    const close = el("button", "tab-close", "×");
    close.type = "button";
    close.title = `Close ${label}`;
    close.setAttribute("aria-label", `Close ${label}`);
    close.addEventListener("click", () => closeTab(key));
    node.append(close);
  }
  $("tabs").append(node);
  const tab = { key, label, src, closable, live, node, button, view: null, frame: null };
  tabs.set(key, tab);
  return tab;
}

function load(tab, hash = "") { // the tab's frame, made the first time it is shown (at a section, if asked)
  const view = el("div", "view");
  view.dataset.key = tab.key;
  const frame = el("iframe");
  frame.title = tab.label;
  if (tab.live) frame.setAttribute("sandbox", "allow-scripts"); // another origin's page: no way out of its frame
  if (tab.key === "/mission") frame.allow = "microphone"; // talking to the Brain
  if (tab.key === "/mission") frame.addEventListener("load", () => watchCount(frame));
  frame.addEventListener("load", () => { // the page that loaded hears whether its tab is in front: show()'s word
    frame.contentWindow?.postMessage({ type: "shown", on: active === tab.key }, location.origin); // went to about:blank
  });
  frame.src = tab.src + hash;
  view.append(frame);
  $("views").append(view);
  tab.view = view;
  tab.frame = frame;
}

function show(key, hash = "") {
  const tab = tabs.get(key);
  if (!tab) return;
  if (!tab.frame) load(tab, hash);
  else if (hash) tab.frame.contentWindow?.location.replace(tab.src + hash); // the same page: only its section moves
  active = key;
  picked = [...picked.filter((one) => one !== key), key];
  for (const one of tabs.values()) {
    const on = one === tab;
    one.node.classList.toggle("active", on);
    if (on) one.button.setAttribute("aria-current", "page");
    else one.button.removeAttribute("aria-current");
    one.view?.classList.toggle("active", on);
  }
  // Our pages pause while hidden. The one in front hears it first: a hand-off's card is never unseen in between.
  for (const one of [tab, ...[...tabs.values()].filter((other) => other !== tab)]) {
    one.frame?.contentWindow?.postMessage({ type: "shown", on: one === tab }, location.origin);
  }
  renderTitle();
  tab.frame.contentWindow?.focus(); // keys go to the page shown (Mission Control's Space to talk, Escape, arrows)
}

function closeTab(key) {
  const tab = tabs.get(key);
  if (!tab?.closable) return;
  tab.node.remove();
  tab.view?.remove(); // its page ends, and any line it had with it
  tabs.delete(key);
  picked = picked.filter((one) => one !== key);
  if (active === key) show(picked.at(-1) || "/home");
}

// The close-tab key: the tab shown, if it has a ×; on AI Home, Mission Control or Settings, nothing.
function closeShown() {
  if (tabs.get(active)?.closable) closeTab(active);
}

document.addEventListener("keydown", (event) => { // the focus is on this page itself (its row of tabs)
  if (!closeTabKey(event)) return;
  event.preventDefault(); // never the browser's: in this window it would close the window, and stop AI Browser
  if (!event.repeat) closeShown();
}, true);

function openClosable(key, label, src, options) { // a closable tab: opened once, then shown again (at `src`)
  const tab = tabs.get(key) || addTab(key, label, src, { closable: true, ...options });
  if (tab.frame && tab.src !== src) {
    tab.src = src;
    tab.frame.src = src; // the setup steps' other section, or a new live view of the same agent
  }
  show(key);
}

function openPage(path) { // one of our pages, by its path and #section: its fixed tab, or the setup steps' own
  if (typeof path !== "string") return;
  let url;
  try {
    url = new URL(path, location.href);
  } catch {
    return;
  }
  if (url.origin !== location.origin) return;
  if (FIXED.some(([key]) => key === url.pathname)) show(url.pathname, SECTION.test(url.hash) ? url.hash : "");
  else if (url.pathname === SETUP) openClosable(SETUP, "Setup", SETUP + url.hash);
}

function openLive({ url, agent, label }) { // an agent's live view: its own closable tab, one per agent
  if (typeof url !== "string" || !LIVE.test(url) || typeof agent !== "string" || !AGENT.test(agent)) return;
  const name = (typeof label === "string" ? label.replace(/\s+/g, " ").trim() : "").slice(0, LABEL_LIMIT) || agent;
  openClosable(`live:${agent}`, `Live view · ${name}`, url, { live: true });
}

// A page of ours asks for a tab, or passes on the close-tab key. Only our own pages' frames count: never the window's
// page itself, a live view (another origin), or anything else that can post a message here; and only the page shown
// passes on the key.
// A page in a frame asks for the system's folder dialog (agent powers). Only this page, the window's top-level one,
// may open it: AI Browser's own app answers window.aib.chooseFolder for top-level pages alone. The answer goes back to
// that frame only: the path picked, null when cancelled, or typed: true where there is no dialog (a browser's window).
async function chooseFolder(from, id) {
  let path;
  try {
    path = typeof window.aib?.chooseFolder === "function" ? await window.aib.chooseFolder() : undefined;
  } catch {
    path = null;
  }
  from.frame?.contentWindow?.postMessage({ type: "folder-chosen", id, path: typeof path === "string" ? path : null,
                                           typed: path === undefined }, location.origin);
}

addEventListener("message", (event) => {
  if (event.origin !== location.origin) return;
  const from = [...tabs.values()].find((tab) => tab.frame && tab.frame.contentWindow === event.source);
  if (!from || from.live) return;
  const message = event.data;
  if (message?.type === "tab") openPage(message.path);
  else if (message?.type === "live") openLive(message);
  else if (message?.type === "choose-folder" && typeof message.id === "string" && message.id.length <= 80) {
    chooseFolder(from, message.id);
  }
  else if (message?.type === "close-tab" && from.key === active) closeShown();
});

function working() { // Mission Control's count of agents at work, from its own title ("" when none)
  try {
    return COUNT.exec(tabs.get("/mission")?.frame?.contentDocument?.title || "")?.[1] || "";
  } catch {
    return "";
  }
}

function renderTitle() {
  const count = working();
  document.title = `${count ? `(${count}) ` : ""}${tabs.get(active)?.label || "AI Home"} · AI Browser`;
}

function watchCount(frame) { // Mission Control sets its title as agents start and stop: the window's title follows
  const head = frame.contentDocument?.head;
  if (head) new MutationObserver(renderTitle).observe(head, { subtree: true, childList: true, characterData: true });
  renderTitle();
}

for (const [key, label] of FIXED) addTab(key, label, key);
show("/home");
