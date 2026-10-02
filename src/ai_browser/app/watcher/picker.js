// Pick the part of a page to watch: an outline follows the mouse; a click picks the element under it, Escape
// cancels. The pick is a CSS selector that matches exactly that element, sent to the Brain page with a sample of its
// text. Injected only when the user clicks "Pick the part to watch".
"use strict";
(() => {
  if (globalThis.AIB_PICKER) return;
  globalThis.AIB_PICKER = true;
  const outline = document.createElement("div");
  Object.assign(outline.style, { position: "fixed", zIndex: "2147483647", pointerEvents: "none", borderRadius: "4px",
                                 border: "2px solid #c96442", background: "rgba(201, 100, 66, 0.12)" });
  document.documentElement.append(outline);
  let current = null;

  function part(node) {
    if (node.id && /^[A-Za-z][\w-]*$/.test(node.id)) return `#${node.id}`;
    let selector = node.tagName.toLowerCase();
    const classes = [...node.classList].filter((name) => /^[A-Za-z][\w-]*$/.test(name)).slice(0, 2);
    if (classes.length) selector += `.${classes.join(".")}`;
    const siblings = node.parentElement ? [...node.parentElement.children].filter((other) =>
      other.tagName === node.tagName) : [];
    if (siblings.length > 1) selector += `:nth-of-type(${siblings.indexOf(node) + 1})`;
    return selector;
  }

  function selectorFor(node) {
    const parts = [];
    for (let at = node; at && at !== document.documentElement; at = at.parentElement) {
      parts.unshift(part(at));
      const selector = parts.join(" > ");
      if (document.querySelectorAll(selector).length === 1 && (parts.length > 1 || parts[0].startsWith("#"))) {
        return selector;
      }
    }
    return parts.join(" > ");
  }

  function finish(message) {
    removeEventListener("mousemove", onMove, true);
    removeEventListener("click", onClick, true);
    removeEventListener("keydown", onKey, true);
    outline.remove();
    delete globalThis.AIB_PICKER;
    chrome.runtime.sendMessage(message).catch(() => {});
  }

  function onMove(event) {
    current = event.target;
    const box = current.getBoundingClientRect();
    Object.assign(outline.style, { left: `${box.left}px`, top: `${box.top}px`, width: `${box.width}px`,
                                   height: `${box.height}px` });
  }

  function onClick(event) {
    event.preventDefault();
    event.stopPropagation();
    const picked = event.target instanceof Element ? event.target : current;
    if (!picked) return;
    finish({ type: "picked", selector: selectorFor(picked), sample: (picked.innerText || "").slice(0, 300) });
  }

  function onKey(event) {
    if (event.key === "Escape") finish({ type: "picked", cancelled: true });
  }

  addEventListener("mousemove", onMove, true);
  addEventListener("click", onClick, true);
  addEventListener("keydown", onKey, true);
})();
