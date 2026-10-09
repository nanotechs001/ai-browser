// Settings → Brave (the saved-agents spec, 6): whether Brave is connected, what uses it through AI Browser's one
// connection (the relay's rows: AI Browser itself, each agent and Claude Code session) with Disconnect, and, while an
// earlier AI Browser's copy of Brave's old extension may still be loaded, how to remove it (until Got it). Connect
// and the setup steps are at the top of Mission Control. Every name is set as text.
"use strict";

import { agentLabel, el } from "./chat.js";
import { COLORS } from "./tablist.js";

export function mountBraveSettings(parts, send) {
  // parts: {state, using, title, list, note, watcher, watcherClose}
  let browser = null; // {kind, name, state}
  let clients = []; // the relay's rows, with names and colours: never a token
  let settings = null;

  function label(row) {
    if (row.kind === "app") return "AI Browser · the tab list and pictures";
    const tabs = `${row.tabs} tab${row.tabs === 1 ? "" : "s"}`;
    const who = row.kind === "agent" ? agentLabel(row) : "Claude Code";
    return `${who} · ${tabs}${row.cut_off ? ` · cut off from ${browser?.name || "Brave"}` : ""}`;
  }

  function render() {
    const name = browser?.name || "Brave";
    parts.state.textContent = browser?.state === "connected" ? `${name} is connected to AI Browser.`
      : `${name} isn't connected: connect it at the top of Mission Control.`;
    parts.using.hidden = !browser || browser.kind !== "brave" || clients.length === 0;
    parts.list.replaceChildren(...(parts.using.hidden ? [] : clients.map((row) => {
      const item = el("li", "client");
      item.style.setProperty("--client-color", COLORS[row.color] || "transparent");
      item.append(el("span", "", label(row)));
      if (row.kind !== "app" && !row.cut_off) {
        const button = el("button", "ghost", "Disconnect");
        button.type = "button";
        button.addEventListener("click", () => send({ type: "browser_disconnect", id: row.id }));
        item.append(button);
      }
      return item;
    })));
    parts.title.textContent = `Using your ${name} through AI Browser`;
    parts.note.textContent = `Anything listed here can use your ${name} without a new question until AI Browser `
      + "quits. Disconnect cuts one off; unticking the switch cuts off everything.";
    // Brave's old extension: AI Browser never removes it, and says until Got it that the user can
    parts.watcher.hidden = !(settings?.old_watcher === true && settings?.watcher_note !== false);
  }

  parts.watcherClose.addEventListener("click", () => {
    parts.watcher.hidden = true;
    send({ type: "settings_set", key: "watcher_note", value: false });
  });

  return {
    onMessage(message) {
      if (message.type === "snapshot") {
        browser = message.browser || null;
        clients = message.browser_clients || [];
        settings = message.settings || null;
      } else if (message.type === "browser") {
        browser = { kind: message.kind, name: message.name, state: message.state };
      } else if (message.type === "browser_clients") {
        clients = message.clients || [];
      } else if (message.type === "settings") {
        settings = message;
      } else {
        return;
      }
      render();
    },
  };
}
