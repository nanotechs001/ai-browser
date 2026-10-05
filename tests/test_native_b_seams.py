"""Part b of AI Browser's own app builds on wave A (watcher safety, browser detection), the relay, the tab menu, AI
accounts and part a (the Electron shell) through a few names. This pins the ones part b keeps using, so no task
starts on a name the merged code spells differently, or before those are merged. (The names part b deletes are
quoted by the tasks that delete them.)"""

import inspect
from pathlib import Path

UI = Path(__file__).parents[1] / "src" / "ai_browser" / "app" / "ui"


def test_the_merged_code_has_the_names_this_plan_uses():
    from ai_browser import agentlink, browser, browsers, engine, grouping, settings, testpages
    from ai_browser.app import bravelink, cdprelay, server, tabs
    from ai_browser.brain import service, store
    from ai_browser.desktop.notes import note_for  # part a

    # part a: the app's notifications and its settings
    assert callable(note_for) and "shortcut" in settings.DEFAULTS and "shortcut" in server.SETTING_KEYS
    for name in ("_notify_desktop", "attach_desktop", "detach_desktop", "_desktop_payload", "_forward",
                 "_settings_payload", "_settings_set", "_snapshot", "_browser_info", "_tab_scope", "_tabs_message",
                 "_job", "_send_all", "_owner_of", "_own", "_record_tab", "_engine_body", "attach_brave",
                 "_brain_command", "_show_check", "_hand", "_socket_kind", "_unsubscribe", "_handle"):
        assert callable(getattr(server.AppServer, name)), name
    # AI accounts: its rows in the rights table
    assert server.ACCOUNT_MESSAGES and {"accounts", "account_add", "account_move"} <= set(server.MESSAGE_RULES)
    # wave A and the relay: the rights table, and what AI Browser's own client may do
    assert callable(server.may_send) and {"watch_set", "style", "approve"} <= set(server.MESSAGE_RULES)
    assert server.BRAIN_MESSAGES and server.SESSION_ID and server.AGENT_ID
    assert {"Page.createIsolatedWorld", "Page.getFrameTree"} <= cdprelay.SESSION_METHODS
    assert {"Runtime", "Input"} <= cdprelay.SESSION_DOMAINS and cdprelay.APP == "app"
    assert "Target.getBrowserContexts" in cdprelay.APP_COMMANDS
    for name in ("visible", "grants", "own_targets", "_grant", "_announce", "local", "_after"):
        assert callable(getattr(cdprelay.Relay, name)), name
    assert {"folder", "tokens", "app_origin"} <= set(inspect.signature(bravelink.BraveLink).parameters)
    for name in ("tabs", "scope", "agents_context", "page_text", "watch", "set_owner", "forget", "_changed",
                 "_readable", "_start_watch", "_drop_watch"):
        assert callable(getattr(bravelink.BraveLink, name)), name
    assert bravelink.USERS == ("you", "brain") and bravelink.WEB == ("http://", "https://")
    for name in ("pages", "tabs", "_text", "page_text", "watch"):
        assert callable(getattr(tabs.TabWatch, name)), name
    # the Brain
    for name in ("on_items", "on_replied", "reader_status", "on_thread", "on_filled", "approve", "draft", "set_watch",
                 "remove_watch", "set_style", "snapshot", "_settings", "_state"):
        assert callable(getattr(service.BrainService, name)), name
    assert [site for site, _, _ in store.BUILT_IN] == ["gmail", "slack", "asana"]
    for name in ("watch", "entry", "set_watch", "remove_watch", "set_style", "_read_watch", "_save_watch", "_write",
                 "_read"):
        assert callable(getattr(store.BrainStore, name)), name
    # where the AI's tabs open
    assert callable(grouping.Placer) and callable(agentlink.AgentLink.status)
    assert callable(browser.Browser.open_worker) and callable(engine.Engine._placement)
    # browser detection, settings, the test pages
    assert callable(browsers.profiles) and callable(browsers.plain_folder)
    assert callable(settings.Settings) and callable(settings.read_settings)
    assert callable(testpages.serve_host) and (testpages.PAGES / "brain" / "gmail.html").is_file()
    # the tab menu and the pages this plan adds to
    assert server.SHELL == "/app" and "export function openTab(" in (UI / "nav.js").read_text(encoding="utf-8")
    page = (UI / "settings.html").read_text(encoding="utf-8")
    assert 'id="accounts-section"' in page and 'id="app-section"' in page  # AI accounts', then part a's
    assert "function handle(" in (UI / "settings.js").read_text(encoding="utf-8")
    assert "export function mountBrain(" in (UI / "brainui.js").read_text(encoding="utf-8")
    assert "export function mountYourTabs(" in (UI / "tablist.js").read_text(encoding="utf-8")


def test_the_tests_have_the_helpers_this_plan_uses():
    import fake_brave
    import fake_desktop
    import test_app_server
    import test_home
    import test_tab_menu
    import ui_socket

    for module, names in ((fake_brave, ("FakePort", "FakeBrave", "FakeRelay", "add_agent", "until")),
                          (fake_desktop, ("FakeDesktop",)),
                          (test_app_server, ("started", "recv", "until", "quiet", "with_brain")),
                          (test_home, ("stack", "home", "until", "open_page", "page_js", "open_settings")),
                          (test_tab_menu, ("frame", "click_in")),
                          (ui_socket, ("ui_socket",))):
        for name in names:
            assert callable(getattr(module, name)), (module.__name__, name)
