"""Where the AI's tabs go in the user's Brave (the Placer: through the app, or a window of their own), and an engine's
link to ai-browser app."""

import asyncio
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


class App:
    """A small stand-in for the app's routes: it records each request and answers from `answers` (path -> JSON)."""

    def __init__(self, answers=None):
        self.requests, self.answers = [], answers or {}
        app = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _answer(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length)) if length else None
                app.requests.append((self.command, self.path, body, self.headers.get("X-AIB-Agent-Token")))
                answer = app.answers.get(self.path.split("?")[0])
                data = b"" if answer is None else json.dumps(answer).encode("utf-8")
                self.send_response(204 if answer is None else 200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = _answer

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class FakeLink:
    """AgentLink's surface for the Placer: open_tab answers what a test sets."""

    def __init__(self, answer=None):
        self.answer, self.opened, self.hellos = answer if answer is not None else {"target": "N1"}, 0, 0
        self.url, self.token, self.agent = "http://127.0.0.1:1/agent-events", "t", "a1"

    async def open_tab(self):
        self.opened += 1
        return self.answer

    async def hello(self):
        self.hellos += 1


class FakeCDP:
    def __init__(self):
        self.sent = []

    async def send(self, method, params=None, **kwargs):
        self.sent.append((method, params))
        return {"targetId": "W1"}


async def test_open_tab_asks_the_app_for_the_agent_and_waits_longer():
    from ai_browser.agentlink import TAB_WAIT, AgentLink

    app = App({"/agent-tab": {"target": "N7"}})
    try:
        link = AgentLink(app.url + "/agent-events", "tok", "a3")
        assert link.base == app.url and TAB_WAIT > 2
        assert await link.open_tab() == {"target": "N7"}
        assert app.requests == [("POST", "/agent-tab", {"agent": "a3"}, "tok")]
    finally:
        app.stop()


async def test_with_no_app_open_tab_and_status_say_nothing():
    from ai_browser.agentlink import AgentLink

    app = App()
    url = app.url
    app.stop()
    link = AgentLink(url + "/agent-events", "tok", "a3")
    assert await link.open_tab() is None
    assert await link.status() == {"handed": []}


async def test_status_is_cached():
    handed = [{"target": "U1", "title": "Shop", "url": "https://s.com/"}]
    app = App({"/agent-status": {"handed": handed}})
    try:
        from ai_browser.agentlink import AgentLink

        link = AgentLink(app.url + "/agent-events", "tok", "a3")
        assert await link.status() == await link.status() == {"handed": handed}
        assert [path for _, path, _, _ in app.requests] == ["/agent-status?agent=a3"]
        await asyncio.sleep(1.1)
        await link.status()
        assert len(app.requests) == 2  # the handed tabs are at most a second old
        app.answers.clear()  # the app answers nothing for a moment: the last answer stands
        await asyncio.sleep(1.1)
        assert (await link.status())["handed"] == handed
    finally:
        app.stop()


async def test_status_reads_handed_ttl_when_called(monkeypatch):
    """The handed tabs' cache length is read at each call, so a longer one set later takes effect (tests rely on it
    to show that only the relay's cut tells an engine about Take back)."""
    import ai_browser.agentlink as agentlink

    app = App({"/agent-status": {"handed": []}})
    try:
        monkeypatch.setattr(agentlink, "HANDED_TTL", 60)
        link = agentlink.AgentLink(app.url + "/agent-events", "tok", "a3")
        await link.status()
        await asyncio.sleep(1.1)
        await link.status()
        assert len(app.requests) == 1  # the 60 s cache still serves
    finally:
        app.stop()


def test_discover_needs_a_link_file_a_live_app_and_this_computer(tmp_path):
    from ai_browser.agentlink import AgentLink

    assert AgentLink.discover(tmp_path, "t1") is None  # no app running
    (tmp_path / "app").mkdir()
    link_file = tmp_path / "app" / "link.json"
    dead = int(subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True,
                              text=True, encoding="utf-8").stdout)
    events = "http://127.0.0.1:8792/agent-events"
    link_file.write_text(json.dumps({"events": events, "session_token": "s", "pid": dead}), encoding="utf-8")
    assert AgentLink.discover(tmp_path, "t1") is None  # the app's process is gone
    link_file.write_text(json.dumps({"events": events, "session_token": "s", "pid": os.getpid()}), encoding="utf-8")
    found = AgentLink.discover(tmp_path, "20261002-120000-ab12")
    assert (found.url, found.token, found.agent) == (events, "s", "cc-20261002-120000-ab12")
    for elsewhere in ("https://evil.example/agent-events", "http://127.0.0.1:80@evil.example/agent-events",
                      "http://127.0.0.1.evil.example:8792/agent-events", "http://127.0.0.1:8792/other"):
        link_file.write_text(json.dumps({"events": elsewhere, "session_token": "s", "pid": os.getpid()}),
                             encoding="utf-8")
        assert AgentLink.discover(tmp_path, "t1") is None, elsewhere  # only ever the app on this computer


