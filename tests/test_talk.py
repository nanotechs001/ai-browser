"""Talking to the Brain in Mission Control: push-to-talk with a stubbed microphone (a 440 Hz tone, given to the page
from outside it), the fake speech engine and the fake claude. The mic is open only while the user talks, every word
stays text, and the Brain only proposes: an agent starts after Start or a plain yes, and nothing else ever happens."""

import asyncio
import json
import math
import shutil
from array import array
from pathlib import Path

import pytest

from ai_browser.chrome import chrome_binary
from test_bridge import EVENTS
from test_home import HOSTILE, stack, until  # noqa: F401  (fixtures)
from test_mission import BUBBLES, LOCAL_VOICE, SLOW_VOICE, WORKING, needs_reply, open_with, station, voice_on
from test_oneshot import oneshots

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
ROOT = Path(__file__).parents[1]
EXTENSION = ROOT / "src" / "ai_browser" / "app" / "ui"
TALKING = "talking with the user"  # in the Brain's talk prompt: the fake claude's script key for it


async def eventually(check, seconds=8.0):
    """True once `check()` is: polled in Python, for the app's side of things."""
    for _ in range(int(seconds * 20)):
        if check():
            return True
        await asyncio.sleep(0.05)
    return bool(check())


# ---- voice.js: the Brain's answers go first; while the user talks, nothing is spoken ---------------------------------

VOICE = """(async () => {
  const { createVoice, guardMs } = await import("/voice.js");
  window.spoken = [];
  let current = null;
  window.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
  speechSynthesis.getVoices = () => [{ name: "Samantha", lang: "en-US", localService: true }];
  speechSynthesis.speak = (said) => {
    window.spoken.push(["speak", said.text]);
    current = said;
    setTimeout(() => { if (current === said) { current = null; said.onend && said.onend(); } }, 400);
  };
  speechSynthesis.cancel = () => {
    window.spoken.push(["cancel"]);
    const was = current;
    current = null;
    if (was && was.onerror) was.onerror({ error: "interrupted" });
  };
  window.bubbleNode = document.createElement("div");
  window.testVoice = createVoice({ bubble: window.bubbleNode, hold: 300 });
  window.guardMs = guardMs;
  return (await window.testVoice.setEnabled(true)).on;
})()"""


@CHROME
async def test_an_answer_goes_first_and_cuts_a_background_update(stack):
    js = await open_with(stack)
    assert await js(VOICE) is True
    await js("testVoice.say('update one'); testVoice.say('update two'); true")
    assert await until(js, "window.spoken.length === 1")
    await js("testVoice.say('the answer', {priority: true}); true")
    assert await until(js, "window.spoken.length >= 4", 5)
    await asyncio.sleep(1.5)
    assert await js("window.spoken") == [["speak", "update one"], ["cancel"], ["speak", "the answer"],
                                         ["speak", "update two"]]  # the cut update isn't said again


@CHROME
async def test_answers_never_count_toward_the_summary(stack):
    js = await open_with(stack)
    assert await js(VOICE) is True
    await js("testVoice.pause(); for (const n of [1, 2, 3, 4]) testVoice.say(`update ${n}`);"
             " testVoice.say('the answer', {priority: true}); true")
    await asyncio.sleep(0.8)
    assert await js("window.spoken") == [] and await js("bubbleNode.hidden") is True
    await js("testVoice.resume(); true")
    assert await until(js, "window.spoken.length >= 2", 5)
    assert (await js("window.spoken"))[:2] == [["speak", "the answer"], ["speak", "4 more updates: open the Brain"]]


@CHROME
async def test_a_pause_cuts_speech_and_holds_the_queue_until_resume(stack):
    js = await open_with(stack)
    assert await js(VOICE) is True
    await js("testVoice.say('update one'); true")
    assert await until(js, "window.spoken.length === 1")
    await js("testVoice.pause(); testVoice.say('update two'); true")
    await asyncio.sleep(1.2)
    assert await js("window.spoken") == [["speak", "update one"], ["cancel"]]
    assert await js("bubbleNode.hidden") is True  # nothing is shown while the user talks, either
    await js("testVoice.resume(); true")
    assert await until(js, "window.spoken.length === 3")
    assert (await js("window.spoken"))[2] == ["speak", "update two"]
    await asyncio.sleep(1.2)
    assert len(await js("window.spoken")) == 3  # the update cut by the pause isn't said again


@CHROME
async def test_the_stuck_voice_guard_grows_with_the_answer(stack):
    js = await open_with(stack)
    assert await js(VOICE) is True
    assert await js("guardMs('x'.repeat(240), 5000)") == 18000  # a 240-character answer isn't cut off
    assert await js("guardMs('short', 5000)") == 12000 and await js("guardMs('short', 20000)") == 20000


# ---- the microphone: a stub from outside the page, and mic.js ------------------------------------------------------

def mic(permission="granted", error=None):
    """A microphone stub, added before the page's scripts: getUserMedia gives a live 440 Hz tone (a real MediaStream
    from an OscillatorNode) and counts opens (window.micOpen) and track stops (window.micClosed). The microphone
    permission answers `permission`, and turns "granted" once getUserMedia has run; with `error` (name, message),
    getUserMedia refuses the way the browser does."""
    refuse = f"throw new DOMException({json.dumps(error[1])}, {json.dumps(error[0])});" if error else ""
    return f"""
window.micOpen = 0; window.micClosed = 0; window.micPermission = {json.dumps(permission)};
navigator.mediaDevices.getUserMedia = async (constraints) => {{
  {refuse}
  window.micOpen += 1;
  window.micConstraints = constraints;
  if (window.micPermission === "prompt") window.micPermission = "granted";
  const context = new AudioContext();
  const tone = context.createOscillator();
  tone.frequency.value = 440;
  const out = context.createMediaStreamDestination();
  tone.connect(out);
  tone.start();
  for (const track of out.stream.getTracks()) {{
    const stop = track.stop.bind(track);
    let stopped = false;
    track.stop = () => {{
      if (stopped) return;
      stopped = true;
      window.micClosed += 1;
      stop();
      tone.stop();
      context.close();
    }};
  }}
  return out.stream;
}};
const realQuery = navigator.permissions.query.bind(navigator.permissions);
navigator.permissions.query = (descriptor) => descriptor && descriptor.name === "microphone"
  ? Promise.resolve({{ name: "microphone", state: window.micPermission, onchange: null }})
  : realQuery(descriptor);
"""


async def front(stack, js):
    """This tab in front with its page focused: real key and mouse events reach it, and it may play (and record)."""
    cdp = stack["cdp"]
    await cdp.send("Page.bringToFront", session_id=js.session)
    await cdp.send("Emulation.setFocusEmulationEnabled", {"enabled": True}, session_id=js.session)
    assert await until(js, "document.visibilityState === 'visible'")


