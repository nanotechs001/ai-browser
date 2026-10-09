// Mission Control (the new look): the user's AI office. The left menu (the line's light, the counts, New Mission, the
// pages, the workspaces and the Usage card), the centre (the Flow · List · Calendar switch, the office of scene.js,
// the menu's pages and the composer), and the right column (side.js) for the agent picked. On the line to the app
// (link.js), sending only messages that are app-only rows of MESSAGE_RULES.
import { askError } from "./accountui.js";
import { mountAgentsPage } from "./agentspage.js";
import { mountHandoffSlot } from "./brainui.js";
import { mountBraveBar } from "./bravebar.js";
import { mountCalendar } from "./calendar.js";
import { el } from "./chat.js";
import { mountComposer } from "./composer.js";
import { mountDrawer } from "./drawer.js";
import { icon } from "./icons.js";
import { connect } from "./link.js";
import { mountIntegrations, mountKnowledge } from "./library.js";
import { guardCloseKey, guardLinks, openTab } from "./nav.js";
import { mountHistory, mountList, mountMissions } from "./pages.js";
import { createScene } from "./scene.js";
import { mountSide } from "./side.js";
import { stateOf, toolLabel } from "./step.js";
import { mountTabsPage } from "./tabspage.js";
import { mountTalk } from "./talk.js";
import { mountUsage } from "./usage.js";
import { createVoice } from "./voice.js";
import { fillMove, mountWorkspaces } from "./workspaces.js";

const $ = (id) => document.getElementById(id);
const PAGES = ["dashboard", "missions", "agents", "knowledge", "integrations", "tabs", "history"];
const VIEWS = ["flow", "list", "calendar"];
const MAC = /mac/i.test(navigator.userAgentData?.platform || navigator.platform || "");
const agents = new Map(); // id -> the agent, as the app describes it
const brainItems = new Map(); // the Brain's inbox: id -> item
const brainState = { busy: false, what: "" }; // what the Brain is doing now
const parts = []; // the menu's pages and cards: each may take every message (onMessage), the agents and the page shown
let speaking = false; // the voice is reading an update aloud
let agentsKnown = false; // the first snapshot is what was there already: only changes after it become updates
let brainKnown = false;
let selected = null; // the agent picked for the right column
let eventsFor = null; // whose actions the right column asked for
let workspace = null; // the workspace the menu filters by (null: every agent)
let workspaceRows = []; // the workspaces, as the app lists them
let page = "dashboard";
let view = "flow";
let defaultModel = "sonnet"; // ai-browser app --model, until the user picks one (the app remembers the pick)
let talkState = "idle"; // the talk panel's state (talk.js): the Brain listens while the user talks
let talk = null; // the talk panel, mounted once the line to the app exists (connect calls setStatus at once)
let tabs = []; // the browser's tab list (snapshot.tabs, then each "tabs" message): the drawer's Your tabs
let tabScope = null; // which profile that list comes from, and how many tabs it leaves out (only numbers)
let browser = null; // where agents browse: {kind, name, state}
let accountRows = []; // Settings → Accounts as the app lists them: names and "signed in", never an email
let tabHidden = false; // the tab menu shows another tab (app.js tells its frames)
let paused = false;
const spoken = new Set(); // the hand-offs the Brain has spoken of: each once

for (const node of document.querySelectorAll("[data-icon]")) {
  node.prepend(icon(node.dataset.icon));
  const label = node.querySelector(":scope > .label"); // the menu's buttons: named when the menu shows icons only
  if (label) {
    const name = label.textContent.split(/\s+/).filter(Boolean).join(" ");
    node.setAttribute("aria-label", name);
    node.title = name;
  }
}
$("new-key").textContent = MAC ? "⌘ K" : "Ctrl K";

function inWorkspace(agent) { // the menu's workspace filter: every agent while none is picked
  return !workspace || agent?.workspace === workspace;
}

function templateInWorkspace(slug) { // the same filter for a template: the Calendar uses it
  return !workspace || workspaceOfTemplate(slug) === workspace;
}

