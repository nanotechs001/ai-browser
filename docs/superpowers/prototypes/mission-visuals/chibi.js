// Prototype: an ORIGINAL chibi desk worker (big head, swept dark hair, black glasses, light suit, tie in the agent's
// colour), half-body behind the station's desk. Each animated part is its own layer so the plan can compare
// "animate SVG <g>" with "animate HTML wrappers" and "draw to canvas". Not project code.
export const DEFS = `
<radialGradient id="skin" cx="38%" cy="32%" r="75%"><stop offset="0" stop-color="#ffe9db"/><stop offset=".65" stop-color="#f7cdb3"/><stop offset="1" stop-color="#e2a587"/></radialGradient>
<radialGradient id="hair" cx="30%" cy="20%" r="90%"><stop offset="0" stop-color="#6a5040"/><stop offset=".45" stop-color="#33271f"/><stop offset="1" stop-color="#17110e"/></radialGradient>
<linearGradient id="suit" x1="0" y1="0" x2="0.3" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#d6d9e4"/></linearGradient>
<radialGradient id="cheek"><stop offset="0" stop-color="#ff8a80" stop-opacity=".6"/><stop offset="1" stop-color="#ff8a80" stop-opacity="0"/></radialGradient>
<radialGradient id="lens" cx="35%" cy="30%" r="80%"><stop offset="0" stop-color="#ffffff" stop-opacity=".35"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></radialGradient>`;

