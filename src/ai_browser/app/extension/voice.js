// The Brain talking back: short updates, one at a time, in a speech bubble above the blob, and spoken aloud when the
// user switched Voice on. Speech uses only voices that run on this computer (localService), so the words never leave it.
// More than three updates waiting become one summary, and the speech in progress stops: the voice never piles up.
"use strict";

const WAITING = 3;
const PAUSE = 600; // ms after a spoken update before the next one
const GUARD_MS = 12000; // a voice that never says it ended is stopped after this long (longer for a long answer)

export function guardMs(text, hold = 5000) { // about 75 ms a character: a 240-character answer isn't cut off
  return Math.max(hold, GUARD_MS, 75 * String(text || "").length);
}

export function speakable(text) { // "1 · Fix the footer" is said "1, Fix the footer": no voice reads the symbol aloud
  return String(text).split(" · ").join(", ");
}

export function createVoice({ bubble, onSpeaking = () => {}, onBlocked = () => {}, onWord = () => {},
                              hold = 5000 } = {}) {
  let queue = []; // [{text, count}]: count > 1 is a summary of that many updates
  let showing = false;
  let timer = null;
  let voice = null; // the on-device voice, while Voice is on
  let speaking = false;
  let blocked = false; // Chrome lets a page speak only after the user clicked it (a reloaded page must ask again)
  let paused = false; // the user is talking: nothing is spoken or shown until the turn ends
  let current = null; // the update on show now
  let spoken = 0; // counts utterances: the late end of one cut short by pause() moves nothing on

  function summary(count) {
    return `${count} more update${count === 1 ? "" : "s"}: open the Brain`;
  }

  function setSpeaking(on) {
    if (speaking !== on) {
      speaking = on;
      onSpeaking(on);
    }
  }

  function next() {
    clearTimeout(timer);
    if (paused) { // held: what waits comes once the user is done talking
      showing = false;
      current = null;
      bubble.hidden = true;
      bubble.textContent = "";
      return;
    }
    const update = queue.shift();
    current = update || null;
    if (!update) {
      showing = false;
      bubble.hidden = true;
      bubble.textContent = "";
      return;
    }
    showing = true;
    const text = update.count > 1 ? summary(update.count) : update.text;
    bubble.textContent = text;
    bubble.hidden = false;
    if (voice && !blocked) speak(text);
    else timer = setTimeout(next, hold);
  }

  function speak(text) {
    let done = false;
    const mine = ++spoken;
    const finish = (wait = PAUSE) => {
      if (done) return;
      done = true;
      if (mine !== spoken) return; // cut short by pause(): what comes next waits for resume()
      setSpeaking(false);
      clearTimeout(timer);
      timer = setTimeout(next, wait);
    };
    try {
      const utterance = new SpeechSynthesisUtterance(speakable(text));
      utterance.voice = voice;
      utterance.lang = voice.lang || "en-US";
      utterance.onend = () => finish();
      utterance.onboundary = (event) => { // each spoken word pulses the Brain (only counted: the words stay here)
        if (event?.name === "word" && !done) onWord();
      };
      utterance.onerror = (event) => {
        if (event?.error !== "not-allowed") return finish();
        blocked = true; // not spoken: the bubble stays its usual time, and the user is told to click the page
        onBlocked(true);
        return finish(hold);
      };
      setSpeaking(true);
      speechSynthesis.speak(utterance);
      timer = setTimeout(() => { // a voice that never says it ended is stopped, so the next one isn't stuck behind it
        try {
          speechSynthesis.cancel();
        } catch { /* nothing to stop */ }
        finish();
      }, guardMs(text, hold));
    } catch {
      setSpeaking(false);
      timer = setTimeout(next, hold);
    }
  }

  function unblock() { // the user clicked the page: the next update is spoken
    if (!blocked) return;
    blocked = false;
    onBlocked(false);
  }

  function stop() { // the speech in progress ends now; its end handler moves the queue on
    try {
      speechSynthesis.cancel();
    } catch { /* nothing was speaking */ }
  }

  function say(text, { priority = false } = {}) {
    const words = String(text || "").trim();
    if (!words) return;
    if (priority) { // the Brain's answer to the user: first in line, never part of a summary
      const answers = queue.filter((update) => update.priority).length;
      queue.splice(answers, 0, { text: words, count: 1, priority: true });
      if (showing && !current?.priority) { // a background update gives way at once, and isn't repeated
        if (speaking) stop();
        else next();
      } else if (!showing) {
        next();
      }
      return;
    }
    queue.push({ text: words, count: 1 });
    const updates = queue.filter((update) => !update.priority);
    if (updates.length > WAITING) { // a burst: what waits becomes one summary, and the voice stops
      queue = [...queue.filter((update) => update.priority),
               { text: "", count: updates.reduce((sum, update) => sum + update.count, 0) }];
      if (speaking && !current?.priority) stop();
    }
    if (!showing) next();
  }

  function pause() { // the user started talking: speech stops now, and nothing more is spoken or shown
    paused = true;
    spoken += 1;
    clearTimeout(timer);
    if (speaking) stop();
    setSpeaking(false);
    next();
  }

  function resume() { // the turn ended: what waited comes now
    if (!paused) return;
    paused = false;
    if (!showing) next();
  }

  async function voices() { // the browser fills its list of voices a moment after the page loads
    let list = speechSynthesis.getVoices();
    if (!list.length) {
      await new Promise((resolve) => {
        const done = () => resolve();
        speechSynthesis.addEventListener?.("voiceschanged", done, { once: true });
        setTimeout(done, 1500);
      });
      list = speechSynthesis.getVoices();
    }
    return list;
  }

  async function setEnabled(on) {
    if (!on) {
      voice = null;
      try {
        speechSynthesis.cancel();
      } catch { /* nothing was speaking */ }
      setSpeaking(false);
      return { on: false, reason: "" };
    }
    let local = [];
    try {
      local = (await voices()).filter((one) => one.localService === true);
    } catch {
      local = [];
    }
    if (!local.length) {
      voice = null;
      return { on: false, reason: "No voice on this computer" };
    }
    const english = local.filter((one) => /^en\b/i.test(one.lang || ""));
    voice = english.find((one) => one.default) || english[0] || local.find((one) => one.default) || local[0];
    return { on: true, reason: "" };
  }

  return { say, pause, resume, setEnabled, unblock, get enabled() { return Boolean(voice); } };
}