const scene = createScene($("scene"), { onSelect: select });
scene.setFilter(inWorkspace);
const brainLabel = el("div", "brain-label");
const brainCount = el("span", "count");
brainCount.id = "brain-count";
const brainWhat = el("span", "what");
brainWhat.id = "brain-what";
brainLabel.append(brainCount, brainWhat);
const bubble = el("div", "bubble");
bubble.id = "bubble";
bubble.hidden = true;
bubble.setAttribute("role", "status");
scene.stage.append(bubble, brainLabel);
const voice = createVoice({
  bubble,
  onSpeaking: (on) => {
    speaking = on;
    renderBrain();
  },
  onBlocked: (blocked) => setText($("voice-note"), blocked ? "Click anywhere on this page to let the Brain speak" : ""),
  onWord: () => scene.pulse(), // each spoken word pulses the globe
});
for (const type of ["pointerdown", "keydown"]) addEventListener(type, () => voice.unblock(), { capture: true });
const link = connect({ view: "mission", onMessage: handle, onState: setStatus });
const send = (message) => link.send(message);
guardLinks(link);
guardCloseKey(); // Command-W (Ctrl+W) never closes the window from here
window.addEventListener("focus", () => link.send({ type: "accounts" })); // shown again: each account's status, now
const drawer = mountDrawer({ link, agentOf: (id) => agents.get(id), accounts: () => accountRows,
                             browserOf: () => ({ tabs, scope: tabScope, browser }),
                             saveSkill: (id, name) => { // Save as skill: Knowledge's Train drafts it from that chat
                               showPage("knowledge");
                               knowledge.fromAgent(id, name);
                             },
                             saveAgent: (agent) => { // Save as agent: a new agent's settings, filled from this run
                               drawer.close();
                               showPage("agents");
                               agentsPage.showAgent("", {
                                 name: agent.name, description: agent.description || "", model: agent.model,
                                 effort: agent.effort || "default",
                                 web: agent.web || "web",
                                 // a run on Default: the agent follows "the default account for new agents"
                                 account: agent.account?.id && agent.account.id !== "default" ? agent.account.id : null,
                                 folder: agent.folder || null, use: [], load: agent.loaded_skills || [],
                               });
                             } });
const side = mountSide({ send, openDrawer, openHistory: () => showPage("history") });
const list = mountList($("view-list"), { onOpen: select });
const composer = mountComposer({ link, workspaceOf: () => workspace }); // Ask AI and Build a Mission
parts.push(composer);
const missions = mountMissions($("page-missions"), { onOpen: openDrawer, visible: inWorkspace,
                                                     decorate: (row, agent) => moveFor(row, { agent: agent.id },
                                                                                       agent.workspace) });
const history = mountHistory($("page-history"), { onOpen: openDrawer, visible: inWorkspace });
const agentsPage = mountAgentsPage($("page-agents"), $("agent-panel"), { link, agents: () => agents,
                                                                        accounts: () => accountRows });
parts.push(missions, history, agentsPage);
const knowledge = mountKnowledge($("page-knowledge"), link, { tabs: () => tabs, model: () => $("task-model").value,
                                                             useSkill: (ref) => { // Use in new mission
                                                               showPage("dashboard");
                                                               composer.pickSkill(ref);
                                                             } });
parts.push(knowledge, mountIntegrations($("page-integrations"), link));
parts.push(mountTabsPage($("page-tabs"), { // the user's tabs: Hand over, Take back, and a click brings one forward
  send,
  agents: () => [...agents.values()].sort((one, two) => (two.number || 0) - (one.number || 0)),
  newAgent: (tab) => { // Hand over → New agent…: Build a Mission, starting in that tab
    showPage("dashboard");
    composer.startIn(tab);
  },
}));

const spaces = mountWorkspaces($("workspaces"), { send, onFilter: setWorkspace });
const usage = mountUsage($("usage"));
parts.push(spaces, {
  onMessage(message) {
    if (message.type === "snapshot" || message.type === "workspaces") {
      workspaceRows = message.workspaces || [];
      renderAll();
    }
    if (message.type === "snapshot" || message.type === "accounts") usage.render(message.accounts || []);
  },
});
parts.push(mountHandoffSlot($("handoff"), send)); // the Brain's hand-offs, by the globe (its inbox lists them all)
parts.push(mountBraveBar($("brave-bar"), { send, openTab })); // Brave's connection, until it is connected
// the hand-offs never cover the composer, nor Ask AI's history above it
const reserved = new ResizeObserver(() => $("centre").style.setProperty("--composer",
  `${$("composer").offsetHeight + $("talk").offsetHeight}px`));
reserved.observe($("composer"));
reserved.observe($("talk"));
parts.push(mountCalendar($("view-calendar"), { onAgent: openDrawer, onTemplate: openTemplate, visible: inWorkspace,
                                                visibleTemplate: templateInWorkspace }));

function openTemplate(slug) { // a template in the Calendar: the Agents page, at its agent's settings or the template
  showPage("agents");
  agentsPage.showTemplate(slug);
}

