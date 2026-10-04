// Mission Control: the user's AI team at work. One station per agent in a 3D room (scene.js), the Brain in the
// middle, on the same line to the app as AI Home (link.js), sending only the messages AI Home sends.
import { askBox, askKey, fillPicker, pickDefault } from "./accountui.js";
import { createBlob } from "./blob.js";
import { mountBrain } from "./brainui.js";
import { checkCard } from "./check.js";
import { agentLabel, createChat } from "./chat.js";
import { connect } from "./link.js";
import { guardCloseKey, guardLinks, openLive, openTab } from "./nav.js";
import { permissionCard } from "./permission.js";
import { COLORS, createScene, STATES, toolLabel } from "./scene.js";
import { mountTalk } from "./talk.js";
import { mountYourTabs } from "./tablist.js";
import { createVoice } from "./voice.js";

const $ = (id) => document.getElementById(id);
const agents = new Map(); // id -> the agent, as the app describes it
const listRows = new Map(); // id -> its row in the List, updated in place
const drawer = { id: null, parts: null, chat: null, brain: null, yourTabs: null }; // an agent, or the Brain
const brainItems = new Map(); // the Brain's inbox: id -> item
const brainState = { busy: false, what: "" }; // what the Brain is doing now
let speaking = false; // the voice is reading an update aloud
let agentsKnown = false; // the first snapshot is what was there already: only changes after it become updates
let brainKnown = false;
let selected = null;
let pending = null; // the new_task request waiting for its "created": one Start, one agent
let pendingTimer = null;
let defaultModel = "sonnet"; // ai-browser app --model, until the user picks one (the app remembers the pick)
let talkState = "idle"; // the talk panel's state (talk.js): the Brain listens while the user talks
let talk = null; // the talk panel, mounted once the line to the app exists
let tabs = []; // the browser's tab list (snapshot.tabs, then each "tabs" message): the drawer's Your tabs
let tabScope = null; // which profile that list comes from, and how many tabs it leaves out (only numbers)
let browser = null; // where agents browse: {kind, name, state} (snapshot.browser, then each "browser" message)
let accountRows = []; // Settings → Accounts as the app lists them: names and "signed in", never an email

const scene = createScene($("scene"), { onSelect: select, onCamera: aimBrain });
const brainButton = el("button", "brain");
brainButton.id = "brain";
brainButton.type = "button";
brainButton.setAttribute("aria-label", "The Brain: open its inbox");
const canvas = el("canvas", "blob");
const orb = el("div", "orb");
brainButton.append(canvas, orb);
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
scene.stage.append(bubble, brainButton, brainLabel);
const blob = createBlob(canvas, orb);
const voice = createVoice({
  bubble,
  onSpeaking: (on) => {
    speaking = on;
    renderBrain();
  },
  onBlocked: (blocked) => setText($("voice-note"), blocked ? "Click anywhere on this page to let the Brain speak" : ""),
  onWord: () => blob.word(),
});
for (const type of ["pointerdown", "keydown"]) addEventListener(type, () => voice.unblock(), { capture: true });
const link = connect({ view: "mission", onMessage: handle, onState: setStatus });
guardLinks(link);
guardCloseKey(); // Command-W (Ctrl+W) never closes the window from here
talk = mountTalk({
  panel: $("talk"),
  micButton: $("mic"),
  link,
  voice,
  onState: (state) => {
    talkState = state;
    renderBrain();
  },
  openAgent: (id, options) => select(id, options),
  openBrain: () => openBrain(),
  model: () => $("task-model").value, // the model last picked here or in AI Home
});

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

function stateOf(agent) {
  return agent.permission || agent.check ? "needs_you" : agent.state;
}

function setStatus(state) {
  talk?.connection(state); // a lost line ends a turn, or a question, at once
  $("status").dataset.state = state;
  $("status").title = { connected: "Connected to ai-browser app", connecting: "Connecting…",
                        refused: "This window wasn't opened by this run of ai-browser app: close it" }[state]
    || "Not connected: is `ai-browser app` running?";
}

