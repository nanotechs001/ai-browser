"""AI Browser's own app on a real Electron, only when AIB_TEST_ELECTRON names an Electron 44 program (an Electron.app's
Contents/MacOS/Electron, or electron.exe); skipped otherwise. Nobody downloads Electron for these: the user may point
them at one they have. The test starts that Electron itself, unpackaged, on a throwaway profile. Chromium's
--remote-debugging-port goes on the TEST's command line, to look inside. The packaged app refuses that switch (Task 6
checks it). A window shows for a moment. No test here registers a global shortcut, and none touches the user's own AI
Browser, Brave or Chrome."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ELECTRON = os.environ.get("AIB_TEST_ELECTRON", "")
REAL = pytest.mark.skipif(not ELECTRON or not Path(ELECTRON).is_file(),
                          reason="set AIB_TEST_ELECTRON to an Electron 44 program to drive the real app")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def browser_ws(port: int, seconds: float = 30) -> str:
    """The DevTools address of the test's Electron (its --remote-debugging-port), once it answers."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(int(seconds * 10)):
        try:
            with opener.open(f"http://127.0.0.1:{port}/json/version", timeout=1) as answer:
                return json.loads(answer.read().decode("utf-8"))["webSocketDebuggerUrl"]
        except OSError:
            time.sleep(0.1)
    raise AssertionError("the test's Electron never opened its debugging port")


async def page_at(cdp, url: str, seconds: float = 30) -> str:
    for _ in range(int(seconds * 10)):
        infos = (await cdp.send("Target.getTargets"))["targetInfos"]
        found = [info["targetId"] for info in infos if info["type"] == "page" and info["url"] == url]
        if found:
            return found[0]
        await asyncio.sleep(0.1)
    raise AssertionError(f"no page at {url}")


