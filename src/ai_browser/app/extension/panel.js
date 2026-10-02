// The chat beside the page. It shows the agent working in the tab you are looking at; on a tab without one, what
// you type starts an agent right there (in your tab, which it never closes). On AI Home it shows the agent that was
// active last. Everything from Claude or from pages is set as text, never parsed as HTML.
import { checkCard } from "./check.js";
import { connect, targetOfTab } from "./link.js";
import { createChat } from "./chat.js";
import { permissionCard } from "./permission.js";

const $ = (id) => document.getElementById(id);
const HOME = chrome.runtime.getURL("home.html");
const COLORS = { grey: "#5f6368", blue: "#1a73e8", red: "#d93025", yellow: "#f9ab00", green: "#188038",
                 pink: "#d01884", purple: "#a142f4", cyan: "#007b83", orange: "#fa903e" };
const agents = new Map();
const activity = new Map(); // agent id -> when something last happened to it
let tab = null; // the tab beside the panel
let target = null; // its DevTools target id
let shown = null; // the agent shown
let pending = null; // a new_task waiting for its agent
let defaultModel = "sonnet";
let storedModel = false; // the user picked a model here before: it wins over the app's default
const chat = createChat($("messages"), { onPage: (page) => { $("page").textContent = page; } });
const link = connect({ view: "panel", onMessage: handle, onState: setStatus });

function setStatus(state) {
  $("status").dataset.state = state;
  $("status").title = { connected: "Connected to ai-browser app", connecting: "Connecting…" }[state]
    || "Not connected: is `ai-browser app` running?";
}

function flash(text) {
  $("hint").textContent = text;
  setTimeout(() => { if ($("hint").textContent === text) $("hint").textContent = ""; }, 4000);
}

function browserPage(url) {
  return !url || url.startsWith(HOME) || /^(chrome|chrome-extension|devtools|about|edge|brave):/i.test(url);
}

function newestFirst(a, b) {
  return Number(b.id.slice(1)) - Number(a.id.slice(1));
}

function agentForTab() {
  if (target) {
    const here = [...agents.values()].filter((agent) => agent.working_tab === target
      || (agent.tabs || []).includes(target) || (agent.adopted || []).includes(target));
    if (here.length) return here.sort(newestFirst)[0];
  }
  if (!tab || browserPage(tab.url)) { // AI Home or a browser page: the agent active last
    return [...agents.values()].sort((a, b) => (activity.get(b.id) || 0) - (activity.get(a.id) || 0))[0] || null;
  }
  return null;
}

function show() {
  const agent = agentForTab();
  const id = agent ? agent.id : null;
  if (id !== shown) {
    shown = id;
    chat.reset(agent ? "Loading…" : "");
    $("page").textContent = "";
    if (id) link.send({ type: "events", id });
  }
  const startHere = !agent && !!tab && !browserPage(tab.url);
  $("start-here").hidden = !startHere;
  $("messages").hidden = startHere;
  $("agent-name").textContent = agent ? agent.name : "AI Browser";
  $("agent-dot").hidden = !agent;
  if (agent) $("agent-dot").style.background = COLORS[agent.color] || "var(--muted)";
  $("stop").hidden = !(agent && (agent.state === "working" || agent.state === "waiting" || agent.check));
  const check = agent?.check; // a bot check waiting for the user: the same card, above the composer
  const checkSlot = $("check-slot");
  if (!check) checkSlot.replaceChildren();
  else if (checkSlot.firstChild?.dataset.since !== String(check.since)) {
    checkSlot.replaceChildren(checkCard(agent, (message) => link.send(message)));
  }
  const asking = agent?.permission; // its tool request waiting for the user: the card above the composer
  const slot = $("permission-slot");
  if (!asking) slot.replaceChildren();
  else if (slot.firstChild?.dataset.request !== asking.request) {
    slot.replaceChildren(permissionCard({ ...asking, agent: agent.id }, (message) => link.send(message), agent.name));
  }
  $("model").value = agent ? agent.model : defaultModel;
  $("input").placeholder = agent ? `Message ${agent.name}` : "Start a task in this tab";
  if (!agent && !startHere && !$("messages").textContent) {
    chat.reset("Open a page and start a task beside it, or start one in AI Home.");
  }
}

