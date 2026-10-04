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
    """`body` (JavaScript ending in a return) run with policy.js as `policy` and line.js as `line`; its value."""
    script = (f"const policy = require({json.dumps(str(ELECTRON_DIR / 'policy.js'))});\n"
              f"const line = require({json.dumps(str(ELECTRON_DIR / 'line.js'))});\n"
              f"const value = (() => {{ {body} }})();\n"
              "process.stdout.write(JSON.stringify(value === undefined ? null : value));")
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