async def started_app(tmp_path, server, url, *switches):
    """The test's Electron on the staged app (with `switches` of the test's own), its start message sent and its hello
    read: (process, port)."""
    from ai_browser.desktop.stage import stage_app

    stage_app(tmp_path / "app")
    port = free_port()
    process = subprocess.Popen([ELECTRON, str(tmp_path / "app"), f"--aib-profile={tmp_path / 'profile'}",
                                f"--remote-debugging-port={port}", *switches], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    start = {"type": "start", "open": f"{url}/open?code={server.new_launch_code()}", "shortcut": None}
    process.stdin.write((json.dumps(start) + "\n").encode("utf-8"))
    process.stdin.flush()
    hello = json.loads(await asyncio.wait_for(asyncio.to_thread(process.stdout.readline), 60))
    assert hello == {"type": "hello", "pid": process.pid}
    return process, port


@REAL
async def test_the_real_app_is_locked_down(fake_claude, tmp_path):  # Review Focus 3
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer
    from ai_browser.cdp import CDP
    from test_home import page_js, until
    from test_tab_menu import connected, frame

    runner, _, _ = fake_claude
    server = AppServer(tmp_path / "home", AgentManager(tmp_path / "home", claude=runner))
    url = await server.start()  # never 8792 (conftest)
    process, cdp = None, None
    try:
        process, port = await started_app(tmp_path, server, url)
        cdp = await CDP.connect(await asyncio.to_thread(browser_ws, port))
        js = await page_js(cdp, await page_at(cdp, url + "/app"))
        assert await until(js, connected("/home"), seconds=30)  # the tab menu, and AI Home's line to the engine
        assert await js("typeof require === 'undefined' && typeof process === 'undefined'")  # no Node.js in pages
        assert await js("JSON.stringify(Object.keys(window.aib))") == '["chat","thisPage"]'  # the bridge: two actions
        assert await js(f"typeof {frame('/home')}.aib") == "undefined"  # framed pages get no bridge at all
        assert await js("window.open('https://example.com/') === null")  # no window opens another
        await js("location.href = 'https://example.com/'; true")  # a website, in the window itself: refused
        await js(f"{frame('/home')}.location.href = 'https://example.com/'; true")  # and in a frame
        await asyncio.sleep(1.5)
        assert await js("location.href") == url + "/app"
        assert await js(f"{frame('/home')}.location.pathname") == "/home"
        ask = "navigator.permissions.query({name: '%s'}).then((answer) => answer.state)"
        assert await js(f"{frame('/home')}.{ask % 'microphone'}") == "granted"  # talking to the Brain
        assert await js(f"{frame('/home')}.{ask % 'camera'}") == "denied"
        assert await js(f"{frame('/home')}.{ask % 'geolocation'}") == "denied"
        process.stdin.write(b'{"type": "quit"}\n')  # the engine stops
        process.stdin.flush()
        assert await asyncio.to_thread(process.wait, 30) == 0
    finally:
        if cdp is not None:
            await cdp.close()
        if process is not None and process.poll() is None:
            process.kill()
        await server.stop()


@REAL
async def test_the_real_app_quits_when_the_engine_goes(fake_claude, tmp_path):  # Review Focus 4
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer

    runner, _, _ = fake_claude
    server = AppServer(tmp_path / "home", AgentManager(tmp_path / "home", claude=runner))
    url = await server.start()
    process = None
    try:
        process, _ = await started_app(tmp_path, server, url)
        process.stdin.close()  # the engine is gone, without a word: its line ends
        assert await asyncio.to_thread(process.wait, 30) == 0  # the app doesn't stay behind in the menu bar
    finally:
        if process is not None and process.poll() is None:
            process.kill()
        await server.stop()


@REAL
def test_the_assembled_app_refuses_a_debugging_port(tmp_path):
    from ai_browser.desktop import assemble, fuses, layout

    binary = Path(ELECTRON)
    root = binary.parents[3] if sys.platform == "darwin" else binary.parent  # the folder Electron's zip unpacks to
    home = tmp_path / "home"
    app = assemble.build(root, home, sys.platform)  # a copy, in a throwaway home; the real codesign and sips on a Mac
    started = subprocess.run([str(layout.executable(app, sys.platform)), f"--remote-debugging-port={free_port()}"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             timeout=30)
    assert started.returncode == 1  # it ended by itself, before any window: the packaged app opens no such port
    holder = layout.framework(app) if sys.platform == "darwin" else layout.executable(app, sys.platform)
    for wire in fuses.states(holder):
        assert wire[0] == wire[2] == wire[3] == "0"


@REAL
async def test_the_real_chat_shows_its_page_only_and_learns_the_tab_only_while_shown(fake_claude, tmp_path):
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer
    from ai_browser.cdp import CDP
    from test_home import page_js, until
    from test_tab_menu import connected

    runner, _, _ = fake_claude
    server = AppServer(tmp_path / "home", AgentManager(tmp_path / "home", claude=runner))
    url = await server.start()
    answer = tmp_path / "page.json"  # what "Brave's front tab" says: a file of the test's, never the user's Brave
    answer.write_text(json.dumps({"state": "ok", "url": "https://shop.example/cart", "title": "Cart"}),
                      encoding="utf-8")
    process, cdp = None, None
    try:
        process, port = await started_app(tmp_path, server, url, f"--aib-fake-page={answer}")
        cdp = await CDP.connect(await asyncio.to_thread(browser_ws, port))
        window = await page_js(cdp, await page_at(cdp, url + "/app"))
        assert await until(window, connected("/home"), seconds=30)
        assert await window("window.aib.thisPage().then((seen) => seen.state)") == "hidden"  # only the chat learns it
        await window("window.aib.chat('show'); true")
        chat = await page_js(cdp, await page_at(cdp, url + "/chat"))
        assert await until(chat, "typeof window.aib === 'object' && document.readyState === 'complete'", seconds=30)
        assert json.loads(await chat("window.aib.thisPage().then((seen) => JSON.stringify(seen))")) == {
            "state": "ok", "url": "https://shop.example/cart", "title": "Cart"}
        assert await chat("typeof require === 'undefined' && typeof process === 'undefined'")  # no Node.js
        await chat("location.href = '/home'; true")  # the chat's window shows its page and nothing else
        assert await chat("window.open('https://example.com/') === null")
        await asyncio.sleep(1.5)
        assert await chat("location.pathname") == "/chat"
        await chat("window.aib.chat('hide'); true")
        assert await until(chat, "document.visibilityState === 'hidden'", seconds=10)
        assert await chat("window.aib.thisPage().then((seen) => seen.state)") == "hidden"  # hidden: never read
        process.stdin.write(b'{"type": "quit"}\n')
        process.stdin.flush()
        assert await asyncio.to_thread(process.wait, 30) == 0
    finally:
        if cdp is not None:
            await cdp.close()
        if process is not None and process.poll() is None:
            process.kill()
        await server.stop()
