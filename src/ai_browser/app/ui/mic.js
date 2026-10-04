// The microphone, only while a turn is open: the page asks for it when the user starts talking, and every track stops
// when the turn ends, so the browser's recording dot shows only then. An AudioWorklet (mic-worklet.js) turns the sound
// into 16 kHz mono 16-bit samples, posted in 250 ms chunks; nothing is kept here: each chunk goes to onChunk.
"use strict";

export const CONSTRAINTS = { audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true,
                                      autoGainControl: true } };
const FLUSH_WAIT = 300; // ms for the worklet to hand over the samples it still holds

async function graph(stream, rate) { // an AudioContext at `rate` (or the computer's own rate), with the worklet loaded
  const context = rate ? new AudioContext({ sampleRate: rate }) : new AudioContext();
  try {
    await context.audioWorklet.addModule(new URL("./mic-worklet.js", import.meta.url).href);
    return { context, source: context.createMediaStreamSource(stream) };
  } catch (error) {
    context.close().catch(() => {});
    throw error;
  }
}

export async function openMic({ onChunk, onError = () => {} }) {
  const stream = await navigator.mediaDevices.getUserMedia(CONSTRAINTS);
  const tracks = stream.getTracks();
  const stopTracks = () => { for (const track of tracks) track.stop(); };
  let built = null;
  try {
    try {
      built = await graph(stream, 16000); // Whisper's rate, if this computer gives it
    } catch {
      built = await graph(stream, 0); // whatever it gives: the worklet averages it down to 16 kHz
    }
    const { context, source } = built;
    const node = new AudioWorkletNode(context, "pcm16k", { numberOfInputs: 1, numberOfOutputs: 1,
                                                           outputChannelCount: [1] });
    let closed = false;
    node.port.onmessage = (event) => {
      if (!closed && event.data instanceof ArrayBuffer) onChunk(event.data);
    };
    node.onprocessorerror = () => { if (!closed) onError(new DOMException("The sound stopped", "AbortError")); };
    for (const track of tracks) {
      track.addEventListener("ended", () => { // unplugged, or taken by the system
        if (!closed) onError(new DOMException("The microphone stopped", "NotReadableError"));
      });
    }
    source.connect(node);
    node.connect(context.destination); // silent (the worklet writes no output): it keeps the worklet running
    if (context.state !== "running") await context.resume();
    const close = () => {
      try {
        source.disconnect();
        node.disconnect();
      } catch { /* already apart */ }
      context.close().catch(() => {});
    };
    return {
      async stop() { // the turn ends: the mic closes now, then the worklet hands over what it still holds
        if (closed) return;
        stopTracks();
        await new Promise((resolve) => {
          const timer = setTimeout(resolve, FLUSH_WAIT);
          node.port.onmessage = (event) => {
            if (closed) return;
            if (event.data instanceof ArrayBuffer) onChunk(event.data);
            else if (event.data === "flushed") {
              clearTimeout(timer);
              resolve();
            }
          };
          node.port.postMessage("flush");
        });
        closed = true;
        close();
      },
      cancel() { // thrown away: nothing more is handed over
        if (closed) return;
        closed = true;
        stopTracks();
        node.port.onmessage = null;
        close();
      },
    };
  } catch (error) {
    stopTracks();
    built?.context.close().catch(() => {});
    throw error;
  }
}
