// The page the user asked about in AI Browser's floating chat, read only on that ask (native-app Decision 4): its
// title, its address and its words. The words are read with textContent only, so the page is never laid out again
// for it. What scripts, styles, templates and noscript blocks hold is left out, and at most `limit` characters are
// kept. It changes nothing in the page, and its answer is plain JSON.
"use strict";
(() => {
  if (globalThis.AIB.page) return;
  const SKIP = "script, style, noscript, template";
  const MOST = 100000; // characters, whatever the engine asks

  globalThis.AIB.page = (limit) => {
    const most = Math.max(0, Math.min(Math.floor(Number(limit) || 0), MOST));
    const words = [];
    let size = 0;
    const root = document.body || document.documentElement;
    if (root) {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode: (node) => (node.parentElement?.closest(SKIP) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
      });
      for (let node = walker.nextNode(); node && size <= most; node = walker.nextNode()) {
        const part = node.textContent.replace(/\s+/g, " ").trim();
        if (part) {
          words.push(part);
          size += part.length + 1;
        }
      }
    }
    const text = words.join(" ");
    return { title: String(document.title || "").slice(0, 300), url: String(location.href).slice(0, 2000),
             text: text.slice(0, most), cut: text.length > most };
  };
})();
