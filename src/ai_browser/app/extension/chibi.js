// The workers: one original chibi office worker per agent (a big round head, dark swept hair, thick black glasses,
// rosy cheeks, a light suit and a tie in the agent's colour), sitting behind the station's desk. Each part is an HTML
// layer holding one small SVG built here from a fixed table of shapes: nothing is parsed from strings and there is no
// innerHTML, so the poses (mission.css) move HTML layers only. The agent's id picks one of 3 hair shapes and one of 3
// skin tones; nothing else of the agent reaches the art, and the tie takes its colour from CSS (--c).
"use strict";

const SVG = "http://www.w3.org/2000/svg";
const INK = "#141418"; // the glasses
const BROWN = "#3c2517"; // the eyes
const LIP = "#8a3f30";
const SHADE = "#c4c8d6"; // the suit's outline

// The parts, back to front. Their names are stable: other art can replace a part later.
export const PARTS = ["body", "head", "face", "blink", "sweat", "arm-l", "arm-r", "arm-up", "arm-thumb", "sparkle"];

const sleeve = (d) => [
  ["path", { d, stroke: SHADE, "stroke-width": "9.8", fill: "none", "stroke-linecap": "round" }],
  ["path", { d, stroke: "url(#mc-suit)", "stroke-width": "9", fill: "none", "stroke-linecap": "round" }],
];
const line = (d, stroke, width, extra = {}) => ["path", { d, stroke, "stroke-width": width, fill: "none",
                                                          "stroke-linecap": "round", ...extra }];

