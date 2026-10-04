// The Brain's shape: thousands of points in the form of a human brain (two hemispheres with their folds, the
// cerebellum at the back and the stem below), made from a seed. Pure: no DOM, no WebGL and no Math.random, so one seed
// always gives the same brain. Axes: x across (+x is the brain's own left), y up, z toward the brain's front.
"use strict";

export const KIND = Object.freeze({ cortex: 0, cerebellum: 1, stem: 2, core: 3 });
export const HEMISPHERES = Object.freeze([Object.freeze([-0.17, 0.06, 0]), Object.freeze([0.17, 0.06, 0])]);

function rng(seed) { // mulberry32: a small, fast generator with a 32-bit state
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hash(x, y, z) { // integer lattice point -> 0..1
  let h = Math.imul(x, 374761393) ^ Math.imul(y, 668265263) ^ Math.imul(z, 1440670441);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
}

function noise(x, y, z) { // value noise, smoothly blended between lattice points
  const ix = Math.floor(x);
  const iy = Math.floor(y);
  const iz = Math.floor(z);
  const fx = x - ix;
  const fy = y - iy;
  const fz = z - iz;
  const u = fx * fx * (3 - 2 * fx);
  const v = fy * fy * (3 - 2 * fy);
  const w = fz * fz * (3 - 2 * fz);
  const lerp = (a, b, t) => a + (b - a) * t;
  return lerp(
    lerp(lerp(hash(ix, iy, iz), hash(ix + 1, iy, iz), u), lerp(hash(ix, iy + 1, iz), hash(ix + 1, iy + 1, iz), u), v),
    lerp(lerp(hash(ix, iy, iz + 1), hash(ix + 1, iy, iz + 1), u),
         lerp(hash(ix, iy + 1, iz + 1), hash(ix + 1, iy + 1, iz + 1), u), v),
    w);
}

function ridge(x, y, z) { // 1 on a fold's crest, 0 in a groove: 2 octaves of 1 - |2·noise - 1|
  let value = 0;
  let weight = 0.65;
  let frequency = 1;
  for (let octave = 0; octave < 2; octave += 1) {
    value += weight * (1 - Math.abs(2 * noise(x * frequency + 11.3 * octave, y * frequency, z * frequency) - 1));
    frequency *= 2.3;
    weight *= 0.35;
  }
  return value / 0.8775;
}

function direction(random) { // a random direction on the unit sphere: [dx, dy (up), dz (front)]
  const dy = random() * 2 - 1;
  const turn = random() * Math.PI * 2;
  const radius = Math.sqrt(1 - dy * dy);
  return [radius * Math.cos(turn), dy, radius * Math.sin(turn)];
}

// count points, 6 numbers each: x, y, z, kind (KIND), fold (0 in a groove to 1 on a ridge), phase (0 to 1). The kinds
// are mixed exactly (80% cortex, 11% cerebellum, 5% stem, the core the rest) and shuffled, so any first n points are an
// even sample of the whole brain: the level of detail is just how many are drawn.
export function brainPoints(count = 8000, seed = 7) {
  const random = rng(seed);
  const out = [];
  const cortex = Math.round(count * 0.8);
  const cerebellum = cortex + Math.round(count * 0.11);
  const stem = cerebellum + Math.round(count * 0.05);
  let guard = 0;
  while (out.length / 6 < cortex && guard++ < count * 40) {
    const h = random() < 0.5 ? -1 : 1; // the hemisphere: -1 right, +1 left
    const [dx, dy, dz] = direction(random);
    let x = dx * 0.42;
    let y = dy * 0.47;
    let z = dz * 0.7;
    if (x * h < 0) x *= 0.3; // the flat inner face: the gap between the hemispheres
    if (y < -0.12) y = -0.12 + (y + 0.12) * 0.55; // a flatter underside
    if (dz < -0.35) { // the back narrows
      x *= 0.92;
      y *= 0.94;
    }
    const temporal = Math.exp(-((z - 0.1) ** 2) / 0.05 - ((y + 0.2) ** 2) / 0.02) * Math.abs(dx);
    y -= 0.1 * temporal; // the temporal lobe hangs down at the side
    x += h * 0.05 * temporal;
    x += h * 0.17;
    y += 0.06;
    const lateral = Math.abs(dx) > 0.45 && z > -0.2 && z < 0.34 && Math.abs(y - (-0.07 + (0.34 - z) * 0.3)) < 0.025;
    const central = y > 0.05 && Math.abs(z - (0.02 + (y - 0.05) * 0.25)) < 0.018 && x * h > 0.05;
    if (lateral || central) continue; // the two big grooves
    const fold = ridge(x * 9.5 + 3, y * 9.5, z * 9.5);
    if (random() > 0.04 + 0.96 * fold ** 6) continue; // points crowd onto the ridges, so the maze shows
    const length = Math.hypot(x - h * 0.17, y - 0.06, z) || 1;
    const dent = 0.03 * (fold - 0.6); // and the grooves sink in, along the normal
    out.push(x + ((x - h * 0.17) / length) * dent, y + ((y - 0.06) / length) * dent, z + (z / length) * dent,
             KIND.cortex, fold, random());
  }
  guard = 0;
  while (out.length / 6 < cerebellum && guard++ < count * 40) {
    const h = random() < 0.5 ? -1 : 1;
    const [dx, dy, dz] = direction(random);
    if (dx * h < -0.3) continue; // no points on the inner faces
    const x = h * 0.13 + dx * 0.2;
    const y = -0.3 + dy * 0.14;
    const z = -0.42 + dz * 0.19;
    const folia = 0.5 + 0.5 * Math.sin((y + 0.3) * 120 + dz * 4); // its fine horizontal folds
    if (random() > 0.1 + 0.9 * folia ** 2) continue;
    out.push(x, y, z, KIND.cerebellum, folia, random());
  }
  while (out.length / 6 < stem) { // never rejects: it fills up to the three parts' total
    const t = random();
    const turn = random() * Math.PI * 2;
    const radius = 0.075 - 0.02 * t + 0.035 * Math.exp(-((t - 0.25) ** 2) / 0.01); // tapering, with the pons' bulge
    out.push(radius * Math.cos(turn), -0.18 - 0.62 * t, -0.1 - 0.12 * t + radius * Math.sin(turn), KIND.stem, 0.6,
             random());
  }
  while (out.length / 6 < count) { // the faint core: never rejects either, so the total is exact
    const [dx, dy, dz] = direction(random);
    const radius = Math.cbrt(random()) * 0.32;
    out.push(dx * radius * 0.9, 0.04 + dy * radius * 0.7, dz * radius * 1.3, KIND.core, 0.3, random());
  }
  for (let index = out.length / 6 - 1; index > 0; index -= 1) { // Fisher-Yates, on the same random stream
    const other = Math.floor(random() * (index + 1));
    for (let part = 0; part < 6; part += 1) {
      const kept = out[index * 6 + part];
      out[index * 6 + part] = out[other * 6 + part];
      out[other * 6 + part] = kept;
    }
  }
  return new Float32Array(out);
}

// The links the signals travel along: cortex points picked in order (probability 0.12, at most `picks`), each linked
// to its `perNode` nearest other picks between 0.06 and 0.22 away, at most `max` links. Index pairs, so at most 65536
// points.
export function synapses(points, { picks = 450, perNode = 2, max = 900, seed = 3 } = {}) {
  const random = rng(seed);
  const count = points.length / 6;
  const chosen = [];
  for (let index = 0; index < count && chosen.length < picks; index += 1) {
    if (points[index * 6 + 3] === KIND.cortex && random() < 0.12) chosen.push(index);
  }
  const links = [];
  for (const one of chosen) {
    const near = [];
    for (const two of chosen) {
      if (one === two) continue;
      const distance = Math.hypot(points[one * 6] - points[two * 6], points[one * 6 + 1] - points[two * 6 + 1],
                                  points[one * 6 + 2] - points[two * 6 + 2]);
      if (distance > 0.06 && distance < 0.22) near.push([distance, two]);
    }
    near.sort((a, b) => a[0] - b[0]);
    for (const [, two] of near.slice(0, perNode)) if (links.length / 2 < max) links.push(one, two);
  }
  return new Uint16Array(links);
}
