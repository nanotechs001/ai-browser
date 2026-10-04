"""AI Browser's pages, read as files: where they live, and (from Task 14) what they never do."""

import re
from pathlib import Path

APP = Path(__file__).parents[1] / "src" / "ai_browser" / "app"
UI = APP / "ui"


def test_the_pages_live_in_app_ui_and_the_watcher_shares_them():
    from ai_browser.brain.watcher import SHARED_SOURCE, WATCHER_SHARED

    for name in ("home.html", "mission.html", "home.js", "mission.js", "link.js", "brainui.js", "brainui.css",
                 "check.js", "mic.js", "mic-worklet.js", "talk.js", "tablist.js", "chat.js", "permission.js"):
        assert (UI / name).is_file(), name
    assert sorted(path.name for path in (APP / "extension").iterdir() if not path.name.startswith(".")) == [
        "manifest.json", "panel.css", "panel.html", "panel.js", "worker.js"]
    assert SHARED_SOURCE == UI and all((UI / name).is_file() for name in WATCHER_SHARED)


def test_the_watchers_shared_files_are_byte_equal_to_app_uis(tmp_path):
    from ai_browser.brain.watcher import WATCHER_SHARED, prepare_watcher

    folder, _ = prepare_watcher(tmp_path, "http://127.0.0.1:8792", "token")
    for name in WATCHER_SHARED:
        assert (folder / name).read_bytes() == (UI / name).read_bytes(), name


INLINE_SCRIPT = re.compile(r"<script(?![^>]*\ssrc=)[^>]*>", re.IGNORECASE)


def test_the_window_pages_are_all_there():
    for name in ("home.html", "mission.html", "settings.html", "setup.html", "nav.js"):
        assert (UI / name).is_file(), name


def test_no_script_writes_html_and_no_page_runs_inline_code():
    scripts, pages = sorted(UI.glob("*.js")), sorted(UI.glob("*.html"))
    assert scripts and pages
    for path in scripts:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\.innerHTML|\.outerHTML|insertAdjacentHTML|document\.write", text), path.name
    for path in pages:
        text = path.read_text(encoding="utf-8")
        assert not INLINE_SCRIPT.search(text), path.name
        assert not re.search(r"<style|\sstyle\s*=", text, re.IGNORECASE), path.name
        assert not re.search(r"\son[a-z]+\s*=", text), path.name


def test_only_the_watchers_shared_files_reach_the_extension_apis():
    for path in sorted(UI.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        if path.name != "brainui.js":  # the watcher's own "Set it up" anchor: a new tab in Brave is right
            assert '"_blank"' not in text and "'_blank'" not in text, path.name
        if path.name not in ("link.js", "brainui.js"):
            assert "chrome." not in text, path.name


def test_nav_js_stays_out_of_the_watcher():
    from ai_browser.brain.watcher import WATCHER_SHARED

    assert "nav.js" not in WATCHER_SHARED
    for name in WATCHER_SHARED:
        assert "nav.js" not in (UI / name).read_text(encoding="utf-8"), name


def test_ai_browser_mode_is_gone_from_the_pages():
    assert "Agents browse in AI Browser" not in (UI / "home.js").read_text(encoding="utf-8")
    assert "No tabs open besides AI Home" not in (UI / "tablist.js").read_text(encoding="utf-8")
