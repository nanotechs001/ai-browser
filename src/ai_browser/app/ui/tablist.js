// AI Home's tab list: every web tab of the user's Brave (or of AI Browser), its title and site, and whose it is: an
// agent's (its name and colour), Claude Code's, the Brain's, handed to an agent, or yours. Hand over gives one of
// your tabs to an agent; Take back ends that. Titles, addresses and names are set as text, never as HTML.
import { agentLabel, el } from "./chat.js";

export const COLORS = { grey: "#5f6368", blue: "#1a73e8", red: "#d93025", yellow: "#f9ab00", green: "#188038",
                        pink: "#d01884", purple: "#a142f4", cyan: "#007b83", orange: "#fa903e" };

function host(url) {
  try {
    return new URL(url).host || url;
  } catch {
    return url;
  }
}

function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

export function chipText(owner) {
  if (!owner || owner.kind === "you") return "you";
  if (owner.kind === "session") return "Claude Code";
  if (owner.kind === "brain") return "Brain";
  if (owner.kind === "handed") return `handed to ${agentLabel(owner)}`;
  return agentLabel(owner);
}

// The tab list's scope in brave mode (the server's tab_scope): which profile the rows come from, and how many of the
// user's tabs it leaves out. Only a number reaches this page: never a title, an address or an id of those tabs.
const SCOPE_SOURCE = {
  last_used: "Showing the Brave profile you used last. Pick the one agents use in Settings → Where agents browse.",
  not_open: "The profile agents use isn't open in Brave yet: open a window of it, and click in it once.",
  none: "Your tabs aren't listed: AI Browser can't tell which Brave profile is yours yet.",
};

export function scopeTexts(scope) {
  if (!scope) return { source: "", elsewhere: "" };
  const count = Number(scope.elsewhere) || 0;
  return {
    source: SCOPE_SOURCE[scope.profile] || "",
    elsewhere: count > 0
      ? `${count} more ${count === 1 ? "tab" : "tabs"} in other profiles or private windows: not shown here.` : "",
  };
}

// send(message): to the app; agents(): the agents a tab can be given to; newAgent(tab): Hand over → New agent…
export function mountTabList(root, { send, agents, newAgent }) {
  const rows = new Map(); // target -> its row, built once and updated in place (a click must not be lost)

  function button(className, label, onClick) {
    const node = el("button", className, label);
    node.type = "button";
    node.addEventListener("click", (event) => {
      event.stopPropagation(); // a button in a row is not a click on the row (Watch)
      onClick();
    });
    return node;
  }

  function toggleMenu(row) {
    const { menu } = row.parts;
    if (!menu.hidden) {
      menu.hidden = true;
      return;
    }
    menu.textContent = "";
    menu.append(button("new", "New agent…", () => {
      menu.hidden = true;
      newAgent(row.tab);
    }));
    for (const agent of agents()) {
      const give = button("give", `Give to ${agentLabel(agent)}`, () => {
        menu.hidden = true;
        send({ type: "hand_tab", id: agent.id, target: row.tab.target });
      });
      give.dataset.id = agent.id;
      menu.append(give);
    }
    menu.append(el("p", "note muted", "The agent will read this tab and act in it."));
    menu.hidden = false;
  }

  function makeRow(target) {
    const row = el("div", "tab");
    row.dataset.target = target;
    const parts = { title: el("span", "title"), host: el("span", "host"), chip: el("span", "chip owner"),
                    actions: el("span", "actions"), menu: el("div", "menu") };
    parts.menu.hidden = true;
    parts.menu.addEventListener("click", (event) => event.stopPropagation());
    parts.hand = button("hand ghost", "Hand over", () => toggleMenu(row));
    parts.take = button("take ghost", "Take back", () => send({ type: "take_back", target }));
    parts.actions.append(parts.hand, parts.take);
    row.append(parts.title, parts.host, parts.chip, parts.actions, parts.menu);
    row.addEventListener("click", () => send({ type: "watch", target }));
    row.parts = parts;
    return row;
  }

  function line(className, text) { // a muted line after the rows, updated in place, gone when not needed
    let node = root.querySelector(`:scope > p.${className}`);
    if (!text) {
      node?.remove();
      return;
    }
    if (!node) node = el("p", `${className} muted`);
    setText(node, text);
    root.append(node); // after the rows and the empty text, in the order of the calls
  }

  function render(tabs, { brave, ownerOf, scope = null }) {
    const open = new Set(tabs.map((tab) => tab.target));
    for (const [target, row] of rows) {
      if (!open.has(target)) {
        row.remove();
        rows.delete(target);
      }
    }
    root.querySelector(".empty")?.remove();
    let previous = null;
    for (const tab of tabs) {
      let row = rows.get(tab.target);
      if (!row) {
        row = makeRow(tab.target);
        rows.set(tab.target, row);
        if (previous) previous.after(row);
        else root.prepend(row);
      }
      row.tab = tab;
      const owner = tab.owner || ownerOf(tab.target);
      const kind = owner?.kind || "you";
      const { parts } = row;
      setText(parts.title, tab.title || tab.url);
      setText(parts.host, host(tab.url));
      setText(parts.chip, chipText(owner));
      parts.chip.dataset.kind = kind;
      parts.chip.style.boxShadow = owner?.color ? `inset 3px 0 0 ${COLORS[owner.color] || "transparent"}` : "";
      parts.hand.hidden = !brave || !["you", "brain"].includes(kind); // the user's own tabs (a Brain row is theirs)
      parts.take.hidden = !brave || kind !== "handed";
      if (parts.hand.hidden) parts.menu.hidden = true;
      row.title = tab.url;
      previous = row;
    }
    if (!tabs.length) {
      root.append(el("p", "empty", scope ? "No web pages open in this profile." : "No web pages open in your browser."));
    }
    const texts = scopeTexts(brave ? scope : null);
    line("scope-source", texts.source);
    line("elsewhere", texts.elsewhere);
  }

  return { render };
}

