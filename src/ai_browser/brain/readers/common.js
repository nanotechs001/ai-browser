// The Brain's readers, run by AI Browser's engine in an isolated world of a tab in the user's Brave
// (Page.createIsolatedWorld): the page's own scripts can't see or change anything here, and each call returns plain
// JSON. This file comes first: it sets up globalThis.AIB once per world, and the site readers after it add themselves
// to AIB.readers. Nothing here sends a message or clicks a send button: the only things it ever does in a page are
// the two the user asks for (the reply they chose to use, put in the reply box; the picker's outline while they pick).
"use strict";
(() => {
  if (globalThis.AIB?.key === "{{KEY}}") return; // this world has this version already
  const CHANGING = new RegExp(String.raw`\b(?:just now|now|today|yesterday|ago|\d+\s*(?:s|secs?|seconds?|m|mins?|minutes?|`
    + String.raw`h|hrs?|hours?|d|days?|w|wks?|weeks?|mo|months?|y|yrs?|years?)\b(?:\s+ago)?)|\b\d{1,2}:\d{2}(?:\s*[ap]\.?m\.?)?`, "gi");
  const typed = new WeakMap(); // a reply box -> what AI Browser typed there last
  const FIELDS = ["id", "from", "subject", "snippet", "url", "time"];

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
  // still holds only what AI Browser typed before (a newer draft used), the new text replaces it.
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

  function clean(item) { // only these fields, as strings, trimmed: the engine checks them again
    const out = {};
    for (const key of FIELDS) {
      out[key] = typeof item[key] === "string" ? item[key].slice(0, key === "snippet" ? 500 : 2000) : "";
    }
    out.unread = item.unread !== false;
    out.from_me = item.from_me === true;
    return out;
  }

  function reader(kind) {
    const found = AIB.readers[kind];
    if (!found) throw new Error(`no reader for ${kind}`);
    return found;
  }

  const AIB = globalThis.AIB = {
    key: "{{KEY}}",
    readers: {},
    text, hash, stableText, ownEmail, typeInto, waitFor, sleep,
    // What the tab shows now: {known: true, items}, {known: "elsewhere", note} (a page of the site this reader doesn't
    // read) or {known: false} (a layout it doesn't recognise). Items are plain strings, never markup.
    read(kind, config = {}) {
      const site = reader(kind);
      let known = false;
      try {
        known = site.check(config);
      } catch {
        known = false;
      }
      if (known === "elsewhere") {
        return { known: "elsewhere", note: site.elsewhere || "open the page to watch in this tab" };
      }
      if (known !== true) return { known: false };
      let items = [];
      try {
        items = site.items(config) || [];
      } catch {
        items = [];
      }
      const out = items.filter((item) => item && typeof item.id === "string" && item.id).slice(0, 200).map(clean);
      return { known: true, items: out, ...(site.memory ? { memory: site.memory() } : {}) };
    },
    thread(kind, config = {}) { // the open thread's text, for a draft
      let value = "";
      try {
        value = reader(kind).thread(config) || "";
      } catch {
        value = "";
      }
      return { text: String(value).slice(0, 20000) };
    },
    async fill(kind, value, config = {}) { // the reply the user chose to use, in the reply box; never sent
      try {
        const result = await reader(kind).fill(String(value || ""), config);
        return { ok: result?.ok === true, reason: String(result?.reason || "") };
      } catch (error) {
        return { ok: false, reason: String(error?.message || error) };
      }
    },
    loaded() {
      return document.readyState === "complete";
    },
  };
})();
