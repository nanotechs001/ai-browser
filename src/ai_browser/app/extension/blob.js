// The Brain, drawn as a brain: thousands of glowing points in its shape (brainshape.js) over a faint web of links,
// with signals running along them. One WebGL1 canvas and three draws a frame (the web, the pulses, the cloud), at most
// 30 frames a second. Its state (idle, thinking, alert, speaking) blends the colours and the motion from one to the
// next. The points are made after the page's first paint; until then, and without WebGL or once the context is lost,
// the dotted brain in CSS (the orb) shows the same states (the stage's data-state). With reduced motion it is still:
// drawn once its points are ready, then only for a short colour fade after a change.
"use strict";

import { brainPoints, synapses } from "./brainshape.js";

const STATES = ["idle", "thinking", "alert", "speaking"];
const FRAME_MS = 1000 / 30; // the Brain doesn't need more than 30 frames a second
const TABLE = { // the states' own numbers, in STATES' order; what is drawn is their blend by the state weights
  speed: [0.25, 1, 0.6, 0.8], // how fast the points drift
  flash: [0.35, 2.2, 1.2, 1.6], // how often a point flashes
  pulse: [0.15, 0.84, 0.54, 0.6], // how fast the signals travel
  sway: [20, 12, 20, 20], // seconds per sway, there and back
};
const YAW = (-55 * Math.PI) / 180; // its left side three-quarters on: the speech area faces the user
const SWAY = (30 * Math.PI) / 180;
const PITCH = 0.22; // the user looks down onto it a little
const STILL = { yaw: YAW, pitch: PITCH, scale: 1, bright: 0, motion: 0 }; // reduced motion: no drift, sway or beat
const BEAT_S = 1.1; // alert: a double heartbeat this often
const FADE_S = 0.7; // reduced motion: a change of state, or a new agent's flash, is a straight fade this long
const LOW = 2500; // adaptive detail: never fewer points than this
const SLOW_MS = 45; // drawn frames further apart than this, on average over 2 s, halve the points
const GAP_MS = 250; // a longer gap (a hidden tab, a still Brain) isn't a slow machine: the window starts again
const CLOUD = ["u_mix", "u_yaw", "u_pitch", "u_scale", "u_dpr", "u_motion", "u_focus", "u_burst", "u_bright", "u_flow",
               "u_flash", "u_wave", "u_size", "u_word"];
const LINKS = ["u_mix", "u_yaw", "u_pitch", "u_scale", "u_dpr", "u_motion", "u_focus", "u_burst", "u_travel", "u_pulse",
               "u_burst_dir"];

