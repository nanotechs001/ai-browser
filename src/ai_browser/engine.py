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

from . import config
from .agentlink import AgentLink
from .browser import Browser, BrowserError
from .cdp import CDP, CDPError
from .appbrowser import app_profile
from .chrome import ChromeError, default_chrome_dir, find_ws_url
from .config import READ_LIMIT, SHELL_LIMIT, load_config, project_root
from .live import LiveView
from .qa import run_qa
from .sandbox import SandboxInfo, Sandboxes
from .skills import Catalog
from .steps import parse_steps
from .tasklog import TaskLog, new_task_id
from .workfs import PathError, WorkDir

DESCRIPTION_LIMIT = 160
CHROME_ALLOW_WAIT = 60  # seconds to wait for the user to click "Allow" in Chrome
RECONNECTED = {"chrome": "(reconnected to your Chrome: earlier tabs and element ids from this session are gone)\n",
               "app": "(reconnected to AI Browser: earlier tabs and element ids from this session are gone)\n"}
_KNOWN_ERRORS = {"ChromeError", "DockerError", "StepError", "PathError", "SkillNotFound", "AmbiguousSkill", "CDPError",
                 "BrowserError", "JSError", "StepStale", "StepBlocked", "ValueError"}


@dataclass
class ToolResult:
    text: str
    images: list[bytes] = field(default_factory=list)


def _message(exc: BaseException) -> str:
    text = str(exc) or type(exc).__name__
    return text if type(exc).__name__ in _KNOWN_ERRORS else f"{type(exc).__name__}: {text}"


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _clean(text: str) -> str:
    """Replace lone UTF-16 surrogates (half an emoji) so tool text is always valid UTF-8."""
    return re.sub("[\ud800-\udfff]", "�", text)


