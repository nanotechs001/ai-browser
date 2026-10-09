// Brave's connection, at the top of Mission Control (the saved-agents spec, 6): while Brave isn't connected, or is
// asking "Allow remote debugging?", a bar says how it stands and offers the one next step: Show me how (the setup
// steps, in a closable tab), Connect or Try again. Connected, it hides. What uses Brave through AI Browser, with
// Disconnect, is Settings → Brave's. Every word is set as text.
"use strict";

import { el } from "./chat.js";

const SAYS = { off: "switch off", ready: "ready", asking: "waiting for Allow", refused: "not allowed",
               lost: "closed" };
const ACTIONS = { off: "Show me how", ready: "Connect", lost: "Connect", refused: "Try again" };

function steps(name) { // the switch, once: the same three steps as the setup page's
  return [`In ${name}, open ${name === "Brave" ? "brave" : "chrome"}://inspect/#remote-debugging.`,
          "Tick \"Allow remote debugging for this browser instance\".",
          `When ${name} asks "Allow remote debugging?", click Allow.`];
}

function notes(name) {
  return {
    ready: `${name} will ask "Allow remote debugging?" once for AI Browser: click Allow`,
    asking: `${name} is asking "Allow remote debugging?": click Allow there (or Deny). Everything waiting for ${name} `
            + "shares this one question.",
    refused: `${name} said no.`,
    lost: `${name} quit or restarted.`,
  };
}

// send(message): to the app; openTab(path): one of our pages, as a tab of AI Browser's window (nav.js)
export function mountBraveBar(root, { send, openTab }) {
  const title = el("strong", "brave-title");
  const action = el("button", "primary brave-action");
  action.type = "button";
  const list = el("ol", "brave-steps");
  const note = el("p", "muted brave-note");
  const warning = el("p", "muted brave-warning");
  const head = el("div", "brave-head");
  head.append(title, action);
  root.replaceChildren(head, list, note, warning);
  let browser = null; // {kind, name, state}, as the app says

  function render() {
    root.hidden = !browser || browser.kind !== "brave" || browser.state === "connected";
    if (root.hidden) return;
    const name = browser.name || "Brave";
    root.dataset.state = browser.state;
    title.textContent = `Your ${name} · ${SAYS[browser.state] || browser.state}`;
    action.textContent = ACTIONS[browser.state] || "";
    action.hidden = !ACTIONS[browser.state];
    list.replaceChildren(...steps(name).map((step) => el("li", "", step)));
    list.hidden = browser.state !== "off";
    note.textContent = notes(name)[browser.state] || "";
    note.hidden = !note.textContent;
    warning.textContent = `While the switch is on, any program on this computer can reach your ${name}, not only `
      + "AI Browser. Turn it off when agents aren't working.";
  }

  action.addEventListener("click", () => {
    if (browser?.state === "off") openTab("/setup#switch"); // the setup page's steps, with their warning
    else send({ type: "brave_connect" });
  });

  return {
    onMessage(message) {
      if (message.type === "snapshot") browser = message.browser || null;
      else if (message.type === "browser") browser = { kind: message.kind, name: message.name, state: message.state };
      else return;
      render();
    },
  };
}