function workspaceOfTemplate(slug) {
  return workspaceRows.find((row) => (row.templates || []).includes(slug))?.id || null;
}

function moveFor(container, target, current) { // Workspace ▾: moves an agent (a filter, no right)
  let select = container.querySelector(":scope > select.move");
  if (!select) {
    select = el("select", "move");
    select.setAttribute("aria-label", "Workspace");
    select.addEventListener("change", () => link.send({ type: "workspace_assign", ...target,
                                                        workspace: select.value || null }));
    container.append(select);
  }
  fillMove(select, workspaceRows, current);
}

function setWorkspace(id) { // the menu's filter: the Dashboard, My Missions and the Calendar show only this one's
  workspace = id;
  spaces.setActive(id);
  scene.setFilter(inWorkspace);
  composer.workspaceChanged();
  renderAll();
}

talk = mountTalk({
  panel: $("talk"),
  micButton: $("mic"),
  link,
  voice,
  onState: (state) => {
    talkState = state;
    renderBrain();
  },
  openAgent: (id, options) => openDrawer(id, options),
  openBrain: () => drawer.openBrain(),
  model: () => $("task-model").value, // the model last picked here (the app remembers it)
  fill: (words) => composer.fill(words), // the mic outside Ask AI fills the box
  keep: 200, // Ask AI's history: this run's talk with the Brain, scrolled on hover (composer.css)
});

function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

function setStatus(state) {
  talk?.connection(state); // a lost line ends a turn, or a question, at once
  $("status").dataset.state = state;
  $("status").title = { connected: "Connected to ai-browser app", connecting: "Connecting…",
                        refused: "This window wasn't opened by this run of ai-browser app: close it" }[state]
    || "Not connected: is `ai-browser app` running?";
}

function applySettings(settings) { // the model picked last: the app keeps it
  if (!settings) return;
  const model = settings.model ?? defaultModel;
  if ([...$("task-model").options].some((option) => option.value === model)) $("task-model").value = model;
  composer.thinkFace();
}

// ---- the agents ----------------------------------------------------------------------------------------------

function renderCounts() { // "1 active task · 3 completed", and who needs the user or failed (plan decision 19)
  const states = [...agents.values()].map(stateOf);
  const atWork = [...agents.values()].filter((agent) => agent.state === "working").length;
  setText(document.querySelector("title"), atWork ? `(${atWork}) Mission Control` : "Mission Control"); // the window's
  try { // and the app's badge (there is no toolbar badge)
    if (atWork) navigator.setAppBadge?.(atWork)?.catch(() => {});
    else navigator.clearAppBadge?.()?.catch(() => {});
  } catch {
    // not an installed app: the title says it
  }
  if (!states.length) {
    setText($("counts"), "No agents yet");
    return;
  }
  const count = (...wanted) => states.filter((one) => wanted.includes(one)).length;
  const active = count("working", "waiting", "needs_you");
  const words = [`${active} active task${active === 1 ? "" : "s"}`, `${count("your_turn")} completed`];
  const needs = count("needs_you");
  if (needs) words.push(`${needs} ${needs === 1 ? "needs" : "need"} you`);
  if (count("failed")) words.push(`${count("failed")} failed`);
  setText($("counts"), words.join(" · "));
}

function brief(text) { // an update is a line, never a page of text
  const words = String(text).replace(/\s+/g, " ").trim();
  return words.length > 140 ? `${words.slice(0, 139).trimEnd()}…` : words;
}

function told(before, agent) { // an agent's change worth a word from the Brain (its name only, never what it read)
  const was = stateOf(before);
  const now = stateOf(agent);
  if (was === now) return;
  if (now === "your_turn") voice.say(brief(`${agent.name} is done`));
  else if (now === "failed") {
    voice.say(brief(agent.limit ? `${agent.name} stopped at a usage limit` : `${agent.name} hit a problem`));
  }
  else if (now === "needs_you") {
    voice.say(brief(agent.check ? `${agent.name} hit a bot check on ${agent.check.site}. It's waiting for you`
      : `${agent.name} wants to ${agent.permission?.card ? "" : "use "}${toolLabel(agent.permission)}. `
        + "It's waiting for you"));
  }
}