async function refreshTab() {
  try {
    const [active] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    tab = active || null;
    target = tab && !browserPage(tab.url) ? await targetOfTab(tab.id) : null;
  } catch {
    tab = null;
    target = null;
  }
  show();
}

function handle(message) {
  switch (message.type) {
    case "snapshot":
      agents.clear();
      for (const agent of message.agents) agents.set(agent.id, agent);
      if (!storedModel && message.default_model) defaultModel = message.default_model;
      shown = null; // a new connection: draw the conversation again
      show();
      break;
    case "agent":
      agents.set(message.agent.id, message.agent);
      activity.set(message.agent.id, Date.now());
      show();
      break;
    case "agent_closed":
      agents.delete(message.id);
      show();
      break;
    case "agent_event":
      activity.set(message.id, Date.now());
      if (message.id === shown) chat.append(message.event);
      break;
    case "agent_events":
      if (message.id === shown) {
        chat.reset();
        for (const event of message.events) chat.append(event);
      }
      break;
    case "created":
      if (pending && message.request === pending) pending = null;
      break;
    case "error":
      if (message.text) flash(message.text);
      break;
  }
}

function send(text) {
  const message = (text ?? $("input").value).trim();
  if (!message) return;
  const page = tab && !browserPage(tab.url) ? { url: tab.url, title: tab.title || "" } : {};
  let sent;
  if (shown) {
    sent = link.send({ type: "send", id: shown, text: message, tab: page });
  } else {
    if (pending) return; // one task per Send
    pending = `p${Date.now()}`;
    sent = link.send({ type: "new_task", text: message, skills: [], model: $("model").value,
      adopt: target || undefined, tab: page, request: pending });
    setTimeout(() => { pending = null; }, 10000);
    if (!sent) pending = null;
  }
  if (!sent) {
    flash("Not connected: is `ai-browser app` running?");
    return;
  }
  $("input").value = "";
}

$("send").addEventListener("click", () => send());
$("input").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    send();
  }
});
$("stop").addEventListener("click", () => shown && link.send({ type: "stop", id: shown }));
$("model").addEventListener("change", () => {
  if (shown) {
    link.send({ type: "model", id: shown, model: $("model").value });
  } else {
    defaultModel = $("model").value;
    chrome.storage.local.set({ model: defaultModel }).catch(() => {});
  }
});
$("home").addEventListener("click", async () => {
  const tabs = await chrome.tabs.query({}).catch(() => []);
  const home = tabs.find((each) => (each.url || each.pendingUrl || "").startsWith(HOME));
  if (home) chrome.tabs.update(home.id, { active: true }).catch(() => {});
  else chrome.tabs.create({ url: HOME }).catch(() => {});
});
$("page-toggle").addEventListener("click", () => { $("page-panel").hidden = !$("page-panel").hidden; });
$("page-close").addEventListener("click", () => { $("page-panel").hidden = true; });
$("start-here").addEventListener("click", (event) => {
  const example = event.target.closest(".example");
  if (example) send(example.textContent);
});
chrome.tabs.onActivated.addListener(refreshTab);
chrome.tabs.onUpdated.addListener((id, change) => {
  if (tab && id === tab.id && (change.url || change.status === "complete")) refreshTab();
});
chrome.windows.onFocusChanged.addListener(refreshTab);

(async () => {
  try {
    const stored = await chrome.storage.local.get("model");
    if (stored.model) {
      defaultModel = stored.model;
      storedModel = true;
    }
  } catch {
    // a convenience only
  }
  await refreshTab();
})();
