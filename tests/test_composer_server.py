"""The composer's server side (the new look, Decision 9): files attached in pieces and placed in the agent's folder
under attachments/, the Web ▾ choice as the agent's tools, and the rights table. On the fake claude, over a real
socket, in throwaway folders."""

import base64
import json

import pytest

from test_app_server import started, told, until, wait_for
from test_bridge import EVENTS
from test_bridge_powers import bridge_for, flag
from test_tools import commands
from ui_socket import ui_socket

ATTACH = ("attach_start", "attach_chunk", "attach_drop")


def test_the_attach_messages_are_app_only():  # the spec's Safety: no new right
    from ai_browser.app.server import MESSAGE_RULES, may_send

    for kind in ATTACH:
        assert kind in MESSAGE_RULES and may_send("app", {"type": kind}) and not may_send("none", {"type": kind})


@pytest.mark.parametrize(("web", "web_tools", "page_tools_blocked"), [("web", True, False), ("brave", False, False),
                                                                      ("none", False, True), ("odd", True, False)])
async def test_web_picks_the_agents_web_tools(fake_claude, tmp_path, web, web_tools, page_tools_blocked):
    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    bridge, _ = bridge_for(tmp_path, runner, web=web)
    [event async for event in bridge.send("hi")]
    await bridge.close()
    argv = commands(log)[0]
    tools = flag(argv, "--tools").split(",")
    assert ("WebSearch" in tools and "WebFetch" in tools) is web_tools
    assert "Bash" in tools and "Read" in tools  # its own tools stay
    blocked = flag(argv, "--disallowedTools").split(",")
    assert ("mcp__ai-browser__open" in blocked and "mcp__ai-browser__act" in blocked) is page_tools_blocked
    assert ("mcp__ai-browser__shell" in blocked) is page_tools_blocked  # its Docker shell has the internet: "none"
    assert "mcp__ai-browser__load_skill" not in blocked and "mcp__ai-browser__sandbox_start" in blocked


async def hello(ws):
    await ws.send(json.dumps({"type": "hello", "view": "mission"}))
    await until(ws, lambda message: message["type"] == "snapshot")


async def send_file(ws, upload, name, data, piece=5):
    """A file sent the way the composer sends it: attach_start, then its pieces once the app is ready."""
    await ws.send(json.dumps({"type": "attach_start", "upload": upload, "name": name, "size": len(data)}))
    ready = (await until(ws, lambda m: m.get("upload") == upload or m.get("request") == upload))[-1]
    if ready["type"] != "attach_ready":
        return ready
    for seq, start in enumerate(range(0, len(data), piece)):
        await ws.send(json.dumps({"type": "attach_chunk", "upload": upload, "seq": seq,
                                  "data": base64.b64encode(data[start:start + piece]).decode()}))
    return (await until(ws, lambda m: (m["type"] == "attach_done" and m["upload"] == upload)
                        or m.get("request") == upload))[-1]


