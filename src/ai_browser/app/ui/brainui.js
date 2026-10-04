// The Brain's inbox, shared by AI Home and the watcher's Brain page: only what is new or needs the user, each with
// what the Brain makes of it and what to do next. Message text is set as text, never as HTML. Approve sends the reply
// the user sees (and may have edited), once; the watcher then puts it in the reply box, and the user presses Send.
"use strict";

const KIND = { needs_reply: "needs your reply", new: "new" };
const SITES = { gmail: "Gmail", slack: "Slack", asana: "Asana" };
const STATES = { drafting: "Drafting…", filling: "Putting it in the reply box…",
                 filled: "It's in the reply box: press Send there when you're happy with it" };
const AGENT = { working: "working", waiting: "waiting in line", your_turn: "done", stopped: "stopped",
                failed: "failed", needs_you: "needs you" };
const COMPACT_LIMIT = 10;
const FINISHED = new Set(["your_turn", "stopped", "failed"]);
const HOLD = 15000; // a clicked Hand or Run waits this long for the item to change (its agent showing up)
const CARD_STATE = { // a send card's state line: the same three lines as talk.js (this file imports nothing)
  working: "It's working: it reads your words when it finishes what it's doing now.",
  waiting: "It's waiting in line: it reads your words when its turn comes.",
  permission: "It's waiting for your Allow or Deny: your words wait too, and don't answer it.",
};
const WATCHER_CARD = "Press Start or Send on this card in AI Browser: the watcher can't.";
const EXPIRED = "This has expired: ask again";

function digits(id) { // "a12" is 12: the watcher ships this file alone, so it works the number out itself
  const found = String(id || "").replace(/\D/g, "");
  return found ? Number(found) : null;
}

