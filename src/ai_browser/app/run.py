"""`ai-browser app`: the agents, the app server and AI Browser's window together, until the user is done.

AI Browser's own app (desktop/) opens when it is set up: closing its window hides it, and its Quit ends the run. Until
it is set up (and with --window), a browser window draws AI Browser instead: an installed browser in --app mode on a
profile of the app's own, with no debugging port (app/window.py). It opens on a one-time code the server swaps for the
window's cookie. The app ends when the last of its windows has been closed for a few seconds (on macOS the browser
keeps running with no window, so the windows' sockets tell), or on Ctrl-C, which closes the window too. Agents browse
in the user's own browser through the app's one connection (the relay)."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import os
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from .. import platforms
from ..accounts import DEFAULT, Accounts
from ..brain.account import BrainAccount
from ..brain.service import BrainService
from ..brain.skillwriter import SkillWriter
from ..brain.store import BrainStore
from ..brain.tools import ToolsConfig
from ..brain.workflows import WorkflowRunner, WorkflowStore
from ..chrome import inspect_address, own_browser_dir
from ..desktop import layout
from ..desktop.assemble import stale
from ..desktop.launch import default_desktop
from ..desktop.release import SETUP_COMMAND, asset_for
from ..hearing.engine import WhisperEngine
from ..hearing.model import ModelStore
from ..hearing.service import HearingService
from ..syncdir import write_atomic
from .agents import AgentManager
from .bravelink import BraveLink
from .server import AppServer
from .window import WINDOW_CHOICES, WindowError, choices, default_launcher

TICK = 30  # seconds between two looks at the scheduled workflows
WINDOW_START_WAIT = 60  # seconds for the window's page to connect once its browser has started
WINDOW_GRACE = 5  # seconds with no AI Browser window before the app ends: a reload or a page change is back sooner
POLL = 0.25  # seconds between two looks at the windows' sockets (time.monotonic stands still while the Mac sleeps)
NO_WINDOW = ("AI Browser's window didn't open: {name} started, but the page never connected. Try again, or pick "
             "another browser with `ai-browser app --window brave`")
RETIRED_APP = ("AI Browser's own Chrome is gone: agents browse in your browser (Brave or Chrome). Drop --browser app "
               "(and AIB_APP_BROWSER).")
APP_ENDED = "AI Browser's app closed by itself, so AI Browser stops too."
NO_APP_PAGE = ("AI Browser's app started, but its page never connected. Try again, or use a browser window: "
               "`uv run ai-browser app --window chrome`")
UPDATING = "Updating AI Browser's app for this version (nothing is downloaded)…"


def ready_text(system: str | None = None) -> str:
    return ("AI Browser is open in its own window: AI Home shows every agent, tab and skill.\n"
            "Close the window, or press Ctrl-C here, to stop.")


def app_text(system: str | None = None) -> str:
    """What the terminal says once AI Browser's own app is open."""
    where = platforms.shortcut("in the menu bar", "by the clock", system)
    stop = platforms.shortcut("press ⌘Q or choose Quit from its menu-bar icon", "choose Quit from its icon there",
                              system)
    return ("AI Browser is open as its own app: AI Home shows every agent, tab and skill.\n"
            f"Closing its window keeps it running {where}. To stop it, {stop}, or press Ctrl-C here.")


def setup_hint(home, system: str | None = None, machine: str | None = None) -> str:
    """The browser window's extra line, on a computer AI Browser's own app runs on, while it isn't set up."""
    if asset_for(system, machine) is None or layout.installed(home, system) is not None:
        return ""
    return f"\nAI Browser can run as its own app, with a shortcut and notifications: run `{SETUP_COMMAND}` once."


BROWSERS = ("brave",)
SWITCH = """Agents browse in your {name}, but its remote-debugging switch is off, so nothing reaches it yet. Once:
  1. In {name}, open {inspect}.
  2. Tick "Allow remote debugging for this browser instance".
  3. When {name} asks "Allow remote debugging?", click Allow. AI Browser holds one connection for all its agents
     and Claude Code sessions, so {name} asks once each time AI Browser starts, and again after {name} restarts.
While this switch is on, any program on this computer can reach your {name}, not only AI Browser. That includes the
sites you are signed in to. While AI Browser is connected, a program that can read AI Browser's files can also use
your {name} through it without a new question; AI Home lists everything connected, with Disconnect. Turn the switch
off when agents aren't working: untick the same box. Only click Allow right after you started AI Browser, clicked
Connect, gave an agent a task, asked Claude Code to browse, or opened {name} again while an agent was working. If
{name} asks at any other time, it isn't AI Browser: click Deny, unless you just started another browser tool
yourself.
Once the switch is on, AI Home's browser card has a Connect button."""
LEFT_ASKING = ('{name} is still showing "Allow remote debugging?" from this AI Browser: click Cancel there. AI Browser '
               "has closed, so Allow would connect nothing and keep {name}'s \"controlled by automated test software\" "
               "bar up until {name} restarts.")


