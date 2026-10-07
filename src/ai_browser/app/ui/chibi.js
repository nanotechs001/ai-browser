// The workers (the new look): one original chibi per agent, in a dark hoodie and glowing headphones, sitting at a
// laptop (the desk draws the laptop: desk.js). A big round head, big eyes, rosy cheeks; the agent's colour shows on
// the shirt under the hoodie. Each part is an HTML layer holding one small SVG built here from a fixed table of
// shapes: nothing is parsed from strings and there is no innerHTML, so the poses (office.css) move HTML layers only.
// The agent's id picks one of 3 hair shapes, 3 hair colours and 3 skin tones; nothing else of the agent reaches the
// art. A sub-agent's worker is the same art, smaller ({small: true}). createAvatar draws the head alone, in one SVG,
// for the right column's and the lists' small round pictures.
"use strict";

const SVG = "http://www.w3.org/2000/svg";
const EYE = "#2a1c16";
const LIP = "#8a3f30";
const HOOD = "#0a1020"; // the hoodie's outline
const PHONES = "#1b2550";
const NEON = "#4f8dfd";
const SHINE = "#ffffff";

// The parts, back to front. Their names are stable: other art can replace a part later.
export const PARTS = ["body", "head", "face", "phones", "blink", "sweat", "arm-l", "arm-r", "arm-up", "arm-thumb",
                      "sparkle"];

const sleeve = (d) => [
  ["path", { d, stroke: HOOD, "stroke-width": "10", fill: "none", "stroke-linecap": "round" }],
  ["path", { d, stroke: "url(#mc-hoodie)", "stroke-width": "9", fill: "none", "stroke-linecap": "round" }],
];
const line = (d, stroke, width, extra = {}) => ["path", { d, stroke, "stroke-width": width, fill: "none",
                                                          "stroke-linecap": "round", ...extra }];

