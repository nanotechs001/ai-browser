// Each agent's profile indicator (the chat-panel spec, 7): whether the Brave profile it browses in is ready. A dot and
// a word: Ready (its context is learned: its tabs can open there), Open it once (open a Brave window of that profile:
// AI Browser learns it in about 30 seconds) or Brave not connected. The hint says what to do, on hover and on focus.
// An agent on "Settings' choice" follows the profile Settings picks; with none picked, the one Brave used last (Ready
// once Brave names it). It follows the saved_agents message, which the app sends again when Brave connects or goes,
// when a profile is learned or forgotten and when Settings' choice changes. Nothing opens Brave by itself. Every word
// is set as text.
"use strict";

import { el } from "./chat.js";

let known = { profiles: [], chosen: null, connected: false, defaultReady: false };

// saved_agents: {profiles: [{folder, name, ready}], chosen, connected, default_ready}
export function setProfiles(message) {
  known = { profiles: Array.isArray(message?.profiles) ? message.profiles : [],
            chosen: typeof message?.chosen === "string" && message.chosen ? message.chosen : null,
            connected: message?.connected === true, defaultReady: message?.default_ready === true };
}

// folder: the agent's own profile, or null (Settings' choice)
export function profileState(folder) {
  if (!known.connected) {
    return { state: "off", word: "Brave not connected",
             hint: "Connect Brave at the top of Mission Control: then it shows whether this profile is ready" };
  }
  const chosen = typeof folder === "string" && folder ? folder : known.chosen;
  if (!chosen) {
    if (known.defaultReady) return { state: "ready", word: "Ready", hint: "It browses in the profile Brave used last" };
    return { state: "open", word: "Open it once",
             hint: "Open a Brave window once: it browses in the profile Brave used last" };
  }
  const row = known.profiles.find((one) => one?.folder === chosen);
  const name = String(row?.name || chosen);
  if (row?.ready === true) return { state: "ready", word: "Ready", hint: `It browses in Brave's ${name} profile` };
  return { state: "open", word: "Open it once",
           hint: `Open a Brave window of the ${name} profile once: AI Browser learns it in about 30 seconds` };
}

// The dot and the word, the hint shown on hover and focus. A desk's nameplate has no room: the dot alone (word:
// false), its word and hint as its tooltip.
export function profileDot(folder, { word = true } = {}) {
  const shown = profileState(folder);
  const node = el("span", "profile-dot");
  node.dataset.state = shown.state;
  node.append(el("span", "dot"));
  if (word) node.append(el("span", "word", shown.word), el("span", "hint", shown.hint));
  else node.title = `${shown.word}: ${shown.hint}`;
  return node;
}
