"""Where the AI's tabs go in the user's Brave (the marker and the Placer), and an engine's link to ai-browser app."""

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


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
    def __init__(self, groups=True, claim_wait=0.0):
        self.groups, self.claim_wait, self.claims, self.reports, self.hellos = groups, claim_wait, [], [], 0
        self.url, self.token, self.agent = "http://127.0.0.1:1/agent-events", "t", "a1"

    async def status(self, max_age=1.0):
        return {"groups": self.groups, "handed": []}

    async def claim(self, target, marker=None, opener=None, url=""):
        self.claims.append((target, marker))
        await asyncio.sleep(self.claim_wait)
        return {"grouped": True, "tab": 1}

    async def hello(self):
        self.hellos += 1

    def report(self, kind, target, adopted=False, **extra):
        self.reports.append((kind, target, adopted, extra))


def test_markers_are_secret_and_random():
    from ai_browser.grouping import MARKER, marker_url, new_marker

    markers = {new_marker() for _ in range(50)}
    assert len(markers) == 50 and all(MARKER.match(marker) for marker in markers)
    assert marker_url("0123456789abcdef") == "about:blank#aib-0123456789abcdef"


async def test_claim_sends_the_agent_the_target_and_the_marker():
    from ai_browser.agentlink import AgentLink

    app = App({"/agent-claim": {"grouped": True, "tab": 412}})
    try:
        link = AgentLink(app.url + "/agent-events", "tok", "a3")
        assert link.base == app.url
        assert await link.claim("T1", marker="0123456789abcdef") == {"grouped": True, "tab": 412}
        assert app.requests == [("POST", "/agent-claim", {"agent": "a3", "target": "T1",
                                                          "marker": "0123456789abcdef"}, "tok")]
    finally:
        app.stop()


async def test_a_claim_with_no_app_says_so():
    from ai_browser.agentlink import AgentLink

    app = App()
    url = app.url
    app.stop()
    link = AgentLink(url + "/agent-events", "tok", "a3")
    assert await link.claim("T1", marker="0123456789abcdef") == {"grouped": False, "reason": "no_app"}
    assert await link.status() == {"groups": False, "handed": []}


async def test_status_is_cached():
    from ai_browser.agentlink import GROUPS_TTL, AgentLink

    handed = [{"target": "U1", "title": "Shop", "url": "https://s.com/"}]
    app = App({"/agent-status": {"groups": True, "handed": handed}})
    try:
        link = AgentLink(app.url + "/agent-events", "tok", "a3")
        assert await link.status() == await link.status() == {"groups": True, "handed": handed}
        assert [path for _, path, _, _ in app.requests] == ["/agent-status?agent=a3"]
        await asyncio.sleep(1.1)
        await link.status(GROUPS_TTL)
        assert len(app.requests) == 1  # whether groups are on may be ten seconds old...
        await link.status()
        assert len(app.requests) == 2  # ...the handed tabs at most one
        app.answers.clear()  # the app answers nothing for a moment: the last answer stands
        await asyncio.sleep(1.1)
        assert (await link.status())["handed"] == handed
    finally:
        app.stop()


def test_discover_needs_a_link_file_a_live_app_and_this_computer(tmp_path):
    from ai_browser.agentlink import AgentLink

    assert AgentLink.discover(tmp_path, "t1") is None  # no app running
    (tmp_path / "app").mkdir()
    link_file = tmp_path / "app" / "link.json"
    dead = int(subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True,
                              text=True).stdout)
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


async def test_with_groups_a_new_tab_carries_a_marker():
    from ai_browser.grouping import MARKER_PREFIX, Placer

    params, marker = await Placer(FakeLink()).create_params()
    assert params == {"url": MARKER_PREFIX + marker, "background": True}  # no newWindow, no browserContextId


async def test_without_the_app_or_its_groups_each_tab_gets_a_window():
    from ai_browser.grouping import Placer

    for placer in (Placer(None), Placer(FakeLink(groups=False))):
        assert await placer.create_params() == ({"url": "about:blank", "newWindow": True, "background": True}, None)


async def test_placed_waits_at_most_claim_wait_and_never_raises():
    from ai_browser.grouping import CLAIM_WAIT, Placer

    link = FakeLink(claim_wait=10)  # the app never answers
    started = time.monotonic()
    await Placer(link).placed("T1", "0123456789abcdef")
    assert time.monotonic() - started < CLAIM_WAIT + 0.3 and link.claims == [("T1", "0123456789abcdef")]
    await Placer(link).placed("T2", None)  # a tab in its own window: nothing to claim
    assert len(link.claims) == 1


def test_a_page_opened_tab_is_reported_with_its_opener():
    from ai_browser.grouping import Placer

    link = FakeLink()
    Placer(link).popup("T2", "T1", "https://s.com/next")
    assert link.reports == [("tab_opened", "T2", False, {"opener": "T1", "url": "https://s.com/next"})]


async def test_a_session_reads_link_json_again_when_the_app_comes_and_goes(monkeypatch):
    from ai_browser import grouping

    monkeypatch.setattr(grouping, "REREAD_EVERY", 0)
    joined = FakeLink()
    found = [joined, None]
    placer = grouping.Placer(None, rediscover=lambda: found.pop(0))
    assert (await placer.create_params())[1] is not None and placer.link is joined and joined.hellos == 1
    assert (await placer.create_params())[1] is None and placer.link is None  # link.json gone: a window of its own