// Each shape is [tag, attributes, children?]. Shapes in the skin's colour carry the class "skin", the hair "hair"
// (CSS fills them from the worker's data-skin and data-colour); the shirt carries "shirt" (CSS fills it with var(--c)).
const ART = {
  body: [
    ["path", { d: "M12 88 C10 71 18 60 40 58 C62 60 70 71 68 88 Z", fill: "url(#mc-hoodie)", stroke: HOOD,
               "stroke-width": "0.8" }],
    ["path", { d: "M25 59 C28 52 52 52 55 59 C50 64 30 64 25 59 Z", fill: "#1a2446" }], // the hood, behind the neck
    ["path", { class: "shirt", d: "M34.5 59 L40 71 L45.5 59 Z" }],
    line("M36.5 63 L35.5 73", "#c9d3f0", "1.2"), // the drawstrings
    line("M43.5 63 L44.5 73", "#c9d3f0", "1.2"),
    line("M27 81 Q40 77 53 81", "#2a3560", "1"), // the pocket
    ["rect", { class: "skin", x: "35", y: "50", width: "10", height: "9", rx: "4" }],
  ],
  head: [
    ["circle", { class: "skin", cx: "15.5", cy: "37", r: "5" }],
    ["circle", { class: "skin", cx: "64.5", cy: "37", r: "5" }],
    ["ellipse", { class: "skin", cx: "40", cy: "33", rx: "25", ry: "23.5" }],
  ],
  face: [
    ["ellipse", { cx: "25", cy: "44", rx: "5.5", ry: "3.2", fill: "url(#mc-cheek)" }],
    ["ellipse", { cx: "55", cy: "44", rx: "5.5", ry: "3.2", fill: "url(#mc-cheek)" }],
    line("M25 25.5 q5 -2.5 9 0", "#2a201b", "1.8"),
    line("M46 25.5 q4 -2.5 9 0", "#2a201b", "1.8"),
    ["g", { class: "eyes-open" }, [
      ["ellipse", { cx: "30", cy: "35", rx: "4.6", ry: "5.8", fill: EYE }],
      ["ellipse", { cx: "50", cy: "35", rx: "4.6", ry: "5.8", fill: EYE }],
      ["ellipse", { cx: "30", cy: "37", rx: "3.2", ry: "3.4", fill: "#6b4a2e", opacity: "0.6" }],
      ["ellipse", { cx: "50", cy: "37", rx: "3.2", ry: "3.4", fill: "#6b4a2e", opacity: "0.6" }],
      ["circle", { cx: "28.4", cy: "32.6", r: "1.8", fill: "#ffffff" }],
      ["circle", { cx: "48.4", cy: "32.6", r: "1.8", fill: "#ffffff" }],
      ["circle", { cx: "31.4", cy: "37.6", r: "0.8", fill: "#ffffff", opacity: "0.85" }],
      ["circle", { cx: "51.4", cy: "37.6", r: "0.8", fill: "#ffffff", opacity: "0.85" }],
    ]],
    ["g", { class: "eyes-happy" }, [line("M26 36 q4 -5 8 0 M46 36 q4 -5 8 0", EYE, "2")]],
    ["g", { class: "eyes-shut" }, [line("M26 36 q4 2.5 8 0 M46 36 q4 2.5 8 0", EYE, "1.8")]],
    line("M36.5 46 q3.5 3.2 7 0", LIP, "1.6", { class: "mouth-smile" }),
    ["ellipse", { class: "mouth-o", cx: "40", cy: "47", rx: "2.4", ry: "2", fill: LIP }],
    line("M36.5 48 q3.5 -3 7 0", LIP, "1.6", { class: "mouth-sad" }),
  ],
  phones: [ // the headphones: a band over the hair, two ear cups with a glowing light
    line("M13 35 C12 9 68 9 67 35", PHONES, "4"),
    line("M15 30 C16 12 64 12 65 30", NEON, "1", { opacity: "0.8" }),
    ["ellipse", { cx: "13.5", cy: "38", rx: "4.6", ry: "7", fill: PHONES, stroke: NEON, "stroke-width": "1.2" }],
    ["ellipse", { cx: "66.5", cy: "38", rx: "4.6", ry: "7", fill: PHONES, stroke: NEON, "stroke-width": "1.2" }],
    ["circle", { cx: "13.5", cy: "38", r: "1.6", fill: "#8fc4ff" }],
    ["circle", { cx: "66.5", cy: "38", r: "1.6", fill: "#8fc4ff" }],
  ],
  blink: [
    ["ellipse", { class: "skin", cx: "30", cy: "35", rx: "5.2", ry: "6.4" }],
    ["ellipse", { class: "skin", cx: "50", cy: "35", rx: "5.2", ry: "6.4" }],
    line("M26 36 q4 2.5 8 0 M46 36 q4 2.5 8 0", EYE, "1.8"),
  ],
  sweat: [
    ["path", { d: "M61 17 C59 20.5 58 22.5 58 24 a3 3 0 0 0 6 0 C64 22.5 63 20.5 61 17 Z", fill: "#9bd8ff",
               stroke: "#5aa9e0", "stroke-width": "0.6" }],
  ],
  "arm-l": [...sleeve("M18 66 C10 72 10 79 16 83"), ["circle", { class: "skin", cx: "18", cy: "84", r: "4.4" }]],
  "arm-r": [...sleeve("M62 66 C70 72 70 79 64 83"), ["circle", { class: "skin", cx: "62", cy: "84", r: "4.4" }]],
  "arm-up": [
    ...sleeve("M62 66 C70 58 72 46 70 36"),
    ["ellipse", { class: "skin", cx: "70", cy: "31", rx: "5", ry: "6" }],
    ["rect", { class: "skin", x: "65.4", y: "21.9", width: "2.2", height: "6.2", rx: "1.1" }],
    ["rect", { class: "skin", x: "67.9", y: "19.9", width: "2.2", height: "7.2", rx: "1.1" }],
    ["rect", { class: "skin", x: "70.4", y: "19.9", width: "2.2", height: "7.2", rx: "1.1" }],
    ["rect", { class: "skin", x: "72.9", y: "22.4", width: "2.2", height: "5.7", rx: "1.1" }],
  ],
  "arm-thumb": [
    ...sleeve("M62 66 C74 72 72 80 64 74"),
    ["rect", { class: "skin", x: "55", y: "62", width: "11", height: "10", rx: "4", stroke: "#000000",
               "stroke-opacity": "0.15", "stroke-width": "0.6" }],
    ["rect", { class: "skin", x: "57.5", y: "52", width: "4.6", height: "12", rx: "2.3", stroke: "#000000",
               "stroke-opacity": "0.15", "stroke-width": "0.6" }],
  ],
  sparkle: [
    ["path", { d: "M69 40 L70.6 44.4 L75 46 L70.6 47.6 L69 52 L67.4 47.6 L63 46 L67.4 44.4 Z", fill: "#fff6c2",
               stroke: "#ffd75a", "stroke-width": "0.8" }],
  ],
};

const HAIR = [ // three shapes, in the hair colour CSS gives (data-colour): over the head, under the face and the phones
  [ // 0: a swept quiff
    ["path", { class: "hair", d: "M15 37 C11 15 25 3 42 3 C58 3 70 13 66 33 C63 25 60 21 55 19 C46 22 33 22 24 17 "
                                 + "C20 22 17 29 15 37 Z" }],
    ["path", { class: "hair", d: "M24 17 C30 3 52 -3 66 9 C58 7 47 9 40 18 Z" }],
    line("M30 11 C38 5 50 4 58 8", SHINE, "1.6", { opacity: "0.3" }),
  ],
  [ // 1: a side part with a fringe
    ["path", { class: "hair", d: "M15 37 C12 16 25 5 41 5 C57 5 69 15 65 35 C63 28 61 24 58 22 C55 16 47 12 40 12 "
                                 + "C33 12 26 15 22 21 C19 25 17 30 15 37 Z" }],
    ["path", { class: "hair", d: "M26 14 C34 8 49 9 58 16 C61 19 62 22 61 25 C56 21 49 19 42 20 C36 20.5 30 20 25 "
                                 + "18 Z" }],
    line("M31 6.5 C29.5 9 28.5 11.5 28 14", "#000000", "1.2", { opacity: "0.35" }),
    line("M38 9 C45 7.5 52 9 57 13", SHINE, "1.5", { opacity: "0.28" }),
  ],
  [ // 2: a messy crop
    ["path", { class: "hair", d: "M16 34 C13 15 26 5 40 5 C55 5 67 15 64 34 C62 27 60 22 57 19 L54 24 L50 17 L45 23 "
                                 + "L40 16 L35 23 L30 17 L26 24 L23 19 C20 23 17 28 16 34 Z" }],
    ["path", { class: "hair", d: "M36 6 C38 1 44 0 48 2 C44 3 41 5 40 8 Z" }],
    line("M27 11 C34 8.5 46 8.5 53 11", SHINE, "1.4", { opacity: "0.3" }),
  ],
];

