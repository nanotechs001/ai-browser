import os
import subprocess

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from ai_browser import testpages
from ai_browser.config import project_root
from ai_browser.engine import Engine, ToolResult
from ai_browser.sandbox import SandboxInfo, Sandboxes
from ai_browser.server import build_server
from ai_browser.skills import Catalog, SkillSource

SPEC_TOOLS = {
    "sandbox_start", "sandbox_stop", "sandbox_status", "open", "observe", "act", "screenshot", "tabs",
    "page_log", "extract", "js", "shell", "read_file", "write_file", "find_skills", "load_skill",
    "read_skill_file", "qa",
}


class FakeEngine:
    async def screenshot(self, size="desktop", full_page=False, element=None):
        return ToolResult("desktop 2×2 saved /tmp/x.jpg", [b"\xff\xd8\xff\xd9"])

    async def qa(self, url, max_pages=30, progress=None):
        if progress is not None:
            await progress(1, max_pages, "checked 1 of up to 30 pages")
        return ToolResult(f"qa {url} — 1 page in 0.1 s")

    async def close(self):
        pass


async def test_lists_exactly_the_spec_tools():
    async with Client(build_server(FakeEngine)) as client:
        tools = await client.list_tools()
    assert {tool.name for tool in tools.tools} == SPEC_TOOLS
    act = next(tool for tool in tools.tools if tool.name == "act")
    assert "confirmed" in act.input_schema["properties"]
    assert "drag e7 e12" in act.description


async def test_qa_tool_is_listed_with_its_parameters():
    async with Client(build_server(FakeEngine)) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
        result = await client.call_tool("qa", {"url": "https://s.com/"})
    assert set(tools["qa"].input_schema["properties"]) == {"url", "max_pages"}
    assert result.content[0].text.startswith("qa https://s.com/ — 1 page")


async def test_sandbox_start_can_use_the_users_own_chrome():
    async with Client(build_server(FakeEngine)) as client:
        tools = await client.list_tools()
    start = next(tool for tool in tools.tools if tool.name == "sandbox_start")
    assert "chrome" in start.input_schema["properties"]
    assert "own Chrome" in start.description


async def test_screenshot_comes_back_as_text_and_jpeg_image():
    async with Client(build_server(FakeEngine)) as client:
        result = await client.call_tool("screenshot", {"size": "desktop"})
    kinds = [block.type for block in result.content]
    assert kinds == ["text", "image"]
    assert result.content[1].mime_type == "image/jpeg"


async def test_skill_tools_work_without_docker(tmp_path):
    folder = tmp_path / "root" / "skills" / "hello"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text("---\nname: hello\ndescription: Greets people\n---\nSay hi.\n")
    catalog = Catalog([SkillSource("demo", tmp_path / "root", "/skills/plugins/demo", "skills/*/SKILL.md")], set())
    async with Client(build_server(lambda: Engine(home=tmp_path, catalog=catalog))) as client:
        found = await client.call_tool("find_skills", {"query": "greets"})
        loaded = await client.call_tool("load_skill", {"name": "demo:hello"})
    assert "demo:hello — Greets people" in found.content[0].text
    assert "Say hi." in loaded.content[0].text


@pytest.mark.docker
async def test_stdio_end_to_end(tmp_path):
    env = {"AIB_HOME": str(tmp_path), "AIB_PROFILE": "pytest-mcp", "PATH": os.environ["PATH"],
           "HOME": os.environ["HOME"]}
    params = StdioServerParameters(command="uv", args=["run", "--directory", str(project_root()), "ai-browser", "mcp"],
                                   env=env)
    try:
        async with Client(params, read_timeout_seconds=120) as client:
            started = await client.call_tool("sandbox_start", {"profile": "pytest-mcp"})
            assert "ready" in started.content[0].text
            info = SandboxInfo("aib-pytest-mcp", "pytest-mcp", "", tmp_path / "sandboxes" / "pytest-mcp" / "work",
                               False, False)
            base, _ = testpages.serve(Sandboxes(tmp_path), info)
            opened = await client.call_tool("open", {"url": base + "form.html"})
            assert 'page  "Form test"' in opened.content[0].text
            increment = next(line.split()[0] for line in opened.content[0].text.splitlines() if '"Increment"' in line)
            acted = await client.call_tool("act", {"steps": [f"click {increment}"]})
            assert acted.content[0].text.startswith("✓ click")
            shot = await client.call_tool("screenshot", {})
            assert [block.type for block in shot.content] == ["text", "image"]
            await client.call_tool("sandbox_stop", {})
    finally:
        subprocess.run(["docker", "rm", "-f", "aib-pytest-mcp"], capture_output=True)
        subprocess.run(["docker", "volume", "rm", "aib-profile-pytest-mcp"], capture_output=True)
