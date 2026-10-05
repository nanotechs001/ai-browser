// The setup page's script. The page holds no secret: it is the one page of AI Browser's that opens anywhere.
"use strict";

// In AI Browser's window the setup steps are a closable tab: the close-tab key (Command-W on a Mac, Ctrl+W elsewhere)
// closes this tab, never the whole window, which would stop AI Browser. This file imports nothing (it opens in Brave
// too, where the key is the browser's, as on any page), so it has its own copy of nav.js's closeTabKey.
if (window.parent !== window) {
  const mac = /mac/i.test(navigator.userAgentData?.platform || navigator.platform || "");
  document.addEventListener("keydown", (event) => {
    const command = mac ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey;
    if (!command || event.altKey || event.shiftKey || String(event.key).toLowerCase() !== "w") return;
    event.preventDefault();
    if (!event.repeat) window.parent.postMessage({ type: "close-tab" }, location.origin);
  }, true);
}
