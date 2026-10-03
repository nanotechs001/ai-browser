// The watcher's Brain page, in Brave: the inbox (only what is new or needs the user), the watch list with the user's
// instructions for each site, adding a site by picking the part of its page to watch, pause, and style notes.
import { mountBrain } from "./brainui.js";
import { connect } from "./link.js";
import { permissionCard } from "./permission.js";
import { watchPattern } from "./sites.js";

const $ = (id) => document.getElementById(id);
const entries = new Map(); // site -> its row in the watch list
const waiting = new Map(); // agent id -> the agent, while a tool request of its waits for the user
let adding = null; // the site being added, waiting for the user's pick

function renderPermissions() {
  const list = $("permissions");
  for (const card of [...list.children]) {
    const agent = waiting.get(card.dataset.agent);
    if (!agent || agent.permission.request !== card.dataset.request) card.remove();
  }
  for (const agent of waiting.values()) {
    if (!list.querySelector(`[data-agent="${CSS.escape(agent.id)}"]`)) {
      const card = permissionCard({ ...agent.permission, agent: agent.id }, (message) => link.send(message),
                                  agent.name, { always: false }); // Always allow stays in AI Home's Tools
      card.dataset.agent = agent.id;
      list.append(card);
    }
  }
  $("permissions-section").hidden = waiting.size === 0;
}

function agentChanged(agent) {
  if (agent?.permission) waiting.set(agent.id, agent);
  else if (agent) waiting.delete(agent.id);
  renderPermissions();
}

const link = connect({ view: "brain", onMessage: handle, onState: setStatus });
const brain = mountBrain($("brain"), link);

function setStatus(state) {
  $("status").dataset.state = state;
  $("status").title = { connected: "Connected to ai-browser app", connecting: "Connecting…" }[state]
    || "The Brain is off: is `ai-browser app` running?";
  if (state === "connected") brain.refresh();
}

function note(id, text) {
  $(id).textContent = text;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function send(message) {
  const sent = link.send(message);
  if (!sent) note("add-note", "Not connected: is ai-browser app running?");
  return sent;
}

function entryRow(site) {
  if (entries.has(site)) return entries.get(site);
  const row = el("div", "watch-entry card");
  row.dataset.site = site;
  const top = el("label", "top-line");
  const enabled = el("input", "enabled");
  enabled.type = "checkbox";
  const label = el("strong", "label");
  const status = el("span", "status muted");
  top.append(enabled, label, status);
  const instructions = el("textarea", "instructions");
  instructions.rows = 2;
  instructions.placeholder = "Your instructions, in plain words. For example: always tell me about clients; skip "
    + "newsletters and receipts";
  const buttons = el("div", "row");
  const save = el("button", "save", "Save");
  const saved = el("span", "saved muted");
  buttons.append(save, saved);
  if (site.startsWith("custom:")) {
    const remove = el("button", "remove ghost", "Remove");
    remove.addEventListener("click", () => send({ type: "watch_remove", site }));
    buttons.append(remove);
  }
  row.append(top, instructions, buttons);
  enabled.addEventListener("change", () => send({ type: "watch_set", site, enabled: enabled.checked }));
  save.addEventListener("click", () => {
    if (send({ type: "watch_set", site, instructions: instructions.value })) saved.textContent = "Saved";
  });
  entries.set(site, row);
  return row;
}

function renderSettings(message) {
  const list = message.watch_list || [];
  for (const [site, row] of entries) {
    if (!list.some((entry) => entry.site === site)) {
      row.remove();
      entries.delete(site);
    }
  }
  for (const entry of list) {
    const row = entryRow(entry.site);
    row.querySelector(".enabled").checked = Boolean(entry.enabled);
    row.querySelector(".label").textContent = entry.label;
    row.querySelector(".status").textContent = entry.status || (entry.enabled ? "" : "off");
    const instructions = row.querySelector(".instructions");
    if (document.activeElement !== instructions) instructions.value = entry.instructions || "";
    if (row.parentElement !== $("watch")) $("watch").append(row);
  }
  $("pause").checked = Boolean(message.paused);
  if (document.activeElement !== $("style")) $("style").value = message.style || "";
}

function handle(message) {
  brain.onMessage(message);
  if (message.type === "snapshot") {
    waiting.clear();
    for (const agent of message.agents || []) agentChanged(agent);
    renderPermissions();
  } else if (message.type === "agent") {
    agentChanged(message.agent);
  } else if (message.type === "agent_closed") {
    waiting.delete(message.id);
    renderPermissions();
  }
  if (message.type === "brain_snapshot" || message.type === "brain_state") renderSettings(message);
  if (message.type === "brain_snapshot") {
    const wanted = /^#item=(.+)$/.exec(location.hash);
    if (wanted) brain.focus(decodeURIComponent(wanted[1]));
  }
  if (message.type === "error" && message.text) note("add-note", message.text);
}

async function loaded(tabId) {
  for (let tries = 0; tries < 100; tries += 1) {
    const tab = await chrome.tabs.get(tabId).catch(() => null);
    if (!tab || tab.status === "complete") return Boolean(tab);
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  return false;
}

$("add").addEventListener("click", async () => {
  let address;
  try {
    address = new URL($("add-url").value.trim());
    if (!/^https?:$/.test(address.protocol)) throw new Error("not a web page");
  } catch {
    note("add-note", "Write the site's address, starting with https://");
    return;
  }
  let allowed = false;
  try { // Brave asks the user, for this site only
    allowed = await chrome.permissions.request({ origins: [`${address.origin}/*`] });
  } catch {
    allowed = false;
  }
  if (!allowed) {
    note("add-note", "Brave didn't allow the Brain to read that site");
    return;
  }
  const tab = await chrome.tabs.create({ url: address.href, active: true });
  adding = { site: `custom:${address.hostname}`, label: address.hostname, url_match: watchPattern(address.href),
             tab: tab.id };
  note("add-note", "In that tab, click the part of the page to watch (Escape cancels)");
  if (await loaded(tab.id)) {
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["picker.js"] }).catch(() => {
      note("add-note", "Couldn't open the picker on that page");
    });
  }
});

chrome.runtime.onMessage.addListener((message, sender) => {
  if (message?.type !== "picked" || !adding || sender.tab?.id !== adding.tab) return false;
  const site = adding;
  adding = null;
  if (message.cancelled) {
    note("add-note", "Cancelled");
    return false;
  }
  if (send({ type: "watch_set", site: site.site, label: site.label, url_match: site.url_match,
             selector: message.selector, enabled: true })) {
    note("add-note", `Watching ${site.label}: ${String(message.sample || "").slice(0, 80)}`);
  }
  chrome.tabs.getCurrent().then((own) => own && chrome.tabs.update(own.id, { active: true })).catch(() => {});
  return false;
});

$("pause").addEventListener("change", () => send({ type: "pause", on: $("pause").checked }));
$("save-style").addEventListener("click", () => {
  if (send({ type: "style", text: $("style").value })) note("style-note", "Saved");
});
