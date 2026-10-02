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
from test_home import HOSTILE, stack, until  # noqa: F401  (fixtures)
from test_mission import BUBBLES, LOCAL_VOICE, SLOW_VOICE, WORKING, needs_reply, open_with, station, voice_on
from test_oneshot import oneshots

CHROME = pytest.mark.skipif(chrome_binary() is None, reason="Google Chrome is not installed")
ROOT = Path(__file__).parents[1]
EXTENSION = ROOT / "src" / "ai_browser" / "app" / "extension"
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
  const { createVoice, guardMs } = await import(chrome.runtime.getURL("voice.js"));
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
  const { openMic } = await import(chrome.runtime.getURL("mic.js"));
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
  const { openMic } = await import(chrome.runtime.getURL("mic.js"));
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
