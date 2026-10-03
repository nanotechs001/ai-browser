"""What a page may send and what a watcher socket may get: the server's two tables, each written down twice (in
app/server.py and here), and Brave's watcher held to them over real sockets."""

import pytest

ONLY_WITH_ITEM, ONCE_OR_DENY = "only with an item", "only once or deny"

# The table of watcher-safety's spec ("the table of what pages may send"), plus cdp-relay's row: (app, watcher).
# A row added to MESSAGE_RULES fails here until this copy says the same.
SENDS = {
    "hello": (True, True),
    **{kind: (False, True) for kind in ("items", "replied", "thread", "filled", "reader_status", "watcher_caps",
                                        "tab_grouped")},
    **{kind: (True, True) for kind in ("brain", "draft", "approve", "hand", "done", "tell", "watch_set",
                                       "watch_remove", "pause", "style")},
    "workflow_run": (True, ONLY_WITH_ITEM),
    **{kind: (True, False) for kind in ("workflows", "workflow_save", "workflow_delete")},
    "permission": (True, ONCE_OR_DENY),
    **{kind: (True, False) for kind in ("tools", "tool_set", "tool_allow", "tool_forget")},
    **{kind: (True, False) for kind in ("skills", "skill_draft", "skill_save")},
    **{kind: (True, False) for kind in ("hearing", "hearing_download", "hearing_cancel", "listen_start",
                                        "listen_chunk", "listen_end", "listen_cancel")},
    **{kind: (True, False) for kind in ("brain_ask", "brain_confirm", "brain_dismiss")},
    "check_continue": (True, True),
    "check_skip": (True, False),
    "check_show": (True, True),
    **{kind: (True, False) for kind in ("brave_connect", "hand_tab", "take_back")},
    "browser_disconnect": (True, False),  # cdp-relay: Disconnect in AI Home's list of connected clients
    "new_task": (True, False),  # with or without adopt
    **{kind: (True, False) for kind in ("send", "stop", "close", "model")},
    **{kind: (True, False) for kind in ("watch", "events", "thumbs")},
}


def test_the_message_table_has_exactly_the_written_down_types():
    from ai_browser.app.server import MESSAGE_RULES

    assert set(MESSAGE_RULES) == set(SENDS)
    assert len(SENDS) == 55
    assert sum(1 for app, _ in SENDS.values() if app) == 48
    assert sum(1 for _, watcher in SENDS.values() if watcher) == 22  # the two conditional rows count as allowed


@pytest.mark.parametrize("kind", sorted(SENDS))
def test_the_message_table_covers_every_type_for_both_roles(kind):
    from ai_browser.app.server import may_send

    app, watcher = SENDS[kind]
    sample = {"type": kind, "id": "a1"}
    assert may_send("app", sample) is app
    if watcher == ONLY_WITH_ITEM:  # the inbox's Run <workflow> on a message; a bare run stays in AI Home
        assert may_send("watcher", {**sample, "item": "i1"}) is True
        for bad in ({}, {"item": ""}, {"item": 3}, {"item": ["i1"]}, {"item": None}):
            assert may_send("watcher", {**sample, **bad}) is False, bad
    elif watcher == ONCE_OR_DENY:  # a lasting Always allow stays in AI Home's Tools
        for answer in ("once", "deny"):
            assert may_send("watcher", {**sample, "answer": answer}) is True
        for bad in ({"answer": "always"}, {}, {"answer": "ONCE"}, {"answer": ["once"]}, {"answer": None}):
            assert may_send("watcher", {**sample, **bad}) is False, bad
    else:
        assert may_send("watcher", sample) is watcher
    if kind == "new_task":  # with or without adopt: never from the watcher
        assert may_send("watcher", {**sample, "adopt": "U1"}) is False
        assert may_send("app", {**sample, "adopt": "U1"}) is True


@pytest.mark.parametrize("message", [{"type": "nonsense"}, {}, {"id": "a1"}, {"type": ["hello"]}, {"type": 7},
                                     {"type": None}, {"type": {"hello": 1}}, {"type": "HELLO"}, {"type": " hello"},
                                     {"type": "x" * 10_000}])
def test_an_unknown_or_malformed_type_is_refused_for_both_roles(message):
    from ai_browser.app.server import may_send

    assert may_send("app", message) is False
    assert may_send("watcher", message) is False


def test_only_the_two_roles_exist():
    from ai_browser.app.server import may_send

    assert may_send("stranger", {"type": "hello"}) is False and may_send("", {"type": "hello"}) is False
