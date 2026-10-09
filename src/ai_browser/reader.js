/* ai-browser page reader: defines window.__aib once per document, in its own isolated world ("aib"), where the page's
   scripts can neither see nor change it.
   Derived from jev-ultrafast's snapshot.js (MIT, browser-use). */
(() => {
  if (window.__aib) return;

  const ROLES = ["button", "link", "checkbox", "radio", "switch", "tab", "menuitem", "menuitemradio",
    "menuitemcheckbox", "option", "gridcell", "combobox", "textbox", "searchbox", "spinbutton", "slider",
    "treeitem", "listbox"];
  const SELECTOR = 'a[href],button,input,textarea,select,summary,[contenteditable=""],[contenteditable="true"],' +
    '[contenteditable="plaintext-only"],[draggable="true"],[onclick],[tabindex]:not([tabindex="-1"]),' +
    ROLES.map((r) => `[role="${r}"]`).join(",");
  const POINTER_TAGS = new Set(["DIV", "SPAN", "LI", "IMG", "svg", "I", "LABEL", "TD", "P", "H1", "H2", "H3",
    "H4", "H5", "H6", "SECTION", "ARTICLE", "FIGURE"]);
  const POINTER_CHECKS = 2000;
  const CLICKABLE = new Set(["button", "link", "menuitem", "menuitemradio", "menuitemcheckbox", "tab", "clickable",
    "option", "gridcell", "treeitem", "draggable"]);
  const SKIP_TEXT = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE"]);

  const ids = new WeakMap();
  const nodes = new Map();
  const sigs = new Map();
  let next = 1;
  let riskyRe = null;
  let downloadsRisky = false; // the user's own browser: a link that downloads is ⚠ too
  const downloadLink = (el) => el.tagName === "A" && el.hasAttribute("download");
  let nameLimit = 80;

  const idOf = (el) => {
    let n = ids.get(el);
    if (!n) { n = next++; ids.set(el, n); }
    nodes.set(n, el);
    return "e" + n;
  };
  const byId = (id) => nodes.get(Number(String(id).slice(1)));
  const winOf = (el) => el.ownerDocument.defaultView;
  const styleOf = (el) => winOf(el).getComputedStyle(el);
  // Clip by whole characters, never inside an emoji's surrogate pair.
  const clip = (s, n) => {
    if (s.length <= n) return s;
    const chars = Array.from(s);
    return chars.length > n ? chars.slice(0, n - 1).join("") + "…" : s;
  };
  const squash = (s) => String(s || "").replace(/\s+/g, " ").trim();

  const visible = (el) => {
    if (!el.isConnected) return false;
    if (el.closest && el.closest('[aria-hidden="true"],[inert]')) return false;
    if (el.checkVisibility && !el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const disabled = (el) => !!(el.disabled || (el.matches && el.matches(":disabled")) ||
    (el.closest && el.closest('[aria-disabled="true"]')));
  const editable = (el) => el.isContentEditable ||
    (el.tagName === "TEXTAREA" && !el.readOnly) ||
    (el.tagName === "INPUT" && !el.readOnly && !["checkbox", "radio", "button", "submit", "reset", "image", "file",
      "hidden", "range", "color"].includes((el.type || "text").toLowerCase()));

  const roleOf = (el) => {
    const explicit = (el.getAttribute("role") || "").split(/\s+/)[0];
    if (ROLES.includes(explicit)) return explicit;
    const tag = el.tagName;
    if (tag === "BUTTON" || tag === "SUMMARY") return "button";
    if (tag === "A" && el.hasAttribute("href")) return "link";
    if (tag === "SELECT") return "select";
    if (tag === "TEXTAREA") return "textbox";
    if (tag === "INPUT") {
      const type = (el.type || "text").toLowerCase();
      if (type === "hidden") return null;
      if (type === "checkbox" || type === "radio") return type;
      if (["button", "submit", "reset", "image", "color"].includes(type)) return "button";
      if (type === "search") return "searchbox";
      if (type === "number") return "spinbutton";
      if (type === "range") return "slider";
      if (type === "file") return "upload";
      if (type === "password") return "password";
      return "textbox";
    }
    if (el.isContentEditable) return "textbox";
    if (el.getAttribute("draggable") === "true") return "draggable";
    return "clickable";
  };

  const nodeText = (n, seen) => {
    if (n.nodeType === 3) return n.textContent;
    if (n.nodeType !== 1 || SKIP_TEXT.has(n.tagName) || n.getAttribute("aria-hidden") === "true") return "";
    if (n.tagName === "SLOT") {  // web components: the label lives in the light DOM assigned to the slot
      const assigned = n.assignedNodes({ flatten: true });
      if (assigned.length) return assigned.map((a) => nodeText(a, seen)).join(" ");
    }
    return nameOf(n, seen, true);
  };
  const childText = (el, seen) => [...el.childNodes].map((n) => nodeText(n, seen)).join(" ");

  const nameOf = (el, seen = new Set(), inner = false) => {
    if (!el || seen.has(el)) return "";
    seen.add(el);
    const root = el.getRootNode();
    const labelled = (el.getAttribute("aria-labelledby") || "").split(/\s+/).filter(Boolean)
      .map((id) => nameOf(root.getElementById ? root.getElementById(id) : null, seen, true))
      .filter(Boolean).join(" ");
    if (labelled) return squash(labelled);
    const aria = el.getAttribute("aria-label");
    if (aria && aria.trim()) return squash(aria);
    if (!inner && el.labels && el.labels.length) {
      const fromLabels = [...el.labels].map((l) => nameOf(l, seen, true)).filter(Boolean).join(" ");
      if (fromLabels) return squash(fromLabels);
    }
    const tag = el.tagName;
    if (tag === "INPUT" && ["button", "submit", "reset"].includes(el.type)) return squash(el.value || el.type);
    if (tag === "IMG") return squash(el.getAttribute("alt") || "");
    if (!["INPUT", "SELECT", "TEXTAREA"].includes(tag) && !el.isContentEditable) {
      const text = squash(childText(el, seen));
      if (text) return text;
      const img = el.querySelector && el.querySelector("img[alt],svg title");
      if (img) return squash(img.getAttribute("alt") || img.textContent);
    }
    return squash(el.getAttribute("title") || el.getAttribute("placeholder") ||
      el.getAttribute("aria-placeholder") || el.getAttribute("data-placeholder") || "");
  };

  // Fields whose contents must never reach the model or the logs (typed by the user during a takeover).
  const SECRET_AUTOCOMPLETE = /\b(cc-|one-time-code|current-password|new-password)/i;
  const SECRET_NAME = /pass(word)?|passwd|otp|cvc|cvv|card.?number/i;
  const secret = (el) => el.tagName === "INPUT" &&
    (SECRET_AUTOCOMPLETE.test(el.getAttribute("autocomplete") || "") ||
     SECRET_NAME.test((el.getAttribute("name") || "") + " " + (el.id || "")));

  const valueOf = (el, role) => {
    if (role === "password") return undefined;
    if (secret(el)) return el.value ? "•••" : "";
    if (role === "select") return [...el.selectedOptions].map((o) => o.label.trim()).join(", ");
    if (role === "upload") return [...(el.files || [])].map((f) => f.name).join(", ");
    if (["checkbox", "radio", "button", "link", "clickable", "draggable", "switch", "tab", "option",
      "menuitem", "menuitemradio", "menuitemcheckbox", "treeitem", "gridcell"].includes(role)) return undefined;
    if (el.isContentEditable) return clip(squash(el.innerText), 200);
    if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") return clip(String(el.value), 200);
    if (["combobox", "textbox", "searchbox", "spinbutton", "slider"].includes(role)) {
      const v = el.getAttribute("aria-valuetext") || el.getAttribute("aria-valuenow") || squash(el.innerText);
      return clip(String(v || ""), 200);
    }
    return undefined;
  };

  const hrefOf = (el) => {
    const raw = el.getAttribute("href") || "";
    if (/^javascript:/i.test(raw)) return "javascript:…";
    let url;
    try { url = new URL(el.href); } catch (e) { return clip(raw, 100); }
    const here = el.ownerDocument.location;
    const short = url.origin === here.origin ? url.pathname + url.search + url.hash : url.href;
    return clip(short, 100);
  };

  // Identity check for targets: same role and accessible name as when the row was shown.
  const sigOf = (el, role, name) => role + "\u0001" + name;

  const rowOf = (el, role, frame) => {
    const name = clip(nameOf(el), nameLimit);
    const row = { id: idOf(el), role, name };
    const value = valueOf(el, role);
    if (value !== undefined) row.value = value;
    if (frame) row.frame = frame;
    if (role === "checkbox" || role === "radio") row.checked = el.indeterminate ? "mixed" : !!el.checked;
    else {
      const checked = el.getAttribute("aria-checked");
      if (checked !== null) row.checked = checked === "mixed" ? "mixed" : checked === "true";
    }
    const expanded = el.getAttribute("aria-expanded");
    if (expanded !== null) row.expanded = expanded === "true";
    if (el.getAttribute("aria-selected") === "true") row.selected = true;
    if (disabled(el)) row.disabled = true;
    if (el.isContentEditable) row.editable = true;
    if (role === "link") row.href = hrefOf(el);
    if (role === "select") {
      const options = [...el.options].filter((o) => !o.disabled).map((o) => o.label.trim());
      row.options = options.slice(0, 8);
      if (options.length > 8) row.more = options.length - 8;
    }
    if (CLICKABLE.has(role) && ((riskyRe && riskyRe.test(name)) || (downloadsRisky && downloadLink(el)))) {
      row.risky = true;
    }
    return row;
  };

  // Element whose box we click: the element itself, or the visible label of a visually hidden checkbox.
  const geometryOf = (el) => {
    if (visible(el)) return el;
    if (el.labels) {
      const label = [...el.labels].find(visible);
      if (label) return label;
    }
    return null;
  };

  const frameOffset = (el) => {
    let x = 0, y = 0, win = winOf(el);
    while (win && win !== window && win.frameElement) {
      const fe = win.frameElement, r = fe.getBoundingClientRect(), cs = styleOf(fe);
      x += r.left + fe.clientLeft + parseFloat(cs.paddingLeft);
      y += r.top + fe.clientTop + parseFloat(cs.paddingTop);
      win = winOf(fe);
    }
    return { x, y };
  };

  const collect = (opts) => {
    const find = opts.find ? String(opts.find).toLowerCase() : null;
    const out = [], frames = [], seen = new Set();
    let above = 0, below = 0, pointerChecks = 0;
    const topW = innerWidth, topH = innerHeight;

    const place = (geo, ctx) => {
      const r = geo.getBoundingClientRect();
      const top = r.top + ctx.y, bottom = r.bottom + ctx.y, left = r.left + ctx.x, right = r.right + ctx.x;
      const inFrame = r.bottom > 0 && r.top < ctx.h && r.right > 0 && r.left < ctx.w;
      const inView = inFrame && bottom > 0 && top < topH && right > 0 && left < topW;
      return { inView, top, bottom, left, h: r.height };
    };
    const entry = (p, row) => ({ top: p.top, left: p.left, h: p.h, row });

    const consider = (el, role, ctx) => {
      if (seen.has(el)) return;
      seen.add(el);
      let geo = geometryOf(el);
      if (!geo && role === "upload") geo = el.parentElement && geometryOf(el.parentElement);
      if (!geo) return;
      const p = place(geo, ctx);
      if (find) {
        const row = rowOf(el, role, ctx.label);
        const hay = (row.name + " " + (row.value || "") + " " + (row.href || "")).toLowerCase();
        if (hay.includes(find)) out.push(entry(p, row));
        return;
      }
      if (!p.inView) {
        if (p.bottom <= 0) above++;
        else if (p.top >= topH) below++;
        return;
      }
      out.push(entry(p, rowOf(el, role, ctx.label)));
    };

    const pointer = (el, ctx) => {
      if (find || seen.has(el) || !POINTER_TAGS.has(el.tagName) || pointerChecks >= POINTER_CHECKS) return;
      if (el.tagName === "LABEL" && el.control) return;  // its control is already a row
      const p = place(el, ctx);
      if (!p.inView) return;
      pointerChecks++;
      if (styleOf(el).cursor !== "pointer") return;
      const parent = el.parentElement;
      if (parent && styleOf(parent).cursor === "pointer") return;
      if (el.querySelector(SELECTOR) || !visible(el)) return;
      seen.add(el);
      out.push(entry(p, rowOf(el, "clickable", ctx.label)));
    };

    const frame = (iframe, ctx) => {
      if (!visible(iframe)) return;
      const r = iframe.getBoundingClientRect();
      if (r.width < 20 || r.height < 20) return;
      let doc = null;
      try { doc = iframe.contentDocument; } catch (e) { doc = null; }
      let label = iframe.getAttribute("name") || iframe.getAttribute("title") || iframe.id ||
        iframe.getAttribute("aria-label");
      if (!doc || !doc.documentElement) {
        if (!label) { try { label = new URL(iframe.src).hostname; } catch (e) { label = "frame"; } }
        frames.push({ label, url: iframe.src, cross: true });
        return;
      }
      label = label || "frame" + (frames.length + 1);
      frames.push({ label, url: doc.location.href, cross: false });
      const cs = styleOf(iframe);
      walk(doc, {
        x: ctx.x + r.left + iframe.clientLeft + parseFloat(cs.paddingLeft),
        y: ctx.y + r.top + iframe.clientTop + parseFloat(cs.paddingTop),
        w: iframe.clientWidth, h: iframe.clientHeight, label,
      });
    };

    const walk = (root, ctx) => {
      for (const el of root.querySelectorAll(SELECTOR)) {
        const role = roleOf(el);
        if (role) consider(el, role, ctx);
      }
      for (const el of root.querySelectorAll("*")) {
        if (el.shadowRoot) walk(el.shadowRoot, ctx);
        else if (el.tagName === "IFRAME" || el.tagName === "FRAME") frame(el, ctx);
        else pointer(el, ctx);
      }
    };

    walk(document, { x: 0, y: 0, w: topW, h: topH, label: null });
    return { rows: readingOrder(out), frames, above, below };
  };

  // Group entries into visual lines (vertical centers close together), then left to right.
  const readingOrder = (entries) => {
    entries.sort((a, b) => a.top - b.top || a.left - b.left);
    const lines = [];
    for (const item of entries) {
      const center = item.top + item.h / 2;
      let line = null;
      for (let i = lines.length - 1; i >= Math.max(0, lines.length - 3); i--) {
        const candidate = lines[i];
        if (Math.abs(center - candidate.center) <= Math.max(8, Math.min(item.h, candidate.h) / 2)) {
          line = candidate;
          break;
        }
      }
      if (line) line.items.push(item);
      else lines.push({ center, h: item.h, items: [item] });
    }
    return lines.flatMap((line) => line.items.sort((a, b) => a.left - b.left)).map((item) => item.row);
  };

  const visibleText = (limit, find) => {
    const parts = [];
    let length = 0;
    for (const doc of sameOriginDocs()) {
      if (!doc.body) continue;
      const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
      const range = doc.createRange();
      const offset = doc === document ? { x: 0, y: 0 } : frameOffset(doc.body);
      let node;
      while ((node = walker.nextNode()) && length < limit) {
        const value = squash(node.textContent);
        const parent = node.parentElement;
        if (!value || !parent || SKIP_TEXT.has(parent.tagName) || parent.closest("script,style,noscript,template")) continue;
        if (find) {
          const at = value.toLowerCase().indexOf(find);
          if (at === -1) continue;
          const snippet = value.slice(Math.max(0, at - 50), at + find.length + 70);
          parts.push(snippet);
          length += snippet.length;
          if (parts.length >= 10) break;
          continue;
        }
        if (!visible(parent)) continue;
        range.selectNodeContents(node);
        const r = range.getBoundingClientRect();
        const top = r.top + offset.y, left = r.left + offset.x;
        if (r.width > 0 && r.height > 0 && top + r.height > 0 && top < innerHeight && left + r.width > 0 && left < innerWidth) {
          parts.push(value);
          length += value.length + 1;
        }
      }
    }
    return clip(parts.join("\n"), limit);
  };

  const containsDeep = (outer, inner) => {
    for (let n = inner; n; n = n.assignedSlot || n.parentNode || n.host) if (n === outer) return true;
    return false;
  };

  // Topmost element at a top-level viewport point, looking through open shadow roots and same-origin frames.
  const deepHit = (x, y) => {
    let doc = document, offX = 0, offY = 0, el = null;
    for (let depth = 0; depth < 10; depth++) {
      el = doc.elementFromPoint(x - offX, y - offY);
      while (el && el.shadowRoot) {
        const root = el.shadowRoot;
        let inner = root.elementFromPoint(x - offX, y - offY);
        if (inner === el) {  // over slotted light-DOM text: find what renders it inside the shadow tree
          inner = root.elementsFromPoint(x - offX, y - offY).find((n) => n !== el && root.contains(n)) || null;
        }
        if (!inner || inner === el) break;
        el = inner;
      }
      if (!el || (el.tagName !== "IFRAME" && el.tagName !== "FRAME")) return el;
      let inner = null;
      try { inner = el.contentDocument; } catch (e) { inner = null; }
      if (!inner) return el;
      const r = el.getBoundingClientRect(), cs = styleOf(el);
      offX += r.left + el.clientLeft + parseFloat(cs.paddingLeft);
      offY += r.top + el.clientTop + parseFloat(cs.paddingTop);
      doc = inner;
    }
    return el;
  };

  const describe = (el) => {
    if (!el) return "nothing";
    const id = el.id ? "#" + el.id : "";
    const cls = typeof el.className === "string" && el.className.trim() ? "." + el.className.trim().split(/\s+/)[0] : "";
    const text = clip(squash(el.innerText || el.textContent || ""), 30);
    return el.tagName.toLowerCase() + id + cls + (text ? ` "${text}"` : "");
  };

  const centerOf = (geo) => {
    const r = geo.getBoundingClientRect(), o = frameOffset(geo);
    const lx = r.left + r.width / 2, ly = r.top + r.height / 2;
    return { x: o.x + lx, y: o.y + ly, lx, ly };
  };
  const inView = (geo, c) => {
    const w = winOf(geo);
    return c.x >= 0 && c.y >= 0 && c.x < innerWidth && c.y < innerHeight &&
      c.lx >= 0 && c.ly >= 0 && c.lx < w.innerWidth && c.ly < w.innerHeight;
  };

  const placeCaret = (el, toEnd) => {
    const doc = el.ownerDocument, range = doc.createRange(), selection = doc.getSelection();
    range.selectNodeContents(el);
    if (toEnd) range.collapse(false);
    selection.removeAllRanges();
    selection.addRange(range);
  };

  const sameOriginDocs = () => {
    const docs = [document];
    for (const f of document.querySelectorAll("iframe,frame")) {
      try { if (f.contentDocument && f.contentDocument.body) docs.push(f.contentDocument); } catch (e) { /* cross-site */ }
    }
    return docs;
  };

  const textIn = (needle) => sameOriginDocs().some((d) => d.body && d.body.innerText.toLowerCase().includes(needle));

  // Safety limits only; extract reports when one is hit.
  const LINK_CAP = 50000, ROW_CAP = 100000, TABLE_CAP = 100;
  const extractors = {
    links() {
      const seen = new Set(), items = [];
      let total = 0;
      for (const doc of sameOriginDocs()) {
        for (const a of doc.querySelectorAll("a[href]")) {
          const href = a.href;
          if (!href || /^javascript:/i.test(href)) continue;
          const text = clip(squash(a.innerText || a.getAttribute("aria-label") || a.title || ""), 120);
          const key = href + "\u0001" + text;
          if (seen.has(key)) continue;
          seen.add(key);
          total++;
          if (items.length < LINK_CAP) items.push({ text, href });
        }
      }
      return { items, total };
    },
    tables() {
      const items = [];
      let total = 0;
      for (const doc of sameOriginDocs()) {
        for (const table of doc.querySelectorAll("table")) {
          const all = [...table.rows];
          if (!all.length) continue;
          total++;
          if (items.length >= TABLE_CAP) continue;
          const rows = all.slice(0, ROW_CAP).map((tr) => [...tr.cells].map((cell) => squash(cell.innerText)));
          items.push({ caption: table.caption ? squash(table.caption.innerText) : "", rows, totalRows: all.length });
        }
      }
      return { items, total };
    },
    meta() {
      const attr = (selector, name = "content") => {
        const el = document.querySelector(selector);
        return el ? el.getAttribute(name) : null;
      };
      const og = {};
      for (const m of document.querySelectorAll('meta[property^="og:"]')) og[m.getAttribute("property")] = m.getAttribute("content");
      const images = [...document.images];
      const noAlt = images.filter((img) => !img.hasAttribute("alt"));
      return {
        title: document.title,
        lang: document.documentElement.lang || null,
        description: attr('meta[name="description"]'),
        canonical: attr('link[rel="canonical"]', "href"),
        robots: attr('meta[name="robots"]'),
        viewport: attr('meta[name="viewport"]'),
        og,
        headings: [...document.querySelectorAll("h1,h2,h3,h4,h5,h6")].slice(0, 80)
          .map((h) => [Number(h.tagName[1]), clip(squash(h.innerText), 100)]),
        images: images.length,
        noAlt: noAlt.length,
        noAltExamples: noAlt.slice(0, 5).map((img) => clip(img.currentSrc || img.src, 100)),
        links: document.links.length,
        words: document.body ? document.body.innerText.split(/\s+/).filter(Boolean).length : 0,
      };
    },
  };

  // Bot-check signals: a few facts about the top page, for the rules in checks.py (Python decides). Nothing inside a
  // check frame is read: only its address, its size and whether it shows.
  const CHECK_FRAME = /\/recaptcha\/(?:api2|enterprise)\/|hcaptcha\.com|challenges\.cloudflare\.com|\/cdn-cgi\/challenge-platform\/|arkoselabs\.com|funcaptcha\.com/i;
  const CHECK_IDS = ["px-captcha", "challenge-form", "challenge-stage", "challenge-running"];
  const readSignals = () => {
    const text = document.body ? squash(document.body.innerText) : "";
    let status = 0;
    try {
      const entry = performance.getEntriesByType("navigation")[0];
      status = (entry && entry.responseStatus) || 0;
    } catch (e) {
      status = 0;
    }
    const frames = [];
    for (const frame of document.querySelectorAll("iframe,frame")) {
      const src = String(frame.src || "");
      if (!CHECK_FRAME.test(src) || frames.length >= 20) continue;
      const r = frame.getBoundingClientRect();
      frames.push({ src: src.slice(0, 2000), w: Math.round(r.width), h: Math.round(r.height),
        onScreen: r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth, visible: visible(frame) });
    }
    return { url: location.href, title: String(document.title || "").slice(0, 200), text: text.slice(0, 2000),
      textLength: text.length, status, ids: CHECK_IDS.filter((id) => document.getElementById(id)), frames };
  };

  const docId = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Math.random()).slice(2);

  const api = {
    doc: docId,

    count() {
      return document.querySelectorAll(SELECTOR).length;
    },

    signals() {
      return readSignals();
    },

    // True when a freshly opened page has something to read: controls, real text, or nothing at all (blank).
    ready() {
      if (location.href === "about:blank" || document.querySelector(SELECTOR)) return true;
      return !!document.body && document.body.innerText.trim().length >= 200;
    },

    observe(opts) {
      riskyRe = opts.risky ? new RegExp(opts.risky, "i") : null;
      downloadsRisky = !!opts.downloads;
      nameLimit = opts.nameLimit || 80;
      for (const [n, el] of nodes) if (!el.isConnected) { nodes.delete(n); sigs.delete("e" + n); }
      const { rows, frames, above, below } = collect(opts);
      const maxRows = opts.maxRows || 150;
      const find = opts.find ? String(opts.find).toLowerCase() : null;
      const shown = rows.slice(0, maxRows);
      // Remember identities only for rows the caller actually sees; targets are checked against these.
      for (const row of shown) {
        const el = byId(row.id);
        if (el) sigs.set(row.id, sigOf(el, row.role, row.name));
      }
      return {
        url: location.href,
        title: document.title,
        w: innerWidth,
        h: innerHeight,
        scrollY: Math.round(scrollY),
        scrollH: document.documentElement.scrollHeight,
        above,
        below,
        frames,
        rows: shown,
        truncated: Math.max(0, rows.length - maxRows),
        text: visibleText(opts.textLimit || 1500, find),
        doc: docId,
        find: opts.find || null,
        signals: readSignals(),
      };
    },

    // Re-check a row before input. kind: click|dblclick|hover|type|append|select|drag|drop|upload.
    target(id, kind, risky, downloads) {
      const el = byId(id);
      if (!el || !el.isConnected) return { ok: false, reason: "gone" };
      const role = roleOf(el) || "clickable";
      const name = clip(nameOf(el), nameLimit);
      const sig = sigs.get(id);
      if (sig !== undefined && sig !== sigOf(el, role, name)) return { ok: false, reason: "changed" };
      const isRisky = !!(CLICKABLE.has(role) &&
        ((risky && new RegExp(risky, "i").test(name)) || (downloads && downloadLink(el))));
      if (kind === "upload") {
        if (el.tagName !== "INPUT" || el.type !== "file") return { ok: false, reason: "not a file input" };
        return { ok: true, x: 0, y: 0, role, name, risky: false };
      }
      if (disabled(el)) return { ok: false, reason: "disabled" };
      if ((kind === "type" || kind === "append") && !editable(el)) return { ok: false, reason: "not editable" };
      const geo = geometryOf(el);
      if (!geo) return { ok: false, reason: "hidden" };
      let c = centerOf(geo);
      if (!inView(geo, c)) {
        geo.scrollIntoView({ block: "center", inline: "center", behavior: "instant" });
        c = centerOf(geo);
        if (!inView(geo, c)) return { ok: false, reason: "offscreen" };
      }
      if (kind !== "drop") {
        const hit = deepHit(c.x, c.y);
        if (!hit || !(containsDeep(geo, hit) || containsDeep(el, hit))) {
          return { ok: false, reason: "covered", by: describe(hit) };
        }
      }
      return { ok: true, x: c.x, y: c.y, role, name, risky: isRisky };
    },

    node(id) {
      return byId(id) || null;
    },

    // Element box in page coordinates (for screenshots).
    rect(id) {
      const el = byId(id);
      if (!el || !el.isConnected) return null;
      const geo = geometryOf(el) || el, r = geo.getBoundingClientRect(), o = frameOffset(geo);
      return { x: o.x + r.left + scrollX, y: o.y + r.top + scrollY, w: r.width, h: r.height };
    },

    extract(kind) {
      return extractors[kind] ? extractors[kind]() : null;
    },

    state(id) {
      const el = byId(id);
      return el && el.isConnected ? rowOf(el, roleOf(el) || "clickable", null) : null;
    },

    selectContents(id) {
      const el = byId(id);
      if (!el) return false;
      el.focus();
      if (el.isContentEditable) placeCaret(el, false);
      else if (typeof el.select === "function") el.select();
      return true;
    },

    // Move the caret to the end; returns "end-key" when the field has no selection API (email, number).
    caretEnd(id) {
      const el = byId(id);
      if (!el) return false;
      el.focus();
      if (el.isContentEditable) { placeCaret(el, true); return true; }
      try {
        const n = el.value.length;
        el.setSelectionRange(n, n);
        return true;
      } catch (e) {
        return "end-key";
      }
    },

    selectOption(id, value) {
      const el = byId(id);
      if (!el || el.tagName !== "SELECT") return { ok: false, reason: "not a dropdown" };
      const options = [...el.options].filter((o) => !o.disabled);
      const want = String(value).trim().toLowerCase();
      const option = options.find((o) => o.label.trim() === value) || options.find((o) => o.value === value) ||
        options.find((o) => o.label.trim().toLowerCase() === want);
      if (!option) {
        return { ok: false, reason: "no option " + JSON.stringify(value), options: options.map((o) => o.label.trim()).slice(0, 30) };
      }
      if (el.multiple) option.selected = true;
      else {
        // The prototype setter keeps framework-controlled selects (React) in sync.
        const setter = Object.getOwnPropertyDescriptor(winOf(el).HTMLSelectElement.prototype, "value").set;
        setter.call(el, option.value);
      }
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      return { ok: true, value: option.label.trim() };
    },

    scrollIntoView(id) {
      const el = byId(id);
      if (!el || !el.isConnected) return false;
      (geometryOf(el) || el).scrollIntoView({ block: "center", behavior: "instant" });
      return true;
    },

    waitText(text, ms) {
      const needle = String(text).toLowerCase();
      return new Promise((resolve) => {
        if (textIn(needle)) { resolve(true); return; }
        const started = Date.now();
        const timer = setInterval(() => {
          if (textIn(needle)) { clearInterval(timer); resolve(true); }
          else if (Date.now() - started >= ms) { clearInterval(timer); resolve(false); }
        }, 50);
      });
    },

    // Resolve after two animation frames (max 50 ms); autocomplete fields wait for options (max 200 ms).
    settle(id) {
      const el = id ? byId(id) : null;
      const auto = !!el && editable(el) && (el.getAttribute("role") === "combobox" ||
        el.hasAttribute("aria-autocomplete") || el.getAttribute("aria-haspopup") === "listbox");
      const optionsShown = () => {
        const refs = (el.getAttribute("aria-controls") || el.getAttribute("aria-owns") || "").split(/\s+/).filter(Boolean);
        const root = el.getRootNode();
        const scopes = refs.length ? refs.map((ref) => root.getElementById(ref)).filter(Boolean) : [el.ownerDocument];
        return scopes.some((scope) => [...scope.querySelectorAll('[role="option"]')].some(visible));
      };
      return new Promise((resolve) => {
        let frames = 0, done = false;
        const finish = () => { if (!done) { done = true; resolve(true); } };
        setTimeout(finish, auto ? 200 : 50);
        const tick = () => {
          if (done) return;
          if (++frames >= 2 && (!auto || optionsShown())) finish();
          else requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      });
    },
  };

  // Defence in depth: pages never see this world at all, and even here the reader can't be replaced.
  Object.defineProperty(window, "__aib", { value: Object.freeze(api), writable: false, configurable: false,
                                           enumerable: false });
})();
