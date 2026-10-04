// Tabs, never windows. AI Browser's pages are tabs of its one window (app.js, the tab menu at /app): a page asks the
// window for a tab with a message to our own origin, and never opens a window of its own. A link to a website goes to
// the user's own browser through the app (open_url), so the window never leaves its own pages. The close-tab key
// closes a tab with a ×, never the window. Only AI Home, Mission Control, Settings and the tab menu import this file;
// the files Brave's watcher shares never do.
"use strict";

const PAGES = ["/home", "/mission", "/settings", "/setup"]; // the pages the window shows as tabs
const MAC = /mac/i.test(navigator.userAgentData?.platform || navigator.platform || "");

function windowPage() { // the tab menu this page is shown in; null for a page opened by itself (tests, by hand)
  return window.parent !== window ? window.parent : null;
}

// The close-tab key: Command-W on a Mac, Ctrl+W elsewhere, with no other modifier. In AI Browser's window it would
// close the whole window, and with it AI Browser and every agent.
export function closeTabKey(event) {
  const command = MAC ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey;
  return command && !event.altKey && !event.shiftKey && String(event.key).toLowerCase() === "w";
}

// In the window, the close-tab key never reaches the browser: the tab menu closes the tab shown if it has a ×, and
// nothing else. A page opened by itself leaves the key to the browser, as any page does.
export function guardCloseKey() {
  const menu = windowPage();
  if (!menu) return;
  document.addEventListener("keydown", (event) => {
    if (!closeTabKey(event)) return;
    event.preventDefault();
    if (!event.repeat) menu.postMessage({ type: "close-tab" }, location.origin);
  }, true);
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