function applySettings(settings) { // the model picked last, here or in AI Home: the app keeps it
  if (!settings) return;
  const model = settings.model ?? defaultModel;
  if ([...$("task-model").options].some((option) => option.value === model)) $("task-model").value = model;
}

// ---- the agents ----------------------------------------------------------------------------------------------

function renderCounts() {
  const states = [...agents.values()].map(stateOf);
  const count = (state) => states.filter((one) => one === state).length;
  const needs = count("needs_you");
  const parts = [[count("working"), "working"], [count("waiting"), "waiting"],
                 [needs, needs === 1 ? "needs you" : "need you"], [count("your_turn"), "done"],
                 [count("failed"), "failed"], [count("stopped"), "stopped"]];
  setText($("counts"), states.length ? parts.filter(([number]) => number).map(([number, word]) => `${number} ${word}`)
    .join(" · ") : "No agents yet");
}

function listRow(agent) {
  let row = listRows.get(agent.id);
  if (!row) {
    row = el("button", "");
    row.dataset.id = agent.id;
    row.created = Number(agent.created) || Infinity;
    row.parts = { dot: el("span", "dot"), name: el("span", "grow"), state: el("span", "chip") };
    row.append(row.parts.dot, row.parts.name, row.parts.state);
    row.addEventListener("click", () => select(agent.id));
    listRows.set(agent.id, row);
    $("list").querySelector(".empty")?.remove();
    const later = [...listRows.values()].filter((other) => other !== row && other.created > row.created)
      .sort((one, two) => one.created - two.created)[0]; // the oldest first, like the stations
    $("list").insertBefore(row, later || null);
  }
  row.parts.dot.style.background = COLORS[agent.color] || COLORS.grey;
  setText(row.parts.name, agentLabel(agent));
  setText(row.parts.state, STATES[stateOf(agent)] || stateOf(agent));
}

function renderEmptyList() {
  if (!agents.size && !$("list").querySelector(".empty")) {
    $("list").append(el("p", "empty muted", "No agents yet: give one a task below."));
  }
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
      : `${agent.name} wants to use ${toolLabel(agent.permission)}. It's waiting for you`));
  }
}

function update(agent) {
  if (!agent?.id) return;
  const before = agents.get(agent.id);
  if (before && agentsKnown) told(before, agent);
  agents.set(agent.id, agent);
  const fresh = agentsKnown && !before; // created while this page is open: its arrival plays
  scene.upsert(agent, { fresh });
  if (fresh) blob.burst(scene.directionTo(agent.id));
  listRow(agent);
  if (drawer.id === agent.id) fillDrawer(agent);
  renderCounts();
  renderBrain();
}

function forget(id) {
  agents.delete(id);
  scene.remove(id);
  listRows.get(id)?.remove();
  listRows.delete(id);
  if (selected === id) selected = null;
  if (drawer.id === id) closeDrawer();
  renderCounts();
  renderEmptyList();
  renderBrain();
}

// ---- the Brain ---------------------------------------------------------------------------------------------------

function renderBrain() { // the Brain thinks while it works, beats while something needs the user
  const needs = [...brainItems.values()].filter((item) => item.kind === "needs_reply").length;
  const agentsNeed = [...agents.values()].some((agent) => stateOf(agent) === "needs_you");
  const state = talkState === "listening" ? "listening" : speaking ? "speaking"
    : brainState.busy || talkState === "transcribing" ? "thinking" : needs || agentsNeed ? "alert" : "idle";
  blob.setState(state);
  setText(brainCount, needs ? `${needs} ${needs === 1 ? "needs" : "need"} you` : "");
  setText(brainWhat, brainState.busy ? brainState.what : "");
  aimBrain();
}

function aimBrain() { // the alert's signals gather on the side facing the oldest agent that needs the user
  const waiting = [...agents.values()].filter((agent) => stateOf(agent) === "needs_you")
    .sort((one, two) => (Number(one.created) || Infinity) - (Number(two.created) || Infinity))[0];
  blob.focus(waiting ? scene.directionTo(waiting.id) : null);
}

