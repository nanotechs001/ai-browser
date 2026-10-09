"""The engine's side of AI Browser's own app (app/server.py): the app's state in Settings; a shortcut the app tries
before it is saved; native notifications in fixed words, in place of Brave's; and their clicks. The app is a fake
(tests/fake_desktop.py), and the pages are sockets."""

import asyncio
import json
import sys

from fake_brave import add_agent
from fake_brave import until as settled
from fake_desktop import FakeDesktop
from test_app_server import recv, started, until
from test_bridge import EVENTS
from ui_socket import ui_socket

HOSTILE = 'Re: <img src=x onerror=alert(1)> wire $5,000 now'


def last_settings(seen: list[dict]) -> dict:
    return [message for message in seen if message["type"] == "settings"][-1]


def notes_of(app: FakeDesktop) -> list[dict]:
    return [message for message in app.sent if message["type"] == "notify"]


async def test_settings_say_whether_the_app_is_set_up_and_running(fake_claude, tmp_path):
    from ai_browser.desktop import layout
    from ai_browser.desktop.release import SETUP_COMMAND, VERSION, asset_for
    from ai_browser.desktop.shortcut import SHORTCUTS, label

    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        assert server._settings_payload()["desktop"] == {
            "running": False, "supported": asset_for() is not None, "set_up": False, "version": VERSION,
            "platform": {"darwin": "mac", "win32": "windows"}.get(sys.platform, "other"), "command": SETUP_COMMAND,
            "problem": "", "shortcut": {"value": "Alt+Space", "label": label("Alt+Space"), "state": "unknown"},
            "shortcuts": [{"value": one, "label": label(one)} for one in SHORTCUTS]}
        layout.set_problem(server.home, "The download stopped before the end: nothing was kept")
        server.attach_desktop(FakeDesktop())
        payload = server._settings_payload()["desktop"]
        assert payload["running"] and payload["problem"] == "The download stopped before the end: nothing was kept"
    finally:
        await server.stop()


async def test_a_taken_shortcut_is_said_and_another_one_is_taken_instead(fake_claude, tmp_path):  # Review Focus 1
    from ai_browser.desktop.shortcut import label
    from ai_browser.settings import read_settings

    server, url = await started(fake_claude, tmp_path, EVENTS)
    lines = []
    server.out = lines.append
    app = FakeDesktop(answers={"Control+Shift+Space": {"ok": False, "why": "taken"}})
    server.attach_desktop(app)
    try:
        async with ui_socket(server, url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "settings"}))
            await recv(ws)
            app.says({"type": "shortcut", "value": "Alt+Space", "ok": False, "why": "taken", "pressed": False})
            shown = last_settings(await until(ws, lambda message: message["type"] == "settings"))
            assert shown["desktop"]["shortcut"] == {"value": "Alt+Space", "label": label("Alt+Space"),
                                                    "state": "taken"}
            assert lines == [f"{label('Alt+Space')} is used by another app, so it does nothing in AI Browser: pick "
                             "another in Settings"]
            await ws.send(json.dumps({"type": "settings_set", "key": "shortcut", "value": "Alt+Shift+Space",
                                      "request": "shortcut"}))
            shown = last_settings(await until(ws, lambda message: message["type"] == "settings"))
            assert shown["shortcut"] == "Alt+Shift+Space" and shown["desktop"]["shortcut"]["state"] == "ready"
            await ws.send(json.dumps({"type": "settings_set", "key": "shortcut", "value": "Control+Shift+Space",
                                      "request": "shortcut"}))
            error = (await until(ws, lambda message: message["type"] == "error"))[-1]
            assert error == {"type": "error", "request": "shortcut",
                             "text": f"{label('Control+Shift+Space')} is used by another app. Pick another one."}
            await ws.send(json.dumps({"type": "settings_set", "key": "shortcut", "value": "F5", "request": "shortcut"}))
            error = (await until(ws, lambda message: message["type"] == "error"))[-1]
            assert error["text"] == "The shortcut must be one of the offered ones, or Off"
        assert read_settings(server.home)["shortcut"] == "Alt+Shift+Space"  # the one the app could take
        assert app.tried == ["Alt+Shift+Space", "Control+Shift+Space"]  # F5 never reached the app
        assert app.shortcut["value"] == "Alt+Shift+Space"
    finally:
        await server.stop()


