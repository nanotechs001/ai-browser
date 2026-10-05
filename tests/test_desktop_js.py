"""AI Browser's own app's rules (desktop/electron/policy.js) and its line (line.js), run under Node.js: plain
functions with no Electron in them. Skipped where Node.js isn't installed, since the app itself never needs it. The
shortcuts' Python side (desktop/shortcut.py) needs no Node."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ELECTRON_DIR = Path(__file__).parents[1] / "src" / "ai_browser" / "desktop" / "electron"
NODE = shutil.which("node")
NEEDS_NODE = pytest.mark.skipif(NODE is None, reason="Node.js isn't installed (AI Browser's app never needs it)")
OWN = "http://127.0.0.1:8793"  # an app's own origin (a string only: no server listens)


def run_js(body: str):
    """`body` (JavaScript ending in a return; it may await) run with policy.js as `policy`, line.js as `line` and
    thispage.js as `thispage`; its value."""
    script = (f"const policy = require({json.dumps(str(ELECTRON_DIR / 'policy.js'))});\n"
              f"const line = require({json.dumps(str(ELECTRON_DIR / 'line.js'))});\n"
              f"const thispage = require({json.dumps(str(ELECTRON_DIR / 'thispage.js'))});\n"
              f"(async () => {{ {body} }})().then((value) => "
              "process.stdout.write(JSON.stringify(value === undefined ? null : value)));")
    done = subprocess.run([NODE, "-e", script], capture_output=True, timeout=60)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    return json.loads(done.stdout.decode("utf-8"))


@NEEDS_NODE
def test_frames_go_only_to_our_pages_and_live_views():  # Review Focus 3
    cases = [  # (address, main frame, allowed)
        (f"{OWN}/app", True, True), (f"{OWN}/home", False, True), (f"{OWN}/open?code=x", True, True),
        ("https://example.com/", True, False), ("https://example.com/", False, False),
        ("http://127.0.0.1:8770/live?token=abc_DEF-1", False, True),
        ("http://127.0.0.1:8770/live?token=abc", True, False),  # a live view in a frame only, never the window
        ("http://127.0.0.1:8790/live?token=abc", False, True), ("http://127.0.0.1:8791/live?token=abc", False, False),
        ("http://127.0.0.1:8770/elsewhere", False, False), ("http://localhost:8793/app", True, False),
        ("http://127.0.0.1:8794/app", True, False), ("file:///etc/passwd", True, False),
        ("data:text/html,hi", False, False), ("javascript:alert(1)", True, False)]
    got = run_js("return " + json.dumps([[url, main] for url, main, _ in cases])
                 + f".map(([url, main]) => policy.mayNavigate(url, {json.dumps(OWN)}, main));")
    assert got == [allowed for _, _, allowed in cases]
    assert run_js(f"return [policy.mayNavigate('{OWN}/app', null, true), policy.mayNavigate('{OWN}/app', '', true),"
                  f" policy.mayNavigate('{OWN}/app', {json.dumps(OWN)}, undefined)];") == [False, False, True]



@NEEDS_NODE
def test_the_chats_window_goes_only_to_the_chat_page():  # Plan decision 15
    cases = [(f"{OWN}/chat", True, True), (f"{OWN}/chat#ask", True, True), (f"{OWN}/chat?x=1", True, False),
             (f"{OWN}/home", True, False), (f"{OWN}/app", True, False), (f"{OWN}/open?code=x", True, False),
             (f"{OWN}/chat", False, False),  # no frame in the chat, not even its own page
             ("http://127.0.0.1:8770/live?token=abc", False, False), ("https://example.com/chat", True, False),
             ("http://localhost:8793/chat", True, False), ("http://me:pw@127.0.0.1:8793/chat", True, False),
             ("javascript:alert(1)", True, False)]
    got = run_js("return " + json.dumps([[url, main] for url, main, _ in cases])
                 + f".map(([url, main]) => policy.mayNavigate(url, {json.dumps(OWN)}, main, 'chat'));")
    assert got == [allowed for _, _, allowed in cases]
    others = run_js(f"return [policy.mayNavigate('{OWN}/home', {json.dumps(OWN)}, true, 'main'),"
                    f" policy.mayNavigate('{OWN}/chat', null, true, 'chat'), policy.CHAT_PATH];")
    assert others == [True, False, "/chat"]


@NEEDS_NODE
def test_the_chat_opens_where_it_was_left_while_a_screen_still_shows_it():
    got = run_js("""
      const screens = [{ x: 0, y: 0, width: 1440, height: 875 }, { x: 1440, y: -200, width: 1920, height: 1080 }];
      return [
        policy.chatBounds(null, screens),
        policy.chatBounds({ x: 100.4, y: 120, width: 420, height: 640 }, screens),
        policy.chatBounds({ x: 2000, y: -150, width: 400, height: 500 }, screens),
        policy.chatBounds({ x: 5000, y: 5000, width: 400, height: 500 }, screens),
        policy.chatBounds({ x: 100, y: -400, width: 400, height: 500 }, screens),
        policy.chatBounds({ x: 1400, y: 100, width: 400, height: 500 }, [screens[0]]),
        policy.chatBounds({ x: 10, y: 10, width: 100, height: 9000 }, screens),
        policy.chatBounds({ x: "a", y: 1 }, screens),
        policy.chatBounds(null, []),
        policy.CHAT_SIZE,
      ];""")
    assert got[0] == {"x": 1044, "y": 48, "width": 380, "height": 560}  # the first time: the main screen's right edge
    assert got[1] == {"x": 100, "y": 120, "width": 420, "height": 640}  # where the user left it
    assert got[2] == {"x": 2000, "y": -150, "width": 400, "height": 500}  # on the second screen
    assert got[3] == got[4] == got[5] == got[0]  # a screen that's gone, a title bar off the top, 40 px left on one
    assert got[6] == {"x": 10, "y": 10, "width": 320, "height": 4000}  # sizes kept within limits
    assert got[7] == got[0]  # a broken file: the first-time place
    assert got[8] == {"x": 884, "y": 48, "width": 380, "height": 560}  # no screen known: a 1280 × 800 one
    assert got[9] == {"width": 380, "height": 560, "minWidth": 320, "minHeight": 360}

@NEEDS_NODE
def test_only_the_microphone_and_copying_are_allowed_and_only_for_our_pages():
    own = json.dumps(OWN)
    got = run_js(f"""
      const page = {{ requestingUrl: {json.dumps(OWN + '/mission')}, isMainFrame: false }};
      const live = {{ requestingUrl: 'http://127.0.0.1:8770/live?token=x', isMainFrame: false }};
      const others = ['notifications', 'geolocation', 'display-capture', 'openExternal', 'hid', 'fullscreen',
                      'clipboard-read', 'unknown'];
      return [
        policy.mayRequest('media', {{ ...page, mediaTypes: ['audio'] }}, {own}),
        policy.mayRequest('media', {{ ...page, mediaTypes: ['audio', 'video'] }}, {own}),
        policy.mayRequest('media', {{ ...page, mediaTypes: ['video'] }}, {own}),
        policy.mayRequest('media', {{ ...page, mediaTypes: [] }}, {own}),
        policy.mayRequest('media', {{ ...live, mediaTypes: ['audio'] }}, {own}),
        policy.mayRequest('media', {{ ...page, mediaTypes: ['audio'] }}, null),
        policy.mayRequest('clipboard-sanitized-write', page, {own}),
        policy.mayRequest('clipboard-sanitized-write', live, {own}),
        ...others.map((name) => policy.mayRequest(name, page, {own})),
        policy.mayCheck('media', {own}, {{ mediaType: 'audio' }}, {own}),
        policy.mayCheck('media', {own}, {{ mediaType: 'video' }}, {own}),
        policy.mayCheck('media', 'http://127.0.0.1:8770', {{ mediaType: 'audio' }}, {own}),
        policy.mayCheck('clipboard-sanitized-write', {own}, {{}}, {own}),
        ...others.map((name) => policy.mayCheck(name, {own}, {{}}, {own})),
      ];""")
    assert got == [True, False, False, False, False, False, True, False, *[False] * 8,
                   True, False, False, True, *[False] * 8]


@NEEDS_NODE
def test_the_start_address_must_be_the_engines_own():
    got = run_js("""return ['http://127.0.0.1:8793/open?code=abc', 'https://127.0.0.1:8793/open?code=abc',
      'http://localhost:8793/open?code=abc', 'http://127.0.0.1/open?code=abc', 'http://127.0.0.1:8793/home',
      'http://me:pw@127.0.0.1:8793/open?code=abc', 'not an address', null].map((open) => policy.startOrigin(open));""")
    assert got == [OWN, None, None, None, None, None, None, None]


@NEEDS_NODE
def test_a_taken_shortcut_keeps_the_one_before():  # Review Focus 1
    got = run_js("""
      const others = new Set(['Alt+Shift+Space']); // another app holds this one
      const mine = [];
      const keys = {
        register(accelerator) { if (others.has(accelerator)) return false; mine.push(accelerator); return true; },
        unregister(accelerator) { mine.splice(mine.indexOf(accelerator), 1); },
      };
      const press = () => {};
      const first = policy.moveShortcut(keys, null, 'Alt+Space', press);
      const taken = policy.moveShortcut(keys, first.registered, 'Alt+Shift+Space', press);
      const other = policy.moveShortcut(keys, taken.registered, 'Control+Shift+Space', press);
      const off = policy.moveShortcut(keys, other.registered, null, press);
      const unknown = policy.moveShortcut(keys, off.registered, 'A', press);
      const broken = policy.moveShortcut({ register() { throw new Error('no'); }, unregister() {} }, null,
                                         'Alt+Space', press);
      return [first, taken, other, off, unknown, broken, mine];""")
    assert got == [{"registered": "Alt+Space", "ok": True, "why": ""},
                   {"registered": "Alt+Space", "ok": False, "why": "taken"},  # the one before is back
                   {"registered": "Control+Shift+Space", "ok": True, "why": ""},
                   {"registered": None, "ok": True, "why": ""},
                   {"registered": None, "ok": False, "why": "unknown"},  # only the offered ones: never a bare key
                   {"registered": None, "ok": False, "why": "taken"},
                   []]


@NEEDS_NODE
def test_a_notification_is_only_what_the_engine_wrote():
    got = run_js("""return [
      policy.notice({ id: 'n1', title: 'An agent is waiting for you',
                      body: 'It asks to use a tool. Answer in AI Home.' }),
      policy.notice({ id: 'n2', title: 'A\\u0007 bot check\\non x', body: 'b'.repeat(500) }),
      policy.notice({ id: 'x1', title: 'no', body: '' }),
      policy.notice({ id: 'n3', title: '', body: 'only a body' }),
      policy.notice({ id: 'n4', title: 42 }),
      policy.notice(null),
    ];""")
    assert got[0] == {"id": "n1", "title": "An agent is waiting for you",
                      "body": "It asks to use a tool. Answer in AI Home."}
    assert got[1]["title"] == "A  bot check on x" and len(got[1]["body"]) == 240
    assert got[2:] == [None, None, None, None]


@NEEDS_NODE
def test_the_line_reads_whole_json_objects_and_drops_the_rest():
    got = run_js("""
      const seen = [];
      const feed = line.splitter((message) => seen.push(message));
      feed('{"type":"start","open":"x"}\\n{"type":"no');
      feed('tify","id":"n1"}\\n');
      feed('not json\\n[1,2]\\n{"no":"type"}\\n\\n');
      feed('{"type":"long","text":"' + 'x'.repeat(70000) + '"}\\n{"type":"after"}\\n');
      feed('{"type":"growing","text":"' + 'y'.repeat(70000));
      feed('"}\\n{"type":"next"}\\n');
      return [seen, line.encode({ type: 'hello', pid: 7 }), line.lineOption(['electron', '--aib-line=/t/line']),
              line.lineOption(['electron']), line.lineOption(['--aib-line=']), line.LIMIT];""")
    assert got[0] == [{"type": "start", "open": "x"}, {"type": "notify", "id": "n1"}, {"type": "after"},
                      {"type": "next"}]
    assert got[1:] == ['{"type":"hello","pid":7}\n', "/t/line", None, None, 65536]


@NEEDS_NODE
def test_the_app_and_the_engine_agree_on_the_shortcuts_and_the_live_views():
    from ai_browser.config import LIVE_PORTS
    from ai_browser.desktop.shortcut import SHORTCUTS

    assert run_js("return [policy.SHORTCUTS, policy.LIVE_PORTS];") == [list(SHORTCUTS),
                                                                      [LIVE_PORTS.start, LIVE_PORTS.stop - 1]]


def test_shortcuts_are_written_the_way_each_keyboard_says_them():
    from ai_browser.desktop.shortcut import DEFAULT, SHORTCUT_ERROR, SHORTCUTS, label, state

    assert SHORTCUTS == ("Alt+Space", "Alt+Shift+Space", "Control+Shift+Space") and DEFAULT == "Alt+Space"
    assert SHORTCUT_ERROR == "The shortcut must be one of the offered ones, or Off"
    assert [label(one, "darwin") for one in SHORTCUTS] == ["⌥Space", "⌥⇧Space", "⌃⇧Space"]
    assert [label(one, "win32") for one in SHORTCUTS] == ["Alt+Space", "Alt+Shift+Space", "Ctrl+Shift+Space"]
    assert label(None, "darwin") == label(None, "win32") == "Off"
    said = {"value": "Alt+Space", "ok": False, "why": "taken", "pressed": False}
    assert state("Alt+Space", said, True) == "taken"
    assert state("Alt+Space", {**said, "ok": True}, True) == "ready"
    assert state("Alt+Space", {**said, "ok": True, "pressed": True}, True) == "works"
    assert state("Alt+Space", said, False) == "unknown"  # the app isn't running: nobody holds it
    assert state("Alt+Space", {**said, "value": "Alt+Shift+Space"}, True) == "unknown"  # it said about another one
    assert state("Alt+Space", {}, True) == "unknown"  # it hasn't said yet
    assert state(None, said, True) == "off"


@NEEDS_NODE
def test_without_an_engine_only_a_double_click_hears_how_to_start():
    got = run_js("return [[true, false], [false, true], [true, true], [false, false]].map(([line, start]) => "
                 "policy.withoutEngine({ line, start }));")
    assert got == ["quit", "quit", "quit", "box"]  # the engine went away: quit quietly; nobody started us: say how


# ---- "This page": the app reads Brave's front tab's address and title, with one fixed command per system -----------

@NEEDS_NODE
def test_this_page_runs_one_fixed_command_per_system():  # Testing: the exact command, per platform
    folder = "C:\\Users\\me\\.ai-browser\\desktop\\AI Browser\\resources\\app"
    got = run_js(f"""return [thispage.command("darwin"),
      thispage.command("win32", {json.dumps(folder)}, {json.dumps({"SystemRoot": "D:\\Windows"})}),
      thispage.command("win32", {json.dumps(folder)}, {json.dumps({"SystemRoot": "..\\evil"})}),
      thispage.command("win32", {json.dumps(folder)}, {{}}),
      thispage.command("linux"), thispage.MAC_SCRIPT];""")
    script = got[5]
    assert got[0] == {"file": "/usr/bin/osascript", "args": ["-l", "JavaScript", "-e", script]}
    powershell = ["-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                  folder + "\\thispage.ps1"]
    assert got[1] == {"file": "D:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "args": powershell}
    assert got[2] == got[3] == {"file": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
                                "args": powershell}  # an odd SystemRoot is never followed
    assert got[4] is None


@NEEDS_NODE
def test_the_mac_script_reads_two_things_and_never_opens_brave():  # Safety: AppleScript only reads
    script = run_js("return thispage.MAC_SCRIPT;")
    for needed in ('Application("com.brave.Browser")', "brave.running()", "brave.windows[0].activeTab", "tab.url()",
                   "tab.title()", "JSON.stringify", "-1743", "brave.windows[0].mode()", '"incognito"',
                   'state: "private"'):
        assert needed in script, needed
    assert script.index('state: "private"') < script.index("tab.url()")  # a private window's tab is never read
    assert script.index("brave.running()") < script.index("brave.windows")  # nothing is asked of a closed Brave
    for never in ("activate", "launch", "open", "make(", "close(", "quit", "reload", "execute", "doJavaScript",
                  "System Events", "keystroke", "click", "delete", "set ", "${", "doShellScript",
                  "includeStandardAdditions"):
        assert never not in script, never


@NEEDS_NODE
def test_only_an_address_and_a_title_come_back_and_a_hostile_title_stays_text():  # Review Focus 5
    hostile = '<img src=x onerror="alert(1)">\n"},{"state":"ok","url":"https://evil.example/"\u202e' + "x" * 5000
    outputs = [json.dumps({"state": "ok", "url": "https://shop.example/cart", "title": "Cart", "extra": "dropped"}),
               json.dumps({"state": "ok", "url": "https://shop.example/", "title": hostile}) + "\n",
               json.dumps({"state": "closed"}), json.dumps({"state": "denied"}), json.dumps({"state": "nowindow"}),
               json.dumps({"state": "launch"}), "not json", "", json.dumps([1]), json.dumps({"state": "ok", "url": 7}),
               "\ufeff" + json.dumps({"state": "closed"})]
    got = run_js(f"return {json.dumps(outputs)}.map((out) => thispage.parse(out));")
    assert got[0] == {"state": "ok", "url": "https://shop.example/cart", "title": "Cart"}
    assert got[1]["url"] == "https://shop.example/" and len(got[1]["title"]) == 300
    assert got[1]["title"].startswith('<img src=x onerror="alert(1)"> "},{"state":"ok"')  # text: never parsed again
    assert "\n" not in got[1]["title"]
    assert got[2:] == [{"state": "closed"}, {"state": "denied"}, {"state": "nowindow"}, {"state": "failed"},
                       {"state": "failed"}, {"state": "failed"}, {"state": "failed"},
                       {"state": "ok", "url": "", "title": ""}, {"state": "closed"}]


@NEEDS_NODE
def test_brave_closed_denied_slow_and_broken_answers_are_plain_states():  # Review Focus 2 and 3
    got = run_js("""
      const answers = [
        { error: "", stdout: '{"state":"closed"}\\n', stderr: "" },
        { error: "failed", stdout: "",
          stderr: "execution error: Error: Not authorized to send Apple events to Brave Browser. (-1743)" },
        { error: "", stdout: '{"state":"denied"}', stderr: "" },
        { error: "slow", stdout: "", stderr: "" },
        { error: "failed", stdout: "", stderr: "boom" },
      ];
      const ran = [];
      const runner = async (file, args) => { ran.push([file, args.length]); return answers.shift(); };
      const states = [];
      for (let at = 0; at < 5; at += 1) states.push((await thispage.read("darwin", runner)).state);
      states.push((await thispage.read("darwin", async () => { throw new Error("spawn ENOENT"); })).state);
      states.push((await thispage.read("linux", runner)).state);
      return [states, ran];""")
    assert got[0] == ["closed", "denied", "denied", "slow", "failed", "failed", "unsupported"]
    private = run_js("""return [thispage.parse('{"state":"private"}'), thispage.STATES.includes("private")];""")
    assert private == [{"state": "private"}, True]  # a private window: its address and title never leave the app
    assert got[1] == [["/usr/bin/osascript", 4]] * 5  # Linux: nothing runs at all


@NEEDS_NODE
def test_the_command_runs_without_a_shell_and_a_slow_one_is_stopped():
    got = run_js("""
      const node = process.execPath;
      return [
        await thispage.run(node, ["-e", "process.stdout.write(process.argv[1])", "$(touch pwned); echo hi"]),
        await thispage.run(node, ["-e", "setTimeout(() => {}, 10000)"], 300),
        await thispage.run(node, ["-e", "process.stdout.write('x'.repeat(200000))"]),
        await thispage.run(node, ["-e", "process.exit(3)"]),
      ];""")
    assert got[0] == {"error": "", "stdout": "$(touch pwned); echo hi", "stderr": ""}  # one argument, as given
    assert got[1]["error"] == "slow" and got[2]["error"] == "failed" and got[3]["error"] == "failed"


# main.js itself, under a stand-in Electron (tests/electron_stub.js) that records every call and ends the run on
# app.exit or app.quit. Nothing is shown, and nothing registers with the system.
STUB = Path(__file__).parent / "electron_stub.js"
START = b'{"type": "start", "open": "http://127.0.0.1:8793/open?code=the-code", "shortcut": null}\n'


def run_main(tmp_path, *switches, feed=None, pause=0.0, **plan) -> list:
    """main.js on the stand-in: the calls it made, in order. `feed` goes to its stdin (the line, when no
    --aib-line names one), and the line ends `pause` seconds later; with no feed, stdin is empty."""
    import os
    import time

    out = tmp_path / "calls.json"
    env = {**os.environ, "STUB_PLAN": json.dumps(plan), "STUB_OUT": str(out)}
    process = subprocess.Popen([NODE, str(STUB), str(ELECTRON_DIR / "main.js"),
                                f"--aib-profile={tmp_path / 'profile'}", *switches],
                               stdin=subprocess.PIPE if feed is not None else subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)
    if feed is not None:
        process.stdin.write(feed)
        process.stdin.flush()
        time.sleep(pause)
        process.stdin.close()
    process.wait(timeout=60)
    assert process.returncode == 0, process.stderr.read().decode("utf-8", "replace")
    process.stderr.close()
    return json.loads(out.read_text(encoding="utf-8"))


def names(calls: list) -> list[str]:
    return [call[0] for call in calls]


@NEEDS_NODE
def test_a_double_click_start_lets_go_of_the_lock_before_it_says_how(tmp_path):  # F2 (b)
    calls = run_main(tmp_path)  # no line, and nothing on stdin: nobody started it
    said = names(calls)
    assert ["dialog.showMessageBox", "Start AI Browser from a terminal"] in calls
    assert said.index("app.releaseSingleInstanceLock") < said.index("dialog.showMessageBox")  # a real start can begin
    assert "new BrowserWindow" not in said and calls[-1] == ["app.exit", 0]


@NEEDS_NODE
@pytest.mark.posix_only  # the Mac's line is a socket
def test_an_engine_gone_before_its_start_quits_quietly(tmp_path):  # F2 (a)
    import socket
    import tempfile
    import threading

    folder = Path(tempfile.mkdtemp(prefix="aib-"))  # a short path: a socket's is limited
    server = socket.socket(socket.AF_UNIX)
    try:
        server.bind(str(folder / "line"))
        server.listen()

        def engine_goes():  # it takes the app's connection, then ends without a start (Ctrl-C, a crash)
            connection, _ = server.accept()
            connection.close()

        threading.Thread(target=engine_goes, daemon=True).start()
        calls = run_main(tmp_path, f"--aib-line={folder / 'line'}")
    finally:
        server.close()
        (folder / "line").unlink(missing_ok=True)
        folder.rmdir()
    assert "dialog.showMessageBox" not in names(calls) and "new BrowserWindow" not in names(calls)
    assert calls[-1] == ["app.exit", 0]


@NEEDS_NODE
def test_once_the_start_has_come_there_is_never_a_box(tmp_path):  # F2 (c)
    calls = run_main(tmp_path, feed=START, ready_after=1000)  # the line ends before Electron is ready
    assert "dialog.showMessageBox" not in names(calls) and "new BrowserWindow" not in names(calls)
    assert calls[-1] == ["app.exit", 0]


@NEEDS_NODE
def test_the_engine_gone_after_the_start_quits_the_app(tmp_path):  # Review Focus 4
    calls = run_main(tmp_path, feed=START, pause=0.5)
    said = names(calls)
    assert ["win.loadURL", "http://127.0.0.1:8793/open?code=the-code"] in calls and "new Tray" in said
    assert "dialog.showMessageBox" not in said and calls[-1] == ["app.quit"]


# The floating chat: its window, the shortcut and the menu-bar icon's Show chat (on the stand-in Electron)
START_ALT_SPACE = b'{"type": "start", "open": "http://127.0.0.1:8793/open?code=the-code", "shortcut": "Alt+Space"}\n'
CHAT = "http://127.0.0.1:8793/chat"


def chat_made(calls) -> list:
    return [call for call in calls if call[:2] == ["new BrowserWindow", "AI Browser chat"]]


def shown(calls) -> list:
    return [call for call in calls if call[0] in ("win.show", "win.hide", "app.hide")]


@NEEDS_NODE
def test_the_shortcut_shows_and_hides_the_chat(tmp_path):  # Review Focus 1, Plan decision 2
    import sys

    calls = run_main(tmp_path, feed=START_ALT_SPACE, pause=2.0,
                     steps=[[300, "press"], [600, "press"], [900, "press"], [1100, "blur"], [1300, "press"]])
    assert ["globalShortcut.register", "Alt+Space"] in calls
    [made] = chat_made(calls)  # one chat window, made at the first press
    assert made[2] == {"x": 1044, "y": 48, "width": 380, "height": 560, "alwaysOnTop": True, "skipTaskbar": True}
    assert [call for call in calls if call[0] == "win.loadURL"] == [
        ["win.loadURL", "http://127.0.0.1:8793/open?code=the-code"], ["win.loadURL", CHAT]]  # its page loads once
    back = [["app.hide"]] if sys.platform == "darwin" else []  # a Mac: the app that was in front gets the keys back
    assert shown(calls) == [["win.show", "AI Browser chat"], ["win.hide", "AI Browser chat"], *back,
                            ["win.show", "AI Browser chat"],
                            ["win.show", "AI Browser chat"]]  # shown, but behind the user's click: in front again
    assert ["win.show", "AI Browser"] not in calls  # the shortcut never brings up the main window


@NEEDS_NODE
def test_show_chat_works_when_another_app_holds_the_shortcut(tmp_path):  # Review Focus 1
    calls = run_main(tmp_path, feed=START_ALT_SPACE, pause=1.5, taken=["Alt+Space"],
                     steps=[[300, "press"], [500, "tray", "Show chat"], [800, "tray", "Open AI Browser"]])
    assert ["globalShortcut.register", "Alt+Space"] in calls and ["press"] in calls  # the press reached nobody
    assert ["tray", "Show chat", True] in calls  # enabled now
    assert calls.index(["win.show", "AI Browser chat"]) > calls.index(["tray", "Show chat", True])
    assert ["win.show", "AI Browser"] in calls  # Open AI Browser: the main window, from the menu-bar icon


@NEEDS_NODE
def test_the_chats_window_shows_its_page_and_nothing_else(tmp_path):  # Plan decision 15
    tries = [["chat", "http://127.0.0.1:8793/home", False], ["chat", CHAT, True], ["chat", CHAT + "#ask", True],
             ["chat", CHAT + "?x=1", False], ["chat", "https://example.com/", False],
             ["chat", "http://127.0.0.1:8793/open?code=x", False], ["main", "http://127.0.0.1:8793/home", True],
             ["main", "https://example.com/", False]]
    calls = run_main(tmp_path, feed=START, pause=1.5,
                     steps=[[300, "tray", "Show chat"], *[[500 + 40 * at, "navigate", kind, url]
                                                          for at, (kind, url, _) in enumerate(tries)]])
    assert [call[1:] for call in calls if call[0] == "navigate"] == tries


@NEEDS_NODE
def test_a_refused_chat_page_loads_again_the_next_time(tmp_path):
    calls = run_main(tmp_path, feed=START, pause=1.5, statuses={CHAT: [403, 200]},
                     steps=[[300, "tray", "Show chat"], [600, "tray", "Show chat"], [900, "tray", "Show chat"]])
    assert [call for call in calls if call == ["win.loadURL", CHAT]] == [["win.loadURL", CHAT]] * 2  # not a third


@NEEDS_NODE
def test_the_chat_opens_where_it_was_left(tmp_path):  # Decision 4: it remembers its place and size
    from conftest import file_mode

    place = {"x": 100, "y": 120, "width": 420, "height": 640}
    run_main(tmp_path, feed=START, pause=1.5, steps=[[300, "tray", "Show chat"], [500, "move", place]])
    kept = tmp_path / "profile" / "chat.json"
    assert json.loads(kept.read_text(encoding="utf-8")) == place and file_mode(kept) in (0o600, None)
    again = run_main(tmp_path, feed=START, pause=1.0, steps=[[300, "tray", "Show chat"]])
    assert chat_made(again)[0][2] == {**place, "alwaysOnTop": True, "skipTaskbar": True}
    kept.write_text(json.dumps({"x": 5000, "y": 5000, "width": 420, "height": 640}), encoding="utf-8")  # gone screen
    gone = run_main(tmp_path, feed=START, pause=1.0, steps=[[300, "tray", "Show chat"]])
    assert chat_made(gone)[0][2] == {"x": 1044, "y": 48, "width": 380, "height": 560, "alwaysOnTop": True,
                                     "skipTaskbar": True}


@NEEDS_NODE
def test_only_the_shown_chat_learns_which_tab_and_one_fixed_command_runs(tmp_path):  # Plan decision 7
    page = json.dumps({"state": "ok", "url": "https://shop.example/", "title": "Shop"})
    calls = run_main(tmp_path, feed=START, pause=2.0, stdout=page, steps=[
        [300, "invoke", "main", "thisPage"],  # AI Browser's window never learns it
        [400, "invoke", "main", "chat", "show"],  # but it may show the chat
        [700, "invoke", "chat", "thisPage"],
        [800, "invoke_framed", "chat", "thisPage"],  # a frame inside the chat gets nothing at all
        [1000, "invoke", "chat", "chat", "hide"],
        [1200, "invoke", "chat", "thisPage"],  # hidden: Brave isn't read
        [1300, "invoke", "main", "chat", "sideways"]])
    expected = run_js(f"return thispage.command(process.platform, {json.dumps(str(ELECTRON_DIR))});")
    seen = {"state": "ok", "url": "https://shop.example/", "title": "Shop"} if expected else {"state": "unsupported"}
    assert [call[1:] for call in calls if call[0] == "answer"] == [
        ["thisPage", {"state": "hidden"}], ["chat", None], ["thisPage", seen], ["thisPage", None], ["chat", None],
        ["thisPage", {"state": "hidden"}], ["chat", None]]
    runs = [call[1:] for call in calls if call[0] == "execFile"]
    assert runs == ([[expected["file"], expected["args"]]] if expected else [])  # once, exactly the fixed command
    assert shown(calls).count(["win.show", "AI Browser chat"]) == 1  # "sideways" showed nothing


@NEEDS_NODE
def test_a_tests_electron_reads_a_file_instead_of_brave(tmp_path):
    answer = tmp_path / "page.json"
    answer.write_text(json.dumps({"state": "denied"}), encoding="utf-8")
    calls = run_main(tmp_path, f"--aib-fake-page={answer}", feed=START, pause=1.5,
                     steps=[[300, "tray", "Show chat"], [600, "invoke", "chat", "thisPage"]])
    assert ["answer", "thisPage", {"state": "denied"}] in calls and "execFile" not in names(calls)
