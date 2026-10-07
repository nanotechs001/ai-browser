// AI Browser's floating chat (/chat), in a small window of AI Browser's own app that stays above the others, beside
// Brave. The shortcut picked in Settings, or the menu-bar icon's Show chat, shows and hides it; Esc and ✕ hide it.
// It holds "This page" (the Brave tab you're on: pagebar.js), the Brain's talk, typed or push-to-talk (talk.js), New
// task, the open agents by number, and the card of the newest agent that waits for you. The Brain only proposes; a
// question reads the page only while "Ask about it" is on; only a click hands a tab over. New task takes pictures
// pasted into its box, and files dropped on it, as Mission Control's Build a Mission does (paste.js, uploads.js: staged
// over this page's own line); the Brain's box takes text only, and says so. Every word from Claude, pages and agents
// is set as text.
import { fillPicker, pickDefault } from "./accountui.js";
import { checkCard } from "./check.js";
import { agentLabel, el } from "./chat.js";
import { connect } from "./link.js";
import { guardLinks } from "./nav.js";
import { host, mountPageBar, pickable } from "./pagebar.js";
import { takeFiles } from "./paste.js";
import { permissionCard } from "./permission.js";
import { mountTalk } from "./talk.js";
import { mountFolderPicker } from "./folderpick.js";
import { mountUploads } from "./uploads.js";

const $ = (id) => document.getElementById(id);
const NOT_CONNECTED = "Not connected: is `ai-browser app` running?";
const PICTURES_HERE = "Pictures go with New task"; // the Brain's box takes text only
const STATES = { working: "working", waiting: "waiting in line", your_turn: "your turn", stopped: "stopped",
                 failed: "failed" };
const quiet = { enabled: false, say() {}, pause() {}, resume() {} }; // the chat answers in text: nothing speaks here
const agents = new Map(); // the open agents, by id
let accounts = []; // Settings → Accounts as the app lists them: names and "signed in", never an email
let pending = null; // the new_task request waiting for its "created"
let taking = []; // the files that went with it: only those chips go when it is created
let pendingTimer = null;
let hereTab = null; // the tab This page showed when "Start it in this page" was last looked at
let talk = null;
let bar = null;
let folders = null; // the Folder picker (agent powers)
let uploads = null; // New task's attached files: pasted or dropped

function setStatus(state) {
  talk?.connection(state); // a lost line ends a turn, or a question, at once
  $("status").dataset.state = state;
  $("status").title = { connected: "Connected to ai-browser app", connecting: "Connecting…",
                        refused: "This window wasn't opened by this run of ai-browser app: close it" }[state]
    || NOT_CONNECTED;
}

function flash(text) {
  $("hint").textContent = text;
  setTimeout(() => { if ($("hint").textContent === text) $("hint").textContent = ""; }, 5000);
}

function ordered() { // the open agents, by number
  return [...agents.values()].sort((a, b) => (a.number || 0) - (b.number || 0));
}

function stateOf(agent) {
  return agent.permission || agent.check ? "needs you" : STATES[agent.state] || "";
}

// The open agents by number, so the user can name one to the Brain ("tell agent 2…"); a click opens it in AI Home.
function renderAgents() {
  const list = $("agents");
  const rows = ordered();
  const signature = JSON.stringify(rows.map((agent) => [agent.id, agentLabel(agent), stateOf(agent)]));
  if (list.dataset.rows === signature) return; // rebuilt only when it changed, so a click lands
  list.dataset.rows = signature;
  list.replaceChildren(...rows.map((agent) => {
    const chip = el("button", "agent-chip");
    chip.type = "button";
    chip.dataset.id = agent.id;
    chip.append(el("span", "agent-name", agentLabel(agent)), el("span", "agent-state muted", stateOf(agent)));
    chip.addEventListener("click", () => link.send({ type: "show_app", agent: agent.id }));
    return chip;
  }));
  list.hidden = rows.length === 0;
}

function renderNeeds() { // the newest agent that waits for you: its tool request or its bot check, answered here
  const slot = $("needs-you");
  const waiting = ordered().reverse().find((agent) => agent.permission || agent.check);
  if (!waiting) {
    slot.replaceChildren();
    return;
  }
  const key = `${waiting.id}:${waiting.permission ? waiting.permission.request : waiting.check.since}`;
  if (slot.firstChild?.dataset.key === key) return;
  const send = (message) => link.send(message);
  const card = waiting.permission
    ? permissionCard({ ...waiting.permission, agent: waiting.id }, send, agentLabel(waiting))
    : checkCard(waiting, send, { openLive: (url, agent) => link.send({ type: "show_app", agent: agent.id }) });
  card.dataset.key = key;
  slot.replaceChildren(card);
}

function setNew(open) { // New task, shown on its button's click
  $("new").hidden = !open;
  $("new-open").setAttribute("aria-expanded", String(open));
  if (open) $("task").focus();
}

// Start it in this page: only for one of your own web tabs, and only the one the user ticked it on. Another tab, or
// this tab on another site, unticks it, so Start never hands over a tab the user didn't mark.
function hereChanged(tab) {
  const mine = Boolean(tab) && pickable([tab]).length === 1;
  const moved = tab?.target !== hereTab?.target || host(tab?.url) !== host(hereTab?.url);
  hereTab = tab;
  $("task-here").disabled = !mine;
  if (!mine || moved) $("task-here").checked = false;
}

