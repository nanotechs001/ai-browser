// The Brain, drawn as a glowing blob: one WebGL canvas where a fragment shader ray-marches a sphere whose surface moves
// with layered noise, lit with a soft rim and a halo. Its state (idle, thinking, alert, speaking) eases the colours and
// the motion from one to the next. Without WebGL, or when the context is lost, a CSS orb takes over with the same
// states (the stage's data-state). With reduced motion, the surface stays still and only state changes are drawn.
"use strict";

const STATES = ["idle", "thinking", "alert", "speaking"];
const VERTEX = "attribute vec2 p; void main() { gl_Position = vec4(p, 0.0, 1.0); }";
const FRAGMENT = `
precision mediump float;
uniform vec2 u_res;
uniform float u_time;
uniform vec4 u_mix;
float hash(vec3 p) { p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
float noise(vec3 x) {
  vec3 i = floor(x); vec3 f = fract(x); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(hash(i), hash(i + vec3(1.0, 0.0, 0.0)), f.x),
                 mix(hash(i + vec3(0.0, 1.0, 0.0)), hash(i + vec3(1.0, 1.0, 0.0)), f.x), f.y),
             mix(mix(hash(i + vec3(0.0, 0.0, 1.0)), hash(i + vec3(1.0, 0.0, 1.0)), f.x),
                 mix(hash(i + vec3(0.0, 1.0, 1.0)), hash(i + vec3(1.0, 1.0, 1.0)), f.x), f.y), f.z);
}
float fbm(vec3 p) { float v = 0.0; float a = 0.5; for (int i = 0; i < 3; i++) { v += a * noise(p); p *= 2.03; a *= 0.5; } return v; }
float speed() { return dot(u_mix, vec4(0.22, 0.9, 0.45, 0.7)); }
float amp() { return dot(u_mix, vec4(0.07, 0.15, 0.10, 0.16)); }
float map(vec3 p) {
  float t = u_time * speed();
  return (length(p) - 1.0 - amp() * (fbm(p * 1.15 + vec3(0.0, t, t * 0.7)) - 0.5) * 2.0) * 0.6;
}
vec3 normalAt(vec3 p) {
  vec2 e = vec2(0.003, 0.0);
  return normalize(vec3(map(p + e.xyy) - map(p - e.xyy), map(p + e.yxy) - map(p - e.yxy), map(p + e.yyx) - map(p - e.yyx)));
}
void main() {
  vec2 uv = (gl_FragCoord.xy * 2.0 - u_res) / min(u_res.x, u_res.y);
  vec3 ro = vec3(0.0, 0.0, 3.3);
  vec3 rd = normalize(vec3(uv * 1.15, -1.9));
  vec3 c1 = (mat4(vec4(0.36, 0.52, 0.98, 0.0), vec4(0.30, 0.40, 1.00, 0.0), vec4(0.96, 0.45, 0.32, 0.0),
                 vec4(0.30, 0.90, 0.72, 0.0)) * u_mix).rgb;
  vec3 c2 = (mat4(vec4(0.72, 0.42, 0.98, 0.0), vec4(0.45, 0.90, 1.00, 0.0), vec4(1.00, 0.78, 0.42, 0.0),
                 vec4(0.62, 0.98, 0.86, 0.0)) * u_mix).rgb;
  float b = dot(ro, rd);
  float h = b * b - dot(ro, ro) + 1.5 * 1.5;
  vec3 color = vec3(0.0);
  float alpha = 0.0;
  if (h > 0.0) {
    float t = -b - sqrt(h);
    for (int i = 0; i < 40; i++) {
      float d = map(ro + rd * t);
      if (d < 0.002) { alpha = 1.0; break; }
      t += d;
      if (t > 6.0) break;
    }
    if (alpha > 0.5) {
      vec3 p = ro + rd * t;
      vec3 n = normalAt(p);
      float fres = pow(1.0 - max(dot(n, -rd), 0.0), 2.2);
      float light = 0.30 + 0.70 * max(dot(n, normalize(vec3(-0.5, 0.7, 0.8))), 0.0);
      float swirl = fbm(p * 2.3 + vec3(u_time * speed() * 0.6));
      color = mix(c1, c2, smoothstep(0.25, 0.75, swirl)) * light + c2 * fres * 1.3;
    }
  }
  float r = length(uv);
  float glow = (exp(-5.0 * max(r - 0.42, 0.0)) * 0.55 + exp(-2.0 * max(r - 0.42, 0.0)) * 0.12) * (1.0 - alpha)
             * (1.0 - smoothstep(0.82, 1.0, r));
  color += c1 * glow;
  gl_FragColor = vec4(color, max(alpha, glow));
}`;
const FRAME_MS = 1000 / 30; // a blob doesn't need more than 30 frames a second

