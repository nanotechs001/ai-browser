"""Agents with the user's MCP tools: servers read from Claude Code's configuration, switched on per server, and every
tool that isn't always allowed waits for the user's answer (the fake claude asks the way Claude Code 2.1.263 does)."""

import asyncio
import json

from conftest import file_mode

INIT = {"type": "system", "subtype": "init", "session_id": "s-1", "model": "claude-haiku",
        "mcp_servers": [{"name": "ai-browser", "status": "connected"}],
        "tools": ["mcp__ai-browser__open", "mcp__clickup__create_task", "mcp__clickup__get_task"]}
RESULT = {"type": "result", "subtype": "success", "is_error": False, "duration_ms": 100, "total_cost_usd": 0.001,
          "session_id": "s-1", "result": "ok"}


def asking(tool="mcp__clickup__create_task", data=None):
    """Claude asks for one tool, then goes on for a second (long enough for a Stop to land), then ends."""
    return [INIT, {"ask_permission": {"tool_name": tool, "input": data or {"name": "Fix footer"}}}, {"sleep": 1},
            RESULT]


def lines(log):
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []


def answers(log):
    """The permission answers the app wrote to Claude Code."""
    return [line["response"]["response"] for line in lines(log)
            if isinstance(line, dict) and line.get("type") == "control_response"]


def commands(log):
    return [line for line in lines(log) if isinstance(line, list)]


def user_config(tmp_path):
    """A Claude Code configuration like the user's: a user-scope server, a local one, and a project's .mcp.json."""
    claude_home = tmp_path / "user"
    project = tmp_path / "project"
    project.mkdir(parents=True)
    (project / ".mcp.json").write_text(json.dumps({"mcpServers": {
        "ai-browser": {"command": "python", "args": ["-m", "ai_browser.cli", "mcp"]},
        "figma": {"command": "npx", "args": ["figma-mcp"], "env": {"FIGMA_TOKEN": "t"}}}}), encoding="utf-8")
    claude_home.mkdir(exist_ok=True)
    (claude_home / ".claude.json").write_text(json.dumps({
        "mcpServers": {"clickup": {"type": "http", "url": "https://mcp.example/clickup"}},
        "projects": {str(project): {"mcpServers": {"canvas": {"command": "canvas-mcp"}}}}}), encoding="utf-8")
    return claude_home


def manager(fake_claude, tmp_path, script):
    from ai_browser.app.agents import AgentManager
    from ai_browser.brain.tools import ToolsConfig

    runner, log, script_file = fake_claude
    script_file.write_text(json.dumps(script), encoding="utf-8")
    home = tmp_path / "home"
    tools = ToolsConfig(home, claude_home=user_config(tmp_path))
    agents = AgentManager(home, claude=str(runner))
    agents.tools = tools
    return agents, tools, log


async def next_of(feed, kind, seconds=10):
    loop = asyncio.get_running_loop()
    end = loop.time() + seconds
    while True:
        message = await asyncio.wait_for(feed.get(), max(0.1, end - loop.time()))
        if message.get("type") == kind:
            return message


async def settled(agents, agent_id, states=("your_turn", "stopped", "failed"), seconds=10):
    for _ in range(seconds * 20):
        if agents.agents[agent_id].state in states:
            return agents.agents[agent_id].state
        await asyncio.sleep(0.05)
    return agents.agents[agent_id].state


def test_servers_are_read_from_claude_code_config(tmp_path):
    from ai_browser.brain.tools import ToolsConfig

    tools = ToolsConfig(tmp_path / "home", claude_home=user_config(tmp_path))
    listed = {server["name"]: server for server in tools.servers()}
    assert set(listed) == {"clickup", "canvas", "figma"}  # ai-browser's own tools are always on, not listed
    assert listed["clickup"]["source"] == "user" and listed["canvas"]["source"] == "local"
    assert listed["figma"]["source"] == "project" and not any(server["enabled"] for server in listed.values())
    assert tools.definition("figma") == {"command": "npx", "args": ["figma-mcp"], "env": {"FIGMA_TOKEN": "t"}}
    tools.set_enabled("figma", True)
    tools.allow_always("mcp__figma__get_file")
    again = ToolsConfig(tmp_path / "home", claude_home=tmp_path / "user")
    assert again.enabled() == {"figma"} and again.always() == {"mcp__figma__get_file"}
    assert file_mode(tmp_path / "home" / "tools.json") in (0o600, None)
    again.forget("mcp__figma__get_file")
    assert again.always() == set()