function picked() { // the right column's agent: the one picked, else the newest at work, needing you, or any
  const visible = [...agents.values()].filter(inWorkspace);
  const newest = (rows) => rows.sort((one, two) => (Number(two.created) || 0) - (Number(one.created) || 0))[0];
  const chosen = agents.get(selected);
  return (chosen && inWorkspace(chosen) ? chosen : null)
    || newest(visible.filter((agent) => stateOf(agent) === "working"))
    || newest(visible.filter((agent) => stateOf(agent) === "needs_you")) || newest(visible) || null;
}

function renderSide() {
  const agent = picked();
  if (agent && agent.id !== eventsFor) { // its actions, for a checklist without a to-do list
    eventsFor = agent.id;
    link.send({ type: "events", id: agent.id });
  }
  side.show([...agents.values()].filter(inWorkspace), agent);
}

function renderAll() {
  renderCounts();
  renderSide();
  list.render(scene.shown().map((id) => agents.get(id)).filter(Boolean));
  for (const part of parts) part.agents?.(agents);
}

function update(agent) {
  if (!agent?.id) return;
  const before = agents.get(agent.id);
  if (before && agentsKnown) told(before, agent);
  agents.set(agent.id, agent);
  scene.upsert(agent, { fresh: agentsKnown && !before }); // created while this page is open: its arrival plays
  drawer.fill(agent);
  renderAll();
  renderBrain();
}

function forget(id) {
  agents.delete(id);
  scene.remove(id);
  if (selected === id) selected = null;
  if (drawer.id === id) drawer.close();
  renderAll();
  renderBrain();
}

// ---- the Brain: the globe ------------------------------------------------------------------------------------------

function renderBrain() { // the globe thinks while the Brain works, and glows amber while something needs the user
  const needs = [...brainItems.values()].filter((item) => item.kind === "needs_reply").length;
  const agentsNeed = [...agents.values()].some((agent) => stateOf(agent) === "needs_you");
  const state = talkState === "listening" ? "listening" : speaking ? "speaking"
    : brainState.busy || talkState === "transcribing" ? "thinking" : needs || agentsNeed ? "alert" : "idle";
  scene.stage.dataset.state = state; // the globe's glow (office.css)
  setText(brainCount, needs ? `${needs} ${needs === 1 ? "needs" : "need"} you` : "");
  setText(brainWhat, brainState.busy ? brainState.what : "");
}

// ---- picking an agent, and its drawer --------------------------------------------------------------------------------

function select(id) { // a desk, a row or an activity: the right column shows it (plan decision 11)
  selected = id;
  scene.select(id);
  renderSide();
  if (agents.has(id) && stateOf(agents.get(id)) === "needs_you") drawer.open(id); // a card waits: one click away
}

function focusOn(message) { // a notification's click, or the floating chat's Open: that agent's drawer, or the Brain's
  if (window.parent !== window) openTab("/mission"); // inside the tab menu: Mission Control's tab in front
  if (message.brain) drawer.openBrain();
  else if (agents.has(String(message.agent || ""))) openDrawer(String(message.agent));
}

function openDrawer(id, options = {}) { // Chat, Hand over, Answer, an activity or a page's Open: the agent's drawer
  selected = id;
  scene.select(id);
  renderSide();
  drawer.open(id, options);
}

// ---- the menu's pages, and the switch -----------------------------------------------------------------------------

