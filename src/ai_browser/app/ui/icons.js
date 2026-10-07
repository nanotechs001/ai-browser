// Mission Control's line icons (the new look): the menu's, the switch's, the composer's and each badge's. Each one is a
// path from the fixed table below, drawn into an <svg> built with createElementNS: nothing is parsed. CSS gives the
// line its colour (currentColor).
"use strict";

const SVG = "http://www.w3.org/2000/svg";
const PATHS = {
  home: "M3 10.5 12 3l9 7.5M5 9v11h5v-6h4v6h5V9",
  missions: "M7 4a3 3 0 1 1 0 6 3 3 0 0 1 0-6zM17 4a3 3 0 1 1 0 6 3 3 0 0 1 0-6zM7 14a3 3 0 1 1 0 6 3 3 0 0 1 "
    + "0-6zM17 14a3 3 0 1 1 0 6 3 3 0 0 1 0-6zM10 7h4M10 17h4M7 10v4M17 10v4",
  template: "M6 3h8l5 5v13H6zM14 3v5h5M9 13h7M9 17h7",
  book: "M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H6.5A1.5 1.5 0 0 0 5 19.5zM5 19.5A1.5 1.5 0 0 0 6.5 21H19",
  cube: "M12 3 20 7.5v9L12 21l-8-4.5v-9zM4 7.5l8 4.5 8-4.5M12 12v9",
  clock: "M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18zM12 7v5l3.5 2",
  folder: "M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2h8.5A1.5 1.5 0 0 1 21 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5z",
  plus: "M12 5v14M5 12h14",
  sparkle: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 15l.7 1.8 1.8.7-1.8.7L19 20l-.7-1.8-1.8-.7 "
    + "1.8-.7z",
  clip: "M20.5 11.5 12 20a5 5 0 0 1-7-7l8.5-8.5a3.5 3.5 0 0 1 5 5L10 18a2 2 0 0 1-3-3l7.5-7.5",
  globe: "M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18",
  play: "M8 5.5v13l10.5-6.5z",
  flow: "M5 5h4v4H5zM15 5h4v4h-4zM10 15h4v4h-4zM7 9v1a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V9M12 12v3",
  list: "M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01",
  calendar: "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
  check: "M5 12.5 10 17 19 7",
  more: "M6 12h.01M12 12h.01M18 12h.01",
  close: "M6 6l12 12M18 6 6 18",
  terminal: "M4 5h16v14H4zM7.5 9.5 10 12l-2.5 2.5M12 15h4.5",
  pencil: "M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4",
  doc: "M6 3h8l5 5v13H6zM14 3v5h5",
  eye: "M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12zM12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6z",
  search: "M11 4a7 7 0 1 1 0 14 7 7 0 0 1 0-14zM20 20l-4-4",
  download: "M12 4v11M7.5 10.5 12 15l4.5-4.5M5 20h14",
  browser: "M3 5h18v14H3zM3 9h18M6 7h.01M8.5 7h.01",
  agents: "M9 6a3 3 0 1 1 0 6 3 3 0 0 1 0-6zM16.5 8a2.5 2.5 0 1 1 0 5M3.5 20c.5-3 3-5 5.5-5s5 2 5.5 5M15.5 15.2c2.4"
    + ".2 4.3 2 4.8 4.8",
  bolt: "M13 2.5 5 13.5h6.5l-1 8 8-11H12z",
  tool: "M14.5 4.5a4.5 4.5 0 0 0-4.3 5.8L4 16.5 7.5 20l6.2-6.2a4.5 4.5 0 0 0 5.8-4.3l-2.6 2.6-2.8-.7-.7-2.8z",
  stop: "M7 7h10v10H7z",
  chat: "M4 5h16v11H9l-5 4z",
  hand: "M7 11V6.5a1.5 1.5 0 0 1 3 0V11M10 10V4.5a1.5 1.5 0 0 1 3 0V10M13 10V5.5a1.5 1.5 0 0 1 3 0V12M16 9.5a1.5 1.5"
    + " 0 0 1 3 0v4.5a7 7 0 0 1-7 7h-1a6 6 0 0 1-5-2.7L3.6 14a1.5 1.5 0 0 1 2.5-1.7L7 13.5",
  left: "M15 6l-6 6 6 6",
  right: "M9 6l6 6-6 6",
  trash: "M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13",
};
const FILLED = new Set(["play", "bolt"]);
export const BADGE_ICONS = { Bash: "terminal", Edit: "pencil", Write: "doc", Read: "eye", "Web Search": "search",
                             "Web Fetch": "download", "Browser Agent": "browser", "Sub-agent": "agents", Skill: "bolt",
                             Tool: "tool", "To-do list": "list" };

export function icon(name, className = "icon") {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", FILLED.has(name) ? `${className} filled` : className);
  const path = document.createElementNS(SVG, "path");
  path.setAttribute("d", PATHS[name] || PATHS.tool);
  svg.append(path);
  return svg;
}