def _max_agents() -> int:
    try:
        return min(10, max(1, int(os.environ.get("AIB_APP_MAX_AGENTS", "3"))))
    except ValueError:
        return 3


def app_browser(choice: str | None = None) -> str:
    """Where agents browse: always the user's own browser. AI Browser's own Chrome is gone, so "app" (from --browser
    or $AIB_APP_BROWSER) is refused with a plain message, and anything else that names no browser too: never a
    guess."""
    value = (choice or os.environ.get("AIB_APP_BROWSER") or "").strip().lower()
    if value == "app":
        raise ValueError(RETIRED_APP)
    if value and value not in BROWSERS:
        raise ValueError(f"--browser must be brave, not {value!r}")
    return "brave"


def brave_env(folder: Path) -> dict[str, str]:
    """Every agent's engine drives the user's own browser."""
    return {"AIB_BROWSER": "chrome", "AIB_CHROME_DIR": str(folder)}


def write_link(home: Path, url: str, token: str, cdp: str | None = None, browser_dir: Path | None = None) -> Path:
    """<home>/app/link.json (mode 0600): how Claude Code sessions find this app, and its relay to the user's Brave."""
    path = Path(home) / "app" / "link.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"events": f"{url}/agent-events", "session_token": token, "pid": os.getpid()}
    if cdp is not None and browser_dir is not None:
        data.update({"cdp": cdp, "browser_dir": str(browser_dir)})
    write_atomic(path, json.dumps(data).encode("utf-8"), 0o600)  # holds the session token
    return path


async def run_app(home: Path, model: str = "sonnet", claude: str | Sequence[str] | None = None,
                  ready: Callable | None = None, stop: asyncio.Event | None = None,
                  out: Callable[[str], None] = print, browser: str | None = None, window_browser: str | None = None,
                  launcher: Callable | None = None, desktop: Callable | None = None) -> int:
    """0 once AI Browser's window is closed (or `stop` is set); 1 with a message when it can't start. `launcher` takes
    the window's setting and returns the browser window (default_launcher); `desktop` takes the home and the shortcut
    and returns AI Browser's own app, or None while it isn't set up (default_desktop). Tests pass their own."""
    home = Path(home)
    try:
        app_browser(browser)
        if window_browser is not None and window_browser not in WINDOW_CHOICES:
            raise ValueError(f"--window must be auto, chrome, brave or edge, not {window_browser!r}")
    except ValueError as exc:
        out(f"error: {exc}")
        return 1
    lock = _lock(home)  # before anything is touched: a second run must not disturb the first one's files
    if lock is None:
        out("error: AI Browser is already running: its window is open (look for it in "
            f"{platforms.shortcut('the Dock', 'the taskbar')})")
        return 1
    try:
        return await _run(home, model, claude, ready, stop or asyncio.Event(), out, window_browser, launcher, desktop)
    finally:
        lock.close()


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


async def _call(method, *args):
    """A window's launch or close: a coroutine is awaited (the tests' windows); a plain call runs in a thread, because
    closing waits up to 10 s for the browser to quit."""
    if inspect.iscoroutinefunction(method):
        return await method(*args)
    return await asyncio.to_thread(method, *args)


async def _first_window(server: AppServer, stop: asyncio.Event) -> bool:
    """True once the window's first socket is in; False after WINDOW_START_WAIT, or when `stop` is set first."""
    deadline = time.monotonic() + WINDOW_START_WAIT
    while not server.window_seen:
        if stop.is_set() or time.monotonic() >= deadline:
            return False
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), POLL)
    return True


async def _until_closed(server: AppServer, stop: asyncio.Event, window=None) -> None:
    """Until `stop`. AI Browser's own app: until it has quit or gone (closing its window only hides it). A browser
    window: until no window socket has been open for WINDOW_GRACE seconds in a row."""
    ended = getattr(window, "ended", None)
    if isinstance(ended, asyncio.Event):
        waiting = [asyncio.ensure_future(stop.wait()), asyncio.ensure_future(ended.wait())]
        try:
            await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in waiting:
                task.cancel()
        return
    empty_since: float | None = None
    while not stop.is_set():
        if server.window_count:
            empty_since = None
        elif empty_since is None:
            empty_since = time.monotonic()
        elif time.monotonic() - empty_since >= WINDOW_GRACE:
            return
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), POLL)


async def _open_app(home: Path, server: AppServer, url: str, desktop: Callable | None, window_browser: str | None,
                    out: Callable[[str], None]):
    """AI Browser's own app, started and linked; or None, and this run uses a browser window. That happens when the
    app isn't set up, when --window asked for one, or when the app couldn't start: then why is said, and kept for
    Settings."""
    if window_browser is not None:
        return None
    app = (desktop or default_desktop)(home, server.settings.get()["shortcut"])
    if app is None:
        return None
    if stale(home):
        out(UPDATING)
    server.attach_desktop(app)
    try:
        await _call(app.launch, lambda: f"{url}/open?code={server.new_launch_code()}")  # made after any rebuild
    except WindowError as exc:
        server.detach_desktop()
        layout.set_problem(home, str(exc))
        out(f"{exc}. AI Browser opens in a browser window this time.")
        return None
    layout.set_problem(home, None)
    if app.note:
        out(app.note)
    return app