// layers, back to front; each is [name, svg body]
export const LAYERS = [
  ["body", `
    <path d="M14 86 C12 70 18 60 40 58 C62 60 68 70 66 86 Z" fill="url(#suit)" stroke="#c4c8d6" stroke-width=".8"/>
    <path d="M34 58 L40 72 L46 58 Z" fill="#fff"/>
    <path d="M34 58 L39 74 L31 69 Z" fill="#e6e8f1" stroke="#cdd1de" stroke-width=".5"/>
    <path d="M46 58 L41 74 L49 69 Z" fill="#e6e8f1" stroke="#cdd1de" stroke-width=".5"/>
    <path d="M38.2 60 L41.8 60 L43 63 L41.6 76 L40 78.5 L38.4 76 L37 63 Z" fill="var(--c, #4c8df6)"/>
    <path d="M37.6 58.4 h4.8 l-.9 3.2 h-3 z" fill="var(--c, #4c8df6)" style="filter:brightness(.8)"/>
    <rect x="35" y="50" width="10" height="9" rx="4" fill="#eebd9f"/>`],
  ["head", `
    <circle cx="15.5" cy="36" r="5.5" fill="url(#skin)"/><circle cx="64.5" cy="36" r="5.5" fill="url(#skin)"/>
    <ellipse cx="40" cy="33" rx="25" ry="23.5" fill="url(#skin)"/>
    <path d="M15 37 C11 15 25 3 42 3 C58 3 70 13 66 33 C63 25 60 21 55 19 C46 22 33 22 24 17 C20 22 17 29 15 37 Z" fill="url(#hair)"/>
    <path d="M24 17 C30 3 52 -3 66 9 C58 7 47 9 40 18 Z" fill="url(#hair)"/>
    <path d="M30 11 C38 5 50 4 58 8" stroke="#8a6c58" stroke-width="1.6" fill="none" stroke-linecap="round" opacity=".7"/>`],
  ["face", `
    <ellipse cx="25" cy="44" rx="5.5" ry="3.2" fill="url(#cheek)"/><ellipse cx="55" cy="44" rx="5.5" ry="3.2" fill="url(#cheek)"/>
    <path d="M24 25.5 q5 -3 10 0" stroke="#2a201b" stroke-width="2.2" fill="none" stroke-linecap="round"/>
    <path d="M46 25.5 q5 -3 10 0" stroke="#2a201b" stroke-width="2.2" fill="none" stroke-linecap="round"/>
    <g class="eyes open"><ellipse cx="30" cy="34" rx="4" ry="4.8" fill="#3c2517"/><ellipse cx="50" cy="34" rx="4" ry="4.8" fill="#3c2517"/>
      <circle cx="28.8" cy="32.2" r="1.5" fill="#fff"/><circle cx="48.8" cy="32.2" r="1.5" fill="#fff"/>
      <circle cx="31.2" cy="36.2" r=".7" fill="#fff" opacity=".8"/><circle cx="51.2" cy="36.2" r=".7" fill="#fff" opacity=".8"/></g>
    <g class="eyes happy"><path d="M26 35 q4 -5 8 0 M46 35 q4 -5 8 0" stroke="#3c2517" stroke-width="2" fill="none" stroke-linecap="round"/></g>
    <g class="eyes shut"><path d="M26 35 q4 2.5 8 0 M46 35 q4 2.5 8 0" stroke="#3c2517" stroke-width="1.8" fill="none" stroke-linecap="round"/></g>
    <rect x="21.5" y="27.5" width="17" height="13.5" rx="3.5" fill="url(#lens)" stroke="#141418" stroke-width="2.4"/>
    <rect x="41.5" y="27.5" width="17" height="13.5" rx="3.5" fill="url(#lens)" stroke="#141418" stroke-width="2.4"/>
    <path d="M38.5 32 h3" stroke="#141418" stroke-width="2"/>
    <path d="M21.5 31.5 L15.5 33 M58.5 31.5 L64.5 33" stroke="#141418" stroke-width="1.8"/>
    <path class="mouth smile" d="M36 46 q4 3.6 8 0" stroke="#8a3f30" stroke-width="1.7" fill="none" stroke-linecap="round"/>
    <ellipse class="mouth open" cx="40" cy="47" rx="2.6" ry="2.2" fill="#8a3f30"/>
    <path class="mouth sad" d="M36.5 48 q3.5 -3 7 0" stroke="#8a3f30" stroke-width="1.7" fill="none" stroke-linecap="round"/>`],
  ["arm-l", `
    <path d="M18 64 C10 70 10 78 16 82" stroke="url(#suit)" stroke-width="9" fill="none" stroke-linecap="round"/>
    <circle cx="18" cy="83" r="4.4" fill="url(#skin)"/>`],
  ["arm-r", `
    <path d="M62 64 C70 70 70 78 64 82" stroke="url(#suit)" stroke-width="9" fill="none" stroke-linecap="round"/>
    <circle cx="62" cy="83" r="4.4" fill="url(#skin)"/>`],
  ["arm-up", `
    <path d="M62 64 C70 58 72 46 70 36" stroke="url(#suit)" stroke-width="9" fill="none" stroke-linecap="round"/>
    <ellipse cx="70" cy="31" rx="5" ry="6" fill="url(#skin)"/>
    <path d="M66.5 27 v-4 M69 26 v-5 M71.5 26 v-5 M74 27 v-3.5" stroke="#f2c2a6" stroke-width="2.2" stroke-linecap="round"/>`],
  ["arm-thumb", `
    <path d="M62 64 C74 70 72 80 64 74" stroke="url(#suit)" stroke-width="9" fill="none" stroke-linecap="round" stroke-opacity="1"/>
    <path d="M62 64 C74 70 72 80 64 74" stroke="#c4c8d6" stroke-width="9.8" fill="none" stroke-linecap="round" opacity=".35"/>
    <rect x="55" y="62" width="11" height="10" rx="4" fill="url(#skin)" stroke="#d99a7c" stroke-width=".6"/>
    <rect x="57.5" y="52" width="4.6" height="12" rx="2.3" fill="url(#skin)" stroke="#d99a7c" stroke-width=".6"/>`],
];

export const svgOf = (bodies, id = "") => `<svg viewBox="0 0 80 88" ${id}>${bodies}</svg>`;
