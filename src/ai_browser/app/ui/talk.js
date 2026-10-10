// Talking to the Brain, in Mission Control and in the floating chat: push-to-talk. The mic opens only while the user
// holds Space or the mic button (or from one click on the button to the next) and its tracks stop when the turn ends:
// there is no wake word
// and nothing listens in the background. The sound goes to `ai-browser app` over the 127.0.0.1 link and becomes text
// on this computer; the words then go to the Brain like typed words, and its answer shows in the log and the bubble.
// Every word here is set with textContent.
"use strict";

import { CONSTRAINTS, openMic } from "./mic.js";
import { agentLabel } from "./chat.js";

const HOLD_MS = 300; // a shorter press of Space is a slip; a shorter press of the mic button is a click (it toggles)
const LOG_LINES = 6; // the lines a talk keeps, unless its page asks for more (Mission Control's Ask AI: this run's)
const BYTES_PER_SECOND = 32000; // 16 kHz, 16-bit, mono
const NOT_CONNECTED = "Not connected: is `ai-browser app` running?";
const CONTROLS = "button, input, textarea, select, a, label, summary, [contenteditable]";
const MODELS = [["sonnet", "Sonnet · balanced"], ["opus", "Opus · best"], ["haiku", "Haiku · fastest"]];
const GO = { start_agent: "Start", message_agent: "Send" }; // anything else is a draft card's "Draft it"
const PAST = { start_agent: "Start a new agent", message_agent: "Send to an agent", draft_reply: "Draft a reply",
               give: "Your words for an agent", start: "Start a new agent" }; // a kept chat's cards, as text
const SEND_STATE = { // what happens to the words, from the agent's state when the card was made
  working: "It's working: it reads your words when it finishes what it's doing now.",
  waiting: "It's waiting in line: it reads your words when its turn comes.",
  permission: "It's waiting for your Allow or Deny: your words wait too, and don't answer it.",
};
const START_HINT = "It can't see your tabs. After it starts, open it and use Your tabs → Give to this agent. Or put "
  + "the page's address in the words.";
const SEND_HINT = "It can't see your tabs: use Your tabs → Give to this agent. Or put the page's address in the "
  + "words.";

export function megabytes(bytes) { // the page's sizes: 1 MB is 1,000,000 bytes, rounded to whole MB
  return `${Math.round((Number(bytes) || 0) / 1e6)} MB`;
}

