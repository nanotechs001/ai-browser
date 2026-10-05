// AI Browser's floating chat (/chat), in a small window of AI Browser's own app that stays above the others, beside
// Brave. The shortcut picked in Settings, or the menu-bar icon's Show chat, shows and hides it; Esc and ✕ hide it.
// It holds "This page" (the Brave tab you're on: pagebar.js) and the Brain's talk, typed or push-to-talk (talk.js).
// The Brain only proposes, and a question reads the page only while "Ask about it" is on. Every word from Claude,
// pages and agents is set as text.
import { connect } from "./link.js";
import { guardLinks } from "./nav.js";
import { mountPageBar } from "./pagebar.js";
import { mountTalk } from "./talk.js";

const $ = (id) => document.getElementById(id);
const NOT_CONNECTED = "Not connected: is `ai-browser app` running?";
const quiet = { enabled: false, say() {}, pause() {}, resume() {} }; // the chat answers in text: nothing speaks here
const agents = new Map(); // the open agents, by id
let model = "sonnet"; // the model picked last in AI Home or Mission Control: a card's Start uses it
let talk = null;
let bar = null;

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

function handle(message) {
  if (message.type === "snapshot") {
    agents.clear();
    for (const agent of message.agents || []) agents.set(agent.id, agent);
    model = message.settings?.model || message.default_model || model;
  } else if (message.type === "agent") {
    agents.set(message.agent.id, message.agent);
  } else if (message.type === "agent_closed") {
    agents.delete(message.id);
  } else if (message.type === "settings" && message.model) {
    model = message.model;
  } else if (message.type === "error" && message.text) {
    flash(String(message.text));
  }
  bar?.onMessage(message);
  talk?.onMessage(message);
}

function hide() { // the chat's window hides (AI Browser's own app); a page opened by itself has nothing to hide
  window.aib?.chat?.("hide");
}

const link = connect({ view: "chat", onMessage: handle, onState: setStatus });
guardLinks(link, { ours: () => link.send({ type: "show_app" }) }); // a website opens in Brave; our pages, in AI Home
bar = mountPageBar($("page"), { link, aib: window.aib, agents: () => [...agents.values()], input: $("talk-text"),
                                onSay: flash });
talk = mountTalk({ panel: $("talk"), micButton: $("mic"), link, voice: quiet, hintVoice: false, model: () => model,
                   openAgent: (id) => link.send({ type: "show_app", agent: id }),
                   openBrain: () => link.send({ type: "show_app", brain: true }),
                   aboutPage: () => bar.asking() });
$("hide").addEventListener("click", hide);
document.addEventListener("keydown", (event) => { // Esc hides the chat (during a talk turn, Esc ends the turn only)
  if (event.key === "Escape" && !event.defaultPrevented && !event.isComposing) hide();
});
