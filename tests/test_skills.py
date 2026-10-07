import json
import os
from pathlib import Path

import pytest

from ai_browser.skills import AmbiguousSkill, Catalog, SkillNotFound


def make_skill(root: Path, folder: str, name: str | None = None, desc: str = "", body: str = "Body",
               scripts: bool = False, frontmatter: bool = True) -> Path:
    d = root / folder
    d.mkdir(parents=True)
    head = f"---\nname: {name or folder}\ndescription: {desc}\n---\n" if frontmatter else "---\n: [broken\n---\n"
    (d / "SKILL.md").write_text(head + body, encoding="utf-8")
    if scripts:
        (d / "scripts").mkdir()
        (d / "scripts" / "run.py").write_text("print('hi')", encoding="utf-8")
    return d


@pytest.fixture
def env(tmp_path):
    claude = tmp_path / ".claude"
    make_skill(claude / "skills", "seo", desc="Comprehensive SEO analysis for any website, including Elementor sites")
    make_skill(claude / "skills", "broken", frontmatter=False)
    ecc = claude / "plugins/cache/ecc/ecc/2.2.2"
    make_skill(ecc / "skills", "api-design", desc="REST API design patterns", scripts=True,
               body="Run ${CLAUDE_PLUGIN_ROOT}/skills/api-design/scripts/run.py")
    make_skill(ecc / "skills", "browser-qa", desc="QA a website in the browser")
    make_skill(ecc / "skills", "seo", desc="SEO from ecc")
    sp = claude / "plugins/cache/sp/superpowers/6.4.1"
    make_skill(sp / "skills", "brainstorming", desc="Explore ideas before building")
    off = claude / "plugins/cache/x/off/1.0"
    make_skill(off / "skills", "hidden", desc="should not appear")
    (claude / "plugins/installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
        "ecc@ecc": [{"installPath": str(ecc)}],
        "superpowers@superpowers-marketplace": [{"installPath": str(sp)}],
        "off@x": [{"installPath": str(off)}],
    }}), encoding="utf-8")
    (claude / "settings.json").write_text(json.dumps({"enabledPlugins": {
        "ecc@ecc": True, "superpowers@superpowers-marketplace": True, "off@x": False}}), encoding="utf-8")
    app = tmp_path / "AppSupport"
    old = app / "local-agent-mode-sessions/skills-plugin/a/old/skills"
    make_skill(old, "docx", desc="OLD")
    new = app / "local-agent-mode-sessions/skills-plugin/a/new/skills"
    make_skill(new, "docx", desc="Word documents")
    make_skill(new, "pdf", desc="PDF files")
    os.utime(old, (1, 1))
    project = tmp_path / "project-skills"
    make_skill(project, "elementor", desc="Build pages in Elementor")
    return {"claude": claude, "app": app, "project": project, "ecc": ecc, "sp": sp, "new": new}


def catalog(env, blocked=()):
    return Catalog.discover(env["claude"], env["app"], env["project"], set(blocked))


def test_discovers_all_enabled_sources(env):
    refs = {skill.ref for skill in catalog(env).all()}
    assert refs == {
        "personal:seo", "personal:broken", "ecc:api-design", "ecc:browser-qa", "ecc:seo",
        "superpowers:brainstorming", "anthropic-skills:docx", "anthropic-skills:pdf", "ai-browser:elementor",
    }


def test_uses_newest_claude_ai_skill_set(env):
    assert catalog(env).get("anthropic-skills:docx").description == "Word documents"


def test_malformed_frontmatter_is_tolerated(env):
    skill = catalog(env).get("personal:broken")
    assert (skill.name, skill.description) == ("broken", "")


def test_sandbox_dirs(env):
    cat = catalog(env)
    assert cat.get("personal:seo").sandbox_dir == "/skills/personal/seo"
    assert cat.get("ecc:api-design").sandbox_dir == "/skills/plugins/ecc/skills/api-design"
    assert cat.get("anthropic-skills:pdf").sandbox_dir == "/skills/claude-ai/pdf"
    assert cat.get("ai-browser:elementor").sandbox_dir == "/skills/ai-browser/elementor"


def test_has_scripts_flag(env):
    cat = catalog(env)
    assert cat.get("ecc:api-design").has_scripts is True
    assert cat.get("ecc:browser-qa").has_scripts is False


def test_blocked_skill_is_invisible(env):
    cat = catalog(env, blocked=["ecc:api-design"])
    assert "ecc:api-design" not in {skill.ref for skill in cat.all()}
    assert all(skill.ref != "ecc:api-design" for skill in cat.find("api design"))
    with pytest.raises(SkillNotFound):
        cat.get("ecc:api-design")


def test_find_ranks_name_matches_first(env):
    results = catalog(env).find("elementor")
    assert results[0].ref == "ai-browser:elementor"
    assert "personal:seo" in {skill.ref for skill in results}


def test_find_without_matches_is_empty(env):
    assert catalog(env).find("zzzz") == []


def test_find_respects_limit(env):
    assert len(catalog(env).find("seo", limit=1)) == 1


def test_get_bare_name_when_unique(env):
    assert catalog(env).get("brainstorming").ref == "superpowers:brainstorming"


