"""`ai-browser app`: the agents, the app server and AI Browser together, until the user is done.

The first start, before the extension is in AI Browser's profile, opens chrome://extensions and the setup page with
the four steps; from then on AI Browser opens on AI Home. The app ends when AI Browser quits, when its last window
closes (on macOS Chrome itself keeps running then), or on Ctrl-C, which quits AI Browser too."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import os
from collections.abc import Callable, Sequence
from pathlib import Path

from .. import platforms
from ..appbrowser import (AppBrowserError, app_profile, extension_id_for, extension_installed, extension_path,
                          launch_app_browser, prepare_extension)
from ..brain.service import BrainService
from ..brain.skillwriter import SkillWriter
from ..brain.store import BrainStore
from ..brain.tools import ToolsConfig
from ..brain.watcher import prepare_watcher
from ..brain.workflows import WorkflowRunner, WorkflowStore
from ..cdp import CDP, CDPError
from ..chrome import inspect_address, own_browser_dir
from ..hearing.engine import WhisperEngine
from ..hearing.model import ModelStore
from ..hearing.service import HearingService
from ..syncdir import write_atomic
from .agents import AgentManager
from .bravelink import BraveLink
from .server import AppServer, reveal_in_finder
from .tabs import TabWatch

WINDOW_CHECKS = 3  # one second apart: this long without any page means the user closed AI Browser's last window
TICK = 30  # seconds between two looks at the scheduled workflows
EXTENSION_WAIT = 6  # seconds for an installed extension to connect; a record Chrome no longer loads never does
READY = ("AI Browser is open: AI Home is the first tab (every agent, tab and skill). Click the AI Browser icon or "
         "press ⌘⇧Y to chat beside any page, or type ai and a space in the address bar.\nPress Ctrl-C here to close it.")
SETUP = """AI Browser needs its extension, once (a Finder window shows its folder):
  1. In the chrome://extensions tab, turn on Developer mode (top right).
  2. Drag the "extension" folder from Finder onto that page.
     (Or click Load unpacked, press ⌘⇧G, paste {folder} and press Enter.)
  3. Pin the AI Browser icon from the puzzle-piece menu.
Already listed there but switched off? Switch it on. If Chrome asks about the new tab page, choose Keep it.
The setup tab says "All set" when it's done. Press Ctrl-C here to close AI Browser."""
BRAVE = """The Brain watches your messages (Gmail, Slack, Asana…) in Brave, through a small extension. Once:
  1. In Brave, open brave://extensions and turn on Developer mode (top right).
  2. Drag the "watcher" folder onto that page.
     (Or click Load unpacked, press ⌘⇧G, paste {folder} and press Enter.)
  3. Click the watcher's icon to open the Brain, and switch on the sites to watch.
It reads new messages in tabs you have open and never sends anything."""
BROWSERS = ("brave", "app")
SWITCH = """Agents browse in your {name}, but its remote-debugging switch is off, so nothing reaches it yet. Once:
  1. In {name}, open {inspect}.
  2. Tick "Allow remote debugging for this browser instance".
  3. When {name} asks "Allow remote debugging?", click Allow. {name} may ask when AI Browser starts and again when
     each agent first uses the browser, and it asks again after it restarts.
While this switch is on, any program on this computer can reach your {name}, not only AI Browser. That includes the
sites you are signed in to. Turn it off when agents aren't working: untick the same box. Only click Allow right after
you started AI Browser or gave an agent a task; if {name} asks at any other time, click Deny.
Once the switch is on, AI Home's browser card has a Connect button."""
reveal = reveal_in_finder  # a Finder window with the extension folder selected (tests replace it)


def _max_agents() -> int:
    try:
        return min(10, max(1, int(os.environ.get("AIB_APP_MAX_AGENTS", "3"))))
    except ValueError:
        return 3


