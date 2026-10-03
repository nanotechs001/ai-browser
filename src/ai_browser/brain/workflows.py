"""The user's workflows: named recipes in plain words, run as AI Browser agents.

Each is a file, <home>/workflows/<slug>.md (mode 0600): YAML front matter, then the instructions. The user writes it
with AI Home's form or in a text editor. A workflow runs by hand (AI Home's Run, or `ai <name>` in the address bar),
from a matching message (the Brain's sorting offers it, or starts it when it is set to run right away), or on a
schedule while `ai-browser app` runs: never two runs of one workflow at once, and runs missed while the app was off
are not caught up. Its agent loads the workflow's skills first and may use only its tools (still asking for each)."""

from __future__ import annotations

import datetime
import json
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from .. import platforms
from ..syncdir import write_atomic

TRIGGERS = {"manual", "message", "schedule"}
MODELS = {"opus", "sonnet", "haiku"}
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
ACTIVE = {"working", "waiting", "needs_you"}  # a run still going: the next one waits
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")
_SKILL = re.compile(r"^[A-Za-z0-9_.:-]{1,100}$")
_SERVER = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_SITE = re.compile(r"^(gmail|slack|asana|custom:[A-Za-z0-9.-]{1,253})$")
_TIME = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _now() -> float:
    return time.time()


@dataclass
class Workflow:
    slug: str
    name: str
    instructions: str
    trigger: str = "manual"  # manual | message | schedule
    site: str = ""  # message: a site from the watch list
    when: str = ""  # message: when it applies, in plain words
    schedule: str = ""  # schedule: "weekdays 09:00", "every 2h"...
    run: str = "ask"  # message: ask first, or "auto" (run right away)
    tools: list[str] = field(default_factory=list)  # MCP servers its agent may use
    skills: list[str] = field(default_factory=list)  # skills its agent loads first
    model: str = "sonnet"

    def public(self) -> dict:
        return asdict(self)


class Schedule:
    def __init__(self, days: set[int] | None = None, hour: int = 0, minute: int = 0, every: float | None = None):
        self.days, self.hour, self.minute, self.every = days, hour, minute, every

    @classmethod
    def parse(cls, text: str) -> Schedule:
        words = str(text or "").strip().lower().split()
        problem = (f'"{text}" isn\'t a schedule: write "daily 09:00", "weekdays 09:00", "mon 08:30", '
                   '"mon,wed 17:00", "every 2h" or "every 30m"')
        if len(words) != 2:
            raise ValueError(problem)
        if words[0] == "every":
            found = re.fullmatch(r"(\d+)([hm])", words[1])
            amount = int(found[1]) if found else 0
            if found and found[2] == "h" and 1 <= amount <= 24:
                return cls(every=amount * 3600)
            if found and found[2] == "m" and 15 <= amount <= 720:
                return cls(every=amount * 60)
            raise ValueError(f"{problem} (every 1h to 24h, or every 15m to 720m)")
        when = _TIME.fullmatch(words[1])
        if not when:
            raise ValueError(problem)
        if words[0] == "daily":
            days = set(range(7))
        elif words[0] == "weekdays":
            days = set(range(5))
        else:
            names = words[0].split(",")
            if any(name not in DAYS for name in names):
                raise ValueError(problem)
            days = {DAYS.index(name) for name in names}
        return cls(days, int(when[1]), int(when[2]))

    def due(self, last: float, now: float) -> bool:
        """Whether a scheduled moment falls after `last` and up to `now` (local time)."""
        if self.every is not None:
            return now - last >= self.every
        day = datetime.datetime.fromtimestamp(last).date()
        end = datetime.datetime.fromtimestamp(now).date()
        day = max(day, end - datetime.timedelta(days=400))
        while day <= end:
            if day.weekday() in self.days:
                moment = datetime.datetime(day.year, day.month, day.day, self.hour, self.minute).timestamp()
                if last < moment <= now:
                    return True
            day += datetime.timedelta(days=1)
        return False


def check(fields: dict, slug: str) -> Workflow:
    """A workflow from the form's (or a file's) fields; ValueError says what is wrong."""
    name, instructions = fields.get("name"), fields.get("instructions")
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        raise ValueError("A workflow needs a name (at most 80 characters)")
    if not isinstance(instructions, str) or not instructions.strip() or len(instructions) > 20000:
        raise ValueError("A workflow needs instructions (at most 20 000 characters)")
    trigger = fields.get("trigger") or "manual"
    if trigger not in TRIGGERS:
        raise ValueError("The trigger is by hand, a message, or a schedule")
    site, when, schedule = str(fields.get("site") or ""), str(fields.get("when") or "").strip(), ""
    if trigger == "message" and (not _SITE.match(site) or not when or len(when) > 300):
        raise ValueError("A message workflow needs a site from the watch list, and when it applies")
    if trigger == "schedule":
        schedule = str(fields.get("schedule") or "").strip()
        Schedule.parse(schedule)
    run = fields.get("run") or "ask"
    if run not in ("ask", "auto"):
        raise ValueError('run is "ask" (ask me first) or "auto" (run right away)')
    tools, skills = fields.get("tools") or [], fields.get("skills") or []
    if not isinstance(tools, list) or not all(isinstance(tool, str) and _SERVER.match(tool) for tool in tools):
        raise ValueError("tools is a list of MCP server names")
    if not isinstance(skills, list) or not all(isinstance(skill, str) and _SKILL.match(skill) for skill in skills):
        raise ValueError("skills is a list of skill names")
    model = fields.get("model") or "sonnet"
    if model not in MODELS:
        raise ValueError("The model is opus, sonnet or haiku")
    return Workflow(slug, name.strip(), instructions.strip(), trigger, site if trigger == "message" else "",
                    when if trigger == "message" else "", schedule, run, list(tools), list(skills), model)


