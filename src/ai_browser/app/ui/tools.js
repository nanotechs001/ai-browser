// Integrations: the user's MCP servers (Claude Code's own configuration, and the claude.ai connectors), each
// switched on or off for AI Browser's agents, their tools (any can be allowed always), and the tools allowed always.
// Agents ask before any other tool. With two or more accounts (AI accounts), a picker shows one account's tools at a
// time: each account has its own servers, switches and always-allowed tools. Everything is shown as text.
import { el } from "./chat.js";

const SOURCES = { user: "your Claude Code", local: "a project", project: "a project", connector: "claude.ai" };

export function mountTools(root, link) {
  const pick = el("select", "tools-account");
  pick.setAttribute("aria-label", "Whose tools");
  pick.hidden = true;
  const note = el("p", "muted", "Switch on the servers agents may use. They still ask you before each tool unless you "
                                + "allow it always. ai-browser's own tools are always on.");
  const servers = el("div", "list tool-servers");
  const always = el("div", "list always-list");
  root.replaceChildren(pick, note, servers, el("h3", "", "Allowed always"), always);
  let account = "default"; // whose tools are shown
  const probed = new Set(); // accounts Claude Code was asked about already (their claude.ai connectors)

  function send(message) {
    if (!link.send(message)) note.textContent = "Not connected: is ai-browser app running?";
  }

  function render({ servers: listed = [], always: allowed = [] }) {
    const shown = account; // the account these rows belong to, whatever is picked later
    servers.replaceChildren();
    for (const server of listed) {
      const row = el("div", "tool-server card");
      row.dataset.name = server.name;
      const top = el("label", "top-line");
      const on = el("input", "on");
      on.type = "checkbox";
      on.checked = Boolean(server.enabled);
      on.addEventListener("change", () => send({ type: "tool_set", account: shown, server: server.name,
                                                 on: on.checked }));
      top.append(on, el("strong", "", server.label || server.name), el("span", "chip", SOURCES[server.source] || ""));
      if (server.status && server.status !== "connected") top.append(el("span", "muted", server.status));
      row.append(top);
      const tools = (server.tools || []).filter((tool) => !allowed.includes(tool));
      if (tools.length) {
        const details = el("details", "tool-list");
        details.append(el("summary", "", `${tools.length} tools`));
        for (const tool of tools) {
          const line = el("div", "tool-line");
          const allow = el("button", "always", "Always allow");
          allow.addEventListener("click", () => send({ type: "tool_allow", account: shown, tool }));
          line.append(el("span", "", tool.split("__").slice(2).join("__") || tool), allow);
          details.append(line);
        }
        row.append(details);
      }
      servers.append(row);
    }
    if (!listed.length) servers.append(el("p", "empty", "No tools yet. Add one in Claude Code (claude mcp add), "
      + "then come back: it shows up here."));
    always.replaceChildren();
    for (const tool of allowed) {
      const line = el("div", "always-tool");
      line.dataset.tool = tool;
      const forget = el("button", "forget ghost", "Forget");
      forget.addEventListener("click", () => send({ type: "tool_forget", account: shown, tool }));
      line.append(el("span", "", tool), forget);
      always.append(line);
    }
    if (!allowed.length) always.append(el("p", "empty", "None yet: agents ask before every tool."));
  }

  function refresh() { // the first time for each account, Claude Code is asked which claude.ai connectors it has
    send({ type: "tools", account, refresh: !probed.has(account) });
    probed.add(account);
  }

  pick.addEventListener("change", () => {
    account = pick.value;
    refresh();
  });

  return {
    refresh,
    setAccounts(rows) { // Settings → Accounts' list: one account's tools at a time, with two or more
      const listed = Array.isArray(rows) ? rows : [];
      const signature = JSON.stringify(listed.map((row) => [row.id, row.name]));
      if (pick.dataset.rows !== signature) {
        pick.textContent = "";
        for (const row of listed) {
          const option = el("option", "", row.name);
          option.value = row.id;
          pick.append(option);
        }
        pick.dataset.rows = signature;
      }
      if (account !== "default" && !listed.some((row) => row.id === account)) { // removed meanwhile
        account = "default";
        refresh();
      }
      pick.value = account;
      pick.hidden = listed.length < 2;
    },
    onMessage(message) {
      if (message.type === "tools_snapshot" && (message.account || "default") === account) render(message);
    },
  };
}
