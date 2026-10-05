"""Part c of AI Browser's own app (the floating chat) builds on part a (the Electron shell) and part b (the
extension's jobs, merged first) through a few names. This pins the ones part c uses and keeps, so no task starts on a
name the merged code spells differently, or before part b is in."""

import inspect
from pathlib import Path

SRC = Path(__file__).parents[1] / "src" / "ai_browser"
UI = SRC / "app" / "ui"
ELECTRON = SRC / "desktop" / "electron"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_part_a_left_the_seams_this_plan_fills():
    from ai_browser.desktop import assemble, launch, stage

    main = text(ELECTRON / "main.js")
    for needed in ("function makeWindow(kind, options) {", "function showWindow(kind) {", "function answerActions() {",
                   "function useShortcut(value, request) {", "function lockContents(contents) {",
                   "function makeTray() {", 'label: "Show chat"', "const ACTIONS = new Map(",
                   "frame !== event.sender.mainFrame || policy.originOf(frame.url) !== own",
                   "if (given && UNPACKAGED) return given.slice(PROFILE.length);", 'app.on("before-quit", () => {'):
        assert needed in main, needed
    assert 'contextBridge.exposeInMainWorld("aib", Object.freeze(bridge));' in text(ELECTRON / "preload.js")
    policy = text(ELECTRON / "policy.js")
    assert "function mayNavigate(url, own, isMainFrame" in policy and "module.exports = {" in policy
    assert {"package.json", "main.js", "preload.js", "policy.js", "line.js"} <= set(stage.APP_FILES)
    assert "NSMicrophoneUsageDescription" in assemble.PLIST and isinstance(launch.UPDATED, str)


def test_part_b_is_merged_with_its_gate_and_its_readers():
    from ai_browser.app import bravelink, inworld, server
    from ai_browser.brain import readers

    assert not (SRC / "app" / "watcher").exists()  # part b retired the watcher: it is merged
    assert "ai_keyword" not in server.MESSAGE_RULES
    assert {"new_task", "hand_tab", "brain_ask", "open_url", "settings_set"} <= set(server.MESSAGE_RULES)
    for name in ("may_run", "run_reader", "tabs", "client", "scope"):
        assert callable(getattr(bravelink.BraveLink, name)), name
    assert bravelink.USERS == ("you", "brain") and bravelink.WEB == ("http://", "https://")
    assert callable(inworld.run) and issubclass(inworld.WorldError, RuntimeError)
    assert readers.FILES[0] == "common.js" and callable(readers.call) and readers.MISSING
    assert server.WorldError is inworld.WorldError  # the server catches the gate's refusals by this name
    for name in ("_talk_command", "_answer", "_handle", "_handable", "_hand", "_open_url", "_send_all", "_job",
                 "attach_brave", "attach_desktop", "_snapshot", "_page"):
        assert callable(getattr(server.AppServer, name)), name
    assert server.PAGES["/app"] == "app.html" and server.AGENT_ID.match("a12")


def test_the_brain_and_the_pages_have_what_the_chat_reuses():
    from ai_browser.brain import service, talk

    assert talk.SAY_LIMIT == 240 and callable(talk.talk_prompt) and callable(talk.parse_answer)
    assert {"text", "history", "state"} <= set(inspect.signature(talk.talk_prompt).parameters)
    assert "\n\nThe user's words: {text}" in talk.TALK and "\n\nAnswer with JSON only" in talk.TALK
    for name in ("respond", "_respond", "_ask_claude", "_dispatch", "_busy"):
        assert callable(getattr(service.BrainService, name)), name
    assert "export function mountTalk({ panel, micButton, link, voice," in text(UI / "talk.js")
    assert "export function guardLinks(link" in text(UI / "nav.js")
    accountui = text(UI / "accountui.js")
    assert "export function fillPicker(select, rows)" in accountui and "export function pickDefault(" in accountui
    assert "export function permissionCard(request, send, agentName" in text(UI / "permission.js")
    assert "export function checkCard(agent, send, { openLive = null } = {})" in text(UI / "check.js")
    assert "export function chipText(owner)" in text(UI / "tablist.js")
    chat = text(UI / "chat.js")
    assert "export function el(" in chat and "export function agentLabel(" in chat


def test_the_tests_have_the_helpers_this_plan_uses():
    import fake_brave
    import fake_desktop
    import test_ai_home_phase2
    import test_app_server
    import test_brain_talk
    import test_check_card
    import test_desktop_electron
    import test_desktop_js
    import test_home
    import test_inworld
    import test_talk
    import ui_socket

    for module, names in ((fake_brave, ("FakePort", "FakeBrave", "add_agent", "until")),
                          (fake_desktop, ("FakeDesktop",)),
                          (test_ai_home_phase2, ("ask_for_clickup", "answered")),
                          (test_app_server, ("started", "recv", "until", "with_brain", "quiet")),
                          (test_brain_talk, ("brain_for", "talk_calls")),
                          (test_check_card, ("checked", "recorded", "heard")),
                          (test_desktop_electron, ("started_app", "browser_ws", "page_at", "free_port")),
                          (test_desktop_js, ("run_js", "run_main", "names")),
                          (test_home, ("stack", "until", "open_page", "page_js", "evaluate")),
                          (test_inworld, ("linked",)),
                          (test_talk, ("talk_script", "talk_calls", "ask_typed")),
                          (ui_socket, ("ui_socket", "ui_cookie"))):
        for name in names:
            assert callable(getattr(module, name)), (module.__name__, name)
    assert test_brain_talk.TALKING == test_talk.TALKING == "talking with the user"
    assert test_desktop_js.START.startswith(b'{"type": "start"') and test_home.HOSTILE
