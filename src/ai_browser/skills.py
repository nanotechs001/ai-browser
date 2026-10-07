"""Catalog of every installed Claude skill, searched and loaded on demand."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from . import platforms
from .config import READ_LIMIT

FILE_LIST_LIMIT = 30
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}


@dataclass(frozen=True)
class Skill:
    ref: str
    namespace: str
    name: str
    description: str
    host_dir: Path
    sandbox_dir: str
    has_scripts: bool
    mount: str = ""


@dataclass(frozen=True)
class SkillSource:
    namespace: str
    host_root: Path
    mount: str
    pattern: str  # "*/SKILL.md" or "skills/*/SKILL.md"


class SkillNotFound(KeyError):
    def __str__(self) -> str:
        return self.args[0]


class AmbiguousSkill(KeyError):
    def __str__(self) -> str:
        return self.args[0]


def _frontmatter(text: str) -> tuple[dict, str]:
    """Split SKILL.md into (frontmatter dict, body); broken frontmatter gives ({}, body)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    body = text[end + 4:].lstrip("\n")
    try:
        data = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return {}, body
    return (data if isinstance(data, dict) else {}), body


def _one_line(text) -> str:
    return " ".join(str(text or "").split())


def user_folders() -> tuple[Path, Path]:
    """Where the user's own skills are: Claude Code's folder (~/.claude: personal skills and plugins) and the Claude
    desktop app's (the skills synced from claude.ai). The test suite points it at a throwaway folder."""
    return Path.home() / ".claude", platforms.claude_desktop_dir()