async def click(stack, js, selector, hold=0.0):
    """A real mouse click (or a press held `hold` seconds) on the middle of `selector`."""
    x, y = await js(f"(() => {{ const r = document.querySelector({json.dumps(selector)}).getBoundingClientRect();"
                    " return [r.x + r.width / 2, r.y + r.height / 2]; })()")
    for kind in ("mousePressed", "mouseReleased"):
        await stack["cdp"].send("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, "button": "left",
                                                             "clickCount": 1}, session_id=js.session)
        if kind == "mousePressed" and hold:
            await asyncio.sleep(hold)


def crossings_per_second(samples):
    """Zero crossings a second over the sound itself: any silence before the tone reaches the page (a fresh browser's
    audio can start late), or after it stops, is left out, so it can't pass for a slower rate."""
    loud = [index for index, value in enumerate(samples) if abs(value) > 1000]
    sound = samples[loud[0]:loud[-1] + 1] if loud else []
    flips = sum(1 for one, two in zip(sound, sound[1:]) if (one >= 0) != (two >= 0))
    return flips / (len(sound) / 16_000) if sound else 0.0


MIC_RUN = """(async () => {
  const { openMic } = await import("/mic.js");
  window.chunks = [];
  const mic = await openMic({ onChunk: (buffer) => window.chunks.push(Array.from(new Int16Array(buffer))),
                              onError: (error) => { window.micError = String(error); } });
  const deadline = Date.now() + 5000; // about a second of sound (the first audio of a fresh browser can start late)
  while (window.chunks.length < 4 && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 50));
  const closedBefore = window.micClosed;
  await mic.stop();
  return { closedBefore, constraints: window.micConstraints, sizes: window.chunks.map((chunk) => chunk.length) };
})()"""

MIC_CANCEL = """(async () => {
  const { openMic } = await import("/mic.js");
  let after = 0;
  let cancelled = false;
  const mic = await openMic({ onChunk: () => { if (cancelled) after += 1; } });
  await new Promise((resolve) => setTimeout(resolve, 400));
  cancelled = true;
  mic.cancel();
  await new Promise((resolve) => setTimeout(resolve, 600));
  return after;
})()"""


@CHROME
async def test_the_mic_sends_16k_mono_chunks_and_closes(stack):
    js = await open_with(stack, mic())
    await front(stack, js)
    await click(stack, js, "#counts")  # the user's own click: the page may now play, and record, sound
    result = await js(MIC_RUN)
    assert result["closedBefore"] == 0 and await js("window.micClosed") == 1  # open while recording, closed by stop
    assert result["constraints"] == {"audio": {"channelCount": 1, "echoCancellation": True, "noiseSuppression": True,
                                               "autoGainControl": True}}
    sizes = result["sizes"]
    assert sizes and all(size == 4000 for size in sizes[:-1]) and sizes[-1] <= 4000  # 250 ms chunks, then the rest
    samples = [value for chunk in await js("window.chunks") for value in chunk]
    assert 16_000 <= len(samples) <= 24_000  # four chunks, about a second at 16 kHz, and what the flush handed over
    assert 836 <= crossings_per_second(samples) <= 924  # a 440 Hz tone crosses zero 880 times a second: 16 kHz intact
    assert await js("window.micError || ''") == ""
    assert await js(MIC_CANCEL) == 0  # cancel hands over nothing more
    assert await js("window.micOpen") == 2 and await js("window.micClosed") == 2


# ---- push-to-talk in Mission Control ---------------------------------------------------------------------------------

