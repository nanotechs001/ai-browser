// The reader for a site the user added: the part of the page they picked (a CSS selector). Each child of that part
// is an item, known by its own data id or else by its text without times ("5 min ago" changes on its own); the rows
// already there when watching starts are only remembered, not reported.
"use strict";
(() => {
  const { start, text, hash, stableText } = globalThis.AIB_WATCH;

  function idOf(row) {
    const own = row.dataset.id || row.dataset.key || row.dataset.itemId || row.dataset.rowKey;
    return own ? `id:${own}` : stableText(row);
  }

  function picked(config) { // the address path of the page the user picked from
    return String(config.url_match || "").replace(/^[^:]+:\/\/[^/]+/, "").replace(/\*$/, "").replace(/\/$/, "");
  }

  function region(config) {
    try {
      return document.querySelector(config.selector);
    } catch {
      return null;
    }
  }

  start({
    kind: "region",
    elsewhere: "open the page you picked to read it",
    check(config) { // the picked part missing from the picked page is an alarm; another page of the site isn't
      if (region(config)) return true;
      return location.pathname.replace(/\/$/, "") === picked(config) ? false : "elsewhere";
    },
    items(config) {
      return [...(region(config)?.children || [])].map((child) => {
        const value = text(child);
        if (!value) return null;
        return { id: hash(idOf(child)), from: "", subject: value.split("\n")[0].slice(0, 100),
                 snippet: value.slice(0, 500), url: location.href, time: "" };
      }).filter(Boolean);
    },
    thread: (config) => text(region(config)),
    fill: () => ({ ok: false, reason: "no reply box here: copy the draft" }),
  });
})();
