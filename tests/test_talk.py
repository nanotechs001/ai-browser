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