async def test_with_the_app_a_new_tab_is_the_apps_to_open():
    from ai_browser.grouping import Placer

    cdp, link = FakeCDP(), FakeLink({"target": "N1"})
    assert await Placer(link).open_tab(cdp) == "N1" and link.opened == 1
    assert cdp.sent == []  # the engine never makes the tab itself: the app places it


async def test_the_apps_words_reach_the_agent_and_silence_is_said_too():
    from ai_browser.grouping import NO_ANSWER, PlaceError, Placer

    words = "Brave's last window is in another profile: click a window of the profile where agents browse"
    for answer, said in (({"error": words}, words), ({}, NO_ANSWER), (None, NO_ANSWER)):
        link = FakeLink(answer)
        link.answer = answer
        with pytest.raises(PlaceError) as refused:
            await Placer(link).open_tab(FakeCDP())
        assert str(refused.value) == said


async def test_without_the_app_each_tab_gets_a_window_of_its_own():
    from ai_browser.grouping import Placer

    cdp = FakeCDP()
    assert await Placer(None).open_tab(cdp) == "W1"
    assert cdp.sent == [("Target.createTarget", {"url": "about:blank", "newWindow": True, "background": True})]


async def test_a_session_reads_link_json_again_when_the_app_comes_and_goes(monkeypatch):
    from ai_browser import grouping

    monkeypatch.setattr(grouping, "REREAD_EVERY", 0)
    joined = FakeLink({"target": "N1"})
    found = [joined, None]
    placer = grouping.Placer(None, rediscover=lambda: found.pop(0))
    assert await placer.open_tab(FakeCDP()) == "N1" and placer.link is joined and joined.hellos == 1
    assert await placer.open_tab(FakeCDP()) == "W1" and placer.link is None  # link.json gone: a window of its own


def test_discover_reads_a_local_cdp_only(tmp_path):
    from ai_browser.agentlink import AgentLink

    (tmp_path / "app").mkdir()
    link_file = tmp_path / "app" / "link.json"
    base = {"events": "http://127.0.0.1:8792/agent-events", "session_token": "s", "pid": os.getpid(),
            "browser_dir": "/x/BraveSoftware/Brave-Browser"}
    link_file.write_text(json.dumps({**base, "cdp": "ws://127.0.0.1:8792/cdp"}), encoding="utf-8")
    found = AgentLink.discover(tmp_path, "t1")
    assert (found.cdp, found.browser_dir, found.pid) == ("ws://127.0.0.1:8792/cdp",
                                                        Path("/x/BraveSoftware/Brave-Browser"), os.getpid())
    for bad in ("ws://127.0.0.1:80@evil/cdp", "wss://127.0.0.1:1/cdp", "ws://localhost:1/cdp",
                "ws://127.0.0.1:1/other", "ws://127.0.0.1:1/cdp?x=1", "ws://127.0.0.1/cdp", 7):
        link_file.write_text(json.dumps({**base, "cdp": bad}), encoding="utf-8")
        found = AgentLink.discover(tmp_path, "t1")
        assert found is not None and found.cdp is None, bad  # ignored: never a connection anywhere else
