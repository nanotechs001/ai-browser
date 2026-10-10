// The line to `ai-browser app`. AI Browser's window (an http page the app serves) opens /ws on its own address: the
// window's cookie goes with it, and a page that this run of the app didn't open is refused (close code 4403), so it
// stops trying. Pings from the server keep the socket alive.
"use strict";

const REFUSED = 4403; // the server's close code for a socket it won't take

function address() {
  return `ws://${location.host}/ws`; // the window: its cookie goes along
}

// shown(): whether the page shows the Brain's hand-off cards now (Mission Control: only while the Brain's chat is
// open); seen() tells the app at once when that changed
export function connect({ view, onMessage = () => {}, onState = () => {}, shown = () => true }) {
  let socket = null;
  let retries = 0;
  let refused = false;
  const waiters = [];
  // Whether this page can be seen: the window shows it and, inside the window's tab menu (app.js), its tab is the one
  // in front. A page in the tab menu's frame counts as hidden until the tab menu says otherwise, which it does as the
  // page loads and on every switch. The Brain's hand-off counts down only while a page can show its card.
  const framed = window.parent !== window;
  let inFront = !framed;
  let told = null; // what the app last heard
  const seen = () => !document.hidden && inFront && shown();

  function report() { // only a change, and only on an open line: a hello says it anew
    const now = seen();
    if (now === told || !socket || socket.readyState !== WebSocket.OPEN) return;
    told = now;
    socket.send(JSON.stringify({ type: "visibility", visible: now }));
  }

  function retry() {
    if (!refused) setTimeout(open, Math.min(5000, 250 * 2 ** retries++));
  }

  async function open() {
    onState("connecting");
    let ws;
    try {
      ws = new WebSocket(address());
    } catch {
      onState("disconnected");
      retry();
      return;
    }
    ws.onopen = () => {
      retries = 0;
      socket = ws;
      told = seen();
      ws.send(JSON.stringify({ type: "hello", view, visible: told }));
      onState("connected");
      for (const resolve of waiters.splice(0)) resolve();
    };
    ws.onmessage = (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      if (message && message.type !== "ping") onMessage(message);
    };
    ws.onclose = (event) => {
      if (socket === ws) socket = null;
      if (event.code === REFUSED) { // not this run's window: retrying can't help
        refused = true;
        onState("refused");
        return;
      }
      onState("disconnected");
      retry();
    };
  }

  open();
  document.addEventListener("visibilitychange", report);
  addEventListener("message", (event) => { // the tab menu, and nothing else, says whether this page's tab is in front
    if (!framed || event.source !== window.parent || event.origin !== location.origin) return;
    if (event.data?.type !== "shown") return;
    inFront = event.data.on === true;
    report();
  });
  return {
    send(message) {
      if (!socket || socket.readyState !== WebSocket.OPEN) return false;
      socket.send(JSON.stringify(message));
      return true;
    },
    seen: report, // the page's own change (Mission Control's chat opened or closed): told at once
    whenOpen() {
      if (socket && socket.readyState === WebSocket.OPEN) return Promise.resolve();
      return new Promise((resolve) => waiters.push(resolve));
    },
  };
}
