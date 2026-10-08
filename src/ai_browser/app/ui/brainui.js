// The Brain's inbox, in AI Home and Mission Control: only what is new or needs the user, each with what the Brain
// makes of it and what to do next; above them, its hand-offs (handoffCard). Message text is set as text, never as
// HTML. Use draft sends the reply the user sees (and may have edited), once; AI Browser then puts it in the reply box,
// and the user presses Send.
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
const EXPIRED = "This has expired: ask again";
const OPEN = new Set(["counting", "waiting"]); // a hand-off still open: Send now (Send, Start) and Cancel
const FROM = { you: "From your words", agent: "From an agent's result", gmail: "From an email in Gmail",
               slack: "From a Slack message", asana: "From an Asana task", pages: "From a part of a page you watch" };
const SHOWN_AFTER = 5000; // ms a slot shows a hand-off that is done (its note), before it empties

function digits(id) { // "a12" is 12: this file imports nothing, so it works the number out itself
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

// A hand-off's card (the brain-delegation spec, 5): "Giving 2 · Research competitors:", the instruction word for word,
// where it came from, and Send now and Cancel while it counts down (the seconds left), Send and Cancel while it waits,
// or Start and Cancel for a NEW agent the Brain suggests; once done, what happened. One click each: the app runs a card
// once. Every word is set as text.
export function handoffCard(handoff, send) {
  const card = el("div", "handoff card");
  card.dataset.id = String(handoff.id || "");
  card.dataset.state = String(handoff.state || "");
  const head = el("p", "handoff-head");
  if (handoff.kind === "start") {
    head.textContent = "Start a NEW agent with this task:";
  } else {
    const number = Number.isInteger(handoff.number) ? handoff.number : digits(handoff.agent);
    head.append("Giving ", el("strong", "", `${number === null ? "" : `${number} · `}${handoff.name || "an agent"}`),
                ":");
  }
  const line = el("p", "handoff-line muted");
  card.append(head, el("blockquote", "handoff-words", String(handoff.instruction || "")),
              el("p", "handoff-from muted", FROM[handoff.source] || ""), line);
  if (OPEN.has(handoff.state)) {
    const go = el("button", "handoff-go primary",
                  handoff.kind === "start" ? "Start" : handoff.state === "counting" ? "Send now" : "Send");
    const cancel = el("button", "handoff-cancel ghost", "Cancel");
    for (const [button, type] of [[go, "handoff_send"], [cancel, "handoff_cancel"]]) {
      button.type = "button";
      button.addEventListener("click", () => {
        if (!button.disabled && send({ type, id: handoff.id })) go.disabled = cancel.disabled = true;
      });
    }
    const buttons = el("div", "row");
    buttons.append(go, cancel);
    card.append(buttons);
  }
  if (handoff.state === "counting") { // the seconds left, as the app counts them
    const ends = Date.now() + (Number(handoff.seconds) || 0) * 1000;
    const tick = () => {
      const left = Math.max(0, Math.ceil((ends - Date.now()) / 1000));
      line.textContent = `Sends in ${left} s, unless you cancel`;
      if (left > 0 && card.dataset.state === "counting") setTimeout(tick, 250);
    };
    tick();
  } else {
    line.textContent = handoff.note
      || (handoff.state === "waiting" ? (handoff.kind === "start" ? "Waiting for your Start" : "Waiting for your Send")
        : "");
  }
  return card;
}

// The Brain's hand-offs, in a slot of their own (under Mission Control's view switch, in the floating chat): every one
// counting down, newest first, so none counts down unseen; else the newest waiting for Send. Each stays until it is
// done, and the newest done shows what happened for a moment while nothing else is open. The Brain's inbox lists them
// all.
export function mountHandoffSlot(slot, send) {
  const handoffs = new Map(); // id -> the hand-off, oldest first
  function render() {
    const all = [...handoffs.values()].reverse(); // newest first
    const counting = all.filter((one) => one.state === "counting");
    const shown = counting.length ? counting : [all.find((one) => one.state === "waiting") || all[0]].filter(Boolean);
    const drawn = new Map([...slot.children].map((card) => [card.dataset.id, card]));
    const cards = shown.map((one) => { // a card as it is stays (its countdown runs on); a changed one is drawn again
      const current = drawn.get(one.id);
      return current?.dataset.state === one.state ? current : handoffCard(one, send);
    });
    for (const card of slot.children) if (!cards.includes(card)) card.dataset.state = "replaced"; // its countdown stops
    slot.replaceChildren(...cards);
    slot.hidden = !cards.length;
  }
  function keep(handoff) {
    if (!handoff?.id) return;
    handoffs.set(handoff.id, handoff);
    if (!OPEN.has(handoff.state)) { // done: shown for a moment, then gone from the slot
      setTimeout(() => {
        if (handoffs.get(handoff.id) === handoff) {
          handoffs.delete(handoff.id);
          render();
        }
      }, SHOWN_AFTER);
    }
  }
  return {
    onMessage(message) {
      if (message.type === "brain_snapshot") {
        handoffs.clear();
        for (const handoff of message.handoffs || []) if (OPEN.has(handoff.state)) keep(handoff);
        render();
      } else if (message.type === "brain_handoff") {
        keep(message.handoff);
        render();
      }
    },
  };
}

export function mountBrain(root, link, { compact = false, openAgent = null, openSettings = null } = {}) {
  const head = el("div", "brain-head");
  const counts = el("span", "brain-others muted");
  const reading = el("span", "brain-reading muted"); // how reading the user's tabs stands (Settings → Brain)
  const turnOn = el("button", "ghost brain-turn-on", "Turn it on in Settings");
  turnOn.hidden = true;
  turnOn.addEventListener("click", () => openSettings?.());
  head.append(counts, reading, turnOn);
  const handoffs = el("div", "brain-handoffs"); // this run's hand-offs, newest first, each updated in place
  const list = el("div", "brain-items list");
  const more = el("button", "brain-more ghost");
  more.hidden = true;
  root.replaceChildren(head, handoffs, list, more);
  const handoffNodes = new Map(); // id -> its card
  const items = new Map(); // id -> the item as the Brain describes it
  const rows = new Map(); // id -> its row, built once and updated in place
  let order = []; // ids, newest first
  let others = 0;
  let readingState = "off";
  let showAll = !compact;
  let focusing = null;

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
      approve: el("button", "approve primary", "Use draft: put it in the reply box"),
      copy: el("button", "copy", "Copy"),
      actions: el("div", "brain-actions"), draftButton: el("button", "draft", "Draft reply"), run: el("button", "run"),
      done: el("button", "done ghost", "Done"), say: el("input", "say"), tell: el("button", "tell", "Tell the Brain"),
      hand: el("button", "hand", "Hand to agent"),
    };
    p.draft.rows = 4;
    p.card.hidden = true;
    p.draft.setAttribute("aria-label", "The reply: edit it before you use it");
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
      if (p.card.dataset.id) { // a typed yes runs this card as its box now reads
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

  function showCard(node, card) { // an inbox card: its words, which the user may edit, and Start (Send) and Cancel
    const p = node.parts;
    clearTimeout(node.cardTimer);
    p.card.replaceChildren();
    p.card.dataset.id = card?.id || "";
    p.card.hidden = !card;
    p.cardTask = null;
    if (!card) return;
    p.card.append(el("p", "brain-card-head", cardHeading(card)));
    const state = card.kind === "message_agent" ? CARD_STATE[card.state] : "";
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
    reading.textContent = { off: "Reading your tabs is off", waiting: "Waiting for Brave" }[readingState] || "";
    turnOn.hidden = readingState !== "off" || !openSettings;
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
    readingState = message.reading || "off";
  }

  function showHandoff(handoff) { // a new one on top; a changed one in its place
    if (!handoff?.id) return;
    const node = handoffCard(handoff, send);
    const old = handoffNodes.get(handoff.id);
    if (old) {
      old.dataset.state = "replaced"; // its countdown stops
      old.replaceWith(node);
    } else {
      handoffs.prepend(node);
    }
    handoffNodes.set(handoff.id, node);
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
      handoffs.replaceChildren();
      handoffNodes.clear();
      for (const handoff of message.handoffs || []) showHandoff(handoff);
      render();
    } else if (message.type === "brain_handoff") {
      showHandoff(message.handoff);
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
