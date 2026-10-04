"""AI Browser's own app, faked, for the engine's tests (app/server.py, app/run.py and the pages). It has
DesktopWindow's surface (desktop/launch.py), with no process behind it. It records what the engine sends and
answers a shortcut as told. says() sends what the real app sends unasked, and quits() is its Quit. With `servers`
(test_app_run's fixture), its launch opens a socket with the window's cookie, as the app's page would."""

from __future__ import annotations

import asyncio
import json

from ui_socket import ui_socket


class FakeDesktop:
    id, name = "desktop", "AI Browser"

    def __init__(self, answers=None, launch_error=None, servers=None, note: str = ""):
        self.answers = dict(answers or {})  # a shortcut's value -> {"ok", "why"}; any other: ok
        self.launch_error = launch_error
        self.servers = servers
        self.note = note
        self.sent: list[dict] = []
        self.tried: list = []
        self.launched: list[str] = []
        self.shortcut = {"value": None, "ok": None, "why": "", "pressed": False}
        self.on_message = None
        self.ended = asyncio.Event()
        self.quit_by_user = False
        self.closed = False
        self.ws = None

    async def launch(self, url: str) -> None:
        self.launched.append(url)
        if self.launch_error is not None:
            raise self.launch_error
        if self.servers:
            server = self.servers[-1]
            self.ws = await ui_socket(server, server.url)
            await self.ws.send(json.dumps({"type": "hello", "view": "home"}))

    async def close(self) -> str:
        self.closed = True
        if self.ws is not None:
            await self.ws.close()
        self.ended.set()
        return ""

    def send(self, message: dict) -> bool:
        self.sent.append(message)
        return not self.ended.is_set()

    async def try_shortcut(self, value):
        self.tried.append(value)
        answer = {"value": value, "pressed": False, **self.answers.get(value, {"ok": True, "why": ""})}
        if answer["ok"]:
            self.shortcut = answer
        return answer

    def says(self, message: dict) -> None:
        """What the real app sends unasked: a shortcut's state as it starts or is pressed, or a click."""
        if message.get("type") == "shortcut":
            self.shortcut = {key: message.get(key) for key in ("value", "ok", "why", "pressed")}
        self.on_message(message)

    def quits(self, by_user: bool = True) -> None:
        self.quit_by_user = by_user
        self.ended.set()