class Catalog:
    def __init__(self, sources: list[SkillSource], blocked: set[str]):
        self.sources = [source for source in sources if source.host_root.is_dir()]
        self.blocked = set(blocked)
        self._skills: dict[str, Skill] = {}
        for source in self.sources:
            for skill_md in sorted(source.host_root.glob(source.pattern)):
                skill = self._read(source, skill_md)
                if skill and skill.ref not in self._skills:
                    self._skills[skill.ref] = skill

    @staticmethod
    def _read(source: SkillSource, skill_md: Path) -> Skill | None:
        try:
            meta, _ = _frontmatter(skill_md.read_text(encoding="utf-8-sig", errors="replace"))
        except OSError:
            return None
        folder = skill_md.parent
        name = _one_line(meta.get("name")) or folder.name
        rel = folder.relative_to(source.host_root).as_posix()
        return Skill(
            ref=f"{source.namespace}:{name}",
            namespace=source.namespace,
            name=name,
            description=_one_line(meta.get("description")),
            host_dir=folder,
            sandbox_dir=f"{source.mount}/{rel}",
            has_scripts=(folder / "scripts").is_dir(),
            mount=source.mount,
        )

    @classmethod
    def of_user(cls, project_skills: Path, blocked: set[str]) -> "Catalog":
        """The skills an agent sees: the user's own (user_folders) and the project's."""
        claude_home, app_support = user_folders()
        return cls.discover(claude_home, app_support, project_skills, blocked)

    @classmethod
    def discover(cls, claude_home: Path, app_support: Path, project_skills: Path, blocked: set[str]) -> "Catalog":
        sources = [SkillSource("personal", claude_home / "skills", "/skills/personal", "*/SKILL.md")]
        sources += _plugin_sources(claude_home)
        synced = sorted(
            (app_support / "local-agent-mode-sessions" / "skills-plugin").glob("*/*/skills"),
            key=lambda path: path.stat().st_mtime,
        )
        if synced:
            sources.append(SkillSource("anthropic-skills", synced[-1], "/skills/claude-ai", "*/SKILL.md"))
        sources.append(SkillSource("ai-browser", project_skills, "/skills/ai-browser", "*/SKILL.md"))
        return cls(sources, blocked)

    def all(self) -> list[Skill]:
        return [skill for ref, skill in self._skills.items() if ref not in self.blocked]

    def find(self, query: str, limit: int = 10) -> list[Skill]:
        tokens = [token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) >= 2]
        scored = []
        for skill in self.all():
            name, description = skill.name.lower(), skill.description.lower()
            score = sum(3 * (token in name) + (token in description) for token in tokens)
            if score:
                scored.append((-score, skill.ref, skill))
        return [skill for _, _, skill in sorted(scored)[:limit]]

    def summary(self) -> str:
        groups: dict[str, list[str]] = {}
        for skill in self.all():
            groups.setdefault(skill.namespace, []).append(skill.name)
        lines = [f"{len(self.all())} skills. Search with find_skills(\"words\"); load with load_skill(\"namespace:name\")."]
        for namespace, names in groups.items():
            lines.append(f"{namespace} ({len(names)}): {', '.join(sorted(names))}")
        return "\n".join(lines)

    def get(self, name: str) -> Skill:
        name = name.strip()
        if ":" in name:
            skill = self._skills.get(name)
            if skill is None or name in self.blocked:
                raise SkillNotFound(f"no skill {name!r}; use find_skills to search")
            return skill
        matches = [skill for skill in self.all() if skill.name == name]
        if not matches:
            raise SkillNotFound(f"no skill {name!r}; use find_skills to search")
        if len(matches) > 1:
            refs = ", ".join(skill.ref for skill in matches)
            raise AmbiguousSkill(f"{name!r} matches {refs}; use the full name")
        return matches[0]

    def load(self, name: str) -> str:
        skill = self.get(name)
        _, body = _frontmatter((skill.host_dir / "SKILL.md").read_text(encoding="utf-8-sig", errors="replace"))
        body = body.replace("${CLAUDE_PLUGIN_ROOT}", skill.mount).replace("${CLAUDE_SKILL_DIR}", skill.sandbox_dir)
        files = _list_files(skill.host_dir)
        lines = [f"skill {skill.ref} · sandbox folder {skill.sandbox_dir} (read-only)"]
        if skill.description:
            lines.append(f"description: {skill.description}")
        if files:
            lines.append("files: " + ", ".join(files))
        return "\n".join(lines) + "\n\n" + body

    def read_file(self, name: str, rel: str) -> str:
        skill = self.get(name)
        parts = PurePosixPath(rel).parts
        if not rel or rel.startswith("/") or ".." in parts:
            raise ValueError(f"{rel!r}: use a path inside the skill folder, like scripts/run.py")
        path = (skill.host_dir / rel).resolve()
        if not path.is_relative_to(skill.host_dir.resolve()):
            raise ValueError(f"{rel!r}: use a path inside the skill folder")
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > READ_LIMIT:
            text = text[:READ_LIMIT] + f"\n[truncated: {len(text) - READ_LIMIT} more chars]"
        return text

    def mounts(self) -> list[tuple[Path, str]]:
        return [(source.host_root, source.mount) for source in self.sources]


def _plugin_sources(claude_home: Path) -> list[SkillSource]:
    try:
        installed = json.loads((claude_home / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    try:
        enabled = json.loads((claude_home / "settings.json").read_text(encoding="utf-8")).get("enabledPlugins") or {}
    except (OSError, ValueError, AttributeError):
        enabled = {}
    sources = []
    for key, entries in (installed.get("plugins") or {}).items():
        if enabled.get(key) is False or not entries:
            continue
        install_path = entries[0].get("installPath") if isinstance(entries[0], dict) else None
        if not install_path:
            continue
        namespace = key.split("@", 1)[0]
        sources.append(SkillSource(namespace, Path(install_path), f"/skills/plugins/{namespace}", "skills/*/SKILL.md"))
    return sources


def _list_files(folder: Path) -> list[str]:
    files = []
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder)
        if any(part in _SKIP_DIRS or part.startswith(".") for part in rel.parts):
            continue
        if path.is_file() and rel.as_posix() != "SKILL.md":
            files.append(rel.as_posix())
            if len(files) >= FILE_LIST_LIMIT:
                break
    return files