const SHARED = `
precision highp float;
uniform vec4 u_mix;
uniform float u_yaw;
uniform float u_pitch;
uniform float u_scale;
uniform float u_dpr;
uniform float u_motion;
uniform vec2 u_focus;
uniform float u_burst;
varying vec3 v_color;
varying float v_alpha;
vec3 view(vec3 p) {
  float c = cos(u_yaw);
  float s = sin(u_yaw);
  p = vec3(c * p.x + s * p.z, p.y, -s * p.x + c * p.z);
  float cp = cos(u_pitch);
  float sp = sin(u_pitch);
  return vec3(p.x, cp * p.y - sp * p.z, sp * p.y + cp * p.z);
}
float aim(vec3 q) {
  vec2 side = normalize(q.xz + vec2(0.0001, 0.0));
  return mix(1.0, 0.35 + 0.65 * smoothstep(-0.2, 0.8, dot(side, u_focus)), u_mix.z);
}
`;
const CLOUD_VERTEX = `${SHARED}
attribute vec3 a_pos;
attribute vec3 a_info;
uniform float u_bright;
uniform float u_flow;
uniform float u_flash;
uniform float u_wave;
uniform float u_size;
uniform float u_word;
void main() {
  float kind = a_info.x;
  float phase = a_info.z * 6.2831853;
  vec3 centre = kind < 0.5 ? vec3(a_pos.x < 0.0 ? -0.17 : 0.17, 0.06, 0.0) : vec3(0.0);
  vec3 normal = a_pos - centre;
  normal /= max(length(normal), 0.0001);
  float drift = dot(u_mix, vec4(0.006, 0.020, 0.010, 0.010)) * u_motion;
  vec3 wander = vec3(sin(0.7 * u_flow + phase), cos(0.5 * u_flow + 1.7 * phase),
                     sin(0.6 * u_flow + 2.3 * phase)) * drift;
  if (kind < 0.5) wander -= normal * dot(wander, normal);
  else wander *= 0.5;
  vec3 q = view((a_pos + wander + normal * 0.03 * u_burst * u_motion) * u_scale);
  float persp = 2.6 / (2.6 - q.z);
  gl_Position = vec4(q.xy * persp * 1.05, 0.0, 1.0);
  float flash = pow(max(0.0, sin(u_flash + 37.0 * phase)), 60.0) * aim(q) * u_motion;
  float ahead = a_pos.z - u_wave; // squared by hand: GLSL's pow() is undefined for a negative base (NaN on ANGLE)
  float wave = u_mix.y * exp(-ahead * ahead / 0.01) * u_motion;
  float ring = u_word * step(abs(distance(a_pos, vec3(0.30, 0.0, 0.35)) - 0.6 * (1.0 - u_word)), 0.05) * u_motion;
  vec3 ridge = (mat4(vec4(0.30, 0.45, 1.00, 0.0), vec4(0.30, 0.85, 1.00, 0.0), vec4(1.00, 0.55, 0.30, 0.0),
                     vec4(0.30, 0.95, 0.75, 0.0)) * u_mix).rgb;
  vec3 groove = (mat4(vec4(0.70, 0.50, 1.00, 0.0), vec4(0.65, 0.50, 1.00, 0.0), vec4(1.00, 0.30, 0.25, 0.0),
                      vec4(0.55, 1.00, 0.90, 0.0)) * u_mix).rgb;
  vec3 base = mix(groove, ridge, a_info.y);
  bool core = kind > 2.5;
  if (core) base = mix(base, vec3(1.0), 0.3);
  float depth = 0.45 + 0.55 * smoothstep(-0.8, 0.8, q.z);
  v_color = base * depth * (1.0 + u_bright) + vec3(1.0, 0.95, 0.9) * (1.2 * flash + wave + ring + u_burst);
  v_alpha = (core ? 0.35 : 0.85) * depth;
  gl_PointSize = u_size * u_dpr * persp * (1.0 + 1.6 * flash);
}`;
const CLOUD_FRAGMENT = `
precision mediump float;
varying vec3 v_color;
varying float v_alpha;
void main() {
  float a = (1.0 - smoothstep(0.05, 0.5, length(gl_PointCoord - 0.5))) * v_alpha;
  gl_FragColor = vec4(v_color * a, a);
}`;
const LINK_VERTEX = `${SHARED}
attribute vec3 a_a;
attribute vec3 a_b;
attribute float a_t;
attribute float a_phase;
uniform float u_travel;
uniform float u_pulse;
uniform vec2 u_burst_dir;
varying float v_round;
void main() {
  float t = u_pulse > 0.5 ? fract(u_travel + a_phase) : a_t;
  vec3 mid = (a_a + a_b) * 0.5;
  vec3 bow = mid + mid / max(length(mid), 0.0001) * 0.04;
  vec3 q = view(mix(mix(a_a, bow, t), mix(bow, a_b, t), t) * u_scale);
  float persp = 2.6 / (2.6 - q.z);
  gl_Position = vec4(q.xy * persp * 1.05, 0.0, 1.0);
  vec3 m = view(mid);
  float fires = step(fract(a_phase * 7.0), dot(u_mix, vec4(0.10, 0.85, 0.60, 0.50)) * aim(m));
  vec2 side = normalize(m.xz + vec2(0.0001, 0.0));
  fires = max(fires, step(0.2, u_burst) * step(0.0001, dot(side, u_burst_dir)));
  float swell = smoothstep(0.85, 1.0, t) * u_pulse;
  float depth = 0.5 + 0.5 * smoothstep(-0.8, 0.8, q.z);
  vec3 tint = (mat4(vec4(0.55, 0.75, 1.00, 0.0), vec4(0.60, 1.00, 1.00, 0.0), vec4(1.00, 0.80, 0.50, 0.0),
                    vec4(0.70, 1.00, 0.90, 0.0)) * u_mix).rgb;
  v_color = tint * (1.0 + 0.6 * swell);
  v_alpha = (u_pulse > 0.5 ? fires * u_motion : 0.10) * depth;
  v_round = u_pulse;
  gl_PointSize = 4.0 * u_dpr * persp * (1.0 + swell);
}`;
const LINK_FRAGMENT = `
precision mediump float;
varying vec3 v_color;
varying float v_alpha;
varying float v_round;
void main() {
  float a = v_alpha;
  if (v_round > 0.5) a *= 1.0 - smoothstep(0.0, 0.5, length(gl_PointCoord - 0.5));
  gl_FragColor = vec4(v_color * a, a);
}`;

