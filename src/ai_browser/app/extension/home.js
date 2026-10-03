// AI Home: every agent and what it is doing, every tab, and all of Claude's skills. Everything from Claude, pages or
// skills is set as text; thumbnails are JPEG data the app made from Chrome screenshots.
import { mountBrain } from "./brainui.js";
import { checkCard } from "./check.js";
import { connect } from "./link.js";
import { agentLabel, createChat, el } from "./chat.js";
import { permissionCard } from "./permission.js";
import { mountTabList } from "./tablist.js";
import { mountTools } from "./tools.js";
import { mountTrain } from "./train.js";
import { mountWorkflows } from "./workflows.js";

const $ = (id) => document.getElementById(id);
const COLORS = { grey: "#5f6368", blue: "#1a73e8", red: "#d93025", yellow: "#f9ab00", green: "#188038",
                 pink: "#d01884", purple: "#a142f4", cyan: "#007b83", orange: "#fa903e" };
const STATES = { working: "working", waiting: "waiting in line", your_turn: "your turn", stopped: "stopped",
                 failed: "failed", needs_you: "needs you" };
const agents = new Map();
const thumbs = new Map();
let tabs = [];
let skills = [];
let summary = null;
let maxWorking = 3;
let pending = null; // the new_task request waiting for its "created"
let pendingTimer = null;
let chatAgent = null;
let storedModel = false; // the user picked a model here before: it wins over the app's default
let browser = null; // where agents browse: {kind, name, state, groups}
let browserClients = []; // what uses the user's browser through AI Browser's one connection (the relay)
let handing = null; // one of the user's tabs the next new task starts in (Hand over → New agent…)
const WINDOWS_TAKE_FOCUS = false; // Task 1's by-hand check: true if each new AI window comes to the front
const STEPS = (name) => [`In ${name}, open ${name === "Brave" ? "brave" : "chrome"}://inspect/#remote-debugging.`,
  "Tick \"Allow remote debugging for this browser instance\".",
  `When ${name} asks "Allow remote debugging?", click Allow.`];
const SAYS = { connected: "connected", off: "switch off", ready: "ready", asking: "waiting for Allow",
               refused: "not allowed", lost: "closed" };
const chat = createChat($("chat-messages"));
const link = connect({ view: "home", onMessage: handle, onState: setStatus });
const brain = mountBrain($("brain"), link, { compact: true, openAgent: (id) => openChat(id) });
let watchSites = []; // the Brain's watch list: a message workflow's sites
let switchedOn = []; // the MCP servers switched on: what a workflow may use
const tools = mountTools($("tools"), link);
const workflows = mountWorkflows($("workflows"), link, { skills: () => skills, sites: () => watchSites,
                                                         servers: () => switchedOn });
const train = mountTrain($("train"), link, { tabs: () => tabs, model: () => $("task-model").value });

function setStatus(state) {
  $("status").dataset.state = state;
  $("status").title = { connected: "Connected to ai-browser app", connecting: "Connecting…" }[state]
    || "Not connected: is `ai-browser app` running?";
}

function flash(text) {
  $("hint").textContent = text;
  setTimeout(() => { if ($("hint").textContent === text) $("hint").textContent = ""; }, 5000);
}

function ordered() {
  return [...agents.values()].sort((a, b) => Number(b.id.slice(1)) - Number(a.id.slice(1)));
}

function owner(target) {
  return ordered().find((agent) => agent.working_tab === target || (agent.tabs || []).includes(target)
    || (agent.adopted || []).includes(target));
}

function renderCounts() {
  const all = [...agents.values()];
  const working = all.filter((agent) => agent.state === "working").length;
  const waiting = all.filter((agent) => agent.state === "waiting").length;
  $("counts").textContent = all.length
    ? `${working} working${waiting ? ` · ${waiting} waiting` : ""} · up to ${maxWorking} at once` : "";
}

const rows = new Map(); // agent id -> its row, built once and then updated in place (a click must not be lost)