async def test_without_the_app_a_picked_shortcut_waits_for_its_next_start(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    try:
        async with ui_socket(server, url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "settings"}))
            await recv(ws)
            await ws.send(json.dumps({"type": "settings_set", "key": "shortcut", "value": None, "request": "shortcut"}))
            shown = last_settings(await until(ws, lambda message: message["type"] == "settings"))
        assert shown["shortcut"] is None and shown["desktop"]["shortcut"]["state"] == "off"
    finally:
        await server.stop()


async def test_the_app_notifies_in_fixed_words(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    app = FakeDesktop()
    server.attach_desktop(app)
    try:
        add_agent(server.agents, "a1")
        server.agents.check_event("a1", {"check": "captcha", "site": "shop.example.com", "target": "T1"})
        server.agents._broadcast({"type": "permission_request", "agent": "a1", "request": "r1", "server": "gmail",
                                  "tool": "mcp__gmail__send", "input": {"body": HOSTILE}})
        assert await settled(lambda: len(notes_of(app)) == 2)
        assert server._brain_out({"type": "notify", "count": 2,
                                  "items": [{"sender": "Maria Lopez", "subject": HOSTILE}]}) is True
        assert [(note["id"], note["title"], note["body"]) for note in notes_of(app)] == [
            ("n1", "A bot check on shop.example.com", "An agent waits for you to solve it."),
            ("n2", "An agent is waiting for you", "It asks to use a tool. Answer in Mission Control."),
            ("n3", "The Brain has 2 new notes", "Open Mission Control to see what needs you.")]
        sent = json.dumps(app.sent)
        assert "Maria" not in sent and "5,000" not in sent and "gmail" not in sent  # no message, no page, no tool
        server.detach_desktop()
        server.agents.check_event("a1", {"check": "captcha", "site": "other.example.com", "target": "T2"})
        await asyncio.sleep(0.3)
        assert len(notes_of(app)) == 3  # without the app nothing else notifies: Mission Control shows the check
        assert server._brain_out({"type": "notify", "count": 1, "items": []}) is False
    finally:
        await server.stop()


async def test_a_click_opens_the_right_place(fake_claude, tmp_path):
    server, url = await started(fake_claude, tmp_path, EVENTS)
    app = FakeDesktop()
    server.attach_desktop(app)
    watched = []

    class Tabs:  # the user's Brave, with no tab listed: Watch brings a tab forward
        def tabs(self):
            return []

        async def watch(self, target):
            watched.append(target)

    server.tabs = Tabs()
    try:
        add_agent(server.agents, "a1")
        add_agent(server.agents, "a2")
        async with ui_socket(server, url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "home"}))
            await recv(ws)
            server.agents.check_event("a1", {"check": "captcha", "site": "shop.example.com", "target": "T1"})
            server.agents._broadcast({"type": "permission_request", "agent": "a2", "request": "r1", "server": "s",
                                      "tool": "t", "input": {}})
            assert await settled(lambda: len(notes_of(app)) == 2)
            app.says({"type": "clicked", "id": "n1"})  # the bot check: the agent's tab, in Brave
            app.says({"type": "clicked", "id": "n2"})  # the tool request: Mission Control, that agent's drawer
            assert (await until(ws, lambda message: message["type"] == "focus"))[-1] == {"type": "focus",
                                                                                         "agent": "a2"}
            assert watched == ["T1"] and app.sent.count({"type": "show"}) == 1
            server._brain_out({"type": "notify", "count": 1, "items": []})
            app.says({"type": "clicked", "id": "n3"})  # the Brain's note: the Brain's inbox
            assert (await until(ws, lambda message: message["type"] == "focus"))[-1] == {"type": "focus",
                                                                                         "brain": True}
            app.says({"type": "clicked", "id": "n1"})  # the same click again: nothing
            app.says({"type": "clicked", "id": "n99"})  # one the engine never sent: nothing
            await asyncio.sleep(0.3)
            assert watched == ["T1"] and app.sent.count({"type": "show"}) == 2
    finally:
        await server.stop()


def test_the_words_never_carry_a_message_or_a_page():
    from ai_browser.desktop.notes import note_for

    assert note_for({"type": "check_request", "agent": "a3", "site": "Shop.Example.com/<b>"}) == {
        "kind": "check", "agent": "a3", "title": "A bot check", "body": "An agent waits for you to solve it."}
    assert note_for({"type": "permission_request", "agent": "nope", "input": {"text": HOSTILE}})["agent"] == ""
    assert note_for({"type": "notify", "count": True})["title"] == "The Brain has a new note"
    assert note_for({"type": "notify", "count": 5000})["title"] == "The Brain has a new note"
    assert note_for({"type": "agent"}) is None and note_for({}) is None


