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
        "panel.css", "panel.html", "panel.js"]
    assert SHARED_SOURCE == UI and all((UI / name).is_file() for name in WATCHER_SHARED)


def test_the_watchers_shared_files_are_byte_equal_to_app_uis(tmp_path):
    from ai_browser.brain.watcher import WATCHER_SHARED, prepare_watcher

    folder, _ = prepare_watcher(tmp_path, "http://127.0.0.1:8792", "token")
    for name in WATCHER_SHARED:
        assert (folder / name).read_bytes() == (UI / name).read_bytes(), name


INLINE_SCRIPT = re.compile(r"<script(?![^>]*\ssrc=)[^>]*>", re.IGNORECASE)


def test_the_window_pages_are_all_there():
    for name in ("app.html", "app.js", "app.css", "home.html", "mission.html", "settings.html", "setup.html",
                 "nav.js"):
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
        if path.name not in ("link.js", "brainui.js"):
            assert "chrome." not in path.read_text(encoding="utf-8"), path.name


OPENS_A_WINDOW = re.compile(r"""\bwindow\s*\.\s*open\b|\bopen\s*\(\s*["'`]|["'`]popup|\bnoopener\b""")


def test_no_page_of_ours_opens_a_window():
    """Our pages are tabs of AI Browser's window (app.js shows them, nav.js asks it for one): no script opens a window
    or a popup, for our pages or anyone's, and "_blank" is left only in brainui.js, the watcher's own "Set it up"
    anchor in Brave, where a new tab is right. No page has a link target of its own."""
    for path in sorted(UI.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        assert not OPENS_A_WINDOW.search(text), path.name
        if path.name != "brainui.js":
            assert '"_blank"' not in text and "'_blank'" not in text, path.name
    for path in sorted(UI.glob("*.html")):
        assert not re.search(r"\starget\s*=", path.read_text(encoding="utf-8"), re.IGNORECASE), path.name
    nav = (UI / "nav.js").read_text(encoding="utf-8")
    assert "export function openTab(" in nav and "WINDOWS" not in nav and "focusHome" not in nav
    for name in ("home.js", "mission.js", "settings.js"):
        text = (UI / name).read_text(encoding="utf-8")
        assert "openWindow" not in text and "focusHome" not in text and "openTab" in text, name


def test_nav_js_stays_out_of_the_watcher():
    from ai_browser.brain.watcher import WATCHER_SHARED

    assert "nav.js" not in WATCHER_SHARED
    for name in WATCHER_SHARED:
        assert "nav.js" not in (UI / name).read_text(encoding="utf-8"), name


def test_ai_browser_mode_is_gone_from_the_pages():
    assert "Agents browse in AI Browser" not in (UI / "home.js").read_text(encoding="utf-8")
    assert "No tabs open besides AI Home" not in (UI / "tablist.js").read_text(encoding="utf-8")


def test_link_js_lists_no_debugger_targets():
    assert "chrome.debugger" not in (UI / "link.js").read_text(encoding="utf-8")  # the watcher has no debugger


def test_every_page_in_the_window_keeps_the_close_tab_key():
    """Command-W (Ctrl+W elsewhere) would close AI Browser's whole window, and stop it: every page the tab menu shows
    keeps that key and asks the menu to close its tab instead (the browser tests show what each does with it)."""
    nav = (UI / "nav.js").read_text(encoding="utf-8")
    assert "export function closeTabKey(" in nav and "export function guardCloseKey(" in nav
    for name in ("home.js", "mission.js", "settings.js"):
        assert "guardCloseKey();" in (UI / name).read_text(encoding="utf-8"), name
    assert "closeTabKey" in (UI / "app.js").read_text(encoding="utf-8")
    assert '"close-tab"' in (UI / "setup.js").read_text(encoding="utf-8")  # setup.js imports nothing: it opens in Brave