export function browserName(nav = navigator) { // the browser this page runs in, for the steps it names
  if (/\bElectron\//.test(String(nav.userAgent || ""))) return "AI Browser"; // AI Browser's own app (Electron)
  const brands = (nav.userAgentData?.brands || []).map((entry) => String(entry?.brand || ""));
  if (brands.some((brand) => /brave/i.test(brand))) return "Brave";
  if (brands.some((brand) => /edge/i.test(brand))) return "Microsoft Edge";
  return "Google Chrome";
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function newId(prefix) { // within the app's ^[A-Za-z0-9-]{1,40}$
  return `${prefix}${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function base64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let start = 0; start < bytes.length; start += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(start, start + 0x8000));
  }
  return btoa(binary);
}

// aboutPage(): the floating chat's "Ask about it": {target, site}, the tab a question reads then and the site the user
// marked on it, or null. hintVoice: say once that Voice reads answers aloud (Mission Control has the switch; the chat
// answers in text only).
// fill(words): the page may take heard words into its own box instead (Mission Control's composer, while the Brain's
// chat is closed): true when it did, and the Brain isn't asked. keep: how many lines the log keeps, the newest at the
// bottom. reveal(): a line, a card or a notice is shown (Mission Control opens the Brain's chat for it).
export function mountTalk({ panel, micButton, link, voice, onState = () => {}, openAgent = () => {},
                            openBrain = () => {}, model = () => "sonnet", aboutPage = () => null,
                            hintVoice = true, fill = () => false, keep = LOG_LINES, reveal = () => {} }) {
  const log = panel.querySelector(".talk-log");
  const status = panel.querySelector(".talk-status");
  const notice = panel.querySelector(".talk-notice");
  const card = panel.querySelector(".talk-card");
  const form = panel.querySelector(".talk-form");
  const input = form.querySelector("input");
  let talkId = newId("k"); // one talk per page load, or the kept chat Mission Control's chat shows (setTalk)
  let hearing = null; // the app's latest hearing_status
  let state = "idle";
  let turn = null; // the turn being recorded
  let finishing = null; // the turn whose words are being turned into text
  let asking = null; // the brain_ask request waiting for its answer
  let lastYou = null; // that question's "You: …" line
  let hinted = false; // "Switch on Voice to hear answers" is said once
  let proposal = null; // the open proposal card: {id, kind, box, picker, node, buttons, timer}
  let confirming = null; // the brain_confirm request waiting for its answer

  function setState(next) {
    state = next;
    panel.dataset.state = next;
    micButton.setAttribute("aria-pressed", String(next === "listening"));
    onState(next);
  }

  function show() {
    panel.hidden = false;
  }

  function progress(text) { // what is happening now: listening, turning words into text, thinking
    if (text) show();
    status.textContent = text;
  }

  function tell(text, open = true) { // a word for the user, kept until the next press; open: the page shows it
    if (text) {
      show();
      if (open) reveal();
    }
    notice.textContent = text;
  }

  function line(who, text) {
    show();
    reveal();
    const node = el("li", who === "You" ? "you" : "brain", `${who}: ${text}`);
    log.append(node);
    while (log.children.length > keep) log.firstElementChild.remove();
    log.scrollTop = log.scrollHeight; // the newest line in view, at the bottom
    return node;
  }

  function row(...nodes) {
    const node = el("div", "row");
    node.append(...nodes);
    return node;
  }

  function button(label, className, onClick) {
    const node = el("button", className, label);
    node.type = "button";
    node.addEventListener("click", onClick);
    return node;
  }

  function setCard(...nodes) {
    card.replaceChildren(...nodes);
    if (nodes.length) {
      show();
      reveal();
    }
  }

  function closeCard() {
    card.replaceChildren();
  }

  function listening(seconds) {
    return `Listening… let go to finish · ${seconds} s`;
  }

  function setupCard(current) { // talking isn't ready: what is missing, and the one step that fixes it
    const box = el("div", "talk-setup");
    const later = () => {
      closeCard();
      setState("idle");
    };
    const size = megabytes(current.size_bytes);
    const download = () => link.send({ type: "hearing_download" }); // the only way the model is fetched
    if (current.state === "no_engine") {
      const steps = el("p");
      steps.append("Talking needs one extra part on this computer. In the ai-browser folder, run ",
                   el("code", "", "uv sync --extra voice"), ", then restart ", el("code", "", "ai-browser app"),
                   ". It downloads faster-whisper and the Python packages it needs, from PyPI.");
      box.append(steps);
      if (current.platform === "mac") {
        box.append(el("p", "muted", "Or use your Mac's Dictation in any text box: press the Microphone key, or the "
                      + "Dictation shortcut in System Settings → Keyboard."));
      } else if (current.platform === "windows") {
        box.append(el("p", "muted", "Or use Voice Access (Windows 11), which runs on this PC."));
      }
      box.append(row(button("OK", "ghost", later)));
    } else if (current.state === "downloading") {
      const bar = el("progress");
      bar.max = Number(current.size_bytes) || 1;
      bar.value = Number(current.done_bytes) || 0;
      box.append(el("p", "", `Downloading the speech model: ${Math.round((Number(current.done_bytes) || 0) / 1e6)} of `
                    + size), bar, row(button("Cancel", "ghost cancel", () => link.send({ type: "hearing_cancel" }))));
    } else if (current.state === "failed") {
      const reason = String(current.reason || "The download failed");
      if (reason.startsWith("The speech model couldn't load")) {
        box.append(el("p", "", `${reason}. Download it again.`),
                   row(button(`Download ${size}`, "primary download", download), button("Not now", "ghost", later)));
      } else {
        box.append(el("p", "", reason),
                   row(button("Try again", "primary download", download), button("Not now", "ghost", later)));
      }
    } else { // no_model
      box.append(el("p", "", `To understand speech on this computer, AI Browser needs the English speech model: `
                    + `${current.model}, ${size}, from Hugging Face. It's saved in ${current.folder}. Your voice `
                    + "never leaves this computer; your words go to Claude, like typed text."),
                 row(button(`Download ${size}`, "primary download", download), button("Not now", "ghost", later)));
    }
    return box;
  }

  function micProblem(error) { // getUserMedia's refusals, in plain words for this browser and this computer
    const name = browserName();
    const system = hearing?.platform;
    if (error?.name === "NotAllowedError" && /system/i.test(String(error?.message || ""))) {
      if (system === "mac") {
        return `macOS blocks the microphone for ${name}: System Settings → Privacy & Security → Microphone → turn `
          + `on ${name}.`;
      }
      if (system === "windows") {
        return "Windows blocks the microphone: Settings → Privacy & security → Microphone → let desktop apps use it.";
      }
      return `This computer blocks the microphone for ${name}.`;
    }
    if (error?.name === "NotAllowedError") {
      return `The microphone is blocked for AI Browser. Open ${name}'s Settings → Privacy and security → Site `
        + `settings → Microphone, and allow ${location.host}.`; // the browser lists the site by its address
    }
    if (error?.name === "NotFoundError") return "No microphone found.";
    if (error?.name === "NotReadableError") return "The microphone is busy, or blocked by the system.";
    return "The microphone couldn't start.";
  }

  function problemCard(text) {
    const box = el("div", "talk-problem");
    box.append(el("p", "", text), row(button("OK", "ghost", closeCard)));
    return box;
  }

  function explainCard() { // before the browser's own question, the first time: what it is, and which choice to make
    const name = browserName();
    const box = el("div", "talk-explain");
    const first = el("p");
    first.append(`${name} will now ask to use your microphone. Choose `,
                 el("strong", "", "Allow while visiting the site"), " (or ", el("strong", "", "Allow"), "), not ",
                 el("strong", "", "Allow this time"), ", so it doesn't ask every time.");
    box.append(first);
    if (hearing?.platform === "mac") {
      box.append(el("p", "", `macOS may also ask once whether ${name} may use the microphone: choose Allow (or OK).`));
    } else if (hearing?.platform === "windows") {
      box.append(el("p", "", "If nothing happens, Windows may be blocking the microphone: Settings → Privacy & "
                    + "security → Microphone → let desktop apps use it."));
    }
    box.append(el("p", "muted", "The mic is on only while you hold Space or the mic button, or from a click on the "
                  + "mic button until you click it again."),
               row(button("Continue", "primary continue", allow), button("Not now", "ghost", () => {
                 closeCard();
                 setState("idle");
               })));
    return box;
  }

  async function allow() { // Continue: the browser asks now; nothing is recorded, and the tracks stop at once
    try {
      const stream = await navigator.mediaDevices.getUserMedia(CONSTRAINTS);
      for (const track of stream.getTracks()) track.stop();
      closeCard();
      setState("idle");
      tell("Ready: hold Space to talk");
    } catch (error) {
      setState("idle");
      setCard(problemCard(micProblem(error)));
    }
  }

  function wordsBox(value, name) { // the user's own words, which they may edit before Start or Send
    const text = el("textarea", "talk-task");
    text.rows = 2;
    text.value = String(value || "");
    text.setAttribute("aria-label", name);
    return text;
  }

  function showProposal(offer) { // the Brain's proposal: it runs only on Start (Send, Draft it) or a plain yes
    closeProposal();
    const box = el("div", "talk-proposal");
    box.dataset.kind = String(offer.kind || "");
    const entry = { id: String(offer.id || ""), kind: offer.kind, box: null, picker: null, node: box, buttons: [],
                    timer: null };
    if (offer.kind === "start_agent") {
      const text = wordsBox(offer.task, "The agent's task");
      const picker = el("select", "talk-model");
      picker.setAttribute("aria-label", "Model");
      for (const [value, label] of MODELS) {
        const option = el("option", "", label);
        option.value = value;
        picker.append(option);
      }
      const last = model(); // the model last picked (the task bar's, from the app's settings)
      picker.value = MODELS.some(([value]) => value === last) ? last : String(offer.model || "sonnet");
      entry.box = text;
      entry.picker = picker;
      box.append(el("p", "", "Start a NEW agent with your words:"), text, picker);
      if (offer.tab_hint) box.append(el("p", "talk-hint muted", START_HINT));
    } else if (offer.kind === "message_agent") { // an agent that is already open: no model, it keeps its own
      const agentId = String(offer.agent || "");
      const text = wordsBox(offer.task, "Your words for this agent");
      entry.box = text;
      box.append(el("p", "", `Send to ${agentLabel({ id: agentId, number: offer.number, name: offer.name })}:`), text);
      if (SEND_STATE[offer.state]) box.append(el("p", "talk-state muted", SEND_STATE[offer.state]));
      if (offer.tab_hint) { // a view only: Give to this agent stays the user's own click
        box.append(el("p", "talk-hint muted", SEND_HINT),
                   row(button("Your tabs…", "ghost talk-tabs", () => openAgent(agentId, { tabs: true }))));
      }
    } else {
      const who = `${offer.sender || "them"}${offer.subject ? ` (${offer.subject})` : ""}`;
      box.append(el("p", "", `Draft a reply to ${who} that says what you asked:`),
                 el("blockquote", "talk-guidance", String(offer.guidance || "")));
    }
    const go = button(GO[offer.kind] || "Draft it", "primary talk-go", () => confirm(entry));
    const no = button("Cancel", "ghost talk-cancel", () => {
      link.send({ type: "brain_dismiss", talk: talkId, proposal: entry.id });
      closeProposal();
    });
    entry.buttons = [go, no];
    box.append(row(go, no, el("span", "muted", "or say yes")));
    const seconds = Number(offer.expires_in);
    entry.timer = setTimeout(() => expire(entry), (Number.isFinite(seconds) ? Math.max(0, seconds) : 120) * 1000);
    proposal = entry;
    setCard(box);
  }

  function closeProposal() {
    if (!proposal) return;
    clearTimeout(proposal.timer);
    if (proposal.node.isConnected) closeCard();
    proposal = null;
  }

  function expire(entry) { // past its two minutes: the app won't run it any more either
    if (proposal !== entry) return;
    proposal = null;
    entry.node.replaceChildren(el("p", "muted", "This has expired: ask again"));
  }

  function confirm(entry) { // Start (or Draft it): one click, one run
    if (proposal !== entry || confirming) return;
    confirming = newId("t");
    for (const node of entry.buttons) node.disabled = true;
    const message = { type: "brain_confirm", talk: talkId, request: confirming, proposal: entry.id };
    if (entry.box) message.task = entry.box.value;
    if (entry.picker) message.model = entry.picker.value;
    if (!link.send(message)) {
      confirming = null;
      for (const node of entry.buttons) node.disabled = false;
      tell(NOT_CONNECTED);
    }
  }

  function created(message) { // the agent the card (or a spoken yes) started: the card has done its job
    if (message.request !== null && message.request !== undefined
        && (message.request === confirming || message.request === asking)) closeProposal();
  }

  function drop(current) { // a press that didn't become a turn: the voice may speak again
    if (turn === current) turn = null;
    voice.resume();
  }

  function press(mode) {
    if (turn || finishing || state === "opening") return;
    turn = { id: newId("u"), mode, downAt: performance.now(), upAt: null, mic: null, seq: 0, sent: 0, live: false,
             done: false, stopOnUp: false };
    voice.pause(); // speech stops at once: the mic never hears the Brain
    tell("");
    start(turn);
  }

  async function start(current) {
    if (!hearing || hearing.state !== "ready") {
      drop(current);
      if (!hearing) {
        tell(link.send({ type: "hearing" }) ? "One moment: checking whether talking is set up" : NOT_CONNECTED);
        return;
      }
      setState("setup");
      setCard(setupCard(hearing));
      return;
    }
    let permission = "granted";
    try {
      permission = (await navigator.permissions.query({ name: "microphone" })).state;
    } catch { /* the browser can't say: getUserMedia asks */ }
    if (turn !== current) return; // thrown away meanwhile (Esc, another window)
    if (permission === "prompt") { // the first time: say what the browser will ask, before it asks
      drop(current);
      setState("explain");
      setCard(explainCard());
      return;
    }
    if (permission === "denied") {
      drop(current);
      setState("idle");
      setCard(problemCard(micProblem({ name: "NotAllowedError", message: "Permission denied" })));
      return;
    }
    setState("opening");
    if (!link.send({ type: "listen_start", turn: current.id })) {
      drop(current);
      setState("idle");
      tell(NOT_CONNECTED);
      return;
    }
    let mic;
    try {
      mic = await openMic({ onChunk: (chunk) => chunked(current, chunk), onError: (error) => broke(current, error) });
    } catch (error) {
      if (turn === current) {
        link.send({ type: "listen_cancel", turn: current.id });
        drop(current);
        setState("idle");
        setCard(problemCard(micProblem(error)));
      }
      return;
    }
    if (turn !== current) { // thrown away (Esc, a lost line) while the mic was opening
      mic.cancel();
      return;
    }
    current.mic = mic;
    current.live = true;
    setState("listening");
    progress(listening(0));
    if (current.upAt !== null) release(); // let go while the mic was opening
  }

  function chunked(current, buffer) { // 250 ms of sound: sent at once, and dropped here
    if (current.done) return;
    const cap = (Number(hearing?.max_seconds) || 30) * BYTES_PER_SECOND;
    const room = Math.max(0, cap - current.sent);
    const piece = buffer.byteLength > room ? buffer.slice(0, room) : buffer;
    if (piece.byteLength) {
      if (!link.send({ type: "listen_chunk", turn: current.id, seq: current.seq, pcm: base64(piece) })) {
        lost(current);
        return;
      }
      current.seq += 1;
      current.sent += piece.byteLength;
      if (turn === current) progress(listening(Math.floor(current.sent / BYTES_PER_SECOND)));
    }
    if (current.sent >= cap && turn === current) {
      current.upAt = performance.now();
      release(`That's ${Number(hearing?.max_seconds) || 30} seconds: I stopped listening`);
    }
  }

  function broke(current, error) { // the microphone stopped by itself mid-turn
    if (turn !== current) return;
    cancel("");
    setCard(problemCard(micProblem(error)));
  }

  function lost(current) { // the line to the app is down: this turn can't be heard
    current.done = true;
    current.mic?.cancel();
    if (turn === current) {
      turn = null;
      voice.resume();
    }
    if (finishing === current) finishing = null;
    setState("idle");
    progress("");
    tell(NOT_CONNECTED);
  }

  async function release(note = "") { // let go: the mic closes, and the words are turned into text
    const current = turn;
    if (!current) return;
    current.upAt ??= performance.now();
    if (!current.live) return; // the mic is still opening: the turn ends as soon as it is open
    if (current.mode === "space" && current.upAt - current.downAt < HOLD_MS) {
      cancel("Hold Space while you talk");
      return;
    }
    turn = null;
    finishing = current;
    setState("transcribing");
    progress(`Turning your words into text…${hearing?.loaded ? "" : " (the first time takes a few seconds longer)"}`);
    tell(note, false); // the words may still go to the page's box (fill): it opens nothing
    await current.mic.stop(); // the tracks stop now; the last samples follow
    current.done = true;
    voice.resume();
    if (finishing !== current) return; // the line went down meanwhile
    if (!link.send({ type: "listen_end", turn: current.id })) lost(current);
  }

  function cancel(text) { // Esc, a slip of the key, or a problem: the turn is thrown away and nothing is sent
    const current = turn;
    if (!current) return;
    turn = null;
    current.done = true;
    current.mic?.cancel();
    link.send({ type: "listen_cancel", turn: current.id });
    voice.resume();
    setState(asking ? "asking" : "idle");
    progress(asking ? "Thinking about what you said" : "");
    tell(text);
  }

  function heard(message) {
    if (turn && message.turn === turn.id && message.error) { // the app dropped the turn while it was recording
      const current = turn;
      turn = null;
      current.done = true;
      current.mic?.cancel();
      voice.resume();
      setState("idle");
      progress("");
      tell(String(message.error));
      return;
    }
    if (!finishing || message.turn !== finishing.id) return;
    finishing = null;
    if (message.error) {
      setState("idle");
      progress("");
      tell(String(message.error));
      return;
    }
    const words = String(message.text || "");
    if (fill(words)) { // the page took them into its box: the user starts it
      setState(asking ? "asking" : "idle");
      progress(asking ? "Thinking about what you said" : "");
      return;
    }
    ask(words);
  }

  function ask(text) { // the user's words, spoken or typed, go to the Brain
    const words = text.trim().slice(0, 2000);
    if (!words) return;
    lastYou = line("You", words);
    asking = newId("t");
    const message = { type: "brain_ask", talk: talkId, request: asking, text: words };
    const about = aboutPage(); // the floating chat: this question reads that tab, then (the user's own mark)
    if (typeof about?.target === "string" && about.target) {
      message.page = about.target;
      message.site = String(about.site || ""); // the engine uses the page only while it is on this site
    }
    if (proposal?.node.isConnected) { // a plain yes runs this card as it now reads, only while it is on screen
      message.proposal = proposal.id;
      if (proposal.box) message.task = proposal.box.value;
      if (proposal.picker) message.model = proposal.picker.value;
    }
    if (!link.send(message)) {
      asking = null;
      setState("idle");
      progress("");
      tell(NOT_CONNECTED);
      return;
    }
    if (!turn) {
      setState("asking");
      progress("Thinking about what you said");
    }
  }

  function answered(message) {
    if (message.talk !== talkId) return;
    const confirmed = confirming !== null && message.request === confirming;
    if (!confirmed && message.request !== asking) return; // an older question's answer is never shown
    if (confirmed) {
      confirming = null;
      closeProposal();
    } else {
      asking = null;
      if (message.hidden && lastYou) lastYou.textContent = "You: (hidden: it sounded like a password)";
      if (!turn) {
        setState("idle");
        progress("");
      }
      if (message.proposal) showProposal(message.proposal);
      else closeProposal(); // any other answer closes the open card: the words were a new question
    }
    if (message.error) tell(String(message.error));
    if (message.say) {
      const say = String(message.say);
      line("Brain", say);
      voice.say(say, { priority: true }); // ahead of any waiting update; spoken when Voice is on
      if (hintVoice && !voice.enabled && !hinted) {
        hinted = true;
        tell("Switch on Voice to hear answers");
      }
    }
    if (message.open?.brain === true) openBrain();
    else if (typeof message.open?.agent === "string") {
      openAgent(message.open.agent, { tabs: message.open.tabs === true }); // tabs: the drawer at Your tabs, a view
    }
  }

  function statusChanged(message) {
    hearing = message;
    panel.dataset.hearing = String(message.state || "");
    if (state !== "setup") return;
    if (message.state === "ready") {
      closeCard();
      setState("idle");
      tell("Ready: hold Space to talk");
    } else {
      setCard(setupCard(message));
    }
  }

  function connection(linkState) { // the line to the app went down: nothing in flight will be answered
    if (linkState !== "disconnected") return;
    if (turn) lost(turn);
    if (finishing) lost(finishing);
    if (asking) {
      asking = null;
      setState("idle");
      progress("");
      tell(NOT_CONNECTED);
    }
    if (confirming) { // a Start whose answer can't come now: the card may be tried again (the app runs it once)
      confirming = null;
      if (proposal) for (const node of proposal.buttons) node.disabled = false;
      tell(NOT_CONNECTED);
    }
  }

  function setTalk(id, exchanges = []) { // Mission Control's New chat and History: another kept chat, its whole log
    talkId = String(id);
    asking = null; // an answer for the chat before is never shown here
    confirming = null;
    closeProposal();
    closeCard();
    log.replaceChildren();
    status.textContent = "";
    notice.textContent = "";
    if (!turn && !finishing) setState("idle");
    for (const one of exchanges) { // its cards as text: how each ended, never a live button
      if (one?.said) line("You", String(one.said));
      if (one?.answer) line("Brain", String(one.answer));
      if (one?.card) {
        log.append(el("li", "past", `${PAST[one.card.kind] || "A card"}: ${one.card.outcome || "Not answered"}`));
      }
    }
    log.scrollTop = log.scrollHeight;
  }

  function onMessage(message) {
    if (message.type === "hearing_status") statusChanged(message);
    else if (message.type === "heard") heard(message);
    else if (message.type === "brain_answer") answered(message);
    else if (message.type === "created") created(message);
  }

  // ---- Space, Esc, the mic button and the box ------------------------------------------------------------------

  function talkable() { // Space talks only when no control has focus (the mic button and the history count as none)
    const active = document.activeElement;
    return !active || active === document.body || active === document.documentElement || active === micButton
      || active === log;
  }

  function isSpace(event) {
    return event.code === "Space" || event.key === " ";
  }

  function letGo() { // another window took the keys: the keyup will never come, so this is the end of the turn
    if (turn?.mode !== "space") return;
    turn.upAt ??= performance.now();
    release();
  }

  addEventListener("keydown", (event) => {
    if (event.key === "Escape" && turn) { // Esc throws the turn away, and does nothing else
      event.preventDefault();
      event.stopImmediatePropagation();
      cancel("");
      return;
    }
    if (!isSpace(event) || event.metaKey || event.ctrlKey || event.altKey || event.isComposing || !talkable()) return;
    event.preventDefault(); // no scrolling, and the mic button isn't pressed by it
    event.stopImmediatePropagation();
    if (document.activeElement === log) log.blur(); // the history is only read: a key on it would pin it solid
    if (!event.repeat && !turn) press("space");
  }, { capture: true });

  addEventListener("keyup", (event) => {
    if (!isSpace(event)) return;
    if (document.activeElement === micButton) event.preventDefault(); // Space on the mic button talks, never clicks
    if (turn?.mode !== "space") return;
    event.preventDefault();
    event.stopImmediatePropagation();
    turn.upAt = performance.now();
    release();
  }, { capture: true });

  addEventListener("blur", letGo);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) letGo();
  });

  document.addEventListener("pointerdown", (event) => { // a click on the room gives the keys back to the page
    if (!(event.target instanceof Element) || event.target.closest(CONTROLS)) return;
    if (event.target.closest("dialog")) return; // a question is open (confirm.js): its focus stays on it
    if (document.activeElement instanceof HTMLElement && document.activeElement !== document.body) {
      document.activeElement.blur();
    }
  }, { capture: true });

  micButton.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    if (turn?.mode === "toggle") { // the second click of a click-to-talk turn ends it
      turn.stopOnUp = true;
      return;
    }
    if (turn) return;
    press("hold");
    micButton.setPointerCapture?.(event.pointerId);
  });

  micButton.addEventListener("pointerup", () => {
    if (!turn) return;
    if (turn.stopOnUp) {
      turn.upAt = performance.now();
      release();
      return;
    }
    if (turn.mode !== "hold") return;
    if (performance.now() - turn.downAt >= HOLD_MS) {
      turn.upAt = performance.now();
      release();
    } else {
      turn.mode = "toggle"; // a click: it listens until the next click
    }
  });

  micButton.addEventListener("click", (event) => {
    event.preventDefault();
    if (event.detail !== 0) return; // a pointer's click was handled above
    if (turn) { // Enter on the button: like a click, it toggles
      turn.upAt = performance.now();
      release();
    } else {
      press("toggle");
    }
  });

  form.addEventListener("submit", (event) => { // the same talk, typed
    event.preventDefault();
    const text = input.value;
    input.value = "";
    ask(text);
  });

  panel.dataset.state = state;
  return {
    onMessage, connection, setTalk,
    get state() { return state; },
    get fresh() { return !asking && !confirming && !log.children.length; }, // nothing said yet, nothing waiting
  };
}