function finish() { // the Start's answer came, or never will: Start can be pressed again
  clearTimeout(pendingTimer);
  pending = null;
  taking = [];
  $("task-start").disabled = false;
}

// New task's Start: the user's words, model and account. With "Start it in this page", that tab is handed over too.
function start() {
  const text = $("task").value.trim();
  if (!text) {
    flash("Write what the agent should do");
    return;
  }
  if (pending) return; // one Start, one agent
  const why = folders.ready() || uploads.why();
  if (why) {
    flash(why);
    return;
  }
  const folder = folders.value();
  const files = uploads.ids();
  const here = $("task-here").checked ? bar.current() : null;
  pending = `c${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  taking = files;
  $("task-start").disabled = true;
  const account = $("task-account").hidden ? {} : { account: $("task-account").value };
  const sent = link.send({ type: "new_task", text, skills: [], model: $("task-model").value, request: pending,
                           ...account, ...(folder ? { folder } : {}), ...(here ? { adopt: here.target } : {}),
                           ...(files.length ? { attachments: files } : {}) });
  if (!sent) {
    finish();
    flash(NOT_CONNECTED);
    return;
  }
  pendingTimer = setTimeout(finish, 10000);
}

function useModel(value) { // the model picked last, in AI Home or Mission Control: the app keeps it
  if (value && [...$("task-model").options].some((option) => option.value === value)) $("task-model").value = value;
}

function handle(message) {
  folders?.onMessage(message);
  uploads?.onMessage(message);
  switch (message.type) {
    case "snapshot":
      uploads?.lost(); // a new connection: the app dropped the files staged for the old one
      agents.clear();
      for (const agent of message.agents || []) agents.set(agent.id, agent);
      accounts = message.accounts || [];
      fillPicker($("task-account"), accounts);
      useModel(message.settings?.model || message.default_model);
      if (pending) finish(); // a new connection: an unanswered Start can be pressed again
      link.send({ type: "accounts" }); // each account's status, now
      link.send({ type: "permission_rules" });
      break;
    case "agent":
      agents.set(message.agent.id, message.agent);
      break;
    case "agent_closed":
      agents.delete(message.id);
      break;
    case "accounts":
      accounts = message.accounts || [];
      fillPicker($("task-account"), accounts);
      break;
    case "settings":
      useModel(message.model);
      break;
    case "created":
      if (pending && message.request === pending) {
        const took = taking;
        finish();
        uploads.taken(took); // the app moved those into the agent's folder
        $("task").value = "";
        $("task-here").checked = false;
        pickDefault($("task-account"), accounts);
        setNew(false);
        flash(`Started ${agentLabel(agents.get(message.id) || { id: message.id })}`);
      }
      break;
    case "error":
      if (pending && message.request === pending) finish();
      if (message.text) flash(String(message.text));
      break;
  }
  renderAgents();
  renderNeeds();
  bar?.onMessage(message);
  talk?.onMessage(message);
}

function hide() { // the chat's window hides (AI Browser's own app); a page opened by itself has nothing to hide
  window.aib?.chat?.("hide");
}

const link = connect({ view: "chat", onMessage: handle, onState: setStatus });
guardLinks(link, { ours: () => link.send({ type: "show_app" }) }); // a website opens in Brave; our pages, in AI Home
bar = mountPageBar($("page"), { link, aib: window.aib, agents: ordered, input: $("talk-text"), onSay: flash,
                                onChange: hereChanged });
folders = mountFolderPicker({ select: $("task-folder"), box: $("folder-ask") },
                            (message) => link.send(message)); // agent powers: the task's folder
uploads = mountUploads({ list: $("attached"), send: (message) => link.send(message), note: flash });
takeFiles($("task"), (files) => uploads.add(files), { area: $("new") }); // pasted or dropped: as Build a Mission
takeFiles($("talk-text"), (files, { text }) => { // the Brain's box: text only, and nothing opens by itself
  if (!text) flash(PICTURES_HERE);
});
talk = mountTalk({ panel: $("talk"), micButton: $("mic"), link, voice: quiet, hintVoice: false,
                   model: () => $("task-model").value,
                   openAgent: (id) => link.send({ type: "show_app", agent: id }),
                   openBrain: () => link.send({ type: "show_app", brain: true }),
                   aboutPage: () => bar.asking() });
$("hide").addEventListener("click", hide);
$("new-open").addEventListener("click", () => setNew($("new").hidden));
$("task-cancel").addEventListener("click", () => setNew(false));
$("task-start").addEventListener("click", start);
$("task").addEventListener("keydown", (event) => { // Command-Enter (Ctrl+Enter elsewhere) starts it too
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey) && !event.isComposing) {
    event.preventDefault();
    start();
  }
});
document.addEventListener("keydown", (event) => { // Esc hides the chat (during a talk turn, Esc ends the turn only)
  if (event.key === "Escape" && !event.defaultPrevented && !event.isComposing) hide();
});
