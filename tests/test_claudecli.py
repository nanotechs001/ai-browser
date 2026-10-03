"""Finding Claude Code on every OS: the native executable, never an npm .cmd script on Windows."""

import os
import shutil
import sys

import pytest

from ai_browser.claudecli import ClaudeNotUsable, claude_argv

NPM = "C:\\Users\\me\\AppData\\Roaming\\npm\\claude.cmd"


def test_a_list_or_a_string_is_kept_as_it_is():
    assert claude_argv([sys.executable, "fake_claude.py"], env={}) == [sys.executable, "fake_claude.py"]
    assert claude_argv(("claude", "--debug"), env={}) == ["claude", "--debug"]
    assert claude_argv("/opt/claude", env={}) == ["/opt/claude"]


def test_aib_claude_wins_over_path(tmp_path):
    folder = tmp_path / "bin"
    folder.mkdir()
    for name in ("claude", "claude.exe"):
        (folder / name).write_bytes(b"")
        (folder / name).chmod(0o755)
    assert claude_argv(env={"AIB_CLAUDE": "/somewhere/claude", "PATH": str(folder)}) == ["/somewhere/claude"]
    found = shutil.which("claude", path=str(folder))
    assert found and claude_argv(env={"PATH": str(folder)}) == [found]


def test_windows_refuses_the_npm_script():
    for found in (NPM, NPM.replace("claude.cmd", "CLAUDE.BAT")):
        with pytest.raises(ClaudeNotUsable) as refused:
            claude_argv(found, system="win32", env={})
        message = str(refused.value)
        assert message.startswith(f"Claude Code was found at {found}, a script from the npm install.")
        assert "irm https://claude.ai/install.ps1 | iex" in message and "AIB_CLAUDE" in message
    with pytest.raises(ClaudeNotUsable):
        claude_argv(env={"AIB_CLAUDE": NPM}, system="win32")
    assert claude_argv("/opt/claude.cmd", system="darwin", env={}) == ["/opt/claude.cmd"]  # only cmd.exe mangles it


def test_windows_prefers_the_native_install(tmp_path):
    native = tmp_path / ".local" / "bin" / "claude.exe"
    native.parent.mkdir(parents=True)
    native.write_bytes(b"MZ")
    npm = tmp_path / "npm"
    npm.mkdir()
    (npm / "claude.cmd").write_text("@echo off\n", encoding="utf-8")
    assert claude_argv(env={"USERPROFILE": str(tmp_path), "PATH": str(npm)}, system="win32") == [str(native)]


async def test_the_panel_the_brain_and_the_probe_say_why(tmp_path, monkeypatch):
    from ai_browser.app.bridge import ClaudeBridge
    from ai_browser.brain.oneshot import ask_claude
    from ai_browser.brain.tools import ToolsConfig

    monkeypatch.setattr(sys, "platform", "win32")  # claude_argv's default system; nothing is started
    bridge = ClaudeBridge(tmp_path / "home", claude=NPM)
    [event] = [event async for event in bridge.send("hi")]
    assert event["type"] == "error" and event["text"].startswith(f"Claude Code was found at {NPM}")
    answer = await ask_claude("hi", claude=NPM, cwd=tmp_path / "calls")
    assert answer.text == "" and answer.error.startswith(f"Claude Code was found at {NPM}")
    assert await ToolsConfig(tmp_path / "home").probe(NPM) is False


def test_the_fake_claude_is_an_argv_prefix(fake_claude):
    runner, _, _ = fake_claude
    assert runner[0] == sys.executable and runner[1].endswith("fake_claude.py") and os.path.isfile(runner[1])