async def test_attached_files_land_in_the_agents_folder_and_are_named_in_the_task(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    log = fake_claude[1]
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            assert (await send_file(ws, "u1", "../shot.png", b"\x89PNG-image"))["type"] == "attach_done"
            assert (await send_file(ws, "u2", "notes.txt", b""))["type"] == "attach_done"  # an empty file is fine
            await ws.send(json.dumps({"type": "new_task", "text": "look at these", "attachments": ["u1", "u2"],
                                      "web": "brave", "request": "m1"}))
            created = (await until(ws, lambda m: m.get("request") == "m1"))[-1]
            assert created["type"] == "created"
            agent = server.agents.agents[created["id"]]
            await wait_for(lambda: agent.state == "your_turn")
            folder = tmp_path / "home" / "app" / "agents" / agent.id / "work" / "attachments"
            assert sorted(path.name for path in folder.iterdir()) == ["notes.txt", "shot.png"]
            assert (folder / "shot.png").read_bytes() == b"\x89PNG-image"
            first = told(log)[0]
            assert first.startswith("look at these\n\nThe user attached these files.")
            assert "- attachments/shot.png (a picture: look at it with Read)" in first
            assert agent.web == "brave" and agent.name == "look at these"
            tools = flag(commands(log)[0], "--tools").split(",")
            assert "WebSearch" not in tools and "WebFetch" not in tools and "Bash" in tools  # web= reached the bridge
            assert list((tmp_path / "home" / "app" / "uploads").glob("*.part")) == []
    finally:
        await server.agents.close_all()
        await server.stop()


async def test_a_task_waits_for_its_files_and_a_refused_one_keeps_them(fake_claude, tmp_path, user_home):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            await ws.send(json.dumps({"type": "attach_start", "upload": "u1", "name": "data.bin", "size": 10}))
            await until(ws, lambda m: m["type"] == "attach_ready")
            await ws.send(json.dumps({"type": "new_task", "text": "x", "attachments": ["u1"], "request": "m1"}))
            assert (await until(ws, lambda m: m.get("request") == "m1"))[-1] == {
                "type": "error", "text": "Wait for the attached files to finish", "request": "m1"}
            await ws.send(json.dumps({"type": "attach_chunk", "upload": "u1", "seq": 0,
                                      "data": base64.b64encode(b"0123456789").decode()}))
            await until(ws, lambda m: m["type"] == "attach_done")
            await ws.send(json.dumps({"type": "new_task", "text": "x", "attachments": ["u1"],
                                      "folder": str(tmp_path / "gone"), "request": "m2"}))
            assert (await until(ws, lambda m: m.get("request") == "m2"))[-1]["type"] == "error"  # a refused folder
            await ws.send(json.dumps({"type": "new_task", "text": "x", "attachments": ["u1"], "request": "m3"}))
            created = (await until(ws, lambda m: m.get("request") == "m3"))[-1]
            assert created["type"] == "created"  # the file was kept for the next try
            assert list(server.agents.agents) == [created["id"]]
    finally:
        await server.agents.close_all()
        await server.stop()


async def test_a_huge_or_extra_attachment_is_refused_and_a_closed_page_leaves_nothing(  # Review Focus 5
        fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    uploads = tmp_path / "home" / "app" / "uploads"
    try:
        async with ui_socket(server, url) as ws:
            await hello(ws)
            await ws.send(json.dumps({"type": "attach_start", "upload": "u0", "name": "movie.mov",
                                      "size": 20_000_001}))
            assert (await until(ws, lambda m: m.get("request") == "u0"))[-1]["text"] == "movie.mov is over 20 MB"
            for number in range(1, 11):
                await ws.send(json.dumps({"type": "attach_start", "upload": f"u{number}", "name": "a.txt",
                                          "size": 4}))
            await ws.send(json.dumps({"type": "attach_start", "upload": "u11", "name": "a.txt", "size": 4}))
            assert (await until(ws, lambda m: m.get("request") == "u11"))[-1]["text"] == "At most 10 files at once"
            assert len(list(uploads.glob("*.part"))) == 10
        await wait_for(lambda: not list(uploads.glob("*.part")))  # the page went: its files went with it
    finally:
        await server.stop()


async def test_files_left_by_a_crash_are_cleared_at_start(fake_claude, tmp_path):
    left = tmp_path / "home" / "app" / "uploads"
    left.mkdir(parents=True)
    (left / "old.part").write_bytes(b"x")
    server, _ = await started(fake_claude, tmp_path, EVENTS)
    try:
        assert not (left / "old.part").exists()
    finally:
        await server.stop()


def scratch_manager(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager

    runner, log, script = fake_claude
    script.write_text(json.dumps(EVENTS), encoding="utf-8")
    return AgentManager(tmp_path / "home", claude=runner)


def staged(tmp_path, data=b"new"):
    path = tmp_path / "staged.part"
    path.write_bytes(data)
    return path


async def test_an_agents_scratch_folder_is_never_reused_with_a_past_runs_attachments(  # Review I2
        fake_claude, tmp_path):
    """Agent ids restart at a1 every run, and a1's scratch folder is still there: a new a1 starts without the old
    attachments (a folder or a link), whatever it attaches itself, and a link's target is never touched."""
    agents = scratch_manager(fake_claude, tmp_path)
    work = tmp_path / "home" / "app" / "agents" / "a1" / "work"
    (work / "attachments").mkdir(parents=True)
    (work / "attachments" / "old.txt").write_text("last run's", encoding="utf-8")
    (work / "attachments" / "inner").mkdir()
    try:
        agent = await agents.create("x", files=[(staged(tmp_path), "new.txt")])
        assert agent.id == "a1"
        await wait_for(lambda: agent.state == "your_turn")
        assert [path.name for path in (work / "attachments").iterdir()] == ["new.txt"]
        assert (work / "attachments" / "new.txt").read_bytes() == b"new"
        assert "old.txt" not in told(fake_claude[1])[0]
        second = await agents.create("y")  # no files at all: a2's folder was never used, nothing to clear
        assert second.id == "a2" and not (work.parent.parent / "a2" / "work" / "attachments").exists()
    finally:
        await agents.close_all()


async def test_a_stale_attachments_link_in_the_scratch_folder_is_unlinked_not_followed(
        fake_claude, tmp_path):  # Review I2
    from conftest import symlink_or_skip

    agents = scratch_manager(fake_claude, tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("not the agent's", encoding="utf-8")
    work = tmp_path / "home" / "app" / "agents" / "a1" / "work"
    work.mkdir(parents=True)
    symlink_or_skip(outside, work / "attachments")
    try:
        agent = await agents.create("x", files=[(staged(tmp_path), "new.txt")])
        await wait_for(lambda: agent.state == "your_turn")
        assert not (work / "attachments").is_symlink()
        assert [path.name for path in (work / "attachments").iterdir()] == ["new.txt"]
        assert [path.name for path in outside.iterdir()] == ["keep.txt"]  # untouched: no file in, none out
        assert (outside / "keep.txt").read_text(encoding="utf-8") == "not the agent's"
    finally:
        await agents.close_all()


async def test_a_stale_attachments_link_goes_even_when_nothing_is_attached(fake_claude, tmp_path):  # Review I2
    from conftest import symlink_or_skip

    agents = scratch_manager(fake_claude, tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("x", encoding="utf-8")
    work = tmp_path / "home" / "app" / "agents" / "a1" / "work"
    work.mkdir(parents=True)
    symlink_or_skip(outside, work / "attachments")
    try:
        agent = await agents.create("x")
        await wait_for(lambda: agent.state == "your_turn")
        assert not (work / "attachments").exists() and not (work / "attachments").is_symlink()
        assert (outside / "keep.txt").exists()
    finally:
        await agents.close_all()


async def test_a_chosen_folders_own_attachments_are_never_cleared(fake_claude, tmp_path, user_home):  # Review I2
    agents = scratch_manager(fake_claude, tmp_path)
    project = tmp_path / "project"
    (project / "attachments").mkdir(parents=True)
    (project / "attachments" / "mine.txt").write_text("the user's own", encoding="utf-8")
    agents.rules.trust(project)
    try:
        agent = await agents.create("x", folder=str(project))
        await wait_for(lambda: agent.state == "your_turn")
        assert (project / "attachments" / "mine.txt").read_text(encoding="utf-8") == "the user's own"
    finally:
        await agents.close_all()