function showPage(name) {
  page = PAGES.includes(name) ? name : "dashboard";
  for (const one of PAGES) $(`page-${one}`).hidden = one !== page;
  for (const button of document.querySelectorAll(".page-link")) {
    if (button.dataset.page === page) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  $("composer").hidden = page !== "dashboard" && page !== "missions";
  $("talk-log").scrollTop = $("talk-log").scrollHeight; // a hidden log loses its place: newest in view again
  if (page === "dashboard" && view === "flow") scene.refit();
  for (const part of parts) part.shown?.(page, view);
}

function showView(name) {
  view = VIEWS.includes(name) ? name : "flow";
  for (const one of VIEWS) $(`view-${one}`).hidden = one !== view;
  for (const tab of $("views-switch").querySelectorAll("[data-view]")) {
    tab.setAttribute("aria-selected", String(tab.dataset.view === view));
  }
  if (view === "flow") scene.refit();
  for (const part of parts) part.shown?.(page, view);
}

function newMission() { // New Mission and Command-K (Ctrl+K): the Dashboard, and the cursor in the box
  showPage("dashboard");
  composer.focus();
}

// ---- the line to the app -----------------------------------------------------------------------------------------

function handle(message) {
  for (const part of parts) part.onMessage?.(message);
  switch (message.type) {
    case "brain_snapshot":
      brainItems.clear();
      for (const item of message.items || []) brainItems.set(item.id, item);
      brainKnown = true;
      Object.assign(brainState, { busy: Boolean(message.activity), what: String(message.activity || "") });
      renderBrain();
      break;
    case "brain_state":
      Object.assign(brainState, { busy: Boolean(message.activity), what: String(message.activity || "") });
      renderBrain();
      break;
    case "brain_item": {
      const item = message.item;
      if (!item?.id) break;
      const before = brainItems.get(item.id);
      brainItems.set(item.id, item);
      if (brainKnown && !before && item.kind === "needs_reply") { // the Brain's one-line summary, never the message
        const summary = item.summary && item.summary !== item.snippet ? item.summary : ""; // no summary: no text
        voice.say(brief(`${item.sender || "Someone"} needs your reply${summary ? `: ${summary}` : ""}`));
      } else if (brainKnown && before && item.state === "draft_ready"
                 && (item.draft_version || 0) > (before.draft_version || 0)) { // a new draft, not a failed fill
        voice.say(brief(`Your reply to ${item.sender || "them"} is ready to check`));
      }
      renderBrain();
      break;
    }
    case "brain_item_gone":
      brainItems.delete(message.id);
      renderBrain();
      break;
    case "brain_handoff": { // a new one: a word from the Brain (names only, never the instruction); the user's own
      const handoff = message.handoff; // words aren't, as the talk said it already
      if (!handoff?.id || spoken.has(handoff.id) || !["counting", "waiting"].includes(handoff.state)
          || handoff.source === "you") break;
      spoken.add(handoff.id);
      const who = `${Number.isInteger(handoff.number) ? `${handoff.number} · ` : ""}${handoff.name || "an agent"}`;
      if (handoff.kind === "start") voice.say("I suggest a new agent: press Start if you want it");
      else if (handoff.state === "counting") voice.say(brief(`Giving ${who} a task. Cancel within 15 seconds`));
      else voice.say(brief(`I have a task for ${who}: press Send if you want it`));
      break;
    }
    case "brain_activity":
      Object.assign(brainState, { busy: Boolean(message.busy), what: String(message.what || "") });
      renderBrain();
      break;
    case "snapshot": {
      const ids = new Set((message.agents || []).map((agent) => agent.id));
      for (const id of [...agents.keys()]) if (!ids.has(id)) forget(id);
      for (const agent of message.agents || []) update(agent);
      tabs = message.tabs || [];
      tabScope = message.tab_scope || null;
      browser = message.browser || null;
      drawer.tabsChanged();
      agentsKnown = true;
      defaultModel = message.default_model || defaultModel;
      applySettings(message.settings);
      accountRows = message.accounts || [];
      if (message.settings?.voice && !$("voice").checked) setVoice(true); // Voice was on: it comes back on
      if (drawer.id) link.send({ type: "events", id: drawer.id });
      eventsFor = null; // and the right column asks for its agent's actions again
      renderAll();
      for (const kind of ["accounts", "thumbs", "brain", "hearing", "permission_rules", "workflows", "skills"]) {
        link.send({ type: kind }); // workflows: the Calendar's templates and each workspace's count; skills: Skills
      }
      break;
    }
    case "focus":
      focusOn(message);
      break;
    case "agent_event":
      side.event(message.id, message.event);
      break;
    case "agent_events":
      side.events(message.id, message.events || []);
      break;
    case "accounts":
      accountRows = message.accounts || [];
      break;
    case "created":
      talk?.onMessage(message); // a start from the talk's card, or a spoken yes
      break;
    case "hearing_status":
    case "heard":
    case "brain_answer":
      talk?.onMessage(message);
      break;
    case "error":
      if (askError(message)) composer.note(message.text || ""); // a refused Continue on: it can be clicked again
      break;
    case "tabs":
      tabs = message.tabs || [];
      tabScope = message.tab_scope || null;
      drawer.tabsChanged();
      break;
    case "browser":
      browser = { kind: message.kind, name: message.name, state: message.state };
      drawer.tabsChanged();
      break;
    case "settings":
      applySettings(message);
      break;
    case "agent":
      update(message.agent);
      break;
    case "agent_closed":
      forget(message.id);
      break;
    case "thumb":
      scene.thumb(message.id, message.jpeg);
      break;
    case "thumbs":
      for (const [id, jpeg] of Object.entries(message.thumbs || {})) scene.thumb(id, jpeg);
      break;
  }
  drawer.onMessage(message); // after the switch: an `accounts` message has set accountRows, which the drawer draws from
}

// ---- moving around the room, and the keys ----------------------------------------------------------------------

const KEYS = { ArrowLeft: () => scene.turn(15), ArrowRight: () => scene.turn(-15), ArrowUp: () => scene.turn(0, 4),
               ArrowDown: () => scene.turn(0, -4), "+": () => scene.zoom(1.15), "=": () => scene.zoom(1.15),
               "-": () => scene.zoom(1 / 1.15), "0": () => scene.reset() };

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && drawer.isOpen) {
    drawer.close();
    return;
  }
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.target instanceof Element && event.target.closest("input, textarea, select, [contenteditable]")) return;
  if (page !== "dashboard" || view !== "flow") return;
  const action = KEYS[event.key];
  if (!action) return;
  event.preventDefault();
  action();
});

