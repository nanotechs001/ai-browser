"""The tool facade: every ai-browser tool call goes through Engine, which never raises into the session."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from websockets.exceptions import InvalidStatus

from . import config, platforms
from .agentlink import GROUPS_TTL, AgentLink
from .browser import Browser, BrowserError, Tab
from .cdp import CDP, CDPError
from .checks import Check, CheckGate
from .chrome import ChromeError, _same_folder, browser_name, find_ws_url, own_browser_dir
from .config import READ_LIMIT, SHELL_LIMIT, load_config, project_root
from .grouping import Placer
from .live import LiveView
from .qa import run_qa
from .sandbox import DockerError, SandboxInfo, Sandboxes
from .shellguard import shell_problem
from .skills import Catalog
from .steps import parse_steps
from .tasklog import TaskLog, new_task_id
from .workfs import PathError, WorkDir

DESCRIPTION_LIMIT = 160
CHROME_ALLOW_WAIT = 60  # seconds a call waits for the user's "Allow"; the question itself stays until they answer
RECONNECTED = {"chrome": "(reconnected to your {name}: earlier tabs and element ids from this session are gone)\n"}
BROWSER_KINDS = {"": "chrome", "own": "chrome", "chrome": "chrome", "brave": "chrome",
                 "sandbox": "sandbox"}  # AIB_BROWSER -> the browser: "chrome" is the user's own (Brave or Chrome)
BAD_BROWSER = "AIB_BROWSER must be own, chrome, brave or sandbox"
RETIRED_BROWSER = ("AIB_BROWSER=app is retired: AI Browser's own Chrome is gone. Use own (your browser) or "
                   "sandbox.")
ASK_SESSION = ("Ask the user to turn the switch on, or whether they want the Docker sandbox instead "
               "(sandbox_start()).")
ASK_AGENT = "Ask the user to turn the switch on (AI Home shows how)."
QA_PROFILE = "qa"  # QA's own named sandbox: it stays up between runs, `ai-browser stop qa` stops it
QA_HINT = "or, if the user wants QA in their own browser, sandbox_start(chrome=true) first"
QA_WHERE = "checked in the Docker sandbox"
RELAY_WAIT = 65  # seconds to wait for the app's relay: its own wait for Allow (60 s) answers first
APP_GONE = ("AI Browser stopped, so this session lost its connection to your {name}. Ask the user to start AI Browser "
            "again, or, if they want this session to connect to {name} by itself ({name} will ask \"Allow remote "
            "debugging?\"), call sandbox_start(chrome=true).")
APP_SILENT = ("AI Browser didn't answer, so this session can't use your {name} through it now. Ask the user to look "
              "at the terminal where AI Browser runs.")
APP_SILENT_AGENT = ("AI Browser didn't answer, so this agent can't use your {name} now. Ask the user to look at the "
                    "terminal where AI Browser runs.")
CUT_OFF_AGENT = ("The user cut this agent off from {name} in AI Home: tell the user. The browser stays off for this "
                 "agent.")
CUT_OFF_SESSION = "The user disconnected this Claude Code session from {name} in AI Home: tell the user."


@dataclass
class Route:
    """Where this session's browser connection goes (Decision 13): "relay" (the app's /cdp) or "direct"."""
    kind: str
    folder: Path
    url: str = ""
    token: str = ""
    link: AgentLink | None = None
    note: str = ""  # the status line's "not through AI Browser: …"
_KNOWN_ERRORS = {"ChromeError", "DockerError", "StepError", "PathError", "SkillNotFound", "AmbiguousSkill", "CDPError",
                 "BrowserError", "JSError", "StepStale", "StepBlocked", "ValueError"}


def _sandbox_profile() -> str:
    """AIB_PROFILE when it names a sandbox profile other than "default" (README "Logging in to sites"), else ""."""
    profile = os.environ.get("AIB_PROFILE", "").strip()
    return "" if profile == "default" else profile


def browser_kind(value: str) -> str | None:
    """The browser AIB_BROWSER names ("chrome": the user's own; "sandbox"), or None for anything else."""
    return BROWSER_KINDS.get(value.strip().lower())


@dataclass
class ToolResult:
    text: str
    images: list[bytes] = field(default_factory=list)


def _message(exc: BaseException) -> str:
    text = str(exc) or type(exc).__name__
    return text if type(exc).__name__ in _KNOWN_ERRORS else f"{type(exc).__name__}: {text}"


def _alive(pid: int) -> bool:
    """Whether a process still runs: platforms.pid_alive, looked up at call time (safe on Windows too)."""
    return platforms.pid_alive(pid)


_CLOSING: set[asyncio.Task] = set()  # closes of direct connections nobody uses any more, kept until they finish


def _close_if_allowed(asking: asyncio.Future) -> None:
    """A done-callback for a direct handshake nobody waits for: if the user allowed it, close the connection at once."""
    if not asking.cancelled() and asking.exception() is None:
        task = asyncio.ensure_future(asking.result().close())
        _CLOSING.add(task)
        task.add_done_callback(_CLOSING.discard)


def _clean(text: str) -> str:
    """Replace lone UTF-16 surrogates (half an emoji) so tool text is always valid UTF-8."""
    return re.sub("[\ud800-\udfff]", "�", text)


def _outcome(text: str) -> str:
    lines = text.splitlines()
    if any(line.startswith("⛔ bot check") for line in lines):
        return "check"
    if any(line.startswith("⏸ waiting for the user") for line in lines):
        return "waiting"
    if any(line.startswith("⛔") for line in lines):
        return "blocked"
    if any(line.startswith("✗") for line in lines):
        return "failed"
    return "ok"


async def _raise(exc: BaseException):
    raise exc


class Engine:
    def __init__(self, home: Path | None = None, default_profile: str = "default", catalog: Catalog | None = None):
        self.home = Path(home) if home else config.home()
        self.cfg = load_config(self.home)
        self.task_id = new_task_id()
        self.log = TaskLog(self.home / "tasks", self.task_id)
        self.default_profile = default_profile
        self._kind = browser_kind(os.environ.get("AIB_BROWSER", ""))  # None: a value that names no browser
        if not os.environ.get("AIB_BROWSER", "").strip() and _sandbox_profile():
            self._kind = "sandbox"  # AIB_PROFILE alone (a client's logins) chooses the Docker sandbox up front
        self.default_chrome = self._kind == "chrome"  # the user's own browser (Brave or Chrome): the default
        self._wanted: tuple[str, bool, str] | None = None  # (profile, fresh, sandbox|chrome) from sandbox_start
        self._catalog = catalog
        self.sandboxes: Sandboxes | None = None
        self.info: SandboxInfo | None = None
        self.cdp: CDP | None = None
        self.browser: Browser | None = None
        self.work: WorkDir | None = None
        self.live = None  # LiveView, set up on first start (live.py)
        self._lock = asyncio.Lock()
        self._shell_logs = 0
        self._link: AgentLink | None = None  # in AI Browser, an agent reports its tabs to the app
        self._adopted_start = False  # the user's tab this agent was started in (AIB_APP_ADOPT) is taken on once
        self._placer: Placer | None = None  # in the user's own browser: where our tabs go (a group, or a window)
        self._agent_id = ""  # AIB_APP_AGENT: this engine serves an agent of ai-browser app
        self.gate = CheckGate()  # the bot-check hold and the skipped sites: they outlast any browser this session uses
        self._notes: list[str] = []  # a hold that ended between calls (the user closed the tab): the next call says so
        self._qa_browser: Browser | None = None  # QA's sandbox browser, kept while a bot check it found is held
        self._relayed = False  # this browser connection goes through the app's relay
        self._via_relay = False  # this session went through the relay before (if the app stops, it says so)
        self._direct_ok = False  # sandbox_start(chrome=true): the user chose a direct connection
        self._folder: Path | None = None  # the browser folder this session connects to (its name in every text)
        self._note = ""
        self._asking: dict[str, asyncio.Future] = {}  # ws url -> a direct handshake whose question is still open

    @property
    def catalog(self) -> Catalog:
        if self._catalog is None:
            self._catalog = Catalog.discover(
                Path.home() / ".claude",
                platforms.claude_desktop_dir(),
                project_root() / "skills",
                set(self.cfg.blocked_skills),
            )
        return self._catalog

    # ---- plumbing ---------------------------------------------------------------------------------

    async def _run(self, tool: str, args: dict, work) -> ToolResult:
        started = time.perf_counter()
        async with self._lock:
            try:
                result = await work()
                if isinstance(result, str):
                    result = ToolResult(result)
                outcome = _outcome(result.text)
            except Exception as exc:  # tools report problems as text; they never crash the session
                result, outcome = ToolResult(f"error: {_message(exc)}"), "error"
        ms = round((time.perf_counter() - started) * 1000)
        result.text = _clean(f"{result.text}\n⏱ {ms} ms")
        try:
            self.log.record(tool, args, ms, outcome, result.text)
        except Exception:  # the log must never cost the caller their result
            pass
        return result

    async def _start(self, profile: str, fresh: bool) -> None:
        if self.sandboxes is None:
            self.sandboxes = Sandboxes(self.home, mounts=self.catalog.mounts())
        info = await asyncio.to_thread(self.sandboxes.start, profile, fresh)
        work = WorkDir(info.work_host, self.task_id)
        cdp = None
        try:
            cdp = await CDP.connect(await asyncio.to_thread(self.sandboxes.ws_url, info))
            browser = Browser(cdp, work, self.cfg, app_origin=os.environ.get("AIB_APP_ORIGIN", ""))
            self._wire(browser)
            await browser.start()
        except BaseException:  # keep no half-started state: the next call starts cleanly
            if cdp is not None:
                await cdp.close()
            if info.fresh:
                await asyncio.to_thread(self.sandboxes.stop, info.name)
            raise
        self.info, self.work, self.cdp, self.browser = info, work, cdp, browser
        if not info.fresh:
            await self._close_orphans()
            self._register()
        await self._attach_live()

    async def _start_chrome(self, mode: str = "chrome") -> None:
        """Connect to the user's own running browser (Brave or Chrome), through the app's relay while the app runs
        (Decision 13)."""
        agent = self._agent_id = os.environ.get("AIB_APP_AGENT", "")
        route, self._relayed, self._note = None, False, ""
        route = self._route()
        self._folder, self._note = route.folder, route.note
        if route.kind == "direct":
            try:
                ws_url = await asyncio.to_thread(find_ws_url, route.folder, 2)
            except ChromeError as exc:
                raise ChromeError(f"{exc}. {ASK_AGENT if agent else ASK_SESSION}") from None
        if route.kind == "relay":
            cdp = await self._through_relay(route)
            self._relayed = self._via_relay = True
            self._direct_ok = False
            self._drop_direct()
        else:
            name = self._browser_name()
            cdp = await self._direct(ws_url, name)
        work_host = self.home / "sandboxes" / "chrome" / "work"  # shared with the shell container of both modes
        work = WorkDir(work_host, self.task_id)
        adopt = os.environ.get("AIB_APP_ADOPT", "") if agent else ""
        self._app_link()  # an agent of ai-browser app reports its tabs to the app
        self._placer = None
        if mode == "chrome":  # where our tabs go: the app's tab groups (through its watcher), or windows of their own
            if agent:
                self._placer = Placer(self._link)
            elif self._note:  # another browser than the app's: its tabs can't join the app's groups
                self._placer = Placer(None)
            else:
                rediscover = lambda: AgentLink.discover(self.home, self.task_id)  # noqa: E731
                self._placer = Placer(route.link if route.link is not None else rediscover(), rediscover=rediscover)
        try:
            # the user's own browser: background tabs only, each placed by the placer
            browser = Browser(cdp, work, self.cfg, mode="chrome", placer=self._placer, keep_tabs=bool(agent),
                              handed=self._handed if agent else None,
                              app_origin=os.environ.get("AIB_APP_ORIGIN", ""))
            self._wire(browser)
            browser.on_tab_event(lambda kind, tab: self._report(f"tab_{kind}", tab))
            browser.on_tab_change(lambda tab: self._report("working_tab", tab))
            await browser.start()
            session = self._placer.link if self._placer is not None and not agent and not self._relayed else None
            if session is not None:  # a Claude Code session joins the running app: its tabs show in AI Home
                with contextlib.suppress(Exception):
                    await session.hello()
            if adopt and not self._adopted_start:  # once: the tab the user started this agent in
                self._adopted_start = True
                with contextlib.suppress(BrowserError, CDPError):
                    await browser.adopt(adopt)
        except BaseException:
            await cdp.close()
            raise
        self.info = SandboxInfo(f"aib-{mode}", mode, "", work_host, False, False, chrome=True)
        self.work, self.cdp, self.browser = work, cdp, browser
        if mode == "chrome" and not agent and not self._relayed:  # the app cleans up for agents and relayed sessions
            await self._close_orphans()
            self._register()
        if mode == "chrome":  # the live view follows the session's tab in the user's browser too
            await self._attach_live()

    def _route(self) -> Route:
        """Decision 13. An app agent always goes through the relay. A session goes through it while the app runs,
        unless AIB_CHROME_DIR names another browser. Without the app a session connects directly, except after the app
        stopped under it, until the user chooses sandbox_start(chrome=true)."""
        agent, relay = os.environ.get("AIB_APP_AGENT", ""), os.environ.get("AIB_APP_CDP", "")
        if agent:
            folder = own_browser_dir()
            if relay:
                return Route("relay", folder, relay, os.environ.get("AIB_APP_AGENT_TOKEN", ""))
            return Route("direct", folder)
        link = AgentLink.discover(self.home, self.task_id)
        if link is not None and link.cdp and link.browser_dir is not None:
            configured = os.environ.get("AIB_CHROME_DIR", "").strip()
            if not configured or _same_folder(Path(configured).expanduser(), link.browser_dir):
                return Route("relay", link.browser_dir, link.cdp, link=link)
            folder = Path(configured).expanduser()
            return Route("direct", folder,
                         note=f"not through AI Browser: AIB_CHROME_DIR names your {browser_name(folder)}")
        if self._via_relay and not self._direct_ok:
            raise ChromeError(APP_GONE.format(name=browser_name(self._folder or own_browser_dir())))
        return Route("direct", own_browser_dir(), link=link)

    async def _direct(self, ws_url: str, name: str) -> CDP:
        """A connection of this session's own (no app). The browser's "Allow remote debugging?" isn't tied to the
        handshake that asked: one given up on leaves the question on screen, and Allow there later opens a connection
        nobody holds (see app/cdprelay.py). So the handshake stays until the user answers: a call waits
        CHROME_ALLOW_WAIT for the answer, and the next call joins the same handshake instead of asking again."""
        asking = self._asking.get(ws_url)
        if asking is None or asking.cancelled() or (asking.done() and asking.exception() is not None):
            asking = self._asking[ws_url] = asyncio.ensure_future(CDP.connect(ws_url, open_timeout=None))
        try:
            cdp = await asyncio.wait_for(asyncio.shield(asking), CHROME_ALLOW_WAIT)
        except TimeoutError:
            raise ChromeError(f"{name} is asking \"Allow remote debugging?\": ask the user to click Allow there, then "
                              "try again (the next call uses the same question)") from None
        except Exception as exc:
            if self._asking.get(ws_url) is asking:
                del self._asking[ws_url]
            raise ChromeError(f"{name} didn't accept the connection ({type(exc).__name__}): when {name} asks "
                              "\"Allow remote debugging?\", click Allow, then try again") from None
        self._asking.pop(ws_url, None)
        return cdp

    def _drop_direct(self) -> None:
        """The app's relay serves this session now. A connection the session's own question opened is closed, not held
        unused (the browser would count two, and its bar would come back whenever one opened or closed). A question
        still open is left to the user's answer, since ending its handshake would leave it on screen with nothing
        behind it; if they allow it, that connection closes at once."""
        for asking in self._asking.values():
            asking.add_done_callback(_close_if_allowed)
        self._asking.clear()

    async def _through_relay(self, route: Route) -> CDP:
        """The app's relay: an agent with its own token; a session says hello first, for its token. An error here is
        never followed by a direct connection (the browser would ask the user out of the blue)."""
        name, link, token = browser_name(route.folder), route.link, route.token
        if link is not None:
            answer = await link.hello()
            if answer is not None and answer.get("cut_off"):
                raise ChromeError(CUT_OFF_SESSION.format(name=name))
            token = answer.get("cdp_token") if answer is not None else None
            if not isinstance(token, str) or not token:
                raise ChromeError(self._app_down(link, name))
        try:
            return await CDP.connect(route.url, open_timeout=RELAY_WAIT, headers={"X-AIB-Agent-Token": token})
        except InvalidStatus as exc:
            status = exc.response.status_code
            text = bytes(exc.response.body or b"").decode("utf-8", "replace").strip()[:500]
            if status == 410:
                raise ChromeError((CUT_OFF_SESSION if link is not None else CUT_OFF_AGENT).format(name=name)) \
                    from None
            if status == 409 and text:
                raise ChromeError(text) from None  # the relay's own words: switch off, said no, not connected
            raise ChromeError(f"AI Browser refused this connection ({status} {text})".strip()) from None
        except Exception:
            raise ChromeError(self._app_down(link, name) if link is not None
                              else APP_SILENT_AGENT.format(name=name)) from None

    @staticmethod
    def _app_down(link: AgentLink, name: str) -> str:
        return (APP_GONE if not _alive(link.pid) else APP_SILENT).format(name=name)

    def _app_link(self) -> AgentLink | None:
        """An agent of ai-browser app reports to the app (AIB_APP_EVENTS) from its first call, whichever browser that
        call uses: a bot check QA meets in its own sandbox, before any Brave is connected, reaches AI Home too."""
        agent = os.environ.get("AIB_APP_AGENT", "")
        if self._link is None and agent and os.environ.get("AIB_APP_EVENTS"):
            self._link = AgentLink(os.environ["AIB_APP_EVENTS"], os.environ.get("AIB_APP_AGENT_TOKEN", ""), agent)
        return self._link

    def _report(self, kind: str, tab) -> None:
        """Tell the app about one of this session's tabs (an agent's link, or a Claude Code session's)."""
        link = self._link or (self._placer.link if self._placer is not None else None)
        if link is not None:
            link.report(kind, tab.target, tab.adopted)

    async def _handed(self) -> list[dict]:
        """The tabs the user handed this agent in AI Home (Hand over)."""
        return (await self._link.status())["handed"] if self._link is not None else []

    async def _placement(self) -> str:
        """Where this session's tabs go in the user's own browser: the status line's last part."""
        if self._placer is None or self.browser is None or self.browser.mode != "chrome":
            return ""
        link = self._placer.link
        if link is None:
            return "its tabs open in their own window: ai-browser app isn't running"
        if not (await link.status(GROUPS_TTL))["groups"]:
            return f"its tabs open in their own window: the watcher isn't connected in your {self._browser_name()}"
        return "tab group 'Claude Code'" if link.agent.startswith("cc-") else "a tab group named after this task"

    async def _taken_back(self) -> str:
        """First in every call: let go of handed tabs the user took back. A held tab among them ends the hold as
        closed (Decision 4): the site is skipped, and the hold never outlives the hand-over."""
        if self.browser is None or self.cdp is None or self.cdp.closed or self.browser.handed is None:
            return ""
        held, note = self.gate.held, ""
        if held is not None and held.where == "session" and held.adopted:
            detached = any(tab.detached for tab in self.browser.owned.values() if tab.target == held.target)
            if detached or held.target not in {item["target"] for item in await self.browser._handed_now()}:
                note = self._release("closed")  # wave 1's sync release: the site is skipped
        return note + await self.browser.let_go_of_taken_back()

    def _default_kind(self) -> str:
        """The browser this session uses until sandbox_start picks another: never a guess."""
        if os.environ.get("AIB_BROWSER", "").strip().lower() == "app":
            raise ValueError(RETIRED_BROWSER)
        if self._kind is None:
            raise ValueError(BAD_BROWSER)
        return self._kind

    def _browser_name(self) -> str:
        return browser_name(self._folder if self._folder is not None else own_browser_dir())

    async def _attach_live(self) -> None:
        if self.live is None:
            live = LiveView()
            try:
                await live.start()
                self.live = live
            except RuntimeError:
                pass  # no free port: the tools still work, only watching is unavailable
        if self.live is not None:
            await self.live.attach(self.browser)

    # ---- session registry: which tabs in a shared profile container belong to which live process ------

    def _sessions_dir(self) -> Path:
        return self.home / "sandboxes" / self.info.profile / "sessions"

    def _register(self) -> None:
        if self.info is None or self.info.fresh or self.browser is None or \
                self._agent_id or self._relayed:  # through the relay the app cleans up
            return
        try:
            folder = self._sessions_dir()
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{self.task_id}.json").write_text(
                json.dumps({"pid": os.getpid(), "targets": self.browser.owned_targets()}), encoding="utf-8")
        except OSError:
            pass

    def _unregister(self) -> None:
        if self.info is not None and not self.info.fresh:
            with contextlib.suppress(OSError):
                (self._sessions_dir() / f"{self.task_id}.json").unlink()

    async def _close_orphans(self) -> None:
        """Close tabs left in this profile's browser by sessions whose process has ended."""
        for record in self._sessions_dir().glob("*.json"):
            if record.stem == self.task_id:
                continue
            try:
                data = json.loads(record.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {"pid": 0, "targets": []}
            try:
                alive = _alive(int(data.get("pid", 0)))
            except (OSError, TypeError, ValueError):  # a record it can't judge is left alone: its tabs stay open
                continue
            if alive:
                continue
            for target in data.get("targets", []):
                with contextlib.suppress(CDPError):
                    await self.cdp.send("Target.closeTarget", {"targetId": target})
            with contextlib.suppress(OSError):
                record.unlink()

    async def _teardown(self, stop_container: bool) -> None:
        self._unregister()
        if self.live is not None:
            await self.live.detach()
        if self.browser is not None:
            try:
                await self.browser.close()
            except Exception:
                pass
        if self._link is not None:
            await self._link.flush()
            self._link = None
        session = self._placer.link if self._placer is not None and not self._agent_id else None
        if session is not None:  # a Claude Code session leaves the app's list
            await session.flush()
            with contextlib.suppress(Exception):
                await session.bye()
        self._placer = None
        if self.cdp is not None:
            await self.cdp.close()
        if stop_container and self.info is not None:
            await asyncio.to_thread(self.sandboxes.stop, self.info.name)
        self.browser = self.cdp = None

    async def _ready(self) -> str:
        """Make sure the browser this session chose is running; returns a note when it had to reconnect."""
        if self.browser is None:  # first use, or an earlier start or reconnect failed: never switch browsers quietly
            profile, fresh, kind = self._wanted or (self.default_profile, False, self._default_kind())
            if kind in RECONNECTED:
                connected_before = self.info is not None and self.info.chrome and self.info.profile == kind
                await self._start_chrome(kind)
                return ((RECONNECTED[kind].format(name=self._browser_name()) if connected_before else "")
                        + await self._held_after_reconnect())
            await self._start(profile, fresh)
            return await self._held_after_reconnect()  # a hold from a browser that is gone ends here
        if self.cdp.closed and self.info.chrome:  # the user's browser was closed or restarted
            kind = self.browser.mode
            stale = [tab.target for tab in self.browser.owned.values() if not tab.adopted]
            await self._teardown(stop_container=False)
            await self._start_chrome(kind)
            for target in stale:  # still open when only the connection dropped
                with contextlib.suppress(CDPError):
                    await self.cdp.send("Target.closeTarget", {"targetId": target})
            return RECONNECTED[kind].format(name=self._browser_name()) + await self._held_after_reconnect()
        if self.cdp.closed:  # Chromium or its container died
            profile, fresh = self.info.profile, self.info.fresh
            await self._teardown(stop_container=fresh)  # a throwaway pair is replaced whole (no stray shell)
            await self._start(self.default_profile if fresh else profile, fresh)
            return ("(sandbox restarted: the browser had stopped, so earlier pages and element ids are gone)\n"
                    + await self._held_after_reconnect())
        return await self.browser.ensure_tab()  # the user, its window or the page may have closed our tab

    async def _with_browser(self, tool: str, args: dict, action, refuse=None) -> ToolResult:
        """Run a browser tool. `refuse()` (by default the gate's refusal for the tool) is asked first, before _ready()
        starts or reconnects anything: a refused call touches nothing."""
        async def work():
            notes = await self._taken_back() + self._take_notes()  # first: a taken-back held tab ends the hold
            refused = refuse() if refuse is not None else self.gate.refusal(tool)
            if refused is not None:
                return notes + refused
            note = ""
            try:
                note = await self._ready()
                try:
                    result = await action(self.browser)
                finally:
                    self._register()  # tabs may have been opened or closed
            except BrowserError as exc:  # nothing ran (no tab to work in, say): what happened first still arrives now
                said = notes + note + self._take_notes()
                if not said:
                    raise
                return f"{said}{exc}"
            except BaseException:
                self._notes.insert(0, notes)  # not lost: the next call says it
                raise
            notes += note + self._take_notes()
            if isinstance(result, ToolResult):
                result.text = notes + result.text
                return result
            return notes + result
        return await self._run(tool, args, work)

    # ---- bot checks: the session holds until the user deals with one ------------------------------------

    def _wire(self, browser: Browser) -> None:
        """Every Browser this session uses hands a check to the same hold and skips the same sites."""
        browser.on_check(self._on_check)
        browser.skipped_site = self.gate.skipped_for
        browser.waiting = lambda: self.gate.waiting() if self.gate.held is not None else None
        browser.on_tab_event(self._on_tab_event)

    async def _on_check(self, tab: Tab, check: Check) -> str:
        """A bot check in this session's browser (wave 1's hook, set by _wire)."""
        return await self._hold(self.browser, tab, check)

    async def _hold(self, browser, tab: Tab, check: Check, where: str = "session") -> str:
        """A bot check in `tab` of `browser`: hold the session, bring its tab forward (even for an agent working in
        the background), tell the app; returns the hand-off. `where` is "session" (this session's browser) or "qa"
        (QA's own sandbox browser). The live-view link is given in the sandbox and for a hold in QA's sandbox, where
        the user can't see the tab otherwise."""
        self.gate.hold(tab.key, tab.target, check, tab.adopted, where=where)
        if browser is not None:
            with contextlib.suppress(BrowserError, CDPError):
                await browser.bring_to_front(tab)
        sandbox = where == "qa" or (self.info is not None and not self.info.chrome)
        live = self.live.url if sandbox and self.live is not None and self.live.url else None
        link = self._app_link()  # even when QA's sandbox is the first browser this agent used
        if link is not None:
            link.report("check", tab.target, tab.adopted, check=check.kind, site=check.site,
                        **({"live": live} if where == "qa" and live else {}))
        return self.gate.handoff(check, tab.key, live)

    def _release(self, how: str) -> str:
        """The hold ends: "solved" (a read found the check gone) or "closed" (its tab went, so its site is skipped).
        Returns the note for the result."""
        held = self.gate.held
        if held is None:
            return ""
        if how == "solved":
            self.gate.solved()
            note = f"(the bot check in tab {held.tab_key} is gone: carrying on)\n"
        else:
            site = self.gate.closed()
            note = f"(the tab with the bot check was closed, so {site} is off-limits for the rest of this task)\n"
        if self._link is not None:
            self._link.report("check_cleared", held.target, held.adopted, how=how)
        return note

    def _on_tab_event(self, kind: str, tab: Tab) -> None:
        held = self.gate.held
        if kind == "closed" and held is not None and held.where == "session" and held.target == tab.target:
            self._notes.append(self._release("closed"))

    async def _held_after_reconnect(self) -> str:
        """After a reconnect our held tab was closed with the old connection (or the browser restarted), so its site is
        skipped; the user's own (adopted) tab is taken on again if it is still open."""
        held = self.gate.held
        if held is None or held.where != "session":
            return ""
        if held.adopted:
            with contextlib.suppress(BrowserError, CDPError):
                infos = (await self.cdp.send("Target.getTargets"))["targetInfos"]
                if any(info.get("targetId") == held.target for info in infos):
                    tab = await self.browser.adopt(held.target)
                    self.gate.hold(tab.key, tab.target, held.check, True)
                    return ""
        return self._release("closed")

    def _take_notes(self) -> str:
        notes, self._notes = "".join(self._notes), []
        return notes

    def _mark_held(self, listing: str) -> str:
        """`tabs list` marks the held tab."""
        held = self.gate.held
        if held is None:
            return listing
        return "\n".join(f"{line}  (bot check: waiting for the user)" if line[2:].startswith(f"{held.tab_key}  ")
                         else line for line in listing.splitlines())

    def _act_refusal(self, steps) -> str | None:
        """While held no step runs; otherwise a goto to a skipped site is refused before anything runs."""
        refused = self.gate.refusal("act")
        for step in steps:
            if refused is None and step.op == "goto":
                refused = self.gate.refusal("act", url=step.value)
        return refused

    def _status_text(self, placement: str = "") -> str:
        info = self.info
        live = self.live.url if self.live is not None and self.live.url else "not started"
        if info.chrome:
            where = f" · {placement}" if placement else ""
            through = ", through AI Browser's connection" if self._relayed else ""
            note = f" · {self._note}" if self._note else ""
            profile = _sandbox_profile()  # AIB_BROWSER chose the user's browser: a sandbox profile can't apply there
            unused = (f"\nAIB_PROFILE={profile} is a Docker sandbox profile: not used here "
                      f"(sandbox_start(profile=\"{profile}\") uses it)") if profile else ""
            return (f"browser: your {self._browser_name()}{through}{note} · only tabs this session opens, and tabs "
                    f"the user hands it{where}\n"
                    f"work folder {self.work.sandbox_task} (on {platforms.this_computer()}: {self.work.host_task}; "
                    "shell and skill scripts run in a Docker sandbox)\n"
                    f"live view: {live}{unused}")
        return (f"sandbox {info.name} ready · profile {info.profile}{' (throwaway)' if info.fresh else ''}\n"
                f"work folder {self.work.sandbox_task} (on {platforms.this_computer()}: {self.work.host_task})\n"
                f"live view: {live}")

    # ---- sandbox tools --------------------------------------------------------------------------------

    async def sandbox_start(self, profile: str = "default", fresh: bool = False, chrome: bool = False) -> ToolResult:
        async def work():
            refused = self.gate.refusal("sandbox_start")  # no other browser or profile while a bot check waits
            if refused is not None:
                return refused
            if chrome:
                self._direct_ok = True  # the user's explicit choice (Decision 13, step 4)
            kind = "chrome" if chrome else "sandbox"
            self._wanted = (profile, fresh, kind)  # later calls restart this one, even if starting fails now
            live = self.info and self.browser and not self.cdp.closed
            same = live and kind == self.browser.mode and (
                kind != "sandbox" or (fresh and self.info.fresh) or
                (not fresh and not self.info.fresh and self.info.profile == profile))
            if not same:
                if self.browser is not None:
                    await self._teardown(stop_container=self.info.fresh)
                if kind == "sandbox":
                    await self._start(profile, fresh)
                else:
                    await self._start_chrome(kind)
            return self._status_text(await self._placement())
        return await self._run("sandbox_start", {"profile": profile, "fresh": fresh, "chrome": chrome}, work)

    async def sandbox_stop(self) -> ToolResult:
        async def work():
            refused = self.gate.refusal("sandbox_stop")
            if refused is not None:
                return refused
            if self.info is None or self.browser is None:
                return "no sandbox is running in this session"
            name, profile, fresh = self.info.name, self.info.profile, self.info.fresh
            self._wanted = None  # the next browser call starts the default again
            if self.info.chrome:
                where = f"your {self._browser_name()}"
                kept = self.browser.keep_tabs
                await self._teardown(stop_container=False)  # the shell stays up for other sessions of this home
                self.info = None
                if kept:
                    return (f"let go of this session's tabs (AI Home closes them with the agent) and disconnected "
                            f"from {where}")
                return f"closed this session's tabs and disconnected from {where}"
            await self._teardown(stop_container=True)
            self.info = None
            kept = "" if fresh else f" (logins stay saved in profile {profile})"
            return f"stopped {name}{kept}"
        return await self._run("sandbox_stop", {}, work)

    async def sandbox_status(self) -> ToolResult:
        async def work():
            if self.info is None or self.browser is None:
                return "no sandbox running yet; browser tools start the default one automatically"
            return self._status_text(await self._placement()) + "\ntabs:\n" + \
                self._mark_held(await self.browser.tabs("list"))
        return await self._run("sandbox_status", {}, work)

    # ---- browser tools --------------------------------------------------------------------------------

    async def open(self, url: str, new_tab: bool = False) -> ToolResult:
        return await self._with_browser("open", {"url": url, "new_tab": new_tab},
                                        lambda browser: browser.open(url, new_tab),
                                        lambda: self.gate.refusal("open", url=url))

    async def observe(self, find: str | None = None) -> ToolResult:
        if self._qa_hold():  # the held tab is in QA's sandbox: read it there
            return await self._run("observe", {"find": find}, lambda: self._observe_qa_hold(find))

        async def action(browser: Browser) -> str:
            held = self.gate.held
            if held is None or held.where != "session":  # (a hold in QA's own browser: the everyday-Brave spec)
                return await browser.observe(find)
            tab = next((tab for tab in browser.owned.values() if tab.target == held.target), None)
            if tab is None:  # its tab went without a word (it can't be read any more): as closed, the site is skipped
                note = self._release("closed")
                return note + (await browser.observe(find) if browser.current is not None else "")
            check = await browser.check_now(tab)  # the user may have dealt with it: read the held tab again
            if check is None:
                if browser.current is not tab:
                    await browser._switch(tab)  # carry on in that tab; only a check still there calls bring_to_front
                return self._release("solved") + await browser.observe(find)
            return await self._on_check(tab, check)  # still there: handed over again, the tab in front again
        return await self._with_browser("observe", {"find": find}, action)

    async def act(self, steps: list[str], confirmed: bool = False) -> ToolResult:
        args = {"steps": steps, "confirmed": confirmed}
        try:
            parsed = parse_steps(steps)  # report grammar mistakes before touching the sandbox
        except ValueError as exc:
            return await self._run("act", args, lambda: _raise(exc))
        return await self._with_browser("act", args, lambda browser: browser.act(parsed, confirmed),
                                        lambda: self._act_refusal(parsed))

    async def screenshot(self, size: str = "desktop", full_page: bool = False,
                         element: str | None = None) -> ToolResult:
        async def action(browser):
            shots = await browser.screenshot(size, full_page, element)
            if isinstance(shots, str):  # the page is a bot check (handed over) or a skipped site: no picture
                return shots
            lines = []
            for shot in shots:
                path = self.log.save_shot(shot.data, f"{shot.label}{'-' + element if element else ''}")
                lines.append(f"{shot.label} {shot.width}×{shot.height} saved {path}")
            return ToolResult("\n".join(lines), [shot.data for shot in shots])
        return await self._with_browser("screenshot", {"size": size, "full_page": full_page, "element": element},
                                        action)

    async def tabs(self, action: str = "list", tab: str | None = None, url: str | None = None) -> ToolResult:
        if self._qa_hold() and (action == "list" or (action == "close" and tab == self.gate.held.tab_key)):
            return await self._run("tabs", {"action": action, "tab": tab, "url": url},
                                   lambda: self._tabs_qa_hold(action, tab))

        async def run(browser: Browser) -> str:
            text = await browser.tabs(action, tab, url)
            return self._mark_held(text) if action == "list" else text
        return await self._with_browser("tabs", {"action": action, "tab": tab, "url": url}, run,
                                        lambda: self.gate.refusal("tabs", action=action, tab=tab, url=url))

    async def page_log(self) -> ToolResult:
        return await self._with_browser("page_log", {}, lambda browser: browser.page_log())

    async def extract(self, kind: str) -> ToolResult:
        return await self._with_browser("extract", {"kind": kind}, lambda browser: browser.extract(kind))

    async def js(self, code: str) -> ToolResult:
        return await self._with_browser("js", {"code": code}, lambda browser: browser.js(code))

    async def qa(self, url: str, max_pages: int = 30, progress=None, ignore_robots: bool = False) -> ToolResult:
        """Website QA of a whole site, politely; returns the summary (the report is in the work folder). In the user's
        own browser by default, QA crawls in its own Docker sandbox instead (Decision 11). A bot check QA finds holds
        the session like any other, and a host that refused cools down."""
        args = {"url": url, "max_pages": max_pages, "ignore_robots": ignore_robots}
        try:
            sandboxed = self._qa_in_sandbox()
        except ValueError as exc:
            return await self._run("qa", args, lambda: _raise(exc))
        if sandboxed:
            async def work():
                # First, as in every call: a taken-back held tab ends the hold (Decision 4)
                notes = await self._taken_back() + self._take_notes()
                try:
                    return notes + await self._qa_sandboxed(url, max_pages, progress, ignore_robots)
                except BaseException:
                    self._notes.insert(0, notes)  # not lost: the next call says it
                    raise
            return await self._run("qa", args, work)

        async def action(browser):  # wave 1's: in this session's own browser
            return await run_qa(browser, self.work, url, max_pages, progress=progress, on_tabs=self._register,
                                ignore_robots=ignore_robots, on_check=self._on_check,
                                on_host_stopped=self.gate.qa_stop, skipped=self.gate.skipped_for)
        return await self._with_browser("qa", args, action, lambda: self.gate.refusal("qa", url=url))

    def _qa_in_sandbox(self) -> bool:
        """QA's browser, by a fixed rule before the run (Decision 11): the Docker sandbox when this session browses
        in the user's own browser by default; their browser only after sandbox_start(chrome=true), which they asked
        for. Any other session's browser (a sandbox) runs QA itself."""
        return self._wanted is None and self._default_kind() == "chrome"

    def _qa_work(self) -> WorkDir:
        """The session's own work folder, even before its browser is connected: QA's report lands where read_file
        looks. (A folder left from a browser this session stopped is not it: the next call connects the default.)"""
        if self.browser is not None and self.work is not None:
            return self.work
        return WorkDir(self.home / "sandboxes" / "chrome" / "work", self.task_id)

    async def _qa_sandbox_browser(self) -> Browser:
        """A Browser in QA's named sandbox (started, or reused), opening no tab of its own; its tabs are q1…"""
        if self.sandboxes is None:
            self.sandboxes = Sandboxes(self.home, mounts=self.catalog.mounts())
        try:
            info = await asyncio.to_thread(self.sandboxes.start, QA_PROFILE)
        except DockerError as exc:
            raise DockerError(f"{exc}; {QA_HINT}") from None
        cdp = await CDP.connect(await asyncio.to_thread(self.sandboxes.ws_url, info))
        try:
            browser = Browser(cdp, self._qa_work(), self.cfg, key_prefix="q",
                              app_origin=os.environ.get("AIB_APP_ORIGIN", ""))
            await browser.start(first_tab=False)
        except BaseException:
            await cdp.close()
            raise
        return browser

    async def _close_qa_browser(self, browser: Browser) -> None:
        with contextlib.suppress(Exception):
            await browser.close()
        with contextlib.suppress(Exception):
            await browser.cdp.close()

    async def _qa_sandboxed(self, url: str, max_pages: int, progress, ignore_robots: bool) -> str:
        refused = self.gate.refusal("qa", url=url)  # first: a refused qa starts no sandbox
        if refused:
            return refused
        browser = await self._qa_sandbox_browser()

        async def on_check(tab, check) -> str:  # a bot check on one of the site's pages: held there, in QA's sandbox
            await self._show_live(browser)  # first, so the tab brought to the front is the one the live view shows
            return await self._hold(browser, tab, check, where="qa")

        try:
            summary = await run_qa(browser, self._qa_work(), url, max_pages, progress=progress,
                                   ignore_robots=ignore_robots, on_check=on_check,
                                   on_host_stopped=self.gate.qa_stop, skipped=self.gate.skipped_for)
        finally:
            if self.gate.held is not None and self.gate.held.where == "qa":
                self._qa_browser = browser  # kept, with its held tab, until the hold ends
            else:
                await self._close_qa_browser(browser)
        return f"{QA_WHERE} (profile {QA_PROFILE})\n{summary}"

    async def _show_live(self, browser: Browser) -> None:
        """Point the live view at `browser` (starting it if needed): the user solves a check in QA's sandbox there."""
        if self.live is None:
            live = LiveView()
            try:
                await live.start()
            except RuntimeError:
                return  # no free port: the hand-off says so without a link
            self.live = live
        await self.live.attach(browser)

    def _qa_hold(self) -> bool:
        held = self.gate.held
        return held is not None and held.where == "qa" and self._qa_browser is not None

    async def _end_qa_hold(self) -> None:
        """The hold in QA's sandbox ended (solved or skipped): the live view goes back to the session's browser, then
        QA's browser closes (in that order, so the live view never streams from a closed connection)."""
        browser, self._qa_browser = self._qa_browser, None
        if self.live is not None:
            if self.browser is not None and self.cdp is not None and not self.cdp.closed:
                await self.live.attach(self.browser)
            else:
                await self.live.detach()
        if browser is not None:
            await self._close_qa_browser(browser)

    async def _qa_release(self, how: str) -> str:
        """End a hold in QA's sandbox: wave 1's release (the note, the report, a skipped site), then QA's browser
        goes. `_release` stays sync because wave 1's tab-closed callback calls it."""
        note = self._release(how)
        await self._end_qa_hold()
        return note

    async def _observe_qa_hold(self, find: str | None) -> str:
        browser, held = self._qa_browser, self.gate.held
        tab = browser.owned.get(held.tab_key)
        if tab is None or browser.cdp.closed:  # closed in the live view, by the page, or with QA's sandbox: skipped
            return await self._qa_release("closed")
        await browser._switch(tab)
        check = await browser.check_now(tab)
        if check is not None:  # still there after the user's Continue: in front again, handed over again
            with contextlib.suppress(BrowserError, CDPError):
                await browser.bring_to_front(tab)
            return self.gate.handoff(check, tab.key, self.live.url if self.live is not None else None)
        page = await browser.observe(find)
        return await self._qa_release("solved") + page

    async def _tabs_qa_hold(self, action: str, tab: str | None) -> str:
        browser, held = self._qa_browser, self.gate.held
        if action == "close":  # the user asked to skip the site: closed there, and the site is off-limits
            closing = browser.owned.get(tab)
            if closing is not None:
                with contextlib.suppress(BrowserError, CDPError):  # QA's sandbox may be gone: skipped all the same
                    await browser.close_tab(closing)
            return await self._qa_release("closed")
        mine = await self.browser.tabs("list") if self.browser is not None and self.cdp is not None \
            and not self.cdp.closed else ""
        line = f"  {held.tab_key}  in QA's Docker sandbox: {held.check.site} (bot check: waiting for the user)"
        return "\n".join(part for part in (mine, line) if part)

    # ---- shell and files --------------------------------------------------------------------------------

    async def shell(self, command: str, timeout: int = 60) -> ToolResult:
        async def action(_browser):
            if self.info.chrome:  # the user's own Chrome: only the sandboxed shell, started on first use or if stopped
                if self.sandboxes is None:
                    self.sandboxes = Sandboxes(self.home, mounts=self.catalog.mounts())
                if not self.info.shell or not await asyncio.to_thread(self.sandboxes.is_running, self.info.shell):
                    self.info.shell = await asyncio.to_thread(self.sandboxes.start_shell, self.info.work_host)
            result = await asyncio.to_thread(self.sandboxes.exec, self.info.shell, command,
                                             self.work.sandbox_task, timeout)
            output = result.output
            if len(output) > SHELL_LIMIT:
                self._shell_logs += 1
                path = self.work.write_text(f".shell/{self._shell_logs:03d}.log", output)
                output = (output[:SHELL_LIMIT] +
                          f"\n… [truncated: {len(output) - SHELL_LIMIT} more chars; full output saved to {path}]")
            status = f"timed out after {timeout}s" if result.timed_out else f"exit {result.code}"
            return f"{output.rstrip()}\n[{status}]"
        def refuse() -> str | None:
            problem = shell_problem(command, self.gate.skipped)
            return self.gate.refusal("shell") or (f"⛔ {problem}" if problem else None)
        return await self._with_browser("shell", {"command": command, "timeout": timeout}, action, refuse)

    async def read_file(self, path: str) -> ToolResult:
        async def action(_browser):
            try:
                return self.work.read_text(path, READ_LIMIT)
            except FileNotFoundError:
                raise PathError(f"{path}: no such file in {self.work.sandbox_task}") from None
            except IsADirectoryError:
                raise PathError(f"{path}: is a folder; use shell to list it") from None
        return await self._with_browser("read_file", {"path": path}, action)

    async def write_file(self, path: str, content: str) -> ToolResult:
        async def action(_browser):
            return f"wrote {self.work.write_text(path, content)} ({len(content)} chars)"
        return await self._with_browser("write_file", {"path": path, "content": content}, action)

    # ---- skills -----------------------------------------------------------------------------------------

    async def find_skills(self, query: str = "", limit: int = 10) -> ToolResult:
        async def work():
            if not query.strip():
                return self.catalog.summary()
            skills = self.catalog.find(query, limit)
            if not skills:
                return f'no skills match "{query}"; try other words, or find_skills("") for the full list'
            lines = []
            for skill in skills:
                description = skill.description
                if len(description) > DESCRIPTION_LIMIT:
                    description = description[:DESCRIPTION_LIMIT - 1] + "…"
                lines.append(f"{skill.ref}{' [scripts]' if skill.has_scripts else ''} — {description}")
            return "\n".join(lines + ['load one with load_skill("namespace:name")'])
        return await self._run("find_skills", {"query": query, "limit": limit}, work)

    async def load_skill(self, name: str) -> ToolResult:
        async def work():
            return self.catalog.load(name)
        return await self._run("load_skill", {"name": name}, work)

    async def read_skill_file(self, name: str, path: str) -> ToolResult:
        async def work():
            return self.catalog.read_file(name, path)
        return await self._run("read_skill_file", {"name": name, "path": path}, work)

    # ---- shutdown ---------------------------------------------------------------------------------------

    async def close(self) -> None:
        """End this session: close its tabs; throwaway sandboxes are removed, named ones stay warm."""
        if self._qa_browser is not None:
            await self._close_qa_browser(self._qa_browser)
            self._qa_browser = None
        if self.browser is not None:
            await self._teardown(stop_container=bool(self.info and self.info.fresh))
        if self._link is not None:  # reports from calls that used no browser of the session's (QA's sandbox)
            await self._link.flush()
        if self.live is not None:
            await self.live.stop()
        for asking in self._asking.values():  # a handshake still waiting for an answer ends with the session
            asking.cancel()
            if asking.done() and not asking.cancelled() and asking.exception() is None:
                await asking.result().close()  # allowed after the last call: nobody holds it
        self._asking.clear()
