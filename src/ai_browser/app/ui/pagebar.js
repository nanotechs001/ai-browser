// "This page" in AI Browser's floating chat: the Brave tab the user is on. While the chat shows, AI Browser's own app
// reads the address and title of Brave's front tab (window.aib.thisPage: AppleScript on a Mac, UI Automation on
// Windows; never the page itself), and the engine matches them to the tab list (this_page). With no single match, or
// no answer, the user picks the tab. Nothing here asks Brave anything: Brave not running, not connected or not allowed
// is said in plain words. "Ask about it" marks the questions that read this tab, and Hand over gives it to an agent:
// both only on the user's click. Every title and address is set as text, on one line, without direction marks.
"use strict";

import { agentLabel, el } from "./chat.js";
import { chipText } from "./tablist.js";

export const LOOK_EVERY = 4000; // ms between two looks while the chat shows
const SLOW_NOTE = 800; // ms before a look that hasn't answered says what it waits for
const SHOWN = 80; // characters of a title the bar shows
const MARKS = /[‎‏‪-‮⁦-⁩]/g; // direction marks: a title can't turn round what it shows
const CONTROL = /[\u0000-\u001f\u007f]/g;
const WEB = /^https?:\/\//i;
const OWN = new Set(["you", "brain"]); // the user's own tabs (one the Brain opened is still theirs)
const PICK = new Set(["denied", "slow", "failed", "unsupported", "outside", "choose", "gone", "private",
                      "unknown"]); // the picker helps
const NOT_CONNECTED = "Not connected: is `ai-browser app` running?";

export const SAYS = {
  closed: "Brave isn't running.",
  nowindow: "Brave has no window open.",
  denied: "macOS doesn't let AI Browser see which Brave tab you're on.",
  slow: "Brave didn't answer in time: pick the tab, or look again.",
  failed: "AI Browser couldn't tell which Brave tab you're on: pick it.",
  unsupported: "AI Browser can't see Brave's tabs on this computer: pick the tab.",
  outside: "Pick the tab: only AI Browser's own app can see which one you're on.",
  choose: "Pick the tab you mean: AI Browser couldn't tell which one it is.",
  gone: "That tab has closed.",
  private: "That's a private window: AI Browser doesn't read those. Pick the tab you mean.",
  unknown: "AI Browser can't see this window's address: pick the tab you mean.",
  not_connected: "Brave isn't connected to AI Browser: connect it at the top of Mission Control.",
  asking: "Brave is asking whether AI Browser may connect: answer it in Brave.",
};
export const DENIED_STEPS = "To allow it: System Settings → Privacy & Security → Automation → AI Browser → turn on "
  + "Brave Browser. Then click ↻.";
export const WAITING = { // a look that takes a moment: the first one on a Mac waits for macOS's question
  mac: "Looking for your tab… The first time, macOS asks whether AI Browser may control Brave Browser: AI Browser "
    + "reads only the tab's address and title.",
  other: "Looking for your tab…",
};

export function plain(text, limit = SHOWN) { // one line, no direction marks or control characters, clipped
  const value = String(text ?? "").replace(MARKS, "").replace(CONTROL, " ").replace(/\s+/g, " ").trim();
  return value.length > limit ? `${value.slice(0, limit - 1)}…` : value;
}

export function host(url) {
  try {
    return new URL(String(url)).host;
  } catch {
    return "";
  }
}

export function pickable(tabs) { // the user's own web tabs: what the picker lists, and what may be handed over
  return (Array.isArray(tabs) ? tabs : [])
    .filter((tab) => OWN.has(tab?.owner?.kind) && WEB.test(String(tab?.url || "")));
}

function option(label, value) {
  const node = el("option", "", label);
  node.value = value;
  return node;
}