function showList(on) {
  $("list").hidden = !on;
  $("list-button").setAttribute("aria-expanded", String(on));
}

function openBrain() {
  closeDrawer();
  showList(false); // the drawer takes the List's place
  setText($("drawer-title"), "The Brain");
  $("drawer-dot").style.background = "var(--accent)";
  const root = el("div", "drawer-brain");
  $("drawer-body").replaceChildren(root);
  drawer.brain = mountBrain(root, link, { openAgent: (id) => select(id), cards: "confirm",
                                          openSetup: () => openTab("/setup#brave") });
  $("drawer").hidden = false;
}

function select(id, options = {}) {
  selected = id;
  for (const node of document.querySelectorAll(".station.selected")) node.classList.remove("selected");
  document.querySelector(`.station[data-id="${CSS.escape(id)}"]`)?.classList.add("selected");
  openAgent(id, options);
}

// ---- the drawer: an agent's state, Watch, Stop, Close, its permission card and its chat ------------------------------

function button(className, label, onClick) {
  const node = el("button", className, label);
  node.addEventListener("click", onClick);
  return node;
}

function openAgent(id, { tabs: showTabs = false } = {}) {
  const agent = agents.get(id);
  if (!agent) return;
  drawer.brain = null;
  drawer.id = id;
  const parts = { state: el("span", "chip"), status: el("div", "status muted"), buttons: el("div", "row buttons"),
                  permission: el("div", "permission-slot"), yourTabs: el("details", "your-tabs"),
                  messages: el("div", "messages"),
                  composer: el("div", "composer"), input: el("textarea"), card: null,
                  account: el("span", "chip account"), moved: el("div", "status muted moved"),
                  askSlot: el("div", "ask-slot"), ask: null, askKey: "" };
  parts.watch = button("watch", "Watch", () => {
    const current = agents.get(id);
    if (current?.working_tab) link.send({ type: "watch", target: current.working_tab });
  });
  parts.watch.title = "Bring this agent's tab to the front";
  parts.stop = button("stop", "Stop", () => link.send({ type: "stop", id }));
  parts.close = button("close ghost", "Close", () => link.send({ type: "close", id }));
  parts.close.title = "End this agent and close the tabs it opened (your own tabs stay open)";
  parts.buttons.append(parts.state, parts.account, parts.watch, parts.stop, parts.close);
  parts.input.rows = 1;
  parts.input.placeholder = "Message this agent";
  parts.input.setAttribute("aria-label", "Message this agent");
  const sendButton = button("primary", "Send", () => sendChat());
  parts.composer.append(parts.input, sendButton);
  parts.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      sendChat();
    }
  });
  drawer.yourTabs = mountYourTabs(parts.yourTabs, { send: (message) => link.send(message), agentId: () => id });
  parts.yourTabs.open = showTabs; // folded, unless the Brain pointed here to hand a tab over
  $("drawer-body").replaceChildren(parts.status, parts.moved, parts.buttons, parts.permission, parts.askSlot,
                                   parts.yourTabs, parts.messages, parts.composer);
  showList(false); // the drawer takes the List's place
  drawer.parts = parts;
  drawer.chat = createChat(parts.messages);
  drawer.chat.reset("Loading…");
  fillDrawer(agent);
  renderYourTabs();
  $("drawer").hidden = false;
  link.send({ type: "events", id });
}