function button(className, label, onClick) {
  const node = el("button", className, label);
  node.addEventListener("click", onClick);
  return node;
}

function makeAgentRow(id) {
  const row = el("div", "agent");
  row.dataset.id = id;
  const main = el("div", "main");
  const head = el("div", "head");
  const parts = { dot: el("span", "dot"), name: el("span", "name"), state: el("span", "chip"),
                  status: el("div", "status"), last: el("div", "last"), totals: el("div", "status totals"),
                  thumb: el("img", "thumb") };
  head.append(parts.dot, parts.name, parts.state);
  const buttons = el("div", "buttons");
  parts.watch = button("watch", "Watch", () => {
    const agent = agents.get(id);
    if (agent && agent.working_tab) link.send({ type: "watch", target: agent.working_tab });
  });
  parts.chat = button("chat", "Chat", () => openChat(id));
  parts.stop = button("stop", "Stop", () => link.send({ type: "stop", id }));
  parts.close = button("close", "Close", () => link.send({ type: "close", id }));
  parts.close.title = "End this agent and close the tabs it opened (your own tabs stay open)";
  buttons.append(parts.watch, parts.chat, parts.stop, parts.close);
  main.append(head, parts.status, parts.last, parts.totals, buttons);
  parts.thumb.alt = "";
  parts.thumb.hidden = true;
  row.append(main, parts.thumb);
  row.parts = parts;
  return row;
}

function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

function fillAgentRow(row, agent) {
  const parts = row.parts;
  const color = COLORS[agent.color] || "var(--muted)";
  row.style.borderLeftColor = color;
  parts.dot.style.background = color;
  setText(parts.name, agentLabel(agent));
  setText(parts.state, STATES[agent.state] || agent.state);
  parts.state.className = `chip ${agent.state}`;
  setText(parts.status, agent.status || "");
  parts.status.hidden = !agent.status;
  setText(parts.last, agent.last_action || "");
  parts.last.hidden = !agent.last_action;
  const totals = [`${Math.round(agent.seconds || 0)} s`];
  if (agent.cost) totals.push(`$${agent.cost.toFixed(2)}`);
  if ((agent.loaded_skills || []).length) totals.push(`skills: ${agent.loaded_skills.join(", ")}`);
  setText(parts.totals, totals.join(" · "));
  const asking = agent.permission; // a tool request waiting for the user: its card, on the row
  if (asking && parts.permission?.dataset.request !== asking.request) {
    parts.permission?.remove();
    parts.permission = permissionCard({ ...asking, agent: agent.id }, (message) => link.send(message), agent.name);
    row.querySelector(".main").append(parts.permission);
  } else if (!asking && parts.permission) {
    parts.permission.remove();
    parts.permission = null;
  }
  const check = agent.check; // a bot check waiting for the user: its card, on the row
  if (check && parts.check?.dataset.since !== String(check.since)) {
    parts.check?.remove();
    parts.check = checkCard(agent, (message) => link.send(message));
    row.querySelector(".main").append(parts.check);
  } else if (!check && parts.check) {
    parts.check.remove();
    parts.check = null;
  }
  parts.watch.disabled = !agent.working_tab;
  parts.stop.hidden = !(agent.state === "working" || agent.state === "waiting" || agent.check);
  const jpeg = thumbs.get(agent.id);
  if (jpeg && parts.thumb.dataset.jpeg !== String(jpeg.length) + jpeg.slice(-16)) {
    parts.thumb.src = `data:image/jpeg;base64,${jpeg}`;
    parts.thumb.dataset.jpeg = String(jpeg.length) + jpeg.slice(-16);
    parts.thumb.hidden = false;
  }
}

