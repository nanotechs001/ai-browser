"""The app's view of a browser's tabs (BraveLink's, over the relay's one connection): every tab, Watch (bring a tab to
the front), closing an agent's tabs when the user closes the agent, a tab's text for a skill draft, and small
thumbnails of the tabs agents work in. AI Browser's own pages (its origin, http://127.0.0.1:<port>) are never listed:
only its window shows them, and a copy the user opened in Brave is a 403 page, not one of their tabs.

It also knows each page's browser context (its profile, or a private window), the service workers, and the context the
browser used last, for BraveLink's one-profile list; all of it from the target list, never by attaching."""

from __future__ import annotations

import asyncio
import base64
import contextlib
from collections.abc import Callable

from ..cdp import CDP, CDPError

THUMB_WIDTH = 320  # pixels: enough to recognise a page in an AI Home row
THUMB_TIMEOUT = 3  # seconds; a page too busy to draw gets no new thumbnail this time
PAGE_TEXT_LIMIT = 20_000  # characters of a tab's text read for a skill draft
REFRESH = 1.5  # seconds between full reads of the tab list: Chrome reports title changes late or not at all


def _page(info: dict) -> dict:
    return {"target": info["targetId"], "url": info.get("url", ""), "title": info.get("title", ""),
            "context": info.get("browserContextId", "")}


def _worker(info: dict) -> dict:
    return {"url": info.get("url", ""), "context": info.get("browserContextId", "")}


