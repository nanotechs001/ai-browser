"""The Brain's kept chats: Mission Control's chat panel, the last 50 (the chat-panel spec, 4 and 5).

One file per chat, <home>/brain/chats/<id>.json, mode 0600 because it holds the user's words and the Brain's answers:
its id, its title (the user's first words, one line, at most 60 characters), when it was made and last updated (ISO
8601, UTC), and its exchanges, at most 200: said, answer, time, and the card an answer showed, kept as text (its kind
and how it ended, never its words or its buttons). Only the app writes them, and only for chat ids it made itself
(new()); the inbox's talks and the floating chat are never kept. Saving a 51st chat drops the least recently updated.
A file that can't be read, or isn't a chat, is skipped; a folder that can't be written leaves the talk going, unkept."""

from __future__ import annotations

import contextlib
import json
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path

from ..syncdir import write_atomic

KEEP_CHATS = 50  # chats kept: a 51st drops the least recently updated
KEEP_EXCHANGES = 200  # exchanges kept per chat: the newest
TITLE_LIMIT = 60  # characters of a chat's title
OUTCOME_LIMIT = 200  # characters of how a card ended
CARD_CANCELLED = "Cancelled"  # a proposal card's Cancel, or a plain no
CHAT_ID = re.compile(r"^c[0-9a-f]{16}$")  # within the app's talk ids (^[A-Za-z0-9-]{1,40}$), and a safe file name


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _line(text, limit: int) -> str:
    """`text` on one line, at most `limit` characters: an ellipsis ends a longer one."""
    line = " ".join(str(text).split())
    return line if len(line) <= limit else line[:limit - 1].rstrip() + "…"


def _text(value) -> str:
    return value if isinstance(value, str) else ""


def _card(value) -> dict | None:
    if not isinstance(value, dict) or not isinstance(value.get("id"), str) or not isinstance(value.get("kind"), str):
        return None
    outcome = value.get("outcome")
    return {"id": value["id"], "kind": value["kind"], "outcome": outcome if isinstance(outcome, str) else None}


def _clean(data, chat_id: str) -> dict | None:
    """A chat as read from its file, with only the fields and types this module writes; None if it isn't one."""
    if not isinstance(data, dict) or data.get("id") != chat_id or not isinstance(data.get("exchanges"), list):
        return None
    exchanges = []
    for one in data["exchanges"][-KEEP_EXCHANGES:]:
        if not isinstance(one, dict):
            continue
        exchange = {"said": _text(one.get("said")), "answer": _text(one.get("answer")), "time": _text(one.get("time"))}
        card = _card(one.get("card"))
        if card is not None:
            exchange["card"] = card
        exchanges.append(exchange)
    return {"id": chat_id, "title": _line(_text(data.get("title")), TITLE_LIMIT), "created": _text(data.get("created")),
            "updated": _text(data.get("updated")), "exchanges": exchanges}


class Chats:
    def __init__(self, home, clock=_now):
        self.folder = Path(home) / "brain" / "chats"
        self.clock = clock
        self._made: set[str] = set()  # ids this run made that have no file yet (an empty chat is never written)
        self._cards: dict[str, str] = {}  # this run's open cards: id -> its chat (a restart ends them all)

    def _path(self, chat_id: str) -> Path:
        return self.folder / f"{chat_id}.json"

    def new(self) -> str:
        """A new chat's id, for the panel's New chat: kept from its first exchange on."""
        chat_id = f"c{secrets.token_hex(8)}"
        self._made.add(chat_id)
        return chat_id

    def kept(self, chat_id) -> bool:
        """Whether this talk id is a kept chat: one the app made this run, or one with a file."""
        if not isinstance(chat_id, str) or not CHAT_ID.fullmatch(chat_id):
            return False
        return chat_id in self._made or self._path(chat_id).is_file()

    def get(self, chat_id) -> dict | None:
        if not isinstance(chat_id, str) or not CHAT_ID.fullmatch(chat_id):
            return None
        try:
            data = json.loads(self._path(chat_id).read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            return None
        return _clean(data, chat_id)

    def list(self) -> list[dict]:
        """The kept chats, the most recently updated first: id, title, when it was last updated, and how many
        exchanges it has (never their words)."""
        try:
            paths = sorted(self.folder.glob("c*.json"))
        except OSError:
            return []
        rows = []
        for path in paths:
            chat = self.get(path.stem)
            if chat is not None:
                rows.append({"id": chat["id"], "title": chat["title"], "updated": chat["updated"],
                             "count": len(chat["exchanges"])})
        return sorted(rows, key=lambda row: row["updated"], reverse=True)

    def last(self, chat_id, count: int) -> list[tuple[str, str]]:
        """Its last `count` exchanges, as the Brain remembers a talk: (said, answer)."""
        chat = self.get(chat_id)
        return [(one["said"], one["answer"]) for one in chat["exchanges"][-count:]] if chat and count > 0 else []

    def add(self, chat_id, said: str, answer: str) -> None:
        """One exchange of a kept chat, as the Brain remembers it (talk.py's Talks.on_add). Any other talk is not
        kept."""
        if not self.kept(chat_id):
            return
        now = self.clock()
        chat = self.get(chat_id) or {"id": chat_id, "title": "", "created": now, "updated": now, "exchanges": []}
        if not chat["title"]:
            chat["title"] = _line(said, TITLE_LIMIT)
        chat["exchanges"] = [*chat["exchanges"],
                             {"said": str(said), "answer": str(answer), "time": now}][-KEEP_EXCHANGES:]
        chat["updated"] = now
        if self._write(chat):
            self._made.discard(chat_id)
            self._trim()

    def card(self, chat_id, card) -> None:
        """The card the last answer showed (a proposal, or a hand-off), kept as text: its id and kind, and later how
        it ended (settle). Its words and buttons are never kept: a reopened chat never re-arms it."""
        chat = self.get(chat_id)
        shown = _card({**card, "outcome": None}) if isinstance(card, dict) else None
        if chat is None or not chat["exchanges"] or shown is None:
            return
        chat["exchanges"][-1]["card"] = shown
        if self._write(chat):
            self._cards[shown["id"]] = chat_id

    def settle(self, card_id, outcome) -> None:
        """How one of this run's cards ended (the Brain's card_ended): kept once, in the chat that showed it."""
        chat_id = self._cards.pop(str(card_id), None)
        chat = self.get(chat_id)
        if chat is None:
            return
        for exchange in reversed(chat["exchanges"]):
            card = exchange.get("card")
            if card is not None and card["id"] == card_id and card["outcome"] is None:
                card["outcome"] = _line(outcome, OUTCOME_LIMIT) or "Done"
                self._write(chat)
                return

    def delete(self, chat_id) -> bool:
        """History's Delete, after the user's yes: its file goes. False when there was none."""
        if not isinstance(chat_id, str) or not CHAT_ID.fullmatch(chat_id):
            return False
        self._made.discard(chat_id)
        self._cards = {card: chat for card, chat in self._cards.items() if chat != chat_id}
        try:
            self._path(chat_id).unlink()
        except FileNotFoundError:
            return False
        return True

    def _trim(self) -> None:
        for row in self.list()[KEEP_CHATS:]:  # the least recently updated go
            with contextlib.suppress(OSError):
                self._path(row["id"]).unlink()

    def _write(self, chat: dict) -> bool:
        try:
            write_atomic(self._path(chat["id"]), (json.dumps(chat, ensure_ascii=False) + "\n").encode("utf-8"), 0o600)
        except OSError:  # a full disk, a read-only home: the talk goes on, unkept
            return False
        return True
