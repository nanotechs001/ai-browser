"""AI Browser's own app (part a) builds on wave B (the app window), the tab menu and AI accounts through a few names.
This pins them, so no task starts on a name the merged code spells differently, or before those are merged."""

import importlib.util
import inspect
from pathlib import Path

UI = Path(__file__).parents[1] / "src" / "ai_browser" / "app" / "ui"


def test_the_merged_code_has_the_names_this_plan_uses():
    from ai_browser import cli, platforms, settings, syncdir
    from ai_browser.app import run, server, window
    from ai_browser.config import LIVE_PORTS, home
    from ai_browser.hearing import model

    # wave B: the window, its launcher, and how run_app waits and ends
    assert issubclass(window.WindowError, RuntimeError) and callable(window.default_launcher)
    assert callable(window.choices)
    for name in ("_run", "_until_closed", "_first_window", "_call", "ready_text", "default_launcher"):
        assert callable(getattr(run, name)), name
    assert {"ready", "stop", "out", "browser", "window_browser", "launcher"} <= set(
        inspect.signature(run.run_app).parameters)
    assert run.WINDOW_GRACE and run.WINDOW_START_WAIT and "{name}" in run.NO_WINDOW
    # the server: its settings, the watcher's notifications, a bot check's tab
    assert {"model", "voice", "window_browser"} <= set(server.SETTING_KEYS)
    for name in ("_settings_payload", "_settings_set", "_forward", "_show_check", "_send_all", "_job"):
        assert callable(getattr(server.AppServer, name)), name
    assert server.CHECK_SITE.pattern == r"[a-z0-9.-]{1,253}"
    assert {"window_browser", "model", "voice"} <= set(settings.DEFAULTS)
    assert callable(settings.read_settings) and callable(settings.write_setting)
    assert callable(cli._doctor_setup) and callable(cli.main)
    assert callable(model.tls_context) and callable(model.urlopen_fetch)
    for name in ("shortcut", "lock_file", "replace", "rmtree", "unlink"):
        assert callable(getattr(platforms, name)), name
    assert callable(syncdir.write_atomic) and callable(home) and LIVE_PORTS == range(8770, 8791)
    # the tab menu: the window's own page (/app) shows ours in frames; a page asks it for a tab
    assert server.SHELL == "/app" and callable(server._page_headers)
    for name in ("app.html", "app.js", "nav.js", "talk.js", "settings.html", "settings.js", "mission.html",
                 "mission.js"):
        assert (UI / name).is_file(), name
    assert "export function openTab(" in (UI / "nav.js").read_text(encoding="utf-8")
    assert "export function browserName(" in (UI / "talk.js").read_text(encoding="utf-8")
    page = (UI / "settings.html").read_text(encoding="utf-8")
    assert 'id="window-section"' in page
    # AI accounts, built before this plan: its Settings section and its module
    assert 'id="accounts-section"' in page and importlib.util.find_spec("ai_browser.accounts") is not None


def test_the_tests_have_the_helpers_this_plan_uses():
    import conftest
    import fake_brave
    import fake_window
    import test_app_run
    import test_app_server
    import test_cli
    import test_home
    import test_tab_menu
    import ui_socket

    for module, names in (
            (conftest, ("fake_python", "symlink_or_skip", "file_mode", "_no_real_window", "_never_the_users_app_port")),
            (test_home, ("stack", "page", "until", "page_js", "open_page")),
            (test_tab_menu, ("connected", "frame", "tab", "active_is")),
            (test_app_run, ("servers", "quiet")), (test_app_server, ("started", "recv", "until")),
            (test_cli, ("_setup_env", "_browser_port_stand_in")), (fake_brave, ("add_agent",)),
            (fake_window, ("SocketWindow",)), (ui_socket, ("ui_socket",))):
        for name in names:
            assert callable(getattr(module, name)), (module.__name__, name)
    assert conftest.USERS_APP_PORT == 8792  # the tab menu's: no test's server takes it (Task 7 guards the doctor too)
