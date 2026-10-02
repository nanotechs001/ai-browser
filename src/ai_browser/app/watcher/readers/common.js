// Shared by every site reader, a content script in a page the user watches. It asks the watcher's worker what to
// watch, reads the page whenever it changes, and reports only what it hasn't reported from this page before. It never
// clicks a send button: the one thing it ever types is the reply the user approved, into the reply box.
"use strict";
(() => {
  if (globalThis.AIB_WATCH) return;
  let reader = null;
  let config = null;
  let observer = null;
  let interval = null;
  let debounce = null;
  let unknownSince = null;
  let lastStatus = null;
  let first = true;
  let generation = 0;
  const reported = new Set();
  const replied = new Set();
  const typed = new WeakMap(); // a reply box -> what the watcher typed there last
  // Times that change on their own ("5 minutes ago", "Yesterday", 10:02): an item's id leaves them out.
  const CHANGING = new RegExp(String.raw`\b(?:just now|now|today|yesterday|ago|\d+\s*(?:s|secs?|seconds?|m|mins?|minutes?|`
    + String.raw`h|hrs?|hours?|d|days?|w|wks?|weeks?|mo|months?|y|yrs?|years?)\b(?:\s+ago)?)|\b\d{1,2}:\d{2}(?:\s*[ap]\.?m\.?)?`, "gi");

  function text(node) {
    return node ? (node.innerText || node.textContent || "").trim() : "";
  }

  function hash(value) { // a short, stable id for a piece of text (cyrb53)
    let h1 = 0xdeadbeef;
    let h2 = 0x41c6ce57;
    for (let i = 0; i < value.length; i += 1) {
      const code = value.charCodeAt(i);
      h1 = Math.imul(h1 ^ code, 2654435761);
      h2 = Math.imul(h2 ^ code, 1597334677);
    }
    h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
    h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
    return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(36);
  }

  function stableText(node) { // the item's words without its times, so its id stays the same as the minutes pass
    if (!node) return "";
    const parts = [];
    const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
    for (let part = walker.nextNode(); part; part = walker.nextNode()) {
      if (!part.parentElement?.closest("time, [datetime], relative-time")) parts.push(part.nodeValue);
    }
    return parts.join(" ").replace(CHANGING, " ").replace(/\s+/g, " ").trim();
  }

  function ownEmail() { // the signed-in address, as the site shows it in its tab title (in any language)
    const found = /[\w.+-]+@[\w-]+(?:\.[\w-]+)+/.exec(document.title);
    return found ? found[0].toLowerCase() : "";
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function waitFor(find, ms) {
    const end = Date.now() + ms;
    for (;;) {
      const found = find();
      if (found || Date.now() > end) return found || null;
      await sleep(100);
    }
  }

  function boxText(box) {
    return (box.isContentEditable ? box.innerText : box.value).replace(/\s+/g, " ").trim();
  }

  // As the user would type it: focus, caret at the end, insert. The same text again changes nothing, and when the box
  // still holds only what the watcher typed before (a newer draft approved), the new text replaces it.
  function typeInto(box, value) {
    const now = boxText(box);
    if (now === value.replace(/\s+/g, " ").trim()) return;
    const replace = Boolean(now) && typed.get(box) === now;
    box.focus();
    const editable = box.isContentEditable;
    if (editable) {
      const range = document.createRange();
      range.selectNodeContents(box);
      if (!replace) range.collapse(false);
      const selection = getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
    } else if (replace) {
      box.select();
    } else {
      box.selectionStart = box.selectionEnd = box.value.length;
    }
    const before = editable ? box.innerText : box.value;
    if (!document.execCommand("insertText", false, value) || (editable ? box.innerText : box.value) === before) {
      if (editable) {
        if (replace) box.replaceChildren();
        box.append(document.createTextNode(value));
      } else {
        box.value = replace ? value : box.value + value;
      }
      box.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
    }
    typed.set(box, boxText(box));
  }

  function send(message) {
    try {
      chrome.runtime.sendMessage({ ...message, site: config.site }).catch(() => {});
    } catch { // the watcher was reloaded or removed: this copy of the reader is finished
      stop();
      if (globalThis.AIB_WATCH === api) delete globalThis.AIB_WATCH;
    }
  }

  function status(ok, note, elsewhere = false) {
    const key = `${ok}|${note}|${elsewhere}`;
    if (key !== lastStatus) {
      lastStatus = key;
      send({ type: "status", ok, note, elsewhere });
    }
  }

  function clean(item) {
    const out = {};
    for (const key of ["id", "from", "subject", "snippet", "url", "time"]) {
      out[key] = typeof item[key] === "string" ? item[key].slice(0, key === "snippet" ? 500 : 2000) : "";
    }
    return out;
  }

  function scan() {
    if (!reader || !config || config.paused) return;
    let known = false;
    try {
      known = reader.check(config);
    } catch {
      known = false;
    }
    if (known === "elsewhere") { // a page of the site this reader doesn't read (Spam, Settings, a board): no alarm
      unknownSince = null;
      status(false, reader.elsewhere || "open the page to watch in this tab", true);
      return;
    }
    if (!known) {
      unknownSince = unknownSince ?? Date.now();
      if (Date.now() - unknownSince >= (config.reader_timeout || 120) * 1000) status(false, "reader needs an update");
      return;
    }
    unknownSince = null;
    status(true, "");
    let items = [];
    try {
      items = reader.items(config) || [];
    } catch {
      items = [];
    }
    const fresh = [];
    for (const item of items) {
      if (!item || typeof item.id !== "string" || !item.id) continue;
      if (item.from_me) { // the user has answered there: whatever the Brain listed for it is done
        if (!replied.has(item.id)) {
          replied.add(item.id);
          send({ type: "replied", id: item.id });
        }
      } else if (!reported.has(item.id) && item.unread !== false) {
        reported.add(item.id);
        fresh.push(clean(item));
      }
    }
    const baseline = first && config.baseline; // an added site: what is there already is where watching starts
    first = false;
    if (fresh.length || baseline) {
      send({ type: "items", items: fresh, ...(baseline ? { baseline: true, selector: config.selector || "" } : {}) });
    }
  }

  async function begin() {
    const mine = ++generation;
    let answer = null;
    try {
      answer = await chrome.runtime.sendMessage({ type: "reader_config", kind: reader.kind });
    } catch {
      answer = null;
    }
    if (mine !== generation) return;
    if (!answer || !answer.site) {
      setTimeout(() => { if (mine === generation) begin(); }, 5000);
      return;
    }
    config = answer;
    if (config.paused) return;
    try {
      await reader.init?.(config);
    } catch { /* a reader without its saved state still reads */ }
    if (mine !== generation) return;
    observer = new MutationObserver(() => {
      clearTimeout(debounce);
      debounce = setTimeout(scan, 500);
    });
    observer.observe(document.documentElement, { subtree: true, childList: true, characterData: true,
                                                 attributes: true, attributeFilter: ["class"] });
    interval = setInterval(scan, 2000); // also catches the unread count in the tab title
    scan();
  }

  function stop() {
    generation += 1;
    observer?.disconnect();
    observer = null;
    clearInterval(interval);
    clearTimeout(debounce);
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!reader || sender.id !== chrome.runtime.id || !message) return false;
    if (message.type === "thread") {
      let value = "";
      try {
        value = reader.thread(config) || "";
      } catch {
        value = "";
      }
      sendResponse({ text: value.slice(0, 20000) });
    } else if (message.type === "fill") {
      Promise.resolve().then(() => reader.fill(String(message.text || ""), config)).then(
        (result) => sendResponse(result || { ok: false, reason: "the reader gave no answer" }),
        (error) => sendResponse({ ok: false, reason: String(error?.message || error) }));
      return true;
    } else if (message.type === "pause") {
      stop();
      if (config) config.paused = true;
    } else if (message.type === "rescan") {
      stop();
      reported.clear();
      replied.clear();
      lastStatus = unknownSince = null;
      first = true;
      begin();
    }
    return false;
  });

  const api = {
    start(siteReader) {
      if (reader) return;
      reader = siteReader;
      begin();
    },
    text, hash, stableText, ownEmail, typeInto, waitFor, sleep,
  };
  globalThis.AIB_WATCH = api;
})();