// Each shape is [tag, attributes, children?]. Shapes in the skin's colour carry the class "skin" (CSS fills them from
// the worker's data-skin); the tie carries the class "tie" (CSS fills it with var(--c)).
const ART = {
  body: [
    ["path", { d: "M14 86 C12 70 18 60 40 58 C62 60 68 70 66 86 Z", fill: "url(#mc-suit)", stroke: SHADE,
               "stroke-width": "0.8" }],
    ["path", { d: "M34 58 L40 72 L46 58 Z", fill: "#ffffff" }],
    ["path", { d: "M34 58 L39 74 L31 69 Z", fill: "#e6e8f1", stroke: "#cdd1de", "stroke-width": "0.5" }],
    ["path", { d: "M46 58 L41 74 L49 69 Z", fill: "#e6e8f1", stroke: "#cdd1de", "stroke-width": "0.5" }],
    ["path", { class: "tie", d: "M38.2 60 L41.8 60 L43 63 L41.6 76 L40 78.5 L38.4 76 L37 63 Z" }],
    ["path", { class: "tie", d: "M37.6 58.4 h4.8 l-0.9 3.2 h-3 z" }],
    ["path", { d: "M37.6 58.4 h4.8 l-0.9 3.2 h-3 z", fill: "#000000", "fill-opacity": "0.2" }],
    ["rect", { class: "skin", x: "35", y: "50", width: "10", height: "9", rx: "4" }],
  ],
  head: [
    ["circle", { class: "skin", cx: "15.5", cy: "36", r: "5.5" }],
    ["circle", { class: "skin", cx: "64.5", cy: "36", r: "5.5" }],
    ["ellipse", { class: "skin", cx: "40", cy: "33", rx: "25", ry: "23.5" }],
  ],
  face: [
    ["ellipse", { cx: "25", cy: "44", rx: "5.5", ry: "3.2", fill: "url(#mc-cheek)" }],
    ["ellipse", { cx: "55", cy: "44", rx: "5.5", ry: "3.2", fill: "url(#mc-cheek)" }],
    line("M24 25.5 q5 -3 10 0", "#2a201b", "2.2"),
    line("M46 25.5 q5 -3 10 0", "#2a201b", "2.2"),
    ["g", { class: "eyes-open" }, [
      ["ellipse", { cx: "30", cy: "34", rx: "4", ry: "4.8", fill: BROWN }],
      ["ellipse", { cx: "50", cy: "34", rx: "4", ry: "4.8", fill: BROWN }],
      ["circle", { cx: "28.8", cy: "32.2", r: "1.5", fill: "#ffffff" }],
      ["circle", { cx: "48.8", cy: "32.2", r: "1.5", fill: "#ffffff" }],
      ["circle", { cx: "31.2", cy: "36.2", r: "0.7", fill: "#ffffff", opacity: "0.8" }],
      ["circle", { cx: "51.2", cy: "36.2", r: "0.7", fill: "#ffffff", opacity: "0.8" }],
    ]],
    ["g", { class: "eyes-happy" }, [line("M26 35 q4 -5 8 0 M46 35 q4 -5 8 0", BROWN, "2")]],
    ["g", { class: "eyes-shut" }, [line("M26 35 q4 2.5 8 0 M46 35 q4 2.5 8 0", BROWN, "1.8")]],
    ["rect", { x: "21.5", y: "27.5", width: "17", height: "13.5", rx: "3.5", fill: "url(#mc-lens)", stroke: INK,
               "stroke-width": "2.4" }],
    ["rect", { x: "41.5", y: "27.5", width: "17", height: "13.5", rx: "3.5", fill: "url(#mc-lens)", stroke: INK,
               "stroke-width": "2.4" }],
    ["path", { d: "M38.5 32 h3", stroke: INK, "stroke-width": "2" }],
    ["path", { d: "M21.5 31.5 L15.5 33 M58.5 31.5 L64.5 33", stroke: INK, "stroke-width": "1.8" }],
    line("M24.5 30.5 l3 -1.4 M44.5 30.5 l3 -1.4", "#ffffff", "1.1", { opacity: "0.7" }),
    line("M36 46 q4 3.6 8 0", LIP, "1.7", { class: "mouth-smile" }),
    ["ellipse", { class: "mouth-o", cx: "40", cy: "47", rx: "2.6", ry: "2.2", fill: LIP }],
    line("M36.5 48 q3.5 -3 7 0", LIP, "1.7", { class: "mouth-sad" }),
  ],
  blink: [
    ["ellipse", { class: "skin", cx: "30", cy: "34", rx: "4.6", ry: "5.4" }],
    ["ellipse", { class: "skin", cx: "50", cy: "34", rx: "4.6", ry: "5.4" }],
    line("M26 35 q4 2.5 8 0 M46 35 q4 2.5 8 0", BROWN, "1.8"),
  ],
  sweat: [
    ["path", { d: "M61 17 C59 20.5 58 22.5 58 24 a3 3 0 0 0 6 0 C64 22.5 63 20.5 61 17 Z", fill: "#9bd8ff",
               stroke: "#5aa9e0", "stroke-width": "0.6" }],
  ],
  "arm-l": [...sleeve("M18 64 C10 70 10 78 16 82"), ["circle", { class: "skin", cx: "18", cy: "83", r: "4.4" }]],
  "arm-r": [...sleeve("M62 64 C70 70 70 78 64 82"), ["circle", { class: "skin", cx: "62", cy: "83", r: "4.4" }]],
  "arm-up": [
    ...sleeve("M62 64 C70 58 72 46 70 36"),
    ["ellipse", { class: "skin", cx: "70", cy: "31", rx: "5", ry: "6" }],
    ["rect", { class: "skin", x: "65.4", y: "21.9", width: "2.2", height: "6.2", rx: "1.1" }],
    ["rect", { class: "skin", x: "67.9", y: "19.9", width: "2.2", height: "7.2", rx: "1.1" }],
    ["rect", { class: "skin", x: "70.4", y: "19.9", width: "2.2", height: "7.2", rx: "1.1" }],
    ["rect", { class: "skin", x: "72.9", y: "22.4", width: "2.2", height: "5.7", rx: "1.1" }],
  ],
  "arm-thumb": [
    ...sleeve("M62 64 C74 70 72 80 64 74"),
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

const HAIR_HIGHLIGHT = "#8a6c58";
const HAIR = [ // always dark brown to near black; drawn over the head, under the face's brows and glasses
  [ // 0: a swept quiff
    ["path", { d: "M15 37 C11 15 25 3 42 3 C58 3 70 13 66 33 C63 25 60 21 55 19 C46 22 33 22 24 17 C20 22 17 29 "
                  + "15 37 Z", fill: "url(#mc-hair)" }],
    ["path", { d: "M24 17 C30 3 52 -3 66 9 C58 7 47 9 40 18 Z", fill: "url(#mc-hair)" }],
    line("M30 11 C38 5 50 4 58 8", HAIR_HIGHLIGHT, "1.6", { opacity: "0.7" }),
  ],
  [ // 1: a side part with a fringe
    ["path", { d: "M15 37 C12 16 25 5 41 5 C57 5 69 15 65 35 C63 28 61 24 58 22 C55 16 47 12 40 12 C33 12 26 15 22 21 "
                  + "C19 25 17 30 15 37 Z", fill: "url(#mc-hair)" }],
    ["path", { d: "M26 14 C34 8 49 9 58 16 C61 19 62 22 61 25 C56 21 49 19 42 20 C36 20.5 30 20 25 18 Z",
               fill: "url(#mc-hair)" }],
    line("M31 6.5 C29.5 9 28.5 11.5 28 14", "#120d0b", "1.2"),
    line("M38 9 C45 7.5 52 9 57 13", HAIR_HIGHLIGHT, "1.5", { opacity: "0.6" }),
  ],
  [ // 2: a short crop
    ["path", { d: "M16 33 C14 16 26 6.5 40 6.5 C54 6.5 66 16 64 33 C63 27 61.5 23 59 20 C52 17.5 46 17 40 17 "
                  + "C34 17 28 17.5 21 20 C18.5 23 17 27 16 33 Z", fill: "url(#mc-hair)" }],
    line("M27 11 C34 8.5 46 8.5 53 11", HAIR_HIGHLIGHT, "1.4", { opacity: "0.55" }),
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
  ["radialGradient", { id: "mc-hair", cx: "30%", cy: "20%", r: "90%" },
   stops([["0", "#6a5040"], ["0.45", "#33271f"], ["1", "#17110e"]])],
  ["linearGradient", { id: "mc-suit", x1: "0", y1: "0", x2: "0.3", y2: "1" },
   stops([["0", "#ffffff"], ["1", "#d6d9e4"]])],
  ["radialGradient", { id: "mc-cheek" }, stops([["0", "#ff8a80", "0.6"], ["1", "#ff8a80", "0"]])],
  ["radialGradient", { id: "mc-lens", cx: "35%", cy: "30%", r: "80%" },
   stops([["0", "#ffffff", "0.35"], ["1", "#ffffff", "0"]])],
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
  return { hair: hash % 3, skin: Math.floor(hash / 3) % 3 };
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

export function createWorker(id) {
  const { hair, skin } = variantOf(id);
  const worker = document.createElement("div");
  worker.className = "worker";
  worker.setAttribute("aria-hidden", "true");
  worker.dataset.hair = String(hair);
  worker.dataset.skin = String(skin);
  for (const name of PARTS) {
    const part = document.createElement("div");
    part.className = `part ${name}`;
    const svg = document.createElementNS(SVG, "svg");
    svg.setAttribute("viewBox", "0 0 80 88");
    for (const item of name === "head" ? [...ART.head, ...HAIR[hair]] : ART[name]) svg.append(shape(document, item));
    part.append(svg);
    worker.append(part);
  }
  return worker;
}
