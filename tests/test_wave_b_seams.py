"""The app window (wave B) builds on the cdp-relay and wave A (watcher-safety, brain-delegation, browser-detection)
through a few names. This pins them, so no task starts on a name the merged code spells differently."""

import inspect


def test_the_relay_and_wave_a_have_the_names_this_plan_uses():
    from ai_browser import browsers
    from ai_browser.app import server
    from ai_browser.app.agents import Agent
    from ai_browser.app.bravelink import BraveLink
    from ai_browser.app.cdprelay import Relay, Tokens
    from ai_browser.app.tabs import TabWatch

    # watcher-safety: what a page may send, by role (the watcher's role retired with its extension)
    assert callable(server.may_send) and callable(server.AppServer._role)
    assert {"hello", "new_task", "hand_tab", "brave_connect", "check_show", "browser_disconnect",
            "tell_confirm"} <= set(server.MESSAGE_RULES)
    # the relay: one connection to the browser, a token per agent, BraveLink and TabWatch on it
    assert {"tokens", "watcher_id"} <= set(inspect.signature(BraveLink).parameters)
    assert "cdp" in inspect.signature(TabWatch).parameters
    assert callable(Tokens.mint) and callable(Relay.serve) and callable(server.AppServer.token_for)
    assert list(inspect.signature(server.AppServer.connect_brave).parameters)[:2] == ["self", "why"]
    # brain-delegation: an agent's number is its id's number
    assert isinstance(inspect.getattr_static(Agent, "number"), property)
    # browser-detection
    for name in ("installed", "os_default", "for_data_dir", "running", "all_data_dirs"):
        assert callable(getattr(browsers, name)), name
    assert {"facts", "binary", "bundle"} <= set(browsers.Installed.__dataclass_fields__)