// Keep the rows in step with the agents without rebuilding them: new rows are inserted, closed ones removed,
// and the rest are only updated.
function renderAgents() {
  const list = $("agents");
  const all = ordered();
  for (const [id, row] of rows) {
    if (!agents.has(id)) {
      row.remove();
      rows.delete(id);
    }
  }
  list.querySelector(".empty")?.remove();
  let previous = null;
  for (const agent of all) {
    let row = rows.get(agent.id);
    if (!row) {
      row = makeAgentRow(agent.id);
      rows.set(agent.id, row);
      if (previous) previous.after(row);
      else list.prepend(row);
    }
    fillAgentRow(row, agent);
    previous = row;
  }
  if (!all.length) list.append(el("p", "empty", "No agents yet. Start a task above, or open the chat beside any page."));
  renderCounts();
  if (chatAgent && agents.has(chatAgent)) {
    const agent = agents.get(chatAgent);
    $("chat-dot").style.background = COLORS[agent.color] || "var(--muted)";
    $("chat-stop").hidden = !(agent.state === "working" || agent.state === "waiting" || agent.check);
  }
}

const tabList = mountTabList($("tabs"), {
  send: (message) => link.send(message),
  agents: () => ordered(),
  newAgent: (tab) => setHanding(tab),
});

function renderTabs() {
  tabList.render(tabs, {
    brave: browser?.kind === "brave",
    ownerOf: (target) => { // AI Browser mode: the app's list has no owners, so they come from the agents
      const agent = owner(target);
      return agent ? { kind: "agent", id: agent.id, name: agent.name, color: agent.color } : { kind: "you" };
    },
  });
}

function setHanding(tab) {
  handing = tab;
  $("handing").hidden = !tab;
  $("handing-text").textContent = tab ? `Starts in your tab: ${tab.title || tab.url}` : "";
  if (tab) $("task").focus();
}

function show(node, text) {
  node.textContent = text || "";
  node.hidden = !text;
}

function renderBrowser() {
  const card = $("browser-card");
  if (!browser) return;
  card.hidden = false;
  card.dataset.state = browser.kind === "brave" ? browser.state : "app";
  const action = $("browser-action");
  if (browser.kind !== "brave") {
    $("browser-title").textContent = "Agents browse in AI Browser";
    for (const id of ["browser-steps", "browser-note", "browser-groups", "browser-warning"]) $(id).hidden = true;
    action.hidden = true;
    renderClients();
    return;
  }
  const name = browser.name || "Brave";
  const on = browser.state === "connected" && browser.groups === "on";
  $("browser-title").textContent = `Your ${name} · ${SAYS[browser.state] || browser.state}${on ? " · tab groups on" : ""}`;
  const steps = $("browser-steps");
  steps.textContent = "";
  for (const step of STEPS(name)) steps.append(el("li", "", step));
  steps.hidden = browser.state !== "off";
  const label = { off: "Show me how", ready: "Connect", lost: "Connect", refused: "Try again" }[browser.state];
  action.textContent = label || "";
  action.hidden = !label;
  show($("browser-note"), {
    ready: `${name} will ask "Allow remote debugging?" once for AI Browser: click Allow`,
    asking: `${name} is asking "Allow remote debugging?": click Allow there (or Deny). Everything waiting for `
            + `${name} shares this one question.`,
    refused: `${name} said no, or nobody answered.`,
    lost: `${name} quit or restarted.`,
  }[browser.state]);
  const why = { no_watcher: `Load the watcher in ${name} to group the AI's tabs; until then they open in a window of `
                            + `their own.${WINDOWS_TAKE_FOCUS ? " Each new AI window may come to the front." : ""}`,
                old_watcher: "Update the watcher: reload it in brave://extensions." }[browser.groups];
  show($("browser-groups"), why ? `Tab groups off: ${why}` : "");
  show($("browser-warning"), `While the switch is on, any program on this computer can reach your ${name}, not only `
                             + "AI Browser. Turn it off when agents aren't working.");
  renderClients();
}

