"""AI Browser's pages, read as files: where they live, and (from Task 14) what they never do."""

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