class WorkflowStore:
    def __init__(self, home: Path):
        self.folder = Path(home) / "workflows"

    def path_of(self, slug: str) -> Path:
        if not _SLUG.match(str(slug)):
            raise ValueError("Not a workflow")
        return self.folder / f"{slug}.md"

    def _files(self) -> list[Path]:
        return sorted(path for path in self.folder.glob("*.md") if _SLUG.match(path.stem)) \
            if self.folder.is_dir() else []

    def _load(self, path: Path) -> Workflow:
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
        fields = {key: data.get(key) for key in ("name", "run", "tools", "skills", "model")}
        fields["instructions"] = text[end + 4:].strip()
        trigger = data.get("trigger", "manual")
        if trigger == "manual":
            fields["trigger"] = "manual"
        elif isinstance(trigger, dict) and isinstance(trigger.get("message"), dict):
            fields.update(trigger="message", site=trigger["message"].get("site"), when=trigger["message"].get("when"))
        elif isinstance(trigger, dict) and "schedule" in trigger:
            fields.update(trigger="schedule", schedule=trigger["schedule"])
        else:
            raise ValueError("trigger is manual, {message: {site, when}} or {schedule: ...}")
        return check(fields, path.stem)

    def all(self) -> list[Workflow]:
        workflows = []
        for path in self._files():
            try:
                workflows.append(self._load(path))
            except (ValueError, OSError):
                continue
        return sorted(workflows, key=lambda workflow: workflow.name.lower())

    def problems(self) -> list[str]:
        problems = []
        for path in self._files():
            try:
                self._load(path)
            except (ValueError, OSError) as exc:
                problems.append(f"{path.name}: {exc}")
        return problems

    def get(self, slug: str) -> Workflow | None:
        try:
            return self._load(self.path_of(slug))
        except (ValueError, OSError):
            return None

    def save(self, fields: dict) -> Workflow:
        """Write a workflow: a new one gets a slug of its own; one with a slug (edited in AI Home) keeps its file."""
        slug = fields.get("slug")
        workflow = check(fields, "")
        if slug:
            self.path_of(slug)
        else:
            base = re.sub(r"[^a-z0-9]+", "-", workflow.name.lower()).strip("-")[:40].strip("-") or "workflow"
            slug, number = base, 1
            while (self.folder / f"{slug}.md").exists():
                number += 1
                slug = f"{base}-{number}"
        workflow.slug = slug
        front: dict = {"name": workflow.name}
        if workflow.trigger == "message":
            front["trigger"] = {"message": {"site": workflow.site, "when": workflow.when}}
            front["run"] = workflow.run
        elif workflow.trigger == "schedule":
            front["trigger"] = {"schedule": workflow.schedule}
        else:
            front["trigger"] = "manual"
        front.update(tools=workflow.tools, skills=workflow.skills, model=workflow.model)
        text = f"---\n{yaml.safe_dump(front, sort_keys=False, allow_unicode=True)}---\n{workflow.instructions}\n"
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.path_of(slug)
        write_atomic(path, text.encode("utf-8"), 0o600)
        return workflow

    def delete(self, slug: str) -> None:
        platforms.unlink(self.path_of(slug), missing_ok=True)  # an editor may hold it a moment on Windows


class WorkflowRunner:
    def __init__(self, store: WorkflowStore, agents, clock: Callable[[], float] | None = None):
        self.store = store
        self.agents = agents
        self.clock = clock
        self.active: dict[str, str] = {}  # slug -> the agent of its latest run
        self.notes: dict[str, str] = {}  # slug -> "Started 09:00", "Skipped 10:00: the last run is still going"
        self.on_change: Callable[[], None] | None = None  # the app shows new notes
        self._last: dict[str, float] = {}

    def _now(self) -> float:
        return (self.clock or _now)()

    def _note(self, slug: str, note: str) -> None:
        self.notes[slug] = note
        if self.on_change is not None:
            self.on_change()

    def running(self, slug: str) -> bool:
        agent = getattr(self.agents, "agents", {}).get(self.active.get(slug, ""))
        return agent is not None and agent.state in ACTIVE

    async def run(self, slug: str, text: str | None = None, page: str | None = None) -> str:
        """Start the workflow's agent: its instructions (the user's words), then the message as labelled page data
        or the user's extra words. Returns the agent's id."""
        workflow = self.store.get(slug)
        if workflow is None:
            raise ValueError(f"There is no workflow {json.dumps(slug)}")
        message = workflow.instructions
        if page:
            message += f"\n\n{page}"
        elif text:
            message += f"\n\nThe user adds: {text}"
        agent = await self.agents.create(message, skills=workflow.skills, model=workflow.model,
                                         servers=workflow.tools)
        self.active[slug] = agent.id
        self._note(slug, f"Started {time.strftime('%H:%M', time.localtime(self._now()))}")
        return agent.id

    async def tick(self) -> None:
        """Run the scheduled workflows that are due (called every 30 seconds while the app runs)."""
        now = self._now()
        for workflow in self.store.all():
            if workflow.trigger != "schedule":
                continue
            last = self._last.setdefault(workflow.slug, now)  # the clock starts now: nothing missed is caught up
            try:
                due = Schedule.parse(workflow.schedule).due(last, now)
            except ValueError:
                continue
            if not due:
                continue
            self._last[workflow.slug] = now
            if self.running(workflow.slug):
                self._note(workflow.slug, f"Skipped {time.strftime('%H:%M', time.localtime(now))}: the last run is "
                                          "still going")
                continue
            await self.run(workflow.slug)