function clientLabel(row) {
  if (row.kind === "app") return "AI Browser · the tab list and pictures";
  const tabs = `${row.tabs} tab${row.tabs === 1 ? "" : "s"}`;
  const who = row.kind === "agent" ? agentLabel(row) : "Claude Code";
  return `${who} · ${tabs}${row.cut_off ? ` · cut off from ${browser?.name || "Brave"}` : ""}`;
}

function renderClients() { // what uses the user's browser through AI Browser's one connection; text only
  const box = $("browser-using");
  const list = $("browser-clients");
  list.textContent = "";
  box.hidden = !browser || browser.kind !== "brave" || browserClients.length === 0;
  if (box.hidden) return;
  const name = browser.name || "Brave";
  $("browser-using-title").textContent = `Using your ${name} through AI Browser`;
  for (const row of browserClients) {
    const item = el("li", "client");
    item.style.setProperty("--client-color", COLORS[row.color] || "transparent");
    item.append(el("span", "", clientLabel(row)));
    if (row.kind !== "app" && !row.cut_off) {
      const button = el("button", "ghost", "Disconnect");
      button.type = "button";
      button.addEventListener("click", () => link.send({ type: "browser_disconnect", id: row.id }));
      item.append(button);
    }
    list.append(item);
  }
  $("browser-clients-note").textContent = `Anything listed here can use your ${name} without a new question until `
    + "AI Browser quits. Disconnect cuts one off; unticking the switch cuts off everything.";
}

async function browserAction() {
  if (!browser || browser.kind !== "brave") return;
  if (browser.state === "off") { // the setup page's steps, with their warning
    try {
      const config = await (await fetch(chrome.runtime.getURL("config.json"), { cache: "no-store" })).json();
      await chrome.tabs.create({ url: `${config.server}/setup#switch` });
    } catch {
      flash("Not connected: is `ai-browser app` running?");
    }
    return;
  }
  link.send({ type: "brave_connect" });
}

function usedBy(skill) {
  return ordered().filter((agent) => (agent.loaded_skills || []).some((name) => name === skill.ref
    || name === skill.name || name.endsWith(`:${skill.name}`)));
}

// The skills list is rebuilt only when the skills or the search change; agent updates only refresh each row's
// "in use" chips and its list of agents.
function renderSkills() {
  if (summary) {
    const parts = Object.entries(summary.by_source).map(([source, count]) => `${source} ${count}`);
    $("skills").querySelector(".count").textContent = `${summary.total} · ${parts.join(", ")}`;
  }
  const query = $("skill-search").value.trim().toLowerCase();
  const list = $("skill-list");
  list.textContent = "";
  const shown = skills.filter((skill) => !query || `${skill.ref} ${skill.description}`.toLowerCase().includes(query));
  for (const skill of shown.slice(0, 200)) {
    const row = el("div", "skill");
    const top = el("div", "top-line");
    top.append(el("span", "name", skill.name), el("span", "chip", skill.source));
    row.append(top);
    if (skill.description) row.append(el("div", "desc", skill.description));
    const uses = el("div", "uses");
    const inUse = el("span", "in-use");
    const choose = el("select");
    const ask = button("", "Ask agent to use it", () => {
      if (choose.value) link.send({ type: "send", id: choose.value,
        text: `Load and use the skill ${skill.ref} with load_skill` });
    });
    uses.append(inUse, button("", "Use in new task", () => pick(skill.ref, true)), choose, ask);
    row.append(uses);
    row.skill = skill;
    row.parts = { inUse, choose, ask };
    list.append(row);
  }
  if (!shown.length && skills.length) list.append(el("p", "empty", "No skill matches."));
  refreshSkillUses();
}

