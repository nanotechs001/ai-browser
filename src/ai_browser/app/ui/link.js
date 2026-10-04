// The line to `ai-browser app`, two ways in. AI Browser's window (an http page the app serves) opens /ws on its own
// address: the window's cookie goes with it, and a page that this run of the app didn't open is refused (close code
// 4403), so it stops trying. Brave's watcher (a chrome-extension page) reads config.json (the server's address and
// token) again before every attempt, so a restarted app, on a new port with a new token, is found again. Pings from the
// server keep the watcher's service worker, and its socket, alive.
"use strict";

const REFUSED = 4403; // the server's close code for a socket it won't take

async function address() {
  if (location.protocol === "http:") return `ws://${location.host}/ws`; // the window: its cookie goes along
  const config = await (await fetch(chrome.runtime.getURL("config.json"), { cache: "no-store" })).json();
  return `${config.server.replace(/^http/, "ws")}/ws?token=${encodeURIComponent(config.token)}`;
}

export function connect({ view, onMessage = () => {}, onState = () => {} }) {
  let socket = null;
  let retries = 0;
  let refused = false;
  const waiters = [];

  function retry() {
    if (!refused) setTimeout(open, Math.min(5000, 250 * 2 ** retries++));
  }

  async function open() {
    onState("connecting");
    let ws;
    try {
      ws = new WebSocket(await address());
    } catch {
      onState("disconnected");
      retry();
      return;
    }
    ws.onopen = () => {
      retries = 0;
      socket = ws;
      ws.send(JSON.stringify({ type: "hello", view }));
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
      if (event.code === REFUSED && location.protocol === "http:") { // not this run's window: retrying can't help
        refused = true;
        onState("refused");
        return;
      }
      onState("disconnected");
      retry();
    };
  }

  open();
  return {
    send(message) {
      if (!socket || socket.readyState !== WebSocket.OPEN) return false;
      socket.send(JSON.stringify(message));
      return true;
    },
    whenOpen() {
      if (socket && socket.readyState === WebSocket.OPEN) return Promise.resolve();
      return new Promise((resolve) => waiters.push(resolve));
    },
  };
}