export function createBlob(canvas, orb, { reduced = matchMedia("(prefers-reduced-motion: reduce)"), count = 8000,
                                          seed = 7 } = {}) {
  const stage = canvas.closest(".stage") || canvas.parentElement;
  const target = [1, 0, 0, 0]; // the state's weights the Brain moves toward
  const mix = [1, 0, 0, 0];
  const clock = { flow: 0, flash: 0, travel: 0, sway: 0, wave: 0, breath: 0, beat: 0 };
  // a new agent's flash (and the side it fires toward), the alert's aim, a spoken word's ring
  const effects = { burst: 0, burstDir: [0, 0], focus: [0, 0], word: 0 };
  const pace = { start: 0, frames: 0, last: 0 }; // adaptive detail: the drawn frames of the current window
  const pending = { frame: 0, timer: 0 }; // the points are made after the first paint
  let gl = null;
  let cloud = null;
  let links = null;
  let buffers = null;
  let pairs = 0; // links
  let n = 0; // points drawn: 0 until they are made
  let ratio = 1;
  let frame = 0;
  let last = 0;
  let shown = false; // the canvas has replaced the orb
  const api = { mode: "css", setState, destroy };

  function setState(state) {
    if (!STATES.includes(state)) return;
    const was = stage.dataset.state;
    if (was !== state) stage.dataset.state = state; // the CSS orb (and the tests) follow this
    target.fill(0);
    target[STATES.indexOf(state)] = 1;
    if (was !== state) wake(); // a still Brain is drawn again only for a change (in motion it never stops)
  }

  function setCount(value) {
    n = value;
    if (stage.dataset.points !== String(n)) stage.dataset.points = String(n); // only when it changes: no style work
  }

  function fallback() { // no WebGL here, or the context was lost: the dotted brain in CSS
    cancelAnimationFrame(frame);
    frame = 0;
    cancelAnimationFrame(pending.frame);
    clearTimeout(pending.timer);
    gl = null;
    n = 0;
    api.mode = "css";
    stage.dataset.mode = "css";
    delete stage.dataset.points;
    orb.hidden = false;
    canvas.hidden = true;
  }

  function compile(kind, source) {
    const shader = gl.createShader(kind);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    return gl.getShaderParameter(shader, gl.COMPILE_STATUS) ? shader : null;
  }

  function program(vertexSource, fragmentSource, attributes, names) {
    const vertex = compile(gl.VERTEX_SHADER, vertexSource);
    const fragment = compile(gl.FRAGMENT_SHADER, fragmentSource);
    if (!vertex || !fragment) return null;
    const made = gl.createProgram();
    gl.attachShader(made, vertex);
    gl.attachShader(made, fragment);
    attributes.forEach((name, index) => gl.bindAttribLocation(made, index, name));
    gl.linkProgram(made);
    if (!gl.getProgramParameter(made, gl.LINK_STATUS)) return null;
    const uniforms = {};
    for (const name of names) uniforms[name] = gl.getUniformLocation(made, name);
    return { program: made, uniforms };
  }

  function build() {
    cloud = program(CLOUD_VERTEX, CLOUD_FRAGMENT, ["a_pos", "a_info"], CLOUD);
    links = program(LINK_VERTEX, LINK_FRAGMENT, ["a_a", "a_b", "a_t", "a_phase"], LINKS);
    if (!cloud || !links) return false;
    buffers = { cloud: gl.createBuffer(), web: gl.createBuffer(), pulses: gl.createBuffer() };
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA); // premultiplied colours
    return true;
  }

  function makePoints() { // a task after the first paint: the page shows first, the brain a moment later
    pending.timer = 0;
    if (!gl || gl.isContextLost()) return; // lost meanwhile: the orb stays, and fallback() follows
    const points = brainPoints(count, seed);
    const ends = synapses(points);
    pairs = ends.length / 2;
    const web = new Float32Array(pairs * 16); // 2 vertices a link: both ends' positions, t (0 or 1), the link's phase
    const pulses = new Float32Array(pairs * 8); // 1 vertex a link
    for (let link = 0; link < pairs; link += 1) {
      const one = ends[link * 2] * 6;
      const two = ends[link * 2 + 1] * 6;
      const phase = (link * 0.618) % 1;
      const both = [points[one], points[one + 1], points[one + 2], points[two], points[two + 1], points[two + 2]];
      web.set([...both, 0, phase, ...both, 1, phase], link * 16);
      pulses.set([...both, 0, phase], link * 8);
    }
    for (const [name, data] of [["cloud", points], ["web", web], ["pulses", pulses]]) {
      gl.bindBuffer(gl.ARRAY_BUFFER, buffers[name]);
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
    }
    setCount(count);
    wake();
  }

  function blend(row) {
    return row[0] * mix[0] + row[1] * mix[1] + row[2] * mix[2] + row[3] * mix[3];
  }

  function advance(step) { // normal motion: every clock moves on at its state's blended speed, so nothing jumps
    clock.flow = (clock.flow + step * blend(TABLE.speed)) % (200 * Math.PI);
    clock.flash = (clock.flash + step * blend(TABLE.flash)) % (2 * Math.PI);
    clock.travel = (clock.travel + step * blend(TABLE.pulse)) % 1;
    clock.sway = (clock.sway + (step * 2 * Math.PI) / blend(TABLE.sway)) % (10 * Math.PI);
    clock.wave = (clock.wave + step * 1.6) % (2 * Math.PI);
    clock.breath = (clock.breath + step * 1.3) % (2 * Math.PI);
    clock.beat = (clock.beat + step) % BEAT_S;
    const peak = (x) => Math.exp(-((x / 0.06) ** 2));
    const beat = (0.035 * peak(clock.beat) + 0.02 * peak(clock.beat - 0.22)) * mix[2];
    return { yaw: YAW + SWAY * Math.sin(clock.sway), pitch: PITCH + 0.05 * Math.sin(0.6 * clock.sway),
             scale: (1 + 0.015 * Math.sin(clock.breath)) * (1 + beat), bright: (0.25 * beat) / 0.035, motion: 1 };
  }

  function ease(step, still) { // the weights move toward the state: eased, or a straight line that lands when still
    let changing = false;
    const move = step / FADE_S;
    for (let index = 0; index < 4; index += 1) {
      const gap = target[index] - mix[index];
      if (still) mix[index] = Math.abs(gap) <= move ? target[index] : mix[index] + Math.sign(gap) * move;
      else mix[index] += gap * Math.min(1, step * 3);
      if (mix[index] !== target[index]) changing = true;
    }
    return changing;
  }

  function measure(now) { // adaptive detail: frames that come too far apart halve the points (never grown back)
    if (!pace.last || now - pace.last > GAP_MS) Object.assign(pace, { start: now, frames: 0 });
    else pace.frames += 1;
    pace.last = now;
    if (now - pace.start < 2000) return;
    if ((now - pace.start) / pace.frames > SLOW_MS && n > LOW) setCount(Math.max(LOW, Math.floor(n / 2)));
    Object.assign(pace, { start: now, frames: 0 });
  }

  function attribute(index, size, stride, offset) {
    gl.enableVertexAttribArray(index);
    gl.vertexAttribPointer(index, size, gl.FLOAT, false, stride, offset);
  }

  function shared(uniforms, view) { // set on every drawn frame: the tests read u_mix, u_focus and u_burst
    gl.uniform4fv(uniforms.u_mix, mix);
    gl.uniform1f(uniforms.u_yaw, view.yaw);
    gl.uniform1f(uniforms.u_pitch, view.pitch);
    gl.uniform1f(uniforms.u_scale, view.scale);
    gl.uniform1f(uniforms.u_dpr, ratio);
    gl.uniform1f(uniforms.u_motion, view.motion);
    gl.uniform2fv(uniforms.u_focus, effects.focus);
    gl.uniform1f(uniforms.u_burst, effects.burst);
  }

  function draw(now) {
    frame = 0;
    if (!gl || !n || gl.isContextLost()) return;
    if (last && now - last < FRAME_MS - 2) { // not yet time for the next frame
      frame = requestAnimationFrame(draw);
      return;
    }
    const step = last ? Math.min(0.1, (now - last) / 1000) : 1 / 30;
    last = now;
    measure(now);
    const still = reduced.matches;
    const changing = ease(step, still);
    const view = still ? STILL : advance(step);
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(links.program); // 1. the web, faint lines
    shared(links.uniforms, view);
    gl.uniform1f(links.uniforms.u_travel, clock.travel);
    gl.uniform2fv(links.uniforms.u_burst_dir, effects.burstDir);
    gl.uniform1f(links.uniforms.u_pulse, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffers.web);
    attribute(0, 3, 32, 0);
    attribute(1, 3, 32, 12);
    attribute(2, 1, 32, 24);
    attribute(3, 1, 32, 28);
    gl.drawArrays(gl.LINES, 0, pairs * 2);
    if (!still) { // 2. the pulses, one bright point travelling along each link that fires
      gl.uniform1f(links.uniforms.u_pulse, 1);
      gl.bindBuffer(gl.ARRAY_BUFFER, buffers.pulses);
      attribute(0, 3, 32, 0);
      attribute(1, 3, 32, 12);
      attribute(2, 1, 32, 24);
      attribute(3, 1, 32, 28);
      gl.drawArrays(gl.POINTS, 0, pairs);
    }
    gl.useProgram(cloud.program); // 3. the cloud
    shared(cloud.uniforms, view);
    gl.uniform1f(cloud.uniforms.u_bright, view.bright);
    gl.uniform1f(cloud.uniforms.u_flow, clock.flow);
    gl.uniform1f(cloud.uniforms.u_flash, clock.flash);
    gl.uniform1f(cloud.uniforms.u_wave, 0.7 * Math.sin(clock.wave));
    gl.uniform1f(cloud.uniforms.u_size, 1.5 * Math.min(1.6, Math.sqrt(count / n)));
    gl.uniform1f(cloud.uniforms.u_word, effects.word);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffers.cloud);
    gl.disableVertexAttribArray(2);
    gl.disableVertexAttribArray(3);
    attribute(0, 3, 24, 0);
    attribute(1, 3, 24, 12);
    gl.drawArrays(gl.POINTS, 0, n);
    if (!shown) { // the first frame with points: the canvas takes the orb's place
      shown = true;
      canvas.hidden = false;
      orb.hidden = true;
    }
    if (!still || changing) frame = requestAnimationFrame(draw); // still: drawn only while it changes
  }

  function wake() {
    if (gl && !frame) {
      last = 0;
      frame = requestAnimationFrame(draw);
    }
  }

  function destroy() {
    cancelAnimationFrame(frame);
    frame = 0;
    cancelAnimationFrame(pending.frame);
    clearTimeout(pending.timer);
    gl?.getExtension("WEBGL_lose_context")?.loseContext();
    gl = null;
  }

  const size = Math.min(360, canvas.clientWidth || 300); // CSS pixels, at most twice that in device pixels
  canvas.width = canvas.height = Math.round(size * Math.min(2, devicePixelRatio || 1));
  ratio = canvas.width / size;
  try {
    gl = canvas.getContext("webgl", { alpha: true, premultipliedAlpha: true, antialias: false });
  } catch {
    gl = null;
  }
  if (gl && build()) {
    api.mode = "webgl";
    stage.dataset.mode = "webgl";
    orb.hidden = false; // the dotted brain shows until the first frame with points
    canvas.hidden = true;
    canvas.addEventListener("webglcontextlost", (event) => {
      event.preventDefault();
      fallback();
    });
    reduced.addEventListener?.("change", wake);
    pending.frame = requestAnimationFrame(() => {
      pending.frame = 0;
      pending.timer = setTimeout(makePoints, 0);
    });
  } else {
    fallback();
  }
  setState(stage.dataset.state || "idle");
  return api;
}
