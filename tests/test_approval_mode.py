"""One "Allow remote debugging?" per app run, counted in a real browser's approval mode.

A throwaway headless browser (Chrome, and Brave when it is installed) with its own temporary profile runs in approval
mode, the mode the brave://inspect switch turns on: its Local State says devtools.remote_debugging.user-enabled. In that
mode the browser asks "Allow remote debugging?" for every WebSocket to /devtools/browser/* and remembers nothing
(Chromium's devtools_http_handler.cc: OnWebSocketRequest calls AcceptDebugging), and it shows its automation bar again
whenever its count of accepted connections changes while above zero (SetActiveWebSocketConnections). So one connection
for the whole run means one question and one bar.

Nobody clicks Allow here: nothing in this project ever answers that question. A small proxy in front of the browser's
port counts the questions as the browser receives them, while the app, two agents and a Claude Code session all want the
browser at once."""

import asyncio
import contextlib
import json
import subprocess
from pathlib import Path

import pytest

from ai_browser.cdp import CDP
from ai_browser.chrome import _same_folder, brave_binary, chrome_binary, own_browser_dirs
from ai_browser.engine import Engine
from ai_browser.skills import Catalog
from fake_brave import add_agent, until

BROWSERS = [pytest.param(binary, id=name) for name, binary in (("chrome", chrome_binary()), ("brave", brave_binary()))
            if binary]
QUESTION = b"GET /devtools/browser/"


class QuestionCounter:
    """A TCP proxy in front of the browser's debugging port. Each WebSocket upgrade to /devtools/browser/ that passes
    through is a question the browser asks; a bare TCP look (the switch check) asks nothing."""

    def __init__(self, upstream_port: int):
        self.upstream_port, self.questions, self.server = upstream_port, 0, None

    async def start(self) -> int:
        self.server = await asyncio.start_server(self._client, "127.0.0.1", 0)
        return self.server.sockets[0].getsockname()[1]

    async def _client(self, reader, writer):
        try:
            first = await reader.read(65536)
            if not first:
                return  # a look at the switch: connected and closed, nothing asked
            if first.startswith(QUESTION):
                self.questions += 1
            up_reader, up_writer = await asyncio.open_connection("127.0.0.1", self.upstream_port)
            up_writer.write(first)
            await up_writer.drain()
            await asyncio.gather(self._pipe(reader, up_writer), self._pipe(up_reader, writer))
        except (OSError, asyncio.CancelledError):
            pass
        finally:
            writer.close()

    @staticmethod
    async def _pipe(reader, writer):
        try:
            while data := await reader.read(65536):
                writer.write(data)
                await writer.drain()
        except OSError:
            pass
        finally:
            writer.close()

    def stop(self):
        self.server.close()