export function createBlob(canvas, orb, { reduced = matchMedia("(prefers-reduced-motion: reduce)") } = {}) {
  const stage = canvas.closest(".stage") || canvas.parentElement;
  const target = [1, 0, 0, 0]; // the state's weights the blob eases toward
  const mix = [1, 0, 0, 0];
  let gl = null;
  let uniforms = null;
  let frame = 0;
  let last = 0;
  let time = 0;
  const api = { mode: "css", setState, destroy };

  function setState(state) {
    if (!STATES.includes(state)) return;
    if (stage.dataset.state !== state) stage.dataset.state = state; // the CSS orb (and the tests) follow this
    target.fill(0);
    target[STATES.indexOf(state)] = 1;
    wake();
  }

  function fallback() { // no WebGL here, or the context was lost: the CSS orb
    cancelAnimationFrame(frame);
    frame = 0;
    gl = null;
    api.mode = "css";
    stage.dataset.mode = "css";
    orb.hidden = false;
    canvas.hidden = true;
  }

  function compile(kind, source) {
    const shader = gl.createShader(kind);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    return gl.getShaderParameter(shader, gl.COMPILE_STATUS) ? shader : null;
  }

  function build() {
    const vertex = compile(gl.VERTEX_SHADER, VERTEX);
    const fragment = compile(gl.FRAGMENT_SHADER, FRAGMENT);
    if (!vertex || !fragment) return false;
    const program = gl.createProgram();
    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return false;
    gl.useProgram(program);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const where = gl.getAttribLocation(program, "p");
    gl.enableVertexAttribArray(where);
    gl.vertexAttribPointer(where, 2, gl.FLOAT, false, 0, 0);
    uniforms = { res: gl.getUniformLocation(program, "u_res"), time: gl.getUniformLocation(program, "u_time"),
                 mix: gl.getUniformLocation(program, "u_mix") };
    return true;
  }

  function draw(now) {
    frame = 0;
    if (!gl) return;
    if (last && now - last < FRAME_MS - 2) { // not yet time for the next frame
      frame = requestAnimationFrame(draw);
      return;
    }
    const step = last ? Math.min(0.1, (now - last) / 1000) : 1 / 30;
    last = now;
    const still = reduced.matches;
    let easing = false;
    for (let index = 0; index < 4; index += 1) {
      mix[index] += (target[index] - mix[index]) * Math.min(1, step * (still ? 1.5 : 3));
      if (Math.abs(target[index] - mix[index]) > 0.003) easing = true;
    }
    time += step * (still ? (easing ? 0.2 : 0) : 1);
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform2f(uniforms.res, canvas.width, canvas.height);
    gl.uniform1f(uniforms.time, time);
    gl.uniform4fv(uniforms.mix, mix);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    if (!still || easing) frame = requestAnimationFrame(draw); // reduced motion: drawn only while it changes
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
    gl?.getExtension("WEBGL_lose_context")?.loseContext();
    gl = null;
  }

  const size = Math.min(360, canvas.clientWidth || 300); // CSS pixels, at most twice that in device pixels
  canvas.width = canvas.height = Math.round(size * Math.min(2, devicePixelRatio || 1));
  try {
    gl = canvas.getContext("webgl", { alpha: true, premultipliedAlpha: true, antialias: false });
  } catch {
    gl = null;
  }
  if (gl && build()) {
    api.mode = "webgl";
    stage.dataset.mode = "webgl";
    orb.hidden = true;
    canvas.hidden = false;
    canvas.addEventListener("webglcontextlost", (event) => {
      event.preventDefault();
      fallback();
    });
    reduced.addEventListener?.("change", wake);
  } else {
    fallback();
  }
  setState(stage.dataset.state || "idle");
  return api;
}
