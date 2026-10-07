// Mission Control's drawer (moved here by the new look; what it shows is unchanged): an agent's state, its account and
// its move, Watch, Stop, Close, its ask at a usage limit, its permission or bot-check card, its plan and sub-agents,
// Your tabs and its chat; or the Brain's inbox. Everything from Claude or a page is set as text.
"use strict";

import { askBox, askKey } from "./accountui.js";
import { mountBrain } from "./brainui.js";
import { checkCard } from "./check.js";
import { agentLabel, createChat, el } from "./chat.js";
import { COLORS } from "./desk.js";
import { openLive } from "./nav.js";
import { permissionCard } from "./permission.js";
import { renderPlan, renderSubagents } from "./plan.js";
import { STATES, stateOf } from "./step.js";
import { mountYourTabs } from "./tablist.js";

export function mountDrawer({ link, agentOf, accounts, browserOf }) {
  const $ = (id) => document.getElementById(id);
  const send = (message) => link.send(message);
  const drawer = { id: null, parts: null, chat: null, brain: null, yourTabs: null };

  function setText(node, text) {
    if (node.textContent !== text) node.textContent = text;
  }

  function button(className, label, onClick) {
    const node = el("button", className, label);
    node.type = "button";
    node.addEventListener("click", onClick);
    return node;
  }

  function close() {
    $("drawer").hidden = true;
    Object.assign(drawer, { id: null, parts: null, chat: null, brain: null, yourTabs: null });
    $("drawer-body").replaceChildren();
  }

  function openBrain() { // the globe's click: the Brain's inbox
    close();
    setText($("drawer-title"), "The Brain");
    $("drawer-dot").style.background = "var(--accent)";
    const root = el("div", "drawer-brain");
    $("drawer-body").replaceChildren(root);
    drawer.brain = mountBrain(root, link, { openAgent: (id) => open(id) });
    $("drawer").hidden = false;
  }

  function renderYourTabs() { // Your tabs follows the tab list and the browser's state
    if (!drawer.yourTabs) return;
    const { tabs, scope, browser } = browserOf();
    drawer.yourTabs.render(tabs, { brave: browser?.kind === "brave", connected: browser?.state === "connected",
                                   name: browser?.name || "Brave", scope });
  }

  function sendChat() {
    const text = drawer.parts?.input.value.trim();
    if (!text || !drawer.id) return;
    if (link.send({ type: "send", id: drawer.id, text })) drawer.parts.input.value = "";
  }

  function fill(agent) { // the drawer's agent changed: its parts are updated in place
    if (!agent || agent.id !== drawer.id || !drawer.parts) return;
    const parts = drawer.parts;
    const rows = accounts();
    const state = stateOf(agent);
    $("drawer-dot").style.background = COLORS[agent.color] || COLORS.grey;
    setText($("drawer-title"), agentLabel(agent));
    const paused = Boolean(agent.limit) && state === "failed"; // at a usage limit: paused, not failed
    setText(parts.state, paused ? "paused" : STATES[state] || state);
    parts.state.className = `chip ${paused ? "waiting" : state}`;
    setText(parts.account, agent.account?.name || "");
    parts.account.hidden = rows.length < 2; // one account: nothing to tell apart
    setText(parts.moved, agent.moved || "");
    parts.moved.hidden = !agent.moved;
    const key = askKey(agent, rows); // the same ask as AI Home's row
    if (key !== parts.askKey) {
      parts.ask?.remove();
      parts.ask = askBox(agent, rows, send);
      if (parts.ask) parts.askSlot.append(parts.ask);
      parts.askKey = key;
    }
    setText(parts.status, agent.status || agent.last_action || "");
    parts.status.hidden = !parts.status.textContent;
    setText(parts.folder, agent.folder ? `Folder: ${agent.folder}` : "No folder: its own scratch folder");
    renderPlan(parts.plan, agent.todos); // agent powers, Decision 9: the agent's plan, live
    renderSubagents(parts.subs, agent.subagents); // Decision 8: each sub-agent, its task and its current action
    parts.watch.disabled = !agent.working_tab;
    parts.stop.hidden = !(agent.state === "working" || agent.state === "waiting" || agent.check);
    const check = agent.check; // a bot check waiting for the user: the same card as AI Home's
    if (check && parts.checkCard?.dataset.since !== String(check.since)) {
      parts.checkCard?.remove();
      parts.checkCard = checkCard(agent, send, {
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
      parts.card = permissionCard({ ...asking, agent: agent.id }, send, agent.name);
      parts.permission.append(parts.card);
    } else if (!asking && parts.card) {
      parts.card.remove();
      parts.card = null;
    }
  }

  function open(id, { tabs: showTabs = false } = {}) {
    const agent = agentOf(id);
    if (!agent) return;
    drawer.brain = null;
    drawer.id = id;
    const parts = { state: el("span", "chip"), status: el("div", "status muted"), buttons: el("div", "row buttons"),
                    permission: el("div", "permission-slot"), yourTabs: el("details", "your-tabs"),
                    messages: el("div", "messages"), composer: el("div", "composer-line"), input: el("textarea"),
                    card: null, account: el("span", "chip account"), moved: el("div", "status muted moved"),
                    askSlot: el("div", "ask-slot"), ask: null, askKey: "",
                    folder: el("div", "status muted folder"), plan: el("section", "plan"),
                    subs: el("section", "subagents") };
    parts.watch = button("watch", "Watch", () => {
      const current = agentOf(id);
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
    parts.composer.append(parts.input, button("primary", "Send", () => sendChat()));
    parts.input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        sendChat();
      }
    });
    drawer.yourTabs = mountYourTabs(parts.yourTabs, { send, agentId: () => id });
    parts.yourTabs.open = showTabs; // folded, unless the user asked to hand a tab over
    $("drawer-body").replaceChildren(parts.status, parts.moved, parts.folder, parts.buttons, parts.permission,
                                     parts.askSlot, parts.plan, parts.subs, parts.yourTabs, parts.messages,
                                     parts.composer);
    drawer.parts = parts;
    drawer.chat = createChat(parts.messages);
    drawer.chat.reset("Loading…");
    fill(agent);
    renderYourTabs();
    $("drawer").hidden = false;
    link.send({ type: "events", id });
  }

  $("drawer-close").addEventListener("click", close);

  return {
    open, openBrain, close, fill, tabsChanged: renderYourTabs,
    get id() { return drawer.id; },
    get isOpen() { return !$("drawer").hidden; },
    onMessage(message) {
      if (message.type?.startsWith("brain_")) drawer.brain?.onMessage(message); // the inbox in the drawer
      if (message.type === "agent_event" && message.id === drawer.id) {
        drawer.chat?.append(message.event);
      } else if (message.type === "agent_events" && message.id === drawer.id && drawer.chat) {
        drawer.chat.reset("No messages yet.");
        for (const event of message.events || []) drawer.chat.append(event);
      } else if (message.type === "accounts" && drawer.id) {
        fill(agentOf(drawer.id));
      }
    },
  };
}
