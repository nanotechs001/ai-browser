// Windows of our own. AI Browser's pages open as small app-style windows, never as tabs: a _blank open from an app
// window brings back a normal tabbed window, so this file never uses one. A link to a website goes to the user's own
// browser through the app (open_url), so the window never leaves its own pages. Only AI Home, Mission Control and
// Settings import this file; the files Brave's watcher shares never do.
"use strict";

export const WINDOWS = {
  "/home": ["aib-home", 1440, 960],
  "/mission": ["aib-mission", 1280, 860],
  "/settings": ["aib-settings", 720, 760],
  "/setup": ["aib-setup", 760, 900],
};

// A window of ours by name: opened on the first click, brought forward on the next (the size counts only when it is
// new). It loads `path` when it is new, or when it shows another page of ours than the one asked for.
export function openWindow(path, name, width, height) {
  const opened = window.open("", name, `popup,width=${width},height=${height}`);
  if (!opened) return null; // the popup blocker: only a click opens a window
  try {
    const showing = opened.location.href === "about:blank" ? null : opened.location.pathname + opened.location.hash;
    if (showing !== path) opened.location.replace(path);
  } catch {
    // not a page of ours: leave it as it is
  }
  opened.focus();
  return opened;
}

export function focusHome() {
  return openWindow("/home", ...WINDOWS["/home"]);
}

function ourPage(url) { // "/home", "/mission", "/settings" or "/setup", or null
  if (url.origin !== location.origin) return null;
  return Object.keys(WINDOWS).find((path) => url.pathname === path) || null;
}

// Every link click on the page (any button, any modifier): a page of ours opens in its own window, a website in the
// user's browser, and anything else is dropped. The click itself never navigates.
export function guardLinks(link) {
  const follow = (event) => {
    const anchor = event.target instanceof Element ? event.target.closest("a[href]") : null;
    if (!anchor) return;
    event.preventDefault();
    let url;
    try {
      url = new URL(anchor.getAttribute("href"), location.href);
    } catch {
      return;
    }
    const page = ourPage(url);
    if (page) openWindow(url.pathname + url.search + url.hash, ...WINDOWS[page]);
    else if ((url.protocol === "http:" || url.protocol === "https:") && url.origin !== location.origin) {
      link.send({ type: "open_url", url: url.href });
    }
  };
  for (const type of ["click", "auxclick"]) document.addEventListener(type, follow, true);
}
