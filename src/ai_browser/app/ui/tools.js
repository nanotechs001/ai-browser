// AI Home → Tools: the user's MCP servers (Claude Code's own configuration, and the claude.ai connectors), each
// switched on or off for AI Browser's agents, their tools (any can be allowed always), and the tools allowed always.
// Agents ask before any other tool. Everything is shown as text.
import { el } from "./chat.js";

const SOURCES = { user: "your Claude Code", local: "a project", project: "a project", connector: "claude.ai" };

export function mountTools(root, link) {
  const servers = el("div", "list tool-servers");
  const always = el("div", "list always-list");
  root.replaceChildren(
    el("p", "muted", "Switch on the servers agents may use. They still ask you before each tool unless you allow it "
                     + "always. ai-browser's own tools are always on."),
    servers, el("h3", "", "Allowed always"), always);
  let probed = false;

  function send(message) {
    if (!link.send(message)) root.querySelector(".muted").textContent = "Not connected: is ai-browser app running?";
  }

  function render({ servers: listed = [], always: allowed = [] }) {
    servers.replaceChildren();
    for (const server of listed) {
      const row = el("div", "tool-server card");
      row.dataset.name = server.name;
      const top = el("label", "top-line");
      const on = el("input", "on");
      on.type = "checkbox";
      on.checked = Boolean(server.enabled);
      on.addEventListener("change", () => send({ type: "tool_set", server: server.name, on: on.checked }));
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
          allow.addEventListener("click", () => send({ type: "tool_allow", tool }));
          line.append(el("span", "", tool.split("__").slice(2).join("__") || tool), allow);
          details.append(line);
        }
        row.append(details);
      }
      servers.append(row);
    }
    if (!listed.length) servers.append(el("p", "empty", "No MCP servers found in Claude Code's configuration."));
    always.replaceChildren();
    for (const tool of allowed) {
      const line = el("div", "always-tool");
      line.dataset.tool = tool;
      const forget = el("button", "forget ghost", "Forget");
      forget.addEventListener("click", () => send({ type: "tool_forget", tool }));
      line.append(el("span", "", tool), forget);
      always.append(line);
    }
    if (!allowed.length) always.append(el("p", "empty", "None yet: agents ask before every tool."));
  }

  return {
    refresh() { // the first time, Claude Code is asked which claude.ai connectors it has
      send({ type: "tools", refresh: !probed });
      probed = true;
    },
    onMessage(message) {
      if (message.type === "tools_snapshot") render(message);
    },
  };
}
