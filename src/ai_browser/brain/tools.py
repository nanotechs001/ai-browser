"""The user's MCP servers, for AI Browser's agents: the same tools as in the Claude Code app.

Servers come from Claude Code's own configuration (user scope in ~/.claude.json, its projects' local servers, and each
of those projects' .mcp.json) and from the claude.ai connectors Claude Code loads for the user's account, which a
probe finds (they can't be passed through --mcp-config). Nothing reaches an agent unless the user switched its server
on, and every tool that isn't always allowed waits for the user's answer. Kept in <home>/tools.json (mode 0600)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
from pathlib import Path

from ..syncdir import write_atomic

CONNECTOR = "claude_ai_"  # how Claude Code names a claude.ai connector's tools: mcp__claude_ai_<Name>__<tool>
PROBE_PROMPT = "Reply with just ok."


def connector_name(label: str) -> str:
    """"claude.ai ClickUp" -> "claude_ai_ClickUp", the server's name in its tools' names."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", label)


def server_of(tool: str) -> str:
    parts = tool.split("__")
    return parts[1] if len(parts) >= 3 and parts[0] == "mcp" else ""


class ToolsConfig:
    def __init__(self, home: Path, claude_home: Path | None = None):
        self.path = Path(home) / "tools.json"
        self.claude_home = Path(claude_home) if claude_home is not None else Path.home()
        data = self._read()

        def listed(key: str) -> list:  # a damaged file is read as far as it makes sense
            return data[key] if isinstance(data.get(key), list) else []

        known = data["known"] if isinstance(data.get("known"), dict) else {}
        self._enabled = {str(name) for name in listed("enabled")}
        self._always = {str(tool) for tool in listed("always") if server_of(str(tool))}
        self._known = {str(server): sorted({str(tool) for tool in tools})
                       for server, tools in known.items() if isinstance(tools, list)}
        self._connectors = {str(item["name"]): str(item.get("status", "")) for item in listed("connectors")
                            if isinstance(item, dict) and isinstance(item.get("name"), str)}

    # ---- what the user has -------------------------------------------------------------------------------

    def _config_servers(self) -> dict[str, tuple[str, str, dict]]:
        """name -> (source, project, definition), from Claude Code's configuration; ai-browser's own is left out."""
        try:
            data = json.loads((self.claude_home / ".claude.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        found: dict[str, tuple[str, str, dict]] = {}

        def add(servers, source: str, project: str) -> None:
            for name, definition in (servers or {}).items() if isinstance(servers, dict) else []:
                if name != "ai-browser" and name not in found and isinstance(definition, dict):
                    found[name] = (source, project, definition)

        projects = data.get("projects") if isinstance(data.get("projects"), dict) else {}
        add(data.get("mcpServers"), "user", "")
        for project, settings in projects.items():
            add((settings or {}).get("mcpServers") if isinstance(settings, dict) else None, "local", project)
        for project in projects:
            with contextlib.suppress(OSError, ValueError, AttributeError):
                add(json.loads((Path(project) / ".mcp.json").read_text(encoding="utf-8")).get("mcpServers"),
                    "project", project)
        return found

    def servers(self) -> list[dict]:
        listed = [{"name": name, "label": name, "source": source, "project": project,
                   "type": str(definition.get("type", "stdio")), "enabled": name in self._enabled, "status": "",
                   "tools": self._known.get(name, [])}
                  for name, (source, project, definition) in self._config_servers().items()]
        listed += [{"name": name, "label": f"{name.removeprefix(CONNECTOR).replace('_', ' ')} (claude.ai)",
                    "source": "connector", "project": "", "type": "connector", "enabled": name in self._enabled,
                    "status": status, "tools": self._known.get(name, [])}
                   for name, status in self._connectors.items()]
        return listed

    def definition(self, name: str) -> dict | None:
        entry = self._config_servers().get(name)
        return dict(entry[2]) if entry else None

    def connectors(self) -> set[str]:
        return set(self._connectors)

    # ---- the user's choices ------------------------------------------------------------------------------

    def enabled(self) -> set[str]:
        return set(self._enabled)

    def set_enabled(self, name: str, on: bool) -> None:
        (self._enabled.add if on else self._enabled.discard)(str(name))
        self._save()

    def always(self) -> set[str]:
        return set(self._always)

    def allow_always(self, tool: str) -> None:
        if server_of(str(tool)):
            self._always.add(str(tool))
            self._save()

    def forget(self, tool: str) -> None:
        self._always.discard(str(tool))
        self._save()

    # ---- what Claude Code reports ------------------------------------------------------------------------

    def note_tools(self, tools) -> None:
        """Tool names from an agent's start: the Tools page can mark them always allowed before they are asked."""
        by_server: dict[str, set[str]] = {}
        for tool in tools if isinstance(tools, list) else []:
            server = server_of(str(tool))
            if server and server != "ai-browser":
                by_server.setdefault(server, set()).add(str(tool))
        changed = False
        for server, names in by_server.items():
            merged = sorted(set(self._known.get(server, [])) | names)
            if merged != self._known.get(server):
                self._known[server], changed = merged, True
        if changed:
            self._save()

    def note_servers(self, servers) -> None:
        """The servers Claude Code loaded for the user's account: the claude.ai connectors among them."""
        found = {connector_name(item["name"]): str(item.get("status", ""))
                 for item in servers if isinstance(item, dict) and isinstance(item.get("name"), str)
                 and item["name"].startswith("claude.ai ")} if isinstance(servers, list) else {}
        if found != self._connectors:
            self._connectors = found
            self._save()

    async def probe(self, claude: str | None = None, timeout: float = 30) -> bool:
        """Start Claude Code the way a connector-using agent does, read which servers and tools it loaded, and end
        it before it answers."""
        claude = claude or shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude")
        folder = self.path.parent / "app" / "probe"
        folder.mkdir(parents=True, exist_ok=True)
        env = {key: value for key, value in os.environ.items()
               if key not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
        try:
            process = await asyncio.create_subprocess_exec(
                claude, "-p", PROBE_PROMPT, "--model", "haiku", "--tools", "", "--setting-sources", "local",
                "--no-session-persistence", "--output-format", "stream-json", "--verbose", cwd=folder, env=env, stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, limit=32 * 1024 * 1024)
        except OSError:
            return False
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        try:
            while True:
                line = await asyncio.wait_for(process.stdout.readline(), max(0.1, deadline - loop.time()))
                if not line:
                    return False
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") == "system" and event.get("subtype") == "init":
                    self.note_servers(event.get("mcp_servers") or [])
                    self.note_tools(event.get("tools") or [])
                    return True
        except TimeoutError:
            return False
        finally:
            if process.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                await process.wait()

    # ---- the file ----------------------------------------------------------------------------------------

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"enabled": sorted(self._enabled), "always": sorted(self._always), "known": self._known,
                "connectors": [{"name": name, "status": status} for name, status in self._connectors.items()]}
        write_atomic(self.path, json.dumps(data).encode("utf-8"), 0o600)