def app_browser(choice: str | None = None) -> str:
    """Where agents browse: --browser, else $AIB_APP_BROWSER, else the user's Brave when its folder exists."""
    value = (choice or os.environ.get("AIB_APP_BROWSER") or "").strip().lower()
    if not value:
        return "brave" if own_browser_dir().is_dir() else "app"
    if value not in BROWSERS:
        raise ValueError(f"--browser must be brave or app, not {value!r}")
    return value


def brave_env(folder: Path) -> dict[str, str]:
    """Every agent's engine drives the user's own browser (this overrides the bridge's AIB_BROWSER=app)."""
    return {"AIB_BROWSER": "chrome", "AIB_CHROME_DIR": str(folder)}


def write_link(home: Path, url: str, token: str) -> Path:
    """<home>/app/link.json (mode 0600): how Claude Code sessions in the user's Brave find this app."""
    path = Path(home) / "app" / "link.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps({"events": f"{url}/agent-events", "session_token": token, "pid": os.getpid()}).encode("utf-8")
    write_atomic(path, data, 0o600)  # holds the session token
    return path


async def run_app(home: Path, model: str = "sonnet", headless: bool = False,
                  claude: str | Sequence[str] | None = None, ready: Callable | None = None,
                  stop: asyncio.Event | None = None, out: Callable[[str], None] = print,
                  pipe_install: bool | None = None, browser: str | None = None) -> int:
    """0 once AI Browser is closed (or `stop` is set); 1 with a message when it can't start."""
    home = Path(home)
    try:
        where = app_browser(browser)
    except ValueError as exc:
        out(f"error: {exc}")
        return 1
    lock = _lock(home)  # before anything is touched: a second run must not disturb the first one's pages
    if lock is None:
        out(f"error: AI Browser is already running (another `ai-browser app` uses {home}): use that one, or stop it "
            "first")
        return 1
    try:
        return await _run(home, model, headless, claude, ready, stop, out, pipe_install, where)
    finally:
        lock.close()


def _setup_pages(url: str) -> list[str]:
    """The one-time setup: its steps, and the page they happen on."""
    return [f"{url}/setup", "chrome://extensions/"]


async def _connected(server: AppServer, seconds: float) -> bool:
    for _ in range(int(seconds * 10)):
        if server.extension_seen:
            return True
        await asyncio.sleep(0.1)
    return server.extension_seen


async def _open(ws_url: str, urls: list[str]) -> None:
    cdp = await CDP.connect(ws_url)
    try:
        for page in urls:
            with contextlib.suppress(CDPError):
                await cdp.send("Target.createTarget", {"url": page})
    finally:
        await cdp.close()


async def _tick(runner: WorkflowRunner) -> None:
    while True:
        await asyncio.sleep(TICK)
        with contextlib.suppress(Exception):  # one workflow that can't start must not stop the others' schedules
            await runner.tick()


def _lock(home: Path):
    """An exclusive lock on <home>/app/lock held for the whole run, or None if another run holds it."""
    folder = home / "app"
    folder.mkdir(parents=True, exist_ok=True)
    return platforms.lock_file(folder / "lock")


