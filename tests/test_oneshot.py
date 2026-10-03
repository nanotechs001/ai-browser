"""One-shot Claude calls for the Brain: no tools, the prompt on stdin, the user's own login only."""

import json


def oneshots(log):
    """The one-shot calls the fake claude received, in order."""
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.startswith('{"oneshot"')]


async def test_ask_claude_is_tool_less_and_reads_the_prompt_from_stdin(fake_claude, tmp_path, monkeypatch):
    from ai_browser.brain.oneshot import ask_claude

    runner, log, script = fake_claude
    script.write_text(json.dumps([{"result": "hello back"}]), encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    answer = await ask_claude("a long prompt\nwith lines", model="haiku", claude=runner, cwd=tmp_path / "calls")
    assert answer.text == "hello back" and not answer.error and answer.cost == 0.001
    [call] = oneshots(log)
    assert call["oneshot"] == "a long prompt\nwith lines"
    argv = call["argv"]
    assert argv[argv.index("--tools") + 1] == "" and "--strict-mcp-config" in argv and "--bare" not in argv
    assert json.loads(argv[argv.index("--mcp-config") + 1]) == {"mcpServers": {}}
    assert "--no-session-persistence" in argv and argv[argv.index("--model") + 1] == "haiku"
    assert argv[argv.index("--setting-sources") + 1] == "local"
    assert argv[argv.index("--output-format") + 1] == "json" and "--input-format" not in argv
    assert not any("a long prompt" in arg for arg in argv)  # never on the command line
    given = json.loads(log.with_name(log.name + ".env").read_text(encoding="utf-8"))
    assert given["ANTHROPIC_API_KEY"] is None and given["ANTHROPIC_AUTH_TOKEN"] is None
    assert given["cwd"] == str((tmp_path / "calls").resolve())


async def test_ask_claude_reports_plain_errors(fake_claude, tmp_path):
    from ai_browser.brain.oneshot import ask_claude

    runner, log, script = fake_claude
    missing = await ask_claude("hi", claude=str(tmp_path / "no-claude"), cwd=tmp_path)
    assert missing.text == "" and "Claude Code isn't available" in missing.error
    script.write_text(json.dumps([{"exit": 3}]), encoding="utf-8")
    failed = await ask_claude("hi", claude=runner, cwd=tmp_path)
    assert failed.text == "" and "exit 3" in failed.error
    script.write_text(json.dumps([{"sleep": 5, "result": "late"}]), encoding="utf-8")
    slow = await ask_claude("hi", claude=runner, cwd=tmp_path, timeout=0.5)
    assert slow.text == "" and "longer than" in slow.error
    script.write_text(json.dumps([{"result": "Usage limit reached", "is_error": True}]), encoding="utf-8")
    refused = await ask_claude("hi", claude=runner, cwd=tmp_path)
    assert refused.text == "" and "Usage limit reached" in refused.error


async def test_one_shot_answers_follow_the_script_in_order(fake_claude, tmp_path):
    from ai_browser.brain.oneshot import ask_claude

    runner, log, script = fake_claude
    script.write_text(json.dumps([{"result": "one"}, {"result": "two"}]), encoding="utf-8")
    answers = [(await ask_claude("hi", claude=runner, cwd=tmp_path)).text for _ in range(3)]
    assert answers == ["one", "two", "two"]
    script.write_text(json.dumps({"default": [{"result": "plain"}], "Sort these": [{"result": "sorted"}]}),
                      encoding="utf-8")
    assert (await ask_claude("Sort these, please", claude=runner, cwd=tmp_path)).text == "sorted"
    assert (await ask_claude("Something else", claude=runner, cwd=tmp_path)).text == "plain"


async def test_thinking_is_off_unless_asked_for(fake_claude, tmp_path, monkeypatch):
    from ai_browser.brain.oneshot import ask_claude

    runner, log, script = fake_claude
    script.write_text(json.dumps([{"result": "ok"}]), encoding="utf-8")
    monkeypatch.setenv("MAX_THINKING_TOKENS", "8000")  # the user's own setting, for their own Claude Code
    env_log = log.with_name(log.name + ".env")
    await ask_claude("sort these", claude=runner, cwd=tmp_path)
    # sorting is quick work: no thinking
    assert json.loads(env_log.read_text(encoding="utf-8"))["MAX_THINKING_TOKENS"] == "0"
    await ask_claude("write a skill", claude=runner, cwd=tmp_path, think=True)
    assert json.loads(env_log.read_text(encoding="utf-8"))["MAX_THINKING_TOKENS"] == "8000"


async def test_a_cancelled_call_ends_its_claude(fake_claude, tmp_path):
    import asyncio

    import pytest

    from ai_browser.brain.oneshot import ask_claude

    runner, log, script = fake_claude
    script.write_text(json.dumps([{"sleep": 30, "result": "late"}]), encoding="utf-8")
    call = asyncio.ensure_future(ask_claude("hi", claude=runner, cwd=tmp_path))
    for _ in range(100):
        if oneshots(log):
            break
        await asyncio.sleep(0.05)
    pid = json.loads(log.with_name(log.name + ".env").read_text(encoding="utf-8"))["pid"]
    call.cancel()  # the app stopping, or the user's Stop
    with pytest.raises(asyncio.CancelledError):
        await call
    from ai_browser import platforms

    assert not platforms.pid_alive(pid)


async def test_text_with_half_an_emoji_still_reaches_claude(fake_claude, tmp_path):
    from ai_browser.brain.oneshot import ask_claude

    runner, log, script = fake_claude
    script.write_text(json.dumps([{"result": "ok"}]), encoding="utf-8")
    answer = await ask_claude("cut here: \ud83d.", claude=runner, cwd=tmp_path)
    assert answer.text == "ok" and not answer.error
    assert oneshots(log)[0]["oneshot"].startswith("cut here: ")