function fillDrawer(agent) { // the drawer's agent changed: its parts are updated in place
  const parts = drawer.parts;
  const state = stateOf(agent);
  $("drawer-dot").style.background = COLORS[agent.color] || COLORS.grey;
  setText($("drawer-title"), agentLabel(agent));
  const paused = Boolean(agent.limit) && state === "failed"; // at a usage limit: paused, not failed
  setText(parts.state, paused ? "paused" : STATES[state] || state);
  parts.state.className = `chip ${paused ? "waiting" : state}`;
  setText(parts.account, agent.account?.name || "");
  parts.account.hidden = accountRows.length < 2; // one account: nothing to tell apart
  setText(parts.moved, agent.moved || "");
  parts.moved.hidden = !agent.moved;
  const key = askKey(agent, accountRows); // the same ask as AI Home's row
  if (key !== parts.askKey) {
    parts.ask?.remove();
    parts.ask = askBox(agent, accountRows, (message) => link.send(message));
    if (parts.ask) parts.askSlot.append(parts.ask);
    parts.askKey = key;
  }
  setText(parts.status, agent.status || agent.last_action || "");
  parts.status.hidden = !parts.status.textContent;
  parts.watch.disabled = !agent.working_tab;
  parts.stop.hidden = !(agent.state === "working" || agent.state === "waiting" || agent.check);
  const check = agent.check; // a bot check waiting for the user: the same card as AI Home's
  if (check && parts.checkCard?.dataset.since !== String(check.since)) {
    parts.checkCard?.remove();
    parts.checkCard = checkCard(agent, (message) => link.send(message), {
      openLive: (url, checked) => openLive(url, checked.id, agentLabel(checked)), // a tab of the window's own
    });
    parts.permission.prepend(parts.checkCard);
  } else if (!check && parts.checkCard) {
    parts.checkCard.remove();
    parts.checkCard = null;
  }
  const asking = agent.permission; // a tool request waiting for the user: the same card as AI Home's
  if (asking && parts.card?.dataset.request !== asking.request) {
    parts.card?.remove();
    parts.card = permissionCard({ ...asking, agent: agent.id }, (message) => link.send(message), agent.name);
    parts.permission.append(parts.card);
  } else if (!asking && parts.card) {
    parts.card.remove();
    parts.card = null;
  }
}

function renderYourTabs() { // the drawer's Your tabs follows the tab list and the browser's state
  if (!drawer.yourTabs) return;
  drawer.yourTabs.render(tabs, { brave: browser?.kind === "brave", connected: browser?.state === "connected",
                                 name: browser?.name || "Brave", scope: tabScope });
}

function sendChat() {
  const text = drawer.parts?.input.value.trim();
  if (!text || !drawer.id) return;
  if (link.send({ type: "send", id: drawer.id, text })) drawer.parts.input.value = "";
}

function closeDrawer() {
  $("drawer").hidden = true;
  drawer.id = null;
  drawer.parts = null;
  drawer.chat = null;
  drawer.brain = null;
  drawer.yourTabs = null;
  $("drawer-body").replaceChildren();
  for (const node of document.querySelectorAll(".station.selected")) node.classList.remove("selected");
}

// ---- the task bar ------------------------------------------------------------------------------------------------

function note(text) {
  setText($("task-note"), text);
  clearTimeout(note.timer);
  note.timer = setTimeout(() => setText($("task-note"), ""), 5000);
}

function finishStart() {
  pending = null;
  clearTimeout(pendingTimer);
  $("start").disabled = false;
}

