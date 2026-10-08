"""What retired with Brave's watcher extension (native app part b): its folder, the module that copied it, its id, its
place in the pages and the `ai` keyword's words. AI Browser never removes the copy a user loaded in Brave: AI Home
says they can (tests/test_home.py)."""

import importlib.util
from pathlib import Path

SRC = Path(__file__).parents[1] / "src" / "ai_browser"
UI = SRC / "app" / "ui"


def test_the_extensions_folder_and_its_helpers_are_gone():
    from ai_browser import syncdir

    assert not (SRC / "app" / "watcher").exists()
    for name in ("ai_browser.brain.watcher", "ai_browser.extension_id"):
        assert importlib.util.find_spec(name) is None, name
    assert callable(syncdir.write_atomic) and not hasattr(syncdir, "sync_folder")


def test_no_page_reaches_an_extension_or_names_the_keyword():
    for path in sorted(UI.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        assert "chrome." not in text and "chrome-extension" not in text, path.name
        assert "config.json" not in text, path.name
    assert "address bar" not in (UI / "home.html").read_text(encoding="utf-8")
    assert "address bar" not in (UI / "workflows.js").read_text(encoding="utf-8")
    assert ".brain-watcher" not in (UI / "brainui.css").read_text(encoding="utf-8")
    assert "watcher-status" not in (UI / "setup.css").read_text(encoding="utf-8")


def test_the_permission_card_always_offers_its_three_answers():
    text = (UI / "permission.js").read_text(encoding="utf-8")
    assert "export function permissionCard(request, send, agentName = \"\") {" in text
    assert "always-elsewhere" not in text and "{ always" not in text


def test_the_readme_tells_the_new_way_and_not_the_old_one():
    text = " ".join((SRC.parents[1] / "README.md").read_text(encoding="utf-8").split())
    for words in ("Settings → **Brain** → **Read my Gmail, Slack and Asana tabs**", "It is off until you turn it on.",
                  "Turning it off stops reading at once, and a read under way keeps nothing.",
                  "**Pick the part to watch**", "then click **Use draft**",
                  "**You press Send**: the Brain never sends anything.", "Settings → **Where agents browse**",
                  "never among your windows", 'click **Remove** on "AI Browser Watcher"',
                  "AI Browser never removes either",
                  "An agent keeps to its tab and opens at most 2 of its own (so usually at most 2 windows), a third "
                  "reusing the oldest"):
        assert words in text, words
    for gone in ("type `ai`", "tab group", "Load unpacked", "the watcher's Brain page", "Pause watching", "**Approve**"):
        assert gone not in text, gone


async def test_website_qa_is_gone():
    """The user's own skill does Website QA now: no `qa` tool, no engine package, no skill, no words that point at it."""
    from mcp.client import Client

    from ai_browser.server import INSTRUCTIONS, build_server

    class Engine:
        async def close(self):
            pass

    async with Client(build_server(Engine)) as client:
        assert "qa" not in {tool.name for tool in (await client.list_tools()).tools}
    assert importlib.util.find_spec("ai_browser.qa") is None
    assert not (SRC / "qa").exists() and not (SRC.parents[1] / "skills" / "website-qa").exists()
    assert not (SRC / "pages" / "qa").exists() and not (SRC / "pages" / "qa2").exists()
    readme = (SRC.parents[1] / "README.md").read_text(encoding="utf-8")
    for text in (readme, INSTRUCTIONS):
        assert "qa(" not in text and "Website QA" not in text and "website-qa" not in text
