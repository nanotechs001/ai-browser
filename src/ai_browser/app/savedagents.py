"""Saved agents (the saved-agents spec, 1): an agent the user sets up once and runs many times, as Claude Code's own
~/.claude/agents files are. Each is a file, <home>/agents/<slug>.md (mode 0600): YAML front matter with its settings,
then its standing instruction, the user's own words. Only AI Browser's own pages write one, on the user's Save
(app-only messages in MESSAGE_RULES): never the Brain, a template or a page's text. A run of it is a desk in Mission
Control like any other; its settings apply when a run starts."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from .. import platforms
from ..syncdir import write_atomic
from .workspaces import one_line

NAME_LIMIT = 60
ABOUT_LIMIT = 160
INSTRUCTION_LIMIT = 8000
CHOICE_LIMIT = 200  # characters of a profile's folder, an account's id or a folder's path
SKILLS_MOST = 500  # skills under Can use, or Load at start
MODELS = ("opus", "sonnet", "haiku")
WEBS = ("web", "brave", "none")  # Web + Brave, Brave only, No web (powers.WEB_CHOICES)
NO_NAME = "An agent needs a name"
NAME_TOO_LONG = f"An agent's name is at most {NAME_LIMIT} characters"
ABOUT_TOO_LONG = f"What it works on is at most {ABOUT_LIMIT} characters"
INSTRUCTION_TOO_LONG = f"The instruction is at most {INSTRUCTION_LIMIT:,} characters"
BAD_MODEL = "The model is opus, sonnet or haiku"
BAD_WEB = "Web is Web + Brave, Brave only or No web"
BAD_SKILLS = "Pick the skills from the list"
BAD_PROFILE = "Pick one of the profiles listed"
BAD_ACCOUNT = "Pick one of the accounts listed"
BAD_FOLDER = "Pick a folder"
BAD_AUTO = "Auto-approve is on or off"
NOT_AN_AGENT = "There is no such agent"
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")
_SKILL_REF = re.compile(r"^[A-Za-z0-9_.-]{1,100}:[A-Za-z0-9_.-]{1,100}$")  # namespace:name, as the server's SKILL_REF
_BREAKS = str.maketrans({"\r": "\n", "\u2028": "\n", "\u2029": "\n", "\t": " "})


@dataclass
class SavedAgent:
    slug: str
    name: str
    description: str = ""
    instruction: str = ""  # its standing instruction: the user's own words, for its system prompt
    profile: str | None = None  # a Brave profile's folder; None: Settings' choice (Where agents browse)
    web: str = "web"
    model: str = "sonnet"
    account: str | None = None  # an account's id; None: the default account for new agents
    folder: str | None = None  # the folder it works in; None: each run's own scratch folder
    auto: bool = False  # Auto-approve in its folder: the user's tick here; every run of it starts with it on
    use: list[str] = field(default_factory=list)  # Can use: skill refs; none is every skill
    load: list[str] = field(default_factory=list)  # Load at start: skill refs, in its first message

    def public(self) -> dict:
        return asdict(self)


def clean_instruction(text) -> str:
    """The standing instruction as it may reach the agent's system prompt: line breaks kept (CR LF, CR and the
    Unicode line and paragraph separators become one line break), a tab becomes a space, and every other control
    or invisible format character (zero-width, direction marks, a byte order mark) is dropped. Trimmed."""
    if not isinstance(text, str):
        return ""
    text = text.replace("\r\n", "\n").translate(_BREAKS)
    return "".join(char for char in text if char == "\n" or unicodedata.category(char) not in ("Cc", "Cf")).strip()


def _words(value, limit: int, too_long: str) -> str:
    text = one_line(value)
    if len(text) > limit:
        raise ValueError(too_long)
    return text


def _choice(value, refused: str) -> str | None:
    """A profile, an account or a folder: one line of text, or None for the default."""
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not one_line(value) or len(value) > CHOICE_LIMIT:
        raise ValueError(refused)
    return value


def _skills(value) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > SKILLS_MOST or not all(
            isinstance(ref, str) and _SKILL_REF.match(ref) for ref in value):
        raise ValueError(BAD_SKILLS)
    return list(dict.fromkeys(value))


def check(fields: dict, slug: str) -> SavedAgent:
    """A saved agent from the Agents page's (or a file's) fields; ValueError in the words the page shows. Load at start
    implies Can use: when Can use names skills, the loaded ones join it (none named is every skill)."""
    name = _words(fields.get("name"), NAME_LIMIT, NAME_TOO_LONG)
    if not name:
        raise ValueError(NO_NAME)
    description = _words(fields.get("description"), ABOUT_LIMIT, ABOUT_TOO_LONG)
    instruction = clean_instruction(fields.get("instruction"))
    if len(instruction) > INSTRUCTION_LIMIT:
        raise ValueError(INSTRUCTION_TOO_LONG)
    model = fields.get("model") or "sonnet"
    if model not in MODELS:
        raise ValueError(BAD_MODEL)
    web = fields.get("web") or "web"
    if web not in WEBS:
        raise ValueError(BAD_WEB)
    auto = fields.get("auto_approve", False)
    if not isinstance(auto, bool):
        raise ValueError(BAD_AUTO)
    use, load = _skills(fields.get("can_use")), _skills(fields.get("load_at_start"))
    if use:
        use = sorted(set(use) | set(load))
    return SavedAgent(slug, name, description, instruction, _choice(fields.get("profile"), BAD_PROFILE), web, model,
                      _choice(fields.get("account"), BAD_ACCOUNT), _choice(fields.get("folder"), BAD_FOLDER), auto,
                      use, load)


class SavedAgents:
    def __init__(self, home: Path):
        self.folder = Path(home) / "agents"

    def path_of(self, slug) -> Path:
        if not isinstance(slug, str) or not _SLUG.match(slug):
            raise ValueError(NOT_AN_AGENT)
        return self.folder / f"{slug}.md"

    def _load(self, path: Path) -> SavedAgent:
        text = path.read_text(encoding="utf-8-sig")  # a BOM from Notepad is dropped
        end = text.find("\n---", 4)
        if not text.startswith("---\n") or end < 0:
            raise ValueError("it needs front matter between two --- lines")
        try:
            data = yaml.safe_load(text[4:end]) or {}
        except yaml.YAMLError:
            raise ValueError("its front matter isn't valid YAML") from None
        if not isinstance(data, dict):
            raise ValueError("its front matter isn't a set of fields")
        return check({**data, "instruction": text[end + 4:]}, path.stem)

    def all(self) -> list[SavedAgent]:
        found = []
        for path in sorted(self.folder.glob("*.md")) if self.folder.is_dir() else []:
            if not _SLUG.match(path.stem):
                continue
            try:
                found.append(self._load(path))
            except (ValueError, OSError):
                continue  # a file broken by hand: skipped, never written over
        return sorted(found, key=lambda saved: saved.name.lower())

    def get(self, slug) -> SavedAgent | None:
        try:
            return self._load(self.path_of(slug))
        except (ValueError, OSError):
            return None

    def save(self, fields: dict) -> SavedAgent:
        """Write an agent: a new one gets a slug of its own; one with a slug (edited on the Agents page) keeps its
        file, and an edit of one deleted meanwhile is refused."""
        slug = fields.get("slug")
        saved = check(fields, "")
        if slug:
            if self.get(slug) is None:  # unreadable counts as missing: never written over
                raise ValueError(NOT_AN_AGENT)
        else:
            base = re.sub(r"[^a-z0-9]+", "-", saved.name.lower()).strip("-")[:40].strip("-") or "agent"
            slug, number = base, 1
            while (self.folder / f"{slug}.md").exists():
                number += 1
                slug = f"{base}-{number}"
        saved.slug = slug
        front = {"name": saved.name, "description": saved.description, "profile": saved.profile, "web": saved.web,
                 "model": saved.model, "account": saved.account, "folder": saved.folder,
                 "auto_approve": saved.auto, "can_use": saved.use, "load_at_start": saved.load}
        text = f"---\n{yaml.safe_dump(front, sort_keys=False, allow_unicode=True)}---\n{saved.instruction}\n"
        write_atomic(self.path_of(slug), text.encode("utf-8"), 0o600)
        return saved

    def delete(self, slug) -> bool:
        path = self.path_of(slug)
        if not path.is_file():
            return False
        platforms.unlink(path, missing_ok=True)  # an editor may hold it a moment on Windows
        return True
