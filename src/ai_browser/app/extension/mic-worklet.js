// The microphone's sound as Whisper takes it: 16 kHz, mono, 16-bit little-endian, in chunks of 4,000 samples (250 ms).
// Any input rate works: each output sample is the average of the input samples in its span (a box filter), which is
// enough for speech. Each chunk goes to the page at once; nothing is kept here.
const RATE = 16000;
const CHUNK = 4000;

class Pcm16k extends AudioWorkletProcessor {
  constructor() {
    super();
    this.step = sampleRate / RATE; // input samples per output sample: 1, 2.75625 or 3
    this.edge = this.step; // where the current output sample's span ends, in input samples
    this.seen = 0;
    this.sum = 0;
    this.count = 0;
    this.chunk = new DataView(new ArrayBuffer(CHUNK * 2));
    this.filled = 0;
    this.port.onmessage = (event) => {
      if (event.data !== "flush") return;
      this.send(); // the turn ended: what is held goes now
      this.port.postMessage("flushed");
    };
  }

  send() {
    if (!this.filled) return;
    const buffer = this.chunk.buffer.slice(0, this.filled * 2);
    this.port.postMessage(buffer, [buffer]);
    this.filled = 0;
  }

  push(value) {
    const clamped = Math.max(-1, Math.min(1, value));
    this.chunk.setInt16(this.filled * 2, Math.round(clamped * 32767), true);
    this.filled += 1;
    if (this.filled === CHUNK) this.send();
  }

  process(inputs) {
    const channels = inputs[0];
    if (!channels || !channels.length) return true;
    const frames = channels[0].length;
    for (let frame = 0; frame < frames; frame += 1) {
      let value = 0;
      for (const channel of channels) value += channel[frame];
      this.sum += value / channels.length; // mono: the channels' average
      this.count += 1;
      this.seen += 1;
      if (this.seen >= this.edge) {
        this.push(this.sum / this.count);
        this.sum = 0;
        this.count = 0;
        this.edge += this.step;
      }
    }
    return true;
  }
}

registerProcessor("pcm16k", Pcm16k);