// root: the bar (#page). link: the line to the app. aib: AI Browser's bridge (undefined outside its own app).
// agents(): the open agents' rows. input: the talk's box (its placeholder says when questions read the tab).
// onSay(text): a short note for the user. onChange(tab): this page changed (null: none).
export function mountPageBar(root, { link, aib, agents, input, onSay = () => {}, onChange = () => {},
                                     every = LOOK_EVERY }) {
  const part = (name) => root.querySelector(`#page-${name}`);
  let tabs = []; // the tab list, as the app sends it
  let tab = null; // this page: a row of the tab list, or null
  let state = ""; // why there is none
  let platform = "other"; // "mac" or "windows", from the app's settings
  let picked = false; // the user picked it: it stays until they look again, or the chat shows again
  let picking = false; // the picker is open on the user's click
  let asking = false; // "Ask about it" is on: each question reads this tab
  let looks = 0; // the latest look's number: an older look's answer is dropped
  let request = null; // the this_page request waiting for the app's answer
  let timer = null;
  let slow = null;

  function setAsk(on) {
    asking = Boolean(on) && tab !== null;
    part("ask").setAttribute("aria-pressed", String(asking));
    input.placeholder = asking ? `Ask about ${host(tab.url) || "this page"}` : "Ask the Brain";
  }

  function fillHand() { // the open agents this tab may be handed to, by number
    const select = part("hand");
    const rows = agents();
    const signature = JSON.stringify(rows.map((agent) => [agent.id, agentLabel(agent)]));
    if (select.dataset.rows !== signature) {
      select.replaceChildren(option("Hand over…", ""), ...rows.map((agent) => option(agentLabel(agent), agent.id)));
      select.dataset.rows = signature;
    }
    select.value = "";
    select.disabled = !(tab && OWN.has(tab.owner?.kind)) || rows.length === 0;
  }

  function fillPicker() { // the user's own web tabs, by title and site
    const select = part("picker");
    const rows = pickable(tabs);
    const signature = JSON.stringify(rows.map((row) => [row.target, row.title, row.url]));
    if (select.dataset.rows !== signature) {
      select.replaceChildren(option(rows.length ? "Pick the tab you mean…" : "None of your tabs is listed", ""),
        ...rows.map((row) => option(`${plain(row.title, 60) || host(row.url)} · ${host(row.url)}`, row.target)));
      select.dataset.rows = signature;
    }
    select.value = "";
  }

  function render() {
    part("title").textContent = tab ? plain(tab.title) || host(tab.url) : "";
    const whose = tab && !OWN.has(tab.owner?.kind) ? ` · ${chipText(tab.owner)}` : "";
    part("host").textContent = tab ? `${host(tab.url)}${whose}` : "";
    part("says").textContent = tab ? "" : SAYS[state] || "";
    part("steps").textContent = !tab && state === "denied" ? DENIED_STEPS : "";
    part("steps").hidden = Boolean(tab) || state !== "denied";
    part("mission").hidden = Boolean(tab) || !(state === "not_connected" || state === "asking");
    part("ask").disabled = !tab;
    if (!tab) setAsk(false);
    fillHand();
    const open = picking || (!tab && PICK.has(state));
    if (open) fillPicker();
    part("picker").hidden = !open;
    onChange(tab);
  }

  function show(next) { // this page is now `next`, a row of the tab list
    // Ask about it belongs to one tab, on the site the user marked ("Ask about <site>"): another site turns it off
    if (tab?.target !== next.target || host(tab?.url) !== host(next.url)) setAsk(false);
    tab = next;
    state = "";
    render();
  }

  function settle(why) { // no tab to show: why, in plain words
    tab = null;
    state = why;
    render();
  }

  async function look() { // which tab the user is on, asked of AI Browser's own app: only while the chat shows
    if (document.hidden || picked) return;
    if (typeof aib?.thisPage !== "function") {
      settle("outside");
      return;
    }
    const mine = ++looks;
    clearTimeout(slow);
    slow = setTimeout(() => {
      if (mine === looks && !tab) part("says").textContent = platform === "mac" ? WAITING.mac : WAITING.other;
    }, SLOW_NOTE);
    let seen;
    try {
      seen = await aib.thisPage();
    } catch {
      seen = { state: "failed" };
    }
    clearTimeout(slow);
    if (mine !== looks || picked || document.hidden) return; // a newer look, a pick, or hidden meanwhile
    if (!seen || seen.state === "hidden") return; // the chat hid: nothing was read
    if (seen.state !== "ok") {
      settle(String(seen.state || "failed"));
      return;
    }
    request = `p${mine}`;
    if (!link.send({ type: "this_page", url: String(seen.url || ""), title: String(seen.title || ""), request })) {
      settle("failed");
    }
  }

  function again() { // ↻, the chat shown again, or Brave's state changed: the app looks now, and a pick ends
    picked = false;
    picking = false;
    look();
  }

  function onMessage(message) {
    if (message.type === "snapshot" || message.type === "tabs") {
      tabs = Array.isArray(message.tabs) ? message.tabs : [];
      if (message.type === "snapshot") platform = message.settings?.desktop?.platform || platform;
      const now = tab ? tabs.find((row) => row.target === tab.target) : null;
      if (tab && !now) { // the tab it showed has closed
        settle("gone");
        again();
      } else if (now) {
        show(now);
      } else {
        render();
      }
      if (message.type === "snapshot") again();
    } else if (message.type === "this_page" && message.request === request) {
      request = null;
      if (picked) return;
      if (message.state === "found" && message.tab) show(message.tab);
      else if (message.state === "not_connected") settle(message.browser === "asking" ? "asking" : "not_connected");
      else settle("choose");
    } else if (message.type === "browser") {
      again();
    } else if (message.type === "agent" || message.type === "agent_closed") {
      fillHand();
    }
  }

  part("ask").addEventListener("click", () => setAsk(!asking));
  part("look").addEventListener("click", again);
  part("pick").addEventListener("click", () => {
    picking = !picking;
    render();
  });
  part("picker").addEventListener("change", () => {
    const row = pickable(tabs).find((one) => one.target === part("picker").value);
    if (!row) return;
    picked = true; // the user's pick holds until ↻, or until the chat shows again
    picking = false;
    looks += 1; // a look under way can't replace it
    show(row);
  });
  part("hand").addEventListener("change", () => { // Hand over: the user's pick of an agent, nothing else
    const id = part("hand").value;
    part("hand").value = "";
    if (!id || !tab) return;
    const agent = agents().find((one) => one.id === id) || { id };
    if (link.send({ type: "hand_tab", id, target: tab.target })) onSay(`Handing this page to ${agentLabel(agent)}`);
    else onSay(NOT_CONNECTED);
  });
  part("mission").addEventListener("click", () => link.send({ type: "show_app" }));
  document.addEventListener("visibilitychange", () => {
    clearInterval(timer);
    timer = null;
    if (document.hidden) {
      setAsk(false); // hidden: no question is about this page any more, and nothing is looked at
      return;
    }
    again();
    timer = setInterval(look, every);
  });
  addEventListener("focus", look);
  if (!document.hidden) timer = setInterval(look, every);
  render();
  // asking(): the tab a question reads, and the site the user marked on it ("Ask about <site>"), or null
  const marked = () => (asking && tab ? { target: tab.target, site: host(tab.url) } : null);
  return { onMessage, look: again, asking: marked, current: () => tab };
}
