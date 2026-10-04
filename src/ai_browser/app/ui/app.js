// AI Browser's window: one page with a row of tabs under the title bar (AI Home, Mission Control, Settings) over one
// frame per tab. A tab's page loads the first time the tab is picked, and is then only hidden, never reloaded, so
// nothing in it resets: a half-typed message, the scroll, Mission Control's room. Each page in a frame keeps its own
// line to the app, and those lines are the window's: the app ends when the window closes (app/run.py), never on a
// switch. The window's title follows the active tab and keeps AI Home's count of agents at work. Labels are text.
"use strict";

const FIXED = [["/home", "AI Home"], ["/mission", "Mission Control"], ["/settings", "Settings"]];
const COUNT = /^\((\d+)\) /; // AI Home's own title while agents work: "(2) AI Home"
const $ = (id) => document.getElementById(id);
const tabs = new Map(); // key -> {key, label, src, node, button, view, frame}
let active = null;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function addTab(key, label, src) {
  const node = el("div", "tab");
  node.dataset.key = key;
  const button = el("button", "tab-label", label);
  button.type = "button";
  button.title = label;
  button.addEventListener("click", () => show(key));
  node.append(button);
  $("tabs").append(node);
  const tab = { key, label, src, node, button, view: null, frame: null };
  tabs.set(key, tab);
  return tab;
}

function load(tab) { // the tab's frame, made the first time it is shown
  const view = el("div", "view");
  view.dataset.key = tab.key;
  const frame = el("iframe");
  frame.title = tab.label;
  if (tab.key === "/mission") frame.allow = "microphone"; // talking to the Brain
  if (tab.key === "/home") frame.addEventListener("load", () => watchCount(frame));
  frame.src = tab.src;
  view.append(frame);
  $("views").append(view);
  tab.view = view;
  tab.frame = frame;
}

function show(key) {
  const tab = tabs.get(key);
  if (!tab) return;
  if (!tab.frame) load(tab);
  active = key;
  for (const one of tabs.values()) {
    const on = one === tab;
    one.node.classList.toggle("active", on);
    if (on) one.button.setAttribute("aria-current", "page");
    else one.button.removeAttribute("aria-current");
    one.view?.classList.toggle("active", on);
  }
  renderTitle();
  tab.frame.contentWindow?.focus(); // keys go to the page shown (Mission Control's Space to talk, Escape, arrows)
}

function working() { // AI Home's count of agents at work, from its own title ("" when none)
  try {
    return COUNT.exec(tabs.get("/home")?.frame?.contentDocument?.title || "")?.[1] || "";
  } catch {
    return "";
  }
}

function renderTitle() {
  const count = working();
  document.title = `${count ? `(${count}) ` : ""}${tabs.get(active)?.label || "AI Home"} · AI Browser`;
}

function watchCount(frame) { // AI Home sets its title as agents start and stop: the window's title follows
  const head = frame.contentDocument?.head;
  if (head) new MutationObserver(renderTitle).observe(head, { subtree: true, childList: true, characterData: true });
  renderTitle();
}

for (const [key, label] of FIXED) addTab(key, label, key);
show("/home");
