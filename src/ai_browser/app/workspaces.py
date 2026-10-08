"""Workspaces (the new look, Decision 6): named groups of agents and templates, which filter Mission Control's
Dashboard, My Missions and Templates. Kept in <home>/workspaces.json (mode 0600): each workspace's id, name and its
templates (workflow slugs). Agents are grouped in memory only, on the agent itself (its `workspace`): their ids start
again with every run, so a saved one would group another agent after a restart. A missing or blank file is no
workspaces, and a broken row is skipped. A file that is there but can't be read, or isn't JSON, shows as no workspaces
and is never written over: every change is refused with words until the user fixes or removes it. Deleting a
workspace removes the grouping only."""

from __future__ import annotations

import json
import re
import secrets
from pathlib import Path

from ..syncdir import write_atomic

FILE = "workspaces.json"
NAME_LIMIT = 40
MOST = 50
_ID = re.compile(r"w[0-9a-f]{8}")
_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,60}")  # a workflow's slug (brain/workflows.py)
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩﻿]")
NO_NAME = "Give the workspace a name"
TOO_LONG = f"A workspace's name is at most {NAME_LIMIT} characters"
TAKEN = "There is a workspace named {name} already"
TOO_MANY = f"At most {MOST} workspaces"
GONE = "That workspace was deleted"
UNREADABLE = "Couldn't read your workspaces file: {path} ({why}). Fix it or remove it, then try again."


def one_line(text) -> str:
    """The user's words as one line of text: control characters and direction marks dropped, whitespace squeezed; ""
    for anything that isn't text. A workspace's name, and a mission's name and description (app/agents.py)."""
    return " ".join(_CONTROL.sub("", text).split()) if isinstance(text, str) else ""


def clean_name(name) -> str:
    """One line: control characters and direction marks dropped, whitespace squeezed. ValueError when it is empty or
    too long."""
    text = one_line(name)
    if not text:
        raise ValueError(NO_NAME)
    if len(text) > NAME_LIMIT:
        raise ValueError(TOO_LONG)
    return text


class Workspaces:
    def __init__(self, home):
        self.path = Path(home) / FILE

    def _load(self) -> list[dict]:
        """The workspaces, for a change: ValueError (UNREADABLE) when the file is there but can't be read or isn't
        JSON, so that a change never writes over it."""
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise ValueError(UNREADABLE.format(path=self.path, why=exc.strerror or exc)) from None
        except ValueError:  # not UTF-8 text
            raise ValueError(UNREADABLE.format(path=self.path, why="it isn't text")) from None
        if not text.strip():  # blank: nothing in it to lose
            return []
        try:
            data = json.loads(text)
        except ValueError:
            raise ValueError(UNREADABLE.format(path=self.path, why="it isn't valid JSON")) from None
        rows = data.get("workspaces") if isinstance(data, dict) else None
        out, seen = [], set()
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not _ID.fullmatch(row["id"]) \
                    or row["id"] in seen:
                continue
            try:
                name = clean_name(row.get("name"))
            except ValueError:
                continue
            listed = row.get("templates") if isinstance(row.get("templates"), list) else []
            templates = [slug for slug in listed if isinstance(slug, str) and _SLUG.fullmatch(slug)]
            seen.add(row["id"])
            out.append({"id": row["id"], "name": name, "templates": list(dict.fromkeys(templates))})
        return out[:MOST]

    def _read(self) -> list[dict]:
        """The workspaces, for display: a file that can't be read shows as none."""
        try:
            return self._load()
        except ValueError:
            return []

    def _write(self, rows: list[dict]) -> None:
        text = json.dumps({"workspaces": rows}, indent=1, ensure_ascii=False) + "\n"
        write_atomic(self.path, text.encode("utf-8"), 0o600)

    def list(self) -> list[dict]:
        return self._read()

    def get(self, workspace_id) -> dict | None:
        return next((row for row in self._read() if row["id"] == workspace_id), None)

    @staticmethod
    def _free(rows: list[dict], name: str, keep=None) -> None:
        if any(row["name"].casefold() == name.casefold() and row["id"] != keep for row in rows):
            raise ValueError(TAKEN.format(name=name))

    def create(self, name) -> dict:
        rows = self._load()
        name = clean_name(name)
        self._free(rows, name)
        if len(rows) >= MOST:
            raise ValueError(TOO_MANY)
        taken = {row["id"] for row in rows}
        new_id = f"w{secrets.token_hex(4)}"
        while new_id in taken:  # 4 billion ids: a clash is all but impossible
            new_id = f"w{secrets.token_hex(4)}"
        row = {"id": new_id, "name": name, "templates": []}
        self._write([*rows, row])
        return row

    def rename(self, workspace_id, name) -> dict:
        rows = self._load()
        row = next((one for one in rows if one["id"] == workspace_id), None)
        if row is None:
            raise ValueError(GONE)
        name = clean_name(name)
        self._free(rows, name, keep=workspace_id)
        row["name"] = name
        self._write(rows)
        return row

    def delete(self, workspace_id) -> bool:
        rows = self._load()
        kept = [row for row in rows if row["id"] != workspace_id]
        if len(kept) == len(rows):
            return False
        self._write(kept)
        return True

    def assign_template(self, slug, workspace_id) -> None:
        """Put a template in one workspace, or in none (None): a template is in at most one."""
        if not isinstance(slug, str) or not _SLUG.fullmatch(slug):
            raise ValueError("Not a template")
        rows = self._load()
        if workspace_id is not None and not any(row["id"] == workspace_id for row in rows):
            raise ValueError(GONE)
        for row in rows:
            row["templates"] = [one for one in row["templates"] if one != slug]
            if row["id"] == workspace_id:
                row["templates"].append(slug)
        self._write(rows)