function refreshSkillUses() {
  const running = ordered().filter((agent) => agent.state !== "failed");
  const options = running.map((agent) => `${agent.id}:${agent.name}`).join("|");
  for (const row of $("skill-list").querySelectorAll(".skill")) {
    const { inUse, choose, ask } = row.parts;
    const names = usedBy(row.skill).map((agent) => agent.name);
    if (inUse.dataset.names !== names.join("|")) {
      inUse.textContent = "";
      for (const name of names) inUse.append(el("span", "chip", `in use by ${name}`));
      inUse.dataset.names = names.join("|");
    }
    if (choose.dataset.options !== options && document.activeElement !== choose) { // never while it's open
      const selected = choose.value;
      choose.textContent = "";
      for (const agent of running) {
        const option = el("option", "", agent.name);
        option.value = agent.id;
        choose.append(option);
      }
      if (running.some((agent) => agent.id === selected)) choose.value = selected;
      choose.dataset.options = options;
    }
    choose.hidden = ask.hidden = !running.length;
  }
}

function renderPicker() {
  const box = $("skills-pick");
  const checked = new Set(pickedSkills());
  box.textContent = "";
  for (const skill of skills) {
    const label = el("label");
    const input = el("input");
    input.type = "checkbox";
    input.value = skill.ref;
    input.checked = checked.has(skill.ref);
    input.addEventListener("change", updatePicked);
    label.append(input, el("span", "", skill.ref));
    box.append(label);
  }
  updatePicked();
}

function pickedSkills() {
  return [...$("skills-pick").querySelectorAll("input:checked")].map((input) => input.value);
}

function pick(ref, on) {
  const input = [...$("skills-pick").querySelectorAll("input")].find((box) => box.value === ref);
  if (input) input.checked = on;
  updatePicked();
  $("task").focus();
}

function updatePicked() {
  const count = pickedSkills().length;
  $("picked-count").textContent = count ? `(${count})` : "";
}

function finishRequest() {
  pending = null;
  clearTimeout(pendingTimer);
  $("start").disabled = false;
}

function handle(message) {
  for (const part of [brain, tools, workflows, train]) part.onMessage(message);
  if (message.type === "brain_snapshot" || message.type === "brain_state") {
    watchSites = message.watch_list || [];
    workflows.options();
  } else if (message.type === "tools_snapshot") {
    switchedOn = (message.servers || []).filter((server) => server.enabled);
    workflows.options();
  }
  switch (message.type) {
    case "snapshot":
      brain.refresh(); // a new connection: the Brain's list, the workflows and the tools again too
      workflows.refresh();
      link.send({ type: "tools" });
      agents.clear();
      for (const agent of message.agents) agents.set(agent.id, agent);
      tabs = message.tabs || [];
      browser = message.browser || null;
      browserClients = message.browser_clients || [];
      renderBrowser();
      summary = message.skills_summary;
      maxWorking = message.max_working || 3;
      if (!storedModel && message.default_model) $("task-model").value = message.default_model;
      if (pending) finishRequest(); // a new connection: an unanswered Start can be pressed again
      renderAgents();
      renderTabs();
      renderSkills();
      link.send({ type: "skills" });
      if (chatAgent) link.send({ type: "events", id: chatAgent });
      break;
    case "agent":
      agents.set(message.agent.id, message.agent);
      renderAgents();
      renderTabs();
      refreshSkillUses();
      break;
    case "agent_closed":
      agents.delete(message.id);
      thumbs.delete(message.id);
      if (chatAgent === message.id) closeChat();
      renderAgents();
      renderTabs();
      refreshSkillUses();
      break;
    case "agent_event":
      if (message.id === chatAgent) chat.append(message.event);
      break;
    case "agent_events":
      if (message.id === chatAgent) {
        chat.reset("No messages yet.");
        for (const event of message.events) chat.append(event);
      }
      break;
    case "tabs":
      tabs = message.tabs || [];
      renderTabs();
      train.tabsChanged();
      break;
    case "browser_clients":
      browserClients = message.clients || [];
      renderClients();
      break;
    case "browser":
      browser = { kind: message.kind, name: message.name, state: message.state, groups: message.groups };
      renderBrowser();
      renderTabs();
      break;
    case "thumb": {
      thumbs.set(message.id, message.jpeg);
      const row = rows.get(message.id);
      if (row && agents.has(message.id)) fillAgentRow(row, agents.get(message.id));
      break;
    }
    case "skills":
      skills = message.skills || [];
      renderSkills();
      renderPicker();
      workflows.options();
      break;
    case "created":
      if (pending && message.request === pending) {
        finishRequest();
        $("task").value = "";
        for (const input of $("skills-pick").querySelectorAll("input:checked")) input.checked = false;
        updatePicked();
        setHanding(null);
      }
      break;
    case "error":
      if (pending && message.request === pending) finishRequest();
      if (message.text) flash(message.text);
      break;
  }
}