const stops = (list) => list.map(([offset, color, opacity = "1"]) =>
  ["stop", { offset, "stop-color": color, "stop-opacity": opacity }]);
const GRADIENTS = [
  ["radialGradient", { id: "mc-skin-0", cx: "38%", cy: "32%", r: "75%" },
   stops([["0", "#ffe9db"], ["0.65", "#f7cdb3"], ["1", "#e2a587"]])], // light
  ["radialGradient", { id: "mc-skin-1", cx: "38%", cy: "32%", r: "75%" },
   stops([["0", "#f6d2ae"], ["0.65", "#dfab80"], ["1", "#bb8158"]])], // medium
  ["radialGradient", { id: "mc-skin-2", cx: "38%", cy: "32%", r: "75%" },
   stops([["0", "#b98463"], ["0.65", "#8f5e3f"], ["1", "#6b412a"]])], // deep
  ["radialGradient", { id: "mc-hair-0", cx: "30%", cy: "20%", r: "90%" },
   stops([["0", "#5a4636"], ["0.45", "#2b211b"], ["1", "#120d0b"]])], // near black
  ["radialGradient", { id: "mc-hair-1", cx: "30%", cy: "20%", r: "90%" },
   stops([["0", "#a0714a"], ["0.45", "#6b4528"], ["1", "#3d2616"]])], // brown
  ["radialGradient", { id: "mc-hair-2", cx: "30%", cy: "20%", r: "90%" },
   stops([["0", "#fff0a8"], ["0.45", "#f2c75c"], ["1", "#c58f2c"]])], // blond
  ["linearGradient", { id: "mc-hoodie", x1: "0", y1: "0", x2: "0.3", y2: "1" },
   stops([["0", "#26315a"], ["1", "#121a36"]])],
  ["radialGradient", { id: "mc-cheek" }, stops([["0", "#ff8a80", "0.6"], ["1", "#ff8a80", "0"]])],
];

function shape(doc, [tag, attributes, children = []]) {
  const node = doc.createElementNS(SVG, tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
  for (const child of children) node.append(shape(doc, child));
  return node;
}

// FNV-1a (32 bits) over the id's UTF-16 code units: the same id always looks the same.
export function variantOf(id) {
  let hash = 0x811c9dc5;
  const text = String(id);
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return { hair: hash % 3, skin: Math.floor(hash / 3) % 3, colour: Math.floor(hash / 9) % 3 };
}

// The page's shared gradients, in one <svg>: url(#mc-…) reaches every worker's SVG. It is 0 × 0 and absolutely placed,
// never display: none or hidden, because the gradients of an undisplayed SVG don't paint. Safe to call more than once.
export function ensureDefs(doc = document) {
  if (doc.getElementById("mc-defs")) return;
  const svg = doc.createElementNS(SVG, "svg");
  svg.id = "mc-defs";
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("width", "0");
  svg.setAttribute("height", "0");
  svg.style.position = "absolute";
  const defs = doc.createElementNS(SVG, "defs");
  for (const gradient of GRADIENTS) defs.append(shape(doc, gradient));
  svg.append(defs);
  doc.body.append(svg);
}

function mark(node, { hair, skin, colour }) {
  node.dataset.hair = String(hair);
  node.dataset.skin = String(skin);
  node.dataset.colour = String(colour);
}

export function createWorker(id, { small = false } = {}) {
  const variant = variantOf(id);
  const worker = document.createElement("div");
  worker.className = small ? "worker small" : "worker";
  worker.setAttribute("aria-hidden", "true");
  mark(worker, variant);
  for (const name of PARTS) {
    const part = document.createElement("div");
    part.className = `part ${name}`;
    const svg = document.createElementNS(SVG, "svg");
    svg.setAttribute("viewBox", "0 0 80 88");
    for (const item of name === "head" ? [...ART.head, ...HAIR[variant.hair]] : ART[name]) {
      svg.append(shape(document, item));
    }
    part.append(svg);
    worker.append(part);
  }
  return worker;
}

export function createAvatar(id) { // the head alone, in one SVG: a small round picture of the agent
  const variant = variantOf(id);
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", "6 2 68 62");
  svg.setAttribute("class", "avatar-art");
  svg.setAttribute("aria-hidden", "true");
  mark(svg, variant);
  for (const item of [...ART.head, ...HAIR[variant.hair], ...ART.face, ...ART.phones]) {
    svg.append(shape(document, item));
  }
  return svg;
}