def test_get_bare_name_when_ambiguous(env):
    with pytest.raises(AmbiguousSkill, match="ecc:seo"):
        catalog(env).get("seo")


def test_get_missing(env):
    with pytest.raises(SkillNotFound):
        catalog(env).get("nope")


def test_load_has_header_files_and_rewritten_root(env):
    text = catalog(env).load("ecc:api-design")
    first = text.splitlines()[0]
    assert "skill ecc:api-design" in first
    assert "/skills/plugins/ecc/skills/api-design" in first
    assert "files: scripts/run.py" in text
    assert "Run /skills/plugins/ecc/skills/api-design/scripts/run.py" in text
    assert "${CLAUDE_PLUGIN_ROOT}" not in text


def test_read_file(env):
    assert catalog(env).read_file("ecc:api-design", "scripts/run.py") == "print('hi')"


@pytest.mark.parametrize("rel", ["../browser-qa/SKILL.md", "/etc/passwd", "scripts/../../seo/SKILL.md"])
def test_read_file_rejects_escapes(env, rel):
    with pytest.raises(ValueError):
        catalog(env).read_file("ecc:api-design", rel)


def test_mounts(env):
    mounts = set(catalog(env).mounts())
    assert (env["claude"] / "skills", "/skills/personal") in mounts
    assert (env["ecc"], "/skills/plugins/ecc") in mounts
    assert (env["sp"], "/skills/plugins/superpowers") in mounts
    assert (env["new"], "/skills/claude-ai") in mounts
    assert (env["project"], "/skills/ai-browser") in mounts


def test_summary_groups_by_namespace(env):
    summary = catalog(env).summary()
    assert "9 skills" in summary
    assert "ecc (3): api-design, browser-qa, seo" in summary


def test_missing_sources_give_an_empty_catalog(tmp_path):
    cat = Catalog.discover(tmp_path / "none", tmp_path / "none2", tmp_path / "none3", set())
    assert cat.all() == []
    assert cat.mounts() == []


def test_the_website_qa_skill_ships_with_the_project():
    from ai_browser.config import project_root

    catalog = Catalog.discover(project_root() / "no-claude-home", project_root() / "no-app-support",
                               project_root() / "skills", set())
    loaded = catalog.load("ai-browser:website-qa")
    assert "qa(" in loaded and "verify" in loaded.lower()


def test_the_website_qa_skill_hands_bot_checks_over_and_stays_polite():
    from ai_browser.config import project_root

    text = (project_root() / "skills" / "website-qa" / "SKILL.md").read_text(encoding="utf-8")
    flat = " ".join(text.split())
    assert ("**Bot checks:** if qa or open stops at a bot check, stop and tell the user. Never switch browsers, "
            "profiles or tools to get past it: the user solves it, or skips the site.") in flat
    assert "Sites that block the sandbox" not in text
    own = flat.split("- **The user's own browser:**", 1)[1].split("- **", 1)[0]  # chrome=true only when asked for
    assert flat.count("chrome=true") == 1 and "chrome=true" in own and "bot check" not in own
    assert "## Be polite" in text and "no `xargs -P`" in flat and "ignore_robots=true" in flat
    assert ("30 pages take about three minutes, because qa is polite (below). A run stops visiting pages after five "
            "minutes and says so") in flat
    assert ("A site with many links takes longer while the links qa didn't visit are checked, about six minutes at "
            "most.") in flat


def test_the_website_qa_skill_says_where_qa_crawls():
    from ai_browser.config import project_root

    text = " ".join((project_root() / "skills" / "website-qa" / "SKILL.md").read_text(encoding="utf-8").split())
    section = text.split("## 1. Pick the browser", 1)[1].split("## 2.", 1)[0]
    assert "qa crawls in the Docker sandbox by default, even when the session browses in the user's Brave" in section
    assert "only when the user asks for their own browser" in section and "sandbox_start(chrome=true)" in section
    assert ("**Bot checks:** if qa or open stops at a bot check, stop and tell the user. Never switch browsers, "
            "profiles or tools to get past it: the user solves it, or skips the site.") in section  # wave 1's line


async def test_no_tests_skill_catalog_reads_the_users_own_folders(tmp_path, tmp_path_factory, monkeypatch):
    """The final review, F12: tests never touch ~/.claude, and Mission Control's pages ask for the skills on every
    snapshot. The app's catalog and an engine's own (where no catalog is handed in) read throwaway folders."""
    from ai_browser.app.agents import AgentManager
    from ai_browser.app.server import AppServer
    from ai_browser.engine import Engine
    from conftest import REAL_HOME

    roots = []

    def spy(cls, claude_home, app_support, *rest):  # where it would read, never read here
        roots.extend([claude_home, app_support])
        return Catalog([], set())

    monkeypatch.setattr(Catalog, "discover", classmethod(spy))
    AppServer(tmp_path / "home", AgentManager(tmp_path / "home"))._skills()
    assert Engine(home=tmp_path / "engine").catalog is not None
    assert len(roots) == 4
    spare = tmp_path_factory.getbasetemp().resolve()  # pytest's own temporary folders (under the home on Windows)
    for root in roots:
        where = Path(os.path.realpath(root))
        assert not where.is_relative_to(REAL_HOME.resolve()) or where.is_relative_to(spare), root