def approval_mode_browser(binary: str, folder: Path) -> subprocess.Popen:
    """A throwaway browser in approval mode: a profile folder of its own, the switch on in its Local State, headless.
    Never one of the user's own profile folders."""
    assert not any(_same_folder(folder, real) for real in own_browser_dirs())
    folder.mkdir(parents=True)
    (folder / "Local State").write_text(json.dumps({"devtools": {"remote_debugging": {"user-enabled": True}}}),
                                        encoding="utf-8")
    return subprocess.Popen([binary, f"--user-data-dir={folder}", "--headless=new", "--no-first-run",
                             "--no-default-browser-check", "--disable-search-engine-choice-screen", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def active_port(folder: Path) -> tuple[int, str]:
    """(port, path) from the browser's DevToolsActivePort, once its approval-mode server is up."""
    for _ in range(200):
        with contextlib.suppress(OSError, ValueError, IndexError):
            lines = (folder / "DevToolsActivePort").read_text(encoding="utf-8").splitlines()
            return int(lines[0]), lines[1]
        await asyncio.sleep(0.1)
    raise AssertionError("the browser started no debugging server in approval mode")


async def app_on(front: Path, home: Path, allow_wait: float):
    """The app in brave mode on `front` (the user's browser as the app sees it), with link.json written."""
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.bravelink import BraveLink
    from ai_browser.app.run import write_link
    from ai_browser.app.server import AppServer

    agents = AgentManager(home)
    server = AppServer(home, agents)
    url = await server.start()
    brave = BraveLink(front, allow_wait=allow_wait, every=0.2, tokens=server.tokens)
    server.attach_brave(brave)
    await brave.start()
    write_link(home, url, server.session_token, url.replace("http://", "ws://", 1) + "/cdp", front)
    return server, brave


def agent_engine(server, front: Path, tmp_path: Path, monkeypatch, agent: str) -> Engine:
    """An agent's engine as ai-browser app sets it up: through the relay, with its own token."""
    monkeypatch.setenv("AIB_BROWSER", "chrome")
    monkeypatch.setenv("AIB_CHROME_DIR", str(front))
    monkeypatch.setenv("AIB_APP_AGENT", agent)
    monkeypatch.setenv("AIB_APP_EVENTS", server.url + "/agent-events")
    monkeypatch.setenv("AIB_APP_AGENT_TOKEN", server.token_for(agent))
    monkeypatch.setenv("AIB_APP_CDP", server.url.replace("http://", "ws://", 1) + "/cdp")
    return Engine(home=tmp_path / f"engine-{agent}", catalog=Catalog([], set()))


@pytest.mark.parametrize("binary", BROWSERS)
async def test_one_question_for_the_app_two_agents_and_a_session(binary, tmp_path, monkeypatch):
    process = approval_mode_browser(binary, tmp_path / "browser")
    counter = server = brave = starting = again = None
    engines = []
    try:
        port, path = await active_port(tmp_path / "browser")
        counter = QuestionCounter(port)
        front_port = await counter.start()
        front = tmp_path / "BraveSoftware" / "Brave-Browser"  # the app's view of the user's Brave: the proxy
        front.mkdir(parents=True)
        (front / "DevToolsActivePort").write_text(f"{front_port}\n{path}\n", encoding="utf-8")
        server, brave = await app_on(front, tmp_path / "home", allow_wait=8)
        assert brave.state == "ready" and counter.questions == 0  # looking at the switch asks nothing
        starting = asyncio.ensure_future(brave.connect("start"))  # the app starts: the browser asks
        assert await until(lambda: brave.state == "asking", 10)
        calls = []
        for agent in ("a1", "a2"):
            add_agent(server.agents, agent)
            engine = agent_engine(server, front, tmp_path, monkeypatch, agent)
            engines.append(engine)
            calls.append(asyncio.ensure_future(engine.tabs("list")))
            await asyncio.sleep(0.5)  # it read its environment before the next agent's is set
        for name in ("AIB_APP_AGENT", "AIB_APP_EVENTS", "AIB_APP_AGENT_TOKEN", "AIB_APP_CDP"):
            monkeypatch.delenv(name)
        session = Engine(home=tmp_path / "home", catalog=Catalog([], set()))  # a Claude Code session: link.json
        engines.append(session)
        calls.append(asyncio.ensure_future(session.tabs("list")))
        await asyncio.sleep(1.5)
        assert counter.questions == 1  # the app, two agents and a session: one question, shared

        texts = [result.text for result in await asyncio.gather(*calls)]  # nobody clicks Allow
        assert brave.state == "asking" and not starting.done()  # the question stays until the user answers it
        assert all('is asking "Allow remote debugging?"' in text for text in texts), texts
        again = asyncio.ensure_future(brave.connect("connect"))  # Connect pressed again: the same question
        await asyncio.sleep(2)
        assert counter.questions == 1 and not again.done()  # nothing asks again, by itself or on Connect

        for _ in range(2):  # the contrast: connections of their own (as engines made before) ask once each
            with pytest.raises(Exception):
                await CDP.connect(f"ws://127.0.0.1:{front_port}{path}", open_timeout=1)
        assert counter.questions == 3
    finally:
        for engine in engines:
            with contextlib.suppress(Exception):
                await engine.close()
        if server is not None:
            await server.stop()
        if brave is not None:
            await brave.close()  # ends the question's handshake: the waiting connects return
        await asyncio.gather(*[task for task in (starting, again) if task is not None], return_exceptions=True)
        if counter is not None:
            counter.stop()
        process.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=15)
