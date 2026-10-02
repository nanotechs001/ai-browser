// The Brain talking back: short updates, one at a time, in a speech bubble above the blob, and spoken aloud when the
// user switched Voice on. Speech uses only voices that run on this Mac (localService), so the words never leave it.
// More than three updates waiting become one summary, and the speech in progress stops: the voice never piles up.
"use strict";

const WAITING = 3;
const PAUSE = 600; // ms after a spoken update before the next one

export function createVoice({ bubble, onSpeaking = () => {}, onBlocked = () => {}, onWord = () => {},
                              hold = 5000 } = {}) {
  let queue = []; // [{text, count}]: count > 1 is a summary of that many updates
  let showing = false;
  let timer = null;
  let voice = null; // the on-device voice, while Voice is on
  let speaking = false;
  let blocked = false; // Chrome lets a page speak only after the user clicked it (a reloaded page must ask again)

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
    const update = queue.shift();
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
    const finish = (wait = PAUSE) => {
      if (done) return;
      done = true;
      setSpeaking(false);
      clearTimeout(timer);
      timer = setTimeout(next, wait);
    };
    try {
      const utterance = new SpeechSynthesisUtterance(text);
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
      }, Math.max(hold, 12000));
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

  function say(text) {
    const words = String(text || "").trim();
    if (!words) return;
    queue.push({ text: words, count: 1 });
    if (queue.length > WAITING) { // a burst: what waits becomes one summary, and the voice stops
      queue = [{ text: "", count: queue.reduce((sum, update) => sum + update.count, 0) }];
      if (speaking) {
        try {
          speechSynthesis.cancel();
        } catch { /* nothing was speaking */ }
      }
    }
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
      return { on: false, reason: "No voice on this Mac" };
    }
    const english = local.filter((one) => /^en\b/i.test(one.lang || ""));
    voice = english.find((one) => one.default) || english[0] || local.find((one) => one.default) || local[0];
    return { on: true, reason: "" };
  }

  return { say, setEnabled, unblock, get enabled() { return Boolean(voice); } };
}
