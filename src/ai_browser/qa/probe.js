// Website QA's in-page probe: links, lazy content, sideways scrolling. Defined once per document as window.__aibqa.
(() => {
  if (window.__aibqa) return;
  const LINK_CAP = 2000;
  const SCAN_CAP = 20000;
  const squash = (s) => String(s || "").replace(/\s+/g, " ").trim();

  // tag#id.class1.class2 "text…" — enough to find the element in the page's code
  const describe = (el) => {
    let label = el.tagName.toLowerCase();
    if (el.id) label += "#" + el.id;
    const classes = [...el.classList].slice(0, 2);
    if (classes.length) label += "." + classes.join(".");
    const text = squash(el.innerText);
    return text ? `${label} "${text.slice(0, 40)}${text.length > 40 ? "…" : ""}"` : label;
  };

  // Inside a box that clips or scrolls sideways, an element cannot make the page itself scroll sideways.
  const insideClip = (el) => {
    for (let a = el.parentElement; a && a !== document.body && a !== document.documentElement; a = a.parentElement) {
      const x = getComputedStyle(a).overflowX;
      if (x === "hidden" || x === "clip" || x === "auto" || x === "scroll") return true;
    }
    return false;
  };

  window.__aibqa = {
    title: () => document.title,

    // Every text a link has on the page (an icon link and a "Log out" link to the same place are one link).
    links() {
      const seen = new Map();
      for (const a of document.querySelectorAll("a[href], area[href]")) {
        const href = a.href;
        if (!/^https?:/i.test(href)) continue;
        if (!seen.has(href)) {
          if (seen.size >= LINK_CAP) continue;
          seen.set(href, []);
        }
        const alts = [...a.querySelectorAll("img[alt]")].map((img) => img.alt).join(" ");
        const text = squash(a.innerText || a.getAttribute("aria-label") || a.title || alts);
        const texts = seen.get(href);
        if (text && !texts.includes(text)) texts.push(text);
      }
      return [...seen.entries()].map(([href, texts]) => [href, texts.join(" · ").slice(0, 200)]);
    },

    // Load lazy images now, and scroll down and back so scroll-triggered content appears too.
    async wake() {
      for (const img of document.querySelectorAll('img[loading="lazy"]')) img.loading = "eager";
      const step = Math.max(200, innerHeight);
      let steps = 0;
      for (let y = step; y < document.documentElement.scrollHeight && steps < 12; y += step, steps++) {
        scrollTo(0, y);
        await new Promise((resolve) => setTimeout(resolve, 60));
      }
      scrollTo(0, 0);
      return steps;
    },

    layout() {
      const root = document.documentElement;
      const overflow = Math.max(0, root.scrollWidth - root.clientWidth);
      // The viewport takes its overflow-x from <html>, or from <body> when <html> leaves it visible; hidden or
      // clip there means visitors can't move the page sideways. (Scrolling by script is no test: scripts may scroll
      // hidden overflow, and phones pan the visual viewport instead.)
      const htmlX = getComputedStyle(root).overflowX;
      const viewportX = htmlX !== "visible" || !document.body ? htmlX : getComputedStyle(document.body).overflowX;
      const scrolls = overflow > 1 && viewportX !== "hidden" && viewportX !== "clip";
      const offenders = [];
      if (scrolls) {
        const edge = root.clientWidth + 1;
        const found = [];
        let scanned = 0;
        for (const el of document.body.querySelectorAll("*")) {
          if (++scanned > SCAN_CAP) break;
          const r = el.getBoundingClientRect();
          if (r.width === 0 || r.height === 0 || r.right + scrollX <= edge) continue;
          if (getComputedStyle(el).position === "fixed" || insideClip(el)) continue;
          found.push([el, Math.round(r.right + scrollX - root.clientWidth)]);
        }
        const flagged = new Set(found.map(([el]) => el));
        for (const [el, over] of found) {
          let outermost = true;
          for (let a = el.parentElement; a; a = a.parentElement) if (flagged.has(a)) { outermost = false; break; }
          if (outermost) offenders.push(`${describe(el)} — ${over} px past the edge`);
          if (offenders.length >= 3) break;
        }
      }
      return { scrolls, overflow, offenders };
    },
  };
})();
