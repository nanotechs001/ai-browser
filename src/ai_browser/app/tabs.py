"""The app's own view of AI Browser: every tab, Watch (bring a tab to the front), closing an agent's tabs when the user
closes the agent, and small thumbnails of the tabs agents work in. One CDP connection, apart from the agents' own."""

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


class TabWatch:
    def __init__(self, ws_url: str, extension_id: str):
        self.ws_url = ws_url
        self.extension_id = extension_id
        self._cdp: CDP | None = None
        self._pages: dict[str, dict] = {}  # target id -> {"target", "url", "title"}, in the order they appeared
        self._callbacks: list[Callable[[list[dict]], None]] = []
        self._notify: asyncio.Task | None = None
        self._poll: asyncio.Task | None = None

    async def start(self) -> None:
        self._cdp = await CDP.connect(self.ws_url)
        self._cdp.on("Target.targetCreated", self._on_target)
        self._cdp.on("Target.targetInfoChanged", self._on_target)
        self._cdp.on("Target.targetDestroyed", self._on_destroyed)
        await self._cdp.send("Target.setDiscoverTargets", {"discover": True})  # also announces the open ones
        self._poll = asyncio.create_task(self._refresh())

    async def close(self) -> None:
        for task in (self._notify, self._poll):
            if task is not None:
                task.cancel()
        if self._cdp is not None:
            await self._cdp.close()

    # ---- the tab list -------------------------------------------------------------------------------------

    def on_change(self, callback: Callable[[list[dict]], None]) -> None:
        """callback(tabs) after tabs open, close or change (at most every 100 ms)."""
        self._callbacks.append(callback)

    def tabs(self) -> list[dict]:
        """The user's and the agents' tabs; AI Browser's own pages (AI Home, the panel) are left out."""
        own = f"chrome-extension://{self.extension_id}/"
        return [dict(page) for page in self._pages.values()
                if not page["url"].startswith(own) and not page["url"].startswith("chrome://newtab")]

    def has_pages(self) -> bool:
        """Whether AI Browser still shows anything at all (a tab, AI Home, the side panel)."""
        return bool(self._pages)

    def _on_target(self, params: dict, session: str | None) -> None:
        info = params.get("targetInfo", {})
        if info.get("type") == "page":
            self._pages[info["targetId"]] = {"target": info["targetId"], "url": info.get("url", ""),
                                             "title": info.get("title", "")}
            self._changed()

    def _on_destroyed(self, params: dict, session: str | None) -> None:
        if self._pages.pop(params.get("targetId"), None) is not None:
            self._changed()

    async def _refresh(self) -> None:
        while not self._cdp.closed:
            await asyncio.sleep(REFRESH)
            try:
                infos = (await self._cdp.send("Target.getTargets", timeout=5))["targetInfos"]
            except CDPError:
                continue
            pages = {info["targetId"]: {"target": info["targetId"], "url": info.get("url", ""),
                                        "title": info.get("title", "")} for info in infos if info.get("type") == "page"}
            if pages != self._pages:
                self._pages = {**{key: pages[key] for key in self._pages if key in pages}, **pages}  # keep the order
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

    async def page_text(self, target: str) -> str:
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
