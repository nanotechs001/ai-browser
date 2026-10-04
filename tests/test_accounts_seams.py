"""AI accounts builds on wave B (app-window) through a few names. This pins them, so no task starts on a name the
merged code spells differently."""

import inspect


def test_wave_b_has_the_names_this_plan_uses():
    from ai_browser import settings
    from ai_browser.app import bridge, server
    from ai_browser.app.agents import Agent, AgentManager
    from ai_browser.brain import oneshot, skillwriter, tools
    from ai_browser.claudecli import claude_argv, spawn_options, track

    assert callable(settings.read_settings) and callable(settings.write_setting) and callable(settings.Settings)
    assert set(settings.DEFAULTS) == {"window_browser", "model", "voice"}
    assert callable(server.may_send) and callable(server.for_watcher) and callable(server.AppServer._role)
    assert {"settings_set", "new_task", "model", "open_url", "tools", "tool_set"} <= set(server.MESSAGE_RULES)
    assert "settings" not in server.WATCHER_RECEIVES and "tools_snapshot" not in server.WATCHER_RECEIVES
    assert server.WATCHER_AGENT_FIELDS == ("id", "name", "color", "state", "permission")
    for name in ("_handle", "_snapshot", "_settings_payload", "_tools_command", "probe_tools", "_tools_snapshot",
                 "_job", "_send_all"):
        assert callable(getattr(server.AppServer, name)), name
    # the first parameters: later tasks add theirs after these (account, environment, env)
    assert list(inspect.signature(AgentManager.create).parameters)[:7] == ["self", "text", "skills", "model", "adopt",
                                                                          "tab", "servers"]
    for name in ("_run", "_on_event", "_ask", "answer_permission", "_record", "_changed", "_pump", "events_of"):
        assert callable(getattr(AgentManager, name)), name
    assert {"id", "name", "number", "queued", "state", "status"} <= set(Agent.PUBLIC)
    assert list(inspect.signature(bridge.ClaudeBridge).parameters)[:8] == ["home", "model", "claude", "env",
                                                                          "agent_id", "tools", "servers",
                                                                          "on_permission"]
    for name in ("send", "_events", "_translate", "_ended", "_start", "_command", "reset", "close"):
        assert callable(getattr(bridge.ClaudeBridge, name)), name
    assert callable(bridge.page_line) and {"panel", "handed"} <= set(bridge.LABELS) and bridge.RESTARTED
    assert list(inspect.signature(oneshot.ask_claude).parameters)[:6] == ["prompt", "model", "claude", "cwd",
                                                                         "timeout", "think"]
    assert "claude_home" in inspect.signature(tools.ToolsConfig).parameters
    assert "ask" in inspect.signature(skillwriter.SkillWriter).parameters and skillwriter.PAGE_BLOCK
    assert callable(claude_argv) and callable(spawn_options) and callable(track)
