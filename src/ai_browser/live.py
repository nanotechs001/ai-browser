"""Live view: watch the sandbox browser and take over mouse and keyboard (for logins). Viewer input is never logged."""

from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
import socket
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from .browser import Browser, Tab
from .cdp import CDPError
from .config import LIVE_PORTS

PAGE = Path(__file__).with_name("static").joinpath("live.html")
_MOUSE = {"down": "mousePressed", "up": "mouseReleased", "move": "mouseMoved"}


class _QuietServer(uvicorn.Server):
    """uvicorn without its own signal handling, so it can live inside the MCP server's event loop."""

    @contextlib.contextmanager
    def capture_signals(self):
        yield

    def install_signal_handlers(self) -> None:  # older uvicorn versions
        pass


def _bind(host: str, port: int) -> socket.socket | None:
    """Bind the port ourselves (no probe-then-bind race); None when it is taken."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError:
        sock.close()
        return None
    return sock


async def _serve(server: uvicorn.Server, sock: socket.socket) -> None:
    try:
        await server.serve(sockets=[sock])
    except (SystemExit, Exception):  # uvicorn exits on fatal startup errors; never let that end the MCP server
        pass


class LiveView:
    def __init__(self, host: str = "127.0.0.1", ports: range = LIVE_PORTS):
        self.host = host
        self.ports = ports
        self.token = secrets.token_urlsafe(16)
        self.url: str | None = None
        self.browser: Browser | None = None
        self.viewers: set[WebSocket] = set()
        self._session: str | None = None  # tab session currently being screencast
        self._server: _QuietServer | None = None
        self._task: asyncio.Task | None = None

    @property
    def streaming(self) -> bool:
        return self._session is not None

    async def start(self) -> str:
        app = Starlette(routes=[Route("/live", self._page), WebSocketRoute("/live/ws", self._socket)])
        for port in self.ports:
            sock = _bind(self.host, port)
            if sock is None:
                continue
            self._server = _QuietServer(uvicorn.Config(app, host=self.host, port=port, log_level="warning",
                                                       access_log=False, lifespan="off"))
            self._task = asyncio.create_task(_serve(self._server, sock))
            for _ in range(200):
                if self._server.started or self._task.done():
                    break
                await asyncio.sleep(0.01)
            if self._server.started:
                self.url = f"http://{self.host}:{port}/live?token={self.token}"
                return self.url
            sock.close()
        self._server = self._task = None
        raise RuntimeError(f"no free port for the live view ({self.ports.start}-{self.ports.stop - 1})")

    async def stop(self) -> None:
        await self.detach()
        for viewer in list(self.viewers):
            with contextlib.suppress(Exception):
                await viewer.close()
        if self._server is not None:
            self._server.should_exit = True
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._task, timeout=5)
        self._server = self._task = None
        self.url = None

    async def attach(self, browser: Browser) -> None:
        await self.detach()
        self.browser = browser
        browser.cdp.on("Page.screencastFrame", self._on_frame)
        browser.on_tab_change(self._on_tab_change)
        if self.viewers:
            await self._ensure_streaming()

    async def detach(self) -> None:
        await self._stop_streaming()
        if self.browser is not None:
            self.browser.cdp.off("Page.screencastFrame", self._on_frame)
        self.browser = None

    # ---- HTTP + websocket ------------------------------------------------------------------------

    async def _page(self, request: Request):
        if request.query_params.get("token") != self.token:
            return PlainTextResponse("forbidden", status_code=403)
        return HTMLResponse(PAGE.read_text())

    async def _socket(self, ws: WebSocket) -> None:
        if ws.query_params.get("token") != self.token:
            await ws.close(code=4403)
            return
        await ws.accept()
        self.viewers.add(ws)
        try:
            await self._ensure_streaming()
            while True:
                await self._input(await ws.receive_json())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            self.viewers.discard(ws)
            if not self.viewers:
                await self._stop_streaming()

    # ---- screencast ----------------------------------------------------------------------------

    async def _ensure_streaming(self) -> None:
        browser = self.browser
        if browser is None or browser.session_id is None or self._session == browser.session_id:
            return
        await self._stop_streaming()
        self._session = browser.session_id
        await browser.cdp.send("Page.startScreencast", {
            "format": "jpeg", "quality": 60, "maxWidth": 1440, "maxHeight": 1440, "everyNthFrame": 1},
            session_id=self._session)

    async def _stop_streaming(self) -> None:
        session, self._session = self._session, None
        if session and self.browser is not None and not self.browser.cdp.closed:
            with contextlib.suppress(CDPError):
                await self.browser.cdp.send("Page.stopScreencast", session_id=session)

    def _on_tab_change(self, tab: Tab) -> None:
        if self.viewers:
            asyncio.ensure_future(self._ensure_streaming())

    def _on_frame(self, params: dict, session: str | None) -> None:
        if session != self._session or self.browser is None:
            return
        asyncio.ensure_future(self._forward(params, session))

    async def _forward(self, params: dict, session: str) -> None:
        with contextlib.suppress(CDPError):
            await self.browser.cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]},
                                        session_id=session)
        meta = params.get("metadata", {})
        message = json.dumps({"t": "frame", "data": params["data"],
                              "w": round(meta.get("deviceWidth", 0)), "h": round(meta.get("deviceHeight", 0))})
        for viewer in list(self.viewers):
            try:
                await viewer.send_text(message)
            except Exception:
                self.viewers.discard(viewer)

    # ---- viewer input (never logged) -------------------------------------------------------------

    async def _input(self, message: dict) -> None:
        if self.browser is None or self._session is None:
            return

        def send(method: str, params: dict):
            return self.browser.cdp.send(method, params, session_id=self._session)

        kind = message.get("t")
        if kind == "mouse" and message.get("e") in _MOUSE:
            params = {"type": _MOUSE[message["e"]], "x": message["x"], "y": message["y"],
                      "modifiers": message.get("mod", 0)}
            if message["e"] == "move":
                params.update(buttons=message.get("buttons", 0), button="left" if message.get("buttons") else "none")
            else:
                params.update(button=message.get("b", "left"), clickCount=message.get("c", 1),
                              buttons=1 if message["e"] == "down" else 0)
            await send("Input.dispatchMouseEvent", params)
        elif kind == "wheel":
            await send("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": message["x"], "y": message["y"],
                                                    "deltaX": message.get("dx", 0), "deltaY": message.get("dy", 0)})
        elif kind == "key" and message.get("e") in {"down", "up"}:
            down = message["e"] == "down"
            params = {"type": ("keyDown" if message.get("text") else "rawKeyDown") if down else "keyUp",
                      "key": message.get("key", ""), "code": message.get("code", ""),
                      "windowsVirtualKeyCode": message.get("kc", 0), "nativeVirtualKeyCode": message.get("kc", 0),
                      "modifiers": message.get("mod", 0)}
            if down and message.get("text"):
                params["text"] = message["text"]
            await send("Input.dispatchKeyEvent", params)
        elif kind == "text" and message.get("text"):
            await send("Input.insertText", {"text": message["text"]})
