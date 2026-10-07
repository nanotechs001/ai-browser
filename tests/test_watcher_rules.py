"""What a page may send: the server's rights table, written down twice (in app/server.py and here). Brave's watcher,
the one other role there was, retired with its extension: only AI Browser's own pages send anything now, and a socket
from anywhere else is refused before it can."""

import inspect
import json
from pathlib import Path

import pytest
from websockets.asyncio.client import connect

from test_app_server import CHECK_REPORT, WATCHER, recv, refused_socket, socket_url, started, until, wait_for
from test_bridge import EVENTS
from ui_socket import ui_socket

# The table of watcher-safety's spec, plus cdp-relay's, brain-delegation's, app-window's, AI accounts' and agent powers'
# rows, every one for AI Browser's own pages. A row added to MESSAGE_RULES fails here until this copy says the same.
SENDS = {
    "hello", "brain", "draft", "approve", "hand", "done", "tell", "watch_set", "watch_remove", "style", "watch_pick",
    "workflow_run", "workflows", "workflow_save", "workflow_delete", "permission",
    "tools", "tool_set", "tool_allow", "tool_forget", "skills", "skill_draft", "skill_save",
    "hearing", "hearing_download", "hearing_cancel", "listen_start", "listen_chunk", "listen_end", "listen_cancel",
    "brain_ask", "brain_confirm", "brain_dismiss", "tell_confirm", "tell_dismiss",
    "check_continue", "check_skip", "check_show", "brave_connect", "hand_tab", "take_back", "browser_disconnect",
    "new_task", "send", "stop", "close", "model", "watch", "events", "thumbs", "settings_set", "open_url",
    "accounts", "account_add", "account_add_existing", "account_remove", "account_default", "account_brain",
    "account_signin", "account_move",  # AI accounts
    "this_page", "show_app",  # the floating chat (native-app part c)
    "folder_choose", "folder_trust", "permission_rules", "permission_rule_remove",  # agent powers
    "workspaces", "workspace_save", "workspace_delete", "workspace_assign",  # the new look's workspaces
    "attach_start", "attach_chunk", "attach_drop",  # the new look's Attach
    "skill_block",  # the new look's Knowledge
    "agent_auto",  # Auto-approve in its folder: the drawer's switch, the user's click only
}
RETIRED = {"items", "replied", "thread", "filled", "reader_status", "watcher_caps", "tab_grouped", "pause",
           "ai_keyword"}  # the watcher's own: gone with it


def test_the_message_table_has_exactly_the_written_down_types():
    from ai_browser.app.server import MESSAGE_RULES

    assert set(MESSAGE_RULES) == SENDS and not set(MESSAGE_RULES) & RETIRED
    assert all(rule.app for rule in MESSAGE_RULES.values())


@pytest.mark.parametrize("kind", sorted(SENDS | RETIRED))
def test_only_ai_browsers_own_pages_send_anything(kind):
    from ai_browser.app.server import may_send

    sample = {"type": kind, "id": "a1", "item": "i1", "answer": "once", "adopt": "U1"}
    assert may_send("app", sample) is (kind in SENDS)
    for role in ("watcher", "none", "", "APP"):
        assert may_send(role, sample) is False, role


@pytest.mark.parametrize("message", [{"type": "nonsense"}, {}, {"id": "a1"}, {"type": ["hello"]}, {"type": 7},
                                     {"type": None}, {"type": {"hello": 1}}, {"type": "HELLO"}, {"type": " hello"},
                                     {"type": "x" * 10_000}])
def test_an_unknown_or_malformed_type_is_refused(message):
    from ai_browser.app.server import may_send

    assert may_send("app", message) is False


async def test_a_socket_from_the_old_watcher_is_refused_before_it_can_send(fake_claude, tmp_path):
    from fake_brave import FakeBrave, add_agent

    server, url = await started(fake_claude, tmp_path, EVENTS)
    brave = FakeBrave([{"target": "U1", "url": "https://shop.example/", "title": "Shop"}])
    server.attach_brave(brave)
    agent = add_agent(server.agents)
    try:
        for origin in (WATCHER, "chrome-extension://anything", "https://evil.example", None):
            assert await refused_socket(connect(socket_url(server, url), origin=origin, proxy=None)) == 4403
        assert agent.adopted == [] and brave.connects == 0 and server.window_count == 0
        assert set(server._roles.values()) <= {"app"}
    finally:
        await server.stop()


async def test_a_malformed_type_is_dropped_and_the_socket_goes_on(fake_claude, tmp_path):
    from fake_brave import add_agent

    server, url = await started(fake_claude, tmp_path, EVENTS)
    add_agent(server.agents)
    bad = [{"type": ["events"]}, {"type": 7}, {"type": None}, {"type": {"events": 1}}, {"id": "a1"},
           {"type": "x" * 10_000}, {"type": "items", "site": "gmail", "items": [{"id": "t1"}]}]
    try:
        async with ui_socket(server, url) as ws:
            await ws.send(json.dumps({"type": "hello", "view": "home"}))
            await until(ws, lambda m: m["type"] == "snapshot")
            for message in bad:
                await ws.send(json.dumps(message))
            await ws.send(json.dumps({"type": "events", "id": "a1"}))
            seen = await until(ws, lambda m: m["type"] == "agent_events")
            assert not any(m["type"] == "error" for m in seen)
    finally:
        await server.stop()


def test_rights_go_by_role_through_the_table():
    from ai_browser.app.server import AppServer

    for method in (AppServer._handle, AppServer._brain_command):  # no origin test of their own
        assert "origin" not in inspect.getsource(method), method.__name__
    assert not hasattr(AppServer, "allow_watcher") and not hasattr(AppServer, "_from_watcher")


async def test_show_me_with_no_tab_source_does_nothing(fake_claude, tmp_path):  # watcher safety's Review Focus 5
    from fake_brave import add_agent

    server, url = await started(fake_claude, tmp_path, EVENTS)  # no browser link attached
    agents = server.agents
    add_agent(agents)
    agents.tab_event("a1", "tab_opened", "T1")
    agents.check_event("a1", {**CHECK_REPORT, "target": "T1"})
    try:
        async with ui_socket(server, url) as page:
            await page.send(json.dumps({"type": "hello", "view": "home"}))
            await recv(page)
            await page.send(json.dumps({"type": "check_show", "id": "a1"}))
            await page.send(json.dumps({"type": "check_continue", "id": "a1"}))  # the socket goes on
            await wait_for(lambda: agents.agents["a1"].check is None)
    finally:
        await server.stop()


def test_the_readme_says_what_ai_home_lists_and_where_always_allow_is():
    text = " ".join((Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8").split())
    assert ("**Tabs:** the web tabs of the Brave profile where agents browse (Settings → **Where agents browse**; until "
            "you pick one, the profile you used last), each marked with whose it is") in text
    assert "Other profiles and private windows are only counted, never listed." in text
    assert "**Always allow** is remembered in `~/.ai-browser/tools.json`" in text
    assert "watcher's Brain page" not in text  # the extension retired
    assert ("AI Home shows the ones in the agents' profile (other profiles and private windows only as a count)"
            in text)