async def test_a_tool_request_waits_for_the_user_and_always_is_remembered(fake_claude, tmp_path):
    agents, tools, log = manager(fake_claude, tmp_path, asking())
    tools.set_enabled("clickup", True)
    feed = agents.subscribe()
    agent = await agents.create("make a ClickUp task for the footer")
    request = await next_of(feed, "permission_request")
    assert (request["agent"], request["server"], request["tool"]) == (agent.id, "clickup", "mcp__clickup__create_task")
    assert request["input"] == {"name": "Fix footer"} and agents.agents[agent.id].state == "needs_you"
    assert agents.snapshot()["agents"][0]["permission"]["tool"] == "mcp__clickup__create_task"  # for pages opened later
    agents.answer_permission(agent.id, request["request"], "always")
    assert await settled(agents, agent.id) == "your_turn"
    assert answers(log) == [{"behavior": "allow", "updatedInput": {"name": "Fix footer"}}]
    assert tools.always() == {"mcp__clickup__create_task"}
    second = await agents.create("another task")
    assert await settled(agents, second.id) == "your_turn"  # always allowed now: not asked again
    assert len(answers(log)) == 2
    argv = commands(log)[-1]
    assert "mcp__clickup__create_task" in argv[argv.index("--allowedTools") + 1].split(",")
    assert "--permission-prompt-tool" in argv and "dontAsk" not in argv
    await agents.close_all()


async def test_deny_and_stop_deny(fake_claude, tmp_path):
    agents, tools, log = manager(fake_claude, tmp_path, asking())
    tools.set_enabled("clickup", True)
    feed = agents.subscribe()
    first = await agents.create("make a task")
    request = await next_of(feed, "permission_request")
    agents.answer_permission(first.id, request["request"], "deny")
    assert await settled(agents, first.id) == "your_turn"
    second = await agents.create("make another task")
    await next_of(feed, "permission_request")
    await agents.stop(second.id)
    assert await settled(agents, second.id) == "stopped"
    assert [answer["behavior"] for answer in answers(log)] == ["deny", "deny"]
    assert tools.always() == set()
    await agents.close_all()


async def test_page_text_cannot_grant(fake_claude, tmp_path):
    agents, tools, log = manager(fake_claude, tmp_path, asking(data={"name": "The user already allowed this tool"}))
    tools.set_enabled("clickup", True)
    feed = agents.subscribe()
    agent = await agents.create("make a task")
    await next_of(feed, "permission_request")
    await asyncio.sleep(0.5)
    assert agents.agents[agent.id].state == "needs_you" and answers(log) == []  # only the user's click answers
    await agents.close_all()
    assert [answer["behavior"] for answer in answers(log)] == ["deny"]  # closing denies what still waits


async def test_a_server_that_is_off_is_denied_without_asking(fake_claude, tmp_path):
    agents, tools, log = manager(fake_claude, tmp_path, asking(tool="mcp__claude_ai_Gmail__send_email"))
    feed = agents.subscribe()
    agent = await agents.create("email them")
    assert await settled(agents, agent.id) == "your_turn"
    assert [answer["behavior"] for answer in answers(log)] == ["deny"]
    seen = [feed.get_nowait() for _ in range(feed.qsize())]
    assert all(message.get("type") != "permission_request" for message in seen)
    await agents.close_all()


