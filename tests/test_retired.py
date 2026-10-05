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