PANEL = "document.getElementById('talk')"
LOG = "[...document.querySelectorAll('#talk-log li')].map((line) => line.textContent)"
NOTICE = "document.getElementById('talk-notice').textContent"
CARD = "document.getElementById('talk-card').textContent"
SPACE = {"key": " ", "code": "Space", "windowsVirtualKeyCode": 32}
ENTER = {"key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13}
ESCAPE = {"key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27}


async def key_down(stack, js, key, text=None):
    """A real key press (CDP Input), as a person's: it gives the page user activation."""
    await stack["cdp"].send("Input.dispatchKeyEvent", {"type": "keyDown", **key, **({"text": text} if text else {})},
                            session_id=js.session)


async def key_up(stack, js, key):
    await stack["cdp"].send("Input.dispatchKeyEvent", {"type": "keyUp", **key}, session_id=js.session)


async def tap(stack, js, key, text=None):
    await key_down(stack, js, key, text)
    await key_up(stack, js, key)


SPOKE = "/· [1-9][0-9]* s$/.test(document.getElementById('talk-status').textContent)"  # a second of sound has gone


async def mouse(stack, js, selector, kind):
    """Half of a real click on the middle of `selector`: kind is "mousePressed" or "mouseReleased"."""
    x, y = await js(f"(() => {{ const r = document.querySelector({json.dumps(selector)}).getBoundingClientRect();"
                    " return [r.x + r.width / 2, r.y + r.height / 2]; })()")
    await stack["cdp"].send("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, "button": "left",
                                                         "clickCount": 1}, session_id=js.session)


async def talk(stack, js, seconds=0.3):
    """Hold Space until a second of sound has gone to the app, `seconds` more, then let go. It waits for the sound,
    not the clock: a fresh browser's audio can start a moment late."""
    await key_down(stack, js, SPACE, " ")
    assert await until(js, f"{PANEL}.dataset.state === 'listening'")
    assert await until(js, SPOKE)
    await asyncio.sleep(seconds)
    await key_up(stack, js, SPACE)


def talk_script(stack, *answers, default=WORKING):
    """The fake claude: agents run `default`; the Brain's talk calls get `answers` in order (the last one repeats)."""
    stack["script"].write_text(json.dumps({"default": default, TALKING: [
        {"result": answer if isinstance(answer, str) else json.dumps(answer)} for answer in answers]}),
        encoding="utf-8")


def talk_calls(stack):
    return [call["oneshot"] for call in oneshots(stack["log"]) if TALKING in call["oneshot"]]


async def ask_typed(js, words):
    """The Ask the Brain box, typed and sent."""
    await js(f"document.getElementById('talk-text').value = {json.dumps(words)};"
             " document.getElementById('talk-form').requestSubmit(); true")


async def open_talk(stack, *sources, hearing="ready"):
    """Mission Control with `sources` run before its scripts, in front, once it knows whether talking is ready."""
    js = await open_with(stack, "".join(sources))
    await front(stack, js)
    assert await until(js, f"{PANEL}.dataset.hearing === {json.dumps(hearing)}")
    return js


@CHROME
async def test_a_spoken_question_gets_a_spoken_answer(stack):
    engine = stack["engine"]
    engine.answers = ["what is fix the footer doing"]
    answer = "Fix the footer is checking the links in the footer."
    talk_script(stack, {"say": answer, "action": "none"})
    js = await open_talk(stack, mic(), LOCAL_VOICE)
    assert await js(f"{PANEL}.hidden") is True  # the talk panel stays hidden until the first turn
    await js(BUBBLES)
    await voice_on(js)
    await talk(stack, js, 0.3)  # about 1.5 s of sound in all
    assert await eventually(lambda: engine.heard)
    [pcm] = engine.heard
    assert 36_000 <= len(pcm) <= 60_000  # 1.5 s of 16 kHz 16-bit mono is 48,000 bytes: ±25%
    samples = array("h")
    samples.frombytes(pcm)
    assert math.sqrt(sum(value * value for value in samples) / len(samples)) / 32768 > 0.05  # not silent
    assert 836 <= crossings_per_second(samples) <= 924  # 880 a second for 440 Hz: 16 kHz arrived intact
    assert await until(js, f"{LOG}.includes('You: what is fix the footer doing')")
    assert await until(js, f"{LOG}.includes({json.dumps('Brain: ' + answer)})")
    assert "The user's words: what is fix the footer doing" in talk_calls(stack)[0]
    assert await until(js, f"window.seen.includes({json.dumps(answer)})")  # in the speech bubble
    assert await until(js, f"window.spoken.some(([text, voice]) => text === {json.dumps(answer)}"
                           " && voice === 'Samantha')")  # and said aloud, by a voice on this computer
    assert await js("window.micOpen") == 1 and await js("window.micClosed") == 1  # the mic closed with the turn
    assert await until(js, f"{PANEL}.dataset.state === 'idle'")
    assert await js(f"{PANEL}.hidden") is False and await js("document.querySelector('#talk .talk-note').textContent") \
        == "Your voice stays on this computer. Your words go to Claude, like typed text."


@CHROME
async def test_words_that_sound_like_a_password_never_leave(stack):
    from ai_browser.brain.talk import HIDDEN, SECRET_ANSWER

    stack["engine"].answers = ["my password is hunter2"]
    talk_script(stack, {"say": "OK.", "action": "none"})
    js = await open_talk(stack, mic())
    await talk(stack, js)
    assert await until(js, f"{LOG}.includes({json.dumps('Brain: ' + SECRET_ANSWER)})")
    assert await js(LOG) == [f"You: {HIDDEN}", f"Brain: {SECRET_ANSWER}"]  # the page hides the words too
    assert talk_calls(stack) == []  # nothing went to Claude


@CHROME
async def test_a_tap_of_space_is_dropped(stack):
    js = await open_talk(stack, mic())
    await tap(stack, js, SPACE, " ")
    assert await until(js, f"{NOTICE} === 'Hold Space while you talk'")
    await asyncio.sleep(0.5)
    assert stack["engine"].heard == [] and talk_calls(stack) == []
    assert await js("window.micOpen") == await js("window.micClosed")


@CHROME
async def test_space_keeps_its_job_in_text_boxes_and_on_buttons(stack):
    talk_script(stack, {"say": "OK.", "action": "none"})
    await stack["server"].agents.create("Fix the footer")
    js = await open_talk(stack, mic())
    assert await until(js, f"{station('a1')} !== null")
    await js("document.getElementById('task').focus(); true")
    await tap(stack, js, SPACE, " ")
    assert await until(js, "document.getElementById('task').value === ' '")  # it typed a space
    await js(f"document.getElementById('task').value = ''; {station('a1')}.focus(); true")
    await tap(stack, js, SPACE, " ")
    assert await until(js, "!document.getElementById('drawer').hidden")  # it pressed the focused station
    await asyncio.sleep(0.5)
    assert await js("window.micOpen") == 0 and await js(f"{PANEL}.dataset.state") == "idle"
    await js("document.getElementById('task').focus(); true")
    for kind in ("mousePressed", "mouseReleased"):  # a click on the room, away from every control
        await stack["cdp"].send("Input.dispatchMouseEvent", {"type": kind, "x": 40, "y": 300, "button": "left",
                                                             "clickCount": 1}, session_id=js.session)
    assert await js("document.activeElement === document.body")  # it gives Space back to talking
    await talk(stack, js)
    assert await eventually(lambda: len(stack["engine"].heard) == 1)


@CHROME
async def test_esc_throws_the_turn_away_and_does_nothing_else(stack):
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    await stack["server"].agents.create("Fix the footer")
    js = await open_talk(stack, mic())
    assert await until(js, f"{station('a1')} !== null")
    await js(f"{station('a1')}.click(); true")  # the drawer opens (a script's click leaves the keys with the page)
    assert await until(js, "!document.getElementById('drawer').hidden")
    await key_down(stack, js, SPACE, " ")
    assert await until(js, f"{PANEL}.dataset.state === 'listening'")
    await asyncio.sleep(0.5)
    await tap(stack, js, ESCAPE)
    await key_up(stack, js, SPACE)
    await asyncio.sleep(1)
    assert stack["engine"].heard == [] and talk_calls(stack) == []  # nothing transcribed, nothing asked
    assert await js("document.getElementById('drawer').hidden") is False  # and the drawer stays open
    assert await js("window.micOpen") == 1 and await js("window.micClosed") == 1
    assert await js(f"{PANEL}.dataset.state") == "idle"


@CHROME
async def test_the_mic_button_clicks_holds_and_stops_at_the_cap(stack):
    engine = stack["engine"]
    talk_script(stack, {"say": "OK.", "action": "none"})
    stack["hearing"].max_seconds = 2  # the page takes its cap from hearing_status
    js = await open_talk(stack, mic())
    assert await js("document.getElementById('mic').title") == "Talk to the Brain: hold Space, or hold or click here"
    assert (await js("document.getElementById('help').textContent")).endswith("· hold Space to talk")

    async def heard(count):
        assert await eventually(lambda: len(engine.heard) == count), count
        assert await until(js, f"{PANEL}.dataset.state === 'idle'")

    await click(stack, js, "#mic")  # a click: it listens until the next click
    assert await until(js, f"{PANEL}.dataset.state === 'listening'")
    assert await js("document.getElementById('mic').getAttribute('aria-pressed')") == "true"
    assert await until(js, SPOKE)
    await click(stack, js, "#mic")
    await heard(1)
    assert await js("document.getElementById('mic').getAttribute('aria-pressed')") == "false"
    await mouse(stack, js, "#mic", "mousePressed")  # held: it listens until it is let go
    assert await until(js, f"{PANEL}.dataset.state === 'listening'")
    assert await until(js, SPOKE)
    await mouse(stack, js, "#mic", "mouseReleased")
    await heard(2)
    await js("document.getElementById('mic').focus(); true")
    await talk(stack, js)  # Space on the focused mic button: the same as on the page, and never a click
    await heard(3)
    await asyncio.sleep(0.5)
    assert await js(f"{PANEL}.dataset.state") == "idle" and len(engine.heard) == 3
    await tap(stack, js, ENTER, "\r")  # Enter on it toggles, like a click
    assert await until(js, f"{PANEL}.dataset.state === 'listening'")
    assert await until(js, SPOKE)
    await tap(stack, js, ENTER, "\r")
    await heard(4)
    await click(stack, js, "#mic")  # left listening: the 2-second cap ends it
    assert await until(js, f"{NOTICE} === \"That's 2 seconds: I stopped listening\"", 6)
    await heard(5)
    assert len(engine.heard[-1]) <= 64_000
    assert await js("window.micOpen") == 5 and await js("window.micClosed") == 5


@CHROME
async def test_talking_cuts_speech_and_holds_updates_until_it_ends(stack):
    talk_script(stack, {"say": "Nothing else needs you.", "action": "none"})
    js = await open_talk(stack, mic(), SLOW_VOICE)
    await voice_on(js)
    needs_reply(stack["brain"], raw_id="t1", sender="Maria", summary="asks to move the launch")
    assert await until(js, "window.spoken.length === 1")  # an update is being spoken (this voice takes 2 s)
    await key_down(stack, js, SPACE, " ")
    assert await until(js, f"{PANEL}.dataset.state === 'listening'")
    assert await js("window.spoken[1]") == ["cancel"]  # the speech stopped before the mic opened
    needs_reply(stack["brain"], raw_id="t2", sender="Ben", summary="asks about staging")
    await asyncio.sleep(1)
    assert await js("window.spoken.length") == 2  # nothing is spoken while the user talks
    assert await js("document.getElementById('bubble').hidden") is True  # or shown
    await key_up(stack, js, SPACE)
    assert await until(js, "window.spoken.some(([kind, text]) => kind === 'speak'"
                           " && text === 'Ben needs your reply: asks about staging')", 12)  # it comes after the turn


@CHROME
async def test_show_me_the_inbox_opens_the_brain(stack):
    stack["engine"].answers = ["show me the inbox"]
    talk_script(stack, {"say": "Here is your inbox.", "action": "open", "target": "brain"})
    js = await open_talk(stack, mic())
    await talk(stack, js)
    assert await until(js, "!document.getElementById('drawer').hidden"
                           " && document.getElementById('drawer-title').textContent === 'The Brain'")  # no confirming
    assert await js(NOTICE) == "Switch on Voice to hear answers"  # Voice is off: said once, at the first answer


@CHROME
async def test_hostile_words_and_answers_stay_text(stack):
    stack["engine"].answers = [HOSTILE]
    talk_script(stack, {"say": HOSTILE, "action": "none"})
    js = await open_talk(stack, mic())
    await talk(stack, js)
    assert await until(js, f"{LOG}.filter((line) => line.includes('<img')).length === 2")
    assert await js("[...document.images].filter((img) => !img.closest('.monitor')).length") == 0
    assert await js("document.title") != "pwned"


def test_no_cloud_speech_anywhere_in_the_extension():
    files = [path for path in EXTENSION.rglob("*") if path.suffix in (".js", ".html", ".json", ".css")]
    assert any(path.name == "talk.js" for path in files)
    for path in files:
        assert "SpeechRecognition" not in path.read_text(encoding="utf-8"), path  # nor webkitSpeechRecognition


@CHROME
async def test_switching_windows_while_holding_space_ends_the_turn_once(stack):
    talk_script(stack, {"say": "OK.", "action": "none"})
    js = await open_talk(stack, mic())
    await key_down(stack, js, SPACE, " ")
    assert await until(js, f"{PANEL}.dataset.state === 'listening'")
    assert await until(js, SPOKE)
    await js("window.dispatchEvent(new Event('blur')); true")  # another window took the keys: no keyup comes
    assert await eventually(lambda: len(stack["engine"].heard) == 1)
    await key_up(stack, js, SPACE)  # the late keyup, once the user is back
    await asyncio.sleep(1)
    assert len(stack["engine"].heard) == 1
    assert await js("window.micOpen") == 1 and await js("window.micClosed") == 1
    assert await until(js, f"{PANEL}.dataset.state === 'idle'")


@CHROME
async def test_only_the_newest_questions_answer_shows(stack):
    stack["script"].write_text(json.dumps({
        "default": WORKING,
        "first question": [{"sleep": 2.5, "result": json.dumps({"say": "The old answer.", "action": "none"})}],
        TALKING: [{"result": json.dumps({"say": "The new answer.", "action": "none"})}]}), encoding="utf-8")
    js = await open_talk(stack, mic())
    for words in ("first question", "second question"):  # typed in Ask the Brain, the second before the first's answer
        await js(f"document.getElementById('talk-text').value = {json.dumps(words)};"
                 " document.getElementById('talk-form').requestSubmit(); true")
    assert await until(js, f"{LOG}.includes('Brain: The new answer.')")
    await asyncio.sleep(3)
    assert await js(f"{LOG}.filter((line) => line.startsWith('Brain:'))") == ["Brain: The new answer."]
    assert await js(f"{LOG}.filter((line) => line.startsWith('You:'))") == ["You: first question",
                                                                              "You: second question"]


@CHROME
async def test_a_dropped_line_ends_the_turn_instead_of_waiting(stack):
    stack["engine"].delay = 4  # the model takes a while to load, and the words to become text
    talk_script(stack, {"say": "OK.", "action": "none"})
    js = await open_talk(stack, mic())
    await talk(stack, js)
    assert await until(js, f"{PANEL}.dataset.state === 'transcribing'")
    assert (await js("document.getElementById('talk-status').textContent")).endswith(
        "(the first time takes a few seconds longer)")  # the model is still loading: the page says so
    for ws in list(stack["server"]._sockets):  # the app's end of the line closes (an app restart looks the same)
        await ws.close()
    assert await until(js, f"{NOTICE} === 'Not connected: is `ai-browser app` running?'", 5)
    assert await js(f"{PANEL}.dataset.state") == "idle"
    assert await eventually(lambda: stack["hearing"]._turns == {})
    assert await until(js, "document.getElementById('status').dataset.state === 'connected'", 10)  # it comes back


# ---- setup, first use, and the microphone's problems -----------------------------------------------------------------

BRAVE = ("Object.defineProperty(Navigator.prototype, 'userAgentData', {configurable: true, get: () => ({"
         " brands: [{brand: 'Brave', version: '152'}, {brand: 'Chromium', version: '152'}], mobile: false,"
         " platform: 'macOS'})});")


@CHROME
async def test_without_the_extra_a_press_says_how_to_add_it(stack):
    stack["engine"].installed = False
    stack["hearing"].platform = "mac"
    js = await open_talk(stack, mic(), hearing="no_engine")
    await tap(stack, js, SPACE, " ")
    assert await until(js, f"{CARD}.includes('uv sync --extra voice')")
    text = await js(CARD)
    assert "then restart ai-browser app" in text and "from PyPI" in text
    assert "Or use your Mac's Dictation in any text box" in text  # the zero-setup way, on a Mac
    assert await js("window.micOpen") == 0 and await js(f"{PANEL}.dataset.state") == "setup"


@CHROME
async def test_the_model_downloads_only_on_the_click(stack):
    store = stack["hearing"].models
    shutil.rmtree(store.folder)
    store.fetch.delay = 0.4  # before each read: the download takes a couple of seconds
    js = await open_talk(stack, mic(), hearing="no_model")
    assert await js("import('/talk.js').then((talk) => talk.megabytes(147769510))") == "148 MB"
    await tap(stack, js, SPACE, " ")
    assert await until(js, f"{CARD}.includes('Whisper tiny.en, 2 MB, from Hugging Face')")
    card = await js(CARD)
    assert str(store.folder) in card and "Nothing you say is ever sent anywhere." not in card  # the words go to Claude
    assert "Your voice never leaves this computer; your words go to Claude, like typed text." in card
    assert await js("document.querySelector('#talk-card .download').textContent") == "Download 2 MB"
    await asyncio.sleep(0.5)
    assert store.fetch.urls == [] and await js("window.micOpen") == 0  # nothing is fetched before the click
    await js("document.querySelector('#talk-card .download').click(); true")
    assert await until(js, f"{CARD}.includes(' of 2 MB') && !!document.querySelector('#talk-card progress')", 5)
    assert await until(js, f"{NOTICE} === 'Ready: hold Space to talk'", 15)
    assert len(store.fetch.urls) == 2 and store.present()
    await talk(stack, js)
    assert await eventually(lambda: len(stack["engine"].heard) == 1)


@CHROME
async def test_first_use_explains_the_browsers_question_first(stack):
    stack["hearing"].platform = "mac"
    js = await open_talk(stack, mic(permission="prompt"))
    await tap(stack, js, SPACE, " ")
    assert await until(js, f"{CARD}.includes('Google Chrome will now ask to use your microphone')")
    text = await js(CARD)
    assert "Choose Allow while visiting the site (or Allow), not Allow this time" in text
    assert "macOS may also ask once whether Google Chrome may use the microphone" in text
    assert "The mic is on only while you hold Space or the mic button, or from a click on the mic button until you " \
        "click it again." in text  # click-to-talk keeps it on too (up to the cap)
    assert await js("window.micOpen") == 0 and await js(f"{PANEL}.dataset.state") == "explain"
    await js("document.querySelector('#talk-card .continue').click(); true")
    assert await until(js, f"{NOTICE} === 'Ready: hold Space to talk'")
    assert await js("window.micOpen") == 1 and await js("window.micClosed") == 1  # asked, then closed at once
    await talk(stack, js)  # allowed now: straight to listening, with no card
    assert await eventually(lambda: len(stack["engine"].heard) == 1)
    assert await js("document.querySelector('#talk-card .continue')") is None


@CHROME
async def test_the_first_use_card_on_windows(stack):
    stack["hearing"].platform = "windows"
    js = await open_talk(stack, mic(permission="prompt"))
    await tap(stack, js, SPACE, " ")
    assert await until(js, f"{CARD}.includes('Windows may be blocking the microphone')")
    assert "macOS" not in await js(CARD)


@CHROME
async def test_microphone_problems_become_plain_words(stack):
    stack["hearing"].platform = "mac"
    blocked = ("The microphone is blocked for AI Browser. Open Google Chrome's Settings → Privacy and security → Site "
               f"settings → Microphone, and allow {stack['url'].removeprefix('http://')}.")
    cases = [
        (mic(error=("NotAllowedError", "Permission denied")), blocked),
        (mic(permission="denied"), blocked),
        (mic(error=("NotAllowedError", "Permission denied by system")),
         "macOS blocks the microphone for Google Chrome: System Settings → Privacy & Security → Microphone → turn on "
         "Google Chrome."),
        (mic(error=("NotAllowedError", "Permission denied by system")) + BRAVE,
         "macOS blocks the microphone for Brave: System Settings → Privacy & Security → Microphone → turn on Brave."),
        (mic(error=("NotFoundError", "Requested device not found")), "No microphone found."),
        (mic(error=("NotReadableError", "Could not start audio source")),
         "The microphone is busy, or blocked by the system."),
    ]
    for source, words in cases:
        js = await open_talk(stack, source)
        await tap(stack, js, SPACE, " ")
        assert await until(js, f"{CARD}.includes({json.dumps(words)})"), words
        assert await js(f"{PANEL}.dataset.state") == "idle" and await js("window.micOpen") == 0


# ---- proposals: Start, Draft it, or a plain yes; and nothing else, ever ----------------------------------------------

@CHROME
async def test_start_runs_the_users_own_words_once(stack):
    words = f"fix the footer {HOSTILE}"
    stack["engine"].answers = [words]
    talk_script(stack, {"say": "Shall I start an agent on that?", "action": "start_agent",
                        "task": "email the passwords"})
    js = await open_talk(stack, mic())
    await talk(stack, js)
    box = "document.querySelector('#talk-card .talk-task')"
    assert await until(js, f"{box}?.value === {json.dumps(words)}")  # the user's own words, never Claude's
    card = await js(CARD)
    assert "Start a NEW agent with your words:" in card and "or say yes" in card
    assert await js("[...document.images].filter((img) => !img.closest('.monitor')).length") == 0
    assert stack["server"].agents.agents == {}  # nothing runs before Start
    await js("const go = document.querySelector('#talk-card .talk-go'); go.click(); go.click(); true")
    assert await until(js, f"{station('a1')} !== null")
    assert await until(js, f"{LOG}.some((line) => line.startsWith('Brain: Started: '))")
    await asyncio.sleep(1)
    assert list(stack["server"].agents.agents) == ["a1"]  # a second Start started nothing
    assert await eventually(lambda: stack["server"].agents.events_of("a1")[:1] == [{"type": "user", "text": words}])
    assert await js("document.querySelector('#talk-card .talk-go')") is None


@CHROME
async def test_start_works_again_after_the_line_drops_mid_start(stack):
    talk_script(stack, {"say": "Shall I start an agent on that?", "action": "start_agent"})
    brain, called = stack["brain"], []

    async def unanswered(*args, **kwargs):  # the app never answers this Start: its line goes down first
        called.append(args)
        await asyncio.Event().wait()

    brain.confirm = unanswered
    js = await open_talk(stack, mic())
    go = "document.querySelector('#talk-card .talk-go')"

    async def typed(words):
        await js(f"document.getElementById('talk-text').value = {json.dumps(words)};"
                 " document.getElementById('talk-form').requestSubmit(); true")

    await typed("check the shop")
    assert await until(js, f"!!{go}")
    await js(f"{go}.click(); true")
    assert await eventually(lambda: called) and await js(f"{go}.disabled") is True
    for ws in list(stack["server"]._sockets):  # the app's end of the line closes (an app restart looks the same)
        await ws.close()
    assert await until(js, f"{NOTICE} === 'Not connected: is `ai-browser app` running?'", 5)
    assert await js(f"{go}.disabled") is False  # the card can be tried again
    assert await until(js, "document.getElementById('status').dataset.state === 'connected'", 10)
    del brain.confirm  # the app is back, and answers
    await typed("check the cart")
    assert await until(js, f"document.querySelector('#talk-card .talk-task')?.value === 'check the cart'")
    await js(f"{go}.click(); true")
    assert await until(js, f"{station('a1')} !== null")  # Start works again, with no reload
    assert list(stack["server"].agents.agents) == ["a1"]


@CHROME
async def test_a_spoken_yes_starts_the_open_proposal(stack):
    stack["engine"].answers = ["check the shop", "yes"]
    talk_script(stack, {"say": "Shall I start an agent on that?", "action": "start_agent"})
    js = await open_talk(stack, mic())
    await talk(stack, js)
    assert await until(js, "!!document.querySelector('#talk-card .talk-task')")
    await js("document.querySelector('#talk-card .talk-task').value = 'check the shop and the cart';"
             " document.querySelector('#talk-card .talk-model').value = 'haiku'; true")
    await talk(stack, js)
    assert await eventually(lambda: "a1" in stack["server"].agents.agents)
    assert stack["server"].agents.agents["a1"].model == "haiku"
    assert await eventually(lambda: stack["server"].agents.events_of("a1")[:1] == [
        {"type": "user", "text": "check the shop and the cart"}])  # the card as it read, with its model
    assert len(talk_calls(stack)) == 1  # the yes never reached Claude
    assert await until(js, "document.querySelector('#talk-card .talk-task') === null")


@CHROME
async def test_a_spoken_yes_never_answers_a_permission(stack, tmp_path):
    from ai_browser.brain.talk import NOTHING_OPEN_WAITING
    from test_tools import answers, asking, user_config

    user_config(tmp_path)
    stack["tools"].set_enabled("clickup", True)
    talk_script(stack, {"say": "It's waiting for your click on Allow.", "action": "none"}, default=asking())
    agents = stack["server"].agents
    await agents.create("make a ClickUp task")
    assert await eventually(lambda: agents.agents["a1"].permission is not None)
    stack["engine"].answers = ["yes"]
    js = await open_talk(stack, mic())
    await talk(stack, js)
    assert await until(js, f"{LOG}.includes({json.dumps('Brain: ' + NOTHING_OPEN_WAITING)})")
    await asyncio.sleep(1)
    assert agents.agents["a1"].permission is not None and agents.agents["a1"].state == "needs_you"
    assert answers(stack["log"]) == []  # no control_response: nothing answered the tool request
    assert talk_calls(stack) == []  # a yes with no card never reaches Claude


@CHROME
async def test_voice_never_approves_or_fills_a_draft(stack):
    from ai_browser.brain.talk import CLICK_ONLY, NOTHING_OPEN

    brain = stack["brain"]
    entry = needs_reply(brain, sender="Maria", summary="asks to move the launch")
    entry.state, entry.draft, entry.draft_version = "draft_ready", "Monday works.", 1
    brain.store.put(entry)
    sent, approved = [], []
    brain.outbox = lambda message: sent.append(message) or True

    async def approve(*args, **kwargs):
        approved.append(args)

    brain.approve = approve
    stack["engine"].answers = ["approve it", "yes"]
    talk_script(stack, {"say": "Approved.", "action": "approve", "item": "gmail:t1"},
                {"say": "Approve is a click on the draft.", "action": "none"})
    js = await open_talk(stack, mic())
    for _ in range(2):
        await talk(stack, js)
        assert await until(js, f"{PANEL}.dataset.state === 'idle'", 10)
    assert await js(LOG) == ["You: approve it", f"Brain: {CLICK_ONLY}", "You: yes", f"Brain: {NOTHING_OPEN}"]
    assert approved == [] and not [message for message in sent if message["type"] == "fill_reply"]
    assert brain.store.get("gmail:t1").state == "draft_ready"


@CHROME
async def test_voice_never_answers_a_bot_check(stack):
    from ai_browser.brain.talk import NOTHING_OPEN_WAITING
    from ai_browser.checks import KINDS

    talk_script(stack, {"say": "Flights to Manila is waiting for you: press Continue on its card once you've solved "
                               "the check.", "action": "none"})
    agents = stack["server"].agents
    agent = await agents.create("Flights to Manila")
    agent.check = {"kind": "check", "check": "google", "what": KINDS["google"], "site": "www.google.com",
                   "target": "T1", "adopted": False, "live": None, "since": 1.0}
    agent.state = "needs_you"
    agents._changed(agent)
    pressed = []

    def recorder(name):
        def record(*args, **kwargs):
            pressed.append(name)
            done = asyncio.get_running_loop().create_future()
            done.set_result(None)
            return done
        return record

    agents.continue_check = recorder("continue")
    agents.skip_check = recorder("skip")
    stack["engine"].answers = ["done", "yes"]
    js = await open_talk(stack, mic())
    assert await until(js, f"{station('a1')}?.dataset.state === 'needs_you'")
    for _ in range(2):
        await talk(stack, js)
        assert await until(js, f"{PANEL}.dataset.state === 'idle'", 10)
    assert pressed == [] and agent.check is not None and agent.state == "needs_you"
    prompts = talk_calls(stack)
    assert len(prompts) == 1 and "Flights to Manila" in prompts[0] and "on www.google.com" in prompts[0]
    assert (await js(LOG))[-1] == f"Brain: {NOTHING_OPEN_WAITING}"  # the yes: a pointer to the card, no Claude call


@CHROME
async def test_an_old_card_expires_and_a_late_yes_starts_nothing(stack):
    stack["brain"].talks.proposal_ttl = 1
    stack["engine"].answers = ["check the shop", "yes"]
    talk_script(stack, {"say": "Shall I start an agent on that?", "action": "start_agent"},
                {"say": "There's nothing open to say yes to.", "action": "none"})
    js = await open_talk(stack, mic())
    await talk(stack, js)
    assert await until(js, f"{CARD}.includes('This has expired: ask again')", 6)
    assert await js("document.querySelector('#talk-card .talk-go')") is None
    await talk(stack, js)
    assert await until(js, f"{LOG}.includes(\"Brain: There's nothing open to say yes to.\")")
    assert stack["server"].agents.agents == {}


# ---- the Brain listens: the particle brain's fifth state (the visuals spec's test 31) -------------------------------

LISTEN_GL = """
window.gl = { last: {} };
(() => {
  const names = new WeakMap();
  const proto = WebGLRenderingContext.prototype;
  const locate = proto.getUniformLocation;
  proto.getUniformLocation = function (program, name) {
    const location = locate.call(this, program, name);
    if (location) names.set(location, name);
    return location;
  };
  for (const method of ["uniform1f", "uniform4fv"]) {
    const real = proto[method];
    proto[method] = function (location, ...values) {
      const name = location && names.get(location);
      if (name) window.gl.last[name] = method === "uniform1f" ? values[0] : Array.from(values[0]);
      return real.call(this, location, ...values);
    };
  }
})();
"""
STAGE_STATES = """
window.states = [];
addEventListener("DOMContentLoaded", () => {
  const stage = document.querySelector(".stage");
  const note = () => {
    if (window.states[window.states.length - 1] !== stage.dataset.state) window.states.push(stage.dataset.state);
  };
  note();
  new MutationObserver(note).observe(stage, { attributes: true, attributeFilter: ["data-state"] });
});
"""
NO_WEBGL = ("const realContext = HTMLCanvasElement.prototype.getContext;"
            "HTMLCanvasElement.prototype.getContext = function (kind, ...rest) {"
            "  return /webgl/.test(kind) ? null : realContext.call(this, kind, ...rest); };")


@CHROME
async def test_the_particle_brain_listens(stack):
    talk_script(stack, {"say": "OK.", "action": "none"})
    js = await open_talk(stack, LISTEN_GL, STAGE_STATES, mic())
    stage = "document.querySelector('.stage')"
    assert await until(js, f"{stage}.dataset.mode === 'webgl' && window.gl.last.u_mix !== undefined")
    await key_down(stack, js, SPACE, " ")
    assert await until(js, f"{stage}.dataset.state === 'listening'")
    settled = ("Math.abs(window.gl.last.u_listen - 1) < 0.05"
               " && window.gl.last.u_mix.every((weight) => Math.abs(weight) < 0.05)")
    assert await until(js, settled, 5)  # u_listen near 1, and the four weights of u_mix near 0
    assert await js(f"{stage}.dataset.mode") == "webgl"  # the shaders with u_listen compile
    await key_up(stack, js, SPACE)
    assert await until(js, "window.gl.last.u_listen < 0.05", 6)  # it eases back once the turn ends
    assert "listening" in await js("window.states")


@CHROME
async def test_without_webgl_the_dotted_brain_listens(stack):
    js = await open_talk(stack, NO_WEBGL, mic())
    stage = "document.querySelector('.stage')"
    assert await until(js, f"{stage}.dataset.mode === 'css'")
    await key_down(stack, js, SPACE, " ")
    assert await until(js, f"{stage}.dataset.state === 'listening'")
    dots = "getComputedStyle(document.querySelector('.stage .orb'), '::before')"
    assert await js(f"{dots}.getPropertyValue('--a').trim()") == "#fff2fa"  # white
    assert await js(f"{dots}.getPropertyValue('--b').trim()") == "#f28cd9"  # rose
    await key_up(stack, js, SPACE)


def test_the_readme_says_how_to_talk_and_the_zero_setup_way():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "## Talking to the Brain" in text
    section = " ".join(text.split("## Talking to the Brain", 1)[1].split("\n## ", 1)[0].split())
    for words in ("hold **Space**", "`uv sync --extra voice`", "a plain `uv sync` removes the extra again",
                  "**Download 148 MB**", "Allow while visiting the site", "never saved or logged", "no cloud speech",
                  "Dictation", "Voice Access", "Win+H", "Windows on Arm"):
        assert words in section, words


def test_the_readme_says_the_brain_can_send_to_an_open_agent():
    text = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
    for words in ('"give this to agent 2"', "Press **Start** or **Send** on it (or type yes) in AI Home or Mission "
                  "Control; the watcher's Brain page shows the card only", '"1 · Fix the footer"', "**Your tabs**",
                  "**Give to this agent**", "**send your words to an agent that's already open**",
                  'a "yes" with no card open does nothing', "hands over or takes back a tab"):
        assert words in text, words


@CHROME
async def test_numbers_show_on_stations_the_list_and_the_drawer(stack):
    stack["script"].write_text(json.dumps(WORKING), encoding="utf-8")
    agents = stack["server"].agents
    await agents.create("Fix the footer")
    await agents.create("Check flights")
    js = await open_with(stack)
    assert await until(js, f"{station('a1', '.nameplate')}?.textContent === '1 · Fix the footer'")
    assert (await js(f"{station('a1')}.getAttribute('aria-label')")).startswith("1 · Fix the footer: ")
    assert await js("document.querySelector('#list button[data-id=\"a1\"] .grow').textContent") == \
        "1 · Fix the footer"
    await js(f"{station('a1')}.click(); true")
    assert await until(js, "document.getElementById('drawer-title').textContent === '1 · Fix the footer'")
    await agents.close("a1")
    assert await until(js, f"{station('a1')} === null")
    assert await js(f"{station('a2', '.nameplate')}.textContent") == "2 · Check flights"  # numbers never change


@CHROME
async def test_a_spoken_message_goes_to_the_existing_agent(stack):
    from ai_browser.brain.talk import RELAY

    words = "tell the footer agent to also check the mobile layout"
    talk_script(stack, {"say": "Sure, I'll pass that on.", "action": "message_agent", "agent": "a1"}, default=EVENTS)
    agents = stack["server"].agents
    await agents.create("Fix the footer")
    assert await eventually(lambda: agents.agents["a1"].state == "your_turn")
    stack["engine"].answers = [words, "yes"]
    js = await open_talk(stack, mic())
    await talk(stack, js)
    box = "document.querySelector('#talk-card .talk-task')"
    assert await until(js, f"{box}?.value === {json.dumps(words)}")  # the user's own words
    card = await js(CARD)
    assert "Send to 1 · Fix the footer:" in card and "or say yes" in card
    assert await js("document.querySelector('#talk-card .talk-go').textContent") == "Send"
    said = "Brain: I can send your words to 1 · Fix the footer. Press Send, or say yes."  # never Claude's "Sure"
    assert await until(js, f"{LOG}.includes({json.dumps(said)})")
    await talk(stack, js)
    assert await eventually(lambda: {"type": "user", "text": f"{RELAY}\n{words}"} in agents.events_of("a1"))
    assert list(agents.agents) == ["a1"] and len(talk_calls(stack)) == 1  # no new agent; the yes skipped Claude
    assert await until(js, f"{box} === null")
    assert await until(js, f"{LOG}.includes('Brain: Sent to 1 · Fix the footer.')")


@CHROME
async def test_send_click_sends_once_to_a_busy_agent_as_queued(stack):
    from ai_browser.brain.talk import RELAY

    talk_script(stack, {"say": "OK.", "action": "message_agent", "agent": "a1"})  # agents stay at work (WORKING)
    agents = stack["server"].agents
    await agents.create("Fix the footer")
    assert await eventually(lambda: agents.agents["a1"].state == "working")
    js = await open_talk(stack, mic())
    await ask_typed(js, "also check the header")
    go = "document.querySelector('#talk-card .talk-go')"
    assert await until(js, f"{go}?.textContent === 'Send'")
    assert "It's working: it reads your words when it finishes what it's doing now." in await js(CARD)
    await js(f"{go}.click(); {go}?.click(); true")
    queued = "Brain: Queued for 1 · Fix the footer: it reads it when it finishes what it's doing now."
    assert await until(js, f"{LOG}.includes({json.dumps(queued)})")
    await asyncio.sleep(1)
    assert [event for event in agents.events_of("a1") if event["type"] == "queued"] == [
        {"type": "queued", "text": f"{RELAY}\nalso check the header"}]  # one click, one message


@CHROME
async def test_hand_over_hint_opens_this_agents_tab_list(stack):
    from ai_browser.brain.talk import HAND_OVER_SAY
    from fake_brave import FakeBrave

    server = stack["server"]
    agents = server.agents
    talk_script(stack, {"say": "Hand it over.", "action": "open", "target": "tabs", "agent": "a1"},
                {"say": "OK.", "action": "message_agent", "agent": "a1"})
    await agents.create("Fix the footer")
    brave = FakeBrave([{"target": "U1", "url": "https://mail.example/inbox", "title": "Inbox"},
                       {"target": "T1", "url": "https://shop.example/", "title": "Agent page"},
                       {"target": "S1", "url": "https://s.example/", "title": "Session page"}])
    brave.owners.update({"T1": {"kind": "agent", "id": "a1", "name": "Fix the footer", "color": "blue"},
                         "S1": {"kind": "session", "id": "cc-x", "name": "Claude Code", "color": "orange"}})
    server.attach_brave(brave)
    agents.env["AIB_BROWSER"] = "chrome"  # brave mode, as run.py's brave_env sets it
    js = await open_talk(stack, mic())
    await ask_typed(js, "give agent 1 my Gmail tab")
    yours = "document.querySelector('#drawer .your-tabs')"
    assert await until(js, f"{yours}?.open === true")
    assert await js(f"{yours}.querySelector('summary').textContent") == "Your tabs (1)"
    assert await js(f"[...{yours}.querySelectorAll('.your-tab')].map((row) => row.dataset.target)") == ["U1"]
    assert await js("document.getElementById('drawer-title').textContent") == "1 · Fix the footer"
    said = "Brain: " + HAND_OVER_SAY.format(label="1 · Fix the footer")
    assert await until(js, f"{LOG}.includes({json.dumps(said)})")
    await asyncio.sleep(0.5)
    assert agents.agents["a1"].adopted == [] and "U1" not in brave.owners  # the Brain handed nothing
    await js(f"{yours}.open = false; true")
    await ask_typed(js, "send this page to agent 1")
    assert await until(js, "!!document.querySelector('#talk-card .talk-tabs')")
    assert "It can't see your tabs: use Your tabs → Give to this agent." in await js(CARD)
    await js("document.querySelector('#talk-card .talk-tabs').click(); true")
    assert await until(js, f"{yours}?.open === true")  # a view only
    assert agents.agents["a1"].adopted == []
    await js(f"{yours}.querySelector('.give-here').click(); true")  # the user's click
    assert await eventually(lambda: "U1" in agents.agents["a1"].adopted)
    brave.set_state("ready")
    assert await until(js, f"{yours}.textContent.includes(\"Brave isn't connected yet: connect it in AI Home.\")")
    assert await js(f"{yours}.querySelectorAll('.your-tab').length") == 0


@CHROME
async def test_your_tabs_say_what_the_list_leaves_out(stack):
    """Brave mode lists one profile (watcher-safety's tab scope). Mission Control's Your tabs says what it leaves out, as
    AI Home's list does, and never "None of your tabs are open." while the user's tabs are elsewhere."""
    from fake_brave import FakeBrave

    server = stack["server"]
    agents = server.agents
    talk_script(stack, {"say": "Hand it over.", "action": "open", "target": "tabs", "agent": "a1"})
    await agents.create("Fix the footer")
    brave = FakeBrave([])
    brave.set_scope("none", 0)  # AI Browser can't tell which Brave profile is the user's yet
    server.attach_brave(brave)
    agents.env["AIB_BROWSER"] = "chrome"  # brave mode, as run.py's brave_env sets it
    js = await open_talk(stack, mic())
    await ask_typed(js, "give agent 1 my Gmail tab")
    yours = "document.querySelector('#drawer .your-tabs')"
    assert await until(js, f"{yours}?.open === true")
    text = f"{yours}.textContent"
    not_listed = "Your tabs aren't listed: AI Browser can't tell which Brave profile is yours yet."
    assert await until(js, f"{text}.includes({json.dumps(not_listed)})")
    assert not await js(f"{text}.includes('None of your tabs are open')")
    brave.set_scope("chosen", 3)  # the chosen profile, with three of the user's tabs in other profiles
    brave.changed()
    assert await until(js, f"{text}.includes('3 more tabs in other profiles or private windows: not shown here.')")
    assert await js(f"{text}.includes('None of your tabs are open in this profile.')")


@CHROME
async def test_spoken_labels_read_the_dot_as_a_pause(stack):
    js = await open_with(stack)
    assert await js(VOICE) is True
    await js("testVoice.say('Sent to 1 · Fix the footer.', {priority: true}); true")
    assert await until(js, "window.spoken.length === 1")
    assert await js("window.spoken") == [["speak", "Sent to 1, Fix the footer."]]
    assert await js("bubbleNode.textContent") == "Sent to 1 · Fix the footer."  # the bubble and the log keep the dot


@CHROME
async def test_a_yes_never_runs_a_card_that_left_the_screen(stack):  # final review I3
    from ai_browser.brain.talk import NOTHING_OPEN, RELAY

    talk_script(stack, {"say": "x", "action": "message_agent", "agent": "a1"}, default=EVENTS)
    agents, brain, seen = stack["server"].agents, stack["brain"], []
    await agents.create("Fix the footer")
    assert await eventually(lambda: agents.agents["a1"].state == "your_turn")
    real = brain.respond

    async def respond(talk_id, text, proposal=None, task=None, model=None):
        seen.append((text, proposal))
        return await real(talk_id, text, proposal=proposal, task=task, model=model)

    brain.respond = respond
    js = await open_talk(stack, mic(permission="denied"))
    await ask_typed(js, "tell the footer agent to check the header")
    assert await until(js, "document.querySelector('#talk-card .talk-go')?.textContent === 'Send'")
    await js("document.activeElement?.blur(); true")
    await tap(stack, js, SPACE, " ")  # the microphone's problem card takes the send card's place
    assert await until(js, f"{CARD}.includes('microphone') && !document.querySelector('#talk-card .talk-go')")
    await ask_typed(js, "ok")  # meant for the card that is no longer on screen
    assert await until(js, f"{LOG}.includes({json.dumps('Brain: ' + NOTHING_OPEN)})")
    await asyncio.sleep(1)
    assert seen[-1] == ("ok", None)  # no card id went with it
    assert not [event for event in agents.events_of("a1") if str(event.get("text", "")).startswith(RELAY)]


@CHROME
async def test_the_browser_is_named_from_its_brands(stack):
    js = await open_with(stack)
    names = await js("import('/talk.js').then(({ browserName }) => [[{brand: 'Microsoft Edge'}, {brand: 'Chromium'}],"
                     " [{brand: 'Brave'}], [{brand: 'Google Chrome'}], []]"
                     ".map((brands) => browserName({ userAgentData: { brands } })))")
    assert names == ["Microsoft Edge", "Brave", "Google Chrome", "Google Chrome"]