async def _run(home: Path, model: str, claude: str | Sequence[str] | None, ready: Callable | None,
               stop: asyncio.Event, out: Callable[[str], None], window_browser: str | None,
               launcher: Callable | None, desktop: Callable | None) -> int:
    accounts = Accounts(home, claude=claude)  # Settings → Accounts: Default, and the logins the user added
    agents = AgentManager(home, claude=claude, max_working=_max_agents(), accounts=accounts)
    brain_account = BrainAccount(accounts)  # the Brain's and its skill writer's calls, on the Brain's account
    brain = BrainService(BrainStore(home), agents, ask=brain_account, claude=claude, agent_model=model)
    workflows = WorkflowStore(home)
    runner = WorkflowRunner(workflows, agents)
    skills = SkillWriter(Path.home() / ".claude" / "skills", ask=brain_account, claude=claude,
                         cwd=home / "brain" / "calls")  # personal skills stay in ~/.claude/skills (plan decision 14)
    hearing = HearingService(ModelStore(home / "models"), WhisperEngine())  # talking; the model only on Download
    tools = ToolsConfig(home, claude_home=accounts.claude_home(DEFAULT))  # Default's .claude.json (Review Focus 1)
    server = AppServer(home, agents, default_model=model, brain=brain, tools=tools, workflows=workflows,
                       runner=runner, skill_writer=skills, hearing=hearing, port_file=home / "app" / "port",
                       accounts=accounts, brain_account=brain_account)
    server.out = out
    window = ticker = brave = link_file = None
    try:
        try:
            url = await server.start()
        except RuntimeError as exc:
            out(f"error: {exc}")
            return 1
        own = own_browser_dir()  # the user's own browser (Brave first): where agents browse
        cdp = url.replace("http://", "ws://", 1) + "/cdp"
        brave = BraveLink(own, tokens=server.tokens, app_origin=url)
        agents.env.update({"AIB_APP_EVENTS": f"{url}/agent-events", "AIB_APP_CDP": cdp, "AIB_APP_ORIGIN": url,
                           **brave_env(own)})
        server.attach_brave(brave)
        agents.close_tabs = brave.close_targets
        link_file = write_link(home, url, server.session_token, cdp, own)
        await brave.start()  # looks at the switch; it never connects by itself
        window = await _open_app(home, server, url, desktop, window_browser, out)  # AI Browser's own app, if set up
        if window is not None:
            server.window_info = {"using": window.id, "name": window.name, "note": "",
                                  "choices": await asyncio.to_thread(choices)}
        else:  # a browser window, as before the app
            try:
                window = (launcher or default_launcher(home))(window_browser or server.settings.get()["window_browser"])
            except WindowError as exc:
                out(f"error: {exc}")
                return 1
            if window.note:
                out(window.note)
            server.window_info = {"using": window.id, "name": window.name, "note": window.note,
                                  "choices": await asyncio.to_thread(choices)}  # detection once, at start
            try:
                await _call(window.launch, f"{url}/open?code={server.new_launch_code()}")
            except WindowError as exc:
                out(f"error: {exc}")
                return 1
        if not await _first_window(server, stop):
            if stop.is_set():
                return 0
            out(NO_APP_PAGE if server.desktop is not None else NO_WINDOW.format(name=window.name))
            return 1
        out(app_text() if server.desktop is not None else ready_text() + setup_hint(home))
        if brave.state == "off":
            out(SWITCH.format(name=brave.name, inspect=inspect_address(brave.folder)))
        else:
            server.connect_brave("start")  # once, as the app starts: Brave asks "Allow remote debugging?"
        ticker = asyncio.create_task(_tick(runner))  # scheduled workflows run while the app does
        if ready is not None:
            result = ready(url, window)
            if inspect.isawaitable(result):
                await result
        await _until_closed(server, stop, window)
        if server.desktop is not None and window.ended.is_set() and not window.quit_by_user and not stop.is_set():
            out(APP_ENDED)
        return 0
    finally:
        asking = brave is not None and brave.state == "asking"  # Brave's question outlives this run (app/cdprelay.py)
        if ticker is not None:
            ticker.cancel()
        if window is not None:  # first, so the window goes at once (after a hand-off it ends nothing, and says so)
            with contextlib.suppress(Exception):
                note = await _call(window.close)
                if note:
                    out(note)
        if link_file is not None:
            with contextlib.suppress(OSError):
                platforms.unlink(link_file, missing_ok=True)
        await server.stop()  # every agent's Claude Code process ends, and the relay's clients with them
        if brave is not None:
            await brave.close()  # the one connection to Brave closes last; the agents' tabs and groups stay there
        if asking:
            out(LEFT_ASKING.format(name=brave.name))
