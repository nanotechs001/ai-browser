"""Minimal async Chrome DevTools Protocol client over one websocket."""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
from collections.abc import Callable

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

log = logging.getLogger(__name__)

Handler = Callable[[dict, str | None], None]


class CDPError(RuntimeError):
    def __init__(self, message: str, code: int = 0, method: str = ""):
        super().__init__(message)
        self.code = code
        self.method = method


class CDP:
    def __init__(self, ws):
        self._ws = ws
        self._ids = itertools.count(1)
        self._pending: dict[int, tuple[asyncio.Future, str]] = {}
        self._handlers: dict[str, list[Handler]] = {}
        self._closed = False
        self._reader = asyncio.create_task(self._read())

    @classmethod
    async def connect(cls, ws_url: str, open_timeout: float = 10, headers: dict[str, str] | None = None) -> "CDP":
        """`headers` go with the handshake (the relay's X-AIB-Agent-Token); no Origin is sent. proxy=None: every
        address given here is on this computer, and a token in a header must never pass through a proxy."""
        ws = await connect(ws_url, max_size=None, ping_interval=None, open_timeout=open_timeout,
                           additional_headers=headers, proxy=None)
        return cls(ws)

    @property
    def closed(self) -> bool:
        return self._closed

    async def send(self, method: str, params: dict | None = None, session_id: str | None = None,
                   timeout: float = 30) -> dict:
        if self._closed:
            raise CDPError("connection closed", method=method)
        message_id = next(self._ids)
        message = {"id": message_id, "method": method, "params": params or {}}
        if session_id:
            message["sessionId"] = session_id
        future = asyncio.get_running_loop().create_future()
        self._pending[message_id] = (future, method)
        try:
            await self._ws.send(json.dumps(message))
            return await asyncio.wait_for(future, timeout)
        except ConnectionClosed:
            self._closed = True
            raise CDPError("connection closed", method=method) from None
        except TimeoutError:
            raise CDPError(f"{method} timed out after {timeout:g}s", code=-1, method=method) from None
        finally:
            self._pending.pop(message_id, None)

    def on(self, method: str, handler: Handler) -> None:
        self._handlers.setdefault(method, []).append(handler)

    def off(self, method: str, handler: Handler) -> None:
        handlers = self._handlers.get(method, [])
        if handler in handlers:
            handlers.remove(handler)

    async def wait_for(self, method: str, predicate: Callable[[dict], bool] | None = None,
                       session_id: str | None = None, timeout: float = 10) -> dict:
        future = asyncio.get_running_loop().create_future()

        def handler(params: dict, sid: str | None) -> None:
            if session_id is not None and sid != session_id:
                return
            if predicate is not None and not predicate(params):
                return
            if not future.done():
                future.set_result(params)

        self.on(method, handler)
        try:
            return await asyncio.wait_for(future, timeout)
        finally:
            self.off(method, handler)

    async def _read(self) -> None:
        try:
            async for raw in self._ws:
                self._dispatch(json.loads(raw))
        except ConnectionClosed:
            pass
        finally:
            self._closed = True
            self._fail_pending()

    def _dispatch(self, message: dict) -> None:
        """One message from the browser: an answer settles its command, an event goes to its handlers."""
        if "id" in message:
            entry = self._pending.get(message["id"])
            if entry is None or entry[0].done():
                return
            future, method = entry
            if "error" in message:
                error = message["error"]
                future.set_exception(CDPError(f"{method}: {error.get('message')}", error.get("code", 0), method))
            else:
                future.set_result(message.get("result", {}))
            return
        for handler in list(self._handlers.get(message.get("method"), ())):
            try:
                handler(message.get("params", {}), message.get("sessionId"))
            except Exception:  # a broken handler must not stop the reader
                log.exception("CDP event handler failed for %s", message.get("method"))

    def _fail_pending(self) -> None:
        for future, method in list(self._pending.values()):
            if not future.done():
                future.set_exception(CDPError("connection closed", method=method))

    async def close(self) -> None:
        self._closed = True
        await self._ws.close()
        try:
            await self._reader
        except Exception:
            pass
        self._fail_pending()