// Mission Control's Your tabs, in an agent's drawer: the user's own tabs (theirs, or a Brain thread's), each with Give
// to this agent. That button is the existing hand_tab, the same click as AI Home's Hand over; the Brain never sends
// it. root is a <details>; every text is set with textContent.
export function mountYourTabs(root, { send, agentId }) {
  const summary = el("summary", "", "Your tabs");
  const list = el("div", "your-tab-list");
  root.replaceChildren(summary, list);

  // scope: the server's tab_scope (brave mode lists one profile), said here as AI Home's list says it
  function render(tabs, { brave = false, connected = false, name = "Brave", scope = null } = {}) {
    root.hidden = !brave; // agents in AI Browser itself can't take the user's tabs
    list.textContent = "";
    if (!brave) return;
    if (!connected) {
      summary.textContent = "Your tabs";
      list.append(el("p", "muted", `${name} isn't connected yet: connect it in AI Home.`));
      return;
    }
    const mine = tabs.filter((tab) => ["you", "brain"].includes(tab.owner?.kind || "you"));
    summary.textContent = `Your tabs (${mine.length})`;
    const texts = scopeTexts(scope);
    if (!mine.length && scope?.profile !== "none") { // with no profile known, the source line says why instead
      list.append(el("p", "muted", scope ? "None of your tabs are open in this profile." : "None of your tabs are open."));
    }
    if (texts.source) list.append(el("p", "muted scope-source", texts.source));
    if (texts.elsewhere) list.append(el("p", "muted elsewhere", texts.elsewhere));
    for (const tab of mine) {
      const row = el("div", "your-tab");
      row.dataset.target = tab.target;
      const give = el("button", "give-here", "Give to this agent");
      give.type = "button";
      give.addEventListener("click", () => {
        if (give.disabled) return;
        give.disabled = true; // one click, one hand-over: the next render shows where the tab went
        send({ type: "hand_tab", id: agentId(), target: tab.target });
      });
      row.title = tab.url || "";
      row.append(el("span", "title", tab.title || tab.url || ""), el("span", "host", host(tab.url || "")), give);
      list.append(row);
    }
  }

  return { render };
}