def _outcome(text: str) -> str:
    lines = text.splitlines()
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
        self.default_chrome = os.environ.get("AIB_BROWSER", "").lower() == "chrome"  # the user's own Chrome
        self.default_app = os.environ.get("AIB_BROWSER", "").lower() == "app"  # AI Browser (ai-browser app)
        self._wanted: tuple[str, bool, str] | None = None  # (profile, fresh, sandbox|chrome|app) from sandbox_start
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

    @property
    def catalog(self) -> Catalog:
        if self._catalog is None:
            self._catalog = Catalog.discover(
                Path.home() / ".claude",
                Path.home() / "Library" / "Application Support" / "Claude",
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
            browser = Browser(cdp, work, self.cfg)
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
        """Connect to the user's own running Chrome (they allowed remote debugging and click Allow), or in app mode
        to AI Browser, the agent's own Chrome started by `ai-browser app`."""
        if mode == "app":
            try:
                ws_url = await asyncio.to_thread(find_ws_url, self._app_profile(), 2)
            except ChromeError:
                raise ChromeError("AI Browser isn't open: start it with `uv run ai-browser app`") from None
        else:
            ws_url = await asyncio.to_thread(find_ws_url, default_chrome_dir(), 2)
        try:
            cdp = await CDP.connect(ws_url, open_timeout=CHROME_ALLOW_WAIT)
        except Exception as exc:
            raise ChromeError(f"Chrome didn't accept the connection ({type(exc).__name__}): when Chrome asks "
                              "\"Allow remote debugging?\", click Allow, then try again") from None
        work_host = self.home / "sandboxes" / "chrome" / "work"  # shared with the shell container of both modes
        work = WorkDir(work_host, self.task_id)
        agent = os.environ.get("AIB_APP_AGENT", "") if mode == "app" else ""
        adopt = os.environ.get("AIB_APP_ADOPT", "") if mode == "app" else ""
        try:
            # An agent started from AI Home works in background tabs; one started in the user's tab works in front.
            browser = Browser(cdp, work, self.cfg, mode=mode,
                              hidden_extension=os.environ.get("AIB_APP_EXTENSION", "") if mode == "app" else "",
                              front=bool(adopt) or not agent)
            if agent and os.environ.get("AIB_APP_EVENTS"):
                link = self._link = self._link or AgentLink(os.environ["AIB_APP_EVENTS"],
                                                             os.environ.get("AIB_APP_AGENT_TOKEN", ""), agent)
                browser.on_tab_event(lambda kind, tab: link.report(f"tab_{kind}", tab.target, tab.adopted))
                browser.on_tab_change(lambda tab: link.report("working_tab", tab.target, tab.adopted))
            await browser.start()
            if adopt and not self._adopted_start:  # once: the tab the user started this agent in
                self._adopted_start = True
                with contextlib.suppress(BrowserError, CDPError):
                    await browser.adopt(adopt)
        except BaseException:
            await cdp.close()
            raise
        self.info = SandboxInfo(f"aib-{mode}", mode, "", work_host, False, False, chrome=True)
        self.work, self.cdp, self.browser = work, cdp, browser
        if mode != "app":  # in AI Browser the app, not the next session, cleans up after a session
            await self._close_orphans()
            self._register()
        if mode == "chrome":  # AI Browser is in plain sight: no live view needed
            await self._attach_live()

    def _app_profile(self) -> Path:
        return Path(os.environ.get("AIB_APP_PROFILE") or app_profile(self.home)).expanduser()

    def _default_kind(self) -> str:
        return "app" if self.default_app else "chrome" if self.default_chrome else "sandbox"

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
        if self.info is None or self.info.fresh or self.browser is None or self.browser.mode == "app":
            return
        try:
            folder = self._sessions_dir()
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{self.task_id}.json").write_text(
                json.dumps({"pid": os.getpid(), "targets": self.browser.owned_targets()}))
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
                data = json.loads(record.read_text())
            except (OSError, ValueError):
                data = {"pid": 0, "targets": []}
            if _alive(int(data.get("pid", 0))):
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
                return RECONNECTED[kind] if connected_before else ""
            await self._start(profile, fresh)
            return ""
        if self.cdp.closed and self.info.chrome:  # the user's Chrome (or AI Browser) was closed or restarted
            kind = self.browser.mode
            stale = [tab.target for tab in self.browser.owned.values() if not tab.adopted]
            await self._teardown(stop_container=False)
            await self._start_chrome(kind)
            for target in stale:  # still open when only the connection dropped
                with contextlib.suppress(CDPError):
                    await self.cdp.send("Target.closeTarget", {"targetId": target})
            return RECONNECTED[kind]
        if self.cdp.closed:  # Chromium or its container died
            profile, fresh = self.info.profile, self.info.fresh
            await self._teardown(stop_container=fresh)  # a throwaway pair is replaced whole (no stray shell)
            await self._start(self.default_profile if fresh else profile, fresh)
            return "(sandbox restarted: the browser had stopped, so earlier pages and element ids are gone)\n"
        return await self.browser.ensure_tab()  # the user, its window or the page may have closed our tab

    async def _with_browser(self, tool: str, args: dict, action) -> ToolResult:
        async def work():
            note = await self._ready()
            try:
                result = await action(self.browser)
            finally:
                self._register()  # tabs may have been opened or closed
            if isinstance(result, ToolResult):
                result.text = note + result.text
                return result
            return note + result
        return await self._run(tool, args, work)

    def _status_text(self) -> str:
        info = self.info
        live = self.live.url if self.live is not None and self.live.url else "not started"
        if info.chrome and info.profile == "app":
            return ("browser: AI Browser (the agent's own Chrome) · tabs list also shows the user's tabs there\n"
                    f"work folder {self.work.sandbox_task} (on this Mac: {self.work.host_task}; shell and skill "
                    "scripts run in a Docker sandbox)")
        if info.chrome:
            return ("browser: your own Chrome · only tabs this session opens are used\n"
                    f"work folder {self.work.sandbox_task} (on this Mac: {self.work.host_task}; shell and skill "
                    "scripts run in a Docker sandbox)\n"
                    f"live view: {live}")
        return (f"sandbox {info.name} ready · profile {info.profile}{' (throwaway)' if info.fresh else ''}\n"
                f"work folder {self.work.sandbox_task} (on this Mac: {self.work.host_task})\n"
                f"live view: {live}")

    # ---- sandbox tools --------------------------------------------------------------------------------

    async def sandbox_start(self, profile: str = "default", fresh: bool = False, chrome: bool = False) -> ToolResult:
        async def work():
            # In AI Browser (AIB_BROWSER=app) a plain sandbox_start() keeps using it.
            kind = "chrome" if chrome else "app" if self.default_app and not fresh and profile == "default" \
                else "sandbox"
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
            return self._status_text()
        return await self._run("sandbox_start", {"profile": profile, "fresh": fresh, "chrome": chrome}, work)

    async def sandbox_stop(self) -> ToolResult:
        async def work():
            if self.info is None or self.browser is None:
                return "no sandbox is running in this session"
            name, profile, fresh = self.info.name, self.info.profile, self.info.fresh
            self._wanted = None  # the next browser call starts the default again
            if self.info.chrome:
                where = "AI Browser" if self.info.profile == "app" else "your Chrome"
                await self._teardown(stop_container=False)  # the shell stays up for other sessions of this home
                self.info = None
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
            return self._status_text() + "\ntabs:\n" + await self.browser.tabs("list")
        return await self._run("sandbox_status", {}, work)

    # ---- browser tools --------------------------------------------------------------------------------

    async def open(self, url: str, new_tab: bool = False) -> ToolResult:
        return await self._with_browser("open", {"url": url, "new_tab": new_tab},
                                        lambda browser: browser.open(url, new_tab))

    async def observe(self, find: str | None = None) -> ToolResult:
        return await self._with_browser("observe", {"find": find}, lambda browser: browser.observe(find))

    async def act(self, steps: list[str], confirmed: bool = False) -> ToolResult:
        args = {"steps": steps, "confirmed": confirmed}
        try:
            parsed = parse_steps(steps)  # report grammar mistakes before touching the sandbox
        except ValueError as exc:
            return await self._run("act", args, lambda: _raise(exc))
        return await self._with_browser("act", args, lambda browser: browser.act(parsed, confirmed))

    async def screenshot(self, size: str = "desktop", full_page: bool = False,
                         element: str | None = None) -> ToolResult:
        async def action(browser):
            shots = await browser.screenshot(size, full_page, element)
            lines = []
            for shot in shots:
                path = self.log.save_shot(shot.data, f"{shot.label}{'-' + element if element else ''}")
                lines.append(f"{shot.label} {shot.width}×{shot.height} saved {path}")
            return ToolResult("\n".join(lines), [shot.data for shot in shots])
        return await self._with_browser("screenshot", {"size": size, "full_page": full_page, "element": element},
                                        action)

    async def tabs(self, action: str = "list", tab: str | None = None, url: str | None = None) -> ToolResult:
        return await self._with_browser("tabs", {"action": action, "tab": tab, "url": url},
                                        lambda browser: browser.tabs(action, tab, url))

    async def page_log(self) -> ToolResult:
        return await self._with_browser("page_log", {}, lambda browser: browser.page_log())

    async def extract(self, kind: str) -> ToolResult:
        return await self._with_browser("extract", {"kind": kind}, lambda browser: browser.extract(kind))

    async def js(self, code: str) -> ToolResult:
        return await self._with_browser("js", {"code": code}, lambda browser: browser.js(code))

    async def qa(self, url: str, max_pages: int = 30, progress=None) -> ToolResult:
        """Website QA of a whole site in this session's browser; returns the summary (the report is in the work folder)."""
        async def action(browser):
            return await run_qa(browser, self.work, url, max_pages, progress=progress, on_tabs=self._register)
        return await self._with_browser("qa", {"url": url, "max_pages": max_pages}, action)

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
        return await self._with_browser("shell", {"command": command, "timeout": timeout}, action)

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
        if self.browser is not None:
            await self._teardown(stop_container=bool(self.info and self.info.fresh))
        if self.live is not None:
            await self.live.stop()