function start() {
  const text = $("task").value.trim();
  if (!text) {
    flash("Write what the agent should do");
    return;
  }
  if (pending) return; // one Start, one agent
  pending = `r${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  $("start").disabled = true;
  const sent = link.send({ type: "new_task", text, skills: pickedSkills(), model: $("task-model").value,
    request: pending, ...(handing ? { adopt: handing.target } : {}) });
  if (!sent) {
    finishRequest();
    flash("Not connected: is `ai-browser app` running?");
    return;
  }
  pendingTimer = setTimeout(finishRequest, 10000);
}

function openChat(id) {
  const agent = agents.get(id);
  if (!agent) return;
  chatAgent = id;
  $("chat").hidden = false;
  $("chat-name").textContent = agentLabel(agent);
  chat.reset("Loading…");
  renderAgents();
  link.send({ type: "events", id });
  $("chat-input").focus();
}

function closeChat() {
  chatAgent = null;
  $("chat").hidden = true;
}

function sendChat() {
  const text = $("chat-input").value.trim();
  if (!text || !chatAgent) return;
  if (link.send({ type: "send", id: chatAgent, text })) $("chat-input").value = "";
  else flash("Not connected: is `ai-browser app` running?");
}

let openingMission = null; // one click, one Mission Control: an open one is brought to the front

async function openMission() {
  const url = chrome.runtime.getURL("mission.html");
  const open = (await chrome.tabs.query({})).find((tab) => tab.url === url || tab.pendingUrl === url);
  if (open) {
    await chrome.tabs.update(open.id, { active: true });
    await chrome.windows.update(open.windowId, { focused: true }).catch(() => {});
  } else {
    await chrome.tabs.create({ url });
  }
}

$("mission").addEventListener("click", () => {
  openingMission ??= openMission().catch(() => {}).finally(() => { openingMission = null; });
});
$("start").addEventListener("click", start);
$("browser-action").addEventListener("click", browserAction);
$("handing-clear").addEventListener("click", () => setHanding(null));
$("task").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) start();
});
$("task-model").addEventListener("change", () => {
  chrome.storage.local.set({ model: $("task-model").value }).catch(() => {});
});
$("skill-search").addEventListener("input", renderSkills);
$("chat-close").addEventListener("click", closeChat);
$("chat-skill").addEventListener("click", () => {
  if (!chatAgent) return;
  $("train-section").open = true;
  train.fromAgent(chatAgent, agents.get(chatAgent)?.name);
});
$("tools-section").addEventListener("toggle", () => { if ($("tools-section").open) tools.refresh(); });
$("chat-send").addEventListener("click", sendChat);
$("chat-stop").addEventListener("click", () => chatAgent && link.send({ type: "stop", id: chatAgent }));
$("chat-input").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    sendChat();
  }
});

(async () => {
  try {
    const stored = await chrome.storage.local.get("model");
    if (stored.model) {
      $("task-model").value = stored.model;
      storedModel = true;
    }
  } catch {
    // a convenience only
  }
  if (new URLSearchParams(location.search).get("pin") === "1") { // AI Home as the first, pinned tab
    try {
      const tab = await chrome.tabs.getCurrent();
      if (tab && !tab.pinned) await chrome.tabs.update(tab.id, { pinned: true });
      if (tab) await chrome.tabs.move(tab.id, { index: 0 });
    } catch {
      // the tab went away
    }
  }
})();