document.addEventListener("keydown", (event) => { // Command-K (Ctrl+K elsewhere): a new mission, from anywhere
  const command = MAC ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey;
  if (!command || event.altKey || event.shiftKey || String(event.key).toLowerCase() !== "k") return;
  if (document.querySelector("dialog:modal")) return; // a question is open (confirm.js): the page behind waits
  event.preventDefault();
  newMission();
}, true);

const roomView = scene.viewport;
let drag = null;
roomView.addEventListener("pointerdown", (event) => {
  if (event.button !== 0 || event.target.closest(".station, .stage")) return;
  drag = { x: event.clientX, y: event.clientY, id: event.pointerId };
  roomView.setPointerCapture(event.pointerId);
  roomView.classList.add("dragging");
});
roomView.addEventListener("pointermove", (event) => {
  if (!drag || event.pointerId !== drag.id) return;
  scene.turn((event.clientX - drag.x) * 0.25, (drag.y - event.clientY) * 0.15);
  drag.x = event.clientX;
  drag.y = event.clientY;
});
for (const type of ["pointerup", "pointercancel"]) {
  roomView.addEventListener(type, (event) => {
    if (drag && event.pointerId === drag.id) {
      drag = null;
      roomView.classList.remove("dragging");
    }
  });
}
const FOLDED = matchMedia("(max-width: 1279px)"); // the right column under the room: the page itself scrolls
roomView.addEventListener("wheel", (event) => { // in proportion to the scroll: a trackpad sends many small ones
  if (FOLDED.matches && !event.ctrlKey && !event.metaKey) return; // it scrolls the page; Ctrl or Cmd (a pinch) zooms
  event.preventDefault();
  const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 400 : 1);
  scene.zoom(Math.exp(-Math.max(-300, Math.min(300, delta)) * 0.002));
}, { passive: false });
roomView.addEventListener("dblclick", (event) => {
  if (!event.target.closest(".station, .stage")) scene.reset();
});

async function setVoice(on) { // Voice: only a voice that runs on this computer; off by default, and remembered
  const result = await voice.setEnabled(on);
  $("voice").checked = result.on;
  setText($("voice-note"), result.reason || "");
  return result;
}

$("voice").addEventListener("change", async () => {
  const result = await setVoice($("voice").checked);
  link.send({ type: "settings_set", key: "voice", value: result.on }); // remembered by the app, not the browser
});
$("task-model").addEventListener("change", () => {
  link.send({ type: "settings_set", key: "model", value: $("task-model").value });
});
$("new-mission").addEventListener("click", newMission);
for (const button of document.querySelectorAll(".page-link")) {
  button.addEventListener("click", () => showPage(button.dataset.page));
}
for (const button of $("views-switch").querySelectorAll("[data-view]")) {
  button.addEventListener("click", () => showView(button.dataset.view));
}
$("usage").addEventListener("click", () => openTab("/settings#accounts-section")); // Settings → Accounts
scene.globe.addEventListener("click", () => drawer.openBrain());
bubble.addEventListener("click", () => drawer.openBrain());

// ---- hidden: its tab or the window. Animations and timers wait (plan decision 16) --------------------------------

function hidden(on) {
  paused = on;
  document.documentElement.classList.toggle("paused", on);
  scene.pause(on);
}

addEventListener("message", (event) => {
  if (event.source !== window.parent || event.origin !== location.origin || event.data?.type !== "shown") return;
  tabHidden = !event.data.on;
  hidden(tabHidden || document.hidden);
});
document.addEventListener("visibilitychange", () => hidden(tabHidden || document.hidden));
setInterval(() => {
  if (!paused) side.tick(); // the step's timer and "2m ago"
}, 1000);
renderCounts();
renderSide();
renderBrain();