async def _run(home: Path, model: str, headless: bool, claude: str | Sequence[str] | None, ready: Callable | None,
               stop: asyncio.Event | None, out: Callable[[str], None], pipe_install: bool | None,
               where: str) -> int:
    agents = AgentManager(home, claude=claude, max_working=_max_agents())
    brain = BrainService(BrainStore(home), agents, claude=claude, agent_model=model)
    workflows = WorkflowStore(home)
    runner = WorkflowRunner(workflows, agents)
    skills = SkillWriter(Path.home() / ".claude" / "skills", claude=claude, cwd=home / "brain" / "calls")
    hearing = HearingService(ModelStore(home / "models"), WhisperEngine())  # talking; the model only on Download
    server = AppServer(home, agents, default_model=model, brain=brain, tools=ToolsConfig(home), workflows=workflows,
                       runner=runner, skill_writer=skills, hearing=hearing)
    server.out = out
    app = watch = ticker = brave = link_file = None
    try:
        try:
            url = await server.start()
            folder = prepare_extension(home, url, server.token)
            watcher, server.watcher_build = prepare_watcher(home, url, server.token)  # Brave's watcher, updated
            server.watcher_folder = extension_path(watcher)
            pipe = headless if pipe_install is None else pipe_install
            # Installed (over the pipe now, or by the user before): the extension's worker opens AI Home itself.
            installed = pipe or extension_installed(app_profile(home), folder)
            urls = [] if installed else _setup_pages(url)
            app = await asyncio.to_thread(launch_app_browser, app_profile(home), folder, headless, pipe, urls)
        except (AppBrowserError, RuntimeError) as exc:
            out(f"error: {exc}")
            return 1
        server.allow_origin(f"chrome-extension://{app.extension_id}")
        server.allow_origin(f"chrome-extension://{extension_id_for(watcher)}", watcher=True)
        agents.env.update({"AIB_APP_PROFILE": str(app.profile), "AIB_APP_EXTENSION": app.extension_id,
                           "AIB_APP_EVENTS": f"{url}/agent-events", "AIB_APP_AGENT_TOKEN": server.agent_token})
        if where == "brave":  # agents browse in the user's own Brave; AI Browser is the control room
            own = own_browser_dir()  # not `folder`: that is the extension's, which the setup steps name
            brave = BraveLink(own)
            agents.env.update(brave_env(own))
            server.attach_brave(brave)
            agents.close_tabs = brave.close_targets
            link_file = write_link(home, url, server.session_token)
            await brave.start()  # looks at the switch; it never connects by itself
        watch = TabWatch(app.ws_url, app.extension_id)  # AI Browser's own tabs: its last window closing ends the app
        await watch.start()
        if brave is None:
            server.attach_tabs(watch)
            agents.close_tabs = watch.close_targets
        if installed and not pipe and not await _connected(server, EXTENSION_WAIT):
            # The profile remembers the extension, but Chrome didn't load it (a one-run install by an older
            # ai-browser leaves such a record): the setup steps after all.
            installed = False
            await _open(app.ws_url, _setup_pages(url))
        if not installed:
            reveal(extension_path(folder))
        out(READY if installed else SETUP.format(folder=extension_path(folder)))
        if brave is not None:
            if brave.state == "off":
                out(SWITCH.format(name=brave.name, inspect=inspect_address(brave.folder)))
            else:
                server.connect_brave()  # once, as the app starts: Brave asks "Allow remote debugging?"
        if not brain.store.watcher_seen:  # the Brain's watcher isn't in Brave yet: its steps, until it is
            out(BRAVE.format(folder=server.watcher_folder))
            if installed and not brain.store.watcher_prompted:  # one Finder window at a time, and only once
                brain.store.set_watcher_prompted()
                reveal(server.watcher_folder)
                await _open(app.ws_url, [f"{url}/setup#brave"])
        ticker = asyncio.create_task(_tick(runner))  # scheduled workflows run while the app does
        if ready is not None:
            result = ready(url, app)
            if inspect.isawaitable(result):
                await result
        stop = stop or asyncio.Event()
        windowless = 0
        while not stop.is_set() and not app.closed:
            try:
                await asyncio.wait_for(stop.wait(), 1)
            except TimeoutError:
                pass
            # On macOS Chrome keeps running after its last window closes: that, too, means the user is done.
            windowless = 0 if watch.has_pages() else windowless + 1
            if windowless >= WINDOW_CHECKS:
                break
        return 0
    finally:
        if ticker is not None:
            ticker.cancel()
        if link_file is not None:
            with contextlib.suppress(OSError):
                platforms.unlink(link_file, missing_ok=True)
        if brave is not None:
            await brave.close()  # the agents' tabs and groups stay in Brave: nothing they left for the user is lost
        await server.stop()  # every agent's Claude Code process ends too
        if watch is not None:
            await watch.close()
        if app is not None:
            await asyncio.to_thread(app.close)
