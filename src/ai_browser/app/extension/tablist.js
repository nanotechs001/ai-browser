// AI Home's tab list: every web tab of the user's Brave (or of AI Browser), its title and site, and whose it is: an
// agent's (its name and colour), Claude Code's, the Brain's, handed to an agent, or yours. Hand over gives one of
// your tabs to an agent; Take back ends that. Titles, addresses and names are set as text, never as HTML.
import { el } from "./chat.js";

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
  if (owner.kind === "handed") return `handed to ${owner.name || "an agent"}`;
  return owner.name || "an agent";
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
      const give = button("give", `Give to ${agent.name}`, () => {
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

  function render(tabs, { brave, ownerOf }) {
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
      root.append(el("p", "empty", brave ? "No web pages open in your browser." : "No tabs open besides AI Home."));
    }
  }

  return { render };
}