function start() {
  const text = $("task").value.trim();
  if (!text) {
    note("Write what the agent should do");
    return;
  }
  if (pending) return;
  pending = `m${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  $("start").disabled = true;
  const account = $("task-account").hidden ? {} : { account: $("task-account").value }; // the picked account
  if (!link.send({ type: "new_task", text, skills: [], model: $("task-model").value, request: pending, ...account })) {
    finishStart();
    note("Not connected: is `ai-browser app` running?");
    return;
  }
  pendingTimer = setTimeout(finishStart, 10000);
}

// ---- the line to the app -----------------------------------------------------------------------------------------

function handle(message) {
  if (message.type?.startsWith("brain_")) drawer.brain?.onMessage(message); // the inbox in the drawer
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
      renderYourTabs();
      agentsKnown = true;
      renderCounts();
      renderEmptyList();
      defaultModel = message.default_model || defaultModel;
      applySettings(message.settings);
      accountRows = message.accounts || [];
      fillPicker($("task-account"), accountRows);
      link.send({ type: "accounts" }); // each account's status, now
      if (message.settings?.voice && !$("voice").checked) setVoice(true); // Voice was on: it comes back on
      if (pending) finishStart(); // a new connection: an unanswered Start can be pressed again
      if (drawer.id) link.send({ type: "events", id: drawer.id });
      link.send({ type: "thumbs" }); // the latest pictures, for a page opened after they were taken
      link.send({ type: "brain" });
      link.send({ type: "hearing" }); // can this page talk? (asked again after every reconnect)
      break;
    }
    case "agent_event":
      if (message.id === drawer.id) drawer.chat?.append(message.event);
      break;
    case "agent_events":
      if (message.id === drawer.id && drawer.chat) {
        drawer.chat.reset("No messages yet.");
        for (const event of message.events || []) drawer.chat.append(event);
      }
      break;
    case "accounts":
      accountRows = message.accounts || [];
      fillPicker($("task-account"), accountRows);
      if (drawer.id && agents.has(drawer.id)) fillDrawer(agents.get(drawer.id));
      break;
    case "created":
      if (pending && message.request === pending) {
        finishStart();
        $("task").value = "";
        pickDefault($("task-account"), accountRows);
      }
      talk?.onMessage(message); // a start from the talk's card, or a spoken yes
      break;
    case "hearing_status":
    case "heard":
    case "brain_answer":
      talk?.onMessage(message);
      break;
    case "error":
      if (pending && message.request === pending) finishStart();
      if (message.text && (!message.request || String(message.request).startsWith("m"))) note(message.text);
      break;
    case "tabs":
      tabs = message.tabs || [];
      tabScope = message.tab_scope || null;
      renderYourTabs();
      break;
    case "browser":
      browser = { kind: message.kind, name: message.name, state: message.state };
      renderYourTabs();
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
}

// ---- moving around ---------------------------------------------------------------------------------------------

const KEYS = { ArrowLeft: () => scene.turn(15), ArrowRight: () => scene.turn(-15), ArrowUp: () => scene.turn(0, 4),
               ArrowDown: () => scene.turn(0, -4), "+": () => scene.zoom(1.15), "=": () => scene.zoom(1.15),
               "-": () => scene.zoom(1 / 1.15), "0": () => scene.reset() };

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && (!$("drawer").hidden || !$("list").hidden)) {
    if (!$("drawer").hidden) closeDrawer();
    else showList(false);
    return;
  }
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.target instanceof Element && event.target.closest("input, textarea, select, [contenteditable]")) return;
  const action = KEYS[event.key];
  if (!action) return;
  event.preventDefault();
  action();
});

const view = scene.viewport;
let drag = null;
view.addEventListener("pointerdown", (event) => {
  if (event.button !== 0 || event.target.closest(".station, .stage")) return;
  drag = { x: event.clientX, y: event.clientY, id: event.pointerId };
  view.setPointerCapture(event.pointerId);
  view.classList.add("dragging");
});
view.addEventListener("pointermove", (event) => {
  if (!drag || event.pointerId !== drag.id) return;
  scene.turn((event.clientX - drag.x) * 0.25, (drag.y - event.clientY) * 0.15);
  drag.x = event.clientX;
  drag.y = event.clientY;
});
for (const type of ["pointerup", "pointercancel"]) {
  view.addEventListener(type, (event) => {
    if (drag && event.pointerId === drag.id) {
      drag = null;
      view.classList.remove("dragging");
    }
  });
}
view.addEventListener("wheel", (event) => { // in proportion to the scroll: a trackpad sends many small ones
  event.preventDefault();
  const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 400 : 1);
  scene.zoom(Math.exp(-Math.max(-300, Math.min(300, delta)) * 0.002));
}, { passive: false });
view.addEventListener("dblclick", (event) => {
  if (!event.target.closest(".station, .stage")) scene.reset();
});

$("drawer-close").addEventListener("click", closeDrawer);
$("home-link").addEventListener("click", () => openTab("/home"));
brainButton.addEventListener("click", openBrain);
bubble.addEventListener("click", openBrain);

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
$("start").addEventListener("click", start);
$("task").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    start();
  }
});
$("task-model").addEventListener("change", () => {
  link.send({ type: "settings_set", key: "model", value: $("task-model").value });
});
$("list-button").addEventListener("click", () => showList($("list").hidden));
renderCounts();
renderEmptyList();
renderBrain();
