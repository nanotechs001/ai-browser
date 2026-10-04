"""Stand-ins for AI Browser's window in run_app's tests: AppWindow's surface (id, name, note, launch(url) and
close() -> str). FakeWindow opens the start address in a test's throwaway headless Chrome, the way the real window
opens it. SocketWindow opens no browser at all, only a socket with the window's cookie, as AI Home's page would."""

from __future__ import annotations

import contextlib
import json

from ai_browser.cdp import CDPError
from ui_socket import ui_socket


class FakeWindow:
    id, name = "chrome", "Google Chrome"

    def __init__(self, cdp, note: str = "", close_note: str = ""):
        self.cdp, self.note, self.close_note = cdp, note, close_note
        self.urls: list[str] = []
        self.targets: list[str] = []
        self.closed = False
        self.on_close = None  # a test's recorder, called first

    async def launch(self, url: str) -> None:
        self.urls.append(url)
        self.targets.append((await self.cdp.send("Target.createTarget", {"url": url}))["targetId"])

    async def close(self) -> str:
        if self.on_close is not None:
            self.on_close()
        for target in self.targets:
            with contextlib.suppress(CDPError):
                await self.cdp.send("Target.closeTarget", {"targetId": target})
        self.closed = True
        return self.close_note

    async def page(self, index: int = 0):
        """js(expression) in the window's page (its index-th launch), with .cdp and .session for click_as_user."""
        session = (await self.cdp.send("Target.attachToTarget", {"targetId": self.targets[index],
                                                                  "flatten": True}))["sessionId"]

        async def js(expression):
            result = await self.cdp.send("Runtime.evaluate", {"expression": expression, "returnByValue": True,
                                                              "awaitPromise": True}, session_id=session)
            return result.get("result", {}).get("value")

        js.cdp, js.session = self.cdp, session
        return js


class SocketWindow:
    id, name = "chrome", "Google Chrome"

    def __init__(self, servers: list, note: str = "", close_note: str = ""):
        self.servers, self.note, self.close_note = servers, note, close_note  # servers: the `servers` fixture's list
        self.ws = None
        self.urls: list[str] = []
        self.closed = False

    async def launch(self, url: str) -> None:
        self.urls.append(url)
        server = self.servers[-1]
        self.ws = await ui_socket(server, server.url)
        await self.ws.send(json.dumps({"type": "hello", "view": "home"}))

    async def close(self) -> str:
        self.closed = True
        if self.ws is not None:
            await self.ws.close()
        return self.close_note
