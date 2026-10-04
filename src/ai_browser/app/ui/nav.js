// Tabs, never windows. AI Browser's pages are tabs of its one window (app.js, the tab menu at /app): a page asks the
// window for a tab with a message to our own origin, and never opens a window of its own. A link to a website goes to
// the user's own browser through the app (open_url), so the window never leaves its own pages. Only AI Home, Mission
// Control and Settings import this file; the files Brave's watcher shares never do.
"use strict";

const PAGES = ["/home", "/mission", "/settings", "/setup"]; // the pages the window shows as tabs

function windowPage() { // the tab menu this page is shown in; null for a page opened by itself (tests, by hand)
  return window.parent !== window ? window.parent : null;
}

// The tab of one of our pages ("/mission", "/settings", "/home", "/setup#brave"): shown at once, loaded the first
// time it is asked for; the setup steps open as a closable tab. A page opened by itself goes there itself instead.
export function openTab(path) {
  const menu = windowPage();
  if (menu) menu.postMessage({ type: "tab", path }, location.origin);
  else location.assign(path);
}

// An engine's live view (a bot check in QA's sandbox) as a closable tab: one per agent, so a second Show me brings the
// first forward. A page opened by itself has no window to show it in.
export function openLive(url, agent, label) {
  windowPage()?.postMessage({ type: "live", url, agent, label }, location.origin);
}

function ourPage(url) { // the page and its #section, if the window shows it as a tab; else null
  if (url.origin !== location.origin || !PAGES.includes(url.pathname)) return null;
  return url.pathname + url.search + url.hash;
}

// Every link click on the page (any button, any modifier): a page of ours becomes its tab, a website goes to the
// user's browser, and anything else is dropped. The click itself never navigates and never opens a window.
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
    if (page) openTab(page);
    else if ((url.protocol === "http:" || url.protocol === "https:") && url.origin !== location.origin) {
      link.send({ type: "open_url", url: url.href });
    }
  };
  for (const type of ["click", "auxclick"]) document.addEventListener(type, follow, true);
}