function cardHeading(card) {
  if (card.kind !== "message_agent") return "Start a NEW agent with your words:";
  const number = Number.isInteger(card.number) ? card.number : digits(card.agent);
  return `Send to ${number === null ? "" : `${number} · `}${card.name || "an agent"}:`;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function mountBrain(root, link, { compact = false, openAgent = null, cards = "view", openSetup = null } = {}) {
  const head = el("div", "brain-head");
  const counts = el("span", "brain-others muted");
  const watcher = el("span", "brain-watcher");
  head.append(counts, watcher);
  const list = el("div", "brain-items list");
  const more = el("button", "brain-more ghost");
  more.hidden = true;
  root.replaceChildren(head, list, more);
  const items = new Map(); // id -> the item as the Brain describes it
  const rows = new Map(); // id -> its row, built once and updated in place
  let order = []; // ids, newest first
  let others = 0;
  let watcherOn = true;
  let showAll = !compact;
  let setupUrl = null;
  let focusing = null;

  if (!openSetup && location.protocol === "chrome-extension:") { // the watcher's Brain page: the server's address
    fetch(chrome.runtime.getURL("config.json"), { cache: "no-store" }).then((answer) => answer.json()).then((config) => {
      setupUrl = `${config.server}/setup#brave`;
      renderHead();
    }).catch(() => {});
  }
  more.addEventListener("click", () => {
    showAll = !showAll;
    render();
  });

  function send(message) {
    const sent = link.send(message);
    if (!sent) counts.textContent = "Not connected: is ai-browser app running?";
    return sent;
  }

  function row(id) {
    if (rows.has(id)) return rows.get(id);
    const node = el("div", "brain-item card");
    node.dataset.id = id;
    const p = {
      line: el("div", "brain-line"), site: el("span", "chip site"), kind: el("span", "chip kind"),
      sender: el("span", "sender"), subject: el("span", "subject"), summary: el("div", "summary"),
      why: el("div", "why muted"), note: el("div", "note muted"), card: el("div", "brain-card"),
      agent: el(openAgent ? "button" : "div", "agent"),
      draftBox: el("div", "brain-draft"), draft: el("textarea", "draft-text"),
      approve: el("button", "approve primary", "Approve: put it in the reply box"), copy: el("button", "copy", "Copy"),
      actions: el("div", "brain-actions"), draftButton: el("button", "draft", "Draft reply"), run: el("button", "run"),
      done: el("button", "done ghost", "Done"), say: el("input", "say"), tell: el("button", "tell", "Tell the Brain"),
      hand: el("button", "hand", "Hand to agent"),
    };
    p.draft.rows = 4;
    p.card.hidden = true;
    p.draft.setAttribute("aria-label", "The reply: edit it before you approve");
    p.say.placeholder = "What should happen? For example: draft a polite no, or check the page";
    p.say.setAttribute("aria-label", "Tell the Brain, or what the agent should do");
    p.line.append(p.site, p.kind, p.sender, p.subject);
    const draftButtons = el("div", "row");
    draftButtons.append(p.approve, p.copy);
    p.draftBox.append(p.draft, draftButtons);
    p.actions.append(p.draftButton, p.run, p.done);
    const say = el("div", "brain-say");
    say.append(p.say, p.tell, p.hand);
    node.append(p.line, p.summary, p.why, p.note, p.card, p.agent, p.draftBox, p.actions, say);
    node.parts = p;
    node.version = -1;
    p.draftButton.addEventListener("click", () => {
      if (send({ type: "draft", id })) p.draftButton.disabled = true;
    });
    p.approve.addEventListener("click", () => {
      const item = items.get(id);
      if (!item || p.approve.disabled || !p.draft.value.trim()) return;
      p.approve.disabled = true; // one approval per draft: the Brain fills the reply box once
      send({ type: "approve", id, text: p.draft.value, version: item.draft_version });
    });
    p.copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(p.draft.value);
        p.copy.textContent = "Copied";
      } catch {
        p.copy.textContent = "Select and copy it";
      }
    });
    p.done.addEventListener("click", () => send({ type: "done", id }));
    p.tell.addEventListener("click", () => {
      const text = p.say.value.trim();
      if (!text) return;
      const message = { type: "tell", id, text };
      if (cards === "confirm" && p.card.dataset.id) { // a typed yes runs this card as its box now reads
        message.proposal = p.card.dataset.id;
        if (p.cardTask) message.task = p.cardTask.value;
      }
      if (send(message)) p.say.value = "";
    });
    p.hand.addEventListener("click", () => {
      if (p.hand.disabled) return;
      if (send({ type: "hand", id, instruction: p.say.value.trim() })) {
        p.say.value = "";
        hold(node, "hand");
      }
    });
    p.run.addEventListener("click", () => {
      const item = items.get(id);
      if (!item?.workflow || p.run.disabled) return;
      if (send({ type: "workflow_run", slug: item.workflow, item: id })) hold(node, "run");
    });
    p.agent.addEventListener("click", () => {
      const item = items.get(id);
      if (openAgent && item?.agent_id) openAgent(item.agent_id);
    });
    p.say.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.isComposing) {
        event.preventDefault();
        p.tell.click();
      }
    });
    rows.set(id, node);
    return node;
  }

  function hold(node, button) { // one click, one agent: the button waits until the item changes
    node.held = { ...node.held, [button]: true };
    node.parts[button].disabled = true;
    clearTimeout(node.holding);
    node.holding = setTimeout(() => {
      node.held = {};
      if (items.has(node.dataset.id)) fill(node, items.get(node.dataset.id));
    }, HOLD);
  }

  function showCard(node, card) { // an inbox card: Start (Send) and Cancel in AI Browser; on the watcher, words only
    const p = node.parts;
    clearTimeout(node.cardTimer);
    p.card.replaceChildren();
    p.card.dataset.id = card?.id || "";
    p.card.hidden = !card;
    p.cardTask = null;
    if (!card) return;
    p.card.append(el("p", "brain-card-head", cardHeading(card)));
    const state = card.kind === "message_agent" ? CARD_STATE[card.state] : "";
    if (cards === "confirm") {
      const task = el("textarea", "brain-card-task");
      task.rows = 2;
      task.value = String(card.task || ""); // the user's own words, which they may edit
      task.setAttribute("aria-label", "Your words");
      p.cardTask = task;
      const go = el("button", "brain-card-go primary", card.kind === "message_agent" ? "Send" : "Start");
      const cancel = el("button", "brain-card-cancel ghost", "Cancel");
      go.addEventListener("click", () => { // one click, one run: the app closes the card before it runs
        if (go.disabled) return;
        if (send({ type: "tell_confirm", id: node.dataset.id, proposal: card.id, task: task.value })) {
          go.disabled = true;
          cancel.disabled = true;
        }
      });
      cancel.addEventListener("click", () => {
        if (!cancel.disabled && send({ type: "tell_dismiss", id: node.dataset.id, proposal: card.id })) {
          go.disabled = true;
          cancel.disabled = true;
        }
      });
      const buttons = el("div", "row");
      buttons.append(go, cancel, el("span", "muted", "or type yes"));
      p.card.append(task);
      if (state) p.card.append(el("p", "brain-card-state muted", state));
      p.card.append(buttons);
    } else {
      p.card.append(el("blockquote", "brain-card-words", String(card.task || "")));
      if (state) p.card.append(el("p", "brain-card-state muted", state));
      p.card.append(el("p", "brain-card-note muted", WATCHER_CARD));
    }
    const seconds = Number(card.expires_in);
    node.cardTimer = setTimeout(() => { // past its two minutes: the app won't run it any more either
      if (p.card.dataset.id !== card.id) return;
      p.cardTask = null;
      p.card.replaceChildren(el("p", "muted", EXPIRED));
    }, (Number.isFinite(seconds) ? Math.max(0, seconds) : 120) * 1000);
  }

  function fill(node, item) {
    const p = node.parts;
    if (node.item !== item) { // the item changed: what a click was waiting for has happened
      node.item = item;
      node.held = {};
    }
    node.dataset.state = item.state;
    p.site.textContent = SITES[item.site] || String(item.site || "").replace(/^custom:/, "");
    p.kind.textContent = KIND[item.kind] || item.kind;
    p.kind.dataset.kind = item.kind;
    p.sender.textContent = item.sender || "";
    p.subject.textContent = item.subject || "";
    p.summary.textContent = item.summary || "";
    p.why.textContent = item.why ? `Why: ${item.why}` : "";
    p.why.hidden = compact || !item.why;
    p.note.textContent = item.note || STATES[item.state] || "";
    p.note.hidden = !p.note.textContent;
    const card = item.card || null;
    if ((card?.id || "") !== (p.card.dataset.id || "")) showCard(node, card); // rebuilt only for a new card
    p.agent.hidden = !item.agent_id;
    if (item.agent_id) {
      const state = AGENT[item.agent_state] || item.agent_state || "starting";
      const number = digits(item.agent_id);
      const result = item.result ? ` · ${item.result}` : "";
      p.agent.textContent = `Agent${number === null ? "" : ` ${number}`}: ${state}${result}`;
    }
    const drafted = Boolean(item.draft) && ["draft_ready", "filling", "filled"].includes(item.state);
    p.draftBox.hidden = !drafted;
    if (drafted && node.version !== item.draft_version) { // a new draft; edits to the current one are kept
      p.draft.value = item.draft;
      p.draft.rows = Math.min(12, Math.max(4, item.draft.split("\n").length + 1)); // the whole draft, sign-off too
      node.version = item.draft_version;
    }
    p.approve.disabled = item.state !== "draft_ready";
    p.draftButton.disabled = ["drafting", "filling"].includes(item.state);
    p.draftButton.textContent = item.draft ? "Draft again" : "Draft reply";
    const busy = Boolean(item.agent_id) && !FINISHED.has(item.agent_state); // its agent is still at it
    p.hand.disabled = busy || Boolean(node.held?.hand);
    p.run.disabled = busy || Boolean(node.held?.run);
    p.run.hidden = !item.workflow;
    p.run.textContent = item.workflow ? `Run ${item.workflow_name || item.workflow}` : "";
  }

  function renderHead() {
    const needs = order.filter((id) => items.get(id)?.kind === "needs_reply").length;
    const fresh = order.length - needs;
    counts.textContent = order.length
      ? [needs && `${needs} need you`, fresh && `${fresh} new`, others && `${others} others`].filter(Boolean).join(" · ")
      : others ? `${others} others, nothing needs you` : "Nothing new";
    watcher.replaceChildren();
    if (!watcherOn) {
      watcher.append("The watcher isn't connected in Brave");
      if (openSetup) { // AI Browser's window: the setup steps in a small window of their own
        const setup = el("button", "brain-setup link", "Set it up");
        setup.type = "button";
        setup.addEventListener("click", () => openSetup());
        watcher.append(" · ", setup);
      } else if (setupUrl) { // the watcher's Brain page, in Brave: a new tab there is right
        const setup = el("a", "brain-setup", "Set it up");
        setup.href = setupUrl;
        setup.target = "_blank";
        watcher.append(" · ", setup);
      }
    }
  }

  function render() {
    for (const [id, node] of rows) {
      if (!items.has(id)) {
        node.remove();
        rows.delete(id);
      }
    }
    const visible = showAll ? order : order.slice(0, COMPACT_LIMIT);
    const shown = new Set(visible);
    for (const node of [...list.children]) {
      if (!shown.has(node.dataset.id)) node.remove();
    }
    let previous = null;
    for (const id of visible) {
      const node = row(id);
      fill(node, items.get(id));
      const next = previous ? previous.nextSibling : list.firstChild;
      if (node !== next) list.insertBefore(node, next);
      previous = node;
    }
    if (!order.length) list.append(el("p", "empty", "Nothing needs you right now."));
    more.hidden = !compact || order.length <= COMPACT_LIMIT;
    more.textContent = showAll ? "Show fewer" : `Show all ${order.length}`;
    renderHead();
    if (focusing && rows.has(focusing)) focus(focusing);
  }

  function settings(message) {
    others = message.others || 0;
    watcherOn = Boolean(message.watcher);
  }

  function onMessage(message) {
    if (message.type === "brain_snapshot") {
      items.clear();
      order = [];
      for (const item of message.items || []) {
        items.set(item.id, item);
        order.push(item.id);
      }
      settings(message);
      render();
    } else if (message.type === "brain_item" && message.item?.id) {
      if (!items.has(message.item.id)) order.unshift(message.item.id);
      items.set(message.item.id, message.item);
      render();
    } else if (message.type === "brain_item_gone") {
      items.delete(message.id);
      order = order.filter((id) => id !== message.id);
      render();
    } else if (message.type === "brain_state") {
      settings(message);
      renderHead();
    }
  }

  function refresh() {
    link.send({ type: "brain" });
  }

  function focus(id) {
    const node = rows.get(id);
    focusing = node ? null : id;
    if (!node) return;
    node.scrollIntoView({ block: "center" });
    node.parts.say.focus();
  }

  link.whenOpen().then(refresh);
  render();
  return { onMessage, refresh, focus };
}
