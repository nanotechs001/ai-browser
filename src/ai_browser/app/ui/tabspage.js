// Mission Control's Tabs page (the saved-agents spec, 6): the user's web tabs in the profile
// where agents browse, and the AI's tabs wherever they are, each with whose it is. Hand over (New agent… or Give to …)
// and Take back; a click on a row brings that tab to the front. Titles, addresses and names are set as text.
"use strict";

import { el } from "./chat.js";
import { pageHead } from "./pages.js";
import { mountTabList } from "./tablist.js";

// send(message): to the app; agents(): the agents a tab can be given to; newAgent(tab): Hand over → New agent…
export function mountTabsPage(root, { send, agents, newAgent }) {
  const list = el("div", "list tabs-list");
  list.id = "tabs";
  root.replaceChildren(pageHead("Tabs"), el("p", "page-note", "Your Brave tabs in the profile where agents browse, "
    + "and the AI's tabs, with whose each one is. Click one to bring it to the front."), list);
  const tabList = mountTabList(list, { send, agents, newAgent });
  let tabs = [];
  let scope = null; // {profile, elsewhere}: only numbers, never a title
  let browser = null; // {kind, name, state}

  function render() {
    const connected = browser?.kind === "brave" && browser.state === "connected";
    tabList.render(tabs, { brave: browser?.kind === "brave", scope: connected ? scope : null,
                           ownerOf: (target) => { // AI Browser mode: the app's list has no owners, so they come from the agents
                             const agent = agents().find((one) => one.working_tab === target
                               || (one.tabs || []).includes(target) || (one.adopted || []).includes(target));
                             return agent ? { kind: "agent", id: agent.id, name: agent.name, color: agent.color }
                                          : { kind: "you" };
                           } });
  }

  return {
    onMessage(message) {
      if (message.type === "snapshot") {
        tabs = message.tabs || [];
        scope = message.tab_scope || null;
        browser = message.browser || null;
      } else if (message.type === "tabs") {
        tabs = message.tabs || [];
        scope = message.tab_scope || null;
      } else if (message.type === "browser") {
        // A new state forgets the scope: while not connected the app sends none, and the one from before must not
        // show in the moment after Brave connects again. The new connection's first list brings its own.
        if (message.state !== browser?.state) scope = null;
        browser = { kind: message.kind, name: message.name, state: message.state };
      } else {
        return;
      }
      render();
    },
  };
}