class TabWatch:
    def __init__(self, ws_url: str, hidden_origin: str = "", open_timeout: float = 10, cdp=None):
        self.ws_url = ws_url
        self.hidden_origin = hidden_origin.rstrip("/")
        self.open_timeout = open_timeout
        self._given = cdp  # the relay's in-process client (brave mode): nothing to connect
        self._cdp: CDP | None = None
        self._pages: dict[str, dict] = {}  # target id -> {"target", "url", "title", "context"}, in the order they came
        self._workers: dict[str, dict] = {}  # service-worker target id -> {"url", "context"}: never pages
        self.default_context: str | None = None  # defaultBrowserContextId: the profile the browser used last
        self._callbacks: list[Callable[[list[dict]], None]] = []
        self._notify: asyncio.Task | None = None
        self._poll: asyncio.Task | None = None

    def _hidden(self, url: str) -> bool:
        """AI Browser's own pages (the app's origin) and the new tab page are never anybody's tab."""
        return url.startswith("chrome://newtab") or (bool(self.hidden_origin)
                                                     and url.startswith(self.hidden_origin + "/"))

    async def start(self) -> None:
        self._cdp = self._given if self._given is not None else await CDP.connect(self.ws_url,
                                                                                   open_timeout=self.open_timeout)
        self._cdp.on("Target.targetCreated", self._on_target)
        self._cdp.on("Target.targetInfoChanged", self._on_target)
        self._cdp.on("Target.targetDestroyed", self._on_destroyed)
        await self._cdp.send("Target.setDiscoverTargets", {"discover": True})  # also announces the open ones
        await self._read_default()  # the profile used last (BraveLink's fallback); a failed read leaves None
        self._poll = asyncio.create_task(self._refresh())

    async def close(self) -> None:
        for task in (self._notify, self._poll):
            if task is not None:
                task.cancel()
        if self._cdp is not None:
            await self._cdp.close()

    @property
    def closed(self) -> bool:
        return self._cdp is None or self._cdp.closed

    # ---- the tab list -------------------------------------------------------------------------------------

    def on_change(self, callback: Callable[[list[dict]], None]) -> None:
        """callback(tabs) after tabs open, close or change (at most every 100 ms)."""
        self._callbacks.append(callback)

    def tabs(self) -> list[dict]:
        """The user's and the agents' tabs; AI Browser's own pages (the app's origin) are left out. Each row has
        exactly target, url and title."""
        return [{key: page[key] for key in ("target", "url", "title")} for page in self.pages()]

    def pages(self) -> list[dict]:
        """The same pages as tabs(), each with its browser context (for BraveLink, which never sends it on)."""
        return [dict(page) for page in self._pages.values() if not self._hidden(page["url"])]

    def worker_contexts(self, extension_id: str) -> set[str]:
        """The contexts of that extension's running service workers (a sleeping worker isn't listed)."""
        if not extension_id:
            return set()
        prefix = f"chrome-extension://{extension_id}/"
        return {worker["context"] for worker in self._workers.values()
                if worker["url"].startswith(prefix) and worker["context"]}

    def has_pages(self) -> bool:
        """Whether AI Browser still shows anything at all (a tab, AI Home, the side panel). A worker isn't a page."""
        return bool(self._pages)

    def _on_target(self, params: dict, session: str | None) -> None:
        info = params.get("targetInfo", {})
        if info.get("type") == "page":
            self._pages[info["targetId"]] = _page(info)
            self._changed()
        elif info.get("type") == "service_worker" and self._workers.get(info["targetId"]) != _worker(info):
            self._workers[info["targetId"]] = _worker(info)
            self._changed()

    def _on_destroyed(self, params: dict, session: str | None) -> None:
        target = params.get("targetId")
        page = self._pages.pop(target, None)
        worker = self._workers.pop(target, None)
        if page is not None or worker is not None:
            self._changed()

    async def _read_default(self) -> bool:
        """Read defaultBrowserContextId; True when it changed. A failed read keeps the last value."""
        try:
            answer = await self._cdp.send("Target.getBrowserContexts", timeout=5)
        except CDPError:
            return False
        context = answer.get("defaultBrowserContextId") or None
        if context == self.default_context:
            return False
        self.default_context = context
        return True

    async def _refresh(self) -> None:
        while not self._cdp.closed:
            await asyncio.sleep(REFRESH)
            changed = await self._read_default()
            try:
                infos = (await self._cdp.send("Target.getTargets", timeout=5))["targetInfos"]
            except CDPError:
                if changed:
                    self._changed()
                continue
            pages = {info["targetId"]: _page(info) for info in infos if info.get("type") == "page"}
            workers = {info["targetId"]: _worker(info) for info in infos if info.get("type") == "service_worker"}
            if pages != self._pages:
                self._pages = {**{key: pages[key] for key in self._pages if key in pages}, **pages}  # keep the order
                changed = True
            if workers != self._workers:
                self._workers = workers
                changed = True
            if changed:
                self._changed()

    def _changed(self) -> None:
        if self._notify is None or self._notify.done():
            self._notify = asyncio.ensure_future(self._tell())

    async def _tell(self) -> None:
        await asyncio.sleep(0.1)
        tabs = self.tabs()
        for callback in list(self._callbacks):
            with contextlib.suppress(Exception):
                callback(tabs)

    # ---- actions ------------------------------------------------------------------------------------------

    async def watch(self, target: str) -> None:
        """Bring a tab to the front (an agent's tab the user wants to watch)."""
        with contextlib.suppress(CDPError):
            await self._cdp.send("Target.activateTarget", {"targetId": target})

    async def close_targets(self, targets: list[str]) -> None:
        for target in targets:
            with contextlib.suppress(CDPError):
                await self._cdp.send("Target.closeTarget", {"targetId": target})

    async def page_text(self, target: str, picked: bool = False) -> str:
        """The text one of AI Browser's tabs shows (a page to learn from, for a skill draft), or "" if it can't be
        read quickly."""
        try:
            return await asyncio.wait_for(self._text(target), THUMB_TIMEOUT)
        except (TimeoutError, CDPError, KeyError, ValueError):
            return ""

    async def _text(self, target: str) -> str:
        cdp = self._cdp
        session = (await cdp.send("Target.attachToTarget", {"targetId": target, "flatten": True}))["sessionId"]
        try:
            result = await cdp.send("Runtime.evaluate", {"expression": "document.body ? document.body.innerText : ''",
                                                         "returnByValue": True}, session_id=session)
            return str(result.get("result", {}).get("value") or "")[:PAGE_TEXT_LIMIT]
        finally:
            with contextlib.suppress(CDPError):
                await cdp.send("Target.detachFromTarget", {"sessionId": session})

    async def thumbnail(self, target: str) -> bytes | None:
        """A small JPEG of what the tab shows now, or None if it can't be had quickly."""
        try:
            return await asyncio.wait_for(self._shot(target), THUMB_TIMEOUT)
        except (TimeoutError, CDPError, KeyError, ValueError):
            return None

    async def _shot(self, target: str) -> bytes:
        cdp = self._cdp
        session = (await cdp.send("Target.attachToTarget", {"targetId": target, "flatten": True}))["sessionId"]
        try:
            # A background tab only draws while it thinks it has focus (as the engine's own tabs do).
            await cdp.send("Emulation.setFocusEmulationEnabled", {"enabled": True}, session_id=session)
            metrics = await cdp.send("Page.getLayoutMetrics", session_id=session)
            view = metrics.get("cssVisualViewport") or metrics.get("visualViewport") or {}
            width, height = max(1, view.get("clientWidth", 1280)), max(1, view.get("clientHeight", 800))
            clip = {"x": view.get("pageX", 0), "y": view.get("pageY", 0), "width": width, "height": height,
                    "scale": min(1, THUMB_WIDTH / width)}
            shot = await cdp.send("Page.captureScreenshot", {"format": "jpeg", "quality": 60, "clip": clip},
                                  session_id=session)
            return base64.b64decode(shot["data"])
        finally:
            with contextlib.suppress(CDPError):
                await cdp.send("Target.detachFromTarget", {"sessionId": session})
