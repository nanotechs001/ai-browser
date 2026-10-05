"""The user's Brave as the Brain's reader meets it (BraveLink's gate and its readers), faked: a test lists the tabs
the gate lets through and scripts each reader's answer, and every call is recorded. Nothing runs in a page."""

from __future__ import annotations

import asyncio

from fake_brave import FakeBrave

GMAIL = "https://mail.google.com/mail/u/0/#inbox"


def row(raw_id, **fields):
    """One row as a reader answers it."""
    return {"id": raw_id, "from": "Maria", "subject": "Launch", "snippet": "Can we move it to Monday?",
            "url": f"https://mail.google.com/mail/u/0/#all/{raw_id}", "time": "10:02", "unread": True,
            "from_me": False, **fields}


class ReadingBrave(FakeBrave):
    """`listed`: what brain_tabs() lists while reading is on and Brave is connected ([{"target", "url", "site"}]).
    `answers`: (target, call name) -> an answer, a function of the call's arguments, or an Exception to raise.
    `hold`: while set to an Event, a read waits for it (a read under way)."""

    def __init__(self, listed=(), state="connected"):
        super().__init__([], state=state)
        self.listed = [dict(tab) for tab in listed]
        self.answers: dict = {}
        self.calls: list[tuple] = []  # (target, purpose, name, args)
        self.hold: asyncio.Event | None = None
        self.brain_reading = lambda: True  # the server sets its own (Settings → Brain's switch)

    def brain_tabs(self):
        if self.state != "connected" or not self.brain_reading():
            return []
        return [dict(tab) for tab in self.listed]

    def may_run(self, target, purpose):
        return purpose in ("brain", "pick") and any(tab["target"] == target for tab in self.brain_tabs())

    async def run_reader(self, target, purpose, name, *args, timeout=10):
        from ai_browser.app.inworld import WorldError

        self.calls.append((target, purpose, name, args))
        if not self.may_run(target, purpose):
            raise WorldError("AI Browser doesn't read that tab")
        if self.hold is not None:
            await self.hold.wait()
        answer = self.answers.get((target, name))
        if isinstance(answer, Exception):
            raise answer
        return answer(*args) if callable(answer) else answer

    def reads(self, name="read"):
        return [call for call in self.calls if call[2] == name]