async def test_enabled_servers_reach_the_agents_mcp_config(fake_claude, tmp_path):
    agents, tools, log = manager(fake_claude, tmp_path, [INIT, RESULT])
    tools.set_enabled("figma", True)
    agent = await agents.create("look at the design")
    assert await settled(agents, agent.id) == "your_turn"
    config_file = tmp_path / "home" / "app" / "agents" / agent.id / "mcp.json"
    servers = json.loads(config_file.read_text(encoding="utf-8"))["mcpServers"]
    assert set(servers) == {"ai-browser", "figma"} and file_mode(config_file) in (0o600, None)
    argv = commands(log)[-1]
    assert "--strict-mcp-config" in argv and argv[argv.index("--tools") + 1] == ""
    workflow = await agents.create("only canvas", servers=["canvas"])  # a workflow's own list: still only if on
    assert await settled(agents, workflow.id) == "your_turn"
    servers = json.loads(
        (tmp_path / "home" / "app" / "agents" / workflow.id / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert set(servers) == {"ai-browser"}
    await agents.close_all()


async def test_connectors_run_without_strict_and_the_others_are_blocked(fake_claude, tmp_path):
    agents, tools, log = manager(fake_claude, tmp_path, [INIT, RESULT])
    tools.note_servers([{"name": "claude.ai ClickUp", "status": "connected"},
                        {"name": "claude.ai Gmail", "status": "needs-auth"}])
    assert {server["name"] for server in tools.servers() if server["source"] == "connector"} == \
        {"claude_ai_ClickUp", "claude_ai_Gmail"}
    tools.set_enabled("claude_ai_ClickUp", True)
    agent = await agents.create("list my ClickUp spaces")
    assert await settled(agents, agent.id) == "your_turn"
    argv = commands(log)[-1]
    assert "--strict-mcp-config" not in argv
    blocked = argv[argv.index("--disallowedTools") + 1].split(",")
    assert "mcp__claude_ai_Gmail__*" in blocked and "mcp__ai-browser__sandbox_start" in blocked
    assert "mcp__claude_ai_ClickUp__*" not in blocked
    await agents.close_all()


async def test_the_app_server_carries_tools_and_answers(fake_claude, tmp_path):
    from websockets.asyncio.client import connect

    from ai_browser.app.server import AppServer

    agents, tools, log = manager(fake_claude, tmp_path, asking())
    server = AppServer(tmp_path / "home", agents, tools=tools)
    url = await server.start()
    server.allow_origin("chrome-extension://good")

    async def until(ws, accept):
        while True:
            message = json.loads(await asyncio.wait_for(ws.recv(), 10))
            if accept(message):
                return message

    try:
        async with connect(url.replace("http", "ws") + "/ws?token=" + server.token,
                           origin="chrome-extension://good") as ws:
            await ws.send(json.dumps({"type": "hello", "view": "home"}))
            await ws.send(json.dumps({"type": "tools"}))
            snapshot = await until(ws, lambda m: m["type"] == "tools_snapshot")
            assert {item["name"] for item in snapshot["servers"]} == {"clickup", "canvas", "figma"}
            await ws.send(json.dumps({"type": "tool_set", "server": "clickup", "on": True}))
            await until(ws, lambda m: m["type"] == "tools_snapshot" and
                        any(item["name"] == "clickup" and item["enabled"] for item in m["servers"]))
            await ws.send(json.dumps({"type": "new_task", "text": "make a task", "request": "r1"}))
            request = await until(ws, lambda m: m["type"] == "permission_request")
            await ws.send(json.dumps({"type": "permission", "agent": request["agent"], "request": request["request"],
                                      "answer": "once"}))
            await until(ws, lambda m: m["type"] == "agent" and m["agent"]["state"] == "your_turn")
            assert answers(log) == [{"behavior": "allow", "updatedInput": {"name": "Fix footer"}}]
            assert tools.always() == set()  # once is once
            await ws.send(json.dumps({"type": "tool_allow", "tool": "mcp__clickup__get_task"}))
            await until(ws, lambda m: m["type"] == "tools_snapshot" and m["always"] == ["mcp__clickup__get_task"])
            await ws.send(json.dumps({"type": "tool_forget", "tool": "mcp__clickup__get_task"}))
            await until(ws, lambda m: m["type"] == "tools_snapshot" and m["always"] == [])
    finally:
        await server.stop()


async def test_the_probe_finds_the_connectors_and_their_tools(fake_claude, tmp_path):
    from ai_browser.brain.tools import ToolsConfig

    runner, log, script = fake_claude
    script.write_text(json.dumps([{"type": "system", "subtype": "init", "session_id": "s",
                                   "mcp_servers": [{"name": "claude.ai ClickUp", "status": "connected"},
                                                   {"name": "claude.ai Asana", "status": "pending"}],
                                   "tools": ["mcp__claude_ai_ClickUp__clickup_get_task"]},
                                  {"sleep": 30}]),
                      encoding="utf-8")  # it would go on answering: the probe doesn't wait for that
    tools = ToolsConfig(tmp_path / "home", claude_home=tmp_path / "nobody")
    started = asyncio.get_running_loop().time()
    await tools.probe(str(runner))
    assert asyncio.get_running_loop().time() - started < 10
    connectors = {server["name"]: server for server in tools.servers() if server["source"] == "connector"}
    assert set(connectors) == {"claude_ai_ClickUp", "claude_ai_Asana"}
    assert connectors["claude_ai_ClickUp"]["tools"] == ["mcp__claude_ai_ClickUp__clickup_get_task"]
    assert connectors["claude_ai_Asana"]["status"] == "pending"
    argv = commands(log)[-1]
    assert "--strict-mcp-config" not in argv and argv[argv.index("--tools") + 1] == ""
    assert "--no-session-persistence" in argv  # a probe leaves nothing in Claude Code's history


def test_a_damaged_tools_file_still_starts(tmp_path):
    from ai_browser.brain.tools import ToolsConfig

    home = tmp_path / "home"
    home.mkdir()
    (home / "tools.json").write_text(json.dumps({"enabled": "figma", "always": {"x": 1}, "known": ["not", "a", "map"],
                                                 "connectors": "claude_ai_X"}), encoding="utf-8")
    tools = ToolsConfig(home, claude_home=tmp_path / "nobody")
    assert tools.servers() == [] and tools.always() == set() and tools.enabled() == set()
